# Exercise 1 — Cloud SQL: HA + Read Replica + PSC, No Public IP

> **Estimated time:** ~75 minutes. **Cost:** ~\$1–2 if you tear it down within an hour. A regional HA `db-custom-2-7680` plus a cross-region replica is ~\$0.40–0.60/hour combined; do not leave it running overnight.

This is the production shape of Cloud SQL you must be able to build from memory by the end of the week: a Postgres primary with **regional high availability** (a synchronous standby in a second zone), a **cross-region read replica** (asynchronous, your DR-promotion target), and **Private Service Connect** so the instance has *no public IP* and is reachable only from inside your VPC. You will validate the no-public-IP claim by connecting from a GCE VM that itself has no external IP.

## Prerequisites

- A GCP project with billing enabled and a **\$10 budget alert armed**. (Do this first. This week bills you.)
- A VPC with at least one subnet in `us-central1`. If you still have the Week 03 shared VPC, use it; otherwise the starter below creates a minimal one.
- `terraform` (or `tofu`) ≥ 1.7, `gcloud`, and `psql` ≥ 15 on your PATH.
- The `google` provider `~> 6.0`.
- These APIs enabled: `sqladmin.googleapis.com`, `compute.googleapis.com`, `servicenetworking.googleapis.com`. Enable with:
  ```bash
  gcloud services enable sqladmin.googleapis.com compute.googleapis.com servicenetworking.googleapis.com
  ```

## Step 1 — Scaffold the Terraform

Create a directory `exercise-01/` with `versions.tf`, `variables.tf`, `network.tf`, `cloudsql.tf`, `psc.tf`, `vm.tf`, and `outputs.tf`. We build it file by file so each concept is isolated.

`versions.tf`:

```hcl
terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
```

`variables.tf`:

```hcl
variable "project_id" {
  type        = string
  description = "Your GCP project ID."
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "replica_region" {
  type    = string
  default = "us-east1"
}

variable "db_password" {
  type        = string
  description = "Initial postgres password. In production this comes from Secret Manager (Week 14)."
  sensitive   = true
}
```

## Step 2 — The network (skip if you have a Week 03 VPC)

`network.tf`:

```hcl
resource "google_compute_network" "vpc" {
  name                    = "wk11-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name                     = "wk11-subnet-central"
  ip_cidr_range            = "10.20.0.0/24"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  private_ip_google_access = true # so the VM can reach *.googleapis.com without a public IP
}

# Allow SSH via IAP and internal traffic within the subnet.
resource "google_compute_firewall" "allow_iap_ssh" {
  name      = "wk11-allow-iap-ssh"
  network   = google_compute_network.vpc.id
  direction = "INGRESS"
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  # IAP's TCP-forwarding range. SSH arrives via IAP, not a public IP.
  source_ranges = ["35.235.240.0/20"]
}

resource "google_compute_firewall" "allow_internal" {
  name      = "wk11-allow-internal"
  network   = google_compute_network.vpc.id
  direction = "INGRESS"
  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }
  source_ranges = ["10.20.0.0/24"]
}
```

## Step 3 — The Cloud SQL primary (HA) and the cross-region replica

`cloudsql.tf`:

```hcl
resource "google_sql_database_instance" "primary" {
  name             = "wk11-current-state-primary"
  region           = var.region
  database_version = "POSTGRES_16"

  settings {
    tier              = "db-custom-2-7680"
    availability_type = "REGIONAL" # HA: synchronous standby in a second zone
    disk_type         = "PD_SSD"
    disk_size         = 20
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7
    }

    ip_configuration {
      ipv4_enabled = false # NO PUBLIC IP
      psc_config {
        psc_enabled               = true
        allowed_consumer_projects = [var.project_id]
      }
    }

    maintenance_window {
      day          = 7
      hour         = 4
      update_track = "stable"
    }
  }

  # For a lab we turn deletion protection OFF so teardown is clean.
  # In production this is `true`.
  deletion_protection = false
}

resource "google_sql_database" "appdb" {
  name     = "current_state"
  instance = google_sql_database_instance.primary.name
}

resource "google_sql_user" "app" {
  name     = "appuser"
  instance = google_sql_database_instance.primary.name
  password = var.db_password
}

resource "google_sql_database_instance" "read_replica" {
  name                 = "wk11-current-state-replica-east"
  region               = var.replica_region
  database_version     = "POSTGRES_16"
  master_instance_name = google_sql_database_instance.primary.name

  replica_configuration {
    failover_target = false
  }

  settings {
    tier              = "db-custom-2-7680"
    availability_type = "ZONAL" # a replica is its own redundancy; no HA on it
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled = false
      psc_config {
        psc_enabled               = true
        allowed_consumer_projects = [var.project_id]
      }
    }
  }

  deletion_protection = false
}
```

## Step 4 — The PSC endpoint (the consumer side)

`psc.tf`:

```hcl
# Reserve an internal IP for the PSC endpoint in our subnet.
resource "google_compute_address" "psc_ip" {
  name         = "wk11-psc-ip"
  region       = var.region
  subnetwork   = google_compute_subnetwork.subnet.id
  address_type = "INTERNAL"
}

# The PSC endpoint: a forwarding rule that targets Cloud SQL's service attachment.
resource "google_compute_forwarding_rule" "psc_endpoint" {
  name                  = "wk11-psc-endpoint"
  region                = var.region
  network               = google_compute_network.vpc.id
  ip_address            = google_compute_address.psc_ip.id
  load_balancing_scheme = "" # empty = PSC endpoint, not a load balancer
  target                = google_sql_database_instance.primary.psc_service_attachment_link
}
```

## Step 5 — A private VM to test from (no external IP)

`vm.tf`:

```hcl
resource "google_compute_instance" "test_client" {
  name         = "wk11-test-client"
  machine_type = "e2-small"
  zone         = "${var.region}-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.subnet.id
    # NOTE: no access_config block => NO external IP. This is the point.
  }

  # Install psql on boot.
  metadata_startup_script = "apt-get update && apt-get install -y postgresql-client"

  # OS Login so we SSH via IAP with our gcloud identity.
  metadata = {
    enable-oslogin = "TRUE"
  }
}
```

`outputs.tf`:

```hcl
output "psc_endpoint_ip" {
  value       = google_compute_address.psc_ip.address
  description = "Connect to Cloud SQL at this internal IP, port 5432, from inside the VPC."
}

output "primary_connection_name" {
  value = google_sql_database_instance.primary.connection_name
}

output "test_vm" {
  value = google_compute_instance.test_client.name
}
```

## Step 6 — Apply

```bash
terraform -chdir=exercise-01 init
terraform -chdir=exercise-01 apply -var="project_id=$(gcloud config get-value project)" -var="db_password=$(openssl rand -base64 18)"
```

The primary takes ~8–12 minutes to create (HA instances are slower because two VMs come up). The replica adds a few minutes. The PSC endpoint and VM are quick. Total wall time: ~15 minutes. **Note the time** — you are billing now.

When it finishes, grab the endpoint IP:

```bash
PSC_IP=$(terraform -chdir=exercise-01 output -raw psc_endpoint_ip)
echo "Cloud SQL is reachable at $PSC_IP:5432 from inside the VPC only."
```

## Step 7 — Validate from the private VM (the no-public-IP proof)

SSH to the VM *via IAP* (because it has no external IP, you cannot SSH directly — IAP tunnels through Google's front end):

```bash
gcloud compute ssh wk11-test-client --zone=us-central1-a --tunnel-through-iap
```

On the VM, connect to Cloud SQL over the PSC internal IP:

```bash
# On the VM:
PGPASSWORD='<the password you generated>' psql \
  "host=<PSC_IP> port=5432 user=appuser dbname=current_state sslmode=require" \
  -c "SELECT version();"
```

Expected output (your Postgres patch version will differ):

```
                                                  version
------------------------------------------------------------------------------------------------------------
 PostgreSQL 16.x on x86_64-pc-linux-gnu, compiled by gcc ...
(1 row)
```

Now prove the *negative*: from your laptop (outside the VPC), try to reach the instance's public IP. There isn't one:

```bash
gcloud sql instances describe wk11-current-state-primary --format="value(ipAddresses)"
# You will see only a PRIVATE_SERVICE_CONNECT address (the service attachment),
# never a PRIMARY (public) address. No route from the internet exists.
```

## Step 8 — TEARDOWN (mandatory)

```bash
terraform -chdir=exercise-01 destroy -var="project_id=$(gcloud config get-value project)" -var="db_password=ignored-on-destroy"
```

Verify nothing survives:

```bash
gcloud sql instances list   # must not list wk11-* instances
gcloud compute instances list --filter="name~wk11"  # empty
```

If `gcloud sql instances list` still shows a `wk11-*` instance, the teardown failed — re-run `destroy` and investigate. **A surviving instance is a failed exercise.**

## Acceptance criteria

- [ ] `terraform apply` creates a Cloud SQL primary with `availability_type = "REGIONAL"` (verify in the console: "High availability" = Enabled).
- [ ] A cross-region read replica exists in `us-east1` referencing the primary.
- [ ] `ipv4_enabled = false` on both — `gcloud sql instances describe` shows no `PRIMARY` (public) IP address, only `PRIVATE_SERVICE_CONNECT`.
- [ ] You connected to the database **from the private VM** (no external IP) over the PSC endpoint and ran `SELECT version();`.
- [ ] `terraform destroy` succeeded and `gcloud sql instances list` shows no `wk11-*` instances.
- [ ] Your \$10 budget alert is still armed.

## Reflection questions (answer in `notes-ex01.md`)

1. You changed `availability_type` from `REGIONAL` to `ZONAL`. What capability did you lose, and what does the instance now cost (roughly) by comparison?
2. The read replica is `availability_type = "ZONAL"`. Why don't we pay for HA on the replica? What *is* the replica's role in the disaster-recovery story?
3. The PSC forwarding rule has `load_balancing_scheme = ""`. What would change if you set it to `"INTERNAL"` instead? (Hint: it would become an internal load balancer forwarding rule, not a PSC endpoint, and the `target` would be invalid.)
4. You connected with `sslmode=require`. What does Cloud SQL do if you connect with `sslmode=disable` over PSC? Should a production app ever use `disable`?

## Hints

1. **HA instances are slow to create** (~10 min) because two VMs and a regional disk come up. Don't assume `apply` hung; watch `gcloud sql operations list`.
2. **The PSC service attachment link** is exposed as `google_sql_database_instance.primary.psc_service_attachment_link` — that is the `target` of your forwarding rule. If Terraform says the attribute is empty, the instance hasn't finished provisioning PSC; wait for `apply` to fully complete.
3. **IAP SSH** requires the `roles/iap.tunnelResourceAccessor` role on your identity and the IAP firewall rule (in `network.tf`). If the SSH hangs, check both.
4. **If `psql` is not on the VM yet**, the startup script may still be running. Wait a minute, or `sudo apt-get install -y postgresql-client` manually.

---

**References**

- Cloud SQL — Configure Private Service Connect: <https://cloud.google.com/sql/docs/postgres/configure-private-service-connect>
- Cloud SQL — high availability: <https://cloud.google.com/sql/docs/postgres/high-availability>
- Cloud SQL — read replicas: <https://cloud.google.com/sql/docs/postgres/replication>
- Terraform `google_sql_database_instance`: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_database_instance>
- IAP TCP forwarding (for SSH to a no-external-IP VM): <https://cloud.google.com/iap/docs/using-tcp-forwarding>
