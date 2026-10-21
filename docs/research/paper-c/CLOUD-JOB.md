# Paper C — cloud job to launch: FLAMeS on the open_ms longitudinal scans (arm A4)

Prepared 2026-10-21 on branch `research/paper-c-pilot`. **Nothing has been launched.**
Project `mstool-research` and bucket `gs://mstool-research-data` only (isolated gcloud configuration
`C:/Users/Nicolas/.gcloud-mstool`). No command here touches any other project.

> **Resumen en español sencillo.** Hace falta pasar FLAMeS (los 5 modelos) por las 40 imágenes
> FLAIR públicas de Ljubljana con dos visitas por paciente (20 pacientes). En el ordenador local
> tardaría días; en una máquina de la nube de investigación tarda unas 4 horas y cuesta menos de
> 1 USD a precio de lista (del crédito gratuito). Con esos mapas se repite el análisis del artículo C
> con la regla que usa hoy la aplicación, sobre una verdad marcada por expertos. Primero una prueba
> corta (1 paciente, 1 modelo, unos céntimos) y después el trabajo completo.

## What the job does

`research/paper_c/cloud/vm_flames_openms_longitudinal.sh` (derived from
`research/cloud/vm_flames_ensemble_v2.sh`, same safety rules: standard VM, `--max-run-duration`,
self-delete trap, wall-clock guard, frozen environment lock, unchanged and resumable driver):

1. Reuses the frozen Python environment (`env/requirements.lock`) and the mirrored FLAMeS weights
   (`inputs/flames_weights.zip`) of the October jobs.
2. Fetches `longitudinal/coregistered` of open_ms_data once (sparse clone; T1/T2 deleted; FLAIR +
   brain mask + change mask ≈ 0.4 GB) and mirrors it to `inputs/open_ms_longitudinal_coreg_v1.tar.gz`
   with its SHA-256.
3. Skull-strips every co-registered FLAIR with the **supplied** brain mask (no HD-BET: no
   non-commercial weights involved).
4. Runs FLAMeS folds 0–4 separately with the unchanged
   `gs://mstool-research-data/flames-ensemble/code/flames_ensemble_driver.py` (no TTA, uint8 maps).

| Output | Path in `gs://mstool-research-data/` |
|---|---|
| FLAMeS fold k (uint8 + slope, co-registered grid) | `flames-openms-long/cohort/openmslong_patientNN_s{1,2}_f{k}_prob.nii.gz` |
| Expert change mask (same for s1/s2; NOT a lesion mask) | `flames-openms-long/cohort/openmslong_patientNN_s{1,2}_gt.nii.gz` |
| Manifest, cost, log, ledger | `flames-openms-long/manifests/`, `…/cost/`, `…/logs/`, `runs/<name>/runinfo.json` |

**Cost estimate.** Measured FLAMeS speed on `n2d-standard-4` (compute ledger): ≈ 68 s per
case-fold → 40 × 5 = 200 case-folds ≈ 3.8 h + ≈ 10 min setup ≈ 4 h × 0.176 USD/h ≈ **0.70 USD**
(list price; worst case with `--max-hours 8` ≈ 1.4 USD). Pilot ≈ 5–10 min ≈ 0.03 USD.

## Launch (owner)

```bash
export CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool"      # project mstool-research only
# The launcher lives on research/cloud-compute-ledger; the startup script on this branch.
git fetch origin
git worktree add ../mstool-ledger origin/research/cloud-compute-ledger
git show origin/research/paper-c-pilot:research/paper_c/cloud/vm_flames_openms_longitudinal.sh \
    > ../mstool-ledger/research/cloud/vm_flames_openms_longitudinal.sh
cd ../mstool-ledger

# The job reuses the driver already in the bucket: both md5 values must match.
gcloud storage hash research/cloud/flames_ensemble_driver.py
gcloud storage objects describe gs://mstool-research-data/flames-ensemble/code/flames_ensemble_driver.py --format="value(md5_hash)"

# 1) Pilot: patient16, both studies, fold 0
python research/cloud/launch_vm.py --name paperc-oml-pilot --machine-type n2d-standard-4 \
  --startup research/cloud/vm_flames_openms_longitudinal.sh --paper C --max-hours 2 \
  --purpose "Paper C pilot: FLAMeS fold 0 on open_ms longitudinal patient16 (2 studies)" \
  --meta folds="0" case-ids="openmslong_patient16_s1 openmslong_patient16_s2"
```

Pilot check (after the VM has deleted itself): two `_f0_prob` files exist, open with nibabel, have
the grid of `study1_FLAIR.nii.gz` of patient16, and probabilities ≥ 0.5 lie on bright FLAIR lesions.

```bash
# 2) Full run: 40 FLAIRs x 5 folds (resumes: the pilot's two fold-0 maps are skipped)
python research/cloud/launch_vm.py --name paperc-oml-full --machine-type n2d-standard-4 \
  --startup research/cloud/vm_flames_openms_longitudinal.sh --paper C --max-hours 8 \
  --purpose "Paper C: FLAMeS 5 folds on 40 open_ms longitudinal FLAIRs"

# 3) Download (about 0.1-0.2 GB) into the folder the analysis reads
mkdir -p data/cohorts/openms-longitudinal-flames
gcloud storage cp "gs://mstool-research-data/flames-openms-long/cohort/*_prob.nii.gz" \
    data/cohorts/openms-longitudinal-flames/
```

## After the download (no analysis change)

```bash
python research/paper_c/extract_candidates.py --workers 4   # adds D-seg to every open_ms patient
python research/paper_c/run_pilot.py                        # arms A4 / A4b are filled in automatically
```

A4 and A4b are pre-registered in PROTOCOL.md §6 (analysed exactly like A2/A2b). Register the run in
the compute ledger (`research/cloud/build_ledger.py` on the ledger branch) as usual.
