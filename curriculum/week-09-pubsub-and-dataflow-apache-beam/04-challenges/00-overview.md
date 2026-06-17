# Week 9 — Challenges

One stretch problem this week. It is harder than the exercises and there is **no solution provided** — only acceptance criteria. It is also the dress rehearsal for the mini-project and, by extension, the capstone's stream/process tiers. Budget the full 2 hours; the validation (killing workers and proving correctness) is the part that teaches.

## Index

1. **[Challenge 1 — Kill the workers, prove exactly-once](./challenge-01-kill-the-workers.md)** — Build the full streaming pipeline (synthetic generator → Pub/Sub → Dataflow Python Beam → BigQuery) with a dead-letter topic for malformed events, run it for 30 minutes, kill the Dataflow workers mid-stream, and prove from the BigQuery row counts that no data was lost and nothing was double-counted. (~2h, paid-but-cheap)

## Ground rules

- **No solution is checked in.** Acceptance criteria only. If you can satisfy them, you understand the material.
- **You may** reuse your Week 04 Terraform modules, the lecture code, and the exercise scaffolding.
- **You may NOT** use the prebuilt Pub/Sub-to-BigQuery Dataflow *template* as your processing tier — you write the Beam pipeline yourself. (You may read the template's source for ideas.)
- **Cost.** This challenge runs real Dataflow workers for ~30–45 minutes. On the smallest worker with Streaming Engine and a teardown at the end, expect well under a dollar. **Arm your budget alert before you start, and run the teardown gate the moment you're done.** A forgotten streaming job is the single most expensive mistake in C18.

## The teardown gate is the deliverable

Both the challenge and the mini-project end with:

```
$ python validate.py            # confirms BigQuery has exactly what was published
$ terraform destroy -auto-approve
Destroy complete!
```

If you skip the teardown, you failed the challenge — and you'll find out on the bill.
