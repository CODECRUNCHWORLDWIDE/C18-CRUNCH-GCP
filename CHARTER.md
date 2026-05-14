# C18 · Crunch GCP — Charter

This document explains *why* C18 is shaped the way it is: why GCP at all, why 15 weeks, why IAM and networking come before compute, why open-source-first, and how C18 relates to its sibling and sequel tracks. The syllabus is the *what*; the charter is the *why*. Read it before you teach this track and before you fork it.

---

## Why GCP as a discipline

There are three major hyperscalers. We do not teach GCP because it is "easy" — it isn't — and we do not teach it because it is "best" — that depends on the workload. We teach GCP because it is **distinctive**, and the distinctive parts are useful even to engineers who will go on to run workloads on AWS, Azure, or their own metal.

The four genuinely distinctive primitives:

1. **BigQuery.** A serverless analytical warehouse with a separation-of-compute-and-storage model that predates and outperforms most open-source equivalents at the petabyte scale. Trino + Iceberg + Parquet on S3 is the open-source path and we teach it as the reference, but BigQuery's slot model and INFORMATION_SCHEMA are unique enough to merit study on their own.
2. **Spanner.** Globally consistent, horizontally scalable, externally consistent, with TrueTime. CockroachDB and YugabyteDB are the open-source-inspired alternatives, but Spanner is the lineage. Understanding Spanner is understanding what TrueTime made possible.
3. **Pub/Sub.** A managed global event bus with exactly-once delivery semantics, ordering keys, and zero capacity planning. Kafka and NATS are the open-source alternatives we teach as the reference, but Pub/Sub's operational simplicity changes what kinds of architectures are practical for a four-person team.
4. **Anthos / GKE.** Google created Kubernetes. GKE is not "managed Kubernetes" in the EKS sense; it is the reference implementation. Autopilot is the most opinionated managed-Kubernetes offering on the market, and learning where its opinions match production reality (and where they don't) is the fastest way to internalize what Kubernetes actually requires.

Beyond the four, GCP has Vertex AI's Model Garden (open-weights serving without the operational pain), Cloud Run (the cleanest serverless-container product), and an IAM model that is — for all its flaws — more tractable than AWS's. These are the reasons C18 exists.

The course is *not* a defense of Google. We teach the lock-in surface honestly and require an exit plan in the capstone. But ignoring GCP because of its smaller market share is engineering malpractice: every distinctive primitive listed above is a tool you might want to reach for, and a tool you must understand before you can credibly choose against it.

---

## Why 15 weeks intensive, not 24

GCP is a smaller surface than AWS. AWS has 200+ named services; GCP has ~120, with significant overlap and clearer grouping. C19 (Crunch AWS) is also 15 weeks but covers ~30% more service surface because AWS has more "primitive" products that don't exist in GCP (think of how many AWS services overlap with what Cloud Run alone covers).

The right unit of work for C18 is not "every GCP service" but "every GCP primitive that a production engineer can't avoid." That list fits comfortably in 15 weeks at 36 hours per week:

- Phase 1 (4 weeks): the substrate — projects, IAM, networking, Terraform.
- Phase 2 (4 weeks): compute and traffic.
- Phase 3 (4 weeks): data and AI.
- Phase 4 (3 weeks): production, security, FinOps, capstone.

A 24-week version would dilute the intensity. A 12-week version would skip Vertex AI or the on-call drill. 15 is the right number; we kept it.

The 36 hr/week cadence is identical to the rest of Crunch Labs. We do not negotiate it. Engineers who attempt the track at 15 hr/week routinely report taking 22 weeks; that's fine, but the rhythm of the seven-artifact weekly deliverable does not change.

---

## Topic ordering rationale

The single most important pedagogical decision in C18 is putting IAM and networking *first* — before any compute. This goes against the instinct of every cloud tutorial ever written, which opens with "let's spin up a VM" or "let's deploy a container."

The rationale: in real production systems on GCP, the two most common categories of outage are:

1. **IAM-related** — over-privileged service accounts that get compromised; under-privileged service accounts that block a deploy at 3 a.m.; key-file leaks; missing audit logs.
2. **Networking-related** — VPC firewall rules that block a legitimate service; missing Private Google Access; Cloud NAT misconfiguration; routes that should be there and aren't.

Compute and data primitives are where engineers spend their visible work, but IAM and networking are where their incidents come from. A C18 graduate must read IAM bindings and VPC firewall rules with the fluency that a junior engineer reads HTTP status codes. The only way to build that fluency is to spend the first four weeks on it before there's anything interesting to deploy.

Subsequent ordering follows the same principle:

- **Compute before data** — you need somewhere to run the producer of the data.
- **GKE before Cloud Run before Cloud Functions** — most opinionated to least, so each step is an addition, not a contradiction.
- **BigQuery before Spanner** — because BigQuery's cost model is the steeper cliff to fall off, and engineers should learn the cliff before they near it.
- **Vertex AI last in Phase 3** — because the inference path depends on having both the data pipeline (Pub/Sub → BigQuery) and the serving plane (GKE) already operational.
- **Observability before security before FinOps in Phase 4** — because you can't secure or cost-optimize what you can't measure.

---

## Open-source-first stance

This is non-negotiable in Crunch Labs and stated again here for C18 specifically.

We teach Kubernetes first; we then teach what GKE adds. Workload Identity, Autopilot, GKE-specific autoscaling profiles — these are the *additions* to a foundation the student already owns. If GKE were to disappear tomorrow, a C18 graduate could run the same workload on EKS, AKS, or self-hosted k0s.

We teach OpenTelemetry first; we then teach the GCP-specific exporters and the Cloud Trace / Cloud Logging / Cloud Monitoring consumers. The instrumentation in the candidate's code is vendor-neutral; only the exporter is GCP-specific. If the company moves to Datadog or Grafana Cloud tomorrow, the swap is one Helm value, not a rewrite.

We teach Terraform first; we use Config Connector and the Cloud Foundation Toolkit where they are clearly better than raw HCL for a given problem, but the candidate's mental model is portable to AWS and Azure.

We teach Apache Beam first; we run it on Dataflow because Dataflow is the cleanest managed runner, but a C18 graduate can run the same pipeline on Flink or Spark.

We teach BigQuery as a distinctive product *and* benchmark it against Trino + Iceberg every time. Students must know the open-source equivalent's performance characteristics by Week 10.

We teach Pub/Sub as a distinctive product *and* benchmark it against Kafka, NATS, and Redpanda. Students must defend the choice on operational complexity, not on familiarity.

We teach Vertex AI Endpoints *and* vLLM / TGI on GKE. The capstone's model-serving choice is deliberately a comparison.

This stance has a cost: C18 is harder than the equivalent "GCP only" course. It is also more honest. A graduate of C18 can be hired to run a GCP shop, an AWS shop, or a self-hosted Kubernetes shop with the same confidence. That is the goal.

---

## Relationship to C19 (sibling) and C22 (sequel)

**C19 · Crunch AWS** is the sibling track. C18 and C19 are intentionally parallel in shape:

- Both 15 weeks, both 36 hr/week.
- Both open with 4 weeks on substrate (IAM, networking, IaC).
- Both close with a multi-region capstone and an on-call drill.
- A graduate of C18 can complete C19 in ~10 weeks rather than 15; we will eventually publish an "accelerated bridge" version for that audience.

C18 and C19 are *not* substitutes for each other in a CV. The intent is that a senior cloud engineer takes one as their primary cloud and the other as a literacy course later.

**C22 · Crunch Mesh** is the natural sequel. C22 takes the GKE-based system you built in C18 and scales it into a real service mesh: gRPC, Kafka, Istio, multi-tenant routing, chaos engineering at the mesh layer. C18's capstone is deliberately mesh-ready — the GKE cluster, the OpenTelemetry tracing, and the Cloud Armor edge are all reusable as the foundation of a C22 capstone.

The official pathway from the Crunch Labs Charter is:

```
C1 (foundation) → C15 (DevOps) → C18 (GCP) or C19 (AWS) → C22 (Mesh)
```

Lands at: senior cloud platform engineer / staff SRE / principal infrastructure engineer. Roughly 18 months of focused post-C1 work.

---

## The "vendor-aware not vendor-loyal" stance

A C18 graduate must be able to do all of the following without hesitation:

- **Recommend** GCP for a workload where it is the right fit, with a budget and a defensible architecture.
- **Recommend against** GCP for a workload where it is the wrong fit (e.g., a regulated workload with sovereignty constraints GCP cannot meet; a workload whose data gravity is on AWS; a price-sensitive workload that runs cheaper on self-hosted hardware).
- **Migrate** a workload off GCP without rewriting it from scratch — because the open-source path was always the foundation.
- **Read** GCP marketing material with adult skepticism. Service-level marketing exaggerates uptime; pricing pages bury egress; "free tier" rarely covers production. The course teaches the candidate to read past this.
- **Defend** vendor-specific choices honestly. "We use BigQuery because Trino + Iceberg would take six engineer-quarters to set up and we have one engineer" is a legitimate defense. "We use BigQuery because it's the best" is not.

The capstone's required exit plan is the formal mechanism enforcing this stance. If you cannot write a credible exit plan for your workload, you do not understand your workload.

---

## License & signature

This charter is licensed GPL-3.0, like the rest of the academy. Fork it, adapt it for your local cohort, but if you publish a modified version, retain the GPL terms and link back to the source.

Maintained by the Code Crunch Club curriculum council. Per-cohort track owners are named in the cohort's `README.md`. Open issues on the master curriculum repository for cross-track concerns.

*Crunch Labs · C18 Crunch GCP · charter v1.0 · 2026-05-13.*
