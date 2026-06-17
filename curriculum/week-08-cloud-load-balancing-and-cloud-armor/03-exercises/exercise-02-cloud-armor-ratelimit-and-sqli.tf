###############################################################################
# Exercise 2 — A Cloud Armor security policy: per-source-IP rate-based ban +
#              a preconfigured SQLi WAF rule, attached to the Exercise 1
#              backend service.
#
# Goal: Write the ordered CEL policy from Lecture 2 §2.5 (WAF before rate limit,
#       default allow tail), attach it to `edge-run-backend` from Exercise 1,
#       then PROVE it with `hey` (the rate limit trips into 429s) and a malformed
#       `curl` (the SQLi WAF returns 403) — and find both in the Cloud Armor logs.
#
# Estimated time: ~45 minutes (5 of which is the policy attaching + propagating).
#
# HOW TO USE THIS FILE
#   1. Complete Exercise 1 first and LEAVE THE LB UP. This file references the
#      `edge-run-backend` backend service Exercise 1 created.
#   2. Put this file alongside Exercise 1's lb.tf (same working dir, same state),
#      OR run it standalone with -var backend_service_name=edge-run-backend if
#      the backend already exists outside this state (see the data source below).
#   3. terraform init && terraform apply -var project_id=$(gcloud config get-value project)
#   4. Follow the RUNBOOK at the bottom to validate.
#   5. terraform destroy when done (teardown gate). This detaches + deletes the
#      policy; it does NOT delete the Exercise 1 LB.
#
# NOTE ON TEST SAFETY: we lower the rate-limit threshold to 100 req / 60s so `hey`
# trips it in seconds, and we enable the SQLi WAF in ENFORCING mode directly —
# which is safe here ONLY because the origin's `/` path has no legitimate SQL-ish
# traffic. In production you ship WAF rules in preview mode first (Lecture 2 §2.4).
###############################################################################

terraform {
  required_version = ">= 1.9.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = "us-central1"
}

variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "backend_service_name" {
  type        = string
  default     = "edge-run-backend"
  description = "The Exercise 1 backend service to protect."
}

variable "office_cidr" {
  type        = string
  default     = "203.0.113.0/24"
  description = "An allowlisted CIDR that is never rate-limited or WAF-blocked. Set to YOUR public /32 if you want to exempt yourself; leave as the doc range to test the block path against yourself."
}

# Look up the Exercise 1 backend service so we can attach the policy to it,
# regardless of whether it lives in this Terraform state or another.
data "google_compute_backend_service" "target" {
  name = var.backend_service_name
}

###############################################################################
# The security policy — ordered exactly as Lecture 2 §2.5 prescribes.
###############################################################################

resource "google_compute_security_policy" "edge" {
  name        = "crunch-edge-policy"
  description = "Office allow -> SQLi WAF -> per-IP rate-based ban -> default allow."

  # --- 100: office allowlist (never blocked by anything below) --------------
  rule {
    action      = "allow"
    priority    = 100
    description = "Office allowlist."
    match {
      expr {
        expression = "inIpRange(origin.ip, '${var.office_cidr}')"
      }
    }
  }

  # --- 900: preconfigured SQLi WAF (runs BEFORE the rate limit so a SQLi -----
  #          probe logs as a 403/DENY, not a 429/RATE_BASED_BAN) --------------
  rule {
    action      = "deny(403)"
    priority    = 900
    description = "WAF: block SQL injection (OWASP CRS 3.3 stable)."
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      }
    }
  }

  # --- 1000: per-source-IP rate-based ban -----------------------------------
  rule {
    action      = "rate_based_ban"
    priority    = 1000
    description = "Per-IP: 100 req / 60s -> 429, then ban the IP for 5 min."
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      enforce_on_key   = "IP"           # count per real TCP peer, not XFF (Lecture 2 §2.6)
      conform_action   = "allow"
      exceed_action    = "deny(429)"
      ban_duration_sec = 300
      rate_limit_threshold {
        count        = 100
        interval_sec = 60
      }
      ban_threshold {
        count        = 100
        interval_sec = 60
      }
    }
  }

  # --- max int: default allow tail ------------------------------------------
  rule {
    action      = "allow"
    priority    = 2147483647
    description = "Default allow (public site posture)."
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }

  # Make sure Cloud Armor request logging is verbose enough to see which rule
  # matched (NORMAL logs allow+deny; VERBOSE adds matched-rule detail).
  advanced_options_config {
    log_level = "VERBOSE"
  }
}

###############################################################################
# Attach the policy to the Exercise 1 backend service.
#
# A backend service can have exactly one security_policy. The cleanest way to
# attach without re-declaring the whole backend service (which lives in
# Exercise 1's state) is the dedicated association resource:
###############################################################################

resource "google_compute_backend_service_security_policy" "attach" {
  backend_service = data.google_compute_backend_service.target.name
  security_policy = google_compute_security_policy.edge.id
}

output "policy_name" {
  value = google_compute_security_policy.edge.name
}

output "attached_to" {
  value = data.google_compute_backend_service.target.name
}

###############################################################################
# RUNBOOK — validate the policy (run after `terraform apply` + ~2 min propagate)
#
# Set HOST to your Exercise 1 hostname:
#   HOST=$(terraform output -raw hostname 2>/dev/null) || HOST=<your LB host>
#
# --- 1) The WAF: a SQLi probe must return 403 -------------------------------
#   curl -si "https://$HOST/?q=1%20OR%201%3D1" | head -1
#   curl -si "https://$HOST/?id=1%27%20UNION%20SELECT%20password%20FROM%20users--" | head -1
#   # Expect: HTTP/2 403 on both. A clean request still works:
#   curl -si "https://$HOST/" | head -1            # HTTP/2 200
#
# --- 2) The rate limit: drive past 100 req / 60s and watch 429s appear ------
#   # `hey` sends 300 requests at concurrency 20 to the clean root.
#   hey -n 300 -c 20 "https://$HOST/"
#   # In the "Status code distribution" you should see a mix of 200 and 429,
#   # then once the ban trips, a run of 429s. Re-run within 5 min => all 429
#   # (you are banned). Wait 5+ min (ban_duration_sec) => 200s return.
#
#   # If you allowlisted your own /32 in var.office_cidr, you will NOT be limited
#   # (priority-100 allow runs first). Set office_cidr back to the doc range
#   # 203.0.113.0/24 to test the limit against yourself.
#
# --- 3) Find both in the Cloud Armor logs (the authoritative proof) ---------
#   # The SQLi 403 logs as a DENY at priority 900:
#   gcloud logging read \
#     'resource.type="http_load_balancer"
#      jsonPayload.enforcedSecurityPolicy.configuredAction="DENY"' \
#     --limit=5 \
#     --format='value(timestamp, httpRequest.requestUrl,
#       jsonPayload.enforcedSecurityPolicy.priority,
#       jsonPayload.enforcedSecurityPolicy.configuredAction)'
#   # Expect a row: <url with ?q=1 OR 1=1>  900  DENY
#
#   # The rate-limit ban logs as RATE_BASED_BAN at priority 1000:
#   gcloud logging read \
#     'resource.type="http_load_balancer"
#      jsonPayload.enforcedSecurityPolicy.configuredAction="RATE_BASED_BAN"' \
#     --limit=5 \
#     --format='value(timestamp,
#       jsonPayload.enforcedSecurityPolicy.priority,
#       jsonPayload.enforcedSecurityPolicy.configuredAction)'
#   # Expect rows at priority 1000, action RATE_BASED_BAN.
#
# PROOF OF DONE:
#   - SQLi curl -> 403, logged as DENY @ priority 900.
#   - hey flood -> 429s past the threshold, logged as RATE_BASED_BAN @ 1000.
#   - clean curl -> 200.
#
# --- TEARDOWN (the gate) ----------------------------------------------------
#   terraform destroy -var project_id=$(gcloud config get-value project)
#   # This detaches + deletes the policy. Exercise 1's LB stays up; tear that
#   # down separately if you are not continuing to the challenge.
###############################################################################
