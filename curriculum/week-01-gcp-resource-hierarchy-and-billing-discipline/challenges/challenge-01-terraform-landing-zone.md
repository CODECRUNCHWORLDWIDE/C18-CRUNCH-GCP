# Challenge 1 — Terraform Landing Zone, Budgets Armed First

**Time estimate:** ~3 hours.

## Problem statement

Provision a real GCP **landing zone** entirely with Terraform: three top-level folders, five projects, and billing budgets that are armed *before* any compute primitive can be created. Then prove three things: the hierarchy is correct (via `gcloud asset`), the budget exists with the right thresholds, and a budget alert actually reaches Slack.

The shape:

```
organizations/<your-org>            (or a bootstrap parent if you have no org)
├── folder: bootstrap
│   └── project: <prefix>-tfstate     (holds the GCS state bucket + alerting infra)
├── folder: shared
│   ├── project: <prefix>-vpc-host    (the shared VPC host - empty for now)
│   └── project: <prefix>-logging     (central log sink target - empty for now)
└── folder: workloads
    ├── project: <prefix>-api-dev
    └── project: <prefix>-api-prod
```

Five projects, three folders. Budgets armed before a single VM, bucket-of-data, or function (beyond the alerting function) can be created.

## The hard constraint: budgets before compute

This is the spirit of the whole week. You must structure the Terraform so that **the budget resources are a dependency of the workload projects' ability to host compute.** Concretely, achieve this with at least one of:

- A `depends_on` from each workload project's `google_project_service` (for `compute.googleapis.com`) onto the `google_billing_budget` — so `compute` cannot be enabled until the budget exists.
- An org policy / module gate that refuses to enable billable APIs on a project that is not covered by a budget.

The grader will read your `plan` and confirm the dependency edge exists. "I created the budget first by hand" does not count — the *dependency* must be expressed in code so it holds on every apply.

## Requirements

1. **Bootstrap layer** (`bootstrap/`, local state initially):
   - Creates the `bootstrap` folder and the `<prefix>-tfstate` project, linked to billing.
   - Creates a **versioned** GCS bucket for remote state.
   - Migrates its own state into that bucket (`terraform init -migrate-state`).
   - Stands up the Pub/Sub topic, the Slack-router Cloud Function (from Exercise 1), and grants the billing service agent publish on the topic.

2. **Platform layer** (`platform/`, GCS backend):
   - Creates `shared/` and `workloads/` folders.
   - Creates all five projects in the right folders, each linked to billing.
   - Creates **one budget per environment scope**: a dev budget (e.g. \$20) scoped to `<prefix>-api-dev`, and a prod budget (e.g. \$80) scoped to `<prefix>-api-prod`, both wired to the Pub/Sub topic with 50/90/100% actual thresholds plus a forecasted-100% rule.
   - Enables `compute.googleapis.com` on the two workload projects **only after** the budgets exist (the dependency edge above).

3. **Validation** (a script, `validate.sh`, or documented commands):
   - `gcloud asset search-all-resources --scope=folders/<workloads-folder-id>` lists exactly the two workload projects.
   - `gcloud billing budgets list --billing-account=<acct>` shows both budgets with four threshold rules each.
   - A synthetic Pub/Sub publish (the technique from Exercise 1, Step 7) lands a message in `#gcp-cost`.

4. **Idempotent.** `terraform apply` a second time shows `No changes`. The grader runs apply twice.

## Acceptance criteria

- [ ] A repo with two Terraform layers: `bootstrap/` and `platform/`, each with `main.tf`, `variables.tf`, `outputs.tf`, and a `backend.tf` (GCS for `platform/`, GCS-after-migration for `bootstrap/`).
- [ ] `terraform validate` passes in both layers.
- [ ] `terraform apply` in `platform/` creates 3 folders and 5 projects, all in the correct parent.
- [ ] **The plan shows `compute.googleapis.com` on each workload project depending on its budget.** This is the load-bearing criterion.
- [ ] Two budgets exist (dev + prod), each with four threshold rules (50/90/100% actual + 100% forecasted), each wired to the Pub/Sub topic.
- [ ] `gcloud asset search-all-resources` confirms the workload-folder contents.
- [ ] A synthetic notification produces a real Slack message in `#gcp-cost`.
- [ ] A second `terraform apply` reports `No changes`.
- [ ] No long-lived service-account key files anywhere in the repo (`gcloud auth application-default login` only).
- [ ] A `README.md` documenting the bootstrap chicken-and-egg resolution and the exact apply order.

## Validation transcript you should be able to produce

```bash
$ terraform -chdir=platform apply -auto-approve
...
Apply complete! Resources: 13 added, 0 changed, 0 destroyed.

$ gcloud asset search-all-resources \
    --scope=folders/$(terraform -chdir=platform output -raw workloads_folder_id) \
    --asset-types=cloudresourcemanager.googleapis.com/Project \
    --format="value(displayName)"
acme-api-dev
acme-api-prod

$ gcloud billing budgets list --billing-account=$BILLING_ACCOUNT \
    --format="table(displayName, thresholdRules.len())"
DISPLAY_NAME           THRESHOLD_RULES
acme-api-dev-monthly   4
acme-api-prod-monthly  4

$ ./validate.sh   # publishes a synthetic 90% notification
Published synthetic alert. Check #gcp-cost.
# -> Slack: :warning: Budget alert: acme-api-dev-monthly crossed 90% (18.00 / 20.00 USD)
```

## Stretch

- **Build the hard cap.** Add the billing-disable consumer from Lecture 2 on the same topic, pointed *only* at `<prefix>-api-dev`. Trigger a real ~\$1 charge (spin up an `e2-micro`, leave it 20 minutes) so an actual — not synthetic — alert fires, and confirm the cap detaches billing at 100%. **Then re-link billing and destroy.** Budget ~\$1 and tear down promptly.
- **Add an org policy** at the `workloads/` folder: `constraints/compute.requireOsLogin = true`. Confirm it inherits to both workload projects (`gcloud resource-manager org-policies list --folder=<id>`). This previews Week 02/14.
- **Add a `terragrunt.hcl`** to DRY the backend config across layers. (You will do this properly in Week 04 — a head start is fine.)
- **Emit a Mermaid diagram** of the tree from `terraform output` so your README renders the hierarchy on GitHub.

## Hints

<details>
<summary>Expressing "budget before compute" as a dependency edge</summary>

```hcl
resource "google_billing_budget" "api_dev" {
  # ... thresholds, scope to acme-api-dev ...
}

resource "google_project_service" "api_dev_compute" {
  project = google_project.api_dev.project_id
  service = "compute.googleapis.com"

  # The budget MUST exist before compute can be enabled here.
  depends_on = [google_billing_budget.api_dev]
}
```

`terraform graph | grep -A1 google_project_service.api_dev_compute` (or just reading the plan) shows the edge.

</details>

<details>
<summary>Getting the folder ID for the asset search</summary>

`google_folder.workloads.name` is `folders/123456789012`. Output the bare number:

```hcl
output "workloads_folder_id" {
  value = trimprefix(google_folder.workloads.name, "folders/")
}
```

</details>

<details>
<summary>If you have no organization (gmail-only)</summary>

You cannot create real `google_folder` resources without an org node. Two options: (1) set up free Cloud Identity on a domain you control and get an org — strongly recommended, the whole course is more realistic with one; or (2) simulate the folder layer with project naming + labels and document the deviation. Option 1 is worth the 30 minutes.

</details>

## Submission

Commit the repo with both layers and `validate.sh`. Make sure a fresh clone can run `terraform -chdir=bootstrap init && apply`, then `platform` init/apply, against the documented variables. Paste the validation transcript into the README. **Do not run `terraform destroy` yet** — the mini-project extends this exact tree, and the teardown gate lives there.
