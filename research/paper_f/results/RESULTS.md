# Paper F — FINAL pre-registered results (2026-10-29): MindGlide, WMH-SynthSeg, SAMSEG and LST-AI vs the FLAMeS ensemble

Research only — not part of the medical device. Analysis exactly as registered in
`docs/research/paper-f/PROTOCOL.md` (v1.0, 2026-10-21) with the deviations of its section 12; the two
entries of 2026-10-29 (SAMSEG analysis set = tier C; Holm over the registered family size) were
committed and pushed in **7a9a24e before any accuracy output of WMH-SynthSeg or SAMSEG was computed**.
Anything not pre-registered is labelled *exploratory*. Supersedes `docs/research/paper-f/RESULTS-interim.md`
(kept unchanged as the record of 2026-10-22; its MindGlide numbers are reproduced here to the last digit).

> **Resumen en español sencillo.** Ninguna de las tres herramientas públicas que funcionan sin
> tarjeta gráfica supera a FLAMeS en las resonancias de cortes gruesos. Todas aciertan
> claramente menos lesiones: MindGlide 0,55 frente a 0,72 de FLAMeS (diferencia −0,17),
> SAMSEG −0,24 y WMH-SynthSeg −0,38. SAMSEG y WMH-SynthSeg marcan muchas menos lesiones falsas
> (−5,2 y −3,9 por estudio), pero solo porque marcan muy poco en general: mucho menos volumen
> de lesión que el experto, y casi nunca encuentran las lesiones pequeñas. En cortes de 1 mm
> FLAMeS también es la mejor (SAMSEG no se probó allí) y LST-AI queda por debajo. FLAMeS sigue siendo
> la mejor opción probada. Como "segunda opinión" solo MindGlide sirve algo para señalar los
> estudios donde FLAMeS falla (exploratorio, aún por validar). Todo el trabajo de este artículo
> costó 12,55 USD de crédito gratuito.

## 1. What was analysed (provenance)

| Item | Value |
|---|---|
| Code | commit **7a9a24e8fa92c83ded210854fd8614f7be4dcd50** (`evaluate.py`, `metrics.py` unchanged in their definitions since 65a95e3/7a4f4f6; additions listed in PROTOCOL.md section 12) — recorded in `run_info.json` before the comparisons were computed |
| Command | `python -I research/paper_f/evaluate.py run --flames-dir data/cohorts/cloud-2026-10/flames --lstai-dir data/cohorts/cloud-2026-10/lstai --tool-dir <toolbench/cohort> --manifests <toolbench/manifests> --tool-cases samseg=results/samseg_tier_c_ids.txt --out research/paper_f/results` (10,000 bootstrap replicates, seed 20261021), then `summarize.py` |
| Inputs | 3,059 files hashed in `run_info.json` (SHA-256 each; digest of the list **d50d356bcd6676b38fb10545f1f0a659a49582ba4d83ad8c5567bdcc9dd0b43b**): 324 expert masks + 1,620 FLAMeS fold maps, 144 LST-AI maps, 324 MindGlide, 179 MindGlide-raw, 324 WMH-SynthSeg, 130 SAMSEG masks, 14 run manifests |
| Outputs | `per_scan.csv.gz` (6,906 rows; uncompressed SHA-256 d6474c58…a6d19; gunzip before re-running `summarize.py`), `comparisons.json` (4b76f37c…), `summary.json`, `tables.md` (all tables; generated) |
| Note on file hashes | `run_info.json` code hashes are of the Windows checkout (CRLF line endings); the VM manifests hash the LF files. The commit hash is the authority |

## 2. Run integrity (`verify_runs.py` → `verify_runs.json`; no accuracy read)

| Tool | Planned cells | Present, SHA-256 = VM record | Failed, never recovered | Failed then re-run OK |
|---|---|---|---|---|
| WMH-SynthSeg (FreeSurfer 8.2.0) | 324 | 324 | 0 | 1 — muslim_16 out of memory (exit 137) → re-run with `--crop` (pre-stated fallback; **this one scan is cropped**) |
| MindGlide 1.3.0, primary arm | 324 | 324 | 0 | 3 — the pilot scans (pilot setup error, fixed) |
| MindGlide, raw-input arm 7.6 | 179 | 179 | 0 | 3 — muslim_49/50/51 (10 h guard of `toolbench-mgraw`) |
| SAMSEG `--lesion`, tier C | 129 | 128 + 1 (below) | 0 | 0 |

- **SAMSEG tier C** = all PediMS (28) + all Muslim (51) + MS3SEG odd ids (50) = `plan_budget.tier_c_ids()`;
  identical to the union of the three VMs' case lists (`samseg_tier_c_ids.txt`). Blocks a/b/c: 42/43/42
  done, 0 errors; ms3seg_001 and pedims_P1_T1 came from the two FreeSurfer pilots.
- **ms3seg_001 (SAMSEG)** has no manifest record: the first pilot's manifest write crashed right after
  this case (numpy integer, fixed in 96bd925), so its SHA-256 was never recorded. Log line: "done in
  607 s, identity, 1129 lesion voxels"; the bucket file (written 15:47:38 UTC at the pilot's end) is
  binary, on the FLAMeS grid and has exactly 1,129 lesion voxels. Kept (PROTOCOL.md section 9).
- One SAMSEG output lies outside the tier (mslesseg_P10_T1, isotropic pilot scan): enters no comparison.
- 0 input SHA-256 mismatches against `flames_inputs.json`; `input_problems` empty in every run; no
  `TOOL DROPPED`; FreeSurfer and MindGlide image digests and the MindGlide weights as pinned; WMH model
  790,531,383 bytes, SHA-256 0ece39dd…5988 = the bucket mirror; no VM left in mstool-research.
- **Structural check** (`structural_check_{samseg,wmhsynthseg}.json`): 130/130 SAMSEG and 324/324
  WMH-SynthSeg PASS (exact FLAMeS grid, binary, probability in [0, 1]). Plausibility warnings (not
  failures): SAMSEG 8 (all near-empty predictions, 0–0.5 mL; median Dice 0.52), WMH-SynthSeg 40 (Dice
  < 0.1, spread over all five cohorts, per-cohort medians 0.21–0.31: no orientation or label error).

## 3. Pre-registered results

### 3.1 Primary family (thick band; Holm over 6 — complete)

| Tool vs FLAMeS | Scans / patients | Δ lesion F1 (95% CI) | Holm p | Δ false lesions / scan (95% CI) | Holm p | Reading (7.1) |
|---|---|---|---|---|---|---|
| MindGlide | 179 / 160 | **−0.170** (−0.206 to −0.136) | < 0.0001 | +0.57 (−0.89 to +2.21) | 0.45 | does **not** outperform; FLAMeS higher F1; false lesions: no difference shown, not equivalent |
| WMH-SynthSeg | 179 / 160 | **−0.384** (−0.424 to −0.344) | < 0.0001 | **−3.88** (−5.21 to −2.27) | < 0.0001 | does **not** outperform: fewer false lesions, but ΔF1 far below −0.05 |
| SAMSEG (tier C) | 129 / 110 | **−0.237** (−0.304 to −0.173) | < 0.0001 | **−5.15** (−6.30 to −3.91) | < 0.0001 | does **not** outperform: fewer false lesions, but ΔF1 far below −0.05 |

No tool is equivalent to FLAMeS (no 90% CI inside ±0.05 F1 and ±1 false lesion). Every sensitivity
analysis S1–S7 (`tables.md`, Table 5) keeps the sign and significance of ΔF1 for all three tools
(range −0.15 to −0.44) and of the fewer false lesions for WMH-SynthSeg and SAMSEG; for MindGlide, false
lesions become significantly *more* without the size filter (+2.4) and with in-plane components (+8.1).

Why the two FreeSurfer tools have fewer false lesions: they mark far less lesion overall (thick band,
predicted vs expert volume: WMH-SynthSeg 4.2–5.2 mL vs 12.7–19.8 mL; SAMSEG 6.8–9.8 mL vs 12.6–19.8 mL;
FLAMeS 13.1–18.4 mL) and detect few small lesions (expert lesions 14–50 mm³ detected: FLAMeS 0.49,
MindGlide 0.22, SAMSEG 0.06, WMH-SynthSeg 0.05; Table 4). Lesion recall on thick scans: FLAMeS
0.65–0.83, SAMSEG 0.30–0.45, WMH-SynthSeg 0.23–0.26 (Table 1).

### 3.2 Secondary family 7.2 (registered size 11; 8 run, 3 not run; Holm with not-run = p 1)

| Comparison | Scans | Estimate (95% CI) | Holm p (registered 11) | Reading |
|---|---|---|---|---|
| MindGlide vs FLAMeS, iso, ΔF1 | 125 | −0.272 (−0.319 to −0.229) | < 0.0001 | FLAMeS better |
| MindGlide vs FLAMeS, iso, Δ false lesions | 125 | +3.07 (+1.78 to +4.32) | < 0.0001 | MindGlide more false lesions |
| WMH-SynthSeg vs FLAMeS, iso, ΔF1 | 125 | −0.363 (−0.429 to −0.297) | < 0.0001 | FLAMeS better |
| WMH-SynthSeg vs FLAMeS, iso, Δ false lesions | 125 | −1.32 (−2.58 to −0.23) | **0.086** | not significant after correction (see note) |
| LST-AI vs FLAMeS, iso, ΔF1 | 124 | −0.180 (−0.212 to −0.150) | < 0.0001 | FLAMeS better |
| LST-AI vs FLAMeS, iso, Δ false lesions | 124 | +3.79 (+2.53 to +4.95) | < 0.0001 | LST-AI more false lesions |
| Degradation (Δ thick − Δ iso), MindGlide, F1 | 304 | +0.102 (+0.047 to +0.160) | < 0.0001 | MindGlide loses less than FLAMeS when slices thicken (but stays below it) |
| Degradation, WMH-SynthSeg, F1 | 304 | −0.021 (−0.098 to +0.056) | 1.0 | no difference shown |
| SAMSEG vs FLAMeS, iso, ΔF1 / Δ false lesions; SAMSEG degradation | 0 | **not run** (tier C is thick-only) | — | — |

Note (reported because it matters): the rule fixed on 2026-10-29 before analysis counts the 3 not-run
tests as p = 1. Holm over only the 8 tests performed would give p = 0.034 for WMH-SynthSeg's fewer
false lesions on iso scans. The registered rule governs: **not significant**.

### 3.3 Raw-input arm 7.6 (thick band; Holm over 4 — complete; same as the interim)

MindGlide on the FLAIR with skull vs FLAMeS: ΔF1 −0.186 (−0.222 to −0.150), Holm p < 0.0001; Δ false
lesions +0.38 (−0.94 to +1.88), Holm p 0.99. Raw vs skull-stripped MindGlide: ΔF1 −0.016 (−0.028 to
−0.004), Holm p 0.037, **equivalent** within ±0.05; Δ false lesions −0.19 (−0.75 to +0.32),
**equivalent** within ±1. Skull stripping did not handicap MindGlide.

### 3.4 Hypotheses — verdicts

| Hypothesis (PROTOCOL.md section 1 / 7) | Verdict |
|---|---|
| P: a public CPU tool (MindGlide, WMH-SynthSeg, SAMSEG) outperforms the FLAMeS ensemble on thick-slice FLAIR | **Not supported** for any tool — FLAMeS has a significantly higher lesion F1 than all three |
| P (equivalence): a tool is equivalent to FLAMeS on thick slices | **Not supported** — none within the margins |
| S-a: a tool matches or beats FLAMeS on 1 mm FLAIR (incl. LST-AI) | **Not supported** — FLAMeS significantly better on F1 vs MindGlide, WMH-SynthSeg, LST-AI; SAMSEG not run |
| S-b: a tool degrades less than FLAMeS from 1 mm to thick slices | **Supported for MindGlide** (+0.10 F1, smaller loss, still below FLAMeS); **inconclusive** for WMH-SynthSeg; SAMSEG not run |
| 7.6: skull stripping handicaps MindGlide | **Not supported** — raw and stripped inputs equivalent |
| S-c (exploratory): disagreement with a second tool flags scans where FLAMeS is poor | **Exploratory only**: promising for MindGlide (AUROC 0.78, 14 poor scans), not for WMH-SynthSeg (0.59) or SAMSEG (0.49) |

## 4. Exploratory (7.5; not confirmatory)

| Tool | Band | E1 AUROC: disagreement flags FLAMeS lesion F1 < 0.5 | E2 keep only FLAMeS lesions the tool also marks, minus FLAMeS alone |
|---|---|---|---|
| MindGlide | thick | 0.779 (14 poor of 179) | F1 −0.074 (−0.111 to −0.040); false lesions −3.8 (−4.7 to −2.8) |
| WMH-SynthSeg | thick | 0.593 (14 poor of 179) | F1 −0.278; false lesions −5.9 |
| SAMSEG | thick | 0.488 (11 poor of 129) | F1 −0.177; false lesions −6.1 |
| MindGlide / LST-AI / WMH-SynthSeg | iso | 0.81 / 0.80 / 0.52 (only 2 poor scans) | F1 −0.106 / −0.033 / −0.303 |

Every "confirmed lesions" filter removes false lesions but costs lesion F1; none is a free gain. The
iso AUROCs rest on 2 poor scans.

## 5. Runtime, memory and cost (descriptive; compute ledger, branch `research/cloud-compute-ledger`)

| Tool | Median per scan (4 vCPU) | Peak memory | CPU rule (≤ 15 min) |
|---|---|---|---|
| MindGlide (stripped) | 77–84 s | 5.5 GB | pass |
| MindGlide raw (E2 machines) | 253–286 s | — | pass |
| WMH-SynthSeg | 216 s (n2d-highmem-4) | 31.3 GB + up to 14.4 GB swap | pass (memory-hungry) |
| SAMSEG `--lesion` | thick 470–524 s (7.8–8.7 min, run medians); the one 1 mm scan (pilot) 556 s | ≤ 7.1 GB | pass |

Paper F total: 14 VM runs, 61.9 VM-hours, **12.55 USD at list price** (cap 15 USD; the tier rule had
projected 13.76). SAMSEG ran on tier C because of the pre-stated budget rule (pilot projection × 1.25
safety), not the CPU rule. With the real cost (~0.027 USD per SAMSEG scan), tier B (179 thick scans)
would have fitted (≈ 13.9 USD in total) and tier A (all 324) would not (≈ 17.8 USD).

## 6. Limitations

- SAMSEG covers 129 of 179 thick scans (tier C; MS3SEG odd ids only) and no 1 mm scan. Its comparison
  with FLAMeS is paired on the same 129 scans; comparisons *between* SAMSEG and the other tools are not
  on identical scan sets.
- All tools received the skull-stripped FLAMeS input (identical-input rule). SAMSEG's atlas registration
  is documented to prefer images with skull; its under-segmentation may partly reflect that. Only
  MindGlide was also tested on raw input (no effect).
- WMH-SynthSeg labels white-matter hyperintensities, not MS lesions specifically; MS3SEG's experts
  exclude periventricular "normal" WMH. muslim_16 was processed with `--crop`.
- MSLesSeg and Ljubljana are skull-stripped 1 mm MNI images; 20 Ljubljana scans were in FLAMeS training
  and are excluded from FLAMeS comparisons (S5 includes them: same conclusions).
- Muslim in-plane spacing is estimated (S6 without Muslim agrees). Expert masks follow each cohort's
  own protocol. The iso-band and second-opinion analyses rest on few poor FLAMeS scans.
- The cohort-weighted thick estimate gives PediMS (9 children) the same weight as MS3SEG (100); S7
  (scan-weighted) agrees.
