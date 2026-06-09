# Week 11 — Exercises

Three focused drills. The first two cost real money — do them early in a day, never late at night, and **tear down what you create**. Exercise 3 is free (it runs locally, no cloud resources). Do them in order; the mini-project assumes you have done all three.

## Index

1. **[Exercise 1 — Cloud SQL: HA + read replica + PSC, no public IP](exercise-01-cloud-sql-ha-replica-psc.md)** — Terraform a production-shaped Cloud SQL Postgres instance (regional HA, a cross-region read replica, Private Service Connect with `ipv4_enabled = false`). Validate connectivity from a private GCE VM that has no external IP. (~75 min, costs ~\$1–2 if torn down promptly)

2. **[Exercise 2 — Spanner: an interleaved schema, up and down within the hour](exercise-02-spanner-interleaved-schema.py)** — Stand up a 100-PU single-region Spanner instance from the Python client, create a `Customers` / `Orders` interleaved schema, write and read rows, then tear the whole thing down. The script has a built-in teardown guard and prints an elapsed-time warning. (~60 min, costs <\$2 if torn down within the hour)

3. **[Exercise 3 — The database decision, as a scoring engine](exercise-03-database-decision.py)** — Implement the seven-axis decision rubric from Lecture 1 as runnable Python, score three concrete workloads, and emit a written justification for each. No cloud resources; runs and tests locally. (~45 min, free)

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Arm a \$10 billing budget alert on your project before Exercise 1 or 2.** This is not optional this week. If you skipped Week 01's budget exercise, do it now: <https://cloud.google.com/billing/docs/how-to/budgets>.
- **Type the Terraform and Python yourself.** Do not copy-paste blindly — the muscle memory of `availability_type`, `psc_config`, and the Spanner DDL is the point.
- Run it. Read the output. Read the error if it failed.
- **End every cloud exercise with its teardown step and run the verification command.** A `gcloud spanner instances list` that returns a row at the end of Exercise 2 is a failed exercise, the same way a leftover `terraform` state is a failed Exercise 1.
- Exercise 3 must run clean with `python exercise-03-database-decision.py` printing the three justifications and `pytest` (if you add tests) passing.

## The teardown checklist for this week

Before you close your laptop on any day you touched the cloud:

```bash
gcloud spanner instances list          # must be EMPTY (or only instances you intend to keep)
gcloud sql instances list              # accounted for — STOPPED or DELETED per the exercise
terraform -chdir=exercise-01 destroy   # if you used Terraform for Cloud SQL
gcloud billing budgets list --billing-account=$BILLING_ACCOUNT_ID  # alert still armed
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c18-week-11` to compare.
