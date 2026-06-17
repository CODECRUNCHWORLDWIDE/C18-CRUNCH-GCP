# Challenge 1 — Instrument the whole fleet and validate the alert by breaking it

> **Estimated time:** 3+ hours. Worth more than its time-cost suggests: this is the artifact the syllabus names as one of three portfolio pieces from C18, and it is the rehearsal for the capstone's observability requirement.

You have, by Week 13, a fleet of services from Weeks 06–12. Your job is to instrument **every one of them** with OpenTelemetry, export traces, metrics, and logs to Cloud Trace + Cloud Logging + Cloud Monitoring, define **one SLO per service** with a **multi-window burn-rate alert**, and then prove the whole thing works by injecting a **1% error rate** into one service and watching the right alert page — while the cause alerts stay silent.

This is open-ended on purpose. There is no solution file. The acceptance criteria below are the contract.

## The fleet

The services you are instrumenting (yours will vary slightly depending on how you built each week):

| Week | Service | Language | Suggested SLI | Suggested SLO |
|------|---------|----------|---------------|---------------|
| 06 | GKE FastAPI service (Autopilot + Standard) | Python | availability (non-5xx fraction) | 99.9% / 28d |
| 07 | Cloud Run service + Cloud SQL backend | Python | availability + latency (< 300ms) | 99.9% / 28d |
| 08 | LB + Cloud Armor edge | n/a (edge) | edge availability (LB 5xx fraction) | 99.95% / 28d |
| 09 | Pub/Sub → Dataflow → BigQuery pipeline | Python (Beam) | freshness (events landed < 60s) + DLQ rate | 99% of events fresh / 28d |
| 10 | BigQuery query service | Python/SQL | query success + latency | 99% / 28d |
| 11 | Database tier (Cloud SQL / AlloyDB / Spanner) | Go gRPC | gRPC availability (non-UNAVAILABLE) | 99.95% / 28d |
| 12 | Vertex AI serving + Gemini fallback | Python | inference availability (incl. fallback) | 99.5% / 28d |

You do not need every service running simultaneously — instrument and deploy them in waves if cost is a concern — but every service must have its instrumentation committed and its SLO + alert applied.

## What "instrumented" means (the bar)

For each service, all of the following must be true:

1. **Resource correctly set.** Every signal carries `service.name`, `service.version`, and `deployment.environment`. The `service.name` is consistent across traces, metrics, and logs for that service.
2. **Traces.** Incoming requests/messages create a SERVER (or CONSUMER) span; outbound calls create CLIENT (or PRODUCER) spans. Context propagates across service boundaries — a request that crosses two of your services appears as **one** trace, not two. (The Week 09 pipeline must propagate context through the Pub/Sub message attributes; this is the hard one.)
3. **Metrics.** At minimum a request/message counter and a duration histogram, exported to Cloud Monitoring, with bounded-cardinality labels (an `outcome` label is fine; a per-tenant label on a metric is not).
4. **Logs.** Structured logs to stdout (picked up by the platform logging agent) carrying the trace ID and span ID in the `logging.googleapis.com/trace` and `spanId` fields, so Cloud Trace shows the log lines inline on the span.
5. **Export path.** Either SDK-direct to GCP exporters or via an OpenTelemetry Collector (sidecar on Cloud Run, DaemonSet on GKE). The collector path is preferred for the GKE and Cloud Run services; SDK-direct is acceptable for the rest. Document which you used and why.

## What "one SLO per service" means (the bar)

For each service:

1. A `google_monitoring_service` and a `google_monitoring_slo` in Terraform, with a defensible goal and a 28-day rolling window.
2. A **fast-burn page** alert (14.4×, 1h AND 5m, CRITICAL) and a **slow-burn ticket** alert (1×, 3d AND 6h, WARNING). The fast burn routes to a pager-class channel; the slow burn does not.
3. An **error-budget policy** — a short markdown table per service stating what happens at 50/75/90/100% budget consumption. (One shared policy document for the fleet is acceptable if the thresholds are uniform.)

## The validation (the proof)

Pick **one** service — the Week 07 Cloud Run service is the easiest target. Then:

1. Deploy the `FaultInjectionMiddleware` (from Lecture 2) behind a `FAULT_RATE` env var.
2. Drive steady traffic for at least 30 minutes (`hey -z 35m -q 50 <url>/health` or equivalent).
3. Set `FAULT_RATE=0.01` (a 1% error rate = a 10× burn against a 99.9% SLO). Confirm:
   - The 14.4× fast-burn page does **not** fire (10× < 14.4×) — this is correct behavior.
   - The slow-burn ticket fires once its windows fill (10× > 1×).
4. Set `FAULT_RATE=0.02` (a 20× burn). Confirm the 14.4× fast-burn page **fires within a few minutes**.
5. Confirm **no cause alert fired** the whole time — no CPU alert, no memory alert, no restart alert. Only the symptom (error-budget burn) alerted.
6. Set `FAULT_RATE=0.0`. Confirm the fast-burn page **auto-closes** as the short window drops below threshold.
7. **Screenshot** the fired alert, the SLO burn-down chart during the injection, and a trace of a failing request with its correlated error log. These screenshots are the portfolio artifact.

## Acceptance criteria

- [ ] Every Week 06–12 service emits OpenTelemetry traces, metrics, and logs to Cloud Trace + Cloud Monitoring + Cloud Logging.
- [ ] A request that crosses two of your services appears as a single correlated trace (context propagation works, including across the Pub/Sub boundary in the Week 09 pipeline).
- [ ] At least one trace per service shows its log lines inline (trace-log correlation works).
- [ ] Each service has exactly one SLO (Terraform `google_monitoring_slo`) with a defensible goal and a 28-day window.
- [ ] Each service has a fast-burn page (14.4×, two windows, CRITICAL) and a slow-burn ticket (1×, two windows, WARNING) in Terraform.
- [ ] An error-budget policy document exists (per service or one shared table).
- [ ] The 1% injection demonstrably does NOT fire the 14.4× page; the 2% injection demonstrably DOES; no cause alert fired during either; the page auto-closes on recovery.
- [ ] Screenshots of the fired page, the SLO burn-down, and a correlated trace+log are committed.
- [ ] `terraform destroy` cleanly removes the SLOs, alert policies, notification channels, and any sinks. Cloud Profiler agents disabled. (The teardown gate — same as the mini-project.)

## Hints

- **Do the easy services first.** The Week 06 GKE service and Week 07 Cloud Run service are textbook request/response — instrument them with the auto-instrumentors and you are 80% done. Build confidence there, then tackle the pipeline.
- **The pipeline (Week 09) is the hard one.** Context does not propagate through Pub/Sub automatically — you must inject the `traceparent` into the message attributes on publish and extract it on the subscriber side. The OTel `propagate.inject` / `propagate.extract` API plus a `TextMapPropagator` over a dict is the pattern. If you skip this, your pipeline shows up as disconnected single-span traces and you lose the end-to-end view.
- **The edge (Week 08) has no code** — its SLI comes from the LB's `loadbalancing.googleapis.com/https/request_count` metric sliced by `response_code_class`. No instrumentation needed, just the SLO.
- **Reuse the `telemetry.py` bootstrap from Exercise 1** across all the Python services. Reuse the Lecture 2 Terraform SLO+alert module across all services — parameterize `service_name`, `goal`, and the metric filter, and `for_each` over the fleet.
- **Budget your validation window.** The slow-burn windows are 6h and 3d — you will not see the slow-burn ticket fire in a 35-minute test. That is fine; assert its *config* is correct and demonstrate the fast-burn behavior live. Note this honestly in your writeup.
