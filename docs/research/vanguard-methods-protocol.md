# CALM-MS — Research Protocol & Publication Plan
## Distribution-free, lesion-wise precision control under scanner/site shift

**Document status:** research protocol (planning), 2026-08-22 · **Feature status:** DARK
(`CALM_MS_RESEARCH_ENABLED = False`) · **Software class:** IEC 62304 Class C
**PI:** Eduardo Romero · **Executing student:** TBD · **Repo:** `medical-imaging-viewer`

> **What this document is.** A concrete, executable protocol to take the repository's
> existing CALM-MS conformal lesion-detection code from a *scoped negative/characterization
> result* to a *genuine world-vanguard methods contribution*. It is written to be honest to
> the point of discomfort: several of our own earlier optimistic claims were retracted under
> adversarial review (see `docs/calm-ms/v2-learned-scorer-result.md`,
> `docs/calm-ms/PROGRAM-CONSOLIDATION.md`), and this protocol is built on top of those
> retractions, not around them.
>
> **What this document is NOT.** It is not a clinical-deployment plan, not a regulatory
> enablement dossier (that is `docs/calm-ms/VV-DOSSIER.md`), and not a claim that the
> guarantee currently works under shift. It does not modify any `app/` code.

---

## 0. TL;DR for a reader with five minutes

- **Where we actually are.** We have a mathematically correct, adversarially-hardened
  conformal lesion-FDR engine (`backend/app/services/conformal_lesion_fdr.py`), a transparent
  learned lesion scorer (`calm_ms_scorer.py` + `calibrated_lesion_scorer.py`), an OOD
  disclosure backstop (`conformal_ood.py`), and — critically — a *documented, reproduced
  failure analysis* showing that **none of these components, alone, keeps the FDR guarantee
  valid under a confident-false-positive scanner shift**.
- **The vanguard we can actually reach** is a **methods** contribution: a rigorous
  *characterization + candidate remedy* for the acquisition-driven **label-shift** failure of
  conformal lesion-FDR control, plus the Class-C-auditable machinery (transparent score, OOD
  disclosure, fail-closed provenance) that a real device would need. This is reachable with
  public + modest new data.
- **The vanguard we cannot yet reach** is a **clinical-biomarker** contribution (a certified
  per-site precision guarantee validated on real multi-scanner cohorts with EDSS/PRL/QSM
  endpoints). That is **data-locked** behind OFSEP/NAIMS/MSBase or our own prospective cohort,
  and no amount of method cleverness substitutes for it.
- **The single most important experimental result** the paper must produce: *on sites unseen
  during calibration, the realized lesion-wise FDR stays ≤ the target α — at higher sensitivity
  than a naive precision-matched probability threshold — via few-shot site-conditional (Mondrian)
  recalibration of a transparent learned score, with an OOD monitor disclosing the residual
  cases where even that fails.*

---

## 1. Honest positioning (no overclaiming)

### 1.1 Who we actually are
- **The group.** A regional computer-vision / medical-imaging lab (Universidad Nacional de
  Colombia, CIM\@Lab lineage) building a deployed Class C MS-imaging product. We are **not** an
  established MS-imaging authority: we are not MSSEG/Empenn, not the MAGNIMS network, not
  icometrix/CorTechs, and we hold no large curated multi-scanner MS cohort. Reviewers will know
  this; the protocol must *earn* credibility with rigor and honesty, not borrow it from a brand.
- **The asset.** A real, deployed Class C device (`brain-mri-476110.web.app` + a FastAPI/Cloud
  Run backend) with a working segmentation/reporting pipeline, an IEC 62304 QMS, and — unusually
  for an academic group — an *engineering* discipline (fail-closed loaders, provenance stamping,
  adversarial verification, retraction of unsupported claims). That discipline is a genuine
  differentiator for a *methods-for-medical-devices* paper.

### 1.2 The constraints we operate under (state them, don't hide them)
- **Compute:** CPU-only, free-tier / no-recurring-cost mandate. No standing GPU. Base-segmenter
  inference (FLAMeS/nnU-Net) is run in short-lived rented GPU bursts, not a standing service.
- **Modality:** single-FLAIR + binary expert masks. **No** QSM, **no** PRL/CVS annotations,
  **no** longitudinal EDSS, **no** paired multi-vendor acquisitions of the same patient.
- **Data volume:** ~199 real segmentations in-product (Expert Rater = ground truth, legacy
  "Output Mask" = the thesis-era AI); for the conformal work the usable labelled public pool is
  ~145 FLAMeS-scored cases across 2 domains (openms + MSLesSeg), of which **only MSLesSeg (115
  cases) is FLAMeS-independent** and therefore usable for a clean null (see §1.4).
- **Baseline reality:** the legacy in-product AI over-segments — **lesion precision ≈ 0.22**,
  Dice ≈ 0.52, sensitivity ≈ 0.85 (memory-noted, legacy benchmark). The committed FLAMeS
  baselines give lesion sensitivity 0.83 (MSLesSeg) / 0.59 (open_ms). This *over-segmentation* is
  precisely the clinical problem a precision dial addresses — it is the honest motivation.

### 1.3 Two vanguards — one reachable, one data-locked
| | **Methods vanguard (reachable)** | **Clinical-biomarker vanguard (data-locked)** |
|---|---|---|
| **Claim** | Distribution-free lesion-precision control that is *characterized and made valid under scanner/site shift* by a transparent robust score + few-shot Mondrian recalibration + OOD disclosure | A certified per-site precision guarantee, validated on real multi-scanner cohorts, tied to clinical endpoints (EDSS progression, PRL/CVS burden) |
| **Data needed** | Pooled public MS-lesion sets + Shifts 2.0 splits; ~20–30 labelled scans at ≥3–5 real scanners (modest new acquisition) | OFSEP/MSBase-scale longitudinal + EDSS; NAIMS/CAVS-MS PRL/QSM; our own LatAm multi-scanner cohort |
| **Venue** | Medical Image Analysis / IEEE TMI; MICCAI/ISBI | NeuroImage:Clinical; ECTRIMS/ACTRIMS; clinical journals |
| **Status** | **This protocol executes it.** | **This protocol sets up the data-wall strategy (§5); it does not claim to deliver it.** |

### 1.4 The one contamination fact that governs every experiment
FLAMeS — our base segmenter — was trained (its refs 12–14) on **ISBI-2015, the Ljubljana
3D-MS-DB (= our `open_ms_data`), and MSSEG-2016**. For a FLAMeS-based null those datasets are
**in-sample** and their false-candidate scores are optimistically sharp → non-exchangeable. This
is why the frozen null was rebuilt from MSLesSeg-only (`docs/calm-ms/DATA-STRATEGY.md` §1, §4).
**Rule for this protocol:** either (a) use only FLAMeS-independent data for any calibration/null,
or (b) swap to a base segmenter with a documented leave-those-out fold and publish the exclusion
manifest. This rule is non-negotiable and every experiment below inherits it.

---

## 2. The core contribution, precisely stated

### 2.1 The one-sentence claim
> **Lesion-wise, distribution-free false-discovery-rate (equivalently: precision) control for
> MS lesion detection that is made — and shown to *stay* — valid under scanner/site
> acquisition shift, using (i) a transparent, Class-C-auditable scanner-robust learned score
> as the conformal statistic, (ii) few-shot site-conditional (Mondrian) recalibration of the
> null, and (iii) an out-of-distribution monitor that *discloses* the residual cases where the
> exchangeability premise still cannot be met — with the whole stack fail-closed and
> reproducible.**

This is the exact gap the published conformal-selection work leaves open: the theorems assume
exchangeability; nobody has *characterized and engineered around* its acquisition-driven
**label-conditional** failure for MS lesion instances, inside a device-grade transparent stack.

### 2.2 What is already built (cite the code, honestly)
- **The FDR engine — sound, verified.** `conformal_lesion_fdr.py`:
  `conformal_pvalues()` computes `p = (1 + #{null ≥ s}) / (n+1)`
  (`conformal_lesion_fdr.py:36-54`), `benjamini_hochberg()` does BH step-up
  (`:57-77`), `select_by_fdr()` composes them (`:80-88`), and `effective_score_cutoff()`
  exposes the adaptive selection's equivalent hard threshold for audit/UI (`:91-98`). The engine
  *refuses* non-finite scores because a non-finite test score would sort above all null scores and
  invert the guarantee (`:48-50`) — a fail-closed detail that matters for Class C.
- **The transparent score — a genuine within-domain component.**
  - Feature layout is contractual and split into *scanner-inflatable* probability moments vs
    *robust* morphology/location features (`calm_ms_lesion_features.py:22-25`), extracted at
    inference **without ground truth** (`candidate_feature_matrix()`, `:64-78`).
  - The shipped scorer is a **degree-2 polynomial logistic regression stored as plain arrays**
    (means/stds, integer monomial-exponent matrix, coefficients) with a pure-NumPy forward pass —
    *no pickled estimator, no arbitrary-code-execution surface, re-derivable by hand*
    (`calm_ms_scorer.py:1-19`, forward pass `:47-64`). It **fails closed** on a
    missing/malformed/empty/provenance-mismatched asset (`load_lesion_scorer()`, `:67-101`;
    note the explicit refusal of an empty-coefficient model that would degrade to a constant,
    `:93-97`). This transparency is a deliberate Class C property and part of the contribution.
  - The training-time twin (`calibrated_lesion_scorer.py`) is L2 logistic + isotonic calibration
    via PAVA (`CalibratedLesionScorer`, `:153-176`); isotonic is monotone so it does **not**
    change the conformal ranking — *calibration is for the UI readout; the guarantee comes from
    the conformal layer* (`:1-23`).
- **The OOD monitor — a disclosure backstop, correctly scoped as insufficient.**
  `conformal_ood.py` measures a Mahalanobis distance of the case's 5-number candidate-score
  summary to the calibration envelope (`assess_ood()`, `:131-159`; threshold 5.0 chosen from a
  115-case validation sweep, `:61-72`). Its own docstring states — and adversarial review proved
  — that it audits the **mixed marginal**, not the **label-conditional false-candidate law** the
  FDR guarantee depends on, so it is *necessary but not sufficient* and can pass a case that
  realizes FDP ≈ 1.0 (`conformal_ood.py:27-52`). We treat it as an honest disclosure layer, never
  as a certificate.

### 2.3 What is *not yet* true — the load-bearing honesty
The task framing ("the robust score + OOD monitor keep the guarantee valid under shift") is the
**target**, not a demonstrated result. Our own reproduced findings
(`docs/calm-ms/F1-site-shift-investigation.md`, `v2-learned-scorer-result.md`,
`PROGRAM-CONSOLIDATION.md` §3) establish:
1. Under a *severe confident-FP* scanner shift, the pooled guarantee **breaks** (realized FDR
   0.43–0.63) and the OOD monitor is **blind** (0/115 flagged).
2. Site-conditional recalibration restores a *theoretically* valid null but power **collapses**
   (recovers 1 of 2692 lesions) when FPs are as confident as TPs — because raw probability is then
   anti-informative.
3. The learned score is a real *within-domain* gain (patient-grouped AUC ≈ 0.80 vs 0.70 raw) but
   under a *fair* monotone shift it does **not** beat raw probability, and **pooled**
   leave-one-site-out AUC is only ≈ 0.62. *(An earlier claim that the score "survives the shift"
   was rigged and is retracted.)*
4. Encouragingly, a **few-shot site-conditional (Mondrian)** scheme controls FDR from k≈2 with
   power plateauing by k≈10 in a 2-site study (`docs/calm-ms/cross-site-selection-study.md`) — a
   *promising candidate*, not a proof (2 sites, no finite-sample bound, a no-label baseline also
   held empirically).

**Therefore the contribution is not "we fixed it" but "we precisely delimit *why* the naive
guarantee fails under acquisition shift, and we demonstrate a transparent, few-shot, Class-C
recipe that restores a *valid-and-useful* operating point in the regime where it is recoverable,
while honestly disclosing the regime where it is not."** That is a stronger, more defensible
methods paper than an overclaim, and it is reachable.

### 2.4 Explicit distinction from the closest prior art
| Work | What it controls / does | How CALM-MS differs |
|---|---|---|
| **Jin & Candès 2023**, *Selection by Prediction with Conformal p-values* (arXiv 2306.xxxxx) + **Weighted Conformalized Selection** (arXiv 2307.09291) | FDR over a *selected set* via conformal p-values; WCS reweights for **covariate** shift | Our engine is exactly their unweighted selection. **WCS's covariate-reweighting does not repair the MS shift**, which is a *label*-shift (P(score∣false) drifts), violating WCS's P(Y∣X)-invariance assumption (`cross-site-selection-study.md` Q1). We diagnose this and use **Mondrian** recalibration instead. |
| **Angelopoulos & Bates**, *Conformal Risk Control*, ICLR 2024 (arXiv 2208.02814) | Expected value of a monotone bounded loss via one threshold λ | Root framework, not our theorem. CALM-MS controls a **set-level FDR** (BH on conformal p-values), and its open problem is *exchangeability under shift*, which CRC also assumes. |
| **"Conformal Lesion Segmentation for 3D Medical Images"**, arXiv:2510.17897 (2025) | Test-time **FNR / recall** (guards *under*-segmentation) | **Closest prior art, orthogonal axis.** They bound the *miss* rate; we bound the *false-discovery* rate (over-segmentation) — the opposite clinical failure, the one our legacy AI actually exhibits (precision 0.22). |
| **"Conformal prediction enables disease course prediction in MS"**, npj Digital Medicine 2025 | **Patient-level** prognostic prediction sets (disease-course) | Different granularity and object. We control error at the **lesion instance** level on the imaging map, not patient-level outcome sets. |
| Conformal lesion-FDR for **tumours/nodules** (arXiv 2504.04482; 2412.20167) | Lesion-instance FDR for other pathologies | Shows the *wrapper* is not novel per se. **Our contribution is the MS-specific acquisition-shift failure characterization + the transparent few-shot remedy**, not the wrapper. |

The honesty of row 5 is deliberate and load-bearing: we do **not** claim the conformal-FDR
wrapper as novel. We claim the **shift-robustness characterization + Class-C transparent recipe**.

---

## 3. Experimental plan

### 3.1 Design principles (fixed before any run)
1. **Patient-level splits, always.** MSLesSeg contains multiple longitudinal timepoints per
   patient; grouping CV by *scan* leaks. Group by *patient* (the v2 result already showed the
   fix: 145 scans → 105 patients, AUC 0.801 → 0.796, `v2-learned-scorer-result.md` §Results-2).
   Every split, CV fold, and calibration/test partition in this protocol is **patient-grouped**.
2. **The calibration unit is a scan, not a lesion.** False candidates cluster within a scan, so
   the effective N is scans and the smallest achievable conformal p-value is `1/(n_scans+1)`
   (`DATA-STRATEGY.md` §2). This caps the resolvable α and must be reported per experiment.
3. **FLAMeS-independence rule (§1.4)** governs every null/calibration set.
4. **Base-model-bound producer.** Probability maps must come from a documented base segmenter on a
   documented grid; an off-grid or wrong-model map is caught fail-closed (this is Gate 6 in the
   V&V dossier; for the *paper* we simply fix and log the producer per experiment).

### 3.2 Datasets (pooled public + benchmark shift splits)
| Dataset | Role | FLAMeS status | Notes |
|---|---|---|---|
| **MSLesSeg (ICPR-2024)**, 115 series, multi-center | Primary clean null + within-domain eval | **independent** ✅ | Multi-center curated (Nature Sci Data 2025, s41597-025-05250-y); the current frozen null. |
| **MSSEG-2016**, 15 masks / 4 scanners | Scanner-isolation anchor | **contaminated** ✗ for FLAMeS | Usable only with a base-model swap + exclusion manifest; ~3.75 masks/scanner → coarsest α ≈ 0.21. |
| **MSSEG-2 (2021)**, 40 masks / 15 scanners, 4-rater uniform | **The** clean multi-scanner instrument | **independent** ✅ | Annotation-uniform; FLAIR-only, new-lesion task; ~2.7 masks/scanner → α ≈ 0.27. Where a label-free baseline can genuinely break. |
| **ISBI-2015** | External OOD test *only if* base swapped | contaminated ✗ for FLAMeS | Longitudinal; forbidden as a FLAMeS null. |
| **3D-MR-MS (Ljubljana / open_ms_data)** | Motivating illustration only | contaminated ✗ (in-sample) | In-FLAMeS-training; its within-site ECE is an in-sample artefact. Do not use as a clean null. |
| **"Muslim" MS FLAIR dataset** (Mendeley/Muslim et al.) | External generalization test | independent (verify) ✅? | Single-modality FLAIR + masks; verify provenance and rater protocol before use. |
| **Shifts 2.0 MS Lesion benchmark** (Malinin et al., NeurIPS 2022; Zenodo 7051658/7051692) | **Field shift benchmark** (in-domain vs `dev_out`/`eval_out`) | contaminated ✗ for FLAMeS; also **CC-BY-NC-SA / OFSEP DUA, non-commercial, 3-yr** | Supports a **marginal (pooled) shift** eval, *not* per-site Mondrian nulls. Report on it for field comparability, with the base-swap + license caveats stated. |
| **MICCAI-2008 (CHB/UNC)** | External OOD test, single-rater | independent (verify) ✅? | 2 sites, 0.5 mm iso; geometry differs — resampling caveat. |

**Metric axis:** lesion-wise **F1 / PPV (precision) / sensitivity** and **error-retention
curves** (the field has moved past Dice; `DATA-STRATEGY.md` §3). Realized **FDP per scan** *and*
**marginal FDR over the pooled set** are both reported (they differ — see §3.6).

### 3.3 Base segmenter
- **Primary:** a strong **nnU-Net** MS-lesion base (FLAMeS is nnU-Net-based and is our current
  producer; mean Dice ≈ 0.74, beats SAMSEG/LST-LPA/LST-AI). The conformal layer is
  model-agnostic (`conformal_lesion_fdr.py:23-26`), so the segmenter is swappable.
- **Contamination-clean variant:** to *legitimately* use MSSEG-2016 / ISBI-2015 / Shifts, retrain
  or select an nnU-Net base with a **documented leave-those-datasets-out fold**, and publish the
  exclusion manifest. This is the honest cost of using the field-standard datasets with a
  guarantee that depends on held-out exchangeability.

### 3.4 The score ladder (the independent variable that matters)
1. **Raw pooled probability** (baseline conformal statistic).
2. **Transparent learned score** — the shipped degree-2 poly-LR on robust features
   (`calm_ms_scorer.py`), patient-grouped, with **IBSI-compliant** feature definitions for any
   radiomic/morphology feature (see §3.7).
3. *(Ablation, not headline)* a stronger black-box score (gradient boosting) to *bound* the
   transparency cost — reported only to quantify what auditability gives up, never as the device
   path.

### 3.5 The calibration ladder
1. **Naive precision-matched hard threshold** on the score (the honest non-conformal baseline —
   pick the threshold that matches the target precision on calibration data).
2. **Pooled ("one-size-fits-all") conformal selection** — BH on conformal p-values against a
   single frozen null.
3. **Few-shot site-conditional (Mondrian) recalibration** — the deployment site contributes a
   small labelled slice (k = 2, 5, 10, 20) whose false-candidate scores become the site's own
   null; select on the disjoint remainder (`cross-site-selection-study.md` Q3).
4. **Weighted conformalized selection (WCS)** — included as a *baseline that is expected to
   underperform*, to empirically confirm covariate-reweighting cannot repair the label-shift.

### 3.6 The primary experiment (the result the paper stands on)
**Multi-site external validation of realized FDR under scanner shift.**

> **Protocol.** Partition sites into *calibration sites* and *held-out (unseen) sites*. Build the
> null / few-shot slice on calibration sites only. On each unseen site, run each (score ×
> calibration) combination and measure the **realized lesion-wise FDR** at target α ∈ {0.10, 0.20,
> 0.30} and the **sensitivity at that operating point**. Repeat over patient-grouped resamples;
> report mean ± sd and the **fraction of resamples/scans exceeding α**.
>
> **PRIMARY RESULT (the claim to defend):** *realized lesion-wise FDR ≤ α holds on unseen sites
> under scanner shift — at strictly higher sensitivity than a naive precision-matched threshold —
> for the transparent-score + few-shot-Mondrian configuration, with the OOD monitor flagging the
> residual cases where it does not.*

**Two regimes, reported separately and honestly:**
- **Mild real cross-site shift** (e.g. between academic cohorts): our data show pooled control is
  *already* roughly adequate here (`F1-site-shift-investigation.md` Result 1). The claim in this
  regime is *sensitivity lift at maintained control*, not rescue.
- **Severe confident-FP shift** (a scanner inflating FP confidence): the regime where pooled
  control breaks (FDR 0.43–0.63) and the OOD monitor is blind. The claim here is that **few-shot
  Mondrian + robust score** recovers a *valid-and-useful* point where it is recoverable, and the
  paper **states plainly where it is not** (when FPs are as confident as TPs, no method recovers
  both validity and power — this is a fundamental, reportable limit).

### 3.7 Baselines, ablations, and compliance
- **Baselines:** raw-probability score vs learned score; naive threshold vs pooled conformal vs
  few-shot Mondrian vs WCS; with vs without the OOD monitor (measured as: does the monitor's
  withheld set actually concentrate the FDR breaches?).
- **Ablations:** feature-group ablation (probability-only vs +morphology vs +location — expect
  location/morphology to co-lead, `v2-learned-scorer-result.md` §Results-3); k-sweep for the
  few-shot slice; label-shuffle null control (AUC should → 0.5, our reported sanity check); scan-
  vs patient-grouping (quantify the leakage the wrong grouping manufactures); α-resolution vs
  n_scans (show the `1/(n+1)` floor empirically).
- **IBSI compliance:** every morphology/radiomic feature (volume, sphericity, surface-to-volume,
  elongation, extent in `calm_ms_lesion_features.py:28-51`) is defined and reported per the
  **Image Biomarker Standardisation Initiative (IBSI)** conventions, with the isotropic-voxel and
  connectivity assumptions stated. This is a reviewer expectation for any radiomic-adjacent score
  and cheap to satisfy.
- **Reproducibility:** deterministic training (the LR is full-batch GD, no randomness,
  `calibrated_lesion_scorer.py:58-96`), transparent no-pickle assets, committed record JSONs,
  fixed seeds for resampling, and a public exclusion manifest for base-model contamination.

### 3.8 Statistical rigor guards
- **Multiplicity:** across {3 α presets × N sites × T timepoints} one cannot claim "controls FDR"
  simultaneously from a handful of resamples (rule of three: 0/30 bounds per-cell exceedance only
  at ≤10%, `DATA-STRATEGY.md` §2). Report a Bonferroni/По-family-wise correction or restrict the
  headline claim to a pre-registered cell.
- **FDR vs FDP:** marginal FDR (population) ≠ per-scan FDP; ~25% of scans exceed α at α=0.30 even
  when the marginal holds (`PROGRAM-CONSOLIDATION.md` §3.5). Report both; if a per-scan claim is
  wanted, add an **FDP-exceedance / FDX** control (Katsevich & Ramdas) as a clearly-scoped
  extension — do not silently upgrade a marginal result to per-scan.
- **Power ceiling is AUC, not N.** α < 0.2 at usable recall needs score AUC ≈ 0.90–0.95; our
  ceiling is ≈ 0.75–0.82 (`DATA-STRATEGY.md` §2). The honest feasible envelope is **α ≈ 0.2–0.3
  at recall ≈ 0.4–0.6**. State this as a finding, not a failure — it delimits what
  distribution-free lesion detection can deliver.

---

## 4. Target venues + timeline

### 4.1 Venues (matched to the two vanguards)
- **Methods (primary):** *Medical Image Analysis* (Elsevier) or *IEEE TMI* — the natural home for
  "distribution-free lesion-precision control under acquisition shift," full theory + multi-site
  eval + ablations. This is the paper this protocol is built to produce.
- **Conference + benchmark:** **MICCAI** or **ISBI** — a shorter, sharper version with the Shifts
  2.0 marginal-shift result and the MSSEG-2 scanner-isolation instrument; ideal for a public
  benchmark/leaderboard entry and community visibility. ISBI is a good *first* external stake
  given its lesion-segmentation heritage.
- **Clinical-facing (secondary, later):** *NeuroImage: Clinical* — once even a modest real
  multi-scanner cohort exists, framing the precision dial for radiologist workflow (second-reader
  triage) rather than as a pure method.
- **Abstracts / community:** **ECTRIMS / ACTRIMS** abstracts — cheap, high-visibility, and the
  right room to recruit the clinical collaborator and cohort access (§5). Submit an abstract even
  from the characterization result.

### 4.2 Indicative timeline (CPU/free constrained, one PI + one student)
| Phase | Months | Milestone |
|---|---|---|
| **P0 — Decontamination & harness** | 0–2 | Base-model exclusion manifest; patient-grouped harness; IBSI feature audit; MSLesSeg-clean reproduction of pooled control. *(Much of the code exists.)* |
| **P1 — Score + Mondrian on public data** | 2–5 | Transparent-score vs raw; pooled vs few-shot Mondrian vs WCS on MSLesSeg + (base-swapped) MSSEG-2; the α-resolution and AUC-ceiling curves. |
| **P2 — Shift benchmark** | 4–7 | Shifts 2.0 marginal-shift result (with license/base-swap caveats); MSSEG-2 scanner-isolation as the clean multi-scanner instrument. **ISBI/MICCAI submission.** |
| **P3 — Full methods paper** | 6–10 | Theory write-up (label-shift diagnosis, Mondrian remedy, OOD disclosure), full ablations, honest limitation section. **MedIA/TMI submission.** |
| **P4 — Real cohort (data-wall dependent)** | 10+ | *Gated on §5.* If a real multi-scanner slice arrives, the clinical-facing NeuroImage:Clinical paper + the *certified* per-site claim. |

Timelines assume no standing GPU; base-segmenter inference is done in short rented bursts and
cached. P4 is explicitly *not* on the critical path for the methods vanguard.

---

## 5. Collaboration + data-wall strategy

The methods vanguard (§1.3 left column) is reachable *without* new collaborations. The
clinical-biomarker vanguard is *entirely* a data-access problem. Strategy:

1. **Co-author with an MS-imaging authority to launder credibility and unlock the clean
   instrument.** The natural partner is **Rennes / Empenn (Olivier Commowick, Christian
   Barillot's group)** — owners of **MSSEG-2016 / MSSEG-2** and the **Anima** evaluation toolkit.
   A collaboration (a) gives principled access to the annotation-uniform, 15-scanner MSSEG-2
   (our one clean multi-scanner instrument) and (b) attaches an established MS-imaging name to a
   regional-lab paper. A **MAGNIMS** center (e.g. UCL/NMR Research Unit, VU Amsterdam) is the
   alternative. *Ask:* method co-development + scanner-isolated evaluation, not data transfer.
2. **Formal application to a longitudinal + EDSS registry.** File a data-access application to
   **OFSEP** (French MS registry; the same DUA that governs Shifts) and/or **MSBase** for
   longitudinal imaging with EDSS. This is a months-long governance process — *start it in P1*, in
   parallel, so P4 is not blocked on a cold start. This is the only realistic public route to the
   *biological* endpoints (progression, recovery) the clinical vanguard needs.
3. **Watch for the NAIMS / CAVS-MS ALPaCA-adjacent PRL/QSM release.** The **North American
   Imaging in MS (NAIMS)** cooperative and **CAVS-MS** are the groups moving paramagnetic-rim-
   lesion (PRL) / central-vein-sign (CVS) / QSM data toward shared availability. Track their
   releases; a QSM/PRL-annotated multi-scanner set would let the precision dial extend from
   "lesion vs not" to *biologically-typed* lesions — a second, higher paper. We hold none of this
   data today; the plan is to be *ready* (transparent, provenance-stamped stack) when it lands.
4. **The long-term unique asset: a Colombian / LatAm multi-scanner cohort.** Our genuine
   structural advantage is neither compute nor a European cohort — it is access, via the deployed
   product and local hospital relationships, to a **LatAm multi-scanner MS population that is
   under-represented in every public dataset**. A prospective collection of **~20–30 expert-
   labelled scans at each of ≥3–5 real scanners** (ideally with EDSS, and aspirationally QSM) is
   *exactly* the ~150-scan-per-site instrument the certified per-site Mondrian guarantee requires
   (`DATA-STRATEGY.md` §4). This is the highest-value, most-defensible long-term investment and
   the thing no reviewer can accuse of being "just a wrapper on public data." It is a
   clinical-partnership / IRB effort, not a download — begin scoping it in P2.

---

## 6. Honest risks, limitations, and the reviewer-attack surface

### 6.1 The risks that could sink the claim
1. **Single-cohort calibration.** The clean null is MSLesSeg-only (multi-center but one curated
   dataset). A guarantee calibrated on one dataset's idiosyncrasies may not transport. *Mitigation:*
   the entire point of §3.6 is to *test* transport on unseen sites; if it fails, that failure is
   the honest reported result, not hidden.
2. **Exchangeability under shift is the whole ballgame.** The FDR theorem is only as good as the
   premise that held-out false-candidate scores are exchangeable with the null. We have *proven to
   ourselves* this premise fails under confident-FP shift and cannot be certified by any score-only
   monitor (`conformal_ood.py:27-52`, `PROGRAM-CONSOLIDATION.md` §3.2). The paper must foreground
   this, not bury it — it is the contribution.
3. **MNI-pre-alignment hides real misregistration.** Our location features and pipeline assume
   correct MNI registration; the public data is pre-aligned, so real-world registration error
   (which *would* corrupt the location features an off-grid case scores plausibly-but-wrong) is
   invisible in our experiments (`v2-learned-scorer-result.md` §Honest-limitations). *Mitigation:*
   an explicit registration-perturbation ablation + a defense-in-depth guard in the scorer, and a
   stated caveat that real deployment needs a registration-quality gate.
4. **Small N and the AUC/α-resolution ceiling.** ~145 usable cases, ≈3 masks/scanner in the
   multi-scanner sets, α not resolvable below ≈0.2 on public data, power AUC-capped. The honest
   envelope (α ≈ 0.2–0.3, recall ≈ 0.4–0.6) must be stated as a finding.
5. **The "recovery"/biological endpoint is ambiguous.** Any clinical framing that reaches for a
   "lesion recovery" or progression endpoint inherits a genuinely ambiguous biology (a shrinking
   T2 lesion is not cleanly "recovery"). *Mitigation:* keep the methods paper strictly about
   *detection precision*; defer biological endpoints to the data-locked clinical vanguard where a
   real longitudinal+EDSS cohort can adjudicate them.

### 6.2 The reviewer's sharpest attack — and the answer
> *"A conformal wrapper on an existing segmenter is incremental. Conformal lesion-FDR already
> exists for tumours and nodules (arXiv 2504.04482, 2412.20167). What's new?"*

**The answer has three parts, and we concede the first:**
- **We concede the wrapper is not novel.** We say so in the abstract
  (`VV-DOSSIER.md` §Prior-art: "the wrapper is not novel"). Claiming otherwise would be
  dishonest and reviewers would find the prior art.
- **The novel, defensible contribution is the MS acquisition-driven *label-shift* failure
  characterization** — a reproduced, quantified demonstration that the exchangeability premise
  fails in a *specific, clinically-realistic* way (confident-FP scanner shift), that it is a
  *label*-shift invisible to covariate methods (killing WCS as a fix) and to any score-only OOD
  monitor, and that *neither a better null nor a better score alone* repairs it. Nobody has
  delimited this for MS lesion instances. It is a publishable *scoping/negative-plus-remedy*
  result.
- **Plus the Class-C-transparent engineered recipe** that a real device needs: a no-pickle,
  hand-re-derivable score; fail-closed provenance; an OOD monitor that *discloses rather than
  hides* its own insufficiency; and a few-shot Mondrian scheme with a *valid exchangeability
  argument* (not empirical luck). The combination of *honest characterization* + *transparent,
  auditable machinery* + *scanner-robust few-shot remedy* is the differentiator. The
  transparency and the disclosure-not-certification stance are not incidental — they are what
  make the method usable in a regulated device, which the tumour/nodule prior art does not
  address.

The strongest possible version of this paper is one a skeptical reviewer *cannot accuse of
overclaiming*, because it has already retracted its own overclaims in the open. That is the
strategy: rigor and honesty as the moat, since brand and data are not (yet) ours.

---

## 7. Execution checklist (for the student)

- [ ] **P0:** Reproduce pooled conformal control on MSLesSeg-clean; commit a record JSON. Audit
      every morphology feature against IBSI. Build the patient-grouped resampling harness.
- [ ] **P0:** Write the base-model exclusion manifest; decide nnU-Net base variant (FLAMeS as-is
      for MSLesSeg-only work; a leave-out-fold retrain to touch MSSEG-2016/ISBI/Shifts).
- [ ] **P1:** Run the full score ladder (§3.4) × calibration ladder (§3.5), patient-grouped, with
      k-sweep. Produce the α-resolution and AUC-ceiling curves.
- [ ] **P1:** File the OFSEP/MSBase data-access application (long lead time — start now).
- [ ] **P2:** Shifts 2.0 marginal-shift result (caveated). MSSEG-2 scanner-isolation via the
      Empenn collaboration. Draft ISBI/MICCAI submission.
- [ ] **P2:** Scope the LatAm prospective multi-scanner collection (IRB, hospital MoUs).
- [ ] **P3:** Full methods paper: theory + multi-site external validation (§3.6) + ablations +
      the honest-limitations section. Submit to MedIA/TMI.
- [ ] **Throughout:** never enable `CALM_MS_RESEARCH_ENABLED`; the research code stays DARK and the
      paper is about the *method*, not a deployed clinical claim (`VV-DOSSIER.md`).

---

### Appendix A — code map (what to cite in the paper's methods section)
| Component | File | Key lines |
|---|---|---|
| Conformal p-values + BH + selection | `backend/app/services/conformal_lesion_fdr.py` | `conformal_pvalues` 36–54, `benjamini_hochberg` 57–77, `select_by_fdr` 80–88, `effective_score_cutoff` 91–98 |
| Transparent frozen scorer (no-pickle poly-LR) | `backend/app/services/calm_ms_scorer.py` | forward pass 47–64, fail-closed loader 67–101 |
| Training-time scorer (LR + isotonic) | `backend/app/services/calibrated_lesion_scorer.py` | `LogisticRegressionL2` 58–103, `IsotonicCalibrator` 105–151, `CalibratedLesionScorer` 153–176 |
| Robust feature extraction (IBSI-audit target) | `backend/app/services/calm_ms_lesion_features.py` | feature layout 22–25, morphology 28–51, `candidate_feature_matrix` 64–78 |
| OOD disclosure monitor | `backend/app/services/conformal_ood.py` | scope/limitation docstring 27–52, `assess_ood` 131–159, threshold 61–72 |

### Appendix B — supporting internal records (evidence, all committed)
- `docs/calm-ms/F1-site-shift-investigation.md` — the shift-breaks-the-guarantee reproduction.
- `docs/calm-ms/v2-learned-scorer-result.md` — the retraction + honest within-domain scorer result.
- `docs/calm-ms/cross-site-selection-study.md` — the few-shot Mondrian candidate (2-site).
- `docs/calm-ms/DATA-STRATEGY.md` — contamination, feasibility ceiling, data-acquisition plan.
- `docs/calm-ms/PROGRAM-CONSOLIDATION.md` — the consolidated honest state of the science.
- `docs/calm-ms/VV-DOSSIER.md` — the enablement gates (why the feature stays dark).
