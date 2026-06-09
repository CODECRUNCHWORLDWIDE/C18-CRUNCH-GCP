# Lecture 2 — The connectivity decision: shared VPC vs peering vs Network Connectivity Center

> **Reading time:** ~75 minutes. **Hands-on time:** ~50 minutes (you attach a service project to a host project's shared VPC, then peer two VPCs and watch routes propagate).

Lecture 1 left you with one global VPC and the reflex *"a VPC is global; a subnet is regional."* That reflex answers a lot of questions. It does not answer the question this lecture is about: **when is one VPC the wrong boundary, and how do you connect two of them?**

You will reach for a second VPC sooner than you think. The moment you have more than one team, more than one project that needs to own its own firewall posture, or a regulatory line that says "the PCI workload's network must be administered separately from everything else," one VPC stops being enough. GCP gives you three tools to connect VPCs (and on-prem): **shared VPC**, **VPC peering**, and **Network Connectivity Center (NCC)**. They are not interchangeable. Choosing the wrong one is a multi-quarter migration to undo. This lecture is the decision framework, with the failure modes that make the decision real.

The one-sentence version, which you should be able to recite by Friday:

> **Shared VPC** centralizes one network under a host project that many service projects consume. **Peering** connects two independent VPCs as equals, non-transitively, with no overlapping ranges. **NCC** is a managed hub that connects many spokes — VPCs, HA VPN, Interconnect, even SD-WAN — without a quadratic mesh of peerings.

Everything below is the *why* and the *when* behind that sentence.

## 2.1 — Why you end up with more than one VPC

In Lecture 1 the global VPC made cross-region traffic free of topology. So why not put everything in one VPC forever? Four forces push you to split:

1. **Administrative blast radius.** A firewall rule, a route, or a subnet change in a VPC affects *every* workload in that VPC. If your data team and your edge team share one VPC, a data-team engineer who fat-fingers a `0.0.0.0/0` ingress rule has just exposed the edge team's bastions too. Separating networks separates the blast radius.

2. **Delegated administration without delegated ownership.** You want a central platform team to own IP planning, firewall posture, Cloud NAT, and the on-prem connection — *the network* — while a dozen application teams deploy VMs, GKE clusters, and load balancers *into* that network without being able to change it. That is exactly the shared-VPC model: the host project owns the network; service projects consume it.

3. **Compliance / sovereignty boundaries.** A PCI-DSS cardholder-data environment, a HIPAA workload, or an EU-data-residency requirement frequently mandates that the regulated workload's network be administratively distinct and auditable in isolation. A separate VPC (often in a separate project under a separate folder, per Week 01) gives you that boundary and the IAM and VPC Service Controls (Week 14) to enforce it.

4. **Acquisitions and partners.** You acquire a company that already runs on GCP with its own VPC and its own `10.0.0.0/8` plan that overlaps yours. You cannot merge those into one VPC — the ranges collide. You connect them, carefully, and plan a re-IP over the next year.

Each of these is a different connectivity problem, and each points at a different one of the three tools. Let's take them one at a time.

## 2.2 — Shared VPC: one network, many consumers

**Shared VPC** lets an organization connect resources from multiple projects to a *common* VPC, so they communicate over internal IPs from that network. There are two project roles:

- The **host project** owns the shared VPC. The platform/network team administers it: subnets, routes, firewall rules, Cloud NAT, Cloud Router, the on-prem connection.
- A **service project** is *attached* to the host project. Its resources (VMs, GKE nodes, internal load balancers) draw IPs from the host's subnets but the compute lives in the service project — its own quota, its own IAM, its own billing line.

The grant that makes this work is `roles/compute.networkUser`. You give a service project's principals (or its whole project) `networkUser` on a *specific subnet* (or the whole host project). That's the least-privilege control: the data team's service project gets `networkUser` on the `data-subnet` only, not on the edge team's subnets.

Here is the wiring in Terraform. Note that you enable the host *first*, then attach service projects, then grant subnet-level `networkUser`:

```hcl
# 1. Designate the host project. This is the project that owns the VPC.
resource "google_compute_shared_vpc_host_project" "host" {
  project = var.host_project_id
}

# 2. Attach a service project to the host. Compute in this project can now
#    draw IPs from the host's subnets (subject to the networkUser grant below).
resource "google_compute_shared_vpc_service_project" "data" {
  host_project    = google_compute_shared_vpc_host_project.host.project
  service_project = var.data_service_project_id
}

# 3. Grant the data team's principals networkUser on ONE subnet only.
#    This is the least-privilege control: they can use this subnet, nothing else.
resource "google_compute_subnetwork_iam_member" "data_team_networkuser" {
  project    = var.host_project_id
  region     = "us-central1"
  subnetwork = google_compute_subnetwork.data.name
  role       = "roles/compute.networkUser"
  member     = "group:data-team@crunch.example.com"
}

# 4. GKE in a service project also needs the host project's GKE service agent
#    to have networkUser, so the cluster can program firewall rules and use
#    alias IPs. This is the single most-forgotten grant in shared-VPC GKE.
resource "google_compute_subnetwork_iam_member" "gke_agent_networkuser" {
  project    = var.host_project_id
  region     = "us-central1"
  subnetwork = google_compute_subnetwork.data.name
  role       = "roles/compute.networkUser"
  member     = "serviceAccount:service-${var.data_service_project_number}@container-engine-robot.iam.gserviceaccount.com"
}
```

### When shared VPC is the right call

- You have a **central platform team** that should own the network and a set of application teams that should consume it but not change it. This is the textbook case and the most common one in mature GCP orgs.
- You want a **single Cloud NAT / single on-prem connection / single firewall posture** to serve many projects. One host project's Cloud Router + HA VPN serves every attached service project — you do not stand up a VPN per team.
- You want **per-team project isolation for IAM, quota, and billing** while keeping **one network**. Service projects are separate projects (separate IAM, separate quota, separate billing sub-accounts) on a shared network.

### The failure modes of shared VPC

1. **It's organization-scoped — you need an org.** Shared VPC requires a GCP organization (host and service projects must be in the same org). A single standalone project (the solo-learner track) cannot use shared VPC. If you have no org, you use peering between two standalone-project VPCs instead.

2. **The host project becomes a chokepoint of authority.** Every subnet, every firewall rule, every NAT config flows through the host project's admins. If that team is a bottleneck, application teams feel it as "I filed a ticket to open a port three days ago." The fix is delegation via *hierarchical firewall policies* (Lecture 1's §1.5 mechanic, applied here): the org/folder owns the must-have deny rules; teams own the allow rules in their own service-project context where you let them.

3. **The forgotten GKE service-agent grant.** A GKE cluster in a service project on a shared VPC needs the *host* project's container-engine robot SA to have `networkUser` (step 4 above) **and** `roles/container.hostServiceAgentUser` on the host project. Forget either and cluster creation fails with an opaque permission error. This is the single most common shared-VPC-GKE support ticket; memorize it.

4. **You cannot nest host projects.** A host project cannot itself be a service project of another host. The topology is one level deep: host → service projects. If you wanted a tree, you wanted folders + multiple host projects + peering between them.

## 2.3 — VPC peering: two networks as equals

**VPC Network Peering** connects two VPCs so that resources in each can reach the other over internal IPs, as if they were one network — *but the two VPCs remain independently administered*. Each side keeps its own firewall rules, its own routes, its own admins. Peering exchanges *subnet routes* (and, optionally, custom routes) between the two.

The three rules that define peering, and that you must internalize:

1. **Peering is symmetric and must be configured on both sides.** You create a peering from A → B *and* from B → A. Until both halves exist, the peering is `INACTIVE`. One-sided peering does nothing.

2. **Peering is non-transitive.** If A peers with B and B peers with C, A **cannot** reach C through B. Routes do not chain. This is the rule that kills the naive "hub VPC" design: you cannot make a star of peerings where the center forwards between spokes. (That is exactly what NCC exists to do — §2.4.)

3. **No overlapping IP ranges.** Two peered VPCs may not have overlapping primary or secondary subnet ranges. There is no NAT in peering — the IPs must be globally unique across the peered set. This is why the acquired-company scenario (§2.1) is painful: their `10.0.0.0/8` collides with yours and you must re-IP one side before you can peer.

The Terraform, both halves:

```hcl
# Half 1: prod VPC peers TO the analytics VPC.
resource "google_compute_network_peering" "prod_to_analytics" {
  name         = "prod-to-analytics"
  network      = google_compute_network.prod_vpc.id
  peer_network = google_compute_network.analytics_vpc.id

  # Export this VPC's custom (static + dynamic) routes to the peer, and import
  # theirs. Off by default — peering exchanges only subnet routes unless you
  # opt in. Turn these on when one side learns on-prem routes via Cloud Router
  # that the other side also needs.
  export_custom_routes = true
  import_custom_routes  = false
}

# Half 2: analytics VPC peers BACK to prod. Both halves required.
resource "google_compute_network_peering" "analytics_to_prod" {
  name                 = "analytics-to-prod"
  network              = google_compute_network.analytics_vpc.id
  peer_network         = google_compute_network.prod_vpc.id
  export_custom_routes = false
  import_custom_routes  = true
}
```

After both halves apply, confirm the peering went `ACTIVE` and that routes propagated:

```bash
gcloud compute networks peerings list --network=prod-vpc \
  --format="table(name, network.basename(), peerNetwork.basename(), state, stateDetails)"
# STATE should read ACTIVE. INACTIVE means the other half is missing.

# The peer's subnet routes now appear as PEERING-type routes in your VPC:
gcloud compute routes list --filter="network:prod-vpc AND nextHopPeering:*" \
  --format="table(destRange, nextHopPeering)"
```

### When peering is the right call

- You have **two (or a few) VPCs that must talk**, each owned by a team that wants to keep administering its own network. Equals, not host/consumer.
- You **cannot use shared VPC** because the two VPCs are in different organizations, or one is a standalone project, or org policy forbids the host/service relationship.
- The **graph is small and flat** — two, three, maybe four VPCs in a full mesh. Beyond that, the quadratic-edge problem (next paragraph) makes NCC the better tool.

### The failure modes of peering

1. **Non-transitivity forces a quadratic mesh.** To fully connect N VPCs with peering, you need N×(N−1)/2 peerings — 4 VPCs is 6 peerings, 6 VPCs is 15, 10 VPCs is 45. Each is two Terraform resources you must keep in sync. This is exactly the scaling wall NCC removes.

2. **No overlapping ranges, ever.** This is the hard one in mergers. You must re-IP before you peer, and re-IP is a maintenance project, not a `terraform apply`.

3. **Peering limits.** There is a cap on peerings per VPC (in the dozens) and on the total routes exchanged. You will not hit it with three VPCs; you will hit it with a mesh of fifty, which is the other reason to reach for NCC at scale.

4. **Custom-route export is off by default.** If the prod VPC learns an on-prem route via its Cloud Router but you forgot `export_custom_routes = true`, the analytics VPC will reach prod's *subnets* but not prod's *on-prem networks*. "I can ping the VM but not the on-prem database it fronts" is the classic symptom.

## 2.4 — Network Connectivity Center: the managed hub

**Network Connectivity Center (NCC)** is GCP's hub-and-spoke connectivity product. You create one **hub**, then attach **spokes** to it. A spoke can be a VPC, an HA VPN tunnel, a Cloud Interconnect attachment (VLAN), or a router appliance (SD-WAN). The hub provides **transitive connectivity** between spokes — the thing peering explicitly will not do.

The headline capability, stated against peering's limitation: with NCC, if VPC-A, VPC-B, and VPC-C are all spokes on the same hub, **A can reach C through the hub.** You connect N VPCs with N spokes, not N²/2 peerings. The hub does the route propagation.

```hcl
# 1. The hub. One per connected domain (often one per org, or one per
#    environment if you want a hard transitivity boundary between dev and prod).
resource "google_network_connectivity_hub" "main" {
  name        = "crunch-hub"
  project     = var.host_project_id
  description = "Transitive hub for all production VPC spokes"
}

# 2. A VPC spoke. Attaching prod-vpc as a spoke makes its subnets reachable
#    from every other VPC spoke on this hub, transitively.
resource "google_network_connectivity_spoke" "prod" {
  name     = "prod-vpc-spoke"
  project  = var.host_project_id
  location = "global"          # VPC spokes are global; VPN/Interconnect spokes are regional
  hub      = google_network_connectivity_hub.main.id

  linked_vpc_network {
    uri = google_compute_network.prod_vpc.self_link
    # Optionally exclude specific subnet ranges from being exported to the hub.
    # exclude_export_ranges = ["10.10.250.0/24"]
  }
}

resource "google_network_connectivity_spoke" "analytics" {
  name     = "analytics-vpc-spoke"
  project  = var.host_project_id
  location = "global"
  hub      = google_network_connectivity_hub.main.id

  linked_vpc_network {
    uri = google_compute_network.analytics_vpc.self_link
  }
}
```

After apply, prod and analytics reach each other *and* anything else on the hub, with no per-pair peering:

```bash
gcloud network-connectivity hubs list-spokes crunch-hub \
  --format="table(name, spokeType, state)"
# Each spoke should read ACTIVE.
```

### When NCC is the right call

- You have **many VPCs** (and/or on-prem links) that must form a connected mesh. The crossover point where NCC beats a peering mesh is roughly **four or more VPCs**, or **any topology that mixes VPCs with VPN/Interconnect spokes**.
- You want **transitive** connectivity — a true hub where any spoke reaches any other — which peering structurally cannot give you.
- You are stitching **hybrid connectivity** (on-prem via HA VPN or Interconnect) into the same fabric as your VPCs. NCC treats a VPN tunnel and a VPC as the same kind of thing: a spoke.

### The failure modes of NCC

1. **It still respects the no-overlap rule.** NCC does not NAT between spokes. Overlapping ranges across spokes break it the same way they break peering. The acquired-company re-IP problem does not go away because you chose NCC.

2. **Transitivity can be *too* much.** Once everything is on one hub, every spoke can reach every other spoke (subject to firewall rules). If your dev VPC and prod VPC are on the same hub, you have created a path between them you may not have wanted. The mitigation is **multiple hubs** (a dev hub and a prod hub) or **spoke groups / route-table scoping**, plus firewall rules — but the default is full transitivity, so design the hub boundary deliberately.

3. **It's a newer, more complex product.** More moving parts than peering, a larger IAM surface, and behavior that has shifted across GCP releases. For two VPCs that will stay two VPCs, NCC is over-engineering; peering is simpler and you should use it.

## 2.5 — The decision table

This is the artifact to keep. When someone asks "shared VPC, peering, or NCC?", you answer from this table and then justify with the failure modes above.

| Question | Shared VPC | Peering | NCC |
|---|---|---|---|
| **Who owns the network?** | One central host project; service projects consume it. | Each VPC owns itself; equals. | Each spoke VPC owns itself; the hub owns route propagation. |
| **Requires an org?** | Yes (host + service in same org). | No (works for standalone projects, cross-org). | Yes (hub lives in a project; spokes can be cross-project). |
| **Transitive?** | N/A (one network). | **No** — A↔B and B↔C does not give A↔C. | **Yes** — that's the point. |
| **Overlapping ranges allowed?** | N/A (one address plan). | No. | No. |
| **Scales to N VPCs?** | N/A (still one network). | Quadratic peerings; painful past ~4. | Linear spokes; built for many. |
| **Mixes in VPN / Interconnect?** | The host's Cloud Router does, for all service projects. | Per-VPC; custom-route export needed. | Yes — VPN/Interconnect are first-class spokes. |
| **Best when…** | A platform team owns the network for many app teams. | Two or three independent VPCs must talk. | Many VPCs + hybrid, needing a transitive mesh. |
| **Worst when…** | No org; or you want truly independent network admins. | More than ~4 VPCs; or you need transitivity. | Only two VPCs (over-engineered); or you need overlap-tolerant NAT (use PSC instead). |

### The two-question shortcut

In an interview or a design review, you can get to the right answer with two questions:

1. **"Is there one team that should own the network for everyone else?"** If yes → **shared VPC**. The whole product is "centralize the network, decentralize the compute."
2. If no: **"How many networks, and do they need transitivity?"** Two or three, no transitivity → **peering**. Four-plus, or transitivity, or hybrid → **NCC**.

If neither fits — for example, two VPCs with *overlapping* ranges that you cannot re-IP — none of these three is the answer. That's a **Private Service Connect** problem (Lecture 1 §1.8): PSC publishes a service across the boundary with a private endpoint in the consumer's own range, and it tolerates overlapping address space because it does not require route exchange. You'll build PSC for real in Weeks 07 and 11; recognize the shape now.

## 2.6 — A worked example: the Crunch landing zone

Tie it back to Week 01's landing zone. You have three folders — `bootstrap/`, `shared/`, `workloads/` — and five projects. Here is the connectivity design that falls out of this lecture:

- The **`shared/` folder** holds the **host project** with the production shared VPC (the one from Lecture 1: multi-region subnets, Cloud NAT, Cloud Router, PGA, hierarchical firewall policy). This is what the mini-project builds.
- The **`workloads/` folder** holds **service projects** — one per application team — each *attached* to the host project's shared VPC, each granted `networkUser` on only the subnet(s) it needs. The Week 06 GKE cluster and the Week 05 MIG will live in these service projects, drawing IPs from the host's subnets.
- The **analytics workload** that needs hard administrative isolation (think: a future regulated dataset) gets its **own VPC** in its own project and **peers** to the host VPC for the one path it needs — non-transitively, so the analytics team's network mistakes cannot reach the rest of the org.
- If, by Week 14, you have grown to many VPCs plus an on-prem HA VPN, you migrate the peering mesh to an **NCC hub**. You will *not* do that this course — but you will sketch it, because "here's how this scales past where we are" is exactly the architecture-review answer a staff engineer wants.

Shared VPC is the spine. Peering is the exception you reach for under isolation pressure. NCC is the scaling answer you keep in your back pocket. That ordering — shared by default, peer the exceptions, NCC at scale — is the opinionated stance of this course, and it is the right default for the vast majority of GCP orgs.

## 2.7 — The reflexes to internalize this week

- **Shared VPC centralizes the network; service projects consume it.** Default to it when one team owns the network for many.
- **Peering is non-transitive and overlap-intolerant.** Two halves required. Great for two or three VPCs; a quadratic mess past four.
- **NCC is the transitive hub.** Reach for it at four-plus VPCs or when stitching hybrid links into the same fabric.
- **Overlapping ranges break peering and NCC both.** If you cannot re-IP, the answer is PSC, not a connectivity product.
- **The forgotten GKE host-service-agent grant** is the #1 shared-VPC-GKE failure. `networkUser` on the subnet *and* `container.hostServiceAgentUser` on the host project.
- **Design the transitivity boundary on purpose.** One NCC hub means everything reaches everything. Split hubs (dev/prod) when you want a hard line.

---

## Lecture 2 — checklist before moving on

- [ ] I can recite the one-sentence definition of shared VPC, peering, and NCC, and place each on the decision table.
- [ ] I can attach a service project to a host project's shared VPC in Terraform and grant subnet-scoped `networkUser`.
- [ ] I can state why peering is non-transitive and what that costs at N VPCs (the N²/2 mesh).
- [ ] I can explain why NCC gives transitivity that peering cannot, and the one risk that creates (everything reaches everything).
- [ ] I can name the two grants a shared-VPC GKE cluster needs on the host project.
- [ ] I can recognize the case where *none* of the three is the answer (overlapping ranges, no re-IP) and name PSC as the alternative.

If any box is unchecked, return to that section before the exercises.

---

**References cited in this lecture**

- Shared VPC overview: <https://cloud.google.com/vpc/docs/shared-vpc>
- Provisioning shared VPC: <https://cloud.google.com/vpc/docs/provisioning-shared-vpc>
- VPC Network Peering: <https://cloud.google.com/vpc/docs/vpc-peering>
- Network Connectivity Center overview: <https://cloud.google.com/network-connectivity/docs/network-connectivity-center/concepts/overview>
- Choosing a network connectivity product: <https://cloud.google.com/network-connectivity/docs/how-to/choose-product>
- Shared VPC + GKE (service-agent grants): <https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-shared-vpc>
- Private Service Connect overview (the overlap-tolerant alternative): <https://cloud.google.com/vpc/docs/private-service-connect>
- `google_compute_shared_vpc_service_project`: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_shared_vpc_service_project>
- `google_network_connectivity_spoke`: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/network_connectivity_spoke>
