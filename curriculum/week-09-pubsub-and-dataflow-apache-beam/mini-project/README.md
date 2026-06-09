# Mini-Project — Deployable streaming-ingest pipeline (generator → Pub/Sub → Dataflow → BigQuery)

> Build, deploy, and tear down a production-shaped streaming-ingest pipeline entirely through Terraform: a synthetic event generator publishes to Pub/Sub, a Dataflow (Python Apache Beam) streaming job parses and windows the events and writes them to a partitioned-clustered BigQuery table, malformed events are routed to a dead-letter topic, and a Cloud Monitoring alert fires when the DLQ accumulates. By the end you have the **stream and process tiers of the capstone**, deployed via your Week 04 modules, validated under load, and torn down on demand.

This is the most important mini-project in Phase 3 and the **direct precursor to the capstone**. The capstone's stream tier (Pub/Sub with a DLQ and per-tenant ordering) and process tier (Dataflow windowing into BigQuery) are exactly what you build here — the capstone scales it up and wraps it in the edge/serve tiers from Phases 2 and 4. Treat this as the first commit of your capstone repo, not a throwaway. Do not delete it; you will extend it in Week 14 and again in Week 15.

**Estimated time:** ~12.5 hours (split across Thursday, Friday, Saturday, Sunday in the suggested schedule).

**Cost:** This runs real Dataflow workers. On the smallest worker (`n1-standard-2` or Dataflow Prime's right-fitting), Streaming Engine, a single region, and a teardown each evening, expect **under \$2 for the week** if you follow teardown discipline. **Multi-region Dataflow is a paid-but-cheap opt-in** (see "Stretch: multi-region") — budget a couple of extra dollars and an armed alert if you take it. Arm your Week 01 budget alert before you `apply`.

---

## What you will build

A single Terraform-deployed system with five parts:

1. **Generator** (`generator/generator.py`) — a synthetic event producer. Publishes JSON events to the Pub/Sub topic at a configurable rate, with per-tenant ordering keys, a deterministic `event_id` (as a message attribute for dedup), and a configurable malformed-event rate so the DLQ has real work.
2. **Stream tier** — a Pub/Sub topic `ingest-events`, a dead-letter topic `ingest-events-dlq`, a Dataflow pull subscription with exactly-once delivery and ordering enabled, and a DLQ inspection subscription. All in Terraform, using your Week 04 module patterns.
3. **Process tier** — a Python Apache Beam streaming pipeline (`pipeline/pipeline.py`) deployed to Dataflow. It reads from the subscription (event-time timestamps, `id_label` dedup), parses and validates each event, routes malformed events to the DLQ via tagged output, windows the good events on event time, and writes them to BigQuery via the Storage Write API.
4. **Sink** — a BigQuery dataset `ingest` and a table `ingest.events`, **partitioned by `event_time` (DAY)** and **clustered by `tenant`** — the exact shape Week 10 will query cheaply.
5. **Alerting** — a Cloud Monitoring alert policy that fires when the DLQ's undelivered-message count exceeds a threshold for a sustained window. A DLQ nobody watches is a silent failure; this alert is non-negotiable.

You ship **one repository** with this layout:

```
mini-project/streaming-ingest/
├── terraform/
│   ├── main.tf                 # wires the modules together for envs/dev
│   ├── variables.tf
│   ├── outputs.tf
│   └── modules/                # reuse / extend your Week 04 modules
│       ├── pubsub-stream/      # topic + dlq + subs + IAM
│       ├── bigquery-sink/      # dataset + partitioned-clustered table
│       ├── dataflow-job/       # the flex-template streaming job
│       └── dlq-alert/          # monitoring alert policy
├── generator/
│   ├── generator.py
│   └── requirements.txt
├── pipeline/
│   ├── pipeline.py
│   ├── requirements.txt
│   └── metadata.json           # flex-template metadata
├── validate.py                 # post-run correctness check
├── teardown.sh                 # drain job, then terraform destroy
└── README.md                   # your writeup
```

---

## Rules

- **You may** read all GCP docs, the Beam docs, the lecture notes, your exercises, the challenge, and your own Week 04 modules.
- **You may NOT** use the prebuilt Pub/Sub-to-BigQuery Dataflow *template* as the processing tier — you write `pipeline.py` yourself. You may read the template's source for ideas.
- **Everything is Terraform.** The only non-Terraform steps allowed are: building/staging the Dataflow flex-template container (`gcloud dataflow flex-template build`), running the generator, and running `validate.py`. No click-ops. No `gcloud pubsub topics create`. If you created it by hand, it doesn't count.
- **The generator and pipeline target Python 3.11+** and pin `apache-beam[gcp]` and `google-cloud-pubsub` in `requirements.txt`.
- **The Dataflow worker uses a dedicated, least-privilege service account.** No default compute SA. No `roles/owner`. This is a Week 02 habit you do not drop now.
- **Region pinning.** Default region `us-central1` (or your nearest free-trial region). Multi-region is an explicit opt-in variable, default `false`.

---

## Acceptance criteria

The grading rubric is below. Each box maps to a specific deliverable.

### Infrastructure as code (30%)

- [ ] `terraform apply` from `terraform/` stands up the topic, DLQ, both subscriptions, the BigQuery dataset + table, the Dataflow job, and the alert policy — with **no resource created by hand**.
- [ ] The subscription has `enable_exactly_once_delivery = true` and `enable_message_ordering = true`.
- [ ] The BigQuery table is partitioned by `event_time` (DAY) and clustered by `tenant`. Verify in the table's DDL.
- [ ] The Dataflow worker SA has only `roles/dataflow.worker`, `roles/pubsub.subscriber` (on the sub), `roles/pubsub.publisher` (on the DLQ), and `roles/bigquery.dataEditor` (on the dataset) — least privilege.
- [ ] The Pub/Sub service account has the publisher/subscriber grants needed for any subscription-level dead-lettering you configure.

### Correctness (35%)

- [ ] The generator publishes well-formed and ~2% malformed events with deterministic `event_id`s and per-tenant ordering keys, and writes `published.jsonl` / `published_bad.jsonl` manifests.
- [ ] `pipeline.py` reads with `timestamp_attribute` (event time) and `id_label="event_id"` (dedup).
- [ ] Malformed events are **routed to the DLQ** via `beam.pvalue.TaggedOutput` + `WriteToPubSub` — not dropped, not crashing the bundle.
- [ ] Good events are windowed on **event time** with `allowed_lateness ≥ 60s` and `AccumulationMode.ACCUMULATING`, and written via `WriteToBigQuery(method='STORAGE_WRITE_API')`.
- [ ] After a 30-minute run and a `drain`: `validate.py` shows `COUNT(DISTINCT event_id)` in `ingest.events` **equals** the well-formed published count (no loss) and `COUNT(*)` **equals** `COUNT(DISTINCT event_id)` (no duplicates).
- [ ] The DLQ contains exactly the malformed events (count matches `published_bad.jsonl`).

### Alerting (15%)

- [ ] A Cloud Monitoring alert policy fires when `pubsub.googleapis.com/subscription/num_undelivered_messages` on the DLQ subscription exceeds a threshold (e.g., > 10) for a sustained window (e.g., 5 minutes).
- [ ] You **demonstrate the alert firing**: temporarily raise the generator's malformed rate to 50%, watch the DLQ accumulate, and capture the alert (screenshot or the incident JSON). Then restore the rate.
- [ ] The alert notification channel is configured (email to your course address or a Slack webhook).

### Documentation & teardown (20%)

- [ ] `README.md` at the project root contains: a one-paragraph description, an architecture diagram (Mermaid is fine), the `validate.py` output proving correctness, and a short "what I'd change for the capstone" note.
- [ ] `findings.md` (or a section of the README) explains *why* exactly-once held end-to-end: the three cooperating pieces.
- [ ] **Teardown gate:** `teardown.sh` drains the Dataflow job, waits for the backlog to empty, then runs `terraform destroy`. After it, `gcloud dataflow jobs list --status=active` shows nothing.

---

## Suggested implementation outline

The order matters: stream tier first, then a trivial pipeline that just lands rows, then windowing/DLQ, then the alert. Get bytes flowing before you get them perfect.

### Day 1 (Thursday — ~2 hours): the stream and sink tiers

1. Scaffold the repo and the four Terraform modules. Reuse your Week 04 `pubsub`-shaped module if you have one; otherwise write `modules/pubsub-stream` with the topic, DLQ, subs, and IAM (lift the IAM grant pattern straight from Exercise 1).
2. Write `modules/bigquery-sink`: the dataset and the partitioned-clustered table. The table schema:
   ```hcl
   resource "google_bigquery_table" "events" {
     dataset_id          = google_bigquery_dataset.ingest.dataset_id
     table_id            = "events"
     deletion_protection = false  # so terraform destroy works in the lab

     time_partitioning {
       type  = "DAY"
       field = "event_time"
     }
     clustering = ["tenant"]

     schema = jsonencode([
       { name = "event_id",   type = "STRING",    mode = "REQUIRED" },
       { name = "event_type", type = "STRING",    mode = "REQUIRED" },
       { name = "tenant",     type = "STRING",    mode = "REQUIRED" },
       { name = "amount",     type = "FLOAT64",   mode = "NULLABLE" },
       { name = "event_time", type = "TIMESTAMP", mode = "REQUIRED" },
     ])
   }
   ```
3. `terraform apply`. Confirm the topic, subs, dataset, and table exist.
4. Write `generator/generator.py` and publish a handful of events by hand. Confirm they sit in the subscription backlog (`gcloud pubsub subscriptions pull ... --auto-ack`).

### Day 2 (Friday — ~3 hours): the processing tier

5. Write `pipeline/pipeline.py`. Start with the simplest version that reads from the subscription and writes raw rows to BigQuery — no windowing, no DLQ yet. Run it on the **Direct runner locally first** against the emulator or a small live backlog to confirm the read/parse/write path works. (You proved you can run Beam locally in Exercise 2; lean on that.)
6. Build and stage the **flex template**:
   ```bash
   gcloud dataflow flex-template build "gs://${BUCKET}/templates/ingest.json" \
     --image-gcr-path "${REGION}-docker.pkg.dev/${PROJECT}/dataflow/ingest:latest" \
     --sdk-language "PYTHON" \
     --flex-template-base-image "PYTHON3" \
     --py-path "pipeline/" \
     --env "FLEX_TEMPLATE_PYTHON_PY_FILE=pipeline.py" \
     --env "FLEX_TEMPLATE_PYTHON_REQUIREMENTS_FILE=requirements.txt" \
     --metadata-file "pipeline/metadata.json"
   ```
7. Wire `modules/dataflow-job` with `google_dataflow_flex_template_job` pointing at the staged template, the subscription, and the BigQuery table. `terraform apply`. Watch the job reach *Running* in the Dataflow UI.
8. Run the generator at ~20 msg/s for a few minutes. Confirm rows land in `ingest.events`.

### Day 3 (Saturday — ~3.5 hours): windowing, DLQ routing, validation, chaos

9. Add the windowing (event-time fixed windows, `allowed_lateness`, `ACCUMULATING`) and the `id_label` dedup to the read. Re-stage the template, re-apply.
10. Add the malformed-event handling: a `DoFn` with a tagged dead-letter output, and a `WriteToPubSub` to the DLQ topic for the bad tag. Bump the generator's malformed rate to ~2%. Confirm bad events land on the DLQ and good events land in BigQuery.
11. Run the full **30-minute load test**. Halfway through, **kill a Dataflow worker** (the challenge's chaos step) and confirm the job recovers.
12. `drain` the job, run `validate.py`. Iterate until `distinct_ids == published_good` and `rows == distinct_ids`. The most common failure is duplicates — if `rows > distinct_ids`, your sink isn't idempotent (check `STORAGE_WRITE_API` and `id_label`).

### Day 4 (Sunday — ~1 hour): the alert and the teardown

13. Add `modules/dlq-alert` (the Cloud Monitoring policy). Apply. Demonstrate it firing by spiking the malformed rate to 50% for a few minutes, then restore.
14. Write the README, the architecture diagram, and `findings.md`.
15. Run `teardown.sh`. Confirm no active Dataflow job remains. Push.

---

## Key code shapes (you fill in the rest)

The DLQ-routing `DoFn` — the load-bearing pattern for the process tier:

```python
import json
import apache_beam as beam

GOOD = "good"
DLQ = "dead_letter"

REQUIRED = ("event_id", "event_type", "tenant", "event_time")

class ParseEvent(beam.DoFn):
    def process(self, raw: bytes):
        try:
            obj = json.loads(raw.decode("utf-8"))
            for field in REQUIRED:
                if field not in obj:
                    raise ValueError(f"missing field: {field}")
            # Coerce / validate types here; raise on anything unexpected.
            obj["amount"] = float(obj.get("amount", 0.0))
            yield beam.pvalue.TaggedOutput(GOOD, obj)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError) as exc:
            # Route the ORIGINAL bytes to the DLQ with a reason attribute.
            yield beam.pvalue.TaggedOutput(DLQ, raw)
```

Wiring the tagged outputs in the pipeline body:

```python
parsed = (
    messages
    | "Parse" >> beam.ParDo(ParseEvent()).with_outputs(GOOD, DLQ)
)
# Good events → window → BigQuery (Storage Write API).
(parsed[GOOD]
 | "Window" >> beam.WindowInto(
       beam.window.FixedWindows(60),
       allowed_lateness=120,
       accumulation_mode=beam.trigger.AccumulationMode.ACCUMULATING)
 | "ToBQ" >> beam.io.WriteToBigQuery(
       table=KNOWN_TABLE_SPEC,
       method=beam.io.WriteToBigQuery.Method.STORAGE_WRITE_API,
       create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
       write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND))
# Malformed events → DLQ topic.
(parsed[DLQ]
 | "ToDLQ" >> beam.io.WriteToPubSub(topic=DLQ_TOPIC))
```

The DLQ alert policy in Terraform:

```hcl
resource "google_monitoring_alert_policy" "dlq_accumulating" {
  display_name = "ingest-dlq accumulating"
  combiner     = "OR"

  conditions {
    display_name = "DLQ undelivered > 10 for 5m"
    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"pubsub_subscription\"",
        "resource.label.subscription_id = \"ingest-events-dlq-pull\"",
        "metric.type = \"pubsub.googleapis.com/subscription/num_undelivered_messages\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 10
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]
}
```

---

## Stretch: multi-region (paid-but-cheap opt-in)

Behind a `var.multi_region = true` flag, deploy a second Dataflow job in a second region (`us-east1`) reading from the *same* Pub/Sub subscription's regional endpoint, or a second subscription. Observe how a regional outage would be absorbed. This costs a second set of worker-hours — budget a couple of dollars and **arm a billing alert**. Default the flag to `false`; the grader will not run it. This is the on-ramp to the capstone's multi-region requirement.

---

## Anti-goals

Explicitly **not** part of this mini-project:

- **The edge tier.** No Cloud Run ingest service, no load balancer, no Cloud Armor. The generator publishes directly. The capstone adds the edge; here we focus on stream + process.
- **The serve tier.** No gRPC service, no Spanner, no Vertex AI. That's the capstone's serve tier.
- **A custom autoscaler.** Use Dataflow's built-in autoscaling (or Dataflow Prime). Hand-tuning worker counts is not the lesson.
- **Schema evolution.** The event schema is fixed. Handling additive/breaking schema changes mid-stream is a real problem and a different exercise.

---

## Submission

Push to your Week 9 GitHub repository at `mini-project/streaming-ingest/`. The instructor reviews by:

1. Reading the Terraform and confirming nothing was created by hand.
2. Running `terraform apply` in a fresh project (or reading your applied-state evidence).
3. Running the generator and `validate.py`, confirming zero loss and zero duplicates.
4. Confirming the DLQ alert exists and your evidence shows it fired.
5. Running `teardown.sh` and confirming no active Dataflow job remains.

A submission whose `validate.py` shows zero loss and zero duplicates, whose alert fired, and whose teardown is clean is a pass. The most common review-fail is "`rows > distinct_ids`" (non-idempotent sink) or "left the Dataflow job running" (no teardown). Verify both before submitting.

---

**References**

- Google Cloud — "Deploy a Dataflow flex template": <https://cloud.google.com/dataflow/docs/guides/templates/using-flex-templates>
- Google Cloud — "Write from Dataflow to BigQuery (Storage Write API)": <https://cloud.google.com/dataflow/docs/guides/write-to-bigquery>
- Google Cloud — "Pub/Sub monitoring metrics": <https://cloud.google.com/pubsub/docs/monitoring>
- Apache Beam — "Additional outputs (tagged outputs)": <https://beam.apache.org/documentation/programming-guide/#additional-outputs>
- Terraform — `google_dataflow_flex_template_job`: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/dataflow_flex_template_job>
