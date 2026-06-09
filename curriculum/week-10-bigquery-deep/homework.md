# Week 10 Homework

Six problems that apply the week's concepts beyond the exercises and mini-project. The full set should take about **5.5 hours**. Work in your Week 10 Git repository so each problem produces at least one commit you can point to later. Every problem that runs a query against a real table must include the `--dry_run` byte estimate as evidence — that is the reflex the week installs.

Each problem includes a **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — The cost-of-a-keystroke table

**Problem statement.** Build a reference table you can keep at your desk. In `notes/cost-table.md`, compute the on-demand cost (US, \$6.25/TiB) of scanning each of: 10 MiB, 100 MiB, 1 GiB, 10 GiB, 100 GiB, 1 TiB, 10 TiB, 100 TiB, 320 TiB. Then, against a public table of your choice, `--dry_run` three real queries — a `SELECT *` with no filter, the same with a partition filter, and the same with named columns + a partition filter — and place each query's bytes on your cost table.

**Acceptance criteria.**

- `notes/cost-table.md` has the nine byte→dollar rows computed correctly (320 TiB ≈ \$2000).
- Three `--dry_run` outputs pasted, each mapped to a dollar figure.
- One sentence stating the factor of reduction from query 1 to query 3.

**Hint.** `cost = bytes / 2^40 * 6.25`. The free first 1 TiB/month does not change the *marginal* cost of an additional scan; note that separately.

**Estimated time.** 30 minutes.

---

## Problem 2 — Find the function-wrapped partition column

**Problem statement.** You are handed five `WHERE` clauses (below) against a table partitioned by `DATE(event_time)`. In `notes/sargable.md`, classify each as **prunes** or **full scan**, and for the full-scan ones, rewrite to a sargable equivalent.

```
1. WHERE event_time >= '2026-01-01' AND event_time < '2026-01-02'
2. WHERE DATE(event_time) = '2026-01-01'
3. WHERE event_time BETWEEN '2026-01-01' AND '2026-01-02'
4. WHERE EXTRACT(YEAR FROM event_time) = 2026
5. WHERE event_time >= TIMESTAMP('2026-01-01') AND event_time < TIMESTAMP('2026-01-08')
```

**Acceptance criteria.**

- Each of the five classified correctly.
- Each full-scan clause rewritten to a pruning equivalent (where one exists; for #4, a year range).
- One sentence explaining why wrapping the partition column in a function defeats pruning.

**Hint.** The partition column must appear **bare** on one side of a comparison. `BETWEEN` on the bare column *does* prune (it is a range). `DATE(...)`, `EXTRACT(...)`, `CAST(...)` around the column do not.

**Estimated time.** 40 minutes.

---

## Problem 3 — Attribute the day's BigQuery spend

**Problem statement.** Write a SQL file `sql/cost-by-user.sql` that queries `INFORMATION_SCHEMA.JOBS_BY_PROJECT` and produces, for the last 7 days: per `user_email`, the total `total_bytes_billed`, the estimated USD, the job count, and the single most expensive query (its first 80 chars). Run it against your lab project and paste the output into `notes/cost-by-user.md`. Then answer: *if this were a 50-person team and one engineer's row showed 200 TiB billed, what two controls from Lecture 1 §5 would you turn on first, and why?*

**Acceptance criteria.**

- `sql/cost-by-user.sql` runs and groups by `user_email` with bytes, USD, count, and a top-query snippet.
- It is region-qualified (`` `region-us` `` or your region).
- The two-controls answer names `maximum_bytes_billed` and a per-user daily scan quota (or `require_partition_filter`), with one sentence of justification each.

**Hint.** Use `ROW_NUMBER() OVER (PARTITION BY user_email ORDER BY total_bytes_billed DESC)` to pick each user's top query, or `ARRAY_AGG(query ORDER BY total_bytes_billed DESC LIMIT 1)`.

**Estimated time.** 1 hour.

---

## Problem 4 — Partition + cluster a table for a *given* workload

**Problem statement.** You are given the three queries a workload runs most (below). In `notes/schema-design.md`, specify the **partition key** and **cluster keys** (in order) for the table they hit, and justify each choice against the actual `WHERE`/`GROUP BY`. Then write the `CREATE TABLE ... PARTITION BY ... CLUSTER BY ... OPTIONS(...)` DDL.

```sql
-- Q_a: hourly traffic for one day for one tenant
SELECT EXTRACT(HOUR FROM ts), COUNT(*) FROM logs
WHERE ts >= @day AND ts < @day_plus_1 AND tenant_id = @t GROUP BY 1;

-- Q_b: error rate by status for one tenant over a week
SELECT status, COUNTIF(status >= 500) / COUNT(*) FROM logs
WHERE ts >= @week_start AND ts < @week_end AND tenant_id = @t GROUP BY status;

-- Q_c: top 10 slowest endpoints for one tenant on one day
SELECT endpoint, APPROX_QUANTILES(latency_ms, 100)[OFFSET(99)] FROM logs
WHERE ts >= @day AND ts < @day_plus_1 AND tenant_id = @t GROUP BY endpoint ORDER BY 2 DESC LIMIT 10;
```

**Acceptance criteria.**

- Partition key chosen (`DATE(ts)`, `DAY`) with justification (every query filters a time range on `ts`).
- Cluster keys chosen and *ordered* (`tenant_id` first — every query filters it; then `status` or `endpoint`) with justification.
- `require_partition_filter = TRUE` set.
- The DDL is valid GoogleSQL.

**Hint.** Partition by the time column all three filter on. Cluster `tenant_id` first because all three filter it; pick the secondary cluster column from the one that appears in `WHERE`/`GROUP BY` most across the three (status appears in Q_b's group, endpoint in Q_c's — defend your pick).

**Estimated time.** 45 minutes.

---

## Problem 5 — Materialized view or scheduled query?

**Problem statement.** For each of the four scenarios below, decide **materialized view**, **scheduled query**, or **neither (just query the base table)**, and justify in one sentence in `notes/mv-decision.md`:

1. A revenue-by-day dashboard refreshed every few seconds by 200 analysts, over one append-only events table, tolerating 30-minute staleness.
2. A nightly report that joins five tables, dedupes, and writes a curated table for downstream consumers.
3. An ad-hoc question an engineer asks once during an incident.
4. A real-time fraud signal that must reflect the last 10 seconds of events with no staleness.

**Acceptance criteria.**

- All four classified with a one-sentence justification each.
- Scenario 1 is an MV (single table, simple aggregate, staleness tolerated, automatic rewrite serves the analysts).
- Scenario 2 is a scheduled query (multi-table transform, full recompute, controlled destination — beyond MV restrictions).
- Scenario 3 is neither (one-off; not worth maintaining anything).
- Scenario 4 names the MV freshness limitation (MV `max_staleness` and maintenance lag make sub-10-second guarantees unreliable; a streaming path is the real answer).

**Hint.** Lecture 2 §5: MVs are for single-table simple aggregates with automatic rewrite + incremental maintenance, with a staleness/cost trade-off. They have join/window restrictions; when you hit them, fall back to a scheduled query.

**Estimated time.** 40 minutes.

---

## Problem 6 — Train and read a BQML model

**Problem statement.** Using a public dataset (taxi tips, Iris, or your Exercise 1 table), train a `LOGISTIC_REG` model on a partition-pruned slice, run `ML.EVALUATE` and `ML.FEATURE_INFO`, and write `notes/bqml-readout.md` answering: (1) the model's roc_auc and what it tells you, (2) the two features `ML.FEATURE_INFO` shows have the widest value ranges (and whether you should normalize them — BQML standardizes numeric features by default, note that), (3) the bytes billed to *train* vs. to *predict* one day, read from `INFORMATION_SCHEMA.JOBS`.

**Acceptance criteria.**

- A `CREATE MODEL ... LOGISTIC_REG` that trains on a *pruned* window (not the whole table).
- `ML.EVALUATE` output pasted; roc_auc interpreted (>0.5 better than random; near 1.0 strong).
- `ML.FEATURE_INFO` output pasted; the normalization note included.
- Train-vs-predict bytes billed from `INFORMATION_SCHEMA.JOBS`.

**Hint.** Lecture 2 §7 has the full `CREATE MODEL`/`ML.EVALUATE`/`ML.PREDICT` pattern. Keep the train `WHERE` to a few months so it is free-tier. roc_auc is the column to read first for a classifier.

**Estimated time.** 1 hour 15 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 30 min |
| 2 | 40 min |
| 3 | 1 h 0 min |
| 4 | 45 min |
| 5 | 40 min |
| 6 | 1 h 15 min |
| **Total** | **~4 h 50 min** |

(The remaining ~40 min of the week's homework budget is reading the linked primary sources — at minimum the "Dremel: A Decade Later" paper and the cost-control docs in `resources.md`.)

## Rubric

| Criterion | Weight | What "great" looks like |
|-----------|-------:|-------------------------|
| Correctness | 35% | Cost math is right; sargable classification is right; the model trains and evaluates |
| Cost discipline | 25% | Every query has a `--dry_run` byte estimate; bytes-billed confirmed from `INFORMATION_SCHEMA.JOBS`; nothing scans more than a few GB |
| Reasoning quality | 20% | Schema/MV/control decisions argue from the *actual* `WHERE`/`GROUP BY` and from blast radius, not vibes |
| Evidence | 10% | Real command outputs pasted, not paraphrased; bytes/dollars shown |
| Completeness | 10% | All six problems committed with sensible messages |

When you've finished all six, push your repo and open the [mini-project](./mini-project/README.md) if you haven't already.
