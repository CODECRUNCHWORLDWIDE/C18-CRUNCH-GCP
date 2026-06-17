# Exercise 1 — Instrument a Python service with OpenTelemetry and export to Cloud Trace + Cloud Monitoring

> **Goal:** Take a plain FastAPI service, add OpenTelemetry traces and metrics, export them to Cloud Trace and Cloud Monitoring, and see a correlated trace with a custom metric — in **under an hour**. This is the syllabus skill: "Add OTel instrumentation to a Python/Go service in under an hour."
>
> **Estimated time:** 60 minutes.

This is the guided exercise. You build a real FastAPI service, instrument it two ways (zero-code auto-instrumentation *and* a hand-written span + metric), export to GCP, and confirm the data landed. The starter and the full solution are both here; type the solution, do not paste it — the muscle memory is the point.

## Prerequisites

- `GOOGLE_CLOUD_PROJECT` set to your project; `gcloud auth application-default login` done.
- The APIs from Lecture 1 enabled (`cloudtrace`, `monitoring`, `logging`).
- Python 3.11+.

## Step 0 — Scaffold

```bash
mkdir otel-ex01 && cd otel-ex01
python -m venv .venv && source .venv/bin/activate
pip install \
  "fastapi==0.115.*" "uvicorn[standard]==0.32.*" \
  "opentelemetry-sdk==1.27.*" "opentelemetry-api==1.27.*" \
  "opentelemetry-exporter-otlp-proto-grpc==1.27.*" \
  "opentelemetry-exporter-gcp-trace==1.7.*" \
  "opentelemetry-exporter-gcp-monitoring==1.7.*" \
  "opentelemetry-instrumentation-fastapi==0.48b0" \
  "opentelemetry-instrumentation-requests==0.48b0" \
  requests
```

We export **directly to GCP** in this exercise (the `gcp-trace` and `gcp-monitoring` exporters) to keep the moving parts minimal. The mini-project switches to the collector + OTLP path. Both are valid; this is the faster on-ramp.

## Step 1 — The uninstrumented service (the starting point)

Create `app.py`. This is a service that does a tiny bit of "work" and an outbound HTTP call, so the trace has something interesting in it:

```python
# app.py — starting point, no instrumentation yet.
import time
import random
import requests
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.get("/work")
def work() -> dict:
    # Simulate some CPU work.
    time.sleep(random.uniform(0.01, 0.05))
    # An outbound call we want to see as a child span.
    r = requests.get("https://www.googleapis.com/discovery/v1/apis", timeout=5)
    return {"apis_listed": len(r.json().get("items", [])), "ok": True}
```

Run it (`uvicorn app:app --port 8080`), hit `http://localhost:8080/work`, confirm it returns JSON. Now it works but tells you nothing. We instrument it.

## Step 2 — Wire the providers (the telemetry bootstrap)

Create `telemetry.py`. This is the reusable bootstrap you will copy into every service in the mini-project. It builds the `Resource`, the `TracerProvider`, and the `MeterProvider`, and points both at GCP.

```python
# telemetry.py — OpenTelemetry bootstrap for traces + metrics → GCP.
import os

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "otel-ex01")


def init_telemetry() -> None:
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": os.environ.get("SERVICE_VERSION", "0.1.0"),
            "deployment.environment": os.environ.get("ENVIRONMENT", "dev"),
        }
    )

    # Traces → Cloud Trace.
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(CloudTraceSpanExporter())
    )
    trace.set_tracer_provider(tracer_provider)

    # Metrics → Cloud Monitoring, exported every 30s.
    metric_reader = PeriodicExportingMetricReader(
        CloudMonitoringMetricsExporter(),
        export_interval_millis=30_000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
```

## Step 3 — Auto-instrument FastAPI + requests, add one manual span and one metric

Replace `app.py` with the instrumented version. Three things happen: (1) `init_telemetry()` runs at import; (2) `FastAPIInstrumentor` and `RequestsInstrumentor` auto-create a SERVER span per request and a CLIENT span per outbound call; (3) we add a manual child span around the "work" and a custom histogram metric for its duration.

```python
# app.py — instrumented.
import time
import random
import requests
from fastapi import FastAPI

from telemetry import init_telemetry, SERVICE_NAME

init_telemetry()  # MUST run before instrumentors attach.

from opentelemetry import trace, metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)
RequestsInstrumentor().instrument()

tracer = trace.get_tracer(SERVICE_NAME)
meter = metrics.get_meter(SERVICE_NAME)

work_duration = meter.create_histogram(
    "ex01.work.duration",
    unit="ms",
    description="Duration of the /work compute span",
)
work_counter = meter.create_counter(
    "ex01.work.count",
    unit="1",
    description="Count of /work calls by outcome",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/work")
def work() -> dict:
    start = time.perf_counter()
    outcome = "ok"
    try:
        with tracer.start_as_current_span("compute") as span:
            sleep_s = random.uniform(0.01, 0.05)
            span.set_attribute("compute.sleep_ms", round(sleep_s * 1000, 2))
            time.sleep(sleep_s)
        # The RequestsInstrumentor turns this into a CLIENT child span automatically.
        r = requests.get(
            "https://www.googleapis.com/discovery/v1/apis", timeout=5
        )
        count = len(r.json().get("items", []))
        return {"apis_listed": count, "ok": True}
    except Exception:
        outcome = "error"
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        work_duration.record(elapsed_ms, {"outcome": outcome})
        work_counter.add(1, {"outcome": outcome})
```

## Step 4 — Run it and generate traffic

```bash
export GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"
export OTEL_SERVICE_NAME="otel-ex01"
uvicorn app:app --port 8080 &
# Hit /work 40 times so there is a metric distribution and several traces.
for i in $(seq 1 40); do curl -s localhost:8080/work > /dev/null; done
# Give the batch/periodic exporters time to flush.
sleep 35
```

## Step 5 — Confirm the data landed

**Cloud Trace.** Open Cloud Trace, filter by service `otel-ex01`. You should see traces for `GET /work`, each a waterfall:

```
GET /work                          (SERVER span, ~45ms)
├── compute                        (INTERNAL span, ~10-50ms, attr compute.sleep_ms)
└── HTTP GET                       (CLIENT span, the googleapis call)
```

The nesting is the proof your manual span and the auto-instrumented client span share the request's context.

**Cloud Monitoring.** In Metrics Explorer, search for `custom.googleapis.com/ex01/work/duration` (the GCP exporter prefixes custom OTel metrics with `custom.googleapis.com/`). You should see a distribution metric; switch the aligner to "99th percentile" and you have your latency SLI source. Search `ex01/work/count` and slice by the `outcome` label.

## Expected output

The terminal shows 40 successful `/work` responses. Cloud Trace shows ~40 traces for service `otel-ex01`, each with the three-span waterfall above. Metrics Explorer shows `ex01.work.duration` as a distribution and `ex01.work.count` with an `outcome=ok` series at 40.

A representative trace summary (your latencies will differ):

```
Trace 7f3a... | otel-ex01 | GET /work | 47.2 ms
  ├─ compute        12.0 ms   compute.sleep_ms=12.0
  └─ HTTP GET       33.8 ms   http.url=https://www.googleapis.com/discovery/v1/apis
                              http.status_code=200
```

## Acceptance criteria

- [ ] `GET /work` returns JSON and the service runs without errors.
- [ ] Cloud Trace shows traces for service `otel-ex01` with a SERVER span, a nested `compute` INTERNAL span, and a CLIENT span for the outbound call — all in **one** trace.
- [ ] The `compute` span carries the `compute.sleep_ms` attribute.
- [ ] Cloud Monitoring shows the `ex01.work.duration` distribution metric and the `ex01.work.count` counter with an `outcome` label.
- [ ] You did the whole thing — scaffold to confirmed data — in under 60 minutes. (Time yourself. This is the skill.)

## Teardown

Nothing persistent is created in GCP by this exercise except the telemetry data itself, which ages out per the default retention (30 days for traces, custom metrics stop accruing the moment you stop the service). Stop uvicorn (`kill %1`) and deactivate the venv. No `terraform destroy` needed here.

## What you just learned

- **Auto-instrumentation does most of the work.** The `FastAPIInstrumentor` + `RequestsInstrumentor` gave you SERVER and CLIENT spans for free, with correct parent/child nesting, without touching the handler.
- **Manual spans and metrics are for the things only you understand.** The `compute` span and the `work.duration` histogram capture *your* domain, not the framework's.
- **`init_telemetry()` must run before the instrumentors attach** — they read the global providers at instrument time. Ordering bugs here produce "no data, no error," the most confusing failure mode in OTel.
- **The GCP exporters prefix custom metrics with `custom.googleapis.com/`** and you read percentiles off the distribution — which is exactly the SLI source you wire into the SLO in Exercise 2.
