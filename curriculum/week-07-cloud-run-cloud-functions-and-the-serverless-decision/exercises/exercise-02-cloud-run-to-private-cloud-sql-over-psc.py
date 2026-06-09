"""
Exercise 2 — Cloud Run to a PRIVATE Cloud SQL Postgres over Private Service Connect
===================================================================================

Goal: Run a FastAPI service on Cloud Run that connects to a Cloud SQL Postgres
      instance that has NO public IP. All traffic goes over Private Service
      Connect (PSC) from inside the Week 03 VPC, reached via Direct VPC egress.
      The service authenticates with IAM DATABASE AUTHENTICATION -- there is no
      static database password anywhere. The Cloud SQL Python connector mints a
      short-lived token for the service account and uses it as the Postgres
      password over a mutual-TLS channel to the PSC endpoint.

Estimated time: 120 minutes.

THE PUNCHLINE you are proving:
    The database is unreachable from the public internet (no public IP, PSC
    only), the application holds NO password (IAM auth), and the SAME code path
    works locally (via the connector's local proxy) and on Cloud Run. Security
    becomes a property of the network + IAM, not a secret in your config.

WHY PSC and not the alternatives:
    - Public IP + Auth Proxy:  the DB has a routable public address. A finding
      in any serious review. We do NOT do this.
    - Private Services Access (legacy VPC peering): works, but peers Google's
      service-producer VPC into yours, consumes an allocated range, and is the
      older model. PSC is the 2026-correct private path: a forwarding rule in
      YOUR VPC points at the instance's service attachment. No peering, no
      shared range, explicit endpoint you control.
    - PSC + IAM auth (this exercise): no public IP, no password, explicit
      private endpoint. This is the pattern the mini-project and capstone reuse.

--------------------------------------------------------------------------------
THE APPLICATION (this file). Save as app/main.py.
--------------------------------------------------------------------------------
"""

import os

import sqlalchemy
from fastapi import FastAPI, HTTPException
from google.cloud.sql.connector import Connector, IPTypes

app = FastAPI(title="crunch-psc", version="1.0.0")

# Required environment, set on the Cloud Run service:
#   INSTANCE_CONNECTION_NAME = "<project>:<region>:<instance>"
#   DB_NAME                  = "crunch"
#   DB_IAM_USER              = "<service-account-without-.gserviceaccount.com>"
#                               (Cloud SQL truncates the SA email for IAM users)
INSTANCE_CONNECTION_NAME = os.environ["INSTANCE_CONNECTION_NAME"]
DB_NAME = os.environ.get("DB_NAME", "crunch")
DB_IAM_USER = os.environ["DB_IAM_USER"]

# The connector resolves the instance, fetches its PSC endpoint, and opens a
# mutual-TLS connection over the private path. ip_type=PSC tells it to use the
# Private Service Connect address, not a public or private-services-access IP.
# enable_iam_auth=True makes it mint an OAuth2 token for the ambient service
# account and present it as the Postgres password -- so there is no password.
_connector = Connector(ip_type=IPTypes.PSC, enable_iam_auth=True)


def _getconn() -> sqlalchemy.engine.base.Connection:
    return _connector.connect(
        INSTANCE_CONNECTION_NAME,
        "pg8000",
        user=DB_IAM_USER,
        db=DB_NAME,
        # NOTE: no `password=` argument. IAM auth supplies the token.
    )


# One engine, created at import time, with a bounded pool. The pool size is a
# REAL knob: every warm Cloud Run instance holds `pool_size` connections open
# against Cloud SQL. With max-instances=N and pool_size=P you can hold up to
# N*P connections -- size it against the instance's connection limit. For this
# exercise pool_size=2, max_overflow=1 keeps us far under any limit.
_engine = sqlalchemy.create_engine(
    "postgresql+pg8000://",
    creator=_getconn,
    pool_size=2,
    max_overflow=1,
    pool_timeout=30,
    pool_recycle=1800,
)


@app.on_event("startup")
def init_schema() -> None:
    """Create the table on startup. Idempotent. Real systems use migrations
    (Alembic); we inline it here so the exercise is self-contained."""
    with _engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id          BIGSERIAL PRIMARY KEY,
                    payload     TEXT NOT NULL,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/whoami")
def whoami() -> dict[str, str]:
    """Report the Postgres identity the connection authenticated as. With IAM
    auth this is the service account (truncated), proving no password was used."""
    with _engine.connect() as conn:
        row = conn.execute(sqlalchemy.text("SELECT current_user, version()")).one()
    return {"db_user": row[0], "server": row[1].split(",")[0]}


@app.post("/events")
def create_event(payload: str) -> dict[str, int]:
    """Insert one event. This is the I/O-bound write path the mini-project
    builds on: validate, persist, return. Most of the latency is the round trip
    to Postgres, which is why concurrency 80 (the default) is correct here."""
    try:
        with _engine.begin() as conn:
            new_id = conn.execute(
                sqlalchemy.text(
                    "INSERT INTO events (payload) VALUES (:p) RETURNING id"
                ),
                {"p": payload},
            ).scalar_one()
    except Exception as exc:  # noqa: BLE001 - surface the DB error to the caller
        raise HTTPException(status_code=500, detail=f"db write failed: {exc}") from exc
    return {"id": int(new_id)}


@app.get("/events/count")
def count_events() -> dict[str, int]:
    with _engine.connect() as conn:
        n = conn.execute(sqlalchemy.text("SELECT count(*) FROM events")).scalar_one()
    return {"count": int(n)}


# ==============================================================================
# THE SETUP. Everything below is a runbook in comment form. Run it top to bottom.
# Substitute PROJECT_ID / REGION / your VPC + subnet names from Week 03.
# ==============================================================================
#
# app/requirements.txt:
#   fastapi==0.115.6
#   uvicorn[standard]==0.34.0
#   sqlalchemy==2.0.36
#   pg8000==1.31.2
#   cloud-sql-python-connector==1.15.0
#
# Dockerfile (multi-stage, slim):
#   FROM python:3.12-slim AS build
#   WORKDIR /app
#   COPY app/requirements.txt .
#   RUN pip install --no-cache-dir --target=/install -r requirements.txt
#   FROM python:3.12-slim
#   WORKDIR /app
#   COPY --from=build /install /usr/local/lib/python3.12/site-packages
#   COPY app/ /app/
#   ENV PORT=8080
#   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
#
# --------------------------------------------------------------------------------
# Step 0 — Variables. Reuse the Week 03 VPC + a subnet in REGION.
# --------------------------------------------------------------------------------
#   PROJECT_ID=$(gcloud config get-value project)
#   REGION=us-central1
#   VPC=crunch-vpc                 # from Week 03
#   SUBNET=crunch-usc1             # a /24+ subnet in REGION (Week 03)
#   INSTANCE=crunch-pg
#   REPO=crunch
#   IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/psc:1.0.0"
#   SA="crunch-ingest"
#   SA_EMAIL="${SA}@${PROJECT_ID}.iam.gserviceaccount.com"
#
# --------------------------------------------------------------------------------
# Step 1 — Create a Cloud SQL Postgres instance with NO public IP and PSC enabled.
#          --no-assign-ip removes the public IP. --enable-private-service-connect
#          turns on the PSC service attachment. --psc-allowed-projects lists which
#          projects may create PSC endpoints to it (just ours).
# --------------------------------------------------------------------------------
#   gcloud sql instances create "${INSTANCE}" \
#       --database-version=POSTGRES_15 \
#       --tier=db-perf-optimized-N-2 \
#       --region="${REGION}" \
#       --no-assign-ip \
#       --enable-private-service-connect \
#       --psc-allowed-projects="${PROJECT_ID}" \
#       --database-flags=cloudsql.iam_authentication=on \
#       --edition=ENTERPRISE
#   # cloudsql.iam_authentication=on is what enables IAM database auth.
#   # If db-perf-optimized-N-2 is unavailable on your account, use --tier=db-g1-small
#   # with --edition=ENTERPRISE (smaller, cheaper; fine for the exercise).
#
#   gcloud sql databases create crunch --instance="${INSTANCE}"
#
# --------------------------------------------------------------------------------
# Step 2 — Find the instance's PSC service attachment and create a PSC ENDPOINT
#          (a forwarding rule) in YOUR VPC that points at it. This is the private
#          door. Nothing public is ever created.
# --------------------------------------------------------------------------------
#   ATTACHMENT=$(gcloud sql instances describe "${INSTANCE}" \
#       --format='value(pscServiceAttachmentLink)')
#   echo "service attachment: ${ATTACHMENT}"
#
#   # Reserve an internal IP in your subnet for the endpoint:
#   gcloud compute addresses create "${INSTANCE}-psc-ip" \
#       --region="${REGION}" --subnet="${SUBNET}"
#   PSC_IP=$(gcloud compute addresses describe "${INSTANCE}-psc-ip" \
#       --region="${REGION}" --format='value(address)')
#
#   # Create the forwarding rule (the PSC endpoint) targeting the attachment:
#   gcloud compute forwarding-rules create "${INSTANCE}-psc-ep" \
#       --region="${REGION}" \
#       --network="${VPC}" \
#       --address="${PSC_IP}" \
#       --target-service-attachment="${ATTACHMENT}"
#
#   # Allow the instance to accept connections from this endpoint:
#   gcloud sql instances patch "${INSTANCE}" \
#       --psc-allowed-projects="${PROJECT_ID}"
#
#   echo "PSC endpoint internal IP: ${PSC_IP}  (private, only reachable in the VPC)"
#
# --------------------------------------------------------------------------------
# Step 3 — Create the ingest service account and the IAM database user that
#          maps to it. The SA is the only identity that can read/write the DB.
# --------------------------------------------------------------------------------
#   gcloud iam service-accounts create "${SA}" \
#       --display-name="Crunch ingest (Cloud Run + IAM DB auth)"
#
#   # The Cloud SQL IAM user is the SA email WITHOUT the .gserviceaccount.com suffix:
#   DB_IAM_USER="${SA}@${PROJECT_ID}.iam"
#   gcloud sql users create "${DB_IAM_USER}" \
#       --instance="${INSTANCE}" \
#       --type=CLOUD_IAM_SERVICE_ACCOUNT
#
#   # The SA needs roles to USE Cloud SQL via IAM auth and to connect:
#   gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
#       --member="serviceAccount:${SA_EMAIL}" --role="roles/cloudsql.client"
#   gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
#       --member="serviceAccount:${SA_EMAIL}" --role="roles/cloudsql.instanceUser"
#
#   # Grant the IAM user table privileges. Connect as the built-in admin ONCE to
#   # GRANT, then never again. Easiest path: use `gcloud sql connect` from Cloud
#   # Shell (which is inside Google's network) OR run the grant from the app's
#   # startup (the app's CREATE TABLE already implies the SA owns the table it
#   # creates). For this exercise the app creates the table as the IAM user on
#   # startup, so the IAM user owns it and no extra GRANT is needed.
#
# --------------------------------------------------------------------------------
# Step 4 — Build and push the image.
# --------------------------------------------------------------------------------
#   gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
#   docker build --platform=linux/amd64 -t "${IMAGE}" .
#   docker push "${IMAGE}"
#
# --------------------------------------------------------------------------------
# Step 5 — Deploy to Cloud Run with DIRECT VPC EGRESS so it can reach the PSC
#          endpoint, running AS the ingest SA, with the env the app needs.
#          Direct VPC egress (--network/--subnet) is the 2026 default; it
#          replaces the old Serverless VPC Access connector for most cases.
# --------------------------------------------------------------------------------
#   gcloud run deploy crunch-psc \
#       --image="${IMAGE}" \
#       --region="${REGION}" \
#       --service-account="${SA_EMAIL}" \
#       --network="${VPC}" \
#       --subnet="${SUBNET}" \
#       --vpc-egress=private-ranges-only \
#       --no-allow-unauthenticated \
#       --set-env-vars="INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:${INSTANCE}" \
#       --set-env-vars="DB_NAME=crunch" \
#       --set-env-vars="DB_IAM_USER=${DB_IAM_USER}" \
#       --concurrency=80 \
#       --cpu=1 --memory=512Mi \
#       --min-instances=0 --max-instances=4
#   # --vpc-egress=private-ranges-only sends RFC1918 traffic (the PSC endpoint)
#   # through the VPC and lets public traffic (none here) go direct. The PSC
#   # endpoint IP is private, so it routes through the VPC -- which is the point.
#
# --------------------------------------------------------------------------------
# Step 6 — Verify. The service requires auth; mint an identity token to call it.
# --------------------------------------------------------------------------------
#   URL=$(gcloud run services describe crunch-psc --region="${REGION}" \
#       --format='value(status.url)')
#   TOKEN=$(gcloud auth print-identity-token)
#
#   curl -s -H "Authorization: Bearer ${TOKEN}" "${URL}/whoami" | python3 -m json.tool
#   # EXPECTED: "db_user": "crunch-ingest@PROJECT_ID.iam"  (the SA, NOT postgres)
#   #           proving IAM auth: the connection's Postgres user IS the SA, and
#   #           no password was ever set or sent.
#
#   curl -s -X POST -H "Authorization: Bearer ${TOKEN}" \
#       "${URL}/events?payload=hello-from-psc" | python3 -m json.tool
#   # EXPECTED: {"id": 1}
#   curl -s -H "Authorization: Bearer ${TOKEN}" "${URL}/events/count" | python3 -m json.tool
#   # EXPECTED: {"count": 1}
#
# --------------------------------------------------------------------------------
# Step 7 — PROVE the database has no public door. Two checks:
# --------------------------------------------------------------------------------
#   gcloud sql instances describe "${INSTANCE}" \
#       --format='value(settings.ipConfiguration.ipv4Enabled)'
#   # EXPECTED: False  -- no public IP exists.
#
#   gcloud sql instances describe "${INSTANCE}" \
#       --format='value(ipAddresses)'
#   # EXPECTED: no PRIMARY/public address; only the PSC path exists.
#
#   # And confirm you CANNOT reach it from your laptop directly (it has no
#   # public IP and no public address to even attempt). The only path is the
#   # PSC endpoint, which lives inside the VPC.
#
# ==============================================================================
# ACCEPTANCE CRITERIA
# ==============================================================================
#
#   [ ] The Cloud SQL instance has ipv4Enabled=False (no public IP).
#   [ ] A PSC endpoint (forwarding rule) in the Week 03 VPC points at the
#       instance's service attachment.
#   [ ] cloudsql.iam_authentication=on; an IAM service-account DB user exists.
#   [ ] The Cloud Run service runs AS the ingest SA, with Direct VPC egress.
#   [ ] /whoami returns the SA as current_user (NOT "postgres", NOT a password user).
#   [ ] POST /events then GET /events/count proves a write/read over the private path.
#   [ ] There is NO database password anywhere: not in env, not in Secret Manager,
#       not in the connection string. IAM auth supplies a short-lived token.
#
# ==============================================================================
# NEGATIVE TEST (do this — it is instructive)
# ==============================================================================
#
#   Remove the SA's instanceUser role and watch the connection fail with an auth
#   error (the IDENTITY resolves but is no longer AUTHORIZED to log in):
#     gcloud projects remove-iam-policy-binding "${PROJECT_ID}" \
#       --member="serviceAccount:${SA_EMAIL}" --role="roles/cloudsql.instanceUser"
#     curl -s -H "Authorization: Bearer ${TOKEN}" "${URL}/events/count"
#     # EXPECTED: a 500 with a Postgres auth/permission error. Authentication and
#     # authorization are separate: PSC + the token handled REACHABILITY and
#     # IDENTITY; the IAM role handles whether that identity may log in.
#   Re-add the role before moving on.
#
# ==============================================================================
# RUN IT LOCALLY FIRST (optional sanity check)
# ==============================================================================
#
#   The connector also works from your laptop -- but only if you can REACH the
#   instance. With a PSC-only instance you cannot from a coffee shop. From Cloud
#   Shell (inside Google's network) or a VM in the VPC you can. To test the app
#   logic locally against a TEMPORARY public-IP test instance, set
#   ip_type=IPTypes.PUBLIC in this file -- but NEVER ship that. The whole point
#   is that production is PSC + private. Revert before deploying.
#
# ==============================================================================
# TEARDOWN (do not skip — Cloud SQL bills per hour)
# ==============================================================================
#
#   gcloud run services delete crunch-psc --region="${REGION}" --quiet
#   gcloud compute forwarding-rules delete "${INSTANCE}-psc-ep" --region="${REGION}" --quiet
#   gcloud compute addresses delete "${INSTANCE}-psc-ip" --region="${REGION}" --quiet
#   gcloud sql instances delete "${INSTANCE}" --quiet
#   gcloud iam service-accounts delete "${SA_EMAIL}" --quiet
#
#   Confirm: cloud sql instances: 0 · forwarding rules (PSC): 0 · cloud run: 0
"""
End of exercise. The application code (top of file) is complete and runnable.
Everything after the first triple-quoted block is the runbook in comment form.
"""
