"""Negative controls for CAPA-015 — durable audit trail and session continuation
(RC-067, RC-068, RC-069; HAZ-010, HAZ-001).

Each mutation re-introduces ONE defect CAPA-015 removed (the audit record kept only on the
instance's disk/memory, an overwrite instead of an append, a silent or unretried write failure,
free text in the record, an unaudited login or clinical action; no refresh cookie, a readable or
cross-site cookie, a raw token stored, no rotation, no reuse revocation, no expiry, no revocation
on logout or password change, a password change that does not reach the login; a hard redirect
on 401, a refresh to the wrong origin, a lost waiting request, another user accepted in the
re-login dialog, ...) or removes one sub-control it added — in the real source, one at a time.
The script asserts every anchor occurs exactly once (the sabotage really was applied), runs the
bound tests of the side it mutated (backend: pytest; frontend: vitest, JSON reporter), records the
failing test names and restores the exact original bytes.

Run from the repository root (needs backend/venv — or BACKEND_PYTHON — with the backend
requirements, and frontend/node_modules). No cloud service is contacted: the backend runs with
GOOGLE_APPLICATION_CREDENTIALS pointing at a file that does not exist.
    python scripts/safety/capa015_negative_controls.py            # every mutation
    python scripts/safety/capa015_negative_controls.py --only S   # re-run mutations starting with S
    python scripts/safety/capa015_negative_controls.py --check    # only assert the anchors
Output: docs/iec62304/records/risk_verification/CAPA-015_negative_controls_2026-10-24.json
NEVER run this while anything else edits the files it mutates (it restores a snapshot).
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
PY = os.environ.get("BACKEND_PYTHON") or os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = "docs/iec62304/records/risk_verification/CAPA-015_negative_controls_2026-10-24.json"
BACKEND_TESTS = ["tests/unit/test_capa015_audit_and_session.py", "tests/unit/test_capa015_review_fixes.py",
                 "tests/unit/test_capa015_review2_fixes.py"]
FRONTEND_TESTS = ["src/services/session.capa015.test.tsx", "src/services/session.capa015.review.test.tsx",
                  "src/services/session.capa015.review2.test.tsx"]
# PRB-002: no cloud credentials, an empty gcloud configuration and a project that does not exist.
_EMPTY_GCLOUD = os.path.join(tempfile.gettempdir(), "capa015-empty-gcloud-config")
os.makedirs(_EMPTY_GCLOUD, exist_ok=True)
NO_CLOUD = {"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(tempfile.gettempdir(), "capa015-no-cloud-credentials.json"),
            "CLOUDSDK_CONFIG": _EMPTY_GCLOUD, "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests",
            "AUDIT_SINK_BACKEND": "memory", "REFRESH_TOKEN_BACKEND": "memory"}

AUD = "backend/app/core/logging/audit.py"
SINK = "backend/app/core/logging/audit_sink.py"
MW = "backend/app/core/logging/audit_middleware.py"
AUTHN = "backend/app/api/routes/authentication.py"
AUTHR = "backend/app/api/routes/auth.py"
SVC = "backend/app/security/auth.py"
RT = "backend/app/security/refresh_tokens.py"
CFG = "backend/app/core/config.py"
RULES = "firestore.rules"
CIP = "backend/app/core/client_ip.py"
USTORE = "backend/app/security/user_storage.py"
CONFTEST = "backend/tests/conftest.py"
GEN = "backend/scripts/generate_secrets.py"
HOOK = "frontend/src/hooks/useSessionTimeout.ts"
SESS = "frontend/src/services/session.ts"
CTX = "frontend/src/contexts/AuthContext.tsx"
DLG = "frontend/src/components/SessionExpiredDialog.tsx"
V3D = "frontend/src/components/ImageViewer3D.tsx"
PROFILE = "frontend/src/pages/ProfilePage.tsx"
BAN = "frontend/src/components/AuditStatusBanner.tsx"
EN = "frontend/src/i18n/locales/en.json"
ES = "frontend/src/i18n/locales/es.json"
DE = "frontend/src/i18n/locales/de.json"

LEGACY_REDIRECT = (
    "  useEffect(() => {\n"
    "    const id = axios.interceptors.response.use((r) => r, (error: AxiosError) => {\n"
    "      if (error.response?.status === 401) { performLogout(); window.location.href = '/login'; }\n"
    "      return Promise.reject(error);\n"
    "    });\n"
    "    return () => axios.interceptors.response.eject(id);\n"
    "  }, [performLogout]);\n"
)

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── RC-067: durable, append-only, identifier-only audit trail; never breaks the request ──
    "B1_not_written_durably": ([(AUD, "                future = get_durable_audit_sink().submit(record)\n",
                                 "                future = None\n")],
                               "records only on stdout / the instance's disk — nothing in Firestore (the defect as found)"),
    "B2_overwrite_instead_of_append": ([(SINK, '.document(str(record["event_id"])).create(doc)', '.document(str(record["event_id"])).set(doc)')],
                                       "an existing audit record can be overwritten"),
    "B3_client_time_only": ([(SINK, '            doc["server_timestamp"] = _server_timestamp()\n',
                              '            doc["server_timestamp"] = record.get("client_timestamp")\n')],
                            "the record carries the instance's clock, not the server commit time"),
    "B4_failure_not_retried": ([(SINK, "                    if item.attempt >= self.max_attempts:\n", "                    if True:\n")],
                               "a failed write is given up at once (record lost from the trail)"),
    "B5_failure_silent": ([(SINK, 'f"AUDIT_SINK_WRITE_FAILED event_id=', 'f"audit write retry event_id=')],
                          "a failed audit write is not logged loudly"),
    "B6_drop_silent": ([(SINK, '            self._log_dropped(record, "queue_full")\n', "            pass\n")],
                       "a record dropped on queue overflow leaves no trace in the server log"),
    "B7_status_hides_failure": ([(SINK, "            elif recent > 0 or self.consecutive_failures >= self.failing_after:\n",
                                  "            elif False:\n"),
                                 (SINK, "            elif self.consecutive_failures > 0:\n", "            elif False:\n")],
                                "the administrator indicator says 'ok' while writes fail"),
    "B8_free_text_in_record": ([(AUD, '        "checksum": event.checksum,\n    }\n',
                                 '        "checksum": event.checksum,\n        "description": event.description,\n    }\n')],
                               "description text (free text) reaches the durable record"),
    "B9_concrete_path_and_query": ([(MW, "            endpoint=template,\n", "            endpoint=str(request.url),\n")],
                                   "the concrete URL with its query string instead of the route template"),
    "B10_file_reference_not_parsed": ([(MW, "            ids.update(file_ref_ids(str(value)))\n", '            ids["file_id"] = str(value)\n')],
                                      "an imaging file reference kept whole (file name) instead of its ids and hash"),
    "B11_typed_identifier_kept": ([(AUD, "attempted_identifier_hmac=keyed_hash(attempted_identifier) if attempted_identifier else None,",
                                    "attempted_identifier_hmac=attempted_identifier,")],
                                  "the identifier typed at a failed login is stored as typed"),
    "B12_login_not_audited": ([(AUTHN, "    _audit_login(http_request, AuditEventType.AUTH_LOGIN_SUCCESS, AuditOutcome.SUCCESS, user=user)\n", "")],
                              "a successful password login leaves no audit record (the defect as found)"),
    "B13_lockout_not_audited": ([(AUTHN, "        if user.is_locked:\n            _audit_login(", "        if False:\n            _audit_login(")],
                                "an account lock-out leaves no audit record"),
    "B14_longitudinal_decision_unmapped": ([(MW, '    ("POST", "/api/v1/segmentation/longitudinal/review"): (E.CLINICAL_LONGITUDINAL_REVIEW, "segmentation_pair"),\n', "")],
                                           "a radiologist's longitudinal decision recorded only as a generic modification"),
    "B15_ai_report_unmapped": ([(MW, '    ("POST", "/api/v1/ai/report/generate"): (E.CLINICAL_AI_REPORT_GENERATE, "report"),\n', "")],
                               "AI report generation not recorded as such"),
    "B16_segmentation_save_unmapped": ([(MW, '    ("POST", "/api/v1/segmentation/{segmentation_id}/save"): (E.CLINICAL_SEGMENTATION_SAVE, "segmentation"),\n', "")],
                                       "a segmentation save not recorded as such"),
    "B17_body_ids_ignored": ([(MW, '            if request.method == "POST" and path in BODY_ID_ROUTES:\n', "            if False:\n")],
                             "the segmentations a longitudinal decision was made on are not recorded"),
    "B18_reads_not_deduplicated": ([(MW, "            durable = not _seen_recently(key)\n", "            durable = True\n")],
                                   "every slice read written to Firestore (unreadable, costly trail)"),
    "B19_actor_not_identified": ([(MW, "        return data.user_id, data.username, data.role.value\n", "        return None, None, None\n")],
                                 "request records without the acting user"),
    "B20_no_request_id": ([(AUD, "            if event.request_id is None:\n                event.request_id = get_request_id()\n",
                            "            if False:\n                event.request_id = get_request_id()\n")],
                          "records not correlated with their request"),
    "B21_auth_service_events_lost": ([(SVC, "        from app.core.logging.audit import emit_audit, AuditEventType, AuditOutcome, AuditSeverity\n",
                                       "        from app.core.logging.audit import emit_audit, AuditEventType, AuditOutcome, AuditSeverity\n        return\n")],
                                     "admin user changes and password changes not in the durable trail (the in-memory list, as found)"),
    "B22_trail_read_by_radiologists": ([(AUTHR, "    outcome: Optional[str] = Query(None, max_length=16),\n    current_user: User = Depends(require_role(UserRole.ADMIN)),\n",
                                         "    outcome: Optional[str] = Query(None, max_length=16),\n    current_user: User = Depends(require_permission(Permission.AUDIT_VIEW)),\n")],
                                       "radiologists can read the whole audit trail (as found)"),
    "B23_status_open_to_all": ([(AUTHR, "async def get_audit_status(current_user: User = Depends(require_role(UserRole.ADMIN))):",
                                 "async def get_audit_status(current_user: User = Depends(get_current_active_user)):")],
                               "any user sees the audit-store status"),
    "B24_trail_reading_not_audited": ([(AUTHR, "    emit_audit(AuditEventType.AUDIT_LOG_READ,", "    (lambda *a, **k: None)(AuditEventType.AUDIT_LOG_READ,")],
                                      "reading the audit trail is not itself recorded"),
    "B25_clients_may_write_trail": ([(RULES, "      allow write: if false; // Only backend can write\n",
                                      "      allow write: if request.auth != null;\n")],
                                    "the security rules let a signed-in client write audit records"),
    # ── RC-068: rotating refresh token, hashed, expiring, revoked; HttpOnly SameSite=Strict cookie ──
    "S1_no_refresh_cookie": ([(AUTHN, "    token.refresh_expires_in = await run_in_threadpool(start_session, response, user, refresh_store)   # CAPA-015 RC-068\n",
                               "    token.refresh_expires_in = None\n")],
                             "password login starts no refresh session (sign in again every hour, as found)"),
    "S2_cookie_readable_by_scripts": ([(RT, '        secure=True,\n        httponly=True,\n        samesite="strict",\n    )',
                                        '        secure=True,\n        httponly=False,\n        samesite="strict",\n    )')],
                                      "the refresh cookie readable by page scripts"),
    "S3_cookie_sent_cross_site": ([(RT, '        httponly=True,\n        samesite="strict",\n    )', '        httponly=True,\n        samesite="lax",\n    )')],
                                  "the refresh cookie sent on cross-site navigations"),
    "S4_raw_token_stored": ([(RT, "            tx.create_token(hash_refresh_token(token), self._new_token_doc(family_id, user_id, now, 0))\n",
                              "            tx.create_token(token, self._new_token_doc(family_id, user_id, now, 0))\n")],
                            "the raw refresh token stored server-side"),
    "S5_no_rotation": ([(RT, '            tx.update_token(token_hash, {"used": True, "used_at": now, "replaced_by": new_hash,\n',
                         '            tx.update_token(token_hash, {"used_at": now, "replaced_by": new_hash,\n')],
                       "a refresh token stays usable after use"),
    "S6_reuse_not_revoking": ([(RT, 'tx.update_family(t["family_id"], {"revoked": True, "revoked_reason": "reuse_detected",',
                                'tx.update_family(t["family_id"], {"revoked": False, "revoked_reason": "reuse_detected",')],
                              "a replayed refresh token does not end the session family"),
    "S7_idle_not_enforced": ([(RT, '            if now >= _aware(t["expires_at"]):\n', "            if False:\n")],
                             "no idle expiry"),
    "S8_absolute_not_enforced": ([(RT, '            if now >= _aware(fam["absolute_expires_at"]):\n', "            if False:\n")],
                                 "no absolute expiry"),
    "S9_logout_not_revoking": ([(AUTHR, '            if family:\n                await run_in_threadpool(refresh_store.revoke_family, family, "logout")\n',
                                 '            if False:\n                await run_in_threadpool(refresh_store.revoke_family, family, "logout")\n')],
                               "logout leaves the refresh session usable"),
    "S10_password_change_not_revoking": ([(AUTHR, '            revoked = await run_in_threadpool(refresh_store.revoke_all_for_user, current_user.id, "password_change")\n',
                                           "            revoked = 0\n")],
                                         "a password change leaves every session usable"),
    "S11_password_not_persisted": ([(SVC, "        self._storage.save_user(user, new_hash, self._password_history[user_id])\n", "        pass\n")],
                                   "the new password kept in one process only: the old one still works at login (as found)"),
    "S12_inactive_user_refreshes": ([(AUTHN, '        elif not user.is_active:\n            reason = "user_inactive"\n',
                                      '        elif False:\n            reason = "user_inactive"\n')],
                                    "a deactivated user keeps refreshing"),
    "S13_locked_user_refreshes": ([(AUTHN, "        elif user.is_locked and (user.locked_until is None or datetime.utcnow() < user.locked_until):\n",
                                    "        elif False:\n")],
                                  "a locked user keeps refreshing"),
    "S14_role_not_reread": ([(AUTHN, "    access = token_manager.create_access_token(user_id=user.id, username=user.username, role=user.role)\n",
                              "    access = token_manager.create_access_token(user_id=user.id, username=user.username, role=type(user.role)(\"radiologist\"))\n")],
                            "the refreshed token keeps a role the user no longer has"),
    "S15_foreign_origin_accepted": ([(AUTHN, '    if origin and origin.rstrip("/") not in _allowed_origins():\n', "    if False:\n")],
                                    "a refresh from a foreign origin accepted"),
    "S16_long_access_token": ([(CFG, "    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=5, le=1440)\n",
                                "    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)\n")],
                              "a 60-minute access token (as found)"),
    "S17_passkey_no_session": ([(AUTHR, "        refresh_expires_in = await run_in_threadpool(start_session, response, user, refresh_store)   # CAPA-015 RC-068\n",
                                 "        refresh_expires_in = None\n")],
                               "passkey login starts no refresh session"),
    "S18_rotation_outside_transaction": ([(RT, "        self.txn.create(self._ref(TOKENS_COLLECTION, token_hash), data)\n",
                                           "        self._ref(TOKENS_COLLECTION, token_hash).create(data)\n"),
                                          (RT, "        self.txn.update(self._ref(TOKENS_COLLECTION, token_hash), data)\n",
                                           "        self._ref(TOKENS_COLLECTION, token_hash).update(data)\n"),
                                          (RT, "        self.txn.create(self._ref(FAMILIES_COLLECTION, family_id), data)\n",
                                           "        self._ref(FAMILIES_COLLECTION, family_id).create(data)\n"),
                                          (RT, "        self.txn.update(self._ref(FAMILIES_COLLECTION, family_id), data)\n",
                                           "        self._ref(FAMILIES_COLLECTION, family_id).update(data)\n")],
                                         "rotation writes outside the transaction (two instances could both rotate one token)"),
    # ── RC-069 (frontend): silent refresh; unsaved work kept; same user only ──
    "F1_hard_redirect_restored": ([(CTX, "  useEffect(() => installAuthInterceptors(axios), []);\n", LEGACY_REDIRECT)],
                                  "a 401 on the global axios instance sends the browser to /login (as found)"),
    "F2_refresh_to_api_host": ([(SESS, "  if (explicit) return explicit.replace(/\\/+$/, '');\n",
                                 "  return API_BASE_URL;\n  if (explicit) return explicit.replace(/\\/+$/, '');\n")],
                               "the refresh sent to the API host (another site: the SameSite cookie would never be sent)"),
    "F3_no_credentials": ([(SESS, "  withCredentials: true,\n  timeout: REFRESH_TIMEOUT_MS,\n",
                            "  withCredentials: false,\n  timeout: REFRESH_TIMEOUT_MS,\n")],
                          "auth calls without the cookie"),
    "F4_refresh_token_in_page_storage": ([(SESS, "      const res = await withTimeout(authClient.post(authUrl('/refresh'), null), REFRESH_TIMEOUT_MS);\n",
                                           "      const res = await withTimeout(authClient.post(authUrl('/refresh'), { refresh_token: localStorage.getItem('refresh_token') }), REFRESH_TIMEOUT_MS);\n")],
                                         "a refresh token read from page storage and sent in the body (as found)"),
    "F5_no_single_flight": ([(SESS, "  if (inflight) return inflight;\n", "")],
                            "concurrent 401s each refresh (the second is a replay: the session would be revoked)"),
    "F6_failure_redirects": ([(SESS, "      markSessionExpired();\n      return waitForReauthentication();\n",
                               "      window.location.href = '/login';\n      throw e;\n")],
                             "a failed refresh leaves the page (unsaved work discarded)"),
    "F7_waiting_requests_dropped": ([(SESS, "  pending.forEach((w) => w.resolve(accessToken));\n",
                                      "  pending.forEach((w) => w.reject(new SessionExpiredError()));\n")],
                                    "the save that was waiting fails after the user signed in again"),
    "F8_no_proactive_refresh": ([(SESS, "  const delay = Math.max(MIN_DELAY_MS, deadline - Date.now() - REFRESH_LEAD_MS);\n",
                                  "  const delay = Math.max(MIN_DELAY_MS, deadline - Date.now() + REFRESH_LEAD_MS);\n")],
                                "the token renewed only after it has expired"),
    "F9_other_user_accepted": ([(CTX, "    if (!user || !userData || userData.id !== user.id) {\n", "    if (!user || !userData) {\n")],
                               "another person's sign-in accepted: the work would be saved under their name"),
    "F10_other_session_left_open": ([(CTX, "      authClient.post(authUrl('/logout'), null, { headers: bearer(tokenData?.access_token) }).catch(() => undefined);\n      throw new WrongUserError();\n",
                                      "      throw new WrongUserError();\n")],
                                    "the other person's new session left open at the workstation"),
    "F11_logout_local_only": ([(CTX, "    authClient.post(authUrl('/logout'), null, { headers: bearer(current) }).catch(() => undefined);\n", "")],
                              "logout does not tell the server (refresh session stays valid, as found)"),
    "F12_dialog_absent": ([(DLG, "  if (!sessionExpired || !user) return null;\n", "  if (sessionExpired || !sessionExpired) return null;\n")],
                          "no re-login dialog"),
    "F13_unsaved_not_named": ([(DLG, "        {hasUnsaved && (\n", "        {false && (\n")],
                              "the dialog does not say the unsaved segmentation is kept"),
    "F14_fetch_not_recovering": ([(SESS, "  if (first.status !== 401 || !tabHasSession()) return first;\n", "  return first;\n")],
                                 "volume / export downloads fail on an expired token"),
    "F15_banner_hidden": ([(BAN, "  if (!isAdmin || !status || status.state === 'ok') return null;\n", "  if (isAdmin || !isAdmin) return null;\n")],
                          "administrators are not told that audit writing fails"),
    "F16_banner_for_everyone": ([(BAN, "  const isAdmin = String(user?.role ?? '').toLowerCase() === 'admin';\n", "  const isAdmin = Boolean(user);\n")],
                                "every user polls and sees the audit-store status"),
    "F17_spanish_text_missing": ([(ES, '    "reauthTitle": "Vuelva a iniciar sesión para continuar",\n', "")],
                                 "a dialog text without its Spanish entry (English shown)"),
    "F18_german_text_in_english": ([(DE, '"reauthMessage": "Zu Ihrer Sicherheit wurde die Sitzung beendet.',
                                     '"reauthMessage": "For your security your session has ended.')],
                                   "the German dialog text left in English"),
    # ── independent review of PR #65 (2026-10-24) ──
    "R1_startup_accepts_short_idle": ([(CFG, "        if self.REFRESH_TOKEN_IDLE_MINUTES <= self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES + 2:\n",
                                        "        if False:\n")],
                                      "a refresh idle limit shorter than the access token accepted at start-up (M1)"),
    "R2_no_refresh_deadline_to_client": ([(AUTHN, "    access.refresh_expires_in = issued.max_age_seconds\n", "")],
                                         "the client is not told when the refresh session ends (M1)"),
    "R3_template_60": ([(GEN, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15\n", "JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60\n")],
                       "the secret generator emits a 60-minute access token again (M1)"),
    "R4_auth_route_skipped_unless_401_403": ([(MW, "        if path.startswith(AUTH_PREFIX) and ctx.explicit and status < 500:\n",
                                               "        if path.startswith(AUTH_PREFIX) and (ctx.explicit or status not in (401, 403)) and status < 500:\n")],
                                             "/auth requests without their own event recorded only on 401/403 (M3, as found)"),
    "R5_passkey_register_unmapped": ([(MW, '    ("POST", "/api/v1/auth/webauthn/register/complete"): (E.AUTH_CREDENTIAL_REGISTER, "credential"),\n', "")],
                                     "a passkey registration recorded only as a generic modification (M3)"),
    "R6_passkey_delete_unmapped": ([(MW, '    ("DELETE", "/api/v1/auth/webauthn/credentials/{credential_id}"): (E.AUTH_CREDENTIAL_DELETE, "credential"),\n', "")],
                                   "a passkey deletion recorded only as a generic deletion (M3)"),
    "R7_logout_event_dropped": ([(AUTHR, "    emit_audit(AuditEventType.AUTH_LOGOUT, outcome, request=request, user_id=user_id,",
                                  "    (lambda *a, **k: None)(AuditEventType.AUTH_LOGOUT, outcome, request=request, user_id=user_id,")],
                                "a logout (incl. one with an unknown cookie and no bearer) leaves no logout record (M3, as found)"),
    "R8_no_grace": ([(RT, "                if (self.grace and used_at is not None and now - used_at <= self.grace and succ is not None\n",
                      "                if (False and used_at is not None and now - used_at <= self.grace and succ is not None\n")],
                    "a lost refresh response or a two-tab race revokes the session (m5, as found)"),
    "R9_grace_after_successor_used": ([(RT, '                        and not succ.get("used") and t.get("successor_sealed")\n',
                                        '                        and t.get("successor_sealed")\n')],
                                      "a replay accepted although the successor was already used (theft) (m5)"),
    "R9b_both_successor_checks_removed": ([(RT, '                        and not succ.get("used") and t.get("successor_sealed")\n',
                                            '                        and t.get("successor_sealed")\n'),
                                           (RT, '            if pred is not None and pred.get("successor_sealed"):   # this token is used: drop the sealed copy\n'
                                                '                tx.update_token(t["predecessor"], {"successor_sealed": None})\n', "")],
                                          "a replay accepted after the successor was used: both protections removed (m5)"),
    "R10_grace_unbounded": ([(RT, "now - used_at <= self.grace and succ is not None", "now - used_at <= self.grace * 1000 and succ is not None")],
                            "a replay accepted long after the window (m5)"),
    "R11_successor_stored_raw": ([(RT, '"successor_sealed": self._seal(new_token, t["family_id"])})',
                                   '"successor_sealed": new_token})')],
                                 "the successor kept for the grace window stored readable (m5)"),
    "R12_store_error_revokes": ([(AUTHN, "    except Exception as e:  # noqa: BLE001\n        return unavailable(e)\n    if owner_id:\n",
                                  "    except Exception as e:  # noqa: BLE001\n        user = None\n    if owner_id:\n")],
                                "a transient user-store error treated as 'user gone': the family is revoked (m6, as found)"),
    "R13_lookup_swallows_errors": ([(USTORE, '            raise UserStoreUnavailable(f"user store read failed: {type(e).__name__}") from e\n',
                                     "            return None\n")],
                                   "the strict lookup returns None on a read error (m6)"),
    "R14_refresh_on_event_loop": ([(AUTHN, "        owner_id, family_id = await run_in_threadpool(refresh_store.peek_owner, token)\n",
                                    "        owner_id, family_id = refresh_store.peek_owner(token)\n")],
                                  "a Firestore call of /refresh runs on the event loop (m8)"),
    "R15_expired_families_revoked_memory": ([(RT, '                    and (now is None or _aware(f.get("absolute_expires_at")) > now)]\n',
                                              "                    ]\n")],
                                            "'revoke every session' also rewrites expired families (memory repository) (m8)"),
    "R16_expired_families_revoked_firestore": ([(RT, '            if now is not None and _aware(f.get("absolute_expires_at")) <= now:\n                continue\n', "")],
                                               "'revoke every session' also rewrites expired families (Firestore repository) (m8)"),
    "R17_leftmost_forwarded_hop": ([(CIP, "        return xff[i]\n", "        return xff[0]\n")],
                                   "the client-supplied first X-Forwarded-For entry used as the client IP (m9, as found)"),
    "R18_hosting_egress_taken_for_client": ([(CIP, "        while i > 0 and steps < _MAX_STEPS and _is_egress(xff[i], nets):\n",
                                              "        while False:\n")],
                                            "Firebase Hosting's own egress address taken for the client (m9 / N1)"),
    "R19_no_source_budget": ([(AUD, '            if durable and _needs_budget(record) and not _take_budget(record.get("ip_address") or "unknown"):\n',
                               "            if False:\n")],
                             "a flood of anonymous requests from one source fills the durable queue (m9)"),
    "R20_drops_red_forever": ([(SINK, "            elif recent > 0 or self.consecutive_failures >= self.failing_after:\n",
                                "            elif self.dropped_total > 0 or self.consecutive_failures >= self.failing_after:\n")],
                              "one old dropped record keeps the banner red until a restart (m9, as found)"),
    "R21_plain_sha256": ([(AUD, '    return hmac.new(_hash_key(), str(value).encode("utf-8"), hashlib.sha256).hexdigest()[:length]\n',
                           '    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:length]\n')],
                         "identifiers hashed with plain SHA-256 (reversible for MRNs, usernames) (m10, as found)"),
    "R22_raw_jwt_key": ([(AUD, '            _HASH_KEY = hmac.new(secret.encode("utf-8"), b"mstool-audit-identifier-hash-v1", hashlib.sha256).digest()\n',
                          '            _HASH_KEY = secret.encode("utf-8")\n')],
                        "the JWT secret used raw as the hash key (m10)"),
    "R23_full_user_agent": ([(AUD, '        "user_agent": classify_user_agent(event.user_agent),\n',
                              '        "user_agent": str(event.user_agent)[:200] if event.user_agent else None,\n')],
                            "the full user-agent string stored (m10, as found)"),
    "R24_forwarded_host_decides": ([(CIP, "        while i > 0 and steps < _MAX_STEPS and _is_egress(xff[i], nets):\n",
                                     '        while i > 0 and steps < _MAX_STEPS and (_is_egress(xff[i], nets) or request.headers.get("x-forwarded-host")):\n')],
                                   "a client-sent X-Forwarded-Host makes the server trust a client-sent hop (N1, as found)"),
    "R25_any_entry_stepped_over": ([(CIP, "        while i > 0 and steps < _MAX_STEPS and _is_egress(xff[i], nets):\n",
                                     "        while i > 0 and steps < _MAX_STEPS:\n")],
                                   "entries that are not published egress addresses are stepped over: the client chooses its address (N1)"),
    "R26_single_egress_step": ([(CIP, "        while i > 0 and steps < _MAX_STEPS and _is_egress(xff[i], nets):\n",
                                 "        while i > 0 and steps < 1 and _is_egress(xff[i], nets):\n")],
                               "a chain through two egress addresses collapses to a proxy address (N1)"),
    "R27_egress_override_ignored": ([(CIP, '    return _networks(override if override is not None else ",".join(EGRESS_CIDRS))\n',
                                      '    return _networks(",".join(EGRESS_CIDRS))\n')],
                                    "the egress list cannot be replaced by a Cloud Run setting: a stale list needs a rebuild (N1)"),
    "R28_authenticated_failures_budgeted": ([(AUD, '    return not record.get("actor_user_id")\n',
                                              '    return record.get("outcome") != "success" or not record.get("actor_user_id")\n')],
                                            "anonymous noise pushes an authenticated user's failed clinical action out of the durable trail (N4, as found)"),
    "R29_register_begin_as_register": ([(MW, '(E.AUTH_CREDENTIAL_REGISTER_BEGIN, "credential")', '(E.AUTH_CREDENTIAL_REGISTER, "credential")')],
                                       "starting a passkey registration is recorded as a completed registration (nit, as found)"),
    "R30_developer_env_breaks_suite": ([(CONFTEST, "os.environ['JWT_ACCESS_TOKEN_EXPIRE_MINUTES'] = '15'\nos.environ['REFRESH_TOKEN_IDLE_MINUTES'] = '30'\n"
                                                   "os.environ['REFRESH_TOKEN_ABSOLUTE_HOURS'] = '12'\n", "")],
                                       "a developer backend/.env with old session lifetimes stops the test suite (N2, as found)"),
    "FR1_client_ignores_refresh_deadline": ([(SESS, "  const deadline = accessExp && sessionExp ? Math.min(accessExp, sessionExp) : accessExp;\n",
                                              "  const deadline = accessExp;\n")],
                                            "the renewal waits for the access token although the refresh session ends first (M1)"),
    "FR2_other_tab_clears_this_tab": ([(CTX, "    const current = getAccessToken();\n    if (current) setToken(current);\n",
                                        "    setToken(getAccessToken());\n")],
                                      "a logout in another tab clears this tab's state: React Router sends it to /login, work lost (M2, as found)"),
    "FR3_foreign_token_used": ([(SESS, "  return !myUserId || !owner || owner === myUserId;\n", "  return true;\n")],
                               "another user's token written by another tab is used here (M2, as found)"),
    "FR4_no_resume_from_other_tab": ([(SESS, "    if (token !== expiredWithToken) resumeWith(token);\n", "    void expiredWithToken;\n")],
                                     "a re-login in another tab leaves this tab's dialog open and its save waiting (M2, as found)"),
    "FR5_stale_dialog_signs_out": ([(CTX, "    if (tryResumeFromSharedSession()) return;\n", "")],
                                   "'sign out' in a stale dialog ends the session another tab recovered (M2, as found)"),
    "FR6_inactivity_ignores_other_tabs": ([(HOOK, "    const v = Number(localStorage.getItem(ACTIVITY_KEY));\n", "    const v = 0;\n")],
                                          "each tab's inactivity timer logs out while the user works in another tab (M2, as found)"),
    "FR7_activity_not_shared": ([(HOOK, "    try { localStorage.setItem(ACTIVITY_KEY, String(now)); } catch { /* storage unavailable */ }\n", "")],
                                "this tab's activity is not shared with the other tabs (M2)"),
    "FR8_404_405_not_ended": ([(SESS, "const ENDED = new Set([401, 403, 404, 405]);", "const ENDED = new Set([401, 403]);")],
                              "a 404/405 from /refresh during a deployment fails the request instead of opening the dialog (M4, as found)"),
    "FR9_refresh_can_hang": ([(SESS, "      const res = await withTimeout(authClient.post(authUrl('/refresh'), null), REFRESH_TIMEOUT_MS);\n",
                               "      const res = await authClient.post(authUrl('/refresh'), null);\n")],
                             "a hanging refresh holds the cross-tab lock forever (m13, as found)"),
    "FR10_caller_token_kept": ([(SESS, "    if (k.toLowerCase() !== 'authorization') callerHeaders[k] = v;\n", "    callerHeaders[k] = v;\n")],
                               "a caller-provided Authorization header (another user's token) is sent from this tab (N3, as found)"),
    "FR11_viewer3d_reads_storage": ([(V3D, "  const token = getAccessToken();   // CAPA-015 re-review N3: only this tab's own token\n",
                                      "  const token = localStorage.getItem('access_token');\n")],
                                    "the 3D viewer reads the shared token from storage itself (N3, as found)"),
    "FR12_profile_reads_storage": ([(PROFILE, "    setLoading(true);\n    try {\n      const token = getAccessToken();   // CAPA-015 re-review N3: only this tab's own token\n",
                                     "    setLoading(true);\n    try {\n      const token = localStorage.getItem('access_token');\n")],
                                   "the profile page reads the shared token from storage itself (N3, as found)"),
    "FR13_page_readable_behind_dialog": ([(DLG, "    if (!sessionExpired || !user) return undefined;\n    const locked",
                                           "    if (!sessionExpired || !user || host) return undefined;\n    const locked")],
                                         "patient data stays readable and clickable behind the re-login dialog (N5, as found)"),
    "FR14_page_not_blurred": ([(DLG, "      node.style.filter = 'blur(18px)';\n", "")],
                              "the page behind the re-login dialog is not blurred (N5)"),
    "FR15_page_not_inert": ([(DLG, "      node.setAttribute('inert', '');\n", "")],
                            "the page behind the re-login dialog can still take focus and input (N5)"),
}

EXPECTED_UNDETECTED = {
    "R9_grace_after_successor_used": (
        "equivalent: using the successor clears the predecessor's sealed copy in the same transaction, so the "
        "grace branch cannot be taken once the successor was used even without this check (defence in depth); "
        "R9b removes both protections and is detected"),
}


def run_backend():
    env = dict(os.environ, **NO_CLOUD)
    r = subprocess.run([PY, "-m", "pytest", *BACKEND_TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    # Counts from pytest's final summary line only (captured log lines also contain "1 error").
    summary = (re.findall(r"^=+ (.+) in [\d.]+s(?: \([^)]*\))? =+$", r.stdout, re.M) or [""])[-1]
    f = re.search(r"(\d+) failed", summary)
    p = re.search(r"(\d+) passed", summary)
    e = re.search(r"(\d+) errors?\b", summary)
    return {"suite": "backend", "failed": int(f.group(1)) if f else 0, "passed": int(p.group(1)) if p else 0,
            "errors": int(e.group(1)) if e else 0, "skipped": 0,
            "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))}


def run_frontend():
    out = os.path.join(tempfile.gettempdir(), "capa015_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run("npx vitest run " + " ".join(FRONTEND_TESTS) + f" --pool=threads --reporter=json --outputFile={out}",
                   cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(out):
        return {"suite": "frontend", "failed": 0, "passed": 0, "skipped": 0, "errors": 1,
                "failing_tests": [], "error_files": ["vitest produced no report"]}
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    failed = [a["title"] for a in res if a["status"] == "failed"]
    errors = [f["name"].split("frontend")[-1] for f in d["testResults"] if f["status"] == "failed" and not f["assertionResults"]]
    return {"suite": "frontend", "failed": len(failed), "passed": sum(a["status"] == "passed" for a in res),
            "skipped": sum(a["status"] in ("skipped", "pending") for a in res), "errors": len(errors),
            "failing_tests": failed, "error_files": errors}


def run_for(paths):
    return run_frontend() if all(p.startswith("frontend/") for p in paths) else run_backend()


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    files = sorted({e[0] for edits, _w in M.values() for e in edits})
    raw = {p: open(p, "rb").read() for p in files}
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
    for name, (edits, _w) in M.items():
        for path, anchor, _r in edits:
            c = text[path].count(anchor)
            assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"
    if "--check" in sys.argv:
        print(f"{len(M)} mutations, every anchor occurs exactly once")
        return 0
    tests = BACKEND_TESTS + [f"frontend/{t}" for t in FRONTEND_TESTS]
    test_sha = {t: sha(open(t if t.startswith("frontend/") else os.path.join("backend", t),
                            encoding="utf-8").read().replace("\r\n", "\n")) for t in tests}
    previous = json.load(open(OUT, encoding="utf-8")) if only and os.path.exists(OUT) else {"mutations": {}}
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "method": "one mutation at a time; each anchor asserted to occur exactly once; the bound tests of the "
                     "mutated side are run (backend pytest without cloud credentials, frontend vitest JSON reporter)",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: sha(text[p]) for p in files},
           "test_sha256": test_sha,
           "tests": tests, "mutations": {}}
    if only:
        res["partial_rerun"] = (f"re-executed from {res['executed']}: mutations starting with {only!r} and every mutation "
                                "whose bound tests changed since its previous execution; the others are kept from the "
                                "previous run with the time and test hashes they were executed with")
    try:
        for name, (edits, what) in M.items():
            if only and not name.startswith(only) and name in previous["mutations"]:
                kept = dict(previous["mutations"][name])
                current = {t: test_sha[t] for t in kept.get("test_sha256", {}) if t in test_sha}
                if current == kept.get("test_sha256") and current:
                    res["mutations"][name] = kept
                    continue
            touched = {}
            for path, anchor, repl in edits:
                touched[path] = touched.get(path, text[path]).replace(anchor, repl, 1)
            for path, mutated in touched.items():
                assert mutated != text[path], name
                open(path, "w", encoding="utf-8", newline=eol[path]).write(mutated)
            out = run_for(list(touched))
            suite_tests = [f"frontend/{t}" for t in FRONTEND_TESTS] if out["suite"] == "frontend" else BACKEND_TESTS
            out.update({"reintroduces": what, "applied": True,
                        "executed": datetime.datetime.now().isoformat(timespec="seconds"),
                        "test_sha256": {t: test_sha[t] for t in suite_tests}})
            res["mutations"][name] = out
            for path in touched:
                open(path, "wb").write(raw[path])
            print(f"{name:40s} [{out['suite']}] {out['failed']} failed / {out['errors']} errors / {out['passed']} passed", flush=True)
    finally:
        for p, b in raw.items():
            open(p, "wb").write(b)
    for p in files:   # the restore is byte-exact
        assert open(p, "rb").read() == raw[p], p
    res["restored"] = {"backend": run_backend(), "frontend": run_frontend()}
    res["expected_undetected"] = EXPECTED_UNDETECTED
    res["undetected"] = sorted(n for n, v in res["mutations"].items() if v["failed"] == 0 and v["errors"] == 0)
    res["unexpected_undetected"] = sorted(set(res["undetected"]) - set(EXPECTED_UNDETECTED))
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    rb, rf = res["restored"]["backend"], res["restored"]["frontend"]
    print("restored backend", rb["passed"], "passed /", rb["failed"], "failed | frontend", rf["passed"], "passed /",
          rf["failed"], "failed /", rf["skipped"], "skipped | undetected:", res["undetected"],
          "| unexpected:", res["unexpected_undetected"])
    bad = rb["failed"] or rb["errors"] or rf["failed"] or rf["errors"] or rf["skipped"]
    return 1 if res["unexpected_undetected"] or bad else 0


if __name__ == "__main__":
    sys.exit(main())
