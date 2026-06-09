# Lecture 2 — Watermarks, late data, and triggers: why a pipeline shipped wrong numbers for six months

> **Reading time:** ~80 minutes. **Hands-on time:** ~60 minutes (you run the windowing pipeline from exercise 2 and watch late data get dropped, then get counted).

This is the most important lecture in the data phase of C18, and it is the one engineers most often skip because it sounds theoretical. It is not theoretical. The failure it teaches you to prevent is **wrong numbers, silently, for months**. A batch job that crashes pages you at 3 a.m. — annoying, but you find out. A streaming pipeline whose window closed before the late events arrived ships a daily revenue number that is 4% low, every day, and the dashboard is green the whole time. The finance team finds it at quarter-end when the reconciliation is off by six figures, and then someone has to explain why the data engineering org cannot be trusted with a sum.

We open with the war story, because it is the whole lecture in one example. Then we build the model — event time vs. processing time, windows, watermarks, triggers, allowed lateness — precisely enough that you can look at a Beam pipeline and predict whether it drops, double-counts, or correctly accounts for late data.

## 2.1 — The war story

A mid-size commerce company ran a streaming pipeline: client apps publish a `purchase` event to Pub/Sub when a customer completes checkout, Dataflow windows the events into one-minute tumbling windows, sums the revenue per window, and writes the per-minute total to BigQuery. A dashboard sums the per-minute totals into a daily figure. Standard stuff. It shipped, the numbers looked right in testing, everyone moved on.

Six months later, finance flags that the warehouse's daily revenue is consistently ~3–5% below the figure from the payment processor's own reports. Not a spike — a steady, quiet shortfall. The pipeline never errored. No alert ever fired. The investigation found the bug in the windowing configuration:

```python
# The bug. Looks completely reasonable.
(events
 | beam.WindowInto(beam.window.FixedWindows(60))      # 1-minute windows
 | beam.CombinePerKey(sum))                            # sum revenue per window
# No trigger configured beyond the default; no allowed lateness configured.
```

The events were timestamped with **event time** — the moment of checkout on the customer's device. But mobile clients buffer events. A customer on a subway loses connectivity, completes a purchase, and the event is published four minutes later when they surface. The phone in airplane mode sends a batch of events on landing. A flaky retry path delays a fraction of events by seconds to minutes. These are **late events**: their event time is older than the watermark by the time they arrive.

With the default trigger and **no allowed lateness**, here is what happened to a purchase whose event time fell in the `12:03:00–12:04:00` window but which *arrived* at `12:08:00`: the window had already fired and closed. The watermark had passed `12:04:00` minutes ago. Beam, with the default configuration, **dropped the late event silently**. It did not error. It did not dead-letter it. It discarded it as "too late to matter" — a default that is correct for some use cases and catastrophic for revenue.

About 3–5% of purchases came from clients with enough delay to miss their window. Every one of those was dropped. Every daily total was 3–5% low. For six months. The dashboard was green the entire time because *nothing was wrong with the pipeline* — it did exactly what it was configured to do. The configuration was wrong, and the configuration was the part nobody reviewed because it "looked reasonable."

The fix was one line of allowed lateness and a trigger that re-fires on late data, plus an accumulation-mode choice. By the end of this lecture you will know exactly why, and you will never write the buggy version.

## 2.2 — Event time vs. processing time: the only distinction that matters

Every event has (at least) two timestamps:

- **Event time** — when the thing actually happened. The checkout completed at `12:03:47` on the customer's clock. This is baked into the event payload by the producer.
- **Processing time** — when your pipeline *observed* the event. The Dataflow worker received it from Pub/Sub at `12:08:12`.

In a perfect world these are equal. In the real world there is always **skew** between them, and the skew is **unbounded and variable**: a few milliseconds for a healthy client on wifi, four minutes for the subway rider, hours for a device that was offline. You do not control it and you cannot bound it tightly without lying.

The entire discipline of stream processing is: **you want to compute results grouped by event time, but events arrive in processing-time order, out of event-time order, with unbounded skew.** Windowing, watermarks, and triggers are the three mechanisms Beam gives you to manage exactly this tension. Tyler Akidau's "Streaming 101/102" essays (in the resources) are the canonical treatment; this lecture is the operational version.

If you take one thing from this section: **always window on event time, never on processing time, unless you have a specific reason.** Processing-time windows produce results that depend on when your pipeline happened to be running and how fast it was — they are not reproducible and they are not what the business means by "revenue per minute." The buggy pipeline above used event time correctly; its bug was in the *lateness* handling, which is the next layer.

## 2.3 — Windows: which shape for which question

A **window** assigns each event to one or more finite time intervals so an unbounded stream can be aggregated. Beam gives you four shapes.

### Fixed windows (tumbling)

Non-overlapping, equal-length intervals. Every event belongs to exactly one window. This is "revenue per minute," "errors per hour," "requests per 5 minutes."

```python
import apache_beam as beam
from apache_beam import window

# Each event lands in exactly one 60-second window: [0,60), [60,120), ...
windowed = events | beam.WindowInto(window.FixedWindows(60))
```

### Sliding windows (hopping)

Overlapping intervals defined by a *size* and a *period*. An event can belong to multiple windows. This is "trailing 5-minute average, updated every minute" — moving aggregates.

```python
# 5-minute windows that start every 1 minute → each event is in 5 windows.
windowed = events | beam.WindowInto(window.SlidingWindows(size=300, period=60))
```

Note the multiplier: with `size=300, period=60`, every event is duplicated into 5 windows. Sliding windows can blow up your state and your output volume by `size/period`. Use them when you genuinely need a moving aggregate, not as a default.

### Session windows

Windows defined by *activity gaps*, not fixed boundaries. A session collects events until there is a gap of more than `gap_size` with no events, then closes. This is "group a user's actions into a browsing session," "a sequence of API calls into one request trace." Session windows are per-key and their boundaries are data-dependent.

```python
# A session ends after 10 minutes of inactivity for a given key.
windowed = events | beam.WindowInto(window.Sessions(gap_size=600))
```

### Global window

One window for all time. The default for batch. For streaming you only use it with an explicit trigger, otherwise the aggregate never fires (the window never ends). Useful for "running total since forever, emit every N elements or every T seconds."

```python
windowed = (events
            | beam.WindowInto(
                window.GlobalWindows(),
                trigger=beam.trigger.Repeatedly(beam.trigger.AfterCount(100)),
                accumulation_mode=beam.trigger.AccumulationMode.ACCUMULATING))
```

The window shape is the *first* decision. It says "which events belong together." It does **not** say "when do I emit a result" — that is the trigger's job, and conflating the two is the root of the war story.

## 2.4 — Watermarks: the system's belief about completeness

Here is the central abstraction. A **watermark** is the stream processor's running estimate of *the event time up to which it believes it has seen all the data*. When the watermark passes the end of a window, the system believes that window is **complete** — every event that belongs in it has arrived — and it is safe to emit the window's final result.

The watermark is a function of processing time: as wall-clock time advances and more events flow in, the watermark advances through event time. Crucially, the watermark is an **estimate**, and there are two kinds:

- **Perfect watermark.** If you knew the exact maximum skew, you could compute a watermark that is never wrong — no event ever arrives behind it. In practice you almost never have a perfect watermark, because skew is unbounded (the offline phone).
- **Heuristic watermark.** A best-effort estimate based on observed data. Pub/Sub-sourced pipelines in Dataflow use a heuristic watermark derived from the publish timestamps and the observed event-time distribution. It will sometimes advance past an event time for which a straggler event later arrives. That straggler is, by definition, **late data**: it arrived after the watermark said its window was complete.

This is the crux: **the watermark can be wrong, and when it is wrong it is wrong in the direction that drops your late data.** A heuristic watermark that advances too aggressively (too optimistic about completeness) declares windows complete before the slow events arrive. Those events are then late. What happens to late data is decided by your *allowed lateness* and *trigger* configuration — and the default drops it.

You can inspect the watermark in the Dataflow UI: the "Data watermark" on a streaming step tells you the event time the step believes it is complete up to. The gap between the data watermark and wall-clock time is your effective skew. If you ever see the watermark *stuck* (not advancing) while data flows, you have a stuck source or a hot key — a separate failure mode we cover in the mini-project troubleshooting.

## 2.5 — Triggers: when to emit, and what to do about late data

The window says *which events belong together*. The watermark says *when the system believes a window is complete*. The **trigger** says *when to actually emit a result for the window* — and a window can fire more than once.

Beam's default trigger is `AfterWatermark()`: emit one result when the watermark passes the end of the window. With the default, and **no allowed lateness**, any event that arrives after that single firing is dropped. That is the war-story bug.

The fix has three independent knobs. Learn all three; they compose.

### Knob 1 — allowed lateness

`allowed_lateness` tells Beam how long, past the watermark passing the window end, to **keep the window's state around** so late events can still be incorporated. Set it to the worst-case skew you are willing to wait for.

```python
windowed = (events
            | beam.WindowInto(
                window.FixedWindows(60),
                allowed_lateness=600))   # accept events up to 10 min late
```

With `allowed_lateness=600`, an event for the `12:03–12:04` window that arrives at `12:08` (4 minutes after the watermark passed) is **still inside the allowed-lateness horizon** and will be incorporated. The same event arriving at `12:20` (16 minutes late) is past the horizon and dropped. The trade-off is explicit: longer lateness = more correct (you catch more stragglers) but more state held in memory/storage and more delay before a window's state can be garbage-collected. You pick the number; the war story's bug was that the number defaulted to **zero**.

### Knob 2 — the trigger (early and late firings)

`AfterWatermark` accepts optional `early` and `late` sub-triggers. `early` fires *before* the watermark (speculative partial results, e.g., every 30 seconds so the dashboard updates live). `late` fires *after* the watermark, once per late element (or batched), to update the result with stragglers.

```python
from apache_beam.transforms.trigger import AfterWatermark, AfterProcessingTime, AccumulationMode

windowed = (events
            | beam.WindowInto(
                window.FixedWindows(60),
                trigger=AfterWatermark(
                    early=AfterProcessingTime(30),   # speculative result every 30s
                    late=AfterProcessingTime(60)),   # update with late data, batched 60s
                allowed_lateness=600,
                accumulation_mode=AccumulationMode.ACCUMULATING))
```

With this configuration, the `12:03–12:04` window: emits speculative partials during the minute, emits the on-time result when the watermark passes `12:04`, and then **re-emits an updated result** each time late data arrives within the 10-minute lateness window. The downstream sink sees multiple results for the same window — which brings us to the third knob.

### Knob 3 — accumulation mode

When a window fires more than once, what does each firing contain?

- **`ACCUMULATING`** — each firing contains the *complete* result so far (all events seen for the window up to now). The late firing emits "the new total including the straggler." Your sink must treat each firing as a **replacement** for the previous one (upsert by window key), or you double-count.
- **`DISCARDING`** — each firing contains *only the new* events since the last firing. The late firing emits "just the straggler's contribution." Your sink must treat each firing as a **delta** to add to the running total.

These are not interchangeable, and pairing the wrong accumulation mode with the wrong sink semantics is its own silent-wrong-numbers bug:

| Accumulation mode | Each firing contains | Sink must |
|---|---|---|
| `ACCUMULATING` | Full result so far | Upsert / replace by window key |
| `DISCARDING` | Only the delta | Sum / append the deltas |

If you use `ACCUMULATING` and your sink *appends* every firing, you count the on-time total plus every late re-total — wildly over. If you use `DISCARDING` and your sink *replaces*, you keep only the last straggler's tiny delta and lose the on-time total — wildly under. For a BigQuery sink, `ACCUMULATING` + upsert-by-window (or write to a partition keyed by window and `MERGE` / dedupe at read) is the common correct pairing.

## 2.6 — The corrected war-story pipeline, line by line

Here is the pipeline that should have shipped. Read every line against the buggy version in §2.1.

```python
import apache_beam as beam
from apache_beam import window
from apache_beam.transforms.trigger import (
    AfterWatermark, AfterProcessingTime, AccumulationMode,
)

def revenue_per_minute(events: beam.PCollection) -> beam.PCollection:
    return (
        events
        # 1. Assign event-time timestamps from the payload (NOT processing time).
        #    The source must set the timestamp; for Pub/Sub use the event's own
        #    field, e.g. beam.io.ReadFromPubSub(..., timestamp_attribute="event_time").
        | "FixedMinute" >> beam.WindowInto(
            window.FixedWindows(60),
            # 2. Fire on watermark, re-fire on each late element, and emit a live
            #    early result every 30s so the dashboard isn't stale.
            trigger=AfterWatermark(
                early=AfterProcessingTime(30),
                late=AfterProcessingTime(0),   # re-fire immediately on each late event
            ),
            # 3. Hold window state for 10 minutes past the watermark so stragglers
            #    (the subway rider) are still counted instead of dropped.
            allowed_lateness=10 * 60,
            # 4. ACCUMULATING: each firing is the COMPLETE total → sink upserts by window.
            accumulation_mode=AccumulationMode.ACCUMULATING,
        )
        | "SumRevenue" >> beam.CombineGlobally(sum).without_defaults()
    )
```

The four numbered choices are the entire fix:

1. **Event-time timestamps from the payload.** The Pub/Sub read uses `timestamp_attribute` so Beam windows on when the purchase happened, not when the worker saw it.
2. **A trigger that re-fires on late data.** `late=AfterProcessingTime(0)` means every straggler triggers an updated result.
3. **`allowed_lateness=10*60`.** The window's state survives for 10 minutes after the watermark passes, so a straggler up to 10 minutes late is incorporated. Set this from your *observed* skew distribution: measure the 99.9th percentile of `processing_time - event_time` in your real traffic and set lateness above it. The buggy pipeline's implicit `allowed_lateness=0` is the root cause.
4. **`ACCUMULATING` + an upsert sink.** Each firing is the full window total; BigQuery upserts by window key. The on-time firing writes "revenue so far = \$9,400"; a late firing rewrites it to "\$9,650." No double-count, no undercount.

You still drop events later than 10 minutes — that is a deliberate, *measured* choice, not an accident. And critically: **emit a metric for dropped-late-data.** Beam exposes the count of elements dropped due to lateness; wire it to a Cloud Monitoring alert. The deepest lesson of the war story is not "set allowed lateness" — it is "make the silent thing loud." If 3% of events are being dropped, an alert should fire, not a finance analyst six months later.

## 2.7 — How to detect you're shipping wrong numbers

You will inherit pipelines you did not write. Here is the checklist to tell whether one is silently wrong:

1. **Does it window on event time or processing time?** Find the `WindowInto`. If the timestamps come from `timestamp_attribute` / an explicit `beam.window.TimestampedValue`, it's event time. If there's no timestamp assignment, it's defaulting to processing time — suspect immediately.
2. **What is `allowed_lateness`?** If it's unset (default 0) and the source has *any* real-world skew (mobile clients, retries, multi-region producers), late data is being dropped. Find the dropped-elements metric in Dataflow (`droppedDueToLateness`) and graph it. A non-zero, steady value is your shortfall.
3. **What's the trigger + accumulation pairing?** Verify the sink semantics match: `ACCUMULATING` → upsert, `DISCARDING` → append. A mismatch over/under-counts.
4. **Is there a reconciliation check?** The single best defense: periodically compare the streaming total to an authoritative batch recomputation (re-read the raw events from Pub/Sub-archived storage or the BigQuery raw landing table and recompute). A daily reconciliation job that alerts on >1% divergence would have caught the war story on day one.
5. **Is the watermark advancing?** A stuck watermark (visible in the Dataflow UI) means a window never fires its final result — events accumulate in state and the result is perpetually "early/speculative." Often caused by a single stuck or empty source partition.

## 2.8 — Dataflow specifics that affect correctness

Beam is the model; Dataflow is the runner. A few Dataflow behaviors matter for correctness:

- **Streaming Engine** moves the windowing state off the workers into Google-managed storage. This makes autoscaling and worker replacement *transparent to correctness* — a worker can be killed and replaced and the window state survives. This is why the kill-the-workers challenge works: the state isn't on the worker you killed. (On the classic, non-Streaming-Engine path, state is checkpointed but recovery is slower.)
- **Exactly-once in Dataflow** is the runner's checkpointing combined with idempotent sinks. Dataflow deduplicates Pub/Sub messages using the `id_label` (a message attribute carrying your `event_id`) so a redelivered message is recognized and not reprocessed. Set `id_label` on the Pub/Sub read to your deterministic event id; without it, a publish-side duplicate becomes a double-count.
- **Drain vs. cancel.** `drain` stops ingesting new data but lets in-flight windows finish and flush — use it for clean shutdown so you don't lose buffered window state. `cancel` stops immediately and discards in-flight state — faster, but you may lose un-flushed windows. The teardown gate uses `drain` for the validation run and `cancel` only when you've already confirmed BigQuery has everything.
- **Late data and the BigQuery sink.** With streaming inserts, supply an `insertId` for dedup; with the Storage Write API (the 2026 default for new pipelines), use the exactly-once stream type. We use the Storage Write API in the mini-project.

## 2.9 — A worked watermark timeline

Abstractions are easier to trust when you trace them through wall-clock time. Here is a single 1-minute fixed window, `[12:03:00, 12:04:00)`, with `allowed_lateness=600` (10 minutes), `trigger=AfterWatermark(early=AfterProcessingTime(30), late=AfterProcessingTime(0))`, `ACCUMULATING`, summing revenue. Read the timeline as (processing time → what happens).

```text
12:03:05  (proc)  event A (event_time 12:03:02, $100) arrives. Window state: {A}=100.
12:03:35  (proc)  EARLY trigger fires (30s of processing time elapsed).
                  Emits speculative result: window [12:03,12:04) = $100. Sink upserts → $100.
12:03:50  (proc)  event B (event_time 12:03:40, $50) arrives. Window state: {A,B}=150.
12:04:05  (proc)  EARLY trigger fires again. Emits $150. Sink upserts → $150.
12:04:20  (proc)  WATERMARK passes 12:04:00. ON-TIME trigger fires.
                  Emits the on-time result: $150. Sink upserts → $150 (no change this time).
                  Window state is RETAINED (allowed_lateness not yet exhausted).
12:08:00  (proc)  event C (event_time 12:03:47, $25) arrives — the subway rider.
                  It's LATE (watermark already passed 12:04), but within the 10-min lateness.
                  Window state: {A,B,C}=175.
12:08:00  (proc)  LATE trigger fires immediately (AfterProcessingTime(0)).
                  Emits the updated complete result: $175. Sink upserts → $175.  ← THE FIX
12:14:20  (proc)  allowed_lateness (10 min past watermark) EXPIRES.
                  Window state is garbage-collected. Any event arriving now is dropped
                  and counted in the droppedDueToLateness metric → the alert.
```

Trace the difference from the buggy pipeline: there, the `12:04:20` on-time firing was the *only* firing, the window state was discarded immediately (lateness 0), and event C at `12:08` hit a window that no longer existed — dropped, silent, $25 short. Here, the window survives 10 minutes, the late firing rewrites $150→$175, the sink upserts (so no double count), and only events later than 10 minutes are dropped — *and those are counted in a metric that alerts*. Every number in this timeline is a consequence of the four knobs in §2.6. Internalize the timeline and the configuration becomes obvious instead of magic.

## 2.10 — Choosing allowed_lateness from real data

"Set allowed_lateness from your measured skew distribution" is easy to say. Here is how you actually do it. Before you deploy the streaming pipeline, land a sample of raw events (with both their event-time field and a processing-time stamp from when you received them) into a table, and compute the skew percentiles:

```sql
-- skew = processing_time - event_time, per event. Look at the tail.
SELECT
  APPROX_QUANTILES(TIMESTAMP_DIFF(received_at, event_time, SECOND), 1000)[OFFSET(500)]  AS p50_secs,
  APPROX_QUANTILES(TIMESTAMP_DIFF(received_at, event_time, SECOND), 1000)[OFFSET(990)]  AS p99_secs,
  APPROX_QUANTILES(TIMESTAMP_DIFF(received_at, event_time, SECOND), 1000)[OFFSET(999)]  AS p999_secs,
  MAX(TIMESTAMP_DIFF(received_at, event_time, SECOND))                                  AS max_secs
FROM `project.raw.event_sample`
WHERE event_time IS NOT NULL;
```

A typical mobile-client result might be `p50=2s, p99=45s, p999=210s, max=37000s` (that last one is the phone that was off for ten hours). Now the decision is explicit and it's a *business* decision, not a guess:

- **Set `allowed_lateness` above the p99.9.** With `p999=210s`, an `allowed_lateness` of `300s` (5 minutes) catches 99.9% of stragglers. You will still drop the 0.1% beyond it — including the ten-hours-off phone — but you do so *knowingly*, and the dropped count is on a graph.
- **The trade-off is state cost.** Longer lateness means windows hold state longer, which costs memory and storage and delays when a window's result is final. `allowed_lateness=37000s` to catch the worst phone would hold every window's state for ten hours — usually not worth it for 0.1% of revenue. The right answer is "lateness above p99.9, plus a reconciliation job that catches the long tail in batch."
- **Reconciliation is how you catch the tail without paying for infinite lateness.** The streaming pipeline is *approximately* complete within `allowed_lateness`; a daily batch job that recomputes from the raw landing table is *eventually* complete and catches the stragglers the stream dropped. The stream gives you fresh-but-approximate; the batch gives you slow-but-exact; reconciliation compares them and alerts on divergence. This is the **lambda-architecture** insight, and it's why "stream alone" is rarely the whole answer for numbers that must reconcile to the penny.

The deepest version of the war-story lesson: **a streaming number is an estimate that converges as lateness allows; if the business needs an exact number, the streaming pipeline must be backed by a batch recomputation it reconciles against.** Engineers who skip the reconciliation are trusting the estimate as truth, which is precisely how six months of wrong numbers happens.

## 2.11 — Five watermark/windowing pitfalls you will meet in code review

You now have the model. Here is the field guide — the five mistakes you will actually find when you review a colleague's streaming pipeline, each with the symptom and the fix.

### Pitfall 1 — Processing-time windows masquerading as event-time

**Symptom.** The `WindowInto` has no timestamp assignment upstream; events get the processing-time stamp Beam assigns by default. The "revenue per minute" graph looks fine in steady state but goes haywire when the pipeline lags — a backlog drains and an hour of events all land in the same processing-time minute, producing a giant spike that never happened.

**Fix.** Assign event-time timestamps from the payload (`timestamp_attribute` on the Pub/Sub read, or `beam.window.TimestampedValue` in a `DoFn`). The graph then reflects when things happened, independent of pipeline speed. Reproducibility is the tell: re-running the same input must produce the same windows. Processing-time windows fail that test.

### Pitfall 2 — `allowed_lateness=0` with a skewed source

**Symptom.** The pipeline windows on event time correctly but never sets `allowed_lateness`. The source has real skew (mobile, retries, batching). Totals are quietly low by the late fraction. This is the war story.

**Fix.** Set `allowed_lateness` above your measured p99.9 skew (§2.10), re-fire on late data, and alert on `droppedDueToLateness`.

### Pitfall 3 — Accumulation mode / sink semantics mismatch

**Symptom.** `ACCUMULATING` with an append-only sink → totals balloon (every firing's full result is added). Or `DISCARDING` with an upsert sink → totals collapse (only the last delta survives). The number is wrong by a factor, not a percentage, so it's usually caught faster than the war story — but it's caught by a human, not a test.

**Fix.** `ACCUMULATING` → upsert by window key. `DISCARDING` → append deltas. Write a test that fires a window twice and asserts the sink ends up with the right total.

### Pitfall 4 — A hot key stalling the watermark

**Symptom.** The Dataflow "Data watermark" stops advancing on one step while throughput looks fine elsewhere. Windows never reach their on-time firing; everything is stuck in speculative/early state and the final result never lands. Often caused by one key (one tenant, one device) producing orders of magnitude more events than the rest, so its bundle never drains and holds the watermark back.

**Fix.** Find the hot key (Dataflow's per-key metrics, or a `Top.PerKey` over a sample). Either shard the hot key (append a random suffix `key#0..N` and re-aggregate downstream) or rate-limit/pre-aggregate it at the source. A stalled watermark is never "fine" — investigate before trusting any number.

### Pitfall 5 — Session windows with a gap shorter than the real inter-event time

**Symptom.** You use `Sessions(gap_size=60)` to group a user's activity, but the user's natural pauses (reading a page, thinking) routinely exceed 60s. Sessions fragment — one real browsing session becomes five "sessions" — and any per-session metric (session length, events per session) is wrong low.

**Fix.** Set `gap_size` from the *observed* inter-event time distribution, the same way you set `allowed_lateness` from the skew distribution. Measure the gaps between consecutive events per key; set the session gap above the typical within-session pause but below the typical between-session gap. Session windows are powerful precisely because the boundary is data-driven, but that means the gap parameter is a *measured* quantity, not a guess. The same discipline as everywhere else this week: derive the knob from the data, don't pick a round number.

The thread through all five: **the silent failures are the dangerous ones.** A crash pages you. A wrong number doesn't. Every pitfall here produces a plausible-looking wrong number, and the only defenses are (a) deriving configuration from measured data and (b) a reconciliation check that compares the stream to an authoritative recomputation. Build both reflexively.

## 2.12 — The reflexes to internalize from this lecture

- **Window on event time. Always, unless you can articulate why processing time is correct here.** It almost never is.
- **`allowed_lateness=0` is a silent data-loss switch.** Set lateness from your *measured* skew distribution, not a guess.
- **A window can fire more than once. Match accumulation mode to sink semantics** — `ACCUMULATING`→upsert, `DISCARDING`→append — or you over/under-count.
- **Make the silent thing loud.** Alert on `droppedDueToLateness`. Run a reconciliation job against an authoritative recomputation. Green dashboards lie; reconciliation doesn't.
- **The watermark is a heuristic estimate, not a fact.** It can advance past data that hasn't arrived. That's why lateness handling exists.
- **End-to-end correctness = event-time windows + measured lateness + matched accumulation/sink + idempotent sink + reconciliation.** Five things. Drop any one and you can ship wrong numbers silently.

## 2.13 — What we did not cover (Week 10 picks it up)

This lecture lands *correct* data into BigQuery. It says nothing about reading it cheaply. The BigQuery sink this pipeline writes to is partitioned by event time and clustered by tenant for a reason — Week 10 teaches you to query that table for under a cent by scanning less than 1% of it. The two weeks are a pair: correct ingest here, cheap query there. Tear this pipeline down, then go land the data Week 10 will read.

---

## Lecture 2 — checklist before moving on

- [ ] I can explain the difference between event time and processing time and why skew is unbounded.
- [ ] I can choose fixed / sliding / session / global windows for a stated aggregation question.
- [ ] I can explain what a watermark is, that it's a heuristic estimate, and how late data relates to it.
- [ ] I can explain `allowed_lateness`, early/late triggers, and the `ACCUMULATING` vs. `DISCARDING` choice — and pair accumulation mode to sink semantics correctly.
- [ ] I can read an unfamiliar pipeline and tell whether it's silently dropping late data.
- [ ] I can name the five-part recipe for end-to-end correctness and the metric/reconciliation that makes the silent failure loud.

If any box is unchecked, re-read that section. Exercise 2 has you watch late data get dropped and then get counted, on the Direct runner, on your laptop.

---

**References cited in this lecture**

- Tyler Akidau — "Streaming 101: The world beyond batch": <https://www.oreilly.com/radar/the-world-beyond-batch-streaming-101/>
- Tyler Akidau — "Streaming 102": <https://www.oreilly.com/radar/the-world-beyond-batch-streaming-102/>
- Apache Beam — "Programming guide: Windowing": <https://beam.apache.org/documentation/programming-guide/#windowing>
- Apache Beam — "Programming guide: Triggers": <https://beam.apache.org/documentation/programming-guide/#triggers>
- Apache Beam — "Streaming pipelines: watermarks and late data": <https://beam.apache.org/documentation/basics/#watermark>
- Google Cloud — "Dataflow streaming pipelines": <https://cloud.google.com/dataflow/docs/concepts/streaming-pipelines>
- Google Cloud — "Streaming Engine": <https://cloud.google.com/dataflow/docs/streaming-engine>
- Google Cloud — "Read from Pub/Sub (timestamp_attribute, id_label)": <https://cloud.google.com/dataflow/docs/concepts/streaming-with-cloud-pubsub>
- Google Cloud — "BigQuery Storage Write API": <https://cloud.google.com/bigquery/docs/write-api>
