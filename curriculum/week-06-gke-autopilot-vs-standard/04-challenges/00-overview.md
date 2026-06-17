# Week 6 — Challenges

One stretch problem this week. It is the hands-on lab the syllabus names for Week 6, scoped as a challenge: deploy the same service two ways and produce the numbers that let you defend the choice. No solution is provided — only acceptance criteria. This is the kind of work that goes in your midterm architecture review (end of Week 8) and on your portfolio.

## Index

1. **[Challenge 1 — Autopilot vs. Standard-with-spot: cold-start, scale-out, and monthly cost](./challenge-01-autopilot-vs-standard-bakeoff.md)** — deploy the FastAPI service to (a) an Autopilot cluster and (b) a Standard cluster with a spot node pool. Wire Workload Identity, an HPA on a custom requests-per-second metric, and a PDB on both. Then measure cold-start latency, scale-out time, and projected monthly cost, and write the one-paragraph recommendation with a dollar number. (~4 hours)

## How to work the challenge

- There is no starter solution and no hint section. The acceptance criteria are the spec.
- You may reuse everything from the exercises: the FastAPI image, the manifests, the Workload Identity bind script, the surge node pool.
- The deliverable is a short writeup (`challenge-01-results.md`) with a table of measurements and a recommendation, plus the manifests and Terraform you used. The numbers must be *yours*, measured on *your* clusters — not copied from the lecture.
- The hard part is not the deploy; it is the **custom-metric HPA**. Scaling on requests-per-second requires the Custom Metrics Stackdriver Adapter and a metric your app (or a sidecar) exports to Cloud Monitoring. Budget most of your time there. The challenge file walks the wiring.
- Tear down both clusters when you finish. The challenge runs two clusters simultaneously; that is the most expensive hour of the week. Do not leave them up.
