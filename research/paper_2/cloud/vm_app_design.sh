#!/bin/bash
# MSTool research cloud job — paper 2, E5 state C (PREREG §12, 2026-11-21): the experts' masks through paper 1's run-3
# pipeline with the application's code at e559929. Project mstool-research ONLY; bucket gs://mstool-research-data only.
# Spot VM, self-deleting, wall-clock guard. The analysis Python runs with NO cloud credentials.
# Metadata: p1code=<paper-1 run-3 evalcode tar> appcode=<e559929 backend tar> p2code=<paper-2 code tar>
#           regsrc=<gs prefix of run 3's transforms> p1results=<gs prefix of run 3's results> commit=<paper-2 sha>
#           workers=8 hourly-rate max-hours
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
P1CODE=$(meta attributes/p1code); APPCODE=$(meta attributes/appcode); P2CODE=$(meta attributes/p2code)
REGSRC=$(meta attributes/regsrc); P1RES=$(meta attributes/p1results); COMMIT=$(meta attributes/commit)
WORKERS=$(meta attributes/workers); WORKERS=${WORKERS:-8}
RATE=$(meta attributes/hourly-rate); RATE=${RATE:-0.18}
MAXH=$(meta attributes/max-hours);   MAXH=${MAXH:-3}
BK="gs://mstool-research-data"; OUT="$BK/paper2/e5/$NAME"
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
# paper 1's evaluation environment, pin for pin (research/cloud/vm_mimics_eval_x.sh, run 3)
python3 -m venv /opt/eval && /opt/eval/bin/pip install -q --upgrade pip && \
/opt/eval/bin/pip install -q numpy==1.26.4 scipy==1.13.1 nibabel==5.3.0 fastapi==0.115.0 starlette==0.38.6 anyio==4.11.0 \
  pydantic==2.9.0 pydantic-settings==2.5.0 python-dotenv==1.0.1 python-json-logger==2.0.7 \
  Pillow==10.4.0 pydicom==2.4.4 nilearn==0.14.1 scikit-image==0.24.0 scikit-learn==1.7.2 || exit 1
python3 -m venv /opt/greedy && /opt/greedy/bin/pip install -q --upgrade pip && \
  /opt/greedy/bin/pip install -q picsl_greedy==1.4.0.3 numpy==1.26.4 SimpleITK==2.5.3 typing_extensions==4.12.2 || exit 1
log

W=/w; D=/w/d; mkdir -p $W/repo $D/mimics/inputs $D/pf/flames $D/manifests $D/wmh $D/atlas $W/work/registration $W/p1 $W/out
G="gcloud storage cp --quiet"
$G "$BK/$P1CODE" $W/p1code.tar.gz && tar -xzf $W/p1code.tar.gz -C $W/repo || exit 1
rm -rf $W/repo/backend && $G "$BK/$APPCODE" $W/appcode.tar.gz && tar -xzf $W/appcode.tar.gz -C $W/repo || exit 1
$G "$BK/$P2CODE" $W/p2code.tar.gz && tar -xzf $W/p2code.tar.gz -C $W/repo || exit 1
$G "$REGSRC/*.mat" $W/work/registration/ || exit 1
$G "$P1RES/per_unit.csv" "$P1RES/registration.json" "$P1RES/records.json" $W/p1/ || exit 1
$G "$BK/mimics/inputs/wmh_*_FLAIR.nii.gz" "$BK/mimics/inputs/wmh_*_brainmask.nii.gz" $D/mimics/inputs/ || exit 1
$G "$BK/flames-ensemble/cohort/mslesseg_*_gt.nii.gz" "$BK/flames-ensemble/cohort/openms_*_gt.nii.gz" $D/pf/flames/ || exit 1
gcloud storage cp -r --quiet "$BK/wmh2017/test" "$BK/wmh2017/training" $D/wmh/ || exit 1
$G "$BK/inputs/lstai_atlas/sub-mni152_space-mni_t1.nii.gz" $D/atlas/ || exit 1
du -sh $D/* $W/work/registration; ls $W/work/registration | wc -l; log

cd $W/repo
export GOOGLE_APPLICATION_CREDENTIALS=/nonexistent/credentials.json GOOGLE_CLOUD_PROJECT=mstool-offline-tests \
       GREEDY_PYTHON=/opt/greedy/bin/python
( while sleep 300; do log; done ) &
echo "=== E5 state C: gates (app pin, transforms, GR, recount) then the records ==="
CLOUDSDK_CONFIG=/nonexistent /opt/eval/bin/python research/paper_2/app_design_vm.py --pf $D/pf --mimics $D/mimics \
  --wmh $D/wmh --manifests $D/manifests --atlas-t1 $D/atlas/sub-mni152_space-mni_t1.nii.gz --work $W/work \
  --p1 $W/p1 --out $W/out --workers $WORKERS
RC=$?
cp $W/work/registration.json $W/out/registration_e5.json 2>/dev/null || true
gcloud storage cp -r --quiet $W/out/* "$OUT/"
echo "done $COMMIT rc=$RC" | gcloud storage cp - "$OUT/DONE" --quiet
echo "ALL DONE $(date -u) rc=$RC"
