# Exercise 1 — A Custom Least-Privilege Role

**Goal:** Write a custom IAM role that grants the minimum permission set for one stated job function, apply it with Terraform, bind it to a test service account, and prove it is genuinely minimal — not too wide, not too narrow — using Policy Analyzer and a real access test.

**Estimated time:** 50 minutes.

---

## The job function

> **The "report publisher."** A nightly batch job reads rows from one BigQuery table (`analytics.daily_orders`), renders a CSV report, and writes the CSV object into one Cloud Storage bucket (`reports-<project>`). It must **not** be able to delete objects, create buckets, read any other table, or touch IAM. It needs exactly: read the source table's data, and create objects in the reports bucket.

Your task is to express that — and *only* that — as a custom role, then prove the claim.

---

## Setup

Work in your Week 1 `workloads/dev` project. Set a shell variable so the commands below copy cleanly:

```bash
export PROJECT_ID="$(gcloud config get-value project)"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
echo "Project: $PROJECT_ID ($PROJECT_NUMBER)"
```

Create a working directory and a Terraform skeleton:

```bash
mkdir -p ex01-report-publisher && cd ex01-report-publisher
```

---

## Step 1 — Find the exact permissions

Do **not** guess. Use the predefined roles as a permission dictionary. The two predefined roles in the neighborhood are `roles/bigquery.dataViewer` and `roles/storage.objectCreator`. List their permissions:

```bash
gcloud iam roles describe roles/bigquery.dataViewer --format='value(includedPermissions)' | tr ';' '\n'
gcloud iam roles describe roles/storage.objectCreator --format='value(includedPermissions)' | tr ';' '\n'
```

From those lists, the *minimum* set for "read one table's data" plus "create objects in one bucket" is:

- `bigquery.tables.getData` — read the rows.
- `bigquery.tables.get` — read the table metadata (schema) so the job can parse rows.
- `bigquery.jobs.create` — required to run the query job that reads the data.
- `storage.objects.create` — write the CSV.

Notice what's **not** there: no `storage.objects.delete`, no `storage.buckets.create`, no `bigquery.datasets.create`, no `*.setIamPolicy`. That's the discipline.

---

## Step 2 — Write the role in Terraform

Create `main.tf`:

```hcl
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
}

variable "project_id" { type = string }

resource "google_project_iam_custom_role" "report_publisher" {
  role_id     = "reportPublisher"
  project     = var.project_id
  title       = "Report Publisher"
  description = "Read one source table and create report objects. Nothing else."
  permissions = [
    "bigquery.jobs.create",
    "bigquery.tables.get",
    "bigquery.tables.getData",
    "storage.objects.create",
  ]
  stage = "GA"
}

# A test service account to bind the role to.
resource "google_service_account" "reporter" {
  project      = var.project_id
  account_id   = "reporter-test"
  display_name = "Exercise 1 report publisher (test)"
}

# Bind the custom role at the project level for this exercise.
# (In production you'd scope the storage permission to the one bucket with a
#  condition — see Exercise 2 — but project scope is fine for the drill.)
resource "google_project_iam_member" "reporter_binding" {
  project = var.project_id
  role    = google_project_iam_custom_role.report_publisher.id
  member  = "serviceAccount:${google_service_account.reporter.email}"
}

output "role_id" {
  value = google_project_iam_custom_role.report_publisher.id
}
output "reporter_email" {
  value = google_service_account.reporter.email
}
```

Apply:

```bash
terraform init
terraform apply -var="project_id=$PROJECT_ID"
```

Expected tail of the output:

```
Apply complete! Resources: 3 added, 0 changed, 0 destroyed.

Outputs:
reporter_email = "reporter-test@<project>.iam.gserviceaccount.com"
role_id = "projects/<project>/roles/reportPublisher"
```

---

## Step 3 — Verify minimality with Policy Analyzer

Policy Analyzer answers "which principals can do permission X on resource Y." Use it to confirm the reporter can read the table data — and *cannot* delete objects.

First, confirm the **granted** access (should return the reporter):

```bash
gcloud asset analyze-iam-policy \
  --organization="$(gcloud projects describe "$PROJECT_ID" --format='value(parent.id)')" \
  --permissions="bigquery.tables.getData" \
  --identity="serviceAccount:reporter-test@$PROJECT_ID.iam.gserviceaccount.com" \
  --format='value(analysisResults.accessControlLists)' 2>/dev/null \
  || gcloud asset analyze-iam-policy \
       --scope="projects/$PROJECT_ID" \
       --full-resource-name="//cloudresourcemanager.googleapis.com/projects/$PROJECT_ID" \
       --permissions="bigquery.tables.getData"
```

If your account can't analyze at the org level, use the project-scope form (the second command). You should see the reporter SA in the results for `bigquery.tables.getData`.

Now confirm the **absent** access — there should be **no** result for delete:

```bash
gcloud asset analyze-iam-policy \
  --scope="projects/$PROJECT_ID" \
  --full-resource-name="//cloudresourcemanager.googleapis.com/projects/$PROJECT_ID" \
  --permissions="storage.objects.delete" \
  --format='value(analysisResults)' \
  | grep -q "reporter-test" && echo "FAIL: reporter can delete!" || echo "PASS: reporter cannot delete"
```

Expected:

```
PASS: reporter cannot delete
```

---

## Step 4 — Prove it with a real access test (impersonation, no key)

Grant yourself token-creator on the reporter SA, then impersonate it to try a write and a forbidden delete:

```bash
gcloud iam service-accounts add-iam-policy-binding \
  "reporter-test@$PROJECT_ID.iam.gserviceaccount.com" \
  --member="user:$(gcloud config get-value account)" \
  --role="roles/iam.serviceAccountTokenCreator"

# Create the reports bucket and a source artifact to write.
gcloud storage buckets create "gs://reports-$PROJECT_ID" --location=us-central1 || true
echo "order_id,total" > /tmp/report.csv

# Write SHOULD succeed (the role grants storage.objects.create):
gcloud storage cp /tmp/report.csv "gs://reports-$PROJECT_ID/report.csv" \
  --impersonate-service-account="reporter-test@$PROJECT_ID.iam.gserviceaccount.com" \
  && echo "PASS: create succeeded"

# Delete SHOULD fail (the role does not grant storage.objects.delete):
gcloud storage rm "gs://reports-$PROJECT_ID/report.csv" \
  --impersonate-service-account="reporter-test@$PROJECT_ID.iam.gserviceaccount.com" \
  && echo "FAIL: delete should not have worked" \
  || echo "PASS: delete denied (403), exactly as designed"
```

Expected:

```
PASS: create succeeded
ERROR: ... 403 ... does not have storage.objects.delete access ...
PASS: delete denied (403), exactly as designed
```

The 403 on delete is the win. The role is wide enough to do the job and no wider.

---

## Acceptance criteria

- [ ] A custom role `reportPublisher` exists with **exactly** four permissions, defined in Terraform.
- [ ] You used `gcloud iam roles describe` on predefined roles to *derive* the permissions rather than guessing.
- [ ] Policy Analyzer confirms the reporter SA *has* `bigquery.tables.getData` and *lacks* `storage.objects.delete`.
- [ ] The impersonated write succeeds and the impersonated delete returns 403.
- [ ] No service-account key was created at any point.

---

## Teardown

```bash
gcloud storage rm -r "gs://reports-$PROJECT_ID" || true
terraform destroy -var="project_id=$PROJECT_ID"
```

Confirm the zero-keys promise:

```bash
gcloud iam service-accounts keys list \
  --iam-account="reporter-test@$PROJECT_ID.iam.gserviceaccount.com" \
  --managed-by=user --format='value(name)' 2>/dev/null || echo "(SA already deleted — good)"
```

---

## Hints

<details>
<summary>Hint 1 — "I can't analyze at the org level"</summary>

`gcloud asset analyze-iam-policy` needs `roles/cloudasset.viewer` somewhere in the scope you query. If you only control a project, query `--scope="projects/$PROJECT_ID"` and skip the org form. The result set is the same for project-scoped bindings.
</details>

<details>
<summary>Hint 2 — "terraform apply says the role already exists"</summary>

Custom roles are *soft-deleted* for 7 days after `terraform destroy`. If you re-run within that window, either `terraform import` the existing role or pick a new `role_id` (e.g. `reportPublisher2`). This soft-delete behavior is a real production gotcha — note it.
</details>

<details>
<summary>Hint 3 — "the write fails with a bucket permission error, not an object error"</summary>

You may need `storage.objects.create` *and* the bucket to use uniform bucket-level access (the default for new buckets). If you created the bucket with fine-grained ACLs, switch it: `gcloud storage buckets update gs://... --uniform-bucket-level-access`.
</details>
