# Week 7 — Resources

Every resource on this page is **free**. Google Cloud documentation is free without an account. The Terraform provider docs, the Cloud SQL Python connector repo, and the Eventarc samples are public. The pricing pages are the source of truth for the numbers in Lecture 1 and 2 — **always re-check them before you commit a cost to a review**, because prices drift and the lectures freeze them at a 2026 snapshot.

## Required reading (work it into your week)

- **Cloud Run — "About instance autoscaling"** (the single most important page for this week — concurrency, min/max instances, scale-to-zero):
  <https://cloud.google.com/run/docs/about-instance-autoscaling>
- **Cloud Run — "Container runtime contract"** (`$PORT`, statelessness, the execution environments):
  <https://cloud.google.com/run/docs/container-contract>
- **Cloud Run — "Set concurrency"**:
  <https://cloud.google.com/run/docs/configuring/concurrency>
- **Cloud Run — CPU allocation (always-allocated vs. request-time)**:
  <https://cloud.google.com/run/docs/configuring/cpu-allocation>
- **Cloud Run — "Configure minimum instances"** (the cold-start floor):
  <https://cloud.google.com/run/docs/configuring/min-instances>
- **Cloud Run — "Tips for general development"** (cold starts, lazy init, the practical performance advice):
  <https://cloud.google.com/run/docs/tips/general>
- **Cloud Run pricing** (the four billing components, the active vs. idle rates):
  <https://cloud.google.com/run/pricing>
- **Cloud SQL — "Connect from Cloud Run"**:
  <https://cloud.google.com/sql/docs/postgres/connect-run>
- **Cloud SQL — "Configure Private Service Connect"** (the no-public-IP private path):
  <https://cloud.google.com/sql/docs/postgres/configure-private-service-connect>
- **Cloud SQL — "IAM database authentication"** (no static password):
  <https://cloud.google.com/sql/docs/postgres/iam-authentication>
- **Cloud Run — "Connect to a VPC network" / Direct VPC egress**:
  <https://cloud.google.com/run/docs/configuring/vpc-direct-vpc>
- **Eventarc — "Create a trigger for Cloud Storage"**:
  <https://cloud.google.com/eventarc/docs/run/create-trigger-storage-gcloud>
- **Cloud Run jobs — "Create and execute jobs"**:
  <https://cloud.google.com/run/docs/create-jobs>

## The pricing pages (the source of truth for the cost lectures)

- **Cloud Run pricing**: <https://cloud.google.com/run/pricing>
- **GKE pricing** (control-plane fee, the free-tier nuance): <https://cloud.google.com/kubernetes-engine/pricing>
- **Compute Engine all-pricing** (spot vs. on-demand machine rates for the GKE side of the curve): <https://cloud.google.com/compute/all-pricing>
- **Cloud SQL pricing** (the per-hour cost that does *not* scale to zero): <https://cloud.google.com/sql/pricing>
- **GCP Pricing Calculator** (build your own model; the homework script reproduces it): <https://cloud.google.com/products/calculator>

## Terraform provider docs (you write all of this in HCL)

- **`google_cloud_run_v2_service`**: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_service>
- **`google_cloud_run_v2_job`**: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_job>
- **`google_sql_database_instance`** (the `psc_config` and `ip_configuration` blocks): <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_database_instance>
- **`google_sql_user`** (type `CLOUD_IAM_SERVICE_ACCOUNT`): <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_user>
- **`google_compute_forwarding_rule`** (the PSC endpoint): <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_forwarding_rule>
- **`google_eventarc_trigger`**: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/eventarc_trigger>
- **`google_cloudfunctions2_function`** (gen2 — to confirm it's Cloud Run underneath): <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloudfunctions2_function>

## The Cloud SQL connectors (how the private auth actually works)

- **`cloud-sql-python-connector`** (the library Exercise 2 uses; read the PSC + IAM-auth sections of the README): <https://github.com/GoogleCloudPlatform/cloud-sql-python-connector>
- **Cloud SQL Auth Proxy** (the older sidecar approach — read to understand what the connector replaces and why public-IP + proxy is the wrong posture): <https://cloud.google.com/sql/docs/postgres/sql-proxy>
- **`cloud-sql-go-connector`** (the Go equivalent, for the Go stretch goal): <https://github.com/GoogleCloudPlatform/cloud-sql-go-connector>

## Conceptual deep dives

- **Cloud Functions gen2 vs. gen1** (the page that confirms gen2 is Cloud Run + Buildpacks): <https://cloud.google.com/functions/docs/concepts/version-comparison>
- **Eventarc overview** (the CloudEvents model, the event sources, the transport): <https://cloud.google.com/eventarc/docs/overview>
- **Eventarc — event providers, types, and destinations**: <https://cloud.google.com/eventarc/docs/reference/supported-events>
- **Cloud Run — execution environments (gen1 vs gen2 sandbox)**: <https://cloud.google.com/run/docs/about-execution-environments>
- **Cloud Run — startup CPU boost** (cuts cold-start app-init time): <https://cloud.google.com/run/docs/configuring/services/cpu#startup-boost>
- **Private Service Connect overview** (the networking primitive under the database path; also the Week 08 subject): <https://cloud.google.com/vpc/docs/private-service-connect>

## Source / samples worth skimming

- **GoogleCloudPlatform/cloud-run-samples** (idiomatic service + job examples in several languages): <https://github.com/GoogleCloudPlatform/cloud-run-samples>
- **GoogleCloudPlatform/eventarc-samples** (the GCS-trigger and Pub/Sub-trigger examples this week mirrors): <https://github.com/GoogleCloudPlatform/eventarc-samples>
- **terraform-google-modules/terraform-google-cloud-run** (a reusable Cloud Run module you might fold into your Week 04 library): <https://github.com/GoogleCloudPlatform/terraform-google-cloud-run>
- **terraform-google-modules/terraform-google-sql-db** (the Cloud SQL module, including the PSC variant): <https://github.com/terraform-google-modules/terraform-google-sql-db>

## Talks worth watching (all free, no account)

- **"What's new with Cloud Run"** (Google Cloud Next, on YouTube) — the yearly state-of-Cloud-Run; watch the most recent one for the current concurrency/CPU/GPU story:
  search YouTube for "What's new with Cloud Run Google Cloud Next".
- **"Serverless vs Kubernetes: choosing the right compute"** (Google Cloud Tech, on YouTube) — the decision framework Lecture 1 formalizes:
  search YouTube for "Cloud Run vs GKE choosing compute".
- **"Cold starts and how to minimize them on Cloud Run"** (Google Cloud Tech, on YouTube) — the practical companion to Lecture 2:
  search YouTube for "Cloud Run cold starts minimize".
- **Ahmet Alp Balkan — Cloud Run / Knative talks and blog** (Ahmet was on the Cloud Run team and writes the clearest explanations of the internals):
  <https://ahmet.im/>

## How to use this resource list

The lectures cite specific URLs from this page at decision points. The links you should read end-to-end **this week** are:

1. **Cloud Run — "About instance autoscaling."** Foundational; do not skip. Every knob you tune is on this page.
2. **Cloud SQL — "Configure Private Service Connect."** Foundational for Exercise 2 and the mini-project; read it before you start the database work.
3. **Cloud Run — "Configure minimum instances"** + **"Tips for general development."** The two pages that make Lecture 2's break-even concrete.
4. **The pricing pages** (Cloud Run, GKE, Cloud SQL). You cannot do the cost model without current numbers; bookmark all three.

The rest are reference material — bookmark and return to them when a specific question arises. The Terraform provider docs in particular are pages you will have open the entire week.

---

*Bookmarks decay. If a Google Cloud doc URL rots, search the page title — Google reorganizes its docs tree often, but the titles are stable and the content reappears at a new path.*
