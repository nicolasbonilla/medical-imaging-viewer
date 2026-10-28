# PRB-024 — Accounts Created After Start-Up Are Invisible to the Administrator Until a Restart

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: see PRB-020. GitHub Issue: not raised.*

**Problem ID**: PRB-024
**Reporter**: browser capture of the release candidate, 2026-10-28 (F17; `logs/backend/seed.log`); reproduced on `main`
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`. Also on the release branch: CAPA-015 (PR #65) made the password change read the store
but left the administrator routes on the memory copy
**Severity**: **Major** (proposed; the administrator cannot see, change, deactivate or delete an account until a
restart — a self-registered account cannot be disabled; HAZ-010). **PENDING owner approval.**
**Status**: OPEN — DRAFT. Fix on branch `fix/platform-security-findings-prb020`.

**Description**: `AuthService` (`security/auth.py`) copies every account from the persistent user store into memory once,
at start-up (`_load_users_from_storage`). The administrator routes read only that copy: `GET /auth/users` →
`list_users` (`auth.py:591-600`, `return list(self._users.values())`), `GET/PATCH/DELETE /auth/users/{id}` →
`get_user_by_id` (`:602-604`), `update_user` / `delete_user` (`:606-641`, `ValueError` for an unknown id → the route
answers **500** "Failed to update user", `routes/auth.py:619`). The register route and the login route write to the
store directly (`authentication.py:269`, `:458`, `:483`), and Cloud Run runs several instances: an account created
after start-up, or on another instance, is unknown to the administrator until that instance restarts; an account
deleted elsewhere is still listed. `register_user` checked duplicates only in memory, so a name another instance had
stored could be created twice; an account the store failed to take was kept "in memory" and reported as created.

**Fix** (on branch, `security/auth.py`): `list_users` and `get_user_by_id` read the persistent store (the source of
truth) and refresh or drop the memory copies; `update_user` / `delete_user` use them (the routes answer 404 for an
unknown account instead of 500); `register_user` checks duplicate usernames and e-mails in the store and fails with 503
when the account cannot be stored (nothing kept in memory); `AuthService.login` (used by tests and the start-up path,
not by the login route) stores the lockout counters, never with an empty password hash (found by a review of this
change: the first version could have written an empty hash). Requirement **REQ-SEC-034**; risk control **RC-084**.

**Verification**: `test_prb020_self_registration_and_accounts.py` — `test_rc084_prb024_*` (5): an account registered
after start-up is listed; its role can be read and changed (password kept); an account the store did not take is not
created (503); a failed sign-in is stored and the password hash kept; an account deleted elsewhere is no longer
listed and answers 404. All fail on `70cc5c7`. Also `tests/security/test_authentication.py::TestAccountLockout` (3,
existing) — they failed after the first version of the fix (lockout kept only in memory) and pass now. Negative controls
S1–S6.

**What the fix does not do**: the role and the active flag are carried in the access token (`get_current_user` builds the
user from the token), so a role change or a deactivation takes effect at the next sign-in or token renewal, not at once.
That is a separate access-control gap (proposed for the CAPA of PRB-020 §7 item 4; CAPA-015's refresh-token checks on
the release branch read the store at renewal).

**Owner decisions (PENDING)**: severity Major; the token gap above (proposed: a CAPA action — check the account in the
store on each request, or a short token lifetime as CAPA-015 sets).

## Review of PR #70 (2026-10-28) *(review of PR #70, 2026-10-28 — DRAFT, PENDING owner approval)*

- **m2**: the administrator `PATCH /auth/users/{id}` (which this fix made work for accounts created after start-up) and
  the passkey sign-in (`webauthn/login/complete`) saved the profile with `password_hash=''` when the password data could not
  be read — the user could no longer sign in with a password — and always erased the password history (the 5-password
  reuse rule restarted after any role change). Now every profile save goes through
  `AuthService.save_profile_keeping_password`: the stored hash and history are written back unchanged (the store first —
  another instance may have changed the password — this process's copy only when the store has none); with no known hash
  nothing is written (PATCH → 503, nothing changed; passkey sign-in → a warning, sign-in still succeeds). The lockout path
  (`_persist_login_state`) uses the same rule.
- **m3**: deleting an account answered 204 when the store had not deleted it (the account could still sign in); now 503
  and the account stays listed.
Tests: `test_rc084_prb024_r1_*` (5 cases) in `backend/tests/unit/test_prb020_review1_findings.py`; all fail at `7de9334`
(`records/risk_verification/PRB-020_review1_tests_on_7de9334_2026-10-28.json`). Negative controls S6 (re-anchored), V15–V19 (`records/risk_verification/PRB-020_negative_controls_2026-10-28.json`).

## Re-review of PR #70 (2026-10-28) *(re-review of PR #70, 2026-10-28 — DRAFT, PENDING owner approval)*

- **R6**: a profile save fell back to this process's password hash when the store gave none; that copy may be older than a
  password changed on another instance, and writing it back would undo the change. The password is now read from the store
  only; if the store gives none (its reader swallows errors, so "unreadable" and "no data" look the same) the save is
  refused (PATCH → 503, nothing changed). A password-read error while refreshing the cache no longer turns the PATCH into
  a 500. Tests `test_rc084_prb024_r2_profile_save_never_uses_the_remembered_hash[error|nothing]` (fail at `570d78f`,
  `records/risk_verification/PRB-020_review2_tests_on_570d78f_2026-10-28.json`); control W9.
- **R4**: a refused new password on `POST /auth/change-password` answered 500 and was logged as typed until the first
  review's handler fix; regression test `test_rc084_prb024_r2_a_refused_new_password_leaks_nothing` (fails at `7de9334`,
  `records/risk_verification/PRB-020_review2_tests_on_7de9334_2026-10-28.json`).
