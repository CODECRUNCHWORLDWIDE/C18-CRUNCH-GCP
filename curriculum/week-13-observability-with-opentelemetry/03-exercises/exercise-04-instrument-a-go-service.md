# Exercise 4 — Instrument a Go service with OpenTelemetry and export to Cloud Trace + Cloud Monitoring

> **Goal:** Take a plain `net/http` Go service, add OpenTelemetry traces and metrics, export them to Cloud Trace and Cloud Monitoring, and see a correlated trace with a custom metric — in **under an hour**. This is the same syllabus skill as Exercise 1, in the other half of the fleet's language stack: "Add OTel instrumentation to a Python/Go service in under an hour."
>
> **Estimated time:** 60 minutes.

This is the Go mirror of Exercise 1. You build a real `net/http` service, instrument it two ways (zero-effort middleware auto-instrumentation *and* a hand-written span + metric), export to GCP, and confirm the data landed. The starter and the full solution are both here; type the solution, do not paste it — the muscle memory is the point. If you did Exercise 1, the structure will feel familiar on purpose: same three-span waterfall, same custom histogram + counter, same acceptance criteria. The differences are the ones Lecture 1 §1.6a calls out — explicit `ctx` threading, an explicit `shutdown` you must `defer`, and the propagator you must install yourself.

## Prerequisites

- `GOOGLE_CLOUD_PROJECT` set to your project; `gcloud auth application-default login` done.
- The APIs from Lecture 1 enabled (`cloudtrace`, `monitoring`, `logging`).
- Go 1.23+.

We export **directly to GCP** in this exercise (the `opentelemetry-operations-go` trace + metric exporters) to keep the moving parts minimal — the same choice Exercise 1 made for the same reason. The mini-project switches the Go services to the OTLP-to-collector path shown in Lecture 1 §1.6a. Both are valid; this is the faster on-ramp.

## Step 0 — Scaffold

```bash
mkdir otel-ex04 && cd otel-ex04
go mod init otel-ex04
go get \
  go.opentelemetry.io/otel@v1.44.0 \
  go.opentelemetry.io/otel/sdk@v1.44.0 \
  go.opentelemetry.io/otel/sdk/metric@v1.44.0 \
  go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp@v0.66.0 \
  github.com/GoogleCloudPlatform/opentelemetry-operations-go/exporter/trace@latest \
  github.com/GoogleCloudPlatform/opentelemetry-operations-go/exporter/metric@latest
```

(Exact versions are pinned in `resources.md`; `go get` resolves the GCP exporters to their current release. If `go build` later complains about a missing indirect dependency, run `go mod tidy` and it will be added.)

## Step 1 — The uninstrumented service (the starting point)

Create `main.go`. This is a service that does a tiny bit of "work" and an outbound HTTP call, so the trace has something interesting in it — the Go counterpart of Exercise 1's FastAPI starter:

```go
// main.go — starting point, no instrumentation yet.
package main

import (
	"encoding/json"
	"io"
	"math/rand"
	"net/http"
	"time"
)

func work(w http.ResponseWriter, r *http.Request) {
	// Simulate some CPU work.
	time.Sleep(time.Duration(10+rand.Intn(40)) * time.Millisecond)

	// An outbound call we want to see as a child span.
	resp, err := http.Get("https://www.googleapis.com/discovery/v1/apis")
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	var parsed struct {
		Items []json.RawMessage `json:"items"`
	}
	_ = json.Unmarshal(body, &parsed)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"apis_listed": len(parsed.Items), "ok": true,
	})
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	mux.HandleFunc("/work", work)
	_ = http.ListenAndServe(":8080", mux)
}
```

Run it (`go run .`), hit `http://localhost:8080/work`, confirm it returns JSON. Now it works but tells you nothing. We instrument it.

## Step 2 — Wire the providers (the telemetry bootstrap)

Create `telemetry.go`. This is the reusable bootstrap you copy into every Go service in the mini-project. It builds the `Resource`, the `TracerProvider`, and the `MeterProvider`, points both at GCP, installs the W3C propagator, and — the Go-specific part Lecture 1 §1.6a stressed — returns a single `shutdown` func you must `defer` so the last batch flushes.

```go
// telemetry.go — OpenTelemetry bootstrap for traces + metrics → GCP.
package main

import (
	"context"
	"errors"
	"os"
	"time"

	traceexporter "github.com/GoogleCloudPlatform/opentelemetry-operations-go/exporter/trace"
	mexporter "github.com/GoogleCloudPlatform/opentelemetry-operations-go/exporter/metric"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	"go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

func serviceName() string {
	if n := os.Getenv("OTEL_SERVICE_NAME"); n != "" {
		return n
	}
	return "otel-ex04"
}

// initTelemetry wires traces → Cloud Trace and metrics → Cloud Monitoring,
// and returns a shutdown func to flush on exit. defer it in main().
func initTelemetry(ctx context.Context) (func(context.Context) error, error) {
	projectID := os.Getenv("GOOGLE_CLOUD_PROJECT")

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName(serviceName()), // REQUIRED — the unit of SLO.
			semconv.ServiceVersion(env("SERVICE_VERSION", "0.1.0")),
			semconv.DeploymentEnvironmentName(env("ENVIRONMENT", "dev")),
		),
		resource.WithTelemetrySDK(),
	)
	if err != nil {
		return nil, err
	}

	// Traces → Cloud Trace.
	traceExp, err := traceexporter.New(traceexporter.WithProjectID(projectID))
	if err != nil {
		return nil, err
	}
	tp := trace.NewTracerProvider(
		trace.WithResource(res),
		trace.WithBatcher(traceExp), // the BatchSpanProcessor equivalent.
	)
	otel.SetTracerProvider(tp)

	// Metrics → Cloud Monitoring, exported every 30s.
	metricExp, err := mexporter.New(mexporter.WithProjectID(projectID))
	if err != nil {
		return nil, err
	}
	mp := metric.NewMeterProvider(
		metric.WithResource(res),
		metric.WithReader(metric.NewPeriodicReader(metricExp,
			metric.WithInterval(30*time.Second))),
	)
	otel.SetMeterProvider(mp)

	// W3C propagator so context crosses service boundaries (see Lecture 1 §1.4/§1.6a).
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{}, propagation.Baggage{},
	))

	return func(ctx context.Context) error {
		return errors.Join(tp.Shutdown(ctx), mp.Shutdown(ctx))
	}, nil
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
```

## Step 3 — Auto-instrument with `otelhttp`, add one manual span and one metric

Replace `main.go` with the instrumented version. Three things happen, mirroring Exercise 1 Step 3: (1) `initTelemetry()` runs in `main` and its `shutdown` is `defer`-ed; (2) `otelhttp.NewHandler` wraps the mux for a SERVER span per request, and `otelhttp.NewTransport` wraps the outbound client for a CLIENT span per call — the Go equivalents of `FastAPIInstrumentor` + `RequestsInstrumentor`; (3) we add a manual child span around the "compute" and a custom histogram + counter for its outcome.

```go
// main.go — instrumented.
package main

import (
	"context"
	"encoding/json"
	"io"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	otelmetric "go.opentelemetry.io/otel/metric"
)

var (
	tracer       = otel.Tracer(serviceName())
	meter        = otel.Meter(serviceName())
	httpClient   = &http.Client{Transport: otelhttp.NewTransport(http.DefaultTransport)}
	workDuration otelmetric.Float64Histogram
	workCount    otelmetric.Int64Counter
)

func work(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context() // carries the SERVER span otelhttp started.
	start := time.Now()
	outcome := "ok"
	defer func() {
		elapsed := float64(time.Since(start).Milliseconds())
		attrs := otelmetric.WithAttributes(attribute.String("outcome", outcome))
		workDuration.Record(ctx, elapsed, attrs)
		workCount.Add(ctx, 1, attrs)
	}()

	// Manual child span around the "compute". ctx threads the parent down.
	computeCtx, span := tracer.Start(ctx, "compute")
	sleep := time.Duration(10+rand.Intn(40)) * time.Millisecond
	span.SetAttributes(attribute.Int64("compute.sleep_ms", sleep.Milliseconds()))
	time.Sleep(sleep)
	span.SetStatus(codes.Ok, "")
	span.End()

	// otelhttp.NewTransport turns this into a CLIENT child span automatically,
	// and propagates the traceparent header. Pass computeCtx (carries the trace).
	req, _ := http.NewRequestWithContext(computeCtx, http.MethodGet,
		"https://www.googleapis.com/discovery/v1/apis", nil)
	resp, err := httpClient.Do(req)
	if err != nil {
		outcome = "error"
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	var parsed struct {
		Items []json.RawMessage `json:"items"`
	}
	_ = json.Unmarshal(body, &parsed)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"apis_listed": len(parsed.Items), "ok": true,
	})
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	shutdown, err := initTelemetry(ctx)
	if err != nil {
		panic(err)
	}
	// Flush spans + metrics before exit. Without this you lose the last batch.
	defer func() {
		sCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = shutdown(sCtx)
	}()

	workDuration, _ = meter.Float64Histogram("ex04.work.duration",
		otelmetric.WithUnit("ms"),
		otelmetric.WithDescription("Duration of the /work handler"))
	workCount, _ = meter.Int64Counter("ex04.work.count",
		otelmetric.WithUnit("1"),
		otelmetric.WithDescription("Count of /work calls by outcome"))

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	mux.HandleFunc("/work", work)

	// otelhttp wraps the mux: a SERVER span per request.
	srv := &http.Server{Addr: ":8080", Handler: otelhttp.NewHandler(mux, "http.server")}
	go func() { _ = srv.ListenAndServe() }()

	<-ctx.Done() // wait for Ctrl-C; then the deferred shutdown flushes telemetry.
	sCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(sCtx)
}
```

> **Ordering gotcha (the Go version of Exercise 1's "init before instrument").** `tracer` and `meter` are package-level vars initialised at import via `otel.Tracer/Meter`, which return *no-op* providers until `otel.SetTracerProvider/SetMeterProvider` run inside `initTelemetry`. That is fine here because spans/metrics are only *recorded* at request time, long after `main` calls `initTelemetry`. But never *record* a span or metric before `initTelemetry` returns, or it silently goes to the no-op provider — "no data, no error," the same confusing failure mode Exercise 1 warns about.

## Step 4 — Run it and generate traffic

```bash
export GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"
export OTEL_SERVICE_NAME="otel-ex04"
go run . &
# Hit /work 40 times so there is a metric distribution and several traces.
for i in $(seq 1 40); do curl -s localhost:8080/work > /dev/null; done
# Give the batch/periodic exporters time to flush.
sleep 35
```

## Step 5 — Confirm the data landed

**Cloud Trace.** Open Cloud Trace, filter by service `otel-ex04`. You should see traces for `/work`, each a waterfall:

```
http.server  (SERVER span, ~45ms)            ← named by otelhttp
├── compute                  (INTERNAL span, ~10-50ms, attr compute.sleep_ms)
└── HTTP GET                 (CLIENT span, the googleapis call)
```

The nesting is the proof your manual span and the auto-instrumented client span share the request's context — exactly the §1.4 propagation working end to end inside one process.

**Cloud Monitoring.** In Metrics Explorer, search for `workload.googleapis.com/ex04.work.duration` (the GCP metric exporter maps OTel instrument names into the `workload.googleapis.com/` prefix). You should see a distribution metric; switch the aligner to "99th percentile" and you have your latency SLI source. Search `ex04.work.count` and slice by the `outcome` label.

## Expected output

The terminal shows 40 successful `/work` responses. Cloud Trace shows ~40 traces for service `otel-ex04`, each with the three-span waterfall above. Metrics Explorer shows `ex04.work.duration` as a distribution and `ex04.work.count` with an `outcome=ok` series at 40.

A representative trace summary (your latencies will differ):

```
Trace 9b2c... | otel-ex04 | http.server /work | 46.8 ms
  ├─ compute        14.0 ms   compute.sleep_ms=14
  └─ HTTP GET       32.1 ms   http.request.method=GET
                              url.full=https://www.googleapis.com/discovery/v1/apis
                              http.response.status_code=200
```

## Acceptance criteria

- [ ] `GET /work` returns JSON and the service runs without errors.
- [ ] Cloud Trace shows traces for service `otel-ex04` with a SERVER span (`http.server`), a nested `compute` INTERNAL span, and a CLIENT span for the outbound call — all in **one** trace.
- [ ] The `compute` span carries the `compute.sleep_ms` attribute.
- [ ] Cloud Monitoring shows the `ex04.work.duration` distribution metric and the `ex04.work.count` counter with an `outcome` label.
- [ ] You `defer`-ed the `shutdown` func and the last batch flushed (no spans lost on exit).
- [ ] You did the whole thing — scaffold to confirmed data — in under 60 minutes. (Time yourself. This is the skill.)

## Teardown

Nothing persistent is created in GCP by this exercise except the telemetry data itself, which ages out per the default retention (30 days for traces; custom metrics stop accruing the moment you stop the service). Stop the server (Ctrl-C, or `kill %1` if backgrounded) — the `defer`-ed `shutdown` flushes the final batch on the way out. No `terraform destroy` needed here.

## What you just learned

- **Middleware auto-instrumentation does most of the work in Go too.** `otelhttp.NewHandler` + `otelhttp.NewTransport` gave you SERVER and CLIENT spans for free, with correct parent/child nesting, the direct analogue of Exercise 1's `FastAPIInstrumentor` + `RequestsInstrumentor`.
- **`ctx` is the trace.** You thread `r.Context()` into the manual span and into the outbound request; drop the `ctx` and the span orphans or the trace splits. This is the one thing Go makes you do by hand that Python did implicitly.
- **You own shutdown.** A `defer`-ed `shutdown` that flushes both providers is mandatory in Go — there is no implicit at-exit flush. Forget it and your last spans never leave the process.
- **Bounded-cardinality metric attributes, identifiers on spans** — the same §1.4 discipline as Python; the GCP metric exporter (and your bill) will not protect you from a high-cardinality label.
- **The GCP exporter maps OTel instrument names into `workload.googleapis.com/`**, and you read percentiles off the distribution — the SLI source you wire into the SLO in Exercise 2, identical to the Python path.
```
