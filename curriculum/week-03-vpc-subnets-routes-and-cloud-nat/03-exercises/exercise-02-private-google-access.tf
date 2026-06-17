###############################################################################
# Exercise 2 — Private Google Access: reach *.googleapis.com privately
#
# Goal: Configure a subnet with NO external IPs so that an instance in it can
#       reach storage.googleapis.com / bigquery.googleapis.com over Google's
#       PRIVATE VIP (199.36.153.8/30), never the public internet. Then VERIFY
#       it from a VM with `dig` and `traceroute`.
#
# Expected outcome (proven from a VM in the subnet, no external IP):
#
#   $ dig +short storage.googleapis.com
#   private.googleapis.com.
#   199.36.153.8
#
#   $ traceroute -n 199.36.153.8
#   traceroute to 199.36.153.8 (199.36.153.8), 30 hops max
#    1  199.36.153.8  0.41 ms  0.39 ms  0.37 ms      <-- ONE hop into Google, no public transit
#
# Estimated time: 60 minutes.
#
# ---------------------------------------------------------------------------
# HOW TO USE THIS FILE
#
#   1. mkdir ex02-pga && cd ex02-pga
#   2. Save this file as main.tf in that folder.
#   3. Fill in the four TODOs below (search for "TODO").
#   4. Enable APIs and apply:
#        gcloud services enable compute.googleapis.com dns.googleapis.com \
#          --project "$(gcloud config get-value project)"
#        terraform init
#        terraform apply -var "project_id=$(gcloud config get-value project)"
#   5. SSH in and verify (commands at the very bottom of this file).
#   6. terraform destroy -var "project_id=$(gcloud config get-value project)"
#
# A complete SOLUTION for the four TODOs is at the bottom of this file behind
# a "peek only if stuck" marker. Write your own first.
# ---------------------------------------------------------------------------

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

# --- The network and subnet -------------------------------------------------

resource "google_compute_network" "vpc" {
  name                    = "ex02-vpc"
  project                 = var.project_id
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "main" {
  name          = "ex02-main"
  project       = var.project_id
  network       = google_compute_network.vpc.id
  region        = var.region
  ip_cidr_range = "10.20.0.0/24"

  # ===========================================================================
  # TODO 1 — Turn ON Private Google Access for this subnet. This is the single
  #          flag that lets instances WITHOUT external IPs reach Google APIs.
  #          (One line. See HINT 1 / SOLUTION at the bottom.)
  # ===========================================================================
  # private_ip_google_access = ...
}

# --- IAP SSH lifeline (you must be able to reach the VM to verify) ----------

resource "google_compute_firewall" "allow_iap_ssh" {
  name      = "ex02-allow-iap-ssh"
  project   = var.project_id
  network   = google_compute_network.vpc.id
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["35.235.240.0/20"] # IAP TCP forwarding range
  target_tags   = ["allow-iap"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# --- The route to the private VIP -------------------------------------------
# The default-internet-gateway route (0.0.0.0/0) already covers 199.36.153.8/30,
# so on a vanilla VPC this route is redundant. We add it EXPLICITLY anyway,
# because in production you frequently delete or override the default route and
# then PGA silently breaks. Making the VIP route explicit is the robust pattern.

resource "google_compute_route" "private_google_apis" {
  name             = "ex02-private-google-apis"
  project          = var.project_id
  network          = google_compute_network.vpc.id

  # =========================================================================
  # TODO 2 — Set dest_range to the private.googleapis.com VIP block, and
  #          next_hop_gateway to the default internet gateway. The VIP block
  #          is a /30. (See HINT 2 / SOLUTION.)
  # =========================================================================
  # dest_range       = "..."
  # next_hop_gateway = "..."
  priority = 1000
}

# --- Private DNS: override *.googleapis.com to the private VIP ---------------

resource "google_dns_managed_zone" "googleapis" {
  name        = "ex02-googleapis-private"
  project     = var.project_id
  dns_name    = "googleapis.com."
  description = "Route *.googleapis.com to the private VIP for this VPC"
  visibility  = "private"

  private_visibility_config {
    networks {
      network_url = google_compute_network.vpc.id
    }
  }
}

# An A record so private.googleapis.com resolves to the four VIP addresses.
resource "google_dns_record_set" "private_a" {
  name         = "private.googleapis.com."
  project      = var.project_id
  managed_zone = google_dns_managed_zone.googleapis.name
  type         = "A"
  ttl          = 300
  rrdatas      = ["199.36.153.8", "199.36.153.9", "199.36.153.10", "199.36.153.11"]
}

# =========================================================================
# TODO 3 — A CNAME so that *.googleapis.com (e.g. storage.googleapis.com)
#          resolves to private.googleapis.com. Fill in name, type, and
#          rrdatas. (See HINT 3 / SOLUTION.)
# =========================================================================
resource "google_dns_record_set" "wildcard_cname" {
  project      = var.project_id
  managed_zone = google_dns_managed_zone.googleapis.name
  ttl          = 300
  # name    = "..."
  # type    = "..."
  # rrdatas = ["..."]
}

# --- The test VM (NO external IP) -------------------------------------------

resource "google_compute_instance" "probe" {
  name         = "ex02-probe"
  project      = var.project_id
  zone         = var.zone
  machine_type = "e2-micro"

  # =========================================================================
  # TODO 4 — Tag this instance so the IAP-SSH firewall rule above applies to
  #          it. Without the tag, the rule targets nothing and you cannot SSH
  #          in to verify. (See HINT 4 / SOLUTION.)
  # =========================================================================
  # tags = ["..."]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.main.id
    # No access_config block => no external IP. That is the whole point of PGA.
  }

  # Install dnsutils + traceroute on boot so the verification commands work.
  metadata_startup_script = <<-EOT
    #!/bin/bash
    apt-get update -y
    apt-get install -y dnsutils traceroute
  EOT
}

output "verify_commands" {
  value = <<-EOT

    # SSH in (no external IP — IAP only):
    gcloud compute ssh ex02-probe --zone=${var.zone} --tunnel-through-iap \
      --project=${var.project_id}

    # Inside the VM, run:
    dig +short storage.googleapis.com        # expect: private.googleapis.com. then 199.36.153.8
    traceroute -n 199.36.153.8               # expect: ONE hop, 199.36.153.8, sub-ms
    curl -s -o /dev/null -w '%%{http_code}\n' https://storage.googleapis.com  # expect a 2xx/4xx, NOT a hang
  EOT
}

###############################################################################
# VERIFICATION (run these after `terraform apply` succeeds)
#
#   gcloud compute ssh ex02-probe --zone=us-central1-a --tunnel-through-iap
#
#   # 1) DNS resolves to the PRIVATE VIP, not a public 142.250.x.x address:
#   $ dig +short storage.googleapis.com
#   private.googleapis.com.
#   199.36.153.8
#
#   # 2) traceroute shows ONE hop into Google's network, no public transit:
#   $ traceroute -n 199.36.153.8
#    1  199.36.153.8  0.41 ms  0.39 ms  0.37 ms
#
#   # 3) An actual API call works despite the VM having no external IP:
#   $ curl -s -o /dev/null -w '%{http_code}\n' https://storage.googleapis.com
#   400        # 400 is fine here — it means we REACHED the API (it just wants auth/path)
#
# If dig returns a public IP (142.250.x.x) the DNS override did not take — check
# TODO 1/2/3. If curl HANGS, PGA is off or the route is missing — check TODO 1/2.
###############################################################################

# ACCEPTANCE CRITERIA
#
#   [ ] terraform apply succeeds; the VM has NO external IP.
#   [ ] dig +short storage.googleapis.com resolves to 199.36.153.x (private VIP).
#   [ ] traceroute -n 199.36.153.8 shows ONE hop into Google's network.
#   [ ] curl https://storage.googleapis.com returns an HTTP code (does not hang).
#   [ ] terraform destroy runs clean.

# TEARDOWN (mandatory):
#   terraform destroy -var "project_id=$(gcloud config get-value project)"
#   gcloud compute routers list --project="$(gcloud config get-value project)"  # expect empty

###############################################################################
# ====================  SOLUTION — peek only if stuck  ========================
#
# HINT 1 / TODO 1 — in resource "google_compute_subnetwork" "main":
#
#   private_ip_google_access = true
#
# HINT 2 / TODO 2 — in resource "google_compute_route" "private_google_apis":
#
#   dest_range       = "199.36.153.8/30"
#   next_hop_gateway = "default-internet-gateway"
#
# HINT 3 / TODO 3 — in resource "google_dns_record_set" "wildcard_cname":
#
#   name    = "*.googleapis.com."
#   type    = "CNAME"
#   rrdatas = ["private.googleapis.com."]
#
# HINT 4 / TODO 4 — in resource "google_compute_instance" "probe":
#
#   tags = ["allow-iap"]
#
# WHY 199.36.153.8/30 (private) and not 199.36.153.4/30 (restricted)?
#   - private.googleapis.com  (199.36.153.8/30)  reaches MOST Google APIs.
#   - restricted.googleapis.com (199.36.153.4/30) reaches ONLY APIs supported
#     inside a VPC Service Controls perimeter (Week 14). Use `private` here.
#
# WHY the CNAME + A pair instead of just A records on *.googleapis.com?
#   - A wildcard CNAME to private.googleapis.com keeps one authoritative A
#     record set. If Google ever changes the VIP set, you update ONE record.
#     This is the pattern Google's own docs recommend.
###############################################################################
