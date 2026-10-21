# Paper C — focused novelty re-check (2026-10-21)

*Research record, not the medical device. Builds on the verification round of 2026-10-17
(`research_notes/Comprobaciones de novedad/verificaciones_2026-10-17.md`, untracked in the main
checkout; its paper-C section is summarised here) and adds a re-search done today, before the
protocol was written.*

## Claim being tested

"A distribution-free, finite-sample guarantee on the **patient-level** probability of a FALSE
'new/enlarging lesion' (disease-activity) call between two FLAIR timepoints in MS." Not claimed:
any novelty of the statistics (split-conformal quantiles, Neyman–Pearson order statistics, conformal
risk control and Learn-then-Test are all established).

## Searches run today

| Source | Query (summary) | Result |
|---|---|---|
| arXiv API | conformal ∧ "multiple sclerosis"; conformal ∧ "new lesions"; "risk control" ∧ MS; conformal ∧ longitudinal ∧ lesion; "new lesion" ∧ "false positive" ∧ patient; Neyman-Pearson ∧ lesion; "lesion activity" ∧ uncertainty | 3 hits in total, none on MS new-lesion detection (2609.21197 is CT lesion-size forecasting) |
| Europe PMC REST | conformal ∧ MS ∧ (new lesion ∨ activity) ∧ MRI (67 hits); MS ∧ new lesions ∧ (FP ∨ specificity) ∧ (stable ∨ no new lesions) ∧ automated (383, 40 newest read); (conformal ∨ risk control ∨ LTT) ∧ lesion detection ∧ MRI 2024–26 (52); (Neyman-Pearson ∨ type I error) ∧ MS ∧ new lesions (40) | no paper giving a guarantee on patient-level false activity |
| Web search (6 queries) | conformal / risk control / Neyman-Pearson × new MS lesions; MSSEG-2 stable patients; Conformal Triage | see below |

## Closest prior work (ranked)

1. **McKinley et al., NeuroImage Clin 2020;25:102104** — label-flip confidence to call a time
   point stable vs progressive; reports stable time points wrongly called progressive (9/83);
   empirical threshold, **no guarantee**.
2. **Homssi et al., AJNR 2023;44:649–655** ("statistical detection of change", SDC) — subtraction
   based; the Neyman–Pearson argument controls a **voxel-wise** false-positive rate; at the subject
   level specificity was 0.67 [0.59, 0.74] in 200 patients, **no subject-level guarantee**. New in
   this re-check; closest *methodological* neighbour on the clinical side.
3. **Angelopoulos et al., "Conformal Triage", medRxiv 2024** — patient-level LTT guarantees on PPV
   / NPV for head-CT triage; not lesion detection, not longitudinal. A 2026 audit (arXiv 2605.20956)
   shows pooled marginal validity does not bound the risk in a low-prevalence subgroup — directly
   relevant to our transfer assumption (§5 of the protocol).
4. **MSSEG-2 measurements without guarantees** — Valencia et al. Front Neurosci 2022 (Table 3:
   stable patients with ≥ 1 false new lesion: experts 0–11 %, top-3 challenge systems 14–36 %);
   Andresen et al. Front Neurosci 2022 (Det_s on 28 stable patients); Basaran et al. 2022; Masson et
   al. Sci Rep 2026 (official MSSEG-2 paper, mean false lesions on 25 stable patients of the revised
   ground truth; 3-class patient accuracy).
5. Lesion/detection risk control in other organs: Hulsman et al. COPA 2025 (CRC on per-scan FNR,
   lung nodules), Tan et al. arXiv 2510.17897 (voxel FNR), Blot et al. UNSURE 2024 (precision of
   follicle detections), Davenport arXiv 2410.03406 (image-level inner/outer sets).
6. Commercial-tool validations report patient-level specificity / PPV without guarantees (Barnett
   2023 iQ-MS; Peters 2025 mdbrain 0.74 → 0.55 across scanners; Hindsholm 2025/2026).

## Verdict

**Still open, as an application/formulation:** no paper found gives a finite-sample guarantee on
the per-patient probability of a false new/enlarging-lesion call in longitudinal MS MRI. The
statistics are textbook (we use a split-conformal / Neyman–Pearson order statistic and its PAC
version), so the defensible contribution is (i) the clinically framed estimand (MAGNIMS 2021:
one new/enlarging lesion = activity), (ii) the honest validity/power trade-off on public data,
(iii) the comparison with the rule an actual product uses, (iv) on MSSEG-2 later, the stable
patients themselves. Residual uncertainty: MICCAI-2026 workshop proceedings (UNSURE, BrainLes),
ECTRIMS/ISMRM abstracts and Google Scholar were not enumerated; Semantic Scholar was not reachable.

Sources: arXiv API, Europe PMC REST, PMC6953959 (McKinley), AJNR 44(6):649 (Homssi), medRxiv
10.1101/2024.02.09.24302543 (Conformal Triage), arXiv 2605.20956, PMC9558286 (Valencia), PMC9490269
(Andresen), PMC13402319 (Masson), arXiv 2412.20167, 2510.17897, 2410.03406, 2501.14036.
