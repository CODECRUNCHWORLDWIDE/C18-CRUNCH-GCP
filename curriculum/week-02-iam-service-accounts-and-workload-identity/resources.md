# Week 2 — Resources

Every link on this page is **free**. Google Cloud documentation is free without an account. The Terraform provider docs are open. RFCs are open. No paywalled books are linked. If a link 404s, open an issue so we can replace it.

## Required reading (work it into your week)

- **IAM overview** — the canonical mental model: principals, roles, policies:
  <https://cloud.google.com/iam/docs/overview>
- **Understanding roles** — basic vs predefined vs custom, with the full predefined catalogue:
  <https://cloud.google.com/iam/docs/understanding-roles>
- **Service accounts overview** — what they are, what they are not, and why you stop downloading keys:
  <https://cloud.google.com/iam/docs/service-account-overview>
- **Workload Identity Federation** — the keyless-credentials feature that is the spine of this week:
  <https://cloud.google.com/iam/docs/workload-identity-federation>
- **Best practices for using and managing service accounts** — read this twice:
  <https://cloud.google.com/iam/docs/best-practices-service-accounts>

## The principal & policy model (read once, reference forever)

- **IAM policy reference (the policy object)** — `bindings`, `members`, `etag`, the read-modify-write loop:
  <https://cloud.google.com/iam/docs/reference/rest/v1/Policy>
- **Policy inheritance & the resource hierarchy** — how org → folder → project → resource bindings union:
  <https://cloud.google.com/iam/docs/resource-hierarchy-access-control>
- **Members / principal identifiers** — the exact `user:`, `group:`, `serviceAccount:`, `principalSet:` syntax:
  <https://cloud.google.com/iam/docs/principal-identifiers>
- **Permissions reference** — the searchable catalogue of every `service.resource.verb` permission and which role grants it:
  <https://cloud.google.com/iam/docs/permissions-reference>

## Custom roles & conditions

- **Creating and managing custom roles**:
  <https://cloud.google.com/iam/docs/creating-custom-roles>
- **Choosing predefined roles to base a custom role on** (the `gcloud iam roles describe` workflow):
  <https://cloud.google.com/iam/docs/understanding-custom-roles>
- **IAM Conditions overview** — what conditions can and cannot scope:
  <https://cloud.google.com/iam/docs/conditions-overview>
- **Conditions attribute reference** — the CEL variables (`resource.name`, `request.time`, etc.):
  <https://cloud.google.com/iam/docs/conditions-attribute-reference>
- **Common Expression Language (CEL) spec** — the language conditions are written in:
  <https://github.com/google/cel-spec>

## Impersonation

- **Create short-lived credentials (impersonation)** — `gcloud` and API flows for tokens that expire:
  <https://cloud.google.com/iam/docs/create-short-lived-credentials-direct>
- **`--impersonate-service-account` flag** — the daily-driver way to stop using keys locally:
  <https://cloud.google.com/sdk/gcloud/reference/config/set> (see the `auth/impersonate_service_account` property)
- **Roles for impersonation** — `serviceAccountTokenCreator` vs `serviceAccountUser`, finally explained:
  <https://cloud.google.com/iam/docs/service-account-permissions>

## Workload Identity Federation — the keyless guides

- **Configure WIF with deployment pipelines (GitHub Actions, GitLab, etc.)**:
  <https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines>
- **Configure WIF for other identity providers (OIDC / SAML)**:
  <https://cloud.google.com/iam/docs/workload-identity-federation-with-other-providers>
- **Configure WIF for Kubernetes** (non-GKE / self-managed clusters as an OIDC issuer):
  <https://cloud.google.com/iam/docs/workload-identity-federation-with-kubernetes>
- **`google-github-actions/auth`** — the GitHub Action that does the token exchange; read the README and the source:
  <https://github.com/google-github-actions/auth>
- **GitLab CI ID tokens** — GitLab's native OIDC `id_tokens` block, the GitLab side of the federation:
  <https://docs.gitlab.com/ee/ci/secrets/id_token_authentication.html>

## Auditing & the toolchain

- **Cloud Audit Logs overview** — Admin Activity (always on) vs Data Access (off by default):
  <https://cloud.google.com/logging/docs/audit>
- **Configure Data Access audit logs** — the IAM policy that turns them on:
  <https://cloud.google.com/logging/docs/audit/configure-data-access>
- **Analyze IAM policies (Policy Analyzer)** — "who can do what on which resource":
  <https://cloud.google.com/policy-intelligence/docs/analyze-iam-policies>
- **Cloud Asset Inventory `analyze-iam-policy`** — the CLI you live in this week:
  <https://cloud.google.com/asset-inventory/docs/analyzing-iam-policy>
- **IAM Recommender** — surfaces unused permissions and over-grants automatically:
  <https://cloud.google.com/iam/docs/recommender-overview>

## Org policy guardrails (stretch, but cite them)

- **Restricting service account usage** — `disableServiceAccountKeyCreation` and friends:
  <https://cloud.google.com/resource-manager/docs/organization-policy/restricting-service-accounts>
- **IAM deny policies** — block a permission regardless of any allow grant:
  <https://cloud.google.com/iam/docs/deny-overview>

## Terraform / OpenTofu provider docs

- **`google_project_iam` family** (`_binding`, `_member`, `_policy` — and why mixing them corrupts state):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_iam>
- **`google_organization_iam_custom_role`** and **`google_project_iam_custom_role`**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_iam_custom_role>
- **`google_iam_workload_identity_pool`** and **`google_iam_workload_identity_pool_provider`**:
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_iam_workload_identity_pool>
- **`google_service_account_iam_member`** (this is where you bind WIF principals to an SA):
  <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_service_account_iam>

## Background: OAuth / OIDC / JWT (read if these are fuzzy)

- **OpenID Connect Core 1.0** — the spec WIF leans on; skim §2 (ID token) and §3 (auth flows):
  <https://openid.net/specs/openid-connect-core-1_0.html>
- **RFC 7519 — JSON Web Token (JWT)** — claims, `iss`, `sub`, `aud`, `exp`:
  <https://datatracker.ietf.org/doc/html/rfc7519>
- **RFC 8693 — OAuth 2.0 Token Exchange** — the STS flow WIF uses to swap an OIDC token for a GCP token:
  <https://datatracker.ietf.org/doc/html/rfc8693>
- **A short, free OIDC primer** (auth0's, vendor-agnostic enough):
  <https://openid.net/developers/how-connect-works/>

## Talks & long-form (free, no signup)

- **"Securing your Google Cloud foundation"** — Google Cloud Next session catalogue; search the current year's IAM hardening talk:
  <https://cloud.withgoogle.com/next>
- **"Workload Identity Federation deep dive"** — search the Google Cloud Tech YouTube channel; the keyless-CI talk is reposted yearly:
  <https://www.youtube.com/@googlecloudtech>
- **The CISA / cloud lateral-movement writeups** — read one real breach where a leaked SA key was the pivot. The 2019/2020-era GCP key-leak postmortems are the canonical lesson. (Search "service account key leak post-mortem" and read a primary source, not a vendor blog.)

## Tools you'll use this week

- **`gcloud`** — installed with the Cloud SDK. Verify with `gcloud --version`; update with `gcloud components update`.
- **`gcloud asset`** — part of the SDK; the Asset Inventory CLI. Enable the API with `gcloud services enable cloudasset.googleapis.com`.
- **`terraform`** (or **`tofu`**) — the `google` and `google-beta` providers, >= 6.x.
- **Python 3.11+** with `google-cloud-asset` and `google-cloud-iam` for the exercise-03 auditor.
- **`jq`** — for slicing JSON policy output on the command line.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Principal (member)** | An identity a policy can name: `user:`, `group:`, `serviceAccount:`, or `principalSet:` (federated). |
| **Role** | A named bundle of permissions. Basic, predefined, or custom. |
| **Permission** | A single `service.resource.verb` capability, e.g. `storage.objects.get`. |
| **Binding** | One row of a policy: a role granted to a set of principals, optionally with a condition. |
| **Policy** | The full set of bindings attached to one resource. Has an `etag` for optimistic concurrency. |
| **Effective policy** | The union of all bindings from a resource up to the org root. What actually applies. |
| **Basic role** | `roles/owner`, `roles/editor`, `roles/viewer`. Legacy, project-wide, far too broad. |
| **Predefined role** | A Google-maintained, service-scoped role, e.g. `roles/run.developer`. |
| **Custom role** | A role you define from a hand-picked permission list. Org- or project-scoped. |
| **IAM Condition** | A CEL expression on a binding that narrows *when* / *on what* it applies. |
| **Impersonation** | Borrowing an SA's identity to mint a short-lived token, instead of holding its key. |
| **`serviceAccountUser`** | Lets a principal *attach* an SA to a resource (deploy as that SA). Not impersonation. |
| **`serviceAccountTokenCreator`** | Lets a principal *mint tokens* for an SA. This is impersonation. |
| **WIF** | Workload Identity Federation — trust an external IdP's OIDC tokens, no keys. |
| **Workload identity pool** | The container that holds federated identities and the providers that mint them. |
| **Attribute mapping** | How an external token's claims (`sub`, `repository`) become GCP `attribute.*` values. |
| **STS** | Google's Security Token Service — swaps an external OIDC token for a federated access token. |
| **Break-glass** | A separate, audited, alerting, time-boxed path to elevated access for emergencies. |

---

*If a link 404s, please open an issue so we can replace it.*
