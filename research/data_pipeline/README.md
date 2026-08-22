# research/data_pipeline — public multi-site MS MRI → CALM-MS

A reproducible, documented pipeline that ingests **public** MS-lesion MRI datasets
into the repo's common cohort format, so the same data can (a) train a base lesion
segmenter and (b) **calibrate + externally-validate the CALM-MS conformal FDR
layer** across many scanners and sites.

It does **not** touch `app/` runtime code. It only *reads* the repo's frozen,
side-effect-free service functions (candidate extraction, per-candidate features,
conformal p-values) so this offline tooling and the served path can never diverge
— a Class C requirement.

```
research/data_pipeline/
├── datasets.yaml          # manifest: URL, access, sequences, N, license, site, use-mapping
├── download.py            # fetch OPEN datasets (idempotent/resumable/checksummed); steps for GATED
├── preprocess.py          # skull-strip/bias/register/normalize → standardized per-case records
├── to_calm_calibration.py # base-segmenter candidates + expert masks → CALM-MS calibration format
├── common.py              # shared target-format definitions + backend path bootstrap
└── tests/test_pipeline.py # CPU-only synthetic end-to-end test
```

## Install

```bash
pip install numpy scipy nibabel pyyaml requests   # core (always)
pip install SimpleITK                              # bias / strip / register steps
pip install hd-bet                                 # real skull-strip (Otsu fallback otherwise)
```

`git` is used to fetch the one repo-hosted dataset (`open_ms_data`).

## Run

```bash
# 0. see what's available and how each maps to a use
python -m research.data_pipeline.download --list

# 1. download the OPEN datasets (idempotent, resumable, md5/sha256-checked where possible)
python -m research.data_pipeline.download --all-open --dest ./raw
#    gated ones print exact registration/DUA steps + write a HOW_TO_OBTAIN.txt drop stub:
python -m research.data_pipeline.download --dataset msseg2 --dest ./raw

# 2. preprocess one dataset into the common cohort format
#    (datasets already in MNI-1mm — mslesseg, open_ms_data — can skip `register`)
python -m research.data_pipeline.preprocess --dataset open_ms_data \
    --raw ./raw/open_ms_data --out ./cohorts/open_ms_data --steps orient,normalize
#    → ./cohorts/open_ms_data/{cohort.csv, cases.json, *_t1.nii.gz, *_flair.nii.gz, *_gt.nii.gz}

# 3. run a base segmenter to get probability maps (existing repo tool), e.g. LST-AI:
python scripts/calm-ms/run_lstai_cohort.py \
    --manifest ./cohorts/open_ms_data/cohort.csv --out-dir ./cohorts/open_ms_data
#    → {case}_prob.nii.gz per case

# 4. emit the CALM-MS calibration format (per-candidate score/features + TP/FP + site)
python -m research.data_pipeline.to_calm_calibration \
    --data-dir ./cohorts/open_ms_data \
    --site-from-cohort ./cohorts/open_ms_data/cohort.csv \
    --dataset open_ms_data --out ./calib/open_ms_data
#    → calibration.csv + calibration_nulls.npz (pooled + per-site conformal nulls)

# 5. calibrate / validate the conformal layer (existing repo tools)
python scripts/calm-ms/run_conformal_experiment.py --data-dir ./cohorts/open_ms_data
#    and, for per-site (Mondrian) external validation, feed the per-site nulls from
#    calibration_nulls.npz the way scripts/calm-ms/site_recalibration_experiment.py does.
```

Run the test suite (no network, no real data):

```bash
pytest research/data_pipeline/tests/test_pipeline.py -q
```

## Target formats produced (matched to the repo)

**Cohort record** — the on-disk layout the existing LST-AI runner + conformal
experiment already consume: a `cohort.csv` with
`case,t1_path,flair_path,expert_path` (this pipeline adds `dataset,site,edss`
columns downstream tools ignore), plus `{case}_prob.nii.gz` + `{case}_gt.nii.gz`
once a base segmenter has run.

**CALM-MS calibration record** — `calibration.csv`: one row per lesion candidate
with the conformal statistic `score`, the null-membership flag `is_false`
(True = false positive), a `site` tag, and the full `FEATURE_NAMES` vector (so a
learned scorer can be refit). `calibration_nulls.npz` carries the ready-to-load
**pooled** null (all FP scores) and **per-site** nulls (`site::<tag>`) — exactly
the two inputs `conformal_lesion_fdr`/`site_recalibration_experiment` need to (i)
calibrate a site against its own FP distribution and (ii) externally validate the
FDR guarantee on the other sites.

## Dataset → use mapping

`flames_clean = true` means the dataset is **not** in the FLAMeS base-model
training set, so it is a valid held-out conformal null / external test for a
FLAMeS base. `false` means it's contaminated for FLAMeS (usable only with a
leave-this-out / non-FLAMeS base). Numbers + contamination flags come from the
repo's vetted `data/registry.yaml`.

| dataset | access | N (labeled) | sequences | site | FLAMeS-clean | use |
|---|---|---|---|---|---|---|
| **mslesseg** | open | 75 (115) | T1/T2/FLAIR | Catania 1.5T (1 site) | ✅ | seg-train, **conformal calibration** |
| **ljubljana_3dmrms** | open | 30 (+20 long.) | T1/T1Gd/T2/FLAIR | Ljubljana 3T | ❌ | external-site validation |
| **open_ms_data** | open | 30 (+20 long.) | T1/T1Gd/T2/FLAIR | Ljubljana 3T | ❌ | external-site validation |
| **msmri_baghdad** | open | 60 | T1/T2/FLAIR (2D) | Baghdad 1.5T | ✅ | external-site validation (**has EDSS**) |
| **shifts2_ms_part2** | open (NC) | ~O(100) | T1/FLAIR | multi-site | ❌ | benchmark protocol, external validation |
| **msseg2016** | gated | 15 | T1/T1Gd/T2/PD/FLAIR | 4 centers/scanners | ❌ | scanner-isolation anchor (non-FLAMeS base) |
| **msseg2** | gated | 40 | FLAIR only | **15 scanners/3 vendors** | ✅ | **conformal calibration** (scanner shift) |
| **isbi2015** | gated | 19 | T1/T2/PD/FLAIR | 1 center | ❌ | seg-train (non-FLAMeS base only) |
| **shifts_ms_part1** | gated | ~O(100) | T1/FLAIR | Rennes/Bordeaux/Lyon | ❌ | benchmark protocol |

The load-bearing clean scanner-shift instrument for a FLAMeS base is **MSSEG-2**
(FLAMeS-independent, 15 scanners); **MSLesSeg** is the largest clean single-site
calibration pool. The FLAMeS-contaminated sets (Ljubljana/open_ms_data, ISBI,
MSSEG-2016, Shifts) become usable for calibration only with a leave-this-out or
non-FLAMeS base.

## Honest data ceiling (read before over-claiming)

- **~500 labeled patients total** are publicly obtainable across every dataset
  here, and much of it is single-rater or *fused*-consensus (not independent
  multi-rater) ground truth. Per-site mask counts are small: MSSEG-2 is ~2.7
  masks/scanner and MSSEG-2016 ~3.75 masks/center — enough for a **marginal
  (pooled) shift** study, **not** for a well-powered per-site Mondrian null. Plan
  the primary claim as pooled cross-site coverage, not per-scanner guarantees.
- **No public QSM / PRL / CVS** advanced-imaging labels exist — the paramagnetic-
  rim / central-vein biomarkers cannot be trained or validated from open data.
- **No public longitudinal cohort paired with EDSS.** The Baghdad/Mendeley set
  ships EDSS but is single-timepoint 2D thick-slice; ISBI-2015 and MSSEG-2 are
  longitudinal but carry no disability scores. Disability-linked longitudinal
  modeling is out of reach with public data alone.
- **License reality:** MSLesSeg / open_ms_data / Ljubljana / Baghdad are CC-BY
  (frictionless); Shifts and the two MSSEG sets are **non-commercial + 3-year
  OFSEP DUA**. Keep commercial vs research use partitioned accordingly.

## Notes on reproducibility

- `download.py` is idempotent (skips verified files), resumable (HTTP `Range`
  `.part` files), and checksums against the Zenodo/Figshare APIs automatically;
  for direct/Mendeley entries add a `sha256` to `datasets.yaml` after the first
  fetch to lock the bytes.
- A few OPEN URLs still carry a `verify:` note in `datasets.yaml` (exact Figshare
  article id / click-through zip name) — confirm those from the live record before
  the first ingest. Everything else (`git`, `zenodo`, `mendeley`) resolves
  automatically.
- `preprocess.py` degrades gracefully: if SimpleITK/HD-BET are absent, the
  affected step is recorded as `skipped(...)` in `cases.json` rather than crashing,
  so the orient+normalize path always runs on a CPU-only box.
