# CAPA Register

Maintained per **QP-002 Corrective and Preventive Action Procedure §6**.

Every CAPA must appear here with: ID, date opened, source, severity, description,
root cause, actions, owner, target dates, status, effectiveness result, date closed.

Severity definitions (QP-002 §5):
- **Critical** — patient safety risk or regulatory non-compliance.
  Investigation 3 d · action plan 7 d · implementation 7 d · verification 30 d.
- **Major** — significant quality system deviation. 10 / 30 / 30 / 60 d.
- **Minor** — isolated process improvement. 30 / 90 / 90 / 90 d.

---

| CAPA ID | Opened | Source | Severity | Description | Root cause (summary) | Owner | Impl. due | Verif. due | Status | Effectiveness | Closed |
|---------|--------|--------|----------|-------------|----------------------|-------|-----------|-----------|--------|---------------|--------|
| [CAPA-001](capa/CAPA-001_Risk_Control_Verification_Integrity.md) | 2026-07-16 | Internal audit (code inspection) | **Critical** | Four risk controls (RC-006, RC-007, RC-010, RC-017) recorded as VERIFIED in the RMF / RCV-SUMMARY are not implemented as described; RCV-SUMMARY reports "Failed 0". Unauthenticated WebSocket streams imaging data. | Verification process accepts unexecuted, unreproducible, self-attested prose as objective evidence; no risk control is bound to an automated test and CI cannot contradict the record. | *TBA — Software Safety Officer* | 2026-07-23 | 2026-08-15 | **OPEN** | RC-006 and RC-017 negative controls executed and passed (§5.1, §5.2). CA-3/4/5 and PA-1/2/3 outstanding. | — |
| [CAPA-002](capa/CAPA-002_Broken_Object_Level_Authorization.md) | 2026-07-18 | Internal audit (found while implementing CAPA-001 CA-2) | **Critical** | Imaging routes authenticate the caller but never authorize the requested object. `file_id` is a caller-supplied GCS path; any authenticated user can read any patient's imaging. OWASP API1:2023. | Preliminary: threat model placed the trust boundary at the perimeter. No SRS requirement states which users may access which records, so no control was designed and no test could exist. Requirements gap, not only a verification gap. | *TBA — Software Safety Officer* | *TBA* | *TBA* | **OPEN** | Not started — action plan is a draft awaiting approval | — |

| [CAPA-003](capa/CAPA-003_Security_Test_Suite_Never_Executed.md) | 2026-07-18 | Internal audit (found while implementing CAPA-001 PA-2) | **Major** | `tests/security/` has never executed: all three modules import `app.core.security.auth`, a path that has never existed in the repo's history, so the suite failed at collection. CI never ran the directory, so nothing reported it. After repairing one import: 63 failed / 43 errors / 9 passed. | Preliminary: same as CAPA-001 in a different medium — verification artefacts authored as descriptions of an intended system, with no execution step able to contradict them. | *TBA — Software Safety Officer* | *TBA* | *TBA* | **OPEN** | Interim: added to CI as an explicitly non-blocking, warning-emitting step. `continue-on-error` must be removed to close. | — |

| [CAPA-004](capa/CAPA-004_Laterality_And_Patient_Identity_In_Viewport.md) | 2026-07-18 | Internal audit (CAPA-001 CA-3 re-verification) | **Critical** | No left/right orientation handling anywhere in the product and no laterality labels on any viewport; no patient identifier rendered in the image viewport in any view mode (`patientName` is a dead prop, MRN displayed nowhere). Compounds into wrong-side / wrong-patient reporting. Also: Edge AI disclaimer hidden behind a click; 7 of 124 routes enforce a permission, 0 enforce a role. | Preliminary: the hazard analysis was framed around what the software *does*, not how a clinician can be *misled by what it displays*. Hazards of presentation are largely absent from the RMF. | *TBA — Software Safety Officer* | *TBA* | *TBA* | **OPEN** | Not started — action plan is a draft awaiting approval | — |
| [CAPA-005](capa/CAPA-005_Unsourced_Normative_Reference_Data.md) | 2026-07-18 | Internal audit (CAPA-001 CA-3 re-verification) | **Critical** | Brain volumetry classifies structures as atrophic/enlarged against a hardcoded normative table with no citation, cohort, n or version; 11 of 32 structures covered; `patient_sex` accepted and never used. Separately the feature never executes — the sole call site omits `patientAge`. | Preliminary: reference data was treated as an implementation constant rather than a controlled clinical input. Nothing distinguishes a number encoding an engineering choice from one encoding a medical fact. | *TBA — Software Safety Officer* | *TBA* | *TBA* | **OPEN** | Not started. **Ordering constraint: Finding 1 (provenance) must be closed before Finding 2 (dead path) — wiring `patientAge` through would silently activate unvalidated clinical logic.** | — |

---

## Notes

- This register was created as action **CA-6** of CAPA-001: QP-002 §6 required it and
  it did not exist. Its absence is recorded here rather than silently remedied.
- No Declaration of Conformity may be executed while a Critical CAPA affecting risk
  control verification is open.
