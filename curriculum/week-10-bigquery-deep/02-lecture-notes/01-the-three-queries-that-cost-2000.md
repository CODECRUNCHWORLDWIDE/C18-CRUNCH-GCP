# Lecture 1 — BigQuery's Pricing Model Is the Failure Mode: The Three Queries That Cost \$2000 by Accident

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can explain how BigQuery stores and bills, name the three classic accidental-\$2000 queries, dissect *why* each one scans what it scans, and rewrite each to scan a fraction of the data — proving the reduction with `--dry_run` and `total_bytes_billed`.

If you only remember one thing from this lecture, remember this:

> **BigQuery on-demand bills on bytes *scanned*, not rows returned, not wall-clock, not result size. The scan is per-column. So the most expensive thing you can type is `SELECT *` over a wide, unpartitioned table — and BigQuery will run it without a confirmation dialog. The entire discipline of this week is "scan less," and the only honest unit of that discipline is bytes billed.**

Every other cloud database punishes you with latency or an outage when you write a bad query. BigQuery punishes you with an invoice, silently, after the query already ran. There is no slow-query log that pages you before the damage; the damage *is* the query, and it completed in eleven seconds and felt fine. That asymmetry is the whole reason this lecture exists. We are going to make the cost of a query something you feel *before* you run it, the way a senior engineer does.

---

## 1. The storage model, only as much as you need

You cannot reason about cost without a mental model of how the bytes are laid out. Here is the minimum.

### Columnar storage: Capacitor

A row-oriented database (Postgres, MySQL) stores all of row 1's columns together, then all of row 2's, and so on. To read one column from a million rows, it touches every row's bytes and throws most of them away.

BigQuery is **columnar**. Its on-disk format is called **Capacitor**. All values of column A across every row are stored together, then all of column B, and so on. This has two consequences that drive everything:

1. **Reading one column does not touch the others.** `SELECT pickup_datetime FROM trips` reads only the `pickup_datetime` column's bytes. The other forty columns are never opened. This is why columnar storage is fast for analytics — and why `SELECT *` is the cardinal sin: it forces every column open.
2. **Compression is enormous, because a column is homogeneous.** A column of `INT64` trip distances compresses far better than a row of mixed types. Capacitor goes further: it *reorders rows* within a block to maximize run-length encoding, and it picks an encoding per column with a cost model. A column of `payment_type` with six distinct values becomes a dictionary plus tiny codes.

The 2020 "Dremel: A Decade Later" paper (in `resources.md`) is the readable source for this. The one sentence to internalize: **Capacitor's job is to make each column as small and as skippable as possible, so a query reads as few bytes as possible.** Partitioning and clustering are how *you* help it skip even more.

### Storage and compute are separate

BigQuery does not have "a server with disks." Storage lives in **Colossus** (Google's distributed file system); compute is a fleet of workers called **slots** orchestrated by **Dremel**. When you run a query, Dremel builds a tree of stages, assigns slots to them, and streams data through an in-memory shuffle. The storage is not "attached" to any worker — any slot can read any Capacitor file from Colossus.

Why you care: because storage and compute are decoupled, **the cost of a query has nothing to do with how big the table is on disk and everything to do with how many of its bytes your query forces a slot to read.** A 100 TB table costs you nothing to query if your query reads 50 MB of it. The lever is always "how few bytes can I make this query read."

### The two pricing models

There are exactly two ways to pay for BigQuery *compute* (storage is billed separately and is cheap):

- **On-demand.** You pay per **byte scanned**: \$6.25 per TiB in the US multi-region at 2026 list (it varies by region; check `resources.md`). The first **1 TiB per month is free**. There is a 10 MB minimum billed per query. This is the default, and it is where the \$2000 query lives.
- **Editions / reservations.** You buy a pool of **slots** (Standard / Enterprise / Enterprise Plus) priced per slot-hour, with optional autoscaling and commitments. You pay for the slots whether you scan a byte or a petabyte. We cover the break-even in Lecture 2 and the challenge.

The \$2000 query is an on-demand phenomenon. On a reservation, the same bad query does not cost \$2000 — it just *hogs your slots* and slows everyone else down, which is a different failure mode (contention, not invoice). For the rest of this lecture, assume on-demand.

### The arithmetic you must be able to do in your head

```
cost (USD) = bytes_scanned / (2^40 bytes per TiB) * 6.25
```

Memorize three anchor points:

| Bytes scanned | Cost (on-demand, US, \$6.25/TiB) |
|---------------|----------------------------------|
| 1 GiB         | \$0.0061 (≈ half a cent)         |
| 1 TiB         | \$6.25                           |
| 320 TiB       | \$2000                           |

So "the \$2000 query" is, precisely, a query that scans about **320 TiB**. That sounds absurd until you realize a single wide table can be tens of TB, and a self-join or a query run a few hundred times a day does the rest. Let's see how it happens.

---

## 2. The first \$2000 query: `SELECT *` over a wide table, run on a schedule

Here is the query. It looks completely innocent.

```sql
-- A "dashboard refresh" someone scheduled to run every 5 minutes.
SELECT *
FROM `bigquery-public-data.wikipedia.pageviews_2024`
WHERE views > 1000
ORDER BY views DESC
LIMIT 100;
```

The author's mental model: "I only want the top 100 rows, so this is cheap." Every clause of that sentence is wrong.

### Why it scans the whole table

1. **`SELECT *` opens every column.** Even though you display 100 rows, BigQuery must read every column of every row to evaluate `WHERE views > 1000` and to materialize the `*`. The `pageviews_2024` family is billions of rows; `SELECT *` reads all of them, all columns.
2. **`LIMIT 100` does not limit the scan.** The limit is applied *after* the scan, at the top of the plan. It caps what is *returned*, not what is *read*. This is the single most common misconception in BigQuery. `LIMIT` never reduces bytes billed (with the narrow exception of a clustered/partitioned table where the optimizer can sometimes stop early — do not rely on it).
3. **`ORDER BY` forces a full shuffle.** To sort, every qualifying row must reach the sort stage, so even the rows you discard were scanned.
4. **Run every 5 minutes = 288 times a day = ~8,640 times a month.** A query that scans, say, 40 GiB per run × 8,640 runs ≈ 338 TiB/month. At \$6.25/TiB that is **~\$2,100/month**, for a dashboard nobody looks at after 9am.

This is not a contrived example. "Someone scheduled a `SELECT *` dashboard query and forgot about it" is the single most common BigQuery cost incident in the wild. The schedule turns a one-time \$0.25 mistake into a recurring four-figure one.

### The fix

```sql
-- Read only the columns you display. Filter on a partition/cluster key.
-- Run it on a sensible cadence, or better, back it with a materialized view.
SELECT title, wiki, views
FROM `bigquery-public-data.wikipedia.pageviews_2024`
WHERE datehour >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
  AND views > 1000
ORDER BY views DESC
LIMIT 100;
```

What changed and why it matters:

- **Three columns instead of `*`.** You now read `title`, `wiki`, `views` — three columns out of the table's set. The other columns are never opened. On a wide table this alone is often a 5–20× reduction.
- **A filter on the partition column (`datehour`).** `pageviews_2024` is partitioned by `datehour`. Filtering to the last hour prunes the scan from "all of 2024" to "one hour." This is the big win — typically a 8,760× reduction (one hour out of a year).
- **A cadence that matches the data.** If the data updates hourly, you do not need to refresh every 5 minutes. And if it is a dashboard, a **materialized view** (Lecture 2) makes the expensive scan happen once on write, not once per viewer.

Prove it with a dry run before and after:

```bash
# Before (the bad one) — note the scanned bytes.
bq query --use_legacy_sql=false --dry_run \
  'SELECT * FROM `bigquery-public-data.wikipedia.pageviews_2024`
   WHERE views > 1000 ORDER BY views DESC LIMIT 100'
# Query successfully validated. ... would process 41234567890 bytes (≈38 GiB).

# After — three columns, one-hour partition filter.
bq query --use_legacy_sql=false --dry_run \
  'SELECT title, wiki, views FROM `bigquery-public-data.wikipedia.pageviews_2024`
   WHERE datehour >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
     AND views > 1000 ORDER BY views DESC LIMIT 100'
# Query successfully validated. ... would process 5242880 bytes (≈5 MiB).
```

38 GiB → 5 MiB is roughly a **7,600× reduction.** Multiply by 8,640 runs/month and the bill goes from ~\$2,100 to under \$1. That is the entire lesson of the week in one diff.

> **The rule:** Never `SELECT *` against a table you do not own and have not measured. Name your columns. Filter on the partition key. And before you put any query on a schedule, multiply its `--dry_run` cost by the number of runs per month — *that* is the real cost, not the single-run cost your gut estimated.

---

## 3. The second \$2000 query: the unpartitioned full scan

The first query was wide. This one is *deep*: a query that has to scan a large table top-to-bottom because the table was never partitioned and the filter cannot prune anything.

```sql
-- "How many trips happened on 2023-07-04?"
SELECT COUNT(*)
FROM `acme-analytics.rides.trips_raw`   -- a table YOU loaded, unpartitioned
WHERE EXTRACT(DATE FROM pickup_datetime) = '2023-07-04';
```

`trips_raw` is your own table — say you loaded five years of NYC taxi data into it without partitioning. It is 1.5 TB on disk. You want one day. You will scan all 1.5 TB.

### Why it scans the whole table

1. **No partitioning means no pruning.** BigQuery has no way to know which Capacitor blocks contain July 4, 2023, because the table is not organized by date. It must read the `pickup_datetime` column for every row to evaluate the `WHERE`. (`COUNT(*)` still has to read the filter column.)
2. **`EXTRACT(DATE FROM pickup_datetime) = '...'` is not sargable even if the table *were* partitioned by `pickup_datetime`.** Wrapping the partition column in a function defeats partition pruning — the optimizer cannot push a function-of-the-column down to a partition predicate. This is a second, subtler footgun: even people who partition correctly kill the pruning by wrapping the column in `DATE()`, `CAST()`, or `EXTRACT()`.
3. **`COUNT(*)` feels free but is not.** People assume `COUNT(*)` is metadata-cheap. It is, *if* you `SELECT COUNT(*) FROM table` with no filter (BigQuery answers that from metadata, ~0 bytes). The moment you add a `WHERE` on a non-partition column, it must scan that column across the whole table.

1.5 TB scanned = ~\$9.16 per run. Run it in an exploratory loop a few hundred times during an incident investigation, or wire it into a per-request app path, and you are at \$2000 fast.

### The fix: partition the table, and write a sargable filter

First, the table should have been partitioned by `pickup_datetime` at load time (we do this in Exercise 1). Given a partitioned table, the filter must touch the partition column *directly*:

```sql
-- Sargable: the partition column appears un-wrapped in a range predicate.
SELECT COUNT(*)
FROM `acme-analytics.rides.trips_partitioned`
WHERE pickup_datetime >= '2023-07-04'
  AND pickup_datetime <  '2023-07-05';
```

Now BigQuery prunes to a single day's partition and scans ~1/1825th of the table (one day out of five years): roughly **0.8 GiB instead of 1.5 TB**, a ~1,800× reduction, ~\$0.005 instead of \$9.16.

The two rules hiding in this fix:

- **Partition the table by the column you filter on most.** For event/trip data that is almost always the event timestamp. (Exercise 1.)
- **Keep the partition column bare in the predicate.** `WHERE pickup_datetime >= '2023-07-04' AND pickup_datetime < '2023-07-05'` prunes; `WHERE DATE(pickup_datetime) = '2023-07-04'` does **not**. Range-on-the-raw-column is the sargable form. Burn this in: *a function around the partition column is a full scan wearing a disguise.*

You can prove pruning happened with the dry run *and* with `INFORMATION_SCHEMA` after the fact (Lecture 2). The dry run on the partitioned table will report kilobytes-to-megabytes; on the unpartitioned one, gigabytes-to-terabytes.

> **The guardrail you should set on every event table:** `require_partition_filter = true`. With it, BigQuery *rejects* any query that does not filter on the partition column, with the error `Cannot query over table ... without a filter over column(s) 'pickup_datetime' that can be used for partition elimination`. That error is a gift — it is BigQuery refusing to let you run the \$9 full scan by accident. We set it in Exercise 1 and the mini-project.

---

## 4. The third \$2000 query: the accidental fan-out / cross-join

The first two queries scanned a lot of *base* data. The third one scans a modest amount of base data and then **explodes it in the shuffle** — the bytes processed balloon mid-query, not at the scan.

```sql
-- "Attach the daily exchange rate to every trip."
SELECT t.trip_id, t.fare_amount, r.rate
FROM `acme-analytics.rides.trips_partitioned` AS t
JOIN `acme-analytics.ref.fx_rates`            AS r
  ON t.currency = r.currency;          -- ⚠️ join key is NOT unique on the right
```

`fx_rates` has one row *per day* per currency — 365 rows for USD in a year. `trips` has, say, 50 million USD trips. The join `ON t.currency = r.currency` matches each trip against **every** USD rate row: 50M × 365 = **18.25 billion** output rows from a 50M-row input. The query may never finish, or it finishes and you have an 18-billion-row intermediate that the engine had to shuffle and materialize. On on-demand the *scan* of the two base tables might be cheap, but if you then write that result somewhere, or the engine spills it, you pay — and on a reservation you have just pinned every slot for an hour.

Cross-joins are the same disease in its most honest form:

```sql
-- A genuine CROSS JOIN with no predicate: rows(A) × rows(B). Almost never intended.
SELECT a.*, b.*
FROM big_table_a AS a, big_table_b AS b;   -- comma-join with no WHERE = cross join
```

The comma-join with no `WHERE` is the most dangerous typo in SQL: it is a syntactically valid Cartesian product. Two million-row tables become a *trillion*-row result.

### Why it costs

The cost driver here is **not** the base-table scan — it is the **shuffle and the materialization of the exploded intermediate**. In `INFORMATION_SCHEMA.JOBS.job_stages` (Lecture 2) you will see a join stage whose *output records* are orders of magnitude larger than its *input records*. That is the signature of a fan-out. The slot-time goes vertical; on-demand bills the bytes the join processed, and a repeated or scheduled version of this is your \$2000.

### The fix: make the join key unique, or aggregate first

The real intent was "the rate *for that trip's day*." The join key was under-specified — it should include the date:

```sql
-- Correct: join on (currency, date) so each trip matches exactly one rate row.
SELECT t.trip_id, t.fare_amount, r.rate
FROM `acme-analytics.rides.trips_partitioned` AS t
JOIN `acme-analytics.ref.fx_rates` AS r
  ON t.currency = r.currency
 AND DATE(t.pickup_datetime) = r.rate_date   -- the missing key
WHERE t.pickup_datetime >= '2024-01-01'
  AND t.pickup_datetime <  '2024-02-01';      -- and prune the partition
```

Now each trip matches exactly one rate row; the output is 50M rows, not 18 billion. The fan-out is gone.

When you *do* need a many-to-one summary, **aggregate before you join** so the side that fans out is collapsed first:

```sql
-- Aggregate fx to one row per (currency, month) BEFORE joining, if monthly is enough.
WITH monthly_fx AS (
  SELECT currency, DATE_TRUNC(rate_date, MONTH) AS m, AVG(rate) AS avg_rate
  FROM `acme-analytics.ref.fx_rates`
  GROUP BY currency, m
)
SELECT t.trip_id, t.fare_amount, f.avg_rate
FROM `acme-analytics.rides.trips_partitioned` AS t
JOIN monthly_fx AS f
  ON t.currency = f.currency
 AND DATE_TRUNC(DATE(t.pickup_datetime), MONTH) = f.m
WHERE t.pickup_datetime >= '2024-01-01' AND t.pickup_datetime < '2024-02-01';
```

The three rules hiding here:

- **A join key must be unique on at least one side, or you have a fan-out.** Before you write a join, ask: "for one row on the left, how many rows on the right match?" If the answer is not "exactly one" (or "zero or one"), you have a many-to-many and you will explode.
- **Never write a comma-join without a `WHERE`.** Prefer explicit `JOIN ... ON`. The comma form hides Cartesian products.
- **The fan-out shows up in the plan as output ≫ input on a stage.** This is the diagnostic you learn to read in Lecture 2.

---

## 5. The safety nets you turn on so the \$2000 query *cannot* run

Discipline is necessary but not sufficient — tired people write `SELECT *` at 2am. BigQuery gives you hard guardrails. Turn them on.

### Per-query maximum bytes billed

Every query can carry a ceiling. If the dry-run cost exceeds it, BigQuery *refuses to run the query* rather than billing you.

```bash
# Refuse to run anything that would bill more than 10 GiB.
bq query --use_legacy_sql=false --maximum_bytes_billed=10737418240 \
  'SELECT * FROM `bigquery-public-data.wikipedia.pageviews_2024`'
# Error: Query exceeded limit for bytes billed: 10737418240. ... bytes billed would be ...
```

In Terraform / scheduled queries you set `maximum_bytes_billed` on the job. In the Python client it is `QueryJobConfig(maximum_bytes_billed=...)`. **Set it on every automated query.** It is the seatbelt: the query that would have cost \$2000 errors out at the 10 GiB line and pages you instead of billing you.

### Per-user / per-project custom quotas

At the project level you can cap **total bytes scanned per day** per user or per project (Cloud Console → IAM & Admin → Quotas, or `gcloud`). Set a per-user daily cap (say 5 TiB) on any project where humans run ad-hoc queries. When a runaway loop hits the cap, queries start failing — annoying, but \$0 instead of \$2000.

### `require_partition_filter` on every event table

Covered in §3. Set it at table creation. It converts "accidental full scan" from a billing event into a query error.

### Billing budgets and the BigQuery cost label

Week 01's budget reflex applies doubly here. Additionally, **label every BigQuery job** (`--label cost_center:analytics`) so that when the budget *does* fire, your `INFORMATION_SCHEMA.JOBS` query (Lecture 2) can attribute the spend to a team or a query in seconds.

> **The combination that makes you safe:** `require_partition_filter` on tables + `maximum_bytes_billed` on automated jobs + a per-user daily scan quota + a billing budget. With all four, the \$2000 query physically cannot happen — the worst case is an error message. Without them, you are one tired `SELECT *` away from it.

---

## 6. The `--dry_run` reflex

The single most valuable habit this week installs: **dry-run every query against a large table before you run it for real.**

```bash
bq query --use_legacy_sql=false --dry_run 'SELECT ...'
# Query successfully validated. Assuming the tables are not modified,
# running this query will process 1234567890 bytes of data.
```

`--dry_run` costs nothing, runs in milliseconds, and returns the **bytes that would be billed** (it actually reports `total_bytes_processed`; for unclustered/un-time-travel cases this equals what you'll be billed, rounded up to the 10 MB minimum). It is the BigQuery equivalent of `terraform plan`: you look at the blast radius before you pull the trigger.

The reflex in full:

1. Write the query.
2. `--dry_run` it. Read the byte count. Convert to dollars in your head (§1's table).
3. If it is more than you expected, find out *why* — almost always a missing partition filter, a `SELECT *`, or a fan-out.
4. Fix it. Dry-run again. Confirm the reduction.
5. Only now run it for real. Then check `total_bytes_billed` in `INFORMATION_SCHEMA.JOBS` to confirm the estimate held.

You will do exactly this loop in Exercise 2 (rewrite a full scan into five queries that each scan <1%) and prove every rewrite with bytes-billed.

A Python version of the dry run, because you will automate it:

```python
from google.cloud import bigquery

client = bigquery.Client()

def dry_run_bytes(sql: str) -> int:
    """Return bytes BigQuery would process for `sql`, without running it."""
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    job = client.query(sql, job_config=job_config)  # API call, but no execution
    return job.total_bytes_processed

def to_usd(bytes_scanned: int, price_per_tib: float = 6.25) -> float:
    """On-demand cost estimate at the US multi-region 2026 list price."""
    return bytes_scanned / (2 ** 40) * price_per_tib

sql = "SELECT title FROM `bigquery-public-data.wikipedia.pageviews_2024` LIMIT 10"
b = dry_run_bytes(sql)
print(f"{b:,} bytes  (~{b / 2**30:.2f} GiB)  ~= ${to_usd(b):.4f}")
```

Wrap that in a pre-commit hook or a CI check that fails when a scheduled query's dry-run cost exceeds a threshold, and you have institutionalized the reflex.

---

## 7. Recap

You should now be able to:

- State that BigQuery on-demand bills on **bytes scanned, per column**, with the first 1 TiB/month free and \$6.25/TiB after (US, 2026 list), and do the bytes→dollars math in your head (320 TiB ≈ \$2000).
- Explain the storage model just enough: **Capacitor** (columnar format) on **Colossus** (storage) executed by **Dremel** across **slots** (compute), with storage and compute separated so cost tracks bytes read, not table size.
- Dissect the three accidental \$2000 queries:
  1. **`SELECT *` over a wide table on a schedule** — fixed by naming columns, filtering the partition key, and matching cadence to data (or backing it with a materialized view).
  2. **The unpartitioned full scan** (and the function-wrapped-partition-column variant) — fixed by partitioning and keeping the partition column bare in a range predicate.
  3. **The fan-out / cross-join** — fixed by making the join key unique on one side (or aggregating first), and never writing a comma-join without a `WHERE`.
- Turn on the four safety nets: `require_partition_filter`, `maximum_bytes_billed`, per-user daily scan quotas, and billing budgets.
- Run the `--dry_run` reflex: estimate before you run, fix, re-estimate, run, then confirm with `total_bytes_billed`.

Next up: how to *read the query plan* so you can point at the exact stage that scans the bytes, and how partition + cluster design turns "scan less" from a slogan into a table schema. Continue to [Lecture 2 — Reading the Query Plan and the "Scan Less" Mental Discipline](./02-reading-the-query-plan-and-scan-less.md).

---

## References

- *Estimate and control query costs* — Google Cloud: <https://cloud.google.com/bigquery/docs/best-practices-costs>
- *BigQuery pricing*: <https://cloud.google.com/bigquery/pricing>
- *Storage internals overview*: <https://cloud.google.com/bigquery/docs/storage_overview>
- *Partitioned tables* (require_partition_filter): <https://cloud.google.com/bigquery/docs/partitioned-tables>
- *Custom cost controls* (maximum bytes billed, custom quotas): <https://cloud.google.com/bigquery/docs/custom-quotas>
- *"Dremel: A Decade Later"* (VLDB 2020) — the Capacitor + disaggregation retrospective: <https://research.google/pubs/pub49489/>
- *BigQuery client library for Python* (`dry_run`, `total_bytes_processed`): <https://cloud.google.com/python/docs/reference/bigquery/latest>
