# C18 · Crunch GCP — Syllabus

**Track:** C18 · Crunch GCP — Google Cloud Engineering
**Tier:** Crunch Labs (production-grade)
**Length:** 15 weeks intensive · ~36 hrs/week · ~540 hours total
**Prerequisite:** C1 + (C15 Crunch DevOps or equivalent) + C14-level Linux
**Capstone:** Realtime Event Pipeline at Scale (one substantial system, multi-region)
**License:** GPL-3.0
**Sub-brand accent:** `#4285F4` (sky)

The syllabus below is the full week-by-week plan. Every week ships the seven-artifact Crunch Labs deliverable: `README.md`, `resources.md`, `lecture-notes/`, `exercises/`, `challenges/`, `quiz.md`, `homework.md`, `mini-project/`. The mini-projects compound: by Week 10 you are extending Week 06's GKE cluster, not starting fresh.

---

## Phase 1 — Foundations (Weeks 01–04)

You cannot operate GCP until you can read the IAM model and the VPC model in your sleep. This phase is unglamorous and load-bearing. We do not deploy a single workload until Week 05.

### Week 01 — The GCP resource hierarchy & billing discipline

- **Topics:** Organization, folders, projects, billing accounts; resource hierarchy as a security model; quota model; the seven `gcloud` muscle-memory commands.
- **Lecture:** Why GCP's project boundary is a stronger isolation primitive than AWS accounts in some ways and weaker in others. The billing-account-to-project relationship and how it routes alerts.
- **Hands-on lab:** *Provision a three-folder, five-project landing zone with Terraform.* Folders: `bootstrap/`, `shared/`, `workloads/`. Billing budgets armed before any compute is created.
- **Skills earned:**
  - Map a real org chart to a folder/project tree without painting yourself into a corner.
  - Configure billing budget alerts that page Slack before they page your CTO.
  - Use `gcloud config configurations` like a sane person.

### Week 02 — IAM, service accounts, and Workload Identity

- **Topics:** Principals (users, groups, SAs, federated identities); roles (basic, predefined, custom); conditions; service-account impersonation; Workload Identity Federation (no more keyfiles).
- **Lecture:** The five IAM mistakes that own production incidents: over-broad `roles/owner`, key-file sprawl, missing audit logs, no separation of break-glass, and `iam.serviceAccountUser` confusion.
- **Hands-on lab:** *Replace a service-account key file with Workload Identity Federation from GitHub Actions.* End state: zero long-lived keys in the repo, OIDC-only deploys.
- **Skills earned:**
  - Write a custom IAM role with the minimum permission set for a real job function.
  - Configure WIF for GitHub Actions, GitLab CI, and a non-GCP Kubernetes cluster.
  - Audit a project with `gcloud asset` + Policy Analyzer and find the over-privileged SA.

### Week 03 — VPC, subnets, routes, and Cloud NAT

- **Topics:** VPC topology, primary/secondary subnet ranges, shared VPC, routes, firewall rules (legacy + hierarchical), Cloud NAT, Cloud Router, Private Google Access.
- **Lecture:** Why GCP's global VPC is fundamentally different from AWS's regional VPC, and why that matters for cross-region service-to-service traffic. When to use a shared VPC vs. peering vs. Network Connectivity Center.
- **Hands-on lab:** *Build a multi-region shared VPC with three subnets, Cloud NAT for egress, Private Google Access for `*.googleapis.com`, and a hierarchical firewall policy.* Validate with traceroute and BGP route inspection.
- **Skills earned:**
  - Read and write VPC firewall rules without locking yourself out.
  - Diagnose "why can't my GKE pod reach BigQuery" — Private Google Access vs. Private Service Connect.
  - Choose between hierarchical firewall policies and per-VPC rules with reason.

### Week 04 — Terraform for GCP, end-to-end

- **Topics:** `terraform` (or `tofu`) on the `google` and `google-beta` providers; module structure; remote state in GCS with locking; `terragrunt` for environments; `for_each` and `count` patterns; the Cloud Foundation Toolkit modules.
- **Lecture:** Why "click in console, then write Terraform" is acceptable in week one and a fireable offense by week six. Drift detection, plan-review workflow, and the policies that keep IaC honest.
- **Hands-on lab:** *Refactor weeks 01–03 deliverables into a reusable Terraform module library.* Output: a `modules/` folder with `org-bootstrap`, `vpc`, `iam-baseline` modules consumed by `envs/dev`, `envs/prod`.
- **Skills earned:**
  - Structure a Terraform repo for an organization with 10 projects, not one.
  - Use Config Connector and Cloud Foundation Toolkit where they beat raw HCL.
  - Wire a Terraform plan into a Cloud Build PR check.

---

## Phase 2 — Compute & Networking (Weeks 05–08)

Now you deploy. Each week of this phase adds one compute primitive and one networking primitive. By the end you can defend the choice of GKE over Cloud Run for any workload.

### Week 05 — Compute Engine, instance groups, and managed VMs

- **Topics:** GCE instance types, machine families (E2/N2/N2D/C3/T2D); MIGs (regional + zonal); instance templates; OS Login; Shielded VM; spot/preemptible.
- **Lecture:** When VMs are still the right answer in 2026 — legacy stateful workloads, GPU-heavy batch jobs, sovereignty constraints. The cost of choosing containers when a VM was the right tool.
- **Hands-on lab:** *Deploy a regional MIG behind an internal TCP load balancer running a Go HTTP service.* Configure autoscaling on CPU + custom metric, validate failover by killing instances.
- **Skills earned:**
  - Choose a machine family for a workload and defend it on price-performance.
  - Configure a regional MIG with rolling updates that don't drop traffic.
  - Use spot VMs without surprising your weekend self.

### Week 06 — GKE Autopilot vs. Standard

- **Topics:** Cluster architecture (control plane, node pools); Autopilot constraints; Standard with private endpoint; Workload Identity in-cluster; PodDisruptionBudgets, HPA, VPA; cluster upgrades & surge config.
- **Lecture:** When Autopilot's constraints save you money and when they cost you a feature you needed. The four GKE upgrade strategies and what each costs in availability.
- **Hands-on lab:** *Deploy the same Python FastAPI service to (a) Autopilot and (b) Standard with a spot node pool.* Configure Workload Identity, an HPA on RPS via a custom metric, and a PDB. Measure cold-start, scale-out, and cost.
- **Skills earned:**
  - Defend Autopilot vs. Standard for a real workload, with a cost number.
  - Run an in-place GKE minor-version upgrade without paging anyone.
  - Wire Workload Identity end-to-end so pods read GCS without keyfiles.

### Week 07 — Cloud Run, Cloud Functions, and the serverless decision

- **Topics:** Cloud Run (v2) services and jobs; concurrency, min-instances, CPU allocation; Cloud Run + Cloud SQL via Private Service Connect; Cloud Functions (gen2) on Cloud Run; Eventarc.
- **Lecture:** The serverless cost curve: where Cloud Run beats GKE, where GKE beats Cloud Run, and the "min-instances=1 pays for itself" threshold.
- **Hands-on lab:** *Deploy a stateless Cloud Run service with a Cloud SQL Postgres backend over Private Service Connect, behind Cloud Armor.* Benchmark cold-start at `min-instances=0`, then `=1`, then `=3`. Compare monthly cost.
- **Skills earned:**
  - Decide GKE vs. Cloud Run on hard numbers, not on taste.
  - Wire Cloud Run to a private Cloud SQL instance without exposing it publicly.
  - Use Eventarc to trigger a Cloud Run job from a GCS write.

### Week 08 — Cloud Load Balancing & Cloud Armor

- **Topics:** External HTTPS LB (global), regional internal HTTPS LB, TCP/SSL Proxy LB, Network LB; backend services and NEGs; Cloud CDN; Cloud Armor (WAF rules, rate limiting, bot management); IAP for app-level zero-trust; Private Service Connect.
- **Lecture:** The five-layer GCP edge: DNS → Cloud Armor → Cloud CDN → LB → backend. What each layer protects and what each layer cannot.
- **Hands-on lab:** *Front the Cloud Run service from Week 07 with a global HTTPS LB, attach Cloud CDN, add a Cloud Armor rule that rate-limits per-IP, and add a preconfigured WAF rule for SQLi.* Validate with `hey` and a deliberately malformed request.
- **Skills earned:**
  - Build a global L7 LB with multiple backends (Cloud Run + GKE + GCS bucket).
  - Write a Cloud Armor rule in Common Expression Language that blocks a real abuse pattern.
  - Configure Identity-Aware Proxy in front of an internal app.

---

## Phase 3 — Data & AI (Weeks 09–12)

Compute moves bytes; data tells the truth. This phase is where GCP is genuinely best-in-class — BigQuery, Spanner, Pub/Sub at scale — and we use it without falling in love with it.

### Week 09 — Pub/Sub and Dataflow (Apache Beam)

- **Topics:** Pub/Sub topics, subscriptions (push/pull), ordering keys, dead-letter topics, exactly-once delivery; Dataflow as managed Apache Beam; streaming vs. batch; windowing, watermarks, triggers; Dataflow Prime.
- **Lecture:** Pub/Sub vs. Kafka vs. NATS vs. SQS: when each wins. Watermarks, late data, and why your event pipeline shipped wrong numbers for six months before anyone noticed.
- **Hands-on lab:** *Build a streaming pipeline: synthetic event generator → Pub/Sub → Dataflow (Python Beam) → BigQuery, with a dead-letter topic for malformed events.* Run the pipeline for 30 minutes, kill workers mid-stream, validate exactly-once.
- **Skills earned:**
  - Write an Apache Beam pipeline in Python with proper windowing.
  - Configure a Pub/Sub dead-letter topic and an alert that fires when it accumulates.
  - Decide push vs. pull subscription for a real consumer pattern.

### Week 10 — BigQuery deep

- **Topics:** Storage model (capacitor, columnar); partitioning (time, integer-range); clustering; BI Engine; materialized views; BigQuery ML; INFORMATION_SCHEMA; slot reservations vs. on-demand; query plan reading.
- **Lecture:** BigQuery's pricing model is the failure mode. The three queries that cost \$2000 by accident. Reading the query plan. The "scan less" mental discipline.
- **Hands-on lab:** *Land a public dataset (NYC taxi or Wikipedia pageviews) into a partitioned-clustered table, then write five queries that scan <1% of the data.* Compare on-demand cost vs. a 100-slot reservation for a 1-hour batch window.
- **Skills earned:**
  - Choose partition + cluster keys for a real query workload.
  - Read a BigQuery query plan and find the stage that costs the money.
  - Write a BQML logistic-regression model on a real dataset and predict.

### Week 11 — Spanner, Cloud SQL, AlloyDB, and the database decision

- **Topics:** Cloud SQL (Postgres/MySQL) HA; read replicas; PSC for private connectivity; AlloyDB columnar engine and Postgres compatibility; Spanner architecture (Paxos, TrueTime); Firestore vs. Bigtable; Memorystore for Redis/Valkey.
- **Lecture:** Spanner is not "managed Postgres at scale." When the cost is justified (multi-region strong consistency, horizontal write scale); when it isn't (you'd be fine with AlloyDB or self-hosted Postgres). The CockroachDB / Yugabyte comparison.
- **Hands-on lab:** *Migrate a Cloud SQL Postgres database to a single-region Spanner instance using Datastream + Dataflow.* Validate with a parallel read shadow-test for 30 minutes. Tear down the Spanner instance before bed.
- **Skills earned:**
  - Choose Cloud SQL, AlloyDB, or Spanner with a budget and a justification.
  - Configure Cloud SQL HA + PSC + a read replica without leaving the private network.
  - Run a zero-downtime Postgres-to-Spanner migration with Datastream.

### Week 12 — Vertex AI, Model Garden, and serving inference

- **Topics:** Vertex AI Workbench, Pipelines (Kubeflow), Training (custom containers), Endpoints (online + batch), Model Garden (open weights); Gemini API for closed-weights; Document AI; BigQuery ML continuity.
- **Lecture:** The build-vs-call decision: when to serve your own model on a Vertex AI Endpoint vs. call Gemini API vs. self-host with vLLM / TGI on GKE. The price/latency/sovereignty triangle.
- **Hands-on lab:** *Deploy an open-weights model from Model Garden to a Vertex AI Endpoint with GPU autoscaling, and write a fallback path that calls Gemini API when the endpoint is unhealthy.* Benchmark p50/p99 latency and per-1000-token cost against vLLM on GKE.
- **Skills earned:**
  - Serve a Hugging Face model on Vertex AI with proper autoscaling.
  - Wire a real fallback (with circuit breaker) between two model providers.
  - Cost-compare a managed endpoint against vLLM on a GKE spot pool.

---

## Phase 4 — Production & Capstone (Weeks 13–15)

You have all the primitives. Phase 4 is what turns a working system into a production-grade one.

### Week 13 — Observability with OpenTelemetry

- **Topics:** OpenTelemetry SDKs (Python + Go) for traces, metrics, logs; Cloud Trace, Cloud Logging, Cloud Monitoring; log routing & sinks (BigQuery, Pub/Sub, GCS); SLO definitions; burn-rate alerts; Cloud Profiler.
- **Lecture:** The alert hygiene rule: page only on user-visible risk. Symptoms vs. causes. The four golden signals re-stated in GCP terms.
- **Hands-on lab:** *Instrument every service from Weeks 06–12 with OpenTelemetry, export to Cloud Trace + Cloud Logging + Cloud Monitoring, and define one SLO per service with a multi-window burn-rate alert.* Validate by injecting a 1% error rate and watching the page.
- **Skills earned:**
  - Add OTel instrumentation to a Python/Go service in under an hour.
  - Define an SLO and the burn-rate alert that protects it without paging on noise.
  - Route logs to a BigQuery sink and query them.

### Week 14 — Security hardening, FinOps, and the on-call drill

- **Topics:** Organization Policy constraints; VPC Service Controls; KMS + CMEK; Secret Manager; Binary Authorization; Security Command Center Premium; commitments and sustained-use discounts; spot capacity; billing-export-to-BigQuery analysis; on-call rotation design.
- **Lecture:** The five security defaults you must change on day one of any new GCP org. The three FinOps moves that pay back inside one quarter.
- **Hands-on lab:** *Apply an Organization Policy bundle, wrap the production project in a VPC SC perimeter, require Binary Authorization for the GKE deploy path, and run a synthetic on-call drill.* Deliverable: signed-off runbook + postmortem.
- **Skills earned:**
  - Configure VPC Service Controls without breaking your own deploys.
  - Set up Binary Authorization with an attestor signed by Cloud Build.
  - Run a no-drama on-call shift end-to-end: page, triage, mitigate, postmortem.

### Week 15 — Capstone delivery and architecture review

- **Topics:** Final integration; architecture review presentation; recorded video walkthrough; resume/portfolio polish; PCA / Cloud DevOps Engineer practice exam; mock interview.
- **Lecture:** How a real architecture review runs — the questions a staff engineer will ask. The "exit plan" requirement: defend the cost of moving this workload off GCP.
- **Hands-on lab:** *Capstone delivery week.* See capstone spec below.
- **Skills earned:**
  - Present and defend a production architecture in front of peers.
  - Write an exit plan that is honest about lock-in.
  - Sit a Google PCA practice exam at passing score.

---

## Assessment matrix

| Instrument | Cadence | Weight | What it measures |
|---|---|---|---|
| Weekly quiz (10 Q) | Weeks 01–14 | 10% | Coverage of the week's lecture material. |
| Weekly homework (5–6 problems) | Weeks 01–14 | 15% | Application of the week's concepts beyond the lab. |
| Weekly mini-project | Weeks 01–14 | 25% | Deployable per-week artifact, graded against the rubric. |
| Midterm architecture review | End of Week 08 | 10% | 5-page writeup of Phase 1+2 system with cost model and exit plan. Peer-reviewed. |
| Capstone delivery | Week 15 | 25% | The system, live. See spec below. |
| On-call drill | Week 14 | 5% | Synthetic page → triage → mitigation → postmortem. Graded on the postmortem quality. |
| Mock interview | Week 15 | 5% | One system-design + one GCP-specific deep-dive interview with a peer or cohort lead. |
| PCA / Cloud DevOps Engineer practice exam | Week 13 + Week 15 | 5% | Diagnostic on Week 13; readiness gate on Week 15 (>=70% to clear). |

A passing grade requires >=70% overall *and* a capstone that runs end-to-end on demand.

---

## Capstone — Realtime Event Pipeline at Scale

> Architect, build, deploy, and on-call a multi-region realtime event pipeline on GCP. Tear it down on demand. Defend every decision.

### Architecture (description)

A diagram that the candidate produces and defends:

- **Edge:** Global external HTTPS LB → Cloud CDN → Cloud Armor (rate-limit + WAF preconfigured rules + a custom CEL rule). DNS via Cloud DNS with health-checked failover.
- **Ingest:** Cloud Run service (stateless, autoscaled, min-instances=1 in primary region, min-instances=0 in standby region) that validates and publishes events to Pub/Sub.
- **Stream:** Pub/Sub topic with a dead-letter topic, ordering keys per tenant, and a 7-day retention.
- **Process:** Dataflow streaming pipeline (Python Apache Beam) that windows, enriches with a Memorystore-cached lookup, and writes to BigQuery (partitioned by event time, clustered by tenant).
- **Serve:** GKE Standard cluster (regional, with a spot node pool) running two services: (a) a "current state" gRPC service backed by Spanner regional, (b) a Vertex AI Endpoint client that calls a Model Garden open-weights model with a Gemini API fallback.
- **Observability:** Every service emits OpenTelemetry traces, metrics, and logs to Cloud Trace + Cloud Monitoring + Cloud Logging. One SLO per service. Burn-rate alerts armed.
- **Security:** Workload Identity Federation for all deploys. VPC Service Controls perimeter around the data project. Binary Authorization on the GKE deploy path. Secret Manager for every credential. CMEK on BigQuery + Spanner.
- **Multi-region:** Primary in `us-central1`, secondary in `us-east1`. BigQuery dataset is regional with a scheduled snapshot copy. Spanner is regional in primary (multi-region as a paid stretch goal). GCS dual-region for the artifact bucket.

### Deliverables

1. **Live deploy** in your own GCP project. Reachable URL or signed-URL demo path. The grader will hit it.
2. **Architecture diagram** (Mermaid or PNG) in the repo.
3. **5-minute video walkthrough** of the architecture and one trace through the system.
4. **Postmortem of one chaos drill.** Pick one and execute:
   - **Region failover.** Kill the primary region's Cloud Run; validate that the standby takes over within SLO.
   - **Certificate rotation.** Rotate the TLS cert on the global LB live; document time-to-rotate and any user-visible blip.
   - **Pub/Sub overload.** Push 10× normal traffic and document where the system bends (DLQ accumulates, Dataflow lag grows, alerts fire) and how you would absorb it permanently.
5. **Cost report.** Billing-export-to-BigQuery analysis of capstone-week spend, with three identified optimization moves and an estimated annualized cost.
6. **Exit plan.** A 2-page document describing what it would take to move this workload to AWS or to self-hosted Kubernetes + Kafka + Trino + Iceberg + vLLM. Honest about effort.

### Acceptance criteria

- The system handles 100 RPS sustained for 30 minutes with p99 < 500ms end-to-end.
- A region failover completes within 5 minutes with zero data loss (Pub/Sub backlog drains; dead-letter is empty at steady state).
- All services emit OpenTelemetry data and have at least one armed burn-rate alert.
- Terraform `terraform destroy` cleanly tears the entire system down. The grader will run it.
- Total monthly cost of the running system (at 100 RPS) is documented and under \$500/month at list price.

---

## Career engineering pack

### Interview prep

- **Cert track:** Google Professional Cloud Architect *and* Professional Cloud DevOps Engineer. Practice exams are run in Week 13 (diagnostic) and Week 15 (readiness gate). The course covers ~90% of the PCA blueprint and ~85% of the Cloud DevOps Engineer blueprint.
- **System design at GCP-shaped companies:** four practice rounds in the `interview-prep/` folder, each modeled on real GCP-using companies (Spotify, Snap, Cloudflare, Shopify): "design a streaming analytics platform on GCP," "design a multi-region key-value store with strong consistency," "design an ML serving platform," "design a global edge with bot protection."
- **GCP technical deep-dives:** four drills — IAM debug, VPC debug, GKE debug, BigQuery query-plan debug — modeled on Google L4/L5 phone screens.

### Production runbook

`production-runbook.md` ships with the capstone and covers what an on-call shift on the capstone system actually looks like:

- The five pager pages you should expect on a normal week and the runbook for each.
- The alert hygiene rules: which alerts page, which file a ticket, which go to Slack only.
- Error budgets per service, with the action triggered when each is consumed.
- Escalation paths and the on-call handoff template.
- The "no-blame postmortem" template the cohort uses, with one fully-worked example from the Week 14 drill.

### Portfolio recommendations

Three artifacts from C18 belong on your portfolio:

1. **The capstone** — repo + live link + 5-min video. This is the headline piece.
2. **The Week 04 Terraform module library** — clean, reusable, documented HCL is a hiring signal in itself.
3. **The Week 13 observability writeup** — "how I instrumented service X with OpenTelemetry and what the burn-rate alert caught" is a strong blog post that recruiters will actually read.

Polished portfolio templates live in `portfolio.md`.

---

## License

GPL-3.0. See [`LICENSE`](LICENSE).

---

*Crunch Labs · C18 Crunch GCP · curriculum council · 2026.*
