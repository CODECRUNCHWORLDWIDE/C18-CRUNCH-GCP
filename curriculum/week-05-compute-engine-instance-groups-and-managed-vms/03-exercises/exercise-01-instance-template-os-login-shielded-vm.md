# Exercise 1 — Hardened Instance Template + One Instance

**Goal:** Author a production-shaped `google_compute_instance_template` in Terraform with OS Login, Shielded VM (Secure Boot + vTPM + integrity monitoring), a dedicated least-privilege service account, no external IP, and a startup script that installs the Week 5 Go service as a `systemd` unit. Then launch exactly one instance from the template and prove every hardening control is on.

**Estimated time:** 75 minutes.

You stop launching instances by hand here. From now on the *template* is the artifact you reason about; instances are disposable copies of it.

---

## Setup

You need, from earlier weeks:

- The Week 04 module library with **remote state in GCS** and a deployed **VPC** (one region, one subnet, Cloud NAT, Private Google Access). Note the GCS bucket and prefix where the Week 04 state lives.
- `gcloud` pointed at your dev project: `gcloud config configurations activate c18-dev`.
- Terraform `>= 1.9` (or OpenTofu `>= 1.7`) and Go `1.23+`.

Make a working directory for this exercise inside your repo, e.g. `envs/dev/exercise-01/`. Everything below goes there.

---

## Step 1 — Read the Week 04 VPC from remote state

You will *not* hard-code the network or subnet. You read them from the Week 04 state. Create `data.tf`:

```hcl
data "terraform_remote_state" "vpc" {
  backend = "gcs"
  config = {
    bucket = "YOUR_TF_STATE_BUCKET"   # the Week 04 state bucket
    prefix = "envs/dev/vpc"           # the Week 04 VPC state prefix
  }
}

# Convenience locals. Adjust the output names to match what your Week 04
# vpc module actually exported (network_self_link / subnet_self_link are the
# conventional names from the Week 04 mini-project).
locals {
  network_self_link = data.terraform_remote_state.vpc.outputs.network_self_link
  subnet_self_link  = data.terraform_remote_state.vpc.outputs.subnet_self_link
  region            = data.terraform_remote_state.vpc.outputs.region
}
```

If your Week 04 module named its outputs differently, fix the references — do not paper over it with a hard-coded string. The point of the module library is that these wire together.

---

## Step 2 — Providers and variables

`versions.tf`:

```hcl
terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  backend "gcs" {
    bucket = "YOUR_TF_STATE_BUCKET"
    prefix = "envs/dev/exercise-01"
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
  description = "The dev project ID."
}

variable "region" {
  type        = string
  description = "Region for the instance template and instance."
  default     = "us-central1"
}

variable "zone" {
  type        = string
  description = "Zone to launch the single test instance in."
  default     = "us-central1-b"
}
```

---

## Step 3 — A dedicated, least-privilege service account

Never run an instance as the default Compute Engine service account — it is over-privileged by default. Create a purpose-built one with only what the service needs (here: write logs and metrics, read its config from a bucket). `service-account.tf`:

```hcl
resource "google_service_account" "workload" {
  account_id   = "week5-workload"
  display_name = "Week 5 MIG workload SA"
  project      = var.project_id
}

# Logging + monitoring so the instance can emit logs/metrics via the Ops Agent.
resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.workload.email}"
}

resource "google_project_iam_member" "metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.workload.email}"
}
```

---

## Step 4 — The startup script

The startup script installs Go, fetches the service source from instance metadata, builds it, and registers it as a `systemd` unit so the init system restarts it if it crashes. Save it as `startup.sh` in the same directory:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Pull the Go source out of instance metadata (set by the template below).
SRC_DIR=/opt/workserver
mkdir -p "${SRC_DIR}"
curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/main-go" \
  > "${SRC_DIR}/main.go"

# Install Go (Debian 12 repo Go is fine for this simple binary).
apt-get update -y
apt-get install -y golang-go

# Build the binary.
cd "${SRC_DIR}"
GOFLAGS=-mod=mod go build -o /usr/local/bin/workserver main.go

# Install a systemd unit so the service is supervised and restarts on failure.
cat >/etc/systemd/system/workserver.service <<'UNIT'
[Unit]
Description=Crunch GCP Week 5 work server
After=network-online.target
Wants=network-online.target

[Service]
Environment=PORT=8080
ExecStart=/usr/local/bin/workserver
Restart=always
RestartSec=2
# Run as an unprivileged user, not root.
DynamicUser=yes
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now workserver.service
```

Save the Go service from Lecture 2 (`main.go`) next to it — you will embed it into metadata so every instance the template stamps builds the same binary. (In the mini-project you graduate to a pre-built binary in GCS so you are not compiling on every boot; for this exercise, build-on-boot keeps the moving parts visible.)

---

## Step 5 — The instance template (the heart of the exercise)

`instance-template.tf`:

```hcl
resource "google_compute_instance_template" "workserver" {
  name_prefix  = "week5-workserver-"
  project      = var.project_id
  region       = var.region
  machine_type = "e2-medium"

  # Immutability discipline: a template is never edited in place. When the
  # startup script or machine type changes, Terraform creates a NEW template
  # (name_prefix + create_before_destroy) and the MIG rolls onto it.
  lifecycle {
    create_before_destroy = true
  }

  disk {
    source_image = "debian-cloud/debian-12"
    auto_delete  = true
    boot         = true
    disk_size_gb = 20
    disk_type    = "pd-balanced"
  }

  network_interface {
    network    = local.network_self_link
    subnetwork = local.subnet_self_link
    # No access_config block => NO external IP. Egress is via Cloud NAT.
  }

  # Shielded VM: all three controls on. This is the production default.
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  # OS Login: SSH governed by IAM, not metadata keys.
  metadata = {
    enable-oslogin = "TRUE"
    startup-script = file("${path.module}/startup.sh")
    main-go        = file("${path.module}/main.go")
  }

  service_account {
    email  = google_service_account.workload.email
    scopes = ["cloud-platform"] # scope is broad; IAM roles on the SA are narrow
  }

  # Block project-wide SSH keys; OS Login is the only way in.
  # (enable-oslogin above already does this, but be explicit.)
  tags = ["week5-workserver"]
}
```

Two things worth pausing on:

- **`create_before_destroy = true` + `name_prefix`** is the immutability pattern. You never mutate a template; a change produces a new one and the old is destroyed only after the new exists. This is what makes zero-downtime rolling updates possible later.
- **`scopes = ["cloud-platform"]`** with a *narrow SA*. The old advice was to scope-limit the access token; the modern advice is to give the broad `cloud-platform` scope and rely on the **IAM roles bound to the service account** (Step 3) to constrain what it can actually do. The SA can only write logs and metrics, so the broad scope is harmless.

---

## Step 6 — One instance from the template, and the health-check firewall

`instance.tf`:

```hcl
resource "google_compute_instance_from_template" "test" {
  name                     = "week5-from-template"
  project                  = var.project_id
  zone                     = var.zone
  source_instance_template = google_compute_instance_template.workserver.id
}

# Allow IAP TCP forwarding (SSH over IAP) to the instance.
resource "google_compute_firewall" "allow_iap_ssh" {
  name    = "week5-allow-iap-ssh"
  project = var.project_id
  network = local.network_self_link

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  # IAP's source range. Without this you cannot SSH over IAP.
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["week5-workserver"]
}

# Allow the load-balancer / health-check probers to reach :8080.
# You will need this in Exercise 2; add it now so it is in muscle memory.
resource "google_compute_firewall" "allow_health_check" {
  name    = "week5-allow-health-check"
  project = var.project_id
  network = local.network_self_link

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
  # The two Google health-check / LB source ranges. Forgetting these is the
  # #1 reason backends never go healthy.
  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]
  target_tags   = ["week5-workserver"]
}
```

`outputs.tf`:

```hcl
output "instance_internal_ip" {
  value = google_compute_instance_from_template.test.network_interface[0].network_ip
}

output "template_self_link" {
  value = google_compute_instance_template.workserver.self_link
}
```

---

## Step 7 — Apply and prove the hardening

```bash
terraform init
terraform plan -var="project_id=$(gcloud config get-value project)"
terraform apply -var="project_id=$(gcloud config get-value project)" -auto-approve
```

Wait ~90 seconds for the startup script to install Go, build, and start the unit. Now prove each control.

**Prove OS Login + IAP (no metadata keys, no public IP):**

```bash
gcloud compute ssh week5-from-template \
  --zone=us-central1-b --tunnel-through-iap
```

You got in via IAM, over IAP, with no external IP and no metadata SSH key. Inside the box:

**Prove Shielded VM:**

```bash
# Secure Boot, vTPM, integrity monitoring should all be active.
mokutil --sb-state 2>/dev/null || echo "SecureBoot via UEFI"
ls /dev/tpm0   # vTPM device present
```

From your laptop, confirm via the API:

```bash
gcloud compute instances describe week5-from-template \
  --zone=us-central1-b \
  --format="yaml(shieldedInstanceConfig)"
```

Expect all three `true`.

**Prove the service is up under systemd:**

```bash
# Inside the instance (over IAP):
systemctl status workserver.service     # active (running)
curl -s localhost:8080/healthz           # ok
curl -s localhost:8080/work | head -c 16 # a hex digest
journalctl -u workserver.service --no-pager | tail
```

**Prove no external IP:**

```bash
gcloud compute instances describe week5-from-template \
  --zone=us-central1-b \
  --format="value(networkInterfaces[0].accessConfigs)"
# Expect EMPTY output — no accessConfigs means no external IP.
```

---

## Expected output

`terraform apply` ends with:

```
Apply complete! Resources: 7 added, 0 changed, 0 destroyed.

Outputs:

instance_internal_ip = "10.10.0.7"
template_self_link    = "https://www.googleapis.com/compute/v1/projects/.../instanceTemplates/week5-workserver-..."
```

The hardening proofs:

```
shieldedInstanceConfig:
  enableIntegrityMonitoring: true
  enableSecureBoot: true
  enableVtpm: true
```

```
● workserver.service - Crunch GCP Week 5 work server
     Loaded: loaded (/etc/systemd/system/workserver.service; enabled; ...)
     Active: active (running) since ...
```

```
ok
```

---

## Acceptance criteria

- [ ] `terraform apply` is clean; the template and one instance exist.
- [ ] The instance has **no external IP** (empty `accessConfigs`).
- [ ] You SSH'd in **over IAP using OS Login** — no metadata SSH key was added.
- [ ] `shieldedInstanceConfig` shows all three controls `true`.
- [ ] The instance runs as a **dedicated SA** with only `logging.logWriter` + `monitoring.metricWriter`, not the default Compute SA.
- [ ] `curl localhost:8080/healthz` returns `ok` and the service runs under `systemd` with `Restart=always`.
- [ ] The template uses `name_prefix` + `create_before_destroy` (immutability pattern).
- [ ] Teardown is clean (see below); `gcloud compute instances list` shows `Listed 0 items.`

---

## Teardown

```bash
terraform destroy -var="project_id=$(gcloud config get-value project)" -auto-approve
gcloud compute instances list   # expect: Listed 0 items.
gcloud compute disks list        # expect: no orphaned data disks
```

---

## Stretch

- Replace build-on-boot with **fetch-a-prebuilt-binary-from-GCS**: build the Go binary locally, `gsutil cp` it to a bucket, and change the startup script to `gsutil cp gs://.../workserver /usr/local/bin/` (the SA already needs `roles/storage.objectViewer` on that bucket). Faster boots, no compiler on the box. This is what the mini-project does.
- Add the **Ops Agent** install to the startup script and confirm CPU/memory metrics appear in Cloud Monitoring under the instance.
- Flip the template's `machine_type` to `t2d-standard-2`, re-apply, and watch `create_before_destroy` make a new template version. Note that the *standalone instance* does not auto-roll — only a MIG does. That distinction is the whole reason Exercise 2 exists.

---

## Hints

<details>
<summary>"Permission denied" on SSH over IAP</summary>

You need both `roles/iap.tunnelResourceAccessor` (to use the IAP tunnel) and `roles/compute.osLogin` or `roles/compute.osAdminLogin` (OS Login) on your user. Grant them on the project, then retry. The `week5-allow-iap-ssh` firewall rule with source `35.235.240.0/20` must also exist.

</details>

<details>
<summary>The service never comes up</summary>

SSH in over IAP and read the boot log: `sudo journalctl -u google-startup-scripts.service --no-pager` shows the startup-script output, and `sudo journalctl -u workserver.service` shows the service. The usual culprit is the `main-go` metadata not being fetched — confirm the `curl` to the metadata server in `startup.sh` succeeded.

</details>

<details>
<summary>Plan wants to recreate the SA's IAM bindings every apply</summary>

Use `google_project_iam_member` (additive, manages one binding) — not `google_project_iam_binding` (authoritative, manages the whole role's member list and will fight other tooling). The exercise uses `_member` deliberately.

</details>

---

When this is comfortable, move to [Exercise 2 — Regional MIG with CPU autoscaling](./exercise-02-regional-mig-autoscaling.tf).
