# Mini-Project — Fleet-Wide Observability: instrument Weeks 06–12, one SLO each, and the portfolio writeup

> Take every service you built in Weeks 06–12 and make it observable end to end with OpenTelemetry: traces to Cloud Trace, metrics to Cloud Monitoring, logs to Cloud Logging with a sink to BigQuery, one SLO and a multi-window burn-rate alert per service, Cloud Profiler on the two heaviest services, and a 1% fault-injection validation that pages the right alert. Then write the portfolio-grade observability document the syllabus names as one of three C18 portfolio artifacts. This is **not** a new system — it extends every prior service rather than starting fresh. It is also the diagnostic checkpoint for the PCA / Cloud DevOps practice exam, and it has a hard teardown gate.

This is the Phase 4 mini-project that turns "I deployed it" into "I can run it on call." Real platform teams spend a large fraction of their effort exactly here: not building features, but making the system legible — so that when it misbehaves at 03:00, the on-call engineer can answer "is the promise being kept, and if not, why" in two minutes instead of two hours. By the end you have a fully instrumented fleet, a tested alert set that pages only on user-visible risk, and a writeup good enough to put in front of a hiring manager.

**Estimated time:** ~9 hours (split across Friday, Saturday, and Sunday in the suggested schedule). The challenge is the first 60% of this; if you did the challenge well, this is instrumentation polish + the writeup + the diagnostic + teardown.

**This compounds.** Per the syllabus, the mini-projects compound — by Week 10 you were extending Week 06's cluster, not starting fresh. Week 13 is the most compounding week of all: it touches *every* service from Weeks 06–12 simultaneously. Do not rebuild anything. Instrument what exists. The capstone (Week 15) then requires every service in the realtime event pipeline to ship with exactly this observability, so the work you do here is capstone work banked early.

---

## What you will build

A single observability layer over the existing fleet, delivered as:

1. **A reusable instrumentation library.** One `telemetry.py` (Python) and one `telemetry.go` (Go) bootstrap, copied into / imported by every service, that sets the `Resource`, wires the `TracerProvider` / `MeterProvider` / `LoggerProvider`, and points them at the OpenTelemetry Collector via OTLP.
2. **An OpenTelemetry Collector deployment.** A sidecar on the Cloud Run services, a DaemonSet on the GKE cluster, both running the `googlecloud` exporter. Fleet-wide sampling and batching policy lives here, not in the services.
3. **Instrumented services, Weeks 06–12.** Every service emits correlated traces, metrics, and logs. A request that crosses two services is one trace. Logs carry trace/span IDs.
4. **A Terraform SLO module.** One reusable module (`modules/slo-with-burn-rate/`) that takes a `service_name`, an SLI filter, a `goal`, and notification channels, and produces a `google_monitoring_service`, a `google_monitoring_slo`, a fast-burn page policy, and a slow-burn ticket policy. Instantiated once per service via `for_each`.
5. **A BigQuery log sink.** A `google_logging_project_sink` routing `severity>=ERROR` (and your structured app errors) to a partitioned BigQuery dataset, plus a Pub/Sub sink stub for the SIEM path and a GCS sink for cold archive. With at least three SQL queries that find real error patterns in the landed logs.
6. **Cloud Profiler** on the two most compute-heavy services (your call — typically the Week 09 Beam pipeline and the Week 12 inference service). A before/after flame-graph comparison if you optimize anything.
7. **The validation run.** The 1% fault injection on one service, with the right alert paging and the cause alerts silent, screenshotted.
8. **The portfolio writeup** (`OBSERVABILITY.md`) — the headline deliverable. See its spec below.

You ship **one repository** layered over your existing week repos (or a new `week-13-observability/` repo that references them):

```
week-13-observability/
  telemetry/
    telemetry.py                 # Python bootstrap (reused by 06,07,09,10,12)
    telemetry.go                 # Go bootstrap (reused by 11)
  collector/
    otel-collector-config.yaml   # receivers/processors/exporters
    cloudrun-sidecar.yaml        # sidecar spec
    gke-daemonset.yaml           # DaemonSet spec
  terraform/
    modules/slo-with-burn-rate/  # the reusable SLO+alert module
    fleet.tf                     # for_each over the 7 services
    log-sinks.tf                 # BigQuery + Pub/Sub + GCS sinks
    notification-channels.tf
    profiler.tf                  # enable + agent config notes
  queries/
    error-patterns.sql           # >= 3 queries over the BigQuery log sink
  validation/
    fault_injection.py           # the middleware
    run-validation.sh            # the injection + traffic script
    screenshots/                 # the proof
  error-budget-policy.md         # what happens at each consumption level
  OBSERVABILITY.md               # the portfolio writeup (headline deliverable)
  TEARDOWN.md                    # the teardown checklist + verification
```

---

## Rules

- **You may** read all the OTel docs, the Google SRE books, the GCP docs, your lecture notes, your exercises, and the provider docs. You may reuse the Exercise 1 `telemetry.py`, the Exercise 2 Terraform, and the Lecture 2 module skeleton verbatim — that is the point of building them.
- **You may NOT** start any service fresh. This project instruments the services that already exist. If a service is broken, fix the service first (that is Week 06–12 debt, not Week 13 work) — but do not rewrite it.
- **You may NOT** put a high-cardinality dimension (tenant ID, user ID, request ID) on a *metric* label. Those belong on traces and logs. A reviewer will check your metric cardinality; a per-tenant metric label is an automatic performance-section fail.
- **You may NOT** create an SLO with a goal of 100%. Defend every goal you pick in the writeup.
- **You may NOT** route the slow-burn alert to the pager. A slow burn is a ticket. Routing it to the pager fails the alert-hygiene criterion.
- The instrumentation must be **vendor-neutral OTel**, not the Cloud Trace SDK directly. The exit (swap the collector exporter to point at OSS backends) must be a config change, and you must state it in the writeup.

---

## Acceptance criteria

The grading rubric is below. Each box maps to a specific deliverable.

### Instrumentation (30%)

- [ ] A reusable `telemetry.py` and `telemetry.go` exist and are imported by the services (not copy-pasted-and-diverged).
- [ ] Every Week 06–12 service emits traces, metrics, and logs with a consistent `service.name` across all three signals.
- [ ] Context propagates across service boundaries: a multi-service request is one trace. **Including** through the Week 09 Pub/Sub boundary (the hard one — `traceparent` in message attributes).
- [ ] Trace-log correlation works: at least one trace per service shows its log lines inline in Cloud Trace.
- [ ] An OpenTelemetry Collector is deployed (sidecar on Cloud Run, DaemonSet on GKE) and the services export OTLP to it; the collector exports to GCP via the `googlecloud` exporter.
- [ ] Metric cardinality is bounded (no per-tenant/per-user metric labels).

### SLOs and burn-rate alerts (30%)

- [ ] A reusable `modules/slo-with-burn-rate/` Terraform module exists and is instantiated once per service via `for_each`.
- [ ] Each of the 7 services has exactly one SLO with a defensible, non-100% goal and a 28-day rolling window.
- [ ] Each service has a fast-burn page (14.4×, 1h AND 5m, CRITICAL → pager) and a slow-burn ticket (1×, 3d AND 6h, WARNING → ticket).
- [ ] `error-budget-policy.md` states the action at 50/75/90/100% consumption.
- [ ] `terraform apply` creates all SLOs and policies cleanly; `terraform plan` is empty on re-run (no drift).

### Logging and profiling (15%)

- [ ] A BigQuery log sink exists (`google_logging_project_sink`) with a correct writer-identity IAM grant, routing errors to a partitioned dataset.
- [ ] A Pub/Sub sink and a GCS sink exist (the SIEM and cold-archive paths) — stubs are acceptable but must be real, correctly-configured resources.
- [ ] `queries/error-patterns.sql` has ≥ 3 SQL queries that find real error patterns in the landed logs, and the writeup shows the output of at least one.
- [ ] Cloud Profiler is enabled on ≥ 2 services and the writeup includes a flame-graph reading (what the hot path was).

### Validation (15%)

- [ ] `validation/run-validation.sh` drives traffic and toggles `FAULT_RATE`.
- [ ] Screenshots prove: (a) the 1% injection does NOT fire the 14.4× page, (b) the 2% injection DOES, (c) no cause alert fired, (d) the page auto-closed on recovery.
- [ ] A screenshot of a failing trace with its correlated error log.
- [ ] A screenshot of the SLO burn-down chart during the injection.

### Writeup (10%)

- [ ] `OBSERVABILITY.md` meets the spec below (it is the portfolio artifact).

---

## The portfolio writeup (`OBSERVABILITY.md`)

This is the headline deliverable and the thing a hiring manager actually reads. It is the syllabus's named portfolio piece: *"how I instrumented service X with OpenTelemetry and what the burn-rate alert caught."* Write it like a senior engineer's blog post, not a lab report. It must contain:

1. **The system in one diagram.** A Mermaid diagram of the fleet with the observability overlay: where the collector sits, where signals flow, where the SLOs are.
2. **The instrumentation decisions.** SDK-direct vs. collector and why. Which signals you put where. The one trace-propagation problem you had to solve (almost certainly the Pub/Sub boundary) and how.
3. **The SLO table.** Every service, its SLI, its goal, and a one-sentence justification of the goal. Why is the edge 99.95% but the Vertex endpoint 99.5%?
4. **The alert design.** Why multi-window burn-rate and not static thresholds. The fast/slow split. One worked burn-rate calculation (e.g. "1% errors against 99.9% = 10× burn = budget gone in 2.8 days").
5. **What the validation caught.** The 1% vs 2% injection result, with the screenshots. The honest note about not being able to observe the slow-burn fire in a 35-minute window.
6. **The exit plan, in miniature.** One paragraph: what it takes to move off Cloud Trace/Monitoring/Logging to Grafana Tempo + Prometheus + Loki. (Answer: change the collector's exporter block; the services do not change. That is the OTel payoff.)
7. **What you would do next.** Exemplars, log-based SLIs, per-tenant SLOs as a deliberate design, a gateway collector. One paragraph of honest "not done yet."

Target 1,200–2,000 words. Code snippets and the diagram are encouraged. This document, the capstone, and the Week 04 module library are the three portfolio artifacts C18 is designed to produce — make this one good.

---

## The PCA / Cloud DevOps practice-exam diagnostic

Per the syllabus assessment matrix, Week 13 is the **diagnostic** checkpoint for the Google Professional Cloud Architect / Professional Cloud DevOps Engineer practice exam (Week 15 is the readiness gate at ≥70%). Take the diagnostic *after* you finish the instrumentation and SLOs, while the material is fresh:

1. Sit a full-length practice exam for the **Professional Cloud DevOps Engineer** (the observability-heavy one). The official exam guide and a free sample are linked in `homework.md`. Time yourself: 2 hours, no notes.
2. Score it. Record your percentage and, more importantly, your **per-domain breakdown** — the DevOps exam domains are roughly: SRE culture & SLOs, service deployment, optimizing performance, managing incidents, and monitoring/logging. The observability domain you just practiced should be your strongest.
3. Write a one-page **diagnostic note** (in `homework.md`'s deliverable) listing your two weakest domains and your plan to close them before the Week 15 readiness gate. This is a diagnostic, not a gate — a low score here is information, not a failure. The point is to find the gaps with two weeks of runway left.

---

## Teardown gate

**This week leaks quietly if you forget it.** Observability resources are cheap to create and easy to leave running. Run `TEARDOWN.md` and verify each line:

- [ ] `terraform destroy` on the `terraform/` directory — removes SLOs, alert policies, notification channels, and the three log sinks.
- [ ] **Confirm the sinks are gone** (`gcloud logging sinks list`) — a forgotten BigQuery sink keeps ingesting every log line and billing storage.
- [ ] **Drop the BigQuery log dataset** if `terraform destroy` did not (datasets with data sometimes need `delete_contents`).
- [ ] **Disable the Cloud Profiler agents** — set the agent env vars off / remove the agent from the container, and confirm no service is still profiling.
- [ ] **Delete the GCS archive bucket** the sink wrote to (it accrues storage).
- [ ] **Stop the load generator** from the validation run.
- [ ] **Verify no alert policy still has a live notification channel** pointed at your phone — a leftover policy on a deleted service will not fire, but a leftover channel is clutter.
- [ ] Run `gcloud monitoring policies list` and `gcloud monitoring channels list` and confirm they are empty (or down to only what you intend to keep).

Skipping the teardown gate fails the week. The capstone reuses all of this anyway, from Terraform — so a clean teardown costs you nothing and a forgotten sink costs you real money over the remaining weeks.

---

## Suggested order of work

1. **Friday (3h):** Stand up the collector. Wire `telemetry.py`/`telemetry.go` into the two easiest services (Week 06 GKE, Week 07 Cloud Run). Confirm traces + metrics + logs land and correlate. Build the `slo-with-burn-rate` module and apply it to those two services.
2. **Saturday (3h):** Instrument the rest of the fleet, including the Pub/Sub propagation for Week 09. Apply the SLO module to all 7 via `for_each`. Stand up the BigQuery log sink and write the queries. Enable Profiler on two services. Run the 1% / 2% validation and capture screenshots.
3. **Sunday (3h):** Write `OBSERVABILITY.md`. Sit the PCA/DevOps practice diagnostic and write the diagnostic note. Run the teardown gate and verify every line. Take the quiz.

If you run short on time, the priority order is: instrumentation + SLOs (60% of the grade) → validation (15%) → writeup (10%) → logging/profiling (15%). A fully instrumented fleet with validated alerts and a thin writeup beats a beautiful writeup over a half-instrumented fleet.
