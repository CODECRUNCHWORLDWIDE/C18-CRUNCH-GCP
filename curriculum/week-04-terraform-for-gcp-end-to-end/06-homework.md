# Week 4 — Homework

Six problems. They apply the week's concepts *beyond* the lab — these are not re-runs of the exercises. Each has a time estimate and a deliverable. Graded against the rubric at the bottom. Total budget: ~5 hours.

Submit everything in a `week-04-homework/` directory in your course Git repo, with a top-level `README.md` indexing your answers and linking each deliverable.

---

## Problem 1 — Read a plan for the footgun (45 min)

You are reviewing a colleague's pull request. The Cloud Build plan check posted this (abbreviated):

```
  # google_sql_database_instance.primary will be updated in-place
  ~ resource "google_sql_database_instance" "primary" {
      ~ settings {
          ~ tier = "db-custom-2-7680" -> "db-custom-4-15360"
        }
    }

  # google_sql_database_instance.replica must be replaced
-/+ resource "google_sql_database_instance" "replica" {
      ~ region           = "us-central1" -> "us-east1" # forces replacement
      ~ name             = "replica" -> "replica" # (no change)
        ...
    }

Plan: 1 to add, 1 to change, 1 to destroy.
```

**Deliverable** (`problem-01.md`): A PR review comment, written as you would actually post it, that:

1. Identifies which resource is being destroyed-and-recreated and the exact attribute that `forces replacement`.
2. Explains the data-loss risk and what must happen *before* this merges (backup? read-replica promotion? maintenance window?).
3. States whether you would approve, request changes, or block, and why.
4. Explains why the `primary` change (in-place `~`) is safe but the `replica` change (`-/+`) is not.

There is no "right" approval decision — there is a right *analysis*. We grade the analysis.

---

## Problem 2 — Convert `count` to `for_each` and prove address stability (45 min)

You inherit this fragment:

```hcl
variable "service_accounts" {
  type    = list(string)
  default = ["ci-deploy", "app-runtime", "backup-agent"]
}

resource "google_service_account" "sa" {
  count        = length(var.service_accounts)
  account_id   = var.service_accounts[count.index]
  display_name = "SA for ${var.service_accounts[count.index]}"
  project      = var.project_id
}
```

**Deliverable** (`problem-02/`): 

1. Rewrite this to use `for_each` over a `toset(var.service_accounts)`. Submit the rewritten `.tf`.
2. In a `problem-02.md`, show the resource *addresses* before (`google_service_account.sa[0]` etc.) and after (`google_service_account.sa["ci-deploy"]` etc.).
3. Explain precisely what `plan` would show if someone removed `"app-runtime"` (the *middle* element) from the `count` version vs. the `for_each` version. (One destroys-and-recreates a trailing SA; the other deletes exactly one. Say which is which and why.)
4. Note one case where this conversion is *not* safe to do directly on a live estate without a `terraform state mv`, and what `state mv` command you'd run to migrate the existing index-keyed state to key-keyed state.

---

## Problem 3 — Design the input/output boundary for a `gcs-bucket` module (45 min)

Design (do not fully implement) a reusable `modules/gcs-bucket` module. The hard part is the boundary: what is an input, what is hard-coded as the module's opinion, what is an output.

**Deliverable** (`problem-03.md`): A table with three columns — *Attribute*, *Input / Hard-coded / Output*, *Reasoning* — covering at least: bucket name, location, `uniform_bucket_level_access`, `versioning`, `force_destroy`, lifecycle rules, labels, public-access prevention, the bucket's self-link, and CMEK key. For each, justify the classification. (Hint: `uniform_bucket_level_access = true` and `public_access_prevention = "enforced"` should be the module's *opinions*, not inputs — a bucket module that lets you turn off uniform access is a security liability. Defend that stance or argue against it.)

Then write the `variables.tf` (with `description` and `validation` on every variable) for your chosen inputs. The `main.tf` is optional; the boundary analysis is the graded artifact.

---

## Problem 4 — The drift incident postmortem (45 min)

Write a short, blameless postmortem for this scenario: a teammate fixed a production outage by manually adding a firewall rule allowing health-check traffic, in the Cloud Console, at 02:00. They never reflected it in HCL. Eleven days later, a different engineer merged an unrelated PR that changed a subnet CIDR; the CI `apply` ran, refreshed state, and removed the manually-added firewall rule as drift. Health checks failed; the service was marked unhealthy and removed from the load balancer; a second outage began at 14:30.

**Deliverable** (`problem-04.md`): A postmortem (~400–600 words) using the structure: *Summary → Timeline → Root cause → Contributing factors → What went well → Action items*. The action items must include at least: (a) a process change (the click-then-codify discipline), (b) a tooling change (scheduled drift detection with `plan -detailed-exitcode`), and (c) a guardrail (the PR plan-review gate, and why a human reading the plan would have caught the firewall-rule removal). Be specific; "be more careful" is not an action item.

---

## Problem 5 — CFT vs. hand-rolled comparison (45 min)

Read the source of `terraform-google-network` on GitHub (`main.tf`, `variables.tf`, and the `subnets` handling in particular).

**Deliverable** (`problem-05.md`): A ~500-word comparison of the CFT network module against the `vpc` module you wrote (in Exercise 2 / the challenge), covering:

1. One thing the CFT module does *more correctly* than yours (e.g., its `for_each` key uses `"${region}/${name}"` to avoid same-name-different-region collisions — does yours?).
2. One thing the CFT module *hides* that you think a learner should understand before adopting it.
3. The version-lag trade-off: when the `google` provider ships v7, who upgrades faster — your module or the CFT module — and why that matters for an estate that wants new provider features.
4. Your recommendation: would you adopt the CFT module for the mini-project, keep your hand-rolled one, or use CFT for `org-bootstrap` (project-factory) but keep your own `vpc`? Defend it in two sentences.

---

## Problem 6 — Cost & teardown audit (15 min)

**Deliverable** (`problem-06.md`):

1. List every billable resource your Week 4 work created (state bucket, any VPCs/subnets — note which are free, Cloud Build minutes, Secret Manager secrets). Mark each as free-tier or paid, with the approximate monthly cost at list price if left running.
2. State which single resource you must *not* destroy (the state bucket) and why.
3. Paste the output of your `verify-empty.sh` (or the equivalent `gcloud asset search-all-resources`) for both `dev` and `prod` after teardown, proving the projects are empty.
4. One sentence: what is the most expensive mistake a student could make this week, and how does the teardown gate prevent it? (Answer: leaving a `dev` environment with NAT/compute billing overnight; the gate forces a verified-empty check before the week is marked done.)

---

## Submission & rubric

Submit `week-04-homework/` with `problem-01.md` … `problem-06.md` and any `.tf` deliverables, indexed by a top-level `README.md`.

| Problem | Points | Full marks when… |
|---|---:|---|
| P1 — Read a plan for the footgun | 20 | Correctly identifies the `-/+` replacement and the `forces replacement` attribute; data-loss analysis is sound; approve/block decision is *justified*. |
| P2 — `count` → `for_each` | 20 | Rewrite is correct and `fmt`-clean; before/after addresses shown; middle-element-removal behavior explained for both; the `state mv` migration named. |
| P3 — Module boundary design | 15 | Every attribute classified with reasoning; security opinions (uniform access, public-access prevention) defended; `variables.tf` has `description` + `validation` throughout. |
| P4 — Drift postmortem | 20 | Blameless; correct root cause (unreflected console change = drift); three concrete action items spanning process, tooling, and guardrail. |
| P5 — CFT comparison | 15 | Read the actual source; names a real correctness difference, a real hidden complexity, the version-lag trade-off, and a defended recommendation. |
| P6 — Cost & teardown | 10 | Billable resources listed and classified; state bucket correctly excluded from teardown; verify-empty output pasted for both envs. |

**Passing:** 70/100. The homework is graded on *analysis quality*, not on whether your opinion matches the instructor's — a well-argued "I'd block this PR" and a well-argued "I'd approve with a backup first" both earn full marks on P1. Hand-waving ("looks fine") does not.

---

*Time estimates are honest medians. P4 (the postmortem) and P5 (the CFT read) are the two that reward going slow — they are the ones that build the senior-engineer judgment the rest of the course assumes.*
