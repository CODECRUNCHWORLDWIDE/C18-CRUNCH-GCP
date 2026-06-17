# Week 8 — Homework

Six problems. They go beyond the exercises: where the exercises walked you through a single layer, these make you *reason* about the edge, *measure* it, and *defend* your choices in writing. Total budget ~4 hours. Each problem states its deliverable and its time estimate. Graded against the rubric at the bottom.

Submit a single `HOMEWORK.md` in your week-08 working directory with one section per problem, plus any code/Terraform/log snippets the problem asks for. Real commands and real output — the "show it, don't assert it" rule from the README applies to homework too.

---

## Problem 1 — The protection matrix, from memory (≈25 min)

Without looking at Lecture 1, reproduce the five-layer protection matrix: for **each** of DNS, Cloud Armor, Cloud CDN, the Load Balancer, and IAP, write one thing it **can** protect and one thing it **cannot**. Then add a sixth row for the **backend** itself.

After you write it from memory, check it against §1.8 and mark every cell you got wrong or fuzzy. The grade is on the *corrected* matrix plus a one-paragraph note on which cell you were least sure of and why.

**Deliverable:** the six-row matrix + the reflection paragraph.

---

## Problem 2 — Pick the load balancer, four times (≈30 min)

For each workload below, name the correct GCP load balancer from the four-row matrix (global external Application / regional internal Application / SSL Proxy / passthrough Network), and justify it in two sentences on **protocol** and **scope**:

1. A public REST API served from Cloud Run, wanting anycast, Cloud CDN for its `/static` assets, and a SQLi WAF.
2. An internal gRPC service called only by other services inside the VPC, in one region.
3. A custom binary protocol over TLS (not HTTP) that you want Google to terminate TLS for and front with a single global IP.
4. A game server that uses raw UDP and must see each player's real source IP, in one region.

**Deliverable:** four (LB, two-sentence justification) pairs. One of them is a trap where the obvious answer is wrong — find it and say why.

---

## Problem 3 — Write and defend a Cloud Armor policy for a real abuse pattern (≈45 min)

A login endpoint `/auth/login` is being credential-stuffed: bursts of `POST`s from a rotating set of ~30 source IPs, ~20 requests/second each, plus occasional SQLi probes in the form field. Your office (`198.51.100.0/24`) load-tests this endpoint nightly and must never be blocked. Legitimate users log in at most a few times a minute.

Write the **complete** Cloud Armor policy in HCL (`google_compute_security_policy`) that:

- never blocks the office CIDR,
- blocks SQLi with the preconfigured rule, logged as a 403,
- rate-limits `POST /auth/login` per source IP with a `rate_based_ban`, threshold justified by the "few per minute for humans, 20/s for the attacker" gap,
- defaults to allow.

Then write **three sentences** defending your priority ordering: why the office allow is first, why the WAF is before the rate limit, and why you chose `enforce_on_key = "IP"` over `XFF_IP`.

**Deliverable:** the HCL policy + the three-sentence defense.

---

## Problem 4 — Measure a Cloud CDN cache hit, and a cache miss you cannot fix (≈40 min)

Using the Exercise 1 LB (or a fresh one), demonstrate with **real output**:

1. A cacheable path (`Cache-Control: public, max-age=...`) returning `cacheHit: True` in the Cloud Logging output on a repeat request. Paste the log line.
2. A path with `Cache-Control: private` (or `no-store`) that **never** caches no matter how many times you hit it. Paste two log lines showing `cacheHit: False`.
3. A one-paragraph explanation of *why* the second path cannot be cached safely and what would happen if you forced it with `FORCE_CACHE_ALL`.

**Deliverable:** the two `gcloud logging read` outputs + the paragraph.

---

## Problem 5 — Prove the IAP JWT verification is not optional (≈30 min)

Using the Exercise 3 app (you can run it locally — it does not need real IAP for the negative tests):

1. Run the app's `__main__` self-test and paste the output showing a garbage JWT is rejected with 401.
2. In writing, explain the attack the verification prevents: describe, step by step, what an attacker does if your backend trusts `X-Goog-IAP-JWT-Assertion` *without verifying it*, or trusts an unauthenticated request because "it's only reachable through the LB."
3. State the two backend-side controls that together make IAP non-bypassable (hint: one is the JWT verification, the other is about who may invoke the backend directly).

**Deliverable:** the self-test output + the two-paragraph explanation + the two controls.

---

## Problem 6 — A first cost line for the edge (≈40 min)

Using the GCP pricing pages from `resources.md` (re-checked — note the date you checked), estimate the **monthly list-price cost** of just the *edge* you would run in front of a small production service:

- one global external Application LB (forwarding rule + data processing for, say, 100 GB/month of traffic),
- one Cloud Armor policy with 4 rules processing ~10M requests/month,
- Cloud CDN serving ~60 GB/month from cache (cache egress + cache lookups),
- one reserved global IP (in use),
- one Google-managed cert.

Build a small table (component, unit price, quantity, monthly cost), sum it, and identify the single largest line item. Then state one assumption that, if wrong by 2×, would most change the total.

**Deliverable:** the cost table + total + the largest-item call-out + the sensitivity note. (This is the warm-up for the mini-project's Part B cost model — reuse it there.)

---

## Rubric

| Problem | Points | Full marks |
|---------|-------:|------------|
| 1 — protection matrix | 15 | Six correct rows (can/cannot each) + honest reflection. |
| 2 — LB selection | 15 | Four correct LBs with protocol+scope justification; the trap identified. |
| 3 — Cloud Armor policy | 20 | Correct, ordered HCL that satisfies all four requirements; the three-sentence defense is right on ordering + key choice. |
| 4 — CDN measurement | 15 | Real `cacheHit: True` and `cacheHit: False` log lines + correct explanation of the un-cacheable path. |
| 5 — IAP verification | 15 | Self-test output + a correct, specific bypass attack + both backend controls named. |
| 6 — edge cost line | 20 | A real-number table with stated date/assumptions, a correct sum, the largest item, and a sensible sensitivity note. |
| **Total** | **100** | |

A passing homework is ≥70 with **no zero** on Problems 3, 5, or 6 — the policy, the verification, and the cost model are the three skills this week most needs to be reflexive before Phase 3. Time estimates are guidance; if a problem takes far longer, note where you got stuck so office hours can target it.

---

*Submit `HOMEWORK.md` before the Sunday quiz. The mini-project's architecture review reuses your Problem 6 cost line and your Problem 1 matrix — do these well and Part B gets shorter.*
