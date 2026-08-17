# `data/` — Research data governance for CALM-MS

Professional, cost-aware home for every dataset the CALM-MS research track touches.
The rule that keeps it coherent: **only committed text lives in git; every byte of
imaging data is either re-downloadable public data or PHI — never versioned.**

## Taxonomy (what lives where)

| Layer | Path | What | Versioned? |
|---|---|---|---|
| **Registry** | `registry.yaml` | The catalogue: every dataset, provenance, license, N, size, access, status | ✅ yes |
| **Manifests** | `manifests/` | *Data-as-code* — reproducible fetch scripts. Downloading is a script, not a memory | ✅ yes |
| **External (raw)** | `external/<dataset>/` | Raw public datasets exactly as published. Re-downloadable → never stored in paid cloud, never in git | ❌ gitignored |
| **Cohorts (curated)** | `cohorts/<dataset>-<basemodel>/` | Analysis-ready pairs: base-segmenter probability map + aligned expert/consensus GT, one grid. The valuable, expensive-to-recompute artifact | ❌ gitignored |
| **Experiments** | `experiments/<run>/` | Experiment outputs (JSON tables, figures). Reproducible from cohorts | ❌ gitignored |
| **Cache** | `cache/` | Scratch / intermediates | ❌ gitignored |

Naming: cohorts are `{dataset}-{basemodel}` (e.g. `isbi19-lstai`, `ljubljana30-flames`)
so the source and the probability source are legible at a glance.

## Production data is SEPARATE and untouched

The app's clinical data is **not** here:
- **Images (PHI):** GCS bucket `brain-mri-medical-images` (project `brain-mri-476110`), keyed by `patients/{pid}/studies/{sid}/...`.
- **Records (PHI):** Firestore (patients / studies / segmentations / documents).
- **Access:** the deployed API (`brain-mri` Cloud Run) with an admin token.

Research data (public benchmarks + their derived cohorts) never mixes with the PHI
bucket. Our own 19 expert cases, pulled from the app, live curated under
`cohorts/isbi19-lstai/` and stay gitignored because they are patient-derived.

## Cost rules (Google Cloud — keep the bill near zero)

1. **No always-on GCP resources for research.** Zero standing cost is the default.
2. **Public raw data is data-as-code, not cloud storage.** It is free to re-download
   from GitHub/Zenodo; storing copies in paid GCS is waste. Keep the *manifest*, not the bytes.
3. **Compute (base segmenter → probability maps) runs on an ephemeral Spot VM**
   with `--max-run-duration`, `--instance-termination-action=DELETE`, and a self-delete
   `trap` — exactly the Phase-1 pattern (~$0.10–0.50/run, auto-deleted, 0 residual).
4. **Persist only the small curated cohorts.** If a cohort must live in the cloud for a
   VM run, use a temporary bucket prefix and delete it after; long-term keep uses
   Nearline/Coldline, never Standard.
5. **Getting the images is free on GCP.** Downloading public datasets to a local disk
   or into the ephemeral VM costs nothing on Google Cloud.

## How to add a dataset

1. Add an entry to `registry.yaml` (provenance, license, access, size, value).
2. Write `manifests/fetch_<dataset>.sh` that downloads **only the subset we need**
   (e.g. the MNI-space images + GT), reproducibly.
3. Build a curated cohort with the base segmenter into `cohorts/<dataset>-<basemodel>/`.
4. Point `run_conformal_experiment.py` / `run_phase2_rescoring.py --data-dir` at it.
