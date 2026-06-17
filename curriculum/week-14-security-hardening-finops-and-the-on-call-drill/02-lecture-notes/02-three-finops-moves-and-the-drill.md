# Lecture 2 — The Three FinOps Moves That Pay Back Inside One Quarter, and the On-Call Drill

> **Reading time:** ~80 minutes. **Hands-on time:** ~50 minutes (you query the billing export, compute one committed-use saving, and dry-run the on-call drill once).

Lecture 1 stopped the bad thing. This lecture does two things: it stops *wasting money* — FinOps — and it gets you *through the night* — on-call. They are in the same lecture because they are the same muscle: a disciplined, evidence-driven, repeatable process run by a tired human, where the difference between competent and incompetent is whether you measured before you acted.

The FinOps half is brutally concrete: there are exactly **three moves that pay back inside one quarter** on a GCP workload, and there are a dozen more that sound clever and pay back never. We do the three. The on-call half is the graded drill: a synthetic page, a triage, a mitigation, a signed runbook, and a no-blame postmortem. The postmortem is the deliverable, and it is graded on quality, not speed.

## Part A — FinOps: the three moves

### 2.0 — The FinOps mindset: inform, then optimize, then operate

FinOps is not "spend less." FinOps is "spend deliberately, with evidence, on a cadence." The loop, from the *Cloud FinOps* book, is **Inform → Optimize → Operate**: first you make the spend *visible* (the billing export), then you *optimize* it (the three moves), then you *operate* — you run the loop monthly so it does not silently rot. The single most common FinOps failure is not "we picked the wrong instance type"; it is "nobody looked at the bill for six months." Make it visible, then act.

The reason there are only three moves worth doing is that **GCP cost is dominated by a handful of SKUs.** Pareto holds hard: on almost every real workload, three or four line items are 80% of the bill. You do not optimize 200 line items; you find the top three and you attack those. Everything else is rounding error you can ignore until the big three are handled.

### 2.1 — Move zero: turn on the billing export (do this Monday)

You cannot optimize what you cannot see, and the GCP billing console is a toy — it shows you charts, not rows you can `GROUP BY`. The real instrument is the **billing export to BigQuery**, which streams every line item into a table you can query with the SQL you learned in Week 10. It takes **up to 24 hours to start populating** after you enable it, which is why this is the Monday-morning task even though the analysis is Thursday.

Enable it once, in the console (Billing → Billing export → BigQuery export → enable Standard usage cost):

```bash
# Confirm the export dataset and table exist after enabling.
# The table name is gcp_billing_export_v1_<BILLING_ACCOUNT_ID with dashes->underscores>.
bq ls --project_id="$PROJECT_ID" billing_export
# Wait up to 24h, then confirm rows exist:
bq query --use_legacy_sql=false \
  'SELECT COUNT(*) AS rows, MIN(usage_start_time) AS earliest
   FROM `'"$PROJECT_ID"'.billing_export.gcp_billing_export_v1_XXXXXX_YYYYYY_ZZZZZZ`'
```

The schema you will query (the columns that matter): `service.description` (the product — Compute Engine, BigQuery, Spanner), `sku.description` (the specific line item — "N2 Instance Core running in Americas"), `cost` (the list charge), `usage.amount` and `usage.unit`, `credits` (a *repeated* field — discounts and promotions land here, and you must `UNNEST` it), `labels` (your cost-allocation tags), and `usage_start_time` / `usage_end_time`. Exercise 3 is built entirely on these columns.

The one trap: **the real cost is `cost` plus the (negative) credits.** A line item with `cost = $100` and a sustained-use credit of `-$30` cost you $70. If you report `cost` alone you overstate the bill by the discounts you already earned. The "effective cost" expression you will reuse all week:

```sql
SELECT
  service.description AS service,
  sku.description     AS sku,
  SUM(cost) AS list_cost,
  SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS effective_cost
FROM `PROJECT.billing_export.gcp_billing_export_v1_XXXXXX`
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY service, sku
ORDER BY effective_cost DESC
LIMIT 10;
```

That query — top SKUs by effective cost over 30 days — is move zero's entire output. The top three rows are what you attack. Everything that follows is "what discount instrument fits each of those three line items."

A second query you will run often is the *daily trend per service*, because a line item that is large *and growing* is a different problem from one that is large and flat. A flat line is a candidate for a commitment; a steeply rising line is a candidate for an architectural fix before you commit to a number that will be wrong in two months:

```sql
SELECT
  service.description AS service,
  DATE(usage_start_time) AS day,
  ROUND(SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)), 2)
    AS effective_cost
FROM `PROJECT.billing_export.gcp_billing_export_v1_XXXXXX`
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY service, day
ORDER BY service, day;
```

Eyeball the trend per service. Three shapes tell you three different things: a **flat** line is your committed-use candidate (commit the floor); a **sawtooth** that drops to near-zero nightly or on weekends is a *spot* or *scale-to-zero* candidate (you are paying for idle); a **monotonically rising** line means do not commit yet — find out *why* it is growing, because a commitment sized to today's number is a loss the day the workload doubles. Reading the shape before choosing the instrument is the difference between FinOps and guessing.

The third routine query attributes cost to a `labels`-based cost center, which is how you turn a flat company bill into a per-team showback. If your resources are labeled (Week 01 taught you to label everything), this is one `UNNEST`:

```sql
SELECT
  (SELECT l.value FROM UNNEST(labels) l WHERE l.key = 'cost-center') AS cost_center,
  ROUND(SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)), 2)
    AS effective_cost
FROM `PROJECT.billing_export.gcp_billing_export_v1_XXXXXX`
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY cost_center
ORDER BY effective_cost DESC;
```

Unlabeled cost shows up as a `NULL` cost center, and a large `NULL` bucket is itself a finding: you cannot manage what you cannot attribute. The first FinOps action on a messy org is frequently "go label the resources" so this query stops returning a giant `NULL`.

### 2.2 — The three discount instruments, and which fits what

GCP has exactly three cost levers worth pulling, and each fits a different *workload shape*. Picking the wrong one wastes the saving.

**Sustained-use discounts (SUD) — automatic, no commitment, Compute only.** If a Compute Engine VM (or GKE Standard node) runs for a large fraction of the month, GCP automatically discounts it on a sliding scale — up to ~30% for a VM that runs the whole month, applied without you doing anything. You do not "buy" an SUD; you earn it by running. The FinOps action here is *negative*: do not accidentally defeat it by churning instances. Long-lived steady nodes earn SUD; constantly-recreated instances do not. (Note: SUDs apply to the older N1 family fully and to others partially; the modern families lean more on CUDs — confirm against the live SUD page.)

**Committed-use discounts (CUD) — you commit, you save 30–70%.** The big lever. You promise GCP a baseline of usage for **1 or 3 years** and get a steep discount on it. Two flavors:

- **Resource-based CUD:** you commit to a specific amount of vCPU and memory in a region. Discount is large (up to ~57% for 3-year) but the commitment is rigid — it is tied to a machine family and region.
- **Spend-based / flexible CUD:** you commit to a dollar-per-hour spend on a service (Compute, or Cloud SQL, or others). More flexible — it follows you across machine families — at a slightly smaller discount.

The CUD math is the heart of the FinOps memo. A commitment is only a saving if your *baseline* utilization — the floor below which usage never drops — exceeds the commitment, for the whole term. The breakeven question: *at what utilization does the committed price beat the on-demand price?* If a 1-year commitment is 37% off and you use the committed capacity 80% of the time, you save; if you use it 40% of the time, the commitment is *more expensive* than on-demand because you pay for the committed capacity whether you use it or not. **Never commit above your demonstrated floor.** The Python you use to compute the breakeven:

```python
def cud_breakeven_utilization(on_demand_hourly: float, committed_hourly: float) -> float:
    """Fraction of the term you must USE the committed capacity for the
    commitment to break even vs. on-demand.

    committed_hourly is paid every hour of the term regardless of use.
    on_demand_hourly is paid only for hours you actually run.
    Breakeven u solves:  committed_hourly = u * on_demand_hourly
    """
    if on_demand_hourly <= 0:
        raise ValueError("on_demand_hourly must be positive")
    return committed_hourly / on_demand_hourly


def cud_annual_saving(
    on_demand_hourly: float,
    committed_hourly: float,
    actual_utilization: float,
) -> float:
    """Annual dollar saving (positive) or loss (negative) of committing,
    given the utilization you actually expect to hit."""
    hours_per_year = 24 * 365
    on_demand_cost = on_demand_hourly * actual_utilization * hours_per_year
    committed_cost = committed_hourly * hours_per_year  # paid regardless
    return on_demand_cost - committed_cost


if __name__ == "__main__":
    # Illustrative: a node that on-demand is $0.10/hr; 1-yr CUD is $0.063/hr (37% off).
    on_demand, committed = 0.10, 0.063
    be = cud_breakeven_utilization(on_demand, committed)
    print(f"Breakeven utilization: {be:.0%}")
    for u in (0.40, 0.63, 0.80, 1.00):
        s = cud_annual_saving(on_demand, committed, u)
        verdict = "SAVE" if s > 0 else "LOSE"
        print(f"At {u:.0%} utilization: ${s:,.0f}/yr  -> {verdict}")
```

Run it: the breakeven is 63%, and at 40% utilization the "discount" loses you money. That number — *commit only above your floor* — is the entire CUD lesson.

**Spot / preemptible capacity — 60–91% off, can vanish.** For fault-tolerant, interruptible work — Dataflow workers (Week 09), GKE batch node pools (Week 06), Dataproc — spot VMs are 60–91% cheaper than on-demand. The catch is preemption: GCP can reclaim a spot VM with 30 seconds' notice. So spot is correct for work that can be *retried* (a Beam bundle, a CI job, a stateless replica behind a load balancer) and wrong for work that cannot survive an interruption (a stateful primary, a single-replica database). You already used spot for GKE node pools and Dataflow in earlier weeks; the FinOps action is to *audit which workloads could be on spot and are not.*

### 2.3 — The three moves, named

Putting the instruments to work, here are the three moves that pay back inside a quarter — the ones worth your Thursday:

**Move 1 — Find the top three line items and right-size them.** Run the §2.1 query. For each of the top three SKUs, ask: is this resource the right size? An over-provisioned Spanner instance, a BigQuery on-demand query pattern that should be a flat-rate slot reservation, a GKE node pool with 20% utilization — these are the easy wins, and they pay back *immediately* because right-sizing has no commitment and no risk. This move alone routinely finds 20–40% on a system nobody has looked at.

**Move 2 — Commit the steady-state floor.** For the compute and database baseline that *never goes to zero* — the `min-instances=1` Cloud Run capacity, the always-on GKE system pool, the production Spanner node — buy a 1-year committed-use discount sized to the demonstrated floor (not the peak). Use the breakeven math above. This pays back over the year but the *decision* is made in a quarter and the saving starts the day you commit.

**Move 3 — Move interruptible work to spot.** Audit every batch/stateless workload — Dataflow, GKE batch pools, CI runners — and move what can tolerate preemption to spot capacity. Pays back the instant you flip it.

Notice what is *not* on the list: chasing tiny SKUs, micro-optimizing a query that costs $4/month, or buying 3-year commitments on a workload you might re-architect in six months. The three moves are the three that move the number and pay back fast. Everything else is for the FinOps platform team, later.

### 2.4 — The FinOps memo

The output of the FinOps work is a one-page memo a finance partner will read, and it has exactly four parts: (1) the top three line items by effective 30-day cost, in dollars; (2) for each, the move (right-size / commit / spot) and the *estimated annualized saving in dollars*; (3) the commitment math for any CUD you propose, showing the breakeven utilization and your demonstrated floor; (4) the risk, in one sentence per move ("the 1-year CUD assumes the Spanner node stays at 1 node for the year; if we re-architect to AlloyDB in Q3 the unused commitment costs us $X"). A FinOps memo without a dollar saving and a stated risk is a wish, not a recommendation. Exercise 3 produces the SQL behind parts (1) and (2); the homework writes the full memo.

### 2.4a — FinOps anti-patterns, and the monthly operate cadence

Knowing the three moves is half the skill; the other half is recognizing the moves that *feel* productive and are not, so you do not spend a week saving four dollars. The anti-patterns that waste a FinOps engineer's time:

- **Micro-optimizing the long tail.** Chasing a SKU that costs $4/month while the top line item is $400/month. Pareto is brutal here: fix the big three, ignore the rest until the big three are handled.
- **Committing above the floor.** Buying a 3-year commitment because the discount headline is biggest, when your demonstrated utilization floor is below the breakeven. A commitment you do not use is *more* expensive than on-demand. The breakeven math (§2.2) exists to stop exactly this.
- **Spot for the wrong workload.** Putting a stateful primary or a must-always-answer service on spot to chase the 80% discount, then eating an outage when it is preempted. Spot is for retryable work only.
- **Turning off the thing instead of right-sizing it.** Deleting a dev environment to save money, then re-creating it (and re-debugging it) every sprint. Often a schedule (scale to zero nights/weekends) saves nearly as much without the friction.
- **Optimizing before measuring.** Buying commitments or resizing instances on a hunch instead of on the billing-export numbers. Every move must trace to a row in the export, or it is a guess.

And the cadence: FinOps is the **Operate** phase of Inform → Optimize → Operate, which means it is *monthly*, not one-time. The loop you run every month: (1) re-run the top-SKU query and the trend query; (2) check whether last month's commitments are being used above breakeven (a committed-use *utilization* report tells you if you over-committed); (3) catch any new large `NULL`-cost-center line (something got created unlabeled); (4) update the memo with what changed. A FinOps effort that happens once and is never repeated regresses within a quarter as new resources appear and traffic shifts. The discipline is the cadence, not the cleanup.

## Part B — On-call and the drill

### 2.5 — On-call is a process, not heroics

A good on-call rotation is designed so that a tired person who has never seen the system can do the right thing by following the runbook. That design has a few non-negotiable properties, all of which you have been building toward:

- **Page only on user-visible risk.** This is the Week 13 rule, restated: a page means "a human must act now or users suffer." Everything else is a ticket or a Slack message. A rotation that pages on CPU at 80% will be ignored within a week, and then the real page gets ignored too. Alert fatigue is a security and reliability vulnerability.
- **Every page has a runbook.** When the pager fires, the responder opens a runbook keyed to that alert: what the alert means, the first three things to check, the known mitigations, and the escalation path. A page with no runbook is a page that takes three times as long to resolve and burns out whoever holds the pager.
- **Mitigate before you diagnose.** The on-call job in the moment is to *stop the bleeding* — fail over, roll back, scale up, shed load — not to find the root cause. Root cause is the postmortem's job, done in daylight. Conflating the two is how a 10-minute incident becomes a 2-hour one.
- **The handoff is a ritual.** End of shift, you hand off: what is on fire, what is smoldering, what you changed, what to watch. A written handoff template, every time.

### 2.5a — Designing the rotation itself

Before the loop, the rotation. A few design decisions, made once, determine whether on-call is sustainable or whether your best engineers quit over it:

- **Rotation length and size.** A weekly rotation across a team of six means each engineer is on call one week in six — sustainable. A rotation of two means every other week, which burns people out and is a retention risk. If you cannot staff at least four-to-five in the rotation, you do not yet have an on-call program; you have two people heroically absorbing pages, and you should say so to your manager and fix the staffing before you formalize it.
- **Primary and secondary.** The primary takes the page; the secondary is the escalation if the primary does not acknowledge within the escalation window (commonly 5–15 minutes) or explicitly escalates. The secondary is also who the primary calls when a page is over their head. A rotation with no secondary has a single point of failure who happens to be asleep.
- **Follow-the-sun, if you can.** If you have engineers in two or three time zones, a rotation that hands off so nobody is paged at 3 a.m. local is worth more than almost any tooling. Most teams cannot do this; if you can, it is the highest-leverage on-call investment there is.
- **The operational/project-work balance.** The SRE rule of thumb is that on-call and operational toil should cap at ~50% of an engineer's time; the rest is project work that *reduces future toil*. A rotation where on-call consumes 100% of the week is a rotation that never improves, because nobody has time to fix the thing that keeps paging. Protect the project half.
- **Compensation and recovery.** On-call is work, including the nights. Whether you compensate with time-in-lieu, pay, or reduced project load, the principle is that a week of broken sleep is not free, and a program that pretends it is will not retain anyone. After a rough night, the responder gets the next morning.

These are not "nice to have." A badly designed rotation produces the same outcome as bad alert hygiene: the pager gets ignored, and then the real incident is missed. Rotation design is reliability engineering.

### 2.6 — The page → triage → mitigate → postmortem loop

The drill walks the full loop. Here is the loop with the GCP tools from Week 13 attached to each step:

1. **Page.** A burn-rate alert (Week 13) fires — say, the ingest service's error-rate SLO is burning fast. The page lands with a link to the alert, the runbook, and the relevant dashboard.
2. **Acknowledge and triage.** Open the dashboard. Is this real (users affected) or a monitoring artifact? Use **Cloud Monitoring** for the golden-signals view, **Cloud Trace** to see *where* in the request path the latency or errors appear, and **Cloud Logging** to read the actual errors. The triage question is one thing: *what changed?* A recent deploy, a traffic spike, a dependency outage, an expiring certificate.
3. **Mitigate.** Stop the bleeding with the least-risky reversible action: roll back the deploy, fail over to the standby region, scale the autoscaler floor up, or shed load with a Cloud Armor rate-limit (Week 08). Note the exact action and the timestamp — the postmortem needs the timeline.
4. **Confirm recovery.** Watch the SLO burn rate fall and the error rate return to baseline. Do not declare victory on a single green data point; watch it hold.
5. **Postmortem.** In daylight, write the no-blame postmortem. This is the deliverable.

A concrete way to internalize "mitigate before you diagnose": picture the page lands at 14:05 saying the ingest error-rate SLO is burning at 14× the budget. Your instinct as an engineer is to open the code and find the bug. That instinct is *wrong in the moment*. The right first move is the reversible mitigation that is most likely to stop the bleeding — here, `gcloud run services update-traffic ingest --to-revisions=<last-good>=100`, which rolls back in seconds. You do that, you watch the error rate fall, *then* you go find out why v1.8.2 returned 500s. The bug is still there to debug at 14:30 in the daylight; the burned error budget is not recoverable. Conflating mitigation and diagnosis is the single most common reason a junior on-call turns a 10-minute incident into a 90-minute one.

The corollary is the **alert-hygiene rule** restated for on-call, because it is what makes the loop survivable: an alert that pages must be *actionable* and *user-visible*. "Disk is 80% full" is not a page — it is a ticket, because nothing bad has happened to a user yet and there is no urgent action. "The error-rate SLO is burning fast" *is* a page, because users are seeing errors now and there is an action (roll back, fail over). A rotation that pages on non-actionable, non-user-visible signals trains its responders to ignore the pager, and a responder who has learned to ignore the pager will also ignore the one that matters. Alert fatigue is not a nuisance; it is a reliability vulnerability, and Week 13's burn-rate alerts were designed precisely to page on the symptom (user-visible error rate) rather than the cause (CPU, memory, disk).

The triage step has a decision tree worth committing to memory, because under pressure you want a default sequence rather than improvisation. The first question is always *is this real?* — is a user actually affected, or is this a monitoring artifact (a probe that broke, a metric that stopped reporting and read as zero)? Check the golden-signals dashboard; if traffic, errors, and latency all look normal to real users, you may be chasing a broken alert, and the fix is to the alert, not the service. If it *is* real, the second question is *what changed?* — and the answer is almost always one of four things, in rough order of likelihood:

1. **A recent deploy.** Check the deploy history first; most incidents trace to a change in the last hour. If a deploy correlates, the mitigation is a rollback, full stop.
2. **A traffic spike.** Check the request-rate panel. If load doubled, the mitigation is to scale the autoscaler floor up or shed load with a Cloud Armor rate-limit.
3. **A dependency outage.** Check Cloud Trace for which span is slow or erroring. If a downstream (the database, an API, the model endpoint from Week 12) is the source, the mitigation is the circuit-breaker / fallback path you built — or failing over to a replica.
4. **A resource or quota limit.** Check for `RESOURCE_EXHAUSTED` errors, expiring certificates, exhausted connection pools. The mitigation depends on the limit, but the diagnosis is in the logs.

That four-way split — deploy, load, dependency, limit — covers the overwhelming majority of pages, and having it memorized means you spend your triage minutes confirming which one it is rather than wondering where to look. The runbook for each alert should encode this: it tells the responder which of the four to check first for *that specific* alert.

### 2.7 — The synthetic fault you will inject

The drill injects a *synthetic* fault so you can practice the loop without an actual outage. The standard fault for this course: a deliberately bad deploy to the ingest service that returns HTTP 500 on 100% of requests (a one-line code change behind a feature flag, or a `min-instances=0` standby region forced to take traffic while cold). The burn-rate alert from Week 13 fires within its multi-window, you get the page, and you run the loop. The mitigation is a rollback or a region failover; the *failover* path is the paid-but-cheap opt-in because it spins the standby region's Cloud Run to `min-instances=1` for the duration. The script that injects and the script that mitigates ship in the mini-project; the drill is timed only so the postmortem has a real timeline, not because speed is graded.

### 2.8 — The no-blame postmortem: the actual deliverable

A postmortem is **blameless** as an engineering decision, not a courtesy. The premise: if a tired human following the documented process caused an outage, the *process* failed, not the human — and you fix processes, not people, because fixing the person changes nothing for the next tired human. The moment a postmortem assigns blame, people stop reporting near-misses, and you lose your best source of reliability data. Blameless is how you keep the information flowing.

A postmortem that a staff engineer will sign has these sections, and the mini-project ships this exact template:

1. **Summary.** Two sentences: what happened, what the user impact was, how long it lasted.
2. **Impact.** Quantified: how many requests/users affected, for how long, against which SLO. "We burned 40% of the monthly error budget in 22 minutes."
3. **Timeline.** Timestamped, factual, no interpretation. `14:03 deploy v1.8.2 reaches 100% traffic. 14:05 error-rate burn-rate alert fires. 14:06 on-call acknowledges. 14:11 rollback initiated. 14:14 error rate returns to baseline. 14:20 incident closed.` The timeline is the spine; write it first, from the logs and the page history, before you write anything interpretive.
4. **Contributing factors (not "root cause").** Mature postmortems list *contributing factors* because complex-system failures rarely have a single root cause — they have several factors that lined up. "The deploy had no canary stage" AND "the burn-rate alert window was 5 minutes, so detection lagged" AND "the rollback runbook was out of date." Each factor is a place to intervene.
5. **What went well.** Genuinely — the alert fired, the rollback worked, the runbook was followed. This is not filler; it tells you which investments are paying off.
6. **Action items.** Each with an **owner** and a **due date**. "Add a canary stage to the ingest deploy pipeline — @you — by 2026-06-20." An action item without an owner and a date is a wish. This is the single most-checked section in a postmortem review: are the action items concrete, owned, and dated?
7. **Lessons learned.** The one-paragraph generalizable insight other teams should steal.

The grading rubric for the drill (5% of the course) is entirely about sections 3, 4, and 6: is the timeline factual and complete, do the contributing factors go beyond "the deploy was bad" to the systemic factors, and are the action items owned and dated? A fast mitigation with a shallow, blamey postmortem fails. A slow mitigation with a deep, blameless, well-actioned postmortem passes with room to spare.

Here is a worked, abbreviated example so you have a model — this is the standard the mini-project's postmortem is held to:

```markdown
# Postmortem — Ingest 500s, 2026-06-12

## Summary
A bad ingest deploy (v1.8.2) returned HTTP 500 on all requests for 11 minutes.
~6,400 ingest requests failed; no data was lost (Pub/Sub retried after rollback).

## Impact
100% of ingest traffic errored for 11 minutes (14:03–14:14 UTC). Burned ~38%
of the ingest service's monthly error budget. No downstream data loss: the
publisher retried and the DLQ stayed empty after recovery.

## Timeline (UTC)
- 14:03  v1.8.2 reaches 100% traffic (no canary stage).
- 14:05  Fast-window burn-rate alert fires; on-call paged.
- 14:06  On-call acknowledges; opens the ingest SLO dashboard.
- 14:08  Cloud Trace shows 500s originate in the ingest handler, not a dependency.
- 14:09  Cloud Logging shows a NullPointer in the v1.8.2 request parser.
- 14:11  Rollback to v1.8.1 initiated (update-traffic to last-good revision).
- 14:14  Error rate returns to baseline; burn-rate alert clears.
- 14:20  Incident closed after error rate holds green for 6 minutes.

## Contributing factors
- The ingest deploy pipeline has no canary stage; a bad revision goes to 100%
  traffic immediately.
- The new request parser had no unit test for the null-field case that crashed.
- The fast-window burn-rate alert is 5 minutes wide, so detection lagged the
  deploy by ~2 minutes.

## What went well
- The burn-rate alert fired correctly and paged on a user-visible symptom.
- The rollback runbook was current; mitigation took under 3 minutes once paged.
- Pub/Sub retry meant zero data loss despite the outage.

## Action items
| Action | Owner | Due |
|---|---|---|
| Add a 10%/5-min canary stage to the ingest deploy pipeline | @platform | 2026-06-20 |
| Add a null-field unit test to the ingest parser | @ingest-team | 2026-06-16 |
| Add a 1-min fast burn-rate window alongside the 5-min one | @platform | 2026-06-23 |

## Lessons learned
A deploy that goes straight to 100% traffic turns every bug into a full outage.
The single highest-leverage fix is the canary stage — it would have caught this
at 10% traffic with a tenth of the impact.
```

Notice what makes this pass: the timeline is purely factual with no blame, the contributing factors are *three systemic process gaps* (no canary, no test, slow detection) rather than "an engineer wrote a NullPointer," and every action item is owned and dated. That is the shape the grader is looking for.

### 2.9 — The runbook contract and sign-off

Alongside the postmortem you sign off a **runbook** for the alert that fired. A runbook is not a wiki page nobody trusts; it is a *tested* document with a contract:

- **Trigger:** the exact alert this runbook answers ("ingest error-rate burn-rate, fast window").
- **Meaning:** what the alert means in one sentence, in user terms.
- **First checks:** the three dashboards/queries to open, in order.
- **Mitigations:** the reversible actions, most-likely-to-work first, each with the exact command.
- **Escalation:** who to call, and when (after N minutes, or if the mitigation fails).
- **Verification:** how you know it is fixed.

"Sign off" means *you ran the drill, followed this runbook, and it worked* — and where it did not, you fixed the runbook before signing. A signed runbook is one that has caught a real (even synthetic) page. An unsigned runbook is fiction.

### 2.9a — Severity, and when a page becomes an "incident"

Not every page is an incident. A page you acknowledge, mitigate in three minutes, and close is just a page. An *incident* is when the impact is large enough or long enough that you need to coordinate — pull in others, communicate to stakeholders, and run a formal postmortem. Teams encode this with a severity scale; a common shape:

- **SEV-3** — minor, single-service degradation, no broad user impact. The on-call handles it solo; a lightweight postmortem if anything was learned.
- **SEV-2** — significant user-facing impact or a burned SLO budget. The on-call may pull in the secondary; a full postmortem is required.
- **SEV-1** — major outage, broad user impact, possible data loss or security exposure. You declare an incident, assign an incident commander (even if that is just you naming yourself), open a comms channel, and the postmortem is mandatory and reviewed.

The synthetic drill in this course is scoped as a SEV-2: one service down, a measurable SLO burn, mitigable by one engineer, full postmortem required. The point of naming the severity is that it sets expectations — a SEV-1 needs comms and an IC; a SEV-3 does not — and prevents both under-reacting to a real outage and over-reacting to a blip. When you run the drill, state the severity in your postmortem's summary; it is the first thing a reviewer wants to know.

The other half of "when does a page become an incident" is *declaring* it out loud. The failure mode is the silent struggle: one engineer fighting a growing outage for forty minutes without telling anyone, because "I almost have it." Declare early. Declaring an incident costs little (a message in a channel) and buys you help and a record; not declaring costs you the forty minutes and the institutional memory. The senior habit is to declare *sooner* than feels necessary and stand it down if it turns out minor.

### 2.10 — The teardown gate

The drill's failover step costs real money while the standby region runs warm. The teardown gate, graded as always: after the drill, scale the standby back to `min-instances=0`, confirm no warm replicas remain, and confirm the billing export shows the spend stopped. The marker:

```bash
gcloud run services describe ingest-standby --region="$STANDBY_REGION" \
  --format='value(spec.template.metadata.annotations["autoscaling.knative.dev/minScale"])'
# Expect: 0  (or empty)
gcloud run services list --region="$STANDBY_REGION" \
  --format='value(metadata.name, status.traffic[0].percent)'
# Confirm the standby is at 0% traffic and minScale 0.
```

If the standby is still warm at end of session, you are still paying — fix it before you stop for the day.

### 2.11 — Putting it together

The week is now whole. You changed the five dangerous defaults and verified each deny (Lecture 1). You made the spend visible, found the top three line items, and proposed three moves with dollar savings and a breakeven (Part A). You ran the page → triage → mitigate → confirm → postmortem loop, signed a runbook, and wrote the postmortem the cohort uses as its template (Part B). The mini-project welds all of it onto the Week-01–13 system: a hardened, cost-reported, drilled, postmortemed production posture, torn down clean.

### 2.12 — What to take into Week 15

Week 15 is delivery. Carry three things forward:

1. **Make it visible, then act, on a cadence.** FinOps is a monthly loop, not a one-time cleanup. The billing export query is the instrument; the three moves are the actions; the memo is the artifact.
2. **Commit only above your demonstrated floor.** A committed-use discount below the floor is a saving; above it, it is a loss you pay for all year. The breakeven number is the whole decision.
3. **The postmortem is the deliverable, and it is blameless by design.** Timeline first, contributing factors not root cause, action items owned and dated. The signed runbook is the receipt that says you can survive the night.

Now go run Exercise 3 — find your top three line items — and then the challenge, where you wrap the perimeter, require Binary Authorization, run the drill, and write the postmortem you will defend in Week 15.

One last framing to carry: FinOps and on-call are the two disciplines that separate "I can build it" from "I can own it." Anyone can stand up a system; the engineer who gets the senior title is the one who can also tell you what it costs, where the money is going, and exactly what they will do when it breaks at 3 a.m. — with a runbook they have tested and a postmortem culture that makes the system better after every incident instead of just assigning blame. That is the posture Week 15 asks you to defend.

---

**References**

- Export Cloud Billing data to BigQuery: <https://cloud.google.com/billing/docs/how-to/export-data-bigquery>
- Standard usage cost export schema: <https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage>
- Committed use discounts: <https://cloud.google.com/docs/cuds>
- Sustained use discounts: <https://cloud.google.com/compute/docs/sustained-use-discounts>
- Spot VMs: <https://cloud.google.com/compute/docs/instances/spot>
- Google SRE Book — Postmortem Culture: <https://sre.google/sre-book/postmortem-culture/>
- Google SRE Book — Being On-Call: <https://sre.google/sre-book/being-on-call/>
- Example postmortem: <https://sre.google/sre-book/example-postmortem/>
- Cloud FinOps (Storment & Fuller, O'Reilly).
