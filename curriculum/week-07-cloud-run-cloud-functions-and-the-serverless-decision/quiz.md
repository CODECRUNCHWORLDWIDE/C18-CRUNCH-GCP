# Week 7 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 8. Answer key at the bottom — don't peek.

---

**Q1.** A Cloud Run service handles a steady, continuous 40 RPS, each request taking 100 ms, on 1 vCPU / 512 MiB instances with concurrency 80. You estimate monthly cost as `requests × latency × vCPU × price = 40 × 0.100 × 1 × $0.000024 × 2.59M ≈ $248`. A teammate says the real number is closer to \$107. Who is right and why?

- A) You are right; the teammate forgot the per-request fee.
- B) The teammate is right; you double-counted CPU that concurrency 80 amortizes across simultaneous requests. Once an instance is saturated, model cost as active-instance-seconds, not request-seconds.
- C) Both are wrong; Cloud Run bills per request only.
- D) You are right; concurrency does not affect billing.

---

**Q2.** Your handler is CPU-bound (50 ms of real computation per request, no I/O). You deploy at the default concurrency of 80 on 1 vCPU and p99 is ~1 second under load. What is the correct fix?

- A) Raise `max-instances` to 100 — the autoscaler will add instances and p99 drops.
- B) **Lower** concurrency (e.g. to 8) so each instance handles fewer simultaneous requests and Cloud Run scales out horizontally instead of stacking CPU-bound work onto a saturated instance.
- C) Raise concurrency to 200 to amortize the CPU further.
- D) Switch to `cpu_idle = true` to allocate more CPU.

---

**Q3.** For an **I/O-bound** handler (mostly waiting on Postgres, ~0 CPU while waiting), the correct concurrency posture is:

- A) Lower concurrency to ~8, same as the CPU-bound case.
- B) Keep concurrency high (at or near the default 80): many waiting requests coexist cheaply on one instance, and lowering it would waste money by scaling out unnecessarily.
- C) Set concurrency to 1 for predictability.
- D) Concurrency has no effect on I/O-bound handlers.

---

**Q4.** You model two cost lines: Cloud Run (`min-instances=0`) and a **dedicated** regional GKE cluster (2× e2-standard-2 spot + control plane ≈ \$102/month flat). For a 100 ms / 1 vCPU request shape, where is the crossover, and what happens to it if the GKE cluster is **shared** across ten services instead of dedicated?

- A) Crossover ~38 RPS; sharing the cluster moves the crossover **up** (Cloud Run wins for longer).
- B) Crossover ~38 RPS; sharing the cluster moves the crossover **down** (GKE wins sooner) because the control-plane fee and node capacity are amortized, dropping GKE's effective line to ~\$20–30.
- C) There is no crossover; Cloud Run is always cheaper.
- D) Crossover ~38 RPS; sharing the cluster has no effect on cost.

---

**Q5.** Which workload is the textbook case where Cloud Run wins decisively and the crossover RPS is irrelevant?

- A) A service pinned at 100% CPU 24/7.
- B) A service that gets 1,000 requests in a 10-minute window once a day and is idle the rest of the time — Cloud Run scales to zero and costs cents; GKE pays full freight for idle nodes.
- C) A service that needs a privileged sidecar.
- D) A service with a 4-hour request timeout.

---

**Q6.** A `min-instances=1` 1-vCPU / 512 MiB instance, kept warm 24/7, costs approximately how much per month at the Cloud Run idle rate, and what does that buy you?

- A) ~\$62/month; it eliminates all cold starts forever.
- B) ~\$10/month; it keeps one instance warm so the first concurrent request after idle skips the cold start (image pull, container start, app init).
- C) ~\$0; min-instances is free.
- D) ~\$250/month; min-instances bills at the active rate continuously.

---

**Q7.** The `min-instances=1` break-even for a service where each cold-served request has business cost `c_cold` is:

- A) `min-instances=1` always pays for itself.
- B) It pays for itself when `N_cold × c_cold > idle_cost` (≈ \$9.72/month) — i.e. when the value of the cold starts it eliminates exceeds the cost of keeping the instance warm.
- C) It pays for itself when latency exceeds 1 second.
- D) It pays for itself when `max-instances > 10`.

---

**Q8.** A service has a "99% of requests under 400 ms" SLO. Its cold-start penalty is 1.5 s, and `N_cold / N_total = 2%`. What does the SLO say about `min-instances`?

- A) Nothing; SLOs don't affect serverless config.
- B) Cold starts alone consume 2% of requests as violations, exceeding the 1% error budget — so `min-instances ≥ 1` is **mandatory** to meet the SLO, regardless of the dollar cost. This is the SLO-budget (Flavor A) case.
- C) The SLO is met because 2% < 400 ms.
- D) Set `min-instances=0` and lower the SLO.

---

**Q9.** You want a Cloud SQL Postgres instance reachable from Cloud Run with the strongest private posture. Which configuration is the 2026-correct answer?

- A) Public IP + Cloud SQL Auth Proxy + authorized networks.
- B) Private services access (legacy VPC peering) + a static password.
- C) `ipv4_enabled = false` (no public IP) + Private Service Connect endpoint in your VPC + IAM database authentication (no password) + Direct VPC egress from Cloud Run.
- D) Public IP with TLS-only enforced.

---

**Q10.** With IAM database authentication via the Cloud SQL Python connector (`enable_iam_auth=True`), what does the application send as the Postgres "password"?

- A) A static password stored in Secret Manager.
- B) Nothing — IAM auth disables passwords entirely and connects anonymously.
- C) A short-lived OAuth2 token minted for the ambient service account, presented as the password over a mutual-TLS channel; there is no static password.
- D) The service account's private key file.

---

**Q11.** What is the relationship between Cloud Functions gen2, Cloud Run services, and Cloud Run jobs?

- A) They are three unrelated products with separate runtimes.
- B) Cloud Functions gen2 *is* a Cloud Run service built by Buildpacks; a Cloud Run job is the same runtime for run-to-completion batch work (no `$PORT`); Eventarc is a uniform event router in front of all three.
- C) Cloud Functions gen2 runs on App Engine; jobs run on GKE.
- D) Jobs and services are the same thing with different names.

---

**Q12.** You wire an Eventarc trigger for `google.cloud.storage.object.v1.finalized` but it never fires when you upload a file. Which missing IAM grant is the most common cause?

- A) The Cloud Run service needs `roles/owner`.
- B) The **GCS service agent** needs `roles/pubsub.publisher` — Eventarc's GCS source delivers events through a Pub/Sub topic the GCS service agent must be able to publish to.
- C) Your user account needs `roles/storage.admin`.
- D) The bucket needs to be public.

---

**Q13.** Why can't an Eventarc trigger target a Cloud Run **job** directly the way it can target a Cloud Run **service** or a gen2 function?

- A) Jobs are deprecated.
- B) A job has no `$PORT` and does not listen for HTTP, so it cannot receive the HTTP-delivered CloudEvent. The pattern is to target a small Cloud Run **service** (a "launcher") that receives the event and calls the Cloud Run Admin API to execute the job.
- C) Jobs can only be triggered by Cloud Scheduler.
- D) Eventarc cannot trigger anything in Cloud Run.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Concurrency amortizes CPU across simultaneous requests. The request-seconds formula (`requests × latency × vCPU × price`) double-counts CPU shared by up to `concurrency` in-flight requests. Once an instance is saturated, model cost as *active-instance-seconds*: a single continuously-active 1-vCPU instance is ~\$62 vCPU + ~\$3 mem + ~\$41 requests ≈ \$107/month, not \$248.

2. **B** — For CPU-bound work, high concurrency tells Cloud Run to stack requests onto one saturated instance; the autoscaler reads "50 of 80 allowed in flight, fine" and does not scale out. Lowering concurrency forces horizontal scale-out so each request gets close to a full vCPU. Raising `max-instances` (A) does not help because the autoscaler isn't triggered.

3. **B** — A sleeping/waiting request uses ~0 CPU, so 80 of them coexist happily on one instance. High concurrency is *correct* and cheapest for I/O-bound handlers; lowering it would scale out unnecessarily and cost more. The right concurrency is a function of how CPU-bound the handler is.

4. **B** — For the 100 ms / 1 vCPU shape against a dedicated ~\$102/month cluster, the lines cross around 38 RPS. A shared cluster amortizes the \$73 control-plane fee and the node capacity across many tenants, dropping GKE's effective line to ~\$20–30 and moving the crossover **down** (GKE wins much sooner — often below ~10 RPS).

5. **B** — Low duty cycle is the textbook Cloud Run win: scale-to-zero costs nothing overnight, while GKE pays for idle nodes 24/7. The crossover RPS is irrelevant because you never approach it. (A) and (C)/(D) are GKE/GCE cases or feature-gap overrides.

6. **B** — At the idle rate (`$0.0000025`/vCPU-s and /GiB-s), a 1-vCPU/512-MiB instance kept warm 24/7 is ~\$6.48 vCPU + ~\$3.24 mem ≈ \$9.72/month. It keeps one instance warm so the first concurrent request after idle skips image pull + container start + app init.

7. **B** — `min-instances=1` pays for itself when `N_cold × c_cold > idle_cost` (~\$9.72/month). Estimate `N_cold` from traffic shape; assign `c_cold` from business context; compare.

8. **B** — This is the SLO-budget (Flavor A) case. If cold-served requests (2%) exceed the error budget (1%) at p99, cold starts alone bust the SLO, so `min-instances ≥ 1` is mandatory regardless of the \$10/month — it's the price of a commitment you already made.

9. **C** — The strongest private posture in 2026: no public IP, a PSC endpoint in your VPC, IAM auth (no password), and Direct VPC egress so Cloud Run reaches the endpoint. Public IP + Auth Proxy (A) leaves a routable address; legacy private services access (B) works but is the older peering model and a static password is a finding.

10. **C** — The connector mints a short-lived OAuth2 token for the ambient service account and presents it as the Postgres password over mutual TLS. There is no static password to store or leak. (B) is wrong — IAM auth is still authentication, just token-based.

11. **B** — gen2 functions are Cloud Run services built by Buildpacks (you can see the underlying service in the Cloud Run console); jobs are the same runtime for run-to-completion work with no `$PORT`; Eventarc routes events to all three. Seeing them as faces of one platform collapses a lot of confusion.

12. **B** — Eventarc's Cloud Storage source delivers via a Pub/Sub topic the GCS service agent publishes to. Without `roles/pubsub.publisher` on the GCS service agent, the trigger creates but never fires. This is the single most common Eventarc-from-GCS fumble.

13. **B** — A job has no `$PORT` and doesn't serve HTTP, so it can't receive the HTTP CloudEvent. Target a tiny Cloud Run service ("launcher") that receives the event and calls the Cloud Run Admin API (`run_job`) to execute the job, passing event data (e.g. the object name) as an env override.

</details>

---

If you scored under 9, re-read the lectures for the questions you missed — especially the cost-curve math (Q1, Q4) and the `min-instances` break-even (Q6–Q8). If you scored 11 or higher, you're ready for the [homework](./homework.md).
