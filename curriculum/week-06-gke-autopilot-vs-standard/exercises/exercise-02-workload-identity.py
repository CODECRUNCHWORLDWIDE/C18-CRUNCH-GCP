"""
Exercise 2 — Workload Identity reads a GCS object with NO key file
==================================================================

Goal: Run a FastAPI endpoint inside a GKE pod that reads an object from a
      private GCS bucket using Application Default Credentials (ADC). The pod
      authenticates via Workload Identity Federation — its Kubernetes service
      account is bound to a Google service account, and the GKE metadata server
      mints a short-lived token on demand. NO service-account key file is ever
      created, mounted, or referenced. The application code below does not know
      or care that Workload Identity exists: it just calls the GCS client, and
      ADC finds the token.

Estimated time: 75 minutes.

THE PUNCHLINE you are proving:
    The same Python file works (a) locally against a key file you set in
    GOOGLE_APPLICATION_CREDENTIALS, and (b) in the pod with no key file at all.
    The application is identical. Only the *environment* differs. That is the
    whole value of ADC + Workload Identity: credentials become an environment
    concern, not a code concern.

--------------------------------------------------------------------------------
THE APPLICATION (this file). Save as app/main.py in the same image as Exercise 1
(the requirements.txt already includes google-cloud-storage).
--------------------------------------------------------------------------------
"""

import os

from fastapi import FastAPI, HTTPException
from google.api_core.exceptions import Forbidden, NotFound
from google.cloud import storage

app = FastAPI(title="crunch-fastapi-wi", version="1.0.0")

POD_NAME = os.getenv("POD_NAME", "unknown")
BUCKET = os.environ["GCS_BUCKET"]          # required: set via the Deployment env
OBJECT = os.getenv("GCS_OBJECT", "hello.txt")

# The client picks up credentials via Application Default Credentials (ADC).
# In the pod, ADC resolves to the GKE metadata server, which mints a token for
# the bound Google service account. No key file, no GOOGLE_APPLICATION_CREDENTIALS,
# nothing on disk. The client is constructed once at import time and reused.
_storage_client = storage.Client()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/whoami")
def whoami() -> dict[str, str]:
    """Report the active service-account email ADC resolved to.

    This is how you confirm Workload Identity worked: the email should be the
    GOOGLE service account you bound, NOT a default compute SA and NOT a user.
    """
    import google.auth

    credentials, project = google.auth.default()
    email = getattr(credentials, "service_account_email", "unknown")
    return {"pod": POD_NAME, "project": project or "unknown", "service_account": email}


@app.get("/read")
def read_object() -> dict[str, str]:
    """Read GCS_OBJECT from GCS_BUCKET and return its contents.

    On success, this proves the pod authenticated to GCS with no key file.
    On 403, the Workload Identity binding exists but the GSA lacks
    roles/storage.objectViewer on the bucket. On 404, the object is missing.
    """
    try:
        bucket = _storage_client.bucket(BUCKET)
        blob = bucket.blob(OBJECT)
        contents = blob.download_as_text()
    except Forbidden as exc:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Forbidden reading gs://{BUCKET}/{OBJECT}. Workload Identity "
                f"resolved an identity, but it lacks storage.objectViewer on the "
                f"bucket. Grant it and retry. Underlying: {exc}"
            ),
        ) from exc
    except NotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=f"gs://{BUCKET}/{OBJECT} not found: {exc}",
        ) from exc

    return {
        "pod": POD_NAME,
        "bucket": BUCKET,
        "object": OBJECT,
        "contents": contents,
    }


# ==============================================================================
# THE SETUP. Everything below is a runbook in comment form. Run it top to bottom.
# ==============================================================================
#
# Step 0 — Reuse the Autopilot cluster and image from Exercise 1, OR create a
#          fresh Autopilot cluster (Workload Identity is on by default there).
#          Rebuild the image so it contains THIS main.py:
#
#   PROJECT_ID=$(gcloud config get-value project)
#   REGION=us-central1
#   IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/crunch/fastapi:1.1.0"
#   docker build --platform=linux/amd64 -t "${IMAGE}" .
#   docker push "${IMAGE}"
#
# Step 1 — Create the private GCS bucket and an object to read.
#
#   BUCKET="${PROJECT_ID}-crunch-wi"
#   gcloud storage buckets create "gs://${BUCKET}" \
#       --location=us-central1 \
#       --uniform-bucket-level-access \
#       --public-access-prevention
#   echo "hello from workload identity, no key file in sight" \
#       | gcloud storage cp - "gs://${BUCKET}/hello.txt"
#
# Step 2 — Create the GOOGLE service account (GSA) the pod will act as, and
#          grant it ONLY objectViewer on this one bucket (least privilege).
#
#   gcloud iam service-accounts create crunch-gcs-reader \
#       --display-name="Crunch GCS reader (Workload Identity)"
#   GSA="crunch-gcs-reader@${PROJECT_ID}.iam.gserviceaccount.com"
#   gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
#       --member="serviceAccount:${GSA}" \
#       --role="roles/storage.objectViewer"
#
# Step 3 — Create the KUBERNETES service account (KSA) the pod will run as.
#
#   kubectl create serviceaccount gcs-reader
#
# Step 4 — Bind the KSA to the GSA. This is the Workload Identity binding: it
#          says "the KSA default/gcs-reader is allowed to impersonate the GSA."
#          The PROJECT_ID.svc.id.goog is the workload identity POOL (the same
#          value you passed as --workload-pool on a Standard cluster; on
#          Autopilot it is implicit).
#
#   gcloud iam service-accounts add-iam-policy-binding "${GSA}" \
#       --role="roles/iam.workloadIdentityUser" \
#       --member="serviceAccount:${PROJECT_ID}.svc.id.goog[default/gcs-reader]"
#
# Step 5 — Annotate the KSA so GKE knows which GSA to mint tokens for. This is
#          the other half of the binding, on the Kubernetes side.
#
#   kubectl annotate serviceaccount gcs-reader \
#       iam.gke.io/gcp-service-account="${GSA}"
#
# Step 6 — Deploy a pod that uses the KSA. Save as k8s/wi-deployment.yaml and
#          apply with PROJECT_ID and BUCKET substituted.
#
#   apiVersion: apps/v1
#   kind: Deployment
#   metadata:
#     name: fastapi-wi
#     labels: { app: fastapi-wi }
#   spec:
#     replicas: 1
#     selector:
#       matchLabels: { app: fastapi-wi }
#     template:
#       metadata:
#         labels: { app: fastapi-wi }
#       spec:
#         serviceAccountName: gcs-reader        # <-- the KSA, this is the key line
#         containers:
#           - name: fastapi
#             image: us-central1-docker.pkg.dev/PROJECT_ID/crunch/fastapi:1.1.0
#             ports: [{ containerPort: 8080 }]
#             env:
#               - name: POD_NAME
#                 valueFrom: { fieldRef: { fieldPath: metadata.name } }
#               - name: GCS_BUCKET
#                 value: "PROJECT_ID-crunch-wi"
#               - name: GCS_OBJECT
#                 value: "hello.txt"
#             resources:
#               requests: { cpu: "250m", memory: "512Mi" }
#               limits:   { cpu: "500m", memory: "512Mi" }
#             readinessProbe:
#               httpGet: { path: /healthz, port: 8080 }
#               initialDelaySeconds: 3
#               periodSeconds: 5
#
#   Apply:
#     sed "s/PROJECT_ID/${PROJECT_ID}/g" k8s/wi-deployment.yaml | kubectl apply -f -
#     kubectl rollout status deployment/fastapi-wi --timeout=180s
#
# Step 7 — Verify. Port-forward and hit the endpoints.
#
#   kubectl port-forward deploy/fastapi-wi 8080:8080 &
#   sleep 2
#   curl -s localhost:8080/whoami | python3 -m json.tool
#   # EXPECTED: "service_account": "crunch-gcs-reader@PROJECT_ID.iam.gserviceaccount.com"
#   #           NOT a default compute SA, NOT a user account.
#
#   curl -s localhost:8080/read | python3 -m json.tool
#   # EXPECTED:
#   # {
#   #     "pod": "fastapi-wi-...",
#   #     "bucket": "PROJECT_ID-crunch-wi",
#   #     "object": "hello.txt",
#   #     "contents": "hello from workload identity, no key file in sight\n"
#   # }
#
# Step 8 — PROVE there is no key file. Exec into the pod and look.
#
#   POD=$(kubectl get pod -l app=fastapi-wi -o jsonpath='{.items[0].metadata.name}')
#   kubectl exec "${POD}" -- printenv GOOGLE_APPLICATION_CREDENTIALS
#   # EXPECTED: empty / unset. ADC did NOT use a key file env var.
#   kubectl exec "${POD}" -- find / -name '*.json' -path '*key*' 2>/dev/null
#   # EXPECTED: nothing. No key file anywhere on disk.
#   kubectl exec "${POD}" -- curl -s -H "Metadata-Flavor: Google" \
#       "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/email"
#   # EXPECTED: crunch-gcs-reader@PROJECT_ID.iam.gserviceaccount.com
#   # That is the GKE metadata server reporting the identity it will mint tokens for.
#
# ==============================================================================
# ACCEPTANCE CRITERIA
# ==============================================================================
#
#   [ ] The GSA has roles/storage.objectViewer on the bucket and NOTHING else.
#   [ ] The KSA default/gcs-reader is bound to the GSA via
#       roles/iam.workloadIdentityUser AND annotated with the GSA email.
#   [ ] The Deployment sets serviceAccountName: gcs-reader.
#   [ ] /whoami returns the crunch-gcs-reader GSA email (not a default SA).
#   [ ] /read returns the object contents with HTTP 200.
#   [ ] kubectl exec confirms GOOGLE_APPLICATION_CREDENTIALS is unset and no
#       key JSON exists on disk.
#   [ ] You can explain the token-minting path: client -> ADC -> metadata server
#       -> mints short-lived token for the bound GSA -> GCS accepts it.
#
# ==============================================================================
# NEGATIVE TEST (do this — it is the most instructive part)
# ==============================================================================
#
#   Remove the objectViewer grant and watch /read return 403:
#     gcloud storage buckets remove-iam-policy-binding "gs://${BUCKET}" \
#         --member="serviceAccount:${GSA}" --role="roles/storage.objectViewer"
#     curl -s localhost:8080/read | python3 -m json.tool
#     # EXPECTED: HTTP 403 with the "Forbidden" detail from the handler above.
#     # This proves the identity resolved correctly (it is NOT an auth failure)
#     # but lacks authorization. Authentication and authorization are separate;
#     # Workload Identity handled the FIRST, IAM the SECOND.
#   Re-add the grant before moving on.
#
# ==============================================================================
# THE NEWER BINDING (read this; you do not have to do it)
# ==============================================================================
#
#   Everything above uses the classic KSA->GSA binding (a GSA exists, the KSA
#   impersonates it). GKE also supports a GSA-LESS binding where you grant IAM
#   roles DIRECTLY to the KSA principal, no Google service account at all:
#
#     gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
#       --member="principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/subject/ns/default/sa/gcs-reader" \
#       --role="roles/storage.objectViewer"
#
#   With that grant you do NOT create a GSA, do NOT add a workloadIdentityUser
#   binding, and do NOT annotate the KSA. The KSA itself is the IAM principal.
#   Fewer moving parts, one fewer identity to audit. Prefer it for new work in
#   2026; the classic form remains common in existing repos, which is why this
#   exercise teaches it first.
#
# ==============================================================================
# TEARDOWN (do not skip)
# ==============================================================================
#
#   kubectl delete deployment fastapi-wi
#   kubectl delete serviceaccount gcs-reader
#   gcloud iam service-accounts delete "${GSA}" --quiet
#   gcloud storage rm --recursive "gs://${BUCKET}"
#   gcloud container clusters delete crunch-autopilot --region=us-central1 --quiet
#
# ==============================================================================
# RUN IT LOCALLY FIRST (optional sanity check)
# ==============================================================================
#
#   You can run this exact file on your laptop to test the logic before deploying.
#   Locally, ADC resolves to your gcloud user creds or a key file:
#     gcloud auth application-default login
#     export GCS_BUCKET="${PROJECT_ID}-crunch-wi"
#     uvicorn main:app --host 0.0.0.0 --port 8080
#     curl localhost:8080/read
#   The SAME code that worked locally works in the pod with no key file. That
#   portability is the entire point.
"""
End of exercise. The application code (top of file) is complete and runnable.
Everything after the first triple-quoted block is the runbook in comment form.
"""
