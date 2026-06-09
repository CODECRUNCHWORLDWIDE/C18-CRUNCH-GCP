# Challenge 1 — Refactor the Weeks 01–03 deliverables into a reusable module library

> **Estimated time:** 2.5–3.5 hours. This is the highest-leverage thing you build in Phase 1; every later week's `apply` is a call into the library you produce here.

You have three weeks of ad-hoc Terraform: the Week 1 landing zone (folders, projects, billing budget), the Week 2 IAM / Workload Identity Federation setup, and the Week 3 multi-region shared VPC. Each is a `main.tf` with local state, hard-coded project IDs, and copy-pasted blocks. Your job is to refactor all of it into a **module library** — `modules/org-bootstrap`, `modules/vpc`, `modules/iam-baseline` — consumed by `envs/dev` and `envs/prod` through Terragrunt, with remote GCS state and locking, and to **prove zero drift** with a clean plan against both environments.

No solution is provided. The lectures and exercises gave you every primitive; this challenge is the assembly.

## The target repository layout

```
c18-foundation/
├── bootstrap/                  # creates the GCS state bucket (local state); run once
│   ├── main.tf
│   └── versions.tf
├── modules/
│   ├── org-bootstrap/          # project, API enablement, billing budget, labels
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── versions.tf
│   │   └── README.md
│   ├── vpc/                    # network, for_each subnets, Cloud NAT, Private Google Access
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── versions.tf
│   │   └── README.md
│   └── iam-baseline/           # custom roles, group bindings, SA + WIF, least-privilege
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       ├── versions.tf
│       └── README.md
├── envs/
│   ├── terragrunt.hcl          # root: remote_state + generate provider (DRY)
│   ├── dev/
│   │   ├── org-bootstrap/terragrunt.hcl
│   │   ├── vpc/terragrunt.hcl
│   │   └── iam-baseline/terragrunt.hcl
│   └── prod/
│       ├── org-bootstrap/terragrunt.hcl
│       ├── vpc/terragrunt.hcl
│       └── iam-baseline/terragrunt.hcl
└── README.md
```

## What each module owns

### `modules/org-bootstrap`

The "spawn a managed project" module from Week 1, generalized. Inputs: `project_id`, `folder_id`, `billing_account`, `enabled_apis` (list), `budget_amount`, `labels` (map). It creates the project (or references an existing one), links billing, enables the APIs via `for_each = toset(var.enabled_apis)` with `disable_on_destroy = false`, and arms a billing budget alert. Outputs: `project_id`, `project_number`. This is the module a future week's `terragrunt.hcl` declares a `dependency` on, so its outputs are the foundation everything else consumes.

### `modules/vpc`

The Week 3 VPC, factored. Inputs: `project_id`, `region`, `subnets` (map of name => CIDR), `secondary_ranges` (map for GKE pods/services), `enable_nat` (bool). It creates the network (`auto_create_subnetworks = false`, hard-coded — that is the module's opinion), the subnets via `for_each` with `private_ip_google_access = true`, a Cloud Router + Cloud NAT gated behind `count = var.enable_nat ? 1 : 0` (the legitimate `count` case), and a hierarchical or per-VPC firewall baseline. Outputs: `network_id`, `subnet_ids` (map), `nat_ip` (or null when NAT disabled).

### `modules/iam-baseline`

The Week 2 IAM / WIF setup, factored. Inputs: `project_id`, `custom_roles` (map of role definitions), `bindings` (map of role => list of members), `wif_pool_id`, `wif_provider_config`, `deploy_sa_id`. It creates a least-privilege custom role per `for_each`, binds members additively (never `roles/owner`), creates the deploy service account, and configures Workload Identity Federation so CI authenticates without a key. Outputs: `deploy_sa_email`, `wif_provider_name`.

## What dev and prod differ on

The whole point of the library is that dev and prod call the *same* modules with *different* inputs. They must differ on at least:

- **Project IDs** (`crunch-gcp-dev` vs. `crunch-gcp-prod`).
- **CIDR ranges** (dev `10.10.x`, prod `10.20.x` — non-overlapping).
- **Budget amounts** (dev small, prod larger).
- **`enable_nat`** (perhaps dev has no NAT to save cost; prod does).

Everything that differs is a Terragrunt `input`. Everything that is the module's job is hard-coded in the module. If you find yourself copy-pasting a resource block between dev and prod, you have found a missing module input.

## Acceptance criteria

- [ ] `modules/` contains exactly three modules: `org-bootstrap`, `vpc`, `iam-baseline`, each with the four-file convention (`main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`) plus a `README.md`.
- [ ] Every module variable has a `description`, and every variable that can be meaningfully validated has a `validation` block.
- [ ] No module declares a `backend` block (backends belong to root modules / Terragrunt, not modules).
- [ ] `envs/dev` and `envs/prod` consume all three modules via Terragrunt, with a single root `terragrunt.hcl` providing `remote_state` (GCS) and a generated provider block.
- [ ] Each `(env, component)` pair has its own state file (distinct `prefix` / `path_relative_to_include()`), confirmed by listing the state bucket.
- [ ] `terragrunt run-all apply` (or per-component apply) succeeds for both environments.
- [ ] **The zero-drift proof:** `terragrunt run-all plan` against *both* dev and prod prints `No changes. Your infrastructure matches the configuration.` Capture this output — it is the deliverable.
- [ ] At least one module uses `for_each` (subnets, APIs, or bindings) and at least one uses `count` for a zero-or-one resource (NAT), and you can explain in your writeup why each is the right choice.
- [ ] `terraform fmt -check -recursive` passes across the whole repo.
- [ ] A top-level `README.md` documents how to bootstrap, apply, and tear down the estate.
- [ ] **Teardown:** `terragrunt run-all destroy` cleanly removes both environments, and `gcloud asset search-all-resources` confirms the projects are empty afterward. (Keep the state bucket — it is the foundation.)

## The drift game (do this last, it is the most instructive part)

Once both environments apply clean, deliberately introduce drift in dev and watch the discipline catch it:

1. In the Cloud Console, manually change a firewall rule that your `vpc` module manages (e.g., add a source range).
2. Run `terragrunt plan` against `envs/dev/vpc`. Terraform refreshes, sees the live rule no longer matches your config, and proposes to **revert** your console change. That proposed revert *is* the drift, surfaced.
3. Now decide, as a senior engineer would: is the console change correct (codify it into HCL and re-plan to clean) or wrong (apply the revert)? Do one, and get back to a clean plan.
4. Write two sentences in your writeup on what would have happened if no one ran this plan for three weeks and an unrelated teammate's apply hit the drift first.

This is the entire point of the week, compressed into one exercise: drift is invisible until someone plans, and a clean plan is the only honest signal that code and cloud agree.

## Submission

Commit to a Git repository (this becomes your portfolio artifact and the mini-project's starting point):

- The full `c18-foundation/` tree above.
- A `DRIFT.md` documenting the drift game: the change you made, the plan that caught it, the decision you took, and the clean re-plan.
- The captured `terragrunt run-all plan` output showing `No changes.` for both environments.

A reviewer will clone your repo, run `terragrunt run-all plan` against both environments, and expect a clean plan. "It applied once" is not the bar; "a fresh plan shows no changes" is the bar.

## Going further (no extra grade)

- Swap your hand-rolled `org-bootstrap` for `terraform-google-project-factory` and your `vpc` for `terraform-google-network`. Diff the plans. Write a paragraph on what changed, what the CFT modules do that yours did not, and whether you would adopt them. (This is the Lecture 2 exercise made concrete.)
- Add the Exercise 3 Cloud Build PR plan check to the repo and demonstrate it commenting on a real PR. (This is also part of the mini-project; doing it here gets you ahead.)
- Add a scheduled Cloud Build trigger that runs `terragrunt run-all plan -detailed-exitcode` nightly against prod and pages a webhook on exit code 2 (drift detected).

---

**References**

- Terraform — "Modules: creation and structure": <https://developer.hashicorp.com/terraform/language/modules/develop>
- Terragrunt — "Keep your backend configuration DRY": <https://terragrunt.gruntwork.io/docs/features/keep-your-backend-configuration-dry/>
- Terragrunt — `dependency` block: <https://terragrunt.gruntwork.io/docs/reference/config-blocks-and-attributes/#dependency>
- Google Cloud — "Best practices for using Terraform": <https://cloud.google.com/docs/terraform/best-practices/general-style-structure>
- Terraform — "Manage resource drift": <https://developer.hashicorp.com/terraform/tutorials/state/resource-drift>
