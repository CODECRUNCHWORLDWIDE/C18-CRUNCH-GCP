# Mini-Project — The Ingest Service: Cloud Run + private Cloud SQL over PSC + an Eventarc-triggered job

> Build the ingest pattern the rest of the course leans on. A stateless Cloud Run v2 service validates and persists events to a Cloud SQL Postgres instance that has **no public IP** — reachable only over **Private Service Connect**, authenticated with **IAM database auth**, no password anywhere. A **Cloud Run job**, fired by **Eventarc** when a file lands in a GCS bucket, batch-imports events from that file into the same database. Everything is deployed via the **Week 04 module library** on the **Week 03 VPC**. Week 08 fronts this service with a load balancer and Cloud Armor; Week 13 instruments it with OpenTelemetry; the capstone reuses this exact ingest shape. The teardown is a gate.

This is the first mini-project in C18 that builds a *durable* artifact other weeks extend rather than rebuild. Treat the Terraform as production code you will read again in a month — because you will, in Week 08 and Week 13.

**Estimated time:** ~13 hours (split across Thursday, Friday, Saturday, Sunday in the suggested schedule).

---

## What you will build

A single Terraform root module (`ingest/`) that, on `terraform apply`, stands up:

1. **A Cloud SQL Postgres 15 instance** (`crunch-ingest-db`) with:
   - `ipv4_enabled = false` (no public IP — the database has no routable internet address).
   - Private Service Connect enabled, with a **PSC endpoint** (forwarding rule + reserved internal IP) in the Week 03 VPC.
   - `cloudsql.iam_authentication = on`.
   - One database, `crunch`, and an **IAM service-account database user** mapped to the ingest service account.
2. **A Cloud Run v2 service** (`crunch-ingest`) that:
   - Runs the FastAPI ingest app (reuse / extend Exercise 2's app).
   - Runs **as the ingest service account**.
   - Uses **Direct VPC egress** into the Week 03 subnet so it can reach the PSC endpoint.
   - Connects to Postgres via the Cloud SQL Python connector with `IPTypes.PSC` and `enable_iam_auth=True`.
   - Has `ingress = "internal-and-cloud-load-balancing"` so Week 08 can front it with an LB (and it is not publicly reachable on its `*.run.app` URL).
   - Sets `concurrency`, `min_instances`, `max_instances`, CPU/memory, and CPU allocation **explicitly**, with a comment justifying each value.
3. **A GCS bucket** (`crunch-ingest-drop`) for batch-import files, with uniform bucket-level access and public-access prevention enforced.
4. **A Cloud Run job** (`crunch-ingest-importer`) that reads a file from the bucket, parses it, and bulk-inserts the events into the same Cloud SQL database over PSC (same connector, same IAM identity).
5. **An Eventarc trigger** (`crunch-ingest-gcs`) that fires on `google.cloud.storage.object.v1.finalized` in the bucket and launches the importer job (via the launcher-service hop from Exercise 3, or directly if you target a gen2 function shim — your choice, justify it).
6. **All the IAM**: the ingest SA's `cloudsql.client` + `cloudsql.instanceUser`, the GCS service agent's `pubsub.publisher`, the Eventarc trigger SA's `eventarc.eventReceiver` + `run.invoker`, and the launcher's job-execution rights.

You ship **one repository** structured as:

```
ingest/
├── README.md                  # the report (see Documentation criteria)
├── main.tf                    # root module: composes the resources below
├── variables.tf               # project_id, region, vpc, subnet, image refs, knobs
├── outputs.tf                 # service url, db connection name, bucket, job name
├── cloud_sql.tf               # instance (no public IP) + PSC endpoint + IAM DB user
├── service.tf                 # Cloud Run v2 service (explicit knobs)
├── job.tf                     # Cloud Run job + Eventarc trigger + launcher
├── iam.tf                     # every grant, each with a comment
├── app/
│   ├── service/               # FastAPI ingest service (main.py, requirements, Dockerfile)
│   └── importer/              # the job body (main.py, requirements, Dockerfile)
└── docs/
    ├── cost-model.md          # the serverless cost analysis (Lecture 1 + 2 applied)
    └── architecture.md        # the request/event path + every private-choice rationale
```

Where it helps, **consume the Week 04 modules** (the `vpc` module to read outputs, and the project conventions for naming, labels, and remote state). You are not rebuilding the VPC; you are deploying onto it. If your Week 04 module library exposes a reusable `cloud-run-service` or `cloud-sql` module, use it; if not, this mini-project is a good reason to add one (and Week 08/13 will thank you).

---

## Rules

- **Terraform (or OpenTofu) only** for infrastructure. Remote state in GCS with locking, per the Week 04 conventions. No console click-ops except to *inspect*.
- **No public IP on the database. Ever.** Any submission whose Cloud SQL instance has `ipv4Enabled = true` fails outright. This is the central skill.
- **No database password anywhere.** IAM auth only. No password in env, in `terraform.tfvars`, in Secret Manager, or in the connection string. A submission with a static DB password fails the security criterion.
- **The service is not publicly reachable on its `*.run.app` URL.** Ingress must be `internal-and-cloud-load-balancing` (or `internal`). Week 08's LB is the public door; this week there is no public door.
- Target images: build with a **multi-stage slim** Dockerfile (cold-start hygiene). Python 3.12. `--platform=linux/amd64`.
- `<TreatWarningsAsErrors>`-equivalent discipline for Terraform: `terraform validate` and `terraform fmt -check` must pass clean. No `terraform apply` with a dirty plan you don't understand.
- The ingest app should be **honest production-shaped code**: input validation, bounded connection pool, structured error responses, a `/healthz` for probes. Not sabotaged, not toy.

---

## Acceptance criteria

The grading rubric is below. Each box maps to a specific deliverable.

### Correctness & connectivity (35%)

- [ ] `terraform apply` from a clean state stands up the entire system with no manual steps.
- [ ] The Cloud SQL instance has `ipv4Enabled = false` (prove with `gcloud sql instances describe`).
- [ ] A PSC endpoint (forwarding rule) in the Week 03 VPC points at the instance's service attachment.
- [ ] `GET /whoami` on the service (via an authenticated call, or via the Week 08 LB later) returns the **ingest service account** as `current_user` — proving IAM auth, no password.
- [ ] `POST /events` writes a row over the private path; `GET /events/count` reflects it.
- [ ] Uploading a file to `crunch-ingest-drop` triggers the importer job within seconds, and the job bulk-inserts the file's events into the same database (verify the count went up).
- [ ] The service's `*.run.app` URL is **not** publicly reachable (ingress is internal / LB-only).

### Serverless decision & cost (25%)

- [ ] `docs/cost-model.md` models the monthly cost of this service on Cloud Run using the Lecture 1 active-instance-seconds method, for a stated traffic shape (you choose and justify it).
- [ ] It computes the **crossover RPS** vs. a dedicated GKE footprint, and vs. a shared cluster, using the lecture formulas.
- [ ] It applies the Lecture 2 **`min-instances=1` break-even** to this service, names a `c_cold`, and states which floor you ship and why.
- [ ] The chosen `concurrency`, `min_instances`, and CPU allocation in `service.tf` **match** the cost-model recommendation, each with a one-line comment in the Terraform justifying it. (E.g. "concurrency=80 because the handler is I/O-bound — see cost-model.md §2.")

### Security posture (20%)

- [ ] No public IP on the database (already above, repeated because it's load-bearing).
- [ ] No password anywhere (IAM auth).
- [ ] The ingest SA has **least privilege**: `cloudsql.client` + `cloudsql.instanceUser`, `storage.objectViewer` on the drop bucket (for the importer), and nothing broader. No `roles/editor`, no `roles/owner`.
- [ ] The GCS bucket has uniform bucket-level access and public-access prevention enforced.
- [ ] `iam.tf` has a comment on every grant explaining *why* that principal needs that role. A reviewer should be able to audit it in five minutes.

### Documentation (20%)

- [ ] `docs/architecture.md` draws the request path (client → [Week 08 LB] → Cloud Run → PSC → Cloud SQL) and the event path (GCS finalize → Eventarc → launcher → importer job → Cloud SQL), with one line justifying each private/security choice.
- [ ] `README.md` (the report) explains how to apply, how to verify, and how to tear down, and contains the teardown confirmation line.
- [ ] The connection-pool sizing decision is documented: `pool_size × max_instances` vs. the Cloud SQL connection limit, with the actual numbers.
- [ ] A "what Week 08 and Week 13 will attach" note: the ingress setting that lets Week 08 front it, and where Week 13 will add OpenTelemetry. (This is the compounding contract.)

---

## Suggested implementation outline

The order matters: get the private database path working first (it's the hard part), then the service, then the event-driven job, then the cost model.

### Day 1 (Thursday — ~0.5h kickoff, then Friday) — the private database path

1. Scaffold `ingest/` and wire remote state per Week 04. Read the Week 03 VPC outputs (network + subnet names) into `variables.tf`.
2. Write `cloud_sql.tf`: the instance with `ipv4_enabled = false`, PSC enabled, IAM auth on, the `crunch` database, and the IAM SA database user. Use `google_sql_database_instance`, `google_sql_database`, `google_sql_user` (type `CLOUD_IAM_SERVICE_ACCOUNT`).
3. Create the PSC endpoint: reserve an internal address in the subnet (`google_compute_address`), then a `google_compute_forwarding_rule` targeting `pscServiceAttachmentLink`. This is the piece most likely to fight you — get it working before anything else.
4. `terraform apply` just the database + PSC. Verify `ipv4Enabled = false`. Stop here if you can't reach it yet — the service comes next.

### Day 2 (Friday — ~3.5h) — the service

5. Build the FastAPI service image (reuse Exercise 2's `app/main.py`, extend with input validation and a real `POST /events` schema). Push to Artifact Registry.
6. Write `service.tf`: the Cloud Run v2 service with `ingress = "internal-and-cloud-load-balancing"`, Direct VPC egress (`vpc_access { network_interfaces { ... } egress = "PRIVATE_RANGES_ONLY" }`), running as the ingest SA, with the env the connector needs, and **explicit** concurrency / min / max / CPU.
7. `terraform apply`. Verify with an authenticated `curl` (mint an identity token) that `/whoami` returns the SA and `POST /events` writes a row over PSC.
8. Write `iam.tf` properly — least privilege, every grant commented.

### Day 3 (Saturday — ~3.5h) — the event-driven job + cost model

9. Build the importer job image (`app/importer/`): reads `BUCKET`/`OBJECT` env, downloads the file, parses events (CSV or JSON-lines — your choice, document the format), bulk-inserts into Cloud SQL via the same connector/IAM identity.
10. Write `job.tf`: the `google_cloud_run_v2_job`, the launcher service (from Exercise 3), and the `google_eventarc_trigger`. Wire the IAM (GCS service agent `pubsub.publisher`, trigger SA `eventReceiver` + `run.invoker`, launcher `run.developer` + `actAs`).
11. `terraform apply`. Drop a file into the bucket; verify the job runs and the event count rises.
12. Write `docs/cost-model.md`: model the service's monthly cost, compute the crossover vs. GKE, apply the `min-instances=1` break-even, and reconcile the numbers with the knobs in `service.tf`.

### Day 4 (Sunday — ~2h) — polish, report, teardown gate

13. Write `docs/architecture.md` and the `README.md` report. Document the connection-pool math and the Week 08/13 attach points.
14. Run `terraform fmt -check` and `terraform validate` clean.
15. **Teardown gate** (below). Confirm everything is gone. Put the confirmation line in `README.md`.

---

## The connection-pool trap (read before you set max-instances)

This is the footgun that bites teams in production and the reason the mini-project makes you document the math. Every warm Cloud Run instance opens its own SQLAlchemy pool. With `pool_size = P` and `max_instances = N`, the service can hold up to `N × (P + max_overflow)` connections open against Cloud SQL. The smallest Cloud SQL tiers cap total connections low (often a few dozen to ~100 depending on tier and flags). If `N × P` exceeds that cap, instances fail to connect under load — a failure that only appears at scale-out, which is the worst time to discover it.

Do the arithmetic explicitly in `docs/`:

```
max_instances (N) × (pool_size + max_overflow) ≤ cloud_sql_max_connections × safety_margin
```

For this mini-project, `N = 4`, `pool_size = 2`, `max_overflow = 1` → up to `4 × 3 = 12` connections, comfortably under any tier's limit. If you raise `max_instances`, shrink the pool or raise the instance tier — and document the trade. This is exactly the kind of cross-resource reasoning the capstone rewards.

---

## Anti-goals

The following are explicitly **not** part of this mini-project. Do not pursue them; they distract from the lesson or belong to a later week.

- **The load balancer and Cloud Armor.** That is Week 08. This week ends at `internal-and-cloud-load-balancing` ingress with no public door. (The *challenge* does a minimal LB+Armor; the mini-project deliberately does not, to keep the surface focused.)
- **Cloud SQL HA, read replicas, failover.** A single zonal instance. Week 11 is the database deep-dive.
- **OpenTelemetry / tracing / SLOs.** Structured logs only this week. Week 13 instruments this exact service.
- **Multi-region.** One region. The capstone goes multi-region; this is the single-region ingest building block.
- **A full migration framework.** Inline `CREATE TABLE IF NOT EXISTS` on startup is fine for the exercise. Production uses Alembic; name it, don't build it.

---

## How this compounds (the contract with future weeks)

- **Week 08** fronts `crunch-ingest` with a global external HTTPS load balancer, a serverless NEG, Cloud CDN, and a Cloud Armor policy. The `internal-and-cloud-load-balancing` ingress you set this week is the hook it attaches to. If your teardown is not replayable, Week 08 fails when the grader runs your `terraform apply`.
- **Week 13** adds OpenTelemetry to the service and the importer job, exports traces/metrics/logs to Cloud Trace + Monitoring + Logging, and defines an SLO + burn-rate alert on the ingest path. Leave the code structured so instrumentation is a wrapper, not a rewrite.
- **The capstone** reuses this exact ingest shape: a stateless, autoscaled, private-database-backed Cloud Run service that validates and persists events, with `min-instances=1` in the primary region and `=0` in standby (the Lecture 2 multi-region refinement). The cost model you write here is the seed of the capstone cost report.

---

## Submission

Push the repository to your Week 7 GitHub repo at `mini-project/ingest/`. The instructor reviews by:

1. Reading `docs/cost-model.md`, `docs/architecture.md`, and `iam.tf`.
2. Running `terraform apply` from your code (on the Week 03 VPC) and confirming the database has no public IP, the service reaches it over PSC, and a dropped file triggers the importer.
3. Running `terraform destroy` and confirming a clean teardown.

A submission whose `terraform apply` brings the system up, whose database has no public IP and no password, whose cost model matches its knobs, and whose `terraform destroy` is clean is a pass. The most common review-fail is "the database came up with a public IP" or "there's a password in tfvars" — both are automatic fails on the security criterion. Check before submitting.

---

## Teardown gate (non-negotiable)

Cloud SQL bills per hour whether or not you touch it. You do not pass the week until you have torn the system down and confirmed nothing remains:

```bash
terraform destroy -auto-approve   # from ingest/

# Then confirm in the project:
gcloud sql instances list                                  # expect: empty
gcloud run services list --region=us-central1              # expect: no crunch-ingest
gcloud run jobs list --region=us-central1                  # expect: no importer
gcloud eventarc triggers list --location=us-central1       # expect: empty
gcloud compute forwarding-rules list                       # expect: no PSC endpoint
```

Put this line at the bottom of your `README.md`:

```
cloud sql: 0 · cloud run services: 0 · jobs: 0 · eventarc triggers: 0 · psc endpoints: 0  →  PASS
```

Because Week 08 rebuilds this from your Terraform, your teardown must be **clean and replayable** — no orphaned forwarding rules, no leaked reserved addresses, no state pointing at deleted resources. A teardown that requires hand-deletion in the console is a failed teardown, and you lose the points in Week 08, not now.

---

**References**

- Cloud Run — connect to Cloud SQL: <https://cloud.google.com/sql/docs/postgres/connect-run>
- Cloud SQL — Private Service Connect: <https://cloud.google.com/sql/docs/postgres/configure-private-service-connect>
- Cloud SQL — IAM database authentication: <https://cloud.google.com/sql/docs/postgres/iam-authentication>
- Cloud SQL Python connector: <https://github.com/GoogleCloudPlatform/cloud-sql-python-connector>
- Cloud Run — Direct VPC egress: <https://cloud.google.com/run/docs/configuring/vpc-direct-vpc>
- Eventarc — Cloud Storage trigger: <https://cloud.google.com/eventarc/docs/run/create-trigger-storage-gcloud>
- `google_cloud_run_v2_service` / `_v2_job` / `google_eventarc_trigger`: <https://registry.terraform.io/providers/hashicorp/google/latest/docs>
