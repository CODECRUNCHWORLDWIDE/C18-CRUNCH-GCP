# Challenge 1 — Cold-start bakeoff: Cloud Run + private Cloud SQL over PSC, behind Cloud Armor

> **Estimated time:** 3–4 hours. Worth more than its time-cost suggests: this is the exact midterm-architecture-review deliverable in miniature — a real service, a real security posture, and a defensible cost number.

You will deploy the ingest service end to end — a stateless Cloud Run v2 service backed by a Cloud SQL Postgres instance with **no public IP**, reachable only over **Private Service Connect**, with **Cloud Armor** in front of it — and then run a controlled experiment: measure cold-start behavior and monthly cost at `min-instances=0`, `=1`, and `=3`. The deliverable is a short report with three benchmark tables and a cost comparison you would defend in a review.

This is open-ended. No step-by-step. The exercises gave you each piece; this challenge makes you assemble them and *measure*.

## What you build

1. A FastAPI service (you can reuse the Exercise 2 app) deployed as a Cloud Run v2 service, running as a dedicated service account, with Direct VPC egress into the Week 03 VPC.
2. A Cloud SQL Postgres 15 instance with `ipv4_enabled = false`, PSC enabled, IAM database authentication on, reachable from the service over a PSC endpoint in your VPC. No password anywhere.
3. A **global external HTTPS load balancer** with a **serverless NEG** backend pointing at the Cloud Run service, and a **Cloud Armor** security policy attached to the backend service. (Week 08 covers the LB in depth; here you stand up the minimum to attach Cloud Armor.)
4. A Cloud Armor policy with at least: a **rate-limit rule** (throttle per-IP above a threshold) and one **preconfigured WAF rule** (e.g. the SQLi sensitivity rule). The default action is `allow`; the rules deny/throttle abuse.

## The experiment

For each of `min-instances ∈ {0, 1, 3}`:

1. **Force a cold state.** Deploy the revision, then wait past the idle window (no traffic for ~15 minutes) so instances scale down to the floor.
2. **Measure cold-start penalty.** Send a single request after idle and record its latency. Repeat a few times (re-idling between) to get a stable cold number. Then send sustained traffic and record the warm p50/p99. The cold-start penalty is `cold_latency − warm_p50`.
3. **Measure burst behavior.** Use `hey` to send a sudden burst (e.g. `-c 60 -n 600`) after idle and record the p99. At `min=0` the whole burst is cold; at `min=1` one instance's worth is warm; at `min=3` most of it is warm.
4. **Record the monthly cost** of that floor: the idle cost of the warm instances (`floor × ~$9.72/month` per 1-vCPU instance) plus the active serving cost for your modeled traffic. Use the Lecture 1 / Lecture 2 formulas.

Run the cold path through Cloud Armor (hit the LB IP / hostname), so your numbers reflect the real edge, not the bare `*.run.app` URL.

## Deliverable

A `report.md` containing:

- **Architecture summary** (5–10 lines): the request path (client → Cloud Armor → LB → serverless NEG → Cloud Run → PSC → Cloud SQL), and a one-line justification of each private/security choice.
- **Three benchmark tables**, one per floor, each with: cold-start latency, warm p50, warm p99, burst p99, and the monthly cost of that floor. Example shape:

  | min-instances | cold start | warm p50 | warm p99 | burst p99 | monthly cost |
  |--------------:|-----------:|---------:|---------:|----------:|-------------:|
  | 0             |   ~1.6 s   |   42 ms  |  88 ms   |  ~1.6 s   |   \$X        |
  | 1             |   42 ms\*  |   41 ms  |  85 ms   |  ~0.9 s   |   \$X+10     |
  | 3             |   41 ms    |   40 ms  |  83 ms   |   95 ms   |   \$X+29     |

  (\* first request after idle is warm-served at `min≥1`.)

- **A break-even paragraph.** Using the Lecture 2 formula `N_cold × c_cold > idle_cost`, state which floor you would actually ship for this service and why, with a `c_cold` assumption you name. Include the crossover.
- **A Cloud Armor proof.** Two `curl`/`hey` transcripts: one showing the rate-limit rule throttling (HTTP 429 after the threshold), one showing the WAF rule blocking an SQLi probe (HTTP 403 on a `?q=' OR 1=1--` style request).
- **A teardown confirmation** line (see below).

## Acceptance criteria

- [ ] Cloud SQL instance has **no public IP** (`ipv4Enabled = false`); reachable only over PSC. Prove it with `gcloud sql instances describe`.
- [ ] The service authenticates with **IAM database auth** — no password in env, Secret Manager, or connection string. `/whoami` returns the service account as `current_user`.
- [ ] A global HTTPS LB with a serverless NEG fronts the service, with a Cloud Armor policy attached to the backend service.
- [ ] The Cloud Armor policy throttles per-IP (rate-limit) **and** blocks an SQLi probe (preconfigured WAF rule). Both demonstrated with a transcript.
- [ ] Cold-start, warm p50/p99, and burst p99 measured at `min-instances` 0, 1, and 3, through the LB.
- [ ] Monthly cost computed for each floor using the lecture formulas (idle warm cost + active serving cost).
- [ ] A break-even recommendation with a named `c_cold` and the crossover.
- [ ] `report.md` contains all three tables, the break-even paragraph, the Cloud Armor proof, and the teardown confirmation.
- [ ] Everything is Terraform (the LB + Cloud Armor may use the `gcloud` path if you prefer, but the service + Cloud SQL + PSC must be Terraform).

## Hints (not steps)

- A serverless NEG (`google_compute_region_network_endpoint_group` with `cloud_run { service = ... }`) is how you attach a Cloud Run service to a backend service. The LB needs a managed cert (a `sslcert` or a Google-managed cert on a domain you control, or use the `nip.io`-style trick for a quick test hostname).
- To force re-idle quickly, you can set the service's idle timeout behavior by simply not sending traffic; Cloud Run scales `min=0` services down within a few minutes of inactivity.
- Measure the cold start at the *application* layer too: log a timestamp at process start and at first-request-served, and diff them. That isolates app-init (phase 4) from network + LB latency.
- Try the image-shrink trick from Lecture 2 between runs: a multi-stage slim image vs. a fat one. Note how much the cold start drops and how that changes which floor you'd pick. (Bonus, not required.)
- The rate-limit rule uses `rate_limit_options` with a `ban_threshold` / `rate_limit_threshold` and `conform_action = "allow"`, `exceed_action = "deny(429)"`. The SQLi WAF rule uses `evaluatePreconfiguredExpr('sqli-v33-stable')` in the `expr` match.

## Going further (no extra grade)

- Add a **Go** version of the service and run the same bakeoff. The distroless Go binary will cold-start far faster; show how that moves your `min-instances` recommendation.
- Schedule the floor with a Cloud Scheduler job (Lecture 2.6) — `min=1` business hours, `min=0` overnight — and recompute the monthly cost. Show the saving.
- Put the `c_cold` term on a real footing: if this were a checkout endpoint, what conversion-loss number would justify `min=3`? Model it.

## Submission

Commit to your Week 7 GitHub repository at `challenges/challenge-01-coldstart-bakeoff/` containing the Terraform, the app, and `report.md`. The grader re-runs your cost spreadsheet and spot-checks one benchmark table against a live re-deploy.

## Teardown (do not skip — Cloud SQL bills per hour)

Tear down the LB, the Cloud Armor policy, the serverless NEG, the Cloud Run service, the PSC endpoint, and the Cloud SQL instance. Confirm:

```
cloud sql: 0 · cloud run: 0 · forwarding rules: 0 · backend services: 0 · armor policies: 0  →  PASS
```

Put that line at the bottom of `report.md`.

---

**References**

- Cloud Run — Cloud Armor + serverless NEG: <https://cloud.google.com/load-balancing/docs/https/setting-up-https-serverless>
- Cloud Armor — rate limiting: <https://cloud.google.com/armor/docs/rate-limiting-overview>
- Cloud Armor — preconfigured WAF rules: <https://cloud.google.com/armor/docs/waf-rules>
- Cloud SQL — Private Service Connect: <https://cloud.google.com/sql/docs/postgres/configure-private-service-connect>
- Cloud Run — minimum instances: <https://cloud.google.com/run/docs/configuring/min-instances>
