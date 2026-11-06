#!/usr/bin/env bash
# Deploys the skull-removal worker: scale-to-zero, private, CPU only, in brain-mri-476110 ONLY.
# Measured peak memory 8.8 GiB on public images, so 12 GiB; over 8 GiB Cloud Run needs 4 CPUs. No instance runs while nobody uses it.
set -euo pipefail

PROJECT="brain-mri-476110"
REGION="us-central1"
SERVICE="strip-worker"
IMAGE="gcr.io/${PROJECT}/${SERVICE}:latest"

gcloud builds submit --project "${PROJECT}" --tag "${IMAGE}" --timeout=1800s .
gcloud run deploy "${SERVICE}" --project "${PROJECT}" --region "${REGION}" --image "${IMAGE}" \
  --cpu 4 --memory 12Gi --min-instances 0 --max-instances 2 --concurrency 1 --timeout 180 \
  --no-allow-unauthenticated
URL=$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" --region "${REGION}" --format="value(status.url)")
echo "Worker: ${URL}"
echo "Main service: SKULL_STRIP_ENABLED=true SKULL_STRIP_ENDPOINT=${URL}, and grant it roles/run.invoker on ${SERVICE}."
