# Week 2 Homework

Six practice problems that revisit the week's topics beyond the lab. The full set should take about **6 hours**. Work in your landing-zone Git repository so each problem produces at least one commit you can point to later, and so the IAM artifacts live alongside the mini-project.

Each problem includes a **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**. The rubric is at the bottom.

---

## Problem 1 — Policy archaeology

**Problem statement.** Pick any project you can read (your `workloads/dev`, or a sandbox). Fetch its IAM policy as JSON and write `notes/p1-policy-read.md` that, for **every binding**, records: the role, whether it's basic/predefined/custom, whether the member is a user/group/SA/federated identity, and whether there's a condition. Then write one sentence per binding answering: *if this principal's credentials leaked tomorrow, what's the blast radius?*

**Acceptance criteria.**

- `notes/p1-policy-read.md` exists with one row per binding and a blast-radius sentence each.
- At least one binding is correctly classified by role tier and principal type.
- You flag any basic-role binding explicitly as Mistake #1.
- Committed.

**Hint.** `gcloud projects get-iam-policy PROJECT --format=json | jq '.bindings'`. Role tier: `roles/owner|editor|viewer` = basic; `projects/.../roles/...` = custom; everything else `roles/...` = predefined.

**Estimated time.** 30 minutes.

---

## Problem 2 — Derive a custom role from scratch

**Problem statement.** A new job function lands: a **"log shipper"** SA that must read its own application logs and write them to one Pub/Sub topic, nothing else. Without guessing, derive the minimum permission set by inspecting predefined roles (`roles/logging.viewer`, `roles/pubsub.publisher`), then write the custom role in Terraform under `homework/p2-log-shipper/`. Apply it, bind it to a test SA, and prove with Policy Analyzer that the SA *cannot* delete the topic.

**Acceptance criteria.**

- A custom role defined in Terraform with an explicit, minimal permission list.
- A comment in the HCL citing which predefined role each permission came from.
- Policy Analyzer (or an impersonated access test) shows the SA can publish but cannot `pubsub.topics.delete`.
- `terraform apply` succeeds; no SA key created.
- Committed, then torn down.

**Hint.** `gcloud iam roles describe roles/pubsub.publisher --format='value(includedPermissions)'`. Publish needs `pubsub.topics.publish`; reading logs needs `logging.logEntries.list` and friends. Resist adding `pubsub.topics.delete`.

**Estimated time.** 1 hour.

---

## Problem 3 — A condition you can defend

**Problem statement.** Write an IAM condition (CEL) for this requirement and apply it as a `google_project_iam_member` binding under `homework/p3-condition/`: *a contractor group may use `roles/run.developer`, but only on Cloud Run services whose name starts with `demo-`, and only until the contract end date `2026-09-30`.* Then write `homework/p3-condition/REASONING.md` explaining each clause and naming one attribute you considered using but couldn't, because it isn't available on the request (check the attribute reference).

**Acceptance criteria.**

- A conditional binding with a CEL expression that has a resource-name clause **and** a time clause.
- The time clause uses `request.time` compared to a fixed timestamp, timezone-pinned.
- `REASONING.md` explains each clause and names one *unavailable* attribute you checked against the reference.
- `terraform apply` succeeds; committed; torn down.

**Hint.** Resource-name clause: `resource.name.startsWith('...demo-')`. Time clause: `request.time < timestamp('2026-09-30T00:00:00Z')`. The attribute reference is in `resources.md`; not every attribute exists on every service's request.

**Estimated time.** 1 hour.

---

## Problem 4 — Run the audit tool and act on it

**Problem statement.** Run Exercise 3's `exercise-03-audit-overprivileged-sa.py` against two projects you control. For the highest-ranked (widest blast-radius) SA in each, write `homework/p4-audit/findings.md` recording: its current roles, *why* it's wide, and a concrete before/after plan to scope it down (which predefined or custom role replaces which basic/admin role). If a project comes back with a CRITICAL finding, **fix one** of them and re-run to show the exit code drop to 0.

**Acceptance criteria.**

- The tool ran against two projects; output captured in `findings.md`.
- For each project's top SA, a before/after least-privilege plan.
- At least one CRITICAL finding actually remediated, with the re-run showing exit code 0 (or a written explanation if both projects were already clean).
- Committed.

**Hint.** The most common top finding is the default Compute SA with `roles/editor`. The fix is usually: enforce `automaticIamGrantsForDefaultServiceAccounts`, then grant the workload's runtime SA exactly what it needs.

**Estimated time.** 1 hour.

---

## Problem 5 — The keyless migration writeup

**Problem statement.** Take a real or hypothetical pipeline that *currently* uses a downloaded SA key (describe it precisely — what it does, where the key lives). Write `homework/p5-keyless/MIGRATION.md` that lays out the step-by-step migration to a keyless path: impersonation if the caller already has a GCP identity, or WIF if it's an external CI/workload. Include the exact Terraform/`gcloud` for the pool/provider or the impersonation grant, the attribute condition, and the `principalSet` binding. End with the rollback plan and the verification that proves zero keys.

**Acceptance criteria.**

- `MIGRATION.md` precisely describes the "before" (the key) and the "after" (impersonation or WIF).
- Includes real, correct Terraform/`gcloud` for the keyless path, with an attribute condition where WIF applies.
- States the verification command proving no user-managed keys remain.
- States a rollback plan.
- Committed.

**Hint.** If the caller is GitHub/GitLab/K8s → WIF (Lecture 2 §2.5–2.6). If the caller is a developer or a GCP-resident job that already has an identity → impersonation (§2.2). The "before/after" framing is the whole point.

**Estimated time.** 1 hour.

---

## Problem 6 — The five-mistake self-audit

**Problem statement.** Write `homework/p6-five-mistakes.md`: for each of the five IAM mistakes from Lecture 1, state (a) the one `gcloud`/script command you'd run to detect it, (b) the current state of your landing zone against it, and (c) the one Terraform change or org policy that fixes/prevents it. This is the seed of an IAM audit checklist you'll carry into every future GCP org you touch.

**Acceptance criteria.**

- All five mistakes covered, each with a detect command, a current-state line, and a fix.
- The detect commands are real and runnable (not pseudocode).
- At least two of the fixes reference an org policy constraint by name.
- Committed.

**Hint.** Detect commands: #1 `search-all-iam-policies` for basic roles; #2 the key-finder loop; #3 `jq '.auditConfigs'`; #4 grep the policy for the break-glass principal and confirm it's separated+alerted; #5 `search-all-iam-policies` for project-level `serviceAccountUser`.

**Estimated time.** 45 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 30 min |
| 2 | 1 h 0 min |
| 3 | 1 h 0 min |
| 4 | 1 h 0 min |
| 5 | 1 h 0 min |
| 6 | 45 min |
| **Total** | **~5 h 15 min** |

---

## Rubric

Graded out of 100. Each problem is weighted; partial credit is real.

| Criterion | Weight | What earns full marks |
|---|---:|---|
| **Least privilege applied** (P1, P2, P4) | 25 | Roles are predefined-or-custom and derived, not guessed; basic-role usage is flagged and justified or removed. |
| **Conditions correct & defended** (P3) | 15 | Both clauses present, timezone pinned, reasoning sound, an unavailable attribute correctly identified. |
| **Audit rigor** (P1, P4, P6) | 20 | Commands are real and runnable; findings are specific; at least one remediation demonstrated end-to-end. |
| **Keyless mastery** (P5) | 20 | The migration is concrete and correct; the attribute condition and `principalSet` scope are right; verification proves zero keys. |
| **The five-mistake checklist** (P6) | 10 | All five covered with detect + state + fix; org policies named. |
| **Repo hygiene** (all) | 10 | Each problem committed; no committed keys; teardown evident where resources were created. |

**Pass mark for the week's homework: 70.** A submission that creates or commits *any* user-managed SA key caps at 50, regardless of other quality — the whole point of the week is that you no longer need one.
