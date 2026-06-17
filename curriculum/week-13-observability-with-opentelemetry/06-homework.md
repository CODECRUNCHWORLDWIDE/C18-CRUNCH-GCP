# Week 13 Homework

Six problems that revisit the week's topics and include the **PCA / Cloud DevOps Engineer practice-exam diagnostic** (per the syllabus assessment matrix, Week 13 is the diagnostic checkpoint; Week 15 is the readiness gate at ≥70%). The full set should take about **6 hours**. Work in your Week 13 Git repository so each problem produces at least one commit you can point to later.

Each problem includes a **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — Audit and reclassify an alert set

**Problem statement.** Take whatever alerts exist on your Week 06–12 services (console-clicked "CPU > 80%" alerts, default Cloud Run alerts, or — if you have none — invent a realistic set of eight that a hurried team would have created). For each alert, classify it as **symptom** or **cause**, and assign a destination: **page**, **ticket**, or **dashboard**. Produce the audit as a Markdown table at `notes/alert-audit.md`. Then write two sentences: how many of the original alerts should page, and how many actually did before the audit.

**Acceptance criteria.**

- `notes/alert-audit.md` has a table with columns: `Alert`, `Symptom or cause`, `Destination (page/ticket/dashboard)`, `Reason (one line)`.
- At least 8 rows.
- No more than 2–3 alerts end up as `page` (if more, your symptoms are too granular — reconsider).
- The two-sentence summary names the before/after page count.
- File committed.

**Hint.** The Lecture 1 audit table is the template. Anything that is a mechanism (CPU, memory, restarts, queue depth, cert expiry) is a cause; anything users experience (errors, latency, freshness) is a symptom. Causes that auto-heal go to a dashboard; causes that are slow-moving go to a ticket; only symptom + risk + needs-action-now pages.

**Estimated time.** 45 minutes.

---

## Problem 2 — Compute the burn-rate table for your own SLO

**Problem statement.** Pick one real service from your fleet and its SLO goal (e.g. Week 07 Cloud Run at 99.9% / 28 days). Compute, by hand and then verify with a tiny script, the following for that SLO:

1. The error budget (as a fraction and as an allowed number of bad requests, assuming a request volume you state).
2. The allowed total unavailability per 28-day window, in minutes.
3. The burn rate for observed error rates of 0.1%, 0.5%, 1%, 2%, and 5%.
4. For each of those burn rates, the time-to-budget-exhaustion.
5. Which of those rates would fire a 14.4× fast-burn page, a 6× medium-burn page, and a 1× slow-burn ticket.

Write it at `notes/burn-rate-table.md`.

**Acceptance criteria.**

- The error budget, allowed downtime, and a 5-row burn-rate table are present and arithmetically correct.
- `burn_rate = (1 − SLI_observed) / (1 − SLO_target)` is shown explicitly for at least one row.
- The fire/no-fire column is correct against the 14.4× / 6× / 1× thresholds.
- A `notes/burn_rate.py` script reproduces the table (≤ 30 lines).
- Files committed.

**Hint.** `burn_rate = observed_error_rate / error_budget`. Time-to-exhaustion = `window_length / burn_rate`. For 99.9% over 28 days: budget = 0.001, downtime ≈ 40 min, and a 1% rate is a 10× burn (28/10 = 2.8 days to exhaustion).

**Estimated time.** 45 minutes.

---

## Problem 3 — Solve the Pub/Sub trace-propagation problem

**Problem statement.** Context does not propagate across an asynchronous Pub/Sub boundary automatically. Write the publisher and subscriber glue, in Python, that (a) injects the active span's context into the Pub/Sub message attributes on publish, and (b) extracts it on the subscriber to make the consumer span a child of the producer span. Verify in Cloud Trace that a published-then-consumed message is **one** trace, not two. Save the code at `notes/pubsub_propagation.py` and a screenshot of the single trace at `notes/pubsub-trace.png`.

**Acceptance criteria.**

- `notes/pubsub_propagation.py` injects context on publish using `opentelemetry.propagate.inject` into the message attributes, and extracts it on the subscriber with `opentelemetry.propagate.extract`.
- The publish span is `kind=PRODUCER` and the consume span is `kind=CONSUMER`, with the consumer span as a child of the producer span.
- A Cloud Trace screenshot shows one trace spanning publish and consume.
- File and screenshot committed.

**Hint.** `propagate.inject(carrier_dict)` writes the `traceparent` key into your dict; pass that dict as the Pub/Sub message `attributes`. On the other side, `ctx = propagate.extract(message.attributes)` and pass `context=ctx` to `tracer.start_as_current_span(..., context=ctx)`. This is the single hardest instrumentation problem in the whole fleet — solving it here de-risks the challenge and mini-project.

**Estimated time.** 75 minutes.

---

## Problem 4 — Write three error-pattern queries over the BigQuery log sink

**Problem statement.** Using the BigQuery log sink from Exercise 3 (or your mini-project sink), write three distinct SQL queries that each find a different real error pattern:

1. The top error codes by count over the last 24 hours.
2. The error rate per tenant (errors grouped by `jsonPayload.tenant_id`), to find a noisy tenant.
3. The "first seen" timestamp of a specific error code (when did this start?), to correlate with a deploy.

Save them at `notes/error-patterns.sql` with a one-line comment above each explaining what on-call question it answers.

**Acceptance criteria.**

- Three syntactically valid BigQuery Standard SQL queries against the routed-log table (wildcard or partitioned).
- Each query has a one-line purpose comment.
- At least one query uses a `_TABLE_SUFFIX` predicate or a partition filter to scan less (the Week 10 "scan less" discipline applied to logs).
- The output of at least one query is pasted as a comment or saved at `notes/error-query-output.txt`.
- File committed.

**Hint.** Structured fields land under `jsonPayload`. The routed-log tables are date-sharded (`<logid>_YYYYMMDD`); use `FROM \`proj.dataset.logid_*\`` with `WHERE _TABLE_SUFFIX BETWEEN '20260601' AND '20260609'` to bound the scan. `severity = 'ERROR'` is the filter.

**Estimated time.** 45 minutes.

---

## Problem 5 — Read a Cloud Profiler flame graph

**Problem statement.** Enable Cloud Profiler on one compute-heavy service (the Week 09 Beam pipeline or the Week 12 inference service are ideal). Let it run under load for at least 20 minutes. Open the CPU flame graph in the Profiler UI. Identify the single function or operation consuming the largest share of CPU time. Write a 200-word note at `notes/profiler-reading.md` covering: which service, what the hot frame was, what fraction of CPU it consumed, and one concrete hypothesis for reducing it (you do not have to implement the fix — just propose it with reasoning).

**Acceptance criteria.**

- `notes/profiler-reading.md` is 180–220 words and names the specific hot frame and its CPU share.
- A screenshot of the flame graph is committed at `notes/flame-graph.png`.
- The proposed optimization is concrete (names a function, a call, or an allocation), not generic ("make it faster").
- The note confirms Cloud Profiler was disabled afterward (teardown discipline).
- Files committed.

**Hint.** Profiler agents are tiny additions: Python is `import googlecloudprofiler; googlecloudprofiler.start(service='...', service_version='...')`; Go is `profiler.Start(profiler.Config{Service: "...", ServiceVersion: "..."})`. The flame graph's widest frames are where the time goes; read width as "share of CPU," not depth.

**Estimated time.** 45 minutes.

---

## Problem 6 — The PCA / Cloud DevOps Engineer practice-exam diagnostic

**Problem statement.** This is the syllabus's Week 13 diagnostic checkpoint. Sit a full-length practice exam for the **Professional Cloud DevOps Engineer** certification (the observability-heavy one; the PCA practice exam is an acceptable substitute if you prefer the architect track). Use the official exam guide and the free sample questions:

- Cloud DevOps Engineer exam guide: <https://cloud.google.com/learn/certification/cloud-devops-engineer>
- Cloud DevOps Engineer sample questions (official, free): linked from the exam guide page.
- Professional Cloud Architect exam guide (substitute): <https://cloud.google.com/learn/certification/cloud-architect>

Time yourself: ~2 hours, no notes, as if it were the real thing. Score it. Then write a one-page diagnostic note.

**Acceptance criteria.**

- `notes/pca-devops-diagnostic.md` records: which exam you sat, your overall percentage, and a per-domain breakdown (SRE culture & SLOs, service deployment, optimizing performance, managing incidents, monitoring/logging).
- The note names your **two weakest domains** and a concrete plan to close them before the Week 15 readiness gate (specific resources, not "study more").
- An honest reflection on the observability domain specifically: did this week's work make it your strongest section? If not, why?
- This is a **diagnostic, not a gate** — any score passes the homework as long as the note is honest and the plan is concrete. The gate is Week 15 (≥70%).
- File committed.

**Hint.** Do not study right before sitting it — the point of a diagnostic is to measure where you are *now*, with two weeks of runway. The observability domain (SLIs/SLOs/error budgets/golden signals/burn rate) should be your strongest after this week; if it is not, that is the most important signal the diagnostic gives you.

**Estimated time.** 2 hours 15 minutes (the exam plus the note).

---

## Submission

Push the entire `notes/` directory and any code to your Week 13 Git repository. The instructor reviews by:

1. Reading each note and checking the audit/burn-rate arithmetic.
2. Re-running the Pub/Sub propagation code and confirming a single trace in Cloud Trace.
3. Running the SQL queries against your sink and confirming they return.
4. Reading the diagnostic note for honesty and a concrete plan.

A submission whose notes are present, whose arithmetic is correct, and whose Pub/Sub trace is genuinely one trace is a pass. The most common review-fail is Problem 3 — a "single trace" that is actually two because the context was injected but never extracted (or extracted but not passed as `context=` to the span). Double-check it shows one trace before submitting.

If anything is unclear, post in the Week 13 channel before the deadline.

---

**References**

- The Site Reliability Workbook — "Alerting on SLOs": <https://sre.google/workbook/alerting-on-slos/>
- Google Cloud — "Define SLOs": <https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring>
- OpenTelemetry — context propagation: <https://opentelemetry.io/docs/concepts/context-propagation/>
- Cloud Logging — view logs routed to BigQuery: <https://cloud.google.com/logging/docs/export/bigquery>
- Cloud Profiler — concepts: <https://cloud.google.com/profiler/docs/concepts-profiling>
- Cloud DevOps Engineer certification: <https://cloud.google.com/learn/certification/cloud-devops-engineer>
