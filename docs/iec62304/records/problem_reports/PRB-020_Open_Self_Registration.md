# PRB-020 — Anyone Can Create an Account (Open Self-Registration)

*Software problem report per SPR-001 (`docs/iec62304/08_Problem_Resolution_Procedure.md` §1), following PRB-001's
layout. Kept under `docs/iec62304/records/problem_reports/`. A GitHub Issue citing this ID is to be raised by the
owner; the agent did not raise one.*

*Numbering: PRB-004 to PRB-009 are in use by the concurrent display-findings work (uncommitted worktree
`viewer-display-prb004`, 2026-10-28); PRB-010 to PRB-019 are left free for it. This branch uses PRB-020 to PRB-026.*

**Problem ID**: PRB-020 (GitHub Issue: not raised — owner action)
**Reporter**: browser capture of the release candidate (`release/owner-signoff-2026-10-25` @ `6d1fde2`, 2026-10-28,
`mstool-film/assets/app-captures/CAPTURES.md` §5 finding F21) and a marketing study that named it the largest EU MDR
risk; reproduced on `main` and record drafted by the AI coding agent
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7` (also present on the release branch)
**Severity**: **Critical** (proposed; security and regulatory — together with PRB-021 it gives anyone on the internet the
patient registry). **PENDING owner approval.**
**Status**: OPEN — DRAFT. Fix implemented on branch `fix/platform-security-findings-prb020` (draft PR, not merged,
not deployed). No Class C module changed. **PENDING owner approval and code review.**

**Description**: The sign-in page offers a "Register" tab to anyone; `POST /api/v1/auth/register` is public and creates
a VIEWER account for anyone who can reach the server. There is no e-mail verification (the field `email_verified` is
written `False` and never read; the response nevertheless said "Please verify your email to activate your account").
A VIEWER holds `PATIENT_VIEW`, which — because of PRB-021 — was enough to list every patient's name, record number,
birth date and sex. For a device that is not CE-marked, offering it to any clinician who signs up, even free of
charge, can count as "making available on the market" (EU MDR art. 2(27); placing on the market / putting into
service, art. 5 and art. 6 for devices offered at a distance).

**Steps to Reproduce** (each reproduced by a failing-first test, §6):
1. Without any token, `POST /api/v1/auth/register` with a username, e-mail, full name and a password meeting the
   policy (`authentication.py:143-287`).
2. The account is stored (`authentication.py:269`) with role VIEWER (`:255`); sign-in works at once.
3. On the sign-in page, the "Register" tab (`LoginPage.tsx:197`) opens the form (`:304-386`, `handleRegister` `:125`).

**Expected Behavior**: Accounts are created by an administrator, with the role the administrator chooses.
Self-registration exists only behind an explicit setting that is off by default and can never be on in production;
when it is off the route does not exist (404) and the sign-in page neither shows the tab nor implies it exists.

**Actual Behavior** (`main` @ `70cc5c7`): as in the steps; mounted at `main.py:272`; VIEWER permissions
`rbac.py:42-47`; no administrator route existed to create an account (`POST /auth/users` answered 405), so the only way
to get an account was to self-register and have an administrator change the role (which itself failed, PRB-024).

**Safety Impact Assessment**:
- [x] Could contribute to a hazardous situation — **HAZ-010** (unauthorized access): anyone becomes a user; with
  PRB-021, anyone reads the patient registry. Use by persons outside the intended users (RMF §2.2) is a reasonably
  foreseeable misuse added to RMF §2.5.
- [ ] Affects a Class C software item — no (authentication routes, Class B per the master document).
- [ ] Requires regulatory notification (EU MDR art. 87) — not for this report (no incident known). **Whether patient
  data were read by self-registered accounts in production is unknown** (production was not contacted); see §7.

## 1. Triage (SPR-001 §3.1)
- **Reproducible**: yes, by request (tests in §6: backend 9 of 10, frontend 3 of 4 fail on `70cc5c7`).
- **Severity**: proposed Critical (§5). **Assigned to**: *(owner decision)*.

## 2. Root Cause (SPR-001 §3.2)
Registration was built as a convenience of an early prototype and never re-examined when the intended users
(RMF §2.2: board-certified neuroradiologists and neurologists with product training, IT administrators) were written
down. No requirement said who may create an account; REQ-SEC-002 ("authentication for all non-public endpoints")
treated registration as a legitimate public endpoint. No administrator path to create accounts existed, so disabling
registration was never possible without breaking access.

## 3. Fix (on branch; PENDING owner approval)
- `backend/app/core/config.py`: `SELF_REGISTRATION_ENABLED` (default **False**).
- `backend/app/security/registration_policy.py` (new): self-registration is on only when the setting is true **and**
  `ENVIRONMENT` is not `production` (a production server ignores the setting and logs a warning); `async` dependency
  `require_self_registration_enabled` answers 404 before the body is used; `registration_status()`.
- `backend/app/api/routes/authentication.py`: the register route depends on it; the response no longer promises an
  e-mail verification that does not exist (PRB-022).
- `backend/app/api/routes/auth.py`: `GET /api/v1/auth/registration` (public; `{"self_registration_enabled", 
  "account_creation"}`) and `POST /api/v1/auth/users` (administrator only, `USER_CREATE`): creates an account with its
  role through `AuthService.register_user`, records `created_by`, checks duplicates against the persistent store
  (PRB-024), password policy unchanged (REQ-SEC-011), password stored only as an Argon2id hash.
- `frontend/src/services/registrationPolicy.ts` (new) and `frontend/src/pages/LoginPage.tsx`: the Register tab and form
  exist only when the server answers exactly `self_registration_enabled: true`; any error or other answer hides them
  (fail closed); otherwise the page says "Accounts are created by an administrator. Contact your administrator for
  access." (en/es/de).
- Requirements: REQ-SEC-030, REQ-SEC-031, REQ-REG-010 (SRS-001 1.16 draft). Risk control: **RC-080**, **RC-081**
  (RMF-001 1.18 draft, HAZ-010).

## 4. What the fix does not do
- **Existing self-registered accounts in production are untouched.** Production was not contacted. They keep working
  (with the VIEWER role) until an administrator reviews them (§7).
- There is no administrator page to create or manage accounts; the administrator uses the API
  (`POST/GET/PATCH/DELETE /api/v1/auth/users`). A user-management page is a separate change (owner decision).
- No e-mail verification, invitation link or password-reset flow exists; an administrator sets the first password and
  must hand it over through a separate channel. The password-expiry and change-password flows are unchanged.
- The setting is read per request; turning self-registration on outside production (for a local demo, a test system)
  needs `SELF_REGISTRATION_ENABLED=true` and `ENVIRONMENT` other than `production`.

## 5. Severity Rationale (SPR-001 §2)
Proposed **Critical**: the problem opens the device to unidentified users (HAZ-010) and, with PRB-021, to the patient
registry; it is also the main regulatory risk named for a device without CE marking. It has no workaround in the
product (no other account-creation path existed). **PENDING owner approval.**

## 6. Verification
- Failing-first tests (written before the fix, run on `main` @ `70cc5c7` by `scripts/safety/prb020_tests_on_base.py`,
  record `records/risk_verification/PRB-020_tests_on_base_2026-10-28.json`):
  `backend/tests/unit/test_prb020_self_registration_and_accounts.py` — `test_rc080_prb020_*` (5), `test_rc081_prb020_*`
  (3, one with 3 roles); `frontend/src/pages/LoginPage.prb020.test.tsx` — `rc080 prb020 *` (4).
  On the base: every RC-080/RC-081 test fails except two positive controls (registration works when explicitly enabled
  outside production; the Register tab shows when the server says it is on).
- Negative controls: `scripts/safety/prb020_negative_controls.py`, mutations R1–R6 and F1–F3 (record
  `records/risk_verification/PRB-020_negative_controls_2026-10-28.json`): first run 56 of 56 detected; re-run after the independent review of PR #70 with 33 more mutations, 89 of 89 detected (the record now holds the re-run); RC-080 8 of 8, RC-081 8 of 8.
- Whole suites after the fix: backend 1 failure (the local-only WebAuthn test, `webauthn` not installed — as on every
  earlier PR); frontend all pass; `tsc --noEmit` clean; `vite build` passes.

## 7. Owner decisions and actions (PENDING)
1. **Decision recorded for approval**: self-registration is off by default and never on in production; accounts are
   created by an administrator. Turning it on for any production use requires a code change, a code review and the
   owner's regulatory decision (EU MDR "making available").
2. **Production review (owner only; production was not contacted)**: list the accounts in production (`GET
   /api/v1/auth/users` as administrator) and deactivate or delete every account that was self-registered and is not a
   known, intended user. Note PRB-002: 62 test accounts were written into production by local test runs.
3. **Data-protection assessment (owner / data-protection officer)**: with PRB-021, any self-registered account could
   list the patient registry. Whether that happened can be established only from production access logs (requests
   to `GET /api/v1/patients` and `/patients/search` by VIEWER accounts). The owner decides whether a GDPR art. 33
   assessment is needed.
4. Severity Critical (proposed); whether a CAPA is opened for the account-lifecycle controls (proposed: yes — no
   invitation flow, no e-mail verification, role changes take effect only at the next sign-in because the access token
   carries the role).

## Review of PR #70 (2026-10-28) *(review of PR #70, 2026-10-28 — DRAFT, PENDING owner approval)*

- **m4 — production detection fails closed**: self-registration was refused only when `ENVIRONMENT` was exactly
  "production"; a production service configured as "prod", "staging", "live" or with an empty value would have opened it
  when the setting was on. Now it can be on only when `ENVIRONMENT` is one of `development`, `local`, `test`, `testing`;
  any other value counts as production (`registration_policy.NON_PRODUCTION_ENVIRONMENTS`). Tests
  `test_rc080_prb020_r1_*` (10 cases; "prod", "staging", "", "live" fail at `7de9334`; "Production " and "PRODUCTION" were
  already refused and are positive controls, as are the four named non-production values). Negative controls R2
  (re-anchored), V20.
- **m1 — audit of administrator-created accounts**: the security event of `POST /auth/users` named the new account as actor
  and `/auth/register` as route. It now names the acting administrator and `/auth/users`, with the new account as target,
  and creating an administrator account adds a second event `privileged_account_created`. Test
  `test_rc081_prb020_r1_audit_of_an_admin_created_account_names_the_administrator` (fails at `7de9334`); negative controls
  V12–V14. (Merge note: CAPA-015, PR #65, maps audit actions to event types; `privileged_account_created` needs an entry
  there at integration.)
- **Found while testing m8 — a refused password answered 500 and was logged as typed**: for a password refused by the
  account model's validator (no capital, no digit, no special character), the validation-error handler failed (the error's
  context holds the Python exception, which is not JSON) and the administrator got a 500 instead of the reason; and every
  validation error, the typed password included, was written to the log with its `input`. Validation errors are now
  reduced to location, message and type; context values become text; the submitted value is neither returned nor logged
  (`core/exception_handlers.py`). Test `test_rc081_prb020_r1_administrator_route_applies_the_password_policy` (4 cases:
  400 with the reason, the password in neither the response nor the log; 3 of 4 fail at `7de9334` with the 500, the fourth
  — too short — returned the password in the response). Negative controls V21, V22. Earlier logs may contain passwords
  typed into refused registrations or account creations (production logs were not read) — owner action in §7.
- Additional owner action (§7, item 5): if production logs are kept, check whether "Request validation failed" entries
  hold `input` values of password fields and restrict or delete them.
Records: `records/risk_verification/PRB-020_review1_tests_on_7de9334_2026-10-28.json`, `records/risk_verification/PRB-020_negative_controls_2026-10-28.json`.
