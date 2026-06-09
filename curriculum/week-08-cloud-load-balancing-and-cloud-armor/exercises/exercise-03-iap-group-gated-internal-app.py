"""
Exercise 3 — An internal app behind Identity-Aware Proxy, gated on a Google group,
             that VERIFIES the IAP-signed JWT.

Goal: put IAP in front of a FastAPI app on a global external LB, grant access only
      to members of a Google group, and prove the app TRUSTS NOTHING it has not
      verified: it validates the `X-Goog-IAP-JWT-Assertion` signature + audience on
      every request, so a request that reaches the backend directly (bypassing the
      LB/IAP) is rejected. This is the non-negotiable step from Lecture 1 §1.6.

Estimated time: ~75 minutes (the LB + IAP wiring is the bulk; the app is small).

WHY VERIFY THE JWT:
  IAP enforces access at the LB, but if an attacker can reach your backend's URL
  directly (a misconfigured firewall, a leaked Cloud Run URL, an internal IP), they
  arrive with NO IAP check at all. The signed header is the only thing that proves a
  request actually came through IAP. An IAP deployment that does not verify the JWT
  is security theater. So this app does two things on every request:
    1. Requires `X-Goog-IAP-JWT-Assertion` to be present.
    2. Verifies its signature against Google's IAP public keys AND checks the
       audience equals THIS backend's expected audience string. Only then does it
       trust the `email` claim and enforce group membership downstream (IAP already
       enforced the group via IAM; we re-read the verified identity for logging/audit).

DEPENDENCIES (pin in your image):
    fastapi==0.115.*
    uvicorn[standard]==0.32.*
    google-auth==2.*        # provides google.auth.transport.requests + google.oauth2.id_token

RUN LOCALLY (it will reject everything, since there's no real IAP JWT — that's correct):
    IAP_AUDIENCE="/projects/123/global/backendServices/456" \
        uvicorn exercise_03_iap_group_gated_internal_app:app --host 0.0.0.0 --port 8080

The infra (LB + IAP + group grant) is in the RUNBOOK at the bottom of this file.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

app = FastAPI(title="crunch-internal-admin")

# The audience an IAP JWT must carry to be accepted by THIS backend. For a
# load-balanced backend it has the exact form:
#   /projects/PROJECT_NUMBER/global/backendServices/BACKEND_SERVICE_ID
# You read PROJECT_NUMBER from `gcloud projects describe` and BACKEND_SERVICE_ID
# from `gcloud compute backend-services describe ... --format='value(id)'`.
# It is injected as an env var so the same image works across environments.
IAP_AUDIENCE = os.environ["IAP_AUDIENCE"]

# One shared request object for the Google public-key fetch (it caches the certs).
_GOOGLE_REQUEST = google_requests.Request()

IAP_JWT_HEADER = "x-goog-iap-jwt-assertion"


def _verify_iap_jwt(iap_jwt: str) -> dict:
    """Verify the IAP-signed JWT and return its claims, or raise HTTPException(401).

    google.oauth2.id_token.verify_token with the IAP issuer checks:
      - the signature against Google's IAP signing keys,
      - the audience equals IAP_AUDIENCE,
      - the token is not expired,
      - the issuer is https://cloud.google.com/iap.
    Any failure raises ValueError, which we map to 401.
    """
    try:
        claims = id_token.verify_token(
            iap_jwt,
            _GOOGLE_REQUEST,
            audience=IAP_AUDIENCE,
            certs_url="https://www.gstatic.com/iap/verify/public_key",
        )
    except ValueError as exc:
        # Bad signature, wrong audience, expired, or wrong issuer.
        raise HTTPException(status_code=401, detail=f"Invalid IAP assertion: {exc}")

    if claims.get("iss") != "https://cloud.google.com/iap":
        raise HTTPException(status_code=401, detail="Wrong IAP issuer.")
    if not claims.get("email"):
        raise HTTPException(status_code=401, detail="IAP assertion has no email claim.")
    return claims


@app.middleware("http")
async def require_verified_iap(request: Request, call_next):
    """Reject any request without a verified IAP assertion.

    The /healthz path is exempt so the LB health check (which does NOT carry an
    IAP JWT) can pass. Everything else must come through IAP.
    """
    if request.url.path == "/healthz":
        return await call_next(request)

    iap_jwt = request.headers.get(IAP_JWT_HEADER)
    if not iap_jwt:
        # No IAP header => this request did not come through IAP. Refuse it.
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing IAP assertion; direct access is not allowed."},
        )

    claims = _verify_iap_jwt(iap_jwt)
    # Stash the verified identity for the handlers to read.
    request.state.iap_email = claims["email"]
    request.state.iap_sub = claims.get("sub", "")
    return await call_next(request)


@app.get("/healthz")
def healthz():
    """LB health check target. Exempt from the IAP requirement above."""
    return {"ok": True}


@app.get("/")
def whoami(request: Request):
    """The protected page. By the time we get here, the IAP JWT is verified and
    IAP has already enforced group membership via the IAM policy on the backend.
    We echo the *verified* identity so you can SEE that the chain worked end to end.
    """
    return {
        "message": "You are inside the internal admin app.",
        "verified_email": request.state.iap_email,
        "verified_subject": request.state.iap_sub,
        "note": "This email came from a cryptographically verified IAP JWT, "
        "not from a forgeable header.",
    }


@app.get("/admin/secret")
def secret(request: Request):
    """A second protected route, to show every route is covered by the middleware.

    IAP already gated this on the group; if you want a SECOND, finer-grained check
    (e.g. only a sub-group may see /admin/secret), do it here against the verified
    email — defense in depth, since IAP's group check is coarse per-backend.
    """
    email = request.state.iap_email
    return {"secret": "rotate the prod DB password Friday", "shown_to": email}


# Optional manual smoke check: confirm that an unsigned/garbage assertion is
# rejected (run this file directly; it does NOT need IAP to test the negative path).
if __name__ == "__main__":
    import sys

    print("Self-test: a garbage JWT must be rejected.", file=sys.stderr)
    try:
        _verify_iap_jwt("not.a.jwt")
    except HTTPException as exc:
        assert exc.status_code == 401, exc
        print(f"  OK — rejected with {exc.status_code}: {exc.detail}", file=sys.stderr)
    else:  # pragma: no cover - only hit if verification is broken
        raise SystemExit("FAIL — a garbage JWT was accepted; verification is broken.")
    print("Self-test passed. Now wire the infra (see the RUNBOOK).", file=sys.stderr)


###############################################################################
# RUNBOOK — put IAP in front of this app and gate it on a Google group.
#
# 0) PREREQS
#    - This app deployed somewhere a global external Application LB can reach:
#      the simplest is Cloud Run (serverless NEG, like Exercise 1) OR a GKE
#      Service via a zonal NEG. IAP works on the load-balanced backend service
#      either way. We assume you reuse the Exercise 1 LB skeleton and point its
#      backend at THIS app's Cloud Run service instead of `edge-origin`.
#    - A Google group you control, e.g. eng-admins@your-domain.com, with at
#      least your account in it and a second account NOT in it (to test 403).
#    - The IAP API enabled:
#        gcloud services enable iap.googleapis.com
#
# 1) DEPLOY THIS APP TO CLOUD RUN
#    Build an image with the deps above and main set to this file, then:
#      gcloud run deploy internal-admin \
#        --image REGION-docker.pkg.dev/PROJECT/REPO/internal-admin:latest \
#        --region us-central1 --no-allow-unauthenticated \
#        --set-env-vars IAP_AUDIENCE=pending          # real value set in step 4
#    (Note --no-allow-unauthenticated: only the LB's service agent should invoke it.)
#
# 2) BUILD THE LB (reuse Exercise 1's lb.tf, pointing the serverless NEG at
#    `internal-admin`). Note the backend service NAME and ID:
#      gcloud compute backend-services describe edge-run-backend --global \
#        --format='value(id)'
#      gcloud projects describe PROJECT --format='value(projectNumber)'
#
# 3) CONFIGURE THE OAUTH CONSENT SCREEN (one-time per project), then enable IAP
#    on the backend service. With Terraform (google + google-beta):
#
#      # An OAuth brand + client for IAP (internal user type is simplest):
#      resource "google_iap_brand" "brand" {
#        support_email     = "you@your-domain.com"
#        application_title = "Crunch Internal Admin"
#        project           = var.project_id
#      }
#      resource "google_iap_client" "client" {
#        display_name = "crunch-internal-admin"
#        brand        = google_iap_brand.brand.name
#      }
#
#      # Turn IAP ON for the backend service:
#      resource "google_compute_backend_service" "internal" {
#        name                  = "edge-run-backend"
#        protocol              = "HTTPS"
#        load_balancing_scheme = "EXTERNAL_MANAGED"
#        backend { group = google_compute_region_network_endpoint_group.run_neg.id }
#        iap {
#          enabled              = true
#          oauth2_client_id     = google_iap_client.client.client_id
#          oauth2_client_secret = google_iap_client.client.secret
#        }
#      }
#
# 4) SET THE AUDIENCE on the Cloud Run service so the app can verify the JWT:
#      AUD="/projects/PROJECT_NUMBER/global/backendServices/BACKEND_SERVICE_ID"
#      gcloud run services update internal-admin --region us-central1 \
#        --set-env-vars IAP_AUDIENCE="$AUD"
#
# 5) GRANT THE GROUP ACCESS (the actual gate). Only members of this group may
#    pass IAP:
#      gcloud iap web add-iam-policy-binding \
#        --resource-type=backend-services \
#        --service=edge-run-backend \
#        --member="group:eng-admins@your-domain.com" \
#        --role="roles/iap.httpsResourceAccessor"
#    (Terraform equivalent: google_iap_web_backend_service_iam_member with
#     role = "roles/iap.httpsResourceAccessor", member = "group:...".)
#
# 6) PROVE IT (proof of done)
#    a) In a browser, open https://<your LB host>/ while logged OUT of Google:
#       => you are REDIRECTED to a Google login. (IAP forced auth.)
#    b) Log in as a GROUP MEMBER:
#       => you see {"verified_email": "you@...", ...}. The email came from the
#          verified JWT, not a header. IAP + verification both worked.
#    c) Log in as a NON-member:
#       => IAP returns 403 "You don't have access." (the IAM gate bit.)
#    d) The bypass test — hit the Cloud Run URL DIRECTLY (not through the LB):
#         curl -i "$(gcloud run services describe internal-admin \
#                    --region us-central1 --format='value(status.url)')/"
#       => 401 "Missing IAP assertion; direct access is not allowed."
#          (Because --no-allow-unauthenticated blocks anonymous invokes, AND even
#           if it didn't, the app refuses requests with no verified IAP JWT.)
#
# PROOF OF DONE:
#   - logged-out => login redirect; member => verified email shown;
#     non-member => 403; direct backend hit => 401 (no IAP JWT).
#
# TEARDOWN (the gate):
#   gcloud iap web remove-iam-policy-binding --resource-type=backend-services \
#     --service=edge-run-backend --member="group:eng-admins@your-domain.com" \
#     --role="roles/iap.httpsResourceAccessor"
#   terraform destroy   # removes the LB + IAP config
#   gcloud run services delete internal-admin --region us-central1 --quiet
###############################################################################
