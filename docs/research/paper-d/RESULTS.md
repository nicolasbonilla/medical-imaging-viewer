# Paper D — Results (v1, 2026-10-22)

Pre-registered protocol: `PROTOCOL.md` v1.0, committed and pushed before any outcome (commit
`980cb56`). Every number below is in `records/results_v1.json` (rendered with
`research/paper_d/report.py`). Intervals are 95 % patient-clustered percentile bootstrap intervals
(B = 2,000, seed 20261021). **No radiologist has read these scans** (§13).

Reproduce (main checkout's `data/` holds the public cohorts):

```
python research/paper_d/register_atlas_greedy.py --data-root <data> --greedy-python <venv>/python --workers 1 --threads 10
python research/paper_d/run_grid.py  --data-root <data> --workers 1
python research/paper_d/analyze.py   --data-root <data> --out docs/research/paper-d/records/results_v1.json
```

## 0. Verification of the computation

- **The grid code is the device, bit for bit.** On every one of the 144 scans, the device's own zone
  map (`generate_zone_map_atlas`) equalled the research zone map, and for the expert mask and the
  device-default mask of every scan (288 masks) the device's `classify_from_zone_mask` +
  `compute_dis_criteria` gave the same four region counts and the same DIS decision as the grid code.
  The run is built to stop on any disagreement; none occurred.
- 16 unit tests pass, incl. a literal port of LST-AI `annotate.py` that the LST-AI rule reproduces
  exactly on real atlas anatomy (`research/paper_d/tests/`).
- Determinism: 21 scans were computed twice (see §12); both computations were identical.
- **G1 registration QC** (`records/g1_registration_record.json`): all 144 scans registered; Dice of
  the warped atlas brain with the scan brain median 0.907 (minimum 0.782), versus 0.883 for the
  world-coordinate placement (G0). No scan fell below the pre-specified 0.70, so the QC-restricted
  sensitivity analysis equals the primary one. The two registrations place the ventricles quite
  differently (ventricle Dice G1 vs G0, median 0.59).

## 1. Cohort (primary "clean" set)

124 scans from 85 patients (MSLesSeg 114 / 75; Ljubljana patients 16–20, 26–30: 10 / 10). Reference
(device rule on the expert mask) meets brain DIS in **95.2 % (90.7–98.4)**; 6 scans do not. 3,992
expert lesions ≥ 3 mm³; expert lesion-count tertile cuts 18 and 30 lesions per scan.

## 2. P1 — flip rate vs the reference

| Pipeline | DIS differs from reference |
|---|---|
| **Device automated default** (FLAMeS fold 0, p ≥ 0.5, ≥ 3 mm³, device rule, G0) | **3.2 % (0.8–6.8)** — 4 scans: 3 false "met", 1 false "not met" |
| **LST-AI as shipped** (LST-AI ensemble, p ≥ 0.5, no size floor, LST-AI rule, LST-AI registration) | **8.1 % (3.3–13.8)** |
| Mean over the 1,120 automated pipelines | **5.3 % (2.9–8.5)** |
| Per-pipeline flip rate (min / median / max) | 0.8 % / 4.8 % / 28.2 % |
| Scans flipped by ≥ 1 automated pipeline | **38.7 % (29.1–49.2)** |

The 4 device-default errors (post hoc description): two scans with periventricular lesions only in
the reference gain one juxtacortical and one infratentorial lesion (false "met"); one scan with
juxtacortical lesions only gains periventricular and infratentorial lesions (false "met"); one scan
loses both of its periventricular lesions (false "not met"). In these 4 scans 58–95 % of the 1,120
pipelines say "met" — they are contested scans, not isolated failures.

## 3. P2 — instability across pipeline variants

| | Automated grid (1,120) | Expert-mask grid (32) |
|---|---|---|
| Not unanimous | **38.7 % (29.1–49.2)** | **4.8 % (1.5–9.2)** |
| Contested (10–90 % of pipelines say "met") | 9.7 % (5.0–15.4) | 4.0 % (0.8–8.0) |
| Pairwise disagreement (two random pipelines) | 5.4 % (3.5–7.7) | 2.1 % (0.5–4.2) |
| Mean flip vs reference | 5.3 % (2.9–8.5) | 2.0 % (0.4–4.0) |

More than a third of the scans get a different answer from at least one plausible pipeline; about one
scan in ten is genuinely contested.

## 4. S1 — drivers

Disagreement between pipelines that differ **only** in one factor (all other factors held equal):

| Factor | Disagreement |
|---|---|
| **Segmenter family** (FLAMeS fold 0 / FLAMeS ensemble / LST-AI) | **7.3 % (4.9–10.1)** |
| Registration (dataset MNI vs LST-AI deformable) | 4.0 % (2.1–6.2) |
| FLAMeS fold (which of 5 folds) | 2.9 % (1.3–4.9) |
| Probability threshold (0.3–0.7) | 1.9 % (1.3–2.6) |
| Minimum lesion size | 1.1 % (0.6–1.8) |
| Region rule (device / LST-AI × all / lateral ventricles) | 0.9 % (0.5–1.5) |

Segmenter family minus registration: **3.3 % (1.2–5.6)** — the segmenter is the single biggest driver.
On the expert mask, only the registration matters: 4.1 % (0.9–8.0); size 0.1 %, rule 0.1 %.

One factor at a time (selected; full table in the JSON):

| Change | From the device default: flip vs default | From the expert reference: flip vs reference |
|---|---|---|
| LST-AI ensemble instead of FLAMeS fold 0 | 11.3 % (6.2–17.3) | — |
| a single LST-AI U-Net | 6.5–7.3 % | — |
| another FLAMeS fold / FLAMeS ensemble | 0.8–2.4 % | — |
| threshold 0.3, 0.4, 0.6 or 0.7 | 0 % | — |
| minimum size none / 14 mm³ / 3 mm long axis | 0–0.8 % | 0 % |
| lateral ventricles only (device rule) | 0 % | 0 % |
| LST-AI rule (either ventricle definition, either order) | 1.6 % | 0 % |
| LST-AI registration (G1) | 1.6 % | 4.0 % (0.8–8.0) |
| small misregistration (G2, ≤ 2°, 2 %, 2 mm) | 0.8 % | 1.6 % |
| IFU 3 / 4 / 3 mm distances (secondary) | 1.6 % | 2.4 % |
| **majority-vote region (the device's pre-audit rule, secondary)** | **7.3 %** | **16.1 % (9.3–23.3)** |

## 5. S2 — per-region stability

| Region | Presence flip vs reference, grid mean | Presence flip, device default | ICC(A,1) counts, default vs reference | Bias, default − reference |
|---|---|---|---|---|
| Periventricular | 3.5 % (1.5–5.9) | 1.6 % | 0.79 (0.71–0.84) | +0.7 lesions |
| Juxtacortical | 3.5 % (1.6–6.1) | 2.4 % | 0.95 (0.89–0.97) | −0.3 |
| **Infratentorial** | **33.3 % (27.3–39.1)** | **27.4 % (19.8–35.5)** | 0.73 (0.61–0.80) | −0.6 |
| Deep white matter | 2.8 % | 1.6 % | 0.88 (0.75–0.94) | +3.3 |

**The infratentorial region is the fragile one**: whether any infratentorial lesion is present changes
in a third of scans across pipelines, and the device default disagrees with the reference in 34 scans
(19 lose, 15 gain the region). DIS survives this only because periventricular and juxtacortical
lesions are both present in most established-MS scans.

## 6. S3 — where fragility concentrates

| Stratum | Scans | Not unanimous | Contested | Device default flip | Expert-grid not unanimous |
|---|---|---|---|---|---|
| Expert lesions ≤ 18 (lowest tertile) | 43 | **65.1 % (48.9–80.5)** | **23.3 % (11.6–37.8)** | 9.3 % (2.1–20.4) | 14.0 % (4.7–25.6) |
| 19–30 | 40 | 40.0 % | 5.0 % | 0 % | 0 % |
| > 30 | 41 | 9.8 % | 0 % | 0 % | 0 % |
| Reference: ≤ 1 DIS region | 6 | 100 % | 66.7 % | 50 % | 83.3 % |
| Reference: 2 regions | 37 | 46.0 % | 8.1 % | 0 % | 0 % |
| Reference: 3 regions | 81 | 30.9 % | 6.2 % | 1.2 % | 1.2 % |

Fragility is a low-burden phenomenon: it is where the decision is clinically made (early MS, CIS),
which this established-MS cohort under-represents.

## 7. S4 — ventricle definition and the LST-AI rule

**Verified in code and atlas.** In the MSMask atlas (LST-AI v1; the device's atlas) label 4
"Ventricles" holds the lateral **and the third** ventricle; the fourth ventricle lies inside label 5
"Infratentorial"; the thalami are labelled white matter. Hence LST-AI v1 **and the device** count a
lesion touching the third ventricle as periventricular, against Filippi 2019 ("lesions touching the
third and fourth ventricles … should not be counted as periventricular") and against the device's own
REQ-FUNC-053 ("PV = abutting the lateral ventricles"). LST-AI v2.0.0rc1 (FastSurfer) maps the third
ventricle, aseg "CSF" and the choroid plexus to periventricular and the fourth ventricle to
infratentorial (code read only; v2 not run). Mapping the fourth ventricle to infratentorial does not
conflict with the guideline in effect (such lesions are infratentorial anyway). LST-AI's code checks
PV → JC → IT, while its paper (and v2) state PV → IT → JC.

**Quantified on 3,992 expert lesions (G0 / G1):**

| | G0 | G1 |
|---|---|---|
| Lesions touching only the third ventricle | 6 | 4 |
| Region changes, device rule → lateral-only (all PV → DWM) | 3 (0.08 %) | 4 (0.10 %) |
| Region changes, LST-AI rule → lateral-only | 6 (0.15 %) | 4 (0.10 %) |
| Lesions touching ventricle and infratentorial label (PV under LST-AI, IT under the device) | 6 | 4 |
| Lesions touching cortex and infratentorial, not ventricle (JC under LST-AI code, IT under its paper order) | 34 | 37 |
| Lesions in no zone → deep white matter **by default** under the device rule | **250 (6.3 %)** | 142 (3.6 %) |
| Scans whose DIS changes: device vs lateral-only, LST-AI vs lateral-only, LST-AI code vs paper order, device vs LST-AI | **0** each | **0** each |

**Criterion C5 not met**: the ventricle definition is wrong by the guideline but immaterial in these
cohorts (0.08 % of lesions, no DIS change). MS lesions rarely touch only the third ventricle. A larger
issue for the device is the 6.3 % of expert lesions that fall in no MSMask white-matter zone (cortical,
CSF-adjacent or misregistered) and are reported as deep white matter by default.

## 8. S5 — DIS-stability indicator (pre-specified) and post hoc signals

**Pre-specified indicator — essentially blind.** The 12 internal variants of the device default
(threshold 0.4/0.5/0.6 × size 3/14 mm³ × all/lateral ventricles) disagreed in **1 scan (0.8 %)**; that
scan was one of the 4 default errors (sensitivity 1/4 for "default ≠ reference", 1/48 for "not
unanimous"). The pivotal-lesion flag fired in 3 scans, all non-unanimous, none a default error.
Reason: threshold, size and ventricle definition barely move the decision (§4); segmenter and
registration do.

**Post hoc, in-sample, NOT pre-specified** (hypotheses for a future pre-registered validation):

| Signal | Flagged | Catches default errors | P(error \| not flagged) | PPV for "not unanimous" |
|---|---|---|---|---|
| Segmenters disagree (FLAMeS fold 0 / FLAMeS ensemble / LST-AI at default settings) | 11.3 % | 3 of 4 | 0.9 % | 14/14 |
| Thin margin (exactly 2 regions with one holding ≤ 2 lesions, or ≤ 1 region) | 9.7 % | 1 of 4 | 2.7 % | 11/12 |
| Either of the two | 18.6 % | 3 of 4 | 1.0 % | 22/23 |
| Registrations disagree (G0 vs G1) | 1.6 % | 1 of 4 | 2.5 % | 2/2 |

With only 4 errors, the error-detection figures are very uncertain (sensitivity 75 %, 95 % CI
20–100 %).

## 9. S6 — sensitivity analyses

| Set | Scans | Default flip | Grid mean flip | Not unanimous | Expert-grid not unanimous |
|---|---|---|---|---|---|
| Primary (clean) | 124 | 3.2 % | 5.3 % | 38.7 % | 4.8 % |
| + 20 FLAMeS-in-sample Ljubljana scans | 144 | 2.8 % | 4.6 % | 35.4 % | 4.2 % |
| FLAMeS-in-sample scans only | 20 | 0 % | 0.2 % | 15.0 % | 0 % |
| MSLesSeg only | 114 | 3.5 % | 5.3 % | 37.7 % | 4.4 % |
| Ljubljana clean only | 10 | 0 % | 5.8 % | 50.0 % | 10.0 % |
| DIS with ≥ 3 periventricular lesions (MAGNIMS 2016) | 124 | 7.3 % | 10.1 % | **57.3 %** | 5.7 % |
| G1 QC-restricted (Dice ≥ 0.70) | 124 | identical to primary (no scan excluded) | | | |

The in-sample scans look far more stable (15 % vs 39 % not unanimous): the contamination handling
mattered. The stricter MAGNIMS 2016 periventricular rule makes the decision markedly more fragile.

## 10. Success criteria (PROTOCOL §9)

| Criterion | Result | Verdict |
|---|---|---|
| C1 — fragile: lower bound of "not unanimous" ≥ 10 % | lower bound **29.1 %** | **met** |
| C2 — fragile with the expert mask: lower bound ≥ 2 % | lower bound **1.5 %** (estimate 4.8 %) | **not met** |
| C3 — a single biggest driver | segmenter family − registration = 3.3 % (1.2–5.6) | **met: the segmenter** |
| C4 — device default | 3.2 % (0.8–6.8) vs reference | reported, no claim |
| C5 — ventricle definition material (≥ 1 % of lesions) | 0.08 % | **not met** |

## 11. Findings about the device (for a problem report; Class C code was not touched)

1. **REQ-FUNC-053 nonconformity (HAZ-005):** the MSMask path counts lesions touching the third
   ventricle as periventricular; the requirement and Filippi 2019 say lateral ventricles only. The
   docstring of the parcellation path says "excludes 3rd/4th ventricle"; the MSMask path does not.
   Measured effect here: 0.08 % of expert lesions, no DIS change.
2. Deep grey matter is white matter in MSMask, so thalamic/caudate lesions abutting a lateral ventricle
   become periventricular (guideline exception); not quantifiable with MSMask.
3. **6.3 % of expert lesions lie in no MSMask zone and are reported as deep white matter by default**
   (flagged per lesion, but they never count towards cortical/juxtacortical DIS).
4. The device's earlier majority-vote rule would have flipped the expert-mask DIS in 16.1 % of scans —
   independent evidence supporting the contact rule introduced by the audit (#2).
5. The automated default disagrees with the expert-mask decision in 3.2 % of these scans, mostly by
   calling DIS met in scans the reference does not (3 of 4), via infratentorial and juxtacortical
   lesions; infratentorial presence is the least stable output.

Recommended: open a problem report (SPR-001) under HAZ-005 for items 1–3; decide by Class C review.

## 12. Deviations and post hoc additions

- APP-3MM (secondary rule) was built at G0 only, as it is analysed one factor at a time from the
  default (at G0). No primary number is affected.
- Registration and grid ran with 1–2 workers instead of 3–4 because the shared machine ran out of
  memory (greedy failed to allocate); failed cases were re-run. 21 scans were computed by worker
  processes after the main process had stopped and therefore lacked their device-check record; they
  were recomputed and gave identical outputs.
- **Post hoc (labelled as such in the JSON):** the post hoc stability signals of §8, the description of
  the 4 default errors (§2) and the direction of region-presence flips (§5). They were added after the
  pre-specified indicator turned out to be nearly blind.

## 13. What these results do not show

- **No radiologist has read these scans.** The reference is the device's rule on an expert lesion
  mask; "flip vs reference" is not diagnostic error. The final paper requires three
  neuroradiologists (PROTOCOL §10), prioritising the 48 non-unanimous scans.
- Established MS (95 % reference DIS met); fragility in CIS is expected to be higher (§6).
- Brain only; two single-site public cohorts; MSMask accuracy unmeasured; LST-AI v2 not run.
