#!/usr/bin/env bash
# Reproducible download of MSLesSeg (Rondinella et al., Nature Sci Data 2025),
# CC-BY-4.0, from Figshare DOI 10.6084/m9.figshare.27919209. Pulls ONLY the
# PREPROCESSED archive ("MSLesSeg Dataset.zip", ~1.47 GB) — already registered to
# MNI152 1 mm + brain-extracted, with expert lesion masks — not the RAW (1.3 GB)
# or code archives. Free (no Google Cloud cost).
#
#   bash data/manifests/fetch_mslesseg.sh
set -euo pipefail

DEST="${1:-data/external/mslesseg}"
URL="https://ndownloader.figshare.com/files/52771814"   # "MSLesSeg Dataset.zip" (preprocessed, MNI 1mm)
mkdir -p "$DEST"
ZIP="$DEST/mslesseg-preprocessed.zip"

if [ ! -f "$ZIP" ]; then
  echo "[fetch] downloading MSLesSeg preprocessed (~1.47 GB)..."
  curl -L --fail --retry 3 -o "$ZIP" "$URL"
fi

echo "[fetch] extracting..."
if command -v unzip >/dev/null 2>&1; then
  unzip -o -q "$ZIP" -d "$DEST"
else
  python -m zipfile -e "$ZIP" "$DEST"
fi
rm -f "$ZIP"                      # keep only the extracted tree (saves 1.47 GB)

echo "[fetch] done:"
du -sh "$DEST"
find "$DEST" -maxdepth 2 -type d | head -20
