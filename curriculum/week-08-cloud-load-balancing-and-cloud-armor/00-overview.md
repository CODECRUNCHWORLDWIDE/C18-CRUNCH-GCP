# Week 8 — Cloud Load Balancing & Cloud Armor

Welcome to **C18 · Crunch GCP**, Week 8 — the week that closes Phase 2. Week 05 put a service on a VM behind an internal load balancer; Week 06 put it on GKE and taught you to upgrade the cluster without dropping a request; Week 07 put it on Cloud Run and gave you the serverless cost curve. In all three cases the service answered on a private address inside the Week 03 VPC, or on a `*.run.app` URL Google owns. This week we build **the edge** — the public front door that the internet hits before it ever reaches your backend — and we build it the way a production shop builds it: as five distinct layers, each with a job, each with a thing it can and a thing it cannot protect.

By Friday you should be able to stand up a **global external Application Load Balancer** with a serverless Network Endpoint Group pointed at the Week 07 Cloud Run service, attach **Cloud CDN** so the cacheable bytes never touch your origin, write a **Cloud Armor** security policy in Common Expression Language that rate-limits abusive source IPs and rejects SQL-injection probes with a preconfigured WAF rule, place **Identity-Aware Proxy** in front of an internal admin app so only members of one Google group get past the front door, and reason about **Private Service Connect** as the private-network alternative to a public LB. You should also be able to do the harder thing: draw the five-layer edge from memory, point at each layer, and say exactly what it stops and what sails straight through it.

The first thing to internalize is that **the GCP edge is not one product — it is a pipeline of five layers, and an attack or a request passes through them in a fixed order.** From the outside in: **DNS** (Cloud DNS resolves your name to an anycast IP), then **Cloud Armor** (the security policy attached to the backend service evaluates the request at Google's edge, before your origin is involved), then **Cloud CDN** (a cache hit is served from the edge and never reaches your backend at all), then the **Load Balancer** (the global forwarding rule, target proxy, URL map, and backend service that terminate TLS and route the request), then your **backend** (Cloud Run, a GKE service via a zonal NEG, a managed instance group, or a GCS bucket). Every defensive and performance decision you make this week lives at exactly one of those layers, and the senior skill is knowing which layer owns which problem. Cloud Armor cannot cache. Cloud CDN cannot block SQLi. DNS cannot rate-limit. The LB cannot authenticate a user. Put the control at the wrong layer and it either does nothing or it does the wrong thing expensively. Lecture 1 is the whole pipeline, layer by layer, with the "what it protects / what it cannot" table you will be quizzed on.

The second thing to internalize is that **Cloud Armor is a Common Expression Language engine, not a checkbox.** A Cloud Armor security policy is an ordered list of rules; each rule has a `priority`, a `match` expression written in CEL, and an `action` (`allow`, `deny(403)`, `deny(429)`, `rate_based_ban`, `throttle`, or `redirect` to reCAPTCHA). The preconfigured WAF rules — SQLi, XSS, LFI, RCE, the OWASP CRS bundle — are *also* CEL, wrapped in the `evaluatePreconfiguredExpr('sqli-v33-stable')` function so you do not hand-write a thousand-line regex. Rate limiting is a rule with a `rate_limit_options` block keyed on a CEL-derived bucket (per source IP, per `X-Forwarded-For` header, per region). Bot management is reCAPTCHA Enterprise scores surfaced into CEL via `token.recaptcha_action.score`. Once you see that all of it is one expression language over the request, you stop memorizing checkboxes and start writing rules. Lecture 2 is CEL end to end: the request attributes you can match on, the preconfigured-expression catalog, the rate-limit bucket semantics, and the `rate_based_ban` vs. `throttle` distinction that decides whether an abuser gets a 429 or a temporary block.

The third thing to internalize is that **the edge is where you stop trusting the network and start trusting identity.** A public LB with Cloud Armor protects you from volumetric abuse and known-bad payloads, but it does not know *who* the requester is. For an internal admin tool, a metrics dashboard, or a partner API, the right control is **Identity-Aware Proxy** — IAP sits in the LB's request path, forces an OAuth login against Google identities, checks the requester against an IAM policy on the backend (a user, a Google group, a service account), and only then forwards the request, stamping a signed `X-Goog-IAP-JWT-Assertion` header your backend can verify. This is BeyondCorp: no VPN, no bastion, no IP allowlist that breaks the moment someone works from a café. Exercise 3 puts IAP in front of an internal app and gates it on group membership, and the lecture explains why the signed-header verification step is non-negotiable (without it, anyone who reaches your backend directly bypasses IAP entirely).

This is the week that ties Phase 2 together, so it carries the **Phase 1+2 midterm architecture review**. The mini-project is two things welded together: a *global L7 edge with three different backends* (the Week 07 Cloud Run service, a GKE service via a zonal NEG, and a static GCS bucket), Cloud CDN, and a Cloud Armor policy — **and** a five-page architecture-review writeup of the entire system you have built from Week 01 through Week 08, with a cost model and an honest exit plan, peer-reviewed by a cohort member. It compounds Weeks 06 and 07: the GKE backend is the Week 06 cluster, the Cloud Run backend is the Week 07 service. The teardown gate is non-negotiable — a global LB with a reserved anycast IP and a managed certificate is not free, and a forgotten forwarding rule is the kind of thing that quietly bills you for a month.

## Learning objectives

By the end of this week, you will be able to:

- **Diagram** the five-layer GCP edge from memory — DNS → Cloud Armor → Cloud CDN → Load Balancer → backend — and state, for each layer, exactly what it can protect and what it cannot.
- **Choose** the correct load balancer for a workload from the GCP LB matrix: global external Application LB (L7, HTTP/S), regional internal Application LB, TCP/SSL Proxy LB, and the passthrough Network LB (L4) — and defend the choice on protocol, scope, and cost.
- **Provision** a global external Application Load Balancer with Terraform: a reserved global IP, a Google-managed TLS certificate, a target HTTPS proxy, a URL map, and a backend service fronting a serverless NEG.
- **Attach** a serverless NEG (Cloud Run), a zonal NEG (GKE), and a backend bucket (GCS) to one URL map so a single hostname routes by path to three different backend types.
- **Enable** Cloud CDN on a backend service, set a sensible cache mode (`CACHE_ALL_STATIC` vs. `USE_ORIGIN_HEADERS`), and verify cache hits with the `Age` and `Via` response headers and the `cacheHit` log field.
- **Write** a Cloud Armor security policy in Common Expression Language: a `rate_based_ban` rule keyed per source IP, a preconfigured SQLi WAF rule via `evaluatePreconfiguredExpr`, a default-allow tail, and the priority ordering that makes them evaluate correctly.
- **Validate** a rate-limit rule under load with `hey` (watch the 429s appear at the threshold) and validate a WAF rule with a deliberately malformed request (watch the 403 and find it in the Cloud Armor logs).
- **Place** Identity-Aware Proxy in front of an internal application, gate access on a Google group via an IAM policy, and verify the signed `X-Goog-IAP-JWT-Assertion` in the backend so the IAP cannot be bypassed.
- **Explain** Private Service Connect as the private-network alternative to a public edge — when you publish a service via a PSC service attachment vs. when you front it with a public LB — and where it fits relative to the Week 03 VPC.
- **Write and defend** a five-page architecture review of the Phase 1+2 system, including a monthly cost model at list price and a two-page exit plan that is honest about lock-in.

## Prerequisites

- **Weeks 01 through 07 of C18 complete.** You have a landing zone (01), Workload Identity Federation for deploys (02), a multi-region shared VPC with Cloud NAT and Private Google Access (03), a Terraform module library with remote state in GCS (04), a regional MIG behind an internal LB (05), a long-lived regional GKE Standard cluster (06), and a stateless Cloud Run service backed by Cloud SQL over Private Service Connect (07). This week fronts the Week 07 service and adds the Week 06 cluster as a second backend.
- **Working CLI:** `gcloud >= 470.0.0`, `terraform >= 1.9` (or `tofu >= 1.8`), `kubectl >= 1.31` (to attach the GKE NEG), `curl`, and `hey` (`go install github.com/rakyll/hey@latest` or your package manager). `dig` / `nslookup` for the DNS layer. Verify with the smoke check in Exercise 1.
- **A registered DNS name you control, or willingness to use a `nip.io`/`sslip.io` wildcard for the lab.** A Google-managed certificate needs a real hostname that resolves to the LB's IP. The exercises show both the real-domain path and the `sslip.io` fallback so you can complete the week even without a domain.
- **Networking literacy at the README level.** You can explain TLS termination, the difference between an L4 and an L7 load balancer, what anycast is, what a forwarding rule does, and why `X-Forwarded-For` is both useful and forgeable. This week assumes those words mean something to you.
- **A GCP project with billing and a budget alert armed (Week 01).** A global LB reserves an anycast IP (free while attached to a forwarding rule, billed when orphaned), and Cloud Armor and managed certs are cheap but not free. Everything in this week runs inside the \$300 free trial if you honor the teardown gate. Budget ~\$2–4 if you leave the edge up overnight.

## Topics covered

- **The five-layer edge.** DNS (Cloud DNS, anycast, health-checked failover routing policies) → Cloud Armor (edge security policy on the backend service) → Cloud CDN (edge cache) → Load Balancer (forwarding rule, target proxy, URL map, backend service) → backend (Cloud Run, GKE, MIG, GCS). The ordered request path, and the protection matrix: what each layer stops and what passes through.
- **The GCP load-balancer matrix.** Global external Application LB (L7, the workhorse for HTTP/S, Cloud CDN-capable, Cloud Armor-capable); regional external/internal Application LB (L7, regional scope, regional Cloud Armor); global/regional TCP/SSL Proxy LB (L4 proxy, for non-HTTP TLS or raw TCP that still wants a Google-terminated front); passthrough Network LB (L4, preserves client IP, no proxy). When each is the right tool.
- **Backend services and NEGs.** The backend service as the unit that owns health checks, balancing mode, session affinity, Cloud CDN, and the Cloud Armor attachment. Network Endpoint Groups: **serverless NEG** (Cloud Run / App Engine / Cloud Functions), **zonal NEG** (GKE container-native LB, pod IPs directly), **internet NEG** (an external origin), and **hybrid/PSC NEG**. Instance-group backends for MIGs.
- **Cloud CDN.** Enabling it on a backend service, the cache modes (`CACHE_ALL_STATIC`, `USE_ORIGIN_HEADERS`, `FORCE_CACHE_ALL`), TTL controls, cache keys (host, path, query, headers, cookies), negative caching, signed URLs/cookies, and reading the `cacheHit` / `cacheId` log fields. What CDN cannot do (it cannot cache authenticated or `Cache-Control: private` responses).
- **Cloud Armor — the engine.** The security policy as an ordered rule list; `priority`, `match`, `action`; the CEL request attributes (`request.headers`, `request.path`, `request.query`, `origin.ip`, `origin.region_code`); `evaluatePreconfiguredExpr` for the OWASP CRS preconfigured rules (SQLi, XSS, LFI, RCE, scanner-detection, protocol-attack); sensitivity tuning and the `opt_in_rule_ids` / `opt_out_rule_ids` overrides.
- **Cloud Armor — rate limiting and bot management.** `rate_limit_options`: the `rate_limit_threshold`, the `enforce_on_key` bucket (`IP`, `ALL`, `HTTP_HEADER`, `HTTP_COOKIE`, `XFF_IP`), `throttle` vs. `rate_based_ban`, and the `ban_duration_sec`. Bot management via reCAPTCHA Enterprise scores surfaced as `token.recaptcha_action.score` in CEL; the `redirect` action to a reCAPTCHA challenge.
- **Identity-Aware Proxy.** IAP in the LB request path, the OAuth consent screen, the IAM policy on the backend (`roles/iap.httpsResourceAccessor` granted to a user / group / SA), the signed `X-Goog-IAP-JWT-Assertion` header, and **verifying that JWT in the backend** so a request that reaches the origin directly cannot bypass IAP. BeyondCorp / context-aware access as the next step.
- **Private Service Connect, briefly.** PSC endpoints (consume a published service via a private IP in your VPC) vs. PSC service attachments (publish your own service for other VPCs to consume privately). Where PSC fits relative to the public edge: PSC is the private door, the LB is the public door, and most production systems have both.
- **Certificates and DNS.** Google-managed certificates (provisioning, the DNS-authorization vs. load-balancer-authorization path, the propagation wait), self-managed certs, and certificate maps for SNI across many hostnames. Cloud DNS as the resolution layer and its health-checked routing policies for failover.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract. Build the edge early in the day with the billing dashboard open in a second tab — a global LB with an orphaned forwarding rule is a slow, quiet cost, and "stand it up, test it, tear it down" is part of the skill this week teaches.

| Day       | Focus                                                        | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | The five-layer edge; the LB matrix; backend services & NEGs  |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Build the global HTTPS LB + serverless NEG; attach Cloud CDN |    1.5h  |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Wednesday | Cloud Armor in CEL: rate limiting, WAF, bot management       |    2h    |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     7h      |
| Thursday  | Identity-Aware Proxy; Private Service Connect; challenge      |    0.5h  |    1.5h   |     1h     |    0.5h   |   1h     |     1h       |    0.5h    |     6h      |
| Friday    | Mini-project — multi-backend edge via the Week 04 modules     |    0h    |    0h     |     1h     |    0.5h   |   0h     |     3.5h     |    0.5h    |     5.5h    |
| Saturday  | Mini-project deep work; cost model; teardown gate            |    0h    |    0h     |     0h     |    0h     |   0h     |     3.5h     |    0h      |     3.5h    |
| Sunday    | Quiz; the midterm architecture-review writeup; peer review   |    0h    |    0h     |     0h     |    1h     |   0h     |     1.5h     |    0.5h    |     3h      |
| **Total** |                                                              | **6h**   | **7h**    | **3h**     | **3.5h**  | **4h**   | **13h**      | **3h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The Cloud Load Balancing, Cloud CDN, Cloud Armor, IAP, and PSC docs; the CEL reference; the Terraform LB module; the talks worth your time |
| [lecture-notes/01-the-five-layer-gcp-edge.md](./02-lecture-notes/01-the-five-layer-gcp-edge.md) | DNS → Cloud Armor → Cloud CDN → LB → backend, layer by layer, with the protection matrix and the LB-selection decision tree |
| [lecture-notes/02-cloud-armor-in-cel.md](./02-lecture-notes/02-cloud-armor-in-cel.md) | Cloud Armor as a CEL engine: rate limiting, preconfigured WAF rules, bot management, and the rule-ordering rules that make a policy correct |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-global-https-lb-with-cloud-run-neg-and-cdn.md](./03-exercises/exercise-01-global-https-lb-with-cloud-run-neg-and-cdn.md) | Build a global external HTTPS LB with a Cloud Run serverless NEG backend and attach Cloud CDN, end to end, with verification |
| [exercises/exercise-02-cloud-armor-ratelimit-and-sqli.tf](./03-exercises/exercise-02-cloud-armor-ratelimit-and-sqli.tf) | Terraform for a Cloud Armor policy with a per-source-IP `rate_based_ban` rule and a preconfigured SQLi WAF rule, plus the `hey` + `curl` validation runbook |
| [exercises/exercise-03-iap-group-gated-internal-app.py](./03-exercises/exercise-03-iap-group-gated-internal-app.py) | A FastAPI internal app that verifies the IAP-signed JWT, plus the Terraform + `gcloud` to put IAP in front and gate it on a Google group |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-front-week07-with-armor-and-validate-under-load.md](./04-challenges/challenge-01-front-week07-with-armor-and-validate-under-load.md) | Front the Week 07 Cloud Run service with a global HTTPS LB + CDN + a per-IP rate limit + a SQLi WAF rule, then validate with `hey` under load and a malformed request the WAF blocks |
| [quiz.md](./05-quiz.md) | 14 questions, answer key at the bottom |
| [homework.md](./06-homework.md) | Six problems with rubric and time estimates |
| [mini-project/README.md](./07-mini-project/00-overview.md) | Full spec for the multi-backend global edge **and** the Phase 1+2 midterm architecture review |

## The "the edge is honest" promise

Every exercise this week ends with a **proof**, not a claim. "I added a rate limit" is worthless; "I ran `hey -z 30s -c 50` and watched the 429s start at request 101 in a 60-second window, here is the Cloud Armor log entry that shows the `rate_based_ban` action" is the deliverable. "I added a WAF rule" is worthless; "`curl 'https://host/?q=1%20OR%201=1'` returns 403 and the log shows `evaluatePreconfiguredExpr('sqli-v33-stable')` matched at priority 1000" is the deliverable. The phrase "it should block that" never appears in a senior engineer's PR; the phrase "it blocks that — here is the 403 and the log line" does. Practice the second form this week.

## What's not here

Week 08 builds the edge. It does **not** cover:

- **Multi-cluster / multi-region traffic management at the global level (Traffic Director, the global external LB with backends in many regions and weighted routing).** We use one or two regions; global *capacity* management and locality-based routing across continents is a scaling concern we name and defer to the capstone.
- **The full OWASP CRS tuning workflow (false-positive triage, per-rule sensitivity, preview-mode rollout of a whole ruleset).** We enable the preconfigured SQLi expression and discuss sensitivity; running a complete CRS in preview mode, mining the logs for false positives, and graduating it to enforcing mode is a security-team workflow that Week 14 (security hardening) revisits.
- **DDoS at the network layer (Cloud Armor Managed Protection Plus, the always-on L3/L4 protection, adaptive protection ML).** We mention Managed Protection and Adaptive Protection; the paid tier and its ML-driven attack signatures are out of scope for a free-trial week.
- **Service mesh ingress (Istio / Anthos Service Mesh gateways, Gateway API).** The GKE Gateway API and mesh ingress are a C22 (Crunch Mesh) topic. This week uses the classic Ingress/standalone-NEG path to attach GKE to the global LB.
- **mTLS to the backend, BackendAuthenticationConfig, and the full zero-trust service-to-service story.** IAP gives us user-to-service zero trust; service-to-service mTLS is mesh territory (C22) and Week 14 touches the GCP-native pieces.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **External Application Load Balancer overview** end to end and draw the component diagram (forwarding rule → target proxy → URL map → backend service → backend) from memory: <https://cloud.google.com/load-balancing/docs/https>.
- Put the **whole OWASP CRS bundle in preview mode** on your test LB, replay a corpus of benign requests through it, and read the Cloud Armor logs to find which preconfigured rules would have false-positived on your traffic. This is the real-world WAF rollout workflow: <https://cloud.google.com/armor/docs/rule-tuning>.
- Configure a **Cloud DNS health-checked failover routing policy** so your hostname resolves to a primary LB IP and fails over to a secondary when a health check fails — the DNS-layer piece the capstone's multi-region story needs: <https://cloud.google.com/dns/docs/policies>.
- Stand up a **reCAPTCHA Enterprise** key, wire the score into a Cloud Armor `redirect`-to-challenge rule, and watch a low-score request get challenged: <https://cloud.google.com/armor/docs/recaptcha-bot-management>.
- Publish one of your services through a **Private Service Connect service attachment** and consume it from a second project's VPC via a PSC endpoint — the private mirror of everything else you built this week: <https://cloud.google.com/vpc/docs/private-service-connect>.

## Up next

Continue to **Week 09 — Pub/Sub and Dataflow (Apache Beam)** once you have torn the edge down cleanly and your peer has signed off on your midterm architecture review. Phase 2 is done: you can deploy compute (VM, GKE, Cloud Run), wire networking (VPC, NAT, LB), and protect the edge (Cloud Armor, CDN, IAP). Phase 3 turns the bytes those services move into truth — events into Pub/Sub, Pub/Sub into Dataflow, Dataflow into BigQuery. The edge you built this week is the front door the capstone's ingest service sits behind; you will not rebuild it, you will reuse it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
