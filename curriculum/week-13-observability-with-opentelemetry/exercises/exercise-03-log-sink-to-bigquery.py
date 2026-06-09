#!/usr/bin/env python3
"""
Exercise 3 — Route logs to a BigQuery sink and query them for an error pattern.

Goal: Create a Cloud Logging sink that routes a filtered slice of logs to a
      BigQuery dataset, emit a structured error pattern (a burst of
      severity=ERROR logs with a shared error_code), wait for them to land,
      then query BigQuery in SQL to find the pattern. This is the syllabus
      skill: "Route logs to a BigQuery sink and query them."

Estimated time: 45 minutes.

HOW TO USE THIS FILE

  1. Install deps:
       pip install "google-cloud-logging==3.11.*" "google-cloud-bigquery==3.25.*"
  2. Set up auth:
       export GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"
       gcloud auth application-default login
  3. Fill in the TWO TODOs below.
  4. Run:
       python exercise-03-log-sink-to-bigquery.py --create   # make sink + dataset
       python exercise-03-log-sink-to-bigquery.py --emit      # emit the error burst
       # wait ~2 minutes for the router to land logs in BigQuery
       python exercise-03-log-sink-to-bigquery.py --query     # find the pattern
       python exercise-03-log-sink-to-bigquery.py --teardown  # delete sink + dataset

ACCEPTANCE CRITERIA
  [ ] A logging sink routing severity>=ERROR for log name "ex03-app" to a
      BigQuery dataset exists.
  [ ] The sink's writer-identity service account has roles/bigquery.dataEditor
      on the dataset (otherwise the router silently drops everything).
  [ ] After --emit and a short wait, the BigQuery dataset has a table with the
      error rows.
  [ ] The --query step returns the injected error_code with the right count.
  [ ] --teardown removes the sink and the dataset (no leak).

SMOKE OUTPUT (target)
  $ python exercise-03-log-sink-to-bigquery.py --query
  error_code        | n
  ------------------+----
  E_PAYMENT_DECLINED| 25
"""

import argparse
import logging as pylogging
import os
import sys
import time

import google.cloud.logging as cloud_logging
from google.cloud import bigquery
from google.cloud.logging_v2 import Client as LoggingClient
from google.cloud.logging_v2.sink import Sink

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
DATASET = "ex03_logs"
SINK_NAME = "ex03-error-sink"
LOG_NAME = "ex03-app"
ERROR_CODE = "E_PAYMENT_DECLINED"
ERROR_BURST = 25


# -----------------------------------------------------------------------------
# create: make the BigQuery dataset, the sink, and grant the writer identity.
# -----------------------------------------------------------------------------
def create() -> None:
    bq = bigquery.Client(project=PROJECT)
    dataset_ref = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    dataset_ref.location = "US"
    bq.create_dataset(dataset_ref, exists_ok=True)
    print(f"dataset ready: {PROJECT}.{DATASET}")

    logging_client: LoggingClient = cloud_logging.Client(project=PROJECT)

    # TODO 1 — Construct the sink.
    #   - destination must be the BigQuery dataset in the form:
    #       "bigquery.googleapis.com/projects/{PROJECT}/datasets/{DATASET}"
    #   - filter must select only severity>=ERROR for our log:
    #       'logName="projects/{PROJECT}/logs/{LOG_NAME}" AND severity>=ERROR'
    #   Then call sink.create() (idempotent guard with exists check).
    destination = ""  # <-- replace (TODO 1)
    log_filter = ""   # <-- replace (TODO 1)

    sink = Sink(SINK_NAME, parent=f"projects/{PROJECT}", filter_=log_filter,
                destination=destination, client=logging_client)
    if not sink.exists():
        sink.create(unique_writer_identity=True)
    else:
        sink.reload()
    print(f"sink ready: {SINK_NAME}")
    print(f"writer identity: {sink.writer_identity}")

    # The router writes as the sink's writer-identity SA. It needs dataEditor
    # on the dataset or it silently drops every routed log. This is THE classic
    # "my sink does nothing" bug.
    _grant_writer(bq, sink.writer_identity)
    print("granted roles/bigquery.dataEditor to the writer identity")


def _grant_writer(bq: bigquery.Client, writer_identity: str) -> None:
    dataset = bq.get_dataset(f"{PROJECT}.{DATASET}")
    entries = list(dataset.access_entries)
    entries.append(
        bigquery.AccessEntry(
            role="WRITER",
            entity_type="userByEmail",
            # writer_identity looks like "serviceAccount:p123-...@gcp-sa-logging..."
            entity_id=writer_identity.split(":", 1)[1],
        )
    )
    dataset.access_entries = entries
    bq.update_dataset(dataset, ["access_entries"])


# -----------------------------------------------------------------------------
# emit: write a burst of structured ERROR logs that match the sink filter.
# -----------------------------------------------------------------------------
def emit() -> None:
    logging_client: LoggingClient = cloud_logging.Client(project=PROJECT)
    gcp_logger = logging_client.logger(LOG_NAME)

    # A few benign INFO logs (these will NOT be routed — the filter is >=ERROR).
    for i in range(5):
        gcp_logger.log_struct(
            {"message": "healthy request", "error_code": None},
            severity="INFO",
        )

    # The error burst (these WILL be routed to BigQuery).
    for i in range(ERROR_BURST):
        gcp_logger.log_struct(
            {
                "message": "payment declined by processor",
                "error_code": ERROR_CODE,
                "tenant_id": f"tenant-{i % 4}",
                "amount_cents": 1999 + i,
            },
            severity="ERROR",
        )
    print(f"emitted {ERROR_BURST} ERROR logs (code={ERROR_CODE}) and 5 INFO logs")
    print("wait ~2 minutes for the log router to land them in BigQuery, then --query")


# -----------------------------------------------------------------------------
# query: find the error pattern in the BigQuery-landed logs.
# -----------------------------------------------------------------------------
def query() -> None:
    bq = bigquery.Client(project=PROJECT)

    # Routed logs land in a date-sharded table named after the log id, e.g.
    # `ex03_app_YYYYMMDD`. Cloud Logging replaces non-alnum chars in the log
    # name with underscores. We use a wildcard table to span any shard.
    #
    # TODO 2 — Write the SQL. Count rows grouped by the structured field
    #   jsonPayload.error_code, for severity = 'ERROR', from the wildcard table
    #   `{PROJECT}.{DATASET}.ex03_app_*`. Order by the count descending.
    #
    #   Hint: structured fields land under the `jsonPayload` RECORD column, so
    #   the field is  jsonPayload.error_code . Filter  WHERE severity = 'ERROR'.
    sql = ""  # <-- replace (TODO 2)

    print("error_code        | n")
    print("------------------+----")
    for row in bq.query(sql).result():
        print(f"{(row['error_code'] or 'NULL'):<18}| {row['n']}")


# -----------------------------------------------------------------------------
# teardown: delete the sink and the dataset so nothing keeps ingesting/charging.
# -----------------------------------------------------------------------------
def teardown() -> None:
    logging_client: LoggingClient = cloud_logging.Client(project=PROJECT)
    sink = Sink(SINK_NAME, parent=f"projects/{PROJECT}", client=logging_client)
    if sink.exists():
        sink.delete()
        print(f"deleted sink: {SINK_NAME}")
    bq = bigquery.Client(project=PROJECT)
    bq.delete_dataset(f"{PROJECT}.{DATASET}", delete_contents=True, not_found_ok=True)
    print(f"deleted dataset: {PROJECT}.{DATASET}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise 3 — BigQuery log sink")
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--emit", action="store_true")
    parser.add_argument("--query", action="store_true")
    parser.add_argument("--teardown", action="store_true")
    args = parser.parse_args()

    if args.create:
        create()
    elif args.emit:
        emit()
    elif args.query:
        query()
    elif args.teardown:
        teardown()
    else:
        parser.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())


###############################################################################
# REFERENCE SOLUTION — do not read until your version runs.
#
# TODO 1:
#   destination = f"bigquery.googleapis.com/projects/{PROJECT}/datasets/{DATASET}"
#   log_filter  = (
#       f'logName="projects/{PROJECT}/logs/{LOG_NAME}" AND severity>=ERROR'
#   )
#
# TODO 2:
#   sql = f"""
#       SELECT jsonPayload.error_code AS error_code, COUNT(*) AS n
#       FROM `{PROJECT}.{DATASET}.ex03_app_*`
#       WHERE severity = 'ERROR'
#       GROUP BY error_code
#       ORDER BY n DESC
#   """
#
# Why the wildcard table: the log router creates one table per UTC day, named
# `ex03_app_YYYYMMDD` (the log id `ex03-app` with the hyphen replaced by an
# underscore). A wildcard `ex03_app_*` spans every shard so the query works no
# matter which day it ran. In production you partition by `timestamp` and
# query with a `_TABLE_SUFFIX` predicate to scan less (see Week 10's "scan less"
# discipline — it applies to your logs too).
###############################################################################
