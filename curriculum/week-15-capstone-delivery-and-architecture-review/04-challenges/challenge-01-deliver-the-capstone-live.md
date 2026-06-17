# Challenge 1 — Deliver the Realtime Event Pipeline at Scale, live

> **Estimated time:** the capstone (the bulk of the week's 12.5 mini-project hours, plus the Friday delivery slot). **This is the assessed capstone.** No solution is provided — only acceptance criteria, because in production nobody hands you the answer key.

You will deliver the **Realtime Event Pipeline at Scale** — the multi-region edge → ingest → stream → process → serve system you have been compounding since Week 01 — **live, in your own GCP project**, end to end. "Live" is the operative word. The grader does not read your diagram and award points. The grader clones your repo, runs `terraform apply`, drives traffic at it, breaks it, reads your dashboards, and runs `terraform destroy`. If any of those steps fails, the capstone does not pass, regardless of how good the writeup is.

This challenge is harder than the mini-project brief in two specific ways: (1) it must withstand a **live region failover within 5 minutes with zero data loss**, executed in front of the grader, and (2) it must **tear down cleanly on demand** — the grader runs `terraform destroy` and confirms zero resources and zero billing tail.

## The system

The full architecture from `SYLLABUS.md` (and the mini-project brief), assembled:

- **Edge:** Global external HTTPS LB → Cloud CDN → Cloud Armor (rate-limit + a preconfigured WAF rule + one custom CEL rule). Cloud DNS with health-checked failover.
- **Ingest:** Cloud Run, stateless, autoscaled, `min-instances=1` in primary and `=0` in standby, validating and publishing to Pub/Sub.
- **Stream:** Pub/Sub topic with a dead-letter topic, per-tenant ordering keys, 7-day retention.
- **Process:** Dataflow streaming (Python Apache Beam) — window, enrich from a Memorystore cache, write to BigQuery (partitioned by event time, clustered by tenant).
- **Serve:** GKE Standard (regional, spot node pool) running (a) a current-state gRPC service on Spanner and (b) a Vertex AI Endpoint client with a Gemini API fallback.
- **Observability:** OpenTelemetry traces/metrics/logs everywhere → Cloud Trace + Monitoring + Logging. One SLO per service. Burn-rate alerts armed.
- **Security:** WIF for all deploys, VPC SC around the data project, Binary Authorization on the GKE path, Secret Manager for every credential, CMEK on BigQuery + Spanner.

## Acceptance criteria (the grader runs every one of these)

### Live performance

- [ ] **100 RPS sustained for 30 minutes at p99 < 500ms end-to-end**, measured off `loadbalancing.googleapis.com/https/total_latencies` (Exercise 1). The grader watches the dashboard.
- [ ] The system reaches steady state within 2 minutes of `terraform apply` completing (the always-warm primary instance is up).

### Live failover

- [ ] **Region failover completes within 5 minutes with zero data loss.** The grader kills the primary region's ingest (or you drive it with `exercise-02-chaos-drill.py region-failover`), and the standby takes over. The Pub/Sub backlog drains and the dead-letter subscription depth is unchanged from before the fault.
- [ ] The failover is *observable*: a burn-rate alert fires, the failover is visible on the dashboard, and a trace from after the failover shows the request served by the standby region.

### Observability

- [ ] **Every service emits OpenTelemetry** traces, metrics, and logs. The grader picks one event and you produce its cross-service trace from the LB through Spanner (Lecture 1, §1.5).
- [ ] **At least one armed burn-rate alert per user-facing service.** The grader inspects the alerting policies; "defined but disabled" does not count.

### Teardown

- [ ] **`terraform destroy` cleanly tears the entire system down.** Zero resources remaining. The grader runs it and then runs `gcloud asset search-all-resources` (or equivalent) to confirm nothing leaked — especially the Spanner instance, the GKE cluster, and any reserved IPs or persistent disks.
- [ ] `terraform apply` is **idempotent**: applying twice with no changes shows `No changes`.

### Cost

- [ ] **Total monthly cost at 100 RPS is documented and under \$500/month at list price**, with the number derived from the billing export (not guessed).

### Delivery artifacts

- [ ] **Architecture diagram** (Mermaid or PNG) in the repo, one page, every arrow labeled.
- [ ] **5-minute video walkthrough** of the architecture and one trace through the system.
- [ ] **Chaos-drill postmortem** for the failover (or another drill), using the `POSTMORTEM.md` skeleton from Exercise 2.
- [ ] **Cost report** from the billing export with three optimization moves and an annualized estimate.
- [ ] **2-page exit plan** (Lecture 2), honest about the engineer-weeks to leave GCP.
- [ ] **Live architecture review delivered** (Friday slot): you present, you trace an event, you answer the staff-engineer questions, you produce the risk list.

## How you are graded

This challenge maps to the **Capstone delivery (25%)** line of the assessment matrix, plus the **Mock interview (5%)** and **PCA readiness gate (5%)**. The single hardest gate is teardown: a system you cannot `apply` and `destroy` on demand is not a system you operate, and it does not pass. Build the `destroy` discipline in from day one — run `terraform destroy` at the end of every working session this week. The grader will, and a leaked Spanner instance over a weekend is both a cost surprise and an automatic fail.

## What "open-ended" means here

There is no single right architecture. Within the spec, you make and defend choices: regional vs multi-region Spanner, the failover mechanism (LB health check vs Cloud DNS routing policy), the Dataflow autoscaling bounds, the GKE node-pool sizing, the Cloud Armor rule set. The challenge is not to match a reference solution; it is to make defensible choices, prove them under load and chaos, and explain the tradeoffs in the review. The exit plan and the self-named risks (Lecture 1, §1.8) are where you demonstrate that you understand the choices you made — which is, in the end, the entire point of the course.
