# Lecture 2 — Where Config Connector and the Cloud Foundation Toolkit beat raw HCL (and where they don't)

> **Reading time:** ~75 minutes. **Hands-on time:** ~45 minutes (you read a CFT module's source, write a Config Connector manifest, and decide which tool a scenario calls for).

Lecture 1 was about operating raw HCL well: state, locking, `for_each`, modules, Terragrunt, drift, plan review. This lecture steps up an altitude to the question a staff engineer asks in an architecture review: **should you be hand-writing this HCL at all?** There are two serious alternatives to "write your own Terraform modules," and both are GCP-native, both are real, and both are overkill in some situations and a month-saver in others. The two are **the Cloud Foundation Toolkit** (Google's blessed, open-source Terraform modules) and **Config Connector** (manage GCP resources as Kubernetes Custom Resources, reconciled by an in-cluster operator). Knowing when each beats raw HCL — and, just as important, when it does not — is the difference between an engineer who reinvents `terraform-google-network` for the fourth time and one who knows when reinventing it is actually the right call.

We cover: the Cloud Foundation Toolkit (what it is, what it gives you, the four modules you will actually use, and the "hidden complexity" trap); then Config Connector (the reconciliation model that makes it fundamentally different from a CI `apply`, when in-cluster reconciliation wins, and the operational cost); then a decision framework you can defend; then Config Controller, the managed option that ties them together.

## 2.1 — The Cloud Foundation Toolkit: Google's blessed modules

The **Cloud Foundation Toolkit (CFT)** is a collection of open-source Terraform modules maintained by Google under the `terraform-google-modules` GitHub organization. They are not a separate tool — they are *just Terraform modules*, published to the Terraform Registry, that you consume the same way you consume your own:

```hcl
module "network" {
  source  = "terraform-google-modules/network/google"
  version = "~> 9.0"

  project_id   = var.project_id
  network_name = "main"
  routing_mode = "GLOBAL"

  subnets = [
    {
      subnet_name   = "app"
      subnet_ip     = "10.10.0.0/20"
      subnet_region = "us-central1"
    },
    {
      subnet_name   = "data"
      subnet_ip     = "10.10.16.0/20"
      subnet_region = "us-central1"
    },
  ]

  secondary_ranges = {
    app = [
      { range_name = "pods", ip_cidr_range = "10.100.0.0/16" },
      { range_name = "svcs", ip_cidr_range = "10.101.0.0/20" },
    ]
  }
}
```

That single module call wraps `google_compute_network`, `google_compute_subnetwork` (with `for_each` internally), secondary ranges for GKE, routes, and optional firewall rules — dozens of resources you would otherwise hand-write. The CFT org has 50+ such modules. The four you will actually reach for in this course and in the field:

- **`terraform-google-project-factory`** — the one CFT is famous for. Creates a project, links a billing account, enables APIs, creates a default service account, and optionally sets up Shared VPC attachment — the entire Week 1 landing-zone "spawn a project" workflow in one module call. This is the strongest CFT module; project creation has a lot of fiddly required ordering (link billing *before* enabling APIs, enable `cloudresourcemanager` *before* anything else) and the module gets it right.
- **`terraform-google-network`** — the VPC + subnets + secondary ranges + routes bundle shown above. The module you will compare your own hand-rolled `vpc` module against (and you do, in the challenge).
- **`terraform-google-kubernetes-engine`** — a GKE cluster with Workload Identity, node pools, and the safe-upgrade defaults baked in. You meet this in Week 6.
- **`terraform-google-iam`** — IAM bindings at the org/folder/project/resource level with `for_each` over members, additive vs. authoritative modes handled correctly (the authoritative-vs-additive distinction is a classic IAM footgun the module spares you).

### What CFT actually buys you

Three concrete things:

1. **Encoded ordering and gotchas.** The project-factory module knows the billing-link-before-API-enable ordering, the "wait for the project to propagate before creating resources in it" sleep, and the IAM-additive-vs-authoritative distinction. These are hours of debugging you skip. The module is the accumulated scar tissue of thousands of GCP project creations.
2. **A stable, versioned API.** `version = "~> 9.0"` pins you to a tested release. Google upgrades the module across provider major versions and publishes an upgrade guide. You inherit that maintenance.
3. **A common vocabulary.** When you join a GCP shop and the repo calls `terraform-google-project-factory`, you already know its inputs. The modules are a lingua franca.

### The hidden-complexity trap

Here is the honest counterweight, and it is the reason this is a *lecture* and not a recommendation to "always use CFT." A CFT module hides complexity — that is its job — but hidden complexity is complexity you did not learn. Three specific traps:

- **You cannot debug what you do not understand.** When `terraform-google-network` produces a plan that wants to recreate a subnet, you need to read the module's source to understand why. If you never hand-wrote a VPC, you do not have the mental model to debug the module's behavior. **This is exactly why this course makes you hand-write the `vpc` module first (the challenge) and only then compare it to CFT.** You earn the right to use the abstraction by first building the thing it abstracts.
- **CFT modules are opinionated, and their opinions may not be yours.** The network module's default firewall rules, the project-factory's default service-account grants — these are Google's defaults, which lean toward "works for the common case," not "minimal for your specific security posture." A `roles/editor` grant that the module adds by default may be exactly what your security review flags. You must read the module's defaults, not assume them.
- **A CFT module is a dependency with its own release cadence.** When the `google` provider ships v7, you wait for CFT to release a v7-compatible module version before you can upgrade. For a fast-moving estate that wants the newest provider features, that lag is real friction. Your own module upgrades on your schedule.

The rule that falls out:

> **Use CFT for the well-trodden, high-gotcha paths (project creation, IAM bindings) where Google's scar tissue is worth more than your control. Hand-write the modules where your opinions matter (your specific VPC topology, your specific security baseline) or where you need to deeply understand the resource graph. Never use a CFT module you have not read the source of.**

In this course you hand-write `org-bootstrap`, `vpc`, and `iam-baseline` (the challenge and mini-project) precisely so you understand the resource graph. In a real job, you might swap your `org-bootstrap` for `project-factory` once you have proven you understand what it does — and keep your hand-rolled `vpc` because your topology is specific enough that the CFT module's generality is a liability.

### A worked look at `project-factory`'s ordering

To make "encoded ordering" concrete, here is the sequence the project-factory module gets right that a first-timer almost always gets wrong, in the order it must happen:

1. **Create the project under a parent** (org or folder). The `google_project` resource. If you skip the parent, the project lands in "No organization" and you cannot apply org policies to it.
2. **Link the billing account.** This must happen *before* you enable most APIs, because enabling a billable API on an unbilled project fails. A naive script enables APIs first and gets a confusing `FAILED_PRECONDITION`.
3. **Enable `cloudresourcemanager.googleapis.com` and `serviceusage.googleapis.com` first**, then everything else. These two are the bootstrap APIs; the others depend on them being on. Order matters even *within* API enablement.
4. **Wait for project propagation.** A freshly-created project is not immediately consistent across all GCP services. The module inserts a `time_sleep` (or a polling read) so that the next resource — a service account, a bucket — does not race the project into existence and fail with `NOT_FOUND`.
5. **Create the default service account and grant it the minimal roles**, additively, never `roles/owner`.

A first-timer hits steps 2, 3, and 4 as three separate confusing failures across an afternoon. The module encodes all of it. That is the value: not the lines of HCL saved, but the hours of `FAILED_PRECONDITION` debugging avoided. When you write your own `org-bootstrap` for the mini-project, you will hit some of these orderings yourself — and that is the point. You earn the judgment to decide *whether* to adopt project-factory by feeling the pain it absorbs.

### Pinning and upgrading a CFT module

A CFT module is pinned exactly like the provider — with `version`:

```hcl
module "project" {
  source  = "terraform-google-modules/project-factory/google"
  version = "~> 17.0"   # pin to a tested major; minors/patches flow in
  # ...
}
```

When you bump the major (`~> 17.0` to `~> 18.0`), you do it in its own PR, read the module's `CHANGELOG.md` and upgrade guide, run `terraform init -upgrade`, and treat a clean `plan` as the acceptance test — the same discipline as a provider major bump from Lecture 1. The difference from your own module is that *you do not control when the upgrade is available*: you wait for Google to ship an v18 module, which may lag a `google` provider v8 by weeks. For an estate chasing brand-new provider features, that lag is the cost of the convenience.

## 2.2 — Config Connector: GCP resources as Kubernetes CRDs

**Config Connector (KCC)** is a fundamentally different model from Terraform. Instead of a CLI that runs a plan-then-apply against the cloud, KCC is a **Kubernetes operator** that runs inside a GKE cluster and continuously reconciles GCP resources defined as **Custom Resources** (CRDs). You `kubectl apply` a YAML manifest describing a Pub/Sub topic, and the in-cluster operator creates and then *continuously maintains* that topic against the live GCP API.

A Config Connector manifest for a Pub/Sub topic looks like this:

```yaml
# A Pub/Sub topic, as a Kubernetes resource.
apiVersion: pubsub.cnrm.cloud.google.com/v1beta1
kind: PubSubTopic
metadata:
  name: events-ingest
  namespace: config-connector
  annotations:
    cnrm.cloud.google.com/project-id: "crunch-gcp-dev"
spec:
  messageRetentionDuration: "604800s"   # 7 days
```

And a GCS bucket:

```yaml
apiVersion: storage.cnrm.cloud.google.com/v1beta1
kind: StorageBucket
metadata:
  name: crunch-gcp-dev-artifacts
  namespace: config-connector
  annotations:
    cnrm.cloud.google.com/project-id: "crunch-gcp-dev"
spec:
  location: US-CENTRAL1
  uniformBucketLevelAccess: true
  versioning:
    enabled: true
```

You `kubectl apply -f topic.yaml`, and the operator creates the topic. You `kubectl get pubsubtopic events-ingest`, and you see its status — `READY`, with the live GCP state reflected back into the CR's `status` field. You `kubectl delete`, and (by default) the topic is deleted.

### The reconciliation model is the whole point

The difference that matters is not the YAML-vs-HCL syntax — it is the **execution model**:

- **Terraform reconciles when you run it.** Drift between runs is invisible until the next `plan`. If someone clicks a change in the console, Terraform does not notice until a human runs `plan` again. That is the entire reason Lecture 1 spent a section on scheduled drift detection — you have to *go look*.
- **Config Connector reconciles continuously.** The in-cluster operator watches both the desired state (the CR) and the actual state (the live GCP resource) and drives them together *on a loop*, every few minutes, forever. If someone clicks a change in the console that diverges from the CR, the operator **reverts it automatically** within minutes. Drift is self-healing.

That self-healing is the single biggest reason to choose Config Connector. If your operational model is "the cluster is the source of truth and nothing should diverge from it, ever, without going through GitOps," then continuous reconciliation enforces that automatically, where Terraform requires you to *schedule a check and page on it*.

### When Config Connector wins

- **You already run a GKE platform and want GitOps for GCP resources alongside your workloads.** If your apps deploy via Argo CD or Flux from a Git repo, putting your GCP resources (the buckets, topics, and IAM the apps need) in the *same* Git repo and the *same* reconciliation loop is genuinely elegant. The Pub/Sub topic an app needs lives next to the app's Deployment, both reconciled by the same GitOps controller. There is no separate "run Terraform" step in the deploy.
- **You want continuous drift correction without building a scheduled drift-check.** The operator does for free what Lecture 1's nightly `plan -detailed-exitcode` job does by hand.
- **Application teams own their own GCP resources.** A team that already lives in `kubectl` and Kubernetes manifests can self-serve a bucket or a topic in a namespace you scoped for them, without learning Terraform and without you brokering every request. The namespace + RBAC model bounds what they can create.

### When Config Connector loses

Be equally honest about the costs:

- **It requires a running GKE cluster.** The operator lives in a cluster, so you are paying for and operating a Kubernetes control plane just to manage GCP resources. For a small estate, that is a wildly disproportionate dependency — you would stand up a whole GKE cluster to manage three buckets. Terraform needs no running infrastructure at all.
- **Bootstrap is circular and awkward.** The cluster that runs Config Connector is itself a GCP resource. You cannot manage the cluster that runs KCC *with* KCC (the same chicken-and-egg as the state bucket, but harder). You bootstrap the cluster with Terraform, then run KCC inside it. So you end up needing Terraform anyway for the foundation.
- **No `plan`.** This is the big one for the discipline Lecture 1 built. Terraform's `plan` shows you the full delta — including `forces replacement` on a stateful resource — *before* you apply. Config Connector reconciles continuously without a human-readable pre-apply diff of the same fidelity. You `kubectl apply` and the operator does what it does. For a destructive change to a stateful resource, the loss of the plan-review gate is a real safety regression. (You can mitigate with admission controllers and Policy Controller, but you are rebuilding the gate.)
- **The blast radius of a bad reconcile is continuous.** A Terraform mistake fires once, at apply, and stops. A Config Connector mistake — a misconfigured CR that the operator keeps trying to reconcile — fires every few minutes, forever, until you fix the CR. A `kubectl delete` of a `StorageBucket` CR with the default deletion policy deletes the *bucket and its data*. (You set `cnrm.cloud.google.com/deletion-policy: abandon` to make delete-the-CR leave the resource — learn that annotation before you trust KCC with anything stateful.)

### The deletion-policy annotation you must know

```yaml
metadata:
  annotations:
    # "abandon": deleting the CR leaves the GCP resource alone. The default is
    # to DELETE the underlying resource — including data. For anything stateful,
    # set abandon and delete the resource deliberately, never by `kubectl delete`.
    cnrm.cloud.google.com/deletion-policy: "abandon"
```

### How Config Connector actually gets installed (so you know what you're signing up for)

Config Connector is not a binary you install on your laptop — it is a controller that runs *inside* a GKE cluster. There are two installation modes, and the choice shapes your operational burden:

- **GKE add-on (Google-managed install).** You enable Config Connector as a cluster add-on at creation time. Google installs and upgrades the controller for you. This is the path most teams take. It still leaves *you* operating the GKE cluster, the node pools, and the cluster upgrades — Google manages the *controller*, not the *cluster*.
- **Manual install via the operator manifest.** You `kubectl apply` the Config Connector operator, then create a `ConfigConnector` CR pointing at a Google service account that has the IAM to create the GCP resources you intend to manage. More control, more to operate.

Either way, the controller authenticates to GCP as a service account — ideally via **Workload Identity** (the in-cluster kind from Week 6, where a Kubernetes service account is bound to a Google service account), so there is no key file. The Kubernetes SA in the `config-connector` namespace is annotated with the Google SA it impersonates:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cnrm-system
  namespace: cnrm-system
  annotations:
    iam.gke.io/gcp-service-account: kcc-deployer@crunch-gcp-dev.iam.gserviceaccount.com
```

That Google SA needs the roles to create whatever CRs you apply — `roles/pubsub.admin` to manage topics, `roles/storage.admin` to manage buckets, and so on. The blast radius of Config Connector is exactly the union of roles you grant that SA. Grant narrowly. A `kcc-deployer` with `roles/owner` is a single Kubernetes RBAC mistake away from owning the whole project.

The point of walking through the install: Config Connector is a *standing piece of infrastructure with its own identity, its own upgrade story, and its own blast radius*. Terraform, by contrast, is a binary you run and then it is gone. That asymmetry — standing operator vs. ephemeral CLI — is the real trade, underneath the YAML-vs-HCL surface.

### A migration scenario you can reason about

Suppose you run a GKE GitOps platform (Argo CD syncing manifests from Git) and you currently manage your app-adjacent GCP resources — a Pub/Sub topic and a GCS bucket per app — with Terraform in a separate repo and a separate apply step. A team complains that shipping a new app requires a PR to the app repo *and* a PR to the Terraform repo, applied by the platform team, with a lag.

Should you move those resources to Config Connector? Walk the framework:

- The resources are **app-adjacent and app-owned** — a topic and a bucket per app. ✅ (favors KCC)
- You **already run a GKE GitOps platform**. ✅ (favors KCC — no new standing infra; the cluster exists)
- The resources are **not stateful in the destructive-change sense** — a topic and a bucket, where you can set `deletion-policy: abandon` on the bucket to protect data. ✅ (favors KCC)
- Teams want **self-service** without brokering through the platform team. ✅ (favors KCC — namespace + RBAC)

Four greens. This is a genuine Config Connector win: move the topic and bucket CRs into each app's Git directory, scope each team a namespace with RBAC, set `deletion-policy: abandon` on buckets, and the new-app flow becomes a *single* PR to the app repo. The foundation (the cluster, the projects, the `kcc-deployer` SA and its IAM) stays in Terraform. That is the canonical shape: **Terraform foundation, Config Connector for app-adjacent self-service on top.**

Now flip one fact: the app needs a **Cloud SQL instance** (stateful, destructive-change-prone, where you very much want a `plan` to catch a `forces replacement` before it recreates the database). That single resource should stay in Terraform even though everything else moves to KCC. Mixing is fine and normal — the decision is per-resource, not per-estate.

## 2.3 — A decision framework you can defend

In an architecture review, "we used Config Connector because it's GCP-native" is not a defense. Here is the framework. Walk it top to bottom; the first row that matches is your answer.

| Situation | Tool | Why |
|---|---|---|
| Project/org bootstrap, billing, foundational IAM | **CFT (`project-factory`, `iam`) on Terraform** | Highest-gotcha, well-trodden paths; Google's scar tissue beats yours; you need a `plan` before touching billing/IAM. |
| Your specific VPC topology / security baseline where opinions matter | **Hand-written Terraform modules** | You need control and deep understanding; generic modules hide the decisions a security review will question. |
| You already run a GKE GitOps platform and want app-adjacent GCP resources in the same loop | **Config Connector** | Continuous reconciliation + GitOps + namespace self-service genuinely beats a separate Terraform run for *app-owned* resources. |
| Small estate (a handful of resources), no running cluster | **Hand-written Terraform** | A GKE cluster to manage three buckets is absurd; Terraform needs no running infrastructure. |
| Stateful, destructive-change-prone resources (databases, Spanner) | **Terraform** | The `plan` gate (catching `forces replacement` before apply) is a safety feature you do not give up on stateful infra. |
| Application teams self-serving bounded resources in their own namespaces | **Config Connector** | The namespace + RBAC model lets teams self-serve without learning Terraform or you brokering every request. |

Two meta-rules sit above the table:

1. **Almost every real GCP estate uses Terraform for the foundation no matter what.** The state bucket, the projects, the org policies, the GKE cluster that *runs* Config Connector — these are bootstrapped with Terraform because of the chicken-and-egg. Config Connector is, at most, an *addition* for app-adjacent resources, layered on a Terraform foundation. It is never a full replacement.
2. **You earn the right to use the abstraction by building the thing it abstracts.** This is why the course sequence is hand-write-then-compare. A CFT module or a Config Connector CR is a leaky abstraction over the resource graph; you cannot debug a leaky abstraction you never understood.

## 2.4 — Config Controller: the managed bundle

**Config Controller** is Google's managed offering that bundles Config Connector + Policy Controller + Config Sync into a Google-operated GKE Autopilot cluster, marketed as "landing zone as a service." It solves the "you have to operate the GKE cluster that runs KCC" problem by having Google operate it for you. You point it at a Git repo of KCC manifests and policy constraints, and Google reconciles your GCP estate from that repo, with policy enforcement (no public buckets, mandatory labels) via Policy Controller.

It is a real option for a large org that wants a fully-managed GitOps control plane for its GCP estate and is willing to pay for the managed cluster. It is overkill for everything in this course and for most small-to-medium estates — you are buying a managed Kubernetes control plane to manage your cloud. We name it so you recognize it in an architecture discussion; we do not use it.

The policy-enforcement half (Policy Controller / OPA Gatekeeper constraints that block non-compliant resources at admission) is genuinely valuable and is the in-cluster analog of the Sentinel/OPA/Conftest policy-as-code we defer to Week 14. The idea — "a public bucket cannot be created, full stop, regardless of who writes the manifest" — is the same idea whether it runs as a Gatekeeper constraint in Config Controller or a Conftest check in your Cloud Build PR gate.

## 2.5 — Reading a CFT module's source (the exercise you do this lecture)

Open `terraform-google-network`'s source on GitHub and read `main.tf` and `variables.tf`. Three things to find and understand:

1. **How it uses `for_each` over the `subnets` input.** It builds a map keyed by `"${subnet_region}/${subnet_name}"` so two subnets with the same name in different regions do not collide — a subtlety your hand-rolled module probably did not handle. This is the kind of accumulated correctness CFT gives you.
2. **What it hard-codes vs. exposes.** Note which decisions are inputs and which are baked in. Compare to the input/output boundary you drew in your own `vpc` module in Lecture 1. Where did Google draw the line differently, and why?
3. **The `secondary_ranges` handling for GKE.** GKE needs secondary IP ranges for pods and services; the module wires them into the subnet. When you write the GKE module in Week 6, you will either feed it these ranges from your own VPC module or adopt the CFT network module — and you will be able to make that call *because* you read both.

This is the lecture's hands-on: read the source, then write a one-paragraph comparison of the CFT network module to your own `vpc` module — what it does better, what it hides, and whether you would adopt it for the mini-project. (The homework formalizes this.)

Here is the specific subtlety to find. Your Exercise 2 module keyed subnets by name:

```hcl
# Your module — keys by name. Two subnets named "app" in different regions COLLIDE.
resource "google_compute_subnetwork" "this" {
  for_each = var.subnets   # map(name => cidr); the key is just the name
  name     = each.key
  region   = var.region    # one region for the whole module
  # ...
}
```

The CFT module supports subnets across *multiple* regions in one call, so it cannot key by name alone — two subnets named `app` in `us-central1` and `us-east1` would collide on the `for_each` key. It keys by a composite instead:

```hcl
# CFT (paraphrased) — keys by "region/name", so multi-region names don't collide.
locals {
  subnets = { for s in var.subnets : "${s.subnet_region}/${s.subnet_name}" => s }
}

resource "google_compute_subnetwork" "subnetwork" {
  for_each = local.subnets
  name     = each.value.subnet_name
  region   = each.value.subnet_region
  # ...
}
```

That composite key is exactly the kind of accumulated correctness CFT gives you — a case your single-region module did not need to handle but a multi-region estate does. Whether you *need* it for the course (you do not — the course pins one region) is the judgment call. Reading the source is how you make that call deliberately instead of cargo-culting the module "to be safe."

### Policy enforcement: the in-cluster analog of the PR gate

There is a fourth piece worth naming because it ties Lecture 1's plan-review gate to the Config Connector world. **Policy Controller** (Google's distribution of OPA Gatekeeper) runs *admission webhooks* in the cluster that *reject* a non-compliant resource before it is created — regardless of who wrote the manifest. A constraint that forbids public buckets looks like:

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: GCPStorageBucketRequireUniformAccess   # a Policy Controller constraint template
metadata:
  name: deny-non-uniform-buckets
spec:
  match:
    kinds:
      - apiGroups: ["storage.cnrm.cloud.google.com"]
        kinds: ["StorageBucket"]
  parameters:
    enforce: true   # reject any StorageBucket CR without uniformBucketLevelAccess
```

This is the *same idea* as a Conftest/OPA check in your Cloud Build PR gate ("a plan that creates a public bucket fails the build"), just enforced at a different point: admission time in the cluster instead of plan time in CI. The principle is identical and is the Week 14 (security hardening) topic in full. Recognize the symmetry now: whether your IaC runs as Terraform-in-CI or Config-Connector-in-cluster, you bolt a *policy gate* in front of it so that certain mistakes are *structurally impossible*, not merely caught by a careful human. Human plan review (Lecture 1) is the floor; policy-as-code is the ceiling.

## 2.6 — The reflexes to internalize this week

- **Terraform is the foundation, always.** State bucket, projects, org policies, and the cluster that runs Config Connector are all bootstrapped with Terraform. Nothing escapes the chicken-and-egg.
- **CFT for high-gotcha well-trodden paths; hand-written for where your opinions matter.** Project factory and IAM: lean on Google. Your specific VPC and security baseline: write your own.
- **Never use a module whose source you have not read.** The abstraction is leaky; you debug what you understand.
- **Config Connector wins when you already run GitOps on GKE and want continuous reconciliation for app-adjacent resources.** It loses when you would stand up a cluster just to manage a handful of resources, or when you need the `plan` gate on stateful infra.
- **Know the `deletion-policy: abandon` annotation** before you trust Config Connector with anything stateful.
- **"It's GCP-native" is not an architecture-review defense.** Walk the decision table; name the trade-off out loud.
- **The decision is per-resource, not per-estate.** A Cloud SQL instance can stay in Terraform (for the `plan` gate) while the app's bucket and topic move to Config Connector. Mixing is normal.
- **The framework transfers; the answer is context-dependent.** The course hand-writes the foundation *because it is a learning context*. In production, the same framework may point at CFT. Learn the walk, not the verdict.

## 2.7 — A second decision worked end-to-end: the landing zone

Apply the framework to the decision you will actually face at the start of the mini-project: *how do I create the projects and the foundational IAM for `dev` and `prod`?* Three candidate answers, walked:

- **Hand-write `org-bootstrap` and `iam-baseline` (what the course makes you do).** You learn the project-creation ordering, the billing link, the additive-vs-authoritative IAM distinction, by feeling them. The cost is the afternoon of `FAILED_PRECONDITION` debugging. The benefit is that you now understand the resource graph well enough to debug *anything* built on it for the next eleven weeks. For a *learning* context, this wins decisively, which is why the mini-project mandates it.
- **Adopt `terraform-google-project-factory` + `terraform-google-iam`.** For a *production* context where you have already learned the graph, this wins: Google's scar tissue beats yours on these specific high-gotcha paths, and you get a versioned, tested API. The "going further" section of the challenge has you do exactly this swap and diff the plans, so you experience both sides.
- **Manage projects with Config Connector.** This *loses* here, and naming why is the skill: project and org-policy creation is foundational, not app-adjacent; it is the chicken-and-egg layer (the cluster that runs KCC lives *inside* a project); and you want a `plan` before touching billing and org-level IAM. Config Connector is for the layer *above* the foundation, not the foundation itself.

The answer the course takes — hand-write for learning, with an explicit invitation to swap to CFT once you have earned it — is the defensible one *for this context*. In your job, the context differs and so might the answer. The framework, not the answer, is what transfers.

## 2.8 — What this lecture did not cover

Policy-as-code in depth — a Rego or Sentinel library that *blocks* a public bucket, *enforces* a label scheme, *caps* machine sizes at plan time — is a Week 14 (security hardening) topic. This week's gate is human plan review plus the cheap `fmt`/`validate` automated checks (Exercise 3). We also did not cover Atlantis (the open-source PR-automation server that productionizes Exercise 3's Cloud Build trigger) beyond a mention, or the SDK-based IaC tools (Pulumi, CDK for Terraform) whose state and drift concepts transfer but whose syntax is out of scope for an HCL-substrate course.

---

## Lecture 2 — checklist before moving on

- [ ] I can name the four CFT modules I would actually reach for and what each saves me.
- [ ] I can state the hidden-complexity trap and why the course makes me hand-write modules before adopting CFT.
- [ ] I can explain how Config Connector's continuous reconciliation differs from Terraform's run-time reconciliation.
- [ ] I can name three situations where Config Connector wins and three where it loses.
- [ ] I know what `cnrm.cloud.google.com/deletion-policy: abandon` does and why it matters for stateful resources.
- [ ] I can walk the decision table and defend a tool choice without saying "because it's GCP-native."
- [ ] I have read `terraform-google-network`'s source and can compare it to my own `vpc` module.
- [ ] I can explain why project/org bootstrap stays in Terraform even on an estate that uses Config Connector heavily.
- [ ] I can name the in-cluster analog of the PR plan-review gate (Policy Controller / OPA Gatekeeper admission webhooks).

If any box is unchecked, return to that section. The challenge and mini-project assume you can decide *whether* to hand-write a module before you write it.

One last framing to carry forward: the through-line of this entire week is *honest signal*. Lecture 1's clean plan is honest signal that code and cloud agree. The plan-review gate is honest signal that a human saw the destructive change before it ran. And this lecture's whole argument — read the module's source, walk the decision table out loud, never adopt an abstraction you cannot debug — is about refusing to let a tool's convenience substitute for your own understanding. The senior move is not "use the fanciest tool"; it is "use the simplest tool you fully understand, and earn the right to the fancier one by first building what it abstracts."

---

**References cited in this lecture**

- Cloud Foundation Toolkit — overview / blueprints: <https://cloud.google.com/docs/terraform/blueprints/terraform-blueprints>
- `terraform-google-modules` GitHub org: <https://github.com/terraform-google-modules>
- `terraform-google-network` module: <https://github.com/terraform-google-modules/terraform-google-network>
- `terraform-google-project-factory` module: <https://github.com/terraform-google-modules/terraform-google-project-factory>
- Config Connector — overview: <https://cloud.google.com/config-connector/docs/overview>
- Config Connector — "How Config Connector works": <https://cloud.google.com/config-connector/docs/concepts/overview>
- Config Connector — resource reference: <https://cloud.google.com/config-connector/docs/reference/overview>
- Config Connector — managing deletion policy: <https://cloud.google.com/config-connector/docs/how-to/managing-deleting-resources>
- Config Controller — overview: <https://cloud.google.com/anthos-config-management/docs/concepts/config-controller-overview>
