###############################################################################
# Exercise 3 — Trigger a Cloud Run JOB from a GCS object-write via Eventarc
# =============================================================================
#
# Goal: When a file is finalized (written) into a GCS bucket, Eventarc delivers
#       the CloudEvent and runs a Cloud Run JOB that processes the object. No
#       polling loop, no cron, no glue server. This is the "GCS write -> batch
#       process" pattern the mini-project bolts onto the ingest service.
#
# Estimated time: 90 minutes.
#
# THE KEY INSIGHT:
#   Eventarc cannot start a Cloud Run *job* directly the way it can a *service*
#   (a job has no $PORT to receive an HTTP CloudEvent). The 2026-correct shape
#   is: GCS finalize -> Eventarc trigger -> a tiny Cloud Run SERVICE (the
#   "launcher") that receives the CloudEvent and calls the Cloud Run Admin API
#   to EXECUTE the job, passing the object name as an env override. This file
#   wires exactly that, with all the IAM. (Eventarc CAN target a service or a
#   gen2 function directly; the job needs the launcher hop.)
#
#   Path:  GCS object finalize
#            -> Eventarc trigger (transport: Pub/Sub, managed)
#              -> Cloud Run service "job-launcher" (receives CloudEvent)
#                -> runs Cloud Run job "processor" with OBJECT=<name> override
#
# IAM you must get right (the part everyone fumbles):
#   1. The GCS service AGENT needs roles/pubsub.publisher (Eventarc's GCS source
#      delivers via a Pub/Sub topic it publishes to).
#   2. The Eventarc TRIGGER service account needs roles/run.invoker on the
#      launcher service (so Eventarc may call it) and roles/eventarc.eventReceiver.
#   3. The LAUNCHER's service account needs roles/run.developer (or a tighter
#      custom role) to execute the job.
#
# Apply with:
#   terraform init
#   terraform apply -var="project_id=$(gcloud config get-value project)" \
#                   -var="region=us-central1" \
#                   -var="launcher_image=<built launcher image>" \
#                   -var="processor_image=<built processor image>"
#
# (The two images: see the "BUILD THE IMAGES" runbook block at the bottom.)
###############################################################################

variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "launcher_image" {
  type        = string
  description = "Image for the tiny CloudEvent->job-execute launcher service."
}
variable "processor_image" {
  type        = string
  description = "Image for the Cloud Run job that processes the object."
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "this" {}

# ---------------------------------------------------------------------------
# The bucket whose writes trigger the job. uniform_bucket_level_access + public
# access prevention because nothing here should ever be public.
# ---------------------------------------------------------------------------
resource "google_storage_bucket" "ingest" {
  name                        = "${var.project_id}-ingest-drop"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true # exercise convenience; lets destroy clean up objects
}

# ---------------------------------------------------------------------------
# The Cloud Run JOB that does the work. Run-to-completion; no $PORT. It reads
# the object name from the OBJECT env var (overridden per-execution by the
# launcher) and the bucket from BUCKET.
# ---------------------------------------------------------------------------
resource "google_service_account" "processor" {
  account_id   = "ingest-processor"
  display_name = "Eventarc-triggered processor job"
}

resource "google_cloud_run_v2_job" "processor" {
  name                = "ingest-processor"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.processor.email
      max_retries     = 1
      timeout         = "600s"
      containers {
        image = var.processor_image
        env {
          name  = "BUCKET"
          value = google_storage_bucket.ingest.name
        }
        # OBJECT is a placeholder; the launcher overrides it per execution.
        env {
          name  = "OBJECT"
          value = "UNSET"
        }
        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }
    }
  }
}

# The processor job needs to READ the object it is told to process.
resource "google_storage_bucket_iam_member" "processor_reads" {
  bucket = google_storage_bucket.ingest.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.processor.email}"
}

# ---------------------------------------------------------------------------
# The LAUNCHER service: receives the CloudEvent, extracts the object name, and
# executes the job with an OBJECT override. Runs as its own SA.
# ---------------------------------------------------------------------------
resource "google_service_account" "launcher" {
  account_id   = "ingest-launcher"
  display_name = "CloudEvent -> job execution launcher"
}

resource "google_cloud_run_v2_service" "launcher" {
  name                = "ingest-job-launcher"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY" # only Eventarc reaches it

  template {
    service_account                  = google_service_account.launcher.email
    max_instance_request_concurrency = 1 # one event -> one launch; keep it simple
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image = var.launcher_image
      ports { container_port = 8080 }
      env {
        name  = "JOB_NAME"
        value = google_cloud_run_v2_job.processor.name
      }
      env {
        name  = "JOB_REGION"
        value = var.region
      }
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
      }
    }
  }
}

# The launcher's SA may EXECUTE the processor job. run.developer is broad;
# in production use a custom role with run.jobs.run + run.executions.* only.
resource "google_project_iam_member" "launcher_runs_jobs" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.launcher.email}"
}
# The launcher SA must be able to act as the processor SA to launch the job.
resource "google_service_account_iam_member" "launcher_acts_as_processor" {
  service_account_id = google_service_account.processor.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.launcher.email}"
}

# ---------------------------------------------------------------------------
# IAM #1: the GCS service AGENT needs pubsub.publisher. Eventarc's GCS source
# routes events through a Pub/Sub topic that the GCS service agent publishes to.
# Without this, the trigger creates but never fires.
# ---------------------------------------------------------------------------
data "google_storage_project_service_account" "gcs" {}

resource "google_project_iam_member" "gcs_can_publish" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs.email_address}"
}

# ---------------------------------------------------------------------------
# IAM #2: the Eventarc TRIGGER service account. It needs eventReceiver and the
# right to invoke the launcher service.
# ---------------------------------------------------------------------------
resource "google_service_account" "trigger" {
  account_id   = "ingest-eventarc-trigger"
  display_name = "Eventarc trigger SA"
}

resource "google_project_iam_member" "trigger_event_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.trigger.email}"
}

resource "google_cloud_run_v2_service_iam_member" "trigger_invokes_launcher" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.launcher.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.trigger.email}"
}

# ---------------------------------------------------------------------------
# THE EVENTARC TRIGGER: GCS object finalize in our bucket -> launcher service.
# google.cloud.storage.object.v1.finalized is the "object written" event.
# ---------------------------------------------------------------------------
resource "google_eventarc_trigger" "gcs_to_launcher" {
  name            = "ingest-gcs-finalize"
  location        = var.region
  service_account = google_service_account.trigger.email

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }
  matching_criteria {
    attribute = "bucket"
    value     = google_storage_bucket.ingest.name
  }

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.launcher.name
      region  = var.region
      path    = "/" # the launcher receives the CloudEvent at POST /
    }
  }

  depends_on = [
    google_project_iam_member.gcs_can_publish,
    google_project_iam_member.trigger_event_receiver,
    google_cloud_run_v2_service_iam_member.trigger_invokes_launcher,
  ]
}

output "bucket" { value = google_storage_bucket.ingest.name }
output "job_name" { value = google_cloud_run_v2_job.processor.name }
output "trigger" { value = google_eventarc_trigger.gcs_to_launcher.name }

###############################################################################
# BUILD THE IMAGES (runbook — do this before `terraform apply`)
# =============================================================================
#
# --- LAUNCHER (app/launcher/main.py) — receives the CloudEvent, runs the job ---
#
#   import os
#   from fastapi import FastAPI, Request
#   from google.cloud import run_v2
#
#   app = FastAPI()
#   PROJECT = os.environ["PROJECT_ID"]
#   REGION = os.environ["JOB_REGION"]
#   JOB = os.environ["JOB_NAME"]
#   _client = run_v2.JobsClient()
#
#   @app.post("/")
#   async def on_event(request: Request):
#       # Eventarc delivers the GCS event; for storage.object.finalized the
#       # object name is in the CloudEvent "subject" header as
#       # "objects/<name>" and also in the JSON body.
#       body = await request.json()
#       object_name = body.get("name") or request.headers.get("ce-subject", "").removeprefix("objects/")
#       job_path = _client.job_path(PROJECT, REGION, JOB)
#       # Run the job with an OBJECT env override for this execution:
#       overrides = run_v2.RunJobRequest.Overrides(
#           container_overrides=[
#               run_v2.RunJobRequest.Overrides.ContainerOverride(
#                   env=[run_v2.EnvVar(name="OBJECT", value=object_name)]
#               )
#           ]
#       )
#       _client.run_job(request=run_v2.RunJobRequest(name=job_path, overrides=overrides))
#       return {"launched": JOB, "object": object_name}
#
#   requirements: fastapi, uvicorn[standard], google-cloud-run==0.10.* ,
#   Dockerfile: same slim multi-stage pattern as Exercise 1/2, CMD uvicorn.
#
# --- PROCESSOR (app/processor/main.py) — the job body, run-to-completion ---
#
#   import os
#   from google.cloud import storage
#
#   def main() -> None:
#       bucket = os.environ["BUCKET"]
#       obj = os.environ["OBJECT"]
#       client = storage.Client()
#       data = client.bucket(bucket).blob(obj).download_as_text()
#       lines = data.count("\n")
#       print(f"[processor] gs://{bucket}/{obj}: {len(data)} bytes, {lines} lines")
#       # Real systems would parse + persist here (e.g. write to the Cloud SQL
#       # instance from Exercise 2). For this exercise we just prove it ran.
#
#   if __name__ == "__main__":
#       main()
#
#   requirements: google-cloud-storage
#   Dockerfile (job — no uvicorn, runs to completion):
#     FROM python:3.12-slim
#     WORKDIR /app
#     COPY app/processor/ /app/
#     RUN pip install --no-cache-dir google-cloud-storage==2.18.2
#     CMD ["python", "main.py"]
#
###############################################################################
# VERIFY (after apply)
# =============================================================================
#
#   PROJECT_ID=$(gcloud config get-value project); REGION=us-central1
#   BUCKET=$(terraform output -raw bucket)
#
#   # Drop a file -> should trigger the job within ~seconds.
#   printf 'a\nb\nc\n' > /tmp/sample.txt
#   gcloud storage cp /tmp/sample.txt "gs://${BUCKET}/sample.txt"
#
#   # Watch the job executions appear:
#   gcloud run jobs executions list --job=ingest-processor --region="${REGION}"
#   # Then read the logs of the latest execution:
#   gcloud logging read \
#     'resource.type="cloud_run_job" AND resource.labels.job_name="ingest-processor"' \
#     --limit=20 --format='value(textPayload)'
#   # EXPECTED a line like:
#   #   [processor] gs://PROJECT_ID-ingest-drop/sample.txt: 6 bytes, 3 lines
#
###############################################################################
# ACCEPTANCE CRITERIA
# =============================================================================
#   [ ] terraform apply creates the bucket, job, launcher service, trigger, and
#       all four IAM grants (GCS->pubsub.publisher, trigger eventReceiver,
#       trigger run.invoker on launcher, launcher run.developer + actAs).
#   [ ] Uploading an object to the bucket causes a job execution within seconds.
#   [ ] The job execution log shows it read the object NAME it was triggered for.
#   [ ] The launcher service ingress is INTERNAL_ONLY (only Eventarc reaches it).
#   [ ] You can explain why the JOB needs the launcher hop (no $PORT for a job)
#       while a SERVICE could be an Eventarc destination directly.
#
###############################################################################
# TEARDOWN (do not skip)
# =============================================================================
#   terraform destroy -var="project_id=${PROJECT_ID}" -var="region=${REGION}" \
#       -var="launcher_image=<...>" -var="processor_image=<...>"
#   Confirm: eventarc triggers: 0 · cloud run services: 0 · jobs: 0 · buckets: 0
###############################################################################
