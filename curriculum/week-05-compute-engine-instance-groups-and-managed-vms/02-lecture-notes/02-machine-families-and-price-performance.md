# Lecture 2 — Machine Families and Price-Performance: Choosing E2/N2/N2D/C3/T2D and Defending It

> **Reading time:** ~75 minutes. **Hands-on time:** ~45 minutes (you launch one instance per family and benchmark requests-per-second-per-dollar).

Lecture 1 told you *when* a VM is the right primitive. This lecture tells you *which* VM, and — more importantly — it tells you how to *defend* the choice with a number instead of a habit. The single most common mistake junior engineers make on Compute Engine is picking the machine type they used last time, or the one that sounds fastest, and calling it a decision. It is not a decision; it is a default with a story attached. By the end of this lecture you will pick a machine family for a workload, justify it on **price-performance** (units of useful work per dollar, not vCPUs per dollar), and back the justification with a benchmark you ran yourself.

The thesis is one sentence: **the right machine family is the one that does your workload's actual work for the fewest dollars, and you cannot know which that is without measuring, because the cheapest per-vCPU-hour family frequently does less work per vCPU.**

## 2.1 — The vocabulary, precisely

Three words get used loosely and you must use them precisely, because the pricing pages and the Terraform attributes use them precisely.

- **Machine family** is a class of hardware and architecture: E2, N2, N2D, T2D, C3, C3D, C4. A family pins you to a CPU generation/vendor and a performance and pricing profile.
- **Machine series** is sometimes used interchangeably with family; Google's docs group families into *general-purpose* (E2, N-series, C-series, Tau), *compute-optimized* (C2, H3), *memory-optimized* (M-series), and *accelerator-optimized* (A-series, G2). For this week you live almost entirely in general-purpose.
- **Machine type** is a specific size within a family: `e2-medium`, `n2-standard-4`, `c3-standard-22`, `t2d-standard-8`. The number is (almost always) the vCPU count. The word — `standard`, `highmem`, `highcpu` — is the memory-to-vCPU ratio.

And one word that trips everyone: a **vCPU** on Compute Engine is **one hardware hyperthread**, not a full physical core. An `n2-standard-4` is 4 vCPUs = 2 physical cores with SMT. The exception worth knowing: on some C-series types you can request **a physical core per vCPU** (no hyperthread sharing) via the `visible_core_count`/`threads_per_core` controls, which matters for licensing and for latency-sensitive work. We will not need it this week, but you should not be surprised by it in an interview.

## 2.2 — The five families you must be able to defend

Here is the working set for 2026. Memorize the shape of each; the exact hourly rates drift, so always confirm against <https://cloud.google.com/compute/all-pricing> before you commit a number to a design doc.

### E2 — cost-optimized, the budget tier

E2 instances run on a mix of underlying hardware (Google schedules them on whatever is cheapest) and offer **shared-core** types (`e2-micro`, `e2-small`, `e2-medium`) where you get a fraction of a vCPU with bursting, plus standard types up to 32 vCPUs. E2 is the cheapest general-purpose family per vCPU-hour. The catch: you do not control the CPU generation, performance is the most variable of any family, and E2 does **not** earn sustained-use discounts (its price is already discounted). E2 has no local SSD and no GPU support.

**Reach for E2 when:** cost is the dominant constraint, the workload is not latency-sensitive, and variable performance is acceptable — dev/test fleets, low-traffic internal tools, cron-style batch that does not care about wall-clock jitter, and the control-plane bastions and CI runners of the world. The MIG you build this week uses `e2-medium` precisely because it is a lab and pennies matter.

### N2 — Intel general-purpose, the safe default

N2 runs on Intel Cascade Lake / Ice Lake. It is the boring, predictable, "nobody got fired for choosing it" family: consistent performance, the full feature set (local SSD, sustained- and committed-use discounts, custom machine types, larger sizes up to 128 vCPUs), and a well-understood single-thread performance profile. It is more expensive per vCPU than E2 or the AMD/Tau families.

**Reach for N2 when:** you want predictable Intel performance and a feature you know is on Intel, when a vendor benchmark or a license is validated against Intel, or when you simply do not have time to benchmark and want the default that will not embarrass you. N2 is the answer you give when the honest answer is "I have not measured yet and I need predictability now."

### N2D — AMD EPYC, the cheaper twin of N2

N2D is the AMD EPYC (Milan) counterpart to N2. Same general-purpose positioning, same feature set, typically **~10% cheaper per vCPU than N2** for broadly comparable performance, and it scales to 224 vCPUs. The trade-off is real but small: some workloads — particularly those tuned for Intel's AVX-512 or with hand-optimized Intel code paths — run measurably slower on EPYC, and a minority run *faster*. You do not know which without testing.

**Reach for N2D when:** your workload is ordinary general-purpose work (web/app servers, language runtimes like Go/Java/Python/Node that are not doing Intel-specific SIMD), and you want the ~10% discount. The decision rule: **default to N2D over N2 for stateless web/app tiers unless a benchmark shows your specific code regresses on EPYC.** That sentence has saved real teams six figures a year.

### T2D (Tau) — the price-performance king for scale-out

T2D is the Tau family, AMD EPYC Milan tuned specifically for **scale-out** workloads. Each vCPU is a **full physical core, not a hyperthread** — which is the whole trick. For workloads that scale by adding more instances and that are throughput-bound rather than single-thread-latency-bound (web front-ends, microservices, containerized app tiers, media transcoding farms), T2D frequently delivers **the best requests-per-second-per-dollar of any general-purpose family**, often beating N2 on price-performance by a wide margin. The limits: a max of 60 vCPUs, no local SSD, and it is genuinely a scale-out family — for a single big latency-sensitive process it is not the right shape.

**Reach for T2D when:** you have a horizontally-scaling, throughput-oriented service (exactly the kind that lives in a MIG behind a load balancer — *this week's mini-project*), and you care about cost per unit of served traffic. This is the family most teams *should* be defaulting their web tier to in 2026 and most are not, because they never benchmarked. (There is also **T2A**, the same idea on Arm/Ampere Altra — even cheaper, but only if your binary is Arm64. A Go service recompiles for Arm trivially; a pile of x86-only native dependencies does not. T2A is a stretch goal this week.)

### C3 — Sapphire Rapids, the performance and consistency tier

C3 runs on 4th-gen Intel Xeon (Sapphire Rapids) on Google's **Titanium** offload infrastructure — Titanium moves networking and storage processing off the host CPU onto dedicated hardware, which means more of the CPU you pay for goes to your workload and the network/storage performance is both higher and more consistent. C3 offers the best single-thread performance and the most consistent tail latencies in the general-purpose lineup, advanced local SSD (Titanium SSD), and high network bandwidth. It costs the most per vCPU of the families here.

**Reach for C3 when:** you have a latency-sensitive workload where p99 matters more than cost — a low-latency API tier, a game server, an in-memory cache or database that needs consistent CPU and network, or a workload that benefits from Sapphire Rapids accelerators (AVX-512, AMX for inference, DSA). The decision rule: **C3 is what you pick when the workload's value is in its tail latency, and you can prove the cheaper families miss your p99 target.** Do not reach for C3 because it is "the fast one"; reach for it because you measured a p99 violation on T2D/N2 and C3 fixes it.

(Briefly, so you are not surprised: **C3D** is the AMD Genoa sibling of C3 — same Titanium platform, EPYC silicon, often cheaper at the high end. **C4** is the newest Intel Granite/Emerald-Rapids generation on Titanium, the current top of the general-purpose performance curve. **H3** is compute-optimized for tightly-coupled HPC. The GPU families — A-series for H100/A100, G2 for L4 — are Week 12. You do not choose those this week.)

## 2.3 — Price-performance is a ratio, and you are measuring the wrong numerator if you measure vCPUs

Here is the mistake, stated as math. The seductive metric is:

```
cost-efficiency (wrong) = vCPUs per dollar-hour
```

By that metric E2 always wins and you would run everything on `e2-standard-32`. But "vCPU" is not what you sell. You sell *served requests*, *transcoded minutes*, *trained steps*, *processed rows*. The metric that actually matters is:

```
price-performance (right) = useful work per dollar-hour
                          = (work units / second) / (dollars / hour) × 3600
                          = work units per dollar
```

The numerator — work per second — is **not constant across families**, and that is the entire point. A T2D vCPU is a full core; an E2 vCPU is a throttled, shared hyperthread on whatever silicon was cheapest. For a CPU-bound web service, one T2D vCPU can do meaningfully more requests per second than one E2 vCPU. So even though T2D costs more per vCPU-hour, it can cost *less per request* — which is the number on the bill that scales with your traffic.

You cannot reason your way to the answer from the spec sheet. The spec sheet gives you the denominator (dollars per hour, which is published) and hides the numerator (work per second on *your* code, which only your benchmark knows). **A price-performance claim without a benchmark is a vibe.** The rest of this lecture makes you produce the benchmark.

## 2.4 — Discounts change the denominator: SUD and CUD

Before you benchmark, understand the two automatic levers on the dollar side, because they can swing a decision.

**Sustained-use discounts (SUD)** apply automatically to N2, N2D, C3, T2D, and the other non-E2 general-purpose families: if you run an instance for a large fraction of the month, Google discounts the price progressively, up to roughly 20–30% off the on-demand rate for a full month, with no action and no commitment. A MIG that holds a steady baseline of instances earns SUD on that baseline for free. (E2 does not earn SUD because its list price is already the discounted one.)

**Committed-use discounts (CUD)** are an explicit commitment: you promise to pay for a baseline amount of compute (resource-based CUD, tied to vCPU/RAM in a region/family) or a baseline dollar spend (spend-based CUD, more flexible) for **one or three years**, in exchange for a deeper discount — commonly ~37% for one year and ~55% for three years on resource-based commitments. CUD is the single biggest FinOps lever on a steady fleet, and it is also a trap if you commit to a family you later want to leave. Week 14 covers the FinOps math in depth; here, internalize the rule: **commit to the baseline you are certain you will run for the term; run the variable peak on on-demand or spot.**

The practical consequence for *this* week: when you compare families, compare them on the discount posture you will actually run in. If your production MIG holds a baseline 24/7, the relevant price is the SUD or CUD price, not the on-demand sticker. For the lab you run on-demand because you tear down nightly, but the *design doc* should cost the baseline at the committed rate.

## 2.5 — A worked decision, end to end

Let us make the abstract concrete with the exact workload you build this week: a **stateless Go HTTP service**, CPU-bound (it does a little JSON work and a small in-memory computation per request), behind an internal load balancer, scaling horizontally in a regional MIG, holding a steady baseline 24/7 with daily peaks.

Walk the decision:

1. **Is it general-purpose?** Yes — no GPU, no extreme memory ratio, no HPC interconnect. So we are choosing among E2, N2, N2D, T2D, C3. (Memory-optimized and accelerator families are out.)
2. **Is it scale-out and throughput-oriented?** Yes — it scales by adding instances, and we care about total served RPS, not single-request latency in microseconds. That points hard at **T2D** (full-core vCPUs, tuned for scale-out) as the price-performance favorite, with **N2D** as the predictable runner-up.
3. **Is p99 latency a hard product requirement?** Suppose our SLO is p99 < 200ms for a service that does ~5ms of work per request. That is loose; we are not tail-latency-bound. So **C3** is probably overkill — we would only pay its premium if a benchmark showed T2D/N2D missing the SLO under load, which at 5ms of work they will not.
4. **Is cost the dominant constraint, with variable performance acceptable?** For *production* serving real users, no — we will not run user traffic on E2's variable hardware. For the *lab*, yes — so the exercises use `e2-medium` because it is pennies and the point is the MIG mechanics, not the silicon.
5. **What is the discount posture?** Production holds a 24/7 baseline → we will buy a **resource-based CUD** on the baseline vCPU count in the chosen family (so picking T2D also commits us to T2D for a year — a real consideration) and run peak on on-demand T2D, with SUD applying to anything above the commitment that runs most of the month.

So the *design-doc* answer is: **T2D for production (full-core scale-out, best RPS/$, SUD on the baseline, 1-year CUD on the committed floor), N2D as the fallback if a benchmark shows our binary regresses on the Tau platform, E2 for the lab.** Notice every clause is defensible and every claim that depends on our code (step 2's "T2D wins on RPS/\$", step 3's "we are not tail-bound") is exactly the kind of claim §2.6 makes you verify.

## 2.6 — Hands-on: benchmark requests-per-second-per-dollar across families

Now produce the number. We will launch a single instance on three families, run an identical Go service and an identical load test against each, and compute RPS per dollar. This is the discipline the whole lecture exists to install.

### The service

Save this as `main.go`. It is intentionally CPU-bound per request — it hashes a small payload in a loop so that the benchmark measures *CPU* price-performance, which is what differs across these families. (A purely I/O-bound service would show almost no family difference, which is itself a lesson: if your workload is not CPU-bound, do not pay for CPU.)

```go
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log"
	"net/http"
	"os"
	"runtime"
)

// work simulates a few milliseconds of CPU-bound work per request by
// repeatedly hashing a buffer. Tune iterations so a single request takes
// a few ms on a modern core; this makes the benchmark CPU-price-bound.
func work(seed []byte, iterations int) string {
	buf := make([]byte, len(seed))
	copy(buf, seed)
	var sum [32]byte
	for i := 0; i < iterations; i++ {
		sum = sha256.Sum256(buf)
		copy(buf, sum[:])
	}
	return hex.EncodeToString(sum[:])
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	mux := http.NewServeMux()

	mux.HandleFunc("/work", func(w http.ResponseWriter, r *http.Request) {
		digest := work([]byte("crunch-gcp-week5"), 2000)
		fmt.Fprintf(w, "%s\n", digest)
	})

	// A trivial health endpoint the load balancer and autohealer can poll.
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})

	log.Printf("listening on :%s with GOMAXPROCS=%d", port, runtime.GOMAXPROCS(0))
	srv := &http.Server{Addr: ":" + port, Handler: mux}
	log.Fatal(srv.ListenAndServe())
}
```

### Launch one instance per family

Pick three families to compare — E2 as the budget baseline, N2D as the general-purpose default, and T2D as the price-performance candidate — at the **same vCPU count** so the comparison is fair. Build the binary for Linux, push it to the instance via the startup-script's fetch-from-GCS pattern you will formalize in Exercise 1, or for this quick test just `scp` it. For now, the fastest path is a startup script that builds in place:

```bash
# Build statically for Linux/amd64 so it runs on any of these families.
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o workserver main.go

ZONE="$(gcloud config get-value compute/region)-b"

for mt in e2-standard-4 n2d-standard-4 t2d-standard-4; do
  name="bench-${mt//./-}"
  gcloud compute instances create "$name" \
    --machine-type="$mt" \
    --zone="$ZONE" \
    --image-family=debian-12 \
    --image-project=debian-cloud \
    --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
    --metadata=enable-oslogin=TRUE \
    --no-address
done
```

Copy the binary to each and start it (over IAP, because there is no external IP):

```bash
for mt in e2-standard-4 n2d-standard-4 t2d-standard-4; do
  name="bench-${mt//./-}"
  gcloud compute scp ./workserver "$name":~/workserver \
    --zone="$ZONE" --tunnel-through-iap
  gcloud compute ssh "$name" --zone="$ZONE" --tunnel-through-iap \
    --command="chmod +x ~/workserver && PORT=8080 nohup ~/workserver >/tmp/srv.log 2>&1 & sleep 1"
done
```

### Load-test each, identically

From a fourth small instance *inside the VPC* (so you are not measuring your home internet), run `hey` against each backend's internal IP for a fixed duration at a fixed concurrency. Get the internal IPs:

```bash
gcloud compute instances list --format="table(name, networkInterfaces[0].networkIP, machineType.basename())"
```

Then, from the load generator, for each backend IP:

```bash
# 30 seconds, 50 concurrent connections, against the CPU-bound endpoint.
hey -z 30s -c 50 "http://<BACKEND_INTERNAL_IP>:8080/work"
```

`hey` prints a summary like:

```
Summary:
  Total:        30.0041 secs
  Requests:     184,233
  Requests/sec: 6140.27
  ...
Status code distribution:
  [200] 184233 responses
```

Record the `Requests/sec` for each family.

### Compute the number that matters

Now the price-performance ratio. Look up the on-demand hourly price for each `*-standard-4` type in your region on <https://cloud.google.com/compute/all-pricing> and fill the table. Illustrative numbers (your real ones will differ — **use yours**):

| Family | Type | RPS (measured) | \$/hour (your region) | RPS per \$/hour | Relative |
|---|---|---:|---:|---:|---:|
| E2 | `e2-standard-4` | 4,900 | 0.134 | 36,567 | 1.00× |
| N2D | `n2d-standard-4` | 5,800 | 0.155 | 37,419 | 1.02× |
| T2D | `t2d-standard-4` | 6,140 | 0.135 | 45,481 | **1.24×** |

The shape of the result — not the exact figures — is the lesson: **T2D, despite costing more per vCPU-hour than E2, did the most work per dollar** because each of its vCPUs is a full core doing more requests per second. The naive "E2 is cheapest" reasoning would have left ~24% of price-performance on the table for this CPU-bound scale-out service. That is the gap between a default and a decision.

Three honest caveats you must state when you present this:

1. **Your workload is not this workload.** A 5ms CPU-bound hash loop is a stand-in. If your real service spends 90% of its time waiting on a database, the CPU family barely matters and you should pick on cost (E2) — the benchmark would show all three families nearly tied, and that flat result is itself the finding.
2. **Concurrency and tuning matter.** Re-run at the concurrency your service actually sees, and set `GOMAXPROCS` to the vCPU count (the Go runtime does this automatically here). A badly-tuned service hides real family differences under its own contention.
3. **The discount posture is missing from the table above.** Re-compute the last column at the *committed* price you will actually pay in production, not the on-demand sticker, before you put it in a design doc.

### Tear it down

```bash
for mt in e2-standard-4 n2d-standard-4 t2d-standard-4; do
  gcloud compute instances delete "bench-${mt//./-}" --zone="$ZONE" --quiet
done
gcloud compute instances delete <load-generator-name> --zone="$ZONE" --quiet
gcloud compute instances list   # expect: Listed 0 items.
```

That `Listed 0 items.` is, again, the only acceptable end state. A benchmark fleet you forgot to delete is the most ironic line item on a cost-optimization week's bill.

## 2.7 — Sizing within a family: standard vs highcpu vs highmem, and "right-size by measuring"

Once you have a family, you still choose a memory-to-vCPU ratio and a size. The naming is consistent across families:

- **`standard`** — ~4 GB RAM per vCPU. The default; start here.
- **`highcpu`** — ~1–2 GB RAM per vCPU. For CPU-bound work that does not need much memory (our hash service; most stateless web tiers). Cheaper for the same vCPU count.
- **`highmem`** — ~8 GB RAM per vCPU. For caches, in-memory databases, JVM heaps.
- **Custom machine types** (N2/N2D and others) — you specify vCPU and memory independently, useful to right-size a workload that does not fit a stock ratio. Beware: custom types carry a small premium and can complicate CUD.

The sizing rule is the same as the family rule: **measure, do not guess.** Run the workload, watch CPU and memory utilization in Cloud Monitoring, and pick the smallest type whose utilization sits in a healthy band (roughly 50–70% CPU at steady state so you have headroom for spikes, with autoscaling handling the rest). Two failure modes to avoid:

- **Over-provisioning by sizing for peak on a single big instance.** That is the "15–30% utilization" trap from Lecture 1 §1.1. The fix is *more, smaller* instances in a MIG that autoscales, not one large instance sized for the worst hour.
- **Under-provisioning memory so the workload OOM-kills under load.** A `highcpu` type is cheaper until your service's working set does not fit and the kernel starts killing it. Measure the working set before you cheap out on RAM.

For this week's MIG you will use small `standard` (lab) or, in the design doc, `highcpu` T2D (production), because the Go service is CPU-bound and memory-light — and you will be able to point at a utilization graph to defend it.

## 2.8 — The defense, rehearsed

In the Phase 2 midterm architecture review, someone will ask "why this machine family?" Here is the shape of an answer that ends the conversation, using this week's service as the example:

> "It is a stateless, CPU-bound, horizontally-scaling HTTP tier, so we are in general-purpose, scale-out territory. We benchmarked E2, N2D, and T2D at equal vCPU on our actual binary: T2D delivered 24% more requests per dollar-hour because its vCPUs are full cores and our work is CPU-bound. Our p99 SLO is loose enough that we do not need C3's tail-latency premium — we verified T2D meets p99 under 1.5× peak load. We run a `highcpu` ratio because the service is memory-light, sized so steady-state CPU sits near 60% with autoscaling for spikes. The 24/7 baseline is on a 1-year resource-based CUD on T2D; peak rides on-demand. If a future release adds Intel-specific SIMD we will re-benchmark, because that is the one change that could flip us to N2 or C3."

Every clause is a measurement or a stated trade-off. Compare to the answer that gets you sent back: "T2D because it's good for web stuff." Same family, no defense. The family was never the hard part — the *defense* is, and the defense is a benchmark plus an articulated SLO and discount posture.

## 2.9 — Recap

You should now be able to:

- Name the five general-purpose families you must defend (E2, N2, N2D, T2D, C3) and the one-line shape of each.
- Explain why price-performance is *work per dollar*, not *vCPUs per dollar*, and why that requires a benchmark.
- State the default rules: N2D over N2 for ordinary web/app tiers; T2D for scale-out throughput; C3 only when a measured p99 violation justifies the premium; E2 for cost-dominated, jitter-tolerant work and labs.
- Account for SUD (automatic) and CUD (committed) when you cost the *baseline* you will actually run.
- Run a fair cross-family benchmark, compute RPS-per-dollar, and state the caveats honestly.
- Right-size within a family by measuring utilization, not by sizing for peak on one big box.
- Deliver a one-paragraph machine-family defense that survives an architecture review.

Next up: you stop launching instances by hand. Exercise 1 has you author the **instance template** — the immutable blueprint that encodes the family, the OS Login and Shielded VM hardening, and the startup script — and launch a single instance from it in Terraform. Everything after that (MIG, autoscaling, spot, the internal LB) stamps copies of that template.

---

## Lecture 2 — checklist before moving on

- [ ] I can describe E2, N2, N2D, T2D, and C3 in one sentence each, including the one situation each is the right answer for.
- [ ] I can explain why "cheapest per vCPU-hour" is the wrong optimization target and what the right one is.
- [ ] I ran the cross-family benchmark, computed RPS-per-dollar-hour for at least three families, and recorded which won and by how much.
- [ ] I can state the default rules (N2D vs N2, when T2D, when C3, when E2) and the exception that would flip each.
- [ ] I know the difference between SUD (automatic) and CUD (committed 1/3-year) and which price belongs in a design doc.
- [ ] I tore down every benchmark instance and the load generator; `instances list` shows `Listed 0 items.`
- [ ] I can deliver the §2.8 one-paragraph defense for a workload of my choosing.

If any box is unchecked, return to that section. The exercises assume you can already defend a family choice with a number.

---

**References cited in this lecture**

- Compute Engine — "Machine families resource and comparison guide": <https://cloud.google.com/compute/docs/machine-resource>
- Compute Engine — "General-purpose machine family": <https://cloud.google.com/compute/docs/general-purpose-machines>
- Compute Engine — "All pricing": <https://cloud.google.com/compute/all-pricing>
- Compute Engine — "Sustained use discounts": <https://cloud.google.com/compute/docs/sustained-use-discounts>
- Compute Engine — "Committed use discounts overview": <https://cloud.google.com/compute/docs/instances/committed-use-discounts-overview>
- Compute Engine — "Set the number of visible cores": <https://cloud.google.com/compute/docs/instances/customize-visible-cores>
- `hey` — HTTP load generator: <https://github.com/rakyll/hey>
