#!/bin/bash
# MSTool research cloud job — SibBMS healthy controls, complete and reusable (Job 1).
# Project mstool-research ONLY (free-credit account); bucket gs://mstool-research-data only.
# Same safety layers as vm_flames_ensemble_v2.sh:
#  * STANDARD (non-Spot) VM; --max-run-duration caps the bill; the trap deletes the VM on any exit;
#    a wall-clock guard stops runaway jobs.
#  * Inputs are mirrored ONCE into gs://.../inputs with SHA-256 (FLAMeS weights, HD-BET weights,
#    each SibBMS control FLAIR/T1w under inputs/sibbms_norm/), so reruns never depend on Zenodo or
#    ai.nsu.ru. The 11 GB SibBMS zip is NEVER downloaded: only the 200 needed members (~1.4 GB) are
#    read by HTTP range requests (remotezip), the first time.
#  * Python packages: the FLAMeS lock (env/requirements.lock) + HD-BET at a pinned commit + remotezip,
#    frozen to env/requirements-controls.lock and reused; a self-test aborts before any work.
#  * Step 1 (sibbms_controls_prep.py): HD-BET (CPU) strips the FLAIR, the same mask strips the T1w
#    (on the FLAIR grid); FLAIR, T1, brain mask and an all-zero lesion mask go to the bucket per case.
#  * Step 2 (flames_ensemble_driver.py, unchanged): FLAMeS folds 0-4 run SEPARATELY (one model per
#    fold, no TTA) -> flames-ensemble/cohort/{case}_f{k}_prob.nii.gz, uploaded per case, resumable.
# Metadata: case-offset=0  case-limit=0  cases=""(explicit ids, wins)  folds="0 1 2 3 4"
#           hdbet-tta=1  hourly-rate  machine-desc  max-hours=12
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
FOLDS=$(meta attributes/folds);          FOLDS=${FOLDS:-0 1 2 3 4}
OFFSET=$(meta attributes/case-offset);   OFFSET=${OFFSET:-0}
LIMIT=$(meta attributes/case-limit);     LIMIT=${LIMIT:-0}
CASES=$(meta attributes/cases)
TTA=$(meta attributes/hdbet-tta);        TTA=${TTA:-1}
RATE=$(meta attributes/hourly-rate);     RATE=${RATE:-0.17583}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-n2d-standard-4}
MAXH=$(meta attributes/max-hours);       MAXH=${MAXH:-12}
BKT="mstool-research-data"; BK="gs://$BKT"; PFX="controls"; FPFX="flames-ensemble"
HDBET_COMMIT="678e44d546a84de0f2a7fc245f176b82b7d912fd"
HDBET_ZIP_MD5="f97a36f89f8eb3071ff05c6f9ac66b56"      # Zenodo record 14445620, release_v1.5.0.zip
START=$(date +%s)

log(){ gcloud storage cp /var/log/job.log "$BK/$PFX/logs/$NAME.log" --quiet 2>/dev/null || true; }
# Compute ledger: hardware facts + a UTC timestamp per stage, uploaded as runs/<name>/runinfo.json.
stage(){ echo "$1=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> /var/log/stages.txt; }
stage boot
hwinfo(){
  {
    echo "cpu_platform=$(meta cpu-platform)"
    echo "cpu_model=$(lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -1)"
    echo "vcpus=$(nproc)"
    echo "threads_per_core=$(lscpu | sed -n 's/^Thread(s) per core:[[:space:]]*//p' | head -1)"
    echo "memory_gb=$(free -g | awk '/^Mem:/{print $2}')"
    echo "gpu=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | tr '\n' ';' || true)"
    echo "os=$(. /etc/os-release && echo "$PRETTY_NAME")"
    echo "kernel=$(uname -r)"
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
    for line in open(p):
        if "=" in line:
            k, v = line.rstrip("\n").split("=", 1); out[k] = v
    return out
info = {"run_id": sys.argv[1], "wall_seconds": int(sys.argv[2]), "rate_usd_per_h_metadata": sys.argv[3],
        "cost_usd_estimate_metadata": sys.argv[4], "hardware": kv("/var/log/hw.txt"), "stages_utc": kv("/var/log/stages.txt")}
json.dump(info, open("/var/log/runinfo.json", "w"), indent=1)
PY
  gcloud storage cp /var/log/runinfo.json "$BK/runs/$NAME/runinfo.json" --quiet 2>/dev/null || true
  log
  gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
}
trap finish EXIT
( sleep $((MAXH*3600)); echo "WALL-CLOCK GUARD HIT"; kill -TERM $$ ) &

W=/w; mkdir -p $W/cache $W/strip $W/gt $W/sibbms; cd $W
export DEBIAN_FRONTEND=noninteractive HOME=/root          # HD-BET keeps its weights in ~/hd-bet_params
apt-get update -qq && apt-get install -y -qq unzip git python3-pip python3-venv 2>&1 | tail -1
# 8 GB swap: a safety net against an out-of-memory kill on 16 GB machines (usage is recorded per case).
fallocate -l 8G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile || true

# cache_get NAME SOURCE_COMMAND : fetch $W/cache/NAME from gs://.../inputs, or build it with the
# source command, then mirror it (with its SHA-256) into the bucket for every future run.
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

stage env_start; echo "=== [1/5] python env (frozen versions) ==="
python3 -m venv /opt/venv && . /opt/venv/bin/activate
pip install -q --upgrade pip 2>&1 | tail -1
if gcloud storage cp "$BK/env/requirements-controls.lock" $W/requirements.lock --quiet 2>/dev/null; then
  pip install -q -r $W/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
else
  # Same versions as the FLAMeS runs on the 145 MS cases, then HD-BET (pinned commit) + remotezip.
  if gcloud storage cp "$BK/env/requirements.lock" $W/flames.lock --quiet 2>/dev/null; then
    pip install -q -r $W/flames.lock --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
  else
    # torch AND torchvision from the SAME (CPU) index (a PyPI torchvision broke two pilots).
    pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
    pip install -q nnunetv2 nibabel google-cloud-storage 2>&1 | tail -2
  fi
  pip install -q --extra-index-url https://download.pytorch.org/whl/cpu remotezip scipy \
    "HD_BET @ git+https://github.com/MIC-DKFZ/HD-BET.git@$HDBET_COMMIT" 2>&1 | tail -2
  pip freeze > $W/requirements.lock && gcloud storage cp $W/requirements.lock "$BK/env/requirements-controls.lock" --quiet
fi
python3 -c "import torch,torchvision,nnunetv2,nibabel,scipy.ndimage,remotezip; from google.cloud import storage; from torchvision.ops import nms; from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor; from HD_BET.hd_bet_prediction import get_hdbet_predictor, hdbet_predict; nms(torch.zeros((1,4)), torch.zeros(1), 0.5); print('env ok', torch.__version__, torchvision.__version__)" || { gcloud storage rm "$BK/env/requirements-controls.lock" --quiet 2>/dev/null; exit 1; }
pip freeze | grep -i -E "hd.bet|nnunetv2|^torch" ; log

stage weights_start; echo "=== [2/5] FLAMeS + HD-BET weights (cached mirrors of Zenodo 17955359 / 14445620) ==="
cache_get flames_weights.zip 'U=$(curl -s https://zenodo.org/api/records/17955359 | python3 -c "import sys,json;d=json.load(sys.stdin);print([f[\"links\"][\"self\"] for f in d[\"files\"] if f[\"key\"].lower().endswith(\".zip\")][0])"); curl -sL -o /w/cache/flames_weights.zip "$U"' || exit 1
export nnUNet_raw=$W/raw nnUNet_preprocessed=$W/prep nnUNet_results=$W/nnunet_results
mkdir -p $nnUNet_raw $nnUNet_preprocessed $nnUNet_results
unzip -q -o $W/cache/flames_weights.zip -d $nnUNet_results/ && rm -f $W/cache/flames_weights.zip
cache_get hdbet_release_v1.5.0.zip 'curl -sL -o /w/cache/hdbet_release_v1.5.0.zip "https://zenodo.org/records/14445620/files/release_v1.5.0.zip?download=1"' || exit 1
echo "$HDBET_ZIP_MD5  $W/cache/hdbet_release_v1.5.0.zip" | md5sum -c - || { echo "HD-BET weights checksum mismatch"; exit 1; }
HDP=$HOME/hd-bet_params/release_2.0.0; mkdir -p $HDP
unzip -q -o $W/cache/hdbet_release_v1.5.0.zip -d $HDP && rm -f $W/cache/hdbet_release_v1.5.0.zip
[ -f $HDP/fold_all/checkpoint_final.pth ] || { echo "HD-BET weights not where HD-BET expects them"; ls -R $HDP | head; exit 1; }
log

stage code_start; echo "=== [3/5] code (uploaded by the coordinator before launch) ==="
gcloud storage cp "$BK/$PFX/code/sibbms_controls_prep.py" "$BK/$PFX/code/job_common.py" $W/ --quiet || exit 1
gcloud storage cp "$BK/$FPFX/code/flames_ensemble_driver.py" $W/driver.py --quiet || exit 1
sha256sum $W/sibbms_controls_prep.py $W/job_common.py $W/driver.py
log

stage inference_start; echo "=== [4/5] controls: fetch + HD-BET + T1 on the FLAIR grid, per-case upload ==="
( while sleep 600; do log; done ) &
python3 $W/sibbms_controls_prep.py --bucket $BKT --run-id "$NAME" --offset "$OFFSET" --limit "$LIMIT" \
  --cases "$CASES" --tta "$TTA" --work $W --cases-json $W/cases.json --also-hash $W/driver.py || exit 1
stage prep_end
log

echo "=== [5/5] FLAMeS: one model per fold, no TTA, per-case upload, resumable ==="
python3 $W/driver.py --cases $W/cases.json --folds $FOLDS --bucket $BKT --prefix $FPFX --run-id "$NAME"
stage inference_end
log
echo "ALL DONE $(date -u)"
