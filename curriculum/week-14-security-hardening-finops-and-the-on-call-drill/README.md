# Week 14 — Security Hardening, FinOps, and the On-Call Drill

Welcome to **C18 · Crunch GCP**, Week 14 — the week you lock the doors, count the money, and prove you can survive a bad night. Phase 4 began with Week 13, where you instrumented every service from Weeks 06–12 with OpenTelemetry and armed burn-rate alerts that page on user-visible risk. Now you take that observable system and make it *defensible*: hardened against the configuration mistakes that own production GCP orgs, cost-engineered so the bill stops surprising you, and operable by a human at 3 a.m. who has never seen this system before and is following your runbook.

This is the most "senior" week of the course, and it is the least about new APIs. You already know how to provision things. This week is about the constraints you put *around* the things — the Organization Policy that makes a public IP impossible to create, the VPC Service Controls perimeter that makes data exfiltration from your warehouse a 403 instead of a breach, the Binary Authorization policy that refuses to run an unsigned image, and the on-call drill that turns "we have a runbook somewhere" into "I followed the runbook and the page resolved in eleven minutes." Hardening is not a feature you ship; it is a posture you hold. FinOps is not a one-time cleanup; it is a discipline you run monthly. On-call is not heroics; it is a process that lets a tired person do the right thing.

The first thing to internalize is that **security and cost are the same problem viewed from two angles, and both are governed by defaults you did not choose.** A fresh GCP organization ships with defaults optimized for "get started fast," not "run a regulated production system." Those defaults — external IPs allowed everywhere, service-account key creation permitted, public Cloud Storage allowed, default network present, audit logs for data access turned off — are precisely the five things that own you if you leave them. Likewise, the billing defaults — on-demand pricing, no commitments, on-demand BigQuery, no spot capacity — are optimized for Google's revenue, not your budget. The senior move in both cases is the same: **change the dangerous defaults on day one, before anyone builds on top of them, and enforce the change at the organization level so a junior engineer cannot undo it by accident.** Lecture 1 names the five security defaults; Lecture 2 names the three FinOps moves. Both are written as "do this before Friday," because by Friday you are on call.

The second thing to internalize is that **a control you cannot verify is not a control.** It is a comment. Anyone can apply an Organization Policy constraint; the engineer who gets paid is the one who then *tries to create the forbidden thing and confirms the 403*, who deploys their own pipeline *through* the VPC SC perimeter to prove they did not lock themselves out, and who pushes an unsigned image to confirm Binary Authorization blocks it. Every exercise this week ends in a verification step — an attempted violation that must fail — because in security and in FinOps, the gap between "I configured it" and "I confirmed it works" is where every incident lives.

The week ends with a graded **synthetic on-call drill** and a no-blame **postmortem**. This is worth 5% of your course grade on its own (see the assessment matrix in the syllabus), and it is graded entirely on the *quality of the postmortem* — not on how fast you mitigated, not on whether you were calm. A good postmortem with a slow mitigation beats a fast mitigation with a blamey, shallow writeup every time. You will receive a synthetic page, triage it with the Cloud Logging and Cloud Trace skills from Week 13, mitigate it, sign off a runbook, and write the postmortem the cohort uses as its template.

## Learning objectives

By the end of this week, you will be able to:

- **Identify and change** the five GCP security defaults that own production orgs — external IP, SA key creation, public storage, the default network, and Data Access audit logs — and enforce each at the organization or folder level with Organization Policy constraints.
- **Apply** an Organization Policy bundle in Terraform that restricts public IPs, enforces CMEK, and restricts resource locations, then **verify enforcement** by attempting each forbidden action and confirming it is denied.
- **Wrap** a production data project in a VPC Service Controls perimeter without breaking your own deploys — including the access level, the ingress/egress rules, and the dry-run-then-enforce rollout that keeps you from locking yourself out.
- **Configure** Binary Authorization on the GKE deploy path with an attestor whose attestations are signed by Cloud Build, so that only images built and signed by your pipeline can run.
- **Encrypt** BigQuery and Spanner with customer-managed encryption keys (CMEK) backed by Cloud KMS, and **store** every credential in Secret Manager with rotation and IAM-scoped access — no secrets in environment variables, in Terraform state, or in code.
- **Read** a billing export in BigQuery, find the top three line items by cost, and **propose** committed-use-discount and spot-capacity moves with a dollar-denominated payback estimate.
- **Reason** about sustained-use discounts, committed-use discounts (resource-based and spend-based), and spot capacity, and choose the right discount instrument for a given workload shape.
- **Run** a synthetic on-call shift end-to-end — receive the page, triage, mitigate, sign off the runbook — and **write** a no-blame postmortem with a timeline, contributing factors, and dated action items that a staff engineer would sign.

## Prerequisites

- **Weeks 01–13 of C18 complete.** This week hardens and cost-engineers the system you have been building since Week 06. Specifically you must be able to write an Organization Policy or IAM resource in Terraform (Week 02, 04), operate the GKE cluster and its deploy path (Week 06), query a partitioned BigQuery table (Week 10), run the Spanner instance (Week 11), and read a Cloud Logging/Cloud Trace investigation (Week 13). The drill assumes the Week 13 burn-rate alerts exist.
- **Organization-level access, or a sandbox org.** Organization Policy and VPC Service Controls are *organization* and *access-policy* scoped resources. If your free-trial account is a standalone project with no organization, several controls can only be applied at the project level (Org Policy supports project-level overrides) and VPC SC requires an organization with an Access Context Manager policy. The lecture walks you through both paths: the full org path if you have a Cloud Identity / Workspace org, and the project-scoped subset if you are on a bare trial project. Read §0 of Lecture 1 before Monday to know which path you are on.
- **The Week 06 GKE cluster and its Cloud Build deploy pipeline are reachable.** Binary Authorization and the drill both run against them. The Week 06 Terraform is idempotent — `terraform apply` brings the cluster back if you tore it down. Budget 15 minutes Sunday night.
- **A billing export to BigQuery already streaming, or one you can enable Monday.** The FinOps exercise queries it. Standard usage cost export takes up to 24 hours to populate after you enable it, so **enable it Monday morning at the latest** or you will have no data Wednesday. §2.1 of Lecture 2 shows the one-time setup.
- **Python 3.12+, `terraform` (or `tofu`) ≥ 1.7, `gcloud`, `bq`, and `kubectl`** on your path, plus the `google-cloud-secret-manager` and `google-cloud-kms` SDKs in a virtualenv. A pinned `requirements.txt` ships in the exercises.
- **A credit card on the billing account.** The hardening controls are free. The drill's *failover* step (killing the primary region's workload and watching the standby take over) is the paid-but-cheap opt-in — it spins a standby Cloud Run service to `min-instances=1` for the duration of the drill. Budget **\$3–6** for the week and tear down the same day. The teardown gate is graded.

## Topics covered

- **The five security defaults you must change.** External IP allowed, service-account key creation allowed, public Cloud Storage allowed, the default VPC network, and Data Access audit logs off. Why each is a footgun and the Organization Policy constraint that closes it.
- **Organization Policy constraints.** Boolean vs. list constraints; the policy hierarchy and inheritance; `enforce`, `allow`/`deny` values, `inheritFromParent`, and the dry-run (`liveState` vs `dryRunSpec`) rollout. The constraints that matter: `compute.vmExternalIpAccess`, `compute.skipDefaultNetworkCreation`, `iam.disableServiceAccountKeyCreation`, `storage.publicAccessPrevention`, `gcp.resourceLocations`, `gcp.restrictNonCmekServices`.
- **Custom Organization Policy constraints.** When the built-in catalog is not enough, the `custom.*` constraint with a CEL condition over the resource. One worked example.
- **VPC Service Controls.** Service perimeters, the protected services list, access levels (Access Context Manager), ingress and egress policies, the dry-run perimeter, and the failure mode you must avoid: locking your own deploy identity out of the project.
- **Cloud KMS and CMEK.** Key rings, keys, key versions, rotation schedules, the per-service service agent that needs `cryptoKeyEncrypterDecrypter`, and applying CMEK to BigQuery datasets and Spanner instances/databases. The difference between Google-managed, customer-managed (CMEK), and customer-supplied (CSEK) keys.
- **Secret Manager.** Secrets, versions, the `latest` alias trap, IAM-scoped access, rotation, regional vs. automatic replication, and reading a secret from a Cloud Run service and a GKE pod via Workload Identity — never from a keyfile or an env var baked into an image.
- **Binary Authorization.** The policy, attestors, attestations, the Cloud KMS-backed or PKIX signature, the Cloud Build attestor on the build path, `evaluationMode`, allowlist patterns, the break-glass annotation, and the dry-run mode that logs instead of blocking.
- **Security Command Center Premium.** The finding model, the built-in detectors (Security Health Analytics, Event Threat Detection, Container Threat Detection), posture management, and how to route a finding to a ticket without drowning in noise. Why Premium (or Enterprise) is the tier that pays for itself the first time it catches a public bucket.
- **FinOps: the discount instruments.** Sustained-use discounts (automatic, on Compute), committed-use discounts (resource-based vs. spend-based / flexible), the commitment term and the breakeven utilization, and spot/preemptible capacity. Which instrument fits which workload shape.
- **Billing export to BigQuery.** Standard vs. detailed usage cost export; the export schema (`service`, `sku`, `cost`, `usage`, `credits`, `labels`); writing the queries that find the top line items and quantify a committed-use saving.
- **On-call rotation design and the drill.** The page → triage → mitigate → postmortem loop; the runbook contract; the no-blame postmortem template; contributing factors vs. root cause; action items with owners and dates.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract. The hardening work is free and can be spread out; the drill's failover step costs real money while it runs — do it in a focused block and tear down the same day.

| Day       | Focus                                                          | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | The five security defaults; Org Policy; enable billing export   |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Org Policy bundle + verification; VPC SC perimeter (Ex 01)      |    1.5h  |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Wednesday | KMS/CMEK, Secret Manager, Binary Authorization (Ex 02)          |    1.5h  |    2h     |     0h     |    0.5h   |   1h     |     0.5h     |    0h      |     6h      |
| Thursday  | FinOps: the three moves; billing export analysis (Ex 03)        |    1h    |    2h     |     0.5h   |    0.5h   |   1h     |     1h       |    0h      |     6h      |
| Friday    | The on-call drill + postmortem; mini-project build (Challenge)  |    0h    |    0h     |     2.5h   |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Saturday  | Mini-project deep work; perimeter hardening; teardown gate      |    0h    |    0h     |     0h     |    0h     |   0h     |     3.5h     |    0h      |     3.5h    |
| Sunday    | Quiz, review, postmortem polish, runbook sign-off               |    0h    |    0h     |     0h     |    1h     |   0h     |     1.5h     |    0h      |     2.5h    |
| **Total** |                                                                | **7h**   | **7.5h**  | **3h**     | **4h**    | **5h**   | **9h**       | **1.5h**   | **37h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The GCP security, Org Policy, VPC SC, KMS, Binary Authorization, billing-export, and SRE-postmortem docs you must read to do this week honestly |
| [lecture-notes/01-the-five-security-defaults.md](./lecture-notes/01-the-five-security-defaults.md) | The five GCP defaults that own new orgs, the Org Policy / VPC SC / Binary Auth / KMS / Secret Manager controls that close them, and how to verify each |
| [lecture-notes/02-three-finops-moves-and-the-drill.md](./lecture-notes/02-three-finops-moves-and-the-drill.md) | The three FinOps moves that pay back inside a quarter — billing-export analysis, committed-use, spot — plus on-call rotation design and the no-blame postmortem |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-org-policy-bundle-and-verify.md](./exercises/exercise-01-org-policy-bundle-and-verify.md) | Apply an Org Policy bundle (restrict public IPs, enforce CMEK, restrict locations) and verify enforcement by attempting each violation |
| [exercises/exercise-02-binary-authorization-cloud-build-attestor.py](./exercises/exercise-02-binary-authorization-cloud-build-attestor.py) | Configure Binary Authorization with a Cloud Build-signed attestor on the GKE deploy path and prove an unsigned image is blocked |
| [exercises/exercise-03-billing-export-finops.sql](./exercises/exercise-03-billing-export-finops.sql) | Analyze a billing export in BigQuery to find the top three line items and quantify a committed-use saving |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-harden-perimeter-and-run-the-drill.md](./challenges/challenge-01-harden-perimeter-and-run-the-drill.md) | Org Policy bundle + VPC SC perimeter without breaking deploys + Binary Auth on GKE + a synthetic on-call drill with a signed runbook and a no-blame postmortem |
| [quiz.md](./quiz.md) | 13 questions with an answer key |
| [homework.md](./homework.md) | Six problems with a rubric |
| [mini-project/README.md](./mini-project/README.md) | The hardened production posture over the whole Week-01–13 system, plus the graded on-call drill postmortem, with a teardown gate |

## The "verify the deny" promise

Every week in this course has a discipline marker. Week 07 had "0 warnings." Week 12 had the GPU teardown gate. Week 14's marker is **verify the deny**: a control you have not seen reject something is a control you do not have. The recurring proof:

```
$ gcloud compute instances create probe --zone=$ZONE \
    --network-interface=subnet=$SUBNET,no-address  # internal-only OK
$ gcloud compute instances create probe-public --zone=$ZONE  # should FAIL
ERROR: ... Constraint constraints/compute.vmExternalIpAccess violated ...

$ gcloud container images add-tag $UNSIGNED_IMAGE ...  # push unsigned image
$ kubectl run probe --image=$UNSIGNED_IMAGE  # should FAIL admission
Error ... denied by Binary Authorization ... no attestation ...
```

If the forbidden action *succeeds*, your control is not in place — no matter what the Terraform plan said. We treat a control that has never denied anything the way Week 07 treated a build warning: it is a defect, and you fix it before you move on. Every exercise and the mini-project codify "verify the deny" into an explicit step you run and capture.

## A note on what's *not* here

Week 14 is a posture week. It deliberately does **not** cover:

- **A full SOC-2 / FedRAMP / ISO-27001 control mapping.** Compliance frameworks are a real discipline and a different course. We implement the *technical* controls those frameworks ask for; we do not write the audit narrative.
- **Penetration testing or red-teaming.** We harden against the common misconfigurations that own GCP orgs. Adversarial security testing is a separate competency.
- **Cost allocation / chargeback / showback org design.** We do the engineering side of FinOps — find the spend, apply the discount, prove the saving. The finance-org side (chargeback models, unit economics, budgeting cadence) is mentioned, not built.
- **The full Security Command Center detector catalog.** We turn it on, route findings to a sink, and act on one. The complete detector taxonomy and tuning guide is reference reading, not lab work.
- **Incident command (IC) at scale.** Our drill is a single-engineer shift. Multi-responder incident command, comms leads, and status-page automation belong to a larger on-call program; we point at the literature.

The point of Week 14 is narrow and load-bearing: change the dangerous defaults, prove the controls deny what they should, find the money, and survive the night with a postmortem a staff engineer would sign.

## Stretch goals

If you finish the regular work early and want to push further:

- Write a **custom Organization Policy constraint** (`custom.*`) with a CEL condition — for example, "deny any GKE cluster without `binaryAuthorization.evaluationMode = PROJECT_SINGLETON_POLICY_ENFORCE`." Apply it and verify it denies a non-compliant cluster.
- Turn on **Security Command Center** (Standard is free; Premium/Enterprise is a trial) and route findings to a Pub/Sub topic, then write a Cloud Run function that posts high-severity findings to Slack. Trigger one by creating a public bucket and watch the finding land.
- Add a **VPC SC egress rule** that allows your data project to reach exactly one external Google API and nothing else, then prove a different API call is denied from inside the perimeter.
- Compute the **committed-use breakeven** for your Week 11 Spanner instance: at what monthly utilization does a 1-year resource-based commitment beat on-demand? Write it as a one-paragraph memo with the number.
- Run the drill a **second time** with a different injected fault (certificate-near-expiry, or a Pub/Sub backlog from Week 09) and compare your two postmortems. Note which contributing factors repeat — repeated factors are systemic.

## Up next

Continue to **Week 15 — Capstone Delivery and Architecture Review** once your mini-project is hardened, cost-reported, drilled, and *torn down*. Week 15 is delivery week: you present and defend the entire system — the VPC SC perimeter you wrapped this week, the Org Policy bundle, the Binary Authorization deploy path, the CMEK on BigQuery and Spanner, the billing-export cost report, and the postmortem from this week's drill all become slides in your architecture review and sections of your production runbook. The instinct you build this week — *change the dangerous default, enforce it at the org, verify the deny, and write the postmortem* — is exactly the instinct a staff engineer interviewing you will probe for. Bring the signed runbook. You earned it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
