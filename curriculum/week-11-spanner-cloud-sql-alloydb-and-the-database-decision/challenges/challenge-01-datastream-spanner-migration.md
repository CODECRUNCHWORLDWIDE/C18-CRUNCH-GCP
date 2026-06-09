# Challenge 1 — Cloud SQL → Spanner Migration with a Shadow-Test (and a Teardown Before Bed)

> **Estimated time:** 2.5–3.5 hours. **Cost:** ~\$3–4 if you tear Spanner and the Dataflow job down inside the window. Worth more than its time-cost suggests: this is the exact shape of a real, money-on-the-line, prove-it-correct database migration.

You will migrate a Cloud SQL for PostgreSQL database into a **single-region** Spanner instance using **Datastream** (change-data-capture) feeding the **Datastream→Spanner Dataflow template**, then run a **30-minute parallel read shadow-test** that proves the two databases return the same answers under live reads, and finally **tear the Spanner instance down before bed** with the billing alert confirmed.

This is open-ended. There is no starter repo and no solution file. You assemble it from Lecture 1 (Spanner schema), Lecture 2 (why you'd do this at all), Exercises 1 and 2 (Cloud SQL + Spanner mechanics), and the docs. The acceptance criteria below are the contract.

## The scenario

The mini-project's "current-state" service is outgrowing single-region Cloud SQL: a second team in Europe needs authoritative, low-staleness reads, and the product owner has asked "could we be on Spanner?" Before you commit a quarter to it, you run a **single-region** dress rehearsal: migrate the data, prove the reads match, measure the write-latency difference (the commit-wait from Lecture 2 is real and you will feel it), and report. Single-region keeps the bill under \$5; the multi-region version is the capstone stretch goal.

## What you build

```
Cloud SQL Postgres (source, seeded)
   │  logical replication (CDC)
   ▼
Datastream stream  ──► writes change events to GCS (or directly feeds Dataflow)
   │
   ▼
Dataflow job (Datastream-to-Spanner template)
   │
   ▼
Spanner (single-region, 100 PU, target schema)
   ▲
   │  parallel read shadow-test (your Python harness reads BOTH, compares)
Cloud SQL (still serving) ◄─┘
```

## Step-by-step outline (assemble the details yourself)

### 1. The source: Cloud SQL Postgres with seeded data

Reuse the Exercise 1 Terraform (HA optional here; `ZONAL` is fine for the source to save cost), but **enable logical replication** — Datastream needs it. On Cloud SQL Postgres you set the `cloudsql.logical_decoding` flag and create a publication + replication slot:

```hcl
settings {
  tier              = "db-custom-2-7680"
  availability_type = "ZONAL"
  database_flags {
    name  = "cloudsql.logical_decoding"
    value = "on"
  }
  # ... ip_configuration with PSC as in Exercise 1 ...
}
```

Seed two tables that map cleanly to a Spanner schema — reuse the `Customers` / `Orders` shape from Exercise 2 (UUID keys so you do not build a hotspot in Spanner). Insert ~10,000 customers and ~50,000 orders so the migration has real volume. Then create the Datastream prerequisites in Postgres:

```sql
-- On the Cloud SQL Postgres source:
CREATE PUBLICATION datastream_pub FOR ALL TABLES;
SELECT pg_create_logical_replication_slot('datastream_slot', 'pgoutput');
-- Grant the Datastream user REPLICATION and SELECT.
CREATE USER datastream_user WITH REPLICATION LOGIN PASSWORD '...';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO datastream_user;
```

### 2. The target: single-region Spanner with the translated schema

Create a 100-PU `regional-us-central1` instance (reuse Exercise 2's pattern — including its teardown guard, you will need it). Create the database with the **Spanner** DDL (GoogleSQL or the PostgreSQL dialect). The schema-translation gotchas to handle:

- Postgres `SERIAL` / `BIGSERIAL` → there is no auto-increment in Spanner; you migrated UUID keys precisely to avoid this.
- Postgres `numeric`/`decimal` → Spanner `NUMERIC` (note the precision rules) or store cents as `INT64` (recommended; you already did).
- Postgres `timestamptz` → Spanner `TIMESTAMP` (UTC).
- Foreign keys / parent-child → `INTERLEAVE IN PARENT` where the access pattern justifies it.

The Spanner migration tool (HarbourBridge) can generate a first-draft Spanner DDL from your Postgres schema; treat its output as a draft you review, not as gospel.

### 3. The pipe: Datastream + the Dataflow template

Create a Datastream **connection profile** for the Postgres source (over the PSC private connectivity from Exercise 1 — Datastream reaches Cloud SQL privately) and a **GCS** destination connection profile. Create the **stream**. Then launch the **Datastream-to-Spanner Dataflow template**, pointing it at the GCS path Datastream writes to and at your Spanner database. The template applies the change events (inserts/updates/deletes) into Spanner continuously.

```bash
gcloud dataflow flex-template run "datastream-to-spanner-$(date +%s)" \
  --template-file-gcs-location="gs://dataflow-templates/latest/flex/Cloud_Datastream_to_Spanner" \
  --region=us-central1 \
  --parameters="inputFilePattern=gs://YOUR_BUCKET/datastream/,streamName=projects/PROJECT/locations/us-central1/streams/YOUR_STREAM,instanceId=wk11-spanner-lab,databaseId=current-state,projectId=PROJECT" \
  --max-workers=2 --num-workers=1
```

Keep `--max-workers=2` so the Dataflow bill stays small. Watch the job in the console until the backlog drains and the row counts in Spanner match the source.

### 4. The proof: a 30-minute parallel read shadow-test

This is the part that distinguishes a migration from a hope. Write a Python harness that, for 30 minutes, repeatedly:

1. Picks a random `CustomerId` that exists in the source.
2. Runs the *same logical query* against Cloud SQL (via `psycopg`) and against Spanner (via `google-cloud-spanner`): e.g. "this customer's order count and total cents."
3. Compares the two results. Logs any mismatch with the key and both values.
4. While reads run, a separate writer thread inserts new orders into Cloud SQL so the CDC pipe is exercised live — and the shadow-test must show Spanner *converging* to the new rows within the replication lag.

Skeleton (fill in the connection details and the loop):

```python
import random, time, psycopg
from google.cloud import spanner

def cloud_sql_summary(conn, customer_id: str) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(total_cents),0) "
            "FROM orders WHERE customer_id = %s",
            (customer_id,),
        )
        n, total = cur.fetchone()
        return int(n), int(total)

def spanner_summary(database, customer_id: str) -> tuple[int, int]:
    with database.snapshot() as snap:
        rows = list(snap.execute_sql(
            "SELECT COUNT(*) AS n, IFNULL(SUM(TotalCents),0) AS total "
            "FROM Orders WHERE CustomerId = @cid",
            params={"cid": customer_id},
            param_types={"cid": spanner.param_types.STRING},
        ))
        n, total = rows[0]
        return int(n), int(total)

# Run for 30 minutes: sample keys, compare, count matches/mismatches,
# allow a bounded convergence window for rows written during the test.
```

Report: total comparisons, exact matches, mismatches that *never* converged (these are real bugs), and the median/95p convergence lag for rows written during the window.

### 5. Measure the commit-wait (Lecture 2 made real)

Time a single-row write to Cloud SQL vs a single-row write to Spanner, 100 each, report the median. Spanner's write will be a few milliseconds slower — that is the TrueTime commit-wait you read about. Note the number; it is the cost of external consistency.

### 6. TEARDOWN before bed (graded)

```bash
# Cancel the Dataflow job FIRST (it bills per worker-hour).
gcloud dataflow jobs cancel JOB_ID --region=us-central1

# Delete the Datastream stream and connection profiles.
gcloud datastream streams delete YOUR_STREAM --location=us-central1
gcloud datastream connection-profiles delete SOURCE_PROFILE --location=us-central1
gcloud datastream connection-profiles delete GCS_PROFILE --location=us-central1

# Delete the Spanner instance (this is the expensive one).
python ../exercises/exercise-02-spanner-interleaved-schema.py --project PROJECT --teardown-only
#   ... or: gcloud spanner instances delete wk11-spanner-lab

# Tear down the Cloud SQL source.
terraform -chdir=source destroy -var=...
```

Verify and screenshot:

```bash
gcloud spanner instances list          # EMPTY
gcloud dataflow jobs list --status=active --region=us-central1   # no active jobs
gcloud datastream streams list --location=us-central1            # empty
gcloud billing budgets list --billing-account=$BILLING_ACCOUNT_ID  # alert ARMED
```

## Acceptance criteria

- [ ] A Cloud SQL Postgres source exists with `cloudsql.logical_decoding = on`, a publication, a replication slot, and ≥10,000 customers / ≥50,000 orders seeded.
- [ ] A Datastream stream captures changes from the source over **private** connectivity (PSC — no public IP on the source).
- [ ] A Dataflow Datastream-to-Spanner job lands the data into a **single-region** (`regional-us-central1`) Spanner instance with a schema that uses UUID keys and at least one `INTERLEAVE IN PARENT` table.
- [ ] Row counts in Spanner match the source (`Customers` and `Orders`) after the backlog drains.
- [ ] The 30-minute shadow-test ran, sampling ≥1,000 comparisons, and reports **zero non-converging mismatches** (rows written during the test may lag, but must converge within a bounded window you state).
- [ ] You report the Spanner-vs-Cloud-SQL single-row write-latency difference (the commit-wait) with a number.
- [ ] **Teardown verified:** `gcloud spanner instances list` is empty, no active Dataflow job, the Datastream stream is deleted, and the budget alert is still armed. Include the command output (or a screenshot) in your writeup.
- [ ] A `results.md` (300–500 words) covers: the schema-translation gotchas you hit, the shadow-test numbers (comparisons / matches / convergence lag), the write-latency delta, and a one-paragraph verdict: *would you actually migrate this workload to Spanner, and why?*

## Hints

1. **Datastream needs logical replication AND a replication slot.** If the stream errors with "could not find replication slot," you skipped `pg_create_logical_replication_slot`. The Datastream Postgres-source doc has the exact grant list.
2. **The Dataflow template reads from GCS** in the GCS-destination topology; make sure the bucket path you pass matches Datastream's actual output prefix. A common failure is an empty job because the prefix is wrong.
3. **Spanner DML vs mutations.** The Dataflow template uses mutations (the fast path); your shadow-test reads should use a `snapshot()` (read-only, no locks) so you do not add write contention while measuring.
4. **Convergence, not instant equality.** CDC is asynchronous. Rows written to Cloud SQL during the test appear in Spanner after a lag (seconds, usually). Your shadow-test must distinguish "lagging, will converge" from "diverged, a bug." Sample a key, and if it mismatches, re-check it a few seconds later before logging a real mismatch.
5. **Cancel Dataflow FIRST in teardown.** A streaming Dataflow job keeps workers alive and keeps billing even after you delete the Spanner target (the job then just errors, still billing). Cancel the job before anything else.
6. **The commit-wait is small but real.** Do not expect Spanner to be dramatically slower per write — expect single-digit-millisecond added latency. If your number is huge (100ms+), you are probably measuring cross-region network, not the commit-wait; confirm your client is in the same region as the Spanner instance.

## Going further (no extra grade, no time pressure)

- Run the shadow-test against a **multi-region** Spanner config (`nam3`) for 10 minutes and compare write latency to the single-region run. This is the genuinely expensive config — budget for it, and tear it down even faster.
- Add a **deletes** case: delete a customer in Cloud SQL and confirm the `ON DELETE CASCADE` interleave removes the customer *and* their orders in Spanner via the CDC pipe.
- Write the **rollback plan**: if the migration shadow-test had failed, what is the exact sequence to abandon Spanner and stay on Cloud SQL with zero data loss? (Hint: you never cut over until the shadow-test is green; the rollback is "stop the Dataflow job, delete Spanner, done" — because Cloud SQL never stopped being authoritative.)

## Submission

Commit to your Week 11 GitHub repository at `challenges/challenge-01-migration/` containing:

- `source/` — the Cloud SQL source Terraform.
- `spanner/` — the Spanner schema DDL and the create/teardown script (or a reference to Exercise 2's).
- `datastream/` — the gcloud commands or Terraform for the stream and connection profiles.
- `shadow_test.py` — the parallel read harness.
- `results.md` — the writeup with the numbers and the teardown verification.

A submission whose shadow-test shows zero non-converging mismatches **and** whose teardown verification is present is a pass. The most common review-fail is a `results.md` that claims success but whose teardown evidence is missing — meaning a Spanner instance may still be billing. Verify before submitting.

---

**References**

- Datastream — PostgreSQL source configuration: <https://cloud.google.com/datastream/docs/configure-your-source-postgresql-database>
- Datastream-to-Spanner Dataflow template: <https://cloud.google.com/dataflow/docs/guides/templates/provided/datastream-to-spanner>
- Cloud SQL → Spanner migration guide: <https://cloud.google.com/spanner/docs/migrating-postgres-spanner>
- Spanner migration tool (HarbourBridge): <https://github.com/GoogleCloudPlatform/spanner-migration-tool>
- Spanner — read-only transactions (snapshots): <https://cloud.google.com/spanner/docs/transactions#read-only_transactions>
- Spanner — TrueTime and external consistency (why the write is slower): <https://cloud.google.com/spanner/docs/true-time-external-consistency>
