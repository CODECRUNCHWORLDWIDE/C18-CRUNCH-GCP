# Week 8 — Challenges

One challenge this week. It is harder and more open-ended than the exercises: no step-by-step, just a goal, acceptance criteria, and the proofs you must produce. It welds Exercises 1 and 2 onto the **real Week 07 Cloud Run service** (not the toy origin) and makes you validate the whole edge under sustained load.

No solution is provided — acceptance criteria only. That is the point: by Week 8 you assemble the edge from the primitives, and "it works" means you can *show* it works under load, not assert it.

| # | File | What you prove |
|---|------|----------------|
| 1 | [challenge-01-front-week07-with-armor-and-validate-under-load.md](./challenge-01-front-week07-with-armor-and-validate-under-load.md) | The Week 07 Cloud Run service, fronted by a global HTTPS LB + Cloud CDN + a per-IP rate limit + a SQLi WAF rule, validated with `hey` under sustained load (p99 holds, 429s appear at the threshold) and a malformed `curl` the WAF blocks — all evidenced in the Cloud Armor logs. |

Budget ~3 hours. Honor the teardown gate; this challenge stands up a full edge in front of a real service and a forgotten forwarding rule bills you.
