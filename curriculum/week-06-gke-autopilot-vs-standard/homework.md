# Week 6 Homework

Six practice problems that revisit the week's topics and push slightly past the exercises. The full set should take about **5 hours**. Work in your Week 6 Git repository so each problem produces at least one commit you can point to later.

Each problem includes a short **problem statement**, **acceptance criteria** so you know when you're done, a **hint** if you get stuck, and an **estimated time**.

---

## Problem 1 — Write the Autopilot-vs-Standard decision memo for a real workload

**Problem statement.** You are handed a workload spec: a stateless Python API, p99 < 200ms target, traffic of ~30 RPS off-peak and ~400 RPS for a 3-hour daily spike, no host-level access needed, and a third-party APM agent that ships *only* as a privileged host-network DaemonSet (no Autopilot variant). Write a one-page memo recommending Autopilot or Standard, running the §1.4 decision procedure explicitly, and ending in a monthly cost estimate for your recommended mode.

**Acceptance criteria.**

- `notes/autopilot-vs-standard-memo.md` exists and runs the decision procedure in order: feature-constraint check first, then cost.
- The memo correctly identifies the privileged host-network DaemonSet as a **hard constraint** that forces Standard (Lecture 1, §1.3 constraint 1), and says so before doing any cost math.
- A monthly cost estimate for the recommended mode using the §1.2 method, with the spiky traffic profile reflected (the spike drives the sizing).
- One sentence on what would change your recommendation (e.g., if the APM vendor shipped an Autopilot-compatible agent).

**Hint.** The trick of this problem is that the cost analysis is a trap — the constraint already decided. The grade is for running the procedure in the *right order*, not for the cheapest answer.

**Estimated time.** 40 minutes.

---

## Problem 2 — Convert the classic Workload Identity binding to the GSA-less form

**Problem statement.** Take the Exercise 2 Workload Identity setup (classic KSA→GSA binding) and rewrite it using the newer **GSA-less** `principal://` IAM binding, where IAM roles are granted directly to the KSA principal with no Google service account at all. Deploy a pod using it and confirm `/read` still works.

**Acceptance criteria.**

- `notes/wi-gsa-less.md` documents the exact `gcloud storage buckets add-iam-policy-binding --member="principal://..."` command, with the correct `projects/PROJECT_NUMBER/.../subject/ns/default/sa/KSA_NAME` path.
- No `google_service_account` (GSA) is created; no `roles/iam.workloadIdentityUser` binding; no `iam.gke.io/gcp-service-account` annotation on the KSA.
- A pod running as the KSA reads the GCS object successfully (200 from `/read`).
- A two-sentence note on when you would still use the classic GSA form (e.g., when the same identity must be shared by non-GKE workloads, or for compatibility with existing GSA-based IAM).

**Hint.** You need the project *number*, not the project ID, in the `principal://` path: `gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)'`.

**Estimated time.** 45 minutes.

---

## Problem 3 — Reproduce a stalled upgrade on purpose

**Problem statement.** On a Standard cluster running the 3-replica FastAPI Deployment, set a PDB of `minAvailable: 3` (deliberately impossible) and a node pool of `strategy=SURGE, max_surge=0, max_unavailable=1`. Start a node-pool upgrade and observe it stall. Capture the evidence, then fix the PDB and watch it complete.

**Acceptance criteria.**

- `notes/stalled-upgrade.md` includes the `kubectl get pdb` output showing `ALLOWED DISRUPTIONS: 0` and the upgrade event/log showing the drain blocked (e.g., `Cannot evict pod as it would violate the pod's disruption budget`).
- The note explains *why* the stall happens (no eviction can be permitted without breaching `minAvailable: 3`-of-3) and ties it to the `max_unavailable=1`/no-surge configuration.
- After changing the PDB to `minAvailable: 2`, the upgrade completes; the note shows the after-state.

**Hint.** You may need to cancel the stalled upgrade (`gcloud container operations` to find it, then let it time out, or roll the node version back). Document how you recovered.

**Estimated time.** 50 minutes.

---

## Problem 4 — Compute the cost crossover point between Autopilot and Standard-spot

**Problem statement.** For a pod requesting 1 vCPU / 4 GiB, build a small spreadsheet (or a Python script) that computes, as a function of *replica count N* running 24/7, the monthly cost on (a) Autopilot general-purpose on-demand and (b) a Standard spot pool of `e2-standard-4` nodes packed at ~3 such pods per node. Find the N at which Standard-spot becomes cheaper than Autopilot.

**Acceptance criteria.**

- `notes/cost-crossover.py` (or `.md` with a table) computes both curves using current `us-central1` list prices (cite them and the date).
- It includes the $73/month cluster fee on both sides (it cancels, but show it).
- It reports the crossover N and a one-line interpretation (e.g., "below ~K replicas the Autopilot convenience is nearly free; above it, Standard-spot's node packing + spot discount wins").
- It notes the assumption that makes spot acceptable (the workload tolerates ~30s-notice preemption).

**Hint.** Autopilot cost is linear in N (per-request billing). Standard-spot cost is a step function in N (you add a whole node every ~3 pods) plus the spot discount. The crossover is where the step function dips below the line.

**Estimated time.** 50 minutes.

---

## Problem 5 — Read a VPA recommendation and adjust requests

**Problem statement.** Deploy a VPA in `updateMode: Off` (recommendation only) on the FastAPI Deployment, run a realistic `hey` load for 10 minutes, then read the VPA's recommendation. Compare it to your hand-set `requests` and write down whether you would change them and by how much.

**Acceptance criteria.**

- `notes/vpa-recommendation.md` includes the `kubectl describe vpa fastapi-vpa` output showing the `Target`, `Lower Bound`, and `Upper Bound` recommendations.
- A comparison table: your current `requests` (cpu/memory) vs. the VPA `Target`.
- A decision: keep, raise, or lower each request, with the reasoning (over-provisioned wastes money on Autopilot and node headroom on Standard; under-provisioned risks OOMKill / throttling).
- A one-sentence note on why you ran VPA in `Off`, not `Auto`, given the HPA is also present.

**Hint.** The VPA needs a few minutes of real load to produce a meaningful recommendation; an idle Deployment gives you the floor. Run the load *before* you read the recommendation.

**Estimated time.** 40 minutes.

---

## Problem 6 — Teardown audit: find the orphan

**Problem statement.** Deliberately create the orphan trap: deploy a `Service type=LoadBalancer` in front of the FastAPI Deployment on a Standard cluster, then run `terraform destroy` on the cluster *without* deleting the Service first. Find the orphaned forwarding rule that survives, then clean it up. Document the trap and the correct teardown order.

**Acceptance criteria.**

- `notes/teardown-audit.md` shows the orphaned resource after `terraform destroy`: `gcloud compute forwarding-rules list` (or `target-pools` / `backend-services`) listing a rule that Terraform did not own and did not delete.
- The note explains *why* it orphaned: the LB resources were created by the in-cluster `Service`/cloud-controller-manager, not by Terraform, so `terraform destroy` of the cluster does not remove them.
- The note states the correct teardown order: `kubectl delete service <lb-service>` (wait for the LB to deprovision), *then* `terraform destroy`.
- The orphan is cleaned up; a final `gcloud compute forwarding-rules list` is empty.

**Hint.** Watch the forwarding rule appear with `gcloud compute forwarding-rules list -w`-style polling when you apply the LB Service, and confirm it disappears when you `kubectl delete service` it. That is the resource that bills you overnight if you forget.

**Estimated time.** 35 minutes.

---

## Rubric

| Criterion | Weight | What earns full marks |
|---|---|---|
| **Correctness** | 40% | Each problem's acceptance criteria are met and the evidence (command output, files) is committed. |
| **Reasoning** | 25% | The notes explain *why*, not just *what* — decision order in P1, auth-n vs auth-z in P2, the stall mechanism in P3, the crossover logic in P4. |
| **Production discipline** | 20% | No key files anywhere (P2). The teardown order is correct and the orphan is cleaned (P6). Costs use real current prices (P1, P4). |
| **Clarity** | 15% | The notes are readable by a teammate who did not do the homework. Tables where tables belong; one-sentence conclusions that commit to an answer. |

A passing homework is **≥70%** with **no key file committed anywhere** (an automatic fail of the production-discipline criterion) and **P6's orphan cleaned up** (leaving a billing orphan in your repo's evidence is a fail).

---

*Commit each problem's notes under `notes/` so you can point a reviewer at them. The cost numbers (P1, P4) and the teardown discipline (P6) are the two things a hiring manager actually reads from this homework.*
