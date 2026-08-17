#!/usr/bin/env bash
# SibBMS (Tuchinov et al., MELBA 2025) — we want ONLY the 100 protocol-matched
# HEALTHY CONTROLS, which serve as a genuine conformal FALSE-NULL (every lesion
# candidate a base segmenter produces on a lesion-free brain is a false positive
# by construction). The release is a SINGLE 11 GB zip (no selective download
# possible), so this is intended to run ON THE EPHEMERAL SPOT VM during the FLAMeS
# compute step — NOT on the local disk — to avoid parking 11 GB locally.
#
# LICENSE CAVEAT: the paper states two conflicting licenses (CC BY 3.0 vs
# CC BY-NC-SA 3.0). Confirm/clarify with the authors before any non-research use.
#
#   bash data/manifests/fetch_sibbms_controls.sh /scratch/sibbms   # on the VM
set -euo pipefail

DEST="${1:-data/external/sibbms}"
URL="https://ai.nsu.ru/files/sibbms/sibbms.zip"     # ~11 GB monolithic (form fallback: forms.gle/VqTenJ4n8S8qvtxQA)
mkdir -p "$DEST"
ZIP="$DEST/sibbms.zip"

if [ ! -f "$ZIP" ]; then
  echo "[fetch] downloading SibBMS (~11 GB, VM-only)..."
  curl -L --fail --retry 3 -o "$ZIP" "$URL"
fi

echo "[fetch] archive layout (identify the healthy-control folder) ==="
# Inspect once, then extract ONLY the controls tree. Folder naming is confirmed at
# run time from this listing (controls are the lesion-free cohort, ~100 subjects).
unzip -l "$ZIP" | grep -iE "control|hc|healthy|norm" | head -20 || \
  { echo "[fetch] no obvious control/ prefix — list top-level dirs:"; \
    unzip -l "$ZIP" | awk '{print $4}' | awk -F/ '{print $1"/"$2}' | sort -u | head; }

echo "[fetch] NEXT: unzip only the controls subtree, e.g.:"
echo "        unzip \"$ZIP\" '<controls-prefix>/*' -d \"$DEST\""
echo "[fetch] then run the base segmenter on each control FLAIR to build the false-null."
