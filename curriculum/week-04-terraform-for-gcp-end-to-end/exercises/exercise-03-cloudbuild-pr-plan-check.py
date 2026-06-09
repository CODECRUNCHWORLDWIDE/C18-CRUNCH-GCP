#!/usr/bin/env python3
"""Exercise 3 — Wire a terraform plan into a Cloud Build PR check that comments
the plan on the pull request.

Goal
----
Run `terraform plan`, capture both a human-readable form (for the PR comment) and
the machine-readable JSON (for a structured summary), then POST the result as an
issue comment on the pull request via the GitHub REST API. This is the primitive
that Atlantis automates; you build it by hand so you understand what it does.

The plan-review workflow this completes (from Lecture 1):
    1. Every change goes through a pull request.
    2. CI runs fmt -check, validate, and plan on the PR.   <-- this script
    3. A human reads the plan comment before merge.
    4. apply runs from CI after merge (never from a laptop), via WIF (no key).

How this runs
-------------
In Cloud Build, this script is the final step of a trigger scoped to pull requests.
Cloud Build sets substitution variables ($_PR_NUMBER, $REPO_FULL_NAME, etc.) which
the cloudbuild.yaml passes in as environment variables. The script:

    1. Runs `terraform init -input=false` (no-op if already inited via cache).
    2. Runs `terraform fmt -check -recursive` — fails the build on a format diff.
    3. Runs `terraform validate`.
    4. Runs `terraform plan -no-color -out=tfplan` (the binary plan).
    5. Runs `terraform show -no-color tfplan`        -> human text for the comment.
    6. Runs `terraform show -json tfplan`            -> JSON for the change summary.
    7. Posts a comment on the PR with the summary + the (truncated) plan text.
    8. Exits non-zero ONLY on init/fmt/validate/plan errors — a plan that proposes
       changes is exit code 0 here (the comment IS the gate; a human reviews it).

Running it locally (no GCP, no real PR needed)
----------------------------------------------
    # Dry-run against a Terraform directory; prints the comment to stdout
    # instead of calling GitHub:
    export TF_DIR=./envs/dev
    python3 exercise-03-cloudbuild-pr-plan-check.py --dry-run

    # Real run (posts to GitHub):
    export GITHUB_TOKEN=ghp_xxx
    export GITHUB_REPOSITORY=CODE-CRUNCH-CLUB/c18-week04
    export PR_NUMBER=42
    export TF_DIR=./envs/dev
    python3 exercise-03-cloudbuild-pr-plan-check.py

Standard library only — no pip install. urllib for the HTTP call, subprocess for
terraform, json for parsing. Python 3.11+.

Acceptance criteria
-------------------
    [ ] fmt -check / validate failures fail the build (non-zero exit).
    [ ] A plan with changes posts a comment and exits 0 (human reviews the comment).
    [ ] A plan with NO changes posts a "No changes" comment and exits 0.
    [ ] A terraform/init error exits non-zero with the error in the logs.
    [ ] --dry-run prints the comment body to stdout without calling GitHub.
    [ ] The JSON summary reports correct add/change/destroy counts.
    [ ] The comment flags any resource with "forces replacement" (the footgun).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

# GitHub truncates comments past 65,536 chars; leave headroom for the wrapper.
MAX_PLAN_CHARS = 60_000


@dataclass(frozen=True)
class PlanSummary:
    """Structured counts derived from `terraform show -json`."""

    to_add: int
    to_change: int
    to_destroy: int
    replacements: list[str]  # addresses of resources being destroyed-and-recreated

    @property
    def has_changes(self) -> bool:
        return bool(self.to_add or self.to_change or self.to_destroy)


def run(cmd: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing stdout/stderr as text. Does not raise on non-zero;
    callers inspect returncode so we can surface terraform's own error text."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def die(message: str, code: int = 1) -> None:
    print(f"::error:: {message}", file=sys.stderr)
    sys.exit(code)


def terraform_init(tf_dir: str) -> None:
    proc = run(["terraform", "init", "-input=false", "-no-color"], tf_dir)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        die("terraform init failed")


def terraform_fmt_check(tf_dir: str) -> None:
    proc = run(["terraform", "fmt", "-check", "-recursive", "-no-color"], tf_dir)
    if proc.returncode != 0:
        # fmt -check exits non-zero and lists the files that need formatting.
        print(proc.stdout)
        die(
            "terraform fmt -check failed — run `terraform fmt -recursive` and commit. "
            f"Files needing format:\n{proc.stdout.strip()}"
        )


def terraform_validate(tf_dir: str) -> None:
    proc = run(["terraform", "validate", "-no-color"], tf_dir)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        die("terraform validate failed")


def terraform_plan(tf_dir: str) -> None:
    """Produce a binary plan file (tfplan). A plan that merely proposes changes
    is NOT an error here — the comment is the gate. We only fail on a real error
    (bad config, auth failure, etc.)."""
    proc = run(
        ["terraform", "plan", "-input=false", "-no-color", "-out=tfplan"],
        tf_dir,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        die("terraform plan failed")


def terraform_show_text(tf_dir: str) -> str:
    proc = run(["terraform", "show", "-no-color", "tfplan"], tf_dir)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        die("terraform show (text) failed")
    return proc.stdout


def terraform_show_json(tf_dir: str) -> dict:
    proc = run(["terraform", "show", "-json", "tfplan"], tf_dir)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        die("terraform show -json failed")
    return json.loads(proc.stdout)


def summarize(plan_json: dict) -> PlanSummary:
    """Walk resource_changes[].change.actions to count adds/changes/destroys and
    flag replacements. A replacement is actions == ["delete","create"] or
    ["create","delete"] — i.e. a destroy-and-recreate, the footgun from Lecture 1."""
    to_add = to_change = to_destroy = 0
    replacements: list[str] = []

    for rc in plan_json.get("resource_changes", []):
        actions = rc.get("change", {}).get("actions", [])
        addr = rc.get("address", "<unknown>")

        if actions == ["create"]:
            to_add += 1
        elif actions == ["update"]:
            to_change += 1
        elif actions == ["delete"]:
            to_destroy += 1
        elif set(actions) == {"create", "delete"}:
            # Replacement: counts as one add AND one destroy, and gets flagged.
            to_add += 1
            to_destroy += 1
            replacements.append(addr)
        # actions == ["no-op"] or ["read"] contribute nothing.

    return PlanSummary(
        to_add=to_add,
        to_change=to_change,
        to_destroy=to_destroy,
        replacements=replacements,
    )


def build_comment(summary: PlanSummary, plan_text: str, tf_dir: str) -> str:
    """Render the Markdown comment body. Leads with the verdict, then any
    replacement warnings (the thing a human MUST see), then the collapsed plan."""
    if not summary.has_changes:
        header = "### ✅ Terraform plan: no changes\n\n`No changes. Your infrastructure matches the configuration.`"
    else:
        header = (
            "### 📋 Terraform plan: changes proposed\n\n"
            f"**Plan:** `{summary.to_add}` to add, "
            f"`{summary.to_change}` to change, "
            f"`{summary.to_destroy}` to destroy."
        )

    warning = ""
    if summary.replacements:
        bullets = "\n".join(f"- `{addr}`" for addr in summary.replacements)
        warning = (
            "\n\n> ⚠️ **Resources will be DESTROYED and RECREATED "
            "(`forces replacement`). Review carefully — this is data loss on a "
            f"stateful resource:**\n{bullets}"
        )

    truncated = plan_text
    note = ""
    if len(plan_text) > MAX_PLAN_CHARS:
        truncated = plan_text[:MAX_PLAN_CHARS]
        note = "\n\n_…plan truncated; see the full output in the Cloud Build logs._"

    body = (
        f"{header}{warning}\n\n"
        f"<sub>directory: `{tf_dir}`</sub>\n\n"
        "<details><summary>Show plan</summary>\n\n"
        f"```\n{truncated}\n```{note}\n\n"
        "</details>\n\n"
        "<sub>Posted by the Cloud Build PR plan check (C18 Week 04, Exercise 3).</sub>"
    )
    return body


def post_pr_comment(repo: str, pr_number: str, token: str, body: str) -> None:
    """POST an issue comment on the PR. The PR-comments endpoint is the issues
    comments endpoint — a PR is an issue with code attached."""
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    payload = json.dumps({"body": body}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "c18-week04-plan-check")

    try:
        with urllib.request.urlopen(request) as response:
            if response.status not in (200, 201):
                die(f"GitHub returned HTTP {response.status}")
            data = json.loads(response.read())
            print(f"Posted PR comment: {data.get('html_url')}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        die(f"GitHub API error HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        die(f"Could not reach GitHub: {exc.reason}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terraform plan PR check")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the comment body to stdout instead of calling GitHub.",
    )
    parser.add_argument(
        "--tf-dir",
        default=os.environ.get("TF_DIR", "."),
        help="Directory to run terraform in (default: $TF_DIR or '.').",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tf_dir = args.tf_dir

    if not os.path.isdir(tf_dir):
        die(f"TF_DIR '{tf_dir}' is not a directory")

    # Run the cheap gates first so we fail fast on formatting/validation.
    terraform_init(tf_dir)
    terraform_fmt_check(tf_dir)
    terraform_validate(tf_dir)

    # Produce the plan and both renderings of it.
    terraform_plan(tf_dir)
    plan_text = terraform_show_text(tf_dir)
    plan_json = terraform_show_json(tf_dir)
    summary = summarize(plan_json)
    comment = build_comment(summary, plan_text, tf_dir)

    if args.dry_run:
        print("=== DRY RUN: comment body that WOULD be posted ===\n")
        print(comment)
        print(
            f"\n=== summary: +{summary.to_add} ~{summary.to_change} "
            f"-{summary.to_destroy}, replacements={summary.replacements} ==="
        )
        return

    repo = os.environ.get("GITHUB_REPOSITORY")
    pr_number = os.environ.get("PR_NUMBER")
    token = os.environ.get("GITHUB_TOKEN")
    missing = [
        name
        for name, val in (
            ("GITHUB_REPOSITORY", repo),
            ("PR_NUMBER", pr_number),
            ("GITHUB_TOKEN", token),
        )
        if not val
    ]
    if missing:
        die(f"Missing required environment variables: {', '.join(missing)}")

    # mypy/readers: the die() above guarantees these are non-None past here.
    assert repo and pr_number and token
    post_pr_comment(repo, pr_number, token, comment)


if __name__ == "__main__":
    main()


# =============================================================================
# THE cloudbuild.yaml THAT INVOKES THIS SCRIPT
#
# Save as cloudbuild.yaml at your repo root. Wire a Cloud Build trigger scoped to
# pull requests (Cloud Build console -> Triggers -> "Pull request" event), and
# attach a service account that uses Workload Identity Federation (Week 2) so
# there is NO key file. Store the GitHub token in Secret Manager and surface it
# as $GITHUB_TOKEN via availableSecrets.
#
#   steps:
#     - id: plan-and-comment
#       name: 'hashicorp/terraform:1.9'
#       entrypoint: 'sh'
#       secretEnv: ['GITHUB_TOKEN']
#       env:
#         - 'TF_DIR=envs/dev'
#         - 'GITHUB_REPOSITORY=$REPO_FULL_NAME'
#         - 'PR_NUMBER=$_PR_NUMBER'
#       args:
#         - '-c'
#         - |
#           apk add --no-cache python3
#           python3 exercise-03-cloudbuild-pr-plan-check.py
#
#   availableSecrets:
#     secretManager:
#       - versionName: projects/$PROJECT_ID/secrets/github-pr-token/versions/latest
#         env: 'GITHUB_TOKEN'
#
#   options:
#     logging: CLOUD_LOGGING_ONLY
#
# $REPO_FULL_NAME and $_PR_NUMBER are populated by Cloud Build on a PR trigger.
# The build's service account needs roles/viewer (to refresh state for the plan)
# and read access to the state bucket. apply is NOT run here — only plan. apply
# runs from a SEPARATE trigger on push-to-main, after the PR merges and a human
# has read this comment.
# =============================================================================
