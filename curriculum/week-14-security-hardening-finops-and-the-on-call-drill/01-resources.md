# Week 14 — Resources

Curated, current to 2026. Read the **must-read** items before you touch the lab; they are the primary sources this week's lectures lean on. The rest are reference you reach for during the exercises and the mini-project. Every link is to a primary source — Google Cloud docs, the Terraform provider, a standards body, or a book whose author actually ran the system.

A working rule for this week: when a doc and a blog post disagree, the doc wins, and the pricing page wins over everything. Pricing and quota numbers in the lectures are illustrative and dated; **confirm every dollar figure against the live pricing page before you put it in a memo.**

---

## Organization Policy

- **must-read** — *Organization Policy Service — overview.* <https://cloud.google.com/resource-manager/docs/organization-policy/overview> — Boolean vs. list constraints, inheritance, the policy hierarchy. The mental model for everything in Lecture 1.
- **must-read** — *Using constraints (the built-in catalog).* <https://cloud.google.com/resource-manager/docs/organization-policy/org-policy-constraints> — The full list of constraints. You will use `compute.vmExternalIpAccess`, `iam.disableServiceAccountKeyCreation`, `storage.publicAccessPrevention`, `gcp.resourceLocations`, and `gcp.restrictNonCmekServices` this week. Bookmark this page.
- *Dry-run policies.* <https://cloud.google.com/resource-manager/docs/organization-policy/dry-run-policy> — Test a constraint in audit mode before you enforce it. The discipline that keeps you from locking out production.
- *Custom organization policy constraints.* <https://cloud.google.com/resource-manager/docs/organization-policy/creating-managing-custom-constraints> — CEL conditions over resources, for the stretch goal.
- *Terraform `google_org_policy_policy` resource.* <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/org_policy_policy> — The modern resource (replaces the deprecated `google_organization_policy`). Supports `rules`, `dry_run_spec`, and condition expressions.

## VPC Service Controls

- **must-read** — *VPC Service Controls overview.* <https://cloud.google.com/vpc-service-controls/docs/overview> — Perimeters, the protected-services model, the threat it actually defends against (data exfiltration via stolen credentials), and the threat it does not.
- **must-read** — *Service perimeter details and configuration.* <https://cloud.google.com/vpc-service-controls/docs/service-perimeters> — Ingress/egress rules, access levels, and the dry-run-then-enforce rollout. The single most important doc for not locking yourself out.
- *Access Context Manager — access levels.* <https://cloud.google.com/access-context-manager/docs/overview> — The access-policy and access-level resources a perimeter references.
- *Troubleshooting VPC Service Controls.* <https://cloud.google.com/vpc-service-controls/docs/troubleshooting> — Reading the `vpcServiceControlsUniqueIdentifier` in a denied request's logs. You will need this when your own deploy gets a 403.
- *Terraform `google_access_context_manager_service_perimeter`.* <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_service_perimeter> — Note the `use_explicit_dry_run_spec` field; that is your safety valve.

## Cloud KMS and CMEK

- **must-read** — *Cloud KMS — customer-managed encryption keys (CMEK).* <https://cloud.google.com/kms/docs/cmek> — What CMEK is, what it protects, the service-agent IAM grant every CMEK-using service needs (`roles/cloudkms.cryptoKeyEncrypterDecrypter`).
- *Key rotation.* <https://cloud.google.com/kms/docs/key-rotation> — Automatic rotation schedules and why the default 90-day rotation is the right starting point.
- *CMEK on BigQuery.* <https://cloud.google.com/bigquery/docs/customer-managed-encryption> — Dataset-default keys and per-table keys.
- *CMEK on Spanner.* <https://cloud.google.com/spanner/docs/cmek> — Instance/database CMEK and the constraint that the key must be in a compatible location.
- *Terraform `google_kms_crypto_key`.* <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/kms_crypto_key> — `rotation_period`, `purpose`, and the `lifecycle { prevent_destroy = true }` you should always set on a key that has encrypted data.

## Secret Manager

- **must-read** — *Secret Manager overview.* <https://cloud.google.com/secret-manager/docs/overview> — Secrets, versions, replication, and the access model. Read this before you ever put a credential anywhere else.
- *Secret rotation.* <https://cloud.google.com/secret-manager/docs/rotation> — The rotation topic + Cloud Function pattern.
- *Access a secret from Cloud Run / GKE.* <https://cloud.google.com/run/docs/configuring/services/secrets> and <https://cloud.google.com/secret-manager/docs/access-secret-version> — How a workload reads a secret via Workload Identity, no keyfile.
- *Python client — `google-cloud-secret-manager`.* <https://cloud.google.com/python/docs/reference/secretmanager/latest> — The `SecretManagerServiceClient` used in Exercise 2.

## Binary Authorization

- **must-read** — *Binary Authorization overview.* <https://cloud.google.com/binary-authorization/docs/overview> — The policy, attestors, attestations, and the admission-controller enforcement point on GKE.
- **must-read** — *Set up Binary Authorization with Cloud Build.* <https://cloud.google.com/binary-authorization/docs/creating-attestations-cloud-build> — The exact path Exercise 2 takes: Cloud Build builds the image and signs an attestation; the attestor verifies it at deploy time.
- *Configuring policy.* <https://cloud.google.com/binary-authorization/docs/configuring-policy-cli> — `evaluationMode`, allowlist patterns, the default-rule, and the break-glass annotation `alpha.image-policy.k8s.io/break-glass`.
- *Dry-run mode.* <https://cloud.google.com/binary-authorization/docs/using-dry-run> — Audit before you block; the same discipline as Org Policy dry-run.
- *Terraform `google_binary_authorization_policy` and `google_binary_authorization_attestor`.* <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/binary_authorization_policy>

## Security Command Center

- *Security Command Center overview and tiers.* <https://cloud.google.com/security-command-center/docs/security-command-center-overview> — Standard (free) vs. Premium/Enterprise. The detector families: Security Health Analytics, Event Threat Detection, Container Threat Detection.
- *Notifications to Pub/Sub.* <https://cloud.google.com/security-command-center/docs/how-to-notifications> — Routing findings so they page or ticket instead of rotting in a console.
- *Security posture.* <https://cloud.google.com/security-command-center/docs/security-posture-overview> — Declarative posture-as-code, the natural next step after Org Policy.

## FinOps, billing, and discounts

- **must-read** — *Export Cloud Billing data to BigQuery.* <https://cloud.google.com/billing/docs/how-to/export-data-bigquery> — The one-time setup and the **up-to-24-hour** population delay. Enable Monday.
- **must-read** — *Billing export schema.* <https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage> — The `service`, `sku`, `cost`, `usage`, `credits`, `labels` columns. Exercise 3 queries exactly these.
- **must-read** — *Committed use discounts.* <https://cloud.google.com/docs/cuds> — Resource-based vs. spend-based (flexible) CUDs, the 1- and 3-year terms, and the commitment math.
- *Sustained use discounts.* <https://cloud.google.com/compute/docs/sustained-use-discounts> — Automatic, no commitment, Compute-Engine only. Why you rarely "do" anything to earn them.
- *Spot VMs.* <https://cloud.google.com/compute/docs/instances/spot> — Pricing, preemption, and the 60–91% discount. The third FinOps move.
- *Pricing — the live pages.* <https://cloud.google.com/compute/all-pricing>, <https://cloud.google.com/bigquery/pricing>, <https://cloud.google.com/spanner/pricing> — Confirm every dollar figure here. The lecture numbers are illustrative and dated.

## SRE, on-call, and postmortems

- **must-read** — *Google SRE Book — Postmortem Culture: Learning from Failure.* <https://sre.google/sre-book/postmortem-culture/> — The no-blame postmortem, the difference between contributing factors and root cause, and why blameless is an engineering choice, not a kindness.
- **must-read** — *Google SRE Book — Being On-Call.* <https://sre.google/sre-book/being-on-call/> — Page load, the operational/project-work balance, and the psychology of the pager.
- *Google SRE Workbook — Incident Response & On-Call.* <https://sre.google/workbook/incident-response/> — The practical version: IC, comms, and the handoff.
- *Postmortem template.* <https://sre.google/sre-book/example-postmortem/> — A fully worked example; the cohort template is modeled on this.
- *PagerDuty — Incident Response docs.* <https://response.pagerduty.com/> — Vendor-neutral, practical on-call process. Skim the "during an incident" and "after an incident" sections.

## Books

- *Site Reliability Engineering* (Beyer, Jones, Petoff, Murphy — O'Reilly, free online at <https://sre.google/books/>). Chapters 11–15 are the on-call and postmortem canon this week is built on.
- *Cloud FinOps, 2nd ed.* (Storment & Fuller, O'Reilly, 2023). The discipline of FinOps as an organizational practice. Read the "Inform → Optimize → Operate" loop; we do the Optimize part with code.
- *Building Secure and Reliable Systems* (Adkins et al., O'Reilly, free at <https://google.github.io/building-secure-and-reliable-systems/>). The security-meets-reliability book; the "least privilege" and "defense in depth" chapters back Lecture 1.

## Talks

- *"How NOT to Measure Latency"* — Gil Tene. <https://www.youtube.com/watch?v=lJ8ydIuPFeU> — Carried forward from Week 12/13: the drill's latency claims must survive this talk's standards.
- *USENIX SREcon — postmortem and blameless-culture track.* <https://www.usenix.org/conferences/byname/925> — Browse recent SREcon programs; there is always at least one excellent postmortem-culture talk per year.

## A note on dollar figures and constraint names

GCP renames constraints and changes prices. The constraint IDs in this week (`compute.vmExternalIpAccess`, etc.) are stable as of 2026, but **always confirm against the live "Using constraints" catalog** before you ship a policy, and confirm every price against the live pricing page before you put it in a memo a finance partner will read. A FinOps memo with a stale number is worse than no memo — it destroys your credibility the moment someone checks it.
