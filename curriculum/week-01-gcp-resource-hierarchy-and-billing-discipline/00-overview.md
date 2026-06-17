# Week 1 — The GCP Resource Hierarchy & Billing Discipline

Welcome to **C18 · Crunch GCP**. Week 1 is the unglamorous, load-bearing foundation: the resource hierarchy and the billing model. By Friday you should be able to map a real org chart onto a folder/project tree, arm a hard billing budget with Slack alerts *before* you create a single VM, and switch between three named `gcloud` configurations without thinking about it.

We assume you already know one cloud — most likely AWS — and that you can write a Terraform module from scratch. The C15 graduate is the target: comfortable with `terraform plan`, IAM-as-a-concept, and the idea that infrastructure is code under review. If that's you, this week is less "learn cloud" and more "learn how GCP draws its boundaries, and why those boundaries differ from the AWS account model you already carry in your head."

The first thing to internalize is that **GCP's primary isolation primitive is the project, not the account**. In AWS, the account is the blast radius, the billing unit, and the IAM trust boundary all at once. In GCP those three concerns are split across three different objects — the project, the billing account, and the IAM policy attached at some node of the hierarchy. Getting that split wrong on day one is how teams end up with a hundred resources in one project that nobody can safely delete. We are not going to do that.

The second thing to internalize: **no compute is deployed this week until billing budgets are armed.** This is not a stylistic preference. It is exercise #1 of the entire course and a hard gate. A GCP project with billing enabled and no budget is a way to wake up to a five-figure invoice because a misconfigured Dataflow job ran all weekend. We arm the budget first, every time, forever.

## Learning objectives

By the end of this week, you will be able to:

- **Distinguish** the four nodes of the GCP resource hierarchy — organization, folder, project, resource — and state what each one is *for* as a security and isolation boundary.
- **Contrast** GCP's project boundary with the AWS account boundary, naming concretely where the GCP primitive is stronger (cheap to create, policy inheritance) and where it is weaker (shared control plane, quota at project scope).
- **Explain** the billing-account-to-project relationship: many projects bill to one billing account, and budget alerts route on the billing account, not the project.
- **Arm** a hard billing budget with threshold alerts at 50/90/100% wired to a Slack channel through Pub/Sub and a Cloud Function — before provisioning any resource.
- **Map** a sample org chart to a folder/project tree and defend every boundary placement in writing.
- **Configure** three named `gcloud` configurations (`dev`, `prod`, `admin`) and switch between them with `gcloud config configurations activate`.
- **Read** the GCP quota model: per-project, per-region quotas; the difference between rate quotas and allocation quotas; and where to request an increase.
- **Provision** a folder/project tree and its budgets with Terraform, idempotently, with state you can hand to a teammate.
- **Validate** a deployed hierarchy with `gcloud asset` and prove a budget alert actually fires.

## Prerequisites

This week assumes you have completed **C15 · Crunch DevOps** or carry equivalent industry experience. Specifically:

- You can write a Terraform module from scratch with variables, outputs, and a `for_each`.
- You understand IAM as a concept: principals, roles, policies, the idea of least privilege.
- You are fluent in a terminal: `cd`, environment variables, piping, reading a `jq` filter.
- You can read and write basic Git (`clone`, `add`, `commit`, `push`).
- You have a credit card for the GCP free trial. Everything this week fits inside the \$300 trial and the always-free tier; the only "spend" is a deliberate \$1 test charge you will trigger to prove a budget alert fires, and even that is optional.

You do **not** need any prior GCP exposure. We start at the hierarchy. If you have an AWS account model burned into your reflexes, you will need to unlearn one habit — "one account per blast radius" — and we will flag it as we go.

## Topics covered

- The resource hierarchy: **organization → folder → project → resource**, and IAM policy inheritance down the tree.
- The **Cloud Identity / Google Workspace** requirement for an organization node, and how to get one for free.
- **Projects**: project ID vs. project number vs. display name; why the ID is immutable and globally unique; the 30-day soft-delete window.
- **Folders** as the org-design tool: by environment, by team, by business unit — and the trade-offs of each.
- **Billing accounts**: the many-projects-to-one-billing-account relationship; self-serve vs. invoiced; the `billing.resourceAssociations` link.
- The **budget** object: amount, scope (billing account, project, label), threshold rules, and the Pub/Sub notification channel.
- Routing a budget alert to **Slack** via Pub/Sub → Cloud Function → Incoming Webhook.
- The **quota model**: rate quotas vs. allocation quotas; per-project and per-region scope; how to read `gcloud compute regions describe` quotas and request an increase.
- The seven `gcloud` muscle-memory commands: `auth login`, `config configurations`, `projects`, `organizations`, `billing`, `asset`, `services`.
- **`gcloud config configurations`**: named contexts for `dev`/`prod`/`admin`, the active config, and per-config properties.
- **Terraform on the `google` provider**: the `google_folder`, `google_project`, `google_billing_budget`, and `google_project_service` resources; the bootstrap chicken-and-egg problem (who creates the project that holds the state bucket?).
- Why **"click in console, then read the API"** is fine in week one and how `gcloud ... --log-http` and the Terraform import workflow teach you the real resource shapes.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target.

| Day       | Focus                                              | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Hierarchy: org/folder/project/resource; AWS contrast |   2h     |    1h     |     0h     |    0.5h   |   1h     |     0h       |    1h      |     5.5h    |
| Tuesday   | Billing accounts, budgets, alert routing to Slack    |   2h     |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Wednesday | Quota model; `gcloud` muscle memory; configurations  |   1h     |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Thursday  | Terraform for the hierarchy; bootstrap problem        |   1h     |    1h     |     1h     |    0.5h   |   1h     |     2h       |    0h      |     6.5h    |
| Friday    | Landing-zone challenge; mini-project work             |   0h     |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                |   0h     |    0h     |     0h     |    0h     |   0.5h   |     3h       |    0h      |     3.5h    |
| Sunday    | Quiz, review, teardown verification                   |   0h     |    0h     |     0h     |    1h     |   0h     |     0.5h     |    0h      |     1.5h    |
| **Total** |                                                      | **6h**   | **6h**    | **4h**     | **3.5h**  | **5.5h** | **11.5h**    | **2.5h**   | **35h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | Curated, current (2026) GCP docs, books, and talks |
| [lecture-notes/01-project-boundaries-vs-aws-accounts.md](./02-lecture-notes/01-project-boundaries-vs-aws-accounts.md) | The hierarchy as a security model; where GCP's project boundary beats and loses to AWS accounts |
| [lecture-notes/02-billing-accounts-and-budget-alert-routing.md](./02-lecture-notes/02-billing-accounts-and-budget-alert-routing.md) | The billing-account-to-project relationship and routing budget alerts before they page your CTO |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-arm-the-budget-first.md](./03-exercises/exercise-01-arm-the-budget-first.md) | **Mandatory exercise #1:** a hard budget cap with 50/90/100% alerts wired to Slack before any resource |
| [exercises/exercise-02-map-the-org-chart.py](./03-exercises/exercise-02-map-the-org-chart.py) | Model a sample org chart as a folder/project tree and justify the boundaries |
| [exercises/exercise-03-gcloud-configurations.py](./03-exercises/exercise-03-gcloud-configurations.py) | Drive three named `gcloud` configurations (`dev`/`prod`/`admin`) and switch between them |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-terraform-landing-zone.md](./04-challenges/challenge-01-terraform-landing-zone.md) | Provision a three-folder, five-project landing zone in Terraform with budgets armed first |
| [quiz.md](./05-quiz.md) | 13 questions with an answer key |
| [homework.md](./06-homework.md) | Six problems applying the week's concepts |
| [mini-project/README.md](./07-mini-project/00-overview.md) | Full spec for the foundational landing-zone module (Weeks 02–04 extend this) |

## The "budget armed" promise

C18 uses a small recurring marker in every lab that touches a real project:

```
budget: armed · 3 thresholds (50/90/100%) · notify: pubsub://billing-alerts · channel: #gcp-cost
```

If you cannot show that line — a budget with threshold rules and a notification channel — you do not get to create compute. We treat an un-budgeted project the way C9 treats a build warning: as a bug. The point of Week 1 is to make "budget armed before anything else" an automatic reflex.

## A note on cost and the free trial

Everything in Week 1 runs inside the GCP \$300 free trial. The hierarchy objects (organizations, folders, projects, billing budgets) are **free**. Pub/Sub topics and a single Cloud Function for alert routing fall inside the always-free tier at the volume you will use. The only deliberate spend is in the challenge, where you may trigger a real ~\$1 charge to prove the 50% alert fires — and that is optional; the lab shows you how to fake the threshold with the Budget API instead.

When you finish the mini-project, the **teardown gate** is mandatory. `terraform destroy` runs, and you confirm `gcloud projects list` shows your projects in the `DELETE_REQUESTED` state. We do not leave projects lying around. A landing zone you can stand up but cannot tear down is a liability, not an asset.

## Stretch goals

If you finish early and want to push further:

- Read the **Google Cloud Architecture Framework** security pillar on resource hierarchy: <https://cloud.google.com/architecture/framework/security>.
- Skim the **Cloud Foundation Toolkit** `project-factory` Terraform module — you will not use it this week, but seeing how Google packages the same idea is instructive: <https://github.com/terraform-google-modules/terraform-google-project-factory>.
- Reproduce one of the org-chart-to-tree mappings from Exercise 2 entirely in the Console, then `terraform import` it. Notice how much you learn about the real resource shape from the import.
- Read the **`gcloud` topic** help pages: `gcloud topic configurations` and `gcloud topic filters`. Most engineers never do; the ones who do are faster forever.

## Up next

Continue to **Week 2 — IAM, Service Accounts, and Workload Identity** once you have pushed the mini-project and confirmed your teardown. Week 2 builds the IAM baseline directly on the folder/project tree you stand up this week — so do not delete the Terraform; you will extend it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
