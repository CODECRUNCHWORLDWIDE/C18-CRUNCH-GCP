# Week 8 — Exercises

Three exercises, in order. Each builds a layer of the edge from Lecture 1 and ends with a **proof**, not a claim — a `curl`, a `hey` run, or a log query that shows the layer doing its job. Do them in order: Exercise 2 attaches its Cloud Armor policy to the load balancer Exercise 1 builds, and the challenge welds all three onto the real Week 07 Cloud Run service.

Budget ~7 hours total. Honor the teardown step at the end of each — a global LB with an orphaned forwarding rule and a reserved IP is a slow, quiet cost.

| # | File | What you build | Proof of done |
|---|------|----------------|---------------|
| 1 | [exercise-01-global-https-lb-with-cloud-run-neg-and-cdn.md](./exercise-01-global-https-lb-with-cloud-run-neg-and-cdn.md) | A global external HTTPS LB with a serverless NEG → Cloud Run, a Google-managed cert, and Cloud CDN attached. Guided, with starter + solution Terraform. | `curl https://<host>/` returns 200 over HTTPS; a second request to a cacheable path shows `Age:` > 0 and `cacheHit: true` in the logs. |
| 2 | [exercise-02-cloud-armor-ratelimit-and-sqli.tf](./exercise-02-cloud-armor-ratelimit-and-sqli.tf) | A Cloud Armor policy — a per-source-IP `rate_based_ban` rule and a preconfigured SQLi WAF rule — attached to the Exercise 1 backend service. Runnable Terraform with the validation runbook inline. | `hey` drives 429s past the threshold; `curl '...?q=1 OR 1=1'` returns 403; both appear in the Cloud Armor logs at the right priorities. |
| 3 | [exercise-03-iap-group-gated-internal-app.py](./exercise-03-iap-group-gated-internal-app.py) | A FastAPI internal app that **verifies the IAP-signed JWT**, plus the Terraform + `gcloud` to put IAP in front and gate it on a Google group. | An un-logged-in request is redirected to Google login; a member of the group gets through and the app prints their verified email from the JWT; a non-member gets 403. |

## Conventions

- **Region:** `us-central1` for regional resources; the global LB resources are, by definition, global. Pin everything else to `us-central1` to stay in the free-trial region.
- **Project:** every command takes `$(gcloud config get-value project)` or a `-var project_id=...`. Set your project once: `gcloud config set project YOUR_PROJECT`.
- **DNS:** if you own a domain, use a real hostname. If you do not, the exercises show the `sslip.io` wildcard path (`<LB_IP>.sslip.io`) so you can still get a Google-managed cert. Both paths are spelled out in Exercise 1.
- **Teardown:** each exercise ends with `terraform destroy` (or the `gcloud` deletes). Run it. The grader for the mini-project will check that you can re-`apply` from clean, which a half-destroyed state breaks.
- **Tools:** `gcloud >= 470`, `terraform >= 1.9` (or `tofu >= 1.8`), `curl`, `hey` (`go install github.com/rakyll/hey@latest`), `dig`. Verify with the smoke check at the top of Exercise 1.

A SOLUTIONS-style annotated walkthrough is embedded in each exercise file (Exercise 1 has the full starter→solution diff; Exercises 2 and 3 are runnable artifacts with the solution inline and the runbook at the bottom). There is no separate `SOLUTIONS.md` this week — the proofs are the solution.
