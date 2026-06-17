# Week 4 — Resources

Every resource on this page is **free**. The HashiCorp and OpenTofu docs are free. The Terraform Registry is free to browse. Google Cloud documentation is free without an account. The Terragrunt docs (Gruntwork's open-source tool) are free. The Cloud Foundation Toolkit and Config Connector are open-source on GitHub. No paywalled books are linked; where a book is genuinely the best treatment of a topic (Brikman's *Terraform: Up & Running*) it is named, and the freely available portions are pointed at, but the lectures never require it.

A note on **Terraform vs. OpenTofu**: in 2026 the two are still drop-in compatible for everything in this course. HashiCorp's docs are more complete; OpenTofu's registry and docs are catching up fast. Read the HashiCorp docs for *concepts* and run whichever binary your shop standardized on. Where a feature diverges (OpenTofu's state encryption, HashiCorp's HCP integration) the lecture says so.

## Required reading (work it into your week)

- **Terraform — "What is Terraform" / language overview** — the conceptual baseline; read it even if you have written Terraform before, for the state-vs-config framing:
  <https://developer.hashicorp.com/terraform/intro>
- **Terraform — "Backends: GCS"** — the exact `backend "gcs"` configuration, bucket requirements, and the locking note. This is the single most-cited page in Lecture 1:
  <https://developer.hashicorp.com/terraform/language/backend/gcs>
- **Terraform — "State: remote state and locking"** — why state must be remote and shared, and how locking prevents concurrent corruption:
  <https://developer.hashicorp.com/terraform/language/state/remote>
- **Terraform — "`for_each`"** — the canonical reference for the iteration pattern we lean on all week:
  <https://developer.hashicorp.com/terraform/language/meta-arguments/for_each>
- **Terraform — "`count`"** — and, critically, the "When to Use `for_each` Instead of `count`" callout on this page:
  <https://developer.hashicorp.com/terraform/language/meta-arguments/count>
- **Terraform — "Modules: creation and structure"** — the `main.tf`/`variables.tf`/`outputs.tf` convention and the module composition guidance:
  <https://developer.hashicorp.com/terraform/language/modules/develop>
- **Google provider — registry docs** — the `google` and `google-beta` provider reference. Bookmark this; you will live in it. Note the per-resource "this resource is in the `google-beta` provider" banners:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs>
- **Google provider — "Using the `google-beta` provider"** — the official guide to when and how to opt into beta resources:
  <https://registry.terraform.io/providers/hashicorp/google-beta/latest/docs/guides/provider_versions>
- **Terragrunt — "Quick start" and "Keep your backend configuration DRY"** — the two pages that justify why we add Terragrunt at all:
  <https://terragrunt.gruntwork.io/docs/getting-started/quick-start/>
- **Cloud Build — "Building repositories from GitHub" and "Creating triggers"** — how the PR plan-check trigger is wired:
  <https://cloud.google.com/build/docs/automating-builds/github/build-repos-from-github>

## Authoritative deep dives

- **HashiCorp — "Terraform recommended practices"** — HashiCorp's own opinionated guide to repo structure, environment separation, and the workflow. The closest thing to an official "how a team should run Terraform":
  <https://developer.hashicorp.com/terraform/cloud-docs/recommended-practices>
- **Google Cloud — "Best practices for using Terraform"** — Google's GCP-specific Terraform guidance: state in GCS, one project per state, module layout, the `google-beta` rule. Read this end-to-end; it is short and dense:
  <https://cloud.google.com/docs/terraform/best-practices/general-style-structure>
- **Google Cloud — "Google Cloud Terraform best practices" (the operations companion)** — covers drift, plan review, CI, and the policy gate at the level this week teaches:
  <https://cloud.google.com/docs/terraform/best-practices-for-terraform>
- **Gruntwork — "How to manage Terraform state"** (the blog series that became the book) — the canonical explanation of why remote state and locking matter, with the failure modes spelled out:
  <https://blog.gruntwork.io/how-to-manage-terraform-state-28f5697e68fa>
- **Gruntwork — "Terraform tips & tricks: loops, if-statements, and gotchas"** — the definitive `count`-vs-`for_each` write-up, including the "do not use `count` for things you will reorder" warning:
  <https://blog.gruntwork.io/terraform-tips-tricks-loops-if-statements-and-gotchas-f739bbae55f9>
- **Yevgeniy Brikman — *Terraform: Up & Running* (3rd ed.)** — the book. Chapters 3 (state), 4 (modules), 5 (loops and conditionals), and 8 (production-grade code) map directly onto this week. Paid, but the best single text on operating Terraform. The author's blog (above) covers the load-bearing chapters for free:
  <https://www.terraformupandrunning.com/>
- **HashiCorp — "Manage resource drift"** — the official tutorial on detecting and reconciling drift, including `plan -refresh-only` and `-detailed-exitcode`:
  <https://developer.hashicorp.com/terraform/tutorials/state/resource-drift>

## Official docs you will keep open

- **Terraform — `backend` block reference**: <https://developer.hashicorp.com/terraform/language/backend>
- **Terraform — `terraform init` (including `-migrate-state`)**: <https://developer.hashicorp.com/terraform/cli/commands/init>
- **Terraform — `terraform plan` (including `-detailed-exitcode` and `-out`)**: <https://developer.hashicorp.com/terraform/cli/commands/plan>
- **Terraform — `terraform import` and `import` blocks**: <https://developer.hashicorp.com/terraform/language/import>
- **Terraform — variable validation blocks**: <https://developer.hashicorp.com/terraform/language/values/variables#custom-validation-rules>
- **Terraform — `terraform show -json` (machine-readable plan output)**: <https://developer.hashicorp.com/terraform/cli/commands/show>
- **Terraform — provider `required_providers` and version constraints**: <https://developer.hashicorp.com/terraform/language/providers/requirements>
- **Google provider — `google_storage_bucket`** (the state bucket): <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket>
- **Google provider — `google_compute_subnetwork`** (the `for_each` exercise target): <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_subnetwork>
- **Google provider — `google_project` and `google_project_service`**: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project>

## Terragrunt

- **Terragrunt — full documentation home**: <https://terragrunt.gruntwork.io/docs/>
- **Terragrunt — `remote_state` block** (auto-generates the backend config): <https://terragrunt.gruntwork.io/docs/reference/config-blocks-and-attributes/#remote_state>
- **Terragrunt — `generate` block** (writes the provider block into each module): <https://terragrunt.gruntwork.io/docs/reference/config-blocks-and-attributes/#generate>
- **Terragrunt — `include` and inheritance** (the parent `terragrunt.hcl` pattern): <https://terragrunt.gruntwork.io/docs/features/include/>
- **Terragrunt — `dependency` and `dependencies`** (wire one module's outputs into another's inputs): <https://terragrunt.gruntwork.io/docs/reference/config-blocks-and-attributes/#dependency>
- **Terragrunt — `run-all`** (apply/destroy a whole tree, and its dependency-ordering caveats): <https://terragrunt.gruntwork.io/docs/reference/cli-options/#run-all>

## Config Connector and Cloud Foundation Toolkit

- **Config Connector — overview** (manage GCP resources as Kubernetes CRDs): <https://cloud.google.com/config-connector/docs/overview>
- **Config Connector — "How Config Connector works"** (the reconciliation model that makes it different from a CI `apply`): <https://cloud.google.com/config-connector/docs/concepts/overview>
- **Config Connector — resource reference** (which GCP resources have CRDs): <https://cloud.google.com/config-connector/docs/reference/overview>
- **Cloud Foundation Toolkit — home**: <https://cloud.google.com/docs/terraform/blueprints/terraform-blueprints>
- **CFT — `terraform-google-modules` org on GitHub** (the blessed modules: project-factory, network, kubernetes-engine, iam, and dozens more): <https://github.com/terraform-google-modules>
- **CFT — `terraform-google-network` module** (the one Lecture 2 compares your hand-rolled `vpc` module against): <https://github.com/terraform-google-modules/terraform-google-network>
- **CFT — `terraform-google-project-factory`** (the project-bootstrap module CFT is best-known for): <https://github.com/terraform-google-modules/terraform-google-project-factory>
- **Config Controller** (Google-managed Config Connector + Policy Controller, the "landing zone as a service" option): <https://cloud.google.com/anthos-config-management/docs/concepts/config-controller-overview>

## Plan review, drift, and CI

- **Cloud Build — `cloudbuild.yaml` schema** (the build-config reference): <https://cloud.google.com/build/docs/build-config-file-schema>
- **Cloud Build — connecting a GitHub repo and the 2nd-gen GitHub host**: <https://cloud.google.com/build/docs/automating-builds/github/connect-repo-github>
- **Cloud Build — Workload Identity / service-account config for triggers** (no key files): <https://cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts>
- **GitHub REST API — "Create an issue comment"** (the call the PR-comment script makes): <https://docs.github.com/en/rest/issues/comments#create-an-issue-comment>
- **Atlantis** (the open-source PR-automation server that productionizes what Exercise 3 builds by hand): <https://www.runatlantis.io/>
- **HashiCorp — "Recommended patterns: a CI/CD workflow"** (plan on PR, apply on merge): <https://developer.hashicorp.com/terraform/tutorials/automation/automate-terraform>

## Talks worth watching (all free, no account)

- **HashiConf — "Terraform at scale" sessions** on the HashiCorp YouTube channel — search "HashiConf Terraform modules at scale". The module-library-plus-environments pattern is the recurring theme.
- **Yevgeniy Brikman — "Reusable, composable, battle-tested Terraform modules"** (a recorded conference talk; the live demo of `for_each` modules is the clearest one available):
  search YouTube for "Brikman reusable Terraform modules".
- **Google Cloud Tech — "Infrastructure as code on Google Cloud with Terraform"** (the official GCP intro, useful for the provider-specifics): search YouTube for "Google Cloud Terraform infrastructure as code".
- **Gruntwork — "Terragrunt: keep your Terraform code DRY"** — the maintainers' own walkthrough of the `envs/` pattern: search YouTube for "Gruntwork Terragrunt DRY".

## How to use this resource list

The lectures cite specific URLs from this page at decision points. The links you should read end-to-end *this week* are:

1. **Terraform — "Backends: GCS"** (Required reading). You wire this on Monday; read it first.
2. **Google Cloud — "Best practices for using Terraform"** (Authoritative deep dives). Short, dense, GCP-specific. Do not skip.
3. **Gruntwork — "Terraform tips & tricks: loops..."** (Authoritative deep dives). The definitive `count`-vs-`for_each` treatment; decisive for Exercise 2.
4. **Terragrunt — "Keep your backend configuration DRY"** (Required reading). You wire this Wednesday; read it Tuesday night.

The rest are reference material — bookmark and return to them when a specific question arises. Even senior engineers keep the Google provider registry docs open in a tab all day.

---

*Bookmarks decay. If a link rots, search the title — these are all canonical pieces and they reappear on the same authors' new homes. The Terraform Registry, in particular, versions its docs; pin your reading to the provider version you actually run (`~> 6.0` for this course).*
