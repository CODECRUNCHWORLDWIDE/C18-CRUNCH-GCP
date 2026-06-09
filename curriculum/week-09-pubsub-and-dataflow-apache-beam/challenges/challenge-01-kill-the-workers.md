# Challenge 1 — Kill the workers, prove exactly-once

> **Estimated time:** 2 hours (most of it watching a pipeline run and validating it). **Cost:** under \$1 with the smallest worker + Streaming Engine + a prompt teardown. Arm your budget alert first.

You will build the canonical GCP streaming stack end to end, run it under continuous load for 30 minutes, kill the Dataflow workers in the middle, and then *prove* — from BigQuery row counts, not from a green dashboard — that no event was lost and no event was double-counted. This is the test the war story in Lecture 2 failed and the test the capstone's acceptance criteria demand. It is worth far more than its time-cost suggests: it is the exact shape of "is this pipeline actually correct under failure?" that a staff engineer will ask you in a review.

## The system

```
generator.py  ──publish (event_id, ordering_key)──▶  Pub/Sub topic: events
                                                          │
                                                          ├─▶ subscription: events-dataflow (pull, exactly-once, id_label)
                                                          │        │
                                                          │        ▼
                                                          │   Dataflow streaming Beam pipeline
                                                          │     - parse JSON; route malformed → DLQ
                                                          │     - window + count by event_type
                                                          │     - write rows to BigQuery (Storage Write API)
                                                          │        │
                                                          │        ▼
                                                          │   BigQuery table: events.parsed (partitioned by event_time, clustered by event_type)
                                                          │
                                                          └─▶ DLQ topic: events-dlq  (malformed events)
```

## Requirements

### Generator

Write `generator.py` that publishes events to the `events` topic at a steady rate (e.g., 20–50 msg/s) for a configurable duration. Each event:

- Is JSON: `{"event_id": "<uuid>", "event_type": "<one of ~6>", "tenant": "<one of ~10>", "amount": <float>, "event_time": "<RFC3339>"}`.
- Carries a **deterministic `event_id`** as both a JSON field and a Pub/Sub message **attribute** (this is the `id_label` Dataflow dedupes on — Lecture 2 §2.8).
- Uses `tenant` as the **ordering key**.
- **Injects ~2% deliberately-malformed events** (truncated JSON, missing required field, wrong type) so the DLQ has something to catch.
- Writes a local **manifest** `published.jsonl` of every well-formed `event_id` it published, so `validate.py` can compare against BigQuery. (Malformed ones go in a separate `published_bad.jsonl`.)

### Processing tier (your Beam pipeline)

Write `pipeline.py` (Python Apache Beam) that:

- Reads from `events-dataflow` with `timestamp_attribute` (event time) and `id_label="event_id"` (dedup).
- Parses each message as JSON inside a `DoFn`. On a parse/validation failure, **tags the element to a dead-letter `PCollection`** (use `beam.pvalue.TaggedOutput`) which is written to the `events-dlq` topic — NOT dropped, NOT crashing the bundle.
- Windows the good events into fixed 1-minute windows on **event time**, with a sane `allowed_lateness` (≥ 60s) and `AccumulationMode.ACCUMULATING`.
- Writes **every well-formed event** as a row to `events.parsed` via the BigQuery **Storage Write API** (`WriteToBigQuery(..., method='STORAGE_WRITE_API')`). Each row includes the `event_id` so `validate.py` can count distinct ids.

> The windowed counts are a secondary output you may also write to a `events.counts` table; the *primary* correctness artifact is that every published-good `event_id` lands in `events.parsed` exactly once.

### Infrastructure (Terraform, via your Week 04 modules)

Provision with Terraform, reusing your Week 04 module patterns where possible:

- The `events` topic, the `events-dlq` topic, the `events-dataflow` subscription (exactly-once, ordering enabled), and a `events-dlq-pull` subscription.
- The two IAM grants the Pub/Sub service account needs for dead-lettering (Lecture 1 §1.4) — though here malformed events are routed by *your pipeline* to the DLQ topic, so the pipeline's worker SA needs `roles/pubsub.publisher` on `events-dlq`.
- The BigQuery dataset and the `events.parsed` table, **partitioned by `event_time` (DAY) and clustered by `event_type`**.
- A Dataflow worker service account with the minimum roles (`roles/dataflow.worker`, `roles/pubsub.subscriber` on the sub, `roles/pubsub.publisher` on the DLQ, `roles/bigquery.dataEditor` on the dataset).

### The chaos: kill the workers

Once the pipeline has been running and ingesting for ~10 minutes:

```bash
# Find the worker VMs (classic) or, on Streaming Engine, the worker instances:
gcloud compute instances list --filter="name~'^dataflow-'" --format="value(name,zone)"

# Kill them. Dataflow will detect the loss and replace them.
gcloud compute instances delete <worker-name> --zone=<zone> --quiet
```

Keep the generator running through the kill. Dataflow on Streaming Engine keeps the windowing state in managed storage, replaces the workers, and resumes. Your job is to prove the replacement was lossless and duplicate-free.

### Validation: prove it

Write `validate.py` that, after you `drain` the job and the backlog is empty:

1. Counts distinct `event_id` in `events.parsed`:
   ```sql
   SELECT COUNT(DISTINCT event_id) AS distinct_ids, COUNT(*) AS rows
   FROM `PROJECT.events.parsed`
   ```
2. Compares `distinct_ids` against the count of well-formed ids in `published.jsonl`. They must be **equal** (no loss).
3. Compares `rows` against `distinct_ids`. They must be **equal** (no duplicates — `rows > distinct_ids` means something double-wrote).
4. Confirms the malformed events from `published_bad.jsonl` are present on `events-dlq` (pull and count).

## Acceptance criteria

- [ ] `terraform apply` stands up all resources; the Dataflow job reaches the *Running* state.
- [ ] The generator publishes for ≥ 30 minutes at a steady rate with ~2% malformed events.
- [ ] You killed at least one Dataflow worker mid-stream and the job recovered to *Running* without manual intervention.
- [ ] After draining: `COUNT(DISTINCT event_id)` in `events.parsed` **equals** the well-formed published count — **zero data loss**.
- [ ] `COUNT(*)` **equals** `COUNT(DISTINCT event_id)` in `events.parsed` — **zero duplicates** (exactly-once held end-to-end).
- [ ] The malformed events are on `events-dlq`, and the count matches `published_bad.jsonl` — **the DLQ caught exactly the bad ones, no good ones**.
- [ ] You can explain, in a 200-word `findings.md`, *why* exactly-once held: name the three cooperating pieces (Pub/Sub exactly-once subscription + Dataflow checkpointing/`id_label` dedup + idempotent Storage Write API sink).
- [ ] **Teardown gate:** `terraform destroy` removes everything, and a follow-up `gcloud dataflow jobs list --status=active` shows no running job.

## Hints (not a solution)

- **Use `drain`, not `cancel`, before validating.** `drain` flushes in-flight windows so the last minute of data lands in BigQuery; `cancel` discards it and your counts will be short by the in-flight window. Only `cancel` after you've confirmed counts match.
- **The dead-letter routing is `TaggedOutput`, not a `dead_letter_policy`.** Because *your pipeline* decides what's malformed (it can't parse the JSON), you tag it and `WriteToPubSub` it to `events-dlq` yourself. A subscription `dead_letter_policy` only fires on repeated *nacks*, which won't happen here because your `DoFn` always "succeeds" (it routes rather than throws). Know the difference: subscription-level DLQ is for poison messages your consumer keeps nacking; pipeline-level tagged-output DLQ is for messages your consumer can read but can't *process*.
- **`id_label="event_id"` is what makes the kill survivable without duplicates.** When a worker dies after reading but before acking, the message is redelivered; Dataflow recognizes the `event_id` and does not reprocess it.
- **Watch the Dataflow UI's "Data watermark" during the kill.** It should keep advancing after the workers are replaced. A stuck watermark after a kill means state recovery failed — investigate before validating.
- **Run the generator from Cloud Shell or a small VM**, not your laptop on hotel wifi — a generator that stalls because *your* connection dropped will make the pipeline look idle and confuse the validation.

## Going further (no extra grade)

- Add the **DLQ-accumulation alert** (Cloud Monitoring policy that fires when `events-dlq` has > N undelivered messages). The mini-project requires this; build it here as a warm-up.
- Add a **reconciliation query**: a scheduled job that compares the streaming `events.counts` totals to a recomputation from `events.parsed`. If they ever diverge by > 1%, you have a windowing bug — this is the check that would have caught the war story.
- **Replay from the DLQ.** Fix the generator's malformed-event bug, then re-publish the dead-lettered events (after correcting them) and confirm they land in `events.parsed`. This is the operational loop a real on-call runs.

## Submission

Commit to your Week 9 repository at `challenges/challenge-01-streaming/` containing `generator.py`, `pipeline.py`, the Terraform, `validate.py`, and `findings.md`. The instructor reviews by reading `findings.md` and re-running `validate.py` against a fresh run. The most common review-fail is "claimed exactly-once but `rows > distinct_ids`" — run `validate.py` yourself before submitting, and if it fails, the bug is almost always a non-idempotent sink (streaming inserts without `insertId`, or a `WriteToBigQuery` without `STORAGE_WRITE_API`).
