# Week 7 — Challenges

One challenge this week. It is harder than the exercises and open-ended: no step-by-step, only acceptance criteria. It composes everything from the week — Cloud Run v2, private Cloud SQL over PSC, Cloud Armor (a sneak peek at Week 08), and the cold-start / cost analysis from both lectures — into one measured deliverable.

| # | File | What you prove | Est. time |
|---|------|----------------|-----------|
| 1 | [challenge-01-coldstart-bakeoff-behind-cloud-armor.md](./challenge-01-coldstart-bakeoff-behind-cloud-armor.md) | Deploy a stateless Cloud Run service with a private Cloud SQL Postgres backend over PSC, put Cloud Armor in front, benchmark cold-start at `min-instances=0`, `=1`, and `=3`, and produce a monthly-cost comparison for each. | 3–4 h |

No solution is provided. The grader checks the acceptance criteria and re-runs your cost spreadsheet. Cloud SQL bills per hour — do the whole challenge in one sitting and tear it down when you finish.
