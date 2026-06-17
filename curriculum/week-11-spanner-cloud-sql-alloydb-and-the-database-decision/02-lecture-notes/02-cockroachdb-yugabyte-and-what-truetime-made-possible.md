# Lecture 2 — CockroachDB, YugabyteDB, and What TrueTime Made Possible

> **Reading time:** ~75 minutes. **Hands-on time:** ~15 minutes (you read the TrueTime section of the Spanner paper and sketch the commit-wait diagram yourself).

Lecture 1 ended on a claim you took on faith: *Spanner can give you strong consistency across continents, and that is a thing you genuinely cannot buy anywhere else as a managed service.* This lecture earns the claim. We go underneath Spanner to the mechanism — **TrueTime** and the **Paxos commit-wait** — that turns a fleet of GPS receivers and atomic clocks into external consistency. Then we ask the question every architecture review eventually asks: *if Google could build this, why can't I run the open-source version on my own GKE cluster and skip the GCP bill?* The answer is CockroachDB and YugabyteDB, and the honest comparison is the most valuable thing in this lecture, because it is the comparison that lets you write the **exit plan** — the two paragraphs that say what it would cost to move this workload off Spanner, and therefore whether the lock-in is worth it.

By the end of this lecture you can explain external consistency from first principles, draw the commit-wait, articulate what TrueTime's physical-clock fleet bought that a hybrid-logical-clock cannot quite replicate, name where CockroachDB and YugabyteDB match Spanner and where they don't, and write the exit-plan paragraph a staff engineer will accept.

## 2.1 — The problem TrueTime solves: ordering events across machines

Start with the hard problem. You have a database spread across machines in different datacenters. Transaction T1 commits in `us-central1` and transaction T2 commits in `europe-west1` a moment later. A reader anywhere in the world should see T1 before T2 if T1 *really happened* before T2 in real, physical time. This property — that the database's transaction order matches real-world order — is called **external consistency** (or *linearizability* extended to multi-object transactions). It is the strongest consistency guarantee a distributed database can offer, and it is what lets you reason about your data as if it lived on one machine.

The obstacle is that **clocks on different machines disagree.** Machine A thinks it is 10:00:00.000; machine B, a millisecond of network and a few microseconds of clock drift away, thinks it is 10:00:00.003. If T1 commits on A at A's "10:00:00.000" and T2 commits on B at B's "10:00:00.001," which happened first? You cannot tell from the timestamps, because the clocks lie by an unknown amount. Classic distributed systems solve this by *not using wall-clock time at all* — they use logical clocks (Lamport timestamps) or vector clocks, which capture causal order but cannot relate two *concurrent* events to real time. That is enough for many systems. It is not enough for "did this withdrawal happen before that one" across continents.

## 2.2 — TrueTime: making the clock uncertainty *explicit and bounded*

Google's insight, from the OSDI 2012 Spanner paper, was not to build a perfect clock — that is impossible — but to build a clock that **knows how wrong it might be** and exposes that uncertainty as part of the API. TrueTime's core call is:

```text
TT.now() → TTinterval { earliest, latest }
```

Instead of returning a single instant, `TT.now()` returns an *interval* `[earliest, latest]` and guarantees that the true absolute time lies somewhere inside it. The width of the interval, conventionally written `2ε` (epsilon on each side), is the bounded uncertainty. Google keeps `ε` small — single-digit milliseconds, often under 4ms — by running a fleet of **GPS receivers and atomic clocks** in every datacenter. GPS gives an absolute reference; atomic clocks bridge the gaps when GPS is unavailable and detect when a GPS source has drifted. A daemon on every machine polls multiple time masters, applies Marzullo's algorithm to reject liars, and maintains the local `[earliest, latest]` bound. The hardware is the part you cannot buy: you can run NTP, but NTP gives you a *guess* at the time, not a *proven bound* on how wrong the guess is.

Two helper predicates fall out of the interval:

- `TT.after(t)` — returns true if `t` is *definitely* in the past (i.e., `t < TT.now().earliest`).
- `TT.before(t)` — returns true if `t` is *definitely* in the future (i.e., `t > TT.now().latest`).

These are the only operations Spanner needs to build external consistency.

## 2.3 — The commit-wait: turning bounded uncertainty into a guarantee

Here is the mechanism, and it is beautifully simple once the interval is in hand. When a transaction commits, Spanner:

1. Picks a commit timestamp `s = TT.now().latest` — the *latest* possible current time, i.e., a time that is guaranteed not to be in the past.
2. Performs the Paxos write to a majority of replicas (this takes some real time).
3. **Waits until `TT.after(s)` is true** — that is, waits until the *earliest* possible current time has passed `s`. This is the **commit-wait**. It lasts until the clock uncertainty around `s` has fully elapsed: roughly `2ε`, a few milliseconds.
4. Only then releases locks and reports the commit to the client.

Why does this work? After the commit-wait, *every* clock everywhere is guaranteed to read a time greater than `s`. So any transaction that *starts* after T1 commits will pick a commit timestamp strictly greater than `s`. Timestamp order therefore matches real-time order: if T1 finished before T2 started in the real world, then `s(T1) < s(T2)`, globally, with no coordination between the two transactions beyond reading their local TrueTime. That is external consistency, paid for with a few milliseconds of commit latency.

```text
  T1 commit                          T1 visible
     │   pick s = TT.now().latest        │
     ▼   ┌─── Paxos write ───┐           ▼
     ────┤                   ├── commit-wait (until TT.after(s)) ──┤
         │                   │   (waits out the clock uncertainty)  │
                                                                    │
                                          any T2 that starts here ──┘ picks s' > s, guaranteed
```

The cost is the commit-wait: every read-write transaction pays ~`2ε` (a few milliseconds) of added latency on commit. The *smaller* Google keeps `ε`, the cheaper the commit-wait, which is why the atomic-clock fleet is worth the capital expense — it directly buys lower write latency. **This is the line item you cannot replicate without the hardware**: a smaller, *provably bounded* `ε`.

## 2.3a — A worked example: two withdrawals across two continents

Make the abstraction concrete. A global bank ledger lives in Spanner with replicas in `us-central1` and `europe-west1`. A customer has \$100. Two requests arrive almost simultaneously: T1 (withdraw \$80, submitted from a US ATM) and T2 (withdraw \$50, submitted from an EU ATM). Both must not succeed — that would overdraw the account.

Walk the timeline with TrueTime:

1. T1 arrives at the leader of the account's split (say the leader is in `us-central1`). It reads the balance (\$100), decides \$80 is fine, and prepares to commit. It picks `s1 = TT.now().latest`.
2. T1 runs Paxos to a majority of replicas, then commit-waits until `TT.after(s1)`. During that wait it holds a lock on the account row.
3. T2 arrives — but the account row is *locked* by T1 until T1's commit-wait finishes. T2 blocks.
4. T1's commit-wait elapses; locks release; T1 is committed at timestamp `s1`, balance now \$20.
5. T2 proceeds, reads the *committed* balance (\$20), sees \$50 would overdraw, and is rejected.

The key property: because T1's commit-wait guarantees `s1` is in the global past before locks release, T2 — which started reading after T1 committed — is *guaranteed* to see T1's write, no matter which continent T2's leader sits on. There is no window where T2 reads a stale \$100. That is external consistency doing its job, and it is exactly the guarantee a ledger needs and a single-region Cloud SQL primary with an async cross-region replica *cannot* give you (the EU read could hit a replica lagging behind the US write).

This is the canonical "why Spanner" workload. If you do not have a workload shaped like this — where two geographically-separated transactions must serialize correctly against shared state with no staleness window — you probably do not need Spanner. Most apps tolerate a few hundred milliseconds of cross-region staleness on most data; the ones that genuinely cannot are rare and they are exactly where Spanner earns its price.

## 2.4 — The open-source answer: CockroachDB and YugabyteDB

If you don't have a GPS-and-atomic-clock fleet, can you still build a distributed SQL database with strong-ish consistency? Yes — and two production-grade open-source systems do exactly that. Both are *Spanner-inspired*: range-sharded, consensus-replicated, SQL on top. Where they differ from Spanner is precisely in how they handle time without TrueTime.

**CockroachDB** (Cockroach Labs, written in Go, Raft consensus per range, Postgres wire protocol):

- Uses **hybrid-logical clocks (HLC)** instead of TrueTime. An HLC combines a physical-clock reading with a logical counter, so it tracks causal order *and* stays close to wall-clock time, but it has no *proven* uncertainty bound — it relies on NTP keeping clocks within a configured `max_offset` (default 500ms).
- Provides **serializable isolation by default** — the strongest SQL isolation level, stronger than the `READ COMMITTED` most Postgres deployments actually run. This is genuinely a point *in CockroachDB's favor*: it refuses to let you accidentally run weak isolation.
- Handles the missing TrueTime bound with **uncertainty intervals and read restarts**: when a read encounters a value with a timestamp inside its uncertainty window, it restarts the read at a higher timestamp. This preserves correctness but can add tail latency under clock skew, and CockroachDB is explicit that it gives *single-key linearizability*, not the full external consistency Spanner guarantees across the whole database, unless you accept those restarts.
- Runs anywhere: your laptop, your GKE cluster, AWS, bare metal. Multi-cloud and on-prem are first-class. This is the portability argument.

**YugabyteDB** (Yugabyte, written in C++/Go, Raft consensus per tablet, two API layers — YSQL reusing real PostgreSQL query-layer code, and YCQL a Cassandra-compatible API):

- Also uses **hybrid-logical clocks**, also relies on bounded clock skew via NTP, also offers serializable and snapshot isolation.
- The headline differentiator: **YSQL reuses the actual PostgreSQL source code for the query layer**, so Postgres feature compatibility is unusually high — stored procedures, triggers, extensions, the lot. If "my app uses a lot of Postgres-specific features and I want distributed SQL" is the constraint, YugabyteDB's compatibility is its strongest card.
- Like CockroachDB, runs anywhere; the Yugabyte Anywhere / self-managed story is built for multi-cloud and on-prem.

The shared truth about both: **they get you 90% of what Spanner gives you, on any infrastructure, with no atomic-clock fleet — and the missing 10% is the provably-bounded clock uncertainty that makes Spanner's external consistency airtight and its commit latency low.** For most workloads that 10% does not matter. For a global financial ledger where a clock-skew-induced read-restart at the wrong moment is unacceptable, it does.

## 2.4a — Splits, Paxos groups, and where the leader lives

Underneath both Spanner and the open-source systems sits the same structural idea, and you should be able to draw it because it explains the performance characteristics you will measure.

A table's primary-key space is chopped into contiguous ranges. Spanner calls a range a **split**; CockroachDB calls it a **range**; YugabyteDB calls it a **tablet**. Same concept. Each range is replicated to a handful of machines (3 or 5 typically), and those replicas run a consensus protocol — **Paxos** in Spanner, **Raft** in CockroachDB and YugabyteDB — to agree on the order of writes. One replica is the **leader** (Spanner) or **leaseholder/Raft leader** (CockroachDB); writes go through it.

```text
Table "Orders", PK = (CustomerId, OrderId)
  │
  ├── split A:  keys [aaaa.. , ffff..)   leader in us-central1-a
  │      replicas: us-central1-a (leader), us-central1-b, us-central1-c
  │
  ├── split B:  keys [ffff.. , mmmm..)   leader in us-central1-b
  │      replicas: us-central1-a, us-central1-b (leader), us-central1-c
  │
  └── split C:  keys [mmmm.. , zzzz..)   leader in us-central1-c
         replicas: ...
```

Three consequences fall out, and each is a thing you can observe:

1. **Write throughput scales with the number of splits and their leaders.** Because different key ranges have different leaders on different machines, writes to different parts of the key space proceed in parallel. This is *the* mechanism behind "Spanner scales writes." It is also why a monotonic key kills you (Lecture 1, §1.5): a monotonic key means *every* write targets the single split holding the highest keys, so every write hits one leader on one machine — you have re-created a single-writer database inside a system designed to avoid one.

2. **A cross-split transaction costs more than a single-split one.** If a transaction touches splits A and C, it needs a two-phase commit coordinated across two Paxos/Raft groups. A single-split transaction (e.g., a parent and its interleaved children, all in the same split) needs only that split's consensus. This is why `INTERLEAVE IN PARENT` matters for performance, not just tidiness: it keeps related rows in one split, turning would-be cross-split transactions into single-split ones.

3. **Leader placement drives latency.** In a multi-region config, the leader of a split lives in some region; writes pay a round-trip to the majority of replicas, which may span regions. Reads from a non-leader region can be served as *stale* reads from a local replica (fast, slightly behind) or as *strong* reads that may need to consult the leader (correct, slower). The leader-placement and read-staleness knobs are where multi-region tuning lives. CockroachDB exposes the same trade-offs via "leaseholder preferences" and "follower reads."

The point of this section: Spanner, CockroachDB, and YugabyteDB are structurally the *same kind of system*. Their differences are in the clock (the next sections) and the operational model, not in the fundamental architecture. When you have understood splits + consensus + leader placement, you have understood all three.

## 2.5 — The honest comparison table

| Dimension | Spanner | CockroachDB | YugabyteDB |
|---|---|---|---|
| **Consensus** | Paxos | Raft | Raft |
| **Clock** | TrueTime (GPS + atomic, *bounded* `ε`) | HLC + NTP (`max_offset`, *unbounded* in the worst case) | HLC + NTP |
| **Strongest guarantee** | External consistency (global linearizability) | Serializable isolation; single-key linearizability | Serializable / snapshot isolation |
| **SQL surface** | Spanner SQL + PostgreSQL dialect (subset) | PostgreSQL wire + dialect (broad) | **YSQL reuses real Postgres query layer (broadest)** |
| **Where it runs** | GCP only (managed) | anywhere (self-host or Cockroach Cloud) | anywhere (self-host or Yugabyte managed) |
| **Operational model** | fully managed, no failover, 99.999% multi-region SLA | you run it (or pay Cockroach Cloud) | you run it (or pay Yugabyte) |
| **On-call burden** | near zero | real: upgrades, rebalancing, disk pressure, clock monitoring | real: same shape |
| **Multi-cloud / on-prem** | no (GCP lock-in) | **yes** | **yes** |

Read the table the way a staff engineer does. Spanner wins on operational burden (near zero) and on the provable-bound guarantee. CockroachDB and YugabyteDB win on portability (no cloud lock-in) and, arguably, on default isolation strength (serializable out of the box). The deciding question is almost never "which is technically better" — they are all excellent — it is **"what is the on-call hour cost of self-hosting, and is avoiding GCP lock-in worth paying it?"**

## 2.5a — Isolation levels: the detail that bites in code review

A subtle but consequential difference, and one that an interviewer will probe: what isolation level does each system give you by default, and what does that mean for the application code?

- **Stock PostgreSQL (Cloud SQL, AlloyDB)** defaults to `READ COMMITTED`. This is *weaker* than most engineers realize — it permits non-repeatable reads and write skew within a transaction. Most applications run on it and are fine, because they do not actually have concurrent transactions racing on the same rows; the ones that do must explicitly `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE` or use `SELECT ... FOR UPDATE` locks, and most teams forget to.

- **Spanner** read-write transactions are *serializable* and the database as a whole is *externally consistent* — strictly stronger than serializable, because it also orders transactions by real time globally. You do not opt into it; it is the only option. The cost is the commit-wait latency and the locking that can cause aborts under contention (you must retry aborted transactions — the client libraries do this for you in the `run_in_transaction` helper).

- **CockroachDB** defaults to `SERIALIZABLE` — the strongest SQL isolation level — out of the box, which is a genuine correctness advantage over stock Postgres's `READ COMMITTED`. (Recent CockroachDB also offers `READ COMMITTED` as an opt-in for compatibility, but the default is the strong one.) Like Spanner, it requires retry logic for aborted transactions.

- **YugabyteDB** offers `SERIALIZABLE`, `SNAPSHOT` (repeatable read), and `READ COMMITTED`, with snapshot as a common default for YSQL; you choose per the workload.

The code-review implication: **moving a workload from Cloud SQL `READ COMMITTED` to Spanner or CockroachDB makes your isolation *stronger*, which can surface latent bugs** — transactions that "worked" under the weaker level because the race never actually happened, but which now abort and retry under serializable contention. This is a feature (the strong system is telling you about a real race), but it means a migration's application-lift includes a transaction-retry audit. This is one of the lines in the exit plan you will write in §2.7, and it is the kind of detail that separates "we could migrate" from "we have migrated and here is what broke."

## 2.5b — Does it actually work? The Jepsen record

A claim of "serializable" or "externally consistent" is only as good as the adversarial testing behind it. The industry-standard adversarial test for distributed databases is **Jepsen** (Kyle Kingsbury's framework), which subjects a database to network partitions, clock skew, process pauses, and node failures while a checker verifies that the observed history is consistent with the claimed guarantee.

The relevant facts for an architecture review:

- **CockroachDB and YugabyteDB have both been through public Jepsen analyses**, found bugs (as essentially every database does on first contact with Jepsen), and fixed them in subsequent releases. The reports are public at `jepsen.io/analyses`. The maturity signal is not "Jepsen found nothing" (nobody passes clean the first time) but "Jepsen found issues, they were fixed, and the database now holds its claimed guarantee under the tested faults."
- **Spanner is not publicly Jepsen-tested in the same way** because it is a closed managed service, but Google publishes its own correctness arguments and the system has run Google's own globally-critical workloads (AdWords, Play) for over a decade — a different but substantial form of evidence.

The takeaway for your decision: all three are production-grade and hold their guarantees under realistic faults; "this database is unproven under partition" is not a valid argument against any of them in 2026. The valid arguments remain the ones in the comparison table — operational model, portability, and the clock-bound nuance — not correctness-under-partition.

## 2.6 — What self-hosting actually costs

The seductive pitch for CockroachDB or YugabyteDB on your own GKE cluster is "same capability, no Spanner bill." The hidden cost is on-call hours, and you must price them honestly.

Running a distributed SQL database yourself means *you* own:

- **Version upgrades** across a multi-node cluster, rolling, without downtime, including the schema-change-compatibility dance between versions.
- **Rebalancing and hotspot management** when a range/tablet gets hot — Spanner does this invisibly; you watch dashboards and intervene.
- **Disk pressure and compaction** — LSM-tree storage engines (both use RocksDB-family engines) need monitoring for write amplification and compaction stalls.
- **Clock monitoring** — because correctness depends on NTP keeping skew under `max_offset`, you must alert on clock drift, and a node whose clock drifts too far must be ejected before it serves a stale read.
- **The 2am page** when a node OOMs, a disk fills, or a network partition splits the cluster. Spanner's SRE team owns this; if you self-host, *you* are the SRE team.

A realistic number: self-hosting a production distributed-SQL cluster is **0.5 to 1.5 full-time engineers** of ongoing operational load once you include on-call, upgrades, and capacity planning. At a loaded cost of \$200k+/engineer, that is \$100k–\$300k/year of human cost — which dwarfs the difference between a Spanner bill and a self-hosted infrastructure bill for all but the largest deployments. **The Spanner premium is, in large part, a payment to not staff a distributed-database SRE function.** Whether that trade is worth it depends entirely on whether you already have that function for other reasons.

## 2.6a — Two case studies: when each side wins

Abstractions decide nothing; cases do. Here are two workloads where the comparison resolves in opposite directions, so you can pattern-match in a real review.

**Case A — CockroachDB wins: a fintech that must run on-prem in three jurisdictions.** A payments company operates in the EU, Brazil, and India, each with data-residency laws requiring that citizen data stay on infrastructure inside the country, some of it on-prem in regulated datacenters. Spanner is GCP-only; it cannot run in a Brazilian regulated on-prem datacenter. The data-residency requirement *forces* portability, and the value of "no DB-ops burden" is moot because the company already runs a platform-SRE team for its on-prem footprint. **CockroachDB self-hosted wins** because the deciding constraint (sovereignty/portability) is one Spanner structurally cannot satisfy at any price. The serializable-by-default isolation is a bonus that matches the correctness bar a payments ledger needs.

**Case B — Spanner wins: a gaming company with a global leaderboard and a 6-person backend team.** A mobile game has players worldwide who must see a consistent global leaderboard and an inventory that cannot duplicate items across regions. It genuinely needs multi-region strong consistency (Case 2.3a's shape). The backend team is six engineers shipping game features; they have no appetite to staff a distributed-database SRE function, and there is no sovereignty constraint. **Spanner wins** because the capability is load-bearing (multi-region strong consistency) *and* the premium buys them out of an SRE function they cannot afford to staff. The exit plan notes CockroachDB as the fallback if they ever raise enough to staff database ops and want to cut the bill — with a trigger condition, not a vague aspiration.

The pattern: the deciding factor is rarely raw performance (all three are excellent) — it is **a constraint** (sovereignty, team size, existing SRE capacity) that makes one option structurally right and the other a poor fit. Find the binding constraint and the decision follows.

## 2.6b — What you cannot replicate, restated precisely

It is worth being exact about the irreducible difference, because hand-waving here gets caught in interviews. CockroachDB's own engineers wrote the canonical honest account ("Living Without Atomic Clocks"), and the precise claim is this:

- TrueTime gives a **provably bounded** uncertainty `ε` maintained by dedicated hardware. Spanner *waits out* that bound on commit, so external consistency holds with no extra coordination, and because `ε` is kept small (single-digit ms) the wait is cheap.
- HLC + NTP gives a **best-effort** bound: NTP keeps clocks close, and the system assumes skew stays under a configured `max_offset`. There is no hardware guarantee of that assumption. CockroachDB handles violations defensively — uncertainty intervals trigger read restarts, and a node whose clock drifts beyond `max_offset` *removes itself* from the cluster to preserve correctness.

So the difference is not "Spanner is consistent and Cockroach isn't" — both are consistent under their assumptions. It is that **Spanner's assumption (bounded `ε`) is enforced by hardware, while Cockroach's (bounded NTP skew) is enforced by configuration and a self-eject safety mechanism.** Under normal operation you cannot tell them apart. Under pathological clock skew, Spanner's wait absorbs it and Cockroach's nodes restart reads or eject — a latency cost, not a correctness cost. For 99.9% of workloads this distinction is academic; for the 0.1% running a global ledger at high contention where a clock-skew-induced storm of read restarts would breach an SLO, it is the reason to pay for the hardware-backed guarantee. Name that distinction precisely and you will never be caught out claiming Cockroach is "less consistent" — it isn't; it makes a different, configuration-backed assumption.

## 2.7 — Writing the exit plan

Every architecture in this course ships an exit plan, because *if you cannot write the exit plan, you do not understand the lock-in.* For a Spanner-backed service, the exit plan answers: what would it take to move this off Spanner, and to what?

A good Spanner exit-plan paragraph has four parts. Here is a worked example for the mini-project's current-state service:

> **Exit target: CockroachDB on GKE (or AWS), or YugabyteDB.** Both are distributed-SQL, Raft-replicated, range-sharded — the same architectural shape as Spanner — so the *data model* (interleaved parent-child tables, UUID keys to avoid hotspots) ports almost directly; CockroachDB expresses parent-child locality with `INTERLEAVE`-equivalent column families and prefix keys, and our UUID primary keys already avoid the monotonic-key hotspot both systems share. **Schema lift:** ~1 week to translate the Spanner DDL to CockroachDB DDL and re-run the migration validation harness. **Application lift:** the gRPC service uses the Spanner client library; swapping to a Postgres driver (CockroachDB speaks the Postgres wire protocol) is ~1 week including the read/write-staleness semantics review, because CockroachDB's serializable isolation and read-restart behavior differs from Spanner's external-consistency model and our read paths must be re-validated. **Operational lift:** the real cost — we would take on 0.5–1 FTE of ongoing distributed-DB operations (upgrades, rebalancing, clock monitoring, on-call) that Spanner currently absorbs. **Verdict:** the migration is *mechanically* a few weeks; the *ongoing* cost is an SRE function we do not currently staff. We stay on Spanner while we lack that function and the multi-region strong-consistency requirement holds; we revisit if either (a) we hire a database-SRE team for other reasons or (b) a sovereignty/multi-cloud requirement forces portability.

Notice the shape: name the target, estimate the schema lift, the application lift, and the operational lift *separately*, then give a verdict with a *trigger condition* for revisiting. That is the paragraph a staff engineer accepts. The version that fails review is "we could move to CockroachDB if we had to" — no numbers, no triggers, no understanding of the operational cost.

## 2.7a — The same transaction, three ways (the application-lift made concrete)

The exit plan's "application lift" is abstract until you see the code. Here is the same logical operation — debit an account if it has sufficient balance — on each system, so you can see exactly what changes during a migration.

**Cloud SQL / AlloyDB (stock Postgres), with explicit locking:**

```python
def debit(conn, account_id: str, amount: int) -> bool:
    with conn.transaction():
        with conn.cursor() as cur:
            # SELECT ... FOR UPDATE takes a row lock; on READ COMMITTED you MUST
            # lock explicitly or a concurrent debit can race (write skew).
            cur.execute(
                "SELECT balance FROM accounts WHERE id = %s FOR UPDATE", (account_id,)
            )
            (balance,) = cur.fetchone()
            if balance < amount:
                return False
            cur.execute(
                "UPDATE accounts SET balance = balance - %s WHERE id = %s",
                (amount, account_id),
            )
    return True
```

**Spanner (Python client) — serializable by construction, retries handled by the helper:**

```python
def debit(database, account_id: str, amount: int) -> bool:
    def _txn(transaction):
        rows = list(transaction.execute_sql(
            "SELECT Balance FROM Accounts WHERE Id = @id",
            params={"id": account_id},
            param_types={"id": spanner.param_types.STRING},
        ))
        balance = rows[0][0]
        if balance < amount:
            return False
        transaction.update(
            table="Accounts", columns=("Id", "Balance"),
            values=[(account_id, balance - amount)],
        )
        return True
    # run_in_transaction RETRIES automatically on ABORTED (serialization conflict).
    return database.run_in_transaction(_txn)
```

**CockroachDB (Postgres wire) — serializable by default, but YOU own the retry loop:**

```python
def debit(conn_factory, account_id: str, amount: int) -> bool:
    # CockroachDB can abort a serializable txn with a 40001 retry error under
    # contention. Unlike Spanner's helper, you (or a library) loop on it.
    for _attempt in range(5):
        try:
            with conn_factory() as conn, conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SELECT balance FROM accounts WHERE id = %s", (account_id,))
                    (balance,) = cur.fetchone()
                    if balance < amount:
                        return False
                    cur.execute(
                        "UPDATE accounts SET balance = balance - %s WHERE id = %s",
                        (amount, account_id),
                    )
            return True
        except psycopg.errors.SerializationFailure:
            continue  # retry the whole transaction
    raise RuntimeError("debit exceeded retry budget under contention")
```

Three things jump out, and they are precisely the application-lift line items:

1. **The Postgres version needs explicit `FOR UPDATE`** because `READ COMMITTED` permits the race; the serializable systems do not — moving *to* Spanner or CockroachDB actually lets you *drop* the explicit lock, but you must verify every such site, because a missing lock that "worked" on Postgres was relying on luck.
2. **Spanner's client retries for you** inside `run_in_transaction`; CockroachDB hands you a `40001 SerializationFailure` and you (or a retry library) loop. A migration *to* CockroachDB therefore requires adding retry loops everywhere a write-write conflict can occur — a real, auditable code change.
3. **The query dialects differ** (named params, `update()` mutations vs SQL `UPDATE`), so the data-access layer changes even though the business logic does not.

This is what "~1 week application lift" in the exit plan actually buys: a transaction-by-transaction audit of isolation assumptions and retry handling. Now the estimate is defensible because you have seen the shape of the change.

## 2.8 — Back to the GCP decision, with the comparison in hand

The point of this lecture is not to talk you out of Spanner. It is to let you *defend* Spanner — or reject it — with the open-source comparison in your hand. The decision now has a richer form than Lecture 1's rubric:

- **You need distributed SQL and you are committed to GCP and you want zero database-ops burden →** Spanner. The premium buys you out of the SRE function.
- **You need distributed SQL but you must be portable (multi-cloud, on-prem, sovereignty) →** CockroachDB or YugabyteDB self-hosted (or their managed clouds). You accept the ops burden in exchange for no lock-in.
- **You need maximum Postgres compatibility in a distributed SQL system →** YugabyteDB (real Postgres query layer) edges out the others.
- **You do not actually need distributed SQL →** none of the above; Cloud SQL or AlloyDB, as Lecture 1 concluded. *This remains the most common outcome.* The distributed-SQL conversation is a trap if you walk into it without first ruling out single-writer Postgres.

The reflex: when someone proposes Spanner, your first two questions are "do we actually need horizontal write scale or multi-region strong consistency?" (Lecture 1) and "if we do, is the GCP lock-in worth not staffing a database-SRE team, versus self-hosting CockroachDB/Yugabyte?" (this lecture). If the answers are "yes" and "yes," Spanner is right and you can defend it. If either is "no," you have just saved your company a meaningful sum.

## 2.8a — A decision flowchart you can defend on a whiteboard

Put §2.8's prose into a shape you can draw in 30 seconds during a review:

```text
Need distributed SQL? (horizontal write scale OR multi-region strong consistency)
   │
   ├── NO ──► Single-writer Postgres is enough. Cloud SQL (cheap) or AlloyDB
   │          (read scale / analytics / no-failover). Lecture 1 settles it.
   │          STOP. Do not have the distributed-SQL conversation.
   │
   └── YES ──► Are you committed to GCP, and do you want ~zero DB-ops burden?
                  │
                  ├── YES ──► Spanner. The premium buys you out of a DB-SRE function.
                  │
                  └── NO (need multi-cloud / on-prem / sovereignty, OR you already
                          run a DB-SRE team) ──►
                             │
                             ├── Need maximum Postgres compatibility? ──► YugabyteDB
                             │       (real Postgres query layer)
                             │
                             └── Otherwise ──► CockroachDB
                                     (serializable default, broad adoption, Cockroach Cloud
                                      if you want managed-but-portable)
```

The first branch is the one most teams skip and the one that saves the most money: *most workloads answer "NO" at the top and never need any of the distributed-SQL options.* The discipline is to force that question first, in writing, before anyone whiteboards a sharding scheme.

## 2.8b — The operational reality, side by side

If you do self-host, here is the concrete dashboard difference — the day-2 reality that the FTE estimate in §2.6 abstracts over. With **Spanner** you watch essentially two things in Cloud Monitoring: CPU utilization (scale up processing units when it sustains >65%) and storage (it autoscales but you watch the trend). That is the operational surface. Google handles splits, rebalancing, leader placement, upgrades, and the clock fleet.

With **self-hosted CockroachDB or YugabyteDB** you watch, at minimum:

- **Per-node CPU, memory, and disk** — and you act on disk pressure before compaction stalls (LSM write amplification is real).
- **Range/tablet hotspots** — a hot range needs a manual split or a schema change; the system rebalances but you intervene on pathological cases.
- **Clock skew across nodes** — alert if any node's offset approaches `max_offset`; a node that exceeds it must be ejected or it risks a stale read.
- **Raft leadership distribution** — leadership concentrated on one node is a latency and availability risk.
- **Rolling upgrades** — version-compatibility windows, finalize steps, and the occasional schema-change-during-upgrade restriction.
- **The 2am page** — OOM, disk-full, network partition. You own the runbook and the rotation.

This is not an argument against self-hosting — plenty of teams run CockroachDB happily and value the portability. It is the honest accounting that turns "self-host to save the Spanner bill" into "self-host *and* staff the function to run it," which is the trade the exit plan must price.

## 2.9 — The reflexes to internalize this week

- **External consistency = transaction order matches real-world order, globally.** It is the strongest guarantee, and TrueTime + commit-wait is how Spanner delivers it.
- **TrueTime's value is the *bound*, not the time.** NTP gives a guess; TrueTime gives a proven `[earliest, latest]`. The bound is what enables the commit-wait, and the atomic-clock fleet is what keeps the bound small.
- **The commit-wait costs ~`2ε` of write latency.** Smaller `ε` = cheaper writes. That is why the hardware investment pays off.
- **CockroachDB and YugabyteDB get ~90% of Spanner without the hardware**, using HLC + NTP, and they run anywhere. The missing 10% is the provable bound.
- **Self-hosting distributed SQL costs 0.5–1.5 FTE of ongoing ops.** The Spanner premium largely buys you out of that. Price the human cost, not just the infrastructure cost.
- **The exit plan has four parts:** schema lift, application lift, operational lift, verdict-with-trigger. "We could move if we had to" fails review.
- **Rule out single-writer Postgres first.** The distributed-SQL conversation is a trap if you skip that step.

These reflexes plus Lecture 1's rubric are everything you need to make and defend the database decision. The exercises put numbers on it; the challenge makes you actually migrate Cloud SQL to Spanner and validate it; the mini-project makes you ship the whole thing and write the exit plan.

---

## Lecture 2 — checklist before moving on

- [ ] I can define external consistency and explain why disagreeing clocks make it hard.
- [ ] I can explain `TT.now()` returning an interval `[earliest, latest]` and why the *bound* is the valuable part.
- [ ] I can draw the commit-wait and explain why waiting out `2ε` guarantees global timestamp order.
- [ ] I can name CockroachDB's and YugabyteDB's consensus (Raft), clock model (HLC + NTP), and what each is best at.
- [ ] I can estimate the human cost of self-hosting distributed SQL (0.5–1.5 FTE) and explain what the Spanner premium buys.
- [ ] I can write a four-part exit-plan paragraph (schema lift, app lift, ops lift, verdict-with-trigger).

If any box is unchecked, re-read that section. The challenge this week makes you migrate a real Cloud SQL database to Spanner — you will appreciate the commit-wait the first time you measure write latency.

---

**References cited in this lecture**

- Spanner: Google's Globally-Distributed Database — OSDI 2012 (the paper; read §3 on TrueTime): <https://research.google/pubs/spanner-googles-globally-distributed-database/>
- Spanner — TrueTime and external consistency: <https://cloud.google.com/spanner/docs/true-time-external-consistency>
- Spanner — replication and Paxos: <https://cloud.google.com/spanner/docs/replication>
- CockroachDB — architecture overview: <https://www.cockroachlabs.com/docs/stable/architecture/overview>
- CockroachDB — life of a distributed transaction (HLC, uncertainty intervals): <https://www.cockroachlabs.com/docs/stable/architecture/transaction-layer>
- CockroachDB — "Living without atomic clocks" (the explicit TrueTime comparison): <https://www.cockroachlabs.com/blog/living-without-atomic-clocks/>
- YugabyteDB — architecture and DocDB: <https://docs.yugabyte.com/preview/architecture/>
- YugabyteDB — YSQL and PostgreSQL compatibility: <https://docs.yugabyte.com/preview/api/ysql/>
- Hybrid Logical Clocks paper (Kulkarni et al.): <https://cse.buffalo.edu/tech-reports/2014-04.pdf>
