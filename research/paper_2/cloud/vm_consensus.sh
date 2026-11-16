#!/bin/bash
# MSTool research cloud job — paper 2, design D5: two-tool consensus on paper 1's frozen masks (PREREG §3).
# Project mstool-research ONLY; bucket gs://mstool-research-data only. Spot VM, self-deleting, wall-clock guard.
# Same environment, inputs and atlas transforms as paper 1's evaluation; the analysis Python has NO cloud credentials.
# Metadata: p1code=<paper-1 evalcode tar> p2code=<paper-2 code tar> regsrc=<gs prefix of the transforms>
#           p1results=<gs prefix of paper 1's results> commit=<paper-2 sha> workers=8 hourly-rate max-hours
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
P1CODE=$(meta attributes/p1code); P2CODE=$(meta attributes/p2code); REGSRC=$(meta attributes/regsrc)
P1RES=$(meta attributes/p1results); COMMIT=$(meta attributes/commit)
WORKERS=$(meta attributes/workers); WORKERS=${WORKERS:-8}
RATE=$(meta attributes/hourly-rate); RATE=${RATE:-0.18}
MAXH=$(meta attributes/max-hours);   MAXH=${MAXH:-4}
BK="gs://mstool-research-data"; OUT="$BK/paper2/consensus/$NAME"
START=$(date +%s)
log(){ gcloud storage cp /var/log/job.log "$BK/paper2/logs/$NAME.log" --quiet 2>/dev/null || true; }
finish(){
  END=$(date +%s); DUR=$((END-START))
  COST=$(python3 -c "print(round($DUR/3600*$RATE,4))" 2>/dev/null || echo NA)
  echo "COST_RECORD,run_id=$NAME,seconds=$DUR,rate_usd_per_h=$RATE,cost_usd_compute_estimate=$COST" | tee /var/log/cost.txt
  gcloud storage cp /var/log/cost.txt "$BK/paper2/cost/$NAME.txt" --quiet 2>/dev/null || true
  log
  gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
}
trap finish EXIT
( sleep $((MAXH*3600)); echo "WALL-CLOCK GUARD HIT"; kill -TERM $$ ) &

export DEBIAN_FRONTEND=noninteractive HOME=/root
apt-get update -qq && apt-get install -y -qq python3-pip python3-venv 2>&1 | tail -1
# paper 1's evaluation environment, pin for pin (research/cloud/vm_mimics_eval.sh at the evaluated commit)
python3 -m venv /opt/eval && /opt/eval/bin/pip install -q --upgrade pip && \
/opt/eval/bin/pip install -q numpy==1.26.4 scipy==1.13.1 nibabel==5.3.0 fastapi==0.115.0 starlette==0.38.6 anyio==4.11.0 \
  pydantic==2.9.0 pydantic-settings==2.5.0 python-dotenv==1.0.1 python-json-logger==2.0.7 \
  Pillow==10.4.0 pydicom==2.4.4 nilearn==0.14.1 scikit-image==0.24.0 scikit-learn==1.7.2 || exit 1
python3 -m venv /opt/greedy && /opt/greedy/bin/pip install -q --upgrade pip && /opt/greedy/bin/pip install -q picsl_greedy==1.4.0.3 || exit 1
log

W=/w; D=/w/d; mkdir -p $W/repo $D/mimics/flames $D/mimics/lstai $D/mimics/toolbench $D/mimics/inputs $D/pf/flames $D/pf/lstai \
  $D/pf/toolbench $D/manifests $D/wmh $D/atlas $W/work/registration $W/p1 $W/out
G="gcloud storage cp --quiet"
$G "$BK/$P1CODE" $W/p1code.tar.gz && tar -xzf $W/p1code.tar.gz -C $W/repo || exit 1
$G "$BK/$P2CODE" $W/p2code.tar.gz && tar -xzf $W/p2code.tar.gz -C $W/repo || exit 1
$G "$BK/mimics/plans/variant.json" $W/work/variant.json || exit 1
$G "$REGSRC/*.mat" $W/work/registration/ || exit 1
$G "$P1RES/per_unit.csv" "$P1RES/lesions.csv" "$P1RES/registration.json" $W/p1/ || exit 1
$G "$BK/mimics/flames/cohort/*" $D/mimics/flames/ && $G "$BK/mimics/lstai/cohort/*_lstai_prob.nii.gz" $D/mimics/lstai/ \
  && $G "$BK/mimics/toolbench/cohort/*_seg.nii.gz" $D/mimics/toolbench/ && $G "$BK/mimics/toolbench/manifests/*.json" $D/manifests/ \
  && $G "$BK/mimics/inputs/*_FLAIR.nii.gz" "$BK/mimics/inputs/*_brainmask.nii.gz" $D/mimics/inputs/ || exit 1
for p in mslesseg_ openms_ sub-; do
  $G "$BK/flames-ensemble/cohort/${p}*" $D/pf/flames/ || exit 1
  $G "$BK/lstai/cohort/${p}*_lstai_prob.nii.gz" $D/pf/lstai/ || exit 1
done
for t in mindglide wmhsynthseg; do for p in mslesseg_ openms_; do $G "$BK/toolbench/cohort/${p}*_${t}_seg.nii.gz" $D/pf/toolbench/ || exit 1; done; done
$G "$BK/toolbench/cohort/sub-*_seg.nii.gz" $D/pf/toolbench/ || exit 1
$G "$BK/inputs/lstai_atlas/sub-mni152_space-mni_t1.nii.gz" $D/atlas/ || exit 1
du -sh $D/*; log

cd $W/repo
export GOOGLE_APPLICATION_CREDENTIALS=/nonexistent/credentials.json GOOGLE_CLOUD_PROJECT=mstool-offline-tests \
       GREEDY_PYTHON=/opt/greedy/bin/python
ARGS="--pf $D/pf --mimics $D/mimics --wmh $D/wmh --manifests $D/manifests --atlas-t1 $D/atlas/sub-mni152_space-mni_t1.nii.gz --work $W/work"
( while sleep 600; do log; done ) &
echo "=== paper 1's registration step with its kept transforms (no new affine; GR recomputed) ==="
CLOUDSDK_CONFIG=/nonexistent /opt/eval/bin/python research/paper_1/mimics/evaluate_mimics.py register $ARGS --threads $(nproc) \
  | tee $W/out/gr_registration.txt || exit 1
# the transforms must be the reference run's (paper 1's reproduction run): every SHA-256 equal to its registration.json
/opt/eval/bin/python - $W/p1/registration.json $W/work/registration.json <<'PY' | tee $W/out/transform_check.txt || exit 1
import json, sys
a = json.load(open(sys.argv[1]))["records"]; b = json.load(open(sys.argv[2]))["records"]
bad = [k for k in a if a[k]["mat_sha256"] != b.get(k, {}).get("mat_sha256") or a[k]["pass"] != b.get(k, {}).get("pass")]
print(f"transforms compared {len(a)}, equal {len(a) - len(bad)}")
sys.exit(1 if bad or len(a) != len(b) else 0)
PY
echo "=== D5 consensus (gate GD5 first) ==="
CLOUDSDK_CONFIG=/nonexistent /opt/eval/bin/python research/paper_2/consensus_eval.py $ARGS --p1-results $W/p1 --out $W/out \
  --workers $WORKERS || exit 1
gcloud storage cp -r --quiet $W/out/* "$OUT/"
echo "done $COMMIT" | gcloud storage cp - "$OUT/DONE" --quiet
echo "ALL DONE $(date -u)"
