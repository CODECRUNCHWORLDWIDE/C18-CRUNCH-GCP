###############################################################################
# Exercise 3 — In-place minor-version upgrade on a Standard cluster with surge
#              configuration, proving ZERO traffic loss.
#
# Goal: Stand up a regional GKE Standard cluster with a node pool whose
#       upgrade_settings use surge (max_surge=1, max_unavailable=0 — the safe
#       default from Lecture 2 §2.4). Deploy the 3-replica FastAPI service with
#       its minAvailable:2 PDB. Run a real node-pool minor-version upgrade while
#       a load generator hammers the service, and prove zero failed requests.
#
# Estimated time: 90 minutes (15 of which is GKE provisioning + upgrade waits).
#
# HOW TO USE THIS FILE
#   1. Put this file in a fresh directory as main.tf.
#   2. terraform init && terraform apply -var project_id=$(gcloud config get-value project)
#   3. Follow the RUNBOOK at the bottom to deploy the app and run the upgrade.
#   4. terraform destroy when done (teardown gate).
#
# This is intentionally a self-contained root module so you can run the upgrade
# drill in isolation. The mini-project promotes the same cluster shape into the
# Week 04 modules/ library; here it is flat for clarity.
###############################################################################

terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Region for the regional cluster."
}

variable "network" {
  type        = string
  default     = "crunch-vpc"
  description = "The Week 03 VPC name."
}

variable "subnetwork" {
  type        = string
  default     = "crunch-us-central1"
  description = "The Week 03 subnet name in var.region."
}

variable "pods_range_name" {
  type        = string
  default     = "pods"
  description = "Secondary range name for pod alias IPs (Week 03)."
}

variable "services_range_name" {
  type        = string
  default     = "services"
  description = "Secondary range name for service alias IPs (Week 03)."
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Look up the currently-available node versions in the Regular channel so the
# exercise upgrades to a REAL version rather than a hard-coded one that may have
# aged out. We deliberately deploy on an OLDER version, then upgrade to a newer.
data "google_container_engine_versions" "regional" {
  location       = var.region
  version_prefix = "1."
}

###############################################################################
# The cluster. We separate the control plane from the node pool: create the
# cluster with remove_default_node_pool=true and a placeholder initial node
# count, then attach our own managed node pool. This is the production pattern —
# it lets the node pool be replaced without recreating the control plane.
###############################################################################
resource "google_container_cluster" "standard" {
  name     = "crunch-standard"
  location = var.region # a REGION (not a zone) => regional control plane, 99.95% SLA

  network    = var.network
  subnetwork = var.subnetwork

  # Use the Week 03 secondary ranges for pods and services (VPC-native).
  ip_allocation_policy {
    cluster_secondary_range_name  = var.pods_range_name
    services_secondary_range_name = var.services_range_name
  }

  # Workload Identity ON. The pool is always PROJECT_ID.svc.id.goog.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Regular release channel: the right default for production (Lecture 2 §2.2).
  release_channel {
    channel = "REGULAR"
  }

  # Upgrades only start in this window (your low-traffic trough in real life;
  # here it is permissive so the drill can run anytime).
  maintenance_policy {
    daily_maintenance_window {
      start_time = "02:00"
    }
  }

  # Pin the control plane to the OLDEST available Regular version so we have
  # somewhere to upgrade TO. In a real cluster you let the channel drive this.
  min_master_version = data.google_container_engine_versions.regional.valid_master_versions[
    length(data.google_container_engine_versions.regional.valid_master_versions) - 1
  ]

  # We manage our own node pool below.
  remove_default_node_pool = true
  initial_node_count       = 1

  # Shielded nodes are a cheap, obvious default.
  enable_shielded_nodes = true

  deletion_protection = false # so `terraform destroy` works for the exercise
}

###############################################################################
# The node pool. THIS is where the surge config lives. node_count is PER ZONE,
# so 1 in a regional cluster => 3 nodes (one per zone in us-central1's a/b/c).
###############################################################################
resource "google_container_node_pool" "default" {
  name     = "default-pool"
  cluster  = google_container_cluster.standard.name
  location = var.region

  node_count = 1 # per zone => 3 nodes total in a regional cluster

  # Deploy nodes on the SAME old version as the control plane so we can upgrade.
  version = google_container_cluster.standard.min_master_version

  # ---- THE LOAD-BEARING BLOCK FOR THIS EXERCISE ----
  # Surge, safe default: add 1 new node, drain 1 old onto it, never run below
  # the pool's capacity. Availability cost ~zero; money cost = 1 surge node for
  # the duration; time cost = one node per wave (Lecture 2 §2.4).
  upgrade_settings {
    strategy        = "SURGE"
    max_surge       = 1
    max_unavailable = 0
  }

  management {
    auto_repair  = true
    auto_upgrade = false # MANUAL: we drive the upgrade ourselves in this drill
  }

  node_config {
    machine_type = "e2-standard-2"
    disk_size_gb = 50
    disk_type    = "pd-balanced"

    # Workload Identity at the node level — GKE_METADATA exposes the WI-aware
    # metadata server to pods (the other half of the cluster-level setting).
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      workload = "fastapi"
    }
  }

  # Ignore version drift caused by the manual upgrade we perform via gcloud, so
  # a later `terraform plan` does not try to revert the node version.
  lifecycle {
    ignore_changes = [version]
  }
}

output "cluster_name" {
  value = google_container_cluster.standard.name
}

output "starting_version" {
  value       = google_container_cluster.standard.min_master_version
  description = "The (older) version we deploy on, before the upgrade drill."
}

output "get_credentials_command" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.standard.name} --region ${var.region}"
}

###############################################################################
# RUNBOOK — follow after `terraform apply`.
# (Comments only below; these are shell commands, not HCL.)
###############################################################################
#
# 1. Wire kubectl:
#      $(terraform output -raw get_credentials_command)
#
# 2. Deploy the FastAPI service + PDB from Exercise 1 (the same image and
#    manifests; substitute your PROJECT_ID into the image). Wait for 3 Ready.
#      kubectl rollout status deployment/fastapi --timeout=180s
#      kubectl get pdb fastapi-pdb
#      # MIN AVAILABLE 2, ALLOWED DISRUPTIONS 1
#
# 3. Start the load generator in its own terminal. We use `hey` against a
#    port-forward; in a real cluster you would hit a Service/LB. Run it for the
#    full duration of the upgrade (a few minutes). The point is ZERO failures.
#      kubectl port-forward service/fastapi 8080:80 >/dev/null 2>&1 &
#      sleep 2
#      # 200 requests/sec for 6 minutes (360s), 50 concurrent connections:
#      hey -z 360s -q 200 -c 50 http://localhost:8080/work
#
# 4. In another terminal, find the newer version to upgrade TO. The control
#    plane was pinned to the OLDEST; pick a NEWER valid version:
#      gcloud container get-server-config --region=us-central1 \
#        --format="value(channels[1].validVersions)" | tr ';' '\n' | head
#      NEW=<pick a newer 1.x-gke version from that list>
#
# 5. Upgrade the CONTROL PLANE first (nodes may never lead it — Lecture 2 §2.1).
#      gcloud container clusters upgrade crunch-standard \
#        --region=us-central1 --master --cluster-version="${NEW}" --quiet
#    Watch: kubectl keeps working throughout because the control plane is
#    REGIONAL (replicated across 3 zones, upgraded one at a time).
#
# 6. Upgrade the NODE POOL with the surge strategy already configured above.
#      gcloud container clusters upgrade crunch-standard \
#        --region=us-central1 --node-pool=default-pool \
#        --cluster-version="${NEW}" --quiet
#
# 7. Watch the surge dance and the PDB pacing it, in two terminals:
#      kubectl get nodes -w
#      # a surge node appears on the NEW version; an old node cordons (
#      # SchedulingDisabled), drains, and disappears; repeat per node.
#      kubectl get pdb fastapi-pdb -w
#      # ALLOWED DISRUPTIONS stays >= 0; when it hits 0 the drain WAITS for a
#      # replacement to become Ready before evicting the next pod.
#
# 8. When `hey` finishes, read its summary. With surge=1/unavailable=0 and
#    minAvailable:2 you should see:
#      Status code distribution:
#        [200] 72000 responses
#      (zero non-200s). THAT is "zero traffic loss through an upgrade."
#
# 9. PROVE the strategy matters: flip the pool to the cheap-risky config and
#    re-run the drill on a fresh version (or re-create the pool). Either you see
#    brief 5xx blips (capacity dips below load) or the upgrade STALLS on the PDB:
#      gcloud container node-pools update default-pool --cluster=crunch-standard \
#        --region=us-central1 --max-surge-upgrade=0 --max-unavailable-upgrade=1
#    You do not understand the strategies until you have watched one stall.
#
###############################################################################
# ACCEPTANCE CRITERIA
#   [ ] The cluster is REGIONAL (location is a region, not a zone).
#   [ ] The node pool has upgrade_settings { strategy=SURGE, max_surge=1,
#       max_unavailable=0 }.
#   [ ] Workload Identity is enabled at the cluster (workload_pool) AND node
#       pool (workload_metadata_config mode=GKE_METADATA) level.
#   [ ] You upgraded the control plane BEFORE the node pool.
#   [ ] The `hey` run spanning the node upgrade shows ZERO non-200 responses.
#   [ ] You reproduced a 5xx blip OR a stalled upgrade with the cheap-risky
#       config, and can explain which you saw and why.
###############################################################################
# TEARDOWN (do not skip)
#   # Delete any Service type=LoadBalancer FIRST (none here — fastapi is
#   # ClusterIP — but make it a habit so destroy doesn't orphan an LB):
#   kubectl delete service fastapi --ignore-not-found
#   terraform destroy -var project_id=$(gcloud config get-value project)
#   # Confirm no orphans:
#   gcloud compute forwarding-rules list   # empty
#   gcloud compute disks list              # no crunch-standard node disks
###############################################################################
