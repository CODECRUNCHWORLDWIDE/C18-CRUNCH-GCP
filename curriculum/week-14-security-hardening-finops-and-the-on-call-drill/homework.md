# Week 14 Homework

Six practice problems that revisit the week's topics. The full set should take about **5 hours**. Work in your Week 14 Git repository so each problem produces at least one commit you can point to later.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

The rubric is at the bottom. The whole homework is graded out of 100.

---

## Problem 1 — Audit the five defaults on a real project

**Problem statement.** Take any GCP project you have (the Week 14 production project is ideal) and audit it against the five security defaults from Lecture 1. For each of the five, determine the *current* state and whether the closing control is in place. Write the audit at `notes/five-defaults-audit.md` as a table with columns: `Default`, `Closing constraint/control`, `Current state`, `In place?`, `Command that proves it`.

**Acceptance criteria.**

- The table covers all five: external IP, SA key creation, public storage, default network, Data Access audit logs.
- Each row names the exact constraint ID or control (e.g. `constraints/iam.disableServiceAccountKeyCreation`) and a `gcloud`/`bq` command whose output proves the current state.
- For at least one default that is *not* yet closed, the note includes the Terraform snippet that would close it.

**Hint.** For Data Access audit logs, `gcloud projects get-iam-policy $PROJECT_ID --format=json | jq '.auditConfigs'` shows whether `DATA_READ`/`DATA_WRITE` are captured. An empty result means data access is *not* logged.

**Estimated time.** 45 minutes.

---

## Problem 2 — Dry-run a VPC SC perimeter and read the would-deny log

**Problem statement.** Apply (or, on the bare-trial path, design and submit) a VPC SC perimeter around your data project in **dry-run** mode protecting BigQuery and Storage. Run your normal deploy and a normal query. Then read the dry-run violation log and produce `notes/vpc-sc-dryrun.md` listing every legitimate identity that *would* have been denied, with the ingress rule you would add to allow each.

**Acceptance criteria.**

- The perimeter HCL (`use_explicit_dry_run_spec = true`) is committed.
- `notes/vpc-sc-dryrun.md` quotes at least two lines from the `VpcServiceControlAuditMetadata` dry-run log and maps each to an ingress rule.
- The note explains, in two sentences, why you would *not* simply allow `*` for ingress (it would defeat the perimeter).

**Hint.** The log filter is in Lecture 1 §7: filter on `protoPayload.metadata.@type="...VpcServiceControlAuditMetadata"` and `protoPayload.metadata.dryRun=true`. The `violationReason` and `principalEmail` fields are what you map to ingress rules.

**Estimated time.** 50 minutes.

---

## Problem 3 — Wire and verify a Cloud Build attestation step

**Problem statement.** Write a `cloudbuild.yaml` that builds a trivial image, pushes it to Artifact Registry, and runs the `sign-and-create` attestation step against your Week 14 attestor, keyed to the built image's digest. Trigger the build, then confirm the attestation exists for that digest.

**Acceptance criteria.**

- `cloudbuild.yaml` has a build step, a push step, and an attestation step that uses the *digest* (not the tag) of the built image.
- `gcloud container binauthz attestations list --attestor=<attestor> --attestor-project=<project>` shows the attestation for the built digest.
- A 100-word note at `notes/attestation.md` explains why the attestation must be keyed to the digest and not the tag (tags are mutable; an attacker could repoint a tag to a malicious image).

**Hint.** Capture the digest inside the build with `$(gcloud artifacts docker images describe ... --format='value(image_summary.digest)')` or by reading the `cloudbuild` substitution `$_IMAGE@$$DIGEST` from a prior step that wrote it to a file in `/workspace`.

**Estimated time.** 50 minutes.

---

## Problem 4 — Find your top three line items and propose a saving

**Problem statement.** Using your billing export (or the synthetic table from Exercise 3 if your export has not populated), find the top three line items by *effective* 30-day cost and propose one FinOps move per item with a dollar saving. Write `notes/top-three-savings.md` with the query, the three line items, the proposed moves, and the estimated annualized saving for each.

**Acceptance criteria.**

- The SQL computes *effective* cost (cost + credits), not list cost, and is included in the note.
- Three line items named with dollar figures.
- Each has a move (right-size / committed-use / spot) and an annualized saving estimate.
- For any committed-use proposal, the breakeven utilization is computed and your demonstrated floor is stated.

**Hint.** Reuse Section A of Exercise 3 for the top three and Sections C/D for the committed-use saving and breakeven. Confirm the CUD percentage against the live pricing page before you put it in the note.

**Estimated time.** 45 minutes.

---

## Problem 5 — Migrate one real secret into Secret Manager

**Problem statement.** Pick one credential the system currently passes via an environment variable, a Terraform variable, or a config file — the Cloud SQL password is ideal — and migrate it into Secret Manager with scoped IAM. Update the consuming workload (Cloud Run or a GKE pod) to read it at runtime via its workload identity, with no keyfile. Confirm the workload still works and no plaintext secret remains in code or state.

**Acceptance criteria.**

- The secret exists in Secret Manager with `user_managed` regional replication.
- Exactly the consuming workload's identity has `roles/secretmanager.secretAccessor` on *that secret* (not project-wide, not a broad role).
- The workload reads the secret at runtime (a code snippet or the Cloud Run `--set-secrets` flag) and works.
- `git grep` for the plaintext secret returns nothing, and the secret is not in `terraform.tfstate`.

**Hint.** Cloud Run can mount a secret directly: `gcloud run services update <svc> --set-secrets=DB_PASSWORD=prod-db-password:latest`. For GKE, use the Secret Manager CSI driver or read it in code with `google-cloud-secret-manager` as in Lecture 1 §9.

**Estimated time.** 50 minutes.

---

## Problem 6 — Write a postmortem for a past (or synthetic) incident

**Problem statement.** Write a complete no-blame postmortem at `notes/postmortem-practice.md` for either (a) a real incident you have lived through in any job, sanitized, or (b) the synthetic ingest-500 drill if you have run it. Use the exact template from the mini-project: summary, quantified impact, factual timeline, *plural* contributing factors, what-went-well, and action items each with an owner and a due date.

**Acceptance criteria.**

- All seven sections present and in the template order.
- The timeline is factual and timestamped, with no interpretation mixed in.
- At least three contributing factors, and they are *systemic* (process/design), not "person X made a mistake."
- Every action item has an owner and a due date.
- The tone is blameless throughout — no individual is named as the cause.

**Hint.** Write the timeline first, purely from facts (logs, page history). Only after the timeline is complete do you write the contributing factors — and force yourself to list at least three, because "the deploy was bad" is never the whole story.

**Estimated time.** 40 minutes.

---

## Rubric (100 points)

| Problem | Points | Full marks when… |
|---|---:|---|
| P1 — Five-defaults audit | 15 | All five rows complete with constraint IDs and proving commands; at least one closing snippet. |
| P2 — VPC SC dry-run | 18 | Dry-run perimeter committed; would-deny log read and mapped to ingress rules; the "why not allow *" reasoning is sound. |
| P3 — Cloud Build attestation | 17 | `cloudbuild.yaml` signs the digest; attestation listed; the digest-not-tag reasoning is correct. |
| P4 — Top three + saving | 18 | Effective-cost SQL correct; three line items in dollars; move + saving per item; breakeven for any CUD. |
| P5 — Secret migration | 17 | Secret in Secret Manager; scoped per-secret IAM; runtime read with no keyfile; no plaintext in code/state. |
| P6 — Postmortem | 15 | All seven sections; factual timeline; ≥3 systemic contributing factors; owned/dated action items; blameless tone. |

**Passing is 70/100.** Two things are non-negotiable regardless of total: a control you claim is closed but cannot show denying the forbidden action does not count (P1, P2, P3), and a postmortem that names an individual as the cause fails P6 outright. The whole week is "verify the deny" and "blame the process, not the person."
