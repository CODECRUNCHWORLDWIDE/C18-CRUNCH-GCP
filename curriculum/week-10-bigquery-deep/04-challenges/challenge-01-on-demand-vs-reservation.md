# Challenge 1 — On-Demand vs. a 100-Slot Reservation: Recommend the Cheaper Option with Numbers

**Time estimate:** ~3 hours.

## Problem statement

You run a nightly analytics batch on a public dataset. Land the data into a partitioned-clustered table, write **five queries that each scan under 1% of the table**, then answer the question a FinOps lead will ask you in a review: **for a one-hour batch window running this work, is it cheaper on on-demand pricing or on a 100-slot BigQuery Enterprise reservation?** Recommend one, defend it with arithmetic, and state the break-even point.

This is the exact deliverable shape of the midterm and the deep-dive interview: a cost decision backed by `--dry_run` evidence and the published slot-hour rate, not by opinion.

## Setup

Use the **NYC taxi** dataset (`bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2018` and the other years) or **Wikipedia pageviews** (`bigquery-public-data.wikipedia.pageviews_*`). Pick one and stay with it.

The scenario you are costing: the batch represents a *realistic heavy night* — so you will deliberately scale the math to a **multi-TiB** workload even though your lab queries scan kilobytes. (You do **not** run multi-TiB queries; you measure the small ones and extrapolate, which is exactly how capacity planning works.)

## Requirements

### Part A — Land it right (30 min)

1. Create a dataset and a table `taxi.trips` (or `wiki.pageviews`) that is:
   - **Partitioned** by the event timestamp at `DAY` granularity (taxi) or `DAY`/`HOUR` (pageviews).
   - **Clustered** by two sensible columns for the workload (taxi: `payment_type, vendor_id`; pageviews: `wiki, title`).
   - Created with `require_partition_filter = TRUE`.
2. Load **at least 3 months** of data so partition pruning is meaningfully demonstrable (still well inside the free storage tier; one quarter of one year is small).
3. Confirm partitioning/clustering with `INFORMATION_SCHEMA.PARTITIONS` and `.COLUMNS` (Exercise 1 technique).

### Part B — Five queries, each <1% (60 min)

Write five distinct, *useful* analytical queries (not five trivial variations). Each must:

- Scan **under 1%** of the table's logical bytes, proven by `--dry_run` *and* confirmed by `total_bytes_billed` in `INFORMATION_SCHEMA.JOBS`.
- Use at least a partition prune; at least **two of the five** must also demonstrate a **cluster prune** (filter/group on a cluster key) where the billed bytes drop below the dry-run estimate.
- Answer a real question (e.g. daily revenue, card-vs-cash split, busiest hour, top vendors, tip-rate distribution).

Produce a table: `query | table_logical_bytes | dry_run_bytes | bytes_billed | % of table | levers`.

### Part C — The cost decision (75 min)

This is the graded core. Compute, with numbers:

1. **Scale the batch to a heavy night.** State an assumption: "in production this batch scans **T TiB** per night" (pick a defensible T — e.g. 40 TiB — and justify it from your per-query bytes × the number of queries × the production data multiple). Show the multiplication.
2. **On-demand cost** of the batch: `T TiB × $6.25/TiB`. Subtract the free 1 TiB/month only if relevant; state which.
3. **Reservation cost** of the batch: a **100-slot Enterprise reservation** at the 2026 US list autoscaling rate (~\$0.06/slot-hour). For a one-hour window: `100 × 1 × $0.06`. Then sanity-check capacity: estimate whether 100 slots can finish the batch in one hour (use the `total_slot_ms` of your measured queries, scaled to production — 100 slots deliver `100 × 3600 × 1000 = 360,000,000` slot-ms in the hour). If the batch needs more slot-ms than that, it overruns the window — say so and either raise the slot count or extend the window, and recompute.
4. **The break-even.** At what scanned-TiB does on-demand cost equal the reservation cost? Solve `T × 6.25 = reservation_cost` for T. Below that T, on-demand wins; above it, the reservation wins.
5. **The recommendation.** State which is cheaper for *this* batch, by how much, and name the one operational risk of your choice (idle-slot waste for the reservation; runaway-query exposure for on-demand).

### Part D — The teardown discipline (15 min)

If you created a real reservation to observe it:

1. Run **one** query against it, capture the `total_slot_ms`.
2. **Delete the reservation immediately** (`gcloud beta bigquery reservations delete ...` or `terraform destroy`).
3. Confirm `gcloud beta bigquery reservations list` shows none.

Document that you did this. A left-running 100-slot reservation is ~\$144/day — the exact failure the week warns about.

## Acceptance criteria

- [ ] `taxi.trips` (or `wiki.pageviews`) is partitioned + clustered with `require_partition_filter = TRUE`, holding ≥ 3 months of data, confirmed via `INFORMATION_SCHEMA`.
- [ ] Five distinct, useful queries, **each scanning < 1%** of the table, with the `query | dry_run_bytes | bytes_billed | % | levers` table filled in from real measurements.
- [ ] At least two queries show a **cluster prune** (billed < dry-run).
- [ ] A cost worksheet showing: the batch-scale assumption (with justification), the on-demand cost, the 100-slot reservation cost, a **capacity sanity-check** (does 100 slots finish in the hour?), the **break-even TiB**, and a one-line recommendation with the dollar delta.
- [ ] The recommendation names the operational risk of the chosen model.
- [ ] If a reservation was created, it is **deleted**, confirmed by `gcloud ... reservations list` returning empty.
- [ ] A `README.md` with the worksheet, the query table, and the `INFORMATION_SCHEMA.JOBS` evidence pasted in.

## A worked break-even, so you know the shape (not the answer)

```
Assume the production batch scans T = 40 TiB/night (your per-query bytes x #queries x prod multiple; show it).

On-demand:        40 TiB x $6.25/TiB                = $250.00 for the night
100-slot Enterprise reservation, 1 hour:
                  100 slots x 1 h x $0.06/slot-hour = $6.00 for the night

Capacity check:   100 slots x 3600 s x 1000 ms      = 360,000,000 slot-ms available in the hour.
                  Measured: your 5 queries used ~X slot-ms on the lab slice;
                  scaled to prod that is ~Y slot-ms. Y must be <= 360,000,000,
                  else the batch overruns and you need more slots or a longer window.

Break-even:       T_be x 6.25 = 6.00  ->  T_be = 0.96 TiB
                  i.e. once the batch scans more than ~1 TiB, the reservation is cheaper.

Recommendation:   For a 40 TiB nightly batch, RESERVE: $6 vs $250, a 40x saving.
                  Risk: the 100 slots bill 24/7 if you forget to delete them
                  (~$144/day idle); gate the reservation to the batch window only
                  (create before, delete after) or use a committed baseline + autoscaling.
```

Your numbers will differ — the point is that you *produce* numbers in exactly this shape and the grader can check the arithmetic.

## Stretch

- **Time-boxed reservation in Terraform.** Express the reservation as a `google_bigquery_reservation` with a scheduled create/destroy (or a Cloud Scheduler + Cloud Function that creates it at 02:00 and deletes it at 03:00). This is how production runs a batch reservation without paying for idle slots.
- **Autoscaling vs. baseline.** Re-do the math for a reservation with `baseline = 0, autoscale_max = 100` (pay only for slots actually used, billed per second). Compare to the flat 100-slot reservation and to on-demand. Three-way.
- **Three-year commitment discount.** Look up the 3-year commitment rate and recompute the break-even for a workload that runs every night for three years. Does the commitment change the recommendation?
- **BI Engine angle.** If this batch feeds a dashboard, estimate what a 2 GB BI Engine reservation would do to the *dashboard's* on-demand bytes (served from memory, not billed as analysis), and whether that tips the decision.

## Submission

Commit a repo `c18-week-10-cost-decision-<yourhandle>` with the landing SQL/Terraform, the five queries, the `INFORMATION_SCHEMA` evidence, and the cost worksheet README. If you created a reservation, include the proof it was deleted. The grader will read your worksheet and re-run the arithmetic; "reservations are cheaper" without the break-even fails the challenge.
