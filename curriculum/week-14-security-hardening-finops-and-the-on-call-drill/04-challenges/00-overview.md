# Week 14 — Challenges

One challenge this week, and it is the week in miniature: harden the perimeter, require Binary Authorization on the deploy path, then run a synthetic on-call drill and deliver a signed runbook plus a no-blame postmortem. No starter code, no solution — acceptance criteria only. This is the work that proves you can hold a production posture *and* survive the night, which is exactly what Week 15's architecture review will probe.

## Index

1. **[Challenge 1 — Harden the perimeter and run the drill](./challenge-01-harden-perimeter-and-run-the-drill.md)** — Apply the Org Policy bundle, wrap the production project in a VPC Service Controls perimeter *without breaking your own deploys*, require Binary Authorization on the GKE deploy path, then run a synthetic on-call drill and deliver a signed-off runbook plus a no-blame postmortem. (~3h)

## How to work the challenge

- There is no solution file. The acceptance criteria are the spec. If you can satisfy every box and defend each choice to a staff engineer, you are done.
- **Verify the deny.** Every hardening control must be shown rejecting the forbidden action — a 403 from the perimeter, a denied unsigned image, a denied public IP. A control you have not seen deny is not done.
- **The postmortem is the graded artifact.** It is worth 5% of the course on its own (see the syllabus assessment matrix). It is graded on timeline quality, contributing-factors depth, and owned/dated action items — not on mitigation speed.
- **Tear down.** The drill's failover step costs real money while it runs. The teardown gate is graded: scale the standby back to zero and confirm the spend stopped.
- Budget **\$3–6** of real spend for the failover step. Do it in one focused block.

This challenge feeds directly into the mini-project, which welds the same controls onto the full Week-01–13 system. Do the challenge first to build the muscles, then the mini-project to do it for real over the whole stack.
