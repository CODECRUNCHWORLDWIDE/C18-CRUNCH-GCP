# Week 13 — Observability with OpenTelemetry: Traces, Metrics, Logs, SLOs, and Burn-Rate Alerts

Welcome to **C18 · Crunch GCP**, Week 13, and the start of Phase 4 — **Production & Capstone**. For twelve weeks you built primitives. Week 06 gave you GKE, Week 07 Cloud Run, Week 08 a global load balancer and Cloud Armor, Week 09 a Pub/Sub-to-Dataflow-to-BigQuery pipeline, Week 10 partitioned-clustered BigQuery, Week 11 a database tier, Week 12 a Vertex AI serving path. Every one of those services works. Not one of them is *observable* in the sense a production engineer means the word: you cannot, today, answer the question "is this service meeting the promise we made to its users, right now, and if not, which dependency is the cause?" without SSH-ing somewhere and reading logs by eye. This week fixes that. By Friday you can instrument a Python or Go service with OpenTelemetry in under an hour, export traces to Cloud Trace, metrics to Cloud Monitoring, and structured logs to Cloud Logging; route those logs to a BigQuery sink and query them; define a Service Level Objective for a service; and arm a multi-window, multi-burn-rate alert that pages you when — and *only* when — the SLO is genuinely at risk.

This is the week the course stops being about "can I deploy it" and starts being about "can I run it on call without hating my life." That distinction is the entire difference between a developer who happens to use the cloud and a platform/SRE engineer who owns a system. The single most important idea in the week — more important than any specific OpenTelemetry API or Cloud Monitoring config — is the **alert hygiene rule: page a human only when there is user-visible risk.** Everything else is a ticket, a dashboard, or a log line. We will derive that rule from first principles in Lecture 1, restate the four golden signals in GCP terms, and then spend Lecture 2 turning it into the one alert primitive that actually obeys it: the multi-window burn-rate alert. If you take one thing from Week 13 into the rest of your career, take that: most production alerting is broken because it pages on causes (CPU is high, a disk is 80% full, a pod restarted) instead of on symptoms (users are getting errors, requests are slow). We page on symptoms. We graph causes.

The second idea is that **OpenTelemetry is the vendor-neutral instrumentation layer and you should treat it as such.** You instrument once, against the OTel API, and you export to whatever backend the business is paying for this quarter — Cloud Trace and Cloud Monitoring today, maybe Grafana Tempo and Prometheus next year, maybe Honeycomb the year after. The instrumentation in your code does not change. This is not a hypothetical: OpenTelemetry is the second-most-active project in the CNCF after Kubernetes itself, it is the convergence point that killed the OpenTracing-vs-OpenCensus schism (Google's own OpenCensus folded into it), and in 2026 every serious observability vendor — including Google Cloud — speaks OTLP, the OpenTelemetry wire protocol, natively. We will export to Google Cloud's backends, but we will do it through the OTel SDK and (where it earns its place) the OpenTelemetry Collector, so that nothing you write this week is locked to GCP. That is also the course's standing rule: name the exit. The exit from Cloud Trace is "point the OTLP exporter at a different collector." That is a one-line change because you instrumented correctly.

The third idea is **the trace is the unit of debugging in a distributed system, and the log line is the unit of evidence.** When the Week 09 pipeline drops events, you do not start by grepping logs across five services. You open the trace for one dropped event, see the span where it died, read the structured log lines *correlated to that span by trace ID*, and you have your answer in ninety seconds instead of ninety minutes. The thing that makes this work is correlation: every log line carries the trace ID and span ID of the request that produced it, every metric exemplar links back to a trace, and Cloud Logging, Cloud Trace, and Cloud Monitoring are stitched together by those IDs. Getting correlation right is most of the work of instrumentation, and it is the part tutorials skip. We will not skip it.

This week is also a **diagnostic checkpoint.** Per the syllabus assessment matrix, the Professional Cloud Architect / Professional Cloud DevOps Engineer practice exam runs in Week 13 as a diagnostic (and again in Week 15 as a readiness gate at ≥70%). The observability domain — SLIs, SLOs, error budgets, burn-rate alerting, the four golden signals — is the single heaviest-weighted section of the Cloud DevOps Engineer blueprint, so the timing is deliberate. You take the diagnostic at the end of the mini-project, score it, and identify your weak domains while there is still time before the capstone. The diagnostic is in `homework.md`.

## Learning objectives

By the end of this week, you will be able to:

- **Instrument** a Python (OpenTelemetry SDK + auto-instrumentation) and a Go (OTel SDK, manual) service to emit traces, metrics, and logs, and export all three to Cloud Trace, Cloud Monitoring, and Cloud Logging via OTLP through the OpenTelemetry Collector.
- **Correlate** logs, traces, and metrics by trace ID and span ID so that one click in Cloud Trace shows you the exact log lines for that request, and explain why correlation is the load-bearing part of instrumentation.
- **Restate** the four golden signals (latency, traffic, errors, saturation) in concrete GCP terms — which Cloud Monitoring metric, which log filter, which trace attribute backs each — and classify any proposed alert as a symptom alert or a cause alert.
- **Apply** the alert-hygiene rule: page only on user-visible risk; everything else is a ticket, a dashboard, or a Slack message. Audit an existing alert set and reclassify each alert.
- **Define** a Service Level Indicator and a Service Level Objective for a real service, choosing a request-based or windows-based SLI with a defensible target, and express it as a Cloud Monitoring `ServiceLevelObjective` resource in Terraform.
- **Compute** an error budget from an SLO and explain what a 99.9% monthly SLO actually permits (≈43 minutes of downtime) and what action each level of budget consumption triggers.
- **Build** a multi-window, multi-burn-rate alerting policy (the Google SRE workbook's 2%/5%/10% fast-and-slow burn pattern) in Terraform, and explain why a single static threshold either pages on noise or misses fast burns.
- **Route** logs with a Cloud Logging sink to BigQuery, Pub/Sub, and a GCS bucket, write the log-router IAM correctly, and query the BigQuery-landed logs in SQL to find an error pattern.
- **Profile** a running service with Cloud Profiler (CPU and heap), read a flame graph, and identify the hot path without a local repro.
- **Validate** an alert end to end by injecting a controlled error rate (1%) into a service and observing that the burn-rate alert fires at the right severity and the wrong alerts stay quiet.
- **Write** a portfolio-grade observability writeup — the "how I instrumented service X and what the burn-rate alert caught" document the syllabus names as one of three portfolio artifacts from C18.

## Prerequisites

- **Weeks 06 through 12 complete and deployable.** This week instruments *those* services. If your Week 09 pipeline or Week 12 Vertex endpoint is not in a state you can redeploy, fix that first — the challenge and mini-project extend every prior service rather than starting fresh. You do not need them all running simultaneously, but you need the Terraform and the container images to exist.
- **A GCP project with the observability APIs enabled:** `cloudtrace.googleapis.com`, `monitoring.googleapis.com`, `logging.googleapis.com`, `cloudprofiler.googleapis.com`. Terraform in `lecture-notes/01` enables them; do it before you start.
- **Python 3.11+ and Go 1.23+ on your PATH.** The OpenTelemetry Python distro we target is the 1.x SDK (`opentelemetry-sdk` 1.27+); the Go module is `go.opentelemetry.io/otel` v1.30+. Exact versions in `resources.md`.
- **`gcloud`, `bq`, and `terraform` (or `tofu`) configured** against the project, with Application Default Credentials set (`gcloud auth application-default login`) so the exporters can authenticate locally.
- **Comfort reading a distributed trace.** If you have never looked at a waterfall view of spans, skim the Cloud Trace overview in `resources.md` before Lecture 1. The mental model — a trace is a tree of timed spans — is assumed.
- **The on-call mindset, even if you have never been on call.** This week asks you to design what wakes you up at 03:00. Take it personally. The alert you write this week is the alert that decides whether you sleep.

## Topics covered

- **OpenTelemetry, the data model.** Traces (spans, span context, trace ID / span ID, parent/child, span kind, attributes, events, status), metrics (counter, up-down counter, histogram, gauge, observable instruments, the new exponential histogram), logs (the log record, the bridge from existing logging frameworks). Resource attributes and semantic conventions (`service.name`, `service.version`, `deployment.environment`). Why the three signals share one `Resource` and one context propagation mechanism.
- **The OpenTelemetry SDK in Python.** `TracerProvider`, `MeterProvider`, `LoggerProvider`; the OTLP exporter; the `BatchSpanProcessor`; auto-instrumentation via `opentelemetry-instrument` for FastAPI/Flask/`requests`/`google-cloud-*`; manual spans with `tracer.start_as_current_span`; the W3C `traceparent` header and context propagation across service boundaries.
- **The OpenTelemetry SDK in Go.** The `otel` global, `trace.Tracer`, `metric.Meter`, the OTLP gRPC exporter, the `otelhttp` and `otelgrpc` instrumentation middlewares, manual span creation, the `slog` bridge for logs.
- **The OpenTelemetry Collector.** The agent vs. gateway deployment patterns, receivers / processors / exporters, the `googlecloud` exporter, the `batch` and `memory_limiter` processors, why a collector beats SDK-direct export for fleet-wide config and cost control. Running it as a sidecar on Cloud Run and as a DaemonSet on GKE.
- **Cloud Trace, Cloud Monitoring, Cloud Logging.** How OTLP data lands in each, the GCP-managed `google.*` exporters vs. OTLP-to-collector-to-googlecloud, trace-log correlation via `logging.googleapis.com/trace` and `spanId`, the `LogEntry` structure, log-based metrics.
- **Log routing & sinks.** The `_Default` and `_Required` buckets, the log router, sink filters in the Logging query language, aggregated sinks at the folder/org level, exclusions, sinks to BigQuery (with partitioned tables), Pub/Sub (for streaming to a SIEM), and GCS (for cold archive). The writer-identity service account and the IAM grant the router needs.
- **The four golden signals in GCP terms.** Latency (Cloud Trace span duration, Cloud Monitoring distribution metrics, `loadbalancing.googleapis.com/https/backend_latencies`), traffic (request counts), errors (5xx ratio, `status` span attribute, error log count), saturation (CPU/memory utilization, queue depth, Pub/Sub `num_undelivered_messages`). Symptoms vs. causes.
- **SLIs, SLOs, error budgets.** Request-based vs. windows-based SLIs. The `ServiceLevelObjective` resource in Cloud Monitoring, the `Service` resource, custom vs. basic SLIs. Choosing a target. The error-budget arithmetic and what each consumption level triggers (the error-budget policy).
- **Burn-rate alerting.** Why a static threshold fails. The burn-rate definition (how fast you are spending the budget relative to "spend it all exactly at the window's end"). The multi-window multi-burn-rate pattern from the Google SRE Workbook: a fast-burn alert (e.g. 14.4× over 1h and 5m) that pages, and a slow-burn alert (e.g. 3× over 6h and 30m) that pages or tickets. Implementing it in Terraform with `google_monitoring_alert_policy`.
- **Cloud Profiler.** Continuous CPU and heap profiling in production, the Python and Go agents, reading the flame graph, comparing two profiles, and the negligible overhead claim (and how to verify it).
- **Validation by fault injection.** Deliberately driving a 1% error rate (a feature flag, a fault-injection middleware, or a Cloud Run revision split) and watching the alert fire at the correct severity while the cause alerts stay silent.

## Weekly schedule

The schedule sums to approximately **36 hours**. Treat it as a target, not a contract. Do the instrumentation on a service you already understand — your own Week 06–12 work — so the new variable is OpenTelemetry, not the service.

| Day       | Focus                                                            | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Alert hygiene, golden signals, the OTel data model               |   2h     |   1.5h    |     0h     |   0.5h    |   1h     |     0h       |    0.5h    |    5.5h     |
| Tuesday   | Instrument Python + Go; export to Cloud Trace + Monitoring       |   2h     |   1.5h    |     0h     |   0.5h    |   1h     |     0h       |    0.5h    |    5.5h     |
| Wednesday | SLOs, error budgets, multi-window burn-rate alerts               |   1.5h   |   1.5h    |     0h     |   0.5h    |   1h     |     0h       |    0.5h    |    5h       |
| Thursday  | Log sinks to BigQuery; Cloud Profiler; challenge #1              |   0.5h   |   0h      |     2h     |   0.5h    |   1h     |     2h       |    0.5h    |    6.5h     |
| Friday    | Mini-project: instrument the fleet, one SLO + alert each         |   0h     |   0h      |     1h     |   0.5h    |   1h     |     3h       |    0.5h    |    6h       |
| Saturday  | Mini-project deep work, 1% fault-injection validation, writeup   |   0h     |   0h      |     0h     |   0h      |   0h     |     3h       |    0h      |    3h       |
| Sunday    | PCA/DevOps diagnostic exam, quiz, teardown gate, review          |   0h     |   0h      |     0h     |   1.5h    |   1h     |     1h       |    0h      |    3.5h     |
| **Total** |                                                                  | **6h**   | **4.5h**  | **3h**     | **4h**    | **6h**   | **9h**       | **2.5h**   | **35h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | OpenTelemetry docs, the Google SRE Workbook chapters, Cloud Trace/Monitoring/Logging docs, the OTel-GCP exporter repos, and the talks worth watching |
| [lecture-notes/01-alert-hygiene-and-golden-signals.md](./lecture-notes/01-alert-hygiene-and-golden-signals.md) | The alert-hygiene rule derived from first principles, symptoms vs. causes, the four golden signals re-stated in GCP terms, and the OpenTelemetry data model that makes them measurable |
| [lecture-notes/02-slos-and-multi-window-burn-rate-alerts.md](./lecture-notes/02-slos-and-multi-window-burn-rate-alerts.md) | SLIs, SLOs, error budgets, why static thresholds fail, and the multi-window multi-burn-rate alert built in Terraform end to end |
| [exercises/README.md](./exercises/README.md) | Index of the four exercises |
| [exercises/exercise-01-instrument-a-python-service.md](./exercises/exercise-01-instrument-a-python-service.md) | Guided: add OTel tracing + metrics to a FastAPI service and export to Cloud Trace + Cloud Monitoring in under an hour |
| [exercises/exercise-04-instrument-a-go-service.md](./exercises/exercise-04-instrument-a-go-service.md) | Guided: the Go mirror of Exercise 1 — add OTel tracing + metrics to a `net/http` service with `otelhttp` and export to Cloud Trace + Cloud Monitoring in under an hour |
| [exercises/exercise-02-burn-rate-alert.tf](./exercises/exercise-02-burn-rate-alert.tf) | Runnable Terraform: define an SLO and a multi-window burn-rate alert that does not page on noise |
| [exercises/exercise-03-log-sink-to-bigquery.py](./exercises/exercise-03-log-sink-to-bigquery.py) | Runnable Python: create a BigQuery log sink, generate a structured error pattern, and query it in SQL |
| [challenges/README.md](./challenges/README.md) | Index of the challenge |
| [challenges/challenge-01-instrument-the-fleet.md](./challenges/challenge-01-instrument-the-fleet.md) | Instrument every service from Weeks 06–12, one SLO + burn-rate alert each, validate with a 1% error injection |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the fleet-wide observability project + the portfolio writeup + the PCA/DevOps diagnostic + the teardown gate |
| [quiz.md](./quiz.md) | 13 questions on alert hygiene, golden signals, SLOs, burn rate, sinks, and the OTel data model, with answer key |
| [homework.md](./homework.md) | Six problems including the PCA/Cloud DevOps practice-exam diagnostic |

## The teardown promise — restated for observability

C18's standing rule is that every week ends with `terraform destroy` and a clean billing line. Week 13 adds a wrinkle: **observability resources are cheap to create and expensive to forget.** A Cloud Profiler agent left running, a BigQuery log sink ingesting every log line at full volume, an alerting policy that pages a phone you no longer check — these do not show up as a big compute bill, they show up as a slow leak and an alert-fatigued you. The mini-project has an explicit teardown gate. Run it. Specifically: delete the log sinks (they keep writing to BigQuery and GCS otherwise), disable the Profiler agents, delete the alerting policies and notification channels, and drop the BigQuery dataset the sink wrote to. The teardown checklist is in the mini-project README.

## A note on what's not here

Week 13 is the observability week. It is deliberately *not*:

- **A Grafana / Prometheus / Tempo / Loki deep dive.** The course standing position is that OTel is the instrumentation layer and the backend is swappable; we use Google's backends because that is the platform this course is about. We point at the OSS exit in `resources.md`. The Grafana cross-cloud dashboard work the README mentions is a stretch goal, not core.
- **Distributed tracing theory beyond what you need.** Dapper, the original Google paper, is in the resources for the curious. We treat tracing as a tool, not a research topic.
- **A full SRE curriculum.** Error budgets, SLOs, and on-call hygiene are introduced here as the minimum a platform engineer must own. The full on-call drill, the escalation design, and the no-blame postmortem are **Week 14**. This week you build the instruments; next week you run the drill.
- **APM vendor comparison.** Datadog, Honeycomb, New Relic, Dynatrace — all speak OTLP, all are defensible choices, none are taught here. The point of OTel is that the choice is reversible.
- **Synthetic monitoring and RUM.** Cloud Monitoring uptime checks get a mention in the golden-signals lecture (they are how you measure "traffic" and "availability" from outside), but real-user monitoring and a full synthetic suite are out of scope.

The point of Week 13 is a sharp, opinionated competence: instrument once with OpenTelemetry, correlate the three signals by trace ID, page only on user-visible risk via a multi-window burn-rate alert, route logs where they belong, and validate the whole thing by breaking the service on purpose and watching the right alert — and only the right alert — fire.

## Up next

Continue to **Week 14 — Security hardening, FinOps, and the on-call drill** once the fleet is instrumented and the 1% injection paged the correct alert. Week 14 takes the alerts you armed this week and runs a synthetic on-call drill against them: a page fires, you triage with the Cloud Trace and Cloud Logging you wired up this week, you mitigate, and you write the postmortem — including, often, "the alert that fired was a cause alert and should have been a ticket; here is the fix." Week 13 builds the instruments. Week 14 proves they were the right instruments. Then Week 15 is the capstone, where every service in the realtime event pipeline ships with the observability you practiced here.

---

*If you find errors in this material, please open an issue or send a PR. Future on-call engineers will thank you.*
