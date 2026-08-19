#!/usr/bin/env bash
# Deploy the FLAMeS worker as a scale-to-zero Cloud Run GPU (NVIDIA L4) service.
# One-time cost model: ~$0.67/GPU-hr, scale-to-zero -> ~1-2 cents per study inference,
# ~$0 idle. Cold start ~30-90 s (mitigated by baked weights + startup CPU boost).
set -euo pipefail

PROJECT="${PROJECT:-brain-mri-476110}"
REGION="${REGION:-us-central1}"           # L4 GPU region
SERVICE="${SERVICE:-flames-worker}"
IMAGE="gcr.io/${PROJECT}/${SERVICE}:latest"

echo "==> building ${IMAGE} (nnU-Net + SynthStrip + baked FLAMeS weights, ~6-8 GB)"
gcloud builds submit --project "${PROJECT}" --tag "${IMAGE}" --timeout=3600s .

echo "==> deploying ${SERVICE} to Cloud Run (L4 GPU, scale-to-zero)"
gcloud run deploy "${SERVICE}" \
  --project "${PROJECT}" --region "${REGION}" \
  --image "${IMAGE}" \
  --gpu 1 --gpu-type nvidia-l4 \
  --cpu 8 --memory 32Gi \
  --min-instances 0 --max-instances 3 \
  --concurrency 1 \
  --timeout 900 \
  --no-cpu-throttling \
  --no-allow-unauthenticated \
  --execution-environment gen2

URL=$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" --region "${REGION}" --format="value(status.url)")
echo "==> FLAMeS worker deployed: ${URL}"
echo "    Set the main service env: FLAMES_ENABLED=true  FLAMES_ENDPOINT=${URL}"
echo "    (and grant the main service's SA run.invoker on ${SERVICE}, plus storage access.)"
