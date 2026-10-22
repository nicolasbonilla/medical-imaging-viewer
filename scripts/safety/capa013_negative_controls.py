"""Negative controls for CAPA-013 — longitudinal change candidates (RC-060, RC-061, RC-062; HAZ-007).

Each mutation re-introduces ONE defect CAPA-013 removed (the activity/DIT flags, an activity
statement from unconfirmed candidates, an unrecorded or unbound reader decision, the subtraction
worded as confirmation, English-only texts, a hard-coded or unbound false-candidate rate, no
abstention on an acquisition change) or removes one sub-control it added — in the real source,
one at a time. The script asserts every anchor occurs exactly once (the sabotage really was
applied), runs the bound tests of the side it mutated (backend: pytest; frontend: vitest, JSON
reporter), records the failing test names and restores the exact original bytes.

Run from the repository root (needs backend/venv or the current Python with the backend
requirements, and frontend/node_modules):
    python scripts/safety/capa013_negative_controls.py            # every mutation
    python scripts/safety/capa013_negative_controls.py --only F   # re-run the mutations whose name
                                                                  # starts with F; others kept from
                                                                  # the existing record
Output: docs/iec62304/records/risk_verification/CAPA-013_negative_controls_2026-10-22.json
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
OUT = "docs/iec62304/records/risk_verification/CAPA-013_negative_controls_2026-10-22.json"
BACKEND_TESTS = ["tests/unit/test_capa013_longitudinal_candidates.py"]
FRONTEND_TESTS = ["src/components/LongitudinalCompare.capa013.test.tsx"]

LCS = "backend/app/services/longitudinal_candidate_safety.py"
SA = "backend/app/api/routes/segmentation_analysis.py"
BRS = "backend/app/services/brain_report_service.py"
AIR = "backend/app/api/routes/ai_report.py"
MCPB = "backend/app/mcp/_backend.py"
MCPS = "backend/app/mcp/ms_clinical_server.py"
DWS = "backend/app/services/dicomweb_service.py"
ASSET = "backend/app/services/assets/longitudinal_false_candidate_evidence.json"
P = "frontend/src/components/LongitudinalResultPanel.tsx"
EN = "frontend/src/i18n/locales/en.json"
ES = "frontend/src/i18n/locales/es.json"
DE = "frontend/src/i18n/locales/de.json"

LEGACY_BANNER = (
    "          {(result as any).activity_candidate && (\n"
    "            <div>{t('longitudinal.activityCandidate', 'Active-disease CANDIDATE')} — "
    "{t('longitudinal.nedaT2Active', 'NEDA-3 MRI (T2-arm): activity CANDIDATE')}</div>\n"
    "          )}\n"
)
READER_BOX = "          {/* RC-060 (c): only after a radiologist's confirmation"

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── RC-060: never activity from unconfirmed candidates; reader decisions recorded and bound ──
    "B1_legacy_flags_returned": ([(LCS, "    out = {k: v for k, v in result.items() if k not in LEGACY_FLAG_KEYS}\n",
                                   "    out = dict(result)\n")],
                                 "activity_candidate / dit_candidate reach the view, the report and the assistant (the defect as found)"),
    "B2_presentation_bypassed": ([(SA, "        result = lcs.present_comparison(\n", "        _bypassed = lcs.present_comparison(\n")],
                                 "the route returns the raw comparison (as on PR #62)"),
    "B3_activity_from_unconfirmed": ([(LCS, "    if confirmed >= MAGNIMS_2021_MIN_NEW_OR_ENLARGING:\n",
                                       "    if total >= MAGNIMS_2021_MIN_NEW_OR_ENLARGING:\n")],
                                     "the activity statement computed from unconfirmed candidates"),
    "B4_rejection_counts_as_confirmation": ([(LCS, '                if d["decision"] == "confirmed":\n',
                                              '                if d["decision"] in REVIEW_DECISIONS:\n')],
                                            "a rejected candidate counted as confirmed"),
    "B5_any_role_may_decide": ([(SA, '    if getattr(current_user, "role", None) != UserRole.RADIOLOGIST:\n'
                                     '        raise HTTPException(status_code=403,\n'
                                     '                            detail="Only a radiologist can confirm or reject a change candidate.")\n',
                                 '    if False:\n'
                                 '        raise HTTPException(status_code=403,\n'
                                 '                            detail="Only a radiologist can confirm or reject a change candidate.")\n')],
                               "any authenticated user records a confirmation"),
    "B6_decision_not_bound_to_masks": ([(SA, "    if binding != current:\n", "    if False:\n")],
                                       "a decision recorded for masks other than those compared"),
    "B7_decisions_survive_a_mask_change": ([(LCS, '        if stored_review.get("tp1_mask_sha256") == binding["tp1_mask_sha256"] \\\n'
                                                  '                and stored_review.get("tp2_mask_sha256") == binding["tp2_mask_sha256"]:\n',
                                             "        if True:\n")],
                                           "decisions kept after either segmentation changed"),
    "B8_reader_not_recorded": ([(SA, '            "reviewed_by": current_user.username,\n', '            "reviewed_by": None,\n')],
                               "a decision stored without the authenticated reader"),
    "B9_decision_values_not_checked": ([(LCS, '        if d.get("decision") not in REVIEW_DECISIONS:\n', "        if False:\n")],
                                       "any decision value accepted"),
    "B10_report_template_activity_classification": ([(BRS, '        "## INTERVAL CHANGE STATUS\\n"\n',
                                                      '        "## DISEASE ACTIVITY CLASSIFICATION\\n"\n'
                                                      '        "- **Active**: new enhancing or new/enlarging T2 lesions since prior\\n"\n')],
                                                    "the report template asks for an Active/Not active classification (the defect as found)"),
    "B11_report_prompt_activity_word": ([(BRS, "                parts.append(f\"  New-lesion candidates (unconfirmed): {sc.get('new', 0)}\")\n",
                                          "                parts.append(f\"  New-lesion count (active disease candidate): {sc.get('new', 0)}\")\n")],
                                        "the report prompt labels candidates as active disease"),
    "B12_report_ignores_reader_confirmation": ([(BRS, '                if isinstance(rc, dict) and rc.get("confirmed_by")',
                                                 '                if False and isinstance(rc, dict) and rc.get("confirmed_by")')],
                                               "the report never states the radiologist's confirmation"),
    "B13_report_notice_removed": ([(AIR, "        if notice:   # CAPA-013", "        if False:   # CAPA-013")],
                                  "a report draft with longitudinal data ends without the unconfirmed-candidate notice"),
    "B14_assistant_receives_flags": ([(MCPB, "                if k not in UNCONFIRMED_ACTIVITY_KEYS}\n", "                if True}\n")],
                                     "the assistant receives activity / DIT flags"),
    "B15_assistant_may_record_decisions": ([(MCPB, '    "/ai/report/generate",\n})',
                                             '    "/ai/report/generate",\n    "/segmentation/longitudinal/review",\n})')],
                                           "the read-only assistant can record a radiologist decision"),
    # ── RC-061: measured false-candidate rate from the versioned asset ──
    "E1_rate_hard_coded": ([(LCS, '            "false_candidates_per_patient": float(m["false_candidates_per_patient"]),\n',
                             '            "false_candidates_per_patient": 8.9,\n')],
                           "the rate written in code instead of read from the asset"),
    "E2_rule_binding_removed": ([(LCS, '        if asset.get("applies_to_rule") != current_rule_parameters():\n', "        if False:\n")],
                                "the rate served for a rule it was not measured on"),
    "E3_incomplete_asset_accepted": ([(LCS, '            "false_candidates_per_patient": float(m["false_candidates_per_patient"]),\n',
                                       '            "false_candidates_per_patient": float(m.get("false_candidates_per_patient", 0)),\n')],
                                     "an asset without the figure served as a rate of 0"),
    "E4_caveat_without_rate": ([(LCS, "radiologist's confirmation counts. \" + evidence_sentence(evidence) + _registration_sentence(result)",
                                 "radiologist's confirmation counts. \" + _registration_sentence(result)")],
                               "the API caveat (assistant, other consumers) omits the measured rate"),
    "E5_asset_figure_not_the_source": ([(ASSET, '    "false_candidates_per_patient": 8.9,\n', '    "false_candidates_per_patient": 2.1,\n')],
                                       "the asset states a figure that is not the one in its source record"),
    "E6_assistant_subtraction_as_confirmation": ([(MCPS, "follow-up on the FLAIR subtraction': a signal, never a confirmation of a lesion.",
                                                   "follow-up on the FLAIR subtraction': they confirm a lesion.")],
                                                 "the assistant is told the subtraction confirms a lesion"),
    # ── RC-062: abstain on an acquisition change ──
    "A1_no_abstention": ([(LCS, '    if acquisition_check.get("status") != "same":                                    # RC-062\n',
                           "    if False:\n")],
                         "candidates shown whatever the acquisition (the defect as found)"),
    "A2_unknown_treated_as_same": ([(LCS, '    status = "differs" if differing else ("not_established" if missing else "same")\n',
                                     '    status = "differs" if differing else "same"\n')],
                                   "missing metadata treated as the same acquisition"),
    "A3_sequence_parameters_ignored": ([(LCS, "    for field in REQUIRED_ACQUISITION_FIELDS + SEQUENCE_FIELDS:\n",
                                         "    for field in REQUIRED_ACQUISITION_FIELDS:\n")],
                                       "repetition / echo / inversion time and slice spacing not compared"),
    "A4_voxel_size_ignored": ([(LCS, "    elif any(abs(a - b) > VOXEL_SPACING_TOL_MM for a, b in zip(s1, s2)):\n", "    elif False:\n")],
                              "a change of voxel size between the visits not detected"),
    "A5_field_strength_tolerance_2T": ([(LCS, '_ABS_TOL = {"magnetic_field_strength_t": 0.05,', '_ABS_TOL = {"magnetic_field_strength_t": 2.0,')],
                                       "1.5 T and 3 T treated as the same field strength"),
    "A6_abstention_keeps_counts": ([(LCS, '            "abstained": True, "changes": [], "status_counts": None, "change_candidates": None,\n',
                                     '            "abstained": True,\n')],
                                   "an abstained comparison still carries candidates and counts"),
    "A7_visit_compared_with_itself": ([(SA, "            _source_acquisition(source_tp2) if source_tp2 else None,\n",
                                        "            _source_acquisition(source_tp1) if source_tp1 else None,\n")],
                                      "the acquisition of visit 1 compared with itself"),
    "A8_pacs_import_records_nothing": ([(DWS, '                "acquisition": acquisition_from_dicom(ds0),\n', "")],
                                       "PACS import stores no acquisition record (every comparison would abstain)"),
    "A9_dicom_numbers_as_text": ([(LCS, "        out[field] = _text(raw) if field in _TEXT_FIELDS else _number(raw)\n",
                                   "        out[field] = _text(raw)\n")],
                                 "acquisition numbers stored as text (field strength '3' never equals 3.0)"),
    # ── frontend: the view ──
    "F1_activity_banner_restored": ([(P, READER_BOX, LEGACY_BANNER + READER_BOX)],
                                    "the 'Active-disease CANDIDATE' / NEDA banner from the legacy flag (the defect as found)"),
    "F2_activity_box_from_unconfirmed": ([(P, "  const confirmedBox = result.reader_confirmed_activity;\n",
                                           "  const confirmedBox = result.reader_confirmed_activity ?? (cc && cc.total > 0 ? { rule: '', "
                                           "confirmed_new: cc.new, confirmed_enlarging: cc.enlarging, confirmed_by: [], first_confirmed_at: '', "
                                           "last_confirmed_at: '' } : undefined);\n")],
                                         "the activity box shown from unconfirmed candidates"),
    "F3_review_buttons_removed": ([(P, "                              {result.review_binding && (\n", "                              {false && (\n")],
                                  "no way for the radiologist to record a decision (review stated, not recorded)"),
    "F4_decision_not_bound": ([(P, "        review_binding: result.review_binding,\n",
                                "        review_binding: { tp1_mask_sha256: '', tp2_mask_sha256: '' },\n")],
                              "the decision sent without the masks it was given for"),
    "F5_no_refresh_after_decision": ([(P, "      onReviewed();\n", "")],
                                     "the panel keeps showing the state before the decision"),
    "F6_rate_hard_coded_in_view": ([(P, "                  mean: num(evidence.false_candidates_per_patient, 1),\n",
                                     "                  mean: '8.9',\n")],
                                   "the rate written in the component instead of the asset"),
    "F7_rate_not_shown": ([(P, '<p data-testid="longitudinal-evidence"', '<p data-testid="longitudinal-evidence-hidden" hidden')],
                          "the measured rate not shown"),
    "F8_backend_english_caveat_preferred": ([(P, "          {t('longitudinal.candidateCaveat')}\n",
                                              "          {result.caveat || t('longitudinal.candidateCaveat')}\n")],
                                            "the English backend caveat shown in every language (the defect as found)"),
    "F9_subtraction_worded_as_confirmation": ([(EN, '"subSummary": "FLAIR subtraction: {{c}} of {{n}} new candidates brighter at follow-up — a signal, not a confirmation."',
                                                '"subSummary": "FLAIR subtraction: {{c}} of {{n}} new candidates confirmed brighter at follow-up"')],
                                              "'confirmed brighter at follow-up' (the defect as found)"),
    "F10_subtraction_supports_new_lesion": ([(EN, '"subBrighterTip": "FLAIR brighter at follow-up (signal {{s}} SD): a signal only, it does not confirm a new lesion"',
                                              '"subBrighterTip": "FLAIR brighter at follow-up (signal {{s}} SD) — supports a genuine new lesion"')],
                                            "'supports a genuine new lesion' (the defect as found)"),
    "F11_spanish_summary_missing": ([(ES, '    "candidatesSummary": "{{total}} candidatos de cambio sin confirmar ({{n}} nuevos ≥{{d}} mm, '
                                          '{{e}} agrandados), que un radiólogo debe revisar uno a uno.",\n', "")],
                                    "a safety text without a Spanish entry (English shown, the defect as found)"),
    "F12_german_rate_in_english": ([(DE, '"evidence": "In einem öffentlichen Test mit von Experten markierten Veränderungen ({{patients}} Patienten, {{segmenter}})',
                                     '"evidence": "In a public test with expert-marked change ({{patients}} patients, {{segmenter}})')],
                                   "the measured rate shown in English to German readers"),
    "F15_spanish_caveat_partly_english": ([(ES, '"candidateCaveat": "Los candidatos de cambio se proponen automáticamente y no son hallazgos:',
                                            '"candidateCaveat": "Change candidates are proposed automatically and are not findings:')],
                                          "the standing caveat left partly in English for Spanish readers"),
    "F13_abstention_ignored": ([(P, "      {abstained ? abstentionBox(result.acquisition_check) : (\n",
                                 "      {false ? abstentionBox(result.acquisition_check) : (\n")],
                               "an abstained comparison shown as if candidates existed, with no reason"),
    "F14_missing_metadata_not_named": ([(P, "            {(check?.missing ?? []).map((m) => (\n",
                                         "            {([] as LongitudinalAcquisitionCheck['missing']).map((m) => (\n")],
                                       "the reader is not told which metadata are missing"),
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
    out = os.path.join(tempfile.gettempdir(), "capa013_vitest.json")
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
                kept.setdefault("executed", previous.get("executed"))
                kept.setdefault("test_sha256", {t: h for t, h in previous.get("test_sha256", {}).items()
                                                if t.startswith("frontend/") == (kept.get("suite") == "frontend")})
                current = {t: test_sha[t] for t in kept["test_sha256"] if t in test_sha}
                if current == kept["test_sha256"] and current:   # same tests as now: the result still holds
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
