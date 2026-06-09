# Week 13 — Quiz

Thirteen questions on alert hygiene, the golden signals, the OpenTelemetry data model, SLOs, error budgets, burn-rate alerting, and log sinks. Take it with your lecture notes closed. Aim for 11/13 before the Week 15 readiness gate — this material is the heaviest-weighted domain on the Cloud DevOps Engineer exam. Answer key at the bottom; don't peek.

---

**Q1.** Which of the following conditions best satisfies the alert-hygiene rule "page only on user-visible risk that needs human action now"?

- A) CPU utilization on a GKE node pool exceeds 85% for 5 minutes.
- B) A pod in the deployment restarted.
- C) The service's error-budget burn rate over 1h AND 5m both exceed 14.4×.
- D) A TLS certificate expires in 14 days.

---

**Q2.** Your team alerts on "memory > 90%" because "we want to catch the OOM before it happens." This is an example of:

- A) A symptom alert — memory pressure is what users experience.
- B) A cause alert — memory is a mechanism that *may* produce a user-visible symptom but usually does not. It belongs on a dashboard, not a pager, unless it is a tight leading indicator.
- C) A burn-rate alert.
- D) A correctly-designed golden-signal alert for saturation.

---

**Q3.** Of the four golden signals, which one is most often a *cause* rather than a *symptom*, and therefore belongs primarily on a dashboard rather than a pager?

- A) Latency.
- B) Traffic.
- C) Errors.
- D) Saturation.

---

**Q4.** In OpenTelemetry, what is the single most important resource attribute, because Cloud Trace, Cloud Monitoring, and your SLOs all group telemetry by it?

- A) `deployment.environment`
- B) `service.version`
- C) `service.name`
- D) `cloud.region`

---

**Q5.** A request flows through `ingest-api` and then `enrich-service`, but in Cloud Trace you see two separate single-service traces instead of one. What is the most likely cause?

- A) The two services use different OTel SDK versions.
- B) Context is not propagating across the service boundary — the caller is not injecting the W3C `traceparent` header (or the callee is not extracting it). One trace requires propagated context.
- C) Cloud Trace cannot display multi-service traces.
- D) The `service.name` is the same on both services, which splits the trace.

---

**Q6.** You want per-request percentile latency in Cloud Monitoring. Which OpenTelemetry instrument do you use?

- A) A Counter.
- B) An UpDownCounter.
- C) A Histogram (exported as a distribution metric, from which you read percentiles).
- D) An observable Gauge.

---

**Q7.** Why is putting `tenant.id` (50,000 distinct values) on a *metric* attribute a mistake, while putting it on a *span* attribute is fine?

- A) Spans cannot hold string attributes; metrics can.
- B) Metric attributes create a separate time series per distinct value (a cardinality explosion that is expensive and slow in Cloud Monitoring). Spans are not aggregated into time series, so high-cardinality attributes are cheap on them and useful for filtering individual traces.
- C) There is no difference; both are fine.
- D) `tenant.id` is reserved and cannot be used as a metric label.

---

**Q8.** A 99.9% SLO over a 28-day rolling window allows approximately how much total unavailability per window?

- A) ~4 minutes.
- B) ~40 minutes.
- C) ~3 hours 22 minutes.
- D) ~6 hours 43 minutes.

---

**Q9.** Your SLO is 99.9% (error budget 0.1%). You observe a sustained 1% error rate. What is the burn rate, and roughly how long until the 28-day budget is exhausted at that rate?

- A) 1× burn; ~28 days.
- B) 10× burn; ~2.8 days.
- C) 0.1× burn; never.
- D) 100× burn; ~7 hours.

---

**Q10.** In a multi-window burn-rate alert, the policy combines a long window (e.g. 1h) and a short window (e.g. 5m) with `combiner = "AND"`. What does the short window accomplish?

- A) It makes the alert fire faster on the first error.
- B) It confirms the burn is *still happening* — if the incident already recovered, the short window has dropped below threshold and the alert does not fire (or auto-closes), preventing a page for a recovered incident.
- C) It raises the severity from WARNING to CRITICAL.
- D) It is redundant; one window is always sufficient.

---

**Q11.** Why does the standard burn-rate alerting pattern route the slow-burn (1× over 3 days) condition to a *ticket* rather than a *page*?

- A) Slow burns are not real problems.
- B) A 1× burn means the budget will last roughly the full window — it is a real leak but not "needs human action *now*," so per the alert-hygiene rule it is a ticket to fix in business hours, not a 03:00 page.
- C) Cloud Monitoring cannot page on the slow-burn condition.
- D) Slow burns always self-heal.

---

**Q12.** You create a Cloud Logging sink to a BigQuery dataset. Logs are being generated that match the sink filter, but nothing appears in BigQuery. What is the most likely cause?

- A) BigQuery does not support log sinks.
- B) The sink's writer-identity service account was not granted write access (e.g. `roles/bigquery.dataEditor`) on the dataset, so the log router silently drops every routed entry.
- C) The filter is wrong; sinks ignore the filter.
- D) Logs always take 24 hours to appear in BigQuery.

---

**Q13.** Trace-log correlation in GCP requires the log entry to carry the trace ID in which field, in which exact format?

- A) `trace_id`, as a raw 128-bit integer.
- B) `logging.googleapis.com/trace`, as the full resource path `projects/PROJECT_ID/traces/TRACE_ID` where `TRACE_ID` is the 32-char hex trace ID.
- C) `otel.trace`, as a base64 string.
- D) Any field named `trace`; Cloud Logging auto-detects the format.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **C** — The burn-rate condition over two windows is the canonical symptom alert: user-visible (the error budget is being spent), risk (fast burn), needs action now (budget gone in ~2 days). A, B, and D are causes or slow-moving — dashboard or ticket, not a page.

2. **B** — Memory is a cause: a mechanism that may produce a user-visible symptom but usually does not (services run hot and serve fine). It belongs on a dashboard. You page on the *symptom* (errors/latency burning the budget), and use memory as a diagnostic signal when a symptom alert fires. The principled exception — a tight leading indicator with too-short lead time — is rare and must be justified.

3. **D** — Saturation. Latency, traffic, and errors are what users experience (symptoms — page on them). Saturation (CPU, memory, queue depth) is usually a mechanism that *may* lead to a symptom — graph it, and page only when it is a true leading indicator or itself user-visible (e.g. a full queue dropping events).

4. **C** — `service.name`. It is the key by which all three signals are grouped, and the unit an SLO is defined over. Inconsistent `service.name` across signals is the most common reason correlation breaks. Set it once in the `Resource`.

5. **B** — Context propagation is broken. One trace across two services requires the caller to inject the W3C `traceparent` (the OTel HTTP instrumentation does this automatically) and the callee to extract it. If either side drops it, you get two disconnected traces. Option D is backwards — a *consistent* `service.name` is correct; it does not split traces (the trace ID does the linking, set per-request, not per-service).

6. **C** — A Histogram. Counters and UpDownCounters give you sums/rates, not distributions; gauges give you a sampled point value. Only a Histogram (exported as a Cloud Monitoring distribution metric) lets you read p95/p99. In 2026 the default is the exponential histogram, which gives accurate percentiles without pre-chosen buckets.

7. **B** — Metric attributes multiply into separate time series; 50,000 tenant values = 50,000 time series per metric, which is expensive and slow in Cloud Monitoring (and bills you for it). Spans are not aggregated into time series, so a high-cardinality attribute on a span is cheap and is exactly what you want for filtering individual traces. Put identifiers on traces/logs, bounded dimensions on metrics.

8. **B** — ~40 minutes (≈40m 19s). 0.1% of 28 days ≈ 40 minutes. Memorize the 99.9% row: three nines buys you about forty minutes of total unavailability every four weeks. (Option C is the 99.5% figure; D is roughly 99%; A is 99.99%.)

9. **B** — burn_rate = (1 − SLI) / (1 − SLO) = 0.01 / 0.001 = **10×**. At 10× you exhaust 28 days of budget in 28/10 = 2.8 days. This is precisely why the mini-project injects 1%: it is a clean 10× burn, above the slow-burn threshold and below the 14.4× fast-burn threshold, so you can observe the alerting boundary.

10. **B** — The short window confirms the burn is *still happening*. With `combiner = "AND"`, both the long and short conditions must be true to fire; once the incident recovers, the short window drops below threshold and the alert does not fire / auto-closes. This is the mechanism that stops you paging for an incident that already healed — the most common false page.

11. **B** — A 1× burn means you are spending the budget at exactly the rate that lasts the whole window: a real but slow leak. Per the alert-hygiene rule, it is user-visible *risk* but does not need human action *now* — so it is a ticket to fix in business hours, not a 03:00 page. Routing it to the pager reintroduces alert fatigue.

12. **B** — The log router writes to the destination as the sink's *writer-identity* service account, which is created when the sink is created (with `unique_writer_identity`). If you do not grant that SA write access on the BigQuery dataset (or the Pub/Sub topic, or the GCS bucket), the router silently drops everything. This is the #1 "my sink does nothing" bug and the reason Exercise 3 grants `dataEditor` explicitly.

13. **B** — The field is `logging.googleapis.com/trace` and the value must be the full resource path `projects/PROJECT_ID/traces/TRACE_ID`, with `TRACE_ID` the 32-character lowercase hex trace ID. The span ID goes in `logging.googleapis.com/spanId` as 16-char hex. Get the format wrong and Cloud Logging stores the field but never links it to the trace, leaving you with two disconnected datasets.

</details>

---

If you scored under 9, re-read the lectures for the questions you missed — especially the burn-rate arithmetic (Q9) and the symptom/cause distinction (Q1–Q3), which are the exam's heaviest topics. If you scored 12 or 13, you are ready for the PCA/DevOps diagnostic in the homework.
