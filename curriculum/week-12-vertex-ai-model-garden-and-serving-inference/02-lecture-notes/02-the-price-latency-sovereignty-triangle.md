# Lecture 2 — The Price/Latency/Sovereignty Triangle for Model Serving

> **Reading time:** ~70 minutes. **Hands-on time:** ~45 minutes (you build the benchmark harness you will use for the rest of the week).

Lecture 1 gave you the three bargains and the decision matrix. This lecture gives you the instrument that *resolves* the matrix when the sieves leave more than one option standing: the **price/latency/sovereignty triangle.** It is called a triangle because, like the project-management "fast, cheap, good — pick two" triangle, you can usually optimize two corners but rarely all three. The cheapest option is rarely the lowest-latency one; the lowest-latency, always-warm option rarely keeps your bytes in your VPC; the sovereign option that keeps everything in your perimeter is rarely the cheapest. Your job is not to find the option that wins all three — there usually isn't one — but to know which corner *your* workload weights most heavily and to have measured numbers for all three.

By the end of this lecture you can compute the price corner exactly, measure the latency corner honestly (without the coordinated-omission bug that makes most reported p99s fiction), and reason about the sovereignty corner as a checklist your auditor will sign. You will leave with a reusable benchmark harness — the same one the exercises and the challenge use.

## 2.1 — Why a triangle and not a checklist

A checklist implies the items are independent: tick price, tick latency, tick sovereignty, ship. They are not independent. They trade against each other, and the trades are structural, not incidental.

- **Price ↔ latency.** The cheapest per-token option at high volume is a self-hosted vLLM fleet on spot GPUs with aggressive continuous batching. But continuous batching trades single-request latency for throughput: to keep the GPU busy, the server holds requests in a batch, which adds queue time to each one. Push batching harder and per-token cost drops while p99 latency climbs. The two corners pull in opposite directions, and where you sit on that line is a tuning decision, not a default.
- **Latency ↔ sovereignty.** The lowest-latency option is usually the always-warm managed API (Gemini), because Google keeps an enormous fleet hot and you never pay a cold start. But that API, in its public form, sends your bytes to a Google service outside your VPC. To regain sovereignty you move to a regional Vertex endpoint inside a VPC-SC perimeter — which reintroduces cold starts and replica management, costing you the latency corner you were buying.
- **Price ↔ sovereignty.** Keeping everything in your own VPC on your own GPUs is maximally sovereign and, at high utilization, cheapest. But sovereignty-at-low-utilization is expensive: you pay for idle in-perimeter GPUs that a multi-tenant managed service would have amortized across other customers. The sovereign option's price is good only when your volume is high enough to keep your private fleet busy.

You cannot reason your way out of these trades. You can only measure where they put you and decide which corner you are unwilling to give up. That is what this lecture instruments.

## 2.2 — The price corner, exactly

There are two cost shapes, and converting between them is the whole skill.

**Per-token (Bargain B — Gemini API).** Published, two rates: input and output, usually quoted per million tokens. Output is typically 3–5× the input rate because generation is sequential and expensive while prompt ingestion is parallel and cheap. There is no idle cost. The cost of a request is exactly:

```text
cost = input_tokens/1e6 * price_in_per_M  +  output_tokens/1e6 * price_out_per_M
```

The only subtlety is **counting tokens correctly.** You do not estimate tokens from character count; you read them from the API's `usage_metadata`, which reports `prompt_token_count`, `candidates_token_count`, and `total_token_count` for the actual request. Estimating from characters is wrong by 20–40% depending on language and content, and a 30% error in the token count is a 30% error in your cost projection — enough to flip a build-vs-call decision. Exercise 2 reads the real counts; never trust a character heuristic in a cost memo.

**Per-node-hour (Bargains A and C).** You pay for the machine — the G2 instance plus the L4 accelerator for a Vertex Endpoint, or the Compute Engine GPU SKU for a GKE node — by the hour (billed per second, minimum one minute), whether or not it serves a request. To compare against per-token, you derive an *effective* per-token cost from the node-hour rate and the measured throughput at your duty cycle:

```text
effective_$/token = node_hour_rate / (tokens_per_second * 3600 * duty_cycle)
```

The `duty_cycle` term is everything. A GPU producing tokens 100% of the wall-clock hour amortizes the node cost across the maximum number of tokens; a GPU idle 90% of the hour amortizes it across one-tenth as many, making the effective per-token cost 10× worse. This is why "build is cheaper than call" is true only above a crossover utilization, and why that crossover is the number your recommendation memo must contain.

Here is the harness that computes both shapes and finds the crossover. You will import this from the exercises.

```python
"""cost_model.py — the price corner of the triangle.

Compute per-1k-request cost for a per-token bargain, effective per-token cost
for a node-hour bargain, and the crossover duty cycle at which the node-hour
bargain becomes cheaper than the per-token one.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenPricing:
    """Per-token (e.g. Gemini API) pricing, in dollars per MILLION tokens."""

    input_per_million: float
    output_per_million: float

    def request_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1_000_000 * self.input_per_million
            + output_tokens / 1_000_000 * self.output_per_million
        )

    def cost_per_1k_requests(self, input_tokens: int, output_tokens: int) -> float:
        return self.request_cost(input_tokens, output_tokens) * 1000


@dataclass(frozen=True)
class NodePricing:
    """Per-node-hour (e.g. Vertex Endpoint or GKE GPU node) pricing."""

    node_hour_rate: float
    sustained_output_tokens_per_second: float

    def effective_cost_per_million_output_tokens(self, duty_cycle: float) -> float:
        if not 0 < duty_cycle <= 1:
            raise ValueError("duty_cycle must be in (0, 1]")
        tokens_per_hour = self.sustained_output_tokens_per_second * 3600 * duty_cycle
        return (self.node_hour_rate / tokens_per_hour) * 1_000_000

    def cost_per_1k_requests(self, output_tokens: int, duty_cycle: float) -> float:
        per_million = self.effective_cost_per_million_output_tokens(duty_cycle)
        return (output_tokens * 1000) / 1_000_000 * per_million


def crossover_duty_cycle(
    token: TokenPricing,
    node: NodePricing,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """The duty cycle at which the node bargain's per-request cost equals the
    token bargain's. Below this utilization, call (per-token) is cheaper; above
    it, build (node-hour) is cheaper. Returns None if the node bargain is never
    cheaper even at full saturation.
    """
    token_cost = token.request_cost(input_tokens, output_tokens)
    # At duty_cycle d: node_request_cost = node_hour_rate * output_tokens
    #                  / (tps * 3600 * d).  Solve node_request_cost == token_cost.
    tps = node.sustained_output_tokens_per_second
    node_cost_at_full = (node.node_hour_rate * output_tokens) / (tps * 3600)
    if node_cost_at_full > token_cost:
        return None  # even saturated, node-hour is pricier — call always wins
    return node_cost_at_full / token_cost


if __name__ == "__main__":
    # Numbers are illustrative — confirm against the live pricing page.
    gemini = TokenPricing(input_per_million=0.075, output_per_million=0.30)
    l4_endpoint = NodePricing(node_hour_rate=0.71, sustained_output_tokens_per_second=1200)

    IN, OUT = 500, 200
    print(f"Gemini per 1k req:      ${gemini.cost_per_1k_requests(IN, OUT):.4f}")
    for d in (1.0, 0.5, 0.25, 0.1):
        print(
            f"L4 endpoint @ {d:>4.0%} duty: "
            f"${l4_endpoint.cost_per_1k_requests(OUT, d):.4f} per 1k req"
        )

    crossover = crossover_duty_cycle(gemini, l4_endpoint, IN, OUT)
    if crossover is None:
        print("Endpoint is never cheaper than Gemini at this workload.")
    else:
        print(f"Crossover: above {crossover:.1%} GPU duty cycle, the endpoint is cheaper.")
```

Run it. The crossover number it prints is the most important sentence in any serving-cost memo: *"Below X% GPU utilization, call Gemini; above it, run our own endpoint."* Everything else is detail.

## 2.3 — The latency corner, honestly

Latency is where most engineers lie to themselves, usually by accident. Three traps, each fatal to a benchmark:

**Trap 1 — reporting the mean.** The mean of a latency distribution is dominated by the body and hides the tail. A service with a 50ms median and a 4s p99 has a mean around 90ms — which sounds fine and is a lie, because 1 in 100 of your users waits 4 seconds. You report **p50 and p99**, always. The p50 is the typical experience; the p99 is the SLO-defining tail. If you must report one number, report p99, because that is the one that pages you.

**Trap 2 — single-request timing.** Timing one request tells you the latency *of one request on an idle system*, which is the latency no production request ever experiences. Real latency emerges under concurrency: requests queue, the GPU batches them, and the tail stretches. You measure under a *fixed concurrency* or, better, a *fixed request rate* that resembles production. A benchmark at concurrency 1 is the inference equivalent of a `Stopwatch` microbenchmark of one call — technically a number, practically a fiction.

**Trap 3 — coordinated omission.** This is the subtle one, and Gil Tene's talk (in the resources) is the canonical treatment. If your load generator sends a request, waits for the response, *then* sends the next, it never measures what happens when the system stalls — because when the system is slow, the generator slows down with it and simply sends fewer requests, omitting exactly the measurements that would reveal the stall. The fix is a **constant arrival rate**: send requests on a fixed schedule regardless of whether prior responses have come back, and count the latency of a request from when it *should* have been sent, not from when you got around to sending it. Tools like `vegeta` do this correctly by default; a naive `for` loop with `requests.get` does not.

Here is a latency harness that avoids all three traps. It drives a fixed concurrency, records every individual latency, and computes proper percentiles. For true constant-arrival-rate measurement you would reach for `vegeta`, but this closed-loop-with-fixed-concurrency version is honest enough for the exercises if you keep concurrency high enough to saturate the system.

```python
"""latency_bench.py — the latency corner of the triangle.

Drive a request-making callable at a fixed concurrency, record every latency,
and report p50/p90/p99 plus throughput. Records latencies for EVERY request,
not a running mean, so the percentiles are real.
"""
from __future__ import annotations

import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable


@dataclass
class BenchResult:
    n: int
    errors: int
    wall_seconds: float
    p50_ms: float
    p90_ms: float
    p99_ms: float
    throughput_rps: float

    def __str__(self) -> str:
        return (
            f"n={self.n} errors={self.errors} "
            f"p50={self.p50_ms:.0f}ms p90={self.p90_ms:.0f}ms p99={self.p99_ms:.0f}ms "
            f"throughput={self.throughput_rps:.1f} req/s"
        )


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return float("nan")
    # Nearest-rank method: index of the pct-th percentile.
    k = max(0, min(len(sorted_values) - 1, int(round(pct / 100 * len(sorted_values) + 0.5)) - 1))
    return sorted_values[k]


def run_benchmark(
    call: Callable[[], None],
    total_requests: int,
    concurrency: int,
    warmup: int = 10,
) -> BenchResult:
    """Run `call` `total_requests` times across `concurrency` workers.

    `call` should perform one inference and raise on failure. The first
    `warmup` calls are discarded so cold-start and JIT-style effects do not
    pollute the steady-state percentiles.
    """
    # Warm up (discarded).
    for _ in range(warmup):
        try:
            call()
        except Exception:
            pass

    latencies_ms: list[float] = []
    errors = 0
    wall_start = time.perf_counter()

    def timed_call() -> float:
        t0 = time.perf_counter()
        call()
        return (time.perf_counter() - t0) * 1000

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(timed_call) for _ in range(total_requests)]
        for fut in as_completed(futures):
            try:
                latencies_ms.append(fut.result())
            except Exception:
                errors += 1

    wall = time.perf_counter() - wall_start
    latencies_ms.sort()
    completed = len(latencies_ms)
    return BenchResult(
        n=completed,
        errors=errors,
        wall_seconds=wall,
        p50_ms=_percentile(latencies_ms, 50),
        p90_ms=_percentile(latencies_ms, 90),
        p99_ms=_percentile(latencies_ms, 99),
        throughput_rps=completed / wall if wall > 0 else 0.0,
    )
```

Note three deliberate choices: it discards a warm-up window (cold starts are real and you measure steady-state separately), it records every latency rather than a running mean (percentiles need the full sample), and it reports throughput alongside latency (the two are coupled — you cannot interpret a latency number without knowing the rate it was measured at). This harness is closed-loop, so it under-reports the tail relative to a true constant-rate `vegeta` run; the challenge has you cross-check with `vegeta` precisely to see the coordinated-omission gap.

## 2.4 — The latency anatomy of each bargain

The same workload has a different latency *shape* on each bargain, and knowing the shape tells you where to look when a p99 misbehaves.

**Gemini API (B).** Two components: network round-trip to the Google endpoint, and shared-fleet queue time. There is no cold start you experience. p50 is excellent and stable. p99 is mostly outside your control — it spikes when the shared fleet is busy, and you cannot tune it, only retry. Streaming helps perceived latency (time-to-first-token is low even when total time is high) but does not change the total. For a workload that cares about p50 and can tolerate an occasional slow tail, this is the best latency option.

**Vertex Endpoint (A).** Three components: network, replica queue, and — crucially — **cold start** when the autoscaler adds a replica. Loading a 9B model from storage into GPU memory takes tens of seconds; during that window, requests routed to the new (not-yet-ready) replica wait or the existing replicas absorb the load at higher latency. Your p99 will show a fat tail correlated with scale-up events. The mitigations: a higher `min_replica_count` (you pay for warm capacity to avoid cold-start tails), and an autoscaling target that triggers *before* the existing replicas saturate (scale at 50% duty cycle, not 90%, so new capacity arrives before you need it). Steady-state, with no scaling event, the p50 is good and the p99 is tight.

**vLLM on GKE (C).** Two latency components plus one cliff. The components: network and continuous-batching queue. Continuous batching is the reason vLLM's throughput dominates — it interleaves the decode steps of many requests so the GPU never idles between tokens — but it means each request's latency depends on how many other requests are in the batch. The cliff: **spot preemption.** When the spot GPU is reclaimed, in-flight requests fail and must retry on a node that may not exist yet (the cluster autoscaler has to find new spot capacity, which can take minutes or fail entirely). Your p50 on vLLM can be the best of the three; your p99 can be the worst, because the spot cliff is a 30-second-to-several-minute event that a percentile over a long window will surface. The mitigation is a small on-demand floor (one non-spot node) plus spot for the burst — which erodes the spot cost advantage, the price↔latency trade in miniature.

## 2.5 — The sovereignty corner, as a checklist

Sovereignty does not show up in either harness because it is not a measured number; it is a set of yes/no answers that either satisfy your compliance posture or do not. Run this checklist for each bargain and record the answers in your memo:

1. **Region of inference.** Where does the compute physically run? Vertex Endpoint: the region you deploy to, enforced. vLLM on GKE: your cluster's region, enforced. Gemini on Vertex AI: the regional endpoint you target. Public AI Studio Gemini API: not directly chosen by you.
2. **VPC reachability.** Can the service be reached without traversing the public internet? Vertex Endpoint: yes, via Private Service Connect. vLLM on GKE: yes, internal load balancer. Gemini on Vertex AI: regional endpoint can sit behind VPC-SC. Public Gemini API: no, it egresses.
3. **VPC-SC perimeter compatibility.** Can you wrap the service in a VPC Service Controls perimeter (Week 14) so data cannot exfiltrate even if a credential leaks? Vertex Endpoint and Gemini-on-Vertex: yes. vLLM on GKE: yes (it is your own service). Public Gemini API: no.
4. **Data-governance terms.** Is request data used to improve Google's models? Read the terms for the *specific* surface — the enterprise Vertex terms and the consumer AI Studio terms differ. Cite the document, do not paraphrase from memory.
5. **Version pinning.** Can you guarantee the model behavior does not change underneath you? Open weights on A or C: yes, you control the artifact. Closed model on B: no, models are deprecated on a schedule and you must migrate.
6. **Egress audit.** Can you prove, in an audit, where every byte went? Self-hosted and Vertex-regional: yes, via VPC flow logs and Cloud Audit Logs. Public API: harder.

A workload with a strict residency or PII-egress requirement will see this checklist eliminate the public Gemini API as a *primary* path on questions 2–4 alone — which is exactly the reasoning in Lecture 1's worked decision. Sovereignty does not negotiate with your latency budget; it eliminates options, and then you pick the cheapest, fastest survivor.

## 2.6 — Reading the triangle for a workload

Put the three corners together for a concrete workload and the decision falls out. Take the mini-project's workload — interactive event enrichment, medium spiky volume, PII present, must stay in-region:

- **Price:** at the workload's actual duty cycle (spiky, quiet nights → low average utilization), the crossover math from §2.2 says the per-token Gemini option is cheaper *on average* than a warm endpoint — but the residency sieve already constrained us. Among the residency-compliant options (Vertex Endpoint, Gemini-on-Vertex, vLLM), the endpoint at `min=1` is bounded and predictable; vLLM warm 24/7 wastes money on quiet nights.
- **Latency:** the endpoint's steady-state p50 meets the interactive budget; its cold-start p99 is the risk, mitigated by `min_replica_count = 1` and an early autoscaling trigger.
- **Sovereignty:** the endpoint keeps the artifact and the inference in-region and VPC-reachable, and lets us pin the model. It satisfies the checklist.

So the primary is the Vertex Endpoint. The fallback is Gemini (accepted as a degraded mode because a slower in-region answer beats an outage). vLLM is benchmarked but not shipped to production for this workload — and the benchmark quantifies exactly how much cheaper-at-high-volume it would be, so if the traffic shape changes (the product takes off and the GPU stays busy all night), you have the number that justifies migrating. That is the triangle doing its job: not picking a winner in the abstract, but telling you which corner this workload weights and what it costs to honor it.

## 2.7 — The benchmark you will actually run this week

Concretely, the exercises and challenge use the two harnesses above plus a small driver per bargain:

- **Gemini (Exercise 2):** wrap a `generate_content` call as the `call` argument to `run_benchmark`, read `usage_metadata` for the real token counts, and feed those into `TokenPricing.cost_per_1k_requests`. Output: p50/p99 and an exact per-1k cost.
- **Vertex Endpoint (Exercise 1, benchmarked in the challenge):** wrap an endpoint `predict` call as `call`, and compute the effective per-token cost from the L4 node-hour rate and the measured throughput at the duty cycle the benchmark drove.
- **vLLM on GKE (Exercise 3):** wrap a call to the OpenAI-compatible `/v1/completions` endpoint as `call`, and compute the effective per-token cost from the spot GPU node-hour rate and the (much higher, thanks to continuous batching) measured throughput.

Three drivers, two shared harnesses, one comparison table. The challenge assembles all three into a single chart and a one-page recommendation. The discipline — *measure all three corners, report p50/p99 not the mean, derive the crossover, name the sovereign constraint* — is the deliverable. The numbers will differ on every machine and every pricing revision; the method does not.

## 2.8 — vLLM vs TGI, and why continuous batching is the cost lever

When you self-host (Bargain C), the inference *server* you run in front of the GPU is itself a choice, and it moves the price corner more than any other knob. The two serious open options in 2026 are **vLLM** and **Hugging Face TGI (Text Generation Inference)**. Both implement the idea that makes self-hosting economical: **continuous batching.**

The naive way to serve a model is one request per GPU at a time: a request arrives, the GPU generates tokens one at a time until done, then takes the next request. Between the decode steps of a single request, the GPU is mostly idle — generating one token touches a fraction of the hardware. That idle time is wasted money. Continuous batching fixes it by interleaving the decode steps of *many* in-flight requests: while request A waits for its next token's memory fetch, the GPU works on request B's token, then C's, then back to A. The GPU stays saturated, and throughput per GPU rises several-fold. vLLM's specific contribution is **PagedAttention** (the paper is in the resources), which manages the attention key-value cache in non-contiguous "pages" the way an OS manages virtual memory — so the server can pack many more concurrent requests into the same GPU memory without fragmentation. More concurrent requests in the batch means higher throughput means lower effective per-token cost. That is the entire reason Exercise 3's vLLM throughput beats the Vertex Endpoint's on the same L4: it is not a faster GPU, it is a fuller one.

TGI implements the same continuous-batching idea with its own scheduler and a tight integration with the Hugging Face model hub. For most open models on most hardware, vLLM and TGI are within a small factor of each other on throughput; which one wins depends on the specific model, the quantization, and the request-length distribution. The stretch goal has you run both on identical hardware and measure — because "vLLM is faster" and "TGI is faster" are both true for *some* model, and a senior engineer benchmarks rather than repeats folklore.

The trade continuous batching makes is the price↔latency trade from §2.1, made concrete. Pushing the batch fuller (a higher `--max-num-seqs`, a higher `--gpu-memory-utilization`) raises throughput and lowers per-token cost — but each request now shares the GPU with more neighbors, so its individual latency rises. Pull the batch emptier and each request is faster but the GPU is less saturated and the per-token cost climbs. Where you set the knob *is* your position on the price↔latency edge of the triangle, and there is no universally correct setting — only the one your workload's latency budget and volume justify. This is the same lesson as the autoscaling-target knob on the Vertex Endpoint (§1.6 in Lecture 1): the serving system gives you a dial between cost and latency, and your job is to know which way to turn it for *this* workload.

## 2.9 — BigQuery ML: the fourth option you forget exists

The triangle has three corners and three serving bargains — but there is a fourth option that does not appear on the triangle at all, because for the right workload it sidesteps the question entirely: **BigQuery ML.** Your Week 10 data already lives in BigQuery. For tabular prediction over that data — a churn score, a fraud flag, a demand forecast — you can `CREATE MODEL` and `ML.PREDICT` *inside the warehouse*, with no endpoint, no GPU, no per-token bill, and no data leaving BigQuery:

```sql
-- Train a logistic-regression classifier directly in BigQuery — no serving tier.
CREATE OR REPLACE MODEL `your_dataset.fraud_classifier`
OPTIONS(model_type = 'LOGISTIC_REG', input_label_cols = ['is_fraud']) AS
SELECT amount, hour_of_day, merchant_category, is_fraud
FROM `your_dataset.transactions`
WHERE _PARTITIONDATE BETWEEN '2026-05-01' AND '2026-05-31';

-- Predict over new rows — the inference is a SQL query, billed as a query, not a GPU.
SELECT transaction_id, predicted_is_fraud, predicted_is_fraud_probs
FROM ML.PREDICT(MODEL `your_dataset.fraud_classifier`,
  (SELECT transaction_id, amount, hour_of_day, merchant_category
   FROM `your_dataset.transactions`
   WHERE _PARTITIONDATE = CURRENT_DATE()));
```

For an LLM-shaped task (generation, classification of free text, summarization) BQML is the wrong tool — you want a transformer behind one of the three bargains. But for a tabular task over warehouse data, BQML collapses the entire serving tier into a query, and the sovereignty corner is automatically satisfied because the data never leaves BigQuery. BQML can even call a Vertex Endpoint as a **remote model** (cited in resources), so a SQL query can invoke your Week-12 endpoint for the rows that genuinely need an LLM, while the cheap tabular rows are scored in-warehouse. The senior move, again, is to recognize the task shape before reaching for the heavyweight option: not every "we need a model" is a GPU-serving problem, and the cheapest corner of the triangle is sometimes the one labeled "you didn't need the triangle."

## 2.10 — What to carry into the exercises

1. **The price corner is a unit conversion.** Per-token is published; per-node-hour you convert via throughput × duty cycle. The crossover duty cycle is the headline number.
2. **The latency corner is a distribution, measured under load, free of coordinated omission.** Report p50 and p99. Discard warm-up. Drive concurrency. Cross-check the tail with a constant-rate tool.
3. **The sovereignty corner is a checklist your auditor signs.** It eliminates options before price or latency get a vote.
4. **No bargain wins all three corners.** Know which corner your workload weights, measure all three, and write the decision down so the next engineer inherits the reasoning, not just the result.

Go build the harness, confirm it runs against a trivial `call` (a `time.sleep(0.05)` stand-in), and you are ready for Exercise 1.

## 2.11 — A second look at the latency tail: streaming and time-to-first-token

One refinement before you benchmark, because it changes how you *report* latency for interactive workloads. So far we have measured total request latency — the time from sending the prompt to receiving the complete response. For a batch or a service-to-service call, that is the right number. For a workload where a *human* is waiting and reading the output as it streams, it is the wrong number, and reporting it makes a good experience look bad.

Generation is sequential: the model produces one token, then the next, then the next. If you stream the response (the `stream=True` path on the Gemini SDK, or the streaming endpoint on vLLM), the user sees the first token after **time-to-first-token (TTFT)** and then watches the rest arrive at the **inter-token latency** rate. A response that takes 3 seconds total but starts appearing after 200ms *feels* fast — the human is reading by the time the tail arrives. A non-streamed response that takes the same 3 seconds feels like a 3-second stall. Same total latency, completely different perceived latency.

So for interactive serving you report three numbers, not one: **TTFT** (how long until something appears — the perceived-responsiveness metric), **inter-token latency** (how fast it reads once it starts), and **total latency** (the SLO-defining number for downstream consumers that need the whole response). The benchmark harness in §2.3 measures total latency; for the streaming case you instrument the first-chunk arrival separately. vLLM's own `benchmark_serving.py` (in the resources) reports TTFT and inter-token latency precisely because the project knows total latency alone misrepresents a streaming workload. When your mini-project serves a human-facing path, report TTFT; when it serves a service-to-service enrichment path (no human waiting), report total latency. Reporting the wrong one is not a measurement error — it is a misframing that makes you optimize the wrong thing.

The triangle does not change — TTFT and total latency are both points on the same latency corner — but *which* point you weight depends, like everything this week, on the workload. A streaming chat UI weights TTFT; a backend that needs the full response before it can act weights total latency; a batch job weights neither and cares only about throughput and cost. Know which one your workload is before you pick the number you optimize.

## 2.12 — Putting the three corners on one page

The deliverable of every serving decision in this course is a single artifact: a one-page table with the three corners measured for each surviving option, and a sentence naming the corner the workload prioritizes. It looks like this, filled in from your own runs:

| Option | Price (per 1k req, at workload duty) | Latency p50 / p99 | Sovereignty | Notes |
|---|---|---|---|---|
| Vertex Endpoint (L4) | derived from node-hour ÷ throughput | measured under load | in-region, VPC-reachable, pinnable | cold-start p99 risk on scale-up |
| Gemini (Vertex-regional) | exact, from `usage_metadata` | measured under load | in-region, VPC-SC-able, **not** pinnable | zero idle cost |
| vLLM on GKE (spot L4) | derived from spot node-hour ÷ throughput | measured under load | full VPC control | spot-preemption p99 cliff |

Below the table, three sentences: the **crossover duty cycle** (the price headline), the **p99 you can commit to an SLO** (the latency headline), and the **sovereignty constraint that eliminated any option** (the constraint headline). That is the whole decision, legible to a staff engineer in thirty seconds, and reproducible because every number traces back to a command they can re-run. A serving decision presented any other way — a paragraph of prose, a vibe, a vendor's marketing number — is not a decision a senior engineer will sign. The table is the deliverable; the rest of this week is learning to fill it in honestly.

The discipline generalizes beyond models. Any "managed vs. self-hosted" decision — a database (Week 11), a message bus, a search cluster — has the same triangle shape: a price corner you convert to a common unit, a latency/performance corner you measure under realistic load, and a sovereignty/control corner that is a checklist your auditor signs. You have now done it for the highest-stakes, fastest-moving version of the decision. The next time someone asks "should we run our own X or pay for managed X," you have the method: name the corners, measure them, find the crossover, and write the one-page table. The model-serving version is just the one where getting it wrong is most expensive and the prices change fastest.

---

**References**

- Vertex AI pricing (both tables): <https://cloud.google.com/vertex-ai/pricing>
- Compute Engine GPU pricing (the self-hosted SKU): <https://cloud.google.com/compute/gpus-pricing>
- Gemini API — token counting: <https://ai.google.dev/gemini-api/docs/tokens>
- Gil Tene — "How NOT to Measure Latency": search YouTube for the talk title.
- vLLM — PagedAttention paper: <https://arxiv.org/abs/2309.06180>
- Google SRE Book — "Handling Overload": <https://sre.google/sre-book/handling-overload/>
- Vertex AI — online prediction logging (measure production token distribution): <https://cloud.google.com/vertex-ai/docs/predictions/online-prediction-logging>
