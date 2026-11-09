#!/bin/bash
# MSTool research cloud job — mirror public datasets into the research bucket (paper 1 addendum,
# docs/research/paper-1/PREREG-mimics-thickness.md). Project mstool-research ONLY; bucket
# gs://mstool-research-data only. Nothing passes through the owner's computer.
# Same safety layers as the other jobs: STANDARD VM, --max-run-duration (set by launch_vm.py), a trap
# that uploads log/cost/runinfo and deletes the VM on any exit, and an in-VM wall-clock guard.
# No image content is examined: mirror_public.py checks sizes and SHA-1/SHA-256 and reads NIfTI HEADERS only.
# Metadata: lists="wmh2017=mirror/lists/wmh2017.tsv dlbs=mirror/lists/dlbs.tsv"  (dest=bucket path of the list)
#           code-prefix=mirror/code  jobs=6  hourly-rate  machine-desc  max-hours=2
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
LISTS=$(meta attributes/lists)
CODEPFX=$(meta attributes/code-prefix);  CODEPFX=${CODEPFX:-mirror/code}
JOBS=$(meta attributes/jobs);            JOBS=${JOBS:-6}
RATE=$(meta attributes/hourly-rate);     RATE=${RATE:-0.07112}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-e2-standard-2}
MAXH=$(meta attributes/max-hours);       MAXH=${MAXH:-2}
BKT="mstool-research-data"; BK="gs://$BKT"; PFX="mirror"
START=$(date +%s)

log(){ gcloud storage cp /var/log/job.log "$BK/$PFX/logs/$NAME.log" --quiet 2>/dev/null || true; }
stage(){ echo "$1=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> /var/log/stages.txt; }
stage boot
{
  echo "cpu_platform=$(meta cpu-platform)"
  echo "cpu_model=$(lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -1)"
  echo "vcpus=$(nproc)"
  echo "memory_gb=$(free -g | awk '/^Mem:/{print $2}')"
  echo "os=$(. /etc/os-release && echo "$PRETTY_NAME")"
  echo "machine_type=$(meta machine-type | awk -F/ '{print $NF}')"
  echo "zone=$ZONE"
  echo "provisioning=$(meta scheduling/provisioning-model)"
  echo "boot_disk_gb=$(df -BG --output=size / | tail -1 | tr -dc 0-9)"
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
        "cost_usd_estimate_metadata": sys.argv[4], "hardware": kv("/var/log/hw.txt"), "stages_utc": kv("/var/log/stages.txt")}
json.dump(info, open("/var/log/runinfo.json", "w"), indent=1)
PY
  gcloud storage cp /var/log/runinfo.json "$BK/runs/$NAME/runinfo.json" --quiet 2>/dev/null || true
  log
  gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
}
trap finish EXIT
( sleep $((MAXH*3600)); echo "WALL-CLOCK GUARD HIT"; kill -TERM $$ ) &

W=/w; mkdir -p $W/lists $W/m; cd $W
export DEBIAN_FRONTEND=noninteractive HOME=/root
stage env_start
apt-get update -qq && apt-get install -y -qq python3-pip python3-venv 2>&1 | tail -1
python3 -m venv /opt/venv && . /opt/venv/bin/activate
pip install -q --upgrade pip 2>&1 | tail -1
pip install -q nibabel==5.3.0 numpy 2>&1 | tail -1
python3 -c "import nibabel; print('env ok', nibabel.__version__)" || exit 1
gcloud storage cp "$BK/$CODEPFX/mirror_public.py" $W/ --quiet || exit 1
sha256sum $W/mirror_public.py
log

stage mirror_start
( while sleep 300; do log; done ) &
RC=0
for item in $LISTS; do
  DEST=${item%%=*}; LST=${item#*=}
  gcloud storage cp "$BK/$LST" $W/lists/$DEST.tsv --quiet || { RC=1; continue; }
  sha256sum $W/lists/$DEST.tsv
  python3 $W/mirror_public.py --list $W/lists/$DEST.tsv --bucket $BKT --dest $DEST --work $W/m --jobs $JOBS || RC=1
  rm -rf $W/m/$DEST                      # free the disk before the next dataset
  log
done
stage mirror_end
echo "ALL DONE rc=$RC $(date -u)"
exit $RC
