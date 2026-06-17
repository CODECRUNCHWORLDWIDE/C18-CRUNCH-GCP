# Week 11 — Resources

Every resource on this page is **free**. Google Cloud documentation is free without an account. The Spanner OSDI 2012 paper, the Hybrid Logical Clocks paper, and the CockroachDB / YugabyteDB architecture docs are public. The talks are on YouTube without an account. No paywalled books are required; the two books listed have freely-readable companion material online.

One cost note that is not a resource but belongs at the top: **before you read any of this, arm a \$10 billing budget alert on your project.** This week is the one week in C18 where a forgotten resource (a Spanner instance) bills you while you sleep. The pricing calculator below is the first link you should open.

## Required reading (work it into your week)

- **Google Cloud Pricing Calculator** — price a Cloud SQL HA instance, an AlloyDB cluster, and a 100-PU Spanner instance *before* you provision any of them:
  <https://cloud.google.com/products/calculator>
- **Spanner — TrueTime and external consistency** (the conceptual core of both lectures):
  <https://cloud.google.com/spanner/docs/true-time-external-consistency>
- **Spanner — schema design best practices** (hotspotting, interleaving, key choice — read before Exercise 2):
  <https://cloud.google.com/spanner/docs/schema-design>
- **Spanner — compute capacity (processing units and nodes)** (the cost unit):
  <https://cloud.google.com/spanner/docs/compute-capacity>
- **Cloud SQL — high availability** (regional HA, synchronous standby, failover):
  <https://cloud.google.com/sql/docs/postgres/high-availability>
- **Cloud SQL — Configure Private Service Connect** (read before Exercise 1):
  <https://cloud.google.com/sql/docs/postgres/configure-private-service-connect>
- **AlloyDB — overview** (the disaggregated-storage architecture):
  <https://cloud.google.com/alloydb/docs/overview>
- **Datastream — overview** (CDC source for the migration challenge):
  <https://cloud.google.com/datastream/docs/overview>

## The canonical papers

- **Spanner: Google's Globally-Distributed Database — OSDI 2012** — the paper. Read §3 (TrueTime) and §4 (concurrency control) at minimum. This is the source for everything in Lecture 2:
  <https://research.google/pubs/spanner-googles-globally-distributed-database/>
- **Hybrid Logical Clocks (Kulkarni, Demirbas, Madappa, Avva, Leone)** — the clock model CockroachDB and YugabyteDB use instead of TrueTime:
  <https://cse.buffalo.edu/tech-reports/2014-04.pdf>
- **Bigtable: A Distributed Storage System for Structured Data — OSDI 2006** — read this if you want to understand Cloud Bigtable's wide-column model from the source:
  <https://research.google/pubs/bigtable-a-distributed-storage-system-for-structured-data/>
- **F1: A Distributed SQL Database That Scales (VLDB 2013)** — the SQL layer Google built on Spanner; useful context for "Spanner is not just a key-value store":
  <https://research.google/pubs/f1-a-distributed-sql-database-that-scales/>

## Google Cloud docs — Spanner

- **Spanner — life of reads and writes** (how a transaction flows through splits and Paxos):
  <https://cloud.google.com/spanner/docs/whitepapers/life-of-reads-and-writes>
- **Spanner — replication** (Paxos groups, leaders, read-only replicas):
  <https://cloud.google.com/spanner/docs/replication>
- **Spanner — primary keys and avoiding hotspots**:
  <https://cloud.google.com/spanner/docs/schema-and-data-model#primary_keys>
- **Spanner — interleaved tables**:
  <https://cloud.google.com/spanner/docs/schema-and-data-model#parent-child>
- **Spanner — the PostgreSQL interface and PGAdapter**:
  <https://cloud.google.com/spanner/docs/postgresql-interface>
- **Spanner — Python client library**:
  <https://cloud.google.com/python/docs/reference/spanner/latest>
- **Spanner — instance configurations (regional vs multi-region) and pricing**:
  <https://cloud.google.com/spanner/docs/instance-configurations>

## Google Cloud docs — Cloud SQL and AlloyDB

- **Cloud SQL — read replicas** (same-region read scaling, cross-region DR):
  <https://cloud.google.com/sql/docs/postgres/replication>
- **Cloud SQL — point-in-time recovery**:
  <https://cloud.google.com/sql/docs/postgres/backup-recovery/pitr>
- **Cloud SQL — the `google_sql_database_instance` Terraform resource**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_database_instance>
- **AlloyDB — columnar engine**:
  <https://cloud.google.com/alloydb/docs/columnar-engine/about>
- **AlloyDB — read pool instances**:
  <https://cloud.google.com/alloydb/docs/instance-read-pool-create>
- **AlloyDB — the `google_alloydb_cluster` Terraform resource (google-beta)**:
  <https://registry.terraform.io/providers/hashicorp/google-beta/latest/docs/resources/alloydb_cluster>

## Google Cloud docs — Firestore, Bigtable, Memorystore

- **Firestore — overview and data model**:
  <https://cloud.google.com/firestore/docs/data-model>
- **Firestore vs Bigtable — Google's own "which database" guide**:
  <https://cloud.google.com/architecture/db-and-storage>
- **Bigtable — schema design (row keys are everything)**:
  <https://cloud.google.com/bigtable/docs/schema-design>
- **Memorystore for Redis — overview**:
  <https://cloud.google.com/memorystore/docs/redis>
- **Memorystore for Valkey — overview** (the open-source Redis fork GCP now offers):
  <https://cloud.google.com/memorystore/docs/valkey>

## The migration path (Datastream + Dataflow + Spanner tooling)

- **Datastream — PostgreSQL source configuration** (logical replication CDC):
  <https://cloud.google.com/datastream/docs/configure-your-source-postgresql-database>
- **Datastream — the Datastream to Spanner Dataflow template**:
  <https://cloud.google.com/dataflow/docs/guides/templates/provided/datastream-to-spanner>
- **Spanner migration tool (HarbourBridge)** — schema and data migration from Postgres/MySQL to Spanner:
  <https://github.com/GoogleCloudPlatform/spanner-migration-tool>
- **Cloud SQL → Spanner migration guide** (Google's end-to-end narrative):
  <https://cloud.google.com/spanner/docs/migrating-postgres-spanner>

## CockroachDB and YugabyteDB (the open-source comparison)

- **CockroachDB — architecture overview**:
  <https://www.cockroachlabs.com/docs/stable/architecture/overview>
- **CockroachDB — "Living Without Atomic Clocks"** — the canonical, honest comparison to TrueTime, written by the people who built the alternative:
  <https://www.cockroachlabs.com/blog/living-without-atomic-clocks/>
- **CockroachDB — transaction layer** (HLC, uncertainty intervals, read restarts):
  <https://www.cockroachlabs.com/docs/stable/architecture/transaction-layer>
- **YugabyteDB — architecture**:
  <https://docs.yugabyte.com/preview/architecture/>
- **YugabyteDB — DocDB storage layer**:
  <https://docs.yugabyte.com/preview/architecture/docdb/>
- **YugabyteDB vs CockroachDB vs Spanner** (Yugabyte's own comparison — read critically, it is a vendor doc):
  <https://www.yugabyte.com/yugabytedb-vs-cockroachdb/>

## Talks worth watching (all free, no account)

- **"Spanner: Google's Globally Distributed Database"** — conference talks by the Spanner authors walking the OSDI paper. Search YouTube for "Spanner OSDI TrueTime talk".
- **"How Google Cloud Spanner works"** — Google Cloud Tech channel deep dive. Search YouTube for "Google Cloud Spanner architecture deep dive".
- **Kyle Kingsbury (aphyr) — Jepsen analyses of CockroachDB and YugabyteDB** — the gold standard for "does this database actually do what it claims under partition." Search YouTube for "Jepsen CockroachDB" and read the written reports at <https://jepsen.io/analyses>.
- **"Choosing the right database on Google Cloud"** — Google Cloud Next session. Search YouTube for "Google Cloud database decision Next".

## Books with free companion material

- **"Database Internals" by Alex Petrov** (O'Reilly) — Part II (distributed systems, consensus, replication) is the best single explanation of the machinery under Spanner/Cockroach/Yugabyte. The author's site has free chapter excerpts: <https://www.databass.dev/>.
- **"Designing Data-Intensive Applications" by Martin Kleppmann** — Chapter 9 (consistency and consensus) is the canonical treatment of linearizability and the ordering problem TrueTime solves. The author's reading-list and talks are free: <https://martin.kleppmann.com/>.

## How to use this resource list

The lectures cite specific URLs from this page at decision points. The links you should read end-to-end *this week* are short:

1. **Spanner — TrueTime and external consistency** (Required reading). Foundational for both lectures.
2. **Spanner — schema design best practices** (Required reading). Read before Exercise 2 or you will build a hotspotting schema.
3. **Cloud SQL — Configure Private Service Connect** (Required reading). Read before Exercise 1.
4. **CockroachDB — "Living Without Atomic Clocks"** (~20 minutes). The single best companion to Lecture 2.
5. **The Spanner OSDI 2012 paper, §3 only** (~30 minutes). The source of the commit-wait.

The rest are reference material — bookmark them and return when a specific question arises. Do not feel obligated to read every link; even senior engineers re-read these when they touch the relevant system.

---

*Bookmarks decay. If a Google Cloud doc link rots, the docs are reorganized often — search the page title at `cloud.google.com` and you will find the current home. The papers and the CockroachDB/Yugabyte docs are stable.*
