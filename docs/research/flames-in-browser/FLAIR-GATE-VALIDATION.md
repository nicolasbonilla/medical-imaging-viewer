# Input-gate validation on public data — FLAIR gate (RC-049) and skull-stripped gate (RC-043)

| | |
|---|---|
| Date | 2026-10-18 (re-review 2 of PR #53) |
| Gate validated | `flair-gate/2` — the shipped TypeScript (`frontend/src/services/flames/pipeline.ts` `checkInputGates`, `contrastGate.ts`, `headerEvidence.ts`, `nifti.ts`). Features recorded by the opt-in harness `src/services/flames/__tests__/gateValidation.flames.test.ts`; decisions re-applied by the shipped decision code in `gateReplay.flames.test.ts`. No Python re-implementation of the decision. |
| Raw results | `evidence/gate-validation-2026-10-18.json` (495 volumes, MSLesSeg + open_ms_data, features + the `flair-gate/1` decisions at recording time) · `evidence/gate-validation-isbi2015-2026-10-18.json` (38 volumes, ISBI-2015) · `evidence/gate-flair-gate-2-2026-10-18.json` (`flair-gate/2` replay of all 533 volumes, with and without positive evidence, and the leave-one-dataset-out results) |
| Status | Evidence for REQ-SAFE-033 / RC-043 / RC-049 — DRAFT, N. G. Bonilla Vargas — approved 2026-10-30 (PR #70) |

## 0. What the re-review found, and the corrections

1. **Content alone does not generalise.** On ISBI-2015 — a scanner not used to set the `flair-gate/1` thresholds — the
   complete `flair-gate/1` gate **accepted 10 of 19 skull-stripped T1 as FLAIR** (white-matter/cortex statistic
   0.91–0.94, under its 0.96 limit); the other 9 were refused only by the skull clues. Confirmed on the recorded rows
   (`gate-validation-isbi2015-2026-10-18.json`, field `accepted`).
2. **A number was quoted for the wrong thing.** The PR body and the earlier version of this file said the gate
   "accepts 136/151 good FLAIR". 136/151 was the **contrast part alone**. The **complete `flair-gate/1` gate**
   (border/volume + skull clues + contrast) accepted **112 of 151** skull-stripped FLAIRs (0.742 [0.667–0.805]) and
   refused 343 of 344 non-FLAIR volumes (MSLesSeg `P71_T2` was accepted). Every figure in this file, the PR, the
   review response and the RMF now states which gate it measures.

**Redesign (`flair-gate/2`).** The image content can only **refuse**. A FLAIR is accepted only with **positive
evidence** as well, and the gate fails closed without it:

* **the clinician's explicit confirmation**, given per file before each run ("I confirm that the selected image is a
  skull-stripped T2-FLAIR (not T1, T2, PD or post-contrast)"). It is recorded with the draft (`sequence_evidence =
  clinician`); the server stores who confirmed (`sequence_confirmed_by`) from the authenticated user, never from the
  client; or
* **a file header that proves an inversion-recovery FLAIR**: an inversion time ≥ 1400 ms and nothing naming another
  sequence (`sequence_evidence = header`). A "FLAIR" text label alone is **not** proof — 15 of the 19 ISBI-2015 FLAIR
  files carry such a label (`2020601_flair1_clo`), but any converter or person can write one.

Content thresholds were also re-fitted on all three datasets, and a second T1 rule was added (below).

## 1. Data (all public, read locally; nothing uploaded)

| Set | Source / licence | Volumes | Notes |
|---|---|---|---|
| MSLesSeg train + test | figshare 10.6084/m9.figshare.27919209, CC BY 4.0 (`data/external/mslesseg`) | 115 timepoints × FLAIR, T1, T2 | skull-stripped by the dataset authors, registered to MNI 1 mm |
| open_ms_data MNI | Lesjak et al. 2018, CC BY 4.0 (`data/external/open_ms_data/cross_sectional/MNI`) | 30 × FLAIR, T1, T1 post-contrast, T2 | skull-stripped, N4, winsorised, MNI |
| open_ms_data native | same, `cross_sectional/coregistered` (6 patients: 01, 05, 10, 15, 20, 25) | 6 × FLAIR, T1, T2 × brain mask | native 3D FLAIR grid, stripped with the dataset's brain mask |
| With skull | same 6 raw FLAIRs | 6 as distributed + 6 with the background set to zero | the first review's "skull but zero background" case |
| **ISBI-2015** longitudinal MS challenge | challenge data (registration; not redistributed), local copy `data/cohorts/isbi19-lstai` prepared for an earlier LST-AI evaluation | 19 × FLAIR, T1 | skull-stripped; a third scanner/site |

No other local public set has the image volumes needed (the SibBMS cohort holds only label maps). The file name is
never used by the gate (the harness passes no series description).

## 2. Rule as shipped (`flair-gate/2`)

Refused if **any** of:

* border nonzero > 2 % or nonzero region outside 500–2600 mL (pre-existing gate);
* **skull clue A** — > 1 % of the voxels within 6 mm of the region's edge brighter than 1.5 × the tissue mode;
* **skull clue B** — > 20 % of the region darker than 0.25 × the tissue mode;
* the header names another sequence, or an inversion time < 1400 ms;
* contrast not measurable (< 500 voxels in either band);
* **T1 rule 1** — white matter (> 6 mm from CSF) median > **0.915** × the cortex-band 75th percentile, after a 15 mm
  local normalisation (was 0.96);
* **T1 rule 2 (new)** — more than **27 %** of the brain in the darker grey-matter class (0.45–0.8 × the tissue mode),
  the pattern of the ISBI-2015 T1 volumes;
* **T2/PD rule** — > **2.5 %** of brain voxels brighter than 1.6 × the tissue mode (was 3.5 %);
* **no positive evidence** — neither the clinician's confirmation of the sequence nor a header with a FLAIR inversion
  time.

The three content thresholds are the largest values that refuse **100 %** of the T1, T1 post-contrast and T2 volumes of
all three datasets with the content rule alone (specificity first; `research/flames_in_browser/gate_lodo.py`, grid
search). On these data they are therefore apparent (in-sample) values; §3 is the out-of-sample estimate.

## 3. Leave-one-dataset-out: what content alone does on an unseen scanner

Each dataset in turn is held out; the thresholds are fitted on the other two exactly as above (100 % training
specificity of the content rule, then most FLAIRs accepted) and evaluated on the held-out one. "Full gate" adds the
fixed skull clues and border/volume refusals. 95 % Wilson intervals. Every row assumes the clinician confirmed every
volume as a FLAIR — i.e. it measures the content check as the **second barrier** after a wrong confirmation.

| Held out | Thresholds from the other two (T1 rule 1 / T1 rule 2 / T2 rule) | Content only: FLAIR accepted | Content only: non-FLAIR refused | Full gate: FLAIR accepted | Full gate: non-FLAIR refused | Let through (full gate) |
|---|---|---|---|---|---|---|
| ISBI-2015 | 0.915 / 0.59 (off) / 0.025 | 13/19 · 0.684 [0.46–0.85] | 18/19 · 0.947 [0.75–0.99] | 12/19 · 0.632 [0.41–0.81] | **18/19 · 0.947 [0.75–0.99]** | `case007` T1 |
| MSLesSeg | 0.96 / 0.27 / 0.085 | 93/115 · 0.809 [0.73–0.87] | 197/230 · 0.857 [0.81–0.90] | 70/115 · 0.609 [0.52–0.69] | **229/230 · 0.996 [0.98–1.00]** | `P71_T2` |
| open_ms_data | 0.915 / 0.27 / 0.025 | 36/36 · 1.000 [0.90–1.00] | 102/102 · 1.000 [0.96–1.00] | 35/36 · 0.972 [0.86–0.99] | **102/102 · 1.000 [0.96–1.00]** | none |
| Pooled over the three held-out runs | — | — | 317/351 · 0.903 [0.87–0.93] | 117/170 · 0.688 [0.62–0.75] | 349/351 · 0.994 [0.98–1.00] | 2 |

Findings:

* **No content threshold guarantees that a T1/T2 of an unseen scanner is refused.** With ISBI-2015 held out, the
  second T1 rule is not learned at all (0.59 = the top of the grid, i.e. off) and `case007` T1 passes; with MSLesSeg
  held out, the content rule lets 33 T2 through (the skull clues catch all but `P71_T2`). The second T1 rule exists
  only because ISBI-2015 was seen; another scanner can fail in another way.
* This is why `flair-gate/2` makes content **refusal-only** and requires positive evidence (§0).
* The same analysis with thresholds fitted for the full gate instead of content alone (`--objective full`, in the
  evidence file) is no better: ISBI-2015 18/19, MSLesSeg 228/230, open_ms_data 102/102 non-FLAIR refused.

## 4. The shipped gate on all 533 volumes (replay of the shipped decision code)

### 4.1 Without positive evidence (no confirmation, no header with a FLAIR inversion time)

**0 of 170** skull-stripped FLAIRs and **0 of 351** non-FLAIR volumes accepted; 12 of 12 with skull refused. Every
dataset: nothing passes. (No public volume carries an inversion time; ISBI-2015's "flair" labels are not proof.)

### 4.2 Assuming the clinician confirmed every volume as a FLAIR (the most permissive legal input)

| | FLAIR accepted (sensitivity) | non-FLAIR refused (specificity) | with skull refused |
|---|---|---|---|
| ISBI-2015 | 12/19 · 0.632 [0.41–0.81] | 19/19 · 1.000 [0.83–1.00] | — |
| MSLesSeg | 40/115 · 0.348 [0.27–0.44] | 230/230 · 1.000 [0.98–1.00] | — |
| open_ms_data | 35/36 · 0.972 [0.86–0.99] | 102/102 · 1.000 [0.96–1.00] | 12/12 |
| **All** | **87/170 · 0.512 [0.44–0.59]** | **351/351 · 1.000 [0.99–1.00]** | **12/12 · [0.76–1.00]** |

These are **apparent** values (thresholds fitted on the same 533 volumes); §3 is the honest out-of-sample estimate of
the content barrier (about 0.95–1.00 per unseen dataset, one T1 let through on ISBI-2015).

ISBI-2015 T1 under `flair-gate/2`: 9 refused by the skull clues, 9 by T1 rule 1, 1 by T1 rule 2 (all 19 are also
refused by the content rule alone). Why stripped FLAIRs are refused (83): T1 rule 1 — 44 (MSLesSeg 38, ISBI 6),
skull clues 26, T1 rule 2 — 6, border/volume 6, T2 rule 1.

**Availability cost.** Only about half of genuine FLAIRs are accepted, about a third on MSLesSeg (its white matter is
often as bright as the cortex band). A refused FLAIR is a safe failure (no result, the reason is shown) but the
prototype is of limited use on such data. This is recorded as a limitation, not hidden.

## 5. What is guaranteed and what is not

| Claim | Basis |
|---|---|
| Without positive evidence nothing is accepted (fail closed). | Code: `decideFlairContrast` returns "not confirmed as FLAIR" unless `clinicianConfirmedFlair` or `headerProvesFlair`; the worker refuses a result without `sequenceEvidence`. Tests: `inputGates.test.ts` (rc049 "refuses even a FLAIR-looking image without positive evidence", "a FLAIR label alone is not"). Data: §4.1, 0/521. Negative controls E1, E3. |
| The confirmation is per file, explicit, and recorded with who gave it. | `BrowserFlamesCard` (run disabled until ticked; reset when the file changes), `useBrowserFlames` (forwards it only when given), backend `create_segmentation` (`sequence_confirmed_by` = authenticated user). Tests: card rc049, hook rc049, backend rc047. Negative controls E4, E5, E6, B10. |
| A T1/T2 that a clinician wrongly confirmed is still refused by content. | **Not guaranteed.** Second barrier only: §3, about 0.95–1.00 per unseen dataset (ISBI-2015 18/19). Residual risk in RMF HAZ-001 / RC-049 and CA-FLAMES-3. |

## 6. The rim clue finds incomplete skull stripping, not random false alarms

25 stripped FLAIRs (24 MSLesSeg, 1 open_ms native) exceed the 1 % rim limit (values 1.0–5.5 %); the with-skull
images have 3.9–7.9 %. Nine refused volumes were inspected visually: **all nine contain tissue left by the stripping**
(orbital fat and eye-muscle tissue, a temporal fragment, a detached piece of non-brain tissue;
`evidence/gate-rim-refusals-orbits.png`). `evidence/gate-skull-zero-background-rim.png` shows the scalp-fat rim of a
with-skull FLAIR whose background was set to zero.

## 7. Header evidence

No public volume carries an inversion time or a DICOM extension. ISBI-2015 FLAIR files carry a "flair" text label
(15 of 19); under `flair-gate/2` that label is recorded as supporting information but is not proof. The header rules
(refuse on another sequence or a short inversion time; prove only with an inversion time ≥ 1400 ms) are exercised by
unit tests (`niftiHeader.test.ts`, `inputGates.test.ts`). In the app the header also uses the series description
stored for the file (never the file name).

## 8. Limits (recorded in RMF §5.1 and §7.2, CA-FLAMES-3)

* Three datasets only (two MNI-registered); only 6 native-space and 6 with-skull subjects, from one scanner.
* §3 shows the content barrier is not guaranteed on an unseen scanner; the shipped thresholds are in-sample.
* The clinician's confirmation is a human control and can be wrong; the content barrier then refuses most but not all
  wrong inputs (§3).
* Not tested: 2D thick-slice clinical FLAIR, fat-suppressed FLAIR with skull, DWI, SWI, PD, T1-FLAIR, paediatric
  brains, heavy motion.
* About half of genuine FLAIRs are refused (§4.2): safe, but a usability limit.

## 9. How to reproduce

```sh
# 1) record features with the shipped gate (opt-in harness; local public data)
python -I research/flames_in_browser/download_openms_native.py <native dir> patient01 patient05 patient10 patient15 patient20 patient25
python -I research/flames_in_browser/make_gate_manifest.py data/external <native dir> cases.json
cd frontend
FLAMES_GATE_MANIFEST=cases.json FLAMES_GATE_OUT=out.json npx vitest run src/services/flames/__tests__/gateValidation.flames.test.ts --pool=threads
# 2) replay the shipped decision code on the committed rows (with / without positive evidence)
E=../docs/research/flames-in-browser/evidence
FLAMES_GATE_REPLAY_IN=$E/gate-validation-2026-10-18.json,$E/gate-validation-isbi2015-2026-10-18.json \
  FLAMES_GATE_REPLAY_EVIDENCE=clinician FLAMES_GATE_REPLAY_OUT=replay.json \
  npx vitest run src/services/flames/__tests__/gateReplay.flames.test.ts --pool=threads   # and FLAMES_GATE_REPLAY_EVIDENCE=none
# 3) leave-one-dataset-out
cd .. && python -I research/flames_in_browser/gate_lodo.py $E/gate-validation-2026-10-18.json $E/gate-validation-isbi2015-2026-10-18.json --objective content --out lodo.json
```

The replay and the leave-one-dataset-out numbers above were produced from the committed evidence files with these
commands; they match the run on the raw harness output exactly.
