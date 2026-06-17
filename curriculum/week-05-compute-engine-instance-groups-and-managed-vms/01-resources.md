# Week 5 — Resources

Every link here is **free**. Google Cloud documentation is public without an account. The Terraform provider docs are open. The open-source modules and tools are on GitHub. No paywalled material is linked. Where a page tends to drift between releases, we say what to search for if the link rots.

## Required reading (work it into your week)

- **Compute Engine — machine families resource and comparison guide** — the single most important page this week. Read the E2/N2/N2D/T2D/C3 sections and the price-performance notes:
  <https://cloud.google.com/compute/docs/machine-resource>
- **General-purpose machine family for Compute Engine** — the per-family deep dive (E2, N-series, Tau T2D/T2A, C-series):
  <https://cloud.google.com/compute/docs/general-purpose-machines>
- **Instance templates overview** — the immutable blueprint a MIG stamps out:
  <https://cloud.google.com/compute/docs/instance-templates>
- **Managed instance groups (MIGs) overview** — regional vs zonal, autohealing, the basis-of-everything page:
  <https://cloud.google.com/compute/docs/instance-groups>
- **Autoscaling groups of instances** — scaling on CPU, LB capacity, and custom metrics; cooldown and stabilization:
  <https://cloud.google.com/compute/docs/autoscaler>
- **Spot VMs** — pricing, preemption behavior, the 30-second notice, and the metadata signal:
  <https://cloud.google.com/compute/docs/instances/spot>
- **OS Login** — IAM-governed SSH, the production alternative to metadata SSH keys:
  <https://cloud.google.com/compute/docs/oslogin>
- **Shielded VM** — Secure Boot, vTPM, integrity monitoring, and what each defends against:
  <https://cloud.google.com/security/products/shielded-vm>

## Networking / load balancing (you need exactly the L4 internal LB this week)

- **Internal passthrough Network Load Balancer overview** — the L4 internal LB that fronts your MIG:
  <https://cloud.google.com/load-balancing/docs/internal>
- **Health checks overview** — the difference between an autohealing health check and a load-balancing health check, and why you almost always want two:
  <https://cloud.google.com/load-balancing/docs/health-check-concepts>
- **Health check firewall rules** — the `130.211.0.0/22` and `35.191.0.0/16` source ranges you must allow or your backends will never go healthy:
  <https://cloud.google.com/load-balancing/docs/health-check-concepts#fw-rule>

## Terraform provider (the exact resources you will write)

- **`google_compute_instance_template`** — argument reference:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_instance_template>
- **`google_compute_region_instance_group_manager`** — the regional MIG, including `update_policy` for rolling updates:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_region_instance_group_manager>
- **`google_compute_region_autoscaler`** — autoscaling policy attached to a regional MIG:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_region_autoscaler>
- **`google_compute_region_health_check`** and **`google_compute_health_check`**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_region_health_check>
- **`google_compute_region_backend_service`** and **`google_compute_forwarding_rule`** (internal LB):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_region_backend_service>

## Pricing (bring numbers, not vibes)

- **Compute Engine pricing** — the authoritative per-vCPU/per-GB hourly rates by family and region:
  <https://cloud.google.com/compute/all-pricing>
- **Sustained use discounts** — the automatic discount for running an instance most of the month:
  <https://cloud.google.com/compute/docs/sustained-use-discounts>
- **Committed use discounts (resource-based and spend-based)** — the 1- and 3-year commitments:
  <https://cloud.google.com/compute/docs/instances/committed-use-discounts-overview>
- **Google Cloud Pricing Calculator** — model a MIG before you build it:
  <https://cloud.google.com/products/calculator>

## Open-source modules and tools to read

You learn more from one hour reading a well-structured Terraform module than from three tutorials.

- **`terraform-google-modules/terraform-google-vm`** — the community instance-template and MIG submodules; read how they parameterize the template:
  <https://github.com/terraform-google-modules/terraform-google-vm>
- **`terraform-google-modules/terraform-google-lb-internal`** — a reference internal-LB module:
  <https://github.com/terraform-google-modules/terraform-google-lb-internal>
- **`GoogleCloudPlatform/cloud-foundation-fabric`** — Google's own opinionated Terraform blueprints; the `compute-vm` and `net-ilb` modules are worth a read:
  <https://github.com/GoogleCloudPlatform/cloud-foundation-fabric>

## Tools you'll use this week

- **`gcloud` CLI** — installed and updated to a 2026 release. Verify with `gcloud version`. Key surfaces: `gcloud compute instance-templates`, `gcloud compute instance-groups managed`, `gcloud compute instances`.
- **`terraform`** (>= 1.9) or **`tofu`** (OpenTofu >= 1.7). Either works; the HCL is identical.
- **`go`** (1.23+) — to build the HTTP service binary the MIG runs.
- **`hey`** — the HTTP load generator we use for scale-out and zero-drop validation: <https://github.com/rakyll/hey>. (`vegeta` is an acceptable substitute and gives you a latency histogram; <https://github.com/tsenart/vegeta>.)
- **`jq`** — for slicing `gcloud ... --format=json` output.

## Talks and longer-form (free, no signup)

- **Google Cloud Next sessions on Compute Engine** — every year there is a "what's new in Compute" and a "cost optimization for Compute" session, posted free on the Google Cloud Tech YouTube channel:
  <https://www.youtube.com/@googlecloudtech>
- **"Compute Engine machine family deep dive"** — search the channel above for the current-year machine-family session; the C3/C4 Titanium offload material is the part to watch.
- **The Google Cloud blog — Compute tag** — release announcements for new machine families land here first:
  <https://cloud.google.com/blog/products/compute>

## Reference architectures

- **Patterns for scalable and resilient apps** — Google's own guidance; the MIG-behind-LB pattern is canonical here:
  <https://cloud.google.com/architecture/scalable-and-resilient-apps>
- **Reliable task scheduling on Compute Engine with spot VMs** — how Google itself recommends running interruptible batch:
  <https://cloud.google.com/architecture>  (search "spot VMs batch")

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **GCE** | Google Compute Engine — the IaaS VM product. |
| **Machine family** | A class of CPU/architecture: E2, N2, N2D, T2D, C3, etc. |
| **Machine type** | A specific size within a family: `e2-medium`, `c3-standard-22`. |
| **vCPU** | One hardware hyperthread (not a full physical core). |
| **MIG** | Managed Instance Group — a self-healing, autoscaling group of identical VMs. |
| **Instance template** | The immutable blueprint a MIG uses to create instances. You version it; you never edit it in place. |
| **Autohealing** | The MIG recreates an instance that fails its health check. |
| **Regional MIG** | A MIG that spreads instances across all zones in a region for AZ-loss survival. |
| **OS Login** | SSH access governed by IAM roles instead of metadata SSH keys. |
| **Shielded VM** | A VM with Secure Boot + vTPM + integrity monitoring enabled. |
| **Spot VM** | A deeply discounted, preemptible VM. Can be reclaimed with ~30s notice. |
| **Preemption** | Google reclaiming a spot VM; signaled via an ACPI shutdown and a metadata flag. |
| **SUD** | Sustained Use Discount — automatic discount for running most of the month. |
| **CUD** | Committed Use Discount — 1- or 3-year commitment for a deeper discount. |
| **ILB** | Internal Load Balancer; this week, the L4 internal passthrough NLB. |
| **`max_surge`** | How many extra instances a rolling update may create above target size. |
| **`max_unavailable`** | How many instances a rolling update may take down at once. |

---

*If a link 404s, please open an issue so we can replace it.*
