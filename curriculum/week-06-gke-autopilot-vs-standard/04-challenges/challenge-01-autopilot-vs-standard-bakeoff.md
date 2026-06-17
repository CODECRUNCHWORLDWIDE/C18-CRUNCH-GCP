# Challenge 1 — Autopilot vs. Standard-with-spot: cold-start, scale-out, and monthly cost

> **Estimated time:** ~4 hours. Worth more than its time-cost suggests: this is the exact "defend the platform choice with a number" deliverable a staff engineer asks for in a review, and it is one of the artifacts the syllabus names for your portfolio.

You will deploy the **same** Python FastAPI service from the exercises to two clusters — (a) GKE **Autopilot** and (b) GKE **Standard with a spot node pool** — wire **Workload Identity**, an **HPA on a custom requests-per-second metric**, and a **PodDisruptionBudget** on both, and then **measure**: cold-start latency, scale-out time under load, and projected monthly cost. The deliverable is a short writeup ending in a one-paragraph recommendation with a dollar figure. Both halves of the syllabus Week-6 lab live here.

## What you build

Two clusters, identical workload, instrumented to compare:

| | Cluster A | Cluster B |
|---|---|---|
| Mode | Autopilot | Standard |
| Node plane | Google-managed | One spot node pool (`e2-standard-4`, autoscale 0–6) |
| Workload Identity | on by default | enabled at cluster + node pool |
| Workload | `fastapi` Deployment, 2–10 replicas | same |
| HPA | on custom RPS metric, target 50 RPS/pod | same |
| PDB | `minAvailable: 50%` | same |

## Part 1 — Deploy to both (reuse the exercises)

Use the Exercise 1 image and manifests on both clusters. Create them on the Week 3 VPC subnet with the `pods`/`services` secondary ranges. The PDB this time is percentage-based (`minAvailable: 50%`) so it tracks an autoscaled replica count without editing.

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fastapi-pdb
spec:
  minAvailable: 50%
  selector:
    matchLabels:
      app: fastapi
```

The Standard spot node pool (HCL fragment — promote into your module or run flat):

```hcl
resource "google_container_node_pool" "spot" {
  name     = "spot-pool"
  cluster  = google_container_cluster.standard.name
  location = var.region

  autoscaling {
    min_node_count = 0
    max_node_count = 6 # per zone
  }

  upgrade_settings {
    strategy        = "SURGE"
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    machine_type = "e2-standard-4"
    spot         = true # 60–91% off; reclaimable with ~30s notice
    disk_size_gb = 50
    disk_type    = "pd-balanced"

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # GKE auto-applies these to spot nodes; declaring them documents intent and
    # lets you target the pool from a workload that tolerates preemption.
    labels = { "cloud.google.com/gke-spot" = "true" }
    taint {
      key    = "cloud.google.com/gke-spot"
      value  = "true"
      effect = "NO_SCHEDULE"
    }
  }
}
```

Your `fastapi` pods must **tolerate** the spot taint to land on the spot pool:

```yaml
      tolerations:
        - key: "cloud.google.com/gke-spot"
          operator: "Equal"
          value: "true"
          effect: "NoSchedule"
```

## Part 2 — The custom-metric HPA (the hard part)

Scaling on **requests-per-second** means the HPA reads a metric from Cloud Monitoring via the **Custom Metrics Stackdriver Adapter**. The path is: your app emits an RPS-shaped metric → Cloud Monitoring → the adapter exposes it on the `custom.metrics.k8s.io` API → the HPA reads it.

The cleanest way to get a real RPS metric without rewriting the app is a **Prometheus sidecar + the adapter's Prometheus-to-Monitoring path**, but for this challenge the supported, lower-effort route is to export a counter from FastAPI to Cloud Monitoring directly and let the adapter surface it. Add a tiny middleware to the service that increments a Cloud Monitoring custom metric per request. (You may instead use the `prometheus-to-sd` sidecar pattern documented by Google; either earns the criterion.)

1. Install the adapter:

   ```bash
   kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/k8s-stackdriver/master/custom-metrics-stackdriver-adapter/deploy/production/adapter_new_resource_model.yaml
   ```

   The adapter itself authenticates via Workload Identity — bind its KSA (`custom-metrics-stackdriver-adapter` in `custom-metrics`) to a GSA with `roles/monitoring.viewer`. This is your second Workload Identity binding of the week; do it the same way as Exercise 2.

2. The HPA reading the custom RPS metric:

   ```yaml
   apiVersion: autoscaling/v2
   kind: HorizontalPodAutoscaler
   metadata:
     name: fastapi-hpa
   spec:
     scaleTargetRef:
       apiVersion: apps/v1
       kind: Deployment
       name: fastapi
     minReplicas: 2
     maxReplicas: 10
     metrics:
       - type: Pods
         pods:
           metric:
             name: custom.googleapis.com|fastapi|requests_per_second
           target:
             type: AverageValue
             averageValue: "50" # scale so each pod handles ~50 RPS
     behavior:
       scaleUp:
         stabilizationWindowSeconds: 30
       scaleDown:
         stabilizationWindowSeconds: 120
   ```

3. Verify the metric is readable through the custom-metrics API before you trust the HPA:

   ```bash
   kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta2/namespaces/default/pods/*/custom.googleapis.com|fastapi|requests_per_second" | python3 -m json.tool
   ```

## Part 3 — Measure

Run the **identical** measurement protocol on both clusters and record the numbers.

### Cold-start

The time from "pod does not exist" to "pod serves a 200." On Autopilot this includes Google provisioning a node; on Standard-spot scaled to 0 it includes the cluster autoscaler adding a spot node. Measure both at-scale (a node already exists) and from-cold (scale to 0, then trigger a request).

```bash
# Scale to zero (Standard spot pool to 0 nodes; Autopilot removes the node).
kubectl scale deployment/fastapi --replicas=0
# Wait until no pods/nodes back the workload, then:
kubectl scale deployment/fastapi --replicas=1
# Time until the pod is Ready and /healthz returns 200:
time (until kubectl get pod -l app=fastapi \
  -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].status}' \
  2>/dev/null | grep -q True; do sleep 1; done)
```

### Scale-out

Generate load that exceeds 50 RPS/pod and time how long the HPA takes to add replicas and how long until the new replicas are Ready and absorbing traffic.

```bash
kubectl port-forward service/fastapi 8080:80 >/dev/null 2>&1 &
hey -z 240s -q 400 -c 80 http://localhost:8080/work &
# In another terminal, watch the HPA react:
kubectl get hpa fastapi-hpa -w
# Record: T0 (load starts), T1 (HPA decides to scale), T2 (new pods Ready).
```

### Monthly cost

Use the §1.2 method from Lecture 1 and the pricing calculator. For Autopilot, sum pod resource requests × hours × rate + cluster fee. For Standard-spot, node count × spot machine price × hours + cluster fee. Compute at **two load points**: steady (2 replicas) and peak (10 replicas), and a blended 24h estimate assuming peak for 4h/day.

## Acceptance criteria

### Deploy (30%)
- [ ] The same FastAPI image runs on both Autopilot and Standard-with-spot.
- [ ] Workload Identity works on both (a pod reads the GCS object from Exercise 2, or `/whoami` reports the bound GSA). No key file anywhere.
- [ ] The Standard `fastapi` pods are scheduled on the **spot** pool (tolerate the spot taint); `kubectl get pod -o wide` shows them on spot nodes.
- [ ] A `minAvailable: 50%` PDB protects the Deployment on both.

### HPA on custom metric (35%)
- [ ] The Custom Metrics Stackdriver Adapter is installed and authenticates via Workload Identity (its KSA bound to a GSA with `monitoring.viewer`).
- [ ] `kubectl get --raw .../custom.metrics.k8s.io/...requests_per_second` returns a real value.
- [ ] The HPA scales the Deployment up under load and back down after, driven by the RPS metric (not CPU). `kubectl describe hpa` shows the custom metric as the scaling signal.

### Measure & recommend (35%)
- [ ] `challenge-01-results.md` contains a table with cold-start (warm + from-zero), scale-out time (T0→T1→T2), and monthly cost (steady, peak, blended) for **both** clusters, measured on your clusters.
- [ ] A one-paragraph recommendation that names which mode you would run this workload on, **with a dollar number** and the deciding factor (cost? cold-start? the spot-reclaim risk? operational toil?).
- [ ] You note at least one thing that surprised you in the measurements (e.g., Autopilot cold-start being slower/faster than expected, spot reclaim during a test, the cluster fee dominating at low scale).

### Teardown (gate — pass/fail)
- [ ] Both clusters deleted. `gcloud container clusters list` is empty of this week's clusters.
- [ ] No orphaned forwarding rules or disks. `gcloud compute forwarding-rules list` and `gcloud compute disks list` are clean.

## Stretch (optional)

- Run the cost comparison again with an **Autopilot Spot Pods** configuration (toleration + `cloud.google.com/gke-spot` nodeSelector) and a Standard pool with a **3-year committed-use discount** modeled in. Does the recommendation change? This is the §1.7 "do the math against the correct compute class" point made real.
- Trigger a spot **preemption** on the Standard pool (Google reclaims a spot node) during a load test and document what the PDB + HPA do. This previews the chaos-drill muscle you need for the capstone.
