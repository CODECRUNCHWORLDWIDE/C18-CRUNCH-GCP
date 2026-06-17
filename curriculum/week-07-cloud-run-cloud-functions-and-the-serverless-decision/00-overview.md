# Week 7 — Cloud Run, Cloud Functions, and the Serverless Decision

Welcome to **C18 · Crunch GCP**, Week 7. Last week you stood GKE up two ways — Autopilot and Standard — deployed the same FastAPI service to both, wired in-cluster Workload Identity, protected the service with a PodDisruptionBudget, autoscaled it on a custom metric, and ran a zero-downtime upgrade. You ended the week with a cost number for each option and the ability to defend the choice. This week we ask the question Week 06 deliberately set up: *now that you can run a service on Kubernetes, should you?* For a stateless HTTP service that scales to zero overnight, the honest answer is frequently "no — run it on Cloud Run," and by Friday you will be able to prove that with a curve, not a preference.

By Friday you should be able to deploy a **Cloud Run v2 service** and tune the three knobs that actually move latency and cost — `concurrency`, `min-instances`, and CPU allocation (always-allocated vs. request-only) — to hit a target p99 at a defensible monthly bill. You should be able to connect that service to a **private Cloud SQL Postgres instance over Private Service Connect** with **no public IP anywhere on the database**, using the Cloud SQL Python connector with IAM authentication. You should be able to deploy a **Cloud Functions gen2** function and understand that it is *just a Cloud Run service with a Google-managed build step in front of it*. And you should be able to fire a **Cloud Run job** from a GCS object-write through **Eventarc**, so that uploading a file triggers a batch process with no polling loop and no cron. Above all, you should leave the week able to draw the **serverless cost curve** for a real workload and point at the request rate where Cloud Run stops being cheaper than GKE — and compute the **`min-instances=1` break-even threshold** to the dollar.

The first thing to internalize is that **Cloud Run is not "serverless containers" in the marketing sense — it is a request-driven autoscaler in front of your container, billed per 100 milliseconds of allocated resource.** You hand Cloud Run an OCI image that listens on `$PORT`. Cloud Run runs zero copies of it when no requests arrive (if `min-instances=0`), spins up a copy when a request shows up (the cold start), routes up to `concurrency` simultaneous requests to each running copy, and adds more copies when the in-flight request count exceeds what the running copies can absorb. You pay for vCPU-seconds and GiB-seconds *while an instance is handling requests* (in the default request-billing model) plus a small per-request fee, and you pay nothing while scaled to zero. That billing model is the entire economic argument for Cloud Run: a service that is idle 70% of the day costs you nothing for 70% of the day. The entire economic argument *against* Cloud Run is the same fact stated differently — a service that is busy 100% of the day, every day, pays a per-request premium over a VM or a GKE node you have already committed to, and somewhere on the utilization axis the two lines cross. Lecture 1 finds that crossing and puts numbers on it.

The second thing to internalize is that **`concurrency` is the most misunderstood knob in serverless and the one that decides both your latency and your bill.** Cloud Run's default concurrency is 80 — each container instance handles up to 80 simultaneous requests. That default is correct for an I/O-bound service (a thin API that mostly waits on a database) and catastrophic for a CPU-bound one (an image resizer, a JSON-crunching aggregator). If your handler is CPU-bound and you leave concurrency at 80, eighty requests pile onto one vCPU's worth of compute, your p99 explodes, and your instinct — "add more instances" — does not help because the bottleneck is *inside* the instance. The fix is to *lower* concurrency so each instance handles fewer requests and Cloud Run scales out horizontally instead of stacking work onto a saturated instance. Exercise 1 is the hands-on version of this: you deploy a deliberately CPU-bound service, watch p99 degrade at concurrency 80, tune concurrency and CPU allocation down to a target latency, and read the cost consequence of the tuning. Concurrency is where serverless stops being magic and starts being capacity planning.

The third thing to internalize is that **the private-database story is the part most teams get wrong, and Private Service Connect is the 2026-correct answer.** A Cloud Run service that talks to a Cloud SQL instance over a *public* IP — even with the Cloud SQL Auth Proxy and TLS — is a finding in any serious security review: the database has a routable public address, and "we locked it down with authorized networks" is one misconfiguration away from an open Postgres on the internet. The right shape is a Cloud SQL instance with **no public IP at all**, reachable only over **Private Service Connect** from inside your VPC, with Cloud Run attached to that VPC through Direct VPC egress, authenticating with **IAM database authentication** so there is no static password to leak. Lecture is split: the cost curve is Lecture 1, but the PSC wiring is taught hands-on in Exercise 2 and is the spine of the mini-project. Get this pattern right once this week and you reuse it in Week 11 (the database deep-dive) and again in the capstone ingest path.

The fourth thing to internalize is that **Cloud Functions gen2, Cloud Run jobs, and Eventarc are three faces of one platform, and knowing that collapses a lot of confusion.** Cloud Functions gen2 *is* Cloud Run under the hood — when you deploy a gen2 function, Google runs Buildpacks to turn your handler into a container and deploys it as a Cloud Run service you can see in the Cloud Run console. A Cloud Run *job* is the same runtime but for run-to-completion batch work instead of request-serving: it runs your container, waits for it to exit 0, and does not listen on a port. **Eventarc** is the glue — it takes events from across GCP (a GCS object finalized, a Pub/Sub message, an Audit Log entry) and delivers them as CloudEvents-formatted HTTP requests to a Cloud Run service, a gen2 function, or (via a Pub/Sub + executions shim) a Cloud Run job. Once you see that "function," "service," and "job" are three packaging conventions over the same Knative-derived runtime, and that Eventarc is a uniform event router in front of all three, the platform stops looking like five separate products and starts looking like one. Exercise 3 wires the GCS → Eventarc → Cloud Run job path end to end.

The fifth thing to internalize is that **the `min-instances=1` decision is a real, computable financial trade, not a vibe.** Setting `min-instances=0` means you pay nothing when idle but every cold request waits for a container to start (hundreds of milliseconds to several seconds depending on your image and whether you use startup CPU boost). Setting `min-instances=1` means one instance is always warm — no cold start for the first concurrent request — but you now pay for that one instance 24/7 at the *idle* (always-allocated, no-request) rate. The break-even question is: *at what level of traffic and cold-start sensitivity does the cost of one always-warm instance pay for itself versus the cost (in latency, in lost conversions, in SLO budget) of cold starts?* Lecture 2 derives the formula, plugs in 2026 list prices, and gives you a spreadsheet-shaped model you can defend in a review. The challenge this week makes you benchmark cold start at `min-instances=0`, `=1`, and `=3` on a real service and produce the monthly-cost comparison for each.

This week's mini-project is the **ingest service** the rest of the course leans on: a Cloud Run v2 service backed by private Cloud SQL over PSC, with an Eventarc-triggered Cloud Run job, deployed via the **Week 04 module library** on the **Week 03 VPC**. Week 08 fronts this exact service with a global HTTPS load balancer and Cloud Armor; Week 13 instruments it with OpenTelemetry; and it is the ingest pattern the capstone reuses. The teardown gate is non-negotiable — Cloud SQL is the first thing in this course that bills per hour whether or not you touch it.

## Learning objectives

By the end of this week, you will be able to:

- **Deploy** a Cloud Run v2 service from an OCI image with Terraform on the `google` provider, setting `concurrency`, `min-instances`, `max-instances`, CPU/memory limits, and the CPU allocation model (always-allocated vs. request-only) explicitly rather than by default.
- **Tune** concurrency and CPU allocation against a target latency: identify whether a handler is CPU-bound or I/O-bound, pick a concurrency that keeps p99 under target, and read the cost consequence of the choice.
- **Connect** a Cloud Run service to a Cloud SQL Postgres instance that has **no public IP**, over **Private Service Connect**, using Direct VPC egress and the Cloud SQL Python connector with **IAM database authentication** (no static password).
- **Explain** that Cloud Functions gen2 is a Cloud Run service with a Buildpacks build step, deploy one, and find the underlying Cloud Run service it produces.
- **Trigger** a Cloud Run job from a GCS object-finalize event through **Eventarc**, passing the object name to the job, with the correct IAM (the Eventarc trigger SA, the GCS service agent's Pub/Sub publish grant, and the job invoker role).
- **Draw** the serverless cost curve for a workload: model Cloud Run cost as a function of request rate and CPU-seconds-per-request, model GKE cost as committed node capacity, and identify the crossover request rate where GKE becomes cheaper.
- **Compute** the `min-instances=1` break-even threshold for a service from its cold-start frequency, cold-start penalty, idle instance cost, and the business cost of a slow request.
- **Defend** GKE vs. Cloud Run for a specific workload on hard numbers — utilization, request shape, cold-start tolerance, and total monthly cost — not on taste.

## Prerequisites

- **Weeks 01 through 06 of C18 complete.** You have a landing zone (Week 01), Workload Identity Federation for deploys (Week 02), a multi-region shared VPC with Cloud NAT, Private Google Access, and secondary ranges (Week 03), a Terraform module library with remote state in GCS (Week 04), a regional MIG behind an internal LB (Week 05), and a GKE cluster you can cost-compare against (Week 06). This week's Terraform consumes the Week 03 VPC module and the Week 04 conventions directly, and reuses last week's cost-reasoning muscle on a new axis.
- **Working CLI:** `gcloud >= 470.0.0`, `terraform >= 1.9` (or `tofu >= 1.8`), `docker` (or `podman`) to build the service image, `psql >= 15` for poking at the database, and `hey` (or `oha`) for load generation. Verify with the smoke check in Exercise 1.
- **Python 3.11+ and FastAPI basics.** The service we deploy is a small FastAPI app served by `uvicorn`. You should be able to read `async def` handlers; you should not be learning FastAPI this week. We provide the code.
- **Postgres literacy at the C16 level.** You can write a `CREATE TABLE`, reason about a connection pool, and explain why opening a fresh connection per request is a bad idea. The database is Postgres 15 on Cloud SQL; you are expected to know SQL, not to be learning it.
- **A GCP project with billing and a budget alert armed (Week 01).** Cloud Run scales to zero and costs nothing idle, but **Cloud SQL bills per hour whether or not you connect to it** — even the smallest `db-perf-optimized-N-2`/`db-g1-small` instance is the first always-on cost in this course. Everything in this week runs inside the \$300 free trial if you honor the teardown gate. Budget ~\$3–6 if you leave a Cloud SQL instance running overnight by accident.

## Topics covered

- **Cloud Run v2 services.** The `google_cloud_run_v2_service` resource, the container contract (`$PORT`, stateless, ephemeral filesystem), the request-driven autoscaler, revisions and traffic splitting, the ingress setting (`all` / `internal` / `internal-and-cloud-load-balancing`), and the execution environment (gen1 vs. gen2 sandboxing).
- **Concurrency.** What `max_instance_request_concurrency` actually controls, the default of 80, the difference between I/O-bound and CPU-bound handlers, why lowering concurrency fixes CPU-bound p99, and the interaction with `max-instances` as a hard ceiling on cost and on database connections.
- **CPU allocation.** Always-allocated CPU (`cpu_idle = false`) vs. CPU-only-during-requests (`cpu_idle = true`), startup CPU boost, why background work and connection pools need always-allocated CPU, and how the choice changes both latency and the per-second billing rate.
- **`min-instances` and cold starts.** What a cold start is (image pull, container start, app init, first-request warmup), the cold-start penalty by image size and language, startup CPU boost, `min-instances` as the warm-pool floor, and the break-even arithmetic.
- **Cloud Run jobs.** `google_cloud_run_v2_job`, run-to-completion semantics, tasks and parallelism (`task_count`, `parallelism`), the `CLOUD_RUN_TASK_INDEX` / `CLOUD_RUN_TASK_COUNT` env vars, retries, and why a job has no `$PORT`.
- **Cloud SQL over Private Service Connect.** A Cloud SQL instance with `ipv4_enabled = false` and PSC enabled, the PSC endpoint (a forwarding rule in your VPC pointing at the instance's service attachment), DNS for the PSC endpoint, and why this beats both public IP + Auth Proxy and the legacy private-services-access (VPC peering) approach.
- **The Cloud SQL connectors and IAM auth.** The Cloud SQL Python connector (`cloud-sql-python-connector`), `IPTypes.PSC`, IAM database authentication (`enable_iam_login`), the database user that maps to a service account, and the disappearance of the static password.
- **Direct VPC egress.** Attaching a Cloud Run service to a VPC subnet directly (the 2026-default, replacing Serverless VPC Access connectors for most cases), egress settings (`all-traffic` vs. `private-ranges-only`), and how this lets Cloud Run reach the PSC endpoint.
- **Cloud Functions gen2.** That gen2 functions are Cloud Run services built by Buildpacks, the `google_cloudfunctions2_function` resource, the difference from gen1, and when you would still reach for a function over a hand-built Cloud Run service (rarely, in 2026 — mostly for the event-trigger ergonomics, which Eventarc now gives you on plain Cloud Run anyway).
- **Eventarc.** The CloudEvents delivery model, the supported event sources (Cloud Audit Logs, direct Pub/Sub, and direct sources like GCS finalize), the trigger → transport (Pub/Sub) → destination (Cloud Run / function / job) path, and the IAM the trigger needs (the trigger service account, the GCS service agent's `pubsub.publisher`, and `run.invoker` on the destination).
- **The serverless cost curve.** Cloud Run pricing components (vCPU-second, GiB-second, per-request, idle rate when always-allocated), GKE cost as committed capacity, the crossover analysis, and the `min-instances=1` break-even formula.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract. The Cloud SQL work is best done with a billing dashboard open in a second tab — the database bills per hour the whole time it runs, and the discipline of "stand it up, use it, tear it down" is the same muscle you built in Week 06, now with a resource that does not scale to zero.

| Day       | Focus                                                          | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Cloud Run v2 model; the serverless cost curve (Lecture 1)       |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Concurrency & CPU allocation tuning (Exercise 1)                |    1h    |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5h      |
| Wednesday | Cloud SQL over PSC, IAM auth, Direct VPC egress (Exercise 2)    |    1h    |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Thursday  | `min-instances=1` break-even (Lecture 2); Eventarc (Exercise 3) |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0.5h     |    0.5h    |     7h      |
| Friday    | Mini-project — ingest service via Week 04 modules               |    0h    |    0h     |     1h     |    0.5h   |   0h     |     3.5h     |    0.5h    |     5.5h    |
| Saturday  | Mini-project deep work; cost report; teardown gate              |    0h    |    0h     |     0h     |    0h     |   0h     |     3.5h     |    0h      |     3.5h    |
| Sunday    | Quiz, cost-curve writeup, polish                                |    0h    |    0h     |     0h     |    1h     |   0h     |     2h       |    0.5h    |     3.5h    |
| **Total** |                                                                | **6h**   | **7h**    | **3h**     | **3.5h**  | **4h**   | **13h**      | **3h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | Cloud Run v2 docs, the concurrency/CPU tuning guides, Cloud SQL PSC + IAM-auth docs, the Cloud SQL Python connector, Cloud Functions gen2, Eventarc, the pricing pages, and the talks worth your time |
| [lecture-notes/01-the-serverless-cost-curve.md](./02-lecture-notes/01-the-serverless-cost-curve.md) | The serverless cost curve: where Cloud Run beats GKE and where GKE beats Cloud Run — the model, the 2026 prices, and the crossover request rate |
| [lecture-notes/02-min-instances-one-break-even.md](./02-lecture-notes/02-min-instances-one-break-even.md) | The "`min-instances=1` pays for itself" threshold and how to compute it — cold-start anatomy, the break-even formula, and a worked spreadsheet |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-tune-concurrency-and-cpu.md](./03-exercises/exercise-01-tune-concurrency-and-cpu.md) | Deploy a stateless Cloud Run v2 service and tune concurrency and CPU allocation for a target latency |
| [exercises/exercise-02-cloud-run-to-private-cloud-sql-over-psc.py](./03-exercises/exercise-02-cloud-run-to-private-cloud-sql-over-psc.py) | A FastAPI service that connects to a private Cloud SQL Postgres instance over PSC with IAM auth and no public IP — the app plus the full runbook |
| [exercises/exercise-03-eventarc-gcs-to-cloud-run-job.tf](./03-exercises/exercise-03-eventarc-gcs-to-cloud-run-job.tf) | Terraform that wires a GCS object-finalize event through Eventarc to a Cloud Run job, with all the IAM |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-coldstart-bakeoff-behind-cloud-armor.md](./04-challenges/challenge-01-coldstart-bakeoff-behind-cloud-armor.md) | Deploy the service with private Cloud SQL over PSC behind Cloud Armor, benchmark cold-start at min-instances 0/1/3, and produce a monthly-cost comparison |
| [quiz.md](./05-quiz.md) | 13 questions, answer key at the bottom |
| [homework.md](./06-homework.md) | Five problems with rubric and time estimates |
| [mini-project/README.md](./07-mini-project/00-overview.md) | Full spec for the ingest service (Cloud Run + private Cloud SQL over PSC + Eventarc job) that Week 08 fronts, Week 13 instruments, and the capstone reuses |

## The teardown promise

C18 treats `terraform destroy` as a contract, and Week 07 raises the stakes that Week 06 introduced. Cloud Run scales to zero and costs you nothing idle — but **Cloud SQL does not scale to zero**, and a forgotten Cloud SQL instance is the single most common way a Crunch GCP learner burns their free-trial credit. Every exercise, the challenge, and the mini-project ends with an explicit teardown step. The mini-project teardown is a **gate**: you do not pass the week until you have run `terraform destroy` and confirmed in the Cloud Console that no Cloud SQL instances, no PSC endpoints (forwarding rules), no Cloud Run services or jobs, no Eventarc triggers, and no leaked Artifact Registry images remain.

```
cloud sql: 0 · cloud run services: 0 · jobs: 0 · eventarc triggers: 0 · psc endpoints: 0  →  PASS
```

The one nuance: because Week 08 fronts this exact service with a load balancer and Week 13 instruments it, your teardown must be **clean and replayable**. The grader runs `terraform apply` from your Week 07 code in Week 08; if the ingest service does not come back up identically and reach its database, you lose the points then, not now. Treat the Terraform you write this week as production code you will read again in a month.

## What's not here

Week 07 introduces serverless compute and the serverless cost decision. It does **not** cover:

- **The global HTTPS load balancer and Cloud Armor in front of Cloud Run.** That is Week 08. This week, your Cloud Run service either takes its default `*.run.app` URL or sits behind an internal ingress; the edge layer (LB → Cloud CDN → Cloud Armor) is next week's subject, and the mini-project is explicitly designed to be fronted by it.
- **Cloud SQL HA, read replicas, and the AlloyDB/Spanner decision.** We use a single zonal Cloud SQL instance this week — the smallest one that exists — because the lesson is *connectivity and serverless integration*, not database operations. Week 11 is the database deep-dive: HA, replicas, and when you should not be using Cloud SQL at all.
- **OpenTelemetry instrumentation of the service.** The service emits plain structured logs this week. Traces, metrics, SLOs, and burn-rate alerts are Week 13, which instruments this exact service.
- **Workflows and Cloud Composer for orchestration.** Eventarc fires a single job from a single event this week. Multi-step orchestration (Workflows, Composer/Airflow) is a Phase 3 data-pipeline concern; we name it and defer it.
- **Cloud Functions gen1.** Gen1 is legacy in 2026. We mention it once to explain why gen2 exists and never deploy it. New work is gen2-or-Cloud-Run.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **Cloud Run "About instance autoscaling"** page end to end and map every paragraph onto a knob in your Terraform: <https://cloud.google.com/run/docs/about-instance-autoscaling>.
- Read the **Cloud SQL "Connect using Private Service Connect"** guide and reproduce the PSC endpoint creation by hand (`gcloud`) before you let Terraform do it, so you understand what the module is actually creating: <https://cloud.google.com/sql/docs/postgres/configure-private-service-connect>.
- Benchmark a **Go** Cloud Run service against the Python one from this week. A statically-linked Go binary in a `scratch`/`distroless` image cold-starts dramatically faster than a Python + `uvicorn` image; measure the delta and note how it shifts the `min-instances=1` break-even.
- Wire an **Eventarc trigger from a direct Pub/Sub topic** (not GCS) to the same Cloud Run job and compare the IAM and latency to the GCS-finalize path.
- Model the **cost curve for your own day-job service** in a spreadsheet using the Lecture 1 formulas and the current pricing pages. Bring a number to office hours: "at our 40 RPS sustained, Cloud Run would cost \$X/month and our current GKE footprint costs \$Y."

## Up next

Continue to **Week 08 — Cloud Load Balancing & Cloud Armor** once you have torn the mini-project down cleanly. Week 08 takes the ingest service you build this week and puts the GCP edge in front of it: a global external HTTPS load balancer with a serverless NEG backend, Cloud CDN, and a Cloud Armor policy that rate-limits per-IP and blocks an SQLi probe with a preconfigured WAF rule. The Cloud Run `internal-and-cloud-load-balancing` ingress setting you learn this week is the hook Week 08 attaches to. The cost-curve reasoning you build this week — utilization, request shape, the crossover point — is the same reasoning you bring to the midterm architecture review at the end of Week 08, where you defend the entire Phase 1+2 system with a cost model and an exit plan.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
