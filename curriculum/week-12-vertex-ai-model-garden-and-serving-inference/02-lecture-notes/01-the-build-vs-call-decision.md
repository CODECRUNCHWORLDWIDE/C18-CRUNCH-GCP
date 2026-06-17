# Lecture 1 — The Build-vs-Call Decision: Vertex Endpoint vs. Gemini API vs. self-hosted vLLM/TGI on GKE

> **Reading time:** ~75 minutes. **Hands-on time:** ~45 minutes (you request GPU quota, tour Model Garden, and deploy a tiny endpoint to confirm the path works).

This is the lecture that earns you the right to put a model in production. Everything else this week — autoscaling, the Gemini SDK, vLLM, the circuit breaker, the benchmark — is downstream of one decision you make on Monday: **for this workload, do I build the serving tier, or do I call someone else's?** There are exactly three answers in the Google Cloud world, and they are not three flavors of the same thing. They are three different *operational bargains*, each with a price, a latency profile, a scaling unit, a failure mode, and an exit cost. A senior engineer does not have a favorite. A senior engineer has a decision matrix and three numbers.

By the end of this lecture you can state the three bargains precisely, place a workload on the right one with evidence, and explain — in a review, to a staff engineer who will push back — why optimizing one corner of the triangle costs you another. You will also have a working GPU quota and a confirmed deploy path, so that Tuesday's exercise does not stall on a quota request that takes a day to approve.

## 1.1 — The three bargains, stated precisely

Forget marketing names for a moment. Here is what you are actually choosing between.

**Bargain A — Vertex AI Endpoint (managed serving of *your* model artifact).** Google runs the GPU. You bring a model — an open-weights model from Model Garden, or a model you trained — and Google hosts it behind an HTTPS endpoint with autoscaling, request logging, and an SLA. You pay **per node-hour** for the machine type and accelerator, whether or not a request is in flight, for as long as at least one replica is up. You own the model artifact and the version; you do not own the kernel, the driver, or the inference server. The scaling unit is a *replica* (a VM with one or more GPUs). The minimum bill is `min_replica_count × node-hour-rate`, which for a single L4 replica is on the order of **\$0.60–0.85/hour** continuously, plus the prediction request charges.

**Bargain B — Gemini API (managed serving of *Google's* model).** Google runs everything: the GPU, the inference server, *and* the model. You own nothing but the prompt and the response. You pay **per token** — separate input and output rates — with **zero idle cost.** Send no requests, pay nothing. The scaling unit is a *token*; there is no replica to manage, no autoscaler to tune, no cold start you control. The trade is total: you cannot inspect the weights, you cannot pin a version forever (models are deprecated on a schedule), and the data leaves your VPC unless you use the Vertex-hosted regional endpoints with VPC-SC.

**Bargain C — self-hosted vLLM/TGI on GKE (you run the whole stack).** You provision a GPU node pool on your own GKE cluster (Week 06), you run an inference server — vLLM or TGI — in a Pod, you mount the model weights, and you expose an OpenAI-compatible HTTP API. You pay the **Compute Engine GPU SKU** for the node, which you can get on **spot** for 60–70% off if you can tolerate preemption. You own the entire stack down to the CUDA driver. The scaling unit is a *Pod on a GPU node*; you tune the HPA and the cluster autoscaler yourself. The minimum bill is the node-hour of however many GPU nodes you keep warm — but spot capacity can vanish mid-request, and you are now operating a GPU fleet, which is a job.

Three bargains. Write them on a card:

| | Who runs the GPU | What you pay for | Idle cost | Scaling unit | You own |
|---|---|---|---|---|---|
| **A. Vertex Endpoint** | Google | node-hour + requests | **Yes** (min replicas) | replica (VM+GPU) | model artifact + version |
| **B. Gemini API** | Google | per token (in/out) | **No** | token | prompt only |
| **C. vLLM/TGI on GKE** | You | Compute GPU SKU (spot-able) | **Yes** (warm nodes) | Pod on GPU node | the entire stack |

Everything else in this lecture is elaboration on this table.

## 1.2 — The decision matrix: which bargain for which workload

The bargain you pick is a function of the workload, not of taste. Here is the matrix a staff engineer carries in their head. The columns are the workload properties that actually move the decision.

| Workload property | Favors **A: Vertex Endpoint** | Favors **B: Gemini API** | Favors **C: vLLM on GKE** |
|---|---|---|---|
| **Traffic shape** | Steady, predictable, high-duty-cycle | Spiky, unpredictable, often near-zero | Steady AND high-volume enough to amortize a fleet |
| **Volume** | Medium-high, sustained | Low-to-medium, bursty | Very high, sustained |
| **Model** | A specific open-weights model you must pin | Whatever Google's best closed model is | A specific open-weights model AND you need control |
| **Sovereignty** | Stays in your project/region; VPC-SC-able | Leaves to a Google service (unless Vertex-regional) | Stays entirely in your VPC, you control egress |
| **Latency floor** | Good steady-state, you eat cold starts | Excellent — Google's fleet is always warm | Best possible if you tune it; worst if you don't |
| **Cost at low volume** | Bad (you pay for idle replicas) | Excellent (pay nothing when idle) | Bad (you pay for idle nodes) |
| **Cost at high volume** | Good (node-hour amortizes) | Bad (per-token adds up fast) | **Best** (spot GPU + continuous batching) |
| **Ops burden** | Low (Google operates it) | Lowest (Google operates everything) | High (you operate a GPU fleet) |
| **Customization** | Medium (your artifact, their server) | None (their model, their server) | Total (your model, your server, your kernel) |

Read the matrix as a sieve, not a scorecard. Start with the hard constraints — the ones that are non-negotiable — and let them eliminate options before you reason about cost.

**Sovereignty is usually the first sieve.** If your compliance posture says "model inputs containing PII may not leave the project's VPC perimeter," Bargain B (the AI Studio Gemini API) is out before you look at price — though Gemini *on Vertex AI* with a regional endpoint inside a VPC-SC perimeter may still qualify; that is a distinction your auditor cares about and you must get right. If your data-residency requirement is "EU only," you must confirm the model is served from an EU region in whichever bargain you pick. Sovereignty does not care about your latency budget. It eliminates options.

**Traffic shape is usually the second sieve.** If your traffic is near-zero most of the day and spikes unpredictably — an internal tool, a low-volume support classifier — then both A and C make you pay for idle GPUs you are not using, and B's pay-per-token-with-zero-idle model wins by a mile on cost even if the per-token rate looks high. Conversely, if you are running a million inferences an hour, twenty-four hours a day, the per-token bill on B becomes grotesque and the node-hour amortization on A or the spot-GPU economics on C dominate.

**Volume × control is usually the tiebreaker.** Once sovereignty and traffic shape have narrowed you to one or two options, the deciding factor is whether your volume is high enough to amortize a self-managed fleet *and* whether you need the control that fleet buys you. vLLM on a spot GKE pool is the cheapest per token at high volume — continuous batching squeezes more tokens out of a GPU than any per-request server — but only if your volume keeps the fleet busy and you have the ops maturity to run it. If you are not running a GPU fleet at high utilization, you are setting money on fire.

## 1.3 — The three numbers, worked

The decision matrix tells you which options survive the sieves. The three numbers tell you which survivor wins. You will *measure* all three this week; here we establish how to *estimate* them so you can sanity-check your measurements.

### Number one: price per 1,000 tokens

This is the great equalizer because it converts all three bargains into the same unit. For Bargain B it is published directly. For A and C you derive it from the node-hour rate and the throughput.

For **Bargain B (Gemini API)**, the published rate is per million tokens, split input and output. Suppose (confirm against the live pricing page — these change) input is \$0.075 per million tokens and output is \$0.30 per million for a Flash-class model. A request with 500 input tokens and 200 output tokens costs:

```text
(500 / 1_000_000) * $0.075  +  (200 / 1_000_000) * $0.30
=  $0.00003750  +  $0.00006000
=  $0.0000975  per request
```

Per 1,000 such requests: **\$0.0975.** Idle cost: zero.

For **Bargain A or C**, you start from a node-hour rate and a measured throughput. Suppose an L4 endpoint costs \$0.71/node-hour and your benchmark shows the deployed Gemma-3-9B model sustains 1,200 output tokens/second across concurrent requests at acceptable latency. Then:

```text
tokens per hour  = 1200 tok/s * 3600 s  = 4_320_000 tokens/hour
cost per token   = $0.71 / 4_320_000    = $0.000000164 per output token
cost per 1M out  = $0.164  per million output tokens
```

That is **less than the Gemini output rate** — but *only if the GPU stays busy.* At 10% duty cycle the effective rate is 10× worse: \$1.64 per million output tokens, now far worse than Gemini. This is the entire game. The self-hosted per-token cost is a function of utilization, and utilization is a function of traffic shape. The instant your traffic dips, the managed-API economics win.

The Python you use to compute this from a real run is small and you will reuse it all week:

```python
def cost_per_1k_requests_token_model(
    input_tokens: int,
    output_tokens: int,
    input_price_per_million: float,
    output_price_per_million: float,
) -> float:
    """Per-1000-request cost for a per-token (e.g. Gemini API) bargain."""
    per_request = (
        input_tokens / 1_000_000 * input_price_per_million
        + output_tokens / 1_000_000 * output_price_per_million
    )
    return per_request * 1000


def effective_cost_per_million_tokens_node_model(
    node_hour_rate: float,
    sustained_output_tokens_per_second: float,
    duty_cycle: float,
) -> float:
    """Per-million-output-token cost for a node-hour (Vertex Endpoint / vLLM) bargain.

    duty_cycle in (0, 1]: the fraction of wall-clock time the GPU is actually
    producing tokens. At duty_cycle=1.0 the GPU is saturated; at 0.1 it is
    mostly idle and you are paying for nothing.
    """
    if not 0 < duty_cycle <= 1:
        raise ValueError("duty_cycle must be in (0, 1]")
    effective_tokens_per_hour = sustained_output_tokens_per_second * 3600 * duty_cycle
    cost_per_token = node_hour_rate / effective_tokens_per_hour
    return cost_per_token * 1_000_000


if __name__ == "__main__":
    gemini = cost_per_1k_requests_token_model(500, 200, 0.075, 0.30)
    print(f"Gemini API: ${gemini:.4f} per 1000 requests")

    for duty in (1.0, 0.5, 0.1):
        endpoint = effective_cost_per_million_tokens_node_model(0.71, 1200, duty)
        print(f"L4 endpoint @ {duty:.0%} duty: ${endpoint:.3f} / 1M output tokens")
```

Run that and watch the endpoint cost cross over the Gemini cost as duty cycle falls. That crossover point — the utilization at which build becomes cheaper than call — is the single most important number in your recommendation memo.

### Number two: p50/p99 latency

Latency is not one number; it is a distribution, and you report two points on it: the median (p50, the typical experience) and the 99th percentile (p99, the tail that defines your SLO). Reporting only a mean is the mark of someone who has not read Gil Tene's "How NOT to Measure Latency" — the mean hides the tail, and the tail is what pages you.

The latency anatomy differs by bargain:

- **Bargain B (Gemini API)** has effectively no cold start — Google's fleet is always warm — but it has *network* latency to a Google service and *queue* latency when the shared fleet is busy. Its p50 is excellent; its p99 is largely outside your control.
- **Bargain A (Vertex Endpoint)** has a cold start when the autoscaler adds a replica (model load from storage to GPU memory, which for a 9B model is tens of seconds), and queue latency at the replica when concurrency exceeds the batch size. Steady-state p50 is good; p99 spikes during scale-up events.
- **Bargain C (vLLM on GKE)** has the best achievable p50 if you tune it — continuous batching keeps the GPU busy without making any single request wait long — but the *worst* p99 if a spot node is preempted mid-request, because now the request fails and retries on a node that may not exist yet.

You will measure these properly in Lecture 2 and the challenge. The estimation rule for Monday: assume Gemini's p50 is your floor (it is the always-warm option), assume your endpoint's p50 is 1.2–2× that, and assume both p99s are 3–10× their respective p50s under load. Then go measure, because these estimates are wrong often enough to be dangerous.

### Number three: where the bytes sit (sovereignty)

This number is not a number; it is a yes/no answer to a list of questions, and it is the corner engineers most often get wrong because it does not show up in a benchmark. The questions:

1. **What region does the inference physically run in?** For a Vertex Endpoint and for vLLM on GKE, you choose the region and it is enforced. For the AI Studio Gemini API, you do not directly choose; for Gemini on Vertex AI you choose a regional endpoint.
2. **Does the request leave your VPC?** A Vertex Endpoint and vLLM on GKE can be reached over Private Service Connect / internal load balancing and wrapped in a VPC-SC perimeter (Week 14). A naive call to the public Gemini API egresses to a Google service.
3. **Is the data used to train Google's models?** Read the data-governance terms for the specific surface you use. The enterprise Vertex terms differ from the consumer AI Studio terms. Your auditor will ask; have the citation ready.
4. **Can you pin a version forever?** With an open-weights model on A or C, yes — you control the artifact. With B, no — closed models are deprecated on a schedule, and "the model changed under us" is a real production incident.

Sovereignty is the corner that turns a cheaper, faster option into a non-starter. It is also the corner that justifies the cost of building when the numbers alone would say call. Treat it as a first-class input, not an afterthought.

## 1.4 — Model Garden: where open weights come from

Model Garden is Vertex AI's catalog of models you can deploy. In 2026 it spans three categories that matter for the build-vs-call decision:

- **Google first-party models** (Gemini, served as an API — Bargain B — and not "deployed" in the endpoint sense).
- **Open-weights models** you can deploy to your own endpoint (Bargain A) or download and self-host (Bargain C). The 2026 families you will actually reach for: **Gemma 3** (Google's open family, 1B/4B/9B/27B-class, the natural default on GCP because it is first-party-supported), **Llama 3.x** (Meta), **Mistral / Mixtral**, and **Qwen**. License obligations vary — Gemma has its own license, Llama has the Llama Community License with a usage-threshold clause — and you must read the model card's license before you ship. License compliance is a real review item.
- **Third-party partner models** served as managed APIs (Anthropic's Claude, AI21, and others are available through Vertex's Model-as-a-Service surface — a Bargain-B-shaped option with a different provider).

Open-weights models in Model Garden live under the `publishers/` resource namespace, e.g. `publishers/google/models/gemma-3-9b-it`. You deploy one to an endpoint either through the console's one-click deploy, through the `aiplatform` Python SDK, or through Terraform plus a thin Python step (the path Exercise 1 takes, because one-click deploys leave no artifact you can review or reproduce).

The one-click deploy is a trap for the same reason a hand-edited production resource is a trap: it is un-versioned, un-reviewed, and un-reproducible. You will use it once on Monday to confirm the path works and to read the machine-type and accelerator options it picks, and then never again. From Tuesday on, the endpoint comes from Terraform.

## 1.5 — A confirm-the-path walkthrough (do this Monday)

Before anything else, request GPU quota. A fresh project has `NVIDIA_L4_GPUS` quota of 0 in most regions. Without it, Tuesday's `terraform apply` fails with a quota error and you lose a day waiting for approval. Request it now:

```bash
# Set your project and a region with L4 availability (us-central1 is a safe default).
export PROJECT_ID="your-project-id"
export REGION="us-central1"
gcloud config set project "$PROJECT_ID"

# Enable the APIs this week needs.
gcloud services enable \
  aiplatform.googleapis.com \
  compute.googleapis.com \
  container.googleapis.com \
  --project="$PROJECT_ID"

# Inspect your current L4 quota in the region. If "limit" is 0, request an increase
# via the console: IAM & Admin -> Quotas -> filter "NVIDIA L4 GPUs" -> region ->
# Edit Quotas -> request 1-4. Approval is usually hours, sometimes a day.
gcloud compute regions describe "$REGION" \
  --format="value(quotas[].metric, quotas[].limit)" \
  | tr ',' '\n' | grep -i l4 || echo "No L4 quota line found — request one in the console."
```

While the quota approves, tour Model Garden in the console (Vertex AI → Model Garden), filter to "Open" models, open the Gemma 3 9B card, and read three things: the **license**, the **recommended machine type and accelerator** for serving (this is what you will encode in Terraform), and the **context window**. These three facts feed directly into Exercise 1.

Then confirm the SDK deploy path with the smallest possible test — list the models you can publish from, without deploying anything that costs money yet:

```python
"""confirm_path.py — verify the Vertex AI SDK is wired and you can see Model Garden.

This does NOT deploy anything. It confirms auth, the SDK, and the region are
correct so that Tuesday's exercise does not fail on a setup problem.
"""
import os

from google.cloud import aiplatform

PROJECT_ID = os.environ["PROJECT_ID"]
REGION = os.environ.get("REGION", "us-central1")

aiplatform.init(project=PROJECT_ID, location=REGION)

# Endpoints you already have in this region (should be empty on a clean project).
endpoints = aiplatform.Endpoint.list()
print(f"Existing endpoints in {REGION}: {len(endpoints)}")
for ep in endpoints:
    print(f"  - {ep.display_name} ({ep.resource_name})")

# Confirm the prediction client can be constructed (no call made).
from google.cloud.aiplatform_v1 import PredictionServiceClient

client = PredictionServiceClient(
    client_options={"api_endpoint": f"{REGION}-aiplatform.googleapis.com"}
)
print(f"Prediction client ready for {REGION}-aiplatform.googleapis.com")
print("Path confirmed. You are ready for Exercise 1.")
```

If that script prints "Path confirmed" and your quota request is approved, you are set for the week. If it raises a permission error, your account is missing `roles/aiplatform.user`; grant it and retry. Do not proceed to the GPU exercises until both checks pass — a quota or auth failure mid-deploy is the most common reason a learner loses a day this week.

## 1.6 — Vertex AI Endpoints: the serving object model

When you deploy on Bargain A, four objects are in play and conflating them causes most of the confusion in the SDK:

- **`Model`** — an artifact in the Vertex Model Registry. For a Model Garden open model, the model points at the published weights and a serving container. A `Model` is not serving anything; it is a registered thing that *can* be deployed.
- **`Endpoint`** — a stable HTTPS resource with a URL and an autoscaling group behind it. An `Endpoint` with nothing deployed serves nothing but exists and costs nothing.
- **`DeployedModel`** — the binding of a `Model` to an `Endpoint` on a specific machine type with a specific accelerator and replica range. *This* is what costs money: deploying a model creates replicas, and replicas are VMs with GPUs.
- **Traffic split** — when more than one `DeployedModel` is on an `Endpoint`, a percentage map decides which deployed model serves each request. This is how you do a canary or an A/B.

The lifecycle that matters for your bill: creating an `Endpoint` is free; deploying a `Model` to it spins up `min_replica_count` replicas and starts billing; un-deploying the model scales to zero and stops the replica billing; deleting the endpoint removes the resource. **The teardown gate checks that you un-deployed and deleted, because an endpoint with a deployed model at `min_replica_count = 1` bills around the clock whether or not you send it a single request.**

Here is the autoscaling config you will encode in Terraform, expressed first as the SDK call so you understand each knob:

```python
# The deploy call (Exercise 1 does this from Terraform's local-exec or a thin
# Python step; shown here so each parameter is legible).
deployed = model.deploy(
    endpoint=endpoint,
    machine_type="g2-standard-12",          # the L4-capable G2 family
    accelerator_type="NVIDIA_L4",            # the GPU
    accelerator_count=1,                     # one L4 per replica
    min_replica_count=1,                     # the floor — this is what you pay when idle
    max_replica_count=3,                     # the ceiling — caps your spend under load
    autoscaling_target_accelerator_duty_cycle=60,  # scale up when GPU >60% busy
    traffic_percentage=100,
    sync=True,
)
```

The `autoscaling_target_accelerator_duty_cycle` is the knob people misunderstand. It is *not* "scale at 60% CPU." It is "add a replica when the GPU duty cycle exceeds 60%." GPUs are the constraint; you scale on GPU saturation, not CPU. Set `min_replica_count` to the lowest number that meets your latency floor for baseline traffic, and `max_replica_count` to the highest number your *budget* tolerates, not the highest your traffic might want — an unbounded ceiling on a GPU autoscaler is how a traffic spike becomes a billing incident.

## 1.7 — Online vs. batch, and why batch is sometimes 10× cheaper

Bargain A has two prediction modes, and choosing the wrong one is a common, expensive mistake.

**Online prediction** keeps replicas warm and serves requests with low latency. You pay for the replicas continuously. This is correct for interactive workloads — a user is waiting for the answer.

**Batch prediction** (`BatchPredictionJob`) spins up resources, scores a whole dataset from BigQuery or GCS, writes the results, and tears the resources down. There is no warm replica, no idle cost, and the throughput per dollar is far better because the system batches aggressively without a latency constraint. This is correct for offline workloads — nobody is waiting, you want a column of predictions added to a table by morning.

The rule: **if no human is waiting on the individual prediction, you almost certainly want batch, and it is often an order of magnitude cheaper than streaming the same volume through an online endpoint.** The Week 10 BigQuery dataset is full of exactly the kind of data you would score in batch — enrich a day's events overnight, not one HTTP request at a time. Exercise 1 deploys an online endpoint because the mini-project is interactive; but in your recommendation memo, the question "could this be batch instead?" should be asked before "which online bargain?", because a yes there beats every online option on cost.

## 1.8 — The two managed-AI services that are pure "call, don't build"

Two GCP services exist entirely to make the build-vs-call decision for you, in the "call" direction, for a narrow task:

- **Document AI** — extract structured data from documents (invoices, forms, IDs, contracts). You pick a **processor** (a pre-built one like the form parser or OCR, or a custom extractor you train with a handful of labeled samples), send a document, and get structured fields back. You would never build this from scratch; the bargain is "pay per page, own nothing, get a maintained extractor." It is the cleanest example of the call side of the decision: a task narrow enough that no sane team builds it.
- **BigQuery ML** — train and serve simple models *inside the warehouse* with `CREATE MODEL` and `ML.PREDICT`, or call a Vertex Endpoint from SQL via a remote model. For tabular prediction over data that already lives in BigQuery (Week 10), this collapses the entire serving tier into a SQL query. It is "call, don't build" for the in-warehouse case.

Both are worth a section because they reframe the week's question. The build-vs-call decision is not always "which GPU bargain." Sometimes the right answer is "this is a document-extraction problem, use Document AI" or "this is a tabular-prediction problem over data already in BigQuery, use BQML" — and you never touch a GPU at all. The senior move is to recognize the task shape before you reach for the heavyweight option.

## 1.9 — Custom-container training, in one breath

This is a serving week, so training gets one section for context. If you must serve a model you trained (rather than an off-the-shelf open model), the path is:

1. Write a training container that obeys the Vertex contract: read hyperparameters and data paths from `AIP_*` environment variables, write the trained artifact to the path in `AIP_MODEL_DIR` (a GCS path Vertex provides), and exit 0 on success.
2. Push the container to Artifact Registry (the registry you have used since Week 04).
3. Submit a `CustomJob` (or a `HyperparameterTuningJob`) that runs the container on a machine type with accelerators.
4. Register the resulting artifact as a `Model`, then deploy it exactly as you would a Model Garden model.

The serving half of that — register a `Model`, deploy to an `Endpoint` — is identical whether the model came from Model Garden or from your own training job. That is the point of the abstraction: *serving does not care where the artifact came from.* This week we use a Model Garden artifact so you do not spend the week training; but the endpoint, the autoscaling, the cost model, and the teardown are the same either way.

The contract a training container obeys, in the smallest honest form, is just "read the inputs Vertex hands you via env vars, write the artifact to the path it hands you, exit 0":

```python
"""train.py — the skeleton of a Vertex custom-training container's entrypoint.

Vertex sets AIP_* env vars at runtime. The only hard contract: write the trained
artifact to AIP_MODEL_DIR (a GCS path) so Vertex can register it as a Model.
"""
import os

# Vertex provides these. AIP_MODEL_DIR is a gs:// path Vertex will read after exit.
model_dir = os.environ["AIP_MODEL_DIR"]
training_data = os.environ.get("AIP_TRAINING_DATA_URI", "")

def train_and_save(output_dir: str) -> None:
    # ... your training loop produces a model object `model` ...
    # The artifact must land under output_dir; Vertex registers whatever it finds.
    # e.g. model.save_pretrained(output_dir) for a transformers model, or
    #      joblib.dump(model, os.path.join(output_dir, "model.joblib")) for sklearn.
    raise NotImplementedError("your training loop goes here")

if __name__ == "__main__":
    train_and_save(model_dir)
    # Exit 0 signals success; Vertex then registers the artifact in AIP_MODEL_DIR.
```

You push that container to Artifact Registry, submit it as a `CustomJob` on a GPU machine type, and the artifact it writes becomes a `Model` you deploy with the exact `model.deploy(...)` call from §1.6. We will not run this loop this week — the open-weights path skips it entirely — but seeing the contract makes the abstraction concrete: an endpoint serves an artifact, and an artifact is just bytes in a registry, regardless of whether they came from Meta, Google, or your own training job.

## 1.10 — Putting it together: a decision you can defend

Here is the decision, as you would write it at the top of a design doc, for the mini-project's workload (an interactive classifier/enricher over Week 10's BigQuery events):

> **Workload:** interactive enrichment of incoming events — a human or a downstream service waits on each call. Volume is medium and spiky (business hours, with quiet nights). Inputs may contain customer identifiers; data-residency requirement is "stays in our region, reachable inside the VPC." We must be able to pin behavior — a silent model change is a production incident.
>
> **Sieve 1 (sovereignty):** the residency + VPC reachability requirement rules out the public AI Studio Gemini API as the *primary* path. Gemini *on Vertex AI*, regional, inside VPC-SC, survives — and we keep it as a *fallback* because a degraded answer beats an outage. The "pin behavior" requirement favors an open-weights model we control for the primary.
>
> **Sieve 2 (traffic shape):** spiky, with quiet nights, argues against a self-hosted vLLM fleet we keep warm 24/7 — we would pay for idle GPUs all night. It also argues against a high `min_replica_count` on a Vertex Endpoint.
>
> **Decision:** primary path is a **Vertex AI Endpoint** serving Gemma 3 9B at `min_replica_count = 1`, `max = 3`, autoscaling on GPU duty cycle — we own the artifact, it stays in-region and VPC-reachable, and the cost is bounded. Fallback is the **Gemini API** behind a circuit breaker, for when the endpoint is unhealthy or saturated — zero idle cost, always warm, accepted as a degraded mode. We reject **vLLM on GKE** for *production* on this workload (the traffic shape does not amortize a fleet) but we **benchmark it** to quantify the cost we are leaving on the table, so the rejection is evidence-based, not reflexive.

That paragraph is the entire week in miniature. Tuesday you build the primary. Wednesday you measure the fallback and the rejected option. Thursday you wire the circuit breaker and benchmark all three. The mini-project ships the decision as code on the Week 06 cluster, and tears it down so the decision does not cost you a weekend's GPU bill.

## 1.11 — Workbench and Pipelines: the exploration and orchestration tier

Two Vertex AI surfaces sit *upstream* of serving and deserve naming so you know where they fit and, just as importantly, where they do not.

**Vertex AI Workbench** is managed JupyterLab — a notebook instance with the GCP SDKs pre-installed, IAM-integrated, and optionally GPU-backed. It is the right tool for *exploration*: poking at a model, sketching a prompt, eyeballing a dataset, prototyping a deploy call before you commit it to Terraform. It is a *trap* the moment it becomes load-bearing. A notebook hides state — cell execution order, in-memory variables, un-committed edits — and a serving path that only works "if you run the cells in the right order on Tuesday's instance" is not a serving path; it is a liability. The rule: explore in Workbench, then move *everything that runs in production* into version-controlled code (the Terraform and the `deploy.py` you wrote above). The confirm-the-path script in §1.5 is exactly the kind of thing you might first write in a notebook and then graduate into a repo. Notebooks are a scratchpad, not a deployment artifact.

**Vertex AI Pipelines** runs Kubeflow Pipelines (KFP) — a DAG of containerized steps, compiled to a pipeline JSON and executed by a managed runner. Pipelines are how you orchestrate the *training* and *batch-scoring* workflows that feed serving: ingest data, preprocess, train, evaluate, register the model, kick off a batch prediction. A KFP component is a Python function (or a container) with typed inputs and outputs; the SDK compiles the DAG and the managed runner executes each step on its own resources with lineage tracking. In a serving-focused week, pipelines stay at arm's length — we are deploying an off-the-shelf open model, so there is no training DAG to orchestrate. But know the shape: a `@dsl.component` decorates a function into a step, `@dsl.pipeline` composes steps into a DAG, `compiler.Compiler().compile(...)` emits the JSON, and `PipelineJob(...).submit()` runs it. When you graduate from serving an open model to serving one you trained, the training half of that lives in a pipeline, and the serving half is exactly the endpoint deploy you wrote in §1.6.

The reason both matter to the build-vs-call decision: they are where the *build* path's hidden cost lives. "Call" (Gemini) needs neither — you send a prompt. "Build your own trained model" needs a Workbench for exploration, a Pipeline for repeatable training, an Artifact Registry for the container, and an MLOps engineer to own all of it. When you tally the cost of the build side of the decision, the GPU node-hours are the *visible* cost; the Workbench, the Pipelines, and the human who maintains them are the *invisible* one. A staff engineer prices both.

## 1.12 — What to take into Lecture 2

Lecture 2 goes deep on the triangle's three corners — the exact cost models, the latency anatomy under concurrency, and how to benchmark all three honestly without falling into coordinated omission. Carry three things forward:

1. **The three bargains are different operational deals, not three vendors of the same thing.** Idle cost, scaling unit, and ownership differ fundamentally.
2. **The three numbers — price per 1k tokens, p50/p99, where the bytes sit — are the only defensible basis for the decision.** Everything else is taste.
3. **Utilization is the hinge.** Self-hosting and managed endpoints win on cost only when the GPU stays busy; the instant traffic dips, the pay-per-token bargain wins. Your recommendation memo lives or dies on the crossover-utilization number.

Now go request that GPU quota if you haven't, and run `confirm_path.py` until it prints "Path confirmed."

## 1.13 — A worked anti-pattern: the GPU you forgot

End on the failure mode this week exists to inoculate you against, because it is the most common and the most expensive. An engineer deploys a model to a Vertex Endpoint at `min_replica_count=1` on a Friday afternoon to demo it, the demo goes well, the engineer closes their laptop, and the endpoint serves zero requests all weekend while billing one L4 replica around the clock. Monday morning the billing alert (you armed budget alerts in Week 01 — this is where that pays off) shows a weekend of GPU node-hours for a model nobody used. The same story plays out with a forgotten spot GPU node pool on GKE, except spot is cheaper so the alert is quieter and the lesson lands later.

The structural cause is the one fact this whole lecture turns on: **on Bargains A and C, you pay for the GPU's existence, not its use.** Zero requests is not zero cost. The managed Gemini API (Bargain B) is the only option where "I forgot about it" costs nothing, because there is nothing warm to forget. That asymmetry is not a footnote; it is a real input to the build-vs-call decision for any team that is not yet disciplined about teardown. For a small team shipping its first model, "call" is sometimes the right answer *specifically because the operational discipline to safely run a warm GPU fleet is not there yet* — and that is a legitimate, defensible reason that has nothing to do with the triangle's three numbers and everything to do with knowing your own team.

The fix is mechanical and you build it into muscle memory this week: every GPU-backed resource is created with a teardown command written *before* you create it, and every work session ends with the teardown receipt — the two `list` commands from the README that must print nothing. The mini-project codifies this into a graded gate. Treat it the way Week 07 of the C# track treats a build warning: a non-empty GPU list at the end of a session is a defect you fix before you stop, not a thing you mean to get to. The engineers who never get a surprise GPU bill are not the ones with better memories; they are the ones who made teardown a reflex instead of a chore.

There is a defensive-engineering version of this you will build in Week 14's FinOps work and should keep in mind now: a *budget guardrail* that automatically un-deploys or alerts on a GPU resource that has served no traffic for N hours. The naive version is a scheduled job that runs the teardown receipt's `list` commands, checks the resource's request-count metric in Cloud Monitoring, and pages (or tears down, in non-production) anything warm-and-idle past a threshold. The point is not to build that this week — it is to internalize that "remember to tear down" is a weak control and "the system tears down what nobody is using" is a strong one. Strong controls are what separate a team that runs GPUs safely from a team that gets a quarterly surprise. For this week, the manual receipt is the control; from Week 14 on, you automate it.

One last framing, because it is the sentence to carry out of this lecture: the build-vs-call decision is not a one-time choice you make at design time and never revisit. It is a *standing* decision that the workload's own evolution can overturn. A workload that today is low-volume and spiky — correctly served by the Gemini API — can, if the product succeeds, become high-volume and steady, at which point the crossover math flips and the right answer becomes a self-hosted fleet. The artifact that lets you notice the flip is the recommendation memo's "what would change this" clause, plus the request-rate and duty-cycle metrics you are already collecting. The senior engineer does not just make the decision; they leave behind the trigger that tells the next engineer when to remake it. That is the difference between a decision and a guess that happened to be right for a while.

---

**References**

- Vertex AI — deployment overview: <https://cloud.google.com/vertex-ai/docs/general/deployment>
- Vertex AI — configure compute and autoscaling: <https://cloud.google.com/vertex-ai/docs/predictions/configure-compute>
- Vertex AI Model Garden — use open models: <https://cloud.google.com/vertex-ai/generative-ai/docs/open-models/use-open-models>
- Vertex AI — batch predictions: <https://cloud.google.com/vertex-ai/docs/predictions/get-batch-predictions>
- Vertex AI pricing: <https://cloud.google.com/vertex-ai/pricing>
- Document AI — overview: <https://cloud.google.com/document-ai/docs/overview>
- BigQuery ML — introduction: <https://cloud.google.com/bigquery/docs/bqml-introduction>
- GCP — GPU quota: <https://cloud.google.com/compute/resource-usage#gpu_quota>
