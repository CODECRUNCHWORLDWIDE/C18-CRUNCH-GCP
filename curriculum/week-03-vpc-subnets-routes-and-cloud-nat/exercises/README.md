# Week 3 — Exercises

Three exercises, in order. They build on each other: Exercise 1 stands up the VPC and proves you didn't lock yourself out, Exercise 2 turns on Private Google Access on that same VPC and verifies it from a VM, and Exercise 3 is the diagnostic skill you'll use for the rest of the course — *"why can't my GKE pod reach BigQuery?"*

Do them in order. Each ends with a `terraform destroy` (or `gcloud ... delete`) step — run it. A forgotten Cloud NAT is a few dollars a week of nothing; the week's teardown discipline starts here.

| # | File | What you practice | Est. time |
|---|------|-------------------|-----------|
| 1 | [exercise-01-firewall-without-lockout.md](./exercise-01-firewall-without-lockout.md) | Write VPC firewall rules for a stated service — allow exactly what's needed — without severing your own IAP/SSH path. Validate every rule with a Connectivity Test before you trust it. | 75 min |
| 2 | [exercise-02-private-google-access.tf](./exercise-02-private-google-access.tf) | Configure Private Google Access so a no-external-IP subnet reaches `*.googleapis.com` over the private VIP. Verify with `dig` and `traceroute` from a VM. Runnable Terraform with TODOs and a solution block. | 60 min |
| 3 | [exercise-03-diagnose-pod-to-bigquery.py](./exercise-03-diagnose-pod-to-bigquery.py) | Build a diagnostic decision-tree tool that distinguishes Private Google Access from Private Service Connect failures for the "GKE pod can't reach BigQuery" class of incident. Runnable Python. | 60 min |

## Before you start

- You have the Lecture 1 VPC concepts cold: global VPC, custom-mode, the two implied firewall rules, the four lockout patterns, Cloud NAT, PGA.
- `gcloud`, `terraform` (≥ 1.7) or `tofu`, `dig`, `traceroute`, and Python 3.11+ are installed. Verify with `gcloud --version`, `terraform version`, `dig -v`, `python3 --version`.
- Your credentials resolve without a key file: `gcloud auth application-default login` or Workload Identity Federation from Week 02.
- Billing budgets are armed (Week 01). These exercises cost cents if you tear down; dollars if you forget.

## The "no lockout" rule applies to every exercise

If a `terraform apply` succeeds but you cannot reach your own bastion through IAP afterward, you locked yourself out and the exercise is **not** done — regardless of what the plan said. Run the Connectivity Test. "I think it's reachable" is not an answer.

## Solutions

Exercise 1 ships its solution inline (it's a guided exercise). Exercises 2 and 3 ship a complete solution block at the bottom of the file behind a "peek only if stuck" marker — write your own first. The point is the reps, not the copy-paste.
