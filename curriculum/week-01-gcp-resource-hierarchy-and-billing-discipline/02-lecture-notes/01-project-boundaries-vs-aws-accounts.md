# Lecture 1 — Project Boundaries vs. AWS Accounts: Where GCP's Isolation Primitive Is Stronger, and Where It Is Weaker

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can describe the four-node GCP resource hierarchy and what each node is *for*, contrast the GCP project boundary against the AWS account boundary with concrete examples of where each wins, and create a folder/project tree from the CLI and from Terraform.

If you only remember one thing from this lecture, remember this:

> **In AWS, the account is the blast radius, the billing unit, and the IAM trust boundary, all fused into one object. In GCP, those three concerns are split: the project is the resource container, the billing account is the payment object, and IAM policy attaches at any node of the hierarchy. The whole week is a consequence of that split.**

You are coming from AWS (or you should pretend you are, because most of your future teammates will be). The single most expensive mistake an AWS engineer makes in their first month on GCP is assuming "project == account." It does not. Let's build the right mental model from the root down.

---

## 1. The four nodes of the hierarchy

GCP arranges everything you own into a strict tree. There are exactly four kinds of node:

```
Organization  (acme.com)                         ← the root, one per identity domain
│
├── Folder  (bootstrap)                           ← optional grouping nodes
│   └── Project  (acme-tf-state-prod)             ← the isolation unit
│       └── Resource  (a GCS bucket)              ← the leaf: VMs, buckets, topics...
│
├── Folder  (shared)
│   ├── Project  (acme-shared-vpc-host)
│   └── Project  (acme-logging)
│
└── Folder  (workloads)
    ├── Folder  (dev)
    │   └── Project  (acme-api-dev)
    └── Folder  (prod)
        └── Project  (acme-api-prod)
```

| Node | What it is | Carries IAM? | Carries org policy? | Holds resources? |
|------|-----------|:---:|:---:|:---:|
| **Organization** | Root of the tree; one per Cloud Identity / Workspace domain | yes | yes | no |
| **Folder** | Grouping node; can nest | yes | yes | no |
| **Project** | The isolation unit; the thing API calls target | yes | yes | **yes** |
| **Resource** | A bucket, VM, topic, dataset | (some) | no | n/a (it *is* the resource) |

Two structural facts fall out of this table immediately:

1. **Only projects hold resources.** You cannot put a VM "in a folder." The folder is purely organizational — a place to attach IAM and org policy and to group projects. This trips up AWS engineers who think of an Organizational Unit (OU) as something you deploy into.
2. **IAM and org policy flow *down* the tree.** A role granted at the organization node is inherited by every folder, project, and resource beneath it. A role granted on a folder is inherited by every project in it. This is the load-bearing security property of the hierarchy, and it is the reason folder placement is a security decision, not a filing decision.

---

## 2. The organization node and why you need Cloud Identity

The organization (org) node is the root. You get **exactly one** per Cloud Identity or Google Workspace domain. If your company is `acme.com`, you verify ownership of `acme.com` through Cloud Identity (the free tier is fine) and GCP creates an organization node named `acme.com`.

Why does this matter on day one?

- **Without an org node, you have no place to hang org-wide IAM or org policy.** Projects created by a bare `@gmail.com` account are "orphan" projects with no parent organization. They work, but you cannot apply a `constraints/compute.requireOsLogin` org policy across all of them, and you cannot grant `roles/resourcemanager.folderAdmin` at a root that does not exist. For a course, an orphan project is survivable. For a company, it is a non-starter.
- **The org node is the boundary that defines "your GCP."** Everything inside it is governed by your policies; everything outside it is someone else's.

The AWS analogue is the **management account** (formerly "master account") of an AWS Organization. But note the asymmetry: in AWS the management account is itself a full account that can hold resources (and famously *should not*, for blast-radius reasons). The GCP organization node holds no resources at all. It is purely a policy anchor. That is cleaner.

> **Action item for the week:** If you have a domain, set up free Cloud Identity and get a real org node — the challenge and mini-project are far more realistic with one. If you only have a `@gmail.com`, you can still complete every lab with orphan projects; we flag the two places where the org node matters.

---

## 3. The project: GCP's true isolation primitive

The **project** is where the real work happens. Every resource lives in exactly one project. Every API call is made *in the context of* a project. Every quota is (mostly) scoped to a project. Billing is attributed per project. IAM bindings, while inheritable from above, are most often written at the project.

A project has three identifiers, and confusing them is a rite of passage:

| Identifier | Example | Properties |
|-----------|---------|-----------|
| **Project ID** | `acme-api-prod-7f3a` | You choose it. Globally unique across all of GCP. **Immutable.** 6–30 chars. The thing every `gcloud --project` and API call uses. |
| **Project number** | `849302157640` | GCP assigns it. Globally unique. Immutable. Used in some IAM member strings and service-agent identities. |
| **Display name** | `ACME API (prod)` | Human-friendly. Mutable. Not unique. Shown in the console picker. |

Three hard rules you will internalize this week:

1. **The project ID is permanent.** You cannot rename it. If you typo it, you delete the project and start over. This is why teams adopt a naming convention (`<org>-<system>-<env>-<suffix>`) and often append a short random suffix to dodge the global-uniqueness collision.
2. **A deleted project is soft-deleted for 30 days.** `gcloud projects delete` moves it to `DELETE_REQUESTED`. You can `gcloud projects undelete` it within ~30 days. After that it is gone, and — critically — the project ID is **not** recycled back into the global pool quickly. Plan around it.
3. **Projects are cheap and disposable on purpose.** A new project costs nothing until you put resources in it. The intended GCP pattern is *many small projects*, not a few big ones. This is the opposite of the instinct most engineers bring from a single shared dev environment.

---

## 4. Folders: the org-design tool

Folders sit between the org and projects, and they can nest (up to a documented depth — 10 levels as of 2026, which you will never approach). A folder does two jobs:

1. **It groups projects** so humans can find them and so you can apply IAM/org policy to a whole subtree at once.
2. **It is an inheritance boundary.** Grant `roles/owner` on the `workloads/dev` folder to the dev team, and they own every project under it — present and future — without you touching each project.

There are three common ways to slice folders, and the choice has consequences:

### By environment (dev / staging / prod)

```
workloads/
├── dev/      → dev team has broad access; relaxed org policy
├── staging/  → CI service accounts deploy here
└── prod/     → tight access; strict org policy; change control
```

**Pro:** Environment is the axis along which *policy* most naturally differs — you want `compute.requireShieldedVm` enforced in prod, maybe relaxed in dev. **Con:** A team that owns three systems has its resources scattered across three env folders.

### By team / business unit

```
workloads/
├── payments/   → payments team owns everything inside
├── search/     → search team owns everything inside
└── platform/   → platform team
```

**Pro:** Ownership and billing attribution are crisp. **Con:** Environment-level policy (strict prod, relaxed dev) now has to be applied per project or via a sub-folder, which reintroduces the env axis anyway.

### Hybrid (team, then environment)

```
workloads/
├── payments/
│   ├── dev/
│   └── prod/
└── search/
    ├── dev/
    └── prod/
```

This is what most mature orgs land on, and what the mini-project models. You get team ownership at the top and environment policy at the leaf. The cost is depth, and depth is free.

> **The rule that keeps you out of a corner:** *folders are for policy and ownership, not for filing.* If a folder boundary does not change who has access or what org policy applies, it is probably noise. Every folder in your tree should be defensible as "the set of projects that share this exact security posture and this exact owner."

---

## 5. The AWS contrast, head-on

Now the part you came for. Here is the mapping AWS engineers reach for, and where it is right and wrong.

| AWS concept | Naive GCP "equivalent" | Reality |
|-------------|------------------------|---------|
| AWS Organization | GCP Organization | Close. Both are the root policy anchor. |
| Organizational Unit (OU) | Folder | Close, but folders can hold IAM directly and are lighter weight. |
| **AWS Account** | **Project** | **This is the dangerous one. They are not equivalent.** |
| IAM (account-scoped) | IAM (hierarchy-scoped) | Fundamentally different trust model. |
| Consolidated Billing | Billing account | Close, covered in Lecture 2. |

The crux is the account-vs-project row. Let's be precise about where each isolation primitive wins.

### Where the GCP project boundary is STRONGER

1. **Projects are cheap, instant, and disposable.** Creating an AWS account historically meant a support-ticket-flavored process, a root email address, and minutes-to-hours of provisioning. (AWS has improved this with Control Tower / Account Factory, but it is still heavier.) A GCP project is a single API call that returns in seconds, costs nothing, and is deleted with one command. This makes the "one project per service per environment" pattern *practical* in GCP in a way "one account per service per environment" is painful in AWS. More boundaries, more cheaply, is a real security win.

2. **Policy inheritance is a first-class, clean tree.** In GCP, an IAM role or org-policy constraint set at a folder is *automatically* inherited by every project beneath it, including projects created later. AWS SCPs (Service Control Policies) do attach to OUs and inherit, but AWS IAM *identities* do not inherit down the org tree the same way — IAM users/roles are account-local. GCP's "grant once at the folder, applies everywhere below, forever" is genuinely cleaner for the common case of "the platform team should be able to read logs in every project."

3. **The project ID is a global, stable handle.** Every resource everywhere is addressable as `projects/<id>/...`. There is no per-account endpoint or per-region account quirk to thread through. Cross-project references (a service account in project A granted access to a bucket in project B) are first-class and do not require the cross-account `sts:AssumeRole` dance.

4. **Quota and billing attribution come for free at the project.** Because the project is the unit of both, you get per-project cost and per-project quota without erecting an account per cost center. In AWS you often spin up an account *specifically* to get clean cost attribution; in GCP a project (or even a label) does that.

### Where the GCP project boundary is WEAKER

1. **The control plane is more shared than an AWS account's.** An AWS account is a very hard wall: a compromised IAM role in account A simply cannot enumerate or touch resources in account B without an explicit cross-account trust. In GCP, all your projects sit under one organization on one shared control plane, and a sufficiently privileged principal at the org or folder level can reach across every project beneath it. The hierarchy that makes inheritance convenient (point 2 above) is the same hierarchy that makes a high-level IAM grant *enormously* powerful. An org-level `roles/owner` is a god key over everything. AWS's account wall has no equivalent single key. **This is the single most important asymmetry: GCP trades a harder per-unit wall for a more convenient shared tree, and you must defend the top of that tree accordingly.**

2. **Quota lives at the project (and sometimes spans regions oddly).** Because quota is per-project, "noisy neighbor" isolation *within* a project is weak — two workloads in the same project compete for the same Compute Engine CPU quota in a region. In AWS, two workloads in two accounts have independent service quotas. The GCP answer is "use more projects," which is cheap (point 1), but you have to *remember* to, and a team that crams everything into one project rediscovers quota contention the hard way.

3. **Some services have organization-wide or shared-fate behavior.** A few resources and quotas are genuinely org- or billing-account-scoped, not project-scoped (certain API rate limits, some allow-listing, billing budgets themselves). The clean "project is my blast radius" story has exceptions you must learn case by case.

4. **Default networking and service agents create implicit cross-project surface.** Google-managed service agents, default service accounts, and shared VPC host/service-project relationships create trust edges that are easy to under-appreciate. A shared VPC host project failure is a multi-service-project failure. (We deal with this properly in Week 3.)

> **The one-sentence summary to put in your notes:** *GCP gives you a cheaper, more numerous boundary (the project) inside a more convenient but more shared governance tree; AWS gives you a heavier, harder boundary (the account) with weaker built-in inheritance. Neither is "more secure" in the abstract — they fail differently, and you defend them differently.*

---

## 6. The seven `gcloud` muscle-memory commands

You will type these every day for 15 weeks. Learn them now, by hand, until they are reflex.

```bash
# 1. Authenticate (opens a browser; stores credentials).
gcloud auth login
gcloud auth application-default login   # for client libraries / Terraform

# 2. Manage named configurations (Exercise 3 lives here).
gcloud config configurations list
gcloud config configurations create dev
gcloud config configurations activate dev
gcloud config set project acme-api-dev

# 3. Projects.
gcloud projects list
gcloud projects create acme-api-dev --folder=123456789012
gcloud projects describe acme-api-dev
gcloud projects delete acme-api-dev          # soft-delete, 30-day window

# 4. Organizations and folders (resource-manager).
gcloud organizations list
gcloud resource-manager folders list --organization=ORG_ID
gcloud resource-manager folders create --display-name=workloads --organization=ORG_ID

# 5. Billing.
gcloud billing accounts list
gcloud billing projects link acme-api-dev --billing-account=0X0X0X-0X0X0X-0X0X0X
gcloud billing projects describe acme-api-dev

# 6. Asset inventory (validation in the challenge).
gcloud asset search-all-resources --scope=organizations/ORG_ID
gcloud asset search-all-iam-policies --scope=folders/FOLDER_ID

# 7. Services (enable APIs before you use them).
gcloud services list --enabled
gcloud services enable compute.googleapis.com --project=acme-api-dev
```

A few notes that save you an afternoon:

- **`--format` and `--filter` are everywhere.** `gcloud projects list --format="value(projectId)" --filter="parent.id=FOLDER_ID"` is how you script. Read `gcloud topic filters` and `gcloud topic formats` once.
- **`--log-http` is the best teacher.** Run any command with `--log-http` and watch the actual REST calls. This is how you learn what a resource really looks like before you write the Terraform for it.
- **Almost every command takes `--project`, but the active config supplies a default.** This is exactly why named configurations (Exercise 3) matter: the difference between "delete the dev bucket" and "delete the prod bucket" is one active config.

---

## 7. Creating the tree from the CLI

Before Terraform, do it once by hand so you know what the resources are. Assume you have an org ID and a billing account.

```bash
ORG_ID=123456789012
BILLING=0X0X0X-0X0X0X-0X0X0X

# Top-level folders.
gcloud resource-manager folders create --display-name=bootstrap --organization=$ORG_ID
gcloud resource-manager folders create --display-name=shared    --organization=$ORG_ID
gcloud resource-manager folders create --display-name=workloads --organization=$ORG_ID

# Grab the workloads folder ID (note: this is the numeric ID, not the name).
WORKLOADS=$(gcloud resource-manager folders list --organization=$ORG_ID \
  --filter="displayName=workloads" --format="value(name)" | cut -d/ -f2)

# A project under workloads. The ID must be globally unique — append a suffix.
gcloud projects create acme-api-dev-7f3a --folder=$WORKLOADS \
  --name="ACME API (dev)"

# Link billing — until you do this, you cannot enable most APIs.
gcloud billing projects link acme-api-dev-7f3a --billing-account=$BILLING

# Enable an API you'll actually use.
gcloud services enable compute.googleapis.com --project=acme-api-dev-7f3a
```

Notice the ordering dependency: **folder → project → link billing → enable APIs**. You cannot enable a billable API on an unlinked project. This ordering becomes a dependency graph in Terraform, and getting it wrong is the most common first-week Terraform error.

---

## 8. The same tree in Terraform

Here is the minimal, correct Terraform for one folder and one project with its API enabled. This is the seed of the mini-project.

```hcl
terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  # No default project: org-level resources don't belong to one.
  billing_project       = var.billing_quota_project
  user_project_override = true
}

variable "org_id" {
  type        = string
  description = "Numeric organization ID."
}

variable "billing_account" {
  type        = string
  description = "Billing account ID, format XXXXXX-XXXXXX-XXXXXX."
}

variable "billing_quota_project" {
  type        = string
  description = "Project used for quota/billing on org-level API calls."
}

resource "google_folder" "workloads" {
  display_name = "workloads"
  parent       = "organizations/${var.org_id}"
}

resource "google_project" "api_dev" {
  name            = "ACME API (dev)"
  project_id      = "acme-api-dev-7f3a"
  folder_id       = google_folder.workloads.name # "folders/123..."
  billing_account = var.billing_account
  # deletion_policy defaults to PREVENT in provider v6+; set to DELETE for labs.
  deletion_policy = "DELETE"
}

resource "google_project_service" "compute" {
  project = google_project.api_dev.project_id
  service = "compute.googleapis.com"

  # Don't let `terraform destroy` leave the API enabled-but-orphaned.
  disable_on_destroy = true
}

output "project_id" {
  value = google_project.api_dev.project_id
}
```

Two production-shop notes you will not find in the quickstart:

- **`deletion_policy = "DELETE"`** is set deliberately for *labs*. The provider defaults to `PREVENT` in v6+ precisely so you do not nuke a real project by running `terraform destroy` from the wrong directory. In the mini-project we make the teardown explicit and gated; in real prod you keep `PREVENT` and delete by hand.
- **`user_project_override` + `billing_project`** matters because some org-level API calls need a project to bill the API *call* against (not the resource). The "quota project" confusion is a classic week-one footgun; the provider docs cover it under "User project override."

---

## 9. The bootstrap chicken-and-egg

There is one problem you must confront before Week 4: **where does the Terraform state live, and who creates the project that holds it?**

You want remote state in a GCS bucket. The bucket lives in a project. That project should itself be managed by Terraform. But Terraform cannot store its state in a bucket that does not exist yet, in a project that does not exist yet, that Terraform is supposed to create.

The standard resolution, which the mini-project uses:

1. **Bootstrap once with local state.** A tiny `bootstrap/` Terraform config, run with a *local* backend, creates the `bootstrap` folder, a `*-tf-state` project, and a versioned GCS bucket.
2. **Migrate state into that bucket.** Add the `backend "gcs"` block pointing at the bucket you just made, run `terraform init -migrate-state`, and commit. The bootstrap config now manages its own state remotely.
3. **Everything else uses the bucket from the start.** All subsequent layers (`shared/`, `workloads/`) declare the GCS backend on day one.

This is the single most important structural idea in the mini-project, and it is the reason the landing zone has a `bootstrap/` folder at all. We walk through it step by step in the mini-project README.

---

## 10. Recap

You should now be able to:

- Draw the org → folder → project → resource tree and say what each node is for.
- Explain that IAM and org policy inherit *down* the tree, and that this is a security property.
- Name three identifiers of a project and state which are immutable.
- Argue, with examples, where the GCP project boundary beats the AWS account boundary (cheap, numerous, clean inheritance, global handles) and where it loses (shared control plane, project-scoped quota contention, org-wide god keys).
- Run the seven `gcloud` command families from memory.
- Create a folder and a project from the CLI in the right order, and the same from Terraform.
- Explain the bootstrap chicken-and-egg and how a `bootstrap/` layer with local-then-migrated state resolves it.

Next up: the billing model and how a budget alert finds its way to Slack before it finds your CTO. Continue to [Lecture 2 — Billing Accounts and Budget Alert Routing](./02-billing-accounts-and-budget-alert-routing.md).

---

## References

- *Resource hierarchy* — Google Cloud: <https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy>
- *Creating and managing projects*: <https://cloud.google.com/resource-manager/docs/creating-managing-projects>
- *Creating and managing folders*: <https://cloud.google.com/resource-manager/docs/creating-managing-folders>
- *IAM policy inheritance*: <https://cloud.google.com/iam/docs/resource-hierarchy-access-control>
- *`google_project` resource* — Terraform: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project>
- *Terraform on Google Cloud best practices*: <https://cloud.google.com/docs/terraform/best-practices-for-terraform>
- *AWS Organizations vs. GCP resource hierarchy* (Google migration guide): <https://cloud.google.com/architecture/migration-from-aws-get-started>
