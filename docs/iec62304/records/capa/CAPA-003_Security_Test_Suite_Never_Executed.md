# CAPA-003 — Security Test Suite Has Never Executed

**CAPA ID**: CAPA-003
**Date Opened**: 2026-07-18
**Source**: Internal code audit, discovered while implementing CAPA-001 PA-2
**Severity**: **MAJOR** — significant quality-system deviation (QP-002 §5)
**Owner**: *(to be assigned — Software Safety Officer / QMS Manager)*
**Status**: OPEN — investigation complete, corrective action not started
**Procedure**: QP-002 Corrective and Preventive Action

---

## 1. Detection

CAPA-001 root cause #4 recorded that `tests/security/` is never run by CI.
Adding it to the pipeline (PA-2) required first confirming that it passes. It
does not. It never has.

## 2. Finding

### 2.1 The suite could not be imported

`tests/security/test_authentication.py`, `test_encryption.py` and
`test_input_validation.py` all import from **`app.core.security.auth`**.

That module does not exist. `git log --diff-filter=D` shows it has **never
existed** in this repository's history — it was not deleted, it was never
written. The real classes live elsewhere:

| Imported as | Actually at |
|---|---|
| `app.core.security.auth.PasswordManager` | `app.security.password.PasswordManager` |
| `app.core.security.auth.TokenManager` | `app.security.jwt_manager.TokenManager` |

Every one of these modules therefore failed at **collection**. Not a single
assertion in `tests/security/` has ever been evaluated.

`tests/conftest.py` references the same non-existent path.

### 2.2 After repairing the import, the suite does not pass

The import in `test_authentication.py` was corrected as part of this
investigation, to establish the true state. Result:

```
63 failed, 9 passed, 43 errors
```

Dominant causes: 288 `AttributeError`, 76 `TypeError`, and 20 further
`ModuleNotFoundError: No module named 'app.core.security.auth'` from the two
files not yet repaired. Sampled instance:
`AttributeError: 'Settings' object has no attribute 'JWT_SECRET_KEY'` — though
`JWT_SECRET_KEY` *is* defined at `app/core/config.py:23`, so the mismatch is
deeper than a rename.

**Assessment**: the suite was written against a codebase shape that does not
exist. It is aspirational scaffolding, not verification.

### 2.3 Why this matters beyond the tests

`backend/pytest.ini:52-63` registers markers naming the standards these tests
purport to satisfy — `security: Security-specific tests (ISO 27001 A.14.2.8)`,
`compliance: ISO 27001/HIPAA compliance tests`, `audit: Audit logging and
compliance tests`. The existence of this suite is the kind of artefact an
auditor would accept as evidence of security verification. It is evidence of
nothing.

Note the ordering: **CAPA-002 (any authenticated user can read any patient's
imaging) is exactly the class of defect a working security suite should catch.**
The suite's silence was not evidence of safety.

## 3. Preliminary Root Cause

To be confirmed with the Safety Officer. Initial assessment — the same root
cause as CAPA-001, in a different medium:

> Verification artefacts were authored as descriptions of an intended system and
> recorded as completed work, with no execution step able to contradict them.
> CAPA-001 found this in prose records; CAPA-003 finds it in test code. In both
> cases the pipeline was structurally incapable of reporting the gap.

This is why CAPA-001 PA-2 (a CI gate that actually runs the checks) is the
higher-leverage action: it addresses the mechanism, not the instances.

## 4. Interim Measure

`tests/security/` has been added to CI as an explicitly **non-blocking** step
that emits a warning naming this CAPA.

This is deliberate and is not a workaround:

- Making it **blocking** today would red-line every build and pressure the team
  into deleting or skipping the suite — converting a visible problem into an
  invisible one.
- **Deleting** it would destroy the evidence and the specification of intent it
  contains.
- **Omitting** it from CI is precisely what caused the problem.

The step is loud and dated so that no reader mistakes a green pipeline for
passing security tests. **`continue-on-error: true` MUST be removed as the final
act of closing this CAPA.**

## 5. Action Plan (draft — requires Safety Officer approval)

| ID | Type | Action | Acceptance criteria | Status |
|----|------|--------|--------------------|--------|
| **CA-3.1** | Corrective | Repair the imports in `test_encryption.py`, `test_input_validation.py` and `tests/conftest.py` to reference modules that exist. | All three modules import; the suite collects. | PENDING |
| **CA-3.2** | Corrective | Triage the 63 failures / 43 errors. For each: fix the test if the code is right, or raise a defect if the code is wrong. Do not delete a failing security test without a recorded rationale. | Every test either passes or is linked to a tracked defect. | PENDING |
| **CA-3.3** | Corrective | Remove `continue-on-error` from the CI step. | `tests/security/` gates the build. | PENDING |
| **PA-3.1** | Preventive | Add a CI check that every test directory under `tests/` is referenced by at least one workflow step. | A new, unreferenced test directory fails CI. | PENDING |

## 6. Note on CA-3.2

The triage matters more than the repair. Each of the 63 failures is one of two
things: a test that encodes a correct security expectation the code does not
meet (a **defect**, possibly serious — CAPA-002 was found this way), or a test
that encodes an expectation that was never valid (a **documentation error**).
Fixing them indiscriminately to make CI green would discard exactly the signal
this CAPA exists to recover.

---

**Prepared by**: Internal code audit
**Requires**: review, root-cause confirmation and sign-off by the Software Safety
Officer. The action plan above is a draft prepared by the finder and must not be
treated as approved.
