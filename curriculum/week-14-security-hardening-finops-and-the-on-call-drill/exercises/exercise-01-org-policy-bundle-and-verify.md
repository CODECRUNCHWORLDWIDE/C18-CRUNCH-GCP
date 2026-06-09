# Exercise 1 — Apply an Organization Policy bundle and verify enforcement

**Goal:** Apply an Organization Policy bundle in Terraform that (a) restricts public IPs, (b) enforces CMEK on BigQuery, and (c) restricts resource locations — then *prove each one denies the forbidden action*. By the end you will have a three-constraint `org-policy` module and three terminal transcripts showing the deny. The transcripts are the deliverable, not the `terraform apply`.

**Estimated time:** 75 minutes.

---

## Setup

You need:

- `terraform` (or `tofu`) ≥ 1.7, `gcloud`, and `bq` on your path.
- A GCP project where you have `roles/orgpolicy.policyAdmin` (project scope is fine — Org Policy supports project-level policies) and `roles/cloudkms.admin`.
- The KMS API and BigQuery API enabled.

```bash
export PROJECT_ID="$(gcloud config get-value project)"
export REGION="us-central1"
gcloud services enable orgpolicy.googleapis.com cloudkms.googleapis.com \
  bigquery.googleapis.com compute.googleapis.com --project="$PROJECT_ID"
```

> If you are on the **full org path** and want to apply at the org node, swap `projects/${PROJECT_ID}` for `organizations/${ORG_ID}` in the `name` and `parent` fields. The verification commands are identical.

---

## Step 1 — Scaffold the module

```bash
mkdir -p ex01-org-policy && cd ex01-org-policy
```

Create `versions.tf`:

```hcl
terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
```

Create `variables.tf`:

```hcl
variable "project_id" { type = string }
variable "region"     { type = string  default = "us-central1" }

# The locations your org is allowed to create resources in. Anything else is denied.
variable "allowed_locations" {
  type    = list(string)
  default = ["in:us-locations"] # value group: all US locations. See gcp.resourceLocations docs.
}
```

---

## Step 2 — Write the three-constraint bundle

Create `main.tf`. This is the bundle: public-IP deny, CMEK-required on BigQuery, and resource-location restriction.

```hcl
data "google_project" "this" { project_id = var.project_id }

# --- (a) Restrict public IPs on VMs -----------------------------------------
resource "google_org_policy_policy" "deny_external_ip" {
  name   = "projects/${var.project_id}/policies/compute.vmExternalIpAccess"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      deny_all = "TRUE"
    }
  }
}

# --- (b) Enforce CMEK on BigQuery -------------------------------------------
# First, a KMS key the BigQuery service agent can use.
resource "google_kms_key_ring" "ring" {
  name     = "ex01-ring"
  location = var.region
}

resource "google_kms_crypto_key" "bq" {
  name            = "ex01-bq"
  key_ring        = google_kms_key_ring.ring.id
  rotation_period = "7776000s" # 90 days
  lifecycle { prevent_destroy = false } # exercise key — fine to destroy on teardown
}

resource "google_kms_crypto_key_iam_member" "bq_agent" {
  crypto_key_id = google_kms_crypto_key.bq.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:bq-${data.google_project.this.number}@bigquery-encryption.iam.gserviceaccount.com"
}

# Now the org policy that REQUIRES CMEK for BigQuery (and Compute disks).
resource "google_org_policy_policy" "require_cmek" {
  name   = "projects/${var.project_id}/policies/gcp.restrictNonCmekServices"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      values {
        # These services may NOT use Google-managed keys — CMEK is mandatory.
        denied_values = [
          "bigquery.googleapis.com",
        ]
      }
    }
  }
}

# --- (c) Restrict resource locations ----------------------------------------
resource "google_org_policy_policy" "restrict_locations" {
  name   = "projects/${var.project_id}/policies/gcp.resourceLocations"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      values {
        allowed_values = var.allowed_locations
      }
    }
  }
}

output "bq_key" { value = google_kms_crypto_key.bq.id }
```

---

## Step 3 — Apply

```bash
terraform init
terraform apply -var "project_id=${PROJECT_ID}" -var "region=${REGION}"
# Note the bq_key output — you will use it to create a COMPLIANT dataset.
export BQ_KEY="$(terraform output -raw bq_key)"
```

---

## Step 4 — Verify the deny (this is the actual exercise)

### (a) Public IP must be denied

```bash
# Compliant (internal only) — succeeds:
gcloud compute instances create probe-internal \
  --zone="${REGION}-a" \
  --network-interface="subnet=default,no-address" || \
  echo "(no default subnet? use your Week-03 subnet)"

# Forbidden (public IP) — MUST fail:
gcloud compute instances create probe-public --zone="${REGION}-a"
```

Expected failure:

```
ERROR: (gcloud.compute.instances.create) Could not fetch resource:
 - Constraint constraints/compute.vmExternalIpAccess violated for project <id>.
```

Clean up: `gcloud compute instances delete probe-internal --zone="${REGION}-a" --quiet 2>/dev/null || true`

### (b) Non-CMEK BigQuery must be denied; CMEK must succeed

```bash
# Forbidden (Google-managed key) — MUST fail:
bq mk --dataset "${PROJECT_ID}:ex01_no_cmek"
```

Expected failure:

```
BigQuery error in mk operation: Access Denied: ... organization policy
constraint "gcp.restrictNonCmekServices" ...
```

```bash
# Compliant (CMEK) — succeeds:
bq mk --dataset \
  --default_kms_key="${BQ_KEY}" \
  "${PROJECT_ID}:ex01_cmek"
bq show --format=prettyjson "${PROJECT_ID}:ex01_cmek" | grep kmsKeyName
```

### (c) Out-of-region resource must be denied

```bash
# Forbidden (a bucket in an EU/asia region while only US is allowed) — MUST fail:
gcloud storage buckets create "gs://ex01-eu-${PROJECT_ID}" --location="europe-west1"
```

Expected failure:

```
ERROR: ... Constraint "constraints/gcp.resourceLocations" violated ...
```

```bash
# Compliant (US region) — succeeds:
gcloud storage buckets create "gs://ex01-us-${PROJECT_ID}" --location="us-central1"
```

Capture all three failures and the three successes into `verify-ex01.txt`. That file is your deliverable.

---

## Acceptance criteria

- [ ] `terraform apply` creates the three org policies and the KMS key with `0` errors.
- [ ] Creating a VM with a public IP is **denied** with a `compute.vmExternalIpAccess` error.
- [ ] Creating a Google-key BigQuery dataset is **denied** with a `gcp.restrictNonCmekServices` error; a CMEK dataset **succeeds** and reports a `kmsKeyName`.
- [ ] Creating a bucket outside the allowed locations is **denied** with a `gcp.resourceLocations` error; an in-region bucket **succeeds**.
- [ ] `verify-ex01.txt` contains all three deny transcripts and all three success transcripts.

---

## Teardown

```bash
bq rm -r -f -d "${PROJECT_ID}:ex01_cmek"
gcloud storage rm --recursive "gs://ex01-us-${PROJECT_ID}"
terraform destroy -var "project_id=${PROJECT_ID}" -var "region=${REGION}"
```

> The org policies are removed by `terraform destroy`. If you applied at the *org* node, double-check nothing else depended on the restriction before removing it.

---

## Stretch

- Add `constraints/iam.disableServiceAccountKeyCreation` (Boolean, `enforce = "TRUE"`) to the bundle and verify a key create is denied.
- Flip `gcp.resourceLocations` to a *dry-run* policy (`dry_run_spec` block) and confirm the out-of-region bucket now *succeeds* but logs a would-be violation. This is the dry-run discipline from Lecture 1 §6.
- Write a custom constraint (`custom.*`) that denies BigQuery datasets without a `cost-center` label, and verify it.

---

## Hints

<details>
<summary>"Error 400: Location ... is not in the allowed locations"</summary>

That is the constraint working — but it may also bite a *legitimate* resource (your KMS key ring must be in an allowed location too). If your `allowed_locations` is US-only, make sure `region` is a US region, or the KMS key creation itself fails.

</details>

<details>
<summary>The CMEK deny did not fire</summary>

`gcp.restrictNonCmekServices` propagation can lag a minute or two after apply. Wait 60 seconds and retry `bq mk`. Also confirm you put `bigquery.googleapis.com` in `denied_values`, not `allowed_values`.

</details>

<details>
<summary>"PERMISSION_DENIED" on the org policy itself</summary>

You need `roles/orgpolicy.policyAdmin` at the scope you are writing to. At project scope, grant it on the project; at org scope, an org admin must grant it.

</details>

---

When all three denies are captured, move to [Exercise 2 — Binary Authorization with a Cloud Build attestor](exercise-02-binary-authorization-cloud-build-attestor.py).
