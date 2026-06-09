# Week 4 — Challenges

One challenge this week, and it is the load-bearing one. No solution is provided — only acceptance criteria. The challenge is deliberately the same shape as the mini-project, because the challenge *is* the first build of the artifact the mini-project then polishes to portfolio grade. Do the challenge Thursday; the mini-project (Friday–Sunday) hardens what you built here into the canonical foundation the rest of the course consumes.

| # | File | What you prove | Time |
|---|------|----------------|------|
| 1 | [challenge-01-refactor-weeks-01-03-into-a-module-library.md](./challenge-01-refactor-weeks-01-03-into-a-module-library.md) | You can take three weeks of ad-hoc HCL and refactor it into `org-bootstrap`, `vpc`, and `iam-baseline` modules consumed by `envs/dev` and `envs/prod` via Terragrunt, with remote state and locking, and prove **zero drift** with a clean plan against both environments. | 2.5–3.5 h |

## How the challenge relates to the mini-project

- **Challenge (Thursday):** get the module library *working*. Three modules, two environments, remote state, a clean plan. Rough edges allowed.
- **Mini-project (Fri–Sun):** make it *portfolio-grade*. Module READMEs, input validation on every variable, the Cloud Build PR plan check wired and demonstrated on a real PR, a teardown gate, and a writeup. This is one of the three artifacts the syllabus names as belonging on your portfolio.

If you finish the challenge with time to spare, do not start new work — start the mini-project's polish pass. They are the same codebase at two levels of finish.
