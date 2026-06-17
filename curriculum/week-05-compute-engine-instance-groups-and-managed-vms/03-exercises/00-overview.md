# Week 5 — Exercises

Three focused drills, in order. Each builds the muscle the mini-project assumes you already have. Do them against your Week 04 module library and remote GCS state — these are not throwaway snippets, they are the components you will assemble into the mini-project.

## Index

1. **[Exercise 1 — Hardened instance template + one instance](./exercise-01-instance-template-os-login-shielded-vm.md)** — author a `google_compute_instance_template` in Terraform with OS Login, Shielded VM (all three controls), a hardened service account, and a startup script that installs the Go service as a `systemd` unit. Launch a single instance from it and prove the hardening. (~75 min)
2. **[Exercise 2 — Regional MIG with CPU autoscaling](./exercise-02-regional-mig-autoscaling.tf)** — a complete, applyable `.tf` file that builds a regional MIG from the template, attaches a `google_compute_region_autoscaler` scaling on CPU, and an autohealing health check. Validate scale-out under synthetic load with `hey`. (~90 min)
3. **[Exercise 3 — Spot + graceful shutdown](./exercise-03-spot-graceful-shutdown.go)** — a runnable Go service that traps the preemption signal, flips its health check to unhealthy, drains in-flight requests within the 30-second notice, and exits cleanly. Plus the Terraform diff that turns the MIG's instances spot. (~75 min)

## How to work the exercises

- **Type the HCL and Go yourself.** Do not paste. The whole point is that `google_compute_region_instance_group_manager` and its `update_policy` block live in your fingers by Friday.
- Every exercise ends with a working `terraform apply` and a **clean teardown**. The acceptance criterion is always two-part: it worked, *and* `gcloud compute instances list` shows `Listed 0 items.` afterward.
- Arm a billing budget at \$10 for the week before your first `apply` (you built budget alerts in Week 01). A forgotten `c3-standard-22` over a weekend is the most expensive way to learn this lesson.
- If you get stuck for more than 15 minutes, read the linked provider docs in [resources.md](../01-resources.md) — the answer is almost always one required argument you missed (frequently the health-check firewall source ranges).

## A note on where these run

Exercises 1 and 2 consume the **Week 04 VPC** via a `terraform_remote_state` data source — they read the network and subnet self-links from the Week 04 state in GCS rather than hard-coding them. If you have not deployed the Week 04 VPC, stand it up from your module library first (one region, one subnet, Cloud NAT, Private Google Access). The exercise files show the exact `terraform_remote_state` block.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c18-week-05` to compare.
