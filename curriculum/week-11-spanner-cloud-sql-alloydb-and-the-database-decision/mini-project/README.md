# Mini-Project — The "Current-State" Service: Cloud SQL Now, Spanner-Ready

> Build a production-shaped "current-state" service: a gRPC API backed by Cloud SQL for PostgreSQL (regional HA + a cross-region read replica + Private Service Connect, no public IP), deployed onto the Week 06 GKE cluster via Workload Identity, with a **documented and tested** Datastream→Spanner migration path that you can execute on demand. The service answers "what is the current state of entity X?" — the read-heavy, low-latency, must-be-correct query at the center of most systems. By the end you have the exact artifact the capstone needs: this becomes **the Spanner-backed gRPC service** in the Realtime Event Pipeline capstone. Spanner is the paid-but-cheap (~\$5) opt-in for the week, gated behind a teardown step you cannot skip.

This is the week's capstone-feeder. Every prior phase contributed a piece: Week 03 gave you the VPC and PSC, Week 04 gave you the Terraform module discipline, Week 06 gave you the GKE cluster and Workload Identity, Week 09 gave you Dataflow. This week you assemble them into a stateful service with a defensible database decision and a *tested escape hatch* to Spanner. The escape hatch is the point: a senior engineer never builds a service on Cloud SQL without knowing exactly what the move to Spanner would cost, and never claims "we could migrate" without having actually run the migration once in a lab.

**Estimated time:** ~12.5 hours (split across Friday, Saturday, Sunday in the suggested schedule).

---

## What you will build

A service called `current-state` with these parts:

1. **A gRPC API** (`GetState`, `PutState`, `ListStateByOwner`) defined in a `.proto`, implemented in **Python** (grpcio) — or Go if you prefer; the capstone uses gRPC and either language is acceptable. The service is stateless; all state lives in the database.

2. **A Cloud SQL for PostgreSQL backend** in the production shape from Exercise 1: regional HA (synchronous standby), a cross-region read replica that `ListStateByOwner` *may* read from, and Private Service Connect so the database has no public IP. Reads of one's own writes go to the primary; bulk list reads go to the replica.

3. **A GKE deployment** onto the Week 06 cluster, using Workload Identity so the pod authenticates to GCP (and reaches Cloud SQL over the PSC endpoint) with **no service-account key file**.

4. **A documented, tested Datastream→Spanner migration path** — the Challenge 1 pipeline, packaged as a runbook in `docs/migration.md` plus a `migrate/` directory of scripts and Terraform, with a shadow-test you have actually run once. Spanner itself is **opt-in**: `terraform apply -var="enable_spanner=true"` brings it up for ~\$5, and a teardown gate (`make teardown-spanner`) brings it back down.

5. **The teardown gate.** A `Makefile` with `teardown` and `teardown-spanner` targets, and a `make verify-teardown` that fails loudly if a Spanner instance still exists or the budget alert is disarmed.

You ship **one repository** with this layout:

```
current-state/
├── proto/current_state.proto          # the gRPC contract
├── src/                               # the Python (or Go) service
│   ├── server.py
│   ├── repository_cloudsql.py         # the Cloud SQL implementation
│   ├── repository_spanner.py          # the Spanner implementation (used post-migration)
│   └── health.py
├── infra/
│   ├── cloudsql.tf                    # HA + replica + PSC (from Exercise 1)
│   ├── spanner.tf                     # gated on var.enable_spanner
│   ├── gke.tf                         # the deployment + Workload Identity binding
│   └── variables.tf
├── k8s/
│   ├── deployment.yaml                # the gRPC service
│   ├── service.yaml
│   └── serviceaccount.yaml            # KSA annotated for Workload Identity
├── migrate/
│   ├── datastream.tf                  # Datastream stream + connection profiles
│   ├── launch_dataflow.sh             # the Datastream-to-Spanner template launch
│   └── shadow_test.py                 # the parallel read validation (from Challenge 1)
├── docs/
│   ├── decision.md                    # WHY Cloud SQL and not AlloyDB/Spanner (the rubric)
│   ├── migration.md                   # the tested runbook to move to Spanner
│   └── exit-plan.md                   # the CockroachDB/Yugabyte exit plan (Lecture 2)
├── Makefile
└── README.md
```

---

## The gRPC contract

Start from the contract; the database is an implementation detail behind it. A minimal `current_state.proto`:

```proto
syntax = "proto3";
package currentstate.v1;

message State {
  string id = 1;          // UUID - chosen to be Spanner-hotspot-safe from day one
  string owner = 2;       // the partition / list key
  bytes payload = 3;      // opaque current-state blob
  int64 version = 4;      // optimistic-concurrency version
  string updated_at = 5;  // RFC3339 UTC
}

message GetStateRequest  { string id = 1; }
message GetStateResponse { State state = 1; }

message PutStateRequest  { State state = 1; int64 expected_version = 2; }
message PutStateResponse { State state = 1; }   // returns the stored state with new version

message ListStateByOwnerRequest  { string owner = 1; int32 limit = 2; }
message ListStateByOwnerResponse { repeated State states = 1; }

service CurrentState {
  rpc GetState(GetStateRequest) returns (GetStateResponse);
  rpc PutState(PutStateRequest) returns (PutStateResponse);
  rpc ListStateByOwner(ListStateByOwnerRequest) returns (ListStateByOwnerResponse);
}
```

Two design decisions encode the week's lessons:

- **`id` is a UUID string, not a sequence.** You are designing the schema to be Spanner-migration-safe from the first commit — a monotonic key would hotspot the moment you migrated. Postgres is happy with a UUID; Spanner requires it.
- **`PutState` carries `expected_version`** for optimistic concurrency. This is the read-modify-write pattern that behaves identically on Cloud SQL (a `WHERE version = $expected` update) and on Spanner (a read-write transaction), so the contract survives the migration.

---

## The Cloud SQL schema

```sql
-- Cloud SQL Postgres. Maps cleanly to the Spanner schema in migrate/.
CREATE TABLE state (
    id          UUID PRIMARY KEY,
    owner       TEXT NOT NULL,
    payload     BYTEA NOT NULL,
    version     BIGINT NOT NULL DEFAULT 1,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_state_owner ON state (owner);
```

The corresponding Spanner schema (in `migrate/`, applied only post-migration):

```sql
CREATE TABLE State (
    Id        STRING(36) NOT NULL,
    Owner     STRING(256) NOT NULL,
    Payload   BYTES(MAX) NOT NULL,
    Version   INT64 NOT NULL,
    UpdatedAt TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (Id);

CREATE INDEX StateByOwner ON State (Owner);
```

Note how little changes: `UUID`→`STRING(36)`, `BYTEA`→`BYTES(MAX)`, `TIMESTAMPTZ`→`TIMESTAMP`. Because you chose a UUID key and avoided `SERIAL`, there is no hotspot to redesign around. *This is what "Spanner-ready" means in practice.*

---

## Rules

- **You may** read the lectures, exercises, Challenge 1, the GCP docs, and the Week 03/04/06/09 deliverables you already built.
- **You may NOT** give the Cloud SQL instance a public IP. `ipv4_enabled = false` and PSC, or the mini-project fails the security check. This is non-negotiable; it is the production rule from Lecture 1.
- **You may NOT** put a service-account key file in the repo or the pod. The pod authenticates via Workload Identity (Week 06). A keyfile in the deployment is an automatic fail.
- **Spanner is opt-in and gated.** The default `terraform apply` (with `enable_spanner=false`) costs Cloud SQL money only. Spanner comes up only when you explicitly enable it for the migration test, and the teardown gate brings it down.
- **The database decision must be written down** in `docs/decision.md` using the seven-axis rubric. "We used Cloud SQL because it's what I know" fails; "Cloud SQL because the workload is single-region, single-writer, needs full Postgres, and is under budget; runner-up AlloyDB, held for when read load grows" passes.
- Target: Python 3.11+ (or Go 1.22+), `google` provider `~> 6.0`, the Week 06 GKE cluster.

---

## Acceptance criteria

The grading rubric is below. Each box maps to a specific deliverable.

### Correctness & deployment (35%)

- [ ] The gRPC service implements `GetState`, `PutState` (with optimistic-concurrency `expected_version`), and `ListStateByOwner`.
- [ ] The service runs on the **Week 06 GKE cluster** and authenticates via **Workload Identity** (no keyfile anywhere).
- [ ] The service reaches Cloud SQL over the **PSC endpoint** (no public IP on the instance — verified with `gcloud sql instances describe`).
- [ ] `GetState` and `PutState` go to the primary; `ListStateByOwner` may use the cross-region read replica (document the staleness trade-off).
- [ ] A smoke test (a gRPC client, `grpcurl` or a Python client) demonstrates a put-then-get round-trip and a `ListStateByOwner`.

### The database decision & Spanner-readiness (35%)

- [ ] `docs/decision.md` scores the workload on the seven-axis rubric and justifies Cloud SQL over AlloyDB and Spanner in one defensible paragraph (deciding axis + rejected runner-up).
- [ ] The schema is **Spanner-hotspot-safe from day one** (UUID key, no `SERIAL`).
- [ ] `docs/migration.md` is a runbook you have **actually executed once**: it migrates the Cloud SQL data into a single-region Spanner instance via Datastream + Dataflow, and includes the shadow-test result (comparisons, matches, convergence lag) proving the two databases agreed.
- [ ] `infra/spanner.tf` is gated on `var.enable_spanner` so Spanner is opt-in.
- [ ] `repository_spanner.py` exists and passes the same contract tests as `repository_cloudsql.py` (the service can run on either backend).

### Teardown & cost discipline (15%)

- [ ] A \$10 budget alert is armed (screenshot or `gcloud billing budgets list` output in the repo).
- [ ] `make teardown-spanner` deletes the Spanner instance; `make verify-teardown` fails if any Spanner instance still exists.
- [ ] At submission time, `gcloud spanner instances list` is **empty** (Spanner was a temporary migration test, not a running cost).
- [ ] The Cloud SQL instance is either torn down or explicitly documented as intentionally-kept with its monthly cost stated.

### Documentation & the exit plan (15%)

- [ ] `README.md` describes the service, how to deploy it, and how to run the migration test.
- [ ] `docs/exit-plan.md` is the four-part Lecture 2 exit plan: schema lift, application lift, operational lift, and verdict-with-trigger for moving to CockroachDB or YugabyteDB.
- [ ] Inline comments in `repository_cloudsql.py` and `repository_spanner.py` explain the read-your-writes vs read-replica trade-off and the optimistic-concurrency mechanism on each backend.

---

## Suggested implementation outline

The order matters: build the service on Cloud SQL first, prove it, *then* document and test the Spanner path.

### Day 1 (Friday — ~3 hours)

1. Define `current_state.proto` and generate the stubs (`python -m grpc_tools.protoc ...`).
2. Implement `repository_cloudsql.py` against a local Postgres (Docker) first — `psycopg`, the optimistic-concurrency update, the owner-index list query. Write the contract tests here so they are backend-agnostic.
3. Stand up the real Cloud SQL backend from `infra/cloudsql.tf` (reuse Exercise 1: HA + replica + PSC). Point the service at the PSC endpoint.
4. Write `docs/decision.md` using the Exercise 3 rubric — this is the artifact that justifies the whole choice.

### Day 2 (Saturday — ~3.5 hours)

5. Containerize the service (multi-stage Dockerfile from C15) and push to Artifact Registry.
6. Deploy to the Week 06 GKE cluster: `k8s/deployment.yaml`, `service.yaml`, and the Workload-Identity-annotated `serviceaccount.yaml`. Bind the KSA to a GSA with `roles/cloudsql.client`.
7. Smoke-test the deployed service through gRPC (port-forward + `grpcurl`, or a client pod).
8. Run the migration test (Challenge 1 in miniature): `terraform apply -var="enable_spanner=true"`, launch the Datastream→Spanner Dataflow job, run `migrate/shadow_test.py` for at least 15 minutes, capture the results into `docs/migration.md`.

### Day 3 (Sunday — ~1 hour + the half-hour quiz)

9. Write `repository_spanner.py` and confirm the contract tests pass against it (you can run them against the still-running Spanner instance before teardown).
10. **TEAR DOWN SPANNER.** `make teardown-spanner`, then `make verify-teardown`. Capture the empty `gcloud spanner instances list`.
11. Write `docs/exit-plan.md` (the four-part Lecture 2 plan).
12. Final `README.md`, commit, push. Confirm the budget alert is still armed.

---

## The Makefile teardown gate

```makefile
PROJECT ?= $(shell gcloud config get-value project)
SPANNER_INSTANCE ?= current-state-spanner

.PHONY: teardown-spanner verify-teardown teardown

teardown-spanner:
	-gcloud dataflow jobs list --status=active --region=us-central1 \
	  --format="value(id)" | xargs -r -I{} gcloud dataflow jobs cancel {} --region=us-central1
	-gcloud spanner instances delete $(SPANNER_INSTANCE) --quiet
	@echo "Spanner teardown attempted. Run 'make verify-teardown' to confirm."

verify-teardown:
	@if gcloud spanner instances list --format="value(name)" | grep -q "$(SPANNER_INSTANCE)"; then \
	  echo "FAIL: Spanner instance $(SPANNER_INSTANCE) still exists and is BILLING."; \
	  exit 1; \
	else \
	  echo "OK: no Spanner instance. Bill stops here."; \
	fi
	@gcloud billing budgets list --billing-account=$$BILLING_ACCOUNT_ID >/dev/null 2>&1 \
	  && echo "OK: budget alert query succeeded." \
	  || echo "WARN: could not verify budget alert; check the console."

teardown: teardown-spanner verify-teardown
	terraform -chdir=infra destroy -var="project_id=$(PROJECT)" -var="enable_spanner=false" -auto-approve
```

`make verify-teardown` is the graded gate: it exits non-zero if a Spanner instance survives. Run it before you submit.

---

## Anti-goals

The following are explicitly **not** part of this mini-project. Do not pursue them; they distract from the lesson.

- **Multi-region Spanner.** The migration test uses single-region (`regional-us-central1`) to keep the bill under \$5. Multi-region is the capstone stretch goal, not here.
- **A REST gateway / HTTP API.** This is a gRPC service. The capstone's edge (Cloud Run + LB) fronts it later; here it speaks gRPC inside the cluster.
- **Cutover automation.** You document and *test* the migration path; you do not build a zero-downtime automated cutover. The shadow-test proves correctness; the cutover decision is a human one made on the shadow-test evidence.
- **AlloyDB.** The decision doc considers it; the build does not deploy it. If your decision rubric concludes AlloyDB is actually the right answer for your workload, that is a *valid* and interesting submission — document it and deploy AlloyDB instead of Cloud SQL, but the Spanner migration path is still required as the escape-hatch exercise.

---

## Submission

Push the repository to your Week 11 GitHub repository at `mini-project/current-state/`. The instructor reviews by:

1. Cloning the repo.
2. Reading `docs/decision.md`, `docs/migration.md`, and `docs/exit-plan.md`.
3. Confirming the Cloud SQL instance has no public IP (`gcloud sql instances describe`).
4. Confirming the pod uses Workload Identity and has no keyfile.
5. Running `make verify-teardown` — must pass (no Spanner instance billing).

A submission that deploys the service over PSC with Workload Identity, justifies the database choice on the rubric, includes a migration runbook with a real shadow-test result, and passes `make verify-teardown` is a pass. The most common review-fail is a migration doc that was never actually run (no shadow-test numbers) — and the second most common is a surviving Spanner instance. Verify both before submitting.

---

## How this feeds the capstone

The capstone's "Serve" tier specifies: *a GKE Standard cluster running (a) a "current state" gRPC service backed by Spanner regional.* This mini-project **is** that service, built first on Cloud SQL with a tested Spanner path. When you reach Week 15, you flip `enable_spanner=true`, run the migration runbook you wrote here, switch the service to `repository_spanner.py`, and the capstone's Spanner-backed gRPC service exists — because you already proved the path works. The discipline you practiced — *decide on the rubric, build Spanner-ready, test the migration, write the exit plan, tear down what bills you* — is exactly what makes the capstone defensible in the architecture review.

---

**References**

- Cloud SQL — Private Service Connect: <https://cloud.google.com/sql/docs/postgres/configure-private-service-connect>
- GKE — Workload Identity: <https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity>
- Cloud SQL Auth / `roles/cloudsql.client`: <https://cloud.google.com/sql/docs/postgres/iam-roles>
- Spanner — Python client: <https://cloud.google.com/python/docs/reference/spanner/latest>
- Datastream-to-Spanner Dataflow template: <https://cloud.google.com/dataflow/docs/guides/templates/provided/datastream-to-spanner>
- gRPC Python quickstart: <https://grpc.io/docs/languages/python/quickstart/>
