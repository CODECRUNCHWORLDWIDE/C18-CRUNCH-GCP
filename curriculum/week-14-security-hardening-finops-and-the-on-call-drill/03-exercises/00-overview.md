# Week 14 — Exercises

Three focused drills. The first two are about *closing a control and proving it denies the forbidden action*; the third is about *finding the money*. Do them in order — Exercise 2 assumes the Org Policy bundle from Exercise 1 is applied, and the mini-project assumes all three.

## Index

1. **[Exercise 1 — Org Policy bundle + verify](./exercise-01-org-policy-bundle-and-verify.md)** — Apply an Organization Policy bundle (restrict public IPs, enforce CMEK, restrict resource locations) in Terraform, then *verify enforcement* by attempting each forbidden action and confirming the deny. (~75 min)
2. **[Exercise 2 — Binary Authorization with a Cloud Build attestor](./exercise-02-binary-authorization-cloud-build-attestor.py)** — Wire Binary Authorization on the GKE deploy path with an attestor signed by Cloud Build, then prove a signed image admits and an unsigned image is denied. Driven by a Python orchestrator over `gcloud`/`kubectl`. (~80 min)
3. **[Exercise 3 — Billing-export FinOps analysis](./exercise-03-billing-export-finops.sql)** — Query a billing export in BigQuery to find the top three line items by effective cost and quantify a committed-use saving. Runnable SQL with an embedded synthetic-data path so it works even if your export has not populated yet. (~60 min)

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Type the commands yourself.** Do not copy-paste blindly — the verification steps are the point, and they only teach you if you *watch the deny happen*.
- Every exercise ends in a **"verify the deny"** step (or, for Exercise 3, a number you can defend). A control you have not seen reject something is not done. A FinOps number you cannot show the query for is not done.
- The hardening exercises are free. Exercise 2 builds and pushes a tiny image (Artifact Registry storage is pennies). None of these three needs the paid failover — that is the challenge and the mini-project.
- **Tear down** anything you create that costs money the same day. The default network probe VMs, the test buckets, the test images — delete them when the verification passes.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c18-week-14` to compare.

## Cost note

Exercise 1: free (Org Policy, KMS key creation is free; key *operations* are sub-cent). Exercise 2: pennies (Artifact Registry storage + one tiny Cloud Build run; the GKE cluster is already running from Week 06). Exercise 3: free if your billing export exists (querying it scans a small table); the embedded synthetic path is free. Confirm `bq` query bytes-billed before running large scans.
