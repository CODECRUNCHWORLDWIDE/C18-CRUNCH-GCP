# Exercise 1 — Land a Public Dataset into a Partitioned-and-Clustered Table, Confirm with `INFORMATION_SCHEMA`

**Time estimate:** ~60 minutes.

## Goal

Take a slice of a BigQuery public dataset and land it into **your own table** that is **partitioned by event time and clustered by two columns**, with `require_partition_filter` turned on. Then prove — not assume — that the partitioning, clustering, and schema actually took, using `INFORMATION_SCHEMA.COLUMNS`, `INFORMATION_SCHEMA.PARTITIONS`, and `INFORMATION_SCHEMA.TABLE_STORAGE`. This is the table shape the mini-project builds on, and the skill ("land it right, then confirm with the catalog") is the one the lab grades.

We use the **NYC taxi** dataset. (The Wikipedia pageviews path is in the hints if you prefer it.)

## Prerequisites

- A GCP project with BigQuery enabled and a **\$10 budget armed** (Week 01 reflex — this is the week it matters).
- `bq` and `gcloud` on your path. `bq version` works.
- The BigQuery Data Editor + Job User roles on the project (you have these as project owner in the lab project).

## Steps

### Step 1 — Make a dataset to land into

A dataset is BigQuery's namespace for tables. Pick the **same region** you will query in (`INFORMATION_SCHEMA.JOBS` is region-scoped, so consistency matters).

```bash
PROJECT=$(gcloud config get-value project)
bq --location=US mk --dataset --description "Week 10 BigQuery deep" "${PROJECT}:rides"
```

### Step 2 — Dry-run the source so you know what you are about to scan

Never load blind. The public `tlc_yellow_trips_2018` table is partition-able by `pickup_datetime`. First, see how big one month is:

```bash
bq query --use_legacy_sql=false --dry_run '
SELECT *
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2018`
WHERE pickup_datetime >= "2018-01-01" AND pickup_datetime < "2018-02-01"'
# Query successfully validated. ... will process N bytes  (read it; expect a few hundred MB)
```

Record N. That is the bytes you will scan to do the load. (One month keeps you well inside the free tier.)

### Step 3 — Create the partitioned-and-clustered table via CTAS

`CREATE TABLE ... AS SELECT` (CTAS) lands the slice and applies the partitioning/clustering in one statement. We select **only the columns we need** (Lecture 1: never `SELECT *` what you do not need).

```bash
bq query --use_legacy_sql=false --maximum_bytes_billed=2147483648 '
CREATE OR REPLACE TABLE `rides.trips_optimized`
PARTITION BY DATE(pickup_datetime)
CLUSTER BY payment_type, vendor_id
OPTIONS (
  require_partition_filter = TRUE,
  description = "NYC yellow taxi Jan 2018, partitioned by pickup day, clustered by payment_type+vendor_id"
) AS
SELECT
  vendor_id,
  pickup_datetime,
  dropoff_datetime,
  passenger_count,
  trip_distance,
  fare_amount,
  tip_amount,
  total_amount,
  payment_type
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2018`
WHERE pickup_datetime >= "2018-01-01" AND pickup_datetime < "2018-02-01"'
```

### Step 4 — Confirm the schema with `INFORMATION_SCHEMA.COLUMNS`

Prove the columns landed with the types you expect:

```bash
bq query --use_legacy_sql=false '
SELECT column_name, data_type, is_partitioning_column, clustering_ordinal_position
FROM `rides.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = "trips_optimized"
ORDER BY ordinal_position'
```

You should see `is_partitioning_column = YES` on `pickup_datetime` and `clustering_ordinal_position = 1` on `payment_type`, `2` on `vendor_id`.

### Step 5 — Confirm partitioning with `INFORMATION_SCHEMA.PARTITIONS`

This is the proof that the table is physically split by day:

```bash
bq query --use_legacy_sql=false '
SELECT partition_id, total_rows, total_logical_bytes
FROM `rides.INFORMATION_SCHEMA.PARTITIONS`
WHERE table_name = "trips_optimized"
ORDER BY partition_id
LIMIT 10'
```

`partition_id` should be dates like `20180101`, `20180102`, ... — one partition per day. If you see a single `__UNPARTITIONED__` or `__NULL__` partition holding everything, the partitioning did not take and you must re-check Step 3.

### Step 6 — Confirm clustering and size with `INFORMATION_SCHEMA.TABLE_STORAGE`

```bash
bq query --use_legacy_sql=false '
SELECT table_name, total_rows, total_partitions,
       ROUND(total_logical_bytes / POW(2,20), 1) AS logical_mib,
       ROUND(active_logical_bytes / POW(2,20), 1) AS active_mib
FROM `rides.INFORMATION_SCHEMA.TABLE_STORAGE`
WHERE table_name = "trips_optimized"'
```

`total_partitions` should be ~31 (one month of days). Note `logical_mib` — that is your storage footprint (well under the 10 GiB free tier).

### Step 7 — Prove partition pruning works (the payoff)

Run the *same logical query* with and without a partition filter and compare the dry-run bytes. The pruned one must scan a fraction.

```bash
# WITHOUT a usable partition filter -> require_partition_filter REJECTS it.
bq query --use_legacy_sql=false --dry_run '
SELECT COUNT(*) FROM `rides.trips_optimized` WHERE passenger_count = 1'
# Error: Cannot query over table 'rides.trips_optimized' without a filter
#        over column(s) 'pickup_datetime' that can be used for partition elimination

# WITH a partition filter on ONE day -> prunes to one partition.
bq query --use_legacy_sql=false --dry_run '
SELECT COUNT(*) FROM `rides.trips_optimized`
WHERE pickup_datetime >= "2018-01-15" AND pickup_datetime < "2018-01-16"
  AND passenger_count = 1'
# Query successfully validated. ... will process M bytes  (M should be ~1/31 of the table)
```

The first command being *rejected* is the seatbelt from Lecture 1 §5 doing its job. The second proves the prune: M should be roughly 1/31 of the table's logical bytes.

### Step 8 — Produce the marker

Compute and print the marker line the week asks for:

```bash
bq query --use_legacy_sql=false --format=prettyjson --dry_run '
SELECT COUNT(*) FROM `rides.trips_optimized`
WHERE pickup_datetime >= "2018-01-15" AND pickup_datetime < "2018-01-16"
  AND payment_type = 1' | jq -r '"dry_run: \(.statistics.totalBytesProcessed) bytes would be billed · partition pruned: 30/31 days · cluster pruned: payment_type"'
```

## Acceptance criteria

- [ ] Dataset `rides` exists in your chosen region.
- [ ] Table `rides.trips_optimized` exists, **partitioned by `DATE(pickup_datetime)`** and **clustered by `payment_type, vendor_id`**, with `require_partition_filter = TRUE`.
- [ ] `INFORMATION_SCHEMA.COLUMNS` shows `pickup_datetime` as the partitioning column and the two cluster columns with ordinals 1 and 2.
- [ ] `INFORMATION_SCHEMA.PARTITIONS` shows ~31 day-partitions (`20180101`...`20180131`), **not** a single `__UNPARTITIONED__` blob.
- [ ] A query without a partition filter is **rejected** by `require_partition_filter`; the same query with a one-day filter scans ~1/31 of the table (proven by dry-run bytes).
- [ ] You can produce the marker line.

## Expected output (shape — your byte counts will differ)

```
# Step 4
+------------------+-----------+-------------------------+-----------------------------+
| column_name      | data_type | is_partitioning_column  | clustering_ordinal_position |
+------------------+-----------+-------------------------+-----------------------------+
| vendor_id        | INT64     | NO                      |                           2 |
| pickup_datetime  | TIMESTAMP | YES                     |                        NULL |
| payment_type     | INT64     | NO                      |                           1 |
| ...              | ...       | ...                     |                         ... |
+------------------+-----------+-------------------------+-----------------------------+

# Step 5
+--------------+------------+----------------------+
| partition_id | total_rows | total_logical_bytes  |
+--------------+------------+----------------------+
| 20180101     |     286100 |             20897123 |
| 20180102     |     310455 |             22654881 |
| ...          |        ... |                  ... |
+--------------+------------+----------------------+

# Step 8
dry_run: 1923456 bytes would be billed · partition pruned: 30/31 days · cluster pruned: payment_type
```

## Cleanup

You will reuse `rides.trips_optimized` in Exercises 2 and 3 and the mini-project, so **keep it** for now. To remove it later:

```bash
bq rm -t -f "${PROJECT}:rides.trips_optimized"
bq rm -r -d -f "${PROJECT}:rides"
```

---

## Hints

<details>
<summary>Wikipedia pageviews instead of taxi</summary>

```bash
bq query --use_legacy_sql=false --maximum_bytes_billed=2147483648 '
CREATE OR REPLACE TABLE `rides.pageviews_optimized`
PARTITION BY DATE(datehour)
CLUSTER BY wiki, title
OPTIONS (require_partition_filter = TRUE) AS
SELECT datehour, wiki, title, views
FROM `bigquery-public-data.wikipedia.pageviews_2024`
WHERE datehour >= "2024-01-01" AND datehour < "2024-01-02"'
```

Pageviews is partitioned by `datehour` (hourly); clustering by `wiki, title` is the canonical choice. One day is plenty for the free tier.

</details>

<details>
<summary>Why cluster by payment_type first, vendor_id second?</summary>

Order cluster columns most-frequently-filtered first (Lecture 2 §4). NYC analysts filter on `payment_type` (cash vs. card) constantly and `vendor_id` less so, so `payment_type` leads. If your workload filtered on `vendor_id` more, you would flip them.

</details>

<details>
<summary>My PARTITIONS query shows one __UNPARTITIONED__ row</summary>

You either forgot `PARTITION BY` in the CTAS, or you partitioned by a column that was NULL/absent. Re-run Step 3 exactly. Also: data freshly streamed in sits in `__UNPARTITIONED__` briefly before BigQuery commits it to day-partitions — but a CTAS load is committed immediately, so you should see day-partitions right away.

</details>
