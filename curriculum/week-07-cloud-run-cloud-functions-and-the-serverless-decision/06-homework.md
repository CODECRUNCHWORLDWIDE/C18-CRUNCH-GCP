# Week 7 Homework

Five problems that revisit the week's topics. The full set should take about **4 hours**. Work in your Week 7 Git repository so each problem produces at least one commit you can point to later. Where a problem says "tear it down," do it — Cloud SQL bills per hour.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

---

## Problem 1 — Write the cost-curve model as a script

**Problem statement.** Implement the Lecture 1 cost model as a small Python script `cost_model.py` that, given a request shape and a GKE footprint, prints the Cloud Run monthly cost, the GKE monthly cost, and the crossover RPS. Use the 2026 prices from Lecture 1. Model Cloud Run with the **active-instance-seconds** method (not request-seconds). Sweep RPS from 1 to 80 and print the crossover for (a) a dedicated GKE cluster and (b) a shared cluster where the control-plane share is \$7.30 and the service bin-packs onto existing spot nodes.

**Acceptance criteria.**

- `cost_model.py` takes parameters: `rps`, `latency_s`, `vcpu`, `mem_gib`, `concurrency`, `busy_hours_per_day`, plus GKE node type/count/spot and control-plane share.
- It prints Cloud Run and GKE monthly cost and the crossover RPS for both the dedicated and shared cases.
- The crossover for the 100 ms / 1 vCPU / concurrency-80 shape against a dedicated ~\$102/month cluster lands in the 35–42 RPS range.
- Re-running with a CPU-bound shape (concurrency 8) moves the crossover well below 20 RPS, and the script shows it.
- Committed, with a 100-word `notes/cost-model.md` explaining why the active-instance-seconds method is correct.

**Hint.** Active-instance-seconds for a saturated single instance is just `instances × busy_seconds`. Don't multiply by request count for the CPU/mem terms; only the per-request fee is per-request.

**Estimated time.** 60 minutes.

---

## Problem 2 — Compute and defend a `min-instances` decision

**Problem statement.** Pick a real (or realistic) service and write a `notes/min-instances-decision.md` that applies the Lecture 2 break-even. State: the cold-start penalty (measure it if you have the service from this week, otherwise estimate from the lecture's per-language ranges), the estimated `N_cold` (monthly cold-served requests) from a stated traffic shape, whether it's a Flavor A (SLO-budget) or Flavor B (business-value) case, the `c_cold` you assign, and the floor you'd ship. Show the arithmetic.

**Acceptance criteria.**

- The note names a cold-start penalty, an `N_cold`, a classification (Flavor A or B), and a `c_cold` (or an error budget for Flavor A).
- It applies `N_cold × c_cold > idle_cost` (or the error-budget comparison) and states the recommended floor with the arithmetic shown.
- It picks the floor from the **burst instance count** (`burst_rps × latency / concurrency`), not a round number, and explains the choice.
- It includes an exit trigger ("we revisit the floor if …").

**Hint.** If you ran the challenge, use its measured cold-start number. Otherwise: lean Go ~150–400 ms, Python+uvicorn ~0.8–2 s, Python+model 3–15 s.

**Estimated time.** 45 minutes.

---

## Problem 3 — Prove the database has no public door

**Problem statement.** Using Terraform, stand up a Cloud SQL Postgres instance with `ipv4_enabled = false` and Private Service Connect enabled, plus a PSC endpoint in your VPC. Do **not** deploy a service. Then write `notes/private-db-proof.md` with the command output proving (a) the instance has no public IP, (b) a PSC endpoint exists in your VPC, and (c) you cannot reach the instance from your laptop (no public address to even attempt). Tear it down.

**Acceptance criteria.**

- `gcloud sql instances describe` output in the note shows `ipv4Enabled: false`.
- A `gcloud compute forwarding-rules describe` (or `list`) shows the PSC endpoint pointing at the instance's service attachment.
- The note explains in 3–4 sentences why this beats public-IP + Auth Proxy and why it beats legacy private services access.
- Teardown confirmed (`gcloud sql instances list` empty) and the confirmation pasted in the note.

**Hint.** `pscServiceAttachmentLink` from `gcloud sql instances describe` is the target for the forwarding rule. Reserve an internal address in your subnet first.

**Estimated time.** 60 minutes.

---

## Problem 4 — Trace the Eventarc IAM, end to end

**Problem statement.** Without deploying anything, write `notes/eventarc-iam.md` that traces every IAM grant required for a `google.cloud.storage.object.v1.finalized` → Eventarc → Cloud Run **job** path (via a launcher service). For each grant, name the **principal**, the **role**, the **resource**, and one sentence on *why* it's needed. There are at least five grants. Then draw the event path as a sequence (GCS finalize → … → job execution).

**Acceptance criteria.**

- The note lists at least five grants: GCS service agent `pubsub.publisher`; trigger SA `eventarc.eventReceiver`; trigger SA `run.invoker` on the launcher; launcher SA job-execution rights (`run.developer` or custom); launcher SA `iam.serviceAccountUser` on the job's SA.
- Each grant has principal / role / resource / why.
- A sequence diagram (ASCII or Mermaid) shows the GCS → Pub/Sub (managed transport) → launcher → Admin API → job path.
- It explains in one sentence why the job needs the launcher hop (no `$PORT`).

**Hint.** Exercise 3's `iam.tf` has all five grants commented. This problem is "explain it back without copying the file verbatim."

**Estimated time.** 30 minutes.

---

## Problem 5 — Cloud Functions gen2 is a Cloud Run service: prove it

**Problem statement.** Deploy a trivial Cloud Functions **gen2** HTTP function (any language; Python is fine — "hello"). Then find the underlying **Cloud Run service** it created, and write `notes/gen2-is-cloud-run.md` documenting: the `gcloud functions deploy --gen2` command you ran, the Cloud Run service that appears (`gcloud run services list`), the fact that the function's URL and the service's URL serve the same handler, and one sentence on when (if ever) you'd reach for a gen2 function over a hand-built Cloud Run service in 2026. Tear it down.

**Acceptance criteria.**

- The note shows the `gcloud functions deploy ... --gen2` command and the resulting `gcloud run services list` output proving a Cloud Run service was created.
- It confirms the function URL and the underlying service respond identically.
- It states the 2026 take: gen2 functions are mostly an ergonomic convenience over Cloud Run; new work often goes straight to Cloud Run + Eventarc unless the function's deploy/trigger ergonomics are worth it.
- Teardown confirmed and pasted.

**Hint.** `gcloud functions deploy hello --gen2 --runtime=python312 --trigger-http --allow-unauthenticated --entry-point=hello --region=us-central1`. Then `gcloud run services list` — you'll see a service named after the function.

**Estimated time.** 45 minutes.

---

## Submission

Push the entire `notes/` directory and any Terraform/scripts to your Week 7 Git repository. The instructor reviews by:

1. Reading each note in `notes/`.
2. Re-running `cost_model.py` and checking the crossover numbers reproduce.
3. Spot-checking that any infrastructure you stood up was torn down (the teardown confirmations are real).
4. Cross-checking the cited behaviors (no public IP, gen2-is-Cloud-Run) against a quick live re-deploy.

A submission whose notes are present, whose script reproduces, and whose teardowns are confirmed is a pass. The most common review-fail is "the note claims no public IP but the instance still exists with one" — verify before submitting.

## Rubric

| Problem | Weight | What earns full marks |
|---|---|---|
| 1 — cost-curve script | 25% | Active-instance-seconds method correct; crossovers in range for both cases; CPU-bound shift shown. |
| 2 — min-instances decision | 20% | Break-even arithmetic shown; correct flavor; floor picked from burst count; exit trigger. |
| 3 — private DB proof | 25% | `ipv4Enabled: false` proven; PSC endpoint shown; rationale vs. alternatives; teardown confirmed. |
| 4 — Eventarc IAM trace | 15% | Five+ grants with principal/role/resource/why; sequence diagram; launcher-hop explained. |
| 5 — gen2 is Cloud Run | 15% | Underlying Cloud Run service shown; identical handler confirmed; 2026 take; teardown confirmed. |

If anything is unclear, post the question in the Week 7 channel before the homework deadline.

---

**References**

- Cloud Run pricing & autoscaling: <https://cloud.google.com/run/pricing> · <https://cloud.google.com/run/docs/about-instance-autoscaling>
- Cloud Run minimum instances: <https://cloud.google.com/run/docs/configuring/min-instances>
- Cloud SQL — Private Service Connect: <https://cloud.google.com/sql/docs/postgres/configure-private-service-connect>
- Cloud SQL — IAM database authentication: <https://cloud.google.com/sql/docs/postgres/iam-authentication>
- Eventarc — Cloud Storage trigger: <https://cloud.google.com/eventarc/docs/run/create-trigger-storage-gcloud>
- Cloud Functions gen2 overview: <https://cloud.google.com/functions/docs/concepts/version-comparison>
