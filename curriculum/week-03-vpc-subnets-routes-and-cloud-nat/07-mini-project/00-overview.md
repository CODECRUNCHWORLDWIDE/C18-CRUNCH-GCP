# Mini-Project — `modules/vpc`: a reusable multi-region shared-VPC module for the landing zone

> Build the reusable Terraform VPC module that the rest of this course consumes. It stands up a multi-region shared VPC (host project + subnets in three regions, each with GKE-ready secondary ranges), Cloud Router + Cloud NAT per region, Private Google Access with the `*.googleapis.com` private-VIP DNS override, and a hierarchical firewall policy with the IAP/health-check must-haves baked in. Week 01's `shared/` and `workloads/` projects consume it; Week 04 refactors it into the canonical module library; Weeks 05–07 deploy compute *into* it. This is the **foundations layer**, and from here forward it compounds.

This is not a throwaway lab. It is the network that every subsequent mini-project assumes exists. The grading bar is correspondingly higher: a clean module interface, sane defaults, a working teardown gate, and a `terraform plan` a reviewer can read without you in the room.

**Estimated time:** ~10 hours (Thursday 2h, Friday 2.5h, Saturday 3h, plus review/teardown).

---

## How this compounds

The syllabus says this mini-project "compounds the foundations layer." Concretely:

- **Week 01** gave you a three-folder, five-project landing zone (`bootstrap/`, `shared/`, `workloads/`). The **host project** for this VPC lives in `shared/`; the **service projects** that consume it live in `workloads/`.
- **Week 02** gave you Workload Identity Federation and service accounts. Your Terraform runs against this VPC with **no key files** — ADC or WIF only.
- **Week 04** takes the module you build here and folds it into `modules/vpc` in the canonical module library that `envs/dev` and `envs/prod` consume. You are writing the *first draft* of that module now; Week 04 hardens its interface and adds the remote-state + plan-review workflow.
- **Weeks 05–07** deploy a MIG, a GKE cluster, and a Cloud Run + PSC backend *into the service projects on this VPC*. They assume the subnets, NAT egress, PGA, and firewall posture you build here.

So: build a real module, with variables and outputs a future-you will consume, not a flat pile of resources. The interface matters as much as the resources.

---

## What you will build

A self-contained module at `modules/vpc/` plus an example invocation at `examples/landing-zone/` that proves it works end to end.

### `modules/vpc/` — the module

```
modules/vpc/
  variables.tf      # host_project_id, vpc_name, regions map, flags
  main.tf           # network, subnets (for_each over regions), router+NAT per region
  firewall.tf       # hierarchical firewall policy + association, legacy fallback rules
  dns.tf            # private googleapis.com zone + A + wildcard CNAME
  shared_vpc.tf     # host-project designation + service-project attachment + networkUser
  outputs.tf        # network_id, subnet ids/self_links, nat names, router names
  versions.tf       # terraform + provider version pins
  README.md         # the module's own usage doc with an example block
```

### `examples/landing-zone/` — the invocation

```
examples/landing-zone/
  main.tf           # module "vpc" { source = "../../modules/vpc"  ... }
  probe.tf          # one e2-micro probe VM per region (no external IP) for validation
  variables.tf
  outputs.tf
  terraform.tfvars.example
```

### The module interface (design it like this)

```hcl
# modules/vpc/variables.tf
variable "host_project_id" {
  type        = string
  description = "Project that owns the shared VPC (lives in the shared/ folder)."
}

variable "vpc_name" {
  type    = string
  default = "crunch-prod-vpc"
}

variable "regions" {
  description = "Per-region subnet plan. Keys are region names."
  type = map(object({
    primary  = string                 # primary CIDR, e.g. "10.10.0.0/20"
    pods     = string                 # GKE pods secondary, e.g. "10.20.0.0/16"
    services = string                 # GKE services secondary, e.g. "10.30.0.0/20"
  }))
}

variable "service_projects" {
  description = "Service projects to attach to the shared VPC (live in workloads/)."
  type        = list(string)
  default     = []
}

variable "firewall_policy_parent" {
  description = "Folder (folders/NNN) or org (organizations/NNN) to attach the hierarchical policy to."
  type        = string
}

variable "nat_log_filter" {
  type    = string
  default = "ERRORS_ONLY"   # "ALL" while debugging
}
```

A caller then writes the *entire* network in one block:

```hcl
# examples/landing-zone/main.tf
module "vpc" {
  source                 = "../../modules/vpc"
  host_project_id        = var.host_project_id
  vpc_name               = "crunch-prod-vpc"
  firewall_policy_parent = var.folder_id
  service_projects       = var.service_project_ids

  regions = {
    "us-central1"  = { primary = "10.10.0.0/20", pods = "10.20.0.0/16", services = "10.30.0.0/20" }
    "us-east1"     = { primary = "10.11.0.0/20", pods = "10.21.0.0/16", services = "10.31.0.0/20" }
    "europe-west1" = { primary = "10.12.0.0/20", pods = "10.22.0.0/16", services = "10.32.0.0/20" }
  }
}
```

That single module call must produce the whole network from the challenge. The work this week is making it real, reusable, and torn down clean.

---

## Rules

- **Terraform (or OpenTofu) ≥ 1.7, `google` provider 6.x, pinned.** No console click-ops except to inspect.
- **`for_each` over `var.regions`** for the subnet, router, and NAT resources. No copy-pasted per-region blocks. This is the whole point of "reusable."
- **No instance gets an external IP.** Egress via Cloud NAT; API access via PGA.
- **The IAP-SSH allow lives in the hierarchical policy**, evaluated before any per-VPC rule, so no service-project admin can accidentally lock the org out of its own bastions.
- **No secrets in the repo.** Credentials resolve via ADC / WIF. `terraform.tfvars` (with real project IDs) is gitignored; `terraform.tfvars.example` is committed.
- **Shared VPC requires an org.** If you are on the solo-learner standalone-project track, build the module's network + NAT + PGA + firewall parts against a single project and *stub* the `shared_vpc.tf` and hierarchical-policy-association with a documented `count = var.enable_org_features ? 1 : 0`. Document the limitation in your README. You still get full marks for everything an org-less account can run.

---

## Acceptance criteria

### Module quality (25%)

- [ ] `modules/vpc/` has the file layout above, with `variables.tf`, `outputs.tf`, and a `README.md` documenting every input and output.
- [ ] Subnets, routers, and NATs are created with `for_each = var.regions` — adding a fourth region is a one-line change to the `regions` map, nothing else.
- [ ] `outputs.tf` exposes at least: `network_id`, `network_self_link`, a `subnets` map (region → `{ id, self_link, primary_cidr }`), `router_names`, and `nat_names`. Weeks 05–07 will consume these.
- [ ] `terraform validate` passes and `terraform fmt -check` is clean.

### Network correctness (25%)

- [ ] Custom-mode VPC, `routing_mode = "GLOBAL"`.
- [ ] Three subnets, three regions, primary + `gke-pods` + `gke-services` secondaries, non-overlapping (prove with `ipcalc` in the writeup).
- [ ] `private_ip_google_access = true` on all subnets.
- [ ] Cloud Router + Cloud NAT in each region, NAT logging on.
- [ ] Private DNS zone overriding `*.googleapis.com` to `199.36.153.8/30`.

### Shared VPC + hierarchical firewall (25%)

- [ ] Host project designated (`google_compute_shared_vpc_host_project`); at least one service project attached (`google_compute_shared_vpc_service_project`) with subnet-scoped `roles/compute.networkUser`. (Solo track: stubbed with `count`, documented.)
- [ ] A hierarchical firewall policy with IAP-SSH allow (`35.235.240.0/20` tcp:22), health-check allow (`130.211.0.0/22`, `35.191.0.0/16`), and a baseline deny-or-`goto_next`, **associated** to the folder/org.
- [ ] After applying the policy, IAP SSH to every probe VM still works (lifeline survives).

### Validation + teardown (25%)

- [ ] Cross-region Connectivity Test (`us-central1` probe → `europe-west1` probe) is REACHABLE — the global-VPC proof.
- [ ] Subnet → VIP Connectivity Test (`199.36.153.8:443`) is REACHABLE; `traceroute -n 199.36.153.8` from a probe shows one hop into Google.
- [ ] `gcloud compute routers get-status` captured for one region, with a two-sentence reading.
- [ ] **Teardown gate:** `terraform destroy` clean; `gcloud compute routers list --project=<host>` empty; the VPC no longer appears in `gcloud compute networks list`. **You do not pass the week without this.**

---

## Suggested build order

### Day 1 (Thursday — ~2h): the network spine

1. Scaffold `modules/vpc/` and `examples/landing-zone/`. Pin versions.
2. Write `variables.tf` (the interface above) and the custom-mode `google_compute_network`.
3. Write the `google_compute_subnetwork` with `for_each = var.regions`, primary + two secondaries, PGA on.
4. `terraform validate`, `fmt`, and a `plan` against the example. No `apply` yet — read the plan and confirm three subnets appear.

### Day 2 (Friday — ~2.5h): egress, private access, sharing

5. Add Cloud Router + Cloud NAT per region (`for_each` again). NAT logging on.
6. Add `dns.tf`: the private `googleapis.com.` zone, the A record, the wildcard CNAME.
7. Add `shared_vpc.tf`: host designation, service-project attachment, subnet-scoped `networkUser`. (Solo track: stub with `count`.)
8. `apply` the example with one probe VM. SSH in via IAP, `dig storage.googleapis.com`, `traceroute -n 199.36.153.8`. Fix until the VIP resolves private and traceroute is one hop.

### Day 3 (Saturday — ~3h): firewall, validation, hardening

9. Add `firewall.tf`: the hierarchical firewall policy + rules + association. Re-`apply`. Confirm IAP SSH still works (the lifeline must survive the policy).
10. Add the second and third probe VMs (one per region). Run the three Connectivity Tests (cross-region, subnet→VIP, IAP→probe). Capture `routers get-status`.
11. Write `modules/vpc/README.md` and the top-level `RESULTS.md` with all the validation output.

### Day 4 (Sunday — ~0.5h): teardown + push

12. Run the teardown gate. Paste the empty `routers list` and `networks list` into `RESULTS.md`. Commit and push.

---

## `RESULTS.md` (the graded artifact)

The infrastructure is destroyed by the time anyone grades it, so the writeup *is* the deliverable. Include:

1. The `terraform apply` resource-count summary.
2. The non-overlap proof: `ipcalc` (or a table) for all nine ranges.
3. The three Connectivity Test `reachabilityDetails.result` lines.
4. `dig +short storage.googleapis.com` and `traceroute -n 199.36.153.8` from a probe VM.
5. `gcloud compute routers get-status <router> --region=<region>` excerpt + two-sentence reading.
6. The module interface: paste your `variables.tf` and `outputs.tf` and one sentence on why each output exists (which later week consumes it).
7. The teardown proof (empty `routers list`, VPC gone from `networks list`).

---

## Hints

- **The hierarchical policy association is the easy-to-forget piece.** A `google_compute_firewall_policy_rule` set with no `google_compute_firewall_policy_association` does nothing. Confirm with `gcloud compute firewall-policies describe <policy> --format="value(associations)"`.
- **Outputs are an API.** Design `outputs.tf` for the consumer you haven't met yet (Week 06's GKE module needs the subnet self-link *and* the secondary-range names). Output a `subnets` map keyed by region with everything a downstream module needs; future-you will thank present-you.
- **`for_each` keys are the region names.** `google_compute_subnetwork.this["us-central1"]` reads cleanly and makes the plan diff legible. Avoid `count` here — index-based addressing makes a region removal reshuffle everything.
- **Test the module in isolation before wiring shared VPC.** Shared VPC needs an org and is the part most likely to fail on a fresh account. Get network+NAT+PGA+firewall green first; add sharing last.
- **The cross-region Connectivity Test is your headline proof.** If `us-central1` → `europe-west1` internal traffic is REACHABLE with zero peering config, the module has demonstrated the global-VPC model — paste that result prominently.

---

## Anti-goals (do not do these — they belong to later weeks)

- **No HA VPN or Cloud Interconnect.** The Cloud Router is here for NAT and for *future* BGP; you do not stand up a live peer this week. (Capstone touches it.)
- **No GKE cluster.** The secondary ranges are *prepared* for GKE; you do not deploy a cluster until Week 06.
- **No Private Service Connect endpoints.** PGA is this week's private-access tool; PSC is Weeks 07/11.
- **No VPC Service Controls perimeter.** That is Week 14. Use the `private` VIP, not `restricted`, this week.
- **No multi-VPC NCC hub.** You may *peer* an analytics VPC as a stretch, but the NCC migration is a later-scale exercise.

---

## Teardown gate (pass/fail)

You do not get credit for the week until all three are true:

```bash
terraform destroy -var-file=terraform.tfvars

gcloud compute routers list --project="$HOST_PROJECT_ID"      # MUST be empty
gcloud compute networks list --project="$HOST_PROJECT_ID" \
  --filter="name:crunch-prod-vpc"                             # MUST be empty
```

A forgotten Cloud NAT in three regions, left running across the rest of the course, is the kind of slow leak that turns a $30 course into a $90 one. Tear it down. Prove it. Then move to Week 04, which takes this module and makes it the canonical `modules/vpc`.

---

**References**

- Provisioning shared VPC: <https://cloud.google.com/vpc/docs/provisioning-shared-vpc>
- Hierarchical firewall policies: <https://cloud.google.com/firewall/docs/firewall-policies-overview>
- Cloud NAT: <https://cloud.google.com/nat/docs/overview>
- Configure Private Google Access: <https://cloud.google.com/vpc/docs/configure-private-google-access>
- terraform-google-modules/terraform-google-network (read its module structure): <https://github.com/terraform-google-modules/terraform-google-network>
- Terraform `for_each`: <https://developer.hashicorp.com/terraform/language/meta-arguments/for_each>
- `google_compute_router_nat`: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_router_nat>
