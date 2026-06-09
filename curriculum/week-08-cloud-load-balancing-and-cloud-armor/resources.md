# Week 8 — Resources

Every resource on this page is **free**. Google Cloud documentation is free and does not require an account. The Terraform provider and the Cloud Foundation Toolkit LB module are open-source on GitHub. The CEL language spec is open. No paywalled books are linked.

These docs change. Cloud Load Balancing was renamed and re-organized in 2023–2024 (the product is now "Application Load Balancer" / "Network Load Balancer" rather than the old "HTTP(S) LB" / "TCP/UDP LB" names), and Cloud Armor ships new preconfigured WAF rule versions periodically. If a page reads differently from this material, **trust the docs and open an issue** so we can update the week.

## Required reading (work it into your week)

- **External Application Load Balancer overview** — the canonical component diagram (forwarding rule → target proxy → URL map → backend service → backend) and the global-vs-regional split. Read it before Lecture 1:
  <https://cloud.google.com/load-balancing/docs/https>
- **Cloud Load Balancing overview — choosing a load balancer** — the decision matrix across Application / Network / Proxy LBs, internal vs. external, global vs. regional. This *is* the LB-selection lecture in table form:
  <https://cloud.google.com/load-balancing/docs/load-balancing-overview>
- **Network Endpoint Groups overview** — serverless, zonal, internet, and PSC NEGs and when each applies:
  <https://cloud.google.com/load-balancing/docs/negs>
- **Cloud Armor security policy overview** — the policy/rule/action model, the CEL match language, and the preconfigured WAF rules. Read it before Lecture 2:
  <https://cloud.google.com/armor/docs/security-policy-overview>
- **Cloud Armor rate limiting overview** — `throttle` vs. `rate_based_ban`, the `enforce_on_key` buckets, and the threshold/interval semantics:
  <https://cloud.google.com/armor/docs/rate-limiting-overview>

## The load-balancer layer

- **Serverless NEGs (Cloud Run / App Engine / Cloud Functions backends)** — how a serverless NEG attaches a Cloud Run service to a global LB:
  <https://cloud.google.com/load-balancing/docs/negs/serverless-neg-concepts>
- **Standalone zonal NEGs for GKE (container-native load balancing)** — attaching a GKE Service's pod IPs directly to a global LB via a standalone NEG, the path the mini-project uses:
  <https://cloud.google.com/kubernetes-engine/docs/how-to/standalone-neg>
- **Backend buckets (serving GCS through a global LB)** — the GCS-bucket backend the mini-project's `/static/*` path uses:
  <https://cloud.google.com/load-balancing/docs/backend-bucket>
- **Backend services overview** — health checks, balancing modes (`RATE`, `UTILIZATION`, `CONNECTION`), session affinity, and where Cloud CDN and the Cloud Armor policy attach:
  <https://cloud.google.com/load-balancing/docs/backend-service>
- **URL maps overview** — host rules, path matchers, and the routing that sends `/api/*` to Cloud Run and `/static/*` to a bucket:
  <https://cloud.google.com/load-balancing/docs/url-map-concepts>

## Cloud CDN

- **Cloud CDN overview** — the edge cache, the relationship to the backend service, and what is and is not cacheable:
  <https://cloud.google.com/cdn/docs/overview>
- **Cache modes** — `CACHE_ALL_STATIC`, `USE_ORIGIN_HEADERS`, `FORCE_CACHE_ALL`, and how each interacts with `Cache-Control`:
  <https://cloud.google.com/cdn/docs/caching>
- **Cache keys** — including/excluding host, path, query string, headers, and cookies from the cache key:
  <https://cloud.google.com/cdn/docs/caching#cache-keys>
- **Inspecting cache behaviour** — the `Age`, `Via`, and `X-Cache` response headers and the `cacheHit` / `cacheId` Cloud Logging fields:
  <https://cloud.google.com/cdn/docs/troubleshooting-steps>

## Cloud Armor — the engine, the WAF, and bots

- **Custom rules language reference (CEL for Cloud Armor)** — the request attributes (`request.headers`, `request.path`, `request.query`, `origin.ip`, `origin.region_code`), operators, and the `evaluatePreconfiguredExpr` / `inIpRange` functions. Keep this open while you write Lecture 2's rules:
  <https://cloud.google.com/armor/docs/rules-language-reference>
- **Preconfigured WAF rules (the OWASP CRS tuning page)** — the `sqli`, `xss`, `lfi`, `rce`, `scannerdetection`, `protocolattack` expression sets, sensitivity levels, and `opt_in`/`opt_out` rule-id overrides:
  <https://cloud.google.com/armor/docs/rule-tuning>
- **Rate-limiting how-to** — configuring `rate_limit_options`, the `enforce_on_key` choices (`IP`, `XFF_IP`, `HTTP_HEADER`, `HTTP_COOKIE`, `ALL`), and `ban_duration_sec`:
  <https://cloud.google.com/armor/docs/configure-rate-limiting>
- **reCAPTCHA Enterprise bot management with Cloud Armor** — surfacing `token.recaptcha_action.score` into CEL and the `redirect` action for a challenge page:
  <https://cloud.google.com/armor/docs/recaptcha-bot-management>
- **Cloud Armor request logging** — the `enforcedSecurityPolicy` log fields, `configuredAction`, `name`, `priority`, and how to find the rule that blocked a request:
  <https://cloud.google.com/armor/docs/request-logging>
- **Adaptive Protection (the ML attack-detection tier, named in Lecture 1, deferred to Week 14)**:
  <https://cloud.google.com/armor/docs/adaptive-protection-overview>

## Identity-Aware Proxy

- **IAP overview** — the BeyondCorp model, where IAP sits in the LB path, and the supported resource types:
  <https://cloud.google.com/iap/docs/concepts-overview>
- **Enabling IAP for a load-balanced backend** — the OAuth consent screen, the IAP-enabled backend service, and the `roles/iap.httpsResourceAccessor` grant:
  <https://cloud.google.com/iap/docs/enabling-compute-howto>
- **Securing your app with signed headers (verifying `X-Goog-IAP-JWT-Assertion`)** — the step Exercise 3 makes you implement; without it, IAP is bypassable:
  <https://cloud.google.com/iap/docs/signed-headers-howto>
- **Context-Aware Access** — the next step beyond group membership (device posture, IP, time-of-day), named here for the stretch goal:
  <https://cloud.google.com/context-aware-access/docs/overview>

## Private Service Connect

- **Private Service Connect overview** — endpoints (consume) vs. service attachments (publish), and where PSC fits relative to the public edge:
  <https://cloud.google.com/vpc/docs/private-service-connect>
- **Publishing a service via a PSC service attachment** — the path you use to make a Week 06/07 service consumable privately from another VPC:
  <https://cloud.google.com/vpc/docs/configure-private-service-connect-producer>

## Certificates and DNS

- **Google-managed SSL certificates** — provisioning, the DNS-authorization vs. load-balancer-authorization path, and the propagation wait:
  <https://cloud.google.com/load-balancing/docs/ssl-certificates/google-managed-certs>
- **Certificate Manager** — certificate maps for SNI across many hostnames (the scalable cert story):
  <https://cloud.google.com/certificate-manager/docs/overview>
- **Cloud DNS routing policies** — weighted, geo, and **health-checked failover** routing, the DNS-layer piece of the five-layer edge:
  <https://cloud.google.com/dns/docs/policies>

## Terraform & IaC

- **`terraform-google-modules/terraform-google-lb-http`** — the Cloud Foundation Toolkit module for the global external Application LB; the mini-project may use it or assemble the resources directly:
  <https://github.com/terraform-google-modules/terraform-google-lb-http>
- **`google_compute_global_forwarding_rule`, `google_compute_target_https_proxy`, `google_compute_url_map`, `google_compute_backend_service`, `google_compute_region_network_endpoint_group`** — the raw resources you assemble in Exercise 1. Start from the backend-service docs and follow the references:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_backend_service>
- **`google_compute_security_policy`** — the Cloud Armor policy resource, including the `rate_limit_options` and `preconfigured_waf_config` blocks used in Exercise 2:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_security_policy>
- **`google_iap_web_backend_service_iam_member`** — the IAM binding that gates an IAP-protected backend on a user/group, used in Exercise 3:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/iap_web_backend_service_iam>

## The CEL language itself

- **CEL specification (cel-spec)** — Cloud Armor's match language is Google's Common Expression Language. Reading the spec once tells you why `inIpRange()`, `.contains()`, and `&&`/`||` behave the way they do:
  <https://github.com/google/cel-spec>
- **CEL language definition (the human-readable grammar and stdlib)**:
  <https://github.com/google/cel-spec/blob/master/doc/langdef.md>

## The tools we use this week

- **`hey` — the HTTP load generator** — used to drive the rate-limit threshold in Exercise 2 and the challenge: `go install github.com/rakyll/hey@latest`:
  <https://github.com/rakyll/hey>
- **`curl`** — the malformed-request tool for the WAF test (`curl 'https://host/?q=1%20OR%201=1'`). Already on your machine.
- **`dig` / `nslookup`** — to confirm your hostname resolves to the LB's anycast IP before you wait on the managed cert.
- **`sslip.io` / `nip.io`** — wildcard DNS that maps `<ip>.sslip.io` to `<ip>`, so you can get a real hostname for a managed cert without owning a domain. The exercises show both paths.
- **`gcloud compute ssl-certificates describe`** — to watch a managed cert move from `PROVISIONING` to `ACTIVE`.

## Videos & talks (free, no signup)

- **Google Cloud Next — "What's new in Cloud Load Balancing" and "Protecting apps with Cloud Armor"** — every session lands on the Google Cloud Tech YouTube channel after the event. Watch a recent edge/Armor talk:
  <https://www.youtube.com/@googlecloudtech>
- **"BeyondCorp: A New Approach to Enterprise Security" (the original Google research papers)** — the architecture IAP implements. Read the first paper once to understand *why* IAP exists:
  <https://research.google/pubs/pub43231/>

## Open-source projects to read this week

You learn more from one hour reading a well-written Terraform module than from three hours of tutorials. Pick one and scroll through:

- **`terraform-google-modules/terraform-google-lb-http`** — read `main.tf` and see how it composes the forwarding rule, proxy, URL map, and backend service. The variable surface *is* the LB's configuration surface:
  <https://github.com/terraform-google-modules/terraform-google-lb-http/blob/main/main.tf>
- **`GoogleCloudPlatform/gcp-cloud-armor-example` and the `cloud-armor` Terraform module** — read a real, multi-rule Cloud Armor policy expressed in HCL:
  <https://github.com/GoogleCloudPlatform/terraform-google-cloud-armor>

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Forwarding rule** | The global anycast IP + port the LB listens on. The entry point. |
| **Target proxy** | Terminates TLS (target *HTTPS* proxy) and hands the request to the URL map. |
| **URL map** | The router: host rules + path matchers decide which backend service serves a request. |
| **Backend service** | The unit that owns health checks, balancing mode, Cloud CDN, and the Cloud Armor attachment. Points at one or more backends. |
| **NEG** | Network Endpoint Group. **Serverless** = Cloud Run/Functions; **zonal** = GKE pod IPs; **internet** = external origin; **PSC** = a published service. |
| **Backend bucket** | A GCS bucket attached to the URL map as a backend — for static assets, Cloud CDN-cached. |
| **Cloud CDN** | The edge cache toggled on a backend service. A cache hit never reaches your origin. |
| **Cloud Armor policy** | An ordered list of CEL rules attached to a backend service, evaluated at Google's edge. |
| **CEL** | Common Expression Language — the language a Cloud Armor `match` is written in. |
| **`evaluatePreconfiguredExpr`** | The CEL function that invokes a preconfigured OWASP rule set (e.g. `'sqli-v33-stable'`). |
| **`rate_based_ban`** | A rate-limit action that *temporarily blocks* an offending key after it exceeds the threshold, for `ban_duration_sec`. |
| **`throttle`** | A rate-limit action that returns 429 above the threshold but does not ban. |
| **`enforce_on_key`** | The bucket a rate limit counts against: `IP`, `XFF_IP`, `HTTP_HEADER`, `HTTP_COOKIE`, or `ALL`. |
| **IAP** | Identity-Aware Proxy — forces an OAuth login and an IAM check in the LB path, stamping `X-Goog-IAP-JWT-Assertion`. |
| **`X-Goog-IAP-JWT-Assertion`** | The signed header IAP adds; the backend must verify it or IAP is bypassable. |
| **PSC** | Private Service Connect — the private door (endpoint to consume, service attachment to publish), the mirror of the public LB. |
| **Managed certificate** | A Google-provisioned TLS cert for a hostname; needs the hostname to resolve to the LB IP first. |
| **Anycast IP** | One IP announced from many Google edge locations; the global LB's single front-door address. |

---

*If a link 404s, please open an issue so we can replace it.*
