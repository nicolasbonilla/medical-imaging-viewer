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

---

## Notes

- This register was created as action **CA-6** of CAPA-001: QP-002 §6 required it and
  it did not exist. Its absence is recorded here rather than silently remedied.
- No Declaration of Conformity may be executed while a Critical CAPA affecting risk
  control verification is open.
