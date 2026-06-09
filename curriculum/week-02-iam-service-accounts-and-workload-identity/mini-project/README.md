# Mini-Project — The IAM Baseline Module

> Add a reusable `iam-baseline` Terraform module to the Week 01 landing zone. It gives every environment custom least-privilege roles, a separated break-glass account, audit logging on the data path, and a Workload Identity Federation deploy path for CI — and nothing in the whole tree uses a downloaded key. Teardown gate included.

This mini-project **compounds on Week 01.** You are not starting fresh. Last week you built `bootstrap/`, `shared/`, and `workloads/` folders and five projects with billing budgets armed. This week you make that landing zone *safe to hand to a junior engineer* by giving it a real IAM posture. By the end you have a module you will keep extending — Week 04 refactors it into the shared module library, and the capstone runs on its descendants.

**Estimated time:** ~11.5 hours (split across Thursday, Friday, and Saturday in the suggested schedule).

---

## Where this fits in the compounding project tree

Your Week 01 repo looks roughly like this:

```
landing-zone/
├── bootstrap/          # the project that holds Terraform state + org-level setup
│   └── main.tf
├── shared/             # shared services (logging, networking later)
│   └── main.tf
├── workloads/
│   ├── dev/
│   │   └── main.tf
│   └── prod/
│       └── main.tf
└── modules/            # (may be empty or minimal after Week 01)
```

This week you add a `modules/iam-baseline/` module and consume it from each environment, plus a `modules/wif-github/` module for the CI path. Your tree becomes:

```
landing-zone/
├── bootstrap/
├── shared/
│   └── logging/                 # NEW: the log sink project for audit logs
├── workloads/
│   ├── dev/    main.tf          # CHANGED: now consumes iam-baseline
│   └── prod/   main.tf          # CHANGED: now consumes iam-baseline (stricter)
├── modules/
│   ├── iam-baseline/            # NEW: this week's deliverable
│   │   ├── variables.tf
│   │   ├── roles.tf             # custom least-privilege roles
│   │   ├── break_glass.tf       # separated emergency access
│   │   ├── audit.tf             # data-access audit logging + sink
│   │   └── outputs.tf
│   └── wif-github/              # NEW: keyless CI deploy path
│       ├── variables.tf
│       ├── main.tf
│       └── outputs.tf
└── audit/
    └── week-02-baseline.md      # extends the file you started in Lecture 1
```

If your Week 01 layout differs, adapt — the requirement is that `iam-baseline` is a *module* consumed by *each environment*, not copy-pasted HCL.

---

## What you will build

### 1. Custom least-privilege roles per environment

The `iam-baseline` module defines a small catalogue of custom roles that express the *job functions* your landing zone needs — not Google's coarse predefined roles, and never basic roles. At minimum:

- **`deployer`** — what CI uses to deploy: create/update the specific resources an environment deploys, read state, and nothing else. No IAM management, no key creation.
- **`appRuntime`** — what a workload's runtime SA gets: read its config bucket and write its data bucket, read secrets it owns. No project-wide anything.
- **`auditor`** — read-only across IAM and logs for the security reviewer: `cloudasset.viewer`, `iam.roleViewer`, `logging.viewer`. Cannot change anything.

Each role is derived from predefined roles' permission lists (the Exercise 1 method), documented with a one-line justification per permission block, and marked with a `stage`.

The module takes a `var.environment` ("dev" | "prod") and can tighten the role set per environment — e.g. `prod`'s `deployer` excludes any delete permission, so a prod deploy can never destroy data, only the teardown path (run by a human break-glass) can.

### 2. Break-glass account separation

A dedicated emergency-access path, **separate** from the everyday platform team's groups:

- A break-glass principal (a dedicated Google account you control, or a clearly-labeled group with exactly one member) that is **not** part of the normal platform group hierarchy.
- A `roles/owner` (or a near-owner custom role) binding on the environment that is **conditioned** so it is normally inert — e.g. a CEL condition tied to a "break-glass active" tag, or kept in a separate apply target requiring a second approver.
- A **log-based alert** that fires the instant the break-glass principal authenticates or is impersonated, paging a real channel.
- A `break-glass-runbook.md` documenting: when its use is justified, the hardware-key requirement, and the mandatory post-use review.

The grading point: everyday access and emergency access are *different identities with different blast radii*, and using the emergency one *lights up a pager*.

### 3. Audit logging on the data path

- **Data Access** audit logs (`DATA_READ` + `DATA_WRITE`) enabled for the services that hold sensitive data in each environment (start with `storage.googleapis.com`; add `bigquery.googleapis.com` if your env has BQ).
- A **log sink** routing audit logs to a BigQuery dataset (or GCS bucket) in the **`shared/logging` project** — a *different* project from the workloads, so a compromise of a workload project cannot delete the evidence.
- The sink's writer identity granted exactly `roles/bigquery.dataEditor` on the destination dataset and nothing more.

### 4. WIF for the CI deploy path

- The `wif-github` module stands up a pool + OIDC provider (from Challenge 1 / Lecture 2 §2.5), attribute-conditioned to your landing-zone repo.
- The CI deploy SA in each environment is the `deployer` custom role from (1), reachable only via WIF — **no key**.
- `prod`'s WIF binding is scoped to `main` (and ideally a `production` GitHub Environment with required reviewers); `dev`'s may allow any branch.

### 5. The teardown gate

A documented, runnable teardown that removes everything this module created and **proves** the org is back to zero keys and zero break-glass exposure.

---

## Rules

- **You may** read the GCP docs, the Cloud Foundation Toolkit IAM module, your lecture notes, and `resources.md`.
- **You may NOT** create a single user-managed service-account key. The org policy `iam.disableServiceAccountKeyCreation` should be enforced; if it is, key creation 403s and you've proven the point structurally.
- **You may NOT** use any basic role (`owner`/`editor`/`viewer`) *except* the break-glass binding, and that one must be conditioned/separated and alerted.
- **You must** consume `iam-baseline` as a module from at least `dev` and `prod`, passing `var.environment`.
- **You must** use `google_project_iam_member` (additive) for grants, never `_binding` or `_policy` on shared roles — clobbering an existing policy is an automatic fail.
- Terraform provider: `hashicorp/google ~> 6.0` (and `google-beta` if a resource requires it). Remote state in the GCS backend from Week 01.

---

## Acceptance criteria

- [ ] A new directory `modules/iam-baseline/` with `variables.tf`, `roles.tf`, `break_glass.tf`, `audit.tf`, `outputs.tf`.
- [ ] At least three custom roles (`deployer`, `appRuntime`, `auditor`), each derived from predefined-role permission lists, each with per-block justification comments.
- [ ] `dev` and `prod` both consume the module; `prod`'s `deployer` is strictly narrower (no delete) than `dev`'s.
- [ ] A break-glass principal separate from the everyday platform groups, with a conditioned/separated `roles/owner`-equivalent grant.
- [ ] A log-based alert that fires on break-glass authentication/impersonation, wired to a real notification channel.
- [ ] `break-glass-runbook.md` present and complete (when, how, hardware key, post-use review).
- [ ] Data Access audit logs enabled for at least `storage.googleapis.com` in each environment.
- [ ] A log sink routing audit logs to a dataset/bucket in a **separate** logging project, with a least-privilege writer-identity grant.
- [ ] A `wif-github` module providing a keyless CI deploy path; the deploy SA uses the `deployer` custom role and has **no** key.
- [ ] `prod`'s WIF binding scoped to `main`; demonstrated that a non-`main` push cannot deploy to prod.
- [ ] Exercise 3's audit tool runs against `dev` and `prod` and reports **zero CRITICAL findings** (exit code 0).
- [ ] `audit/week-02-baseline.md` updated: for each of the five mistakes, the landing zone's current posture and the module line that addresses it.
- [ ] The teardown gate runs clean (below) and the org is back to zero keys.

---

## Verification walkthrough

Run these after `terraform apply` on both environments:

```bash
# 1. No user-managed keys anywhere in either workload project.
for proj in "$DEV_PROJECT" "$PROD_PROJECT"; do
  for sa in $(gcloud iam service-accounts list --project="$proj" --format='value(email)'); do
    gcloud iam service-accounts keys list --iam-account="$sa" \
      --managed-by=user --project="$proj" --format='value(name)' \
      | grep -q . && echo "FAIL key on $sa" || true
  done
done
echo "key scan complete"

# 2. No basic roles outside the break-glass binding.
gcloud asset search-all-iam-policies --scope="projects/$PROD_PROJECT" \
  --query='policy:(roles/owner OR roles/editor)' \
  --format='value(policy.bindings.members)'
# -> only the break-glass principal should appear, on a conditioned binding.

# 3. The automated audit reports clean.
python3 ../exercises/exercise-03-audit-overprivileged-sa.py "$PROD_PROJECT"
echo "audit exit code: $?"   # must be 0

# 4. Data Access logging is on.
gcloud projects get-iam-policy "$PROD_PROJECT" --format=json | jq '.auditConfigs'

# 5. The keyless deploy works (push to main) and a non-main push to prod is denied.
#    (Demonstrated in your CI run logs, captured in the writeup.)
```

Expected: the key scan prints only `key scan complete`; the basic-role query returns only the conditioned break-glass principal; the audit tool exits `0`; `auditConfigs` shows `DATA_READ`/`DATA_WRITE` on storage.

---

## Teardown gate

This is a graded step. Skipping it fails the week.

```bash
# Tear down the workload environments first (they depend on the modules).
terraform -chdir=workloads/prod destroy -auto-approve
terraform -chdir=workloads/dev  destroy -auto-approve

# Then the shared logging sink (after the sources are gone).
terraform -chdir=shared/logging destroy -auto-approve

# Prove the org is back to a clean IAM posture:
for proj in "$DEV_PROJECT" "$PROD_PROJECT"; do
  gcloud iam service-accounts list --project="$proj" --format='value(email)' \
    | while read sa; do
        gcloud iam service-accounts keys list --iam-account="$sa" \
          --managed-by=user --project="$proj" --format='value(name)' \
          | grep -q . && echo "LEFTOVER KEY: $sa" || true
      done
done
echo "teardown verification complete — no leftover keys"
```

Note what you do **not** tear down: the org policies (`disableServiceAccountKeyCreation`, `automaticIamGrantsForDefaultServiceAccounts`) stay enforced — they are landing-zone posture, not per-week scaffolding. Document this distinction in your writeup: *some things this week are scaffolding to destroy; some are permanent posture to keep.*

---

## What to submit

1. The `landing-zone` repo (public GitHub), with the `modules/iam-baseline/` and `modules/wif-github/` modules and the changed `dev`/`prod`.
2. `break-glass-runbook.md`.
3. `audit/week-02-baseline.md` (the five-mistake posture report).
4. A `MINI-PROJECT.md` writeup: the role catalogue and its justifications, the break-glass design, the audit-sink topology, the WIF deploy path, and your captured verification output.
5. Evidence the teardown gate ran clean.

---

## Why this matters

Phase 1 of C18 builds "a locked-down landing zone you can hand to a junior engineer without flinching." Week 01 gave it structure and a budget. This week gives it an *identity posture*: nobody over-privileged, no keys to leak, emergencies that page, and a CI path that can't be impersonated. Every workload you deploy from Week 05 forward lands inside this posture. Get it right once, here, and you never think about it again — which is exactly what good platform engineering feels like.
