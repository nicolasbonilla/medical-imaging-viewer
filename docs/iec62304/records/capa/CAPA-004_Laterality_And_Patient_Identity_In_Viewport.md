# CAPA-004 — No Laterality Handling and No Patient Identity in the Image Viewport

**CAPA ID**: CAPA-004
**Date Opened**: 2026-07-18
**Source**: Internal code audit (CAPA-001 CA-3, re-verification of all 22 risk controls)
**Severity**: **CRITICAL** — direct patient-safety hazard (QP-002 §5)
**Owner**: *(to be assigned — Software Safety Officer / QMS Manager)*
**Status**: OPEN — investigation complete, corrective action not started
**Procedure**: QP-002 Corrective and Preventive Action

---

## 1. Summary

This device is a brain-MRI viewer whose stated users are neuroradiologists
performing lesion localisation. Two absences were found which compound into the
classic wrong-side / wrong-patient reporting setup:

1. **There is no left/right orientation handling anywhere in the product**, and
   no laterality (L/R) labels on any viewport.
2. **No patient identifier is rendered inside the image viewport**, in any view
   mode.

A mirrored slice, with no L/R marker, carrying no patient name, is the precise
condition under which a radiologist reports a lesion on the wrong side of the
brain, or attributes it to the wrong patient. Neither the code nor the Risk
Management File contains a barrier against either.

Both are **absences of controls that were never claimed**, discovered while
re-verifying controls that *were* claimed. They are filed separately from
CAPA-001 because they are hazard-analysis gaps, not verification gaps.

---

## 2. Finding 1 — no laterality handling (relates to HAZ-006)

### 2.1 Evidence

`backend/app/utils/nifti_utils.py` `load_nifti_from_bytes()` (a **Class C**
module) performs size and parseability checks only:

- `MAX_NIFTI_SIZE_BYTES` upper bound and a 348-byte minimum header check
- `nib.load(tmp_path)` / `img.get_fdata()`

It never reads `img.affine` for orientation, and never calls `nib.aff2axcodes`,
`nib.as_closest_canonical`, or any `ornt` API.

A repository-wide search across `backend/app` and `frontend/src` for every
orientation primitive — `aff2axcodes`, `as_closest_canonical`, `axcodes`,
`ornt`, `neurolog*`, `radiolog*` — returns **no orientation logic at all**. The
only matches are unrelated prose ("radiology report", the `radiologist` role
string, "neuroradiologists" in a docstring).

`ImageOrientation` in `frontend/src/types/imaging.ts` is
`'axial' | 'sagittal' | 'coronal'` — *which plane to slice*, not patient
laterality. It is not a laterality control and must not be mistaken for one in
future verification.

`.affine` **is** read elsewhere (`ms_region_classifier.py`,
`segmentation.py`) but exclusively for atlas resampling — never validated,
never surfaced, never warned upon.

**Consequence**: a volume stored LAS renders mirrored relative to one stored
RAS, with nothing in code or UI to indicate it.

### 2.2 The recorded control overstates reality

`03_Risk_Management_File.md:220` records RC-013 as **PARTIAL** —
*"NIfTI loaded and parsed; explicit orientation warning not yet implemented"* —
which implies orientation is parsed and only the *warning* is missing.
Orientation is not parsed at all. The status is not merely optimistic; it
describes a different system.

The residual-risk table (`:240`) justifies HAZ-006 as ALARP via
*"P1 — auto-transpose + orientation validation"*. **The orientation-validation
half of that ALARP justification does not exist**, so the residual-risk
determination for HAZ-006 is unsupported and must be re-assessed.

### 2.3 The auto-transpose control (RC-012) is a no-op on the common case

`SegmentationCanvasLocal.tsx` detects axis mismatch purely dimensionally:

```
const needsTranspose = maskDims
  && maskDims.width !== imageWidth
  && maskDims.height === imageWidth
  && maskDims.width === imageHeight;
```

For a **square in-plane volume — 256×256, the standard brain-MRI acquisition
matrix — `imageWidth === imageHeight`**, so `maskDims.width !== imageWidth` is
false and `needsTranspose` is always false. A genuinely transposed mask is
dimensionally indistinguishable and renders silently rotated/mirrored with no
detection, no warning and no fallback. The paint-coordinate counterpart fails
identically.

The control is therefore blind in precisely the geometry it most needs to cover.
It also corrects only the overlay mask, never the underlying image, and exists
only in the 2D canvas — `ImageViewer3D` and `MultiPanelViewer` have no
equivalent.

---

## 3. Finding 2 — no patient identity in the viewport (relates to HAZ-009)

### 3.1 Evidence

`ViewerApp.tsx` passes `patientName` into `ImageViewer2D`. In
`ImageViewer2D.tsx` the identifier appears exactly twice — the prop type
declaration and the destructuring in the function signature:

```
patientName?: string;
function ImageViewer2D({ viewerControls, createSegmentationRef, patientName, studyDescription, studyModality }: ImageViewer2DProps) {
```

**It is never rendered.** `patientName`, `studyDescription` and `studyModality`
are dead props — destructured and discarded. Verified by direct inspection: the
two lines above are the complete set of occurrences in the file.

**MRN is not displayed in the viewer under any code path.** The only `mrn`
reference in `ViewerApp.tsx` is passed to a report modal that renders only when
a report is open.

Patient name reaches the screen only as a **navigation breadcrumb** in the page
header, conditional on the `usePatient` query resolving. If it fails or is
pending, the crumb silently vanishes and the viewer shows an unidentified brain.
The 3D and multi-panel paths receive no patient props whatsoever.

### 3.2 The recorded control is false in three separate respects

`03_Risk_Management_File.md:223` records RC-016 as **VERIFIED** —
*"Patient name and MRN prominently displayed in viewer header … Patient
identification visible in viewer header at all times."*

- "**MRN**" — never displayed in the viewer.
- "**from ControlPanel data**" — the data comes from the `usePatient` hook;
  `ControlPanel` receives no patient props.
- "**at all times**" — conditional, absent from the image area, absent in 3D and
  multi-panel modes.

**Consequence**: a screenshot, an exported slice, a printed image or a maximised
viewport carries no patient identifier. This is also the failure mode that
DICOM viewers conventionally guard with a persistent burned-in corner
annotation.

### 3.3 This finding defines a verification anti-pattern

RC-016 is the clearest instance of a defect class worth naming, because it
explains how several controls passed inspection while absent:

> The props exist and look correct **at the call site**. A verifier who greps the
> caller sees `patientName={patientData?.full_name}` and records VERIFIED. The
> receiving component never renders it.

Verification must inspect the **render path**, not the call site. The same
pattern produced the RC-008 finding below.

---

## 4. Related findings from the same re-verification

Recorded here because they share the render-path/enforcement-path blindness,
though they are tracked under CAPA-001 CA-3:

- **RC-008** (Edge AI disclaimer): the disclaimer string exists in the component
  but is gated behind `useState(false)` and renders only after the user clicks a
  "Disclaimer" toggle. A user who runs Quick Screen and reads a confidence-scored
  abnormal/normal verdict sees **no limitation statement at all**. The component's
  own header comment asserts *"A clear disclaimer is always shown"* — the comment
  is false, contradicted twenty lines below it. Verification by grepping for the
  string cannot distinguish a displayed control from a hidden one.

- **RC-018** (RBAC): the model is correct — 4 roles, 15 permissions — but of
  **124 route decorators, 7 enforce a permission and 0 enforce a role**, all
  confined to `auth.py` (user administration and audit viewing). Every clinical
  route — imaging, studies, patients, segmentation, documents, DICOMweb, AI
  report, FHIR — gates on authentication only. A user provisioned as VIEWER can
  delete studies and generate AI reports. Ten of the fifteen permissions are
  never checked anywhere. Counts verified by direct census.

  This compounds CAPA-002: there is neither object-level authorization *nor*
  role-level authorization on clinical data.

---

## 5. Preliminary Root Cause

To be confirmed with the Safety Officer.

The hazard analysis was written around **what the software does** (segment,
measure, report) rather than **how a clinician can be misled by what it
displays**. Hazards of presentation — mirrored anatomy, unlabelled laterality,
unattributed images, a hidden limitation statement — are largely absent from the
RMF, and where present (HAZ-006, HAZ-009) they are discharged by controls that
address a different concern than the hazard names.

This is a different failure from CAPA-001. CAPA-001 concerns controls recorded
as present that were absent. Here the controls are absent *and were never
claimed*, because the hazard was never framed in terms a control could address.

---

## 6. Interim Position

- The device is **not CE-marked, not FDA-cleared and not in clinical use**.
- **No clinical use may proceed** until CA-4.1 and CA-4.2 are closed. These are
  not documentation defects; they are missing safety barriers in the primary
  clinical workflow.
- The ALARP determination for **HAZ-006 must be withdrawn** pending re-assessment
  (§2.2), and HAZ-009 re-assessed (§3.2).

## 7. Action Plan (draft — requires Safety Officer approval)

| ID | Type | Action | Acceptance criteria | Status |
|----|------|--------|--------------------|--------|
| **CA-4.1** | Corrective | Canonicalise orientation on load: read the affine, convert to a known orientation (e.g. `nib.as_closest_canonical`), and **refuse to display** a volume whose orientation cannot be determined rather than guessing. | Test: an LAS volume and an RAS volume of the same subject render identically; a volume with an unusable affine raises rather than rendering. | PENDING |
| **CA-4.2** | Corrective | Render persistent L/R (and A/P, S/I) laterality labels on every 2D viewport, and patient name + MRN as a persistent viewport annotation in 2D, 3D and multi-panel. | Test: labels present in the rendered output for every view mode; identity annotation survives maximise and is included in any export. | PENDING |
| **CA-4.3** | Corrective | Replace RC-012's dimensional heuristic with affine-derived axis order, so detection does not degenerate on square volumes. | Test: a transposed 256×256 mask is detected. | PENDING |
| **CA-4.4** | Corrective | Render the Edge AI disclaimer unconditionally (RC-008); remove the false "always shown" comment. | Test asserts the disclaimer renders without user interaction. | PENDING |
| **CA-4.5** | Corrective | Enforce permissions on clinical routes (RC-018), coordinated with CAPA-002 CA-2.1 so authentication, authorization and role enforcement are designed together rather than in three passes. | Test: a VIEWER receives 403 on delete/generate routes. | PENDING |
| **PA-4.1** | Preventive | Add "hazards of presentation" to the hazard-analysis checklist: for each displayed quantity, ask how a clinician could be misled by it being wrong, absent, mirrored or unattributed. | Checklist updated; RMF re-run against it. | PENDING |
| **PA-4.2** | Preventive | Verification of any UI control must inspect the **render path**, not the call site or the presence of a string in source. | Verification procedure updated; §3.3 cited as the worked example. | PENDING |

---

## 8. Note on Sequencing

CA-4.1 and CA-4.2 are cheap relative to their safety value — orientation
canonicalisation is a known, solved problem with a one-line nibabel primitive,
and viewport annotation is presentational. They should not wait on the larger
authorization work in CAPA-002.

CA-4.3 depends on CA-4.1: once orientation is canonical, the transpose heuristic
can be derived from the affine instead of guessed from shape.

---

**Prepared by**: Internal code audit. Findings in §2, §3 and §4 were confirmed by
direct inspection of the cited source, not accepted from a secondary report.
**Requires**: review, root-cause confirmation and sign-off by the Software Safety
Officer. The action plan above is a draft prepared by the finder and must not be
treated as approved.
