#!/bin/bash
# MSTool research cloud job — paper 1 addendum: the frozen final evaluation (PREREG-mimics-thickness.md section 11
# steps 6-8; amendment 1). Project mstool-research ONLY; bucket gs://mstool-research-data only. Spot VM, self-deleting
# (same safety layers as every research job). The analysis Python runs with NO cloud credentials (offline variables),
# imports the app's region/DIS code read-only, and greedy lives in its own venv.
# Metadata: evalcode=mimics/evalcode/<commit>.tar.gz  commit=<git sha>  workers=8  hourly-rate machine-desc max-hours
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
EVALCODE=$(meta attributes/evalcode); COMMIT=$(meta attributes/commit)
WORKERS=$(meta attributes/workers);      WORKERS=${WORKERS:-8}
RATE=$(meta attributes/hourly-rate);     RATE=${RATE:-0.18}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-c2d-standard-8 spot}
MAXH=$(meta attributes/max-hours);       MAXH=${MAXH:-8}
BKT="mstool-research-data"; BK="gs://$BKT"; PFX="mimics"
START=$(date +%s)
log(){ gcloud storage cp /var/log/job.log "$BK/$PFX/logs/$NAME.log" --quiet 2>/dev/null || true; }
stage(){ echo "$1=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> /var/log/stages.txt; }
stage boot
{
  echo "cpu_platform=$(meta cpu-platform)"; echo "vcpus=$(nproc)"; echo "memory_gb=$(free -g | awk '/^Mem:/{print $2}')"
  echo "machine_type=$(meta machine-type | awk -F/ '{print $NF}')"; echo "zone=$ZONE"
  echo "provisioning=$(meta scheduling/provisioning-model)"; echo "boot_disk_gb=$(df -BG --output=size / | tail -1 | tr -dc 0-9)"
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
json.dump({"run_id": sys.argv[1], "wall_seconds": int(sys.argv[2]), "rate_usd_per_h_metadata": sys.argv[3],
           "cost_usd_estimate_metadata": sys.argv[4], "hardware": kv("/var/log/hw.txt"), "stages_utc": kv("/var/log/stages.txt")},
          open("/var/log/runinfo.json", "w"), indent=1)
PY
  gcloud storage cp /var/log/runinfo.json "$BK/runs/$NAME/runinfo.json" --quiet 2>/dev/null || true
  log
  gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
}
trap finish EXIT
( sleep $((MAXH*3600)); echo "WALL-CLOCK GUARD HIT"; kill -TERM $$ ) &

export DEBIAN_FRONTEND=noninteractive HOME=/root
apt-get update -qq && apt-get install -y -qq python3-pip python3-venv 2>&1 | tail -1
stage env_start
python3 -m venv /opt/eval && /opt/eval/bin/pip install -q --upgrade pip && \
/opt/eval/bin/pip install -q numpy==1.26.4 scipy==1.13.1 nibabel==5.3.0 fastapi==0.115.0 starlette==0.38.6 anyio==4.11.0 \
  pydantic==2.9.0 pydantic-settings==2.5.0 python-dotenv==1.0.1 python-json-logger==2.0.7 || exit 1
python3 -m venv /opt/greedy && /opt/greedy/bin/pip install -q --upgrade pip && /opt/greedy/bin/pip install -q picsl_greedy==1.4.0.3 || exit 1
/opt/greedy/bin/python -c "from picsl_greedy import Greedy3D; print('greedy ok')" || exit 1
log

stage data_start
W=/w; D=/w/d; mkdir -p $W/repo $D/mimics/flames $D/mimics/lstai $D/mimics/toolbench $D/mimics/inputs $D/pf/flames $D/pf/lstai \
  $D/pf/toolbench $D/manifests $D/wmh $D/atlas $W/work $W/results
gcloud storage cp "$BK/$EVALCODE" $W/code.tar.gz --quiet && tar -xzf $W/code.tar.gz -C $W/repo || exit 1
gcloud storage cp "$BK/$PFX/plans/variant.json" $W/work/variant.json --quiet || exit 1
G="gcloud storage cp --quiet"
$G "$BK/$PFX/flames/cohort/*" $D/mimics/flames/ && $G "$BK/$PFX/lstai/cohort/*_lstai_prob.nii.gz" $D/mimics/lstai/ \
  && $G "$BK/$PFX/toolbench/cohort/*_seg.nii.gz" $D/mimics/toolbench/ && $G "$BK/$PFX/toolbench/manifests/*.json" $D/manifests/ \
  && $G "$BK/$PFX/inputs/*_FLAIR.nii.gz" "$BK/$PFX/inputs/*_brainmask.nii.gz" $D/mimics/inputs/ || exit 1
for p in mslesseg_ openms_ sub-; do
  $G "$BK/flames-ensemble/cohort/${p}*" $D/pf/flames/ || exit 1
  $G "$BK/lstai/cohort/${p}*_lstai_prob.nii.gz" $D/pf/lstai/ || exit 1
done
for t in mindglide wmhsynthseg; do for p in mslesseg_ openms_; do $G "$BK/toolbench/cohort/${p}*_${t}_seg.nii.gz" $D/pf/toolbench/ || exit 1; done; done
$G "$BK/toolbench/cohort/sub-*_seg.nii.gz" $D/pf/toolbench/ || exit 1
gcloud storage cp -r --quiet "$BK/wmh2017/test" "$BK/wmh2017/training" "$BK/wmh2017/additional_annotations" $D/wmh/ || exit 1
$G "$BK/inputs/lstai_atlas/sub-mni152_space-mni_t1.nii.gz" $D/atlas/ || exit 1
du -sh $D/*; log

stage eval_start
cd $W/repo
export GOOGLE_APPLICATION_CREDENTIALS=/nonexistent/credentials.json GOOGLE_CLOUD_PROJECT=mstool-offline-tests \
       GREEDY_PYTHON=/opt/greedy/bin/python MIMICS_CODE_COMMIT="$COMMIT"
ARGS="--pf $D/pf --mimics $D/mimics --wmh $D/wmh --manifests $D/manifests --atlas-t1 $D/atlas/sub-mni152_space-mni_t1.nii.gz --work $W/work"
( while sleep 600; do log; done ) &
echo "=== GR: registration before any outcome ==="
CLOUDSDK_CONFIG=/nonexistent /opt/eval/bin/python research/paper_1/mimics/evaluate_mimics.py register $ARGS --threads $(nproc) \
  | tee $W/results/gr_registration.txt || exit 1
gcloud storage cp $W/work/registration.json $W/results/gr_registration.txt "$BK/$PFX/results/$NAME/" --quiet; log
echo "=== G3: structural check ==="
CLOUDSDK_CONFIG=/nonexistent /opt/eval/bin/python research/paper_1/mimics/evaluate_mimics.py check $ARGS > $W/results/g3_structural_check.txt
tail -1 $W/results/g3_structural_check.txt; log
echo "=== evaluation, once ==="
CLOUDSDK_CONFIG=/nonexistent /opt/eval/bin/python research/paper_1/mimics/evaluate_mimics.py run $ARGS --workers $WORKERS \
  --results $W/results || exit 1
echo "=== G2: independent recount ==="
CLOUDSDK_CONFIG=/nonexistent /opt/eval/bin/python research/paper_1/mimics/check_counts_mimics.py --records $W/work/records.json \
  --pf $D/pf --mimics $D/mimics --out $W/results/independent_check.json
cp $W/work/registration.json $W/results/registration.json
gcloud storage cp -r --quiet $W/results/* "$BK/$PFX/results/$NAME/"
echo "done $COMMIT" | gcloud storage cp - "$BK/$PFX/results/$NAME/DONE" --quiet
stage eval_end
echo "ALL DONE $(date -u)"
