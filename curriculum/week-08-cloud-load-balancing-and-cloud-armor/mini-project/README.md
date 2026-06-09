# Mini-Project — A Global L7 Edge Over Three Backends, and the Phase 1+2 Midterm Architecture Review

> Build a **global external Application Load Balancer** that fronts **three different backend types behind one hostname** — the Week 07 Cloud Run service (`/api/*`), a Week 06 GKE service via a standalone zonal NEG (`/app/*`), and a GCS bucket via a backend bucket (`/static/*`) — with **Cloud CDN** on the cacheable paths and a **Cloud Armor** policy on the dynamic ones. **Then** write the **Phase 1+2 midterm architecture review**: a five-page writeup of the entire system you have built from Week 01 through Week 08, with a monthly cost model at list price and a two-page exit plan, peer-reviewed by a cohort member. The edge is the build; the review is the assessment. Both ship this week. The teardown gate is non-negotiable.

This is the capstone of Phase 2 and it **compounds Weeks 06 and 07**: the GKE backend is the long-lived regional Standard cluster you built in Week 06, and the Cloud Run backend is the stateless service you built in Week 07. You are not building new backends; you are building the *edge* that unifies the ones you already have, and then stepping back to review the whole two-phase system as one architecture — which is exactly the midterm the assessment matrix weights at 10%.

**Estimated time:** ~13 hours (split across Friday, Saturday, and the Sunday review block in the suggested schedule). Roughly 8 hours on the edge, 4 on the writeup, 1 on the peer review.

---

## Part A — The build: one hostname, three backends, two protections

### What you will build

A `edge` Terraform module in your Week 04 `modules/` library, consumed by `envs/dev`, that provisions a single global external Application LB with a URL map that fans out by path:

| Path | Backend | NEG / backend type | Cloud CDN | Cloud Armor |
|------|---------|--------------------|-----------|-------------|
| `/api/*` | Week 07 Cloud Run service | serverless NEG | off (dynamic) | yes (rate limit + SQLi WAF) |
| `/app/*` | Week 06 GKE Service | standalone **zonal NEG** | off (dynamic) | yes (rate limit + SQLi WAF) |
| `/static/*` | GCS bucket | **backend bucket** | **on** (`CACHE_ALL_STATIC`) | no (static, public) |
| `/` (default) | a default backend (Cloud Run is fine) | serverless NEG | off | yes |

Concretely, the module provisions:

1. A reserved **global anycast IP** and a **Google-managed TLS certificate** for one hostname (a real domain you control, or `<ip>.sslip.io`).
2. A **serverless NEG** → the Week 07 Cloud Run service (redeploy from your Week 07 repo if torn down).
3. A **standalone zonal NEG** → the Week 06 GKE Service. You annotate the GKE Service for container-native LB (`cloud.google.com/neg: '{"exposed_ports": {"80":{"name":"app-neg"}}}'`), GKE creates the NEG, and you attach it to a backend service with a health check. (This is the container-native path from Lecture 1 §1.5 — the LB talks to pod IPs directly.)
4. A **GCS bucket** with a couple of static files and a **backend bucket** with Cloud CDN enabled.
5. A **URL map** with host rule + path matchers routing the four path classes above.
6. A **Cloud Armor security policy** (the Exercise 2 policy: per-IP `rate_based_ban` + `sqli-v33-stable` WAF + default allow) attached to the two **dynamic** backend services (`/api`, `/app`, default). Not attached to the static backend bucket (static public content does not need it, and a backend bucket cannot carry a policy the same way).
7. The **target HTTPS proxy** and **global forwarding rule** that tie it together.

### Repository layout (extends Week 04, compounds 06 + 07)

```
infra/
  modules/
    org-bootstrap/    # Week 01/04
    vpc/              # Week 03/04
    iam-baseline/     # Week 04
    compute/          # Week 05
    gke/              # Week 06   <-- the GKE backend lives here
    cloudrun/         # Week 07   <-- the Cloud Run backend lives here
    edge/             # <-- YOU BUILD THIS WEEK
      main.tf             #   global IP, cert, proxy, forwarding rule, URL map
      backends.tf         #   3 backend services + the backend bucket
      negs.tf             #   serverless NEG (Run) + reference to the GKE zonal NEG
      armor.tf            #   the Cloud Armor policy + attachments
      cdn.tf              #   backend bucket + GCS bucket + CDN config
      variables.tf        #   project_id, region, hostname, run_service,
                          #   gke_neg_name, gke_neg_zones, static_bucket
      outputs.tf          #   lb_ip, hostname, policy_name
      versions.tf         #   provider + version pins
      README.md           #   module docs: inputs, outputs, an example call
  envs/
    dev/
      edge.tf         # module "edge" { source = "../../modules/edge" ... }
k8s/
  app-service.yaml    # the Week 06 Service, annotated for a standalone NEG
MINIPROJECT.md        # Part A writeup + teardown evidence
ARCHITECTURE-REVIEW.md# Part B: the 5-page midterm review (see below)
```

### Rules

- **You may** reuse everything from the exercises and the challenge: the LB skeleton, the Armor policy, the serverless NEG. The mini-project is the *productionized, modularized, multi-backend* version of that work.
- **You may NOT** create any of it with `gcloud` by hand and "write the Terraform later." It goes through the `edge` module, through `envs/dev`, with a `terraform plan` you read before you `apply`. That is the Week 04 discipline and it is graded here.
- **You may NOT** front the static path with `FORCE_CACHE_ALL`. Use `CACHE_ALL_STATIC` (or `USE_ORIGIN_HEADERS` with correct `Cache-Control` on the objects). Caching a dynamic or private response is an automatic fail of the correctness criterion.
- **The Cloud Armor policy must be attached to the dynamic backends and demonstrably bite** (the same proofs as the challenge: a `hey` 429 and a SQLi 403, both in the logs).
- Target `terraform >= 1.9`, `google` provider `~> 6.0`. A clean `terraform validate` and a no-drift `terraform plan` before you call it done.
- Region `us-central1` for the regional pieces; the LB is global by definition. Everything pinned to stay in the free-trial region.

### Part A acceptance criteria

- [ ] One hostname, one anycast IP, `ACTIVE` managed cert, serves all three backends by path.
- [ ] `curl https://$HOST/api/<path>` hits Cloud Run (200); `curl https://$HOST/app/<path>` hits the GKE service (200); `curl https://$HOST/static/<file>` hits the bucket (200).
- [ ] The GKE backend is reached via a **standalone zonal NEG** (container-native — show the NEG and the backend service config).
- [ ] `/static/*` shows `cacheHit: True` in the logs; the dynamic paths never do.
- [ ] The Cloud Armor policy is attached to the dynamic backends and bites (429 under `hey`, 403 on SQLi, both logged at the right priorities).
- [ ] `terraform destroy` is clean; no orphaned global resources afterward.

---

## Part B — The Phase 1+2 Midterm Architecture Review

This is the assessment the syllabus weights at 10% of the course. You write a **five-page** architecture review (`ARCHITECTURE-REVIEW.md`, ~2,000–2,500 words plus diagrams and the cost table) of the **entire system you have built from Week 01 through Week 08**, and a cohort peer reviews it. This is the document a staff engineer would ask you to produce before signing off on a design, and the skill it builds — *describe a system you built, cost it honestly, and plan your exit from it* — is the headline skill of the whole course.

### What the system is (the thing you are reviewing)

By Week 08 you have built, across the phases:

- **Week 01:** an org/folder/project landing zone with billing budgets armed.
- **Week 02:** Workload Identity Federation for deploys; no key files.
- **Week 03:** a multi-region shared VPC with Cloud NAT, Private Google Access, hierarchical firewall.
- **Week 04:** a reusable Terraform module library with remote state in GCS.
- **Week 05:** a regional MIG behind an internal TCP LB.
- **Week 06:** a long-lived regional GKE Standard cluster with a spot node pool, Workload Identity, HPA, PDB.
- **Week 07:** a stateless Cloud Run service backed by Cloud SQL over Private Service Connect.
- **Week 08:** the global L7 edge over all of it — LB, CDN, Cloud Armor, IAP.

The review treats these as **one system**, not eight homeworks. Your job is to describe it as an architect would, find its weaknesses, cost it, and write its exit plan.

### Required sections

The five pages must contain, in this order:

**1. Architecture diagram and narrative (≈1 page).**
A diagram (Mermaid in the markdown, or a committed PNG) of the whole system — edge → compute → data → network → identity — with the request path traced through it. A paragraph per layer explaining what it does and why it is there. Use the five-layer edge framing from Lecture 1 for the edge portion.

**2. The decisions and their justifications (≈1 page).**
Five-to-seven decisions you made and *why*, each with the alternative you rejected. Examples: "GKE Standard over Autopilot for the long-lived cluster, because Weeks 12/13 need node-pool control"; "Cloud Run over GKE for the stateless API, because at our request volume scale-to-zero beats a always-on pod"; "global external Application LB over regional, because we want anycast and Cloud CDN"; "`rate_based_ban` keyed on `IP` not `XFF_IP`, because we sit directly behind the LB." Each decision names the trade-off, not just the choice.

**3. The cost model (≈1 page, with a table).**
A monthly cost estimate **at list price** for the running system, line by line, using the pricing pages from `resources.md` (re-checked — pricing moves). At minimum: the GKE node pool(s), the Cloud Run requests/instance-time, Cloud SQL, the LB forwarding rule + data processing, Cloud Armor (per-policy + per-rule + per-request), Cloud CDN egress, the reserved IP, the managed cert (free), and egress. State your assumptions (request volume, instance hours). Identify the **top three line items** and one optimization for each (e.g. committed-use discount on the GKE nodes, Cloud Run `min-instances` tuning, CDN to cut origin egress). This is the FinOps muscle the capstone's cost report exercises in full.

**4. Failure modes and what is not protected (≈0.5 page).**
For each layer of the edge and each compute tier, what happens when it fails, and what the system does *not* protect against. Use the Lecture 1 §1.8 protection matrix as the spine: "Cloud Armor does not stop a business-logic flaw"; "DNS failover is TTL-bound and coarse"; "a single-region GKE cluster does not survive a region loss." Honesty here is graded higher than optimism.

**5. The exit plan (≈1.5 pages, the hardest section).**
What it would take to move this workload **off GCP** — to AWS, or to self-hosted Kubernetes + an open-source edge (e.g. an Envoy/Nginx ingress + ModSecurity WAF + a CDN like Fastly/Cloudflare + cert-manager). For each GCP component, name the closest open-source or other-cloud equivalent and the *migration effort* (trivial / moderate / hard / re-architect). Be specific about lock-in: which choices are portable (Terraform, containers, FastAPI, SQL) and which are sticky (Cloud Armor CEL rules, IAP/BeyondCorp, the managed-cert + anycast-LB convenience, PSC). A good exit plan is honest that the *convenience* of the managed edge is the lock-in, and quantifies the labor to replace it. The course's whole "we name the open-source alternative every time" ethos lives in this section.

### Part B rules

- **Five pages.** Not three (you skipped something), not ten (you padded). The constraint is the skill — a staff engineer's review is tight.
- **The cost model uses real, current numbers** from the GCP pricing pages, with stated assumptions. A cost model with no assumptions is fiction.
- **The exit plan names specific replacements**, not "we'd use open source." "Replace Cloud Armor with an Nginx + ModSecurity (OWASP CRS) sidecar and lose the managed CEL ergonomics; ~2 engineer-weeks to port the rules and tune false positives" is the bar.
- **It must be peer-reviewed.** A cohort member reads it and fills in the review template below. You incorporate or rebut their feedback in a short changelog at the end of the document.

### The peer-review template (your reviewer fills this in)

```
PEER REVIEW — <author>'s Phase 1+2 architecture review
Reviewer: <name>    Date: <date>

1. Could you trace a request through the diagram without asking the author? (Y/N + note)
2. Is each decision justified against a named alternative? (which are weak?)
3. Cost model: are the assumptions stated and plausible? Top-3 line items correct?
   (flag any line item you think is off by >2x)
4. Failure modes: name one failure the author missed.
5. Exit plan: name one GCP component whose replacement effort the author
   under- or over-stated, and why.
6. The one thing this review most needs before a staff engineer would sign off:
```

---

## Grading rubric (both parts)

| Criterion | Weight | What earns full marks |
|-----------|-------:|-----------------------|
| **Part A — multi-backend edge works** | 30% | One hostname routes to Cloud Run, GKE (via zonal NEG), and GCS by path; cert `ACTIVE`; all three return 200. |
| **Part A — CDN + Armor proven** | 20% | `/static/*` shows `cacheHit: True`; the Armor policy bites (429 + 403) on the dynamic paths, both in the logs. |
| **Part A — IaC discipline** | 10% | Everything via the `edge` module + `envs/dev`; clean `validate` + no-drift `plan`; clean `destroy`. |
| **Part B — review completeness** | 20% | All five sections present, ~5 pages, diagram + narrative + decisions + cost + failures + exit. |
| **Part B — cost model + exit plan quality** | 15% | Real numbers with assumptions; top-3 line items + optimizations; exit plan names specific replacements with effort estimates. |
| **Part B — peer review incorporated** | 5% | A peer review is attached and the author responds to it in a changelog. |

A passing mini-project requires the edge to actually serve all three backends **and** the review to be five honest pages with a costed exit plan. A working edge with a hand-waved review fails the midterm; a beautiful review with a broken edge fails the build. Both ship.

---

## The teardown gate (non-negotiable)

The edge is not free. After you have captured every proof for Part A and your peer has reviewed Part B:

```bash
terraform destroy -var-file=envs/dev/dev.tfvars   # or your env's invocation
# Then confirm nothing is orphaned:
gcloud compute forwarding-rules list --global
gcloud compute addresses list --global
gcloud compute backend-services list --global
gcloud compute url-maps list
gcloud compute security-policies list
# All should be empty of this week's resources.
gsutil ls 2>/dev/null | grep -i static || echo "static bucket gone"
```

The Week 06 GKE cluster and Week 07 Cloud Run service may stay (Phase 3 uses them), but **the edge — LB, IP, cert, NEGs, policy, backend bucket — comes down.** A forgotten global forwarding rule with a reserved IP is the single most common "why is my free trial draining" surprise. Treat skipping the teardown as failing the week.

## What you take into Phase 3

You now have the full Phase 2 picture: compute (VM, GKE, Cloud Run), networking (VPC, NAT, internal + external LB), and edge protection (CDN, Cloud Armor, IAP). The `edge` module you wrote is the front door the **capstone's ingest service** sits behind — you will reuse it, not rebuild it. The architecture-review writeup is the first draft of the capstone's architecture document and the exit plan it requires. And the cost-modeling muscle you built in Part B is exactly the one Week 14 (FinOps) and the capstone cost report demand. Phase 3 turns the bytes these services move into truth: Pub/Sub, Dataflow, BigQuery, Spanner, Vertex AI. The front door is built. Now we fill the house.
