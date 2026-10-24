"""Negative controls for CAPA-014 — de-identification of the AI report draft (RC-064, RC-065, RC-066; HAZ-016).

Each mutation re-introduces ONE defect CAPA-014 removed (the removal step bypassed — the defect as
found —, one removal rule disabled, accents or German spellings not matched, measurements removed
as numbers, the exact age sent, a request sent without a patient reference, without authorization
or with an unreadable or incomplete record, the residual check or one of its categories removed,
the payload logged, the false header claim back, the panel note or its translations missing, the
segmentation not sent by the panel or the assistant) — in the real source, one at a time. The script
asserts every anchor occurs exactly once (the sabotage really was applied), runs the bound tests of
the side it mutated (backend: pytest; frontend: vitest, JSON reporter), records the failing test
names and restores the exact original bytes.

Run from the repository root (needs backend/venv or the current Python with the backend
requirements, and frontend/node_modules):
    python scripts/safety/capa014_negative_controls.py            # every mutation
    python scripts/safety/capa014_negative_controls.py --only D   # re-run the mutations whose name
                                                                  # starts with D; others kept from
                                                                  # the existing record
Output: docs/iec62304/records/risk_verification/CAPA-014_negative_controls_2026-10-24.json
(each mutation carries the time it was executed and the SHA-256 of the tests it ran).
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
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = "docs/iec62304/records/risk_verification/CAPA-014_negative_controls_2026-10-24.json"
BACKEND_TESTS = ["tests/unit/test_capa014_report_deidentification.py",
                 "tests/unit/test_capa009_object_authorization_everywhere.py",
                 "tests/unit/test_capa008_assistant_read_only.py",
                 "tests/unit/test_brain_report_service.py"]
FRONTEND_TESTS = ["src/components/AIReportPanel.capa014.test.tsx"]

DI = "backend/app/services/report_deidentification.py"
BRS = "backend/app/services/brain_report_service.py"
AIR = "backend/app/api/routes/ai_report.py"
MCPS = "backend/app/mcp/ms_clinical_server.py"
PANEL = "frontend/src/components/AIReportPanel.tsx"
CLIENT = "frontend/src/api/aiReport.ts"
EN = "frontend/src/i18n/locales/en.json"
ES = "frontend/src/i18n/locales/es.json"
DE = "frontend/src/i18n/locales/de.json"


def _note_line(path):
    lines = [ln for ln in open(path, encoding="utf-8").read().replace("\r\n", "\n").split("\n")
             if ln.startswith('    "deidentificationNote": ')]
    assert len(lines) == 1, path
    return lines[0] + "\n"


EN_NOTE, ES_NOTE, DE_NOTE = _note_line(EN), _note_line(ES), _note_line(DE)

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── RC-064: the single removal step and its rules ──
    "D1_removal_step_and_residual_check_bypassed": (
        [(BRS, "        clean = deidentify_report_input(findings, volumetry, identifiers)\n",
          "        clean = type('C', (), {'findings': findings, 'volumetry': volumetry, 'redactions': {}})()\n"),
         (BRS, "        assert_no_residual_identifiers(user_prompt, identifiers)\n", "")],
        "the findings forwarded verbatim (the defect as found)"),
    "D2_removal_step_bypassed": (
        [(BRS, "        clean = deidentify_report_input(findings, volumetry, identifiers)\n",
          "        clean = type('C', (), {'findings': findings, 'volumetry': volumetry, 'redactions': {}})()\n")],
        "no removal step (only the residual check left)"),
    "D3_names_rule_removed": ([(DI, '        if c.names:\n            s = _substitute(s, c.names, _fixed(NAME, "name"), n)\n', "")],
                              "the patient's names from the record not removed"),
    "D4_accents_and_case_not_folded": ([(DI, '    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()\n',
                                         "    return ch\n")],
                                       "matching sensitive to case and accents ('PÉREZ' != 'Perez')"),
    "D5_no_german_spellings": ([(DI, '                fold(low.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")),\n'
                                     '                fold(low).replace("ae", "a").replace("oe", "o").replace("ue", "u")}\n',
                                 "                }\n")],
                               "'Müller' not matched as 'Mueller'"),
    "D6_particles_removed_alone": ([(DI, "            if len(fold(t)) >= 2 and fold(t) not in NAME_PARTICLES:\n",
                                     "            if len(fold(t)) >= 2:\n")],
                                   "'de', 'la' removed everywhere for a compound surname (clinical text damaged)"),
    "D7_record_numbers_rule_removed": ([(DI, '        if c.record_numbers:\n            s = _substitute(s, c.record_numbers, _fixed(RECORD_NUMBER, "record_number"), n)\n', "")],
                                       "the record number from the record not removed"),
    "D8_record_number_separators_required": ([(DI, '    return r"[\\s\\-/_#:]{0,2}".join(re.escape(c) for c in chars)\n',
                                               '    return "".join(re.escape(c) for c in chars)\n')],
                                             "'mrn 2025 0042' / 'PAT 77123' not matched"),
    "D9_record_phone_rule_removed": ([(DI, '        if c.phones:\n            s = _substitute(s, c.phones, _fixed(PHONE, "phone"), n)\n', "")],
                                     "the record's phone numbers not removed in formats the pattern misses"),
    "D10_record_address_rule_removed": ([(DI, '        if c.address:\n            s = _substitute(s, c.address, _fixed(ADDRESS, "address"), n)\n', "")],
                                        "address, city and postal code from the record not removed"),
    "D11_birth_date_not_recognised": ([(DI, '        if _is_birth_date(precision, d, self.ids.birth_date):\n            return BIRTH_DATE, "birth_date"\n', "")],
                                      "the birth date treated as an ordinary date"),
    "D12_birth_context_rule_removed": ([(DI, '        s = _substitute(s, BIRTH_CONTEXT_RE, _fixed(BIRTH_DATE, "birth_date"), n, group="when")\n', "")],
                                       "'DOB: 1978' kept"),
    "D13_dates_kept": ([(DI, "        s = _substitute(s, DATE_RE, self._date, n)\n", "")], "exact dates sent"),
    "D14_dates_not_intervals": ([(DI, '        return f"[date {index} = date 1 {sign} {amount} {unit}]"\n',
                                  "        return DATE_REMOVED\n")],
                                "dates removed without the interval the report needs"),
    "D15_email_rule_removed": ([(DI, '        s = _substitute(s, EMAIL_RE, _fixed(EMAIL, "email"), n)\n', "")], "e-mail addresses sent"),
    "D16_phone_pattern_removed": ([(DI, "        s = _substitute(s, PHONE_RE, self._phone, n)\n", "")], "phone numbers not in the record sent"),
    "D17_id_word_rule_removed": ([(DI, '        s = _substitute(s, ID_WORD_RE, self._id_word, n, group="val")\n', "")],
                                 "short numbers after MRN / Fallnummer / NHC sent"),
    "D18_id_number_rule_removed": ([(DI, "        s = _substitute(s, ID_TOKEN_RE, self._id_token, n)\n", "")],
                                   "long ID-like numbers (accession, UID) sent"),
    "D19_measurements_removed_as_ids": ([(DI, "        if sum(ch.isdigit() for ch in token) < 6 or _UNIT_AHEAD.match(m.string, m.end()):\n",
                                          "        if sum(ch.isdigit() for ch in token) < 6:\n")],
                                        "a measurement with its unit removed as an ID number (clinical content lost)"),
    "D20_exact_age_sent": ([(DI, "                cleaned[key] = (key, band)\n", "                cleaned[key] = (key, value)\n")],
                           "the exact age sent instead of the 5-year band"),
    "D21_own_age_in_text_kept": ([(DI, '        if c.age:\n            s = _substitute(s, c.age, self._age, n, group="age")\n', "")],
                                 "'48 years' (the patient's own age) kept"),
    "D22_age_phrases_kept": ([(DI, '        s = _substitute(s, AGE_PHRASE_RE, self._age, n, group="age")\n', "")],
                             "'47 años de edad' kept"),
    "D23_keys_not_scrubbed": ([(DI, "            return {self.text(k) if isinstance(k, str) else k: self.value(x) for k, x in v.items()}\n",
                                "            return {k: self.value(x) for k, x in v.items()}\n")],
                              "identifiers in dictionary keys (region names) sent"),
    "D24_titled_names_kept": ([(DI, '        s = _substitute(s, TITLED_PERSON_RE, _fixed(PERSON, "person_name"), n, folded=False)\n', "")],
                              "'Dr. Gregory House' sent"),
    "D25_institutions_kept": ([(DI, '        s = _substitute(s, INSTITUTION_AFTER_RE, _fixed(INSTITUTION, "institution"), n, folded=False)\n', "")],
                              "'Hospital Universitario San Ignacio' sent"),
    "D26_streets_kept": ([(DI, '        s = _substitute(s, STREET_RE, _fixed(ADDRESS, "address"), n, folded=False)\n', "")],
                         "street addresses not in the record sent"),
    # Added after the first (dry) run: over-removal guards and the rules it showed untested.
    "D27_year_ranges_removed_as_ids": ([(DI, '        if _YEARS_ONLY.fullmatch(token):\n            return None                        # a year range ("2019-2021"): clinical history\n', "")],
                                       "'2019-2021' (treatment period) removed as an ID number"),
    "D28_year_lists_removed_as_phones": ([(DI, '        if _YEARS_ONLY.fullmatch(s.strip()):\n            return None                        # a list of years: clinical history\n', "")],
                                         "'MRI 2019 2020 2021' removed as a phone number"),
    "D29_german_nie_as_id_word": ([(DI, "pid|dni|c\\.c\\.|cc|", "pid|dni|nie|nif|c\\.c\\.|cc|")],
                                  "German 'nie' (never) read as an ID word, the following number removed"),
    "D30_clinical_ring_as_street": ([(DI, "(?:straße|strasse|str\\.|weg|allee|platz|gasse)", "(?:straße|strasse|str\\.|weg|allee|platz|gasse|ring|damm)")],
                                    "'Kontrastmittelring 5 mm' removed as a street address"),
    "D31_institution_before_rule_removed": ([(DI, '        s = _substitute(s, INSTITUTION_BEFORE_RE, _fixed(INSTITUTION, "institution"), n, folded=False)\n', "")],
                                            "'Mayo Clinic' sent"),
    "D32_phone_inside_a_token": ([(DI, 'PHONE_RE = re.compile(r"(?<![\\w+.\\-])', 'PHONE_RE = re.compile(r"(?<![\\w+])')],
                                 "part of an ID ('A-20251012-0042') read as a phone, the rest sent"),
    # ── RC-065: fail closed ──
    "F1_route_needs_no_segmentation": ([(AIR, "    if not request.segmentation_id:\n        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=SUBJECT_REQUIRED_DETAIL)\n", "")],
                                       "a request without patient reference reaches the provider"),
    "F2_route_does_not_authorize": ([(AIR, "    patient_id = await authorize_segmentation_id(request.segmentation_id, current_user)\n",
                                      "    from app.security.resource_access import resolve_segmentation_patient_id, _segmentation_service\n"
                                      "    patient_id = await resolve_segmentation_patient_id(request.segmentation_id, _segmentation_service())\n")],
                                    "any caller drafts a report on any patient's segmentation"),
    "F3_unreadable_record_ignored": ([(AIR, "    return PatientIdentifiers.from_record(record)\n",
                                       "    return PatientIdentifiers.from_record(record or {'mrn': 'NONE', 'given_name': 'x', "
                                       "'family_name': 'y', 'birth_date': '1900-01-01'})\n")],
                                     "the provider is called although the patient record could not be read"),
    "F4_incomplete_record_accepted": ([(DI, "        if not (mrn and given and family and isinstance(birth, date)):\n",
                                        "        if not (mrn or given or family):\n")],
                                      "a record without record number, name or birth date accepted"),
    "F5_service_sends_without_identifiers": ([(BRS, "        if not isinstance(identifiers, PatientIdentifiers):\n", "        if False:\n"),
                                              (DI, "    if not isinstance(identifiers, PatientIdentifiers):\n", "    if False:\n")],
                                             "the service builds and sends a prompt without identifiers"),
    "F6_residual_check_removed": ([(BRS, "        assert_no_residual_identifiers(user_prompt, identifiers)\n", "")],
                                  "no check of the final prompt"),
    "F7_residual_name_check_removed": ([(DI, '    if c.residual_name and c.residual_name.search(folded):\n        found.append("name")\n', "")],
                                       "the residual check misses the patient's name"),
    "F8_residual_record_number_check_removed": ([(DI, '    if c.residual_record_numbers and c.residual_record_numbers.search(folded):\n        found.append("record_number")\n', "")],
                                                "the residual check misses the record number"),
    "F9_residual_birth_date_check_removed": ([(DI, '    if any(_is_birth_date(p, d, identifiers.birth_date) for p, d in find_dates(text) if p != "noyear"):\n        found.append("birth_date")\n', "")],
                                             "the residual check misses the birth date"),
    "F10_residual_email_check_removed": ([(DI, '    if any(fold(e) in folded for e in identifiers.emails):\n        found.append("email")\n', "")],
                                         "the residual check misses the e-mail address"),
    "F11_residual_phone_check_removed": ([(DI, '    if c.phones and c.phones.search(folded):\n        found.append("phone")\n', "")],
                                         "the residual check misses the phone number"),
    "F12_assistant_omits_segmentation": ([(MCPS, '            "segmentation_id": segmentation_id,\n', "")],
                                         "the assistant's report tool sends no segmentation (every draft refused)"),
    # ── RC-066: records and disclosure ──
    "L1_raw_findings_logged": ([(BRS, '                   "redactions": dict(clean.redactions)},\n',
                                 '                   "redactions": dict(clean.redactions), "findings": findings},\n')],
                               "the raw findings written to the log"),
    "L2_prompt_logged": ([(BRS, '                   "redactions": dict(clean.redactions)},\n',
                           '                   "redactions": dict(clean.redactions), "prompt": user_prompt},\n')],
                         "the prompt (clinical free text) written to the log"),
    "L3_counts_not_logged": ([(BRS, '                   "redactions": dict(clean.redactions)},\n',
                               '                   "redactions": {}},\n')],
                             "no record of what was removed"),
    "L4_false_header_claim": ([(BRS, "Data sent to the model provider (CAPA-014; RC-064, RC-065, RC-066; HAZ-016):\n",
                                "HIPAA Compliance:\n- No names, IDs, or dates are sent to the external API\n"
                                "Data sent to the model provider (CAPA-014; RC-064, RC-065, RC-066; HAZ-016):\n")],
                              "the service header claims again what it did not do"),
    "U1_note_not_shown": ([(PANEL, "                {t('report.deidentificationNote')}\n", "                {''}\n")],
                          "no note next to the draft button"),
    "U2_note_english_in_spanish": ([(ES, ES_NOTE, '    "deidentificationNote": ' + EN_NOTE.split(": ", 1)[1])],
                                   "the Spanish note is the English text"),
    "U3_note_missing_in_german": ([(DE, DE_NOTE, "")], "no German note (the key is shown)"),
    "U4_note_away_from_button": ([(PANEL, "              {/* Generate button */}\n", "              <span />\n              {/* Generate button */}\n")],
                                 "the note no longer directly above the draft button"),
    "U5_panel_omits_segmentation": ([(PANEL, "      ...(activeSegId ? { segmentation_id: activeSegId } : {}),\n", "")],
                                    "the panel sends no segmentation (every draft refused)"),
    "U6_client_claims_hipaa": ([(CLIENT, "   * Generate a structured brain MRI report using Claude API.\n",
                                 "   * Generate a structured brain MRI report using Claude API.\n   * HIPAA compliant: only de-identified findings are sent.\n")],
                               "the API client claims HIPAA compliance again"),
}

# Mutations that are NOT defects (equivalent code), stated rather than claimed as tested.
EXPECTED_UNDETECTED = {}


def run_backend():
    r = subprocess.run([PY, "-m", "pytest", *BACKEND_TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ))
    f = re.search(r"(\d+) failed", r.stdout)
    p = re.search(r"(\d+) passed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"suite": "backend", "failed": int(f.group(1)) if f else 0, "passed": int(p.group(1)) if p else 0,
            "errors": int(e.group(1)) if e else 0, "skipped": 0,
            "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))}


def run_frontend():
    out = os.path.join(tempfile.gettempdir(), "capa014_vitest.json")
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
    tests = BACKEND_TESTS + [f"frontend/{t}" for t in FRONTEND_TESTS]
    test_sha = {t: sha(open(t if t.startswith("frontend/") else os.path.join("backend", t),
                            encoding="utf-8").read().replace("\r\n", "\n")) for t in tests}
    previous = json.load(open(OUT, encoding="utf-8")) if only and os.path.exists(OUT) else {"mutations": {}}
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "method": "one mutation at a time; each anchor asserted to occur exactly once; the bound tests of the "
                     "mutated side are run (backend pytest, frontend vitest JSON reporter)",
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
                if current == kept.get("test_sha256") and current:   # same tests as now: the result still holds
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
            print(f"{name:45s} [{out['suite']}] {out['failed']} failed / {out['errors']} errors / {out['passed']} passed", flush=True)
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
