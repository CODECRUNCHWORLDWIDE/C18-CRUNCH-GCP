# Challenge 1 — Circuit-breaker fallback and the three-way benchmark

> **Estimated time:** 150 minutes. Worth more than its time-cost suggests — this is the canonical shape of a senior "we're putting a model in production" task, end to end: build the resilient client, measure all three options, and write the decision down.

You are the engineer who owns the serving tier. The team is putting Gemma 3 9B in front of the event-enrichment pipeline. Your job has three parts, and you are graded on all three: (1) build a **circuit-breaker client** that treats the Vertex Endpoint as primary and the Gemini API as fallback, with real health detection and half-open recovery; (2) **benchmark** p50/p99 latency and per-1,000-token cost across all three serving options; (3) write a **one-page recommendation** for the production path that a staff engineer would sign.

This composes everything from the week: the Exercise 1 endpoint, the Exercise 2 Gemini driver, the Exercise 3 vLLM deployment, and the Lecture 2 harnesses.

## Part 1 — The circuit-breaker client

Build a client class — call it `ResilientModelClient` — that exposes a single method `generate(prompt: str) -> ModelResponse` and internally manages a circuit breaker around the primary Vertex Endpoint, failing over to the Gemini API when the breaker is open.

The circuit breaker must implement the three-state machine from Martin Fowler's description (cited in resources):

- **Closed** — normal operation; all requests go to the primary endpoint. Failures are counted. When the failure count crosses a threshold within a window, the breaker trips to **Open**.
- **Open** — the primary is presumed unhealthy; all requests go straight to the Gemini fallback without touching the endpoint. After a cooldown, the breaker moves to **Half-open**.
- **Half-open** — a single probe request is sent to the primary. If it succeeds, the breaker closes (primary is healthy again). If it fails, the breaker re-opens and the cooldown restarts.

You may use `pybreaker` or hand-roll the state machine — hand-rolling is more instructive and the acceptance criteria assume you understand the states regardless of which you choose.

Requirements:

- A `ModelResponse` carries the generated text, which path served it (`"primary"` or `"fallback"`), and the input/output token counts.
- A failure is: a non-2xx from the endpoint, a timeout, or a connection error. A *slow but successful* response is **not** a failure (do not trip the breaker on latency alone — that is a separate decision and conflating them causes flapping).
- **Every failover is logged as a structured event** (JSON line) with the timestamp, the reason, and the breaker state transition. You cannot operate what you cannot see; an unlogged failover is an invisible degradation.
- The fallback path uses the Gemini API via the Vertex-regional path (the sovereign option from Lecture 2 — a degraded answer that stays in-region beats a faster answer that violates residency).
- A health check you can call independently of a real request, so the mini-project's readiness probe can use it.

The starting shape (you fill in the bodies):

```python
"""resilient_client.py — Vertex Endpoint primary, Gemini fallback, circuit breaker."""
from __future__ import annotations

import enum
import json
import sys
import threading
import time
from dataclasses import dataclass


class BreakerState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ModelResponse:
    text: str
    path: str          # "primary" | "fallback"
    input_tokens: int
    output_tokens: int


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0,
                 window_seconds: float = 60.0) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.window_seconds = window_seconds
        self._state = BreakerState.CLOSED
        self._failures: list[float] = []          # timestamps of recent failures
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def state(self) -> BreakerState:
        """Return the current state, transitioning OPEN -> HALF_OPEN if the
        cooldown has elapsed."""
        # TODO: implement the time-based OPEN -> HALF_OPEN transition.
        raise NotImplementedError

    def record_success(self) -> None:
        """A primary call succeeded — close the breaker and clear failures."""
        # TODO
        raise NotImplementedError

    def record_failure(self) -> None:
        """A primary call failed — record it, trip to OPEN if over threshold."""
        # TODO
        raise NotImplementedError

    def allow_primary(self) -> bool:
        """True if a request (or half-open probe) should hit the primary."""
        # TODO: CLOSED -> True; OPEN -> False; HALF_OPEN -> True (probe).
        raise NotImplementedError

    def _log_transition(self, to_state: BreakerState, reason: str) -> None:
        print(json.dumps({
            "event": "circuit_breaker_transition",
            "ts": time.time(),
            "to_state": to_state.value,
            "reason": reason,
        }), file=sys.stderr)


class ResilientModelClient:
    def __init__(self, breaker: CircuitBreaker) -> None:
        self._breaker = breaker

    def generate(self, prompt: str) -> ModelResponse:
        """Try the primary endpoint when the breaker allows; otherwise (or on
        failure) fall back to Gemini. Log every failover."""
        # TODO: implement the closed/open/half-open routing.
        raise NotImplementedError

    def _call_primary(self, prompt: str) -> ModelResponse:
        """Call the Vertex Endpoint. Raise on any failure (the breaker counts it)."""
        # TODO: use the Exercise 1 endpoint.predict(...) call.
        raise NotImplementedError

    def _call_fallback(self, prompt: str) -> ModelResponse:
        """Call the Gemini API (Vertex-regional path). Should rarely fail."""
        # TODO: use the Exercise 2 generate_content call.
        raise NotImplementedError

    def health(self) -> bool:
        """True if the client can serve (primary healthy OR fallback reachable)."""
        # TODO
        raise NotImplementedError
```

## Part 2 — The three-way benchmark

Drive the same fixed workload (the boring sentiment prompt from the exercises, fixed token shape) against all three serving options and produce one comparison table. Use the `latency_bench.run_benchmark` harness from Lecture 2 and the `cost_model` harness for the per-token math.

You must:

1. Benchmark the **Vertex Endpoint** directly (no breaker) for its native p50/p99 and derive its effective \$/1M-token cost from the L4 node-hour rate and measured throughput.
2. Benchmark the **Gemini API** for p50/p99 and exact per-token cost (you already have this from Exercise 2).
3. Benchmark **vLLM on the GKE spot pool** for p50/p99 and throughput, and derive its effective \$/1M-token cost from the spot node-hour rate.
4. **Force a failover** during a fourth run: benchmark the `ResilientModelClient` *while the endpoint is unhealthy* (un-deploy the model, or block the endpoint with a firewall rule, or point it at a bad address) and confirm the breaker trips, the load shifts to Gemini, and the run still succeeds. Capture the p50/p99 of the degraded mode.
5. **Cross-check the tail with a constant-rate tool.** Run one option through `vegeta` (or `locust` with a fixed hatch rate) at a constant arrival rate and compare its reported p99 to your closed-loop harness's p99. Document the coordinated-omission gap.

Produce a single table:

```text
| Option                  | p50    | p99    | throughput | $/1M out tok | sovereignty      |
|-------------------------|--------|--------|------------|--------------|------------------|
| Vertex Endpoint (L4)    | ...ms  | ...ms  | ... rps    | $... @ X%    | in-region, VPC   |
| Gemini API (Vertex)     | ...ms  | ...ms  | ... rps    | $... (token) | in-region, VPC-SC|
| vLLM on GKE (spot L4)   | ...ms  | ...ms  | ... rps    | $... @ 100%  | full VPC control |
| Resilient (degraded)    | ...ms  | ...ms  | ... rps    | n/a          | falls to Gemini  |
```

## Part 3 — The recommendation memo

Write a **one-page** (400–600 word) memo, `RECOMMENDATION.md`, that a staff engineer would sign. It must:

- State the workload's properties (traffic shape, volume, sovereignty constraint) in two or three sentences.
- Run the **sieve** from Lecture 1: which options does the sovereignty constraint eliminate, and why.
- Present the **crossover duty cycle** (from `cost_model.crossover_duty_cycle`): below what GPU utilization is Gemini cheaper than the endpoint? Where does the workload's actual duty cycle sit relative to that line?
- Recommend a **primary path** and a **fallback path**, and justify each on price, latency, and sovereignty — naming which corner of the triangle you are prioritizing and which you are sacrificing.
- State explicitly what would change your recommendation (e.g., "if sustained volume rises above N req/s such that GPU duty cycle exceeds the crossover, migrate the primary to vLLM on a mixed spot+on-demand pool").
- Include the benchmark table from Part 2 as evidence.

A memo that recommends an option without the crossover number, or that does not name the sovereignty sieve, fails the review — those are the two things a staff engineer checks first.

## Acceptance criteria

- [ ] `ResilientModelClient.generate` routes to the primary when the breaker is closed, to Gemini when open, and probes the primary when half-open. The state machine is correct.
- [ ] A failure on the primary (non-2xx, timeout, or connection error) is counted; a slow-but-successful response is **not** counted. The breaker trips after the threshold and recovers via a half-open probe.
- [ ] Every failover and every state transition is logged as a structured JSON line to stderr.
- [ ] The fallback uses the Gemini Vertex-regional path (sovereign), not the public AI Studio path.
- [ ] The three-way benchmark table exists with p50, p99, throughput, and \$/1M-output-token for all three options plus the degraded mode.
- [ ] A forced-failover run demonstrates the breaker tripping and the run still succeeding via Gemini, with the transition visible in the logs.
- [ ] A `vegeta` (or `locust` constant-rate) cross-check is reported, with the coordinated-omission gap between closed-loop and constant-rate p99 documented in one sentence.
- [ ] `RECOMMENDATION.md` is 400–600 words, runs the sovereignty sieve, contains the crossover duty cycle, recommends a primary + fallback with triangle-corner justification, and states what would change the recommendation.
- [ ] **Teardown receipt is clean:** `gcloud ai endpoints list` and the GPU node-pool list both print nothing after you finish.

## Hints

1. **Do not trip the breaker on latency.** A failure is an error or a timeout, not "slow." Conflating slow with failed makes the breaker flap under load — it opens, sheds to Gemini, the endpoint recovers because load dropped, it closes, load returns, it opens again. Count only hard failures.

2. **The half-open probe must be single-flight.** Only one request probes the primary in half-open; the rest go to fallback until the probe resolves. If you let every request probe, you hammer a recovering endpoint and never let it recover. Use the lock.

3. **Forcing a failover cleanly:** the least-destructive way to make the endpoint "unhealthy" for the benchmark is to point `_call_primary` at a bad endpoint ID or add a deny firewall rule, run the degraded benchmark, then revert — rather than un-deploying the model (which costs you the 20-40 minute redeploy). Pick the method that does not waste a deploy cycle.

4. **The crossover number is the headline.** Reviewers will look for it. Compute it with `crossover_duty_cycle` from Lecture 2 using your *measured* throughput, not an assumed one.

5. **Coordinated omission:** your `ThreadPoolExecutor` harness is closed-loop — it waits for each response before issuing the next on that worker, so it under-reports the tail. `vegeta -rate=20/s` issues at a constant rate regardless of responses. Expect the `vegeta` p99 to be *higher*; that gap is the lie your closed-loop harness was telling.

## Submission

Commit to your Week 12 repository at `challenges/challenge-01/`:

- `resilient_client.py` — the completed circuit-breaker client.
- `bench.py` — the three-way benchmark driver that produces the table.
- `results.md` — the comparison table and the `vegeta` cross-check.
- `RECOMMENDATION.md` — the one-page memo.
- A short `README.md` explaining how to run it and the teardown command.

The instructor reviews by reading `RECOMMENDATION.md` first, then re-running `bench.py` against a fresh deploy. A memo whose recommendation does not follow from its own table is the most common review-fail.

---

**References**

- Martin Fowler — CircuitBreaker: <https://martinfowler.com/bliki/CircuitBreaker.html>
- Google SRE Book — Handling Overload: <https://sre.google/sre-book/handling-overload/>
- Gil Tene — How NOT to Measure Latency: search YouTube for the talk.
- `vegeta` — constant-rate load testing: <https://github.com/tsenart/vegeta>
- Vertex AI pricing: <https://cloud.google.com/vertex-ai/pricing>
