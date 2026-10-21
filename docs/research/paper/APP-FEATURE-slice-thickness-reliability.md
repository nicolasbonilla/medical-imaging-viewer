# App feature (research input): "Reliability by slice thickness"

> **Status: RESEARCH INPUT, NOT A REQUIREMENT.** Nothing here is in SRS-001 or RMF-001. Before any
> implementation this must become a requirement (REQ-*), get a risk review (it changes what a
> clinician is told about how far to trust the lesion overlay — Class C territory) and a code
> review. All numbers come from Paper A v0.3 (`RESULTS-v0.3.md`, records
> `docs/research/records/2026-10-21_paper_a_v03_results.json` and `..._posthoc.json`) — 5 public
> cohorts, one segmenter (FLAMeS 5-fold ensemble), CPU research code — and must be re-derived for
> the deployed segmenter version before use. Values marked **[post hoc]** come from analyses
> written after the results were seen.
>
> *Revised 2026-10-21 after an independent re-implementation of the analysis: the first version
> of this spec presented thick-slice bands as "guarantee holds"; it now abstains on thick-slice
> studies unless the site has its own calibration.*

## 1. Purpose

A FLAIR acquired with 4–8 mm slices is still read every day. The automatic lesion list behaves
differently on such scans: fewer small lesions are found, and the "false lesions controlled at X %"
dial calibrated on thin-slice data does not carry over reliably. The feature tells the reader, per
scan, **what the automatic lesion list can and cannot be trusted for at this slice thickness**, and
withholds the false-lesion dial where the evidence does not support it.

## 2. Default behaviour (conservative)

| slice spacing (from the header) | lesion overlay | "high-confidence lesions" view with a false-lesion figure | per-scan promise |
|---|---|---|---|
| ≤ 1.5 mm **native** (3D acquisition, verified from the acquisition metadata) | shown, with the detection note of §3 | shown **only if** calibrated on patients from this site, or from 1-mm sites, with the same segmenter version | not offered (finds < 5 % of lesions) |
| > 1.5 mm native, **resampled/registered images whose native thickness is unknown**, or unknown | shown, with the thick-slice detection warning of §3 | **"Not reliable for this slice thickness" — not shown**, unless the site has its own calibration (§4) | not offered |

Rationale (v0.3): calibrated on thin-slice sites, the average false-lesion rate on thick-slice
sites was 2.6–3.2× the value obtained with local calibration (at a 10 % target: 10.7 % and 12.2 % vs
4.1 % and 3.8 %), one site was undecided (12.2 % [6.2, 19.7]), and **[post hoc]** on the third of
thick-slice scans with many false candidates it was 19.6 % [12.0, 28.2] — twice the promised 10 %.
No violation was *detected* on average, but that is not enough to display a guarantee to a reader.
The ≈ 4 mm band rests on 9 children from one site and is treated as thick.

**Read the native thickness, not the grid.** A FLAIR acquired at 3–5 mm and resampled to 1 mm (as
in MSLesSeg, the largest "1-mm" cohort of the study) shows 1-mm spacing in its header. The band must
come from the acquisition metadata (DICOM Slice Thickness / Spacing Between Slices of the original
series); if the image was resampled or registered and the original value is not available, treat it
as unknown (thick).

## 3. Detection note (no guarantee — observed detection of expert-marked lesions, before selection)

| slice spacing | lesions 3–14 mm³ | 14–50 mm³ (≈ 3–4.6 mm across) | 50–150 mm³ | 150–500 mm³ | ≥ 500 mm³ | evidence |
|---|---|---|---|---|---|---|
| ≤ 1.5 mm grid — **mostly 2–5 mm native, resampled** | 36 % | 72 % | 81 % | 87 % | 90 % | 125 scans, 2 sites (only 10 natively thin) |
| of which MSLesSeg native 2–2.3 mm **[post hoc]** | 37 % | 74 % | 86 % | 91 % | 98 % | 43 scans |
| of which MSLesSeg native 3 mm **[post hoc]** | 29 % | 65 % | 77 % | 83 % | 86 % | 52 scans |
| of which MSLesSeg native 4–5 mm **[post hoc]** | 16 % | 39 % | 73 % | 82 % | 71 % | 15 scans |
| ≈ 4 mm | 37 % | 67 % | 76 % | 77 % | 80 % | 28 scans of 9 children, 1 site |
| 4.5–6.5 mm | 13 % | 45 % | 59 % | 66 % | 76 % | 76 scans, 2 sites |
| > 6.5 mm | 21 % | 43 % | 69 % | 72 % | 70 % | 75 scans, mostly 1 site |

Wording for thick slices: *"On scans with slices thicker than 4.5 mm, about 6–7 in 10 lesions of
50 mm³ or more (≈ 4.6 mm across) and fewer than half of smaller lesions are found automatically. No
lesion size is found 8 times in 10. An empty or short list does not mean an absence of lesions."*
Within MSLesSeg alone, detection of 14–50 mm³ lesions falls from 74 % (2–2.3 mm) to 39 % (4–5 mm)
**[post hoc]**, so thickness matters even inside the "1-mm" band. These rows differ between sites as
much as between thicknesses (bands are sites), so they describe
the research data, not a calibrated property of the reader's scanner. For Muslim-like data without
reliable pixel size, the size thresholds move by about one bin (50 vs 150 mm³).

## 4. With the site's own calibration (opt-in)

A site may enable the false-lesion dial on thick-slice studies after providing **≥ 10 patients with
expert lesion masks**, acquired with the same protocol and segmented with the deployed segmenter
version. What it then gets, from the v0.3 within-site results (MS3SEG and Muslim, 1.5 T, 4.9–8.3 mm):

| setting | realised average false-lesion rate (within-site) | share of expert lesions in the high-confidence view | per-scan promise |
|---|---|---|---|
| 10 % | 4.1 % (MS3SEG), 3.8 % (Muslim) | **6 % and 1 %** | — |
| 20 % | 7.5 %, 6.9 % | **20 % and 16 %** | — |
| per-scan, γ = 0.1, δ = 0.1 | exceedance 7.5 % / 9.2 % with 10 local patients | **3.8 % and 0.6 %** | valid but nearly silent → not offered |

The card must say plainly what that leaves: *"With local calibration, the high-confidence view
lists about 1 in 5 of the lesions an expert would mark at the 20 % setting, and almost none at
10 %. The full overlay remains the primary view."*

## 5. Rules the feature must enforce

1. **Use the 5-fold ensemble, never a single fold.** It doubles the lesions found at the 20 % setting
   (sensitivity 0.10 → 0.20 leave-one-site-out); it is not a validity fix (it removed violations on
   one site and raised the false rate on another).
2. **Calibrate with the deployed segmenter version.** A different segmenter's calibration doubled
   the false rate on the same images (expected: different score scales).
3. **Thick or unknown spacing → no false-lesion figure without local calibration** (§2, §4).
4. **No per-scan promise** on any thickness in this version: where it is valid it finds < 5 % of
   lesions.
5. Show the evidence size with every number (scans, patients, sites) and "research data, not
   validated for this site".

## 6. What the feature must not claim

- Not a diagnosis, not dissemination-in-space, not lesion counting for McDonald criteria.
- No guarantee for healthy or screening populations: even pooled calibration flagged false lesions
  in 10 of 30 healthy controls at the 10 % setting (fold-0 maps; ensemble not yet tested).
- No thickness-specific guarantee: the thickness bands are confounded with site, scanner,
  population and annotation protocol.

## 7. Open items before this could become a requirement

- Ensemble maps for ≥ 100 healthy controls (pending data-access form).
- A second, independent site per thickness band, and a within-site thickness comparison.
- Per-band (Mondrian) calibration tested as a pre-registered remedy.
- Re-derivation of all tables for the exact deployed model version with the same code, and a
  version lock between the tables and the model.
- UX wording reviewed with radiologists; risk analysis of over-trust in the false-lesion figure and
  of under-reading thick-slice studies.
