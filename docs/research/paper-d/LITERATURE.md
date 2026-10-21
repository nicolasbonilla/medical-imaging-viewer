# Paper D — Novelty check (focused literature search)

**Date:** 2026-10-21, before any result. **Sources searched:** Europe PMC (title, abstract and full
text), PubMed Central, medRxiv, the web, and the LST-AI GitHub repository (code at tags v1.0.0,
v1.1.0, the v1.2.0 container commit `4d930aa`, and v2.0.0rc1). The searcher read every quoted
passage in its source. Conference abstracts and vendor white papers are poorly indexed, so "none
found" means none was found, not that none exists.

## 1. Verdicts

| Claim | Verdict | Closest work |
|---|---|---|
| (i) No study reports how often the **automated DIS decision flips** across plausible pipeline variants | **Supported** | Eloyan 2014 (registration changes lesion-location conclusions); LST-AI repository notes and issues #23 / #38 (anecdotal flips); Griffanti 2018 (periventricular definitions, by volume, in ageing) |
| (ii) No study reports the **automated brain-DIS decision vs the DIS from expert lesion masks** on public data | **Supported** | per-lesion or per-count agreement only, on in-house data: LST-AI medRxiv v1; van Nederpelt 2024; Rakić 2021; Bawil 2026 |
| (iii) The **LST-AI / MSMask handling of the third and fourth ventricles** has not been examined | **Supported** | none published. The guidelines exclude these ventricles (Filippi 2019); icobrain and van Nederpelt restrict PV to the lateral ventricles by design; a 2012 letter (Sahraian) asked about the fourth ventricle |

The claims must name the LST-AI version: v1 (MSMask atlas, what our LST-AI maps and the device use)
and v2.0.0rc1 (FastSurfer labels) differ.

## 2. Automated region labels vs humans (all per lesion; none makes a DIS decision)

- **Rakić M et al.**, icobrain ms 5.1, *NeuroImage: Clinical* 2021;31:102707,
  doi:10.1016/j.nicl.2021.102707. Detection per lesion class against manual 4-class delineations
  (n = 51). Cascade JC (dilated overlap with cortex > 10 % of the lesion volume) → IT → PV (dilated
  **lateral** ventricles) → DWM, i.e. JC before PV, the reverse of LST-AI.
- **van Nederpelt DR et al.**, *NeuroImage: Clinical* 2024;44:103680,
  doi:10.1016/j.nicl.2024.103680. "From the automated lesion location method, 93 % was correctly
  classified (total manual segmented lesion count = 1666)". Per lesion, run on the **manual** masks,
  neuroradiologist review; SynthSeg lateral ventricles dilated 1 mm → PV, then ≥ 5 cortical voxels →
  JC, then IT, else deep. n = 30.
- **Wiltgen T et al.**, LST-AI, *NeuroImage: Clinical* 2024;42:103611,
  doi:10.1016/j.nicl.2024.103611. The **published** paper does not validate the location labels. The
  **medRxiv v1** (doi:10.1101/2023.11.23.23298966) had a lesion-level confusion matrix on an in-house
  test set: PV 80.5 % correct, JC 86.9 %, subcortical 33.9 % (26.2 % went to PV, 39.8 % to JC); the
  section was removed in v2 and in the published paper. The paper states the order PV, IT, JC, SC;
  the v1 code checks PV → **JC → IT** → SC (verified by us at commit `4d930aa`, the v1.2.0 container).
- **Bawil MB et al.**, *J Imaging Inform Med* 2026, doi:10.1007/s10278-026-01906-2 (abstract only):
  per-region lesion counts vs 3 neuroradiologists in 15 cases (PV r = 0.93, JC r = 0.93).

## 3. Automated DIS decision vs experts or diagnosis — none found

- **Spampinato MV et al.**, *AJNR* 2025;46(7):1510-16, doi:10.3174/ajnr.A8655: commercial software
  separates MS from non-MS by lesion count; no DIS computed.
- **Ma J et al.** ("DeepMS"), medRxiv 2026: classifier compared with DIS **as assessed by
  radiologists**, not computed automatically.
- **Mendelsohn Z et al.**, *Neuroradiology* 2023;65:5-24, doi:10.1007/s00234-022-03074-w: 9 of 10
  commercial report tools output McDonald-region counts; clinical validation evidence is scarce.
- **Barkhof F et al.**, *Lancet Neurol* 2025;24(10):866-79 (MAGNIMS-CMSC-NAIMS): automated tools
  "will require more extensive real world clinical validation".
- **Wattjes MP et al.**, *Clin Neuroradiol* 2026, doi:10.1007/s00062-026-01670-4 (German consensus)
  describes LST-AI as giving "expert-level accuracy, including McDonald criteria-based localization",
  which the published LST-AI paper does not validate — a motivation for paper D.
- **van Nederpelt DR et al.**, *Eur Radiol* 2025, doi:10.1007/s00330-025-11544-x: 75.6 % of surveyed
  users want a "fulfilment of the McDonald criteria" section in automated reports.

## 4. Stability across pipelines (partial evidence only)

- **Eloyan A et al.**, *PLoS One* 2014;9:e107263: "conclusions regarding lesion localization can vary
  substantially with the choice of registration algorithm".
- **Griffanti L et al.**, *NeuroImage* 2018;170:174-181: four periventricular/deep definitions of
  white-matter hyperintensities (ageing, volumes).
- **de Sitter A et al.**, *NeuroImage* 2017;163:106-114; **Egger C et al.**, *NeuroImage: Clinical*
  2017: large differences between MS segmenters.
- **Grahl S et al.**, *MSARD* 2019;29:124-129: evidence for a ~3 mm lesion-size threshold.
- LST-AI repository (not peer reviewed): testing notes say "a small lesion on a region border can flip
  category"; issue #23 (run-to-run differences in annotated counts from deformable registration and
  unthresholded small lesions); issue #38 (a registration-metric change labelled symmetric
  periventricular lesions PV on one side and subcortical on the other).

## 5. Human baseline (inter-reader agreement)

- **Mahmoudi N et al.**, *Eur J Neurol* 2026;33:e70469: 3 readers, 78 patients; DIS Fleiss κ
  0.58–0.66 (0.66 under McDonald 2017); PV presence κ 0.70, IT κ 0.56; PV and JC lesion counts κ
  0.28–0.32.
- **Korteweg T et al.**, *Eur Radiol* 2007;17:67-71: DIS κ 0.62 between trained radiologists, 0.29
  for radiologists new to the criteria.
- **Hagens MH et al.**, *Mult Scler* 2019;25:352-360; **Barkhof F et al.**, *Neuroradiology*
  1999;41:347-350; **Heinemann J et al.**, *MSARD* 2025;94:106304 (PV and JC lesions misidentified by
  46 % and 55 % of neurologists).

## 6. Definitions (quoted)

- **Filippi M et al.**, *Brain* 2019;142(7):1858-75, doi:10.1093/brain/awz144.
  - PV: "in direct contact with the lateral ventricles, without intervening white matter … exception
    … a lesion that abuts the lateral ventricles but is located in the deep grey matter (e.g. caudate
    nucleus or thalamus)".
  - "Lesions touching the third and fourth ventricles, and lesions in the midbrain touching the
    cerebral aqueduct should not be counted as periventricular."
  - JC: "abutting … the cortex without intervening normal white matter … can be located in all brain
    lobes and in the cerebellum". Cortical: "completely within the cortex or spanning the cortex and
    subjacent white matter". IT: "in the brainstem, cerebellar peduncles or cerebellum".
  - Size: "Generally … at least 3 mm in their long axis".
- **Thompson AJ et al.** (McDonald 2017), *Lancet Neurol* 2018;17:162-73: DIS = "one or more
  T2-hyperintense lesions … in two or more of four areas of the CNS: periventricular, cortical or
  juxtacortical, and infratentorial brain regions, and the spinal cord"; for people over 50 or with
  vascular risk factors "it might be prudent … to seek a higher number of periventricular lesions".
- **Filippi M et al.** (MAGNIMS 2016), *Lancet Neurol* 2016;15:292-303: "≥ 3 periventricular lesions".
- **Montalban X et al.** (McDonald 2024), *Lancet Neurol* 2025;24(10):850-65: DIS in "2 out of 5
  anatomical locations (optic nerve, juxtacortical/intracortical, periventricular, infratentorial,
  spinal cord)". Full text not accessed (paywall); the age ≥ 50 recommendation is reported from the
  official slide deck as extra evidence (cord lesion, CSF, central vein sign), not a higher PV count —
  **unverified** in the paper itself.
- **Barkhof F et al.** 2025 (accepted manuscript): PV keeps the lateral-ventricle wording (corpus
  callosum included, deep grey matter excluded); lesions "generally at least 3 mm"; "at least 3
  periventricular lesions in CIS patients > 45 years old improves specificity"; MS can be confirmed
  with typical lesions in "at least four locations" — a brain-only pipeline reaches at most three.

## 7. LST-AI region rule — what the code does (verified in the source by us)

| Version | Region source | Third ventricle | Fourth ventricle | Order |
|---|---|---|---|---|
| v1.x (MSMask; container v1.2.0, commit `4d930aa`; **the version that produced our LST-AI maps, and the atlas the device uses**) | MSMask atlas warped by greedy | inside label 4 "Ventricles" → **PV** | inside label 5 "Infratentorial" → IT | PV → JC → IT → SC |
| v2.0.0rc1 (Aug 2026) | FastSurfer aseg mapped to classes | label 14 → **PV** | label 15 → IT | PV → IT → JC → SC |

v2 also maps aseg "CSF" (label 24) and the choroid plexus (31, 63) to the periventricular class, and
deep grey matter (thalamus, caudate, putamen, pallidum) to WM. The guideline conflicts are therefore:
the third ventricle (and, with PV checked first, midbrain lesions touching the aqueduct / third
ventricle), CSF label 24 and the deep-grey-matter exception. **Mapping the fourth ventricle to IT does
not conflict with Filippi 2019 in effect**: a lesion touching the fourth ventricle lies in the
brainstem or cerebellum and is infratentorial either way. Paper D can quantify the third-ventricle
part on v1 MSMask (shared with v2 and with the device); the v2-only parts (CSF label 24, choroid
plexus) need FastSurfer segmentations and are **not quantified**.

## 8. Licences

- MNI ICBM 2009c (TemplateFlow LICENSE): McGill permissive licence, use "for any purpose and without
  fee … provided that the above copyright notice appear".
- FSL: non-commercial, but the current FSL licence page releases the Harvard-Oxford and Cerebellum
  atlases under CC BY-SA 4.0; JHU, Juelich, Striatum and Thalamus atlases stay non-commercial. Paper D
  uses no FSL atlas.
- LST-AI code MIT; paper CC BY-NC-ND; MSMask has no separate statement (to be confirmed).
- FLAMeS (Dereskewicz E et al., *J Neuroimaging* 2025;35(5):e70085, doi:10.1111/jon.70085): weights
  CC BY-NC 4.0. Training: 668 scans including "PubMRI" = Lesjak 2018 (Ljubljana, 20 scans);
  **MSLesSeg (n = 51) was an external test set**, not training.

## 9. Framing

- **Botvinik-Nezer R et al.**, *Nature* 2020;582:84-88 (70 teams, same data, different results).
- **Steegen S et al.**, *Perspect Psychol Sci* 2016;11:702-12 (multiverse analysis).
