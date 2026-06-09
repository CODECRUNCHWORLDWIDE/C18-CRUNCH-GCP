#!/usr/bin/env python3
"""Exercise 3 — Find the over-privileged service account in a project.

Goal
----
Audit a project's IAM with the Cloud Asset Inventory API and rank every
service account by "blast radius": how many distinct permissions it can
exercise, weighted by how dangerous the roles it holds are. The SA at the top
of the ranking is the one an attacker wants to compromise first, and the one
you should scope down first.

This is the automated form of the manual audit in Lecture 1, §1.7. It runs
against any project you can read with `roles/cloudasset.viewer`.

Why this approach
-----------------
`gcloud asset search-all-iam-policies` is the right primitive, but eyeballing
its output does not scale past a handful of bindings. This tool pulls every
IAM binding in the project, attributes each to the service accounts it grants,
expands roles to their permission counts, flags the five mistakes from
Lecture 1, and prints a ranked report. No service-account key is used: it
authenticates with Application Default Credentials (your `gcloud auth
application-default login` session), which is the keyless path.

Usage
-----
    python3 -m venv .venv && source .venv/bin/activate
    pip install google-cloud-asset google-cloud-iam

    gcloud auth application-default login   # keyless ADC, no JSON key file
    export PROJECT_ID="$(gcloud config get-value project)"

    python3 exercise-03-audit-overprivileged-sa.py "$PROJECT_ID"

Acceptance criteria
-------------------
    [ ] Runs against a real project with only ADC (no key file).
    [ ] Prints every service account in the project ranked by blast radius.
    [ ] Flags basic roles (owner/editor/viewer) as Mistake #1.
    [ ] Flags any project-level serviceAccountUser binding as Mistake #5.
    [ ] Flags unconditional roles/owner as a critical finding.
    [ ] Exit code is non-zero if any critical finding is present (CI-friendly).

Expected output shape (your numbers differ)
-------------------------------------------
    === IAM blast-radius audit: my-project ===
    Service accounts found: 4

    RANK  PERMS  ROLES                                   SERVICE ACCOUNT
    ----  -----  --------------------------------------  -------------------------------
       1   3812  roles/editor                            123-compute@developer.gservic...
       2    178  roles/storage.admin                     etl@my-project.iam.gserviceac...
       3     14  reportPublisher (custom)                reporter@my-project.iam.gservi...
       4      0  (none)                                  unused@my-project.iam.gservice...

    FINDINGS
      [CRITICAL] 123-compute@... holds roles/editor (basic role, Mistake #1)
      [HIGH]     project-level roles/iam.serviceAccountUser to group:devs@ (Mistake #5)

    2 finding(s). Highest severity: CRITICAL.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

from google.api_core.exceptions import GoogleAPIError, PermissionDenied
from google.cloud import asset_v1
from google.cloud import iam_admin_v1


BASIC_ROLES = {"roles/owner", "roles/editor", "roles/viewer"}

# Roles dangerous enough to flag even though they are predefined.
SENSITIVE_ROLES = {
    "roles/iam.serviceAccountTokenCreator",
    "roles/iam.serviceAccountUser",
    "roles/iam.serviceAccountKeyAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
}


@dataclass
class Finding:
    severity: str  # CRITICAL | HIGH | MEDIUM
    message: str

    _ORDER = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1}

    @property
    def rank(self) -> int:
        return self._ORDER[self.severity]


@dataclass
class SaProfile:
    email: str
    roles: set[str] = field(default_factory=set)
    permission_count: int = 0

    @property
    def member(self) -> str:
        return f"serviceAccount:{self.email}"


def list_service_accounts(project_id: str) -> dict[str, SaProfile]:
    """Return {email: SaProfile} for every SA defined in the project."""
    client = iam_admin_v1.IAMClient()
    request = iam_admin_v1.ListServiceAccountsRequest(name=f"projects/{project_id}")
    profiles: dict[str, SaProfile] = {}
    for sa in client.list_service_accounts(request=request):
        profiles[sa.email] = SaProfile(email=sa.email)
    return profiles


def role_permission_count(project_id: str, role: str) -> int:
    """How many permissions a role grants. Custom roles are project-scoped;
    predefined roles are global. Basic roles are huge, so we cap their reported
    count at a sentinel to keep the table readable while still ranking them top.
    """
    if role in BASIC_ROLES:
        # owner/editor are thousands of permissions; we don't need the exact
        # number, only that they dwarf everything else.
        return {"roles/owner": 9999, "roles/editor": 3812, "roles/viewer": 2600}[role]

    client = iam_admin_v1.IAMClient()
    try:
        if role.startswith("projects/"):
            name = role  # custom role, already a full resource name
        else:
            name = role  # predefined: get_role accepts "roles/foo"
        fetched = client.get_role(request=iam_admin_v1.GetRoleRequest(name=name))
        return len(fetched.included_permissions)
    except GoogleAPIError:
        # A role we can't read (rare) contributes 1 so it still ranks.
        return 1


def collect_bindings(project_id: str) -> list[tuple[str, list[str], bool]]:
    """Return [(role, members, has_condition)] for every binding on the project,
    via Cloud Asset Inventory's search-all-iam-policies.
    """
    client = asset_v1.AssetServiceClient()
    scope = f"projects/{project_id}"
    request = asset_v1.SearchAllIamPoliciesRequest(scope=scope)
    out: list[tuple[str, list[str], bool]] = []
    for result in client.search_all_iam_policies(request=request):
        policy = result.policy
        for binding in policy.bindings:
            has_condition = bool(binding.condition and binding.condition.expression)
            out.append((binding.role, list(binding.members), has_condition))
    return out


def audit(project_id: str) -> tuple[list[SaProfile], list[Finding]]:
    profiles = list_service_accounts(project_id)
    findings: list[Finding] = []
    bindings = collect_bindings(project_id)

    perm_cache: dict[str, int] = {}

    for role, members, has_condition in bindings:
        if role not in perm_cache:
            perm_cache[role] = role_permission_count(project_id, role)
        perms = perm_cache[role]

        # Attribute role to the SAs it is granted to.
        for member in members:
            if member.startswith("serviceAccount:"):
                email = member.split(":", 1)[1]
                prof = profiles.setdefault(email, SaProfile(email=email))
                prof.roles.add(role)
                prof.permission_count += perms

            # Mistake #5: project-level serviceAccountUser to ANY member.
            if role == "roles/iam.serviceAccountUser":
                findings.append(
                    Finding(
                        "HIGH",
                        f"project-level roles/iam.serviceAccountUser to {member} "
                        f"(Mistake #5: grant on the SA resource, not the project)",
                    )
                )

        # Mistake #1: basic roles anywhere.
        if role in BASIC_ROLES:
            sev = "CRITICAL" if role == "roles/owner" else "HIGH"
            who = ", ".join(members[:3]) + ("…" if len(members) > 3 else "")
            cond = "" if not has_condition else " (conditional)"
            findings.append(
                Finding(
                    sev,
                    f"{role} granted to {who}{cond} "
                    f"(Mistake #1: basic-role sprawl — replace with predefined/custom)",
                )
            )

        # Unconditional owner is the worst single binding shape.
        if role == "roles/owner" and not has_condition:
            for member in members:
                findings.append(
                    Finding(
                        "CRITICAL",
                        f"UNCONDITIONAL roles/owner to {member} — no break-glass "
                        f"separation (Mistake #4) and maximum blast radius",
                    )
                )

    ranked = sorted(profiles.values(), key=lambda p: p.permission_count, reverse=True)
    return ranked, findings


def print_report(project_id: str, ranked: list[SaProfile], findings: list[Finding]) -> None:
    print(f"=== IAM blast-radius audit: {project_id} ===")
    print(f"Service accounts found: {len(ranked)}\n")

    print(f"{'RANK':>4}  {'PERMS':>5}  {'ROLES':<38}  SERVICE ACCOUNT")
    print(f"{'----':>4}  {'-----':>5}  {'-' * 38}  {'-' * 31}")
    for i, p in enumerate(ranked, start=1):
        roles_label = ", ".join(sorted(p.roles)) or "(none)"
        if len(roles_label) > 38:
            roles_label = roles_label[:37] + "…"
        email = p.email if len(p.email) <= 31 else p.email[:30] + "…"
        print(f"{i:>4}  {p.permission_count:>5}  {roles_label:<38}  {email}")

    print("\nFINDINGS")
    if not findings:
        print("  (none — this project passes the five-mistake checklist)")
    else:
        # De-duplicate and sort by severity.
        seen: set[str] = set()
        unique = [f for f in findings if not (f.message in seen or seen.add(f.message))]
        for f in sorted(unique, key=lambda x: x.rank, reverse=True):
            print(f"  [{f.severity:<8}] {f.message}")

    if findings:
        worst = max(findings, key=lambda f: f.rank).severity
        print(f"\n{len(set(f.message for f in findings))} finding(s). Highest severity: {worst}.")
    else:
        print("\n0 findings.")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <project_id>", file=sys.stderr)
        return 2
    project_id = argv[1]
    try:
        ranked, findings = audit(project_id)
    except PermissionDenied as exc:
        print(
            "PermissionDenied: you need roles/cloudasset.viewer and "
            "roles/iam.roleViewer on the project.\n"
            f"  detail: {exc.message}",
            file=sys.stderr,
        )
        return 3
    print_report(project_id, ranked, findings)

    # CI-friendly: non-zero exit if anything CRITICAL is present.
    if any(f.severity == "CRITICAL" for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
