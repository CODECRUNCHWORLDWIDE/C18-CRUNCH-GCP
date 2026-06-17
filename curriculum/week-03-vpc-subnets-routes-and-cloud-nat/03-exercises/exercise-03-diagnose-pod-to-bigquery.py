#!/usr/bin/env python3
"""Exercise 3 — Diagnose "why can't my GKE pod reach BigQuery?"

Goal
----
Build a diagnostic decision-tree tool that walks the *exact* ordered checklist a
senior engineer uses when a GKE pod cannot reach a Google API (BigQuery, GCS,
...). The single most useful thing this tool teaches is how to distinguish a
**Private Google Access (PGA)** problem from a **Private Service Connect (PSC)**
problem — the two are constantly confused, and they have different fixes.

This is a *runnable, self-contained* tool. It ships with a built-in scenario
simulator so you can run it with zero GCP access and watch the decision tree
classify several realistic failures. When you DO have a live cluster, the same
tree drives the real `gcloud`/`kubectl` commands printed for each node.

Run it
------
    python3 exercise-03-diagnose-pod-to-bigquery.py            # run all scenarios
    python3 exercise-03-diagnose-pod-to-bigquery.py --list     # list scenarios
    python3 exercise-03-diagnose-pod-to-bigquery.py --scenario pga_off
    python3 exercise-03-diagnose-pod-to-bigquery.py --commands # print the live runbook

Estimated time: 60 minutes (read the tree, run the scenarios, then fill in the
ONE TODO at the bottom: add a new scenario and confirm the tree classifies it).

Requires only the Python 3.11+ standard library. No third-party packages, no
GCP credentials, nothing to install.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    """The terminal classification the decision tree arrives at."""

    DNS = "DNS_MISRESOLUTION"
    ROUTE = "MISSING_OR_BAD_ROUTE"
    FIREWALL = "FIREWALL_DENY"
    PGA_OFF = "PRIVATE_GOOGLE_ACCESS_DISABLED"
    NEEDS_PSC = "NEEDS_PRIVATE_SERVICE_CONNECT"
    IAM = "IAM_PERMISSION_DENIED"
    WORKLOAD_IDENTITY = "WORKLOAD_IDENTITY_NOT_BOUND"
    HEALTHY = "HEALTHY_NO_NETWORK_PROBLEM"


# Human-readable fix for each verdict. These are the actual remediations, in the
# voice you'd write in a postmortem's "action items" section.
FIXES: dict[Verdict, str] = {
    Verdict.DNS: (
        "bigquery.googleapis.com is resolving to a PUBLIC IP (142.250.x.x) instead "
        "of the private VIP (199.36.153.8). Fix the private Cloud DNS zone that "
        "overrides *.googleapis.com -> private.googleapis.com (A 199.36.153.8-11). "
        "This is the Exercise 2 setup; the pod inherits the node's resolver."
    ),
    Verdict.ROUTE: (
        "There is no route to the private VIP 199.36.153.8/30. The default-internet- "
        "gateway route normally covers it; if you deleted/overrode the default route, "
        "add an explicit route dest_range=199.36.153.8/30 "
        "next_hop_gateway=default-internet-gateway."
    ),
    Verdict.FIREWALL: (
        "An egress firewall rule is blocking the path to 199.36.153.8/30:443. Add an "
        "EGRESS allow to 199.36.153.8/30 tcp:443 for the node service account / tag, "
        "BEFORE any broad egress deny (priority lower-numbered than the deny)."
    ),
    Verdict.PGA_OFF: (
        "Private Google Access is OFF on the node subnet. The nodes have no external "
        "IP and cannot reach Google APIs. Set private_ip_google_access=true on the "
        "subnet the node pool draws from. This is the #1 cause of this incident."
    ),
    Verdict.NEEDS_PSC: (
        "The target is NOT reachable via the shared *.googleapis.com VIP from this "
        "VPC topology (e.g. cross-VPC, VPC-SC perimeter requiring restricted VIP, or a "
        "published service rather than a Google API). PGA will not help; you need a "
        "Private Service Connect endpoint with an IP in your own subnet."
    ),
    Verdict.IAM: (
        "Network path is fine; the request reaches BigQuery and is rejected with a 403. "
        "The pod's identity lacks roles/bigquery.jobUser or dataViewer. This is an IAM "
        "problem masquerading as a network problem — the giveaway is a 403, not a hang."
    ),
    Verdict.WORKLOAD_IDENTITY: (
        "The pod's Kubernetes SA is not bound to a Google SA via Workload Identity, so "
        "the client falls back to no/anonymous credentials and BigQuery returns 401/403. "
        "Bind the KSA to a GSA (Week 02) and annotate the KSA. Network is NOT the issue."
    ),
    Verdict.HEALTHY: (
        "No network problem found. If the symptom persists, it is above the network "
        "layer (client config, endpoint typo, quota, regional dataset mismatch)."
    ),
}


@dataclass
class Probe:
    """The observable signals the decision tree consumes.

    In the simulator these are pre-set per scenario. Against a live cluster, each
    field maps to one command (see `live_runbook()` below) whose output you read
    and translate into the boolean/string here.
    """

    # What does bigquery.googleapis.com resolve to FROM THE POD? "private" if it
    # resolves into 199.36.153.0/24, "public" if 142.250.x.x / 173.194.x.x, etc.
    dns_resolution: str = "private"  # "private" | "public"

    # Is there a route in the node's VPC that covers 199.36.153.8/30?
    has_route_to_vip: bool = True

    # Does an egress firewall rule ALLOW tcp:443 to 199.36.153.8/30 (and is there
    # no higher-priority deny shadowing it)?
    egress_allowed_to_vip: bool = True

    # Is private_ip_google_access=true on the subnet the node pool uses?
    pga_enabled: bool = True

    # Is the *target* reachable via the shared *.googleapis.com VIP at all, given
    # the topology? False when you need PSC instead (cross-VPC, VPC-SC restricted,
    # published non-Google service).
    reachable_via_shared_vip: bool = True

    # If the request actually reaches BigQuery, what HTTP status comes back?
    # None means "no response — it hung / timed out at the network layer".
    api_http_status: int | None = 200

    # Is the pod's KSA bound to a GSA via Workload Identity?
    workload_identity_bound: bool = True

    # Does that GSA hold a BigQuery role (jobUser/dataViewer)?
    has_bigquery_iam: bool = True


@dataclass
class Scenario:
    name: str
    summary: str
    probe: Probe
    expected: Verdict
    trace: list[str] = field(default_factory=list)


def diagnose(p: Probe) -> tuple[Verdict, list[str]]:
    """The decision tree. ORDER MATTERS — we rule out the cheapest, most-common,
    most-isolating causes first, exactly the order you'd debug at 3am.

    Returns the verdict and a human-readable trace of every branch taken.
    """
    trace: list[str] = []

    # 1) DNS first. If the name resolves to a PUBLIC IP, nothing downstream matters
    #    — the pod is trying to reach the internet and (correctly) has no path.
    trace.append(f"1. DNS: bigquery.googleapis.com -> {p.dns_resolution} address")
    if p.dns_resolution != "private":
        trace.append("   -> resolves PUBLIC. The private DNS override is missing.")
        return Verdict.DNS, trace
    trace.append("   -> resolves to the private VIP. DNS is fine; continue.")

    # 2) Route. The name is right; is there a path to the VIP at all?
    trace.append("2. ROUTE: is 199.36.153.8/30 covered by a route?")
    if not p.has_route_to_vip:
        trace.append("   -> NO route to the VIP. Packets have nowhere to go.")
        return Verdict.ROUTE, trace
    trace.append("   -> route exists. Continue.")

    # 3) PGA. Even with DNS+route, a node with no external IP needs PGA on the
    #    subnet. This is THE most common real cause, so we check it explicitly.
    trace.append("3. PGA: private_ip_google_access on the node subnet?")
    if not p.pga_enabled:
        trace.append("   -> PGA is OFF. No-external-IP nodes cannot reach Google APIs.")
        return Verdict.PGA_OFF, trace
    trace.append("   -> PGA is on. Continue.")

    # 4) Firewall egress to the VIP.
    trace.append("4. FIREWALL: egress allow tcp:443 to 199.36.153.8/30?")
    if not p.egress_allowed_to_vip:
        trace.append("   -> egress to the VIP is DENIED (or shadowed by a deny).")
        return Verdict.FIREWALL, trace
    trace.append("   -> egress allowed. Continue.")

    # 5) Is the target even reachable via the SHARED VIP? If not, PGA was never
    #    going to work — this is the PGA-vs-PSC fork, the heart of the exercise.
    trace.append("5. REACHABILITY: target reachable via the shared *.googleapis.com VIP?")
    if not p.reachable_via_shared_vip:
        trace.append("   -> NOT reachable via shared VIP. PGA cannot help; you need PSC.")
        return Verdict.NEEDS_PSC, trace
    trace.append("   -> reachable via shared VIP. The NETWORK path is good.")

    # --- Past this point, the network is fine. Anything left is identity/IAM. ---

    # 6) The request reached BigQuery. What did it say?
    trace.append(f"6. RESPONSE: BigQuery returned HTTP {p.api_http_status}")
    if p.api_http_status is None:
        # Reached the VIP but no response: treat as a deeper network fault, but with
        # DNS/route/PGA/firewall already cleared, the realistic cause is the target
        # not actually being on the shared VIP — fold into the PSC verdict.
        trace.append("   -> no response despite a good local path. Re-examine target/PSC.")
        return Verdict.NEEDS_PSC, trace

    if p.api_http_status in (401, 403):
        # Identity problem. Distinguish "not bound at all" from "bound but unauthorized".
        trace.append("   -> 401/403 means the path WORKS but identity is rejected.")
        if not p.workload_identity_bound:
            trace.append("   -> pod KSA not bound to a GSA (Workload Identity).")
            return Verdict.WORKLOAD_IDENTITY, trace
        if not p.has_bigquery_iam:
            trace.append("   -> GSA lacks a BigQuery role.")
            return Verdict.IAM, trace
        # Bound and has role but still 403: most likely IAM scoping at the dataset.
        trace.append("   -> bound and has a project role; check dataset-level IAM.")
        return Verdict.IAM, trace

    trace.append("   -> 2xx. The pod CAN reach BigQuery. No network problem.")
    return Verdict.HEALTHY, trace


def live_runbook() -> str:
    """The real commands behind each decision-tree node, for use on a live cluster."""
    return """\
LIVE RUNBOOK — run these from a debug pod (kubectl run -it dbg --image=google/cloud-sdk:slim -- bash)

1. DNS    : dig +short bigquery.googleapis.com
            # expect: private.googleapis.com. then 199.36.153.x  (NOT 142.250.x.x)

2. ROUTE  : gcloud compute routes list --filter="network:NODE_VPC" \\
              --format="table(destRange,nextHopGateway.basename())" | grep 199.36.153
            # expect a route covering 199.36.153.8/30 (the default 0.0.0.0/0 counts)

3. PGA    : gcloud compute networks subnets describe NODE_SUBNET --region=REGION \\
              --format="value(privateIpGoogleAccess)"
            # expect: True

4. FIREWALL: gcloud compute firewall-rules list \\
              --filter="network:NODE_VPC AND direction:EGRESS" \\
              --format="table(name,priority,denied[].map().firewall_rule().list(),allowed[].map().firewall_rule().list())"
            # confirm no EGRESS deny shadows tcp:443 to 199.36.153.8/30

5. REACH  : gcloud network-management connectivity-tests create bq-reach \\
              --source-instance=NODE_VM --destination-ip-address=199.36.153.8 \\
              --destination-port=443 --protocol=TCP
            gcloud network-management connectivity-tests describe bq-reach \\
              --format="value(reachabilityDetails.result)"   # expect REACHABLE

6. IDENTITY: # from the pod, with the client library:
            python3 -c "from google.cloud import bigquery; \\
              print(list(bigquery.Client().query('SELECT 1 AS x').result()))"
            # 200/rows = healthy. 403 = IAM. 401 = Workload Identity not bound.
            kubectl get sa POD_SA -o jsonpath='{.metadata.annotations.iam\\.gke\\.io/gcp-service-account}'
            # empty annotation = the KSA is not bound to a GSA -> Workload Identity verdict
"""


def build_scenarios() -> list[Scenario]:
    """Realistic failure scenarios. Each one is a 3am incident someone actually had."""
    return [
        Scenario(
            name="healthy",
            summary="Everything wired correctly; BigQuery returns 200.",
            probe=Probe(),
            expected=Verdict.HEALTHY,
        ),
        Scenario(
            name="pga_off",
            summary="Nodes have no external IP and PGA was never enabled on the subnet.",
            probe=Probe(pga_enabled=False),
            expected=Verdict.PGA_OFF,
        ),
        Scenario(
            name="dns_public",
            summary="No private DNS zone; the name resolves to a public Google IP.",
            probe=Probe(dns_resolution="public"),
            expected=Verdict.DNS,
        ),
        Scenario(
            name="egress_denied",
            summary="A hardened egress-deny rule shadows the path to the VIP on tcp:443.",
            probe=Probe(egress_allowed_to_vip=False),
            expected=Verdict.FIREWALL,
        ),
        Scenario(
            name="needs_psc",
            summary=(
                "BigQuery sits behind a VPC-SC perimeter requiring the restricted VIP / a "
                "cross-VPC topology — the shared *.googleapis.com VIP does not reach it."
            ),
            probe=Probe(reachable_via_shared_vip=False),
            expected=Verdict.NEEDS_PSC,
        ),
        Scenario(
            name="wi_not_bound",
            summary="Network path is perfect but the pod KSA is not bound to a GSA; 401.",
            probe=Probe(api_http_status=401, workload_identity_bound=False),
            expected=Verdict.WORKLOAD_IDENTITY,
        ),
        Scenario(
            name="iam_denied",
            summary="Path and identity exist, but the GSA lacks a BigQuery role; 403.",
            probe=Probe(api_http_status=403, has_bigquery_iam=False),
            expected=Verdict.IAM,
        ),
        # =====================================================================
        # TODO — Add ONE more scenario of your own and confirm the tree
        #        classifies it correctly. Suggestion: "no route to the VIP
        #        because someone deleted the default route to harden egress and
        #        forgot to add the explicit 199.36.153.8/30 route."
        #        Set the right Probe fields and the expected Verdict, then run:
        #            python3 exercise-03-diagnose-pod-to-bigquery.py
        #        It must print PASS for your new scenario.
        # =====================================================================
        # Scenario(
        #     name="route_deleted",
        #     summary="Default route removed for egress hardening; VIP route forgotten.",
        #     probe=Probe(has_route_to_vip=False),
        #     expected=Verdict.ROUTE,
        # ),
    ]


def run_scenario(s: Scenario, verbose: bool) -> bool:
    verdict, trace = diagnose(s.probe)
    ok = verdict == s.expected
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {s.name}: {s.summary}")
    print(f"        verdict={verdict.value}  expected={s.expected.value}")
    if verbose or not ok:
        for line in trace:
            print(f"        {line}")
    print(f"        FIX: {FIXES[verdict]}")
    print()
    return ok


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List scenarios and exit.")
    parser.add_argument("--scenario", help="Run a single scenario by name (verbose).")
    parser.add_argument("--commands", action="store_true", help="Print the live runbook.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print the trace.")
    args = parser.parse_args(argv)

    scenarios = build_scenarios()

    if args.commands:
        print(live_runbook())
        return 0

    if args.list:
        for s in scenarios:
            print(f"{s.name:16s} -> expected {s.expected.value}")
        return 0

    if args.scenario:
        match = [s for s in scenarios if s.name == args.scenario]
        if not match:
            print(f"No scenario named {args.scenario!r}. Try --list.", file=sys.stderr)
            return 2
        return 0 if run_scenario(match[0], verbose=True) else 1

    print("=== GKE pod -> BigQuery diagnostic decision tree ===\n")
    results = [run_scenario(s, verbose=args.verbose) for s in scenarios]
    passed, total = sum(results), len(results)
    print(f"{passed}/{total} scenarios classified correctly.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

# -----------------------------------------------------------------------------
# EXPECTED OUTPUT (abridged) when you run `python3 exercise-03-...py`:
#
#   === GKE pod -> BigQuery diagnostic decision tree ===
#
#   [PASS] healthy: Everything wired correctly; BigQuery returns 200.
#           verdict=HEALTHY_NO_NETWORK_PROBLEM  expected=HEALTHY_NO_NETWORK_PROBLEM
#           FIX: No network problem found. ...
#
#   [PASS] pga_off: Nodes have no external IP and PGA was never enabled ...
#           verdict=PRIVATE_GOOGLE_ACCESS_DISABLED  expected=PRIVATE_GOOGLE_ACCESS_DISABLED
#           FIX: Private Google Access is OFF on the node subnet. ...
#   ... (one block per scenario) ...
#   7/7 scenarios classified correctly.
#
# ACCEPTANCE CRITERIA
#   [ ] The script runs with the stdlib only (no pip install).
#   [ ] All built-in scenarios print PASS.
#   [ ] You can articulate, from the `needs_psc` scenario, the one-sentence
#       difference between Private Google Access and Private Service Connect.
#   [ ] You added one new scenario (the TODO) and it prints PASS.
#
# REFLECTION (write 4-6 sentences in results-ex03.md):
#   1. Why does the tree check DNS before PGA, even though PGA-off is the more
#      common cause? (Hint: cost of the check, and isolation of the signal.)
#   2. The `iam_denied` and `wi_not_bound` scenarios both have a PERFECT network
#      path. What single observable distinguishes a network failure from these?
#   3. In `needs_psc`, why will turning on PGA never fix the problem?
# -----------------------------------------------------------------------------
