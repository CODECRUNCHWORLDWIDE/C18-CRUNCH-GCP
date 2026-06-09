# Week 4 — Exercises

Three exercises, in order. Each is a skill drill, not capstone work — you build one muscle per exercise, and the challenge and mini-project assemble them. Do them in order: Exercise 2 assumes the remote backend from Exercise 1, and Exercise 3 assumes the module structure from Exercise 2.

Budget ~6 hours across the three. Run every `apply` early in a session, never in the last fifteen minutes — a half-applied Terraform run is the worst place to leave a cloud overnight. Tear down what you stand up.

| # | File | What you build | Time |
|---|------|----------------|------|
| 1 | [exercise-01-gcs-remote-backend-with-locking.md](./exercise-01-gcs-remote-backend-with-locking.md) | Bootstrap a GCS state bucket and migrate a local-state root module into it. Prove the lock holds against a concurrent apply by watching the 412 precondition error. | ~90 min |
| 2 | [exercise-02-for-each-subnet-module.tf](./exercise-02-for-each-subnet-module.tf) | Refactor three duplicated `google_compute_subnetwork` blocks into one `for_each`-driven module, then consume it from `envs/dev` and `envs/prod` with different CIDRs. Prove the addresses are stable. | ~75 min |
| 3 | [exercise-03-cloudbuild-pr-plan-check.py](./exercise-03-cloudbuild-pr-plan-check.py) | A Python script (run from Cloud Build) that runs `terraform plan`, parses the machine-readable JSON, and posts the human-readable plan as a comment on the pull request via the GitHub API. | ~90 min |

## Prerequisites for all three

- `terraform` 1.9+ (or `tofu` 1.8+) on your PATH. `terraform version`.
- `gcloud` authenticated via `gcloud auth application-default login`, as a principal that can create GCS buckets and Compute networks in your course project.
- The `google` provider `~> 6.0`. Exercise 1 pins it; the rest inherit.
- Exercise 2 also needs Terragrunt 0.60+ (`terragrunt --version`) for the optional DRY variant; a plain-Terraform path is provided.
- Exercise 3 needs a GitHub repository connected to Cloud Build (2nd-gen GitHub host) and a `GITHUB_TOKEN` available to the build. The script also runs locally for testing against a fake plan.

## A note on cost

Everything here is nearly free: a GCS state bucket holds a few KB, a VPC and three subnets are free, a Cloud Build run inside the free tier is free. The only way to spend money is to forget to `terraform destroy` and leave something billing. The teardown steps are part of each exercise, not optional.

## Solutions

There is no separate `SOLUTIONS.md` for this week — Exercises 2 and 3 are runnable files with the full solution inline (Exercise 2's solution is at the bottom of the `.tf` file under a clearly marked fence; Exercise 3 is a complete, working script). Exercise 1 is fully guided with every command and expected output shown. The challenge and mini-project are where you work without a net.
