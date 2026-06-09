# Week 6 — Exercises

Three focused drills that build the muscle the mini-project assumes. Do them in order; each one assumes the last. Exercises 1 and 2 run against an Autopilot cluster (cheap, fast to create); Exercise 3 needs a Standard cluster because you cannot run a manual node-pool upgrade on Autopilot.

## Index

1. **[Exercise 1 — Deploy FastAPI to Autopilot with a PodDisruptionBudget](exercise-01-fastapi-on-autopilot-with-a-pdb.md)** — containerize the provided FastAPI service, push it to Artifact Registry, deploy it to an Autopilot cluster as a 3-replica Deployment, protect it with a PDB, and prove the PDB blocks a too-aggressive `kubectl drain`. (~75 min)
2. **[Exercise 2 — Workload Identity reads a GCS object with no key file](exercise-02-workload-identity.py)** — a runnable FastAPI endpoint plus the manifests and bind script that let a pod read a GCS object using Application Default Credentials and a federated identity. Verify with `kubectl exec` that no key file exists anywhere. (~75 min)
3. **[Exercise 3 — In-place minor-version upgrade on Standard with surge config](exercise-03-surge-upgrade.tf)** — a complete Standard cluster + node pool in Terraform with surge upgrade settings, the upgrade procedure, and a `hey`-based load generator that proves zero traffic loss through a real node-pool upgrade. (~90 min)

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Type the commands and manifests yourself.** Do not copy-paste blindly. The point of these drills is that `kubectl` and `gcloud container` become muscle memory.
- Every exercise ends with an **explicit teardown step**. Run it. A GKE cluster left running overnight is the single most common surprise-bill event in this course. `gcloud container clusters delete` is not optional.
- If `kubectl apply` is rejected by GKE Warden on Autopilot, read the rejection message — it names the exact constraint you violated. That is Autopilot doing its job (Lecture 1, §1.5).
- Exercise 2's Python file is a *real, runnable* FastAPI app. You can run it locally against a key file to test the logic, then deploy it to GKE where the key file disappears and Workload Identity takes over. The whole point is that the *application code does not change* between those two — ADC handles it.

## Cost note

- Exercises 1 and 2 on a regional Autopilot cluster running 3 small pods for an hour cost well under \$1 — but the \$0.10/hr cluster management fee accrues whether or not pods are scheduled. **Delete the cluster when you finish each session.**
- Exercise 3 on a 3-node regional `e2-standard-2` Standard cluster costs roughly \$0.20/hr in node compute plus the cluster fee. The upgrade itself adds one surge node for ~10 minutes. Budget under \$1 if you tear down promptly.
- There are no checked-in solutions. The course is open source — solutions live in forks. After you finish, search GitHub for `c18-week-06` to compare.
