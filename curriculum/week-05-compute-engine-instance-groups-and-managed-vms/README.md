# Week 5 — Compute Engine, Instance Groups, and Managed VMs

Welcome to Phase 2. For four weeks you built the boring, load-bearing foundation: the org/folder/project hierarchy, IAM you can defend in an audit, a shared VPC with Cloud NAT and Private Google Access, and a Terraform module library with remote state. You have not deployed a single workload. That ends today.

This week you put compute on the VPC you built in Week 04 — and you do it with Compute Engine, the oldest and least fashionable primitive in the catalog. That is deliberate. In 2026 the reflex is "containerize it, run it on GKE or Cloud Run, move on." That reflex is correct most of the time and wrong often enough to cost you real money and real outages. A VM is still the right answer for a stateful legacy daemon that assumes a stable local disk, for a GPU batch job that wants the whole machine, and for a workload pinned to a region by a sovereignty contract. The senior move is not "always containers." It is knowing exactly when the box wins, choosing the machine family on price-performance, and running the box in a managed instance group so it heals itself.

By Friday you will have a regional managed instance group (MIG) running a Go HTTP service, fronted by an internal load balancer, autoscaling on CPU, and surviving a rolling update with zero dropped requests — all in Terraform, layered onto the Week 04 VPC. You will also have run instances on spot pricing and handled the 30-second preemption notice gracefully, because the difference between "spot saved us 70%" and "spot lost us a customer's checkout" is exactly that handler.

The throughline of this course holds here: **measure, defend, and tear down.** Every machine-family claim gets a price-performance number. Every architecture choice gets a one-sentence defense. And every lab ends with `terraform destroy` because a forgotten C3 instance is a $200 surprise on next month's bill.

## Learning objectives

By the end of this week, you will be able to:

- **Choose** a GCE machine family (E2, N2, N2D, C3, T2D) for a given workload and defend it on price-performance, not on habit.
- **Decide** when a VM is the right primitive in 2026 versus when a container would have been cheaper and more available — and articulate the cost of getting that wrong.
- **Author** an instance template in Terraform with OS Login, Shielded VM, and a hardened service account, and launch a single instance from it.
- **Build** a regional managed instance group with autoscaling on CPU and validate scale-out under synthetic load.
- **Configure** a rolling update on a MIG with `max_surge` and `max_unavailable` set so an image change drains and replaces instances without dropping traffic.
- **Run** workloads on spot/preemptible VMs and write a graceful-shutdown handler that drains in-flight requests within the 30-second preemption notice.
- **Front** a regional MIG with an internal passthrough load balancer and a health check that actually reflects readiness, not just "the port is open."
- **Tear down** every resource you create and prove with `gcloud compute instances list` that nothing is left billing.

## Prerequisites

This week assumes you have completed **Weeks 01–04** of C18, or carry equivalent GCP and Terraform experience. Specifically:

- You have a working Terraform setup against the `google` and `google-beta` providers with **remote state in GCS** and state locking (Week 04).
- You have the **shared VPC** from Week 03 deployed, or you can stand it up from your module library in under ten minutes: at minimum one region, one subnet with a primary range, Cloud NAT for egress, and Private Google Access enabled.
- You can read and write **VPC firewall rules** without locking yourself out (Week 03), and you understand the difference between an ingress allow rule and a health-check source range.
- Your IAM is sane: you are operating as an impersonated service account with the predefined roles you need, not as `roles/owner` (Week 02).
- You have `gcloud` configured (`gcloud config configurations`), the `google-cloud-cli` updated to a 2026 release, Terraform `>= 1.9` (or OpenTofu `>= 1.7`), and Go `1.23+` installed locally so you can build the service binary.
- You are comfortable with `systemd` unit files and `journalctl` at the C14 Linux level. The startup script this week installs a `systemd` service; you need to read its logs when it misbehaves.

You do **not** need any prior Compute Engine exposure. We start at machine families. If you have used EC2, most of the mental model transfers — the surprises are the global VPC, the regional MIG (no AWS equivalent that behaves the same), OS Login, and the per-second billing with sustained-use discounts.

## Topics covered

- **Machine families in 2026:** E2 (shared-core and cost-optimized), N2 (Intel general-purpose, the safe default), N2D (AMD EPYC, ~10% cheaper for the same vCPU), T2D (Tau, the price-performance king for scale-out web), C3 (Sapphire Rapids, the latency/throughput tier with Titanium offload), and a word on C3D, C4, and the GPU/TPU families you will meet in Week 12.
- **Price-performance discipline:** how to read the on-demand hourly rate, what sustained-use discounts (SUD) and committed-use discounts (CUD) actually buy you, and why "cheapest per-vCPU-hour" is the wrong metric — "cheapest per-unit-of-work" is the right one.
- **When VMs are still right:** legacy stateful daemons with local-disk assumptions, GPU/accelerator batch that wants the whole box, licensing pinned to a host, and data-residency/sovereignty constraints that a managed service does not yet satisfy in your region.
- **Instance templates:** the immutable blueprint a MIG stamps out. Why you never edit a template — you create a new version and roll it.
- **OS Login:** SSH access governed by IAM instead of metadata SSH keys. Why metadata keys are a credential-sprawl footgun and OS Login (plus 2FA) is the production default.
- **Shielded VM:** Secure Boot, vTPM, and integrity monitoring. What each one actually defends against and why you turn all three on by default.
- **Managed instance groups (MIG):** regional vs zonal, target size, autohealing via health checks, the difference between a health check for autohealing and one for load balancing.
- **Autoscaling:** scaling on CPU utilization, on load-balancing capacity, and on a custom Cloud Monitoring metric. Cooldown, min/max replicas, and the scale-in danger zone.
- **Rolling updates and canaries:** `max_surge`, `max_unavailable`, `minimal_action`, and how to ship a new instance template without dropping a request.
- **Spot/preemptible VMs:** the pricing, the 30-second `ACPI G2 Soft Off` preemption signal, the metadata `preempted` flag, and the graceful-shutdown handler that drains connections before the box dies.
- **Internal passthrough Network Load Balancer:** the L4 internal LB that fronts the MIG, its backend service, and the health check that gates membership.
- **Teardown discipline:** the `terraform destroy` gate, orphaned-disk detection, and the `gcloud` commands that prove your bill is clean.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                        | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | When VMs are right in 2026; machine families & pricing      |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Instance templates, OS Login, Shielded VM; first instance   |    2h    |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Wednesday | Regional MIGs, autohealing, autoscaling on CPU              |    1h    |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Thursday  | Spot/preemptible, graceful shutdown; rolling updates        |    1h    |    1.5h   |     0.5h   |    0.5h   |   1h     |     1.5h     |    0h      |     6h      |
| Friday    | Internal LB in front of the MIG; mini-project build         |    0h    |    0.5h   |     0.5h   |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work (Terraform + Go + failover drill)    |    0h    |    0h     |     0h     |    0h     |   1h     |     3.5h     |    0h      |     4.5h    |
| Sunday    | Quiz, teardown verification, write-up                       |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                             | **6h**   | **7.5h**  | **2.5h**   | **4h**    | **6h**   | **12.5h**    | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Curated, current (2026) Google Cloud docs, talks, and source to read |
| [lecture-notes/01-when-vms-are-still-right-in-2026.md](./lecture-notes/01-when-vms-are-still-right-in-2026.md) | The honest VM-vs-container decision: legacy stateful, GPU batch, sovereignty, and the cost of choosing wrong |
| [lecture-notes/02-machine-families-and-price-performance.md](./lecture-notes/02-machine-families-and-price-performance.md) | E2/N2/N2D/C3/T2D — choosing one and defending it on price-performance |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-instance-template-os-login-shielded-vm.md](./exercises/exercise-01-instance-template-os-login-shielded-vm.md) | Build a hardened instance template and launch one instance from it |
| [exercises/exercise-02-regional-mig-autoscaling.tf](./exercises/exercise-02-regional-mig-autoscaling.tf) | A regional MIG with CPU autoscaling, validated under load |
| [exercises/exercise-03-spot-graceful-shutdown.go](./exercises/exercise-03-spot-graceful-shutdown.go) | A Go service that drains in-flight requests on the spot-preemption signal |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-ilb-mig-zero-drop-failover.md](./challenges/challenge-01-ilb-mig-zero-drop-failover.md) | Regional MIG behind an internal LB, autoscaling on CPU + custom metric, zero-drop failover under a kill-and-rolling-update drill |
| [quiz.md](./quiz.md) | 13 questions with an answer key |
| [homework.md](./homework.md) | Six problems with deliverables and a rubric |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the Terraform-deployed regional MIG mini-project (compounds on Week 04) |

## The "zero dropped requests" promise

C18's recurring marker for this week is a load-test summary that survives chaos:

```
Summary:
  Total:        90.0012 secs
  Requests:     449,861
  Success rate: 100.00%
  Non-2xx:      0
```

If you killed instances mid-traffic, or rolled a new instance template, and your load test reports even one non-2xx or one connection error, **you are not done.** A MIG that heals but drops traffic during the heal is a MIG you cannot deploy on a Friday. The point of this week is to make `Success rate: 100.00%` ordinary even while the infrastructure underneath is being deliberately destroyed.

## A word on cost before you start

Compute Engine bills per second after the first minute. A regional MIG with three `e2-medium` instances costs roughly **$0.10/hour** in the cheap regions — pennies for a lab. A single `c3-standard-22` is roughly **$1.00/hour**, and a forgotten one over a weekend is a $50 lesson. The mini-project includes a teardown gate for a reason. Arm a billing budget alert (you built one in Week 01) at $10 for this week's project before you `terraform apply`. Then every lab ends the same way:

```bash
terraform destroy -auto-approve
gcloud compute instances list      # expect: "Listed 0 items."
gcloud compute disks list          # expect: no orphaned data disks
```

## Stretch goals

If you finish the regular work early and want to push further:

- Read the Compute Engine **machine-family comparison** page end to end and build your own price-performance spreadsheet for one real workload: <https://cloud.google.com/compute/docs/machine-resource>.
- Run the same Go service on E2, N2, N2D, T2D, and C3 single instances and benchmark requests/sec/$ with `hey`. Write down which family won and why.
- Convert your MIG to use a **stateful** configuration (preserved disks and instance names) and reason about when that beats a stateless MIG.
- Read the open-source `terraform-google-vm` module on GitHub to see how the community structures instance-template and MIG submodules: <https://github.com/terraform-google-modules/terraform-google-vm>.

## Up next

Continue to **Week 06 — GKE Autopilot vs. Standard** once you have pushed the mini-project and proven your teardown is clean. Week 06 will ask the question this week sets up: now that you can run the service on a self-healing MIG, when is GKE worth the extra control plane, and when is it ceremony you do not need?

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
