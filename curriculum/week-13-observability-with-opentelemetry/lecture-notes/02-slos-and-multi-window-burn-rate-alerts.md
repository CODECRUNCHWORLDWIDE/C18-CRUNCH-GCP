# Lecture 2 — SLIs, SLOs, Error Budgets, and Multi-Window Burn-Rate Alerts

> **Reading time:** ~80 minutes. **Hands-on time:** ~70 minutes (you define an SLO in Terraform and arm a multi-window burn-rate alert, then break the service and watch it fire).

Lecture 1 gave you the rule — page only on user-visible risk — and the symptom set — the four golden signals. This lecture turns that into the one alerting primitive that actually obeys the rule: the multi-window, multi-burn-rate alert. To get there we have to build the chain: an SLI measures the symptom, an SLO sets the promise, an error budget turns the promise into a spendable quantity, and the burn rate measures how fast you are spending it. The alert fires when you are spending too fast to make it to the end of the window. Every link in that chain exists for a reason, and the reason is always "so the alert pages on real risk and stays quiet otherwise." Read the Site Reliability Workbook Chapter 5 before or alongside this lecture; it is the source.

## 2.1 — SLI: the service level indicator

An **SLI** is a quantitative measure of one aspect of the service level, expressed as a ratio of good events to total events, between 0 and 1 (usually shown as a percentage). The canonical form:

> SLI = good events / valid events

The discipline is in the words "good" and "valid." A request-based availability SLI for an HTTP service:

> SLI = (count of requests with status < 500) / (count of all requests with status defined)

A latency SLI:

> SLI = (count of requests served in < 300 ms) / (count of all requests)

A data-freshness SLI for the Week 09 pipeline:

> SLI = (count of events landed in BigQuery within 60 s of event time) / (count of all events)

There are two structural families:

- **Request-based SLI.** Count good and total *events* (requests, messages). This is the form Cloud Monitoring calls a request-based SLI. It is the right default for request/response services.
- **Windows-based SLI.** Slice time into small windows (e.g. 1 minute), declare each window "good" or "bad" by some criterion (e.g. "error rate in this minute was below 1%"), and the SLI is the fraction of good windows. This is the right form for things measured continuously rather than per-request (a batch pipeline's uptime, a queue's drain rate).

Pick request-based unless the thing you measure is not naturally per-request. The math in this lecture is written for request-based; the workbook covers the windows-based variant.

The SLI must be measured **from as close to the user as possible.** An availability SLI computed from the load balancer's view (`response_code_class`) is better than one computed inside the app, because the LB sees the requests the app never received (the app crashed, the connection was refused). A latency SLI from the LB's `total_latencies` includes the queueing the app does not see. Measure at the edge when you can.

## 2.2 — SLO: the promise

An **SLO** is a target value for an SLI over a time window:

> 99.9% of requests over a rolling 28 days are served with status < 500.

Three knobs: the SLI (what you measure), the target (99.9%), and the window (28 days rolling, or a calendar month). The target is a business decision, not an engineering one — it is the promise you are willing to make and be held to. The most common mistake is setting it to 100%. **100% is the wrong target for everything**, because the cost of the last fraction of a nine grows without bound and because your dependencies (the network, the cloud provider, DNS) are not 100% either. If you promise 100% you will break the promise, and a promise you always break is worse than no promise. Pick a target you can actually hold and that the users actually need. Most user-facing services live at 99.9% or 99.95%; internal best-effort services at 99% or 99.5%.

The number of nines is not free. Here is what each costs as allowed bad time per 28-day window (this table is worth memorizing; it is on the PCA/DevOps exam in spirit):

| SLO | Allowed unavailability per 28 days | Per day |
|-----|------------------------------------|---------|
| 99%      | ~6h 43m   | ~14m 24s |
| 99.5%    | ~3h 22m   | ~7m 12s |
| 99.9%    | ~40m 19s  | ~1m 26s |
| 99.95%   | ~20m 10s  | ~43s |
| 99.99%   | ~4m 2s    | ~8.6s |

Read the 99.9% row carefully: **a "three nines" service is allowed about forty minutes of complete unavailability every four weeks.** That is not much. It is also not nothing. The whole point of the next section is to treat those forty minutes as a *budget you get to spend*, not a failure to be ashamed of.

## 2.3 — Error budget: the promise made spendable

The **error budget** is the inverse of the SLO: `1 − SLO`. A 99.9% SLO has a 0.1% error budget. Over 28 days, if you serve 100 million requests, your budget is 100,000 failed requests. You may spend them however you like. Spend them on a risky deploy, on an experiment, on a region failover drill, on a chaos test. As long as you stay within budget over the window, **you are meeting the promise and there is nothing to alert on, no matter how many individual errors occurred.**

This reframing is the single most important cultural idea in SRE, and it directly serves the alert-hygiene rule:

- It tells you **when not to alert.** Errors happened? Fine — were they within budget? Then no page. The budget is the threshold between "noise" and "risk."
- It tells you **when to stop shipping.** If a team burns the budget early, the error-budget *policy* (a pre-agreed document) says: freeze feature launches, redirect to reliability work, until the budget recovers. This converts "the SREs and the developers argue about reliability" into "the budget decides." It is a contract, not a vibe.
- It tells you **what to do at each consumption level.** This is the error-budget policy and it is part of your deliverable:

| Budget consumed (rolling 28d) | Action |
|-------------------------------|--------|
| < 50% | Normal operations. Ship freely. |
| 50–75% | Heads-up in the team channel. Review recent deploys. No freeze. |
| 75–90% | Slow down. New launches require a reliability review. |
| > 90% | Feature freeze. All hands on reliability until budget recovers. |
| 100% (SLO breached) | Incident review. The promise was broken; understand why. |

These thresholds are an example, not a law — your team sets them — but you must *have* them written down before the budget gets tight, not after.

## 2.4 — Why a static threshold fails

Now the alerting. The naive approach: "alert if the error rate over the last 5 minutes exceeds 0.1%." This fails in both directions, and seeing exactly how is the motivation for the whole burn-rate apparatus.

**It pages on noise.** A 0.1% threshold over 5 minutes, on a service doing 100 requests in those 5 minutes, fires on a *single* error. One transient error pages you at 03:00. Multiply by every service and you have a pager that never stops. You cannot fix this by raising the threshold to "0.1% over 5 minutes AND at least 50 errors," because then —

**It misses fast burns on low-traffic windows and slow burns entirely.** If the threshold is high enough to ignore a single error, it ignores a sustained low-grade error rate that quietly eats your entire 28-day budget over three days. A service returning 0.05% errors continuously is *under* a 0.1% instantaneous threshold forever, yet over 28 days it burns half the budget for no reason and you never hear about it until the budget is gone.

The instantaneous error rate is the wrong thing to alert on. What you actually care about is: **am I spending the budget fast enough that I will run out before the window ends?** That quantity is the burn rate.

## 2.5 — Burn rate: the right quantity

The **burn rate** is how fast you are consuming the error budget, expressed as a multiple of the "spend it all exactly at the window's end" rate.

- Burn rate **1×** means: you are consuming the budget at exactly the rate that uses it all up precisely at the end of the 28-day window. Right on target.
- Burn rate **2×** means: at this rate you exhaust the budget in 14 days.
- Burn rate **14.4×** means: you exhaust the *entire 28-day budget in about 2 days*, and the famous number 14.4 is chosen so that you burn **about 2% of the budget in 1 hour** — `14.4 × (1 hour / 720 hours per 28 days) ≈ 2.0%`. (The workbook's standard table fixes the exact window/burn-rate pairs; they are reproduced below, and the "~2% in 1h" figure matches the fast-burn row of that table.)

The arithmetic: over a window of length `T`, at burn rate `B`, the fraction of the total budget consumed is `B × (window_observed / T)`. Burn rate itself is just the observed error rate divided by the SLO's error-budget rate:

> burn_rate = (1 − SLI_observed) / (1 − SLO_target)

So if your SLO is 99.9% (budget = 0.001) and you are observing a 1.0% error rate (1 − SLI = 0.01), your burn rate is `0.01 / 0.001 = 10×`. At 10× you exhaust 28 days of budget in 2.8 days. That is a fast burn and it should page.

This is exactly why the mini-project injects a **1% error rate**: against a 99.9% SLO it is a clean 10× burn, comfortably above the fast-burn threshold, so you can watch the right alert fire and the cause alerts stay silent.

## 2.6 — Multi-window, multi-burn-rate: the actual pattern

A single burn-rate threshold over a single window still has a tension: a short window reacts fast but is jumpy (fires on a brief spike); a long window is stable but slow (a real fast burn takes too long to detect). The Site Reliability Workbook's answer is to use **multiple burn rates over multiple windows**, each tuned to a different failure speed, and to require **two windows to agree** before paging.

The standard table (workbook Chapter 5, for a 99.9% / 28-day SLO):

| Severity | Burn rate | Long window | Short window | Budget consumed at fire | Action |
|----------|-----------|-------------|--------------|-------------------------|--------|
| **Page (fast burn)** | 14.4× | 1 hour | 5 min | ~2% in 1h | **Page.** Budget gone in ~2 days at this rate. |
| **Page (medium burn)** | 6× | 6 hours | 30 min | ~5% in 6h | **Page.** Budget gone in ~5 days. |
| **Ticket (slow burn)** | 1× | 3 days | 6 hours | ~10% over 3d | **Ticket.** Slow leak; fix in business hours. |

Two ideas make this work:

1. **The long window decides severity; the short window confirms it is still happening.** The 14.4× / 1h alert also checks the last 5 minutes. If the burn was real but already stopped (a brief incident that recovered), the short window has dropped below threshold and the alert **does not fire / auto-resolves**. This is what stops you paging for an incident that already healed itself — the single most common false page. The short window is the "is it *still* burning?" check.

2. **Fast and slow burns get different treatment.** A 14.4× burn is an emergency — page. A 1× slow leak that will take three days to matter is a ticket — it does not need you at 03:00, it needs a fix in daylight. Notice the slow-burn row does *not* page. That is the alert-hygiene rule from Lecture 1, made arithmetic: the slow leak is real but not "needs human action *now*," so it is a ticket, not a page.

You typically deploy the **fast-burn page (14.4×)** and the **slow-burn ticket (1×)** at minimum; the medium-burn (6×) page is a common third. Two pages plus a ticket per service, all tied to one SLO. That is the whole alert set for a service. Compare that to the dozen cause-alerts a console-clicking team accumulates.

## 2.7 — Building it in Terraform

Cloud Monitoring models this as three resources: a `Service` (the thing the SLO is about), a `ServiceLevelObjective`, and one or more `AlertPolicy` resources whose condition is a burn-rate condition against the SLO. Here is the full chain for a Cloud Run service's availability SLO. This is real, applies cleanly against the `hashicorp/google` provider 5.x/6.x, and is the skeleton you reuse for every service in the mini-project.

```hcl
# slo.tf — availability SLO + multi-window burn-rate alerts for a Cloud Run service.

variable "project_id" { type = string }
variable "service_name" {
  type    = string
  default = "ingest-api"
}
variable "run_location" {
  type    = string
  default = "us-central1"
}

# 1. The Service the SLO is about. For a Cloud Run service we use a custom
#    Service and point the SLI at the run.googleapis.com request_count metric.
resource "google_monitoring_service" "ingest" {
  project      = var.project_id
  service_id   = "${var.service_name}-svc"
  display_name = "${var.service_name} (Cloud Run)"

  basic_service {
    service_type = "CLOUD_RUN"
    service_labels = {
      service_name = var.service_name
      location     = var.run_location
    }
  }
}

# 2. The SLO: 99.9% of requests over a rolling 28 days return non-5xx.
#    A request-based SLI built from good_total_ratio over the Cloud Run
#    request_count metric, sliced by response_code_class.
resource "google_monitoring_slo" "ingest_availability" {
  project      = var.project_id
  service      = google_monitoring_service.ingest.service_id
  slo_id       = "${var.service_name}-availability"
  display_name = "${var.service_name} availability 99.9% / 28d"

  goal                = 0.999
  rolling_period_days = 28

  request_based_sli {
    good_total_ratio {
      # "good" = non-5xx responses; "total" = all responses.
      good_service_filter = join(" AND ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${var.service_name}\"",
        "metric.label.\"response_code_class\"!=\"5xx\"",
      ])
      total_service_filter = join(" AND ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${var.service_name}\"",
      ])
    }
  }
}

# 3. A notification channel (email here; PagerDuty/Slack in production).
resource "google_monitoring_notification_channel" "oncall_email" {
  project      = var.project_id
  display_name = "${var.service_name} on-call email"
  type         = "email"
  labels = {
    email_address = "oncall@example.com"
  }
}

# 4a. FAST-BURN page: 14.4x over 1h, confirmed by 14.4x over 5m.
resource "google_monitoring_alert_policy" "fast_burn" {
  project      = var.project_id
  display_name = "${var.service_name} SLO fast burn (14.4x) — PAGE"
  combiner     = "AND"

  conditions {
    display_name = "Fast burn 1h"
    condition_threshold {
      filter = "select_slo_burn_rate(\"${google_monitoring_slo.ingest_availability.id}\", \"3600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 14.4
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
      }
    }
  }
  conditions {
    display_name = "Fast burn 5m"
    condition_threshold {
      filter = "select_slo_burn_rate(\"${google_monitoring_slo.ingest_availability.id}\", \"300s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 14.4
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.oncall_email.id]
  severity              = "CRITICAL"

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    subject = "PAGE: ${var.service_name} is burning its error budget fast (14.4x)"
    content = <<-EOT
      The ${var.service_name} availability SLO is burning at >= 14.4x.
      At this rate the 28-day error budget is exhausted in ~2 days.

      This is a PAGE: there is user-visible risk that needs action now.

      First steps:
      1. Open Cloud Trace, filter to service ${var.service_name}, status=ERROR.
      2. Open the correlated error logs from a failing trace.
      3. Check the most recent deploy (service.version attribute) — roll back if it correlates.
    EOT
    mime_type = "text/markdown"
  }
}

# 4b. SLOW-BURN ticket: 1x over 3 days, confirmed by 1x over 6h.
#     Note: this does NOT page. It is a slow leak — fix in business hours.
resource "google_monitoring_alert_policy" "slow_burn" {
  project      = var.project_id
  display_name = "${var.service_name} SLO slow burn (1x) — TICKET"
  combiner     = "AND"

  conditions {
    display_name = "Slow burn 3d"
    condition_threshold {
      filter = "select_slo_burn_rate(\"${google_monitoring_slo.ingest_availability.id}\", \"259200s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 1.0
      duration        = "0s"
      aggregations {
        alignment_period   = "3600s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
      }
    }
  }
  conditions {
    display_name = "Slow burn 6h"
    condition_threshold {
      filter = "select_slo_burn_rate(\"${google_monitoring_slo.ingest_availability.id}\", \"21600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 1.0
      duration        = "0s"
      aggregations {
        alignment_period   = "3600s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
      }
    }
  }

  # Route to a ticketing channel, NOT the pager. Severity WARNING, not CRITICAL.
  notification_channels = [google_monitoring_notification_channel.oncall_email.id]
  severity              = "WARNING"

  documentation {
    subject   = "TICKET: ${var.service_name} slow error-budget burn (1x)"
    content   = "Slow burn. Not a page. Investigate in business hours; the budget is leaking but you have days."
    mime_type = "text/markdown"
  }
}
```

The key API detail: `select_slo_burn_rate("<slo_id>", "<lookback>")` is a Monitoring Query Language / filter function that computes the burn rate of the named SLO over the given lookback window. The `combiner = "AND"` on the policy is what implements "both windows must agree" — the policy fires only when both the long-window and short-window conditions are simultaneously true. That `AND` is the line that stops you paging for an incident that already recovered. The slow-burn policy sets `severity = "WARNING"` and routes to a ticket channel; the fast-burn sets `CRITICAL` and routes to the pager. Same SLO, two policies, two destinations — exactly the alert-hygiene split from Lecture 1.

## 2.8 — Validating the alert by breaking the service

An alert you have never seen fire is an alert you do not trust. You validate it the same way you validate a backup: by exercising it on purpose. The recipe (the mini-project formalizes it):

1. Deploy a fault-injection toggle into the service — a middleware that returns a 500 for a configurable fraction of requests, gated by an env var:

```python
# fault_injection.py — FastAPI middleware, gated by FAULT_RATE (0.0–1.0).
import os
import random
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class FaultInjectionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._rate = float(os.environ.get("FAULT_RATE", "0.0"))

    async def dispatch(self, request, call_next):
        if self._rate > 0.0 and random.random() < self._rate:
            return JSONResponse(
                {"error": "injected fault"}, status_code=500
            )
        return await call_next(request)
```

2. Generate steady traffic (`hey -z 30m -q 50 https://<service-url>/health`), set `FAULT_RATE=0.01` on a new revision, and split 100% of traffic to it. You are now serving a clean 1% error rate.

3. Against a 99.9% SLO, 1% errors = `0.01 / 0.001 = 10×` burn. That is below the 14.4× fast-burn threshold but above the 6× medium-burn threshold. So if you armed the 6× policy, **it pages within ~30 minutes** (its short window). The 14.4× policy stays quiet (correctly — 10× is not 14.4×). The slow-burn ticket will eventually fire too. Push `FAULT_RATE=0.02` (20× burn) and the 14.4× fast-burn page fires within minutes.

4. Confirm the **cause alerts stay silent**: CPU is fine, memory is fine, no pod restarted. Only the symptom (error-budget burn) alerted. That is the whole thesis of the week, demonstrated on a live service.

5. Roll back (`FAULT_RATE=0.0`), watch the short windows drop below threshold, and watch the fast-burn alert auto-close (the `auto_close = "1800s"` and the `AND`-combiner short window working together). Set `FAULT_RATE` to 0 and tear down the load generator.

If the wrong alert fired, or no alert fired, or a cause alert fired — you found a bug in your alerting *before* it found you on call. That is the entire point of validation, and it is why the mini-project's acceptance criteria require you to do it and screenshot the result.

## 2.9 — Common mistakes

- **SLO target of 100%.** Impossible, and it removes the error budget entirely, which removes the whole alerting model. Never.
- **Measuring the SLI inside the app.** You miss the requests the app never received. Measure at the LB / Cloud Run edge.
- **Paging on the slow-burn alert.** A 1× burn does not need you at 03:00. Route it to a ticket. Paging on it reintroduces alert fatigue.
- **One window instead of two.** A single short window pages on recovered incidents; a single long window detects fast burns too slowly. Always pair a long window (severity) with a short window (still-happening confirmation) via `AND`.
- **High-cardinality metric labels in the SLI filter.** The SLI is computed over an aggregate metric; do not slice it by `tenant.id` or you get one SLO per tenant and a billing surprise. Per-tenant SLOs are a deliberate, separate design, not an accident of a label.
- **No error-budget policy.** Without the pre-agreed "what we do at each consumption level" document, the budget is just a number on a dashboard nobody acts on. Write the policy before the budget gets tight.

## Summary

- **SLI** = good / valid events, measured as close to the user as possible. Request-based by default.
- **SLO** = a target for the SLI over a window (e.g. 99.9% over 28 days). Never 100%. The number of nines maps to a fixed allowed-downtime budget — memorize the 99.9% ≈ 40 min/28d row.
- **Error budget** = `1 − SLO`, a spendable quantity. Within budget = meeting the promise = nothing to alert on. The error-budget policy says what to do at each consumption level.
- **Burn rate** = `(1 − SLI_observed) / (1 − SLO_target)` = how many times faster than "on target" you are spending. 1% errors against a 99.9% SLO = 10× burn.
- **Multi-window multi-burn-rate** is the alert that obeys the hygiene rule: a fast-burn page (14.4×, 1h AND 5m) for emergencies, a slow-burn ticket (1×, 3d AND 6h) for leaks, the `AND` of long+short windows so recovered incidents do not page. Build it with `google_monitoring_slo` + `google_monitoring_alert_policy` using `select_slo_burn_rate`.
- **Validate by injecting a 1% error rate** and confirming the right alert pages while the cause alerts stay silent. An unvalidated alert is an untrusted alert.

This is the production-grade alerting model. Two pages and a ticket per service, every page user-visible and actionable, validated by deliberate breakage. The exercises and the mini-project make you do it for real, across the whole Week 06–12 fleet.
