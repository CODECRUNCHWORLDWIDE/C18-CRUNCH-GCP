# Week 10 — BigQuery Deep

Welcome to **Week 10 of C18 · Crunch GCP**, and to the one week where the failure mode is not an outage — it is an invoice. BigQuery is the best columnar analytics engine any cloud sells, and it will hand you a query plan that scans 4 TB and bills you for it without so much as a confirmation dialog. By Friday you should be able to land a public dataset into a partitioned-and-clustered table, read a query plan and point at the stage that costs the money, rewrite a full-scan query into five queries that each touch under 1% of the data, and tell — with numbers — whether a workload belongs on on-demand pricing or a slot reservation.

This is Phase 3, Data & AI. Week 09 built the streaming pipeline: a synthetic event generator → Pub/Sub → Dataflow (Python Apache Beam) → BigQuery, with a dead-letter topic. That pipeline writes to BigQuery, but Week 09 did not care *how* the destination table was shaped. This week we care intensely. The mini-project extends Week 09's pipeline output — it does not start fresh. You take the table Week 09 lands events into and turn it into a partitioned-clustered table with a materialized view and a BigQuery ML model that predicts on the data. If you skipped Week 09 or deleted the pipeline, you re-stand-it-up first; the teardown gate at the end of Week 09 told you to keep the Terraform.

The first thing to internalize is that **BigQuery's pricing model is the failure mode**. On-demand BigQuery bills on *bytes scanned*, not rows returned, not wall-clock, not result size. A `SELECT COUNT(*)` over a 10 TB table that you wrote because you "just wanted to check the row count" can scan the whole table and cost you on the order of \$50 in one keystroke — and `SELECT *` with a `LIMIT 10` on the same table scans *every column of every row* before the limit applies, because the limit is a display cap, not a scan cap. The three queries that cost \$2000 by accident are all variations on this theme, and we dissect each one in Lecture 1.

The second thing to internalize is that **you fix the cost by scanning less, and you prove it with `bytes-billed`**. Partitioning prunes whole date ranges before the scan. Clustering prunes blocks within a partition. A materialized view pre-aggregates so the expensive scan happens once, on write, not once per read. The "scan less" discipline is not a tip — it is the entire job. We make `--dry_run` and `INFORMATION_SCHEMA.JOBS` your reflexes the way `terraform plan` became your reflex in Week 04.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** BigQuery's columnar storage model — Capacitor encoding, the Colossus/Dremel split, and why "bytes scanned" is the unit that bills, not rows or wall-clock.
- **Diagnose** the three classic queries that cost \$2000 by accident (`SELECT *` over a wide table, an unpartitioned full scan, and a cross-join that explodes), and rewrite each to scan a fraction of the data.
- **Design** partition keys (time and integer-range) and cluster keys for a real query workload, and defend the choice against the actual `WHERE` and `GROUP BY` clauses the workload runs.
- **Read** a BigQuery query plan from `INFORMATION_SCHEMA.JOBS` and the execution-details view, and point at the stage that drives the bytes scanned and the slot-time.
- **Prove** a rewrite with `--dry_run` (bytes that *would* be billed) and `total_bytes_billed` (bytes actually billed), and quantify the reduction.
- **Build** a materialized view that BigQuery's optimizer automatically rewrites queries to use, and confirm the rewrite with the query plan.
- **Train** a BigQuery ML logistic-regression model with `CREATE MODEL`, evaluate it with `ML.EVALUATE`, and predict with `ML.PREDICT` — all in SQL, no data leaving BigQuery.
- **Decide** between on-demand pricing and a slot reservation (or autoscaling editions) with a break-even calculation for a real batch window, and recommend the cheaper option with numbers.
- **Query** `INFORMATION_SCHEMA` to audit table partitioning, find the most expensive jobs of the day, and attribute cost to a user or label.

## Prerequisites

This week assumes you have completed **Weeks 01–09** of C18, and specifically:

- **Week 09's pipeline still exists or can be re-applied.** The mini-project extends the BigQuery table that Week 09's Dataflow pipeline writes to. You kept the Terraform; you re-run it if needed. If you genuinely cannot recover it, the mini-project README includes a 40-line synthetic loader so you are not blocked — but the intended path is to extend Week 09.
- **You can read and write SQL.** Not BigQuery-specific SQL — just `SELECT`, `JOIN`, `GROUP BY`, window functions, CTEs. GoogleSQL (BigQuery's dialect) is standard-SQL-shaped with extensions; we teach the extensions, not the basics.
- **You are fluent with `bq` and `gcloud`.** You have used them since Week 01. This week leans hard on `bq query --dry_run`, `bq show`, and `bq mk --time_partitioning_field`.
- **Terraform on the `google` provider.** The table, the partitioning/clustering config, the materialized view, the BQML model, and the reservation are all provisioned in HCL. You write `google_bigquery_table`, `google_bigquery_dataset`, and `google_bigquery_reservation` resources.
- **A billing account with a budget armed** (Week 01's reflex). This is the one week where an un-budgeted project can actually hurt you. Arm a \$10 budget on the lab project before you run a single query.

You do **not** need prior BigQuery experience. We start at the storage model.

## Topics covered

- The **columnar storage model**: Capacitor (the columnar format), Colossus (the storage layer), Dremel (the execution engine), and the storage/compute separation that makes "scan less" the only lever that matters for cost.
- **Why bytes-scanned bills**: on-demand pricing is \$6.25/TiB scanned (us-multi-region, 2026 list); the scan is per-column, so `SELECT *` is the most expensive thing you can type.
- **The three \$2000 queries**: `SELECT *` over a wide table; an unpartitioned full table scan; an accidental cross-join / fan-out, and how each one is fixed.
- **Time partitioning**: `DAY`/`HOUR`/`MONTH`/`YEAR` and ingestion-time vs. column-based; the `require_partition_filter` guardrail; the `__NULL__` and `__UNPARTITIONED__` partitions.
- **Integer-range partitioning**: when an `INT64` key (tenant ID, bucketed hash) beats a date.
- **Clustering**: up to four columns, sorted-block pruning *within* a partition; how clustering and partitioning compose; the automatic re-clustering BigQuery does for free.
- **`INFORMATION_SCHEMA`**: `JOBS`, `JOBS_BY_PROJECT`, `TABLE_STORAGE`, `PARTITIONS`, `COLUMNS` — the views you use to audit cost, confirm partitioning, and find the expensive job.
- **The query plan**: reading `INFORMATION_SCHEMA.JOBS.job_stages`, the stage-by-stage records/bytes, `total_bytes_processed` vs. `total_bytes_billed`, and slot-milliseconds.
- **Materialized views**: incremental maintenance, automatic query rewrite, the staleness/freshness trade-off, and where an MV beats a scheduled query.
- **BI Engine**: the in-memory acceleration layer for dashboards; when a reservation of BI Engine capacity pays for itself.
- **BigQuery ML**: `CREATE MODEL` with `LOGISTIC_REG`, `ML.EVALUATE`, `ML.PREDICT`, `ML.FEATURE_INFO`; the value proposition (the data never leaves BigQuery) and its limits.
- **Slot reservations vs. on-demand**: the capacity model (Editions: Standard/Enterprise/Enterprise Plus), baseline + autoscaling slots, commitments, and the break-even math against on-demand for a batch window.
- **The Trino + Iceberg comparison**: what the open-source equivalent of this stack looks like, and the honest trade-offs (the course's standing "name the open-source alternative" rule).

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target.

| Day       | Focus                                                          | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Storage model, bytes-scanned pricing, the three \$2000 queries  |   2h     |    1h     |     0h     |    0.5h   |   1h     |     0h       |    1h      |     5.5h    |
| Tuesday   | Partitioning + clustering; landing a public dataset            |   1h     |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5h      |
| Wednesday | Reading the query plan; `INFORMATION_SCHEMA`; the rewrite drill |   2h     |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     7h      |
| Thursday  | Materialized views, BI Engine, BQML; reservations vs. on-demand |   1h     |    1h     |     1h     |    0.5h   |   1h     |     2h       |    0h      |     6.5h    |
| Friday    | The five-query challenge; reservation cost model               |   0h     |    0h     |     2h     |    0.5h   |   1h     |     2h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work (MV + BQML on the Week 09 table)         |   0h     |    0h     |     0h     |    0h     |   0.5h   |     3h       |    0h      |     3.5h    |
| Sunday    | Quiz, review, teardown verification                            |   0h     |    0h     |     0h     |    1h     |   0h     |     1h       |    0.5h    |     2.5h    |
| **Total** |                                                                | **6h**   | **6h**    | **4h**     | **3.5h**  | **5.5h** | **10h**      | **3.5h**   | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | Curated, current (2026) BigQuery docs, papers, books, and talks |
| [lecture-notes/01-the-three-queries-that-cost-2000.md](./02-lecture-notes/01-the-three-queries-that-cost-2000.md) | The pricing model as the failure mode; the three accidental \$2000 queries dissected and fixed |
| [lecture-notes/02-reading-the-query-plan-and-scan-less.md](./02-lecture-notes/02-reading-the-query-plan-and-scan-less.md) | Reading the query plan from `INFORMATION_SCHEMA.JOBS`; the "scan less" mental discipline; partition + cluster design |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-land-and-confirm-with-information-schema.md](./03-exercises/exercise-01-land-and-confirm-with-information-schema.md) | Land a public dataset into a partitioned-clustered table; confirm the schema with `INFORMATION_SCHEMA` |
| [exercises/exercise-02-rewrite-full-scan-into-five-queries.sql](./03-exercises/exercise-02-rewrite-full-scan-into-five-queries.sql) | Rewrite a full-scan query into five queries that each scan <1% of the data, proven with `bytes-billed` |
| [exercises/exercise-03-read-the-query-plan.py](./03-exercises/exercise-03-read-the-query-plan.py) | Pull a job's query plan via the API and identify the stage that drives the cost |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-on-demand-vs-reservation.md](./04-challenges/challenge-01-on-demand-vs-reservation.md) | Land a public dataset, write five <1%-scan queries, compare on-demand vs. a 100-slot reservation for a 1-hour batch window |
| [quiz.md](./05-quiz.md) | 13 questions with an answer key |
| [homework.md](./06-homework.md) | Six problems applying the week's concepts |
| [mini-project/README.md](./07-mini-project/00-overview.md) | Partitioned-clustered dataset fed by the Week 09 pipeline, with a materialized view, a BQML model, and a Trino+Iceberg comparison note |

## The "scan less" promise

C18 carried a "budget armed" marker since Week 01. Week 10 adds a second recurring marker to every query you run against a real table:

```
dry_run: 124.3 MiB would be billed · partition pruned: 364/365 days · cluster pruned: yes
```

If you cannot show that line — a `--dry_run` byte estimate, evidence of partition pruning, and evidence of clustering doing work — you do not get to run the query for real against a large table. We treat an un-dry-run query against a multi-GB table the way Week 01 treated an un-budgeted project: as a bug. The point of Week 10 is to make `bq query --dry_run` an automatic reflex *before* the query, and `INFORMATION_SCHEMA.JOBS` a reflex *after* it.

## A note on cost and the free tier

BigQuery's free tier is genuinely generous and you can do almost all of this week inside it:

- **The first 1 TiB of query (analysis) per month is free** on on-demand pricing. The whole exercise set scans well under 1 TiB *if you partition and cluster as instructed*. The entire point of the week is to make that true.
- **The first 10 GiB of active storage per month is free.** The public-dataset slices we land are kilobytes-to-megabytes after partition pruning at load time.
- **Public datasets** (`bigquery-public-data`) cost you nothing to *store* — Google stores them. You pay only to *scan* them, and only for the bytes your query touches. This is exactly why partitioning and clustering them into your own table matters: you control the scan.
- **The slot-reservation comparison** in the challenge is computed on paper from the published rates. You do **not** need to buy a reservation to do the math. If you want to *observe* a reservation, the challenge shows how to create a 100-slot Enterprise edition reservation, run one query, and delete it within the hour — budget under \$2, and tear it down immediately.
- **BQML** training on the small slices here is free or cents. `LOGISTIC_REG` on a few hundred MB is well inside the free analysis tier.

When you finish the mini-project, the **teardown gate** is mandatory. `terraform destroy` removes the dataset, the table, the materialized view, the model, and any reservation. You confirm with `bq ls` that the dataset is gone and `gcloud` shows no reservation. We do not leave reservations running — a forgotten 100-slot Enterprise reservation is a way to spend real money over a weekend.

## Stretch goals

If you finish early and want to push further:

- Read the **Dremel paper** (the 2010 VLDB original and the 2020 "Dremel: A Decade Later" retrospective). The retrospective explains Capacitor and the storage/compute split better than any docs page: <https://research.google/pubs/pub36632/>.
- Turn on **BI Engine** with a small reservation (1 GB is free-tier-friendly) and re-run a dashboard-shaped query; compare the latency and the bytes-billed (BI Engine-served bytes are not billed as analysis).
- Add a **second BQML model type** — try `BOOSTED_TREE_CLASSIFIER` on the same features and compare `ML.EVALUATE` ROC-AUC against the logistic regression.
- Reproduce one of your five rewritten queries against the **same data in BigQuery Storage Read API** from a Python client, and notice that the Storage API bills differently (per-byte read, not per-byte scanned).

## Up next

Continue to **Week 11 — Spanner, Cloud SQL, AlloyDB, and the database decision** once you have pushed the mini-project and confirmed your teardown — *especially* that no reservation is left running. Week 11 leaves the analytics world for the transactional one; the contrast between BigQuery's scan-the-world model and Spanner's index-a-row model is the whole reason they are taught back to back.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
