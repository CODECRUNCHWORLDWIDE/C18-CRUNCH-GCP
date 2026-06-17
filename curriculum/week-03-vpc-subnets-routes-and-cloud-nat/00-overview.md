# Week 3 — VPC, Subnets, Routes, and Cloud NAT

Welcome to the networking week. This is the load-bearing week of Phase 1. Week 01 gave you the resource hierarchy; Week 02 gave you the IAM model. This week gives you the *network*, and the network is where production incidents actually live. A misconfigured firewall rule does not show up in `terraform plan` as a problem — it shows up at 3am as "the GKE pods can't reach BigQuery and the on-call doesn't know whether it's DNS, IAM, routing, or a firewall."

By Friday you will be able to stand up a multi-region shared VPC from Terraform, attach Cloud NAT for egress without giving anything a public IP, turn on Private Google Access so a private subnet reaches `*.googleapis.com` without traversing the internet, write firewall rules that bite the right traffic without locking yourself out, and read a Cloud Router's BGP table to confirm the routes you think exist actually exist. You will also be able to answer the single most common GCP networking interview question — *"why can't my GKE pod reach BigQuery?"* — by distinguishing Private Google Access from Private Service Connect on sight.

The mental model that makes this week click, and the one that trips up every engineer arriving from AWS: **a GCP VPC is global, not regional.** One VPC spans every region on Earth. Subnets are regional and live inside that one global VPC. There is no "VPC peering between us-central1 and us-east1" because they are already the same VPC. Internalize that sentence now; the rest of the week is consequences of it.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** why a GCP VPC is a global object with regional subnets, and contrast it precisely with AWS's regional-VPC-plus-peering model — including what each costs for cross-region service-to-service traffic.
- **Design** a subnet layout with a primary range plus secondary ranges for GKE pods and services, and justify the CIDR math (no overlaps, room to grow, RFC 1918 discipline).
- **Choose** between shared VPC, VPC peering, and Network Connectivity Center for a stated connectivity requirement, and defend the choice with the failure modes of each.
- **Write** VPC firewall rules — both the legacy per-VPC kind and hierarchical firewall policies — that allow exactly the traffic a service needs and nothing else, *without* severing your own SSH/IAP path.
- **Configure** Cloud Router and Cloud NAT so a subnet with no external IPs can still reach the internet for egress, with logging armed.
- **Enable** Private Google Access on a subnet and verify, with `dig` and `traceroute`, that `*.googleapis.com` resolves to a private VIP and never leaves Google's network.
- **Diagnose** the "GKE pod can't reach BigQuery" class of failure by ruling out DNS, routes, firewall, Private Google Access, and Private Service Connect in a defensible order.
- **Validate** any network you build with Connectivity Tests (the Network Intelligence Center reachability tool) instead of guessing.
- **Inspect** the routes Cloud Router learns and advertises over BGP, and read a route table the way you'd read a `ip route` on a Linux box.

## Prerequisites

This week assumes you have completed **Week 01** (resource hierarchy, a Terraform-provisioned landing zone with `bootstrap/`, `shared/`, `workloads/` folders) and **Week 02** (IAM, service accounts, Workload Identity Federation). Concretely, before you start:

- You have a GCP organization (or a single billing-linked project for the solo-learner track) and at least two projects you can put a shared VPC across — a **host project** and a **service project**. Week 01's `shared/` and `workloads/` projects are exactly these.
- You can run `terraform plan`/`apply` against the `google` and `google-beta` providers with credentials that resolve via Workload Identity Federation or `gcloud auth application-default login`. No key files.
- You have **billing budgets armed** from Week 01. Cloud NAT and a Cloud Router cost a few cents an hour; the teardown gate at the end of this week is not optional.
- You are comfortable with **CIDR math**: you can split `10.0.0.0/16` into `/20`s in your head well enough to not overlap two subnets. If `10.8.0.0/22` vs `10.8.4.0/22` "do these overlap?" is not instant for you, do the CIDR refresher in `resources.md` first.
- Networking literacy at the README's stated bar: TCP handshake, what a NAT gateway does, the difference between L4 and L7, and what a default route (`0.0.0.0/0`) means.

You do **not** need any prior GCP networking. We start from the global-VPC model. If you carry AWS VPC habits, this week will spend real effort *unlearning* them — that is by design.

## Topics covered

- The global VPC model: one VPC, every region, regional subnets inside it. Why there is no intra-VPC peering.
- Auto-mode vs custom-mode VPCs, and why every production VPC is custom-mode.
- Subnet ranges: the primary range, and secondary ranges for GKE alias IPs (pods + services). The `--secondary-range` flag and the Terraform `secondary_ip_range` block.
- Routes: system-generated routes (subnet routes, the default internet route), custom static routes, and dynamic routes learned by Cloud Router over BGP. Route priority and the longest-prefix-match rule.
- Firewall rules, legacy per-VPC: ingress vs egress, allow vs deny, priority, the two implied rules (allow-egress, deny-ingress), targeting by tag vs by service account.
- Hierarchical firewall policies: org- and folder-level rules that apply before per-VPC rules, with `goto_next` for delegation. When hierarchical beats per-VPC and when it doesn't.
- Shared VPC: host project, service projects, the `roles/compute.networkUser` grant, and who can create what.
- VPC peering: non-transitive, no overlapping ranges, the export/import-custom-routes flags. When peering beats shared VPC.
- Network Connectivity Center (NCC): the hub-and-spoke model for stitching many VPCs and on-prem together, and where it replaces a mesh of peerings.
- Cloud Router: a managed BGP speaker. What it advertises, what it learns, and how to read its route table.
- Cloud NAT: source NAT for egress from private instances. Port allocation, the endpoint-independent-mapping setting, and NAT logging.
- Private Google Access: reaching `*.googleapis.com` and `*.gcr.io`/Artifact Registry from a subnet with no external IP, via `private.googleapis.com` / `restricted.googleapis.com` VIPs.
- Private Service Connect (PSC): the *other* private-access mechanism, for published services and Google APIs via a consumer endpoint — and exactly how it differs from Private Google Access.
- Connectivity Tests (Network Intelligence Center): static reachability analysis you run instead of guessing.
- Cloud DNS basics for the `*.googleapis.com` private zone, enough to make Private Google Access work.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract. The networking concepts are front-loaded because everything downstream depends on them.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Global VPC vs regional VPC; subnets, secondary ranges       |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Routes, firewall rules (legacy + hierarchical)              |    2h    |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0h      |     5.5h    |
| Wednesday | Shared VPC vs peering vs NCC; the connectivity decision     |    1h    |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Thursday  | Cloud Router, Cloud NAT, Private Google Access vs PSC       |    1h    |    1h     |     1h     |    0.5h   |   1h     |     2h       |    0.5h    |     7h      |
| Friday    | Connectivity Tests; BGP route inspection; mini-project work |    0h    |    0.5h   |     1h     |    0.5h   |   1h     |     2.5h     |    0.5h    |     6h      |
| Saturday  | Mini-project deep work (VPC module + teardown gate)         |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, architecture review of a peer's module        |    0h    |    0h     |     0h     |    1h     |   0h     |     0.5h     |    0.5h    |     2h      |
| **Total** |                                                             | **6h**   | **7h**    | **4h**     | **4h**    | **5h**   | **10h**      | **2.5h**   | **38.5h**   |

(The total runs a little hot at ~38h because networking is the week people most regret rushing. If you're on pace, trim the self-study.)

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | Curated GCP docs, RFCs, talks, and tools — all current to 2026 |
| [lecture-notes/01-global-vpc-vs-regional-vpc.md](./02-lecture-notes/01-global-vpc-vs-regional-vpc.md) | Why GCP's VPC is global, what that means for cross-region traffic, subnets, secondary ranges, routes, firewall rules, Cloud Router, Cloud NAT, Private Google Access |
| [lecture-notes/02-shared-vpc-peering-and-ncc.md](./02-lecture-notes/02-shared-vpc-peering-and-ncc.md) | Choosing the connectivity model: shared VPC vs peering vs Network Connectivity Center, with the failure modes of each |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-firewall-without-lockout.md](./03-exercises/exercise-01-firewall-without-lockout.md) | Write firewall rules for a stated service without locking yourself out; validate with Connectivity Tests |
| [exercises/exercise-02-private-google-access.tf](./03-exercises/exercise-02-private-google-access.tf) | Configure Private Google Access so a subnet reaches `*.googleapis.com` privately; verify with `dig` + `traceroute` |
| [exercises/exercise-03-diagnose-pod-to-bigquery.py](./03-exercises/exercise-03-diagnose-pod-to-bigquery.py) | A diagnostic decision-tree tool: "why can't my GKE pod reach BigQuery" — Private Google Access vs Private Service Connect |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-multi-region-shared-vpc.md](./04-challenges/challenge-01-multi-region-shared-vpc.md) | Build a multi-region shared VPC with three subnets, Cloud NAT, Private Google Access, and a hierarchical firewall policy; validate with traceroute and BGP route inspection |
| [quiz.md](./05-quiz.md) | 12 multiple-choice questions with an answer key |
| [homework.md](./06-homework.md) | Six problems with a rubric and time estimates |
| [mini-project/README.md](./07-mini-project/00-overview.md) | Full spec for the reusable VPC module added to the landing zone |

## The "no lockout" promise

Week 7 of C9 had its "build succeeded · 0 warnings" marker. Week 3 of C18 has a harsher one. Every network you stand up this week must satisfy:

```
✓ terraform apply succeeded
✓ Connectivity Test: SSH/IAP path to host → REACHABLE
✓ Connectivity Test: subnet → *.googleapis.com (private VIP) → REACHABLE
✓ Connectivity Test: subnet → 0.0.0.0/0 via Cloud NAT → REACHABLE
✓ No instance in the VPC has an external IP
```

If your `terraform apply` succeeds but you cannot SSH to your own bastion through IAP afterward, you locked yourself out, and you do **not** get to claim the network works. The "without locking yourself out" clause is not a footnote. It is the skill.

## Cost and teardown discipline

This week's live resources are cheap but not free:

- A **Cloud Router** is free. A **Cloud NAT** gateway is billed per-hour plus per-GB processed — order of a few cents per hour. Leave one running for a month and it's a few dollars; leave ten running and forgotten across a course and it's real money.
- The **e2-micro** test VMs you'll use as connectivity probes are in the always-free tier in eligible regions, but two of them in `us-east1` for a week are not.
- **Connectivity Tests** themselves are free to run.
- **Private Google Access** is free — it's a subnet flag, not a billed resource.

Every exercise and the mini-project end with an explicit `terraform destroy` step. The mini-project has a **teardown gate**: you do not get credit for the week until you have shown the `destroy` ran clean and `gcloud compute routers list` returns empty in your project. Treat a forgotten Cloud NAT the way you'd treat a forgotten `print()` in production logging — sloppy, and eventually expensive.

## Stretch goals

If you finish early and want to go deeper:

- Read the GCP **"VPC network overview"** end to end, then the **"Routes overview"** — they are short and they are the source of truth: <https://cloud.google.com/vpc/docs/vpc> and <https://cloud.google.com/vpc/docs/routes>.
- Turn on **VPC Flow Logs** on one subnet, generate some traffic, and export the logs to BigQuery. You'll do the real version of this in Week 13; a preview here is cheap.
- Read the **Network Connectivity Center** docs and sketch (on paper) how you'd connect four VPCs and one on-prem site with NCC vs with a full mesh of peerings. Count the connections in each: <https://cloud.google.com/network-connectivity/docs/network-connectivity-center>.
- Stand up a second Cloud Router with a **custom advertised route** and confirm a peer learns it. This previews the Cloud Interconnect / HA VPN material that the capstone touches.

## Up next

Continue to **Week 04 — Terraform for GCP, end-to-end** once you have pushed the mini-project VPC module and proven the teardown gate. Week 04 takes the module you build this week and folds it into the reusable `modules/vpc` that `envs/dev` and `envs/prod` will consume for the rest of the course. The work compounds — your Week 3 module is the thing Week 4 refactors.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
