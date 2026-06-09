# Lecture 1 — Click-then-codify, drift, remote state, and the plan-review discipline that keeps IaC honest

> **Reading time:** ~80 minutes. **Hands-on time:** ~70 minutes (you wire a GCS backend, write a `for_each` module, and run your first drift check).

This is the lecture that turns three weeks of ad-hoc HCL into a codebase you would let a stranger run `apply` against. Everything in Weeks 1 through 3 worked — you have a landing zone, a Workload Identity Federation setup, and a multi-region shared VPC, all provisioned with Terraform. But you provisioned it the way everyone provisions their first cloud: one `main.tf` per week, state on your laptop, project IDs typed inline, resource blocks copy-pasted. That code is a liability, and this lecture is about why, and what the production-shop version looks like.

We cover five things, in order: the state model (what Terraform actually does when you `apply`), remote state and locking in GCS (why your laptop is not a safe place to keep the contract), the `google`/`google-beta` provider mechanics (version pins and the beta opt-in rule), the two factoring tools you use ten times a day (`for_each` and modules), and the discipline that ties it together (click-ops, drift, and plan review). By the end you can articulate why "click in the console then write Terraform" is fine in week one and a fireable offense by week six — which is the single most important sentence in Phase 1.

## 1.1 — Terraform is a reconciliation engine, and the state file is the contract

The first mental-model correction: `terraform apply` does **not** "create your VPC." Terraform is a reconciliation engine. When you run `apply`, it computes the difference between three things and then issues the API calls that drag reality toward your configuration:

1. **The configuration** — the `.tf` files you wrote. This is the *desired* state.
2. **The state file** — `terraform.tfstate`, a JSON document recording what Terraform believes it owns and the last-known attributes of each resource. This is Terraform's *memory*.
3. **The real cloud** — what actually exists right now, fetched via a `refresh` (a read of every resource in state against the live GCP APIs).

The `plan` phase computes `(desired) - (refresh of real, keyed by state)` and prints the delta. The `apply` phase executes that delta. That is the entire loop:

```
        ┌────────────────┐      refresh       ┌──────────────┐
        │  state file    │ ◄───────────────── │  real cloud  │
        │ (what TF owns) │                    │  (GCP APIs)  │
        └───────┬────────┘                    └──────────────┘
                │ diff
        ┌───────▼────────┐
        │ configuration  │  ── plan ──►  delta  ── apply ──►  API calls
        │ (desired)      │
        └────────────────┘
```

Three consequences fall straight out of this model, and they drive the rest of the week:

- **The state file is the source of truth for *what Terraform believes it owns*.** If a resource is not in state, Terraform will try to *create* it (and collide with the existing one). If a resource is in state but gone from the cloud, Terraform will *recreate* it. If a resource is in state and in the cloud but its attributes differ from your configuration, Terraform will *update* it. State is the join key between your code and the cloud.
- **Whoever holds the state file holds the cloud.** If `terraform.tfstate` lives on your laptop, then exactly one person can safely run `apply`, there is no audit trail of who changed what, and a lost laptop is a lost cloud — you can no longer associate your code with the resources it created without a painful `terraform import` of every resource by hand.
- **Two people running `apply` against the same local state is a data race.** State is read at the start of a run and written at the end. If two runs overlap, the second writer clobbers the first's record, and now the state file describes a cloud that does not exist. This is not theoretical: a team that shares `terraform.tfstate` over Slack will eventually corrupt it. The fix is remote state with locking, which we wire in section 1.2.

One more nuance that bites people: the state file contains **secrets in plaintext**. A `google_sql_user`'s password, a generated `random_password`, a service-account key — if it is an attribute of a resource Terraform manages, it is in the state JSON, unencrypted (Terraform 1.x; OpenTofu adds optional state encryption, which we note but do not rely on). This is a second reason state must never sit in a Git repo or an unencrypted laptop disk, and a reason the GCS state bucket must have uniform bucket-level access and tight IAM.

## 1.2 — Remote state in GCS with locking

The `gcs` backend stores the state file as an object in a Cloud Storage bucket and uses **GCS object generations** as the locking mechanism. There is no separate lock table (unlike AWS, where the S3 backend historically needed a DynamoDB table). Terraform writes a `.tflock` object; if a second run finds the lock present, it refuses to proceed until the first releases it. This is the single best feature of the GCS backend: locking is built in, free, and requires no extra infrastructure.

### The chicken-and-egg: bootstrapping the state bucket

You cannot store the state of the state bucket *in* the state bucket before the bucket exists. So you bootstrap: create the bucket with **local state**, then migrate. The bootstrap config is small and lives in its own directory so it does not pollute the rest of your tree:

```hcl
# bootstrap/main.tf — creates the bucket that will hold everyone else's state.
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  # NOTE: no backend block here yet. This runs with LOCAL state on purpose.
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_storage_bucket" "tf_state" {
  name     = "${var.project_id}-tf-state"
  location = var.region
  project  = var.project_id

  # Versioning is non-negotiable for a state bucket. If a bad apply corrupts
  # state, you roll back to the previous generation of the object.
  versioning {
    enabled = true
  }

  # Uniform bucket-level access disables per-object ACLs. State buckets must
  # use IAM only — no legacy ACLs granting accidental public read.
  uniform_bucket_level_access = true

  # Never let someone delete the state bucket out from under a running estate.
  force_destroy = false

  # Keep the last 10 non-current versions for 30 days, then prune. Without a
  # lifecycle rule, a versioned bucket grows unbounded.
  lifecycle_rule {
    condition {
      num_newer_versions = 10
    }
    action {
      type = "Delete"
    }
  }
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30
    }
    action {
      type = "Delete"
    }
  }
}

variable "project_id" {
  type        = string
  description = "Project that owns the Terraform state bucket."
}

variable "region" {
  type        = string
  description = "Region for the state bucket. Use a regional bucket for a regional estate."
  default     = "us-central1"
}

output "state_bucket" {
  value       = google_storage_bucket.tf_state.name
  description = "Bucket name to reference in other modules' backend blocks."
}
```

Run it once:

```bash
cd bootstrap
terraform init          # local backend, no bucket needed yet
terraform apply         # creates the state bucket
terraform output state_bucket
# => "crunch-gcp-bootstrap-tf-state"
```

### Migrating an existing local state into the bucket

Now you have a bucket. Take a *different* root module — say your Week 3 VPC — that currently uses local state, and migrate it. Add a `backend "gcs"` block:

```hcl
# vpc/versions.tf
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  backend "gcs" {
    bucket = "crunch-gcp-bootstrap-tf-state"
    prefix = "envs/dev/vpc"   # one prefix per (env, component) — keeps states separate
  }
}
```

The `prefix` is how you partition one bucket into many independent state files. The rule: **one state file per (environment, component)**. Dev VPC and prod VPC must not share a state file, or a `dev` apply can touch `prod` resources. Reinitialize with the migrate flag:

```bash
cd vpc
terraform init -migrate-state
# Terraform detects the backend changed from "local" to "gcs" and asks:
#   "Do you want to copy existing state to the new backend?"  => yes
```

Terraform copies `terraform.tfstate` into `gs://crunch-gcp-bootstrap-tf-state/envs/dev/vpc/default.tfstate` and deletes the local copy. From now on, every `plan`/`apply` reads and writes that object, and acquires a lock for the duration. Verify the lock works by running two `apply`s in parallel from two terminals — the second prints:

```
Error: Error acquiring the state lock

Error message: writing "gs://.../default.tflock" failed: googleapi: Error 412:
At least one of the pre-conditions you specified did not hold., conditionNotMet
Lock Info:
  ID:        1718041200000000
  Operation: OperationTypeApply
  Who:       you@laptop
  Created:   2026-06-09 12:00:00
```

That 412 (precondition failed) *is* the lock working: GCS rejected the second writer's conditional write because the lock object already existed at a different generation. Exactly what you want.

## 1.3 — The `google` and `google-beta` providers

Pin your providers. Always. An unpinned provider means a `terraform init` next month pulls a newer major version, a resource schema changes, and a `plan` that was clean yesterday wants to destroy-and-recreate your database today. The `required_providers` block with a pessimistic constraint (`~>`) is the floor of professional Terraform:

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"   # >= 6.0.0 and < 7.0.0 — allows patches and minors, not a major bump
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}
```

The `~> 6.0` operator means "6.x, any minor or patch, but not 7.0." It lets you take bug fixes without taking a breaking major bump unattended. You upgrade major versions deliberately, in their own PR, with the upgrade guide open and a clean plan as the acceptance test — never as an accidental side effect of `init`.

### When a resource only exists in `google-beta`, and why

Google ships new GCP features to the **beta** API first, and the Terraform provider mirrors that: a brand-new resource (or a new field on an existing resource) often appears only in `google-beta` for a few months before graduating to GA in `google`. The rule is:

- **Opt into beta per-resource, not globally.** You configure both providers and explicitly set `provider = google-beta` on the specific resource that needs a beta field. Everything else stays on the stable `google` provider.
- **A beta resource may change schema before GA.** That is the cost. You take it when the feature is worth it and you are willing to re-plan when the schema settles.

```hcl
provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# This GA resource uses the stable provider implicitly.
resource "google_compute_network" "vpc" {
  name                    = "main"
  auto_create_subnetworks = false
}

# This one needs a field that is only in beta — opt in EXPLICITLY, just here.
resource "google_compute_subnetwork" "with_beta_field" {
  provider                 = google-beta
  name                     = "app"
  network                  = google_compute_network.vpc.id
  region                   = var.region
  ip_cidr_range            = "10.10.0.0/20"
  private_ip_google_access = true
}
```

A common mistake is to set the whole project to `google-beta` "to be safe." Do not. You then silently ride beta schemas for resources that have a perfectly stable GA form, and you inherit beta's churn for no benefit. Beta is a scalpel, not a blanket.

### Provider aliases for multi-region and multi-project

When one root module touches two regions or two projects, you alias the provider and select it per-resource:

```hcl
provider "google" {
  alias   = "us"
  project = var.project_id
  region  = "us-central1"
}

provider "google" {
  alias   = "eu"
  project = var.project_id
  region  = "europe-west1"
}

resource "google_storage_bucket" "us_bucket" {
  provider = google.us
  name     = "${var.project_id}-us"
  location = "us-central1"
}

resource "google_storage_bucket" "eu_bucket" {
  provider = google.eu
  name     = "${var.project_id}-eu"
  location = "europe-west1"
}
```

You will use aliases in the capstone (primary `us-central1`, secondary `us-east1`). Learn the pattern now.

## 1.4 — `for_each` vs. `count`: stable addressing is the whole game

Good Terraform is mostly good *factoring*, and the factoring tool you reach for first is `for_each`. Here is the junior version of three subnets:

```hcl
# DON'T. Three near-identical blocks that can drift apart and are tedious to extend.
resource "google_compute_subnetwork" "app" {
  name          = "app"
  region        = "us-central1"
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.10.0.0/20"
}
resource "google_compute_subnetwork" "data" {
  name          = "data"
  region        = "us-central1"
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.10.16.0/20"
}
resource "google_compute_subnetwork" "gke" {
  name          = "gke"
  region        = "us-central1"
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.10.32.0/20"
}
```

The senior version is one block driven by a map:

```hcl
variable "subnets" {
  description = "Map of subnet name => its CIDR range."
  type        = map(string)
  default = {
    app  = "10.10.0.0/20"
    data = "10.10.16.0/20"
    gke  = "10.10.32.0/20"
  }
}

resource "google_compute_subnetwork" "this" {
  for_each      = var.subnets
  name          = each.key
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = each.value

  # private_ip_google_access on every subnet, for free, no copy-paste.
  private_ip_google_access = true
}
```

This is not aesthetics. It is three concrete wins:

1. **The three subnets cannot drift apart.** They are generated from one template; a change to `private_ip_google_access` applies to all three by definition. With three hand-written blocks, someone eventually edits two of them and forgets the third.
2. **Adding a fourth subnet is one map entry**, not a copy-pasted block you then forget to edit.
3. **The plan is *readable* because addresses are stable.** `for_each` addresses resources by key: `google_compute_subnetwork.this["app"]`, `["data"]`, `["gke"]`. The key is derived from your data, so reordering the map changes nothing. Contrast `count`, which addresses by *positional index*: `google_compute_subnetwork.this[0]`, `[1]`, `[2]`. If you delete the *first* item from a `count` list, every subsequent resource shifts index, and Terraform reads that as "destroy index 2 and recreate it at index 1" for every following element. On real infrastructure — a subnet, a database, a load balancer — that is a destroy-and-recreate of live resources because you sorted a list. This is the single most expensive `count` footgun, and it is why the rule is:

> **Use `for_each` by default. Use `count` only for "zero or one of this thing."**

The legitimate `count` case is a conditional resource:

```hcl
# "Create a NAT gateway only in environments that need egress." Zero or one.
resource "google_compute_router_nat" "nat" {
  count   = var.enable_nat ? 1 : 0
  name    = "egress-nat"
  router  = google_compute_router.router.name
  region  = var.region
  # ...
}
```

When you need to iterate over a *list* rather than a map, convert it to a set so the keys are the values themselves and are stable:

```hcl
variable "enabled_apis" {
  type    = list(string)
  default = ["compute.googleapis.com", "iam.googleapis.com", "storage.googleapis.com"]
}

resource "google_project_service" "apis" {
  for_each = toset(var.enabled_apis)   # set => each.key == each.value == the API name
  project  = var.project_id
  service  = each.key

  disable_on_destroy = false   # don't disable an API just because TF stopped managing it
}
```

`for_each` also drives **dynamic blocks** — repeated nested blocks inside one resource. The canonical GCP example is firewall rule `allow` blocks:

```hcl
variable "allowed" {
  description = "Map of rule name => { protocol, ports }."
  type = map(object({
    protocol = string
    ports    = list(string)
  }))
  default = {
    https = { protocol = "tcp", ports = ["443"] }
    ssh   = { protocol = "tcp", ports = ["22"] }
  }
}

resource "google_compute_firewall" "this" {
  for_each = var.allowed
  name     = "allow-${each.key}"
  network  = google_compute_network.vpc.id

  dynamic "allow" {
    for_each = [each.value]
    content {
      protocol = allow.value.protocol
      ports    = allow.value.ports
    }
  }
  source_ranges = ["0.0.0.0/0"]
}
```

## 1.5 — Module structure and the public/private boundary

A module is a directory of `.tf` files. The convention — and you should follow it for every module in the library you build this week — is four files:

```
modules/vpc/
├── main.tf       # the resources
├── variables.tf  # the inputs (the module's public API)
├── outputs.tf    # the outputs (what callers can read back)
├── versions.tf   # required_version + required_providers (NO backend block — modules don't have backends)
└── README.md     # what it does, inputs, outputs, an example call
```

The single most important design decision in a module is **what is an input and what is hard-coded**. The discipline:

- **Anything that differs between environments is an input.** Project ID, region, CIDR ranges, instance counts, labels — all inputs, because `dev` and `prod` need different values.
- **Anything that is an invariant of *this module's job* is hard-coded.** A `vpc` module always sets `auto_create_subnetworks = false` (auto-subnets are a footgun and a `vpc` module that allows them is not opinionated enough to be useful). The naming convention, the fact that every subnet gets Private Google Access — those are the module's *opinions*, baked in.

Inputs get **validation blocks**. A module that silently accepts garbage and fails at `apply` time (after creating half the resources) is worse than one that rejects garbage at `plan` time:

```hcl
# modules/vpc/variables.tf
variable "project_id" {
  type        = string
  description = "Project that will own the VPC and subnets."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid GCP project ID (6-30 chars, lowercase, digits, hyphens)."
  }
}

variable "region" {
  type        = string
  description = "Primary region for the VPC's subnets."
  validation {
    condition     = contains(["us-central1", "us-east1", "europe-west1"], var.region)
    error_message = "region must be one of the course-approved regions to stay in the free tier."
  }
}

variable "subnets" {
  description = "Map of subnet name => CIDR range. CIDRs must not overlap (checked at apply by GCP)."
  type        = map(string)
  validation {
    condition     = length(var.subnets) > 0
    error_message = "Provide at least one subnet; an empty VPC is almost never what you want."
  }
}
```

Outputs are the module's *return values* — the attributes a caller needs to wire this module into the next one. A `vpc` module's outputs are the network self-link and the subnet self-links, because the GKE module that consumes it needs them:

```hcl
# modules/vpc/outputs.tf
output "network_id" {
  description = "Self-link of the created VPC network."
  value       = google_compute_network.vpc.id
}

output "subnet_ids" {
  description = "Map of subnet name => self-link, for downstream modules to reference."
  value       = { for k, s in google_compute_subnetwork.this : k => s.id }
}
```

Callers consume the module by `source` and inputs:

```hcl
# envs/dev/main.tf
module "vpc" {
  source     = "../../modules/vpc"
  project_id = "crunch-gcp-dev"
  region     = "us-central1"
  subnets = {
    app  = "10.10.0.0/20"
    data = "10.10.16.0/20"
    gke  = "10.10.32.0/20"
  }
}

# Downstream module reads the VPC's outputs as its inputs.
module "gke" {
  source     = "../../modules/gke"   # (you write this in Week 6)
  network_id = module.vpc.network_id
  subnet_id  = module.vpc.subnet_ids["gke"]
}
```

Version your modules with Git tags (`v1.0.0`, `v1.1.0`) once they stabilize. A caller can then pin `source = "git::https://...//modules/vpc?ref=v1.2.0"`. Within a single repo, the relative `../../modules/vpc` path is fine and is what you use this week; cross-repo consumption is where the tag-pinning matters.

## 1.6 — Environment separation: workspaces vs. directory-per-environment

There are exactly two reasonable answers to "how do I run the same modules for `dev` and `prod`," and you should be able to defend the one you pick.

**Answer one: workspaces + per-environment `.tfvars`.** Terraform's built-in `terraform workspace` partitions state by name within one backend, and you pass `-var-file=dev.tfvars`. It is simple, built-in, zero extra dependencies. It falls apart the moment `dev` and `prod` need **different backends** (different state buckets, different projects) or **different provider configs** — which they always eventually do, because you do not want a `dev` mistake to even *authenticate* against `prod`. Workspaces share one backend block; that is their fatal limit for serious multi-environment work.

**Answer two: a directory per environment.** `envs/dev/` and `envs/prod/` are each a thin root module that calls the shared `modules/` with environment-specific inputs and its own backend block. This is the pattern at every GCP shop you will interview at. Its one annoyance: the backend block and provider block get copy-pasted across every `envs/*` directory, and copy-pasted config drifts. That is exactly the problem **Terragrunt** solves.

### Terragrunt: keep backend and provider config DRY

Terragrunt is a thin wrapper around Terraform. Its two load-bearing features are `remote_state` (generates the backend block for each environment) and `generate` (writes the provider block into each environment). You write the backend config **once** in a root `terragrunt.hcl`, and each environment `include`s it:

```hcl
# envs/terragrunt.hcl — the ROOT config, included by every environment.
remote_state {
  backend = "gcs"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    bucket = "crunch-gcp-bootstrap-tf-state"
    # The prefix is derived from the path, so dev and prod get different state
    # files automatically. THIS is the line plain Terraform cannot express.
    prefix = "${path_relative_to_include()}/terraform.tfstate"
  }
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<-EOF
    provider "google" {
      project = "${local.project_id}"
      region  = "${local.region}"
    }
    provider "google-beta" {
      project = "${local.project_id}"
      region  = "${local.region}"
    }
  EOF
}

locals {
  project_id = "PLACEHOLDER"  # overridden per-environment below
  region     = "us-central1"
}
```

```hcl
# envs/dev/terragrunt.hcl — the dev environment.
include "root" {
  path = find_in_parent_folders()
}

locals {
  project_id = "crunch-gcp-dev"
  region     = "us-central1"
}

terraform {
  source = "../../modules/vpc"
}

inputs = {
  project_id = local.project_id
  region     = local.region
  subnets = {
    app  = "10.10.0.0/20"
    data = "10.10.16.0/20"
    gke  = "10.10.32.0/20"
  }
}
```

```hcl
# envs/prod/terragrunt.hcl — same module, different inputs, AUTOMATICALLY different state prefix.
include "root" {
  path = find_in_parent_folders()
}

locals {
  project_id = "crunch-gcp-prod"
  region     = "us-central1"
}

terraform {
  source = "../../modules/vpc"
}

inputs = {
  project_id = local.project_id
  region     = local.region
  subnets = {
    app  = "10.20.0.0/20"
    data = "10.20.16.0/20"
    gke  = "10.20.32.0/20"
  }
}
```

Now `cd envs/dev && terragrunt apply` and `cd envs/prod && terragrunt apply` share one module, one backend bucket, and one provider config — but get distinct state files (`envs/dev/.../terraform.tfstate` vs. `envs/prod/.../terraform.tfstate`) and distinct project IDs. That is the whole value proposition: **DRY config, separate state, no copy-paste.**

Be honest about the trade-off. Terragrunt is a third-party binary and a dependency. A two-person shop with two environments can live without it — copy-pasting two backend blocks is survivable. By the time you have ten environments, or `dev`/`staging`/`prod` × three regions, the copy-paste is a liability and Terragrunt pays for itself. We teach it because it is the 2026 de-facto standard in production GCP shops and because it solves the one problem plain Terraform genuinely cannot: generating per-environment backend blocks without copy-paste. Terragrunt's `dependency` block also wires one module's outputs into another's inputs across directories — you use it in the mini-project to feed the `org-bootstrap` project ID into the `vpc` and `iam-baseline` modules.

## 1.7 — Click-ops, drift, and the fireable-offense rule

Here is the most important sentence in Phase 1, and it deserves its own section:

> **"Click in the console, then write Terraform" is a perfectly fine learning move in week one, and a fireable offense by week six.**

Both halves are true, and the difference between them is the whole discipline.

**Why it is fine in week one.** When you land on a new cloud you do not know the resource graph. You do not know which fields are required, which are computed, which are immutable-after-create. Clicking through the Cloud Console to create a thing teaches you its *shape* faster than reading the provider docs cold. That is a legitimate learning move — *as long as you then codify it and let Terraform own it*. The honest week-one workflow is: click to learn the shape, then write the HCL, then `terraform import` the resource you clicked (or delete it and let Terraform recreate it), then confirm a clean plan. The console was a teacher, not a manager.

**Why it is a fireable offense by week six.** Six weeks in, you know the resource graph. Now the temptation is different: production is on fire, you SSH into the console, click a fix, and the fire goes out. You feel like a hero. You have just created **drift** — the real cloud no longer matches the state file. Here is how that bites, concretely:

- Three weeks later, a teammate runs `terraform apply` to deploy an unrelated change. Terraform refreshes state, sees that the live firewall rule does not match the configuration (because of your console fix), and **reverts your fix** as part of the apply — silently, in the middle of a change that had nothing to do with it. The fire reignites, now at 2 a.m., now mysterious because the person who applied has no idea their change touched your firewall rule.
- Or worse: your console change altered an immutable field, and the next `apply` reads it as a **destroy-and-recreate**, takes down the resource, and the recreate fails because some dependency moved.

Console fixes that are never reflected back into HCL are how IaC shops get burned. The discipline that prevents it is **drift detection plus plan review**.

### Detecting drift

`terraform plan` *is* a drift detector — a clean plan means no drift. But you want to detect drift *proactively*, on a schedule, before a human's apply trips over it. Use `-detailed-exitcode`:

```bash
terraform plan -detailed-exitcode -out=/dev/null
# Exit code 0: no changes (no drift).
# Exit code 2: changes present (drift, or pending config changes).
# Exit code 1: error.
```

Wire that into a scheduled Cloud Build (or cron) job that runs nightly against `prod` and pages Slack on exit code 2. When the page fires, someone reads the plan: if the drift is a console fix, they codify it; if it is a config change someone forgot to apply, they apply it. Either way, the gap between code and cloud is closed deliberately, by a human reading a plan — not silently, by the next unrelated apply.

`plan -refresh-only` is the surgical version: it shows you what changed in the *cloud* without proposing config-driven changes, so you can see drift in isolation. And when you genuinely accept reality over your config (someone changed something on purpose and you want to adopt it), `apply -refresh-only` writes reality into state without touching the cloud.

### Reading a plan for the destroy-and-recreate footgun

The most important plan-reading skill is spotting a destroy-and-recreate before it pages you. Terraform marks them with `-/+`:

```
  # google_sql_database_instance.main must be replaced
-/+ resource "google_sql_database_instance" "main" {
      ~ name             = "prod-db" -> "prod-db-v2" # forces replacement
      ...
    }

Plan: 1 to add, 0 to change, 1 to destroy.
```

`# forces replacement` next to a changed attribute is the alarm. `1 to destroy` on a database is a data-loss event if you `apply` it without a backup. The `-/+` symbol (destroy then create) versus `+/-` (create then destroy, when `create_before_destroy` is set) tells you the order. **A senior engineer reads every plan before merge specifically hunting for `forces replacement` on a stateful resource.** That habit is the entire reason plan review exists.

### The plan-review workflow

The workflow that keeps all of this honest:

1. **Every change goes through a pull request.** No direct apply from a laptop against shared environments.
2. **CI runs `fmt -check`, `validate`, and `plan` on the PR**, and posts the plan output as a comment on the PR (you build this in Exercise 3).
3. **A human reads the plan before merge.** This is where `forces replacement` gets caught.
4. **`apply` runs from CI after merge**, never from a laptop, using Workload Identity Federation so there is no key file.

That is the loop the whole course assumes from here forward: *module first, remote state, open a PR, read the plan, merge, CI applies, prove zero drift.* Build the muscle this week.

## 1.8 — Teardown discipline

Every environment you stand up, you tear down. `terraform destroy` per environment, or `terragrunt run-all destroy` to walk the whole tree. The `run-all` form respects dependency order (it destroys `vpc` after the things that depend on it), but be careful with `--terragrunt-ignore-dependency-order` — that flag exists for speed and will happily try to destroy a VPC while a subnet still references it, which fails noisily. After destroy, verify the projects are empty:

```bash
gcloud asset search-all-resources --scope=projects/crunch-gcp-dev \
  --format="table(assetType, displayName)" | head
# Should return only the project itself and default resources, nothing you provisioned.
```

Leaving a `dev` environment billing overnight by accident is the most common way students blow through the free trial. The teardown is part of the work, not an afterthought.

## 1.9 — The reflexes to internalize this week

- **State is the contract.** Remote, in GCS, versioned, locked. Never on a laptop, never in Git.
- **One state file per (environment, component).** A `prefix` per component; dev and prod never share state.
- **Pin providers with `~>`.** Upgrade majors deliberately, in their own PR, with a clean plan as the test.
- **Beta is a scalpel.** Opt into `google-beta` per-resource, never globally.
- **`for_each` by default, `count` only for zero-or-one.** Stable addressing keeps your plan readable and prevents destroy-and-recreate from a reorder.
- **Inputs are what differs between environments; the module's opinions are hard-coded.** Validate every input.
- **Click to learn, then codify.** A console change you never reflect into HCL is drift, and drift is how you get paged for someone else's apply.
- **Read every plan for `forces replacement` on stateful resources.** That is the entire point of plan review.
- **Tear it down, then verify the project is empty.** The teardown is part of the work.

## 1.10 — What this lecture did not cover (Lecture 2 picks it up)

This lecture is raw HCL plus Terragrunt — the bread-and-butter of operating Terraform on GCP. It deliberately leaves two architectural questions for Lecture 2: **when do you stop hand-writing HCL and adopt Google's blessed Cloud Foundation Toolkit modules**, and **when does Config Connector — managing GCP resources as Kubernetes CRDs reconciled in-cluster — beat a CI `apply` entirely**? Those are the "should I even be writing this myself" questions, and they are exactly the questions a staff engineer asks in an architecture review. Lecture 2 answers them honestly, including the cases where the blessed tools are overkill you will regret adopting.

---

## Lecture 1 — checklist before moving on

- [ ] I can explain the configuration/state/real-cloud triangle and why the state file is the contract.
- [ ] I can bootstrap a GCS state bucket with local state and migrate a root module into it with `terraform init -migrate-state`.
- [ ] I can explain how GCS object generations provide locking and what a 412 precondition error means.
- [ ] I can pin `google` and `google-beta` with `~> 6.0` and opt into a beta resource per-resource.
- [ ] I can refactor three duplicated blocks into one `for_each` block and explain why the addresses are stable.
- [ ] I can state the `count`-vs-`for_each` rule and the destroy-and-recreate footgun `count` causes on a reorder.
- [ ] I can lay out a `modules/` + `envs/dev` + `envs/prod` repo and wire Terragrunt's `remote_state` and `generate` blocks.
- [ ] I can detect drift with `plan -detailed-exitcode` and read a plan for `forces replacement`.
- [ ] I can articulate why click-then-codify is fine in week one and a fireable offense by week six.

If any box is unchecked, return to that section. Lecture 2 assumes you can structure a module library and read a plan.

---

**References cited in this lecture**

- Terraform — "Backends: GCS": <https://developer.hashicorp.com/terraform/language/backend/gcs>
- Terraform — "State: remote state": <https://developer.hashicorp.com/terraform/language/state/remote>
- Terraform — "`for_each`": <https://developer.hashicorp.com/terraform/language/meta-arguments/for_each>
- Terraform — "`count`" (and the "when to use `for_each` instead" callout): <https://developer.hashicorp.com/terraform/language/meta-arguments/count>
- Terraform — "Modules: creation and structure": <https://developer.hashicorp.com/terraform/language/modules/develop>
- Terraform — "Manage resource drift": <https://developer.hashicorp.com/terraform/tutorials/state/resource-drift>
- Google provider — registry docs: <https://registry.terraform.io/providers/hashicorp/google/latest/docs>
- Google Cloud — "Best practices for using Terraform": <https://cloud.google.com/docs/terraform/best-practices/general-style-structure>
- Terragrunt — "Keep your backend configuration DRY": <https://terragrunt.gruntwork.io/docs/features/keep-your-backend-configuration-dry/>
- Gruntwork — "Terraform tips & tricks: loops, if-statements, and gotchas": <https://blog.gruntwork.io/terraform-tips-tricks-loops-if-statements-and-gotchas-f739bbae55f9>
