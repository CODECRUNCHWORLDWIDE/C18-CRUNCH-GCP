# Challenge 1 — Internal LB + MIG, Zero-Drop Failover Under Chaos

**Time estimate:** ~3 hours.

## Problem statement

Take everything from this week's exercises and build the system the syllabus names as the Week 5 hands-on lab, then attack it and prove it survives.

You will deploy, entirely in Terraform on top of the Week 04 VPC:

1. A **regional managed instance group** running the Go HTTP service from the exercises, spread across all zones in the region.
2. An **internal passthrough Network Load Balancer** (L4 internal) in front of the MIG: a `google_compute_region_backend_service` with the MIG as its backend, a `google_compute_region_health_check`, and a `google_compute_forwarding_rule` with an internal VIP.
3. **Autoscaling on TWO signals at once:** CPU utilization **and** a custom Cloud Monitoring metric (requests-per-second-per-instance) exported by the service. The autoscaler scales on whichever signal demands more capacity.
4. A **rolling-update policy** (`max_surge`, `max_unavailable=0`) tuned so a new instance template rolls out without dropping a request.

Then you run a **chaos drill** and prove the system holds:

- A sustained load test against the internal VIP for the full drill duration.
- **Mid-traffic, you kill instances** (`gcloud compute instances delete`) and watch autohealing replace them.
- **Mid-traffic, you roll a new instance template** (change the service to return a new version string) and watch the MIG `PROACTIVE`-roll onto it.
- The load test must report **`Success rate: 100.00%`** — zero non-2xx, zero connection errors — across both the kills and the roll.

## Why a custom metric, not just CPU

CPU is a lagging proxy. By the time CPU climbs, requests are already queuing and latency is already rising. For a service whose cost-per-request is steady, **requests-per-second-per-instance is a leading signal** — it climbs the instant traffic arrives, before the CPU has fully ramped. Scaling on RPS-per-instance lets you add capacity *before* latency degrades. Real shops scale web tiers on a custom RPS or queue-depth metric and keep CPU as a backstop. This challenge makes you wire the real pattern, not the tutorial one.

You will need the service to **export a custom metric to Cloud Monitoring** (the Ops Agent or the monitoring client library), and the autoscaler's `metric` block to target it. The provider supports multiple `autoscaling_policy` signals; the autoscaler takes the max across them.

## Acceptance criteria

- [ ] Everything is in **Terraform**, layered on the Week 04 VPC via `terraform_remote_state`. `terraform apply` is clean; `terraform destroy` is clean.
- [ ] The MIG is **regional**, instances spread across zones, running the hardened template (OS Login, Shielded VM, dedicated SA, no external IP) from Exercise 1.
- [ ] An **internal passthrough NLB** fronts the MIG with an internal VIP; a client inside the VPC reaches the service only through the VIP, never an instance IP directly.
- [ ] The **LB health check** and the **autohealing health check** are distinct and correctly scoped (LB check gates traffic; autohealing check gates recreation — and the autohealing one is more conservative).
- [ ] The health-check firewall rule allows `130.211.0.0/22` and `35.191.0.0/16` to the service port.
- [ ] The autoscaler scales on **both CPU (target ~0.6) and a custom RPS-per-instance metric**, taking the max. You can demonstrate a scale-out triggered by the custom metric *before* CPU would have triggered it.
- [ ] The rolling-update policy has **`max_unavailable = 0`** and a positive `max_surge`, with `type = PROACTIVE`.
- [ ] **Chaos drill, documented:** a `hey`/`vegeta` run against the VIP that spans (a) deleting at least 2 instances mid-run and (b) a full template roll, ending with `Success rate: 100.00%`, zero non-2xx, zero connection errors. Paste the summary.
- [ ] A short `CHALLENGE.md` writeup: the architecture (one diagram or ASCII), the two autoscaling signals and why, the chaos drill method, the load-test summary, and one sentence defending the machine family you chose.
- [ ] Teardown verified: `gcloud compute instances list` => `Listed 0 items.`, `gcloud compute forwarding-rules list` empty, `gcloud compute disks list` no orphans.

## The chaos drill, precisely

Run it like an incident, because that is what it is rehearsing.

1. From the in-VPC load generator, start the load against the **internal VIP** (not an instance IP):
   ```bash
   ~/go/bin/hey -z 180s -c 100 http://<INTERNAL_VIP>:8080/work
   ```
2. At ~T+30s, **kill two instances** in different zones:
   ```bash
   gcloud compute instances delete <inst-a> --zone=<zone-a> --quiet &
   gcloud compute instances delete <inst-b> --zone=<zone-b> --quiet &
   ```
   The LB health check should drop them from rotation *before* they fully die (this is why the LB check interval matters), and autohealing refills the group.
3. At ~T+90s, **roll a new template**: change the service's version string, rebuild, push the new binary to GCS (or change the `main-go` metadata), `terraform apply`. The MIG `PROACTIVE`-rolls: `max_surge` new instances come up healthy, then old ones drain out — `max_unavailable=0` means capacity never dips.
4. When `hey` finishes, read the summary. **100.00% or you are not done.**

## Stretch

- **Connection draining on the backend service.** Set `connection_draining_timeout_sec` on the backend service and prove a request in flight when an instance is removed from rotation still completes. Combine with the Exercise 3 graceful-shutdown handler for belt-and-suspenders.
- **Canary the roll.** Use the MIG's `version` block with a second `version` at a small `target_size.fixed` to canary the new template to 1 instance, validate it, then promote. Document the canary→promote sequence.
- **Scale on queue depth instead of RPS.** Put a small in-memory work queue in front of the handler and export queue depth as the custom metric. Argue when queue depth is a better scaling signal than RPS.
- **Fault-inject latency, not just death.** Make 5% of instances respond slowly (not fail) and show how the LB + autohealing behave differently than under hard failure. This is the failure mode health checks miss.

## Hints

<details>
<summary>The internal LB skeleton (regional backend service + forwarding rule)</summary>

```hcl
resource "google_compute_region_health_check" "lb" {
  name               = "week5-ilb-hc"
  region             = var.region
  check_interval_sec = 3
  timeout_sec        = 3
  healthy_threshold  = 2
  unhealthy_threshold = 2
  http_health_check {
    port         = 8080
    request_path = "/healthz"
  }
}

resource "google_compute_region_backend_service" "ilb" {
  name                  = "week5-ilb-backend"
  region                = var.region
  protocol              = "TCP"
  load_balancing_scheme = "INTERNAL"
  health_checks         = [google_compute_region_health_check.lb.id]
  connection_draining_timeout_sec = 30

  backend {
    group          = google_compute_region_instance_group_manager.workserver.instance_group
    balancing_mode = "CONNECTION"
  }
}

resource "google_compute_forwarding_rule" "ilb" {
  name                  = "week5-ilb-fr"
  region                = var.region
  load_balancing_scheme = "INTERNAL"
  backend_service       = google_compute_region_backend_service.ilb.id
  ports                 = ["8080"]
  network               = local.network_self_link
  subnetwork            = local.subnet_self_link
  # Omit ip_address to let GCP allocate an internal VIP from the subnet.
}
```

</details>

<details>
<summary>Adding the custom-metric signal to the autoscaler</summary>

```hcl
autoscaling_policy {
  min_replicas = 2
  max_replicas = 8

  cpu_utilization {
    target = 0.6
  }

  # Scale on a custom per-instance metric. The autoscaler takes the MAX of
  # this and the CPU signal. The metric must be a GAUGE the service exports.
  metric {
    name   = "custom.googleapis.com/workserver/requests_per_second"
    target = 200            # target ~200 RPS per instance
    type   = "GAUGE"
  }
}
```

Export the metric from the service with the Cloud Monitoring client library (`cloud.google.com/go/monitoring/apiv3`) or via the Ops Agent's Prometheus/StatsD receiver. The metric must report a per-instance value the autoscaler can average.

</details>

<details>
<summary>Why max_unavailable=0 is the zero-drop precondition</summary>

A rolling update with `max_unavailable > 0` removes serving instances before their replacements are healthy — a capacity dip exactly when you are also adding load from the roll. With `max_unavailable = 0` and `max_surge > 0`, the MIG always adds healthy capacity first, then removes old. Combined with the LB draining and the Exercise 3 graceful shutdown, no client connection is ever sent to an instance that is going away.

</details>

## Submission

Commit the Terraform, the service, and `CHALLENGE.md` under `challenges/challenge-01/` in your Week 5 repo. The writeup must include the pasted `Success rate: 100.00%` summary that spans both the kills and the roll. A clean `terraform destroy` on a fresh clone is part of the bar — the grader will run it.

## Why this matters

This is the Week 5 hands-on lab from the syllabus, and it is the load-bearing skill of the whole compute phase: **a self-healing, autoscaling fleet you can deploy to on a Friday because a roll never drops traffic.** Every later week assumes you can do this — the GKE rolling updates in Week 06, the Cloud Run revisions in Week 07, the capstone's region failover in Week 14 are all the same idea (fail readiness, add capacity first, drain, then remove) at different layers. Get the muscle here on the simplest substrate and it transfers everywhere.
