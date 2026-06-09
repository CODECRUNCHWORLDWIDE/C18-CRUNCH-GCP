# Lecture 1 — Pub/Sub vs. Kafka vs. NATS vs. SQS: when each wins

> **Reading time:** ~75 minutes. **Hands-on time:** ~45 minutes (you stand up a topic, two subscriptions, and a dead-letter topic in Terraform).

This lecture does two jobs. First, it teaches the Pub/Sub data model precisely enough that you can build on it without surprises — topics, subscriptions, the at-least-once default, ordering keys, dead-letter topics, and exactly-once delivery. Second, it places Pub/Sub on the map next to the three brokers you will be asked to compare it against in any real architecture review: Apache Kafka, NATS, and Amazon SQS. By the end you can answer the question every staff engineer asks — *"why Pub/Sub and not Kafka?"* — with a real answer instead of "it's the GCP one."

We do this in order: model first, comparison second. You cannot compare brokers you do not understand, and the comparison is only interesting once you know what Pub/Sub actually guarantees.

## 1.1 — The Pub/Sub data model in one diagram

Pub/Sub has exactly four nouns. Learn them and most of the service falls out.

```
publisher  ──publish──▶  TOPIC  ──fan-out──▶  SUBSCRIPTION_A  ──deliver──▶  subscriber(s)
                           │
                           └──────fan-out──▶  SUBSCRIPTION_B  ──deliver──▶  subscriber(s)
```

- **Topic.** A named resource you publish messages to. A topic has no consumers of its own; it is a pure fan-out point. Publishing to a topic with no subscriptions throws the message away — there is nothing to deliver it to.
- **Subscription.** A named resource attached to exactly one topic. Each subscription gets its own independent copy of every message published to the topic after the subscription was created. Two subscriptions on the same topic are fully isolated: acking a message on `SUBSCRIPTION_A` has no effect on `SUBSCRIPTION_B`.
- **Message.** A payload (bytes, up to 10 MB) plus optional string attributes, a `messageId` assigned by the service, a `publishTime`, and an optional `orderingKey`.
- **Ack.** A subscriber's acknowledgement that it has successfully processed a message. Until a message is acked (or its ack deadline expires), Pub/Sub considers it outstanding and will redeliver it.

The most important consequence of this model: **a topic is not a queue, and a subscription is not a consumer group.** In Kafka, the topic holds the log and consumer groups track offsets into it. In Pub/Sub, the topic is a fan-out point and the subscription is the thing that holds the per-consumer state (the backlog of unacked messages). If you want N independent readers of the same stream, you create N subscriptions, not one subscription with N consumers. If you want N workers sharing the load of one stream, you create one subscription and attach N workers to it — Pub/Sub load-balances messages across the connected clients.

### The default guarantee: at-least-once

Out of the box, Pub/Sub guarantees **at-least-once delivery**. Every published message will be delivered to each subscription at least once. It may be delivered more than once: if a subscriber takes too long to ack (exceeding the ack deadline), or if the ack itself is lost in flight, Pub/Sub redelivers. Your subscriber must therefore be **idempotent** by default — processing the same message twice must produce the same result as processing it once.

This is not a Pub/Sub quirk; it is the default for SQS standard queues and for most Kafka consumer configurations too. At-least-once is the honest default for a distributed message system, because the alternative — at-most-once — drops messages on failure, and you almost never want that. We will see in §1.5 how Pub/Sub upgrades this to exactly-once when you ask for it, and what it costs.

## 1.2 — Pull vs. push subscriptions

A subscription delivers messages to subscribers in one of two modes. The choice is the first real architectural decision you make with Pub/Sub, and exercise 3 has you defend it for two stated patterns.

### Pull subscriptions

In a **pull** subscription, the subscriber initiates. The client library opens a long-lived bidirectional gRPC stream (this is *StreamingPull*, the default in every modern client library) and Pub/Sub pushes messages down that stream as fast as the client's flow-control settings allow. The client acks each message back up the same stream.

```python
from google.cloud import pubsub_v1

subscriber = pubsub_v1.SubscriberClient()
sub_path = subscriber.subscription_path("my-project", "orders-pull")

def callback(message: pubsub_v1.subscriber.message.Message) -> None:
    print(f"received {message.message_id}: {message.data!r}")
    message.ack()

# flow_control caps how many messages / bytes are outstanding at once.
flow_control = pubsub_v1.types.FlowControl(max_messages=100, max_bytes=10 * 1024 * 1024)
future = subscriber.subscribe(sub_path, callback=callback, flow_control=flow_control)

try:
    future.result()  # blocks; runs the callback on a thread pool
except KeyboardInterrupt:
    future.cancel()
    future.result()
```

Pull is the default for a reason. It gives the *consumer* control over flow: the client library's `FlowControl` decides how many messages are outstanding at once, so a slow worker simply pulls slower and the backlog accumulates in Pub/Sub (which retains it for up to 7 days by default, configurable to 31 days). You scale by adding more pull clients to the same subscription. Pull is correct for:

- Worker pools that process at their own pace (the canonical case).
- Dataflow — Dataflow's Pub/Sub source uses pull internally.
- Any consumer behind a firewall with no public ingress (pull is outbound-only).
- Workloads where you want the backlog to absorb a downstream outage.

### Push subscriptions

In a **push** subscription, Pub/Sub initiates. You configure an HTTPS endpoint; Pub/Sub sends each message as an HTTP POST to that endpoint and treats a `2xx` response as the ack. A non-`2xx` (or a timeout) is a nack, and Pub/Sub retries with exponential backoff.

```hcl
resource "google_pubsub_subscription" "orders_push" {
  name  = "orders-push"
  topic = google_pubsub_topic.orders.id

  push_config {
    push_endpoint = "https://ingest.example.com/pubsub/orders"

    # OIDC token so the endpoint can verify the request is from Pub/Sub.
    oidc_token {
      service_account_email = google_service_account.pubsub_pusher.email
      audience              = "https://ingest.example.com/pubsub/orders"
    }

    attributes = {
      x-goog-version = "v1"
    }
  }

  ack_deadline_seconds = 30
}
```

Push is correct for:

- Serverless consumers that have no always-on process to pull — Cloud Run and Cloud Functions are the headline case. Pub/Sub's POST wakes the service; there is nothing to keep running.
- Low-volume, latency-sensitive event delivery where the cost of an always-connected puller is not justified.
- Webhook-style integrations to systems you do not control the runtime of.

The flow-control story is the inverse of pull: with push, **Pub/Sub controls the rate**, ramping up based on the success rate and latency of your endpoint (this is the *push backoff* / slow-start behavior). Your endpoint cannot say "send me at most 100 at a time"; it can only respond slowly or with errors, which Pub/Sub interprets as backpressure. For a Cloud Run service with `max_instances` set, this is exactly what you want — Pub/Sub fills your instances and backs off when they're saturated.

### The decision, compressed

| Question | Pull | Push |
|---|---|---|
| Who initiates delivery? | Subscriber | Pub/Sub |
| Who controls flow? | Subscriber (`FlowControl`) | Pub/Sub (slow-start) |
| Best consumer shape | Always-on worker pool, Dataflow | Cloud Run / Functions, webhooks |
| Network requirement | Outbound only | Public (or internal) HTTPS ingress |
| Backlog absorbs downstream outage? | Yes, naturally | Only as retries; endpoint must come back |
| Auth to consumer | IAM on subscribe | OIDC token in the POST |

There is a third mode worth a sentence: **export subscriptions** (BigQuery and Cloud Storage subscriptions) deliver straight into a sink with no consumer code at all. They are excellent for "I just want the raw stream in BigQuery" and useless when you need to transform or enrich — which is exactly why we use Dataflow this week instead of a BigQuery subscription. Know they exist; we don't use them in the mini-project.

## 1.3 — Ordering keys

By default, Pub/Sub does **not** guarantee order. Messages published in the order A, B, C may be delivered B, A, C. For most analytics workloads this is fine — you are aggregating, and addition commutes. But some workloads need order: a per-account ledger where "deposit \$100" must be applied before "withdraw \$80", or a per-device state machine where events must replay in sequence.

An **ordering key** is a string attribute on a message. Pub/Sub guarantees that messages with the *same* ordering key, published to the *same* region, are delivered to a subscriber **in publish order**. Messages with *different* ordering keys have no ordering relationship to each other and are delivered with full parallelism.

```python
from google.cloud import pubsub_v1

# enable_message_ordering on the publisher is required.
publisher = pubsub_v1.PublisherClient(
    publisher_options=pubsub_v1.types.PublisherOptions(enable_message_ordering=True)
)
topic_path = publisher.topic_path("my-project", "ledger")

# All three messages share ordering_key="acct-42" → delivered in this order.
for amount in (100, -80, 25):
    publisher.publish(
        topic_path,
        data=str(amount).encode("utf-8"),
        ordering_key="acct-42",  # per-account FIFO
    )
```

Three things you must internalize about ordering keys:

1. **Ordering is per key, not global.** This is the feature, not a limitation. Global ordering would force every message through a single serialization point and cap your throughput at one partition's worth. Per-key ordering lets you choose the cardinality of your parallelism: pick `account_id` and every account is an independent ordered stream. Pick a constant and you have global order at the cost of throughput.

2. **The subscription must have `enable_message_ordering = true`.** Both the publisher (the option above) and the subscription must opt in. A subscription without it will deliver ordered-key messages out of order, silently. This is a common Terraform mistake.

3. **Ordering and DLQ interact.** If an ordered message fails repeatedly and you have a dead-letter topic, Pub/Sub will eventually dead-letter it — and to preserve order, it pauses delivery of *later* messages with the same key until the poison message is dead-lettered. A single poison message in an ordered key blocks that key's stream. Design for it: validate aggressively at publish time so poison messages never enter an ordered key.

In Terraform, the subscription side looks like this:

```hcl
resource "google_pubsub_subscription" "ledger_pull" {
  name                       = "ledger-pull"
  topic                      = google_pubsub_topic.ledger.id
  enable_message_ordering    = true   # MUST match publisher intent
  ack_deadline_seconds       = 30
  message_retention_duration = "604800s"  # 7 days
}
```

## 1.4 — Dead-letter topics

Every real stream contains malformed messages. A producer ships a schema change early. A client double-encodes JSON. A field that was always present goes missing. If your subscriber nacks a poison message, Pub/Sub redelivers it — and the subscriber nacks again — forever. The message blocks a worker, the redelivery count climbs, and your processing throughput drops as workers churn on a message they can never process. This is the **poison-message** problem, and the answer is a **dead-letter topic** (DLQ).

You configure a subscription with a `dead_letter_policy`: after a message has been delivered `max_delivery_attempts` times without an ack, Pub/Sub stops redelivering it on the main subscription and instead **republishes it to the dead-letter topic**, with the original message plus attributes recording why and how many times it was attempted (`CloudPubSubDeadLetterSourceDeliveryCount`, `CloudPubSubDeadLetterSourceSubscription`).

```hcl
# The dead-letter topic and a subscription on it so you can inspect failures.
resource "google_pubsub_topic" "orders_dlq" {
  name = "orders-dlq"
}

resource "google_pubsub_subscription" "orders_dlq_pull" {
  name  = "orders-dlq-pull"
  topic = google_pubsub_topic.orders_dlq.id
}

# The main subscription, wired to dead-letter after 5 failed deliveries.
resource "google_pubsub_subscription" "orders_pull" {
  name  = "orders-pull"
  topic = google_pubsub_topic.orders.id

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.orders_dlq.id
    max_delivery_attempts = 5  # min 5, max 100
  }

  ack_deadline_seconds = 30
}
```

The trap that catches everyone the first time: **Pub/Sub itself needs IAM permissions to dead-letter.** The dead-lettering is done by Pub/Sub's own service account, not by you. That service account needs `roles/pubsub.publisher` on the dead-letter topic (to write the poison message) and `roles/pubsub.subscriber` on the source subscription (to ack the poison message on the main subscription so it stops being redelivered). If you skip these grants, the `dead_letter_policy` is configured but silently does nothing — messages keep getting redelivered past `max_delivery_attempts`. Wire it in Terraform:

```hcl
data "google_project" "current" {}

# The Pub/Sub service agent for this project.
locals {
  pubsub_sa = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_topic_iam_member" "dlq_publisher" {
  topic  = google_pubsub_topic.orders_dlq.id
  role   = "roles/pubsub.publisher"
  member = local.pubsub_sa
}

resource "google_pubsub_subscription_iam_member" "main_subscriber" {
  subscription = google_pubsub_subscription.orders_pull.id
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_sa
}
```

Exercise 1 has you build exactly this and prove a malformed message lands in the DLQ. The mini-project adds the alert that fires when the DLQ accumulates — because a DLQ nobody watches is a silent failure waiting to happen.

## 1.5 — Exactly-once delivery

"Exactly-once" is the most over-claimed property in streaming. Let's be precise about what Pub/Sub gives you and what it cannot.

You enable it per-subscription:

```hcl
resource "google_pubsub_subscription" "orders_eos" {
  name                         = "orders-eos"
  topic                        = google_pubsub_topic.orders.id
  enable_exactly_once_delivery = true

  # Exactly-once requires a regional pull (no push, no global endpoint).
  # The client must use the regional service endpoint matching the message-storage region.
}
```

With `enable_exactly_once_delivery = true`, Pub/Sub guarantees: **for a single subscription, once a message is successfully acknowledged, it will not be redelivered.** The mechanism is a combination of a per-message acknowledgement ID that is invalidated atomically on ack, and a lease (the ack deadline) that, when extended, returns a fresh ack ID — so a stale ack from a slow worker after the deadline expired is rejected rather than honored. The client library surfaces this: `message.ack()` now returns a future that tells you whether the ack was *durably recorded*, and you only treat the message as done when it was.

Here are the three places engineers think they have exactly-once and don't:

1. **Publish-side duplicates are not deduplicated.** If your *publisher* retries a publish because it didn't get a publish ACK (network blip), Pub/Sub may store two messages with different `messageId`s carrying the same payload. Exactly-once is about *delivery* of a stored message, not *de-duplication of publishes*. If you need publish-side idempotency, you must add it yourself — typically a deterministic message attribute (`event_id`) that the consumer dedupes on. Dataflow's Pub/Sub source can dedupe on a message attribute (`id_label`) for exactly this reason; we use it in the mini-project.

2. **Cross-region and cross-subscription is out of scope.** Exactly-once is per-subscription, within the region. Two subscriptions each get their own exactly-once stream; they don't coordinate.

3. **The sink must cooperate.** Pub/Sub can deliver your message exactly once, but if your Dataflow worker reads it, writes a row to BigQuery, and *then* crashes before acking, the message is redelivered and you'd double-write — unless the sink is idempotent. This is why Dataflow's correctness story is not "Pub/Sub exactly-once" alone; it is Pub/Sub exactly-once *plus* Beam's checkpointing *plus* an idempotent BigQuery write (the Storage Write API with stream offsets, or streaming inserts with `insertId` dedup). End-to-end exactly-once is a property of the whole pipeline, not one component.

The challenge this week — kill the workers mid-stream and prove no loss and no duplicates — is precisely a test of (3). You will see that Beam + Dataflow + Pub/Sub exactly-once + an idempotent sink holds, and you'll have the BigQuery row counts to prove it.

There is also a cost: exactly-once adds latency (the durable-ack round trip) and caps a subscription's throughput lower than at-least-once. The honest default for high-volume analytics where addition commutes is *at-least-once with an idempotent sink*; reserve exactly-once for the cases where a duplicate is a correctness bug you cannot absorb (financial postings, inventory decrements).

## 1.6 — The four-way comparison

Now the question every review asks. You have four real options for a message backbone: **Pub/Sub**, **Apache Kafka** (self-hosted or Confluent/MSK/Aiven), **NATS** (with JetStream), and **Amazon SQS**. They are not interchangeable. Here is the map.

### The axes that matter

- **Delivery guarantee.** At-least-once is the baseline for all four. Exactly-once: Pub/Sub (per-subscription, regional), Kafka (transactional producer + idempotent consumer, within Kafka), SQS FIFO (deduplication within a 5-minute window), NATS JetStream (at-least-once; "exactly-once" via message-ID dedup window).
- **Ordering.** Pub/Sub: per ordering-key. Kafka: per partition (strong, the model everyone else copies). SQS: FIFO queues give per-message-group ordering; standard queues give none. NATS JetStream: per-subject ordering within a stream.
- **Throughput ceiling.** Kafka: highest, scales with partitions and brokers, millions of msg/s on a real cluster. Pub/Sub: effectively unbounded for unordered traffic (Google operates the partitioning for you); per-ordering-key throughput is capped (~1 MB/s per key guidance). NATS: very high for core NATS (in-memory, fire-and-forget); JetStream adds persistence and lowers it. SQS: high but with per-queue limits; FIFO queues are capped at 300 msg/s (3000 with batching) unless you request higher.
- **Retention & replay.** Kafka: retention by time or size; replay by seeking an offset — its killer feature. Pub/Sub: 7 days default (31 max), and *seek* lets you replay to a timestamp or a snapshot. NATS JetStream: configurable retention, replay by sequence. SQS: a queue, not a log — once acked (deleted), a message is gone; max retention 14 days and no replay.
- **Operational cost.** Pub/Sub, SQS: fully managed, pay-per-use, zero brokers to run. Kafka: you run brokers (or pay Confluent/MSK to), you manage partitions, rebalances, ZooKeeper/KRaft, and storage — real headcount. NATS: lightweight to run yourself (single Go binary), cheap to operate, but it *is* yours to operate.

### The comparison table

| Property | **Pub/Sub** | **Kafka** | **NATS (JetStream)** | **SQS** |
|---|---|---|---|---|
| Model | Topic fan-out + subscriptions | Partitioned log + consumer groups | Subject-based pub/sub + streams | Queue (standard / FIFO) |
| Delivery default | At-least-once | At-least-once | At-least-once | At-least-once (std) |
| Exactly-once | Per-subscription, regional | Transactional, within Kafka | Dedup window | FIFO dedup (5 min) |
| Ordering | Per ordering-key | Per partition | Per subject | FIFO: per message-group |
| Replay / seek | Yes (timestamp / snapshot) | Yes (offset) — best in class | Yes (sequence) | No |
| Retention | 7d default, 31d max | Unbounded (config) | Config | 14d max, deleted on ack |
| Throughput | Very high; per-key capped | Highest | Very high | High; FIFO capped |
| Ops burden | None (managed) | High (you run it) | Low–medium (you run it) | None (managed) |
| Native fit | GCP | Anywhere; the open standard | Edge / microservices / IoT | AWS |

### When each wins

- **Pub/Sub wins** when you are on GCP, you want zero broker operations, you need clean integration with Dataflow and BigQuery, and your ordering needs are per-entity (per-account, per-device) rather than a single global log. It is the path of least resistance for the GCP data stack and it scales without you thinking about partitions. It loses when you need a *long-lived replayable log* as the system of record (Pub/Sub's 31-day max retention is a ceiling Kafka doesn't have) or when you're multi-cloud and want one broker everywhere.

- **Kafka wins** when the log *is* the architecture: event sourcing, CDC pipelines, stream-table duality, infinite replay, and an ecosystem (Kafka Connect, ksqlDB, Flink) you want to standardize on across clouds. It is the right answer when you have the team to operate it (or the budget for Confluent) and when partition-level ordering and offset-based replay are load-bearing. It loses on operational cost for small teams and on "I just want events into BigQuery without running a cluster."

- **NATS wins** when you want a *lightweight, low-latency* fabric for service-to-service messaging — microservice request/reply, edge and IoT fan-in, ephemeral pub/sub — and you value a single small Go binary you can run anywhere over a managed service. JetStream adds the persistence and at-least-once delivery that core NATS lacks. It loses when you need the managed-service "not my problem" property or deep cloud-native analytics integration.

- **SQS wins** when you are on AWS and you need a *simple, durable work queue* — decouple a producer from a consumer, absorb spikes, retry failures, dead-letter poison messages — and you do **not** need replay or a log. SQS is the most boring, most reliable choice for "queue of tasks." It loses the moment you need to re-read the stream, fan out to multiple independent consumers cheaply (you'd reach for SNS+SQS), or do windowed stream processing (that's Kinesis/Flink territory on AWS).

The honest meta-answer for an architecture review: *pick the managed option native to your cloud unless a specific requirement (infinite replay, multi-cloud portability, sub-millisecond edge latency) forces you off it.* On GCP, that default is Pub/Sub, and this course uses it — while naming Kafka every time as the open alternative, exactly as the C18 charter requires.

## 1.7 — A note on Pub/Sub Lite (and why we don't use it)

Google shipped **Pub/Sub Lite** as a cheaper, capacity-provisioned, Kafka-shaped (partitioned, you-manage-throughput) sibling to Pub/Sub. As of 2026, **Pub/Sub Lite is deprecated and scheduled for shutdown** — Google's guidance is to use Pub/Sub or managed Kafka instead. Do not architect on it. If you see it in an older tutorial, mentally substitute standard Pub/Sub (for managed) or Managed Service for Apache Kafka (for the partitioned-log shape). This is the kind of currency check a senior engineer does reflexively: the service that was the "obvious cost-saver" two years ago is the wrong answer today.

## 1.8 — Retention, replay, and seek

Pub/Sub is not a log the way Kafka is, but it is also not a fire-and-forget queue the way SQS standard is. It sits in between, and the in-between behavior is governed by two retention knobs you must understand before you operate one.

**Subscription message retention.** Each subscription retains *unacknowledged* messages for `message_retention_duration` — default 7 days, max 31 days. If your consumer is down for three days and the subscription's retention is 7 days, the backlog is intact when the consumer returns; the messages are redelivered. This is the property that makes pull subscriptions absorb downstream outages. If your consumer is down longer than the retention, the oldest messages are dropped. Set retention from your worst-case acceptable consumer-downtime:

```hcl
resource "google_pubsub_subscription" "orders_pull" {
  name                       = "orders-pull"
  topic                      = google_pubsub_topic.orders.id
  message_retention_duration = "604800s"  # 7 days — the default, made explicit
  retain_acked_messages      = true        # also keep ACKED messages for replay (see below)
}
```

**Topic message retention.** Independently, a *topic* can retain messages (acked or not) so that a *newly created* subscription can be initialized to read history, and so any subscription can `seek` backward. Topic retention is also up to 31 days. This is the closest Pub/Sub gets to Kafka's replayable log — and the 31-day ceiling is exactly why, in the homework's broker memo, a "1-year replay" requirement flips the decision to Kafka.

**Seek.** The `seek` operation rewinds (or fast-forwards) a subscription's acknowledgement state to a point in time or to a named snapshot:

```bash
# Replay everything from the last hour (requires retain_acked_messages + retention covering it).
gcloud pubsub subscriptions seek orders-pull \
  --time="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)"

# Or snapshot now, deploy a risky consumer change, and seek back to the snapshot if it goes wrong.
gcloud pubsub snapshots create before-deploy --subscription=orders-pull
# ... if the deploy corrupts processing ...
gcloud pubsub subscriptions seek orders-pull --snapshot=before-deploy
```

Two operational uses of seek that earn their keep:

1. **Reprocessing after a bug.** You shipped a pipeline that computed the wrong enrichment for two hours. Fix the code, deploy, and `seek` the subscription back two hours — Pub/Sub redelivers the window and your corrected pipeline reprocesses it. This only works if `retain_acked_messages = true` and the retention window covers the period, so set both *before* you need them. Retrofitting retention does not recover messages already dropped.
2. **Snapshot-before-deploy as a safety net.** Take a snapshot, deploy, and if the new consumer mangles data, seek back to the snapshot and the unacked state is restored. The snapshot is a named bookmark, not a copy of the data, so it's cheap.

The catch with seek and an idempotent sink: replaying redelivers messages your consumer may have already processed. If your sink is idempotent (deduping on `event_id`), replay is safe — already-written rows are recognized and skipped. If it isn't, replay double-writes. This is the same idempotency requirement as exactly-once, surfacing again: **idempotency is the property that makes both redelivery and replay safe**, which is why it's the first habit Lecture 1 §1.1 told you to build.

## 1.9 — Schemas, quotas, and the operational edges

Three more things a senior engineer knows about Pub/Sub before putting it in production.

**Schemas.** Pub/Sub supports topic-level schemas (Avro or Protocol Buffers). When a topic has a schema, publishes that don't conform are rejected at publish time — moving a class of malformed-message problems left, to the producer, instead of right, to your DLQ. This does not replace the DLQ (schema validation can't catch a semantically-wrong-but-structurally-valid message), but it catches the truncated-JSON and wrong-type cases before they ever enter the stream:

```hcl
resource "google_pubsub_schema" "order_schema" {
  name       = "order-schema"
  type       = "AVRO"
  definition = file("${path.module}/order.avsc")
}

resource "google_pubsub_topic" "orders" {
  name = "orders"
  schema_settings {
    schema   = google_pubsub_schema.order_schema.id
    encoding = "JSON"  # or BINARY
  }
}
```

For the mini-project we deliberately do *not* schema-enforce the topic, because the whole point is to exercise the DLQ with malformed events. In a real production stream you would schema-enforce *and* keep the DLQ — defense in depth.

**Quotas and throughput.** Pub/Sub's regional publish quota is high (on the order of GB/s per region by default, raisable) and the service partitions transparently — you do not provision partitions the way you do in Kafka. The one place you *do* have a per-stream cap is **ordering keys**: Google's guidance is to keep a single ordering key under ~1 MB/s of publish throughput, because messages for one key are serialized. If you need both high per-entity throughput and ordering, your entity (the key) must be fine-grained enough that no single key is hot. A constant ordering key (global order) caps you at one key's throughput — fine for a low-volume control stream, fatal for a high-volume event stream.

**Subscription expiry.** By default, a subscription that receives no activity for 31 days is *deleted* by Pub/Sub. For a long-idle subscription (a disaster-recovery consumer, say), set `expiration_policy { ttl = "" }` to disable expiry — otherwise your standby subscription quietly vanishes and you find out during the failover you built it for. This is the kind of default that bites you exactly when you can least afford it.

```hcl
resource "google_pubsub_subscription" "dr_standby" {
  name  = "orders-dr-standby"
  topic = google_pubsub_topic.orders.id
  expiration_policy {
    ttl = ""  # never expire — this standby must survive a long idle period
  }
}
```

## 1.10 — The reflexes to internalize from this lecture

- **A topic is a fan-out point; a subscription holds the consumer state.** N independent readers = N subscriptions. N workers sharing load = N clients on one subscription.
- **At-least-once is the default. Make your consumer idempotent before you do anything else.** Exactly-once is an optimization you enable when a duplicate is a correctness bug, not a convenience.
- **Ordering is per-key and both sides must opt in.** Choose the key cardinality to trade ordering granularity against throughput.
- **A production subscription has a dead-letter topic, and you granted the Pub/Sub service account publisher on it.** A `dead_letter_policy` without the IAM grant is a no-op.
- **Exactly-once is per-subscription, regional, and does not dedupe publishes or fix a non-idempotent sink.** End-to-end exactly-once is a property of the whole pipeline.
- **The broker choice is a managed-vs-operated and replay-vs-no-replay decision before it is a feature checklist.** Pub/Sub for managed-on-GCP; Kafka for the log-as-architecture; NATS for the light fabric; SQS for the simple AWS work queue.

## 1.11 — What we did not cover (Lecture 2 picks it up)

This lecture is about getting messages reliably *delivered*. It says nothing about what happens once a stream processor reads them and has to decide *which messages belong together in a result* — that is the windowing-and-watermark problem, and it is where pipelines ship wrong numbers. Lecture 2 is that lecture. Read it before you write a single line of the mini-project's Beam code.

---

## Lecture 1 — checklist before moving on

- [ ] I can name the four Pub/Sub nouns (topic, subscription, message, ack) and explain why a topic is not a queue.
- [ ] I can choose pull vs. push for a stated consumer and justify it on flow-control and network grounds.
- [ ] I can configure an ordering key in Terraform and on the publisher, and I know both sides must opt in.
- [ ] I can wire a dead-letter topic *including* the two IAM grants the Pub/Sub service account needs.
- [ ] I can state what exactly-once delivery guarantees and the three places it doesn't help.
- [ ] I can place Pub/Sub, Kafka, NATS, and SQS on the map and name the workload where each wins.

If any box is unchecked, return to that section. Exercise 1 assumes you can build the topic + DLQ in Terraform yourself.

---

**References cited in this lecture**

- Google Cloud — "What is Pub/Sub?": <https://cloud.google.com/pubsub/docs/overview>
- Google Cloud — "Pull subscriptions" / StreamingPull: <https://cloud.google.com/pubsub/docs/pull>
- Google Cloud — "Push subscriptions": <https://cloud.google.com/pubsub/docs/push>
- Google Cloud — "Message ordering": <https://cloud.google.com/pubsub/docs/ordering>
- Google Cloud — "Handle message failures (dead-letter topics)": <https://cloud.google.com/pubsub/docs/handling-failures>
- Google Cloud — "Exactly-once delivery": <https://cloud.google.com/pubsub/docs/exactly-once-delivery>
- Google Cloud — "Replay and discard messages (seek)": <https://cloud.google.com/pubsub/docs/replay-overview>
- Google Cloud — "Pub/Sub Lite deprecation": <https://cloud.google.com/pubsub/lite/docs>
- Apache Kafka — Documentation: <https://kafka.apache.org/documentation/>
- NATS — JetStream concepts: <https://docs.nats.io/nats-concepts/jetstream>
- AWS — Amazon SQS FIFO queues: <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues.html>
