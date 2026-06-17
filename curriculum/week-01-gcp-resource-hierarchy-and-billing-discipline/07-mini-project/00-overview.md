# Mini-Project — The Landing-Zone Module

> Build a reusable Terraform **landing-zone module** that stands up an organization's folder/project tree (`bootstrap/`, `shared/`, `workloads/`), arms billing budgets with Slack alerting, and enforces "no compute until the budget is armed." This is the **foundational mini-project of C18.** Weeks 02 (IAM baseline) and 03 (VPC layer) and 04 (module library) all extend *this exact tree.* You will not start from a blank project again after this week.

This is the most important artifact you produce in Phase 1. It is the thing a senior engineer hands a junior and says "stand up the new business unit in here." It is opinionated, it is teardown-able, and it refuses to let anyone create compute in an un-budgeted project.

**Estimated time:** ~11 hours (split across Thursday, Friday, Saturday in the suggested schedule).

---

## What you will build

A two-layer Terraform repository plus a reusable module:

```
landing-zone/
├── README.md
├── modules/
│   ├── budgeted-project/        # the heart: a project that CANNOT host compute
│   │   ├── main.tf              #   until a budget covering it exists
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── slack-budget-alerting/   # topic + function + budget wiring
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       └── function/
│           ├── main.py
│           └── requirements.txt
├── bootstrap/                   # layer 0: local state -> migrated to GCS
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── backend.tf
├── platform/                    # layer 1: the tree, consumes the modules
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── backend.tf
│   └── terraform.tfvars.example
└── scripts/
    ├── validate.sh              # gcloud asset + budget checks
    ├── prove-alert.sh           # synthetic notification -> Slack
    └── teardown.sh              # the GATED destroy
```

By the end you have a public repo of ~400–500 lines of HCL + ~60 lines of Python that another engineer can clone, point at their org and billing account, and `apply` to get a safe, budgeted landing zone.

---

## The tree you provision

```
organizations/<org-id>
├── folder: bootstrap
│   └── project: <prefix>-tfstate      (GCS state bucket + Pub/Sub + alerting fn)
├── folder: shared
│   ├── project: <prefix>-vpc-host     (Week 03 fills this with a shared VPC)
│   └── project: <prefix>-logging      (Week 13 routes log sinks here)
└── folder: workloads
    ├── project: <prefix>-api-dev      (budgeted; compute gated on the budget)
    └── project: <prefix>-api-prod     (budgeted; compute gated on the budget)
```

Three folders, five projects. Empty for now where later weeks fill them in. The `shared/` projects are intentionally bare — they are placeholders that Week 03 and Week 13 extend, and leaving them empty now is correct, not lazy.

---

## Rules

- **You may** use the `hashicorp/google` and `hashicorp/google-beta` providers, the Functions Framework for the Cloud Function, and standard Terraform.
- **You may NOT** use the Cloud Foundation Toolkit `project-factory` or `folders` modules this week. Build the primitives by hand. You will adopt CFT in Week 04 *after* you understand what it abstracts. Using it now hides the exact lesson.
- **No long-lived service-account key files.** Authenticate with `gcloud auth application-default login`. A key file in the repo is an automatic fail.
- **The budget-before-compute dependency must be expressed in code**, not done by hand. The `budgeted-project` module enforces it; see below.
- **Remote state in GCS**, with versioning on the bucket. The bootstrap chicken-and-egg is part of the assignment, not something to dodge.
- Terraform 1.9+ (or OpenTofu 1.8+). `google` provider `~> 6.0`.

---

## The load-bearing idea: the `budgeted-project` module

The single most important design decision is that **a workload project cannot enable a billable compute API until a budget covering it exists.** You encode this so the rule holds on every apply, forever, even when a teammate adds a sixth project at 2am.

`modules/budgeted-project/main.tf`:

```hcl
terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
  }
}

variable "project_id"        { type = string }
variable "display_name"      { type = string }
variable "folder_id"         { type = string } # "folders/123..."
variable "billing_account"   { type = string }
variable "billing_topic_id"  { type = string } # the Pub/Sub topic for alerts
variable "budget_amount_usd" { type = number }
variable "enable_compute"    { type = bool, default = false }
variable "deletion_policy"   { type = string, default = "DELETE" } # labs only

resource "google_project" "this" {
  name            = var.display_name
  project_id      = var.project_id
  folder_id       = var.folder_id
  billing_account = var.billing_account
  deletion_policy = var.deletion_policy
}

# The budget for THIS project. Created before any compute API can be enabled.
resource "google_billing_budget" "this" {
  billing_account = var.billing_account
  display_name    = "${var.project_id}-monthly"

  budget_filter {
    projects        = ["projects/${google_project.this.number}"]
    calendar_period = "MONTH"
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount_usd)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    pubsub_topic   = var.billing_topic_id
    schema_version = "1.0"
  }
}

# Compute is OPTIONAL and GATED: it depends on the budget existing.
resource "google_project_service" "compute" {
  count   = var.enable_compute ? 1 : 0
  project = google_project.this.project_id
  service = "compute.googleapis.com"

  disable_on_destroy = true
  depends_on         = [google_billing_budget.this]
}

output "project_id"     { value = google_project.this.project_id }
output "project_number" { value = google_project.this.number }
output "budget_name"    { value = google_billing_budget.this.name }
```

Read the `depends_on` carefully. There is **no path** by which `compute.googleapis.com` gets enabled before the budget resource is created, because Terraform builds the dependency graph from that edge. That is the rule, in code, not in a runbook.

> **Why scope the budget by project *number*, not ID?** The `google_project.this.number` is available as a computed attribute after the project is created, and budget filters key on `projects/<number>`. Using the number also means a project rename (display name) never silently detaches the budget.

---

## The alerting module

`modules/slack-budget-alerting/` packages Exercise 1's plumbing as a module: the Pub/Sub topic, the IAM grant for the billing service agent, the Secret Manager secret for the webhook, and the gen2 Cloud Function. It exports `topic_id` so `budgeted-project` modules can wire their budgets to it.

`modules/slack-budget-alerting/main.tf` (abridged — you fill in the function deploy):

```hcl
resource "google_pubsub_topic" "billing_alerts" {
  project = var.alerting_project_id
  name    = "billing-alerts"
}

resource "google_pubsub_topic_iam_member" "billing_publisher" {
  project = var.alerting_project_id
  topic   = google_pubsub_topic.billing_alerts.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:billing-budget-alert@system.gserviceaccount.com"
}

resource "google_secret_manager_secret" "webhook" {
  project   = var.alerting_project_id
  secret_id = "slack-webhook-url"
  replication { auto {} }
}

resource "google_secret_manager_secret_version" "webhook" {
  secret      = google_secret_manager_secret.webhook.id
  secret_data = var.slack_webhook_url
}

# google_cloudfunctions2_function "budget_to_slack" -> you deploy function/main.py
# (source via a google_storage_bucket_object zip; see the function docs).

output "topic_id" { value = google_pubsub_topic.billing_alerts.id }
```

The `function/main.py` is the exact Slack-router from Lecture 2 / Exercise 1. Copy it in; do not rewrite it.

---

## Suggested order of operations

Build incrementally. Do not try to apply the whole tree at once on the first run.

### Phase 1 — Bootstrap with local state (~1.5h)

1. `mkdir landing-zone && cd landing-zone && git init`.
2. In `bootstrap/`, write Terraform (local backend) that:
   - Creates the `bootstrap` folder.
   - Creates the `<prefix>-tfstate` project via the `budgeted-project` module (`enable_compute = false` — state buckets need no compute), linked to billing.
   - Creates a **versioned** GCS bucket: `google_storage_bucket` with `versioning { enabled = true }` and `uniform_bucket_level_access = true`.
   - Stands up the `slack-budget-alerting` module in the tfstate project.
3. `terraform -chdir=bootstrap init && apply`. State is local for now.
4. Commit: `bootstrap: tree root + state bucket + alerting (local state)`.

### Phase 2 — Migrate bootstrap state to GCS (~0.5h)

1. Add `bootstrap/backend.tf` with the `backend "gcs"` block pointing at the bucket you just made, `prefix = "bootstrap"`.
2. `terraform -chdir=bootstrap init -migrate-state`. Confirm the migration when prompted.
3. Verify: `gcloud storage ls gs://<prefix>-tfstate/bootstrap/` shows `default.tfstate`.
4. Commit: `bootstrap: migrate state to GCS`.

This is the chicken-and-egg resolution from Lecture 1, §9. Get it working before moving on; everything else depends on the bucket existing.

### Phase 3 — The platform layer (~3h)

1. In `platform/`, set `backend "gcs"` from the start (`prefix = "platform"`).
2. Create the `shared/` and `workloads/` folders.
3. Create the two `shared` projects (`vpc-host`, `logging`) via `budgeted-project` with small budgets, `enable_compute = false`.
4. Create the two `workloads` projects (`api-dev`, `api-prod`) via `budgeted-project` with `enable_compute = true`, dev budget \$20, prod budget \$80.
5. Wire every `budgeted-project`'s `billing_topic_id` to the alerting module's `topic_id` output (read via a `terraform_remote_state` data source pointing at the bootstrap state, or pass it as a variable).
6. `terraform -chdir=platform init && apply`.
7. Commit: `platform: shared + workloads folders, five budgeted projects`.

### Phase 4 — Validation (~1.5h)

Write `scripts/validate.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

WORKLOADS=$(terraform -chdir=platform output -raw workloads_folder_id)
BILLING="${BILLING_ACCOUNT:?set BILLING_ACCOUNT}"

echo "== Projects under workloads/ =="
gcloud asset search-all-resources \
  --scope="folders/${WORKLOADS}" \
  --asset-types="cloudresourcemanager.googleapis.com/Project" \
  --format="value(displayName)"

echo "== Budgets on the billing account =="
gcloud billing budgets list --billing-account="${BILLING}" \
  --format="table(displayName, thresholdRules.len())"

echo "== Compute enabled only where intended =="
for p in $(terraform -chdir=platform output -json workload_project_ids | jq -r '.[]'); do
  printf "%s: " "$p"
  gcloud services list --enabled --project="$p" \
    --filter="config.name=compute.googleapis.com" --format="value(config.name)" \
    || echo "(none)"
done
```

Run it. The workloads folder should contain exactly `api-dev` and `api-prod`; each budget should report 4 threshold rules.

### Phase 5 — Prove the alert (~0.5h)

Write `scripts/prove-alert.sh` using the synthetic-publish technique from Exercise 1, Step 7. Run it; confirm a `:warning:` message lands in `#gcp-cost`. Screenshot it for your README.

### Phase 6 — README + idempotency check (~1h)

1. Run `terraform apply` again in both layers — both must report `No changes`. If not, you have non-deterministic config (commonly a `for_each` over an unstable set, or a missing `tostring`). Fix it.
2. Write the README (see required sections below).
3. `terraform fmt -recursive` and commit.

### Phase 7 — The teardown gate (~1h)

See the next section. This is mandatory and graded.

---

## The teardown gate (MANDATORY)

A landing zone you can stand up but cannot tear down is a liability. The gate proves you can destroy cleanly. **But** — Weeks 02–04 extend this tree, so you tear down only at the *end* of Week 01, after the quiz, and you keep the repo so you can re-apply at the start of Week 02.

`scripts/teardown.sh`:

```bash
#!/usr/bin/env bash
# Gated teardown. Destroys platform first, then bootstrap. Requires explicit
# confirmation because this deletes projects (soft-delete, 30-day window).
set -euo pipefail

echo "This will DESTROY the landing zone:"
echo "  - 2 workload projects, 2 shared projects (soft-deleted, 30-day undelete)"
echo "  - all budgets, the alerting function, the Pub/Sub topic"
echo "  - LAST: the tfstate project and its GCS state bucket"
echo
read -r -p "Type the org prefix to confirm: " confirm
if [[ "$confirm" != "${LZ_PREFIX:?set LZ_PREFIX}" ]]; then
  echo "Confirmation did not match. Aborting." >&2
  exit 1
fi

# Destroy the consuming layer first.
terraform -chdir=platform destroy -auto-approve

# Then bootstrap. Note: you cannot destroy the bucket that holds bootstrap's
# OWN remote state while using it. Migrate bootstrap state back to local first.
terraform -chdir=bootstrap init -migrate-state -backend=false
terraform -chdir=bootstrap destroy -auto-approve

echo "Teardown complete. Verify:"
echo "  gcloud projects list --filter='lifecycleState=DELETE_REQUESTED'"
```

Run it (only at the end of the week). Then verify:

```bash
gcloud projects list --filter='lifecycleState=DELETE_REQUESTED' \
  --format="table(projectId, lifecycleState)"
```

All five projects must show `DELETE_REQUESTED`. Paste that output into your README under "Teardown verification."

> **The bucket-holding-its-own-state gotcha:** you cannot `terraform destroy` the GCS bucket while Terraform is reading its state *from* that bucket. The script migrates bootstrap state back to local (`-backend=false`) before destroying, which is the canonical resolution. If you skip it, the destroy hangs trying to lock state in a bucket it is deleting.

---

## Acceptance criteria

- [ ] A public repo `c18-week-01-landing-zone-<yourhandle>` with the layout above.
- [ ] `modules/budgeted-project/` exists and **gates compute on the budget via `depends_on`**. The plan shows the edge.
- [ ] `modules/slack-budget-alerting/` deploys the Pub/Sub topic, the secret, and the gen2 Cloud Function.
- [ ] Bootstrap uses local state, then migrates to a **versioned** GCS bucket.
- [ ] Platform creates 3 folders and 5 projects in the correct parents.
- [ ] Two workload budgets exist (dev \$20, prod \$80), each with four threshold rules, wired to the topic.
- [ ] `compute.googleapis.com` is enabled on `api-dev` and `api-prod` **only**, never on the `shared` or `tfstate` projects.
- [ ] `scripts/validate.sh` runs clean and shows the right folder contents and budget counts.
- [ ] `scripts/prove-alert.sh` lands a real Slack message (screenshot in README).
- [ ] A second `terraform apply` in both layers reports `No changes`.
- [ ] No service-account key files anywhere; `gcloud auth application-default login` only.
- [ ] `scripts/teardown.sh` runs and `gcloud projects list` shows all five in `DELETE_REQUESTED`.
- [ ] README includes: a one-paragraph overview, the exact apply order, the bootstrap chicken-and-egg explanation, the validation transcript, the alert screenshot, the teardown verification, and a "Things I learned" section with at least 3 specific items.

---

## Rubric

| Criterion | Weight | What "great" looks like |
|-----------|-------:|-------------------------|
| Tree correctness | 20% | 3 folders, 5 projects, correct parents; idempotent apply |
| Budget-before-compute | 20% | The dependency is in code; compute genuinely cannot precede the budget |
| Alerting works | 15% | Synthetic publish lands in Slack; function logs confirm; webhook is a secret |
| Module quality | 15% | `budgeted-project` and `slack-budget-alerting` are reusable, parameterized, documented |
| State discipline | 10% | Versioned GCS backend; bootstrap migration done correctly |
| Teardown | 10% | `teardown.sh` works, including the state-migration-before-destroy step |
| README quality | 10% | A new engineer can clone and apply in <15 minutes from the README alone |

---

## What this prepares you for (the compounding)

This mini-project is the trunk. Later weeks graft onto it:

- **Week 02 — IAM baseline.** You add an `iam-baseline` module that grants `roles/viewer` to a platform group at the `workloads/` folder, sets up Workload Identity Federation for CI in the `bootstrap` project, and writes a custom role. It binds to the *folders and projects you created this week.* Do not delete the tree.
- **Week 03 — VPC layer.** The empty `<prefix>-vpc-host` project becomes a real shared-VPC host with subnets, Cloud NAT, and Private Google Access; the workload projects become service projects attached to it.
- **Week 04 — Module library.** You refactor `bootstrap/` and `platform/` and the per-week modules into a clean `modules/` library consumed by `envs/dev` and `envs/prod`, with remote state and a Cloud Build PR check. The `budgeted-project` module you wrote this week is the first entry in that library.

By Week 04 you are extending this repository, not rewriting it. That is the entire point of building it well now.

---

## Stretch (optional)

- Add the **hard-cap** consumer (Lecture 2 §7) on the alerting topic, pointed only at `api-dev`, behind a `var.enable_hard_cap` flag (default `false`).
- Add an **org policy** module that sets `constraints/compute.requireOsLogin` and `constraints/iam.disableServiceAccountKeyCreation` at the `workloads/` folder.
- Emit a **Mermaid diagram** of the tree from a `terraform output` so the README renders the hierarchy on GitHub.
- Wire a **GitHub Actions** workflow that runs `terraform validate` + `fmt -check` on PRs (you will make it apply via WIF in Week 02 — for now, plan-only).

---

## Resources

- *`google_project`*: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project>
- *`google_billing_budget`*: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/billing_budget>
- *`google_cloudfunctions2_function`*: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloudfunctions2_function>
- *GCS backend*: <https://developer.hashicorp.com/terraform/language/settings/backends/gcs>
- *Programmatic budget notifications*: <https://cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications>

---

## Submission

1. Push the repo to GitHub with a public URL.
2. Ensure the README has the apply order, the validation transcript, the Slack screenshot, and the teardown verification.
3. Confirm a fresh clone can `init`/`apply` against documented variables, and that `teardown.sh` cleanly destroys.
4. Post the repo URL in your cohort tracker. **Keep the repo** — Week 02 starts by re-applying it.
