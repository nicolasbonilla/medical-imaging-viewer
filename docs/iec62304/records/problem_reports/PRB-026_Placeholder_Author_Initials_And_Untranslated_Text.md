# PRB-026 — "current_user" as Segmentation Author, Two Different Patient Initials, Spanish Text in the English Interface

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: see PRB-020. GitHub Issue: not raised.*

**Problem ID**: PRB-026
**Reporter**: browser capture of the release candidate, 2026-10-28 (F06, F16, F03); reproduced on `main`
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`
**Severity**: **Major** (proposed; attribution of clinical work shown falsely; an inconsistent patient-identification cue,
HAZ-009; a Class C provenance badge not in the user's language). **N. G. Bonilla Vargas — approved 2026-10-30 (PR #70).**
**Status**: OPEN — DRAFT. Fix on branch `fix/platform-security-findings-prb020`.

## A. Segmentation author "current_user" (F06)
**Actual**: every segmentation, whoever made it, showed the author "current_user": the viewer filled the field with that
placeholder (`useSegmentationData.ts:128`, `SegmentationPanel.tsx:333`) and displayed it (`SegmentationPanel.tsx:613`,
`SegmentationList.tsx:308`). The server never stored who created a segmentation: the create route passes the
authenticated username (`segmentation.py`), but `create_segmentation` used it only for the AI-draft sequence confirmation
and built the metadata without it (`segmentation_service.py:176-188`).
**Fix**: `SegmentationMetadata.created_by` (username of the authenticated user, set by the server at creation; the
request cannot set it); the viewer shows the recorded author (`utils/segmentationAuthor.ts`) or "Author not recorded"
(older segmentations, tool or script imports) — never a placeholder and never the name of whoever is signed in.
Requirement **REQ-FUNC-111**; risk control **RC-088** (HAZ-010 attribution).

## B. Patient initials "DD" on the list, "DP" on the record (F16)
**Actual**: the list card took the first and last word of the full name (`PatientCard.tsx:44-55`; the list item carried
no name parts: "Demo Patient (public data)" → "DD"); the record banner the first two words (`PatientBanner.tsx:185`;
a title in the full name, "Dr. Anna Beispiel", gave "DA"). An avatar is a patient-identification cue (HAZ-009).
**Fix**: one rule, `utils/patientDisplay.ts::patientInitials` — first letter of the given name and of the family name
(punctuation skipped, case per the user's language); the full name only when a part is missing. The list item now
carries `given_name` and `family_name` (`PatientSummary`). Requirement **REQ-UI-011**; risk control **RC-087**.

## C. Spanish text written into the code (F03)
**Actual** (shown in every interface language): `NiivueViewer2D.tsx:160` "No se pudo cargar el volumen", `:203`
"Cargando volumen…", `:214` "W/L GPU · solo visualización (para pintar, usa el modo estándar)"; `ImageViewer2D.tsx:357`
"Cargando visor GPU…"; `ViewerControls.tsx:122` tooltip "Ventana/nivel instantáneo por GPU (solo visualización)" (key
missing in every locale); `viewer/SegmentationRow.tsx:16-29` provenance badges "Experto", "IA", "IA · investigación",
"Sin verificar" (a Class C traceability control: expert vs validated tool vs legacy over-segmenter) and the English
"Show/Hide overlay"; `ConformalPanel.tsx:21-164` — the whole CALM-MS second-reader panel (always shown in the Tools tab).
**Fix**: every string above in `en/es/de.json` (`viewer.*`, `provenance.*`, `conformal.*`); the code keeps only English
fallbacks. Requirement **REQ-UI-010**; risk control **RC-087**.
Found while doing it (not changed): 120 keys used in the code are missing from `en.json` and most from `es/de.json`
(their English default shows in every language), and three locale files hold duplicate keys inside sections
(`common.error`, `viewer.colormap`, `viewer.viewMode`, `es: viewer.windowLevel` — the last one wins). Owner decision.

## Verification
Backend `test_prb021_patient_scope_creator_counts.py` — `test_rc088_prb026_*` (2: the creator stored with the
metadata; the request model has no such field — positive control) and `test_rc087_prb026_*` (1: the list item carries
the name parts). Frontend `useSegmentationData.prb026.test.tsx` — `rc088 prb026 *` (5), `patientInitials.prb026.test.tsx`
— `rc087 prb026 *` (4), `i18nStrings.prb026.test.tsx` — `rc087 prb026 *` (5: badges in en/de/es, the CALM-MS panel in
English, no Spanish literal left in the five components, every new key in all three locales). On `70cc5c7` all fail
except the positive control. Negative controls A1–A2, F9–F21.

## Owner decisions (PENDING)
Severity Major; the Spanish and German wording of the new keys awaits a native speaker's review (the German
"Experte"/"KI" badges and the CALM-MS texts were translated by the agent); whether the 120 missing keys and the duplicate
keys are fixed under a separate change (proposed).

## Review of PR #70 (2026-10-28) *(review of PR #70, 2026-10-28 — DRAFT, N. G. Bonilla Vargas — approved 2026-10-30 (PR #70))*

Test gap m8: no test showed that the create **route** passes the authenticated user (only the service and the request
schema were tested; removing `created_by=current_user.username` from the route passed every test). Added
`test_rc088_prb026_r1_the_route_records_the_authenticated_user` (a request through the real route with a `created_by` in the
body: the stored author is the signed-in user). It passes at `7de9334` (the behaviour was right); its value is shown by
negative control V24 (the route passes no user → the test fails).
