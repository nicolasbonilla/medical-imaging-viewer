#!/bin/bash
# MSTool research cloud job: does the AI mark the same lesions on a FLAIR stripped with SynthStrip (free weights) as with the current
# strip? Public data, production build, real browser, one fold. Project mstool-research ONLY. VM deleted by the trap on any exit.
#
# Run 4, the flow as built: the worker's own code removes the skull of images inside the app's range, and the production build reads them with
# its real input gates (strippedByApp). Both SynthStrip models. Acceptance, fixed before the run: at least 90 % of the images pass the gates
# and finish; lesion sensitivity against the expert no more than 2 points below the current strip. The better model is the one that goes in.
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
RATE=0.36; BK="gs://mstool-research-data"; PFX="skull-strip"
START=$(date +%s)
log(){ gcloud storage cp /var/log/job.log "$BK/$PFX/logs/$NAME.log" --quiet 2>/dev/null || true; }
finish(){
  DUR=$(($(date +%s)-START)); COST=$(python3 -c "print(round($DUR/3600*$RATE,4))" 2>/dev/null || echo NA)
  echo "COST_RECORD,run_id=$NAME,seconds=$DUR,cost_usd_compute_estimate=$COST" | tee /var/log/cost.txt
  gcloud storage cp /var/log/cost.txt "$BK/$PFX/cost/$NAME.txt" --quiet 2>/dev/null || true
  log
  gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
}
trap finish EXIT
( sleep 5400; echo "WALL-CLOCK GUARD HIT"; kill -TERM $$ ) &

export DEBIAN_FRONTEND=noninteractive HOME=/root
apt-get update -qq && apt-get install -y -qq curl xz-utils || exit 1
W=/w; mkdir -p $W/out $W/models $W/data $W/raw; cd $W
gcloud storage cp "$BK/skull-strip/code/flow.tar.gz" $W/ --quiet || exit 1
mkdir repo && tar -xzf $W/flow.tar.gz -C repo || exit 1

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/root/.local/bin:$PATH"
uv venv --python 3.11 /w/venv || exit 1
source /w/venv/bin/activate
uv pip install torch --index-url https://download.pytorch.org/whl/cpu || exit 1
uv pip install nipreps-synthstrip numpy scipy nibabel psutil playwright fastapi || exit 1
python -m playwright install --with-deps chromium || exit 1
curl -fsSL -o $W/synthstrip.1.pt https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/requirements/synthstrip.1.pt || exit 1
curl -fsSL -o $W/synthstrip.nocsf.1.pt https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/requirements/synthstrip.nocsf.1.pt || exit 1

curl -fsSL https://nodejs.org/dist/v22.11.0/node-v22.11.0-linux-x64.tar.xz | tar -xJ -C /opt || exit 1
export PATH="/opt/node-v22.11.0-linux-x64/bin:$PATH"
(cd repo/frontend && npm ci --no-audit --no-fund && VITE_ENABLE_BROWSER_FLAMES=true npm run build) || exit 1
log

gcloud storage cp "$BK/site-guarantee/models/flames-fold0-2a10bb9d.onnx" $W/models/ --quiet || exit 1
gcloud storage cp "$BK/inputs/extra_cohorts_raw_v1.tar.gz" $W/a.tar.gz --quiet || exit 1
tar -xzf $W/a.tar.gz -C $W/raw || exit 1
CO="$BK/flames-ensemble/cohort"
python - <<'PY'
# Images with a real skull, inside the app's range (no axis above 6 mm).
import glob, json, os
import nibabel as nib
picked = []
for f in sorted(glob.glob("/w/raw/**/muslim_*_flair.nii.gz", recursive=True)):
    if max(nib.load(f).header.get_zooms()[:3]) <= 6 and len(picked) < 20:
        picked.append({"name": os.path.basename(f).split("_flair")[0], "raw": f})
print(picked)
json.dump(picked, open("/w/picked.json", "w"))
open("/w/names.txt", "w").write(" ".join(c["name"] for c in picked))
PY
for c in $(cat /w/names.txt); do
  gcloud storage cp "$CO/${c}_f0_prob.nii.gz" "$CO/${c}_gt.nii.gz" $W/data/ --quiet
done
python - <<'PY'
# The worker's own code, on each model.
import json, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/w/repo/strip-worker")
import server
for tag, weights in (("nocsf", "/w/synthstrip.nocsf.1.pt"),):
    server.MODEL = weights
    cases = []
    for c in json.load(open("/w/picked.json")):
        n = c["name"]
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(c["raw"], f"{d}/flair.nii.gz")
            brain = server.strip_file(Path(f"{d}/flair.nii.gz"), Path(d))
            shutil.copy(brain, f"/w/data/{n}_{tag}.nii.gz")
        cases.append({"name": n, "flair": f"/w/data/{n}_{tag}.nii.gz", "probs": [f"/w/data/{n}_f0_prob.nii.gz"], "gt": f"/w/data/{n}_gt.nii.gz"})
    json.dump(cases, open(f"/w/cases_{tag}.json", "w"))
print("stripped")
PY
log
for tag in nocsf; do
  python repo/research/skull_strip/browser/ensemble_check.py --dist repo/frontend/dist --models $W/models --cases /w/cases_$tag.json --out $W/out/$tag --folds 0
done
python - <<'PY'
import json, statistics as st
for tag in ("nocsf",):
    rows = json.load(open(f"/w/out/{tag}/ensemble_check.json"))
    good = [r for r in rows if "comparison" in r]
    print(tag, "complete", len(good), "of", len(rows)); [print("  ", r["name"], str(r.get("error"))[:110]) for r in rows if "comparison" not in r]
    if good:
        d = [r["comparison"]["dice"] for r in good]; b = [r["comparison"]["expert_browser"] for r in good]; f = [r["comparison"]["expert_reference"] for r in good]
        print("  dice median", round(st.median(d), 3), "worst", round(min(d), 3), "sens", round(st.mean(x["sensitivity"] for x in b), 3), round(st.mean(x["sensitivity"] for x in f), 3),
              "prec", round(st.mean(x["precision"] for x in b), 3), round(st.mean(x["precision"] for x in f), 3), "seconds", st.median(r["seconds"] for r in good))
PY
gcloud storage cp -r $W/out "$BK/$PFX/results/$NAME/" --quiet || exit 1
echo JOB_OK
