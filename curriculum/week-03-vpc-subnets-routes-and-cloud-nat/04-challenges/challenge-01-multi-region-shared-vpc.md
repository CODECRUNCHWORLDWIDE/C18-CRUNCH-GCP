# Challenge 1 — Multi-region shared VPC with NAT, PGA, and a hierarchical firewall policy

> **Estimated time:** 2.5–4 hours. This is the syllabus's hands-on lab in full. No step-by-step and no solution — acceptance criteria only. You will lift the structure of this into the mini-project, so build it like you mean it.

## The brief

Stand up, entirely from Terraform, a production-shaped network for the Crunch landing zone:

- A **custom-mode, GLOBAL-routing-mode VPC** in a **host project**.
- **Three regional subnets** — `us-central1`, `us-east1`, `europe-west1` — each with a primary range and two secondary ranges (GKE pods + services), non-overlapping across all three regions.
- **Cloud Router + Cloud NAT in each of the three regions**, so a VM with no external IP in any region can reach the internet for egress.
- **Private Google Access** on all three subnets, with a private Cloud DNS zone overriding `*.googleapis.com` to the `private.googleapis.com` VIP (`199.36.153.8/30`).
- A **hierarchical firewall policy** (folder- or org-attached) that enforces the must-have rules *above* any per-VPC rule: allow IAP SSH from `35.235.240.0/20`, allow Google health-check ranges, and a low-priority deny-all-ingress baseline — with `goto_next` where you want to delegate the rest to per-VPC rules.
- One **`e2-micro` probe VM per region** (no external IP, IAP-reachable) so you can run `traceroute` and prove cross-region reachability.

Then **validate** with Connectivity Tests, `traceroute`, and `gcloud compute routers get-status`, and write up the results.

## Why this is the shape it is

This challenge exists because every later week's compute lands in *this* network. The GKE cluster (Week 06), the MIG (Week 05), the Cloud Run + PSC backend (Week 07) — all of them assume a host VPC that already has multi-region subnets, NAT egress, private API access, and a firewall posture that won't lock anyone out. If you build it sloppily now, you debug it for the next ten weeks. Build the substrate once, correctly.

## Address plan (use this, or justify your own)

Plan on paper before you write HCL. A workable, readable plan:

| Region | Primary | GKE pods (secondary) | GKE services (secondary) |
|---|---|---|---|
| `us-central1` | `10.10.0.0/20` | `10.20.0.0/16` | `10.30.0.0/20` |
| `us-east1` | `10.11.0.0/20` | `10.21.0.0/16` | `10.31.0.0/20` |
| `europe-west1` | `10.12.0.0/20` | `10.22.0.0/16` | `10.32.0.0/20` |

The second octet encodes the role (1x primary, 2x pods, 3x services); the third-octet offset encodes the region. Run each range through `ipcalc` and confirm zero overlaps before you `apply`.

## Acceptance criteria

### Network topology (30%)

- [ ] One custom-mode VPC (`auto_create_subnetworks = false`, `routing_mode = "GLOBAL"`) in the host project.
- [ ] Three subnets in three regions, each with a primary + `gke-pods` + `gke-services` secondary ranges, all non-overlapping (prove with `ipcalc`).
- [ ] `private_ip_google_access = true` on all three subnets.
- [ ] No instance has an external IP. Confirm: `gcloud compute instances list --format="value(name,networkInterfaces[0].accessConfigs[0].natIP)"` shows no NAT IPs.

### Egress and private access (25%)

- [ ] A Cloud Router + Cloud NAT in each of the three regions; NAT logging enabled (`filter = "ERRORS_ONLY"` is fine).
- [ ] A private Cloud DNS zone for `googleapis.com.` with an A record for `private.googleapis.com.` (199.36.153.8–11) and a `*.googleapis.com.` CNAME to it.
- [ ] From a probe VM, `dig +short storage.googleapis.com` resolves to `199.36.153.x` (private VIP, NOT a public `142.250.x.x`).
- [ ] From a probe VM, `curl -s -o /dev/null -w '%{http_code}' https://storage.googleapis.com` returns an HTTP status (does not hang) despite no external IP.

### Hierarchical firewall policy (20%)

- [ ] A `google_compute_firewall_policy` (or network firewall policy attached at folder/org level) with, at minimum:
  - An **allow** rule for IAP SSH from `35.235.240.0/20` on tcp:22, high priority (low number).
  - An **allow** rule for Google health-check ranges (`130.211.0.0/22`, `35.191.0.0/16`).
  - A low-priority **deny** ingress baseline, OR a `goto_next` action that delegates the rest to per-VPC rules — your choice, but defend it in the writeup.
- [ ] The policy is **associated** to the folder/org so it evaluates *before* per-VPC rules. Confirm with `gcloud compute firewall-policies describe`.
- [ ] You can still SSH to every probe VM through IAP after the policy is applied (the lifeline survives the hierarchy).

### Validation (25%)

- [ ] **Connectivity Test — intra-region:** probe-central → probe-central (or a same-region target) on tcp:22 is REACHABLE.
- [ ] **Connectivity Test — cross-region:** probe-central → probe-east on tcp:22 (or icmp) is REACHABLE, proving the global VPC carries cross-region internal traffic with no peering.
- [ ] **Connectivity Test — subnet → VIP:** probe-central → `199.36.153.8` on tcp:443 is REACHABLE.
- [ ] **`traceroute`:** from a probe VM, `traceroute -n 199.36.153.8` shows ONE hop into Google's network (paste it).
- [ ] **BGP / route inspection:** `gcloud compute routers get-status <router> --region=<region>` output is captured (the session has no live BGP peer this week, so expect an empty `bgpPeerStatus` and the system `bestRoutes`; paste it and explain what each field would show once a VPN/Interconnect peer existed). Also paste `gcloud compute routes list --filter="network:<vpc>"` showing the three subnets' system routes and the default route.

### Teardown gate (pass/fail — you do not pass the challenge without it)

- [ ] `terraform destroy` runs clean.
- [ ] `gcloud compute routers list --project=<host>` returns empty.
- [ ] `gcloud compute networks list --project=<host>` does not list the challenge VPC.

## The writeup (`RESULTS.md`)

300–500 words plus pasted command output:

1. The `terraform apply` summary (resource count).
2. The three Connectivity Test results (intra-region, cross-region, subnet→VIP) — the `reachabilityDetails.result` line for each.
3. The `traceroute -n 199.36.153.8` output (the one-hop proof).
4. The `gcloud compute routers get-status` excerpt + a two-sentence explanation of what `bgpPeerStatus` and `bestRoutes` mean.
5. One paragraph defending your hierarchical-policy choice (deny-baseline vs `goto_next` delegation) and *why* a hierarchical policy beats per-VPC rules for the IAP/health-check must-haves (hint: org-wide enforcement that a per-VPC admin cannot accidentally remove).
6. The teardown proof (`routers list` empty).

## Hints (not a solution)

- **Use `for_each` over the region map.** A `regions = { "us-central1" = {...}, ... }` variable and `for_each = var.regions` on the subnet, router, and NAT resources is the clean way to avoid copy-pasting three near-identical blocks. This is the shape the mini-project's module wants, so practice it here.
- **Hierarchical firewall policies are a different resource family** than legacy per-VPC `google_compute_firewall`. Look at `google_compute_firewall_policy`, `google_compute_firewall_policy_rule`, and `google_compute_firewall_policy_association`. The association is the easy-to-forget piece — a policy with no association does nothing.
- **`routing_mode = "GLOBAL"`** is what makes a future single on-prem link serve all three regions. You won't add the link this week, but set it now; changing it later forces route churn.
- **Cross-region Connectivity Test** is the cleanest single proof of the global-VPC model. If `us-central1` → `europe-west1` internal traffic is REACHABLE with no peering anywhere in your config, you have demonstrated the thing this whole week is about.
- **The empty BGP peer status is expected, not a failure.** You have no VPN/Interconnect peer this week. The point is to *read* the router's status and know what it would show — that reading skill is what you'll use when a real peer's routes go missing.

## Going further (no extra grade)

- Attach the analytics-VPC **peering** from Lecture 2 and run a Connectivity Test that proves it is **non-transitive** (a third VPC peered to analytics cannot reach the host VPC through it).
- Turn on **VPC Flow Logs** on the `us-central1` subnet, generate traffic with the cross-region test, and export the logs to BigQuery (you'll do the production version in Week 13).
- Replace the legacy per-VPC firewall rules entirely with a **network firewall policy** and compare the two models' ergonomics. Note which one you'd hand a junior engineer.

---

**References**

- VPC network overview: <https://cloud.google.com/vpc/docs/vpc>
- Hierarchical firewall policies: <https://cloud.google.com/firewall/docs/firewall-policies-overview>
- `google_compute_firewall_policy_rule`: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_firewall_policy_rule>
- Cloud NAT: <https://cloud.google.com/nat/docs/overview>
- Cloud Router get-status: <https://cloud.google.com/network-connectivity/docs/router/how-to/viewing-router-details>
- Connectivity Tests: <https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/how-to/running-connectivity-tests>
- Private Google Access: <https://cloud.google.com/vpc/docs/configure-private-google-access>
