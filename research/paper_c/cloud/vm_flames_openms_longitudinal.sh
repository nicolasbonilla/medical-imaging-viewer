#!/bin/bash
# MSTool research cloud job — Paper C: FLAMeS 5-fold maps for the open_ms_data LONGITUDINAL scans
# (Lesjak et al. 2016; 20 patients x 2 studies, co-registered 2D FLAIR, CC-BY).
# Project mstool-research ONLY. Derived from research/cloud/vm_flames_ensemble_v2.sh (branch
# research/cloud-compute-ledger) with the SAME safety rules:
#  * STANDARD (non-Spot) VM; --max-run-duration caps the bill; the trap deletes the VM on any exit;
#    a wall-clock guard stops runaway jobs.
#  * Inputs mirrored ONCE into gs://.../inputs with SHA-256; the frozen env lock is reused.
#  * The UNCHANGED driver gs://.../flames-ensemble/code/flames_ensemble_driver.py uploads every
#    case-fold as soon as it finishes and skips what is already uploaded (resumable).
# Differences from v2: dataset = longitudinal/coregistered (FLAIR x supplied brain mask, no HD-BET),
# output prefix flames-openms-long (never mixes with flames-ensemble/cohort).
# Metadata: folds="0 1 2 3 4"  case-ids="" (optional pilot list)  hourly-rate  machine-desc  max-hours
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
FOLDS=$(meta attributes/folds);          FOLDS=${FOLDS:-0 1 2 3 4}
RATE=$(meta attributes/hourly-rate);     RATE=${RATE:-0.18}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-n2d-standard-4}
MAXH=$(meta attributes/max-hours);       MAXH=${MAXH:-8}
CASE_IDS=$(meta attributes/case-ids)
BKT="mstool-research-data"; BK="gs://$BKT"; PFX="flames-openms-long"
START=$(date +%s)

log(){ gcloud storage cp /var/log/job.log "$BK/$PFX/logs/$NAME.log" --quiet 2>/dev/null || true; }
stage(){ echo "$1=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> /var/log/stages.txt; }
stage boot
{
  echo "cpu_platform=$(meta cpu-platform)"
  echo "cpu_model=$(lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -1)"
  echo "vcpus=$(nproc)"
  echo "memory_gb=$(free -g | awk '/^Mem:/{print $2}')"
  echo "machine_type=$(meta machine-type | awk -F/ '{print $NF}')"
  echo "zone=$ZONE"
  echo "provisioning=$(meta scheduling/provisioning-model)"
} > /var/log/hw.txt
finish(){
  stage end
  END=$(date +%s); DUR=$((END-START))
  COST=$(python3 -c "print(round($DUR/3600*$RATE,4))" 2>/dev/null || echo NA)
  echo "COST_RECORD,run_id=$NAME,machine=$MACHINE,seconds=$DUR,rate_usd_per_h=$RATE,cost_usd_compute_estimate=$COST" | tee /var/log/cost.txt
  gcloud storage cp /var/log/cost.txt "$BK/$PFX/cost/$NAME.txt" --quiet 2>/dev/null || true
  python3 - "$NAME" "$DUR" "$RATE" "$COST" <<'PY' || true
import json, sys
def kv(p):
    out = {}
    for line in open(p):
        if "=" in line:
            k, v = line.rstrip("\n").split("=", 1); out[k] = v
    return out
info = {"run_id": sys.argv[1], "wall_seconds": int(sys.argv[2]), "rate_usd_per_h_metadata": sys.argv[3],
        "cost_usd_estimate_metadata": sys.argv[4], "hardware": kv("/var/log/hw.txt"), "stages_utc": kv("/var/log/stages.txt"),
        "paper": "C"}
json.dump(info, open("/var/log/runinfo.json", "w"), indent=1)
PY
  gcloud storage cp /var/log/runinfo.json "$BK/runs/$NAME/runinfo.json" --quiet 2>/dev/null || true
  log
  gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
}
trap finish EXIT
( sleep $((MAXH*3600)); echo "WALL-CLOCK GUARD HIT"; kill -TERM $$ ) &

W=/w; mkdir -p $W/cache $W/data; cd $W
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq unzip git python3-pip python3-venv 2>&1 | tail -1

cache_get(){
  local n="$1"; shift
  if gcloud storage cp "$BK/inputs/$n" "$W/cache/$n" --quiet 2>/dev/null; then
    echo "cache hit: $n"
  else
    echo "cache miss: $n -> fetching from source"; bash -c "$*" || return 1
    sha256sum "$W/cache/$n" | awk '{print $1}' > "$W/cache/$n.sha256"
    gcloud storage cp "$W/cache/$n" "$W/cache/$n.sha256" "$BK/inputs/" --quiet
  fi
  [ -s "$W/cache/$n" ]
}

stage env_start; echo "=== [1/5] python env (frozen lock of the v2 FLAMeS jobs) ==="
python3 -m venv /opt/venv && . /opt/venv/bin/activate
pip install -q --upgrade pip 2>&1 | tail -1
gcloud storage cp "$BK/env/requirements.lock" $W/requirements.lock --quiet || { echo "no frozen lock: run a v2 job first"; exit 1; }
pip install -q -r $W/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
python3 -c "import torch,torchvision,nnunetv2,nibabel; from torchvision.ops import nms; from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor; nms(torch.zeros((1,4)), torch.zeros(1), 0.5); print('env ok', torch.__version__)" || exit 1
log

stage weights_start; echo "=== [2/5] FLAMeS weights (cached mirror of Zenodo 17955359) ==="
cache_get flames_weights.zip 'U=$(curl -s https://zenodo.org/api/records/17955359 | python3 -c "import sys,json;d=json.load(sys.stdin);print([f[\"links\"][\"self\"] for f in d[\"files\"] if f[\"key\"].lower().endswith(\".zip\")][0])"); curl -sL -o /w/cache/flames_weights.zip "$U"' || exit 1
export nnUNet_raw=$W/raw nnUNet_preprocessed=$W/prep nnUNet_results=$W/nnunet_results
mkdir -p $nnUNet_raw $nnUNet_preprocessed $nnUNet_results
unzip -q -o $W/cache/flames_weights.zip -d $nnUNet_results/ && rm -f $W/cache/flames_weights.zip
log

stage datasets_start; echo "=== [3/5] open_ms_data longitudinal/coregistered (FLAIR, brain mask, change mask) ==="
cache_get open_ms_longitudinal_coreg_v1.tar.gz 'git clone -q --filter=blob:none --sparse https://github.com/muschellij2/open_ms_data.git /w/oms && git -C /w/oms sparse-checkout set longitudinal/coregistered && rm -f /w/oms/longitudinal/coregistered/*/study*_T1W.nii.gz /w/oms/longitudinal/coregistered/*/study*_T2W.nii.gz && tar -czf /w/cache/open_ms_longitudinal_coreg_v1.tar.gz -C /w/oms longitudinal' || exit 1
mkdir -p $W/data/oms && tar -xzf $W/cache/open_ms_longitudinal_coreg_v1.tar.gz -C $W/data/oms && rm -f $W/cache/open_ms_longitudinal_coreg_v1.tar.gz
log

stage cases_start; echo "=== [4/5] skull-strip with the SUPPLIED brain mask, case list ==="
python3 - "$CASE_IDS" <<'PY'
import glob, json, os, sys
import nibabel as nib, numpy as np
CASE_IDS = sys.argv[1].split()
root = "/w/data/oms/longitudinal/coregistered"
os.makedirs("/w/brain", exist_ok=True); os.makedirs("/w/gt", exist_ok=True)
cases = {}
for pdir in sorted(glob.glob(f"{root}/patient*")):
    pid = os.path.basename(pdir)
    bm = nib.load(f"{pdir}/brainmask.nii.gz"); m = np.asarray(bm.dataobj) > 0
    gt = nib.load(f"{pdir}/gt.nii.gz")
    for s in (1, 2):
        cid = f"openmslong_{pid}_s{s}"
        fl = nib.load(f"{pdir}/study{s}_FLAIR.nii.gz")
        assert fl.shape[:3] == m.shape and np.abs(fl.affine - bm.affine).max() < 1e-3, cid
        arr = np.asarray(fl.dataobj, dtype=np.float32) * m
        out = f"/w/brain/{cid}_FLAIR.nii.gz"
        img = nib.Nifti1Image(arr, fl.affine, fl.header.copy()); img.set_data_dtype(np.float32)
        nib.save(img, out)
        g = f"/w/gt/{cid}_gt.nii.gz"     # the expert CHANGE mask (same for s1 and s2), not a lesion mask
        nib.save(nib.Nifti1Image((np.asarray(gt.dataobj) > 0).astype(np.uint8), gt.affine, gt.header), g)
        cases[cid] = {"flair": out, "gt": g}
if CASE_IDS:
    missing = [c for c in CASE_IDS if c not in cases]
    if missing:
        sys.exit(f"case-ids not found: {missing}")
    cases = {c: cases[c] for c in CASE_IDS}
json.dump(cases, open("/w/cases.json", "w"), indent=1)
print("CASES", len(cases))
PY
[ -s /w/cases.json ] || exit 1
gcloud storage cp $W/gt/*_gt.nii.gz "$BK/$PFX/cohort/" --quiet --no-clobber 2>/dev/null || true
log

stage inference_start; echo "=== [5/5] unchanged FLAMeS driver: per-fold model, per-case upload, resumable ==="
gcloud storage cp "$BK/flames-ensemble/code/flames_ensemble_driver.py" $W/driver.py --quiet || exit 1
sha256sum $W/driver.py
( while sleep 600; do log; done ) &
python3 $W/driver.py --cases /w/cases.json --folds $FOLDS --bucket $BKT --prefix $PFX --run-id "$NAME"
stage inference_end
log
echo "ALL DONE $(date -u)"
