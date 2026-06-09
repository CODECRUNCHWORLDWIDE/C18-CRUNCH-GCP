# Week 12 — Challenges

One stretch problem. No solution is provided — only acceptance criteria. This is the kind of open-ended, multi-part task you would be handed in a real production shop: "we're putting a model in front of the enrichment pipeline; figure out the serving path, build a fallback, and tell me which option we should ship and why, with numbers."

## Index

1. **[Challenge 1 — Circuit-breaker fallback and the three-way benchmark](challenge-01-circuit-breaker-fallback-and-bench.md)** — deploy the Model Garden endpoint with GPU autoscaling, write a circuit-breaker client that fails over to the Gemini API when the endpoint is unhealthy, benchmark p50/p99 and per-1,000-token cost across all three serving options (endpoint, Gemini, vLLM-on-GKE), and write a one-page recommendation for the production path. (~2.5h)

## How to work the challenge

- **Reuse your exercise artifacts.** The endpoint from Exercise 1, the Gemini driver from Exercise 2, the vLLM deployment from Exercise 3, and the `cost_model` / `latency_bench` harnesses from Lecture 2 are all inputs. The challenge assembles them; it does not start fresh.
- **The deliverable is a decision, not just code.** The circuit breaker is the engineering; the recommendation memo is the judgment. A staff engineer cares about both, but they will read the memo first.
- **Tear everything down.** The challenge runs the same GPU resources as the exercises. The teardown receipt applies.

There are no checked-in solutions; the course is open source and solutions live in forks. The acceptance criteria tell you when you are done.
