# Paper C pilot — results of the pre-registered analysis

*Research code and research findings, not the medical device. Date: 2026-10-21.*

- Protocol: `PROTOCOL.md`, committed before any detector output (6233b4b); entry 1 (implementation
  clarifications) before outcomes; entry 2 (run disclosures, post-hoc checks) after; entry 3 (arm
  A4 inputs) committed before A4 was computed (efb203f). The 2026-10-22 re-run reproduced every
  A1–A3 number and the transport analysis identically.
- Records: `docs/research/records/2026-10-21_paper_c_{inventory,flames_overlap_longitudinal,pilot,
  verify_primary,posthoc}.json|_output.txt`. Candidate cache SHA-256 is in the pilot record.
- Code: `research/paper_c/` (11 synthetic tests pass, including validity simulations of the
  thresholds). The four primary cells were recomputed by a separate code path
  (`verify_primary.py`): identical counts. No independent re-implementation of the candidate
  extraction was done.
- Terms. *False call* = a selected candidate that does not overlap the truth change region.
  *FWER* = share of patients with ≥ 1 false call (in a stable patient this is exactly a false
  activity call). *True flag* = patient flagged by ≥ 1 true candidate. Intervals: exact
  Clopper–Pearson 95 % over patients (FWER, true flag); patient-cluster bootstrap 95 % (lesion
  sensitivity, false calls per patient). *Violated* = CP lower bound > α; otherwise "no violation
  detected" (with 20–25 patients this can only exclude gross failures).

---

## 0. Bottom line

**Update 2026-10-22 — arm A4 (FLAMeS maps from the cloud job; inputs logged in protocol entry 3
before analysis; A1–A3 re-ran identically).** On the open_ms patients with **expert** change
masks, the app's own rule on FLAMeS plus the app's own subtraction score gives:
- the conformal threshold keeps the per-patient false-call rate on target — **0.10 (2/20)
  [0.01, 0.32] at α = 0.1 and 0.20 (4/20) [0.06, 0.44] at α = 0.2** — while **20/20 patients
  [0.83, 1.00] are still flagged by a real change** and **28 % [18, 38] of the expert-marked
  new/enlarging lesions** (≥ 3 mm) are kept at α = 0.1 (31 % [19, 41] at α = 0.2); false calls
  drop from 8.9 to 0.15 per patient. Candidate AUROC 0.84 [0.75, 0.90].
- **The app's current rule, against expert masks:** ≥ 1 false new/enlarging candidate in
  **20/20 patients [0.83, 1.00]**, 8.9 [5.8, 12.6] per patient; with the app's subtraction
  confirmation 19/20 [0.75, 1.00], 5.4 [3.5, 7.7] per patient. This confirms the MSLesSeg finding
  (25/25) with real expert change masks.
- Caveats: A4 is a pre-registered *secondary* arm, so the pre-registered go/no-go (primary cells
  A1/A2) stays **NO-GO**; the reading "the method works with the FLAMeS rule when acquisitions are
  consistent" is an interpretation, not a pre-registered test. All 20 patients are highly active
  (446 expert lesions ≥ 3 mm), so "20/20 flagged" is easy; for a patient with a single new lesion
  the lesion-level figure (~0.3) is the better guide. No stable patients, n = 20, wide intervals.
  See §2b.

1. **No stable patients could be studied.** All 20 open_ms longitudinal patients have
   expert-marked change, and 25/25 MSLesSeg first pairs are active under the approximate truth.
   The target quantity, P(false activity | stable), is **not measured** by this pilot; it was
   replaced (pre-registered) by the per-patient probability of ≥ 1 false new/enlarging call.
2. **Validity: no violation detected in any of the 4 primary cells**, and the realised rates sit
   at the nominal level, as split-conformal theory predicts: open_ms 2/20 = 0.10 [0.01, 0.32] at
   α = 0.1 and 4/20 = 0.20 [0.06, 0.44] at α = 0.2; MSLesSeg 2/25 = 0.08 [0.01, 0.26] and
   5/25 = 0.20 [0.07, 0.41]. The intervals are wide; this shows the procedure is not grossly
   broken, nothing more.
3. **The guarantee is bought by abstention.** At α = 0.2 the conformal threshold flags *by a true
   change* 0/20 open_ms patients (model-free subtraction score) and 5/25 MSLesSeg patients (the
   app's rule on FLAMeS + subtraction score; lesion sensitivity 0.07 [0.01, 0.14]). Pre-registered
   go/no-go: **NO-GO — redesign the score before requesting MSSEG-2 time.** The secondary score
   (FLAMeS probability change, S_dp) does better (10/25 = 0.40 [0.21, 0.61] flagged by a true
   change at α = 0.2, 7/25 at α = 0.1) but still below the 0.5 bar.
4. **The app's current rule over-calls** (pre-registered criterion met). On FLAMeS masks of
   MSLesSeg, `activity_candidate`'s candidate set contains ≥ 1 false new/enlarging lesion in
   **25/25 patients (1.00 [0.86, 1.00]), 8.2 [6.3, 10.4] false calls per patient**;
   with the app's subtraction confirmation still 25/25 and 3.7 per patient; a fixed 0.5 SD bar on
   all candidates 19/25 = 0.76 [0.55, 0.91]. Caveat: the MSLesSeg truth is approximate (§6), so
   part of these "false" calls may be real change missed by per-timepoint annotation.
5. **Transfer assumption (Q4) neither supported nor contradicted:** the largest false score does
   not grow with disease change (Spearman ρ = 0.04, p = 0.87 open_ms; −0.03, p = 0.88 MSLesSeg).
   So there is no evidence that calibrating on active patients is conservative for stable ones —
   the stable-conditional calibration on MSSEG-2 remains necessary.

## 1. Data and candidates

| arm | data (units) | detector / score | candidates (true) | per patient, median | patients with ≥ 1 false candidate | candidate AUROC [95 %] |
|---|---|---|---|---|---|---|
| A1 | open_ms longitudinal, 20 patients, expert change | D-sub / S_sub | 476 (185) | 23 | 19/20 | **0.40** [0.34, 0.46] |
| A2 | MSLesSeg first pairs, 25, approx. truth | app rule on FLAMeS / S_sub | 327 (119) | 11 | 25/25 | 0.70 [0.63, 0.78] |
| A2b | same | app rule on FLAMeS / S_dp | 327 (119) | 11 | 25/25 | 0.72 [0.63, 0.80] |
| A3 | same | D-sub / S_sub | 1264 (56) | 31 | 24/25 | 0.55 [0.40, 0.69] |
| A4 | open_ms longitudinal, 20, expert change | app rule on FLAMeS / S_sub | 390 (212) | 14 | 20/20 | **0.84** [0.75, 0.90] |
| A4b | same | app rule on FLAMeS / S_dp | 390 (212) | 14 | 20/20 | 0.76 [0.67, 0.82] |

Truth: open_ms 835 expert change components (500 brighter at follow-up); MSLesSeg first pairs:
every pair active (inventory record).

## 2. Primary cells (CF-M, leave-one-patient-out)

| arm | α | per-patient false-call rate [CP 95 %] | class | flagged by a true change | lesion sensitivity [boot 95 %] | false calls / patient | median threshold |
|---|---|---|---|---|---|---|---|
| A1 | 0.1 | 0.10 (2/20) [0.01, 0.32] | no violation detected | 0/20 | 0.000 | 0.20 | 4.06 SD |
| A1 | 0.2 | 0.20 (4/20) [0.06, 0.44] | no violation detected | 0/20 | 0.000 | 0.30 | 3.89 SD |
| A2 | 0.1 | 0.08 (2/25) [0.01, 0.26] | no violation detected | 1/25 | 0.004 [0.000, 0.012] | 0.16 | 4.90 SD |
| A2 | 0.2 | 0.20 (5/25) [0.07, 0.41] | no violation detected | 5/25 | 0.070 [0.012, 0.136] | 0.36 | 1.48 SD |

All four cells are "bought by abstention" or "intermediate" (A2, α = 0.2: 0.20 exactly) under the
pre-registered usefulness rule; none is informative (≥ 0.5).

## 2b. Arm A4 — the app's rule on FLAMeS, expert change truth (added 2026-10-22)

FLAMeS 5-fold maps of the 40 co-registered FLAIRs (runs `paperc-oml-pilot` + `paperc-oml-full`,
0.69 USD); gate G1 passed (the reconstruction reproduced the app's counts in 20/20 patients).

| procedure (A4, score S_sub) | per-patient false-call rate [CP 95 %] | flagged by a true change | lesion sensitivity [boot 95 %] | false calls / patient | median threshold |
|---|---|---|---|---|---|
| app rule, every candidate (`activity_candidate`) | **1.00 (20/20) [0.83, 1.00]** | 20/20 | 0.52 [0.40, 0.61] | 8.90 [5.8, 12.6] | — |
| app rule + subtraction confirmation (new ≥ 0.5 SD) | 0.95 (19/20) [0.75, 1.00] | 20/20 | 0.49 [0.38, 0.59] | 5.40 [3.5, 7.7] | — |
| fixed bar S_sub > 0.5 SD on all candidates | 0.85 (17/20) [0.62, 0.97] | 20/20 | 0.46 [0.34, 0.56] | 3.15 | 0.5 SD |
| **CF-M, α = 0.1** | **0.10 (2/20) [0.01, 0.32]** — no violation detected | **20/20 [0.83, 1.00]** | **0.28 [0.18, 0.38]** | 0.15 [0.0, 0.4] | 1.14 SD |
| **CF-M, α = 0.2** | **0.20 (4/20) [0.06, 0.44]** — no violation detected | 20/20 | 0.31 [0.19, 0.41] | 0.25 | 1.05 SD |
| CF-PAC, α = 0.1 | abstains 20/20 (n = 19 < 22) | — | — | — | — |
| CF-PAC, α = 0.2 | 0.10 (2/20) [0.01, 0.32] | 20/20 | 0.28 | 0.15 | 1.14 SD |
| A4b (score S_dp), CF-M α = 0.1 / 0.2 | 0.10 / 0.20 | 14/20 [0.46, 0.88] / 15/20 [0.51, 0.91] | 0.13 / 0.16 | 0.10 / 0.20 | 0.93 / 0.92 |

Q4: ρ = 0.15 (p 0.53) for S_sub, −0.09 (p 0.71) for S_dp. Under the pre-registered usefulness rule
every A4 CF-M cell is **informative**. Unlike MSLesSeg, the subtraction score works better than the
FLAMeS probability change here.

**[post hoc, after the A4 results]** Why A4 works and A2 does not: on open_ms the largest false
S_sub per patient ranges −0.15 to 1.21 SD (no outlier), true candidates have median S_sub 1.15
vs 0.36 for false ones, and in 19/20 patients the best true candidate outranks every false one;
on MSLesSeg two patients carry false candidates at 4.9 and 5.3 SD (scanner changes and MNI
resampling are plausible causes, not shown). Of the app-rule candidates on open_ms, 106/282 "new"
and 72/108 "enlarged" are false against the expert masks — "enlarged" is the weaker part of the
rule.

## 3. Baselines and the app's rule (MSLesSeg first pairs, D-seg; A1 for D-sub)

| procedure | per-patient false-call rate | flagged by true change | lesion sensitivity | false calls / patient |
|---|---|---|---|---|
| A2 every candidate = **app's `activity_candidate` rule** | **1.00 (25/25) [0.86, 1.00]** | 24/25 | 0.47 [0.39, 0.55] | 8.24 |
| A2 app rule + subtraction confirmation (new ≥ 0.5 SD) | 1.00 (25/25) [0.86, 1.00] | 21/25 | 0.36 [0.27, 0.44] | 3.68 |
| A2 fixed bar S_sub > 0.5 SD on all candidates | 0.76 (19/25) [0.55, 0.91] | 20/25 | 0.29 [0.20, 0.39] | 2.52 |
| A2 plug-in quantile, α = 0.1 / 0.2 | 0.12 / 0.20 | 3/25 / 5/25 | 0.04 / 0.07 | 0.28 / 0.36 |
| A2 CF-PAC (δ = 0.1), α = 0.1 / 0.2 | 0.04 / 0.08 | 1/25 / 1/25 | 0.004 / 0.004 | 0.08 / 0.16 |
| A1 every D-sub candidate | 0.95 (19/20) [0.75, 1.00] | 19/20 | 0.38 [0.29, 0.47] | 14.6 |
| A1 CF-PAC, α = 0.1 | abstains in 20/20 (n = 19 < 22 needed) | — | — | — |

The app reports `activity_candidate = True` for 25/25 pairs (and 39/40 of all pairs); in this cohort
every pair is active under the approximate truth, so the rule's patient-level call is "right" —
but in every patient it is accompanied by false new/enlarging candidates, which is exactly what
would produce false activity in a stable patient.

## 4. Secondary analyses

- **Score S_dp (A2b, FLAMeS probability change):** α = 0.1: 0.08 (2/25) [0.01, 0.26], flagged by
  true change 7/25, lesion sensitivity 0.031; α = 0.2: 0.20 (5/25) [0.07, 0.41], 10/25 = 0.40
  [0.21, 0.61], sensitivity 0.105 [0.048, 0.167]. Best of the pilot; still not informative.
- **D-sub on MSLesSeg (A3):** 0.08 / 0.20 at α = 0.1 / 0.2, true flags 1/25 at both; candidate
  AUROC 0.55 — the model-free score barely separates true from false on resampled MNI data.
- **Sensitivity analyses (pre-specified)** — validity unchanged everywhere (no violated cell):
  open_ms positive-only truth (identical cells); D-sub thresholds 1.0 / 2.0 SD (A1 AUROC 0.60 /
  0.27; 0 true flags at both α); MSLesSeg all 40 pairs (A2: 0.07 [0.02, 0.20] and 0.17 [0.07, 0.33];
  A2b α = 0.2: 13/39 flagged by true change); A3 thresholds 1.0 / 2.0 SD (≤ 1/25 true flags).
- **Transport (exploratory, D-sub):** calibrated on all open_ms and applied to MSLesSeg, the rate is
  **0.20 (5/25) [0.07, 0.41] at α = 0.1** — twice nominal, not a detected violation at this n but a
  warning that thresholds do not move between datasets; the reverse is conservative (0/20, 1/20).
- **Q4:** ρ(largest false score, number of true change components) = 0.04 (p 0.87, A1), −0.03
  (0.88, A2), 0.12 (0.55, A2b), −0.11 (0.59, A3).

## 5. Post hoc (written after the results; explanatory only)

`posthoc.py` → `2026-10-21_paper_c_posthoc.json`.
- On open_ms the model-free subtraction score is higher for false than for true candidates
  (median 2.07 vs 1.98 SD), while true candidates are about twice as large (median 51 vs 27 mm³;
  MSLesSeg D-sub 112 vs 30 mm³). A size-aware or learned change score is the obvious redesign; it
  must be pre-registered before it is tested.
- A per-patient ranking has more room than the global threshold: in 15/25 MSLesSeg patients (A2)
  the best true candidate outranks every false one of the same patient, but the patient-level
  guarantee is set by the heaviest tail across patients: the median patient's largest false
  S_sub is 0.89 SD, yet two patients have false candidates at 4.9 and 5.3 SD, and at α = 0.1 with
  24 calibration patients the threshold is the 23rd of 24 values. Two outlying patients decide the
  whole operating point — a reason to look at those cases (registration, scanner change) before
  redesigning the score.
- Of the app-rule candidates, 161/249 "new" and 47/78 "enlarged" are false under the approximate
  truth.

## 6. Limitations

1. **No stable patients** (the estimand that matters clinically is not measured); the
   family-wise surrogate equals it only under assumption A-dom, which the pilot cannot test.
2. **Small n:** 20 and 25 patients; Clopper–Pearson intervals ±0.15–0.2. Leave-one-patient-out
   estimates the marginal rate; calibration-conditional behaviour is only probed by CF-PAC.
3. **Approximate truth in MSLesSeg:** per-timepoint masks drawn independently create spurious
   "new" lesions and hide real ones; 18/40 pairs change scanner string; native 2–5 mm slices
   resampled to MNI.
4. **Registration not exercised:** open_ms uses the providers' co-registration and MSLesSeg the MNI
   alignment; the app's own rigid registration (and its failures) are outside this pilot.
5. **open_ms longitudinal is 2D 3-mm FLAIR** (paper A: guarantees and power degrade on thick
   slices); expert change masks do not encode direction (sign inferred from the subtraction).
6. **A4 is a secondary arm with n = 20 highly active patients** (446 expert lesions ≥ 3 mm); its
   good result cannot change the pre-registered verdict, and "flagged by a true change" is easy at
   this disease burden. FLAMeS ran on 2D 3-mm FLAIR (outside its 3D training majority). FLAMeS
   training overlap: no raw-spacing match, but the same people may appear in the cross-sectional
   Ljubljana training scans (unknowable). Expert change masks are themselves imperfect; a "false"
   candidate may be a change the experts did not mark.
7. The subtraction thresholds (1.5 / 1.0 SD) and the score definitions were fixed a priori without
   tuning; a better detector could change the utility conclusion entirely — that is the point of
   the NO-GO.
8. Run disclosures: two extraction runs failed on memory (other jobs on the machine) and were
   resumed from per-unit caches; the 0.29 GB of open_ms FLAIRs were deleted afterwards for disk
   space (re-fetchable, `--stream`). No number depends on these events.

## 7. What is needed next

1. ~~Launch the prepared FLAMeS job~~ — done 2026-10-22 (0.69 USD), A4 in §2b.
2. For MSSEG-2, pre-register the A4 configuration (app rule on FLAMeS 5-fold + subtraction score,
   stable-conditional calibration primary) as the primary arm, and look at the two MSLesSeg
   outlier patients (scanner change / registration) before deciding whether the scanner-change
   pairs need their own calibration or abstention.
3. Pre-register a v2 score (size-aware subtraction and/or FLAMeS probability change combined; or
   a small learned change classifier with patient-level cross-fitting) on this pilot's data as
   development data, then test it on MSSEG-2.
4. MSSEG-2 access (Shanoir + OFSEP agreement; non-commercial): 28 stable patients make the
   stable-conditional calibration and the direct false-activity measurement possible. FLAMeS saw
   14 MSSEG-2 cases only as *test* data (FLAMeS paper), so it is usable there.
