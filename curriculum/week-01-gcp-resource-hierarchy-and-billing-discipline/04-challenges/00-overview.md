# Week 1 — Challenges

The exercises drill the basics. **The challenge stretches you.** It takes 2–4 hours and produces something you can put on your portfolio — and, more importantly, it produces the literal foundation that Weeks 02, 03, and 04 build directly on top of.

## Index

1. **[Challenge 1 — Terraform landing zone, budgets armed first](./challenge-01-terraform-landing-zone.md)** — provision a three-folder (`bootstrap/`, `shared/`, `workloads/`), five-project landing zone entirely in Terraform, with billing budgets armed *before* any compute primitive can be created. Validate the hierarchy with `gcloud asset` and prove a budget alert fires. (~3 h)

## Why this challenge matters

This is not a throwaway. The folder/project tree you stand up here is the **same tree** the mini-project formalizes into a reusable module, and the same tree Week 02 (IAM baseline) and Week 03 (VPC layer) extend. The whole point of the C18 ordering is that you never start from a blank project again after this week — you start from a landing zone.

Do not delete what you build until the explicit teardown gate at the end of the mini-project. If you tear it down early, you will be rebuilding it on Monday.

The challenge has no checked-in solution — only acceptance criteria. That is deliberate. A landing zone you can produce against a spec, without a reference to copy, is the skill being assessed.
