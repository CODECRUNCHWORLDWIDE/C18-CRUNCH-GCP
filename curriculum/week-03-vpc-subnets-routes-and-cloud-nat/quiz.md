# Week 3 — Quiz

Twelve multiple-choice questions. Take it with your lecture notes closed. Aim for 10/12 before moving to Week 04. Answer key at the bottom — don't peek.

---

**Q1.** A VM in a `us-central1` subnet and a VM in a `europe-west1` subnet are in the **same** GCP VPC, each with an internal IP and no external IP. With default firewall rules allowing intra-VPC traffic, can they reach each other over their internal IPs, and what (if anything) did you have to provision to make it work?

- A) No — you must create a VPC peering between the two regions first.
- B) No — you must create a Cloud Interconnect between the regions.
- C) Yes — they are already on the same global VPC; no peering or transit gateway is needed. You still pay GCP's inter-region egress rate for the bytes, but you provision no connection.
- D) Yes — but only if both subnets are in auto-mode.

---

**Q2.** You create a VPC with `auto_create_subnetworks = true` and then wonder why you have a `/20` subnet in 40 regions you never intended to use. What is the correct production posture?

- A) Auto-mode is correct for production; the extra subnets are free and harmless.
- B) Use custom-mode (`auto_create_subnetworks = false`) and create exactly the subnets you want, in the regions you want, with the CIDRs you choose.
- C) Use auto-mode but delete the subnets you don't want afterward.
- D) Auto-mode vs custom-mode makes no difference once you add firewall rules.

---

**Q3.** Which statement about a subnet's **secondary ranges** is correct?

- A) Secondary ranges are used for the subnet's own VM primary IPs.
- B) Secondary ranges are GKE alias-IP ranges — typically one for pods and one for services — and must not overlap any other range in the VPC (or any peered VPC).
- C) A subnet can have at most one secondary range.
- D) Secondary ranges are only used by Cloud NAT.

---

**Q4.** Two routes match a packet destined for `10.20.5.7`: route X is `10.20.0.0/16` priority 100, route Y is `10.20.5.0/24` priority 1000. Which route is selected?

- A) X — it has the lower (better) priority number.
- B) Y — longest-prefix match wins *before* priority is even considered, and `/24` is more specific than `/16`.
- C) X — `/16` covers more addresses, so it is preferred.
- D) Neither — the priorities conflict and the packet is dropped.

---

**Q5.** A fresh custom-mode VPC has which two **implied** firewall rules that you cannot delete?

- A) Implied allow-ingress from `0.0.0.0/0` and implied deny-egress to `0.0.0.0/0`.
- B) Implied deny-ingress from `0.0.0.0/0` (priority 65535) and implied allow-egress to `0.0.0.0/0` (priority 65535).
- C) Implied allow-ingress and implied allow-egress, both priority 0.
- D) There are no implied rules; a fresh VPC allows nothing in either direction.

---

**Q6.** You strip the external IP from a production VM. To keep SSH access, which firewall rule must already be in place *before* you remove the IP?

- A) An ingress allow on tcp:22 from `0.0.0.0/0`.
- B) An ingress allow on tcp:22 from the IAP TCP-forwarding range `35.235.240.0/20`, targeting a tag the instance carries.
- C) An egress allow to `35.235.240.0/20`.
- D) None — removing the external IP automatically enables IAP.

---

**Q7.** Cloud NAT lets a VM with no external IP reach the internet for egress. Which statement is true?

- A) Cloud NAT is a managed VM appliance you must size and patch.
- B) Cloud NAT is a configuration on a Cloud Router that programs the VPC's software data plane; there is no NAT instance. A VM that *has* an external IP bypasses Cloud NAT and egresses via its own IP.
- C) Cloud NAT NATs all traffic, including from VMs that have external IPs.
- D) Cloud NAT requires the VM to also have an external IP.

---

**Q8.** A VM with no external IP calls `storage.googleapis.com` and the call hangs. DNS resolves the name to a public `142.250.x.x` address. What is the most likely fix?

- A) Add an external IP to the VM.
- B) Enable Private Google Access on the subnet and add a private Cloud DNS zone that overrides `*.googleapis.com` to the private VIP `199.36.153.8/30`, so the name resolves to the private VIP instead of a public address.
- C) Open an ingress firewall rule from `0.0.0.0/0`.
- D) Switch the subnet to auto-mode.

---

**Q9.** In one sentence each, the difference between Private Google Access (PGA) and Private Service Connect (PSC) is best captured by which option?

- A) PGA and PSC are two names for the same feature.
- B) PGA is a subnet flag that lets instances reach Google's *shared* API VIPs (`*.googleapis.com`) over internal IPs; PSC creates a *private endpoint with an IP in your own subnet* mapped to a specific published service or API.
- C) PGA is for inbound traffic; PSC is for outbound.
- D) PGA requires an external IP; PSC does not.

---

**Q10.** You have a central platform team that should own IP planning, firewall posture, Cloud NAT, and the on-prem link, while a dozen app teams deploy VMs and GKE clusters into that network without changing it. Which connectivity model fits?

- A) VPC peering between every app team's VPC.
- B) Network Connectivity Center hub with one spoke per app team.
- C) Shared VPC — a host project owns the network; service projects (one per app team) attach and consume it via subnet-scoped `roles/compute.networkUser`.
- D) Separate VPCs with no connection.

---

**Q11.** VPC peering connects two VPCs. Which set of statements is entirely correct?

- A) Peering is transitive (A↔B and B↔C gives A↔C), tolerates overlapping ranges, and is configured on one side only.
- B) Peering is non-transitive (A↔B and B↔C does **not** give A↔C), forbids overlapping ranges, and must be configured on **both** sides before it goes ACTIVE.
- C) Peering is transitive, forbids overlapping ranges, and is configured on both sides.
- D) Peering is non-transitive, tolerates overlapping ranges via NAT, and is configured on one side only.

---

**Q12.** You must connect six VPCs plus an on-prem site (via HA VPN) into a single transitive mesh. Which is the right tool, and why is the alternative wrong?

- A) Peering — a full mesh of 6 VPCs is only a handful of connections and peering supports transitivity.
- B) Shared VPC — make all six service projects of one host.
- C) Network Connectivity Center — it gives transitive connectivity with linear (one-per-spoke) scaling and treats the HA VPN as a first-class spoke; a peering mesh would need 15 peerings and still would not be transitive.
- D) Separate them — six VPCs should never be connected.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **C** — A GCP VPC is global. Two subnets in different regions of the same VPC route to each other over internal IPs with no peering and no transit gateway; you provision nothing. You still pay the inter-region egress *byte* rate (global VPC gives you free *topology*, not free bytes), and the traffic is subject to firewall rules — but no connection is provisioned. A and B describe the AWS model. D is wrong: auto vs custom mode does not change cross-region reachability.

2. **B** — Production VPCs are custom-mode. `auto_create_subnetworks = false` and you create exactly the subnets you intend, so you control every CIDR and avoid collisions with on-prem or peers. A is wrong (the extra subnets are real attack/collision surface); C is the manual-cleanup anti-pattern; D is false.

3. **B** — Secondary ranges hold GKE alias IPs (pods + services) and, like every range in the VPC, must not overlap any other range here or in a peered VPC. A confuses primary with secondary; C is false (multiple secondaries are allowed); D is false (NAT does not use secondary ranges).

4. **B** — Route selection is longest-prefix match *first*, then priority only as a tiebreaker among equal prefixes. `10.20.5.0/24` is more specific than `10.20.0.0/16`, so route Y wins regardless of its higher priority number. Priority only matters when prefixes tie.

5. **B** — Every VPC has an implied **deny ingress** from `0.0.0.0/0` and an implied **allow egress** to `0.0.0.0/0`, both at priority 65535, neither deletable. So a fresh VPC: everything can leave, nothing can enter, until you add allow-ingress rules with a lower priority number.

6. **B** — The IAP TCP-forwarding range is `35.235.240.0/20`; you need an ingress allow on tcp:22 from that range, targeting a tag (or service account) the instance carries, **before** you remove the external IP. A (`0.0.0.0/0` on 22) is the lockout-inviting wrong answer; C targets the wrong direction; D is false — removing the IP does not auto-enable anything.

7. **B** — Cloud NAT is a Cloud Router configuration that programs the SDN data plane; there is no instance to manage. A VM with its own external IP egresses via that IP and bypasses NAT entirely — which is why "I added NAT but my public-IP VM still shows its own IP" is expected. A, C, D are all false.

8. **B** — The name resolving to a public address is the tell: PGA's DNS override is missing. Enable `private_ip_google_access = true` on the subnet and add the private `*.googleapis.com` → `199.36.153.8/30` DNS zone so the name resolves to the private VIP. A defeats the no-external-IP posture; C is unrelated (it's ingress); D is nonsense.

9. **B** — PGA is a *subnet flag* for reaching the *shared* `*.googleapis.com` VIPs over internal IPs; PSC provisions a *private endpoint with an IP in your own subnet* for a specific published service or API (and tolerates overlapping ranges, since it needs no route exchange). They solve different problems at different layers.

10. **C** — This is the textbook shared-VPC case: centralize the network in a host project, decentralize the compute into service projects, grant subnet-scoped `networkUser`. A and B over-engineer it; D breaks the requirement that teams share one network.

11. **B** — Peering is non-transitive, forbids overlapping ranges (no NAT in peering), and requires both halves before it is ACTIVE. A, C, and D each get at least one of the three properties wrong.

12. **C** — NCC gives transitive connectivity with linear scaling (one spoke per VPC) and makes the HA VPN a first-class spoke. A is wrong because peering is **not** transitive and 6 VPCs need 15 peerings; B forces an awkward single-host topology that does not include the on-prem site cleanly; D ignores the requirement.

</details>

---

If you scored under 8, re-read the lecture sections for the questions you missed (Q1–Q9 map to Lecture 1; Q10–Q12 map to Lecture 2). If you scored 11 or 12, you're ready for the [homework](./homework.md).
