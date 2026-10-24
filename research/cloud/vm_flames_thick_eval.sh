#!/bin/bash
# MSTool research cloud job — FLAMeS-thick evaluation (docs/research/flames-thick/PROTOCOL.md §7).
# Derived from vm_flames_ensemble_v2.sh (same frozen CPU environment, input mirrors, HD-BET cache,
# per-case upload, wall-clock guard, self-deleting STANDARD VM, ledger records). Differences:
#  * the models are the fine-tuned FLAMeS-thick / FLAMeS-FT exports (gs://.../flames-thick/train/<run>/
#    model.tar.gz, SHA-256 checked), loaded through nnU-Net's external-trainer lookup;
#  * the cases are exactly the pre-registered 211-scan evaluation set (research/flames_thick/eval_cases.py);
#  * outputs go to flames-thick/eval/ as {case}_{TAG}_f0_prob.nii.gz (fold 0, no TTA, uint8 like FLAMeS maps).
# Project mstool-research ONLY. Nothing here trains; nothing here touches another project.
# Metadata: models="ftA=flames-thick/train/flames-thick-a/model.tar.gz ftB=flames-thick/train/flames-thick-b/model.tar.gz"
#           case-ids (pilot subset)  allow-count (logged deviation only)  hourly-rate  machine-desc  max-hours
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
MODELS=$(meta attributes/models)
CASE_IDS=$(meta attributes/case-ids)
ALLOW=$(meta attributes/allow-count)
CHUNK=$(meta attributes/chunk)           # "i/n": this VM takes every n-th scan of the sorted set, from the i-th
RATE=$(meta attributes/hourly-rate);     RATE=${RATE:-0.17583}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-n2d-standard-4}
MAXH=$(meta attributes/max-hours);       MAXH=${MAXH:-12}
DATASETS="openms mslesseg ms3seg muslim pedims"
BKT="mstool-research-data"; BK="gs://$BKT"; PFX="flames-thick/eval"; CODE="$BK/flames-thick/code"
START=$(date +%s)

log(){ gcloud storage cp /var/log/job.log "$BK/$PFX/logs/$NAME.log" --quiet 2>/dev/null || true; }
stage(){ echo "$1=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> /var/log/stages.txt; }
stage boot
hwinfo(){
  {
    echo "cpu_platform=$(meta cpu-platform)"
    echo "cpu_model=$(lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -1)"
    echo "vcpus=$(nproc)"
    echo "memory_gb=$(free -g | awk '/^Mem:/{print $2}')"
    echo "os=$(. /etc/os-release && echo "$PRETTY_NAME")"
    echo "machine_type=$(meta machine-type | awk -F/ '{print $NF}')"
    echo "zone=$ZONE"
    echo "provisioning=$(meta scheduling/provisioning-model)"
  } > /var/log/hw.txt
}
hwinfo
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
    try:
        for line in open(p):
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1); out[k] = v
    except OSError:
        pass
    return out
info = {"run_id": sys.argv[1], "wall_seconds": int(sys.argv[2]), "rate_usd_per_h_metadata": sys.argv[3],
        "cost_usd_estimate_metadata": sys.argv[4], "hardware": kv("/var/log/hw.txt"), "stages_utc": kv("/var/log/stages.txt"),
        "code_sha256": kv("/var/log/code_sha.txt"), "models_sha256": kv("/var/log/models_sha.txt")}
json.dump(info, open("/var/log/runinfo.json", "w"), indent=1)
PY
  gcloud storage cp /var/log/runinfo.json "$BK/runs/$NAME/runinfo.json" --quiet 2>/dev/null || true
  log
  gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
}
trap finish EXIT
( sleep $((MAXH*3600)); echo "WALL-CLOCK GUARD HIT"; kill -TERM $$ ) &
[ -n "$MODELS" ] || { echo "metadata 'models' is required"; exit 1; }

W=/w; mkdir -p $W/cache $W/data $W/code $W/models; cd $W
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq unzip git python3-pip python3-venv 2>&1 | tail -1

cache_get(){            # identical to v2: mirrored input with SHA-256 sidecar, built from source only once
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

stage env_start; echo "=== [1/5] python env (the frozen lock of the v2 FLAMeS jobs) + code ==="
python3 -m venv /opt/venv && . /opt/venv/bin/activate
pip install -q --upgrade pip 2>&1 | tail -1
gcloud storage cp "$BK/env/requirements.lock" $W/requirements.lock --quiet || { echo "frozen lock missing"; exit 1; }
pip install -q -r $W/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
for f in flames_ensemble_driver.py cohorts_extra.py extra_cohorts_stage.py flames_thick.tar.gz; do
  gcloud storage cp "$CODE/$f" "$W/code/$f" --quiet || exit 1
done
tar -xzf $W/code/flames_thick.tar.gz -C $W/code
(cd $W/code && sha256sum flames_ensemble_driver.py cohorts_extra.py extra_cohorts_stage.py flames_thick.tar.gz | awk '{print $2"="$1}') > /var/log/code_sha.txt
export PYTHONPATH=$W/code nnUNet_extTrainer=$W/code/flames_thick/nnunet_ext
pip freeze > $W/constraints.txt
pip install -q -c $W/constraints.txt "hd-bet==2.0.1" --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
python3 -c "import torch,nnunetv2; from torchvision.ops import nms; nms(torch.zeros((1,4)), torch.zeros(1), 0.5); \
from nnunetv2.utilities.find_objects import recursive_find_trainer_class_by_name as f; \
print('env ok', torch.__version__, f('nnUNetTrainerFLAMeSThick').__name__, f('nnUNetTrainerFLAMeSFT').__name__)" || exit 1
log

stage weights_start; echo "=== [2/5] fine-tuned models (SHA-256 checked) ==="
export nnUNet_raw=$W/raw nnUNet_preprocessed=$W/prep nnUNet_results=$W/nnunet_results
mkdir -p $nnUNet_raw $nnUNet_preprocessed $nnUNet_results
MODEL_ARGS=""
for m in $MODELS; do
  TAG=${m%%=*}; OBJ=${m#*=}
  gcloud storage cp "$BK/$OBJ" "$W/models/$TAG.tar.gz" --quiet || exit 1
  WANT=$(gcloud storage cat "$BK/$OBJ.sha256" | awk '{print $1}')
  GOT=$(sha256sum "$W/models/$TAG.tar.gz" | awk '{print $1}')
  [ -n "$WANT" ] && [ "$WANT" = "$GOT" ] || { echo "model $TAG: sha256 $GOT != $WANT"; exit 1; }
  echo "$TAG=$GOT" >> /var/log/models_sha.txt
  mkdir -p "$W/models/$TAG" && tar -xzf "$W/models/$TAG.tar.gz" -C "$W/models/$TAG"
  DIR=$(dirname "$(ls -d $W/models/$TAG/*/*__nnUNetPlans__3d_fullres/fold_0 | head -1)")
  [ -f "$DIR/fold_0/checkpoint_final.pth" ] || { echo "model $TAG: no checkpoint"; exit 1; }
  MODEL_ARGS="$MODEL_ARGS --model $TAG=$DIR"
done
log

stage datasets_start; echo "=== [3/5] datasets (the cached mirrors the reference maps were made from) ==="
cache_get open_ms_data_MNI.tar.gz 'git clone -q --filter=blob:none --sparse https://github.com/muschellij2/open_ms_data.git /w/oms && git -C /w/oms sparse-checkout set cross_sectional/MNI && tar -czf /w/cache/open_ms_data_MNI.tar.gz -C /w/oms cross_sectional' || exit 1
mkdir -p $W/data/open_ms_data && tar -xzf $W/cache/open_ms_data_MNI.tar.gz -C $W/data/open_ms_data && rm -f $W/cache/open_ms_data_MNI.tar.gz
cache_get mslesseg_52771814.zip 'curl -sL -o /w/cache/mslesseg_52771814.zip https://ndownloader.figshare.com/files/52771814' || exit 1
mkdir -p $W/data/mslesseg && unzip -q -o $W/cache/mslesseg_52771814.zip -d $W/data/mslesseg && rm -f $W/cache/mslesseg_52771814.zip
cache_get extra_cohorts_raw_v1.tar.gz "python3 $W/code/extra_cohorts_stage.py build-raw --out $W/extra_raw --cohorts ms3seg muslim pedims && tar -czf $W/cache/extra_cohorts_raw_v1.tar.gz -C $W extra_raw" || exit 1
[ -d $W/extra_raw ] || tar -xzf $W/cache/extra_cohorts_raw_v1.tar.gz -C $W
rm -f $W/cache/extra_cohorts_raw_v1.tar.gz
log

stage cases_start; echo "=== [4/5] the pre-registered evaluation set + ground truth ==="
python3 - "$BK" "$CASE_IDS" "$ALLOW" "$CHUNK" <<'PY'
import glob, json, os, subprocess, sys
import nibabel as nib, numpy as np
sys.path.insert(0, "/w/code")
from flames_thick import eval_cases as ec
BK, CASE_IDS, ALLOW, CHUNK = sys.argv[1], sys.argv[2].split(), sys.argv[3], sys.argv[4]
cases = {}
extra = {c: v for c, v in json.load(open("/w/extra_raw/cases_extra.json")).items()}
for c, v in extra.items():
    cases[c] = {"flair": None, "gt": os.path.join("/w/extra_raw", v["gt"])}
for pat in sorted(glob.glob("/w/data/open_ms_data/cross_sectional/MNI/patient*")):
    fl = glob.glob(f"{pat}/FLAIR*regtoMNI.nii.gz"); gt = glob.glob(f"{pat}/GOLD_STANDARD*regtoMNI.nii.gz")
    if fl and gt: cases["openms_" + os.path.basename(pat)] = {"flair": fl[0], "gt": gt[0]}
for split in glob.glob("/w/data/mslesseg/**/train", recursive=True) + glob.glob("/w/data/mslesseg/**/test", recursive=True):
    for pat in sorted(glob.glob(f"{split}/P*")):
        tps = [x for x in sorted(glob.glob(f"{pat}/T*")) if os.path.isdir(x)]
        for d, cid in ([(tp, f"mslesseg_{os.path.basename(pat)}_{os.path.basename(tp)}") for tp in tps]
                       or [(pat, f"mslesseg_{os.path.basename(pat)}")]):
            fl = glob.glob(f"{d}/*FLAIR*.nii.gz"); gt = glob.glob(f"{d}/*MASK*.nii.gz")
            if fl and gt: cases[cid] = {"flair": fl[0], "gt": gt[0]}
json.dump(cases, open("/w/cases_all.json", "w"), indent=1)
args = ["--cases", "/w/cases_all.json", "--out", "/w/cases_sel.json"]
if CASE_IDS: args += ["--ids", *CASE_IDS]
if ALLOW: args += ["--allow-count", ALLOW]
ec.main(args)
sel = json.load(open("/w/cases_sel.json"))
if CHUNK:
    i, n = (int(x) for x in CHUNK.split("/"))
    keep = sorted(sel)[i - 1::n]
    sel = {c: sel[c] for c in keep}
    print("CHUNK", CHUNK, len(sel))
need = [c for c in sel if c in extra]
if need:     # brains cached by the reference runs are reused; HD-BET only runs for a missing one
    subprocess.run([sys.executable, "/w/code/extra_cohorts_stage.py", "strip", "--raw", "/w/extra_raw", "--cases", *need,
                    "--bucket-prefix", f"{BK}/inputs/extra_stripped", "--out", "/w/extra_brain",
                    "--result", "/w/extra_selected.json"], check=True)
    got = json.load(open("/w/extra_selected.json"))
    for c in need:
        sel[c]["flair"] = got[c]["flair"] if c in got else None
missing = [c for c in sel if not sel[c]["flair"]]
if missing:
    sys.exit(f"no FLAIR for {missing}: a scan of the evaluation set cannot be dropped silently")
os.makedirs("/w/gt", exist_ok=True)
for c, v in sel.items():
    g = nib.load(v["gt"])
    nib.save(nib.Nifti1Image((g.get_fdata() > 0).astype(np.uint8), g.affine, g.header), f"/w/gt/{c}_gt.nii.gz")
json.dump(sel, open("/w/cases.json", "w"), indent=1)
print("CASES", len(sel))
PY
[ -s /w/cases.json ] || exit 1
gcloud storage cp $W/gt/*_gt.nii.gz "$BK/$PFX/cohort/" --quiet --no-clobber 2>/dev/null || true
log

stage inference_start; echo "=== [5/5] driver: fold 0 of each fine-tuned model, per-case upload, resumable ==="
( while sleep 600; do log; done ) &
python3 $W/code/flames_ensemble_driver.py --cases /w/cases.json --folds 0 --bucket $BKT --prefix $PFX \
    --run-id "$NAME" $MODEL_ARGS
stage inference_end
log
echo "ALL DONE $(date -u)"
