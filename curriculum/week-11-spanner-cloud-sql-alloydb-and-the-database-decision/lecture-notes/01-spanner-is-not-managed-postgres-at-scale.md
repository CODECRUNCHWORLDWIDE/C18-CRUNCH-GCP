# Lecture 1 — Spanner Is Not "Managed Postgres at Scale"

> **Reading time:** ~75 minutes. **Hands-on time:** ~30 minutes (you arm a billing alert and read a Spanner pricing calculator before you provision anything this week).

This is the lecture that stops you from spending \$650 a month on a problem an `db-custom-2-7680` Cloud SQL instance solves for \$120. It is also the lecture that stops you from spending a quarter of an engineering team's time hand-rolling sharding logic on a single-writer Postgres because nobody wanted to have the Spanner conversation. Both mistakes come from the same misconception: that GCP's relational databases form a ladder — Cloud SQL at the bottom, AlloyDB in the middle, Spanner at the top — and that "scaling up" means climbing it. They do not form a ladder. They are three different databases for three different problem shapes, and the job of this lecture is to teach you the shapes so precisely that the right answer is obvious before you open the pricing calculator.

By the end of this lecture you can take a workload — a read/write ratio, a consistency requirement, a region footprint, a latency target, and a dollar budget — and put the right GCP relational database behind it with a number and a one-paragraph justification that survives an architecture review.

## 1.1 — The three databases, in one paragraph each

**Cloud SQL** is managed PostgreSQL (or MySQL, or SQL Server). It runs a single primary VM with a real Postgres process on it. Google manages the VM, the OS, the backups, the failover to a hot standby, and the patching. It is *the same Postgres you run on a laptop*, with the same `pg_stat_statements`, the same extensions (mostly), the same single-writer architecture, and the same ceiling: one machine's worth of write throughput. You scale it up (a bigger VM) and out for reads (replicas), but the write path is one process on one box. This is the right answer for the overwhelming majority of transactional workloads on Earth, and it is the answer you should reach for first, every time, until you can articulate why it is wrong.

**AlloyDB** is also PostgreSQL — wire-compatible, extension-compatible, `pg_dump`-restorable — but Google rebuilt the storage engine underneath it. The Postgres compute nodes are stateless; durable state lives in a *disaggregated, log-structured storage layer* on Colossus that is replicated across three zones automatically. The consequence: a zone loss does not require a failover (the storage survives), read pools scale reads horizontally to dozens of nodes, and a columnar engine transparently keeps hot columns in a column-store format so analytical queries run 10–100× faster than stock Postgres. It is still single-writer — one primary takes writes — but it removes most of the operational pain of running Postgres at the size where the pain starts. This is the right answer when "I have a Postgres app, it's growing, and I'm tired of being its pager" is true *and* you don't need horizontal write scale or multi-region synchronous consistency.

**Spanner** is not Postgres. It is a globally-distributed, horizontally-scalable, externally-consistent relational database that Google built for itself (the OSDI 2012 paper is the canonical reference) and then offered as a service. Tables are range-sharded into *splits*; each split is a Paxos replication group with a leader; writes commit through Paxos and are ordered by **TrueTime**, a clock service backed by GPS receivers and atomic clocks in every datacenter. The payoff is the thing no other managed database gives you: you can scale writes by adding nodes, with no application-visible sharding, and you can run a multi-region configuration that gives synchronous strong consistency across continents. It speaks a Postgres dialect now (PGAdapter and the native PostgreSQL interface), but the dialect is a compatibility layer, not the database. Spanner is the right answer when you need horizontal write scale *or* multi-region synchronous strong consistency — and it is the wrong answer, an expensive wrong answer, for everything else.

## 1.2 — Cloud SQL: the production shape you should know cold

Most engineers have run Postgres. Fewer have run *production* Cloud SQL the way a staff engineer expects it configured. The production shape has four properties, and you should be able to draw them on a whiteboard.

**1. Regional high availability.** A Cloud SQL HA instance is *two* VMs — a primary in zone A and a synchronous standby in zone B of the same region. Writes are committed to the primary and synchronously replicated (via regional persistent disk) to the standby. If the primary's zone fails, Cloud SQL fails over to the standby automatically, promoting it and re-pointing the instance's connection name. The failover takes tens of seconds to a couple of minutes; in-flight connections drop and must reconnect. **HA protects against zone loss; it does not scale reads** — the standby serves no traffic until failover.

**2. Read replicas.** A read replica is a *separate* asynchronously-replicated copy you create explicitly. It serves read-only queries, taking read load off the primary. You can create several. A replica can be in the *same region* (for read scaling) or a *different region* (for disaster recovery and geo-local reads). A cross-region replica can be *promoted* to a standalone primary if the primary region is lost entirely — this is your DR story, distinct from the same-region HA failover. **Replicas are asynchronous: they lag, and you must not read your own writes from them without thinking about it.**

**3. No public IP.** A production database has no public IP. Full stop. In 2026 the connectivity mechanism is **Private Service Connect** (PSC). Cloud SQL publishes a *service attachment*; you create a PSC *endpoint* (a forwarding rule with an internal IP) in your VPC that targets it; your application connects to that internal IP. Nothing routes from the internet. We cover PSC in detail in §1.3 and you build it in Exercise 1.

**4. Point-in-time recovery and a maintenance window.** Automated backups plus write-ahead-log archiving give you PITR — restore to any second in the retention window. You set a maintenance window (a low-traffic hour) so Google's patching happens when you choose, not when it chooses.

Here is the Terraform shape of a production Cloud SQL primary with HA and PSC. You will flesh this out in Exercise 1; read it now for the vocabulary.

```hcl
resource "google_sql_database_instance" "primary" {
  name             = "current-state-primary"
  region           = "us-central1"
  database_version = "POSTGRES_16"

  settings {
    tier              = "db-custom-2-7680" # 2 vCPU, 7.5 GB RAM
    availability_type = "REGIONAL"         # this is what makes it HA (synchronous standby)
    disk_type         = "PD_SSD"
    disk_size         = 20
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true # WAL archiving for PITR
      start_time                     = "03:00"
      transaction_log_retention_days = 7
    }

    ip_configuration {
      ipv4_enabled = false # NO PUBLIC IP. This is the whole point.
      psc_config {
        psc_enabled               = true
        allowed_consumer_projects = [var.project_id]
      }
    }

    maintenance_window {
      day          = 7 # Sunday
      hour         = 4 # 04:00 in the instance's timezone
      update_track = "stable"
    }
  }

  deletion_protection = true
}
```

Three lines carry the senior signal: `availability_type = "REGIONAL"` (that is what makes it HA — `ZONAL` is the cheap, single-zone, no-failover option you use only in dev), `ipv4_enabled = false` with a `psc_config` block (no public IP), and `point_in_time_recovery_enabled = true` (you can recover to a second, not just to last night's backup). A reviewer who sees `ipv4_enabled = true` on a production instance stops reading the rest of your PR.

The cross-region read replica is a second resource that references the primary:

```hcl
resource "google_sql_database_instance" "read_replica" {
  name                 = "current-state-replica-east"
  region               = "us-east1"
  database_version     = "POSTGRES_16"
  master_instance_name = google_sql_database_instance.primary.name

  replica_configuration {
    failover_target = false # set true only if this is your DR-promotion target
  }

  settings {
    tier              = "db-custom-2-7680"
    availability_type = "ZONAL" # a replica is usually zonal; it is not your HA story
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled = false
      psc_config {
        psc_enabled               = true
        allowed_consumer_projects = [var.project_id]
      }
    }
  }
}
```

Note `availability_type = "ZONAL"` on the replica: you don't usually pay for HA on a read replica, because the replica is itself redundancy. Your HA is the synchronous standby on the *primary*; your DR is the *cross-region* replica you can promote.

## 1.3 — Private Service Connect, and why it beats the old VPC peering

For years, the way you reached a private Cloud SQL instance was *private services access* — Google reserves an IP range in your VPC, peers a Google-managed VPC to yours via `servicenetworking`, and the instance gets an IP in the reserved range. It works. It also has three sharp edges that bite at scale:

1. **IP-range exhaustion.** Every service that uses private services access (Cloud SQL, Memorystore, AlloyDB) draws from the same reserved range. Run dozens of instances and you run out of addresses, and re-sizing the range is disruptive.
2. **Non-transitive peering.** VPC peering does not transit. If your app is in a Shared VPC service project and the database peering is on the host project, the routes do not always go where you expect, and debugging "why can't my pod reach the database" becomes a peering-topology exercise.
3. **One peering, shared blast radius.** The single `servicenetworking` peering is a shared dependency; a misconfiguration affects every service behind it.

**Private Service Connect** fixes all three by inverting the model. Instead of peering two VPCs, the *producer* (Cloud SQL) publishes a **service attachment**, and the *consumer* (you) creates a **PSC endpoint** — an internal forwarding rule with an IP you choose, in a subnet you choose, in your VPC. The connection is a point-to-point NAT, not a peering. Each consumer gets its own endpoint; there is no shared range to exhaust, no transitive-peering surprise, and the blast radius is one endpoint.

The chain looks like this:

```text
Cloud SQL instance
  └── publishes a SERVICE ATTACHMENT (a Google-side resource, dns_name + psc_service_attachment_link)
        │
        ▼
Your VPC
  └── PSC ENDPOINT (google_compute_forwarding_rule, load_balancing_scheme = "")
        ├── target = the service attachment
        ├── ip_address = an internal IP you reserve in your subnet
        └── your app connects to THIS internal IP (or a DNS name you publish for it)
```

The Terraform for the consumer endpoint, once the instance exists:

```hcl
# Reserve an internal IP for the PSC endpoint.
resource "google_compute_address" "psc_endpoint_ip" {
  name         = "current-state-psc-ip"
  region       = "us-central1"
  subnetwork   = var.subnet_self_link
  address_type = "INTERNAL"
}

# The PSC endpoint: a forwarding rule that targets Cloud SQL's service attachment.
resource "google_compute_forwarding_rule" "psc_endpoint" {
  name                  = "current-state-psc-endpoint"
  region                = "us-central1"
  network               = var.network_self_link
  ip_address            = google_compute_address.psc_endpoint_ip.id
  load_balancing_scheme = "" # empty string = PSC endpoint, not an LB
  target                = google_sql_database_instance.primary.psc_service_attachment_link
}
```

The empty-string `load_balancing_scheme` is the tell that this is a PSC endpoint and not a load balancer forwarding rule — a detail that trips up everyone the first time. Your application then connects to `google_compute_address.psc_endpoint_ip.address` on port 5432, from inside the VPC, with no public IP anywhere in the path. Exercise 1 builds this end to end and validates it from a private GCE VM with no external IP.

## 1.4 — AlloyDB: Postgres with the storage engine rebuilt

When Cloud SQL stops being enough — and the symptom is usually *operational*, not *throughput* — AlloyDB is the next stop, and it is a far shorter step than the marketing implies because it is *genuinely Postgres*. Your app does not change. Your extensions mostly work. Your `pg_dump` restores. What changes is underneath.

The architecture: AlloyDB separates *compute* from *storage*. The Postgres process runs on a compute node that holds only a cache; durable state — the data blocks and the write-ahead log — lives in a regional, log-structured **storage layer** built on Colossus and replicated across three zones. This buys three things stock Postgres cannot:

1. **Zone-loss survival without a failover.** Because storage is regional and triply-replicated, losing a zone does not lose data and does not require promoting a standby. A new compute node attaches to the surviving storage. Recovery is faster and simpler than Cloud SQL HA's failover.
2. **Horizontal read scaling via read pools.** You attach *read pool instances* — groups of read-only compute nodes that share the same storage. Reads scale by adding nodes; the application points read traffic at the read-pool endpoint. This is cleaner than Cloud SQL's discrete async replicas because the read nodes read the *same* storage, so replica lag is minimal.
3. **The columnar engine.** AlloyDB watches your query patterns and transparently keeps hot columns in an in-memory *columnar* format alongside the row store. Analytical queries (aggregations, scans over a few columns of a wide table) hit the column store and run 10–100× faster than they would on row-oriented Postgres. You do not rewrite queries; the planner chooses the column store when it helps. This is the feature that lets AlloyDB serve a workload that would otherwise force you to ETL into BigQuery.

The Terraform lives in `google-beta` for some of the surface; the cluster-and-instance shape:

```hcl
resource "google_alloydb_cluster" "main" {
  provider   = google-beta
  cluster_id = "current-state-alloy"
  location   = "us-central1"
  network_config {
    network = var.network_self_link
  }
  initial_user {
    user     = "postgres"
    password = var.alloy_password # use Secret Manager in real life; see Week 14
  }
}

resource "google_alloydb_instance" "primary" {
  provider      = google-beta
  cluster       = google_alloydb_cluster.main.name
  instance_id   = "primary"
  instance_type = "PRIMARY"
  machine_config {
    cpu_count = 2
  }
}

resource "google_alloydb_instance" "read_pool" {
  provider      = google-beta
  cluster       = google_alloydb_cluster.main.name
  instance_id   = "read-pool"
  instance_type = "READ_POOL"
  read_pool_config {
    node_count = 2 # scale reads by raising this
  }
  machine_config {
    cpu_count = 2
  }
}
```

The decision signal: **if your workload is "Postgres, but bigger and with the occasional heavy analytical query," AlloyDB is almost always the right answer and Spanner is almost always overkill.** AlloyDB stays single-writer; if you need to scale *writes* horizontally, AlloyDB does not solve that, and you are now in Spanner territory.

## 1.5 — Spanner: the architecture, briefly (Lecture 2 goes deeper on TrueTime)

Spanner's data model: tables, rows, primary keys, secondary indexes, SQL. Underneath, Spanner shards each table into **splits** — contiguous ranges of the primary key — and each split is an independently-replicated **Paxos group** with a leader and (in a multi-region config) replicas in other regions. Writes go to the split's leader, which runs Paxos to commit to a majority of replicas. Reads can be served by any replica for *stale* reads, or by the leader for *strong* reads.

Two consequences flow from this and they are the entire reason Spanner exists:

1. **Writes scale horizontally.** Because the key space is split across many Paxos groups on many machines, write throughput grows as you add nodes. There is no single write process. This is the thing Cloud SQL and AlloyDB cannot do — they have one writer.
2. **External consistency across regions, via TrueTime.** Spanner assigns every transaction a commit timestamp drawn from TrueTime, and uses a *commit-wait* to guarantee that timestamp order matches real-time order globally. The result is **external consistency** (linearizability across the whole database, across regions) without a global lock. Lecture 2 is the full mechanism; for now, hold the claim: *Spanner can give you strong consistency across continents, and that is a thing you genuinely cannot buy anywhere else as a managed service.*

The capacity unit is the **processing unit** (PU); 1000 PU = 1 node. The smallest billable unit is 100 PU. Storage and network are billed separately. A 100-PU single-region instance is roughly \$0.09–\$0.13/hour at 2026 list (region-dependent) — cheap enough to run a one-hour lab for under \$2, expensive enough that a forgotten instance over a weekend is a real \$40+ surprise. **This is why every Spanner lab this week has a teardown gate.**

Schema design has two rules you must internalize before Exercise 2:

- **Do not use a monotonically increasing primary key.** A timestamp or auto-increment key sends every new write to the *same* split (the one holding the highest keys), creating a hotspot that no amount of nodes can relieve. Use a UUID, or hash a prefix of the key, to spread writes across splits.
- **Use `INTERLEAVE IN PARENT` for parent-child data you always read together.** Interleaving physically co-locates child rows with their parent row in the same split, so a "fetch this order and all its line items" read is a single-split operation instead of a cross-split join.

```sql
-- Spanner GoogleSQL dialect. Note: STRING(N), no SERIAL, explicit PRIMARY KEY clause.
CREATE TABLE Customers (
  CustomerId   STRING(36) NOT NULL,  -- a UUID; spreads writes across splits
  Name         STRING(256) NOT NULL,
  CreatedAt    TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (CustomerId);

CREATE TABLE Orders (
  CustomerId   STRING(36) NOT NULL,  -- shared prefix with the parent
  OrderId      STRING(36) NOT NULL,
  TotalCents   INT64 NOT NULL,
  PlacedAt     TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (CustomerId, OrderId),
  INTERLEAVE IN PARENT Customers ON DELETE CASCADE;
```

`Orders` is interleaved in `Customers`: every order row physically lives next to its customer row, so reading a customer and their orders touches one split. `ON DELETE CASCADE` ties their lifecycle. There is no `SERIAL` — you generate keys application-side (UUIDs) or use a sequence with the bit-reversed positive sequence kind that Spanner provides to avoid hotspots.

## 1.6 — When Spanner's cost is justified — and when it is theatre

Here is the decision, stated as bluntly as the architecture review demands. You go to Spanner when **at least one** of these is true and you can defend it:

- **You need horizontal write scale.** Your write throughput exceeds what one big Cloud SQL or AlloyDB primary can sustain (tens of thousands of writes/sec, sustained, with headroom), and sharding it yourself would be a multi-quarter project that reinvents what Spanner gives you. *This is rare.* Most workloads that claim it are actually read-bound and would be fine with AlloyDB read pools.
- **You need multi-region synchronous strong consistency.** You have users on two continents who must see the same data with no read-staleness window, and you cannot tolerate the failover gap of a primary/replica setup. A bank ledger spanning regions, a global inventory that cannot oversell, a multi-region session store that must be authoritative everywhere. *This is the case where Spanner has no peer.*
- **You need five-nines availability with no failover.** Spanner's multi-region configs offer a 99.999% SLA because there is no failover step — the database survives a region loss by continuing to serve from the surviving regions' Paxos replicas. If your business genuinely needs that number, Spanner is the managed answer.

You do **not** go to Spanner when:

- **You picked it because "global, unlimited scale" sounded good in the design doc.** That is theatre. Price a 100-PU Spanner instance against a `db-custom-2-7680` AlloyDB or Cloud SQL instance for the same workload, and unless one of the three justifications above holds, you are paying a premium for capability you will never use.
- **Your workload is analytical.** Spanner is bad at `SELECT *`, bad at large scans, bad at ad-hoc aggregation. If the query surface is analytical, none of this week's databases is the answer — BigQuery is. Putting an analytical workload on Spanner is the most expensive way to do it slowly.
- **You have large transactions.** Spanner limits transaction size (mutations per commit, locked rows). A workload that wants to update a million rows in one transaction fights Spanner the whole way; Postgres shrugs.
- **You are pre-product-market-fit.** A startup with 200 users does not need horizontal write scale. It needs the cheapest correct database, which is Cloud SQL, and the engineering time it would spend learning Spanner's quirks is better spent shipping.

The senior framing: **Spanner is a capability purchase, not a scale upgrade.** You buy it for the *specific* capability (horizontal writes, multi-region strong consistency, no-failover availability), and if you cannot name the capability, you are buying theatre. The cost is justified exactly when the capability is load-bearing and not before.

## 1.6a — The NoSQL neighbors: Firestore, Bigtable, and Memorystore

The relational decision is most of this week, but a complete answer in an architecture review names the NoSQL stores too, because sometimes the right answer is "not a relational database at all." Three GCP services round out the picture.

**Firestore** is a document database: collections of documents, each a JSON-ish tree, with strong consistency, automatic multi-region replication, and *real-time listeners* (a client subscribes to a query and gets pushed updates as data changes). It is the right answer for application state that is naturally hierarchical and benefits from live sync — a collaborative editor's presence, a mobile app's per-user data, a chat app's message threads. It is the *wrong* answer for analytical scans (it has no `GROUP BY` over a collection), for workloads with hot single documents (a counter everyone increments), and for anything that wants rich relational joins. Decision tell: *do clients need to subscribe to live changes, and is the data document-shaped?* → Firestore.

**Bigtable** is a wide-column store: a giant sorted map from a row key to a set of column families, single-digit-millisecond reads and writes at petabyte scale, *eventual* consistency across clusters in a multi-cluster (replicated) setup. Row-key design is the *entire* game — there are no secondary indexes, so every access pattern must be served by the row key's structure (reverse-timestamp suffixes for "latest first," tenant prefixes for isolation, hashed prefixes to avoid hotspots). It is the right answer for high-throughput time-series (metrics, IoT telemetry, ad-tech event streams) and high-throughput key-value lookups where you control the access pattern. It is the wrong answer for ad-hoc queries, low-volume apps (the cluster minimum makes it expensive at small scale), and anything needing transactions across rows. Decision tell: *sustained tens-of-thousands-of-writes-per-second, single known access pattern, time-series or key-value?* → Bigtable.

**Memorystore** (Redis or the Valkey fork GCP added after the Redis license change) is a cache, not a database. It sits *in front of* any of the above to absorb hot reads. The rule: **Memorystore is not a system of record.** You put derived or cached state in it (cache-aside: read from Memorystore, miss → read the database, populate Memorystore), and you must be able to lose the entire cache without losing data. Standard-tier Memorystore offers HA with a replica and automatic failover; it is still a cache. Decision tell: *are we reading the same hot keys over and over and can we tolerate losing the copy?* → put Memorystore in front of the real database.

The complete decision now has a NoSQL branch: before you even reach the relational rubric, ask whether the workload is document-shaped with live sync (Firestore), wide-column high-throughput (Bigtable), purely analytical (BigQuery), or genuinely relational (the rest of this lecture). Most line-of-business workloads are relational; knowing the others lets you recognize the minority that aren't.

## 1.7 — The decision rubric

Make the decision repeatable. Score the workload on seven axes; the highest-weighted unmet need drives the answer.

| Axis | Question | Cloud SQL | AlloyDB | Spanner |
|---|---|---|---|---|
| **Consistency** | Strong, across regions, no staleness window? | single-region strong; cross-region async | single-region strong | **global strong (external)** |
| **Write scale** | Beyond one big machine, sustained? | no (one writer) | no (one writer) | **yes (sharded writers)** |
| **Read scale** | Many read replicas, low lag? | async replicas (lag) | **read pools (low lag)** | replicas (stale/strong) |
| **Region footprint** | Multi-region authoritative? | DR via promotion | regional | **multi-region native** |
| **Query surface** | Rich Postgres SQL + extensions? | **full Postgres** | **full Postgres** | Spanner SQL / PG dialect (subset) |
| **Ops budget** | Tolerable on-call burden? | low (managed) | **very low (no failover)** | very low (but new skills) |
| **Dollar budget** | Cost per unit of capacity? | **cheapest** | mid | **most expensive** |

The reading: if the workload needs full Postgres, is cheap, and is single-region — **Cloud SQL**. If it needs full Postgres, is growing, wants low-lag read scale or has analytical queries, and you want to stop paging — **AlloyDB**. If — and only if — it needs horizontal write scale, multi-region strong consistency, or no-failover five-nines — **Spanner**. Write the justification as one sentence naming the deciding axis and the runner-up: *"AlloyDB, because the workload needs low-lag read scale and an occasional analytical query but stays single-region single-writer; runner-up Cloud SQL, rejected because read-replica lag would violate the read-your-writes requirement on the dashboard."* Exercise 3 makes you write three of these.

## 1.7a — A worked decision, with numbers

Theory is cheap; let us run the rubric on a real workload and put dollars next to it, because "with a budget and a justification" is the actual deliverable an architecture review wants.

**The workload.** A B2B SaaS product — project-management software, 3,000 paying teams, all in North America. The database holds projects, tasks, comments, and attachments-metadata. Traffic is read-heavy (a 20:1 read:write ratio): people look at boards far more than they edit them. There is a "team activity dashboard" that runs a moderately heavy aggregation (tasks-by-status, velocity-over-time) every time someone opens it. Peak write rate is ~400 writes/sec. Data size is ~300 GB and growing ~10 GB/month. The product owner wants the database bill under \$600/month and the on-call burden low. No multi-region requirement today; a European expansion is "maybe next year."

**Run the axes:**

- **Consistency:** single-region strong is enough today. No cross-region authoritative requirement. → does *not* point to Spanner.
- **Write scale:** 400 writes/sec is trivial for one machine. A `db-custom-4-16384` Cloud SQL primary handles this with headroom. → does *not* point to Spanner.
- **Read scale:** read-heavy, and the dashboard aggregation is getting slower as data grows. This is the axis that is starting to hurt. → points toward AlloyDB (read pools + columnar engine) or Cloud SQL read replicas.
- **Region footprint:** single-region. The "maybe next year" Europe expansion is a *future* consideration, not a present requirement — and you do not buy multi-region capability a year early. → note it in the exit plan, do not act on it.
- **Query surface:** full Postgres, including the dashboard's aggregations and the app's relational joins. → Cloud SQL and AlloyDB both qualify; Spanner's subset dialect would be friction.
- **Ops budget:** low burden wanted. AlloyDB's no-failover zone-loss survival is attractive. → mild point for AlloyDB.
- **Dollar budget:** under \$600/month.

**Price it (2026 list, order-of-magnitude):**

- **Cloud SQL** `db-custom-4-16384` regional HA + a same-region read replica + 300 GB SSD ≈ \$450–550/month. Within budget. The dashboard aggregation stays slow (row-oriented Postgres).
- **AlloyDB** primary (4 vCPU) + a 2-node read pool + 300 GB ≈ \$550–700/month. At or slightly over budget. The dashboard aggregation gets 10–50× faster (columnar engine) and reads scale on the pool with low lag.
- **Spanner** 100 PU is too small for the data + a production footprint; a realistic single-region node ≈ \$650+/month *and* you rewrite the dashboard aggregations (Spanner is bad at them) and lose full Postgres. Over budget, worse query fit, no capability you need.

**The decision and justification:**

> **Cloud SQL** for launch (`db-custom-4-16384` regional HA + one same-region read replica, ~\$500/month), with the dashboard aggregation moved to the read replica to keep it off the primary. **Deciding axis: dollar budget under a single-region, single-writer, full-Postgres workload — Cloud SQL is the cheapest correct answer.** Runner-up **AlloyDB**, rejected *for now* on budget and held in reserve: the moment the dashboard aggregation's latency becomes a complaint or the read replicas can't keep lag low, we migrate to AlloyDB for the columnar engine and low-lag read pools — a `pg_dump`/restore-grade move, not a rewrite. **Spanner is rejected outright:** we have no horizontal-write-scale or multi-region-strong-consistency requirement, so it would be a capability purchase with no capability bought. The "maybe Europe next year" note lives in the exit plan; if it becomes real and *authoritative-in-both-regions* is required, that is the conversation where Spanner re-enters — not before.

Notice the shape of a good answer: it names the deciding axis, prices the alternatives, gives a *trigger* for the runner-up ("the moment the dashboard latency becomes a complaint"), and explicitly rejects Spanner with a reason. That is what "a budget and a justification" means, and it is what Exercise 3 makes you produce three times.

## 1.8 — The reflexes to internalize this week

- **Reach for Cloud SQL first.** It is the right answer most of the time. Justify any move up from it.
- **No public IP on a production database, ever.** `ipv4_enabled = false`, PSC endpoint, connect from inside the VPC.
- **`availability_type = "REGIONAL"` is what HA *means*.** A `ZONAL` instance has no standby and no failover. Know which you wrote.
- **HA is not read scaling, and a read replica is not HA.** The synchronous standby protects against zone loss; the async replica scales reads and is your DR-promotion target. Two different resources, two different jobs.
- **Spanner is a capability purchase.** Name the capability (horizontal writes, multi-region strong consistency, no-failover five-nines) or do not buy it.
- **If the workload is analytical, the answer is BigQuery, not any database in this lecture.**
- **Arm the billing alert before you provision Spanner.** Every time. The teardown gate is graded.
- **Write the one-sentence justification.** Deciding axis plus rejected runner-up. If you cannot write it, you have not made the decision — you have made a guess.

These reflexes are the whole methodology of the database decision. Lecture 2 goes underneath the Spanner claim — how TrueTime actually delivers external consistency, and how CockroachDB and YugabyteDB get most of the way there without an atomic-clock fleet — so that when you say "Spanner, because multi-region strong consistency" in a review, you can defend the *because*.

---

## Lecture 1 — checklist before moving on

- [ ] I can name the one-paragraph difference between Cloud SQL, AlloyDB, and Spanner without looking.
- [ ] I can draw the production Cloud SQL shape: HA (regional, synchronous standby), cross-region read replica, PSC (no public IP), PITR.
- [ ] I can explain why PSC beats the old `servicenetworking` VPC peering (no IP exhaustion, no transitive-peering surprises, per-consumer blast radius).
- [ ] I can state the three justifications for Spanner and the four anti-patterns.
- [ ] I can fill in the seven-axis decision rubric and write a one-sentence justification naming the deciding axis and the rejected runner-up.
- [ ] I have armed a \$10 billing budget alert on my project *before* the Spanner exercises.

If any box is unchecked, re-read that section. Lecture 2 assumes you can already make the Cloud SQL / AlloyDB / Spanner call on a workload.

---

**References cited in this lecture**

- Spanner — overview and architecture: <https://cloud.google.com/spanner/docs/whitepapers/life-of-reads-and-writes>
- Spanner — TrueTime and external consistency: <https://cloud.google.com/spanner/docs/true-time-external-consistency>
- Spanner — schema design (avoiding hotspots, interleaving): <https://cloud.google.com/spanner/docs/schema-design>
- Spanner — compute capacity (processing units / nodes): <https://cloud.google.com/spanner/docs/compute-capacity>
- Cloud SQL — high availability: <https://cloud.google.com/sql/docs/postgres/high-availability>
- Cloud SQL — read replicas: <https://cloud.google.com/sql/docs/postgres/replication>
- Cloud SQL — Private Service Connect: <https://cloud.google.com/sql/docs/postgres/configure-private-service-connect>
- AlloyDB — overview and architecture: <https://cloud.google.com/alloydb/docs/overview>
- AlloyDB — columnar engine: <https://cloud.google.com/alloydb/docs/columnar-engine/about>
- Pricing calculator (price everything before you provision): <https://cloud.google.com/products/calculator>
