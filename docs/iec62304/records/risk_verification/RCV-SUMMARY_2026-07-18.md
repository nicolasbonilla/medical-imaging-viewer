# Risk Control Verification Summary — 2026-07-18

**Supersedes**: `RCV-SUMMARY_2026-04-12.md`, which is **withdrawn as inaccurate**.
**Raised under**: CAPA-001 action CA-3.
**Method**: adversarial re-verification of all 22 risk controls against source
code, conducted by four independent auditors briefed to *falsify* each claim
rather than confirm it. The seven most severe findings were then re-confirmed
personally by direct inspection before being recorded here.
**Status**: this record is itself provisional until an independent verifier
distinct from the implementer signs it off (CAPA-001 PA-3).

---

## 1. Headline

| | 2026-04-12 record | 2026-07-18 actual |
|---|---|---|
| Verified | 21 / 22 (95.5 %) | **4 / 22 (18 %)** |
| Partial | 1 | 6 |
| Overstated / not implemented | **0** | **12** |
| Correctly recorded as absent | 0 | 0 |

The previous record's claim of **"Failed 0"** was false. It is not a matter of
degree: of 22 controls, twelve are recorded as protecting patients in ways the
code does not.

---

## 2. Verification standard applied

A control is recorded **VERIFIED** only if all of the following hold:

1. The control exists in the code, at the cited location.
2. Its behaviour matches the **wording** of the control, not merely its theme.
3. For UI controls, the value reaches the **render path** — not merely a prop, a
   type, or a string present in source.
4. For enforcement controls, the check is **applied at the call sites** it claims
   to cover, not merely defined.
5. It is bound to an automated test whose removal turns CI red.

Criteria 3 and 4 were added as a result of this exercise; see §5.

---

## 3. Results

### 3.1 Verified (4)

| RC | Control | Evidence |
|----|---------|----------|
| RC-006 | Report carries mandatory physician-review disclaimer | `brain_report_service.py::_apply_disclaimer`; `test_rc006_report_disclaimer.py`; negative control 8 failed (CAPA-001 §5.1). Implemented under CA-1 — was absent at the time of the previous record. |
| RC-017 | Authentication on all endpoints incl. WebSocket | `websocket.py::_authenticate_websocket`; `test_rc017_websocket_auth.py`; two negative-control vectors (CAPA-001 §5.2). Implemented under CA-2. **Authentication only** — authorization is absent, see CAPA-002. |
| RC-014 | Longitudinal tri-colour overlay (TP1/TP2/overlap) | `SegmentationCanvasLocal.tsx` — blue/red/green, overlap branch correctly tested first, bounds-guarded, fails closed on dimension mismatch. The one control found implemented exactly as written. |
| RC-009 | Edge AI hidden when model unavailable | `useEdgeAI.ts` HEAD check; correctly also rejects `text/html`, defeating the Firebase SPA-rewrite false positive. Broader than claimed. Residual: brief pre-resolution window where the button is clickable; fails to an error, not a wrong answer. **Note the RCV/RMF ID conflict in §4.** |

### 3.2 Partial (6)

| RC | Recorded | Actual |
|----|----------|--------|
| RC-002 | VERIFIED — mode separation | Control is real and effective (`isPaintMode` default false, not persisted, enforced via `canInteract`; no AI path enables it). **The cited file is wrong**: the toggle is in `ImageViewer2D.tsx`, not `ViewerApp.tsx`. The only relevant line in the cited file sets paint mode *on*. UI-layer only; no server-side equivalent. |
| RC-011 | VERIFIED — method displayed (EDT/Atlas/Geometric) | Method *is* displayed, and honestly resolves to the effective method under `auto`. But the backend has **five** methods and the dropdown exposes **three**; "EDT" and "Atlas" are not selectable method names at all. The control's wording cannot be mapped to the screen. |
| RC-012 | VERIFIED — auto-transpose detection | Detector is purely dimensional and is therefore a **no-op on square (256×256) volumes** — the standard brain-MRI matrix. Blind in the geometry it most needs to cover. See CAPA-004 §2.3. |
| RC-015 | VERIFIED — DIS per-region details with qualifying lesion counts | Implements 3 of 5 McDonald 2024 DIS regions — **correctly and honestly**: spinal cord and optic nerve require sequences not present in a brain mask, the payload declares `spinal_cord_evaluated: false`, and the UI scopes the badge to "Brain MRI: n/3". The **counts are not displayed**: `qualifying_lesion_count` is returned by the backend and declared in the TypeScript type but read by no component. |
| RC-019 | VERIFIED — DICOM-SEG, "8 unit tests" | Code is correct: SOP Class UID `1.2.840.10008.5.1.4.1.1.66.4` set in both file meta and SOP Common, header modules present. **The test count is false — there are 7, not 8**, with no parametrisation to expand it. A tally written from memory rather than from the file. |
| RC-013 | PARTIAL — "loaded and parsed; orientation warning pending" | **Overstated even as PARTIAL.** No orientation is parsed. See §3.3. |

### 3.3 Overstated or not implemented (12)

| RC | Recorded | Actual | Tracked |
|----|----------|--------|---------|
| RC-001 | VERIFIED — all AI segmentation results labelled "assistive — requires physician review" | The phrase exists **nowhere** in the codebase. `SegmentationPanel.tsx` (889 lines) carries no disclaimer of any kind; AI masks are visually indistinguishable from hand-drawn ones. The cited `QuickScreenBadge.tsx` is a different feature (slice classifier, not segmentation). | CA-3 |
| RC-003 | VERIFIED — manual tools "always available" | Rendered under **two** conditions (`!is3D && activeSegmentation`). In 3D view the clinician has no manual override at all. "Always" is false. | CA-3 |
| RC-004 | VERIFIED — percentile ranges with normative reference | Normative table has **no provenance**; only 11 of 32 structures covered; `patient_sex` accepted and never used. The render path is **dead** — the sole call site omits `patientAge`, so no percentile is ever computed. No range shown, bar scaled by volume not percentile, value hover-only. | **CAPA-005** |
| RC-005 | VERIFIED — abnormality flags show threshold criteria | Thresholds exist only in Python comments; never reach the API or UI. Badge shows a bare word. Flag can never fire (same dead path). | **CAPA-005** |
| RC-007 | VERIFIED — no auto-commit without confirmation | Outcome holds — exhaustive search of write primitives, FHIR (GET-only) and DICOMweb (inbound-only) found no persistence path. But it holds **by absence of the feature, not by a control**: there is no confirmation gate, no export function, and no test to turn CI red if auto-save were added. | CA-3 |
| RC-008 | VERIFIED — Edge AI badge displays disclaimer | Disclaimer is gated behind `useState(false)` and renders only after a click. A user reading a confidence-scored verdict sees **no limitation statement**. The file's own comment claims "A clear disclaimer is always shown" — false, contradicted in the same file. | **CAPA-004** §4 |
| RC-010 | VERIFIED — per-lesion confidence displayed | The geometric path sets `confidence = None` **deliberately**, because it has no calibrated confidence. The code is more honest than the document. Recorded as `deliberately_absent`, not as a defect. | CA-3 |
| RC-016 | VERIFIED — patient name and MRN in viewer header "at all times" | `patientName` reaches `ImageViewer2D` and is **never rendered** — a dead prop. **MRN is displayed nowhere in the viewer.** Identity appears only as a conditional breadcrumb; 3D and multi-panel receive no patient props. | **CAPA-004** §3 |
| RC-018 | VERIFIED — RBAC, 4 roles / 15 permissions | Model is correct. Enforcement is not: of **124 route decorators, 7 enforce a permission and 0 enforce a role**, all in `auth.py`. Every clinical route gates on authentication only. A VIEWER can delete studies and generate reports. 10 of 15 permissions are never checked. | **CAPA-004** §4 |
| RC-021 | VERIFIED — 30 s timeout with error message | **No timeout exists anywhere** in the report path — zero occurrences of "timeout" in `brain_report_service.py` or `ai_report.py`. There is no `CLAUDE_TIMEOUT` setting. The codebase sets explicit timeouts elsewhere, so this is an omission, not a convention. Additionally the `async def` handler calls the **synchronous** client without a threadpool, so a hung upstream call blocks the event loop for the whole worker. | CA-3 |
| RC-022 | VERIFIED — "confirmed by user … documented in project memory" | Recollection is not objective evidence. The code does not depend on the assumption: it silently defaults `voxel_spacing` to 1 mm — the harm HAZ-014 describes. | CA-1 CA-5 |
| RC-007′ | VERIFIED (RCV-2026-04-12 wording) — de-identification before third-party API | No de-identification routine exists under `backend/app/`. Free-text fields are interpolated verbatim into the prompt. | CA-1 CA-4 |

---

## 4. Structural finding — the same ID denotes different controls

The RMF and the withdrawn RCV-SUMMARY **assign different content to the same RC
IDs**. Confirmed for RC-007, RC-009, RC-012, RC-016 and RC-020: for example the
RMF's RC-009 is model-availability gating, while the RCV-SUMMARY's RC-009 is
"model name and version displayed in UI" (which is itself not implemented — no
version string is rendered anywhere).

**Any traceability audit keyed on an RC ID resolves to a different control
depending on which document is opened.** This is a more fundamental defect than
any individual false row: the identifier scheme does not identify.

Aggravating: `docs/iec62304/generate_audit_records.py` hardcodes the evidence
strings, meaning parts of the audit record are **machine-generated from fixed
text rather than from inspection**. A generated record cannot verify anything;
it can only restate what someone typed.

---

## 5. Why the previous verification passed — the two blind spots

CAPA-001 identified the root cause as prose accepted in place of executed checks.
This exercise revealed the two specific mechanisms:

**Call-site blindness.** RC-016 is the worked example. `ViewerApp.tsx` reads
`patientName={patientData?.full_name}` — a verifier grepping the caller sees a
correct-looking wiring and records VERIFIED. The receiving component never
renders it. **Verification must inspect the render path.**

**Definition-site blindness.** RC-018 is the worked example. `Permission` defines
15 permissions and `RBACManager` maps them to roles — a verifier reading the
security module sees a complete RBAC implementation. Seven of 124 routes apply
it. **Verification must count the enforcement sites.**

Both blind spots share a shape: *the control was verified where it was written,
not where it takes effect.* This is now criterion 3 and 4 in §2.

---

## 6. Consequences

1. **The RMF's residual-risk determinations are unsupported.** HAZ-006's ALARP
   justification cites "orientation validation" which does not exist; HAZ-003,
   HAZ-004, HAZ-005, HAZ-009, HAZ-010 and HAZ-014 all rest at least partly on
   controls listed in §3.3. The residual-risk table must be re-derived from this
   record, not amended.
2. **No Declaration of Conformity may be executed.** Already stated in CAPA-001;
   restated here with a fuller basis.
3. **CAPA-004 and CAPA-005 were opened** from these findings, for hazards that
   were never claimed rather than claimed-and-absent.
4. **The 2026-04-12 record must be marked withdrawn in place**, not deleted — it
   is evidence of the nonconformity.

---

## 7. What this record does not claim

- It is **not** independently verified. It was produced by the same process it
  criticises — one party inspecting and recording. CAPA-001 PA-3 requires an
  independent verifier, and until that is done this record carries the same
  structural weakness as its predecessor, differing only in that it is
  adversarial and cites evidence that can be re-run.
- Only **RC-006 and RC-017** are bound to automated tests. The other 20 rows rest
  on inspection, which is exactly what CAPA-001 PA-1 says is insufficient. They
  are recorded here as *findings*, not as verified controls, and
  `rc_test_manifest.json` reflects that distinction.
- The four VERIFIED controls in §3.1 should be read as "verified to the standard
  in §2 at commit HEAD of `capa/rmf-verification-integrity`", not as a permanent
  property.

---

**Prepared by**: Internal code audit, 2026-07-18.
**Requires**: independent verification and Software Safety Officer sign-off
before any row here is treated as a verification record under ISO 14971.
