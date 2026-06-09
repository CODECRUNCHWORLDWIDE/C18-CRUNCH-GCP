# Week 15 — Resources

Capstone week. The reading here is split into five buckets: how architecture reviews actually run, the two exam blueprints you are gated on, the load- and chaos-testing tooling, the cost / FinOps queries, and the exit-plan references. Everything is free unless explicitly noted; the two practice-exam vouchers are the only thing that costs money, and they are optional (the bundled practice questions in `exercise-03` clear the gate on their own).

## Architecture review — how it really runs

- **Google SRE Book — "Postmortem Culture: Learning from Failure"** — the blameless-postmortem chapter you will model your chaos-drill writeup on:
  <https://sre.google/sre-book/postmortem-culture/>
- **Google SRE Workbook — "Implementing SLOs"** — the SLO/error-budget framing the reviewers expect you to speak in:
  <https://sre.google/workbook/implementing-slos/>
- **Google Cloud Architecture Framework** — the canonical six-pillar review lens (operational excellence, security, reliability, cost, performance, sustainability). Reviewers ask questions straight off this:
  <https://cloud.google.com/architecture/framework>
- **AWS "Working Backwards" / Amazon's PR-FAQ and the architecture-review tradition** — read for contrast; the question style transfers:
  <https://www.aboutamazon.com/news/workplace/an-insider-look-at-amazons-culture-and-processes>
- **"How to run an architecture review" — Pragmatic Engineer (Gergely Orosz)** — the practitioner's view of the meeting itself:
  <https://blog.pragmaticengineer.com/>
- **Mermaid live editor** — draw the architecture diagram you will defend; it renders in GitHub:
  <https://mermaid.live/>

## The exam blueprints (your readiness gate)

- **Professional Cloud Architect — exam guide (2026 blueprint):**
  <https://cloud.google.com/learn/certification/cloud-architect>
- **Professional Cloud DevOps Engineer — exam guide:**
  <https://cloud.google.com/learn/certification/cloud-devops-engineer>
- **Sample questions (official, free)** — calibrate the question *style* before you sit `exercise-03`:
  <https://cloud.google.com/learn/certification/practice-exams>
- **Google Cloud Skills Boost** — free quests that map to the blueprint domains you find weak after the practice exam:
  <https://www.cloudskillsboost.google/>

## Load testing & end-to-end latency

- **`hey`** — the simple HTTP load generator we default to for the 100-RPS run; one binary, no setup:
  <https://github.com/rakyll/hey>
- **Locust** — Python-defined load, distributed across workers when you want multi-region origin; what you graduate to:
  <https://locust.io/>
- **`wrk2`** — corrected-latency load generator; use it when you care about coordinated-omission-free p99:
  <https://github.com/giltene/wrk2>
- **Gil Tene — "How NOT to Measure Latency"** — watch this before you trust any p99 number you produce:
  <https://www.youtube.com/watch?v=lJ8ydIuPFeU>
- **Cloud Monitoring MQL / PromQL reference** — how to read the p99 distribution off the dashboard rather than off your laptop:
  <https://cloud.google.com/monitoring/mql>

## Chaos engineering on GCP

- **Cloud DNS routing policies (geolocation + health-checked failover)** — the mechanism behind the region-failover drill:
  <https://cloud.google.com/dns/docs/policies-overview>
- **Global external Application Load Balancer — SSL certificates** — how cert rotation works on the LB, including Google-managed vs self-managed:
  <https://cloud.google.com/load-balancing/docs/ssl-certificates>
- **Pub/Sub — flow control, dead-letter topics, and backlog metrics** — what bends first under 10x overload:
  <https://cloud.google.com/pubsub/docs/handling-failures>
- **Dataflow — monitoring and autoscaling** — read `data_watermark` lag and the backlog-bytes metric during the overload drill:
  <https://cloud.google.com/dataflow/docs/guides/using-monitoring-intf>
- **Principles of Chaos Engineering** — the discipline, stated plainly:
  <https://principlesofchaos.org/>

## Cost, billing export, FinOps

- **Billing export to BigQuery — schema reference** — the table your cost queries run against:
  <https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables>
- **GCP Pricing Calculator** — for the list-price numbers in your cost report and exit plan:
  <https://cloud.google.com/products/calculator>
- **FinOps Foundation — the FinOps framework** — vendor-neutral language for the cost section of the review:
  <https://www.finops.org/framework/>
- **Committed use discounts (CUDs) and sustained use discounts** — the moves that pay back inside a quarter:
  <https://cloud.google.com/docs/cuds>

## The exit plan & lock-in

- **Apache Beam portability — the Beam model runs on Flink/Spark, not just Dataflow** — your Beam pipeline is your most portable asset; know why:
  <https://beam.apache.org/documentation/runners/capability-matrix/>
- **Apache Iceberg** — the open table format you would land in if you left BigQuery:
  <https://iceberg.apache.org/>
- **Trino** — the query engine that replaces BigQuery on Iceberg:
  <https://trino.io/>
- **CockroachDB & YugabyteDB** — the self-hosted answers to "what replaces Spanner":
  <https://www.cockroachlabs.com/docs/> · <https://docs.yugabyte.com/>
- **vLLM** — the open-weights serving engine that replaces a Vertex AI Endpoint on a GKE GPU pool:
  <https://docs.vllm.ai/>
- **Apache Kafka** — the streaming substrate that replaces Pub/Sub; Strimzi runs it on Kubernetes:
  <https://kafka.apache.org/> · <https://strimzi.io/>
- **Martin Kleppmann — *Designing Data-Intensive Applications*** — the book to cite when you justify the consistency/availability tradeoffs in your exit plan (not free; widely available through libraries):
  <https://dataintensive.net/>

## Tools you'll use this week

- **`gcloud`, `bq`, `gsutil`, `kubectl`, `terraform`** — already installed from earlier weeks.
- **`hey`** — `go install github.com/rakyll/hey@latest` or `brew install hey`.
- **`python3` with `google-cloud-monitoring`, `google-cloud-pubsub`, `requests`** — the exercise scripts import these; `pip install google-cloud-monitoring google-cloud-pubsub requests`.
- **`jq`** — for slicing `gcloud --format=json` output.
- **A screen recorder** — QuickTime (macOS), OBS Studio (cross-platform, free), or Loom for the 5-minute video.

## Career pack (cross-referenced)

The capstone is the headline portfolio artifact. The supporting docs live one level up in the track root:

- `interview-prep/` — the four system-design rounds and four GCP deep-dive drills used for the mock interview.
- `production-runbook.md` — the on-call runbook that ships with the capstone.
- `portfolio.md` — the templates for writing up the capstone, the Week 04 module library, and the Week 13 observability post.

---

*If a link 404s, please open an issue so we can replace it.*
