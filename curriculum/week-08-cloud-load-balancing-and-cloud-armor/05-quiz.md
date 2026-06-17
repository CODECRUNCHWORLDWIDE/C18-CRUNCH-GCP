# Week 8 — Quiz

Fourteen questions on the five-layer edge, the load-balancer matrix, NEGs, Cloud CDN, Cloud Armor in CEL, IAP, and Private Service Connect. Take it with your lecture notes closed. Aim for 12/14 before moving to Week 9. Answer key at the bottom — don't peek.

---

**Q1.** In the five-layer GCP edge, what is the correct order a request passes through, outside-in?

- A) Load Balancer → Cloud Armor → Cloud CDN → DNS → backend.
- B) DNS → Cloud Armor → Cloud CDN → Load Balancer → backend.
- C) DNS → Cloud CDN → Cloud Armor → Load Balancer → backend.
- D) Cloud Armor → DNS → Load Balancer → Cloud CDN → backend.

---

**Q2.** Cloud Armor and Cloud CDN are configured as:

- A) Standalone products you place in front of the LB with their own forwarding rules.
- B) Features attached to the **backend service** inside the load balancer (`security_policy` and `enable_cdn`).
- C) DNS records.
- D) IAM policies on the project.

---

**Q3.** A request is blocked by a Cloud Armor `deny(403)` rule. Which downstream layers see it?

- A) Cloud CDN and the backend, but not the LB.
- B) None — it is denied at the edge before the cache, the LB routing, and the backend.
- C) All of them; Armor only logs, it does not stop.
- D) Only the backend, which returns the 403.

---

**Q4.** You need a public, global, HTTP/S front door with URL-based routing, Cloud CDN, and full Cloud Armor. Which load balancer?

- A) Passthrough Network LB (L4).
- B) Regional internal Application LB.
- C) Global external Application LB (L7, `EXTERNAL_MANAGED`).
- D) SSL Proxy LB.

---

**Q5.** Which load balancer preserves the client's original source IP and puts no proxy in the path — the right tool for a raw TCP service that must see the real client IP?

- A) Global external Application LB.
- B) Passthrough Network LB.
- C) SSL Proxy LB.
- D) Regional internal Application LB.

---

**Q6.** You want one backend service to send traffic directly to the **pod IPs** of a GKE Service (container-native load balancing). What backend do you attach?

- A) A serverless NEG.
- B) An instance-group backend.
- C) A zonal (standalone) NEG.
- D) A backend bucket.

---

**Q7.** Cloud CDN is set to `FORCE_CACHE_ALL` on a backend service that also serves logged-in users' account pages. What is the consequence?

- A) Nothing; `FORCE_CACHE_ALL` respects `Cache-Control: private`.
- B) Account pages get cached at the edge and one user's page can be served to another — a data-leak bug.
- C) The LB refuses to apply the config.
- D) Cloud Armor blocks the responses.

---

**Q8.** In a Cloud Armor policy, rules evaluate by `priority`. Which is true?

- A) Highest priority number is evaluated first; all matching rules apply.
- B) Lowest priority number is evaluated first; the **first** matching rule's action applies and evaluation stops.
- C) Rules evaluate in random order.
- D) Only the default rule is ever evaluated.

---

**Q9.** You want abusive source IPs to be **temporarily blocked** after they exceed 100 requests in 60 seconds — not merely 429'd while they keep trying. Which action and key?

- A) `throttle`, `enforce_on_key = "ALL"`.
- B) `rate_based_ban`, `enforce_on_key = "IP"`, with `ban_duration_sec`.
- C) `deny(403)`, `enforce_on_key = "XFF_IP"`.
- D) `allow`, `enforce_on_key = "HTTP_COOKIE"`.

---

**Q10.** Why default to `enforce_on_key = "IP"` rather than `"XFF_IP"` when your backend sits directly behind the global LB?

- A) `XFF_IP` is faster but less accurate.
- B) `XFF_IP` keys on a client-supplied, forgeable `X-Forwarded-For` entry; an attacker scatters across buckets and defeats the limit. `IP` uses the real TCP peer (`origin.ip`), which is not forgeable.
- C) `IP` is the only key Cloud Armor supports.
- D) There is no difference.

---

**Q11.** You add a preconfigured SQLi WAF rule at priority 1000 and a per-IP rate limit at priority 900. A SQLi probe arrives during a flood. What does it log as, and what is wrong?

- A) It logs as a 403/DENY at 1000; nothing is wrong.
- B) It logs as a 429/RATE_BASED_BAN at 900, masking that it was a SQLi attack — the WAF should be at a *lower* priority number so it runs first.
- C) It logs as both simultaneously.
- D) It is allowed, because two rules cannot both match.

---

**Q12.** How does a pod/app behind IAP authenticate that a request genuinely came through IAP and was not sent directly to the backend?

- A) It trusts the source IP.
- B) It verifies the signed `X-Goog-IAP-JWT-Assertion` JWT (signature, issuer, and audience) on every request.
- C) It checks for any `X-Forwarded-For` header.
- D) IAP encrypts the whole request body.

---

**Q13.** A per-IP Cloud Armor rate limit does **not** stop a distributed bot that sends one request from each of ten thousand residential IPs. What control addresses that?

- A) A bigger `ban_duration_sec`.
- B) `enforce_on_key = "ALL"` with a huge threshold.
- C) Bot management — reCAPTCHA Enterprise scores surfaced as `token.recaptcha_*.score` in CEL, actioned with a `redirect`-to-challenge or `deny` on low scores.
- D) Cloud CDN.

---

**Q14.** What is Private Service Connect, relative to the public edge you built this week?

- A) A faster public load balancer.
- B) The private door: a service attachment *publishes* your service for other VPCs to consume privately via a PSC endpoint (a private IP), with no public IP or VPC peering. The mirror of the public LB.
- C) A Cloud Armor rule type.
- D) A DNS routing policy.

---
---

## Answer key

**Q1 — B.** DNS resolves the name, then Cloud Armor (edge security), then Cloud CDN (edge cache), then the LB (TLS + routing), then your backend. Order is fixed and load-bearing. (Lecture 1 §1.1.)

**Q2 — B.** Conceptually they sit before the backend, but they are *configured* as features on the backend service (`security_policy = ...`, `enable_cdn = true`). Hold both pictures at once. (Lecture 1 §1.1.)

**Q3 — B.** A `deny` at the edge stops the request before the cache, the routing, and the backend — which is why Armor is your cheapest defense. (Lecture 1 §1.3.)

**Q4 — C.** Global external Application LB is the L7 workhorse: anycast, URL routing, Cloud CDN, full Cloud Armor. The other rows in the matrix exist for non-HTTP or regional/internal cases. (Lecture 1 §1.5.)

**Q5 — B.** The passthrough Network LB (L4) preserves the client source IP and puts no proxy in the path — the Week 05 internal-TCP case. The proxy LBs and Application LBs all terminate/proxy. (Lecture 1 §1.5.)

**Q6 — C.** A zonal (standalone) NEG holds pod `IP:port` endpoints, so the LB reaches pods directly — container-native LB. Serverless NEG = Cloud Run; instance-group = MIG; backend bucket = GCS. (Lecture 1 §1.5.)

**Q7 — B.** `FORCE_CACHE_ALL` ignores origin headers and caches everything, including private per-user responses — a classic data-leak foot-gun. Use `USE_ORIGIN_HEADERS` or `CACHE_ALL_STATIC`. (Lecture 1 §1.4.)

**Q8 — B.** Lowest priority number first; first match wins and evaluation stops — exactly like a firewall list. Order specific rules early, the broad default last. (Lecture 2 §2.1.)

**Q9 — B.** `rate_based_ban` with `ban_duration_sec` temporarily blocks the offending key after it trips the threshold; `throttle` only 429s while over the line. Key on `IP`. (Lecture 2 §2.3.)

**Q10 — B.** `XFF_IP` trusts a client-supplied, forgeable header; an attacker scatters fake first entries across rate buckets. `origin.ip` is the real TCP peer and cannot be forged. (Lecture 2 §2.6.)

**Q11 — B.** Lower number = earlier. With the rate limit at 900 it runs first, so the SQLi probe logs as a 429/RATE_BASED_BAN and you lose the signal that it was an injection attack. The WAF must run *before* the rate limit (lower priority number). (Lecture 2 §2.5.)

**Q12 — B.** Verify the signed `X-Goog-IAP-JWT-Assertion` (signature against Google's IAP keys, issuer `https://cloud.google.com/iap`, audience = this backend). Without verification, a request that reaches the backend directly bypasses IAP entirely. (Lecture 1 §1.6, Exercise 3.)

**Q13 — C.** A per-IP limit can't see that ten thousand single-request IPs are one actor. Bot management (reCAPTCHA Enterprise scores in CEL) addresses the distributed case: challenge or deny low scores. (Lecture 2 §2.7.)

**Q14 — B.** PSC is the private analog of the public forwarding rule: a service attachment publishes your service for other VPCs to consume via a private-IP endpoint, no public exposure or peering. Most production systems have both doors. (Lecture 1 §1.7.)

---

*Scoring: 12+/14 move on. 9–11, re-read the lecture section each missed question cites. <9, re-read both lectures before the mini-project — the edge build assumes this material is reflexive.*
