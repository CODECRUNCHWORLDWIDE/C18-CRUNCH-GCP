# Exercise 1 — A Global External HTTPS Load Balancer with a Cloud Run NEG and Cloud CDN

> **Estimated time:** ~90 minutes (15 of which is waiting for the managed cert to provision — start it, then read while it bakes).
> **You will build:** the four-link LB chain from Lecture 1 §1.5 — global forwarding rule → target HTTPS proxy → URL map → backend service → serverless NEG → a Cloud Run service — with a Google-managed certificate and Cloud CDN turned on. **Proof of done:** `curl https://<host>/` returns 200 over HTTPS; a cacheable path returns `Age:` > 0 on the second hit and `cacheHit: true` in the logs.

This is the load-balancer layer, end to end, in Terraform. We deploy a tiny Cloud Run service (a stand-in for the Week 07 service — the challenge uses the real one), wrap it in a serverless NEG, and assemble the global LB in front of it. By the end you have the artifact every other layer this week attaches to.

---

## 0. Smoke check

Confirm your tools before you start. All of these should print a version, not an error:

```bash
gcloud --version | head -1            # >= 470.0.0
terraform version | head -1           # >= 1.9  (or: tofu version, >= 1.8)
curl --version | head -1
dig -v 2>&1 | head -1                  # any
gcloud config get-value project       # your project, not "(unset)"
```

Enable the APIs this exercise touches (idempotent — safe to re-run):

```bash
gcloud services enable \
  compute.googleapis.com \
  run.googleapis.com \
  certificatemanager.googleapis.com
```

---

## 1. Deploy a tiny Cloud Run service (the origin)

We need *something* behind the LB. Deploy the smallest possible HTTP service. Create `app/main.py`:

```python
# app/main.py — a 30-line origin that proves caching and shows request headers.
import os
from fastapi import FastAPI, Response

app = FastAPI()


@app.get("/")
def root():
    # Dynamic: never cache. Cloud CDN must respect this.
    return Response(
        content='{"ok": true, "origin": "cloud-run"}',
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/static/version.json")
def static_version():
    # Cacheable: long TTL. This is the path we prove a CDN hit on.
    return Response(
        content='{"version": "1.0.0"}',
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )
```

`app/Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.* "uvicorn[standard]==0.32.*"
COPY main.py .
ENV PORT=8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
```

Build and deploy with the source-deploy shortcut (no Artifact Registry dance needed):

```bash
PROJECT=$(gcloud config get-value project)
gcloud run deploy edge-origin \
  --source ./app \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances 0 --max-instances 3 \
  --port 8080
```

Note the `*.run.app` URL it prints; confirm it works directly before you put an LB in front:

```bash
RUN_URL=$(gcloud run services describe edge-origin --region us-central1 --format='value(status.url)')
curl -s "$RUN_URL/" ; echo
curl -s "$RUN_URL/static/version.json" ; echo
```

You should see the two JSON bodies. Now we front it.

---

## 2. The starter Terraform (what you fill in)

Create `lb.tf`. The starter has the resources stubbed with `# TODO` markers; your job is to wire the four-link chain. (The full solution is in §5 — try it from the stubs first.)

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    google = { source = "hashicorp/google"; version = "~> 6.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = "us-central1"
}

variable "project_id" { type = string }

# Use sslip.io if you don't own a domain: the hostname is derived from the IP
# AFTER you reserve it (see §3). For a real domain, set this to your name.
variable "hostname" {
  type        = string
  default     = ""  # leave empty to use the <ip>.sslip.io path
  description = "FQDN for the managed cert. Empty => sslip.io fallback."
}

# 1) Reserve a GLOBAL anycast IP for the forwarding rule.
resource "google_compute_global_address" "edge" {
  name = "edge-ip"
  # (global addresses are EXTERNAL by default for LBs)
}

# 2) A serverless NEG pointing at the Cloud Run service.
resource "google_compute_region_network_endpoint_group" "run_neg" {
  # TODO: name, region, network_endpoint_type = "SERVERLESS",
  #       cloud_run { service = "edge-origin" }
}

# 3) The backend service that owns CDN + (later) the Armor policy.
resource "google_compute_backend_service" "run_backend" {
  # TODO: name, protocol = "HTTPS", load_balancing_scheme = "EXTERNAL_MANAGED",
  #       backend { group = <the NEG's id> }, enable_cdn = true,
  #       cdn_policy { cache_mode = "USE_ORIGIN_HEADERS" }
}

# 4) URL map: default to the Cloud Run backend.
resource "google_compute_url_map" "edge" {
  # TODO: name, default_service = <backend service id>
}

# 5) Managed cert (needs the hostname to resolve to the IP — see §3).
resource "google_compute_managed_ssl_certificate" "edge" {
  # TODO: name, managed { domains = [ local.fqdn ] }
}

# 6) Target HTTPS proxy: terminates TLS, points at the URL map + cert.
resource "google_compute_target_https_proxy" "edge" {
  # TODO: name, url_map = <url map id>, ssl_certificates = [ <cert id> ]
}

# 7) Global forwarding rule: anycast IP:443 -> the proxy.
resource "google_compute_global_forwarding_rule" "edge" {
  # TODO: name, target = <proxy id>, port_range = "443",
  #       ip_address = <reserved IP>, load_balancing_scheme = "EXTERNAL_MANAGED"
}

locals {
  # If you set var.hostname, use it. Otherwise derive <ip>.sslip.io.
  fqdn = var.hostname != "" ? var.hostname : "${replace(google_compute_global_address.edge.address, ".", "-")}.sslip.io"
}

output "lb_ip"   { value = google_compute_global_address.edge.address }
output "hostname"{ value = local.fqdn }
```

The trick that makes sslip.io work even though the cert needs the hostname: `sslip.io` resolves `<ip-with-dashes>.sslip.io` to `<ip>` *automatically*, so the moment you reserve the IP, the hostname already resolves — no DNS record to create. (For a real domain, you create an A record in §3.)

---

## 3. Apply in two passes (reserve IP → DNS → cert)

The managed cert will not go `ACTIVE` until its hostname resolves to the LB IP. So:

**Pass 1 — reserve the IP only**, so you can learn it:

```bash
terraform init
terraform apply -target=google_compute_global_address.edge \
  -var project_id=$(gcloud config get-value project)
terraform output lb_ip      # note this IP
```

**If you own a domain:** create an A record now: `your.host. 300 IN A <lb_ip>`, and run with `-var hostname=your.host`. **If you use sslip.io:** the hostname `<dashed-ip>.sslip.io` already resolves; leave `hostname` empty.

Confirm resolution before you wait on the cert:

```bash
HOST=$(terraform output -raw hostname 2>/dev/null || true)
dig +short "$HOST"          # must print the LB IP
```

**Pass 2 — apply everything:**

```bash
terraform apply -var project_id=$(gcloud config get-value project)
```

Now wait for the cert. This is the 15-minute coffee break:

```bash
watch -n 30 'gcloud compute ssl-certificates describe edge-cert \
  --global --format="value(managed.status, managed.domainStatus)"'
# Wait for ACTIVE. PROVISIONING is normal for 10-60 minutes.
```

While it bakes, read Lecture 2.

---

## 4. Prove it works

Once the cert is `ACTIVE`:

```bash
HOST=$(terraform output -raw hostname)

# 4a. HTTPS to the dynamic root: expect 200 and Cache-Control: no-store.
curl -si "https://$HOST/" | head -20
# Look for: HTTP/2 200, cache-control: no-store, and the JSON body.

# 4b. The cacheable path: hit it TWICE. The second hit should be a CDN hit.
curl -si "https://$HOST/static/version.json" | grep -iE 'age:|via:|cache-control'
sleep 2
curl -si "https://$HOST/static/version.json" | grep -iE 'age:|via:|cache-control'
# On the SECOND request you should see `age:` with a value > 0 and a `via:` header
# naming a Google cache. That is your edge cache serving without hitting Cloud Run.
```

Confirm the cache hit authoritatively in the logs (the headers can be cached-by-browser-proxy noise; the log field is the truth):

```bash
gcloud logging read \
  'resource.type="http_load_balancer" httpRequest.requestUrl:"version.json"' \
  --limit=5 \
  --format='value(timestamp, httpRequest.requestUrl, httpRequest.cacheHit)'
# At least one row should show cacheHit = True for /static/version.json.
```

**Proof of done:** the root returns 200 over HTTPS; `/static/version.json` shows `cacheHit: True` in the logs on a repeat request; the dynamic root never shows `cacheHit: True` (because `no-store`).

---

## 5. The solution (fill in the TODOs)

Here is the completed `lb.tf` body for the seven resources (drop these in place of the stubs):

```hcl
resource "google_compute_region_network_endpoint_group" "run_neg" {
  name                  = "edge-run-neg"
  region                = "us-central1"
  network_endpoint_type = "SERVERLESS"
  cloud_run { service = "edge-origin" }
}

resource "google_compute_backend_service" "run_backend" {
  name                  = "edge-run-backend"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend { group = google_compute_region_network_endpoint_group.run_neg.id }
  enable_cdn = true
  cdn_policy {
    cache_mode  = "USE_ORIGIN_HEADERS"   # honour our Cache-Control headers
    negative_caching = true
  }
}

resource "google_compute_url_map" "edge" {
  name            = "edge-url-map"
  default_service = google_compute_backend_service.run_backend.id
}

resource "google_compute_managed_ssl_certificate" "edge" {
  name = "edge-cert"
  managed { domains = [local.fqdn] }
}

resource "google_compute_target_https_proxy" "edge" {
  name             = "edge-proxy"
  url_map          = google_compute_url_map.edge.id
  ssl_certificates = [google_compute_managed_ssl_certificate.edge.id]
}

resource "google_compute_global_forwarding_rule" "edge" {
  name                  = "edge-fr"
  target                = google_compute_target_https_proxy.edge.id
  port_range            = "443"
  ip_address            = google_compute_global_address.edge.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
```

The two non-obvious bits:

- **`load_balancing_scheme = "EXTERNAL_MANAGED"`** on both the backend service and the forwarding rule. This selects the *global external Application LB* (the modern Envoy-based one). The older `EXTERNAL` scheme is the classic LB; we want the managed one because it is what supports the full Cloud Armor + CDN feature set you build on this week.
- **`cache_mode = "USE_ORIGIN_HEADERS"`** is the honest mode: the CDN caches exactly what your `Cache-Control` says. That is why `/` (with `no-store`) is never cached and `/static/version.json` (with `max-age=3600`) is. Had you used `FORCE_CACHE_ALL`, the dynamic root would have been cached too — a bug.

---

## 6. Teardown (the gate)

```bash
terraform destroy -var project_id=$(gcloud config get-value project)
gcloud run services delete edge-origin --region us-central1 --quiet
```

Confirm nothing is orphaned (a leftover forwarding rule or reserved IP bills you):

```bash
gcloud compute forwarding-rules list --global
gcloud compute addresses list --global
# Both should be empty (or contain only resources from other work).
```

---

## What you learned

- The four-link LB chain is not magic — it is seven Terraform resources wired in a fixed order, and the order is exactly the request path from Lecture 1.
- A serverless NEG is how Cloud Run attaches to a global LB; you will swap it for a zonal NEG (GKE) and a backend bucket (GCS) in the mini-project, and the chain above is unchanged — only the NEG changes.
- A managed cert needs DNS to resolve first; the two-pass apply (reserve IP → DNS → apply) is the standard ritual.
- Cloud CDN is one toggle (`enable_cdn`) plus a cache mode, and you *prove* it works with the `cacheHit` log field, not by squinting at headers.

In Exercise 2 you attach a Cloud Armor policy to `edge-run-backend` and watch it bite. **Leave Exercise 1 up if you are doing Exercise 2 next** (Exercise 2 references this backend service) — otherwise tear it down.
