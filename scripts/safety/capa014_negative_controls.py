"""Negative controls for CAPA-014 (redesign) — no free text leaves the application (RC-064, RC-065, RC-066; HAZ-016).

Each mutation re-introduces ONE defect the redesign removes, or disables one sub-control, in the real source,
one at a time: the structured payload bypassed or leaking (free text, unlisted labels, non-numbers, exact age,
"90 or older" missing, sex other than M/F, payload in the system prompt); the tripwire removed or blind to one
identifier form (names, names written together, pairs of the device's own words, particle surnames, record
numbers with separators, birth date, phone, e-mail, generic patterns, format characters, look-alike letters,
German spellings, the length cap, a quadratic pattern) or over-blocking (the device's own words); fail closed
undone (no segmentation, no authorization, unreadable or incomplete record, service without identifiers,
assistant without segmentation); the typed text not merged, merged before the disclaimer, the model not told;
the payload or prompt logged, no counts; false claims back (service header, README, API client, viewer
footer); the panel note missing, untranslated or away from the button. Second independent review (N1-N9):
the typed text not quoted, quoted with a fixed fence, not closed, the model text without its fixed heading,
the viewer loading images; the application's label names missing from the vocabulary, unlisted labels
numbered per occurrence, their names not shown in the draft; "not available" printed as 0; no plausibility
range; the instruction sent although nothing was typed; the system templates' words exempt; the numeric
record number matched inside measurements; the digits of a prefixed record number not checked; pairs and
joined words of the device's own text reported; the RC-007 claim back in the record generator; the stale
model name back in the technical documentation; the DIS evaluation state dropped, or a DIS not evaluated
sent as "NOT MET" (coordination with PR #68). The script asserts every anchor occurs
exactly once, runs the bound tests of the mutated side (backend pytest; frontend vitest JSON reporter),
records the failing test names and restores the exact original bytes.

Run from the repository root (backend/venv or the current Python with the backend requirements, and
frontend/node_modules). PRB-002: run with GOOGLE_APPLICATION_CREDENTIALS pointing to a missing file,
CLOUDSDK_CONFIG to an empty folder, GOOGLE_CLOUD_PROJECT=mstool-offline-tests and ANTHROPIC_API_KEY unset;
the script also sets these for the test processes it starts.
    python scripts/safety/capa014_negative_controls.py            # every mutation
    python scripts/safety/capa014_negative_controls.py --only T   # re-run mutations starting with T
Output: docs/iec62304/records/risk_verification/CAPA-014_review2_negative_controls_2026-10-24.json
(the first redesign's run, 52 mutations, is kept as CAPA-014_negative_controls_2026-10-24.json)
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
OUT = "docs/iec62304/records/risk_verification/CAPA-014_review2_negative_controls_2026-10-24.json"
BACKEND_TESTS = ["tests/unit/test_capa014_report_provider_payload.py",
                 "tests/unit/test_capa009_object_authorization_everywhere.py",
                 "tests/unit/test_capa008_assistant_read_only.py",
                 "tests/unit/test_brain_report_service.py"]
FRONTEND_TESTS = ["src/components/AIReportPanel.capa014.test.tsx"]
EMPTY = os.path.join(tempfile.gettempdir(), "capa014-empty-gcloud")
os.makedirs(EMPTY, exist_ok=True)
OFFLINE = {**os.environ, "GOOGLE_APPLICATION_CREDENTIALS": os.path.join(EMPTY, "missing.json"),
           "CLOUDSDK_CONFIG": EMPTY, "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests"}
OFFLINE.pop("ANTHROPIC_API_KEY", None)

G = "backend/app/services/report_payload_guard.py"
BRS = "backend/app/services/brain_report_service.py"
AIR = "backend/app/api/routes/ai_report.py"
MCPS = "backend/app/mcp/ms_clinical_server.py"
README = "README.md"
PANEL = "frontend/src/components/AIReportPanel.tsx"
VIEWER = "frontend/src/components/ReportViewerModal.tsx"
CLIENT = "frontend/src/api/aiReport.ts"
EN = "frontend/src/i18n/locales/en.json"
ES = "frontend/src/i18n/locales/es.json"
DE = "frontend/src/i18n/locales/de.json"
GEN = "docs/iec62304/generate_audit_records.py"
TECHDOC = "docs/Technical_Documentation_MS_Brain_MRI_Viewer.md"


def _line(path, prefix):
    lines = [ln for ln in open(path, encoding="utf-8").read().replace("\r\n", "\n").split("\n") if ln.startswith(prefix)]
    assert len(lines) == 1, (path, prefix)
    return lines[0] + "\n"


EN_NOTE, ES_NOTE, DE_NOTE = (_line(p, '    "deidentificationNote": ') for p in (EN, ES, DE))
SKIP_GENERIC = ("    for category, pattern in _GENERIC.items():\n        if pattern.search(norm):\n")


def skip_generic(*names):
    cond = " and ".join(f'category != "{n}"' for n in names)
    return (G, SKIP_GENERIC, f"    for category, pattern in _GENERIC.items():\n        if {cond} and pattern.search(norm):\n")


M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── RC-064: structured payload only ──
    "P1_payload_bypassed": ([(BRS, "        payload = provider_payload(findings, volumetry)\n",
                              "        payload = type(\"P\", (), {\"findings\": findings, \"volumetry\": volumetry, \"withheld\": {}, "
                              "\"unlisted\": {}})()\n")],
                            "the request's findings go to the prompt builder as received"),
    "P2_builder_prints_free_text": ([(BRS, "        if findings.get(\"clinician_entry\") is True:\n            parts.append(CLINICIAN_TEXT_INSTRUCTION)\n",
                                      "        if findings.get(\"clinician_entry\") is True:\n            parts.append(CLINICIAN_TEXT_INSTRUCTION)\n        if findings.get(\"clinical_indication\"):\n"
                                      "            parts.append(f\"Clinical indication: {findings['clinical_indication']}\")\n")],
                                    "the prompt builder prints the clinical indication again"),
    "P3_payload_copies_free_text": ([(G, '    if f.get("patient_sex") in ("M", "F"):\n        out["patient_sex"] = f["patient_sex"]\n',
                                      '    if f.get("patient_sex") in ("M", "F"):\n        out["patient_sex"] = f["patient_sex"]\n'
                                      '    out.update({k: f[k] for k in FREE_TEXT_FIELDS if k in f})\n')],
                                    "the free-text fields copied into the payload"),
    "P4_any_label_accepted": ([(G, '    """The canonical label when `value` is one of the device\'s labels, otherwise None."""\n',
                                '    """The canonical label when `value` is one of the device\'s labels, otherwise None."""\n'
                                '    return value if isinstance(value, str) else None\n')],
                              "labels outside the device's vocabulary sent"),
    "P5_counts_not_coerced": ([(G, "        n = _number(value)\n        if n is None:\n            if value is not None:\n",
                                "        n = _number(value)\n        if n is None:\n            return value\n            if value is not None:\n")],
                              "any value printed where a number is expected (free text through number fields)"),
    "P6_any_sex_sent": ([(G, '    if f.get("patient_sex") in ("M", "F"):\n', '    if f.get("patient_sex"):\n'),
                         (BRS, '        if findings.get("patient_sex") in ("M", "F"):\n', '        if findings.get("patient_sex"):\n')],
                        "any sex value sent, shown as Female"),
    "P7_exact_age_sent": ([(G, '        out["patient_age"] = band\n', '        out["patient_age"] = f.get("patient_age")\n')],
                          "the exact age sent instead of the 5-year band"),
    "P8_no_90_or_older": ([(G, '    if years >= 90:\n        return "90 or older"\n', "")],
                          "ages of 90 and over sent in 5-year bands (93 -> 90-94)"),
    "P9_payload_in_system_prompt": ([(BRS, "                system=system_prompt,\n", "                system=system_prompt + user_prompt,\n")],
                                    "the system prompt no longer the fixed template"),
    # second independent review (N2, N3, N4)
    "P10_app_label_names_missing": ([(G, "    labels |= set(_EXTRA_LABELS) | set(APP_LABEL_NAMES)\n", "    labels |= set(_EXTRA_LABELS)\n")],
                                    "the application's own labels ('MS Lesion (Active)') sent as unlisted"),
    "P11_unlisted_numbered_per_occurrence": ([(G, "        if written not in self.unlisted:\n"
                                                  "            self.unlisted[written] = f\"[unlisted label {len(self.unlisted) + 1}]\"\n"
                                                  "        return self.unlisted[written]\n",
                                               "        self.unlisted[f\"{written}#{len(self.unlisted)}\"] = f\"[unlisted label {len(self.unlisted) + 1}]\"\n"
                                               "        return f\"[unlisted label {len(self.unlisted)}]\"\n")],
                                             "groups and rows no longer match: one label gets several numbers"),
    "P12_unlisted_names_not_shown": ([(AIR, "            unlisted_note(unlisted, request.language))}\n", "            None)}\n")],
                                     "the draft does not say which label each placeholder stands for"),
    "P13_not_available_printed_as_zero": ([(G, "            return NOT_AVAILABLE if required else None\n        if not low",
                                            "            return 0 if required else None\n        if not low")],
                                          "a value that is not a number reported as 0"),
    "P14_no_plausibility_range": ([(G, "        if not low <= n <= high:\n", "        if False:\n")],
                                  "dates, record numbers and phone numbers in number fields sent"),
    # coordination with PR #68 (PRB-003): the DIS evaluation state
    "P15_dis_not_evaluated_as_not_met": ([(G, '        if state not in (None, DIS_EVALUATED) or not isinstance(dis.get("dis_met"), bool):\n',
                                           "        if False:\n")],
                                         "a DIS not evaluated or without a conclusion sent as 'NOT MET'"),
    "P16_dis_evaluated_state_dropped": ([(G, "            o[\"evaluation_status\"] = DIS_EVALUATED     # kept as received; never invented for a block without it\n",
                                          "            pass\n")],
                                        "the 'evaluated' DIS state lost in the payload (every DIS not evaluated after PR #68)"),
    "P17_builder_prints_not_evaluated_as_not_met": ([(BRS, '        if (findings.get("dis_assessment") or {}).get("evaluation_status") == "not_evaluated":\n',
                                                      '        if False:\n')],
                                                    "the prompt builder prints 'NOT MET' for a DIS not evaluated"),
    # ── RC-065: detection-only tripwire and fail closed ──
    "T1_tripwire_removed": ([(BRS, "        assert_prompt_carries_no_identifier(user_prompt, identifiers)\n", "")],
                            "no check of the final prompt"),
    "T2_name_check_removed": ([(G, "            if s in unique or (len(s) >= 4 and any(s in w for w in unique if w not in safe_words)):\n",
                                "            if False:\n")],
                              "the patient's names, contact, city and street not looked for"),
    "T3_names_written_together_missed": ([(G, "            if s in unique or (len(s) >= 4 and any(s in w for w in unique if w not in safe_words)):\n",
                                           "            if s in unique:\n")],
                                         "'Fuentemüller', 'delaFuente' not found"),
    "T4_device_words_reported": ([(G, "            if s in safe_words:\n                continue\n", "")],
                                 "a patient named White blocks every draft ('Deep White Matter')"),
    "T5_pair_check_removed": ([(G, '    if "name" not in found and (any(w in joined and w not in safe_words for w in unique)\n'
                                   '                                or any((a, b) in pairs and (a, b) not in safe_pairs\n'
                                   '                                       for a, b in zip(words, words[1:]))):\n'
                                   '        found.append("name")\n', "")],
                              "names made only of the device's words ('Black White') not found"),
    "T6_record_number_check_removed": ([(G, '        if pattern and pattern.search(norm):\n            found.append("record_number")\n',
                                         '        if False:\n            found.append("record_number")\n')],
                                       "the record number not looked for"),
    "T7_record_number_separators_required": ([(G, '    return re.compile(r"(?<![a-z0-9])" + r"[\\s\\-./_#:]{0,3}".join(re.escape(c) for c in chars) + r"(?![a-z0-9])")\n',
                                               '    return re.compile(r"(?<![a-z0-9])" + "".join(re.escape(c) for c in chars) + r"(?![a-z0-9])")\n')],
                                             "'H C 7 7 8 8 1 2', 'MRN 2025 0042' not found"),
    "T8_birth_date_check_removed": ([(G, '    if any(p.search(norm) for p in _birth_patterns(ids.birth_date)):\n        found.append("birth_date")\n', "")],
                                    "'geb. 9.11.', \"born '75\" not found"),
    "T9_record_phone_check_removed": ([(G, '    if ids.phones and any(p in digits for digits in runs for p in ids.phones):\n        found.append("phone")\n', "")],
                                      "the patient's short phone forms ('01 40400') not found"),
    "T10_email_checks_removed": ([(G, '    if any(e in norm for e in ids.emails):\n        found.append("email")\n', ""),
                                  skip_generic("email")], "e-mail addresses not found"),
    "T11_generic_email_removed": ([skip_generic("email")], "other people's e-mail addresses not found"),
    "T12_generic_date_removed": ([skip_generic("date")], "dates with a year not found"),
    "T13_generic_plus_phone_removed": ([skip_generic("phone")], "'+1 555 0100' not found"),
    "T14_long_number_removed": ([(G, '        if digits >= 9 and (len(groups) == 1 or len(groups) >= 3 or run.startswith("0")):\n',
                                  "        if False:\n")], "long and phone-like numbers not found"),
    "T15_id_like_number_removed": ([(G, '            found.append("id_like_number")\n', "            pass\n")],
                                   "'X1234567L' not found"),
    "T16_titled_name_removed": ([skip_generic("titled_name")], "'Dr. Smith' not found"),
    "T17_format_characters_kept": ([(G, '    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf")\n', "")],
                                   "a soft hyphen or zero-width character hides a name"),
    "T18_look_alikes_kept": ([(G, "    t = t.translate(_CONFUSABLES)\n", "")], "a Cyrillic 'о' hides a name"),
    "T19_no_german_spellings": ([(G, '    return {s for s in (base, normalise(expanded), base.replace("ae", "a").replace("oe", "o").replace("ue", "u")) if s}\n',
                                  "    return {base}\n")], "'Muenchen', 'MUELLER' not found"),
    "T20_particle_surname_dropped": ([(G, "    return kept or parts\n", "    return kept\n")],
                                     "a surname such as Do or Le never looked for"),
    "T21_length_cap_removed": ([(G, '    if len(text) > MAX_SCANNED_CHARS:\n        return ["text_too_long_to_check"]\n', "")],
                               "no cap on the scanned text"),
    "T22_quadratic_email_pattern": ([(G, '    "email": re.compile(r"(?<![a-z0-9._%+\\-])[a-z0-9._%+\\-]{1,64}@[a-z0-9\\-]{1,63}(?:\\.[a-z0-9\\-]{1,63}){0,8}"\n'
                                         '                        r"\\.[a-z]{2,24}(?![a-z])"),\n',
                                      '    "email": re.compile(r"[a-z0-9._%+\\-]+@[a-z0-9.\\-]+\\.[a-z]{2,}"),\n')],
                                    "the e-mail pattern of the first version (quadratic time)"),
    # second independent review (N5, N8, safe pairs)
    "T23_template_words_exempt": ([(BRS, '    texts = [UNLISTED, "Structure Label"]\n',
                                    '    texts = list(REPORT_TEMPLATES.values()) + [UNLISTED, "Structure Label"]\n')],
                                  "words of the system templates ('Pons', 'Filippi') never reported"),
    "T24_numeric_record_number_in_measurements": ([(G, '        return re.compile(rf"(?<![\\w.,]){chars}(?!\\w|[.,]\\d|\\s?(?:{_UNIT_AFTER}))")\n',
                                                    '        return re.compile(r"(?<![a-z0-9])" + r"[\\s\\-./_#:]{0,3}".join(chars) + r"(?![a-z0-9])")\n')],
                                                  "an all-digit record number found inside '12345.67 mm³' (false refusal)"),
    "T25_prefixed_digits_not_checked": ([(G, "        numbers += [d for n in list(numbers) if not n.isdigit() and len(d := _digits(n)) >= 6 and d not in numbers]\n", "")],
                                        "'id 20250042' (the digits of MRN-2025-0042) not found"),
    "T26_device_pairs_reported": ([(G, "                                or any((a, b) in pairs and (a, b) not in safe_pairs\n",
                                    "                                or any((a, b) in pairs\n")],
                                  "a patient named Deep White blocks every draft ('Deep White Matter')"),
    "T27_device_joined_words_reported": ([(G, "any(w in joined and w not in safe_words for w in unique)", "any(w in joined for w in unique)")],
                                         "a patient named Juxta Cortical blocks every draft ('Juxtacortical')"),
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
    "F4_incomplete_record_accepted": ([(G, "        if not (mrn and given and family and isinstance(birth, date)):\n",
                                        "        if not (mrn or given or family):\n")],
                                      "a record without record number, name or birth date accepted"),
    "F5_service_sends_without_identifiers": ([(BRS, "        if not isinstance(identifiers, PatientIdentifiers):\n", "        if False:\n")],
                                             "the service builds and sends a prompt without the patient's identifiers"),
    "F6_assistant_omits_segmentation": ([(MCPS, '            "segmentation_id": segmentation_id,\n', "")],
                                        "the assistant's report tool sends no segmentation (every draft refused)"),
    # ── RC-066: typed text merged locally; records; claims; screen texts ──
    "M1_typed_text_not_merged": ([(AIR, '            result["content"], request.language, clinician_entry(request.findings, request.language),\n',
                                        '            result["content"], request.language, None,\n')],
                                 "the clinician's typed text missing from the draft"),
    "M2_entry_before_disclaimer": ([(AIR, "(disclaimer if has_disclaimer else None, entry, heading, note, body)",
                                     "(entry, disclaimer if has_disclaimer else None, heading, note, body)")],
                                   "the typed text placed before the RC-006 disclaimer"),
    "M3_model_not_told": ([(BRS, "        if findings.get(\"clinician_entry\") is True:\n            parts.append(CLINICIAN_TEXT_INSTRUCTION)\n", "")],
                          "the model is not told that the clinician's text is added by the application"),
    # second independent review (N1, N6, N7): the draft's structure
    "M4_typed_text_not_quoted": ([(AIR, "{quoted(findings[key].strip()[:MAX_TYPED_CHARS])}", "{findings[key].strip()[:MAX_TYPED_CHARS]}")],
                                 "typed Markdown rendered: a typed heading, image or link becomes report structure"),
    "M5_fixed_short_fence": ([(AIR, '    fence = "`" * max(3, 1 + max((len(run) for run in re.findall(r"`+", text)), default=0))\n',
                               '    fence = "```"\n')],
                             "typed backticks close the quoted block and the rest is rendered"),
    "M6_no_ai_heading": ([(AIR, "    heading = f\"### {AI_DRAFT_HEADING.get(language, AI_DRAFT_HEADING['en'])}\"\n", "    heading = None\n")],
                         "the model text continues under the clinician's heading"),
    "M7_entry_not_closed": ([(AIR, '"\\n\\n".join(blocks) + "\\n\\n---" if blocks else None', '"\\n\\n".join(blocks) if blocks else None')],
                            "the clinician's entry is not closed before the AI draft"),
    "M8_instruction_always_sent": ([(BRS, '        if findings.get("clinician_entry") is True:\n', "        if True:\n")],
                                   "the model is told about a clinician's entry that does not exist"),
    "L1_raw_findings_logged": ([(BRS, '            extra={"report_id": report_id, "privacy_check": "passed", "withheld": payload.withheld},\n',
                                 '            extra={"report_id": report_id, "privacy_check": "passed", "withheld": payload.withheld, "findings": findings},\n')],
                               "the request's findings written to the log"),
    "L2_prompt_logged": ([(BRS, '            extra={"report_id": report_id, "privacy_check": "passed", "withheld": payload.withheld},\n',
                           '            extra={"report_id": report_id, "privacy_check": "passed", "withheld": payload.withheld, "prompt": user_prompt},\n')],
                         "the prompt written to the log"),
    "L3_counts_not_logged": ([(BRS, '            extra={"report_id": report_id, "privacy_check": "passed", "withheld": payload.withheld},\n',
                               '            extra={"report_id": report_id, "privacy_check": "passed", "withheld": {}},\n')],
                             "no record of what was withheld"),
    "C1_false_header_claim": ([(BRS, "Data sent to the model provider (CAPA-014; RC-064, RC-065, RC-066; HAZ-016):\n",
                                "HIPAA compliance: patient data is de-identified before sending to Claude API.\n"
                                "Data sent to the model provider (CAPA-014; RC-064, RC-065, RC-066; HAZ-016):\n")],
                              "the service header claims de-identification again"),
    "C2_readme_badge_back": ([(README, '  <img src="https://img.shields.io/badge/WebAuthn-passkeys-orange" alt="WebAuthn">\n',
                               '  <img src="https://img.shields.io/badge/HIPAA-compliant-green" alt="HIPAA">\n'
                               '  <img src="https://img.shields.io/badge/WebAuthn-passkeys-orange" alt="WebAuthn">\n')],
                             "the README's 'HIPAA compliant' badge back"),
    "C3_generator_claim_back": ([(GEN, '    ("RC-007", "HAZ-003", "Withdrawn 2026-07-18; replaced by RC-064, RC-065 and RC-066 (CAPA-014)",\n',
                                  '    ("RC-007", "HAZ-003", "De-identified data only sent to Claude API",\n'
                                  '     "brain_report_service.py _build_findings_prompt strips PHI; only age/sex/findings sent", ""),\n'
                                  '    ("RC-007b", "HAZ-003", "Withdrawn 2026-07-18; replaced by RC-064, RC-065 and RC-066 (CAPA-014)",\n')],
                                "the record generator writes the withdrawn RC-007 statement again"),
    "C4_stale_model_name": ([(TECHDOC, "                                              (claude-sonnet-4-5-20250929,\n",
                              "                                              (claude-3-5-sonnet,\n")],
                            "the technical documentation names a model the device does not use"),
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
    "U7_viewer_footer_claim_back": ([(VIEWER, "                    {t('reportViewer.aiDataNote')}\n",
                                      "                    {t('reportViewer.hipaaNote', 'HIPAA Compliant — Only de-identified clinical findings were used.')}\n")],
                                    "the report viewer footer claims HIPAA compliance again"),
    "U8_viewer_loads_images": ([(VIEWER, "                      img: ({ alt }) => (\n"
                                         "                        <span className=\"text-gray-500\">[image: {alt || '-'}]</span>\n"
                                         "                      ),\n", "")],
                               "an image named in the draft is loaded on screen and in print"),
}

# Mutations that are NOT defects (equivalent code), stated rather than claimed as tested.
EXPECTED_UNDETECTED = {}


def run_backend():
    r = subprocess.run([PY, "-m", "pytest", *BACKEND_TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace", env=OFFLINE)
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
           "design": "redesign after the independent review of PR #67: structured payload only, typed text merged "
                     "locally, detection-only tripwire (the scrubbing module of the first version was removed)",
           "method": "one mutation at a time; each anchor asserted to occur exactly once; the bound tests of the "
                     "mutated side are run (backend pytest offline per PRB-002, frontend vitest JSON reporter)",
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
