# Lecture 2 — Impersonation vs. Workload Identity Federation: Ending the Keyfile Era

> **Reading time:** ~80 minutes. **Hands-on time:** ~60 minutes (you impersonate an SA, then stand up a real WIF pool).

Lecture 1 named the five mistakes. Two of them — key-file sprawl (#2) and `serviceAccountUser` confusion (#5) — are really the same wound: people reach for long-lived credentials because the short-lived path looks scary. This lecture removes the fear. By the end you can mint a short-lived token *as* a service account from your laptop without a key file, you understand the OAuth token-exchange that makes Workload Identity Federation work, and you can stand up a WIF pool that lets a GitHub Actions workflow deploy to GCP with **zero** long-lived secrets in the repo.

This is the most important lecture in Phase 1. The keyless deploy path you build here is the one every later week assumes. By Week 4 your Terraform runs on it. By the capstone, *every* automated path into GCP is OIDC-federated. We start with the human case (impersonation) because it's the simplest token exchange, then generalize to the workload case (federation).

## 2.1 — What a service-account key file actually is, and why it must die

When you run `gcloud iam service-accounts keys create key.json --iam-account=sa@p.iam.gserviceaccount.com`, GCP generates an RSA key pair, keeps the public half, and hands you the private half as JSON:

```json
{
  "type": "service_account",
  "project_id": "my-project",
  "private_key_id": "a1b2c3...",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n",
  "client_email": "sa@my-project.iam.gserviceaccount.com",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

That private key is a **bearer credential that does not expire.** Anyone holding this file can sign a JWT, exchange it at `token_uri` for an access token, and act as the SA — from any IP, at any time, forever, until a human disables the key. It does not rotate on its own. It cannot be scoped to a network or a time window after issuance. It is the cloud equivalent of a house key that also works on every other door you own and can be photocopied silently.

The failure modes are not hypothetical:

- The key gets committed to a repo (public or private — private repos leak too, via forks, CI logs, and laptops).
- The key sits in a CI secret store that a compromised build step exfiltrates.
- The key is copied onto three developer laptops, one of which is stolen.

GitHub's secret scanning, GitGuardian, and TruffleHog all find these constantly. The industry consensus in 2026 is unambiguous: **do not create service-account key files.** Google's own best-practices doc says it; the org policy `iam.disableServiceAccountKeyCreation` enforces it. The rest of this lecture is the two things you do instead.

## 2.2 — Impersonation: the human and the chain

When *you* (a human, or a CI job that already has *some* GCP identity) need to act as a service account, you don't download its key. You ask GCP to mint a **short-lived token** for that SA on your behalf. This is impersonation.

The permission that allows it is `roles/iam.serviceAccountTokenCreator`, granted **on the target SA resource** (mistake #5: never at the project). Once you hold it, every `gcloud` command takes a flag:

```bash
gcloud storage ls gs://reports-bucket \
  --impersonate-service-account=reporter@my-project.iam.gserviceaccount.com
```

Under the hood, `gcloud` calls `iamcredentials.googleapis.com`'s `generateAccessToken`, presenting *your* identity and the target SA's email. GCP checks that *you* hold `serviceAccountTokenCreator` on that SA, and if so returns an OAuth2 access token valid for up to one hour. The command then runs as the SA. Nothing was downloaded. The token expires in minutes. There is nothing to leak.

You can make impersonation the default for a whole `gcloud` configuration so you don't repeat the flag:

```bash
gcloud config set auth/impersonate_service_account \
  reporter@my-project.iam.gserviceaccount.com
```

And from application code with the Python client library, you wrap your own credentials in an impersonation layer — no key file in sight:

```python
import google.auth
from google.auth import impersonated_credentials
from google.cloud import storage

# Your own credentials — from `gcloud auth application-default login`,
# from a GKE Workload Identity, or from a WIF token. No key file.
source_credentials, _ = google.auth.default()

target = impersonated_credentials.Credentials(
    source_credentials=source_credentials,
    target_principal="reporter@my-project.iam.gserviceaccount.com",
    target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
    lifetime=600,  # seconds; max 3600
)

client = storage.Client(credentials=target, project="my-project")
for blob in client.list_blobs("reports-bucket"):
    print(blob.name)
```

**Impersonation chains.** You can impersonate through a chain: A may impersonate B, B may impersonate C, so A can reach C by hopping. You pass the intermediate principals via `--impersonate-service-account=B,C` (or `delegates=[...]` in code). This is powerful and dangerous — each hop is a `serviceAccountTokenCreator` grant, and a chain is exactly as strong as its weakest link. Audit chains the same way you audit `serviceAccountUser`: they should be short, deliberate, and resource-scoped.

**`TokenCreator` vs. `serviceAccountUser`, one more time**, because it's mistake #5 and you will be asked in the quiz:

- `roles/iam.serviceAccountTokenCreator` — *mint a token as* the SA. Used for impersonation (this section) and for WIF (next section). The keyless verb.
- `roles/iam.serviceAccountUser` — *attach / run as* the SA on a new resource (deploy a VM or Cloud Run service that uses it). Used at deploy time. Different verb, different blast radius.

Both are granted on the SA resource, never the project.

## 2.3 — Workload Identity Federation: the model

Impersonation solves the case where the caller *already has a GCP identity*. But your GitHub Actions runner, your GitLab pipeline, your AWS Lambda, your on-prem Kubernetes pod — none of those have a GCP identity to start from. The old answer was "give them a key file." The 2026 answer is **Workload Identity Federation (WIF)**: teach GCP to *trust an external identity provider's tokens* and trade one of those tokens for a short-lived GCP token.

The insight is that those external workloads already carry a verifiable identity token:

- GitHub Actions mints an **OIDC JWT** for each workflow run, signed by GitHub, with claims like `repository`, `ref`, and `environment`.
- GitLab CI mints an OIDC `id_token` with `project_path`, `ref`, and `ref_type`.
- A Kubernetes pod has a **projected service-account token** — an OIDC JWT signed by the cluster's OIDC issuer, with `sub` like `system:serviceaccount:ns:name`.
- An AWS workload has a signed `GetCallerIdentity` (the AWS provider type, not OIDC).

WIF says: *if a token from issuer X has claim Y, treat it as Google principal Z, and let Z impersonate this service account.* No key. The external platform proves who it is with a token it already has; GCP exchanges that for a 1-hour GCP token.

The objects you create:

- A **workload identity pool** — a container for external identities in a project. One per trust domain is typical (`github`, `gitlab`, `corp-k8s`).
- A **workload identity provider** inside the pool — trusts exactly one issuer. An *OIDC* provider for GitHub/GitLab/K8s; an *AWS* provider for AWS accounts.
- An **attribute mapping** — turns external token claims into Google attributes: `google.subject = assertion.sub`, `attribute.repository = assertion.repository`.
- An **attribute condition** (critical) — a CEL expression that the token must satisfy *before the mapping is accepted*. This is your security boundary; skip it and any GitHub repo on the planet can assume your SA.
- A **binding** on the target SA granting `roles/iam.workloadIdentityUser` to a `principalSet://` (a scoped set of external identities).

## 2.4 — The token exchange, step by step

When `google-github-actions/auth` runs in a workflow, this happens — and you should be able to draw it on a whiteboard:

1. **GitHub mints an OIDC token.** The workflow requests it (`permissions: id-token: write`). GitHub signs a JWT with `iss=https://token.actions.githubusercontent.com`, `aud` set to your configured audience, `sub=repo:acme/api:ref:refs/heads/main`, plus `repository`, `ref`, `actor`, etc.

2. **The action calls GCP STS.** It POSTs the GitHub JWT to `https://sts.googleapis.com/v1/token` as an [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693) token exchange, naming your workload identity provider's full resource name as the audience.

3. **STS validates the token.** It fetches GitHub's public keys from the issuer's JWKS endpoint, verifies the signature, checks `aud` and `exp`, then evaluates your **attribute condition**. If the condition fails — say the token's `repository` isn't on your allow-list — the exchange is rejected here. If it passes, STS applies the **attribute mapping** and returns a *federated access token* representing the `principal://...` / `principalSet://...` identity.

4. **The action exchanges the federated token for an SA token.** It calls `iamcredentials.googleapis.com`'s `generateAccessToken`, presenting the federated token and the target SA email. GCP checks that the federated principal holds `roles/iam.workloadIdentityUser` on that SA. If so, it returns a 1-hour OAuth2 access token *for the service account*.

5. **The workflow uses the SA token** for `gcloud`, Terraform, `bq`, whatever. It expires in an hour. There was never a key.

Two security checks live in this flow, and you must configure both:

- **The attribute condition** (step 3) decides *which external tokens are even allowed into the pool*. This is your first gate.
- **The `workloadIdentityUser` binding's `principalSet://`** (step 4) decides *which mapped identities may impersonate this specific SA*. This is your second gate.

Belt and suspenders. A common production mistake is configuring a permissive provider (no attribute condition) and relying solely on the binding — that works, but it means *any* GitHub repo's token can enter your pool, and a single overly-broad binding then leaks production. Configure the condition.

## 2.5 — WIF for GitHub Actions, in Terraform

Here is the full, correct, copy-this setup. It is the spine of the challenge and the mini-project's CI path.

```hcl
variable "project_id" { type = string }
variable "project_number" { type = string }
variable "github_repo" {
  type        = string
  description = "owner/name, e.g. acme/api"
}

# 1. The pool.
resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions"
  description               = "OIDC federation for GitHub Actions workflows."
}

# 2. The provider, trusting GitHub's issuer.
resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # The security gate: only tokens from THIS repo are accepted into the pool.
  attribute_condition = "assertion.repository == '${var.github_repo}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# 3. The deploy SA the workflow will act as.
resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "ci-deployer"
  display_name = "CI deploy service account (WIF-only, no keys)"
}

# 4. Let ONLY main-branch runs of THIS repo impersonate the deploy SA.
resource "google_service_account_iam_member" "wif_binding" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member = format(
    "principalSet://iam.googleapis.com/projects/%s/locations/global/workloadIdentityPools/%s/attribute.repository/%s",
    var.project_number,
    google_iam_workload_identity_pool.github.workload_identity_pool_id,
    var.github_repo,
  )
}

output "provider_resource_name" {
  value = google_iam_workload_identity_pool_provider.github.name
}
output "deployer_sa_email" {
  value = google_service_account.deployer.email
}
```

Note the layering. The `attribute_condition` says *only tokens from `acme/api` enter the pool*. The `principalSet://` on `attribute.repository/acme/api` says *only the `acme/api` identity may impersonate the deployer*. If you wanted to lock to `main` only, you'd map `attribute.ref` and bind a `principalSet://.../attribute.ref/refs/heads/main` instead — the syntax composes one attribute per `principalSet`. (For "main of this repo," map a composite attribute or add an attribute condition `assertion.ref == 'refs/heads/main'`.)

The workflow side carries no secret — only the two outputs above, which are not sensitive:

```yaml
name: deploy
on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write   # REQUIRED — lets the runner mint its OIDC token.

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          project_id: my-project
          workload_identity_provider: projects/123456789012/locations/global/workloadIdentityPools/github-pool/providers/github-provider
          service_account: ci-deployer@my-project.iam.gserviceaccount.com

      - uses: google-github-actions/setup-gcloud@v2

      - name: Prove it works, keylessly
        run: |
          gcloud auth list
          gcloud storage ls gs://my-deploy-artifacts
```

There is no `GCP_SA_KEY` secret. There is no JSON in the repo. The `workload_identity_provider` and `service_account` values are identifiers, not credentials — leaking them grants nothing, because the only thing that can use them is a token GitHub signs for *your* repo, validated by *your* attribute condition.

## 2.6 — Generalizing to a second provider

The challenge asks you to add a second provider after GitHub works. The pattern is identical; only the `issuer_uri`, the claim names, and the attribute condition change.

**GitLab CI** — GitLab issues OIDC `id_token`s; the issuer is your GitLab instance:

```hcl
resource "google_iam_workload_identity_pool_provider" "gitlab" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "gitlab-provider"
  attribute_mapping = {
    "google.subject"        = "assertion.sub"
    "attribute.project_path" = "assertion.project_path"
  }
  attribute_condition = "assertion.project_path == 'acme-group/api'"
  oidc {
    issuer_uri = "https://gitlab.com"
  }
}
```

On the GitLab side you declare an ID token and pass it to the same `auth` flow:

```yaml
deploy:
  id_tokens:
    GCP_ID_TOKEN:
      aud: https://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/github-pool/providers/gitlab-provider
  script:
    - echo "$GCP_ID_TOKEN" > token.jwt
    - gcloud iam workload-identity-pools create-cred-config ... # exchange and deploy
```

**A non-GCP Kubernetes cluster** — the pod's projected SA token is an OIDC JWT signed by the cluster's OIDC issuer. You publish the cluster's OIDC discovery document at a URL GCP can reach, point `issuer_uri` at it, and map `assertion.sub` (which is `system:serviceaccount:NS:NAME`). The attribute condition pins the namespace and SA. This is the hard half of the challenge and the most general form of WIF: *any* OIDC issuer GCP can fetch a JWKS from can be a provider.

## 2.7 — Auditing the keyless world

Once you've gone keyless, the audit shifts. You stop hunting for key files (the org policy bans them) and start auditing:

- **Who holds `roles/iam.workloadIdentityUser` on each SA, and is the `principalSet://` tight?** A `principalSet://` that maps to `attribute.repository/*` or a missing attribute condition is the new "key file in a repo."
- **Are providers scoped with an attribute condition?** A provider with no condition trusts every token from the issuer.
- **Are impersonation grants (`serviceAccountTokenCreator`) resource-scoped and short-chained?**

The query you'll run constantly:

```bash
gcloud asset search-all-iam-policies \
  --scope=projects/my-project \
  --query='policy:(roles/iam.workloadIdentityUser OR roles/iam.serviceAccountTokenCreator)' \
  --format='table(resource, policy.bindings.role, policy.bindings.members)'
```

Read each `member`. If it's a `principalSet://` ending in a wildcard or a bare attribute name with no value, that's your finding. Exercise 3 automates this with the Asset and Policy Analyzer APIs.

## 2.8 — Hands-on: impersonate, then federate (60 minutes)

Do this in your `workloads/dev` project.

**Part A — impersonation (20 min).**

1. Create a service account `reporter` and grant it `roles/storage.objectViewer` on a test bucket.
2. Grant *yourself* `roles/iam.serviceAccountTokenCreator` on `reporter` (the SA resource, not the project).
3. Run `gcloud storage ls gs://YOUR_BUCKET --impersonate-service-account=reporter@...`. Confirm it works.
4. Run the same `ls` *without* the flag, as yourself with no bucket access. Confirm the 403. You've now proven you can borrow an identity without holding a key.

**Part B — WIF for GitHub Actions (40 min).**

1. Apply the Terraform from §2.5 against a throwaway repo you control. Capture the two outputs.
2. Add the workflow from §2.5 to the repo. Push to `main`.
3. Watch the run. The `gcloud auth list` step should show the `ci-deployer` SA as the active account. The `storage ls` should succeed.
4. **Prove the gate works:** push the same workflow from a *fork* or a second repo. The auth step must fail — the attribute condition rejects the foreign `repository` claim. If a foreign repo can authenticate, your condition is wrong; fix it before moving on.
5. Confirm zero keys: run the key-finder loop from lecture 1 against the project. It prints nothing.

That's the keyless deploy path. The challenge hardens it (lock to `main`, add a second provider); the mini-project wires it into the landing zone as the only path CI uses. From here forward in C18, downloading an SA key is a failing grade. You don't need one — you just built the thing that replaces it.
