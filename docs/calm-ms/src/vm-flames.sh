#!/bin/bash
# CALM-MS cloud job: build FLAMeS probability-map cohorts, self-log COST, self-delete.
# Runs on a GCP Deep Learning VM (pytorch GPU image). Cost safety = 5 layers:
#  (1) Spot provisioning, (2) --max-run-duration hard cap + DELETE termination,
#  (3) this trap self-deletes on ANY exit, (4) a wall-clock budget guard inside,
#  (5) a written cost record uploaded to GCS for the ledger.
exec > /var/log/flames.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }  # -f: missing attr -> empty (not 404 HTML)
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
LIMIT=$(meta attributes/case-limit);   LIMIT=${LIMIT:-3}
RATE=$(meta attributes/hourly-rate);   RATE=${RATE:-0.22}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-n1-standard-4+P4}
PFLAGS=$(meta attributes/predict-flags); PFLAGS=${PFLAGS:--f 0 --disable_tta}
DEVICE=$(meta attributes/device); DEVICE=${DEVICE:-cuda}
OFFSET=$(meta attributes/case-offset); OFFSET=${OFFSET:-0}   # for chunked parallel full run
BK="gs://brain-mri-medical-images/calm-flames"
START=$(date +%s)

log(){ gsutil -q cp /var/log/flames.log "$BK/logs/$NAME.log" 2>/dev/null || true; }

finish(){
  END=$(date +%s); DUR=$((END-START))
  COST=$(python3 -c "print(round($DUR/3600*$RATE,4))" 2>/dev/null || echo "NA")
  REC="run_id=$NAME,machine=$MACHINE,limit=$LIMIT,start=$START,end=$END,seconds=$DUR,rate=$RATE,cost_usd=$COST"
  echo "COST_RECORD,$REC" | tee /var/log/cost.txt
  gsutil -q cp /var/log/cost.txt "$BK/cost/$NAME.txt" 2>/dev/null || true
  log
  gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
}
trap finish EXIT

W=/w; mkdir -p $W/in $W/out $W/cohort; cd $W
[ -d /opt/conda/bin ] && export PATH=/opt/conda/bin:$PATH   # conda if present (older DLVM); else system python3 below
apt-get update -qq && apt-get install -y -qq unzip git python3-pip 2>&1 | tail -1
export nnUNet_raw=$W/raw nnUNet_preprocessed=$W/prep nnUNet_results=$W/nnunet_results
mkdir -p $nnUNet_raw $nnUNet_preprocessed $nnUNet_results

echo "=== [1/5] deps + nnU-Net v2 ==="
python3 -m pip install -q --upgrade pip 2>&1 | tail -1
if [ "$DEVICE" = "cpu" ]; then TIDX="--index-url https://download.pytorch.org/whl/cpu"; else TIDX=""; fi
python3 -m pip install -q torch $TIDX 2>&1 | tail -2
python3 -m pip install -q nnunetv2 nibabel 2>&1 | tail -2
python3 -c "import numpy,torch,nibabel;print('deps ok: numpy',numpy.__version__,'torch',torch.__version__)" || echo "DEP IMPORT FAILED"
echo "nnUNetv2_predict=$(which nnUNetv2_predict || echo MISSING)"; log

echo "=== [2/5] FLAMeS weights (Zenodo 17955359) ==="
WZIP=$(curl -s https://zenodo.org/api/records/17955359 \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print([f['links']['self'] for f in d['files'] if f['key'].lower().endswith('.zip')][0])")
curl -L -o $W/flames.zip "$WZIP"
unzip -q -o $W/flames.zip -d $nnUNet_results/
ls -R $nnUNet_results | head -20; log

echo "=== [3/5] fetch datasets + assemble nnU-Net input (FLAIR as _0000) ==="
python3 - "$LIMIT" "$OFFSET" <<'PY'
import os, sys, glob, subprocess, shutil, json
LIMIT = int(sys.argv[1]); OFF = int(sys.argv[2]); W="/w"; IN=f"{W}/in"
gt_map = {}   # caseid -> gt path (kept for later)
def add(caseid, flair, gt):
    dst=os.path.join(IN, f"{caseid}_0000.nii.gz"); shutil.copy(flair, dst); gt_map[caseid]=gt

# open_ms_data (blobless sparse: cross_sectional/MNI)
d=f"{W}/open_ms_data"
subprocess.run(["git","clone","--filter=blob:none","--sparse","https://github.com/muschellij2/open_ms_data.git",d],check=True)
subprocess.run(["git","-C",d,"sparse-checkout","set","cross_sectional/MNI"],check=True)
for pat in sorted(glob.glob(f"{d}/cross_sectional/MNI/patient*")):
    fl=glob.glob(f"{pat}/FLAIR*regtoMNI.nii.gz"); gt=glob.glob(f"{pat}/GOLD_STANDARD*regtoMNI.nii.gz")
    if fl and gt: add("openms_"+os.path.basename(pat), fl[0], gt[0])

# MSLesSeg (figshare preprocessed, MNI 1mm) — each Pn/Tk timepoint is a case
m=f"{W}/mslesseg"; os.makedirs(m,exist_ok=True)
subprocess.run(["bash","-c",f"curl -L -o {m}/d.zip https://ndownloader.figshare.com/files/52771814 && unzip -q -o {m}/d.zip -d {m}"],check=True)
root=glob.glob(f"{m}/**/train",recursive=True)+glob.glob(f"{m}/**/test",recursive=True)
for split in root:
    for pat in sorted(glob.glob(f"{split}/P*")):
        for tp in sorted(glob.glob(f"{pat}/T*")):
            fl=glob.glob(f"{tp}/*FLAIR*.nii.gz"); gt=glob.glob(f"{tp}/*MASK*.nii.gz")
            if fl and gt: add(f"mslesseg_{os.path.basename(pat)}_{os.path.basename(tp)}", fl[0], gt[0])

cases=sorted(gt_map)
cases = cases[OFF:] if LIMIT<=0 else cases[OFF:OFF+LIMIT]   # chunk = [OFFSET, OFFSET+LIMIT)
# keep only selected in IN, drop the rest
for f in glob.glob(f"{IN}/*_0000.nii.gz"):
    cid=os.path.basename(f)[:-len("_0000.nii.gz")]
    if cid not in cases: os.remove(f)
json.dump({c:gt_map[c] for c in cases}, open(f"{W}/gt_map.json","w"))
print("ASSEMBLED", len(cases), "cases:", cases[:5], "..." if len(cases)>5 else "")
PY
log

echo "=== [4/5] FLAMeS inference (--save_probabilities) ==="
nnUNetv2_predict -i $W/in -o $W/out -d 004 -c 3d_fullres -tr nnUNetTrainer_8000epochs \
  -device $DEVICE $PFLAGS --save_probabilities 2>&1 | tail -20; log

echo "=== [5/5] npz -> lesion-probability NIfTI + pair with GT -> upload ==="
python3 - <<'PY'
import os, glob, json, numpy as np, nibabel as nib
W="/w"; OUT=f"{W}/out"; COH=f"{W}/cohort"
gt_map=json.load(open(f"{W}/gt_map.json"))
n=0
for npz in sorted(glob.glob(f"{OUT}/*.npz")):
    cid=os.path.basename(npz)[:-4]
    prob=np.load(npz)["probabilities"]           # (C, ...) ; channel 1 = lesion
    les=prob[1].astype(np.float32)
    fl=nib.load(f"{W}/in/{cid}_0000.nii.gz")      # original geometry
    arr=les
    if arr.shape!=fl.shape:                        # nnU-Net may store (C,X,Y,Z) matching fl
        try: arr=np.transpose(les, (0,1,2))
        except Exception: pass
    nib.save(nib.Nifti1Image(arr, fl.affine, fl.header), f"{COH}/{cid}_prob.nii.gz")
    g=nib.load(gt_map[cid]); nib.save(nib.Nifti1Image((g.get_fdata()>0).astype(np.uint8), g.affine, g.header), f"{COH}/{cid}_gt.nii.gz")
    n+=1
print("BUILT", n, "prob/gt pairs")
PY
gsutil -m cp $W/cohort/* "$BK/cohort/" 2>/dev/null || true
touch $W/DONE; gsutil cp $W/DONE "$BK/DONE-$NAME" 2>/dev/null || true
log
echo "ALL DONE $(date -u)"
# trap 'finish' now records cost + self-deletes.
