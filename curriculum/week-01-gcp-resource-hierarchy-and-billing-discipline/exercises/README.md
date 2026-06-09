# Week 1 — Exercises

Three focused drills. The first is **mandatory and gating** — you do not create compute in this course until you have armed a budget with Slack alerts. The other two build the muscle memory you will rely on for the next 14 weeks.

## Index

1. **[Exercise 1 — Arm the budget first](exercise-01-arm-the-budget-first.md)** — set a hard budget with 50/90/100% threshold alerts wired to Slack via Pub/Sub and a Cloud Function, *before* you provision any resource. **Mandatory.** (~75 min)
2. **[Exercise 2 — Map the org chart](exercise-02-map-the-org-chart.py)** — model a sample org chart as a folder/project tree in Python, emit it as a diagram and a justification table, and defend every boundary placement. (~45 min)
3. **[Exercise 3 — gcloud configurations](exercise-03-gcloud-configurations.py)** — drive three named `gcloud` configurations (`dev`/`prod`/`admin`) and switch between them safely, with a guard that refuses a destructive command in the wrong context. (~40 min)

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Type the commands yourself.** Do not copy-paste blindly. The point of Week 1 is reflexes — `gcloud config configurations activate prod` should become as automatic as `cd`.
- Run it. Read the output. If `gcloud` errors, read the error: GCP errors are unusually good and almost always name the missing permission or the unlinked billing account.
- If you get stuck for more than 10 minutes, peek at the hints at the bottom of each file.
- Every exercise that touches a real project must end with the **budget-armed marker** visible:
  ```
  budget: armed · 3 thresholds (50/90/100%) · notify: pubsub://billing-alerts · channel: #gcp-cost
  ```
  If you cannot show that line, you are not done, and you may not move on to compute in later weeks.

## A note on cost

Everything here fits inside the \$300 free trial and the always-free tier. The Pub/Sub topic and the single Cloud Function are free at this volume. The only deliberate spend is an *optional* ~\$1 charge in the challenge to prove a real alert fires — and Exercise 1 shows you how to simulate the threshold with the Budget API for free instead.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c18-week-01` to compare approaches.
