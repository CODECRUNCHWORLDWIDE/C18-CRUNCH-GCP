# Week 10 — Challenges

One challenge this week. It is the synthesis of the exercises: land a public dataset right, prove you can answer real questions while scanning under 1% of the data, and then put a **dollar figure** on the pricing-model decision — on-demand vs. a 100-slot reservation for a one-hour batch window — and recommend the cheaper option with numbers a finance person would accept.

No solution is provided — acceptance criteria only. This is the "BigQuery query-plan debug + cost decision" drill that the syllabus models on a Google L4/L5 phone screen.

## Index

1. **[Challenge 1 — On-demand vs. a 100-slot reservation](./challenge-01-on-demand-vs-reservation.md)** — land NYC taxi (or Wikipedia pageviews), write five queries that each scan <1% of the data, then compute and defend whether a one-hour batch of that work is cheaper on on-demand or on a 100-slot Enterprise reservation. (~3 hours)

## How to approach it

- **Do the arithmetic, not the vibes.** The grader checks your numbers. "Reservations are cheaper for big workloads" is not an answer; "this batch scans 41 TiB = \$256 on-demand vs. 100 slots × 1h × \$0.06 = \$6 reserved, so reserve it, break-even is at X TiB" is.
- **Prove every scan claim with `--dry_run` and `total_bytes_billed`.** A claim of "<1%" without the bytes-billed evidence does not count.
- **You do not have to buy a reservation** to do the math — it is computed from published rates. If you choose to observe one, create it, run one query, and **delete it within the hour** (the reservation footgun from Lecture 2 §8).
- **Tear down.** The teardown gate is on the mini-project, but if you created a reservation here, delete it now.
