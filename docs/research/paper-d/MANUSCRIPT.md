# How fragile is an automated dissemination-in-space decision? A multiverse analysis of brain-MRI DIS in multiple sclerosis

*Manuscript skeleton v0.1 (2026-10-21). Numbers are frozen from `records/results_v1.json` and
`RESULTS.md`; the protocol was committed before any result (`PROTOCOL.md`). **This version has no
radiologist reads; the final version requires three neuroradiologists (§2.7, §5).***

*Authors: N. G. Bonilla Vargas [+ co-authors TBD, incl. three neuroradiologists]*
*Target: NeuroImage: Clinical / AJNR (full paper); MICCAI workshop (short version)*

---

## Abstract

**Background.** Software now labels multiple sclerosis (MS) lesions by McDonald region and reports
whether brain MRI shows dissemination in space (DIS). Region labels have been compared with raters
lesion by lesion, but the decision itself — and how much it depends on the many equally reasonable
choices inside such a pipeline — has not been measured.

**Methods.** Pre-registered multiverse analysis on two public MNI-space cohorts (MSLesSeg, Ljubljana;
124 scans, 85 patients after removing scans the FLAMeS segmenter was trained on). We varied the
segmenter (FLAMeS single folds, FLAMeS 5-fold ensemble, LST-AI), the probability threshold
(0.3–0.7), the minimum lesion size (none, 3 mm³, 14 mm³, 3-mm long axis), the region rule (a
medical-device rule and LST-AI's published code, each with all ventricles or lateral ventricles only)
and the atlas registration (dataset MNI registration vs LST-AI's deformable registration): 1,120
automated pipelines plus 32 pipelines on the expert mask. Reference: the device's DIS rule applied to
the expert mask. Primary outcomes: DIS flip rate vs reference, and the share of scans whose decision
is not unanimous across pipelines, with patient-clustered bootstrap intervals.

**Results.** [P1, P2 with CIs; biggest driver; expert-mask fragility; ventricle finding; stratum
where fragility concentrates.]

**Conclusions.** [One sentence on fragility; one on the third-ventricle rule; one on the stability
indicator.]

---

## 1. Introduction

- Automated reports increasingly state McDonald-region counts and DIS (Mendelsohn 2023: 9 of 10
  commercial tools report region counts; van Nederpelt 2025: 75.6 % of users want a "McDonald
  criteria" section). Consensus documents describe LST-AI as offering "McDonald criteria-based
  localization" (Wattjes 2026) although its location labels were never validated in the published
  paper (Wiltgen 2024).
- What exists: per-lesion agreement of automated region labels with raters (Rakić 2021; van Nederpelt
  2024, 93 % on manual masks; LST-AI medRxiv v1: PV 80.5 %, JC 86.9 %, subcortical 33.9 %).
  Human DIS agreement is moderate (Fleiss κ 0.58–0.66, Mahmoudi 2026; κ 0.62 for trained readers,
  Korteweg 2007).
- What is missing: the decision. DIS is a threshold on counts (≥ 1 lesion in ≥ 2 regions), so a single
  small lesion near a region border, a threshold, or a definition (which ventricles are
  "periventricular"?) can flip it. Multiverse analysis (Steegen 2016) and analytic-flexibility studies
  (Botvinik-Nezer 2020) show how such choices drive conclusions; in MS, registration alone changes
  lesion-location conclusions (Eloyan 2014).
- Contributions: (1) the first measurement of DIS-decision fragility across plausible pipelines,
  with a pre-registered protocol and clustered intervals; (2) the automated DIS decision vs the DIS
  from expert masks on public data; (3) an audit of how LST-AI's region rule (v1 MSMask, v2
  FastSurfer) and a medical device that reuses its atlas treat the third and fourth ventricles,
  quantified; (4) a DIS-stability indicator a reporting tool can compute at no extra cost.

## 2. Methods

### 2.1 Data
MSLesSeg (Rondinella 2025; 115 scans, 75 patients, MNI152 1 mm; single validated rater) and the
Ljubljana 3D MS database (Lesjak 2018; 30 patients; 3-rater consensus). FLAMeS was trained on 20
Ljubljana patients; these are excluded from all primary analyses (sensitivity analysis only). One
MSLesSeg scan with a blank T1 is excluded. Primary set: 124 scans, 85 patients.

### 2.2 Segmenters and probability maps
FLAMeS (nnU-Net, 5 folds, no test-time augmentation; Dereskewicz 2025) and LST-AI v1.2.0 (3-U-Net
ensemble; Wiltgen 2024), run on CPU; probability maps stored at 1/255 resolution.

### 2.3 Region assignment
MSMask atlas (LST-AI; labels CSF, GM, WM, ventricles, infratentorial; ICBM 2009c grid). Rules:
(i) the device rule (zone map, contact, IT > PV > JC > DWM); (ii) LST-AI `annotate.py` verbatim
(lesion dilation, PV > JC > IT > subcortical); each with all MSMask ventricles or the lateral
ventricles only (third ventricle split off by erosion and nearest-seed assignment). Secondary: the
IFU 3 / 4 / 3 mm distances, majority vote, and the PV > IT > JC order of the LST-AI paper / v2.

### 2.4 Registration
G0: the datasets' MNI registration, atlas placed by world coordinates (the device). G1: LST-AI's
greedy deformable registration of the atlas T1 to the scan T1, reproduced with its exact commands.
Secondary G2: a seeded small residual misregistration (≤ 2°, ≤ 2 %, ≤ 2 mm).

### 2.5 DIS rule and reference
Brain DIS: ≥ 1 lesion in ≥ 2 of PV, JC, IT (spinal cord and optic nerve unavailable). Reference: the
device's own code (`classify_from_zone_mask`, `compute_dis_criteria`) on the expert mask with the
device settings. The research code reproduces the device bit for bit (checked on every scan).

### 2.6 Outcomes and statistics
As pre-registered (PROTOCOL §6–§9): flip rate vs reference (P1), non-unanimity, contested share and
pairwise disagreement across pipelines (P2), factor attribution (S1), region-count stability (S2),
strata (S3), ventricle audit (S4), stability indicator (S5), sensitivity analyses (S6).
Patient-clustered percentile bootstrap (B = 2,000).

### 2.7 Planned reader study (final version)
Three neuroradiologists, blinded to pipeline outputs, will rate each lesion's region and the DIS
decision on every scan that is not unanimous across pipelines and on a random sample of unanimous
scans. Reference = majority; Fleiss κ between readers is the human baseline; the automated and
expert-mask decisions are then compared with it.

## 3. Results

See RESULTS.md (§3.1 cohort; §3.2 P1; §3.3 P2; §3.4 drivers; §3.5 regions; §3.6 strata;
§3.7 ventricles; §3.8 indicator; §3.9 sensitivity).

## 4. Discussion

[To be written from RESULTS.md after the reader study; key points listed in RESULTS.md §Discussion
notes.]

## 5. Limitations

- **No radiologist reads.** The reference is a device rule applied to an expert mask, not a
  radiologist's DIS decision; agreement with the reference is not diagnostic accuracy. The final
  paper requires three neuroradiologists (§2.7).
- **Established MS.** Most scans have many lesions and meet brain DIS easily; fragility in clinically
  isolated syndromes, where the decision matters, is likely higher than the marginal rates here.
- **Brain only.** Spinal cord and optic nerve are absent; brain DIS is a partial proxy for McDonald
  2017 / 2024 DIS.
- **Expert masks.** MSLesSeg masks come from one validated rater; Ljubljana masks are a consensus;
  both are segmentations, not region reads.
- **Atlas.** MSMask's region accuracy is unmeasured; it treats deep grey matter as white matter; the
  third-ventricle split is approximate; LST-AI v2 (FastSurfer) could not be run.
- **Two sites**, one public cohort each; FLAMeS contamination limits the Ljubljana part to 10 patients.
- Registration G1 reproduces LST-AI's call but with the dataset's skull-stripped T1 against an
  unstripped atlas T1, as LST-AI does.

## 6. Conclusion

[After results.]

## Data and code availability

Public data (MSLesSeg CC-BY-4.0; Ljubljana CC-BY). Code: `research/paper_d/` (MIT-compatible),
tests in `research/paper_d/tests/`, records in `docs/research/paper-d/records/`.

## References (verified in LITERATURE.md)

Barkhof 2025; Botvinik-Nezer 2020; de Sitter 2017; Dereskewicz 2025; Eloyan 2014; Filippi 2016;
Filippi 2019; Griffanti 2018; Korteweg 2007; Lesjak 2018; Mahmoudi 2026; Mendelsohn 2023; Montalban
2025; Rakić 2021; Rondinella 2025; Steegen 2016; Thompson 2018; van Nederpelt 2024; van Nederpelt
2025; Wattjes 2026; Wiltgen 2024.
