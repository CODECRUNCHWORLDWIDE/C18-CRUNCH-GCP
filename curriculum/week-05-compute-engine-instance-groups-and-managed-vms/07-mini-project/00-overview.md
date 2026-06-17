# Mini-Project — A Self-Healing Regional MIG Behind an Internal LB

> Build, in Terraform, a `compute` module that runs a Go HTTP service on a **regional managed instance group** behind an **internal passthrough load balancer**, with **CPU autoscaling** and **zero-drop rolling updates** — and wire it into your Week 04 module library, consuming the Week 04 VPC. Prove it survives a chaos drill with 100% success rate. Tear it down on demand.

This is the first mini-project where you deploy a real workload, and it is deliberately the moment the course's compounding kicks in. You do **not** start from a blank directory. You add a `modules/compute/` module to the **Week 04 module library**, you read the network and subnet from the **Week 04 VPC** via remote state, you consume the new module from **`envs/dev`** exactly the way Week 04 taught you, and you ship it through the same plan-review reflex. From here to the capstone, "provision X" means "write a module for X, wire it into `envs/`, read the plan, apply, prove it, tear it down." This week installs that loop on the simplest possible workload.

**Estimated time:** ~12.5 hours (split across Thursday, Friday, Saturday in the suggested schedule).

---

## What you will build

A directory `modules/compute/` in your Week 04 repo, plus a thin root module in `envs/dev/compute/` that consumes it, producing:

- A **dedicated least-privilege service account** for the workload (logs + metrics only).
- A hardened **instance template**: OS Login, Shielded VM (all three), no external IP, the Go service installed as a `systemd` unit, `name_prefix` + `create_before_destroy` for immutability.
- A **regional MIG** spread across the region's zones, with **autohealing** on a conservative `/healthz` check and a **`PROACTIVE` rolling-update policy** (`max_surge` > 0, `max_unavailable = 0`).
- A **regional autoscaler** scaling on CPU (target 60%) with min 2 / max 6 and a slower scale-in than scale-out.
- An **internal passthrough Network Load Balancer**: regional backend service (the MIG), a regional LB health check, an internal forwarding rule with a VIP allocated from the Week 04 subnet.
- The **health-check firewall rule** (`130.211.0.0/22`, `35.191.0.0/16` → port 8080) and an **IAP SSH** rule.
- The Go service from the exercises, with the **graceful-shutdown handler** from Exercise 3 (so the same artifact survives spot preemption and rolling updates).
- A **teardown gate**: a documented, verified `terraform destroy` and the `gcloud` proofs that nothing is left billing.

By the end you have a service reachable at an internal VIP that you can hammer with load while killing instances and rolling templates, and it never drops a request.

---

## Why it compounds on Week 04 (read this before you start)

The whole point of Week 04 was that the next eleven weeks are `module "thing" { source = "../../modules/thing" }`. This is the first cash-in. Concretely:

- **You reuse the Week 04 remote state backend.** The `compute` env's `backend "gcs"` block points at the same state bucket, a new prefix (`envs/dev/compute`). State locking and versioning are already on from Week 04.
- **You read the VPC from Week 04 state, you do not recreate it.** A `terraform_remote_state` data source pulls `network_self_link`, `subnet_self_link`, and `region` from `envs/dev/vpc`. If those output names differ in your Week 04 code, fix the reference — wiring modules together cleanly *is* the skill.
- **You consume the new module exactly like Week 04's modules.** `modules/compute/` has `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, and a `README.md` — the same structure and the same per-module README discipline you established in Week 04.
- **You ship it through the same plan-review gate.** Open a PR, let the Cloud Build trigger post the `terraform plan`, read it, merge, apply from CI (or apply locally if your cohort has not wired CI yet — but read the plan first, every time).

If you skipped the Week 04 mini-project, do it first. This week genuinely builds on that artifact; there is no clean shortcut.

---

## Repository layout (added to the Week 04 repo)

```
<your-week-04-repo>/
├── modules/
│   ├── org-bootstrap/         # from Week 04
│   ├── vpc/                   # from Week 04
│   ├── iam-baseline/          # from Week 04
│   └── compute/               # NEW this week
│       ├── main.tf            # SA, template, MIG, autoscaler, ILB, firewall
│       ├── variables.tf       # project_id, region, network/subnet, sizing, image
│       ├── outputs.tf         # ilb_vip, mig_self_link, instance_group, template
│       ├── versions.tf        # required_version + google provider pin
│       ├── startup.sh         # installs the binary as a systemd unit
│       └── README.md          # what the module does, inputs, outputs, example
├── envs/
│   ├── dev/
│   │   ├── vpc/               # from Week 04 (its state is read here)
│   │   └── compute/           # NEW: thin root module that calls modules/compute
│   │       ├── main.tf        # module "compute" {...} + remote_state data source
│   │       ├── terragrunt.hcl # or backend.tf, matching your Week 04 pattern
│   │       └── outputs.tf
│   └── prod/                  # from Week 04 (you do NOT deploy compute to prod)
└── service/
    └── workserver/
        ├── main.go            # the Go service (with the Exercise 3 drain handler)
        └── go.mod
```

You deploy to **`envs/dev` only**. `prod` stays untouched — this is a lab workload and the teardown gate is real.

---

## The service

Use the Go service from Exercise 3 (the CPU-bound `/work` + `/healthz` handler **with the graceful-shutdown drain**). Add a version string so you can prove rolling updates:

```go
var version = "v1" // bump to v2 to demonstrate a zero-drop roll

// in the mux:
mux.HandleFunc("/version", func(w http.ResponseWriter, r *http.Request) {
    fmt.Fprintln(w, version)
})
```

Build it once, locally, statically, and push it to a GCS bucket the workload SA can read:

```bash
cd service/workserver
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o workserver main.go
gsutil cp workserver gs://<your-artifacts-bucket>/workserver/v1/workserver
```

The startup script `gsutil cp`s the prebuilt binary instead of compiling on boot — faster, no compiler on the box, and the binary is a versioned, auditable artifact. Grant the workload SA `roles/storage.objectViewer` on that bucket.

---

## Acceptance criteria

- [ ] A new module `modules/compute/` with the standard five files **plus a `README.md`** documenting inputs, outputs, and a usage example.
- [ ] A new env `envs/dev/compute/` that consumes `modules/compute` and reads the Week 04 VPC via `terraform_remote_state`. **No hard-coded network/subnet self-links.**
- [ ] The env uses the **same GCS remote-state backend** as Week 04 (new prefix), with locking.
- [ ] `terraform plan` is reviewed (in a PR comment if your CI is wired) before `apply`. `terraform apply` is clean.
- [ ] The MIG is **regional**, spread across zones, running the **hardened template** (OS Login + Shielded VM ×3 + dedicated SA + no external IP + `create_before_destroy`).
- [ ] The service is fronted by an **internal passthrough NLB**; you reach `/version` and `/work` only through the **internal VIP**, never an instance IP.
- [ ] **Autohealing** recreates a manually-deleted instance. **Autoscaling** scales 2→toward 6 under sustained load and back to 2 after the scale-in window.
- [ ] A **chaos drill** documented in the repo: a `hey` run against the VIP that spans (a) deleting ≥2 instances mid-run and (b) a **template roll from `v1` to `v2`**, ending with `Success rate: 100.00%`, zero non-2xx, zero connection errors. Paste the summary.
- [ ] The Go service includes the **graceful-shutdown handler** (fail readiness → wait → drain → exit), and you can show its log during the roll.
- [ ] A **machine-family defense** in the README: one paragraph, with the benchmark number from Lecture 2, defending the family you chose for the *design doc* (T2D/N2D) vs. the lab (`e2-medium`).
- [ ] **Teardown gate verified** (see below). `gcloud compute instances list` => `Listed 0 items.`, no orphaned disks, no orphaned forwarding rules.

---

## Suggested order of operations

### Phase 1 — The module scaffold (~1h)

1. `mkdir -p modules/compute envs/dev/compute service/workserver`.
2. Create the five module files with empty/placeholder content and the module `README.md` stub.
3. In `envs/dev/compute/main.tf`, add the `terraform_remote_state` data source for the Week 04 VPC and a `module "compute"` block calling `../../modules/compute` with the network/subnet/region wired from the remote state.
4. `terraform init` the env. Confirm the backend initializes against your Week 04 state bucket. First commit: `compute module scaffold`.

### Phase 2 — The service + artifact (~1h)

1. Drop the Exercise 3 `main.go` into `service/workserver/`, add the `version`/`/version` handler, `go mod init`.
2. Build statically, push to GCS, grant the (not-yet-created) workload SA read on the bucket (you will create the SA in the module; for now note the bucket and binary path as a module variable).
3. Commit: `workserver v1 + artifact`.

### Phase 3 — Template + SA + firewall (~2h)

1. In `modules/compute/main.tf`, write the workload SA + IAM bindings (logs, metrics, `storage.objectViewer` on the artifact bucket).
2. Write the instance template (Exercise 1 shape): Shielded VM ×3, OS Login, no external IP, `name_prefix` + `create_before_destroy`, the SA, and the `startup.sh` that `gsutil cp`s the binary and installs the `systemd` unit.
3. Write the IAP-SSH and health-check firewall rules.
4. `apply`. Launch a throwaway `google_compute_instance_from_template` to smoke-test the template, SSH over IAP, confirm `/healthz`. Delete it. Commit: `hardened template + SA + firewall`.

### Phase 4 — MIG + autoscaler + autohealing (~2h)

1. Add the regional MIG (Exercise 2 shape): `version` → template, `named_port http:8080`, `auto_healing_policies` with `initial_delay_sec` ≥ 60 (binary fetch is fast now), `update_policy` (`PROACTIVE`, `max_surge` 3, `max_unavailable` 0).
2. Add the regional autoscaler (CPU 0.6, min 2, max 6, `scale_in_control` slower than scale-out). Put `ignore_changes = [target_size]` on the MIG so it and the autoscaler do not fight.
3. `apply`. Confirm 2 instances across zones. Drive load against one and watch scale-out. Delete one and watch autoheal. Commit: `regional MIG + autoscaler + autohealing`.

### Phase 5 — Internal load balancer (~1.5h)

1. Add the regional LB health check (distinct from the autohealing check — more aggressive), the regional backend service (`INTERNAL`, `TCP`, `connection_draining_timeout_sec = 30`, backend = the MIG's `instance_group`), and the internal forwarding rule (VIP from the Week 04 subnet, port 8080).
2. `apply`. From the in-VPC load generator, hit the **VIP** and confirm `/version` returns `v1` and `/work` returns a digest. Commit: `internal LB in front of the MIG`.

### Phase 6 — The chaos drill (~2.5h)

1. Start the sustained load against the VIP:
   ```bash
   ~/go/bin/hey -z 180s -c 100 http://<INTERNAL_VIP>:8080/work
   ```
2. At ~T+30s, delete two instances in different zones. Watch the LB drop them and the MIG refill.
3. At ~T+90s, build `workserver` as `v2`, push to `gs://.../workserver/v2/`, change the module's binary-path variable (and `version`), `apply`. The MIG `PROACTIVE`-rolls onto the new template. Watch `journalctl -u workserver.service -f` on a draining instance show the four-step graceful shutdown.
4. When `hey` finishes, paste the summary into `mini-project/CHAOS-DRILL.md`. It must read `Success rate: 100.00%`.
5. Re-run the load and `curl http://<VIP>:8080/version` — it now returns `v2` with no gap in the load test. Commit: `chaos drill: 100% success across kills + v1->v2 roll`.

### Phase 7 — Write-up, defense, teardown (~2.5h)

1. Fill the module `README.md`: inputs, outputs, usage example, and the machine-family defense paragraph with your Lecture 2 benchmark number.
2. Write `mini-project/CHAOS-DRILL.md`: method, the pasted 100% summary, and one paragraph on *why* it held (fail-readiness order, `max_unavailable=0`, LB draining).
3. Run the **teardown gate** (below) and paste the clean proofs into the README.
4. Push. Open the PR if your cohort uses one. Commit: `docs + verified teardown`.

---

## Expected output

Reaching the VIP:

```
$ curl http://10.10.0.42:8080/version
v1
$ curl -s http://10.10.0.42:8080/work | head -c 16
b8f2a1c0d3e4f5a6
```

The MIG at idle and under load:

```
NAME                   ZONE           STATUS
week5-workserver-a1b2  us-central1-a  RUNNING
week5-workserver-c3d4  us-central1-b  RUNNING          # idle: 2

# ... under sustained load, within ~3 min ...
week5-workserver-a1b2  us-central1-a  RUNNING
week5-workserver-c3d4  us-central1-b  RUNNING
week5-workserver-e5f6  us-central1-c  RUNNING
week5-workserver-g7h8  us-central1-a  RUNNING
week5-workserver-i9j0  us-central1-b  RUNNING
week5-workserver-k1l2  us-central1-c  RUNNING          # scaled to max 6
```

The chaos-drill summary (the week's promise):

```
Summary:
  Total:        180.0021 secs
  Requests:     449,861
  Requests/sec: 2499.21
  Success rate: 100.00%
Status code distribution:
  [200] 449861 responses
```

---

## Teardown gate

This is not optional and it is graded. A forgotten regional MIG of `c3` instances is a multi-hundred-dollar weekend.

```bash
# Tear down the compute env (NOT the VPC — later weeks reuse it).
cd envs/dev/compute
terraform destroy -auto-approve

# Prove nothing is left billing.
gcloud compute instances list            # expect: Listed 0 items.
gcloud compute instance-groups managed list   # expect: empty
gcloud compute forwarding-rules list      # expect: empty
gcloud compute disks list                 # expect: no orphaned data disks
gcloud compute instance-templates list    # the template is gone too

# Clean up the load generator and any artifact you no longer need.
gcloud compute instances delete week5-loadgen --zone=<zone> --quiet
```

Paste the `Listed 0 items.` lines into the README. The grader runs `terraform destroy` on a fresh clone and expects it to leave the project clean — and to leave the **Week 04 VPC intact**, because Week 06 reuses it.

---

## Rubric

| Criterion | Weight | What "great" looks like |
|----------|-------:|-------------------------|
| Compounds on Week 04 | 15% | New `compute` module + `envs/dev/compute`; VPC read via remote state; same backend; no hard-coded self-links |
| Hardened template | 15% | OS Login, Shielded VM ×3, dedicated SA, no external IP, `create_before_destroy` immutability |
| Regional MIG + autoscaling | 15% | Regional spread, autohealing with sane `initial_delay`, CPU autoscaler with slower scale-in, autoscaler owns size |
| Internal LB | 15% | Working internal VIP, distinct LB vs autohealing checks, health-check firewall correct, connection draining on |
| Zero-drop chaos drill | 20% | `Success rate: 100.00%` across both instance kills and a `v1→v2` roll; graceful-shutdown log shown |
| Machine-family defense | 10% | One paragraph with a real benchmark number; lab vs design-doc family distinguished |
| Teardown + docs | 10% | Verified clean teardown (VPC preserved); module README + chaos-drill writeup someone can follow |

---

## Stretch (optional)

- **Make the MIG spot** (Exercise 3 scheduling block) and run the chaos drill with a *real* simulated preemption (`gcloud compute instances simulate-maintenance-event`). Prove 100% across a real reclaim path.
- **Add the custom-metric autoscaling signal** (RPS-per-instance) from the challenge, taking the max of CPU and RPS. Show a scale-out the custom metric triggered before CPU would have.
- **Canary the roll**: use a second `version` block at `target_size.fixed = 1` to canary `v2` to one instance, validate `/version`, then promote.
- **Wire the Ops Agent** in the startup script and build a Cloud Monitoring dashboard: MIG size, per-instance CPU, LB request count, and the custom RPS metric on one screen. This is the dashboard you would actually keep open during the drill.
- **Cost the design.** Using Lecture 2's discount math, write the monthly cost of this MIG at its 24/7 baseline on T2D with a 1-year resource-based CUD, vs. on-demand, vs. spot for the variable peak. One table.

---

## What this prepares you for

- **Week 06 (GKE):** you redeploy *this same Go service* to Autopilot and Standard and compare cold-start, scale-out, and cost against the MIG you built here. The question "when is GKE worth the control plane vs. a self-healing MIG?" only has a real answer once you have built both.
- **Week 08 (Cloud LB + Cloud Armor):** the internal NLB here becomes the backend behind a global external HTTPS LB with a WAF. Same backend-service mental model, one layer up.
- **Week 14 (FinOps + on-call):** the CUD/SUD math and the chaos-drill discipline here are the warm-up for the capstone's region-failover drill and cost report.
- **The capstone:** the GKE Standard cluster runs services fronted by exactly this LB pattern. The "fail readiness, add capacity first, drain, then remove" reflex you install here is the reflex the capstone's zero-downtime requirements assume.

---

## Submission

1. Push to GitHub. The Week 5 work lives in the **same repo** as Week 04 (it is one growing module library), under the new `modules/compute/`, `envs/dev/compute/`, and `service/workserver/` paths.
2. Ensure the module `README.md`, `mini-project/CHAOS-DRILL.md`, and the pasted teardown proofs are present.
3. Ensure `terraform apply` and `terraform destroy` are both green on a fresh clone, and that destroy leaves the Week 04 VPC intact.
4. Post the repo URL and the `Success rate: 100.00%` summary in your cohort tracker.
