#!/bin/bash
# Paper 1 healthy-control arm — final evaluation, once every tool VM has deleted itself
# (PREREG-healthy-controls.md section 11 step 7). Downloads use ONLY project mstool-research through the
# isolated gcloud config; the analysis itself runs with NO cloud credentials (offline environment).
#
#     bash research/paper_1/run_final_evaluation.sh <scratch dir OUTSIDE the repository>
#
# Data stay outside the repository (SibBMS is CC BY-NC-SA); only counts and tables are written to
# research/paper_1/results/. The analysis Python must import the app (fastapi etc.): backend/venv.
set -euo pipefail
WT="$(cd "$(dirname "$0")/../.." && pwd)"
D="${1:?give a scratch folder outside the repository}"
B=gs://mstool-research-data
G="gcloud storage"
PRJ="--project=mstool-research"
PY="${PAPER1_PYTHON:-C:/Users/Nicolas/medical-imaging-viewer/backend/venv/Scripts/python.exe}"
mkdir -p "$D/flames" "$D/lstai" "$D/brainmask" "$D/toolbench" "$D/manifests" "$D/empty_gcloud"

echo "== 1. downloads (project mstool-research, isolated config)"
(
  export CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool
  [ -n "$(ls "$D/flames" 2>/dev/null)" ] || $G cp "$B/flames-ensemble/cohort/sub-*" "$D/flames/" $PRJ --quiet
  [ -n "$(ls "$D/lstai" 2>/dev/null)" ] || $G cp "$B/lstai/cohort/sub-*_lstai_prob.nii.gz" "$D/lstai/" $PRJ --quiet
  [ -n "$(ls "$D/brainmask" 2>/dev/null)" ] || $G cp "$B/controls/sibbms/*_brainmask.nii.gz" "$D/brainmask/" $PRJ --quiet
  $G cp "$B/toolbench/cohort/sub-*_seg.nii.gz" "$D/toolbench/" $PRJ --quiet
  $G cp "$B/toolbench/manifests/toolbench-ctl-*.json" "$B/lstai/manifests/lstai-ctl.json" "$D/manifests/" $PRJ --quiet
  $G cp "$B/toolbench/cost/toolbench-ctl-*.txt" "$D/manifests/" $PRJ --quiet
  gcloud compute instances list $PRJ --filter="name~^toolbench-ctl" --format="value(name)" > "$D/still_running.txt"
)
if [ -s "$D/still_running.txt" ]; then echo "VMs still running: $(cat "$D/still_running.txt") -> wait"; exit 1; fi
echo "tool outputs: $(ls "$D/toolbench" | wc -l) (expected 300 at tier A)"

export GOOGLE_APPLICATION_CREDENTIALS="$D/no_such_credentials.json" CLOUDSDK_CONFIG="$D/empty_gcloud" \
       GOOGLE_CLOUD_PROJECT=mstool-offline-tests
CASES=$(seq -f "sub-%03g" 1 100 | tr '\n' ' ')
cd "$WT"
echo "== 2. G3 structural check (no outcome printed)"
"$PY" -I research/paper_1/evaluate_controls.py check --tool-dir "$D/toolbench" --manifests "$D/manifests" \
    --tools wmhsynthseg mindglide samseg --cases $CASES > "$D/g3_check.txt" || true
tail -1 "$D/g3_check.txt"; grep FAIL "$D/g3_check.txt" | head -20 || true
echo "== 3. evaluation (all six arms), once"
"$PY" -I research/paper_1/evaluate_controls.py run --flames-dir "$D/flames" --lstai-dir "$D/lstai" \
    --tool-dir "$D/toolbench" --brainmask-dir "$D/brainmask" --manifests "$D/manifests" \
    --out research/paper_1/results --workers 3
cp "$D/g3_check.txt" research/paper_1/results/g3_structural_check.txt
echo "== 4. G2 independent recount"
"$PY" -I research/paper_1/check_counts.py --results research/paper_1/results --flames-dir "$D/flames" \
    --lstai-dir "$D/lstai" --tool-dir "$D/toolbench"
echo "== 5. compute ledger (reads mstool-research only; isolated config set inside build_ledger.py)"
( unset GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_PROJECT; export CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool
  python research/cloud/build_ledger.py )
echo "done: research/paper_1/results/{summary.json,tables.md,per_control.csv,lesions.csv,independent_check.json}"
