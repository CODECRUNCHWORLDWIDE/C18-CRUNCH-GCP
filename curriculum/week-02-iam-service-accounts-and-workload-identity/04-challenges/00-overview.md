# Week 2 — Challenges

One stretch problem this week. No solution is provided — only acceptance criteria. The challenge is harder and more open-ended than the exercises, and it is the practical core of the syllabus: ending the keyfile era for your own CI.

## Index

1. **[Challenge 1 — Keyless deploys with WIF, then a second provider](./challenge-01-wif-github-actions-and-second-provider.md)** — replace a service-account key file with Workload Identity Federation from GitHub Actions so the repo holds zero long-lived keys and deploys are OIDC-only. Then extend WIF to one additional provider: GitLab CI or a non-GCP Kubernetes cluster. (~3–4 hours)

## How to work the challenge

- There is no step-by-step. You have the lecture notes (§2.5–2.7), the exercises, and the official docs in `resources.md`. Use them.
- The acceptance criteria are the contract. When every box is ticked, you're done.
- **Prove the negative.** A keyless setup that *works* is half the grade; a keyless setup where you've *demonstrated that a foreign repo / branch / namespace is rejected* is the whole grade. Security is the absence of a path, and you must show the path is absent.
- Tear down at the end. The WIF pool and providers cost nothing, but leave them only if they're part of your ongoing landing zone — otherwise destroy.
