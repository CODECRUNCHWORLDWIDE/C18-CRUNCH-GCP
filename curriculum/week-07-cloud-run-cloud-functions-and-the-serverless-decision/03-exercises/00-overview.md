# Week 7 — Exercises

Three exercises, in order. Each is a skill drill, not capstone work — do them before you start the mini-project, because the mini-project assumes you can already do all three. Every exercise ends with a teardown step; run it. Cloud SQL bills per hour, so Exercise 2 and the challenge are the ones to be disciplined about.

| # | File | What you build | Est. time |
|---|------|----------------|-----------|
| 1 | [exercise-01-tune-concurrency-and-cpu.md](./exercise-01-tune-concurrency-and-cpu.md) | Deploy a stateless Cloud Run v2 service with a deliberately CPU-bound endpoint, then tune `concurrency` and CPU allocation to hit a target p99 — and read the cost consequence of the tuning. | ~90 min |
| 2 | [exercise-02-cloud-run-to-private-cloud-sql-over-psc.py](./exercise-02-cloud-run-to-private-cloud-sql-over-psc.py) | A FastAPI service that connects to a Cloud SQL Postgres instance with **no public IP**, over **Private Service Connect**, using the Cloud SQL Python connector with **IAM database authentication**. The app is runnable; the full setup is a runbook in the file. | ~120 min |
| 3 | [exercise-03-eventarc-gcs-to-cloud-run-job.tf](./exercise-03-eventarc-gcs-to-cloud-run-job.tf) | Terraform that wires a **GCS object-finalize** event through **Eventarc** to a **Cloud Run job**, including every IAM grant the trigger needs and the job code that reads the object name from the event. | ~90 min |

## Before you start

Run this smoke check. If any line fails, fix it before the exercises — they all assume these tools and versions.

```bash
gcloud version            # gcloud >= 470.0.0
gcloud config get-value project
terraform version         # >= 1.9   (or: tofu version >= 1.8)
docker version            # or: podman version
psql --version            # >= 15
hey -h 2>/dev/null && echo "hey: ok"   # or: oha --version

# Enable the APIs the week needs (idempotent):
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  eventarc.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  servicenetworking.googleapis.com \
  compute.googleapis.com \
  pubsub.googleapis.com
```

## How these compound

- **Exercise 1** teaches the concurrency/CPU knobs that the Lecture 1 cost curve depends on. You cannot model cost without understanding concurrency.
- **Exercise 2** is the private-database pattern that is the spine of the mini-project, reused in Week 11 and the capstone. Get the PSC + IAM-auth wiring right here so the mini-project is assembly, not discovery.
- **Exercise 3** is the Eventarc-triggered job that the mini-project bolts onto the service. The IAM in this exercise is the IAM the mini-project needs.

Do them in order. The mini-project is the three exercises composed into one deployable system.
