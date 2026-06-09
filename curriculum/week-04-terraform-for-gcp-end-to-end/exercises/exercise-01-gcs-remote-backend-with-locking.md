# Exercise 1 — Configure a GCS remote backend with state locking and migrate local state into it

**Goal:** Bootstrap a versioned, locked GCS bucket to hold Terraform state, then migrate an existing local-state root module into it with `terraform init -migrate-state`. Prove the lock works by watching a concurrent apply get rejected with a 412 precondition error. This is the Monday move that turns your laptop-bound Terraform into team-safe Terraform.

**Estimated time:** 90 minutes.

---

## Setup

You need:

```bash
terraform version          # 1.9+ (or `tofu version`, 1.8+)
gcloud config get-value project   # your course project, e.g. crunch-gcp-dev
gcloud auth application-default login   # so Terraform picks up ADC
```

Set a shell variable for your project so the commands below copy-paste cleanly:

```bash
export TF_PROJECT="$(gcloud config get-value project)"
echo "Working in project: ${TF_PROJECT}"
```

Make a working directory for this exercise:

```bash
mkdir -p ex01/bootstrap ex01/vpc
```

---

## Step 1 — Write the bootstrap config (creates the state bucket with LOCAL state)

The state bucket cannot store its own state before it exists. So `bootstrap/` runs with local state, on purpose. Create `ex01/bootstrap/main.tf`:

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  # NO backend block here. Local state is intentional for the bootstrap.
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_storage_bucket" "tf_state" {
  name     = "${var.project_id}-tf-state"
  location = var.region
  project  = var.project_id

  versioning {
    enabled = true
  }

  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle_rule {
    condition {
      num_newer_versions = 10
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
  description = "Region for the state bucket."
  default     = "us-central1"
}

output "state_bucket" {
  value       = google_storage_bucket.tf_state.name
  description = "Name of the state bucket to use in backend blocks."
}
```

---

## Step 2 — Apply the bootstrap

```bash
cd ex01/bootstrap
terraform init
terraform apply -var="project_id=${TF_PROJECT}"
```

Type `yes` when prompted. Expected tail of the output:

```
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

Outputs:

state_bucket = "crunch-gcp-dev-tf-state"
```

Confirm the bucket exists and has versioning on:

```bash
gcloud storage buckets describe "gs://${TF_PROJECT}-tf-state" \
  --format="yaml(versioning, uniform_bucket_level_access)"
```

Expected:

```yaml
uniform_bucket_level_access:
  enabled: true
versioning:
  enabled: true
```

You now have a place to keep state. Note that the bootstrap module *itself* still uses local state (its `terraform.tfstate` is in `ex01/bootstrap/`). That is fine and conventional — the bootstrap is small, rarely changes, and you can commit its state to a private repo or migrate it later. Everything *else* uses the bucket.

---

## Step 3 — Write a root module that starts with LOCAL state

We need something to migrate. Create a tiny VPC root module in `ex01/vpc/main.tf` that starts with local state:

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  # No backend yet — starts local, so we have something to migrate in Step 5.
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_compute_network" "vpc" {
  name                    = "ex01-vpc"
  auto_create_subnetworks = false
  project                 = var.project_id
}

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

output "network_id" {
  value = google_compute_network.vpc.id
}
```

Apply it with local state:

```bash
cd ../vpc
terraform init
terraform apply -var="project_id=${TF_PROJECT}"
```

Expected tail:

```
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

Outputs:

network_id = "projects/crunch-gcp-dev/global/networks/ex01-vpc"
```

Confirm the state is local:

```bash
ls -la terraform.tfstate
# -rw-r--r--  ...  terraform.tfstate   <-- this file is the contract, and it is on your laptop. We fix that next.
```

---

## Step 4 — Add the GCS backend block

Edit `ex01/vpc/main.tf` and add a `backend "gcs"` block inside the `terraform { ... }` block (replace the `# No backend yet` comment):

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  backend "gcs" {
    bucket = "crunch-gcp-dev-tf-state"   # <-- use YOUR bucket name from Step 2
    prefix = "envs/dev/vpc"               # one prefix per (env, component)
  }
}
```

> Replace `crunch-gcp-dev-tf-state` with your actual bucket name. The `prefix` partitions one bucket into many independent state files — `envs/dev/vpc` is distinct from a future `envs/prod/vpc`.

---

## Step 5 — Migrate the state

```bash
terraform init -migrate-state
```

Terraform detects the backend changed from `local` to `gcs` and asks:

```
Initializing the backend...
Terraform detected that the backend type changed from "local" to "gcs".

Do you want to copy existing state to the new backend?
  Pre-existing state was found while migrating the previous "local" backend to the
  newly configured "gcs" backend. ...

  Enter a value: yes
```

Type `yes`. Expected:

```
Successfully configured the backend "gcs"! Terraform will automatically
use this backend unless the backend configuration changes.
```

Verify the state now lives in the bucket and the local copy is gone:

```bash
gcloud storage ls "gs://${TF_PROJECT}-tf-state/envs/dev/vpc/"
# gs://crunch-gcp-dev-tf-state/envs/dev/vpc/default.tfstate

ls terraform.tfstate 2>/dev/null && echo "STILL LOCAL (bad)" || echo "local state gone (good)"
# local state gone (good)
```

Run a plan to confirm everything still agrees — this is the clean-plan contract:

```bash
terraform plan -var="project_id=${TF_PROJECT}"
```

Expected:

```
No changes. Your infrastructure matches the configuration.
```

The state moved, and Terraform still sees zero drift. That is a successful migration.

---

## Step 6 — Prove the lock works (the payoff)

The GCS backend locks via a `.tflock` object. To see it work, hold a lock open in one terminal and try a second operation in another.

**Terminal A** — start an apply and pause it *during* the lock window. The easiest reliable way is to run an apply that prompts and just don't answer it yet:

```bash
# Terminal A — leave this sitting at the "Enter a value:" prompt. The lock is HELD.
terraform apply -var="project_id=${TF_PROJECT}"
# ... Terraform refreshes, shows the plan, then waits:
#   Do you really want to apply these actions?
#   Enter a value: _      <-- DO NOT type anything yet
```

While Terminal A sits at that prompt, the lock object exists in the bucket. Confirm:

```bash
# (a third terminal, or check from your file browser)
gcloud storage ls "gs://${TF_PROJECT}-tf-state/envs/dev/vpc/"
# default.tfstate
# default.tflock    <-- the lock is present
```

**Terminal B** — in the same `ex01/vpc` directory, try to plan. It will be rejected:

```bash
# Terminal B
terraform plan -var="project_id=${TF_PROJECT}"
```

Expected:

```
Error: Error acquiring the state lock

Error message: writing "gs://crunch-gcp-dev-tf-state/envs/dev/vpc/default.tflock"
failed: googleapi: Error 412: At least one of the pre-conditions you specified did
not hold., conditionNotMet
Lock Info:
  ID:        1718041200000000
  Operation: OperationTypeApply
  Who:       you@your-laptop
  Created:   2026-06-09 12:00:00 ...
```

That **412 precondition failed** is the lock doing its job: GCS rejected Terminal B's conditional write because the lock object already exists at a generation Terminal B didn't expect. This is exactly the protection that prevents two simultaneous applies from corrupting state.

Now go back to **Terminal A** and answer the prompt:

```bash
# Terminal A — type "no" to cancel (we don't actually need to apply anything; the plan was clean).
  Enter a value: no
```

Once Terminal A releases, Terminal B's `terraform plan` will succeed if you re-run it. The lock was held for exactly the duration of A's operation.

---

## Step 7 — Teardown

Destroy the VPC (state stays in the bucket; only the resource goes away):

```bash
cd ex01/vpc
terraform destroy -var="project_id=${TF_PROJECT}"   # type yes
```

Decide whether to keep the state bucket. For this exercise, you can destroy it too — but note `force_destroy = false` means you must empty it first:

```bash
cd ../bootstrap
# The bucket has versioned objects; empty it before destroy.
gcloud storage rm --recursive "gs://${TF_PROJECT}-tf-state/**" 2>/dev/null || true
terraform destroy -var="project_id=${TF_PROJECT}"   # type yes
```

> In the real mini-project you keep the state bucket — it is the foundation. Here we tear it down so the exercise leaves nothing behind. In practice the state bucket is the one thing you create once and never destroy.

Verify nothing is left:

```bash
gcloud compute networks list --project="${TF_PROJECT}" --format="value(name)" | grep ex01 || echo "no ex01 networks (good)"
gcloud storage buckets list --project="${TF_PROJECT}" --format="value(name)" | grep tf-state || echo "no state bucket (good)"
```

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `bootstrap/` created a versioned, uniform-bucket-level-access GCS state bucket with local state.
- [ ] You migrated the `vpc/` root module from local state into `gs://<bucket>/envs/dev/vpc/` with `terraform init -migrate-state`.
- [ ] The local `terraform.tfstate` is gone after migration and `terraform plan` reports `No changes`.
- [ ] You observed a `.tflock` object in the bucket while an apply was held open.
- [ ] You observed the **412 precondition** error when a second operation tried to acquire the held lock.
- [ ] You can explain, in your own words, why the state file is "the contract" and why two concurrent local applies corrupt it.
- [ ] Teardown left the project with no `ex01` networks and no orphaned state bucket.

---

## Reflection questions

1. The `prefix` was `envs/dev/vpc`. If you also had an `envs/prod/vpc` with the same prefix, what would go wrong? What is the rule for state-file partitioning?
2. Why does the bootstrap module use local state instead of storing its own state in the bucket it creates? Is there a way to break the chicken-and-egg without local state? (Hint: you can manually `gsutil mb` the bucket first, then write a backend block that points at it — but you've just moved the manual step, not eliminated it.)
3. The 412 error is an HTTP precondition-failed. What HTTP feature of GCS objects is Terraform using to implement the lock, and why does it not need a separate lock table the way the S3 backend historically did?
4. The state file contains resource attributes in plaintext, including secrets. Name two things you did in this exercise that protect that file (one IAM-shaped, one bucket-config-shaped), and one thing you would add for a production state bucket (Hint: customer-managed encryption keys — Week 14).

---

When this exercise feels comfortable, move to [Exercise 2 — the `for_each` subnet module](./exercise-02-for-each-subnet-module.tf).
