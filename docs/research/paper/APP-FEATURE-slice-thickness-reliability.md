# App feature (research input): "Reliability by slice thickness"

> **Status: RESEARCH INPUT, NOT A REQUIREMENT.** Nothing here is in SRS-001 or RMF-001. Before any
> implementation this must become a requirement (REQ-*), get a risk review (it changes what a
> clinician is told about how far to trust the lesion overlay — Class C territory) and a code
> review. All numbers come from Paper A v0.3 (`RESULTS-v0.3.md`, record
> `docs/research/records/2026-10-21_paper_a_v03_results.json`) — 5 public cohorts, one segmenter
> (FLAMeS 5-fold ensemble), CPU research code — and must be re-derived for the deployed segmenter
> version before use.

## 1. Purpose

A FLAIR acquired with 4–8 mm slices is still read every day. The lesion overlay and any "false
lesions controlled at X %" claim behave differently on such scans. The feature tells the reader,
per scan, **how reliable the automatic lesion list is for this slice thickness**: which lesion sizes
are reliably found, whether the false-lesion guarantee is known to hold, and how many false lesions
to expect.

## 2. What the screen would show (one card next to the lesion list)

1. **Slice thickness band** read from the image header (slice spacing = largest voxel dimension):
   - "Thin (≤ 1.5 mm, 3D)" · "≈ 4 mm 2D" · "4.5–6.5 mm 2D" · "> 6.5 mm 2D" · "Unknown → treated as
     > 6.5 mm".
2. **Smallest lesion reliably detected** (automatic segmentation, before any selection), from
   Table A: e.g. "Lesions ≥ 50 mm³ (≈ 4.6 mm across) are found about 8 times in 10" for thin
   scans; "No lesion size is found 8 times in 10; lesions ≥ 50 mm³ are found about 6–7 times in 10"
   for > 6.5 mm.
3. **False-lesion guarantee status** for the "high-confidence lesions" view (conformal selection,
   P1) at the two offered settings (10 % and 20 % false lesions on average):
   - "Holds (tested on N patients from other sites)" / "Holds, but almost nothing is selected" /
     "Not established".
4. **Expected counts per scan at that setting**: false and true lesions in the high-confidence
   view (Table A).
5. **Per-scan promise** (P2, "at most 1 in 10 scans exceeds γ false lesions"): shown only when the
   site has its own calibration (≥ 10 local patients with expert masks); otherwise "Not available
   for this thickness without local calibration".
6. A fixed footnote: "Based on 304 research scans from 5 public cohorts (Italy, Slovenia, Iran,
   Iraq and one paediatric cohort); one segmenter; not validated for this site."

## 3. Table A — values the card would use (FLAMeS 5-fold ensemble, leave-one-site-out calibration)

| band | evidence (scans / patients; sites) | raw detection ≥ 80 % from | raw detection ≥ 50 % from | P1 at 10 % → status · realised · lesions found · false / true per scan | P1 at 20 % → status · realised · lesions found · false / true per scan | P2 (per-scan) without local calibration |
|---|---|---|---|---|---|---|
| Thin ≤ 1.5 mm | 125 / 85; MSLesSeg, Ljubljana | 50 mm³ (≈ 4.6 mm) | 14 mm³ (≈ 3 mm) | holds, almost silent · 0.8 % · 1 % · 0.01 / 0.3 | holds · 1.8 % · 9 % · 0.13 / 3.0 | holds, almost silent (0.2 % found) |
| ≈ 4 mm 2D | 28 / 9 children; PediMS | not reached (max 0.80 at ≥ 500 mm³) | 14 mm³ | holds · 0.7 % · 6 % · 0.07 / 2.5 | holds · 5.0 % · 16 % · 0.50 / 6.5 | holds, almost silent (2.5 % found) |
| 4.5–6.5 mm 2D | 76 / 76; Muslim, MS3SEG | not reached (max 0.76) | 50 mm³ (≈ 4.6 mm) | holds · 8.4 % · 11 % · 0.45 / 3.8 | holds · 10.1 % · 24 % · 0.88 / 7.9 | not established (16 % of scans exceed vs 10 %) |
| > 6.5 mm 2D | 75 / 75; MS3SEG, Muslim | not reached (max 0.72) | 50 mm³ | holds · 8.7 % · 17 % · 0.63 / 5.9 | holds · 12.0 % · 36 % · 1.73 / 12.4 | not established (17 % exceed) |

"Holds" = protocol class *holds* (upper 95 % bound ≤ target + 5 points). Per the pre-registered
rule a band is labelled "guarantee holds" only if both settings hold **with** selections — this
excludes the thin band (silent at 10 % under foreign calibration; with its own site's calibration
it selects: MSLesSeg within-site realised 1.6 %, 10 % of lesions found).

**Per-scan exceedance rises with thickness** even where the average holds: at the 20 % setting,
the share of scans with more than 10 % false lesions is 6 % (thin), 14 % (≈ 4 mm), 30 %
(4.5–6.5 mm), 49 % (> 6.5 mm). The card should say so for thick bands: "on average within target;
individual scans vary more".

## 4. Rules the feature must enforce (derived from the v0.3 results)

1. **Use the 5-fold ensemble, never a single fold.** With fold 0 alone the guarantee was violated
   on MS3SEG (realised 20 % at a 10 % target) and lesion-level sensitivity at the guarantee halved.
2. **Calibrate with the deployed segmenter.** Calibrating on another segmenter's candidates broke
   the guarantee (LST-AI-calibrated → FLAMeS: 21 % realised at a 10 % target).
3. **No per-scan promise on thick slices without local calibration**: the per-scan threshold
   calibrated on thin scans was exceeded on 21 % (MS3SEG) and 29 % (Muslim) of scans (target 10 %;
   PediMS 7 %, inconclusive). With
   ≥ 10 local patients it was restored (MS3SEG: 7.5 %), but mixing local patients into a large
   foreign pool did not restore it.
4. **Local calibration size**: the average guarantee needs no minimum, but ~10 local patients
   recover ~90 % of the achievable power; fewer than 9 means the per-scan promise must abstain.
5. **Unknown or implausible slice spacing → most conservative band.** Muslim-like data without
   reliable pixel size: the minimum-size statement moved between 50 and 150 mm³ with a ±10 % volume
   error; show the range.
6. **Children**: the ≈ 4 mm band rests on 9 children (28 scans) — show "limited evidence".

## 5. What the feature must not claim

- Not a diagnosis, not dissemination-in-space, not lesion counting for McDonald criteria.
- No guarantee for healthy or screening populations: even pooled calibration flagged false lesions
  in 10 of 30 healthy controls at the 10 % setting (fold-0 maps; ensemble not yet tested on
  controls).
- No claim for scanners, populations or annotation protocols outside the five cohorts; bands are
  confounded with site and annotation protocol.

## 6. Open items before this could become a requirement

- Ensemble maps for ≥ 100 healthy controls (pending data-access form).
- A second site per thickness band (bands B2–B4 rest on 1–2 sites each).
- Re-derivation of Table A for the exact deployed model version, with the same pre-registered code
  (`research/paper_a/v03_analysis.py`), and a version lock between Table A and the model.
- UX wording reviewed with radiologists; risk analysis of over-trust in "holds".
