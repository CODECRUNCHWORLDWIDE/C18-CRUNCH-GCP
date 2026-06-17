# Week 1 — Resources

Almost everything here is **free**. Google Cloud documentation is free without an account. The Terraform provider docs are open. The two books listed have free chapters or are worth buying once; they are flagged. No resource on this page is required behind a paywall to pass the week.

## Required reading (work it into your week)

- **Resource hierarchy overview** — the canonical Google Cloud page. Read it twice:
  <https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy>
- **Creating and managing organizations**:
  <https://cloud.google.com/resource-manager/docs/creating-managing-organization>
- **Creating and managing folders**:
  <https://cloud.google.com/resource-manager/docs/creating-managing-folders>
- **Creating and managing projects**:
  <https://cloud.google.com/resource-manager/docs/creating-managing-projects>
- **Cloud Billing overview** — the billing account is its own object; this explains why:
  <https://cloud.google.com/billing/docs/concepts>
- **Create, edit, or delete budgets and budget alerts**:
  <https://cloud.google.com/billing/docs/how-to/budgets>
- **Manage programmatic budget alert notifications** (the Pub/Sub path you will wire to Slack):
  <https://cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications>

## The IAM and policy-inheritance angle

You will go deep on IAM in Week 2. This week, read only enough to understand how policy flows down the hierarchy.

- **IAM overview** (skim §"Policy inheritance"):
  <https://cloud.google.com/iam/docs/overview>
- **Understanding IAM policy inheritance**:
  <https://cloud.google.com/iam/docs/resource-hierarchy-access-control>
- **Organization policy service** (constraints that ride the hierarchy — you preview this in the challenge):
  <https://cloud.google.com/resource-manager/docs/organization-policy/overview>

## Quotas

- **Working with quotas** — the model: rate vs. allocation, per-project, per-region:
  <https://cloud.google.com/docs/quotas/overview>
- **View and manage quotas**:
  <https://cloud.google.com/docs/quotas/view-manage>
- **Quota adjuster and request increases**:
  <https://cloud.google.com/docs/quotas/help/request_increase>

## The `gcloud` CLI

- **`gcloud` CLI overview** — install and first run:
  <https://cloud.google.com/sdk/docs>
- **Managing `gcloud` CLI configurations** — the heart of Exercise 3:
  <https://cloud.google.com/sdk/docs/configurations>
- **`gcloud` cheat sheet** — print it, tape it to your monitor for a week:
  <https://cloud.google.com/sdk/docs/cheatsheet>
- **`gcloud topic configurations`** — run `gcloud topic configurations` locally; it is the best doc on named configs:
  <https://cloud.google.com/sdk/gcloud/reference/topic/configurations>

## Cloud Asset Inventory (validation)

- **Cloud Asset Inventory overview** — used to validate your hierarchy in the challenge:
  <https://cloud.google.com/asset-inventory/docs/overview>
- **`gcloud asset` reference**:
  <https://cloud.google.com/sdk/gcloud/reference/asset>

## Terraform for GCP

- **`hashicorp/google` provider docs** — bookmark these; you live here for 15 weeks:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs>
- **`google_folder`**: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_folder>
- **`google_project`**: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project>
- **`google_billing_budget`**: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/billing_budget>
- **`google_project_service`** (enabling APIs): <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_service>
- **GCS backend for remote state**: <https://developer.hashicorp.com/terraform/language/settings/backends/gcs>
- **Terraform on Google Cloud — best practices**:
  <https://cloud.google.com/docs/terraform/best-practices-for-terraform>

## Cloud Foundation Toolkit (read, don't adopt yet)

You will not use these in Week 1 — you build the primitives by hand first. But knowing they exist matters.

- **Cloud Foundation Toolkit landing page**:
  <https://cloud.google.com/docs/terraform/blueprints/terraform-blueprints>
- **`terraform-google-project-factory`** — how Google packages "make a project the right way":
  <https://github.com/terraform-google-modules/terraform-google-project-factory>
- **`terraform-google-folders`**:
  <https://github.com/terraform-google-modules/terraform-google-folders>

## Python for the GCP APIs

The Slack-router Cloud Function and Exercise 2 use Python.

- **Cloud Client Libraries for Python** (`google-cloud-*`):
  <https://cloud.google.com/python/docs/reference>
- **`google-cloud-billing-budgets`** client:
  <https://cloud.google.com/python/docs/reference/billingbudgets/latest>
- **Functions Framework for Python** (run a Cloud Function locally):
  <https://github.com/GoogleCloudPlatform/functions-framework-python>
- **Slack Incoming Webhooks** (where the alert lands):
  <https://api.slack.com/messaging/webhooks>

## Books

- ***Google Cloud Platform in Action* / *Google Cloud Cookbook* (O'Reilly)** — the Cookbook is the more current of the two for 2026 task-level recipes. Buy once; recipes 1.x cover the hierarchy:
  <https://www.oreilly.com/library/view/google-cloud-cookbook/9781492092599/>
- ***Terraform: Up & Running*, 3rd ed., Yevgeniy Brikman** — cloud-agnostic but the state, module, and environment-layout chapters are the best in print. Chapter on backends is directly relevant this week:
  <https://www.terraformupandrunning.com/>
- **Google Cloud free *Architecture Framework*** (free, online, current) — the security and cost pillars are the closest thing to an opinionated textbook for this week:
  <https://cloud.google.com/architecture/framework>

## Talks and video (free, no signup)

- **"How to organize your Google Cloud resources"** — Google Cloud Tech, the canonical hierarchy talk:
  <https://www.youtube.com/@googlecloudtech>
  *(If a specific link rots, the Google Cloud Tech channel reposts the hierarchy and billing talks each Next conference.)*
- **Google Cloud Next session archive** — billing, FinOps, and org-design sessions are recorded yearly:
  <https://cloud.withgoogle.com/next>
- **"FinOps Foundation" — cloud cost discipline** (vendor-neutral, GCP-applicable):
  <https://www.finops.org/>

## Tools you'll use this week

- **`gcloud` CLI** — installed with the Google Cloud SDK. Verify with `gcloud version`.
- **`terraform`** (or **`tofu`**, OpenTofu) — 1.9+ for the syntax used here. `terraform version`.
- **`python3`** 3.11+ with `pip install google-cloud-billing-budgets functions-framework requests`.
- **`jq`** — for slicing `gcloud --format=json` output. `jq --version`.
- **A Slack workspace** you can add an Incoming Webhook to. A free personal workspace is fine.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Organization** | The root node of the hierarchy. One per Cloud Identity / Workspace domain. Free. |
| **Folder** | A grouping node between org and project. Holds projects and other folders. Carries IAM and org policy. |
| **Project** | The primary isolation unit. Holds resources. Has an immutable ID, a number, and a display name. |
| **Resource** | A VM, a bucket, a Pub/Sub topic — anything that lives inside a project. |
| **Billing account** | The payment object. Many projects link to one. Budgets and alerts attach here. |
| **Project ID** | Globally unique, immutable, human-chosen string. The thing every API call references. |
| **Project number** | Globally unique, immutable integer GCP assigns. Used by some APIs and IAM bindings. |
| **Budget** | A named spend target on a billing account (or scoped to projects/labels) with threshold rules. |
| **Threshold rule** | "Notify at X% of the budget amount" — actual or forecasted spend. |
| **Quota** | A limit on resource consumption. Rate (per-minute API calls) or allocation (count of resources). |
| **Landing zone** | The baseline org/folder/project/network/IAM scaffold you stand up before any workload. |
| **`gcloud` configuration** | A named bundle of CLI properties (account, project, region). Switch with `activate`. |
| **CFT** | Cloud Foundation Toolkit — Google's library of opinionated Terraform modules. |

---

*If a link 404s, please open an issue so we can replace it. Google moves doc URLs more often than it should.*
