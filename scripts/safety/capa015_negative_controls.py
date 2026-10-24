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
BACKEND_TESTS = ["tests/unit/test_capa015_audit_and_session.py"]
FRONTEND_TESTS = ["src/services/session.capa015.test.tsx"]
NO_CLOUD = {"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(tempfile.gettempdir(), "capa015-no-cloud-credentials.json"),
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
SESS = "frontend/src/services/session.ts"
CTX = "frontend/src/contexts/AuthContext.tsx"
DLG = "frontend/src/components/SessionExpiredDialog.tsx"
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
    "B7_status_hides_failure": ([(SINK, "            elif self.dropped_total > 0 or self.consecutive_failures >= self.failing_after:\n",
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
    "B11_typed_identifier_kept": ([(AUD, "attempted_identifier_sha256=sha256_prefix(attempted_identifier) if attempted_identifier else None,",
                                    "attempted_identifier_sha256=attempted_identifier,")],
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
    "S1_no_refresh_cookie": ([(AUTHN, "    start_session(response, user, refresh_store)       # CAPA-015 RC-068\n", "")],
                             "password login starts no refresh session (sign in again every hour, as found)"),
    "S2_cookie_readable_by_scripts": ([(RT, '        secure=True,\n        httponly=True,\n        samesite="strict",\n    )',
                                        '        secure=True,\n        httponly=False,\n        samesite="strict",\n    )')],
                                      "the refresh cookie readable by page scripts"),
    "S3_cookie_sent_cross_site": ([(RT, '        httponly=True,\n        samesite="strict",\n    )', '        httponly=True,\n        samesite="lax",\n    )')],
                                  "the refresh cookie sent on cross-site navigations"),
    "S4_raw_token_stored": ([(RT, "            tx.create_token(hash_refresh_token(token), self._new_token_doc(family_id, user_id, now, 0))\n",
                              "            tx.create_token(token, self._new_token_doc(family_id, user_id, now, 0))\n")],
                            "the raw refresh token stored server-side"),
    "S5_no_rotation": ([(RT, '            tx.update_token(token_hash, {"used": True, "used_at": now, "replaced_by": new_hash})\n',
                         '            tx.update_token(token_hash, {"used_at": now, "replaced_by": new_hash})\n')],
                       "a refresh token stays usable after use"),
    "S6_reuse_not_revoking": ([(RT, 'tx.update_family(t["family_id"], {"revoked": True, "revoked_reason": "reuse_detected",',
                                'tx.update_family(t["family_id"], {"revoked": False, "revoked_reason": "reuse_detected",')],
                              "a replayed refresh token does not end the session family"),
    "S7_idle_not_enforced": ([(RT, '            if now >= _aware(t["expires_at"]):\n', "            if False:\n")],
                             "no idle expiry"),
    "S8_absolute_not_enforced": ([(RT, '            if now >= _aware(fam["absolute_expires_at"]):\n', "            if False:\n")],
                                 "no absolute expiry"),
    "S9_logout_not_revoking": ([(AUTHR, '            if family:\n                refresh_store.revoke_family(family, "logout")\n',
                                 '            if False:\n                refresh_store.revoke_family(family, "logout")\n')],
                               "logout leaves the refresh session usable"),
    "S10_password_change_not_revoking": ([(AUTHR, '            revoked = refresh_store.revoke_all_for_user(current_user.id, "password_change")\n',
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
    "S17_passkey_no_session": ([(AUTHR, "        start_session(response, user, refresh_store)     # CAPA-015 RC-068\n", "")],
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
    "F3_no_credentials": ([(SESS, "  withCredentials: true,\n  headers: { 'Content-Type': 'application/json' },\n});",
                            "  withCredentials: false,\n  headers: { 'Content-Type': 'application/json' },\n});")],
                          "auth calls without the cookie"),
    "F4_refresh_token_in_page_storage": ([(SESS, "      const res = await authClient.post(authUrl('/refresh'), null);\n",
                                           "      const res = await authClient.post(authUrl('/refresh'), { refresh_token: localStorage.getItem('refresh_token') });\n")],
                                         "a refresh token read from page storage and sent in the body (as found)"),
    "F5_no_single_flight": ([(SESS, "  if (inflight) return inflight;\n", "")],
                            "concurrent 401s each refresh (the second is a replay: the session would be revoked)"),
    "F6_failure_redirects": ([(SESS, "      markSessionExpired();\n      return waitForReauthentication();\n",
                               "      window.location.href = '/login';\n      throw e;\n")],
                             "a failed refresh leaves the page (unsaved work discarded)"),
    "F7_waiting_requests_dropped": ([(SESS, "  pending.forEach((w) => w.resolve(accessToken));\n",
                                      "  pending.forEach((w) => w.reject(new SessionExpiredError()));\n")],
                                    "the save that was waiting fails after the user signed in again"),
    "F8_no_proactive_refresh": ([(SESS, "  const delay = Math.max(MIN_DELAY_MS, exp - Date.now() - REFRESH_LEAD_MS);\n",
                                  "  const delay = Math.max(MIN_DELAY_MS, exp - Date.now() + REFRESH_LEAD_MS);\n")],
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
    "F14_fetch_not_recovering": ([(SESS, "  if (first.status !== 401 || !getAccessToken()) return first;\n", "  return first;\n")],
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
}

EXPECTED_UNDETECTED = {}


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
