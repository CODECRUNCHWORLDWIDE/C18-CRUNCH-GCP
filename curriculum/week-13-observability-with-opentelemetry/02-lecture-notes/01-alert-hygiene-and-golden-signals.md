# Lecture 1 — Alert Hygiene, the Four Golden Signals, and the OpenTelemetry Data Model

> **Reading time:** ~75 minutes. **Hands-on time:** ~50 minutes (you enable the APIs, instrument a service, and see your first trace in Cloud Trace).

This is the lecture that decides whether you sleep on call. Everything technical in Week 13 — the OTel SDK, the collector, the SLO resources, the burn-rate math — is downstream of one judgment call you make over and over for the rest of your career: *does this condition warrant waking a human?* Get that judgment right and a quiet pager means the system is healthy. Get it wrong and your pager becomes background noise, you start ignoring it, and the one page that mattered dies in a sea of "disk 80% full on a node that auto-scales anyway." This lecture derives the rule that keeps the pager honest, restates the four golden signals in concrete GCP terms so you know *what* to measure, and then introduces the OpenTelemetry data model — the vendor-neutral way you actually capture all of it.

## 1.1 — The alert-hygiene rule, derived from first principles

Here is the rule, stated once, plainly:

> **Page a human only when there is user-visible risk that requires human action now. Everything else is a ticket, a dashboard, or a Slack message.**

That sentence has four load-bearing words and you must understand each.

**"User-visible"** means a person or system that depends on your service is, right now, getting a worse experience — errors, slowness, wrong answers, missing data. A CPU at 95% is not user-visible. A CPU at 95% that is causing requests to time out *is*. The CPU is a cause; the timeout is the symptom. We page on symptoms.

**"Risk"** means the bad outcome is happening or is imminent and trending the wrong way. Not "happened once at 03:00 and recovered." A single 500 in a million requests is not risk; a 500 rate that is burning your error budget fast enough to exhaust it before the month ends is risk. This is the entire reason burn-rate alerting (Lecture 2) exists — it is the math that turns "errors are happening" into "errors are happening *fast enough to matter*."

**"Requires human action"** means there is something a human can usefully do right now that automation is not already doing. If the system auto-heals — the pod restarts, the autoscaler adds capacity, the retry succeeds — then paging a human to watch it heal is theater. Page when the human is the mitigation, not when the human is a spectator.

**"Now"** means it cannot wait for business hours. If the right response is "open a ticket and look at it Tuesday," it is not a page. The bar for waking someone at 03:00 is high and it should be. Most things that feel urgent are not.

Why does this rule matter so much? Because **alerts have a cost, and the cost is paid in attention, which is finite and non-replenishable.** Every page that turns out not to need action trains the on-call engineer to trust the pager less. After enough false pages, the engineer develops a reflex: acknowledge, glance, dismiss, go back to sleep. That reflex does not distinguish the false page from the real one. Alert fatigue is not a personality flaw; it is the rational adaptation to a noisy signal. The fix is not "try harder to care" — the fix is to make the signal worth caring about by removing everything that does not meet the bar above. Google's SRE practice quantifies this: a healthy on-call rotation should receive **no more than about two actionable pages per shift**. If you are paging more than that, the problem is your alerts, not your system.

## 1.2 — Symptoms vs. causes: the distinction that organizes everything

The most common alerting mistake is **alerting on causes instead of symptoms.** It feels responsible — "I'll alert on high memory so I catch the OOM before it happens" — and it is almost always wrong. Here is why.

A symptom is something the user experiences: requests are failing, requests are slow, data is stale, the feature returns wrong answers. There are a small, stable number of symptoms for any service. They map directly to the promises you made.

A cause is a mechanism that *might* produce a symptom: high CPU, high memory, a full queue, a slow database query, a restarted pod, a deploy, a noisy neighbor, a failed health check on one of fifty replicas. There are an unbounded number of causes, they change every time you refactor, and — crucially — **most causes do not produce a symptom.** Your service runs at 90% memory all day and serves every request perfectly. Your autoscaler kills and replaces pods constantly and no user notices. If you page on every cause, you page constantly, and almost none of it is user-visible.

Worse, cause-alerting has a coverage problem in *both* directions. It over-fires (paging on causes that did not hurt anyone) **and** it under-fires (the next outage will have a cause you did not think to alert on). You cannot enumerate all the causes. You *can* enumerate the symptoms, because the symptoms are just the inverse of your service's promises. So:

- **Page on symptoms.** "The error rate is burning the budget." "p99 latency exceeds the SLO threshold and is trending up." "The pipeline's end-to-end freshness exceeds the SLO." These are few, stable, and user-visible.
- **Graph causes.** CPU, memory, queue depth, query latency, pod restarts, GC pauses — these go on dashboards. When a symptom alert fires, you open the dashboards and the *causes* tell you *why*. Causes are diagnostic, not alerting, signals.
- **Ticket the slow-moving causes.** "Disk will be full in nine days at the current growth rate" is a real problem, but it is a ticket, not a 03:00 page. "Certificate expires in 14 days" is a ticket. Automate the ticket if you can.

There is one principled exception: you may page on a cause when the cause is a near-certain leading indicator of an imminent, hard-to-recover symptom and the lead time is too short to wait for the symptom. "The disk will be full in 20 minutes and a full disk corrupts the database" is a defensible cause-page. These are rare. The default is symptom-based, and you should be able to justify every cause-page in a sentence.

## 1.3 — The four golden signals, re-stated in GCP terms

The Google SRE book names four signals that, monitored well, tell you almost everything about a service's health. They are the canonical symptom set. Here they are with the *exact* GCP-native way to measure each.

### Latency — "how long do requests take?"

Latency is the time to serve a request. The trap, made famous by Gil Tene's "How NOT to Measure Latency" talk, is averaging it: the mean latency hides the tail, and the tail is what users feel. **Measure latency as a distribution and alert on a high percentile — p95 or p99 — not the mean.**

In GCP:
- For HTTP services behind a load balancer: `loadbalancing.googleapis.com/https/backend_latencies` and `https/total_latencies` are Cloud Monitoring **distribution** metrics. You read percentiles off the distribution directly.
- For Cloud Run: `run.googleapis.com/request_latencies` (distribution).
- For your own instrumented code: an OpenTelemetry **histogram** instrument named per the semantic conventions (`http.server.request.duration`), exported to Cloud Monitoring as a distribution metric, from which you read the percentile.
- For a single slow request, the **trace** in Cloud Trace shows you *where* the time went — which span dominated the waterfall.

The latency SLI (Lecture 2) is typically "the fraction of requests served faster than X ms," which is a request-based SLI computed from the distribution.

### Traffic — "how much demand is the service under?"

Traffic is the rate of requests (or messages, or bytes). It is the denominator for everything else: a 50-error spike means nothing without knowing it was 50 out of 50 (catastrophe) or 50 out of 5 million (noise).

In GCP:
- `loadbalancing.googleapis.com/https/request_count` for LB-fronted services.
- `run.googleapis.com/request_count` for Cloud Run.
- For Pub/Sub (Week 09): `pubsub.googleapis.com/topic/send_message_operation_count` (publish rate) and `subscription/pull_message_operation_count`.
- For your own code: an OTel **counter** (`http.server.request.count`) exported as a Cloud Monitoring cumulative metric.

Traffic is rarely an alerting signal on its own (a traffic *drop* to zero can be, if it means "nobody can reach us"), but it is the context that makes every other signal interpretable. There is one traffic-based alert worth arming: a **"traffic floor"** that pages when request volume drops to near-zero on a service that should always have traffic. A sudden drop to zero usually means a layer in front of you is failing — DNS, the load balancer, an upstream that stopped calling you — and your own service looks perfectly healthy from the inside while no users can reach it. This is the rare case where the *absence* of a signal is the symptom. Use it sparingly and only on services with a predictable, non-zero traffic baseline; a batch service that is legitimately idle at night would page constantly.

The other reason to graph traffic prominently: it is the **denominator that makes a percentage honest**. A burn-rate alert (Lecture 2) divides errors by total requests; on a service doing five requests a minute, a single error is a 20% error rate and the math gets jumpy. Knowing your traffic volume tells you how much to trust a percentage-based alert and whether you need a minimum-request guard on it.

### Errors — "what fraction of requests fail?"

Errors is the rate of requests that failed — explicitly (5xx, exceptions, RPC `UNAVAILABLE`) or implicitly (wrong answer, policy violation). The implicit ones are the dangerous ones because they do not show up as a 500; you have to define them.

In GCP:
- The 5xx ratio from the LB or Cloud Run request_count metric, sliced by `response_code_class`.
- The OTel **span status**: every span carries a `status` (`OK`, `ERROR`, `UNSET`). An error rate is the fraction of root spans with status `ERROR`.
- A **log-based metric**: a counter over Cloud Logging entries matching `severity>=ERROR` for the implicit errors that never surfaced as an HTTP status.
- For Pub/Sub: `subscription/dead_letter_message_count` — events that failed processing and were dead-lettered (you built this in Week 09; now it becomes an error signal).

The errors SLI is "the fraction of requests that succeeded," and it is the most common SLO basis.

### Saturation — "how close to a limit is the service?"

Saturation is how full the most constrained resource is — CPU, memory, connection pool, queue, disk, IOPS. It is the one golden signal that is usually a *cause*, not a symptom, which is why it belongs primarily on dashboards. You alert on saturation only when (a) it is a tight leading indicator of an imminent symptom, or (b) it is itself the user-visible thing (a full queue means events are being dropped — *that* is user-visible).

In GCP:
- GKE: `kubernetes.io/container/cpu/limit_utilization`, `.../memory/limit_utilization`.
- Cloud Run: `run.googleapis.com/container/cpu/utilizations`, `.../memory/utilizations`, and `container/instance_count` against your max.
- Pub/Sub: `subscription/num_undelivered_messages` and `subscription/oldest_unacked_message_age` — backlog and lag, the saturation signal for an event pipeline.
- Database: connection-pool utilization, `cloudsql.googleapis.com/database/cpu/utilization`.

The mental model: **latency, traffic, and errors are symptoms — page on them. Saturation is usually a cause — graph it, and page only when it is a true leading indicator.**

For an event pipeline specifically (your Week 09 work), saturation deserves a closer look because it is the place where the cause/symptom line genuinely blurs. Consider `subscription/num_undelivered_messages` (the backlog) versus `subscription/oldest_unacked_message_age` (the lag). Backlog is a *cause* signal — a backlog of a few thousand messages is completely normal under bursty load and the subscriber will drain it; paging on "backlog > 0" is the noisiest alert you can write. Lag age is closer to a *symptom* — if the oldest unprocessed message is now five minutes old and your pipeline's freshness SLO promises sixty seconds, that lag is *directly* the thing your users care about (their data is stale), and it is trending the wrong way. So you graph the backlog and you alert on the lag-age-versus-SLO. Same subsystem, two metrics, two completely different alerting decisions — and the discriminator is exactly the question from §1.2: *which of these does a user actually experience?* The user does not experience a backlog; they experience stale data, which the lag age measures. This is the saturation signal done right, and it is the model the mini-project's Week 09 SLO follows.

## 1.4 — The three pillars are one model: the OpenTelemetry data model

Now: how do you actually capture latency, traffic, errors, and saturation in a way that (a) works across Python and Go, (b) correlates the signals, and (c) exports to Cloud Trace/Monitoring/Logging without locking you in? OpenTelemetry. OTel models telemetry as **three signals that share one context and one resource**: traces, metrics, and logs. They are often called "the three pillars," but that framing is misleading — the whole point of OTel is that the pillars are *stitched together*, not separate.

### Resource — the identity of the thing emitting

Every signal is tagged with a `Resource`: a set of attributes that identify the producer. The semantic conventions define the keys. At minimum:

```python
from opentelemetry.sdk.resources import Resource

resource = Resource.create({
    "service.name": "ingest-api",        # REQUIRED — the unit of SLO
    "service.version": "1.4.2",          # so you can attribute a regression to a deploy
    "deployment.environment": "prod",    # prod / staging / dev
    "cloud.provider": "gcp",
    "cloud.region": "us-central1",
})
```

`service.name` is the most important attribute in all of OpenTelemetry. It is the key by which Cloud Trace, Cloud Monitoring, and your SLOs group everything. Get it consistent across all three signals or your correlation breaks. Set it once, in the resource, and never hard-code a service name anywhere else.

### Traces — the unit of debugging

A **trace** is a tree of **spans**. A span is a single timed operation: an HTTP request, a database query, a Pub/Sub publish, a function call you chose to instrument. Each span has:

- A **trace ID** (128-bit, shared by every span in the trace) and a **span ID** (64-bit, unique to the span).
- A **parent span ID** (empty for the root span — the entry point).
- A **name** (`POST /events`, `SELECT users`), a **kind** (`SERVER`, `CLIENT`, `PRODUCER`, `CONSUMER`, `INTERNAL`), a start and end time.
- **Attributes** (key/value: `http.response.status_code=200`, `db.system=postgresql`).
- **Events** (timestamped logs attached to the span) and a **status** (`OK` / `ERROR` / `UNSET`).

Context **propagation** is what makes a trace span service boundaries. When `ingest-api` calls `enrich-service`, it injects the trace context into the outgoing request as a W3C `traceparent` HTTP header. `enrich-service` extracts it and makes its spans children of the caller's span. The result is one trace spanning both services. This is automatic if you use the OTel HTTP instrumentation on both sides — and broken the moment one service forgets to propagate. The most common "my trace is split into two traces" bug is a service that does not propagate context across an async boundary (a Pub/Sub message, a background task).

Here is a minimal manual span in Python:

```python
from opentelemetry import trace

tracer = trace.get_tracer("ingest-api")

def handle_event(event: dict) -> None:
    with tracer.start_as_current_span("handle_event") as span:
        span.set_attribute("event.type", event["type"])
        span.set_attribute("tenant.id", event["tenant"])
        try:
            _validate(event)
            _publish(event)
            span.set_status(trace.Status(trace.StatusCode.OK))
        except ValidationError as exc:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise
```

Note what we did *not* put on the span: we did not attach the full event payload. Span attributes are indexed and queried; high-cardinality, large-payload attributes blow up cost and are usually a privacy problem. Put identifiers and low-cardinality dimensions on spans; put the bulky detail in a correlated log line.

### Metrics — the unit of aggregation

A **metric** is a numeric measurement aggregated over time. OTel defines instruments:

- **Counter** — monotonically increasing (request count, bytes sent). Cumulative.
- **UpDownCounter** — can go up or down (active connections, queue depth).
- **Histogram** — records a distribution of values (request duration). This is how you get percentiles. In 2026 the default is the **exponential histogram**, which gives accurate percentiles across a wide range without you pre-choosing buckets.
- **Gauge / Observable instruments** — sampled on collection (CPU utilization, memory in use). You register a callback that reads the current value.

```python
from opentelemetry import metrics

meter = metrics.get_meter("ingest-api")
request_counter = meter.create_counter(
    "ingest.requests",
    unit="1",
    description="Count of ingest requests by outcome",
)
request_duration = meter.create_histogram(
    "ingest.request.duration",
    unit="ms",
    description="Ingest request duration",
)

def record(outcome: str, duration_ms: float, event_type: str) -> None:
    attrs = {"outcome": outcome, "event.type": event_type}
    request_counter.add(1, attrs)
    request_duration.record(duration_ms, attrs)
```

Metric **attributes** (the dict above) are dimensions you can slice by in Cloud Monitoring. Keep cardinality bounded: `outcome` has three values, `event.type` has a dozen — fine. `tenant.id` with 50,000 tenants as a *metric* attribute is a cost bomb; that dimension belongs on traces and logs, not on a metric. This is the single most expensive observability mistake teams make, and Cloud Monitoring will bill you for it.

### Logs — the unit of evidence

A **log record** in OTel is a structured event with a timestamp, severity, body, attributes, and — critically — the trace ID and span ID of the active span when it was emitted. That last part is the correlation glue. When you emit a log inside an active span, the SDK stamps the trace/span ID onto the log record. Cloud Logging stores those in `logging.googleapis.com/trace` and `spanId`, and Cloud Trace shows the log lines inline on the span. One click from "this request was slow" to "here is exactly what it logged."

In Python the cleanest path in 2026 is the logging bridge plus structured logging to stdout, which Cloud Run/GKE's logging agent picks up:

```python
import logging
import json

class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context()
        payload = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logging.googleapis.com/trace":
                f"projects/{PROJECT}/traces/{ctx.trace_id:032x}" if ctx.trace_id else None,
            "logging.googleapis.com/spanId":
                f"{ctx.span_id:016x}" if ctx.span_id else None,
        }
        return json.dumps({k: v for k, v in payload.items() if v is not None})
```

The exact field names matter: `logging.googleapis.com/trace` must be the full resource path `projects/PROJECT/traces/TRACE_ID` (hex, 32 chars) and `logging.googleapis.com/spanId` the 16-char hex span ID, or Cloud Logging will not link them. Get these wrong and your logs and traces are two disconnected datasets. Get them right and you have the single most useful debugging affordance in the whole stack.

## 1.5 — Why a collector, and why OTLP

You can export from the SDK directly to Cloud Trace/Monitoring (the `opentelemetry-exporter-gcp-*` packages do exactly that). For a single service learning the ropes, that is fine, and Exercise 1 does it. For a *fleet*, you put an **OpenTelemetry Collector** in the path:

- Services export OTLP (the OTel wire protocol) to the collector.
- The collector batches, samples, redacts, enriches, and exports to the `googlecloud` exporter (and anywhere else).
- Fleet-wide policy — sampling rate, what to drop, where to send — lives in the collector config, not in fifty services' code.

The deployment patterns: an **agent** collector (sidecar on Cloud Run, DaemonSet on GKE) that each service talks to over localhost, and optionally a **gateway** collector (a central deployment) the agents forward to for org-wide processing. We run the agent pattern this week; the gateway is a stretch goal.

The reason this matters for the course's standing rule — name the exit — is that the collector *is* the exit. Your code emits OTLP. Today the collector's exporter says `googlecloud`. Tomorrow it says `otlp` pointed at Grafana Tempo, or `prometheus`, or `loki`. Your fifty services never change. That is the entire value proposition of OpenTelemetry, and it is why we instrument against it instead of against the Cloud Trace SDK directly.

## 1.6 — Sampling, and why observability has a cost you must budget

Traces are not free. A high-traffic service producing a span for every request, every database call, and every outbound HTTP call generates an enormous volume of spans, and Cloud Trace bills per span ingested past the free tier. Metrics with bounded cardinality are cheap; logs at full fidelity are the expensive one (Cloud Logging bills per GiB ingested, and a chatty service at full debug level will surprise you on the invoice). So part of instrumenting correctly is deciding *how much* to keep. That decision is **sampling**, and getting it wrong in either direction is a classic mistake: sample too aggressively and the one trace you need at 03:00 was dropped; sample too little and you pay for millions of identical happy-path traces nobody will ever look at.

There are two sampling strategies, and you should understand both:

- **Head-based sampling** decides at the *start* of a trace, in the SDK, whether to keep it — before you know whether anything interesting happened. The OTel `TraceIdRatioBased` sampler keeps a fixed fraction (say 10%) deterministically by trace ID, so a sampled trace is sampled consistently across every service it touches (the decision propagates in the `traceparent` flags). It is cheap and simple. Its weakness is that it is blind: a 10% sampler keeps 10% of your errors *and* 10% of your boring successes, when you would happily keep 100% of the errors and 1% of the successes.

- **Tail-based sampling** decides at the *end* of a trace, after all spans are collected, when you know the outcome — so you can keep 100% of traces that errored or exceeded a latency threshold and a small fraction of the rest. It cannot live in the SDK (the SDK does not see the whole trace), so it lives in the **collector**, which buffers spans until the trace completes and then applies a policy. This is the production default for any service where the happy path dominates: keep all the interesting traces, sample the boring ones.

```python
# Head-based: keep 10% of traces, decided in the SDK, propagated downstream.
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased

sampler = ParentBased(root=TraceIdRatioBased(0.10))
tracer_provider = TracerProvider(resource=resource, sampler=sampler)
```

The `ParentBased` wrapper matters: it says "respect the parent's sampling decision if there is one, and only apply the ratio at the root." Without it, each service re-rolls the dice and you get traces that are sampled in service A but dropped in service B — broken, half-present traces, the worst of both worlds. Always wrap your root sampler in `ParentBased`.

Tail-based sampling is configured in the collector (we deploy it in the mini-project), and the policy reads naturally:

```yaml
# collector snippet: keep all errors + slow traces, sample 5% of the rest.
processors:
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: keep-errors
        type: status_code
        status_code: { status_codes: [ERROR] }
      - name: keep-slow
        type: latency
        latency: { threshold_ms: 500 }
      - name: sample-the-rest
        type: probabilistic
        probabilistic: { sampling_percentage: 5 }
```

The mental model to carry: **you sample traces, you do not sample SLO metrics.** Your error-rate and latency SLIs must be computed from *unsampled* metrics (the counter and histogram every request increments), because an SLO computed from a 10% trace sample is a 10×-noisier SLO. Sample the expensive narrative data (traces, debug logs); keep the cheap aggregate data (metrics, error logs) at full fidelity. This is the division that keeps the observability bill sane without blinding you when it matters. We return to it in the mini-project, where fleet-wide sampling policy is exactly the thing the collector exists to own.

## 1.6a — The OpenTelemetry SDK in Go

Everything in §1.4–§1.6 was illustrated in Python, but the data model is language-agnostic by design — that is the whole point of the semantic conventions. Half the fleet you instrument in the mini-project is Go (your Week 06 GKE workloads and the Go services in the Week 09 pipeline), and Go's SDK is different enough from Python's that it deserves its own walk-through. The concepts map one-to-one — `Resource`, `TracerProvider`, `MeterProvider`, OTLP exporter, propagation, auto + manual instrumentation — but the ergonomics do not. Two differences dominate:

1. **Go is explicit about shutdown and errors.** Python's SDK hides the provider behind module-level globals you set once. Go hands you the provider object and expects *you* to call `Shutdown(ctx)` to flush the batch before the process exits — forget it and your last spans never leave the process. The idiomatic pattern is to return a single `shutdown` func from your bootstrap and `defer` it in `main`.
2. **`context.Context` carries the trace, everywhere.** In Python the active span lives in a context-var the SDK manages implicitly; in Go the active span lives in the `context.Context` you thread through every function call by hand. If a function does not take a `ctx` and pass it down, its spans are orphaned (no parent) and propagation across an outbound call silently breaks. The rule is the same rule you already follow for cancellation and deadlines: **`ctx` is the first argument and you pass it down.** OTel piggybacks on it.

The versions we target in 2026 (pin them; they move in lockstep within a release train): the core API/SDK `go.opentelemetry.io/otel` **v1.44.0**, the metric/log SDK components on the matching minor, and the contrib instrumentation `go.opentelemetry.io/contrib/instrumentation/...` at **v0.66.0** (contrib tracks core but with a `0.` major while the instrumentation APIs stabilize). The Google Cloud exporters live in `github.com/GoogleCloudPlatform/opentelemetry-operations-go/exporter/{trace,metric}`. Exact versions are in `resources.md`.

### The bootstrap: providers, OTLP exporter, propagator

Here is the Go equivalent of the Python `telemetry.py` bootstrap from Exercise 1, but exporting **OTLP to a collector** (the fleet path from §1.5) rather than direct-to-GCP — Go is where you most often run the collector sidecar, so we show that path here and the direct-to-GCP exporters in the exercise. The function builds the `Resource`, a `TracerProvider` with a `BatchSpanProcessor`, a `MeterProvider` with a periodic reader, installs the W3C propagator, and returns a single `shutdown` func that flushes both.

```go
// telemetry.go — OpenTelemetry bootstrap for traces + metrics → OTLP collector.
package main

import (
	"context"
	"errors"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	"go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

// initTelemetry wires traces + metrics to the OTLP endpoint (the collector,
// e.g. a localhost:4317 sidecar) and returns a shutdown func to flush on exit.
func initTelemetry(ctx context.Context, serviceName, serviceVersion string) (func(context.Context) error, error) {
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName(serviceName),       // REQUIRED — the unit of SLO.
			semconv.ServiceVersion(serviceVersion), // attribute a regression to a deploy.
			semconv.DeploymentEnvironmentName("prod"),
		),
		resource.WithFromEnv(),   // picks up OTEL_RESOURCE_ATTRIBUTES.
		resource.WithTelemetrySDK(),
	)
	if err != nil {
		return nil, err
	}

	// Traces → OTLP/gRPC. WithInsecure() because the sidecar is on localhost;
	// in production the collector terminates TLS or you run over a UDS.
	traceExp, err := otlptracegrpc.New(ctx, otlptracegrpc.WithInsecure())
	if err != nil {
		return nil, err
	}
	tp := trace.NewTracerProvider(
		trace.WithResource(res),
		trace.WithBatcher(traceExp), // the BatchSpanProcessor equivalent.
		// Head-based sampling, ParentBased so the decision propagates (see §1.6).
		trace.WithSampler(trace.ParentBased(trace.TraceIDRatioBased(0.10))),
	)
	otel.SetTracerProvider(tp)

	// Metrics → OTLP/gRPC, exported every 30s.
	metricExp, err := otlpmetricgrpc.New(ctx, otlpmetricgrpc.WithInsecure())
	if err != nil {
		return nil, err
	}
	mp := metric.NewMeterProvider(
		metric.WithResource(res),
		metric.WithReader(metric.NewPeriodicReader(metricExp,
			metric.WithInterval(30*time.Second))),
	)
	otel.SetMeterProvider(mp)

	// The propagator: W3C traceparent + baggage. Without this, context does NOT
	// cross service boundaries and your traces split — the §1.4 propagation bug.
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	// One shutdown func that flushes both providers. defer this in main().
	return func(ctx context.Context) error {
		return errors.Join(tp.Shutdown(ctx), mp.Shutdown(ctx))
	}, nil
}
```

Three things to notice, each a direct analogue of a Python point made above:

- **`otel.SetTracerProvider` / `SetMeterProvider`** install the global the way `trace.set_tracer_provider` did in Python. Library code then calls `otel.Tracer("name")` and gets the configured provider — the same global-lookup pattern, so instrumentation libraries you did not write find your provider automatically.
- **`trace.WithBatcher`** is the Go name for the `BatchSpanProcessor`: it buffers spans and ships them in batches instead of one network call per span. `trace.WithSyncer` (one call per span) exists only for tests.
- **The propagator is not installed by default.** This is the single most common Go OTel bug: you set up providers, spans appear, but every service starts a *new* trace because nobody called `SetTextMapPropagator`. Install the W3C `TraceContext` propagator explicitly, or context does not cross the wire and §1.4's distributed trace never forms.

### Auto-instrumentation: `otelhttp` and `otelgrpc`

Just like Python's `FastAPIInstrumentor`, Go's contrib packages give you the boundary spans (§1.9) for almost free. For `net/http`, you wrap your handler (server side) and your `http.Client`'s transport (client side):

```go
import "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"

// SERVER span per request, named by the route. otelhttp also extracts the
// incoming traceparent header and makes the handler's spans children of it.
handler := otelhttp.NewHandler(mux, "ingest-api")
http.ListenAndServe(":8080", handler)

// CLIENT span per outbound call, and it INJECTS the traceparent header so the
// downstream service continues the same trace — the propagation glue from §1.4.
client := &http.Client{Transport: otelhttp.NewTransport(http.DefaultTransport)}
```

For gRPC services (your Week 09 enrichers talk gRPC), the equivalent is a one-line interceptor on both ends using the new stats-handler API:

```go
import (
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"google.golang.org/grpc"
	"google.golang.org/grpc/stats"
)

// Server: a stats handler gives you a SERVER span per RPC.
srv := grpc.NewServer(grpc.StatsHandler(otelgrpc.NewServerHandler()))

// Client: a stats handler gives you a CLIENT span per RPC and propagates context.
conn, _ := grpc.NewClient(target,
	grpc.WithStatsHandler(otelgrpc.NewClientHandler()))
```

That is the whole boundary layer for a Go service: `otelhttp` on the HTTP edges, `otelgrpc` on the gRPC edges, and because both honour the propagator you installed in the bootstrap, a request that enters `ingest-api` over HTTP and fans out to `enrich-service` over gRPC is **one trace**, exactly as §1.4 requires.

### Manual spans, a histogram, and the `slog` log bridge

Hand-written spans are the Go mirror of the Python `start_as_current_span` block — note the `ctx` threading and the explicit `defer span.End()`, which is the Go equivalent of the Python `with` block closing the span:

```go
var tracer = otel.Tracer("ingest-api")
var meter  = otel.Meter("ingest-api")

// One histogram, created once at startup (do NOT create instruments per request).
requestDuration, _ := meter.Int64Histogram(
	"ingest.request.duration",
	otelmetric.WithUnit("ms"),
	otelmetric.WithDescription("Ingest request duration"),
)

func handleEvent(ctx context.Context, ev Event) (err error) {
	// ctx carries the parent span; this span becomes its child. Thread ctx down.
	ctx, span := tracer.Start(ctx, "handle_event")
	defer span.End() // the Go equivalent of leaving the `with` block.

	span.SetAttributes(
		attribute.String("event.type", ev.Type),
		attribute.String("tenant.id", ev.Tenant), // identifier, low-ish cardinality: OK on a span.
	)

	start := time.Now()
	defer func() {
		// Record the metric with bounded-cardinality attributes only.
		outcome := "ok"
		if err != nil {
			outcome = "error"
		}
		requestDuration.Record(ctx, time.Since(start).Milliseconds(),
			otelmetric.WithAttributes(attribute.String("outcome", outcome)))
	}()

	if err = validate(ev); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return err
	}
	span.SetStatus(codes.Ok, "")
	return nil
}
```

The same cardinality discipline from §1.4 applies and Go does nothing to protect you from violating it: `tenant.id` as a *span* attribute is fine (spans are sampled and not aggregated); `tenant.id` as a *metric* attribute would explode your Cloud Monitoring bill exactly as it would in Python. Put identifiers on spans, bounded dimensions (`outcome`) on metrics.

For logs, the 2026-idiomatic Go path is the **`slog` bridge** — `otelslog` — which routes Go's standard structured logger through the OTel `LoggerProvider` so log records carry the active trace/span ID automatically, the §1.4 correlation glue, without the hand-rolled formatter the Python example needed:

```go
import (
	"go.opentelemetry.io/contrib/bridges/otelslog"
	otellog "go.opentelemetry.io/otel/sdk/log"
	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc"
)

// In the bootstrap: a LoggerProvider whose records ship over OTLP.
logExp, _ := otlploggrpc.New(ctx, otlploggrpc.WithInsecure())
lp := otellog.NewLoggerProvider(
	otellog.WithResource(res),
	otellog.WithProcessor(otellog.NewBatchProcessor(logExp)),
)
global.SetLoggerProvider(lp) // from go.opentelemetry.io/otel/log/global

// Then make slog write through the bridge:
logger := otelslog.NewLogger("ingest-api")

// Anywhere you have a ctx with an active span, the trace_id/span_id are attached:
logger.InfoContext(ctx, "event accepted", "event.type", ev.Type, "tenant.id", ev.Tenant)
```

The critical detail mirrors the Python one: pass the **`ctx` that holds the active span** (`InfoContext`, not `Info`), or the bridge has no span to read and the log line lands uncorrelated. When this works, the collector's `googlecloud` exporter maps the OTLP log record's trace ID onto Cloud Logging's `logging.googleapis.com/trace` field for you — you do not hand-format it as the Python stdout path did, because the OTLP-to-Cloud-Logging mapping is the collector's job. That is one more reason the Go fleet leans on the collector path: it owns the field-name mapping §1.4 warned you to get exactly right.

### The complete runnable example

Putting it together — a minimal HTTP service that is fully instrumented (boundary span from `otelhttp`, a manual child span, a histogram, correlated logs) and flushes cleanly on shutdown. This is the Go analogue of the §1.7 Python `tracedemo`, and it is the skeleton Exercise 4 builds on.

```go
// main.go — run: go run . ; then curl localhost:8080/work a few times.
// Requires a collector on localhost:4317 (or set OTEL_EXPORTER_OTLP_ENDPOINT).
package main

import (
	"context"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"time"

	"go.opentelemetry.io/contrib/bridges/otelslog"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	otelmetric "go.opentelemetry.io/otel/metric"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	shutdown, err := initTelemetry(ctx, "otel-ex04", "0.1.0")
	if err != nil {
		panic(err)
	}
	// Flush spans + metrics before exit. Without this you lose the last batch.
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = shutdown(shutdownCtx)
	}()

	tracer := otel.Tracer("otel-ex04")
	meter := otel.Meter("otel-ex04")
	logger := otelslog.NewLogger("otel-ex04")

	workDuration, _ := meter.Float64Histogram("ex04.work.duration",
		otelmetric.WithUnit("ms"), otelmetric.WithDescription("Duration of /work"))

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"status":"ok"}`))
	})
	mux.HandleFunc("/work", func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context() // carries the SERVER span otelhttp started.
		start := time.Now()

		// A manual child span around the "compute" — the §1.9 internal span.
		_, span := tracer.Start(ctx, "compute")
		sleep := time.Duration(10+rand.Intn(40)) * time.Millisecond
		span.SetAttributes(attribute.Int64("compute.sleep_ms", sleep.Milliseconds()))
		time.Sleep(sleep)
		span.SetStatus(codes.Ok, "")
		span.End()

		workDuration.Record(ctx, float64(time.Since(start).Milliseconds()),
			otelmetric.WithAttributes(attribute.String("outcome", "ok")))
		logger.InfoContext(ctx, "work done", "sleep_ms", sleep.Milliseconds())
		w.Write([]byte(`{"ok":true}`))
	})

	// otelhttp wraps the mux: a SERVER span per request, named "http.server".
	srv := &http.Server{Addr: ":8080", Handler: otelhttp.NewHandler(mux, "http.server")}
	go func() { _ = srv.ListenAndServe() }()

	<-ctx.Done() // wait for Ctrl-C, then the deferred shutdown flushes telemetry.
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutdownCtx)
}
```

Run a collector locally, `go run .`, hit `/work` a dozen times, and you get the same three-layer waterfall the Python service produced — a `http.server` SERVER span, a `compute` INTERNAL child, and the histogram and correlated logs alongside — proving the data model really is one model across both languages. Exercise 4 turns this skeleton into a service exporting to GCP, the Go mirror of Exercise 1.

## 1.7 — Hands-on: enable the APIs and see your first trace

Enable the observability APIs with Terraform (do this before the exercises):

```hcl
# observability-apis.tf
locals {
  observability_apis = [
    "cloudtrace.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "cloudprofiler.googleapis.com",
  ]
}

resource "google_project_service" "observability" {
  for_each           = toset(local.observability_apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
```

Then the smallest possible instrumented Python service, exporting traces directly to Cloud Trace:

```python
# tracedemo.py — run: python tracedemo.py, then open Cloud Trace.
import os
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

resource = Resource.create({"service.name": "tracedemo"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("tracedemo")

with tracer.start_as_current_span("root") as root:
    root.set_attribute("demo", True)
    with tracer.start_as_current_span("child-work") as child:
        child.set_attribute("step", "compute")
    with tracer.start_as_current_span("child-io") as child:
        child.set_attribute("step", "write")

provider.shutdown()  # flush the batch before exit
print("Trace exported. Open Cloud Trace and look for service 'tracedemo'.")
```

Run it (`GOOGLE_CLOUD_PROJECT` set, ADC configured), wait ten seconds for the batch to flush, and open Cloud Trace. You will see one trace named `root` with two child spans, `child-work` and `child-io`, in a waterfall. That waterfall is the unit of debugging. Everything else this week is making more of those, correlating them with logs and metrics, and deciding which of them, in aggregate, is allowed to wake you up.

## 1.8 — The audit you will do this week

Before you write a single new alert, you will audit whatever alerts your Week 06–12 services already have (probably none, or a couple of console-clicked "CPU > 80%" alerts). For each, you classify it:

| Alert | Symptom or cause? | Keep as page / demote to ticket / move to dashboard |
|-------|-------------------|-----------------------------------------------------|
| "CPU > 80% for 5 min" | Cause | Dashboard. Not user-visible on its own. |
| "Pod restarted" | Cause | Dashboard (or ticket if it loops). Auto-heals. |
| "5xx rate burning error budget at 14×" | Symptom | **Page.** |
| "Pub/Sub backlog > 0 for 1 min" | Cause (and noisy) | Dashboard. Backlog is normal; alert on *lag age* trending past SLO. |
| "Certificate expires in 14 days" | Cause, slow | Ticket (automate it). |
| "p99 latency > SLO threshold, fast burn" | Symptom | **Page.** |

This table is the deliverable of the homework's audit problem, and it is the mindset the whole week trains. Two pages per shift, both actionable, both user-visible. Everything else lives somewhere quieter.

## Summary

- **Page only on user-visible risk that needs human action now.** Everything else is a ticket, a dashboard, or a Slack message. Attention is finite; protect it.
- **Page on symptoms, graph causes.** Symptoms are few and stable (the inverse of your promises); causes are unbounded and mostly harmless. The exception — a tight leading indicator — is rare and must be justified.
- **The four golden signals are your symptom set:** latency (distribution, percentile), traffic (rate, the denominator), errors (failure fraction), saturation (usually a cause — graph it). Each maps to a specific Cloud Monitoring metric, span attribute, or log filter.
- **OpenTelemetry models traces, metrics, and logs as one correlated model** sharing a `Resource` and a propagated context. `service.name` is the key that ties them together. Trace/span IDs on log records are the correlation glue; get the `logging.googleapis.com/trace` field exactly right.
- **Instrument against OTel and export via a collector** so the backend is replaceable — that is the named exit from Cloud Trace/Monitoring/Logging.
- **Sample traces (the expensive narrative), keep metrics and error logs at full fidelity (the cheap aggregate).** Wrap your root sampler in `ParentBased` so the decision propagates and traces are not half-present. Compute SLOs from unsampled metrics, never from a trace sample.
- **Instrument the boundaries before the internals.** SERVER + CLIENT spans across the fleet give you the request topology for almost nothing; that is the data your golden signals and SLOs feed on. Breadth first, depth second.

The throughline of this lecture is a single discipline: decide what matters to the user, measure exactly that as close to the user as you can, page only when it is genuinely at risk, and make everything else available — on a dashboard, in a trace, in a log — for the moment you need it. The next lecture makes "genuinely at risk" precise. But the judgment you practiced here — symptom versus cause, page versus ticket versus dashboard — is the part you will use every day for the rest of your career, on every system you ever own. The tools change; the judgment does not.

## 1.9 — One more thing: instrument the boundaries first

If you take only one tactical instruction from this lecture into the challenge, take this: **instrument the boundaries of your system before you instrument the insides.** The boundaries are where the truth lives. A SERVER span at the entry point of each service plus a CLIENT span at each outbound call gives you, almost for free, the entire request topology — who calls whom, where the time goes, where the errors originate — and it is exactly the data your golden-signal metrics and your SLOs are computed from. The auto-instrumentation libraries (the FastAPI/Flask/`requests`/gRPC instrumentors in Python, `otelhttp`/`otelgrpc` in Go) give you those boundary spans with one line of setup each. Do that across the fleet first. Only *then* add the hand-written internal spans for the specific operations you suspect, the custom metrics for your domain outcomes, and the structured logs for the events that matter. Teams that do it the other way around — lovingly hand-instrumenting one service's internals while the boundaries between services are dark — end up with deep visibility into one box and no idea how requests flow between boxes, which is precisely backwards for debugging a distributed system. Breadth at the boundaries beats depth in the internals, every time, when you are starting from nothing. That ordering is what makes the "instrument the whole fleet in a week" challenge actually achievable.

In Lecture 2 we turn "page on the error symptom" into the precise mechanism that does it without paging on noise: the SLO, the error budget, and the multi-window multi-burn-rate alert.
