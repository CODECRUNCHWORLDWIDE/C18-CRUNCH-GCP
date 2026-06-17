# Lecture 1 — The Five IAM Mistakes That Own Production Incidents

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can read an IAM policy and its inheritance, name the four principal types, classify any role as basic/predefined/custom, and recognize-and-remediate the five IAM mistakes that turn into the incident channel.

If you only remember one thing from this lecture, remember this:

> **IAM is allow-only and additive.** There is no implicit deny that protects you. A principal can do something if *any* binding, *anywhere* from the resource up to the org root, grants it — and nobody has to approve that grant after the fact. The blast radius of a single careless `roles/editor` is the entire project, forever, silently.

That is the whole game. Everything below is a consequence of that one sentence.

---

## 1. The four principals

A GCP IAM policy grants *roles* to *principals*. There are exactly four kinds of principal you will use, and the syntax is part of the identity — `user:ada@example.com` and `serviceAccount:ada@example.com` are different principals even with the same local part.

| Principal | Identifier syntax | What it is | When to use |
|-----------|-------------------|------------|-------------|
| **User** | `user:ada@example.com` | A human Google identity (Workspace or Cloud Identity). | Real people. Almost never bound directly — bind the group. |
| **Group** | `group:platform-eng@example.com` | A Google Group; membership is managed in the directory. | The default for humans. You grant to the group; HR manages who is in it. |
| **Service account** | `serviceAccount:deployer@PROJECT.iam.gserviceaccount.com` | A non-human identity for a workload. | Code, pipelines, VMs, pods. |
| **Federated identity** | `principalSet://iam.googleapis.com/projects/.../attribute.repository/org/repo` | An external identity (GitHub, GitLab, AWS, a K8s cluster) trusted via Workload Identity Federation. | CI runners and non-GCP workloads. The keyless path. Lecture 2. |

There are a few more you will meet (`domain:example.com`, `allAuthenticatedUsers`, `allUsers` — the last two are *public access*, and `allUsers` on a bucket is the canonical "we leaked the data lake" headline). For day-to-day work, the four above are the vocabulary.

**The first rule of principals: bind groups, not users.** When you write `user:ada@example.com` into a policy, you have created a fact that outlives Ada's employment. When she leaves, someone has to remember that binding exists, find it across every project, and remove it. When you write `group:platform-eng@example.com`, offboarding Ada is one directory operation and every binding updates for free. The only principals that should appear as `user:` in a reviewed policy are break-glass accounts and, occasionally, the org's first bootstrapping admin.

---

## 2. The policy object and the read-modify-write loop

An IAM policy is a JSON object attached to one resource. Fetch the policy on your Week 1 workloads project:

```bash
gcloud projects get-iam-policy "$PROJECT_ID" --format=json
```

```json
{
  "version": 3,
  "etag": "BwYf3xZq1nA=",
  "bindings": [
    {
      "role": "roles/owner",
      "members": [
        "user:founder@example.com"
      ]
    },
    {
      "role": "roles/run.developer",
      "members": [
        "serviceAccount:deployer@my-proj.iam.gserviceaccount.com"
      ],
      "condition": {
        "title": "prod-only",
        "expression": "resource.name.startsWith(\"projects/my-proj/locations/us-central1\")"
      }
    }
  ]
}
```

Three fields matter every time:

- **`bindings`** — the list. Each binding is `{ role, members[], condition? }`. A principal granted the same role twice (once plain, once with a condition) gets *both*; conditions narrow a binding, they do not narrow other bindings.
- **`etag`** — an opaque optimistic-concurrency token. When you write a policy back, you must send the `etag` you read. If someone else changed the policy in between, your write fails and you re-read. This is why you never hand-edit IAM in two places at once.
- **`version`** — `3` means "conditions are present / allowed." Always request version 3 or conditions silently disappear from the read.

You almost never write policies by hand with `set-iam-policy`. That is the read-modify-write loop and it is a footgun: get the policy, edit JSON, set it back with the etag, hope nobody raced you. Two safer paths:

```bash
# Additive, single-binding, etag-safe: the gcloud "add-iam-policy-binding" helper.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:deployer@my-proj.iam.gserviceaccount.com" \
  --role="roles/run.developer"

# Or, the way we actually do it: Terraform, where the binding is declared and reviewed.
```

In Terraform you have three resources and choosing wrong corrupts state:

```hcl
# google_project_iam_member — ONE principal, ONE role. Non-authoritative. Safe default.
resource "google_project_iam_member" "deployer_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# google_project_iam_binding — ALL principals for ONE role. Authoritative for that role.
# It will REMOVE anyone you didn't list. Use only when you own the whole role.

# google_project_iam_policy — the ENTIRE policy. Authoritative for everything.
# It will remove every binding you didn't declare. Almost never what you want.
```

> **The rule:** default to `google_project_iam_member`. It is additive and minds its own business. Reach for `_binding` only when you genuinely own every grant of a role, and never use `_policy` on a project a human also touches — the first time someone clicks a Console grant and Terraform reverts it, you have started an incident.

---

## 3. Inheritance and the effective policy

Policies attach at four levels: organization, folder, project, resource. The *effective* policy on a resource is the **union** of every binding from that resource up to the org root. A `roles/viewer` granted at the folder level applies to every project in that folder and every resource in those projects. There is no way to subtract it lower down with a normal allow policy — inheritance is one-directional and additive. (IAM *deny* policies, a separate mechanism, are the only way to claw back; stretch goal.)

This is why a sloppy org- or folder-level grant is so dangerous. Granting `group:contractors@example.com` the role `roles/editor` at the folder level — "just so they can get unblocked this week" — silently gives them edit on every project that folder will *ever* contain, including the prod project you create next quarter. Nobody re-approves it. It just inherits.

Compute the effective answer the right way — do not eyeball it:

```bash
# Who can do what on this project, accounting for inheritance from folders/org.
gcloud asset analyze-iam-policy \
  --organization="$ORG_ID" \
  --full-resource-name="//cloudresourcemanager.googleapis.com/projects/$PROJECT_ID" \
  --format=json
```

We live in `analyze-iam-policy` for the rest of the week. It is the only tool that answers the question that matters — "what is the *effective* access" — rather than the question the Console answers, which is "what is bound *at this one level*."

---

## 4. The role taxonomy: basic, predefined, custom

A role is a named set of permissions. There are three kinds, and the difference is the difference between a junior and a senior engineer's IAM.

### Basic roles — the legacy trap

`roles/owner`, `roles/editor`, `roles/viewer`. They predate the rest of IAM. They are project-wide and enormous:

- **`roles/viewer`** — read almost everything in the project.
- **`roles/editor`** — modify almost everything. Notably, `editor` can create service accounts and (unless you block it) their keys, which is a privilege-escalation path.
- **`roles/owner`** — everything `editor` can do, *plus* manage IAM. An owner can grant themselves or anyone else any role. There is no containing an owner.

Basic roles exist for the first ten minutes of a new project and for nothing else. The number of permissions in `roles/editor` runs into the thousands and grows every time Google ships a service. You cannot reason about it. If you see a basic role on a service account in a code review, that is a finding, not a style nit.

### Predefined roles — the daily driver

Google maintains a few thousand predefined roles, scoped to a service and an intent: `roles/run.developer`, `roles/run.invoker`, `roles/storage.objectViewer`, `roles/artifactregistry.writer`, `roles/bigquery.dataViewer`. Read one:

```bash
gcloud iam roles describe roles/run.developer
```

```yaml
description: Can deploy and manage Cloud Run services.
includedPermissions:
- run.services.create
- run.services.delete
- run.services.get
- run.services.getIamPolicy
- run.services.list
- run.services.update
- run.revisions.get
- run.revisions.list
# ... and the supporting iam/serviceusage permissions ...
name: roles/run.developer
stage: GA
title: Cloud Run Developer
```

Predefined roles are the right answer most of the time. Compose several small ones rather than reaching for one big one. A deployer that pushes images and rolls out Cloud Run needs `roles/artifactregistry.writer` + `roles/run.developer` + the ability to act as the runtime SA — three named, reviewable, Google-maintained roles, not `roles/editor`.

### Custom roles — when predefined is still too broad

Sometimes even the narrowest predefined role grants more than the job needs, or you want a role that spans exactly N permissions across two services. Then you author a custom role from the permission catalogue. We do this in Exercise 1; the mechanics:

```bash
# Inspect what's available, then hand-pick.
gcloud iam roles create crunchDeployer \
  --project="$PROJECT_ID" \
  --title="Crunch Deployer" \
  --description="Deploy Cloud Run + push images. Nothing else." \
  --permissions="run.services.get,run.services.create,run.services.update,run.revisions.get,artifactregistry.repositories.uploadArtifacts" \
  --stage="GA"
```

Custom-role rules you must know:

- They live at **org** or **project** scope. Org-scoped roles are reusable across projects; project-scoped roles are not. For a baseline you reuse everywhere, define at the org. For a one-off, project.
- They are **not** automatically updated when Google adds permissions to a service. You own the maintenance. A predefined role grows; your custom role is frozen until you edit it.
- A permission can be in stage `TESTING`, `SUPPORTED`, or `GA`. A `TESTING` permission can disappear; do not put it in a role you depend on.
- You cannot include permissions you yourself do not hold. IAM will not let you mint a role more powerful than you.

> **The discipline:** start from the *narrowest predefined role that works*, deploy, then read the audit logs to see which permissions were actually used, then tighten to a custom role if there is a real gap. Do not start by inventing a custom role from first principles — you will get it wrong and spend a day chasing permission-denied errors. Start broad-but-predefined, measure, tighten. The IAM Recommender (section 7) automates the "measure" step.

---

## 5. Mistake #1 — `roles/owner` sprawl

**The mistake:** service accounts and humans accumulate `roles/owner` (or `roles/editor`) because it is the fastest way to make an error message go away. The deploy fails with `PERMISSION_DENIED`; someone grants the deployer `roles/editor`; the deploy works; the binding never gets tightened. Repeat across every project and every quarter. Within a year, half your service accounts are owners and you have no idea which permissions any of them actually needs.

**Why it owns incidents:** an owner SA whose key leaks (see mistake #2) is game over — the attacker can grant themselves more access, create more keys, disable audit logging, and delete the evidence. An owner has no blast-radius containment. The 2019-era cloud key-leak postmortems all share this shape: an over-privileged credential leaked, and because it was over-privileged, the leak escalated from "read one bucket" to "own the project."

**How to audit against it:** find every owner and editor, everywhere.

```bash
gcloud asset search-all-iam-policies \
  --scope="organizations/$ORG_ID" \
  --query="policy:(roles/owner OR roles/editor)" \
  --format="table(resource, policy.bindings.role, policy.bindings.members)"
```

Every row that is a `serviceAccount:` is a finding. The remediation is the section-4 discipline: replace the basic role with the composition of predefined roles the workload actually uses, verified against the audit log.

**How to prevent it:** an org policy constraint that simply forbids basic roles on service accounts is the strongest control. You will add the auditing query to CI in this week's homework so the count of basic-role bindings is a number that goes to zero and a test fails if it grows.

---

## 6. Mistake #2 — key-file sprawl

**The mistake:** someone runs `gcloud iam service-accounts keys create key.json --iam-account=...`, downloads a JSON key, and from that moment a password-that-never-expires exists outside Google's control. It gets committed (GitHub's secret scanning catches a few; most it does not), pasted into a CI secret store, copied to three laptops, and emailed once. There is no rotation. There is no expiry. There is no record of where the copies are.

**Why it owns incidents:** a service-account key is a bearer credential with no second factor and, by default, no expiry. Combine it with mistake #1 (the key is for an owner SA) and a single `git push` of a `.json` file is a full compromise. Combine it with mistake #3 (no Data Access logs) and you cannot even tell what the leaked key read.

**How to audit against it:** list every user-managed key and its age.

```bash
for sa in $(gcloud iam service-accounts list --project="$PROJECT_ID" --format="value(email)"); do
  gcloud iam service-accounts keys list \
    --iam-account="$sa" \
    --managed-by=user \
    --format="table(name.scope(keys), validAfterTime, validBeforeTime)"
done
```

Any key with `keyType: USER_MANAGED` is a finding the moment you have a keyless alternative — which, after Lecture 2, is always. (Google-managed keys, `keyType: SYSTEM_MANAGED`, are fine; those are the ones Google rotates for you and never lets you download.)

**How to prevent it:** the org policy `constraints/iam.disableServiceAccountKeyCreation`. Turn it on and the `keys create` call fails for everyone. Then the *only* ways to authenticate as an SA are impersonation (humans, local dev) and Workload Identity Federation (CI, workloads) — both keyless, both short-lived, both in Lecture 2. The entire second half of this week exists to make this org policy something you can turn on without breaking anyone.

---

## 7. Mistake #3 — missing audit logs

**The mistake:** GCP gives you **Admin Activity** audit logs for free and always-on — every "who changed IAM, who created a VM, who deleted a bucket" event. But **Data Access** logs — "who *read* which object, who *queried* which table" — are **off by default** for most services, because they are high-volume. So when the breach happens, you can see that the attacker's SA existed and what roles it held, but you cannot see *what data it actually touched*. The postmortem has a hole exactly where the impact assessment needs to be.

**Why it owns incidents:** "we were breached but we cannot determine what was exfiltrated" is the difference between a contained incident and a regulatory disclosure for your entire customer base. The cost of Data Access logging is real (volume), but the cost of not having it during an incident is unbounded.

**How to audit against it:** read the project's audit config.

```bash
gcloud projects get-iam-policy "$PROJECT_ID" \
  --format="json(auditConfigs)"
```

If `auditConfigs` is `null` or empty, Data Access logging is off. Turn it on for the services that touch sensitive data — at minimum Cloud Storage, BigQuery, and Secret Manager. In Terraform:

```hcl
resource "google_project_iam_audit_config" "data_access" {
  project = var.project_id
  service = "allServices" # or scope to "storage.googleapis.com", "bigquery.googleapis.com"

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

Then **route the logs off the project** to a sink the project's own admins cannot delete — a separate logging project's bucket or a BigQuery dataset — so that an attacker who compromises the project cannot erase the trail. The mini-project this week wires that sink.

---

## 8. Mistake #4 — no break-glass separation

**The mistake:** the path you use for emergency elevated access is the same path you use every day. Either everyone has standing `roles/owner` (so "emergency access" is meaningless because it is always-on — see mistake #1), or there is no emergency path at all and during the incident someone grants themselves owner in a panic, unreviewed, unalerted, and forgets to remove it afterward.

**Why it owns incidents:** the moments you need elevated access are exactly the moments you most need a record of who used it. Standing access means no signal. Panic access means no review. Both leave you, post-incident, unable to answer "who had owner during the outage and why."

**What break-glass actually looks like:**

- A **separate, named account or group** — `grp-breakglass@example.com` — that is *not* anyone's daily identity. Your daily account holds the least-privilege roles for your job; the break-glass identity holds the elevated roles and you assume it only in an emergency.
- Access to it is **alerting**: an assumption of the break-glass identity fires a notification to the whole team and the security channel. Using it is loud on purpose.
- It is **time-boxed** where possible — granted via a conditioned binding that expires (IAM Conditions, Lecture/Exercise this week), or via a just-in-time grant that is revoked on a timer.
- Every use produces an **Admin Activity log entry** (free, always-on) and, because you routed logs off-project (mistake #3), one nobody can delete.

The shape: separate identity, loud on use, time-boxed, logged off-project. The mini-project implements break-glass separation as a distinct group with a conditioned, alerting elevated-access binding.

---

## 9. Mistake #5 — `serviceAccountUser` / `serviceAccountTokenCreator` confusion

This is the single most-confused pair in GCP IAM, and the confusion is a real privilege-escalation vector. Both roles are *about* service accounts, and both sound like "lets you use the SA," but they grant different things.

- **`roles/iam.serviceAccountUser`** — lets a principal **attach** a service account to a resource it creates: deploy a Cloud Run service *running as* SA-X, create a VM *running as* SA-X, submit a Cloud Function *as* SA-X. The principal does not get the SA's token directly; the platform runs the workload with the SA's identity. The permission is `iam.serviceAccounts.actAs`.

- **`roles/iam.serviceAccountTokenCreator`** — lets a principal **mint short-lived tokens for** the SA: call `generateAccessToken` / `generateIdToken` and walk away with a credential that authenticates *as* the SA, from anywhere, for the token's lifetime. The permission is `iam.serviceAccounts.getAccessToken` (and friends). **This is impersonation.**

**Why the confusion owns incidents:** if you grant a principal `serviceAccountUser` (or, worse, `serviceAccountTokenCreator`) on a *powerful* SA — say one with `roles/owner` — you have just given that principal everything the SA can do. People grant `serviceAccountUser` thinking "they just need to deploy," not realizing that the SA they are pointing at is an owner, so "deploy as this SA" means "become an owner." The classic escalation: a developer has `roles/run.developer` (modest) plus `serviceAccountUser` on the *default Compute SA* (which, by default, has `roles/editor`). They deploy a Cloud Run service running as that editor SA, the service runs their code, and their code now executes with editor. Modest + actAs(powerful) = powerful.

**The rules that keep you safe:**

- Grant `serviceAccountUser` **scoped to the specific SA**, never project-wide, and only point it at *least-privilege* runtime SAs. Never at the default Compute/App Engine SA (which is why one of your first hardening moves is to strip roles off, or disable, the default SAs).
- Grant `serviceAccountTokenCreator` deliberately and rarely; it is the impersonation grant and Lecture 2 is built on it. When you grant it, grant it on the *target* SA to the *specific* caller, and audit it like a key.
- Read the difference out loud until it sticks: **`User` = act *as* (attach to a resource). `TokenCreator` = mint a *token* (impersonate from anywhere).**

Audit who can act-as or impersonate any SA:

```bash
gcloud asset search-all-iam-policies \
  --scope="organizations/$ORG_ID" \
  --query="policy:(roles/iam.serviceAccountUser OR roles/iam.serviceAccountTokenCreator)" \
  --format="table(resource, policy.bindings.role, policy.bindings.members)"
```

---

## 10. The audit toolchain, in one place

Everything above used three tools. Here they are together, because by Friday you will reach for them reflexively.

```bash
# 1. search-all-iam-policies — fast, org-wide, "find every binding matching a query".
#    Best for "show me every owner / every key-creator / every public bucket".
gcloud asset search-all-iam-policies --scope="organizations/$ORG_ID" \
  --query="policy:roles/owner"

# 2. analyze-iam-policy — slower, precise, "what is the EFFECTIVE access including inheritance".
#    Best for "what can THIS identity actually do" or "who can do X on THIS resource".
gcloud asset analyze-iam-policy --organization="$ORG_ID" \
  --identity="serviceAccount:deployer@my-proj.iam.gserviceaccount.com"

# 3. recommender — "which granted permissions has this principal NOT used in 90 days".
#    Best for tightening: it tells you the custom role you should have written.
gcloud recommender recommendations list \
  --project="$PROJECT_ID" \
  --recommender="google.iam.policy.Recommender" \
  --location=global \
  --format="table(content.overview.member, content.overview.removedRole)"
```

Three questions, three tools: *who has this role* (search), *what can this identity effectively do* (analyze), *what is over-granted* (recommender). Memorize which tool answers which question.

---

## 11. Recap

You should now be able to:

- Name the four principal types and write their identifier syntax from memory.
- Read a policy object — `bindings`, `members`, `condition`, `etag` — and explain the read-modify-write loop and why you prefer `add-iam-policy-binding` / Terraform `_member`.
- Explain inheritance: the effective policy is the union from resource to org, additive and allow-only.
- Classify any role as basic / predefined / custom and articulate why basic roles are a finding on a service account.
- State all five mistakes, the audit query for each, and the remediation:
  1. **`roles/owner` sprawl** — `search-all-iam-policies` for basic roles; replace with composed predefined/custom roles.
  2. **Key-file sprawl** — `keys list --managed-by=user`; disable key creation, move to impersonation + WIF.
  3. **Missing audit logs** — check `auditConfigs`; enable Data Access logs and route them off-project.
  4. **No break-glass separation** — a distinct, alerting, time-boxed, off-project-logged elevated path.
  5. **`User`/`TokenCreator` confusion** — *act as* vs *mint token*; scope to specific least-privilege SAs.

Next up: how to stop downloading keys at all. Continue to [Lecture 2 — Impersonation and Workload Identity Federation](./02-impersonation-and-workload-identity-federation.md).

---

## References

- *IAM overview* — Google Cloud: <https://cloud.google.com/iam/docs/overview>
- *Understanding roles* — Google Cloud: <https://cloud.google.com/iam/docs/understanding-roles>
- *Resource hierarchy & inheritance* — Google Cloud: <https://cloud.google.com/iam/docs/resource-hierarchy-access-control>
- *Best practices for service accounts* — Google Cloud: <https://cloud.google.com/iam/docs/best-practices-service-accounts>
- *Cloud Audit Logs* — Google Cloud: <https://cloud.google.com/logging/docs/audit>
- *Analyze IAM policy (Asset Inventory)* — Google Cloud: <https://cloud.google.com/asset-inventory/docs/analyzing-iam-policy>
- *IAM Recommender* — Google Cloud: <https://cloud.google.com/iam/docs/recommender-overview>
- *Service account permissions (User vs TokenCreator)* — Google Cloud: <https://cloud.google.com/iam/docs/service-account-permissions>
