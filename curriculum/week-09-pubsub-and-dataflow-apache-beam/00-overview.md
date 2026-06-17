# Week 9 — Pub/Sub and Dataflow (Apache Beam)

Welcome to **Phase 3 — Data & AI**. Phase 1 locked down a landing zone; Phase 2 taught you to put compute on it. Week 9 is where the platform starts to *move bytes in motion* — a streaming substrate that ingests events as fast as the world produces them, processes them while they are still warm, and lands clean, queryable tables on the other side.

This is the week most engineers get wrong, and they get it wrong *silently*. A batch pipeline that crashes pages you. A streaming pipeline that ships a number that is 4% low because a window closed before the late data arrived will run for six months before a finance analyst notices the quarterly total doesn't reconcile. Nobody gets paged. The dashboard is green. The number is wrong. That failure mode — **wrong, not down** — is the spine of this week.

You will build the canonical GCP streaming stack: a synthetic event generator publishing to **Pub/Sub**, a **Dataflow** (managed Apache Beam) streaming pipeline that windows and enriches the stream, and a **BigQuery** sink with a **dead-letter topic** for the malformed events that *always* show up in real traffic. You will run it, kill the workers mid-stream, and prove exactly-once delivery held. By Friday you can defend Pub/Sub against Kafka, NATS, and SQS with real numbers, and you can read a watermark diagram and tell whether a pipeline is about to ship a wrong number.

This week is the **direct precursor to the capstone**. The capstone's stream and process tiers are exactly what you build here, scaled up. Treat the mini-project as the first commit of your capstone, not a throwaway.

## Learning objectives

By the end of this week, you will be able to:

- **Create** a Pub/Sub topic with an ordering key, a push and a pull subscription, and a dead-letter topic, entirely in Terraform, and prove malformed messages land in the DLQ.
- **Decide** push vs. pull subscription for a stated consumer pattern and defend the choice on flow-control, latency, and operational grounds.
- **Explain** exactly-once delivery in Pub/Sub — what it guarantees, what it costs, and the three places engineers think they have it but don't.
- **Write** an Apache Beam pipeline in Python with fixed windows, sliding windows, and session windows, and run it on the Direct runner locally with no cloud spend.
- **Reason** about watermarks, allowed lateness, and triggers well enough to predict whether a given configuration drops, double-counts, or correctly accounts for late data.
- **Compare** Pub/Sub against Kafka, NATS, and SQS on ordering, throughput, delivery guarantees, retention, and operational cost — and name the workload where each wins.
- **Deploy** a generator → Pub/Sub → Dataflow → BigQuery streaming pipeline via the Week 04 Terraform modules, with a DLQ and an alert that fires when the DLQ accumulates.
- **Validate** end-to-end correctness under failure: kill Dataflow workers mid-stream and prove no data loss and no duplicates landed in BigQuery.
- **Tear down** all of it on demand, with a teardown gate you do not skip.

## Prerequisites

This week assumes you have completed **Weeks 01–08** of C18, or carry equivalent production GCP experience. Specifically:

- **Week 04 Terraform module discipline.** You can write a module with `for_each`, consume it from `envs/dev`, and run a plan/apply cycle against a real project with remote state in GCS. This week's mini-project deploys *through* your Week 04 modules.
- **Week 01 billing discipline.** Your budget alert is armed. Dataflow on the streaming engine bills per worker-hour; an un-torn-down pipeline is the single most common surprise charge in this course.
- **Python 3.11+ fluency.** You can read a `with`-block, a generator, a decorator, and a `typing` annotation without slowing down. Apache Beam's Python SDK leans on all four.
- **SQL literacy.** You can write a `GROUP BY ... HAVING` and read a `CREATE TABLE` with a partition spec. BigQuery is the sink.
- **A GCP project with billing enabled** and the APIs you'll enable in the lab: `pubsub.googleapis.com`, `dataflow.googleapis.com`, `bigquery.googleapis.com`, `monitoring.googleapis.com`.

You do **not** need prior Kafka or Beam experience. We start at the Pub/Sub data model and build up. If you've used Kafka, you'll find the comparison lecture sharpens what you already know; a couple of mental models (offsets, consumer groups) need adjusting and we flag them.

## Topics covered

- The Pub/Sub data model: topics, subscriptions, messages, acks, and the at-least-once default.
- **Pull** subscriptions (StreamingPull, the client-library default) vs. **push** subscriptions (HTTP POST to an endpoint) — flow control, latency, scaling, and when each is correct.
- **Ordering keys** — what they guarantee (per-key FIFO within a region), what they cost (throughput per key), and the publish-side and subscribe-side requirements.
- **Dead-letter topics** — the `max_delivery_attempts` mechanism, the IAM grants Pub/Sub itself needs, and why a DLQ is not optional in production.
- **Exactly-once delivery** in Pub/Sub: the `enable_exactly_once_delivery` flag, the regional-endpoint requirement, the ack-deadline-extension semantics, and the three caveats (publish-side dedup, cross-region, and sink idempotency).
- **Dataflow** as managed Apache Beam: the runner model, Streaming Engine, autoscaling, and Dataflow Prime.
- **Apache Beam** core model: `PCollection`, `PTransform`, `ParDo`, `DoFn`, the Python SDK, and the Direct runner for local development.
- **Windowing:** fixed (tumbling), sliding (hopping), session, and global windows — and which aggregation each is for.
- **Watermarks:** the event-time vs. processing-time distinction, how Pub/Sub-sourced watermarks advance, and the heuristic vs. perfect watermark.
- **Triggers and allowed lateness:** event-time triggers, processing-time triggers, `AfterWatermark`, early/late firings, accumulation mode, and the `allowed_lateness` knob that decides whether late data is counted or dropped.
- **The wrong-numbers failure mode:** how a too-tight watermark or a too-short allowed-lateness silently undercounts, and how to detect it.
- **Pub/Sub vs. Kafka vs. NATS vs. SQS:** ordering, throughput, delivery semantics, retention, replay, and total cost of ownership.
- Writing to BigQuery from Beam: `WriteToBigQuery`, streaming inserts vs. Storage Write API, and how the sink participates in exactly-once.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract. The mini-project is load-bearing; protect its hours.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Pub/Sub data model; push vs. pull; ordering; DLQ            |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Exactly-once; Pub/Sub vs. Kafka/NATS/SQS                    |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Wednesday | Beam model; windowing; Direct runner                        |    1h    |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Thursday  | Watermarks, late data, triggers; the wrong-numbers lecture  |    1h    |    1h     |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6h      |
| Friday    | Dataflow deploy; BigQuery sink; DLQ alert                   |    0h    |    0.5h   |     0h     |    0.5h   |   1h     |     3h       |    0.5h    |     5.5h    |
| Saturday  | Mini-project deep work; kill-the-workers validation         |    0h    |    0h     |     0h     |    0h     |   0h     |     3.5h     |    0h      |     3.5h    |
| Sunday    | Quiz, review, teardown gate                                 |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0.5h    |     2.5h    |
| **Total** |                                                             | **6h**   | **6.5h**  | **2h**     | **3.5h**  | **5h**   | **12.5h**    | **3h**     | **35.5h**   |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | Curated GCP docs, Beam docs, and the comparison sources, current to 2026 |
| [lecture-notes/01-pubsub-vs-kafka-nats-sqs.md](./02-lecture-notes/01-pubsub-vs-kafka-nats-sqs.md) | The Pub/Sub data model end-to-end, then the four-way comparison: when each broker wins |
| [lecture-notes/02-watermarks-late-data-and-triggers.md](./02-lecture-notes/02-watermarks-late-data-and-triggers.md) | Windows, watermarks, triggers, and the six-months-of-wrong-numbers war story |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-ordering-key-and-dlq.md](./03-exercises/exercise-01-ordering-key-and-dlq.md) | Terraform a topic with an ordering key + DLQ; prove malformed messages land in the DLQ |
| [exercises/exercise-02-beam-windowing.py](./03-exercises/exercise-02-beam-windowing.py) | A runnable Beam pipeline with fixed and sliding windows on the Direct runner |
| [exercises/exercise-03-push-vs-pull-decision.py](./03-exercises/exercise-03-push-vs-pull-decision.py) | A runnable decision tool + a working push and pull consumer for two stated patterns |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-kill-the-workers.md](./04-challenges/challenge-01-kill-the-workers.md) | Build the full streaming pipeline, kill workers mid-stream, prove exactly-once and no data loss |
| [quiz.md](./05-quiz.md) | 12 multiple-choice questions with an answer key |
| [homework.md](./06-homework.md) | Six practice problems with a rubric |
| [mini-project/README.md](./07-mini-project/00-overview.md) | Full spec for the deployable streaming-ingest mini-project |

## The teardown promise

C18 has one recurring marker that ends every week:

```
$ terraform destroy -auto-approve
...
Destroy complete! Resources: 17 destroyed.
```

Dataflow streaming jobs do not stop when you close your laptop. They run, they autoscale, and they bill per worker-hour until you `drain` or `cancel` them. **Every mini-project and challenge this week ends with an explicit teardown gate.** If you finish the work and skip the teardown, you failed the week — and you will find out at the end of the month. The teardown gate is the deliverable, not an afterthought.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **"Streaming 101" and "Streaming 102"** essays by Tyler Akidau (the Beam model's original author). They are the source material for everything in Lecture 2: <https://www.oreilly.com/radar/the-world-beyond-batch-streaming-101/>.
- Turn on **Dataflow Prime** for the mini-project and read the autoscaling/right-fitting behavior in the job graph: <https://cloud.google.com/dataflow/docs/guides/enable-dataflow-prime>.
- Swap the BigQuery sink from streaming inserts to the **Storage Write API** and compare cost and exactly-once behavior: <https://cloud.google.com/bigquery/docs/write-api>.
- Opt in to **multi-region Dataflow** (the paid-but-cheap exercise — budget a few dollars and an armed alert) and observe how a regional outage would be absorbed.
- Write a one-page note for your future self: "the three watermark mistakes I will never make again," in your own words.

## Up next

Continue to **Week 10 — BigQuery deep** once you have torn down this week's pipeline and pushed the mini-project. Week 10 takes the partitioned, clustered table this pipeline writes and teaches you to query it for under a cent. The two weeks are a pair: Week 9 lands the data correctly; Week 10 reads it cheaply.

---

*Cohort owner for this rotation is named in the track README. If you find errors in this material, open an issue or send a PR. Future learners will thank you.*
