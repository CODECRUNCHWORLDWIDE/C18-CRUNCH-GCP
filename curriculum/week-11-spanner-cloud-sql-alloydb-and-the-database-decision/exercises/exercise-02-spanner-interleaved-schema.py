#!/usr/bin/env python3
"""Exercise 2 - Spanner: an interleaved schema, up and down within the hour.

Goal: Stand up a 100-PU single-region Spanner instance, create a Customers/Orders
      interleaved schema, write and read rows, then TEAR IT DOWN. The whole
      lifecycle runs in one process so you cannot forget the teardown.

      Spanner bills by the hour. A 100-PU regional instance is ~$0.09-0.13/hour.
      This script prints elapsed time and refuses to exit without offering to
      delete the instance.

Estimated time: 60 minutes. Cost: < $2 if run in one sitting.

PREREQUISITES
  - A GCP project with billing enabled and a $10 budget alert ARMED.
  - The Spanner API enabled:
        gcloud services enable spanner.googleapis.com
  - Application Default Credentials:
        gcloud auth application-default login
  - The Python client:
        pip install google-cloud-spanner==3.49.0

HOW TO RUN
  Full lifecycle (create -> schema -> write -> read -> teardown prompt):
        python exercise-02-spanner-interleaved-schema.py --project YOUR_PROJECT

  Force teardown of a leftover instance (the safety net if a previous run died):
        python exercise-02-spanner-interleaved-schema.py --project YOUR_PROJECT --teardown-only

  Skip the interactive prompt and auto-delete at the end (CI / disciplined use):
        python exercise-02-spanner-interleaved-schema.py --project YOUR_PROJECT --auto-teardown

ACCEPTANCE CRITERIA
  [ ] A 100-PU regional instance is created in regional-us-central1.
  [ ] The Customers table uses a UUID primary key (no monotonic-key hotspot).
  [ ] The Orders table is INTERLEAVE IN PARENT Customers ON DELETE CASCADE.
  [ ] You write 3 customers and several interleaved orders, then read them back.
  [ ] At the end, `gcloud spanner instances list` shows NO wk11-* instance.

SMOKE OUTPUT (abridged)
  [00:00] Creating instance wk11-spanner-lab (100 PU, regional-us-central1) ...
  [00:42] Instance ready.
  [00:43] Creating database current-state with interleaved schema ...
  [01:05] Schema applied (2 tables, 1 interleave).
  [01:06] Inserted 3 customers, 5 orders.
  [01:06] Customer 'Ada Corp' has 2 orders totalling $137.50
  ...
  [01:08] TEARDOWN: deleting instance wk11-spanner-lab ... done.
  [01:08] Verified: instance no longer exists. Bill stops here.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import datetime, timezone

from google.api_core import exceptions as gax_exceptions
from google.cloud import spanner
from google.cloud.spanner_admin_instance_v1.types import spanner_instance_admin

INSTANCE_ID = "wk11-spanner-lab"
DATABASE_ID = "current-state"
# regional-us-central1 is a single-region config: cheapest, no multi-region premium.
INSTANCE_CONFIG = "regional-us-central1"
PROCESSING_UNITS = 100  # the smallest billable capacity. 1000 PU = 1 node.

# DDL is GoogleSQL dialect. Note: STRING(N), no SERIAL, explicit PRIMARY KEY,
# and the INTERLEAVE IN PARENT clause that co-locates child rows with parents.
SCHEMA_DDL = [
    """
    CREATE TABLE Customers (
        CustomerId STRING(36) NOT NULL,
        Name       STRING(256) NOT NULL,
        CreatedAt  TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
    ) PRIMARY KEY (CustomerId)
    """,
    """
    CREATE TABLE Orders (
        CustomerId STRING(36) NOT NULL,
        OrderId    STRING(36) NOT NULL,
        TotalCents INT64 NOT NULL,
        PlacedAt   TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
    ) PRIMARY KEY (CustomerId, OrderId),
      INTERLEAVE IN PARENT Customers ON DELETE CASCADE
    """,
]

_START = time.monotonic()


def stamp() -> str:
    """Elapsed mm:ss since the script started, so you watch the billing clock."""
    elapsed = int(time.monotonic() - _START)
    return f"[{elapsed // 60:02d}:{elapsed % 60:02d}]"


def log(msg: str) -> None:
    print(f"{stamp()} {msg}", flush=True)


def create_instance(client: spanner.Client) -> spanner.instance.Instance:
    instance = client.instance(
        INSTANCE_ID,
        configuration_name=f"projects/{client.project}/instanceConfigs/{INSTANCE_CONFIG}",
        display_name="Week 11 Spanner lab (TEAR ME DOWN)",
        processing_units=PROCESSING_UNITS,
    )
    log(f"Creating instance {INSTANCE_ID} ({PROCESSING_UNITS} PU, {INSTANCE_CONFIG}) ...")
    operation = instance.create()
    operation.result(timeout=300)  # block until the instance is ready
    log("Instance ready.")
    return instance


def create_database(instance: spanner.instance.Instance) -> spanner.database.Database:
    log(f"Creating database {DATABASE_ID} with interleaved schema ...")
    database = instance.database(DATABASE_ID, ddl_statements=SCHEMA_DDL)
    operation = database.create()
    operation.result(timeout=300)
    log("Schema applied (2 tables, 1 interleave).")
    return database


def seed_data(database: spanner.database.Database) -> dict[str, str]:
    """Insert 3 customers and several interleaved orders. Returns name -> id map."""
    customers = [
        (str(uuid.uuid4()), "Ada Corp"),
        (str(uuid.uuid4()), "Babbage LLC"),
        (str(uuid.uuid4()), "Turing Inc"),
    ]
    name_to_id = {name: cid for cid, name in customers}

    # Orders keyed by (customer_id, order_id). TotalCents in cents to avoid float.
    orders = [
        (name_to_id["Ada Corp"], str(uuid.uuid4()), 9999),
        (name_to_id["Ada Corp"], str(uuid.uuid4()), 3751),
        (name_to_id["Babbage LLC"], str(uuid.uuid4()), 12000),
        (name_to_id["Turing Inc"], str(uuid.uuid4()), 500),
        (name_to_id["Turing Inc"], str(uuid.uuid4()), 4200),
    ]

    def _write(transaction: spanner.transaction.Transaction) -> None:
        transaction.insert(
            table="Customers",
            columns=("CustomerId", "Name", "CreatedAt"),
            values=[
                (cid, name, spanner.COMMIT_TIMESTAMP) for cid, name in customers
            ],
        )
        transaction.insert(
            table="Orders",
            columns=("CustomerId", "OrderId", "TotalCents", "PlacedAt"),
            values=[
                (cid, oid, cents, spanner.COMMIT_TIMESTAMP)
                for cid, oid, cents in orders
            ],
        )

    database.run_in_transaction(_write)
    log(f"Inserted {len(customers)} customers, {len(orders)} orders.")
    return name_to_id


def read_back(database: spanner.database.Database) -> None:
    """A single-split read per customer thanks to INTERLEAVE: customer + its orders."""
    sql = """
        SELECT c.Name, COUNT(o.OrderId) AS num_orders, SUM(o.TotalCents) AS total_cents
        FROM Customers AS c
        LEFT JOIN Orders AS o ON c.CustomerId = o.CustomerId
        GROUP BY c.Name
        ORDER BY c.Name
    """
    with database.snapshot() as snapshot:
        rows = snapshot.execute_sql(sql)
        for name, num_orders, total_cents in rows:
            total = (total_cents or 0) / 100.0
            log(f"Customer '{name}' has {num_orders} orders totalling ${total:0.2f}")


def teardown(client: spanner.Client) -> None:
    instance = client.instance(INSTANCE_ID)
    log(f"TEARDOWN: deleting instance {INSTANCE_ID} ...")
    try:
        instance.delete()  # deleting the instance deletes its databases too
    except gax_exceptions.NotFound:
        log("Instance already gone.")
        return
    # Verify it is actually gone. The bill stops when the instance is deleted.
    for attempt in range(10):
        try:
            instance.reload()
            time.sleep(2)
        except gax_exceptions.NotFound:
            log("Verified: instance no longer exists. Bill stops here.")
            return
    log("WARNING: instance still appears to exist. Run with --teardown-only and "
        "check `gcloud spanner instances list` immediately.")


def confirm_teardown(auto: bool) -> bool:
    if auto:
        return True
    log("The instance is still running and BILLING.")
    answer = input(f"{stamp()} Delete instance '{INSTANCE_ID}' now? [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Spanner interleaved-schema lab with teardown guard.")
    p.add_argument("--project", required=True, help="GCP project ID.")
    p.add_argument("--teardown-only", action="store_true",
                   help="Skip the lab; just delete any leftover wk11 instance.")
    p.add_argument("--auto-teardown", action="store_true",
                   help="Delete the instance at the end without prompting.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    client = spanner.Client(project=args.project)

    if args.teardown_only:
        teardown(client)
        return 0

    instance = None
    try:
        instance = create_instance(client)
        database = create_database(instance)
        seed_data(database)
        read_back(database)
    except Exception as exc:  # noqa: BLE001 - we want to ALWAYS reach teardown
        log(f"ERROR during lab: {exc!r}")
        log("Proceeding to teardown anyway so you are not billed for a broken run.")
    finally:
        # The teardown ALWAYS runs. This is the guard: a failed lab still tears down.
        if confirm_teardown(args.auto_teardown):
            teardown(client)
        else:
            log("You chose NOT to tear down. The instance is STILL BILLING.")
            log("Tear it down with: "
                f"python {sys.argv[0]} --project {args.project} --teardown-only")
            log(f"Or: gcloud spanner instances delete {INSTANCE_ID}")
            return 1
    return 0


if __name__ == "__main__":
    # A tiny sanity print so nobody runs this thinking it is free.
    print(f"[{datetime.now(timezone.utc).isoformat()}] Spanner lab starting. "
          "This creates a BILLABLE instance. Ctrl-C now if you have not armed a budget alert.")
    sys.exit(main())
