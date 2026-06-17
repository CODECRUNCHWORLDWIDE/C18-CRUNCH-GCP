# Week 9 — Resources

Every resource on this page is **free**. Google Cloud documentation is free without an account. The Apache Beam docs and source are Apache-2.0 and public. Tyler Akidau's "Streaming 101/102" essays are free on the O'Reilly radar. The Terraform provider docs are public. No paywalled books are required; the one book mentioned (the Beam authors' "Streaming Systems") has its first chapters available as the free essays.

Currency note: this list is checked against the 2026 state of the services. Pub/Sub Lite is deprecated — it appears here only so you recognize it as a wrong answer in older tutorials. The BigQuery Storage Write API is the current default for Beam→BigQuery writes; the legacy streaming-inserts path still works but is no longer the recommendation.

## Required reading (work it into your week)

- **Google Cloud — "What is Pub/Sub?" (the data model)**:
  <https://cloud.google.com/pubsub/docs/overview>
- **Google Cloud — "Choose a subscription type" (pull vs. push vs. export)**:
  <https://cloud.google.com/pubsub/docs/subscriber>
- **Google Cloud — "Message ordering"**:
  <https://cloud.google.com/pubsub/docs/ordering>
- **Google Cloud — "Handle message failures" (dead-letter topics + the IAM grants)**:
  <https://cloud.google.com/pubsub/docs/handling-failures>
- **Google Cloud — "Exactly-once delivery" (read twice; note the regional requirement)**:
  <https://cloud.google.com/pubsub/docs/exactly-once-delivery>
- **Apache Beam — "Programming guide: Windowing"**:
  <https://beam.apache.org/documentation/programming-guide/#windowing>
- **Apache Beam — "Programming guide: Triggers" (the allowed-lateness / accumulation-mode reference)**:
  <https://beam.apache.org/documentation/programming-guide/#triggers>
- **Tyler Akidau — "Streaming 101: The world beyond batch"** — the source material for Lecture 2. If you read one thing this week beyond the lectures, read this:
  <https://www.oreilly.com/radar/the-world-beyond-batch-streaming-101/>
- **Tyler Akidau — "Streaming 102"** — windows, watermarks, triggers, accumulation, in the author's own words:
  <https://www.oreilly.com/radar/the-world-beyond-batch-streaming-102/>

## Authoritative deep dives

- **Google Cloud — "Dataflow streaming pipelines" (the runner's view of the Beam model)**:
  <https://cloud.google.com/dataflow/docs/concepts/streaming-pipelines>
- **Google Cloud — "Streaming Engine" (why killing a worker doesn't lose state)**:
  <https://cloud.google.com/dataflow/docs/streaming-engine>
- **Google Cloud — "Read from Pub/Sub with Dataflow" (`timestamp_attribute`, `id_label`, dedup)**:
  <https://cloud.google.com/dataflow/docs/concepts/streaming-with-cloud-pubsub>
- **Google Cloud — "Dataflow Prime" (right-fitting + vertical autoscaling)**:
  <https://cloud.google.com/dataflow/docs/guides/enable-dataflow-prime>
- **Google Cloud — "Pub/Sub to BigQuery" Dataflow template (the managed alternative to hand-written Beam)**:
  <https://cloud.google.com/dataflow/docs/guides/templates/provided/pubsub-to-bigquery>
- **Google Cloud — "BigQuery Storage Write API" (the exactly-once sink path)**:
  <https://cloud.google.com/bigquery/docs/write-api>
- **Google Cloud — "Replay and discard messages" (seek; Pub/Sub's replay story)**:
  <https://cloud.google.com/pubsub/docs/replay-overview>
- **Apache Beam — "Streaming systems basics: watermarks"**:
  <https://beam.apache.org/documentation/basics/#watermark>
- **Apache Beam — "Python SDK quickstart"**:
  <https://beam.apache.org/get-started/quickstart-py/>

## The four-way comparison sources

When you write the homework comparison, cite the primary docs, not blog hot-takes:

- **Apache Kafka — Documentation (design, delivery semantics, exactly-once)**:
  <https://kafka.apache.org/documentation/#design>
- **Confluent — "Exactly-once semantics in Apache Kafka"**:
  <https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/>
- **Google Cloud — "Managed Service for Apache Kafka" (the GCP-managed-Kafka option)**:
  <https://cloud.google.com/managed-service-for-apache-kafka/docs/overview>
- **NATS — JetStream concepts (persistence, delivery, dedup window)**:
  <https://docs.nats.io/nats-concepts/jetstream>
- **NATS — "Core NATS vs. JetStream"**:
  <https://docs.nats.io/nats-concepts/core-nats>
- **AWS — Amazon SQS standard vs. FIFO**:
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-queue-types.html>
- **AWS — SQS dead-letter queues**:
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html>

## Terraform / IaC references

- **Terraform `google_pubsub_topic`**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/pubsub_topic>
- **Terraform `google_pubsub_subscription` (push_config, dead_letter_policy, retry_policy)**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/pubsub_subscription>
- **Terraform `google_dataflow_flex_template_job` (deploy a streaming job as IaC)**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/dataflow_flex_template_job>
- **Terraform `google_bigquery_table` (time-partitioning + clustering)**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_table>
- **Terraform `google_monitoring_alert_policy` (the DLQ-accumulation alert)**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_alert_policy>

## Client-library and SDK references

- **`google-cloud-pubsub` (Python) — publisher & subscriber clients**:
  <https://cloud.google.com/python/docs/reference/pubsub/latest>
- **Apache Beam Python SDK — `apache_beam.io.gcp.pubsub`**:
  <https://beam.apache.org/releases/pydoc/current/apache_beam.io.gcp.pubsub.html>
- **Apache Beam Python SDK — `apache_beam.transforms.window`**:
  <https://beam.apache.org/releases/pydoc/current/apache_beam.transforms.window.html>
- **Apache Beam Python SDK — `apache_beam.transforms.trigger`**:
  <https://beam.apache.org/releases/pydoc/current/apache_beam.transforms.trigger.html>
- **`gcloud pubsub` CLI reference**:
  <https://cloud.google.com/sdk/gcloud/reference/pubsub>

## Source repos worth skimming

- **`apache/beam`** — the Beam SDK. The Python windowing/trigger implementations live in `sdks/python/apache_beam/transforms/`:
  <https://github.com/apache/beam>
- **`GoogleCloudPlatform/DataflowTemplates`** — Google's open-source Dataflow templates, including the Pub/Sub-to-BigQuery streaming template with dead-letter handling. Read this to see production-grade error routing in real Beam code:
  <https://github.com/GoogleCloudPlatform/DataflowTemplates>
- **`googleapis/python-pubsub`** — the Python Pub/Sub client; read `samples/snippets/` for canonical publish/subscribe patterns:
  <https://github.com/googleapis/python-pubsub>

## Talks worth watching (all free, no account)

- **Tyler Akidau — "Watermarks: Time and Progress in Apache Beam and Beyond"** (Strata / various) — the definitive watermark talk by the model's author. Search YouTube for "Tyler Akidau watermarks".
- **Frances Perry & Tyler Akidau — "The Dataflow Model" / Apache Beam keynote** — the origin of the windowing-watermark-trigger triad. Search YouTube for "Frances Perry Apache Beam".
- **Google Cloud — "Pub/Sub deep dive" (Cloud Next session)** — the messaging team walks the delivery guarantees. Search YouTube for "Google Cloud Pub Sub deep dive Next".
- **"Streaming Systems" book overview** — Akidau, Chernyak, Lax. The book is the long-form of Streaming 101/102; the first chapters are the free essays linked above.

## How to use this resource list

The lectures cite specific URLs at decision points. The three you should read end-to-end this week:

1. **Streaming 101 + 102** (Akidau). Foundational; Lecture 2 is built on them. ~90 minutes total, decisive.
2. **Pub/Sub "Exactly-once delivery"** doc. ~20 minutes; clears up the most over-claimed property in the week.
3. **Beam "Triggers" programming-guide section.** ~30 minutes; you will reference it while writing the mini-project.

The rest are reference material — bookmark and return when a specific question arises. Do not feel obligated to read every link; even senior engineers re-read the watermark essay when they touch a streaming pipeline.

---

*Bookmarks decay. If a Google Cloud doc link rots, the page almost always moved within `cloud.google.com/pubsub` or `cloud.google.com/dataflow` — search the title. Beam docs are stable at `beam.apache.org`.*
