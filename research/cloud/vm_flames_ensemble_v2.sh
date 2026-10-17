#!/bin/bash
# MSTool research cloud job v2 — FLAMeS 5-fold ensemble on the public cohorts.
# Project mstool-research ONLY (free-credit account). Professional-grade safety:
#  * STANDARD (non-Spot) VM: not preempted; --max-run-duration caps the bill; the trap below
#    deletes the VM on any exit; a wall-clock guard stops runaway jobs.
#  * Inputs (FLAMeS weights, datasets) are mirrored ONCE into gs://.../inputs with SHA-256, so
#    reruns never depend on Zenodo/Figshare/GitHub availability.
#  * Python packages are frozen to gs://.../env/requirements.lock on the first run and reused, so
#    every rerun uses identical versions.
#  * The driver uploads every case as soon as it finishes and skips what is already uploaded.
#  * A manifest (versions, checksums, timings, errors) and a cost record go to the bucket.
# Metadata: folds="0 1 2 3 4"  datasets="openms mslesseg"  case-offset=0  case-limit=0
#           hourly-rate=0.39  machine-desc=n2-standard-8  max-hours=24  tta=0
exec > /var/log/job.log 2>&1
set -x
MD="http://metadata/computeMetadata/v1/instance"
meta(){ curl -sf -H "Metadata-Flavor: Google" "$MD/$1" 2>/dev/null || true; }
NAME=$(meta name); ZONE=$(meta zone | awk -F/ '{print $NF}')
FOLDS=$(meta attributes/folds);          FOLDS=${FOLDS:-0 1 2 3 4}
DATASETS=$(meta attributes/datasets);    DATASETS=${DATASETS:-openms mslesseg}
OFFSET=$(meta attributes/case-offset);   OFFSET=${OFFSET:-0}
LIMIT=$(meta attributes/case-limit);     LIMIT=${LIMIT:-0}
RATE=$(meta attributes/hourly-rate);     RATE=${RATE:-0.39}
MACHINE=$(meta attributes/machine-desc); MACHINE=${MACHINE:-n2-standard-8}
MAXH=$(meta attributes/max-hours);       MAXH=${MAXH:-24}
TTA=$(meta attributes/tta);              TTA=${TTA:-0}
CASE_IDS=$(meta attributes/case-ids)     # optional explicit case list (pilots); overrides offset/limit
BKT="mstool-research-data"; BK="gs://$BKT"; PFX="flames-ensemble"
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

W=/w; mkdir -p $W/cache $W/data; cd $W
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq unzip git python3-pip python3-venv 2>&1 | tail -1

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
if gcloud storage cp "$BK/env/requirements.lock" $W/requirements.lock --quiet 2>/dev/null; then
  pip install -q -r $W/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
else
  # torch AND torchvision from the SAME (CPU) index, before nnunetv2: a PyPI torchvision built for
  # another torch breaks with "operator torchvision::nms does not exist" (Aug 2026 and 2026-10-17).
  pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
  pip install -q nnunetv2 nibabel google-cloud-storage 2>&1 | tail -2
  pip freeze > $W/requirements.lock && gcloud storage cp $W/requirements.lock "$BK/env/requirements.lock" --quiet
fi
python3 -c "import torch,torchvision,nnunetv2,nibabel; from google.cloud import storage; from torchvision.ops import nms; from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor; nms(torch.zeros((1,4)), torch.zeros(1), 0.5); print('env ok', torch.__version__, torchvision.__version__)" || { gcloud storage rm "$BK/env/requirements.lock" --quiet 2>/dev/null; exit 1; }
# Extra public cohorts (MS3SEG, Muslim 2022, PediMS; docs/research/cohorts-extra.md) need the fetchers
# and HD-BET. HD-BET is installed with every frozen version as a CONSTRAINT, so torch / nnU-Net /
# numpy stay exactly as in the lock (HD-BET 2.0.1 only adds scikit-image).
EXTRA=""; for d in ms3seg muslim pedims; do case " $DATASETS " in *" $d "*) EXTRA="$EXTRA $d";; esac; done
if [ -n "$EXTRA" ]; then
  for f in cohorts_extra.py extra_cohorts_stage.py; do gcloud storage cp "$BK/$PFX/code/$f" "$W/$f" --quiet || exit 1; done
  pip freeze > $W/constraints.txt
  pip install -q -c $W/constraints.txt "hd-bet==2.0.1" --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
  python3 -c "import torch,torchvision,nnunetv2; from torchvision.ops import nms; nms(torch.zeros((1,4)), torch.zeros(1), 0.5); import sys; sys.path.insert(0,'$W'); import cohorts_extra as c; print('extra env ok', torch.__version__, nnunetv2.__file__, sorted(c.FETCHERS))" || exit 1
  which hd-bet || exit 1
fi
log

stage weights_start; echo "=== [2/5] FLAMeS weights (cached mirror of Zenodo 17955359) ==="
cache_get flames_weights.zip 'U=$(curl -s https://zenodo.org/api/records/17955359 | python3 -c "import sys,json;d=json.load(sys.stdin);print([f[\"links\"][\"self\"] for f in d[\"files\"] if f[\"key\"].lower().endswith(\".zip\")][0])"); curl -sL -o /w/cache/flames_weights.zip "$U"' || exit 1
export nnUNet_raw=$W/raw nnUNet_preprocessed=$W/prep nnUNet_results=$W/nnunet_results
mkdir -p $nnUNet_raw $nnUNet_preprocessed $nnUNet_results
unzip -q -o $W/cache/flames_weights.zip -d $nnUNet_results/ && rm -f $W/cache/flames_weights.zip
log

stage datasets_start; echo "=== [3/5] datasets (cached mirrors) ==="
case " $DATASETS " in *" openms "*)
  cache_get open_ms_data_MNI.tar.gz 'git clone -q --filter=blob:none --sparse https://github.com/muschellij2/open_ms_data.git /w/oms && git -C /w/oms sparse-checkout set cross_sectional/MNI && tar -czf /w/cache/open_ms_data_MNI.tar.gz -C /w/oms cross_sectional' || exit 1
  mkdir -p $W/data/open_ms_data && tar -xzf $W/cache/open_ms_data_MNI.tar.gz -C $W/data/open_ms_data && rm -f $W/cache/open_ms_data_MNI.tar.gz ;;
esac
case " $DATASETS " in *" mslesseg "*)
  cache_get mslesseg_52771814.zip 'curl -sL -o /w/cache/mslesseg_52771814.zip https://ndownloader.figshare.com/files/52771814' || exit 1
  mkdir -p $W/data/mslesseg && unzip -q -o $W/cache/mslesseg_52771814.zip -d $W/data/mslesseg && rm -f $W/cache/mslesseg_52771814.zip ;;
esac
if [ -n "$EXTRA" ]; then
  # All three cohorts fetched once (streaming range reads), cached as one tarball with its SHA-256.
  cache_get extra_cohorts_raw_v1.tar.gz "python3 $W/extra_cohorts_stage.py build-raw --out $W/extra_raw --cohorts ms3seg muslim pedims && tar -czf $W/cache/extra_cohorts_raw_v1.tar.gz -C $W extra_raw" || exit 1
  [ -d $W/extra_raw ] || tar -xzf $W/cache/extra_cohorts_raw_v1.tar.gz -C $W
  rm -f $W/cache/extra_cohorts_raw_v1.tar.gz
  for m in $W/extra_raw/*/manifest.json; do gcloud storage cp "$m" "$BK/extra_qc/$(basename "$(dirname "$m")")_manifest.json" --quiet --no-clobber 2>/dev/null || true; done
fi
log

stage cases_start; echo "=== [4/5] case list + ground truth ==="
python3 - "$OFFSET" "$LIMIT" "$DATASETS" "$BK" "$CASE_IDS" <<'PY'
import glob, json, os, subprocess, sys
import nibabel as nib, numpy as np
OFF, LIMIT, DATASETS, BK, CASE_IDS = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3].split(), sys.argv[4], sys.argv[5].split()
cases = {}
extra = {}
if os.path.exists("/w/extra_raw/cases_extra.json"):
    extra = {c: v for c, v in json.load(open("/w/extra_raw/cases_extra.json")).items() if v["cohort"] in DATASETS}
    for c, v in extra.items():
        cases[c] = {"flair": None, "gt": os.path.join("/w/extra_raw", v["gt"])}   # FLAIR set after stripping
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
ids = sorted(cases)
ids = ids[OFF:] if LIMIT <= 0 else ids[OFF:OFF + LIMIT]
if CASE_IDS:
    missing = [c for c in CASE_IDS if c not in cases]
    if missing:
        sys.exit(f"case-ids not found: {missing}")
    ids = sorted(CASE_IDS)
sel_extra = [c for c in ids if c in extra]
if sel_extra:   # skull-strip only the selected extra cases (reusing brains already in the bucket)
    subprocess.run([sys.executable, "/w/extra_cohorts_stage.py", "strip", "--raw", "/w/extra_raw", "--cases", *sel_extra,
                    "--bucket-prefix", f"{BK}/inputs/extra_stripped", "--out", "/w/extra_brain",
                    "--result", "/w/extra_selected.json"], check=True)
    got = json.load(open("/w/extra_selected.json"))
    for c in sel_extra:
        if c in got:
            cases[c]["flair"] = got[c]["flair"]
    ids = [c for c in ids if cases[c]["flair"]]
sel = {c: cases[c] for c in ids}
os.makedirs("/w/gt", exist_ok=True)
for c, v in sel.items():
    g = nib.load(v["gt"])
    nib.save(nib.Nifti1Image((g.get_fdata() > 0).astype(np.uint8), g.affine, g.header), f"/w/gt/{c}_gt.nii.gz")
json.dump(sel, open("/w/cases.json", "w"), indent=1)
print("CASES", len(sel), ids[:2], "...", ids[-2:])
PY
gcloud storage cp $W/gt/*_gt.nii.gz "$BK/$PFX/cohort/" --quiet --no-clobber 2>/dev/null || true
log

stage inference_start; echo "=== [5/5] driver: per-fold model, per-case upload, resumable ==="
gcloud storage cp "$BK/$PFX/code/flames_ensemble_driver.py" $W/driver.py --quiet || exit 1
TTAFLAG=""; [ "$TTA" = "1" ] && TTAFLAG="--tta"
( while sleep 600; do log; done ) &
python3 $W/driver.py --cases /w/cases.json --folds $FOLDS --bucket $BKT --prefix $PFX --run-id "$NAME" $TTAFLAG
stage inference_end
log
echo "ALL DONE $(date -u)"
