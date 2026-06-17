# Week 11 Homework

Six practice problems that revisit the week's topics. The full set should take about **5 hours**. Work in your Week 11 Git repository so each problem produces at least one commit you can point to later.

Each problem includes a short **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**. Two of the six touch real cloud resources and cost a small amount — they carry a teardown line you must honor.

---

## Problem 1 — Read the Spanner paper's TrueTime section and diagram the commit-wait

**Problem statement.** Open the Spanner OSDI 2012 paper (<https://research.google/pubs/spanner-googles-globally-distributed-database/>) and read §3 (TrueTime) and the commit-wait discussion in §4. Save a note at `notes/truetime.md` (200–250 words) that:

1. States what `TT.now()` returns and what the `ε` (epsilon) represents.
2. Explains, in your own words, why waiting out `2ε` on commit guarantees that timestamp order matches real-time order globally.
3. Includes an ASCII or Mermaid diagram of the commit-wait timeline (pick-timestamp → Paxos write → wait → release locks).

**Acceptance criteria.**

- `notes/truetime.md` exists, is 200–250 words, and correctly names `TT.now()` returning an interval `[earliest, latest]`.
- The note explains the commit-wait in terms of the bounded uncertainty, not hand-waving.
- A diagram of the timeline is present.
- File is committed.

**Hint.** The key sentence in the paper is that Spanner picks `s = TT.now().latest` and waits until `TT.after(s)`. Lecture 2 §2.3 has the diagram you should reproduce in your own words.

**Estimated time.** 40 minutes.

---

## Problem 2 — Score five workloads on the decision rubric

**Problem statement.** Extend the Exercise 3 decision engine with **five new workloads** drawn from systems you have actually seen or can describe concretely (a social app feed, a global session store, an IoT telemetry sink, an internal BI dashboard backend, a multi-tenant billing ledger, etc.). For each, fill in the seven axes and run `decide()`. Then, for each, write the one-sentence justification by hand and compare it to what the engine produced.

**Acceptance criteria.**

- `notes/five-workloads.py` (or an extension of the Exercise 3 file) defines five new `Workload` instances with realistic axis values.
- Running it prints five decisions; each names a deciding axis and a runner-up.
- `notes/five-workloads.md` contains your hand-written one-sentence justification for each, and a note on any case where you *disagreed* with the engine (the engine is a starting point, not an oracle — disagreement is fine if you explain it).
- At least one workload resolves to each of Cloud SQL, AlloyDB, and Spanner across the five.

**Hint.** If all five resolve to the same database, your workloads are too similar — deliberately vary the multi-region-strong and horizontal-write-scale flags, since those are the only two that unlock Spanner.

**Estimated time.** 50 minutes.

---

## Problem 3 — Cost a Spanner workload three ways

**Problem statement.** Using the GCP pricing calculator (<https://cloud.google.com/products/calculator>), produce a cost comparison for a single workload (10,000 writes/sec peak, 500 GB, US-only) across three configurations:

1. A `db-custom-8-32768` Cloud SQL regional HA instance + one read replica.
2. An AlloyDB cluster (primary + a 2-node read pool).
3. A single-region Spanner instance sized to sustain the write rate (estimate the processing units; the docs give a rough writes/sec-per-node figure).

Write the comparison at `notes/cost-comparison.md` as a table (monthly cost for each) plus a paragraph naming which you would choose for this workload and why.

**Acceptance criteria.**

- `notes/cost-comparison.md` has a three-row cost table with monthly figures from the calculator.
- The Spanner sizing shows your reasoning (writes/sec ÷ per-node throughput → node/PU count).
- A paragraph picks one option and names the deciding factor. (For a US-only single-region workload at this scale, the honest answer is usually Cloud SQL or AlloyDB unless write scale genuinely exceeds one machine — defend whatever you conclude.)

**Hint.** Spanner's docs quote rough throughput per node; a single regional node sustains thousands of writes/sec. 10,000 writes/sec may or may not need more than one node — show the arithmetic.

**Estimated time.** 45 minutes.

---

## Problem 4 — Build and tear down a Spanner instance, measure the write latency

**Problem statement.** Run Exercise 2's script (or your own) to create a 100-PU single-region Spanner instance. Before tearing it down, write a small script that times 100 single-row inserts and reports the median latency. Then tear the instance down. Save the number and a one-paragraph interpretation (the few-millisecond floor is the commit-wait from Lecture 2) at `notes/write-latency.md`.

> **Teardown line:** this problem creates a billable Spanner instance. Tear it down in the same sitting. End with `gcloud spanner instances list` returning empty and paste that output into the note.

**Acceptance criteria.**

- `notes/write-latency.md` reports a median single-row insert latency (a real number from your run).
- The interpretation connects the floor to the TrueTime commit-wait.
- The note includes the `gcloud spanner instances list` output showing the instance is gone.
- Total Spanner runtime was under one hour (state the elapsed time).

**Hint.** Use `database.run_in_transaction` for each insert and time it with `time.monotonic()`. Expect a single-digit-to-low-double-digit-millisecond median; if it is huge, your client is not in the same region as the instance.

**Estimated time.** 50 minutes.

---

## Problem 5 — Write the exit plan for the mini-project service

**Problem statement.** For the "current-state" service (mini-project), write the four-part exit plan from Lecture 2 §2.7 at `notes/exit-plan.md`. Assume the service is on Spanner (post-migration) and the target is CockroachDB self-hosted on GKE. Cover: schema lift, application lift, operational lift, and a verdict with an explicit trigger condition.

**Acceptance criteria.**

- `notes/exit-plan.md` has all four parts clearly labeled.
- The schema-lift section addresses how the interleaved/UUID schema ports to CockroachDB.
- The operational-lift section gives an honest FTE estimate (0.5–1.5) for self-hosting.
- The verdict names a *trigger* — a specific condition under which you would revisit the decision (e.g., "if we hire a database-SRE team" or "if a sovereignty requirement forces multi-cloud").

**Hint.** The worked example in Lecture 2 §2.7 is the template. The failing version is "we could move if we had to" — yours must have numbers and a trigger.

**Estimated time.** 40 minutes.

---

## Problem 6 — Firestore vs Bigtable decision memo

**Problem statement.** You are designing two features: (a) a real-time collaborative document editor's presence/cursor state, and (b) an IoT fleet's per-device telemetry at 50,000 writes/sec. Write a one-page memo at `notes/firestore-vs-bigtable.md` choosing Firestore or Bigtable for *each*, with the deciding factor and the rejected alternative named.

**Acceptance criteria.**

- `notes/firestore-vs-bigtable.md` makes a clear choice for each feature.
- The collaborative-editor feature picks Firestore (real-time listeners, strong consistency, document model) — or argues a defensible alternative.
- The telemetry feature picks Bigtable (wide-column, high write throughput, row-key design) — or argues a defensible alternative.
- Each choice names the deciding factor and the rejected alternative in one sentence.
- The memo notes whether Memorystore belongs in front of either (it does, for the editor's hot presence reads).

**Hint.** The deciding axes are: does it need real-time listeners and strong consistency (Firestore), or sustained high write throughput with single-digit-ms reads at scale and a known access pattern (Bigtable)? Row-key design vs document model is the tell.

**Estimated time.** 35 minutes.

---

## Submission

Push the entire `notes/` directory and any scripts to your Week 11 Git repository. The instructor reviews by:

1. Reading each note in `notes/`.
2. Re-running any scripts attached (Problems 2 and 4) and verifying the numbers are plausible.
3. Cross-checking the cited URLs are real and the claims are consistent with the source.
4. **Confirming Problem 4's teardown evidence is present** — a note that reports a Spanner write latency but no teardown output means an instance may still be billing.

A submission whose notes are present, whose scripts run, and whose Problem 4 shows the instance torn down is a pass. The most common review-fail this week is missing teardown evidence; the second is an exit plan with no trigger condition. Check both before submitting.

---

**References**

- Spanner OSDI 2012 paper: <https://research.google/pubs/spanner-googles-globally-distributed-database/>
- Spanner — compute capacity and throughput: <https://cloud.google.com/spanner/docs/compute-capacity>
- GCP pricing calculator: <https://cloud.google.com/products/calculator>
- CockroachDB — "Living Without Atomic Clocks": <https://www.cockroachlabs.com/blog/living-without-atomic-clocks/>
- Firestore vs Bigtable — Google's database decision guide: <https://cloud.google.com/architecture/db-and-storage>
- Spanner — Python client: <https://cloud.google.com/python/docs/reference/spanner/latest>
