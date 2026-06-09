# Week 10 — Exercises

Three focused drills, one per skill the week is graded on: **land + confirm**, **rewrite to scan less**, and **read the plan**. The first uses `bq` and `INFORMATION_SCHEMA`; the second is SQL you run and measure; the third is Python against the BigQuery API. All three fit inside the BigQuery free analysis tier (first 1 TiB/month free) *if you partition and filter as instructed* — which is the whole point.

## Index

1. **[Exercise 1 — Land a public dataset into a partitioned-and-clustered table, confirm with `INFORMATION_SCHEMA`](exercise-01-land-and-confirm-with-information-schema.md)** — load a slice of NYC taxi (or Wikipedia pageviews) into your own partitioned-clustered table, set `require_partition_filter`, and prove the schema/partitioning/clustering took with `INFORMATION_SCHEMA.COLUMNS`, `.PARTITIONS`, and `.TABLE_STORAGE`. (~60 min)
2. **[Exercise 2 — Rewrite a full-scan query into five queries that each scan <1%](exercise-02-rewrite-full-scan-into-five-queries.sql)** — take one fat full-scan query and replace it with five targeted queries, each touching under 1% of the data, and prove every one with `--dry_run` and `total_bytes_billed`. (~75 min)
3. **[Exercise 3 — Read a query plan and identify the cost-driving stage](exercise-03-read-the-query-plan.py)** — run a query from Python, pull `QueryJob.query_plan`, and programmatically point at the stage that drove the bytes scanned (the scan) and any stage where output ≫ input (a fan-out). (~45 min)

## How to work the exercises

- **Dry-run first, always.** Before you run any query against a real table this week, `bq query --dry_run` it and read the bytes. This is the reflex the whole week installs. If you cannot show the `--dry_run` byte estimate, you are not done.
- **Show the marker.** Every query against a multi-GB table should be able to produce the line:
  ```
  dry_run: 124.3 MiB would be billed · partition pruned: 364/365 days · cluster pruned: yes
  ```
- **Arm a budget first.** This is the one week where an un-budgeted project can cost real money. Set a \$10 budget on the lab project before you start (Week 01 reflex).
- **Type the queries yourself.** Do not paste blindly. The point is that `SELECT title, wiki, views ... WHERE datehour >= ...` becomes as automatic as the `SELECT *` it replaces.
- If you get stuck for more than 10 minutes, peek at the hints at the bottom of each file.

## A note on cost

Everything here fits inside the free tier:

- **The first 1 TiB of query analysis per month is free.** The exercises scan well under that *because* you partition and filter. If you find yourself about to scan more than a few GB, stop — you wrote the query wrong, and that is the lesson.
- **Public datasets cost nothing to store.** You pay only for the bytes you scan, which you minimize.
- **Loading a slice into your own table** uses a tiny bit of storage (free under 10 GiB) and a load job (free).
- Set `--maximum_bytes_billed` on your `bq query` calls as a seatbelt: `bq query --maximum_bytes_billed=2147483648 ...` refuses anything over 2 GiB.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c18-week-10` to compare approaches.
