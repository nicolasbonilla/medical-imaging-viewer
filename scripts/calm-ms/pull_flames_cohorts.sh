#!/usr/bin/env bash
# Pull the FLAMeS-built cohort (prob + gt pairs) from GCS into data/cohorts/,
# organized by source dataset so each can feed the conformal experiment directly.
# Uses `gcloud storage` (local gsutil is broken). Free (download only).
#
#   bash scripts/calm-ms/pull_flames_cohorts.sh
#
# Then run the conformal / re-scoring experiment on each (or a merged dir):
#   python scripts/calm-ms/run_phase2_rescoring.py --data-dir data/cohorts/mslesseg115-flames \
#       --alphas 0.05,0.1,0.2,0.3 --threshold 0.5 --out data/experiments/phase2-mslesseg.json
set -euo pipefail

BK="gs://brain-mri-medical-images/calm-flames/cohort"
ALL="data/cohorts/flames-all"
mkdir -p "$ALL"

echo "[pull] downloading prob/gt pairs from $BK ..."
gcloud storage cp "$BK/*_prob.nii.gz" "$ALL/" 2>/dev/null || true
gcloud storage cp "$BK/*_gt.nii.gz"   "$ALL/" 2>/dev/null || true

# Split by source prefix into per-dataset cohorts (openms_* , mslesseg_*).
for pref in openms mslesseg; do
  d="data/cohorts/${pref}-flames"; mkdir -p "$d"
  mv "$ALL/${pref}_"*_prob.nii.gz "$d/" 2>/dev/null || true
  mv "$ALL/${pref}_"*_gt.nii.gz   "$d/" 2>/dev/null || true
  n=$(ls "$d"/*_prob.nii.gz 2>/dev/null | wc -l)
  echo "[pull] ${pref}-flames: $n prob/gt pairs"
done
rmdir "$ALL" 2>/dev/null || true

echo "[pull] done. Cohorts under data/cohorts/*-flames/"
du -sh data/cohorts/*-flames 2>/dev/null || true
