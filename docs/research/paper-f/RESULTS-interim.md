# Paper F — INTERIM results (2026-10-22): MindGlide and LST-AI vs the FLAMeS ensemble

**Interim, not final.** WMH-SynthSeg and SAMSEG have not run yet: they wait for the owner's
FreeSurfer licence file (RUNBOOK.md 0.1). The primary family of PROTOCOL.md 7.1 (6 tests) and the
secondary family 7.2 (11 tests) are therefore incomplete; their multiplicity-adjusted p-values below
are the conservative Bonferroni bound (p × family size), which Holm can never exceed once the family
is complete. No outcome, definition, band, threshold or comparison was changed (PROTOCOL.md section
12 lists the only additions, both made before these results were looked at). Research only — not
part of the medical device.

> **Resumen en español sencillo.** En los 179 estudios de cortes gruesos, MindGlide acierta menos
> lesiones que FLAMeS (F1 por lesión 0,55 frente a 0,72; diferencia −0,17, intervalo −0,21 a −0,14) y
> marca un número parecido de lesiones falsas (+0,6 por estudio, intervalo −0,9 a +2,2). Darle la FLAIR
> original con cráneo, como piden sus autores, no lo mejora (−0,02). En 1 mm la ventaja de FLAMeS es
> aún mayor (−0,27 frente a MindGlide; −0,18 frente a LST-AI). FLAMeS sigue siendo la mejor opción
> probada; en cortes gruesos pierde poco acierto pero casi duplica las lesiones falsas (6,9 frente a
> 3,8 por estudio). Que MindGlide no coincida con FLAMeS sí señala bien los estudios donde FLAMeS falla
> (área bajo la curva 0,78 en cortes gruesos): idea útil para una "segunda opinión", aún por validar.

## 1. What was run and checked

| Item | Value |
|---|---|
| Code | `evaluate.py` / `metrics.py` as committed in 7a4f4f6 (unchanged since the protocol); `summarize.py` (formatting only) added with these results |
| MindGlide, primary arm (FLAMeS skull-stripped FLAIR) | 324 / 324 scans, runs `toolbench-mindglide-a/b` + pilot, 0 errors (coordinator report) |
| MindGlide, raw-input arm 7.6 (FLAIR before skull stripping) | 179 / 179 thick-band scans, runs `toolbench-mgraw` + `toolbench-mgraw-2` (the first hit its 10 h guard on a slow machine and was resumed), 0 errors |
| FLAMeS 5-fold ensemble | 324 / 324 (`data/cohorts/cloud-2026-10/flames`) |
| LST-AI v1.2.0 | 144 (MSLesSeg 114 — P49_T2 has a blank T1 — and Ljubljana 30); not run on thick cohorts (needs T1) |
| WMH-SynthSeg, SAMSEG | **not run** (licence pending) |
| Structural check (`evaluate.py check`) | MindGlide 324/324 PASS, MindGlide raw 179/179 PASS: exact FLAMeS grid, binary masks. Plausibility warnings (not failures): 17 MindGlide scans (15 with Dice < 0.1, mostly MSLesSeg, several predicting > 10× the expert volume), 3 MindGlide-raw scans (`results-interim/structural_check_mindglide.json`) |
| Contamination | the 20 Ljubljana scans in FLAMeS training are excluded from every FLAMeS comparison (iso band: 125 scans for FLAMeS pairs) |
| Inference | patient-cluster bootstrap stratified by cohort, 10,000 replicates, seed 20261021, cohort-weighted |

Files: `results-interim/per_scan.csv.gz` (6,906 rows: scan × tool × pre-stated variant),
`comparisons.json` (all pre-stated comparisons), `summary.json` + `tables.md` (the tables below).

## 2. Key results

**Primary family (thick band, 179 scans / 160 patients) — MindGlide vs FLAMeS:**
- Lesion-wise F1: **−0.170** (95% CI −0.206 to −0.136), p < 0.0001, still < 0.0001 after the ×6
  bound. MindGlide 0.554 vs FLAMeS 0.724 (cohort-weighted means).
- False lesions per scan: **+0.57** (−0.89 to +2.21), p = 0.45 — no difference shown; not equivalent
  within ±1 either (90% CI −0.66 to +1.97).
- Pre-stated reading (7.1): MindGlide does **not** outperform FLAMeS on thick slices; FLAMeS is better
  on lesion F1. Every sensitivity analysis agrees on F1 (−0.15 to −0.19). False lesions turn
  significantly worse for MindGlide without the size filter (+2.4) and with in-plane components (+8.1).

**Raw-input arm 7.6 (thick band, Holm over 4, complete):** MindGlide on the FLAIR with skull vs FLAMeS:
F1 −0.186 (−0.222 to −0.150), Holm p < 0.0001; false lesions +0.38 (−0.94 to +1.88). Raw vs
skull-stripped MindGlide: F1 −0.016 (−0.028 to −0.004), Holm p = 0.037, equivalent within ±0.05;
false lesions −0.19 (−0.75 to +0.32), equivalent within ±1. Skull stripping did not handicap MindGlide.

**Secondary (iso band; bound ×11):** MindGlide vs FLAMeS F1 −0.272 (−0.319 to −0.229), false lesions
+3.1 (+1.8 to +4.3); LST-AI vs FLAMeS F1 −0.180 (−0.212 to −0.150), false lesions +3.8 (+2.5 to +4.9).
Degradation contrast (thick minus iso gap) for MindGlide +0.102 (+0.047 to +0.160): MindGlide loses
less than FLAMeS when slices get thick, but starts much lower and stays below it.

**FLAMeS itself across bands:** F1 0.765 (iso) vs 0.724 (thick); false lesions 3.8 vs 6.9 per scan;
detection of small expert lesions (14–50 mm³) 0.56 vs 0.49. On thick slices MindGlide detects only
0.22 of these small lesions and 0.53 of 50–200 mm³ lesions (FLAMeS 0.79).

**Exploratory second opinion (7.5):** disagreement between MindGlide and FLAMeS flags scans where
FLAMeS lesion F1 < 0.5 with AUROC 0.78 on thick slices (14 such scans of 179; iso 0.81 but only 2 such
scans). Keeping only FLAMeS lesions that MindGlide also sees cuts false lesions by 3.8 per thick scan
but lowers F1 by 0.074 (−0.111 to −0.040).

## 3. Tables (generated by `research/paper_f/summarize.py`)

See `results-interim/tables.md` for the full set (per cohort, per band and sub-band, all available
pre-stated comparisons, detection by lesion size, sensitivity analyses, exploratory analyses, status
counts). Excerpt — per band, cohort-weighted mean (95% CI):

| Band | Tool | Scans | Lesion F1 | False lesions / scan | Dice |
|---|---|---|---|---|---|
| iso | FLAMeS (5 folds) | 125 | 0.765 (0.727 to 0.798) | 3.8 (2.8 to 5.0) | 0.657 (0.607 to 0.705) |
| iso | LST-AI | 144 | 0.620 (0.588 to 0.650) | 8.4 (7.2 to 9.8) | 0.520 (0.474 to 0.563) |
| iso | MindGlide | 145 | 0.518 (0.490 to 0.543) | 6.3 (5.6 to 7.0) | 0.418 (0.364 to 0.469) |
| thick | FLAMeS (5 folds) | 179 | 0.724 (0.702 to 0.745) | 6.9 (6.0 to 7.8) | 0.642 (0.614 to 0.665) |
| thick | MindGlide | 179 | 0.554 (0.517 to 0.589) | 7.5 (6.7 to 8.5) | 0.493 (0.452 to 0.522) |
| thick | MindGlide raw input | 179 | 0.538 (0.503 to 0.572) | 7.3 (6.6 to 8.0) | 0.508 (0.470 to 0.536) |

(LST-AI and MindGlide iso rows include all 30 Ljubljana scans; the FLAMeS row has the 10 clean ones.
The paired comparisons use only scans where both tools are usable and uncontaminated.)

## 4. Limitations of this interim

- Two of the three pre-registered CPU tools are missing; the primary family is 2 of 6 tests.
- MSLesSeg and Ljubljana are skull-stripped MNI-registered 1 mm images: far from MindGlide's training
  inputs; its iso-band numbers say little about MindGlide on native clinical scans.
- The iso-band AUROC rests on 2 poor FLAMeS scans; the thick-band one on 14. Both are exploratory.
- Muslim in-plane voxel size is estimated (S6 without Muslim agrees: F1 −0.194).
- Expert masks follow each cohort's own protocol (e.g. MS3SEG excludes periventricular "normal" WMH).
- Runtime and cost of these runs are in `toolbench/manifests` and `toolbench/cost`; the compute
  ledger has not been rebuilt here (no cloud command beyond the read-only download of the masks).

## 5. What comes next

1. Owner: FreeSurfer licence → pilot for WMH-SynthSeg and SAMSEG (RUNBOOK.md 3) → wave 1 (WMH-SynthSeg),
   wave 2 (SAMSEG tier).
2. Re-run `evaluate.py run` + `summarize.py` on all outputs: complete Holm families replace the
   bounds; this interim file stays as the record of what was known when.
