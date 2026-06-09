# Mini-Project — The Analytics Layer on the Week 09 Pipeline

> Take the BigQuery table that **Week 09's Pub/Sub → Dataflow pipeline** lands events into, and turn it into a production analytics layer: a **partitioned-and-clustered** table, a **materialized view** that pre-aggregates the hot query, and a **BQML logistic-regression model** that predicts on the data — all provisioned in Terraform, all gated by `require_partition_filter`, all torn down cleanly. You also write a **Trino + Iceberg comparison note** (the course's standing "name the open-source alternative" rule). **This extends Week 09. You do not start fresh.**

This is the Phase-3 compounding artifact. Week 09 built the pipe; this week builds what makes the data at the end of the pipe cheap to query and useful to predict on. By the end you have a dataset another engineer can point a dashboard at without scanning the world, and a model that scores new events as they arrive — and a teardown that leaves no reservation running.

**Estimated time:** ~10 hours (split across Thursday, Friday, Saturday, Sunday in the suggested schedule).

---

## The compounding: what you inherit from Week 09

Week 09's hands-on lab was: *synthetic event generator → Pub/Sub → Dataflow (Python Beam) → BigQuery, with a dead-letter topic.* Its Dataflow pipeline writes events to a BigQuery table. **Week 09's teardown gate told you to keep the Terraform** — this is the week you were keeping it for.

You inherit (or re-stand-up) a BigQuery table roughly like this — an events table with at least an event timestamp, a tenant/user key, an event type, and a numeric payload:

```
events.raw_events
  event_id        STRING
  event_time      TIMESTAMP     -- when the event happened (the partition key)
  tenant_id       STRING        -- per-tenant (a cluster key)
  event_type      STRING        -- e.g. "view", "click", "purchase" (a cluster key)
  amount          FLOAT64       -- a payload number
  user_agent      STRING
  ... (whatever Week 09 wrote)
```

If Week 09's pipeline wrote a *different* schema, adapt the partition/cluster keys to your columns — the *shape* (timestamp partition, tenant+type clustering, an aggregatable amount, a predictable label) is what matters.

> **If you genuinely cannot recover the Week 09 table** (you deleted it and the repo), a 50-line synthetic loader is provided at the end of this README so you are not blocked. But re-applying Week 09's Terraform is the intended path, and the grader rewards extending it over the synthetic fallback.

---

## What you will build

A Terraform module + SQL that turns the raw events table into an analytics layer:

```
analytics-layer/
├── README.md
├── main.tf                      # dataset, optimized table, MV, reservation (gated)
├── variables.tf
├── outputs.tf
├── backend.tf                   # GCS backend (reuse the Week 01 state bucket)
├── sql/
│   ├── 01_create_optimized_table.sql   # CTAS: partitioned + clustered from raw_events
│   ├── 02_materialized_view.sql         # daily per-tenant per-type aggregate MV
│   ├── 03_train_model.sql               # CREATE MODEL ... LOGISTIC_REG
│   ├── 04_evaluate_model.sql            # ML.EVALUATE
│   └── 05_predict.sql                   # ML.PREDICT on recent events
├── scripts/
│   ├── prove_pruning.sh         # dry-run before/after, confirm partition+cluster prune
│   ├── confirm_mv_rewrite.sh    # show the optimizer rewrote a base-table query to the MV
│   └── teardown.sh              # the GATED destroy (incl. reservation check)
└── notes/
    └── trino-iceberg-comparison.md
```

By the end: ~150 lines of HCL + ~120 lines of SQL + the comparison note. Another engineer clones it, points it at the Week 09 dataset, applies, and gets the optimized table, the MV, and the trained model.

---

## Part 1 — The optimized table (partition + cluster)

`sql/01_create_optimized_table.sql` — a CTAS that reshapes `events.raw_events` into a partitioned-clustered table. This is the Exercise 1 skill applied to *your* pipeline's data.

```sql
CREATE OR REPLACE TABLE `events.events_optimized`
PARTITION BY DATE(event_time)
CLUSTER BY tenant_id, event_type
OPTIONS (
  require_partition_filter = TRUE,
  partition_expiration_days = 90,
  description = "Week 09 events, partitioned by event day, clustered by tenant+type"
) AS
SELECT
  event_id,
  event_time,
  tenant_id,
  event_type,
  amount,
  user_agent
FROM `events.raw_events`
WHERE event_time IS NOT NULL;   -- keep NULL timestamps out of __NULL__
```

In Terraform, the table is a `google_bigquery_table` with `time_partitioning`, `clustering`, and `require_partition_filter`. The CTAS can be run as a `google_bigquery_job` (a `query` job) so the whole thing is one `terraform apply`:

```hcl
resource "google_bigquery_table" "events_optimized" {
  dataset_id          = var.dataset_id
  table_id            = "events_optimized"
  deletion_protection = false  # labs

  time_partitioning {
    type                     = "DAY"
    field                    = "event_time"
    require_partition_filter = true
    expiration_ms            = 90 * 24 * 3600 * 1000
  }
  clustering = ["tenant_id", "event_type"]

  schema = file("${path.module}/schema/events_optimized.json")
}
```

**Confirm** with `INFORMATION_SCHEMA.PARTITIONS` (one partition per day, not `__UNPARTITIONED__`) and run `scripts/prove_pruning.sh` to show a one-day-filtered query scans a small fraction. Capture the marker:

```
dry_run: 2.1 MiB would be billed · partition pruned: 89/90 days · cluster pruned: tenant_id
```

---

## Part 2 — The materialized view

`sql/02_materialized_view.sql` — pre-aggregate the query your dashboard runs constantly: daily counts and revenue per tenant per event type. Because it is an MV, the optimizer rewrites matching base-table queries to read it (Lecture 2 §5).

```sql
CREATE MATERIALIZED VIEW `events.daily_tenant_rollup`
PARTITION BY day
CLUSTER BY tenant_id
OPTIONS (
  enable_refresh = TRUE,
  refresh_interval_minutes = 30,
  max_staleness = INTERVAL "30" MINUTE
) AS
SELECT
  DATE(event_time)      AS day,
  tenant_id,
  event_type,
  COUNT(*)              AS events,
  SUM(amount)           AS total_amount,
  COUNTIF(event_type = 'purchase') AS purchases
FROM `events.events_optimized`
GROUP BY day, tenant_id, event_type;
```

In Terraform this is a `google_bigquery_table` with a `materialized_view { query = ... }` block.

**The proof that earns the points:** `scripts/confirm_mv_rewrite.sh` runs a *base-table* query that the MV can answer, then reads `INFORMATION_SCHEMA.JOBS` (or the job's `query_info`) to show the optimizer used the MV — `total_bytes_billed` is a fraction of the base scan, and the plan references `daily_tenant_rollup`. If the rewrite does **not** fire, your dashboard query's aggregation does not match the MV's; reconcile them.

```bash
# A query a dashboard would run, written against the BASE table:
bq query --use_legacy_sql=false '
SELECT day, SUM(total_amount) AS revenue
FROM (
  SELECT DATE(event_time) AS day, SUM(amount) AS total_amount
  FROM `events.events_optimized`
  WHERE event_time >= "2026-06-01" AND event_time < "2026-06-08"
  GROUP BY day
) GROUP BY day'
# Then confirm in INFORMATION_SCHEMA.JOBS that bytes_billed << the base table,
# i.e. the optimizer read the MV.
```

---

## Part 3 — The BQML logistic-regression model

`sql/03_train_model.sql` — train a model that predicts something useful and *predictable* from the event features. A natural label on event data: **will this user convert (have a purchase) within their session/day?** Define the label, train, evaluate, predict (Lecture 2 §7).

```sql
CREATE OR REPLACE MODEL `events.conversion_model`
OPTIONS (
  model_type          = 'LOGISTIC_REG',
  input_label_cols    = ['converted'],
  auto_class_weights  = TRUE,
  data_split_method   = 'AUTO_SPLIT'
) AS
SELECT
  tenant_id,
  EXTRACT(HOUR      FROM event_time) AS event_hour,
  EXTRACT(DAYOFWEEK FROM event_time) AS dow,
  event_type,
  amount,
  -- label: did this tenant have a purchase on this day?
  MAX(IF(event_type = 'purchase', 1, 0))
    OVER (PARTITION BY tenant_id, DATE(event_time)) AS converted
FROM `events.events_optimized`
WHERE event_time >= '2026-03-01' AND event_time < '2026-06-01';  -- prune the train window
```

```sql
-- 04_evaluate_model.sql
SELECT * FROM ML.EVALUATE(MODEL `events.conversion_model`);
SELECT * FROM ML.FEATURE_INFO(MODEL `events.conversion_model`);
```

```sql
-- 05_predict.sql : score the last day of events.
SELECT tenant_id, event_type, predicted_converted, predicted_converted_probs
FROM ML.PREDICT(
  MODEL `events.conversion_model`,
  (SELECT tenant_id,
          EXTRACT(HOUR FROM event_time) AS event_hour,
          EXTRACT(DAYOFWEEK FROM event_time) AS dow,
          event_type, amount
   FROM `events.events_optimized`
   WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY))
);
```

In Terraform, train via a `google_bigquery_job` query job, or document running `sql/03_train_model.sql` with `bq query` as a post-apply step. **Capture the `ML.EVALUATE` row** (precision, recall, accuracy, roc_auc) in your README — that is the deliverable, not a perfect model. A toy event dataset will produce a mediocre ROC-AUC; that is fine. The skill is "trained, evaluated, and predicted in SQL with the data never leaving BigQuery," not "won a Kaggle competition."

> **Cost note:** training and prediction both scan their input once — **prune the window** (`WHERE event_time >= ...`) so you train on a slice, not the whole table. On the small Week 09 data this is free-tier.

---

## Part 4 — The reservation decision (paper + optional observe)

Apply the challenge's cost reasoning to *this* workload. In `README.md` under "Cost decision":

1. Sum the `total_bytes_billed` of the table build + MV refresh + model train + a day of predictions (from `INFORMATION_SCHEMA.JOBS`).
2. Compute the **on-demand cost** of running this analytics layer's nightly refresh.
3. Compute the **100-slot reservation cost** for the refresh window, with the capacity sanity-check.
4. State the **break-even** and a one-line recommendation. For a small pipeline like this, on-demand almost certainly wins (you scan megabytes) — *say so with numbers*, and state at what data volume the recommendation would flip.

Optionally provision the reservation in Terraform behind a flag (`var.enable_reservation`, default `false`) so the teardown gate has something to prove it removed:

```hcl
resource "google_bigquery_reservation" "batch" {
  count         = var.enable_reservation ? 1 : 0
  name          = "week10-batch"
  location      = var.location
  slot_capacity = 100
  edition       = "ENTERPRISE"
  autoscale { max_slots = 0 }   # flat 100 for the demo; delete promptly
}
```

---

## Part 5 — The Trino + Iceberg comparison note

`notes/trino-iceberg-comparison.md` (~1 page) — the standing "name the open-source alternative" deliverable. Cover:

1. **The mapping** (Lecture 2 §9): Capacitor↔Parquet, Colossus↔object storage, Dremel/slots↔Trino workers, partitioning↔Iceberg hidden partitioning, clustering↔Iceberg sort order, MV↔scheduled Spark/Trino job, BQML↔(no native equivalent).
2. **A performance/operational comparison of ONE of your queries.** You do not have to stand up Trino — reason about it: what would you operate (a Trino cluster + a catalog + object storage), what would you pay (compute cluster hours + storage reads vs. bytes-scanned), and where would the Iceberg equivalent of your partition prune and cluster prune come from (partition spec + Parquet row-group stats).
3. **The honest verdict:** for a team of this size and this query volume, which would you run and why. Name the lock-in cost of staying on BigQuery and the operational cost of moving to Trino+Iceberg. (If you want a real number, the capstone's exit plan reuses this.)

---

## The teardown gate (MANDATORY)

```bash
#!/usr/bin/env bash
# scripts/teardown.sh - gated destroy. Removes the analytics layer AND verifies
# no reservation is left running (the Lecture 2 §8 footgun).
set -euo pipefail

echo "This will DESTROY the Week 10 analytics layer:"
echo "  - events_optimized table, daily_tenant_rollup MV, conversion_model"
echo "  - any week10-batch reservation"
echo "It does NOT touch the Week 09 raw_events table or pipeline."
read -r -p "Type the dataset name to confirm: " confirm
if [[ "$confirm" != "${DATASET:?set DATASET}" ]]; then
  echo "Confirmation did not match. Aborting." >&2
  exit 1
fi

terraform destroy -auto-approve

echo "Verifying no reservation remains (the expensive one):"
gcloud beta bigquery reservations list --location="${LOCATION:?set LOCATION}" \
  --format="value(name)" || true
echo "If the line above is EMPTY, you are safe. A listed reservation bills ~\$144/day."

echo "Verifying the analytics objects are gone:"
bq ls "${DATASET}" | grep -E "events_optimized|daily_tenant_rollup|conversion_model" \
  && { echo "Objects still present - teardown incomplete." >&2; exit 1; } \
  || echo "events_optimized / MV / model removed. Teardown complete."
```

Run it. Paste the "reservation list is empty" and "objects removed" output into your README. **A left-running reservation is a failed teardown** — this is the one BigQuery resource that bills continuously regardless of queries.

---

## Acceptance criteria

- [ ] A repo `c18-week-10-analytics-layer-<yourhandle>` with the layout above, **built on the Week 09 dataset** (or the documented synthetic fallback, with a note explaining why).
- [ ] `events_optimized` is **partitioned by `DATE(event_time)`**, **clustered by `tenant_id, event_type`**, with `require_partition_filter = TRUE`; confirmed via `INFORMATION_SCHEMA.PARTITIONS`.
- [ ] `scripts/prove_pruning.sh` shows a one-day query scanning < 5% of the table (partition prune) and at least one query where billed < dry-run (cluster prune).
- [ ] `daily_tenant_rollup` materialized view exists, and `scripts/confirm_mv_rewrite.sh` proves the optimizer **rewrote a base-table query to read the MV** (bytes-billed evidence).
- [ ] `conversion_model` is trained; `ML.EVALUATE` output (with roc_auc) is pasted in the README; `ML.PREDICT` runs and returns predictions on recent events.
- [ ] A **cost decision** section: on-demand vs. 100-slot reservation for the refresh, with break-even and recommendation, numbers from `INFORMATION_SCHEMA.JOBS`.
- [ ] `notes/trino-iceberg-comparison.md` covers the mapping, one query's operational comparison, and an honest verdict.
- [ ] A second `terraform apply` reports `No changes` (idempotent).
- [ ] `scripts/teardown.sh` runs; the README shows the **reservation list empty** and the analytics objects gone.
- [ ] No long-lived service-account keys; `gcloud auth application-default login` only.

---

## Rubric

| Criterion | Weight | What "great" looks like |
|-----------|-------:|-------------------------|
| Built on Week 09 | 15% | Extends the real pipeline's table; the inheritance is documented, not faked |
| Partition + cluster correctness | 20% | Right keys for the workload; `require_partition_filter` on; pruning proven with bytes |
| Materialized view | 20% | MV exists, `max_staleness` set sensibly, and the **automatic rewrite is proven** in the plan |
| BQML model | 20% | Trained, evaluated (roc_auc reported), predicts; train/predict windows are partition-pruned |
| Cost decision | 10% | On-demand vs. reservation with break-even and a numbers-backed recommendation |
| Trino+Iceberg note | 5% | Honest mapping + operational comparison + a defensible verdict |
| Teardown | 10% | Clean destroy; **reservation confirmed deleted**; Week 09 pipeline untouched |

---

## Synthetic fallback loader (only if Week 09 is unrecoverable)

Run this once to create an `events.raw_events` table with believable data, then proceed as above. This is the *fallback* — extending Week 09 is the intended path.

```sql
CREATE SCHEMA IF NOT EXISTS events;

CREATE OR REPLACE TABLE `events.raw_events` AS
SELECT
  GENERATE_UUID()                                            AS event_id,
  TIMESTAMP_SUB(CURRENT_TIMESTAMP(),
                INTERVAL CAST(RAND() * 90 * 24 * 3600 AS INT64) SECOND) AS event_time,
  CONCAT('tenant_', CAST(CAST(RAND() * 20 AS INT64) AS STRING))         AS tenant_id,
  ['view', 'click', 'add_to_cart', 'purchase'][OFFSET(CAST(RAND() * 4 AS INT64))] AS event_type,
  ROUND(RAND() * 200, 2)                                     AS amount,
  ['Mozilla/5.0', 'curl/8.0', 'okhttp/4.0'][OFFSET(CAST(RAND() * 3 AS INT64))]    AS user_agent
FROM UNNEST(GENERATE_ARRAY(1, 500000)) AS n;   -- 500k synthetic events over 90 days
```

500k rows over 90 days gives you ~5,500 rows/day across 20 tenants — enough for partition pruning, cluster pruning, an MV that aggregates meaningfully, and a model with a non-trivial (if mediocre) ROC-AUC.

---

## What this prepares you for (the compounding forward)

- **Week 11 — databases.** You will contrast this scan-the-world analytics table against a Spanner row-indexed transactional store. The "BigQuery for analytics, Spanner for serving" split is the whole reason they are taught back to back.
- **Week 13 — observability.** You will route Cloud Logging to a **BigQuery log sink** and query it with exactly the partition/cluster/`INFORMATION_SCHEMA` skills from this week. Logs are events; this table shape is the log-analytics shape.
- **Week 14 — FinOps.** You will analyze the **billing export in BigQuery** — and the bytes-billed / `INFORMATION_SCHEMA.JOBS` discipline you built this week is the exact tool you use to find the team running the \$2000 query.
- **Capstone.** The capstone's Dataflow pipeline writes to a BigQuery table "partitioned by event time, clustered by tenant" — this mini-project *is* that table, one week early.

---

## Submission

1. Push the repo with a public URL.
2. Ensure the README has: the Week 09 inheritance note, the pruning proof, the MV-rewrite proof, the `ML.EVALUATE` output, the cost decision, the Trino+Iceberg note, and the teardown verification (reservation empty + objects gone).
3. Confirm a fresh clone can `init`/`apply` against documented variables and that `teardown.sh` cleanly destroys with no reservation left.
4. Post the repo URL in your cohort tracker. **Keep the Week 09 pipeline** — Week 13 routes logs into this same analytics pattern.
