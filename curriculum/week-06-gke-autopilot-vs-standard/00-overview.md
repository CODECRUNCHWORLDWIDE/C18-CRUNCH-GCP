# Week 6 — GKE: Autopilot vs. Standard

Welcome to **C18 · Crunch GCP**, Week 6. Phase 1 made you fluent in the platform's load-bearing primitives: Week 01 gave you the project/folder hierarchy and a billing budget that pages before your CTO does; Week 02 made Workload Identity Federation the only way you authenticate a deploy; Week 03 built the shared VPC with Cloud NAT and Private Google Access that every workload from now on lives inside; Week 04 turned all of it into a reusable Terraform module library; Week 05 put a regional managed instance group of VMs behind an internal load balancer and taught you when a VM is still the right answer. This week we deploy the compute primitive that most production GCP shops actually run their services on: **Google Kubernetes Engine**.

By Friday you should be able to stand up a GKE cluster two different ways — Autopilot (Google runs the nodes, you pay per pod) and Standard (you run the nodes, you pay per VM) — deploy the same Python FastAPI service to both, wire in-cluster Workload Identity so a pod reads a GCS object **with no key file anywhere**, protect that service with a PodDisruptionBudget so a node drain never takes you to zero replicas, autoscale it on requests-per-second with a Horizontal Pod Autoscaler reading a custom metric, and run an in-place minor-version upgrade on the Standard cluster with surge configuration that does not drop a single request. You should also be able to do the harder thing: produce a **cost number** for each option and defend the choice in an architecture review.

The first thing to internalize is that **Autopilot and Standard are not two products — they are two operating models for the same product.** A GKE cluster has a control plane (the API server, scheduler, controller-manager, and etcd, all run and SLA'd by Google in both modes) and a data plane (the nodes your pods run on). The only real difference between Autopilot and Standard is *who owns the nodes*. In Standard you create node pools, pick machine types, set autoscaling bounds, and pay for the VMs whether or not pods are scheduled on them. In Autopilot you never see a node; you submit pods with resource requests, Google provisions exactly the capacity those requests need, and you pay per vCPU-second and GiB-second of *requested pod resources* plus a small per-pod premium. Everything else — the upgrade story, Workload Identity, PodDisruptionBudgets, HPA, the networking model — is shared. That is why this week teaches them side by side: once you understand the node-ownership axis, the rest of GKE is one body of knowledge with two billing models bolted on.

The second thing to internalize is that **Autopilot's constraints are the product, not a limitation to route around.** Autopilot forbids privileged containers, restricts `hostPath` and `hostNetwork`, mandates resource requests on every container, enforces a minimum pod size (currently 0.25 vCPU / 0.5 GiB at general availability), rejects DaemonSets that need node-level access it does not allow, and pins you to a Google-managed node OS and a curated set of machine classes. Every one of those constraints exists so Google can take operational responsibility for the nodes — and so Google can bin-pack your pods onto shared infrastructure and charge you only for what you request. If your workload fits the constraints, Autopilot is almost always cheaper *in total cost of ownership* than a Standard cluster you have to patch, autoscale, right-size, and upgrade yourself. If your workload needs a feature Autopilot forbids — a privileged sidecar, a GPU/TPU configuration Autopilot does not yet expose, a `DaemonSet` that mounts the host, a sub-0.25-vCPU pod, or per-node tuning — then the constraint costs you the feature and you reach for Standard. Lecture 1 is the decision framework, with a worked cost model in both directions.

The third thing to internalize is that **a GKE cluster is a long-lived stateful artifact, and the way you change it in production is the upgrade story, not `terraform destroy && terraform apply`.** The control plane upgrades on Google's schedule (you can pause it inside maintenance windows and exclusions, but you cannot skip minor versions). The nodes upgrade on a strategy *you* choose, and the four strategies — surge (the default), blue-green, short-lived node-pool recreate, and the Autopilot-managed path — trade money against availability in ways you must be able to quantify. Surge with `maxSurge=1, maxUnavailable=0` costs you one extra node's worth of compute for the duration of the upgrade and drops zero capacity; `maxSurge=0, maxUnavailable=1` costs nothing extra but removes a node's worth of capacity at a time; blue-green doubles your node footprint for the upgrade window but gives you an instant rollback. Lecture 2 walks all four with the exact availability arithmetic, and Exercise 3 makes you run a real one with `hey` hammering the service the whole time, proving zero traffic loss.

This is the cluster Phase 3 builds on. The mini-project this week — a regional Standard cluster with a spot node pool, Workload Identity, HPA, and a PDB, provisioned via the Week 04 modules on the Week 03/05 VPC — is **the long-lived artifact that Weeks 10, 12, and 13 explicitly extend rather than rebuild.** Week 10 lands BigQuery data the cluster's services query; Week 12 serves a model from a pod on this cluster's spot pool; Week 13 instruments every service on it with OpenTelemetry. You will tear it down at the end of this week (the teardown gate is non-negotiable) and stand it back up from Terraform in Week 10. Treat the Terraform you write this week as production code you will read again in a month.

## Learning objectives

By the end of this week, you will be able to:

- **Diagram** the GKE architecture from memory: the Google-managed control plane (API server, scheduler, controller-manager, etcd) versus the data plane (node pools in Standard, invisible managed nodes in Autopilot), and explain what Google's SLA covers in each mode.
- **Decide** Autopilot vs. Standard for a real workload and back the decision with a monthly cost number, naming the specific Autopilot constraint that would force Standard if one applies.
- **Provision** a GKE Autopilot cluster and a GKE Standard cluster (the latter with a private endpoint and a spot node pool) with Terraform on the `google` provider, on top of the Week 03 shared VPC.
- **Deploy** a Python FastAPI service to GKE as a Deployment + Service, with correct readiness/liveness/startup probes and resource requests that Autopilot will accept.
- **Configure** a `PodDisruptionBudget` so that a voluntary disruption (node drain, upgrade, autoscale-down) can never take the service below a defined minimum availability.
- **Wire** in-cluster Workload Identity end to end: a Kubernetes ServiceAccount bound to a Google service account via the cluster's Workload Identity pool, so a pod reads a GCS object using its ambient identity with **zero key files**.
- **Autoscale** the service with a `HorizontalPodAutoscaler` reading a custom requests-per-second metric exported to Cloud Monitoring, and explain how HPA differs from and conflicts with VPA.
- **Run** an in-place GKE minor-version upgrade of a Standard cluster's control plane and a node pool with surge configuration (`maxSurge` / `maxUnavailable`), proving zero traffic loss with a load generator running throughout.
- **Quantify** the availability and dollar cost of each of the four node-upgrade strategies (surge, blue-green, recreate, Autopilot-managed) and pick the right one for a given SLO.

## Prerequisites

- **Weeks 01 through 05 of C18 complete.** You have a landing zone (Week 01), Workload Identity Federation for deploys (Week 02), a multi-region shared VPC with Cloud NAT, Private Google Access, and secondary ranges for pods and services (Week 03), a Terraform module library with remote state in GCS (Week 04), and a regional MIG behind an internal LB (Week 05). This week's Terraform consumes the Week 03 VPC module and the Week 04 conventions directly.
- **Working CLI:** `gcloud` `>= 470.0.0` with the `gke-gcloud-auth-plugin` component installed, `kubectl` `>= 1.31`, `terraform` `>= 1.9` (or `tofu >= 1.8`), `helm >= 3.16`, and `docker` (or `podman`) to build the service image. Verify with the smoke check in Exercise 1.
- **Kubernetes fluency at the C15 level.** You can read `kubectl describe pod` to debug a `CrashLoopBackOff`, write a Deployment and a Service YAML from memory, explain what a readiness probe does versus a liveness probe, and reason about resource requests vs. limits. This week is *GCP's* take on Kubernetes; it assumes you already know Kubernetes.
- **Python 3.11+ and FastAPI basics.** The service we deploy is a small FastAPI app. You should be able to read `async def` route handlers and a `uvicorn`/`gunicorn` entrypoint. We provide the code; you should not be learning FastAPI this week.
- **A GCP project with billing and a budget alert armed (Week 01).** GKE control planes for Autopilot and the first zonal Standard cluster fall under the free management tier; you pay for the nodes and the Autopilot pod resources. Everything in this week runs inside the \$300 free trial if you honor the teardown gate. Budget ~\$3–5 if you leave a cluster running overnight by accident.

## Topics covered

- **GKE cluster architecture.** The control plane Google runs and SLAs (regional vs. zonal control plane, the 99.95% regional SLA), etcd, the API server endpoint (public, private, or both), and the data plane: node pools, node auto-provisioning, the GKE-managed node OS (Container-Optimized OS, `containerd` runtime).
- **Autopilot vs. Standard, the operating-model axis.** Who owns the nodes, who patches them, who pays for idle capacity, and the GA Autopilot constraint list (resource-request mandate, minimum pod size, no privileged containers, restricted `hostPath`/`hostNetwork`, curated machine classes, managed DaemonSet allowlist).
- **The Autopilot cost model.** Per-pod-resource billing (vCPU-second, GiB-second, ephemeral storage), the per-pod premium, the "balanced" vs. "scale-out" vs. "performance" compute classes, and how spot pods map onto Autopilot's spot pricing.
- **The Standard cost model.** Per-VM billing regardless of pod scheduling, the management-fee-free first cluster, spot/preemptible node pools (~60–91% discount), node auto-provisioning, and right-sizing with VPA recommendations.
- **In-cluster Workload Identity.** The cluster Workload Identity pool (`PROJECT.svc.id.goog`), the KSA→GSA binding via `roles/iam.workloadIdentityUser`, the `iam.gke.io/gcp-service-account` annotation, the metadata-server interception that issues short-lived tokens, and why this replaces every exported key file.
- **PodDisruptionBudgets.** `minAvailable` vs. `maxUnavailable`, voluntary vs. involuntary disruptions, how a PDB gates `kubectl drain` and node-pool upgrades, and the classic deadlock (a PDB that can never be satisfied blocks an upgrade forever).
- **Horizontal Pod Autoscaler.** Scaling on CPU, on memory, and on **custom/external metrics** via the Custom Metrics Stackdriver Adapter; the `behavior` block for scale-up/scale-down stabilization; the interaction with cluster autoscaler and Autopilot's pod-driven provisioning.
- **Vertical Pod Autoscaler.** Recommendation mode vs. auto mode, why VPA-auto and HPA-on-CPU conflict, and how Autopilot uses VPA-style request adjustment under the hood.
- **The four upgrade strategies.** Surge upgrades (`maxSurge`/`maxUnavailable`), blue-green upgrades (the soak/rollback window), the recreate/short-lived-pool pattern, and Autopilot's fully-managed upgrade path. Release channels (Rapid/Regular/Stable/Extended), maintenance windows, maintenance exclusions, and the version-skew policy.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract. The cluster work is best done in daylight with a billing dashboard open in a second tab — GKE nodes cost money the whole time they run, and the discipline of "stand it up, use it, tear it down" is part of the skill.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | GKE architecture; Autopilot vs Standard decision framework  |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Deploy FastAPI to Autopilot; PodDisruptionBudgets           |    1.5h  |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Wednesday | In-cluster Workload Identity; HPA on a custom metric        |    1.5h  |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Upgrade strategies; surge config; run a live upgrade        |    1h    |    1.5h   |     1h     |    0.5h   |   1h     |     1h       |    0.5h    |     6.5h    |
| Friday    | Mini-project — regional Standard cluster via Week 04 modules |    0h    |    0h     |     1h     |    0.5h   |   0h     |     3.5h     |    0.5h    |     5.5h    |
| Saturday  | Mini-project deep work; cost report; teardown gate          |    0h    |    0h     |     0h     |    0h     |   0h     |     3.5h     |    0h      |     3.5h    |
| Sunday    | Quiz, architecture-review writeup, polish                   |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0.5h    |     2.5h    |
| **Total** |                                                             | **6h**   | **7h**    | **3h**     | **3.5h**  | **4h**   | **12.5h**    | **3h**     | **35.5h**   |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | GKE docs, the Autopilot/Standard comparison page, Workload Identity, PDB/HPA/VPA, upgrade strategy docs, the `terraform-google-modules` GKE module, and the talks worth your time |
| [lecture-notes/01-autopilot-constraints-and-the-cost-model.md](./02-lecture-notes/01-autopilot-constraints-and-the-cost-model.md) | When Autopilot's constraints save you money and when they cost you a feature you needed — the decision framework with a worked cost model in both directions |
| [lecture-notes/02-the-four-gke-upgrade-strategies.md](./02-lecture-notes/02-the-four-gke-upgrade-strategies.md) | The four GKE upgrade strategies and what each costs in availability — surge, blue-green, recreate, Autopilot-managed, with the exact arithmetic |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-fastapi-on-autopilot-with-a-pdb.md](./03-exercises/exercise-01-fastapi-on-autopilot-with-a-pdb.md) | Deploy a FastAPI service to a GKE Autopilot cluster and configure a PodDisruptionBudget |
| [exercises/exercise-02-workload-identity.py](./03-exercises/exercise-02-workload-identity.py) | A FastAPI app that reads a GCS object using in-cluster Workload Identity — no key file — plus the manifests and the verification harness |
| [exercises/exercise-03-surge-upgrade.tf](./03-exercises/exercise-03-surge-upgrade.tf) | Terraform for a Standard cluster + node pool with surge config, and the runbook to perform an in-place minor-version upgrade with zero traffic loss |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-autopilot-vs-standard-bakeoff.md](./04-challenges/challenge-01-autopilot-vs-standard-bakeoff.md) | Deploy the same service to Autopilot and to Standard-with-spot; configure WI, HPA on RPS, and a PDB; measure and compare cold-start, scale-out time, and monthly cost |
| [quiz.md](./05-quiz.md) | 13 questions, answer key at the bottom |
| [homework.md](./06-homework.md) | Six problems with rubric and time estimates |
| [mini-project/README.md](./07-mini-project/00-overview.md) | Full spec for the long-lived regional Standard cluster that Weeks 10, 12, and 13 extend |

## The teardown promise

C18 treats `terraform destroy` as a contract, and Week 06 is where the contract starts to bite — GKE nodes are the first thing in this course that costs real money per hour. Every exercise, the challenge, and the mini-project ends with an explicit teardown step. The mini-project teardown is a **gate**: you do not pass the week until you have run `terraform destroy` and confirmed in the Cloud Console that no GKE clusters, no orphaned node pools, no leaked persistent disks, and no leaked external IPs remain in the project.

```
gke clusters: 0 · node pools: 0 · disks: 0 · external IPs: 0  →  PASS
```

The one nuance: because Weeks 10, 12, and 13 *rebuild* this cluster from the same Terraform, your teardown must be **clean and replayable**. A teardown that leaves Terraform state pointing at deleted resources, or that requires you to hand-delete something in the console, is a failed teardown. The grader runs `terraform apply` from your Week 06 code in Week 10; if it does not come back up identically, you lose the points then, not now.

## What's not here

Week 06 introduces GKE as a compute primitive. It does **not** cover:

- **Service mesh (Istio / Anthos Service Mesh / Cilium mesh).** mTLS between services, traffic-splitting, and L7 mesh policy are a C22 (Crunch Mesh) topic. We use plain Kubernetes Services and a GKE Ingress at most this week.
- **Multi-cluster (Fleet, Multi-Cluster Ingress, Config Sync / GitOps).** One regional cluster is plenty for this course; fleets are a scaling concern we name and defer.
- **GKE networking deep internals (Dataplane V2 / eBPF, NEG details, container-native LB internals).** We *use* container-native load balancing via NEGs and we *use* Dataplane V2 (it is the Autopilot default), but the eBPF internals are out of scope. Week 08 covers the load-balancing layer in depth.
- **Stateful workloads on GKE (StatefulSets, persistent volumes, CSI drivers, regional PDs).** Our service is stateless by design — state lives in GCS, BigQuery, and (later) Spanner. Stateful Kubernetes is a large topic we deliberately avoid so the cluster stays cheap and disposable.
- **Binary Authorization and the secure deploy path.** That is Week 14 (security hardening). This week we get the cluster running; Week 14 locks down what is allowed to run on it.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **GKE Autopilot overview** end to end and make a personal list of every constraint, then check each one against a workload you run at your day job: <https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview>.
- Read the **GKE node upgrade strategies** page and reproduce the blue-green node-pool upgrade by hand (not in this week's exercise — Exercise 3 does surge): <https://cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies>.
- Skim the **`terraform-google-modules/terraform-google-kubernetes-engine`** module source and note how it parameterizes the difference between Autopilot and Standard. You will use this module in the mini-project: <https://github.com/terraform-google-modules/terraform-google-kubernetes-engine>.
- Read the **Custom Metrics Stackdriver Adapter** README and trace how an HPA on a custom metric resolves through the `external.metrics.k8s.io` API: <https://github.com/GoogleCloudPlatform/k8s-stackdriver/tree/master/custom-metrics-stackdriver-adapter>.
- Watch a recent **"GKE the hard way" / GKE deep-dive** talk from Google Cloud Next and note where the speaker's defaults differ from this week's.

## Up next

Continue to **Week 07 — Cloud Run, Cloud Functions, and the serverless decision** once you have torn the mini-project down cleanly. Week 07 asks the question this week sets up: now that you can run a service on GKE, *should you?* For a stateless FastAPI service that scales to zero overnight, Cloud Run is often the cheaper and simpler answer, and Week 07 gives you the cost curve that decides it. The Autopilot-vs-Standard cost reasoning you build this week is the same muscle you use to decide GKE-vs-Cloud-Run next week — only the axes change.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
