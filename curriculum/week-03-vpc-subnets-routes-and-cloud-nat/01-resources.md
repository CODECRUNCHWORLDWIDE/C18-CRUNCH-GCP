# Week 3 — Resources

Everything linked here is **free**. Google Cloud documentation is free and does not require an account. The RFCs are public. The Terraform provider docs are open. No paywalled courses are linked, and you do not need to spend a cent to read any of this.

Read the **Required reading** during the week — it's woven into the lectures and exercises. The rest is reference and depth.

## Required reading (work it into your week)

- **VPC network overview** — the canonical model. Read this first; the global-VPC idea is here in the first three paragraphs:
  <https://cloud.google.com/vpc/docs/vpc>
- **Subnets (VPC network)** — primary range, secondary ranges, the purpose flags:
  <https://cloud.google.com/vpc/docs/subnets>
- **Routes overview** — system routes, custom routes, dynamic routes, priority, longest-prefix match:
  <https://cloud.google.com/vpc/docs/routes>
- **VPC firewall rules overview** — ingress/egress, priority, implied rules, targets:
  <https://cloud.google.com/firewall/docs/firewalls>
- **Cloud NAT overview** — what source NAT does for you and what it does not:
  <https://cloud.google.com/nat/docs/overview>
- **Private Google Access** — the subnet flag that lets a private instance reach Google APIs:
  <https://cloud.google.com/vpc/docs/private-google-access>
- **Private access options for services** — the page that finally disambiguates Private Google Access from Private Service Connect from Serverless VPC Access. Read it twice:
  <https://cloud.google.com/vpc/docs/private-access-options>

## The connectivity-model decision (Lecture 2)

- **Shared VPC overview** — host project, service projects, the `networkUser` role:
  <https://cloud.google.com/vpc/docs/shared-vpc>
- **VPC Network Peering** — non-transitive, no overlaps, custom-route export/import:
  <https://cloud.google.com/vpc/docs/vpc-peering>
- **Network Connectivity Center overview** — hub-and-spoke for many VPCs and on-prem:
  <https://cloud.google.com/network-connectivity/docs/network-connectivity-center/concepts/overview>
- **Choosing a network connectivity product** — Google's own decision page; compare it against Lecture 2's table:
  <https://cloud.google.com/network-connectivity/docs/how-to/choose-product>

## Cloud Router and BGP

- **Cloud Router overview** — the managed BGP speaker, what it advertises and learns:
  <https://cloud.google.com/network-connectivity/docs/router/concepts/overview>
- **View Cloud Router route advertisements / learned routes**:
  <https://cloud.google.com/network-connectivity/docs/router/how-to/viewing-router-details>
- **RFC 4271 — A Border Gateway Protocol 4 (BGP-4)** — you do not need to read all of it, but skim §1 and §3 so "BGP advertises prefixes between autonomous systems" is not a black box:
  <https://datatracker.ietf.org/doc/html/rfc4271>

## Diagnostics (you will use these all week)

- **Connectivity Tests (Network Intelligence Center)** — static reachability analysis. This is the tool that replaces guessing:
  <https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview>
- **VPC Flow Logs** — per-flow logging you can export to BigQuery:
  <https://cloud.google.com/vpc/docs/flow-logs>
- **Firewall Rules Logging** — see which rule allowed or denied a connection:
  <https://cloud.google.com/firewall/docs/firewall-rules-logging>
- **gcloud compute networks subnets / routes / firewall-rules** command reference:
  <https://cloud.google.com/sdk/gcloud/reference/compute/networks>

## The AWS-comparison reading (Lecture 1)

You are likely arriving with AWS habits. These two pages, read side by side, make the global-vs-regional difference concrete:

- **AWS — "What is Amazon VPC?"** (regional by definition):
  <https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html>
- **Google Cloud — "Google Cloud for AWS professionals: Networking"** — Google's own mapping of AWS concepts to GCP ones; honest and useful:
  <https://cloud.google.com/docs/compare/aws/networking>

## CIDR / IP-addressing refresher

If "do `10.8.0.0/22` and `10.8.4.0/22` overlap?" is not instant for you, fix that before Monday:

- **RFC 1918 — Address Allocation for Private Internets** — the `10/8`, `172.16/12`, `192.168/16` ranges you'll use:
  <https://datatracker.ietf.org/doc/html/rfc1918>
- **RFC 4632 — Classless Inter-Domain Routing (CIDR)** — the prefix-length model:
  <https://datatracker.ietf.org/doc/html/rfc4632>
- **`ipcalc`** — a tiny CLI that prints the network/broadcast/host range for any CIDR. `brew install ipcalc` or `apt install ipcalc`. Use it to check your subnet plan.

## GKE networking (you preview it in Exercise 3)

- **GKE — VPC-native clusters and alias IP ranges** — why GKE needs secondary ranges:
  <https://cloud.google.com/kubernetes-engine/docs/concepts/alias-ips>
- **GKE — Private clusters** — the private control plane and node access model:
  <https://cloud.google.com/kubernetes-engine/docs/concepts/private-cluster-concept>

## Terraform / OpenTofu

- **`google_compute_network`** — the VPC resource:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_network>
- **`google_compute_subnetwork`** — subnets and secondary ranges:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_subnetwork>
- **`google_compute_router`** and **`google_compute_router_nat`** — Cloud Router + Cloud NAT:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_router_nat>
- **`google_compute_firewall`** (legacy) and **`google_compute_network_firewall_policy`** + **`google_compute_network_firewall_policy_rule`**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_firewall>
- **The terraform-google-modules `network` module** — the community-standard VPC module; read its source, you'll borrow from it in Week 04:
  <https://github.com/terraform-google-modules/terraform-google-network>

## Tools you'll use this week

- **`gcloud`** — the CLI. `gcloud compute networks describe`, `... routes list`, `... routers get-status`. Verify with `gcloud --version`.
- **`terraform`** (≥ 1.7) or **`tofu`** (OpenTofu ≥ 1.7) — your IaC. The `google` provider is at the 6.x major in 2026; pin it.
- **`dig`** — DNS lookups, to confirm `*.googleapis.com` resolves to a private VIP. Preinstalled on macOS/Linux (`dnsutils` package on Debian).
- **`traceroute`** / **`tracepath`** — to confirm traffic to Google APIs stays on Google's network (one hop, no public transit).
- **`ipcalc`** — CIDR sanity-checks.
- **Python 3.11+** with the **`google-cloud-*`** libraries for Exercise 3's diagnostic tool. `pip install google-cloud-compute`.

## Videos and talks (free, no signup)

- **Google Cloud Tech — "VPC deep dive"** playlist on the official channel. Search "VPC deep dive Google Cloud Tech" on YouTube; the official channel reposts annually:
  <https://www.youtube.com/@googlecloudtech>
- **Google Cloud Next** networking sessions — every Next talk is posted free. Filter for the networking track; the "advanced VPC design" sessions are the relevant ones.
- **"This is My Architecture" / "Architecting with Google Cloud"** — short architecture walkthroughs; the multi-region ones touch shared VPC and NCC.

## Open-source projects to read this week

You learn more from one hour reading a battle-tested VPC module than from three hours of docs:

- **`terraform-google-modules/terraform-google-network`** — the de-facto-standard VPC module. Read `modules/vpc/main.tf` and `modules/subnets/main.tf`:
  <https://github.com/terraform-google-modules/terraform-google-network>
- **Cloud Foundation Toolkit (CFT)** — Google's blessed landing-zone modules; the `net-vpc` and `net-cloudnat` modules are the reference:
  <https://github.com/GoogleCloudPlatform/cloud-foundation-fabric>
- **`terraform-google-modules/terraform-google-cloud-router`** — a focused Cloud Router + NAT module:
  <https://github.com/terraform-google-modules/terraform-google-cloud-router>

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **VPC** | A *global* virtual network in GCP. One VPC spans every region. |
| **Subnet** | A *regional* IP range inside a VPC. Lives in exactly one region. |
| **Primary range** | The main CIDR of a subnet; instances get IPs from it. |
| **Secondary range** | An extra CIDR on a subnet, used for GKE pod and service alias IPs. |
| **Route** | A rule: "to reach destination X, send via next-hop Y." System, static, or dynamic. |
| **Firewall rule** | Allow/deny for traffic, by direction, priority, and target. Stateful. |
| **Hierarchical firewall policy** | Firewall rules attached at the org or folder level, evaluated *before* per-VPC rules. |
| **Shared VPC** | One *host* project owns the network; *service* projects attach to it. |
| **VPC peering** | Two VPCs exchange routes privately. Non-transitive. No overlapping ranges. |
| **NCC** | Network Connectivity Center — a hub that connects many spokes (VPCs, VPN, Interconnect). |
| **Cloud Router** | A managed BGP speaker. Advertises and learns routes dynamically. |
| **Cloud NAT** | Source NAT: lets instances *without* external IPs reach the internet for egress. |
| **PGA** | Private Google Access — a subnet flag; lets a private instance reach Google APIs over a private VIP. |
| **PSC** | Private Service Connect — a consumer endpoint with a private IP for a published service or Google API. |
| **VIP** | Virtual IP — `private.googleapis.com` (199.36.153.8/30) and `restricted.googleapis.com` (199.36.153.4/30). |
| **BGP** | Border Gateway Protocol — how Cloud Router and your peers exchange route prefixes. |
| **ASN** | Autonomous System Number — the identity a BGP speaker advertises under. |
| **Longest-prefix match** | When two routes match, the one with the more specific (longer) CIDR wins. |

---

*If a link 404s, please open an issue so we can replace it. GCP docs URLs are stable but the product names occasionally shift.*
