# Week 12 — Exercises

Three focused drills that measure all three corners of the triangle. Do them **in order** — Exercise 1 stands up the endpoint the challenge benchmarks, Exercise 2 establishes the Gemini fallback's economics, Exercise 3 quantifies the option you will (probably) reject. Together they produce the comparison table the challenge and mini-project depend on.

These exercises cost **real money** while resources are up. An L4-backed endpoint and a spot GPU node are not free-tier. Budget **\$8–18** for the whole week if you tear down promptly; budget \$150+ if you forget. **Every exercise ends with a teardown step. It is not optional, and the mini-project's teardown gate is graded.**

## Index

1. **[Exercise 1 — Deploy a Model Garden model to a Vertex Endpoint](./exercise-01-deploy-model-garden-endpoint.md)** — deploy Gemma 3 9B from Model Garden to a Vertex AI Endpoint with GPU autoscaling, in Terraform plus a thin Python deploy step. End with a working `predict` call and a teardown. (~90 min, plus deploy wait)
2. **[Exercise 2 — Gemini API cost and latency](./exercise-02-gemini-cost-latency.py)** — call the Gemini API from a service, read the real token counts from `usage_metadata`, and compute a defensible per-1,000-token cost and a p50/p99 latency distribution from a load test. (~60 min)
3. **[Exercise 3 — vLLM on a GKE spot pool, benchmarked](./exercise-03-vllm-gke-benchmark.py)** — self-host the same open-weights model with vLLM on a GKE Standard spot GPU node pool, expose the OpenAI-compatible server, and benchmark p50/p99 and throughput against the Vertex Endpoint. (~120 min, plus node-pool wait)

## Before you start

- You completed Lecture 1's quota request and `confirm_path.py` prints "Path confirmed." If your `NVIDIA_L4_GPUS` quota is still 0, stop and request it — Exercises 1 and 3 will fail without it.
- The Week 06 GKE cluster exists (`terraform apply` in the Week 06 directory if you tore it down). Exercise 3 adds a node pool to it.
- A virtualenv with the pinned dependencies:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install \
  'google-cloud-aiplatform==1.71.*' \
  'google-genai==1.*' \
  'requests==2.32.*'
```

- These environment variables set, and exported in every shell you run the exercises in:

```bash
export PROJECT_ID="your-project-id"
export REGION="us-central1"
export CLUSTER="crunch-gke"        # your Week 06 cluster name
```

## How to work the exercises

- Read the prompt. Understand the cost shape *before* you create the resource — know what each thing bills before you `apply`.
- **Type the Terraform and the Python yourself.** Do not paste the whole file blind. The muscle memory of the `aiplatform` SDK and the GKE GPU node-pool config is the point.
- Run it. Watch the deploy. Read the error if it crashed — a quota error and a region-availability error look different and have different fixes.
- **Tear down the same session.** A GPU left up overnight is the single most expensive mistake in this course. Run the teardown step and confirm the `list` commands print nothing.
- Save your numbers. Each exercise produces a p50/p99 and a cost figure; you assemble them into one table in the challenge.

There are no solutions checked in. The course is open source — solutions live in forks. The acceptance criteria in each file tell you when you are done; the smoke output tells you what "working" looks like (your machine's numbers will differ).

## The teardown receipt

After every session, both of these must print nothing:

```bash
gcloud ai endpoints list --region="$REGION" --format='value(name)'
gcloud container node-pools list --cluster="$CLUSTER" --region="$REGION" \
  --filter='config.accelerators:*' --format='value(name)'
```

If either prints a resource, you are still paying for a GPU. Fix it before you stop.
