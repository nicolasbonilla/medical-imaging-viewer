"""Negative controls for PRB-020 .. PRB-026 (platform, security and regulatory findings of the 2026-10-28 browser
capture of the release candidate): open self-registration, unscoped patient registry, false security claims,
creator access and access-log reason, new accounts invisible to the administrator, counts of deleted studies,
"SEGM." always 0, placeholder segmentation author, inconsistent initials, Spanish text in the English interface.

Each mutation re-introduces ONE defect the fix removed (or removes one sub-control it added) in the real source,
one at a time. The script:
  - refuses to start if any file it mutates has uncommitted changes (it restores bytes from a snapshot);
  - asserts every anchor occurs exactly once in the LF text (so a Windows CRLF checkout works), writes the
    mutation with the file's own line endings, restores the exact original bytes after each mutation, and also on
    exit, on Ctrl+C and on SIGTERM/SIGBREAK/SIGHUP;
  - runs only the bound tests of the side it mutated — backend offline per PRB-002 (a credentials file and a
    gcloud configuration folder that do not exist, an offline project id, no model-provider key), frontend with
    vitest (--pool=threads, JSON reporter);
  - checks the baseline passes first, and records failing test names per mutation.

Run from the repository root:
    python scripts/safety/prb020_negative_controls.py              # every mutation
    python scripts/safety/prb020_negative_controls.py --only P     # only the mutations whose name starts with P
Output: docs/iec62304/records/risk_verification/PRB-020_negative_controls_2026-10-28.json
NEVER run this while anything else edits the files it mutates.
"""
import atexit
import datetime
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = "docs/iec62304/records/risk_verification/PRB-020_negative_controls_2026-10-28.json"

BACKEND_TESTS = ["tests/unit/test_prb020_self_registration_and_accounts.py",
                 "tests/unit/test_prb021_patient_scope_creator_counts.py",
                 "tests/security/test_authentication.py::TestAccountLockout"]
FRONTEND_TESTS = ["src/pages/LoginPage.prb020.test.tsx", "src/components/StudyCard.prb025.test.tsx",
                  "src/components/patientInitials.prb026.test.tsx", "src/hooks/useSegmentationData.prb026.test.tsx",
                  "src/components/i18nStrings.prb026.test.tsx"]

CFG = "backend/app/core/config.py"
POL = "backend/app/security/registration_policy.py"
AUTHN = "backend/app/api/routes/authentication.py"
AUTHR = "backend/app/api/routes/auth.py"
SVC = "backend/app/security/auth.py"
PAT = "backend/app/api/routes/patients.py"
PSVC = "backend/app/services/patient_service_firestore.py"
PSCH = "backend/app/models/patient_schemas.py"
PACC = "backend/app/security/patient_access.py"
PDEP = "backend/app/security/patient_access_dependency.py"
SSVC = "backend/app/services/study_service_firestore.py"
STR = "backend/app/api/routes/studies.py"
SEG = "backend/app/services/segmentation_service.py"
LOGIN = "frontend/src/pages/LoginPage.tsx"
REGP = "frontend/src/services/registrationPolicy.ts"
CARD = "frontend/src/components/StudyCard.tsx"
PCARD = "frontend/src/components/PatientCard.tsx"
BANNER = "frontend/src/components/PatientBanner.tsx"
PDISP = "frontend/src/utils/patientDisplay.ts"
HOOK = "frontend/src/hooks/useSegmentationData.ts"
PANEL = "frontend/src/components/SegmentationPanel.tsx"
AUTHOR = "frontend/src/utils/segmentationAuthor.ts"
ROW = "frontend/src/components/viewer/SegmentationRow.tsx"
NIIVUE = "frontend/src/components/NiivueViewer2D.tsx"
IV2D = "frontend/src/components/ImageViewer2D.tsx"
CONF = "frontend/src/components/ConformalPanel.tsx"
EN = "frontend/src/i18n/locales/en.json"
DE = "frontend/src/i18n/locales/de.json"

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── PRB-020: self-registration (REQ-SEC-030/031) ──
    "R1_register_route_open": ([(AUTHN, "    dependencies=[Depends(require_self_registration_enabled)],\n", "")],
                               "POST /auth/register creates an account for anyone (the defect as found)"),
    "R2_production_honours_the_setting": ([(POL, '    if str(getattr(settings, "ENVIRONMENT", PRODUCTION)).strip().lower() == PRODUCTION:\n',
                                            "    if False:\n")],
                                          "a production server opens self-registration when the setting is on"),
    "R3_setting_on_by_default": ([(CFG, "    SELF_REGISTRATION_ENABLED: bool = Field(default=False)\n",
                                   "    SELF_REGISTRATION_ENABLED: bool = Field(default=True)\n")],
                                 "self-registration on unless someone turns it off"),
    "R4_status_endpoint_says_open": ([(POL, "    enabled = self_registration_enabled()\n", "    enabled = True\n")],
                                     "the sign-in page is told self-registration is on when it is not"),
    "R5_any_role_creates_accounts": ([(AUTHR, "    current_user: User = Depends(require_permission(Permission.USER_CREATE)),\n) -> User:\n",
                                       "    current_user: User = Depends(get_current_active_user),\n) -> User:\n")],
                                     "a viewer, technician or radiologist creates accounts, an administrator among them"),
    "R6_creator_of_the_account_not_recorded": ([(AUTHR, "created = auth_service.register_user(user_create, created_by=current_user.id)",
                                                 "created = auth_service.register_user(user_create)")],
                                               "who created an account is not recorded"),
    # ── PRB-024: the persistent user store is the source of truth ──
    "S1_list_users_from_memory": ([(SVC, "        users = self._storage.list_all_users()\n",
                                    "        users = list(self._users.values())\n")],
                                  "accounts created after start-up are invisible to the administrator (the defect as found)"),
    "S2_get_user_from_memory": ([(SVC, "        user = self._storage.get_user_by_id(user_id)\n        if user is None:\n            self._users.pop(user_id, None)\n            return None\n",
                                  "        user = self._users.get(user_id)\n        if user is None:\n            return None\n")],
                                "an account created after start-up cannot be opened or changed (PATCH answered 500)"),
    "S3_duplicates_checked_in_memory_only": ([(SVC, "                or self._storage.username_exists(user_create.username)):\n",
                                               "                or False):\n")],
                                             "a username another instance already stored is created twice"),
    "S4_unstored_account_reported_as_created": ([(SVC, '            raise HTTPException(\n                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,\n',
                                                  '            return user\n            raise HTTPException(\n                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,\n')],
                                                "an account the store did not take is reported as created"),
    "S5_lockout_kept_in_memory_only": ([(SVC, "            self._persist_login_state(user)   # PRB-024: the store is the source of truth\n\n            raise HTTPException(",
                                         "\n            raise HTTPException(")],
                                       "a lockout is invisible to the administrator routes and lost on restart"),
    "S6_login_state_written_without_the_password": ([(SVC, "            self._storage.save_user(user, password_hash, self._password_history.get(user.id))\n",
                                                      '            self._storage.save_user(user, "", self._password_history.get(user.id))\n')],
                                                    "recording a failed sign-in overwrites the stored password hash (locks the user out)"),
    # ── PRB-021: patient registry scoped to the care team (REQ-SEC-014) ──
    "P1_patient_list_unscoped": ([(PAT, "        allowed_ids=_listing_scope(current_user, care_team),\n", "        allowed_ids=None,\n")],
                                 "every signed-in user lists every patient (the defect as found)"),
    "P2_patient_search_unscoped": ([(PAT, "search_patients(search, allowed_ids=_listing_scope(current_user, care_team))",
                                     "search_patients(search, allowed_ids=None)")],
                                   "every signed-in user searches every patient"),
    "P3_revoked_assignment_lists": ([(PAT, "if e.user_id == str(current_user.id) and e.is_active}", "if e.user_id == str(current_user.id)}")],
                                    "a revoked care-team assignment still lists the patient"),
    "P4_everyone_scoped_like_an_administrator": ([(PAT, "    if current_user.role == UserRole.ADMIN:\n        return None\n    try:\n",
                                                   "    if True:\n        return None\n    try:\n")],
                                                 "the listing scope returns the whole registry for every role"),
    "P5_scoped_search_ignores_the_mrn": ([(PSVC, '                if search.mrn and d.get("mrn") != search.mrn.upper():\n                    return False\n', "")],
                                         "a scoped search returns patients that do not match the record number"),
    "P6_scoped_list_ignores_the_status": ([(PSVC, '            if status and data.get("status") != status:\n                continue\n', "")],
                                          "a scoped list ignores the status filter"),
    "P7_scoped_list_not_paged": ([(PSVC, "            return self._summaries_with_counts(self._page(docs, page, page_size)), len(docs)\n",
                                   "            return self._summaries_with_counts(docs), len(docs)\n")],
                                 "a scoped list ignores the page size"),
    # ── PRB-023: creator on the care team; the true denial reason ──
    "C1_creator_not_on_the_care_team": ([(PAT, "    if current_user.role != UserRole.ADMIN:\n        try:\n            care_team.assign(",
                                          "    if False:\n        try:\n            care_team.assign(")],
                                        "the clinician who creates a patient gets 'Patient not found' (the defect as found)"),
    "C2_administrator_put_on_care_teams": ([(PAT, "    if current_user.role != UserRole.ADMIN:\n        try:\n            care_team.assign(",
                                             "    if True:\n        try:\n            care_team.assign(")],
                                           "an administrator who creates a patient is put on its care team"),
    "C3_failed_assignment_hidden": ([(PAT, "            raise HTTPException(\n                status_code=500,\n",
                                      "            return patient\n            raise HTTPException(\n                status_code=500,\n")],
                                    "a creator whose assignment was not recorded is told the creation succeeded"),
    "C4_provenance_not_read": ([(PSVC, '            created_by=(str(doc_data["created_by"]) if doc_data.get("created_by") is not None else None),\n', "")],
                               "the access check cannot see created_by: 'quarantined' for an attributed patient (as found)"),
    "C5_provenance_returned_to_clients": ([(PSCH, "    created_by: Optional[str] = Field(default=None, exclude=True)\n",
                                            "    created_by: Optional[str] = Field(default=None)\n")],
                                          "every patient response carries the creator's user id"),
    "C6_quarantine_on_the_callers_assignments": ([(PACC, "        record_unassigned = (not patient_assignments) if patient_assignments is not None else not assignments\n",
                                                   "        record_unassigned = not assignments\n")],
                                                 "'quarantined' decided on the caller's assignments, not the record's (as found)"),
    "C7_record_assignments_not_read": ([(PDEP, "    if patient is not None and created_by is None and user.role != UserRole.ADMIN:\n",
                                         "    if False:\n")],
                                       "the access check never reads the record's assignments"),
    # ── PRB-025: deleted studies and documents; SEGM.; permanent deletion ──
    "K1_deleted_studies_listed": ([(SSVC, '                    if (d.to_dict() or {}).get("status") not in self.REMOVED_STUDY_STATUSES]\n',
                                    "                    if True]\n")],
                                  "a deleted (cancelled) study stays in the patient's list (the defect as found)"),
    "K2_deleted_studies_counted": ([(PSVC, "        return total - sum(self._count(Collections.STUDIES, patient_id, s) for s in self._REMOVED_STUDY_STATUSES)\n",
                                     "        return total\n")],
                                   "a deleted study is counted in the patient's study count (as found)"),
    "K3_deleted_documents_counted": ([(PSVC, "        total = self._count(Collections.DOCUMENTS, patient_id)\n        return total - sum(",
                                       "        total = self._count(Collections.DOCUMENTS, patient_id)\n        return total\n        return total - sum(")],
                                     "a deleted (entered-in-error) document is counted"),
    "K4_zone_map_counted_as_segmentation": ([(SSVC, ' and data.get("description") != self.ZONE_MAP_DESCRIPTION:\n', ":\n")],
                                            "the MAGNIMS zone map is counted as a segmentation"),
    "K5_segmentation_count_not_computed": ([(SSVC, "            summary.segmentation_count = self._segmentation_count(doc_data)\n", "")],
                                           "no segmentation count reaches the study card (as found)"),
    "K6_explicit_status_filter_drops_deleted": ([(SSVC, "        if search.status:\n            # Get total count\n",
                                                  "        if False:\n            # Get total count\n")],
                                                "a deleted study cannot be found even when asked for by status"),
    "K7_permanent_deletion_open": ([(STR, "    if hard_delete and current_user.role != UserRole.ADMIN:\n", "    if False:\n")],
                                   "any user with access erases a study's images permanently (as found)"),
    # ── PRB-026: segmentation author; initials (backend parts) ──
    "A1_segmentation_creator_not_stored": ([(SEG, "            # PRB-026: who created it — the authenticated user passed by the route, never a client field.\n            created_by=created_by,\n", "")],
                                           "the creator of a segmentation is not stored (as found)"),
    "A2_list_item_without_name_parts": ([(PSVC, '            given_name=doc_data.get("given_name"),\n', "")],
                                        "the patient list item carries no given name (the card falls back to the full name)"),
    # ── Frontend: PRB-020 / PRB-022 sign-in page ──
    "F1_register_tab_always_shown": ([(LOGIN, "          {selfRegistration ? (\n", "          {true ? (\n")],
                                     "the Register tab is offered whatever the server says (as found)"),
    "F2_status_read_as_open": ([(REGP, "    return response?.data?.self_registration_enabled === true;\n", "    return true;\n")],
                               "any answer of the server shows the Register tab"),
    "F3_fail_open": ([(REGP, "  } catch {\n    return false;\n  }\n", "  } catch {\n    return true;\n  }\n")],
                     "the Register tab is shown when the server cannot be asked"),
    "F4_mfa_claim_back": ([(LOGIN, '              <a href="#" className="hover:text-gray-300 transition-colors">Cookie Policy</a>\n            </div>\n',
                            '              <a href="#" className="hover:text-gray-300 transition-colors">Cookie Policy</a>\n            </div>\n'
                            '            <p className="text-center text-[8px] text-gray-600 mt-2">MFA enforced · NIST SP 800-63B AAL2 · Data never leaves your jurisdiction</p>\n')],
                          "the footer claims MFA, AAL2 and data residency again (as found)"),
    "F5_hipaa_badge_back": ([(LOGIN, "                { label: 'AES-256', sub: 'At rest' },\n",
                              "                { label: 'AES-256', sub: 'At rest' },\n                { label: 'HIPAA', sub: '2026' },\n")],
                            "a HIPAA badge without any assessment (as found)"),
    # ── Frontend: PRB-025 counts ──
    "F6_segm_hard_coded": ([(CARD, "{segmentationCountText}</div>", "{0}</div>")], "the study card shows SEGM. 0 always (as found)"),
    "F7_unknown_count_shown_as_zero": ([(CARD, "String(segmentationCount) : '—';", "String(segmentationCount) : '0';")],
                                       "a count nobody computed is shown as 0"),
    "F8_patient_card_unknown_count_as_zero": ([(PCARD, "Number.isFinite(n) ? String(n) : '—');", "Number.isFinite(n) ? String(n) : '0');")],
                                              "the patient card shows 0 for a count the server could not compute"),
    # ── Frontend: PRB-026 initials ──
    "F9_card_first_and_last_word": ([(PCARD, "const getInitials = (patient: Patient): string => patientInitials(patient);",
                                      "const getInitials = (patient: Patient): string => { const p = (patient.full_name || '').trim().split(/\\s+/); "
                                      "return (p[0][0] + p[p.length - 1][0]).toUpperCase(); };")],
                                    "the list card uses the first and last word of the full name: 'DD' (as found)"),
    "F10_banner_first_two_words": ([(BANNER, "          {patientInitials(patient)}\n",
                                     "          {patient.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}\n")],
                                   "the record page uses the first two words: a title becomes an initial (as found)"),
    "F11_rule_ignores_name_parts": ([(PDISP, "  if (given && family) return (given + family).toLocaleUpperCase();\n", "")],
                                    "the shared rule reads the full name instead of the given and family name"),
    "F12_punctuation_as_initial": ([(PDISP, "const LETTER = /\\p{L}/u;\n", "const LETTER = /\\S/u;\n")],
                                   "a bracket or quote becomes an initial"),
    # ── Frontend: PRB-026 author ──
    "F13_hook_placeholder_author": ([(HOOK, "          created_by: recordedAuthor(currentSegmentation.metadata),\n",
                                      "          created_by: 'current_user',\n")],
                                    "the open segmentation shows 'current_user' as its author (as found)"),
    "F14_panel_placeholder_author": ([(PANEL, "    created_by: recordedAuthor(seg.metadata),", "    created_by: 'current_user',")],
                                     "the saved-segmentation list shows 'current_user' as the author (as found)"),
    "F15_no_author_not_recorded_text": ([(AUTHOR, "    t('segmentation.authorNotRecorded', 'Author not recorded')\n", "    ''\n")],
                                        "a segmentation without a recorded author shows an empty author"),
    # ── Frontend: PRB-026 interface language ──
    "F16_badge_not_translated": ([(ROW, "            {t(`provenance.${prov.key}`, prov.label)}\n", "            {prov.label}\n")],
                                 "the provenance badge ignores the interface language"),
    "F17_english_locale_in_spanish": ([(EN, '    "expert": "Expert",\n', '    "expert": "Experto",\n')],
                                      "the English interface shows the Spanish badge 'Experto' (as found)"),
    "F18_niivue_loading_in_spanish": ([(NIIVUE, "          {t('viewer.loadingVolume', 'Loading volume…')}\n", "          Cargando volumen…\n")],
                                      "'Cargando volumen…' in every interface language (as found)"),
    "F19_gpu_viewer_loading_in_spanish": ([(IV2D, "{t('viewer.loadingGpuViewer', 'Loading GPU viewer…')}", "Cargando visor GPU…")],
                                          "'Cargando visor GPU…' in every interface language (as found)"),
    "F20_conformal_title_in_spanish": ([(CONF, "{t('conformal.title', 'Per-lesion second reader (CALM-MS)')}",
                                         "Segunda lectura por lesión (CALM-MS)")],
                                       "the CALM-MS panel in Spanish in every interface language (as found)"),
    "F21_german_key_missing": ([(DE, '    "loadingVolume": "Volumen wird geladen…",\n', "")],
                               "a key missing in German: the German interface falls back to English"),
}


def offline_env(tmp):
    """PRB-002: backend tests never reach a real cloud service or the model provider."""
    env = dict(os.environ)
    for name in ("ANTHROPIC_API_KEY", "FIRESTORE_EMULATOR_HOST"):
        env.pop(name, None)
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(tmp, "no-such-credentials.json"),
                "CLOUDSDK_CONFIG": os.path.join(tmp, "empty-gcloud"), "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests"})
    os.makedirs(env["CLOUDSDK_CONFIG"], exist_ok=True)
    return env


def run_backend(env):
    r = subprocess.run([PY, "-m", "pytest", *BACKEND_TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                       timeout=1200)
    f = re.search(r"(\d+) failed", r.stdout)
    p = re.search(r"(\d+) passed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"suite": "backend", "exit": r.returncode, "failed": int(f.group(1)) if f else 0,
            "passed": int(p.group(1)) if p else 0, "errors": int(e.group(1)) if e else 0,
            "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))}


def run_frontend():
    out = os.path.join(tempfile.gettempdir(), "prb020_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run("npx vitest run " + " ".join(FRONTEND_TESTS) + f" --pool=threads --reporter=json --outputFile={out}",
                       cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1200)
    if not os.path.exists(out):
        return {"suite": "frontend", "exit": r.returncode, "failed": 0, "passed": 0, "errors": 1,
                "failing_tests": [], "error_files": ["vitest produced no report"]}
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    return {"suite": "frontend", "exit": r.returncode, "failed": sum(a["status"] == "failed" for a in res),
            "passed": sum(a["status"] == "passed" for a in res),
            "errors": sum(1 for f in d["testResults"] if f["status"] == "failed" and not f["assertionResults"]),
            "failing_tests": [a["title"] for a in res if a["status"] == "failed"]}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_RAW = {}


def _restore():
    for p, b in _RAW.items():
        try:
            if open(p, "rb").read() != b:
                open(p, "wb").write(b)
        except OSError:
            open(p, "wb").write(b)


def _on_signal(signum, _frame):
    _restore()
    raise SystemExit(f"interrupted by signal {signum}; every mutated file restored")


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    files = sorted({e[0] for edits, _w in M.values() for e in edits})
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *files], capture_output=True, text=True).stdout
    if dirty.strip():
        raise SystemExit(f"uncommitted changes in {dirty.split()}: commit them first (the script restores bytes)")
    _RAW.update({p: open(p, "rb").read() for p in files})
    atexit.register(_restore)
    for sig in ("SIGTERM", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), _on_signal)
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in _RAW.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in _RAW.items()}
    for name, (edits, _w) in M.items():
        for path, anchor, _r in edits:
            c = text[path].count(anchor)
            assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"
    tests = [f"backend/{t.split('::')[0]}" for t in BACKEND_TESTS] + [f"frontend/{t}" for t in FRONTEND_TESTS]
    previous = json.load(open(OUT, encoding="utf-8")) if only and os.path.exists(OUT) else {"mutations": {}}
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "tree": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
           "method": "one mutation at a time; each anchor asserted to occur exactly once (LF text); the bound tests of "
                     "the mutated side run (backend pytest offline per PRB-002; frontend vitest --pool=threads, JSON "
                     "reporter); original bytes restored after each mutation, on exit and on signals, and verified at "
                     "the end; the baseline must pass first",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: sha(text[p]) for p in files},
           "test_sha256": {t: sha(open(t, encoding="utf-8").read().replace("\r\n", "\n")) for t in sorted(set(tests))},
           "backend_tests": BACKEND_TESTS, "frontend_tests": FRONTEND_TESTS, "baseline": {}, "mutations": {}}
    with tempfile.TemporaryDirectory() as tmp:
        env = offline_env(tmp)
        res["baseline"] = {"backend": run_backend(env), "frontend": run_frontend()}
        print("baseline", {k: (v["passed"], v["failed"], v["errors"]) for k, v in res["baseline"].items()}, flush=True)
        if any(b["failed"] or b["errors"] or not b["passed"] for b in res["baseline"].values()):
            raise SystemExit("the baseline must pass before the mutations mean anything")
        try:
            for name, (edits, what) in M.items():
                if only and not name.startswith(only) and name in previous["mutations"]:
                    res["mutations"][name] = previous["mutations"][name]
                    continue
                touched = {}
                for path, anchor, repl in edits:
                    touched[path] = touched.get(path, text[path]).replace(anchor, repl, 1)
                for path, mutated in touched.items():
                    assert mutated != text[path], name
                    open(path, "w", encoding="utf-8", newline=eol[path]).write(mutated)
                out = run_frontend() if all(p.startswith("frontend/") for p in touched) else run_backend(env)
                out.update({"reintroduces": what, "applied": True,
                            "executed": datetime.datetime.now().isoformat(timespec="seconds"),
                            "detected": bool(out["failed"] or out["errors"] or out["exit"] != 0)})
                res["mutations"][name] = out
                for path in touched:
                    open(path, "wb").write(_RAW[path])
                print(f"{name:44s} [{out['suite']}] detected={out['detected']} {out['failing_tests'][:2]}", flush=True)
        finally:
            _restore()
        for p in files:   # the restore is byte-exact
            assert open(p, "rb").read() == _RAW[p], p
        res["restored"] = {"backend": run_backend(env), "frontend": run_frontend()}
    undetected = sorted(n for n, v in res["mutations"].items() if not v["detected"])
    res["summary"] = {"mutations": len(res["mutations"]), "detected": len(res["mutations"]) - len(undetected),
                      "undetected": undetected}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    rb, rf = res["restored"]["backend"], res["restored"]["frontend"]
    print(f"restored backend {rb['passed']} passed / {rb['failed']} failed | frontend {rf['passed']} passed / "
          f"{rf['failed']} failed | detected {res['summary']['detected']} of {res['summary']['mutations']} -> {OUT}")
    bad = any(r["failed"] or r["errors"] for r in (rb, rf))
    return 1 if undetected or bad else 0


if __name__ == "__main__":
    sys.exit(main())
