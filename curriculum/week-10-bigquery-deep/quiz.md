# Week 10 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 11. Answer key at the bottom — don't peek.

---

**Q1.** On BigQuery on-demand pricing, what does a query bill on?

- A) The number of rows returned to the client.
- B) The wall-clock time the query ran.
- C) The bytes scanned (read), which is per-column.
- D) The size of the result set written.

---

**Q2.** Why is `SELECT * FROM wide_table LIMIT 10` expensive even though it returns only 10 rows?

- A) The `LIMIT` is ignored entirely by BigQuery.
- B) `SELECT *` forces every column to be read, and `LIMIT` caps what is *returned*, not what is *scanned*.
- C) Returning 10 rows requires writing them to storage first.
- D) It is not expensive; `LIMIT 10` makes it cheap.

---

**Q3.** A table is partitioned by `DATE(pickup_datetime)`. Which `WHERE` clause **prunes** partitions?

- A) `WHERE DATE(pickup_datetime) = '2023-07-04'`
- B) `WHERE EXTRACT(DATE FROM pickup_datetime) = '2023-07-04'`
- C) `WHERE pickup_datetime >= '2023-07-04' AND pickup_datetime < '2023-07-05'`
- D) `WHERE CAST(pickup_datetime AS DATE) = '2023-07-04'`

---

**Q4.** You see a query stage in `job_stages` where `records_written` is 18 billion but `records_read` is 50 million. What is this the signature of?

- A) A successful partition prune.
- B) A fan-out — a join that multiplied rows because the join key was not unique on one side.
- C) Normal aggregation.
- D) A clustering re-sort.

---

**Q5.** What does `require_partition_filter = TRUE` do?

- A) Automatically adds a partition filter to every query.
- B) Rejects any query that lacks a filter on the partition column usable for partition elimination.
- C) Makes the table partition itself hourly.
- D) Caps the bytes billed per query.

---

**Q6.** What is the difference between `total_bytes_processed` and `total_bytes_billed`?

- A) They are always identical.
- B) `total_bytes_processed` is what `--dry_run` predicts; `total_bytes_billed` is what you actually pay (rounded up to the 10 MB per-query minimum), and for clustered tables it can be *lower* than the dry-run estimate.
- C) `total_bytes_billed` is always larger because it includes storage.
- D) `total_bytes_processed` includes network egress.

---

**Q7.** You cluster a table `CLUSTER BY payment_type, vendor_id`. A query filters only on `vendor_id`. What happens?

- A) Maximum block pruning, same as filtering on `payment_type`.
- B) Less effective pruning than filtering on `payment_type`, because the data is sorted by `payment_type` first.
- C) The query is rejected.
- D) Clustering has no effect on `WHERE` at all.

---

**Q8.** What is the key advantage of a **materialized view** over a scheduled query that writes the same aggregate to a table?

- A) MVs are always fresher.
- B) MVs are incrementally maintained *and* the optimizer automatically rewrites matching base-table queries to read the MV without you naming it.
- C) MVs can join unlimited tables.
- D) MVs are free to store.

---

**Q9.** A 100-slot Enterprise reservation at ~\$0.06/slot-hour is left running 24/7 and never queried. Roughly what does it cost per day?

- A) \$0 — you only pay when you query.
- B) ~\$0.06 — one slot-hour.
- C) ~\$144 — 100 slots × 24 hours × \$0.06.
- D) ~\$6.25 — one TiB.

---

**Q10.** For a nightly batch that scans **40 TiB**, which pricing model is cheaper and why?

- A) On-demand, because reservations are always more expensive.
- B) A reservation — 40 TiB on-demand is \$250, while a 100-slot reservation for the one-hour window is ~\$6 (assuming 100 slots finish the batch in the hour).
- C) They cost the same.
- D) Neither; you must use BI Engine.

---

**Q11.** In BigQuery ML, what is the main value proposition of training a `LOGISTIC_REG` model with `CREATE MODEL`?

- A) It always beats a hand-tuned PyTorch model.
- B) The data never leaves BigQuery — no export pipeline, no separate feature store — and you train/evaluate/predict in SQL.
- C) Training is always free regardless of data size.
- D) It can train 7B-parameter language models.

---

**Q12.** Which `INFORMATION_SCHEMA` view do you query to find the most expensive jobs of the day and read their `total_bytes_billed`?

- A) `INFORMATION_SCHEMA.COLUMNS`
- B) `INFORMATION_SCHEMA.PARTITIONS`
- C) `INFORMATION_SCHEMA.JOBS_BY_PROJECT` (region-qualified)
- D) `INFORMATION_SCHEMA.TABLE_STORAGE`

---

**Q13.** In the Trino + Iceberg comparison, what concept in Iceberg is the closest analog to BigQuery's partition pruning?

- A) Iceberg's manifest files only.
- B) Iceberg's "hidden partitioning" (partition spec), which lets the engine skip data files that cannot match the predicate.
- C) Iceberg's time-travel snapshots.
- D) Parquet's footer checksum.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **C** — On-demand bills on bytes scanned, and the scan is per-column. Not rows, not wall-clock, not result size. This is the failure mode the whole week is about.
2. **B** — `SELECT *` opens every column; `LIMIT` is a display cap applied after the scan. Naming columns and filtering the partition key is the fix.
3. **C** — Only the bare-column range predicate prunes. Wrapping the partition column in `DATE()`, `EXTRACT()`, or `CAST()` defeats partition elimination — a full scan in disguise.
4. **B** — Output records ≫ input records is the fan-out fingerprint. The join key was non-unique on one side; fix by making it unique (add the missing key) or aggregating first.
5. **B** — It is the seatbelt: it rejects queries lacking a usable partition filter, converting an accidental full scan from a billing event into a query error. (Use `maximum_bytes_billed` for the per-query byte cap — option D is a different control.)
6. **B** — `processed` is the dry-run prediction; `billed` is what you pay (10 MB minimum), and clustering can make billed *lower* than the dry-run estimate because the dry run can't know which blocks it will skip.
7. **B** — Cluster column *order* matters: data is sorted by the first column first. Filtering only on the second column prunes less than filtering on the first. Order columns most-filtered-first.
8. **B** — Incremental maintenance + automatic query rewrite (smart tuning). Your dashboards keep querying the base table and transparently get the cheap MV answer. A scheduled query has neither property.
9. **C** — 100 × 24 × \$0.06 ≈ \$144/day, scanning nothing. The reservation footgun: slots bill continuously, idle or not. This is why the teardown gate verifies no reservation remains.
10. **B** — 40 TiB × \$6.25 = \$250 on-demand vs. ~\$6 for a 100-slot reservation for the hour (if capacity suffices). Reservations win for heavy scan-intensive workloads; on-demand wins for light/sporadic ones.
11. **B** — The data never leaves BigQuery; you train, evaluate, and predict in SQL. BQML is for classical ML (GLMs, trees, k-means, matrix factorization, imported models), not deep learning — that is Vertex AI (Week 12).
12. **C** — `JOBS_BY_PROJECT` (region-qualified, e.g. `` `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT ``) has one row per job with `total_bytes_billed` and the repeated `job_stages`. The others describe schema/partitions/storage, not jobs.
13. **B** — Iceberg's hidden partitioning (partition spec) lets the engine skip data files that can't match the predicate — the open-format analog of BigQuery's partition pruning. Sort order + Parquet row-group stats are the clustering analog.

</details>

---

If you scored under 9, re-read the lecture for the questions you missed — especially Q3 (bare partition column), Q6 (processed vs. billed), and Q9 (the idle-reservation cost), which are the three ideas that separate "knows BigQuery syntax" from "won't accidentally spend \$2000." If you scored 12 or 13, you're ready for the [homework](./homework.md).
