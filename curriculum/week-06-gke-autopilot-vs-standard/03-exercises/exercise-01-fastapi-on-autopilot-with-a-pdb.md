# Exercise 1 — Deploy FastAPI to Autopilot with a PodDisruptionBudget

**Goal:** Containerize a small FastAPI service, push it to Artifact Registry, deploy it to a GKE Autopilot cluster as a 3-replica Deployment behind an internal Service, protect it with a PodDisruptionBudget, and *prove* the PDB does its job by trying to drain too many pods at once and watching the eviction API refuse.

**Estimated time:** 75 minutes.

By the end you can answer, with a demonstration rather than a recitation, the question "what does a PodDisruptionBudget actually do?" — it refuses an eviction that would breach `minAvailable`, which is the mechanism that keeps a node drain (and therefore an upgrade) from becoming an outage.

---

## Prerequisites

- A GCP project with billing, `gcloud` configured, region default `us-central1`.
- The `container.googleapis.com`, `compute.googleapis.com`, and `artifactregistry.googleapis.com` APIs enabled.
- An Artifact Registry Docker repo named `crunch` in `us-central1` (see the Week 6 README prerequisites).
- The Week 3 VPC `crunch-vpc` with subnet `crunch-us-central1` and secondary ranges `pods` and `services`. If you do not have these, the cluster create will fail — go back to Week 3.
- Docker running locally.

---

## Step 1 — The FastAPI service

Create `app/main.py`. This is the service we deploy this week and reuse in the challenge and mini-project. It exposes a health check, a root handler, and a `/work` endpoint that burns a little CPU so the HPA in later exercises has something to scale on.

```python
import os
import time

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="crunch-fastapi", version="1.0.0")

POD_NAME = os.getenv("POD_NAME", "unknown")


class WorkResult(BaseModel):
    pod: str
    iterations: int
    elapsed_ms: float


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "crunch-fastapi", "pod": POD_NAME}


@app.get("/work", response_model=WorkResult)
def work(iterations: int = 50_000) -> WorkResult:
    start = time.perf_counter()
    acc = 0
    for i in range(iterations):
        acc = (acc + i * i) % 2_147_483_647
    elapsed = (time.perf_counter() - start) * 1000.0
    return WorkResult(pod=POD_NAME, iterations=iterations, elapsed_ms=round(elapsed, 3))
```

Create `app/requirements.txt`:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
google-cloud-storage==2.19.0
```

(`google-cloud-storage` is unused in this exercise but used in Exercise 2; pin it now so the image is identical across both.)

---

## Step 2 — The Dockerfile

Create `Dockerfile`. A slim, non-root, multi-stage-free image is fine for this service.

```dockerfile
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

# Run as a non-root user — Autopilot rejects containers that try to run as
# UID 0 with a writable root filesystem in some policies; non-root is the
# always-safe default.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
USER 10001

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## Step 3 — Build and push to Artifact Registry

```bash
PROJECT_ID=$(gcloud config get-value project)
REGION=us-central1
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/crunch/fastapi:1.0.0"

# Configure Docker to auth against Artifact Registry.
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

# Build for the cluster's architecture (amd64) even if you are on Apple silicon.
docker build --platform=linux/amd64 -t "${IMAGE}" .
docker push "${IMAGE}"
```

Expected tail of the push:

```
1.0.0: digest: sha256:... size: 1786
```

---

## Step 4 — Create the Autopilot cluster

```bash
gcloud container clusters create-auto crunch-autopilot \
  --region=us-central1 \
  --network=crunch-vpc \
  --subnetwork=crunch-us-central1 \
  --cluster-secondary-range-name=pods \
  --services-secondary-range-name=services \
  --release-channel=regular

gcloud container clusters get-credentials crunch-autopilot --region=us-central1
```

Cluster creation takes 5–9 minutes. Workload Identity is on automatically; you did not have to ask for it.

---

## Step 5 — The Deployment, Service, and PodDisruptionBudget

Create `k8s/deployment.yaml`. Note the explicit resource requests (mandatory on Autopilot), the readiness/liveness probes (the PDB and the upgrade both depend on readiness being honest), and the `POD_NAME` downward-API injection so you can see which pod served you.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi
  labels:
    app: fastapi
spec:
  replicas: 3
  selector:
    matchLabels:
      app: fastapi
  template:
    metadata:
      labels:
        app: fastapi
    spec:
      containers:
        - name: fastapi
          # Replace PROJECT_ID with your project; or use `kubectl set image` after apply.
          image: us-central1-docker.pkg.dev/PROJECT_ID/crunch/fastapi:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 3
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: fastapi
spec:
  selector:
    app: fastapi
  ports:
    - port: 80
      targetPort: 8080
  type: ClusterIP
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fastapi-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: fastapi
```

Apply it (substituting your project into the image, or use `sed`):

```bash
sed "s/PROJECT_ID/${PROJECT_ID}/" k8s/deployment.yaml | kubectl apply -f -
kubectl rollout status deployment/fastapi --timeout=180s
```

Expected:

```
deployment "fastapi" successfully rolled out
```

On Autopilot the first rollout is slower than on Standard — Google has to provision nodes to fit your pods. Give it a couple of minutes.

---

## Step 6 — Verify the service answers

```bash
kubectl port-forward service/fastapi 8080:80 &
sleep 2
curl -s localhost:8080/ | python3 -m json.tool
```

Expected (the pod name will differ):

```json
{
    "service": "crunch-fastapi",
    "pod": "fastapi-7c9d8f6b5d-h4q2x"
}
```

Kill the port-forward when done: `kill %1`.

---

## Step 7 — Prove the PDB does its job

This is the payoff. We will try to drain a node aggressively and watch the eviction API refuse.

First, see the PDB's current state:

```bash
kubectl get pdb fastapi-pdb
# NAME          MIN AVAILABLE   ALLOWED DISRUPTIONS   AGE
# fastapi-pdb   2               1                     2m
```

`ALLOWED DISRUPTIONS: 1` means the PDB will permit exactly one pod to be voluntarily evicted right now (3 running, `minAvailable` 2, so 1 may go). Now try to evict *two* pods at once via the eviction API directly:

```bash
# Pick two pods.
PODS=$(kubectl get pods -l app=fastapi -o jsonpath='{.items[*].metadata.name}')
set -- $PODS
echo "evicting $1 and $2"

# Evict the first — should succeed.
kubectl delete pod "$1" --grace-period=30
# pod "fastapi-..." deleted

# Immediately try to evict the second, before its replacement is Ready.
# Use the eviction subresource so the PDB is enforced (a plain delete is NOT
# gated by the PDB — only the eviction API is).
cat <<EOF | kubectl create -f - 2>&1 || true
apiVersion: policy/v1
kind: Eviction
metadata:
  name: $2
  namespace: default
EOF
```

If the timing is right (the first pod's replacement has not yet become Ready), the eviction is refused:

```
Error from server (TooManyRequests): Cannot evict pod as it would violate the
pod's disruption budget.
```

That message — `Cannot evict pod as it would violate the pod's disruption budget` — is the entire point of a PDB. The eviction API checked `ALLOWED DISRUPTIONS`, saw it was 0 (because one pod was already gone and not yet replaced), and refused. A node drain during an upgrade uses this same eviction API, which is *why* the PDB paces an upgrade (Lecture 2, §2.3).

> **Critical distinction:** `kubectl delete pod` is **not** gated by the PDB — it deletes the pod outright. Only the **eviction API** (`kubectl drain`, the upgrade drainer, or a manual `Eviction` object) honors the PDB. This trips up everyone once. The PDB protects against *voluntary, eviction-API-mediated* disruptions, not against `delete`.

Watch the Deployment heal back to 3:

```bash
kubectl get pods -l app=fastapi -w
# all three return to Running/Ready within ~30s
```

---

## Acceptance criteria

- [ ] The FastAPI image is built `--platform=linux/amd64` and pushed to Artifact Registry.
- [ ] The Autopilot cluster is created with `create-auto` (no `--num-nodes`, no `--machine-type`).
- [ ] `kubectl rollout status deployment/fastapi` reports success with 3 ready replicas.
- [ ] Every container declares CPU **and** memory `requests` (Autopilot rejects pods that omit them).
- [ ] `curl localhost:8080/` returns JSON including a `pod` field.
- [ ] `kubectl get pdb fastapi-pdb` shows `MIN AVAILABLE 2` and `ALLOWED DISRUPTIONS 1` at steady state.
- [ ] You triggered and observed the `Cannot evict pod as it would violate the pod's disruption budget` message via the eviction API.
- [ ] You can explain, in one sentence, why `kubectl delete pod` was *not* blocked but the `Eviction` was.

---

## Teardown (do not skip)

```bash
gcloud container clusters delete crunch-autopilot --region=us-central1 --quiet
```

Confirm nothing lingers:

```bash
gcloud container clusters list
# (should not list crunch-autopilot)
gcloud compute forwarding-rules list
# (a ClusterIP Service creates no LB, so this should be empty for this exercise)
```

---

## Reflection questions

1. Why does Autopilot force you to declare resource requests when Standard does not? (Hint: the billing model from Lecture 1, §1.2.)
2. You set `minAvailable: 2` on a 3-replica Deployment. What value of `minAvailable` would make a node drain *impossible* to complete, and why?
3. The PDB blocks the eviction API but not `kubectl delete pod`. During a GKE node upgrade, which one does GKE use, and what does that tell you about whether your PDB will protect you during the upgrade?
4. If you scaled the Deployment to 10 replicas, would `minAvailable: 2` still be a sensible PDB? What would `maxUnavailable: 10%` express instead, and when is the percentage form better?
