# Lecture 2 — The Exit Plan: Defending the Cost of Leaving GCP

> **Reading time:** ~70 minutes. **Hands-on time:** ~50 minutes (you draft your own 2-page exit plan against the capstone).

C18 has said it since the README: *every architecture in this course has a documented exit plan, and if you cannot write the exit plan you do not understand the workload*. This is the lecture that cashes that promise. The exit plan is the artifact that most impresses a staff-level reviewer, because writing one forces you to do the thing junior engineers never do — enumerate every managed-service dependency, price its open-source or competitor replacement, and put an honest engineer-week number on the migration. By the end of this lecture you can write the 2-page exit plan for the capstone, and you will understand lock-in as a *spectrum* rather than a binary, which is the framing that lets you make sober platform decisions for the rest of your career.

## 2.1 — Why an exit plan, and why now

People hear "exit plan" and assume it means "we're leaving GCP." It does not. The vast majority of exit plans are never executed. You write one for three reasons, none of which is imminent migration:

1. **Negotiating leverage.** When your committed-use discount renewal comes up and the account team knows you *could* leave in two quarters for \$X, your discount is better. A credible exit plan is worth real money at the negotiating table even if you never use it.
2. **Risk management.** Clouds change pricing, deprecate services, and have outages. A board or a CTO who is told "we are all-in on GCP" will ask "what happens if Google triples the Spanner price or sunsets a service we depend on?" The exit plan is the answer. "Here is what it would cost and how long it would take" is a far better answer than a shrug.
3. **It proves you understand the system.** This is the reason that matters for *you*, this week. You cannot price the replacement for a service you do not understand. Writing the exit plan is a comprehension test you administer to yourself. Every line you cannot fill in is a part of your own system you do not actually understand.

The honesty rule is absolute: an exit plan that says "easy, we'd just lift-and-shift to AWS in a sprint" is a lie that destroys your credibility. The real number for the capstone is on the order of **8–16 engineer-weeks** for a small team to reach functional parity on a different substrate, and the value of the exit plan is in being specific about *where* those weeks go.

## 2.2 — Lock-in is a spectrum, not a binary

The single most useful mental model in this lecture: rank every dependency on a **portability spectrum** from "trivial to move" to "you are effectively married to this." For each component of the capstone, ask one question: *how much of this is a standard interface versus a proprietary one?*

| Tier | Meaning | Capstone examples |
|---|---|---|
| **Green — commodity** | Standard interface; many implementations exist; moving is config, not code. | GKE (it's Kubernetes — `kubectl apply` works anywhere), Cloud SQL Postgres (it's Postgres), GCS (it's S3-compatible-ish via the XML API), Cloud DNS, the HTTPS load balancer (any cloud has one). |
| **Yellow — portable model, proprietary runtime** | Your *code* targets an open model, but you run it on a proprietary engine. Moving means changing the runner, not rewriting the logic. | Dataflow (your pipeline is **Apache Beam** — it runs on Flink or Spark too), Cloud Run (your service is a **container** — Knative or plain k8s runs it), OpenTelemetry (the whole point of OTel is vendor-neutral export). |
| **Orange — proprietary, with a real OSS analog** | No standard interface, but a credible open-source or competitor replacement exists with meaningful migration work. | BigQuery → Trino + Iceberg, Pub/Sub → Kafka, Vertex AI Endpoint → vLLM on a GPU pool, Memorystore → self-hosted Redis/Valkey. |
| **Red — proprietary, hard to replace at parity** | The service gives you a guarantee that is genuinely hard to reproduce. Leaving means accepting a weaker guarantee or building something large. | Spanner (external consistency across regions via TrueTime — CockroachDB/Yugabyte get *close* but not identical), BigQuery's serverless scale-to-zero economics, Cloud Armor's managed WAF + bot management. |

The discipline this table forces: **architect so that your red-tier dependencies are few, isolated, and load-bearing for a reason you can defend.** The capstone has exactly one true red dependency — Spanner's cross-region external consistency — and it is fine to depend on it *if you can say why it's worth being married to it.* If you cannot, you over-engineered, and the exit plan is where you find out.

The green and yellow tiers are why your exit plan is 8–16 weeks and not 8–16 months. You designed for portability without thinking of it as portability: you used Kubernetes, you wrote Beam, you used containers, you emitted OTel. That was good engineering for its own sake; the side effect is that most of your system is already portable.

## 2.3 — The exit-plan structure (the 2-page template)

Two pages. Reviewers will not read more, and the discipline of two pages forces you to price, not to ramble. The structure:

### Page 1 — Inventory and target

**Section 1: Dependency inventory.** A table, one row per managed GCP service the system uses, with its portability tier and the proposed replacement. This is the table in §2.2 applied to your *specific* system.

**Section 2: Target architecture.** One paragraph and (ideally) a second diagram: "If we left GCP for AWS, here is the mapping." or "If we left for self-hosted, here is the stack." Pick *one* target for the 2-page version; the stretch goal is to do both.

**Section 3: What we keep.** Critically, name what does *not* move. Your application code (Python services, the Beam pipeline logic, the gRPC proto definitions, the SQL schema) is largely portable. Saying "the business logic is 9,000 lines of Python and Beam that moves nearly unchanged" is the part that makes the estimate credible.

### Page 2 — Cost and effort

**Section 4: Migration effort, by component.** A table with engineer-week estimates per component, summed. This is the number the CTO reads.

**Section 5: Steady-state cost delta.** Does the target run cheaper or more expensive than GCP at the same scale? Self-hosted Kafka is cheaper in raw compute but more expensive in ops headcount. Be honest about *both*.

**Section 6: Risks and one-way doors.** What you would lose. The capstone's honest answer: you lose Spanner's external consistency (CockroachDB gives you serializable, not the same TrueTime guarantee) and you take on operating a Kafka cluster, an Iceberg catalog, and a GPU autoscaler that Google was running for you.

## 2.4 — Pricing the replacements: the capstone, component by component

This is the substance. We walk each capstone component, name the replacement, and estimate the work. The estimates are for a competent two-engineer team and assume the application code already exists (it does — you wrote it).

### Edge (LB + Cloud Armor + CDN) — Green/Orange — ~1 week

The HTTPS load balancer maps to an AWS Application Load Balancer or an NLB+ALB pair; the migration is Terraform, not code. **Cloud CDN → CloudFront** is config. The harder part is **Cloud Armor → AWS WAF**: your custom CEL rule has to be rewritten in AWS WAF's rule syntax, and the managed bot-management has a rough analog but not an identical one. Budget a few days to port and re-test the WAF rules and the rate-limit policy. Self-hosted is harder — you would run Envoy or HAProxy plus a WAF like Coraza, and you own the bot problem yourself.

### Ingest (Cloud Run) — Yellow — ~0.5 week

Cloud Run runs a container. On AWS it becomes a container on **ECS Fargate** or **App Runner**, or a Knative service on EKS. The service code does not change. What changes: the `min-instances` / `max-instances` autoscaling config and the IAM identity binding. Half a week, mostly re-testing the autoscaling behavior under load.

### Stream (Pub/Sub) — Orange — ~2 weeks

Pub/Sub → **Kafka** (self-hosted via Strimzi on Kubernetes, or **Amazon MSK**, or Confluent Cloud). This is real work. Pub/Sub's ordering keys map to Kafka partitions; its dead-letter topic maps to a DLQ pattern you implement; its at-least-once delivery maps to Kafka consumer-group semantics; its scale-to-zero economics do *not* map at all — a Kafka cluster has a fixed minimum cost. Your *publisher* and *consumer* code changes from the Pub/Sub client to the Kafka client, which is a known, bounded change. The two weeks go to: standing up and tuning the cluster, re-implementing the DLQ-and-replay, and load-testing partition balance under 10x.

### Process (Dataflow / Apache Beam) — Yellow — ~1 week

This is your best portability story and you should lead with it. Your pipeline is **Apache Beam**. Beam's portability layer means the *same pipeline code* runs on the **Flink runner** or **Spark runner** instead of the Dataflow runner — see the Beam capability matrix in `resources.md`. You change the runner flag and the I/O connectors (the Pub/Sub source becomes a Kafka source, the BigQuery sink becomes an Iceberg sink). The windowing, the enrichment, the triggers — all unchanged. One week, most of it spent on the I/O connector swap and re-validating exactly-once into the new sink.

### Process sink + analytics (BigQuery) — Orange/Red — ~3 weeks

BigQuery is the hardest analytical piece. The open replacement is **Apache Iceberg** tables on object storage, queried by **Trino** (or DuckDB for smaller scale). The migration: your partitioned-clustered table schema maps to Iceberg partition specs; your SQL mostly works in Trino (it's ANSI-ish) but some BigQuery functions and the `_PARTITIONTIME` pseudo-column do not, so queries need an audit; and you lose BigQuery's serverless scale-to-zero — you now run and size a Trino cluster. Three weeks: schema port, query audit and rewrite, Trino cluster sizing, and the historical-data backfill from BigQuery export to Iceberg. The *economic* change is significant and goes in Section 5: BigQuery's "pay only for the bytes you scan, scale to zero between queries" is genuinely hard to reproduce; a Trino cluster has a floor cost.

### Serve — current state (Spanner gRPC) — Red — ~3 weeks

This is the one true red dependency. Spanner gives you **external consistency** (linearizable across regions, via TrueTime). The honest replacements:

- **CockroachDB** — serializable isolation, Postgres wire protocol, multi-region. The *closest* analog and the one to lead with. Migration: your gRPC service's data-access layer changes from the Spanner client to a Postgres client (CockroachDB speaks pgwire), the DDL ports with edits, and you re-validate your transactions under contention. You get serializable, which is strong, but **not** Spanner's external-consistency-with-bounded-clock-uncertainty guarantee — and the exit plan must say so plainly.
- **YugabyteDB** — similar tradeoffs.

Three weeks: schema and transaction port, re-validation of the consistency assumptions your application actually relies on (most applications need serializable, not external consistency — finding out which you need is the real exercise), and operating the cluster.

### Serve — model (Vertex AI Endpoint + Gemini fallback) — Orange — ~2 weeks

The open-weights model on the Vertex AI Endpoint moves to **vLLM** (or TGI) on a **GKE/EKS GPU node pool** — you already cost-compared exactly this in Week 12, so the analysis is done; this is execution. The Gemini API fallback is harder: there is no drop-in open replacement for a frontier closed model, so the exit plan must say "we either accept a quality regression by falling back to a second open model, or we keep one cross-cloud call to a frontier API and accept that single non-portable dependency." Naming that you *keep one deliberate non-portable call* is a mature answer. Two weeks: stand up vLLM with autoscaling, port the circuit-breaker fallback logic, re-benchmark p50/p99.

### Observability (OpenTelemetry) — Green — ~0.5 week

This is the easiest, by design. OpenTelemetry is vendor-neutral; the *only* thing that changes is the OTLP exporter endpoint. Point it at **Grafana Cloud / Tempo / Mimir / Loki**, or self-host the LGTM stack, instead of Cloud Trace / Monitoring / Logging. Your instrumentation code does not change at all. This is the payoff for having used OTel instead of a vendor SDK in Week 13.

### Security, IAM, networking — Yellow/Orange — ~1.5 weeks

WIF → AWS IAM roles / OIDC, Secret Manager → AWS Secrets Manager or Vault, VPC SC → AWS resource policies + VPC endpoints + SCPs, Binary Authorization → cosign + an admission controller (Kyverno/OPA Gatekeeper). All have analogs; none is a one-to-one port. A week and a half to re-establish the security posture.

## 2.5 — The summed estimate and what it teaches

Add it up:

| Component | Tier | Engineer-weeks (to AWS / self-hosted) |
|---|---|---|
| Edge (LB / Armor / CDN) | Green/Orange | 1.0 |
| Ingest (Cloud Run → container) | Yellow | 0.5 |
| Stream (Pub/Sub → Kafka) | Orange | 2.0 |
| Process (Beam runner swap) | Yellow | 1.0 |
| Analytics (BigQuery → Iceberg+Trino) | Orange/Red | 3.0 |
| Serve current-state (Spanner → CockroachDB) | Red | 3.0 |
| Serve model (Vertex → vLLM) | Orange | 2.0 |
| Observability (OTel re-point) | Green | 0.5 |
| Security / IAM / networking | Yellow/Orange | 1.5 |
| Integration, testing, cutover, rollback plan | — | 2.5 |
| **Total** | | **~17 engineer-weeks** |

Two things jump out, and both belong in your exit plan's conclusion:

1. **The cost is concentrated in three components** — Pub/Sub, BigQuery, and Spanner — which together are ~8 of the 17 weeks. Those are your orange/red tiers. Everything else is cheap to move *because you architected on open interfaces*. The lesson: lock-in cost is dominated by a handful of proprietary services, and you can manage it by being deliberate about exactly those.

2. **The application code barely moves.** Of the 17 weeks, almost none is rewriting business logic. It is infrastructure re-plumbing and re-validation. That is the difference between a system designed by someone who read this course and one that hard-codes BigQuery SQL into every service: the latter's exit plan is 50 weeks, because the proprietary dependency leaked into the application layer.

## 2.6 — Steady-state cost delta: be honest in both directions

Section 5 of the plan is where junior exit plans cheat. "Self-hosted is cheaper" is half the truth. The full truth has two columns:

- **Compute/storage cost.** Self-hosted Kafka + Trino + CockroachDB + vLLM on reserved instances *can* be cheaper than the managed equivalents at steady high utilization — that is real. Spot/reserved EC2 plus your own operators beats per-request managed pricing past a utilization threshold.
- **Operational cost.** You now run a Kafka cluster, an Iceberg catalog and compaction jobs, a Trino cluster, a distributed SQL database, and a GPU autoscaler. That is, conservatively, **1–2 full-time SRE-equivalents** of ongoing work that Google was doing for you invisibly. At a loaded cost of ~\$250k/engineer, that is \$250k–\$500k/year of operational cost that does not show up on any cloud bill.

The honest conclusion for a system at the capstone's scale (~\$500/month on GCP): **leaving is almost certainly not worth it at this scale.** The managed services are cheap relative to the salary cost of operating their replacements. Self-hosting starts to win only at much larger scale, where the managed-service bill is large enough to fund a dedicated platform team that would exist anyway. *That* is the sophisticated takeaway, and stating it — "at our scale the exit plan is a negotiating tool and a risk hedge, not an action item; it would become an action item around \$N/month or if the org grew a platform team for other reasons" — is exactly what a staff engineer wants to hear.

## 2.7 — Drafting your own: the worked outline

Here is the skeleton you fill in for the capstone, in Markdown, ready to drop into `EXIT-PLAN.md`:

```markdown
# Exit Plan — Realtime Event Pipeline at Scale

## 1. Why this document exists
Negotiating leverage + risk hedge + comprehension check. Not an action item at current scale.

## 2. Dependency inventory
| GCP service | Portability tier | Replacement | Notes |
|---|---|---|---|
| HTTPS LB + Cloud Armor + CDN | Green/Orange | ALB + AWS WAF + CloudFront | Rewrite custom CEL rule |
| Cloud Run (ingest) | Yellow | ECS Fargate / Knative | Container moves unchanged |
| Pub/Sub | Orange | Kafka (MSK / Strimzi) | Ordering keys -> partitions; no scale-to-zero |
| Dataflow (Beam) | Yellow | Beam on Flink/Spark | Runner flag + I/O connectors only |
| BigQuery | Orange/Red | Iceberg + Trino | Query audit; lose serverless economics |
| Spanner | Red | CockroachDB | Serializable, NOT external consistency |
| Vertex AI Endpoint | Orange | vLLM on GPU pool | Gemini fallback has no OSS drop-in |
| OpenTelemetry export | Green | Grafana LGTM | Re-point OTLP endpoint only |
| WIF / Secret Mgr / VPC SC / BinAuthz | Yellow/Orange | IAM/OIDC, Vault, SCPs, cosign+Kyverno | Re-establish posture |

## 3. Target architecture (pick one: AWS shown)
[one paragraph + diagram]

## 4. What we keep
~9k lines of Python services + Beam pipeline + gRPC protos + SQL schema move nearly unchanged.

## 5. Effort estimate
[the summed table from 2.5] -> ~17 engineer-weeks.

## 6. Steady-state cost delta
Compute may be cheaper at high utilization; +1-2 SRE FTE in ops cost.
Net at current scale: leaving is not worth it. Threshold to revisit: ~$N/month.

## 7. Risks / one-way doors
Lose Spanner external consistency; take on operating Kafka/Trino/CRDB/vLLM.
```

That is the whole artifact. Two pages when rendered. Every cell is a claim you can defend in the review.

## 2.6b — Why the application code "barely moves": the isolation pattern

The claim in §2.5 that does the most work — "the application code barely moves" — is only true if you *built* it to be true. The mechanism is a boring, decades-old discipline: put the proprietary dependency behind an interface that your business logic depends on, so swapping the implementation never touches the logic. For the capstone's gRPC service, that means the handler depends on a `StateRepository` interface, not on the Spanner client directly. Here is the Go that makes the exit cheap:

```go
package state

import "context"

// StateRepository is the seam the exit plan relies on. Business logic depends on
// this interface; nothing in the handlers imports the Spanner client directly.
type StateRepository interface {
	IncrementCounter(ctx context.Context, tenant, metric string, delta int64) error
	GetTenantCounters(ctx context.Context, tenant string) (map[string]int64, error)
}

// Handler holds the interface, not a concrete database. This is the whole trick:
// to migrate off Spanner you write one new implementation of StateRepository and
// change one line of wiring in main(). The handler code does not change at all.
type Handler struct {
	repo StateRepository
}

func NewHandler(repo StateRepository) *Handler {
	return &Handler{repo: repo}
}
```

The Spanner implementation lives in its own file and is the *only* place the Spanner client is imported:

```go
package state

import (
	"context"

	"cloud.google.com/go/spanner"
	"google.golang.org/grpc/codes"
)

// SpannerRepository is the only file in the codebase that imports the Spanner
// client. Replacing it with a CockroachRepository (pgx) is a self-contained change.
type SpannerRepository struct {
	client *spanner.Client
}

func NewSpannerRepository(client *spanner.Client) *SpannerRepository {
	return &SpannerRepository{client: client}
}

func (r *SpannerRepository) IncrementCounter(ctx context.Context, tenant, metric string, delta int64) error {
	// Spanner's GoogleSQL dialect has no `ON CONFLICT`; the upsert verb is
	// `INSERT OR UPDATE`. And because that statement always overwrites the listed
	// columns (it cannot reference the existing value the way Postgres's
	// `DO UPDATE SET value = value + @delta` does), an *increment* must read the
	// current value inside the transaction and write back the sum. This is
	// exactly the kind of dialect divergence that the exit-cost argument is about:
	// the DDL and DML do not port to Postgres-wire databases unedited.
	_, err := r.client.ReadWriteTransaction(ctx, func(ctx context.Context, txn *spanner.ReadWriteTransaction) error {
		var current int64
		row, err := txn.ReadRow(ctx, "counters",
			spanner.Key{tenant, metric}, []string{"value"})
		switch {
		case spanner.ErrCode(err) == codes.NotFound:
			current = 0
		case err != nil:
			return err
		default:
			if err := row.Columns(&current); err != nil {
				return err
			}
		}
		stmt := spanner.Statement{
			SQL: `INSERT OR UPDATE INTO counters (tenant, metric, value)
			       VALUES (@tenant, @metric, @value)`,
			Params: map[string]any{"tenant": tenant, "metric": metric, "value": current + delta},
		}
		_, err = txn.Update(ctx, stmt)
		return err
	})
	return err
}

func (r *SpannerRepository) GetTenantCounters(ctx context.Context, tenant string) (map[string]int64, error) {
	out := map[string]int64{}
	stmt := spanner.Statement{
		SQL:    `SELECT metric, value FROM counters WHERE tenant = @tenant`,
		Params: map[string]any{"tenant": tenant},
	}
	iter := r.client.Single().Query(ctx, stmt)
	defer iter.Stop()
	err := iter.Do(func(row *spanner.Row) error {
		var metric string
		var value int64
		if err := row.Columns(&metric, &value); err != nil {
			return err
		}
		out[metric] = value
		return nil
	})
	return out, err
}
```

When the exit plan says "Spanner migration is ~3 engineer-weeks," *this is why*. The migration is: write a `CockroachRepository` that implements the same two-method interface using `pgx`, change `NewSpannerRepository(client)` to `NewCockroachRepository(pool)` in `main()`, and re-validate the transactions under contention. Note that the SQL itself does *not* port unedited — Spanner's GoogleSQL upsert is `INSERT OR UPDATE` and cannot reference the prior value, whereas CockroachDB speaks Postgres wire and gives you the cleaner `INSERT ... ON CONFLICT (tenant, metric) DO UPDATE SET value = counters.value + @delta`, collapsing the read-then-write into one statement. That divergence is precisely the kind of proprietary-dialect cost the exit plan is measuring — but because it is sealed inside one file, it stays a three-engineer-week line item instead of a rewrite. The handlers, the gRPC layer, the OpenTelemetry spans, the tests against the interface — none of it changes. Contrast the *other* world, where someone inlined `r.client.ReadWriteTransaction(...)` directly into forty handler methods: now the migration touches forty files and the estimate is forty times worse. The interface is a one-hour decision in week eleven that saves three months in a hypothetical migration. That is the entire argument for clean seams, and the exit plan is where it gets measured.

You make the identical argument for the analytics path: your services never run BigQuery SQL inline; they call a `QueryService` interface whose BigQuery implementation is the only thing that imports the BigQuery client. Swapping to a Trino implementation is then a contained change. The pattern is the same everywhere: **the proprietary dependency is allowed exactly one file.**

## 2.7b — The Spanner question, in detail: do you actually need external consistency?

The single hardest line in the exit plan is the Spanner row, because the honest answer requires you to understand a distinction most engineers blur: the difference between **serializability** and **external consistency**. Getting this right is what separates an exit plan that a database-literate reviewer respects from one they pick apart.

- **Serializability** means the result of a set of transactions is equivalent to *some* serial order of those transactions. CockroachDB and YugabyteDB give you this (CockroachDB's default is `SERIALIZABLE`). It is a strong guarantee — stronger than the `READ COMMITTED` default most Postgres deployments run.
- **External consistency** (Spanner's guarantee, via TrueTime) means the serial order respects *real wall-clock time*: if transaction T1 commits before T2 starts, every observer sees T1 before T2, across regions, with bounded clock uncertainty. This is strictly stronger than serializability.

The exit-plan question is therefore not "can CockroachDB replace Spanner" — it can, at the SQL and serializability level — but "**does this workload actually rely on external consistency, or just serializability?**" For the capstone's current-state counters, the honest answer is almost certainly *just serializability*: you need each tenant's counter updates to apply in a consistent order and reads to see committed writes, but you do not need a global wall-clock ordering of events across regions. That means the exit to CockroachDB loses a guarantee you were not using, which makes the migration *easier* to justify, not harder.

State exactly this in the plan: "We use Spanner for strong, scalable, regionally-survivable transactions. We do **not** rely on external consistency for correctness — serializability suffices for our counter semantics. A migration to CockroachDB would preserve the guarantee we actually depend on. We chose Spanner over self-hosting CockroachDB because of operational burden, not because of the consistency model." A reviewer who reads that knows you understand your own data model better than the marketing page does — and that is the comprehension the exit plan is supposed to prove.

The corollary: if you *had* designed something that genuinely needed external consistency — say a global ledger where the real-time ordering of cross-region transactions is legally meaningful — then Spanner would be a true red dependency with no clean exit, and the right move is to say *that*, loudly, because it is the rare case where the lock-in is the entire point of the design.

## 2.7c — A worked exit-plan exchange

Here is how the exit conversation sounds in the review, reconstructed and edited.

> **R:** If Google tripled the price of Spanner tomorrow, what do you do?
>
> **Candidate:** Short term, nothing — at our scale Spanner is \$260 a month, so a 3x is \$780, annoying but not fatal, and the exit costs more than the increase for years. Medium term, it goes on the list to migrate to CockroachDB, which is about three engineer-weeks: the gRPC service's data layer moves from the Spanner client to a pgwire client, the DDL ports with edits, and I re-validate the transactions under contention. We don't rely on external consistency, only serializability, so CockroachDB preserves the guarantee we actually use.
>
> **R:** Three weeks sounds optimistic for a database migration.
>
> **Candidate:** Three weeks for *functional parity in staging*, not for the zero-downtime production cutover — that's the extra integration-and-cutover line in my estimate, another piece of the two-and-a-half weeks I budgeted for cutover across the whole system. And it's three weeks because the application code barely moves: the business logic isn't coupled to Spanner, it's behind a repository interface. If I'd hard-coded Spanner mutations into the service handlers it'd be three *months*. That isolation was deliberate.
>
> **R:** What's the thing you can't get back if you leave?
>
> **Candidate:** The operational invisibility. Google runs Spanner's Paxos groups, its split rebalancing, its backups, its upgrades, and I never think about any of it. The day I'm on CockroachDB I own a distributed database, which is conservatively half an SRE's time forever. That operational cost doesn't show up on the cloud bill, and it's the real reason staying is cheaper at our scale. The exit plan exists so I know the number, not because I plan to use it.

That answer wins because it separates the three time horizons (do nothing / migrate later / the threshold), prices both the migration *and* the hidden operational cost, and credits the architectural decision (the repository interface) that keeps the number small. It is the exit plan made conversational.

## 2.8 — The lock-in conversation you'll have for the rest of your career

Step back from the capstone. The skill you just built — pricing lock-in honestly, on a spectrum, with engineer-weeks — is one of the highest-value things a staff engineer does, and almost nobody does it well. The two failure modes are everywhere:

- **The zealot who refuses all managed services** "to avoid lock-in," and burns a platform team's entire year operating Kafka and Postgres clusters to save a cloud bill smaller than two of their salaries. They confused "no lock-in" with "good engineering." Lock-in is a cost like any other; you pay it when the thing you are locked into is worth more than the exit cost.
- **The maximalist who hard-codes proprietary services into the application layer** "because it's easier," and discovers three years later that the exit plan is a full rewrite. They never drew the portability spectrum and never noticed the lock-in leaking out of the infrastructure layer into the business logic.

The right posture is the one this course has modeled for fifteen weeks: **use the managed service where it is genuinely best, name the open alternative every time, keep the proprietary dependency isolated behind your own interface, and know the exit number.** Spanner is worth depending on *if* you need what it gives you. BigQuery is worth depending on *because* its serverless economics are hard to reproduce and you isolated it behind a query layer. Pub/Sub is worth depending on *because* operating Kafka is a tax you do not need to pay at this scale. You can say all of that with numbers now. That is what it means to defend an architecture.

## 2.9 — Data gravity and egress: the cost the naive plan forgets

There is one line item that junior exit plans omit entirely and that a sharp reviewer will ask about immediately: **the cost of physically moving the data out.** Compute is cattle — you spin up the replacement and shift traffic. Data is not. If you have terabytes in BigQuery and Spanner, leaving GCP means *egressing* that data across the internet to the new home, and cloud providers charge for egress precisely because it is the friction that keeps you in. This is "data gravity": the larger your data, the more it costs to move, and the more it anchors you.

For the capstone at its current scale the egress cost is trivial — you might have gigabytes, not terabytes, and the one-time egress is a few dollars. But the exit plan must *state* this explicitly, because the reviewer's real question is "does this scale?" The honest answer:

- **At the capstone's scale (GB):** egress is negligible, a one-time cost in the low tens of dollars. Not a factor.
- **At production scale (TB–PB):** egress becomes a real, sometimes dominant, one-time migration cost. GCP charges per-GB for internet egress (the exact rate is tiered; see the pricing calculator in `resources.md`). A petabyte of egress is a meaningful five-figure bill, plus the *time* to transfer it — at which point you are looking at a Transfer Appliance (physical disk shipment) rather than a wire transfer, which adds weeks.
- **The hidden gravity:** even after the bulk transfer, you have a *cutover window* where writes are happening to both systems, and reconciling that without data loss is its own engineering effort — the "integration, testing, cutover" line in the §2.5 estimate exists largely to cover this.

The strategic implication for the exit plan's conclusion: **data gravity grows over time, so the exit cost is lowest now and only ever increases.** That is a genuine argument *for* keeping the exit plan current and *for* not letting any single proprietary store become the only copy of irreplaceable data. The capstone mitigates this by design — BigQuery is the analytical store, not the only copy, because events also flow durably through Pub/Sub and the raw landing path. Naming that ("our data of record is replayable from the event stream, so a migration rebuilds the analytical store rather than egressing it") is a sophisticated point that turns the data-gravity question from a weakness into evidence that you designed for it.

## 2.9b — Keeping the exit plan honest: tie it to the dependency list in code

An exit plan written once and never updated rots within a quarter, because the system changes and new proprietary dependencies sneak in. The discipline that keeps it honest is to make the dependency inventory a thing you can *regenerate from the system* rather than maintain by hand. You will not build a perfect tool for this, but a cheap one catches the worst drift: a script that walks your Terraform and flags every `google_*` resource type, so a reviewer can diff the declared inventory against what the code actually uses.

A starter, in Python, that you run in CI and that fails the build if a new GCP service appears that is not in the documented inventory:

```python
#!/usr/bin/env python3
"""Flag GCP service dependencies in Terraform that are missing from EXIT-PLAN.md."""
import pathlib
import re
import sys

# Map terraform resource prefixes to the inventory rows in EXIT-PLAN.md.
KNOWN = {
    "google_compute_": "Edge / LB",
    "google_cloud_run": "Ingest",
    "google_pubsub_": "Stream",
    "google_dataflow_": "Process",
    "google_bigquery_": "Analytics",
    "google_spanner_": "Serve (state)",
    "google_vertex_ai_": "Serve (model)",
    "google_redis_": "Cache",
    "google_secret_manager_": "Security",
    "google_kms_": "Security",
}


def declared_services(tf_dir: pathlib.Path) -> set[str]:
    """Return the set of inventory categories the Terraform actually uses."""
    found: set[str] = set()
    pattern = re.compile(r'resource\s+"(google_[a-z0-9_]+?)_')
    for tf in tf_dir.rglob("*.tf"):
        text = tf.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            resource = match.group(1) + "_"
            for prefix, category in KNOWN.items():
                if resource.startswith(prefix):
                    found.add(category)
                    break
            else:
                # An unknown google_* resource: a new dependency to document.
                found.add(f"UNDOCUMENTED:{resource}")
    return found


def main() -> int:
    tf_dir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "terraform")
    exit_plan = pathlib.Path("EXIT-PLAN.md")
    if not exit_plan.exists():
        print("EXIT-PLAN.md not found; the exit plan is a required artifact.")
        return 1
    plan_text = exit_plan.read_text(encoding="utf-8")
    used = declared_services(tf_dir)
    missing = [s for s in used
               if s.startswith("UNDOCUMENTED:") or s not in plan_text]
    if missing:
        print("Exit plan is stale - these dependencies are not documented:")
        for s in sorted(missing):
            print(f"  - {s}")
        return 1
    print(f"Exit plan covers all {len(used)} GCP service categories in Terraform.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

This is not the point of the exit plan, but it embodies the point: the inventory is the part that drifts, and a thirty-line check that fails CI when an undocumented `google_*` resource appears is enough to keep the most important page honest. When a teammate adds, say, a Cloud Tasks queue and the build goes red until they add a row to the inventory, the exit plan stays current for free. A reviewer who learns you *enforce* the inventory in CI knows the document is real and not a one-time artifact written for a meeting and forgotten. That enforcement is the difference between an exit plan that ages into fiction and one a CTO can actually rely on at renewal time.

## 2.10 — Putting the exit plan in front of leadership

Finally, a note on audience, because the exit plan has two readers and they want different things. The *engineer* reviewer wants the per-component breakdown, the portability tiers, and the isolation pattern — the technical substance. The *leadership* reader (a CTO, a VP, a board member) wants exactly three sentences: how long, how much, and what we lose. Your two-page document must serve both, which is why the structure front-loads the inventory and effort tables (skimmable by leadership) and pushes the detailed reasoning into the prose (read by engineers).

The sentence that lands with leadership is the scale-aware conclusion: "Moving this workload off GCP is roughly 17 engineer-weeks and would add 1–2 SREs of permanent operational cost; at our current spend that is not worth it, and it becomes worth revisiting around \$N/month or if we grow a platform team for other reasons. We keep this document current as a negotiating lever and a risk hedge." That sentence demonstrates that you understand lock-in as a managed cost rather than a moral failing — which is the entire posture this course has tried to teach. An engineer who can write that sentence, and back every number in it, is an engineer a company trusts with platform decisions. That is the outcome of C18.

## Summary

The exit plan exists for negotiating leverage, risk management, and — most importantly for you this week — as a comprehension test you administer to yourself. Lock-in is a spectrum (green/yellow/orange/red), and good architecture keeps the red-tier dependencies few, isolated, and justified. The capstone has exactly one true red dependency (Spanner's external consistency) and one near-red (BigQuery's serverless economics); everything else is green or yellow *because you built on Kubernetes, containers, Apache Beam, and OpenTelemetry*. The total exit cost is ~17 engineer-weeks, concentrated in Pub/Sub, BigQuery, and Spanner, with the application code moving nearly unchanged. The honest steady-state conclusion is that leaving is not worth it at the capstone's scale — the managed services cost less than the salaries to operate their replacements — and saying *exactly that*, with the threshold at which it changes, is what reads as senior. Write the two pages. Defend every cell.
