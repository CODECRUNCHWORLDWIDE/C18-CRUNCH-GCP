# Exercise 1 — Deploy a Model Garden model to a Vertex AI Endpoint with GPU autoscaling

**Goal:** Take an open-weights model from Vertex AI Model Garden (Gemma 3 9B), deploy it to a Vertex AI Endpoint backed by an L4 GPU with request-driven autoscaling, send it a real prediction, and tear it down — all reproducibly, from Terraform plus a thin Python deploy step. No console one-click deploys; everything is code you can review and re-run.

**Estimated time:** 90 minutes of work, plus 20–40 minutes of unattended deploy wait (model load to GPU is slow). Cost while up: roughly **\$0.70–1.00/hour** for one L4 replica. Tear down the same session.

---

## Why Terraform *and* Python

The Vertex Endpoint resource itself is cleanly expressed in Terraform (`google_vertex_ai_endpoint`). The *deploy-a-model-to-the-endpoint* step is not — the Terraform provider's coverage of `DeployedModel` for Model Garden open models lags the SDK, and the deploy is a long-running, stateful operation that the SDK handles more gracefully. So we use the right tool for each job: Terraform owns the endpoint (the stable, free resource) and the Python step owns the deploy (the expensive, long-running binding). This is a common, legitimate pattern — Terraform for the resource graph, a thin imperative step for the operation Terraform models poorly — and naming it explicitly is part of the lesson.

---

## Setup

```bash
mkdir -p week12-ex01 && cd week12-ex01
export PROJECT_ID="your-project-id"
export REGION="us-central1"
gcloud config set project "$PROJECT_ID"
```

Confirm your L4 quota is non-zero (Lecture 1 had you request it):

```bash
gcloud compute regions describe "$REGION" \
  --format="value(quotas[].metric, quotas[].limit)" | tr ',' '\n' | grep -i l4
```

If the limit is 0, stop and request a quota increase before continuing.

---

## Step 1 — The Terraform for the endpoint

Create `main.tf`. This creates only the endpoint (free) and the IAM the deploy step needs. The expensive deploy happens in Step 2.

```hcl
terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# The Endpoint: a stable HTTPS resource with nothing deployed yet. Free until a
# model is deployed onto it.
resource "google_vertex_ai_endpoint" "gemma" {
  name         = "gemma3-9b-endpoint"
  display_name = "gemma3-9b-endpoint"
  location     = var.region
  description  = "Week 12 — Gemma 3 9B open-weights serving endpoint"

  labels = {
    course = "c18-crunch-gcp"
    week    = "12"
    teardown = "required"
  }
}

output "endpoint_id" {
  value       = google_vertex_ai_endpoint.gemma.name
  description = "The numeric endpoint ID — pass this to the Python deploy step."
}

output "endpoint_resource_name" {
  value = "projects/${var.project_id}/locations/${var.region}/endpoints/${google_vertex_ai_endpoint.gemma.name}"
}
```

Apply it:

```bash
terraform init
terraform apply -var="project_id=$PROJECT_ID" -var="region=$REGION"
```

Capture the endpoint ID:

```bash
export ENDPOINT_ID="$(terraform output -raw endpoint_id)"
echo "Endpoint: $ENDPOINT_ID"
```

At this point you have spent nothing — an endpoint with no deployed model is free.

---

## Step 2 — The Python deploy step

This deploys the Model Garden open model onto the endpoint. It is the expensive step; it starts billing for one L4 replica when it completes. Create `deploy.py`:

```python
"""deploy.py — deploy a Model Garden open-weights model onto an existing endpoint.

Reads PROJECT_ID, REGION, ENDPOINT_ID from the environment. The endpoint is
created by Terraform; this step does the long-running, expensive deploy.
"""
import os
import sys

from google.cloud import aiplatform
from google.cloud.aiplatform import model_garden

PROJECT_ID = os.environ["PROJECT_ID"]
REGION = os.environ.get("REGION", "us-central1")
ENDPOINT_ID = os.environ["ENDPOINT_ID"]

# The Model Garden publisher model resource for Gemma 3 9B instruction-tuned.
# Confirm the exact ID against the live Model Garden — open-model IDs change.
PUBLISHER_MODEL = "publishers/google/models/gemma3"

# Serving hardware. The L4 (g2 family) is the cheapest GPU that fits a 9B model.
MACHINE_TYPE = "g2-standard-12"
ACCELERATOR_TYPE = "NVIDIA_L4"
ACCELERATOR_COUNT = 1

# Autoscaling: one warm replica (the latency floor + the idle cost), up to three
# under load. Scale on GPU duty cycle, EARLY (50%) so new capacity arrives before
# the existing replica saturates — this trims the cold-start p99 tail.
MIN_REPLICAS = 1
MAX_REPLICAS = 3
TARGET_GPU_DUTY_CYCLE = 50


def main() -> int:
    aiplatform.init(project=PROJECT_ID, location=REGION)

    endpoint = aiplatform.Endpoint(
        endpoint_name=f"projects/{PROJECT_ID}/locations/{REGION}/endpoints/{ENDPOINT_ID}"
    )
    print(f"Target endpoint: {endpoint.resource_name}")

    # Open the Model Garden entry and deploy it onto our endpoint.
    open_model = model_garden.OpenModel(PUBLISHER_MODEL)
    print(f"Deploying {PUBLISHER_MODEL} on {MACHINE_TYPE} + {ACCELERATOR_COUNT}x{ACCELERATOR_TYPE} ...")
    print("This takes 20-40 minutes (model load to GPU memory). Do not interrupt.")

    deployed = open_model.deploy(
        endpoint=endpoint,
        machine_type=MACHINE_TYPE,
        accelerator_type=ACCELERATOR_TYPE,
        accelerator_count=ACCELERATOR_COUNT,
        min_replica_count=MIN_REPLICAS,
        max_replica_count=MAX_REPLICAS,
        autoscaling_target_accelerator_duty_cycle=TARGET_GPU_DUTY_CYCLE,
        accept_eula=True,  # Gemma's license — you read the model card in Lecture 1.
    )

    print("Deployed. The endpoint now bills for at least one L4 replica.")
    print(f"Deployed models on endpoint: {[dm.id for dm in endpoint.list_models()]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run it:

```bash
python deploy.py
```

Go get coffee. Model load to GPU memory for a 9B model is genuinely 20–40 minutes the first time. **When it returns, you are paying for a GPU.** Note the wall-clock start time — you will tear down within a couple of hours.

---

## Step 3 — Send a real prediction

Create `predict.py` and send the model a prompt through the deployed endpoint:

```python
"""predict.py — send one chat-style prediction to the deployed endpoint."""
import os

from google.cloud import aiplatform

PROJECT_ID = os.environ["PROJECT_ID"]
REGION = os.environ.get("REGION", "us-central1")
ENDPOINT_ID = os.environ["ENDPOINT_ID"]

aiplatform.init(project=PROJECT_ID, location=REGION)
endpoint = aiplatform.Endpoint(
    endpoint_name=f"projects/{PROJECT_ID}/locations/{REGION}/endpoints/{ENDPOINT_ID}"
)

# The Gemma serving container exposes an OpenAI-style chat schema. The exact
# instance shape depends on the serving container the Model Garden deploy chose;
# this is the common chat-completions form.
instances = [
    {
        "messages": [
            {"role": "user", "content": "In one sentence, what is a Vertex AI Endpoint?"}
        ],
        "max_tokens": 64,
        "temperature": 0.2,
    }
]

response = endpoint.predict(instances=instances)
print("Raw prediction:")
for prediction in response.predictions:
    print(prediction)
```

Run it:

```bash
python predict.py
```

You should get back a generated sentence. The exact JSON shape depends on the serving container, but you will see your prompt answered. That confirms the full path: Terraform endpoint → SDK deploy → live prediction.

---

## Step 4 — Confirm the autoscaling config landed

Read the deployed model's autoscaling config back and confirm it matches what you asked for:

```bash
gcloud ai endpoints describe "$ENDPOINT_ID" --region="$REGION" \
  --format="yaml(deployedModels[].dedicatedResources)"
```

You should see `minReplicaCount: 1`, `maxReplicaCount: 3`, and an autoscaling metric targeting accelerator duty cycle at 50. If the min/max are not what you set, your deploy used defaults — re-read Step 2.

---

## Step 5 — Tear down (NOT optional)

Un-deploy the model (stops the replica billing), then destroy the endpoint:

```bash
# Un-deploy every model on the endpoint (this stops the GPU billing).
python - <<'PY'
import os
from google.cloud import aiplatform

aiplatform.init(project=os.environ["PROJECT_ID"], location=os.environ.get("REGION", "us-central1"))
endpoint = aiplatform.Endpoint(
    endpoint_name=f'projects/{os.environ["PROJECT_ID"]}/locations/{os.environ.get("REGION","us-central1")}/endpoints/{os.environ["ENDPOINT_ID"]}'
)
endpoint.undeploy_all()
print("All models undeployed. GPU billing stopped.")
PY

# Destroy the (now empty) endpoint with Terraform.
terraform destroy -var="project_id=$PROJECT_ID" -var="region=$REGION"
```

Confirm the teardown receipt:

```bash
gcloud ai endpoints list --region="$REGION" --format='value(name)'
# (no output)
```

If that prints nothing, you are no longer paying. If it prints an endpoint, run `terraform destroy` again and check for stuck deployed models.

---

## Expected output (smoke test — your text will differ)

After `python predict.py`:

```
Raw prediction:
{'choices': [{'message': {'role': 'assistant', 'content': 'A Vertex AI Endpoint is a managed, autoscaling HTTPS service that hosts a deployed model and serves online predictions.'}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 19, 'completion_tokens': 27, 'total_tokens': 46}}
```

After teardown, the endpoints list is empty.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `terraform apply` created the endpoint and `terraform output endpoint_id` returns a numeric ID.
- [ ] `python deploy.py` completed and `endpoint.list_models()` shows one deployed model.
- [ ] `python predict.py` returns a generated answer to the prompt.
- [ ] `gcloud ai endpoints describe` confirms `minReplicaCount: 1`, `maxReplicaCount: 3`, autoscaling on accelerator duty cycle at 50.
- [ ] `endpoint.undeploy_all()` ran and `terraform destroy` removed the endpoint.
- [ ] `gcloud ai endpoints list` prints nothing — the teardown receipt is clean.
- [ ] You recorded the deploy wall-clock time and the endpoint's node-hour rate (from the pricing page) for the challenge's cost comparison.

---

## Stretch

- Deploy Gemma 3 27B to the *same* endpoint as a second `DeployedModel` with `traffic_percentage=10` and watch the autoscaler treat the two independently. (Costs more — a 27B model needs a bigger machine. Tear down promptly.)
- Turn on request/response logging to BigQuery (`enable_request_response_logging`) and confirm a logged row lands in the configured table after a `predict` call.
- Re-run `deploy.py` with `min_replica_count=0` (scale-to-zero, if your model/container supports it) and measure the cold-start latency of the first request after a quiet period — this is the p99 tail Lecture 2 warned about, made visible.

---

## Hints

<details>
<summary>If deploy.py fails with a quota error</summary>

`NVIDIA_L4_GPUS` quota in your region is 0 or too low for `g2-standard-12` (which needs 1 L4). Request an increase in IAM & Admin → Quotas, or pick a region where you already have quota. The error message names the exact quota and region.

</details>

<details>
<summary>If the model ID is rejected</summary>

Model Garden open-model IDs change. Open Model Garden in the console, find the Gemma 3 9B card, and copy the exact `publishers/google/models/...` resource name from the deploy panel. Hard-coding a stale ID is the most common Step-2 failure.

</details>

<details>
<summary>If predict.py returns an unexpected JSON shape</summary>

The instance schema depends on the serving container the deploy chose. Print `response.predictions` raw and adapt — some containers expect `{"prompt": "...", "max_tokens": N}` (completions) rather than the chat `messages` shape. The Model Garden card documents the container's expected schema.

</details>

---

When this exercise's endpoint is **torn down**, move to [Exercise 2 — Gemini API cost and latency](exercise-02-gemini-cost-latency.py).
