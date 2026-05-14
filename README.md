# C18 · Crunch GCP — Google Cloud Engineering

> A 15-week intensive on Google Cloud as a platform discipline. You leave with a production-grade GKE-based system: multi-region, observable, Cloud Armor-protected, BigQuery-instrumented, Vertex AI-served, and runnable on the free trial. The Crunch Labs tier for engineers who already know Docker, Kubernetes, and Terraform and want a real cloud under their hands.

[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![GCP](https://img.shields.io/badge/cloud-Google%20Cloud-4285F4.svg)](https://cloud.google.com/)
[![Built in the open](https://img.shields.io/badge/built-in%20the%20open-B98F3E.svg)](https://github.com/CODE-CRUNCH-CLUB)

This is the Google Cloud track of the Code Crunch Crunch Labs tier. It assumes you have completed **C1** and **C15 (Crunch DevOps)** or carry equivalent industry experience with Docker, Kubernetes, and Terraform. It also assumes Linux fluency at the C14 level. Crunch GCP is not a "GCP for beginners" survey. It is a production-engineering course that uses Google Cloud as the substrate.

If you've never written a Terraform module from scratch, never read a `kubectl describe pod` to debug a `CrashLoopBackOff`, or have never paged on a Saturday morning, do C15 first. This track will overwhelm you in week three.

---

## Who this course is for

Four personas drive the design. If you recognize yourself in one of these, you are in the right room.

- **The DevOps engineer adding GCP.** You already run a CI/CD platform on AWS or on-prem Kubernetes. Your company is acquiring a team that lives on Google Cloud, or you've been asked to evaluate BigQuery and Pub/Sub against your current Kafka/Spark stack. You need the platform vocabulary, the IAM model, and the failure modes — not another `gcloud auth login` tutorial.
- **The senior Python backend engineer leveling up to platform.** You've shipped FastAPI services for three years. You can read a flame graph and tune a Postgres query. You now want to own the system end-to-end — the GKE cluster, the VPC, the load balancer, the OpenTelemetry pipeline, the SLOs — and step into a platform or staff role.
- **The SRE preparing for Google Professional Cloud Architect.** You can already pass the exam on theory. You want the practical reps: a real multi-region failover, a real Cloud Armor rule that bites, a real Spanner migration, a real on-call rotation. C18 is the lab the certification doesn't give you.
- **The founder choosing GCP for a new product.** You're picking a cloud and you need to know what you're walking into: the billing surface, the IAM mistakes, the regional gotchas, the AI / data primitives, and the exit-cost shape. By Week 15 you'll have a defensible architecture for your own product, costed out, with a runbook.

---

## What you can do at the end of 15 weeks

1. **Design** a multi-region GCP architecture from a blank diagram: VPC topology, IAM hierarchy, project/folder layout, billing accounts, and the failover plan, defending each choice against open-source alternatives.
2. **Provision** that architecture with Terraform (or OpenTofu) and the `google` and `google-beta` providers, organized as reusable modules with remote state in GCS and state locking.
3. **Operate** a GKE cluster — Autopilot for one workload, Standard with node pools for another — including upgrades, surge config, Workload Identity, and Pod Disruption Budgets.
4. **Build** an event pipeline on Pub/Sub and Dataflow (Apache Beam) that lands clean partitioned tables in BigQuery and replays cleanly after an outage.
5. **Ship** a stateless Cloud Run service backed by Cloud SQL with Private Service Connect, fronted by an external HTTPS Load Balancer with Cloud Armor.
6. **Serve** a Vertex AI Endpoint for a real model (open weights from Model Garden or a Gemini API path) with autoscaling, request logging, and a documented fallback when the endpoint is down.
7. **Instrument** every service with OpenTelemetry, exporting to Cloud Trace, Cloud Logging, and Cloud Monitoring, with SLOs and burn-rate alerts that page on real risk, not noise.
8. **Lock down** a production project: organization policies, custom IAM roles, VPC Service Controls perimeter, Binary Authorization for the deploy path, and Secret Manager for every credential.
9. **Cost-engineer** a workload: read a billing export in BigQuery, identify the top three line items, apply committed-use discounts where they pay back, and use spot/preemptible nodes where appropriate.
10. **Run** an on-call drill: receive a synthetic page, diagnose with Cloud Logging and Cloud Trace, mitigate, write the postmortem, and adjust the alert that fired.
11. **Pass** the Google Professional Cloud Architect or Cloud DevOps Engineer certification readiness gate — practice exam scored, weak areas identified, plan to sit the test.
12. **Defend** every GCP decision in an architecture review: "We chose Spanner over CockroachDB self-hosted because…" with a real budget and a real exit plan.

---

## Prerequisites

**Required:**

- **C1** complete, or equivalent Python fluency at the level of building a 1000-line FastAPI service from scratch.
- **C15 Crunch DevOps** complete, or you can: write a multi-stage Dockerfile, write a Helm chart from scratch, write a Terraform module with `for_each` and a remote backend, configure GitHub Actions or GitLab CI for a multi-environment deploy.
- **C14 Crunch Linux** level Linux: comfortable in `journalctl`, `systemd` unit files, `iptables`/`nftables` basics, `tcpdump` reads.
- **Networking literacy:** you can explain TCP three-way handshake, TLS termination, the difference between L4 and L7 load balancers, what a NAT gateway does, and CIDR math.
- **One credit card.** Labs run inside the GCP \$300 free trial / always-free tier wherever possible, but a few exercises (Spanner regional, multi-region Dataflow) cost a few dollars total. Budget \$30–50 for the full 15 weeks beyond the trial.

**Helpful but not required:**

- Prior exposure to any cloud (AWS, Azure, DigitalOcean). The platform-engineering muscles transfer; the vocabulary doesn't.
- Reading-knowledge of Go. Several GCP-native tools (Kubernetes, Terraform, Skaffold, kpt) are Go projects and you'll occasionally read their source.

---

## Program at a glance

| Phase | Weeks | Theme | Outcome |
|---|---|---|---|
| **Phase 1 — Foundations** | 01–04 | Projects, IAM, networking, billing, Terraform | A locked-down landing zone you can hand to a junior engineer without flinching. |
| **Phase 2 — Compute & Networking** | 05–08 | GKE, Cloud Run, Cloud Functions, LBs, Cloud Armor | A multi-tier service architecture that survives an AZ loss. |
| **Phase 3 — Data & AI** | 09–12 | BigQuery, Pub/Sub, Dataflow, Spanner, Vertex AI | An event-to-insight pipeline with a model-serving path. |
| **Phase 4 — Production & Capstone** | 13–15 | Observability, security, FinOps, on-call, capstone | The capstone shipped, on-called, postmortemed. |

Full week-by-week plan in [`SYLLABUS.md`](SYLLABUS.md). Track rationale in [`CHARTER.md`](CHARTER.md).

---

## Weekly cadence

Same 36 hr/week rhythm as the rest of Crunch Labs. The cadence is non-negotiable; the depth is what makes this Labs and not a survey.

| Block | Hours/week | What you do |
|---|---|---|
| Lectures | 6 | 2–3 markdown lectures per week. Every code block runnable. Cite primary sources (GCP docs, Kubernetes docs, RFCs). |
| Exercises | 6 | 3+ small tasks with starter Terraform / scripts and a `SOLUTIONS.md`. Skill drills, not capstone work. |
| Challenges | 4 | 2 stretch problems. No solution provided; acceptance criteria only. |
| Quiz | 1 | 10 questions, answer key at the bottom. Closes the week. |
| Homework | 6 | 5–6 problems with rubric and time estimates. Graded against the rubric. |
| Mini-project | 8 | One concrete, specific, deployable mini-system per week. See SYLLABUS. |
| Self-study | 5 | Read the linked primary sources. Office hours. Architecture review of someone else's mini-project. |

---

## Cost expectations & free-tier guidance

This is the most important section in the README. Read it before week one.

- **All weekly labs run inside the GCP \$300 free trial and the always-free tier.** New trial accounts get \$300 in credit valid for 90 days; for a 15-week course this covers everything if you tear down nightly.
- **Spot / preemptible nodes everywhere they fit.** GKE node pools, Dataflow workers, and Dataproc clusters are all configured for spot by default. This drops cost by ~60–80%.
- **Region pinning.** Default region for the course is `us-central1` (or your nearest free-trial region). Multi-region exercises explicitly opt-in.
- **Spanner is the expensive one.** The Spanner labs (Week 11) use the smallest regional instance and run for under an hour with billing alerts armed. Budget ~\$5 for the week.
- **Multi-region Dataflow (Week 09) and the capstone failover drill (Week 14)** are the other paid-but-cheap exercises. Total course out-of-pocket beyond the trial: \$30–50 if you follow teardown discipline.
- **Billing budgets are exercise #1 of Week 01.** You set a hard cap before you provision anything. If you skip it, the course will eventually punish you.
- **Teardown gates every week.** Every mini-project has an explicit `terraform destroy` / `gcloud projects delete` step. Treat skipping it as failing the week.

If you cannot put a credit card on file at all, the course is still partially completable: you can run Terraform `plan`, study the syllabus, and use the GCP Skills Boost free labs as substitutes for the live deploys. You won't earn the capstone certificate this way, but the reading-group track exists.

---

## Recommended pre/post tracks

**Before C18:**

- **C1** (Convos · Python) — required.
- **C15 Crunch DevOps** — required. C18 picks up where C15 left off.
- **C14 Crunch Linux** — strongly recommended.
- **C16 Crunch Pro — Web Backend** — helpful for the services you'll deploy.

**After C18:**

- **C22 Crunch Mesh** — the natural sequel. Take what you built on GKE and grow it into a real multi-service mesh with gRPC, Kafka, and Istio at scale.
- **C19 Crunch AWS** — sibling cloud. After C18 you can do C19 in ~10 weeks rather than 15; the platform-engineering muscles transfer directly.
- **C23 Crunch Agents** — if you want to wire a real LLM agent into the GCP platform you just learned.

The intended pathway from the [Crunch Labs Charter](../CRUNCH-LABS-CHARTER.md): **C1 → C15 → C18 → C22.** That sequence lands you at senior cloud platform engineer / staff SRE in about 18 months of focused work post-C1.

---

## What this course is NOT

- **Not a Google PCA cram course.** The cert is a side-effect, not the goal. You'll be ready to sit it after Week 13 but the course doesn't teach to the exam.
- **Not "GCP is best."** We choose GCP services where they're genuinely best-in-class (BigQuery, Spanner, Pub/Sub at scale, Vertex AI's Model Garden). We name the open-source alternative every time (Trino + Iceberg, CockroachDB, NATS/Kafka, vLLM / TGI / Hugging Face).
- **Not vendor lock-in.** Every architecture in the course has a documented "exit plan" — what it would take to lift this workload to AWS, Azure, or self-hosted. If you can't write the exit plan you don't understand the workload.
- **Not click-ops.** Almost nothing is done in the Cloud Console after Week 02. Terraform first, `gcloud` second, console only to inspect.

---

## Tools we use

- **CLI:** `gcloud`, `bq`, `gsutil`, `kubectl`, `helm`, `kustomize`, `skaffold`, `terraform` (or `tofu`).
- **Languages:** Python 3.11+ for services and Beam pipelines, Go for the occasional sidecar, HCL for Terraform, YAML for Kubernetes, SQL for BigQuery.
- **Observability:** OpenTelemetry SDKs (Python + Go), Cloud Trace, Cloud Logging, Cloud Monitoring, Grafana for cross-cloud dashboards.
- **IaC:** Terraform with `google` and `google-beta`, Config Connector for in-cluster GCP resources, Cloud Foundation Toolkit for landing-zone modules.
- **Local dev:** `minikube` or `kind` for week-one Kubernetes, then GKE for everything from week five forward.
- **Editors:** any. The course assumes a Unix-ish terminal.

---

## How to start

1. Read this README in full.
2. Read [`CHARTER.md`](CHARTER.md) to understand *why* the topics are ordered the way they are.
3. Read [`SYLLABUS.md`](SYLLABUS.md) end-to-end. Do not skip ahead; the week ordering matters.
4. Create a fresh GCP free-trial account and a dedicated billing account for the course.
5. Open Week 01. Set your billing budget alerts as the first exercise. Then begin.

---

## License

GPL-3.0. See [`LICENSE`](LICENSE). Fork it, adapt it, teach it locally. If you improve a week, PR back. We read every PR.

## Maintainers

Code Crunch Club curriculum council. Track owner rotates per cohort; current cohort owner is named in the per-week `README.md`. Open issues on the master curriculum repository for cross-track concerns; open issues here for per-week corrections.
