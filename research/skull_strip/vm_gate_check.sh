#!/bin/bash
# MSTool research cloud job, review B1 of the skull-strip branch: does the FLAIR gate still refuse T1 and T2 once the app removed the skull?
# And does a FLAIR with its skull follow the flow as built: refused as a skull, stripped, read? Public data (Muslim et al. 2022, CC BY 4.0).
# Project mstool-research ONLY. VM deleted by the trap on any exit.
#
# Acceptance, fixed before the run:
#   1  every T1 and T2, stripped by the worker code and read with strippedByApp, is refused (100 %)
#   2  every FLAIR read as uploaded is refused by a skull clue (so the app asks the server)
#   3  FLAIRs stripped and read: at least 90 % finish; sensitivity against the expert no more than 2 points below the current strip
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
RATE=0.28; BK="gs://mstool-research-data"; PFX="skull-strip"
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
gcloud storage cp "$BK/$PFX/code/flow.tar.gz" "$BK/$PFX/code/cohorts_extra.py" $W/ --quiet || exit 1
mkdir repo && tar -xzf $W/flow.tar.gz -C repo || exit 1
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/root/.local/bin:$PATH"
uv venv --python 3.11 /w/venv || exit 1
source /w/venv/bin/activate
uv pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu || exit 1
uv pip install nipreps-synthstrip==0.0.1 nibabel==5.4.2 numpy==2.4.6 scipy==1.17.1 fastapi==0.162.0 psutil playwright || exit 1
python -m playwright install --with-deps chromium || exit 1
curl -fsSL -o $W/synthstrip.1.pt https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/requirements/synthstrip.1.pt || exit 1
curl -fsSL https://nodejs.org/dist/v22.11.0/node-v22.11.0-linux-x64.tar.xz | tar -xJ -C /opt || exit 1
export PATH="/opt/node-v22.11.0-linux-x64/bin:$PATH"
(cd repo/frontend && npm ci --no-audit --no-fund && VITE_ENABLE_BROWSER_FLAMES=true npm run build) || exit 1
gcloud storage cp "$BK/site-guarantee/models/flames-fold0-2a10bb9d.onnx" $W/models/ --quiet || exit 1
gcloud storage cp "$BK/inputs/extra_cohorts_raw_v1.tar.gz" $W/a.tar.gz --quiet && tar -xzf $W/a.tar.gz -C $W/raw || exit 1
log

python - <<'PY'
# T1 and T2 with their skull, from the public archive; then every image stripped by the worker's own code.
import glob, json, os, re, shutil, sys, tempfile, zipfile
from pathlib import Path
import nibabel as nib
sys.path.insert(0, "/w"); sys.path.insert(0, "/w/repo/strip-worker")
import cohorts_extra as ce
import server
server.MODEL = "/w/synthstrip.1.pt"
zf = zipfile.ZipFile(ce.HttpRangeFile(ce._muslim_zip_url(), readahead=1 << 22))
names = zf.namelist()
print([n for n in names if n.startswith("Patient-1/")])
others = []
for pid in range(1, 61):
    for kind in ("T1", "T2"):
        hits = [n for n in names if n.startswith(f"Patient-{pid}/") and n.lower().endswith(".nii") and re.search(rf"-{kind}(\.nii|$|[^a-z0-9])", n, re.I) and "seg" not in n.lower()]
        if hits and sum(1 for o in others if o[1] == kind) < 15:
            dest = f"/w/raw/muslim_{pid:02d}_{kind}.nii"
            with zf.open(hits[0]) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            img = nib.load(dest)
            if img.ndim == 3 and max(img.header.get_zooms()[:3]) <= 6:
                others.append((f"muslim_{pid:02d}_{kind}", kind, dest))
flairs = []
for f in sorted(glob.glob("/w/raw/**/muslim_*_flair.nii.gz", recursive=True)):
    if max(nib.load(f).header.get_zooms()[:3]) <= 6 and len(flairs) < 20:
        flairs.append((os.path.basename(f).split("_flair")[0], "FLAIR", f))
print("others", len(others), "flairs", len(flairs))
stripped, raw_flairs = [], []
for name, kind, path in others + flairs:
    with tempfile.TemporaryDirectory() as d:
        img = nib.load(path); nib.save(img, f"{d}/flair.nii.gz")
        try:
            brain = server.strip_file(Path(f"{d}/flair.nii.gz"), Path(d))
        except Exception as e:
            print("strip failed", name, type(e).__name__); continue
        shutil.copy(brain, f"/w/data/{name}_stripped.nii.gz")
    case = {"name": name, "kind": kind, "flair": f"/w/data/{name}_stripped.nii.gz"}
    if kind == "FLAIR":
        case.update(probs=[f"/w/data/{name}_f0_prob.nii.gz"], gt=f"/w/data/{name}_gt.nii.gz")
        nib.save(nib.load(path), f"/w/data/{name}_raw.nii.gz")
        raw_flairs.append({"name": name + "_as_uploaded", "kind": "FLAIR raw", "flair": f"/w/data/{name}_raw.nii.gz"})
    stripped.append(case)
json.dump([c for c in stripped if c["kind"] != "FLAIR"], open("/w/cases_others.json", "w"))
json.dump([c for c in stripped if c["kind"] == "FLAIR"], open("/w/cases_flair.json", "w"))
json.dump(raw_flairs, open("/w/cases_raw.json", "w"))
open("/w/flair_names.txt", "w").write(" ".join(c["name"] for c in stripped if c["kind"] == "FLAIR"))
PY
CO="$BK/flames-ensemble/cohort"
for c in $(cat /w/flair_names.txt); do gcloud storage cp "$CO/${c}_f0_prob.nii.gz" "$CO/${c}_gt.nii.gz" $W/data/ --quiet; done
log
python repo/research/skull_strip/browser/ensemble_check.py --dist repo/frontend/dist --models $W/models --cases /w/cases_others.json --out $W/out/others --folds 0 --timeout-minutes 10
python repo/research/skull_strip/browser/ensemble_check.py --dist repo/frontend/dist --models $W/models --cases /w/cases_raw.json --out $W/out/raw --folds 0 --stripped 0 --timeout-minutes 10
log
python repo/research/skull_strip/browser/ensemble_check.py --dist repo/frontend/dist --models $W/models --cases /w/cases_flair.json --out $W/out/flair --folds 0
python - <<'PY'
import json, statistics as st
others = json.load(open("/w/out/others/ensemble_check.json"))
refused = [r for r in others if "error" in r]
print("1 T1/T2 refused", len(refused), "of", len(others)); [print("   PASSED THROUGH", r["name"]) for r in others if "error" not in r]
from collections import Counter
print("   reasons", Counter(("FLAIR" in str(r.get("error"))) for r in refused))
raw = json.load(open("/w/out/raw/ensemble_check.json"))
skull = [r for r in raw if "skull" in str(r.get("error", ""))]
print("2 FLAIR as uploaded refused by a skull clue", len(skull), "of", len(raw)); [print("   ", r["name"], str(r.get("error"))[:90]) for r in raw if r not in skull]
fl = json.load(open("/w/out/flair/ensemble_check.json"))
good = [r for r in fl if "comparison" in r]
print("3 FLAIR stripped finished", len(good), "of", len(fl)); [print("   ", r["name"], str(r.get("error"))[:90]) for r in fl if "comparison" not in r]
if good:
    b = [r["comparison"]["expert_browser"] for r in good]; f = [r["comparison"]["expert_reference"] for r in good]
    print("   sensitivity", round(st.mean(x["sensitivity"] for x in b), 3), round(st.mean(x["sensitivity"] for x in f), 3),
          "precision", round(st.mean(x["precision"] for x in b), 3), round(st.mean(x["precision"] for x in f), 3),
          "dice median", round(st.median(r["comparison"]["dice"] for r in good), 3))
PY
gcloud storage cp -r $W/out "$BK/$PFX/results/$NAME/" --quiet || exit 1
echo JOB_OK
