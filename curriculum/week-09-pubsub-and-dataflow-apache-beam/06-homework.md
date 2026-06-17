# Week 9 Homework

Six practice problems that revisit the week's topics. The full set should take about **5 hours**. Work in your Week 9 Git repository so each problem produces at least one commit you can point to later.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

---

## Problem 1 — The four-way broker decision memo

**Problem statement.** Write a one-page decision memo (`notes/broker-decision.md`) for a fictional but specific scenario: *"We're a GCP-native commerce company. We need an event backbone for purchase events: ~5,000 events/sec peak, per-account ordering, 30-day replay for reprocessing, and we have a 4-person platform team."* Argue for one of Pub/Sub, Kafka (self-managed or Confluent), NATS JetStream, or SQS. Your memo must:

1. Name the chosen broker and the single most decisive factor.
2. Address each of the five axes from Lecture 1 (delivery guarantee, ordering, throughput, retention/replay, ops cost) for the chosen broker.
3. Name the strongest argument *against* your choice and rebut it.
4. State the one requirement that, if it changed, would flip your decision.

**Acceptance criteria.**

- `notes/broker-decision.md` exists, is 350–550 words, and cites at least three primary-source URLs (the broker docs, not blogs).
- All five axes are addressed for the chosen broker.
- The "argument against" and the "what would flip it" sections are present and concrete.
- The memo names a specific decisive factor, not "it depends."

**Hint.** The 30-day replay requirement is the interesting tension: Pub/Sub's max retention is 31 days (just barely fits), Kafka does it natively but adds ops cost for a 4-person team. The "what would flip it" is likely "if replay needed to be 1 year" → Kafka.

**Estimated time.** 45 minutes.

---

## Problem 2 — Prove the IAM grant is load-bearing

**Problem statement.** Using your Exercise 1 Terraform as a base, write a short experiment (`notes/dlq-iam-experiment.md`) that documents, with command output, what happens when the Pub/Sub service account *lacks* `roles/pubsub.publisher` on the dead-letter topic. Capture: (a) `delivery_attempt` climbing past `max_delivery_attempts`, (b) the DLQ remaining empty, and (c) the behavior returning to normal once the grant is restored.

**Acceptance criteria.**

- `notes/dlq-iam-experiment.md` shows the `delivery_attempt` exceeding `max_delivery_attempts` (e.g., 6, 7, 8) with the grant removed.
- It shows an empty DLQ pull during that window.
- It shows dead-lettering resuming after restoring the grant.
- A 100-word explanation of *why* Pub/Sub uses its own service account (rather than the consumer's) to dead-letter.
- Teardown run at the end (note it in the file).

**Hint.** Comment out the `google_pubsub_topic_iam_member` for the DLQ publisher, `terraform apply`, publish a malformed message, run the nack loop, then `gcloud pubsub subscriptions pull <dlq-sub> --auto-ack`.

**Estimated time.** 45 minutes.

---

## Problem 3 — Reproduce the wrong-numbers bug, then fix it

**Problem statement.** Extend the Exercise 2 Beam pipeline into a standalone script (`homework/late_data.py`) that demonstrates the war story numerically. Generate 1,000 synthetic revenue events spread over 10 one-minute windows, with a configurable fraction (default 5%) injected as "late" (event time in an early window, arriving after the watermark would have passed). Run the windowed sum twice — once with `allowed_lateness=0`, once with `allowed_lateness=600` — and print the total revenue for each. Compute and print the **percentage undercount** of the dropping run.

**Acceptance criteria.**

- `homework/late_data.py` runs on the Direct runner with no cloud spend.
- It prints both totals and the percentage undercount, which should be approximately equal to the injected late fraction (~5%).
- A `notes/late-data.md` with the output and a 150-word explanation of which Beam configuration knob fixed it and why.
- Bonus: also print the count of events that were dropped due to lateness in the first run.

**Hint.** Reuse the `AssignEventTime` `DoFn` and the windowing from Exercise 2. The undercount = `(counting_total - dropping_total) / counting_total * 100`.

**Estimated time.** 60 minutes.

---

## Problem 4 — The push-vs-pull decision matrix

**Problem statement.** Take the `decide()` function from Exercise 3 and extend it into a documented decision matrix (`notes/push-pull-matrix.md`). Define **six** distinct consumer patterns from your own experience or imagination (not the four from the exercise), run them through `decide()`, and record the recommendation and reasons in a Markdown table. Then write a paragraph on the *one* pattern where you disagree with the tool's output (or would want more nuance), and what additional input the tool would need to get it right.

**Acceptance criteria.**

- `notes/push-pull-matrix.md` has a table with six patterns, each with the tool's recommendation and the decisive reason.
- At least two patterns recommend PUSH and at least two recommend PULL.
- A paragraph identifying a pattern where the simple rules engine is insufficient and naming the missing input.
- The six patterns are distinct from the four sample patterns in the exercise.

**Hint.** A good "tool is insufficient" case: a consumer that is always-on *but* must scale horizontally to zero overnight — the binary `always_on_process` flag can't capture "on during the day, off at night." The missing input is a schedule/elasticity dimension.

**Estimated time.** 40 minutes.

---

## Problem 5 — Read a real Dataflow template's error routing

**Problem statement.** Open the `GoogleCloudPlatform/DataflowTemplates` repo and find the streaming Pub/Sub-to-BigQuery template's dead-letter handling. Read how it routes failed BigQuery inserts and malformed messages. Write a 250-word summary (`notes/template-dlq.md`) covering:

1. The template's path within the repo.
2. How it distinguishes a *parse* failure from a *BigQuery insert* failure (they go to different dead-letter destinations).
3. The data shape it writes to the dead-letter table/topic (what metadata does it attach to a failed record?).
4. One thing the template does that your mini-project's DLQ routing does *not* — and whether you should adopt it.

**Acceptance criteria.**

- `notes/template-dlq.md` exists, is 220–280 words, and cites the specific file path(s) in the repo.
- It correctly distinguishes the parse-failure path from the insert-failure path.
- It names the dead-letter record's metadata fields (e.g., the original payload, the error message, a timestamp).
- It identifies one production-grade technique you could adopt.

**Hint.** Look for `PubSubToBigQuery` (or `PubsubToBigQuery`) under `v1/` or `v2/` and the `errorRecords` / `failedInserts` / `transformDeadletterOut` handling. The template separates *transform* errors (can't parse) from *write* errors (BigQuery rejected the insert).

**Estimated time.** 40 minutes.

---

## Problem 6 — Cost-model the streaming pipeline

**Problem statement.** Write a cost estimate (`notes/streaming-cost.md`) for the mini-project pipeline running continuously at **100 events/sec, 1 KB each**, in a single region, for a 30-day month. Break it down by component:

1. **Pub/Sub** — message ingestion + delivery volume (price per TiB).
2. **Dataflow** — worker-hours (assume one small worker held steady) + Streaming Engine + Shuffle.
3. **BigQuery** — streaming/Storage Write API ingestion + storage of the landed rows.
4. **Monitoring** — the alert policy (free tier likely covers it).

State your assumptions and your sources (the public pricing pages). Then state the single biggest line item and one concrete move to cut it.

**Acceptance criteria.**

- `notes/streaming-cost.md` has a per-component breakdown with dollar figures and the assumptions behind each.
- It cites the Pub/Sub, Dataflow, and BigQuery pricing pages.
- It identifies the biggest line item (almost certainly Dataflow worker-hours) and a concrete reduction (spot/preemptible workers, Dataflow Prime right-fitting, or drain-when-idle).
- The total monthly figure is plausible (this workload should land in the low tens of dollars in one region).

**Hint.** At 100 msg/s × 1 KB, monthly volume ≈ 100 × 1024 × 86400 × 30 ≈ 265 GiB — well under Pub/Sub's first-TiB pricing tier, so Pub/Sub is cheap. Dataflow worker-hours (24×30 = 720 hours of one worker) dominate. Spot workers cut that ~60–80%.

**Estimated time.** 50 minutes.

---

## Submission

Push the entire `notes/` and `homework/` directories to your Week 9 Git repository. The instructor reviews by:

1. Reading each note in `notes/`.
2. Re-running `homework/late_data.py` and verifying the undercount matches the injected late fraction.
3. Cross-checking the cited URLs are real and the claims are consistent with the sources.

A submission whose notes are present, whose `late_data.py` reproduces the undercount, and whose cost model is plausible and sourced is a pass. The most common review-fail is "the broker memo says 'it depends' instead of choosing" — pick one and defend it.

---

## Rubric

| Problem | Weight | What earns full marks |
|---|---|---|
| 1 — Broker memo | 20% | A clear choice, all five axes addressed, a rebutted counter-argument, and a "what would flip it." |
| 2 — DLQ IAM experiment | 15% | Command output showing the silent-no-op and the recovery; correct explanation of the service-account model. |
| 3 — Wrong-numbers repro | 20% | Runs locally; undercount ≈ injected late fraction; correct identification of the fixing knob. |
| 4 — Push/pull matrix | 15% | Six distinct patterns, mixed recommendations, and a genuine "tool is insufficient" case. |
| 5 — Template DLQ read | 15% | Correct file path, parse-vs-insert distinction, dead-letter metadata named, one technique to adopt. |
| 6 — Cost model | 15% | Sourced per-component breakdown, plausible total, biggest line item + a concrete cut. |

A passing homework is ≥ 70% across the rubric. Anything that claims a number without a source or a run loses the marks for that problem.

---

**References**

- Google Cloud — Pub/Sub pricing: <https://cloud.google.com/pubsub/pricing>
- Google Cloud — Dataflow pricing: <https://cloud.google.com/dataflow/pricing>
- Google Cloud — BigQuery pricing: <https://cloud.google.com/bigquery/pricing>
- `GoogleCloudPlatform/DataflowTemplates`: <https://github.com/GoogleCloudPlatform/DataflowTemplates>
- Apache Beam — Triggers: <https://beam.apache.org/documentation/programming-guide/#triggers>
- Google Cloud — "Handle message failures": <https://cloud.google.com/pubsub/docs/handling-failures>
