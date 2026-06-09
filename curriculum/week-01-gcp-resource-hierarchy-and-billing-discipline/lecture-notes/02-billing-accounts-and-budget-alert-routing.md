# Lecture 2 — Billing Accounts and Budget Alert Routing: Page Slack Before You Page Your CTO

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can explain the billing-account-to-project relationship, scope a budget correctly, build the Pub/Sub → Cloud Function → Slack path that turns a budget threshold into a message in `#gcp-cost`, and state precisely why a budget is an *alert*, not a cap.

If you only remember one thing from this lecture, remember this:

> **A Google Cloud budget does not stop spending. It sends a notification. The "hard cap" is something *you* build on top of the notification — a Pub/Sub message that triggers code that disables billing on the project. If you skip that step, your "budget" is a tripwire with no teeth, and you will learn this the morning a runaway job has already spent the money.**

Lecture 1 split the AWS account into three GCP objects: project, billing account, IAM policy. This lecture is about the second of those — the billing account — and the one piece of automation that makes the whole course safe to run on a real credit card. Exercise 1 is mandatory for a reason: until the budget is armed, you do not get to create compute.

---

## 1. The billing account is its own object

In AWS, billing is an attribute of the account — the account *is* the payer (or it rolls up to a payer account under Consolidated Billing). In GCP, billing is a **separate first-class object** that lives outside the resource hierarchy entirely.

```
Cloud Billing Account  (0X0X0X-0X0X0X-0X0X0X)        ← a payment instrument + an entity
│
│  linked to (many-to-one)
│
├── Project  acme-api-dev-7f3a
├── Project  acme-api-prod-2b91
├── Project  acme-tf-state-prod
└── Project  acme-logging
```

Key facts that fall out immediately:

- **A billing account is not in the resource tree.** It is not under the org, not under a folder. It is its own object with its own IAM (`roles/billing.admin`, `roles/billing.user`, `roles/billing.viewer`). An org *can* own billing accounts, but the billing account is not a *node* in the org/folder/project tree.
- **Many projects link to one billing account.** Every project that incurs cost must be linked to exactly one billing account at a time. Unlink it and the project's billable resources stop (and eventually get reclaimed).
- **The link is the resource you manage.** In `gcloud` it is `gcloud billing projects link`; in Terraform it is the `billing_account` attribute on `google_project`, or a separate `google_billing_project_info`. That link — the `billing.resourceAssociations` edge — is what routes a project's cost to a payer.

There are two kinds of billing account you will meet:

| Type | How you pay | Who has it |
|------|-------------|------------|
| **Self-serve (online)** | Credit/debit card, auto-charged | Almost everyone; the free trial converts to this |
| **Invoiced (offline)** | Monthly invoice, net terms | Large enterprises with a Google sales relationship |

For this course you have a self-serve account created when you started the \$300 free trial. That is the one you will arm a budget against.

> **The AWS contrast, restated:** AWS Consolidated Billing rolls member accounts up to a payer account; the payer *is* an account. GCP's billing account is a peer object that projects *point at*. The practical difference: in GCP you can move a project to a different billing account with one API call and zero resource migration, because the project and its payer were never the same object. That is genuinely nice the day a cost-center reorg lands on your desk.

---

## 2. Billing IAM is separate from project IAM

This catches everyone once. The permission to *create resources in a project* (`roles/editor`, `roles/owner` on the project) is **not** the permission to *change the project's billing* or *see the bill*.

| Role | Scope | Lets you… |
|------|-------|-----------|
| `roles/billing.admin` | Billing account | Manage the billing account, link/unlink projects, set budgets |
| `roles/billing.user` | Billing account | Link a *new* project to this billing account (but not manage it) |
| `roles/billing.viewer` | Billing account | See cost and budgets; change nothing |
| `roles/billing.projectManager` | Project | Change *which* billing account this project uses |
| `roles/resourcemanager.projectCreator` | Org/folder | Create projects (but cannot link them to billing without `billing.user`) |

The combination that bites people: a CI service account can create projects (`projectCreator`) but cannot link them to billing (`billing.user`), so every automated project lands in a state where it exists but cannot enable a billable API. The fix is to grant the CI principal `roles/billing.user` on the billing account. We do exactly this in the mini-project's bootstrap.

---

## 3. What a budget actually is

A **budget** is a named object that lives on a billing account (and optionally narrows its scope). It has:

1. **An amount.** Either a fixed number (`$50`) or "last month's spend" (a moving target). For labs, always fixed.
2. **A scope.** The whole billing account, or a filtered subset: specific projects, specific services, specific labels, specific credits. Scope is how you say "alert me on the *dev* project's spend, separately from prod."
3. **Threshold rules.** "Notify at X% of the amount." Each rule chooses **actual** spend or **forecasted** spend. You will arm three: 50%, 90%, 100% — all on actual, plus often a forecasted-100% as an early warning.
4. **Notification channels.** Where the alert goes:
   - **Email** to the billing admins / users (on by default; weak — nobody reads it).
   - **A Pub/Sub topic** (the programmatic path; this is the one that matters).
   - **Cloud Monitoring notification channels** (newer; can fan out to Slack/PagerDuty via Monitoring).

> **The single most important sentence about budgets:** *a budget does not enforce anything.* It is a notification engine. Crossing 100% does not stop your spend. If you want a hard cap — billing actually disabled — you wire the Pub/Sub message to a function that calls `cloudbilling.projects.updateBillingInfo` with an empty billing account, which **detaches billing and stops billable resources.** That is the "hard cap" in the exercise title, and it is code *you* write. Google ships the tripwire; you build the teeth.

---

## 4. Why the Pub/Sub path, not just email

The default budget creates email alerts to whoever holds `billing.admin`/`billing.user`. That is the alert that pages your CTO — literally, because the CTO is often the billing admin on a young company's account. It is also useless operationally: it is unstructured email, it cannot trigger automation, and it arrives in an inbox nobody watches on a Saturday.

The **programmatic notification** path publishes a structured JSON message to a Pub/Sub topic *every time the budget is evaluated* (roughly every 20–30 minutes, and on every threshold crossing). That message looks like this:

```json
{
  "budgetDisplayName": "acme-all-projects-monthly",
  "alertThresholdExceeded": 0.9,
  "costAmount": 45.12,
  "costIntervalStart": "2026-06-01T07:00:00Z",
  "budgetAmount": 50.0,
  "budgetAmountType": "SPECIFIED_AMOUNT",
  "currencyCode": "USD"
}
```

Pub/Sub is a real message bus, so now you have options. You can:

- Trigger a **Cloud Function** that posts to a Slack Incoming Webhook (what we build).
- Trigger a **Cloud Function** that *disables billing* on the offending project (the hard cap).
- Fan it into BigQuery for cost analytics.
- Route it to PagerDuty/Opsgenie for true on-call.

The architecture for this week:

```
Budget (90% threshold crossed)
        │  publishes JSON
        ▼
Pub/Sub topic  billing-alerts
        │  push/event trigger
        ▼
Cloud Function (gen2, Python)  budget-to-slack
        │  HTTPS POST
        ▼
Slack Incoming Webhook  →  #gcp-cost
```

Everything in that diagram is inside the always-free tier at the volume you will use. The topic is free. One gen2 Cloud Function invoked a handful of times a day is free. The only thing that is not Google's is the Slack webhook, which is also free.

---

## 5. The Cloud Function: budget message to Slack

Here is the function, complete and correct for the Functions Framework (Python 3.12, gen2). The Pub/Sub message arrives base64-encoded in a CloudEvent; we decode it, format it, and POST to Slack.

`main.py`:

```python
"""Cloud Function (gen2): forward a Cloud Billing budget alert to Slack.

Triggered by a Pub/Sub message published by a Cloud Billing budget's
programmatic notification channel. Decodes the budget notification JSON,
formats a human-readable Slack message, and POSTs it to an Incoming Webhook.

Environment variables:
  SLACK_WEBHOOK_URL  the Slack Incoming Webhook URL (set as a secret).
"""

from __future__ import annotations

import base64
import json
import os

import functions_framework
import requests
from cloudevents.http import CloudEvent

SLACK_TIMEOUT_SECONDS = 10


def _emoji_for(threshold: float) -> str:
    """Pick a Slack emoji by how serious the threshold is."""
    if threshold >= 1.0:
        return ":rotating_light:"
    if threshold >= 0.9:
        return ":warning:"
    return ":moneybag:"


def _format_message(notification: dict) -> dict:
    """Build the Slack chat.postMessage-style payload from a budget message."""
    name = notification.get("budgetDisplayName", "(unnamed budget)")
    threshold = float(notification.get("alertThresholdExceeded", 0.0))
    cost = float(notification.get("costAmount", 0.0))
    budget = float(notification.get("budgetAmount", 0.0))
    currency = notification.get("currencyCode", "USD")

    pct = threshold * 100
    emoji = _emoji_for(threshold)
    headline = (
        f"{emoji} *Budget alert: {name}* crossed {pct:.0f}% "
        f"({cost:,.2f} / {budget:,.2f} {currency})"
    )

    return {
        "text": headline,
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": headline},
            },
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
    """Entry point. Decode the Pub/Sub message and forward it to Slack."""
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set")

    # The Pub/Sub payload is base64-encoded in data.message.data.
    message = cloud_event.data["message"]
    raw = base64.b64decode(message["data"]).decode("utf-8")
    notification = json.loads(raw)

    # The first notification on a new budget has no threshold field; skip it.
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

Two details that are not optional:

- **The first notification has no `alertThresholdExceeded`.** When a budget is created, the API fires a "hello" message with current spend but no threshold. If you do not guard against it, your first Slack message is a `KeyError` traceback. The guard above handles it.
- **The webhook URL is a secret.** Do not bake it into the source. Pass it as an env var sourced from Secret Manager (we wire this in the exercise). A leaked Incoming Webhook URL lets anyone spam your channel.

You can test this locally with the Functions Framework before deploying:

```bash
pip install functions-framework requests cloudevents
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T000/B000/XXXX"
functions-framework --target=budget_to_slack --signature-type=cloudevent &

# Build a fake CloudEvent with a base64 budget message and POST it:
python3 - <<'PY'
import base64, json, requests
msg = {"budgetDisplayName": "test", "alertThresholdExceeded": 0.9,
       "costAmount": 45.0, "budgetAmount": 50.0, "currencyCode": "USD"}
data = base64.b64encode(json.dumps(msg).encode()).decode()
event = {"message": {"data": data}}
requests.post("http://localhost:8080",
              headers={"ce-id": "1", "ce-source": "//test", "ce-type": "test",
                       "ce-specversion": "1.0", "Content-Type": "application/json"},
              json=event)
PY
```

A real Slack message lands in `#gcp-cost`. That is the loop you want green before you ever create a VM.

---

## 6. The budget in Terraform

The whole thing — topic, budget, threshold rules, Pub/Sub channel — is declarative. Here is the budget resource (the function deploy is in the exercise/mini-project):

```hcl
resource "google_pubsub_topic" "billing_alerts" {
  project = var.alerting_project_id
  name    = "billing-alerts"
}

# The budget itself lives on the billing account, not in a project.
resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "acme-all-projects-monthly"

  budget_filter {
    # Scope to specific projects so dev and prod alert separately.
    projects = [for p in var.budgeted_projects : "projects/${p}"]
    calendar_period = "MONTH"
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    threshold_percent = 0.9
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    # Early warning: forecasted to blow the budget by period end.
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    pubsub_topic                     = google_pubsub_topic.billing_alerts.id
    schema_version                   = "1.0"
    disable_default_iam_recipients   = false
  }
}
```

The pieces that map back to the lecture:

- **`budget_filter.projects`** is the scope. Drop it and the budget watches the whole billing account; include it and you get per-project budgets.
- **Four `threshold_rules`** — three on `CURRENT_SPEND` (50/90/100) and one `FORECASTED_SPEND` 100% as the early warning. The forecasted rule is what fires on Tuesday to tell you Friday is going to be expensive.
- **`all_updates_rule.pubsub_topic`** is the wire to your topic. This is the line that turns email-to-CTO into automation.
- **`disable_default_iam_recipients = false`** keeps the email going *too*. In a real org you often set this to `true` once Slack is trusted, so the CTO stops getting paged for a 50% dev alert.

One IAM detail: the Cloud Billing service agent must be allowed to publish to your topic. The budget will silently fail to deliver otherwise. Grant it:

```hcl
resource "google_pubsub_topic_iam_member" "billing_publisher" {
  project = var.alerting_project_id
  topic   = google_pubsub_topic.billing_alerts.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:billing-budget-alert@system.gserviceaccount.com"
}
```

That `billing-budget-alert@system.gserviceaccount.com` is a Google-managed system service account; the address is documented and stable. Forgetting this grant is the number-one reason "my budget is configured but Slack never fires."

---

## 7. Budget vs. hard cap: the part everyone gets wrong

Say it again, because it is the whole point of the lecture: **a budget alerts; it does not cap.** Crossing 100% does not stop anything. The infamous "I set a \$50 budget and still got a \$3000 bill" stories are all the same story — someone assumed the budget was a cap.

To build a real cap, you add a *second* consumer on the same Pub/Sub topic — a function that, on a 100%-actual crossing, **disables billing on the project**:

```python
@functions_framework.cloud_event
def kill_billing(cloud_event):
    """Detach billing from the project when actual spend hits 100%.

    DESTRUCTIVE. This stops all billable resources in the project. Only wire
    this to a non-prod project, or to a project whose downtime you can accept.
    """
    import base64, json, os
    from googleapiclient import discovery

    raw = base64.b64decode(cloud_event.data["message"]["data"]).decode("utf-8")
    note = json.loads(raw)
    if note.get("alertThresholdExceeded", 0.0) < 1.0:
        return  # only act on a real 100% breach

    project_id = os.environ["TARGET_PROJECT_ID"]
    billing = discovery.build("cloudbilling", "v1")
    name = f"projects/{project_id}"
    # Empty billingAccountName detaches billing -> stops billable resources.
    billing.projects().updateBillingInfo(
        name=name, body={"billingAccountName": ""}
    ).execute()
    print(f"Disabled billing on {project_id}")
```

This is genuinely destructive: detaching billing stops VMs, drains managed services, and can lose un-snapshotted state. You wire it only to disposable lab projects, or to a project whose hard downtime you actively prefer over runaway spend. For the mandatory Exercise 1 you build the *alert* path (Slack). The kill path is the challenge's stretch, and you point it only at a throwaway project.

> **The decision rule:** alert for everything; cap only what you can afford to have abruptly killed. A dev sandbox that hits 100%? Cap it — better dead than expensive. The prod payments database? Never auto-cap — page a human. Knowing which is which is the senior judgment this week is teaching.

---

## 8. Reading the bill: billing export to BigQuery

Budgets tell you *that* you spent; they do not tell you *on what*. For that, enable **billing export to BigQuery** — a daily (or near-real-time) dump of every line item into a dataset you can query. You will lean on this heavily in Week 14 (FinOps), but turn it on now so you have history to query later.

A query you will run a hundred times over the course:

```sql
-- Top spend by service, this month, across all projects on the billing account.
SELECT
  service.description AS service,
  ROUND(SUM(cost), 2) AS cost_usd
FROM `acme-billing.billing_export.gcp_billing_export_resource_v1_0X0X0X_0X0X0X_0X0X0X`
WHERE invoice.month = FORMAT_DATE('%Y%m', CURRENT_DATE())
GROUP BY service
ORDER BY cost_usd DESC
LIMIT 20;
```

The point this week is just to **enable the export** so the table starts filling. An empty history is the thing you regret in Week 14. Budgets are the smoke alarm; the BigQuery export is the security camera you review after the fact.

---

## 9. Quotas, briefly, because they are the *other* cost surprise

A budget protects you from *spend*. A quota protects you (and Google) from *runaway resource creation* — and a quota you forgot to raise will block a deploy at the worst time.

Two flavors, and you must know which is which:

| Quota type | Measures | Example | Resets |
|------------|----------|---------|--------|
| **Rate quota** | Requests per unit time | "Compute Engine API: 2,000 read requests/min" | Continuously (per minute) |
| **Allocation quota** | Count of a thing that exists | "CPUs in `us-central1`: 24" | Never — it is a standing ceiling |

Most are **per-project, per-region**. The two facts that save you a debugging session:

1. **A fresh project has *low* default quotas.** A brand-new project might allow only 8–24 CPUs in a region. Your Week 5 MIG that wants 30 vCPUs will fail to scale with a quota error, not a billing error. Read the quota before you blame the autoscaler.
2. **Quota is not billing.** Hitting an allocation quota does not cost money; it just blocks creation. Hitting a budget does not block creation; it just alerts. They are independent guardrails, and conflating them is a classic week-one mistake.

Inspect quotas with:

```bash
# Allocation quotas for a region (look for CPUS, IN_USE_ADDRESSES, etc.)
gcloud compute regions describe us-central1 \
  --project=acme-api-dev-7f3a \
  --format="table(quotas.metric, quotas.limit, quotas.usage)"
```

Request increases through the Quotas page or `gcloud` — and know that some increases are auto-approved in seconds while others (large CPU/GPU asks) go to a human and take a day. Plan for the latter before a deploy deadline, not during one.

---

## 10. Recap

You should now be able to:

- Explain that the billing account is an object *outside* the resource hierarchy, with its own IAM, that many projects link to.
- Distinguish billing IAM (`billing.admin/user/viewer`, `projectManager`) from project IAM, and name the `projectCreator` + `billing.user` combination CI needs.
- State the four parts of a budget — amount, scope, threshold rules, notification channels — and why the Pub/Sub channel is the one that matters.
- Build and locally test the Cloud Function that turns a budget Pub/Sub message into a Slack post, including the no-threshold first-message guard.
- Write the `google_billing_budget` Terraform with three actual thresholds plus a forecasted early warning, and grant the billing service agent publish on the topic.
- Explain, sharply, that a budget *alerts* and does not *cap*, and describe the second consumer that builds a real cap by detaching billing.
- Distinguish rate quotas from allocation quotas and read a region's quotas with `gcloud`.

Next up: do the work. Continue to the [exercises](../exercises/README.md) — and remember that Exercise 1 is mandatory and gates everything else.

---

## References

- *Cloud Billing overview*: <https://cloud.google.com/billing/docs/concepts>
- *Create, edit, or delete budgets and budget alerts*: <https://cloud.google.com/billing/docs/how-to/budgets>
- *Programmatic budget notifications (Pub/Sub)*: <https://cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications>
- *Disable billing to stop usage* (the hard-cap pattern): <https://cloud.google.com/billing/docs/how-to/notify#cap_disable_billing_to_stop_usage>
- *`google_billing_budget`* — Terraform: <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/billing_budget>
- *Export billing data to BigQuery*: <https://cloud.google.com/billing/docs/how-to/export-data-bigquery>
- *Working with quotas*: <https://cloud.google.com/docs/quotas/overview>
- *Functions Framework for Python*: <https://github.com/GoogleCloudPlatform/functions-framework-python>
