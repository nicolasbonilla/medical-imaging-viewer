# Paper F → MSTool-AI app: what the result would change (research input, not a device change)

Every paper must ship as a real app feature. This note fixes **now**, before any result, which app
change each possible outcome of paper F would justify, so the product decision cannot be bent to the
numbers afterwards. Nothing here changes the medical device: any of it needs a requirement in SRS-001,
a risk review in RMF-001, a SOUP/licence review and a code review first (CLAUDE.md, Class C).

> **Resumen en español sencillo.** Hoy la aplicación usa un solo modelo para marcar lesiones. El
> artículo F dirá si, en estudios de cortes gruesos (lo habitual en hospitales), otra herramienta lo
> hace mejor, igual o peor. Según el resultado, la aplicación podría: elegir el modelo según el grosor
> de corte, mostrar un aviso con la fiabilidad medida en ese tipo de estudio, o pedir una "segunda
> opinión" a otro modelo y avisar al médico cuando ambos no coinciden. Ninguna de las herramientas
> probadas se puede meter tal cual en el producto: sus licencias son de investigación o no están claras.

## 1. What the app already has

- Slice thickness is read from DICOM/NIfTI and shown (`ControlPanel.tsx`, `imaging_service.py`), so the
  app can route or warn by thickness without new data.
- FLAMeS auto-segmentation is wired end to end (server worker; dark until a worker is deployed, by the
  no-recurring-cost rule).
- `segmentation_comparison_service.py` already compares two segmentations — the natural place for a
  lesion-wise agreement score.

## 2. Outcome → app action (fixed before the results)

| Paper F outcome (PROTOCOL.md 7.1 / 7.5) | App action proposed | Condition before shipping |
|---|---|---|
| A CPU tool **outperforms** FLAMeS on thick slices (Holm-significant higher lesion F1, false lesions not worse by > 1 per scan) | **Thickness-aware routing**: for studies with slice spacing > 3 mm, offer that tool (or a model trained the same way) as the default segmenter; FLAMeS stays for ≤ 1.5 mm | a licence that allows product use (see 3); SOUP pinning by digest; verification on a held-out thick-slice cohort |
| **Equivalent** (both 90% CIs inside ±0.05 F1 and ±1 false lesion) | Keep FLAMeS only (one model = simpler verification); no routing | — |
| FLAMeS **better or equal** but its thick-band F1 / false lesions are clearly worse than on 1 mm | **Thick-slice reliability notice** on the segmentation and report: "on studies with slices > 3 mm, lesion detection measured on 179 public scans: F1 x (95% CI), y false lesions per scan" — numbers from paper F, labelled as research evidence | wording reviewed as non-diagnostic; numbers frozen with the paper |
| Disagreement predicts poor FLAMeS scans (E1 AUROC ≥ 0.75 in the thick band, with ≥ 10 poor scans) | **Second-opinion flag**: run a second segmenter, compute lesion-wise agreement with FLAMeS, show "low agreement — review carefully" under a threshold | threshold chosen on paper F data must be re-validated on a cohort not used in paper F; second model licence-clean |
| "Confirmed lesions" (FLAMeS ∩ second tool) cut false lesions without losing F1 (E2) | **Review aid**: optional overlay highlighting FLAMeS lesions the second model also sees; never changes the measured volumes or counts | as above; displayed as a reading aid only |
| None of the above | No app change; paper F is reported as a negative/benchmark result | — |

The second-opinion ideas are exploratory in the protocol; a positive exploratory result only justifies
building and validating the feature, not shipping it.

## 3. Licence reality for the product (why no tool ships as is)

- **FreeSurfer (WMH-SynthSeg, SAMSEG)**: royalty-free licence but "designed for research purposes
  only… clinical applications are neither recommended nor advised"; needs per-user registration. Not
  a basis for a Class C feature without a separate agreement with MGH and our own validation.
- **MindGlide**: code MIT, but the weights have **no stated licence** and were trained on private
  industry trial data. Product use needs written permission from the authors (UCL / MS-PINPOINT). It
  also ships a browser (ONNX, fp32, 123 MB) version, which could run in the app's existing browser
  worker (`edgeAI.worker.ts`, a Class C module) at no server cost — only worth pursuing if the licence
  is cleared and paper F shows a benefit.
- **LST-AI**: MIT, but the authors say "not validated, licensed or approved for any clinical usage"; it
  also needs a T1, which many thick-slice studies do not have.
- A licence-clean path, if paper F shows that thick-slice training is what matters: train our own model
  with the same recipe (random slice thickness / SynthSeg-style synthesis) on data whose licences allow
  product use — a separate project with its own cost.

## 4. Cost and runtime facts the app would inherit (measured by the paper F runs)

The manifests record CPU seconds and peak memory per scan for each tool on 4 vCPU. Planning values
until then: MindGlide ~1–5 min and < 16 GB; WMH-SynthSeg ~1–4 min but ~32 GB RAM (the Cloud Run
maximum); SAMSEG ~6–15+ min. Any server-side use would be pay-per-use CPU (no idle cost), in line with
the no-recurring-cost rule.

## 5. Interim reading against section 2 (2026-10-22; MindGlide and LST-AI only — RESULTS-interim.md)

WMH-SynthSeg and SAMSEG are still pending (FreeSurfer licence), so no row is final. With what exists:

| Row of section 2 | Interim evidence | Interim reading |
|---|---|---|
| A CPU tool outperforms FLAMeS on thick slices | MindGlide lesion F1 −0.170 (−0.206 to −0.136) vs FLAMeS on 179 thick scans; false lesions +0.6 (−0.9 to +2.2); MindGlide on raw FLAIR is no better (−0.016 vs stripped) | **Not met** by MindGlide: no thickness-aware routing to MindGlide |
| Equivalent | not equivalent (F1 90% CI −0.200 to −0.141) | not met |
| FLAMeS best, but worse on thick than on 1 mm | FLAMeS F1 0.724 thick vs 0.765 iso; false lesions 6.9 vs 3.8 per scan; small lesions (14–50 mm³) found 49% vs 56% | **Applies so far** → candidate wording for a thick-slice notice: "on studies with slices > 3 mm (179 public research scans) automatic lesion detection reached F1 0.72 with about 7 false lesions per study; small lesions are often missed" — numbers to be frozen only with the final results |
| Disagreement predicts poor FLAMeS scans | MindGlide–FLAMeS disagreement: AUROC 0.78 on thick slices with 14 poor scans (criterion: ≥ 0.75 with ≥ 10 poor scans) | **Criterion met (exploratory)** → worth building and validating a second-opinion flag on a cohort not used here; MindGlide itself cannot ship (weights licence not stated), so the second model must be licence-clean |
| Confirmed-lesions review aid | FLAMeS ∩ MindGlide: −3.8 false lesions per thick scan but F1 −0.074 | **Not met** (F1 drops) → not proposed |

Product consequence today: keep FLAMeS as the only segmenter; prepare (not ship) the thick-slice
notice and a second-opinion design, both to be confirmed when the FreeSurfer tools are in.

*Superseded by section 5b (2026-10-31): the "criterion met" reading of the disagreement row above does
not stand.*

## 5b. Final reading (2026-10-31; all tools; after the internal review of the manuscript)

Sources: `research/paper_f/results/` (final pre-registered results, commit 1d3be48) and the post hoc
numbers of `research/paper_f/manuscript/data/extra_numbers.json` (labelled post hoc).

> **Resumen en español sencillo.** FLAMeS sigue siendo el mejor modelo probado, también en cortes
> gruesos: nada que cambiar en el segmentador. La idea de la "segunda opinión" **queda descartada**:
> contar cuántas lesiones marca FLAMeS señala mejor los estudios dudosos que comparar con otro modelo.
> El aviso de fiabilidad para cortes gruesos no se puede publicar con estas cifras tal cual sin una
> revisión de licencias (ver abajo).

| Row of section 2 | Final evidence | Final reading |
|---|---|---|
| A CPU tool outperforms FLAMeS on thick slices | lesion F1 vs FLAMeS: MindGlide −0.170, SAMSEG −0.237 (129 scans), WMH-SynthSeg −0.384, all Holm p < 0.002; no tool meets the reading rule | **Not met**: no thickness-aware routing |
| Equivalent | no tool equivalent | not met |
| FLAMeS best, but worse on thick than on 1 mm | FLAMeS F1 0.724 on thick vs 0.765 on the 1 mm grid; 6.9 vs 3.8 false lesions per scan; 14–50 mm³ lesions found 49% vs 56%. The two bands are different cohorts (and the "1 mm" band is mostly MSLesSeg, acquired with ~2.6 mm slices), so this is a description, not a measured effect of slice thickness | Notice still possible, but **blocked by licences** (below) and to be worded as research evidence from different cohorts |
| Disagreement predicts poor FLAMeS scans | MindGlide–FLAMeS disagreement AUROC 0.779 (14 poor scans). Post hoc, a FLAMeS-only score — how few lesions FLAMeS predicted — gives 0.932 (95% CI 0.861–0.987); adding disagreement gives 0.884, no gain. Disagreement mostly tracks "FLAMeS marked few lesions" | **Not supported. No second-opinion flag is proposed.** A FLAMeS-only "few lesions found" rule is a better candidate, but it is post hoc on 14 poor scans and would need its own pre-specified threshold and validation on data not used here |
| Confirmed-lesions review aid | F1 always drops (MindGlide: −0.074) | **Not met**: not proposed |

**Licence consequences for any product use of paper F numbers (new):**
- 151 of the 179 thick scans (MS3SEG, Muslim) were skull-stripped with HD-BET, whose model parameters
  are **CC BY-NC 4.0** (Zenodo record 14445620). Quoting the thick-band F1 / false-lesion figures in the
  product, its labelling or its marketing is commercial use of results that depend on non-commercial
  parameters: legal review first, or recompute the figures with a skull stripper whose licence allows
  it.
- Ljubljana is **CC BY-NC-ND** according to its laboratory's page (registry commit 71a52ad): its numbers
  must not feed product calibration, thresholds or marketing, and no derived masks may be published.
- The conflict of interest (the product already uses FLAMeS, the winner of this benchmark) is declared
  in the manuscript; any product statement citing paper F must cite it as research evidence produced by
  the manufacturer.

Product consequence: keep FLAMeS as the only segmenter; do **not** build the second-opinion flag; the
thick-slice notice stays a draft until the licence question above is settled and the wording is
reviewed as non-diagnostic.

## 6. Traceability to open

When a result triggers a row of section 2: create the requirement in SRS-001 (new REQ id, "to be
assigned"), add the hazards it touches in RMF-001 (missed lesions and false lesions on thick-slice
studies feed lesion counts and dissemination-in-space reporting), record the tool as SOUP with its
digest and licence, and reference this file and the paper F results commit in the PR.
