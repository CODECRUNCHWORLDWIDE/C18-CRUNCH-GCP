# Exercise 1 — Arm the Budget First (MANDATORY)

**Goal:** Before you create a single billable resource in this course, stand up a hard budget on your billing account with threshold alerts at **50%, 90%, and 100%**, route those alerts through Pub/Sub to a Cloud Function, and have that function post to a Slack channel. By the end, a budget threshold crossing lands as a message in `#gcp-cost` — not as an email nobody reads, and not as a five-figure invoice on Monday.

**This exercise is mandatory and gating.** The rest of C18 assumes it is done. Weeks 05 onward create compute; you do not get there without this.

**Estimated time:** 75 minutes.

---

## Setup

You need:

- The `gcloud` CLI authenticated: `gcloud auth login` and `gcloud auth application-default login`.
- Your billing account ID: `gcloud billing accounts list` — it looks like `0X0X0X-0X0X0X-0X0X0X`.
- A project to host the alerting plumbing (the Pub/Sub topic + function). Create a dedicated one; do not put alerting infra in a workload project.
- A Slack workspace where you can create an **Incoming Webhook**. A free personal workspace is fine. Create a channel `#gcp-cost` and add a webhook at <https://api.slack.com/messaging/webhooks>. Copy the webhook URL — it looks like `https://hooks.slack.com/services/T.../B.../...`.

```bash
gcloud auth login
gcloud auth application-default login
gcloud billing accounts list
```

Export the values you will reuse:

```bash
export BILLING_ACCOUNT="0X0X0X-0X0X0X-0X0X0X"     # yours, from the list above
export ALERT_PROJECT="acme-billing-alerts-7f3a"   # globally unique; pick your own suffix
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../..."
export REGION="us-central1"
```

---

## Step 1 — Create and link the alerting project

```bash
# Create the project (no folder needed for the lab; add --folder=ID if you have an org).
gcloud projects create "$ALERT_PROJECT" --name="ACME Billing Alerts"

# Link it to billing — required before you can enable billable APIs.
gcloud billing projects link "$ALERT_PROJECT" --billing-account="$BILLING_ACCOUNT"

# Enable the APIs we need: Pub/Sub, Cloud Functions, Cloud Build, Secret Manager, Billing Budgets.
gcloud services enable \
  pubsub.googleapis.com \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  billingbudgets.googleapis.com \
  --project="$ALERT_PROJECT"
```

`run.googleapis.com` is included because gen2 Cloud Functions run on Cloud Run under the hood.

---

## Step 2 — Create the Pub/Sub topic

```bash
gcloud pubsub topics create billing-alerts --project="$ALERT_PROJECT"
```

Grant the Cloud Billing system service agent permission to publish to it. **This is the step everyone forgets**, and forgetting it means the budget is configured but Slack never fires:

```bash
gcloud pubsub topics add-iam-policy-binding billing-alerts \
  --project="$ALERT_PROJECT" \
  --member="serviceAccount:billing-budget-alert@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

That `billing-budget-alert@system.gserviceaccount.com` address is a stable, Google-managed system account documented in the budget notification guide.

---

## Step 3 — Store the Slack webhook as a secret

Do not bake the webhook into source. Put it in Secret Manager:

```bash
printf '%s' "$SLACK_WEBHOOK_URL" | \
  gcloud secrets create slack-webhook-url \
    --project="$ALERT_PROJECT" \
    --data-file=- \
    --replication-policy="automatic"
```

---

## Step 4 — Write the Cloud Function

Make a folder for the function source:

```bash
mkdir -p budget-to-slack && cd budget-to-slack
```

`main.py` (this is the function from Lecture 2 — type it, don't just copy):

```python
"""Cloud Function (gen2): forward a Cloud Billing budget alert to Slack."""

from __future__ import annotations

import base64
import json
import os

import functions_framework
import requests
from cloudevents.http import CloudEvent

SLACK_TIMEOUT_SECONDS = 10


def _emoji_for(threshold: float) -> str:
    if threshold >= 1.0:
        return ":rotating_light:"
    if threshold >= 0.9:
        return ":warning:"
    return ":moneybag:"


def _format_message(notification: dict) -> dict:
    name = notification.get("budgetDisplayName", "(unnamed budget)")
    threshold = float(notification.get("alertThresholdExceeded", 0.0))
    cost = float(notification.get("costAmount", 0.0))
    budget = float(notification.get("budgetAmount", 0.0))
    currency = notification.get("currencyCode", "USD")
    pct = threshold * 100
    headline = (
        f"{_emoji_for(threshold)} *Budget alert: {name}* crossed {pct:.0f}% "
        f"({cost:,.2f} / {budget:,.2f} {currency})"
    )
    return {
        "text": headline,
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": headline}},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Spend so far this period: *{cost:,.2f} {currency}*  ·  "
                            f"Budget: *{budget:,.2f} {currency}*  ·  "
                            f"Threshold: *{pct:.0f}%*"
                        ),
                    }
                ],
            },
        ],
    }


@functions_framework.cloud_event
def budget_to_slack(cloud_event: CloudEvent) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set")

    message = cloud_event.data["message"]
    raw = base64.b64decode(message["data"]).decode("utf-8")
    notification = json.loads(raw)

    if "alertThresholdExceeded" not in notification:
        print(f"Skipping non-threshold notification: {raw}")
        return

    payload = _format_message(notification)
    response = requests.post(webhook, json=payload, timeout=SLACK_TIMEOUT_SECONDS)
    response.raise_for_status()
    print(f"Forwarded {notification['budgetDisplayName']} alert to Slack")
```

`requirements.txt`:

```text
functions-framework==3.*
requests==2.*
cloudevents==1.*
```

---

## Step 5 — Deploy the function

Deploy a gen2 function triggered by the topic, with the webhook injected from Secret Manager:

```bash
gcloud functions deploy budget-to-slack \
  --gen2 \
  --project="$ALERT_PROJECT" \
  --region="$REGION" \
  --runtime=python312 \
  --source=. \
  --entry-point=budget_to_slack \
  --trigger-topic=billing-alerts \
  --set-secrets="SLACK_WEBHOOK_URL=slack-webhook-url:latest" \
  --no-allow-unauthenticated
```

If the deploy complains about the Cloud Functions or Cloud Build service account lacking secret access, grant it:

```bash
PROJECT_NUMBER=$(gcloud projects describe "$ALERT_PROJECT" --format="value(projectNumber)")
gcloud secrets add-iam-policy-binding slack-webhook-url \
  --project="$ALERT_PROJECT" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

---

## Step 6 — Create the budget with three thresholds

The budget lives on the **billing account**, not the project. Set a small lab amount (e.g. \$50). The Budget API does not have a clean `gcloud` create-with-pubsub one-liner across all versions, so we use the REST API directly with a JSON body — this also teaches you the real resource shape.

Create `budget.json`:

```json
{
  "displayName": "c18-lab-monthly",
  "budgetFilter": {
    "calendarPeriod": "MONTH"
  },
  "amount": {
    "specifiedAmount": { "currencyCode": "USD", "units": "50" }
  },
  "thresholdRules": [
    { "thresholdPercent": 0.5, "spendBasis": "CURRENT_SPEND" },
    { "thresholdPercent": 0.9, "spendBasis": "CURRENT_SPEND" },
    { "thresholdPercent": 1.0, "spendBasis": "CURRENT_SPEND" },
    { "thresholdPercent": 1.0, "spendBasis": "FORECASTED_SPEND" }
  ],
  "notificationsRule": {
    "pubsubTopic": "projects/PROJECT_ID/topics/billing-alerts",
    "schemaVersion": "1.0"
  }
}
```

Substitute your real project ID into the `pubsubTopic` line, then POST it:

```bash
sed -i.bak "s/PROJECT_ID/${ALERT_PROJECT}/" budget.json && rm budget.json.bak

curl -s -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://billingbudgets.googleapis.com/v1/billingAccounts/${BILLING_ACCOUNT}/budgets" \
  -d @budget.json | jq .
```

You should get back a budget object with a `name` like `billingAccounts/0X0X0X-.../budgets/<uuid>`. Save that name.

---

## Step 7 — Prove it fires (without spending real money)

You will not wait around for real spend to cross 50%. Instead, publish a synthetic budget notification straight onto the topic, exactly like the Budget service would. This proves the **topic → function → Slack** path end to end:

```bash
FAKE=$(python3 -c 'import base64,json; print(base64.b64encode(json.dumps({
  "budgetDisplayName": "c18-lab-monthly",
  "alertThresholdExceeded": 0.9,
  "costAmount": 45.12,
  "budgetAmount": 50.0,
  "currencyCode": "USD"
}).encode()).decode())')

gcloud pubsub topics publish billing-alerts \
  --project="$ALERT_PROJECT" \
  --message="$FAKE"
```

Within a few seconds, a `:warning:` message should appear in `#gcp-cost`:

```
:warning: Budget alert: c18-lab-monthly crossed 90% (45.12 / 50.00 USD)
Spend so far this period: 45.12 USD · Budget: 50.00 USD · Threshold: 90%
```

Check the function logs to confirm the invocation:

```bash
gcloud functions logs read budget-to-slack \
  --gen2 --project="$ALERT_PROJECT" --region="$REGION" --limit=20
```

You should see `Forwarded c18-lab-monthly alert to Slack`.

---

## Expected output

In your terminal, after Step 6:

```json
{
  "name": "billingAccounts/0X0X0X-0X0X0X-0X0X0X/budgets/3f2c...-...-...",
  "displayName": "c18-lab-monthly",
  "budgetFilter": { "calendarPeriod": "MONTH" },
  "amount": { "specifiedAmount": { "currencyCode": "USD", "units": "50" } },
  "thresholdRules": [ ... four rules ... ],
  "notificationsRule": { "pubsubTopic": "projects/.../topics/billing-alerts", "schemaVersion": "1.0" }
}
```

In Slack, after Step 7: a `:warning:` message in `#gcp-cost`.

In your notes, the marker:

```
budget: armed · 3 thresholds (50/90/100%) · notify: pubsub://billing-alerts · channel: #gcp-cost
```

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] A dedicated alerting project exists, is linked to billing, and has Pub/Sub, Functions, and Secret Manager enabled.
- [ ] A `billing-alerts` Pub/Sub topic exists, and `billing-budget-alert@system.gserviceaccount.com` has `roles/pubsub.publisher` on it.
- [ ] The Slack webhook is stored in Secret Manager, **not** in source.
- [ ] The `budget-to-slack` gen2 function is deployed and triggered by the topic.
- [ ] A budget named `c18-lab-monthly` exists with **four** threshold rules (50/90/100% actual + 100% forecasted).
- [ ] Publishing a synthetic notification produces a real Slack message in `#gcp-cost` and a `Forwarded ... to Slack` log line.
- [ ] You can produce the `budget: armed ...` marker line.

---

## Stretch

- Add the **hard-cap** consumer from Lecture 2 — a second function on the same topic that detaches billing at 100% actual. Point it only at a throwaway project. Test it by publishing a synthetic `1.0` notification and confirming `gcloud billing projects describe <throwaway>` shows `billingEnabled: false`.
- Set `disableDefaultIamRecipients: true` in the budget so the email to billing admins stops once Slack is trusted.
- Enable **billing export to BigQuery** now, so you have cost history to query in Week 14.
- Re-implement Steps 2–6 in Terraform (`google_pubsub_topic`, `google_billing_budget`, `google_cloudfunctions2_function`) — this is a head start on the mini-project.

---

## Hints

<details>
<summary>The deploy succeeds but no Slack message arrives when I publish</summary>

Check, in order: (1) the function logs — is it being invoked at all? If not, the trigger topic is wrong. (2) Is `SLACK_WEBHOOK_URL` actually set? `gcloud functions describe ... --gen2` shows the secret mounts. (3) Does the synthetic message have an `alertThresholdExceeded` field? Without it the function deliberately skips (the no-threshold guard). (4) Is the webhook URL still valid? Slack expires unused webhooks.

</details>

<details>
<summary>The budget POST returns 403 PERMISSION_DENIED</summary>

You need `roles/billing.admin` (or at least `billing.budgets.create`) on the billing account, and `billingbudgets.googleapis.com` enabled on whatever project your access token bills against. Check `gcloud billing accounts get-iam-policy "$BILLING_ACCOUNT"`.

</details>

<details>
<summary>The function deploy fails on the secret</summary>

Gen2 functions run as the Compute Engine default service account (`<projectNumber>-compute@developer.gserviceaccount.com`) unless you override it. That account needs `roles/secretmanager.secretAccessor` on `slack-webhook-url`. The grant command is in Step 5.

</details>

---

When this is green, move to [Exercise 2 — Map the org chart](./exercise-02-map-the-org-chart.py).
