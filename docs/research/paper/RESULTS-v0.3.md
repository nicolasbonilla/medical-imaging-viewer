# Paper A v0.3 — Results of the pre-registered multi-site analysis

*Research code and research findings, not the medical device. Date: 2026-10-21.*

- Protocol: `docs/research/paper/PROTOCOL-v0.3.md` — committed before any outcome (9951494);
  implementation clarifications 1–4 (c0c5fa1) and the gate-G1 deviation 5 (50c9b08) were logged
  before any outcome was computed. No later deviation.
- Records: `docs/research/records/2026-10-21_paper_a_v03_*.json` (+ `_output.txt`): inventory
  (input SHA-256), candidates (cache SHA-256, gate G1), results (all numbers below), post-hoc
  (explanatory checks written **after** the results were seen — labelled as such wherever used).
- Code: `research/paper_a/v03_{data,inventory,candidates,metrics,analysis,posthoc}.py`; tests
  `research/paper_a/test_v03_metrics.py` (33 pass).
- Arms: **ens** = 5-fold FLAMeS mean probability (primary); **f0** = fold 0 alone (= the v0.1/v0.2
  pipeline). P1 = conformal BH (FDR target α); P2 = scan-conformal FDX threshold (target
  P(FDP > γ) ≤ δ = 0.1). "Realised FDR" = mean per-scan FDP; "FDX" = share of test scans with
  FDP > γ. Intervals are 95 % patient-cluster bootstrap (FDX: union with exact Clopper–Pearson).
  Cell classes (protocol §9): *violated* = CI lower bound > nominal; *holds* = CI upper bound ≤
  nominal + 0.05 (**note: a "holds" cell may have a point estimate slightly above nominal**);
  otherwise *inconclusive*; "uninf." = holds only through abstention (< 10 selections or
  end-to-end sensitivity < 0.05).

---

## 0. Bottom line

1. **Marginal lesion-FDR control (P1) was not violated in any of the 16 held-out-site cells**
   (1-mm → thick-slice and leave-one-site-out), but it is not "established" everywhere: on Muslim
   at α = 0.1 the realised FDR was 0.122 [0.062, 0.197] (inconclusive), and on MS3SEG at α = 0.1 it
   was 0.107 [0.074, 0.145] (point estimate above nominal, within the pre-registered margin).
   Pre-registered verdict for Q1/P1: **inconclusive**.
2. **Per-scan exceedance control (P2) does not transport from 1-mm to thick-slice sites**: with a
   threshold calibrated on MSLesSeg + Ljubljana, 21 % of MS3SEG scans (γ = 0.1) and 29 % / 27 % of
   Muslim scans (γ = 0.1 / 0.2) had FDP above γ, against a 10 % budget. Verdict Q1/P2: **refuted**.
3. **Thickness matters, mostly through power and slack, not through outright violation.** Under
   leave-one-site-out calibration, realised FDR at α = 0.2 rises with slice thickness — 0.018
   (≤ 1.5 mm), 0.050 (3.9 mm), 0.101 (4.5–6.5 mm), 0.120 (> 6.5 mm) — and the share of scans with
   FDP > 0.1 rises from 6 % to 49 %. Raw lesion detection falls: no lesion size reaches 80 %
   detection on thick-slice scans, and 50 % detection needs ≥ 50 mm³ (≈ 4.6 mm diameter) on
   4.5–8.3 mm slices versus ≥ 14 mm³ (≈ 3 mm) on 1-mm and 3.9-mm scans.
4. **The 5-fold ensemble is the largest effect in this study.** Candidate AUROC rises from
   0.67–0.76 (any single fold) to 0.78–0.82 (ensemble) at every site; at the guarantee
   (P1, α = 0.2) end-to-end lesion sensitivity doubles (leave-one-site-out 0.203 vs 0.102,
   Δ = +0.10 [0.07, 0.13]; 1-mm → thick 0.341 vs 0.194, Δ = +0.15 [0.12, 0.18]) and realised FDR
   falls. **With fold 0 alone — the v0.2 pipeline — MS3SEG is violated** (P1 α = 0.1: 0.201
   [0.166, 0.242]); the ensemble removes 5 violated cells and adds 2 (Muslim, P2). Pre-registered
   verdict Q3: "helps on power, but with new violated cells".
5. **Per-site recalibration works for P1 at any size and for P2 only site-only with ≥ 10
   patients.** Within-site P1 stayed below α on average at every calibration size; 10 target
   patients reach ~90 % of full within-site power on MS3SEG and Muslim. P2 needs ≥ 9 site patients (δ = 0.1) and is restored on MS3SEG
   (k = 10: FDX 0.075) and, by near-total abstention, on Muslim; adding the 1-mm pool to the site
   patients never restored P2 (FDX 0.16–0.28 for k ≤ 40).
6. **Paired segmenter shift (same MSLesSeg images, FLAMeS vs LST-AI) breaks validity in one
   direction**: LST-AI-calibrated selection on FLAMeS candidates gave realised FDR 0.207
   [0.175, 0.240] at α = 0.1; the other direction selected nothing.
7. **Power remains the cost**: at the guarantee, end-to-end lesion sensitivity is 0.01–0.40
   depending on site, design and α; per-scan (P2) selection finds 0.1–12 % of lesions.

---

## 1. Data, gates and score quality

**Inventory (gate G0).** 324 cases × (5 FLAMeS folds + expert mask), 144 × LST-AI (ensemble + 3
sub-models) and 30 controls opened; every map matches its mask's grid; SHA-256 of every input in
`2026-10-21_paper_a_v03_inventory.json`. The new fold-0 maps reproduce the August fold-0 maps
(145 scans; max |Δp| 0.0022; 6 voxels in 5 scans change side of 0.5).
**Pipeline reproduction (gate G1).** Fold-0 candidates vs v0.2's cache: counts identical in
125/125 scans, one-to-one labels identical for 4400/4400 candidates, score differences ≤ 0.0017
outside the 5 boundary-voxel scans; one candidate inside them differs by 0.0078 → strict criterion
failed on that candidate, deviation 5 logged before any outcome.

**Table 1. Cohorts (ensemble arm; one-to-one lenient labels).**

| site | scans / patients | slice spacing (mm) | candidates | false | candidate precision | detectable expert lesions | raw lesion sensitivity | AUROC ens [95 % CI] | AUROC fold 0 |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| MSLesSeg | 115 / 75 | 1 (MNI) | 3788 | 1257 | 0.668 | 3344 | 0.757 | 0.818 [0.798, 0.837] | 0.735 [0.708, 0.761] |
| Ljubljana clean 10 | 10 / 10 | 1 (MNI) | 517 | 82 | 0.841 | 667 | 0.652 | 0.802 [0.729, 0.883] | 0.698 [0.625, 0.773] |
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
  γ = 0.1 0.20 [0.10, 0.30]; Muslim P2 γ = 0.1 / 0.2 0.27 [0.12, 0.41] / 0.25 [0.12, 0.37]. Same
  conclusions.
- **Verdicts (protocol §10):** P1 — *inconclusive* (no violated cell; MS3SEG holds; Muslim α = 0.1
  inconclusive). P2 — *refuted* (MS3SEG γ = 0.1 and Muslim γ = 0.1, 0.2 violated).
- **Why P2 fails and P1 does not (post-hoc explanation).** P2 is a single threshold (0.965 when
  calibrated on the 1-mm sites). The share of scans with a false candidate above 0.965 is 6 %
  (MSLesSeg) and 10 % (Ljubljana) but 24 % (MS3SEG) and 29 % (Muslim) — the realised FDX almost
  exactly. Thick-slice sites produce more very-confident false candidates (scan-clustered KS test
  of the false-score law vs the 1-mm sites: MS3SEG D = 0.107, p = 0.0005; Muslim D = 0.094,
  p = 0.025; PediMS D = 0.057, p = 0.51). P1 calibrates on the whole false-score law and controls
  only the expected FDP, which absorbs the shift with less slack lost.
- **Strict matching (IoU ≥ 0.10) and PediMS without patient P9** leave every primary class
  unchanged. With the **fold-consensus score** S_cons (secondary score), every D3 P1 cell holds
  (Muslim α = 0.1: 0.068 [0.026, 0.122]) and no P2 cell is violated (MS3SEG γ = 0.1: 0.14
  [0.08, 0.22], inconclusive), at a modest power cost (D3, α = 0.2: sensitivity 0.296 vs 0.341).
  This is a sensitivity analysis, not the primary result.

**Baselines in D3 (α = 0.1 / 0.2; realised FDR).** Precision-matched threshold (B1): MS3SEG
0.164 [0.136, 0.196] / 0.230 [0.206, 0.255] — **violated at both**; Muslim 0.144 [0.107, 0.180]
— **violated** / 0.235; PediMS 0.106 / 0.197. Conformal risk control (B2): MS3SEG 0.072 / 0.129;
**Muslim 0.180 [0.103, 0.265] at α = 0.1 — violated**; PediMS 0.069 / 0.098. Learn-then-Test (B3):
MS3SEG 0.083 / 0.181; Muslim 0.134 [0.062, 0.226] / 0.159; PediMS 0.000 / 0.114. Conformal BH (P1)
is the only procedure with no violated D3 cell.

**1-mm sites under foreign calibration are over-conservative.** Leave-one-site-out and thick →
1-mm calibration made MSLesSeg nearly silent (P1 α = 0.1: 34 selections, sensitivity 0.010;
within-site D1: 358 selections, 0.102): the thick sites' heavier false-score tail inflates the
null. The guarantee is safe there, but useless.

## 3. Q2 — Validity and power by slice thickness

**Table 3. By thickness band, leave-one-site-out calibration (D2), ensemble arm.** The pooled
5-fold design (D4) gives the same pattern (record `thickness.D4|by_band`).

| band (slice spacing) | scans / patients (sites) | P1 α = 0.1: FDR · sens. | P1 α = 0.2: FDR [CI] · scans FDP > 0.1 · sens. [CI] · false / true lesions per scan | P2 γ = 0.1: FDX [CI] · sens. |
|---|---|---|---|---|
| B1 ≤ 1.5 mm | 125 / 85 (MSLesSeg, Ljubljana) | 0.008 · 0.010 (uninf.) | 0.018 [0.004, 0.040] · 6 % · 0.094 [0.053, 0.141] · 0.13 / 3.0 | 0.016 [0.002, 0.057] · 0.002 (uninf.) |
| B2 3.9 mm | 28 / 9 (PediMS) | 0.007 · 0.064 | 0.050 [0.016, 0.093] · 14 % · 0.164 [0.042, 0.440] · 0.50 / 6.5 | 0.000 [0, 0.12] · 0.025 (uninf.) |
| B3 4.5–6.5 mm | 76 / 76 (Muslim 45, MS3SEG 31) | 0.084 · 0.112 | 0.101 [0.063, 0.145] · 30 % · 0.236 [0.180, 0.298] · 0.88 / 7.9 | 0.158 [0.079, 0.260] · 0.047 (inconcl.) |
| B4 > 6.5 mm | 75 / 75 (MS3SEG 69, Muslim 6) | 0.087 · 0.170 | 0.120 [0.093, 0.152] · 49 % · 0.355 [0.310, 0.402] · 1.73 / 12.4 | 0.173 [0.093, 0.278] · 0.077 (inconcl.) |

Every P1 cell holds; the slack shrinks monotonically with thickness, and the per-scan
exceedance grows. Power grows with thickness too — thick-slice expert lesions are larger (median
108–117 mm³ vs 68 mm³ on MSLesSeg and 20 mm³ on Ljubljana; post-hoc record) and the 1-mm band is
penalised by the foreign null. Within MS3SEG, per-scan FDP does not trend with slice spacing
(6.0–8.1 mm; Spearman ρ = 0.03, p = 0.75); within Muslim ρ = 0.30, p = 0.035, but only 6 scans
exceed 6.5 mm (post hoc).

**Table 4. Expert-lesion sensitivity by lesion volume and band** (raw = matched by any candidate,
no selection; "at guarantee" = selected by P1 α = 0.2, D2). Bins: [3, 14), [14, 50), [50, 150),
[150, 500), ≥ 500 mm³ (equivalent sphere diameter ≈ 1.8–3, 3–4.6, 4.6–6.6, 6.6–9.8, ≥ 9.8 mm).

| band | lesions per bin | raw sensitivity | at guarantee | smallest bin from which raw ≥ 0.8 / ≥ 0.5 | at guarantee ≥ 0.5 |
|---|---|---|---|---|---|
| B1 ≤ 1.5 mm | 531 / 1217 / 1327 / 610 / 326 | 0.36 / 0.72 / 0.81 / 0.87 / 0.90 | 0.02 / 0.04 / 0.09 / 0.20 / 0.21 | **50 mm³** / 14 mm³ | never |
| B2 3.9 mm | 75 / 324 / 378 / 234 / 93 | 0.37 / 0.67 / 0.76 / 0.77 / 0.80 (0.796) | 0.03 / 0.08 / 0.19 / 0.22 / 0.33 | **never** / 14 mm³ | never |
| B3 4.5–6.5 mm | 48 / 514 / 976 / 673 / 343 | 0.13 / 0.45 / 0.59 / 0.66 / 0.76 | 0.00 / 0.10 / 0.23 / 0.30 / 0.38 | **never** / 50 mm³ | never |
| B4 > 6.5 mm | 34 / 455 / 1074 / 713 / 343 | 0.21 / 0.43 / 0.69 / 0.72 / 0.70 | 0.06 / 0.10 / 0.32 / 0.48 / 0.56 | **never** / 50 mm³ | 500 mm³ |

Muslim's estimated pixel size moves its own 50 %-detection size: 50 mm³ at nominal and × 0.9
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

- **Fold-0 primary cells** (same 32 cells, record `q3.f0_primary_cells`): MS3SEG is violated in
  D3 P1 α = 0.1 (0.201 [0.166, 0.242]), D2 P1 α = 0.1 (0.176 [0.139, 0.216]) and in every MS3SEG
  P2 cell (FDX 0.39–0.62); D3 P1 α = 0.2 is 0.225 [0.193, 0.260]. The ensemble removes these 5
  violations and adds 2 (Muslim P2, D3; fold 0 there: FDX 0.16 / 0.12, inconclusive, at
  sensitivity 0.024). Pre-registered verdict: **"helps on power, but with new violated cell(s)"**.
- Folds 1–4 behave like fold 0 (D3, P1 α = 0.2: realised FDR 0.157–0.176, sensitivity 0.19–0.25),
  so fold 0 is typical, and the gain comes from averaging.
- Mechanism (post hoc): the share of false candidates scoring ≥ 0.95 drops from 16–32 % (fold 0)
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
Muslim P2 γ = 0.1, 0.2) are **restored by site-only recalibration with k* = 10 patients** — on
Muslim only through near-total abstention (sensitivity 0.004–0.006). Augmenting a large foreign
pool with site patients never restored P2 and kept P1 at α = 0.1 on the edge, because the
quantile/null is dominated by the 85 foreign patients.

## 6. Healthy controls (fold-0 arm only)

**Table 7. False detections per 100 healthy scans (controls with ≥ 1 false detection, of 30).**

| calibration (fold-0 candidates) | P1 α = 0.1 | P1 α = 0.2 | P2 γ = 0.1 / 0.2 | CRC (B2) α = 0.1 / 0.2 |
|---|---|---|---|---|
| own null, leave-one-control-out (floor) | 10.0 (3) | 20.0 (6) | — | — |
| MSLesSeg only (v0.2 reference) | 83.3 (17) | 136.7 (22) | 43.3 (12) | 46.7 (13) / 63.3 (16) |
| 1-mm patient sites | 86.7 (17) | 136.7 (22) | 43.3 (12) | 46.7 (13) / 63.3 (16) |
| thick-slice patient sites | 30.0 (8) | 76.7 (15) | 6.7 (2) | 16.7 (5) / 20.0 (6) |
| all five patient sites | 36.7 (10) | 103.3 (17) | 16.7 (5) | 16.7 (5) / 43.3 (12) |

Pooling heterogeneous patient sites more than halves false detections on healthy brains at
α = 0.1 (36.7 vs 83.3 per 100), but stays 3.7× above the controls' own floor; the scan-level
threshold P2 calibrated on all sites flags a false lesion in 5 of 30 controls (exact 95 % CI
6–35 %). v0.2 reported 86.7 for the MSLesSeg-only null at α = 0.1; the one-detection difference
comes from the ≤ 0.008 score differences between the August and the re-extracted MSLesSeg
candidates (G1). Ensemble maps of controls are pending (data-access form), so the ensemble arm
could not be tested on controls.

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
false candidates look significant: **segmenter shift violates the guarantee.** Calibration must
come from the segmenter that is deployed.

## 8. Negative and unexpected results (stated plainly)

- The per-scan FDX procedure does not transport to thick-slice sites; recalibration restores it
  only with ≥ 10 site patients and, at Muslim, only by abstaining.
- Marginal FDR control on Muslim at α = 0.1 is not established (CI to 0.197).
- At γ ≤ 0.2 the FDX threshold is almost insensitive to γ (identical γ = 0.1 / 0.2 selections in
  most cells): 22–51 % (ensemble; fold 0: 22–59 %) of calibration scans need a threshold above
  their top false candidate, so the procedure largely behaves like "no false lesion above the
  threshold in 90 % of patients" (post hoc).
- Foreign or pooled calibration makes the 1-mm sites nearly silent (sensitivity ≤ 0.01 at α = 0.1).
- v0.2's whole pipeline (fold 0) would have violated the guarantee on MS3SEG.
- Thickness-specific minimum lesion sizes rest on one site per band (B2: 9 children; B3/B4:
  MS3SEG and Muslim, confounded with annotation protocol).

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
- **Healthy controls: fold 0 only, 30 scans**; the ensemble's effect on false detections in healthy
  brains is untested.
- **Site, thickness, scanner, population and annotation protocol are confounded** (e.g. MS3SEG
  excludes periventricular "normal" hyperintensities from its lesion class, so FLAMeS hits there
  count as false). Bands are sites, not controlled thickness experiments.
- MSLesSeg's native FLAIR geometry is not published in the sources we could access; it is used as
  delivered (MNI 1 mm).
- 3D connected components on 4–8 mm slices can merge or split lesions; candidate and expert-lesion
  rules are identical, but lesion counts are not comparable to 1-mm counts.
- The "holds" rule tolerates realised values up to α + 0.05 at the CI upper bound; three "holds"
  cells have point estimates slightly above α (ensemble D3 MS3SEG α = 0.1: 0.107).
- Layer-1/Layer-2 region certificates of v0.2 §5 were not re-run on the new sites.

## 10. Reproducibility

| result | script | record |
|---|---|---|
| input hashes, grids, fold-0 reproduction | `research/paper_a/v03_inventory.py` | `2026-10-21_paper_a_v03_inventory.json` |
| candidates, labels, gate G1 | `research/paper_a/v03_candidates.py` | `2026-10-21_paper_a_v03_candidates.json` (cache SHA-256 2096109e…) |
| Tables 1–7, §2–§7 | `research/paper_a/v03_analysis.py` (+ `v03_metrics.py`, `v03_data.py`) | `2026-10-21_paper_a_v03_results.json` |
| post-hoc explanations (labelled) | `research/paper_a/v03_posthoc.py` | `2026-10-21_paper_a_v03_posthoc.json` |
| metric/procedure tests | `research/paper_a/test_v03_metrics.py` (33 pass) | — |

Runtime on the local CPU: candidates 18 min (7 workers), analysis 6 min, post hoc < 1 min.
