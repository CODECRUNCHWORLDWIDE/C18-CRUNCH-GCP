# Week 4 — Quiz

Thirteen questions on state, locking, `for_each` vs `count`, modules, Terragrunt, drift, plan review, Config Connector, and the Cloud Foundation Toolkit. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 5. Answer key at the bottom — don't peek.

---

**Q1.** Terraform `apply` is best described as:

- A) A tool that creates the resources listed in your `.tf` files.
- B) A reconciliation engine that computes the delta between the configuration (desired), the state file (Terraform's memory), and the real cloud (via refresh), then issues the API calls to close the delta.
- C) A wrapper around `gcloud` that runs your commands in order.
- D) A script that reads the state file and prints it.

---

**Q2.** You and a teammate both keep `terraform.tfstate` locally and share it over Slack. You both run `terraform apply` within the same minute. What is the most likely outcome?

- A) Terraform queues the second apply automatically; no problem.
- B) The second writer clobbers the first's state record, producing a state file that describes a cloud that doesn't exist — a corrupted state and a data race.
- C) Both applies fail with a lock error.
- D) Nothing — local state is process-safe.

---

**Q3.** The GCS backend implements state locking using:

- A) A separate Cloud SQL lock table you must provision.
- B) A DynamoDB table, the same as the S3 backend.
- C) GCS object generations — Terraform writes a `.tflock` object with a conditional (generation-precondition) write; a second writer is rejected with HTTP 412.
- D) A file lock on your local disk.

---

**Q4.** You bootstrap a state bucket. Why does the `bootstrap/` module use **local** state instead of storing its own state in the bucket it creates?

- A) Local state is faster.
- B) Chicken-and-egg: the bucket cannot store the state of its own creation before it exists. You bootstrap with local state, then everything *else* uses the bucket.
- C) The GCS backend doesn't support bucket resources.
- D) It's a bug in the course material; the bootstrap should use the bucket.

---

**Q5.** You have three subnets. A colleague converts them to `count` over a *list*, then deletes the **first** list element. What does the next `plan` show, and why?

- A) Deletes one subnet cleanly; the rest are untouched.
- B) No changes; `count` addresses by stable key.
- C) A destroy-and-recreate of the remaining subnets, because `count` addresses by positional index — deleting element 0 shifts every later element's index, and Terraform reads the shift as "destroy at the old index, create at the new one."
- D) An error; you can't delete from a `count` list.

---

**Q6.** The rule for choosing between the two meta-arguments is:

- A) `count` by default; `for_each` only for maps.
- B) `for_each` by default; `count` only for the "zero or one of this thing" conditional case.
- C) Always `count`; `for_each` is deprecated.
- D) They're interchangeable; pick by taste.

---

**Q7.** You want to enable a beta-only field on one `google_compute_subnetwork`. The correct approach is:

- A) Set the entire project to use `google-beta` to be safe.
- B) Configure both `google` and `google-beta` providers, and set `provider = google-beta` on *only* that one resource; everything else stays on the stable `google` provider.
- C) Edit the provider source to a fork.
- D) You cannot use beta fields with Terraform.

---

**Q8.** In a `vpc` module, which of these should be hard-coded (the module's opinion) rather than an input?

- A) The project ID.
- B) The region.
- C) The CIDR ranges.
- D) `auto_create_subnetworks = false` — a `vpc` module that allows auto-subnets is not opinionated enough to be useful; this is an invariant of the module's job.

---

**Q9.** Plain Terraform workspaces fall down for serious multi-environment work primarily because:

- A) Workspaces are slower than directories.
- B) Workspaces share one backend block, so `dev` and `prod` cannot have different backends, different state buckets, or different provider configs — which they always eventually need.
- C) Workspaces don't support `for_each`.
- D) Workspaces require Terragrunt.

---

**Q10.** Terragrunt's single most important feature — the thing plain Terraform genuinely cannot do — is:

- A) Running `terraform apply` in parallel.
- B) Generating per-environment backend blocks (and provider blocks) from a single root config, so each `(env, component)` gets a distinct state file without copy-pasted backend blocks.
- C) Replacing the `google` provider.
- D) Storing state in a database.

---

**Q11.** Six weeks into a project, production is on fire and you click a fix in the Cloud Console without reflecting it in HCL. Three weeks later a teammate runs an unrelated `terraform apply`. What is the danger?

- A) None; console changes are independent of Terraform.
- B) Terraform refreshes state, sees the live resource no longer matches the config (your console fix is drift), and silently *reverts your fix* as part of the unrelated apply — reigniting the fire at a confusing time.
- C) Terraform will refuse to run until you re-click the fix.
- D) The console change is automatically imported into state.

---

**Q12.** When does Config Connector beat raw Terraform?

- A) Always — it's GCP-native.
- B) For a tiny estate of three buckets with no running cluster.
- C) When you already run a GKE GitOps platform and want app-adjacent GCP resources in the *same* continuous-reconciliation loop (self-healing drift, namespace self-service) as your workloads.
- D) For stateful databases where you need a `plan` gate before destructive changes.

---

**Q13.** Which statement about the Cloud Foundation Toolkit is correct?

- A) CFT is a separate CLI tool you install instead of Terraform.
- B) CFT modules are just Terraform modules published to the registry; they shine on high-gotcha well-trodden paths (project creation, IAM), but you should never use one whose source you haven't read, because the hidden complexity is complexity you didn't learn and can't debug.
- C) CFT modules cannot be version-pinned.
- D) CFT replaces the need for state files.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Terraform is a reconciliation engine. It diffs desired (config) against memory (state) against reality (refresh) and closes the gap. It does not blindly "create"; if a resource is already in state, it updates or no-ops it.

2. **B** — Local state is read at the start of a run and written at the end. Two overlapping runs mean the second writer clobbers the first's record, and the state file now describes a cloud that doesn't exist. This is the canonical reason for remote state with locking. There is no lock with local state, so A and C are wrong.

3. **C** — The GCS backend uses object generations: it writes a `.tflock` object with a precondition that fails (HTTP 412) if the object already exists at a different generation. No separate lock table is needed — this is a genuine advantage over the historical S3+DynamoDB setup.

4. **B** — Chicken-and-egg. The bucket can't hold the state of its own creation before it exists. You bootstrap with local state and migrate everything else into the bucket. The bootstrap is small and rarely changes, so local (or committed-to-private-repo) state is acceptable for it.

5. **C** — `count` addresses by positional index (`[0]`, `[1]`, `[2]`). Deleting element 0 shifts every later element's index, and Terraform interprets the shift as destroy-at-old-index + create-at-new-index for every following resource — a destroy-and-recreate of live subnets caused purely by a reorder. This is the headline `count` footgun and the reason for the `for_each`-by-default rule.

6. **B** — `for_each` by default (stable, key-based addressing; set/map semantics; readable plans), `count` only for the zero-or-one conditional case (`count = var.enable_x ? 1 : 0`).

7. **B** — Opt into beta per-resource. Configure both providers, set `provider = google-beta` on the one resource that needs the beta field, and leave everything else on the stable provider. Setting the whole project to beta (A) silently rides beta schemas for resources that have stable GA forms and inherits beta churn for no benefit.

8. **D** — `auto_create_subnetworks = false` is an invariant of what a `vpc` module is *for*; auto-subnets are a footgun. The module's opinions (this, Private Google Access on every subnet, the naming scheme) are hard-coded. Project, region, and CIDRs differ between environments and are inputs.

9. **B** — Workspaces share one backend block. The moment `dev` and `prod` need different backends, different state buckets, or different provider configs (so a dev mistake can't even authenticate against prod), workspaces are insufficient. This is why directory-per-environment + Terragrunt is the production pattern.

10. **B** — Terragrunt's `remote_state` block generates a distinct backend (and `generate` produces the provider block) per environment from one root config, using `path_relative_to_include()` to derive a per-component state prefix. Plain Terraform cannot template a backend block — backend config can't use variables — so this is the one thing it genuinely can't do without copy-paste.

11. **B** — The unreflected console change is *drift*. The next refresh sees the live resource diverge from the config and proposes (and, on apply, executes) a revert — silently, as a side effect of an unrelated change, at a confusing time. This is exactly why the discipline is plan-review + scheduled drift detection, and why click-then-never-codify is the fireable offense.

12. **C** — Config Connector's win is continuous in-cluster reconciliation: self-healing drift, GitOps alongside workloads, namespace self-service. It requires a running GKE cluster (so it loses for a tiny estate, B) and lacks Terraform's `plan` gate (so it loses for stateful databases where you need to catch `forces replacement` before applying, D). "Always, it's GCP-native" (A) is never an architecture-review answer.

13. **B** — CFT modules are ordinary Terraform modules on the registry, version-pinnable like any other. They earn their keep on high-gotcha paths (project-factory encodes billing-link-before-API-enable ordering; the IAM module handles additive-vs-authoritative correctly). The honest caveat: never adopt a module whose source you haven't read, because the abstraction is leaky and you debug what you understand. This is why the course makes you hand-write modules first.

</details>

---

If you scored under 9, re-read the lecture for the questions you missed — especially the `count`-vs-`for_each` footgun (Q5) and the drift/click-ops discipline (Q11). If you scored 11+, you're ready for the [homework](./homework.md) and the mini-project.
