#!/usr/bin/env python3
"""Exercise 3 - Read a BigQuery query plan and identify the cost-driving stage.

Goal: Practice the "find the stage that costs the money" drill from Lecture 2.
      You run a query through the Python client, pull QueryJob.query_plan (the
      job_stages you saw in INFORMATION_SCHEMA), and PROGRAMMATICALLY point at:
        (a) the SCAN stage  - the input stage that read the most records, and
        (b) any FAN-OUT stage - a stage whose output records >> input records.
      Ninety percent of cost incidents are one of those two; this script finds
      both in a second.

Estimated time: 45 minutes.

HOW TO USE THIS FILE

  1. Install the client (Python 3.11+):

         python3 -m pip install google-cloud-bigquery

     Authenticate once: `gcloud auth application-default login`.

  2. You need the `rides.trips_optimized` table from Exercise 1, in a dataset
     you own. Set PROJECT below or pass --project.

  3. Run it three ways and watch the analyzer's verdict change:

         # A) A clean, partition-pruned query - no fan-out, small scan.
         python3 exercise-03-read-the-query-plan.py --case good

         # B) A query with a deliberate self-join fan-out.
         python3 exercise-03-read-the-query-plan.py --case fanout

         # C) Bring your own SQL.
         python3 exercise-03-read-the-query-plan.py --sql "SELECT ..."

  4. The two TODOs are the heart of the exercise: implement
     `find_scan_stage` and `find_fanout_stages`. The rendering and the driver
     are provided. Fill in the TODOs so the verdict matches EXPECTED OUTPUT.

ACCEPTANCE CRITERIA

  [ ] Both TODOs implemented; the script runs for --case good and --case fanout
      with no exception.
  [ ] For --case good: the analyzer names the table-read stage as the scan and
      reports NO fan-out.
  [ ] For --case fanout: the analyzer flags the join stage as a fan-out
      (output records >> input records).
  [ ] The script prints total_bytes_billed and the est. USD for every run.

Inline hints are at the bottom of the file. Don't peek until you've tried for
at least 15 minutes.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from google.cloud import bigquery

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

PROJECT: str | None = None  # None -> use the client's default project
TABLE = "rides.trips_optimized"  # from Exercise 1
PRICE_PER_TIB_USD = 6.25  # US multi-region on-demand list (2026)

# A clean, partition-pruned query: one day, two columns, a simple aggregation.
GOOD_SQL = f"""
SELECT payment_type, COUNT(*) AS trips, SUM(total_amount) AS revenue
FROM `{{table}}`
WHERE pickup_datetime >= '2018-01-15' AND pickup_datetime < '2018-01-16'
GROUP BY payment_type
ORDER BY trips DESC
"""

# A deliberate self-join with a NON-unique key -> fan-out. We join the day's
# trips to themselves on payment_type (thousands of rows per type), so each row
# matches thousands of rows: output records >> input records.
FANOUT_SQL = f"""
SELECT a.vendor_id, COUNT(*) AS pair_count
FROM `{{table}}` AS a
JOIN `{{table}}` AS b
  ON a.payment_type = b.payment_type           -- NOT unique -> explodes
WHERE a.pickup_datetime >= '2018-01-15' AND a.pickup_datetime < '2018-01-16'
  AND b.pickup_datetime >= '2018-01-15' AND b.pickup_datetime < '2018-01-16'
GROUP BY a.vendor_id
"""


# ----------------------------------------------------------------------------
# A flattened view of one plan stage (the fields we care about)
# ----------------------------------------------------------------------------


@dataclass
class Stage:
    id: int
    name: str
    records_read: int
    records_written: int
    slot_ms: int
    reads_from_table: bool  # True if this stage reads the base table (a scan)


def flatten_plan(job: bigquery.QueryJob) -> list[Stage]:
    """Turn QueryJob.query_plan into our simple Stage list.

    The client exposes job.query_plan as a list of QueryPlanEntry objects with
    .name, .records_read, .records_written, .slot_ms, and .steps (the kinds of
    work in the stage). A stage reads the base table if any of its steps is a
    READ step that references the table (heuristic: a READ step kind).
    """
    stages: list[Stage] = []
    for i, entry in enumerate(job.query_plan or []):
        steps = entry.steps or []
        reads_from_table = any(
            (step.kind or "").upper() == "READ" for step in steps
        )
        stages.append(
            Stage(
                id=i,
                name=entry.name or f"stage-{i}",
                records_read=int(entry.records_read or 0),
                records_written=int(entry.records_written or 0),
                slot_ms=int(entry.slot_ms or 0),
                reads_from_table=reads_from_table,
            )
        )
    return stages


# ----------------------------------------------------------------------------
# Functions to implement
# ----------------------------------------------------------------------------


def find_scan_stage(stages: list[Stage]) -> Stage | None:
    """Return the stage that read the most records FROM THE TABLE (the scan).

    The "scan stage" is the input/leaf stage that pulls rows off Colossus. Among
    stages where reads_from_table is True, return the one with the largest
    records_read. If none read the table (e.g. a metadata-only query), return
    None.

    TODO: implement. Hint: filter stages to reads_from_table, then max() by
    records_read.
    """
    raise NotImplementedError


def find_fanout_stages(stages: list[Stage], ratio: float = 4.0) -> list[Stage]:
    """Return stages where output records exceed input records by >= `ratio`.

    A fan-out is a stage whose records_written is much larger than its
    records_read - the signature of a join that multiplied rows (Lecture 1 §4).
    We use a default ratio of 4x to avoid flagging benign 1:1-ish stages.

    Guard against division by zero: a stage that read 0 records but wrote many
    is a generator/cross-join source and SHOULD be flagged.

    TODO: implement. Return the matching stages sorted by ratio descending.
    """
    raise NotImplementedError


# ----------------------------------------------------------------------------
# Rendering + driver (provided - do not change)
# ----------------------------------------------------------------------------


def to_usd(bytes_billed: int) -> float:
    return bytes_billed / (2 ** 40) * PRICE_PER_TIB_USD


def run_and_analyze(client: bigquery.Client, sql: str, label: str) -> None:
    print(f"\n=== {label} ===")
    job = client.query(sql)
    job.result()  # block until done so the plan is populated

    billed = int(job.total_bytes_billed or 0)
    processed = int(job.total_bytes_processed or 0)
    print(
        f"total_bytes_processed: {processed:,}  "
        f"total_bytes_billed: {billed:,}  "
        f"est_usd: ${to_usd(billed):.6f}"
    )

    stages = flatten_plan(job)
    print(f"plan: {len(stages)} stages")
    for s in stages:
        print(
            f"  [{s.id}] {s.name:<22} read={s.records_read:>10,} "
            f"written={s.records_written:>12,} slot_ms={s.slot_ms:>9,} "
            f"{'(table scan)' if s.reads_from_table else ''}"
        )

    scan = find_scan_stage(stages)
    if scan is not None:
        print(
            f"SCAN STAGE: [{scan.id}] {scan.name} "
            f"read {scan.records_read:,} records from the table "
            f"-> this drives the bytes scanned."
        )
    else:
        print("SCAN STAGE: none (metadata-only query).")

    fanouts = find_fanout_stages(stages)
    if fanouts:
        for f in fanouts:
            blow = f.records_written / max(f.records_read, 1)
            print(
                f"FAN-OUT: [{f.id}] {f.name} wrote {f.records_written:,} "
                f"from {f.records_read:,} read ({blow:.0f}x) "
                f"-> a join multiplied rows; THIS is the cost driver."
            )
    else:
        print("FAN-OUT: none detected.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=PROJECT)
    ap.add_argument("--table", default=TABLE)
    ap.add_argument("--case", choices=["good", "fanout"], default="good")
    ap.add_argument("--sql", default=None, help="run your own SQL instead")
    args = ap.parse_args()

    client = bigquery.Client(project=args.project)

    if args.sql:
        run_and_analyze(client, args.sql, "custom SQL")
        return

    if args.case == "good":
        run_and_analyze(client, GOOD_SQL.format(table=args.table), "GOOD (pruned)")
    else:
        run_and_analyze(client, FANOUT_SQL.format(table=args.table), "FAN-OUT (self-join)")


if __name__ == "__main__":
    try:
        main()
    except NotImplementedError:
        print(
            "Implement find_scan_stage and find_fanout_stages first "
            "(see the TODOs).",
            file=sys.stderr,
        )
        sys.exit(2)


# ----------------------------------------------------------------------------
# EXPECTED OUTPUT (shape - your record counts and bytes will differ)
# ----------------------------------------------------------------------------
#
# === GOOD (pruned) ===
# total_bytes_processed: 1,234,567  total_bytes_billed: 10,485,760  est_usd: $0.000060
# plan: 3 stages
#   [0] S00: Input            read=   286,100 written=         6 slot_ms=    1,200 (table scan)
#   [1] S01: Aggregate        read=         6 written=         6 slot_ms=      300
#   [2] S02: Output           read=         6 written=         6 slot_ms=       50
# SCAN STAGE: [0] S00: Input read 286,100 records from the table -> this drives the bytes scanned.
# FAN-OUT: none detected.
#
# === FAN-OUT (self-join) ===
# total_bytes_processed: 2,469,134  total_bytes_billed: 10,485,760  est_usd: $0.000060
# plan: 5 stages
#   [0] S00: Input            read=   286,100 written=   286,100 slot_ms=    1,500 (table scan)
#   [1] S01: Input            read=   286,100 written=   286,100 slot_ms=    1,500 (table scan)
#   [2] S02: Join+            read=   572,200 written= 1,400,000,000 slot_ms=  900,000
#   [3] S03: Aggregate        read= 1,400,000,000 written=        2 slot_ms=  120,000
#   [4] S04: Output           read=         2 written=        2 slot_ms=       50
# SCAN STAGE: [0] S00: Input read 286,100 records from the table -> this drives the bytes scanned.
# FAN-OUT: [2] S02: Join+ wrote 1,400,000,000 from 572,200 read (2447x) -> a join multiplied rows; THIS is the cost driver.
#
# Note: on-demand bytes_billed for the fan-out may look SMALL (the base scan is
# small) while slot_ms is HUGE - that mismatch is exactly the fan-out fingerprint.
# On a reservation, that slot_ms is what pins your slots and starves other queries.
#
# ----------------------------------------------------------------------------
# WRITEUP (do this in a writeup.md)
# ----------------------------------------------------------------------------
#
#   1. For the fan-out case, total_bytes_billed is tiny but slot_ms is enormous.
#      Explain why bytes-billed UNDER-states the cost of a fan-out on a
#      reservation, and what number you'd watch instead (slot_ms / slot-time).
#   2. Take ONE of your Exercise 2 rewrites and one of the BAD-query variants,
#      run them through --sql, and paste the analyzer verdict for each.
#
# ----------------------------------------------------------------------------
# HINTS (read only if stuck >15 min)
# ----------------------------------------------------------------------------
#
# find_scan_stage:
#
#   def find_scan_stage(stages):
#       table_stages = [s for s in stages if s.reads_from_table]
#       if not table_stages:
#           return None
#       return max(table_stages, key=lambda s: s.records_read)
#
# find_fanout_stages:
#
#   def find_fanout_stages(stages, ratio=4.0):
#       hits = []
#       for s in stages:
#           denom = s.records_read if s.records_read > 0 else 1
#           if s.records_written / denom >= ratio and s.records_written > 0:
#               hits.append(s)
#       return sorted(hits, key=lambda s: s.records_written / max(s.records_read, 1),
#                     reverse=True)
