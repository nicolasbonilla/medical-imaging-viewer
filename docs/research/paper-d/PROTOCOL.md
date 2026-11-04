# Paper D — Pre-registered protocol

## How fragile is an automated dissemination-in-space decision? Flip rates of brain-MRI DIS under plausible pipeline choices

**Version:** 1.0 · **Date:** 2026-10-21 · **Branch:** `research/paper-d-dis-fragility`
**Status:** pre-registration. This file is committed **before any DIS outcome on real scans is
computed**. Already done at commit time, and disclosed here: atlas inspection (§4), the G1
registration preprocessing (§5.5, which produces warped atlases and image-similarity QC, no DIS),
and unit tests on synthetic lesion masks (§8). Any later change to this protocol is logged in §12
with its reason and the date, and RESULTS.md says which analyses were affected.

**What this is.** Research code and analysis, **not the medical device**. No file of `backend/app`
is modified. The device's Class C modules `ms_region_classifier.py`, `lesion_analysis_service.py`
and `lesion_metrics.py` are **imported read-only** so that the reference decision is computed by the
device's own code. No data of the device's users is used; only public datasets stored locally; no
cloud resource.

---

## 1. Question

When a brain-MRI dissemination-in-space (DIS) decision is produced automatically, how often does the
decision change when only **plausible** pipeline choices change — the lesion segmenter, the
probability threshold, the minimum lesion size, the region-assignment rule or atlas, and the atlas
registration? Which of these choices drives most of the change? And does the decision change
**relative to the decision the same software makes from an expert's lesion mask**?

DIS is evaluated on the brain only: ≥ 1 lesion in ≥ 2 of periventricular (PV), cortical/
juxtacortical (JC) and infratentorial (IT). Spinal cord and optic nerve are not available, so this is
**brain DIS**, a partial proxy for McDonald 2017 / 2024 DIS (a patient who is brain-DIS-negative may
still meet DIS with a cord or optic-nerve lesion).

## 2. Novelty check

Recorded in `docs/research/paper-d/LITERATURE.md` (same commit, before any result). Summary:

- automated **per-lesion region labels vs raters** exist (icobrain ms, Rakić et al. 2021; van
  Nederpelt et al. 2024, "93 % correctly classified"; the LST-AI medRxiv v1 confusion matrix);
- **not found**: the automated **DIS decision** compared with the DIS from expert masks, and the
  **flip rate of the DIS decision across plausible pipeline variants** (verdicts (i) and (ii)
  supported); nor any examination of how LST-AI / MSMask treat the third and fourth ventricles
  (verdict (iii) supported);
- human baseline for DIS: Fleiss κ 0.58–0.66 between three readers (Mahmoudi et al. 2026).

## 3. Data

| Cohort | Scans / patients | Space | Expert mask | FLAMeS status | Licence |
|---|---|---|---|---|---|
| MSLesSeg (Rondinella et al., Sci Data 2025) | 115 / 75 (longitudinal T1–T4 for 25) | MNI152 1 mm (182×218×182) | one rater, validated by a neuroradiologist and a neurologist | **not in training** (clean) | CC-BY-4.0 |
| Ljubljana 3D MS DB (Lesjak et al., Neuroinformatics 2018) | 30 / 30 | MNI152 1 mm | consensus of 3 raters | **in training except patients 16–20, 26–30** | CC-BY |

Inputs per scan, already on the scan grid (`data/cohorts/cloud-2026-10/`, git-ignored): the expert
mask; FLAMeS (nnU-Net, `Dataset004_WML`, no test-time augmentation) lesion probability of folds 0–4;
LST-AI v1.2.0 ensemble probability and its three single-model probabilities (U-Nets A, B, C); the
T1 image (for registration level G1). Probabilities are stored as integer codes k with p = k / 255.

**Primary analysis set ("clean set").** All MSLesSeg scans plus Ljubljana patients 16–20 and 26–30.

**Contamination.** FLAMeS was trained on the Ljubljana patients 1–15 and 21–25, so FLAMeS would look
artificially close to the expert there. These 20 scans are **excluded from every primary analysis**
and appear only in a sensitivity analysis (§6, S6a) labelled "FLAMeS in-sample". LST-AI was trained
on neither cohort.

**Pre-specified exclusion.** `mslesseg_P49_T2`: the public release ships a blank T1 (0.097 %
non-zero voxels), so LST-AI did not run and G1 is impossible. Primary set: **124 scans from 85
patients** (MSLesSeg 114 / 75, Ljubljana 10 / 10). Complete-case analysis; any further scan that
fails to load or whose grids differ is excluded and listed in RESULTS.md.

**Out of scope.** The native-space cohorts in `data/cohorts/cloud-2026-10/flames/` (MS3SEG, MUSLIM,
PediMS): there is no image in the local cohort to register an atlas to, and the device itself refuses
atlas regions on non-MNI grids (RC-032).

## 4. Atlas and licences

- **MSMask** (labels 1 CSF, 2 GM, 3 WM, 4 Ventricles, 5 Infratentorial), from the LST-AI v1.1.0
  release `lst_data.zip`, SHA-256 `2ad50b14…dd0f`. The same file ships with the device
  (`backend/data/msmask/`) and with the LST-AI v1.2.0 container that produced the LST-AI maps. Grid:
  ICBM 2009c 1 mm (193×229×193, origin −96/−132/−78). Atlas T1 `sub-mni152_space-mni_t1`
  (SHA-256 `d4104bbd…476b`), used only for registration level G1.
- **Licences.** LST-AI code is MIT. The atlas files carry no separate licence statement; we assume
  the repository's MIT licence applies and record this as **to be confirmed** (also open in the
  device's CAPA-006 PA-6.5). The atlas sits on the ICBM 2009c grid, whose template licence (McGill)
  permits use for any purpose with the copyright notice (LITERATURE.md §8). **No FSL atlas is used**
  (JHU and others are non-commercial; Harvard-Oxford is now CC BY-SA 4.0). greedy (picsl_greedy
  1.4.0.3, Apache-2.0) is a research tool only; it is not part of the device. FLAMeS weights are
  CC BY-NC 4.0 (research use).
- **Atlas inspection (done before this commit, not an outcome).** Label 4 is one connected structure
  that contains **the lateral ventricles and the third ventricle**; the **fourth ventricle carries
  label 5** (Infratentorial); the **thalami carry label 3 (WM)**. Pinned by
  `test_third_ventricle_is_inside_label4_and_fourth_inside_label5`.

## 5. Factor grid

### 5.1 Sources (S)

| Level | Meaning |
|---|---|
| E | expert mask (reference source) |
| F0 … F4 | FLAMeS single fold k (F0 = what the device's FLAMeS worker runs: `-f 0`, no TTA) |
| FENS | FLAMeS 5-fold ensemble (mean probability) |
| LENS | LST-AI ensemble (mean of its 3 U-Nets, as LST-AI outputs) |
| L1, L2, L3 | (secondary) LST-AI single U-Nets |

### 5.2 Probability threshold (T)

T ∈ {0.3, 0.4, 0.5, 0.6, 0.7}; voxel is lesion when p ≥ T, evaluated on the stored codes
(k ≥ 255·T; FENS: Σk ≥ 5·255·T). 0.5 is the default of FLAMeS, LST-AI and the device worker. Not
applicable to E.

### 5.3 Minimum lesion size (M)

A lesion is an 18-connected component (device convention, RC-030), except under the LST-AI rules,
which use 26-connected components as LST-AI's code does.

| Level | Rule |
|---|---|
| none | every component (LST-AI's own annotation has no floor) |
| v3 | volume ≥ 3 mm³ (device: `MIN_LESION_VOLUME_MM3`, MSSEG-2016 evaluation floor) — **default** |
| v14 | volume ≥ 14.14 mm³ (sphere of 3 mm diameter) |
| la3 | long axis ≥ 3 mm (Filippi 2019), measured as the largest bounding-box extent |

### 5.4 Region-assignment rule (R)

| Level | Rule |
|---|---|
| **APP** | the device: MSMask zone map (WM voxels within a 3×3×3 dilation of ventricles → PV, of cortex → JC, of infratentorial → IT; label-5 voxels → IT; other WM → DWM), lesion assigned by **contact**, priority IT > PV > JC > DWM; a lesion in no zone is DWM. **Default and reference rule.** |
| APP-LV | APP with the ventricles restricted to the **lateral** ventricles (third ventricle relabelled CSF) — the Filippi 2019 periventricular definition |
| LSTAI | LST-AI v1.2.0 `annotate.py` verbatim: each 26-connected lesion dilated by a 3×3×3 cube; PV if it touches label 4, else JC if it touches label 2, else IT if it touches label 5, else subcortical (= DWM). Priority **PV > JC > IT** |
| LSTAI-LV | LSTAI with label 4 restricted to the lateral ventricles |
| APP-3MM | (secondary) APP with the 3 / 4 / 3 mm distances (PV / JC / IT) that the device's IFU stated until CAPA-006 |
| APP-MAJ | (secondary) zone holding most of the lesion's voxels — the device's rule before the audit that introduced the contact rule; ties broken IT > PV > JC > DWM |
| LSTAI-ORD2 | (secondary) LSTAI with the order stated in the LST-AI paper and used by LST-AI v2: PV > **IT > JC** > SC |

**Third-ventricle split** (for the -LV rules): erode label 4 once (6-neighbourhood), which cuts the
interventricular foramina; the eroded component that is midline and narrow (centroid |x| < 2 mm,
centroid z < 20 mm, > 200 voxels, all voxels within |x| ≤ 10 mm) seeds the third ventricle, every
other eroded component seeds the lateral ventricles; every label-4 voxel takes the class of its
nearest seed. An approximation of the anatomy (it also assigns the midline CSF under the fornix to
the third ventricle); its extent is reported.

### 5.5 Registration (G)

| Level | Meaning |
|---|---|
| **G0** | the dataset's own MNI registration; atlas placed on the scan grid by world coordinates (nearest neighbour) — **the device** |
| G1 | LST-AI's own registration reproduced: greedy `-m WNCC 2x2x2 -sv -n 100x50x10` of the atlas T1 to the scan T1, MSMask warped with `-ri LABEL 0.2vox` (exact commands from `annotate.py`) |
| G2 | (secondary) G0 with a small residual misregistration: one seeded random perturbation per scan (rotation ≤ 2°, isotropic scale within ±2 %, translation within ±2 mm per axis, about MNI (0, −18, 18)) |

G1 quality control: Dice between the warped atlas brain and the scan's brain (T1 > 0). Primary
analyses keep every scan (the pipeline as shipped); a sensitivity analysis drops scans with
Dice < 0.70.

### 5.6 DIS rule and reference

- **DIS rule (fixed, the device's):** `compute_dis_criteria` — brain DIS met when ≥ 1 qualifying
  lesion lies in ≥ 2 of PV, JC, IT. Exploratory variant: PV requires ≥ 3 lesions (MAGNIMS 2016).
- **Reference decision:** source E, M = v3, R = APP, G = G0 — the DIS that **the device's own code**
  reports from the expert's mask. It is **not** a radiologist's DIS read (§10).
- **Device automated default:** F0, T = 0.5, M = v3, R = APP, G = G0.
- **LST-AI as shipped:** LENS, T = 0.5, M = none, R = LSTAI, G = G1.

### 5.7 Grids

- **Primary automated grid:** S ∈ {F0–F4, FENS, LENS} × T (5) × M (4) × R ∈ {APP, APP-LV, LSTAI,
  LSTAI-LV} × G ∈ {G0, G1} = **1,120 pipelines**, each weighted equally.
- **Expert downstream grid:** E × M (4) × R (4) × G (2) = **32 pipelines** (the reference is one).
- Secondary levels (L1–L3, APP-3MM, APP-MAJ, LSTAI-ORD2, G2, PV ≥ 3) are analysed separately (S6) and never
  enter the primary numbers.

## 6. Outcomes

Unit of analysis: the **scan**; scans are clustered within patients (MSLesSeg timepoints).

**Primary**

- **P1 — flip rate vs reference.** For a pipeline, the share of scans whose DIS differs from the
  reference. Reported for (i) the device automated default, (ii) LST-AI as shipped, (iii) the mean
  over the 1,120 primary pipelines (the expected flip rate of a pipeline chosen at random from the
  plausible set), with the distribution over pipelines (minimum, median, maximum), and (iv) the share
  of scans flipped by at least one pipeline.
- **P2 — instability across pipeline variants.** The share of scans whose DIS is **not unanimous**
  across the 1,120 primary pipelines; the share that is **contested** (10–90 % of pipelines say DIS
  met); and the mean pairwise disagreement (probability that two pipelines drawn at random disagree on
  a scan). The same three numbers on the 32 expert pipelines measure fragility that remains with a
  perfect lesion mask.

**Secondary**

- **S1 — drivers.** For each factor, the disagreement rate between pipelines that differ **only** in
  that factor, averaged over all such pairs and scans. Factors: segmenter family {F0, FENS, LENS},
  FLAMeS fold {F0–F4}, T, M, R, G. Also one-factor-at-a-time changes from the device default.
- **S2 — per-region count stability.** For PV, JC, IT and DWM: region-presence flip rate vs
  reference (grid mean and device default); device default vs reference counts (ICC(A,1), Bland–
  Altman bias and 95 % limits); within-scan dispersion of counts across the primary grid.
- **S3 — where fragility concentrates.** P1 and P2 within strata of the reference margin (number of
  DIS regions present in the reference: ≤ 1, 2, 3) and of expert lesion-count tertiles.
- **S4 — the ventricle definition and the LST-AI priority.** On expert masks at G0 and G1: lesions
  whose region changes APP → APP-LV and LSTAI → LSTAI-LV; lesions that touch only the third ventricle;
  lesions that touch both label 5 and label 4 (IT under the device, PV under LST-AI); lesions lying
  wholly outside the WM zones (DWM by default under APP); and the scans whose DIS changes.
  Filippi 2019 excludes lesions touching the third and fourth ventricles and midbrain lesions touching
  the aqueduct from PV; the fourth ventricle is already inside label 5, so only the third-ventricle
  part is testable here. LST-AI v2 (FastSurfer; CSF label 24 and choroid plexus mapped to PV) cannot
  be run here and is described from its code only.
- **S5 — a DIS-stability indicator (prototype for the app).** From the device default pipeline
  alone, recompute DIS under 12 internal variants the app can compute without running another network
  (T ∈ {0.4, 0.5, 0.6} × M ∈ {v3, v14} × R ∈ {APP, APP-LV}); flag the decision **fragile** when the
  12 do not agree. Also flag a **pivotal lesion**: default DIS met with exactly 2 regions, one of
  which holds a single lesion. Report the share flagged and, flagged vs not flagged, the flip rate
  vs reference (risk difference), plus sensitivity and specificity of each flag and of their union for
  "default ≠ reference" and for "not unanimous in the primary grid". In-sample, exploratory.
- **S6 — sensitivity analyses.** (a) adding the 20 FLAMeS-in-sample Ljubljana scans (FLAMeS results
  flagged); (b) secondary levels; (c) DIS with PV ≥ 3; (d) MSLesSeg only and Ljubljana-clean only;
  (e) G1 restricted to registrations with Dice ≥ 0.70.

## 7. Statistics

- Patient-clustered percentile bootstrap, **B = 2,000**, seed **20261021**; every interval is a 95 %
  interval resampling patients with all their scans. Each scan has equal weight.
- Differences between factors (S1) use the paired bootstrap of the difference.
- No multiplicity adjustment: the study is descriptive; every pre-specified outcome is reported,
  including null or unfavourable ones.

## 8. Implementation and verification

Code: `research/paper_d/` (`common.py`, `atlas.py`, `rules.py`, `register_atlas_greedy.py`,
`run_grid.py`, `analyze.py`); tests: `research/paper_d/tests/`.

- The zone map built by the research code equals the device's `generate_zone_map_atlas` output
  bit for bit (test).
- On **every scan**, the expert mask and the device-default mask are also run through the device's
  `classify_from_zone_mask` and `compute_dis_criteria`; the run **stops** if any region count or
  decision differs from the grid code.
- The LST-AI rule equals a literal port of `annotate.py` (test on real atlas anatomy).
- Outputs (git-ignored): `data/experiments/paper-d/`. Committed: summary records in
  `docs/research/paper-d/records/`.

## 9. Success criteria (decided now)

- **C1 — fragility.** "Automated brain-DIS is fragile under plausible pipeline choices" is claimed
  only if the lower 95 % bound of P2 (not unanimous, primary grid) is **≥ 10 %** of scans.
- **C2 — fragility without segmentation error.** "Rule, size and registration choices alone flip DIS"
  is claimed only if the lower 95 % bound of P2 on the expert grid is **≥ 2 %**.
- **C3 — the biggest driver.** A factor is named the biggest driver only if its S1 disagreement
  exceeds the runner-up's with a paired 95 % interval of the difference that excludes 0; otherwise
  we report that no single factor dominates.
- **C4 — the device default.** Its flip rate vs reference is reported with its interval; no
  threshold, no claim of clinical accuracy.
- **C5 — the ventricle definition.** Called material only if it changes the region of **≥ 1 %** of
  expert lesions (S4); DIS changes are reported as counts with the scans named.
- If C1 fails, the paper reports that automated brain-DIS is robust in this established-MS
  population, and says where the residual fragility sits (S3).

## 10. Limitations declared in advance

- **No radiologist reads yet.** The reference is the device's rule applied to an expert mask, not a
  radiologist's DIS decision. **The paper's final version requires three neuroradiologists**,
  blinded to every pipeline output, rating lesion regions and DIS on (i) every scan that is not
  unanimous in the primary grid and (ii) a random sample of unanimous scans; reference = majority;
  inter-rater agreement (Fleiss κ) reported as the human baseline.
- Established MS (most scans have many lesions): the marginal flip rate understates fragility in
  clinically isolated syndromes, where the decision is made; S3 addresses this only in part.
- Spinal cord and optic nerve absent (brain DIS only).
- MSLesSeg expert masks come from a single validated rater; Ljubljana masks are a consensus.
- MSMask region accuracy is unmeasured (device HAZ-005); the atlas sits on ICBM 2009c and the data
  on FSL MNI152, placed by world coordinates; the third-ventricle split is approximate.
- Two public cohorts, one site each (Catania 1.5/3 T; Ljubljana 3 T).

## 11. Deliverables

`RESULTS.md` (all pre-specified outcomes, deviations), `MANUSCRIPT.md` (skeleton with limitations),
`APP-FEATURE.md` (DIS-stability indicator, marked research input), `LITERATURE.md` (novelty check),
`records/` (summary JSON). Draft pull request only; nothing is merged or deployed.

## 12. Change log

| Date | Change | Reason | Affects |
|---|---|---|---|
| 2026-10-21 | v1.0 | first issue | — |
| 2026-10-22 | none to the protocol; implementation deviations and post hoc analyses are listed in RESULTS.md §12 (APP-3MM built at G0 only; fewer parallel workers; 21 scans recomputed, identical; post hoc stability signals labelled as such) | after the run | secondary rule APP-3MM only |
| 2026-10-31 | none to the automated analysis. §10's planned reader study is specified in `READER_STUDY_PROTOCOL.md` v1.0 (84 scans: all 48 non-unanimous + 36 unanimous controls; two tasks; washout ≥ 4 weeks), written before any reader was invited; case selection `select_reader_cases.py`, power `reader_power.py`. Citation correction: the MSLesSeg paper's first author is Guarnera (Sci Data 2025;12:920), not Rondinella | preparation of the reader study | none |
