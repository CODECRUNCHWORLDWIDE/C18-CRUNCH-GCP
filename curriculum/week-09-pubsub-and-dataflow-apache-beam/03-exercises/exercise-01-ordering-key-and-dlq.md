# Exercise 1 — Ordering key + dead-letter topic, proven

> **Estimated time:** ~45 minutes. **Cost:** effectively \$0 — Pub/Sub's free tier (10 GiB/month) covers this. Teardown gate at the end.

**Goal.** Provision a Pub/Sub topic with an ordering key, a pull subscription wired to a dead-letter topic with `max_delivery_attempts = 5`, and the two IAM grants the Pub/Sub service account needs to actually dead-letter. Then publish a deliberately-malformed message, nack it five times, and watch it appear on the dead-letter topic. By the end you can defend, with a working artifact, the claim "a `dead_letter_policy` without the IAM grants is a silent no-op."

## What you'll build

```
publisher ──▶ TOPIC (orders) ──▶ SUBSCRIPTION (orders-pull, max_delivery_attempts=5)
                                        │  after 5 nacks
                                        ▼
                                 DLQ TOPIC (orders-dlq) ──▶ SUBSCRIPTION (orders-dlq-pull)
```

## Prerequisites

- A GCP project with billing and the Pub/Sub API enabled:
  ```bash
  gcloud services enable pubsub.googleapis.com --project="$PROJECT_ID"
  ```
- Terraform ≥ 1.6 (or OpenTofu ≥ 1.6) and the `google` provider ≥ 5.x.
- `export PROJECT_ID=your-project-id` in your shell.

## Steps

### Step 1 — Write the Terraform

Create `exercise-01/main.tf`. The starter below has **two deliberate gaps** marked `# TODO`. Fill them — they are the IAM grants that make the DLQ actually work.

```hcl
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

variable "project_id" {
  type = string
}

provider "google" {
  project = var.project_id
}

data "google_project" "current" {}

locals {
  # The Pub/Sub service agent. Pub/Sub uses THIS identity (not yours) to
  # publish to the DLQ and to ack the poison message on the source sub.
  pubsub_sa = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# --- Main topic with ordering enabled on the subscription side --------------
resource "google_pubsub_topic" "orders" {
  name = "orders"
}

# --- Dead-letter topic + a subscription so we can inspect failures ----------
resource "google_pubsub_topic" "orders_dlq" {
  name = "orders-dlq"
}

resource "google_pubsub_subscription" "orders_dlq_pull" {
  name                       = "orders-dlq-pull"
  topic                      = google_pubsub_topic.orders_dlq.id
  message_retention_duration = "604800s" # 7 days
}

# --- Main pull subscription, ordered, dead-lettering after 5 attempts -------
resource "google_pubsub_subscription" "orders_pull" {
  name                    = "orders-pull"
  topic                   = google_pubsub_topic.orders.id
  enable_message_ordering = true
  ack_deadline_seconds    = 10

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.orders_dlq.id
    max_delivery_attempts = 5
  }

  # Retry fast so the exercise doesn't take all day.
  retry_policy {
    minimum_backoff = "1s"
    maximum_backoff = "5s"
  }
}

# --- TODO 1 -----------------------------------------------------------------
# Grant the Pub/Sub service account roles/pubsub.publisher on the DLQ topic,
# so Pub/Sub can write the poison message there.
# Use resource: google_pubsub_topic_iam_member
# ----------------------------------------------------------------------------


# --- TODO 2 -----------------------------------------------------------------
# Grant the Pub/Sub service account roles/pubsub.subscriber on the MAIN
# subscription, so Pub/Sub can ack the poison message on it (stop redelivery).
# Use resource: google_pubsub_subscription_iam_member
# ----------------------------------------------------------------------------

output "topic"        { value = google_pubsub_topic.orders.name }
output "subscription" { value = google_pubsub_subscription.orders_pull.name }
output "dlq_topic"    { value = google_pubsub_topic.orders_dlq.name }
```

### Step 2 — Apply

```bash
cd exercise-01
terraform init
terraform apply -auto-approve -var="project_id=$PROJECT_ID"
```

### Step 3 — Publish an ordered, malformed message

We publish a message with an ordering key and a payload that our consumer will reject (it expects JSON; we send garbage).

```bash
gcloud pubsub topics publish orders \
  --project="$PROJECT_ID" \
  --message='this-is-not-json' \
  --ordering-key='acct-42'
```

### Step 4 — Nack it five times

A consumer that nacks everything. Save as `exercise-01/nack_loop.py` and run it. It pulls the message, fails to parse it, and nacks — five times — then Pub/Sub dead-letters it.

```python
import json
from google.cloud import pubsub_v1
import os

project = os.environ["PROJECT_ID"]
subscriber = pubsub_v1.SubscriberClient()
sub_path = subscriber.subscription_path(project, "orders-pull")

attempts = 0

def callback(message: pubsub_v1.subscriber.message.Message) -> None:
    global attempts
    attempts += 1
    delivery = message.delivery_attempt  # None unless dead_letter_policy is set
    try:
        json.loads(message.data.decode("utf-8"))
        message.ack()
        print(f"[ack] parsed ok: {message.data!r}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"[nack] malformed (delivery_attempt={delivery}): {message.data!r}")
        message.nack()

flow = pubsub_v1.types.FlowControl(max_messages=1)
future = subscriber.subscribe(sub_path, callback=callback, flow_control=flow)
print("listening on orders-pull; ctrl-c after you see delivery_attempt reach 5...")
try:
    future.result(timeout=60)
except Exception:
    future.cancel()
    future.result()
```

```bash
PROJECT_ID=$PROJECT_ID python nack_loop.py
```

You should see `delivery_attempt` climb 1 → 2 → 3 → 4 → 5. After the fifth nack, Pub/Sub stops redelivering on `orders-pull` and republishes the message to `orders-dlq`.

### Step 5 — Prove it landed in the DLQ

```bash
gcloud pubsub subscriptions pull orders-dlq-pull \
  --project="$PROJECT_ID" --auto-ack --limit=5 --format=json
```

You should see your malformed message, plus the dead-letter attributes Pub/Sub adds:

```json
[
  {
    "message": {
      "data": "dGhpcy1pcy1ub3QtanNvbg==",
      "attributes": {
        "CloudPubSubDeadLetterSourceDeliveryCount": "5",
        "CloudPubSubDeadLetterSourceSubscription": "orders-pull",
        "CloudPubSubDeadLetterSourceSubscriptionProject": "your-project-id",
        "CloudPubSubDeadLetterSourceTopicPublishTime": "2026-06-09T10:14:22.118Z"
      }
    },
    "ackId": "..."
  }
]
```

`dGhpcy1pcy1ub3QtanNvbg==` is base64 for `this-is-not-json` — your poison message, now safely quarantined.

### Step 6 — Prove the IAM grants are load-bearing (the lesson)

Comment out **TODO 1** (the publisher grant on the DLQ), `terraform apply`, publish a fresh malformed message, and run the nack loop again. This time `delivery_attempt` climbs **past 5** — to 6, 7, 8… — and nothing ever appears in `orders-dlq`. Pub/Sub *tried* to dead-letter but lacked permission to publish to the DLQ, so it silently kept redelivering. Re-add the grant, apply, and confirm dead-lettering resumes. This is the exact silent failure Lecture 1 §1.4 warns about.

## Expected output (Step 4, abbreviated)

```
listening on orders-pull; ctrl-c after you see delivery_attempt reach 5...
[nack] malformed (delivery_attempt=1): b'this-is-not-json'
[nack] malformed (delivery_attempt=2): b'this-is-not-json'
[nack] malformed (delivery_attempt=3): b'this-is-not-json'
[nack] malformed (delivery_attempt=4): b'this-is-not-json'
[nack] malformed (delivery_attempt=5): b'this-is-not-json'
```

## Acceptance criteria

- [ ] `terraform apply` succeeds; outputs show `orders`, `orders-pull`, `orders-dlq`.
- [ ] TODO 1 and TODO 2 are filled with the correct IAM `member` (the Pub/Sub service agent) and roles.
- [ ] The nack loop shows `delivery_attempt` reaching 5.
- [ ] The malformed message appears on `orders-dlq-pull` with `CloudPubSubDeadLetterSourceDeliveryCount = 5`.
- [ ] You verified Step 6: with the publisher grant removed, the message is **not** dead-lettered and `delivery_attempt` exceeds 5.
- [ ] `enable_message_ordering = true` is set on the subscription (ordering keys require it on both sides).

## Teardown gate (do not skip)

```bash
terraform destroy -auto-approve -var="project_id=$PROJECT_ID"
```

```
Destroy complete! Resources: 6 destroyed.
```

## Reflection questions (answer in a `notes.md`)

1. Why does Pub/Sub use *its own* service account to dead-letter rather than yours? (Hint: the dead-letter must happen even when your consumer code is down.)
2. `delivery_attempt` is `None` on a subscription *without* a `dead_letter_policy`. Why does the field only populate when a DLQ is configured?
3. You set `max_delivery_attempts = 5`. The minimum the API allows is 5 and the max is 100. If a transient downstream outage causes legitimate messages to nack, what's the risk of setting this too *low*? Too *high*?

---

## Hints — peek only if stuck

**TODO 1:**

```hcl
resource "google_pubsub_topic_iam_member" "dlq_publisher" {
  topic  = google_pubsub_topic.orders_dlq.id
  role   = "roles/pubsub.publisher"
  member = local.pubsub_sa
}
```

**TODO 2:**

```hcl
resource "google_pubsub_subscription_iam_member" "main_subscriber" {
  subscription = google_pubsub_subscription.orders_pull.id
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_sa
}
```

If `local.pubsub_sa` errors, the project number lookup may be slow on first apply — `terraform apply` again; the `data.google_project.current` will be populated on the second pass.
