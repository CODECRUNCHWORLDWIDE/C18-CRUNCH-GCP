# Lecture 1 — The Serverless Cost Curve: Where Cloud Run Beats GKE and Where GKE Beats Cloud Run

> **Reading time:** ~75 minutes. **Hands-on time:** ~45 minutes (you build a cost model in a spreadsheet and plot the crossover).

This is the lecture that earns you the right to say "we should run this on Cloud Run" — or "we should run this on GKE" — in an architecture review and be believed. The argument for serverless is almost always made on feeling: "Cloud Run is simpler," "Kubernetes is overkill," "serverless is cheaper." Sometimes each of those is true. The senior move is to stop asserting and start computing. By the end of this lecture you can model the monthly cost of a workload on Cloud Run as a function of request rate and CPU-seconds-per-request, model the same workload on a committed GKE footprint, draw both lines on the same axes, and point at the request rate where they cross. That crossing is the decision.

We are going to do this with 2026 list prices, in `us-central1`, with the math written out so you can re-run it for your own numbers. Prices change; the *shape* of the curve does not. Always check the live pricing pages (linked at the end) before you commit a number to a review — but learn the shape here so the numbers mean something when you look them up.

## 1.1 — What you are actually paying for on Cloud Run

Cloud Run bills you on four components. You must know all four or your model is wrong.

1. **vCPU-time.** Billed per vCPU-second while an instance is "active." Whether an instance is active depends on the CPU allocation model (more on this in a moment). In the **request-based billing** model, an instance is active only while it is handling at least one request (plus a short post-request tail). In the **instance-based billing** (always-allocated) model, an instance is active for its entire lifetime.
2. **Memory-time.** Billed per GiB-second, on the same "active" clock as vCPU-time.
3. **Requests.** A small per-request fee. At normal request volumes this is a rounding error next to vCPU and memory; at extreme volumes (billions of requests) it starts to matter.
4. **Networking.** Egress, the same as everywhere on GCP. Usually small for an internal service; we will hold it constant and ignore it in the crossover model, then add it back as a sanity check.

The 2026 `us-central1` list prices we will use throughout (Tier 1 region, after the always-free allowance, request-based billing):

| Component | Price |
|---|---|
| vCPU | \$0.000024 / vCPU-second (active) |
| Memory | \$0.0000025 / GiB-second (active) |
| Requests | \$0.40 / million requests |
| Idle vCPU (always-allocated, no request) | \$0.0000025 / vCPU-second |
| Idle memory (always-allocated, no request) | \$0.0000025 / GiB-second |

Two facts about that table decide everything downstream:

- **The active vCPU rate is ~10× the idle vCPU rate.** When CPU is allocated only during requests, you pay the high rate but only while requests run. When CPU is always-allocated, you pay the low idle rate continuously plus the high rate during requests. This is the lever the `min-instances` decision pulls (Lecture 2).
- **Memory is cheap relative to CPU.** A typical request-serving instance is CPU-bound on cost, not memory-bound. Do not over-rotate on the memory line; size memory for correctness (no OOMs) and optimize the CPU line.

### The request-based cost formula

For a service in request-based billing, the monthly compute cost is:

```
monthly_cost ≈ R_month × s_req × ( vCPU_count × price_vcpu_active
                                 + mem_gib  × price_mem_active )
             + R_month × price_per_request
```

where:

- `R_month` = requests per month
- `s_req` = mean wall-clock seconds an instance spends actively serving one request's "share" of compute. **This is the subtle term.** It is *not* the request latency. Because up to `concurrency` requests share one active instance simultaneously, the billed CPU-seconds per request is roughly `latency / concurrency` for the CPU-time component, *if* the instance stays saturated. We will be careful with this below.

Let us make it concrete. Suppose:

- A request takes **100 ms** of wall-clock latency, of which the instance is "active" the whole time.
- The instance is configured with **1 vCPU, 512 MiB**.
- Concurrency is **80** and the instance is well-saturated (always ~80 in flight).
- Traffic is **40 requests/second sustained**, all month: `R_month = 40 × 86400 × 30 ≈ 103.7M` requests.

With concurrency 80 and 40 RPS, the math says you need `40 × 0.100 = 4` request-seconds of capacity per second, and one instance at concurrency 80 provides up to `80 × (1/0.100) = 800` requests/second of capacity — so **one instance covers this easily**, and it is active essentially 100% of the time because requests are continuous.

For a continuously-active single instance, the cleaner way to compute cost is **instance-time**, not request-time:

```
active_instance_seconds_per_month ≈ instances × seconds_in_month
                                   = 1 × (86400 × 30) = 2,592,000 s
vCPU cost  = 2,592,000 × 1   × 0.000024  = $62.21
mem  cost  = 2,592,000 × 0.5 × 0.0000025 = $3.24
request cost = 103.7M × ($0.40 / 1M)     = $41.48
TOTAL ≈ $106.93 / month
```

At 40 RPS, this service costs about **\$107/month** on Cloud Run. Hold that number; we will compare it to GKE.

> **The trap in the formula.** People model Cloud Run as `requests × latency × price` and forget that concurrency amortizes CPU across simultaneous requests. If you bill 100 ms of 1 vCPU *per request* at 40 RPS, you get `40 × 0.100 × 1 × 0.000024 × 2.592M = $248/month` — more than 2× too high, because you double-counted the CPU that 80 concurrent requests share. **Always model Cloud Run as active-instance-seconds, not as request-seconds, once the instance is saturated.** The request-seconds formula is only correct in the low-traffic regime where each request gets its own under-utilized instance.

## 1.2 — What you are actually paying for on GKE

GKE cost is the opposite shape: you pay for **committed node capacity**, mostly independent of request rate, plus a small control-plane fee.

The 2026 `us-central1` list prices we will use:

| Component | Price |
|---|---|
| GKE control plane (per cluster, beyond the one free zonal cluster) | \$0.10 / hour ≈ \$73 / month |
| `e2-standard-2` (2 vCPU, 8 GiB) on-demand | ~\$0.067 / hour ≈ \$48.9 / month |
| `e2-standard-2` **spot** | ~\$0.020 / hour ≈ \$14.6 / month (≈ 70% off) |
| `e2-standard-4` (4 vCPU, 16 GiB) on-demand | ~\$0.134 / hour ≈ \$97.8 / month |

The defining property: **a node costs the same whether your pods are busy or idle.** A GKE service that handles 1 RPS and a GKE service that handles 1,000 RPS cost the same if they run on the same nodes — until the 1,000-RPS service needs to scale out and add nodes. Cost on GKE is a **step function of provisioned capacity**, and capacity is provisioned for your *peak*, not your average.

A minimal production-shaped GKE footprint for one stateless service (the kind we would actually deploy after Week 06):

- One **regional** Standard cluster: control plane \$73/month (the first zonal cluster is free, but regional control planes and any cluster beyond the first are billed; we model the realistic case where you already have a billed cluster).
- A node pool that can survive a node loss: **2 nodes minimum** for any service you care about (one node draining during an upgrade should not take you to zero).
- Use **spot** nodes where the workload tolerates preemption (stateless, fronted by a retry-capable LB — which describes our service).

Two `e2-standard-2` spot nodes plus a shared control-plane fee:

```
control plane:        $73.00 / month   (amortized; shared across all services on the cluster)
2 × e2-standard-2 spot: 2 × $14.60 = $29.20 / month
TOTAL (this service's slice) ≈ $102.20 / month   if it has the cluster to itself
```

But here is the thing that makes the GKE side genuinely cheaper at scale: **the control plane is a fixed cost amortized across every service on the cluster.** If ten services share that regional cluster, each one's slice of the control-plane fee is \$7.30, not \$73. And the spot node pool that runs our one service can also run nine others through bin-packing. The marginal cost of adding the eleventh service to an existing cluster is *the pod's resource requests*, not a whole new \$102/month footprint.

## 1.3 — Drawing the curve

Now we put both on the same axes. The x-axis is **sustained request rate** (RPS). The y-axis is **monthly cost (\$)**. We hold the request shape fixed: 100 ms latency, 1 vCPU / 512 MiB per instance equivalent, concurrency 80.

**Cloud Run** (request-based billing, `min-instances=0`):

- Cost rises roughly **linearly** with request rate, because you pay for active-instance-seconds and active-instance-seconds scale with traffic.
- It starts at essentially **\$0** when traffic is zero (scale to zero — you pay nothing).
- At 40 RPS we computed ≈ \$107/month. At 80 RPS it roughly doubles the compute portion (you need ~2 active instances or one busier one) to ≈ \$190/month. At 4 RPS it is ≈ \$15/month. At 0.4 RPS it is a few dollars.

**GKE** (regional Standard, spot, dedicated to this service):

- Cost is roughly **flat** at ≈ \$102/month across the whole low-to-moderate range, because the two-node spot pool absorbs everything up to its capacity regardless of request rate.
- It only rises when the service's peak exceeds the node-pool capacity and the autoscaler adds nodes — a step, not a slope.

Plotting these (you will do this in the hands-on section):

```
cost ($/mo)
  220 |                                          Cloud Run (min=0)  ╱
      |                                                          ╱
  180 |                                                       ╱
      |                                                    ╱
  140 |                                                 ╱
      |                                              ╱
  102 |======================================== GKE (2× e2-std-2 spot, dedicated)
      |                                     ╱
   60 |                                  ╱
      |                               ╱
   20 |                            ╱
      |                         ╱
    0 |____________________╱_______________________________________  RPS
      0      4      8     16     24     32     40     48     56
                              ↑ crossover ≈ 38 RPS (this shape)
```

For *this* request shape and *this* GKE footprint, the lines cross around **38 RPS sustained**. Below it, Cloud Run is cheaper. Above it, dedicated GKE is cheaper. That single number — "the crossover is ~38 RPS for a dedicated cluster" — is worth more in a review than any amount of "serverless is simpler."

But you must immediately qualify it, because two adjustments move the crossover dramatically:

### Adjustment 1 — Shared cluster moves GKE's line *down*

If the GKE cluster already exists and is shared, this service's marginal cost is not \$102 — it is the spot capacity for its pod requests, maybe \$15–30/month, with the control plane already paid for by other tenants. That pushes GKE's effective line down toward \$20–30 flat, which pushes the crossover **down to ~10 RPS or lower**. *On a cluster you already run, GKE wins much sooner.* This is why mature platform teams that already operate a GKE fleet put almost everything on it: the marginal node cost is tiny and they have already paid the operational tax.

### Adjustment 2 — Idle traffic moves Cloud Run's line *down to zero*

If the service is idle most of the time — a nightly batch endpoint, an internal admin tool, a webhook receiver that fires twice an hour — Cloud Run's `min-instances=0` cost approaches **\$0**, while GKE pays full freight for nodes that sit idle all night. For bursty, low-duty-cycle, or scale-to-zero workloads, **Cloud Run wins decisively and the crossover is irrelevant** because you never approach it. The classic example: a service that gets 1,000 requests in a 10-minute window once a day and nothing the rest of the time. On Cloud Run it costs cents. On GKE it costs a full month of node-time to be ready for ten minutes.

## 1.4 — The four-quadrant decision framework

Stop thinking "Cloud Run vs GKE" as a single axis. There are two axes that matter, and they make four quadrants:

- **Duty cycle** (how much of the day the service is actually busy): low → high.
- **Existing platform** (do you already run a GKE fleet?): no → yes.

```
                     No existing GKE fleet        Existing GKE fleet
                  ┌────────────────────────────┬────────────────────────────┐
  Low duty cycle  │  CLOUD RUN.                 │  CLOUD RUN.                 │
  (idle a lot)    │  Scale to zero. Pay         │  Even with a fleet, paying  │
                  │  nothing overnight. The     │  for idle pods all night    │
                  │  textbook serverless win.   │  beats a node you reserve.  │
                  ├────────────────────────────┼────────────────────────────┤
  High duty cycle │  IT DEPENDS — run the       │  GKE.                       │
  (busy 24/7)     │  numbers. Often Cloud Run   │  Marginal node cost is tiny │
                  │  if you don't want to       │  on a paid-for cluster.     │
                  │  operate Kubernetes; GKE    │  Bin-pack it onto the fleet.│
                  │  past the crossover RPS.    │  Below ~10 RPS, GKE wins.   │
                  └────────────────────────────┴────────────────────────────┘
```

Only one quadrant is a genuine "run the numbers" coin-flip: **high duty cycle, no existing fleet.** That is where the crossover RPS is the deciding number. In the other three quadrants the decision is usually clear before you compute anything — but you still compute, because reviews reward numbers and punish assertions.

## 1.5 — The non-cost factors that override the curve

Cost is the *default* tiebreaker, not the only factor. Several considerations override the curve outright. Name these in a review so nobody thinks you only know how to multiply.

- **You need a feature Cloud Run does not have.** GPUs were Cloud Run-unavailable for years (they exist on Cloud Run in 2026 for inference, but with constraints); a privileged sidecar; a `DaemonSet`-style per-node agent; a workload that needs to hold long-lived stateful connections beyond Cloud Run's request/timeout model; gRPC bidirectional streaming with very long sessions; raw UDP. If you need it and Cloud Run can't, the curve is moot — you're on GKE (or GCE).
- **Request timeout.** Cloud Run's per-request timeout maxes out at 60 minutes (and the practical sweet spot is far lower). A request that legitimately runs for hours is a **Cloud Run job**, not a service — or it belongs on GKE / Batch. Know the difference: long *request* → reconsider the shape; long *job* → Cloud Run job is fine.
- **Operational maturity.** If your team cannot operate Kubernetes — upgrades, node pools, PDBs, the on-call surface from Week 06 — then GKE's apparent cost win is a mirage, because the operational tax (engineer-hours, incidents) dwarfs the node-cost delta. Cloud Run's "Google operates the substrate" is worth real money that does not show on the compute bill. Quantify it: an engineer-week spent on a cluster upgrade is worth more than the \$80/month you saved on nodes.
- **Cold-start sensitivity.** A user-facing service where a 2-second cold start loses conversions cannot live on `min-instances=0` Cloud Run without `min-instances≥1` (Lecture 2) — which changes its cost line. A back-office service nobody notices stalling can. Match the duty-cycle quadrant to the latency SLO.
- **Connection limits to the database.** Cloud Run scales out to many instances; each instance opens its own connection pool. At high `max-instances` you can blow past Cloud SQL's connection limit. This is a real serverless footgun (we manage it in the mini-project by capping `max-instances` and sizing the pool). GKE's pod count is something you control more directly. Connection math is part of the decision.

## 1.6 — A worked example you can defend

Let us cost a realistic ingest service — the one you build in the mini-project. Requirements:

- Validates and persists incoming events to Postgres.
- Peak **60 RPS** for ~4 hours/day (business hours in one timezone), **5 RPS** the rest of the day, near-zero overnight.
- 80 ms p50 latency, mostly I/O-bound (waiting on Postgres) — so concurrency 80 is appropriate.
- p99 latency SLO of 400 ms; cold starts of ~1.5s are tolerable for the *first* request after idle but not desirable during business hours.
- No existing GKE fleet dedicated to it (greenfield product).

**Cloud Run model.** Compute the active-instance-seconds across the day's traffic shape:

- Business hours (4h = 14,400s) at 60 RPS, 80 ms, conc 80: need `60 × 0.080 = 4.8` request-seconds/s of capacity; one instance provides up to `80 / 0.080 = 1000` req/s — so ~1 instance, active ~100% of business hours. Active-instance-seconds ≈ 14,400.
- Shoulder hours (say 12h = 43,200s) at 5 RPS: `5 × 0.080 = 0.4` request-seconds/s — one instance, active a fraction of the time. With request-based billing and bursty arrival, model it as ~30% active: ≈ 13,000 instance-seconds.
- Overnight (8h): near zero. ≈ 0.

Daily active-instance-seconds ≈ `14,400 + 13,000 ≈ 27,400`; monthly ≈ `27,400 × 30 = 822,000` instance-seconds at 1 vCPU / 512 MiB:

```
vCPU:    822,000 × 1   × 0.000024  = $19.73
mem:     822,000 × 0.5 × 0.0000025 = $1.03
requests: ~ (60×14,400 + 5×43,200) × 30 = (864,000 + 216,000) × 30 = 32.4M  × $0.40/1M = $12.96
Cloud Run TOTAL ≈ $33.7 / month   (min-instances=0)
```

Add `min-instances=1` during business hours only (you can schedule this) for cold-start protection — Lecture 2 computes that delta; it adds a few dollars.

**GKE model (greenfield, dedicated).** Regional Standard, 2× `e2-standard-2` spot, dedicated control plane: ≈ **\$102/month** as computed earlier, flat.

**The verdict you write in the review:** *"At our traffic shape (60 RPS peak 4h/day, near-zero overnight, no existing fleet), Cloud Run costs ≈ \$34/month against ≈ \$102/month for a dedicated GKE cluster — a 3× saving — and scales to zero overnight where GKE pays full freight. We recommend Cloud Run. We will revisit if sustained traffic exceeds ~40 RPS around the clock, at which point the crossover analysis (see attached spreadsheet) favors moving to the shared platform cluster once one exists."* That is a defensible decision. It has a number, a crossover condition, and an exit trigger.

## 1.7 — The Cloud Run mechanics that the cost model rests on

Before you build the model, you must be able to read the Terraform that produces the costs, because every line in the `template` block maps to a term in the formula. Here is a Cloud Run v2 service with every cost-relevant knob set explicitly:

```hcl
resource "google_cloud_run_v2_service" "ingest" {
  name                = "crunch-ingest"
  location            = "us-central1"
  deletion_protection = false

  # ingress decides who can reach it. internal-and-cloud-load-balancing means
  # only the VPC and a Google Cloud LB can hit it -- the public *.run.app URL
  # is dead. This is the hook Week 08 attaches its load balancer to.
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    # CONCURRENCY: the cost-and-latency lever from Exercise 1. 80 is right for
    # this I/O-bound handler; it amortizes CPU across many waiting requests.
    max_instance_request_concurrency = 80

    # The autoscaler bounds. min=0 is the cheapest (scale to zero); it is also
    # the term Lecture 2's break-even decides. max caps both cost AND the number
    # of DB connection pools opened against Cloud SQL.
    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    # Per-request timeout. Cloud Run caps at 3600s; a request that runs longer
    # belongs in a job, not a service. Set it to your real p99.9, not the max.
    timeout = "30s"

    containers {
      image = var.image
      ports { container_port = 8080 }
      resources {
        limits = {
          cpu    = "1"      # 1 vCPU -> the vCPU term in the cost formula.
          memory = "512Mi"  # the GiB term; size for correctness, not cost.
        }
        # cpu_idle = true  -> request-time CPU (cheapest; CPU only while serving).
        # cpu_idle = false -> always-allocated (idle rate continuously; needed
        #                     only if the instance does background work).
        cpu_idle          = true
        startup_cpu_boost = true # cuts cold-start app-init; nearly free.
      }
    }
  }

  # Revisions + traffic splitting: a new deploy creates a new revision. You can
  # send 0% to it (a dark launch), then shift traffic gradually. Traffic on the
  # OLD revision keeps the OLD revision warm; the NEW revision at 0% is cold.
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}
```

Three mechanics in that file change how you reason about cost:

- **Revisions are immutable; traffic is a separate dimension.** Every change to the template mints a new revision. You can split traffic across revisions by percentage (canary, blue-green). The cost consequence: during a canary, you may be paying for *two* warm fleets if both revisions carry `min-instances`. Plan canaries to be short, or set the new revision's floor to 0 until it takes full traffic.
- **`timeout` is a cost and correctness boundary.** A request that hangs for the full timeout holds an instance's concurrency slot the whole time, reducing effective capacity and pushing the autoscaler to add instances (cost). A tight, honest timeout is a cost control. The 3600s maximum is for long-but-bounded request work; anything genuinely long-running is a *job*, which bills only while it runs and then exits.
- **`ingress` does not change compute cost but changes the whole security and edge story.** `internal-and-cloud-load-balancing` is what lets Week 08 put a load balancer (and Cloud Armor) in front while keeping the `*.run.app` URL dark. The mini-project sets this deliberately.

## 1.8 — A worked case where GKE wins, with the numbers

The lectures so far have leaned Cloud-Run-favorable because most *greenfield, low-duty-cycle* services are. Here is the opposite case, fully costed, so you can defend GKE when GKE is right.

A platform team runs a **fleet** of 25 microservices on one regional GKE Standard cluster. The cluster's node pool is 6× `e2-standard-4` spot nodes (24 vCPU, 96 GiB total), bin-packing all 25 services. One of those services, `pricing-engine`, is **CPU-bound** (40 ms of real compute per request, so concurrency must be ~6 to keep p99 healthy — the Exercise 1 lesson) and runs at a **sustained 50 RPS, 20 hours/day** (it's a back-of-house service feeding other services, busy whenever the business is).

**Cost on the existing GKE fleet:** `pricing-engine` requests, say, 0.5 vCPU / 512 MiB per pod and runs ~3 pods to cover 50 RPS at concurrency 6. That is 1.5 vCPU of the 24-vCPU pool. Its marginal cost is its slice of the spot nodes (~1.5/24 of 6× \$29/month spot ≈ \$11/month) plus 1/25 of the \$73 control plane (\$2.92/month). **Marginal cost ≈ \$14/month.** It is already running on a cluster the team operates anyway.

**Cost on Cloud Run:** CPU-bound at concurrency 6 means each instance covers `6 / 0.040 = 150` req/s of capacity — so one instance covers 50 RPS, but it is *active essentially 20 hours/day* because traffic is continuous. Active-instance-seconds ≈ `1 × 20 × 3600 × 30 = 2,160,000`. At 1 vCPU:

```
vCPU:    2,160,000 × 1   × 0.000024  = $51.84
mem:     2,160,000 × 0.5 × 0.0000025 = $2.70
requests: 50 × 20 × 3600 × 30 = 108M × $0.40/1M = $43.20
Cloud Run TOTAL ≈ $97.74 / month
```

**The verdict:** `pricing-engine` costs ≈ \$14/month on the fleet it already runs on, versus ≈ \$98/month on Cloud Run — a **7× saving on GKE**. The reasons compound: it's high duty cycle (no scale-to-zero benefit), it's CPU-bound (expensive on Cloud Run's per-active-second model), and the cluster already exists (marginal node cost is tiny). This is the bottom-right quadrant of the framework, and the numbers say GKE, decisively. *Write that in a review and nobody argues with you.*

## 1.9 — Building the model yourself (hands-on)

Open a spreadsheet (or write a small Python script — homework does the script version). Build two columns:

1. A **Cloud Run** column parameterized by: RPS, latency (s), vCPU, mem (GiB), concurrency, hours-per-day busy. Compute active-instance-seconds correctly (saturated-instance model, not request-seconds), multiply by the rates, add the per-request fee.
2. A **GKE** column parameterized by: node type, node count, spot (y/n), control-plane share. Compute the flat monthly cost.

Sweep RPS from 1 to 80 and find where the lines cross for:

- A dedicated GKE cluster (expect crossover ~35–40 RPS for the 100 ms / 1 vCPU shape).
- A shared cluster where this service's control-plane share is \$7.30 and it bin-packs onto existing spot nodes (expect crossover ~8–12 RPS).

Then change the request shape to **CPU-bound** (latency dominated by computation, concurrency must drop to ~8 to keep p99 in check — Exercise 1 shows why). Watch the Cloud Run line steepen sharply: with concurrency 8 instead of 80, you need 10× more active-instance-seconds for the same traffic, and the crossover moves **way down** — CPU-bound serverless is expensive, and the curve proves it.

This is the single most useful artifact you will build this week. Keep the spreadsheet; you will reuse it in the midterm architecture review at the end of Week 08 and in the capstone cost report.

## 1.10 — The reflexes to internalize this week

- **Model Cloud Run as active-instance-seconds, not request-seconds, once instances are saturated.** The request-seconds model double-counts CPU that concurrency amortizes.
- **Model GKE as committed capacity, not per-request cost.** Cost is a step function of provisioned nodes, sized for peak, flat across request rate until you scale out.
- **The crossover RPS is the number, and it moves.** A shared cluster pushes it down (GKE wins sooner); a low duty cycle makes it irrelevant (Cloud Run wins regardless).
- **Concurrency is a cost lever, not just a latency lever.** Halving concurrency roughly doubles Cloud Run cost at fixed traffic, because each instance amortizes CPU over fewer requests.
- **Name the non-cost overrides.** Feature gaps, request-timeout limits, operational maturity, cold-start sensitivity, and database connection limits override the curve. A review answer that is only arithmetic is incomplete.
- **Write the exit trigger.** Every "we chose Cloud Run" should come with "we revisit at X RPS sustained" and every "we chose GKE" with "the marginal cost on the fleet is Y." Decisions with triggers age well.

## 1.11 — What we did not cover (Lecture 2 picks it up)

This lecture held `min-instances` at 0 for the cost-curve baseline. That is the cheapest configuration and the one with the worst cold-start behavior. The moment you have a latency SLO that cold starts threaten, you reach for `min-instances ≥ 1`, which adds a continuous idle cost and changes the Cloud Run line. **Lecture 2 derives the `min-instances=1` break-even** — the request rate and cold-start sensitivity at which keeping one instance always warm pays for itself — and the challenge this week makes you benchmark it at `0`, `1`, and `3` on a real service. The cost curve you built here is the canvas; Lecture 2 paints the cold-start cost onto it.

---

## Lecture 1 — checklist before moving on

- [ ] I can list Cloud Run's four billing components and the ~10× gap between active and idle vCPU rates.
- [ ] I can compute Cloud Run monthly cost using the *active-instance-seconds* model and explain why the request-seconds model overcounts.
- [ ] I can compute a GKE footprint cost (control plane + spot nodes) and explain why it is flat across request rate.
- [ ] I can draw both lines and identify the crossover RPS for a given request shape.
- [ ] I can state how a shared cluster and a low duty cycle each move the crossover.
- [ ] I can name five non-cost factors that override the curve.
- [ ] I have built the two-column spreadsheet and found the crossover for both the dedicated and shared GKE cases.

If any box is unchecked, return to that section. Lecture 2 assumes you can model the baseline cost before we add cold-start cost on top.

---

**References cited in this lecture**

- Cloud Run pricing: <https://cloud.google.com/run/pricing>
- Cloud Run — "About instance autoscaling": <https://cloud.google.com/run/docs/about-instance-autoscaling>
- Cloud Run — "Container runtime contract": <https://cloud.google.com/run/docs/container-contract>
- Cloud Run — CPU allocation (always-allocated vs. request-time): <https://cloud.google.com/run/docs/configuring/cpu-allocation>
- GKE pricing: <https://cloud.google.com/kubernetes-engine/pricing>
- Compute Engine pricing (spot/on-demand machine rates): <https://cloud.google.com/compute/all-pricing>
- GCP Pricing Calculator (build your own model): <https://cloud.google.com/products/calculator>
