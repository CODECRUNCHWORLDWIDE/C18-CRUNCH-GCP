# =============================================================================
# Exercise 2 — Regional MIG with CPU autoscaling
# =============================================================================
#
# Goal: Build a REGIONAL managed instance group from the hardened instance
#       template, attach a regional autoscaler that scales on CPU utilization,
#       wire an autohealing health check, and validate scale-out under load.
#
# Estimated time: 90 minutes.
#
# HOW TO USE THIS FILE
#
#   1. Drop this file into a fresh working dir, e.g. envs/dev/exercise-02/.
#   2. Copy data.tf, variables.tf, versions.tf, service-account.tf,
#      instance-template.tf, startup.sh, and main.go from Exercise 1 into the
#      same directory (the MIG reuses the SAME hardened template). Adjust the
#      backend prefix in versions.tf to "envs/dev/exercise-02".
#   3. terraform init && terraform apply -var="project_id=$(gcloud config get-value project)"
#   4. Run the load test in the "VALIDATE" comment block at the bottom and
#      watch the MIG scale from 2 -> up to 6 instances on CPU.
#   5. terraform destroy. Confirm `gcloud compute instances list` => Listed 0 items.
#
# ACCEPTANCE CRITERIA
#
#   [ ] terraform apply is clean; a REGIONAL MIG exists spread across zones.
#   [ ] `gcloud compute instance-groups managed list` shows your MIG, regional.
#   [ ] The MIG holds the autoscaler's minimum (2) at idle.
#   [ ] Under sustained CPU load it scales OUT toward max (6) within ~2-3 min.
#   [ ] When load stops it scales IN back toward min after the stabilization
#       window (this is deliberately slower than scale-out).
#   [ ] An instance you manually delete is RECREATED by autohealing.
#   [ ] Teardown is clean.
#
# This file assumes the Exercise 1 template resource is named
# `google_compute_instance_template.workserver` and the firewall rule
# `google_compute_firewall.allow_health_check` (source ranges 130.211.0.0/22
# and 35.191.0.0/16) is present. Both come from Exercise 1.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Health check used for BOTH autohealing and (in the mini-project) the LB.
#
# Note: an autohealing health check should be CONSERVATIVE. If it is too
# aggressive it will kill instances that are merely slow under load, which
# turns a load spike into a recreation storm. We poll /healthz, which returns
# 200 cheaply and does NOT do per-request CPU work — so a busy instance still
# answers it. Never point an autohealing check at an endpoint that does real
# work; you will recreate exactly the instances that are earning their keep.
# -----------------------------------------------------------------------------
resource "google_compute_health_check" "workserver" {
  name               = "week5-workserver-hc"
  project            = var.project_id
  check_interval_sec = 5
  timeout_sec        = 5
  healthy_threshold  = 2
  unhealthy_threshold = 3 # 3 * 5s = 15s of failure before we recreate

  http_health_check {
    port         = 8080
    request_path = "/healthz"
  }

  log_config {
    enable = true
  }
}

# -----------------------------------------------------------------------------
# The REGIONAL managed instance group.
#
# Regional (not zonal) so instances spread across all zones in the region and
# the group survives a single-zone outage. distribution_policy controls the
# spread; we let it use all zones in the region.
# -----------------------------------------------------------------------------
resource "google_compute_region_instance_group_manager" "workserver" {
  name               = "week5-workserver-mig"
  project            = var.project_id
  region             = var.region
  base_instance_name = "week5-workserver"

  # Spread across all zones in the region. With < 3 zones available the MIG
  # uses what it can; with 3+ it balances evenly for zone-loss survival.
  distribution_policy_target_shape = "EVEN"

  version {
    instance_template = google_compute_instance_template.workserver.self_link
  }

  named_port {
    name = "http"
    port = 8080
  }

  # Autohealing: if an instance fails the health check, recreate it.
  # initial_delay_sec must cover the startup script's build-and-start time,
  # or the MIG will recreate instances that are simply still booting.
  auto_healing_policies {
    health_check      = google_compute_health_check.workserver.id
    initial_delay_sec = 180
  }

  # Rolling-update policy. You will lean on this hard in Exercise 3 and the
  # mini-project; setting it now means an instance-template change rolls
  # safely instead of replacing everything at once.
  update_policy {
    type                         = "PROACTIVE"
    minimal_action               = "REPLACE"
    max_surge_fixed              = 3 # create up to 3 extra before removing old
    max_unavailable_fixed        = 0 # never drop below target during a roll
    replacement_method           = "SUBSTITUTE"
    instance_redistribution_type = "PROACTIVE"
  }

  # The autoscaler (below) owns target_size, so we do NOT set it here.
  # Setting both fights for ownership and produces perpetual diffs.

  lifecycle {
    # Let the autoscaler own size; ignore drift on target_size.
    ignore_changes = [target_size]
  }
}

# -----------------------------------------------------------------------------
# The regional autoscaler. Scales on CPU utilization with a target of 60%.
#
# - min_replicas 2 keeps two instances for AZ-spread even at idle.
# - max_replicas 6 caps the lab cost (and proves scale-out without a huge bill).
# - cooldown_period is how long after a new instance boots before its metrics
#   count, so warm-up CPU doesn't trigger more scale-out.
# - scale_in_control deliberately makes scale-IN slower than scale-OUT: you
#   scale out fast to protect latency, and scale in slowly to avoid flapping.
# -----------------------------------------------------------------------------
resource "google_compute_region_autoscaler" "workserver" {
  name    = "week5-workserver-autoscaler"
  project = var.project_id
  region  = var.region
  target  = google_compute_region_instance_group_manager.workserver.id

  autoscaling_policy {
    min_replicas    = 2
    max_replicas    = 6
    cooldown_period = 90

    cpu_utilization {
      target = 0.6 # scale to keep average CPU near 60%
    }

    # Scale in no more than 1 instance per 120s window. Protects against the
    # "load drops for 10s, autoscaler kills half the fleet, load returns,
    # everyone scrambles to scale back out" flap.
    scale_in_control {
      max_scaled_in_replicas {
        fixed = 1
      }
      time_window_sec = 120
    }
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------
output "mig_self_link" {
  value = google_compute_region_instance_group_manager.workserver.self_link
}

output "mig_instance_group" {
  description = "The instance-group resource the LB will back onto in the mini-project."
  value       = google_compute_region_instance_group_manager.workserver.instance_group
}

# =============================================================================
# VALIDATE — run these after `terraform apply`
# =============================================================================
#
# 1) Confirm the MIG is regional and at min size (2):
#
#      gcloud compute instance-groups managed list
#      gcloud compute instance-groups managed list-instances \
#        week5-workserver-mig --region="$(gcloud config get-value compute/region)"
#
#    Expect 2 instances, spread across zones (the zone column differs).
#
# 2) Stand up a tiny in-VPC load generator (no external IP, reaches instances
#    over the internal network) and install `hey`:
#
#      ZONE="$(gcloud config get-value compute/region)-b"
#      gcloud compute instances create week5-loadgen \
#        --machine-type=e2-small --zone="$ZONE" \
#        --image-family=debian-12 --image-project=debian-cloud \
#        --metadata=enable-oslogin=TRUE --no-address \
#        --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring
#      gcloud compute ssh week5-loadgen --zone="$ZONE" --tunnel-through-iap \
#        --command="sudo apt-get update -y && sudo apt-get install -y hey || (sudo apt-get install -y golang-go && go install github.com/rakyll/hey@latest)"
#
# 3) Get one MIG instance's internal IP (any of them; the LB comes in the
#    mini-project, here we hit an instance directly to drive CPU):
#
#      gcloud compute instances list \
#        --format="table(name, networkInterfaces[0].networkIP, zone.basename())"
#
# 4) From the load generator, hammer the CPU-bound endpoint for 4 minutes:
#
#      gcloud compute ssh week5-loadgen --zone="$ZONE" --tunnel-through-iap \
#        --command="~/go/bin/hey -z 4m -c 80 http://<MIG_INSTANCE_IP>:8080/work"
#
#    (Hit several instances in parallel, or in the mini-project hit the LB VIP,
#     to drive the GROUP's average CPU up. For this exercise, driving one box
#     to ~100% pulls the regional average over 60% and triggers scale-out.)
#
# 5) Watch the MIG scale out (in another terminal, re-run every 20s):
#
#      watch -n 20 'gcloud compute instance-groups managed list-instances \
#        week5-workserver-mig --region="$(gcloud config get-value compute/region)"'
#
#    Within ~2-3 minutes you should see instance count climb from 2 toward 6.
#
# 6) Stop the load. After the stabilization/scale-in window (a few minutes,
#    slowed by scale_in_control) the count returns to 2.
#
# 7) Prove autohealing: delete one instance by name and watch it come back:
#
#      gcloud compute instances delete <one-instance-name> \
#        --zone=<its-zone> --quiet
#      # The MIG recreates it within initial_delay + a health-check cycle.
#
# =============================================================================
# EXPECTED (shape, not exact numbers)
# =============================================================================
#
#   NAME                       ZONE           STATUS
#   week5-workserver-abc1      us-central1-a  RUNNING
#   week5-workserver-def2      us-central1-b  RUNNING      <- idle: 2
#   ... under load ...
#   week5-workserver-abc1      us-central1-a  RUNNING
#   week5-workserver-def2      us-central1-b  RUNNING
#   week5-workserver-ghi3      us-central1-c  RUNNING
#   week5-workserver-jkl4      us-central1-a  RUNNING
#   week5-workserver-mno5      us-central1-b  RUNNING
#   week5-workserver-pqr6      us-central1-c  RUNNING      <- scaled to max 6
#
# =============================================================================
# TEARDOWN
# =============================================================================
#
#   gcloud compute instances delete week5-loadgen --zone="$ZONE" --quiet
#   terraform destroy -var="project_id=$(gcloud config get-value project)" -auto-approve
#   gcloud compute instances list   # expect: Listed 0 items.
#   gcloud compute disks list        # expect: no orphaned disks
#
# =============================================================================
# WHY EACH KNOB IS SET THE WAY IT IS (read before you change anything)
# =============================================================================
#
#   - Regional, not zonal: a zonal MIG dies with its zone. Regional spreads
#     across zones so a single-AZ loss drops at most 1/3 of capacity, and the
#     autoscaler + autohealer refill the survivors.
#
#   - cpu_utilization.target = 0.6: leaves 40% headroom for the lag between
#     "CPU rises" and "new instance is serving." Set it to 0.9 and your latency
#     blows up during the scale-out lag because you started too late.
#
#   - max_unavailable_fixed = 0 in update_policy: a rolling update must never
#     reduce serving capacity below target. With max_surge=3 it adds capacity
#     first, then removes old instances. This is the zero-drop precondition you
#     prove in the mini-project.
#
#   - scale_in_control slower than scale-out: scaling in aggressively saves a
#     few cents and risks a latency cliff when load returns. Scale out for
#     latency; scale in for cost; never let the cost side win a fight with the
#     latency side.
#
#   - autohealing initial_delay_sec = 180: must exceed the startup script's
#     build-and-start time. Too short and the MIG recreates instances that are
#     merely still booting -> infinite recreation loop. This is the single most
#     common MIG misconfiguration.
