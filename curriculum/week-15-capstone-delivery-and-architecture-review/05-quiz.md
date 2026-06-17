# Week 15 — Quiz

Thirteen questions. This is the last quiz of the course; it mixes capstone-week material (architecture review, exit plans, load/chaos testing) with the synthesis questions a reviewer or interviewer actually asks. Take it with your notes closed. Aim for 11/13. Answer key at the bottom — don't peek.

---

**Q1.** In an architecture review, what is the *output* of the meeting — the thing that means the review succeeded?

- A) A polished slide deck.
- B) A prioritized risk list, each item tagged accept / mitigate-now / mitigate-later, with owners.
- C) Sign-off that the architecture is perfect.
- D) A recording of the presentation.

---

**Q2.** A reviewer asks "what is the single point of failure in this diagram?" For the capstone, which is the *most defensible* answer?

- A) "There isn't one; it's fully redundant."
- B) "The regional Spanner instance — a region loss takes out current-state reads. Multi-region is the documented fix; I chose regional for the budget. Here's the dollar delta."
- C) "Pub/Sub, because it's a Google service."
- D) "The load balancer, because all traffic goes through it."

---

**Q3.** You claim "p99 < 500ms end-to-end." A staff engineer asks how you measured it. Which measurement is *correct*?

- A) The p99 your `hey` client printed at the end of the run.
- B) The sum of each hop's average latency.
- C) The p99 of `loadbalancing.googleapis.com/https/total_latencies`, server-side, over the sustained 100-RPS window.
- D) The slowest single request you observed.

---

**Q4.** Why is reading the p99 off `hey`'s own client-side histogram unreliable for end-to-end latency?

- A) `hey` only measures successful requests.
- B) Coordinated omission: if a worker stalls waiting on a slow response, it stops issuing requests, hiding the worst latencies behind the back-pressure they caused.
- C) `hey` rounds to whole milliseconds.
- D) `hey` cannot send POST requests.

---

**Q5.** On the lock-in portability spectrum, which capstone component is **green (commodity)** — moving it is config, not code?

- A) Spanner's cross-region external consistency.
- B) BigQuery's serverless scale-to-zero economics.
- C) The GKE workloads (it's Kubernetes — `kubectl apply` works on any cluster).
- D) Cloud Armor's managed bot management.

---

**Q6.** Your Apache Beam pipeline is described as a "yellow" (portable model, proprietary runtime) dependency. Why is that the *good* news in an exit plan?

- A) Beam is owned by Google so it's free.
- B) The same pipeline code runs on the Flink or Spark runner; leaving Dataflow means swapping the runner and I/O connectors, not rewriting the windowing/enrichment logic.
- C) Beam pipelines never need to change.
- D) Beam only runs on Dataflow, so there's nothing to migrate.

---

**Q7.** In the exit-plan effort estimate, the migration cost was concentrated in three components (~8 of 17 engineer-weeks). Which three?

- A) OpenTelemetry, Cloud DNS, and the load balancer.
- B) Pub/Sub, BigQuery, and Spanner.
- C) Cloud Run, GKE, and Secret Manager.
- D) Cloud CDN, Cloud Armor, and Memorystore.

---

**Q8.** The exit plan's honest steady-state conclusion at the capstone's scale (~\$500/mo) is:

- A) Leave immediately; self-hosting is always cheaper.
- B) Leaving is not worth it at this scale — the managed services cost less than the salaries to operate their replacements (+1–2 SRE FTE) — and it becomes worth revisiting only at much larger scale.
- C) Lock-in is irrelevant; never write an exit plan.
- D) Stay on GCP forever regardless of cost.

---

**Q9.** During the region-failover drill, what proves **zero data loss** (as opposed to just "the standby is serving")?

- A) The LB returns 200s from the standby.
- B) The Pub/Sub backlog drains and the dead-letter subscription depth is unchanged across the fault.
- C) The video shows a green dashboard.
- D) `terraform apply` succeeded.

---

**Q10.** Why does the capstone run ingest at `min-instances=1` in primary but `min-instances=0` in standby?

- A) Standby has no traffic so it must be 0.
- B) A FinOps tradeoff: pay for one always-warm instance in primary to kill cold-start on the hot path; keep standby cold because failover tolerates a brief warm-up and you don't want to pay for idle capacity in two regions.
- C) Cloud Run requires different settings per region.
- D) It's a bug; both should be 1.

---

**Q11.** A reviewer says "show me one credential in the repo." What should the result be, and why?

- A) Show the encrypted SA key — encryption makes it safe.
- B) There should be none: Workload Identity Federation for deploys and Secret Manager for runtime credentials mean no key material lives in the repo.
- C) Show the Spanner password — it's needed for the gRPC service.
- D) Credentials in the repo are fine if the repo is private.

---

**Q12.** The grader's single hardest gate on the capstone is teardown. What does "clean teardown" require?

- A) `terraform destroy` removes everything, leaves zero resources (`gcloud asset search-all-resources` confirms), and there is no billing tail — including no leaked Spanner instance or GKE cluster.
- B) You delete the project in the Console.
- C) You stop the Cloud Run service.
- D) You set the budget to \$0.

---

**Q13.** Under a Pub/Sub 10x overload drill, which sequence best describes where a well-built capstone "bends" first?

- A) Ingest crashes immediately at 2x.
- B) Spanner loses data at 3x.
- C) Dataflow lag grows and the subscription backlog builds; past a threshold the burn-rate alert fires, while ingest keeps accepting (publish backpressures) and the DLQ stays empty until truly malformed input appears.
- D) BigQuery rejects all writes at 5x.

---
---

## Answer key

**Q1 — B.** The deliverable of a review is a prioritized, owned risk list. Slides and recordings are inputs, not outputs; "it's perfect" is never a real outcome. (Lecture 1, §1.1, §1.9.)

**Q2 — B.** Naming your own biggest risk with a fix and a cost reads as senior; "there isn't one" reads as someone who hasn't operated a system. (Lecture 1, §1.4, §1.8.)

**Q3 — C.** End-to-end p99 is the server-side LB latency distribution over the sustained window. Summing hop averages ignores queueing; the single slowest request is not a percentile. (Lecture 1, §1.6; Exercise 1.)

**Q4 — B.** Coordinated omission: a stalled load generator stops sending while waiting, so the worst latencies never get sampled. Gil Tene's talk in `resources.md` is the canonical reference. (Exercise 1, Step 2.)

**Q5 — C.** GKE workloads are plain Kubernetes — green/commodity. Spanner consistency and BigQuery economics are red; Cloud Armor bot management is orange. (Lecture 2, §2.2.)

**Q6 — B.** Beam's portability means the runner is swappable; the business logic (windowing, triggers, enrichment) is unchanged. That's why Dataflow is yellow, not orange. (Lecture 2, §2.2, §2.4.)

**Q7 — B.** Pub/Sub (→ Kafka), BigQuery (→ Iceberg+Trino), and Spanner (→ CockroachDB) are the orange/red dependencies that dominate the estimate. (Lecture 2, §2.5.)

**Q8 — B.** At this scale the managed services are cheaper than the headcount to run their replacements; the exit plan is a hedge and negotiating tool, revisited at larger scale. (Lecture 2, §2.6.)

**Q9 — B.** "Serving from standby" proves availability, not durability. Zero data loss is proven by the backlog draining and the DLQ depth being unchanged. (Exercise 2; mini-project resilience criteria.)

**Q10 — B.** It's a deliberate FinOps tradeoff: warm primary for hot-path latency, cold standby to avoid paying for idle capacity, accepting a brief failover warm-up. (Lecture 1, §1.4; mini-project.)

**Q11 — B.** None. WIF + Secret Manager is the whole point; a key in the repo (encrypted or not, private or not) fails the security question. (Lecture 1, §1.4; Week 02 / Week 14.)

**Q12 — A.** Clean teardown = `destroy` removes everything, an asset search confirms zero remaining, and there's no billing tail. The Spanner instance and GKE cluster are the classic leaks. (Challenge 1; mini-project.)

**Q13 — C.** A well-built system absorbs overload gracefully: ingest backpressures rather than crashing, the backlog and Dataflow lag grow, the burn-rate alert fires, and the DLQ only fills with genuinely malformed input. (Exercise 2, pubsub-overload; Lecture 1, §1.4.)

---

*Score 11+/13 and you're ready for the live review. Below that, re-read the lecture section cited next to each one you missed before Friday.*
