# Exercise 1 — Firewall rules for a real service, without locking yourself out

**Goal:** You are handed a concrete service spec. Write the VPC firewall rules that allow *exactly* the traffic it needs — and not one port more — while keeping your own IAP/SSH lifeline intact. Then validate every rule with a Connectivity Test, the way a senior engineer does before trusting any firewall change in production.

**Estimated time:** 75 minutes.

**You need:** a GCP project with billing, `gcloud` + `terraform` (or `tofu`), and ADC credentials (`gcloud auth application-default login`). This exercise creates one VPC, one subnet, two tiny `e2-micro` VMs, a Cloud Router + NAT, and a handful of firewall rules. Total cost if you destroy at the end: a few cents.

---

## The service spec

You are deploying a two-tier web service into one `us-central1` subnet:

- A **web tier** (`role:web`): an HTTP server on **tcp/8080**. It must be reachable by Google Cloud Load Balancer health checks and forwarded traffic. It must *not* be reachable directly from the public internet.
- An **app tier** (`role:app`): a gRPC backend on **tcp/9090**. It must be reachable **only** from the web tier. Nothing else.
- **Both tiers** have **no external IP**. They reach the internet for egress (package installs, image pulls) via Cloud NAT.
- **You** must be able to SSH to either VM through **IAP TCP forwarding** at any time, for debugging.

Translate that into the smallest correct firewall rule set. Then prove it.

---

## Step 0 — Scaffold

Make a folder and a `provider.tf`:

```bash
mkdir ex01-firewall && cd ex01-firewall
```

`provider.tf`:

```hcl
terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project_id" {
  type        = string
  description = "Your GCP project ID."
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

provider "google" {
  project = var.project_id
  region  = var.region
}
```

Enable the APIs you'll touch (idempotent — safe to re-run):

```bash
gcloud services enable compute.googleapis.com networkmanagement.googleapis.com iap.googleapis.com \
  --project "$(gcloud config get-value project)"
```

---

## Step 1 — The network, subnet, NAT (the substrate)

`network.tf`:

```hcl
resource "google_compute_network" "vpc" {
  name                    = "ex01-vpc"
  project                 = var.project_id
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "main" {
  name                     = "ex01-main"
  project                  = var.project_id
  network                  = google_compute_network.vpc.id
  region                   = var.region
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true
}

resource "google_compute_router" "router" {
  name    = "ex01-router"
  project = var.project_id
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "ex01-nat"
  project                            = var.project_id
  region                             = var.region
  router                             = google_compute_router.router.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}
```

---

## Step 2 — The two VMs (no external IP)

`vms.tf`. Note the `access_config` block is **absent** — that's what makes a VM have no external IP. Note the network tags: they are how the firewall rules target each tier.

```hcl
resource "google_compute_instance" "web" {
  name         = "ex01-web"
  project      = var.project_id
  zone         = var.zone
  machine_type = "e2-micro"
  tags         = ["web", "allow-iap"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.main.id
    # No access_config block => no external IP. This is the production default.
  }
}

resource "google_compute_instance" "app" {
  name         = "ex01-app"
  project      = var.project_id
  zone         = var.zone
  machine_type = "e2-micro"
  tags         = ["app", "allow-iap"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.main.id
  }
}
```

---

## Step 3 — The firewall rules (the actual exercise)

This is where you do the thinking. Write `firewall.tf`. The rules, in the order you should reason about them:

```hcl
# RULE 1 — THE LIFELINE. IAP TCP forwarding to SSH on every VM that carries
# the allow-iap tag. 35.235.240.0/20 is Google's published IAP source range.
# This rule goes in FIRST, before anything that could deny. Without it, a VM
# with no external IP is unreachable.
resource "google_compute_firewall" "allow_iap_ssh" {
  name      = "ex01-allow-iap-ssh"
  project   = var.project_id
  network   = google_compute_network.vpc.id
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["allow-iap"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  log_config { metadata = "INCLUDE_ALL_METADATA" }
}

# RULE 2 — Health checks from Google's LB/health-check ranges to the web tier
# on tcp/8080. These ranges are fixed and published. Without this, the LB marks
# your backends unhealthy and serves nothing.
resource "google_compute_firewall" "allow_health_checks" {
  name      = "ex01-allow-health-checks"
  project   = var.project_id
  network   = google_compute_network.vpc.id
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]
  target_tags   = ["web"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
  log_config { metadata = "INCLUDE_ALL_METADATA" }
}

# RULE 3 — The app tier (tcp/9090) is reachable ONLY from the web tier. We scope
# the SOURCE by tag, not by CIDR: source_tags = ["web"] means "instances tagged
# web," which is tighter and survives IP changes. The TARGET is the app tier.
resource "google_compute_firewall" "allow_web_to_app" {
  name      = "ex01-allow-web-to-app"
  project   = var.project_id
  network   = google_compute_network.vpc.id
  direction = "INGRESS"
  priority  = 1000

  source_tags = ["web"]   # only the web VMs may originate this traffic
  target_tags = ["app"]

  allow {
    protocol = "tcp"
    ports    = ["9090"]
  }
  log_config { metadata = "INCLUDE_ALL_METADATA" }
}
```

Notice what is **not** here:

- **No `0.0.0.0/0 → tcp/8080` rule.** The web tier is reachable by health checks (Rule 2) and will be reachable by the LB's forwarding traffic (which also originates from `130.211.0.0/22`/`35.191.0.0/16`), but never directly from the public internet. The spec said "must not be reachable directly from the public internet" — so we never write a rule that allows the internet in.
- **No explicit egress rule.** The implied allow-egress to `0.0.0.0/0` is still in place; Cloud NAT handles the actual SNAT. We did not write a blanket egress *deny*, because that would also kill Cloud NAT's path (lockout pattern #1 from Lecture 1).
- **No allow on app/tcp9090 from anywhere but `web`.** Source-tag scoping is the tight control.

Apply:

```bash
terraform init
terraform apply -var "project_id=$(gcloud config get-value project)"
```

---

## Step 4 — Validate with Connectivity Tests (do NOT skip this)

A Connectivity Test is a static reachability analysis — it traces the configured path through routes and firewall rules and tells you REACHABLE / UNREACHABLE *without* sending a packet. It is how you confirm a firewall change before you trust it. Run four tests that mirror the spec.

**Test A — your IAP lifeline reaches the web VM on tcp/22 (must be REACHABLE):**

```bash
gcloud network-management connectivity-tests create ex01-iap-to-web \
  --source-ip-address=35.235.240.1 \
  --destination-instance=ex01-web \
  --destination-port=22 \
  --protocol=TCP \
  --project="$(gcloud config get-value project)"

gcloud network-management connectivity-tests describe ex01-iap-to-web \
  --project="$(gcloud config get-value project)" \
  --format="value(reachabilityDetails.result)"
# Expect: REACHABLE
```

**Test B — health-check range reaches the web VM on tcp/8080 (must be REACHABLE):**

```bash
gcloud network-management connectivity-tests create ex01-hc-to-web \
  --source-ip-address=35.191.0.1 \
  --destination-instance=ex01-web \
  --destination-port=8080 \
  --protocol=TCP \
  --project="$(gcloud config get-value project)"

gcloud network-management connectivity-tests describe ex01-hc-to-web \
  --format="value(reachabilityDetails.result)" \
  --project="$(gcloud config get-value project)"
# Expect: REACHABLE
```

**Test C — the web VM reaches the app VM on tcp/9090 (must be REACHABLE):**

```bash
gcloud network-management connectivity-tests create ex01-web-to-app \
  --source-instance=ex01-web \
  --destination-instance=ex01-app \
  --destination-port=9090 \
  --protocol=TCP \
  --project="$(gcloud config get-value project)"

gcloud network-management connectivity-tests describe ex01-web-to-app \
  --format="value(reachabilityDetails.result)" \
  --project="$(gcloud config get-value project)"
# Expect: REACHABLE
```

**Test D — the public internet does NOT reach the app VM on tcp/9090 (must be UNREACHABLE / DROPPED):**

```bash
gcloud network-management connectivity-tests create ex01-internet-to-app \
  --source-ip-address=8.8.8.8 \
  --destination-instance=ex01-app \
  --destination-port=9090 \
  --protocol=TCP \
  --project="$(gcloud config get-value project)"

gcloud network-management connectivity-tests describe ex01-internet-to-app \
  --format="value(reachabilityDetails.result)" \
  --project="$(gcloud config get-value project)"
# Expect: UNREACHABLE (the trace ends in a DROPPED state at the implied deny)
```

Expected results, all four together:

```
ex01-iap-to-web        REACHABLE     # lifeline intact
ex01-hc-to-web         REACHABLE     # health checks work
ex01-web-to-app        REACHABLE     # web can call app
ex01-internet-to-app   UNREACHABLE   # internet cannot reach app
```

If **Test A** is anything but REACHABLE, you have locked yourself out — fix the IAP rule before doing anything else. If **Test D** is REACHABLE, you have a hole — find the rule that allows the internet in and remove it.

---

## Step 5 — Prove the lifeline for real

The Connectivity Test is static analysis. Confirm it with a live IAP SSH (this exercises the real path, including OS Login / SSH key propagation):

```bash
gcloud compute ssh ex01-web \
  --zone=us-central1-a \
  --tunnel-through-iap \
  --command="echo 'IAP SSH works' && curl -s -m 5 https://storage.googleapis.com -o /dev/null -w 'egress via NAT: %{http_code}\n'"
```

You should see `IAP SSH works` and an HTTP status code (the `curl` proves Cloud NAT egress works — the VM has no external IP yet reached the internet).

---

## Step 6 — Tear down (mandatory)

```bash
# Delete the connectivity tests first (they're cheap but tidy up).
for t in ex01-iap-to-web ex01-hc-to-web ex01-web-to-app ex01-internet-to-app; do
  gcloud network-management connectivity-tests delete "$t" --quiet \
    --project="$(gcloud config get-value project)"
done

terraform destroy -var "project_id=$(gcloud config get-value project)"

# Confirm nothing lingers:
gcloud compute routers list --project="$(gcloud config get-value project)"   # expect empty
gcloud compute firewall-rules list --project="$(gcloud config get-value project)" \
  --filter="network:ex01-vpc"                                                # expect empty
```

---

## Acceptance criteria

- [ ] `terraform apply` succeeds and creates exactly four firewall rules (IAP-SSH, health-check, web-to-app, and the implied rules you did **not** write).
- [ ] Test A (IAP → web:22) is **REACHABLE**.
- [ ] Test B (health-check → web:8080) is **REACHABLE**.
- [ ] Test C (web → app:9090) is **REACHABLE**.
- [ ] Test D (internet → app:9090) is **UNREACHABLE**.
- [ ] A live `gcloud compute ssh --tunnel-through-iap` to `ex01-web` succeeds, and the in-VM `curl` to `storage.googleapis.com` returns an HTTP code (NAT egress confirmed).
- [ ] `terraform destroy` runs clean and `gcloud compute routers list` returns empty.

---

## Stretch

- Add an **egress-deny** rule on the app tier that blocks all egress *except* to the web tier and to the PGA VIP `199.36.153.8/30`, then re-run Test C (still REACHABLE) and a new test app→`8.8.8.8`:443 (now UNREACHABLE). This is the "app tier has no business calling the internet" hardening, done without breaking PGA.
- Replace **target tags** with **target service accounts** on all three rules (`target_service_accounts` instead of `target_tags`). Tag-based targeting is convenient; SA-based targeting is stronger because tags can be added by anyone with `compute.instances.setTags`. Re-run all four tests; results should be identical.
- Turn on **Firewall Rules Logging** (already on via `log_config`) and, after the live SSH, find the log entry in Cloud Logging that shows the IAP-SSH rule allowed your connection: filter `logName:"firewall"` and look for `rule_details.reference` = `ex01-allow-iap-ssh`.

---

## The senior takeaway

The skill is not "write a firewall rule." Anyone can write `allow tcp:22 from 0.0.0.0/0`. The skill is: **write the minimum rule set the spec actually requires, keep your lifeline rule first, and validate every rule with a Connectivity Test before you trust it.** Test D — proving the thing that should be blocked *is* blocked — is the half of the job most engineers skip, and it's the half that keeps you out of the postmortem.

---

**References**

- VPC firewall rules: <https://cloud.google.com/firewall/docs/firewalls>
- IAP TCP forwarding: <https://cloud.google.com/iap/docs/using-tcp-forwarding>
- Connectivity Tests: <https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/how-to/running-connectivity-tests>
- Health-check probe ranges: <https://cloud.google.com/load-balancing/docs/health-check-concepts#ip-ranges>
- `gcloud network-management connectivity-tests`: <https://cloud.google.com/sdk/gcloud/reference/network-management/connectivity-tests>

When this feels solid, continue to [Exercise 2 — Private Google Access](./exercise-02-private-google-access.tf).
