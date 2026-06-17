#!/usr/bin/env python3
"""Exercise 3 - gcloud configurations: dev / prod / admin, switched safely.

Goal: Build the muscle memory of named `gcloud` configurations - separate,
      named bundles of CLI properties (account, project, region) that you
      switch between with `gcloud config configurations activate`. The senior
      habit this drills: the active configuration is the difference between
      "delete the dev bucket" and "delete the PROD bucket", so you (a) always
      know which one is active and (b) refuse destructive commands in prod
      unless you confirm.

Estimated time: 40 minutes.

WHY A PYTHON WRAPPER?

  You will run the raw `gcloud config configurations` commands by hand first
  (see the SHELL DRILL block at the bottom). Then you wrap them in this tiny,
  testable Python guard so the lesson sticks: a CLI that prints the active
  config in every prompt and blocks a destructive verb against `prod` without
  an explicit confirmation. This is a real pattern teams ship in their
  dotfiles.

HOW TO USE THIS FILE

  Python 3.11+, standard library only. It shells out to `gcloud`.

      # Do the shell drill first (bottom of file), then:
      python3 exercise-03-gcloud-configurations.py list
      python3 exercise-03-gcloud-configurations.py active
      python3 exercise-03-gcloud-configurations.py guard prod "gcloud storage rm -r gs://x"

  Fill in the TWO functions marked `# TODO`. The script has a built-in
  self-test you can run WITHOUT gcloud installed:

      python3 exercise-03-gcloud-configurations.py selftest

ACCEPTANCE CRITERIA

  [ ] You created three configurations by hand: dev, prod, admin (shell drill).
  [ ] `gcloud config configurations list` shows all three.
  [ ] Both TODOs implemented.
  [ ] `python3 exercise-03-gcloud-configurations.py selftest` prints "all
      self-tests passed".
  [ ] `guard prod "<destructive cmd>"` refuses without confirmation; the same
      against `dev` proceeds.

Hints at the bottom. Don't peek for 15 minutes.
"""

from __future__ import annotations

import subprocess
import sys

# Verbs we consider destructive enough to require confirmation in prod.
DESTRUCTIVE_VERBS: tuple[str, ...] = (
    "delete",
    "rm",
    "destroy",
    "remove",
    "disable",
    "detach",
    "reset",
)

# Configurations we treat as "blast radius - confirm first".
PROTECTED_CONFIGS: tuple[str, ...] = ("prod", "admin")


# ----------------------------------------------------------------------------
# Functions to implement
# ----------------------------------------------------------------------------


def is_destructive(command: str) -> bool:
    """Return True if `command` contains a destructive verb as a whole word.

    A "whole word" means it appears as one of the space-separated tokens, so
    that "gcloud storage rm gs://x" trips on "rm" but a project named
    "my-rm-tool" in "gcloud config set project my-rm-tool" does NOT.

    Examples:
        is_destructive("gcloud storage rm -r gs://b")  -> True
        is_destructive("gcloud projects delete p")     -> True
        is_destructive("gcloud projects list")         -> False
        is_destructive("gcloud config set project my-rm-tool") -> False

    TODO: tokenize on whitespace and check membership against DESTRUCTIVE_VERBS.
    """
    raise NotImplementedError


def needs_confirmation(config_name: str, command: str) -> bool:
    """Return True iff this command should be blocked pending confirmation.

    The rule: block when the active configuration is protected
    (PROTECTED_CONFIGS) AND the command is destructive.

    Examples:
        needs_confirmation("dev",  "gcloud projects delete p") -> False
        needs_confirmation("prod", "gcloud projects delete p") -> True
        needs_confirmation("prod", "gcloud projects list")     -> False
        needs_confirmation("admin","gcloud iam roles delete r") -> True

    TODO: combine the protected-config check with is_destructive().
    """
    raise NotImplementedError


# ----------------------------------------------------------------------------
# gcloud wrappers (provided)
# ----------------------------------------------------------------------------


def _run(args: list[str]) -> str:
    """Run a gcloud command and return stdout (raises on non-zero exit)."""
    result = subprocess.run(
        args, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def list_configurations() -> str:
    """Return the table of all named configurations."""
    return _run(
        [
            "gcloud",
            "config",
            "configurations",
            "list",
            "--format=table(name, is_active, properties.core.project, properties.core.account)",
        ]
    )


def active_configuration() -> str:
    """Return the name of the currently active configuration."""
    return _run(
        [
            "gcloud",
            "config",
            "configurations",
            "list",
            "--filter=is_active=true",
            "--format=value(name)",
        ]
    )


def guard(config_name: str, command: str, *, confirmed: bool) -> int:
    """Decide whether to run `command` under the named config.

    Returns a process-style exit code: 0 = proceed, 1 = blocked.
    """
    banner = f"[{config_name}] $ {command}"
    print(banner)
    if needs_confirmation(config_name, command) and not confirmed:
        print(
            f"REFUSED: '{command}' is destructive and the active config is "
            f"'{config_name}' (protected). Re-run with --yes to confirm.",
            file=sys.stderr,
        )
        return 1
    print(f"PROCEED: would execute under config '{config_name}'.")
    return 0


# ----------------------------------------------------------------------------
# Self-test (no gcloud required)
# ----------------------------------------------------------------------------


def selftest() -> int:
    cases_destructive = [
        ("gcloud storage rm -r gs://b", True),
        ("gcloud projects delete p", True),
        ("gcloud projects list", False),
        ("gcloud config set project my-rm-tool", False),
        ("gcloud compute instances reset vm-1", True),
        ("gcloud services enable compute.googleapis.com", False),
    ]
    for cmd, want in cases_destructive:
        got = is_destructive(cmd)
        assert got == want, f"is_destructive({cmd!r}) = {got}, want {want}"

    cases_confirm = [
        ("dev", "gcloud projects delete p", False),
        ("prod", "gcloud projects delete p", True),
        ("prod", "gcloud projects list", False),
        ("admin", "gcloud iam roles delete r", True),
        ("dev", "gcloud storage rm gs://b", False),
    ]
    for cfg, cmd, want in cases_confirm:
        got = needs_confirmation(cfg, cmd)
        assert got == want, f"needs_confirmation({cfg!r}, {cmd!r}) = {got}, want {want}"

    print("all self-tests passed")
    return 0


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    cmd = argv[1]
    if cmd == "selftest":
        return selftest()
    if cmd == "list":
        print(list_configurations())
        return 0
    if cmd == "active":
        print(f"active configuration: {active_configuration()}")
        return 0
    if cmd == "guard":
        if len(argv) < 4:
            print("usage: guard <config> <command> [--yes]", file=sys.stderr)
            return 2
        confirmed = "--yes" in argv
        return guard(argv[2], argv[3], confirmed=confirmed)

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))


# ----------------------------------------------------------------------------
# SHELL DRILL - do this by hand FIRST (it is the actual skill being graded)
# ----------------------------------------------------------------------------
#
#   # Create three named configurations.
#   gcloud config configurations create dev
#   gcloud config configurations create prod
#   gcloud config configurations create admin
#
#   # Set per-config properties. Each `set` writes to the ACTIVE config, so
#   # activate first, then set.
#   gcloud config configurations activate dev
#   gcloud config set account you@acme.com
#   gcloud config set project acme-api-dev-7f3a
#   gcloud config set compute/region us-central1
#
#   gcloud config configurations activate prod
#   gcloud config set account you@acme.com
#   gcloud config set project acme-api-prod-2b91
#   gcloud config set compute/region us-central1
#
#   gcloud config configurations activate admin
#   gcloud config set account admin@acme.com   # often a separate break-glass identity
#
#   # See them all, and which is active.
#   gcloud config configurations list
#   gcloud config configurations describe prod
#
#   # Switch. THIS is the muscle memory: never run a destructive command
#   # without checking the active config first.
#   gcloud config configurations activate dev
#   gcloud config get-value project        # confirm before you act
#
# EXPECTED `gcloud config configurations list` (your projects/accounts vary):
#
#   NAME   IS_ACTIVE  ACCOUNT          PROJECT
#   admin  False      admin@acme.com
#   dev    True       you@acme.com     acme-api-dev-7f3a
#   prod   False      you@acme.com     acme-api-prod-2b91
#
# ----------------------------------------------------------------------------
# HINTS (read only if stuck >15 min)
# ----------------------------------------------------------------------------
#
# is_destructive:
#   def is_destructive(command):
#       tokens = command.split()
#       return any(token in DESTRUCTIVE_VERBS for token in tokens)
#
# needs_confirmation:
#   def needs_confirmation(config_name, command):
#       return config_name in PROTECTED_CONFIGS and is_destructive(command)
#
# ----------------------------------------------------------------------------
