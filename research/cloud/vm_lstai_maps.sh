#!/bin/bash
# MSTool research cloud job — LST-AI v1.2.0 probability maps (Job 2).
# Project mstool-research ONLY (free-credit account); bucket gs://mstool-research-data only.
# Same safety layers as vm_flames_ensemble_v2.sh (standard VM, max-run-duration, self-delete trap,
# wall-clock guard, cached inputs with SHA-256, frozen host env with a self-test, per-case upload,
# resumable, manifest + cost record). LAUNCH WITH --disk-gb 100: the image is 11.1 GB compressed.
#  * LST-AI runs from the public Docker image pinned BY DIGEST (bit-identical every run); optional
#    mirror of the image in the bucket (mirror-image=1) only protects against Docker Hub outages.
#  * --probability_map --stripped --device cpu (+ --segment_only by default: skips the region
#    annotation, which does not change the probability maps).
#  * Inputs: MSLesSeg (Figshare 52771814) and open_ms_data cross_sectional/MNI from the same cached
#    mirrors as the FLAMeS runs; SibBMS controls = Job 1 outputs (controls/sibbms/*_FLAIR, *_T1).
# Metadata: datasets="mslesseg openms controls"  case-offset=0  case-limit=0  cases=""(explicit ids)
#           segment-only=1  store-dtype=uint8  lstai-image=<digest ref>  mirror-image=0
#           hourly-rate  machine-desc  max-hours=14
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
DATASETS=$(meta attributes/datasets);    DATASETS=${DATASETS:-mslesseg openms controls}
OFFSET=$(meta attributes/case-offset);   OFFSET=${OFFSET:-0}
LIMIT=$(meta attributes/case-limit);     LIMIT=${LIMIT:-0}
CASES=$(meta attributes/cases)
SEGONLY=$(meta attributes/segment-only); SEGONLY=${SEGONLY:-1}
DTYPE=$(meta attributes/store-dtype);    DTYPE=${DTYPE:-uint8}
IMAGE=$(meta attributes/lstai-image);    IMAGE=${IMAGE:-jqmcginnis/lst-ai@sha256:2b2a0d6454e6efff60a350df3c650ae9584f1926338dec7842f9e71912cc6c85}
MIRROR=$(meta attributes/mirror-image);  MIRROR=${MIRROR:-0}
RATE=$(meta attributes/hourly-rate);     RATE=${RATE:-0.20794}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-n2-standard-4}
MAXH=$(meta attributes/max-hours);       MAXH=${MAXH:-14}
BKT="mstool-research-data"; BK="gs://$BKT"; PFX="lstai"
TAG="lstai:v1.2.0"; MIR="$BK/inputs/lstai_v1.2.0_image.tar"
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

W=/w; mkdir -p $W/cache $W/data $W/run; cd $W
export DEBIAN_FRONTEND=noninteractive HOME=/root
apt-get update -qq && apt-get install -y -qq unzip git python3-pip python3-venv docker.io 2>&1 | tail -1
systemctl start docker 2>/dev/null || service docker start 2>/dev/null || true
# 16 GB swap: safety net for TensorFlow on 16 GB machines (peak memory and swap are recorded per case).
fallocate -l 16G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile || true

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

stage env_start; echo "=== [1/5] host python env (frozen versions; LST-AI itself lives in the image) ==="
python3 -m venv /opt/venv && . /opt/venv/bin/activate
pip install -q --upgrade pip 2>&1 | tail -1
if gcloud storage cp "$BK/env/requirements-lstai-host.lock" $W/requirements.lock --quiet 2>/dev/null; then
  pip install -q -r $W/requirements.lock 2>&1 | tail -2
else
  pip install -q nibabel numpy scipy google-cloud-storage 2>&1 | tail -2
  pip freeze > $W/requirements.lock && gcloud storage cp $W/requirements.lock "$BK/env/requirements-lstai-host.lock" --quiet
fi
python3 -c "import nibabel, numpy, scipy.ndimage; from google.cloud import storage; print('host env ok', nibabel.__version__, numpy.__version__)" || { gcloud storage rm "$BK/env/requirements-lstai-host.lock" --quiet 2>/dev/null; exit 1; }
log

stage image_start; echo "=== [2/5] LST-AI image v1.2.0, pinned by digest ==="
if [ "$MIRROR" != "0" ] && gcloud storage cp "$MIR.id" $W/image.id --quiet 2>/dev/null; then
  gcloud storage cp "$MIR" - --quiet | docker load || exit 1
  [ "$(docker image inspect -f '{{.Id}}' $TAG)" = "$(cat $W/image.id)" ] || { echo "mirrored image id mismatch"; exit 1; }
else
  for att in 1 2 3; do docker pull "$IMAGE" && break; echo "pull attempt $att failed"; sleep 30; done
  docker image inspect "$IMAGE" > /dev/null || exit 1
  docker tag "$IMAGE" $TAG
  if [ "$MIRROR" = "1" ]; then
    docker image inspect -f '{{.Id}}' $TAG > $W/image.id
    docker save $TAG | gcloud storage cp - "$MIR" --quiet && gcloud storage cp $W/image.id "$MIR.id" --quiet
  fi
fi
docker image inspect -f '{{.Id}} {{.RepoDigests}} {{.Size}}' $TAG
# Cheap check BEFORE any work: the entry point must know the flags we rely on.
docker run --rm $TAG --help | grep -q -- "--probability_map" || { echo "image lacks --probability_map"; exit 1; }
df -h / ; log

stage datasets_start; echo "=== [3/5] datasets (cached mirrors + Job 1 controls) ==="
case " $DATASETS " in *" openms "*)
  cache_get open_ms_data_MNI.tar.gz 'git clone -q --filter=blob:none --sparse https://github.com/muschellij2/open_ms_data.git /w/oms && git -C /w/oms sparse-checkout set cross_sectional/MNI && tar -czf /w/cache/open_ms_data_MNI.tar.gz -C /w/oms cross_sectional' || exit 1
  mkdir -p $W/data/open_ms_data && tar -xzf $W/cache/open_ms_data_MNI.tar.gz -C $W/data/open_ms_data && rm -f $W/cache/open_ms_data_MNI.tar.gz ;;
esac
case " $DATASETS " in *" mslesseg "*)
  cache_get mslesseg_52771814.zip 'curl -sL -o /w/cache/mslesseg_52771814.zip https://ndownloader.figshare.com/files/52771814' || exit 1
  mkdir -p $W/data/mslesseg && unzip -q -o $W/cache/mslesseg_52771814.zip -d $W/data/mslesseg && rm -f $W/cache/mslesseg_52771814.zip ;;
esac
case " $DATASETS " in *" controls "*)
  mkdir -p $W/data/controls
  gcloud storage cp "$BK/controls/sibbms/*_FLAIR.nii.gz" "$BK/controls/sibbms/*_T1.nii.gz" $W/data/controls/ --quiet || echo "no Job 1 controls in the bucket yet"
  ls $W/data/controls | wc -l ;;
esac
log

stage code_start; echo "=== [4/5] code (uploaded by the coordinator before launch) ==="
gcloud storage cp "$BK/$PFX/code/lstai_driver.py" "$BK/$PFX/code/job_common.py" $W/ --quiet || exit 1
sha256sum $W/lstai_driver.py $W/job_common.py
log

stage inference_start; echo "=== [5/5] LST-AI per case, per-case upload, resumable ==="
( while sleep 600; do log; done ) &
python3 $W/lstai_driver.py --bucket $BKT --prefix $PFX --run-id "$NAME" --datasets $DATASETS \
  --roots mslesseg=$W/data/mslesseg openms=$W/data/open_ms_data/cross_sectional/MNI controls=$W/data/controls \
  --offset "$OFFSET" --limit "$LIMIT" --cases "$CASES" --image $TAG --image-ref "$IMAGE" \
  --segment-only "$SEGONLY" --dtype "$DTYPE" --work $W/run
stage inference_end
log
echo "ALL DONE $(date -u)"
