# Mini-Project — The Hardened Production Posture

> Lock down everything you built through Week 13: an Organization Policy bundle, a VPC Service Controls perimeter around the data project, Binary Authorization on the GKE deploy path, Secret Manager for every credential, and CMEK on BigQuery + Spanner — then run the graded on-call drill and deliver the postmortem. Tear it down on demand. This is the security-and-operations capstone of the course, and it compounds: it does not stand up new infrastructure, it *wraps* the system you have spent thirteen weeks building.

This mini-project is worth 25% of the weekly grade (the mini-project weight) and the embedded on-call drill is worth a further 5% of the *course* grade (the drill, graded on the postmortem). It is the single most important week's artifact after the capstone itself, because it is the difference between "I built a system" and "I built a system I can defend in front of an auditor and operate at 3 a.m."

---

## What you are building

You are not building new services. By Week 14 the system already exists:

- **Week 06** — a GKE cluster (Autopilot + Standard) with a Cloud Build deploy path.
- **Week 07** — a Cloud Run ingest service backed by Cloud SQL over Private Service Connect.
- **Week 08** — a global HTTPS load balancer with Cloud Armor.
- **Week 09–10** — a Pub/Sub → Dataflow → BigQuery pipeline landing partitioned, clustered tables.
- **Week 11** — a Spanner instance as the transactional store.
- **Week 12** — a Vertex AI / Gemini serving tier with a circuit-breaker fallback.
- **Week 13** — OpenTelemetry on every service, SLOs, and burn-rate alerts.

This week you put a *posture* around all of it. The deliverable is a `week-14-hardening/` Terraform root module plus the operational artifacts (runbook, postmortem, FinOps memo, teardown receipt) that turn the running system into a defensible one.

If you tore down earlier weeks, the Terraform is idempotent: `terraform apply` on Week 06 brings the cluster back, Week 10's loader re-populates BigQuery, Week 11 re-creates the Spanner instance. Budget 30 minutes Sunday night to bring the system back to a known-good state before you start hardening it.

---

## Required deliverables

### 1. The Organization Policy bundle (enforced + verified)

A Terraform module applying, at the org/folder if you have one or the project if you do not:

- `compute.vmExternalIpAccess` — deny all external IPs.
- `iam.disableServiceAccountKeyCreation` — no long-lived SA keys.
- `storage.publicAccessPrevention` — no public buckets.
- `gcp.restrictNonCmekServices` — CMEK mandatory on BigQuery and Spanner.
- `gcp.resourceLocations` — resources restricted to your allowed locations.
- `compute.skipDefaultNetworkCreation` — no default network on new projects (org/folder path).

**Verification artifact:** `verify/org-policy.txt` containing a captured deny for each of the five list/Boolean constraints, plus a captured success for the compliant equivalent (a CMEK dataset, an internal-IP VM, an in-region bucket).

### 2. The VPC Service Controls perimeter (dry-run → enforce)

A perimeter around the **data project** protecting `bigquery.googleapis.com`, `storage.googleapis.com`, and `spanner.googleapis.com`, with:

- An Access Context Manager access policy and an access level for your operator + deploy identities.
- Ingress rules for the Cloud Build deploy SA, the Dataflow service agent, and any other legitimate cross-boundary caller — each justified in a comment.
- A **dry-run rollout**: applied with `use_explicit_dry_run_spec = true`, the dry-run violation log read and captured, ingress rules added until the log is clean of legitimate traffic, then promoted to enforce.

**Verification artifact:** `verify/vpc-sc.txt` containing (a) the dry-run violation log read, (b) a successful deploy *through* the perimeter, and (c) a captured VPC-SC `403` from outside the perimeter against a protected service.

> **Bare-trial path:** deliver the dry-run perimeter HCL, the ingress-identity justification list, and the expected-403 description. The design is graded; live enforcement is the full-path bonus.

### 3. Binary Authorization on the GKE deploy path (dry-run → enforce)

- A Cloud Build attestor backed by a Cloud KMS asymmetric-sign key.
- A `cloudbuild.yaml` whose successful build signs the image's attestation.
- A policy requiring attestation by that attestor, rolled out dry-run first, then enforced, with system-image whitelists so kube-system pods still run.

**Verification artifact:** `verify/binauthz.txt` containing a captured admission of a signed image and a captured denial of an unsigned one.

### 4. Secret Manager for every credential

- Every credential the system uses (the Cloud SQL password, any API token, the TLS private material) lives in Secret Manager — not in env vars baked into an image, not in Terraform state, not in code.
- Each secret is read at runtime by a workload identity with `roles/secretmanager.secretAccessor` scoped to *that secret* (not project-wide).

**Verification artifact:** `verify/secrets.txt` showing (a) the secret list, (b) the per-secret IAM bindings (scoped, not broad), and (c) a workload reading a secret via its workload identity with no keyfile present.

### 5. CMEK on BigQuery + Spanner

- A Cloud KMS key ring and keys with a 90-day rotation schedule and `prevent_destroy = true`.
- The BigQuery dataset(s) and the Spanner database encrypted with your keys, and the per-service service agents granted `cryptoKeyEncrypterDecrypter`.

**Verification artifact:** `verify/cmek.txt` showing the dataset and Spanner database reporting your `kmsKeyName`, and a non-CMEK creation attempt being denied by the org policy.

### 6. The FinOps cost report

A one-page memo, `finops-memo.md`, produced from the billing-export analysis (Exercise 3):

- The top three line items by *effective* 30-day cost, in dollars, with the query that produced them.
- For each, the proposed move (right-size / committed-use / spot) and the estimated annualized saving.
- The committed-use breakeven math for any CUD you propose, with your demonstrated utilization floor.
- One sentence of stated risk per move.

### 7. The graded on-call drill + postmortem

- Inject the synthetic fault (the provided `drill/inject.sh`, or your own equivalent) into the ingest service.
- Run the loop: page → triage → mitigate (rollback or paid region failover) → confirm recovery.
- Deliver `runbook.md` (signed off — you followed it during the drill) and `postmortem.md` (no-blame, with timeline, contributing factors, what-went-well, and owned/dated action items).

This is the 5%-of-course artifact. It is graded on postmortem quality, not mitigation speed.

### 8. The teardown gate (graded)

`teardown.sh` that scales the standby back to `min-instances=0`, confirms no warm paid compute remains, and confirms the billing export shows the failover spend stopped. The five hardening controls stay (they are free); the paid drill resources go.

---

## Suggested repo layout

```
week-14-hardening/
  README.md                      # how to apply, verify, drill, and tear down
  terraform/
    main.tf                      # wires the modules below
    variables.tf
    versions.tf
    modules/
      org-policy/                # the five-constraint bundle
      vpc-sc/                    # access policy, access level, perimeter (dry-run flag)
      binauthz/                  # attestor, KMS sign key, policy
      kms-cmek/                  # key ring, keys, service-agent grants
      secrets/                   # Secret Manager secrets + scoped IAM
  cloudbuild.yaml                # build + sign attestation
  drill/
    inject.sh                    # inject the synthetic fault
    mitigate.sh                  # rollback / region failover
  verify/
    org-policy.txt
    vpc-sc.txt
    binauthz.txt
    secrets.txt
    cmek.txt
  finops-memo.md
  runbook.md
  postmortem.md
  teardown.sh
```

---

## The drill script contract

`drill/inject.sh` must inject a *reversible* fault that trips a Week 13 burn-rate alert. The reference fault is a deploy of a broken revision to the ingest service that returns HTTP 500 on every request (a one-line change behind an env flag), or — for the paid failover path — forcing the cold standby region to take 100% of traffic. The mitigation script `mitigate.sh` reverses it: `gcloud run services update-traffic` back to the good revision, or scales the standby to `min-instances=1` and shifts traffic.

The drill is timed only so your postmortem has a real timeline. Capture timestamps from the page, the acknowledge, the mitigation, and the confirmed recovery — those are the spine of the postmortem.

---

## The postmortem template (use this exact structure)

`postmortem.md` must follow the SRE no-blame structure:

```markdown
# Postmortem — Ingest 500s, 2026-MM-DD

## Summary
<two sentences: what happened, user impact, duration>

## Impact
<quantified: requests/users affected, duration, SLO/error-budget consumed>

## Timeline (all times <TZ>)
- HH:MM  <factual event, no interpretation>
- HH:MM  ...

## Contributing factors
- <factor 1 — systemic, e.g. "no canary stage in the ingest deploy">
- <factor 2 — e.g. "burn-rate alert fast window was 5m, delaying detection">
- <factor 3 ...>

## What went well
- <the alert fired / the rollback worked / the runbook was followed>

## Action items
| Action | Owner | Due |
|---|---|---|
| <concrete change> | @you | 2026-MM-DD |

## Lessons learned
<one paragraph, generalizable>
```

The grader checks the **timeline** (factual, complete), the **contributing factors** (plural, systemic, not "the deploy was bad"), and the **action items** (each owned and dated). A blamey or shallow postmortem fails this section.

---

## Acceptance criteria

- [ ] `terraform apply` brings up all five hardening controls with `0` errors.
- [ ] Each control has a captured "verify the deny" transcript in `verify/`.
- [ ] The VPC SC perimeter was rolled out dry-run-first and a deploy *through* it succeeds (you did not lock yourself out).
- [ ] Binary Authorization denies an unsigned image and admits a signed one.
- [ ] Every credential is in Secret Manager with scoped IAM; no keyfile or env-baked secret remains.
- [ ] BigQuery and Spanner report CMEK `kmsKeyName`; a non-CMEK create is denied.
- [ ] `finops-memo.md` names the top three line items in dollars and proposes a saving with breakeven math.
- [ ] The drill ran: a real burn-rate page, a captured triage, a timestamped mitigation, confirmed recovery.
- [ ] `runbook.md` is signed off (you followed it) and `postmortem.md` follows the template with owned/dated action items.
- [ ] `teardown.sh` runs clean; the failover spend stopped; the free controls remain.

---

## Grading rubric (100 points)

| Area | Points | What earns full marks |
|---|---:|---|
| Org Policy bundle + verify | 12 | All five constraints applied and each deny captured; compliant equivalents still work. |
| VPC SC perimeter | 18 | Dry-run-first rollout; ingress justified; deploy-through succeeds; outside-403 captured; enforced only after clean dry-run. No self-lockout. |
| Binary Authorization | 14 | Cloud Build-signed attestor; dry-run-then-enforce; unsigned denied, signed admitted; break-glass explained. |
| Secret Manager | 8 | Every credential migrated; scoped per-secret IAM; runtime read via workload identity, no keyfile. |
| CMEK on BigQuery + Spanner | 8 | Both report your key; rotation + prevent_destroy set; service agents granted; non-CMEK create denied. |
| FinOps memo | 10 | Top three by effective cost in dollars; move + saving + breakeven + risk per item. |
| On-call drill + postmortem | 22 | Real page; factual timeline; systemic contributing factors; what-went-well; owned/dated action items; blameless tone; signed runbook. |
| Teardown gate | 8 | Paid resources gone; spend stopped (captured); free controls retained. |

Anything that *locks out your own deploys* — a perimeter or Binary Auth policy applied straight to enforce that broke CI/CD — caps the relevant section at half marks, because not-locking-yourself-out is the entire senior skill this week teaches.

---

## Compounding note

This mini-project **compounds on Week 13** and locks down everything built through Week 13. The hardened posture you ship here is the security section of your Week 15 capstone architecture review: the VPC SC perimeter, the Org Policy bundle, the Binary Authorization deploy path, the CMEK, and the postmortem all become slides and runbook sections you defend live. The failover drill is the paid-but-cheap opt-in (\$3–6). The teardown gate is included and graded — do not leave the standby region warm over the weekend.

When this is hardened, cost-reported, drilled, postmortemed, and *torn down*, you are ready for Week 15 — capstone delivery and the architecture review where a staff engineer asks you to defend every one of these decisions.
