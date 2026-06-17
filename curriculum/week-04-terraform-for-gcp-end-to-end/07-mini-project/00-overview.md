# Mini-Project — The Week 04 Terraform Module Library

> **The canonical foundation.** This is not a throwaway week-project. The `modules/` library you build here *replaces* the ad-hoc Weeks 01–03 code and becomes the foundation that every later week — GKE (Week 6), Cloud Run (Week 7), Pub/Sub + BigQuery (Weeks 9–10), Spanner (Week 11), and the capstone — builds on. The syllabus is explicit that the mini-projects compound; this is the one they compound *onto*. Build it like someone is going to read it, because the rest of the course will.

**Time budget:** ~13 hours (Friday–Sunday). **Deliverable:** a portfolio-grade `modules/` folder with `org-bootstrap`, `vpc`, and `iam-baseline`, wired into `envs/dev` and `envs/prod` with remote state, locking, and a working Cloud Build PR plan check, with a teardown gate.

---

## Why this is the headline Phase-1 artifact

The README and SYLLABUS both name "the Week 04 Terraform module library" as one of the three artifacts that belong on your portfolio. Clean, reusable, documented HCL is a hiring signal in itself — a reviewer can read it in ten minutes and know whether you operate Terraform like a professional or like someone who copy-pastes from Stack Overflow. This mini-project is where you produce that artifact.

It is also the literal substrate for the rest of C18. From Week 5 forward, "provision X" means "write a `modules/x` module, wire it into `envs/dev` and `envs/prod`, open a PR, read the plan, merge, prove zero drift." If your library is solid, the next eleven weeks are a pleasure. If it is shaky, you fight it every week. Spend the time now.

This mini-project hardens the [Week 4 Challenge](../04-challenges/challenge-01-refactor-weeks-01-03-into-a-module-library.md) into production grade. The challenge got the library *working*; the mini-project makes it *portfolio-grade*: documented, validated, CI-gated, and torn down cleanly. If you did the challenge, you start from your challenge repo. If you skipped it, the challenge is your build guide.

---

## The brief

Produce a single Git repository, `c18-foundation`, containing:

1. A **`bootstrap/`** root module (local state) that creates the GCS state bucket. Run once, never destroyed.
2. A **`modules/`** library of three production-grade modules, each documented, validated, and following the four-file convention.
3. **`envs/dev`** and **`envs/prod`** that consume all three modules via Terragrunt, with remote GCS state, per-component locking, and inter-module wiring (`dependency`).
4. A **Cloud Build PR plan check** (Exercise 3's script + a `cloudbuild.yaml` + a trigger) that comments the plan on every pull request, authenticated via Workload Identity Federation (no key file).
5. A **teardown gate**: a documented, tested `terragrunt run-all destroy` path that leaves both projects empty, plus a verification command.
6. A **`PORTFOLIO.md`** writeup aimed at a hiring reviewer.

---

## Repository layout (the target)

```
c18-foundation/
├── README.md                       # how to bootstrap, apply, tear down
├── PORTFOLIO.md                    # the hiring-reviewer writeup
├── DRIFT.md                        # the drift-game record (from the challenge)
├── cloudbuild.yaml                 # the PR plan-check build config
├── .terraform-version              # pins the TF/tofu version for the team
├── bootstrap/
│   ├── main.tf
│   └── versions.tf
├── modules/
│   ├── org-bootstrap/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── versions.tf
│   │   └── README.md
│   ├── vpc/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── versions.tf
│   │   └── README.md
│   └── iam-baseline/
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       ├── versions.tf
│       └── README.md
├── envs/
│   ├── terragrunt.hcl              # root: remote_state + generated provider
│   ├── dev/
│   │   ├── env.hcl                 # dev-wide locals (project_id, region, budget)
│   │   ├── org-bootstrap/terragrunt.hcl
│   │   ├── vpc/terragrunt.hcl
│   │   └── iam-baseline/terragrunt.hcl
│   └── prod/
│       ├── env.hcl
│       ├── org-bootstrap/terragrunt.hcl
│       ├── vpc/terragrunt.hcl
│       └── iam-baseline/terragrunt.hcl
└── scripts/
    └── verify-empty.sh             # the teardown-gate verification
```

---

## Phase 1 — bootstrap the state foundation (~1 h)

Create `bootstrap/` with the state-bucket config from Lecture 1 / Exercise 1: versioning on, uniform bucket-level access, `force_destroy = false`, a lifecycle rule pruning old versions. Apply it with local state. This bucket is the one thing you create once and never destroy — it holds the state of everything else.

Record the bucket name; it goes into the root `envs/terragrunt.hcl`.

**Gate:** `gcloud storage buckets describe gs://<bucket>` shows versioning enabled and uniform bucket-level access. The bootstrap's own state may stay local (conventional) or be committed to a private repo.

---

## Phase 2 — write the three modules (~5 h)

Each module follows the four-file convention plus a `README.md`. Every variable gets a `description`. Every variable that can be validated gets a `validation` block. No module declares a `backend`.

### `modules/org-bootstrap`

Owns: the project (create or reference), billing link, API enablement (`for_each = toset(var.enabled_apis)`, `disable_on_destroy = false`), a billing budget alert, and a consistent label scheme.

```hcl
# modules/org-bootstrap/variables.tf (excerpt — the shape you must produce)
variable "project_id" {
  type        = string
  description = "Project ID to create or manage."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid GCP project ID (6-30 lowercase chars/digits/hyphens)."
  }
}

variable "billing_account" {
  type        = string
  description = "Billing account ID (XXXXXX-XXXXXX-XXXXXX) to link to the project."
  sensitive   = true
}

variable "enabled_apis" {
  type        = list(string)
  description = "GCP service APIs to enable on the project."
  default     = ["compute.googleapis.com", "iam.googleapis.com", "storage.googleapis.com"]
}

variable "budget_amount" {
  type        = number
  description = "Monthly budget in USD that arms an alert at 50/90/100%."
  validation {
    condition     = var.budget_amount > 0
    error_message = "budget_amount must be positive."
  }
}

variable "labels" {
  type        = map(string)
  description = "Labels applied to the project for cost attribution."
  default     = {}
}
```

Outputs: `project_id`, `project_number`. These are the foundation other modules depend on.

### `modules/vpc`

Owns: the network (`auto_create_subnetworks = false`, hard-coded opinion), `for_each` subnets with `private_ip_google_access = true`, GKE secondary ranges, and an optional Cloud NAT gated by `count = var.enable_nat ? 1 : 0` (the legitimate zero-or-one `count` case). Outputs: `network_id`, `subnet_ids` (map), `nat_ip`.

This is where you demonstrate both meta-arguments correctly in one module: `for_each` for the subnets (stable addressing), `count` for the conditional NAT (zero-or-one). Your `PORTFOLIO.md` must explain why each is correct.

### `modules/iam-baseline`

Owns: least-privilege custom roles (`for_each` over a role-definitions map), additive member bindings (never `roles/owner`), the deploy service account, and Workload Identity Federation config so CI authenticates without a key. Outputs: `deploy_sa_email`, `wif_provider_name`.

**Gate for Phase 2:** `terraform validate` passes in each module directory; `terraform fmt -check -recursive` is clean; every module has a `README.md` documenting inputs, outputs, and an example call.

---

## Phase 3 — wire the environments with Terragrunt (~3 h)

Root `envs/terragrunt.hcl` provides `remote_state` (GCS, with `prefix = "${path_relative_to_include()}/terraform.tfstate"`) and a `generate` block writing the provider config. Per-environment `env.hcl` files hold environment-wide locals. Each `(env, component)/terragrunt.hcl` includes the root, sets `terraform { source = "../../../modules/<component>" }`, and passes `inputs`.

Use a `dependency` block so `vpc` and `iam-baseline` consume `org-bootstrap`'s `project_id` output rather than re-declaring it:

```hcl
# envs/dev/vpc/terragrunt.hcl (excerpt)
include "root" {
  path = find_in_parent_folders()
}

dependency "bootstrap" {
  config_path = "../org-bootstrap"
  # Stub outputs so `plan` works before the dependency is applied (CI safety).
  mock_outputs = {
    project_id = "mock-project-id"
  }
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

terraform {
  source = "../../../modules/vpc"
}

inputs = {
  project_id = dependency.bootstrap.outputs.project_id
  region     = local.env.locals.region
  enable_nat = local.env.locals.enable_nat
  subnets = {
    app  = local.env.locals.cidr_prefix == "10.10" ? "10.10.0.0/20" : "10.20.0.0/20"
    data = local.env.locals.cidr_prefix == "10.10" ? "10.10.16.0/20" : "10.20.16.0/20"
    gke  = local.env.locals.cidr_prefix == "10.10" ? "10.10.32.0/20" : "10.20.32.0/20"
  }
}
```

dev and prod differ on: project IDs, CIDR prefixes, budget amounts, and `enable_nat`. Everything else is shared through the modules.

**Gate for Phase 3:** Each `(env, component)` has a distinct state file in the bucket (verify by listing). `terragrunt run-all apply` succeeds for both environments. **`terragrunt run-all plan` against both dev and prod prints `No changes.`** Capture this — it is the headline deliverable.

---

## Phase 4 — the Cloud Build PR plan check (~2 h)

Take Exercise 3's `exercise-03-cloudbuild-pr-plan-check.py` and the `cloudbuild.yaml` from its footer. Wire a Cloud Build trigger on pull requests against your repo, with a service account that uses the WIF config from your `iam-baseline` module (no key file). Store a GitHub token in Secret Manager. Open a real PR that changes one CIDR, and confirm the bot comments the plan on the PR, with the change summary and any `forces replacement` warning.

**Gate for Phase 4:** A screenshot (or the comment URL) of the plan check commenting on a real PR. The build authenticates via WIF — no service-account key in the repo.

---

## Phase 5 — teardown gate (~0.5 h)

Write `scripts/verify-empty.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT="${1:?usage: verify-empty.sh <project-id>}"

echo "Resources still present in ${PROJECT} (excluding the project itself):"
gcloud asset search-all-resources \
  --scope="projects/${PROJECT}" \
  --format="table(assetType, displayName)" \
  | grep -v -E 'cloudresourcemanager.googleapis.com/Project$' \
  || true

count="$(gcloud asset search-all-resources --scope="projects/${PROJECT}" \
  --format='value(name)' | grep -v -c 'cloudresourcemanager' || true)"

if [[ "${count}" -eq 0 ]]; then
  echo "CLEAN: ${PROJECT} has no provisioned resources."
else
  echo "NOT CLEAN: ${count} resources remain in ${PROJECT}. Teardown incomplete."
  exit 1
fi
```

Then run the teardown:

```bash
cd envs/prod && terragrunt run-all destroy
cd ../dev    && terragrunt run-all destroy
./scripts/verify-empty.sh crunch-gcp-dev
./scripts/verify-empty.sh crunch-gcp-prod
```

**Gate for Phase 5:** `verify-empty.sh` reports `CLEAN` for both projects. Keep the state bucket — it is the foundation, not a per-run resource.

---

## Phase 6 — the portfolio writeup (~1.5 h)

Write `PORTFOLIO.md` for a hiring reviewer who will spend ten minutes. It must contain:

- A one-paragraph summary of what the library provisions and why it is structured as modules + envs.
- The captured clean-plan output for both environments (the zero-drift proof).
- A short section on each module: what it owns, its key inputs/outputs, and *one design decision you defend* (e.g., why `vpc` hard-codes `auto_create_subnetworks = false`; why `iam-baseline` binds additively rather than authoritatively; why `enable_nat` is a `count` and `subnets` is a `for_each`).
- The PR-check screenshot/URL.
- A "what I would do differently at 10× scale" paragraph (e.g., split state per team, adopt `terraform-google-project-factory`, add OPA policy gates).

---

## Grading rubric (100 points)

| Criterion | Points | What earns full marks |
|---|---:|---|
| **Three modules, four-file convention, READMEs** | 15 | All three modules present, each with `main/variables/outputs/versions.tf` + a `README.md` with inputs/outputs/example. |
| **Input validation & no-backend-in-modules** | 10 | Every variable has a `description`; validatable variables have `validation` blocks; no module declares a `backend`. |
| **`for_each` and `count` used correctly** | 10 | `for_each` for subnets/APIs/bindings (stable addressing); `count` only for the zero-or-one NAT; defended in `PORTFOLIO.md`. |
| **Remote state + locking + per-component state files** | 15 | GCS backend via Terragrunt; distinct state file per `(env, component)`; lock demonstrated or explained. |
| **Terragrunt DRY + `dependency` wiring** | 10 | Single root `terragrunt.hcl`; `dependency` feeds `org-bootstrap` outputs into `vpc`/`iam-baseline`; dev/prod differ only in inputs. |
| **Zero-drift clean plan (both envs)** | 15 | Captured `terragrunt run-all plan` showing `No changes.` for dev and prod. The headline deliverable. |
| **Cloud Build PR plan check (WIF, no key)** | 10 | The check comments a real PR; authenticates via Workload Identity Federation; flags `forces replacement`. |
| **Teardown gate** | 10 | `verify-empty.sh` reports CLEAN for both projects after `run-all destroy`; state bucket retained. |
| **`PORTFOLIO.md` quality** | 5 | Reads like a hiring artifact; defends design decisions; honest "at 10× scale" section. |

**Passing:** 70/100. **Portfolio-ready:** 90+. A submission whose `terragrunt run-all plan` is not clean cannot exceed 70 regardless of other marks — the clean-plan contract is non-negotiable.

---

## The clean-plan contract (restated)

A reviewer clones your repo, runs `terragrunt run-all plan` against both environments, and expects:

```
No changes. Your infrastructure matches the configuration.
```

"It applied once" is not the bar. "It applied, and a fresh plan shows no changes" is the bar. A non-clean re-plan means your configuration is not what you deployed — a computed field, a self-drifting resource, or an unexpressed dependency. Chase the clean plan the way you chase a green test suite, because it is the only honest signal that code and cloud agree.

---

## How this feeds the rest of the course

| Later week | What it adds to THIS library |
|---|---|
| Week 5 (Compute) | `modules/compute` (regional MIG) consumed by `envs/*`, reading `vpc.subnet_ids`. |
| Week 6 (GKE) | `modules/gke` reading `vpc.network_id` + secondary ranges; WIF from `iam-baseline`. |
| Week 7 (Cloud Run) | `modules/cloud-run` + private Cloud SQL over PSC, in the same VPC. |
| Weeks 9–11 (Data) | `modules/pubsub`, `modules/bigquery`, `modules/spanner` — all on this foundation. |
| Capstone | The whole system is `module "thing" { source = "../../modules/thing" }` calls into the library you build this week, across two regions. |

Every one of those is a new module in *this* `modules/` folder, wired into *these* `envs/`, gated by *this* PR check, torn down by *this* gate. You are not building a week-project. You are building the spine of the course.

---

*Teardown is part of the work, not an afterthought. A `dev` environment left billing overnight is the most common way students burn the free trial. The gate exists for a reason — run it.*
