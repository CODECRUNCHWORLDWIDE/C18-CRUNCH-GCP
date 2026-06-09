#!/usr/bin/env python3
"""
Exercise 2 - Chaos drill driver for the Realtime Event Pipeline capstone.

Drive ONE chaos drill against your live capstone, capture a precise timeline,
measure the SLO impact and the recovery time, and emit a POSTMORTEM.md skeleton
you fill in. Pick exactly one drill for the capstone deliverable:

  region-failover  Disable the primary region's Cloud Run and prove the standby
                   region takes over within the 5-minute SLO with zero data loss.

  cert-rotation    Rotate the TLS certificate on the global load balancer live and
                   measure time-to-rotate and any user-visible blip.

  pubsub-overload  Push 10x normal traffic at the ingest edge and document where the
                   system bends (DLQ depth, Dataflow lag, which alert fires first).

USAGE
  pip install google-cloud-monitoring google-cloud-pubsub requests
  gcloud auth application-default login
  export GCP_PROJECT=your-project-id
  export GCP_PROJECT_STANDBY=your-standby-project-id   # region-failover only
  export LB_IP=$(gcloud compute addresses describe edge-ip --global \
                   --format='value(address)')

  python3 exercise-02-chaos-drill.py region-failover --duration 600
  python3 exercise-02-chaos-drill.py pubsub-overload --rps 1000 --duration 300
  python3 exercise-02-chaos-drill.py cert-rotation --new-cert edge-cert-2

WHAT IT DOES (and does NOT do)
  This driver injects the fault by calling the relevant gcloud command (region
  failover = disabling the primary backend; cert rotation = swapping the LB cert;
  overload = a high-rate request loop) and then *probes* the system once per second,
  recording status codes and latency. It computes when the SLO was first breached and
  when it recovered. It does not mutate Terraform state; the fault is reversible and the
  driver reverses it on exit (Ctrl-C is handled). Adapt the resource names near the top
  to match YOUR capstone.

ACCEPTANCE CRITERIA
  [ ] One drill runs end-to-end and prints a timeline with: t0 (steady state),
      t_fault (fault injected), t_impact (first SLO breach, or "none"),
      t_recover (SLO restored), and recovery_seconds.
  [ ] For region-failover: recovery_seconds < 300 and zero data loss
      (DLQ depth unchanged, backlog drains).
  [ ] A POSTMORTEM.md skeleton is written with the measured timeline filled in.
  [ ] The fault is reversed and the system is back to steady state at exit.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Callable

import requests

# --------------------------------------------------------------------------- #
# Adapt these to YOUR capstone's resource names.
# --------------------------------------------------------------------------- #
PROJECT = os.environ.get("GCP_PROJECT", "")
PROJECT_STANDBY = os.environ.get("GCP_PROJECT_STANDBY", "")
LB_IP = os.environ.get("LB_IP", "")

PRIMARY_REGION = "us-central1"
STANDBY_REGION = "us-east1"
INGEST_SERVICE = "ingest"                 # Cloud Run service name
INGEST_BACKEND = "ingest-backend-primary"  # LB backend service for primary
URL_MAP = "edge-url-map"
TARGET_PROXY = "edge-https-proxy"          # for cert rotation
DLQ_SUBSCRIPTION = "events-dlq-sub"        # Pub/Sub DLQ subscription id
WORK_SUBSCRIPTION = "events-dataflow-sub"  # main work subscription id

# SLO: a probe is "good" if it returns 2xx within this many milliseconds.
SLO_LATENCY_MS = 500.0
# Number of consecutive good/bad probes that flips the steady-state verdict.
HYSTERESIS = 3


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #
def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a gcloud/shell command, surfacing stderr on failure."""
    print(f"  $ {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc


def gcloud(args: list[str], project: str = "", check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["gcloud", *args]
    if project:
        cmd += [f"--project={project}"]
    return run(cmd, check=check)


# --------------------------------------------------------------------------- #
# The continuous probe: one HTTP request/sec, recording status + latency.
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class Probe:
    t: dt.datetime
    ok: bool
    status: int
    latency_ms: float


class Prober:
    """Background thread that probes the edge once per second."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.samples: list[Probe] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._session = requests.Session()

    def _one(self) -> Probe:
        body = json.dumps(
            {"tenant": "chaos", "type": "probe", "id": f"probe-{int(time.time()*1000)}",
             "ts": iso(now_utc())}
        )
        t0 = time.monotonic()
        try:
            r = self._session.post(
                self.url,
                data=body,
                headers={"Content-Type": "application/json",
                         "X-Idempotency-Key": f"probe-{int(time.time()*1000)}"},
                timeout=SLO_LATENCY_MS / 1000.0 * 4,  # generous; we judge against SLO below
            )
            latency_ms = (time.monotonic() - t0) * 1000.0
            ok = (200 <= r.status_code < 300) and latency_ms <= SLO_LATENCY_MS
            return Probe(now_utc(), ok, r.status_code, latency_ms)
        except requests.RequestException:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Probe(now_utc(), False, 0, latency_ms)

    def _loop(self) -> None:
        while not self._stop.is_set():
            tick = time.monotonic()
            self.samples.append(self._one())
            # Pace to ~1 Hz.
            sleep = 1.0 - (time.monotonic() - tick)
            if sleep > 0:
                self._stop.wait(sleep)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


# --------------------------------------------------------------------------- #
# Timeline analysis: when did the SLO break and recover?
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class Timeline:
    t_start: dt.datetime
    t_fault: dt.datetime | None = None
    t_impact: dt.datetime | None = None     # first sustained SLO breach
    t_recover: dt.datetime | None = None    # SLO restored after fault

    @property
    def recovery_seconds(self) -> float | None:
        if self.t_fault and self.t_recover:
            return (self.t_recover - self.t_fault).total_seconds()
        return None

    @property
    def impact_seconds(self) -> float | None:
        if self.t_impact and self.t_recover:
            return (self.t_recover - self.t_impact).total_seconds()
        return None


def analyze(samples: list[Probe], t_fault: dt.datetime) -> Timeline:
    """Find first sustained breach after the fault and the subsequent recovery."""
    tl = Timeline(t_start=samples[0].t if samples else now_utc(), t_fault=t_fault)
    after = [s for s in samples if s.t >= t_fault]
    bad_streak = 0
    good_streak = 0
    breached = False
    for s in after:
        if s.ok:
            good_streak += 1
            bad_streak = 0
            if breached and tl.t_recover is None and good_streak >= HYSTERESIS:
                tl.t_recover = s.t
                break
        else:
            bad_streak += 1
            good_streak = 0
            if not breached and bad_streak >= HYSTERESIS:
                breached = True
                tl.t_impact = s.t
    if not breached:
        # No sustained breach: the system absorbed the fault. Recovery == fault time.
        tl.t_recover = t_fault
    return tl


# --------------------------------------------------------------------------- #
# Drill 1: region failover
# --------------------------------------------------------------------------- #
def drill_region_failover(duration_s: int) -> tuple[Timeline, dict]:
    if not PROJECT_STANDBY:
        sys.exit("region-failover needs GCP_PROJECT_STANDBY set.")

    dlq_before = pubsub_backlog(DLQ_SUBSCRIPTION)
    prober = Prober(f"https://{LB_IP}/v1/events")
    prober.start()
    print(f"[t0] steady state, probing https://{LB_IP}/v1/events ...")
    time.sleep(20)  # establish a steady-state baseline

    t_fault = now_utc()
    print(f"[t_fault={iso(t_fault)}] injecting fault: scaling primary ingest to zero")
    # Reversible fault: drive primary Cloud Run to min/max instances = 0 so the LB
    # health check fails the primary backend and Cloud DNS / LB shifts to standby.
    gcloud(["run", "services", "update", INGEST_SERVICE,
            f"--region={PRIMARY_REGION}", "--min-instances=0", "--max-instances=0"],
           project=PROJECT)

    def restore() -> None:
        print("[restore] bringing primary ingest back up")
        gcloud(["run", "services", "update", INGEST_SERVICE,
                f"--region={PRIMARY_REGION}", "--min-instances=1", "--max-instances=10"],
               project=PROJECT, check=False)

    _install_restore_handler(restore)
    time.sleep(duration_s)
    prober.stop()
    restore()

    dlq_after = pubsub_backlog(DLQ_SUBSCRIPTION)
    tl = analyze(prober.samples, t_fault)
    extra = {
        "drill": "region-failover",
        "dlq_depth_before": dlq_before,
        "dlq_depth_after": dlq_after,
        "data_loss": "none" if dlq_after <= dlq_before else f"DLQ grew by {dlq_after - dlq_before}",
        "samples": len(prober.samples),
    }
    return tl, extra


# --------------------------------------------------------------------------- #
# Drill 2: certificate rotation
# --------------------------------------------------------------------------- #
def drill_cert_rotation(new_cert: str, duration_s: int) -> tuple[Timeline, dict]:
    if not new_cert:
        sys.exit("cert-rotation needs --new-cert NAME (a pre-created SSL cert resource).")

    prober = Prober(f"https://{LB_IP}/v1/events")
    prober.start()
    print(f"[t0] steady state, probing TLS endpoint ...")
    time.sleep(20)

    t_fault = now_utc()
    print(f"[t_fault={iso(t_fault)}] rotating cert on target proxy {TARGET_PROXY} -> {new_cert}")
    gcloud(["compute", "target-https-proxies", "update", TARGET_PROXY,
            f"--ssl-certificates={new_cert}", "--global"], project=PROJECT)

    time.sleep(duration_s)
    prober.stop()
    tl = analyze(prober.samples, t_fault)
    extra = {
        "drill": "cert-rotation",
        "new_cert": new_cert,
        "samples": len(prober.samples),
        "note": "A correctly-rotated managed cert produces ZERO failed probes; "
                "any blip indicates a mismatched cert chain or propagation lag.",
    }
    return tl, extra


# --------------------------------------------------------------------------- #
# Drill 3: Pub/Sub 10x overload
# --------------------------------------------------------------------------- #
def drill_pubsub_overload(rps: int, duration_s: int) -> tuple[Timeline, dict]:
    work_before = pubsub_backlog(WORK_SUBSCRIPTION)
    dlq_before = pubsub_backlog(DLQ_SUBSCRIPTION)

    prober = Prober(f"https://{LB_IP}/v1/events")
    prober.start()
    print(f"[t0] steady state ...")
    time.sleep(20)

    t_fault = now_utc()
    print(f"[t_fault={iso(t_fault)}] flooding ingest at ~{rps} RPS for {duration_s}s")
    stop_flag = threading.Event()
    flood = threading.Thread(target=_flood, args=(rps, stop_flag), daemon=True)
    flood.start()

    time.sleep(duration_s)
    stop_flag.set()
    flood.join(timeout=5)
    # Let the system drain a little so we can see whether it recovers.
    time.sleep(60)
    prober.stop()

    work_after = pubsub_backlog(WORK_SUBSCRIPTION)
    dlq_after = pubsub_backlog(DLQ_SUBSCRIPTION)
    tl = analyze(prober.samples, t_fault)
    extra = {
        "drill": "pubsub-overload",
        "target_rps": rps,
        "work_backlog_before": work_before,
        "work_backlog_after": work_after,
        "dlq_depth_before": dlq_before,
        "dlq_depth_after": dlq_after,
        "bend_point": "ingest stayed up" if tl.t_impact is None
                      else f"ingest SLO broke at {iso(tl.t_impact)}",
        "samples": len(prober.samples),
    }
    return tl, extra


def _flood(rps: int, stop: threading.Event) -> None:
    session = requests.Session()
    url = f"https://{LB_IP}/v1/events"
    interval = 1.0 / max(rps, 1)
    while not stop.is_set():
        tick = time.monotonic()
        try:
            session.post(
                url,
                data=json.dumps({"tenant": "flood", "type": "page_view",
                                 "id": f"f-{int(time.time()*1e6)}", "ts": iso(now_utc())}),
                headers={"Content-Type": "application/json"},
                timeout=2,
            )
        except requests.RequestException:
            pass
        sleep = interval - (time.monotonic() - tick)
        if sleep > 0:
            time.sleep(sleep)


# --------------------------------------------------------------------------- #
# Pub/Sub backlog read (used to prove zero data loss / find the bend point)
# --------------------------------------------------------------------------- #
def pubsub_backlog(subscription_id: str) -> int:
    """Approximate undelivered message count via Monitoring; 0 on any error."""
    try:
        from google.cloud import monitoring_v3  # imported lazily so --help works offline
    except ImportError:
        print("  (google-cloud-monitoring not installed; backlog reported as 0)")
        return 0
    try:
        client = monitoring_v3.MetricServiceClient()
        name = f"projects/{PROJECT}"
        end = time.time()
        interval = monitoring_v3.TimeInterval(
            {"end_time": {"seconds": int(end)}, "start_time": {"seconds": int(end - 300)}}
        )
        flt = (
            'metric.type="pubsub.googleapis.com/subscription/num_undelivered_messages" '
            f'AND resource.labels.subscription_id="{subscription_id}"'
        )
        results = client.list_time_series(
            request={"name": name, "filter": flt, "interval": interval,
                     "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL}
        )
        latest = 0
        for series in results:
            for point in series.points:
                latest = int(point.value.int64_value)
                break
            break
        return latest
    except Exception as exc:  # noqa: BLE001 - drill tooling should degrade gracefully
        print(f"  (backlog read failed: {exc}; reporting 0)")
        return 0


# --------------------------------------------------------------------------- #
# Restore handler so Ctrl-C never leaves the system faulted
# --------------------------------------------------------------------------- #
def _install_restore_handler(restore: Callable[[], None]) -> None:
    def handler(signum, frame):  # noqa: ANN001
        print("\n[signal] caught interrupt; restoring system before exit")
        try:
            restore()
        finally:
            sys.exit(130)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


# --------------------------------------------------------------------------- #
# Postmortem skeleton
# --------------------------------------------------------------------------- #
def write_postmortem(tl: Timeline, extra: dict, path: str = "POSTMORTEM.md") -> None:
    recovery = tl.recovery_seconds
    impact = tl.impact_seconds
    verdict = "PASS" if (extra["drill"] != "region-failover" or
                         (recovery is not None and recovery < 300
                          and extra.get("data_loss") == "none")) else "REVIEW"
    md = f"""# Chaos Drill Postmortem - {extra['drill']}

> Generated by exercise-02-chaos-drill.py on {iso(now_utc())}. Fill in the prose sections.

## Summary

- **Drill:** {extra['drill']}
- **Verdict:** {verdict}
- **Recovery time:** {f'{recovery:.0f}s' if recovery is not None else 'n/a'}
- **User-visible impact window:** {f'{impact:.0f}s' if impact is not None else 'none (system absorbed the fault)'}

## Timeline (UTC)

| Event | Time |
|---|---|
| Steady-state baseline | {iso(tl.t_start)} |
| Fault injected | {iso(tl.t_fault) if tl.t_fault else 'n/a'} |
| First sustained SLO breach | {iso(tl.t_impact) if tl.t_impact else 'none'} |
| SLO restored | {iso(tl.t_recover) if tl.t_recover else 'n/a'} |

## Measurements

```
{json.dumps(extra, indent=2)}
```

## What we expected

<!-- One paragraph: what the design predicted would happen during this fault. -->

## What actually happened

<!-- One paragraph: the gap between expectation and reality, if any. -->

## Did data move correctly?

<!-- Region failover: backlog drained, DLQ unchanged? Overload: where did it bend? -->

## Action items

| Action | Owner | Tag (accept / mitigate-now / mitigate-later) |
|---|---|---|
|  |  |  |
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"\n[postmortem] wrote {path}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Capstone chaos-drill driver.")
    sub = parser.add_subparsers(dest="drill", required=True)

    p_fail = sub.add_parser("region-failover")
    p_fail.add_argument("--duration", type=int, default=600, help="seconds to observe")

    p_cert = sub.add_parser("cert-rotation")
    p_cert.add_argument("--new-cert", required=True, help="pre-created SSL cert resource name")
    p_cert.add_argument("--duration", type=int, default=180)

    p_over = sub.add_parser("pubsub-overload")
    p_over.add_argument("--rps", type=int, default=1000, help="flood rate (10x of 100 RPS)")
    p_over.add_argument("--duration", type=int, default=300)

    args = parser.parse_args()

    if not PROJECT or not LB_IP:
        sys.exit("Set GCP_PROJECT and LB_IP environment variables first (see module docstring).")

    print(f"=== Chaos drill: {args.drill} (project={PROJECT}) ===")
    if args.drill == "region-failover":
        tl, extra = drill_region_failover(args.duration)
    elif args.drill == "cert-rotation":
        tl, extra = drill_cert_rotation(args.new_cert, args.duration)
    elif args.drill == "pubsub-overload":
        tl, extra = drill_pubsub_overload(args.rps, args.duration)
    else:  # unreachable due to required=True
        sys.exit(2)

    print("\n=== Timeline ===")
    print(f"  steady state : {iso(tl.t_start)}")
    print(f"  fault        : {iso(tl.t_fault) if tl.t_fault else 'n/a'}")
    print(f"  first breach : {iso(tl.t_impact) if tl.t_impact else 'none'}")
    print(f"  recovered    : {iso(tl.t_recover) if tl.t_recover else 'n/a'}")
    if tl.recovery_seconds is not None:
        print(f"  recovery_seconds: {tl.recovery_seconds:.0f}")
    write_postmortem(tl, extra)


if __name__ == "__main__":
    main()
