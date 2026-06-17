# Mini-Project — The Long-Lived GKE Standard Cluster

> Provision a **regional GKE Standard cluster** with a spot node pool, on the Week 03/05 VPC, via a reusable `gke` module added to your Week 04 module library. Run the FastAPI service on it with Workload Identity (no key file), an HPA on a custom requests-per-second metric, and a PodDisruptionBudget. This cluster is the **long-lived artifact** the syllabus promises: Weeks 10, 12, and 13 explicitly *extend* it rather than rebuild it. Build it like you are going to live in it for ten weeks, because you are. Ship it with a teardown gate that you run nightly and re-apply each session.

This is the most important mini-project in Phase 2. Up to now your mini-projects were disposable — build it, grade it, destroy it, never see it again. This one is different. The `gke` module you write this week is consumed by `envs/dev` and stays in your repo. Week 10 lands a BigQuery dataset that this cluster's services write to. Week 12 adds a spot **GPU** node pool to this cluster and runs a vLLM serving pod on it. Week 13 instruments every workload on this cluster with OpenTelemetry. If you build a throwaway here, you pay for it three times later. If you build a clean, parameterized, documented module here, the next three extensions are `module "gpu_pool" { ... }` and a clean plan.

**Estimated time:** ~12.5 hours (split across Thursday, Friday, Saturday in the suggested schedule).

---

## What you will build

A `gke` Terraform module in your Week 04 `modules/` library, consumed by `envs/dev`, that provisions:

1. A **regional** GKE Standard cluster (`crunch-gke`) in `us-central1`, on the Week 03 VPC `crunch-vpc` / subnet `crunch-us-central1`, using the `pods` and `services` secondary ranges. Regional control plane (99.95% SLA). Regular release channel. Workload Identity enabled (`workload_pool = PROJECT_ID.svc.id.goog`). Shielded nodes on. A private control-plane endpoint with your workstation's IP in the authorized-networks allowlist. A maintenance window in a low-traffic hour.
2. A **default node pool** (`e2-standard-2`, autoscale 1–3 per zone) for system workloads and the adapter, with `upgrade_settings { strategy=SURGE, max_surge=1, max_unavailable=0 }` and `workload_metadata_config { mode=GKE_METADATA }`.
3. A **spot node pool** (`e2-standard-4`, autoscale 0–6 per zone, `spot=true`, tainted `cloud.google.com/gke-spot`) for the application workload. Same surge config.
4. A **Google service account** (`crunch-fastapi`) with `roles/storage.objectViewer` on a project GCS bucket, bound to the Kubernetes service account `fastapi` via Workload Identity. No key file.

On that cluster you deploy (with `kubectl` / a thin Helm chart / kustomize — your choice, document it):

5. The **FastAPI service** (the Exercise 1/2 image) as a Deployment of 2–10 replicas on the spot pool, with the `POD_NAME` downward-API var, readiness/liveness probes, and resource requests.
6. A **PodDisruptionBudget** (`minAvailable: 50%`).
7. An **HPA v2** scaling on a custom requests-per-second metric (target 50 RPS/pod), via the Custom Metrics Stackdriver Adapter (the adapter authenticates via its own Workload Identity binding).
8. A **VPA in recommendation mode (`updateMode: Off`)** on the same Deployment — not to act, but to produce a CPU/memory recommendation you read and compare against your hand-set requests. (Running VPA-`Auto` and HPA-on-CPU together is a known foot-gun; here VPA is advisory only and the HPA scales on RPS, so they coexist.)

You ship **one repository state**: your Week 04 repo, now with a `modules/gke/` directory and `envs/dev` calling it, plus a `k8s/` directory with the application manifests and a `MINIPROJECT.md` writeup.

---

## Repository layout (extends Week 04)

```
infra/
  modules/
    org-bootstrap/        # from Week 01/04
    vpc/                  # from Week 03/04
    iam-baseline/         # from Week 04
    compute/              # from Week 05
    gke/                  # <-- YOU BUILD THIS WEEK
      main.tf             #   google_container_cluster + 2 node pools
      variables.tf        #   project_id, region, network, subnetwork, ranges,
                          #   authorized_networks, node machine types, spot bounds
      outputs.tf          #   cluster_name, endpoint, ca_certificate, location,
                          #   fastapi_gsa_email
      versions.tf         #   provider + version pins
      workload_identity.tf#   GSA + objectViewer binding + WI binding
      README.md           #   module docs: inputs, outputs, an example call
  envs/
    dev/
      gke.tf              # module "gke" { source = "../../modules/gke" ... }
k8s/
  deployment.yaml         # FastAPI Deployment + Service (ClusterIP)
  pdb.yaml                # minAvailable: 50%
  hpa.yaml                # autoscaling/v2 on custom RPS metric
  vpa.yaml                # VerticalPodAutoscaler updateMode: Off
  serviceaccount.yaml     # KSA `fastapi`, annotated with the GSA
MINIPROJECT.md            # the writeup + the teardown evidence
```

---

## Rules

- **You may** reuse everything from the exercises and the challenge: the image, the manifests, the Workload Identity bind script, the surge node pool, the adapter install. The mini-project is the *productionized, modularized* version of that work.
- **You may NOT** create the cluster with `gcloud container clusters create` by hand and "write the Terraform later." It goes through the module, through `envs/dev`, with a `terraform plan` you read before you `apply`. That is the Week 04 discipline and it is graded here.
- **You may NOT** mount a service-account key file into any pod. A key file is an automatic fail of the security criterion. Workload Identity or nothing.
- The cluster is **Standard**, not Autopilot. The syllabus is explicit: this long-lived cluster is the one Weeks 12 (GPU spot pool) and 13 (per-node OTel agent) extend, and both extensions need node-pool control that Autopilot does not give. You proved you can run Autopilot in the exercises; the *artifact* is Standard for a reason — articulate that reason in the writeup.
- Target `terraform` >= 1.7, `google` provider ~> 6.0. `<TreatWarningsAsErrors>`-equivalent discipline: a `terraform validate` and a clean `terraform plan` with no drift before you call it done.
- Region `us-central1`. Everything pinned there to stay in the free-trial region and keep cost down.

---

## Acceptance criteria

The grading rubric. Each box maps to a deliverable.

### Module quality (25%)

- [ ] `modules/gke/` has `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, and a `README.md` documenting every input and output with types and an example call.
- [ ] Every `variable` that can have a bad value has a `validation` block (e.g., `machine_type` non-empty, spot `max_node_count >= min_node_count`).
- [ ] The module takes the VPC network, subnetwork, and the two secondary range names as **inputs** (it does not hard-code the Week 03 names) and is consumed by `envs/dev/gke.tf` with the real values.
- [ ] `terraform plan` against `envs/dev` is clean (no drift) after `apply`. Paste the `No changes.` line into `MINIPROJECT.md`.

### Cluster correctness (25%)

- [ ] The cluster is **regional** (location is `us-central1`, not a zone). `gcloud container clusters describe crunch-gke --region us-central1 --format='value(location)'` returns the region.
- [ ] Two node pools exist: a default `e2-standard-2` pool and a **spot** `e2-standard-4` pool (`spot=true`, tainted).
- [ ] Both node pools have `upgrade_settings { strategy=SURGE, max_surge=1, max_unavailable=0 }`.
- [ ] Workload Identity is enabled at the cluster (`workload_pool`) and on both node pools (`workload_metadata_config = GKE_METADATA`).
- [ ] The control-plane endpoint is private with your workstation IP in the authorized-networks list; a `kubectl get nodes` works from your machine and would fail from an un-allowlisted IP.

### Workload correctness (30%)

- [ ] The FastAPI Deployment runs 2–10 replicas on the **spot** pool (tolerates the spot taint). `kubectl get pod -o wide` shows them on spot nodes.
- [ ] Workload Identity works: `/whoami` reports the `crunch-fastapi` GSA, or the pod reads the GCS object. `kubectl exec` confirms no key file and no `GOOGLE_APPLICATION_CREDENTIALS`.
- [ ] A `minAvailable: 50%` PDB protects the Deployment; `kubectl get pdb` shows it tracking the replica count.
- [ ] The HPA scales on the custom RPS metric (not CPU). Under a `hey` load that pushes past 50 RPS/pod, replicas increase; after load, they decrease. `kubectl describe hpa` shows the custom metric driving it.
- [ ] A VPA in `updateMode: Off` produces a recommendation; you record it in `MINIPROJECT.md` and compare it to your hand-set `requests`, noting whether you would adjust them.

### Writeup & cost (10%)

- [ ] `MINIPROJECT.md` includes: the Autopilot-vs-Standard justification for choosing Standard here (tie it to the Week 12/13 extensions); the clean-plan evidence; the VPA recommendation vs. your requests; and a **monthly cost estimate** at steady state (2 replicas on spot) and a note on what each later week will add to that bill.

### Teardown gate (pass/fail — you cannot pass the week without this)

- [ ] You demonstrate the **nightly teardown / morning re-apply** cycle: delete any `Service type=LoadBalancer` first (none here if you used ClusterIP, but show the habit), then `terraform destroy`, then `terraform apply` the next session and confirm the cluster comes back identically.
- [ ] After `terraform destroy`: `gcloud container clusters list` is empty of `crunch-gke`; `gcloud compute forwarding-rules list` and `gcloud compute disks list` show no orphans from this cluster.

> **The teardown gate is the most-failed criterion in this course.** A GKE Standard regional cluster with two node pools left running overnight bills real money, and a `Service type=LoadBalancer` you forgot to delete before `terraform destroy` leaves a forwarding rule that Terraform does not own and will not clean up — it bills until you delete it by hand. Make the teardown a reflex now. The capstone grader runs `terraform destroy` on your system and watches it go clean; this week is where that reflex is built.

---

## How the compounding works (read before you start)

The syllabus says the mini-projects compound and that Weeks 10, 12, and 13 extend *this* cluster. Concretely, so you build with the right seams:

- **Week 10 (BigQuery deep)** lands a partitioned-clustered BigQuery dataset and the FastAPI service writes events to it. Your `gke` module's `fastapi` GSA will gain `roles/bigquery.dataEditor` on that dataset — so make the GSA and its bindings a clean, extendable part of the module, not a one-off `gcloud` command.
- **Week 12 (Vertex AI / serving inference)** adds a **spot GPU node pool** to this cluster and runs a vLLM serving pod with a Gemini fallback. Your module should make adding a third node pool a matter of one more `google_container_node_pool` block driven by a variable — so parameterize the node-pool config (machine type, accelerators, bounds) rather than hard-coding two pools.
- **Week 13 (OpenTelemetry)** instruments every workload on this cluster with OTel, exporting traces/metrics/logs to Cloud Trace/Monitoring/Logging, and defines an SLO per service. The cluster you build now is the one those SLOs are measured against — so keep the FastAPI service's readiness probe honest and its labels stable; Week 13 selects on them.

Build the module so each of those is an *addition*, not a *rewrite*. That is the entire reason this mini-project is Standard and modular rather than a quick Autopilot cluster: it has to grow.

---

## Suggested order of work

1. **Thursday (~1h, alongside the upgrade exercise):** scaffold `modules/gke/` — `variables.tf`, `versions.tf`, the `google_container_cluster` resource with WI + regional + private endpoint + maintenance window. Wire `envs/dev/gke.tf`. `terraform plan` (do not apply yet) and read it.
2. **Friday (~4h):** add the two node pools (default + spot) with surge config. `apply`. `get-credentials`. Deploy the FastAPI Deployment + Service + PDB onto the spot pool. Verify it serves. Add `workload_identity.tf` (the GSA + bindings) and the annotated KSA; verify `/whoami` and `/read`.
3. **Saturday (~3.5h):** install the Custom Metrics Stackdriver Adapter (with its WI binding), wire the HPA on the RPS metric, load-test it scaling up and down. Add the VPA in `Off` mode and read its recommendation. Write `MINIPROJECT.md`.
4. **Sunday (~1h):** the teardown/re-apply cycle and the cost section. Prove clean destroy and clean re-apply. Submit.

---

## What "done" looks like

```
$ terraform -chdir=envs/dev apply
Apply complete! Resources: 6 added, 0 changed, 0 destroyed.

$ kubectl get pods -o wide
NAME                       READY   STATUS    NODE
fastapi-6c8d...-2k4x9      1/1     Running   gke-crunch-gke-spot-pool-...   <- on spot
fastapi-6c8d...-8j7w2      1/1     Running   gke-crunch-gke-spot-pool-...

$ kubectl get hpa fastapi-hpa
NAME          REFERENCE            TARGETS              MINPODS   MAXPODS   REPLICAS
fastapi-hpa   Deployment/fastapi   12/50 (req/s/pod)    2         10        2

$ kubectl get pdb fastapi-pdb
NAME          MIN AVAILABLE   ALLOWED DISRUPTIONS
fastapi-pdb   50%             1

$ curl .../whoami
{"service_account": "crunch-fastapi@PROJECT_ID.iam.gserviceaccount.com", ...}

$ terraform -chdir=envs/dev destroy   # nightly
Destroy complete! Resources: 6 destroyed.
```

That is a long-lived, modular, Workload-Identity-secured, autoscaled, PDB-protected GKE Standard cluster you can tear down at night and bring back in the morning — and that the next three Phase-3/4 weeks build directly on top of. Ship it.
