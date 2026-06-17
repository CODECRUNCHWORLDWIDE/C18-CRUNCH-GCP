# Lecture 1 — The Global VPC: subnets, routes, firewalls, Cloud NAT, and Private Google Access

> **Reading time:** ~80 minutes. **Hands-on time:** ~70 minutes (you build a custom-mode VPC, attach Cloud NAT, and turn on Private Google Access from Terraform).

This is the lecture that rewires the AWS habits out of your head. If you have never touched AWS, you have an advantage this week — you have nothing to unlearn. If you have run VPCs on AWS for years, the single most important sentence in this course is the next one, and you should read it three times:

**A Google Cloud VPC is a global resource. One VPC spans every region on Earth. Subnets are regional and live inside that one global VPC.**

Everything in this lecture is a consequence of that sentence. By the end you will be able to stand up a custom-mode VPC with regional subnets and GKE-ready secondary ranges, read the routes GCP generates for you, write firewall rules that bite the right traffic, attach a Cloud Router and Cloud NAT so private instances reach the internet for egress, and turn on Private Google Access so those same private instances reach `*.googleapis.com` without ever touching the public internet.

## 1.1 — Global VPC vs regional VPC: the model, stated precisely

In AWS, a VPC is **regional**. You create a VPC in `us-east-1`. Its CIDR block, its subnets, its route tables, its security groups — all of it is scoped to that one region. To get a resource in `us-west-2` onto "the same network," you create a *second* VPC in `us-west-2` and join the two with **VPC peering** or a **Transit Gateway**. Cross-region traffic between your own services traverses an explicit peering connection that you provisioned, that you pay for per-GB, and that you can misconfigure.

In Google Cloud, the VPC is **global**. You create one VPC. It has no region. Inside it you create **subnets**, and *each subnet* is pinned to one region. A VM in a `us-central1` subnet and a VM in a `europe-west1` subnet, both in the same VPC, can talk to each other over their internal RFC 1918 addresses **with no peering, no transit gateway, no extra route**, because they are already on the same network. The traffic rides Google's private global backbone between regions.

Here is the difference in one diagram, in words:

```
AWS                                  GCP
---                                  ---
VPC (us-east-1)  ──peering──  VPC    VPC (global)
  subnet us-east-1a          (us-     subnet  us-central1   (regional)
  subnet us-east-1b           west-2) subnet  europe-west1  (regional)
                              subnet           subnet  asia-east1    (regional)
                              us-west-2a
```

On AWS the *VPC* is the regional thing and you peer VPCs to span regions. On GCP the *subnet* is the regional thing and the VPC already spans regions for free.

### Why this matters for cross-region service-to-service traffic

Three concrete consequences, in order of how often they bite:

1. **No peering tax for your own cross-region traffic.** A service in `us-central1` calling a service in `us-east1` inside the same VPC needs no peering connection and no route you have to author. Internal IPs are routable across the whole VPC by default (subject to firewall rules). On AWS the same call requires a peering or Transit Gateway you stood up and pay an hourly charge for. *You still pay GCP for inter-region egress bytes* — global VPC is not free networking, it's free *topology*. The bytes between `us-central1` and `us-east1` are billed at the inter-region rate. But you do not provision or manage a connection.

2. **One firewall surface, one route table, for the whole globe.** Because there is one VPC, there is one set of routes and (for legacy rules) one firewall surface across every region. That is powerful and dangerous. A `0.0.0.0/0` allow-ingress rule you wrote "just for the dev subnet in us-central1" applies to *every* subnet in *every* region in that VPC unless you scope it with target tags or service accounts. We come back to this in §1.5; it is the most common self-inflicted wound of the week.

3. **Regional vs global load balancers map cleanly onto this.** Because the network is global, GCP can offer a genuinely *global* external HTTPS load balancer with a single anycast IP that fronts backends in multiple regions. AWS's equivalent requires Global Accelerator stitched in front of regional load balancers. You'll build the global LB in Week 08; the reason it's possible is the global VPC you're learning now.

The mental cost of the global VPC is that **isolation is opt-in, not the default**. On AWS, two services in two regions are isolated until you peer them. On GCP, two services in one VPC are connected until you firewall them apart. If you want AWS-style hard isolation in GCP, you use *separate VPCs* (and then, if they must talk, you peer them or put them on a shared VPC or NCC — that's Lecture 2). Choose isolation deliberately; it is not handed to you.

## 1.2 — Auto-mode vs custom-mode, and why production is always custom-mode

When you create a VPC, GCP offers two modes:

- **Auto-mode.** GCP automatically creates one `/20` subnet in *every* region, drawn from a predefined `10.128.0.0/9` block, and keeps adding subnets in new regions as Google launches them. Convenient for a demo. A liability in production: you did not choose the ranges, they may collide with your on-prem or with a peer VPC, and you have subnets in regions you never intended to use.
- **Custom-mode.** GCP creates *no* subnets. You create exactly the subnets you want, in exactly the regions you want, with exactly the CIDRs you choose.

Every production VPC in this course is **custom-mode**. The Terraform flag is `auto_create_subnetworks = false`. Memorize it; forgetting it is a classic "why do I have 40 subnets I didn't ask for" mistake.

```hcl
resource "google_compute_network" "vpc" {
  name                            = "crunch-prod-vpc"
  project                         = var.host_project_id
  auto_create_subnetworks         = false      # custom-mode. Non-negotiable.
  routing_mode                    = "GLOBAL"    # see §1.4
  delete_default_routes_on_create = false       # keep the default internet route
  mtu                             = 1460         # default; 8896 if you want jumbo frames
}
```

Two of those arguments deserve a sentence each. `routing_mode = "GLOBAL"` controls how Cloud Router advertises learned dynamic routes — with `GLOBAL`, a route learned by a Cloud Router in one region is propagated to instances in *all* regions; with `REGIONAL` (the default), only to the same region. For a multi-region VPC where you want a single on-prem connection to serve every region, `GLOBAL` is what you want. `mtu = 1460` is the GCP default; you can raise it to 8896 for jumbo frames if your whole path supports it, but mismatched MTU is a classic source of "large requests hang while small ones work" — leave it at the default unless you have measured a reason.

## 1.3 — Subnets: primary ranges, secondary ranges, and the CIDR discipline

A subnet has one **primary range** (the CIDR that instances get their IPs from) and zero or more **secondary ranges** (extra CIDRs used for GKE alias IPs — one for pods, one for services). Here is a real subnet definition for a region that will eventually host a GKE cluster:

```hcl
resource "google_compute_subnetwork" "central" {
  name          = "crunch-central"
  project       = var.host_project_id
  network       = google_compute_network.vpc.id
  region        = "us-central1"
  ip_cidr_range = "10.10.0.0/20"   # primary: 4094 usable host IPs

  # Private Google Access: instances without external IPs can reach Google APIs.
  private_ip_google_access = true

  # VPC Flow Logs — sampled, exported later (Week 13). Cheap insurance.
  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }

  secondary_ip_range {
    range_name    = "gke-pods"
    ip_cidr_range = "10.20.0.0/16"   # pods: 65k alias IPs — pods are dense
  }
  secondary_ip_range {
    range_name    = "gke-services"
    ip_cidr_range = "10.30.0.0/20"   # services: 4094 ClusterIPs
  }
}
```

### The CIDR math you must get right

The cardinal rule: **no two ranges in the same VPC (or in any VPC you peer with) may overlap.** Not the primaries, not the secondaries, not across regions. Overlap and you get silently broken routing — packets go to the wrong place and nobody gets an error at `apply` time.

Plan the address space on paper before you write any HCL. A workable plan for a three-region VPC:

| Region | Primary | GKE pods (secondary) | GKE services (secondary) |
|---|---|---|---|
| `us-central1` | `10.10.0.0/20` | `10.20.0.0/16` | `10.30.0.0/20` |
| `us-east1` | `10.11.0.0/20` | `10.21.0.0/16` | `10.31.0.0/20` |
| `europe-west1` | `10.12.0.0/20` | `10.22.0.0/16` | `10.32.0.0/20` |

Notice the discipline: the *second octet* encodes the role (1x = primary, 2x = pods, 3x = services), and the *third octet* offset encodes the region. You can read any IP in this VPC and know what it is. Pods get a `/16` (65k addresses) because GKE assigns a `/24` of pod IPs *per node* by default — a 100-node cluster burns 100 `/24`s = a `/17` worth of pod space, so `/16` gives you headroom. Services get a `/20` because ClusterIPs are cheap and you rarely have thousands. Run every range through `ipcalc` before you commit:

```bash
$ ipcalc 10.20.0.0/16
Address:   10.20.0.0
Network:   10.20.0.0/16
HostMin:   10.20.0.1
HostMax:   10.20.255.254
Hosts/Net: 65534
```

A subnet's primary range can be **expanded** later without recreating it (`gcloud compute networks subnets expand-ip-range`), but it cannot be shrunk and secondary ranges cannot overlap the new primary. Plan generously up front; resizing a live subnet is a maintenance window you don't want.

## 1.4 — Routes: system, static, and dynamic

A route answers one question: "for a packet headed to destination D, what is the next hop?" GCP has three kinds.

**System-generated routes.** Created for you, automatically:

- One **subnet route** per subnet, for the subnet's primary and each secondary range, with next-hop "the VPC itself." This is what makes intra-VPC traffic work without any configuration. Priority 0 (the system default for subnet routes), and they cannot be deleted while the subnet exists.
- One **default route** to `0.0.0.0/0` with next-hop "default internet gateway," priority 1000. This is what lets instances *with an external IP* reach the internet. Delete it (or override it with a higher-priority route) and your VPC has no internet egress. We keep it (`delete_default_routes_on_create = false`) and instead control egress with firewall rules and Cloud NAT.

**Custom static routes.** Routes you author. The common case is forcing traffic through an appliance:

```hcl
# Force all internet-bound traffic from tagged instances through a NAT/firewall VM.
resource "google_compute_route" "egress_via_appliance" {
  name              = "egress-via-fw-appliance"
  project           = var.host_project_id
  network           = google_compute_network.vpc.id
  dest_range        = "0.0.0.0/0"
  next_hop_instance = google_compute_instance.fw_appliance.self_link
  priority          = 800             # lower number = higher priority than the default 1000
  tags              = ["route-via-fw"] # only instances with this tag use this route
}
```

**Dynamic routes.** Learned over BGP by a **Cloud Router** (see §1.7) from an on-prem device or a peer. You don't author these; you author the Cloud Router and it learns and installs them.

### Route selection: longest-prefix match, then priority

When multiple routes match a destination, GCP picks using two rules in order:

1. **Longest prefix wins.** A route to `10.20.5.0/24` beats a route to `10.20.0.0/16` for a packet to `10.20.5.7`, because `/24` is more specific than `/16`. This is the same rule every IP router uses.
2. **If prefixes tie, lowest priority number wins.** Priority `100` beats priority `1000`. (Counterintuitive: *lower number = higher priority*. It's a "cost" not a "rank.")

This is why the appliance route above uses `priority = 800` — it ties on prefix with the default `0.0.0.0/0` route (both `/0`) but its lower priority number wins, so tagged instances send internet traffic to the appliance instead of the default gateway.

List the routes GCP computed for your VPC and read them like a Linux `ip route`:

```bash
gcloud compute routes list --filter="network:crunch-prod-vpc" \
  --format="table(name, destRange, priority, nextHopGateway.basename(), nextHopInstance.basename(), nextHopIp)"
```

## 1.5 — Firewall rules without locking yourself out

GCP firewall rules are **stateful** (return traffic for an allowed connection is automatically permitted) and apply at the VPC level. Every VPC has two **implied rules** that you cannot delete:

- **Implied allow egress** to `0.0.0.0/0`, priority 65535. Everything can leave by default.
- **Implied deny ingress** from `0.0.0.0/0`, priority 65535. Nothing can enter by default.

So a fresh VPC: instances can reach out, nothing can reach in. To let traffic in, you write **allow-ingress** rules with a priority lower than 65535.

A firewall rule has: a **direction** (`INGRESS`/`EGRESS`), an **action** (`allow`/`deny`), a **priority** (0–65535, lower wins), a **source** (for ingress: CIDR ranges, source tags, or source service accounts), a **target** (which instances it applies to: all, by tag, or by service account), and the **protocols/ports**.

Here is the canonical "don't lock yourself out" set. Read every comment:

```hcl
# 1. ALWAYS allow IAP TCP forwarding to your SSH/RDP. This is your lifeline.
#    35.235.240.0/20 is Google's published IAP source range. Without this rule,
#    `gcloud compute ssh --tunnel-through-iap` cannot reach your instances and
#    you have locked yourself out of every VM with no external IP.
resource "google_compute_firewall" "allow_iap_ssh" {
  name      = "allow-iap-ssh"
  project   = var.host_project_id
  network   = google_compute_network.vpc.id
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["35.235.240.0/20"]  # IAP's range — do NOT use 0.0.0.0/0 here
  target_tags   = ["allow-iap"]

  allow {
    protocol = "tcp"
    ports    = ["22", "3389"]
  }
  log_config { metadata = "INCLUDE_ALL_METADATA" }
}

# 2. Allow health checks from Google's LB/health-check ranges to your backends.
resource "google_compute_firewall" "allow_health_checks" {
  name          = "allow-health-checks"
  project       = var.host_project_id
  network       = google_compute_network.vpc.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]  # GCP health-check ranges
  target_tags   = ["lb-backend"]
  allow { protocol = "tcp" }
}

# 3. Allow intra-VPC traffic between your own subnets, scoped by tag.
resource "google_compute_firewall" "allow_internal" {
  name          = "allow-internal"
  project       = var.host_project_id
  network       = google_compute_network.vpc.id
  direction     = "INGRESS"
  priority      = 1100
  source_ranges = ["10.10.0.0/14"]   # covers all three regional primaries above
  target_tags   = ["internal"]
  allow { protocol = "tcp"; ports = ["0-65535"] }
  allow { protocol = "udp"; ports = ["0-65535"] }
  allow { protocol = "icmp" }
}
```

### The four lockout patterns, and how to avoid each

1. **Deleting the implied egress and forgetting Cloud NAT depends on it.** If you write an explicit `EGRESS deny 0.0.0.0/0` to "lock down egress," you also block the path Cloud NAT uses. Allow egress to the destinations you need (or to `0.0.0.0/0` and let Cloud NAT be the choke point), don't blanket-deny.
2. **A high-priority deny that shadows your SSH allow.** Priority `100 deny ingress tcp:22 from 0.0.0.0/0` beats your `priority 1000` IAP allow, because 100 < 1000. Order matters: your *allow* for the IAP range must have a *lower* priority number than any broad deny, or the broad deny must explicitly exclude the IAP range.
3. **Targeting by tag but forgetting to tag the instance.** A perfect IAP-allow rule with `target_tags = ["allow-iap"]` does nothing if your bastion VM doesn't carry the `allow-iap` tag. Tag the instance, or target by service account.
4. **Removing external IPs without an IAP path first.** The moment you strip an instance's external IP, your only way in is IAP (or a bastion). If the IAP rule isn't already in place, you're locked out. **Apply the IAP rule before you remove external IPs**, never after.

The senior habit: **before you `terraform apply` anything that changes firewalls or removes external IPs, run a Connectivity Test from Google's IAP range to your bastion on tcp:22.** If it says REACHABLE in the plan-equivalent, you keep your lifeline. You'll do exactly this in Exercise 1.

## 1.6 — Cloud NAT: egress for instances with no external IP

The production default is that **no instance has an external IP**. External IPs are an attack surface and a billing line item. But instances still need to pull container images, hit `pip`/`apt` mirrors, call third-party APIs — they need *egress* to the internet. **Cloud NAT** provides exactly that: source NAT for outbound connections, with no inbound exposure.

Cloud NAT is **not** a box your traffic routes through. It is a *configuration* on a **Cloud Router** that programs the VPC's software-defined data plane to source-NAT outbound packets. There is no NAT instance to size, patch, or fail over. You attach it to a region:

```hcl
resource "google_compute_router" "central" {
  name    = "crunch-central-router"
  project = var.host_project_id
  region  = "us-central1"
  network = google_compute_network.vpc.id

  bgp {
    asn = 64514   # private ASN (64512–65534) — used if you later add VPN/Interconnect
  }
}

resource "google_compute_router_nat" "central" {
  name                                = "crunch-central-nat"
  project                             = var.host_project_id
  region                              = "us-central1"
  router                              = google_compute_router.central.name
  nat_ip_allocate_option              = "AUTO_ONLY"        # GCP manages the external IPs
  source_subnetwork_ip_ranges_to_nat  = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  # Endpoint-independent mapping: a given internal IP+port maps to a stable
  # external IP+port regardless of destination. Turn it OFF for higher port
  # utilization unless a downstream peer requires source-IP+port stability.
  enable_endpoint_independent_mapping = false

  # Per-VM minimum ports. Too low and busy VMs exhaust ports and drop
  # connections ("NAT allocation failed"); too high and you waste the
  # 64k-port-per-external-IP budget. 64 is a sane floor; raise for chatty VMs.
  min_ports_per_vm = 64

  log_config {
    enable = true
    filter = "ERRORS_ONLY"   # or "ALL" while debugging; ERRORS_ONLY in steady state
  }
}
```

Two failure modes to know cold:

- **NAT port exhaustion.** Each external NAT IP has ~64k ports. `min_ports_per_vm` reserves a block per VM. With the default 64 ports/VM and one external IP, you can fan out to ~1000 VMs before you must add IPs. A VM making thousands of concurrent outbound connections (a crawler, a load generator) blows through its block and you see `Dropped` counts in NAT logs and "connection timed out" in the app. Fix: raise `min_ports_per_vm`, enable dynamic port allocation, or add external IPs.
- **Cloud NAT only NATs traffic with no other path.** If an instance *has* an external IP, its egress goes out that IP directly and Cloud NAT is bypassed. Cloud NAT is for instances *without* external IPs. This is why "I added Cloud NAT but my one VM with a public IP still shows its own IP" is expected, not a bug.

## 1.7 — Cloud Router: the managed BGP speaker

You just created a Cloud Router as a prerequisite for Cloud NAT, but its real job is **BGP**. A Cloud Router is a managed router that speaks BGP to peers — your on-prem router over an HA VPN or Cloud Interconnect, or another network. It does two things:

- **Advertises** your VPC's subnet routes (and any custom advertised ranges) to the peer, so the peer knows how to reach your subnets.
- **Learns** the peer's routes and installs them as dynamic routes in your VPC, so your instances know how to reach the peer's networks.

With `routing_mode = "GLOBAL"` on the VPC, routes learned by a Cloud Router in one region propagate to instances in *all* regions (one on-prem link serves the whole global VPC). With `REGIONAL`, only the same region.

You won't stand up a VPN this week, but you *will* read the router's state, because "what routes does this router actually know?" is the question you ask when cross-network traffic mysteriously fails:

```bash
# What is this router advertising and learning right now?
gcloud compute routers get-status crunch-central-router \
  --region=us-central1 \
  --format="yaml(result.bestRoutes, result.bgpPeerStatus)"
```

The output shows `bgpPeerStatus` (is the BGP session `UP`? how many routes received?) and `bestRoutes` (the dynamic routes installed). If a peer's network is unreachable, this is the first place you look: a `DOWN` peer or zero received routes tells you the problem is BGP, not firewall, not DNS. You'll do this for real in the challenge.

## 1.8 — Private Google Access: reaching `*.googleapis.com` privately

Here is the scenario that defines the week. You have a VM with **no external IP** (correct, production-default). It needs to write to a Cloud Storage bucket — i.e., call `storage.googleapis.com`. But `storage.googleapis.com` resolves to a *public* IP, and your VM has no public IP and (if you've locked egress down) no internet path. The call hangs.

**Private Google Access (PGA)** is the fix. It's a per-subnet flag (`private_ip_google_access = true`, which you already set in §1.3). When on, instances in that subnet can reach Google APIs and services over their **internal** IPs, via a special VIP, without needing an external IP and without the traffic leaving Google's network.

There are two VIP ranges:

- **`private.googleapis.com`** → `199.36.153.8/30`. Reaches *most* Google APIs (`storage.googleapis.com`, `bigquery.googleapis.com`, etc.).
- **`restricted.googleapis.com`** → `199.36.153.4/30`. Reaches only APIs that are supported *inside a VPC Service Controls perimeter* (you'll wire this in Week 14).

To make `*.googleapis.com` resolve to the VIP, you point a private Cloud DNS zone at it. The full PGA recipe in Terraform:

```hcl
# 1. The subnet has PGA on (set in §1.3): private_ip_google_access = true

# 2. A route so the VIP range is reachable. The default internet route covers
#    199.36.153.8/30, but if you've removed/overridden the default route, add
#    an explicit route to the VIP via the default internet gateway.
resource "google_compute_route" "private_google_apis" {
  name             = "private-google-apis"
  project          = var.host_project_id
  network          = google_compute_network.vpc.id
  dest_range       = "199.36.153.8/30"
  next_hop_gateway = "default-internet-gateway"
  priority         = 1000
}

# 3. A private DNS zone that overrides *.googleapis.com to the private VIP.
resource "google_dns_managed_zone" "googleapis" {
  name        = "googleapis-private"
  project     = var.host_project_id
  dns_name    = "googleapis.com."
  description = "Route *.googleapis.com to the private VIP"
  visibility  = "private"
  private_visibility_config {
    networks {
      network_url = google_compute_network.vpc.id
    }
  }
}

resource "google_dns_record_set" "googleapis_a" {
  name         = "private.googleapis.com."
  project      = var.host_project_id
  managed_zone = google_dns_managed_zone.googleapis.name
  type         = "A"
  ttl          = 300
  rrdatas      = ["199.36.153.8", "199.36.153.9", "199.36.153.10", "199.36.153.11"]
}

resource "google_dns_record_set" "googleapis_cname" {
  name         = "*.googleapis.com."
  project      = var.host_project_id
  managed_zone = google_dns_managed_zone.googleapis.name
  type         = "CNAME"
  ttl          = 300
  rrdatas      = ["private.googleapis.com."]
}
```

After `apply`, prove it from a VM in the subnet (this is Exercise 2's verification step):

```bash
# DNS must resolve to the private VIP, not a public IP.
$ dig +short storage.googleapis.com
private.googleapis.com.
199.36.153.8

# traceroute must show ONE hop into Google's network, no public-internet transit.
$ traceroute -n 199.36.153.8
traceroute to 199.36.153.8, 30 hops max
 1  199.36.153.8  0.412 ms  0.398 ms  0.371 ms
```

One hop, a `199.36.153.x` address, sub-millisecond: the traffic went straight into Google's network. If `dig` returned a public IP (like `142.250.x.x`) or `traceroute` showed public-internet hops, PGA is not wired correctly — the DNS override or the route is missing.

### PGA is *not* Private Service Connect

This is the distinction Exercise 3 drills, so internalize it now in one sentence each:

- **Private Google Access** is a *subnet flag* that lets instances reach Google's *shared* API VIPs (`*.googleapis.com`) over internal IPs. No per-API endpoint. No private IP *in your subnet* for the API.
- **Private Service Connect (PSC)** creates a *private endpoint with an IP in your own subnet* that maps to a specific published service (a Google API, or a third-party SaaS, or your own service in another VPC). It's a forwarding rule you provision; the API appears to live at an IP you chose inside your range.

You use PGA for "let my private VMs call Google APIs." You use PSC for "give me a private IP *in my VPC* that points at this specific service, so I can firewall it and DNS it as if it were mine," and especially for "let Cloud SQL / a partner SaaS be reachable privately." Both keep traffic off the public internet; they do it at different layers. Week 07 (Cloud Run + Cloud SQL over PSC) and Week 11 (Cloud SQL HA + PSC) use PSC for real; this week, PGA is the tool.

## 1.9 — Putting it together: the minimal correct VPC

Here is the smallest VPC that satisfies the "no lockout" promise from the README — custom-mode, one regional subnet with PGA, Cloud Router + NAT for egress, IAP SSH, and the private DNS for Google APIs. Read it as the spine of this week's mini-project:

```hcl
module "minimal_vpc" {
  source          = "../modules/vpc"   # you build this in the mini-project
  host_project_id = var.host_project_id
  vpc_name        = "crunch-prod-vpc"
  regions = {
    "us-central1" = {
      primary       = "10.10.0.0/20"
      pods          = "10.20.0.0/16"
      services      = "10.30.0.0/20"
      enable_nat    = true
      enable_pga    = true
    }
  }
}
```

Everything in this lecture — custom-mode network, subnet with secondary ranges and PGA, IAP firewall rule, Cloud Router, Cloud NAT, the private-VIP route, and the `*.googleapis.com` DNS override — collapses into that module call. The mini-project is building the module; this lecture is the parts list.

## 1.10 — The reflexes to internalize this week

- **A VPC is global; a subnet is regional.** Say it until it's reflex. Every AWS instinct that fights this sentence is wrong here.
- **Custom-mode, always.** `auto_create_subnetworks = false`. You choose every range.
- **No instance has an external IP.** Egress goes through Cloud NAT; API calls go through Private Google Access.
- **The IAP rule goes in first.** Before you strip external IPs, before any broad deny, the `35.235.240.0/20 → tcp:22` allow exists and your bastion carries the tag.
- **Plan CIDRs on paper, check with `ipcalc`, never overlap.** Across regions, across secondaries, across any peer.
- **Validate with Connectivity Tests, not vibes.** "I think it's reachable" is not an answer. Run the test.
- **Read the route table and the BGP status when traffic fails.** `gcloud compute routes list` and `routers get-status` answer "does the path even exist" before you blame the firewall.

The next lecture takes the global VPC you now understand and asks the harder question: when one VPC isn't the right boundary — when do you reach for a *second* VPC and connect it with shared VPC, peering, or Network Connectivity Center?

---

## Lecture 1 — checklist before moving on

- [ ] I can state, without hedging, why a GCP VPC is global and a subnet is regional, and what that means for cross-region service-to-service traffic.
- [ ] I can write a custom-mode `google_compute_network` and a `google_compute_subnetwork` with primary + two secondary ranges, with non-overlapping CIDRs I verified in `ipcalc`.
- [ ] I can explain the two implied firewall rules and the four lockout patterns, and write an IAP-SSH allow rule from `35.235.240.0/20`.
- [ ] I can attach a Cloud Router + Cloud NAT so a VM with no external IP reaches the internet for egress, and I know the port-exhaustion failure mode.
- [ ] I can enable Private Google Access and verify with `dig` + `traceroute` that `*.googleapis.com` resolves to `199.36.153.8` and stays on Google's network.
- [ ] I can state the one-sentence difference between Private Google Access and Private Service Connect.

If any box is unchecked, return to that section before Lecture 2.

---

**References cited in this lecture**

- VPC network overview: <https://cloud.google.com/vpc/docs/vpc>
- Subnets: <https://cloud.google.com/vpc/docs/subnets>
- Routes overview: <https://cloud.google.com/vpc/docs/routes>
- VPC firewall rules: <https://cloud.google.com/firewall/docs/firewalls>
- Cloud NAT overview: <https://cloud.google.com/nat/docs/overview>
- Cloud Router overview: <https://cloud.google.com/network-connectivity/docs/router/concepts/overview>
- Private Google Access: <https://cloud.google.com/vpc/docs/private-google-access>
- Private access options for services: <https://cloud.google.com/vpc/docs/private-access-options>
- IAP TCP forwarding source range: <https://cloud.google.com/iap/docs/using-tcp-forwarding>
- Google Cloud for AWS professionals — Networking: <https://cloud.google.com/docs/compare/aws/networking>
