# CAPA-015 — Audit Trail Not Durable; Session Not Continued (Hourly Forced Sign-In, Unsaved Work at Risk)

**CAPA ID**: CAPA-015
**Date Opened**: 2026-10-24 (DRAFT — opening, severity and actions **PENDING owner approval**)
**Source**: Code reading of 2026-10-24 (two defects reported to the AI coding agent), re-checked in the code of `main` @ `70cc5c7` on 2026-10-24 and reproduced by tests written before the fix (§5). Three further defects were found while verifying (§1, F6–F7).
**Severity**: **Critical** (proposed — QP-002 §5: regulatory non-compliance; SPR-001 §2: security impact). The audit trail required for medical-device traceability (IEC 81001-5-1 logging, ISO 27001 A.12.4, EU MDR Annex I §17.2/§17.4) and for GDPR accountability (Art. 5(2), Art. 30, Art. 32) was lost on every server restart. The device is not in clinical use, which lowers the probability of harm, not the class. **PENDING owner approval.**
**Owner**: *(to be assigned — a person; the AI coding agent cannot own a CAPA)*
**Status**: DRAFT. Corrections implemented on branch `fix/audit-trail-and-session-capa015` (draft PR). **Merge after CAPA-014** (parallel PR; it holds RC-064..066, REQ-SEC-021..023, SRS 1.11, RMF 1.13, TM 1.10). Nothing merged, nothing deployed. **Owner approval: PENDING owner approval.** Effectiveness is not verified.
**Identifiers**: RC-067, RC-068, RC-069; REQ-SEC-024, REQ-SEC-025, REQ-SEC-026; document versions **SRS 1.12, RMF 1.14, TM 1.11** (drafts).
**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: HAZ-010 (HAZ-001 for unsaved segmentation work) · REQ-SEC-003 · REQ-SEC-009 · REQ-SEC-012 · RC-017 · RC-036 · CAPA-009 · CAPA-014

---

## 1. Findings (code of `main` @ `70cc5c7`)

### F1 — The audit trail did not survive a restart
- `AuditLogger` appended to `logs/audit.log` on the container's disk (`backend/app/core/logging/audit.py` ~231, ~272).
- `GET /auth/audit-logs` returned an in-memory list (`backend/app/security/auth.py` ~104, ~704).
- The Firestore collection `audit_logs` was declared (`backend/app/core/firebase.py` ~103–111) and protected in `firestore.rules`, but **nothing wrote to it**.
- Cloud Run runs 0–5 instances and scales to zero (`cloudbuild.yaml`); the disk is per-instance memory. Every restart, redeploy or scale-in erased "who did what". On Cloud Run the growing file also consumed instance memory.

### F2 — Most security and clinical events never reached the audit logger
- The password-login route (`authentication.py`) wrote only to the operational logger; failed logins, lock-outs and successful logins were not audit records. The middleware could not name the actor (`request.state.user` was never set).
- **Segmentation save/confirm, AI report generation and longitudinal decisions produced no audit event at all.** The request that opened this CAPA assumed they were "already emitted by the audit logger"; they were not.
- The middleware copied the **query string** into audit records — `GET /auth/me?token=…` (accepted by the route) would have written an access token into the trail.
- `event_id` was a 16-hex hash of the clock and `id(object())` (collisions possible); the request id was the millisecond clock (shared by concurrent requests).

### F3 — The audit trail was readable by radiologists
`/auth/audit-logs` required `AUDIT_VIEW`, which the role map also grants to radiologists.

### F4 — No session continuation: forced sign-in every hour
- The frontend posted a `refresh_token` from `localStorage` (never stored) to `/auth/refresh` (`frontend/src/services/apiClient.ts` ~42) — **no such route existed**.
- Login issued one access token of 60 minutes (`authentication.py` ~486; `config.py:25`).

### F5 — Unsaved segmentation work could be lost when the session ended
- After 60 minutes every request failed with 401. Saving a segmentation failed; the mask stayed in memory but could not be saved, and the only way forward — signing in again — left the viewer and discarded it.
- Any 401 seen by the global axios instance (`AuthContext.tsx`) cleared the session and set `window.location.href = '/login'` at once (the browser's "leave page?" prompt could appear; confirming it lost the work).
- The frontend never told the server about a logout.

### F6 — Found while verifying: a password change did not take effect at login; logout revocation was ineffective
- `AuthService.change_password` updated one process's memory only; the login route reads the persistent user store. **The old password kept working and the new one was refused**; a user created after start-up got 404.
- `auth.py` built its own `TokenManager`; logout revoked the token in that instance's list, which the authentication dependency (`get_token_manager()`) never consulted.

### F7 — Found while testing: the test suite reached the real Firestore
On a developer machine with gcloud application-default credentials, importing the app made the user store list the real Firestore collection (billing the credentials' quota project — here a different product's project). The suite had to be isolated before any audit or session test could run safely (§3, CA-15.9).

## 2. Root cause

1. **Deployment change without re-assessment.** The audit logger was written for a single long-lived server with a persistent disk. When the backend moved to Cloud Run (stateless, scale to zero) nothing classified what the process kept on disk or in memory as *cache* or *record*. The durable collection was declared in anticipation; its write path was never built, and no test checked durability.
2. **Coverage assumed, not verified.** "All endpoints include audit logging" (module docstrings) was taken as true; handlers wrote to the operational logger, which is not the audit trail. No test asked "after this action, is there a record?".
3. **A contract with one side only.** The refresh flow existed in the frontend but not in the backend; no end-to-end test expired a session. Error handling chose the simplest reaction (redirect to login) without considering clinical work held in memory.

## 3. Corrections and corrective actions (implemented on the branch — PENDING owner approval)

| ID | Action | Control |
|----|--------|---------|
| CA-15.1 | Durable sink: every record goes (1) at once to stdout as one structured JSON line (Cloud Logging) and (2) to a bounded queue written by background threads to Firestore `audit_logs` with `document(event_id).create()` — append-only, server commit time (`SERVER_TIMESTAMP`). Failures retried with exponential back-off and logged as `AUDIT_SINK_WRITE_FAILED`; overflow or exhausted retries logged in full as `AUDIT_RECORD_DROPPED`. The request is never blocked: the middleware waits at most `AUDIT_FLUSH_WAIT_MS` (500 ms) for the request's own records, and only while the sink is healthy (Cloud Run throttles CPU between requests); queued records are flushed at shutdown. | RC-067 |
| CA-15.2 | Allow-listed record (schema v1): event id (UUID), type, severity, outcome, action, actor id / username / role, IP, user agent, request id, trace id, method, **route template** (never the concrete path or query string), status code, resource ids, reason code, short coded details. No description text, no request body, no image data; file names and identifiers typed at a failed login reduced to a SHA-256 prefix. | RC-067 |
| CA-15.3 | One record per API request (actor read from the bearer token); clinical actions mapped by route: segmentation create / save (incl. binary mask upload) / modify / delete / AI-review confirm, lesion readings, **longitudinal decisions** (with both segmentation ids), **AI report generation** (template, language), AI and clinical-tool runs, DICOM-SEG export, care-team changes. Reads of patient data recorded durably once per actor, route and resource per 5 minutes per instance (every read stays on stdout). Authentication writes explicit records: login success; failure with a reason code (`user_not_found`, `invalid_password`, `captcha_required`, `account_locked`, …); lock-out; passkey login; refresh; refresh-token reuse; logout; password change and the sessions it revoked; admin user changes (fields changed, new role); reading the trail. | RC-067 |
| CA-15.4 | `GET /auth/audit-logs` reads Firestore, newest first, cursor pagination (`page_token`), filters by actor / event type / outcome, **administrators only**, returns the sink status. `GET /auth/audit-status` (administrators only). A red banner shows administrators when writing fails (`AuditStatusBanner`). | RC-067 |
| CA-15.5 | Refresh tokens: 15-minute access token; opaque refresh token (384 random bits), **only its SHA-256 stored** (Firestore `refresh_tokens`), grouped per sign-in in a family (`refresh_token_families`); rotation on every use in **one Firestore transaction**; a reused token **revokes the family** and is audited; idle expiry 30 min, absolute expiry 12 h (decision D-2); revoked on logout, on password change (all families of the user) and at refresh time when the account is missing, inactive or locked; the new access token carries the role stored now. | RC-068 |
| CA-15.6 | Cookie transport: `__session` cookie, `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`, responses `Cache-Control: no-store`. Refresh refuses a foreign `Origin`. See "Why a cookie is possible" below. | RC-068 |
| CA-15.7 | Frontend: silent refresh two minutes before expiry; one refresh shared by concurrent requests (and by tabs, Web Locks API); on 401 one refresh and a retry; when the session cannot continue, **the page and its unsaved work stay**, the re-login dialog opens (password, passkey or CAPTCHA), **only the same user** is accepted (another person's new session is closed at once), and the refused requests are retried after sign-in. No hard redirect on 401. Logout tells the server. Volume and export downloads use the same recovery. | RC-069 |
| CA-15.8 | Password change persisted to the user store (old password refused, new accepted at login). Logout revokes in the token manager the authentication dependency checks. | RC-068 |
| CA-15.9 | Test isolation: `backend/tests/conftest.py` points `GOOGLE_APPLICATION_CREDENTIALS` at a file that does not exist and selects the in-memory audit and refresh stores; the CAPA-015 scripts do the same. | (verification integrity) |

### Why a cookie is possible (and how)
The API answers at `brain-mri-…-uc.a.run.app`; the app at `app.mstool-ai.com` / `brain-mri-476110.web.app`. `run.app` is on the Public Suffix List, so the API is a **different site**: a `SameSite=Strict` cookie set by it would never be sent by the app, and a `SameSite=None` third-party cookie is blocked by Safari (and by Chrome/Firefox under tracking protection) and would give up the cross-site protection. The auth routes are therefore served **on the app's own origin**: `firebase.json` rewrites `/api/v1/auth/**` to the Cloud Run service `brain-mri` (same project, `us-central1`). Firebase Hosting forwards only a cookie named `__session` — hence the name. All other API calls keep going directly to Cloud Run with the bearer token (Hosting rewrites have a 60-second limit, unsuitable for uploads and AI runs). In development the Vite proxy (`/api` → `localhost:8000`) and in the Docker deployment nginx (`/api` → backend) give the same origin. **Deployment order: backend first, then hosting** (decision D-4).

### What changes for users and administrators
- Users stay signed in while they work (a fresh sign-in at most once per 12-hour shift); after 30 minutes away with the tab closed they must sign in again. The 15-minute inactivity log-off is unchanged.
- If the session ends while a segmentation is unsaved, a dialog asks the same user to sign in again; the work is kept and the save that was waiting completes.
- Administrators can read the audit trail (paginated) and see a red banner when audit writing fails. Radiologists can no longer read it.
- A password change signs the user out everywhere and the new password works at once.

## 4. Preventive actions (proposed — PENDING owner approval)

| ID | Action |
|----|--------|
| PA-15.1 | Add to the Software Development Plan / deployment checklist: any state a service keeps on local disk or in memory is classified as cache or record; records go to a durable store and are bound to a durability test. |
| PA-15.2 | Log-based alert (Cloud Monitoring) on `AUDIT_SINK_WRITE_FAILED`, `AUDIT_RECORD_DROPPED`, `REFRESH_STORE_UNAVAILABLE` and `auth.token.reuse_detected` (decision D-7; no cloud command was run). |
| PA-15.3 | Firestore TTL policies: `refresh_tokens.expires_at`, `refresh_token_families.absolute_expires_at` (+ 30 days); retention for `audit_logs` per decision D-3 (requires a `retain_until` field — small follow-up change). |
| PA-15.4 | End-to-end session test in a real browser against a deployed preview (cookie through the Hosting rewrite, two tabs, laptop sleep). |

### Retention (proposal — decision D-3)
| Store | Content | Proposed retention | Basis |
|-------|---------|--------------------|-------|
| Firestore `audit_logs` | staff identity, role, IP, user agent, pseudonymous resource ids; no patient names, no image data | **6 years** from the event, then deleted by TTL; IP address and user agent could be removed after 12 months (minimisation) | HIPAA §164.316(b)(2) six-year documentation retention as a reference point; long enough for complaint, vigilance and post-market investigations; GDPR Art. 5(1)(e) limits it to what accountability needs |
| Cloud Logging (stdout copy) | the same records | 30 days (default `_Default` bucket); optionally a dedicated bucket for `labels.audit="true"` with 400 days | backup copy while Firestore is unavailable |
| `refresh_tokens` / families | token hashes, user id, times | until expiry + 1 day / + 30 days | needed only to detect reuse |

## 5. Verification (by the author — not independent; **PENDING owner approval**)

**Tests written before the fix, failing on `main`.** Commit `ecbcdad` (tests only, on top of `70cc5c7`): `backend/tests/unit/test_capa015_audit_and_session.py` (29 cases, `test_rc067_*`, `test_rc068_*`) and `frontend/src/services/session.capa015.test.tsx` (`rc069 …`, `rc067 …`). On `70cc5c7` **backend 29 of 29 fail** for the behaviour they check (no record in `audit_logs`, no refresh cookie, `/auth/refresh` 404, `expires_in` 3600, password change 404 "User not found", radiologist reads the trail) and **frontend 10 of 10 fail**. Two frontend cases were added later and also fail on the base: `fetch`-based downloads (added during implementation, with one assertion that the dialog names the unsaved segmentation) and "no English phrase left in the Spanish or German texts" (added after the first negative-control run, below). Re-run of the final test files against the base by `scripts/safety/capa015_tests_on_base.py` → `docs/iec62304/records/risk_verification/CAPA-015_tests_on_base_2026-10-24.json`: **backend 29 of 29 fail, frontend 12 of 12 fail**.

**After the fix.** Both files pass (29/29, 12/12). Whole backend tree (`pytest tests`, no cloud credentials): **1725 passed, 20 skipped, 5 xfailed, 1 failed** — `tests/integration/test_auth_endpoints.py::TestWebAuthnEndpoints::test_webauthn_credentials_endpoint_exists`, because `webauthn` is not installed in the local environment (fails identically on `main`). Frontend (vitest `--pool=threads`, final tests): 40 files, 346 tests — 343 passed, 3 skipped (FLAMeS tests needing local research data), 0 failed. Type check (`tsc --noEmit`) clean; production build (`vite build`) passes. Existing test changed: `test_capa009_*` classifies `/auth/audit-logs` as administrator-only.

**Negative controls.** `scripts/safety/capa015_negative_controls.py` — 61 mutations, one at a time in the real source, anchors asserted unique, bytes restored, no cloud credentials. The first full run detected **60 of 61**: F18 (the German dialog text translated only in part) passed, because the language test compared whole strings. The test now refuses any English three-word phrase in the Spanish and German texts, and the script now reads pytest's summary line (it had counted "1 error" in captured log lines as test errors). Second full run (2026-10-24, against the final tests): **61 mutations, 61 detected** — RC-067: B1–B25, F15–F16; RC-068: S1–S18; RC-069: F1–F14, F17–F18 — and the bound tests green after the byte-exact restore (backend 29/29, frontend 12/12). Record: `docs/iec62304/records/risk_verification/CAPA-015_negative_controls_2026-10-24.json` (each mutation with its execution time and the SHA-256 of the tests it ran).

**Not verified.** No run against a real Firestore or the emulator (an in-memory stand-in implements the calls used, including transactions); no real browser (jsdom); the Firebase Hosting rewrite, the `__session` cookie through it and Cloud Run CPU throttling were not exercised in a deployed environment; Web Locks across tabs not tested; no usability evaluation (IEC 62366).

## 6. Class C modules

None of the Class C modules listed in `CLAUDE.md` is modified. Security-relevant modules changed (code review required before merge): `core/logging/audit.py`, `audit_middleware.py`, `audit_sink.py` (new), `security/refresh_tokens.py` (new), `security/auth.py`, `api/routes/auth.py`, `api/routes/authentication.py`, `core/config.py`, `frontend/src/services/session.ts` (new), `contexts/AuthContext.tsx`, `services/apiClient.ts`, `firebase.json`, `firestore.rules`, `firestore.indexes.json`.

## 7. Residual risk and open items

- The audit-store status is per server instance; the banner samples whichever instance answers.
- Records still queued when an instance is killed without its shutdown flush are lost from Firestore; each record was already written to stdout (Cloud Logging, 30 days by default).
- Reads are deduplicated per instance (5 minutes): several instances may each write one record for the same read.
- AI report records carry no patient identifier: the request carries none by design (REQ-SEC-007).
- The 15-minute inactivity log-off still discards unsaved work (existing HIPAA control, unchanged) — decision D-5.
- Access-token revocation remains in per-instance memory; with 15-minute tokens a revoked token can work for at most 15 minutes on another instance.
- Two tabs refreshing at the same instant in a browser without the Web Locks API, or a refresh response lost in the network, look like reuse: the family is revoked and the user signs in again (no work lost).
- If Firestore is unreachable a refresh fails closed (re-login dialog); sign-in still works.
- Pre-existing, not changed: the first `X-Forwarded-For` hop is client-controlled (recorded IP and rate limiting); the exception handler drops `HTTPException` headers (`X-CAPTCHA-Required`; the frontend relies on the message). The assistant's `API_SERVICE_TOKEN` (a clinician's access token) now lasts 15 minutes instead of 60.
- The role map still lists `AUDIT_VIEW` for radiologists (now unused by the audit endpoints) — decision D-6.

## 8. Owner decisions (all **PENDING owner approval**)

| ID | Decision | Proposal |
|----|----------|----------|
| D-1 | Severity | Critical (regulatory non-compliance) |
| D-2 | Session lifetimes | Access 15 min; refresh idle **30 min**, absolute **12 h** — instead of the suggested 12 h idle / 7 d absolute, which would let anyone opening a shared clinical workstation hours later continue the previous user's session and so weaken the existing 15-minute automatic log-off. Configurable: `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_IDLE_MINUTES`, `REFRESH_TOKEN_ABSOLUTE_HOURS`. |
| D-3 | Audit retention | §4 table (6 years Firestore; Cloud Logging copy 30 days or a 400-day bucket) |
| D-4 | Firebase Hosting rewrite of `/api/v1/auth/**` to Cloud Run | Accept; deploy backend first, then hosting. Without it the refresh cookie cannot work and users are asked to sign in again when the access token expires (no work lost). |
| D-5 | Inactivity log-off discards unsaved work | Consider a lock screen that hides patient data but keeps the work (separate change) |
| D-6 | Radiologists' `AUDIT_VIEW` | Remove from the role map or define a restricted view |
| D-7 | Alerting | PA-15.2 |

## 9. Approvals

| Role | Name | Decision | Date |
|------|------|----------|------|
| CAPA owner | PENDING owner approval | PENDING owner approval | PENDING owner approval |
| Severity (D-1) | PENDING owner approval | PENDING owner approval | PENDING owner approval |
| Corrective actions CA-15.1–15.9 | PENDING owner approval | PENDING owner approval | PENDING owner approval |
| Preventive actions PA-15.1–15.4 | PENDING owner approval | PENDING owner approval | PENDING owner approval |
| Decisions D-2–D-7 | PENDING owner approval | PENDING owner approval | PENDING owner approval |
| Code review (security modules, CLAUDE.md) | PENDING owner approval | PENDING owner approval | PENDING owner approval |
| Effectiveness verification | PENDING owner approval | PENDING owner approval | PENDING owner approval |
