# Week 11 — Challenges

One harder, open-ended challenge. No full solution is provided — only acceptance criteria. This is the canonical shape of a real migration, in microcosm, and it is the most production-realistic thing you will do this week.

## Index

1. **[Challenge 1 — Migrate Cloud SQL Postgres to single-region Spanner with Datastream + Dataflow, shadow-test it, and tear it down before bed](./challenge-01-datastream-spanner-migration.md)** — Stand up a Cloud SQL Postgres source with seeded data, capture changes with Datastream, land them in single-region Spanner via the Datastream→Spanner Dataflow template, run a 30-minute parallel read shadow-test that proves the two databases return the same answers, then tear the Spanner instance down before bed with billing alerts confirmed. (~2.5 hours, costs ~\$3–4 if torn down within the window)

## How to work the challenge

- This challenge **costs money** (Spanner + a Dataflow worker). Arm your \$10 budget alert first. Do it early in a day so the teardown deadline ("before bed") is real.
- There is no starter repo and no solution. You assemble the pieces from the lectures, Exercises 1 and 2, and the Datastream/Spanner docs.
- The shadow-test is the heart of it: a migration you cannot *prove* correct is a migration you have not done. The acceptance criteria are written so that a passing submission has evidence, not assertions.
- **The teardown gate is graded.** A Spanner instance still listed at the end is a failed challenge. The challenge explicitly ends with `gcloud spanner instances list` returning empty and a screenshot of the budget alert still armed.
