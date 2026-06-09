###############################################################################
# Exercise 2 — Refactor a duplicated resource block into a for_each-driven
#              module consumed by two environments.
#
# Goal: You are handed a root module with THREE near-identical
#       google_compute_subnetwork blocks (the "STARTING POINT" below). Refactor
#       them into ONE for_each-driven module under modules/vpc/, then consume
#       that module from envs/dev and envs/prod with DIFFERENT CIDR maps.
#
#       Expected outcome:
#         - One subnet resource block, addressed by stable keys
#           (google_compute_subnetwork.this["app"], not [0]).
#         - dev and prod share the module, differ only in inputs.
#         - Reordering the subnet map causes ZERO plan changes (stable addressing).
#
# Estimated time: 75 minutes.
#
# HOW TO USE THIS FILE
#   This single .tf file documents the WHOLE exercise: the starting point you
#   refactor away from, the target file layout, the commands to run, and the
#   full solution at the bottom. Lay the files out on disk as shown in the
#   "TARGET LAYOUT" comment, fill in modules/vpc/, and run the commands. Peek at
#   the SOLUTION fence only when stuck.
#
# TARGET LAYOUT (create these files on disk)
#   ex02/
#   ├── modules/
#   │   └── vpc/
#   │       ├── main.tf        <-- the for_each block (YOU WRITE THIS)
#   │       ├── variables.tf   <-- inputs (YOU WRITE THIS)
#   │       ├── outputs.tf      <-- outputs (YOU WRITE THIS)
#   │       └── versions.tf     <-- provider pin (given below)
#   ├── envs/
#   │   ├── dev/
#   │   │   └── main.tf         <-- calls ../../modules/vpc with dev CIDRs
#   │   └── prod/
#   │       └── main.tf         <-- calls ../../modules/vpc with prod CIDRs
#
# COMMANDS
#   cd ex02/envs/dev  && terraform init && terraform apply -var="project_id=$TF_PROJECT"
#   cd ../prod        && terraform init && terraform apply -var="project_id=$TF_PROJECT"
#
# ACCEPTANCE CRITERIA
#   [ ] modules/vpc has ONE google_compute_subnetwork block driven by for_each.
#   [ ] Subnets are addressed by key: .this["app"], .this["data"], .this["gke"].
#   [ ] envs/dev and envs/prod call the SAME module with different CIDR maps.
#   [ ] Reordering the entries in the subnets map produces "No changes." on plan.
#   [ ] terraform validate passes in modules/vpc and both envs.
#   [ ] terraform fmt -check passes (no formatting diffs).
###############################################################################


###############################################################################
# STARTING POINT — the code you are refactoring AWAY from. DO NOT keep this.
# Three duplicated blocks. They can drift apart, are addressed positionally if
# you naively convert to count, and adding a fourth subnet means copy-paste.
###############################################################################
#
# resource "google_compute_network" "vpc" {
#   name                    = "ex02-vpc"
#   auto_create_subnetworks = false
#   project                 = var.project_id
# }
#
# resource "google_compute_subnetwork" "app" {
#   name                     = "app"
#   region                   = var.region
#   network                  = google_compute_network.vpc.id
#   ip_cidr_range            = "10.10.0.0/20"
#   private_ip_google_access = true
#   project                  = var.project_id
# }
#
# resource "google_compute_subnetwork" "data" {
#   name                     = "data"
#   region                   = var.region
#   network                  = google_compute_network.vpc.id
#   ip_cidr_range            = "10.10.16.0/20"
#   private_ip_google_access = true
#   project                  = var.project_id
# }
#
# resource "google_compute_subnetwork" "gke" {
#   name                     = "gke"
#   region                   = var.region
#   network                  = google_compute_network.vpc.id
#   ip_cidr_range            = "10.10.32.0/20"
#   private_ip_google_access = true
#   project                  = var.project_id
# }
#
###############################################################################


###############################################################################
# modules/vpc/versions.tf  —  GIVEN. Copy this verbatim. Note: NO backend block;
# modules never declare a backend. The root module (envs/*) owns the backend.
###############################################################################
#
# terraform {
#   required_version = ">= 1.9.0"
#   required_providers {
#     google = {
#       source  = "hashicorp/google"
#       version = "~> 6.0"
#     }
#   }
# }
#
###############################################################################


# =============================================================================
# YOUR TASK
#
#   1. Write modules/vpc/variables.tf with three inputs:
#        - project_id (string, validated as a plausible GCP project ID)
#        - region     (string, default "us-central1")
#        - subnets     (map(string): subnet name => CIDR; validated non-empty)
#
#   2. Write modules/vpc/main.tf with:
#        - one google_compute_network "vpc"
#        - ONE google_compute_subnetwork "this" driven by for_each = var.subnets,
#          using each.key for the name and each.value for the CIDR.
#
#   3. Write modules/vpc/outputs.tf exposing:
#        - network_id (the VPC self-link)
#        - subnet_ids (map of subnet name => self-link, built with a for expression)
#
#   4. Write envs/dev/main.tf and envs/prod/main.tf that each call the module
#      with a DIFFERENT subnets map (dev uses 10.10.x, prod uses 10.20.x).
#
#   Then run the commands at the top and verify a clean plan. Finally, REORDER
#   the entries in one env's subnets map and run `terraform plan` again — it must
#   print "No changes." That clean re-plan after a reorder is the whole point:
#   for_each addresses by key, so order is irrelevant.
# =============================================================================


###############################################################################
# HINTS — peek only if stuck.
###############################################################################
#
# HINT 1 — the for_each block:
#     resource "google_compute_subnetwork" "this" {
#       for_each                 = var.subnets
#       name                     = each.key
#       ip_cidr_range            = each.value
#       region                   = var.region
#       network                  = google_compute_network.vpc.id
#       project                  = var.project_id
#       private_ip_google_access = true
#     }
#
# HINT 2 — the subnet_ids output uses a `for` expression over the for_each map:
#     output "subnet_ids" {
#       value = { for name, s in google_compute_subnetwork.this : name => s.id }
#     }
#
# HINT 3 — variable validation for a non-empty map:
#     validation {
#       condition     = length(var.subnets) > 0
#       error_message = "Provide at least one subnet."
#     }


###############################################################################
# ============================  FULL SOLUTION  ============================== #
# Lay these out on disk exactly as the paths in the comments indicate.        #
# Everything below is correct, idiomatic, fmt-clean Terraform.                #
###############################################################################

# ---------------------------------------------------------------------------
# FILE: ex02/modules/vpc/versions.tf
# ---------------------------------------------------------------------------
#
#   terraform {
#     required_version = ">= 1.9.0"
#     required_providers {
#       google = {
#         source  = "hashicorp/google"
#         version = "~> 6.0"
#       }
#     }
#   }

# ---------------------------------------------------------------------------
# FILE: ex02/modules/vpc/variables.tf
# ---------------------------------------------------------------------------
#
#   variable "project_id" {
#     type        = string
#     description = "Project that owns the VPC and subnets."
#     validation {
#       condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
#       error_message = "project_id must be a valid GCP project ID."
#     }
#   }
#
#   variable "region" {
#     type        = string
#     description = "Region for all subnets in this module."
#     default     = "us-central1"
#   }
#
#   variable "subnets" {
#     type        = map(string)
#     description = "Map of subnet name => primary CIDR range."
#     validation {
#       condition     = length(var.subnets) > 0
#       error_message = "Provide at least one subnet; an empty VPC is rarely intended."
#     }
#   }

# ---------------------------------------------------------------------------
# FILE: ex02/modules/vpc/main.tf
# ---------------------------------------------------------------------------
#
#   resource "google_compute_network" "vpc" {
#     name                    = "ex02-vpc"
#     auto_create_subnetworks = false
#     project                 = var.project_id
#   }
#
#   resource "google_compute_subnetwork" "this" {
#     for_each                 = var.subnets
#     name                     = each.key
#     ip_cidr_range            = each.value
#     region                   = var.region
#     network                  = google_compute_network.vpc.id
#     project                  = var.project_id
#     private_ip_google_access = true
#   }

# ---------------------------------------------------------------------------
# FILE: ex02/modules/vpc/outputs.tf
# ---------------------------------------------------------------------------
#
#   output "network_id" {
#     description = "Self-link of the created VPC network."
#     value       = google_compute_network.vpc.id
#   }
#
#   output "subnet_ids" {
#     description = "Map of subnet name => self-link, for downstream modules."
#     value       = { for name, s in google_compute_subnetwork.this : name => s.id }
#   }

# ---------------------------------------------------------------------------
# FILE: ex02/envs/dev/main.tf
# ---------------------------------------------------------------------------
#
#   terraform {
#     required_version = ">= 1.9.0"
#     required_providers {
#       google = {
#         source  = "hashicorp/google"
#         version = "~> 6.0"
#       }
#     }
#     # In the real mini-project this is a backend "gcs" block. For the exercise,
#     # local state per-env is fine; the point here is the module + for_each.
#   }
#
#   provider "google" {
#     project = var.project_id
#     region  = "us-central1"
#   }
#
#   variable "project_id" {
#     type = string
#   }
#
#   module "vpc" {
#     source     = "../../modules/vpc"
#     project_id = var.project_id
#     region     = "us-central1"
#     subnets = {
#       app  = "10.10.0.0/20"
#       data = "10.10.16.0/20"
#       gke  = "10.10.32.0/20"
#     }
#   }
#
#   output "subnet_ids" {
#     value = module.vpc.subnet_ids
#   }

# ---------------------------------------------------------------------------
# FILE: ex02/envs/prod/main.tf  (SAME module, different CIDRs)
# ---------------------------------------------------------------------------
#
#   terraform {
#     required_version = ">= 1.9.0"
#     required_providers {
#       google = {
#         source  = "hashicorp/google"
#         version = "~> 6.0"
#       }
#     }
#   }
#
#   provider "google" {
#     project = var.project_id
#     region  = "us-central1"
#   }
#
#   variable "project_id" {
#     type = string
#   }
#
#   module "vpc" {
#     source     = "../../modules/vpc"
#     project_id = var.project_id
#     region     = "us-central1"
#     subnets = {
#       app  = "10.20.0.0/20"
#       data = "10.20.16.0/20"
#       gke  = "10.20.32.0/20"
#     }
#   }
#
#   output "subnet_ids" {
#     value = module.vpc.subnet_ids
#   }

###############################################################################
# EXPECTED OUTPUT
#
#   $ cd ex02/envs/dev && terraform apply -var="project_id=$TF_PROJECT"
#   ...
#   Apply complete! Resources: 4 added, 0 changed, 0 destroyed.
#   Outputs:
#   subnet_ids = {
#     "app"  = "https://www.googleapis.com/compute/v1/.../subnetworks/app"
#     "data" = "https://www.googleapis.com/compute/v1/.../subnetworks/data"
#     "gke"  = "https://www.googleapis.com/compute/v1/.../subnetworks/gke"
#   }
#
#   # THE PROOF: reorder the subnets map (put gke first), then:
#   $ terraform plan -var="project_id=$TF_PROJECT"
#   No changes. Your infrastructure matches the configuration.
#
#   Contrast: had you used count over a LIST and deleted the first element,
#   the plan would show "destroy [1], [2] and recreate at [0], [1]" — a
#   destroy-and-recreate of live subnets caused purely by reordering. for_each's
#   key-based addressing makes order irrelevant. That is why the rule is
#   "for_each by default, count only for zero-or-one."
#
# TEARDOWN
#   cd ex02/envs/prod && terraform destroy -var="project_id=$TF_PROJECT"
#   cd ../dev         && terraform destroy -var="project_id=$TF_PROJECT"
#
# REFLECTION (answer in a results-ex02.md next to your files)
#   1. Why does each.key produce a stable resource address while count's index
#      does not? What is the data type of for_each's argument (map vs set vs list)?
#   2. The module hard-codes auto_create_subnetworks = false and
#      private_ip_google_access = true. Why are those the MODULE's opinions
#      rather than inputs? What would have to be true for them to become inputs?
#   3. You used `toset(...)` nowhere here because var.subnets is already a map.
#      When WOULD you need toset()? (Hint: for_each over a list of strings.)
#   4. dev and prod differ only in their CIDR map. What ELSE would realistically
#      differ between dev and prod, and would those differences be module inputs
#      or would they live in the envs/ root modules?
###############################################################################
