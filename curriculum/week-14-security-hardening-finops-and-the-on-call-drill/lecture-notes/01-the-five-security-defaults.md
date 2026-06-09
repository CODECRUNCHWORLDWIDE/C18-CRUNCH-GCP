# Lecture 1 — The Five Security Defaults You Must Change on Day One of Any New GCP Org

> **Reading time:** ~80 minutes. **Hands-on time:** ~50 minutes (you apply the Org Policy bundle, stand up KMS + a perimeter dry-run, and confirm the deploy path still works).

This is the lecture that turns "I provisioned a thing" into "I provisioned a thing that cannot be misused." Everything in Phase 4 assumes you can lock down a project; this lecture is the lockdown. By the end of it you will know the five GCP defaults that own production organizations, the exact control that closes each one, the order to apply them in so you do not lock yourself out, and — the part everyone skips — how to *verify* each control by attempting the forbidden thing and watching it fail.

A senior engineer does not memorize a checklist of 200 CIS benchmark line items. A senior engineer knows the *five defaults that actually own orgs in the wild*, closes those first, and then uses Security Command Center and the CIS benchmark to find the long tail. We do the five. If you do nothing else this week, do the five.

## 0 — Which path are you on: full org or bare trial project?

Before anything else, find out what scope you have, because three of the five controls are org-or-folder-scoped resources and two of them (VPC Service Controls especially) *require* an organization with an Access Context Manager policy.

```bash
# Do you have an organization?
gcloud organizations list
# If this prints an ORGANIZATION_ID, you are on the FULL path.
# If it prints nothing, you are on a BARE TRIAL PROJECT.
```

**Full path (you have a Cloud Identity / Workspace org).** You apply Organization Policy at the org or folder node, you create an Access Context Manager access policy, and you wrap the production project in a real VPC SC perimeter. This is the production posture and what the mini-project grades against if you have it.

**Bare-trial path (standalone project, no org).** Organization Policy still works — it supports *project-level* policies that act as local overrides — so four of the five controls apply unchanged at the project scope. VPC Service Controls is the one you cannot fully exercise without an org; for that control you will do the *dry-run design* and submit the perimeter spec, and the lecture flags exactly where the bare-trial path diverges. You lose nothing pedagogically; you just cannot enforce the perimeter for real on a no-org account.

Throughout this lecture, commands that need an org use `$ORG_ID`; commands that work at project scope use `$PROJECT_ID`. Set both now:

```bash
export ORG_ID="$(gcloud organizations list --format='value(ID)' | head -n1)"   # may be empty
export PROJECT_ID="$(gcloud config get-value project)"
export REGION="us-central1"
echo "ORG_ID=${ORG_ID:-<none — bare trial path>}  PROJECT_ID=$PROJECT_ID"
```

## 1 — Default #1: external IPs are allowed everywhere

**The default.** A fresh org lets anyone with `compute.instances.create` attach an *external* IP to a VM. That is one click (or one missing Terraform argument) away from a database VM, a Jenkins box, or a "temporary debug instance" sitting on the public internet with SSH open. The single most common GCP breach pattern is not an exotic zero-day; it is a VM with a public IP and a weak credential.

**The control.** The Organization Policy list constraint `constraints/compute.vmExternalIpAccess`. Set its allowed list to empty (deny all) and no VM in the scope can get an external IP. Egress still works through Cloud NAT (which you built in Week 03), so this breaks nothing that was designed correctly — it only breaks the lazy pattern of giving a VM a public IP because NAT felt like effort.

```hcl
# org-policy/external-ip.tf
# Deny external IPs on all VMs in the project (or org/folder — change the parent).
resource "google_org_policy_policy" "deny_external_ip" {
  name   = "projects/${var.project_id}/policies/compute.vmExternalIpAccess"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      # An empty allow/deny list with deny_all = true denies the whole list.
      deny_all = "TRUE"
    }
  }
}
```

**Verify the deny.** Try to create a VM with a public IP. It must fail.

```bash
# This one is fine — internal IP only, egress via Cloud NAT:
gcloud compute instances create probe-internal \
  --zone="${REGION}-a" \
  --network-interface="subnet=default,no-address"

# This one MUST fail with a constraint-violation error:
gcloud compute instances create probe-public \
  --zone="${REGION}-a"
# ERROR: ... Constraint constraints/compute.vmExternalIpAccess violated for
#        projects/<project>. Add the instance project, folder, or org to ...
```

If `probe-public` succeeds, your policy is not in effect — most likely you applied it at a node that does not cover this project, or a higher node has `inheritFromParent = false` with an allow. Clean up the probe (`gcloud compute instances delete probe-internal probe-public --zone="${REGION}-a"`).

## 2 — Default #2: service-account key creation is allowed

**The default.** Anyone with `iam.serviceAccountKeys.create` can mint a long-lived JSON key for a service account. That key is a bearer credential with no expiry, no rotation, and a strong tendency to end up committed to a repo, pasted into a Slack DM, or baked into a Docker image. Every keyfile is a credential you will eventually leak. Week 02 taught you Workload Identity Federation precisely so you would never need one.

**The control.** The Boolean constraint `constraints/iam.disableServiceAccountKeyCreation`. Enforce it and the API to create a key returns an error. Combine it with `constraints/iam.disableServiceAccountKeyUpload` if you also want to forbid importing externally-generated keys.

```hcl
# org-policy/no-sa-keys.tf
resource "google_org_policy_policy" "no_sa_keys" {
  name   = "projects/${var.project_id}/policies/iam.disableServiceAccountKeyCreation"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }
}
```

**Verify the deny.**

```bash
SA="$(gcloud iam service-accounts list --format='value(email)' | head -n1)"
gcloud iam service-accounts keys create /tmp/should-fail.json --iam-account="$SA"
# ERROR: ... Key creation is not allowed on this service account.
#        Constraint constraints/iam.disableServiceAccountKeyCreation ...
```

If a key file lands in `/tmp/should-fail.json`, delete it *and the key* immediately (`gcloud iam service-accounts keys delete`) and fix the policy. A leaked key from a verification step is still a leaked key.

## 3 — Default #3: public Cloud Storage is allowed

**The default.** A bucket can be made world-readable with `allUsers` or world-accessible to any Google account with `allAuthenticatedUsers`. "We'll just make the bucket public for the static assets" is how customer PII ends up indexed by a search engine. The fix is not "remember not to do that"; the fix is "make it structurally impossible, then allow exceptions deliberately."

**The control.** The list constraint `constraints/storage.publicAccessPrevention` enforces public access prevention org-wide so a bucket cannot be made public even if someone tries. (There is also a bucket-level `publicAccessPrevention = enforced` setting; the org policy makes it the non-overridable default.)

```hcl
# org-policy/no-public-storage.tf
resource "google_org_policy_policy" "no_public_buckets" {
  name   = "projects/${var.project_id}/policies/storage.publicAccessPrevention"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }
}
```

**Verify the deny.**

```bash
BUCKET="probe-public-$(date +%s)-${PROJECT_ID}"
gcloud storage buckets create "gs://${BUCKET}" --location="$REGION"
# This MUST fail:
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="allUsers" --role="roles/storage.objectViewer"
# ERROR: ... One or more users named in the policy do not belong to a permitted
#        customer ... public access prevention ...
gcloud storage buckets delete "gs://${BUCKET}"
```

## 4 — Default #4: the default network exists

**The default.** A new project is created with a "default" VPC network: one auto-mode network with a subnet in every region and a permissive set of firewall rules including `default-allow-ssh` (0.0.0.0/0 → tcp:22) and `default-allow-rdp`. Auto-mode networks and world-open SSH are the opposite of the deliberate VPC you built in Week 03. You want every network to be a network *you* designed, with the firewall rules *you* wrote.

**The control.** The Boolean constraint `constraints/compute.skipDefaultNetworkCreation`, enforced at the org or folder *before any project is created*, means new projects ship with no default network at all. For projects that already have one, delete the default network and its permissive rules by hand (or in Terraform) after confirming nothing depends on it.

```hcl
# org-policy/no-default-network.tf  (apply at the ORG or FOLDER, not the project,
# because the effect is on FUTURE project creation under that node)
resource "google_org_policy_policy" "skip_default_network" {
  count  = var.org_id != "" ? 1 : 0
  name   = "organizations/${var.org_id}/policies/compute.skipDefaultNetworkCreation"
  parent = "organizations/${var.org_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }
}
```

**Verify.** On the bare-trial path you verify by deleting the existing default network and confirming your Week 03 VPC is the only one left:

```bash
gcloud compute networks list --format='table(name,subnet_mode)'
# Expect ONLY your deliberate Week-03 VPC. If "default" is present and unused:
gcloud compute firewall-rules delete default-allow-ssh default-allow-rdp \
  default-allow-icmp default-allow-internal --quiet 2>/dev/null || true
gcloud compute networks delete default --quiet 2>/dev/null || true
```

On the full path, you verify by creating a fresh project under the org node and confirming it has zero networks until you create one.

## 5 — Default #5: Data Access audit logs are off

**The default.** GCP logs *admin* activity (who changed IAM, who created a VM) by default, for free, and you cannot turn it off. But it does **not** log *data access* — who read which row from BigQuery, who downloaded which object from a bucket — unless you explicitly enable Data Access audit logs. When an auditor or an incident asks "who read the customer table on the night of the breach," the honest answer on a default org is "we have no idea." That is the answer that ends careers.

**The control.** Set the audit-log config on the IAM policy at the org (or project) level to capture `DATA_READ` and `DATA_WRITE` for the services that touch sensitive data. Data Access logs cost money (they are voluminous), so you enable them deliberately on the services that matter — BigQuery, Cloud Storage, Spanner, Secret Manager — not blanket on `allServices`.

```hcl
# audit/data-access.tf
resource "google_project_iam_audit_config" "data_access" {
  project = var.project_id
  service = "allServices"   # or scope to bigquery.googleapis.com, etc.

  audit_log_config {
    log_type = "ADMIN_READ"
  }
  audit_log_config {
    log_type = "DATA_READ"
  }
  audit_log_config {
    log_type = "DATA_WRITE"
  }
}
```

**Verify.** Read something, then find the access in the log.

```bash
bq query --use_legacy_sql=false 'SELECT 1 AS probe'
# Wait ~1 minute, then confirm a data_access entry exists:
gcloud logging read \
  'logName:"cloudaudit.googleapis.com%2Fdata_access" AND protoPayload.serviceName="bigquery.googleapis.com"' \
  --limit=1 --format='value(protoPayload.authenticationInfo.principalEmail, protoPayload.methodName)'
# Expect: your-email@example.com  google.cloud.bigquery.v2.JobService.InsertJob
```

If that returns nothing, Data Access logging is not capturing BigQuery — check the audit config actually applied (`gcloud projects get-iam-policy $PROJECT_ID --format=json | jq '.auditConfigs'`).

## 6 — The order of operations (so you do not lock yourself out)

The five controls are not equally dangerous to *you*. External-IP, no-SA-keys, no-public-storage, and audit logs are safe to apply in any order — the worst case is a developer's lazy pattern stops working, which is the point. But the VPC Service Controls perimeter (next section) and Binary Authorization can lock out *your own deploy pipeline*, and a constraint applied at the wrong node can have surprising blast radius. The order that has never bitten me:

1. **Audit logs first.** You want the record of every subsequent change. Free to apply, never breaks anything.
2. **The four "deny the lazy pattern" Org Policy constraints next** (external IP, SA keys, public storage, default network). Each one breaks only a bad habit, and each one is independently verifiable.
3. **CMEK and Secret Manager third** — additive, not restrictive. They do not block anything; they just route encryption and secrets through resources you control.
4. **VPC Service Controls in dry-run mode fourth.** Dry-run *logs* what it *would* block without blocking. You run it for a day, read the would-be-denied list, fix your deploy path, and only then enforce.
5. **Binary Authorization in dry-run mode fifth**, same discipline: log, fix, enforce.

The principle behind the order: **restrictive controls go on last and go on in dry-run first.** You never flip a control from off to hard-enforce on a system with live deploys. You flip it to dry-run, watch the logs for a working day, fix what would have broken, and then enforce. This is the single most important operational habit in this lecture and it is why VPC SC and Binary Auth have explicit dry-run modes.

## 7 — VPC Service Controls without breaking your own deploys

VPC Service Controls is the control engineers fear, and rightly — a misconfigured perimeter can wall off your data project from your own CI/CD identity, your monitoring, and your laptop, all at once. Done right, it is the strongest control in the catalog: it makes a *stolen credential useless from outside the perimeter*. Even if an attacker steals a service-account token, they cannot use it to read your BigQuery datasets from the public internet, because the perimeter denies any request to a protected service that does not originate from inside.

**The model.** A *service perimeter* names (a) a set of projects, (b) a set of *protected services* (e.g. `bigquery.googleapis.com`, `storage.googleapis.com`, `spanner.googleapis.com`), and (c) *ingress* and *egress* rules that punch deliberate holes for the traffic you actually need. A request to a protected service from a project inside the perimeter, to a resource inside the perimeter, is allowed. A request that crosses the boundary is denied unless a rule allows it.

**The failure mode you must avoid.** Your Cloud Build pipeline (Week 06) deploys *into* the data project. If the perimeter does not have an ingress rule for the Cloud Build service account, your next deploy gets a 403 and you are now debugging a self-inflicted outage. The fix is the dry-run rollout.

Here is a perimeter in Terraform, started in dry-run:

```hcl
# vpc-sc/perimeter.tf
# Requires an organization and an Access Context Manager access policy.
resource "google_access_context_manager_access_policy" "policy" {
  parent = "organizations/${var.org_id}"
  title  = "c18-access-policy"
}

# An access level that allows the deploy identity's known networks/identities.
resource "google_access_context_manager_access_level" "deploy" {
  parent = "accessPolicies/${google_access_context_manager_access_policy.policy.name}"
  name   = "accessPolicies/${google_access_context_manager_access_policy.policy.name}/accessLevels/deploy"
  title  = "deploy"

  basic {
    conditions {
      # Identities allowed to reach protected services from outside.
      members = [
        "serviceAccount:${var.cloudbuild_sa}",
        "user:${var.operator_email}",
      ]
    }
  }
}

resource "google_access_context_manager_service_perimeter" "data" {
  parent = "accessPolicies/${google_access_context_manager_access_policy.policy.name}"
  name   = "accessPolicies/${google_access_context_manager_access_policy.policy.name}/servicePerimeters/data"
  title  = "data-perimeter"

  # Start in dry-run: this block defines what WOULD be enforced. It logs
  # violations without blocking. Flip to `status` only after the logs are clean.
  use_explicit_dry_run_spec = true

  spec {
    resources = ["projects/${var.data_project_number}"]
    restricted_services = [
      "bigquery.googleapis.com",
      "storage.googleapis.com",
      "spanner.googleapis.com",
    ]
    access_levels = [google_access_context_manager_access_level.deploy.name]

    # Let the deploy SA reach the protected services from outside the perimeter.
    ingress_policies {
      ingress_from {
        identities = ["serviceAccount:${var.cloudbuild_sa}"]
        sources { access_level = "*" }
      }
      ingress_to {
        resources = ["*"]
        operations {
          service_name = "storage.googleapis.com"
          method_selectors { method = "*" }
        }
      }
    }
  }
}
```

**The rollout discipline.** Apply the dry-run perimeter. Run your deploy. Then read the dry-run violation log:

```bash
gcloud logging read \
  'protoPayload.metadata.@type="type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata"
   AND protoPayload.metadata.dryRun=true' \
  --limit=20 \
  --format='value(protoPayload.authenticationInfo.principalEmail, protoPayload.metadata.violationReason, resource.labels.service)'
```

Every line in that output is a request the *enforced* perimeter would have denied. If your deploy SA, your monitoring agent, or your laptop appears, add an ingress rule for it. Iterate until the dry-run log is empty of legitimate traffic for a full working day. *Then* — and only then — move the `spec` block to a `status` block (drop `use_explicit_dry_run_spec` or set it false and populate `status`) to enforce. That is how you get the strongest control in the catalog without paging yourself.

> **Bare-trial path:** you cannot create an access policy without an org, so you stop at "write the dry-run perimeter spec and the ingress rules." Submit the HCL and a paragraph naming which deploy identities you would have allowed and why. The mini-project grades the *design* on the bare-trial path and the *enforcement* on the full path.

## 8 — CMEK: who holds the key

By default, Google encrypts everything at rest with Google-managed keys. That is real encryption, but *Google* holds the key. **Customer-managed encryption keys (CMEK)** mean the key lives in *your* Cloud KMS key ring, you control its rotation, and — critically — you can *disable* it, which makes the data unreadable even by Google. CMEK is the control your auditor means when they say "do you control your encryption keys."

The mechanics that trip people up: each Google service that encrypts with your key uses a per-service *service agent* identity, and that agent needs `roles/cloudkms.cryptoKeyEncrypterDecrypter` on your key, or the service silently fails to write. Forgetting the grant is the #1 CMEK mistake.

```hcl
# kms/cmek.tf
resource "google_kms_key_ring" "ring" {
  name     = "c18-prod"
  location = var.region
  project  = var.project_id
}

resource "google_kms_crypto_key" "data" {
  name            = "data"
  key_ring        = google_kms_key_ring.ring.id
  rotation_period = "7776000s" # 90 days — rotate on a schedule, always

  lifecycle {
    prevent_destroy = true # never let a `terraform destroy` orphan encrypted data
  }
}

# The BigQuery service agent must be able to use the key, or table writes fail.
data "google_project" "p" { project_id = var.project_id }

resource "google_kms_crypto_key_iam_member" "bq_agent" {
  crypto_key_id = google_kms_crypto_key.data.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:bq-${data.google_project.p.number}@bigquery-encryption.iam.gserviceaccount.com"
}

# A CMEK-encrypted BigQuery dataset.
resource "google_bigquery_dataset" "events" {
  dataset_id = "events_cmek"
  location   = var.region
  project    = var.project_id

  default_encryption_configuration {
    kms_key_name = google_kms_crypto_key.data.id
  }

  depends_on = [google_kms_crypto_key_iam_member.bq_agent]
}
```

Spanner CMEK is the same shape — a `kms_key_name` on the database, and the Spanner service agent granted on the key. The constraint `constraints/gcp.restrictNonCmekServices` (in the Org Policy bundle) makes CMEK *mandatory* for the services you list, so a future engineer cannot create a Google-key-managed BigQuery dataset by accident.

**Verify.** Confirm the dataset reports your key, and confirm a non-CMEK dataset is rejected when the constraint is on:

```bash
bq show --format=prettyjson "${PROJECT_ID}:events_cmek" | grep -A2 kmsKeyName
# Should print your crypto key resource name.

# With constraints/gcp.restrictNonCmekServices enforcing bigquery, this fails:
bq mk --dataset "${PROJECT_ID}:no_cmek_should_fail"
# ERROR: ... organization policy constraint gcp.restrictNonCmekServices ...
```

## 9 — Secret Manager: no credential anywhere but here

The rule is absolute: **no secret in code, no secret in an environment variable baked into an image, no secret in Terraform state, no secret in a `.env` committed by accident.** Every credential — a database password, an API token, a TLS private key — lives in Secret Manager, is read at runtime by a workload identity that has `roles/secretmanager.secretAccessor` on exactly that secret, and is rotated on a schedule.

```hcl
# secrets/db-password.tf
resource "google_secret_manager_secret" "db_password" {
  secret_id = "prod-db-password"
  project   = var.project_id

  replication {
    user_managed {
      replicas { location = var.region }
    }
  }
}

# Grant ONE workload SA read access to THIS secret — not project-wide.
resource "google_secret_manager_secret_iam_member" "app_reader" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.app_workload_sa}"
}
```

The `latest` alias is a trap in one specific way: a workload that reads `latest` picks up a new version the instant you add one, which is great for rotation but means a *bad* rotation breaks every reader at once. Pin to a numbered version for anything where a coordinated rollout matters, and read `latest` only where you have tested that adding a version is safe. The Python a workload uses to read a secret (no keyfile — it authenticates as its workload identity) is in Exercise 2; the shape is:

```python
from google.cloud import secretmanager

def read_secret(project_id: str, secret_id: str, version: str = "latest") -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")
```

## 10 — Binary Authorization: only images your pipeline signed

The deploy-path control. Binary Authorization is a GKE admission controller that **refuses to run a container image unless it carries a valid attestation** — a signature proving the image went through your build pipeline. An attacker who gets `kubectl` access still cannot run their own image, because their image was never signed by your Cloud Build attestor.

The pieces: an **attestor** (an identity that vouches for images, backed by a Cloud KMS signing key or a PKIX key), an **attestation** (a signed statement "image digest X passed"), the **Cloud Build step** that creates the attestation after a successful build, and the **policy** on the cluster that says "require an attestation from this attestor before admitting any pod." Exercise 2 wires the whole chain; here is the policy shape:

```hcl
# binauthz/policy.tf
resource "google_binary_authorization_policy" "policy" {
  project = var.project_id

  # Default: deny everything that is not explicitly attested.
  default_admission_rule {
    evaluation_mode  = "REQUIRE_ATTESTATION"
    enforcement_mode = "ENFORCED_BLOCK_AND_AUDIT_LOG"
    require_attestations_by = [
      google_binary_authorization_attestor.build.name,
    ]
  }

  # Allow Google's own system images (kube-system, etc.) without attestation.
  admission_whitelist_patterns { name_pattern = "gcr.io/google-containers/*" }
  admission_whitelist_patterns { name_pattern = "k8s.gcr.io/*" }
  admission_whitelist_patterns { name_pattern = "registry.k8s.io/*" }
}
```

**The dry-run discipline applies here too.** Set `enforcement_mode = "DRYRUN_AUDIT_LOG_ONLY"` first, deploy your real workloads, read the audit log for would-be-denied admissions, confirm every legitimate image is attested, and *then* flip to `ENFORCED_BLOCK_AND_AUDIT_LOG`. Flip a fresh Binary Auth policy straight to enforce on a running cluster and your next rollout — including a legitimate one whose attestation step you forgot to wire — fails admission and you have an outage.

**Verify the deny.**

```bash
# A signed image from your pipeline deploys fine.
kubectl run signed --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/app/api@${SIGNED_DIGEST}"

# An arbitrary unsigned image MUST be denied:
kubectl run unsigned --image="nginx:latest"
# Error from server (Forbidden): admission webhook "imagepolicywebhook.image-policy.k8s.io"
#   denied the request: Image nginx:latest denied by Binary Authorization ...
#   No attestations found that were valid and signed by a key trusted by the attestor.
```

The break-glass escape hatch exists for the 3 a.m. incident where you must deploy an un-attested fix *right now*: annotate the pod with `alpha.image-policy.k8s.io/break-glass: "true"`. It bypasses the policy and writes a loud audit log entry, which is exactly right — break-glass should be possible and impossible to do quietly.

## 11 — Security Command Center, in one breath

You have closed the five defaults. Security Command Center (SCC) finds the long tail. SCC Standard is free and runs Security Health Analytics — it flags public buckets, over-broad IAM, missing audit logs, the works. SCC Premium/Enterprise adds Event Threat Detection (anomalous IAM grants, crypto-mining patterns) and Container Threat Detection (a reverse shell in a pod). The move is not "read the SCC console daily" — nobody does that — it is **route findings to Pub/Sub, filter to high severity, and ticket or page them**, so SCC becomes part of your alerting pipeline rather than another dashboard nobody opens. The stretch goal wires that route. The point for this lecture: SCC is how you catch the *sixth* default you forgot, and it pays for itself the first time it catches a public bucket before an auditor does.

## 12 — Putting it together: the day-one hardening, as a sequence

Here is the whole lecture as the sequence you run on day one of any new GCP org, which is exactly what Exercise 1 and the mini-project codify:

1. **Enable Data Access audit logs** (free record of everything that follows).
2. **Apply the four "deny the lazy pattern" Org Policy constraints** — external IP, SA keys, public storage, default network — and **verify each deny**.
3. **Stand up KMS, apply CMEK** to BigQuery + Spanner, and enforce `gcp.restrictNonCmekServices`; move every credential into **Secret Manager**.
4. **Apply the VPC SC perimeter in dry-run**, read the would-deny log, add ingress for your deploy identity, and enforce only when the dry-run log is clean.
5. **Apply Binary Authorization in dry-run**, confirm your signed images pass and unsigned images would be denied, and enforce.
6. **Turn on Security Command Center** and route high-severity findings to a pager.

Every step ends in a verification — an attempted violation that must fail. That is the difference between a hardened org and a wishful one.

## 13 — What to take into Lecture 2

Lecture 2 turns from "stop the bad thing" to "stop wasting money" and then to "survive the night." Carry three things forward:

1. **Change the dangerous default, enforce it at the org, verify the deny.** The control you have not seen reject something is a comment, not a control.
2. **Restrictive controls go on last and go on in dry-run first.** VPC SC and Binary Auth lock out your own deploys if you skip the dry-run. The dry-run-then-enforce loop is the operational habit that makes hardening safe.
3. **Who holds the key, and where do the bytes sit.** CMEK, Secret Manager, and the VPC SC perimeter are three answers to the same auditor question — *who can read this data, and from where* — and you should be able to answer it for every dataset in your system.

Now go run Exercise 1: apply the Org Policy bundle and verify all three denies before you read Lecture 2.

---

**References**

- Organization Policy Service overview: <https://cloud.google.com/resource-manager/docs/organization-policy/overview>
- Using constraints (catalog): <https://cloud.google.com/resource-manager/docs/organization-policy/org-policy-constraints>
- VPC Service Controls overview: <https://cloud.google.com/vpc-service-controls/docs/overview>
- Service perimeter configuration: <https://cloud.google.com/vpc-service-controls/docs/service-perimeters>
- Cloud KMS CMEK: <https://cloud.google.com/kms/docs/cmek>
- Secret Manager overview: <https://cloud.google.com/secret-manager/docs/overview>
- Binary Authorization overview: <https://cloud.google.com/binary-authorization/docs/overview>
- Binary Authorization with Cloud Build: <https://cloud.google.com/binary-authorization/docs/creating-attestations-cloud-build>
- Security Command Center overview: <https://cloud.google.com/security-command-center/docs/security-command-center-overview>
- Building Secure and Reliable Systems: <https://google.github.io/building-secure-and-reliable-systems/>
