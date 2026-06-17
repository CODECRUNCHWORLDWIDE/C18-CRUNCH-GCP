# Challenge 1 — Harden the perimeter and run the drill

**This is the hard one.** You will apply the Organization Policy bundle, wrap the production project in a VPC Service Controls perimeter *without breaking your own deploys*, require Binary Authorization on the GKE deploy path, then run a synthetic on-call drill and deliver a signed-off runbook plus a no-blame postmortem. It is open-ended on purpose: there is no solution file, only acceptance criteria and the standard a staff engineer would hold you to.

**Estimated time:** 3 hours of focused work (plus the dry-run soak, which is wall-clock, not effort).

**Cost:** \$3–6 for the failover step. Tear down the same day.

---

## The scenario

Your team runs the Week-01–13 system: a Cloud Run ingest service, a Pub/Sub → Dataflow → BigQuery pipeline, a GKE service tier, and a Spanner store, all observable via the Week 13 OpenTelemetry + burn-rate alerts. Compliance has handed down three requirements and your manager has handed down a fourth:

1. **No data exfiltration path.** Even with a stolen service-account token, an attacker must not be able to read BigQuery or Spanner from outside the perimeter. (VPC Service Controls.)
2. **No unsigned code in production.** Only images your Cloud Build pipeline built and signed may run on GKE. (Binary Authorization.)
3. **No dangerous defaults.** Public IPs, public buckets, and non-CMEK datasets must be impossible to create. (Org Policy bundle.)
4. **Prove you can survive a bad night.** Run a drill, deliver a runbook the next on-call can follow, and a postmortem the team can learn from.

And the constraint that makes it hard: **you must not break your own deploys doing any of this.** A perimeter or a Binary Auth policy that locks out your CI/CD is a self-inflicted outage and an automatic fail of the challenge.

---

## Part 1 — The Org Policy bundle (build on Exercise 1)

Apply the three-constraint bundle from Exercise 1 (restrict public IPs, enforce CMEK, restrict locations) to the production project, plus add `iam.disableServiceAccountKeyCreation` and `storage.publicAccessPrevention`. Verify each deny.

**Acceptance criteria:**

- [ ] All five constraints applied via Terraform (`google_org_policy_policy`), committed.
- [ ] Captured deny transcripts for: public IP, public bucket, non-CMEK BigQuery dataset, SA key creation, out-of-region resource.
- [ ] A CMEK BigQuery dataset and an in-region bucket still create successfully (the controls do not over-block).

---

## Part 2 — The VPC Service Controls perimeter, without locking yourself out

Wrap the data project (the one holding BigQuery and Spanner) in a service perimeter protecting `bigquery.googleapis.com`, `storage.googleapis.com`, and `spanner.googleapis.com`. **Roll it out in dry-run first.** Read the dry-run violation log, add ingress rules for your legitimate identities (the Cloud Build deploy SA, your operator identity, the Dataflow service agent), and only enforce when the dry-run log is clean of legitimate traffic for a full working day.

**Acceptance criteria:**

- [ ] Perimeter applied in **dry-run** first (`use_explicit_dry_run_spec = true`), with a transcript of the dry-run violation log read via the `VpcServiceControlAuditMetadata` log filter.
- [ ] Ingress rules added for every legitimate cross-boundary identity, each justified in a one-line comment.
- [ ] A deploy run *through* the perimeter succeeds (your CI/CD is not locked out) — captured.
- [ ] **Verify the deny:** from outside the perimeter (e.g. your laptop with a token but not on an allowed access level), a `bq query` or `gcloud spanner databases execute-sql` against the protected project returns a VPC-SC `403`. Capture it.
- [ ] Perimeter promoted to **enforce** only after the dry-run log was clean.

> **Bare-trial path (no org):** you cannot create an Access Context Manager policy. Deliver the *dry-run perimeter spec* (the full HCL), the list of ingress identities you would allow with justification, and a paragraph describing the exact 403 you would expect from outside. The design is graded; the live enforcement is the full-path bonus.

---

## Part 3 — Binary Authorization on the GKE deploy path (build on Exercise 2)

Require attestation by your Cloud Build attestor for the GKE cluster. Wire the Cloud Build pipeline so a successful build *signs* the image's attestation. Roll out the policy in dry-run, confirm your real workloads are all attested, then enforce.

**Acceptance criteria:**

- [ ] A `cloudbuild.yaml` that builds the image, pushes to Artifact Registry, and runs the `sign-and-create` attestation step keyed to the image digest. Committed.
- [ ] Policy rolled out **dry-run first**, with the audit log confirming your existing workloads would pass.
- [ ] Policy promoted to `ENFORCED_BLOCK_AND_AUDIT_LOG`.
- [ ] **Verify the deny:** a `kubectl run` of an unsigned image (e.g. `nginx:latest`) is denied at admission with a Binary Authorization error. Captured.
- [ ] A signed image from the pipeline admits successfully. Captured.
- [ ] You can explain the break-glass annotation and when you would use it.

---

## Part 4 — The synthetic on-call drill

Inject a synthetic fault into the ingest service (a deploy that returns HTTP 500 on all requests, or a forced cold standby taking traffic). Run the full loop: receive the page from your Week 13 burn-rate alert, triage with Cloud Monitoring / Trace / Logging, mitigate (rollback or region failover — the failover is the paid step), confirm recovery, and write it up.

**Acceptance criteria:**

- [ ] The Week 13 burn-rate alert actually fired and paged (or you captured the alert firing if you do not have a real pager wired).
- [ ] A timestamped triage log: what you checked, in what order, and what you concluded.
- [ ] A mitigation with a captured timestamp and the exact command/action.
- [ ] Confirmed recovery: the SLO burn rate fell and held (not a single green point).
- [ ] **A signed-off runbook** for the alert: trigger, meaning, first checks, mitigations (commands), escalation, verification. "Signed off" = you followed it during the drill and fixed anything that did not work.
- [ ] **A no-blame postmortem** with: summary, quantified impact, factual timeline, contributing factors (plural, systemic — not just "the deploy was bad"), what-went-well, and action items each with an **owner and a due date**.

---

## Part 5 — Teardown gate (graded)

- [ ] Standby region scaled back to `min-instances=0`; no warm replicas remain.
- [ ] Billing export (or `gcloud billing`) confirms the failover spend stopped.
- [ ] The Org Policy / perimeter / Binary Auth controls remain (those are free and are the point) — but no paid compute is left running.

---

## How this is judged

A staff engineer reviewing this challenge looks for four things:

1. **Did you verify every deny?** A control with no captured rejection is treated as not in place.
2. **Did you avoid locking yourself out?** A perimeter or Binary Auth policy that broke your own deploys — even briefly — is the most common and most serious mistake. The dry-run rollout is how you prove you knew that.
3. **Is the postmortem real?** Timeline factual and complete, contributing factors systemic and plural, action items owned and dated, tone blameless. A shallow or blamey postmortem fails this part regardless of how clean the hardening was.
4. **Did you tear down?** The failover spend stopped, captured.

If you can hand this to the next on-call engineer and they can both *trust the controls* and *follow the runbook*, you have passed. That is the bar for Week 15.

---

## Stretch

- Add a **custom Org Policy constraint** that denies any GKE cluster without Binary Authorization enabled, and verify it denies a non-compliant cluster.
- Run the drill a **second time** with a different fault (certificate near-expiry, or a Week 09 Pub/Sub backlog) and diff your two postmortems. Repeated contributing factors are systemic — name them.
- Route a **Security Command Center** high-severity finding to Slack via Pub/Sub + a Cloud Run function, and trigger one by creating (then deleting) a public bucket in dry-run.
