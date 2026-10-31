# Paper A v0.3 — Results of the pre-registered multi-site analysis

*Research code and research findings, not the medical device. Date: 2026-10-21.*

- Protocol: `docs/research/paper/PROTOCOL-v0.3.md` — committed before any outcome (9951494);
  implementation clarifications 1–4 (c0c5fa1) and the gate-G1 deviation 5 (50c9b08) were logged
  before any outcome was computed; entry 6 (transparency, after results) and entry 7 (a 3-case
  thick-slice pilot of 2026-10-18 that preceded the protocol) are disclosed there.
- Records: `docs/research/records/2026-10-21_paper_a_v03_*.json` (+ `_output.txt`): inventory
  (input SHA-256), candidates (cache SHA-256, gate G1), results (all pre-registered numbers below),
  post-hoc (explanatory checks written **after** the results were seen — every use below is marked
  **[post hoc]**).
- Code: `research/paper_a/v03_{data,inventory,candidates,metrics,analysis,posthoc}.py`; tests
  `research/paper_a/test_v03_metrics.py` (33 pass).
- **Revision 2026-10-21 (after an independent re-implementation).** A separate re-implementation
  reproduced the candidates (e.g. MS3SEG 3402 candidates / 1162 false) and every primary rate to
  three decimals and found no leakage between calibration and test patients. It also showed that
  several statements in the first version of this file overclaimed; they are corrected below
  ("no violation detected" instead of "held"; per-scan failure intervals; thickness confounded with
  site; the ensemble's effect on validity is mixed; recalibration of the per-scan promise works by
  near-abstention). One post-hoc check was added (§2, scans with many false candidates).
- **Terminology correction (2026-10-21):** "1-mm sites" / band "≤ 1.5 mm" means *delivered on a
  1-mm grid*. MSLesSeg was acquired with 2–5 mm FLAIR slices and resampled to MNI 1 mm; only
  Ljubljana is natively thin (§3, note on MSLesSeg).
- **Healthy-control addendum (2026-10-24).** §6 now reports 100 distinct SibBMS healthy controls
  with both arms, under a separate pre-registration (`PROTOCOL-v0.3-addendum-controls.md`,
  commit caa47e7, before any control outcome); records `2026-10-24_paper_a_v03c_*`. It replaces the
  30-control, fold-0-only Table 7 of the first v0.3 text.
- Arms: **ens** = 5-fold FLAMeS mean probability (primary); **f0** = fold 0 alone (= the v0.1/v0.2
  pipeline). P1 = conformal BH (FDR target α); P2 = scan-conformal FDX threshold (target
  P(FDP > γ) ≤ δ = 0.1). "Realised FDR" = mean per-scan FDP; "FDX" = share of test scans with
  FDP > γ. Intervals are 95 % patient-cluster bootstrap (FDX: union with exact Clopper–Pearson).
  Cell classes (protocol §9): *violated* = CI lower bound > nominal; *holds* = CI upper bound ≤
  nominal + 0.05 (**a "holds" cell may have a point estimate above nominal; "holds" means "no
  violation detected and the upper bound is within the margin", not "the guarantee is proven"**);
  otherwise *inconclusive*; "uninf." = holds only through abstention (< 10 selections or
  end-to-end sensitivity < 0.05).

---

## 0. Bottom line

1. **No violation of marginal lesion-FDR control (P1) was detected in the 16 held-out-site
   cells** (1-mm → thick-slice and leave-one-site-out). That is weaker than "the guarantee held":
   on Muslim at α = 0.1 the result is undecided (0.122 [0.062, 0.197]); 3 of the 16 cells pass only
   because almost nothing is selected (MSLesSeg, Ljubljana and Muslim at α = 0.1, leave-one-site-out);
   PediMS (9 patients) and Ljubljana (10) are underpowered; on MS3SEG at α = 0.1 the estimate
   (0.107 [0.074, 0.145]) is above nominal and passes only through the pre-registered margin.
   **The calibration does not transfer as such**: on the two large thick-slice sites the realised
   FDR at α = 0.1 is 2.6–3.2× the within-site value (MS3SEG 0.107 vs 0.041; Muslim 0.122 vs 0.038),
   which itself sits near α·π0 **[post hoc]** (π0 = share of false candidates, 0.34–0.37), as
   conformal BH predicts under exchangeability. Exchangeability is broken; the average bound survives because lesion-rich
   scans (many true candidates) dilute the false selections. **[post hoc]** On the third of
   MS3SEG + Muslim scans with ≥ 40 % false candidates (51 of 151), realised FDR at α = 0.1 is
   0.196 [0.120, 0.282] with 1-mm calibration vs 0.050 [0.011, 0.103] with within-site calibration.
   Pre-registered verdict for Q1/P1: **inconclusive**.
2. **Per-scan exceedance control (P2) does not transport from 1-mm to thick-slice sites**: with a
   threshold calibrated on MSLesSeg + Ljubljana, 21 % [13, 30] of MS3SEG scans (γ = 0.1) and
   29 % [17, 44] / 27 % [16, 42] of Muslim scans (γ = 0.1 / 0.2) had FDP above γ, against a 10 %
   budget. Only the Muslim γ = 0.1 cell remains violated after correction for the 32 primary
   comparisons; when calibration patients are re-drawn too (two-level bootstrap) the MS3SEG lower
   bound falls to 0.10, i.e. no longer a detected violation. Verdict Q1/P2 by the pre-registered
   rule: **refuted** (on the strength of Muslim; MS3SEG is borderline).
3. **Slice thickness: a gradient, confounded with site** — and the thin band is not natively thin:
   MSLesSeg (110 of its 125 scans) was acquired at 2–5 mm and resampled to 1 mm. Under leave-one-site-out calibration,
   realised FDR at α = 0.2 is 0.018 (≤ 1.5 mm), 0.050 (3.9 mm), 0.101 (4.5–6.5 mm), 0.120 (> 6.5 mm)
   and the share of scans with FDP > 0.1 is 6 %, 14 %, 30 %, 49 %. Each band is essentially one or
   two sites, and within a site the gradient is small (MS3SEG 4.5–6.5 → > 6.5 mm: 0.103 → 0.121;
   Muslim 0.099 → 0.102 with only 6 scans above 6.5 mm), so this is mostly a between-site
   difference, not a demonstrated thickness effect. Raw detection on thick slices: lesions
   ≥ 50 mm³ (≈ 4.6 mm across) are found 59–76 % of the time depending on size bin; smaller lesions
   (14–50 mm³) 43–45 %; no size reaches 80 %. On 1-mm scans 80 % is reached from 50 mm³.
4. **The 5-fold ensemble: a large power gain, a mixed effect on validity.** Candidate AUROC rises
   from 0.67–0.76 (any single fold) to 0.78–0.82 at every site; at α = 0.2 end-to-end sensitivity
   doubles (leave-one-site-out 0.102 → 0.203, Δ +0.10 [0.075, 0.129]; 1-mm → thick 0.194 → 0.341).
   At α = 0.1 the leave-one-site-out gain is only about 3 points (0.053 → 0.082, Δ +0.028
   [0.016, 0.042]). Validity is **not** uniformly better: the ensemble removes the fold-0
   violations on MS3SEG (fold 0, 1-mm → thick, α = 0.1: 0.201 [0.166, 0.242]) but **raises** realised
   FDR on Muslim (1-mm → thick, α = 0.1: 0.122 vs 0.051, Δ +0.070 [0.012, 0.143]; fold 0 there
   selects almost nothing) and creates 2 new violated cells (Muslim, P2). Pre-registered verdict Q3:
   "helps on power, but with new violated cells".
5. **Per-site recalibration restores validity — for the per-scan promise mostly by abstaining.**
   Within-site P1 stayed below α on average at every calibration size, and 10 local patients reach
   ~90 % of the within-site power (α = 0.2: sensitivity 0.18 on MS3SEG, 0.15 on Muslim). P2 needs
   ≥ 9 local patients (δ = 0.1); with 10 its FDX is 0.075 on MS3SEG and 0.092 on Muslim, **but it then
   finds 3.8 % (MS3SEG) and 0.6 % (Muslim) of lesions** — validity restored by near-abstention.
   Adding the local patients to the 1-mm pool never restored P2 (FDX 0.16–0.28 for k ≤ 40).
6. **Segmenter swap (same MSLesSeg images, FLAMeS vs LST-AI)**: LST-AI-calibrated selection on
   FLAMeS candidates gave realised FDR 0.207 [0.175, 0.240] at α = 0.1; the other direction selected
   nothing. This was expected — the two segmenters' scores live on different scales (mean false-
   candidate score 0.65 for LST-AI vs 0.76 for FLAMeS) — and it was tested on one site only; it
   illustrates the rule "calibrate with the deployed segmenter" rather than adding a new finding.
7. **Power remains the cost**: at the guarantee, end-to-end lesion sensitivity is 0.01–0.40
   depending on site, design and α; per-scan (P2) selection finds 0.1–12 % of lesions.
8. **Healthy brains (addendum, 100 controls, one site, template-normalised).** On a lesion-free scan
   the FDR promise becomes "P(≥ 1 reported lesion) ≤ α". With the 1-mm-site calibration the ensemble
   reported ≥ 1 lesion in **14/100 healthy controls at α = 0.1 (95 % CI 7.9–22.4 %)** and **24/100
   at α = 0.2 (16.0–33.6 %)**: both *inconclusive* by the pre-registered rule, with point estimates
   above nominal. The per-scan threshold P2 reported a lesion in 6/100 (2.2–12.6 %, *holds*), but it
   finds almost no lesions in patients either. **Fold 0 fails badly** on healthy brains (59/100 at
   α = 0.1). **Without selection, the automatic segmentation shows ≥ 1 lesion in 85/100 healthy
   brains and meets the app's brain dissemination-in-space rule in 19/100 (11.8–28.1 %)**; with
   selection, 0–3/100. The old "0/200 (≤ 1.8 %)" / "0/30 (≤ 9.5 %)" healthy-DIS statements are
   replaced by these numbers.

---

## 1. Data, gates and score quality

**Inventory (gate G0).** 324 cases × (5 FLAMeS folds + expert mask), 144 × LST-AI (ensemble + 3
sub-models) and 30 controls opened (the 100-control addendum has its own gate C0, §6); every map matches its mask's grid; SHA-256 of every input in
`2026-10-21_paper_a_v03_inventory.json`. The new fold-0 maps reproduce the August fold-0 maps
(145 scans; max |Δp| 0.0022; 6 voxels in 5 scans change side of 0.5).
**Pipeline reproduction (gate G1).** Fold-0 candidates vs v0.2's cache: counts identical in
125/125 scans, one-to-one labels identical for 4400/4400 candidates, score differences ≤ 0.0017
outside the 5 boundary-voxel scans; one candidate inside them differs by 0.0078 → strict criterion
failed on that candidate, deviation 5 logged before any outcome.

**Table 1. Cohorts (ensemble arm; one-to-one lenient labels).**

| site | scans / patients | slice spacing (mm) | candidates | false | candidate precision | detectable expert lesions | raw lesion sensitivity | AUROC ens [95 % CI] | AUROC fold 0 |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| MSLesSeg | 115 / 75 | MNI 1 mm; native 2–5 mm | 3788 | 1257 | 0.668 | 3344 | 0.757 | 0.818 [0.798, 0.837] | 0.735 [0.708, 0.761] |
| Ljubljana clean 10 | 10 / 10 | MNI 1 mm; native 3D 0.8 mm | 517 | 82 | 0.841 | 667 | 0.652 | 0.802 [0.729, 0.883] | 0.698 [0.625, 0.773] |
| MS3SEG | 100 / 100 | 6.0–8.1 (med. 7.2) | 3402 | 1162 | 0.658 | 3354 | 0.668 | 0.802 [0.786, 0.816] | 0.720 [0.701, 0.737] |
| Muslim | 51 / 51 | 4.86–8.3 (med. 6.0) | 1540 | 568 | 0.631 | 1819 | 0.534 | 0.784 [0.741, 0.822] | 0.746 [0.710, 0.782] |
| PediMS | 28 / 9 | 3.9 | 1110 | 321 | 0.711 | 1104 | 0.715 | 0.801 [0.774, 0.864] | 0.698 [0.679, 0.768] |

Folds 1–4 individually: AUROC 0.67–0.76 at every site (record `q3.auroc`). Fold disagreement alone
(−SD of the five per-fold candidate means) has AUROC 0.77–0.81, as high as the ensemble mean.

## 2. Q1 — Does the guarantee hold on held-out sites? (primary)

**Table 2. The 32 primary cells (ensemble arm).** D3 = calibrate on MSLesSeg + Ljubljana-10, test
on each thick site; D2 = leave-one-site-out. Entries: realised value [95 % CI] → class; end-to-end
sensitivity; selections.

| design · site | P1 α = 0.1 (FDR) | P1 α = 0.2 (FDR) | P2 γ = 0.1 (FDX vs 0.1) | P2 γ = 0.2 (FDX vs 0.1) |
|---|---|---|---|---|
| D3 · MS3SEG | 0.107 [0.074, 0.145] holds (point > α); sens 0.258; 957 | 0.123 [0.099, 0.151] holds; 0.404; 1545 | **0.21 [0.13, 0.30] violated**; 0.121; 436 | 0.12 [0.06, 0.20] inconcl.; 0.121 |
| D3 · Muslim | 0.122 [0.062, 0.197] **inconclusive**; 0.095; 195 | 0.097 [0.058, 0.146] holds; 0.235; 471 | **0.29 [0.17, 0.44] violated**; 0.036; 81 | **0.27 [0.16, 0.42] violated**; 0.036 |
| D3 · PediMS | 0.041 [0.009, 0.102] holds; 0.120; 139 | 0.086 [0.056, 0.122] holds; 0.326; 399 | 0.07 [0.00, 0.24] inconcl.; 0.053; 60 | 0.07 [0.00, 0.24] inconcl. |
| D2 · MSLesSeg | 0.009 [0.000, 0.029] holds, uninf.; 0.010; 34 | 0.018 [0.004, 0.042] holds; 0.089; 312 | 0.02 [0.00, 0.06] holds, uninf.; 0.001; 4 | 0.03 [0.00, 0.07] holds, uninf. |
| D2 · Ljubljana-10 | 0.000 [0, 0] holds, uninf.; 0.009; 6 | 0.011 [0.000, 0.033] holds; 0.118; 80 | 0.00 [0.00, 0.31] inconcl., uninf. | same |
| D2 · MS3SEG | 0.087 [0.059, 0.121] holds; 0.201; 744 | 0.116 [0.093, 0.142] holds; 0.381; 1453 | 0.16 [0.09, 0.25] inconcl.; 0.087; 316 | 0.12 [0.06, 0.20] inconcl. |
| D2 · Muslim | 0.082 [0.033, 0.137] holds, uninf.; 0.030; 66 | 0.100 [0.048, 0.163] holds; 0.139; 276 | 0.18 [0.08, 0.31] inconcl., uninf. | same |
| D2 · PediMS | 0.007 [0.000, 0.022] holds; 0.064; 73 | 0.050 [0.016, 0.093] holds; 0.164; 195 | 0.00 [0.00, 0.12] holds, uninf. | same |

- **Multiplicity** (Bonferroni intervals, 20 000 resamples): no P1 cell is violated; of the P2
  cells only Muslim γ = 0.1 stays *violated* (Bonferroni CI [0.12, 0.52]).
- **Two-level bootstrap** (calibration and test patients resampled — the marginal view):
  D3 MS3SEG P1 α = 0.1 0.101 [0.070, 0.136]; Muslim P1 α = 0.1 0.104 [0.042, 0.182]; MS3SEG P2
  γ = 0.1 0.20 [0.10, 0.30]; Muslim P2 γ = 0.1 / 0.2 0.27 [0.12, 0.41] / 0.25 [0.12, 0.37]. The
  MS3SEG P2 lower bound falls to the nominal 0.10, so in this marginal view the MS3SEG violation is
  no longer detected; the Muslim P2 violations remain.
- **Verdicts (protocol §10):** P1 — *inconclusive* (no violation detected; MS3SEG within margin
  with a point estimate above α; Muslim α = 0.1 undecided; 3 of 16 cells pass only by abstention;
  Ljubljana-10 and PediMS-9 underpowered). P2 — *refuted* (MS3SEG γ = 0.1 and Muslim γ = 0.1, 0.2
  violated; only Muslim γ = 0.1 survives Bonferroni; MS3SEG borderline in the two-level view).
- **The calibration does not transfer as such.** With within-site calibration (D1) the realised
  FDR at α = 0.1 is 0.041 (MS3SEG) and 0.038 (Muslim), close to **[post hoc]** α·π0 = 0.034 / 0.037
  (π0 = share of false candidates; conformal BH attains α·π0 under exchangeability). With 1-mm calibration it is
  0.107 and 0.122, i.e. 2.6–3.2× higher: the false-candidate scores of thick-slice scans are not
  exchangeable with the 1-mm null, and the average bound survives only because many scans are
  lesion-rich, so their false selections are diluted by true ones. **[post hoc]** Restricting to
  the third of MS3SEG + Muslim scans with ≥ 40 % false candidates (51 of 151 scans, mean π0 0.52):
  realised FDR at α = 0.1 is **0.196 [0.120, 0.282]** with 1-mm calibration vs 0.050 [0.011, 0.103]
  with within-site calibration (α = 0.2: 0.169 [0.119, 0.229] vs 0.125 [0.071, 0.192]); with ≥ 50 %
  false candidates (24 scans): 0.225 [0.101, 0.366] at α = 0.1. The guarantee is a mixture
  statement over scans; on low-lesion-load thick-slice scans the 1-mm calibration does not deliver
  it. (The independent re-implementation, with a different within-site fold split, found the same
  pattern: ≈ 0.20 vs ≈ 0.07.)
- **Why P2 fails and P1 does not [post hoc].** P2 is a single threshold (0.965 when
  calibrated on the 1-mm sites). The share of scans with a false candidate above 0.965 is 6 %
  (MSLesSeg) and 10 % (Ljubljana) but 24 % (MS3SEG) and 29 % (Muslim) — the realised FDX almost
  exactly. Thick-slice sites produce more very-confident false candidates (pre-registered
  scan-clustered KS test of the false-score law vs the 1-mm sites: MS3SEG D = 0.107, p = 0.0005; Muslim D = 0.094,
  p = 0.025; PediMS D = 0.057, p = 0.51). P1 calibrates on the whole false-score law and controls
  only the expected FDP, which absorbs the shift with less slack lost.
- **Strict matching (IoU ≥ 0.10) and PediMS without patient P9** leave every primary class
  unchanged. With the **fold-consensus score** S_cons (secondary score), every D3 P1 cell holds
  (Muslim α = 0.1: 0.068 [0.026, 0.122]) and no P2 cell is violated (MS3SEG γ = 0.1: 0.14
  [0.08, 0.22], inconclusive), at a modest power cost (D3, α = 0.2: sensitivity 0.296 vs 0.341).
  This is a sensitivity analysis, not the primary result.

**Baselines in D3 (α = 0.1 / 0.2; realised FDR; pre-registered).** Precision-matched threshold (B1): MS3SEG
0.164 [0.136, 0.196] / 0.230 [0.206, 0.255] — **violated at both**; Muslim 0.144 [0.107, 0.180]
— **violated** / 0.235; PediMS 0.106 / 0.197. Conformal risk control (B2): MS3SEG 0.072 / 0.129;
**Muslim 0.180 [0.103, 0.265] at α = 0.1 — violated**; PediMS 0.069 / 0.098. Learn-then-Test (B3):
MS3SEG 0.083 / 0.181; Muslim 0.134 [0.062, 0.226] / 0.159; PediMS 0.000 / 0.114. ~~Conformal BH (P1)
is the only procedure with no violated D3 cell.~~ **Corrected 2026-10-31:** Learn-then-Test (B3) had no
violated D3 (or D2) cell either; conformal BH and B3 are the two procedures without one (journal manuscript §6.4).

**1-mm sites under foreign calibration are over-conservative.** Leave-one-site-out and thick →
1-mm calibration made MSLesSeg nearly silent (P1 α = 0.1: 34 selections, sensitivity 0.010;
within-site D1: 358 selections, 0.102): the thick sites' heavier false-score tail inflates the
null. The guarantee is safe there, but useless.

## 3. Q2 — Validity and power by slice thickness

**Table 3. By thickness band, leave-one-site-out calibration (D2), ensemble arm.** The pooled
5-fold design (D4) gives the same pattern (record `thickness.D4|by_band`).

| band (slice spacing) | scans / patients (sites) | P1 α = 0.1: FDR · sens. | P1 α = 0.2: FDR [CI] · scans FDP > 0.1 · sens. [CI] · false / true lesions per scan | P2 γ = 0.1: FDX [CI] · sens. |
|---|---|---|---|---|
| B1 ≤ 1.5 mm grid (native: 10 at 0.8 mm, 110 at 2–5 mm, 5 unknown) | 125 / 85 (MSLesSeg, Ljubljana) | 0.008 · 0.010 (uninf.) | 0.018 [0.004, 0.040] · 6 % · 0.094 [0.053, 0.141] · 0.13 / 3.0 | 0.016 [0.002, 0.057] · 0.002 (uninf.) |
| B2 3.9 mm | 28 / 9 (PediMS) | 0.007 · 0.064 | 0.050 [0.016, 0.093] · 14 % · 0.164 [0.042, 0.440] · 0.50 / 6.5 | 0.000 [0, 0.12] · 0.025 (uninf.) |
| B3 4.5–6.5 mm | 76 / 76 (Muslim 45, MS3SEG 31) | 0.084 · 0.112 | 0.101 [0.063, 0.145] · 30 % · 0.236 [0.180, 0.298] · 0.88 / 7.9 | 0.158 [0.079, 0.260] · 0.047 (inconcl.) |
| B4 > 6.5 mm | 75 / 75 (MS3SEG 69, Muslim 6) | 0.087 · 0.170 | 0.120 [0.093, 0.152] · 49 % · 0.355 [0.310, 0.402] · 1.73 / 12.4 | 0.173 [0.093, 0.278] · 0.077 (inconcl.) |

**MSLesSeg is not natively 1 mm (correction, 2026-10-21, post hoc).** The dataset's own
acquisition table (`info_dataset/patient_scanners_info/patient_scanners_info_FLAIR.csv`, distributed
with the public MSLesSeg release [Rondinella/Guarnera et al., Sci Data 2025]; SHA-256 958ca1e9…)
lists native FLAIR slice thicknesses of 2–2.3 mm (43 of our 115 scans), 3 mm (52), 4–5 mm (15) and
unknown (5), on 8 scanner models (Philips, GE, Siemens), with both long-TR (8000–11000 ms, 2D-type)
and short-TR/long-TE (4800 ms, ~300 ms, 3D-type) sequences. The public images are registered and
resampled to MNI 1 mm. The "≤ 1.5 mm" band (B1) is therefore **"delivered on a 1-mm grid"**: only the
10 Ljubljana scans are natively thin (3D FLAIR 0.47 × 0.47 × 0.8 mm); 110 of the 125 B1 scans were
acquired at 2–5 mm. Throughout these documents "1-mm sites" means "sites delivered on a 1-mm grid".
This further confounds the thickness analysis: B1 vs B2–B4 compares resampled 2–5 mm (plus 10 thin)
acquisitions with natively stored 3.9–8.3 mm acquisitions. **[post hoc]** Within MSLesSeg, raw
detection of 14–50 mm³ lesions falls with native thickness — 0.74 (2–2.3 mm, 43 scans), 0.65 (3 mm,
52), 0.39 (4–5 mm, 15); lesions ≥ 50 mm³: 0.86–0.98, 0.77–0.86, 0.71–0.82 — a within-site gradient
in detection (confounded with scanner and patient), recorded in
`2026-10-21_paper_a_v03_mslesseg_native.json` (`research/paper_a/v03_mslesseg_native.py`).

No P1 band cell shows a detected violation; the slack shrinks across bands and the per-scan
exceedance grows. **This ordering is confounded with site**: B1 is MSLesSeg + Ljubljana, B2 is
PediMS alone, B3/B4 are MS3SEG and Muslim. Within a site the gradient is small (pre-registered
site × band cells, α = 0.2: MS3SEG 4.5–6.5 mm → > 6.5 mm 0.103 → 0.121; Muslim 0.099 → 0.102, with
only 6 Muslim scans above 6.5 mm), and **[post hoc]** per-scan FDP does not trend with slice
spacing within MS3SEG (6.0–8.1 mm; Spearman ρ = 0.03, p = 0.75; Muslim ρ = 0.30, p = 0.035 on 6
scans above 6.5 mm). The band table therefore describes these sites, not a controlled thickness
effect. Power grows across bands too — **[post hoc]** thick-slice expert lesions are larger
(median 108–117 mm³ vs 68 mm³ on MSLesSeg and 20 mm³ on Ljubljana) — and the 1-mm band is
penalised by the foreign null.

**Table 4. Expert-lesion sensitivity by lesion volume and band** (raw = matched by any candidate,
no selection; "at guarantee" = selected by P1 α = 0.2, D2). Bins: [3, 14), [14, 50), [50, 150),
[150, 500), ≥ 500 mm³ (equivalent sphere diameter ≈ 1.8–3, 3–4.6, 4.6–6.6, 6.6–9.8, ≥ 9.8 mm).

| band | lesions per bin | raw sensitivity | at guarantee | smallest bin from which raw ≥ 0.8 / ≥ 0.5 | at guarantee ≥ 0.5 |
|---|---|---|---|---|---|
| B1 ≤ 1.5 mm grid (mostly 2–5 mm native) | 531 / 1217 / 1327 / 610 / 326 | 0.36 / 0.72 / 0.81 / 0.87 / 0.90 | 0.02 / 0.04 / 0.09 / 0.20 / 0.21 | **50 mm³** / 14 mm³ | never |
| B2 3.9 mm | 75 / 324 / 378 / 234 / 93 | 0.37 / 0.67 / 0.76 / 0.77 / 0.80 (0.796) | 0.03 / 0.08 / 0.19 / 0.22 / 0.33 | **never** / 14 mm³ | never |
| B3 4.5–6.5 mm | 48 / 514 / 976 / 673 / 343 | 0.13 / 0.45 / 0.59 / 0.66 / 0.76 | 0.00 / 0.10 / 0.23 / 0.30 / 0.38 | **never** / 50 mm³ | never |
| B4 > 6.5 mm | 34 / 455 / 1074 / 713 / 343 | 0.21 / 0.43 / 0.69 / 0.72 / 0.70 | 0.06 / 0.10 / 0.32 / 0.48 / 0.56 | **never** / 50 mm³ | 500 mm³ |

Reading the raw column correctly: on thick slices lesions ≥ 50 mm³ are found **59–76 %** of the
time (by bin), lesions of 14–50 mm³ 43–45 %, lesions < 14 mm³ 13–21 %; "≥ 50 mm³" is where detection
first exceeds one half, not where it is one half. Muslim's estimated pixel size moves its own
50 %-detection size: 50 mm³ at nominal and × 0.9
volumes, 150 mm³ at × 1.1 (the 50–150 mm³ bin falls to 0.487). The PediMS 3.9-mm band misses
0.8 by 0.004 on 93 lesions — read it as "about 80 % for lesions ≥ 500 mm³".

## 4. Q3 — 5-fold ensemble vs fold 0

**Table 5. Ensemble minus fold 0, same scans and expert lesions (patient-paired bootstrap).**

| design · test set | P1 α = 0.2 realised FDR: ens / f0 [Δ CI] | P1 α = 0.2 end-to-end sensitivity: ens / f0 [Δ CI] |
|---|---|---|
| D3 · thick (all) | 0.110 / 0.178 [−0.098, −0.037] | 0.341 / 0.194 [+0.117, +0.177] |
| D3 · MS3SEG | 0.123 / 0.225 [−0.131, −0.074] | 0.404 / 0.282 [+0.087, +0.153] |
| D3 · Muslim | 0.097 / 0.122 [−0.104, +0.053] | 0.235 / 0.080 [+0.096, +0.216] |
| D3 · PediMS | 0.086 / 0.110 [−0.094, +0.030] | 0.326 / 0.112 [+0.143, +0.240] |
| D2 · all sites | 0.067 / 0.084 [−0.034, −0.000] | 0.203 / 0.102 [+0.074, +0.129] |
| D1 · all sites (within-site) | 0.061 / 0.085 [−0.045, −0.004] | 0.219 / 0.078 [+0.108, +0.178] |
| D4 · all sites (pooled) | 0.063 / 0.070 [−0.025, +0.011] | 0.196 / 0.069 [+0.096, +0.157] |

- **At α = 0.1 the power gain is small and validity moves both ways** (same paired bootstrap):
  leave-one-site-out, all sites: sensitivity 0.082 vs 0.053 (Δ +0.028 [0.016, 0.042], about 3
  points), realised FDR 0.046 vs 0.068; 1-mm → thick, all thick sites: sensitivity 0.187 vs 0.111
  (Δ +0.076 [0.050, 0.106]), FDR 0.101 vs 0.136. **On Muslim the ensemble raises realised FDR**:
  1-mm → thick α = 0.1, 0.122 vs 0.051 (Δ +0.070 [0.012, 0.143]); leave-one-site-out α = 0.1, 0.082
  vs 0.020 (Δ [0.017, 0.121]) and α = 0.2, 0.100 vs 0.044 (Δ [0.006, 0.116]) — fold 0 there selects
  almost nothing (sensitivity 0.002–0.035), so its low FDR is partly abstention, but the ensemble
  is not "safer" on that site.
- **Fold-0 primary cells** (same 32 cells, record `q3.f0_primary_cells`): MS3SEG is violated in
  D3 P1 α = 0.1 (0.201 [0.166, 0.242]), D2 P1 α = 0.1 (0.176 [0.139, 0.216]) and in every MS3SEG
  P2 cell (FDX 0.39–0.62; D3 γ = 0.1 is violated with both arms); D3 P1 α = 0.2 is 0.225
  [0.193, 0.260]. The ensemble removes 5 violated cells (all MS3SEG) and **creates 2 new ones**
  (Muslim P2, D3; fold 0 there: FDX 0.16 / 0.12, inconclusive, at sensitivity 0.024).
  Pre-registered verdict: **"helps on power, but with new violated cell(s)"** — the ensemble is a
  large power improvement, not a validity fix.
- Folds 1–4 behave like fold 0 (D3, P1 α = 0.2: realised FDR 0.157–0.176, sensitivity 0.19–0.25),
  so fold 0 is typical, and the gain comes from averaging.
- Mechanism **[post hoc]**: the share of false candidates scoring ≥ 0.95 drops from 16–32 % (fold 0)
  to 3–6 % (ensemble) at every site (MS3SEG 32 % → 6 %); the ICC of false-candidate scores within
  scans drops too (fold 0 0.05–0.19, ensemble −0.01–0.10).
- LST-AI replicates the direction but not the mechanism: its 3-model ensemble does not rank better
  than sub-model 1 (MSLesSeg AUROC 0.737 vs 0.758) but produces far fewer false candidates
  (precision 0.45 vs 0.25), so its sensitivity at the guarantee is higher (P1 α = 0.2: 0.102 vs
  0.017; realised FDR 0.093 vs 0.166).

## 5. Q4 — Per-site recalibration

**Within-site calibration (D1, ensemble).** P1 realised FDR, α = 0.1 / 0.2: MSLesSeg 0.016 /
0.046; Ljubljana 0.000 / 0.034; MS3SEG 0.041 / 0.075; Muslim 0.038 / 0.069; PediMS 0.024 / 0.066
— all well below α; sensitivity at α = 0.2: 0.31 / 0.14 / 0.20 / 0.16 / 0.15. P2 (γ = 0.1) FDX:
0.09 / 0.10 / 0.10 / 0.08 / 0 (PediMS abstains: 8 calibration patients < 9).

**Table 6. Recalibration curve (D5; 200 draws of k target patients; mean over draws).**

| site · procedure | k = 3 | k = 10 | k = 40 | k* (site-only / augmented) |
|---|---|---|---|---|
| MS3SEG · P1 α = 0.2, site-only | FDR 0.056, sens 0.166 | 0.069, 0.183 | 0.078, 0.193 | 10 / 1 |
| MS3SEG · P1 α = 0.1, augmented (1-mm pool + k) | 0.104 (72 % of draws > α) | 0.101 (56 %) | 0.081 (15 %) | 10 / 20 |
| MS3SEG · P2 γ = 0.1, site-only | abstains | FDX 0.075, sens 0.038 | 0.086, 0.037 | 10 / none |
| MS3SEG · P2 γ = 0.1, augmented | FDX 0.192 | 0.187 | 0.162 | — |
| Muslim · P1 α = 0.2, site-only | 0.045, 0.131 | 0.053, 0.150 | 0.068, 0.159 | 10 / 1 |
| Muslim · P2 γ = 0.1, site-only | abstains | FDX 0.092, sens 0.006 | 0.096, 0.005 | 10 / none |
| Muslim · P2 γ = 0.1, augmented | 0.250 | 0.235 | 0.196 | — |
| PediMS · P1 α = 0.2, site-only (k ≤ 5) | 0.057, 0.184 | — | — | 2 / 1 |
| Ljubljana · P1 α = 0.2, site-only (k ≤ 5) | 0.025, 0.124 | — | — | 2 / 1 |

Pre-registered Q4 verdict (record `q4.verdict`): the three violated cells (MS3SEG P2 γ = 0.1;
Muslim P2 γ = 0.1, 0.2) are formally **restored by site-only recalibration with k* = 10
patients**, but at a large sensitivity cost: with 10 local patients the per-scan procedure finds
**3.8 % of lesions on MS3SEG and 0.6 % on Muslim** (vs 12.1 % and 3.6 % when, invalidly, calibrated
on the 1-mm sites). In plain terms, validity is restored by near-abstention; and the k* criterion
is met trivially when the within-site power it is compared to is itself near zero (Muslim D1 P2
sensitivity 0.004). Augmenting a large foreign
pool with site patients never restored P2 and kept P1 at α = 0.1 on the edge, because the
quantile/null is dominated by the 85 foreign patients.

## 6. Healthy controls — 100 SibBMS controls (addendum, pre-registered 2026-10-24)

*Protocol: `PROTOCOL-v0.3-addendum-controls.md` (commit caa47e7, before any control outcome).
Records: `2026-10-24_paper_a_v03c_{inventory,calibration,controls,controls_check}.json`. The fold-0
arm on 30 of these controls (sub-001…020, 031…040) had been seen in the first v0.3 text and is not
blind; everything else is. An independent re-implementation (own decoding, labelling, p-values and
BH) reproduced every primary count and every per-control candidate and selection count exactly.*

**Data.** 100 healthy adults of the public SibBMS dataset (one site; `Output/Norm` images,
spatially normalised to an MNI-type 1-mm template, brain ≈ 2.0 L; licence CC BY-NC-SA 3.0),
HD-BET-stripped, FLAMeS folds 0–4. **Not in FLAMeS training**: FLAMeS's Table 1 lists 11 training
sources (668 scans, people with MS), none SibBMS; the released weights' fingerprint has 668 entries,
none compatible with a SibBMS image; SibBMS was released after FLAMeS was submitted. The lesion
"truth" is an assumption (healthy volunteers; no expert reading of these scans for incidental
white-matter hyperintensities). On a lesion-free scan FDP = 1{≥ 1 reported lesion}, so the FDR
promise of P1 reads P(≥ 1 reported lesion) ≤ α, and P2's reads ≤ δ = 0.1.

**Table 7. Healthy controls with ≥ 1 reported lesion, of 100 (exact 95 % CI, %) → class; false
lesions per scan.** Ensemble arm unless stated. Primary cells in bold.

| calibration (patients) | P1 α = 0.1 | P1 α = 0.2 | P2 γ = 0.1 (= 0.2) | B2 (CRC) α = 0.1 / 0.2 | B3 (LTT) α = 0.1 / 0.2 |
|---|---|---|---|---|---|
| **1-mm sites (primary)** | **14 [7.9, 22.4] inconclusive; 0.22** | **24 [16.0, 33.6] inconclusive; 0.37** | **6 [2.2, 12.6] holds; 0.06** | 7 holds / 25 inconcl. | 2 holds / **32 [23.0, 42.1] violated** |
| MSLesSeg only | 15 [8.6, 23.5] inconcl. | 24 inconcl. | 6 holds | 7 holds / 25 inconcl. | 2 holds / 30 violated |
| all five patient sites | 5 [1.6, 11.3] holds | 19 [11.8, 28.1] inconcl. | 2 holds | 2 holds / 11 holds | 2 holds / 32 violated |
| thick-slice sites | 3 [0.6, 8.5] holds | 14 [7.9, 22.4] holds | 2 holds | 2 holds / 7 holds | 1 holds / 29 violated |
| own null (leave-one-control-out, exchangeable by construction) | 4 [1.1, 9.9] | 13 [7.1, 21.2] | — | — | — |
| **fold 0**, 1-mm sites | **59 [48.7, 68.7] violated; 1.08** | **72 [62.1, 80.5] violated; 1.54** | **32 [23.0, 42.1] violated** | 38 violated / 53 violated | 14 inconcl. / 50 violated |
| fold 0, all five patient sites | 39 violated | 58 violated | 7 holds | 13 inconcl. / 32 violated | 8 inconcl. / 48 violated |

**No selection (the full automatic segmentation):** ensemble **85/100 [76.5, 91.4]** controls with
≥ 1 candidate, 2.63 per scan (0 / 1 / 2 / ≥ 3 candidates: 15 / 21 / 19 / 45 scans; max 8); fold 0
93/100, 3.06 per scan; folds 1–4 85–90/100, 2.4–3.3 per scan. B1 (precision-matched threshold, no
guarantee): 32 and 51 of 100 at α = 0.1 / 0.2 with 1-mm calibration. Bonferroni intervals over the
4 primary cells change no class. P2 γ = 0.1 and 0.2 use the same threshold (0.965): one result, not
two.

- **Primary verdict.** P1 with the calibration the app spec would use (1-mm sites) is *inconclusive*
  on healthy brains at both α, with point estimates above nominal (14 % vs 10 %; 24 % vs 20 %): the
  data neither confirm nor refute the promise, and a false-alarm rate up to ~2× nominal at α = 0.1
  is compatible with them. P2 *holds* (6 %), but P2 is the procedure that finds 0.1–12 % of lesions
  in patients.
- **Blindness and QC (pre-specified S5, S6).** On the 70 controls never analysed before, P1 α = 0.1
  gives 13/70 (18.6 % [10.3, 29.7]) — that subset's lower bound exceeds 10 % (*violated* in the
  subset) — against 1/30 on the 30 seen before (**[post hoc]** Fisher p = 0.06); at α = 0.2: 17/70 vs
  7/30. Without sub-075 (HD-BET mask 2.8 L, flagged before outcomes): 14/99 and 23/99, no class
  changes. Fold 0 is violated in both subsets (42/70; 17/30).
- **The pool matters, in the expected direction.** Pools that include thick-slice patients give
  fewer false alarms on healthy brains (all sites 5/100, thick sites 3/100 at α = 0.1) because their
  false-candidate scores have a heavier upper tail. **[post hoc]** The control candidates' scores
  look more like the thick-slice null than the 1-mm null: the share ≥ 0.95 is 5.7 % (controls) vs
  2.7 % (1-mm patients' false candidates) and 5.6 % (thick-slice); naive KS D = 0.12 against the
  1-mm null (candidates are clustered in scans, so its p = 0.003 is optimistic). Exchangeability with
  the 1-mm patient null is therefore doubtful, as on the thick-slice sites (§2).
- **The ensemble is essential (S4).** Ensemble vs fold 0, same 100 controls, 1-mm calibration:
  P1 α = 0.1 14 vs 59 (Δ −45 points [−55, −35]; discordant 1 vs 46, exact McNemar p < 10⁻⁵);
  P1 α = 0.2 24 vs 72; P2 6 vs 32. Raw: 85 vs 93 controls with a candidate (Δ −8 [−14, −3],
  p = 0.008), 2.63 vs 3.06 candidates per scan. The gain on healthy brains is larger than on
  patients (§4) because fold-0 false candidates are over-confident (median score 0.96 vs 0.74).
- **The app's dissemination-in-space rule on healthy brains (S3).** The app's own code path
  (`generate_zone_map_atlas` → `classify_from_zone_mask` → `compute_dis_criteria`, brain only) runs
  on these images: they pass the app's MNI-grid check and the MSMask atlas overlaps the brain masks
  with median Dice 0.97. **Applied to the unselected automatic segmentation, `dis_met_brain` is true
  in 19/100 healthy controls (95 % CI 11.8–28.1 %; fold 0: 22/100)**, and 79/100 have ≥ 1 automatic
  lesion in a DIS region. After selection: P1 α = 0.1 2/100 [0.2, 7.0]; P1 α = 0.2 3/100
  [0.6, 8.5]; P2 0/100 (one-sided 95 % bound 3.0 %); all-site P1 α = 0.1 0/100. Without sub-075:
  18/99 raw. By the pre-registered rule (lower bound > 5 %) this must be stated plainly: **the
  unselected automatic segmentation fulfils the app's brain-DIS rule in about 1 in 5 healthy brains**
  of this dataset.
- **Where the false lesions sit (S7).** 263 ensemble candidates: 165 periventricular (63 %), 33
  juxtacortical, 4 infratentorial, 61 deep white matter (app regions); median 23 mm inside the brain
  mask, only 2/263 within 3 mm of the skull-strip edge, none touching it; median 27 mm³ (90th
  percentile 208 mm³, template space). Selected ones (P1 α = 0.1, 22 lesions): 11 PV, 9 JC, 2 DWM,
  median 48 mm³. **[post hoc]** Visual check of the top candidate of four controls (sub-053, -079,
  -043, -062): a symmetric hyperintensity at the occipital horn (the usual periventricular
  "cap"/trigone pattern of normal brains), and small focal subcortical / deep white-matter
  hyperintensities, FLAIR intensity 1.1–1.7 × the brain median. They are not skull-stripping or
  template-boundary artefacts; they are the kind of findings readers see in healthy brains — some may
  be genuine incidental hyperintensities (unknowable here: no expert read of these scans).
- **Reproduction (S8).** The new fold-0 candidates of the 30 August controls equal the v0.3 cache
  (30/30 counts, scores within 0.0008).

*Does template normalisation make these controls easier or harder than clinical scans?* Both
directions are plausible and neither is measured. Easier: registration resamples the FLAIR onto a
smooth 1-mm grid (as for MSLesSeg, the main calibration cohort), one site and one protocol, and
skull-stripping on a clean template-space image produced no edge candidates. Harder: the template
enlarges brains (≈ 2.0 L mask vs ≈ 1.2–1.6 L native), so each candidate's physical volume is
inflated ~1.3–1.4× and tiny blobs pass the 3 mm³ floor more easily; resampling a possibly thicker
native acquisition can create partial-volume bright spots. The native SibBMS acquisition and the
controls' ages could not be verified from the sources we could access (the preprint was not
retrievable), and incidental hyperintensities become more common with age. The numbers describe
this dataset, not healthy brains in general.

*Superseded (first v0.3 text, fold 0, 30 controls):* MSLesSeg-calibrated P1 α = 0.1 flagged 17/30,
the all-site pool 10/30, P2 with all sites 5/30 — consistent with the 100-control fold-0 rows above.

## 7. Exploratory: paired segmenter shift (LST-AI vs FLAMeS on the same MSLesSeg images)

5-fold patient cross-fit, calibration and test patients disjoint; P1 realised FDR (α = 0.1 / 0.2),
sensitivity:

| calibration → test | FDR | sensitivity |
|---|---|---|
| FLAMeS → FLAMeS | 0.019 / 0.052 | 0.109 / 0.329 |
| LST-AI → LST-AI | 0.053 / 0.095 | 0.016 / 0.102 |
| FLAMeS → LST-AI | no selection | 0 |
| **LST-AI → FLAMeS** | **0.207 [0.175, 0.240] / 0.236 [0.203, 0.268]** | 0.66 / 0.69 |

v0.2 could only show the safe direction (power collapse, confounded with site). With the same
images, a calibration set from a less confident segmenter makes the more confident segmenter's
false candidates look significant, and the guarantee is violated. **This was expected, not a
discovery**: LST-AI's scores sit on a lower scale (mean false-candidate score 0.65 vs 0.76 for the
FLAMeS ensemble on MSLesSeg), so any null from one segmenter is miscalibrated for the other. It was
tested on one site (MSLesSeg) only. Its value is to make the deployment rule concrete: calibration
must come from the segmenter version that is deployed.

## 8. Negative and unexpected results (stated plainly)

- The per-scan FDX procedure does not transport to thick-slice sites; recalibration restores it
  only with ≥ 10 site patients, and then finds 3.8 % (MS3SEG) and 0.6 % (Muslim) of lesions.
- Marginal FDR control on Muslim at α = 0.1 is not established (CI to 0.197); "no violation
  detected" in the other cells includes 3 abstention cells and two underpowered sites.
- 1-mm calibration does not transfer as such to thick slices: realised FDR is 2.6–3.2× the
  within-site value, and **[post hoc]** 0.196 [0.120, 0.282] at α = 0.1 on the third of thick-slice
  scans with ≥ 40 % false candidates.
- The ensemble raises realised FDR on Muslim (0.122 vs 0.051 at α = 0.1) and adds 2 violated cells;
  its power gain at α = 0.1 (leave-one-site-out) is about 3 points.
- The thickness gradient across bands is largely a between-site difference.
- At γ ≤ 0.2 the FDX threshold is almost insensitive to γ (identical γ = 0.1 / 0.2 selections in
  most cells): 22–51 % (ensemble; fold 0: 22–59 %) of calibration scans need a threshold above
  their top false candidate, so the procedure largely behaves like "no false lesion above the
  threshold in 90 % of patients" **[post hoc]**.
- Foreign or pooled calibration makes the 1-mm sites nearly silent (sensitivity ≤ 0.01 at α = 0.1).
- v0.2's whole pipeline (fold 0) would have violated the guarantee on MS3SEG.
- Thickness-specific minimum lesion sizes rest on one site per band (B2: 9 children; B3/B4:
  MS3SEG and Muslim, confounded with annotation protocol).
- **Healthy brains (addendum):** with the calibration the app spec would use, the FDR promise on
  healthy brains is not established (14/100 at α = 0.1, 24/100 at α = 0.2, both above nominal,
  undecided); on the 70 never-analysed controls alone, α = 0.1 is violated (13/70, lower bound
  10.3 %). Fold 0 fails on healthy brains at every P1 and P2 operating point with 1-mm calibration
  (59/100 at α = 0.1). Learn-then-Test at α = 0.2 is violated with every pool (29–32/100).
- **The unselected automatic segmentation meets the app's brain-DIS rule in 19/100 healthy
  controls** (11.8–28.1 %) and shows ≥ 1 lesion in 85/100; this is a safety-relevant property of any
  workflow that computes DIS from an unreviewed automatic segmentation.

## 9. Limitations

- **Contamination handling**: 20 of 30 Ljubljana scans are FLAMeS training data and were excluded
  everywhere (also as calibration); the clean Ljubljana set has 10 scans. MS3SEG, Muslim and PediMS
  have no known overlap with FLAMeS training (dataset descriptions; not forensically verified like
  Ljubljana).
- **Muslim in-plane pixel size is estimated** (±5 % per axis); it shifts lesion volumes by ~±10 %
  and Muslim's 50 %-detection size between 50 and 150 mm³. Muslim spans ~20 uncontrolled centres
  and annotation was a sequential correction chain.
- **PediMS: 28 scans of only 9 children**; percentile bootstrap intervals with 9 clusters (and 10
  for Ljubljana) under-cover; within-site P2 is impossible (≤ 8 calibration patients).
- **Healthy controls (addendum): one site, one dataset, template-normalised images** (registered
  and resampled to an MNI-type 1-mm template; brains ≈ 2.0 L), native acquisition and ages not
  verified; "lesion-free" is an assumption about volunteers, not an expert read of these scans
  (some "false" lesions may be genuine incidental hyperintensities); licence CC BY-NC-SA 3.0
  (research use only); 30 of the 100 had been analysed with fold 0 before the addendum (not blind
  for that arm). One HD-BET mask (sub-075) includes non-brain tissue (sensitivity analysis changes
  nothing). The LST-AI arm on controls is pending (maps being computed).
- **Site, thickness, scanner, population and annotation protocol are confounded** (e.g. MS3SEG
  excludes periventricular "normal" hyperintensities from its lesion class, so FLAMeS hits there
  count as false). Bands are sites, not controlled thickness experiments.
- **MSLesSeg is not natively 1 mm**: its FLAIRs were acquired at 2–5 mm (dataset acquisition table)
  and resampled to MNI 1 mm, so the "1-mm" band mixes 10 natively thin scans with 110 resampled
  2–5 mm scans; an earlier version of this file wrongly said the native geometry was unpublished.
- 3D connected components on 4–8 mm slices can merge or split lesions; candidate and expert-lesion
  rules are identical, but lesion counts are not comparable to 1-mm counts.
- The "holds" rule tolerates realised values up to α + 0.05 at the CI upper bound; "holds" cells
  with point estimates above α: ensemble D3 MS3SEG α = 0.1 (0.107) and fold-0 D2 MS3SEG α = 0.2
  (0.208). "Holds" means no violation detected, not proof of validity.
- **A 3-case thick-slice pilot preceded the protocol** (2026-10-18: one scan each of MS3SEG,
  Muslim and PediMS, FLAMeS fold 0, run to test the processing chain). Its maps are among the v0.3
  inputs. The analyst who wrote the protocol did not inspect pilot outcomes, but the pilot was run
  in the same project before pre-registration; disclosed in protocol §13 entry 7.
- The independent re-implementation used a different within-site fold split; its within-site
  numbers differ from ours in the second decimal (e.g. MS3SEG α = 0.1: 0.047 vs 0.041).
- Layer-1/Layer-2 region certificates of v0.2 §5 were not re-run on the new sites.

## 10. Reproducibility

| result | script | record |
|---|---|---|
| input hashes, grids, fold-0 reproduction | `research/paper_a/v03_inventory.py` | `2026-10-21_paper_a_v03_inventory.json` |
| candidates, labels, gate G1 | `research/paper_a/v03_candidates.py` | `2026-10-21_paper_a_v03_candidates.json` (cache SHA-256 2096109e…) |
| Tables 1–7, §2–§7 | `research/paper_a/v03_analysis.py` (+ `v03_metrics.py`, `v03_data.py`) | `2026-10-21_paper_a_v03_results.json` |
| MSLesSeg native slice thickness (post hoc) | `research/paper_a/v03_mslesseg_native.py` | `2026-10-21_paper_a_v03_mslesseg_native.json` |
| post-hoc explanations (labelled; item 5 = low-lesion-load scans, added after the independent review) | `research/paper_a/v03_posthoc.py` | `2026-10-21_paper_a_v03_posthoc.json` |
| metric/procedure tests | `research/paper_a/test_v03_metrics.py` (33 pass) | — |
| controls addendum: protocol | — | `docs/research/paper/PROTOCOL-v0.3-addendum-controls.md` (commit caa47e7) |
| controls: input hashes, grid, atlas alignment, fingerprint check (gate C0) | `research/paper_a/v03c_inventory.py` | `2026-10-24_paper_a_v03c_inventory.json` |
| controls: frozen operating points (patient data only) | `research/paper_a/v03c_calibration.py` | `2026-10-24_paper_a_v03c_calibration.json` |
| controls: §6, Table 7, app DIS, location | `research/paper_a/v03c_controls.py` | `2026-10-24_paper_a_v03c_controls.json` (control cache SHA-256 cbf41cf4…) |
| controls: independent re-implementation | `research/paper_a/v03c_controls_check.py` | `2026-10-24_paper_a_v03c_controls_check.json` (all counts equal) |

Runtime on the local CPU: candidates 18 min (7 workers), analysis 6 min, post hoc < 1 min; controls addendum: extraction 13 min (3 workers), analysis 5 min, independent check 15 min.
