# PRB-032 — Input Validators: Host-Dependent Absolute-Path Check, Audit Event Types That Never Existed, Five Open Detection Gaps

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: next free after PRB-031. GitHub Issue: not
raised — owner action.*

**Problem ID**: PRB-032
**Reporter**: AI coding agent, while closing CAPA-003 (the two tests of `tests/security/` still failing on every GitHub
run, in the non-blocking step); branch `fix/capa-003-security-gate`, PR #80 (draft)
**Date**: 2026-11-11
**Version**: `main` @ `d5d4726` (pre-existing)
**Severity**: **Minor** (proposed). No effect on the deployed system today: the input-validation middleware bypasses
every path (recorded RMF open item, PRB-020 known issue) and no route calls the validators directly. Findings A and B
would have surfaced the moment the middleware was re-enabled or a validator was wired into a route.
**Status**: OPEN — DRAFT. A and B fixed on branch `fix/capa-003-security-gate` (not merged, not deployed); C open;
D unchanged (recorded elsewhere). *Owner approval pending — not signed.*

## 1. What happened

**A. The path validator depended on the host operating system.** `PathTraversalValidator` decided whether a path is
absolute with `os.path.isabs`. On Linux, which is what the server runs on, a Windows drive path
(`C:\Windows\System32\config\sam`), a drive-relative path (`C:name`), a UNC path (`\\server\share\x`), a device path
(`\\?\C:\...`) and a backslash-rooted path were all accepted. `TestPathTraversalProtection` therefore failed on every
GitHub run since the suite started executing, and passed on the developer's Windows laptop.

**B. Four audit event types never existed.** The validators reference `AuditEventType.SECURITY_INJECTION_ATTEMPT`,
`SECURITY_XSS_ATTEMPT`, `SECURITY_PATH_TRAVERSAL` and `SECURITY_INVALID_INPUT`, none of which was ever defined. Every
detection therefore raised `AttributeError` at argument evaluation, before writing its audit event and before raising
its `*Detected` exception. Had the middleware been enabled:
- a detected attack in a query parameter would have produced HTTP 500 instead of 400, with no security audit event;
- a header flagged as suspicious, which by design is logged and let through, would have failed the request instead;
- a detection in a JSON body would have been swallowed (see D).

The security tests hid the defect by replacing the enum with a `MagicMock`, with a comment saying the defect was
"reported separately". No such report existed. This is the failure mode CAPA-003 §6 warns about: a test changed to
pass, which discards the signal.

**C. Five detection gaps, documented as expected-failure tests.**

| # | Test | Gap |
|---|------|-----|
| C1 | `test_detect_nosql_injection` | The SQL validator has no NoSQL operator detection (`$ne`, `$gt`, `||`). |
| C2 | `test_detect_encoded_xss` | The XSS validator does not URL- or HTML-entity-decode before matching. |
| C3 | `test_reject_executable_disguised_as_dicom` | File-format detection falls back to the extension, so a PE executable renamed `.dcm` is accepted as DICOM. |
| C4 | `test_detect_eicar_test_file` | No antivirus signature: EICAR is rejected as an invalid format, not flagged as malicious. |
| C5 | `test_detect_executable_polyglot` | No embedded-executable signature, so a valid JPEG carrying a PE payload is accepted. |

**D. The middleware bypasses every path.** `'/'` is in its bypass list and the check is a prefix match. This is already
recorded: RMF residual-risk table, "Input-validation middleware (PRB-020 known issue)". Its precondition for
re-enabling is that the validators stop writing the typed value to the audit log, because a password containing a
listed keyword would be logged. In addition, `_validate_body` catches every exception, so a body detection never
blocks even when the validators work.

## 2. Fix (A, B) — branch `fix/capa-003-security-gate`

- **A.** The validator refuses absolute paths of both families on every host:
  - a leading `/` or `\` (POSIX-absolute, UNC, device and backslash-rooted paths);
  - a drive prefix `^[A-Za-z]:`, refused by design (a colon is illegal in a Windows file name and no storage path of
    this system starts with `<letter>:`).
  - The returned path is normalised with POSIX rules on every host.
  - Neither path refusal writes the raw value to the audit log, only the field, the pattern and the length, because a
    file name can carry patient identifiers (RMF precondition, D). The pattern branch logged it before.
- **B.** The four members are added to `AuditEventType`. The `MagicMock` replacement of the enum is removed from the
  security tests; only the logger is isolated.

## 3. Verification

- `tests/security/test_path_traversal_every_host.py`: 7 absolute payloads × 2 host path families are refused, and 4
  safe relative paths × 2 are accepted. Failing-first: 7 cases failed on the old code.
- `tests/security/test_validators_audit_events.py`:
  - every `AuditEventType.X` referenced anywhere in `app/` exists;
  - SQL, XSS, relative-traversal and Windows-absolute detections are audited with the right type, then raised;
  - the middleware still bypasses every path, pinned so that re-enabling it points to the RMF precondition.
  - Failing-first: collection error (`AttributeError`) on the old code.
- C1–C5 stay as **strict** expected-failure tests that cite this report: a fix makes them fail until the marker is
  removed.
- `tests/security/` now **gates** the build (CAPA-003 CA-3.3).

## 4. Open — owner decisions

1. **Severity.** Minor is proposed.
2. **C1–C5.** Fix them before any validator is wired into a route or the middleware is re-enabled, or accept them with
   a rationale. C3 bears on REQ-SEC-013 ("reject malformed files"). This report does **not** establish whether the
   upload paths in use reject such files by their own parsing; that is a separate check.
3. **D.** Keep the middleware off; this is the current, recorded state. Re-enabling it needs:
   - the RMF precondition;
   - a false-positive check on real queries, for example a surname with an apostrophe, which the SQL patterns match,
     while the application uses no SQL database;
   - a decision on whether body detections should block.
