# Week 10 — Resources

Almost everything here is **free**. Google Cloud documentation is free without an account. The two papers are free PDFs from Google Research. The books listed have free chapters or are worth buying once; they are flagged. The public datasets cost nothing to store and only the bytes you scan to query — and the entire week is about scanning very few of them.

## Required reading (work it into your week)

- **BigQuery storage internals — overview** — start here; how data is stored, the Colossus/Capacitor split:
  <https://cloud.google.com/bigquery/docs/storage_overview>
- **Introduction to partitioned tables** — time and integer-range partitioning, the canonical page:
  <https://cloud.google.com/bigquery/docs/partitioned-tables>
- **Introduction to clustered tables** — the four-column limit, block pruning within a partition:
  <https://cloud.google.com/bigquery/docs/clustered-tables>
- **Query plan and timeline** — how to read `job_stages` and the execution graph; the heart of Lecture 2:
  <https://cloud.google.com/bigquery/docs/query-plan-explanation>
- **Estimate and control query costs** — the `--dry_run` discipline and the maximum-bytes-billed guardrail:
  <https://cloud.google.com/bigquery/docs/best-practices-costs>
- **`INFORMATION_SCHEMA.JOBS` view** — the view you query to find the expensive job and read `total_bytes_billed`:
  <https://cloud.google.com/bigquery/docs/information-schema-jobs>

## Pricing — read it twice, it is the failure mode

- **BigQuery pricing** — the canonical page; note on-demand analysis is priced per TiB scanned and editions are priced per slot-hour:
  <https://cloud.google.com/bigquery/pricing>
- **Compute pricing models (on-demand vs. editions)** — the decision the challenge makes you compute:
  <https://cloud.google.com/bigquery/docs/reservations-intro>
- **Estimating storage and query costs** — worked examples of how bytes-scanned becomes dollars:
  <https://cloud.google.com/bigquery/docs/estimate-costs>
- **Custom cost controls** — per-user and per-project maximum bytes billed (the safety net against the \$2000 query):
  <https://cloud.google.com/bigquery/docs/custom-quotas>

## Partitioning, clustering, and the storage model

- **Partitioning vs. clustering — when to use which** (decision guidance):
  <https://cloud.google.com/bigquery/docs/partitioned-tables#dt_partition_vs_clustering>
- **Require a partition filter** — the `require_partition_filter` guardrail that blocks accidental full scans:
  <https://cloud.google.com/bigquery/docs/managing-partitioned-tables#require-filter>
- **Manage clustered tables** — automatic re-clustering, which is free and runs in the background:
  <https://cloud.google.com/bigquery/docs/creating-clustered-tables>

## Materialized views and BI Engine

- **Introduction to materialized views** — incremental maintenance and automatic query rewrite:
  <https://cloud.google.com/bigquery/docs/materialized-views-intro>
- **Use materialized views** — the smart-tuning rewrite and how to confirm it in the plan:
  <https://cloud.google.com/bigquery/docs/materialized-views-use>
- **BI Engine overview** — the in-memory acceleration layer; reservation-based, bytes served are not billed as analysis:
  <https://cloud.google.com/bigquery/docs/bi-engine-intro>

## BigQuery ML

- **Introduction to BigQuery ML** — what model types exist and when ML-in-SQL is the right call:
  <https://cloud.google.com/bigquery/docs/bqml-introduction>
- **`CREATE MODEL` for logistic regression** — the exact syntax used in the exercises and mini-project:
  <https://cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create-glm>
- **`ML.EVALUATE`** — precision/recall/ROC-AUC for a classifier:
  <https://cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-evaluate>
- **`ML.PREDICT`** — scoring new rows; the output schema:
  <https://cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-predict>
- **End-to-end BQML logistic-regression tutorial** — the Google Analytics sample; a good template to adapt:
  <https://cloud.google.com/bigquery/docs/logistic-regression-prediction>

## The papers (free PDFs — the real internals)

- **"Dremel: Interactive Analysis of Web-Scale Datasets" (VLDB 2010)** — the original. The columnar record-shredding section is the foundation of everything BigQuery does:
  <https://research.google/pubs/pub36632/>
- **"Dremel: A Decade Later" (VLDB 2020)** — the retrospective. Explains Capacitor, the storage/compute disaggregation, embedded shuffle, and the move to Colossus. **Read this one if you only read one paper this week:**
  <https://research.google/pubs/pub49489/>
- **"Capacitor" — the columnar format** (covered in the Decade Later paper §4; no standalone paper). The key ideas: reordering rows to maximize run-length encoding, and the cost-based decision of which encoding to use per column.

## Public datasets you will use

- **BigQuery public datasets — catalog**:
  <https://cloud.google.com/bigquery/public-data>
- **NYC TLC Trips** (`bigquery-public-data.new_york_taxi_trips`) — the taxi dataset; large, time-ordered, perfect for partitioning by pickup time:
  <https://console.cloud.google.com/marketplace/product/city-of-new-york/nyc-tlc-trips>
- **Wikipedia pageviews** (`bigquery-public-data.wikipedia.pageviews_2024` and friends) — the alternative; partition by datehour, cluster by `wiki` + `title`:
  <https://console.cloud.google.com/marketplace/product/bigquery-public-data/wikipedia>

## `bq` CLI and the API

- **`bq` command-line tool reference** — `bq query --dry_run`, `bq mk --time_partitioning_field`, `bq show`:
  <https://cloud.google.com/bigquery/docs/reference/bq-cli-reference>
- **BigQuery client library for Python** (`google-cloud-bigquery`) — used in Exercise 3 to pull the query plan:
  <https://cloud.google.com/python/docs/reference/bigquery/latest>
- **`QueryJob.query_plan` and `QueryJob.timeline`** — the Python objects that expose `job_stages`:
  <https://cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.job.QueryJob>

## Terraform for BigQuery

- **`google_bigquery_dataset`**: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_dataset>
- **`google_bigquery_table`** (time/range partitioning, clustering, MV blocks):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_table>
- **`google_bigquery_reservation`** + **`google_bigquery_capacity_commitment`** (the editions reservation):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_reservation>
- **`google_bigquery_data_transfer_config`** (scheduled queries, if you choose that over an MV):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_data_transfer_config>

## The open-source alternative (the standing "name it" rule)

C18 names the open-source alternative every week. For BigQuery it is **Trino + Iceberg on object storage**.

- **Trino** — the distributed SQL query engine (formerly PrestoSQL); the closest open analog to BigQuery's compute:
  <https://trino.io/docs/current/>
- **Apache Iceberg** — the open table format that gives you partitioning, hidden partitioning, and time travel over Parquet on object storage:
  <https://iceberg.apache.org/docs/latest/>
- **Iceberg partitioning spec** — "hidden partitioning" is conceptually what BigQuery's partition pruning does; read it to make the comparison honest:
  <https://iceberg.apache.org/spec/#partitioning>
- **BigQuery's own BigLake / Iceberg interop** — Google now reads/writes Iceberg tables, which blurs the line; know it exists:
  <https://cloud.google.com/bigquery/docs/iceberg-tables>

## Books

- ***Google BigQuery: The Definitive Guide*, Lakshmanan & Tigani (O'Reilly)** — still the best single book on BigQuery. The storage-model and query-optimization chapters are directly this week. Buy once:
  <https://www.oreilly.com/library/view/google-bigquery-the/9781492044451/>
- ***Data Pipelines with Apache Airflow / Fundamentals of Data Engineering*, Reis & Housley (O'Reilly)** — *Fundamentals* has the clearest vendor-neutral treatment of columnar storage, partitioning, and cost models. The chapter on storage abstractions pairs well with the Dremel paper:
  <https://www.oreilly.com/library/view/fundamentals-of-data/9781098108298/>
- **Google Cloud free *Architecture Framework*, cost-optimization pillar** — the BigQuery cost section is the closest thing to an opinionated textbook for the reservation-vs-on-demand decision:
  <https://cloud.google.com/architecture/framework/cost-optimization>

## Talks and video (free, no signup)

- **"BigQuery under the hood"** — Google Cloud Tech; the canonical internals talk, reposted most years at Next:
  <https://www.youtube.com/@googlecloudtech>
- **Google Cloud Next — data analytics session archive** — the reservation/editions and BQML sessions are recorded yearly:
  <https://cloud.withgoogle.com/next>
- **"How BigQuery's query optimizer works"** — search the Google Cloud Tech channel; the materialized-view rewrite demo is the useful five minutes.

## Tools you'll use this week

- **`bq` CLI** — installed with the Google Cloud SDK. Verify with `bq version`. You live in `bq query --dry_run` this week.
- **`gcloud`** — for reservations (`gcloud beta bigquery reservations`).
- **`terraform`** (or **`tofu`**) 1.9+, `google` provider `~> 6.0`.
- **`python3`** 3.11+ with `pip install google-cloud-bigquery`. Exercise 3 uses it to pull the query plan.
- **`jq`** — for slicing `bq ... --format=prettyjson` and `INFORMATION_SCHEMA` output.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Capacitor** | BigQuery's columnar on-disk format. Reorders rows and picks per-column encodings to maximize compression and scan-skipping. |
| **Colossus** | Google's distributed file system; where Capacitor files actually live. The "storage" half of storage/compute separation. |
| **Dremel** | The execution engine. Turns SQL into a tree of stages run across many slots, with an in-memory shuffle between them. |
| **Slot** | A unit of BigQuery compute (roughly a CPU + RAM share). On-demand gives you a fair share; reservations buy a fixed number. |
| **Bytes scanned** | The bytes BigQuery reads to answer a query. On-demand bills on this. Per-column: `SELECT *` scans every column. |
| **`total_bytes_processed`** | Bytes the engine processed for the query (the estimate `--dry_run` returns). |
| **`total_bytes_billed`** | Bytes you actually pay for; rounds up to a 10 MB minimum per query and is what cost is computed from. |
| **Partition** | A horizontal slice of a table keyed by a date/timestamp/int. A `WHERE` on the key prunes whole partitions before scanning. |
| **Clustering** | Sorted storage on up to 4 columns within each partition. A `WHERE`/`GROUP BY` on cluster keys prunes blocks. |
| **Require partition filter** | A table setting that rejects any query lacking a filter on the partition column. The seatbelt against the full scan. |
| **Materialized view** | A precomputed, incrementally maintained query result. The optimizer rewrites matching queries to read it instead. |
| **BI Engine** | An in-memory cache layer for sub-second dashboard queries. Bytes served from BI Engine are not billed as analysis. |
| **BQML** | Machine learning in SQL: `CREATE MODEL`, `ML.PREDICT`, `ML.EVALUATE`. The data never leaves BigQuery. |
| **Reservation** | A purchased pool of slots (Editions). Fixed cost regardless of bytes scanned; the alternative to on-demand. |
| **Editions** | BigQuery's tiered compute SKUs: Standard, Enterprise, Enterprise Plus. Priced per slot-hour, with autoscaling. |
| **Iceberg** | The open table format (the Trino-stack analog of a partitioned BigQuery table). Hidden partitioning ≈ partition pruning. |

---

*If a link 404s, please open an issue so we can replace it. Google moves doc URLs more often than it should.*
