# Mini-Project — The Full Capstone Integration: Realtime Event Pipeline at Scale

> Assemble every prior week's compounding artifact — the landing zone, the shared VPC, the GKE cluster, the Cloud Run ingest service, the Pub/Sub + Dataflow pipeline, the BigQuery tables, the Spanner-backed gRPC service, the Vertex AI serving path, the OpenTelemetry instrumentation, the security perimeter, and the FinOps controls — into one multi-region system that stands up with a single `terraform apply`, sustains 100 RPS at p99 < 500ms, survives a region failover in under 5 minutes with zero data loss, and tears down cleanly with `terraform destroy`. Then deliver it: architecture diagram, 5-minute video, chaos-drill postmortem, a cost report under \$500/month, and a 2-page exit plan.

This is the capstone. It is not a new build; it is the **integration** of fourteen weeks of compounding work into one system you can stand up, prove, defend, and tear down on demand. By the SYLLABUS note, the mini-projects compound — by Week 10 you were extending Week 06's cluster, not starting fresh — and Week 15 is where the compounding pays off. If you kept your Terraform modular and your `destroy` clean every week, this week is assembly and proof. If you took shortcuts, this is where you pay for them.

**Estimated time:** ~12.5 hours of the week's schedule (Monday through Saturday mini-project blocks), on top of the exercises and the live review.

---

## What you assemble

You already have, from the prior weeks, a Terraform module library and a set of services. The mini-project wires them into one root module with two region instantiations and proves the whole thing works together.

### The modules you compose (from prior weeks)

- `org-bootstrap`, `vpc`, `iam-baseline` — Weeks 01–04. The landing zone and shared VPC.
- `gke-standard` — Week 06. The regional cluster with a spot node pool, Workload Identity, PDBs.
- `cloud-run-ingest` — Week 07. The stateless ingest service.
- `edge` — Week 08. The global HTTPS LB, Cloud CDN, Cloud Armor.
- `pubsub`, `dataflow` — Week 09. The topic, DLQ, and the Beam streaming pipeline.
- `bigquery` — Week 10. The partitioned-clustered dataset.
- `spanner`, `state-grpc` — Week 11. The database and the gRPC serving service.
- `vertex-serving` — Week 12. The endpoint client with the Gemini fallback.
- `observability` — Week 13. The OTel collector config, SLOs, burn-rate alerts.
- `security`, `finops` — Week 14. Org Policy, VPC SC, Binary Authorization, Secret Manager, CMEK, billing export.

### The root module that ties them together

```
capstone/
├── terraform/
│   ├── main.tf            # composes every module; two region instantiations
│   ├── variables.tf       # primary_region, standby_region, project ids, budget
│   ├── regions.tf         # for_each over a regions map -> per-region resources
│   ├── edge.tf            # global LB, Cloud Armor, Cloud DNS failover policy
│   ├── data.tf            # BigQuery, Spanner, Pub/Sub (region-pinned)
│   ├── outputs.tf         # lb_ip, grpc_host, bq_dataset, dashboards_url
│   └── backend.tf         # GCS remote state with locking
├── services/
│   ├── ingest/            # Python FastAPI ingest service + Dockerfile (Week 07)
│   ├── state-grpc/        # Go gRPC service over Spanner (Week 11)
│   └── pipeline/          # Python Apache Beam streaming pipeline (Week 09)
├── diagram.md             # Mermaid architecture diagram
├── EXIT-PLAN.md           # the 2-page exit plan (Lecture 2)
├── POSTMORTEM.md          # chaos-drill postmortem (Exercise 2)
├── cost-report.md         # billing-export analysis (under $500/mo)
├── load-test.md           # the 100-RPS p99 writeup (Exercise 1)
└── README.md              # how to apply, prove, and destroy
```

The key Terraform pattern is the regions map driving `for_each`, so primary and standby are the *same* module with different parameters:

```hcl
# terraform/regions.tf
locals {
  regions = {
    primary = {
      region         = var.primary_region   # us-central1
      ingest_min     = 1                     # always-warm on the hot path
      ingest_max     = 10
    }
    standby = {
      region         = var.standby_region    # us-east1
      ingest_min     = 0                      # cold; failover tolerates warm-up
      ingest_max     = 10
    }
  }
}

module "ingest" {
  source   = "../modules/cloud-run-ingest"
  for_each = local.regions

  project        = var.project
  region         = each.value.region
  min_instances  = each.value.ingest_min
  max_instances  = each.value.ingest_max
  topic_id       = google_pubsub_topic.events.id
  image          = "${var.artifact_registry}/ingest:${var.image_tag}"
  service_account = module.iam.ingest_sa_email
}
```

And the edge backend service references both regional ingest services so the global LB fails over automatically when the primary backend's health check fails:

```hcl
# terraform/edge.tf (excerpt)
resource "google_compute_backend_service" "ingest" {
  name                  = "ingest-backend"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  health_checks         = [google_compute_health_check.ingest.id]

  dynamic "backend" {
    for_each = module.ingest
    content {
      group = google_compute_region_network_endpoint_group.ingest[backend.key].id
    }
  }

  security_policy = google_compute_security_policy.armor.id
  enable_cdn      = false  # CDN is on the static/asset path, not the POST ingest path
}
```

---

## The end-to-end data flow you must demonstrate

One event, traced through every hop. This is the trace-an-event walk from Lecture 1 §1.5, and it is what your 5-minute video shows:

1. **Edge.** `POST /v1/events` hits the global LB. Cloud Armor evaluates the rate-limit and WAF rules. The request lands on the healthy ingest backend (primary unless failed over).
2. **Ingest.** The Cloud Run service validates the payload, assigns/honors the idempotency key, and publishes to the Pub/Sub `events` topic with ordering key = tenant. Returns `202 Accepted` once the publish is durable.
3. **Stream.** Pub/Sub holds the message (7-day retention). Malformed messages route to the dead-letter topic.
4. **Process.** Dataflow pulls the message, applies an event-time window, enriches it from the Memorystore cache, and streams it into BigQuery (partitioned by event time, clustered by tenant). Exactly-once into BigQuery via the streaming dedup key.
5. **Serve — analytical.** Analysts query BigQuery with a partition filter, scanning <1% of the data.
6. **Serve — operational.** In parallel, the current-state counters are updated and the gRPC service reads them from Spanner (strongly consistent). The Vertex AI client scores events with a Gemini fallback when the endpoint is unhealthy.
7. **Observe.** Every hop emits an OpenTelemetry span sharing one trace ID. Cloud Trace shows the full waterfall.

---

## Rules

- **You may** reuse every module and service you wrote in Weeks 01–14. That is the point — this is integration, not a rewrite.
- **You may NOT** hand-create resources in the Console and leave them out of Terraform. The grader runs `terraform destroy`; anything created by hand leaks and fails the teardown gate.
- **Region pinning:** primary `us-central1`, standby `us-east1` (or your nearest free-trial regions). BigQuery dataset is regional with a scheduled snapshot copy. Spanner is regional in primary (multi-region is the stretch goal).
- **Spot everywhere it fits:** the GKE serving node pool and the Dataflow workers run on spot/preemptible by default.
- **No long-lived keys.** WIF for all CI deploys; Secret Manager for runtime credentials. `grep -ri "private_key\|BEGIN.*PRIVATE" .` must return nothing in the repo.
- **Teardown discipline:** run `terraform destroy` at the end of every working session this week. The Spanner instance and the GKE cluster are the expensive leaks.

---

## Acceptance criteria

The rubric maps each box to a deliverable. This is the same bar as `challenges/challenge-01`, restated for the build.

### Integration & deploy (25%)

- [ ] A single `terraform apply` from the `terraform/` directory stands up the entire system in both regions.
- [ ] `terraform apply` a second time shows `No changes` (idempotent).
- [ ] `terraform destroy` removes everything; `gcloud asset search-all-resources` confirms zero leaked resources afterward.
- [ ] The README documents the exact apply → prove → destroy sequence and a grader can follow it cold.

### Performance (15%)

- [ ] 100 RPS sustained for 30 minutes at p99 < 500ms, measured off the LB latency distribution (Exercise 1), with `load-test.md` and a chart.
- [ ] The Pub/Sub backlog stays flat under sustained load (the pipeline keeps up).

### Resilience (20%)

- [ ] A region failover completes in < 5 minutes with zero data loss, driven by `exercise-02-chaos-drill.py` (or by hand) and documented in `POSTMORTEM.md`.
- [ ] The DLQ subscription depth is unchanged across the failover and the backlog drains afterward.

### Observability (15%)

- [ ] Every service emits OTel traces, metrics, and logs to Cloud Trace + Monitoring + Logging.
- [ ] At least one armed burn-rate alert per user-facing service; the failover drill makes one fire.
- [ ] You can produce a single cross-service trace for one event on demand.

### Security & cost (15%)

- [ ] No long-lived keys in the repo; WIF + Secret Manager only.
- [ ] The data project is inside a VPC SC perimeter; Binary Authorization gates the GKE deploy path; CMEK on BigQuery + Spanner.
- [ ] `cost-report.md` derives the monthly cost from the billing export, shows it is under \$500/mo, and names three optimization moves with an annualized estimate.

### Delivery (10%)

- [ ] `diagram.md` — one-page Mermaid architecture diagram, every arrow labeled.
- [ ] A 5-minute video walkthrough (link in the README) tracing one event end to end.
- [ ] `EXIT-PLAN.md` — the 2-page exit plan from Lecture 2.
- [ ] The live architecture review delivered (Friday slot).

---

## Suggested order of work

- **Monday.** Compose the root module. Get `terraform apply` to stand up *primary region only*, end to end, and trace one event by hand. Get `terraform destroy` clean. Do not move on until both directions work in one region.
- **Tuesday.** Add the standby region via the regions `for_each`. Run Exercise 1 (100 RPS / 30 min) against primary and fix whatever fails the p99 bar (usually Cloud Run max-instances or the publish path).
- **Wednesday.** Run the failover chaos drill (Exercise 2). Measure recovery time; tune the standby warm-up and the LB health-check interval until you are under 5 minutes with zero data loss. Write `POSTMORTEM.md`.
- **Thursday.** Write `EXIT-PLAN.md` (Lecture 2) and `cost-report.md` from the billing export. Sit the practice exam (Exercise 3) and clear the gate.
- **Friday.** Record the 5-minute video. Deliver the live architecture review. Capture the risk list.
- **Saturday.** Mock interview, portfolio polish, and a final clean `apply` → prove → `destroy` cycle as the grader will run it.

---

## What "done" looks like

A grader clones your repo, reads the README, runs `terraform apply`, watches your dashboard show 100 RPS at p99 < 500ms, kills your primary region and watches the standby take over inside 5 minutes with an empty DLQ, opens one trace that spans the whole system, reads your cost report and confirms it is under \$500/month, reads your two-page exit plan and finds it honest, then runs `terraform destroy` and confirms zero resources remain. Every one of those steps passes without you touching the keyboard to fix something. That is the capstone. That is C18.
