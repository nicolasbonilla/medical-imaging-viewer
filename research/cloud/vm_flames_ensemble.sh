#!/bin/bash
# MSTool research cloud job — FLAMeS 5-fold ensemble probability maps for the public cohorts.
#
# Runs as the startup script of a Spot VM in project mstool-research (free-credit account;
# NEVER any other project). Produces, for every case and every requested fold, the lesion
# probability map as a uint8 NIfTI (round(p*255)) in the input geometry, plus the ground truth,
# and uploads each fold as soon as it finishes, so a Spot preemption loses at most one fold.
# A relaunch skips cases/folds already in the bucket (resumable).
#
# Cost safety (5 layers): Spot provisioning; --max-run-duration with DELETE; this trap deletes
# the VM on any exit; a wall-clock guard; a cost record written to the bucket.
#
# Metadata (all optional):
#   folds="0 1 2 3 4"   case-offset=0   case-limit=0 (0 = all)   datasets="openms mslesseg"
#   hourly-rate=0.08    machine-desc=n2-standard-8   max-hours=15
exec > /var/log/flames.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
FOLDS=$(meta attributes/folds);          FOLDS=${FOLDS:-0 1 2 3 4}
OFFSET=$(meta attributes/case-offset);   OFFSET=${OFFSET:-0}
LIMIT=$(meta attributes/case-limit);     LIMIT=${LIMIT:-0}
DATASETS=$(meta attributes/datasets);    DATASETS=${DATASETS:-openms mslesseg}
RATE=$(meta attributes/hourly-rate);     RATE=${RATE:-0.08}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-n2-standard-8}
MAXH=$(meta attributes/max-hours);       MAXH=${MAXH:-15}
BK="gs://mstool-research-data/flames-ensemble"
START=$(date +%s)

log(){ gcloud storage cp /var/log/flames.log "$BK/logs/$NAME.log" --quiet 2>/dev/null || true; }
finish(){
  END=$(date +%s); DUR=$((END-START))
  COST=$(python3 -c "print(round($DUR/3600*$RATE,4))" 2>/dev/null || echo NA)
  echo "COST_RECORD,run_id=$NAME,machine=$MACHINE,seconds=$DUR,rate_usd_per_h=$RATE,cost_usd=$COST" | tee /var/log/cost.txt
  gcloud storage cp /var/log/cost.txt "$BK/cost/$NAME.txt" --quiet 2>/dev/null || true
  log
  gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
}
trap finish EXIT
# Wall-clock guard: whatever happens, stop after MAXH hours (the VM also has --max-run-duration).
( sleep $((MAXH*3600)); echo "WALL-CLOCK GUARD HIT"; kill -TERM $$ ) &

W=/w; mkdir -p $W/in $W/cohort; cd $W
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq unzip git python3-pip python3-venv 2>&1 | tail -1
python3 -m venv /opt/venv && . /opt/venv/bin/activate
export nnUNet_raw=$W/raw nnUNet_preprocessed=$W/prep nnUNet_results=$W/nnunet_results
mkdir -p $nnUNet_raw $nnUNet_preprocessed $nnUNet_results

echo "=== [1/5] deps (CPU torch + nnU-Net v2) ==="
pip install -q --upgrade pip 2>&1 | tail -1
pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
pip install -q nnunetv2 nibabel 2>&1 | tail -2
python3 -c "import numpy,torch,nibabel;print('deps ok', numpy.__version__, torch.__version__, 'threads', torch.get_num_threads())" || exit 1
log

echo "=== [2/5] FLAMeS weights (Zenodo 17955359) ==="
for att in 1 2 3 4; do
  WZIP=$(curl -s https://zenodo.org/api/records/17955359 | python3 -c "import sys,json;d=json.load(sys.stdin);print([f['links']['self'] for f in d['files'] if f['key'].lower().endswith('.zip')][0])" 2>/dev/null)
  curl -sL -o $W/flames.zip "$WZIP" && unzip -q -o $W/flames.zip -d $nnUNet_results/ && ls "$nnUNet_results" | grep -qi Dataset004 && { echo "weights OK"; rm -f $W/flames.zip; break; }
  echo "weights attempt $att failed; retry"; sleep 10
done
ls -R "$nnUNet_results" | grep -i "fold_" | head; log

echo "=== [3/5] fetch datasets + assemble input (FLAIR as _0000) ==="
python3 - "$DATASETS" "$OFFSET" "$LIMIT" <<'PY'
import os, sys, glob, subprocess, shutil, json
DATASETS = sys.argv[1].split(); OFF = int(sys.argv[2]); LIMIT = int(sys.argv[3])
W = "/w"; IN = f"{W}/in"; gt_map = {}
def add(cid, flair, gt):
    shutil.copy(flair, os.path.join(IN, f"{cid}_0000.nii.gz")); gt_map[cid] = gt
if "openms" in DATASETS:
    d = f"{W}/open_ms_data"
    subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--sparse",
                    "https://github.com/muschellij2/open_ms_data.git", d], check=True)
    subprocess.run(["git", "-C", d, "sparse-checkout", "set", "cross_sectional/MNI"], check=True)
    for pat in sorted(glob.glob(f"{d}/cross_sectional/MNI/patient*")):
        fl = glob.glob(f"{pat}/FLAIR*regtoMNI.nii.gz"); gt = glob.glob(f"{pat}/GOLD_STANDARD*regtoMNI.nii.gz")
        if fl and gt: add("openms_" + os.path.basename(pat), fl[0], gt[0])
if "mslesseg" in DATASETS:
    m = f"{W}/mslesseg"; os.makedirs(m, exist_ok=True)
    subprocess.run(["bash", "-c", f"curl -sL -o {m}/d.zip https://ndownloader.figshare.com/files/52771814 && unzip -q -o {m}/d.zip -d {m} && rm -f {m}/d.zip"], check=True)
    for split in glob.glob(f"{m}/**/train", recursive=True) + glob.glob(f"{m}/**/test", recursive=True):
        for pat in sorted(glob.glob(f"{split}/P*")):
            tps = [x for x in sorted(glob.glob(f"{pat}/T*")) if os.path.isdir(x)]
            if tps:
                for tp in tps:
                    fl = glob.glob(f"{tp}/*FLAIR*.nii.gz"); gt = glob.glob(f"{tp}/*MASK*.nii.gz")
                    if fl and gt: add(f"mslesseg_{os.path.basename(pat)}_{os.path.basename(tp)}", fl[0], gt[0])
            else:
                fl = glob.glob(f"{pat}/*FLAIR*.nii.gz"); gt = glob.glob(f"{pat}/*MASK*.nii.gz")
                if fl and gt: add(f"mslesseg_{os.path.basename(pat)}", fl[0], gt[0])
cases = sorted(gt_map)
cases = cases[OFF:] if LIMIT <= 0 else cases[OFF:OFF + LIMIT]
for f in glob.glob(f"{IN}/*_0000.nii.gz"):
    if os.path.basename(f)[:-len("_0000.nii.gz")] not in cases: os.remove(f)
json.dump({c: gt_map[c] for c in cases}, open(f"{W}/gt_map.json", "w"))
print("ASSEMBLED", len(cases), "cases:", cases[:3], "...", cases[-3:])
PY
log

echo "=== [4/5] ground truth pairs -> bucket ==="
python3 - <<'PY'
import json, numpy as np, nibabel as nib
gt_map = json.load(open("/w/gt_map.json"))
for cid, p in gt_map.items():
    g = nib.load(p)
    nib.save(nib.Nifti1Image((g.get_fdata() > 0).astype(np.uint8), g.affine, g.header), f"/w/cohort/{cid}_gt.nii.gz")
PY
gcloud storage cp $W/cohort/*_gt.nii.gz "$BK/cohort/" --quiet --no-clobber 2>/dev/null || true
log

echo "=== [5/5] FLAMeS per fold (no TTA), resumable, upload per fold ==="
DONE_LIST=$(gcloud storage ls "$BK/cohort/*_prob.nii.gz" 2>/dev/null | xargs -n1 basename 2>/dev/null)
for k in $FOLDS; do
  mkdir -p $W/in_f$k $W/out_f$k
  n=0
  for f in $W/in/*_0000.nii.gz; do
    cid=$(basename "$f" _0000.nii.gz)
    if echo "$DONE_LIST" | grep -qx "${cid}_f${k}_prob.nii.gz"; then continue; fi
    ln -sf "$f" "$W/in_f$k/"; n=$((n+1))
  done
  echo "fold $k: $n cases to run"; [ "$n" -eq 0 ] && continue
  nnUNetv2_predict -i $W/in_f$k -o $W/out_f$k -d 004 -c 3d_fullres -tr nnUNetTrainer_8000epochs \
    -f $k --disable_tta -device cpu --save_probabilities 2>&1 | tail -5
  python3 - "$k" <<'PY'
import os, sys, glob, numpy as np, nibabel as nib
k = sys.argv[1]; W = "/w"; n = 0
for npz in sorted(glob.glob(f"{W}/out_f{k}/*.npz")):
    cid = os.path.basename(npz)[:-4]
    les = np.load(npz)["probabilities"][1].astype(np.float32)   # (z,y,x); channel 1 = lesion
    fl = nib.load(f"{W}/in/{cid}_0000.nii.gz")
    arr = np.transpose(les, (2, 1, 0))                            # -> (x,y,z), validated Aug 2026
    if arr.shape != fl.shape:
        print("SHAPE MISMATCH", cid, arr.shape, fl.shape); continue
    # Stored as uint8 with a NIfTI scale factor computed by nibabel (read back with get_fdata:
    # max error ~0.002 on a 0-1 scale, verified locally 2026-10-17). ~10x smaller than float32.
    img = nib.Nifti1Image(np.clip(arr, 0.0, 1.0), fl.affine, fl.header.copy())
    img.set_data_dtype(np.uint8)
    nib.save(img, f"{W}/cohort/{cid}_f{k}_prob.nii.gz")
    os.remove(npz); n += 1
print("fold", k, "converted", n)
PY
  gcloud storage cp $W/cohort/*_f${k}_prob.nii.gz "$BK/cohort/" --quiet 2>/dev/null || true
  rm -f $W/cohort/*_f${k}_prob.nii.gz $W/out_f$k/*.nii.gz
  log
done
touch $W/DONE; gcloud storage cp $W/DONE "$BK/DONE-$NAME" --quiet 2>/dev/null || true
echo "ALL DONE $(date -u)"
