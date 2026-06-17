# Challenge 1 — Keyless Deploys with WIF, Then a Second Provider

> **Estimated time:** 3–4 hours. Worth far more than its time-cost suggests: this is the single most reused artifact in the whole course. Every later week's CI deploy runs on what you build here, and "I set up keyless WIF deploys" is a real hiring signal you can point at on GitHub.

You will take a repository that currently deploys to GCP with a downloaded service-account key, rip the key out entirely, replace it with Workload Identity Federation from GitHub Actions, and then prove the same SA can also be reached from a *second* identity provider — GitLab CI **or** a non-GCP Kubernetes cluster — without either provider ever holding a long-lived secret.

This is open-ended. There is no fill-in-the-blank. Use Lecture 2 (§2.5–2.7), the exercises, and `resources.md`.

---

## Part 0 — The starting point (the thing you're replacing)

Create (or use) a GitHub repo that deploys *something small* to GCP — copying an artifact to a bucket is enough. Wire it up the **old, wrong way first**, so you have a "before" to delete:

```yaml
# .github/workflows/deploy.yml  — THE BAD VERSION you will delete
- uses: google-github-actions/auth@v2
  with:
    credentials_json: ${{ secrets.GCP_SA_KEY }}   # <-- a downloaded JSON key. This is the wound.
- run: gcloud storage cp ./artifact.txt gs://my-deploy-artifacts/
```

Confirm it works with the key, then commit the "before" state on a branch. You will diff against it. (If your org policy already bans key creation from Exercise/Lecture work, you can simulate the "before" by describing it — but most learners will have a project where they can still create one key for this single demonstration. Delete it the moment Part 1 is green.)

---

## Part 1 — Replace the key with GitHub Actions WIF

End state: the repo's deploy workflow authenticates to GCP with **zero secrets**, OIDC-only.

What you must build (Terraform preferred; `gcloud` acceptable if you document every command):

- A workload identity pool and an **OIDC provider** trusting `https://token.actions.githubusercontent.com`.
- An **attribute mapping** that maps at least `assertion.sub`, `assertion.repository`, and `assertion.ref`.
- An **attribute condition** that admits *only* tokens from your repository. A missing condition is an automatic fail — a provider with no condition trusts every repo on GitHub.
- A deploy service account with the **minimum** roles to do the deploy (use a predefined role like `roles/storage.objectAdmin` scoped to the one bucket via a condition, or a custom role — do not use `roles/editor`).
- A `roles/iam.workloadIdentityUser` binding on that SA, granted to a `principalSet://` scoped to your repository (and, for full credit, to `main` only).
- The rewritten workflow with `permissions: id-token: write` and `google-github-actions/auth@v2` configured with `workload_identity_provider` + `service_account` and **no** `credentials_json`.

Then:

- Delete the `GCP_SA_KEY` secret from the repo.
- If you created a real SA key in Part 0, **disable and delete it** and confirm with `gcloud iam service-accounts keys list --managed-by=user` (no output).
- Push to `main`; the keyless deploy must succeed.

---

## Part 2 — Prove the gates hold (the half that's actually security)

A working keyless deploy is necessary but not sufficient. Demonstrate, with evidence in your writeup, that the access is *scoped*:

1. **Foreign repo is rejected.** Fork the repo (or use a second repo you own) and run the same workflow. The `auth` step must fail because the attribute condition rejects the foreign `repository` claim. Capture the failure log.
2. **Wrong branch is rejected (full credit).** If you scoped the binding/condition to `main`, run the workflow from a feature branch and show the `workloadIdentityUser` check denies it. Capture the log.
3. **The SA is least-privilege.** Run Exercise 3's audit tool (or `gcloud asset analyze-iam-policy`) against the project and show the deploy SA does *not* hold any basic role and cannot do anything beyond the deploy.

---

## Part 3 — Add a second provider

Pick **one** and wire it into the *same* pool (or a second pool — your call, document the choice):

### Option A — GitLab CI

- Add an OIDC provider trusting `https://gitlab.com` (or your self-managed instance's issuer).
- Map `assertion.project_path` and gate the attribute condition on your exact project path.
- On the GitLab side, declare an `id_token` with the provider's full resource name as the `aud`, exchange it, and run the same deploy.
- Bind a `principalSet://` for `attribute.project_path/<your-group/project>` to the deploy SA.

### Option B — Non-GCP Kubernetes cluster (the harder, more impressive path)

- Stand up a `kind` cluster (or use any cluster you control). Expose its OIDC discovery document (`/.well-known/openid-configuration` and the JWKS) at a URL GCP can fetch — a public GCS bucket or a small static host works.
- Add an OIDC provider with that `issuer_uri`.
- Map `assertion.sub` (which is `system:serviceaccount:<ns>:<name>`) and gate the attribute condition on your exact namespace and SA.
- From a pod using a *projected* service-account token (`audience` set to the provider resource name), exchange the token and run the deploy.

For either option, prove the *same* deny tests: a wrong project path / wrong namespace is rejected.

---

## Acceptance criteria

- [ ] The GitHub repo contains **zero** long-lived GCP credentials. No `credentials_json`, no committed JSON, no `GCP_SA_KEY` secret.
- [ ] `gcloud iam service-accounts keys list --managed-by=user` prints nothing for the deploy SA.
- [ ] The GitHub Actions deploy succeeds via WIF (OIDC-only), with `id-token: write` permission and an attribute-conditioned provider.
- [ ] The deploy SA holds **no basic role**; its roles are predefined-scoped or custom and sufficient for exactly the deploy.
- [ ] A **foreign repo** running the same workflow is **denied** — log captured.
- [ ] (Full credit) A **non-`main` branch** is denied — log captured.
- [ ] A **second provider** (GitLab CI or non-GCP K8s) reaches the same SA keylessly, with its own attribute condition.
- [ ] The second provider's **wrong scope** (project path / namespace) is denied — log captured.
- [ ] A short `CHALLENGE.md` writeup with: an architecture sketch of the token exchange, the Terraform/commands you ran, and the captured deny logs.

---

## What "good" looks like

A reviewer reading your `CHALLENGE.md` should be able to answer, from your evidence alone:

- *Which exact tokens can reach this SA?* (Answer: tokens from repo X on branch main, and tokens from GitLab project Y / K8s SA Z — nothing else.)
- *What happens to every other token?* (Answer: rejected at the attribute condition or the `principalSet` binding, with a log to prove it.)
- *Where is the long-lived secret?* (Answer: there isn't one.)

If your writeup makes those three answers obvious, you've internalized the keyless model and you're ready to run every later week's deploys on it.

---

## Stretch (no extra credit, pure growth)

- Add a **third** provider so you have GitHub + GitLab + K8s all reaching the same SA, and write the single `principalSet`/condition matrix that governs all three.
- Add a log-based **alert** that fires whenever the deploy SA is impersonated from an unexpected provider, so a future misconfiguration pages you instead of silently granting access.
