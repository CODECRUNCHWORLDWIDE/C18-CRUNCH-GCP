# Exercise 2 — An IAM Condition Scoped by Resource Tag and Time Window
#
# Goal: Grant a group `roles/compute.instanceAdmin.v1` that is true ONLY when
#       (a) the target resource carries the tag `environment=staging`, AND
#       (b) the request happens inside a weekday maintenance window.
#       This is "scoped in space and time" — the binding is narrow on both axes.
#
#       Expected outcome: outside the window, or on a non-staging resource, the
#       same group gets a 403. Inside the window, on a staging-tagged resource,
#       it works. You prove both halves.
#
# Estimated time: 45 minutes.
#
# HOW TO USE THIS FILE
#
#   1. Copy this file into a fresh directory as `main.tf`.
#   2. Fill in the three TODOs (the CEL expression has two clauses + a binding).
#   3. Initialize and apply:
#
#        export PROJECT_ID="$(gcloud config get-value project)"
#        export TF_VAR_project_id="$PROJECT_ID"
#        export TF_VAR_admin_group="group:platform-staging@example.com"  # a real group you own
#        terraform init
#        terraform apply
#
#   4. Verify with `gcloud asset analyze-iam-policy` and a real access test.
#   5. Tear down: `terraform destroy`
#
# ACCEPTANCE CRITERIA
#
#   [ ] The binding uses a CONDITION (not an unconditional binding).
#   [ ] The condition has TWO clauses joined by &&: a tag match AND a time window.
#   [ ] The tag clause uses resource.matchTag() (not a string-prefix hack).
#   [ ] The time clause references request.time and getHours() in UTC.
#   [ ] `terraform apply` succeeds with no errors.
#   [ ] You demonstrate a DENY outside the window and an ALLOW inside it.
#   [ ] No service-account key created anywhere.
#
# SMOKE OUTPUT (target)
#
#   Apply complete! Resources: 3 added, 0 changed, 0 destroyed.
#   Outputs:
#     condition_title = "staging-and-maintenance-window"
#
# Inline hints at the bottom of this file.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
}

variable "project_id" {
  type        = string
  description = "Target project for the conditional binding."
}

variable "admin_group" {
  type        = string
  description = "Member string, e.g. group:platform-staging@example.com"
}

# A tag key/value the condition will match on. Tags are org/project-level
# key=value pairs you attach to resources for access control and policy.
resource "google_tags_tag_key" "environment" {
  parent      = "projects/${var.project_id}"
  short_name  = "environment"
  description = "Deployment environment for IAM-condition scoping."
}

resource "google_tags_tag_value" "staging" {
  parent      = google_tags_tag_key.environment.id
  short_name  = "staging"
  description = "The staging environment value."
}

# ---------------------------------------------------------------------------
# TODO 1 — Write the tag-match clause of the CEL condition.
#
# We want: the bound resource must carry environment=staging.
# IAM conditions express this with resource.matchTag(KEY_NAMESPACE, VALUE),
# where KEY_NAMESPACE is "<project_id>/environment" and VALUE is "staging".
#
# Replace the empty string below with the matchTag() call. Use string
# interpolation for var.project_id. It should look like:
#   resource.matchTag('PROJECT_ID/environment', 'staging')
# ---------------------------------------------------------------------------
locals {
  tag_clause = "" # TODO 1: resource.matchTag('${var.project_id}/environment', 'staging')

  # -------------------------------------------------------------------------
  # TODO 2 — Write the maintenance-window clause of the CEL condition.
  #
  # We want: the request must occur Mon–Fri between 02:00 and 06:00 UTC.
  # IAM conditions give you request.time (a Timestamp). Use:
  #   request.time.getHours('UTC')           -> 0..23
  #   request.time.getDayOfWeek('UTC')       -> 0 (Sun) .. 6 (Sat)
  #
  # Compose: hours in [2,6) AND day in [1,5] (Mon=1 .. Fri=5).
  # Replace the empty string below.
  # -------------------------------------------------------------------------
  time_clause = "" # TODO 2: request.time.getHours('UTC') >= 2 && request.time.getHours('UTC') < 6 && request.time.getDayOfWeek('UTC') >= 1 && request.time.getDayOfWeek('UTC') <= 5

  condition_expression = "${local.tag_clause} && ${local.time_clause}"
}

# ---------------------------------------------------------------------------
# TODO 3 — Write the conditional IAM binding.
#
# Use google_project_iam_member (NOT iam_binding — _binding is authoritative
# for the whole role and will clobber other members of that role; _member adds
# one member non-destructively, which is what you almost always want).
#
# Grant var.admin_group the role roles/compute.instanceAdmin.v1 with the
# condition built above. Give the condition a title and description.
# ---------------------------------------------------------------------------
resource "google_project_iam_member" "conditional_admin" {
  project = var.project_id
  role    = "roles/compute.instanceAdmin.v1"
  member  = var.admin_group

  # TODO 3: add the condition block. It must reference local.condition_expression.
  condition {
    title       = "staging-and-maintenance-window"
    description = "Compute admin only on environment=staging, Mon-Fri 02:00-06:00 UTC."
    expression  = local.condition_expression
  }
}

output "condition_title" {
  value = google_project_iam_member.conditional_admin.condition[0].title
}

output "condition_expression" {
  value = local.condition_expression
}

# ===========================================================================
# VERIFICATION (run after apply)
# ===========================================================================
#
# 1. Inspect the rendered condition:
#
#      terraform output condition_expression
#
#    It should print BOTH clauses joined by &&, e.g.:
#      resource.matchTag('my-proj/environment', 'staging') &&
#      request.time.getHours('UTC') >= 2 && request.time.getHours('UTC') < 6 &&
#      request.time.getDayOfWeek('UTC') >= 1 && request.time.getDayOfWeek('UTC') <= 5
#
# 2. Confirm the binding exists with its condition:
#
#      gcloud projects get-iam-policy "$PROJECT_ID" --format=json \
#        | jq '.bindings[] | select(.role=="roles/compute.instanceAdmin.v1")'
#
#    You should see a "condition" object on the binding. A binding with a
#    "condition" requires policy schema version 3 — gcloud handles this for you.
#
# 3. Prove the TIME gate (this is the satisfying part). Conditions are evaluated
#    at request time, so the same identity is allowed or denied depending on the
#    clock. Use Policy Troubleshooter's condition simulation:
#
#      # Tag present + inside window  -> CONDITIONAL/GRANTED
#      # Tag absent  OR outside window -> NOT_GRANTED
#    Read the troubleshooter output and confirm the access flips with the clock.
#
# ===========================================================================
# TEARDOWN
# ===========================================================================
#
#   terraform destroy
#
#   # Zero-keys promise — this exercise creates no SA and no keys, but confirm:
#   gcloud iam service-accounts keys list --managed-by=user \
#     --format='value(name)' 2>/dev/null || true
#
# ===========================================================================
# HINTS
# ===========================================================================
#
# HINT 1 (TODO 1): The tag namespace is "<project_id>/<short_name>". For a
#   project-scoped tag key named "environment" in project "my-proj", that is
#   "my-proj/environment". matchTag's second arg is the VALUE short_name,
#   "staging". So:
#     resource.matchTag('${var.project_id}/environment', 'staging')
#   Note: matchTag uses the namespaced name, matchTagId uses the numeric IDs.
#   The namespaced form is more readable; prefer it.
#
# HINT 2 (TODO 2): getDayOfWeek returns 0=Sunday..6=Saturday. Mon-Fri is 1..5.
#   getHours with 'UTC' avoids the trap where the evaluator's local timezone
#   shifts your window. ALWAYS pin the timezone in IAM-condition time math.
#     request.time.getHours('UTC') >= 2 && request.time.getHours('UTC') < 6 &&
#     request.time.getDayOfWeek('UTC') >= 1 && request.time.getDayOfWeek('UTC') <= 5
#
# HINT 3 (TODO 3): _member vs _binding vs _policy is the single most dangerous
#   choice in GCP Terraform. _policy = "this is the ENTIRE policy" (wipes all
#   else). _binding = "these are ALL members of this role" (wipes other members
#   of that role). _member = "add this ONE member" (additive, safe). When in
#   doubt, _member. The condition block goes inside the _member resource.
