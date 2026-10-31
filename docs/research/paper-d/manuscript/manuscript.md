# How fragile is an automated dissemination-in-space decision? A pre-registered multiverse analysis of brain-MRI DIS in multiple sclerosis, with a neuroradiologist reference

*Manuscript skeleton v0.2, 2026-10-31 (branch `research/paper-d-dis-fragility`). Research, not the
medical device. Numbers are frozen from `../records/results_v1.json` and `../RESULTS.md`; the
protocol was committed before any result (`../PROTOCOL.md`, commit `980cb56`). The reader study is
specified in `../READER_STUDY_PROTOCOL.md`; every result that needs the three neuroradiologists is
marked **TODO**. Supersedes `../MANUSCRIPT.md` (v0.1).*

**Authors.** Nicolás G. Bonilla Vargas¹; [Reader A]², [Reader B]³, [Reader C]⁴ (neuroradiologists;
authorship per ICMJE, `../READER_STUDY_PROTOCOL.md` §11) [+ others TBD].
¹ MSTool-AI. ²–⁴ TBD.
**Target.** NeuroImage: Clinical or AJNR (full paper); short version for a MICCAI workshop.
Reporting: GRRAS (Kottner et al. 2011) for the reader study; STARD 2015 items where applicable
(Bossuyt et al. 2015).

---

## Abstract

**Background.** Software now labels multiple sclerosis (MS) lesions by McDonald region and reports
whether brain MRI shows dissemination in space (DIS). Region labels have been compared with raters
lesion by lesion, but the decision itself — and how much it depends on equally reasonable choices
inside a pipeline — has not been measured, nor compared with neuroradiologists.

**Methods.** Pre-registered multiverse analysis on two public MNI-space cohorts (MSLesSeg,
Ljubljana; 124 scans, 85 patients after removing scans the FLAMeS segmenter was trained on). We
varied the segmenter (FLAMeS single folds and 5-fold ensemble, LST-AI), the probability threshold
(0.3–0.7), the minimum lesion size, the region rule (a medical-device rule and LST-AI's published
code, each with all or lateral ventricles) and the atlas registration: 1,120 automated pipelines and
32 pipelines on the expert lesion mask. Reference (this version): the device's DIS rule on the expert
mask. Primary outcomes: flip rate versus reference and the share of scans whose decision is not
unanimous across pipelines (patient-clustered bootstrap). **Reader study (TODO):** three
neuroradiologists, blinded, read 84 scans (all 48 non-unanimous and 36 unanimous controls) for
regional lesion presence and brain DIS, and labelled 1,181 expert lesions by region.

**Results (automated part).** The reference met brain DIS in 95.2 % of scans. The device's automated
default disagreed with it in 3.2 % (95 % CI 0.8–6.8), LST-AI as shipped in 8.1 % (3.3–13.8), the
average plausible pipeline in 5.3 % (2.9–8.5). The decision was not unanimous across pipelines in
38.7 % of scans (29.1–49.2) and contested (10–90 % of pipelines) in 9.7 % (5.0–15.4); in the lowest
lesion-count tertile, 65.1 % and 23.3 %. The segmenter was the largest driver (7.3 % disagreement
between pipelines differing only in segmenter; 3.3 points [1.2–5.6] above registration). With the
expert mask, only registration mattered (4.8 % not unanimous, 1.5–9.2). Infratentorial presence was
the least stable output. A pre-registered stability indicator built from threshold, size and
ventricle variations was nearly blind (1 of 124 scans); post hoc, disagreement between segmenters
flagged 11 % of scans including 3 of the 4 default errors. **Reader results: TODO.**

**Conclusions.** Automated brain-DIS decisions in established MS usually agree with the expert-mask
decision, but more than a third are not robust to equally plausible pipeline choices — mostly the
segmenter — and fragility concentrates in low-burden scans. **Whether these are the scans
neuroradiologists disagree on: TODO.**

---

## 1. Introduction

1. *Automated reports state DIS.* Nine of ten commercial MS reporting tools output McDonald-region
   counts (Mendelsohn et al. 2023); 75.6 % of surveyed users want a "fulfilment of the McDonald
   criteria" section in quantitative reports (van Nederpelt et al. 2025); a German consensus
   describes LST-AI as offering McDonald-criteria-based localisation (Wattjes et al. 2026), although
   the published LST-AI paper does not validate its location labels (Wiltgen et al. 2024).
2. *What is known.* Per-lesion agreement of automated region labels with raters (Rakić et al. 2021;
   van Nederpelt et al. 2024, 93 % of lesions on manual masks; the LST-AI preprint's confusion matrix,
   Wiltgen et al., medRxiv 2023). Human agreement on DIS is moderate: Fleiss κ 0.58–0.66 among three
   readers (Mahmoudi et al. 2026), κ 0.62 between trained radiologists and 0.29 for readers new to
   the criteria (Korteweg et al. 2007). Lesion location by region varies across patients and
   diagnostic regions (Pongratz et al. 2023).
3. *What is missing.* DIS is a threshold on counts (≥ 1 lesion in ≥ 2 regions; Thompson et al. 2018;
   Montalban et al. 2025; Barkhof et al. 2025), so one small lesion at a region border, a probability
   threshold or a definition ("which ventricles are periventricular?", Filippi et al. 2019) can flip
   it. Multiverse analysis (Steegen et al. 2016) and many-analysts studies (Botvinik-Nezer et al.
   2020) show how defensible analytic choices change conclusions; in MS, the registration algorithm
   alone changes lesion-location conclusions (Eloyan et al. 2014), and segmenters differ widely (de
   Sitter et al. 2017).
4. *Contributions.* (1) The first measurement of DIS-decision fragility across plausible pipelines,
   pre-registered, with clustered intervals; (2) the automated DIS decision versus the DIS from
   expert masks on public data; (3) an audit of how LST-AI's region rule (v1 MSMask, v2 FastSurfer)
   and a medical device that reuses its atlas treat the third and fourth ventricles; (4) a
   neuroradiologist reference on the contested scans, testing whether automated fragility marks the
   scans humans disagree on (**TODO**); (5) a stability signal a reporting tool can compute.

## 2. Methods

### 2.1 Data
MSLesSeg (Guarnera et al. 2025; 115 scans, 75 patients, MNI152 1 mm; one validated rater;
CC-BY-4.0; collected under the approval of Comitato Etico Catania 2, irreversibly anonymised) and the
Ljubljana 3D MS database (Lesjak et al. 2018; 30 patients; three-rater consensus; CC-BY). FLAMeS was
trained on Ljubljana patients 1–15 and 21–25: these 20 scans are excluded from all primary analyses.
One MSLesSeg scan with a blank T1 is excluded. **Primary set: 124 scans, 85 patients.**

### 2.2 Segmenters
FLAMeS (Dereskewicz et al. 2025; nnU-Net, 5 folds, no test-time augmentation) and LST-AI v1.2.0
(three-U-Net ensemble; Wiltgen et al. 2024), run on CPU; probabilities stored at 1/255 resolution.

### 2.3 Region assignment
MSMask atlas (LST-AI; labels CSF, GM, WM, ventricles, infratentorial; ICBM 2009c grid). Rules:
(i) the device rule (zone map, contact, priority IT > PV > JC > DWM); (ii) LST-AI `annotate.py`
verbatim (3×3×3 lesion dilation, PV > JC > IT > subcortical); each with all MSMask ventricles or the
lateral ventricles only (third ventricle split off by erosion and nearest-seed assignment).
Secondary: the device's earlier 3 / 4 / 3 mm distances, majority vote, and the PV > IT > JC order of
the LST-AI paper and v2.

### 2.4 Registration
G0: the datasets' MNI registration, atlas placed by world coordinates (the device). G1: LST-AI's
greedy deformable registration of the atlas T1 to the scan T1, with its exact commands. Secondary
G2: a seeded small misregistration (≤ 2°, ≤ 2 %, ≤ 2 mm).

### 2.5 DIS rule and references
Brain DIS: ≥ 1 lesion in ≥ 2 of periventricular (PV), cortical/juxtacortical (JC), infratentorial
(IT); spinal cord and optic nerve are unavailable (brain DIS is a partial proxy for McDonald 2017 /
2024). **Automated-part reference:** the device's code (`classify_from_zone_mask`,
`compute_dis_criteria`) on the expert mask; the research code reproduces the device bit for bit on
every scan. **Reader reference (final version):** majority of three neuroradiologists (§2.7).

### 2.6 Outcomes and statistics (pre-registered, PROTOCOL §6–§9)
P1 flip rate versus reference; P2 non-unanimity, contested share and pairwise disagreement across
pipelines; S1 factor attribution; S2 region-count stability; S3 strata; S4 ventricle audit; S5
stability indicator; S6 sensitivity analyses. Patient-clustered percentile bootstrap (B = 2,000,
seed 20261021).

### 2.7 Reader study (pre-specified before any read; `../READER_STUDY_PROTOCOL.md`)
- *Cases.* All 48 scans not unanimous across the 1,120 pipelines (12 contested) and 36 unanimous
  control scans (one per patient, from patients without a non-unanimous scan, sampled with a fixed
  seed and stratified by lesion-count tertile as far as available): 84 scans, 74 patients; 4
  training scans from outside the analysis set; 12 scans re-read after washout.
- *Readers and platform.* Three neuroradiologists, MSTool-AI research reading build (offline,
  local; not the medical device), blinded to every automated output, to the expert mask in Task 1,
  to the strata and to each other; randomised order per reader.
- *Tasks.* Task 1 — per scan: presence and count category of PV, JC/cortical and IT lesions, brain
  DIS, confidence. Task 2 (≥ 4 weeks later) — per lesion: region of each expert lesion (1,181
  lesions: all lesions of non-unanimous scans, up to 10 per control scan).
- *Analyses.* R1 (primary): association of automated non-unanimity with reader non-unanimity,
  adjusted for log lesion count; R2: automated decisions versus the reader majority
  (sampling-weighted to the 124-scan set); R3: Fleiss κ, Gwet AC1 and raw agreement (inter-reader),
  Cohen κ (intra-reader); R4: lesion-level agreement of the device and LST-AI rules with the reader
  majority by region; R5: sensitivity and specificity of the pre-specified stability signals.

## 3. Results — automated part (complete)

### 3.1 Cohort
124 scans from 85 patients (MSLesSeg 114 / 75; Ljubljana 10 / 10). Reference met brain DIS in
**95.2 % (90.7–98.4)**; 3,992 expert lesions ≥ 3 mm³; lesion-count tertile cuts 18 and 30 per scan.
Device agreement check: zone map equal on all 144 scans; 288 masks reproduced the device's counts and
decisions exactly. G1 registration QC: median brain Dice 0.907 (minimum 0.782).

### 3.2 Flip rate versus the reference (P1) — Table 1
| Pipeline | DIS differs from reference |
|---|---|
| Device automated default (FLAMeS fold 0, p ≥ 0.5, ≥ 3 mm³, device rule, G0) | **3.2 % (0.8–6.8)**; 3 false "met", 1 false "not met" |
| LST-AI as shipped | **8.1 % (3.3–13.8)** |
| Mean over the 1,120 automated pipelines | **5.3 % (2.9–8.5)** |
| Per-pipeline flip rate, min / median / max | 0.8 % / 4.8 % / 28.2 % |
| Scans flipped by ≥ 1 automated pipeline | **38.7 % (29.1–49.2)** |

### 3.3 Instability across pipelines (P2) — Table 2
| | Automated grid (1,120) | Expert-mask grid (32) |
|---|---|---|
| Not unanimous | **38.7 % (29.1–49.2)** | **4.8 % (1.5–9.2)** |
| Contested (10–90 % say "met") | 9.7 % (5.0–15.4) | 4.0 % (0.8–8.0) |
| Pairwise disagreement | 5.4 % (3.5–7.7) | 2.1 % (0.5–4.2) |
| Mean flip versus reference | 5.3 % (2.9–8.5) | 2.0 % (0.4–4.0) |

### 3.4 Drivers (S1) — Table 3
Disagreement between pipelines differing only in: segmenter family **7.3 % (4.9–10.1)**;
registration 4.0 % (2.1–6.2); FLAMeS fold 2.9 % (1.3–4.9); threshold 1.9 % (1.3–2.6); minimum size
1.1 % (0.6–1.8); region rule 0.9 % (0.5–1.5). Segmenter minus registration: **3.3 % (1.2–5.6)**
(criterion C3 met). On the expert mask only registration mattered: 4.1 % (0.9–8.0). One factor at a
time from the device default: LST-AI ensemble instead of FLAMeS fold 0 flips 11.3 % (6.2–17.3);
the device's pre-audit majority-vote rule would flip 16.1 % (9.3–23.3) of expert-mask decisions.

### 3.5 Regions (S2) — Table 4
| Region | Presence flip versus reference, grid mean | Device default | ICC(A,1) counts | Bias (default − reference) |
|---|---|---|---|---|
| Periventricular | 3.5 % (1.5–5.9) | 1.6 % | 0.79 (0.71–0.84) | +0.7 |
| Juxtacortical | 3.5 % (1.6–6.1) | 2.4 % | 0.95 (0.89–0.97) | −0.3 |
| **Infratentorial** | **33.3 % (27.3–39.1)** | **27.4 % (19.8–35.5)** | 0.73 (0.61–0.80) | −0.6 |
| Deep white matter | 2.8 % | 1.6 % | 0.88 (0.75–0.94) | +3.3 |

### 3.6 Where fragility concentrates (S3) — Table 5
Lowest expert lesion-count tertile (≤ 18 lesions, 43 scans): not unanimous **65.1 % (48.9–80.5)**,
contested **23.3 % (11.6–37.8)**, device-default flip 9.3 % (2.1–20.4); middle tertile 40.0 % / 5.0 %
/ 0 %; top tertile 9.8 % / 0 % / 0 %. All six scans whose reference is "not met" are non-unanimous.

### 3.7 Ventricles and the LST-AI rule (S4)
MSMask label 4 holds the lateral **and third** ventricles; the fourth ventricle lies in label 5
(infratentorial); thalami are labelled white matter. LST-AI v1 and the device therefore count a
lesion touching only the third ventricle as periventricular, against Filippi et al. (2019). Effect:
6 such expert lesions (G0), region changes in 3 (0.08 %) under the device rule; **no DIS decision
changed** (criterion C5 not met). 250 expert lesions (6.3 %) fall in no MSMask white-matter zone and
are reported as deep white matter by default. LST-AI's code checks PV → JC → IT while its paper and
v2 state PV → IT → JC; no decision changed in these cohorts. (Reported to the device's problem-report
process as PRB-001.)

### 3.8 Stability indicator (S5) and post hoc signals
The pre-registered indicator (12 internal variants: threshold 0.4/0.5/0.6 × size 3/14 mm³ ×
all/lateral ventricles) disagreed in **1 scan (0.8 %)** — nearly blind. *Post hoc, in-sample:*
segmenters disagree (FLAMeS fold 0 / ensemble / LST-AI at default settings) flagged 11.3 % of scans,
caught 3 of the 4 default errors, left a 0.9 % error rate among unflagged scans and had PPV 14/14 for
"not unanimous"; a thin margin (two regions, one with ≤ 2 lesions, or ≤ 1 region) flagged 9.7 %
(1 of 4 errors; 11/12 not unanimous). With 4 errors, sensitivity 75 % has a 95 % CI of 20–100 %.

### 3.9 Sensitivity analyses (S6)
With the 20 FLAMeS-in-sample scans: 35.4 % not unanimous (in-sample scans alone: 15.0 %, versus
38.7 % clean — contamination handling mattered). MSLesSeg only 37.7 %; Ljubljana clean only 50.0 %.
With the MAGNIMS 2016 rule (≥ 3 periventricular lesions; Filippi et al. 2016): **57.3 %** not
unanimous, default flip 7.3 %.

### 3.10 Pre-registered criteria
C1 fragile (lower bound of non-unanimity ≥ 10 %): **met** (29.1 %). C2 fragile with the expert mask
(lower bound ≥ 2 %): not met (1.5 %). C3 single biggest driver: **met, the segmenter**. C4 device
default: 3.2 % (0.8–6.8), reported without a claim. C5 ventricle definition material: not met.

## 4. Results — reader study (**TODO**, filled only by the pre-registered analysis)

- 4.1 Readers, reading times, protocol adherence, scans excluded for image quality — **TODO**.
- 4.2 R3 human baseline: Fleiss κ / Gwet AC1 / raw agreement for brain DIS and for PV, JC, IT
  presence; intra-reader κ on 12 repeats — **TODO** (Table 6).
- 4.3 R1: reader non-unanimity in pipeline-non-unanimous versus unanimous scans, adjusted odds ratio
  for log lesion count — **TODO** (Table 7, Figure 3).
- 4.4 R2: device default, LST-AI as shipped, grid mean and the device rule on the expert mask versus
  the reader majority (sampling-weighted); each reader versus the other two — **TODO** (Table 8).
- 4.5 R4: lesion-level region agreement (device rule and LST-AI rule versus the reader majority;
  confusion matrices; infratentorial; "no-zone" lesions; third-ventricle lesions) — **TODO**.
- 4.6 R5: stability signals versus "default ≠ reader majority" — **TODO**.

## 5. Discussion (draft points; final after the reader study)

1. *Agreement on average, fragility at the margin.* 3–8 % flip rates sound reassuring, but 39 % of
   scans have a plausible pipeline that says otherwise, two in three in the lowest-burden tertile —
   the scans where the DIS decision matters clinically (clinically isolated syndrome, early MS).
2. *The segmenter, not the post-processing, decides.* Threshold, size floor and region rule matter
   least; which network produced the mask matters most, then registration. A stability signal must
   vary the segmenter, not sweep thresholds.
3. *Infratentorial lesions are the weak link*, consistent with lower human agreement for
   infratentorial lesions (κ 0.56, Mahmoudi et al. 2026). **TODO: reader data.**
4. *Rule audits matter even when the effect is small.* The third-ventricle inclusion is a guideline
   error with negligible effect here; the device's former majority rule would have flipped 16 % of
   expert-mask decisions.
5. *Contamination is not a detail.* On FLAMeS's own training scans only 15 % of decisions were not
   unanimous.
6. *Human baseline.* **TODO**: is automated fragility larger than, equal to, or concentrated in the
   same scans as reader disagreement?

## 6. Limitations

- The automated-part reference is a device rule on an expert mask, not a radiologist's DIS read
  (addressed by the reader study).
- Established MS (95 % reference DIS met); fragility in clinically isolated syndrome is likely higher
  and is not measured here.
- Brain only (no spinal cord, no optic nerve).
- Expert masks: one validated rater (MSLesSeg) or a consensus (Ljubljana).
- MSMask region accuracy unmeasured; deep grey matter labelled white matter; approximate
  third-ventricle split; LST-AI v2 not run.
- Two single-site public cohorts; FLAMeS contamination limits the Ljubljana part to 10 patients.
- Reader study: images are MNI-registered and skull-stripped as distributed, not the native clinical
  acquisitions; readers see no clinical information; the enriched sample is re-weighted for
  population estimates; controls are heavier in lesion burden than non-unanimous scans (adjusted).

## 7. Conclusion — **TODO** (after the reader study)

---

## Declarations

- **Ethics.** Public, de-identified data released under CC-BY licences (MSLesSeg collected under the
  approval of Comitato Etico Catania 2, prot. 810/C.E., with consent to publication of anonymised
  data, Guarnera et al. 2025; Ljubljana 3D MS DB, Lesjak et al. 2018). Reader study: readers
  participate as investigators with written consent to the processing of their pseudonymised
  ratings; ethics-committee statement **TODO** (`../READER_STUDY_PROTOCOL.md` §10).
- **Competing interests.** N.G.B.V. develops MSTool-AI, software intended to become a commercial
  medical device whose DIS rule is evaluated here. Readers: **TODO**.
- **Pre-registration.** Automated part: `PROTOCOL.md` v1.0 committed before any outcome (`980cb56`).
  Reader study: `READER_STUDY_PROTOCOL.md`, to be time-stamped (OSF) before the first read — **TODO**.
- **Data and code.** Public data (MSLesSeg CC-BY-4.0; Ljubljana CC-BY). Code `research/paper_d/`
  with tests; records in `docs/research/paper-d/records/`. Reader ratings (pseudonymised) released
  with the paper if all readers agree — **TODO**.
- **Author contributions (CRediT).** **TODO**.

## References (each checked on 2026-10-31 against its DOI record via OpenAlex; quoted passages were checked in the source in `../LITERATURE.md`)

1. Barkhof F, Reich DS, Oh J, et al. 2024 MAGNIMS–CMSC–NAIMS consensus recommendations on the use of MRI for the diagnosis of multiple sclerosis. *Lancet Neurol* 2025;24(10):866–879. doi:10.1016/S1474-4422(25)00304-7
2. Bossuyt PM, Reitsma JB, Bruns DE, et al. STARD 2015: an updated list of essential items for reporting diagnostic accuracy studies. *BMJ* 2015;351:h5527. doi:10.1136/bmj.h5527
3. Botvinik-Nezer R, Holzmeister F, Camerer CF, et al. Variability in the analysis of a single neuroimaging dataset by many teams. *Nature* 2020;582(7810):84–88. doi:10.1038/s41586-020-2314-9
4. de Sitter A, Steenwijk MD, Ruet A, et al. Performance of five research-domain automated WM lesion segmentation methods in a multi-center MS study. *NeuroImage* 2017;163:106–114. doi:10.1016/j.neuroimage.2017.09.011
5. Dereskewicz E, La Rosa F, dos Santos Silva J, et al. A novel convolutional neural network for automated multiple sclerosis brain lesion segmentation. *J Neuroimaging* 2025;35(5):e70085. doi:10.1111/jon.70085
6. Eloyan A, Shou H, Shinohara RT, et al. Health effects of lesion localization in multiple sclerosis: spatial registration and confounding adjustment. *PLoS One* 2014;9(9):e107263. doi:10.1371/journal.pone.0107263
7. Feinstein AR, Cicchetti DV. High agreement but low kappa: I. The problems of two paradoxes. *J Clin Epidemiol* 1990;43(6):543–549. doi:10.1016/0895-4356(90)90158-L
8. Filippi M, Rocca MA, Ciccarelli O, et al. MRI criteria for the diagnosis of multiple sclerosis: MAGNIMS consensus guidelines. *Lancet Neurol* 2016;15(3):292–303. doi:10.1016/S1474-4422(15)00393-2
9. Filippi M, Preziosa P, Banwell BL, et al. Assessment of lesions on magnetic resonance imaging in multiple sclerosis: practical guidelines. *Brain* 2019;142(7):1858–1875. doi:10.1093/brain/awz144
10. Fleiss JL. Measuring nominal scale agreement among many raters. *Psychol Bull* 1971;76(5):378–382. doi:10.1037/h0031619
11. Guarnera F, Rondinella A, Crispino E, et al. MSLesSeg: baseline and benchmarking of a new multiple sclerosis lesion segmentation dataset. *Sci Data* 2025;12:920. doi:10.1038/s41597-025-05250-y
12. Gwet KL. Computing inter-rater reliability and its variance in the presence of high agreement. *Br J Math Stat Psychol* 2008;61(1):29–48. doi:10.1348/000711006X126600
13. Hardesty LA, Ganott MA, Hakim CM, et al. "Memory effect" in observer performance studies of mammograms. *Acad Radiol* 2005;12(3):286–290. doi:10.1016/j.acra.2004.11.026
14. Korteweg T, Uitdehaag BMJ, Knol DL, et al. Interobserver agreement on the radiological criteria of the International Panel on the diagnosis of multiple sclerosis. *Eur Radiol* 2007;17:67–71. doi:10.1007/s00330-006-0303-5
15. Kottner J, Audigé L, Brorson S, et al. Guidelines for Reporting Reliability and Agreement Studies (GRRAS) were proposed. *J Clin Epidemiol* 2011;64(1):96–106. doi:10.1016/j.jclinepi.2010.03.002
16. Lesjak Ž, Galimzianova A, Koren A, et al. A novel public MR image dataset of multiple sclerosis patients with lesion segmentations based on multi-rater consensus. *Neuroinformatics* 2018;16(1):51–63. doi:10.1007/s12021-017-9348-7
17. Mahmoudi N, Renne J, Konen FF, et al. Does interrater variation influence the classification according to the diagnostic criteria for multiple sclerosis? *Eur J Neurol* 2026;33(1):e70469. doi:10.1111/ene.70469
18. Mendelsohn Z, Pemberton H, Gray J, et al. Commercial volumetric MRI reporting tools in multiple sclerosis: a systematic review of the evidence. *Neuroradiology* 2023;65(1):5–24. doi:10.1007/s00234-022-03074-w
19. Montalban X, Lebrun-Frénay C, Oh J, et al. Diagnosis of multiple sclerosis: 2024 revisions of the McDonald criteria. *Lancet Neurol* 2025;24(10):850–865. doi:10.1016/S1474-4422(25)00270-4
20. Pongratz V, Bussas M, Schmidt P, et al. Lesion location across diagnostic regions in multiple sclerosis. *NeuroImage Clin* 2023;37:103311. doi:10.1016/j.nicl.2022.103311
21. Rakić M, Vercruyssen S, Van Eyndhoven S, et al. icobrain ms 5.1: combining unsupervised and supervised approaches for improving the detection of multiple sclerosis lesions. *NeuroImage Clin* 2021;31:102707. doi:10.1016/j.nicl.2021.102707
22. Steegen S, Tuerlinckx F, Gelman A, Vanpaemel W. Increasing transparency through a multiverse analysis. *Perspect Psychol Sci* 2016;11(5):702–712. doi:10.1177/1745691616658637
23. Thompson AJ, Banwell BL, Barkhof F, et al. Diagnosis of multiple sclerosis: 2017 revisions of the McDonald criteria. *Lancet Neurol* 2018;17(2):162–173. doi:10.1016/S1474-4422(17)30470-2
24. van Nederpelt DR, Pontillo G, Barrantes-Cepas M, et al. Scanner-specific optimisation of automated lesion segmentation in MS. *NeuroImage Clin* 2024;44:103680. doi:10.1016/j.nicl.2024.103680
25. van Nederpelt DR, Mendelsohn Z, Bos L, et al. User requirements for quantitative radiological reports in multiple sclerosis. *Eur Radiol* 2025;35(10):5967–5978. doi:10.1007/s00330-025-11544-x
26. Wattjes MP, Lukas C, Langner S, et al. Expert panel consensus guidelines of the German Society of Neuroradiology on the use of magnetic resonance imaging in the diagnosis and monitoring of multiple sclerosis. *Clin Neuroradiol* 2026;36(3):831–854. doi:10.1007/s00062-026-01670-4
27. Wiltgen T, McGinnis J, Schlaeger S, et al. LST-AI: a deep learning ensemble for accurate MS lesion segmentation. *NeuroImage Clin* 2024;42:103611. doi:10.1016/j.nicl.2024.103611 (preprint with the location confusion matrix: *medRxiv* 2023, doi:10.1101/2023.11.23.23298966, version 1)

*Verification notes.* Korteweg et al. was published online 2006, in print 2007 (vol. 17). Lesjak et
al. was published online 2017, in print 2018. The MSLesSeg first author is **Guarnera** (earlier
notes in this folder wrote "Rondinella 2025"). The Wattjes 2026 title is abbreviated in the DOI
record; full title to be copied from the journal at submission. LITERATURE.md items not cited here
(Bawil 2026, Spampinato 2025, Egger 2017, Griffanti 2018, Grahl 2019, Hagens 2019, Heinemann 2025,
Barkhof 1999) remain verified there and can be added.
