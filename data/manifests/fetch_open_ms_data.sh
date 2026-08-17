#!/usr/bin/env bash
# Reproducible, SELECTIVE download of the Ljubljana open_ms_data (Lesjak et al. 2018):
# the 3-rater CONSENSUS MS lesion masks already in MNI 1mm space. Pulls ONLY the
# ~0.57 GB cross_sectional/MNI subset (the full repo is 9.5 GB) via a blobless,
# sparse checkout — so it is fast, small, and costs nothing on Google Cloud.
#
#   bash data/manifests/fetch_open_ms_data.sh
#
# Result: data/external/open_ms_data/cross_sectional/MNI/patientNN/
#   FLAIR_..._regtoMNI.nii.gz  T1_..._regtoMNI.nii.gz  ...  GOLD_STANDARD_..._regtoMNI.nii.gz  (GT)
set -euo pipefail

REPO="https://github.com/muschellij2/open_ms_data.git"
DEST="${1:-data/external/open_ms_data}"
WANT="cross_sectional/MNI"          # add "longitudinal" later for the C4 head

mkdir -p "$(dirname "$DEST")"
if [ -d "$DEST/.git" ]; then
  echo "[fetch] repo present -> updating sparse set"
  git -C "$DEST" sparse-checkout set "$WANT"
else
  echo "[fetch] blobless + sparse clone (downloads only $WANT)"
  git clone --filter=blob:none --sparse "$REPO" "$DEST"
  git -C "$DEST" sparse-checkout set "$WANT"
fi

echo "[fetch] done. Downloaded subset:"
du -sh "$DEST/$WANT"
echo "[fetch] patients:"
ls "$DEST/$WANT" | grep -c patient || true
