# Lecture 2 — The "min-instances=1 Pays for Itself" Threshold and How to Compute It

> **Reading time:** ~70 minutes. **Hands-on time:** ~50 minutes (you measure a cold start and plug your own numbers into the break-even formula).

Lecture 1 drew the serverless cost curve with `min-instances=0` — the cheapest configuration and the one with the worst tail latency. This lecture is about the single most consequential Cloud Run knob after concurrency: **`min-instances`**, the floor on how many container instances Cloud Run keeps warm even when no traffic is arriving. The decision "should I set `min-instances=1`?" is not a matter of taste. It is a financial trade with two sides — the dollar cost of keeping one instance always warm versus the cost (in latency, lost conversions, and SLO budget) of the cold starts you would otherwise pay. By the end of this lecture you can compute both sides, find the break-even, and defend the number. The challenge this week makes you benchmark cold start at `min-instances=0`, `1`, and `3` and produce the cost comparison for each — this lecture is the theory that makes that benchmark mean something.

## 2.1 — What a cold start actually is

When a request arrives and there is no warm instance to handle it, Cloud Run performs a **cold start**: the end-to-end time from "request arrives" to "your handler returns the first byte" for a request that had to wait for a fresh instance. It is the sum of several phases, and knowing the phases tells you which ones you can shrink:

1. **Scheduling / scale-up decision.** Cloud Run's autoscaler decides it needs another instance. Tens of milliseconds; not yours to optimize.
2. **Image pull.** The OCI image is pulled to the host (cached on hosts that recently ran it; cold on others). **This scales with image size.** A 1.2 GB Python image with the full CUDA stack pulls far slower than a 40 MB distroless Go binary. This is the phase you most directly control by shrinking your image.
3. **Container start.** The container runtime starts your process. Milliseconds to tens of milliseconds.
4. **Application initialization.** Your code from process start to "ready to serve": importing modules, building the framework app, opening connection pools, loading models, reading config. **This is usually the biggest controllable phase.** A Python service that imports `pandas`, `numpy`, and a 200 MB ML model at startup can spend several seconds here. A service that lazily defers heavy imports and opens the DB pool on first use is ready in a few hundred milliseconds.
5. **First-request warmup.** The first request through a fresh interpreter/JIT runs slower than steady state (Python bytecode caching, JIT warmup in JVM/Go-with-PGO, connection establishment).

The **cold-start penalty** is the extra latency a cold-served request pays over a warm-served one: roughly phases 2 + 3 + 4 + (the warmup delta of 5). For the services in this course:

- A lean **Go** service in a distroless image: ~150–400 ms cold-start penalty.
- A typical **Python + FastAPI + uvicorn** service in a slim image: ~800 ms – 2 s.
- A **Python service that loads an ML model** at startup: 3–15 s, sometimes worse.

**Startup CPU boost** (`startup_cpu_boost = true` in the v2 service) temporarily allocates extra CPU during instance startup, which meaningfully cuts phases 3–4 for CPU-bound init. Turn it on for any service where init is non-trivial; it is nearly free because it only applies during the (brief) startup window.

> The single highest-leverage cold-start fix is **shrink the image and defer heavy init**. Before you reach for `min-instances`, ask: is my image 1 GB because I shipped the build toolchain into the runtime stage? Am I importing modules I only need on one endpoint at module-import time? A multi-stage build and lazy imports often turn a 4-second cold start into an 800 ms one, which changes the break-even math below in your favor — sometimes enough that you do not need `min-instances` at all.

## 2.2 — How often do you actually pay a cold start?

The cost of cold starts depends on **how many requests are cold-served**, which depends on your traffic shape and Cloud Run's scaling behavior. You do not pay a cold start per request — you pay one when traffic forces a scale-up from a cold state. The rough model:

- **Steady, continuous traffic:** once the service is warm and `max-instances` is high enough, almost no requests are cold-served. Cold starts happen only at scale-up boundaries and after an idle period. Cold-start cost is low; `min-instances` buys little.
- **Bursty traffic after idle:** every burst that arrives to a scaled-to-zero service pays a cold start on its leading edge. If you get one burst per hour after idling, you pay ~24 cold starts/day on the first request of each burst (and possibly more as the burst forces additional scale-up).
- **Spiky fan-out:** a sudden spike that needs 10 new instances pays 10 cold starts more or less at once. The user-visible damage is the p99 during the spike.

The variable that matters is **`N_cold`: the number of requests per month that are served by a cold instance.** You estimate it from your traffic shape:

```
N_cold ≈ (number of scale-from-cold events per month)
         × (requests caught in the cold window per event)
```

For a service that idles to zero and gets a burst every hour around the clock, with ~3 requests caught before the first instance warms:

```
N_cold ≈ 24 events/day × 30 days × 3 requests = 2,160 cold-served requests/month
```

That is the number on the "cost of cold starts" side of the trade.

## 2.3 — The cost of keeping one instance warm

The other side: `min-instances=1` keeps one instance alive 24/7. You pay for it at the **idle rate** when no request is in flight, and at the active rate while it serves. The continuous idle cost dominates because the instance is idle most of the time (that's the whole point — it's warm and waiting). Using the Lecture 1 prices for a 1 vCPU / 512 MiB instance, billed continuously at the idle rate:

```
seconds_per_month = 86,400 × 30 = 2,592,000 s
idle vCPU: 2,592,000 × 1   × 0.0000025 = $6.48
idle mem:  2,592,000 × 0.5 × 0.0000025 = $3.24
min-instances=1 idle cost ≈ $9.72 / month per warm instance
```

So **one always-warm 1-vCPU instance costs about \$10/month**. (`min-instances=3` is ~\$29/month, three warm instances.) Note this is the *idle* rate — much cheaper than always-allocated active CPU — because a warm-but-idle instance is not actively serving. If you set `cpu_idle = false` (always-allocated CPU) the rate is the same idle rate when not serving; the difference is whether *background* work can run between requests, which a warm `min-instances` instance with always-allocated CPU can do.

> **A subtlety that trips people up.** `min-instances` keeps instances warm; it does **not** by itself make their CPU always-allocated. A `min-instances=1` instance still throttles CPU between requests unless you also set always-allocated CPU. If your warm instance needs to do background work (refresh a cache, keep a heartbeat) it needs always-allocated CPU; if it just needs to be ready to serve instantly, the default request-time CPU plus the warm container is enough — the container is up, the app is initialized, the pool is open, so the next request skips phases 2–4 entirely.

## 2.4 — The break-even formula

Now we balance the two sides. `min-instances=1` "pays for itself" when the value of the cold starts it eliminates exceeds the \$10/month it costs.

The cold-start cost has two flavors, and you pick the one that fits your service:

### Flavor A — cold starts cost you SLO budget (latency-quantified)

You have a p99 latency SLO. Cold-served requests blow past it. The question is whether eliminating them keeps you inside the SLO. This is not directly a dollar amount; it is a reliability constraint. The rule:

> If your cold-start rate would consume more than your error budget allows at p99, you set `min-instances ≥ 1` **regardless of cost**, because the alternative is missing the SLO. The \$10/month is just the price of meeting a commitment you already made.

Quantify it: if your SLO is "99% of requests under 400 ms" and your cold-start penalty is 1.5 s, then every cold-served request is an SLO violation. If `N_cold / N_total > 1%`, you are out of budget on cold starts alone and `min-instances` is mandatory. Compute `N_cold / N_total`:

```
N_total = R_month (total monthly requests)
cold_fraction = N_cold / N_total
if cold_fraction > error_budget_fraction:  min-instances ≥ 1 is required
```

For the bursty service above with `N_cold ≈ 2,160` and, say, `N_total = 1.0M` requests/month: `cold_fraction = 0.216%`. That is under a 1% budget — so cold starts alone do not break the SLO, and `min-instances` is a cost-optimization question, not a reliability mandate. Flavor B applies.

### Flavor B — cold starts cost you business value (dollar-quantified)

Each slow (cold-served) request has a business cost: a lost conversion, an abandoned page, a frustrated user, a timeout in a calling service that triggers a retry (which doubles load). Assign a dollar value `c_cold` to one cold-served request. Then:

```
monthly_cost_of_cold_starts = N_cold × c_cold
min-instances=1 pays for itself when:
    N_cold × c_cold  >  $9.72   (the warm-instance idle cost)
=>  break-even:  N_cold > $9.72 / c_cold
```

Worked examples:

- **User-facing checkout, c_cold = \$0.05** (a cold 1.5s start loses 5 cents of expected conversion value on average): break-even at `N_cold > 9.72 / 0.05 ≈ 195` cold starts/month. Our bursty service has 2,160 — **far past break-even. Set `min-instances=1`; it pays for itself 11× over.**
- **Internal admin tool, c_cold = \$0.0001** (nobody cares if the dashboard takes 2s once an hour): break-even at `N_cold > 97,200` cold starts/month. A service with 2,160 cold starts is nowhere near it — **leave `min-instances=0` and save the \$10.**
- **Webhook receiver feeding a retry-capable queue, c_cold ≈ \$0** (the caller retries; the cold start is invisible to humans): break-even at infinity — **never set `min-instances`; cold starts are free here.**

The formula in one line: **`min-instances=1` is worth it when `N_cold × c_cold > idle_cost`.** Estimate `N_cold` from your traffic shape, assign `c_cold` from your business context, compare to ~\$10/month. That is the whole decision, and it is defensible because every term is a number you can point at.

### Setting the floor in Terraform

The break-even decision lands as one number in the `scaling` block of the Cloud Run v2 service. Make it explicit and comment the *reasoning*, not just the value — a reviewer (or future you) should be able to read the cost decision off the Terraform:

```hcl
resource "google_cloud_run_v2_service" "checkout_api" {
  name     = "checkout-api"
  location = "us-central1"

  template {
    max_instance_request_concurrency = 80
    scaling {
      # min=1: N_cold ~2,400/mo x c_cold $0.05 = $120/mo of lost-conversion
      # value, vs ~$10/mo to keep one instance warm. Pays for itself ~12x.
      # See cost-model.md and Lecture 2 break-even. Floor=1 (not 2) because
      # business-hours bursts need ~1.6 instances warm -> rounds to 2 only at
      # peak, which the scheduled warm-up (below) handles.
      min_instance_count = 1
      max_instance_count = 10
    }
    containers {
      image = var.image
      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        startup_cpu_boost = true # shrink phase 3-4 of the cold start, nearly free
      }
    }
  }
}
```

Two things this snippet bakes in: the floor is a *justified* number (the comment cites the break-even), and `startup_cpu_boost = true` is on — because the cheapest cold-start fix is the one you apply before you pay for warmth. A reviewer who reads `min_instance_count = 1` with no comment cannot tell whether it was reasoned or cargo-culted; the comment is the difference between an engineering decision and a guess.

## 2.5 — Why `min-instances=3`, and how to think about higher floors

`min-instances=1` eliminates the cold start for the *first* concurrent request after idle. It does **not** help a burst that needs more than one instance at once: if a spike arrives needing 5 instances, you have 1 warm and pay 4 cold starts. `min-instances=3` keeps three warm, absorbing bursts up to `3 × concurrency` simultaneous requests without any cold start.

The cost is linear (`3 × $9.72 ≈ $29/month`), but the benefit is not: the right floor is roughly **your typical burst's instance count**, not a round number. Compute it:

```
typical_burst_rps × latency / concurrency = instances a burst needs
```

For a burst of 120 RPS, 80 ms latency, concurrency 80: `120 × 0.080 / 80 = 0.12` instances — one warm instance covers it; `min-instances=1` suffices. For a CPU-bound burst of 120 RPS, 80 ms, concurrency 8: `120 × 0.080 / 8 = 1.2` instances — you want `min-instances=2` to cover the burst warm. **CPU-bound services need higher `min-instances` floors** because their low concurrency means each instance covers fewer requests — the same reason CPU-bound services are expensive on Cloud Run (Lecture 1).

The challenge benchmarks `0`, `1`, and `3` precisely so you can *see* this: at `0` the burst is all-cold; at `1` the first instance's worth is warm and the rest cold; at `3` most realistic bursts are fully warm. You read the p99 at each floor and the monthly cost at each floor and pick the knee of the curve.

## 2.6 — Scheduling min-instances (the cost-aware refinement)

A blunt `min-instances=1` pays \$10/month to be warm at 3am when nobody is using the service. If your traffic is predictable — busy business hours, dead overnight — you can **schedule** the floor: `min-instances=1` (or 2, 3) during business hours, `min-instances=0` overnight. There is no native "scheduled min-instances" field; you implement it with a small **Cloud Scheduler → Cloud Run Admin API** job (or a tiny Cloud Function) that patches the service's `min-instances` on a cron. Two scheduler jobs — one at 08:00 setting the floor, one at 20:00 dropping it to 0 — cut the warm-instance cost by ~⅔ for a business-hours service.

Worked: business-hours-only `min-instances=1` (12h/day) costs `9.72 × (12/24) ≈ $4.86/month` instead of \$9.72. For a service that genuinely idles overnight, that halves the break-even threshold and makes `min-instances` worth it for a wider range of `c_cold`. The mini-project's stretch goal wires this scheduler.

```hcl
# Sketch: Cloud Scheduler job that sets the floor at 08:00 every weekday.
# (Full version in the homework. This is the shape.)
resource "google_cloud_scheduler_job" "warm_up" {
  name      = "ingest-warm-up"
  schedule  = "0 8 * * 1-5"          # 08:00 Mon-Fri
  time_zone = "America/Chicago"
  region    = var.region

  http_target {
    http_method = "PATCH"
    uri = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/services/ingest?updateMask=scaling.minInstanceCount"
    body = base64encode(jsonencode({ scaling = { minInstanceCount = 1 } }))
    oauth_token { service_account_email = google_service_account.scheduler.email }
  }
}
```

## 2.7 — Measuring the cold start honestly

The break-even math is only as good as your cold-start number, and most people measure it wrong. Three traps:

1. **They measure once.** A single cold request is noisy — the host may have a cached image, or not. Measure several cold starts (re-idling between each) and take the median, not the min and not the max.
2. **They include the load balancer and network in "cold start."** If you measure from `curl` on your laptop through a global LB, you are measuring cold start + TLS handshake + LB latency + your home network. To isolate the *instance* cold start, instrument the application: log a monotonic timestamp at process start and at first-request-served, and emit the delta.
3. **They confuse "first request slow" with "cold start."** The first request through a fresh interpreter is slower than steady state even on a *warm* instance (interpreter caches, connection establishment). Separate the **instance** cold start (phases 2–4) from the **first-request warmup** (phase 5) by sending a second request immediately after the first and comparing.

Here is the application-layer instrumentation that isolates app-init (phase 4), which is usually the biggest controllable piece:

```python
import time

# Captured at module import (process start). On a cold start this is "now";
# on a warm instance the process has been alive a while.
_PROCESS_START = time.monotonic()
_first_request_seen = False


@app.middleware("http")
async def cold_start_marker(request, call_next):
    global _first_request_seen
    response = await call_next(request)
    if not _first_request_seen:
        _first_request_seen = True
        # Time from process start to first served request == app-init + the
        # gap before traffic arrived. On a request that triggered a cold start
        # this is dominated by app-init (phase 4). Log it; scrape it later.
        init_ms = (time.monotonic() - _PROCESS_START) * 1000
        print(f'{{"event":"first_request","app_init_ms":{init_ms:.0f}}}')
    return response
```

To force a cold start for measurement on a `min-instances=0` service: deploy the revision, send no traffic for ~15 minutes (Cloud Run scales `min=0` services down within a few minutes of inactivity), then send one request. The `app_init_ms` log line on that request is your phase-4 number. Subtract it from the end-to-end cold latency to estimate phases 2–3 (image pull + container start). The challenge's harness does exactly this across `min-instances` 0, 1, and 3.

A practical reading of typical numbers from this measurement:

```
end-to-end cold latency (curl through *.run.app):   1,580 ms
  - app_init_ms (logged by the middleware):           620 ms   <- phase 4, yours to shrink
  - image pull + container start (the remainder):     760 ms   <- phase 2-3, shrink the image
  - network + TLS + LB (measured separately, warm):   200 ms   <- not "cold start"
warm p50 (steady state):                                42 ms
=> cold-start PENALTY = cold (1,580 - 200 network) - warm 42 ≈ 1,338 ms
```

That 1,338 ms penalty is the number you plug into the SLO check (does it bust the budget?) and the lever you attack (shrink the 620 ms app-init with lazy imports, shrink the 760 ms image pull with a multi-stage slim build).

## 2.8 — A portfolio example: setting floors across a fleet of services

The break-even is not a per-service ritual you do once; on a real platform you do it across a portfolio and the answers differ. Consider four Cloud Run services a team runs:

| Service | Traffic shape | Cold-start penalty | `N_cold`/mo | `c_cold` | Flavor | Decision |
|---|---|---|---|---|---|---|
| `checkout-api` | bursty, user-facing, business hours | 1.3 s | ~2,400 | \$0.05 | B | `min=2` business hours (scheduled), `min=0` overnight |
| `ingest` (this week) | steady-ish business hours, near-zero overnight | 1.2 s | ~2,000 | \$0.002 | B | `min=1` business hours; cold starts feed a retrying client |
| `admin-dashboard` | a few hits/hour, internal | 1.8 s | ~700 | \$0.0001 | B | `min=0`; nobody cares about a 2 s dashboard once an hour |
| `webhook-receiver` | random, feeds a queue with retries | 0.9 s | ~10,000 | ~\$0 | B | `min=0`; the caller retries, cold starts are invisible |

Run the arithmetic on two of them:

- **`checkout-api`:** `N_cold × c_cold = 2,400 × $0.05 = $120/month` of cold-start cost, against `min=2` costing `2 × $9.72 × (12/24 scheduled) ≈ $9.72/month`. The warmth pays for itself **12× over**, and the floor is 2 (not 1) because morning-ramp bursts need ~2 instances warm (`burst_rps × latency / concurrency` worked out to ~1.6, rounded up). Easy yes.
- **`admin-dashboard`:** `N_cold × c_cold = 700 × $0.0001 = $0.07/month` of cold-start cost, against `$9.72/month` for one warm instance. The warmth costs **140× more than the cold starts it eliminates**. Easy no — `min=0`.

The lesson: **the same company, the same week, the same engineer ships `min=2` on one service and `min=0` on another, and both are correct, because the break-even terms differ.** A team that sets `min=1` on everything "to be safe" is burning money on the dashboards and the webhook receivers; a team that sets `min=0` on everything is missing SLOs on checkout. The break-even is the discipline that gets each one right.

## 2.9 — The decision procedure, end to end

When someone asks "should this service set `min-instances`?", run this procedure out loud:

1. **Measure the cold-start penalty.** Deploy at `min-instances=0`, hit it cold (wait past the idle window), and measure the cold-served request latency minus the warm latency. The challenge harness does this with `hey` and timestamp inspection.
2. **Try to shrink it first.** Multi-stage build, distroless/slim base, lazy imports, startup CPU boost. Re-measure. Often this alone solves the problem.
3. **Estimate `N_cold`** from your traffic shape (scale-from-cold events × requests caught per event).
4. **Classify the cost of a cold start.** Is it an SLO-budget problem (Flavor A) or a business-value problem (Flavor B)?
   - Flavor A: if `N_cold / N_total > error_budget`, `min-instances ≥ 1` is mandatory.
   - Flavor B: `min-instances=1` pays for itself when `N_cold × c_cold > $9.72`.
5. **Pick the floor** from your typical burst's instance count (`burst_rps × latency / concurrency`), rounding up. CPU-bound → higher floor.
6. **Consider scheduling** the floor if traffic is predictable, to recover the overnight idle cost.
7. **Write the number and the trigger.** "We set `min-instances=1` during business hours; it costs ~\$5/month and eliminates ~2,000 cold starts worth ~\$0.05 each. We revisit the floor if p99 during morning ramp exceeds 400 ms."

## 2.10 — Common mistakes

- **Setting `min-instances` to fix a problem that's really image bloat.** A 4-second cold start from a 1.5 GB image is an image problem. `min-instances=10` masks it expensively; a multi-stage build fixes it cheaply. Always shrink first.
- **Confusing `min-instances` with `cpu_idle`.** `min-instances` keeps the container alive; `cpu_idle=false` (always-allocated CPU) lets it use CPU between requests. They are orthogonal. A warm instance with throttled idle CPU still serves the next request instantly (the app is initialized) — you only need always-allocated CPU if the instance does *background* work.
- **Setting `min-instances` high "to be safe" without computing the burst size.** Three warm instances at \$29/month for a service whose bursts never exceed one instance's capacity is \$19/month of waste. Compute the burst instance count.
- **Forgetting `min-instances` interacts with `max-instances` and DB connections.** A warm instance opens its connection pool at startup. `min-instances=3` means 3 pools open continuously against Cloud SQL even at zero traffic. Size the pool and `max-instances` against the database's connection limit (the mini-project does this explicitly).
- **Ignoring that `min-instances` is per-revision and per-region.** Deploying a new revision with traffic at 0% does not keep the new revision warm. In a multi-region setup (capstone), each region has its own floor — the capstone uses `min-instances=1` in the primary region and `0` in standby for exactly this cost reason.

## 2.11 — The reflexes to internalize this week

- **`min-instances=1` costs ~\$10/month per warm 1-vCPU instance.** Memorize the order of magnitude; it anchors every break-even.
- **The break-even is `N_cold × c_cold > idle_cost`.** Estimate cold starts from traffic shape, assign a dollar value per cold start from business context, compare to \$10.
- **SLO-budget cold starts are a mandate, not a trade.** If cold starts alone bust your error budget, you set the floor regardless of cost.
- **Shrink the image before you buy warmth.** A multi-stage build and lazy imports move the break-even in your favor for free.
- **Pick the floor from burst instance count, not a round number.** CPU-bound services need higher floors.
- **Schedule the floor when traffic is predictable.** Two Cloud Scheduler jobs recover the overnight idle cost.

## 2.12 — Language and runtime: the cheapest way to move the break-even

The single most under-used lever for the `min-instances` decision is **the language and image you ship**, because it changes the cold-start penalty — which is in the numerator of every break-even you compute. Two services with identical traffic and identical `c_cold` can land on opposite sides of the threshold purely because one cold-starts in 1.5 s and the other in 250 ms.

The 2026 rough ranges, instance cold start (phases 2–4), for a service that opens a DB pool at startup:

| Runtime / image | Typical cold start | Why |
|---|---|---|
| Go, static binary, distroless/scratch (~15–40 MB) | 150–400 ms | Tiny image (fast pull), no interpreter, instant process start, minimal init. |
| Java, JIT, slim JRE (~150–300 MB) | 2–6 s | Large image, JVM startup, classloading; AOT (GraalVM native-image) collapses this to Go-like numbers. |
| Node.js, slim (~80–150 MB) | 0.5–1.5 s | Moderate image, fast V8 startup, `require` graph dominates. |
| Python + uvicorn, slim (~120–250 MB) | 0.8–2 s | Moderate image, interpreter + import graph; heavy imports (pandas, ML) push it to many seconds. |
| Python + ML model loaded at startup (~1–3 GB) | 3–15 s+ | Huge image (slow pull) + model deserialization in app-init. |

What this means for the break-even, concretely. Take the bursty service from §2.4 (`N_cold ≈ 2,160`, checkout-grade `c_cold = $0.05`):

- Shipped as **Python + uvicorn** with a 1.5 s cold start: cold starts cost `2,160 × $0.05 = $108/month` of lost value, so `min=1` (\$10) is an easy yes — you pay \$10 to save \$108.
- Re-shipped as **Go distroless** with a 250 ms cold start: a 250 ms cold-served request is barely worse than warm; `c_cold` collapses toward ~\$0.005 (a quarter-second blip rarely loses a conversion). Now cold starts cost `2,160 × $0.005 = $10.8/month` — right at the break-even, and you might leave `min=0` and save the \$10 entirely.

So the *same workload* wants `min=1` in Python and arguably `min=0` in Go, because the runtime moved the cold-start penalty across the threshold. This is why the week's Go stretch goal exists: **rewriting a hot, cold-start-sensitive service in Go can be cheaper than paying for warmth in Python** — the engineering cost is one-time, the `min-instances` cost is monthly and forever. For a service that runs for years, the math often favors the rewrite. Always consider "shrink the cold start" (image + language + lazy init) *before* "buy warmth," because shrinking is a one-time cost and warmth is a recurring one.

## 2.13 — The multi-region floor (a preview of the capstone)

The capstone runs the ingest service in two regions: `us-central1` (primary) and `us-east1` (standby). The `min-instances` decision is *per region*, and the cost-aware answer is asymmetric:

- **Primary region: `min-instances=1` (or scheduled `=2` at peak).** This region takes all the traffic in steady state; you want it warm so the first request after any lull is fast. You pay the ~\$10/month (or scheduled less) and it pays for itself on real traffic.
- **Standby region: `min-instances=0`.** It takes traffic only during a failover. Keeping it warm 24/7 would double your warm-instance bill for capacity you use a few minutes a year. The trade: when failover happens, the standby pays a cold start on its first requests. That is acceptable *because failover is already a degraded event* — a 1.5 s cold start on the first post-failover request is invisible next to the failover itself, and the standby warms up within seconds as traffic shifts.

The arithmetic that justifies the asymmetry: if failover happens, say, twice a year for ~10 minutes each, the standby's cold-start exposure is `~2 × (a handful of cold requests)` per year — `N_cold` near zero. By the break-even, `min-instances=0` on the standby is correct by a wide margin. Setting it to `1` "for safety" would cost ~\$120/year to eliminate cold starts that occur during events that are already degraded. **Match the floor to the region's role:** warm where traffic lives, cold where capacity merely waits. You will implement exactly this in the capstone; the break-even you learn here is what makes the asymmetry defensible rather than arbitrary.

## 2.14 — The one-page cheat sheet

When you are in a review and need the answer fast, this is the whole lecture compressed:

- **Idle cost of one warm 1-vCPU instance:** ≈ **\$10/month** (`$6.48` vCPU + `$3.24` mem at the idle rate). `min=3` ≈ \$29/month. Memorize this; it anchors everything.
- **Break-even (business-value):** set `min≥1` when **`N_cold × c_cold > $10/month`**.
- **Break-even (SLO-budget):** set `min≥1` (mandatory) when **`N_cold / N_total > error_budget`** at p99 with a cold-start penalty that violates the SLO.
- **`N_cold`** = scale-from-cold events/month × requests caught per event. Estimate from traffic shape.
- **Floor size** = ceil(`burst_rps × latency / concurrency`). CPU-bound (low concurrency) → higher floor.
- **Before you buy warmth:** shrink the image (multi-stage slim), defer heavy imports, turn on `startup_cpu_boost`, consider a faster runtime (Go). These are one-time costs; warmth is recurring.
- **Schedule the floor** for predictable traffic: Cloud Scheduler → Admin API `services.patch` at start/end of business hours. Recovers the overnight idle cost.
- **Multi-region:** warm the primary (`min=1`), keep the standby cold (`min=0`) — failover is already degraded, so a cold start there is invisible.
- **Always write the number and the trigger.** "min=1, costs ~\$5/mo scheduled, eliminates ~2k cold starts worth ~\$0.05 each; revisit if morning-ramp p99 > 400 ms."

Sanity table for the common service archetypes:

| Archetype | `c_cold` | Typical `min-instances` |
|---|---|---|
| User-facing checkout / login (conversions at stake) | \$0.01–0.10 | 1–3, scheduled |
| Internal API feeding retrying clients | ~\$0.001 | 0–1 |
| Internal dashboard / admin tool | ~\$0.0001 | 0 |
| Webhook / queue feeder (caller retries) | ~\$0 | 0 |
| Standby region (failover only) | ~\$0 | 0 |

## 2.15 — What we did not cover

This lecture treats `min-instances` as a single-region knob. The capstone's multi-region story — `min-instances=1` in the primary region for warmth, `min-instances=0` in the standby region to keep it cheap until failover — is a Week 14 / capstone refinement that builds directly on this break-even math. We also did not cover **CPU-always-allocated background processing** in depth (a warm instance that proactively does work between requests); that is a pattern you reach for rarely, and we name it here only so you know `min-instances` and `cpu_idle` are different levers. For this week, the single-region break-even is the skill: measure the cold start, estimate the cold-start rate, assign a cost, compare to \$10/month, and write the number.

---

## Lecture 2 — checklist before moving on

- [ ] I can name the five phases of a cold start and identify which I control (image size, app init).
- [ ] I can estimate `N_cold` (monthly cold-served requests) from a traffic shape.
- [ ] I can compute the idle cost of `min-instances=1` (~\$10/month per 1-vCPU instance) and `=3` (~\$29).
- [ ] I can apply the break-even `N_cold × c_cold > idle_cost` and distinguish SLO-budget (Flavor A) from business-value (Flavor B) cold-start cost.
- [ ] I can pick the right floor from a burst's instance count and explain why CPU-bound services need higher floors.
- [ ] I can sketch a Cloud Scheduler job that schedules the floor for business hours.

If any box is unchecked, return to that section. The challenge this week makes you measure all of this on a real service.

---

**References cited in this lecture**

- Cloud Run — "About instance autoscaling" (min/max instances): <https://cloud.google.com/run/docs/about-instance-autoscaling>
- Cloud Run — "Configure minimum instances": <https://cloud.google.com/run/docs/configuring/min-instances>
- Cloud Run — "Tips for general development" (cold starts, lazy init): <https://cloud.google.com/run/docs/tips/general>
- Cloud Run — "Startup CPU boost": <https://cloud.google.com/run/docs/configuring/services/cpu#startup-boost>
- Cloud Run — CPU allocation (always-allocated vs request-time): <https://cloud.google.com/run/docs/configuring/cpu-allocation>
- Cloud Run Admin API v2 (`services.patch`, for scheduled min-instances): <https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services/patch>
- Cloud Run pricing: <https://cloud.google.com/run/pricing>
