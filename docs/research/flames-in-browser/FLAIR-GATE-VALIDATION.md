# Input-gate validation on public data — FLAIR contrast gate (RC-049) and skull-stripped gate (RC-043)

| | |
|---|---|
| Date | 2026-10-18 |
| Code validated | the shipped TypeScript (`frontend/src/services/flames/pipeline.ts` `checkInputGates`, `contrastGate.ts`, `headerEvidence.ts`, `nifti.ts`) run by the opt-in harness `src/services/flames/__tests__/gateValidation.flames.test.ts` — not a Python re-implementation |
| Raw results | `evidence/gate-validation-2026-10-18.json` (one row per volume: decision, reason, header evidence, every feature) |
| Status | Evidence for REQ-SAFE-033 / RC-043 / RC-049 — DRAFT, PENDING owner approval |

## 1. Data (all public, read locally; nothing uploaded)

| Set | Source / licence | Volumes | Notes |
|---|---|---|---|
| MSLesSeg train + test | figshare 10.6084/m9.figshare.27919209, CC BY 4.0 (`data/external/mslesseg`) | 115 timepoints × FLAIR, T1, T2 | skull-stripped by the dataset authors, registered to MNI 1 mm |
| open_ms_data MNI | Lesjak et al. 2018, CC BY 4.0 (`data/external/open_ms_data/cross_sectional/MNI`) | 30 × FLAIR, T1, T1 post-contrast, T2 | skull-stripped, N4, winsorised, MNI |
| open_ms_data native | same, `cross_sectional/coregistered` (downloaded 6 patients: 01, 05, 10, 15, 20, 25) | 6 × FLAIR, T1, T2 × brain mask | native 3D FLAIR grid (0.8 × 0.47 × 0.47 mm), stripped with the dataset's brain mask |
| With skull | same 6 raw FLAIRs | 6 as distributed (noisy background) + 6 with the background set to zero (largest head component, holes filled) | the reviewer's "skull but zero background" case |

The file name is never used by the gate (the harness passes no series description).

## 2. Rule (as shipped, `flair-gate/1`)

Refused if **any** of:
* border nonzero > 2 % or nonzero region outside 500–2600 mL (pre-existing gate);
* **skull clue A** — > 1 % of the voxels within 6 mm of the region's edge brighter than 1.5 × the tissue mode (scalp fat);
* **skull clue B** — > 20 % of the region darker than 0.25 × the tissue mode (bone, air, enclosed background noise);
* header names another sequence or an inversion time < 1400 ms (never decisive in this data: no volume carried sequence text);
* **T1 rule** — white matter (> 6 mm from CSF) median > 0.96 × the cortex band (1.5–3 mm from CSF) 75th percentile, after a 15 mm local normalisation;
* **T2/PD rule** — > 3.5 % of brain voxels brighter than 1.6 × the tissue mode;
* contrast not measurable (< 500 voxels in either band).

Thresholds were chosen on the same public data (specificity first); there is no separate held-out set, so the numbers
below are apparent performance and likely optimistic for other scanners.

## 3. Results (495 volumes, 0 errors; 95 % Wilson intervals)

### 3.1 FLAIR contrast gate on its own (T1 rule + T2/PD rule + measurability) — RC-049

| | Accepted as FLAIR / refused | Rate |
|---|---|---|
| Skull-stripped **FLAIR**, all sets | 136 of 151 accepted | sensitivity **0.901** [0.843–0.939] |
| — MSLesSeg | 100 / 115 | 0.870 [0.796–0.919] |
| — open_ms_data MNI | 30 / 30 | 1.000 [0.886–1.000] |
| — open_ms_data native | 6 / 6 | 1.000 [0.610–1.000] |
| **T1** (all sets) | 151 of 151 refused | **1.000** [0.975–1.000] |
| **T1 post-contrast** | 30 of 30 refused | 1.000 [0.886–1.000] |
| **T2** | 149 of 151 refused | 0.987 [0.953–0.996] |
| All non-FLAIR | 330 of 332 refused | specificity **0.994** [0.978–0.998] |

The reviewer's case — a skull-stripped T1 — is refused in every one of the 151 T1 volumes (the T1 rule alone refuses
them all). The 15 genuine FLAIRs refused by the T1 rule are all MSLesSeg volumes whose white matter is as bright as
the cortex band (statistic 0.96–1.02); this is a safe failure (no result, reason shown) but it is the main usability
cost of the rule.

### 3.2 Complete input gate as shipped (border/volume + skull clues + contrast) — RC-043 + RC-049

| | Result | Rate |
|---|---|---|
| Skull-stripped FLAIR accepted | 112 of 151 | **0.742** [0.667–0.805] |
| Non-FLAIR refused (T1, T1 post, T2) | 343 of 344 | **0.997** [0.984–0.999] |
| FLAIR **with skull**, as distributed | 6 of 6 refused | 3 of them passed the original border/volume gate |
| FLAIR **with skull, background set to zero** (reviewer's case) | 6 of 6 refused | 4 of them passed the original border/volume gate |
| With-skull total | **12 of 12 refused** [0.757–1.000] | **7 of 12 passed the original gate** → reviewer's suspicion confirmed |

Why stripped FLAIRs were refused (39): skull rim clue 21, rim clue + T1 rule 4, T1 rule 8, pre-existing border/volume
gate 6 (MNI images whose brain touches the field of view; this gate is unchanged).

The only accepted non-FLAIR is MSLesSeg `P71_T2`: it has no bright CSF (share above 1.6× the tissue mode 0.2 %),
i.e. it does not look like a T2 at all (possibly a different weighting stored under that name).

### 3.3 The rim clue finds incomplete skull stripping, not random false alarms

25 stripped FLAIRs (24 MSLesSeg, 1 open_ms native) exceed the 1 % rim limit (values 1.0–5.5 %); the with-skull
images have 3.9–7.9 %. Nine refused volumes were inspected visually (P24_T1, P2_T1, P56, P4_T1, P7_T2, P68, P59,
P8_T2 and open_ms native patient 15): **all nine contain tissue left by the stripping** — orbital fat and eye-muscle
tissue at the skull base, a temporal fragment, or a detached piece of non-brain tissue
(`evidence/gate-rim-refusals-orbits.png`; red = voxels > 1.5× the tissue mode within 6 mm of the edge). FLAMeS was
trained on SynthStrip-stripped FLAIRs; such residual bright tissue is a known source of false "lesions" at the edge.
For comparison, `evidence/gate-skull-zero-background-rim.png` shows the scalp-fat rim of a with-skull FLAIR whose
background was set to zero.

### 3.4 Header evidence

None of the 495 public volumes carries sequence text or an inversion time in its NIfTI header (verdict "none" for
all), so the header rule was exercised only by unit tests (`niftiHeader.test.ts`, `inputGates.test.ts`). In the
app it also uses the series description stored for the file (never the file name).

## 4. Limits (recorded in RMF §5.1 and §7.2, CA-FLAMES-3)

* Thresholds were chosen on the same data: no independent held-out set; MNI-registered data dominate (295 of 302
  stripped volumes); only 6 native-space subjects and 6 with-skull subjects, all from one scanner (open_ms_data).
* Not tested: 2D thick-slice clinical FLAIR, fat-suppressed FLAIR with skull (the rim clue relies on bright scalp
  fat; the dark clue is the fallback), DWI, SWI, PD, T1-FLAIR, paediatric brains, heavy motion.
* A refused FLAIR is a safe failure; an accepted non-FLAIR would not be. The measured specificity is high but the
  interval is wide for rare sequences.

## 5. How to reproduce

```sh
# manifest of cases (local public data + the 6 downloaded open_ms_data patients and their zero-background variants)
python -I research/flames_in_browser/download_openms_native.py <native dir> patient01 patient05 patient10 patient15 patient20 patient25
python -I research/flames_in_browser/make_gate_manifest.py data/external <native dir> cases.json
cd frontend
FLAMES_GATE_MANIFEST=cases.json FLAMES_GATE_OUT=out.json npx vitest run src/services/flames/__tests__/gateValidation.flames.test.ts --pool=threads
# re-apply changed thresholds to recorded features with the shipped decision code:
FLAMES_GATE_REPLAY_IN=out.json FLAMES_GATE_REPLAY_OUT=replay.json npx vitest run src/services/flames/__tests__/gateReplay.flames.test.ts --pool=threads
```
