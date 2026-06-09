#!/usr/bin/env python3
"""Exercise 2 — Binary Authorization with a Cloud Build-signed attestor.

Goal: wire Binary Authorization on the GKE deploy path so that ONLY images
      built and signed by your Cloud Build pipeline can run, then PROVE it:
      a signed image admits, an unsigned image is denied. This script is an
      orchestrator over `gcloud` and `kubectl` — it builds the attestor, signs
      an attestation with a Cloud KMS key, applies a dry-run-then-enforce
      policy, and runs the two verification deploys.

Estimated time: 80 minutes.

HOW TO USE THIS FILE

1. Have the Week 06 GKE cluster reachable and Binary Authorization enabled on
   it (the cluster's `enable_binary_authorization` / evaluationMode must be set;
   step 0 below checks and instructs). You also need an Artifact Registry repo.

2. Create a venv and install the SDK used for the signing helper:

       python -m venv .venv && source .venv/bin/activate
       pip install google-cloud-kms==3.* google-cloud-binary-authorization==1.*

3. Set the environment variables in the CONFIG block, then run the phases in
   order. Each phase is a function; `main()` runs them. Fill in the four TODOs.

       export PROJECT_ID=...    REGION=us-central1
       export CLUSTER=...       ZONE=us-central1-a
       export AR_REPO=app       # Artifact Registry repo name
       python exercise-02-binary-authorization-cloud-build-attestor.py

ACCEPTANCE CRITERIA

  [ ] An attestor exists, backed by a Cloud KMS asymmetric-sign key.
  [ ] Cloud Build builds an image AND creates a signed attestation for its digest.
  [ ] The Binary Authorization policy requires an attestation from that attestor.
  [ ] Policy is rolled out DRYRUN first, audited, then ENFORCED (no straight-to-block).
  [ ] Deploying the SIGNED image succeeds.
  [ ] Deploying an UNSIGNED image (e.g. nginx:latest) is DENIED at admission.
  [ ] The deny transcript is saved to verify-ex02.txt.

SMOKE OUTPUT (target)

  [phase 1] attestor 'build-attestor' ready (KMS key version 1)
  [phase 2] built image, digest sha256:ab12... and signed attestation
  [phase 3] policy applied in DRYRUN mode
  [phase 3] policy promoted to ENFORCED_BLOCK_AND_AUDIT_LOG
  [verify ] signed image: ADMITTED
  [verify ] unsigned image: DENIED  <-- this is the win
  PASS: Binary Authorization enforces the build-signed attestor.

Inline hints at the bottom of the file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# CONFIG — read from the environment so the file stays secret-free.
# ---------------------------------------------------------------------------
PROJECT_ID = os.environ["PROJECT_ID"]
REGION = os.environ.get("REGION", "us-central1")
ZONE = os.environ.get("ZONE", f"{REGION}-a")
CLUSTER = os.environ["CLUSTER"]
AR_REPO = os.environ.get("AR_REPO", "app")

ATTESTOR = "build-attestor"
NOTE_ID = "build-attestor-note"
KEYRING = "binauthz"
KEY = "attestor-key"
IMAGE_PATH = f"{REGION}-docker.pkg.dev/{PROJECT_ID}/{AR_REPO}/probe"


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command, echoing it. Returns the CompletedProcess."""
    print("    $ " + " ".join(cmd))
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        capture_output=capture,
    )


# ---------------------------------------------------------------------------
# PHASE 0 — preflight: confirm the cluster has Binary Authorization wired.
# ---------------------------------------------------------------------------
def phase0_preflight() -> None:
    print("[phase 0] preflight")
    run(["gcloud", "services", "enable",
         "binaryauthorization.googleapis.com", "containeranalysis.googleapis.com",
         "cloudkms.googleapis.com", "artifactregistry.googleapis.com",
         f"--project={PROJECT_ID}"])
    # Confirm the cluster exists and reports a Binary Authorization evaluation mode.
    cp = run(["gcloud", "container", "clusters", "describe", CLUSTER,
              f"--zone={ZONE}", f"--project={PROJECT_ID}",
              "--format=value(binaryAuthorization.evaluationMode)"],
             capture=True)
    mode = cp.stdout.strip()
    if not mode or mode == "DISABLED":
        print("    WARNING: cluster does not have Binary Authorization enabled.")
        print("    Enable it (recreates the admission webhook config):")
        print(f"      gcloud container clusters update {CLUSTER} --zone={ZONE} \\")
        print("        --binauthz-evaluation-mode=PROJECT_SINGLETON_POLICY_ENFORCE")
        sys.exit(1)
    print(f"    cluster evaluation mode = {mode}")
    run(["gcloud", "container", "clusters", "get-credentials", CLUSTER,
         f"--zone={ZONE}", f"--project={PROJECT_ID}"])


# ---------------------------------------------------------------------------
# PHASE 1 — create the KMS signing key, the Container Analysis note, and the
#           attestor that trusts the key.
# ---------------------------------------------------------------------------
def phase1_attestor() -> str:
    print("[phase 1] attestor + KMS signing key")
    # KMS key ring + asymmetric-sign key.
    run(["gcloud", "kms", "keyrings", "create", KEYRING,
         f"--location={REGION}", f"--project={PROJECT_ID}"], check=False)

    # TODO 1 — create an ASYMMETRIC_SIGN key in the keyring.
    #
    # The key PURPOSE must be `asymmetric-signing` and a signing algorithm such
    # as `ec-sign-p256-sha256`. Binary Authorization verifies attestations with
    # the key's PUBLIC half, so the key must be a signing key, not encryption.
    #
    #   gcloud kms keys create <KEY> --location=<REGION> --keyring=<KEYRING> \
    #     --purpose=asymmetric-signing --default-algorithm=ec-sign-p256-sha256
    #
    # YOUR CODE HERE (one run([...]) call, check=False so reruns are idempotent)

    # The Container Analysis note that backs the attestor.
    note_payload = {
        "name": f"projects/{PROJECT_ID}/notes/{NOTE_ID}",
        "attestation": {"hint": {"human_readable_name": "Cloud Build attestor"}},
    }
    with open("/tmp/note.json", "w") as fh:
        json.dump(note_payload, fh)
    run(["curl", "-s", "-X", "POST",
         "-H", "Content-Type: application/json",
         "-H", f"Authorization: Bearer {_token()}",
         f"https://containeranalysis.googleapis.com/v1/projects/{PROJECT_ID}/notes/?noteId={NOTE_ID}",
         "-d", f"@/tmp/note.json"], check=False)

    # Create the attestor and attach the KMS public key version.
    run(["gcloud", "container", "binauthz", "attestors", "create", ATTESTOR,
         f"--attestation-authority-note={NOTE_ID}",
         f"--attestation-authority-note-project={PROJECT_ID}",
         f"--project={PROJECT_ID}"], check=False)

    key_version = (
        f"projects/{PROJECT_ID}/locations/{REGION}/keyRings/{KEYRING}"
        f"/cryptoKeys/{KEY}/cryptoKeyVersions/1"
    )
    run(["gcloud", "container", "binauthz", "attestors", "public-keys", "add",
         f"--attestor={ATTESTOR}",
         f"--keyversion={key_version}",
         f"--project={PROJECT_ID}"], check=False)
    print(f"    attestor '{ATTESTOR}' ready (KMS key version 1)")
    return key_version


# ---------------------------------------------------------------------------
# PHASE 2 — build an image and sign an attestation for its digest.
#           In production Cloud Build does this; here we emulate the build
#           step's signing so the exercise is self-contained, then point you
#           at the cloudbuild.yaml that does it in CI.
# ---------------------------------------------------------------------------
def phase2_build_and_sign(key_version: str) -> str:
    print("[phase 2] build + sign attestation")
    # A trivial Dockerfile so the build is fast and free-ish.
    with open("/tmp/Dockerfile", "w") as fh:
        fh.write("FROM gcr.io/distroless/static:nonroot\n")
    run(["gcloud", "artifacts", "repositories", "create", AR_REPO,
         "--repository-format=docker", f"--location={REGION}",
         f"--project={PROJECT_ID}"], check=False)

    # Build with Cloud Build and capture the resulting digest.
    run(["gcloud", "builds", "submit", "/tmp",
         f"--tag={IMAGE_PATH}:v1", f"--project={PROJECT_ID}"])
    cp = run(["gcloud", "artifacts", "docker", "images", "describe",
              f"{IMAGE_PATH}:v1", "--format=value(image_summary.digest)",
              f"--project={PROJECT_ID}"], capture=True)
    digest = cp.stdout.strip()
    image_url = f"{IMAGE_PATH}@{digest}"
    print(f"    built image, digest {digest[:14]}...")

    # TODO 2 — sign an attestation for this digest with the attestor.
    #
    # `gcloud container binauthz attestations sign-and-create` builds the
    # payload for the image URL, signs it with the KMS key version, and uploads
    # the attestation occurrence. This is EXACTLY what the Cloud Build step does
    # in `cloudbuild.yaml` (see the bottom of this file).
    #
    #   gcloud container binauthz attestations sign-and-create \
    #     --artifact-url=<image_url> \
    #     --attestor=<ATTESTOR> --attestor-project=<PROJECT_ID> \
    #     --keyversion=<key_version> \
    #     --keyversion-project=<PROJECT_ID> \
    #     --keyversion-location=<REGION> \
    #     --keyversion-keyring=<KEYRING> --keyversion-key=<KEY>
    #
    # YOUR CODE HERE (one run([...]) call)

    print("    signed attestation for digest")
    return image_url


# ---------------------------------------------------------------------------
# PHASE 3 — apply the policy, dry-run first, then enforce.
# ---------------------------------------------------------------------------
def phase3_policy() -> None:
    print("[phase 3] policy: dry-run then enforce")

    # TODO 3 — write the Binary Authorization policy YAML.
    #
    # Requirements:
    #   * defaultAdmissionRule.evaluationMode = REQUIRE_ATTESTATION
    #   * defaultAdmissionRule.requireAttestationsBy = [ <attestor resource> ]
    #   * defaultAdmissionRule.enforcementMode = DRYRUN_AUDIT_LOG_ONLY  (first pass)
    #   * admissionWhitelistPatterns for system images:
    #       gcr.io/google-containers/*, k8s.gcr.io/*, registry.k8s.io/*,
    #       and your Artifact Registry repo path with /* so system pulls work.
    #
    # The attestor resource string is:
    #   projects/<PROJECT_ID>/attestors/<ATTESTOR>
    #
    attestor_resource = f"projects/{PROJECT_ID}/attestors/{ATTESTOR}"
    policy_yaml = ""  # YOUR CODE HERE — build the YAML string (see HINT 3)

    if not policy_yaml.strip():
        print("    TODO 3 not filled in — write the policy YAML.")
        sys.exit(1)

    with open("/tmp/binauthz-policy.yaml", "w") as fh:
        fh.write(policy_yaml)
    run(["gcloud", "container", "binauthz", "policy", "import",
         "/tmp/binauthz-policy.yaml", f"--project={PROJECT_ID}"])
    print("    policy applied in DRYRUN mode")

    # Audit window: in DRYRUN, deploys are NOT blocked; the would-be denials are
    # logged. In a real rollout you wait a working day and read the audit log.
    # Here we wait briefly so the admission webhook picks up the new policy.
    time.sleep(20)

    # Promote to enforce by swapping the enforcement mode and re-importing.
    enforced = policy_yaml.replace(
        "DRYRUN_AUDIT_LOG_ONLY", "ENFORCED_BLOCK_AND_AUDIT_LOG"
    )
    with open("/tmp/binauthz-policy-enforced.yaml", "w") as fh:
        fh.write(enforced)
    run(["gcloud", "container", "binauthz", "policy", "import",
         "/tmp/binauthz-policy-enforced.yaml", f"--project={PROJECT_ID}"])
    print("    policy promoted to ENFORCED_BLOCK_AND_AUDIT_LOG")
    time.sleep(20)


# ---------------------------------------------------------------------------
# VERIFY — the whole point. Signed image admits; unsigned image is denied.
# ---------------------------------------------------------------------------
def verify(image_url: str) -> None:
    print("[verify ] signed vs unsigned")
    transcript_lines: list[str] = []

    # Signed image should ADMIT.
    cp = run(["kubectl", "run", "signed-probe", f"--image={image_url}",
              "--restart=Never", "--command", "--", "/bin/true"],
             check=False, capture=True)
    signed_ok = cp.returncode == 0
    transcript_lines.append(f"signed deploy rc={cp.returncode}\n{cp.stderr}")
    print(f"    signed image: {'ADMITTED' if signed_ok else 'REJECTED (unexpected!)'}")

    # TODO 4 — attempt to deploy an UNSIGNED image and assert it is DENIED.
    #
    # Use a public image your pipeline never signed, e.g. `nginx:latest`.
    #   kubectl run unsigned-probe --image=nginx:latest --restart=Never
    # Capture the result. The deploy MUST fail with a Binary Authorization
    # admission error mentioning "denied by Binary Authorization" / "No
    # attestations found". Set `unsigned_denied` accordingly.
    #
    unsigned_denied = False  # YOUR CODE HERE — run the unsigned deploy, set this
    # (append the stderr to transcript_lines as well)

    print(f"    unsigned image: {'DENIED' if unsigned_denied else 'ADMITTED (FAIL!)'}")

    with open("verify-ex02.txt", "w") as fh:
        fh.write("\n\n".join(transcript_lines))

    # Cleanup probes.
    run(["kubectl", "delete", "pod", "signed-probe", "unsigned-probe",
         "--ignore-not-found"], check=False)

    if signed_ok and unsigned_denied:
        print("PASS: Binary Authorization enforces the build-signed attestor.")
    else:
        print("FAIL: the control did not behave as required. Re-check the TODOs.")
        sys.exit(1)


def _token() -> str:
    return subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True, text=True, capture_output=True,
    ).stdout.strip()


def main() -> None:
    phase0_preflight()
    key_version = phase1_attestor()
    image_url = phase2_build_and_sign(key_version)
    phase3_policy()
    verify(image_url)


if __name__ == "__main__":
    main()


# ===========================================================================
# HINTS — peek only if stuck.
# ===========================================================================
#
# HINT 1 — the KMS key creation call:
#
#   run(["gcloud", "kms", "keys", "create", KEY,
#        f"--location={REGION}", f"--keyring={KEYRING}",
#        "--purpose=asymmetric-signing",
#        "--default-algorithm=ec-sign-p256-sha256",
#        f"--project={PROJECT_ID}"], check=False)
#
# HINT 2 — the sign-and-create call:
#
#   run(["gcloud", "container", "binauthz", "attestations", "sign-and-create",
#        f"--artifact-url={image_url}",
#        f"--attestor={ATTESTOR}", f"--attestor-project={PROJECT_ID}",
#        f"--keyversion-project={PROJECT_ID}",
#        f"--keyversion-location={REGION}",
#        f"--keyversion-keyring={KEYRING}",
#        f"--keyversion-key={KEY}",
#        "--keyversion=1",
#        f"--project={PROJECT_ID}"])
#
# HINT 3 — the policy YAML (DRYRUN first). Note the whitelist for your repo's
#          system pulls and Google system images:
#
#   policy_yaml = f"""\
#   defaultAdmissionRule:
#     evaluationMode: REQUIRE_ATTESTATION
#     enforcementMode: DRYRUN_AUDIT_LOG_ONLY
#     requireAttestationsBy:
#       - {attestor_resource}
#   admissionWhitelistPatterns:
#     - namePattern: gcr.io/google-containers/*
#     - namePattern: k8s.gcr.io/*
#     - namePattern: registry.k8s.io/*
#     - namePattern: gke.gcr.io/*
#   globalPolicyEvaluationMode: ENABLE
#   """
#
# HINT 4 — the unsigned-deploy verification:
#
#   cp = run(["kubectl", "run", "unsigned-probe", "--image=nginx:latest",
#             "--restart=Never"], check=False, capture=True)
#   transcript_lines.append(f"unsigned deploy rc={cp.returncode}\n{cp.stderr}")
#   unsigned_denied = (cp.returncode != 0 and
#                      "Binary Authorization" in (cp.stderr or ""))
#
# REFLECTION QUESTIONS — answer in verify-ex02.txt after the transcript:
#
# 1. Why does the policy whitelist gcr.io/google-containers/* and friends? What
#    breaks on the cluster if you require attestation for EVERY image including
#    kube-system?
# 2. Why roll out in DRYRUN before ENFORCED? Describe the exact outage you would
#    cause by going straight to ENFORCED on a running cluster whose existing
#    workloads were never attested.
# 3. The break-glass annotation `alpha.image-policy.k8s.io/break-glass: "true"`
#    bypasses the policy and writes a loud audit log. When is using it the RIGHT
#    call, and why is the loud audit log a feature, not a bug?
# 4. The attestation is signed by a KMS key Binary Authorization verifies with
#    the PUBLIC half. What attack does this prevent that a simple "image is from
#    our registry" allowlist does not?
