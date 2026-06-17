#!/usr/bin/env python3
"""Exercise 3 - The database decision, as a scoring engine.

Goal: Implement the seven-axis decision rubric from Lecture 1 as runnable Python,
      score three concrete workloads, and emit a written justification for each.
      No cloud resources. Runs and tests locally. FREE.

      The point is not to build a perfect oracle; it is to make the decision
      EXPLICIT. A rubric that is written down can be argued with in a review; a
      gut call cannot. By the end you can defend a database choice with a number
      and a one-sentence justification naming the deciding axis and the runner-up.

Estimated time: 45 minutes.

HOW TO RUN
        python exercise-03-database-decision.py

HOW TO TEST (optional - add your own asserts or run with pytest)
        pytest exercise-03-database-decision.py

ACCEPTANCE CRITERIA
  [ ] decide(workload) returns a Decision with a winner, a runner-up, and a
      one-sentence justification naming the DECIDING axis.
  [ ] The three sample workloads each resolve to a defensible choice:
        - The SaaS CRM  -> Cloud SQL (cheap, single-region, full Postgres).
        - The growing analytics-adjacent app -> AlloyDB (read pools + columnar).
        - The global ledger -> Spanner (multi-region strong consistency).
  [ ] No workload that lacks BOTH horizontal-write-scale AND multi-region-strong
      needs Spanner. (The "Spanner is a capability purchase" rule from Lecture 1.)
  [ ] python exercise-03-database-decision.py prints three justifications.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple


class Database(str, Enum):
    CLOUD_SQL = "Cloud SQL"
    ALLOYDB = "AlloyDB"
    SPANNER = "Spanner"
    BIGQUERY = "BigQuery"  # the analytical escape hatch; not a transactional DB


@dataclass(frozen=True)
class Workload:
    """A workload described on the axes that actually drive the decision."""
    name: str
    # Consistency: does it need strong reads with NO staleness window, across regions?
    needs_multiregion_strong: bool
    # Write scale: sustained writes beyond one big machine (tens of thousands/sec)?
    needs_horizontal_write_scale: bool
    # Read scale: many low-lag read replicas needed?
    needs_low_lag_read_scale: bool
    # Does it run heavy analytical queries against the transactional data?
    has_analytical_queries: bool
    # Is the query surface primarily analytical (scans/aggregations), not transactional?
    is_primarily_analytical: bool
    # Does it need rich Postgres SQL + extensions?
    needs_full_postgres: bool
    # Region footprint: must be authoritative in more than one region?
    is_multi_region: bool
    # Monthly dollar budget for the database (USD).
    monthly_budget_usd: int
    # Does the team already run a database-SRE function (affects self-host viability)?
    has_db_sre_function: bool = False


@dataclass
class Decision:
    workload: str
    winner: Database
    runner_up: Database
    deciding_axis: str
    justification: str
    scores: Dict[Database, int] = field(default_factory=dict)


# Rough monthly floor cost (USD) for the smallest production-shaped config of each.
# These are order-of-magnitude figures for the rubric, not a billing quote.
APPROX_FLOOR_COST: Dict[Database, int] = {
    Database.CLOUD_SQL: 120,   # db-custom-2-7680 regional HA
    Database.ALLOYDB: 320,     # primary + a 2-node read pool
    Database.SPANNER: 650,     # 100 PU is cheaper, but a *production* footprint is ~1 node
}


def decide(w: Workload) -> Decision:
    """Apply the seven-axis rubric. Highest-weighted UNMET need drives the answer."""

    # Rule 0: a primarily-analytical workload is not a transactional-DB question at all.
    if w.is_primarily_analytical:
        return Decision(
            workload=w.name,
            winner=Database.BIGQUERY,
            runner_up=Database.ALLOYDB,
            deciding_axis="query surface (analytical)",
            justification=(
                f"BigQuery, because {w.name} is primarily analytical (scans and "
                "aggregations), and no transactional database in this rubric is the "
                "right tool for that; runner-up AlloyDB, whose columnar engine could "
                "serve light analytics inline but would lose on cost and scan performance "
                "for a workload this scan-heavy."
            ),
        )

    # Rule 1: Spanner is a CAPABILITY purchase. You need it iff at least one of
    # {horizontal write scale, multi-region strong consistency} holds.
    needs_spanner_capability = (
        w.needs_horizontal_write_scale or w.needs_multiregion_strong
    )

    if needs_spanner_capability:
        # Even so, confirm the budget can carry it; if not, the decision is "negotiate
        # the requirement or the budget" - we flag it rather than silently downgrade.
        deciding = (
            "multi-region strong consistency"
            if w.needs_multiregion_strong
            else "horizontal write scale"
        )
        runner_up = Database.ALLOYDB
        budget_note = ""
        if w.monthly_budget_usd < APPROX_FLOOR_COST[Database.SPANNER]:
            budget_note = (
                f" NOTE: the stated budget (${w.monthly_budget_usd}/mo) is below the "
                f"~${APPROX_FLOOR_COST[Database.SPANNER]}/mo production Spanner floor - "
                "the requirement and the budget are in conflict and one must move."
            )
        return Decision(
            workload=w.name,
            winner=Database.SPANNER,
            runner_up=runner_up,
            deciding_axis=deciding,
            justification=(
                f"Spanner, because {w.name} needs {deciding}, which neither single-writer "
                f"Cloud SQL nor AlloyDB can provide; runner-up AlloyDB, rejected because it "
                f"is single-writer and single-region and so cannot meet the {deciding} "
                f"requirement.{budget_note}"
            ),
        )

    # Rule 2: no Spanner capability needed. Choose between AlloyDB and Cloud SQL.
    # AlloyDB wins when low-lag read scale or analytical queries are present AND the
    # budget can carry it; otherwise Cloud SQL is the cheapest correct answer.
    wants_alloydb = w.needs_low_lag_read_scale or w.has_analytical_queries
    can_afford_alloydb = w.monthly_budget_usd >= APPROX_FLOOR_COST[Database.ALLOYDB]

    if wants_alloydb and can_afford_alloydb:
        deciding = (
            "low-lag read scaling"
            if w.needs_low_lag_read_scale
            else "inline analytical queries"
        )
        return Decision(
            workload=w.name,
            winner=Database.ALLOYDB,
            runner_up=Database.CLOUD_SQL,
            deciding_axis=deciding,
            justification=(
                f"AlloyDB, because {w.name} needs {deciding} but stays single-region and "
                f"single-writer; runner-up Cloud SQL, rejected because read-replica lag "
                f"(async) and the lack of a columnar engine would hurt the "
                f"{'read-your-writes path' if w.needs_low_lag_read_scale else 'analytical queries'}."
            ),
        )

    # Rule 3: the default and most common answer - Cloud SQL.
    runner_up = Database.ALLOYDB if wants_alloydb else Database.ALLOYDB
    deciding = "cost (cheapest correct answer)"
    extra = ""
    if wants_alloydb and not can_afford_alloydb:
        deciding = "budget (AlloyDB would help but exceeds the budget)"
        extra = (
            f" The workload would benefit from AlloyDB but the ${w.monthly_budget_usd}/mo "
            f"budget is below AlloyDB's ~${APPROX_FLOOR_COST[Database.ALLOYDB]}/mo floor."
        )
    return Decision(
        workload=w.name,
        winner=Database.CLOUD_SQL,
        runner_up=runner_up,
        deciding_axis=deciding,
        justification=(
            f"Cloud SQL, because {w.name} needs full Postgres, is single-region and "
            f"single-writer, and has no requirement that justifies a step up; runner-up "
            f"AlloyDB, held in reserve for when read load or analytics grow.{extra}"
        ),
    )


# --------------------------------------------------------------------------- #
# Three concrete workloads to score.
# --------------------------------------------------------------------------- #
WORKLOADS: List[Workload] = [
    Workload(
        name="SaaS CRM (B2B, single-region, 2k tenants)",
        needs_multiregion_strong=False,
        needs_horizontal_write_scale=False,
        needs_low_lag_read_scale=False,
        has_analytical_queries=False,
        is_primarily_analytical=False,
        needs_full_postgres=True,
        is_multi_region=False,
        monthly_budget_usd=200,
    ),
    Workload(
        name="Growing marketplace app (read-heavy, dashboards, single-region)",
        needs_multiregion_strong=False,
        needs_horizontal_write_scale=False,
        needs_low_lag_read_scale=True,
        has_analytical_queries=True,
        is_primarily_analytical=False,
        needs_full_postgres=True,
        is_multi_region=False,
        monthly_budget_usd=500,
    ),
    Workload(
        name="Global payments ledger (US + EU authoritative, cannot oversell)",
        needs_multiregion_strong=True,
        needs_horizontal_write_scale=False,
        needs_low_lag_read_scale=True,
        has_analytical_queries=False,
        is_primarily_analytical=False,
        needs_full_postgres=False,
        is_multi_region=True,
        monthly_budget_usd=3000,
    ),
]


def print_decision(d: Decision) -> None:
    print("=" * 78)
    print(f"Workload : {d.workload}")
    print(f"Winner   : {d.winner.value}")
    print(f"Runner-up: {d.runner_up.value}")
    print(f"Deciding : {d.deciding_axis}")
    print("Justification:")
    print(f"  {d.justification}")
    print()


def main() -> None:
    for w in WORKLOADS:
        print_decision(decide(w))


# --------------------------------------------------------------------------- #
# Tests. Run with `pytest exercise-03-database-decision.py`.
# These encode the acceptance criteria as executable assertions.
# --------------------------------------------------------------------------- #
def test_crm_picks_cloud_sql() -> None:
    d = decide(WORKLOADS[0])
    assert d.winner == Database.CLOUD_SQL


def test_marketplace_picks_alloydb() -> None:
    d = decide(WORKLOADS[1])
    assert d.winner == Database.ALLOYDB


def test_ledger_picks_spanner() -> None:
    d = decide(WORKLOADS[2])
    assert d.winner == Database.SPANNER
    assert "multi-region strong consistency" in d.deciding_axis


def test_spanner_is_a_capability_purchase() -> None:
    """No workload lacking BOTH horizontal-write-scale AND multi-region-strong
    should ever resolve to Spanner."""
    for w in WORKLOADS:
        if not (w.needs_horizontal_write_scale or w.needs_multiregion_strong):
            assert decide(w).winner != Database.SPANNER


def test_analytical_workload_routes_to_bigquery() -> None:
    analytical = Workload(
        name="Ad-hoc analytics on event data",
        needs_multiregion_strong=False,
        needs_horizontal_write_scale=False,
        needs_low_lag_read_scale=False,
        has_analytical_queries=True,
        is_primarily_analytical=True,
        needs_full_postgres=False,
        is_multi_region=False,
        monthly_budget_usd=400,
    )
    assert decide(analytical).winner == Database.BIGQUERY


def test_requirement_budget_conflict_is_flagged() -> None:
    """A multi-region-strong requirement under a sub-Spanner budget must be flagged,
    not silently downgraded."""
    underfunded = Workload(
        name="Underfunded global ledger",
        needs_multiregion_strong=True,
        needs_horizontal_write_scale=False,
        needs_low_lag_read_scale=False,
        has_analytical_queries=False,
        is_primarily_analytical=False,
        needs_full_postgres=False,
        is_multi_region=True,
        monthly_budget_usd=100,
    )
    d = decide(underfunded)
    assert d.winner == Database.SPANNER
    assert "conflict" in d.justification


if __name__ == "__main__":
    main()
