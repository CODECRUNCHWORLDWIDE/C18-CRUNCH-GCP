# Week 9 — Exercises

Three focused drills. The first touches real GCP (and costs effectively nothing — Pub/Sub's free tier covers it). The second and third run entirely on your laptop with the Beam Direct runner and a Pub/Sub emulator, so you can do them on a plane with no cloud spend. Do them in order; later ones assume earlier ones.

## Index

1. **[Exercise 1 — Ordering key + dead-letter topic](exercise-01-ordering-key-and-dlq.md)** — Terraform a Pub/Sub topic with an ordering key and a DLQ, wire the IAM grants Pub/Sub itself needs, then prove a malformed message lands in the DLQ after `max_delivery_attempts`. (~45 min)
2. **[Exercise 2 — Beam windowing on the Direct runner](exercise-02-beam-windowing.py)** — a runnable Apache Beam (Python) pipeline that applies fixed and sliding windows to a synthetic event stream, then demonstrates late data being dropped vs. counted by toggling `allowed_lateness`. Runs locally. (~50 min)
3. **[Exercise 3 — Push vs. pull decision + working consumers](exercise-03-push-vs-pull-decision.py)** — a decision tool that recommends push or pull for a stated consumer pattern, plus a working pull subscriber and a push-handler (Flask) you run against the Pub/Sub emulator to feel the difference. (~40 min)

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Type the code yourself.** Do not copy-paste the solution blocks. Muscle memory is the point.
- Run it. Watch the output. Read the error if it crashed.
- If you get stuck for more than 10 minutes, peek at the inline hints at the bottom of each file.
- Exercise 1 ends with `terraform destroy`. **Run it.** A forgotten subscription is harmless on the free tier, but the teardown habit is the deliverable.

## Setup once, before exercise 2 and 3

You can do exercises 2 and 3 with no real GCP project using the Pub/Sub emulator and the Beam Direct runner. Install once:

```bash
python -m venv .venv && source .venv/bin/activate
pip install "apache-beam[gcp]==2.* " google-cloud-pubsub flask
# The emulator ships with the gcloud CLI:
gcloud components install pubsub-emulator beta --quiet
```

Start the emulator in a separate terminal when an exercise asks for it:

```bash
gcloud beta emulators pubsub start --project=demo-local --host-port=localhost:8085
# In your exercise shell:
export PUBSUB_EMULATOR_HOST=localhost:8085
export PUBSUB_PROJECT_ID=demo-local
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c18-week-09` to compare.
