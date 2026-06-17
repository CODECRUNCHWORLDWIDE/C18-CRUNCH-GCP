###############################################################################
# Exercise 2 — Define an SLO and a multi-window burn-rate alert that does not
#              page on noise.
#
# Goal: For a Cloud Run service, define a 99.9% / 28-day availability SLO, then
#       arm a FAST-BURN page (14.4x, 1h AND 5m) and a SLOW-BURN ticket
#       (1x, 3d AND 6h). The fast burn pages; the slow burn tickets. The
#       long+short window AND-combiner is what keeps recovered incidents from
#       paging you.
#
# Estimated time: 50 minutes.
#
# HOW TO USE THIS FILE
#
#   1. Put this file in an empty directory as `main.tf`.
#   2. Fill in the THREE TODOs below.
#   3. Run:
#        terraform init
#        terraform apply -var="project_id=$(gcloud config get-value project)" \
#                        -var="alert_email=you@example.com" \
#                        -var="service_name=otel-ex01"
#   4. Validate by injecting errors (see the VALIDATION block at the bottom),
#      then `terraform destroy` to tear it down.
#
# ACCEPTANCE CRITERIA
#   [ ] terraform apply succeeds with no errors.
#   [ ] A Service, an SLO (goal 0.999, rolling 28d), and TWO alert policies exist
#       in Cloud Monitoring.
#   [ ] The fast-burn policy is severity CRITICAL with two conditions (1h + 5m)
#       combined with AND, threshold 14.4.
#   [ ] The slow-burn policy is severity WARNING with two conditions (3d + 6h),
#       threshold 1.0, and does NOT route to a pager-class channel.
#   [ ] Injecting a >=14.4x burn fires the fast-burn page; injecting a 1% (10x)
#       burn does NOT fire the 14.4x page but eventually fires the slow-burn ticket.
###############################################################################

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.40, < 7.0"
    }
  }
}

variable "project_id" { type = string }

variable "service_name" {
  type    = string
  default = "otel-ex01"
}

variable "run_location" {
  type    = string
  default = "us-central1"
}

variable "alert_email" {
  type        = string
  description = "Where the page/ticket notifications go (use a real address you can check)."
}

provider "google" {
  project = var.project_id
}

# -----------------------------------------------------------------------------
# 1. The Service the SLO is about (a Cloud Run service).
# -----------------------------------------------------------------------------
resource "google_monitoring_service" "svc" {
  project      = var.project_id
  service_id   = "${var.service_name}-svc"
  display_name = "${var.service_name} (Cloud Run)"

  basic_service {
    service_type = "CLOUD_RUN"
    service_labels = {
      service_name = var.service_name
      location     = var.run_location
    }
  }
}

# -----------------------------------------------------------------------------
# 2. The SLO: 99.9% of requests over a rolling 28 days return non-5xx.
#
# TODO 1 — Complete the request_based_sli.good_total_ratio block so that:
#          - total counts ALL run.googleapis.com/request_count for this service,
#          - good counts the same metric EXCLUDING response_code_class = "5xx".
#          The filter strings are GCP monitoring filters; the "good" filter is the
#          "total" filter plus  metric.label."response_code_class"!="5xx".
# -----------------------------------------------------------------------------
resource "google_monitoring_slo" "availability" {
  project      = var.project_id
  service      = google_monitoring_service.svc.service_id
  slo_id       = "${var.service_name}-availability"
  display_name = "${var.service_name} availability 99.9% / 28d"

  goal                = 0.999
  rolling_period_days = 28

  request_based_sli {
    good_total_ratio {
      # TODO 1: fill in good_service_filter and total_service_filter.
      good_service_filter  = "" # <-- replace
      total_service_filter = "" # <-- replace
    }
  }
}

# -----------------------------------------------------------------------------
# 3. Notification channel.
# -----------------------------------------------------------------------------
resource "google_monitoring_notification_channel" "oncall" {
  project      = var.project_id
  display_name = "${var.service_name} on-call"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

# -----------------------------------------------------------------------------
# 4a. FAST-BURN page: 14.4x over 1h AND 14.4x over 5m -> PAGE (CRITICAL).
#
# TODO 2 — Add the SECOND condition (the 5-minute short window). The first
#          condition (1h) is given. The short window confirms the burn is STILL
#          happening, so a recovered incident does not page. Use the same
#          threshold (14.4) and the select_slo_burn_rate function with a 300s
#          lookback.
# -----------------------------------------------------------------------------
resource "google_monitoring_alert_policy" "fast_burn" {
  project      = var.project_id
  display_name = "${var.service_name} SLO fast burn (14.4x) — PAGE"
  combiner     = "AND" # both windows must agree
  severity     = "CRITICAL"

  conditions {
    display_name = "Fast burn 1h"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.availability.id}\", \"3600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 14.4
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
      }
    }
  }

  # TODO 2: add the second condition block for the 5-minute (300s) short window.

  notification_channels = [google_monitoring_notification_channel.oncall.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    subject   = "PAGE: ${var.service_name} burning error budget fast (14.4x)"
    content   = "User-visible risk, needs action now. Open Cloud Trace (status=ERROR), read correlated logs, check the latest deploy and roll back if it correlates."
    mime_type = "text/markdown"
  }
}

# -----------------------------------------------------------------------------
# 4b. SLOW-BURN ticket: 1x over 3d AND 1x over 6h -> TICKET (WARNING).
#     This deliberately does NOT page. A slow leak is fixed in business hours.
#
# TODO 3 — Set the severity to WARNING (not CRITICAL) so your routing layer
#          treats it as a ticket, not a page. (We use the same email channel
#          here for the exercise; in production this routes to a ticket queue.)
# -----------------------------------------------------------------------------
resource "google_monitoring_alert_policy" "slow_burn" {
  project      = var.project_id
  display_name = "${var.service_name} SLO slow burn (1x) — TICKET"
  combiner     = "AND"
  severity     = "" # <-- TODO 3: set to WARNING

  conditions {
    display_name = "Slow burn 3d"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.availability.id}\", \"259200s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 1.0
      duration        = "0s"
      aggregations {
        alignment_period   = "3600s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
      }
    }
  }

  conditions {
    display_name = "Slow burn 6h"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.availability.id}\", \"21600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 1.0
      duration        = "0s"
      aggregations {
        alignment_period   = "3600s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.oncall.id]

  documentation {
    subject   = "TICKET: ${var.service_name} slow error-budget burn (1x)"
    content   = "Slow burn. NOT a page. The budget is leaking but you have days. Investigate in business hours."
    mime_type = "text/markdown"
  }
}

output "slo_id" {
  value = google_monitoring_slo.availability.id
}

###############################################################################
# VALIDATION (run after apply)
#
#   1. Deploy the FaultInjectionMiddleware from Lecture 2 into the service and
#      point traffic at it (hey -z 30m -q 50 https://<url>/health).
#   2. Set FAULT_RATE=0.02 (a 20x burn vs 99.9% SLO) on a new revision, 100%
#      traffic. The 14.4x FAST-BURN page should fire within a few minutes.
#   3. Set FAULT_RATE=0.01 (a 10x burn). The 14.4x page should NOT fire (10 < 14.4);
#      the slow-burn ticket will fire after its windows fill.
#   4. Set FAULT_RATE=0.0. Watch the short window drop and the page auto-close
#      (auto_close = 1800s + the AND-combiner short window).
#   5. Confirm no CPU/memory/restart "cause" alert fired. Only the symptom did.
#
# TEARDOWN
#   terraform destroy -var="project_id=..." -var="alert_email=..." -var="service_name=..."
###############################################################################

###############################################################################
# REFERENCE SOLUTION — do not read until your version applies.
#
# TODO 1:
#   good_service_filter = join(" AND ", [
#     "metric.type=\"run.googleapis.com/request_count\"",
#     "resource.type=\"cloud_run_revision\"",
#     "resource.label.\"service_name\"=\"${var.service_name}\"",
#     "metric.label.\"response_code_class\"!=\"5xx\"",
#   ])
#   total_service_filter = join(" AND ", [
#     "metric.type=\"run.googleapis.com/request_count\"",
#     "resource.type=\"cloud_run_revision\"",
#     "resource.label.\"service_name\"=\"${var.service_name}\"",
#   ])
#
# TODO 2 (second condition in fast_burn):
#   conditions {
#     display_name = "Fast burn 5m"
#     condition_threshold {
#       filter          = "select_slo_burn_rate(\"${google_monitoring_slo.availability.id}\", \"300s\")"
#       comparison      = "COMPARISON_GT"
#       threshold_value = 14.4
#       duration        = "0s"
#       aggregations {
#         alignment_period   = "300s"
#         per_series_aligner = "ALIGN_NEXT_OLDER"
#       }
#     }
#   }
#
# TODO 3:
#   severity = "WARNING"
###############################################################################
