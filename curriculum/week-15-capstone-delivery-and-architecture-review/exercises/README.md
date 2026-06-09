# Week 15 — Exercises

Three exercises, in the order you do them. They are the proof-of-readiness steps that gate the capstone delivery: you cannot defend a system you have not load-tested, you cannot write a credible postmortem for a drill you have not run, and you cannot clear the readiness gate without sitting the exam. Do them against your *live* capstone system (or a scaled-down version of it), not against a slide.

| # | File | What you do | Est. time |
|---|------|-------------|-----------|
| 1 | [exercise-01-load-test-100rps-p99.md](./exercise-01-load-test-100rps-p99.md) | Run the system at 100 RPS sustained for 30 minutes and verify p99 < 500ms end-to-end, read off Cloud Monitoring. | ~90 min |
| 2 | [exercise-02-chaos-drill.py](./exercise-02-chaos-drill.py) | Drive one chaos drill (region failover, cert rotation, or Pub/Sub 10x), capture the timeline, and emit a postmortem skeleton. | ~120 min |
| 3 | [exercise-03-pca-readiness-gate.py](./exercise-03-pca-readiness-gate.py) | Sit the PCA / Cloud DevOps practice exam and clear the >=70% readiness gate; the script scores you and names your weakest domains. | ~120 min |

## Rules

- **Exercises 2 and 3 are runnable Python.** They are real programs — `python3 exercise-02-chaos-drill.py --help` works. Exercise 2 talks to GCP via the client libraries (`google-cloud-pubsub`, `google-cloud-monitoring`, `requests`); Exercise 3 is self-contained (the question bank is embedded) and needs no GCP access.
- **Exercise 1 is a guided Markdown walkthrough** with starter and solution commands, because the work is operational (running `hey`, reading a dashboard) rather than a single program.
- Install once: `pip install google-cloud-monitoring google-cloud-pubsub requests`, and `brew install hey` (or `go install github.com/rakyll/hey@latest`).
- Authenticate with `gcloud auth application-default login` so the client libraries pick up your credentials.
- Set `export GCP_PROJECT=your-project-id` (and `GCP_PROJECT_STANDBY` for the failover drill) before running.

## The bar

You have cleared the exercises when:

- Exercise 1 produces a p99 number under 500ms, read from `loadbalancing.googleapis.com/https/total_latencies`, over a 30-minute 100-RPS window, with the chart screenshot saved.
- Exercise 2 prints a clean drill timeline (start, fault injected, SLO impact, recovery, recovery time) and writes a `POSTMORTEM.md` skeleton you fill in.
- Exercise 3 prints `READINESS GATE: PASS` with a score >= 70% and a per-domain breakdown.

Solutions for Exercise 1 are inline (it is operational). Exercises 2 and 3 are complete, correct programs — read them, run them, then adapt Exercise 2 to your own system's resource names.
