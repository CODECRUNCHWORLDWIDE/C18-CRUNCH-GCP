# Lecture 1 — When VMs Are Still the Right Answer in 2026

> **Reading time:** ~70 minutes. **Hands-on time:** ~40 minutes (you launch one instance and reason about three real workloads).

This is the lecture that gives you permission to reach for a virtual machine without apologizing for it. The industry reflex in 2026 is "containerize everything, run it on GKE Autopilot or Cloud Run, and never think about an OS again." That reflex is correct for most stateless web services — which is precisely why it became a reflex, and precisely why it is dangerous. A reflex stops being engineering the moment it stops being a decision. Senior engineers do not run VMs because they are old-fashioned, and they do not run containers because they are fashionable. They pick the substrate that minimizes total cost — engineering time, dollars, and risk — over the life of the workload, and they can defend the pick in one sentence.

By the end of this lecture you will be able to name the three categories of workload where a Compute Engine VM beats a container platform in 2026, quantify the cost of choosing containers when a VM was right, and launch a single hardened instance so you have something concrete under your hands before we automate it.

## 1.1 — The default is correct, which is the problem

Let us be honest about the baseline. For a stateless HTTP service that scales horizontally, holds no local state, and tolerates being killed and rescheduled, a container platform is almost always the right answer. Cloud Run gives you scale-to-zero, request-based billing, and zero machine management. GKE gives you a richer scheduling model and bin-packing across a node pool. Both amortize the operating system across many workloads, both patch the kernel for you (Autopilot fully, Cloud Run entirely), and both turn "deploy" into "push an image."

The economics are real. A container that uses 200 MiB of memory and a tenth of a vCPU does not need a whole `e2-medium` to itself; it needs a slice of one, packed alongside nineteen of its siblings. That bin-packing is where container platforms earn their keep: utilization. A fleet of VMs, each running one process, typically runs at 15–30% CPU utilization because you size for peak and pay for trough. A well-packed GKE node pool runs at 60–70%. That delta is money.

So why does this lecture exist? Because "almost always" is not "always," and the exceptions are expensive in a specific, predictable way: when you force a workload that wanted a VM onto a container platform, you do not get a graceful degradation. You get a months-long fight against the platform's assumptions, a pile of `securityContext` privilege escalations and `hostPath` mounts that defeat the platform's value, and an on-call rotation that wakes up for failure modes the platform was supposed to eliminate. The cost is not a slightly higher bill. The cost is engineering time bleeding into a leak that never closes, plus the operational risk of a workload running in a posture nobody fully understands.

There are three categories where this happens reliably. Memorize them.

## 1.2 — Category one: legacy stateful daemons with local-disk assumptions

The first category is the workload that was written before containers existed and assumes things containers deliberately make hard: a stable hostname, a persistent local filesystem at a fixed path, a long-lived process that holds in-memory state across requests, and a startup sequence that takes minutes and must not be interrupted.

Think of a license-server daemon that writes a lock file to `/var/lib/vendor/license.lock` and refuses to start a second instance if the lock exists. Think of an old Java monolith with a 4-minute warm-up that builds a 12 GiB in-process cache and must not be killed mid-warm-up. Think of a message broker or a search index that was designed to own its disk and treats the disk as the source of truth, with replication bolted on as an afterthought.

You *can* run these on Kubernetes. `StatefulSet` exists precisely for this. But look at what you sign up for:

- A `StatefulSet` with `PersistentVolumeClaim` templates, so each pod gets a stable identity and a persistent disk.
- A `PodDisruptionBudget` so the node autoscaler does not evict your pod during a scale-down.
- A `terminationGracePeriodSeconds` long enough to cover the slow shutdown, plus a `preStop` hook to trigger the drain.
- A `readinessProbe` that does not mark the pod ready until the 4-minute warm-up finishes, and a `startupProbe` so the `livenessProbe` does not kill it during warm-up.
- An anti-affinity rule so two replicas never land on the same node.
- And, frequently, a `securityContext` with elevated privileges because the daemon wants to `mlock` memory or set a real-time scheduling priority — which on Autopilot is simply forbidden, and on Standard is a security review you now own.

By the time you have written all of that, you have re-implemented, badly, the thing a VM gives you for free: one process, one machine, one disk, a stable hostname, and an init system that starts it once and leaves it alone. The MIG you will build this week gives you the *self-healing* part — if the box dies, a new one comes up from the template — without the impedance mismatch. For a stateful daemon you run a MIG with a **stateful configuration** (preserved instance names and disks), or even a single instance with autohealing, and you are done. No `StatefulSet`. No `PodDisruptionBudget`. No fight.

The decision rule: **if the workload's correctness depends on stable local disk and a long-lived process identity, and it was not designed to be evicted, a VM removes more risk than a container platform adds.**

## 1.3 — Category two: GPU and accelerator batch that wants the whole machine

The second category is the heavy batch job — model training, scientific simulation, video transcoding, genomics — that wants an accelerator and wants the whole machine around it.

GPUs are not fungible the way vCPUs are. When you attach an NVIDIA L4 or H100 to a VM, you get the whole GPU, its full memory, and the PCIe bandwidth to it. Container platforms can schedule GPUs, and GKE does it well with the NVIDIA device plugin — but the moment your job wants the entire box (all the GPUs, all the host RAM, the NVLink fabric between GPUs, a specific NUMA topology, or a custom CUDA/driver stack pinned to a version your code was validated against), the container abstraction starts costing you more than it saves.

The economics here invert the usual bin-packing argument. Bin-packing helps when many small workloads share a big machine. A training job that wants 8×H100 *is* the big machine — there is nothing to pack alongside it. So the container platform's headline advantage evaporates, and you are left paying for the platform's overhead (the control plane, the system pods on the node, the scheduling latency) for no benefit.

And the timeline is different. A training run is a batch job: it starts, it runs for six hours, it writes a checkpoint to a bucket, it exits. That is exactly the shape spot VMs were designed for. You launch a GPU VM on spot pricing, your job checkpoints every N minutes to GCS, and when Google reclaims the box you get the 30-second notice (which you will learn to handle this week), checkpoint one last time, and exit. A new spot VM picks up from the checkpoint. You pay 60–91% less than on-demand for a workload that does not care about being interrupted as long as it can resume.

The decision rule: **if the job wants the whole accelerated machine, runs as a finite batch, and can checkpoint-and-resume, a spot VM is both cheaper and simpler than a containerized GPU pod.** (Week 12 revisits this when we compare a Vertex AI Endpoint, vLLM on GKE, and self-managed GPU VMs for *serving* — a different question with a different answer.)

### Spot economics, with numbers

"Spot saves 60–91%" is a slogan until you put it on a job and watch the bill. Here is the arithmetic that makes it a decision. Spot VMs (the successor to the old "preemptible" instances — same idea, no 24-hour cap, set with `--provisioning-model=SPOT`) are priced as a variable discount off the on-demand rate, published per machine family and region and refreshed monthly. In 2026 the discount sits in the 60–91% band for most general-purpose families and is typically deepest on the accelerator families because GPU on-demand capacity is the scarcest and the spare-capacity pool is the most volatile.

Make it concrete with the GPU batch job from above. Suppose an on-demand `a2-highgpu-1g` (one A100 40 GB) lists at roughly **\$3.67/hour** in `us-central1`, and spot for that shape runs ~65% off, so ~**\$1.28/hour**. A training run that needs 200 GPU-hours:

```text
on-demand:  200 hr * $3.67  = $734
spot:       200 hr * $1.28  = $256        ← 65% saved, ~$478 kept
```

That \$478 is real only if the job survives reclamation. Spot's contract is: Google can reclaim the VM at any time on **~30 seconds' notice**, delivered as an `ACPI G2 Soft Off` (a shutdown signal your guest sees) and surfaced in instance metadata. The break-even question is *how much work do you lose per reclamation, and how often does it happen?* If your job checkpoints to GCS every 10 minutes, the worst-case loss per preemption is 10 minutes of compute — call it \$0.21 on the spot rate. Even at an aggressive five preemptions across the run, you have lost ~\$1 of redone work to save \$478. The economics are overwhelming *because the checkpoint interval bounds the loss*. A job that checkpoints once at the end loses the entire run on a single reclaim and spot becomes a trap — you will burn more re-running than you ever saved.

The decision rule for spot economics: **spot is worth it when the per-reclamation loss (one checkpoint interval of work) times the expected reclamation count is far smaller than the discount.** That is almost always true for checkpointing batch, almost never true for a stateful single-writer database, and a judgment call for stateless serving (where a MIG with a spot base plus an on-demand floor — covered Thursday — gets you most of the discount while keeping a guaranteed-available core). You write the 30-second drain handler in Exercise 3; the point here is that the handler is what *converts* the slogan into the saved \$478.

One trap to name now: spot is **capacity-reclaimable, not just price-variable**. In a capacity crunch (an `a2`/`a3` GPU shortage in a popular region) your spot request can simply fail to be fulfilled, or your running instances can be reclaimed faster than your checkpoint interval assumed. For deadline-bound batch you hedge with a **fallback to on-demand** (MIG instance redistribution, or a job runner that retries on-demand after N spot failures) and you spread across zones. Spot is cheapest-effort capacity, not guaranteed capacity, and the design must assume it can vanish.

## 1.4 — Category three: sovereignty, residency, and licensing constraints

The third category is not technical at all. It is legal, and it is the one junior engineers never see coming.

Some workloads are pinned to a region, a specific hardware posture, or a specific operating system by a contract, a regulation, or a license. Examples that show up in real engagements:

- **Data residency.** A European customer's contract says their data may not leave a specific set of regions, and may not transit a region you do not control. On a VM you control exactly which region the disk lives in and which region the instance runs in, and you can prove it. On some managed services the control plane or the build infrastructure lives elsewhere, and you cannot always demonstrate to an auditor that no byte crossed a border.
- **Sovereignty.** Government and regulated-industry contracts increasingly require that the workload run in a sovereign-cloud configuration with specific operational controls. Google offers sovereign and assured-workloads configurations, and the VM is frequently the only compute primitive certified for the strictest tiers in your region during the window you need it.
- **OS-level certification.** A workload validated under an FDA, FIPS, or PCI assessment may be certified against a *specific* OS image at a *specific* patch level. On a VM you pin the exact image and freeze it. On a fully-managed platform the OS is the platform's, and it changes under you — which is normally a feature and here is a compliance violation.
- **BYOL licensing.** Software licensed per physical host, or licensed only on bare-metal or sole-tenant nodes, simply cannot run on a shared container platform without breaching the license. Compute Engine **sole-tenant nodes** exist for exactly this.

None of these are about performance or cost. They are about being able to stand in front of an auditor or a customer's security team and say, with evidence, "this workload ran here, on this image, and nowhere else." A VM gives you that evidence trivially. The managed platforms are catching up — Assured Workloads is real and growing — but in 2026 the VM is still the primitive you reach for when the constraint is a signed document rather than a benchmark.

The decision rule: **if a contract, regulation, or license dictates where and on what the workload runs, the VM is the primitive with the strongest, most auditable guarantees.**

### Sole-tenant nodes and BYOL licensing, in detail

The licensing case deserves its own treatment because it is the one where the *physical* placement of the hypervisor — not just the region — is the constraint, and it is where junior engineers reach for the wrong primitive.

A normal Compute Engine VM is a tenant on a host Google also rents to other customers' VMs. That is invisible and fine for almost everything. But a class of commercial software — older Oracle Database editions, some Windows Server and SQL Server licensing under BYOL, certain SAP and ISV products — is licensed **per physical core of the host**, or contractually requires that no other tenant share the physical machine. On shared hosts you cannot satisfy that: you do not know or control how many physical cores the host has, and you are by definition sharing it.

Compute Engine **sole-tenant nodes** solve exactly this. A sole-tenant node is a *whole physical server* dedicated to your project — no other customer's VMs land on it. You provision a **node group** (a managed pool of physical nodes, with optional autoscaling) and then schedule VMs onto it with **node affinity**. Because you now own the physical host, you can:

- **Count and pin physical cores for licensing.** You know the node has, say, 2 sockets of a specific CPU, and you can use `--visible-core-count` / `threads_per_core=1` to present physical cores (not hyperthreads) to the guest, which is what a per-core license usually requires you to demonstrate.
- **Bring your own license (BYOL)** legally, because the host is dedicated and the core count is fixed and auditable.
- **Pin maintenance behavior** — sole-tenant nodes let you control host maintenance policy (e.g. choose when live-migration happens) more tightly than shared VMs, which matters for license audits and for workloads sensitive to migration jitter.

A minimal shape:

```bash
# Create a sole-tenant node template (the hardware/licensing blueprint)...
gcloud compute sole-tenancy node-templates create c18-st-template \
  --node-type=n2-node-80-640 \
  --region="$(gcloud config get-value compute/region)"

# ...a node group (the actual dedicated physical nodes)...
gcloud compute sole-tenancy node-groups create c18-st-group \
  --node-template=c18-st-template \
  --target-size=1 \
  --zone="$(gcloud config get-value compute/region)-b"

# ...then schedule a VM onto it with node affinity and per-core licensing posture.
gcloud compute instances create licensed-db \
  --node-group=c18-st-group \
  --machine-type=n2-standard-16 \
  --threads-per-core=1 \
  --zone="$(gcloud config get-value compute/region)-b" \
  --image-family=debian-12 --image-project=debian-cloud
```

The cost trade is honest: a sole-tenant node bills as the *whole physical machine* (you pay for the full host regardless of how many VMs you pack onto it), plus a **sole-tenancy premium** on top of the equivalent shared-VM rate. So sole-tenant only makes economic sense when the **license savings or the compliance requirement** exceeds that premium — which for a five- or six-figure-per-year per-core database license, it overwhelmingly does, and for a workload that could run anywhere, it never does. The decision rule: **reach for sole-tenant nodes when a license or a no-shared-host contract demands a dedicated physical machine; otherwise the premium is pure waste.**

## 1.4a — Disk choice is a workload decision, not a default

The other VM-shaped decision that quietly determines correctness and cost is **storage**, and it is one a container platform abstracts away in ways that can hurt you. On a VM you choose deliberately, and the choices are not interchangeable.

- **Balanced Persistent Disk (`pd-balanced`)** — the sensible default boot disk and general data disk. SSD-backed, network-attached, durable (replicated within the zone), survives instance stop/delete if you ask it to, and snapshot-able. Good IOPS-per-dollar for most workloads. This is what your MIG instances boot from this week.
- **SSD Persistent Disk (`pd-ssd`)** — higher sustained IOPS and throughput than balanced, for databases and latency-sensitive I/O that balanced cannot keep up with. More expensive per GiB. Performance scales with provisioned size and vCPU count.
- **Hyperdisk** — the 2026 successor for serious I/O. **Hyperdisk Balanced**, **Hyperdisk Extreme** (highest IOPS, for large in-cloud databases), and **Hyperdisk Throughput** (for throughput-bound analytics/streaming) let you **provision IOPS and throughput independently of capacity** — you no longer have to buy a giant disk just to unlock IOPS. On the machine families that support it (C3, C4, N4, M-series), Hyperdisk is the right answer for any workload where you were previously over-provisioning `pd-ssd` capacity to chase IOPS.
- **Local SSD** — physically attached NVMe on the host, in fixed increments (375 GiB each, multiple attachable). It is by far the fastest storage available — single-digit-microsecond latency, very high IOPS — and it is **ephemeral**: the data is gone when the instance stops, is deleted, or is live-migrated/terminated. It cannot be snapshotted and does not survive a host failure.

The local-SSD-vs-persistent-disk trade is the one people get wrong in both directions:

- **Wrong toward persistent disk:** running a scratch/temp workload — a shuffle space for a batch job, a scratch directory for video transcode, a cache that is rebuildable — on `pd-ssd` because "persistent sounds safer," paying network-disk prices and eating network-disk latency for data you would throw away anyway. Local SSD is cheaper *and* faster for genuinely ephemeral scratch.
- **Wrong toward local SSD:** putting the *source of truth* — a database's data files, the only copy of anything — on local SSD because it benchmarks beautifully, and then losing all of it the first time the instance is stopped or the host fails. Local SSD has **no durability guarantee**. The moment data on it is irreplaceable, it is the wrong disk.

The decision rule: **local SSD for fast, ephemeral, rebuildable data (scratch, cache, shuffle); persistent disk or Hyperdisk for anything whose loss is a problem.** And the corollary that ties back to §1.2: a legacy daemon that "owns its disk and treats it as the source of truth" needs a *persistent* disk preserved across instance replacement — which on a MIG means a **stateful** configuration that preserves the data disk when the autohealer recreates the instance. Putting that daemon's state on local SSD would silently convert "self-healing" into "self-erasing."

## 1.5 — The cost of choosing containers when a VM was right

Let us put numbers and failure modes on the abstract claim that "getting this wrong is expensive." Here is what it actually looks like in the field.

**The slow bleed.** A team containerizes the legacy license daemon from §1.2. It runs, mostly. But the `StatefulSet` evicts it during a node upgrade because nobody set a `PodDisruptionBudget`, and the daemon's lock file is now stale on the persistent volume, and the new pod refuses to start, and someone gets paged at 2 a.m. to manually delete a lock file. This recurs every node upgrade — roughly monthly. Each incident is an hour of senior on-call time plus the customer-facing downtime. Annualize it: twelve incidents, twelve hours of senior time, plus the trust erosion. A single instance with autohealing would never have evicted itself.

**The privilege-escalation tax.** A workload wants `CAP_SYS_NICE` to set real-time scheduling. On GKE Autopilot it is forbidden, so the team migrates to Standard. On Standard it requires a privileged `securityContext`, which fails the security review, which means a documented exception, which means the workload now runs in a posture the security team flagged. Every quarter the exception is re-reviewed. That is recurring meeting time and a standing audit finding — all to run a process that on a VM would just call `chrt` in its `systemd` unit.

**The utilization mirage.** The bin-packing argument assumed many small workloads. But the GPU training job from §1.3 is one big workload. The team runs it on a GKE node pool with one node per job, pays for the control plane and the system DaemonSets, and gets exactly zero bin-packing benefit while adding scheduling latency to a job that starts a handful of times a day. The "container saves money through utilization" thesis was simply false for this workload, and nobody checked.

**The compliance reversal.** The team runs a PCI-scoped workload on a managed platform whose OS updates automatically. The QSA (the PCI assessor) asks for evidence of the exact OS patch level at the time of the last transaction. The platform updated the OS twice that month and the team cannot produce a frozen image. The finding is material. Remediation is migrating to a pinned VM image anyway — the migration they avoided, now done under audit pressure on a deadline.

The pattern across all four: **the cost is not on the bill, it is in the operational and compliance posture.** You do not see it in the pricing calculator. You see it in the on-call log, the security-exception register, and the audit findings. That is exactly why the wrong choice survives so long — the metric that would expose it is not the one anyone is watching.

## 1.6 — The honest counter: when the VM is the wrong reflex

This lecture is not "VMs good, containers bad." That is the opposite reflex and equally lazy. The VM is wrong, and a container platform right, when:

- The workload is **stateless** and scales horizontally. Cloud Run or a GKE Deployment will out-utilize and out-deploy a MIG every time.
- The workload is **bursty and idle-heavy**. Cloud Run's scale-to-zero means you pay nothing between requests; a MIG's minimum size is paying for idle VMs.
- You run **many small services** and want to bin-pack them. That is GKE's home turf.
- The deploy cadence is **high** and you want image-based rollouts with instant rollback. Container platforms make this a one-liner; a MIG rolling update is good but coarser.
- You do not want to own an **operating system** at all. Every VM is a kernel you patch, a `systemd` you debug, and an SSH surface you secure. That is real, recurring work this week will show you the shape of.

The skill is not picking a side. The skill is recognizing which of the six container-favoring conditions or three VM-favoring conditions your specific workload matches, and defending the call. In an architecture review (the midterm at the end of Phase 2), "we ran it on a VM because it's a stateful daemon with a 4-minute warm-up and a local-disk lock, and a single instance with autohealing removes more risk than a `StatefulSet` adds" is a sentence that ends the conversation. "We ran it on a VM because that's what I'm comfortable with" gets you sent back to do the analysis.

## 1.6a — Discounts make the VM cheaper than the sticker: a worked SUD vs CUD example

Lecture 2 introduces sustained-use discounts (SUD) and committed-use discounts (CUD) as part of the machine-family decision. Here, frame them as the other half of the "VM vs container" cost argument, because the sticker price you compare against a container platform is almost never the price you actually pay for a steady VM fleet. Skip this and you will *overstate* the cost of the VM and pick the container platform for a workload the VM would have served more cheaply.

Two automatic-or-committed levers:

- **Sustained-use discounts (SUD)** apply *automatically*, with no commitment, to the non-E2 general-purpose families (N2, N2D, C3, T2D, …). Run an instance for a large fraction of the month and Google progressively discounts it, up to roughly **20–30% off on-demand** for a full month. A MIG holding a steady baseline earns this for free on the baseline instances.
- **Committed-use discounts (CUD)** are an explicit 1- or 3-year commitment to a baseline of compute, in exchange for a deeper discount — commonly **~37% for 1 year and ~55% for 3 years** on resource-based commitments.

Work a concrete fleet: a production MIG holding a steady baseline of **4 × `n2-standard-4`** (16 vCPU total) 24/7, with daily peaks handled by autoscaling on top. Take a representative `n2-standard-4` on-demand rate of **\$0.1942/hour** in `us-central1` and 730 hours/month.

```text
On-demand sticker (what you'd naively compare to a container bill):
  4 nodes * $0.1942/hr * 730 hr            = $567 / month

Sustained-use discount applied automatically (steady 24/7 ≈ 30% off the
non-discounted portion; net effective ~20% on this family/region):
  $567 * (1 - 0.20)                        ≈ $454 / month   (no action, no commitment)

1-year resource-based CUD on the 16-vCPU baseline (~37% off):
  $567 * (1 - 0.37)                        ≈ $357 / month

3-year resource-based CUD on the baseline (~55% off):
  $567 * (1 - 0.55)                        ≈ $255 / month
```

So the *same* baseline fleet costs anywhere from **\$567 to \$255 a month** depending purely on the discount posture you choose — a 2.2× spread on identical hardware. The number you carry into a "VM vs container" comparison must be the one you will actually pay: if this baseline runs for three years, the honest figure is **\$255**, not the \$567 sticker, and a comparison that used \$567 would have wrongly favored the container platform.

The discipline that follows: **commit to the baseline you are certain you will run for the full term, and run the variable peak on on-demand or spot.** The danger is over-committing — a 3-year CUD on a family you abandon in year one is money you pay for compute you no longer want, and resource-based CUDs are tied to a family and region, so picking T2D commits you to T2D. Week 14 does the full FinOps treatment; the rule for this week is simply: **cost the baseline at the committed rate in the design doc, cost the peak at on-demand/spot, and never compare a container bill against a VM's undiscounted sticker.**

## 1.6b — OS image, Shielded VM, and Confidential VM: the posture you pin

The hands-on below turns on Shielded VM with three flags and pins a specific OS image. Those are not decoration; each is a posture choice a VM lets you make explicitly and that a fully-managed platform makes *for* you. Know what each buys.

**The OS image is yours to pin and freeze.** Google publishes maintained public image families — `debian-12`, `ubuntu-2404-lts`, `rocky-linux-9`, `cos-stable` (Container-Optimized OS), the Windows Server families, and the SQL Server and other premium images. You reference a *family* (`--image-family=debian-12`) to always get the latest patched image in that line, or you pin an *exact* image name to freeze a known-good build — which is precisely the compliance lever from §1.4: a PCI- or FIPS-certified workload pins the exact image and does not let it move under audit. For a production fleet the right pattern is usually a **custom image** built from a hardened base with your agents and config baked in (so boot is fast and reproducible), versioned and rolled through the instance template like any other change. You own the patch cadence; that is both the cost and the control.

**Shielded VM** (the three flags you will set: `--shielded-secure-boot`, `--shielded-vtpm`, `--shielded-integrity-monitoring`) defends the *boot path*:

- **Secure Boot** refuses to load boot components not signed by a trusted authority — it blocks boot-level rootkits and unsigned kernel modules.
- **vTPM** (virtual Trusted Platform Module) provides a hardware-rooted measured boot and a place to seal secrets to the boot state.
- **Integrity monitoring** compares the measured boot against a known-good baseline and surfaces a tamper signal you can alert on.

Turn all three on by default. They are free, they break almost nothing (the rare exception is an unsigned third-party kernel module, which you should be suspicious of anyway), and "we run Shielded VM fleet-wide" is a one-line answer to a security reviewer's first question.

**Confidential VM** is the next tier, and it is a *workload* decision rather than a default. It encrypts memory **in use** — not just at rest and in transit — using AMD SEV / SEV-SNP (on N2D/C2D/C3D), Intel TDX (on C3), or equivalent, so that even Google's hypervisor cannot read your VM's RAM in plaintext. You enable it with `--confidential-compute-type=SEV` (or `TDX`) on a supported family. The trade is a modest performance overhead and a constrained set of supported machine types and features. Reach for it when a contract or regulation requires data-in-use protection — sensitive PII, regulated health/financial data, multi-party computation where you must prove even the cloud operator cannot see the plaintext. It is the strongest version of the §1.4 sovereignty argument: not just "the data stayed in this region," but "the data was never readable in cleartext memory anywhere." For an ordinary stateless web tier it is overkill; for the workloads that need it, it is the only primitive that provides it, and it is a VM-only capability.

## 1.6c — Migrating from on-prem: the VM is the landing zone

There is one more reason the VM persists in 2026, and it is the one most enterprises actually hit first: **migration from a data center.** When a company moves a few hundred existing servers to GCP, the workloads are not cloud-native, are not containerized, and frequently have no one left who fully understands them. The VM is the only primitive that lets you move them *as they are* and modernize later — and "later, incrementally, with a fallback" is what makes a migration survivable.

The realistic phased path, and where Compute Engine sits in each phase:

1. **Lift-and-shift (rehost).** Use **Migrate to Virtual Machines** (the GCP service, formerly Migrate for Compute Engine) to stream existing VMware/Hyper-V/physical workloads into Compute Engine VMs with minimal change — often with test-clone-and-cutover so you validate the migrated VM before flipping traffic. The workload runs on a GCE VM that looks almost exactly like the box it left. This buys you *out of the data center* fast, before you have re-architected anything. It is explicitly the *least* cloud-native option and explicitly the right *first* step, because it decouples "stop paying for the data center" from "modernize the app."
2. **Replatform (lift-and-optimize).** Once running on VMs, pick the cheap, high-leverage cloud wins that do not require re-architecting: move the database to **Cloud SQL** or **AlloyDB** instead of self-managing it on a VM, put the fleet behind a managed load balancer, swap a hand-rolled cache for **Memorystore**, move backups to snapshots and GCS, and put the still-VM application tier into a **MIG** so it self-heals and autoscales (the exact thing you build this week). The app code barely changes; the operational posture improves a lot.
3. **Refactor / re-architect (containerize).** *Only when the business case justifies it* — a service that changes often, scales unpredictably, or whose VM operational cost is now the bottleneck — do you containerize it onto GKE or Cloud Run. This is the expensive, high-value phase, and the discipline of the migration is to spend it *selectively*, on the workloads where the §1.1 container advantages are real, rather than boiling the ocean.

The thread through all three: **the VM is the landing zone and the fallback.** A workload that is stuck on a VM forever because it is a stateful legacy daemon (§1.2) simply stays in phase 2, self-healing in a MIG, and that is a perfectly good permanent home — not a failure to "finish" the migration. A workload that earns containerization graduates to phase 3 on its own schedule. The mistake migrations make is treating phase 1 as embarrassing and trying to leap straight to phase 3 under deadline, which is how you get the §1.5 failure modes — a half-understood workload forced onto a platform whose assumptions it violates, under time pressure, with no fallback. Lift-and-shift to a VM first, prove it runs, *then* modernize what pays for itself. The VM is what makes that sequencing possible.

## 1.7 — Hands-on: launch one hardened instance and feel the substrate

Before we automate anything, launch a single instance by hand so the abstractions this week have something concrete underneath them. You will throw this away in five minutes; the point is muscle memory and seeing what "a VM" is.

First, confirm your `gcloud` is pointed at the right project and region. Use the configuration you set up in Week 01:

```bash
gcloud config configurations activate c18-dev   # your dev configuration
gcloud config get-value project
gcloud config get-value compute/region
```

Now launch an `e2-medium` running a current Debian image, with OS Login and Shielded VM enabled. We will dissect each flag in Lecture 2 and Exercise 1; for now, just see it boot:

```bash
gcloud compute instances create week5-scratch \
  --machine-type=e2-medium \
  --zone="$(gcloud config get-value compute/region)-b" \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --shielded-secure-boot \
  --shielded-vtpm \
  --shielded-integrity-monitoring \
  --metadata=enable-oslogin=TRUE \
  --no-address
```

The `--no-address` flag is deliberate and it is the production default: the instance has **no external IP**. It reaches the internet through the Cloud NAT you built in Week 03, and you reach it through Identity-Aware Proxy tunneling, not a public SSH port. Connect:

```bash
gcloud compute ssh week5-scratch \
  --zone="$(gcloud config get-value compute/region)-b" \
  --tunnel-through-iap
```

Because OS Login is on, your SSH access is governed by your IAM role — you needed `roles/compute.osLogin` (or `osAdminLogin`) and `roles/iap.tunnelResourceAccessor` to get in. There is no SSH key in the instance metadata. When you offboard an engineer, you remove an IAM binding; you do not rotate keys on every host. That is the whole pitch for OS Login, and you just used it.

Inside the box, look at what you have:

```bash
systemctl status                 # a full init system, your responsibility now
cat /etc/os-release              # the exact, pinned OS image
free -h                          # the whole machine's memory is yours
nproc                            # the vCPUs are yours, not a cgroup slice
journalctl -b --no-pager | tail  # the boot log — read it when startup misbehaves
```

This is the substrate. One kernel, one init system, one disk, the whole machine. Everything this week — templates, MIGs, autoscaling, spot, the internal LB — is machinery for running *fleets* of this thing without SSH-ing into any of them. But this is the atom. Log out and destroy it immediately:

```bash
exit
gcloud compute instances delete week5-scratch \
  --zone="$(gcloud config get-value compute/region)-b" \
  --quiet
gcloud compute instances list   # expect: Listed 0 items.
```

That last line is the teardown reflex. You will type it after every lab this week. A forgotten instance is a recurring charge; `Listed 0 items.` is the only acceptable end state.

## 1.8 — A decision checklist you can carry into a review

When someone asks "VM or container for this?", walk this list out loud:

1. **Is it stateless and horizontally scalable?** → Lean container (Cloud Run if bursty, GKE if you want bin-packing across many services).
2. **Does correctness depend on stable local disk and a long-lived process identity?** → Lean VM (MIG, possibly stateful config).
3. **Is it a finite batch job that wants the whole accelerated machine and can checkpoint?** → Lean VM on spot.
4. **Is the placement dictated by a contract, regulation, or license?** → Lean VM (possibly sole-tenant), for the audit evidence.
5. **Does the data live anywhere durable, or is it ephemeral scratch?** → Source-of-truth state on a VM means a preserved persistent disk (stateful MIG) or Hyperdisk; ephemeral scratch wants local SSD. Getting this backwards either erases data or overpays for scratch (§1.4a).
6. **Is data-in-use protection or a frozen, certified OS image a requirement?** → Lean VM (Confidential VM and a pinned/custom image are VM-only levers) (§1.6b).
7. **What is the deploy cadence, and do you need instant image-based rollback?** → High cadence + instant rollback leans container.
8. **Who owns the OS patching, and do you want to?** → If "nobody, and no," lean Cloud Run; if "we already run a fleet and have the muscle," a VM is cheap to add.
9. **What does the cost model actually say** when you include the *discounted* baseline (SUD/CUD, §1.6a), spot for the peak, and the operational and compliance posture — not just the on-demand hourly sticker? → This is the tiebreaker, and it is where most people stop too early.

Run that list and you will be right far more often than the engineer who has only one reflex. The next lecture turns "lean VM" into "which VM" — the machine-family choice, on price-performance, with numbers you can defend (and it goes deep on the SUD/CUD math §1.6a only sketched).

---

## Lecture 1 — checklist before moving on

- [ ] I can name the three workload categories where a VM beats a container platform in 2026 (legacy stateful, accelerator batch, sovereignty/licensing).
- [ ] I can name at least four conditions that correctly favor a container platform over a VM.
- [ ] I can describe one concrete, recurring cost of forcing a VM-shaped workload onto a container platform (eviction-on-upgrade, privilege-escalation tax, utilization mirage, compliance reversal).
- [ ] I can do the spot break-even reasoning (per-reclamation loss = one checkpoint interval) and say when spot is a win vs. a trap (§1.3).
- [ ] I know when a workload needs sole-tenant nodes (per-core/BYOL licensing or a no-shared-host contract) and why the premium is otherwise waste (§1.4).
- [ ] I can choose local SSD vs. persistent disk / Hyperdisk correctly and explain why local SSD under a source-of-truth daemon is self-erasing (§1.4a).
- [ ] I can cost a steady baseline at the SUD/CUD rate instead of the on-demand sticker, and I will never compare a container bill against a VM's undiscounted price (§1.6a).
- [ ] I can explain what Shielded VM's three flags and Confidential VM each defend against, and when to pin a frozen/custom OS image (§1.6b).
- [ ] I can lay out the rehost → replatform → refactor migration path and why the VM is the landing zone and the fallback (§1.6c).
- [ ] I launched a single hardened instance with OS Login + Shielded VM + no external IP, SSH'd in via IAP, and deleted it.
- [ ] I can recite the teardown reflex: `delete`, then `instances list` shows `Listed 0 items.`
- [ ] I can walk the nine-point decision checklist out loud for a workload of my choosing.

If any box is unchecked, return to that section. Lecture 2 assumes you have launched at least one instance yourself and can defend "VM vs container" before we move on to "which VM."

---

**References cited in this lecture**

- Compute Engine — "Machine families resource and comparison guide": <https://cloud.google.com/compute/docs/machine-resource>
- Compute Engine — "Spot VMs": <https://cloud.google.com/compute/docs/instances/spot>
- Compute Engine — "Handle Spot VM preemption": <https://cloud.google.com/compute/docs/instances/spot#preemption-process>
- Compute Engine — "Sole-tenant nodes": <https://cloud.google.com/compute/docs/nodes/sole-tenant-nodes>
- Compute Engine — "Bring your own license (BYOL)": <https://cloud.google.com/compute/docs/nodes/bringing-your-own-licenses>
- Compute Engine — "About persistent disk": <https://cloud.google.com/compute/docs/disks/persistent-disks>
- Compute Engine — "About Hyperdisk": <https://cloud.google.com/compute/docs/disks/hyperdisks>
- Compute Engine — "About local SSD disks": <https://cloud.google.com/compute/docs/disks/local-ssd>
- Compute Engine — "Sustained use discounts": <https://cloud.google.com/compute/docs/sustained-use-discounts>
- Compute Engine — "Committed use discounts overview": <https://cloud.google.com/compute/docs/instances/committed-use-discounts-overview>
- Compute Engine — "OS Login": <https://cloud.google.com/compute/docs/oslogin>
- Compute Engine — "Shielded VM": <https://cloud.google.com/security/products/shielded-vm>
- Compute Engine — "Confidential VM overview": <https://cloud.google.com/confidential-computing/confidential-vm/docs/confidential-vm-overview>
- Compute Engine — "OS images": <https://cloud.google.com/compute/docs/images/os-details>
- Google Cloud — "Migrate to Virtual Machines": <https://cloud.google.com/migrate/virtual-machines/docs>
- Google Cloud — "Migration to Google Cloud: rehost, replatform, refactor": <https://cloud.google.com/architecture/migration-to-gcp-getting-started>
- Kubernetes — "StatefulSets": <https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/>
- Google Cloud — "Assured Workloads": <https://cloud.google.com/assured-workloads>
- Google Cloud — "Patterns for scalable and resilient apps": <https://cloud.google.com/architecture/scalable-and-resilient-apps>
