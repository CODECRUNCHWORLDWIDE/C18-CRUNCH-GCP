# Exercise 1 — Deploy a Cloud Run v2 service and tune concurrency and CPU allocation for a target latency

> **Estimated time:** 90 minutes. **Goal:** Deploy a stateless Cloud Run v2 service with a deliberately CPU-bound endpoint, watch its p99 collapse at the default concurrency of 80, then tune `concurrency` and CPU allocation until p99 is under a target — and read the cost consequence of each change. By the end you can defend, with numbers, the claim "for a CPU-bound handler, lowering concurrency is what fixes p99, not adding instances."

This is the hands-on companion to Lecture 1. The cost curve only makes sense once you have felt concurrency bite. The lesson: **concurrency is capacity planning, not a free dial.**

---

## What you'll deploy

A tiny FastAPI service with two endpoints:

- `GET /healthz` — instant, for probes.
- `GET /work?ms=NN` — burns approximately `NN` milliseconds of **real CPU** (a busy loop, not a `sleep`). This simulates a CPU-bound handler: an image transform, a JSON aggregation, a hash. We use `ms=50` as the target work.

Because the work is CPU-bound, stacking 80 of these onto one vCPU is a disaster, and the exercise makes you see exactly that.

---

## Step 0 — Scaffold

```bash
mkdir -p crunch-tune/app && cd crunch-tune
PROJECT_ID=$(gcloud config get-value project)
REGION=us-central1
REPO=crunch
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/tune:1.0.0"

# Artifact Registry repo (idempotent; ignore "already exists")
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker --location="${REGION}" \
  --description="Crunch GCP week 7" 2>/dev/null || true
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
```

Create `app/main.py`:

```python
import os
import time

from fastapi import FastAPI

app = FastAPI(title="crunch-tune", version="1.0.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/work")
def work(ms: int = 50) -> dict[str, int]:
    """Burn approximately `ms` milliseconds of REAL CPU.

    A busy loop, not a sleep: this simulates a CPU-bound handler. A sleep
    would simulate an I/O-bound handler (waiting on a database), which is
    the OPPOSITE tuning lesson. The point of this exercise is the CPU-bound
    case, where concurrency 80 is catastrophic.
    """
    deadline = time.perf_counter() + (ms / 1000.0)
    iterations = 0
    while time.perf_counter() < deadline:
        # Trivial arithmetic in a tight loop keeps the CPU pinned.
        iterations += 1
    return {"requested_ms": ms, "iterations": iterations}
```

Create `app/requirements.txt`:

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
```

Create `Dockerfile` (multi-stage, slim — cold-start hygiene matters later):

```dockerfile
FROM python:3.12-slim AS build
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir --target=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=build /install /usr/local/lib/python3.12/site-packages
COPY app/ /app/
ENV PORT=8080
# Single worker on purpose: we want Cloud Run's concurrency to be the dial,
# not uvicorn's internal worker count. One process, Cloud Run controls fan-out.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

Build and push (`--platform=linux/amd64` matters on Apple Silicon):

```bash
docker build --platform=linux/amd64 -t "${IMAGE}" .
docker push "${IMAGE}"
```

---

## Step 1 — Deploy at the defaults (concurrency 80, 1 vCPU)

We deploy with Terraform so the knobs are explicit and version-controlled. Create `service.tf`:

```hcl
variable "project_id" { type = string }
variable "region" { type = string }
variable "image" { type = string }
variable "concurrency" {
  type    = number
  default = 80 # Cloud Run's default. We will lower this.
}
variable "cpu" {
  type    = string
  default = "1"
}
variable "cpu_idle" {
  type    = number
  default = true # request-time CPU (cheapest). false = always-allocated.
  # NOTE: cpu_idle is a bool in the provider; declared loosely here for clarity,
  # set it as a real bool below.
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_cloud_run_v2_service" "tune" {
  name                = "crunch-tune"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    # The two knobs this exercise tunes:
    max_instance_request_concurrency = var.concurrency

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    containers {
      image = var.image
      ports { container_port = 8080 }
      resources {
        limits = {
          cpu    = var.cpu
          memory = "512Mi"
        }
        cpu_idle          = true  # request-time CPU allocation
        startup_cpu_boost = true
      }
      startup_probe {
        http_get { path = "/healthz" }
        initial_delay_seconds = 2
        period_seconds        = 3
        failure_threshold     = 5
      }
    }
  }
}

# Allow unauthenticated access for the duration of this exercise so `hey` can
# hit it without minting tokens. (In production this is internal-only + IAM.)
resource "google_cloud_run_v2_service_iam_member" "noauth" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.tune.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "url" {
  value = google_cloud_run_v2_service.tune.uri
}
```

Apply at the defaults:

```bash
terraform init
terraform apply \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="image=${IMAGE}" \
  -var="concurrency=80"
URL=$(terraform output -raw url)
echo "${URL}"

# Warm it and sanity check:
curl -s "${URL}/work?ms=50" | python3 -m json.tool
```

---

## Step 2 — Load it and watch p99 collapse

Drive load that forces ~50 concurrent requests of 50 ms CPU work each. With concurrency 80 and 1 vCPU, Cloud Run stacks them all onto a single under-powered instance before it scales out, and the CPU-bound work serializes.

```bash
# 50 concurrent connections, 2000 requests, each doing 50ms of CPU work.
hey -c 50 -n 2000 "${URL}/work?ms=50"
```

Read the `hey` summary. With concurrency 80 / 1 vCPU you should see something like:

```text
Summary:
  Requests/sec:  ~180
Latency distribution:
  50% in 0.21 secs
  95% in 0.62 secs
  99% in 0.98 secs        <-- p99 ~1s for 50ms of work. Catastrophic.
```

**Why?** Fifty 50 ms-of-CPU requests landed on one instance (because concurrency 80 said "send up to 80 here") with one vCPU. The CPU can only do one busy-loop at a time, so the requests time-share a single core. Each request's *wall-clock* time balloons because it spends most of it waiting for the CPU. Adding instances does not help until Cloud Run decides to scale out — and the autoscaler scales on instance utilization/concurrency, which it reads as "fine, the instance is handling its 50 < 80 allowed requests."

This is the trap: **for a CPU-bound handler, high concurrency tells Cloud Run to pile work onto a saturated instance instead of scaling out.**

---

## Step 3 — Tune concurrency down

Lower concurrency so each instance handles fewer simultaneous requests and Cloud Run scales out horizontally. For 50 ms of CPU on 1 vCPU, a sane concurrency is small — start at 8.

```bash
terraform apply \
  -var="project_id=${PROJECT_ID}" -var="region=${REGION}" -var="image=${IMAGE}" \
  -var="concurrency=8"

# re-warm, then load again
curl -s "${URL}/work?ms=50" > /dev/null
hey -c 50 -n 2000 "${URL}/work?ms=50"
```

Now Cloud Run, seeing each instance hit 8 in-flight, scales out to ~6–7 instances to cover 50 concurrent requests. Each request gets close to a full vCPU. Expect:

```text
Summary:
  Requests/sec:  ~620
Latency distribution:
  50% in 0.052 secs
  95% in 0.071 secs
  99% in 0.089 secs        <-- p99 ~89ms for 50ms of work. Healthy.
```

p99 dropped from ~1s to ~90 ms. You changed one number. **That is the lesson:** for CPU-bound work, concurrency is the throttle that decides whether Cloud Run stacks or scales.

---

## Step 4 — The cost consequence

Here is the catch Lecture 1 warned about. At concurrency 80 you (in principle) amortized CPU across many requests — cheap per request, terrible latency. At concurrency 8 you scaled out to ~7 instances — great latency, but you are now paying for ~7 instances' worth of active vCPU-seconds instead of ~1. **You bought latency with money.**

Quantify it. While the load test runs, watch instance count:

```bash
# In another terminal during the load test:
gcloud run services describe crunch-tune --region="${REGION}" \
  --format='value(status.traffic)' >/dev/null   # warms the describe
gcloud monitoring time-series list \
  --filter='metric.type="run.googleapis.com/container/instance_count"' \
  --format='value(points.value.int64Value)' 2>/dev/null | head -5 || true
# Simpler: open Cloud Run > crunch-tune > METRICS > "Container instance count"
# and watch it climb to ~7 at concurrency 8 vs ~1-2 at concurrency 80.
```

The trade in numbers (using Lecture 1 prices, 1 vCPU active = \$0.000024/vCPU-s):

- **Concurrency 80:** ~1–2 active instances, ~180 req/s, p99 ~1s. Cheap, slow.
- **Concurrency 8:** ~7 active instances, ~620 req/s, p99 ~90ms. ~7× the active-instance-seconds per unit time, ~3.5× the throughput → roughly 2× the cost *per request*, but it actually meets a latency SLO.

The senior framing for a review: *"At concurrency 80 the service is cheap but cannot meet a 400 ms p99 for CPU-bound work. Dropping to concurrency 8 meets p99 at roughly 2× the per-request cost. If this latency SLO is real, concurrency 8 is the floor; if it isn't, leave it at 80 and save the money."*

---

## Step 5 — The I/O-bound counterpoint (read, don't redeploy)

If `/work` had been `await asyncio.sleep(ms/1000)` instead of a busy loop — i.e., **I/O-bound**, simulating waiting on Postgres — the story inverts. A sleeping request uses ~0 CPU, so 80 of them coexist happily on one instance: concurrency 80 is *correct* for I/O-bound handlers, gives you the best cost (one instance amortizes 80 waiting requests), and lowering concurrency would *waste* money by scaling out unnecessarily. **The right concurrency is a function of how CPU-bound the handler is.** The mini-project's ingest handler is I/O-bound (it writes to Postgres and returns), so it keeps concurrency at or near the default — and you should be able to explain why.

---

## Acceptance criteria

- [ ] The service is deployed via Terraform with `max_instance_request_concurrency` set explicitly.
- [ ] `hey -c 50 -n 2000 "${URL}/work?ms=50"` at concurrency 80 shows p99 ≳ 500 ms (the collapse).
- [ ] The same load at concurrency 8 shows p99 ≲ 150 ms (the fix).
- [ ] You observed instance count climb from ~1–2 (conc 80) to ~6–7 (conc 8) in Cloud Run metrics.
- [ ] You can state the cost trade in one sentence: lower concurrency bought latency by scaling out, at higher per-request cost.
- [ ] You can explain why the *opposite* tuning (keep concurrency high) is correct for an I/O-bound handler.

## Teardown (do not skip)

```bash
terraform destroy \
  -var="project_id=${PROJECT_ID}" -var="region=${REGION}" -var="image=${IMAGE}"
# Optional: remove the image
gcloud artifacts docker images delete "${IMAGE}" --quiet 2>/dev/null || true
```

Confirm in the console: `Cloud Run services: 0`.

---

## Reflection (answer in `results-ex01.md`)

1. At concurrency 80, adding `max_instance_count=50` would *not* have fixed p99 by itself. Why? (Hint: what does the autoscaler scale on, and does a 50/80-full instance trigger a scale-out?)
2. You set `cpu_idle = true` (request-time CPU). For this load test, would `cpu_idle = false` (always-allocated) change the latency? Change the cost? Why or why not?
3. The mini-project's ingest handler writes one row to Postgres and returns. Is it CPU-bound or I/O-bound? What concurrency would you set, and what does that do to its Cloud Run cost relative to this exercise's service?

---

**References**

- Cloud Run — "About instance autoscaling": <https://cloud.google.com/run/docs/about-instance-autoscaling>
- Cloud Run — "Set concurrency": <https://cloud.google.com/run/docs/configuring/concurrency>
- Cloud Run — CPU allocation: <https://cloud.google.com/run/docs/configuring/cpu-allocation>
- `google_cloud_run_v2_service` provider docs: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_service>
- `hey` load generator: <https://github.com/rakyll/hey>
