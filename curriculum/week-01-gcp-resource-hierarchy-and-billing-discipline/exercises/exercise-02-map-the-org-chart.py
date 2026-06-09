#!/usr/bin/env python3
"""Exercise 2 - Map the org chart to a folder/project tree.

Goal: Practice the single most important Week 1 design skill - turning a real
      org chart into a defensible GCP folder/project hierarchy, where every
      boundary is justified by "who has access" and "what org policy applies"
      rather than by filing convenience.

Estimated time: 45 minutes.

HOW TO USE THIS FILE

  1. You need Python 3.11+. No third-party packages - standard library only.

         python3 exercise-02-map-the-org-chart.py

  2. The SAMPLE_ORG below describes a fictional company, ACME, as an org chart:
     business units, the teams in each, and the environments each team ships to.
     Your job is to fill in the TWO functions marked `# TODO` so that the script
     renders (a) an ASCII folder/project tree and (b) a justification table.

  3. Run it. The output must match the EXPECTED OUTPUT block at the bottom of
     this file. The placement rules are stated in the docstrings; follow them.

  4. Then answer the WRITEUP prompt at the very bottom in a separate
     `writeup.md` - three short paragraphs defending your boundaries.

ACCEPTANCE CRITERIA

  [ ] Both TODOs implemented; `python3 exercise-02-map-the-org-chart.py` runs
      with no exception and prints the tree and the table.
  [ ] Output matches the EXPECTED OUTPUT block (modulo trailing whitespace).
  [ ] You used the "team, then environment" hybrid layout from Lecture 1.
  [ ] `writeup.md` exists and defends three specific boundary choices.

Inline hints are at the bottom of the file. Don't peek until you've tried for
at least 15 minutes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ----------------------------------------------------------------------------
# The sample org chart (the input you are mapping)
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Team:
    name: str
    environments: tuple[str, ...]  # which envs this team ships to


@dataclass(frozen=True)
class BusinessUnit:
    name: str
    teams: tuple[Team, ...]


# ACME ships a payments product and a search product, plus a platform group
# that owns shared infrastructure. Payments is regulated (PCI) so prod is
# locked down hard; search is not. Platform owns the shared VPC and logging.
SAMPLE_ORG: tuple[BusinessUnit, ...] = (
    BusinessUnit(
        name="payments",
        teams=(
            Team("checkout", ("dev", "prod")),
            Team("ledger", ("dev", "prod")),
        ),
    ),
    BusinessUnit(
        name="search",
        teams=(
            Team("indexer", ("dev", "staging", "prod")),
            Team("ranking", ("dev", "prod")),
        ),
    ),
    BusinessUnit(
        name="platform",
        teams=(
            Team("network", ("shared",)),   # the shared VPC host project
            Team("observability", ("shared",)),  # the central logging project
        ),
    ),
)

ORG_DOMAIN = "acme.com"
PROJECT_SUFFIX = "7f3a"  # a stable short suffix to dodge global ID collisions


# ----------------------------------------------------------------------------
# The data structures you build (the output you are producing)
# ----------------------------------------------------------------------------


@dataclass
class Node:
    """One node in the rendered hierarchy: a folder or a project."""

    kind: str  # "folder" or "project"
    name: str
    project_id: str | None = None  # only for projects
    children: list["Node"] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Functions to implement
# ----------------------------------------------------------------------------


def project_id_for(bu: str, team: str, env: str) -> str:
    """Build a globally-unique, convention-following project ID.

    Convention (from Lecture 1): <org>-<bu>-<team>-<env>-<suffix>, lowercased,
    using the bare "acme" org prefix. Example:
        acme-payments-checkout-prod-7f3a

    Project IDs are 6-30 chars, lowercase letters, digits, and hyphens, and
    must start with a letter. The inputs here all satisfy that.
    """
    return f"acme-{bu}-{team}-{env}-{PROJECT_SUFFIX}"


def build_tree(org: tuple[BusinessUnit, ...]) -> Node:
    """Build the folder/project tree using the team-then-environment hybrid.

    Layout (from Lecture 1, section 4):

        organizations/acme.com
        ├── folder: bootstrap            (always present; holds tf-state)
        ├── folder: shared               (platform BU lives here, flat)
        │   ├── project: acme-platform-network-shared-7f3a
        │   └── project: acme-platform-observability-shared-7f3a
        └── folder: workloads
            ├── folder: payments
            │   ├── folder: checkout
            │   │   ├── project: acme-payments-checkout-dev-7f3a
            │   │   └── project: acme-payments-checkout-prod-7f3a
            │   └── folder: ledger
            │       └── ...
            └── folder: search
                └── ...

    Rules:
      - The "platform" business unit maps into the top-level `shared/` folder,
        flat (no per-team subfolder), because its projects are shared
        infrastructure, not per-environment workloads.
      - Every OTHER business unit becomes a folder under `workloads/`, with a
        subfolder per team, and a project per (team, environment).
      - A `bootstrap/` folder is always present (no projects added here in this
        exercise - it just exists, ready for the tf-state project).

    TODO: build and return the root Node for organizations/acme.com.
    """
    raise NotImplementedError


def justification_rows(org: tuple[BusinessUnit, ...]) -> list[tuple[str, str, str]]:
    """Produce (boundary, kind, justification) rows for the table.

    Return one row per top-level folder explaining WHY it exists in terms of
    access + org policy (not filing). Use exactly these four rows, in order:

        ("bootstrap", "folder",
         "Isolates Terraform state + break-glass; tightest access in the org.")
        ("shared",    "folder",
         "Platform-owned shared infra (VPC host, logging); read by all, "
         "written by platform only.")
        ("workloads", "folder",
         "All product workloads; per-BU subfolders carry team ownership, "
         "per-env leaves carry environment policy.")
        ("payments",  "folder",
         "PCI-regulated BU; prod leaf gets strict org policy "
         "(Shielded VM, OS Login) that search does not need.")

    TODO: return the four rows above as a list of 3-tuples.
    """
    raise NotImplementedError


# ----------------------------------------------------------------------------
# Rendering (provided - do not change)
# ----------------------------------------------------------------------------


def render_tree(node: Node, prefix: str = "", is_last: bool = True, is_root: bool = True) -> list[str]:
    """Render a Node tree as ASCII lines."""
    connector = "" if is_root else ("└── " if is_last else "├── ")
    label = (
        f"{node.kind}: {node.name}"
        if node.kind == "folder"
        else f"project: {node.project_id}"
    )
    lines = [f"{prefix}{connector}{label}"]
    if is_root:
        child_prefix = ""
    else:
        child_prefix = prefix + ("    " if is_last else "│   ")
    for i, child in enumerate(node.children):
        last = i == len(node.children) - 1
        lines.extend(render_tree(child, child_prefix, last, is_root=False))
    return lines


def render_table(rows: list[tuple[str, str, str]]) -> list[str]:
    """Render the justification rows as a fixed-width table."""
    header = ("Boundary", "Kind", "Why it exists (access + policy)")
    widths = [12, 7, 70]
    out = []
    out.append(
        f"{header[0]:<{widths[0]}} {header[1]:<{widths[1]}} {header[2]}"
    )
    out.append(f"{'-' * widths[0]} {'-' * widths[1]} {'-' * widths[2]}")
    for boundary, kind, why in rows:
        out.append(f"{boundary:<{widths[0]}} {kind:<{widths[1]}} {why}")
    return out


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------


def main() -> None:
    root = build_tree(SAMPLE_ORG)
    print(f"# Folder/project tree for organizations/{ORG_DOMAIN}\n")
    for line in render_tree(root):
        print(line)

    print("\n# Boundary justification\n")
    for line in render_table(justification_rows(SAMPLE_ORG)):
        print(line)


if __name__ == "__main__":
    main()


# ----------------------------------------------------------------------------
# EXPECTED OUTPUT (yours should match, modulo trailing whitespace)
# ----------------------------------------------------------------------------
#
# # Folder/project tree for organizations/acme.com
#
# folder: acme.com
# ├── folder: bootstrap
# ├── folder: shared
# │   ├── project: acme-platform-network-shared-7f3a
# │   └── project: acme-platform-observability-shared-7f3a
# └── folder: workloads
#     ├── folder: payments
#     │   ├── folder: checkout
#     │   │   ├── project: acme-payments-checkout-dev-7f3a
#     │   │   └── project: acme-payments-checkout-prod-7f3a
#     │   └── folder: ledger
#     │       ├── project: acme-payments-ledger-dev-7f3a
#     │       └── project: acme-payments-ledger-prod-7f3a
#     └── folder: search
#         ├── folder: indexer
#         │   ├── project: acme-search-indexer-dev-7f3a
#         │   ├── project: acme-search-indexer-staging-7f3a
#         │   └── project: acme-search-indexer-prod-7f3a
#         └── folder: ranking
#             ├── project: acme-search-ranking-dev-7f3a
#             └── project: acme-search-ranking-prod-7f3a
#
# # Boundary justification
#
# Boundary     Kind    Why it exists (access + policy)
# ------------ ------- ----------------------------------------------------------------------
# bootstrap    folder  Isolates Terraform state + break-glass; tightest access in the org.
# shared       folder  Platform-owned shared infra (VPC host, logging); read by all, written by platform only.
# workloads    folder  All product workloads; per-BU subfolders carry team ownership, per-env leaves carry environment policy.
# payments     folder  PCI-regulated BU; prod leaf gets strict org policy (Shielded VM, OS Login) that search does not need.
#
# ----------------------------------------------------------------------------
# WRITEUP (do this in writeup.md, ~3 short paragraphs)
# ----------------------------------------------------------------------------
#
#  1. Why does `platform` map to a FLAT `shared/` folder instead of getting
#     per-team, per-env subfolders like the product BUs? (Hint: shared infra is
#     not per-environment; the VPC host project is one project, used by all.)
#
#  2. Defend the `payments` subtree. What org policy would you attach at the
#     `payments/checkout/prod` leaf that you would NOT attach at any search
#     project, and why does the folder boundary make that cheap to enforce?
#
#  3. Pick one boundary you were TEMPTED to add but did not (e.g. a per-region
#     folder, or a folder per microservice). State why adding it would have been
#     "filing, not policy" and would have painted you into a corner.
#
# ----------------------------------------------------------------------------
# HINTS (read only if stuck >15 min)
# ----------------------------------------------------------------------------
#
# build_tree skeleton:
#
#   def build_tree(org):
#       root = Node("folder", ORG_DOMAIN)
#       root.children.append(Node("folder", "bootstrap"))
#
#       shared = Node("folder", "shared")
#       workloads = Node("folder", "workloads")
#
#       for bu in org:
#           if bu.name == "platform":
#               for team in bu.teams:
#                   pid = project_id_for(bu.name, team.name, "shared")
#                   shared.children.append(Node("project", team.name, project_id=pid))
#               continue
#           bu_folder = Node("folder", bu.name)
#           for team in bu.teams:
#               team_folder = Node("folder", team.name)
#               for env in team.environments:
#                   pid = project_id_for(bu.name, team.name, env)
#                   team_folder.children.append(Node("project", env, project_id=pid))
#               bu_folder.children.append(team_folder)
#           workloads.children.append(bu_folder)
#
#       root.children.append(shared)
#       root.children.append(workloads)
#       return root
#
# justification_rows: just return the four tuples written in the docstring,
# in that exact order.
#
# ----------------------------------------------------------------------------
