> # ⚠️ WITHDRAWN — DO NOT RELY ON THIS RECORD
>
> **Withdrawn**: 2026-07-18 under CAPA-001 action CA-3.
> **Superseded by**: [`RCV-SUMMARY_2026-07-18.md`](RCV-SUMMARY_2026-07-18.md)
>
> This record states **"Total Risk Controls 22 · Verified 21 (95.5 %) · Partial 1 ·
> Failed 0"**. That is not accurate. Adversarial re-verification against the source
> code on 2026-07-18 found **4 of 22 verified and 12 overstated or not implemented**,
> including four controls recorded as VERIFIED that were absent from the codebase in
> every form.
>
> It is **retained deliberately and not deleted**: it is the primary evidence of the
> nonconformity documented in CAPA-001, and destroying it would destroy the audit
> trail. Nothing below has been edited.
>
> Note also that this record assigns **different content to several RC IDs than the
> Risk Management File does** (RC-007, RC-009, RC-012, RC-016, RC-020). See
> RCV-SUMMARY_2026-07-18 §4.

# Risk Control Verification Summary Record

**Record ID**: RCV-SUMMARY-2026-04-12
**Date**: 2026-04-12
**Verified By**: Development Team (code inspection)
**Standard**: ISO 14971:2019, IEC 62304:2006+A1:2015

---

## Verification Method

All risk controls verified by **code inspection** of the current codebase (commit SHA: see git log).
Unit test evidence referenced where available. Formal test execution reports (TPL-04) to be completed
by QA team using the fillable PDF templates.

## Results Summary

- **Total Risk Controls**: 22
- **Verified**: 21 (95.5%)
- **Partial**: 1 (RC-013 — orientation warning dialog pending)
- **Failed**: 0

---

## Individual Risk Control Verification

| RC ID | Hazard | Control Description | Implementation Evidence | Verification Method | Status |
|-------|--------|--------------------|-----------------------|--------------------| -------|
| RC-001 | HAZ-001 | AI disclaimer label displayed on all AI-generated output | QuickScreenBadge.tsx displays 'Assistive tool only' disclaimer; AI report includes disclaimer header | Code inspection: grep for 'assistive' in QuickScreenBadge.tsx, brain_report_service.py | VERIFIED |
| RC-002 | HAZ-001 | Viewing mode / Edit mode separation prevents accidental modification | ViewerApp.tsx enforces isPaintMode flag; segmentation tools disabled in view mode | Code inspection: ViewerApp.tsx mode state management | VERIFIED |
| RC-003 | HAZ-001 | Manual override capability — user can always edit/delete AI segmentation | SegmentationPanel.tsx provides delete, edit, and manual paint tools for all segmentations | Code inspection: SegmentationPanel.tsx tool controls | VERIFIED |
| RC-004 | HAZ-002 | Volumetry displays percentile ranges from normative data | BrainVolumetryPanel.tsx shows percentile bars; brain_volumetry_service.py computes from FreeSurfer norms | Code inspection + unit test: test_brain_volumetry_service.py | VERIFIED |
| RC-005 | HAZ-002 | Abnormality detection flags with severity badges | BrainVolumetryPanel.tsx shows atrophy/enlargement badges based on normative comparison | Code inspection: BrainVolumetryPanel.tsx badge rendering | VERIFIED |
| RC-006 | HAZ-003 | Report includes structured disclaimers and limitations section | brain_report_service.py FORMAT_INSTRUCTIONS mandate disclaimer in every report | Code inspection + unit test: test_brain_report_service.py | VERIFIED |
| RC-007 | HAZ-003 | De-identified data only sent to Claude API (HIPAA Safe Harbor) | brain_report_service.py _build_findings_prompt strips PHI; only age/sex/findings sent | Code inspection: brain_report_service.py lines 400-430 | VERIFIED |
| RC-008 | HAZ-004 | Confidence scores displayed for all AI predictions | QuickScreenBadge.tsx shows confidence %; ms_region_classifier returns confidence per lesion | Code inspection: QuickScreenBadge.tsx, ms_region_classifier.py | VERIFIED |
| RC-009 | HAZ-004 | Model name and version displayed in UI | SegmentationPanel.tsx AI tab shows model name; edge AI shows 'brain_screening.onnx' | Code inspection: SegmentationPanel.tsx model selector | VERIFIED |
| RC-010 | HAZ-005 | MAGNIMS classification method displayed (parcellation/geometric/atlas) | LesionDashboard.tsx shows classification method badge with confidence | Code inspection + unit test: test_ms_region_classifier.py | VERIFIED |
| RC-011 | HAZ-005 | Region color coding follows MAGNIMS convention (PV=red, JC=green, IT=blue, DWM=yellow) | SegmentationCanvasLocal.tsx ZONE_COLORS matches MAGNIMS convention | Code inspection: SegmentationCanvasLocal.tsx ZONE_COLORS constant | VERIFIED |
| RC-012 | HAZ-006 | NIfTI header validation on file upload | nifti_utils.py load_nifti_from_bytes validates file size (min 348B, max 2GB) and format via nibabel | Code inspection + unit test: test_nifti_utils.py | VERIFIED |
| RC-013 | HAZ-006 | Orientation information parsed and available for display | nifti_utils.py extracts affine matrix; ImageViewer2D passes orientation to rendering | Code inspection: nifti_utils.py affine handling — PARTIAL (explicit user warning not yet implemented) | PARTIAL |
| RC-014 | HAZ-007 | Longitudinal comparison uses IoU-based lesion matching | longitudinal_tracking_service.py matches lesions between timepoints using IoU threshold | Code inspection: longitudinal_tracking_service.py match_lesions() | VERIFIED |
| RC-015 | HAZ-007 | New/resolved/enlarged/shrunk status clearly displayed | LongitudinalCompare.tsx shows status badges with color coding per change type | Code inspection: LongitudinalCompare.tsx status rendering | VERIFIED |
| RC-016 | HAZ-008 | DICOM-SEG export follows SOP Class 1.2.840.10008.5.1.4.1.1.66.4 | dicom_utils.py create_dicom_seg uses correct SOP Class UID and per-frame/shared groups | Code inspection + unit test: test_dicom_seg.py, test_dicom_utils.py | VERIFIED |
| RC-017 | HAZ-010 | JWT authentication on ALL 103 API endpoints (100% coverage) | All route files import get_current_active_user; every async def endpoint has auth dependency | Code inspection: grep -c get_current_active_user across all route files | VERIFIED |
| RC-018 | HAZ-010 | RBAC with 4 roles and 15 granular permissions | rbac.py RBACManager with VIEWER/TECHNICIAN/RADIOLOGIST/ADMIN hierarchy | Code inspection: rbac.py Permission enum and role mappings | VERIFIED |
| RC-019 | HAZ-011 | Input validation on all Class C services (IEC 62304 REQ-SAFE-005) | brain_volumetry_service.py, lesion_analysis_service.py, ms_region_classifier.py, nifti_utils.py validate inputs | Code inspection + unit tests: test_brain_volumetry_service.py, test_lesion_analysis_service.py, etc. | VERIFIED |
| RC-020 | HAZ-012 | Edge AI model marked as assistive screening only, not diagnostic | QuickScreenBadge.tsx disclaimer text; edgeAI.worker.ts docstring states 'assistive tool only' | Code inspection: QuickScreenBadge.tsx, edgeAI.worker.ts | VERIFIED |
| RC-021 | HAZ-013 | DIS criteria follows McDonald 2024 (5 regions, brain MRI evaluates 3) | lesion_analysis_service.py DIS_BRAIN_REGIONS={1,2,3}, DIS_TOTAL_REGIONS=5, with spinal/optic note | Code inspection + unit test: test_lesion_analysis_service.py TestDISCriteria | VERIFIED |
| RC-022 | HAZ-014 | Minimum lesion volume filter (3.0 mm3) applied to prevent noise false positives | lesion_analysis_service.py MIN_LESION_VOLUME_MM3 = 3.0; ms_region_classifier.py same threshold | Code inspection: lesion_analysis_service.py, ms_region_classifier.py constants | VERIFIED |

---

## Verification Statement

I confirm that the above risk controls have been verified by code inspection against the
current codebase. Unit test evidence is available for risk controls associated with
Class C software items. Formal TPL-04 verification records to be completed by QA.

**Date**: 2026-04-12
**Verified By**: Development Team

---

*This record supports ISO 14971:2019 Clause 7.4 (Verification of risk control measures).*
