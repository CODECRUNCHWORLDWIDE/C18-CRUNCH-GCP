# Week 11 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 12. Answer key at the bottom — don't peek.

---

**Q1.** A team proposes Spanner for a single-region SaaS app with 5,000 users and a budget of \$200/month, citing "we want room to scale." What is the correct senior response?

- A) Approve it; Spanner scales, so it is future-proof.
- B) Reject it. Spanner is a *capability* purchase, not a scale upgrade. The workload needs neither horizontal write scale nor multi-region strong consistency, so the right answer is Cloud SQL; the budget cannot carry a production Spanner footprint anyway.
- C) Approve AlloyDB instead, because it is the middle option.
- D) Approve it, but only the multi-region config, for maximum future-proofing.

---

**Q2.** On a Cloud SQL instance, `availability_type = "REGIONAL"` provides which capability?

- A) Read scaling — the standby serves read traffic.
- B) A synchronous standby in a second zone of the same region, with automatic failover on zone loss. The standby serves no traffic until failover.
- C) A cross-region asynchronous replica for disaster recovery.
- D) Nothing; it is a no-op label.

---

**Q3.** Your production Cloud SQL instance must not be reachable from the internet. Which configuration achieves this in 2026?

- A) `ipv4_enabled = true` with an authorized-networks allowlist of `0.0.0.0/0`.
- B) `ipv4_enabled = false` with a `psc_config` block, and a PSC endpoint (forwarding rule with `load_balancing_scheme = ""`) in your VPC.
- C) A public IP plus Cloud Armor.
- D) `ipv4_enabled = true` with SSL required.

---

**Q4.** What does TrueTime's `TT.now()` return, and why does it matter?

- A) A single precise timestamp, accurate to the nanosecond.
- B) An interval `[earliest, latest]` guaranteed to contain the true time; the *bounded uncertainty* is what enables the commit-wait and therefore external consistency.
- C) A Lamport logical counter.
- D) The local machine's NTP-synced wall clock with no uncertainty.

---

**Q5.** Spanner's commit-wait does what?

- A) Waits for a quorum of replicas to acknowledge the write, then returns immediately.
- B) After choosing commit timestamp `s = TT.now().latest`, waits until `TT.after(s)` is true (roughly `2ε`) before releasing locks, guaranteeing that any later transaction picks a strictly greater timestamp — globally.
- C) Waits for the read replicas to catch up before allowing the next write.
- D) Adds a fixed 100ms delay to every transaction for safety.

---

**Q6.** You design a Spanner table with `PRIMARY KEY (CreatedAt)` where `CreatedAt` is a monotonically increasing timestamp. What happens?

- A) Optimal performance — sorted keys are fast.
- B) A write hotspot: every new row targets the split holding the highest keys, so write throughput cannot scale no matter how many nodes you add. Use a UUID or hashed prefix instead.
- C) Nothing; Spanner auto-shards by hash regardless of key.
- D) A read hotspot only; writes are fine.

---

**Q7.** What does `INTERLEAVE IN PARENT` accomplish in a Spanner schema?

- A) It creates a foreign-key constraint with no storage implications.
- B) It physically co-locates child rows with their parent row in the same split, so reading a parent and its children is a single-split operation instead of a cross-split join.
- C) It replicates the child table to every region.
- D) It enables auto-increment on the child's primary key.

---

**Q8.** When is AlloyDB the better choice than both Cloud SQL and Spanner?

- A) When you need multi-region synchronous strong consistency.
- B) When you have a Postgres workload that is growing, wants low-lag horizontal read scaling and/or runs occasional heavy analytical queries, stays single-region and single-writer, and you want to reduce operational burden (no failover on zone loss).
- C) When you need horizontal *write* scale beyond one machine.
- D) When the workload is purely analytical with ad-hoc scans.

---

**Q9.** A workload's query surface is primarily analytical — large scans and aggregations over event data, no transactional point reads. Which of this week's databases is the right answer?

- A) Spanner, for scale.
- B) AlloyDB, for the columnar engine.
- C) None of them. If the workload is primarily analytical, the answer is BigQuery (Week 10), not a transactional database.
- D) Cloud SQL with a big read replica.

---

**Q10.** How do CockroachDB and YugabyteDB handle the clock problem without TrueTime?

- A) They use a GPS + atomic-clock fleet identical to Google's.
- B) They use hybrid-logical clocks (HLC) plus NTP with a configured `max_offset`; they get a close approximation of external consistency but lack TrueTime's *provably bounded* uncertainty, handling skew with uncertainty intervals and read restarts.
- C) They ignore wall-clock time entirely and use only Lamport timestamps.
- D) They require an external atomic clock you must purchase separately.

---

**Q11.** In an architecture review, you argue for Spanner over self-hosted CockroachDB. What is the strongest single argument, honestly stated?

- A) Spanner is technically superior in every dimension.
- B) Self-hosting distributed SQL costs roughly 0.5–1.5 FTE of ongoing operations (upgrades, rebalancing, clock monitoring, on-call); the Spanner premium largely buys you out of staffing that function — which is worth it unless you already run a database-SRE team or need multi-cloud portability.
- C) CockroachDB cannot do serializable isolation.
- D) Spanner is cheaper than self-hosting in raw infrastructure cost.

---

**Q12.** Firestore vs Bigtable — which statement is correct?

- A) Bigtable is a document database with strong consistency, ideal for app state and real-time listeners.
- B) Firestore is a document database with strong consistency and automatic multi-region, good for app state and real-time sync; Bigtable is a wide-column store, single-digit-ms at petabyte scale, eventual across clusters, where row-key design is everything — good for time-series and high-throughput key-value.
- C) They are interchangeable; pick whichever has the lower price.
- D) Firestore is for analytics and Bigtable is for transactions.

---

**Q13.** During a Cloud SQL → Spanner migration, your shadow-test samples a customer key, finds the order count differs between Cloud SQL (12) and Spanner (11), and the row was just written to Cloud SQL during the test. What should you conclude?

- A) A correctness bug — fail the migration immediately.
- B) Probably replication lag, not a bug: CDC is asynchronous, so a row just written to the source appears in Spanner after a lag. Re-check the key after a bounded convergence window; only log a real mismatch if it never converges.
- C) Spanner lost the write; data loss has occurred.
- D) The shadow-test is broken and should be ignored.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Spanner is a capability purchase. With no horizontal-write-scale and no multi-region-strong-consistency requirement, the deciding axis points to Cloud SQL, and the \$200 budget is below a production Spanner footprint regardless. "Future-proofing" with a capability you do not need is theatre (Lecture 1, §1.6).

2. **B** — `REGIONAL` availability means a synchronous standby in a second zone with automatic failover on zone loss. It is *not* read scaling (the standby serves nothing until failover) and it is *not* the cross-region DR replica (that is a separate resource). (Lecture 1, §1.2.)

3. **B** — `ipv4_enabled = false` plus a `psc_config` block on the instance, and a consumer-side PSC endpoint (a forwarding rule with `load_balancing_scheme = ""` targeting the service attachment). No public IP exists. Option A allowlisting `0.0.0.0/0` is the opposite of private. (Lecture 1, §1.3; Exercise 1.)

4. **B** — `TT.now()` returns an interval `[earliest, latest]` guaranteed to contain the true time. The value is the *bound*, not the point: it lets Spanner perform the commit-wait and thereby guarantee external consistency. NTP gives a guess; TrueTime gives a proven bound. (Lecture 2, §2.2.)

5. **B** — The commit-wait: after picking `s = TT.now().latest` and doing the Paxos write, Spanner waits until `TT.after(s)` (about `2ε`) before releasing locks. This guarantees every clock everywhere now reads past `s`, so any later transaction gets a strictly greater timestamp — making timestamp order match real-time order globally. (Lecture 2, §2.3.)

6. **B** — A monotonic primary key sends every write to the single split holding the highest keys, creating a hotspot that no number of nodes relieves. The fix is a UUID or a hashed prefix to spread writes across splits. (Lecture 1, §1.5; Spanner schema-design docs.)

7. **B** — `INTERLEAVE IN PARENT` physically co-locates child rows with the parent row in the same split, turning "fetch a parent and its children" into a single-split read. It is a storage/locality directive, not just a constraint. (Lecture 1, §1.5; Exercise 2.)

8. **B** — AlloyDB fits the "Postgres, but bigger, with low-lag read scaling and/or analytical queries, single-region single-writer, and I want to stop paging" shape. It does *not* give horizontal write scale (still single-writer) or multi-region strong consistency (that is Spanner), and it is not the answer for purely-analytical workloads (that is BigQuery). (Lecture 1, §1.4, §1.7.)

9. **C** — None of this week's transactional databases. A primarily-analytical query surface (scans, aggregations) is a BigQuery workload (Week 10). Putting it on Spanner is the most expensive way to do it slowly. The decision rubric's Rule 0 routes analytical workloads to BigQuery. (Lecture 1, §1.6; Exercise 3.)

10. **B** — Hybrid-logical clocks plus NTP with a `max_offset`. They approximate external consistency and handle clock skew with uncertainty intervals and read restarts, but lack TrueTime's *provably bounded* `ε`. The atomic-clock fleet is the part you cannot buy off the shelf. (Lecture 2, §2.4, §2.5.)

11. **B** — The honest, strongest argument is the operational one: self-hosting distributed SQL costs 0.5–1.5 FTE of ongoing ops, and the Spanner premium buys you out of staffing that. Option A (superior in every dimension) is false — CockroachDB defaults to serializable isolation and runs multi-cloud, both genuine advantages. (Lecture 2, §2.6, §2.7.)

12. **B** — Firestore: document model, strong consistency, automatic multi-region, real-time listeners — app state and sync. Bigtable: wide-column, single-digit-ms at petabyte scale, eventual across clusters, row-key design is everything — time-series and high-throughput key-value. (Lecture 1, Topics; resources Firestore/Bigtable docs.)

13. **B** — CDC is asynchronous; a row just written to the source appears in Spanner after a replication lag. The shadow-test must distinguish "lagging, will converge" from "diverged, a bug" by re-checking the key after a bounded window. Only a mismatch that *never* converges is a real correctness failure. (Challenge 1, hint 4.)

</details>

---

If you scored under 9, re-read the lectures for the questions you missed. If you scored 11 or higher, you're ready for the [homework](./06-homework.md). Either way: confirm `gcloud spanner instances list` is empty before you close your laptop.
