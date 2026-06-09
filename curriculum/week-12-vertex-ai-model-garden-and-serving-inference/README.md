# Week 12 — Vertex AI, Model Garden, and Serving Inference

Welcome to **C18 · Crunch GCP**, Week 12 — the last week of Phase 3 and the model-serving tier of the capstone. Week 09 gave you an event pipeline on Pub/Sub and Dataflow. Week 10 landed that pipeline's output as partitioned, clustered tables in BigQuery. Week 11 made you choose a transactional store and defend it. This week you put a model in front of that data and answer the only question that matters once you have data worth serving: **do you build the serving tier, or do you call someone else's?**

That question has a name in this course — the **build-vs-call decision** — and it is the single most expensive architecture call in any AI-adjacent system in 2026. Get it wrong toward "build" and you are running a GPU fleet at 11% utilization, paying for an MLOps engineer you didn't need, and explaining to finance why the inference line item is bigger than the rest of the platform combined. Get it wrong toward "call" and you wake up one morning to a 4× price change on a closed API, a data-residency finding from your auditor, and a p99 that triples whenever the provider has a busy afternoon. There is no default-correct answer. There is only a decision you can defend, and the way you defend it is with three numbers: **price per 1,000 tokens, p50/p99 latency, and where the bytes physically sit.** That is the price/latency/sovereignty triangle, and by Friday you will have measured all three corners yourself for the same open-weights model served three different ways.

This is not a "prompt engineering" week and it is not a "fine-tune a model" week. Those are real skills and they belong in a different course. This is a **platform-engineering** week. You will treat Vertex AI the way you treated GKE in Week 06 and Cloud Run in Week 07: as a managed substrate with an API, a billing surface, a scaling model, a failure mode, and an exit cost. You will deploy an open-weights model from **Model Garden** to a **Vertex AI Endpoint** with **GPU autoscaling**, you will call the **Gemini API** as a closed-weights alternative and capture its real per-token economics, and you will self-host the *same* open-weights model with **vLLM** on a **GKE spot pool** and benchmark p50/p99 against the managed endpoint. Then you will wire the three together behind a **circuit breaker** so that when your primary serving path goes unhealthy, traffic fails over to a fallback instead of failing the user — and you will deploy that client as a service on the Week 06 cluster, reading enriched rows from the Week 10 BigQuery dataset. That last piece is the mini-project: the model-serving tier of the capstone, with a teardown gate so you do not leave an A100 running over the weekend and burn your free-trial credit to zero.

The first thing to internalize is that **a model endpoint is a backend service, not a magic box.** It has a request rate, a queue, a saturation point, a cold-start cost, and a per-request marginal cost. The discipline you built operating an HTTP service — read the latency histogram, watch the saturation signal, set an autoscaler, plan for the dependency being down — is exactly the discipline that applies here. The only new variable is that the most expensive resource in the system is no longer CPU or memory; it is a GPU that costs more per hour than the rest of your node pool combined, and that you cannot get on-demand in your preferred region on a Tuesday afternoon. Everything in this week is downstream of that one fact.

The second thing to internalize is that **the three serving options are not three flavors of the same thing — they are three fundamentally different operational bargains.** A Vertex AI Endpoint is "Google runs the GPU, you pay per node-hour, you own the model artifact." The Gemini API is "Google runs everything including the model, you pay per token, you own nothing but the prompt." vLLM on GKE is "you run the GPU, you pay for the node (spot, if you're brave), you own the entire stack down to the CUDA driver." Each bargain has a price corner, a latency corner, and a sovereignty corner, and no single option wins all three. The senior move is to know which corner your specific workload cares about most and to have the numbers to prove your choice in a review.

## Learning objectives

By the end of this week, you will be able to:

- **Deploy** an open-weights model from Vertex AI Model Garden to a Vertex AI Endpoint with a GPU-backed machine type and request-driven autoscaling, entirely from Terraform plus a thin Python deploy step.
- **Distinguish** the three serving postures — managed Vertex Endpoint, Gemini API, self-hosted vLLM/TGI on GKE — by their cost model, latency profile, scaling unit, and data-residency guarantee, and place a given workload on the right one with evidence.
- **Reason** explicitly about the price/latency/sovereignty triangle: name which corner a workload optimizes for, and show why optimizing one corner sacrifices another.
- **Call** the Gemini API from a Python service, count input and output tokens correctly, and compute a defensible per-1,000-token cost and a p50/p99 latency distribution from a real load test.
- **Self-host** an open-weights model with vLLM on a GKE Standard node pool backed by spot GPUs, expose the OpenAI-compatible server, and benchmark its throughput and tail latency against the managed endpoint.
- **Build** a circuit-breaker client that treats a Vertex Endpoint as primary and the Gemini API as fallback, with health detection, half-open probing, and structured logging of every failover.
- **Measure** all three options on one workload and write a one-page recommendation that a staff engineer would sign, defending the production path on price, latency, and sovereignty.
- **Tear down** every GPU-backed resource on a schedule and verify zero residual cost — the teardown gate is graded.

## Prerequisites

- **Weeks 01–11 of C18 complete.** You can write a Terraform module with `for_each` and a remote GCS backend (Week 04), operate a GKE Standard cluster with node pools and Workload Identity (Week 06), front a service with a load balancer (Week 08), and query a partitioned BigQuery table (Week 10). This week composes all of those.
- **The Week 06 GKE cluster is reachable.** The mini-project deploys onto it. If you tore it down, the Week 06 Terraform is idempotent — `terraform apply` brings it back. Budget 15 minutes for that before Monday.
- **The Week 10 BigQuery dataset exists and has rows.** The mini-project reads enriched events from it. If you dropped the dataset, the Week 10 loader script re-creates and re-populates it; run it once before Thursday.
- **A GCP project with the Vertex AI API and the Compute Engine API enabled, and a GPU quota.** This is the one prerequisite that bites: a brand-new project has a default `NVIDIA_L4_GPUS` quota of **0** in most regions. You must request a quota increase (typically 1–4 L4s) *before* Monday — approval can take a few hours to a day. Lecture 1 walks you through the request. Do it first.
- **Python 3.12+, the `google-cloud-aiplatform` SDK, and `google-genai` SDK installed in a virtualenv.** A `requirements.txt` is pinned in the exercises.
- **A credit card on the billing account.** GPU node-hours are not free-tier. The whole week, run carefully with the teardown gate, costs **\$8–18** of real money beyond the trial. Most of that is the few hours an L4 endpoint and a spot GPU node spend online during the benchmark. Leave a GPU running for a weekend and it is \$150+. The teardown gate is not bureaucracy; it is the lesson.

## Topics covered

- **The build-vs-call decision.** When to serve your own model on a Vertex AI Endpoint, when to call the Gemini API, when to self-host vLLM/TGI on GKE. The decision matrix and the three numbers that drive it.
- **The price/latency/sovereignty triangle.** Per-token vs per-node-hour cost models; cold-start and queue latency vs steady-state latency; data residency, VPC-SC reachability, and the "where do the bytes sit" question. Why you can pick two corners but rarely all three.
- **Vertex AI Workbench.** Managed JupyterLab instances for exploration; when a notebook is the right tool and when it is a trap that hides un-versioned state.
- **Vertex AI Pipelines (Kubeflow / KFP).** The DSL, components, the compiled pipeline JSON, the managed pipeline runner. Where pipelines fit in a serving-focused week (training and batch-scoring orchestration) and why we keep them at arm's length this week.
- **Custom-container training.** The training container contract (`AIP_*` env vars, the artifact output path), pushing to Artifact Registry, submitting a `CustomJob`. Covered as background; the serving path is the focus.
- **Vertex AI Endpoints — online.** Models, Endpoints, DeployedModels, traffic split, machine types, accelerators, `min_replica_count` / `max_replica_count`, autoscaling on request rate and GPU duty cycle, request/response logging to BigQuery.
- **Vertex AI Endpoints — batch.** `BatchPredictionJob` for offline scoring against a BigQuery or GCS source; when batch beats online on cost by an order of magnitude.
- **Model Garden — open weights.** Browsing Model Garden, the one-click and Terraform deploy paths, the open-weights families available in 2026 (Gemma 3, Llama 3.x, Mistral, Qwen), license obligations, and the `publishers/` resource namespace.
- **The Gemini API — closed weights.** The `google-genai` SDK, model IDs and context windows, `generate_content`, streaming, the `usage_metadata` token counts, structured output, and the pricing model that makes per-token math possible.
- **Document AI.** Processors (form parser, OCR, custom extractor) as a worked example of a "call, don't build" managed AI service; how it relates to the build-vs-call frame.
- **vLLM and TGI on GKE.** The OpenAI-compatible server, PagedAttention and continuous batching (why vLLM's throughput dominates a naive server), the GPU node pool, the spot-capacity bargain, and the model-weights-on-a-PVC pattern.
- **Circuit breakers for model providers.** The closed/open/half-open state machine, failure thresholds, the half-open probe, and why a model fallback is a *degraded-mode* design decision, not just an error handler.
- **Benchmarking inference.** Measuring p50/p99 latency and per-1,000-token cost honestly: warm-up, concurrency, input/output token control, and why a single-request timing lies the same way a `Stopwatch` microbenchmark lies.
- **BigQuery ML continuity.** Where `CREATE MODEL` / `ML.PREDICT` fits relative to Vertex serving, briefly, to close the Phase 3 loop.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract. The GPU-backed exercises cost real money while they run — do them in a focused block and tear down the same day, not in dribs and drabs across the week.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Build-vs-call; the triangle; quota & Model Garden tour       |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Deploy a Model Garden model to a Vertex Endpoint (Ex 01)     |    1.5h  |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Wednesday | Gemini API economics + vLLM on a GKE spot pool (Ex 02, 03)   |    1.5h  |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Thursday  | Circuit-breaker fallback; benchmark the triangle (Challenge) |    0.5h  |    0h     |     2.5h   |    0.5h   |   1h     |     1.5h     |    0.5h    |     6.5h    |
| Friday    | Mini-project: build the serving tier on Week 06 GKE          |    0h    |    0h     |     0h     |    0.5h   |   1h     |     3.5h     |    0.5h    |     5.5h    |
| Saturday  | Mini-project deep work; teardown gate; benchmark write-up    |    0h    |    0h     |     0h     |    0h     |   0h     |     4h       |    0h      |     4h      |
| Sunday    | Quiz, review, recommendation memo polish                     |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                             | **7h**   | **7.5h**  | **4.5h**   | **4h**    | **5h**   | **13.5h**    | **2.5h**   | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Vertex AI docs, Model Garden, the `google-genai` SDK, vLLM, the GKE GPU guide, and the pricing pages you must read to do the cost math |
| [lecture-notes/01-the-build-vs-call-decision.md](./lecture-notes/01-the-build-vs-call-decision.md) | Vertex Endpoint vs Gemini API vs self-hosted vLLM/TGI on GKE: the three operational bargains, the decision matrix, and the worked numbers |
| [lecture-notes/02-the-price-latency-sovereignty-triangle.md](./lecture-notes/02-the-price-latency-sovereignty-triangle.md) | The triangle in depth: the cost models, the latency anatomy, the sovereignty questions, and how to benchmark all three corners honestly |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-deploy-model-garden-endpoint.md](./exercises/exercise-01-deploy-model-garden-endpoint.md) | Deploy a Model Garden open-weights model to a Vertex Endpoint with GPU autoscaling, in Terraform + Python |
| [exercises/exercise-02-gemini-cost-latency.py](./exercises/exercise-02-gemini-cost-latency.py) | Call the Gemini API from a service, count tokens, compute per-1,000-token cost and p50/p99 latency |
| [exercises/exercise-03-vllm-gke-benchmark.py](./exercises/exercise-03-vllm-gke-benchmark.py) | Self-host the same model with vLLM on a GKE spot pool and benchmark p50/p99 against the endpoint |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-circuit-breaker-fallback-and-bench.md](./challenges/challenge-01-circuit-breaker-fallback-and-bench.md) | Endpoint + Gemini circuit-breaker fallback, three-way benchmark, and a production-path recommendation |
| [quiz.md](./quiz.md) | 12 questions with an answer key |
| [homework.md](./homework.md) | Five problems with a rubric |
| [mini-project/README.md](./mini-project/README.md) | The serving tier of the capstone: a Vertex client with Gemini fallback on the Week 06 GKE cluster, reading the Week 10 BigQuery dataset, with a teardown gate |

## The "teardown gate" promise

Every week in this course ends with `terraform destroy` and a clean billing report. Week 12 makes that a graded requirement, because this is the first week where forgetting it is genuinely expensive. The marker we use all week:

```
$ gcloud ai endpoints list --region=$REGION --format='value(name)'
$ gcloud container node-pools list --cluster=$CLUSTER --region=$REGION --filter='config.accelerators:*' --format='value(name)'
(no output — both empty)
$ # Billing export confirms $0.00 of GPU SKU usage in the last hour
```

If those two `list` commands print anything after you finish a session, you are still paying. We treat a non-empty GPU resource list at the end of a work session the way Week 07 treated a build warning: it is a defect, and you fix it before you stop for the day. The mini-project's teardown gate codifies this into a script you run and a screenshot you submit.

## A note on what's *not* here

Week 12 is a serving week. It deliberately does **not** cover:

- **Fine-tuning, LoRA adapters, RLHF, or training from scratch.** Real skills, different course. We deploy *open weights as published* and *closed weights as a service*. The custom-container training contract gets one section in Lecture 1 for context, no more.
- **RAG, vector databases, and embeddings pipelines.** A serving tier is a prerequisite for RAG, not the same thing. We serve the model; what you feed it is your application's concern.
- **Prompt engineering as a discipline.** We send prompts to measure latency and cost, not to optimize quality. Your prompts this week are deliberately boring and fixed-length so the benchmarks are honest.
- **Multi-modal and video models.** Gemini does them; the economics and the serving posture are the same triangle. We stay on text so the token math is clean.
- **Model evaluation and quality benchmarking.** We benchmark *operational* properties — latency, throughput, cost — not *quality*. Quality benchmarking (MMLU, eval harnesses, LLM-as-judge) is a separate competency.

The point of Week 12 is narrow and load-bearing: make the build-vs-call decision the way a staff engineer makes it, with three numbers and a teardown receipt.

## Stretch goals

If you finish the regular work early and want to push further:

- Deploy a **second** Model Garden model (a larger one — Gemma 3 27B vs the 9B you used) to the same endpoint as a second `DeployedModel` and split traffic 90/10. Watch how the autoscaler treats the two.
- Stand up **TGI (Text Generation Inference)** alongside your vLLM deployment on the same GKE node pool and compare its continuous-batching throughput to vLLM's on identical hardware. Note which one wins on your model.
- Turn on **request/response logging** to BigQuery on your Vertex Endpoint, then write a Week-10-style SQL query over the logged predictions to compute the real production token distribution rather than your synthetic benchmark's.
- Wire a **Document AI** form-parser processor into the mini-project as a second "call, don't build" dependency and add it to your recommendation memo's triangle.
- Read the **vLLM PagedAttention paper** and write a one-paragraph note on why continuous batching changes the per-token cost math versus a request-per-GPU server.

## Up next

Continue to **Week 13 — Observability with OpenTelemetry** once your mini-project is deployed, benchmarked, and *torn down*. Week 13 instruments every service you have built in Weeks 06–12 — including this week's serving tier — with traces, metrics, and logs, defines an SLO per service, and wires a burn-rate alert. The circuit-breaker failover you build this week becomes one of the first things you put an SLO on: "99.5% of model requests succeed within 2s, counting a Gemini fallback as a success." The instinct you build this week — *measure the dependency, plan for it being down, fail to a degraded mode* — is exactly the instinct Week 13 turns into a paging policy.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
