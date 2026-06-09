# Week 9 — Quiz

Twelve multiple-choice questions. Take it with your lecture notes closed. Aim for 10/12 before moving to Week 10. Answer key at the bottom — don't peek.

---

**Q1.** You create one Pub/Sub topic and want three independent services to each receive *every* message published to it, processing at their own pace. What's the correct topology?

- A) One topic, one subscription, three clients on it — Pub/Sub load-balances.
- B) One topic, three subscriptions — one per service. Each subscription gets its own copy of every message.
- C) Three topics, three subscriptions, and a fan-out service that re-publishes.
- D) One topic, one push subscription with three endpoints.

---

**Q2.** Pub/Sub's default delivery guarantee, with no flags set, is:

- A) Exactly-once, always.
- B) At-most-once (messages may be dropped on failure).
- C) At-least-once (messages may be delivered more than once; make consumers idempotent).
- D) Ordered, at-least-once, globally.

---

**Q3.** A team configures a subscription with `dead_letter_policy { max_delivery_attempts = 5 }` but messages keep getting redelivered a 6th, 7th, 8th time and never appear on the DLQ topic. The most likely cause is:

- A) `max_delivery_attempts` must be ≥ 10.
- B) The Pub/Sub service account lacks `roles/pubsub.publisher` on the DLQ topic (and/or `roles/pubsub.subscriber` on the source subscription), so dead-lettering silently fails.
- C) Dead-letter topics only work with push subscriptions.
- D) The consumer is acking the messages, so they never reach the DLQ.

---

**Q4.** You enable `enable_exactly_once_delivery = true` on a subscription. Which statement is **true**?

- A) Publish-side duplicates (a publisher retrying a publish it didn't get an ACK for) are now automatically deduplicated.
- B) Once a message is successfully acknowledged on this subscription, it will not be redelivered — but publish-side dedup and sink idempotency are still your responsibility.
- C) It guarantees exactly-once across all subscriptions on the topic.
- D) It is supported on push subscriptions with a global endpoint.

---

**Q5.** You publish three messages A, B, C with the same `ordering_key="acct-7"` to a topic in one region, and the subscription has `enable_message_ordering = true`. What does Pub/Sub guarantee?

- A) A, B, C are delivered in that order to a subscriber.
- B) A, B, C are delivered in some order, but never the same one twice.
- C) Nothing — ordering keys are advisory.
- D) A, B, C are delivered in order, *and* messages with other ordering keys are also serialized behind them.

---

**Q6.** For a Cloud Run service that scales to zero and processes events only when they arrive, the correct subscription type is:

- A) Pull, because Cloud Run can hold a StreamingPull stream.
- B) Push, because there's no always-on process to pull; Pub/Sub's HTTP POST wakes the service and Pub/Sub controls the rate via slow-start.
- C) A BigQuery export subscription.
- D) Either works identically; the choice is cosmetic.

---

**Q7.** A streaming pipeline windows purchase events into 1-minute fixed windows and sums revenue. It uses event-time windows but leaves `allowed_lateness` at its default. Mobile clients sometimes deliver events 2–4 minutes late. What happens?

- A) Late events are buffered and counted when they arrive; the totals are correct.
- B) The pipeline errors and pages on-call when a late event arrives.
- C) Late events arrive after their window's single watermark firing and are **silently dropped**; the per-minute totals are quietly undercounted.
- D) Late events are routed to the dead-letter topic automatically.

---

**Q8.** A window fires more than once (an on-time firing and a late firing). The pipeline uses `AccumulationMode.ACCUMULATING`. For the totals in BigQuery to be correct, the sink must:

- A) Append every firing as a new row.
- B) Upsert / replace by window key — each firing contains the *complete* total so far, so the late firing supersedes the on-time one.
- C) Ignore all firings after the first.
- D) Sum the firings, because each contains only the delta.

---

**Q9.** Which statement about watermarks is **correct**?

- A) A watermark is a guarantee that no event with an earlier event time will ever arrive.
- B) A heuristic watermark is an *estimate* of completeness; it can advance past an event time for which a straggler later arrives, making that straggler "late."
- C) Watermarks are based on processing time, not event time.
- D) A stuck watermark means the pipeline is healthy and caught up.

---

**Q10.** You're choosing a message backbone and the system of record must support **infinite replay** — re-reading the entire stream from any offset, years back. Which broker is the natural fit?

- A) Pub/Sub — its 31-day max retention covers it.
- B) SQS — a queue with replay built in.
- C) Apache Kafka — offset-based replay over an unbounded, time/size-retained log is its defining feature.
- D) NATS core (non-JetStream) — it persists everything by default.

---

**Q11.** In a Dataflow Beam pipeline reading from Pub/Sub, what does setting `id_label="event_id"` on the read accomplish?

- A) It sets the BigQuery primary key.
- B) It tells Dataflow to deduplicate messages by that attribute, so a redelivered message (e.g., after a worker is killed and a message is re-read) is recognized and not reprocessed — a key piece of end-to-end exactly-once.
- C) It enables message ordering.
- D) It routes malformed messages to the DLQ.

---

**Q12.** A `DoFn` in your pipeline can *read* a message but cannot *process* it (the JSON is malformed). The correct way to send it to a dead-letter topic is:

- A) Configure the subscription's `dead_letter_policy` — it will catch the malformed message.
- B) `raise` an exception so the bundle fails and Pub/Sub nacks the message.
- C) Use `beam.pvalue.TaggedOutput` to tag it to a dead-letter `PCollection` and `WriteToPubSub` it to the DLQ topic — the subscription's `dead_letter_policy` only fires on repeated *nacks*, which won't happen because the `DoFn` "succeeds" by routing.
- D) Drop it silently; malformed events don't matter.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — A topic is a fan-out point; a subscription holds per-consumer state. N independent readers = N subscriptions, each receiving its own copy of every message. Option A (one subscription, three clients) *load-balances* the messages across the clients — each message goes to only one of them — which is the opposite of what you want here.

2. **C** — At-least-once is the default for Pub/Sub (and SQS standard, and most Kafka configs). It can deliver a message more than once on redelivery; your consumer must be idempotent. Exactly-once (A) is opt-in; at-most-once (B) drops on failure and is not the default; global ordering (D) is not provided.

3. **B** — A `dead_letter_policy` without the IAM grants is a silent no-op. Pub/Sub uses *its own* service account to publish the poison message to the DLQ and to ack it on the source subscription. Missing `roles/pubsub.publisher` on the DLQ topic means it keeps redelivering past `max_delivery_attempts`. `max_delivery_attempts` minimum is 5, not 10 (A). Dead-letter works with pull too (C).

4. **B** — Exactly-once guarantees that an *acknowledged* message on *that subscription* won't be redelivered. It does **not** dedupe publish-side duplicates (A) — that's your job (e.g., a deterministic `event_id`); it is per-subscription, not cross-subscription (C); and it requires a *regional* pull endpoint, not push/global (D).

5. **A** — With ordering enabled on both publisher and subscription, same-key messages in the same region are delivered in publish order. They are still at-least-once (may be redelivered), so B's "never twice" is wrong. Ordering keys are a real guarantee, not advisory (C). Different ordering keys are *not* serialized behind each other (D) — that's the whole point of per-key ordering.

6. **B** — Push fits scale-to-zero serverless: there's no process to hold a pull stream, so Pub/Sub's POST wakes the service, and Pub/Sub controls the rate via slow-start. Pull (A) needs an always-on puller. A BigQuery export subscription (C) skips your code entirely, which isn't what's described.

7. **C** — Default trigger fires once on the watermark; with default (zero) `allowed_lateness`, anything arriving after that firing is silently dropped. This is the Lecture 2 war story exactly. It does not error (B) or auto-DLQ (D), and it does not buffer late data without `allowed_lateness` (A).

8. **B** — `ACCUMULATING` means each firing contains the *complete* result so far, so the sink must upsert/replace by window key — otherwise appending every firing double-counts. Option D describes `DISCARDING` (deltas), which would need summing. Pairing the wrong accumulation mode with the wrong sink semantics is its own silent-wrong-numbers bug.

9. **B** — A heuristic watermark is an *estimate* of completeness and can advance past data that hasn't arrived yet; that straggler becomes late data. A is the *perfect* watermark (rarely achievable). Watermarks track *event* time as a function of processing time (C is backwards). A stuck watermark is a problem, not health (D).

10. **C** — Kafka's offset-based replay over an unbounded log is its defining feature and the right fit for "system of record with infinite replay." Pub/Sub caps at 31 days (A). SQS deletes on ack and has no replay (B). Core NATS (non-JetStream) does *not* persist (D).

11. **B** — `id_label` tells Dataflow to dedupe by that message attribute, so a redelivered message (after a worker is killed mid-stream) is recognized and not reprocessed. This is exactly what makes the kill-the-workers challenge produce zero duplicates. It does not set a BQ key (A), enable ordering (C), or route to DLQ (D).

12. **C** — Use `TaggedOutput` to route the unprocessable message to a dead-letter `PCollection` and write it to the DLQ topic yourself. The subscription `dead_letter_policy` (A) only fires on repeated *nacks*, which won't happen because the `DoFn` succeeds by routing rather than throwing. Raising (B) crashes the bundle and relies on nack-based dead-lettering, which is the wrong tool for "I read it but can't process it." Dropping (D) is the silent-failure anti-pattern.

</details>

---

If you scored under 9, re-read the lectures for the questions you missed — especially Q7/Q8/Q9 (the watermark/lateness/accumulation triad) and Q3/Q4 (DLQ IAM and exactly-once caveats), which are the ones engineers get wrong in production. If you scored 11 or 12, you're ready for the [homework](./homework.md).
