#!/usr/bin/env python3
# Exercise 2 — Apache Beam windowing on the Direct runner
#
# Goal: Run a real Apache Beam (Python) pipeline that applies FIXED and
#       SLIDING windows to a synthetic event stream, then SEE late data get
#       dropped vs. counted by toggling allowed_lateness. No cloud, no spend:
#       this runs entirely on your laptop on the Direct runner.
#
# Estimated time: 50 minutes.
#
# WHY THIS EXERCISE EXISTS
#
#   Lecture 2 claimed that allowed_lateness=0 is a silent data-loss switch and
#   that a late event whose window already fired gets dropped. This exercise
#   makes you watch it happen. You generate events with deliberate event-time
#   skew (some events are "late"), run the pipeline once with allowed_lateness=0
#   and once with allowed_lateness=600, and compare the per-window sums. The
#   undercount in the first run IS the war story, reproduced on your machine.
#
# SETUP
#
#   python -m venv .venv && source .venv/bin/activate
#   pip install "apache-beam==2.*"
#   python exercise-02-beam-windowing.py
#
# WHAT YOU'LL SEE
#
#   Two tables of (window, revenue, event_count). The DROPPING run's total is
#   strictly less than the COUNTING run's total; the difference equals the sum
#   of the events you injected as "very late."
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import argparse
from typing import Iterable

import apache_beam as beam
from apache_beam import window
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.transforms.trigger import (
    AfterWatermark,
    AfterProcessingTime,
    AccumulationMode,
)
from apache_beam.utils.timestamp import Timestamp


# Each event is (event_time_seconds, revenue). We model a 5-minute span of
# purchases. The last three events are the "subway riders": their event time
# falls in early windows but they arrive (in stream order) at the very end,
# so a too-aggressive watermark will consider them late.
#
# Layout: 300 seconds = five 60s fixed windows: [0,60) [60,120) [120,180)
# [180,240) [240,300).
ON_TIME_EVENTS = [
    (10, 100.0),   # window [0,60)
    (45, 50.0),    # window [0,60)
    (70, 200.0),   # window [60,120)
    (130, 75.0),   # window [120,180)
    (200, 300.0),  # window [180,240)
    (260, 40.0),   # window [240,300)
    (290, 60.0),   # window [240,300)
]

# These belong to early windows by EVENT TIME but arrive last. With a watermark
# that has already advanced past their windows, allowed_lateness decides their
# fate. Total late revenue = 25 + 15 + 35 = 75.0
LATE_EVENTS = [
    (15, 25.0),    # belongs in window [0,60)   — arrives late
    (95, 15.0),    # belongs in window [60,120) — arrives late
    (135, 35.0),   # belongs in window [120,180)— arrives late
]


class AssignEventTime(beam.DoFn):
    """Attach the event-time timestamp from the payload, NOT processing time.

    This is the single most important line in any streaming pipeline: we tell
    Beam to window by WHEN THE THING HAPPENED, not when we saw it.
    """

    def process(self, element: tuple[int, float]) -> Iterable[beam.transforms.window.TimestampedValue]:
        event_time, revenue = element
        yield beam.window.TimestampedValue(revenue, Timestamp(event_time))


class FormatWindow(beam.DoFn):
    """Emit (window_label, total_revenue, count) so we can print a table."""

    def process(
        self,
        revenue_total: float,
        window_param=beam.DoFn.WindowParam,
    ) -> Iterable[tuple[str, float]]:
        # window_param is an IntervalWindow with .start and .end (Timestamps).
        start = int(window_param.start)
        end = int(window_param.end)
        yield (f"[{start:>3},{end:>3})", revenue_total)


def build_pipeline(
    pipeline: beam.Pipeline,
    allowed_lateness_secs: int,
    label: str,
) -> beam.PCollection:
    """Fixed 60s windows summing revenue, with a configurable allowed lateness.

    To reproduce the war story on the bounded Direct runner we feed ON_TIME
    events first, advance the watermark by injecting a 'punctuation' far in the
    future, then feed LATE events. allowed_lateness decides whether the late
    revenue is counted.
    """
    # We use TestStream semantics via a simple two-phase Create + flatten so the
    # late events are processed after the on-time ones. On the Direct runner the
    # watermark for a bounded Create source jumps to +inf when the source is
    # exhausted, so allowed_lateness is what actually gates the late events.
    on_time = (
        pipeline
        | f"{label}/CreateOnTime" >> beam.Create(ON_TIME_EVENTS)
        | f"{label}/TsOnTime" >> beam.ParDo(AssignEventTime())
    )
    late = (
        pipeline
        | f"{label}/CreateLate" >> beam.Create(LATE_EVENTS)
        | f"{label}/TsLate" >> beam.ParDo(AssignEventTime())
    )

    return (
        (on_time, late)
        | f"{label}/Flatten" >> beam.Flatten()
        | f"{label}/Window" >> beam.WindowInto(
            window.FixedWindows(60),
            trigger=AfterWatermark(late=AfterProcessingTime(0)),
            allowed_lateness=allowed_lateness_secs,
            accumulation_mode=AccumulationMode.ACCUMULATING,
        )
        | f"{label}/Sum" >> beam.CombineGlobally(sum).without_defaults()
        | f"{label}/Format" >> beam.ParDo(FormatWindow())
    )


def sliding_window_demo(pipeline: beam.Pipeline) -> beam.PCollection:
    """Same data, 5-minute sliding windows that hop every 60s.

    Every event lands in size/period = 300/60 = up to 5 windows, so the output
    has overlapping windows — the 'trailing 5-minute revenue, updated each
    minute' shape from Lecture 2 §2.3.
    """
    return (
        pipeline
        | "Sliding/Create" >> beam.Create(ON_TIME_EVENTS + LATE_EVENTS)
        | "Sliding/Ts" >> beam.ParDo(AssignEventTime())
        | "Sliding/Window" >> beam.WindowInto(window.SlidingWindows(size=300, period=60))
        | "Sliding/Sum" >> beam.CombineGlobally(sum).without_defaults()
        | "Sliding/Format" >> beam.ParDo(FormatWindow())
    )


def run(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--demo",
        choices=["lateness", "sliding"],
        default="lateness",
        help="lateness: compare dropping vs counting late data. sliding: show hopping windows.",
    )
    known_args, beam_args = parser.parse_known_args(argv)
    options = PipelineOptions(beam_args)

    if known_args.demo == "sliding":
        with beam.Pipeline(options=options) as p:
            results = sliding_window_demo(p)
            results | "PrintSliding" >> beam.Map(
                lambda kv: print(f"SLIDING  window={kv[0]}  revenue={kv[1]:>8.2f}")
            )
        return

    # lateness demo: two pipelines, same data, different allowed_lateness.
    print("=" * 60)
    print("RUN A — allowed_lateness=0   (the war-story bug: late data DROPPED)")
    print("=" * 60)
    with beam.Pipeline(options=options) as p:
        dropping = build_pipeline(p, allowed_lateness_secs=0, label="drop")
        dropping | "PrintDrop" >> beam.Map(
            lambda kv: print(f"DROP   window={kv[0]}  revenue={kv[1]:>8.2f}")
        )

    print()
    print("=" * 60)
    print("RUN B — allowed_lateness=600 (the fix: late data COUNTED)")
    print("=" * 60)
    with beam.Pipeline(options=options) as p:
        counting = build_pipeline(p, allowed_lateness_secs=600, label="count")
        counting | "PrintCount" >> beam.Map(
            lambda kv: print(f"COUNT  window={kv[0]}  revenue={kv[1]:>8.2f}")
        )

    print()
    print("Expected: RUN B's total exceeds RUN A's total by 75.00 — the late")
    print("revenue (25 + 15 + 35). That 75.00 is the silent undercount.")


if __name__ == "__main__":
    run()

# ============================================================================
# WHAT TO OBSERVE / ACCEPTANCE CRITERIA
# ============================================================================
#
#   [ ] `python exercise-02-beam-windowing.py` runs with no errors.
#   [ ] RUN A (allowed_lateness=0) shows window [0,60), [60,120), [120,180)
#       totals that EXCLUDE the late revenue.
#   [ ] RUN B (allowed_lateness=600) shows those same windows INCLUDING the
#       late revenue (window [0,60) gains 25, [60,120) gains 15, [120,180)
#       gains 35).
#   [ ] The grand total of RUN B minus RUN A is exactly 75.00.
#   [ ] `python exercise-02-beam-windowing.py --demo sliding` prints OVERLAPPING
#       windows (you'll see windows like [-240,60), [-180,120), ... because a
#       sliding window can start before the first event).
#
# Note on the Direct runner: it is a correctness-focused local runner, not a
# performance one. The exact firing behavior of late triggers on a BOUNDED
# Create source is simplified vs. a true unbounded Pub/Sub stream on Dataflow;
# the POINT of this exercise is the allowed_lateness contrast, which holds. The
# mini-project runs the unbounded version on Dataflow where the watermark
# advances from real Pub/Sub publish times.
#
# REFLECTION (answer in notes.md):
#   1. In RUN A, which specific late events were dropped, and which window did
#      each belong to by event time?
#   2. You set accumulation_mode=ACCUMULATING. If your BigQuery sink APPENDED
#      every firing instead of upserting by window, what would the [0,60) total
#      look like after the late firing? (Hint: re-read Lecture 2 §2.5.)
#   3. The sliding demo produces windows that start at negative timestamps.
#      Why? (Hint: a 300s window hopping every 60s that must contain an event
#      at t=10 can start as early as t=-290.)
