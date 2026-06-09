# Week 3 Homework

Six problems that revisit the week's topics and push a little past the exercises. The full set should take about **5 hours**. Work in your Week 3 Git repository so each problem produces at least one commit you can point to later.

Each problem includes a **problem statement**, **acceptance criteria** so you know when you're done, a **hint**, and an **estimated time**.

> Cost note: Problems 1, 3, 4, and 6 are read/plan/diagram only — zero spend. Problems 2 and 5 create live resources; both end with a teardown step. Keep your Week 01 budget armed.

---

## Problem 1 — Design and defend a three-region address plan

**Problem statement.** Design the IP address plan for a new production VPC that must hold, in each of `us-central1`, `us-east1`, and `asia-southeast1`: a primary subnet range, a GKE pods secondary range, and a GKE services secondary range. The org's existing on-prem network uses `10.0.0.0/12` (`10.0.0.0`–`10.15.255.255`), which you must **not** collide with because it will be peered later. Write the plan as a Markdown table at `notes/address-plan.md`, and for each range, paste the `ipcalc` output proving its bounds. Add two sentences justifying your pod-range size relative to your services-range size.

**Acceptance criteria.**

- [ ] `notes/address-plan.md` has a 9-row table (3 regions × 3 ranges) with no overlaps and no collision with `10.0.0.0/12`.
- [ ] Each range has its `ipcalc` (or equivalent) bounds pasted.
- [ ] A two-sentence justification of pod-range size (denser — `/16`-ish) vs services-range size (sparse — `/20`-ish), referencing GKE's per-node `/24` pod allocation.
- [ ] File committed.

**Hint.** Start your VPC at `10.16.0.0` or higher to clear the `10.0.0.0/12` on-prem block. GKE assigns a `/24` of pod IPs per node by default, so a 100-node cluster needs ~`/17` of pod space — size pods generously, services sparsely.

**Estimated time.** 45 minutes.

---

## Problem 2 — Build and validate Cloud NAT egress (live)

**Problem statement.** From Terraform, create a custom-mode VPC with one `us-central1` subnet (no PGA this time — we are testing NAT specifically), a Cloud Router + Cloud NAT, an IAP-SSH firewall rule, and one `e2-micro` VM with no external IP. SSH in via IAP and prove the VM reaches the internet through NAT by `curl`-ing a public non-Google site. Then deliberately add an `EGRESS deny 0.0.0.0/0` rule, re-test, observe the break, and fix it without blanket-allowing everything.

**Acceptance criteria.**

- [ ] `terraform apply` creates the VPC, subnet, router, NAT, firewall rule, and VM.
- [ ] `gcloud compute ssh <vm> --tunnel-through-iap --command="curl -s -o /dev/null -w '%{http_code}' https://example.com"` returns a 2xx/3xx (NAT egress works).
- [ ] After adding `EGRESS deny 0.0.0.0/0`, the same `curl` fails (times out); your `notes/nat-egress.md` records the before/after.
- [ ] You fix egress by adding a *scoped* egress allow (e.g., to the specific destinations or `0.0.0.0/0` at a lower priority number than the deny) rather than deleting the deny, and the `curl` works again. Document the fix.
- [ ] `terraform destroy` clean; `gcloud compute routers list` empty.

**Hint.** The implied allow-egress is what NAT rides on. A high-priority (low-number) `EGRESS deny 0.0.0.0/0` shadows it. The senior fix is a *more specific* or *lower-priority-number* allow that re-opens only what you need — never a panic-delete of the deny.

**Estimated time.** 60 minutes.

---

## Problem 3 — Read a real route table and explain every row

**Problem statement.** Take the VPC from Problem 2 (or any VPC you have) and run `gcloud compute routes list --filter="network:<your-vpc>" --format="table(name, destRange, priority, nextHopGateway.basename(), nextHopInstance.basename(), nextHopIp, nextHopPeering)"`. Paste the output into `notes/route-table.md` and annotate **every row**: is it a system subnet route, the default internet route, a custom static route, a peering route, or a dynamic route? For each, state its next hop and why it exists.

**Acceptance criteria.**

- [ ] `notes/route-table.md` contains the real `gcloud compute routes list` output.
- [ ] Every row is annotated with its type (subnet / default-internet / static / peering / dynamic) and a one-line explanation.
- [ ] You correctly identify the `0.0.0.0/0 → default-internet-gateway` priority-1000 default route and at least one subnet route (`<your primary CIDR> → <network>`).
- [ ] File committed.

**Hint.** Subnet routes have the subnet's CIDR as `destRange` and the network as the next hop; the default route is `0.0.0.0/0` to `default-internet-gateway` at priority 1000. If you see a `nextHopPeering` value, that row came from a peered VPC.

**Estimated time.** 30 minutes.

---

## Problem 4 — Write the connectivity-model decision memo

**Problem statement.** You are handed four scenarios. For each, choose shared VPC, VPC peering, NCC, or "none of these — use PSC," and justify in 2–3 sentences citing the relevant failure mode. Write the memo at `notes/connectivity-decision.md`.

1. A platform team must own the network (IP planning, firewall, NAT, on-prem link) for eight application teams who deploy GKE and VMs but must not change the network.
2. You acquired a company whose VPC uses `10.0.0.0/8`, which overlaps your `10.0.0.0/8`. The two must exchange traffic for one specific internal API next week; a re-IP is a year out.
3. Twelve VPCs across three environments plus two on-prem sites (HA VPN) must form a transitive mesh, with a hard line between dev and prod.
4. Exactly two independent VPCs, each owned by a team that wants to keep administering its own network, must talk over internal IPs. No overlap, no transitivity needed, no org-wide host project desired.

**Acceptance criteria.**

- [ ] All four scenarios answered with a model and a 2–3 sentence justification.
- [ ] Scenario 1 → shared VPC; 2 → PSC (overlap, no re-IP — neither peering nor NCC works); 3 → NCC (transitive, hybrid, with dev/prod hub split); 4 → peering. Each justification names the failure mode that rules out the alternatives.
- [ ] File committed.

**Hint.** The two-question shortcut from Lecture 2: (a) one team owning the network for everyone? → shared VPC. (b) else: how many networks, and transitivity? Two, none → peering; four-plus / transitive / hybrid → NCC. Overlapping ranges with no re-IP defeats *both* peering and NCC → PSC.

**Estimated time.** 45 minutes.

---

## Problem 5 — Prove Private Google Access end to end with a diagnostic

**Problem statement.** Re-use Exercise 2's PGA setup (or rebuild it). SSH into the probe VM and capture three pieces of evidence into `notes/pga-proof.md`: (1) `dig +short bigquery.googleapis.com` resolving to the private VIP, (2) `traceroute -n 199.36.153.8` showing one hop, (3) a successful authenticated BigQuery call from the VM (`bq query --use_legacy_sql=false 'SELECT 1 AS x'` or the Python client) that returns a row — proving the *whole* path works, DNS through API. Then run Exercise 3's diagnostic tool with `--scenario dns_public` and paste the verdict, explaining how it maps to what you'd see if you deleted the DNS override.

**Acceptance criteria.**

- [ ] `notes/pga-proof.md` has the `dig`, `traceroute`, and successful `bq`/Python query output.
- [ ] `dig` shows `199.36.153.x`, not a public `142.250.x.x`.
- [ ] `traceroute -n 199.36.153.8` shows a single hop into Google's network.
- [ ] The BigQuery call returns `x = 1` (or your chosen query's result), proving identity + network both work.
- [ ] The Exercise-3 `dns_public` verdict (`DNS_MISRESOLUTION`) is pasted with a one-sentence mapping to the real failure.
- [ ] `terraform destroy` clean.

**Hint.** The VM needs a service account with `roles/bigquery.jobUser` (and the BigQuery API enabled) for the query to succeed — that is the identity half. If the query 403s but `dig`/`traceroute` are correct, you have proven the *network* is fine and the problem is IAM, which is exactly the distinction Exercise 3 teaches.

**Estimated time.** 60 minutes.

---

## Problem 6 — Read the terraform-google-network module and extract one pattern

**Problem statement.** Open the de-facto-standard VPC module at <https://github.com/terraform-google-modules/terraform-google-network>. Read `modules/vpc/main.tf` and `modules/subnets/main.tf`. Find **one** pattern that is more sophisticated than what you wrote this week (candidates: the `for_each` over a subnet list with a composite key, the dynamic `secondary_ip_range` block, the way it handles per-subnet flags, or the flow-log config wiring). Write a 200-word note at `notes/module-pattern.md` explaining the pattern, why the module authors chose it, and how you would fold it into your mini-project's `modules/vpc`.

**Acceptance criteria.**

- [ ] `notes/module-pattern.md` is 180–220 words and cites the specific file + the pattern by name (e.g., "the `for_each` composite key `${region}/${name}`").
- [ ] The note explains *why* the pattern exists (what problem it solves that a naive `count` or copy-paste does not).
- [ ] The note states concretely how you would apply it to your own `modules/vpc`.
- [ ] File committed.

**Hint.** The community module keys subnets by `"${region}/${subnet_name}"` so two subnets with the same name in different regions don't collide in the `for_each` map. That composite-key trick is the single most reusable thing in the module; if you're stuck on what to write about, write about that.

**Estimated time.** 40 minutes.

---

## Submission

Push the entire `notes/` directory and any Terraform to your Week 3 Git repository. The instructor reviews by:

1. Reading each note in `notes/`.
2. Re-running any live commands you cite (Problems 2 and 5) and checking they reproduce.
3. Cross-checking the cited URLs are real and the claims are consistent with the source.
4. Confirming your teardown ran (no orphaned routers/NATs in the project you used).

A submission whose notes are present, whose live commands reproduce, and whose teardown is proven is a pass. The most common review-fail is "the note claims PGA works but the pasted `dig` shows a public IP" — double-check the evidence matches the claim before submitting.

If anything is unclear, post in the Week 3 channel before the deadline.

---

## Rubric

| Problem | Weight | What earns full marks |
|---|---:|---|
| 1 — Address plan | 15% | 9 non-overlapping ranges, no on-prem collision, `ipcalc` proof, sizing justification. |
| 2 — Cloud NAT (live) | 20% | NAT egress proven, egress-deny break observed and *scoped*-fixed, clean teardown. |
| 3 — Route table | 15% | Every row correctly typed and explained; default + subnet routes identified. |
| 4 — Connectivity memo | 15% | All four scenarios correct with failure-mode justifications (incl. the PSC trap). |
| 5 — PGA proof | 20% | `dig` private VIP + one-hop traceroute + successful authenticated BQ query; diagnostic mapping. |
| 6 — Module pattern | 15% | Specific pattern named from the real source, why it exists, how you'd adopt it. |

A passing homework is ≥ 70% across the rubric. Live problems (2, 5) with no teardown proof cap at half marks regardless of the rest — the teardown discipline is the point of the week.

---

**References**

- VPC firewall rules: <https://cloud.google.com/firewall/docs/firewalls>
- Routes overview: <https://cloud.google.com/vpc/docs/routes>
- Cloud NAT: <https://cloud.google.com/nat/docs/overview>
- Configure Private Google Access: <https://cloud.google.com/vpc/docs/configure-private-google-access>
- Choosing a network connectivity product: <https://cloud.google.com/network-connectivity/docs/how-to/choose-product>
- terraform-google-modules/terraform-google-network: <https://github.com/terraform-google-modules/terraform-google-network>
- `ipcalc`: install with `brew install ipcalc` or `apt install ipcalc`.
