# PRB-001 — MSMask Path Counts a Lesion Touching the Third Ventricle as Periventricular

*Software problem report per SPR-001 (`docs/iec62304/08_Problem_Resolution_Procedure.md` §1). SPR-001 says
problem reports are GitHub Issues; none has ever been raised in this repository and no problem-report
record existed before this one. This record follows the SPR-001 §1 template field by field and is
kept under `docs/iec62304/records/problem_reports/`. A GitHub Issue citing this ID is to be raised by
the owner (as CAPA-006 did); the agent did not raise one.*

**Problem ID**: PRB-001 (GitHub Issue: not raised — owner action)
**Reporter**: Paper D research analysis (PR #61, branch `research/paper-d-dis-fragility`, `docs/research/paper-d/RESULTS.md` §7 and §11, record `docs/research/paper-d/records/results_v1.json` key `S4_ventricles`); record drafted by the AI coding agent
**Date**: 2026-10-22
**Version**: `main` @ `6209131`; `backend/app/services/ms_region_classifier.py` is identical on this branch's base (`af3fc32`). Present since the MSMask ventricle rule was introduced (`67fa336`, 2026-02-28)
**Severity**: **Critical — safety-related** (proposed; SPR-001 §2 classes a problem with a safety impact as Critical; raised from Minor on 2026-10-23 after the independent review of PR #62; rationale in §5). **PENDING owner approval.**
**Status**: OPEN — DRAFT. Fix proposed, **not implemented** (`ms_region_classifier.py` is a Class C module; CLAUDE.md requires a code review before any change).

**Description**: REQ-FUNC-053 defines periventricular (PV) as "abutting the **lateral** ventricles", as do the module docstring (`ms_region_classifier.py` line 8), DD-CLS-001 (DDS-001 §DD-CLS-001), IFU-001 §10.3, CER-001 and GSPR-001, following Filippi et al. 2019 ("lesions touching the third and fourth ventricles … should not be counted as periventricular"). On the MSMask atlas path (REQ-FUNC-053 path 3), the PV landmark is the whole of MSMask label 4 "Ventricles", which holds the lateral **and the third** ventricle. White matter abutting the third ventricle therefore becomes PV zone, and a lesion touching only the third ventricle can be classified **periventricular**: in paper D, of the 6 expert lesions that touched only the third ventricle (dataset MNI placement, G0), the device classified **3** as periventricular and 3 not; with the LST-AI registration (G1), 4 of 4 *(stated exactly 2026-10-23 after the independent review of PR #62; the first draft said every such lesion is classified periventricular)*. The rule is inherited from LST-AI v1 (the atlas and its annotation rule).

**Steps to Reproduce**:
1. Take an MNI-grid FLAIR (one that passes `looks_mni`, RC-032) and a lesion mask with a lesion that abuts the third ventricle and no lateral ventricle (paper D found 6 such expert lesions in 124 public scans, G0 placement).
2. Call `classify-regions` with `method="msmask"` (or `auto` with no LST-AI segmentation and no parcellation), or `generate-zone-map` without a parcellation.
3. Read the region of that lesion, or the PV zone of the zone map around the third ventricle.

Paper D ran the device's own functions (`generate_zone_map_atlas`, `classify_from_zone_mask`, `compute_dis_criteria`) on every one of its 144 scans and stopped on any disagreement with its research code; none occurred (`RESULTS.md` §0), so the numbers below are the device's behaviour.

**Expected Behavior**: A lesion touching only the third ventricle is not periventricular. It takes the region the rest of the rule gives it (juxtacortical if it abuts cortex, otherwise deep white matter). The fourth ventricle is already inside MSMask label 5 (infratentorial), which agrees with the guideline (such lesions are infratentorial anyway).

**Actual Behavior** (`ms_region_classifier.py`, `generate_zone_map_atlas`):
- line 1120: `ventricles = (msmask_data == MSMASK_LABELS["Ventricles"])   # label 4` — lateral and third ventricle together;
- line 1138: `ventricles_dilated = binary_dilation(ventricles, structure=struct)`;
- line 1165: `pv_mask = ventricles_dilated & wm & (zone_map != 3)` — white matter next to the third ventricle becomes PV.
The thalami are labelled white matter in MSMask, so thalamic white-matter voxels next to the third ventricle are in the PV zone.

Measured in paper D (3,992 expert lesions >= 3 mm³, 124 scans, 85 patients; MSLesSeg and Ljubljana):

| | G0 (dataset MNI placement) | G1 (LST-AI registration) |
|---|---|---|
| Expert lesions touching only the third ventricle | 6 | 4 |
| Lesions whose region changes, device rule → lateral ventricles only (all PV → DWM) | **3 (0.08 %)** | 4 (0.10 %) |
| PV lesions in total, device rule → lateral only | 905 → 902 | — |
| Scans with at least one changed lesion | 1.6 % (0–3.9 %) | 2.4 % (0–5.4 %) |
| Scans whose brain DIS decision changes | **0** | **0** |

(Intervals: 95 % patient-clustered bootstrap, from the record.)

**Safety Impact Assessment**:
- [x] Could contribute to a hazardous situation — **HAZ-005** (wrong region assignment), and through the PV count **HAZ-008** (DIS evaluated incorrectly). Not observed to change a DIS decision in the data examined.
- [x] Affects a Class C software item — `backend/app/services/ms_region_classifier.py`.
- [ ] Requires regulatory notification (EU MDR Article 87) — no: the device is not CE-marked and not in clinical use.

---

## 1. Triage (SPR-001 §3.1)

- **Reproducible**: yes, by construction (the code reads label 4 whole) and measured with the device's own functions in paper D.
- **Severity**: proposed Critical, safety-related (§5; raised from Minor on 2026-10-23 after the independent review of PR #62).
- **Assigned to**: *(to be assigned — Class C change; owner decision)*.

## 2. Root Cause (SPR-001 §3.2)

1. **An external atlas and rule adopted as-is.** MSMask (LST-AI v1) has one label for the lateral and third ventricles. The device copied LST-AI's use of that label as the PV landmark. The requirement (lateral ventricles only) was written correctly, but the atlas content was never checked against it.
2. **No test of the landmark itself.** UT-CLS-001/002/003 test the contact rule, the evidence fields and the path preconditions (RC-032); none checks which anatomy counts as "ventricle" on the MSMask path. The parcellation path does it right (`LATERAL_VENTRICLE_LABELS = {4, 43}`, line 54; comment at line 761 "excludes 3rd/4th ventricle"), which may have made the MSMask path look covered.
3. **Same family as CAPA-006**: labelling (IFU, CER, GSPR) states a rule that one design output does not apply.

## 3. Impact Analysis (SPR-001 §3.3)

**Other paths and uses of the same zone map:**

| Path / use | Ventricle definition | Affected? |
|---|---|---|
| Path 1 — LST-AI zones (copy of LST-AI's own lesion-types mask) | LST-AI v1 rule on MSMask label 4 | **Yes, inherited.** LST-AI is off in production (`LSTAI_ENABLED` default `False`) |
| Path 2 — parcellation + distance (`generate_zone_map`, `classify_lesions_with_parcellation`) | FreeSurfer labels 4 and 43 (lateral ventricles) | No |
| Path 3 — MSMask atlas (`generate_zone_map_atlas`) | MSMask label 4 (lateral + third) | **Yes** |
| Path 4 — geometric heuristics | No ventricle landmark (distance from the brain centre) | Not this defect (a different, known limitation of the heuristic) |
| `generate-zone-map` route (zone overlay shown to the user) | Path 2 or 3 | Yes when path 3 is used: the PV colour extends around the third ventricle |
| Longitudinal comparison, region stratification of new/enlarging candidates (MNI-grid data only) | MSMask zone map | Yes |

**Exposure.** Path 3 applies only to images that pass the MNI grid gate (RC-032, since 2026-09-28): in practice, public research datasets delivered in MNI space, rarely clinical studies. Before 2026-09-28 the atlas was also applied to non-MNI images (CAPA-006), where the region error from misplacement is far larger than this one.

**Requirements affected:** REQ-FUNC-053 (nonconformity of path 3, and of path 1 by inheritance). REQ-SAFE-010 (amended) and REQ-SAFE-021 are not affected: the evidence fields and the path preconditions behave as specified.

**Risk controls affected:** none fails. RC-032 (preconditions) and RC-010 (amended) (evidence, not confidence) do not address the landmark. A new control is proposed: **RC-059** (RMF-001 v1.11 DRAFT §5.1, NOT IMPLEMENTED).

**Labelling:** IFU-001 §10.3 (region table: "PV — abuts (is in contact with) the lateral ventricles"), CER-001, GSPR-001 and DDS-001 state the requirement correctly; path 3 does not meet them. DDS-001 lists MSMask label 4 as "ventricles" without saying it includes the third ventricle.

**Previously released versions:** every version since `67fa336` (2026-02-28) that could run the MSMask path.

**Regulatory notification:** not required (not CE-marked, not in clinical use).

## 4. Related Observations from Paper D — Not Covered by This Report

Paper D §11 recommends problem reports for two more items. They are recorded here so they are not lost; each needs its own report (owner decision), because the fix and the evidence differ:

1. **Deep grey matter is white matter in MSMask.** Thalamic or caudate lesions next to a lateral ventricle become periventricular, against the guideline exception. Not quantifiable with MSMask.
2. **6.3 % of expert lesions (250 of 3,992, G0; 3.6 % at G1) lie in no MSMask zone** and are reported as deep white matter by default; purely cortical lesions should count as cortical/juxtacortical (McDonald 2017/2024). RC-010 (amended) already flags these lesions per lesion (`atlas_coverage = false`, amber warning), but they never count towards the cortical/juxtacortical DIS region.
3. *(Minor, path 1)* LST-AI's code checks PV → JC → IT while its paper states PV → IT → JC; 34 expert lesions touch cortex and the infratentorial label without touching a ventricle (G0). No DIS decision changed in paper D.

## 5. Severity Rationale (SPR-001 §2)

SPR-001 has three levels: Critical (safety impact, data corruption, complete failure), Major (significant functional loss, no workaround), Minor (minor inconvenience, workaround available). This problem has a safety impact (it can contribute to HAZ-005 and, through the PV count, HAZ-008), so SPR-001 §2 classes it **Critical**. Proposed: **Critical, safety-related** (raised from Minor on 2026-10-23 after the independent review of PR #62; the first draft proposed Minor because no level fits a low-frequency nonconformity exactly). The facts that argued for Minor bear on the probability and urgency of harm, not on the class:
- the effect measured with the device's own code is small: 3 of 3,992 lesions (0.08 %) change region, and 0 of 124 DIS decisions change, under two different atlas placements;
- a workaround exists: every region comes with its contact evidence (RC-010 amended), and the region classification is decision support that a radiologist reviews (intended use);
- the path is used only on MNI-grid images (RC-032).

Why it is still safety-related and must not be closed as cosmetic:
- the evidence comes from established MS (95 % of scans met DIS on the expert mask); in early MS or a clinically isolated syndrome, a single periventricular lesion can decide DIS, and paper D found fragility concentrated in scans with few lesions (65 % of scans with <= 18 lesions not unanimous across pipelines);
- the thalamic part (§4 item 1) is not quantified;
- it is a nonconformity of the device to its own requirement and labelling.

**CAPA linkage (SPR-001 §4.1).** SPR-001 §4.1 requires a CAPA for any problem that affects a Class C software item or regulatory compliance; this one does both. Proposed: handle it under the open **CAPA-006** (MAGNIMS labelling and atlas space — same module, same hazard, same root cause family) as a new action **CA-6.14**, rather than opening a new CAPA. **Owner decision — PENDING.** The CAPA-006 record itself is not changed by this draft.

## 6. Proposed Resolution (SPR-001 §4) — NOT implemented

**Fix (Class C change; code review required before any edit):**
1. **Derive a lateral-ventricle landmark once, offline**, from MSMask label 4, separating the third ventricle with the method pre-specified and used in paper D (`research/paper_d/atlas.py::split_third_ventricle`: one 6-neighbour erosion of label 4 cuts the narrow interventricular foramina; the midline, narrow eroded component is the third-ventricle seed, the others are lateral seeds; every label-4 voxel takes the class of its nearest seed). Have a neuroradiologist check the split visually, store the derived mask next to MSMask with its SHA-256 and provenance (method, parameters, voxel counts), and version it.
2. **In `generate_zone_map_atlas`**, use only the lateral-ventricle voxels as the PV landmark; third-ventricle voxels are treated like CSF (not a landmark). Infratentorial (label 5, which contains the fourth ventricle) is unchanged.
3. **Fail closed:** if the derived landmark is missing or its SHA-256 does not match, the MSMask path refuses with the reason stated (as RC-032 refusals do); it never falls back to the whole label 4.
4. **Path 1 (LST-AI zones):** before LST-AI is enabled anywhere, either recompute the regions from LST-AI's lesion mask with the corrected device rule instead of copying LST-AI's lesion-types labels, or state the deviation in the result and the IFU (owner decision).
5. **Documents:** the module docstring and DDS-001 (MSMask label 4 holds lateral and third ventricles; the derived landmark); TM-001 and RMF-001 rows for RC-059. Until the fix ships, list the deviation in the known residual anomalies of the next release (REL-001 §2.2) — owner decision.

**Verification (proposed):**

| ID | Check | Pass criterion |
|---|---|---|
| V1 | New unit tests `test_rc059_*` on a synthetic label map with lateral and third ventricles | A lesion abutting only the third ventricle is not PV; one abutting a lateral ventricle is PV (positive control); one abutting both is PV; a lesion in the fourth ventricle region stays IT |
| V2 | Tests on the real derived landmark (skipped with a stated reason where the atlas is not available, as for other atlas tests) | SHA-256 matches; third-ventricle part midline (every voxel within 10 mm of the midline) and voxel counts equal to the provenance record; in the zone map, 0 PV voxels whose only ventricle contact is the third ventricle |
| V3 | Fail-closed tests | Missing or altered landmark → path refused with the reason, never classified with the whole label 4 |
| V4 | Regression on paper D's data (124 scans, G0), using paper D's device-agreement harness | Exactly the lesions listed in `S4_ventricles.G0` change (3, PV → DWM); every other region identical; 0 DIS decisions change |
| V5 | Negative controls, one at a time, anchors asserted unique (as in CAPA-006 to CAPA-011): whole label 4 restored as the landmark; hash check removed; lateral and third classes swapped | Each mutation turns at least one V1–V3 test red; record under `records/risk_verification/` |
| V6 | Bind RC-059 in `rc_test_manifest.json` (status `implemented`, tests and negative control named); UT-CLS-001/002/003 and UT-LBL-001 still pass | CI manifest gate green |
| V7 | Review and approval | Review record per PR and owner decision recorded by the owner (CAPA-012 CA-12.1, CA-12.2) |

## 7. Closure (SPR-001 §4, step 6) — not applicable yet

Resolution description, verification evidence, commit SHA of the fix, affected and fixed versions: *to be completed when the fix is implemented and approved.*

---

**Prepared by**: internal audit from paper D (drafted by the AI coding agent, Claude Code), 2026-10-22.
**Approval**: PENDING owner approval — severity, CAPA linkage (CA-6.14 under CAPA-006, or a new CAPA) and the proposed fix. No approval is recorded here.
