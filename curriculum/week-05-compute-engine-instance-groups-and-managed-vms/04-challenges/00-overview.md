# Week 5 — Challenges

The exercises drilled the pieces — template, MIG, autoscaler, spot, graceful shutdown. **The challenge assembles them into a system and then attacks it.** It takes 2.5–4 hours and produces something you can show in the Phase 2 midterm architecture review.

## Index

1. **[Challenge 1 — Internal LB + MIG, zero-drop failover](./challenge-01-ilb-mig-zero-drop-failover.md)** — a regional MIG behind an internal passthrough Network Load Balancer running the Go service, autoscaling on **CPU plus a custom Cloud Monitoring metric**, validated by killing instances mid-traffic and rolling a new instance template — with **zero dropped requests** the whole time. (~3 hours)

Challenges are optional. If you skip them you can still pass the week. If you do this one, you arrive at the mini-project with the hard part already solved: the difference between a MIG that *heals* and a MIG that heals *without dropping traffic* is exactly the custom-metric autoscaling and the rolling-update tuning this challenge forces you to get right. The mini-project then layers the Terraform structure and the Week 04 wiring on top of a system you have already proven survives chaos.

No solution is provided — acceptance criteria only. That is the Crunch Labs challenge contract: you get the spec and the bar, not the answer.
