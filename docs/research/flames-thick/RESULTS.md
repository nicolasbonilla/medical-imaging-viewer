# FLAMeS-thick — results (pre-registered analysis)

*Research, not the medical device. Protocol: `PROTOCOL.md` (pre-registered 2026-10-21; every change in §14,
all logged before the corresponding results existed). Record with every number and every per-scan metric:
`docs/research/records/2026-10-23_flames_thick_results.json` (written by `research/flames_thick/analysis.py`,
unchanged pre-registered code; tables below generated from it by `research/flames_thick/results_tables.py`).*

> **Resumen en español sencillo.** Se volvió a entrenar FLAMeS de dos maneras: A, enseñándole además
> imágenes con cortes gruesos simulados, y B, sin ese truco (control). En los tres hospitales de cortes
> gruesos, A marca algo mejor las lesiones que el FLAMeS original (+0,025 de F1) y da un 19 % menos de
> lesiones falsas. Pero la mejora no llega al mínimo que se fijó de antemano (+0,03), así que el resultado
> principal es **no concluyente**. Además, B hace lo mismo o mejor que A: la mejora viene de reentrenar con
> MSLesSeg, no del truco de los cortes gruesos. Y en resonancias finas de verdad (Ljubljana) A pierde mucho
> (Dice −0,17): **no sirve para la aplicación** según la regla fijada de antemano.

## 1. What was run

- **Models.** A = FLAMeS fold 0 fine-tuned 300 epochs on MSLesSeg-train with the thick-slice augmentation;
  B = the same without it; R = original FLAMeS fold 0; E = original 5-fold ensemble (context). A and B were
  trained on Kaggle's free T4 GPUs (PROTOCOL §14; RUNBOOK §10), `model.tar.gz` SHA-256
  A `54448dd0…f8cc`, B `9b2aab1d…1c62`; the evaluation VMs loaded exactly these checkpoints
  (`checkpoint_final.pth` SHA-256 A `24da7ea8…471c`, B `67b4ab3d…bdf4`, checked against the archives).
- **Evaluation.** Two CPU VMs (`flames-thick-eval-1/-2`, 2026-10-22/23, 212 + 210 case-model maps, 0 errors,
  no test-time mirroring, 68 s per case-model), the 211 pre-registered scans of PROTOCOL §7, all present for
  every arm (none dropped). Input identity: every evaluation FLAIR has the SHA-256 of the reference runs
  (the analysis aborts otherwise); all 211 expert masks identical to the reference masks. Analysis exactly as
  pre-registered (§8–§9): p ≥ 0.5, 18-connected lesions ≥ 3 mm³, Hungarian max-IoU matching (IoU > 0 primary),
  paired percentile bootstrap over patients, B = 10 000, seed 20261021.

## 2. Pre-registered verdicts

| hypothesis | rule (PROTOCOL §9) | result | verdict |
|---|---|---|---|
| **H1** (primary): thick sites, A vs R | ΔF1 CI lower > 0 **and** ΔF1 ≥ +0.03 **and** FP-ratio CI upper ≤ 1.10 | ΔF1 **+0.025 [+0.010, +0.039]**; FP ratio **0.810 [0.763, 0.862]** | **Inconclusive** — the CI excludes 0 and false lesions fall by 19 %, but the point estimate is below the smallest effect of interest (+0.03); not refuted because the CI upper bound (+0.039) exceeds +0.03. No thick site shows harm. |
| **H2**: ~1 mm non-inferiority, A vs R | pooled ΔDice CI lower > −0.02 and ΔF1 CI lower > −0.03; Ljubljana points ΔDice ≥ −0.02, ΔF1 ≥ −0.03 | pooled ΔDice −0.004 [−0.063, +0.054], ΔF1 −0.022 [−0.084, +0.034]; **Ljubljana ΔDice −0.172, ΔF1 −0.181** | **Not shown → A is "not deployable"** (§9.2), whatever H1 says. All four conditions fail. |
| **H3** (S3): augmentation effect, A vs B | ΔF1 (A − B) CI lower > 0 | ΔF1 −0.005 [−0.017, +0.006]; A has more false lesions than B (FP ratio 1.107 [1.051, 1.176]) | **Augmentation effect not shown.** The thick-site gain is explained by fine-tuning on MSLesSeg (B vs R +0.030 [+0.016, +0.044], FP ratio 0.732 [0.688, 0.775]), not by the simulated thickening. |
| S1 expected direction | A lowers the 50 %-detection size on B3/B4 below 50 mm³ | 50 % size stays [50,150) mm³ for every arm on B3 and B4; small-lesion detection [14,50) is *lower* with A (B3 0.38 vs 0.44; B4 0.33 vs 0.42) | **Not observed** (opposite direction for small lesions; gains only for lesions ≥ 150–500 mm³). |

Answer to the question of §1: fine-tuning FLAMeS on MSLesSeg-train with simulated thick slices did **not**
measurably improve lesion-wise detection on real thick-slice FLAIR beyond the pre-set smallest effect, the
thickening itself added nothing over plain fine-tuning, and the model lost performance on true ~1-mm 3D FLAIR.

## 3. All pre-registered numbers

Evaluation set: 211 scans {'mslesseg': 22, 'openms': 10, 'ms3seg': 100, 'muslim': 51, 'pedims': 28}.
Thick sites (H1): MS3SEG, Muslim, PediMS — 179 scans, 160 patients.

### H1 and its sensitivity analyses (A vs R unless stated)
| comparison (thick sites) | scans / patients | mean F1 | ΔF1 [95 % CI] | mean false lesions / scan | FP ratio [95 % CI] |
|---|---|---|---|---|---|
| H1 primary: A vs R, lenient IoU > 0 | 179 / 160 | A 0.632 vs R 0.607 | +0.025 [+0.010, +0.039] | A 11.24 vs R 13.87 | 0.810 [0.763, 0.862] |
| S6 strict matching IoU ≥ 0.10 | 179 / 160 | A 0.606 vs R 0.588 | +0.018 [+0.002, +0.033] | A 12.16 vs R 14.56 | 0.835 [0.787, 0.887] |
| S6 without PediMS P9 (Baló) | 178 / 159 | A 0.632 vs R 0.607 | +0.025 [+0.010, +0.039] | A 11.22 vs R 13.84 | 0.811 [0.762, 0.862] |
| S3 / H3: A vs B (augmentation effect) | 179 / 160 | A 0.632 vs B 0.637 | −0.005 [−0.017, +0.006] | A 11.24 vs B 10.15 | 1.107 [1.051, 1.176] |
| S4: A vs E (5-fold ensemble) | 179 / 160 | A 0.632 vs E 0.632 | +0.000 [−0.013, +0.013] | A 11.24 vs E 11.46 | 0.981 [0.921, 1.048] |
| context: B vs R (fine-tuning without thickening) | 179 / 160 | B 0.637 vs R 0.607 | +0.030 [+0.016, +0.044] | B 10.15 vs R 13.87 | 0.732 [0.688, 0.775] |

Only H1 has a pre-registered verdict; S3 is read with its own rule (effect shown if the ΔF1 CI lower bound
> 0); the other rows are estimates. (The analysis script also prints H1-rule strings for every row:
H1, S6 strict and S6 without P9 are all "inconclusive".) S4: one fine-tuned model matches the original
5-fold ensemble on thick sites (ΔF1 +0.000, FP ratio 0.98) — an estimate, not a verdict.

### H1 per thick site (A vs R)
| site | scans / patients | mean F1 A vs R | ΔF1 [95 % CI] | false lesions A vs R | FP ratio [95 % CI] |
|---|---|---|---|---|---|
| MS3SEG | 100 / 100 | 0.654 vs 0.627 | +0.026 [+0.008, +0.044] | 12.12 vs 13.96 | 0.868 [0.804, 0.939] |
| Muslim | 51 / 51 | 0.556 vs 0.531 | +0.025 [−0.002, +0.052] | 10.35 vs 13.39 | 0.773 [0.679, 0.867] |
| PediMS | 28 / 9 | 0.691 vs 0.673 | +0.018 [−0.030, +0.056] | 9.71 vs 14.43 | 0.673 [0.544, 0.748] |

No site has a ΔF1 CI upper bound < 0 ("success with harm" rule not triggered).

### H2 (~1 mm non-inferiority, A vs R)
| quantity | estimate [95 % CI] | margin | met? |
|---|---|---|---|
| pooled ΔDice (32 scans: Ljubljana clean-10 + MSLesSeg test) | −0.004 [−0.063, +0.054] | CI lower > −0.02 | no |
| pooled ΔF1 | −0.022 [−0.084, +0.034] | CI lower > −0.03 | no |
| Ljubljana clean-10 ΔDice (point) | −0.172 | ≥ −0.02 | no |
| Ljubljana clean-10 ΔF1 (point) | −0.181 | ≥ −0.03 | no |

### S1 detection by lesion size (pooled lesions, patient-bootstrap 95 % CI)
| band | arm | [3,14) | [14,50) | [50,150) | [150,500) | ≥ 500 mm³ | 50 % from | 80 % from |
|---|---|---|---|---|---|---|---|---|
| B1 | R | 0.38 [0.27–0.45] (n 322) | 0.69 [0.60–0.75] (n 519) | 0.80 [0.74–0.86] (n 405) | 0.85 [0.80–0.89] (n 192) | 0.87 [0.77–0.96] (n 92) | [14,50) | [50,150) |
| B1 | E | 0.37 [0.28–0.47] (n 322) | 0.69 [0.59–0.75] (n 519) | 0.81 [0.76–0.86] (n 405) | 0.87 [0.82–0.91] (n 192) | 0.89 [0.80–0.97] (n 92) | [14,50) | [50,150) |
| B1 | A | 0.14 [0.09–0.21] (n 322) | 0.53 [0.40–0.62] (n 519) | 0.75 [0.67–0.82] (n 405) | 0.89 [0.84–0.93] (n 192) | 0.92 [0.85–1.00] (n 92) | [14,50) | [150,500) |
| B1 | B | 0.22 [0.16–0.31] (n 322) | 0.58 [0.47–0.66] (n 519) | 0.78 [0.70–0.85] (n 405) | 0.90 [0.84–0.94] (n 192) | 0.95 [0.90–0.99] (n 92) | [14,50) | [150,500) |
| B2 | R | 0.40 [0.22–0.46] (n 75) | 0.68 [0.53–0.71] (n 324) | 0.79 [0.68–0.86] (n 378) | 0.79 [0.67–0.87] (n 234) | 0.78 [0.73–0.86] (n 93) | [14,50) | never |
| B2 | E | 0.37 [0.20–0.44] (n 75) | 0.67 [0.56–0.70] (n 324) | 0.76 [0.66–0.84] (n 378) | 0.77 [0.63–0.87] (n 234) | 0.80 [0.73–0.91] (n 93) | [14,50) | never |
| B2 | A | 0.27 [0.17–0.31] (n 75) | 0.48 [0.40–0.62] (n 324) | 0.71 [0.63–0.79] (n 378) | 0.79 [0.68–0.86] (n 234) | 0.87 [0.81–0.98] (n 93) | [50,150) | ≥ 500 |
| B2 | B | 0.27 [0.14–0.30] (n 75) | 0.54 [0.49–0.66] (n 324) | 0.71 [0.62–0.79] (n 378) | 0.75 [0.66–0.81] (n 234) | 0.89 [0.85–0.96] (n 93) | [14,50) | ≥ 500 |
| B3 | R | 0.12 [0.03–0.26] (n 48) | 0.44 [0.38–0.50] (n 514) | 0.61 [0.55–0.67] (n 976) | 0.65 [0.60–0.70] (n 673) | 0.76 [0.70–0.82] (n 343) | [50,150) | never |
| B3 | E | 0.12 [0.03–0.26] (n 48) | 0.45 [0.38–0.51] (n 514) | 0.59 [0.54–0.65] (n 976) | 0.66 [0.61–0.70] (n 673) | 0.76 [0.70–0.81] (n 343) | [50,150) | never |
| B3 | A | 0.04 [0.00–0.12] (n 48) | 0.38 [0.32–0.44] (n 514) | 0.54 [0.47–0.61] (n 976) | 0.66 [0.60–0.72] (n 673) | 0.88 [0.84–0.91] (n 343) | [50,150) | ≥ 500 |
| B3 | B | 0.06 [0.00–0.17] (n 48) | 0.36 [0.30–0.42] (n 514) | 0.56 [0.49–0.62] (n 976) | 0.66 [0.59–0.73] (n 673) | 0.85 [0.80–0.89] (n 343) | [50,150) | ≥ 500 |
| B4 | R | 0.15 [0.04–0.31] (n 34) | 0.42 [0.36–0.48] (n 455) | 0.68 [0.64–0.71] (n 1074) | 0.72 [0.66–0.77] (n 713) | 0.72 [0.65–0.79] (n 343) | [50,150) | never |
| B4 | E | 0.21 [0.08–0.40] (n 34) | 0.43 [0.38–0.49] (n 455) | 0.69 [0.65–0.72] (n 1074) | 0.72 [0.66–0.77] (n 713) | 0.70 [0.63–0.78] (n 343) | [50,150) | never |
| B4 | A | 0.12 [0.02–0.26] (n 34) | 0.33 [0.28–0.38] (n 455) | 0.66 [0.63–0.70] (n 1074) | 0.78 [0.73–0.82] (n 713) | 0.87 [0.82–0.91] (n 343) | [50,150) | ≥ 500 |
| B4 | B | 0.06 [0.00–0.16] (n 34) | 0.31 [0.27–0.37] (n 455) | 0.66 [0.61–0.70] (n 1074) | 0.76 [0.71–0.80] (n 713) | 0.85 [0.80–0.89] (n 343) | [50,150) | ≥ 500 |

Bands by slice spacing: B1 ≤ 1.5 mm (Ljubljana, MSLesSeg test; 32 scans), B2 1.5–4.5 (PediMS; 28),
B3 4.5–6.5 (Muslim 45, MS3SEG 31), B4 > 6.5 (MS3SEG 69, Muslim 6). The size tables use 2 000 bootstrap
draws (as written in the analysis code committed before any map existed); every other CI uses 10 000.

### S2 per site (means over scans)
| site | arm | lesion F1 | false lesions / scan | Dice | lesion sensitivity | lesion precision |
|---|---|---|---|---|---|---|
| MS3SEG | R | 0.63 | 13.96 | 0.66 | 0.68 | 0.60 |
| MS3SEG | E | 0.66 | 11.62 | 0.68 | 0.68 | 0.66 |
| MS3SEG | A | 0.65 | 12.12 | 0.65 | 0.69 | 0.65 |
| MS3SEG | B | 0.66 | 10.31 | 0.65 | 0.66 | 0.67 |
| Muslim | R | 0.53 | 13.39 | 0.56 | 0.54 | 0.58 |
| Muslim | E | 0.55 | 11.14 | 0.57 | 0.54 | 0.63 |
| Muslim | A | 0.56 | 10.35 | 0.52 | 0.54 | 0.63 |
| Muslim | B | 0.57 | 9.53 | 0.53 | 0.56 | 0.66 |
| PediMS | R | 0.67 | 14.43 | 0.68 | 0.73 | 0.63 |
| PediMS | E | 0.70 | 11.46 | 0.68 | 0.72 | 0.69 |
| PediMS | A | 0.69 | 9.71 | 0.63 | 0.67 | 0.72 |
| PediMS | B | 0.68 | 10.71 | 0.61 | 0.68 | 0.69 |
| Ljubljana clean-10 | R | 0.68 | 9.40 | 0.65 | 0.60 | 0.80 |
| Ljubljana clean-10 | E | 0.69 | 8.20 | 0.66 | 0.60 | 0.82 |
| Ljubljana clean-10 | A | 0.50 | 5.10 | 0.48 | 0.38 | 0.82 |
| Ljubljana clean-10 | B | 0.58 | 6.40 | 0.52 | 0.49 | 0.82 |
| MSLesSeg test | R | 0.66 | 10.55 | 0.61 | 0.70 | 0.65 |
| MSLesSeg test | E | 0.67 | 10.00 | 0.64 | 0.71 | 0.67 |
| MSLesSeg test | A | 0.71 | 5.95 | 0.68 | 0.68 | 0.77 |
| MSLesSeg test | B | 0.72 | 5.59 | 0.69 | 0.68 | 0.78 |

S2 is reported as point estimates per site (the pre-registered analysis code does not bootstrap them);
MSLesSeg test is in-domain for A and B (same source, protocol and annotators as the training split).

### S5 MSLesSeg test by native FLAIR slice thickness (A − R, means)
| native thickness | scans | ΔF1 | ΔDice |
|---|---|---|---|
| ≤ 3 mm | 15 | +0.015 | +0.016 |
| 4–5 mm | 7 | +0.124 | +0.191 |

### S7 internal-validation pseudo-Dice per epoch (thin, in-domain; forgetting check)
| run | epochs | first | min | median | max | last | nnU-Net final validation Dice (15 scans) |
|---|---|---|---|---|---|---|---|
| flames-thick-a (A) | 300 | 0.819 | 0.799 | 0.824 | 0.846 | 0.820 | 0.737 |
| flames-thick-b (B) | 300 | 0.839 | 0.807 | 0.837 | 0.856 | 0.843 | 0.757 |

No forgetting on the internal (MSLesSeg-train) validation scans; unchanged FLAMeS scores 0.689 on them
(without mirroring; logged in PROTOCOL §14 before training).

## 4. Interpretation (not part of the pre-registered verdicts)

- What fine-tuning changed is mostly **precision**: both fine-tuned models produce 19–27 % fewer false lesions
  on thick sites and detect large lesions better (≥ 500 mm³: 0.85–0.88 vs 0.72–0.76), while detecting fewer
  small ones. That is the opposite of the mechanism the study was designed to test (better small-lesion
  detection on thick slices). A plausible but untested explanation is that the model takes on MSLesSeg's
  annotation style; the protocol's limitations (§11) anticipated this possibility.
- On true thin 3D FLAIR (Ljubljana) both fine-tuned models lose sensitivity (0.60 → 0.49 B, 0.38 A) at
  unchanged precision: the fine-tuning harms thin data and the thickening augmentation makes it worse.
- In-domain (MSLesSeg test) A and B improve clearly (F1 0.71–0.72 vs 0.66; false lesions halved), most on
  scans acquired at 4–5 mm (S5, n = 7): an in-domain gain that does not carry over to other sites.
- No post-hoc analysis was run. The only number computed outside the analysis script is the unchanged-FLAMeS
  baseline on the internal validation scans (0.689), computed and logged before training.

## 5. Consequences

- **App:** do not ship A (or B) as a replacement for FLAMeS: H2 fails (§9.2 "not deployable"). The original
  FLAMeS (and its 5-fold ensemble) stays the segmenter; Paper A's thick-slice caveats stay valid.
- **Paper:** a clean, pre-registered negative/inconclusive result on simulated thick-slice augmentation for
  MS lesion segmentation, with a positive side finding (fewer false lesions after fine-tuning) that would need
  its own pre-registration, preferably with a fine-tuning set that is not in-domain for one evaluation site
  and an explicit thin-FLAIR guard during training.

## 6. Limitations

- Pre-stated (PROTOCOL §11): site, thickness, scanner, population and annotation protocol are confounded at
  the thick sites; B controls for fine-tuning on MSLesSeg labels but not for every confound; Muslim in-plane
  size estimated; PediMS has 9 children; Ljubljana-10 is small (its guard-rail has no CI by design);
  MSLesSeg is itself 2–5 mm native resampled to 1 mm; 3D components on 4–8 mm slices can merge or split
  lesions; one fold, one training seed — run-to-run variance of fine-tuning is not estimated, so small
  differences between A and B (|ΔF1| ≈ 0.005) cannot be separated from it.
- Added by this run (all logged in PROTOCOL §14 before results): training moved to Kaggle (same GPU model,
  code and software; both arms side by side; sessions paused/resumed twice, like preemptions); the pilot's
  pseudo-Dice bar was replaced (single-scan pilot), and the replacement checks all passed.
- H2's pooled estimate mixes an in-domain improvement (MSLesSeg test) with an out-of-domain loss
  (Ljubljana), so its wide CI is expected; the Ljubljana guard-rail alone already fails.
- S2 and S5 are point estimates (no CI) as implemented in the pre-registered code.
