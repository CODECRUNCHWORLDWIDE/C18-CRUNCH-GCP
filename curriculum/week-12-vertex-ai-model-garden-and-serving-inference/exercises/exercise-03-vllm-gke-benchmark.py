"""Exercise 3 — Self-host the model with vLLM on a GKE spot pool and benchmark it.

Goal: serve the SAME open-weights model you deployed in Exercise 1 (Gemma 3 9B),
but this time on YOUR OWN GKE Standard cluster, on a SPOT GPU node pool, behind
vLLM's OpenAI-compatible server. Then benchmark p50/p99 and throughput against
the Vertex Endpoint. This is Bargain C: you own the whole stack, you take the
spot bargain (60-70% off) and accept the preemption cliff.

The throughput should beat the Vertex Endpoint per GPU because of vLLM's
continuous batching (PagedAttention) — that is the whole point. The p99 may be
WORSE if a spot node is preempted mid-run. Capture both.

Estimated time: 120 minutes, plus node-pool creation wait (~5-10 min) and the
vLLM container's model download + load to GPU (~10-20 min on first start).

----------------------------------------------------------------------------------
PART A — PROVISION THE GPU NODE POOL (shell, do this first)
----------------------------------------------------------------------------------

Add a SPOT L4 node pool to your Week 06 cluster. Spot is the cost bargain; the
node can be preempted with 30s notice, which is the latency cliff Lecture 2 warned
about.

  export PROJECT_ID="your-project-id"
  export REGION="us-central1"
  export CLUSTER="crunch-gke"     # your Week 06 cluster

  gcloud container node-pools create gpu-spot-l4 \
    --cluster="$CLUSTER" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --machine-type=g2-standard-12 \
    --accelerator=type=nvidia-l4,count=1,gpu-driver-version=latest \
    --spot \
    --num-nodes=1 \
    --enable-autoscaling --min-nodes=0 --max-nodes=2 \
    --node-labels=workload=vllm,capacity=spot

----------------------------------------------------------------------------------
PART B — DEPLOY vLLM (kubectl, apply the manifest below)
----------------------------------------------------------------------------------

Save this manifest as vllm.yaml and `kubectl apply -f vllm.yaml`. It runs the
official vLLM OpenAI-compatible server, pinned to the spot GPU node, and exposes
it on an internal Service. Set HF_TOKEN as a secret first if the model is gated:

  kubectl create secret generic hf-token --from-literal=token="$HF_TOKEN"

--- vllm.yaml -------------------------------------------------------------------
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-gemma
  labels: { app: vllm-gemma }
spec:
  replicas: 1
  selector:
    matchLabels: { app: vllm-gemma }
  template:
    metadata:
      labels: { app: vllm-gemma }
    spec:
      nodeSelector:
        workload: vllm
        cloud.google.com/gke-accelerator: nvidia-l4
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - "--model=google/gemma-3-9b-it"
            - "--max-model-len=4096"
            - "--gpu-memory-utilization=0.92"
            - "--port=8000"
          ports:
            - containerPort: 8000
          env:
            - name: HUGGING_FACE_HUB_TOKEN
              valueFrom:
                secretKeyRef: { name: hf-token, key: token }
          resources:
            limits:
              nvidia.com/gpu: "1"
          readinessProbe:
            httpGet: { path: /health, port: 8000 }
            initialDelaySeconds: 60
            periodSeconds: 10
            failureThreshold: 60   # model load is slow; be patient
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-gemma
spec:
  type: ClusterIP
  selector: { app: vllm-gemma }
  ports:
    - port: 8000
      targetPort: 8000
---------------------------------------------------------------------------------

Wait for readiness, then port-forward so this script can reach it locally:

  kubectl rollout status deployment/vllm-gemma --timeout=1800s
  kubectl port-forward svc/vllm-gemma 8000:8000

----------------------------------------------------------------------------------
PART C — BENCHMARK (this script)
----------------------------------------------------------------------------------

  pip install 'requests==2.32.*'
  python exercise-03-vllm-gke-benchmark.py \
      --base-url http://localhost:8000 \
      --model google/gemma-3-9b-it \
      --requests 120 --concurrency 12

----------------------------------------------------------------------------------
PART D — TEAR DOWN (NOT optional)
----------------------------------------------------------------------------------

  kubectl delete -f vllm.yaml
  gcloud container node-pools delete gpu-spot-l4 \
    --cluster="$CLUSTER" --region="$REGION" --project="$PROJECT_ID" --quiet

Confirm the receipt:
  gcloud container node-pools list --cluster="$CLUSTER" --region="$REGION" \
    --filter='config.accelerators:*' --format='value(name)'
  # (no output)

----------------------------------------------------------------------------------
ACCEPTANCE CRITERIA
----------------------------------------------------------------------------------

  [ ] The spot GPU node pool was created and vLLM became Ready.
  [ ] The benchmark drives concurrency > 1 and reports p50/p99/throughput.
  [ ] Throughput per GPU exceeds the Vertex Endpoint's (continuous batching wins).
  [ ] You record the SPOT node-hour rate and derive an effective $/1M-token cost.
  [ ] The GPU node pool is DELETED and the teardown receipt is empty.

SMOKE OUTPUT (target shape — your numbers will differ):

  vLLM benchmark: google/gemma-3-9b-it @ http://localhost:8000
  requests=120 concurrency=12 errors=0
  latency:    p50=410ms  p90=720ms  p99=1180ms
  throughput: 26.4 req/s   (continuous batching => high per-GPU throughput)
  tokens:     avg_in=44  avg_out=57
  cost:       spot L4 node-hour=$0.28  effective=$0.078 / 1M output tokens @ 100% duty
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

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


def one_call(base_url: str, model: str, session: requests.Session) -> CallResult:
    """One call to vLLM's OpenAI-compatible /v1/chat/completions endpoint, timed.

    vLLM returns a `usage` block with prompt_tokens and completion_tokens — the
    same real-token-count discipline as Exercise 2.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 16,
        "temperature": 0.0,
    }
    t0 = time.perf_counter()
    resp = session.post(f"{base_url}/v1/chat/completions", json=payload, timeout=60)
    resp.raise_for_status()
    latency_ms = (time.perf_counter() - t0) * 1000

    body = resp.json()
    usage = body.get("usage", {})
    return CallResult(
        latency_ms=latency_ms,
        input_tokens=int(usage.get("prompt_tokens", 0)),
        output_tokens=int(usage.get("completion_tokens", 0)),
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


def effective_cost_per_million_output_tokens(
    node_hour_rate: float, output_tokens_per_second: float, duty_cycle: float
) -> float:
    """Convert a node-hour rate into an effective per-million-output-token cost.

    Same conversion as Lecture 2's cost_model.NodePricing. duty_cycle=1.0 assumes
    the GPU is saturated; scale down for a realistic production duty cycle.
    """
    if not 0 < duty_cycle <= 1:
        raise ValueError("duty_cycle must be in (0, 1]")
    tokens_per_hour = output_tokens_per_second * 3600 * duty_cycle
    return (node_hour_rate / tokens_per_hour) * 1_000_000


def run(base_url: str, model: str, requests_total: int, concurrency: int,
        warmup: int, spot_node_hour_rate: float) -> None:
    session = requests.Session()
    print(f"vLLM benchmark: {model} @ {base_url}")

    for _ in range(warmup):
        try:
            one_call(base_url, model, session)
        except Exception as exc:  # noqa: BLE001
            print(f"  (warmup error ignored: {exc})", file=sys.stderr)

    results: list[CallResult] = []
    errors = 0
    wall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(one_call, base_url, model, requests.Session())
            for _ in range(requests_total)
        ]
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"  request error: {exc}", file=sys.stderr)

    wall = time.perf_counter() - wall_start
    if not results:
        print("No successful requests — is the port-forward up and the pod Ready?", file=sys.stderr)
        sys.exit(1)

    latencies = sorted(r.latency_ms for r in results)
    avg_in = statistics.mean(r.input_tokens for r in results)
    avg_out = statistics.mean(r.output_tokens for r in results)
    total_output_tokens = sum(r.output_tokens for r in results)
    output_tps = total_output_tokens / wall if wall > 0 else 0.0

    eff_cost = effective_cost_per_million_output_tokens(
        node_hour_rate=spot_node_hour_rate,
        output_tokens_per_second=output_tps,
        duty_cycle=1.0,
    )

    print(f"requests={len(results)} concurrency={concurrency} errors={errors}")
    print(
        f"latency:    p50={percentile(latencies, 50):.0f}ms  "
        f"p90={percentile(latencies, 90):.0f}ms  "
        f"p99={percentile(latencies, 99):.0f}ms"
    )
    print(f"throughput: {len(results) / wall:.1f} req/s   "
          f"({output_tps:.0f} output tok/s — continuous batching)")
    print(f"tokens:     avg_in={avg_in:.0f}  avg_out={avg_out:.0f}")
    print(
        f"cost:       spot L4 node-hour=${spot_node_hour_rate:.2f}  "
        f"effective=${eff_cost:.3f} / 1M output tokens @ 100% duty"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="vLLM-on-GKE cost/latency benchmark")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--model", default="google/gemma-3-9b-it")
    parser.add_argument("--requests", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--warmup", type=int, default=8)
    parser.add_argument(
        "--spot-node-hour-rate",
        type=float,
        default=0.28,
        help="Spot g2-standard-12 + L4 node-hour rate — VERIFY on the pricing page",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        args.base_url,
        args.model,
        args.requests,
        args.concurrency,
        args.warmup,
        args.spot_node_hour_rate,
    )
