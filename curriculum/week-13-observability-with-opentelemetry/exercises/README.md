# Week 13 — Exercises

Four exercises, each a skill drill, not capstone work. Do them in order: Exercise 1 instruments a Python service and gets data into Cloud Trace + Cloud Monitoring; Exercise 4 does the same for a Go service (the other half of the fleet's language stack); Exercise 2 defines the SLO and the burn-rate alert that watches it; Exercise 3 routes logs to BigQuery and queries them. Together they are the full observability loop for one service — which is exactly what the challenge and mini-project then make you do across the whole fleet. Exercise 4 sits alongside Exercise 1 by design: do whichever matches the language of the service you are instrumenting first, then the other for breadth (the syllabus skill is "Python *or* Go in under an hour").

Budget about **4.5 hours** of core time — Exercises 1, 2, and 3. Exercise 4 is the Go counterpart of Exercise 1 and shares Tuesday's "instrument Python + Go" block: do whichever language matches the service you instrument first as your core hour, and treat the other as a +60-minute breadth drill (the self-study time on Tuesday covers it). They all run inside the free trial; the only cost is a few cents of BigQuery storage in Exercise 3, reclaimed at teardown.

| # | File | What you do | Est. time |
|---|------|-------------|-----------|
| 1 | [exercise-01-instrument-a-python-service.md](./exercise-01-instrument-a-python-service.md) | Add OpenTelemetry tracing and metrics to a FastAPI service and export to Cloud Trace + Cloud Monitoring in under an hour. Guided, with starter + solution code and expected output. | 60 min |
| 4 | [exercise-04-instrument-a-go-service.md](./exercise-04-instrument-a-go-service.md) | The Go mirror of Exercise 1: add OpenTelemetry tracing and metrics to a `net/http` service with `otelhttp` and export to Cloud Trace + Cloud Monitoring in under an hour. Guided, with starter + solution code and expected output. | 60 min |
| 2 | [exercise-02-burn-rate-alert.tf](./exercise-02-burn-rate-alert.tf) | Runnable Terraform: define a 99.9% availability SLO for the service and a multi-window burn-rate alert that pages on a fast burn but not on noise. Fill in three TODOs, `terraform apply`, validate. | 50 min |
| 3 | [exercise-03-log-sink-to-bigquery.py](./exercise-03-log-sink-to-bigquery.py) | Runnable Python: create a Cloud Logging sink to BigQuery, emit a structured error pattern, and query the landed logs in SQL to find it. Fill in two TODOs. | 45 min |

## Conventions

- Set `GOOGLE_CLOUD_PROJECT` and run `gcloud auth application-default login` before any exercise so the exporters and clients authenticate.
- Pin the OTel versions from `resources.md` (`opentelemetry-sdk` 1.27+, exporters 1.27+). Mismatched versions are the #1 cause of "the import works but nothing exports."
- Each exercise has acceptance criteria. You are done when every box is checked, not when the code runs once.
- **Tear down at the end.** Exercise 2 leaves an alert policy and a notification channel; Exercise 3 leaves a sink and a BigQuery dataset. Both files document their teardown. The mini-project teardown gate assumes you already cleaned up the exercises.

## Solutions

Exercise 1 ships its solution inline (it is the guided one). Exercises 2 and 3 are runnable files with `TODO` markers and a fully-worked reference at the bottom of each file inside a clearly-marked block — fill in the TODOs yourself first, then compare. Do not read the reference block until you have a version that runs.
