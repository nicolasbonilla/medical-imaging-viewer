#!/bin/bash
# MSTool research cloud job — paper 1 addendum 2 (docs/research/paper-1/PREREG-addendum-2026-11-age-faithful-
# deterministic.md): HD-BET and the six tools on the Dallas 21-49 sample (unchanged mimics_vm.py), SynthSeg anatomy,
# deterministic registration runs. Project mstool-research ONLY; bucket gs://mstool-research-data only.
# Safety layers as every research job: Spot VM with --max-run-duration and termination action DELETE (launch_vm.py),
# a trap that uploads log/cost/runinfo and deletes the VM on any exit, an in-VM wall-clock guard, containers pinned by
# digest with --network=none, every input SHA-256-checked, every output uploaded at once, resumable.
# Order: [A] mimics_vm.py prep  ->  [B] x_jobs.py pre (regtest, SynthSeg)  ->  [C] mimics_vm.py tool steps
#        ->  [D] x_jobs.py post (SynthSeg of B2, registration run, overlays).
# Metadata: code=mimics/xcode/<commit>  plan=mimics/plans/<vm>.json  needs="hdbet flames lstai mindglide fs cdata greedy"
#           swap-gb  hourly-rate  machine-desc  max-hours
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
CODE=$(meta attributes/code)
PLAN=$(meta attributes/plan)
NEEDS=$(meta attributes/needs)
SWAPGB=$(meta attributes/swap-gb);       SWAPGB=${SWAPGB:-8}
RATE=$(meta attributes/hourly-rate);     RATE=${RATE:-0.09003}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-c2d-standard-4 spot}
MAXH=$(meta attributes/max-hours);       MAXH=${MAXH:-12}
BKT="mstool-research-data"; BK="gs://$BKT"; PFX="mimics"
LSTAI_REF="jqmcginnis/lst-ai@sha256:2b2a0d6454e6efff60a350df3c650ae9584f1926338dec7842f9e71912cc6c85"
MG_REF="ghcr.io/ms-pinpoint/mindglide@sha256:14e88f61d6cba18322d03774b168682e255383387aaab55e6a5aa33a2dbdd971"
FS_REF="freesurfer/freesurfer@sha256:5648104ca75a24f6ee5a8786146f99b405c2bda1da12bff723a15056da8ddf6b"
HDBET_ZIP_MD5="f97a36f89f8eb3071ff05c6f9ac66b56"
START=$(date +%s)
need(){ case " $NEEDS " in *" $1 "*) return 0;; *) return 1;; esac; }

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
  echo "boot_disk_gb=$(df -BG --output=size / | tail -1 | tr -dc 0-9)"
} > /var/log/hw.txt
finish(){
  stage end
  rm -rf /w/fs_license
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
( sleep $((MAXH*3600)); echo "WALL-CLOCK GUARD HIT"; docker ps -q | xargs -r docker kill; kill -TERM $$ ) &

W=/w; mkdir -p $W/cache $W/data $W/code $W/models $W/atlas; cd $W
export DEBIAN_FRONTEND=noninteractive HOME=/root
apt-get update -qq && apt-get install -y -qq unzip git python3-pip python3-venv docker.io 2>&1 | tail -1
systemctl start docker 2>/dev/null || service docker start 2>/dev/null || true
fallocate -l ${SWAPGB}G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile || true

stage env_start; echo "=== [1/7] python envs ==="
python3 -m venv /opt/venv && . /opt/venv/bin/activate
pip install -q --upgrade pip 2>&1 | tail -1
if need hdbet || need flames; then
  gcloud storage cp "$BK/env/requirements-controls.lock" $W/requirements.lock --quiet || exit 1
  pip install -q -r $W/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
  python3 -c "import torch,nnunetv2,nibabel,scipy.ndimage,matplotlib; from google.cloud import storage; from HD_BET.hd_bet_prediction import get_hdbet_predictor; from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor; print('env ok', torch.__version__)" || exit 1
else
  gcloud storage cp "$BK/env/requirements-lstai-host.lock" $W/requirements.lock --quiet || exit 1
  pip install -q -r $W/requirements.lock 2>&1 | tail -2
  python3 -c "import nibabel, numpy, scipy.ndimage; from google.cloud import storage; print('host env ok', nibabel.__version__)" || exit 1
fi
if need greedy; then
  # The registration environment: greedy with every dependency pinned, and the fixed image built with the evaluation
  # VM's pins (numpy 1.26.4, scipy 1.13.1, nibabel 5.3.0), so both registration runs and the evaluation share them.
  python3 -m venv /opt/greedy && /opt/greedy/bin/pip install -q --upgrade pip && \
    /opt/greedy/bin/pip install -q picsl_greedy==1.4.0.3 numpy==1.26.4 SimpleITK==2.5.3 typing_extensions==4.12.2 || exit 1
  /opt/greedy/bin/python -c "from picsl_greedy import Greedy3D; print('greedy ok')" || exit 1
  python3 -m venv /opt/evalreg && /opt/evalreg/bin/pip install -q --upgrade pip && \
    /opt/evalreg/bin/pip install -q numpy==1.26.4 scipy==1.13.1 nibabel==5.3.0 || exit 1
  gcloud storage cp "$BK/inputs/lstai_atlas/sub-mni152_space-mni_t1.nii.gz" $W/atlas/ --quiet || exit 1
fi
log

stage code_start; echo "=== [2/7] code and plan (committed code, uploaded by launch_x.py) ==="
gcloud storage cp "$BK/$CODE/*" $W/code/ --quiet || exit 1
gcloud storage cp "$BK/$PLAN" $W/plan.json --quiet || exit 1
sha256sum $W/code/* $W/plan.json
python3 - <<'PY' || exit 1
import json
p = json.load(open("/w/plan.json"))
json.dump({"prep": p.get("prep", []), "steps": []}, open("/w/plan_a.json", "w"), indent=1)
json.dump({"prep": [], "steps": p.get("steps", []), "idle_wait_h": p.get("idle_wait_h", 30)}, open("/w/plan_b.json", "w"), indent=1)
PY
log

stage weights_start; echo "=== [3/7] weights and images (only what the plan needs) ==="
if need hdbet; then
  gcloud storage cp "$BK/inputs/hdbet_release_v1.5.0.zip" $W/cache/ --quiet || exit 1
  echo "$HDBET_ZIP_MD5  $W/cache/hdbet_release_v1.5.0.zip" | md5sum -c - || { echo "HD-BET weights checksum mismatch"; exit 1; }
  HDP=$HOME/hd-bet_params/release_2.0.0; mkdir -p $HDP
  unzip -q -o $W/cache/hdbet_release_v1.5.0.zip -d $HDP && rm -f $W/cache/hdbet_release_v1.5.0.zip
  [ -f $HDP/fold_all/checkpoint_final.pth ] || { echo "HD-BET weights not where HD-BET expects them"; exit 1; }
fi
if need flames; then
  export nnUNet_raw=$W/raw nnUNet_preprocessed=$W/prep_nn nnUNet_results=$W/nnunet_results
  mkdir -p $nnUNet_raw $nnUNet_preprocessed $nnUNet_results
  gcloud storage cp "$BK/inputs/flames_weights.zip" "$BK/inputs/flames_weights.zip.sha256" $W/cache/ --quiet || exit 1
  [ "$(sha256sum $W/cache/flames_weights.zip | awk '{print $1}')" = "$(awk '{print $1}' $W/cache/flames_weights.zip.sha256)" ] || { echo "FLAMeS weights checksum mismatch"; exit 1; }
  unzip -q -o $W/cache/flames_weights.zip -d $nnUNet_results/ && rm -f $W/cache/flames_weights.zip
fi
pull(){ for att in 1 2 3; do docker pull "$1" && break; echo "pull attempt $att failed"; sleep 30; done
        docker image inspect "$1" > /dev/null && docker tag "$1" "$2"; }
if need lstai; then pull "$LSTAI_REF" lstai:v1.2.0 || exit 1; docker run --rm lstai:v1.2.0 --help | grep -q -- "--probability_map" || exit 1; fi
if need mindglide; then pull "$MG_REF" mindglide:bench || exit 1; fi
LIC=""; WMH=""
if need fs; then
  pull "$FS_REF" freesurfer:bench || exit 1
  set +x
  mkdir -p $W/fs_license && chmod 700 $W/fs_license
  gcloud storage cp "$BK/secrets/freesurfer/license.txt" $W/fs_license/license.txt --quiet 2>/dev/null \
    && [ "$(wc -w < $W/fs_license/license.txt)" -ge 3 ] && chmod 600 $W/fs_license/license.txt && LIC=$W/fs_license/license.txt
  set -x
  [ -n "$LIC" ] || { echo "no usable FreeSurfer licence"; exit 1; }
  M=WMH-SynthSeg_v10_231110.pth
  gcloud storage cp "$BK/inputs/$M" "$BK/inputs/$M.sha256" $W/models/ --quiet || exit 1
  [ "$(sha256sum $W/models/$M | awk '{print $1}')" = "$(cat $W/models/$M.sha256)" ] || { echo "WMH model checksum mismatch"; exit 1; }
  WMH=$W/models/$M
fi
if need cdata; then
  gcloud storage cp "$BK/inputs/mslesseg_52771814.zip" "$BK/inputs/open_ms_data_MNI.tar.gz" $W/cache/ --quiet || exit 1
  mkdir -p $W/data/mslesseg $W/data/open_ms_data
  unzip -q -o $W/cache/mslesseg_52771814.zip -d $W/data/mslesseg && tar -xzf $W/cache/open_ms_data_MNI.tar.gz -C $W/data/open_ms_data
  rm -f $W/cache/mslesseg_52771814.zip $W/cache/open_ms_data_MNI.tar.gz
fi
docker images; df -h /; log
( while sleep 600; do log; done ) &
VMARGS="--bucket $BKT --work $W --code $W/code --sets $W/code/analysis_sets.json --data $W/data \
  --flames-inputs $W/code/flames_inputs.json --controls-inputs $W/code/controls_inputs.json --lstai-image-ref $LSTAI_REF \
  --mg-image-ref $MG_REF --fs-image-ref $FS_REF ${LIC:+--fs-license $LIC} ${WMH:+--wmh-model $WMH}"
XARGS="--plan $W/plan.json --bucket $BKT --run-id $NAME --work $W --code $W/code --data $W/data \
  --flames-inputs $W/code/flames_inputs.json --controls-inputs $W/code/controls_inputs.json --fs-image-ref $FS_REF \
  ${LIC:+--fs-license $LIC} --threads $(nproc) --msmask $W/code/sub-mni152_space-mni_msmask.nii.gz \
  --atlas-t1 $W/atlas/sub-mni152_space-mni_t1.nii.gz"

stage prep_start; echo "=== [4/7] HD-BET preparation (mimics_vm.py, resumable) ==="
python3 $W/code/mimics_vm.py --plan $W/plan_a.json --run-id "$NAME" $VMARGS; log
stage xpre_start; echo "=== [5/7] x_jobs pre: registration pre-check, SynthSeg ==="
python3 $W/code/x_jobs.py --phase pre $XARGS; log
stage tools_start; echo "=== [6/7] tools (mimics_vm.py, resumable; no outcome printed) ==="
python3 $W/code/mimics_vm.py --plan $W/plan_b.json --run-id "$NAME-t" $VMARGS; log
stage xpost_start; echo "=== [7/7] x_jobs post: SynthSeg of B2, registration run, overlays ==="
python3 $W/code/x_jobs.py --phase post $XARGS
RC=$?
stage inference_end
echo "=== done rc=$RC ==="
log
echo "ALL DONE $(date -u)"
