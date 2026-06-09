# Week 13 — Challenges

One challenge this week, and it is the heart of the week: instrument the entire fleet you built in Weeks 06–12 and prove the alerting works by breaking a service on purpose. No solution is provided — only acceptance criteria. Budget about **3 hours** (it can run longer if your Week 06–12 services need waking up first).

| # | File | What you do | Est. time |
|---|------|-------------|-----------|
| 1 | [challenge-01-instrument-the-fleet.md](./challenge-01-instrument-the-fleet.md) | Instrument every service from Weeks 06–12 with OpenTelemetry, export to Cloud Trace + Cloud Logging + Cloud Monitoring, define one SLO per service with a multi-window burn-rate alert, then validate by injecting a 1% error rate into one service and confirming the right alert pages. | 3h+ |

This challenge is deliberately the on-ramp to the mini-project: the mini-project takes the same fleet, adds the portfolio writeup and the PCA/DevOps diagnostic, and formalizes the teardown gate. If you do the challenge well, the mini-project is mostly polish and prose. Do not treat them as separate work — the challenge *is* the first 60% of the mini-project.

## Why no solution is provided

By Week 13 you own these services. There is no single right SLO target for your Week 11 database tier or your Week 12 Vertex endpoint — the right answer depends on what you built and what promise it should make. A provided solution would be a guess at your architecture. The acceptance criteria are precise about *what* must be true (one SLO per service, multi-window burn-rate alert, validated by injection); *how* you get there is the judgment this week trains. If you are stuck, the lecture notes and the three exercises contain every technique you need — the challenge is assembly, not invention.
