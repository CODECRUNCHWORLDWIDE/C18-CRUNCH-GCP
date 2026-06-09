# Week 5 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 06. Answer key at the bottom — don't peek.

---

**Q1.** Which of the following is the *strongest* argument for running a workload on a Compute Engine VM rather than a container platform in 2026?

- A) VMs are simpler to learn than Kubernetes.
- B) The workload's correctness depends on stable local disk and a long-lived process identity, and it was not designed to be evicted.
- C) VMs are always cheaper than containers.
- D) Containers cannot run stateful workloads at all.

---

**Q2.** A team runs a GPU model-training job (8×H100, six hours, checkpoints to GCS every 10 minutes) on a GKE node pool with one node per job. What is the most accurate critique?

- A) This is ideal — GKE's bin-packing saves money here.
- B) They get no bin-packing benefit (the job *is* the whole machine) and pay control-plane and system-pod overhead for nothing; a spot GPU VM with checkpoint-resume is cheaper and simpler.
- C) GPUs cannot be scheduled on Kubernetes, so this cannot work.
- D) They should use Cloud Run, which is best for GPU batch.

---

**Q3.** Why is "vCPUs per dollar-hour" the wrong way to compare machine families on price-performance?

- A) Because vCPU counts are not published.
- B) Because a vCPU is not constant work across families — a T2D vCPU is a full core while an E2 vCPU is a throttled shared hyperthread — so the right metric is *useful work per dollar*, which requires a benchmark.
- C) Because all families have identical per-vCPU performance.
- D) Because dollars are not a meaningful unit.

---

**Q4.** A stateless, CPU-bound, horizontally-scaling HTTP service with a loose p99 SLO needs a default machine family for its production web tier. Which is the best first choice, and what would flip it?

- A) C3 by default; flip to E2 if cost matters.
- B) E2 by default; flip to N2 if you need an Intel benchmark.
- C) T2D by default (full-core scale-out, best RPS/\$); flip to N2/C3 only if a benchmark shows a regression on the Tau platform or a measured p99 violation.
- D) M-series by default; flip to A-series for GPUs.

---

**Q5.** What is the difference between a sustained-use discount (SUD) and a committed-use discount (CUD)?

- A) They are two names for the same automatic discount.
- B) SUD applies automatically when you run an instance most of the month (no commitment); CUD requires committing to a 1- or 3-year baseline for a deeper discount.
- C) SUD requires a 1-year commitment; CUD is automatic.
- D) Only E2 instances earn SUD.

---

**Q6.** You enable OS Login on an instance. What changes about how engineers reach it?

- A) Nothing; they still use metadata SSH keys.
- B) SSH access is governed by IAM roles (e.g. `roles/compute.osLogin`) instead of metadata SSH keys, so offboarding is removing an IAM binding, not rotating keys on every host.
- C) The instance gets a public IP automatically.
- D) The instance can only be reached from the Cloud Console.

---

**Q7.** Shielded VM enables three controls. Which set is correct?

- A) Firewall, NAT, and routing.
- B) Secure Boot, vTPM, and integrity monitoring.
- C) Encryption, replication, and snapshots.
- D) OS Login, IAP, and Cloud Armor.

---

**Q8.** Why do you set `name_prefix` and `lifecycle { create_before_destroy = true }` on a `google_compute_instance_template`?

- A) To make the template name shorter.
- B) Because instance templates are effectively immutable; a change must create a *new* template (with a fresh name) before the old one is destroyed, which is what lets a MIG roll onto it without a gap.
- C) To enable autoscaling.
- D) It is required syntax with no behavioral effect.

---

**Q9.** What is the key advantage of a *regional* MIG over a *zonal* MIG?

- A) Regional MIGs are cheaper per instance.
- B) Regional MIGs spread instances across all zones in the region, so a single-zone outage drops at most a fraction of capacity and the group refills the survivors; a zonal MIG dies with its zone.
- C) Zonal MIGs cannot autoscale.
- D) Regional MIGs do not need a health check.

---

**Q10.** A MIG keeps recreating instances in a loop, even though the service eventually starts fine after a ~2-minute startup script. What is the most likely misconfiguration?

- A) The machine family is wrong.
- B) `auto_healing_policies.initial_delay_sec` is shorter than the startup time, so the MIG recreates instances that are merely still booting.
- C) The autoscaler `max_replicas` is too low.
- D) OS Login is disabled.

---

**Q11.** In a MIG `update_policy`, you set `max_surge = 3` and `max_unavailable = 0`. What behavior does this produce during a template roll, and why does it matter?

- A) It removes 3 instances at a time before adding replacements; faster rolls.
- B) It adds up to 3 healthy new instances *before* removing any old ones, so serving capacity never dips below target — the precondition for a zero-drop rolling update.
- C) It makes the roll happen all at once.
- D) It disables autohealing during the roll.

---

**Q12.** When a spot VM is about to be preempted, what does your service receive, and what is the correct *first* action?

- A) Nothing; spot VMs just vanish.
- B) An ACPI G2 Soft Off (seen as SIGTERM) and an `instance/preempted=TRUE` metadata flag, with ~30 seconds; the first action is to fail the health check so the LB stops sending new connections, *then* drain in-flight and exit.
- C) A SIGKILL with no warning; nothing can be done.
- D) An email; you should reply to it.

---

**Q13.** During a graceful shutdown, why must you fail the readiness/health check and wait briefly *before* closing the HTTP listener?

- A) To save CPU.
- B) Because the load balancer is still routing new connections until it observes the failed health check; closing the listener first sends those new connections to a closed port, producing connection-refused errors (non-2xx).
- C) Because closing the listener first is faster.
- D) There is no reason; you can close immediately.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — The three VM-favoring categories are legacy stateful (stable disk + long-lived identity, not designed for eviction), accelerator batch that wants the whole machine, and sovereignty/licensing constraints. "Simpler than Kubernetes" (A) and "always cheaper" (C) are false; (D) is false — `StatefulSet` exists, it's just often more cost than a VM removes.
2. **B** — The job *is* the big machine, so bin-packing (the container platform's main economic advantage) gives nothing, and you pay control-plane + system-pod overhead. It is a finite batch that checkpoints — exactly the shape spot VMs were designed for. (Lecture 1 §1.3.)
3. **B** — A vCPU does not represent constant work across families; price-performance must be measured as work per dollar on your actual code. (Lecture 2 §2.3.)
4. **C** — T2D is the scale-out price-performance king (full-core vCPUs). The flips are a measured EPYC/Tau regression (→ N2/C3) or a measured p99 violation (→ C3). (Lecture 2 §2.2, §2.5.)
5. **B** — SUD is automatic for running most of the month, no commitment; CUD is a 1- or 3-year baseline commitment for a deeper discount. E2 does *not* earn SUD because its price is already discounted, but that's not the SUD-vs-CUD distinction the question asks for. (Lecture 2 §2.4.)
6. **B** — OS Login moves SSH authorization into IAM; offboarding is an IAM change, not a per-host key rotation. (Lecture 1 §1.7, resources glossary.)
7. **B** — Secure Boot, vTPM, integrity monitoring. Turn all three on by default. (README topics; resources.)
8. **B** — Templates are immutable; `name_prefix` + `create_before_destroy` means a change produces a new template before the old is destroyed, enabling a gapless roll. (Exercise 1 Step 5.)
9. **B** — Regional spreads across zones for single-AZ-loss survival; zonal dies with its zone. (Exercise 2; resources glossary.)
10. **B** — `initial_delay_sec` shorter than startup time makes the autohealer recreate still-booting instances — an infinite recreation loop. The single most common MIG misconfiguration. (Exercise 2 "why each knob".)
11. **B** — Add healthy capacity first, then remove old; capacity never dips below target. This is the zero-drop precondition. (Exercise 2 / Challenge 1.)
12. **B** — ACPI G2 Soft Off (SIGTERM) + the `instance/preempted` metadata flag, ~30s budget; first action is fail readiness so new traffic stops arriving. (Exercise 3.)
13. **B** — The LB keeps routing until it sees the failed check; close first and those in-flight new connections hit a closed listener → connection-refused → non-2xx. Fail readiness, wait, then drain and close. (Exercise 3 "why the order matters".)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11+, you're ready for the [homework](./homework.md) and the [mini-project](./mini-project/README.md).
