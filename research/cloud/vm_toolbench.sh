#!/bin/bash
# MSTool research cloud job — Paper F tool benchmark: CPU MS-lesion segmenters on the FLAMeS cohorts.
# Project mstool-research ONLY (free-credit account); bucket gs://mstool-research-data only.
# Same safety layers as vm_lstai_maps.sh: standard VM, --max-run-duration, self-delete trap, wall-clock
# guard, cached inputs, frozen host env with a self-test, per-case upload, resumable, manifest + cost
# record + runinfo for the compute ledger. DISK: --disk-gb 150 when a FreeSurfer tool runs (FreeSurfer
# 8.2.0 image = 14.3 GB compressed, several times that unpacked, + 16 GB swap); --disk-gb 100 for MindGlide
# alone (4.7 GB compressed). MEMORY: WMH-SynthSeg needs ~32 GB -> n2d-highmem-4 (RUNBOOK.md section 2).
#  * Tools run from public containers pinned BY DIGEST, with --network=none (nothing leaves the VM).
#  * Inputs are the exact FLAIR files the FLAMeS runs used; the driver checks every SHA-256 against
#    research/paper_f/flames_inputs.json and refuses anything else (no skull stripping is redone here).
#  * FreeSurfer tools need the OWNER's FreeSurfer licence file in the bucket (RUNBOOK.md section 0);
#    it is mounted read-only into the container and never printed, logged or copied elsewhere.
# Metadata: tools="wmhsynthseg mindglide samseg"  datasets="mslesseg openms ms3seg muslim pedims"
#           case-offset=0  case-limit=0  cases=""(explicit ids)  timeout-min=45  wmh-crop=0
#           mindglide-image=<ref@digest>  fs-image=<ref@digest>  hourly-rate  machine-desc  max-hours=12
#           max-minutes (optional, overrides max-hours for the in-VM guard)
#           input-variant=flames (primary arm: the FLAMeS skull-stripped FLAIR) | raw (secondary arm,
#           PROTOCOL.md 7.6: FLAIR before skull stripping, MS3SEG/Muslim/PediMS only; outputs {tool}-raw)
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
TOOLS=$(meta attributes/tools);          TOOLS=${TOOLS:-wmhsynthseg mindglide samseg}
VARIANT=$(meta attributes/input-variant); VARIANT=${VARIANT:-flames}   # flames (primary) | raw (PROTOCOL 7.6)
DATASETS=$(meta attributes/datasets)
if [ "$VARIANT" = "raw" ]; then DATASETS=${DATASETS:-ms3seg muslim pedims}; else DATASETS=${DATASETS:-mslesseg openms ms3seg muslim pedims}; fi
OFFSET=$(meta attributes/case-offset);   OFFSET=${OFFSET:-0}
LIMIT=$(meta attributes/case-limit);     LIMIT=${LIMIT:-0}
CASES=$(meta attributes/cases)
TMIN=$(meta attributes/timeout-min);     TMIN=${TMIN:-45}
MGIMG=$(meta attributes/mindglide-image); MGIMG=${MGIMG:-ghcr.io/ms-pinpoint/mindglide@sha256:14e88f61d6cba18322d03774b168682e255383387aaab55e6a5aa33a2dbdd971}
FSIMG=$(meta attributes/fs-image);       FSIMG=${FSIMG:-freesurfer/freesurfer@sha256:5648104ca75a24f6ee5a8786146f99b405c2bda1da12bff723a15056da8ddf6b}
WMHCROP=$(meta attributes/wmh-crop);     WMHCROP=${WMHCROP:-0}
RATE=$(meta attributes/hourly-rate);     RATE=${RATE:-0.18268}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-n2d-standard-4}
MAXH=$(meta attributes/max-hours);       MAXH=${MAXH:-12}
MAXM=$(meta attributes/max-minutes)      # optional finer guard (pilot: 105 min under a 2 h hard stop)
GUARD_S=$((MAXH*3600)); [ -n "$MAXM" ] && GUARD_S=$((MAXM*60))
BKT="mstool-research-data"; BK="gs://$BKT"; PFX="toolbench"
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
    echo "boot_disk_gb=$(df -BG --output=size / | tail -1 | tr -dc 0-9)"
  } > /var/log/hw.txt
}
hwinfo
finish(){
  stage end
  rm -rf /w/fs_license                                   # the licence never outlives the job
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
( sleep $GUARD_S; echo "WALL-CLOCK GUARD HIT"; docker ps -q | xargs -r docker kill; kill -TERM $$ ) &

W=/w; mkdir -p $W/cache $W/data $W/run $W/extra_brain; cd $W
export DEBIAN_FRONTEND=noninteractive HOME=/root
apt-get update -qq && apt-get install -y -qq unzip git python3-pip python3-venv docker.io 2>&1 | tail -1
systemctl start docker 2>/dev/null || service docker start 2>/dev/null || true
# 16 GB swap: safety net on 16 GB machines (peak memory and swap are recorded per case-tool).
fallocate -l 16G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile || true
NEED_FS=0; NEED_MG=0
for t in $TOOLS; do case $t in wmhsynthseg|samseg) NEED_FS=1;; mindglide) NEED_MG=1;; *) echo "unknown tool $t"; exit 1;; esac; done

stage env_start; echo "=== [1/6] host python env (same frozen lock as the LST-AI job; tools live in the images) ==="
python3 -m venv /opt/venv && . /opt/venv/bin/activate
pip install -q --upgrade pip 2>&1 | tail -1
if gcloud storage cp "$BK/env/requirements-lstai-host.lock" $W/requirements.lock --quiet 2>/dev/null; then
  pip install -q -r $W/requirements.lock 2>&1 | tail -2
else
  pip install -q nibabel numpy scipy google-cloud-storage 2>&1 | tail -2
  pip freeze > $W/requirements.lock && gcloud storage cp $W/requirements.lock "$BK/env/requirements-lstai-host.lock" --quiet
fi
python3 -c "import nibabel, numpy, scipy.ndimage; from google.cloud import storage; print('host env ok', nibabel.__version__, numpy.__version__)" || exit 1
log

stage image_start; echo "=== [2/6] containers, pinned by digest ==="
drop(){  # remove tool(s) from TOOLS, loudly; the other tools go on
  for x in "$@"; do TOOLS=$(echo " $TOOLS " | sed "s/ $x / /g"); echo "TOOL DROPPED: $x ($REASON)"; done
  TOOLS=$(echo $TOOLS); [ -n "$TOOLS" ] || { echo "no tool left"; exit 1; }
}
pull(){  # pull REF and tag it LOCAL; three attempts (registries rate-limit anonymous pulls)
  for att in 1 2 3; do docker pull "$1" && break; echo "pull attempt $att failed"; sleep 30; done
  docker image inspect "$1" > /dev/null || return 1
  docker tag "$1" "$2"
}
if [ "$NEED_MG" = "1" ]; then
  pull "$MGIMG" mindglide:bench || { REASON="image pull failed"; drop mindglide; }
fi
if [ "$NEED_FS" = "1" ]; then
  pull "$FSIMG" freesurfer:bench || { REASON="image pull failed"; drop wmhsynthseg samseg; NEED_FS=0; }   # 8.2.0, 14.3 GB
fi
docker images; df -h / ; log

stage license_start; echo "=== [3/6] FreeSurfer licence (owner's file; never printed) ==="
LIC=""
if [ "$NEED_FS" = "1" ]; then
  set +x
  mkdir -p $W/fs_license && chmod 700 $W/fs_license
  if gcloud storage cp "$BK/secrets/freesurfer/license.txt" $W/fs_license/license.txt --quiet 2>/dev/null \
     && [ "$(wc -w < $W/fs_license/license.txt)" -ge 3 ]; then
    chmod 600 $W/fs_license/license.txt
    echo "licence present ($(wc -l < $W/fs_license/license.txt) lines)"
    LIC=$W/fs_license/license.txt
  else
    rm -rf $W/fs_license
    REASON="no usable FreeSurfer licence at $BK/secrets/freesurfer/license.txt (RUNBOOK.md 0.1)"
    drop wmhsynthseg samseg; NEED_FS=0
  fi
  set -x
fi
# WMH-SynthSeg model: not inside the FreeSurfer image. Fetched once from MGH into the bucket mirror
# (with its SHA-256); every later run must match that checksum and the published size.
WMH=""
case " $TOOLS " in *" wmhsynthseg "*)
  M=WMH-SynthSeg_v10_231110.pth; mkdir -p $W/models
  if gcloud storage cp "$BK/inputs/$M" "$BK/inputs/$M.sha256" $W/models/ --quiet 2>/dev/null; then
    [ "$(sha256sum $W/models/$M | awk '{print $1}')" = "$(cat $W/models/$M.sha256)" ] || { echo "WMH model checksum mismatch"; exit 1; }
  else
    curl -sfL -o $W/models/$M "https://ftp.nmr.mgh.harvard.edu/pub/dist/lcnpublic/dist/WMH-SynthSeg/$M" || exit 1
    [ "$(stat -c %s $W/models/$M)" = "790531383" ] || { echo "WMH model has the wrong size"; exit 1; }
    sha256sum $W/models/$M | awk '{print $1}' > $W/models/$M.sha256
    gcloud storage cp $W/models/$M $W/models/$M.sha256 "$BK/inputs/" --quiet
  fi
  WMH=$W/models/$M ;;
esac
# Cheap self-checks BEFORE any work: each tool exists and knows the flags we rely on (a failing tool is
# dropped and logged; the WMH-SynthSeg check runs with its model mounted, as in the real runs).
case " $TOOLS " in *" mindglide "*)
  docker run --rm --network=none mindglide:bench --help 2>&1 | grep -q -- "--device" \
    || { REASON="--help lacks --device"; drop mindglide; } ;;
esac
if [ "$NEED_FS" = "1" ]; then
  FSHOME=$(docker image inspect -f '{{range .Config.Env}}{{println .}}{{end}}' freesurfer:bench | sed -n 's/^FREESURFER_HOME=//p')
  echo "FREESURFER_HOME=$FSHOME"
  FSRUN(){ docker run --rm --network=none ${WMH:+-v $WMH:$FSHOME/models/WMH-SynthSeg_v10_231110.pth:ro} \
             --entrypoint /bin/bash freesurfer:bench -c "source \$FREESURFER_HOME/SetUpFreeSurfer.sh >/dev/null 2>&1; $1" 2>&1; }
  case " $TOOLS " in *" wmhsynthseg "*)
    FSRUN "mri_WMHsynthseg --help" | grep -q -- "--save_lesion_probabilities" \
      || { REASON="mri_WMHsynthseg --help lacks --save_lesion_probabilities"; drop wmhsynthseg; } ;;
  esac
  case " $TOOLS " in *" samseg "*)
    FSRUN "run_samseg --help" | grep -q -- "--lesion-mask-pattern" \
      || { REASON="run_samseg --help lacks --lesion-mask-pattern"; drop samseg; }
    FSRUN "fspython -c 'import tensorflow'" > /dev/null \
      || echo "WARNING: tensorflow not importable in fspython; SAMSEG --lesion may fail (recorded per case)" ;;
  esac
fi
echo "TOOLS AFTER CHECKS: $TOOLS"
log

stage datasets_start; echo "=== [4/6] datasets (cached mirrors only: the bytes FLAMeS used) ==="
cache_get(){  # cached inputs only — this job never rebuilds an input
  gcloud storage cp "$BK/inputs/$1" "$W/cache/$1" --quiet && [ -s "$W/cache/$1" ]
}
case " $DATASETS " in *" openms "*)
  cache_get open_ms_data_MNI.tar.gz || exit 1
  mkdir -p $W/data/open_ms_data && tar -xzf $W/cache/open_ms_data_MNI.tar.gz -C $W/data/open_ms_data && rm -f $W/cache/open_ms_data_MNI.tar.gz ;;
esac
case " $DATASETS " in *" mslesseg "*)
  cache_get mslesseg_52771814.zip || exit 1
  mkdir -p $W/data/mslesseg && unzip -q -o $W/cache/mslesseg_52771814.zip -d $W/data/mslesseg && rm -f $W/cache/mslesseg_52771814.zip ;;
esac
EXTRA=""; for d in ms3seg muslim pedims; do case " $DATASETS " in *" $d "*) EXTRA="$EXTRA $d";; esac; done
if [ -n "$EXTRA" ]; then
  cache_get extra_cohorts_raw_v1.tar.gz || exit 1
  tar -xzf $W/cache/extra_cohorts_raw_v1.tar.gz -C $W && rm -f $W/cache/extra_cohorts_raw_v1.tar.gz
  if [ "$VARIANT" = "flames" ]; then
    # The HD-BET brains the FLAMeS runs used (MS3SEG, Muslim); PediMS ships skull-stripped.
    gcloud storage cp "$BK/inputs/extra_stripped/*_flair_brain.nii.gz" $W/extra_brain/ --quiet || exit 1
    ls $W/extra_brain | wc -l
  fi
fi
# Raw-input arm: MS3SEG/Muslim raw FLAIRs are in the tarball above (the files HD-BET was run on).
# PediMS raw = raw/defaced_FLAIR.nii.gz from Figshare, fetched once (MD5 checked) and cached as a tarball.
if [ "$VARIANT" = "raw" ]; then case " $DATASETS " in *" pedims "*)
  P=pedims_raw_flair_v1.tar.gz
  if gcloud storage cp "$BK/inputs/$P" "$BK/inputs/$P.sha256" $W/cache/ --quiet 2>/dev/null; then
    [ "$(sha256sum $W/cache/$P | awk '{print $1}')" = "$(cat $W/cache/$P.sha256)" ] || { echo "PediMS raw tarball checksum mismatch"; exit 1; }
  else
    gcloud storage cp "$BK/$PFX/code/cohorts_extra.py" "$BK/$PFX/code/extra_cohorts_stage.py" $W/ --quiet \
      && python3 $W/extra_cohorts_stage.py pedims-raw --out $W/pedims_raw_build \
      && tar -czf $W/cache/$P -C $W/pedims_raw_build . \
      && sha256sum $W/cache/$P | awk '{print $1}' > $W/cache/$P.sha256 \
      && gcloud storage cp $W/cache/$P $W/cache/$P.sha256 "$BK/inputs/" --quiet \
      || echo "WARNING: PediMS raw FLAIR unavailable; PediMS is reported as an input problem"
  fi
  mkdir -p $W/pedims_raw && [ -s $W/cache/$P ] && tar -xzf $W/cache/$P -C $W/pedims_raw && rm -f $W/cache/$P
  ls $W/pedims_raw/pedims_raw 2>/dev/null | wc -l ;;
esac; fi
log

stage code_start; echo "=== [5/6] code (uploaded by the coordinator before launch) ==="
gcloud storage cp "$BK/$PFX/code/toolbench_driver.py" "$BK/$PFX/code/job_common.py" "$BK/$PFX/code/flames_inputs.json" $W/ --quiet || exit 1
sha256sum $W/toolbench_driver.py $W/job_common.py $W/flames_inputs.json
log

stage inference_start; echo "=== [6/6] tools per case (tool-major), per-case upload, resumable ==="
( while sleep 600; do log; done ) &
python3 $W/toolbench_driver.py --bucket $BKT --prefix $PFX --run-id "$NAME" --tools $TOOLS --datasets $DATASETS \
  --roots mslesseg=$W/data/mslesseg openms=$W/data/open_ms_data/cross_sectional/MNI extra_raw=$W/extra_raw extra_brain=$W/extra_brain pedims_raw=$W/pedims_raw \
  --input-variant "$VARIANT" \
  --expected $W/flames_inputs.json --offset "$OFFSET" --limit "$LIMIT" --cases "$CASES" --timeout-min "$TMIN" \
  --images mindglide=mindglide:bench fs=freesurfer:bench --image-refs mindglide="$MGIMG" fs="$FSIMG" \
  ${LIC:+--fs-license "$LIC"} ${WMH:+--wmh-model "$WMH"} --wmh-crop "$WMHCROP" --work $W/run
stage inference_end
log
echo "ALL DONE $(date -u)"
