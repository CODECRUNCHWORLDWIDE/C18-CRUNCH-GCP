# Week 2 — Quiz

Twelve questions. Take it with your lecture notes closed. Aim for 11/12 before moving to Week 3. Answer key at the bottom — don't peek.

---

**Q1.** An IAM policy answers a single question. Which one?

- A) Where in the world is this resource stored?
- B) Who can do what on which resource, and under what condition?
- C) How much will this resource cost per month?
- D) Which APIs are enabled on this project?

---

**Q2.** Which principal type should appear in *most* of your production IAM bindings?

- A) Individual users (`user:jane@example.com`).
- B) Google Groups (`group:platform@example.com`).
- C) Service-account keys.
- D) The default Compute service account.

---

**Q3.** What does the `etag` field on an IAM policy protect against?

- A) Unauthorized reads of the policy.
- B) Lost-update races — a write fails if the policy changed since you read it.
- C) Policies growing beyond the size limit.
- D) Conditions referencing attributes that don't exist.

---

**Q4.** A user has `roles/editor` granted at the **organization** level. You remove them from a specific project's IAM policy. What is their effective access on that project?

- A) None — the project-level removal revokes it.
- B) They still have `roles/editor` on the project, via inheritance from the org.
- C) `roles/viewer` only — removal downgrades rather than revokes.
- D) It depends on the `etag`.

---

**Q5.** You need a role for a workload that reads objects from one bucket and nothing else. What's the correct first move?

- A) Grant `roles/editor` — it's simplest.
- B) Grant `roles/storage.admin` — it's storage-scoped.
- C) Grant the predefined `roles/storage.objectViewer`; drop to a custom role only if no predefined role is narrow enough.
- D) Create a custom role with every `storage.*` permission.

---

**Q6.** Which statement about `roles/iam.serviceAccountUser` vs. `roles/iam.serviceAccountTokenCreator` is correct?

- A) They are aliases for the same permission set.
- B) `serviceAccountUser` mints short-lived tokens; `serviceAccountTokenCreator` attaches the SA to resources.
- C) `serviceAccountUser` lets a principal *act as* / attach the SA; `serviceAccountTokenCreator` lets a principal *mint short-lived tokens as* the SA (impersonation).
- D) Both should always be granted at the project level for convenience.

---

**Q7.** Why is a downloaded service-account JSON key file a production liability?

- A) It is large and slows down deploys.
- B) It is a long-lived, non-expiring bearer credential that does not rotate and cannot be scoped after issuance.
- C) It only works from inside GCP, so it breaks local development.
- D) It encrypts data at rest, which is redundant with CMEK.

---

**Q8.** In Workload Identity Federation for GitHub Actions, what are the **two** security gates that scope which tokens can reach a service account?

- A) The billing budget and the quota.
- B) The provider's *attribute condition* and the SA's `workloadIdentityUser` *`principalSet://` binding*.
- C) The repo's branch protection and a `GCP_SA_KEY` secret.
- D) The VPC firewall and Cloud Armor.

---

**Q9.** A GitHub Actions workflow needs to mint its OIDC token for WIF. Which workflow permission is required?

- A) `contents: write`
- B) `id-token: write`
- C) `actions: write`
- D) `packages: write`

---

**Q10.** You write an IAM condition `request.time.getHours() >= 2 && request.time.getHours() < 6` and access behaves inconsistently across teammates. What's the most likely bug?

- A) `getHours()` isn't a valid CEL function.
- B) You didn't pin a timezone — use `getHours('UTC')`; otherwise the evaluator's timezone shifts the window.
- C) Conditions can't reference `request.time`.
- D) The binding needs `roles/owner` to evaluate conditions.

---

**Q11.** Which Terraform IAM resource is **safe** (additive) for adding one member to a role without disturbing the existing policy?

- A) `google_project_iam_policy` — sets the entire policy.
- B) `google_project_iam_binding` — sets all members of one role.
- C) `google_project_iam_member` — adds one member to one role, non-destructively.
- D) None of them are additive; you must edit JSON by hand.

---

**Q12.** Admin Activity audit logs are on by default, but you investigate a breach and can't tell *who read* the customer bucket. Why, and what's the fix?

- A) Audit logs are never available for Cloud Storage; there is no fix.
- B) Data Access logs are off by default; enable `DATA_READ`/`DATA_WRITE` for `storage.googleapis.com` and route them to a sink in a separate project.
- C) The logs were deleted by the etag rotation; restore from backup.
- D) You need `roles/owner` to read any audit log; grant it to yourself.

---

## Answer key

> Don't read this until you've committed to your answers.

| Q | Answer | Why |
|---|--------|-----|
| 1 | **B** | IAM is exactly "who can do what on which resource, under what condition." Everything else maps to those four nouns. |
| 2 | **B** | Bind groups, not individuals — membership is managed by your IdP and access tracks joiners/leavers automatically. Direct user bindings are a cleanup smell. |
| 3 | **B** | The `etag` is a concurrency token for read-modify-write; a stale etag makes the write fail, preventing two engineers from silently clobbering each other. |
| 4 | **B** | IAM allow policies inherit downward and are additive; you cannot revoke at a child what a parent granted. Fix it at the org or use an IAM Deny policy. |
| 5 | **C** | Predefined first (`roles/storage.objectViewer`), custom only when no predefined role is narrow enough. `editor`/`admin` are over-grants; "every storage permission" is just a hand-rolled admin. |
| 6 | **C** | `serviceAccountUser` = act as / attach (deploy-time). `serviceAccountTokenCreator` = mint short-lived tokens (impersonation). Both granted on the SA resource, never the project. |
| 7 | **B** | A downloaded key is a non-expiring bearer credential. It doesn't rotate, can't be scoped after issuance, and is the largest category of GCP credential compromise. |
| 8 | **B** | The provider's attribute condition gates which external tokens enter the pool; the `principalSet://` binding gates which mapped identities may impersonate the SA. Belt and suspenders. |
| 9 | **B** | `id-token: write` lets the runner request its OIDC JWT from GitHub. Without it, `google-github-actions/auth` has no token to exchange. |
| 10 | **B** | Always pin the timezone in condition time math: `getHours('UTC')`. An unpinned call uses the evaluator's zone and your window drifts per locale. |
| 11 | **C** | `_member` is additive (one member, one role). `_binding` is authoritative for a role (wipes other members); `_policy` is authoritative for the whole resource (wipes everything). When in doubt, `_member`. |
| 12 | **B** | Data Access logs are off by default (high volume, billable). Enable `DATA_READ`/`DATA_WRITE` for the data services and route to a sink in a separate project so a workload compromise can't delete the evidence. |

**Scoring.** 11–12 correct: you can be trusted with `setIamPolicy`. 8–10: re-read the five mistakes in Lecture 1. Below 8: re-read both lectures before the mini-project — IAM mistakes compound, and this is the week they start.
