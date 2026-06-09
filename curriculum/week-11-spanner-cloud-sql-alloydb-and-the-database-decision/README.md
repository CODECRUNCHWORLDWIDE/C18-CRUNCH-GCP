# Week 11 — Spanner, Cloud SQL, AlloyDB, and the Database Decision

Welcome to **C18 · Crunch GCP**, Week 11. Phase 1 gave you the resource hierarchy, IAM, and the VPC. Phase 2 put compute behind a load balancer and Cloud Armor. Week 09 moved bytes through Pub/Sub and Dataflow; Week 10 taught you to make BigQuery cheap. This week we answer the question that every staff engineer eventually has to defend in an architecture review: **which database, and why, and what does it cost?** GCP gives you at least seven first-class answers — Cloud SQL (Postgres/MySQL), AlloyDB, Spanner, Firestore, Bigtable, Memorystore, and BigQuery itself when the workload is analytical. The wrong choice is not a bug you fix in a sprint; it is an architecture you live with for years. By Friday you should be able to stand in front of a whiteboard, take a workload with a read/write ratio, a consistency requirement, a region footprint, and a budget, and put the right GCP database on the board with a number next to it and a sentence that survives cross-examination.

This is the third week of Phase 3 — **Data & AI**. The throughline of the phase is that *compute moves bytes; data tells the truth*, and the truth has a price. Last week that price was measured in bytes scanned. This week it is measured in dollars per node-hour and in the architectural blast radius of a consistency model. The single most expensive mistake junior cloud engineers make on GCP is reaching for Spanner because the marketing copy says "global, strongly consistent, unlimited scale" — and then paying \$650/month for a workload that an `db-custom-2-7680` Cloud SQL instance would serve for \$120 with room to spare. The second most expensive mistake is the opposite: bolting horizontal sharding logic onto a single-writer Postgres because nobody wanted to have the Spanner conversation, and then spending a quarter of engineering time reinventing what TrueTime gives you for free. This week teaches you to make that call on evidence.

The first thing to internalize is that **Spanner is not "managed Postgres at scale."** It is a different database with a different storage model (Colossus-backed, range-sharded into splits), a different consistency mechanism (Paxos replication coordinated by TrueTime's bounded-uncertainty clock), a different cost model (you pay for compute capacity in *processing units* or *nodes*, plus storage, plus network), and a different set of things it is bad at (ad-hoc analytics, large transactions, anything that wants a `SELECT *` over an unindexed column). It speaks a Postgres dialect now — the PGAdapter and the native PostgreSQL interface are real — but speaking the dialect does not make it Postgres any more than speaking English makes you British. Lecture 1 is the full argument for when Spanner's cost is justified and when it is theatre.

The second thing to internalize is that **AlloyDB is the answer to far more workloads than people expect.** It is genuinely Postgres — wire-compatible, extension-compatible, `pg_dump`-compatible — with a disaggregated storage layer that survives a zone loss without a failover, a columnar engine that runs analytical queries 10–100× faster than stock Postgres on the same data, and read pools that scale reads horizontally without the application knowing. For the very common shape "I have a Postgres app, it is growing, I want it to stop being my 2am problem, and I occasionally run a heavy analytical query against it," AlloyDB is usually the right answer and Spanner is usually overkill. Lecture 1 draws the line precisely: you go to Spanner when you need *horizontal write scale* or *multi-region synchronous strong consistency* — and not before.

The third thing to internalize is that **the open-source alternatives are real and you must be able to name them.** CockroachDB and YugabyteDB are both Spanner-shaped — distributed SQL, Raft (CockroachDB) or Raft (YugabyteDB) consensus instead of Paxos, hybrid-logical-clock timestamps instead of a TrueTime atomic-clock fleet — and both will run on your own GKE cluster on any cloud. Lecture 2 is the honest comparison: what TrueTime's physical-clock fleet bought Google that an HLC cannot quite replicate, where CockroachDB's serializable-by-default isolation actually beats Spanner's, what self-hosting costs you in on-call hours, and how to write the exit-plan paragraph that an architecture review demands. You will not leave this week believing GCP is best; you will leave it able to defend GCP where it is best and recommend against it where it isn't.

The fourth thing to internalize is that **the teardown is part of the lab.** Spanner is the one service in this course that will quietly bill you while you sleep. A single 1000-processing-unit instance is ~\$0.90/hour; leave it running over a weekend and you have spent \$45 on a lab that should have cost \$2. Every Spanner exercise this week has an explicit teardown gate, a billing-alert verification step, and a "before bed" deadline. We treat a forgotten Spanner instance the way Week 07 treated a `Debug`-build benchmark: a failing grade, not a footnote.

## Learning objectives

By the end of this week, you will be able to:

- **Compare** GCP's seven first-class data stores — Cloud SQL, AlloyDB, Spanner, Firestore, Bigtable, Memorystore, BigQuery — along the axes that actually drive the decision: consistency model, write scaling, read scaling, latency, region footprint, query surface, and cost per unit of capacity.
- **Configure** a Cloud SQL for PostgreSQL instance with regional high availability (synchronous standby in a second zone), a cross-region read replica, and Private Service Connect so the instance has *no public IP* and is reachable only from inside your VPC.
- **Explain** Spanner's architecture from first principles: Colossus storage, splits and range-sharding, Paxos groups, leader leases, and the role of TrueTime's `TT.now()` interval in enabling external consistency without a global lock.
- **Provision** a single-region Spanner instance with the smallest viable capacity (100 processing units), define a schema that uses an `INTERLEAVE IN PARENT` table for locality, write and read rows, and tear the whole thing down inside one billing hour.
- **Decide** between Cloud SQL, AlloyDB, and Spanner for three concrete workloads with a stated budget, producing a written justification that names the deciding factor and the runner-up choice for each.
- **Distinguish** Firestore from Bigtable (document vs wide-column, strong vs eventual at scale, query surface, hot-key behavior) and know when Memorystore (Redis/Valkey) belongs in front of any of them.
- **Articulate** the CockroachDB and YugabyteDB comparison: where distributed-SQL open source matches Spanner, where TrueTime's atomic-clock fleet still wins, and what self-hosting actually costs an on-call rotation.
- **Migrate** a Cloud SQL Postgres database into Spanner using a Datastream change-data-capture stream into a Dataflow template, and validate correctness with a parallel read shadow-test before any cutover.
- **Arm** a billing budget alert and a Cloud Monitoring alert on Spanner CPU and storage *before* creating the instance, and verify both fired (or would fire) as part of teardown discipline.
- **Cite** the Spanner, AlloyDB, Cloud SQL, and Datastream documentation, the original Spanner OSDI 2012 paper, and the CockroachDB/Yugabyte architecture docs that justify each decision.

## Prerequisites

- **Weeks 01 through 10 of C18 complete.** You can stand up a VPC with private subnets and Private Google Access (Week 03), write a Terraform module with `for_each` and a GCS remote backend (Week 04), deploy a workload to GKE (Week 06), wire Cloud Run to a private Cloud SQL over PSC (Week 07), and build a Dataflow pipeline (Week 09). This week reuses all of it.
- **A GCP project with billing enabled and a budget already armed.** Week 01's first exercise was a hard billing cap; if you skipped it, do it now before you touch Spanner. The Spanner labs cost real money — budget ~\$5 for the week and arm a \$10 alert.
- **The Week 06 GKE cluster, or the ability to recreate it.** The mini-project integrates the new database service with that cluster. If you tore it down, the `envs/dev` Terraform from Week 06 brings it back in ~12 minutes.
- **Working `gcloud`, `terraform` (or `tofu`) ≥ 1.7, and `psql` ≥ 15 on your PATH.** Confirm with `gcloud version`, `terraform version`, `psql --version`. The `google` provider we target is `~> 6.0` and `google-beta ~> 6.0` (AlloyDB and some Spanner features live in `google-beta`).
- **Python 3.11+** for the migration validation harness and the Spanner client exercises, with the ability to `pip install google-cloud-spanner` and `google-cloud-datastream`.
- **A credit card on the billing account.** Cloud SQL HA, the cross-region read replica, and Spanner are not free-tier. The week is designed so that disciplined teardown keeps total out-of-pocket under \$5.

## Topics covered

- **Cloud SQL for PostgreSQL — the production shape.** Regional HA (synchronous standby in a second zone, automatic failover), the difference between HA failover and a read replica, cross-region read replicas (asynchronous, promotable for DR), maintenance windows, point-in-time recovery, and the `ENABLE_PRIVATE_SERVICE_CONNECT` connectivity mode versus the older private-services-access (VPC peering) mode.
- **Private Service Connect for databases.** Why PSC is the 2026 default over the legacy `servicenetworking` VPC peering: per-consumer endpoints, no IP-range exhaustion, no transitive peering surprises, and a clean DNS story. The service-attachment / endpoint / forwarding-rule chain.
- **AlloyDB for PostgreSQL.** The disaggregated architecture (compute nodes over a regional, log-structured storage layer on Colossus), the columnar engine and how the auto-columnarization decides what to keep in the column store, primary instances vs read pool instances, the "4× faster than standard Postgres for transactional, up to 100× for analytical" claim and where it holds.
- **Spanner architecture.** Colossus storage, tables sharded into *splits* by primary-key range, each split a Paxos group with a leader and replicas, leader leases, and **TrueTime**: the `TT.now()` interval `[earliest, latest]`, the commit-wait that turns bounded clock uncertainty into external consistency, and why the GPS+atomic-clock fleet in every Google datacenter is the thing you cannot buy off the shelf.
- **Spanner schema design.** Primary key choice and hotspotting (monotonic keys are an anti-pattern; UUIDs or hashed prefixes spread load), `INTERLEAVE IN PARENT` for parent-child locality, secondary indexes and `STORING` columns, the absence of `SERIAL`/auto-increment and what to use instead, and processing units vs nodes (1 node = 1000 PU) as the capacity unit.
- **Firestore vs Bigtable.** Firestore (document model, strong consistency, automatic multi-region, great for app state and real-time listeners, weak for analytical scans) versus Bigtable (wide-column, single-digit-millisecond at petabyte scale, eventual across clusters, row-key design is everything, no secondary indexes). The decision: app data and sync → Firestore; time-series and high-throughput key-value → Bigtable.
- **Memorystore for Redis / Valkey.** When a cache belongs in front of any of the above, the Valkey fork and why GCP added it, Standard-tier HA, read replicas, and the cache-aside vs read-through patterns. The "Memorystore is not a database" rule.
- **The decision framework.** A repeatable scoring rubric: consistency need, write-scale need, read-scale need, region footprint, query surface, operational budget, and dollar budget. How to weight them and how to write the one-paragraph justification an architecture review will accept.
- **The CockroachDB / YugabyteDB comparison.** Distributed SQL on Raft, HLC timestamps vs TrueTime, serializable-by-default isolation, the self-hosting cost in on-call hours, the multi-cloud portability argument, and how to write the exit-plan paragraph that defends or rejects the GCP lock-in.
- **Datastream + Dataflow migration.** CDC from Cloud SQL Postgres via logical replication, the Datastream → GCS or Datastream → Dataflow path, the Spanner migration tooling (HarbourBridge / the Spanner migration tool), schema translation gotchas, and the parallel-read shadow-test pattern for validating a migration before cutover.

## Weekly schedule

The schedule adds up to approximately **36 hours**. Treat it as a target, not a contract. Do the Spanner exercises *early in a day*, never late at night — the teardown gate exists because tired engineers forget running instances. Arm your billing alert before you provision anything.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Cloud SQL HA + read replica + PSC; the decision axes        |    2h    |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Tuesday   | Spanner architecture, TrueTime, Paxos, schema design        |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Wednesday | Firestore vs Bigtable, Memorystore, the decision framework  |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     1h       |    0.5h    |     5.5h    |
| Thursday  | CockroachDB/Yugabyte comparison; challenge #1 (migration)   |    1h    |    0h     |     2.5h   |    0.5h   |   1h     |     1h       |    0.5h    |     6.5h    |
| Friday    | Mini-project — current-state service, Cloud SQL backend     |    0h    |    0h     |     0.5h   |    0.5h   |   1h     |     3h       |    0.5h    |     5.5h    |
| Saturday  | Mini-project deep work — Datastream→Spanner migration path  |    0h    |    0h     |     0h     |    0h     |   0h     |     3.5h     |    0h      |     3.5h    |
| Sunday    | Quiz, teardown verification, review, polish                 |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0.5h    |     2.5h    |
| **Total** |                                                             | **6h**   | **5h**    | **5h**     | **3.5h**  | **5h**   | **12.5h**    | **3h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Spanner/Cloud SQL/AlloyDB/Datastream docs, the Spanner OSDI paper, the CockroachDB and Yugabyte architecture docs, talks worth watching |
| [lecture-notes/01-spanner-is-not-managed-postgres-at-scale.md](./lecture-notes/01-spanner-is-not-managed-postgres-at-scale.md) | The full argument: Cloud SQL → AlloyDB → Spanner, what each costs, when Spanner's price is justified and when it is theatre, with the decision rubric |
| [lecture-notes/02-cockroachdb-yugabyte-and-what-truetime-made-possible.md](./lecture-notes/02-cockroachdb-yugabyte-and-what-truetime-made-possible.md) | TrueTime from first principles, the Paxos commit-wait, the HLC alternative, the CockroachDB / Yugabyte comparison, and the exit-plan paragraph |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-cloud-sql-ha-replica-psc.md](./exercises/exercise-01-cloud-sql-ha-replica-psc.md) | Terraform a Cloud SQL Postgres instance with HA, a cross-region read replica, and PSC — no public IP. Validate from a private GCE VM |
| [exercises/exercise-02-spanner-interleaved-schema.py](./exercises/exercise-02-spanner-interleaved-schema.py) | Stand up a 100-PU single-region Spanner instance, create an interleaved schema, write/read rows, and tear it down within the hour — all from the Python client, with a teardown guard |
| [exercises/exercise-03-database-decision.py](./exercises/exercise-03-database-decision.py) | Score three workloads against the decision rubric and emit a written justification. A runnable, testable decision engine |
| [challenges/README.md](./challenges/README.md) | Index of the challenge |
| [challenges/challenge-01-datastream-spanner-migration.md](./challenges/challenge-01-datastream-spanner-migration.md) | Migrate a Cloud SQL Postgres DB to single-region Spanner via Datastream + Dataflow, run a 30-minute parallel read shadow-test, tear Spanner down before bed with billing alerts confirmed |
| [quiz.md](./quiz.md) | 13 questions on Cloud SQL, AlloyDB, Spanner, TrueTime, Firestore/Bigtable, and the decision framework, with an answer key |
| [homework.md](./homework.md) | Six practice problems with a rubric |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the "current-state" service: Cloud SQL (HA + replica + PSC) backend, a documented & tested Datastream→Spanner migration path, integrated with the Week 06 GKE cluster. This becomes the Spanner-backed gRPC service in the capstone |

## The teardown promise

C18 treats teardown the way C9 treated `dotnet build` warnings: a contract, not a courtesy. For Week 11 the contract is specific because Spanner bills by the hour:

```
Spanner instance:    DELETED   (gcloud spanner instances list → empty)
Billing alert:       ARMED     (budget alert at $10, verified in console)
Cloud SQL instance:  STOPPED or DELETED per the mini-project gate
```

Every exercise and the challenge end with a teardown step and a verification command. **A forgotten Spanner instance is a failing grade for the week**, the same way a `Debug` benchmark was a failing grade in C9 Week 07. The discipline is the point: production engineers who cannot be trusted to tear down a costly resource cannot be trusted with the production billing account.

## A note on what's not here

Week 11 is the relational and operational-NoSQL decision. It does **not** cover:

- **BigQuery as an OLAP store.** That was Week 10. We mention BigQuery only as the analytical *runner-up* in the decision rubric — "if the workload is analytical, none of this week's databases is the answer; BigQuery is."
- **Spanner multi-region configs.** A `nam3` or global Spanner config is the genuinely expensive, genuinely powerful configuration — and it is a capstone stretch goal, not a Week 11 lab. We use single-region (`regional-us-central1`) all week to keep the bill under \$5. Lecture 1 explains what multi-region buys and why we don't pay for it yet.
- **Spanner's graph and vector features.** Spanner Graph and the vector index are real 2026 features; they are out of scope for the decision this week and belong in an elective.
- **Bigtable schema deep design.** We compare Bigtable to Firestore at the decision level; the row-key-design deep dive (a full week's worth of material on its own) is left to the resources list.
- **Database migration *off* GCP.** The exit plan (Lecture 2) is the architectural argument; the mechanical lift-to-CockroachDB is left as a homework thought-exercise, not a lab.

The point of Week 11 is a sharp, defensible decision: take a workload, put the right GCP database behind it with a dollar number, name the open-source alternative, and write the exit plan. Then tear down the one that bills you while you sleep.

## Up next

Continue to **Week 12 — Vertex AI, Model Garden, and serving inference** once you have shipped this week's mini-project *and verified the teardown*. Week 12 closes Phase 3: the database you chose this week becomes the state store behind a model-serving path. The mini-project's "current-state" service is the same gRPC service that the capstone wires to a Vertex AI Endpoint client. The decision discipline you build this week — *pick on evidence, name the alternative, write the exit plan, tear down what bills you* — is the same discipline that makes the capstone defensible in front of a staff engineer.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
