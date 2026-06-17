# Week 2 — IAM, Service Accounts, and Workload Identity

Welcome to Week 2 of **C18 · Crunch GCP**. Last week you built a landing zone: a three-folder, five-project tree with billing budgets armed before a single byte of compute. It is locked down at the *resource hierarchy* level — you decided who owns which project. This week you decide what every principal in that hierarchy is actually *allowed to do*, and you do it without leaving a single long-lived credential on disk anywhere.

IAM is the part of GCP that gets people fired. Not because it is hard to make something work — granting `roles/owner` to a service account makes everything work — but because the way you make it work is exactly the way you get breached. The over-broad grant that unblocks a deploy on Friday is the lateral-movement path the attacker uses on Monday. This week is about learning to grant the *minimum* and to prove, with `gcloud asset` and Policy Analyzer, that you granted the minimum.

The headline skill of the week: **eliminate service-account key files.** A downloaded `.json` key is a password that never expires, that you cannot rotate without redeploying, that gets committed to repos, pasted into Slack, and copied to laptops. In 2026 there is no excuse for one in a CI pipeline. You will replace a GitHub Actions key-file deploy with Workload Identity Federation — short-lived, OIDC-minted, keyless — and then extend the pattern to a second provider.

We do almost everything in Terraform and `gcloud`. The Console is for *reading* the IAM model, never for writing it. A binding you clicked into existence is a binding nobody can review.

## Learning objectives

By the end of this week, you will be able to:

- **Distinguish** the four kinds of GCP principal — users, groups, service accounts, and federated (external) identities — and choose the right one for a given job.
- **Read** an IAM policy at any level of the hierarchy and compute the *effective* permissions on a resource, accounting for inheritance.
- **Classify** every role as basic, predefined, or custom, and explain why `roles/owner`, `roles/editor`, and `roles/viewer` are almost always the wrong answer.
- **Author** a custom IAM role containing the minimum permission set for a stated job function, and verify the claim with Policy Analyzer.
- **Scope** a binding with an IAM Condition by resource tag, name prefix, or time window using Common Expression Language (CEL).
- **Configure** service-account impersonation so humans and pipelines borrow an identity for minutes instead of holding a key forever.
- **Configure** Workload Identity Federation for GitHub Actions, GitLab CI, and a non-GCP Kubernetes cluster, so deploys are OIDC-only and the repo holds zero keys.
- **Audit** a project with `gcloud asset` and Policy Analyzer to find the over-privileged service account and the unused key.
- **Recognize and remediate** the five IAM mistakes that own production incidents: `roles/owner` sprawl, key-file sprawl, missing Data Access audit logs, no break-glass separation, and `serviceAccountUser`/`serviceAccountTokenCreator` confusion.

## Prerequisites

This week assumes you completed **Week 1** of C18 (the landing zone) and that you arrive with the course prerequisites: C1 Python, C15 DevOps (you can write a Terraform module with `for_each` and a remote backend, and a GitHub Actions or GitLab CI pipeline), and C14-level Linux. Specifically:

- You have the Week 1 landing-zone repo on disk, with `terraform`/`tofu` working against a GCS remote backend and a billing budget armed.
- `gcloud --version` reports a current SDK (>= 470.0.0). Run `gcloud components update` if it is stale.
- You can read JSON and YAML fluently and write a basic Python script with `pip install`-ed dependencies.
- You have a GitHub account and can create a repository and add a GitHub Actions workflow. (GitLab is used in the challenge; a free gitlab.com account covers it.)
- You understand OAuth2 and JWTs at the level of "an OIDC token is a signed JSON blob with claims and an expiry." If that sentence is fuzzy, read the OIDC primer linked in `resources.md` before Wednesday.

You do **not** need any prior GCP IAM exposure. We start at the principal model.

## Topics covered

- The four principal types: Google identities (users), Google Groups, service accounts (SAs), and federated identities via Workload Identity Federation.
- The IAM policy object: `bindings`, `members`, `role`, `condition`, and `etag` — and how the policy attaches at org / folder / project / resource level.
- Policy inheritance and the *effective* policy: the union of every binding from the resource up to the org.
- The role taxonomy: **basic** (`owner`/`editor`/`viewer` — legacy, too broad), **predefined** (Google-maintained, service-scoped), and **custom** (you author them).
- Permissions: the `service.resource.verb` grammar (`compute.instances.start`), `TESTING`/`SUPPORTED`/`GA` permission stages, and where the catalogue lives.
- Custom roles at org vs project level; `launchStage`; the rules for editing and deleting roles.
- IAM Conditions: CEL expressions over `resource.name`, `resource.type`, `request.time`, and resource tags; their limits (which services support them).
- Service-account impersonation: `roles/iam.serviceAccountTokenCreator`, `--impersonate-service-account`, short-lived access tokens and ID tokens, and the impersonation chain.
- The `iam.serviceAccountUser` vs `iam.serviceAccountTokenCreator` distinction — the single most-confused pair in GCP IAM.
- Workload Identity Federation: workload identity pools, OIDC and AWS providers, attribute mapping, attribute conditions, and the keyless token exchange.
- WIF for GitHub Actions (OIDC), GitLab CI (OIDC), and a self-managed / non-GCP Kubernetes cluster (OIDC via the cluster's issuer).
- Audit logging: Admin Activity (always on, free) vs Data Access logs (off by default, must be enabled), and routing them to a sink.
- The auditing toolchain: `gcloud asset search-all-iam-policies`, `gcloud asset analyze-iam-policy`, the Policy Analyzer, and the recommender that flags unused permissions.
- Break-glass design: a separate, alerting, audited, time-boxed path to elevated access that is never the daily-driver path.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Principals, the policy object, inheritance             |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Role taxonomy; authoring a custom least-privilege role |    1.5h  |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Wednesday | IAM Conditions; impersonation; the user/tokenCreator trap |  1.5h  |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6.5h    |
| Thursday  | Workload Identity Federation end-to-end                |    1h    |    1.5h   |     1h     |    0.5h   |   1h     |     1.5h     |    0h      |     6.5h    |
| Friday    | Auditing with gcloud asset + Policy Analyzer; mini-project |  0h   |    1h     |     1h     |    0.5h   |   1h     |     2h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                 |    0h    |    0h     |     0h     |    0h     |   0h     |     3.5h     |    0h      |     3.5h    |
| Sunday    | Quiz, review, teardown gate                            |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0.5h    |     2.5h    |
| **Total** |                                                        | **6h**   | **8h**    | **3h**     | **4h**    | **5h**   | **11.5h**    | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | Current (2026) GCP IAM docs, the OIDC primer, the WIF guides, talks |
| [lecture-notes/01-the-five-iam-mistakes.md](./02-lecture-notes/01-the-five-iam-mistakes.md) | The five IAM mistakes that own production incidents, and how to audit against each |
| [lecture-notes/02-impersonation-and-workload-identity-federation.md](./02-lecture-notes/02-impersonation-and-workload-identity-federation.md) | Impersonation vs. WIF; ending the keyfile era; the token exchange in detail |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-custom-least-privilege-role.md](./03-exercises/exercise-01-custom-least-privilege-role.md) | Author a custom role for a job function; verify with Policy Analyzer |
| [exercises/exercise-02-iam-condition.tf](./exercises/exercise-02-iam-condition.tf) | A Terraform config that scopes a binding by tag and by time window |
| [exercises/exercise-03-audit-overprivileged-sa.py](./03-exercises/exercise-03-audit-overprivileged-sa.py) | A Python auditor that finds the over-privileged SA via the Asset API |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-keyless-ci-with-wif.md](./challenges/challenge-01-keyless-ci-with-wif.md) | Replace a key file with WIF from GitHub Actions; extend to a second provider |
| [quiz.md](./05-quiz.md) | 13 questions with an answer key |
| [homework.md](./06-homework.md) | Five problems with rubric and time estimates |
| [mini-project/README.md](./07-mini-project/00-overview.md) | The IAM baseline module added to the Week 1 landing zone |

## The "least privilege or it didn't happen" promise

C18 uses a recurring marker on every IAM artifact this week. After you grant access, you must be able to produce the receipt:

```
$ gcloud asset analyze-iam-policy \
    --organization=ORG_ID \
    --identity="serviceAccount:deployer@PROJECT.iam.gserviceaccount.com" \
    --format="value(mainAnalysis.analysisResults[].iamBinding.role)"
roles/run.developer
roles/artifactregistry.writer
```

If that command prints `roles/owner`, `roles/editor`, or a list longer than the job needs, you are not done. The point of Week 2 is to make "the SA holds exactly these three roles, and here is the proof" an ordinary sentence in a code review.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **IAM deny policies** docs and add one deny rule to your project that blocks `iam.serviceAccountKeys.create` for everyone except a break-glass group: <https://cloud.google.com/iam/docs/deny-overview>.
- Turn on the **org policy constraint** `iam.disableServiceAccountKeyCreation` in your sandbox org and watch what breaks. Then fix what breaks the *right* way (impersonation / WIF) instead of toggling the policy back off: <https://cloud.google.com/resource-manager/docs/organization-policy/restricting-service-accounts>.
- Read the source of `google-github-actions/auth`: it is a thin Node action over the STS token exchange. Tracing one OIDC exchange through it teaches you more than any doc: <https://github.com/google-github-actions/auth>.
- Write a one-page note for your future self: "the difference between `actAs`, `serviceAccountUser`, and `serviceAccountTokenCreator`, with one example of each going wrong."

## Up next

Continue to **Week 3 — VPC, subnets, routes, and Cloud NAT** once you have pushed the mini-project and run the teardown gate. The IAM baseline you build this week is consumed by every later week: the GKE Workload Identity in Week 6, the Cloud Build deploy path in Week 4, and the VPC Service Controls perimeter in Week 14 all sit on top of it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
