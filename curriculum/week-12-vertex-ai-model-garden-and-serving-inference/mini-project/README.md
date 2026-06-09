# Mini-Project — The Serving Tier: a Vertex client with circuit-breaker Gemini fallback on the Week 06 GKE cluster

> Build the model-serving tier of the capstone. A Python service — deployed as a workload on your **Week 06 GKE cluster** — reads enriched events from your **Week 10 BigQuery dataset**, classifies/enriches each one through a **Vertex AI Endpoint** (primary, Gemma 3 9B from Model Garden) with a **circuit-breaker fallback to the Gemini API** (Vertex-regional, sovereign) when the endpoint is unhealthy, and writes the results back to BigQuery. It exposes a health endpoint, logs every failover, and ships with a **graded teardown gate** so you do not leave a GPU running over the weekend. This is Phase 3's capstone deliverable: the tier that turns "data worth serving" into "a model in front of it that survives its primary going down."

This compounds the Phase 3 stack. It does **not** start fresh. It runs on the GKE cluster you built in Week 06, reads the BigQuery tables you landed in Week 10, and uses the serving primitives you exercised this week. Week 13 will instrument this exact service with OpenTelemetry and put an SLO on it; Week 14 will wrap it in a VPC-SC perimeter and require Binary Authorization to deploy it. Build it as if those weeks are coming, because they are.

**Estimated time:** ~13.5 hours (Friday, Saturday, and Sunday polish in the suggested schedule).

---

## Where this sits in the capstone

| Week | What you built | What this mini-project uses from it |
|---|---|---|
| **06** | GKE cluster (Standard, node pools, Workload Identity) | The cluster the serving service is deployed onto, and the GPU node pool option |
| **08** | External HTTPS LB + Cloud Armor | (Optional) the ingress in front of the service |
| **10** | BigQuery dataset of enriched events, partitioned + clustered | The **source** rows to classify and the **sink** for the results |
| **12** | Vertex Endpoint + Gemini + circuit breaker (this week) | The serving tier you assemble here |

If any of those upstream pieces is torn down, bring it back first: `terraform apply` in the Week 06 directory restores the cluster; the Week 10 loader re-populates BigQuery. Do this Friday morning, not Saturday night.

---

## What you will build

A single deployable service, `serving-tier`, with these components:

1. **A BigQuery reader** that pulls a batch of un-enriched rows from the Week 10 events table (`WHERE enrichment IS NULL LIMIT N`), using a parameterized query and the partition/cluster keys so the scan is cheap.
2. **A `ResilientModelClient`** (the circuit-breaker client from the challenge, productionized) that classifies each event through the Vertex Endpoint primary and fails over to Gemini when the breaker is open. Every failover is a structured log line.
3. **A BigQuery writer** that writes the enrichment result back — the predicted label, the serving path that produced it (`primary`/`fallback`), the token counts, and a timestamp — using a `MERGE` so re-runs are idempotent.
4. **An HTTP server** (FastAPI or the stdlib) exposing `GET /healthz` (liveness), `GET /readyz` (the `ResilientModelClient.health()` check), and `POST /enrich` (process one batch on demand). The health endpoints are what GKE's probes hit.
5. **A Kubernetes manifest** (Deployment + Service + ServiceAccount with Workload Identity) that runs the service on the Week 06 cluster, authenticating to Vertex AI and BigQuery via Workload Identity — **no service-account key files** (the Week 02 lesson).
6. **A teardown gate**: a script that un-deploys the endpoint, deletes any GPU node pool, deletes the workload, and verifies the receipt is clean. You submit the receipt.

You ship **one repository** with this layout:

```
serving-tier/
  terraform/
    endpoint.tf            # the Vertex Endpoint (from Exercise 1)
    iam.tf                 # Workload Identity binding for the service SA
    outputs.tf
  src/
    serving_tier/
      __init__.py
      config.py            # env-driven config (project, region, endpoint id, dataset)
      bigquery_io.py       # reader + idempotent MERGE writer
      resilient_client.py  # circuit breaker, Vertex primary, Gemini fallback
      cost_model.py        # the Lecture 2 cost harness (vendored)
      server.py            # FastAPI app: /healthz /readyz /enrich
  k8s/
    deployment.yaml        # Deployment + Service + ServiceAccount (Workload Identity)
  scripts/
    deploy_model.py        # the Exercise 1 SDK deploy step
    teardown.sh            # the graded teardown gate
    seed_events.sql        # (optional) top up the Week 10 table with test rows
  tests/
    test_resilient_client.py   # breaker state machine unit tests (no GCP needed)
    test_bigquery_io.py        # MERGE idempotency test (against a temp table)
  Dockerfile
  requirements.txt
  README.md
  RECOMMENDATION.md        # the production-path memo (from the challenge, refined)
```

---

## Rules

- **You may** read Google Cloud docs, the `google-cloud-aiplatform`, `google-genai`, and `google-cloud-bigquery` SDK docs, the vLLM docs, your Week 12 exercises and challenge, and the Lecture 2 harnesses.
- **You may NOT** use a service-account key file. Authentication to Vertex AI and BigQuery is via **Workload Identity** (Week 02). A key file in the repo is an automatic fail.
- **You may NOT** hard-code the project ID, region, endpoint ID, or dataset name in source. They come from environment variables / a `ConfigMap`. (`config.py` reads them.)
- The Vertex Endpoint comes from **Terraform plus the `deploy_model.py` SDK step** — no console one-click deploys.
- The circuit breaker must **not trip on latency** — only on hard failures (non-2xx, timeout, connection error). The fallback uses the **Vertex-regional Gemini path** (sovereign), not the public AI Studio key path.
- The BigQuery writer must be **idempotent** — re-running on the same input must not duplicate or corrupt rows. Use `MERGE`.
- `<TreatWarningsAsErrors>`-equivalent discipline: the Python is type-hinted, passes `ruff check` clean, and the unit tests pass without any GCP access (mock the clients).
- **Teardown is graded.** The submitted teardown receipt must be clean.

---

## Step-by-step

### Phase A — Restore the upstream stack (Friday morning, ~30 min)

1. `terraform apply` in your Week 06 directory if the cluster is down. Confirm `kubectl get nodes` lists nodes.
2. Confirm the Week 10 BigQuery dataset exists and has rows: `bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM your_dataset.events WHERE enrichment IS NULL'`. If it is empty, run `scripts/seed_events.sql` (you write this — a handful of `INSERT`s of realistic event rows) or re-run the Week 10 loader.

### Phase B — The endpoint and the IAM (Friday, ~1.5h)

3. `terraform apply` the `endpoint.tf` (from Exercise 1) and the `iam.tf` (a Workload Identity binding so the service's Kubernetes ServiceAccount can impersonate a Google SA with `roles/aiplatform.user` and `roles/bigquery.dataEditor`).
4. Run `scripts/deploy_model.py` to deploy Gemma 3 9B onto the endpoint. **The GPU billing starts here — note the time.**

### Phase C — The service (Friday + Saturday, ~6h)

5. Implement `resilient_client.py` (productionize the challenge's client — the same state machine, but reading config from env and using the SDK clients).
6. Implement `bigquery_io.py`: a `read_unenriched(limit)` that returns rows and a `write_enrichments(results)` that `MERGE`s them back idempotently.
7. Implement `server.py`: FastAPI with `/healthz` (always 200 if the process is up), `/readyz` (200 iff `client.health()` is true), and `POST /enrich` (read a batch, classify each through the resilient client, write back, return a summary).
8. Write the unit tests: the breaker state machine (closed → open → half-open → closed, threshold, cooldown) with **no GCP calls** (inject fakes), and the MERGE idempotency test against a temporary table.

### Phase D — Deploy to GKE (Saturday, ~2h)

9. Build and push the container to Artifact Registry.
10. `kubectl apply -f k8s/deployment.yaml`. The ServiceAccount uses Workload Identity; confirm the pod authenticates to Vertex and BigQuery with **no key file mounted**.
11. Confirm the readiness probe goes green and `POST /enrich` against the in-cluster service processes a batch and writes results to BigQuery. Query BigQuery to verify the `serving_path` column shows `primary`.

### Phase E — Prove the fallback (Saturday, ~1h)

12. Force the endpoint unhealthy (point the client at a bad endpoint ID via a `ConfigMap` change, or add a deny firewall rule). Hit `POST /enrich` again. Confirm: the breaker trips, the logs show the transition, the batch still completes via Gemini, and the new BigQuery rows show `serving_path = fallback`. Revert.

### Phase F — Benchmark, recommend, tear down (Saturday + Sunday, ~2.5h)

13. Run the three-way benchmark (from the challenge) and refine `RECOMMENDATION.md` with the service's real measured numbers.
14. Run `scripts/teardown.sh`. Confirm the receipt is clean. Screenshot it.

---

## The teardown gate (graded)

`scripts/teardown.sh` must do all of this and end by printing the receipt:

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${REGION:?set REGION}"
: "${CLUSTER:?set CLUSTER}"
: "${ENDPOINT_ID:?set ENDPOINT_ID}"

echo "1/4 Deleting the GKE workload..."
kubectl delete -f k8s/deployment.yaml --ignore-not-found

echo "2/4 Undeploying the model (stops GPU billing on the endpoint)..."
python - <<PY
import os
from google.cloud import aiplatform
aiplatform.init(project=os.environ["PROJECT_ID"], location=os.environ["REGION"])
ep = aiplatform.Endpoint(
    endpoint_name=f'projects/{os.environ["PROJECT_ID"]}/locations/{os.environ["REGION"]}/endpoints/{os.environ["ENDPOINT_ID"]}'
)
ep.undeploy_all()
print("  undeployed all models")
PY

echo "3/4 Destroying the endpoint and IAM via Terraform..."
terraform -chdir=terraform destroy -auto-approve \
  -var="project_id=${PROJECT_ID}" -var="region=${REGION}"

echo "4/4 Deleting any GPU node pool added to the cluster..."
for pool in $(gcloud container node-pools list --cluster="$CLUSTER" --region="$REGION" \
    --filter='config.accelerators:*' --format='value(name)'); do
  gcloud container node-pools delete "$pool" --cluster="$CLUSTER" --region="$REGION" --quiet
done

echo "===== TEARDOWN RECEIPT ====="
echo "Endpoints in region (must be empty):"
gcloud ai endpoints list --region="$REGION" --format='value(name)'
echo "GPU node pools (must be empty):"
gcloud container node-pools list --cluster="$CLUSTER" --region="$REGION" \
  --filter='config.accelerators:*' --format='value(name)'
echo "============================"
echo "If both lists above are empty, you are no longer paying for a GPU."
```

A submission whose receipt shows an endpoint or a GPU node pool still up does not pass — the same way a build warning does not pass in C9. The teardown gate is the lesson, not the bureaucracy.

---

## Acceptance criteria & rubric

### Correctness (35%)

- [ ] `POST /enrich` reads un-enriched rows from the Week 10 BigQuery table, classifies each through the `ResilientModelClient`, and writes results back idempotently via `MERGE`.
- [ ] The written rows carry the predicted label, the `serving_path` (`primary`/`fallback`), token counts, and a timestamp.
- [ ] Re-running `POST /enrich` on already-enriched rows does not duplicate or corrupt data (idempotency test passes).
- [ ] `GET /readyz` returns 200 iff the client can serve (primary healthy or fallback reachable); `GET /healthz` returns 200 whenever the process is up.

### Resilience (25%)

- [ ] The circuit breaker implements closed/open/half-open correctly; a forced primary failure trips it and a half-open probe recovers it.
- [ ] The breaker does **not** trip on latency alone — only on hard failures.
- [ ] The forced-failover demo shows the batch completing via Gemini with `serving_path = fallback` in BigQuery and the transition in the structured logs.
- [ ] The fallback uses the Vertex-regional Gemini path (sovereign), not the public AI Studio path.

### Platform integration (20%)

- [ ] The service runs on the **Week 06 GKE cluster** as a Deployment with a readiness probe wired to `/readyz`.
- [ ] Authentication to Vertex AI and BigQuery is via **Workload Identity** — no key file anywhere in the repo or mounted in the pod.
- [ ] The Vertex Endpoint is created by Terraform + the SDK deploy step, not a console one-click.
- [ ] Project/region/endpoint/dataset are env-driven (ConfigMap), not hard-coded.

### Judgment & teardown (20%)

- [ ] `RECOMMENDATION.md` recommends a production path with the crossover duty cycle, the sovereignty sieve, and triangle-corner justification (refined from the challenge with the service's real numbers).
- [ ] `scripts/teardown.sh` runs clean and the submitted **teardown receipt is empty** for both endpoints and GPU node pools.
- [ ] The unit tests pass with **no GCP access** (clients mocked), and `ruff check` is clean.

---

## What "done" looks like

- A `kubectl get pods` showing your `serving-tier` pod Running and Ready on the Week 06 cluster.
- A BigQuery query showing enriched rows with `serving_path` populated — some `primary`, and after your forced-failover demo, some `fallback`.
- A structured log excerpt showing a `circuit_breaker_transition` event.
- A `RECOMMENDATION.md` a staff engineer would sign.
- A teardown receipt with two empty lists.

---

## Stretch (no extra grade, real signal)

- Add a **batch path**: a `BatchPredictionJob` (or a vLLM-on-GKE batch run) that enriches the whole backlog overnight, and compare its per-row cost to the online `/enrich` path. This is the Lecture 1 "could this be batch?" question, answered with numbers.
- Put the service behind the **Week 08 external HTTPS LB + Cloud Armor** so `/enrich` is reachable (and rate-limited) from outside the cluster.
- Wire **request/response logging to BigQuery** on the Vertex Endpoint and write a Week-10-style query over the logged predictions to compute the real production token distribution, then feed that back into `cost_model` for a more accurate crossover.
- Add a **Document AI** processor as a second "call, don't build" dependency: if an incoming event carries an attached document, route it through a form parser before enrichment, and add it to the triangle in `RECOMMENDATION.md`.

---

## Up next

Week 13 instruments this exact service with OpenTelemetry — traces across the BigQuery read, the model call, and the BigQuery write; metrics on the failover rate; logs routed to a BigQuery sink — and defines the SLO you will be paged on: "99.5% of `/enrich` batches succeed within budget, counting a Gemini fallback as a success." The circuit breaker you built here is what makes that SLO achievable. Build the serving tier so it is ready to be observed.
