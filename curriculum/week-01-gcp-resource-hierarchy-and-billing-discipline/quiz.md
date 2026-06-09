# Week 1 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 2. Answer key at the bottom — don't peek.

---

**Q1.** Which statement best describes how GCP's project boundary differs from an AWS account?

- A) A GCP project and an AWS account are exactly equivalent: both are the billing unit, the IAM trust boundary, and the blast radius.
- B) In AWS the account fuses billing, IAM trust, and blast radius into one object; in GCP those concerns are split across the project, the billing account, and IAM policy attached to a hierarchy node.
- C) A GCP project is heavier and slower to create than an AWS account.
- D) GCP projects cannot reference each other; an AWS account can.

---

**Q2.** Which of the four hierarchy nodes can actually *hold resources* (a VM, a bucket)?

- A) The organization.
- B) Any folder.
- C) Only projects.
- D) Both folders and projects.

---

**Q3.** You grant `roles/viewer` to a group at the `workloads/` folder. A new project is created under `workloads/dev/` next week. Who can view it?

- A) Nobody — the grant only applies to projects that existed when it was made.
- B) The group — IAM grants on a folder are inherited by all projects beneath it, including future ones.
- C) Only an org admin, until the grant is re-applied to the new project.
- D) The group, but only after running `gcloud projects sync-iam`.

---

**Q4.** Which of a project's three identifiers is globally unique, immutable, *and* the thing every `gcloud --project` flag and API call references?

- A) The display name.
- B) The project number.
- C) The project ID.
- D) The billing account ID.

---

**Q5.** A teammate says "I set a \$50 budget on the project, so it can't spend more than \$50." What is wrong with that statement?

- A) Nothing — a budget is a hard cap.
- B) A budget only *alerts*; it does not stop spending. A hard cap requires extra automation that detaches billing.
- C) Budgets cap spending but only on the first of the month.
- D) The cap is \$50 per day, not per month, so the statement understates the limit.

---

**Q6.** Where does a Cloud Billing **budget** object live?

- A) Inside the project it watches, as a child resource.
- B) On the billing account, optionally scoped to projects/labels/services.
- C) In the organization node, as an org policy constraint.
- D) In a folder, inherited downward like IAM.

---

**Q7.** You configured a budget with a Pub/Sub notification channel, but no Slack message ever arrives even though spend crossed 90%. The function is deployed and the topic exists. What is the most likely cause?

- A) Budgets cannot publish to Pub/Sub.
- B) The Cloud Billing system service agent (`billing-budget-alert@system.gserviceaccount.com`) lacks `roles/pubsub.publisher` on the topic.
- C) The budget amount is too low.
- D) Pub/Sub topics only deliver to email, not functions.

---

**Q8.** Your CI service account has `roles/resourcemanager.projectCreator` at the org. It creates a project successfully, but cannot enable `compute.googleapis.com` on it. Why?

- A) `projectCreator` does not include the ability to link the new project to a billing account; you also need `roles/billing.user` on the billing account.
- B) Compute API can only be enabled by a human.
- C) The project ID was not globally unique.
- D) Compute API requires an organization, and the project is an orphan.

---

**Q9.** Which is an **allocation** quota (as opposed to a rate quota)?

- A) "Compute Engine API: 2,000 read requests per minute."
- B) "CPUs in `us-central1`: 24."
- C) "Pub/Sub publish: 1 GB/s."
- D) "Cloud Functions invocations per second."

---

**Q10.** In the bootstrap chicken-and-egg problem, why does the `bootstrap/` Terraform layer start with **local** state?

- A) Local state is faster.
- B) Because the GCS bucket that will hold remote state does not exist yet — the bootstrap layer is the thing that creates it. You migrate to GCS after the bucket exists.
- C) Because GCS backends do not support state locking.
- D) Because the organization node must be created with local state.

---

**Q11.** In the `budgeted-project` module, compute is gated on the budget via:

```hcl
resource "google_project_service" "compute" {
  ...
  depends_on = [google_billing_budget.this]
}
```

What does this guarantee?

- A) Nothing useful; `depends_on` is cosmetic.
- B) Terraform will not enable `compute.googleapis.com` until the budget resource has been created, on every apply.
- C) The budget will be deleted if compute is disabled.
- D) Compute will be enabled first, then the budget.

---

**Q12.** When you run `gcloud config configurations activate prod` and then `gcloud projects delete acme-api-prod`, what is the role of the active configuration?

- A) None — `gcloud projects delete` ignores the active config.
- B) The active config supplies default properties (account, project, region) so a single mistaken `activate` is the difference between deleting the dev vs. prod project. This is exactly why you confirm the active config before destructive commands.
- C) The active config encrypts the delete request.
- D) The active config determines the billing account charged for the delete.

---

**Q13.** Why does the mini-project's teardown migrate the bootstrap layer's state back to **local** before running `terraform destroy` on it?

- A) To make the destroy faster.
- B) Because Terraform cannot destroy the GCS bucket that is currently holding the very state it is reading from; migrating to local frees the bucket to be deleted.
- C) Because GCS buckets cannot be deleted by Terraform at all.
- D) Because local state is required to delete projects.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — The core lesson of Lecture 1: AWS fuses billing/IAM/blast-radius into the account; GCP splits them across project, billing account, and hierarchy-attached IAM.
2. **C** — Only projects hold resources. Org and folders are policy/grouping nodes; you cannot "put a VM in a folder."
3. **B** — IAM grants flow *down* the hierarchy and apply to projects created later under that node. This inheritance is the load-bearing security property — and the reason folder placement is a security decision.
4. **C** — The project ID: globally unique, immutable, and the handle every API call uses. The number is also unique/immutable but is not what `--project` takes; the display name is mutable and non-unique.
5. **B** — A budget alerts; it does not cap. The "I set a budget and still got a huge bill" stories all stem from this misconception. A real cap is a second consumer that detaches billing.
6. **B** — The budget lives on the billing account (outside the resource hierarchy), optionally scoped via `budget_filter` to projects, labels, or services.
7. **B** — The classic silent failure: the billing system service agent needs `roles/pubsub.publisher` on the topic or delivery fails silently.
8. **A** — `projectCreator` lets you make projects but not link them to billing; you need `roles/billing.user` on the billing account too. This is the CI footgun from Lecture 2.
9. **B** — An allocation quota is a standing ceiling on a count of things (CPUs in a region). The others are rate quotas (per unit time).
10. **B** — The bootstrap layer creates the state bucket, so it cannot store its state there until it exists. Local first, then `init -migrate-state`.
11. **B** — `depends_on` makes Terraform order the graph so the budget is created before the compute API is enabled, on every apply — the rule lives in code.
12. **B** — The active configuration supplies the default project/account; the whole point of named configs (and the Exercise 3 guard) is that the active config is the difference between a safe and a catastrophic destructive command.
13. **B** — You cannot delete a bucket while Terraform is reading its state from that same bucket; migrating bootstrap state to local (`-backend=false`) frees it for deletion.

</details>

---

If you scored under 9, re-read the lecture for the questions you missed — especially Q5 (budget ≠ cap) and Q1 (project ≠ account), which are the two ideas the whole week turns on. If you scored 12 or 13, you're ready for the [homework](./homework.md).
