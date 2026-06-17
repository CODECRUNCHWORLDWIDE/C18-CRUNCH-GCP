-- Exercise 2 - Rewrite a full-scan query into five queries that each scan <1%
--              of the data, and prove it with bytes-billed.
--
-- Goal: Practice the core "scan less" discipline. You are handed ONE fat query
--       that scans the whole table (and would scan the whole public dataset if
--       run against the source). Your job: produce FIVE focused queries that
--       together answer the same business questions, where each query scans
--       UNDER 1% of the table, and prove each reduction with --dry_run and the
--       INFORMATION_SCHEMA.JOBS total_bytes_billed after running it.
--
-- Estimated time: 75 minutes.
--
-- HOW TO USE THIS FILE
--
--   1. You need the `rides.trips_optimized` table from Exercise 1 (NYC yellow
--      taxi Jan 2018, PARTITION BY DATE(pickup_datetime), CLUSTER BY
--      payment_type, vendor_id, require_partition_filter = TRUE).
--
--   2. Section A is THE BAD QUERY. Dry-run it, record the bytes. This is your
--      baseline - the number every rewrite must beat by >100x.
--
--   3. Section B has FIVE rewrites (Q1..Q5), each already correct. Run each with
--      --dry_run, record bytes, then run for real, then read total_bytes_billed
--      from INFORMATION_SCHEMA.JOBS. Confirm each is < 1% of the baseline.
--
--   4. Section C is the PROOF query: it pulls your last 6 jobs and shows
--      total_bytes_billed so you can paste the evidence into your writeup.
--
--   5. Then complete the TODO at the bottom: write a SIXTH query of your own
--      that answers a new question while staying under 1%, and prove it.
--
-- Run a single statement with:
--   bq query --use_legacy_sql=false --dry_run '<paste the statement>'
--   bq query --use_legacy_sql=false           '<paste the statement>'
--
-- ACCEPTANCE CRITERIA
--
--   [ ] You recorded the baseline bytes for the BAD query (Section A).
--   [ ] All five rewrites run; each --dry_run is < 1% of the baseline.
--   [ ] You confirmed each rewrite's total_bytes_billed in INFORMATION_SCHEMA.JOBS
--       (Section C), and it matches the dry-run within rounding.
--   [ ] You wrote and proved a sixth query of your own (the TODO).
--   [ ] Your writeup states, per query, the baseline %, and WHICH lever did the
--       work (partition prune, column pruning, cluster prune, or aggregation).

-- ===========================================================================
-- SECTION A - THE BAD QUERY (your baseline; do NOT keep running this)
-- ===========================================================================
--
-- "Give me a monthly dashboard: total trips, revenue, avg tip %, the busiest
--  vendor, and card-vs-cash split."  Written as one SELECT * + everything query
--  that scans the whole table, all columns, every time the dashboard loads.
--
-- Dry-run this ONCE, record the bytes, then never run it again.

SELECT *
FROM `rides.trips_optimized`
WHERE pickup_datetime >= '2018-01-01' AND pickup_datetime < '2018-02-01'
ORDER BY total_amount DESC;

-- NOTE: even with the partition filter, SELECT * over the whole month reads
-- EVERY column of EVERY row, and the ORDER BY forces a full shuffle. That is
-- your baseline B_bytes. Each rewrite below must scan < 0.01 * B_bytes.


-- ===========================================================================
-- SECTION B - THE FIVE REWRITES (run each: dry-run, then real, then confirm)
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- Q1 - Total trips + revenue for ONE day (partition prune + column pruning).
--      Lever: one day out of 31 (partition) AND 2 columns out of 9 (column).
-- ---------------------------------------------------------------------------
SELECT
  COUNT(*)          AS trips,
  SUM(total_amount) AS revenue
FROM `rides.trips_optimized`
WHERE pickup_datetime >= '2018-01-15' AND pickup_datetime < '2018-01-16';

-- ---------------------------------------------------------------------------
-- Q2 - Card-vs-cash split for one day (partition prune + cluster prune).
--      Lever: payment_type is the LEADING cluster key, so blocks prune within
--      the day partition; only 2 columns read.
-- ---------------------------------------------------------------------------
SELECT
  payment_type,
  COUNT(*) AS trips
FROM `rides.trips_optimized`
WHERE pickup_datetime >= '2018-01-15' AND pickup_datetime < '2018-01-16'
GROUP BY payment_type
ORDER BY trips DESC;

-- ---------------------------------------------------------------------------
-- Q3 - Average tip % for CARD trips on one day (cluster prune on payment_type).
--      Lever: WHERE payment_type = 1 prunes blocks; fare/tip columns only.
--      NULLIF guards divide-by-zero on zero-fare trips.
-- ---------------------------------------------------------------------------
SELECT
  ROUND(AVG(SAFE_DIVIDE(tip_amount, NULLIF(fare_amount, 0)) * 100), 2) AS avg_tip_pct
FROM `rides.trips_optimized`
WHERE pickup_datetime >= '2018-01-15' AND pickup_datetime < '2018-01-16'
  AND payment_type = 1;   -- card; cluster-pruned

-- ---------------------------------------------------------------------------
-- Q4 - Busiest vendor for one day (partition prune + group on a cluster key).
--      Lever: one day; vendor_id is the 2nd cluster key; 1 column grouped.
-- ---------------------------------------------------------------------------
SELECT
  vendor_id,
  COUNT(*) AS trips
FROM `rides.trips_optimized`
WHERE pickup_datetime >= '2018-01-15' AND pickup_datetime < '2018-01-16'
GROUP BY vendor_id
ORDER BY trips DESC
LIMIT 1;

-- ---------------------------------------------------------------------------
-- Q5 - Hourly trip profile for one day (partition prune + 1 column read).
--      Lever: one day; only pickup_datetime is read; the EXTRACT happens AFTER
--      the partition prune (the WHERE keeps the column BARE so pruning works).
-- ---------------------------------------------------------------------------
SELECT
  EXTRACT(HOUR FROM pickup_datetime) AS hour,
  COUNT(*)                           AS trips
FROM `rides.trips_optimized`
WHERE pickup_datetime >= '2018-01-15' AND pickup_datetime < '2018-01-16'
GROUP BY hour
ORDER BY hour;


-- ===========================================================================
-- SECTION C - THE PROOF (bytes-billed for your recent jobs)
-- ===========================================================================
--
-- After running Q1..Q5 for real, run this to read what you were ACTUALLY billed.
-- Replace `region-us` with your jobs' region if you loaded elsewhere.

SELECT
  job_id,
  -- first 60 chars of the query so you can tell them apart
  SUBSTR(REGEXP_REPLACE(query, r'\s+', ' '), 1, 60) AS query_snippet,
  total_bytes_processed,
  total_bytes_billed,
  ROUND(total_bytes_billed / POW(2, 40) * 6.25, 6) AS est_usd
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
  AND job_type = 'QUERY'
  AND state = 'DONE'
  AND statement_type != 'SCRIPT'
ORDER BY creation_time DESC
LIMIT 10;


-- ===========================================================================
-- TODO - WRITE AND PROVE A SIXTH QUERY OF YOUR OWN
-- ===========================================================================
--
-- Answer a NEW business question about one day's data while staying under 1% of
-- the baseline. Ideas: "longest 5 trips by distance for one day", "median fare
-- by passenger_count for one day", "share of trips over $50 for one day".
--
-- Requirements:
--   - Filter on pickup_datetime with a BARE range predicate (so the partition
--     prunes; require_partition_filter will reject you otherwise).
--   - Read only the columns you need (no SELECT *).
--   - If you can, filter or group on a cluster key (payment_type or vendor_id)
--     to show a cluster prune too.
--   - Dry-run it, confirm < 1% of baseline, run it, confirm total_bytes_billed.
--
-- Write your query below this line:
--
-- SELECT ...
-- FROM `rides.trips_optimized`
-- WHERE pickup_datetime >= '2018-01-15' AND pickup_datetime < '2018-01-16'
--   AND ...
-- GROUP BY ...;


-- ===========================================================================
-- WRITEUP (do this in a writeup.md next to this file)
-- ===========================================================================
--
--   1. A table: query | baseline_bytes | this_query_bytes | % of baseline |
--      lever(s). All five (plus your sixth) must be < 1%.
--   2. One paragraph: which single lever gave the biggest reduction across all
--      six queries, and why (hint: the partition prune from one-day-of-31 is
--      ~3.2% before column pruning; column pruning + cluster pruning take you
--      the rest of the way under 1%).
--   3. One paragraph: the BAD query's ORDER BY had no LIMIT and SELECT *. Explain
--      in cost terms why removing BOTH (no full sort, named columns) mattered,
--      even though both queries had the same partition filter.


-- ===========================================================================
-- HINTS (read only if stuck)
-- ===========================================================================
--
-- - "< 1% of baseline" is easy to hit: the baseline scans all 31 days x all 9
--   columns. A one-day, 2-column query scans roughly (1/31) x (2/9) ~= 0.7% of
--   the SELECT * baseline before clustering even helps. Clustering on
--   payment_type drops Q2/Q3 further.
--
-- - The dry-run for CLUSTERED tables OVER-estimates: it cannot know which blocks
--   it will skip. So Q2/Q3 may dry-run higher than they bill. ALWAYS confirm the
--   real number in Section C - that is the one that counts.
--
-- - If a query is REJECTED with "without a filter over column(s)
--   'pickup_datetime'", you wrapped the column in a function (DATE(...),
--   EXTRACT(...)) in the WHERE, or omitted it. Keep it bare in a range predicate.
--
-- - SAFE_DIVIDE returns NULL instead of erroring on divide-by-zero; combine with
--   NULLIF(fare_amount, 0) to also skip the zero-fare rows cleanly.
