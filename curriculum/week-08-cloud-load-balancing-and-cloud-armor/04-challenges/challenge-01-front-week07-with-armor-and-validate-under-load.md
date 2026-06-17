# Challenge 1 — Front the Week 07 Cloud Run Service with a Global HTTPS LB, Cloud CDN, and a Cloud Armor Policy, Then Validate Under Load

> **Difficulty:** hard. **Estimated time:** ~3 hours. **No solution provided** — acceptance criteria and required proofs only.

This is the hands-on lab the syllabus names for Week 08. You take the **real** Cloud Run service you shipped in Week 07 (the stateless service backed by Cloud SQL over Private Service Connect, *not* the toy origin from Exercise 1) and you build the production edge in front of it: a global external HTTPS LB, Cloud CDN, a per-source-IP rate limit, and a preconfigured SQLi WAF rule. Then you prove the whole thing holds under sustained load with `hey` and blocks a malformed request with the WAF — and you back every claim with a Cloud Armor log line.

The exercises gave you each piece in isolation. The challenge makes you assemble them on a real service and *validate under load*, which is where the interesting failures live: a backend service health check that flaps, a rate limit keyed wrong so the load test never trips it, a WAF that 403s your own legitimate traffic, a cache that serves a stale or private response. Find and fix those, and you have built an edge you could put in front of production.

## The goal

Stand up, in Terraform (extend your Week 04 module library or a self-contained root module — your call, document it):

1. A **global external Application LB** (`EXTERNAL_MANAGED`) with a reserved anycast IP and a Google-managed TLS certificate for a hostname you control (or `<ip>.sslip.io`).
2. A **serverless NEG** pointing at your **Week 07 Cloud Run service** (the real one — redeploy it from your Week 07 repo if you tore it down).
3. **Cloud CDN** enabled on the backend service with `cache_mode = "USE_ORIGIN_HEADERS"`. (If the Week 07 service has no cacheable path, add one — a `GET /static/health.json` returning `Cache-Control: public, max-age=300` is enough — and document it.)
4. A **Cloud Armor security policy** attached to that backend service with, at minimum:
   - a **per-source-IP `rate_based_ban`** rule (you choose the threshold; it must be low enough that `hey` trips it and high enough that a single human browsing does not),
   - a **preconfigured SQLi WAF rule** (`evaluatePreconfiguredExpr('sqli-v33-stable')`) at a priority that makes a SQLi probe log as a 403, not a 429,
   - a sensible default tail.
5. Cloud Armor **request logging at `VERBOSE`** so the matched rule is visible in the logs.

Then validate.

## Required proofs (paste these into your `CHALLENGE.md`)

You are graded on the proofs, not the Terraform. Each proof is a command and its real output (redact your IP/host as you like, keep the status codes and log fields).

**Proof 1 — the edge serves the real service over HTTPS.**

```bash
curl -si "https://$HOST/<a real Week07 path>" | head -1     # HTTP/2 200
```

**Proof 2 — Cloud CDN serves the cacheable path from the edge.**

```bash
curl -si "https://$HOST/static/health.json" >/dev/null      # prime
curl -si "https://$HOST/static/health.json" | grep -i '^age:'  # age > 0
gcloud logging read \
  'resource.type="http_load_balancer" httpRequest.requestUrl:"health.json"' \
  --limit=3 --format='value(httpRequest.requestUrl, httpRequest.cacheHit)'
# At least one row with cacheHit = True.
```

**Proof 3 — the rate limit trips under load.** Run `hey` hard enough to cross your threshold, and show the 429s:

```bash
hey -z 30s -c 50 "https://$HOST/<a cheap dynamic path>"
# Paste the full "Status code distribution" — it must contain BOTH 200 and 429.
# State your threshold and explain why 50 concurrent for 30s crosses it.
```

**Proof 4 — p99 latency holds for the *allowed* traffic during the load test.** From the same `hey` run, paste the latency histogram and state your p99 for the 200-status responses. (You are proving the edge does not *itself* add unacceptable latency to legitimate traffic while it rate-limits the abusive traffic.)

**Proof 5 — the WAF blocks a malformed request.**

```bash
curl -si "https://$HOST/?q=1%27%20OR%20%271%27%3D%271" | head -1   # HTTP/2 403
curl -si "https://$HOST/?id=1%20UNION%20SELECT%20NULL--" | head -1 # HTTP/2 403
curl -si "https://$HOST/" | head -1                                # HTTP/2 200 (clean)
```

**Proof 6 — both blocks appear in the Cloud Armor logs at the right priorities.**

```bash
gcloud logging read \
  'resource.type="http_load_balancer"
   jsonPayload.enforcedSecurityPolicy.configuredAction=("DENY" OR "RATE_BASED_BAN")' \
  --limit=10 \
  --format='value(httpRequest.requestUrl,
    jsonPayload.enforcedSecurityPolicy.priority,
    jsonPayload.enforcedSecurityPolicy.configuredAction)'
# Must show: the SQLi URL as DENY at your WAF priority, and the flood as
# RATE_BASED_BAN at your rate-limit priority. If the SQLi shows as RATE_BASED_BAN,
# your priority ordering is wrong (WAF must run before the rate limit).
```

## Acceptance criteria

- [ ] The **real Week 07 Cloud Run service** is behind the LB (not the Exercise 1 toy). Stated and shown.
- [ ] HTTPS works with a Google-managed cert in `ACTIVE` state. (`gcloud compute ssl-certificates describe ... --format='value(managed.status)'` → `ACTIVE`.)
- [ ] Cloud CDN demonstrably serves a cache hit (`cacheHit: True` in logs), and a dynamic/`private` path is demonstrably **not** cached.
- [ ] The rate limit produces 429s under `hey` and does **not** block a single human browsing. Threshold justified.
- [ ] p99 for allowed (200) traffic during the load test is stated and is reasonable (sub-second for a warm Cloud Run service; state your number).
- [ ] The SQLi WAF returns 403 on a malformed request and 200 on the clean one, and logs as a 403/DENY (not a 429) — proving correct rule ordering.
- [ ] Every claim above has a pasted command + output in `CHALLENGE.md`.
- [ ] `terraform destroy` tears the edge down cleanly; no orphaned forwarding rules or addresses (`gcloud compute forwarding-rules list --global` and `addresses list --global` are clean afterward).

## Stretch (optional, not graded but noted)

- Add a **geo-deny** rule and prove it with a request from a VPN exit in the denied region (or by temporarily denying your *own* region and watching yourself get 403'd, then reverting).
- Put the SQLi rule in **preview mode** first, run a corpus of *benign* requests through your real endpoints, and report whether any would have false-positived. This is the real production WAF rollout (Lecture 2 §2.4) and the difference between a WAF and an outage.
- Add a **second backend** to the URL map (a GCS `backend bucket` for `/static/*`) so one hostname routes `/api/*` to Cloud Run and `/static/*` to the bucket — a preview of the mini-project's multi-backend edge.

## What good looks like

A senior reviewer reading your `CHALLENGE.md` should be able to, in five minutes, see: the edge serves the real service, the cache hits, the rate limit bites at a justified threshold without harming real users, the WAF blocks SQLi and logs it as a 403 at the right priority, p99 holds, and the whole thing tears down clean. If your writeup says "the rate limit works" without a `hey` status distribution, you have not done the challenge — you have asserted it. Show the 429s.
