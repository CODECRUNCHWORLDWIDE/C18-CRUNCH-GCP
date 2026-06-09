"""Exercise 2 — Call the Gemini API and capture per-1000-token cost and p50/p99 latency.

Goal: call the Gemini API from a service, read the REAL token counts from the
response's usage_metadata (never estimate from characters), and compute a
defensible per-1000-token cost plus a p50/p99 latency distribution from a load
test that drives a fixed concurrency.

This is the Bargain B corner of the price/latency/sovereignty triangle: zero idle
cost, always warm, per-token pricing. By the end you have the exact numbers you
will compare against the Vertex Endpoint (Exercise 1) and vLLM (Exercise 3) in
the challenge.

Estimated time: 60 minutes.

----------------------------------------------------------------------------------
HOW TO RUN
----------------------------------------------------------------------------------

  python3 -m venv .venv && source .venv/bin/activate
  pip install 'google-genai==1.*'

  # Auth: either Vertex AI (recommended for sovereignty — stays in your project)
  # or the AI Studio API key. This script uses the Vertex AI path by default.
  export GOOGLE_GENAI_USE_VERTEXAI=true
  export GOOGLE_CLOUD_PROJECT="your-project-id"
  export GOOGLE_CLOUD_LOCATION="us-central1"
  gcloud auth application-default login   # one time

  python exercise-02-gemini-cost-latency.py --requests 60 --concurrency 6

  # To use the AI Studio key path instead (note: leaves your VPC — see Lecture 2
  # sovereignty checklist), unset GOOGLE_GENAI_USE_VERTEXAI and set:
  #   export GOOGLE_API_KEY="..."

----------------------------------------------------------------------------------
WHAT YOU IMPLEMENT
----------------------------------------------------------------------------------

Nothing is stubbed out — this file runs as-is. Your job is to:
  1. Run it against your project and capture the printed table.
  2. Confirm the per-token cost matches a hand calculation from the pricing page.
  3. Vary --requests and --concurrency and watch p99 move relative to p50.
  4. Save the output for the challenge's three-way comparison.

----------------------------------------------------------------------------------
ACCEPTANCE CRITERIA
----------------------------------------------------------------------------------

  [ ] The script runs and prints a table with p50, p99, throughput, and a
      per-1000-request cost derived from REAL usage_metadata token counts.
  [ ] The token counts come from response.usage_metadata, not from len(text).
  [ ] You confirm the cost figure by hand against the live pricing page.
  [ ] p99 >= p50 (always) and p99 grows relative to p50 as concurrency rises.
  [ ] You record the numbers for the challenge.

----------------------------------------------------------------------------------
SMOKE OUTPUT (target shape — your numbers will differ)
----------------------------------------------------------------------------------

  Gemini benchmark: gemini-2.0-flash-001  (Vertex AI path)
  requests=60 concurrency=6 errors=0
  latency:    p50=540ms  p90=880ms  p99=1310ms
  throughput: 9.8 req/s
  tokens:     avg_in=46  avg_out=58  (from usage_metadata)
  cost:       $0.0000209 / request  ->  $0.0209 / 1000 requests
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from google import genai
from google.genai import types

# Confirm the current model ID and prices against the live pages before trusting
# the cost number. These change. (Vertex AI generative pricing + Gemini models.)
MODEL_ID = "gemini-2.0-flash-001"
INPUT_PRICE_PER_MILLION = 0.075   # USD per 1M input tokens — VERIFY on the pricing page
OUTPUT_PRICE_PER_MILLION = 0.30   # USD per 1M output tokens — VERIFY on the pricing page

# A deliberately fixed, boring prompt so the benchmark is honest: every request
# has nearly the same token shape, so the cost and latency are not polluted by
# prompt-length variance. This is a benchmark, not a product.
PROMPT = (
    "Classify the sentiment of this support ticket as exactly one of "
    "POSITIVE, NEGATIVE, or NEUTRAL, and reply with only that single word: "
    "'The new dashboard is fast but the export button is hidden and I cannot find it.'"
)


@dataclass
class CallResult:
    latency_ms: float
    input_tokens: int
    output_tokens: int


def make_client() -> genai.Client:
    """Build a Gen AI client. Honors GOOGLE_GENAI_USE_VERTEXAI for the sovereign
    (in-project, regional) path; falls back to the AI Studio key path otherwise.
    """
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
    if use_vertex:
        return genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    # AI Studio path — leaves your VPC. See Lecture 2 sovereignty checklist.
    return genai.Client(api_key=os.environ["GOOGLE_API_KEY"])


def one_call(client: genai.Client) -> CallResult:
    """One generate_content call, timed, with REAL token counts from usage_metadata."""
    t0 = time.perf_counter()
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=PROMPT,
        config=types.GenerateContentConfig(
            max_output_tokens=16,
            temperature=0.0,  # deterministic-ish: a benchmark wants stable output length
        ),
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    # The ONLY correct source of token counts. Do not estimate from text length.
    usage = response.usage_metadata
    return CallResult(
        latency_ms=latency_ms,
        input_tokens=usage.prompt_token_count or 0,
        output_tokens=usage.candidates_token_count or 0,
    )


def percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return float("nan")
    k = max(
        0,
        min(
            len(sorted_values) - 1,
            int(round(pct / 100 * len(sorted_values) + 0.5)) - 1,
        ),
    )
    return sorted_values[k]


def run(requests_total: int, concurrency: int, warmup: int) -> None:
    client = make_client()

    path = "Vertex AI path" if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true" else "AI Studio path"
    print(f"Gemini benchmark: {MODEL_ID}  ({path})")

    # Warm up (discarded) — the first call pays connection setup and auth.
    for _ in range(warmup):
        try:
            one_call(client)
        except Exception as exc:  # noqa: BLE001 - warm-up errors are non-fatal
            print(f"  (warmup error ignored: {exc})", file=sys.stderr)

    results: list[CallResult] = []
    errors = 0
    wall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one_call, client) for _ in range(requests_total)]
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"  request error: {exc}", file=sys.stderr)

    wall = time.perf_counter() - wall_start
    if not results:
        print("No successful requests — check auth, model ID, and quota.", file=sys.stderr)
        sys.exit(1)

    latencies = sorted(r.latency_ms for r in results)
    avg_in = statistics.mean(r.input_tokens for r in results)
    avg_out = statistics.mean(r.output_tokens for r in results)

    cost_per_request = (
        avg_in / 1_000_000 * INPUT_PRICE_PER_MILLION
        + avg_out / 1_000_000 * OUTPUT_PRICE_PER_MILLION
    )

    print(f"requests={len(results)} concurrency={concurrency} errors={errors}")
    print(
        f"latency:    p50={percentile(latencies, 50):.0f}ms  "
        f"p90={percentile(latencies, 90):.0f}ms  "
        f"p99={percentile(latencies, 99):.0f}ms"
    )
    print(f"throughput: {len(results) / wall:.1f} req/s")
    print(f"tokens:     avg_in={avg_in:.0f}  avg_out={avg_out:.0f}  (from usage_metadata)")
    print(
        f"cost:       ${cost_per_request:.7f} / request  ->  "
        f"${cost_per_request * 1000:.4f} / 1000 requests"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gemini API cost/latency benchmark")
    parser.add_argument("--requests", type=int, default=60, help="total requests after warmup")
    parser.add_argument("--concurrency", type=int, default=6, help="concurrent in-flight requests")
    parser.add_argument("--warmup", type=int, default=5, help="discarded warmup requests")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.requests, args.concurrency, args.warmup)
