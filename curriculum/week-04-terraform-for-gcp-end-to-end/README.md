# Week 4 — Terraform for GCP, End-to-End

Welcome to **C18 · Crunch GCP**, Week 4 — the week the course stops being a tour and starts being a codebase. Week 1 gave you the resource hierarchy and a billing budget. Week 2 gave you IAM, service accounts, and Workload Identity Federation. Week 3 gave you the VPC, the subnets, Cloud NAT, and a hierarchical firewall policy. You provisioned all of it with Terraform, but you provisioned it the way most people write their first Terraform: one big `main.tf` per week, local state on your laptop, hard-coded project IDs, copy-pasted resource blocks, and a `terraform apply` you ran by hand on a Friday. That code worked. It is also a liability. This week we take the three weeks of ad-hoc HCL and refactor it into the thing a hiring manager actually wants to see: **a versioned module library with remote state, state locking, environment separation, and a plan-review gate that runs in CI**.

This is the last week of Phase 1, and it is the load-bearing one. Everything from Week 5 forward — the GKE cluster, the Cloud Run service, the Pub/Sub-to-BigQuery pipeline, the Spanner instance, the capstone — is provisioned *on top of* the module library you build this week. If you do Week 4 well, the next eleven weeks are `module "thing" { source = "../../modules/thing" }` and a clean `plan`. If you do it badly, you spend the next eleven weeks fighting drift, copy-pasting fixes across environments, and re-typing project IDs. The whole course pivots on this week. The `SYLLABUS.md` is explicit that the mini-projects compound; this is the one they compound *onto*.

The first thing to internalize is that **Terraform is not a provisioning tool, it is a reconciliation engine, and the state file is the contract**. When you run `terraform apply`, Terraform does not "create your VPC." It computes the difference between three things — the configuration you wrote (the desired state), the state file (what Terraform thinks exists), and the real cloud (what actually exists, fetched via a `refresh`) — and then issues the API calls that drag reality toward the configuration. The state file is the source of truth for *what Terraform believes it owns*. If that file lives on your laptop, then exactly one person can safely run `apply`, there is no audit trail, and a lost laptop is a lost cloud. The first lecture and the first exercise this week move that state into a GCS bucket with object-level locking so the whole team — and your CI system — can operate on the same cloud without racing each other into a corrupted state. This is not optional polish. A team that shares local state files over Slack is a team that will eventually `apply` two conflicting changes simultaneously and corrupt the state. We fix that on Monday.

The second thing to internalize is the title of Lecture 1, which is also the most important sentence in Phase 1: **"click in the console, then write Terraform" is a perfectly fine learning move in week one and a fireable offense by week six.** In your first week on any cloud you do not know the resource graph, you do not know which fields are required, and clicking through the console teaches you the shape of the thing faster than reading the provider docs. That is fine — *as long as you then codify it and let Terraform own it*. What is not fine, six weeks in, is "fixing" a production incident by clicking in the console and never reflecting the change back into HCL. That click creates **drift**: the real cloud no longer matches the state file, and the next `terraform apply` someone runs — possibly months later, possibly in the middle of a different change — will either revert your console fix (taking down the thing you fixed) or fail in a confusing way. Drift is how IaC shops get bitten, and the discipline that prevents it is a *plan-review workflow*: every change goes through a pull request, the `terraform plan` output is posted as a comment on that PR, a human reads the plan before it merges, and `apply` only runs from CI after merge. Lecture 1 builds the mental model; Exercise 3 and the mini-project wire the Cloud Build PR check that makes it real.

The third thing to internalize is that **good Terraform is mostly good *factoring*, and the two factoring tools you will use ten times a day are `for_each` and modules.** A junior engineer writes three near-identical `google_compute_subnetwork` blocks for three subnets. A senior engineer writes one block driven by `for_each = var.subnets` and a map variable. The difference is not aesthetics: the `for_each` version cannot drift between the three subnets (they are generated from one template), it adds a fourth subnet by adding one map entry instead of copy-pasting a block, and — critically — its plan is *readable* because the resources are addressed by a stable key (`google_compute_subnetwork.this["app"]`) rather than by a positional index that shifts when you reorder the list. Lecture 1 covers the `count`-versus-`for_each` decision in detail (short version: `for_each` almost always, `count` only for "zero or one of this thing"). Exercise 2 has you collapse a duplicated resource block into a `for_each`-driven module consumed by two environments. The mini-project makes you do it for real across `org-bootstrap`, `vpc`, and `iam-baseline`.

The fourth thing to internalize is that **environment separation is a code-organization problem with exactly two reasonable answers, and you should be able to defend the one you pick.** Answer one: plain Terraform workspaces and per-environment `.tfvars` files — simple, built-in, and it falls apart the moment `dev` and `prod` need different backends or different provider configs (which they always eventually do). Answer two: a directory per environment (`envs/dev`, `envs/prod`), each a thin root module that calls the shared modules with environment-specific inputs, with a tool like **Terragrunt** to keep the backend config and the provider config DRY across those directories. We teach Terragrunt this week because it is the de-facto standard in production GCP shops in 2026 and because it solves the one problem plain Terraform genuinely cannot: generating per-environment backend blocks without copy-paste. Lecture 1 is honest about the trade-off — Terragrunt is a wrapper, it adds a dependency, and a small shop can live without it — but the module-library-plus-`envs/`-directory pattern it enables is the pattern you will see at every GCP-using company you interview at. Lecture 2 then steps outside raw HCL entirely to ask the harder architectural question: **when do Config Connector and the Cloud Foundation Toolkit beat hand-written Terraform**, and when are they overkill you will regret adopting.

By Friday you will have a `modules/` directory with three production-grade, documented, input-validated modules; an `envs/dev` and an `envs/prod` that consume them through Terragrunt with remote GCS state and locking; and a Cloud Build trigger that runs `terraform plan` on every pull request and posts the plan as a PR comment. You will prove zero drift with a clean `plan` against both environments. That artifact — clean, reusable, documented HCL — is one of the three things the syllabus names as belonging on your portfolio. Build it like someone is going to read it, because someone is.

## Learning objectives

By the end of this week, you will be able to:

- **Operate** Terraform (or OpenTofu) against the `google` and `google-beta` providers with pinned versions, an explicit `required_providers` block, and a clean understanding of when a resource only exists in `google-beta` and why.
- **Migrate** local Terraform state into a GCS remote backend with object-level locking, using `terraform init -migrate-state`, and explain why the state file is the contract and why concurrent local applies corrupt it.
- **Structure** a Terraform repository as a `modules/` library plus per-environment root modules (`envs/dev`, `envs/prod`), and articulate the boundary between "what is a module input" and "what is hard-coded."
- **Refactor** a duplicated resource block into a `for_each`-driven module, choosing `for_each` over `count` for the right reasons (stable addressing, no positional-index churn, set/map semantics).
- **Wire** Terragrunt to keep backend and provider configuration DRY across environments, generating per-environment backend blocks from a single `terragrunt.hcl`.
- **Distinguish** acceptable click-then-codify (week one, learning the resource shape) from unacceptable click-ops (week six, fixing prod in the console and never reflecting it), and name the drift it causes.
- **Detect** drift with `terraform plan -detailed-exitcode` and a scheduled drift-check, and read a plan well enough to spot a destroy-and-recreate before it pages you.
- **Build** a plan-review workflow: a Cloud Build trigger on pull requests that runs `terraform plan` and posts the plan as a comment on the PR via the GitHub API, with `apply` gated behind merge.
- **Decide** when Config Connector (GCP resources as Kubernetes CRDs, reconciled in-cluster) or the Cloud Foundation Toolkit (Google's blessed landing-zone modules) is the right tool, and when raw HCL is simpler and more honest.
- **Tear down** a multi-environment Terraform estate cleanly with `terraform destroy` (or `terragrunt run-all destroy`), and verify the GCP projects are empty afterward.

## Prerequisites

- **Weeks 1 through 3** of C18 complete, with the deliverables in a Git repository you still have: the three-folder/five-project landing zone (Week 1), the Workload Identity Federation setup (Week 2), and the multi-region shared VPC (Week 3). This week *refactors* that code; you need it on disk.
- **Terraform 1.9+ or OpenTofu 1.8+** on your PATH. Run `terraform version` (or `tofu version`). Everything in this week works identically on both; we write `terraform` and you may read `tofu`. The `google` provider version we target is `~> 6.0`; `google-beta` likewise.
- **Terragrunt 0.60+** for the environment exercises and the mini-project. `terragrunt --version`. If you cannot install it, the lectures explain the plain-Terraform fallback, but the mini-project assumes Terragrunt.
- **`gcloud` authenticated** as a principal that can create GCS buckets and read/write the projects from Weeks 1–3. `gcloud auth application-default login` so Terraform picks up your credentials via Application Default Credentials.
- **A GitHub repository** (or a Cloud Source Repositories mirror) you can connect to Cloud Build. The PR-check exercise needs a real repo with real pull requests. A private repo is fine.
- **Workload Identity Federation from Week 2**, because the Cloud Build trigger should authenticate to GCP without a service-account key. If you skipped WIF, the exercise has a key-based fallback, but you will be undoing your own Week 2 work to use it.
- **A billing budget still armed from Week 1.** This week creates and destroys buckets and triggers, which are nearly free, but you will leave dev environments running between sessions. The budget is your safety net.

## Topics covered

- **The Terraform mental model, restated for production.** Configuration vs. state vs. real cloud; the `refresh`/`plan`/`apply` loop; why the state file is the contract; why two people running local `apply` is a data race.
- **The `google` and `google-beta` providers.** `required_providers` with version pins, the `~>` pessimistic constraint operator, provider aliases, the `project`/`region`/`zone` defaults, and the rule for when a resource is only in `google-beta` (new features land in beta first; you opt in per-resource, not globally).
- **Remote state in GCS with locking.** The `backend "gcs"` block, the state bucket (versioning on, uniform bucket-level access, a lifecycle rule), GCS object generation as the locking mechanism, `terraform init -migrate-state`, and why you bootstrap the state bucket with local state and then migrate.
- **Module structure.** The `main.tf`/`variables.tf`/`outputs.tf`/`versions.tf` convention, `variable` validation blocks, `output` values, the public/private boundary, the README-per-module discipline, and semantic versioning of modules via Git tags.
- **`for_each` and `count`.** Why `for_each` produces stable resource addresses and `count` produces fragile positional ones; the "zero or one" case where `count` wins; iterating maps vs. sets; `for_each` over a `toset(...)`; the `each.key`/`each.value` idiom; dynamic blocks driven by `for_each`.
- **Environment separation.** Workspaces vs. directory-per-environment; why workspaces fall down on differing backends; the `envs/dev` + `envs/prod` + shared `modules/` layout; Terragrunt's `generate` and `remote_state` blocks; `include` and `dependency` for DRY config and inter-module wiring.
- **Click-ops, drift, and plan review.** When click-then-codify is fine and when it is a fireable offense; what drift is and how it bites; `terraform plan -detailed-exitcode` for drift detection; the PR-review-then-CI-apply workflow; reading a plan for the destroy-and-recreate footgun.
- **Cloud Build PR checks.** A `cloudbuild.yaml` that runs `fmt -check`, `validate`, and `plan`; a Cloud Build trigger scoped to pull requests; posting the plan as a PR comment via the GitHub API; WIF auth from Cloud Build so there is no key.
- **Config Connector and the Cloud Foundation Toolkit.** Config Connector (GCP resources as Kubernetes CRDs reconciled by an in-cluster operator) — when in-cluster reconciliation beats a CI `apply`; the CFT modules (`terraform-google-modules/*`) — when Google's blessed modules save you a month and when they hide complexity you needed to see.
- **Teardown discipline.** `terraform destroy` per environment, `terragrunt run-all destroy` with `--terragrunt-ignore-dependency-order` caveats, verifying empty projects, and never leaving a `dev` environment billing overnight by accident.

## Weekly schedule

The schedule adds up to approximately **36 hours**. Treat it as a target, not a contract. Run your `apply`s early in a session, not in the last fifteen minutes — a half-applied Terraform run is the worst place to leave a cloud overnight.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Providers, remote state, locking; Exercise 1                |    2h    |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Tuesday   | Module structure, `for_each` vs `count`; Exercise 2         |    2h    |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Wednesday | Terragrunt, environments, drift & plan review; Exercise 3   |    2h    |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Thursday  | Config Connector & CFT; start the challenge                 |    1h    |    0h     |     2.5h   |    0.5h   |   1h     |     1h       |    0.5h    |     6.5h    |
| Friday    | Mini-project — modules + envs + PR check                    |    0h    |    0h     |     0h     |    0.5h   |   1h     |     3.5h     |    0.5h    |     5.5h    |
| Saturday  | Mini-project deep work, prove zero drift, teardown gate     |    0h    |    0h     |     0h     |    0h     |   0h     |     3.5h     |    0h      |     3.5h    |
| Sunday    | Quiz, review, polish the module READMEs                     |    0h    |    0h     |     0h     |    1h     |   0h     |     1.5h     |    0h      |     2.5h    |
| **Total** |                                                             | **9h**   | **8h**    | **4.5h**   | **3.5h**  | **5h**   | **13h**      | **2.5h**   | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Terraform/OpenTofu docs, the `google` provider registry, the Terragrunt docs, the Cloud Foundation Toolkit and Config Connector docs, and the GCS-backend and plan-review references |
| [lecture-notes/01-click-then-codify-drift-and-plan-review.md](./lecture-notes/01-click-then-codify-drift-and-plan-review.md) | The state model, remote state + locking, modules and `for_each`, Terragrunt environments, and the click-ops/drift/plan-review discipline that keeps IaC honest |
| [lecture-notes/02-config-connector-and-cloud-foundation-toolkit.md](./lecture-notes/02-config-connector-and-cloud-foundation-toolkit.md) | When Config Connector (GCP-as-CRDs) and the Cloud Foundation Toolkit (Google's blessed modules) beat raw HCL, and when they are overkill |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-gcs-remote-backend-with-locking.md](./exercises/exercise-01-gcs-remote-backend-with-locking.md) | Bootstrap a GCS state bucket and migrate local state into it with locking; verify the lock holds against a concurrent apply |
| [exercises/exercise-02-for-each-subnet-module.tf](./exercises/exercise-02-for-each-subnet-module.tf) | Refactor a triplicated subnet block into a `for_each`-driven module consumed by `dev` and `prod` |
| [exercises/exercise-03-cloudbuild-pr-plan-check.py](./exercises/exercise-03-cloudbuild-pr-plan-check.py) | A Python script (run from Cloud Build) that runs `terraform plan`, parses it, and posts the plan as a comment on the pull request |
| [challenges/README.md](./challenges/README.md) | Index of the challenge |
| [challenges/challenge-01-refactor-weeks-01-03-into-a-module-library.md](./challenges/challenge-01-refactor-weeks-01-03-into-a-module-library.md) | Refactor the Weeks 01–03 deliverables into `org-bootstrap`, `vpc`, and `iam-baseline` modules consumed by `envs/dev` and `envs/prod` via Terragrunt; prove zero drift |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the Week 04 Terraform module library — the canonical foundation all later weeks build on, with a teardown gate |
| [quiz.md](./quiz.md) | 13 questions on state, locking, `for_each`, Terragrunt, drift, plan review, Config Connector, and CFT, with an answer key |
| [homework.md](./homework.md) | Six practice problems for the week, with a rubric |

## The "clean plan" promise

Where Week 7 of C9 had the "build succeeded" contract, Week 4 of C18 has the **clean-plan contract**. A `terraform plan` that prints

```
No changes. Your infrastructure matches the configuration.
```

is the IaC equivalent of a green test suite. It means the configuration, the state file, and the real cloud all agree. Every mini-project this week — and every mini-project for the rest of the course — is graded with a fresh `plan` after `apply`, and if that plan is not clean, the work is not done. "It applied fine" is not the bar. "It applied, and a re-plan shows no changes" is the bar. A non-clean re-plan means your configuration is not actually what you deployed: you have a field Terraform recomputes every run, a resource that drifts on its own, or a dependency you did not express. Senior engineers chase a clean plan the way they chase a clean test run, and for the same reason — it is the only honest signal that the system is in the state you think it is.

## A note on what's not here

Week 4 is the Terraform-discipline week. It does **not** cover:

- **Terraform Cloud / HCP Terraform / Spacelift / env0 as managed backends.** All are real, all are fine, and all cost money the free trial does not cover. We use GCS for state and Cloud Build for the plan check because they are inside the GCP free tier and because they teach the primitives the managed products wrap. If your shop uses HCP Terraform, the concepts transfer one-to-one.
- **Sentinel / OPA / Conftest policy-as-code in depth.** We mention policy gates and wire one trivial `fmt`/`validate` gate, but full policy-as-code (a Rego library that blocks public buckets, enforces labels, caps machine sizes) is a Week 14 (security hardening) topic. This week's gate is human plan review plus the cheap automated checks.
- **Atlantis.** The open-source PR-automation server that does what our Cloud Build trigger does, with more features. We build the primitive ourselves so you understand what Atlantis automates; adopting Atlantis afterward is a one-afternoon swap.
- **Pulumi / CDK for Terraform / the SDK-based IaC tools.** Real, growing, and out of scope for a course whose substrate is HCL. The state and drift concepts transfer; the syntax does not.
- **Importing a large existing estate with `terraform import` / `import` blocks at scale.** We do one small import in passing. Industrial-scale brownfield import (a 200-resource account someone built by hand) is a specialized skill we point at in resources and leave for a dedicated week.

## Up next

Continue to **Week 5 — Compute Engine, instance groups, and managed VMs** once your Week 4 module library applies clean and tears down clean. Week 5 is the first week you deploy a real workload, and you deploy it by writing a `compute` module that lives in the `modules/` library you just built and consuming it from `envs/dev`. From here to the capstone, "provision X" means "write a module for X, wire it into the envs, open a PR, read the plan, merge." The muscle you build this week — *module first, remote state, read the plan, prove zero drift, tear it down* — is the muscle the rest of the course assumes you already have.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
