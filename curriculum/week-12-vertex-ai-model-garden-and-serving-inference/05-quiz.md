# Week 12 — Quiz

Twelve questions on the build-vs-call decision, the price/latency/sovereignty triangle, Vertex serving, the Gemini API, vLLM on GKE, and the circuit-breaker pattern. Take it with your lecture notes closed. Aim for 10/12 before moving to Week 13. Answer key at the bottom — don't peek.

---

**Q1.** You are serving a low-volume internal tool: a few hundred classifications a day, spiky, near-zero at night, no special data-residency requirement. Which serving bargain is cheapest for this workload, and why?

- A) A Vertex AI Endpoint with `min_replica_count=1`, because Google operates it.
- B) The Gemini API, because it has zero idle cost and you only pay for the tokens you actually use.
- C) vLLM on a GKE spot pool, because spot GPUs are 60–70% cheaper.
- D) A `BatchPredictionJob`, because batch is always cheapest.

---

**Q2.** What does the `autoscaling_target_accelerator_duty_cycle` parameter on a Vertex Endpoint deployment control?

- A) The CPU utilization at which a new replica is added.
- B) The GPU utilization (duty cycle) at which a new replica is added.
- C) The maximum number of GPUs per replica.
- D) The fraction of traffic sent to the newest replica.

---

**Q3.** You report a serving latency of "mean 90ms." A senior engineer rejects the number. What is the most likely reason?

- A) The mean is in milliseconds and should be in microseconds.
- B) The mean hides the tail; you must report p50 and p99 because the tail is what defines the SLO and pages you.
- C) 90ms is too fast to be real for a 9B model.
- D) The mean should be computed only over successful requests.

---

**Q4.** In the price corner of the triangle, the *effective* per-token cost of a self-hosted vLLM node is computed as `node_hour_rate / (tokens_per_second * 3600 * duty_cycle)`. Why does the `duty_cycle` term flip the build-vs-call decision?

- A) It doesn't — node-hour cost is fixed regardless of utilization.
- B) Because at low duty cycle you amortize the fixed node cost across far fewer tokens, so the effective per-token cost rises and the pay-per-token API becomes cheaper.
- C) Because duty cycle changes the node-hour rate Google charges.
- D) Because duty cycle only affects latency, not cost.

---

**Q5.** Which of the following is **not** a reason a single-request, closed-loop latency measurement is misleading for a production serving benchmark?

- A) It measures latency on an idle system, which no production request experiences.
- B) It suffers coordinated omission: when the system stalls, the generator slows with it and omits the slow measurements.
- C) It cannot measure GPU duty cycle.
- D) It ignores the queue and batching latency that only appear under concurrency.

---

**Q6.** Your compliance posture requires that inputs containing PII never leave your project's VPC perimeter. Which option does this requirement eliminate *first*, before you consider price or latency?

- A) A Vertex AI Endpoint in your region.
- B) vLLM on your own GKE cluster.
- C) The public AI Studio Gemini API (it egresses to a Google service outside your VPC).
- D) A `BatchPredictionJob` reading from BigQuery.

---

**Q7.** In a circuit breaker, a request arrives while the breaker is in the **half-open** state. What should happen?

- A) The request is rejected outright.
- B) A single probe request is sent to the primary; success closes the breaker, failure re-opens it. Other concurrent requests go to the fallback until the probe resolves.
- C) All requests flood the primary to test it quickly.
- D) The request always goes to the fallback regardless of the probe.

---

**Q8.** Why should a circuit breaker **not** trip on high latency alone (only on hard failures like non-2xx, timeout, connection error)?

- A) Latency is impossible to measure.
- B) Because tripping on latency causes flapping: the breaker opens, load shifts away, the endpoint recovers because load dropped, the breaker closes, load returns, it opens again.
- C) Because high latency never indicates a real problem.
- D) Because the fallback is always slower than the primary.

---

**Q9.** What makes vLLM's per-GPU throughput substantially higher than a naive one-request-per-GPU server?

- A) It uses a larger GPU.
- B) Continuous batching (PagedAttention) interleaves the decode steps of many concurrent requests so the GPU never idles between tokens.
- C) It compresses the model weights.
- D) It runs only on spot instances.

---

**Q10.** You deploy a model to a Vertex Endpoint at `min_replica_count=1`, send it zero requests for 24 hours, then delete the endpoint. What did you pay for?

- A) Nothing — no requests means no charge.
- B) 24 hours of one L4 replica's node-hour cost, because a deployed model at `min_replica_count=1` keeps a replica warm and billing regardless of traffic.
- C) Only the per-token cost of the deploy.
- D) Only storage for the model artifact.

---

**Q11.** When computing the per-1,000-token cost of a Gemini API call for a cost memo, where must the token counts come from?

- A) `len(prompt_text)` divided by 4.
- B) An estimate from the character count of the input and output.
- C) The response's `usage_metadata` (`prompt_token_count`, `candidates_token_count`) — the real counts, because a character estimate is wrong by 20–40% and a cost memo cannot tolerate that.
- D) The model card's documented average.

---

**Q12.** A workload needs offline enrichment of a day's BigQuery events by morning — no human is waiting on any individual prediction. Compared to streaming the same volume through an online Vertex Endpoint, what is true of a `BatchPredictionJob`?

- A) Batch is always slower and more expensive.
- B) Batch has no warm-replica idle cost and batches aggressively without a latency constraint, often making it an order of magnitude cheaper for non-interactive workloads.
- C) Batch cannot read from BigQuery.
- D) Batch and online cost exactly the same per prediction.

---

## Answer key

**Don't read this until you've answered all twelve.**

**A1 — B.** Low-volume, spiky, near-zero-at-night workloads are exactly where the Gemini API's zero-idle-cost, pay-per-token model wins. A warm endpoint or a warm vLLM node pays for idle GPUs all night; the per-token bargain pays nothing when idle. (Lecture 1, §1.2; Lecture 2, §2.2.)

**A2 — B.** It is the GPU duty cycle at which the autoscaler adds a replica. GPUs are the constrained resource in inference, so you scale on GPU saturation, not CPU. Setting it *early* (e.g., 50%) trims the cold-start p99 tail by bringing capacity online before the existing replica saturates. (Lecture 1, §1.6; Exercise 1.)

**A3 — B.** The mean is dominated by the body of the distribution and hides the tail. A 50ms median with a 4s p99 has a mean around 90ms — which sounds fine and is a lie, because 1 in 100 users waits 4 seconds. Report p50 and p99. (Lecture 2, §2.3.)

**A4 — B.** The node-hour cost is fixed, but the number of tokens it is amortized over scales with duty cycle. At 10% duty cycle the effective per-token cost is 10× the saturated cost, which is enough to flip the decision toward the pay-per-token API. The duty cycle at which the two cross is the headline number of the recommendation memo. (Lecture 2, §2.2.)

**A5 — C.** A, B, and D are all real reasons a single-request closed-loop measurement misleads. GPU duty cycle is a cost/utilization metric, not a property the latency measurement is trying to capture — so "cannot measure GPU duty cycle" is not the reason the *latency* number is misleading. (Lecture 2, §2.3.)

**A6 — C.** Sovereignty is the first sieve. A residency/PII-egress requirement eliminates the public AI Studio Gemini API (which egresses to a Google service) before price or latency get a vote. The in-region endpoint, in-cluster vLLM, and BigQuery batch all keep the bytes in your perimeter. (Lecture 1, §1.2; Lecture 2, §2.5.)

**A7 — B.** Half-open sends a *single* probe to the primary; success closes the breaker, failure re-opens it. The probe must be single-flight (one request, not all of them) so a recovering endpoint is not hammered. (Lecture 2, §2.4; Challenge hints.)

**A8 — B.** Tripping on latency causes flapping. A failure is a hard error or timeout; "slow" is a separate signal. Conflating them makes the breaker oscillate under load. (Challenge, Part 1; hints.)

**A9 — B.** Continuous batching / PagedAttention interleaves the decode steps of many requests so the GPU stays busy across requests rather than idling between tokens of a single one. That is why vLLM's throughput per GPU dominates and why its effective per-token cost at high utilization is the lowest of the three options. (Lecture 2, §2.4; Exercise 3; resources — PagedAttention paper.)

**A10 — B.** A deployed model at `min_replica_count=1` keeps one replica warm and billing 24/7 regardless of traffic. Zero requests does not mean zero cost on Bargain A. This is exactly why the teardown gate checks for deployed models, not just for traffic. (Lecture 1, §1.6; Exercise 1; mini-project teardown gate.)

**A11 — C.** Always read the real counts from `usage_metadata`. A character-based estimate is off by 20–40% depending on language and content, and a 30% error in the token count is a 30% error in the cost projection — enough to flip a build-vs-call decision. (Lecture 2, §2.2; Exercise 2.)

**A12 — B.** Batch prediction has no warm-replica idle cost and batches aggressively because nothing is waiting on the latency, often making it an order of magnitude cheaper than streaming the same volume online. "Could this be batch?" should be asked before "which online bargain?" (Lecture 1, §1.7.)

---

**Scoring:** 12/12 — you can defend the build-vs-call decision in a review. 10–11 — solid; re-read the sections behind your misses. 8–9 — re-read both lectures before the mini-project. Below 8 — the triangle hasn't landed yet; re-read Lecture 2 §2.2–2.5 and re-run the Exercise 2 cost math by hand.
