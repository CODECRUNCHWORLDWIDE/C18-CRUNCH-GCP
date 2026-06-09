# Week 12 Homework

Five practice problems that revisit the week's topics. The full set should take about **5 hours**. Work in your Week 12 Git repository so each problem produces at least one commit you can point to later.

Each problem includes a **problem statement**, **deliverables**, **acceptance criteria**, a **hint**, and an **estimated time**.

A note on cost: Problems 1, 2, and 5 cost nothing (reading, SQL over the free tier, and Python math). Problems 3 and 4 touch GPU-backed resources — do them in a focused block and tear down the same session.

---

## Problem 1 — Compute the crossover duty cycle for three workloads

**Problem statement.** Using the `cost_model.py` harness from Lecture 2, compute the crossover duty cycle (the GPU utilization above which a self-hosted/endpoint node-hour bargain beats the per-token Gemini bargain) for three workloads, with current prices you look up on the live Vertex AI pricing page:

1. A small-output classifier: 400 input tokens, 20 output tokens per request.
2. A summarizer: 2,000 input tokens, 500 output tokens per request.
3. A long-form generator: 200 input tokens, 2,000 output tokens per request.

For each, assume an L4 endpoint at the current node-hour rate and a measured sustained throughput of 1,000 output tokens/second.

**Deliverables.** A `notes/crossover.md` with a small table (workload, input/output tokens, crossover duty cycle) and a two-sentence interpretation: which workload shape most favors building your own endpoint, and why.

**Acceptance criteria.**

- The three crossover numbers are computed with `crossover_duty_cycle`, not estimated.
- The prices used are dated and cited from the live pricing page (prices change).
- The interpretation correctly identifies that **output-heavy** workloads favor self-hosting (the node-hour cost is amortized over many output tokens; the per-token API charges the high output rate per token).
- File committed.

**Hint.** Output-heavy workloads pay the per-token API's expensive *output* rate on every token, which is where self-hosting's amortization bites hardest. Input-heavy workloads pay the cheap input rate, so the per-token API stays competitive longer.

**Estimated time.** 45 minutes.

---

## Problem 2 — Run the sovereignty checklist for a real workload

**Problem statement.** Pick a workload from your own work or invent a realistic one (e.g., "summarize customer support tickets that contain names and account numbers, for a company under EU data-residency obligations"). Run the six-question sovereignty checklist from Lecture 2 §2.5 against all three serving options (Vertex Endpoint, Gemini-on-Vertex, vLLM-on-GKE) and the public AI Studio Gemini API.

**Deliverables.** A `notes/sovereignty.md` with a 4×6 table (four options × six checklist questions) filled in with yes/no/conditional answers, and a one-paragraph conclusion stating which options survive the sieve for your workload.

**Acceptance criteria.**

- All four options are assessed against all six questions.
- The data-governance row (question 4) cites the *specific* terms document for each surface, not a paraphrase.
- The version-pinning row (question 5) correctly distinguishes open weights (pinnable) from closed models (deprecated on a schedule).
- The conclusion correctly eliminates the public AI Studio path for any workload with a VPC-egress or residency constraint.
- File committed.

**Hint.** The enterprise Vertex AI data-governance terms and the consumer AI Studio terms differ — link both. The distinction is the one your auditor cares about most.

**Estimated time.** 45 minutes.

---

## Problem 3 — Benchmark the endpoint's cold-start p99

**Problem statement.** Re-deploy your Exercise 1 endpoint, but with `min_replica_count=0` if your serving container supports scale-to-zero (otherwise `min_replica_count=1` and a long idle period). Drive a benchmark run that includes the *first* request after a quiet period, and measure how the cold-start request's latency compares to the steady-state p50. Then re-deploy at `min_replica_count=1` and confirm the cold-start tail disappears.

**Deliverables.** A `notes/cold-start.md` with: the cold-start request latency, the steady-state p50/p99 at `min=1`, and a two-sentence explanation of the price↔latency trade you just measured (a warm replica costs idle node-hours but removes the cold-start tail).

**Acceptance criteria.**

- The cold-start latency is reported as a distinct number, not folded into the steady-state percentiles.
- The steady-state p50/p99 at `min_replica_count=1` is reported.
- The explanation correctly frames `min_replica_count` as buying down the cold-start p99 with idle cost.
- **The endpoint is torn down** and the receipt is clean.

**Hint.** A 9B model loads to GPU memory in tens of seconds. The first request to a not-yet-ready replica is your cold-start tail; that is the p99 spike Lecture 2 §2.4 described, made visible.

**Estimated time.** 75 minutes (most of it deploy wait — tear down promptly).

---

## Problem 4 — Cross-check a p99 with a constant-rate tool

**Problem statement.** Take any one serving option you have running (Gemini is cheapest for this — no GPU needed) and benchmark it two ways at the same target load: (a) with your closed-loop `latency_bench.run_benchmark` harness at a fixed concurrency, and (b) with `vegeta` (or `locust` with a fixed hatch rate) at a constant arrival rate matching that concurrency's effective throughput. Compare the two p99s.

**Deliverables.** A `notes/coordinated-omission.md` with both p99 numbers, the ratio between them, and a two-sentence explanation of why the constant-rate p99 is higher (coordinated omission in the closed-loop harness).

**Acceptance criteria.**

- Both p99 numbers are reported, measured at comparable load.
- The constant-rate p99 is higher than (or, if the system never stalled, equal to) the closed-loop p99.
- The explanation correctly names coordinated omission: the closed-loop harness slows its issue rate when the system stalls, omitting the slow measurements.
- File committed.

**Hint.** `vegeta attack -rate=10/s -duration=30s` issues requests on a fixed schedule regardless of whether prior responses returned; your `ThreadPoolExecutor` waits for each response before reusing a worker. The gap between their p99s *is* the coordinated-omission error.

**Estimated time.** 60 minutes.

---

## Problem 5 — Write the breaker state machine and unit-test it

**Problem statement.** Implement the `CircuitBreaker` class from the challenge (closed/open/half-open, failure threshold, cooldown, single-flight half-open probe) and write a unit test suite that proves the state transitions **without any GCP access** — inject fake "primary call" functions that succeed or fail on demand.

**Deliverables.** `circuit_breaker.py` and `test_circuit_breaker.py`. The tests cover: (1) closed → open after the threshold of failures within the window; (2) open → half-open after the cooldown; (3) half-open → closed on a successful probe; (4) half-open → open on a failed probe; (5) a slow-but-successful call does **not** trip the breaker.

**Acceptance criteria.**

- All five transitions are tested and pass with `pytest`, with no network calls (time is controlled via a injected clock or `monkeypatch`, not real `sleep`).
- The half-open probe is single-flight (a test asserts that while one probe is in flight, other calls go to the fallback path).
- `ruff check` is clean.
- Files committed.

**Hint.** Inject a clock function (`now: Callable[[], float]`) instead of calling `time.time()` directly, so the test can advance time past the cooldown without sleeping. This is the standard testability move for any time-dependent state machine.

**Estimated time.** 75 minutes.

---

## Rubric

Total: **100 points.** Graded against the acceptance criteria above.

| Problem | Points | What earns full marks |
|---|---:|---|
| 1 — Crossover duty cycle | 18 | Three computed crossovers, dated prices, correct "output-heavy favors build" interpretation |
| 2 — Sovereignty checklist | 18 | Full 4×6 table, cited governance terms, correct elimination of the public API |
| 3 — Cold-start p99 | 22 | Distinct cold-start number, steady-state percentiles, correct price↔latency framing, **clean teardown** |
| 4 — Coordinated omission | 20 | Both p99s, correct direction of the gap, correct explanation |
| 5 — Breaker + tests | 22 | Five transitions tested without network, single-flight probe asserted, clean ruff |

**Penalties.** Any GPU-backed resource left running after a session: **−20** and an automatic re-do of the teardown gate (this course does not let an unattended A100 slide). A hard-coded credential or key file in any committed file: **−15** (Week 02 discipline carries forward).

**Deadline.** Before you start Week 13. Week 13 instruments the mini-project's service, which assumes you have the breaker and the cost model working — Problems 1 and 5 are direct prerequisites for it.
