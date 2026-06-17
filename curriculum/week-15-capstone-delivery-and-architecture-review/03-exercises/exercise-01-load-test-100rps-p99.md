# Exercise 1 — Load test at 100 RPS for 30 minutes, verify p99 < 500ms end-to-end

> **Estimated time:** ~90 minutes (10 min setup, 30 min running, 50 min reading and writing it up). **Cost:** a few cents of egress plus 30 minutes of an always-warm Cloud Run instance — under \$1.

This is the capstone acceptance test that everyone fails the first time, because the first time they discover their `min-instances=0` standby autoscaling cold-starts in the middle of the run, or their Dataflow pipeline lags, or they were measuring p99 from their laptop and counting their home wifi. You will measure it *correctly*: server-side, off the load balancer's own distribution metric, over a sustained window.

## Goal

Drive 100 requests/second of synthetic events at your capstone's ingest edge for 30 minutes, and read the end-to-end p99 latency off Cloud Monitoring. The acceptance bar is **p99 < 500ms** sustained. You will produce a chart screenshot and a short writeup.

## What "end-to-end" means here

End-to-end is measured at the **global external Application Load Balancer**, from the moment it receives the request to the moment it sends the last byte of the response. That is the metric `loadbalancing.googleapis.com/https/total_latencies`. It is the right boundary because:

- It includes everything the client experiences inside GCP: Cloud Armor evaluation, the LB hop, Cloud Run cold-start (if any), validation, and the synchronous Pub/Sub publish.
- It excludes your laptop's network, which is noise you do not control and your users do not share.
- It is recorded by Google on every request, so there is no coordinated-omission problem — slow requests are counted, not dropped.

The asynchronous tail (Pub/Sub → Dataflow → BigQuery) is **not** in this number, and that is correct: ingest returns as soon as the event is durably published. You verify the async path's health separately, with the Pub/Sub backlog metric.

## Step 1 — Confirm the system is warm and healthy

Cold-start contaminates the first minute. Warm the primary region before the timed run:

```bash
export GCP_PROJECT="your-project-id"
LB_IP=$(gcloud compute addresses describe edge-ip --global \
  --project="$GCP_PROJECT" --format='value(address)')

# Sanity: one request must succeed before you load-test.
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" \
  -X POST "https://${LB_IP}/v1/events" \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: warmup-1" \
  -d '{"tenant":"acme","type":"page_view","id":"warmup-1","ts":"2026-06-09T00:00:00Z"}'
```

You want a `200` and a `time_total` under ~0.3s. If you get a `403`, Cloud Armor is blocking you (check the rate-limit rule and your source IP). If you get a `502`/`503`, the backend is unhealthy — fix that before load-testing; a load test against a broken backend measures nothing.

## Step 2 — Generate 100 RPS for 30 minutes with `hey`

`hey` is the simplest correct tool. At 100 RPS for 30 minutes you send 180,000 requests. Use `-q` (per-worker query rate) × `-c` (workers) = target RPS, and `-z` for a duration:

```bash
# 5 workers x 20 q/s = 100 RPS, for 30 minutes.
# Each request carries a unique idempotency key so the system dedupes correctly.
cat > /tmp/payload.json <<'EOF'
{"tenant":"acme","type":"page_view","id":"load","ts":"2026-06-09T00:00:00Z"}
EOF

hey -z 30m -q 20 -c 5 \
  -m POST \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: load-$(date +%s)-${RANDOM}" \
  -D /tmp/payload.json \
  "https://${LB_IP}/v1/events"
```

A note on the idempotency key: `hey` sends the *same* header on every request, which is fine for a load test of the ingest path (the dedup logic still exercises), but if you want unique keys per request you need a wrapper. The starter wrapper is in Step 5. For the p99 measurement, the header value does not matter — the LB latency metric counts every request.

`hey` will print its own client-side histogram at the end. **Do not report that number.** It is measured from your machine and is subject to coordinated omission if any worker stalls. Use it only as a sanity check that the run actually sustained ~100 RPS.

## Step 3 — Read p99 off Cloud Monitoring (the number you report)

While the run is going, open Cloud Monitoring → Metrics Explorer (or use the MQL below in a dashboard). The query for the LB's p99 latency:

```
fetch https_lb_rule
| metric 'loadbalancing.googleapis.com/https/total_latencies'
| filter (resource.url_map_name == 'edge-url-map')
| align delta(1m)
| every 1m
| group_by [], [value_p99: percentile(value.total_latencies, 99)]
```

Replace `edge-url-map` with your URL map's name (`gcloud compute url-maps list`). Add a second line for `value_p50` to see the median alongside the tail. Watch the chart for the full 30 minutes. You are looking for:

- **p99 stays under 500ms for the whole window** (the acceptance bar). A spike in the first minute from cold-start is acceptable *if* it recovers; annotate it.
- **The line is flat-ish, not climbing.** A climbing p99 means something downstream is saturating (Cloud Run hitting max-instances, the publish call backpressuring).

Also chart the request rate to confirm you actually sustained 100 RPS:

```
fetch https_lb_rule
| metric 'loadbalancing.googleapis.com/https/request_count'
| align rate(1m)
| every 1m
| group_by [], [req_per_s: sum(value.request_count)]
```

## Step 4 — Verify the async path kept up

Ingest p99 can be perfect while the pipeline silently falls behind. Check that the Pub/Sub subscription backlog did not grow unboundedly during the run:

```bash
# Oldest unacked message age, in seconds, over the run window.
gcloud monitoring time-series list \
  --project="$GCP_PROJECT" \
  --filter='metric.type="pubsub.googleapis.com/subscription/oldest_unacked_message_age" AND resource.labels.subscription_id="events-dataflow-sub"' \
  --format='value(points.value.int64Value)' 2>/dev/null | head -5
```

A steady value (a few seconds) is healthy. A monotonically climbing value means Dataflow is not keeping up at 100 RPS — note it as a finding even if ingest p99 passed, because it is a real scaling limit.

## Step 5 — (Starter) Unique-key load generator

If you want unique idempotency keys per request (more realistic dedup exercise), `hey` alone cannot do it. Here is a tiny Python driver you can run instead, which the solution expands:

```python
#!/usr/bin/env python3
"""Minimal 100-RPS driver with unique idempotency keys. Starter."""
import os, time, uuid, threading, requests

LB_IP = os.environ["LB_IP"]
URL = f"https://{LB_IP}/v1/events"
TARGET_RPS = 100
DURATION_S = 30 * 60

# TODO: implement a token-bucket pacer that sends TARGET_RPS requests/sec,
#       each with a fresh X-Idempotency-Key = uuid4(), for DURATION_S seconds,
#       using a thread pool so a slow response does not stall the pacer.
```

## Step 6 — Write it up

Save a `load-test.md` in your capstone repo with:

1. The MQL p99 query and a screenshot of the 30-minute chart.
2. The measured p99 (one number) and p50.
3. The sustained request rate (proving ~100 RPS).
4. The Pub/Sub backlog behavior (flat or climbing).
5. One sentence: did it pass the < 500ms bar, and if there was a spike, what caused it.

## Solution — the unique-key driver

The token-bucket pacer that completes Step 5, using a bounded thread pool so a slow response never stalls the send rate (this is the coordinated-omission fix on the *client* side):

```python
#!/usr/bin/env python3
"""100-RPS load driver with unique idempotency keys and a non-blocking pacer."""
import os
import time
import uuid
import json
from concurrent.futures import ThreadPoolExecutor

import requests

LB_IP = os.environ["LB_IP"]
URL = f"https://{LB_IP}/v1/events"
TARGET_RPS = int(os.environ.get("TARGET_RPS", "100"))
DURATION_S = int(os.environ.get("DURATION_S", str(30 * 60)))

PAYLOAD = {"tenant": "acme", "type": "page_view", "ts": "2026-06-09T00:00:00Z"}


def send_one(session: requests.Session) -> None:
    key = str(uuid.uuid4())
    body = dict(PAYLOAD, id=key)
    try:
        session.post(
            URL,
            data=json.dumps(body),
            headers={
                "Content-Type": "application/json",
                "X-Idempotency-Key": key,
            },
            timeout=5,
        )
    except requests.RequestException:
        # A timeout is a data point, not a crash. The LB metric records the
        # server-side latency regardless; we just don't block the pacer.
        pass


def main() -> None:
    session = requests.Session()
    # Pool large enough that a few slow responses never throttle the send rate.
    pool = ThreadPoolExecutor(max_workers=TARGET_RPS * 2)
    interval = 1.0 / TARGET_RPS
    deadline = time.monotonic() + DURATION_S
    next_send = time.monotonic()
    sent = 0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_send:
            pool.submit(send_one, session)
            sent += 1
            next_send += interval
            # If we fell behind, catch up without bursting unboundedly.
            if next_send < now:
                next_send = now + interval
        else:
            time.sleep(min(interval / 4, next_send - now))
    pool.shutdown(wait=True)
    print(f"Submitted {sent} requests over {DURATION_S}s "
          f"(~{sent / DURATION_S:.1f} RPS).")


if __name__ == "__main__":
    main()
```

Run it with:

```bash
export LB_IP="$LB_IP"
export TARGET_RPS=100
export DURATION_S=1800
python3 driver.py
```

## Expected output

`hey`'s own summary (client-side, sanity only) looks roughly like:

```
Summary:
  Total:        1800.4 s
  Requests/sec: 99.87
Status code distribution:
  [200] 179812 responses
  [503]    188 responses     # a handful during the cold-start minute is acceptable
```

And the number you actually report, off Cloud Monitoring:

```
p50 end-to-end latency:  41 ms
p99 end-to-end latency:  312 ms   <-- under 500ms: PASS
sustained request rate:  ~100 RPS for 30 min
Pub/Sub oldest-unacked:  3-6 s, flat (pipeline kept up)
```

If your p99 is over 500ms, the three usual culprits are: (1) Cloud Run `max-instances` too low, so requests queue — raise it and re-run; (2) the synchronous Pub/Sub publish is the bottleneck — check the publish span in a trace; (3) you forgot to warm the system and the cold-start minute dominated a too-short run — run the full 30 minutes.

## Acceptance criteria

- [ ] 100 RPS sustained for 30 minutes (confirmed via the LB `request_count` rate chart).
- [ ] p99 measured from `loadbalancing.googleapis.com/https/total_latencies`, **not** from `hey`'s client output.
- [ ] p99 < 500ms over the window (a recoverable cold-start spike is acceptable if annotated).
- [ ] Pub/Sub backlog behavior checked and reported (flat = pass).
- [ ] `load-test.md` written with the chart screenshot and the one-number p99.
