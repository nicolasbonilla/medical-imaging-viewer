#!/usr/bin/env bash
# Deploy the brain-mri backend to PRODUCTION (Cloud Run, us-central1, project brain-mri-476110).
#
# Always use this script instead of a bare `gcloud builds submit`: it names the project
# explicitly, so the machine's default gcloud project (which may belong to an unrelated
# product) is never used. On 2026-10-17 a bare submit uploaded the source and created a
# failing service in an unrelated project. cloudbuild.yaml also refuses any other project.
set -euo pipefail

PROJECT="brain-mri-476110"
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain --untracked-files=no -- . ':!.claude')" ]; then
  echo "Refusing to deploy: the working tree has uncommitted changes." >&2
  exit 1
fi

SHA="$(git rev-parse --short HEAD)"
echo "Deploying commit ${SHA} to project ${PROJECT} (Cloud Run brain-mri, us-central1)..."
gcloud builds submit --project="${PROJECT}" --config=cloudbuild.yaml --substitutions=COMMIT_SHA="${SHA}"

echo "Serving revision:"
gcloud run services describe brain-mri --project="${PROJECT}" --region=us-central1 \
  --format="value(status.latestReadyRevisionName,status.traffic[0].percent,spec.template.spec.containers[0].image)"
