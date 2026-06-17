# Lecture 2 — Cloud Armor in Common Expression Language: Rate Limiting, Preconfigured WAF Rules, and Bot Management

> **Reading time:** ~85 minutes. **Hands-on time:** ~50 minutes (you write a policy, attach it, and watch a rule bite in the logs).

Lecture 1 put Cloud Armor in the pipeline — layer 2, at Google's edge, before the cache and your backend. This lecture takes it apart. By the end you can write a Cloud Armor security policy that rate-limits abusive source IPs, rejects SQL-injection probes with a preconfigured WAF rule, allows your office CIDR unconditionally, blocks a sanctioned country, and challenges suspected bots — all in **Common Expression Language**, all ordered correctly so the rules evaluate the way you intend. You will also be able to read the Cloud Armor request logs and point at the exact rule that blocked a given request, which is the skill that turns "the WAF did something" into "the WAF matched rule priority 1000 with action `deny(403)`."

## 2.1 — A security policy is an ordered list of CEL rules

A Cloud Armor **security policy** is attached to a backend service and consists of:

- A list of **rules**, each with:
  - a **`priority`** (an integer; **lower number = evaluated first**),
  - a **`match`** — either a list of source IP ranges (`src_ip_ranges`) for the simple case, or a CEL **expression** for everything interesting,
  - an **`action`** — `allow`, `deny(403)` / `deny(404)` / `deny(502)`, `rate_based_ban`, `throttle`, or `redirect` (to a Google reCAPTCHA challenge or an external URL),
  - optional **`rate_limit_options`** (for `throttle` and `rate_based_ban`),
  - optional **`preview = true`** (evaluate and *log* the rule but do not enforce it — the single most important operational flag in the product).
- A **default rule** at priority `2147483647` (the max int) that you set to `allow` or `deny`. Every policy has one; it is the tail.

The engine walks rules from lowest priority to highest and **applies the action of the first rule whose match is true.** First match wins; evaluation stops. This is exactly like a firewall rule list, and the same discipline applies: **specific allows and denies go at low priority numbers (early), the broad default goes at the max (last).** Get the ordering wrong and a broad early rule shadows a specific later one that never runs.

The mental model that makes the rest of this lecture click: **everything in a Cloud Armor `match` is a CEL expression over the request.** The simple `src_ip_ranges` form is sugar for `inIpRange(origin.ip, '...')`. The preconfigured WAF rules are CEL via `evaluatePreconfiguredExpr(...)`. The rate limit is a normal rule whose *action* is rate-aware. Once you see it is one expression language over one request object, you stop hunting for the right checkbox and start writing the condition you actually mean.

## 2.2 — The request object: what CEL can see

A Cloud Armor CEL expression evaluates against a fixed set of request attributes. The ones you will actually use:

| Attribute | Type | What it is |
|-----------|------|------------|
| `origin.ip` | string | The client source IP as Google's edge sees it (the real TCP peer). |
| `origin.region_code` | string | The 2-letter country/region code derived from `origin.ip` (e.g. `"US"`, `"RU"`). |
| `request.path` | string | The URL path, e.g. `/api/orders`. |
| `request.query` | string | The raw query string after `?`. |
| `request.method` | string | `GET`, `POST`, … |
| `request.scheme` | string | `http` or `https`. |
| `request.headers['name']` | string | A request header by lowercase name, e.g. `request.headers['user-agent']`. |
| `request.headers['x-forwarded-for']` | string | The XFF chain — useful, but **forgeable**; see §2.6. |
| `token.recaptcha_session.score` / `token.recaptcha_action.score` | double | The reCAPTCHA Enterprise score, 0.0 (bot) → 1.0 (human); see §2.7. |

The CEL operators and functions you reach for:

- Logical: `&&`, `||`, `!`.
- String: `.contains('x')`, `.startsWith('/api')`, `.lower()`, `.matches('regex')` (RE2 syntax).
- IP: `inIpRange(origin.ip, '203.0.113.0/24')`.
- WAF: `evaluatePreconfiguredExpr('sqli-v33-stable')` and the `[ ... ]`-argument form for opt-outs (§2.4).

A first, concrete rule. "Allow my office unconditionally, before any other rule can deny it":

```hcl
rule {
  action   = "allow"
  priority = 100
  match {
    versioned_expr = "SRC_IPS_V1"
    config {
      src_ip_ranges = ["203.0.113.0/24"]
    }
  }
  description = "Office network: never rate-limit or WAF-block us."
}
```

The same intent in the CEL form (use this when the condition is more than just an IP list):

```hcl
rule {
  action   = "allow"
  priority = 100
  match {
    expr {
      expression = "inIpRange(origin.ip, '203.0.113.0/24')"
    }
  }
  description = "Office network: explicit CEL allow at low priority."
}
```

Both are at priority 100 so they evaluate *before* the rate-limit (priority 1000) and the WAF (priority 900) below — your own office never gets banned for load-testing.

## 2.3 — Rate limiting: `throttle` vs. `rate_based_ban`

Rate limiting is a rule whose action is rate-aware and whose `rate_limit_options` define the threshold, the bucket, and what happens when the bucket overflows. The two actions:

- **`throttle`** — above the threshold, return 429; below it, allow. The offender is throttled continuously: every request over the line gets a 429, but the moment they slow down they are served again. Good for "be nice, share the resource."
- **`rate_based_ban`** — above the threshold, *temporarily ban* the key for `ban_duration_sec`: every request from that key is dropped for the ban window, even if they stop after tripping it. Good for "you are clearly abusing this; go away for ten minutes." This is the one you want against credential-stuffing and scrapers.

The `rate_limit_options` block, annotated:

```hcl
rule {
  action   = "rate_based_ban"
  priority = 1000
  match {
    versioned_expr = "SRC_IPS_V1"
    config { src_ip_ranges = ["*"] }   # this rule applies to everyone…
  }
  rate_limit_options {
    enforce_on_key = "IP"              # …counted per source IP
    rate_limit_threshold {
      count        = 100               # 100 requests…
      interval_sec = 60                # …per 60-second sliding window
    }
    conform_action = "allow"           # under the threshold → allow
    exceed_action  = "deny(429)"       # over the threshold → 429…
    ban_duration_sec = 600             # …and ban the IP for 10 minutes
    ban_threshold {                    # (optional finer ban trigger)
      count        = 100
      interval_sec = 60
    }
  }
  description = "Per-IP rate-based ban: 100 req / 60s, ban 10 min."
}
```

The `enforce_on_key` choices — the *bucket* the count accumulates against — are the part people get wrong:

| `enforce_on_key` | Counts per | Use when |
|------------------|------------|----------|
| `IP` | `origin.ip` (the real TCP peer) | The default and the right answer most of the time. |
| `XFF_IP` | The first IP in `X-Forwarded-For` | You sit behind *another* trusted proxy and the real client IP is in XFF. **Dangerous if XFF is attacker-controlled** (§2.6). |
| `HTTP_HEADER` | A named header's value (e.g. an API key header) | Per-API-key or per-tenant limits. |
| `HTTP_COOKIE` | A named cookie's value | Per-session limits. |
| `ALL` | One global bucket for the whole rule | A blunt global cap (e.g. "no more than 10k req/min total to `/expensive`"). |

The single most common rate-limit bug: choosing `XFF_IP` when you are *directly* behind the global LB. The global external Application LB *appends* the real client IP to `X-Forwarded-For`, but the header is client-supplied up to that point — an attacker can prepend a fake IP. If you key on `XFF_IP` without a trusted-proxy chain in front, every attacker just sends a random fake first XFF entry and each request lands in a different bucket, defeating the limit entirely. **Default to `IP`** unless you have a specific, trusted L7 proxy ahead of Cloud Armor.

The interval semantics: `count` requests per `interval_sec`. The limit is enforced on a sliding-ish window per key; you do not get a perfectly precise token bucket, you get "roughly N per interval, evaluated at Google's edge across all the POPs serving that key." For the exercise you will pick numbers low enough that `hey` trips them obviously (e.g. 100/60s, then drive 50 concurrent for 30s).

## 2.4 — Preconfigured WAF rules: the OWASP CRS, wrapped in CEL

Hand-writing a regex that catches every SQL-injection shape is a fool's errand; the OWASP Core Rule Set is thousands of expert-maintained signatures. Cloud Armor ships the CRS as **preconfigured expression sets** you invoke with one CEL function:

```hcl
rule {
  action   = "deny(403)"
  priority = 900
  match {
    expr {
      expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
    }
  }
  description = "Block SQL injection (OWASP CRS 3.3, stable sensitivity)."
}
```

The preconfigured expression sets you should know (the version suffix moves; `v33` is CRS 3.3 at time of writing — check the resources page):

| Expression | Catches |
|------------|---------|
| `sqli-v33-stable` | SQL injection |
| `xss-v33-stable` | Cross-site scripting |
| `lfi-v33-stable` | Local file inclusion (`../../etc/passwd`) |
| `rfi-v33-stable` | Remote file inclusion |
| `rce-v33-stable` | Remote code execution |
| `scannerdetection-v33-stable` | Vulnerability scanners (sqlmap, nikto, …) |
| `protocolattack-v33-stable` | HTTP request smuggling, response splitting |
| `sessionfixation-v33-stable` | Session fixation |

### Sensitivity and the false-positive problem

The `-stable` suffix is the **paranoia-level / sensitivity** tuning. Each CRS rule has a paranoia level 1–4; higher paranoia catches more attacks *and more false positives*. `evaluatePreconfiguredExpr('sqli-v33-stable')` uses a curated stable sensitivity (roughly paranoia level 1). You can tune sensitivity and opt specific noisy rule IDs out with the `preconfigured_waf_config` block:

```hcl
rule {
  action   = "deny(403)"
  priority = 900
  match {
    expr {
      expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
    }
  }
  preconfigured_waf_config {
    exclusion {
      # This field/rule combo false-positives on our /search endpoint's
      # legitimate use of SQL keywords; opt that one CRS rule out for it.
      request_query_param { operator = "EQUALS"; value = "q" }
      target_rule_set = "sqli-v33-stable"
      target_rule_ids = ["owasp-crs-v030301-id942100-sqli"]
    }
  }
  description = "SQLi block, with one false-positive rule opted out for ?q="
}
```

The **operational rule that matters more than any syntax**: you do not ship a WAF rule straight to enforcing mode on a production endpoint. You ship it with `preview = true` first, let it *log without blocking* for a few days, mine the Cloud Armor logs for what it *would* have blocked, confirm those are all attacks and not your own legitimate traffic, opt out the false positives, *then* flip `preview = false`. A WAF that 403s your checkout flow because the address field contained the word "SELECT" is worse than no WAF — it is a self-inflicted outage. We do the full preview workflow in Week 14; this week you enable `sqli-v33-stable` directly on a *test* path so you can watch it bite, which is safe because nothing legitimate hits that path.

## 2.5 — Putting a policy together: priority is the whole game

Here is a complete, ordered policy that combines everything so far. Read the priorities top to bottom — they encode the intent.

```hcl
resource "google_compute_security_policy" "edge" {
  name        = "crunch-edge-policy"
  description = "Office allow → geo deny → WAF → rate-limit → default allow."

  # 100: our office is never touched by anything below.
  rule {
    action   = "allow"
    priority = 100
    match {
      expr { expression = "inIpRange(origin.ip, '203.0.113.0/24')" }
    }
    description = "Office allowlist."
  }

  # 200: block a sanctioned region outright.
  rule {
    action   = "deny(403)"
    priority = 200
    match {
      expr { expression = "origin.region_code == 'KP'" }
    }
    description = "Geo-deny."
  }

  # 900: block known-bad payloads (SQLi). Runs before the rate limit so a
  #       SQLi probe is a 403, not a 429 — the action tells you which it was.
  rule {
    action   = "deny(403)"
    priority = 900
    match {
      expr { expression = "evaluatePreconfiguredExpr('sqli-v33-stable')" }
    }
    description = "WAF: SQLi."
  }

  # 1000: per-IP rate-based ban for everyone who got this far.
  rule {
    action   = "rate_based_ban"
    priority = 1000
    match {
      versioned_expr = "SRC_IPS_V1"
      config { src_ip_ranges = ["*"] }
    }
    rate_limit_options {
      enforce_on_key   = "IP"
      conform_action   = "allow"
      exceed_action    = "deny(429)"
      ban_duration_sec = 600
      rate_limit_threshold { count = 100; interval_sec = 60 }
    }
    description = "Per-IP rate limit + ban."
  }

  # max int: the default tail. Allow what survived everything above.
  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config { src_ip_ranges = ["*"] }
    }
    description = "Default allow."
  }
}
```

Walk the order and notice what each priority buys you:

- **Office (100) before everything** so your own load tests never trip the rate limit and your own pen-test traffic is not WAF-blocked. (Take the office allow *out* before you actually pen-test, obviously.)
- **Geo-deny (200) early** so sanctioned traffic is dropped before you spend any WAF or rate-limit evaluation on it.
- **WAF (900) before the rate limit (1000)** so a SQLi probe gets a **403** (the WAF action) rather than a **429** (the rate-limit action). This is deliberate: the *action in the log* tells you *why* a request was blocked. If the rate limit ran first, every blocked SQLi probe would show as a 429 and you would lose the signal that you were under a SQLi attack, not just a volumetric one.
- **Default allow (max) last.** If you instead default-*deny*, you have built an allowlist edge (deny everything except explicitly-allowed) — a stronger posture for an internal API, a worse one for a public site that wants the world.

That ordering reasoning — "which action do I want in the log, and which rule must run first to produce it" — is the senior skill the quiz tests.

## 2.6 — `X-Forwarded-For` is your friend and your enemy

`X-Forwarded-For` deserves its own section because it is the source of half the Cloud Armor footguns.

The global external Application LB **appends** the real client IP (the TCP peer it observed) to whatever `X-Forwarded-For` the client sent, and also sets `X-Forwarded-For` you can read in CEL as `request.headers['x-forwarded-for']`. So the *last* IP that Google appended is trustworthy (Google observed it); everything *before* it is client-supplied and forgeable.

Consequences:

- **For rate limiting, use `enforce_on_key = "IP"` (which uses `origin.ip`, the real TCP peer Google saw) unless you have a trusted proxy in front of Cloud Armor.** `origin.ip` is not forgeable; the client cannot lie about the IP its packets came from. `XFF_IP` keys on the *first* XFF entry, which an attacker controls — they send a random first entry per request and scatter across buckets.
- **For logging the client IP into your backend**, read the LB-appended value, not the raw client-sent header.
- **For a geo or allowlist rule, use `origin.ip` / `origin.region_code`**, again because they derive from the real peer, not from a header the client can set.

The one time `XFF_IP` is correct: you have a *known, trusted* CDN or proxy (not Google's LB — a third one) in front of the Google LB, that L7 proxy sets a clean XFF, and you have a `trusted-proxy` configuration that tells Cloud Armor how many proxy hops to trust. Absent that, `origin.ip` every time.

## 2.7 — Bot management: reCAPTCHA scores in CEL

The rate limiter stops volumetric abuse from a few IPs. It does *not* stop a distributed bot that sends one request from each of ten thousand residential IPs — each IP stays under the per-IP threshold. That is what **bot management** addresses, via reCAPTCHA Enterprise.

The mechanism: you create a reCAPTCHA Enterprise **WAF key** (a session-token or action-token key), put the reCAPTCHA JavaScript on your pages (or use the action-token flow), and the resulting token carries a **score** from 0.0 (almost certainly a bot) to 1.0 (almost certainly human). Cloud Armor surfaces that score into CEL as `token.recaptcha_session.score` (or `token.recaptcha_action.score`), and you write rules on it:

```hcl
# Challenge low-scoring (likely-bot) requests to /login with a reCAPTCHA
# interstitial instead of blocking them outright — humans pass, bots fail.
rule {
  action   = "redirect"
  priority = 800
  match {
    expr {
      expression = "request.path.startsWith('/login') && token.recaptcha_session.score < 0.3"
    }
  }
  redirect_options {
    type = "GOOGLE_RECAPTCHA"
  }
  description = "Bot management: challenge low-score logins."
}
```

The `redirect` action with `type = "GOOGLE_RECAPTCHA"` serves a Google-hosted challenge page; a human solves it and proceeds, a bot fails and is stopped — without you having to outright block a score band that will inevitably contain some real users. You can also `deny(403)` on a very low score if you would rather drop than challenge. The score thresholds are workload-specific; 0.3 is a common starting line for "challenge below this."

We do not stand up reCAPTCHA in this week's required exercises (it needs a real frontend to issue tokens, which is beyond a Terraform-and-`curl` lab), but it is in the stretch goals, and you must know the *shape*: a score in `[0,1]`, surfaced as `token.recaptcha_*.score`, matched in CEL, actioned with `redirect`-to-challenge or `deny`. Bot management is "rate limiting for distributed bots that each look individually innocent."

## 2.8 — Reading the logs: prove which rule bit

A rule you cannot observe firing is a rule you do not trust. Every Cloud Armor decision is logged (when request logging is enabled on the backend service's LB) under the `enforcedSecurityPolicy` structure in the request log. The fields that matter:

- `enforcedSecurityPolicy.name` — the policy name (`crunch-edge-policy`).
- `enforcedSecurityPolicy.priority` — **which rule matched** (e.g. `900` for the WAF, `1000` for the rate limit).
- `enforcedSecurityPolicy.configuredAction` — the action (`DENY`, `ALLOW`, `THROTTLE`, `RATE_BASED_BAN`).
- `enforcedSecurityPolicy.outcome` — `ACCEPT` or `DENY`.
- For preview rules, the parallel `previewSecurityPolicy.*` fields show what *would* have happened.

The Logs Explorer query you run after the exercise's `curl` SQLi test:

```
resource.type="http_load_balancer"
jsonPayload.enforcedSecurityPolicy.configuredAction="DENY"
jsonPayload.enforcedSecurityPolicy.priority=900
```

and the `gcloud` equivalent for a terminal-only workflow:

```bash
gcloud logging read \
  'resource.type="http_load_balancer"
   jsonPayload.enforcedSecurityPolicy.configuredAction="DENY"' \
  --limit=10 --format='value(timestamp, httpRequest.requestUrl,
   jsonPayload.enforcedSecurityPolicy.priority,
   jsonPayload.enforcedSecurityPolicy.configuredAction)'
```

When you can run that query and see your SQLi `curl` show up as a `DENY` at priority 900, and your `hey` flood show up as `RATE_BASED_BAN` at priority 1000, you have *proven* the policy works — which is the only kind of "it works" this week accepts.

## 2.9 — The full decision procedure for a new policy

When you sit down to write a Cloud Armor policy for a real service, run this procedure:

1. **Allowlist what must never be blocked.** Your office, your monitoring, your CI's egress IP — at the lowest priorities, action `allow`. (Remove before pen-testing.)
2. **Hard-deny what must never be served.** Sanctioned geos, a known-bad CIDR — next, action `deny(403)`.
3. **WAF the known-bad payloads.** The preconfigured expressions relevant to your stack (almost always at least `sqli` and `xss`), in **preview mode first**, graduated to enforcing after you have mined the logs for false positives. Put these *before* the rate limit so payload attacks log as their own action.
4. **Rate-limit the volumetric abuse.** A `rate_based_ban` keyed on `IP` for the broad case; per-tenant `HTTP_HEADER` limits where you have API keys. Threshold set from your real traffic's p99 request rate, with headroom.
5. **Bot-manage the distributed case** (if you have a frontend that can issue reCAPTCHA tokens): challenge or deny low scores on the sensitive paths.
6. **Default.** `allow` for a public site, `deny` for an allowlist-only internal API.
7. **Enable request logging and verify every rule in the logs** before you call it done.

That procedure, in that order, is the answer to "design a Cloud Armor policy for X" in an interview and in the architecture review at the end of this week.

## 2.10 — What you should be able to do now

Before Exercise 2, you should be able to, from memory:

- Write a `rate_based_ban` rule keyed per source IP with a threshold and a ban duration, and explain why `enforce_on_key = "IP"` beats `XFF_IP` for a directly-fronted LB.
- Write a preconfigured SQLi WAF rule with `evaluatePreconfiguredExpr` and explain why it goes *before* the rate limit and *in preview mode first* on a production path.
- Order a multi-rule policy correctly using priorities, and explain why the order produces the log signal you want.
- Read the `enforcedSecurityPolicy` log fields and identify which rule blocked a given request.
- Explain why a per-IP rate limit does not stop a distributed bot, and what does.

If those are solid, Exercise 2 is twenty minutes of Terraform and ten minutes of watching `hey` and `curl` trip the rules you wrote. If they are shaky, the rules will *look* applied and mysteriously not bite — and the fix is always either a priority ordering bug or an `enforce_on_key` mistake, both of which this lecture just inoculated you against.

---

*Exercise 2 makes you write exactly the policy in §2.5, attach it to the Exercise 1 load balancer, and validate the rate limit with `hey` and the WAF with a malformed `curl` — then find both in the logs. The challenge welds Exercises 1 and 2 onto the real Week 07 Cloud Run service and validates the whole edge under sustained load.*
