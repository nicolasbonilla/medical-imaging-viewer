#!/bin/bash
# CALM-MS: FLAMeS on SibBMS HEALTHY CONTROLS -> conformal FALSE-NULL.
# Every lesion candidate FLAMeS produces on a lesion-free brain is a false positive
# by construction, so their scores are a protocol-matched empirical null. Self-logs
# COST + self-deletes (same 5 safety layers as vm-flames.sh).
#
# Pulls ONLY the control FLAIR files via remotezip (HTTP-range, ~1-3 GB) instead of
# the 11 GB archive. Controls are native-space, non-skull-stripped -> HD-BET strips
# them, then FLAMeS. Output: {sub}_prob.nii.gz + {sub}_gt.nii.gz (all-zero GT).
exec > /var/log/sibbms.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
LIMIT=$(meta attributes/case-limit); LIMIT=${LIMIT:-3}
OFFSET=$(meta attributes/case-offset); OFFSET=${OFFSET:-0}
RATE=$(meta attributes/hourly-rate); RATE=${RATE:-0.10}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-n2-standard-8-cpu}
BK="gs://brain-mri-medical-images/calm-sibbms"
START=$(date +%s)

log(){ gsutil -q cp /var/log/sibbms.log "$BK/logs/$NAME.log" 2>/dev/null || true; }
finish(){
  END=$(date +%s); DUR=$((END-START))
  COST=$(python3 -c "print(round($DUR/3600*$RATE,4))" 2>/dev/null || echo NA)
  echo "COST_RECORD,run_id=$NAME,machine=$MACHINE,limit=$LIMIT,seconds=$DUR,rate=$RATE,cost_usd=$COST" | tee /var/log/cost.txt
  gsutil -q cp /var/log/cost.txt "$BK/cost/$NAME.txt" 2>/dev/null || true
  log; gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
}
trap finish EXIT

W=/w; mkdir -p $W/sibbms $W/strip $W/in $W/out $W/cohort; cd $W
[ -d /opt/conda/bin ] && export PATH=/opt/conda/bin:$PATH
apt-get update -qq && apt-get install -y -qq unzip git python3-pip 2>&1 | tail -1
export nnUNet_raw=$W/raw nnUNet_preprocessed=$W/prep nnUNet_results=$W/nnunet_results
mkdir -p $nnUNet_raw $nnUNet_preprocessed $nnUNet_results

echo "=== [1/6] deps: nnU-Net + HD-BET + remotezip ==="
python3 -m pip install -q --upgrade pip 2>&1 | tail -1
python3 -m pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
python3 -m pip install -q nnunetv2 nibabel remotezip 2>&1 | tail -2
python3 -m pip install -q "HD-BET @ git+https://github.com/MIC-DKFZ/HD-BET.git" 2>&1 | tail -3
RUNDEV=$(python3 -c "import torch;print('cuda' if torch.cuda.is_available() else 'cpu')" 2>/dev/null || echo cpu)
echo "compute=$RUNDEV  nnUNetv2_predict=$(which nnUNetv2_predict||echo MISSING)  hd-bet=$(which hd-bet||echo MISSING)"; log

echo "=== [2/6] FLAMeS weights ==="
for att in 1 2 3 4; do
  WZIP=$(curl -s https://zenodo.org/api/records/17955359 | python3 -c "import sys,json;d=json.load(sys.stdin);print([f['links']['self'] for f in d['files'] if f['key'].lower().endswith('.zip')][0])" 2>/dev/null)
  curl -L -o $W/flames.zip "$WZIP" && unzip -q -o $W/flames.zip -d $nnUNet_results/ && ls "$nnUNet_results" | grep -qi Dataset004 && { echo "weights OK"; break; }
  echo "weights attempt $att failed; retry"; sleep 8
done; log

echo "=== [3/6] extract control FLAIR via remotezip (only Output/Norm/*FLAIR) ==="
python3 - "$LIMIT" "$OFFSET" <<'PY'
import sys
from remotezip import RemoteZip
LIMIT=int(sys.argv[1]); OFF=int(sys.argv[2])
url='https://ai.nsu.ru/files/sibbms/sibbms.zip'
with RemoteZip(url) as z:
    fl=sorted(n for n in z.namelist() if n.startswith('Output/Norm/') and 'FLAIR' in n and n.endswith('.nii.gz'))
    fl = fl[OFF:] if LIMIT<=0 else fl[OFF:OFF+LIMIT]
    print("controls to fetch:", len(fl))
    for n in fl: z.extract(n, '/w/sibbms')
PY
log

echo "=== [4/6] HD-BET skull-strip each control ==="
python3 - <<'PY'
import os, glob, subprocess
for fl in sorted(glob.glob('/w/sibbms/Output/Norm/**/*FLAIR*.nii.gz', recursive=True)):
    sub=fl.split('/Norm/')[1].split('/')[0]        # sub-NNN
    out=f'/w/strip/{sub}_FLAIR.nii.gz'
    r=subprocess.run(['hd-bet','-i',fl,'-o',out,'-device','cpu'], capture_output=True, text=True)
    print(sub, 'stripped' if os.path.exists(out) else 'FAILED', r.stderr[-200:] if r.returncode else '')
PY
log

echo "=== [5/6] assemble + FLAMeS predict ==="
for f in /w/strip/*_FLAIR.nii.gz; do sub=$(basename "$f" _FLAIR.nii.gz); cp "$f" "$W/in/${sub}_0000.nii.gz"; done
nnUNetv2_predict -i $W/in -o $W/out -d 004 -c 3d_fullres -tr nnUNetTrainer_8000epochs \
  -device $RUNDEV -f 0 --disable_tta --save_probabilities 2>&1 | tail -15; log

echo "=== [6/6] npz -> prob NIfTI (transpose 2,1,0) + all-zero GT -> upload ==="
python3 - <<'PY'
import os, glob, numpy as np, nibabel as nib
for npz in sorted(glob.glob('/w/out/*.npz')):
    cid=os.path.basename(npz)[:-4]
    les=np.load(npz)["probabilities"][1].astype(np.float32)
    fl=nib.load(f'/w/in/{cid}_0000.nii.gz')
    arr=np.transpose(les,(2,1,0))
    if arr.shape!=fl.shape: print("SHAPE MISMATCH",cid,arr.shape,fl.shape); continue
    nib.save(nib.Nifti1Image(arr, fl.affine, fl.header), f'/w/cohort/{cid}_prob.nii.gz')
    nib.save(nib.Nifti1Image(np.zeros(fl.shape,np.uint8), fl.affine, fl.header), f'/w/cohort/{cid}_gt.nii.gz')  # lesion-free
    print("BUILT", cid)
PY
gsutil -m cp $W/cohort/* "$BK/cohort/" 2>/dev/null || true
touch $W/DONE; gsutil cp $W/DONE "$BK/DONE-$NAME" 2>/dev/null || true; log
echo "ALL DONE $(date -u)"
