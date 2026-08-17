#!/bin/bash
# CALM-MS cloud job: run LST-AI on the cohort, upload outputs, self-delete.
exec > /var/log/calm.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
NAME=$(curl -s -H "Metadata-Flavor: Google" $MD/name)
ZONE=$(curl -s -H "Metadata-Flavor: Google" $MD/zone | awk -F/ '{print $NF}')
BK="gs://brain-mri-medical-images/calm-run"

log(){ gsutil -q cp /var/log/calm.log "$BK/calm.log" 2>/dev/null || true; }
# SELF-DELETE on ANY exit (success, failure, or error). Layer-1 (max-run-duration
# + DELETE) is the hard backstop; this deletes early to save cost.
cleanup(){ log; gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet; }
trap cleanup EXIT

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq docker.io
systemctl start docker 2>/dev/null || service docker start 2>/dev/null || true
sleep 5

mkdir -p /w/cohort /w/results
gsutil -m cp "$BK/cohort/*" /w/cohort/ ; log
docker pull jqmcginnis/lst-ai:v1.2.0 ; log

i=0
for t1 in /w/cohort/*_t1.nii.gz; do
  i=$((i+1))
  case=$(basename "$t1" _t1.nii.gz)
  mkdir -p /w/${case}_out /w/${case}_tmp
  echo "=== [$i/19] $case START $(date -u) ==="
  docker run --rm -v /w:/work jqmcginnis/lst-ai:v1.2.0 \
    --t1 /work/cohort/${case}_t1.nii.gz --flair /work/cohort/${case}_flair.nii.gz \
    --output /work/${case}_out --temp /work/${case}_tmp \
    --probability_map --device cpu --stripped || echo "!! LST-AI FAILED for $case"
  # Collect the key outputs (probability in MNI, final seg, affine, brain ref).
  cp /w/${case}_tmp/*space-mni_seg-lst_prob_1.nii.gz /w/results/${case}_prob_mni.nii.gz 2>/dev/null || echo "no prob1 $case"
  cp /w/${case}_tmp/*space-mni_seg-lst_prob_2.nii.gz /w/results/${case}_prob2_mni.nii.gz 2>/dev/null || true
  cp /w/${case}_tmp/affine_flair_to_mni.mat        /w/results/${case}_flair2mni.mat 2>/dev/null || echo "no affine $case"
  cp /w/${case}_tmp/*space-mni_FLAIR.nii.gz         /w/results/${case}_mni_ref.nii.gz 2>/dev/null || true
  cp /w/${case}_out/*dseg*.nii.gz                   /w/results/${case}_ai_seg.nii.gz 2>/dev/null || echo "no seg $case"
  cp /w/${case}_out/*prob*.nii.gz                   /w/results/${case}_seg_prob_native.nii.gz 2>/dev/null || true
  rm -rf /w/${case}_tmp /w/${case}_out
  gsutil -m cp /w/results/${case}_* "$BK/results/" 2>/dev/null || true
  log
  echo "=== [$i/19] $case DONE $(date -u) ==="
done

echo "ALL DONE $(date -u)"
touch /w/DONE ; gsutil cp /w/DONE "$BK/DONE" ; log
# trap self-deletes the VM now.
