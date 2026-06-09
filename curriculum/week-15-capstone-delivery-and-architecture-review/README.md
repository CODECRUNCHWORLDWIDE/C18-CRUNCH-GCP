# Week 15 — Capstone Delivery and Architecture Review

Welcome to the last week of **C18 · Crunch GCP**. You do not learn a new GCP service this week. You ship.

Everything you have built since Week 01 — the landing zone, the shared VPC, the GKE cluster, the Cloud Run ingest service, the Pub/Sub + Dataflow pipeline, the BigQuery tables, the Spanner-backed gRPC service, the Vertex AI serving path, the OpenTelemetry instrumentation, the security perimeter, and the FinOps controls — gets assembled into one running system: the **Realtime Event Pipeline at Scale**, multi-region, in your own GCP project. Then you defend it.

"Defend it" is not a metaphor. This week you run a real architecture review: you stand in front of peers (or a cohort lead, or a recorded camera that a hiring manager will eventually watch), you walk a single event through the whole system, and you answer the questions a staff engineer asks when they are deciding whether to trust your design in production. You produce a 5-minute video, a chaos-drill postmortem, a billing-export cost report under \$500/month, and a 2-page **exit plan** that is honest about exactly how much it would cost to move this workload off GCP. And you sit the PCA / Cloud DevOps Engineer practice exam and clear the **>=70% readiness gate** — that is a hard gate, not a participation trophy.

The week has a rhythm: integrate and harden early, prove the SLOs with load and chaos drills mid-week, then deliver and defend at the end. If your Week 14 mini-project did not tear down cleanly with `terraform destroy`, fix that first — the grader runs `destroy` on your live project and a leaked Spanner instance is the difference between a pass and a \$200 surprise.

This is the week the course has been building toward. Treat it like a release.

## Learning objectives

By the end of this week, you will be able to:

- **Integrate** every prior-week artifact into one multi-region system that deploys from a single `terraform apply` and tears down with one `terraform destroy`.
- **Prove** an end-to-end SLO empirically: 100 RPS sustained for 30 minutes with p99 < 500ms, measured with a load generator and read off a real Cloud Monitoring dashboard.
- **Execute** a chaos drill — region failover, certificate rotation, or a Pub/Sub 10x overload — and write the postmortem a real incident review would accept.
- **Present** a production architecture in a live review and answer the standard staff-engineer questions about blast radius, failure modes, cost, and data correctness without flinching.
- **Write** an honest exit plan that prices the lock-in: what it costs in engineer-weeks and dollars to move this workload to AWS or to self-hosted Kafka + Trino + Iceberg + vLLM.
- **Produce** a billing-export cost report from BigQuery that ties the running system to a number under \$500/month at list price, with three concrete optimization moves.
- **Clear** the PCA / Cloud DevOps Engineer practice exam at >=70%, and identify your two weakest blueprint domains with a study plan.
- **Record** a 5-minute walkthrough that a hiring manager can watch and a peer can reproduce.

## Prerequisites

This week assumes you have completed Weeks 01–14 of C18 and that those mini-projects produced working, version-controlled Terraform. Specifically, you need:

- A GCP project (or two: primary + standby) with billing enabled and a budget alert armed. (Week 01.)
- A working Terraform module library: `org-bootstrap`, `vpc`, `iam-baseline`, plus the per-service modules accumulated through Week 14. (Week 04 onward.)
- Workload Identity Federation configured for your CI so deploys carry no long-lived keys. (Week 02.)
- A GKE Standard cluster module, a Cloud Run ingest module, a Pub/Sub + Dataflow module, a BigQuery dataset module, a Spanner module, and a Vertex AI serving module — each deployable on its own and composable. (Weeks 06–12.)
- OpenTelemetry wired through every service with at least one SLO and one burn-rate alert per service. (Week 13.)
- The Week 14 security and FinOps controls: Org Policy bundle, VPC SC perimeter, Binary Authorization, Secret Manager, CMEK, billing export to BigQuery.

If any of those is missing or broken, this week will expose it. That is the point.

## Topics covered

- How a real architecture review runs: the agenda, the artifacts, the questions, and the failure modes of the *reviewer* as well as the reviewed.
- The staff-engineer question set: blast radius, the single points of failure, the data-loss windows, the "what pages you at 3am" walk, and the cost-per-request math.
- The exit-plan discipline: naming every managed-service dependency, pricing the replacement, and being honest about the engineer-weeks.
- Load testing an end-to-end system: generating 100 RPS, measuring p99 *end-to-end* (not per-hop), and reading the latency distribution off Cloud Monitoring.
- Chaos engineering on GCP: region failover via Cloud DNS health-checked routing, TLS certificate rotation on a global load balancer, and Pub/Sub backpressure under 10x overload.
- The PCA and Cloud DevOps Engineer exam blueprints: domain weighting, the question style, and the readiness gate.
- Billing-export-to-BigQuery cost analysis: the queries that attribute spend to a service, and the three optimization moves that pay back first.
- The 5-minute video walkthrough: what to show, what to skip, and how to trace one event on camera.
- Mock interview structure: one system-design round and one GCP deep-dive round.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract; the capstone deserves whatever it takes.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Final integration; the architecture-review playbook    |    2h    |    0.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Tuesday   | Load test at 100 RPS; read the p99 off the dashboard   |    0h    |    2h     |     1h     |    0.5h   |   1h     |     2h       |    0h      |     6.5h    |
| Wednesday | Chaos drill: failover / cert rotation / Pub/Sub 10x    |    1h    |    2h     |     1h     |    0.5h   |   1h     |     1.5h     |    0h      |     7h      |
| Thursday  | The exit plan; the cost report; PCA practice exam      |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     1.5h     |    0.5h    |     6.5h    |
| Friday    | Record the video; deliver the live architecture review |    0h    |    0h     |     0h     |    0.5h   |   0h     |     3h       |    0.5h    |     4h      |
| Saturday  | Mock interview; portfolio polish; teardown drill       |    0h    |    0h     |     0h     |    0h     |   1h     |     2h       |    0.5h    |     3.5h    |
| Sunday    | Quiz, retrospective, course wrap                       |    0h    |    0h     |     0h     |    1h     |   0h     |     0.5h     |    0.5h    |     2h      |
| **Total** |                                                        | **4h**   | **8h**    | **2h**     | **3.5h**  | **5h**   | **12.5h**    | **2.5h**   | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Architecture-review references, exam blueprints, load/chaos tooling, exit-plan templates |
| [lecture-notes/01-how-a-real-architecture-review-runs.md](./lecture-notes/01-how-a-real-architecture-review-runs.md) | The agenda, the artifacts, and the questions a staff engineer will ask |
| [lecture-notes/02-the-exit-plan-defending-the-cost-of-leaving-gcp.md](./lecture-notes/02-the-exit-plan-defending-the-cost-of-leaving-gcp.md) | Pricing the lock-in: every managed dependency, its replacement, and the engineer-weeks |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-load-test-100rps-p99.md](./exercises/exercise-01-load-test-100rps-p99.md) | Run 100 RPS for 30 minutes and verify p99 < 500ms end-to-end |
| [exercises/exercise-02-chaos-drill.py](./exercises/exercise-02-chaos-drill.py) | Drive and verify one chaos drill, capture the timeline, write the result |
| [exercises/exercise-03-pca-readiness-gate.py](./exercises/exercise-03-pca-readiness-gate.py) | Score the PCA / Cloud DevOps practice exam against the >=70% gate |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-deliver-the-capstone-live.md](./challenges/challenge-01-deliver-the-capstone-live.md) | Deliver the Realtime Event Pipeline at Scale live, end to end |
| [quiz.md](./quiz.md) | 13 questions, answer key at the bottom |
| [homework.md](./homework.md) | The week's deliverables with a rubric |
| [mini-project/README.md](./mini-project/README.md) | The full capstone integration brief |

## The "it runs on demand" promise

C18 has one recurring marker, and Week 15 is where it cashes out:

```
terraform destroy complete · 0 resources remaining · 4m12s
```

The grader will clone your repo, run `terraform apply`, hit your system at 100 RPS, run a chaos drill, read your dashboards, then run `terraform destroy` and confirm zero resources remain and zero billing tail. If `apply` and `destroy` are not both clean and idempotent, the capstone does not pass — regardless of how good the architecture diagram looks. A system you cannot stand up and tear down on demand is not a system you operate; it is a system you are afraid of.

## Stretch goals

If you finish the regular work early and want to push further:

- Make Spanner multi-region (`nam3`) instead of regional and re-run the cost report. Document the delta and whether the strong-consistency-across-regions guarantee is worth it for *this* workload.
- Add a second chaos drill. You only have to execute one for the capstone; executing two makes your postmortem section materially stronger in a portfolio.
- Replace the `hey`-based load generator with a Locust distributed run from three regions and compare the p99 you measure from each.
- Write the exit plan for *both* targets (AWS and self-hosted) instead of one, and put a confidence interval on each engineer-week estimate.
- Read one published architecture review or "post-incident review" from a company that runs on GCP (Spotify, Snap, Cloudflare, Shopify engineering blogs) and write a one-page note on what they asked that you did not.

## Up next

There is no Week 16. After you push the capstone and clear the readiness gate, you are done with C18. The intended next track is **C22 Crunch Mesh** — take the GKE cluster you just built and grow it into a real multi-service mesh with gRPC, Kafka, and Istio at scale. Read the [Crunch Labs Charter](../../../CRUNCH-LABS-CHARTER.md) for the full pathway.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
