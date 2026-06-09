# Week 5 Homework

Six problems that revisit the week's topics and push them slightly past the exercises. The full set should take about **6 hours**. Work in your Week 5 directory (the same repo as Week 04) so each problem produces at least one commit and, where it deploys, a clean teardown.

Each problem includes a **problem statement**, **acceptance criteria** (deliverables), a **hint**, and an **estimated time**. Arm a \$10 billing budget before any `apply`. Every deploying problem ends with `gcloud compute instances list` => `Listed 0 items.`

---

## Problem 1 — The machine-family defense memo

**Problem statement.** Pick a real workload you know (from work, a side project, or one of these: a Postgres-backed FastAPI service at 500 RPS; a video-transcoding batch farm; an in-memory recommendation cache at p99 < 20ms). Write a one-page memo, `homework/p1-family-defense.md`, that chooses a GCE machine family for it and defends the choice. The memo must:

1. State whether the workload is general-purpose, compute-optimized, memory-optimized, or accelerator, and why.
2. Name the family you'd default to and the one specific measurement that would flip you to a different family.
3. State the discount posture (on-demand, SUD, or CUD) for the *baseline* and for the *peak*, with the price you'd actually use in a design doc.
4. Include the price-performance ratio definition (work per dollar) and name the work unit for *this* workload.

**Acceptance criteria.**

- [ ] `homework/p1-family-defense.md` exists, ~1 page, addressing all four points.
- [ ] The defense names a *measurement* that would flip the choice, not a vibe.
- [ ] Committed.

**Hint.** Reuse the §2.8 paragraph shape from Lecture 2. The flip-trigger for a CPU-bound scale-out service is "a benchmark shows our binary regresses on EPYC/Tau" or "a measured p99 violation"; for a memory-bound one it's "working set exceeds the highmem ratio."

**Estimated time.** 45 minutes.

---

## Problem 2 — Benchmark two families for real

**Problem statement.** Run the Lecture 2 cross-family benchmark for two families at equal vCPU (e.g. `e2-standard-4` vs `t2d-standard-4`) on the CPU-bound Go service. Drive each with `hey -z 30s -c 50 .../work` from an in-VPC load generator. Record RPS, look up the per-region hourly price for each, and compute RPS-per-dollar-hour. Write the result and a one-sentence conclusion in `homework/p2-benchmark.md`.

**Acceptance criteria.**

- [ ] A table with both families: type, measured RPS, \$/hour (your region), RPS-per-\$/hour, and the relative multiplier.
- [ ] A one-sentence conclusion naming the winner and by how much.
- [ ] At least one stated caveat (e.g. "this is CPU-bound; an I/O-bound service would show no family difference").
- [ ] Teardown verified; `instances list` => `Listed 0 items.`
- [ ] Committed.

**Hint.** Launch both instances with `--no-address` and SSH/scp over `--tunnel-through-iap`. Run `hey` from a third in-VPC instance, not your laptop, so you measure the VM and not your home network.

**Estimated time.** 1 hour.

---

## Problem 3 — Harden a template and prove it

**Problem statement.** Author a `google_compute_instance_template` in `homework/p3-template/` with OS Login, Shielded VM (all three), a dedicated SA scoped to logs + metrics only, no external IP, and `name_prefix` + `create_before_destroy`. Launch one instance from it. Then produce three pieces of evidence that the hardening is real.

**Acceptance criteria.**

- [ ] `terraform apply` clean; one instance from the template.
- [ ] Evidence 1: `gcloud compute instances describe ... --format="yaml(shieldedInstanceConfig)"` shows all three `true`.
- [ ] Evidence 2: `--format="value(networkInterfaces[0].accessConfigs)"` is empty (no external IP).
- [ ] Evidence 3: you SSH'd in over IAP using OS Login (no metadata SSH key added) — paste the `gcloud compute ssh ... --tunnel-through-iap` command and that it succeeded.
- [ ] The instance runs as the dedicated SA, **not** the default Compute SA (`describe ... --format="value(serviceAccounts[0].email)"`).
- [ ] Teardown verified.
- [ ] Committed (the three evidence outputs in a `p3-evidence.txt`).

**Hint.** This is Exercise 1 condensed. The one new requirement is *pasting the evidence* — the habit of proving a control rather than asserting it.

**Estimated time.** 45 minutes.

---

## Problem 4 — Tune autohealing so it doesn't loop

**Problem statement.** Deliberately misconfigure a MIG's `auto_healing_policies.initial_delay_sec` to a value *shorter* than your startup time (e.g. 20s when the script takes ~90s). Apply, observe the recreation loop, then fix it. Write up what you saw and the rule you derived in `homework/p4-autoheal.md`.

**Acceptance criteria.**

- [ ] Evidence of the loop: `gcloud compute instance-groups managed list-instances ...` output showing instances cycling, or the MIG's operation history / activity log.
- [ ] The fix: `initial_delay_sec` raised above the measured startup time, and evidence the group then stabilizes at target size.
- [ ] A one-paragraph rule: how to choose `initial_delay_sec` relative to startup time, and why a too-aggressive *autohealing* check (vs the LB check) is dangerous.
- [ ] Teardown verified.
- [ ] Committed.

**Hint.** Measure your real startup time first: SSH in and `systemd-analyze` or read `journalctl -u google-startup-scripts.service` for the script's start/end timestamps. Set `initial_delay_sec` to comfortably exceed it (startup time + a margin).

**Estimated time.** 45 minutes.

---

## Problem 5 — Prove a zero-drop rolling update

**Problem statement.** With a regional MIG (min 2) behind the service, run a sustained `hey` load and, mid-traffic, roll the instance template from a `v1` binary to a `v2` binary (change the `/version` string). Use `update_policy` with `max_surge > 0` and `max_unavailable = 0`. The load test must report 100% success across the roll. Capture the proof in `homework/p5-rolling-update.md`.

**Acceptance criteria.**

- [ ] The `hey` summary spanning the roll, showing `Success rate: 100.00%`, zero non-2xx, zero connection errors.
- [ ] Evidence the roll actually happened: `curl .../version` returns `v1` before and `v2` after, with no gap in the load test window.
- [ ] The `update_policy` block in your HCL with `max_unavailable = 0` and a positive `max_surge`.
- [ ] One sentence explaining *why* `max_unavailable = 0` is the zero-drop precondition.
- [ ] Teardown verified.
- [ ] Committed.

**Hint.** Hit the service through the LB VIP (or, if you have not built the LB yet, hit the MIG instances round-robin). The graceful-shutdown handler from Exercise 3 plus `connection_draining_timeout_sec` on the backend service is what makes the *drain side* of the roll clean.

**Estimated time.** 1 hour 15 minutes.

---

## Problem 6 — Spot cost + preemption write-up

**Problem statement.** Make a small MIG's instances spot (the Exercise 3 `scheduling` block). Then write `homework/p6-spot.md` covering: (1) the on-demand vs spot price for your machine type in your region, as a percentage saving; (2) a description of the exact preemption signal and your service's four-step graceful-shutdown response; (3) one workload from your own experience that *should* run on spot and one that should *not*, each with a one-sentence reason.

**Acceptance criteria.**

- [ ] The price comparison with a real percentage (from <https://cloud.google.com/compute/all-pricing> or `gcloud compute machine-types describe` + the spot price).
- [ ] Evidence the instances are spot: `gcloud compute instances describe ... --format="value(scheduling.provisioningModel)"` returns `SPOT`.
- [ ] The four-step drain sequence described in your own words (fail readiness → wait for deregistration → drain in-flight → flush/exit).
- [ ] One good-fit and one bad-fit workload, each justified in a sentence.
- [ ] Teardown verified.
- [ ] Committed.

**Hint.** Good fit: a finite, checkpointable batch job (the GPU-training shape). Bad fit: a stateful primary database with no fast failover, or a service whose loss of any single instance violates an SLA without spare capacity. The graceful handler turns "lost a customer's checkout" into "drained cleanly," but it does not make a non-redundant stateful primary safe on spot.

**Estimated time.** 1 hour 15 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 45 min |
| 2 | 1 h 0 min |
| 3 | 45 min |
| 4 | 45 min |
| 5 | 1 h 15 min |
| 6 | 1 h 15 min |
| **Total** | **~5 h 45 min** |

---

## Rubric

| Criterion | Weight | What "great" looks like |
|----------|-------:|-------------------------|
| Defensible reasoning | 25% | P1/P6 choices are backed by a measurement or a stated trade-off, never a vibe |
| Real measurement | 25% | P2's benchmark is run on actual VMs in-VPC, with a region price and a stated caveat |
| Hardening proven, not asserted | 15% | P3 pastes the three evidence outputs; the SA is the dedicated one |
| Operational correctness | 20% | P4's autoheal rule and P5's zero-drop proof are real (loop observed and fixed; 100% summary pasted) |
| Teardown discipline | 15% | Every deploying problem ends with verified `Listed 0 items.`; no orphaned disks or forwarding rules |

---

When you've finished all six, push your repo and start (or finish) the [mini-project](./mini-project/README.md). The homework is the warm-up; the mini-project is the artifact.
