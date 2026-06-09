# Week 13 — Resources

Almost everything on this page is **free**. The OpenTelemetry documentation and specification are open-source under the CNCF. The Google SRE books — *Site Reliability Engineering* and *The Site Reliability Workbook* — are readable in full, for free, at `sre.google/books`. The Google Cloud docs are free without an account. The exporter and instrumentation repos are Apache-2.0 on GitHub. Where a resource is a paid book, it is marked `[paid]` and a free equivalent is named.

The single most important reading for this week is **The Site Reliability Workbook, Chapter 5 ("Alerting on SLOs")**. It is where the multi-window multi-burn-rate alert comes from, it is short, and it is the source of truth for Lecture 2. Read it before Wednesday.

## Required reading (work it into your week)

- **OpenTelemetry — "What is OpenTelemetry?" and the data-model overview**:
  <https://opentelemetry.io/docs/what-is-opentelemetry/>
- **OpenTelemetry — Traces concepts** (spans, span context, span kind, status):
  <https://opentelemetry.io/docs/concepts/signals/traces/>
- **OpenTelemetry — Metrics concepts** (counter, histogram, gauge, observable instruments):
  <https://opentelemetry.io/docs/concepts/signals/metrics/>
- **OpenTelemetry — Logs concepts** (the log record, the bridge):
  <https://opentelemetry.io/docs/concepts/signals/logs/>
- **OpenTelemetry — Semantic conventions for resources** (`service.name`, `deployment.environment`):
  <https://opentelemetry.io/docs/specs/semconv/resource/>
- **OpenTelemetry — Python: getting started**:
  <https://opentelemetry.io/docs/languages/python/getting-started/>
- **OpenTelemetry — Go: getting started**:
  <https://opentelemetry.io/docs/languages/go/getting-started/>
- **The Site Reliability Workbook — Chapter 5, "Alerting on SLOs"** (the burn-rate chapter; read it twice):
  <https://sre.google/workbook/alerting-on-slos/>
- **The Site Reliability Workbook — Chapter 2, "Implementing SLOs"**:
  <https://sre.google/workbook/implementing-slos/>
- **Site Reliability Engineering — Chapter 6, "Monitoring Distributed Systems"** (the four golden signals, the original source):
  <https://sre.google/sre-book/monitoring-distributed-systems/>
- **Google Cloud — "Define SLOs"** and the SLO/SLI concepts:
  <https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring>
- **Google Cloud — OpenTelemetry on Google Cloud overview**:
  <https://cloud.google.com/trace/docs/setup/python-ot>

## Authoritative deep dives

- **The Site Reliability Workbook (full text, free)** — the practical companion to the SRE book; Chapters 2, 4, and 5 are the observability core of this week:
  <https://sre.google/workbook/table-of-contents/>
- **Site Reliability Engineering (full text, free)** — the original. Chapter 4 ("Service Level Objectives") and Chapter 6 ("Monitoring Distributed Systems") are the canonical definitions of SLO and golden signals:
  <https://sre.google/sre-book/table-of-contents/>
- **"Dapper, a Large-Scale Distributed Systems Tracing Infrastructure"** — the 2010 Google paper that invented the trace-as-tree-of-spans model OpenTelemetry implements:
  <https://research.google/pubs/pub36356/>
- **OpenTelemetry — the specification** (the source of truth when docs and SDK disagree):
  <https://opentelemetry.io/docs/specs/otel/>
- **OpenTelemetry — the OTLP protocol specification**:
  <https://opentelemetry.io/docs/specs/otlp/>
- **Charity Majors / Liz Fong-Jones / George Miranda — "Observability Engineering" (O'Reilly)** `[paid]` — the canonical book on observability-as-a-discipline; the high-cardinality and "debug with traces" arguments. Free equivalent: the Honeycomb blog and the OTel docs cover ~70% of it:
  <https://www.honeycomb.io/blog>
- **Cindy Sridharan — "Distributed Systems Observability" (O'Reilly free report)** — short, free, the best 60-page introduction to the three pillars and why they are not actually three separate pillars:
  <https://www.oreilly.com/library/view/distributed-systems-observability/9781492033431/>

## OpenTelemetry SDK references (version-pinned for 2026)

We target these versions. Pin them in `requirements.txt` / `go.mod` so your numbers and APIs match the lectures.

- **Python — `opentelemetry-sdk` 1.27+, `opentelemetry-api` 1.27+, `opentelemetry-exporter-otlp` 1.27+, `opentelemetry-instrumentation-fastapi` 0.48b0+** (the `0.xxbN` "instrumentation" versions track the stable SDK; the mapping is documented on the releases page):
  <https://github.com/open-telemetry/opentelemetry-python/releases>
- **Python — zero-code auto-instrumentation (`opentelemetry-instrument`)**:
  <https://opentelemetry.io/docs/zero-code/python/>
- **Python — the `opentelemetry-instrumentation` contrib registry** (FastAPI, Flask, `requests`, `google-cloud-*`, SQLAlchemy, psycopg):
  <https://github.com/open-telemetry/opentelemetry-python-contrib>
- **Go — `go.opentelemetry.io/otel` v1.30+ and `go.opentelemetry.io/otel/sdk` v1.30+**:
  <https://github.com/open-telemetry/opentelemetry-go/releases>
- **Go — `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` and `.../google.golang.org/grpc/otelgrpc`**:
  <https://github.com/open-telemetry/opentelemetry-go-contrib>
- **The OpenTelemetry Collector** (the binary, the receivers/processors/exporters model):
  <https://opentelemetry.io/docs/collector/>
- **The `googlecloud` exporter for the Collector** (the supported path for OTLP → Cloud Trace/Monitoring/Logging):
  <https://github.com/GoogleCloudPlatform/opentelemetry-operations-collector>
- **`opentelemetry-operations-python`** — Google's Python exporters (`opentelemetry-exporter-gcp-trace`, `opentelemetry-exporter-gcp-monitoring`) when you export SDK-direct instead of via the collector:
  <https://github.com/GoogleCloudPlatform/opentelemetry-operations-python>
- **`opentelemetry-operations-go`** — the Go equivalent:
  <https://github.com/GoogleCloudPlatform/opentelemetry-operations-go>

## Google Cloud docs

- **Cloud Trace — overview and setup**:
  <https://cloud.google.com/trace/docs/overview>
- **Cloud Trace — find and view traces** (reading the waterfall):
  <https://cloud.google.com/trace/docs/finding-traces>
- **Cloud Monitoring — metrics overview and metric types** (gauge/delta/cumulative, distribution metrics):
  <https://cloud.google.com/monitoring/api/v3/kinds-and-types>
- **Cloud Monitoring — alerting policies** (the `google_monitoring_alert_policy` surface):
  <https://cloud.google.com/monitoring/alerts>
- **Cloud Monitoring — log-based metrics**:
  <https://cloud.google.com/logging/docs/logs-based-metrics>
- **Cloud Logging — the `LogEntry` structure**:
  <https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry>
- **Cloud Logging — routing and storage overview (the log router)**:
  <https://cloud.google.com/logging/docs/routing/overview>
- **Cloud Logging — configure and manage sinks**:
  <https://cloud.google.com/logging/docs/export/configure_export_v2>
- **Cloud Logging — the Logging query language**:
  <https://cloud.google.com/logging/docs/view/logging-query-language>
- **Cloud Logging — view logs routed to BigQuery** (the partitioned-table schema):
  <https://cloud.google.com/logging/docs/export/bigquery>
- **Cloud Logging — correlate trace and log data** (the `logging.googleapis.com/trace` and `spanId` fields):
  <https://cloud.google.com/trace/docs/trace-log-integration>
- **Cloud Profiler — concepts and the supported languages**:
  <https://cloud.google.com/profiler/docs/concepts-profiling>
- **Cloud Profiler — Python agent** and **Go agent** setup:
  <https://cloud.google.com/profiler/docs/profiling-python> and <https://cloud.google.com/profiler/docs/profiling-go>
- **Cloud Monitoring — SLO REST reference (`ServiceLevelObjective`, `Service`)**:
  <https://cloud.google.com/monitoring/api/ref_v3/rest/v3/services.serviceLevelObjectives>

## Terraform provider references

- **`google_monitoring_service`** (the SLO's parent Service resource):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_service>
- **`google_monitoring_slo`** (the SLO resource):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_slo>
- **`google_monitoring_alert_policy`** (the burn-rate alert):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_alert_policy>
- **`google_monitoring_notification_channel`**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_notification_channel>
- **`google_logging_project_sink`** and **`google_logging_project_bucket_config`**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/logging_project_sink>
- **`google_bigquery_dataset`** and **`google_pubsub_topic`** (sink destinations):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_dataset>

## Talks worth watching (all free, no account)

- **"How NOT to Measure Latency" — Gil Tene** (the canonical talk on why your p99 is a lie if you measure it wrong; foundational for the latency golden signal):
  search YouTube for "Gil Tene How NOT to Measure Latency".
- **"OpenTelemetry: The Vision, Reality, and How to Get Started" — KubeCon** (any recent year):
  search YouTube for "OpenTelemetry KubeCon getting started".
- **"SLOs, Error Budgets, and Burn Rate Alerting" — Google Cloud Tech / SRE talks**:
  search YouTube for "Google SRE burn rate alerting SLO".
- **"Monarch: Google's Planet-Scale In-Memory Time Series Database"** — the system behind Cloud Monitoring; read the VLDB paper or watch a conference talk:
  <https://research.google/pubs/pub50652/>
- **Charity Majors — "Observability and the Glorious Future"** (NDC / various):
  search YouTube for "Charity Majors observability".

## The OSS exit (named, per the course rule)

You instrument with OpenTelemetry so the backend is replaceable. The OSS exit from Cloud Trace / Monitoring / Logging is:

- **Traces:** Grafana Tempo or Jaeger. Point the OTLP exporter at the Tempo distributor instead of the GCP collector. Zero code change.
  <https://grafana.com/oss/tempo/>
- **Metrics:** Prometheus (via the OTel Collector's `prometheus` exporter or the Prometheus remote-write exporter) + Grafana.
  <https://prometheus.io/docs/prometheus/latest/feature_flags/#otlp-receiver>
- **Logs:** Grafana Loki or an Elastic/OpenSearch cluster, via the Collector's `loki` or `elasticsearch` exporter.
  <https://grafana.com/oss/loki/>
- **SLOs / burn-rate alerting:** Sloth (Prometheus SLO generator) or Pyrra generate the same multi-window burn-rate rules as Prometheus recording + alerting rules.
  <https://github.com/slok/sloth>

The exit plan you write in the capstone (Week 15) should cost this out. Because you instrumented against OTel, the migration is "change the collector's exporter block and stand up the OSS backends," not "rewrite every service."

## How to use this resource list

The lectures cite specific URLs from this page at decision points. The links you should read end-to-end this week, in order:

1. **The Site Reliability Workbook, Chapter 5 ("Alerting on SLOs")** — the burn-rate chapter. Non-negotiable. Lecture 2 assumes it.
2. **OpenTelemetry — Traces concepts** — so the data model in Lecture 1 lands.
3. **SRE Book, Chapter 6 ("Monitoring Distributed Systems")** — the four golden signals, from the source.
4. **Google Cloud — "Define SLOs"** — the mapping from the SRE theory to the actual Cloud Monitoring resources you build in Terraform.

The rest are reference material — bookmark them and return when a specific question arises.

---

*Bookmarks decay. If a link rots, search the title — these are canonical pieces and they reappear on the same authors' new homes. The SRE books in particular have lived at `sre.google` for years and will outlast this course.*
