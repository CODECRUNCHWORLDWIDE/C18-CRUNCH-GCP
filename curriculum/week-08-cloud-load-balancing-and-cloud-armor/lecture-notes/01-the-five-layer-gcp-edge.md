# Lecture 1 — The Five-Layer GCP Edge: DNS → Cloud Armor → Cloud CDN → LB → Backend, and What Each Layer Can and Cannot Protect

> **Reading time:** ~80 minutes. **Hands-on time:** ~40 minutes (you provision one global LB and watch a request pass through every layer).

This is the lecture that lets you walk into an architecture review, draw the GCP edge on a whiteboard, and answer the only question that matters: *"when a request comes in, what happens to it, in what order, and where would you stop an attack?"* Almost every edge decision a team makes — "should this be cached?", "where do I rate-limit?", "why is the WAF not catching this?", "why is my user not being asked to log in?" — is really a question about **which of five layers owns the problem**. Get the layers and their ordering wrong and you put a control where it cannot work. Get them right and the edge becomes a pipeline you can reason about one stage at a time.

## 1.1 — The edge is a pipeline, and order is everything

A request to a GCP-fronted service passes through five layers, in this fixed order, outside-in:

```text
            ┌─────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────────┐   ┌──────────┐
 client ──▶ │  DNS    │──▶│  Cloud Armor │──▶│  Cloud CDN │──▶│ Load Balancer│──▶│ backend  │
            │ (name → │   │ (edge WAF +  │   │ (edge      │   │ (TLS term,   │   │ (Run,    │
            │ anycast │   │  rate limit) │   │  cache)    │   │  URL map,    │   │  GKE,    │
            │  IP)    │   │              │   │            │   │  routing)    │   │  GCS,…)  │
            └─────────┘   └──────────────┘   └────────────┘   └──────────────┘   └──────────┘
```

The thing to fix in your head before anything else: **these are not five products you bolt together arbitrarily — they are stages a packet visits in order.** DNS happens first because the client needs an IP before it can connect. Cloud Armor and Cloud CDN both run *at Google's edge*, before your origin is involved, which is why they can stop or serve a request without your backend ever waking up. The load balancer's data plane is also at the edge, but it is the stage that terminates TLS, consults the URL map, and decides which backend gets the request. The backend is your code.

A subtlety that trips people up: **Cloud Armor and Cloud CDN are not separate boxes in the path — they are features attached to the *backend service* inside the load balancer.** Conceptually they sit "before" the backend, and Google evaluates them at the edge, but in Terraform and in the console you enable Cloud CDN on the backend service (`enable_cdn = true`) and you attach a Cloud Armor policy to the backend service (`security_policy = ...`). The pipeline diagram is the *logical* order a request is processed in; the *configuration* hangs off the backend service. Holding both pictures at once — logical pipeline, physical config-on-backend-service — is the senior mental model.

The order has consequences you must be able to recite:

- **Cloud Armor runs before the cache.** A request blocked by Cloud Armor never reaches Cloud CDN, never reaches the LB routing, never reaches your origin. This is why Cloud Armor is your cheapest defense: a `deny(403)` at the edge costs you almost nothing.
- **Cloud CDN runs before the backend.** A cache *hit* is served from the edge; your backend never sees it. This is why a CDN in front of cacheable content is your cheapest scaling lever: traffic you never pay to compute.
- **The LB routes after the cache miss.** Only a request that is allowed (passed Armor) and not cached (missed CDN) reaches the URL map, which picks a backend service, which picks a backend, which is your code.

## 1.2 — Layer 1: DNS (Cloud DNS)

DNS is the layer everyone forgets is a layer. The client has a hostname (`api.example.com`); it needs an IP. Cloud DNS is Google's authoritative DNS service, and the IP it returns for a global external Application LB is an **anycast IP**: a single address announced from many of Google's ~180+ edge locations simultaneously, so the client's packets enter Google's network at the *nearest* edge and ride Google's backbone the rest of the way. This is why a global LB feels fast from everywhere — the TLS handshake terminates at an edge near the user, not at your backend's region.

What DNS *can* protect:

- **Failover.** Cloud DNS routing policies can be **health-checked**: you point a record at a primary IP and a secondary IP, attach a health check, and DNS serves the secondary when the primary is unhealthy. This is the capstone's multi-region failover seam. (Note the catch every senior engineer knows: DNS failover is gated by TTL and resolver caching — a 300-second TTL means up to five minutes of clients stuck on the dead IP. DNS is *coarse* failover.)
- **Geo / weighted routing.** Send EU users to an EU IP, US users to a US IP; or split traffic 90/10 for a canary. These are routing policies, not load balancing — DNS hands out IPs, it does not see requests.

What DNS *cannot* protect:

- **It cannot rate-limit, inspect payloads, or block anything.** DNS hands out an IP and is done. By the time the abusive request arrives, DNS is no longer in the path. Anyone who tells you to "block the attacker in DNS" is confusing DNS with the firewall.
- **It cannot terminate TLS or see the HTTP request.** DNS operates below HTTP entirely.

The one DNS gotcha for this week: a **Google-managed TLS certificate will not provision until the hostname resolves to the LB's IP.** Google validates that you control the name by checking that it points at the LB (load-balancer authorization) or by a DNS TXT record (DNS authorization). So the sequence is always: reserve the IP → create the LB → create the DNS A record → *then* the managed cert moves from `PROVISIONING` to `ACTIVE` (which can take 10–60 minutes). If your cert is stuck in `PROVISIONING`, the first thing to check is `dig +short api.example.com` against the LB IP.

### DNS health-checked failover, in detail

The capstone needs multi-region failover, and the coarse, DNS-level half of that story is a Cloud DNS **routing policy** with a health check. The mechanism:

- You create a routing policy on the A record with a **primary** target (the LB IP in `us-central1`) and a **backup** target (the LB IP in `us-east1`), plus a **health check** against the primary.
- While the primary's health check passes, Cloud DNS answers queries with the primary IP.
- When the primary fails the health check, Cloud DNS starts answering with the backup IP. New resolutions go to the standby region.

The two properties you must state in an architecture review:

1. **It is coarse, because of TTL and resolver caching.** A client (or its resolver) that cached the primary IP under a 300-second TTL keeps using the dead primary for up to five minutes after the failover decision. You can lower the TTL (30–60s) to tighten this, at the cost of more DNS queries. DNS failover is "minutes," not "seconds" — it is a *region-loss* tool, not a *request-level* one.
2. **It is independent of the LB's own failover.** A single global LB already fails over *between backends* (an unhealthy Cloud Run region, an unhealthy GKE zone) automatically and instantly, within its anycast footprint. DNS failover is for the case where the *whole LB or whole region* is gone — a strictly bigger blast radius. Most systems lean on the LB's intra-region health and reserve DNS failover for true region loss.

The capstone wires this; this week you only need to know it is the DNS layer's one real protective capability and what its TTL-bound coarseness costs.

## 1.3 — Layer 2: Cloud Armor (the edge security policy)

Cloud Armor is a security policy — an ordered list of rules — attached to a backend service and evaluated **at Google's edge, before the cache and before your backend.** Each rule is a CEL `match` expression and an `action`. Lecture 2 is Cloud Armor in full; here we place it in the pipeline.

What Cloud Armor *can* protect:

- **Volumetric abuse, via rate limiting.** "More than 100 requests in 60 seconds from one source IP → 429 or temporary ban." This is the single most useful edge control for a small service, because it turns "someone is hammering my `/login`" from an outage into a non-event.
- **Known-bad payloads, via the preconfigured WAF rules.** SQLi, XSS, LFI, RCE, scanner signatures — the OWASP Core Rule Set, wrapped in `evaluatePreconfiguredExpr`. A request whose query string contains `1' OR '1'='1` gets a 403 at the edge.
- **Geography and IP reputation.** "Deny requests from these country codes" (`origin.region_code`), "allow only this office CIDR" (`inIpRange(origin.ip, '203.0.113.0/24')`), "block this known-bad /24."
- **L3/L4 volumetric DDoS** (with the always-on protection that comes with the global external LB; the ML-driven Adaptive Protection is a paid tier we name and defer to Week 14).

What Cloud Armor *cannot* protect:

- **It cannot cache.** Armor blocks or allows; it does not serve. Caching is the next layer.
- **It cannot authenticate a user.** Armor knows the request's IP, headers, and payload — not *who* the human is. A rate limit does not stop an authenticated abuser with a valid session who stays under the threshold. User identity is IAP's job (§1.6).
- **It cannot catch a zero-day in your application logic.** A preconfigured WAF rule catches *known* attack shapes. A business-logic flaw — "if I pass `account_id=other_user` I see their data" — looks like a perfectly well-formed request and sails straight through. The WAF is a coarse filter, not a substitute for secure code.
- **It cannot inspect an encrypted payload it cannot terminate.** Armor on an Application LB sees the decrypted HTTP request (the LB terminated TLS). Armor on a *proxy* LB for raw TLS passthrough sees far less. Match Armor's capability to the LB type.

## 1.4 — Layer 3: Cloud CDN (the edge cache)

Cloud CDN is a toggle on a backend service (`enable_cdn = true`) that caches cacheable responses at Google's edge. A cache *hit* is served from the edge POP nearest the user; your backend never sees the request. Lecture-level detail you must know:

- **Cache modes.** `USE_ORIGIN_HEADERS` (cache exactly what your `Cache-Control` headers say — the honest, explicit mode), `CACHE_ALL_STATIC` (cache static content types even without origin headers, with a default TTL), and `FORCE_CACHE_ALL` (cache *everything*, ignoring origin headers — a foot-gun that will happily cache a logged-in user's account page and serve it to the next person; never use it on dynamic or authenticated content).
- **Cache keys.** By default the key is scheme + host + path + query. You can include or exclude the query string, specific headers, and cookies. Getting the cache key wrong is how you serve user A's content to user B.
- **The `Age`, `Via`, and `X-Cache` headers** tell you whether a response was a hit. The Cloud Logging field `httpRequest.cacheHit = true` is the authoritative signal.

What Cloud CDN *can* protect:

- **Your backend's capacity and your wallet.** Every cache hit is a request you do not compute and (on Cloud Run) do not pay an instance-second for. For a content-heavy site, CDN is the difference between 3 origin instances and 30.
- **Latency.** Cached bytes are served from an edge near the user.
- **A thundering herd, partially.** Request collapsing means many simultaneous misses for the same object hit your origin once, not N times.

What Cloud CDN *cannot* protect:

- **It cannot cache authenticated or `private` responses safely.** A response with `Cache-Control: private`, `no-store`, or a `Set-Cookie` is (correctly) not cached in shared mode. If your content is per-user, the CDN gives you nothing on those paths — and if you force it to cache them, you create a data-leak incident.
- **It cannot block an attack.** CDN serves or fetches; it does not deny. (A cache hit does *incidentally* absorb a flood of identical requests, but that is a side effect, not a security control.)
- **It cannot fix a wrong cache key.** Garbage key in, garbage hits out.

The senior framing: **Cloud Armor is the security layer, Cloud CDN is the performance layer, and they are independent.** You can have one without the other. Most edges want both: Armor first (stop the bad), CDN second (serve the cacheable), backend last (compute the rest).

### The cache key is the part that bites you

A CDN's correctness lives entirely in the **cache key** — the tuple the CDN uses to decide whether two requests are "the same object." By default the key is `scheme + host + path + full query string`. The two ways this goes wrong in production:

- **Key too narrow → you serve the wrong thing.** If your content varies by a header (say `Accept-Language`) or a cookie but those are *not* in the cache key, the CDN serves the first-cached variant to everyone. The English page gets served to the German user; worse, if you accidentally cache a per-user response, user A's data is served to user B. The fix is to either *include* the varying dimension in the key or *not cache* the varying response.
- **Key too wide → your hit rate collapses.** If you include the full query string and your URLs carry a unique tracking parameter (`?utm_source=...&fbclid=...`), every request is a distinct cache key, every request misses, and the CDN does nothing but add a hop. The fix is to *exclude* the irrelevant query parameters from the key (`cache_key_policy { query_string_blacklist = [...] }` or an allowlist).

The cache-key controls (`include_host`, `include_protocol`, `include_query_string`, the query allow/deny lists, and named headers/cookies) are on the backend service's `cdn_policy`. Getting them right is the difference between a CDN that cuts origin load 90% and one that does nothing.

### Signed URLs and signed cookies

Cloud CDN can serve *time-limited, authenticated* content without your origin being in the path on every request, via **signed URLs** and **signed cookies**. You configure a signing key on the backend service; your origin (which *does* authenticate the user once) hands the client a URL with a signature and an expiry; the CDN validates the signature at the edge and serves the cached bytes only if it is valid and unexpired. This is how you serve, say, a paywalled video segment from the edge: the origin authorizes once and issues a signed URL, the CDN does the rest. It is the one way "authenticated content" and "CDN cache" coexist — the authentication moves to a signature the edge can check, not a session the origin must validate. We do not build it this week (it needs a signing flow beyond a Terraform-and-`curl` lab) but you must know it exists, because "CDN cannot cache authenticated content" has exactly this exception.

## 1.5 — Layer 4: The Load Balancer (the data plane that terminates and routes)

Now the request has survived DNS, been allowed by Armor, and missed the cache. The load balancer is the layer that terminates TLS, consults the URL map, and routes to a backend. Its anatomy, which you will assemble by hand in Exercise 1, is a four-link chain:

```text
global forwarding rule  →  target HTTPS proxy  →  URL map  →  backend service  →  backend (NEG / IG / bucket)
   (anycast IP:443)         (terminates TLS,        (routes      (health checks,      (Cloud Run via
                             holds the certs)        by host      CDN toggle,           serverless NEG,
                                                     + path)      Armor policy)         GKE via zonal NEG,
                                                                                        GCS via backend bucket)
```

- The **forwarding rule** binds the anycast IP and port (443 for HTTPS).
- The **target HTTPS proxy** terminates TLS (it holds the SSL certificates) and forwards the now-plaintext HTTP request to the URL map.
- The **URL map** is the router: a default service plus host rules and path matchers. `api.example.com/api/*` → the Cloud Run backend service; `api.example.com/static/*` → the GCS backend bucket; everything else → a default. This is how *one hostname and one IP* fan out to three different backend types.
- The **backend service** is the unit that owns the health check, the balancing mode, session affinity, the **Cloud CDN toggle**, and the **Cloud Armor policy attachment**. It points at one or more backends.
- The **backend** is the thing that runs your code: a serverless NEG (Cloud Run), a zonal NEG (GKE pods), an instance-group backend (a MIG), or a backend bucket (GCS).

### Choosing the load balancer

This is the matrix you will be quizzed on. GCP has, broadly, four load-balancer shapes:

| LB | Layer | Scope | Use it for | Cloud CDN? | Cloud Armor? |
|----|-------|-------|------------|------------|--------------|
| **Global external Application LB** | L7 (HTTP/S) | Global (anycast) | Public web/API serving; the workhorse of this week | Yes | Yes |
| **Regional external/internal Application LB** | L7 (HTTP/S) | Regional | Regional or internal HTTP apps; internal microservices | No (regional has no Cloud CDN) | Regional Armor |
| **Global/regional TCP or SSL Proxy LB** | L4 (proxy) | Global/regional | Non-HTTP TLS (e.g. a custom protocol over TLS), or raw TCP that still wants a Google-terminated, anycast front | No | Limited |
| **Passthrough Network LB** | L4 (passthrough) | Regional | Raw TCP/UDP where you must preserve the client source IP and want no proxy in the path (e.g. the Week 05 internal TCP LB) | No | No |

The decision tree, top to bottom:

1. **Is it HTTP or HTTPS?** If yes, you almost certainly want an **Application LB** (L7) — it gives you URL-based routing, Cloud CDN, and full Cloud Armor.
2. **Public or internal?** Public → global external Application LB. Internal-only (service-to-service inside the VPC) → regional internal Application LB.
3. **Not HTTP?** A TLS-wrapped custom protocol → **SSL Proxy LB**. Raw TCP/UDP that needs the real client IP and no proxy → **passthrough Network LB** (the Week 05 case).
4. **Need global anycast and Cloud CDN?** Only the *global* Application LB gives you both. Regional LBs are regional.

For everything in this week — fronting Cloud Run, GKE, and GCS for public HTTP — the answer is the **global external Application LB**, every time. The other rows exist so you can defend *not* using it when the protocol or scope is wrong.

### NEGs: how the backend service finds your code

A backend service does not point at "Cloud Run." It points at a **Network Endpoint Group**, and the NEG type tells the LB how to reach the endpoints:

- **Serverless NEG** — wraps a Cloud Run service (or App Engine / Cloud Functions). No health check, no balancing mode; Google routes to the serverless platform. This is how Exercise 1 attaches the Week 07 Cloud Run service.
- **Zonal NEG** — a list of `IP:port` endpoints that are **pod IPs** in a GKE cluster. This is *container-native* load balancing: the LB sends traffic straight to the pods, skipping the kube-proxy hop. The mini-project attaches the Week 06 GKE service this way (a standalone NEG).
- **Internet NEG** — an external origin (an on-prem server, a service in another cloud) reachable by IP or FQDN. Lets a GCP LB front a non-GCP backend.
- **PSC NEG** — points at a Private Service Connect service attachment, so the LB reaches a privately-published service. The bridge between the public edge and §1.7's private door.
- **Instance-group backend** (not a NEG) — a managed instance group of VMs, the Week 05 shape, attached directly.

The senior point: **the NEG abstraction is why one URL map can route to Cloud Run, GKE, and GCS at once.** Each path matcher targets a backend service; each backend service targets the NEG (or bucket) that knows how to reach that backend type. The LB does not care that one backend is serverless and another is a pod — the NEG layer hides the difference.

## 1.6 — Layer 5 (and a half): the backend, and where identity lives

The backend is your code: the Cloud Run service from Week 07, a GKE Service from Week 06, a MIG from Week 05, or a GCS bucket. The pipeline has done its job — the request that reaches your backend is one that passed Armor, missed the cache, and matched a route.

But there is a control that lives *between the LB and the backend* and is neither network nor cache: **Identity-Aware Proxy.** IAP intercepts the request inside the LB's path, forces an OAuth login against Google identities, checks the requester against an IAM policy on the backend service (a user, a Google group, or a service account holding `roles/iap.httpsResourceAccessor`), and only then forwards the request — stamping a signed `X-Goog-IAP-JWT-Assertion` header. This is BeyondCorp: zero-trust access to an internal app with no VPN, no bastion, no brittle IP allowlist.

What IAP *can* protect:

- **User-level access to internal apps.** "Only members of `eng-admins@example.com` can reach the admin dashboard." Group membership is checked at the edge, on every request.
- **Defense against credential-stuffing and unauthenticated probing** of internal tools, because the tool never sees an unauthenticated request.

What IAP *cannot* protect:

- **Itself, if you do not verify the signed header.** This is the one rule juniors miss: IAP adds `X-Goog-IAP-JWT-Assertion`, but if an attacker can reach your backend *directly* (bypassing the LB), they reach it with no IAP check at all. The backend **must** (a) only accept traffic from the LB, and (b) verify the IAP JWT's signature and audience on every request. Exercise 3 makes you implement the verification; without it, IAP is theater.
- **Authorization inside the app.** IAP says "this is Alice from `eng-admins`." Whether Alice may delete *this specific* record is your application's authorization logic, not IAP's.

## 1.7 — The private mirror: Private Service Connect

Everything above is the *public* edge. Many production systems also have a *private* door: a service that other VPCs (other teams, other projects, a partner) consume without ever touching the public internet. That is **Private Service Connect**:

- A **PSC service attachment** *publishes* your service: you put your service behind an internal LB, expose it as a service attachment, and a consumer in another VPC creates a **PSC endpoint** — a private IP in *their* VPC that tunnels to *your* service over Google's backbone. No VPC peering, no public IP, no overlapping-CIDR headaches.
- A **PSC endpoint** *consumes* a published service (including Google APIs, the `private.googleapis.com` path from Week 03, and managed services like the Cloud SQL instance you reached over PSC in Week 07).

Where PSC fits the five-layer model: **PSC is the private analog of the forwarding rule.** It is the entry point, but on the private network instead of the anycast public IP. A service can have both: a public global LB for external users and a PSC service attachment for internal/partner consumers, each with its own security posture. You front the public door with Cloud Armor; you gate the private door with VPC firewall rules and the consumer-allowlist on the service attachment. We go deep on PSC in Week 11 (databases) and Week 14 (VPC Service Controls); this week you need to know it exists and where it sits.

### A worked PSC vs. public-LB comparison

Make it concrete. You run an internal billing API that two consumers need: your own customer-facing web app (public, on the internet) and a partner's batch system (in *their* GCP project, in *their* VPC). Two doors, two postures:

- **The public door (for nothing here, actually).** The billing API is internal-only; it has *no* public door. If a junior engineer "just put it behind the global LB with Cloud Armor," they would have exposed an internal financial API to the entire internet and trusted a WAF to keep attackers out. Wrong layer, wrong door.
- **The private door for your own app.** Your customer-facing web app is public (it has the global LB + Armor), but it calls the billing API *internally* — same VPC or via the Week 03 shared VPC, over a regional internal Application LB. No public IP for billing.
- **The private door for the partner.** The partner is in a different org's VPC; you cannot just give them an internal IP on your network. You publish the billing API as a **PSC service attachment**: you put it behind an internal LB, expose a service attachment, and explicitly allowlist the partner's project. The partner creates a **PSC endpoint** — a private IP *in their VPC* — that tunnels to your service over Google's backbone. No public exposure, no VPC peering (which would force non-overlapping CIDRs and expose far more than one service), no shared trust domain.

The lesson the comparison teaches: **"how do consumers reach this service" is a layer-and-door decision, and the public global LB is the right answer for exactly one case — public internet users.** Internal consumers use an internal LB; cross-org consumers use PSC. Reaching for the public LB by reflex is how internal services end up on the internet. The architecture review at the end of this week should classify *every* service you have built by which door it belongs behind.

### The regional internal Application LB, briefly

The "internal door for your own app" above uses the **regional internal Application LB** — the L7 internal cousin of this week's global external one. It has the same chain shape (forwarding rule → target proxy → URL map → backend service → backend) but with `load_balancing_scheme = "INTERNAL_MANAGED"`, a *regional* internal IP from one of your VPC subnets, and no public exposure. It does HTTP routing and *regional* Cloud Armor, but **no Cloud CDN** (caching is a public-edge concern; internal service-to-service traffic does not cache). You use it for the microservice mesh inside the VPC: service A calls service B through an internal LB that health-checks B's backends and spreads load, all on private IPs. The Week 05 internal *TCP* LB was the L4 version of this idea; the internal Application LB is the L7 version, for when you want path routing and host-based virtual services between internal services. We name it here so the LB matrix in §1.5 has a concrete internal-L7 anchor; the mini-project's `/app` path could, in a larger design, route through one of these to reach a fleet of internal services rather than a single GKE Service.

## 1.7a — TLS termination and certificates: where the handshake actually happens

The five-layer model glosses one thing worth pulling apart, because it is the source of more "why is my LB returning a cert error" tickets than anything else: **where TLS terminates, and what cert it uses.**

On a global external Application LB, TLS terminates at the **target HTTPS proxy**, which lives at Google's edge — the same Frankfurt POP that ran Cloud Armor in the narration above. The proxy holds one or more SSL certificates. The handshake the client does is with Google's edge, not with your backend; from the proxy onward, Google re-encrypts (or not) on the hop to your backend depending on the backend service's protocol. For a serverless NEG (Cloud Run), that hop rides Google's network and is encrypted by the platform. The practical consequence: **your backend never sees the client's TLS handshake** and never needs the public certificate — Cloud Run answers plain HTTP on `:8080` and the edge handles all the public TLS. This is why the Exercise 1 origin has no cert config at all.

There are three ways to put a certificate on the proxy:

- **Google-managed certificate** (`google_compute_managed_ssl_certificate`). Google provisions and *auto-renews* a cert for a hostname, for free. The catch you already know: it will not move from `PROVISIONING` to `ACTIVE` until the hostname resolves to the LB's IP (load-balancer authorization) or you complete a DNS TXT challenge (DNS authorization, via Certificate Manager). This is the right default — no renewal cron, no expiry pages.
- **Self-managed certificate** (`google_compute_ssl_certificate`). You bring your own cert and private key (from your CA, or an ACME client). You own renewal. Use this only when you need a CA Google does not offer, a wildcard with specific constraints, or a cert pinned for compliance.
- **Certificate Manager with a certificate map.** For many hostnames behind one LB, a managed cert per host does not scale (there is a per-proxy cert limit). Certificate Manager lets you attach a *certificate map* to the proxy, with map entries selecting a cert per SNI hostname. This is the scalable cert story; you reach for it when you front dozens of domains.

The senior framing: **the managed cert is one of the stickiest conveniences in the whole edge.** Free auto-renewing TLS for any hostname that resolves to your LB is genuinely excellent, and it is exactly the kind of thing your exit plan (mini-project Part B) has to account for — replacing it means standing up `cert-manager` or an ACME client and owning renewal yourself. Convenience is the lock-in.

## 1.7b — Assembling the chain: a worked mental walkthrough

You will build the four-link chain in Exercise 1 in Terraform; here is the *reasoning* order, which is the reverse of the request order, because each link references the one "downstream" of it. Build it backend-first:

1. **Start at the backend.** You have a thing that runs code: a Cloud Run service, a GKE Service, a MIG, or a bucket. Nothing to create here — it already exists from Weeks 05/06/07.
2. **Wrap it in a NEG (or point at a bucket).** A serverless NEG names the Cloud Run service; a zonal NEG is created by GKE when you annotate the Service; a backend bucket names the GCS bucket. The NEG is the adapter between "your backend" and "something the LB can attach."
3. **Create the backend service** and attach the NEG. This is where the interesting config lives: the health check (not for serverless NEGs — Google health-checks the platform), the balancing mode, **`enable_cdn`**, and the **`security_policy`** (the Cloud Armor attachment, added in Exercise 2). One backend service per backend type.
4. **Create the URL map** and set its `default_service` to a backend service, plus `host_rule` + `path_matcher` blocks to route `/api/*`, `/app/*`, `/static/*` to their respective backend services. The URL map is the only place the *routing* lives.
5. **Create the target HTTPS proxy**, pointing at the URL map and listing the SSL certificate(s). This is the TLS-terminating link.
6. **Create the global forwarding rule**, binding the reserved anycast IP and `:443` to the proxy. This is the front door — the IP your DNS A record points at.
7. **Reserve the global address first** (it has no dependencies) and create the **DNS record** pointing at it, so the managed cert can authorize.

Notice the dependency chain runs *downstream-to-upstream*: the forwarding rule needs the proxy, the proxy needs the URL map and cert, the URL map needs the backend services, the backend services need the NEGs. Terraform's dependency graph builds them in the right order automatically *if* you reference each resource's `.id` in the next — which is why Exercise 1's solution wires `google_compute_target_https_proxy.edge.url_map = google_compute_url_map.edge.id` rather than hard-coding a name. Get the references right and `terraform apply` builds the whole chain in one pass (minus the cert wait).

A common assembly mistake to inoculate against now: **mixing load-balancing schemes.** Every resource in the chain must agree on `EXTERNAL_MANAGED` (the modern global external Application LB). If the backend service is `EXTERNAL_MANAGED` but the forwarding rule is `EXTERNAL` (the classic LB), the apply fails with a scheme-mismatch error that does not name the real problem. When Exercise 1 errors on apply, the scheme is the first thing to check.

## 1.7c — Inside the backend service: health checks, balancing modes, and affinity

The backend service is the most configuration-dense object in the chain, and three of its knobs decide how your traffic actually behaves. You will set them in Exercise 1 and the mini-project, so understand what each does.

**Health checks.** A backend service (for instance-group and zonal-NEG backends) attaches a health check — an HTTP, HTTPS, TCP, or gRPC probe Google runs against each endpoint from its distributed health-checking infrastructure. An endpoint that fails the check is taken out of rotation; traffic only goes to healthy endpoints. The two mistakes here: (1) pointing the health check at a path that requires auth (so every endpoint reports unhealthy and the LB serves nothing — this is the IAP-vs-health-check trap that makes Exercise 3 exempt `/healthz` from the IAP middleware), and (2) a health check more aggressive than the backend's startup time (so a slow-booting pod is killed before it is ready). **Serverless NEGs (Cloud Run) have no health check** — Google health-checks the serverless platform itself, which is why the Exercise 1 backend service has no health-check block.

**Balancing mode.** For instance-group and zonal-NEG backends, the balancing mode decides *when a backend is "full"* and traffic spills to the next: `RATE` (requests per second per endpoint — the right mode for a stateless HTTP service where each request costs roughly the same), `UTILIZATION` (CPU utilization of the backend instances — for heterogeneous request costs), or `CONNECTION` (concurrent connections — for long-lived connections like websockets). Pick `RATE` for the GKE backend in the mini-project; it is the honest mode for a FastAPI service. Serverless NEGs do not expose a balancing mode (the platform manages it).

**Session affinity.** By default the LB spreads requests across endpoints with no stickiness, which is correct for a stateless service. If your backend holds per-session state (it should not, but legacy ones do), session affinity (`CLIENT_IP`, `GENERATED_COOKIE`, `HEADER_FIELD`) pins a client to one backend. The senior note: **session affinity is a smell.** It defeats even load distribution and complicates failover. The Week 06/07 services are stateless precisely so you never need it; reach for it only to nurse a legacy backend, and write a ticket to remove the state.

These three knobs are why the backend service, not the URL map or the proxy, is "where the interesting config lives." The URL map routes; the proxy terminates TLS; the **backend service decides health, distribution, caching, and security** — it is the brain of the chain.

## 1.7d — Why "global" actually matters: anycast, proximity, and the backbone

It is worth being precise about *why* the global external Application LB is the workhorse and not just a regional LB with extra steps, because the reason is a real performance property you can measure and defend in the architecture review.

A **regional** LB has a regional IP; clients connect to that region no matter where they are. A user in Sydney hitting a `us-central1` regional LB does a TCP+TLS handshake across the Pacific — three round trips of ~150ms each before the first byte of the request even leaves their laptop. That is ~450ms of latency you pay on *every cold connection*, entirely in the network, before your code runs.

A **global** LB has a single **anycast** IP announced from Google's ~180+ edge POPs. The Sydney user's packets enter Google's network at the *Sydney* edge (a few milliseconds away), and the TCP+TLS handshake terminates *there*. From the Sydney edge, the request rides **Google's private backbone** to your `us-central1` backend — which is faster and more reliable than the public internet, and, crucially, the handshake latency was paid against the nearby edge, not the distant backend. The user feels a local connection to a remote service. This is the single biggest reason a global LB "feels fast from everywhere," and it is why Cloud CDN (which serves cache hits *from that same nearby edge*) compounds so well with it.

The corollary for the cost model: a global LB's data-processing charge and the backbone are part of what you pay for, and they are part of what the exit plan has to replace. Reproducing anycast + a global backbone yourself is not a weekend project — it is the reason CDN/edge vendors exist. Name that in Part B.

## 1.8 — The protection matrix (memorize this)

This is the single table the quiz draws from. For each layer, what it stops and what passes through:

| Layer | Stops / does | Cannot stop / does not do |
|-------|--------------|---------------------------|
| **DNS** | Resolves name → anycast IP; coarse failover (health-checked policy); geo/weighted IP routing | Cannot rate-limit, inspect, block, or see the HTTP request at all |
| **Cloud Armor** | Rate-limits per key; blocks known-bad payloads (preconfigured WAF); geo/IP allow-deny; L3/L4 DDoS | Cannot cache; cannot authenticate a *user*; cannot catch a business-logic flaw or a valid-looking abusive request |
| **Cloud CDN** | Serves cacheable bytes from the edge; absorbs identical-request floods; cuts origin cost & latency | Cannot block anything; cannot cache authenticated/`private` responses safely; cannot fix a bad cache key |
| **Load Balancer** | Terminates TLS; routes by host/path; spreads load; health-checks backends | Cannot decide *who* a user is; cannot inspect payloads for attacks (that's Armor) |
| **IAP (LB↔backend)** | Forces login; checks group/user IAM on every request; stamps a signed identity header | Cannot protect a directly-reachable backend; cannot do in-app authorization; useless if the JWT is unverified |
| **Backend** | Runs your code; enforces in-app authorization | Should assume everything in front of it can fail or be bypassed; verify the IAP JWT, validate every input |

The discipline this table encodes: **put each control at the layer that owns it.** Rate limit in Armor, not in your app (your app should never see the flood). Cache in CDN, not in your app (do not hand-roll a cache when the edge has one). Authenticate in IAP for internal apps (do not reinvent OAuth in every service). Validate input in the backend (the WAF is a filter, not a guarantee). When a request misbehaves, the matrix tells you which layer should have caught it — and that is how you debug an edge.

## 1.8a — The cost shape of the edge

Because the mini-project makes you cost this system, internalize the *shape* of the edge bill now — not the exact numbers (they move; re-check the pricing pages), but which line items dominate and which are rounding error.

- **The reserved global IP** is free *while attached to a forwarding rule* and billed *when orphaned*. This asymmetry is exactly the teardown trap: a `terraform destroy` that deletes the forwarding rule but leaves the address reserved flips it from free to billed. Always confirm `gcloud compute addresses list --global` is clean after teardown.
- **The forwarding rule + LB data processing** is a small hourly charge plus a per-GB processing charge on traffic through the LB. For a low-traffic service this is a few dollars a month; for a high-traffic one the per-GB processing is a real line item.
- **Cloud Armor** is a per-policy monthly charge plus a per-rule charge plus a per-request charge. Four rules and ten million requests is small money, but a policy with hundreds of rules and billions of requests is not — the per-request charge is the one that scales with traffic.
- **Cloud CDN** is cache egress (data served from cache to users) plus cache-fill (data fetched from your origin into the cache) plus a per-lookup charge. The *win* is that cache egress is cheaper than origin egress and you stop paying origin compute for hits — so CDN is usually net-negative cost (it saves more than it costs) for cacheable content, and pure overhead for content that does not cache.
- **The managed certificate** is free.

The shape to carry into the review: **at low traffic the edge is a handful of dollars dominated by the forwarding rule; at high traffic it is dominated by data processing, Armor per-request, and CDN egress — all of which scale with your traffic, not with your config.** The optimization levers are therefore traffic-shaped: cache more (cut origin egress and compute), keep the Armor rule count sane, and do not orphan IPs.

## 1.9 — A request's journey, narrated

Put it together. A user in Berlin types `https://api.example.com/api/orders`:

1. **DNS.** Their resolver asks Cloud DNS for `api.example.com`; Cloud DNS returns the anycast IP `34.x.x.x`. Their packets enter Google's network at the Frankfurt edge.
2. **TLS + Armor.** The Frankfurt edge terminates TLS using the managed certificate on the target HTTPS proxy. The decrypted request is evaluated against the Cloud Armor policy on the matched backend service: source IP under the rate limit? ✓. Query string clean of SQLi? ✓. Allowed.
3. **CDN.** The backend service has `enable_cdn = true`, but `/api/orders` is a `POST`-ish dynamic path returning `Cache-Control: private` — cache miss, correctly not cacheable. (A `GET /static/logo.png` would have been a hit served right here, and steps 4–5 would never run.)
4. **LB routing.** The URL map matches `/api/*` → the Cloud Run backend service → the serverless NEG wrapping the Week 07 service.
5. **Backend.** Cloud Run scales an instance (or reuses a warm one), runs the FastAPI handler, queries Cloud SQL over PSC, returns the orders. The response rides Google's backbone back to Frankfurt and to the user.

Now narrate the attack. A botnet in three countries hammers `/login` with credential-stuffing, salting some requests with `' OR 1=1 --`:

1. **DNS** hands them all the same anycast IP. (DNS did nothing; it cannot.)
2. **Armor** does the work. The SQLi-laced requests hit the preconfigured `sqli-v33-stable` rule → 403 at the edge, logged, never reaching the cache or backend. The clean-but-abusive requests trip the `rate_based_ban` rule at 100/60s per source IP → 429, then a temporary ban → the offending IPs are dropped at the edge for `ban_duration_sec`.
3. **CDN, LB, backend** never see the blocked traffic. Your origin's CPU graph stays flat. The page never fires.

That flat CPU graph during an attack is the entire point of the edge. You build it this week.

## 1.9a — Debugging the edge: which layer ate my request?

When the edge misbehaves, the five-layer model is also your debugging tree. The symptom tells you the layer; the layer tells you the fix. The playbook every senior engineer runs, top to bottom:

**Symptom: the hostname does not resolve / `curl` cannot connect.**
Layer: DNS or the forwarding rule. Run `dig +short api.example.com` — does it return the LB IP? If not, the A record is wrong or missing. If it does, `curl -v https://IP/` directly — does the TCP connection open on 443? If not, the forwarding rule or the IP reservation is the problem.

**Symptom: TLS error / certificate not valid.**
Layer: the proxy's certificate. `gcloud compute ssl-certificates describe edge-cert --global --format='value(managed.status, managed.domainStatus)'`. If `PROVISIONING`, the hostname is not resolving to the LB yet (back to DNS) — wait, or fix the A record. If `ACTIVE` but the client still errors, the client is hitting a different IP (stale DNS cache) or an SNI mismatch.

**Symptom: 403 on requests that should work.**
Layer: Cloud Armor (or IAP). Query the logs for `enforcedSecurityPolicy.configuredAction="DENY"` — which rule priority matched? A WAF false positive (your legitimate request looked like SQLi) shows here; opt that rule out or move the rule to preview. If there is no Armor deny in the logs, it is IAP (the requester is not in the allowed group) — check the IAP IAM policy.

**Symptom: 429 on normal traffic.**
Layer: Cloud Armor rate limit. Your threshold is too low, or your `enforce_on_key` is wrong (e.g. `ALL` is bucketing every client together). The logs show `RATE_BASED_BAN` / `THROTTLE` at the rate-limit priority.

**Symptom: stale or wrong content served.**
Layer: Cloud CDN. The cache key is wrong (serving one user's response to another) or the cache mode is too aggressive (`FORCE_CACHE_ALL` caching a dynamic page). Check `httpRequest.cacheHit` in the logs and the backend service's `cdn_policy`.

**Symptom: 502 / 503 from the LB.**
Layer: the backend service or the backend. The backend is unhealthy (failing health checks — wrong probe path, too aggressive, IAP blocking the health check), or there is no healthy endpoint at all (the NEG is empty, the Cloud Run service is down). `gcloud compute backend-services get-health <name> --global` shows endpoint health.

The discipline: **read the symptom, name the layer, query that layer's evidence.** Do not guess. The Cloud Armor logs, the cert status, the backend health, and `dig` are four commands that localize almost every edge failure to one layer in under a minute. An engineer who runs the tree looks like they can read minds; they are just reading the layers in order.

## 1.10 — What you should be able to do now

Before Exercise 1, you should be able to, on a whiteboard and without notes:

- Draw the five layers in order and label each with one capability and one limitation.
- Name the four-link LB chain (forwarding rule → target proxy → URL map → backend service) and say what each link does.
- Pick the right LB for a workload from the four-row matrix and defend it on protocol and scope.
- Name the four NEG types and which backend each fronts.
- Explain why a Google-managed cert needs DNS to resolve first.
- Explain why an IAP-protected backend must verify the signed JWT.

If any of those is shaky, re-read the relevant section before you touch Terraform. The build in Exercise 1 goes fast once the model is solid and is a maze of opaque errors when it is not.

## 1.11 — The one-sentence summary of each layer

If you remember nothing else from this lecture, remember these six sentences. They are the architecture-review answer in compressed form, and they fit on an index card:

- **DNS** turns your name into a nearby anycast IP and can fail over coarsely between regions — but it cannot see, rate-limit, or block a request.
- **Cloud Armor** stops volumetric abuse and known-bad payloads at the edge before they cost you anything — but it cannot cache, cannot identify a *user*, and cannot catch a valid-looking business-logic attack.
- **Cloud CDN** serves cacheable bytes from a nearby edge and cuts your origin cost and latency — but it cannot block anything and must never cache a private response.
- **The load balancer** terminates TLS at the edge, routes by host and path, and spreads load across healthy backends — but it does not know who the user is or whether a payload is malicious.
- **IAP** forces a login and an IAM check on every request to an internal app and stamps a signed identity — but it is bypassable unless the backend verifies the signature and refuses direct traffic.
- **The backend** runs your code and is the only layer that can enforce in-app authorization — so it must assume every layer in front of it can fail or be bypassed, verify what it is told, and validate every input.

Each layer has exactly one job and exactly one blind spot. The whole discipline of building an edge is matching the control to the layer that owns it, in the order a request actually travels. Everything in this week's exercises, the challenge, and the mini-project is an application of those six sentences. Carry them into the architecture review and you will sound like the staff engineer running it, not the candidate being reviewed.

---

*Lecture 2 takes the Cloud Armor layer apart in full: the CEL request attributes, the rate-limit bucket semantics, the preconfigured WAF expressions, and the bot-management scores — everything you need to write the rules Exercise 2 and the challenge make you validate under load.*
