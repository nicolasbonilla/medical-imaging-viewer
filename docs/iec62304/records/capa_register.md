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
| [CAPA-001](capa/CAPA-001_Risk_Control_Verification_Integrity.md) | 2026-07-16 | Internal audit (code inspection) | **Critical** | Four risk controls (RC-006, RC-007, RC-010, RC-017) recorded as VERIFIED in the RMF / RCV-SUMMARY are not implemented as described; RCV-SUMMARY reports "Failed 0". Unauthenticated WebSocket streams imaging data. | Verification process accepts unexecuted, unreproducible, self-attested prose as objective evidence; no risk control is bound to an automated test and CI cannot contradict the record. | *TBA — Software Safety Officer* | 2026-07-23 | 2026-08-15 | **OPEN** | Pending — negative-control test (deliberately remove a control; CI must go red) | — |

---

## Notes

- This register was created as action **CA-6** of CAPA-001: QP-002 §6 required it and
  it did not exist. Its absence is recorded here rather than silently remedied.
- No Declaration of Conformity may be executed while a Critical CAPA affecting risk
  control verification is open.
