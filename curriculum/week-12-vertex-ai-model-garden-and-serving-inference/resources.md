# Week 12 — Resources

Every resource on this page is **free to read** without a paid account. The Google Cloud documentation, the Vertex AI API reference, the `google-genai` and `google-cloud-aiplatform` SDK docs, and the vLLM / TGI / Kubeflow project docs are all public. The pricing pages are public — you must read them this week because the cost corner of the triangle is not optional. A few linked talks are on YouTube (free, no account). No paywalled books are required; the two referenced books are optional and noted as such.

A note on link rot: Google reorganizes `cloud.google.com/vertex-ai/docs/...` paths roughly once a year and renames model IDs more often than that. If a link 404s, search the exact title — the canonical pages reappear under new slugs. Model IDs (`gemini-2.x-flash`, `gemma-3-...`) change; always confirm the current ID against the live Model Garden and the pricing page before you hard-code one.

## Required reading (work it into your week)

- **Vertex AI — overview and the "deploy a model to an endpoint" guide** — the spine of Exercise 1:
  <https://cloud.google.com/vertex-ai/docs/general/deployment>
- **Vertex AI — online prediction and autoscaling** (the `min/max_replica_count`, accelerator, and autoscaling-metric reference):
  <https://cloud.google.com/vertex-ai/docs/predictions/configure-compute>
- **Vertex AI Model Garden — overview** (how open-weights models are published and deployed):
  <https://cloud.google.com/model-garden>
- **Vertex AI Model Garden — deploy open models** (the `publishers/` namespace and one-click + programmatic deploy):
  <https://cloud.google.com/vertex-ai/generative-ai/docs/open-models/use-open-models>
- **Gemini API on Vertex AI — `generate_content` and the Google Gen AI SDK** (the SDK you use in Exercise 2):
  <https://cloud.google.com/vertex-ai/generative-ai/docs/start/quickstarts/quickstart-multimodal>
- **Google Gen AI SDK for Python (`google-genai`) — reference**:
  <https://googleapis.github.io/python-genai/>
- **Vertex AI pricing** (read the *prediction* node-hour table and the *Gemini* per-token table — both corners of the triangle live here):
  <https://cloud.google.com/vertex-ai/pricing>
- **GKE — run GPUs in Standard node pools** (the node-pool accelerator config and the device plugin):
  <https://cloud.google.com/kubernetes-engine/docs/how-to/gpus>
- **GKE — use spot VMs** (the spot bargain you take in Exercise 3):
  <https://cloud.google.com/kubernetes-engine/docs/concepts/spot-vms>
- **vLLM — deploying with Kubernetes** (the OpenAI-compatible server you run on GKE):
  <https://docs.vllm.ai/en/latest/deployment/k8s.html>
- **vLLM — OpenAI-compatible server reference** (the `/v1/completions` and `/v1/chat/completions` surface):
  <https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html>

## Vertex AI — the serving surface in depth

- **`aiplatform.Model` / `aiplatform.Endpoint` Python SDK reference** — the classes you script in the deploy step:
  <https://cloud.google.com/python/docs/reference/aiplatform/latest>
- **Vertex AI — `BatchPredictionJob`** (the offline-scoring path that beats online on cost for non-interactive workloads):
  <https://cloud.google.com/vertex-ai/docs/predictions/get-batch-predictions>
- **Vertex AI — request/response logging to BigQuery** (close the Phase 3 loop: serve predictions, then query them):
  <https://cloud.google.com/vertex-ai/docs/predictions/online-prediction-logging>
- **Vertex AI — custom container training contract** (`AIP_*` env vars, the artifact output path; background for Lecture 1):
  <https://cloud.google.com/vertex-ai/docs/training/code-requirements>
- **Vertex AI Workbench — managed instances** (when a notebook is the right tool):
  <https://cloud.google.com/vertex-ai/docs/workbench/instances/introduction>
- **Vertex AI Pipelines (Kubeflow) — introduction**:
  <https://cloud.google.com/vertex-ai/docs/pipelines/introduction>
- **Kubeflow Pipelines (KFP) SDK v2 docs** — the DSL you compile to pipeline JSON:
  <https://www.kubeflow.org/docs/components/pipelines/>
- **Document AI — overview and processors** (the worked "call, don't build" example):
  <https://cloud.google.com/document-ai/docs/overview>
- **Terraform `google_vertex_ai_endpoint` resource** (the IaC surface for Exercise 1):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/vertex_ai_endpoint>

## The Gemini API and closed-weights serving

- **Gemini API — models and context windows** (confirm the current model IDs here, not from memory):
  <https://ai.google.dev/gemini-api/docs/models>
- **Gemini API — token counting and `usage_metadata`** (how you get `prompt_token_count` and `candidates_token_count` for the cost math):
  <https://ai.google.dev/gemini-api/docs/tokens>
- **Gemini API — generating content and streaming**:
  <https://ai.google.dev/gemini-api/docs/text-generation>
- **Gemini API — structured output (JSON mode / response schema)**:
  <https://ai.google.dev/gemini-api/docs/structured-output>
- **Gemini on Vertex AI vs the AI Studio Gemini API — the difference that matters for sovereignty** (regional endpoints, VPC-SC, data governance):
  <https://cloud.google.com/vertex-ai/generative-ai/docs/learn/overview>

## Self-hosting — vLLM, TGI, and the GPU node pool

- **vLLM — project home and docs**:
  <https://docs.vllm.ai/>
- **vLLM — the PagedAttention paper** ("Efficient Memory Management for Large Language Model Serving with PagedAttention", Kwon et al.) — read the abstract and §4 for why continuous batching dominates throughput:
  <https://arxiv.org/abs/2309.06180>
- **vLLM — engine arguments** (the `--max-model-len`, `--gpu-memory-utilization`, `--tensor-parallel-size` knobs that decide whether your model fits):
  <https://docs.vllm.ai/en/latest/serving/engine_args.html>
- **Hugging Face TGI (Text Generation Inference) — docs** (the vLLM alternative; the stretch goal compares them):
  <https://huggingface.co/docs/text-generation-inference/index>
- **GKE — about GPUs** (supported accelerators, the `cloud.google.com/gke-accelerator` node selector, time-sharing and MIG):
  <https://cloud.google.com/kubernetes-engine/docs/concepts/gpus>
- **GKE — autoscaling GPU node pools** (cluster autoscaler + node auto-provisioning for accelerators):
  <https://cloud.google.com/kubernetes-engine/docs/how-to/node-auto-provisioning>
- **NVIDIA — L4 and L40S GPU spec sheets** (so you can reason about memory ceilings — an L4 has 24 GB, which decides which models fit):
  <https://www.nvidia.com/en-us/data-center/l4/>
- **Hugging Face — Gemma 3 model card** (license obligations and the served weights):
  <https://huggingface.co/google/gemma-3-9b-it>

## Cost, quota, and FinOps for inference

- **Vertex AI pricing — prediction (node-hour) and generative (per-token)**:
  <https://cloud.google.com/vertex-ai/pricing>
- **Compute Engine — GPU pricing** (the underlying SKU when you self-host on GKE; spot vs on-demand):
  <https://cloud.google.com/compute/gpus-pricing>
- **GCP — GPU quota and how to request an increase** (do this first — a fresh project has 0 GPU quota):
  <https://cloud.google.com/compute/resource-usage#gpu_quota>
- **GCP — billing export to BigQuery** (the receipt for the teardown gate; you query the GPU SKU line):
  <https://cloud.google.com/billing/docs/how-to/export-data-bigquery>
- **Vertex AI — quotas and limits**:
  <https://cloud.google.com/vertex-ai/docs/quotas>

## Circuit breakers and resilient client design

- **Martin Fowler — "CircuitBreaker"** (the canonical description of closed/open/half-open):
  <https://martinfowler.com/bliki/CircuitBreaker.html>
- **Google SRE Book — "Handling Overload" and "Addressing Cascading Failures"** (why a fallback is a load-shedding decision, not just an error handler):
  <https://sre.google/sre-book/handling-overload/>
- **`google-api-core` retry and timeout config** (the SDK-level retry surface you tune underneath your circuit breaker):
  <https://googleapis.dev/python/google-api-core/latest/retry.html>
- **`pybreaker` — a small, well-tested Python circuit-breaker library** (you can use it or hand-roll the state machine in the challenge):
  <https://github.com/danielfm/pybreaker>

## Benchmarking inference honestly

- **`locust` — distributed load testing in Python** (one way to drive the p50/p99 measurement):
  <https://docs.locust.io/>
- **`vegeta` — a constant-rate HTTP load tester in Go** (the no-warm-up-bug tool; constant request rate is the right primitive for tail-latency):
  <https://github.com/tsenart/vegeta>
- **vLLM — `benchmark_serving.py`** (the project's own serving benchmark, the reference for how to measure TTFT and inter-token latency):
  <https://github.com/vllm-project/vllm/blob/main/benchmarks/benchmark_serving.py>
- **Gil Tene — "How NOT to Measure Latency"** (the talk every engineer who reports a p99 should have watched; coordinated omission is the trap):
  search YouTube for "Gil Tene How NOT to Measure Latency".

## BigQuery ML continuity (closing the Phase 3 loop)

- **BigQuery ML — `CREATE MODEL` and `ML.PREDICT`** (where in-warehouse inference fits relative to Vertex serving):
  <https://cloud.google.com/bigquery/docs/bqml-introduction>
- **BigQuery ML — remote models over a Vertex Endpoint** (call your Week-12 endpoint from a SQL query):
  <https://cloud.google.com/bigquery/docs/remote-models-intro>

## Talks worth watching (all free, no account)

- **"Serving LLMs in production with vLLM"** — the project maintainers' overview of PagedAttention and continuous batching. Search YouTube for "vLLM serving production".
- **"Vertex AI: from notebook to endpoint"** — a Google Cloud Next session walking the deploy path end to end. Search YouTube for "Vertex AI deploy endpoint Next".
- **Gil Tene — "How NOT to Measure Latency"** — coordinated omission, the reason most reported p99s are fiction.
- **"GPUs on GKE"** — a Google Cloud session on node pools, time-sharing, and spot capacity for accelerators. Search YouTube for "GKE GPU node pool".

## Optional books (not required for any exercise)

- **"Designing Machine Learning Systems" — Chip Huyen** (O'Reilly). The chapters on model serving and the build-vs-buy framing are the best book-length treatment of this week's decision. Optional.
- **"Reliable Machine Learning" — Chen, Murphy, Kumar, et al.** (O'Reilly). The SRE-for-ML book; the chapters on serving and on-call map directly onto Weeks 12–14. Optional.

## How to use this resource list

The lectures cite specific URLs from this page at decision points. The links you should read end-to-end *this week* are:

1. **Vertex AI pricing** — both tables. You cannot do the triangle without them. Do not skip.
2. **Vertex AI "configure compute" (autoscaling)** — foundational for Exercise 1.
3. **vLLM "deploying with Kubernetes"** — foundational for Exercise 3.
4. **Gemini API "token counting"** — decisive for the cost math in Exercise 2.
5. **Gil Tene's "How NOT to Measure Latency"** — ~40 minutes, decisive for the challenge benchmark.

The rest are reference material — bookmark them and return when a specific question arises.

---

*Bookmarks decay. If a Google Cloud link rots, search the exact page title; the canonical docs reappear under new slugs. Always confirm a model ID and a price against the live page before you hard-code it — both change more often than this file does.*
