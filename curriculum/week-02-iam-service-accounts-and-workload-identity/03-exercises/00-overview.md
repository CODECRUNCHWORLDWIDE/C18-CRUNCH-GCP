# Week 2 — Exercises

Short, focused drills. Each one should take 30–60 minutes. Do them in order; later ones assume earlier ones. Run everything against your Week 1 `workloads/dev` project unless told otherwise.

## Index

1. **[Exercise 1 — A custom least-privilege role](./exercise-01-custom-least-privilege-role.md)** — write a custom IAM role with the minimum permission set for a stated job function (the "report publisher"), apply it with Terraform, and verify it is actually minimal with Policy Analyzer. (~50 min)
2. **[Exercise 2 — An IAM condition scoped by tag and time](./exercise-02-iam-condition-scoped-binding.tf)** — fill in the TODOs in a Terraform file that grants a binding only on resources carrying a tag, and only during a maintenance window. (~45 min)
3. **[Exercise 3 — Audit for the over-privileged service account](./exercise-03-audit-overprivileged-sa.py)** — a runnable Python tool that uses the Asset and Policy Analyzer APIs to find the SA with the widest blast radius in a project. (~50 min)

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Type the code yourself.** Do not copy-paste. Muscle memory is the entire point of these drills, and IAM mistakes come from copy-pasting bindings you didn't read.
- Apply it. See the effect. Read the error if it 403'd — the error message names the missing permission, which is half of least-privilege work.
- If you get stuck for more than 10 minutes, peek at the inline hints at the bottom of each file.
- **Every exercise ends with the "zero keys" check** from the README. If `gcloud iam service-accounts keys list --managed-by=user` prints a key, you reached for the wrong tool.
- Tear down what you create. Each exercise has a teardown block. Skipping it costs you money and leaves audit findings for future-you.

## Prerequisites for all three

```bash
# gcloud authenticated as YOU, not a key file:
gcloud auth login
gcloud auth application-default login

# Terraform / OpenTofu installed:
terraform version   # or: tofu version

# Python 3.11+ with the client libraries for exercise 3:
python3 -m venv .venv && source .venv/bin/activate
pip install google-cloud-asset google-cloud-iam google-auth
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c18-week-02` to compare.
