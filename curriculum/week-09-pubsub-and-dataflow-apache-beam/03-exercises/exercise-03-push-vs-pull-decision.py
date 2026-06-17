#!/usr/bin/env python3
# Exercise 3 — Push vs. pull: a decision tool + working consumers
#
# Goal: Decide push vs. pull for a stated consumer pattern and JUSTIFY it, then
#       feel the difference by running a real pull subscriber and a real push
#       handler against the Pub/Sub EMULATOR (no cloud spend).
#
# Estimated time: 40 minutes.
#
# This file has three parts:
#   (1) decide(pattern)  — a small rules engine that recommends PUSH or PULL
#       for a consumer pattern and explains why, encoding Lecture 1 §1.2.
#   (2) run_pull_consumer()  — a working StreamingPull subscriber.
#   (3) a Flask app (push_app) that is a working PUSH endpoint: it accepts the
#       Pub/Sub POST envelope, decodes the message, and 200s to ack.
#
# SETUP (emulator path — no real GCP project needed)
#
#   pip install google-cloud-pubsub flask
#   gcloud components install pubsub-emulator beta --quiet
#
#   # terminal 1: start the emulator
#   gcloud beta emulators pubsub start --project=demo-local --host-port=localhost:8085
#
#   # every other terminal:
#   export PUBSUB_EMULATOR_HOST=localhost:8085
#   export PUBSUB_PROJECT_ID=demo-local
#
# USAGE
#
#   python exercise-03-push-vs-pull-decision.py decide          # print recommendations
#   python exercise-03-push-vs-pull-decision.py setup           # create topic + 2 subs
#   python exercise-03-push-vs-pull-decision.py publish "hello"  # publish a message
#   python exercise-03-push-vs-pull-decision.py pull            # run the pull consumer
#   python exercise-03-push-vs-pull-decision.py push-server     # run the Flask push handler
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import dataclass

# ----------------------------------------------------------------------------
# PART 1 — the decision tool
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsumerPattern:
    name: str
    always_on_process: bool          # is there a long-lived process to pull?
    needs_consumer_flow_control: bool  # must the consumer cap its own intake?
    public_ingress_ok: bool          # can it expose / reach an HTTPS endpoint?
    wants_backlog_absorption: bool    # should the broker hold backlog on outage?
    is_serverless_scale_to_zero: bool  # Cloud Run/Functions, scale to zero?


def decide(p: ConsumerPattern) -> tuple[str, list[str]]:
    """Return ('PUSH'|'PULL', [reasons]). Encodes Lecture 1 §1.2.

    The rule of thumb: serverless/scale-to-zero and webhook-shaped consumers
    want PUSH (there is nothing to keep pulling). Always-on worker pools,
    Dataflow, and anything that must control its own flow or absorb backlog want
    PULL.
    """
    reasons: list[str] = []
    push_score = 0
    pull_score = 0

    if p.is_serverless_scale_to_zero:
        push_score += 2
        reasons.append("Serverless scale-to-zero: nothing stays running to pull → PUSH wakes it.")
    if p.always_on_process:
        pull_score += 2
        reasons.append("Always-on process exists: it can hold a StreamingPull stream → PULL.")
    if p.needs_consumer_flow_control:
        pull_score += 2
        reasons.append("Consumer must cap its own intake: only PULL exposes FlowControl.")
    if p.wants_backlog_absorption:
        pull_score += 1
        reasons.append("Wants the broker to absorb backlog on a downstream outage: PULL backlog is natural.")
    if not p.public_ingress_ok:
        pull_score += 1
        reasons.append("No public HTTPS ingress available: PULL is outbound-only.")
    if p.public_ingress_ok and p.is_serverless_scale_to_zero:
        push_score += 1
        reasons.append("Has HTTPS ingress AND is serverless: PUSH fits Cloud Run's request model.")

    decision = "PUSH" if push_score > pull_score else "PULL"
    return decision, reasons


SAMPLE_PATTERNS = [
    ConsumerPattern(
        name="Cloud Run image-thumbnailer (scale-to-zero, public URL)",
        always_on_process=False,
        needs_consumer_flow_control=False,
        public_ingress_ok=True,
        wants_backlog_absorption=False,
        is_serverless_scale_to_zero=True,
    ),
    ConsumerPattern(
        name="Dataflow streaming pipeline (always-on, controls its own flow)",
        always_on_process=True,
        needs_consumer_flow_control=True,
        public_ingress_ok=False,
        wants_backlog_absorption=True,
        is_serverless_scale_to_zero=False,
    ),
    ConsumerPattern(
        name="On-prem worker pool behind a firewall, must rate-limit DB writes",
        always_on_process=True,
        needs_consumer_flow_control=True,
        public_ingress_ok=False,
        wants_backlog_absorption=True,
        is_serverless_scale_to_zero=False,
    ),
    ConsumerPattern(
        name="Third-party webhook receiver we don't control the runtime of",
        always_on_process=False,
        needs_consumer_flow_control=False,
        public_ingress_ok=True,
        wants_backlog_absorption=False,
        is_serverless_scale_to_zero=True,
    ),
]


def print_decisions() -> None:
    for pat in SAMPLE_PATTERNS:
        decision, reasons = decide(pat)
        print(f"\n>>> {pat.name}")
        print(f"    RECOMMENDATION: {decision}")
        for r in reasons:
            print(f"      - {r}")


# ----------------------------------------------------------------------------
# PART 2 — setup, publish, pull (against the emulator)
# ----------------------------------------------------------------------------

TOPIC_ID = "events"
PULL_SUB_ID = "events-pull"
PUSH_SUB_ID = "events-push"


def _project() -> str:
    return os.environ.get("PUBSUB_PROJECT_ID", "demo-local")


def setup_resources() -> None:
    from google.cloud import pubsub_v1

    project = _project()
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    topic_path = publisher.topic_path(project, TOPIC_ID)
    try:
        publisher.create_topic(request={"name": topic_path})
        print(f"created topic {topic_path}")
    except Exception as exc:  # AlreadyExists on re-run
        print(f"topic exists or error (ok on re-run): {exc}")

    pull_path = subscriber.subscription_path(project, PULL_SUB_ID)
    try:
        subscriber.create_subscription(request={"name": pull_path, "topic": topic_path})
        print(f"created pull subscription {pull_path}")
    except Exception as exc:
        print(f"pull sub exists or error (ok on re-run): {exc}")

    push_path = subscriber.subscription_path(project, PUSH_SUB_ID)
    try:
        subscriber.create_subscription(
            request={
                "name": push_path,
                "topic": topic_path,
                "push_config": {"push_endpoint": "http://localhost:8088/pubsub/events"},
            }
        )
        print(f"created push subscription {push_path} → http://localhost:8088/pubsub/events")
    except Exception as exc:
        print(f"push sub exists or error (ok on re-run): {exc}")


def publish(text: str) -> None:
    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(_project(), TOPIC_ID)
    future = publisher.publish(topic_path, data=text.encode("utf-8"), source="exercise-03")
    print(f"published message id={future.result()} data={text!r}")


def run_pull_consumer() -> None:
    from google.cloud import pubsub_v1

    subscriber = pubsub_v1.SubscriberClient()
    sub_path = subscriber.subscription_path(_project(), PULL_SUB_ID)

    def callback(message: "pubsub_v1.subscriber.message.Message") -> None:
        # The CONSUMER decided to ack. Flow control (below) is the consumer's
        # lever — push has no equivalent.
        print(f"[PULL] id={message.message_id} attrs={dict(message.attributes)} data={message.data!r}")
        message.ack()

    flow = pubsub_v1.types.FlowControl(max_messages=10, max_bytes=1 * 1024 * 1024)
    future = subscriber.subscribe(sub_path, callback=callback, flow_control=flow)
    print("[PULL] StreamingPull open on events-pull. Ctrl-C to stop. Publish in another shell.")
    try:
        future.result()
    except KeyboardInterrupt:
        future.cancel()
        future.result()


# ----------------------------------------------------------------------------
# PART 3 — the push handler (Flask). Pub/Sub POSTs the message here; a 200
# response is the ack. This is exactly what a Cloud Run push consumer does.
# ----------------------------------------------------------------------------


def make_push_app():
    from flask import Flask, request, Response

    app = Flask(__name__)

    @app.route("/pubsub/events", methods=["POST"])
    def receive_push() -> Response:
        envelope = request.get_json(silent=True)
        if not envelope or "message" not in envelope:
            # 400 → Pub/Sub treats as nack and retries with backoff.
            return Response("bad pubsub envelope", status=400)

        msg = envelope["message"]
        data_b64 = msg.get("data", "")
        try:
            data = base64.b64decode(data_b64).decode("utf-8") if data_b64 else ""
        except Exception:
            return Response("bad base64", status=400)

        attrs = msg.get("attributes", {})
        message_id = msg.get("messageId", "?")
        print(f"[PUSH] id={message_id} attrs={attrs} data={data!r}")

        # 200/204 → Pub/Sub treats as ACK. The ENDPOINT cannot set flow control;
        # Pub/Sub ramps based on our success rate and latency (slow-start).
        return Response("", status=204)

    return app


def run_push_server() -> None:
    app = make_push_app()
    print("[PUSH] Flask push handler on http://localhost:8088/pubsub/events")
    print("[PUSH] (the emulator's push delivery is limited; in real GCP this is a Cloud Run URL)")
    app.run(host="0.0.0.0", port=8088)


# ----------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "decide":
        print_decisions()
    elif cmd == "setup":
        setup_resources()
    elif cmd == "publish":
        publish(argv[1] if len(argv) > 1 else "hello from exercise 3")
    elif cmd == "pull":
        run_pull_consumer()
    elif cmd == "push-server":
        run_push_server()
    else:
        print(f"unknown command: {cmd}")
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

# ============================================================================
# ACCEPTANCE CRITERIA
# ============================================================================
#
#   [ ] `python exercise-03-push-vs-pull-decision.py decide` recommends PUSH for
#       the Cloud Run thumbnailer and the webhook receiver, and PULL for the
#       Dataflow pipeline and the firewalled worker pool.
#   [ ] With the emulator running, `setup` then `publish "x"` then `pull` shows
#       the [PULL] consumer receiving and acking the message.
#   [ ] You can articulate, in notes.md, ONE thing the pull consumer can do that
#       the push handler cannot (answer: cap intake via FlowControl) and ONE
#       thing push gives you that pull does not (answer: no always-on process /
#       scale to zero).
#
# REFLECTION (answer in notes.md):
#   1. The push handler returns 400 on a bad envelope. What does Pub/Sub do with
#      that response, and how does it differ from a 204?
#   2. The pull consumer sets FlowControl(max_messages=10). If your downstream
#      DB can only handle 5 writes/sec, how would you use this lever, and why is
#      there no push equivalent?
#   3. Why is PULL the right choice for Dataflow even though Dataflow is "always
#      scaling"? (Hint: Dataflow's Pub/Sub source pulls; it controls its own
#      flow via autoscaling + StreamingPull.)
