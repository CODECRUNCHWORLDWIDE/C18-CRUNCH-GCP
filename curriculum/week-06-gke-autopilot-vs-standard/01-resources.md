# Week 6 — Resources

Every resource on this page is **free**. Google Cloud documentation is free and does not require an account. The Kubernetes docs are open. Terraform and the Cloud Foundation Toolkit modules are open-source on GitHub. No paywalled books are linked.

These docs change. GKE ships features roughly quarterly and the Autopilot constraint list moves. If a page reads differently from this material, **trust the docs and open an issue** so we can update the week.

## Required reading (work it into your week)

- **GKE Autopilot overview** — the canonical statement of what Autopilot is and the full constraint list. Read it before Lecture 1:
  <https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview>
- **Autopilot and Standard comparison** — the side-by-side feature matrix Google maintains:
  <https://cloud.google.com/kubernetes-engine/docs/resources/autopilot-standard-feature-comparison>
- **GKE cluster architecture** — control plane vs. nodes, what Google manages:
  <https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-architecture>
- **Use Workload Identity Federation for GKE** — the in-cluster Workload Identity setup, the metadata server, the KSA→GSA binding:
  <https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity>
- **GKE node upgrade strategies** — surge vs. blue-green, the availability/cost trade-off. Read it before Lecture 2:
  <https://cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies>

## GKE pricing (read it with a calculator open)

The cost numbers in Lecture 1 and the challenge come straight from these pages. Pricing changes; re-check before you quote a number in an architecture review.

- **GKE pricing** — the cluster management fee, Autopilot pod-resource pricing, Standard per-node pricing:
  <https://cloud.google.com/kubernetes-engine/pricing>
- **Compute Engine pricing** — Standard node VMs bill as Compute Engine instances; this is where the per-vCPU/per-GiB numbers live:
  <https://cloud.google.com/compute/all-pricing>
- **Spot VMs pricing and the spot discount** — the 60–91% discount that makes a spot node pool cheap:
  <https://cloud.google.com/compute/docs/instances/spot>
- **Google Cloud Pricing Calculator** — build the side-by-side before you commit:
  <https://cloud.google.com/products/calculator>

## Workload, scaling, and disruption controls

- **Configure a PodDisruptionBudget (Kubernetes docs)** — `minAvailable`/`maxUnavailable`, voluntary vs. involuntary disruption:
  <https://kubernetes.io/docs/tasks/run-application/configure-pdb/>
- **HorizontalPodAutoscaler walkthrough (Kubernetes docs)** — the algorithm, the `behavior` block, custom/external metrics:
  <https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough/>
- **Scaling on custom and external metrics in GKE** — the GCP-specific HPA-on-Cloud-Monitoring path:
  <https://cloud.google.com/kubernetes-engine/docs/how-to/horizontal-pod-autoscaling>
- **Custom Metrics Stackdriver Adapter** — the adapter that surfaces Cloud Monitoring metrics to the HPA via `external.metrics.k8s.io`:
  <https://github.com/GoogleCloudPlatform/k8s-stackdriver/tree/master/custom-metrics-stackdriver-adapter>
- **Vertical Pod Autoscaler in GKE** — recommendation mode vs. auto, and why it conflicts with HPA-on-CPU:
  <https://cloud.google.com/kubernetes-engine/docs/concepts/verticalpodautoscaler>

## Upgrades, channels, and maintenance

- **Release channels** — Rapid / Regular / Stable / Extended and what each commits you to:
  <https://cloud.google.com/kubernetes-engine/docs/concepts/release-channels>
- **Maintenance windows and exclusions** — pinning *when* the control plane and nodes may upgrade:
  <https://cloud.google.com/kubernetes-engine/docs/concepts/maintenance-windows-and-exclusions>
- **Upgrading a cluster** — the actual `gcloud container clusters upgrade` and node-pool upgrade flow:
  <https://cloud.google.com/kubernetes-engine/docs/how-to/upgrading-a-cluster>
- **Kubernetes version and version skew policy** — why you cannot skip a minor version:
  <https://kubernetes.io/releases/version-skew-policy/>

## Terraform & IaC

- **`terraform-google-modules/terraform-google-kubernetes-engine`** — the Cloud Foundation Toolkit GKE module; the mini-project uses the `beta-autopilot-private-cluster` and `private-cluster` submodules:
  <https://github.com/terraform-google-modules/terraform-google-kubernetes-engine>
- **`google_container_cluster` resource** — the raw Terraform resource (read it even though you'll mostly use the module; the module is a thin wrapper):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/container_cluster>
- **`google_container_node_pool` resource** — where `upgrade_settings`, `max_surge`, and `max_unavailable` live:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/container_node_pool>
- **The `google` and `google-beta` provider docs** — Autopilot still needs `google-beta` for a few arguments:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs>

## The service we deploy

- **FastAPI** — the Python web framework for the service in every exercise:
  <https://fastapi.tiangolo.com/>
- **`google-cloud-storage` Python client** — used in Exercise 2 to read a GCS object with the pod's ambient Workload Identity:
  <https://cloud.google.com/python/docs/reference/storage/latest>
- **`google-cloud-monitoring` Python client** — used to export the custom RPS metric the HPA scales on:
  <https://cloud.google.com/python/docs/reference/monitoring/latest>
- **`hey` — the HTTP load generator** — used in Exercise 3 and the challenge to prove zero traffic loss during an upgrade:
  <https://github.com/rakyll/hey>

## Tools you'll use this week

- **`gcloud`** (`>= 470.0.0`) with the `gke-gcloud-auth-plugin` component: `gcloud components install gke-gcloud-auth-plugin`. Verify with `gke-gcloud-auth-plugin --version`.
- **`kubectl`** (`>= 1.31`). `gcloud container clusters get-credentials` writes your kubeconfig.
- **`terraform`** (`>= 1.9`) or **`tofu`** (`>= 1.8`).
- **`helm`** (`>= 3.16`) — used to install the Custom Metrics Stackdriver Adapter in the challenge.
- **`docker`** or **`podman`** — to build and push the FastAPI image to Artifact Registry.

## Videos & talks (free, no signup)

- **Google Cloud Next — GKE keynote and deep-dive sessions** — every session lands on the Google Cloud Tech YouTube channel after the event. Watch a recent "What's new in GKE" and a "GKE Autopilot in production" talk:
  <https://www.youtube.com/@googlecloudtech>
- **"Kubernetes the Hard Way" (Kelsey Hightower)** — not GKE-specific, but the canonical "what the control plane actually does" walkthrough. Read it once to demystify the managed control plane you never see:
  <https://github.com/kelseyhightower/kubernetes-the-hard-way>

## Open-source projects to read this week

You learn more from one hour reading a well-written Terraform module than from three hours of tutorials. Pick one and scroll through:

- **`terraform-google-modules/terraform-google-kubernetes-engine`** — read `modules/beta-autopilot-private-cluster/main.tf` and `modules/private-cluster/main.tf` side by side. The diff between them *is* this week's lecture:
  <https://github.com/terraform-google-modules/terraform-google-kubernetes-engine/tree/master/modules>
- **`GoogleCloudPlatform/microservices-demo`** ("Online Boutique") — a realistic multi-service app that runs on Autopilot; read the manifests for how a production team sets requests, PDBs, and probes:
  <https://github.com/GoogleCloudPlatform/microservices-demo>

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Control plane** | The Google-managed API server, scheduler, controller-manager, and etcd. You never SSH to it. SLA'd at 99.95% for regional clusters. |
| **Node pool** | A group of identical VMs (a managed instance group under the hood) that pods schedule onto. Standard only; Autopilot hides this. |
| **Autopilot** | The operating mode where Google owns the nodes and you pay per requested pod resource. |
| **Standard** | The operating mode where you own the node pools and pay per VM. |
| **Compute class** | An Autopilot pod hint (`balanced`, `scale-out`, `performance`) that selects the machine family Google provisions for the pod. |
| **Workload Identity** | The mechanism that maps a Kubernetes ServiceAccount to a Google service account so pods authenticate with no key file. The pool is `PROJECT.svc.id.goog`. |
| **KSA / GSA** | Kubernetes ServiceAccount / Google service account. Workload Identity binds one to the other. |
| **PDB** | PodDisruptionBudget — caps how many pods of a workload can be *voluntarily* disrupted at once. |
| **HPA** | HorizontalPodAutoscaler — adds/removes pod replicas based on a metric (CPU, memory, or custom). |
| **VPA** | VerticalPodAutoscaler — adjusts a pod's CPU/memory *requests*. Conflicts with HPA-on-CPU. |
| **Surge upgrade** | Node upgrade strategy: add `maxSurge` new nodes, then drain `maxUnavailable` old ones. The default. |
| **Blue-green upgrade** | Node upgrade strategy: stand up a whole new node pool, soak, then cut over. Doubles cost during the window; instant rollback. |
| **Release channel** | Rapid / Regular / Stable / Extended — how aggressively Google auto-upgrades your control plane. |
| **NEG** | Network Endpoint Group — how a GKE Service exposes pod IPs directly to a Google load balancer (container-native LB). |
| **COS** | Container-Optimized OS — the minimal, Google-maintained node OS GKE runs by default. |

---

*If a link 404s, please open an issue so we can replace it.*
