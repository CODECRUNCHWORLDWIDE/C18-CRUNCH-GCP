#!/usr/bin/env python3
"""
Exercise 3 - PCA / Cloud DevOps Engineer practice exam + >=70% readiness gate.

A self-contained practice exam scorer. The question bank below is original, modeled
on the *style* of the Google Professional Cloud Architect and Professional Cloud DevOps
Engineer blueprints (it is NOT a copy of any official exam). Each question is tagged
with the blueprint domain it exercises, so the scorer can tell you not just whether you
passed the >=70% gate but WHICH domains are weak so you know where to study before you
sit the real test.

USAGE
  python3 exercise-03-pca-readiness-gate.py            # interactive, all questions
  python3 exercise-03-pca-readiness-gate.py --domain reliability   # one domain only
  python3 exercise-03-pca-readiness-gate.py --review   # print answers+rationale, no quiz
  python3 exercise-03-pca-readiness-gate.py --self-test # verify the bank is consistent

GATE
  Prints "READINESS GATE: PASS" iff score >= 70%. Otherwise PARTIAL/FAIL with a
  per-domain breakdown and a study plan pointing at your two weakest domains.

No GCP access or network required. Pure standard library.
"""

from __future__ import annotations

import argparse
import dataclasses
import random
import sys
import textwrap

PASS_THRESHOLD = 0.70


@dataclasses.dataclass(frozen=True)
class Question:
    domain: str
    prompt: str
    options: tuple[str, ...]  # A, B, C, D
    answer: int               # 0-based index of the correct option
    rationale: str


# --------------------------------------------------------------------------- #
# Question bank. Domains mirror the PCA + Cloud DevOps blueprints.
# --------------------------------------------------------------------------- #
BANK: list[Question] = [
    Question(
        domain="reliability",
        prompt=(
            "A global external Application Load Balancer fronts ingest in two regions. "
            "You want automatic failover to the standby region when the primary backend "
            "is unhealthy, with no DNS TTL delay. What provides this?"
        ),
        options=(
            "A Cloud DNS geolocation routing policy with a 5s TTL.",
            "The LB's backend-service health checks plus multiple backends; the LB "
            "routes to a healthy backend within a health-check interval, no DNS change needed.",
            "A second LB in the standby region and a manual DNS cutover runbook.",
            "Pub/Sub message replay from the standby region.",
        ),
        answer=1,
        rationale=(
            "A global LB already load-balances across regional backends; if the primary "
            "backend fails its health check the LB serves from the healthy backend within "
            "a health-check interval. DNS-based failover (A/C) adds TTL latency and is the "
            "fallback when you must fail over across separate LBs."
        ),
    ),
    Question(
        domain="reliability",
        prompt=(
            "Your SLO is 99.9% availability (43.2 min/month error budget). You want to be "
            "paged only when the budget is burning fast enough to exhaust in hours, not on "
            "every blip. Which alerting approach fits?"
        ),
        options=(
            "A single threshold alert: page when error rate > 0.1% for 1 minute.",
            "A multi-window, multi-burn-rate alert: a fast-burn condition (e.g. 14.4x over "
            "1h) pages, a slow-burn condition (e.g. 6x over 6h) files a ticket.",
            "Alert on absolute error count > 100 in any 5-minute window.",
            "No alert; review the error budget weekly in a dashboard.",
        ),
        answer=1,
        rationale=(
            "Multi-window multi-burn-rate alerting is the SRE-workbook standard: a high "
            "burn rate over a short window pages (real fast burn), a lower burn over a long "
            "window tickets. A single 1-minute threshold (A) pages on noise."
        ),
    ),
    Question(
        domain="security",
        prompt=(
            "A GitHub Actions workflow must deploy to GCP. You want zero long-lived keys "
            "in the repo. What do you configure?"
        ),
        options=(
            "Store a service-account JSON key as an encrypted GitHub secret.",
            "Workload Identity Federation: a workload identity pool + provider trusting "
            "GitHub's OIDC issuer, with the SA impersonated via short-lived tokens.",
            "A user OAuth token refreshed by a cron job.",
            "Embed the key in a private container image pulled at deploy time.",
        ),
        answer=1,
        rationale=(
            "WIF lets GitHub's OIDC token be exchanged for a short-lived GCP access token; "
            "no key material is ever stored. Storing a JSON key (A) is exactly the anti-"
            "pattern WIF replaces."
        ),
    ),
    Question(
        domain="security",
        prompt=(
            "You wrap a data project in a VPC Service Controls perimeter. A Dataflow job in "
            "a different project must read from a BigQuery dataset inside the perimeter. The "
            "job starts failing with a VPC SC denial. What is the correct fix?"
        ),
        options=(
            "Grant the Dataflow SA roles/owner on the data project.",
            "Disable the perimeter during the job and re-enable it after.",
            "Add an ingress rule to the perimeter allowing the Dataflow SA/identity and the "
            "BigQuery API from the source project.",
            "Move BigQuery out of the perimeter.",
        ),
        answer=2,
        rationale=(
            "VPC SC blocks cross-perimeter access even for authorized IAM principals; the "
            "intended escape hatch is an explicit ingress/egress rule scoped to the identity "
            "and API. Disabling the perimeter (B) or over-granting (A) defeats the control."
        ),
    ),
    Question(
        domain="security",
        prompt=(
            "You require that only container images signed by your Cloud Build pipeline can "
            "run on a GKE cluster. Which feature enforces this at admission time?"
        ),
        options=(
            "Binary Authorization with an attestor whose public key verifies the build's "
            "attestation.",
            "A Cloud Armor WAF rule on the cluster ingress.",
            "An Org Policy constraint on allowed machine types.",
            "A firewall rule blocking egress to Docker Hub.",
        ),
        answer=0,
        rationale=(
            "Binary Authorization gates pod admission on signed attestations. Cloud Armor "
            "(B) protects HTTP traffic, not image provenance."
        ),
    ),
    Question(
        domain="data",
        prompt=(
            "A BigQuery table stores 5 TB of events. Analysts repeatedly query a single "
            "day's data filtered by tenant. Queries scan the whole table and cost too much. "
            "What schema change fixes this most directly?"
        ),
        options=(
            "Partition by event-time (daily) and cluster by tenant.",
            "Create a materialized view of the entire table.",
            "Switch the table to the legacy SQL dialect.",
            "Increase the on-demand query quota.",
        ),
        answer=0,
        rationale=(
            "Time partitioning lets a date filter prune to one partition; clustering by "
            "tenant co-locates tenant rows so the scan reads far fewer blocks. Together they "
            "make the typical query scan <1% of the table."
        ),
    ),
    Question(
        domain="data",
        prompt=(
            "Your streaming Dataflow (Beam) pipeline windows on event time. Some events "
            "arrive 20 minutes late due to mobile retries. With default settings those "
            "events are dropped. What do you configure to include them?"
        ),
        options=(
            "Switch to processing-time windows.",
            "Set allowed lateness on the window and choose a trigger that fires on late "
            "data (e.g. accumulating panes).",
            "Increase the number of Dataflow workers.",
            "Disable the watermark.",
        ),
        answer=1,
        rationale=(
            "Allowed lateness keeps window state open past the watermark so late elements "
            "still land; a late-firing trigger emits the updated result. Processing-time "
            "windows (A) abandon event-time correctness."
        ),
    ),
    Question(
        domain="data",
        prompt=(
            "You need strongly-consistent reads and writes across two regions with "
            "horizontal write scale, and you can pay for it. Which GCP database fits?"
        ),
        options=(
            "Cloud SQL for PostgreSQL with a cross-region read replica.",
            "Firestore in Datastore mode.",
            "Cloud Spanner (multi-region configuration).",
            "Memorystore for Redis with replication.",
        ),
        answer=2,
        rationale=(
            "Spanner multi-region gives external consistency and horizontal write scale. A "
            "Cloud SQL read replica (A) is async and read-only; Memorystore (D) is a cache, "
            "not a system of record."
        ),
    ),
    Question(
        domain="compute",
        prompt=(
            "A stateless HTTP service has spiky traffic and idles to zero overnight. You "
            "want to pay nothing when idle but avoid cold-start latency on the hot path "
            "during the day. What is the right Cloud Run configuration?"
        ),
        options=(
            "min-instances=0 always; accept cold starts.",
            "min-instances=1 (or a small number) during business hours, scaling to 0 "
            "off-hours; tune concurrency so each instance handles many requests.",
            "Deploy on a GKE Standard cluster with one always-on node.",
            "Use Cloud Functions gen1 with a 1-minute timeout.",
        ),
        answer=1,
        rationale=(
            "A small min-instances kills cold start on the hot path while concurrency keeps "
            "instance count low; scaling to 0 off-hours saves money. Pure min-instances=0 "
            "(A) reintroduces cold starts during the day."
        ),
    ),
    Question(
        domain="compute",
        prompt=(
            "You run a regional GKE Standard cluster. You want a node pool that is ~70% "
            "cheaper for fault-tolerant batch work and can be reclaimed by Google. What do "
            "you use, and what must the workload tolerate?"
        ),
        options=(
            "A Spot node pool; workloads must tolerate node preemption (PodDisruptionBudgets "
            "and graceful shutdown).",
            "A sole-tenant node pool; no special tolerance needed.",
            "A GPU node pool; tolerate higher latency.",
            "Autopilot; tolerate nothing, it is fully managed.",
        ),
        answer=0,
        rationale=(
            "Spot VMs are deeply discounted but preemptible; the workload must handle abrupt "
            "node loss. Sole-tenant (B) is the opposite (isolation, premium price)."
        ),
    ),
    Question(
        domain="networking",
        prompt=(
            "A GKE pod must reach BigQuery's API privately, without traversing the public "
            "internet and without a public IP on the node. What enables this?"
        ),
        options=(
            "Cloud NAT for egress to bigquery.googleapis.com.",
            "Private Google Access on the subnet, so *.googleapis.com resolves to private "
            "VIPs reachable without external IPs.",
            "A public load balancer in front of BigQuery.",
            "VPC peering with Google's project.",
        ),
        answer=1,
        rationale=(
            "Private Google Access lets instances without external IPs reach Google APIs "
            "over Google's network. Cloud NAT (A) would route egress to the public internet."
        ),
    ),
    Question(
        domain="networking",
        prompt=(
            "You must block a specific abusive request pattern (a header value matching a "
            "regex) at the edge before it reaches your backend, and rate-limit per source "
            "IP. Which product and language?"
        ),
        options=(
            "iptables rules on each GKE node.",
            "A Cloud Armor security policy with a custom rule written in CEL plus a "
            "rate-based ban rule.",
            "A BigQuery scheduled query.",
            "A Cloud Run ingress setting.",
        ),
        answer=1,
        rationale=(
            "Cloud Armor evaluates CEL expressions and rate-based rules at the edge in front "
            "of the LB backends, exactly the right layer to block patterns and throttle IPs."
        ),
    ),
    Question(
        domain="devops",
        prompt=(
            "A Terraform apply in CI must not race against another apply. Two engineers push "
            "near-simultaneously. What prevents corrupt state?"
        ),
        options=(
            "Run terraform apply with -parallelism=1.",
            "A GCS remote backend, which provides state locking via object generation so "
            "the second apply waits for the lock.",
            "Commit the state file to Git.",
            "Use terraform refresh before apply.",
        ),
        answer=1,
        rationale=(
            "The GCS backend takes a lock so concurrent applies serialize; the second blocks "
            "until the first releases. Committing state to Git (C) is an anti-pattern."
        ),
    ),
    Question(
        domain="devops",
        prompt=(
            "You want to attribute last month's spend to each service in the capstone. What "
            "is the supported, queryable mechanism?"
        ),
        options=(
            "Screenshot the billing console monthly.",
            "Enable billing export to BigQuery and query the export table grouped by "
            "service.description and labels.",
            "Parse the PDF invoice with a regex.",
            "Read the Cloud Monitoring CPU metric and multiply by a guessed rate.",
        ),
        answer=1,
        rationale=(
            "Billing export to BigQuery produces a detailed table you can group by service "
            "and resource labels - the basis of any real FinOps analysis."
        ),
    ),
    Question(
        domain="devops",
        prompt=(
            "Every capstone service emits traces, metrics, and logs. You want vendor-neutral "
            "instrumentation that you could re-point at Grafana if you left GCP. What do you "
            "use in the services?"
        ),
        options=(
            "The Cloud Trace client library directly.",
            "OpenTelemetry SDKs exporting via OTLP, with the Cloud exporter (or collector) "
            "as the configured backend.",
            "print() statements parsed by a log sink.",
            "A proprietary APM agent.",
        ),
        answer=1,
        rationale=(
            "OpenTelemetry is the vendor-neutral standard; only the exporter/endpoint changes "
            "if you switch backends. Using the Cloud Trace library directly (A) couples your "
            "code to GCP."
        ),
    ),
]


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def domains() -> list[str]:
    seen: list[str] = []
    for q in BANK:
        if q.domain not in seen:
            seen.append(q.domain)
    return seen


def self_test() -> int:
    """Validate the bank: every answer index is in range and options have 4 entries."""
    errors = 0
    for i, q in enumerate(BANK):
        if len(q.options) != 4:
            print(f"Q{i}: expected 4 options, got {len(q.options)}")
            errors += 1
        if not 0 <= q.answer < len(q.options):
            print(f"Q{i}: answer index {q.answer} out of range")
            errors += 1
    if errors:
        print(f"SELF-TEST FAILED: {errors} problem(s).")
        return 1
    print(f"SELF-TEST OK: {len(BANK)} questions across {len(domains())} domains.")
    return 0


def ask(question: Question, number: int, total: int) -> bool:
    print(f"\nQ{number}/{total}  [{question.domain}]")
    print(textwrap.fill(question.prompt, width=88))
    letters = "ABCD"
    for idx, opt in enumerate(question.options):
        print(f"  {letters[idx]}) " + textwrap.fill(opt, width=84,
              subsequent_indent="     "))
    while True:
        raw = input("Your answer (A/B/C/D, or 'skip'): ").strip().lower()
        if raw == "skip":
            return False
        if raw in ("a", "b", "c", "d"):
            return letters.index(raw.upper()) == question.answer
        print("  Please enter A, B, C, D, or skip.")


def review() -> None:
    letters = "ABCD"
    for i, q in enumerate(BANK, 1):
        print(f"\nQ{i} [{q.domain}] correct answer: {letters[q.answer]}")
        print(textwrap.fill(q.prompt, width=88))
        print("  -> " + textwrap.fill(q.options[q.answer], width=84,
              subsequent_indent="     "))
        print("  Why: " + textwrap.fill(q.rationale, width=82, subsequent_indent="       "))


def run_quiz(questions: list[Question]) -> None:
    total = len(questions)
    correct = 0
    per_domain: dict[str, list[int]] = {}  # domain -> [correct, asked]
    for n, q in enumerate(questions, 1):
        got = ask(q, n, total)
        per_domain.setdefault(q.domain, [0, 0])
        per_domain[q.domain][1] += 1
        if got:
            correct += 1
            per_domain[q.domain][0] += 1

    score = correct / total if total else 0.0
    print("\n" + "=" * 60)
    print(f"SCORE: {correct}/{total} = {score:.0%}")
    print("=" * 60)
    print("\nPer-domain breakdown:")
    weak: list[tuple[str, float]] = []
    for dom, (c, a) in sorted(per_domain.items()):
        pct = c / a if a else 0.0
        bar = "#" * int(pct * 20)
        print(f"  {dom:<12} {c}/{a:<3} {pct:>4.0%} |{bar:<20}|")
        weak.append((dom, pct))

    if score >= PASS_THRESHOLD:
        print(f"\nREADINESS GATE: PASS  ({score:.0%} >= {PASS_THRESHOLD:.0%})")
    elif score >= 0.5:
        print(f"\nREADINESS GATE: PARTIAL  ({score:.0%} < {PASS_THRESHOLD:.0%})")
    else:
        print(f"\nREADINESS GATE: FAIL  ({score:.0%} < {PASS_THRESHOLD:.0%})")

    weak.sort(key=lambda x: x[1])
    if weak and weak[0][1] < 1.0:
        print("\nStudy plan - your two weakest domains:")
        for dom, pct in weak[:2]:
            print(f"  - {dom} ({pct:.0%}): review the C18 week(s) and the blueprint "
                  f"section for {dom}; redo --domain {dom} until 100%.")
    print("\nRun with --review to see every answer and rationale.")


def main() -> None:
    parser = argparse.ArgumentParser(description="PCA / Cloud DevOps readiness gate.")
    parser.add_argument("--domain", help="quiz only this domain "
                        f"({', '.join(domains())})")
    parser.add_argument("--review", action="store_true", help="print answers, no quiz")
    parser.add_argument("--self-test", action="store_true", help="validate the bank")
    parser.add_argument("--shuffle", action="store_true", help="randomize question order")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())
    if args.review:
        review()
        return

    questions = list(BANK)
    if args.domain:
        questions = [q for q in BANK if q.domain == args.domain]
        if not questions:
            sys.exit(f"No questions for domain '{args.domain}'. "
                     f"Choose from: {', '.join(domains())}")
    if args.shuffle:
        random.shuffle(questions)

    print("PCA / Cloud DevOps practice exam. Answer honestly, notes closed.")
    print(f"{len(questions)} questions. Gate: >= {PASS_THRESHOLD:.0%}.")
    try:
        run_quiz(questions)
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
