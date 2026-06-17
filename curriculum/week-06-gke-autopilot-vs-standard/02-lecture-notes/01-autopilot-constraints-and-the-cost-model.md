# Lecture 1 — When Autopilot's Constraints Save You Money, and When They Cost You a Feature You Needed

> **Reading time:** ~75 minutes. **Hands-on time:** ~45 minutes (you stand up one Autopilot cluster and price one Standard cluster).

This is the lecture that lets you walk into an architecture review and say "we should run this on Autopilot, and here is the monthly number" — or the opposite — and defend it. Almost every GKE-vs-GKE decision a team makes is really an Autopilot-vs-Standard decision, and almost every Autopilot-vs-Standard decision comes down to two questions: *does my workload fit Autopilot's constraints?* and *does Autopilot's pay-per-pod model cost more or less than a Standard cluster I have to right-size, autoscale, patch, and upgrade myself?* By the end of this lecture you can answer both for a real workload, with numbers, and you can name the specific constraint that would force you off Autopilot if one applies.

## 1.1 — One product, two operating models

Start from the architecture, because the cost model falls out of it. A GKE cluster has two halves:

- **The control plane.** The Kubernetes API server, the scheduler, the controller-manager, and `etcd`. Google runs all of it. You never SSH to it, you never patch it, you never size it. In **both** Autopilot and Standard, Google operates the control plane and SLAs it: 99.95% availability for a *regional* control plane (replicated across three zones), 99.5% for a *zonal* one. You talk to it through the Kubernetes API endpoint, which can be public, private, or both.
- **The data plane.** The nodes — Compute Engine VMs running Container-Optimized OS and the `containerd` runtime — where your pods actually execute.

The control plane is identical between the two modes. **The entire Autopilot-vs-Standard distinction is about who owns the data plane.**

In **Standard**, you create node pools. A node pool is a managed instance group of identical VMs: you pick the machine type (`e2-standard-4`, `n2-standard-8`, `c3-standard-4`, …), the disk, the min and max node count for the cluster autoscaler, whether the pool is spot or on-demand, and the node OS. You pay Compute Engine prices for every VM in the pool, **whether or not a single pod is scheduled on it.** An idle `e2-standard-4` node costs the same as a busy one. Your job is to keep the pool sized so that you have enough headroom to schedule pods without paying for a fleet of empty nodes — which is exactly the job the cluster autoscaler does, imperfectly, and which you tune for the rest of the cluster's life.

In **Autopilot**, you never create a node pool and you never see a node. You submit pods with resource *requests* (`cpu`, `memory`, `ephemeral-storage`), and Google provisions exactly enough capacity to run them, bin-packs your pods onto shared (or sole-tenant, if you pay for it) infrastructure, and bills you for the **sum of your pods' resource requests**, by the vCPU-second and the GiB-second, plus a small per-pod premium and the cluster management fee. There is no idle-node line item because there are no nodes you own to be idle.

This is the whole game. Standard: you pay for VMs and manage them. Autopilot: you pay for pod requests and Google manages the VMs. Everything else in GKE — Workload Identity, PDBs, HPA, VPA, the upgrade story, the networking model — works the same in both modes.

## 1.2 — The constraints are the product

Autopilot can take operational responsibility for your nodes only because it controls what runs on them. Those controls are the **constraints**, and you must know them cold, because a single one of them can force a workload onto Standard. The current general-availability list (check the resources page — it moves):

1. **Every container must declare resource requests.** Autopilot has nothing to bill and nothing to schedule against if you do not. A pod with no requests is mutated to a default or rejected. In Standard, a request-less pod schedules onto whatever node has room; in Autopilot, requests are mandatory. *This is the constraint people hit first, and it is a good one — it forces a hygiene practice you should already have.*
2. **There is a minimum pod size.** At GA, an Autopilot pod's *total* requests are rounded up to at least **0.25 vCPU and 0.5 GiB** of memory (the exact floor depends on the compute class; the "balanced" default is 0.25 vCPU). A pod that requests 50m CPU and 64Mi is billed as if it requested 250m and 512Mi. *If you run hundreds of tiny pods (a per-tenant sidecar, a fleet of small workers), the minimum-pod-size rounding can make Autopilot more expensive than a tightly bin-packed Standard cluster.* This is the most common cost surprise.
3. **No privileged containers, restricted host access.** `privileged: true`, `hostNetwork: true`, `hostPID`, `hostIPC`, and most `hostPath` mounts are forbidden or heavily restricted. A `CAP_NET_ADMIN` sidecar that rewrites `iptables`, a node-exporter DaemonSet that reads `/proc` off the host, a CNI plugin you install yourself — none of these run on Autopilot. *If your observability or security stack needs node-level access, Autopilot costs you that feature.*
4. **A curated machine surface.** You do not pick a machine type; you pick a **compute class** (`balanced`, `scale-out`, `performance`) and optionally a hardware hint (Arm via `scale-out` on `t2a`, GPUs via the GPU compute class). Autopilot exposes a growing but bounded set. *If you need a specific machine family Autopilot does not surface (a particular C3D shape, a niche GPU/TPU topology, sole-tenant nodes for a license), that is a Standard reason.*
5. **A managed, allowlisted DaemonSet surface.** Autopilot runs the DaemonSets *it* needs (logging, monitoring, the metadata server). It allows *your* DaemonSets only if they fit the security model — no host mounts, requests declared, no privileged access. *A DaemonSet that needs the host forces Standard.*
6. **No SSH to nodes, no node-level tuning.** You cannot set kernel sysctls beyond an allowlist, cannot change the node OS, cannot install a custom kubelet config. *If you tune nodes for a database or a latency-sensitive workload, Autopilot is the wrong tool.*

Read that list as a filter, not a wall. For the overwhelming majority of **stateless web/API services** — which is exactly what the FastAPI service in this week's exercises is — every constraint is satisfied trivially: you declare requests (you should anyway), you do not need privilege, you do not need host access, and `balanced` is the right compute class. For those workloads Autopilot is the right default. The constraints only bite when you bring a sidecar, an agent, or a tuning requirement that needs the node.

## 1.3 — The Autopilot cost model, precisely

Autopilot bills three things:

- **The cluster management fee.** A flat per-cluster, per-hour fee (the first cluster per billing account per zone is fee-free under the management-tier policy; check pricing). Same in Standard.
- **Pod resource usage.** The sum of your pods' **requests** — vCPU-seconds, GiB-seconds of memory, and GiB-seconds of ephemeral storage — at the per-unit rate for the pod's compute class. Crucially, it is **requests**, not usage: a pod that requests 1 vCPU and uses 0.1 is billed for 1. This is why right-sizing requests matters more on Autopilot than anywhere else.
- **A spot discount** if you mark the pod for spot (via a `cloud.google.com/gke-spot` toleration / nodeSelector). Autopilot spot pods get the spot discount on their requested resources, with the spot caveat that Google can reclaim them.

The arithmetic for a single steady-state pod that requests `R_cpu` vCPU and `R_mem` GiB, running for `H` hours a month:

```
monthly_pod_cost = H * (R_cpu * price_vcpu_hour + R_mem * price_gib_hour)
```

Round `R_cpu` up to the 0.25 vCPU floor and `R_mem` up to the 0.5 GiB floor first. Multiply by replica count. Add the management fee. That is the whole bill. There is no node line item, no idle headroom, no autoscaler slack to pay for.

## 1.4 — The Standard cost model, precisely

Standard bills the nodes, as Compute Engine instances:

```
monthly_node_cost = node_count * hours_per_month * price_per_node_hour
```

where `price_per_node_hour` is the Compute Engine price for the node's machine type (e.g. an `e2-standard-4` at on-demand list, or ~1/3 of that on spot). Plus the cluster management fee (same as Autopilot). Plus persistent-disk cost for the node boot disks. Critically, `node_count` is the number of VMs you are *running*, not the number your pods *need* — the gap between those two is the headroom you pay for, and the cluster autoscaler's job is to keep it small without ever failing to schedule a pod.

The hidden cost in Standard is not on the bill: it is **the operational labor** of right-sizing the pools, tuning the autoscaler, patching and upgrading the nodes, and reacting when a node pool runs out of room at 2 a.m. Autopilot folds that labor into the per-pod premium. When you compare the two, compare *total* cost of ownership, not just the invoice.

## 1.5 — A worked cost comparison: where Autopilot wins

Take a realistic small service: a FastAPI API that needs **3 replicas** for redundancy, each requesting **0.5 vCPU and 1 GiB**, running **24/7** (730 hours/month). Bursty but never huge.

**Autopilot.** Requests are above the 0.25 vCPU / 0.5 GiB floor, so no rounding. Using representative `us-central1` list rates (re-check pricing — these move; we use round illustrative numbers of \$0.0445/vCPU-hour and \$0.0049/GiB-hour for the balanced class):

```
per-replica vCPU:  0.5 vCPU * $0.0445/vCPU-hr * 730 hr = $16.24
per-replica mem:   1.0 GiB  * $0.0049/GiB-hr  * 730 hr =  $3.58
per-replica total:                                       $19.82
3 replicas:                                              $59.46  / month
```

**Standard.** Three pods at 0.5 vCPU / 1 GiB each total 1.5 vCPU and 3 GiB of *requests*. The smallest sensible node that fits all three with room for the GKE system pods (which themselves request ~0.5 vCPU and ~0.5 GiB per node) and survives a single-node failure is **two** `e2-standard-2` nodes (2 vCPU / 8 GiB each), so that losing one node still schedules all three pods. At a representative `e2-standard-2` on-demand list of ~\$0.0671/hr:

```
2 nodes * $0.0671/hr * 730 hr = $97.97  / month  (on-demand)
```

Autopilot is **~40% cheaper here** *before* you count the labor of patching and upgrading those two nodes yourself — because Autopilot bills the 1.5 vCPU you requested, while Standard bills the 4 vCPU of node capacity you had to buy to host it with failure headroom. **When your requests do not neatly fill a node, you pay Standard for the gap. Autopilot eliminates the gap.** This is the canonical Autopilot win: small-to-medium stateless services where node bin-packing leaves slack.

## 1.6 — A worked cost comparison: where Autopilot loses

Now flip the workload. You run a **batch fleet**: 200 short-lived worker pods, each requesting **50m vCPU and 64Mi** (genuinely tiny — they shell out to a CLI and wait on I/O), bursting up for 4 hours a day.

**Autopilot.** The 0.25 vCPU / 0.5 GiB **minimum-pod-size floor** dominates. Each 50m/64Mi pod is billed as 250m/512Mi:

```
per-pod billed:  0.25 vCPU + 0.5 GiB
200 pods * 4 hr/day * 30 days = 24,000 pod-hours
vCPU: 24,000 * 0.25 * $0.0445 = $267
mem:  24,000 * 0.5  * $0.0049 = $ 59
                                 $326  / month
```

**Standard.** On a tightly bin-packed Standard cluster you schedule those tiny pods many-to-a-node. 200 pods at a real 50m/64Mi each is 10 vCPU and ~13 GiB of *actual* requests, which fits on **two** `e2-standard-8` nodes (8 vCPU / 32 GiB) with room to spare, autoscaled down to zero the other 20 hours a day with the cluster autoscaler. At ~\$0.268/hr per `e2-standard-8`:

```
2 nodes * 4 hr/day * 30 days * $0.268 = $64  / month
```

Standard is **~5× cheaper** here, because the minimum-pod-size floor turns 50m pods into 250m pods on Autopilot, while Standard lets you pack the real 50m requests densely onto large nodes. **When you run many pods far smaller than Autopilot's floor, Autopilot's rounding is the cost.** This is the canonical Autopilot loss: high-count, tiny-pod fleets.

The general rule that falls out of these two examples:

> Autopilot wins when your pods are **medium-sized and your node bin-packing would leave slack.** Standard wins when your pods are **far below the minimum-pod-size floor and you can pack them densely**, or when you can amortize big committed-use-discounted or spot nodes across a steady fleet.

## 1.7 — When the constraint, not the cost, decides

Cost is the tiebreaker. The constraint list is the hard gate. Some real examples of constraints overriding cost:

- **A service-mesh sidecar that needs `NET_ADMIN`.** Istio's older `init` container rewrites `iptables` and needs `NET_ADMIN`. On Autopilot you must use the CNI-based (ambient/sidecarless) install or Google's managed mesh; the classic privileged-init install does not run. If you are committed to the old install, that is a Standard reason regardless of cost.
- **A node-exporter DaemonSet reading host `/proc` and `/sys`.** Your existing Prometheus stack ships a node-exporter that mounts `hostPath: /proc`. Autopilot forbids it. You either replace it with GKE's managed Prometheus (the right move) or you run on Standard.
- **A GPU/accelerator topology Autopilot does not surface.** Autopilot exposes GPUs through its GPU compute class, but if you need a specific multi-GPU NVLink topology or a TPU slice shape it does not yet offer, that is Standard. (Week 12 hits this when we serve a model.)
- **Sole-tenant nodes for a per-core-licensed product.** Some commercial software is licensed per physical core and requires sole tenancy. Autopilot's shared infrastructure cannot give you that; Standard with sole-tenant node pools can.

In each case, the workflow is the same: **check the constraints first, then the cost.** If a constraint disqualifies Autopilot, the cost comparison is moot. If no constraint disqualifies it, run the cost comparison from §1.5/§1.6 and pick the cheaper total cost of ownership.

## 1.8 — Spot changes the arithmetic on both sides

Spot capacity (60–91% off on-demand, reclaimable on ~30 seconds' notice) is available in both modes:

- **Autopilot spot:** add the `cloud.google.com/gke-spot: "true"` nodeSelector (and tolerate the spot taint) and Autopilot bills your pod's requests at the spot rate. No node management; Google handles the spot pool.
- **Standard spot:** create a node pool with `spot = true`. The VMs are spot-priced and the autoscaler manages them. You combine it with a small on-demand pool for the pods that must not be evicted.

For a fault-tolerant, replicated stateless service that can lose a replica without user-visible impact (protected by a PDB so it never loses *all* replicas at once), spot is close to free money — it drops the dominant line item by 60–91%. The mini-project this week runs the service on a **spot** Standard node pool for exactly this reason: it is the cheap, production-realistic default, and the PDB plus multiple replicas absorb the reclamations. The challenge measures whether Autopilot-spot or Standard-spot is cheaper for the same service; the answer depends on whether the pod requests fill the node, which is the §1.5/§1.6 logic applied to spot prices.

## 1.9 — Standing up an Autopilot cluster (so the numbers are real)

Before the exercises, stand up one Autopilot cluster so the cost model is not abstract. With Terraform on the Week 03 VPC (we will do this properly in the exercises; this is the minimal shape):

```hcl
resource "google_container_cluster" "autopilot" {
  provider            = google
  name                = "c18-w6-autopilot"
  location            = "us-central1"          # regional → 99.95% control-plane SLA
  enable_autopilot    = true                   # the one flag that makes it Autopilot
  deletion_protection = false                  # we tear down nightly; never set false in prod

  network    = data.google_compute_network.shared_vpc.id      # Week 03 VPC
  subnetwork = data.google_compute_subnetwork.gke_subnet.id   # Week 03 subnet

  # Autopilot REQUIRES VPC-native (alias IPs). The secondary ranges come from Week 03.
  ip_allocation_policy {
    cluster_secondary_range_name  = "gke-pods"
    services_secondary_range_name = "gke-services"
  }

  # Workload Identity is on by default in Autopilot; we make it explicit.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  release_channel {
    channel = "REGULAR"
  }
}
```

Note what is *absent*: no `node_config`, no `node_pool`, no machine type, no autoscaling bounds. `enable_autopilot = true` is the entire difference. You submit pods; Google finds them homes.

Confirm it came up and that you cannot see nodes you own:

```bash
gcloud container clusters get-credentials c18-w6-autopilot --region us-central1
kubectl get nodes      # you WILL see nodes, but you did not create them and cannot pool them
kubectl get nodes -o jsonpath='{.items[*].metadata.labels.cloud\.google\.com/gke-nodepool}'
# prints the Google-managed default pool name; you never sized it
```

Bill the empty cluster for ten minutes, check the cost dashboard, and you will see the management fee accruing with **zero pod-resource charges** because nothing is scheduled. That is the Autopilot model in one observation: you pay for what you run, and right now you run nothing.

## 1.10 — The decision framework, on one card

Put this on a sticky note. When someone asks "Autopilot or Standard?", run it top to bottom:

1. **Does the workload need a forbidden feature?** Privileged container, host network/path, custom node OS/kernel, an unsupported machine/GPU shape, sole-tenant nodes, a host-mounting DaemonSet? → **Standard.** Stop here.
2. **Are your pods far below 0.25 vCPU / 0.5 GiB, and many of them?** → Lean **Standard** (dense bin-packing beats the floor). Run the §1.6 numbers to confirm.
3. **Are your pods medium-sized and would leave node slack on Standard?** → Lean **Autopilot** (no slack to pay for). Run the §1.5 numbers to confirm.
4. **Do you have the headcount to patch, upgrade, right-size, and on-call the node pools?** If not, weight toward **Autopilot** — it folds that labor into the price.
5. **Is the workload spot-tolerant and replicated behind a PDB?** Then spot is on the table either way; compare Autopilot-spot vs. Standard-spot with the same arithmetic.

The senior move is never "Autopilot is better" or "Standard is better." It is "for *this* workload, the constraint check passes/fails, and the monthly number is \$X on Autopilot versus \$Y on Standard, so we go with Z." Numbers, not taste. You will produce exactly that number in the challenge.

## 1.11 — The control-plane endpoint: public, private, or both

The control plane runs in a Google-managed project, but *you* decide how your network reaches its API endpoint, and on Standard you have three meaningful postures. This matters because the endpoint is the door to your cluster — anyone who can reach it and authenticate can run `kubectl` against your workloads.

- **Public endpoint, no restriction.** The API server has a public IP reachable from anywhere on the internet. Authentication (IAM + the cluster's RBAC) still gates *access*, but the *attack surface* is the whole internet. Acceptable for a throwaway dev cluster, never for production.
- **Public endpoint with master authorized networks.** The API server keeps a public IP, but only the CIDR ranges in your **authorized networks** allowlist may reach it. This is the pragmatic production default for a team that deploys from CI runners and a handful of office/VPN egress IPs: you list those CIDRs and the rest of the internet is refused at the endpoint, before authentication.
- **Private endpoint (`enable_private_endpoint = true`).** The API server has *no* public IP; it is reachable only from within the VPC (and peered networks, and the authorized-networks list applied to internal ranges). Your CI must run inside the VPC (a private Cloud Build worker pool, a bastion, or a self-hosted runner on a VM in the subnet) to reach it. This is the locked-down posture the mini-project uses.

The two flags people confuse:

- `enable_private_nodes` — the **nodes** get no public IPs (they egress via Cloud NAT, which you built in Week 03). This is about the data plane's reachability. You almost always want this `true` in production.
- `enable_private_endpoint` — the **control-plane API endpoint** gets no public IP. This is about who can run `kubectl`. You want this `true` for the strictest posture, but it forces your deploy tooling inside the VPC.

In HCL, the relevant block on a Standard cluster:

```hcl
private_cluster_config {
  enable_private_nodes    = true
  enable_private_endpoint = true                 # API endpoint is VPC-internal only
  master_ipv4_cidr_block  = "172.16.0.0/28"      # /28 for the control-plane peering range
}

master_authorized_networks_config {
  cidr_blocks {
    cidr_block   = "10.8.0.0/20"                 # the Week 03 subnet that hosts your runner
    display_name = "vpc-deploy-subnet"
  }
}
```

The `master_ipv4_cidr_block` is a `/28` carved for the VPC peering between your VPC and the Google-managed control-plane network. It must not overlap any of your subnet ranges (including the Week 03 pod/service secondary ranges) — a `/28` is 16 addresses, which is all the control-plane peering needs. Plan it the way you planned the Week 03 ranges: write it down, never overlap it.

On Autopilot the same private-endpoint options exist, set at creation. The difference, again, is only the node plane: you do not configure `enable_private_nodes` per node pool because there are no node pools — Autopilot clusters created with the private setting give you private nodes by default.

## 1.12 — Workload Identity in-cluster: the mechanism, briefly

Lecture 1 is about choosing and costing the cluster, but the single most important *security* default on either mode is **in-cluster Workload Identity**, and the cost framework should not let you forget it: a key-file-mounting pod is a finding in a security review, on Autopilot *or* Standard. The mechanism — covered hands-on in Exercise 2 — is:

1. Each pod runs as a **Kubernetes service account (KSA)** (the `default` KSA if you do not specify one).
2. You bind that KSA to a **Google service account (GSA)** with an IAM policy: the KSA is granted `roles/iam.workloadIdentityUser` on the GSA, and the KSA is annotated with the GSA's email.
3. When the application inside the pod calls a Google API using Application Default Credentials, the client library contacts the **GKE metadata server** (a link-local endpoint), which checks the binding and mints a **short-lived OAuth token** for the GSA. The token lives ~1 hour, is never written to disk, and carries exactly the GSA's IAM grants.

On **Autopilot**, Workload Identity is on and cannot be turned off — the metadata server is the only credential path, so the secure thing is the *only* thing. On **Standard**, you opt in with `workload_pool` at the cluster and `workload_metadata_config { mode = "GKE_METADATA" }` on each node pool; forget either and the old key-file path is still tempting. Score "mandatory Workload Identity" in Autopilot's favor when you weigh the two — it removes a class of incident entirely. The newer GSA-less `principal://` binding (grant IAM roles directly to the KSA principal, no GSA at all) is the 2026 preference for new work; the classic GSA binding remains common in existing repos.

## 1.13 — VPC-native is not optional, and the secondary ranges are from Week 03

Both Autopilot and modern Standard clusters are **VPC-native**: pods and services get IP addresses from **secondary alias ranges** on the subnet, not from a separate overlay. This is why Week 03 had you carve two secondary ranges — `gke-pods` and `gke-services` — on the `us-central1` subnet, and why this week's clusters reference them by name in `ip_allocation_policy`. The sizing matters and is a one-way door at cluster creation:

- The **pod** secondary range must be large enough for `max_pods_per_node × max_nodes`. The GKE default is 110 pods/node, which consumes a `/24` (256 addresses, GKE allocates a `/24` per node by default for the 110-pod ceiling). A `/16` pod range gives you 256 such `/24`s — room for 256 nodes. Undersize it and you cannot scale the cluster; you cannot resize it later without rebuilding.
- The **services** secondary range caps the number of `ClusterIP` Services. A `/20` (4096 service IPs) is generous for most clusters.

If your Week 03 ranges are too small, fix them in Week 03's module and re-apply *before* creating the cluster — you cannot grow them under a live cluster. This is the most common "I have to rebuild the cluster" mistake in this course, and it is entirely avoidable with five minutes of CIDR planning. The mini-project's `gke` module takes the range names as inputs precisely so the cluster is decoupled from where those ranges live.

## 1.14 — You cannot convert; you migrate

A consequence of "Autopilot and Standard are two operating models" that surprises people: **you cannot convert a cluster from one mode to the other.** There is no `gcloud container clusters update --enable-autopilot` on an existing Standard cluster, and no reverse. If you chose wrong, you create a *new* cluster in the right mode and migrate the workloads — drain traffic, re-point your deploy at the new cluster, delete the old one. For stateless services behind a load balancer this is a routine blue-green at the cluster level (the same idea as the node-pool blue-green in Lecture 2, one level up). For stateful workloads it is real work.

This is the deepest reason the §1.10 decision framework matters: the decision is **semi-permanent**. Getting it right at design time is cheap; getting it wrong means a cluster migration. It is also why the mini-project's long-lived cluster is deliberately **Standard** — Weeks 12 and 13 add a GPU node pool and per-node tuning that Autopilot would forbid, so committing to Standard now avoids a forced migration in three weeks. You proved you can run Autopilot in the exercises; the *artifact* is Standard because the artifact has to grow into features Autopilot does not allow.

## 1.14a — Autopilot compute classes, in detail

Section 1.2 said Autopilot exposes "compute classes" instead of machine types. That abstraction is worth a closer look, because choosing the class is the closest thing Autopilot gives you to a sizing knob, and the wrong default can quietly cost you money or latency.

- **`general-purpose` (the implicit default).** E-series-equivalent shared-core-friendly capacity. The cheapest per-vCPU rate, the broadest availability, the right default for a stateless API that is not latency-critical at the tail. This is what the FastAPI service runs on unless you say otherwise.
- **`balanced`.** N-series-equivalent. A higher per-vCPU rate than general-purpose, more consistent performance, higher per-pod CPU and memory ceilings. Reach for it when general-purpose's bursting model gives you tail-latency you cannot accept.
- **`scale-out`.** Throughput-optimized, available on Arm (`t2a`/Axion-class) and AMD. Often the cheapest *per unit of throughput* for horizontally-scalable, CPU-bound workloads that do not care about single-thread latency. If your service is embarrassingly parallel and you have an Arm-compatible image, `scale-out` on Arm can be the cheapest option Autopilot offers — but you must build a multi-arch image (Exercise 1's image is amd64-only; an Arm variant is a stretch goal).
- **`performance`.** Dedicated (non-shared) capacity on C-series-class machines, for latency-sensitive workloads that need a whole core's worth of predictable performance. The most expensive class. Justify it with a tail-latency SLO, not a hunch.
- **Accelerator classes (GPU/TPU).** For inference and training. Week 12 uses these (with the caveat from §1.7 that some topologies are Standard-only).

You select a class with a `nodeSelector`:

```yaml
      nodeSelector:
        cloud.google.com/compute-class: scale-out
        kubernetes.io/arch: arm64        # only if your image is multi-arch
```

The cost lesson: when you run the §1.5/§1.6 arithmetic for a *real* Autopilot decision, run it against the **class you will actually request**, not the general-purpose default rate, and include the spot setting if the workload tolerates preemption. A `scale-out`-on-Arm-spot Autopilot deployment can be dramatically cheaper than the general-purpose-on-demand number a naive estimate produces — sometimes cheap enough to flip a decision that looked like a Standard win. The challenge this week is graded partly on whether you did the math against the correct class.

## 1.14b — Total cost of ownership: the line item that is not on the invoice

Both §1.5 and §1.6 compared *invoice* costs. The honest comparison includes the cost that never appears on a Cloud Billing export: **the engineering labor of operating Standard's node plane.** On Standard you own:

- **Right-sizing the node pools.** Picking machine types, setting autoscaler min/max, and revisiting them as the workload changes. Get it wrong and you either over-pay for idle nodes or fail to schedule pods at peak.
- **Node upgrades.** Even with auto-upgrade on, you own the *strategy* (Lecture 2), the maintenance window, the PDB tuning, and the incident when an upgrade goes sideways.
- **Node-level incidents.** A node that wedges, a disk that fills, a kernel-level resource leak. On Standard these are yours to diagnose (you can SSH in); on Autopilot they are Google's (you cannot, and do not have to).
- **Capacity planning for spikes.** The autoscaler reacts; it does not predict. A sudden 10× spike that outpaces node provisioning is a Standard problem you tune around. Autopilot has the same physics but Google owns the provisioning.

Put a number on it. If operating a Standard cluster's node plane costs a fraction of one platform engineer's time per month — say, conservatively, a few hours a week of right-sizing, upgrade-watching, and the occasional node incident — that is real money, and it is money Autopilot folds into its per-pod premium. For a small team, the *invoice* difference between Autopilot and Standard is often smaller than the *labor* difference, and the labor difference favors Autopilot. This is the argument that wins the Autopilot case even when the raw invoice math is close: you are not just buying compute, you are buying back engineering hours. The corollary: at large scale, where you employ a platform team that operates the node plane *anyway* for dozens of clusters, the marginal labor of one more Standard cluster approaches zero, and the invoice math (where committed-use + spot + dense packing favors Standard) dominates. **Autopilot's TCO advantage is largest for small teams and shrinks as your platform team grows.**

## 1.14c — Reading the bill: how to tell where the money went

When the GKE line on your billing export surprises you, here is how to diagnose it in each mode.

On **Autopilot**, the bill is the sum of pod requests, so the diagnostic is: *which pods are requesting the most, and are they requesting more than they use?* A pod requesting 2 vCPU that uses 0.2 is paying 10× what it needs. Find them:

```bash
# Requests vs. actual usage per pod (needs metrics-server / managed metrics).
kubectl top pods --all-namespaces
# Compare the USAGE columns against the requests in each pod's spec.
```

Then either lower the requests (and re-verify with a VPA recommendation, §Mini-project) or accept the headroom if the pod genuinely bursts to it. On Autopilot, **over-requesting is the cost**, and the fix is right-sizing requests — which is exactly what the VerticalPodAutoscaler in recommendation mode is for.

On **Standard**, the bill is the node count, so the diagnostic is: *how full are my nodes?* A cluster of mostly-empty nodes is paying for headroom it is not using:

```bash
kubectl describe nodes | grep -A5 "Allocated resources"
# If every node shows ~20% CPU requested, you have ~5× the nodes you need.
```

Then lower the node-pool min, tighten the autoscaler, or use a smaller machine type. On Standard, **idle node capacity is the cost**, and the fix is bin-packing (smaller/fewer nodes, the autoscaler scaling closer to actual demand). The symmetry is exact: Autopilot punishes over-requesting per pod; Standard punishes under-packing per node. Both are right-sizing problems; the unit differs.

## 1.14d — A worked comparison at scale: where committed-use + spot flips it

The §1.5 and §1.6 examples were small. The decision changes shape at scale, and the mechanism is **committed-use discounts (CUDs)** and **spot**, both of which apply to Standard nodes and only narrowly to Autopilot. Walk a realistic mid-size service: **40 replicas at 1 vCPU / 4 GiB each**, steady 24/7, fault-tolerant (tolerates spot reclaims behind a PDB).

**Autopilot, general-purpose, on-demand.** No floor rounding (the pods are well above 0.25 vCPU):

```
vCPU: 40 * 1   * $0.0445 * 730 = $1,299 / month
mem:  40 * 4   * $0.0049 * 730 = $  573 / month
total                          ≈ $1,872 / month
```

**Standard, on-demand, no commitment.** 40 vCPU + 160 GiB of requests pack onto ~5 `n2-standard-16` nodes (16 vCPU / 64 GiB = 80 vCPU / 320 GiB capacity, leaving headroom for system pods and a lost node). At ~\$0.7769/hr per `n2-standard-16`:

```
5 nodes * $0.7769/hr * 730 hr ≈ $2,836 / month   (on-demand, naive)
```

Naively, Standard looks *worse* than Autopilot here ($2,836 vs $1,872) — which is the trap that makes people pick Autopilot at scale without finishing the math. Now apply the two discounts Standard can use and Autopilot mostly cannot:

**Standard, 3-year committed-use discount (~55% off the steady base).**

```
$2,836 * (1 - 0.55) ≈ $1,276 / month   (committed)
```

**Standard, spot node pool (~70% off, fault-tolerant workload).**

```
$2,836 * (1 - 0.70) ≈ $851 / month     (spot)
```

At 40 steady replicas, **Standard with a commitment is cheaper than Autopilot ($1,276 vs $1,872), and Standard on spot is less than half ($851 vs $1,872)** — because CUDs and spot discount the *nodes*, and Autopilot's per-request billing does not get the same leverage. The §1.6 rule, restated for scale: **once a workload is large and steady enough to justify a commitment, or fault-tolerant enough to run on spot, Standard's node-level discounts beat Autopilot's per-request rate.** The crossover is not a fixed replica count — it depends on density, steadiness, and spot-tolerance — which is exactly why you run the numbers per workload instead of memorizing a threshold. The homework (Problem 4) makes you compute the crossover point for a specific pod size; do it, because "Autopilot is cheaper" and "Standard is cheaper" are both true, at different scales, and the only way to know which applies is the arithmetic.

The one caveat that keeps Autopilot honest at scale: the **labor** from §1.14b. The $851 spot Standard number assumes you operate the spot pool, handle reclaims, tune the autoscaler, and own the upgrades. If that labor costs more than the ~\$1,000/month you saved, Autopilot's higher invoice is the cheaper *total*. At a large platform team that operates clusters anyway, the labor is amortized and Standard wins outright; at a three-person startup, the labor is a real tax and the decision is genuinely close. Numbers and headcount, not taste.

## 1.15 — What this sets up

Lecture 2 takes the cluster you can now choose and cost, and answers the next production question: **how do you change it while it is serving traffic?** A cluster is a long-lived artifact; you upgrade it, you do not redeploy it. The four upgrade strategies trade money against availability the same way Autopilot-vs-Standard trades managed-ness against control, and the arithmetic is just as concrete. Read it before Thursday — Exercise 3 makes you run a live upgrade with a load generator proving zero traffic loss, and Lecture 2 is the map for it.

---

**References**

- GKE Autopilot overview (the constraint list): <https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview>
- Autopilot vs. Standard feature comparison: <https://cloud.google.com/kubernetes-engine/docs/resources/autopilot-standard-feature-comparison>
- GKE cluster architecture: <https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-architecture>
- GKE pricing: <https://cloud.google.com/kubernetes-engine/pricing>
- Spot VMs: <https://cloud.google.com/compute/docs/instances/spot>
- Workload Identity Federation for GKE: <https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity>
- Private cluster concepts (endpoint, authorized networks): <https://cloud.google.com/kubernetes-engine/docs/concepts/private-cluster-concept>
- Committed use discounts: <https://cloud.google.com/docs/cuds>
- `google_container_cluster` Terraform resource: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/container_cluster>

> **A closing word on judgment.** This entire lecture refuses to give you a rule like "always Autopilot" or "always Standard," and that refusal is the lesson. The right answer is a function of four inputs — does it fit the constraints, how dense and steady is it, can it run on spot, and how much node-plane labor can your team absorb — and any two of those inputs can point opposite ways. A senior engineer holds all four at once, runs the arithmetic, and produces a sentence: "for this workload, the constraint check passes, it is small and bursty, it tolerates spot, and we are a four-person team, so we run it on Autopilot at roughly \$X/month." The number and the reasoning are the deliverable. The challenge this week grades you on producing exactly that sentence, with *your* number, on *your* clusters. Get comfortable defending it — the architecture review at the end of Week 08 asks you to defend it in front of peers.
