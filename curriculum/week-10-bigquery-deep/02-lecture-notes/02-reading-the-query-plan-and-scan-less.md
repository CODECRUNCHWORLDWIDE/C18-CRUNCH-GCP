# Lecture 2 — Reading the Query Plan and the "Scan Less" Mental Discipline

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can read a BigQuery query plan from `INFORMATION_SCHEMA.JOBS.job_stages`, point at the stage that drives the bytes scanned and the slot-time, design partition and cluster keys for a real query workload, confirm a materialized-view rewrite in the plan, and decide on-demand vs. a slot reservation with break-even math.

Lecture 1 taught you that bytes scanned is the unit that bills, and showed three queries that scan too much. This lecture teaches you the two things you need to fix that systematically: **how to read the plan to see *where* the bytes go**, and **how to shape the table so the plan reads fewer of them.** Then it puts a price on slots so you can choose your pricing model with numbers instead of vibes.

If you only remember one thing from this lecture:

> **The query plan tells you which stage is expensive, and the table schema (partition + cluster keys) decides how much that stage can skip. "Scan less" is not a query trick; it is mostly a *schema* decision you make once, at table-creation time, in service of the `WHERE` and `GROUP BY` the workload actually runs.**

---

## 1. What a query plan is

When you submit a query, Dremel compiles it into a tree of **stages**. Each stage runs in parallel across many slots, reads from the previous stage (or from Colossus, if it is a leaf input stage), does work (filter, aggregate, join, sort), and writes its output into an in-memory **shuffle** that the next stage reads. A simple `GROUP BY` is typically three stages:

```
Stage 0: INPUT    — read the table's needed columns from Colossus, apply the WHERE,
                    do a partial aggregation, write to shuffle.
Stage 1: AGGREGATE— read the partial aggregates from shuffle, combine them, write to shuffle.
Stage 2: OUTPUT   — read the final aggregates, format, return to the client.
```

The number you cared about in Lecture 1 — bytes scanned — is determined almost entirely by **Stage 0, the input stage**: how many bytes it reads from Colossus before anything else happens. Everything downstream operates on whatever Stage 0 let through. So **reading the plan is mostly about answering: how many bytes and records did the input stage read, and why that many?**

---

## 2. Reading the plan from `INFORMATION_SCHEMA.JOBS`

You have three ways to see a plan: the Console (the visual execution graph), the API (`QueryJob.query_plan`, used in Exercise 3), and SQL against `INFORMATION_SCHEMA`. The SQL way is the one you script and the one that survives in a runbook, so learn it.

`INFORMATION_SCHEMA.JOBS` (and `JOBS_BY_PROJECT`) has one row per job, with a repeated `job_stages` field. Here is the query you will run a hundred times this week — "show me the most expensive jobs today and their bytes billed":

```sql
SELECT
  job_id,
  user_email,
  query,
  total_bytes_processed,
  total_bytes_billed,
  -- dollars at US on-demand list price
  ROUND(total_bytes_billed / POW(2, 40) * 6.25, 4) AS est_usd,
  total_slot_ms,
  TIMESTAMP_DIFF(end_time, start_time, MILLISECOND) AS elapsed_ms
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
  AND state = 'DONE'
ORDER BY total_bytes_billed DESC
LIMIT 20;
```

Note `` `region-us` `` — `INFORMATION_SCHEMA.JOBS*` is **region-qualified**; you must name the region your jobs ran in. Two columns matter most:

- **`total_bytes_processed`** — what the engine processed. This is what `--dry_run` predicted.
- **`total_bytes_billed`** — what you pay for. It rounds up to the 10 MB per-query minimum and reflects the actual billed scan. *This is the number that becomes dollars.* Multiply by \$6.25/2^40 and you have the cost.

`total_slot_ms` is slot-milliseconds: how much compute the query consumed. On a reservation this is the number that competes with everyone else's queries; on on-demand it does not bill, but a high slot-ms with low bytes billed is the fingerprint of a fan-out (lots of compute, modest scan).

### Drilling into the stages

To find *which stage* drove the cost, unnest `job_stages`:

```sql
SELECT
  stage.id,
  stage.name,
  stage.records_read,
  stage.records_written,
  stage.shuffle_output_bytes,
  stage.slot_ms
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT,
  UNNEST(job_stages) AS stage
WHERE job_id = 'bquxjob_xxxxxxxx_xxxxxxxxxxxx'
ORDER BY stage.id;
```

What you are hunting for:

- **The input stage with huge `records_read`** — that is your scan. If it read 2 billion records and you expected to touch one day's worth, your partition pruning failed.
- **A stage where `records_written` ≫ `records_read`** — that is a **fan-out** (Lecture 1, §4). The join exploded the row count. This is the single most useful diagnostic the stage view gives you.
- **A stage with most of the `slot_ms`** — that is where the compute went. Usually it is a sort, a big join, or a high-cardinality aggregation.

> **The "find the stage that costs the money" drill (Exercise 3 and the deep-dive interview):** run a query, pull its `job_stages`, and answer two questions: (1) which stage read the most bytes/records from the table (the scan)? (2) is there a stage where output ≫ input (a fan-out)? Ninety percent of cost incidents are one of those two, and the plan tells you which in thirty seconds.

---

## 3. Partitioning: prune whole slices before the scan

Partitioning splits a table into independent segments keyed by a column. A filter on the partition column lets BigQuery **skip entire partitions without reading them** — the bytes in a pruned partition are never scanned and never billed. This is your biggest lever.

### Time partitioning

The common case. Partition by a `DATE`, `TIMESTAMP`, or `DATETIME` column at `DAY`, `HOUR`, `MONTH`, or `YEAR` granularity.

```sql
-- DDL: a trips table partitioned by day on the event timestamp.
CREATE TABLE `acme-analytics.rides.trips_partitioned`
PARTITION BY DATE(pickup_datetime)
OPTIONS (
  require_partition_filter = TRUE,          -- the seatbelt from Lecture 1 §5
  partition_expiration_days = 1825          -- auto-drop partitions older than 5y
) AS
SELECT * FROM `acme-analytics.rides.trips_raw`;
```

Choosing granularity:

- **`DAY`** is the default and right for most event/log/trip data. You get up to ~4,000 partitions per table (≈11 years of daily), which covers almost everything.
- **`HOUR`** when you query intra-day windows constantly *and* you have enough data per hour to be worth it. Hourly partitioning on low-volume data creates tiny partitions and metadata overhead — do not partition hourly on a table that gets 100 rows a day.
- **`MONTH`/`YEAR`** when you have many years and your queries span months — keeps partition count sane.

Ingestion-time vs. column-based: BigQuery can partition by the *load time* (`_PARTITIONTIME`, a pseudo-column) instead of a data column. Prefer **column-based** (partition by the actual `pickup_datetime`) so the partition matches the *event* time, not when the loader happened to run. Ingestion-time partitioning silently misfiles late-arriving data — exactly the late-data problem Week 09 warned you about.

Two special partitions you will see: `__NULL__` (rows whose partition column is NULL) and `__UNPARTITIONED__` (streaming buffer rows not yet committed to a partition). A query that filters the partition column with an equality will not read `__NULL__`; if your data has NULL timestamps, you must account for them.

### Integer-range partitioning

When the natural slicing key is an integer, not a date — most often a **tenant/customer ID** or a **bucketed hash** — use integer-range partitioning:

```sql
CREATE TABLE `acme-analytics.rides.trips_by_vendor`
PARTITION BY RANGE_BUCKET(vendor_id, GENERATE_ARRAY(1, 100, 1))
OPTIONS (require_partition_filter = TRUE) AS
SELECT * FROM `acme-analytics.rides.trips_raw`;
```

`RANGE_BUCKET(col, GENERATE_ARRAY(start, end, interval))` defines the buckets. A query `WHERE vendor_id = 7` prunes to one bucket. Use integer-range when your dominant filter is "one tenant" rather than "one time window." You cannot partition by *both* a date and an int — a table has exactly one partition column — so pick the dimension your queries filter on most, and use **clustering** for the secondary dimension.

> **The partition-design rule:** Partition by the column that appears in the `WHERE` of your *most expensive, most frequent* query. For event data that is the event timestamp 95% of the time. Confirm your choice by looking at `INFORMATION_SCHEMA.JOBS` for last week's actual queries — partition for the workload you *have*, not the one you imagine.

---

## 4. Clustering: prune blocks *within* a partition

Partitioning prunes whole partitions. **Clustering** sorts the data *inside* each partition by up to four columns, so a filter or aggregation on those columns can skip blocks within the partition too. Clustering composes with partitioning — you almost always want both.

```sql
CREATE TABLE `acme-analytics.rides.trips_optimized`
PARTITION BY DATE(pickup_datetime)
CLUSTER BY payment_type, vendor_id      -- up to 4 columns, order matters
OPTIONS (require_partition_filter = TRUE) AS
SELECT * FROM `acme-analytics.rides.trips_raw`;
```

How clustering works and the rules that fall out:

- **The data is physically sorted by the cluster columns, in the order you list them.** A filter on `payment_type` (the first cluster column) prunes blocks effectively; a filter on `vendor_id` *alone* (the second) prunes less, because the data is sorted by `payment_type` first. **Order cluster columns from most-frequently-filtered to least, and from lowest to higher cardinality for the leading columns.**
- **Clustering helps `WHERE`, `GROUP BY`, and `JOIN` on the cluster keys**, by reading fewer blocks and by enabling more efficient aggregation.
- **BigQuery re-clusters automatically and for free** in the background as you insert data. You do not run a `VACUUM`. New data lands unsorted and is folded into the clustered layout asynchronously.
- **Dry-run does not always show clustering savings**, because the engine cannot know at planning time exactly which blocks it will skip. The savings show up in `total_bytes_billed` *after* the run. This is the one place where `--dry_run` over-estimates: cluster-pruned bytes are billed less than the dry run predicted. So for clustered tables, confirm the real savings in `INFORMATION_SCHEMA.JOBS`, not just the dry run.

### Partition vs. cluster: when to use which

| Situation | Use |
|-----------|-----|
| Dominant filter is a time window | **Partition** by the timestamp |
| Dominant filter is one tenant/customer (integer) | **Partition** by integer range on that key |
| Secondary filters (status, type, vendor) you also slice by | **Cluster** by those, within the partition |
| High-cardinality string you filter or group by often | **Cluster** by it (partitioning would create too many partitions) |
| Table is small (< ~1 GB) | Neither — the whole table is one scan unit anyway |

The canonical shape for an event table: **partition by event time (DAY), cluster by tenant + event-type.** That handles "give me last week's events for tenant X of type Y" — the most common analytics query — with a partition prune *and* two cluster prunes. This is exactly the shape the mini-project builds on the Week 09 table.

---

## 5. Materialized views: do the expensive scan once, on write

A **materialized view (MV)** is a precomputed, **incrementally maintained** query result stored as a table. The two properties that make it different from a plain table or a scheduled query:

1. **Incremental maintenance.** When base-table rows change, BigQuery updates only the affected parts of the MV, in the background — you do not recompute the whole thing. (A scheduled query recomputes everything every run; the MV does delta maintenance.)
2. **Automatic query rewrite (smart tuning).** You do *not* have to query the MV by name. If you run a query against the *base table* that the optimizer recognizes the MV can answer, it transparently rewrites your query to read the MV instead. Your dashboards keep querying the base table and silently get the cheap answer.

```sql
-- An MV that pre-aggregates daily revenue per vendor.
CREATE MATERIALIZED VIEW `acme-analytics.rides.daily_vendor_revenue`
PARTITION BY day
CLUSTER BY vendor_id
AS
SELECT
  DATE(pickup_datetime) AS day,
  vendor_id,
  COUNT(*)              AS trips,
  SUM(fare_amount)      AS revenue
FROM `acme-analytics.rides.trips_optimized`
GROUP BY day, vendor_id;
```

Now this query, written against the *base table*, gets rewritten to read the MV:

```sql
-- The user wrote this against trips_optimized; the optimizer reads the MV.
SELECT day, SUM(revenue) AS total_revenue
FROM (
  SELECT DATE(pickup_datetime) AS day, SUM(fare_amount) AS revenue
  FROM `acme-analytics.rides.trips_optimized`
  WHERE pickup_datetime >= '2024-01-01' AND pickup_datetime < '2024-02-01'
  GROUP BY day
)
GROUP BY day;
```

### Confirming the rewrite in the plan

How do you *know* the optimizer used the MV and not the base table? Read the plan. In `job_stages`, the input stage's `name` will reference the materialized view, and the `total_bytes_billed` will be a fraction of the base-table scan. Or check the job's `query_info.optimization_details` (in the API / Console "Execution details"), which lists `materialized_views_used`. If you scan the full base table, the rewrite did not fire — usually because your query's aggregation does not match the MV's, or the MV is stale beyond `max_staleness`.

### Freshness vs. cost

MVs maintained in real time cost maintenance compute on every base change. If your dashboard tolerates slightly stale data, set `max_staleness`:

```sql
CREATE MATERIALIZED VIEW `acme-analytics.rides.daily_vendor_revenue`
OPTIONS (
  enable_refresh = TRUE,
  refresh_interval_minutes = 60,
  max_staleness = INTERVAL "1" HOUR
)
AS SELECT ... ;
```

`max_staleness = 1 HOUR` tells BigQuery the MV may be up to an hour behind the base table; queries get the cheap MV answer without forcing an expensive on-the-fly merge of fresh base rows. **This is the lever:** trade a little freshness for a lot of cost. A revenue dashboard does not need second-fresh data; a fraud check might.

> **MV vs. scheduled query:** use an **MV** when the result is a simple aggregation/filter of one table and you want automatic rewrite + incremental maintenance. Use a **scheduled query** when you need a complex multi-table transform, a full recompute, or a destination you control precisely. MVs have restrictions (limited join/window support, one base table for incremental maintenance); when you hit them, fall back to a scheduled query. The mini-project uses an MV because the aggregation is exactly what MVs are good at.

---

## 6. BI Engine: the dashboard accelerator

**BI Engine** is an in-memory analysis service that caches hot data and serves dashboard-shaped queries in sub-second time. You buy a small **reservation** of BI Engine memory (e.g. 1–10 GB); BigQuery keeps the hot columns of your frequently-queried tables in RAM and serves matching queries from memory.

The cost angle that matters this week: **bytes served from BI Engine are not billed as on-demand analysis.** A dashboard hitting the same partitioned table every few seconds, served from BI Engine, stops accumulating bytes-scanned charges for the cached portion. BI Engine pays for itself when you have a high-QPS, low-latency dashboard over a stable dataset — which is exactly the Looker/Looker Studio use case Google designed it for. It does *not* help one-off analytical queries; that is what partitioning and MVs are for.

You will not need BI Engine for the core week (it is a stretch goal), but you must be able to say *when* it earns its keep: **many users, repeated similar queries, sub-second latency requirement, stable hot dataset.**

---

## 7. BigQuery ML: machine learning where the data already lives

BQML lets you train and serve models **in SQL, with the data never leaving BigQuery.** That is the whole value proposition: no export to a notebook, no feature pipeline to a separate ML platform, no data-movement cost or governance headache. You `CREATE MODEL`, then `ML.PREDICT` against it like a table function.

A logistic-regression classifier end to end — this is the exact shape the mini-project uses:

```sql
-- 1. Train. label_col must be the thing you predict; everything else is a feature.
CREATE OR REPLACE MODEL `acme-analytics.rides.tip_classifier`
OPTIONS (
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['high_tip'],
  auto_class_weights = TRUE,             -- handle class imbalance
  data_split_method = 'AUTO_SPLIT'       -- BQML holds out an eval set for you
) AS
SELECT
  trip_distance,
  passenger_count,
  EXTRACT(HOUR FROM pickup_datetime)               AS pickup_hour,
  EXTRACT(DAYOFWEEK FROM pickup_datetime)          AS dow,
  payment_type,
  IF(tip_amount / NULLIF(fare_amount, 0) > 0.20, 1, 0) AS high_tip  -- the label
FROM `acme-analytics.rides.trips_optimized`
WHERE pickup_datetime >= '2024-01-01' AND pickup_datetime < '2024-04-01'
  AND fare_amount > 0;

-- 2. Evaluate. precision/recall/accuracy/f1/log_loss/roc_auc on the held-out split.
SELECT * FROM ML.EVALUATE(MODEL `acme-analytics.rides.tip_classifier`);

-- 3. Inspect what the model learned.
SELECT * FROM ML.FEATURE_INFO(MODEL `acme-analytics.rides.tip_classifier`);

-- 4. Predict on new data. Output adds predicted_high_tip + probability columns.
SELECT trip_distance, payment_type, predicted_high_tip,
       predicted_high_tip_probs
FROM ML.PREDICT(
  MODEL `acme-analytics.rides.tip_classifier`,
  (SELECT trip_distance, passenger_count,
          EXTRACT(HOUR FROM pickup_datetime) AS pickup_hour,
          EXTRACT(DAYOFWEEK FROM pickup_datetime) AS dow,
          payment_type
   FROM `acme-analytics.rides.trips_optimized`
   WHERE pickup_datetime >= '2024-04-01' AND pickup_datetime < '2024-04-02')
);
```

The cost note: **training scans the training data once (billed as analysis), prediction scans the prediction input.** Both are partition-prunable — train and predict on a date range, not the whole table. A `LOGISTIC_REG` on a few hundred MB is free-tier-friendly.

The honest limits: BQML is excellent for the "good enough, in-place" model — logistic/linear regression, k-means, boosted trees, matrix factorization, and now imported TensorFlow/ONNX models and remote Vertex models. It is **not** where you train a 7B-parameter network. The decision rule: **if the data is already in BigQuery and the model is a classical ML model, BQML saves you an entire data-movement pipeline; if you need deep learning or the data lives elsewhere, use Vertex AI (Week 12).**

---

## 8. Slot reservations vs. on-demand: the break-even

Now the decision the challenge makes you compute. Two pricing models for compute (storage is separate and cheap either way):

- **On-demand:** \$6.25/TiB scanned (US, 2026 list), first 1 TiB/month free. You pay per byte; idle costs nothing; a runaway query costs a lot.
- **Editions (reservations):** you buy **slots** priced per slot-hour. 2026 US list, approximate: **Standard ~\$0.04/slot-hour, Enterprise ~\$0.06/slot-hour, Enterprise Plus ~\$0.10/slot-hour** (autoscaling, pay-as-you-go) — commitments (1-year/3-year) discount these further. You pay for the slots whether idle or saturated; a runaway query does not cost more, it just hogs slots.

### The break-even calculation

The question is always: **for this workload, is the bytes-scanned bill (on-demand) bigger or smaller than the slot-hours bill (reservation)?**

Worked example — a **1-hour batch window** running heavy queries, the challenge's scenario:

- Suppose your batch scans **50 TiB** in that hour.
  - **On-demand:** `50 TiB × $6.25 = $312.50` for the hour (minus the free TiB if not used yet).
- Suppose you provision a **100-slot Enterprise reservation** for that hour.
  - **Reservation:** `100 slots × 1 hour × $0.06/slot-hour = $6.00` for the hour.
  - But: 100 slots must actually be *enough* to finish the batch in the hour. If the batch needs more slot-time than 100 slots × 1 hour = 100 slot-hours can deliver, it runs longer (and you pay for the longer window) or you need more slots.

In this example the reservation is **~50× cheaper** — because the batch scans a *lot* of bytes but does not need a *lot* of wall-clock-slots to do it. That is the general shape: **reservations win when you scan many bytes relative to the slot-time you need; on-demand wins when you scan few bytes or run sporadically.**

The decision rule, stated cleanly:

- **Heavy, predictable, scan-intensive workloads → reservation.** A nightly batch that scans tens of TiB is far cheaper on a reservation. Buy a baseline + autoscaling reservation sized to finish in the window.
- **Sporadic, light, or spiky ad-hoc workloads → on-demand.** A team running a few GB of queries a day pays cents on-demand and would waste a reservation's idle slot-hours.
- **The hybrid most shops land on:** a small **committed baseline reservation** for the predictable batch + autoscaling for spikes, and **on-demand for ad-hoc exploration** (often via assignment of specific projects to the reservation and leaving others on-demand). BigQuery lets you assign projects/folders/orgs to reservations, so you can split the org this way.

You compute exactly this — with the dry-run bytes from your five queries and the slot-hour rate — in the challenge, and recommend the cheaper option with numbers. The grader checks your arithmetic.

> **The reservation footgun (and why the teardown gate exists):** a reservation bills for its slots **continuously**, idle or not. A forgotten 100-slot Enterprise reservation is `100 × 24 × $0.06 = $144/day`, ~\$4,300/month, scanning nothing. This is the one BigQuery cost that is *not* bytes-scanned — it is slot-hours — and it is the most common "why is my bill so high, I barely queried anything" incident among people who tried reservations and forgot them. **Delete the reservation when the batch window ends.** Terraform `destroy` does this in the mini-project; the teardown gate verifies it.

---

## 9. The Trino + Iceberg honest comparison

The course names the open-source alternative every week. For BigQuery it is **Trino (the query engine) over Apache Iceberg tables (the open table format) on object storage (S3/GCS).**

The conceptual mapping:

| BigQuery | Trino + Iceberg |
|----------|-----------------|
| Capacitor (columnar format) | Parquet (columnar format) |
| Colossus (storage) | S3 / GCS / MinIO object storage |
| Dremel + slots (compute) | Trino workers (you run/scale them) |
| Partitioning | Iceberg partitioning ("hidden partitioning") |
| Clustering | Iceberg sort order + Parquet row-group stats |
| Bytes-scanned billing | You pay for the compute cluster + object-storage reads |
| Materialized view | Iceberg + a scheduled Spark/Trino job (no native incremental MV) |
| BQML | Trino has no native ML; you bolt on Spark MLlib / external |

The honest trade-offs:

- **Trino + Iceberg gives you no lock-in and a predictable compute bill** (you run the cluster), and Iceberg's open format means any engine (Spark, Flink, DuckDB, BigQuery itself via BigLake) can read it. That is real, and it is why the capstone exit-plan asks you to cost it.
- **BigQuery gives you zero operational burden** — no cluster to size, patch, or babysit; the optimizer, re-clustering, and MV maintenance are free background work — at the cost of vendor lock-in and the bytes-scanned billing model that this whole week is about defending against.
- **The line is blurring:** BigQuery now reads and writes Iceberg tables (BigLake/BigQuery tables for Apache Iceberg), so "BigQuery vs. Iceberg" is increasingly "BigQuery's managed compute vs. self-run Trino, both over Iceberg." The mini-project's comparison note asks you to benchmark one of your queries conceptually against the Trino+Iceberg path and write down the operational-cost difference, not just the dollar difference.

---

## 10. Recap

You should now be able to:

- Read a query plan from `INFORMATION_SCHEMA.JOBS_BY_PROJECT` — find the most expensive jobs by `total_bytes_billed`, and unnest `job_stages` to find **the scan stage** (huge `records_read`) and **the fan-out stage** (`records_written` ≫ `records_read`).
- Distinguish `total_bytes_processed` (what dry-run predicts) from `total_bytes_billed` (what you pay), and convert the latter to dollars.
- Design **partition keys** (time `DAY`/`HOUR`/`MONTH`/`YEAR`, or integer-range for tenant IDs), keep the partition column bare in predicates, and set `require_partition_filter`.
- Design **cluster keys** (up to 4, ordered most-filtered-first), know that clustering prunes blocks within a partition and is re-clustered for free, and that its savings show up in bytes-billed not the dry run.
- Build a **materialized view**, set `max_staleness` to trade freshness for cost, and confirm the automatic rewrite fired by reading the plan.
- Say when **BI Engine** earns its keep (high-QPS, sub-second dashboards over a stable dataset).
- Train, evaluate, and predict with a **BQML** logistic-regression model in SQL, and state when BQML beats exporting to Vertex AI.
- Compute the **on-demand vs. reservation break-even** for a batch window with slot-hour rates, and know the reservation footgun (idle slots still bill — delete reservations).
- Map the stack honestly onto **Trino + Iceberg** and name the operational-cost trade-off.

That is the toolkit. The exercises drill each piece; the challenge makes you put a dollar figure on the pricing-model decision; the mini-project assembles all of it on top of the Week 09 pipeline. Continue to the [exercises](../03-exercises/00-overview.md).

---

## References

- *Query plan and timeline* — Google Cloud: <https://cloud.google.com/bigquery/docs/query-plan-explanation>
- *`INFORMATION_SCHEMA.JOBS`*: <https://cloud.google.com/bigquery/docs/information-schema-jobs>
- *Partitioned tables*: <https://cloud.google.com/bigquery/docs/partitioned-tables>
- *Clustered tables*: <https://cloud.google.com/bigquery/docs/clustered-tables>
- *Materialized views*: <https://cloud.google.com/bigquery/docs/materialized-views-intro>
- *BI Engine*: <https://cloud.google.com/bigquery/docs/bi-engine-intro>
- *BigQuery ML `CREATE MODEL` (GLM)*: <https://cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create-glm>
- *Reservations / Editions*: <https://cloud.google.com/bigquery/docs/reservations-intro>
- *BigQuery pricing*: <https://cloud.google.com/bigquery/pricing>
- *Apache Iceberg spec (partitioning)*: <https://iceberg.apache.org/spec/#partitioning>
