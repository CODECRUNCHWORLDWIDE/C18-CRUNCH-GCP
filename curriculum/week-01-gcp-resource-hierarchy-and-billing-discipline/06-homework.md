# Week 1 Homework

Six problems that apply the week's concepts beyond the exercises and mini-project. The full set should take about **5.5 hours**. Work in your Week 1 Git repository so each problem produces at least one commit you can point to later.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

---

## Problem 1 — `gcloud` environment audit

**Problem statement.** Run the following and write the relevant pieces into `notes/gcloud-audit.md`:

1. `gcloud version` — the SDK version and the components installed.
2. `gcloud config configurations list` — every named configuration and which is active.
3. `gcloud auth list` — every credentialed account and which is active.
4. `gcloud organizations list` — your org ID, or a note that you are running orphan (gmail-only).
5. `gcloud billing accounts list` — your billing account ID (mask the last group of digits if you commit this publicly).

Then answer in one sentence: *if I run `gcloud projects create foo` right now with no `--folder` and no `--organization`, where does the project land in the hierarchy, and why is that a problem for a company (but acceptable for this course)?*

**Acceptance criteria.**

- File `notes/gcloud-audit.md` exists with the five outputs and the one-sentence answer.
- Sensitive IDs are masked if the repo is public.
- Committed.

**Hint.** An orphan project (created with no parent) has no organization, so org-wide IAM and org policy cannot reach it. For a course that is fine; for a company it means you cannot govern it.

**Estimated time.** 20 minutes.

---

## Problem 2 — Map a *different* org chart

**Problem statement.** Take the `exercise-02-map-the-org-chart.py` modeler and feed it a **different** org. In `homework/p2-org/org.py`, define a new `SAMPLE_ORG` for a fictional media company "Riff" with:

- A `studio` business unit with teams `editing` (dev, prod) and `rendering` (dev, staging, prod).
- A `distribution` business unit with teams `cdn` (prod) and `catalog` (dev, prod).
- A `platform` business unit with teams `network` (shared) and `security` (shared).

Reuse the `build_tree`, `project_id_for`, and rendering functions (import them or copy them). Produce the ASCII tree and the justification table for Riff.

Then write `homework/p2-org/writeup.md`: one paragraph defending why `cdn` has only a `prod` environment (no dev), and one paragraph on whether `security` belongs in `shared/` or deserves its own top-level folder.

**Acceptance criteria.**

- `python3 homework/p2-org/org.py` prints a tree and table for Riff with no exception.
- The `studio/rendering` subtree shows three environment projects; `distribution/cdn` shows one.
- `writeup.md` addresses both questions in separate paragraphs.
- Committed.

**Hint.** The only thing that changes is the input `SAMPLE_ORG` tuple; the tree-builder and renderer are identical. For the `security` question: a top-level `security/` folder is defensible when its org policy and access posture differ sharply from the rest of `platform`.

**Estimated time.** 1 hour.

---

## Problem 3 — A second budget threshold consumer

**Problem statement.** Extend the Slack-router function from Exercise 1. In `homework/p3-router/main.py`, add behavior so that:

- At a **forecasted** 100% crossing (the `FORECASTED_SPEND` rule), the message is prefixed with `:crystal_ball: FORECAST` instead of the actual-spend emoji.
- The Slack message includes the **billing period start date** (`costIntervalStart`) formatted as `YYYY-MM-DD`.

You must distinguish forecasted from actual notifications. The budget notification JSON includes a `forecastThresholdExceeded` field for forecasted rules (vs. `alertThresholdExceeded` for actual). Handle both.

Write three unit tests in `homework/p3-router/test_router.py` (use `pytest` or `unittest`) that assert the formatting for: an actual 90% message, an actual 100% message, and a forecasted 100% message.

**Acceptance criteria.**

- `main.py` distinguishes forecasted from actual and formats each correctly.
- Three passing tests covering the three cases.
- The no-threshold first-message guard from Lecture 2 is preserved (a message with neither field is skipped).
- Committed.

**Hint.** Branch on which key is present:

```python
if "forecastThresholdExceeded" in note:
    threshold = float(note["forecastThresholdExceeded"]); prefix = ":crystal_ball: FORECAST"
elif "alertThresholdExceeded" in note:
    threshold = float(note["alertThresholdExceeded"]); prefix = _emoji_for(threshold)
else:
    return  # the hello message; skip
```

`costIntervalStart` is an ISO timestamp; `datetime.fromisoformat(...).date().isoformat()` gives the date.

**Estimated time.** 1 hour.

---

## Problem 4 — Quota reconnaissance

**Problem statement.** Pick one of your real lab projects (the alerting project from Exercise 1 is fine). Without requesting any increase, document its current quota posture in `notes/quota-recon.md`:

1. The CPU allocation quota in `us-central1` (`gcloud compute regions describe`).
2. The number of in-use external IP addresses allowed in that region.
3. One **rate** quota you can find for an API you enabled (look in the Console → IAM & Admin → Quotas, or `gcloud services quota` if available in your SDK).

Then answer: *Your Week 5 lab will deploy a regional managed instance group that wants 30 vCPUs in `us-central1`. Based on the quota you just read, will it succeed on this project today? If not, which quota blocks it, and is hitting that quota a billing event or a creation-blocking event?*

**Acceptance criteria.**

- `notes/quota-recon.md` lists the three quota values with the commands used.
- The Week-5 answer correctly identifies whether the CPU quota blocks a 30-vCPU MIG, names the quota, and states that hitting an allocation quota *blocks creation* (it does not cost money).
- Committed.

**Hint.** A fresh project commonly allows only 8–24 CPUs per region by default. `gcloud compute regions describe us-central1 --format="value(quotas)"` dumps them; filter for `metric=CPUS`.

**Estimated time.** 45 minutes.

---

## Problem 5 — The "budget vs. cap" decision memo

**Problem statement.** Write a one-page decision memo at `notes/budget-vs-cap.md` that a hypothetical platform team could adopt as policy. It must answer, with reasoning:

1. For each of these four projects, decide **alert-only** or **hard-cap (auto-disable billing)**, and justify: (a) a developer's personal sandbox, (b) a shared CI/build project, (c) the production payments database project, (d) a one-off data-migration project that runs for a weekend.
2. State the single rule of thumb your decisions follow.
3. Name one failure mode of an over-aggressive hard cap on the wrong project.

**Acceptance criteria.**

- `notes/budget-vs-cap.md` exists with all four projects classified and justified.
- The rule of thumb is stated explicitly (it should resemble "cap only what you can afford to have abruptly killed").
- The failure mode is concrete (e.g. "auto-disabling billing on the prod database during a traffic spike causes a hard outage and possible data loss").
- Committed.

**Hint.** Lecture 2 §7 gives you the decision rule. The sandbox and the weekend migration are good cap candidates; the payments DB never is.

**Estimated time.** 45 minutes.

---

## Problem 6 — Reflection essay

**Problem statement.** Write a 350–450 word reflection at `notes/week-01-reflection.md` answering:

1. Which mental model was hardest to update from your prior cloud (most likely AWS): "account == project," "the account is the wall," or "the bill is part of the account"? Why?
2. The course makes Exercise 1 (arm the budget) mandatory and gating. Having done it, do you agree it should gate everything, or is that overkill? Defend your position.
3. If you had to explain the GCP resource hierarchy to a colleague in one paragraph, using only the words organization, folder, project, and billing account, what would you say?
4. What is one thing about GCP billing or quotas that surprised you this week?

**Acceptance criteria.**

- File exists, 350–450 words.
- Each numbered question is addressed in its own paragraph.
- Committed.

**Hint.** This is for *you*, not for a grade. Be honest. Future-you reading it in Week 14 (FinOps) will be grateful you wrote down what surprised you now.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 20 min |
| 2 | 1 h 0 min |
| 3 | 1 h 0 min |
| 4 | 45 min |
| 5 | 45 min |
| 6 | 30 min |
| **Total** | **~4 h 20 min** |

(The remaining ~1h of the week's homework budget is reading the linked primary sources in `resources.md`.)

## Rubric

| Criterion | Weight | What "great" looks like |
|-----------|-------:|-------------------------|
| Correctness | 35% | Quota/billing facts are right; the modeler runs; the router tests pass |
| Reasoning quality | 30% | Memos and writeups argue from *access + policy* and *blast radius*, not vibes |
| Code hygiene | 15% | Python is idiomatic, tested, and runs with no third-party deps beyond `requests`/`pytest` |
| Evidence | 10% | Real command outputs pasted, not paraphrased; IDs masked where public |
| Completeness | 10% | All six problems committed with sensible messages |

When you've finished all six, push your repo and open the [mini-project](./07-mini-project/00-overview.md) if you haven't already.
