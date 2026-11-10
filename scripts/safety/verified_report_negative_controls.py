"""Negative controls for the verified AI report (RC-102 .. RC-106; REQ-FUNC-116, REQ-SAFE-048..051) — PENDING owner
approval.

  RC-102  facts written by code (MAGNIMS counting, "not computed" never 0, regions only when confirmed, DIS only when
          evaluated, candidate wording, no technique section, the route's backstop never edits a code-written line)
  RC-103  every answer checked (frozen claim check v2, format rules, RC-070 backstop), at most two regenerations, then
          withheld with a note; the regeneration request checked for identifiers (RC-065)
  RC-104  every attempt and the outcome in the audit log (prompt SHA-256, model id, verdict, rule ids, latency)
  RC-105  the kill switch
  RC-106  the model allow-list and retirement, fixed parameters, failures / refusals / timeouts give the measurements only

Each mutation re-introduces ONE defect (or removes one sub-control) in the real source, one at a time, IN A THROWAWAY
DETACHED WORKTREE of the commit under test (created under the system temporary folder and removed afterwards; only
worktrees named with PREFIX are ever touched), so an interrupted run never leaves a mutation in a checkout. Backend
only: no frontend, no node_modules. The script:
  - refuses to start when a file it mutates, a test it runs or this script has uncommitted changes;
  - asserts every anchor occurs exactly once in the LF text, writes the mutation with the file's own line endings,
    restores the exact original bytes after each mutation, at exit and on a signal, and checks the restore;
  - runs the bound tests with no cloud credential (PRB-002): a credentials file and a gcloud configuration folder that
    do not exist, the offline project id, no model-provider key;
  - checks the baseline passes first and records the failing test names per mutation.

Run from the repository root with the backend's Python (it needs the backend requirements):
    <backend python> scripts/safety/verified_report_negative_controls.py           # in a throwaway worktree
    <backend python> scripts/safety/verified_report_negative_controls.py --here    # only in a disposable checkout
The backend Python is taken from MSTOOL_BACKEND_PYTHON, else backend/venv of this checkout or of the main checkout.
Output: docs/iec62304/records/risk_verification/VERIFIED-REPORT_negative_controls_review1_2026-11-10.json
(the first round, before the independent review of PR #78: ..._negative_controls_2026-11-10.json, kept)
"""
import atexit
import datetime
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(REPO)
OUT = "docs/iec62304/records/risk_verification/VERIFIED-REPORT_negative_controls_review2_2026-11-10.json"   # earlier rounds: _2026-11-10.json, _review1_2026-11-10.json (kept)
PREFIX = "verified-report-safety-run-"


def _git(*args, cwd=REPO, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def _backend_python():
    explicit = os.environ.get("MSTOOL_BACKEND_PYTHON")
    if explicit and os.path.exists(explicit):
        return explicit
    common = _git("rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    for root in (REPO, os.path.dirname(common)):
        for rel in (("backend", "venv", "Scripts", "python.exe"), ("backend", "venv", "bin", "python")):
            candidate = os.path.join(root, *rel)
            if os.path.exists(candidate):
                return candidate
    return sys.executable


PY = _backend_python()
TESTS = [
    "tests/unit/test_rc102_verified_report_flow.py",
    "tests/unit/test_rc103_verified_report_loop.py",
    "tests/unit/test_rc103_report_claim_verifier.py",
    "tests/unit/test_rc104_verified_report_audit.py",
    "tests/unit/test_rc105_rc106_report_model_controls.py",
    "tests/unit/test_brain_report_service.py",
    "tests/unit/test_verified_report_review1.py",       # independent review of PR #78, R1-R10
    "tests/unit/test_verified_report_review2.py",       # second independent review of PR #78, A-J
]

VR = "backend/app/services/verified_report.py"
BRS = "backend/app/services/brain_report_service.py"
LEX = "backend/app/services/report_claim_lexicon.py"
CFG = "backend/app/core/config.py"
AUD = "backend/app/core/logging/audit.py"
STR = "backend/app/services/report_claim_strict.py"
RT = "backend/app/api/routes/ai_report.py"

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── RC-102: the facts are written by code ──
    "F1_range_from_21": ([(VR, "    if n < 20:\n        return t[\"count_exact\"]", "    if n < 21:\n        return t[\"count_exact\"]")],
                         "20 lesions reported as an exact count, not as the MAGNIMS 2021 range"),
    "F2_not_computed_as_zero": ([(VR, "    if v is None or v != int(v) or v < 0:\n        return None\n",
                                  "    if v is None or v != int(v) or v < 0:\n        return 0\n")],
                                "a count that was not computed is written 0"),
    "F3_regions_without_confirmation": ([(VR, '    if la is not None and evaluated and la.get("regions_confirmed") is not False and regs_in:\n',
                                          '    if la is not None and la.get("regions_confirmed") is not False and regs_in:\n')],
                                        "lesions per region reported for a segmentation no radiologist confirmed"),
    "F4_dis_without_the_gate": ([(VR, "    evaluated = gate.is_evaluated(dis_block)\n",
                                  "    evaluated = isinstance(dis_block, dict) and dis_block.get(\"evaluation_status\") == \"evaluated\"\n")],
                                "a DIS result reported from a block the gate did not mark evaluated (no yes/no conclusion)"),
    "F5_candidates_called_lesions": ([(VR, '        "lng_ok": "The software proposed {new} new and {enl} enlarging unconfirmed change candidates ({res} resolved, "',
                                       '        "lng_ok": "The software found {new} new and {enl} enlarging lesions ({res} resolved, "')],
                                     "change candidates written as new and enlarging lesions"),
    "F6_technique_section_asked_again": ([(VR, "[IMPRESSION_COMMENT]: one or two sentences summarising, without any diagnosis.\n",
                                           "[IMPRESSION_COMMENT]: one or two sentences summarising, without any diagnosis.\n"
                                           "[TECHNIQUE]: describe the MRI technique, or state the standard MS protocol.\n")],
                                         "the model is asked for a technique section again (the retired template's defect)"),
    "F7_own_not_evaluated_sentence": ([(VR, "        dis_s = _dis_not_evaluated_line(lang)\n",
                                        "        dis_s = \"Dissemination in space: not evaluated (no radiologist confirmed it).\" if lang == \"en\" else _dis_not_evaluated_line(lang)\n")],
                                      "a code-written DIS line the route's backstop replaces (and counts as the model's)"),
    "F8_t1_next_to_spinal_cord": ([(VR, '        "lim_items": "clinical indication|contrast-enhanced imaging|T1-weighted imaging|brain volumetry",',
                                    '        "lim_items": "clinical indication|contrast-enhanced imaging|T1-weighted imaging|spinal cord imaging|brain volumetry",')],
                                  "a limitation sentence the route's backstop reads as a statement on DIS"),
    "F9_first_request_not_checked": ([(BRS, "                assert_prompt_carries_no_identifier(sent_text, identifiers)\n", "                pass\n")],
                                     "the first request is sent without the identifier check (RC-065)"),
    # ── independent review of PR #78 (R1-R10) ──
    "F10_dis_only_crashes": ([(VR, '    if la is not None and evaluated and la.get("regions_confirmed") is not False and regs_in:\n',
                               '    if evaluated and la.get("regions_confirmed") is not False and regs_in:\n')],
                             "R1: a DIS-only request (no lesion analysis) crashes the report (HTTP 500)"),
    "F11_not_included_dropped": ([(VR, '    if view.get("not_included"):\n        lim.append(', '    if False:\n        lim.append(')],
                                 "R3: measurements the verified report does not use are dropped silently"),
    "F12_region_not_computed_as_zero": ([(VR, "        if n is None:\n            not_computed.append(r)\n",
                                          "        if n is None:\n            counts[r] = 0\n")],
                                        "R4: a region count that was not computed is written 0"),
    "F13_stricter_dis_rule_back": ([(VR, "    evaluated = gate.is_evaluated(dis_block)\n",
                                     "    evaluated = gate.is_evaluated(dis_block) and _count(dis_block.get(\"regions_with_lesions\")) is not None\n")],
                                   "R6: a confirmed mask reported as not confirmed (the report contradicts the gate)"),
    "F14_placeholder_in_record_sent": ([(BRS, '                if UNLISTED.rstrip("]") in sent_text:\n', "                if False:\n")],
                                       "R8: a label of the request in the record is sent instead of refused"),
    "F15_number_reader_accepts_inf": ([(VR, "    from app.services.report_payload_guard import _number\n    return _number(x)\n",
                                        "    return None if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x else x\n")],
                                      "R10: an infinite value is read as a number (and a count of it crashes)"),
    # ── second independent review of PR #78 (A-J) ──
    "F16_other_label_hides_regions": ([(VR, "        regions_view = _region_breakdown(regs_in)\n",
                                        "        regions_view = _region_breakdown(regs_in) if set(regs_in) <= set(REGION_ORDER) else None\n")],
                                      "E: a label outside the four MAGNIMS regions makes the whole breakdown \"not computed\""),
    "F17_other_labels_dropped": ([(VR, "    if others:\n        ns =", "    if False:\n        ns =")],
                                 "E: lesions with other labels are dropped silently"),
    "F18_not_evaluated_twice": ([(VR, '([dis_s] if dis["status"] == "evaluated" else [])', "[dis_s]")],
                                "F: the \"DIS not evaluated\" statement is repeated in the impression"),
    "F19_per_lesion_table_back": ([(VR, '            "size_classes_mm3": {"small": "<100", "medium": "100-1000", "large": ">1000"},\n',
                                    '            "size_classes_mm3": {"small": "<100", "medium": "100-1000", "large": ">1000"},\n'
                                    '            "lesion_table": [[les.get("volume_mm3"), les.get("volume_ml")] for les in la.get("lesions") or []\n'
                                    '                             if isinstance(les, dict)],\n')],
                                  "J: the per-lesion volumes reach the model again (and widen the E1 number pool)"),
    # ── RC-103: every answer is checked ──
    "C1_claim_check_not_run": ([(VR, "    res = V.verify(assembled, None, view)\n", "    res = {\"elements\": []}\n")],
                               "the frozen claim check does not run on the answer"),
    "C2_digits_allowed": ([(VR, '    if re.search(r"\\d", re.sub(r"\\{[a-z_]+\\}", "", fc + " " + ic)):\n', "    if False:\n")],
                          "digits allowed in the comments"),
    "C3_headings_allowed": ([(VR, "    if S.heading_lines(fc) or S.heading_lines(ic):\n", "    if False:\n")],
                            "headings allowed in the comments (a section of the model's own)"),
    "C4_unknown_placeholder_allowed": ([(VR, "        if ph not in vals:\n", "        if False:\n")],
                                       "a placeholder the record does not have is left in the report"),
    "C5_rc070_backstop_not_in_the_loop": ([(VR, '    if view["dis"]["status"] != "evaluated":\n        from app.services import dis_review_gate as gate\n',
                                            '    if False:\n        from app.services import dis_review_gate as gate\n')],
                                          "a DIS statement the frozen rules miss passes the loop"),
    "C6_no_regeneration": ([(VR, "MAX_REGENERATIONS = 2 ", "MAX_REGENERATIONS = 0 ")], "no regeneration: blocked after one answer"),
    "C7_more_regenerations": ([(VR, "MAX_REGENERATIONS = 2 ", "MAX_REGENERATIONS = 5 ")], "more than two regenerations"),
    "C8_failing_answer_delivered": ([(VR, "        if not fails:\n            return FlowResult(", "        if not fails or attempt == max_regenerations:\n            return FlowResult(")],
                                    "the last failing answer is delivered instead of withheld"),
    "C9_no_withheld_note": ([(VR, '    return FlowResult(text=assemble(view, lang, "", "") + "\\n\\n" + note, outcome=outcome,',
                              '    return FlowResult(text=assemble(view, lang, "", ""), outcome=outcome,')],
                            "the report without comments does not say why"),
    "C10_refusal_read_as_text": ([(VR, '        if reply.stop_reason == "refusal":\n', "        if False:\n")],
                                 "a refusal is treated as an answer and regenerated"),
    "C11_feedback_not_checked": ([(VR, "            tripwire(feedback)\n", "            pass\n")],
                                 "a regeneration request is sent without the identifier check (RC-065)"),
    "C12_truncation_not_flagged": ([(VR, '        if reply.stop_reason == "max_tokens":\n', "        if False:\n")],
                                   "a cut-off answer is accepted"),
    "C13_lexicon_drift": ([(LEX, "    r\"\\b(?:consistent with|typical of|", "    r\"\\b(?:typical of|")],
                          "the ported rules drift from the frozen benchmark rules (\"consistent with MS\" passes)"),
    "C14_exact_count_placeholder": ([(VR, '        vals["total_count"] = str(n) if n < 20 else les["count_category"]\n',
                                      '        vals["total_count"] = str(n)\n')],
                                    "R5: the {total_count} placeholder gives the exact count from 20 lesions (MAGNIMS 2021: the range)"),
    "C15_headings_only_hash": ([(VR, "    if S.heading_lines(fc) or S.heading_lines(ic):\n",
                                 '    if re.search(r"^\\s*#", fc + "\\n" + ic, re.M):\n')],
                               "B: a bold or capital comment line is read as a heading and checked for nothing"),
    "C16_strict_rules_not_run": ([(VR, "    for e in list(res[\"elements\"]) + S.comment_elements(fc) + S.comment_elements(ic):\n",
                                   "    for e in list(res[\"elements\"]):\n")],
                                 "A: only the frozen v2 rules run on the answer"),
    "C17_negation_anywhere_before": ([(STR, '    words = _clause_before(fold, m.start()).split()\n    return bool(L.NEGATION.search(" ".join(words[-GOVERNING_WORDS:])))\n',
                                       "    return bool(L.NEGATION.search(fold[:m.start()]))\n")],
                                     "A: a negation anywhere earlier in the sentence exempts a treatment phrase (v2's rule)"),
    "C18_negation_window_unbounded": ([(STR, "GOVERNING_WORDS = 3\n", "GOVERNING_WORDS = 99\n")],
                                      "A: a negation anywhere earlier in the clause exempts a treatment phrase"),
    "C19_negated_diagnosis_exempt": ([(STR, "        diag = _hits(fold, L.L1 + L.L4 + DIAGNOSTIC_TERMS)\n",
                                       "        diag = [m for m in _hits(fold, L.L1 + L.L4 + DIAGNOSTIC_TERMS) if not governed_by_negation(fold, m)]\n")],
                                     "A: a denied diagnosis (\"not consistent with MS\") passes"),
    "C20_disclaimer_found_anywhere": ([(STR, '    return bool(DISCLAIMER.fullmatch(re.sub(r"\\s+", " ", fold).strip(" .!")))\n',
                                        '    return bool(DISCLAIMER.search(fold))\n')],
                                      "A: a sentence that only starts with the disclaimer is exempt (\"not a diagnosis, but ... MS\")"),
    "C21_negated_activity_exempt": ([(STR, "    act = [m for m in _hits(fold, L.L3)\n",
                                      "    act = [m for m in _hits(fold, L.L3) if not governed_by_negation(fold, m)\n")],
                                    "A: a denied activity statement (\"no disease activity\") passes"),
    "C22_regenerations_not_validated": ([(VR, "    if isinstance(max_regenerations, bool) or not isinstance(max_regenerations, int) \\\n"
                                              "            or not 0 <= max_regenerations <= MAX_REGENERATIONS:\n", "    if False:\n")],
                                        "I: any number of regenerations is accepted"),
    # ── RC-104: the audit ──
    "A1_attempts_not_audited": ([(BRS, "        self._emit(AuditEventType.CLINICAL_AI_REPORT_ATTEMPT, outcome, details, AuditSeverity.LOW)\n", "        pass\n")],
                                "the model attempts are not in the audit log"),
    "A2_outcome_not_audited": ([(BRS, "        audit.outcome(result, model_id if reason is None else None)\n", "        pass\n")],
                               "the outcome of the report is not in the audit log"),
    "A3_hash_not_of_the_request": ([(VR, '"prompt_sha256": prompt_sha256(request),', '"prompt_sha256": prompt_sha256(request_meta),')],
                                   "the recorded hash is not that of the request sent"),
    "A4_audit_keys_dropped": ([(AUD, '    "flow", "attempt", "model_id", "model_answered", "prompt_sha256", "verdict", "rule_ids", "latency_ms",\n',
                                "    \"flow\", \"attempt\",\n")],
                              "the audit record silently drops the model id, hash, verdict, rule ids and latency"),
    "A5_rule_ids_carry_answer_text": ([(VR, "        return sorted({f\"E3.{'section' if k.startswith('section:') else k}\" for k in kind.split(\"+\")})\n",
                                        "        return sorted({f\"E3.{k}\" for k in kind.split(\"+\")})\n")],
                                      "a rule id carries words of the answer (a section name) into the audit log"),
    "A6_refusal_not_audited": ([(BRS, "            audit.not_sent(e)\n            raise\n", "            raise\n")],
                               "R7: a draft refused by a privacy check (or failed) before any model call leaves no audit record"),
    # ── RC-105: the kill switch ──
    "K1_kill_switch_ignored": ([(BRS, '        if getattr(self._settings, "REPORT_LLM_ENABLED", True) is not True:\n', "        if False:\n")],
                               "REPORT_LLM_ENABLED=false still calls the model"),
    "K2_kill_switch_setting_removed": ([(CFG, "    REPORT_LLM_ENABLED: bool = Field(default=True)\n", "")],
                                       "the environment cannot switch the model off"),
    # ── RC-106: the model ──
    "M1_allow_list_bypassed": ([(BRS, "        if not report_model_allowed(model_id):\n            return verified_report.REASON_MODEL_NOT_ALLOWED\n",
                                 "        if model_id is None:\n            return verified_report.REASON_MODEL_NOT_ALLOWED\n")],
                               "any configured model id is called"),
    "M2_retiring_default_back": ([(CFG, '    CLAUDE_MODEL: str = Field(default="claude-sonnet-5-5")\n',
                                   '    CLAUDE_MODEL: str = Field(default="claude-sonnet-4-5-20250929")\n')],
                                 "the default model is the one retiring on 2026-11-30 (the defect as found)"),
    "M3_retirement_date_ignored": ([(BRS, "    return retires is None or (today or date.today()) < date.fromisoformat(retires)\n", "    return True\n")],
                                   "an allow-listed model past its retirement date is still called"),
    "M4_sampling_parameter_sent": ([(BRS, "                    extra_body=copy.deepcopy(params), timeout=max(1.0, float(timeout_s)))",
                                     "                    extra_body=copy.deepcopy(params), timeout=max(1.0, float(timeout_s)), temperature=0.0)")],
                                   "a sampling parameter is sent (400 on the current models)"),
    "M5_answer_read_by_position": ([(BRS, '    text = "".join(_block_field(b, "text") or "" for b in blocks\n                   if _block_field(b, "type") == "text" and isinstance(_block_field(b, "text"), str))\n',
                                     '    text = (_block_field(blocks[0], "text") or "") if blocks else ""\n')],
                                   "the first block is read as the answer (a thinking block, as content[0].text did)"),
    "M6_provider_failure_propagates": ([(BRS, "            except Exception as e:  # noqa: BLE001 — every failure: the comments are not delivered, the report is\n",
                                         "            except ValueError as e:  # noqa: BLE001 — every failure: the comments are not delivered, the report is\n")],
                                       "a provider failure fails the report instead of giving the measurements only"),
    "M7_no_time_budget": ([(VR, "        if remaining <= 0:\n", "        if False:\n")], "the 25 s budget of a report is not enforced"),
    "M8_long_call_timeout": ([(BRS, "timeout=max(1.0, float(timeout_s)))", "timeout=600.0)")],
                             "one call may wait ten minutes (the SDK default)"),
    "M9_404_not_recognised": ([(BRS, '    if getattr(exc, "status_code", None) == 404 or name == "NotFoundError":\n', "    if False:\n")],
                              "a model the provider no longer serves is reported as a generic error"),
    "M10_sdk_retry_back": ([(BRS, "            self._client = anthropic.Anthropic(api_key=api_key, max_retries=0)\n",
                             "            self._client = anthropic.Anthropic(api_key=api_key, max_retries=1)\n")],
                           "R2: the SDK retries with a fresh full timeout (about twice the 25 s budget)"),
    "M11_wait_not_bounded": ([(BRS, "                message = await asyncio.wait_for(asyncio.to_thread(\n", "                message = await (asyncio.to_thread(\n"),
                              (BRS, "timeout=max(1.0, float(timeout_s))), timeout=float(timeout_s))", "timeout=max(1.0, float(timeout_s))))")],
                             "R2: the wait for the provider is not bounded by the remaining budget"),
    "M12_retired_table_decides": ([(BRS, "    if entry is None:\n        return False\n    retires = entry.get(\"retires_on\")\n",
                                    "    if entry is None or model_id in RETIRED_OR_RETIRING_MODELS:\n        return False\n    retires = entry.get(\"retires_on\")\n")],
                                  "R9: a second allow mechanism (the retired table) next to the allow-list and its retirement date"),
    # ── RC-064: only what is rendered is sent and validated (second review, C, D, H) ──
    "P1_unrendered_fields_validated": ([(BRS, "            payload = provider_payload(rendered_findings, rendered_volumetry, identifiers)\n",
                                         "            payload = provider_payload(findings, volumetry, identifiers)\n")],
                                       "C: a bad value in a field the report does not render refuses the whole report"),
    "P2_unrenderable_request_accepted": ([(RT, "    if not verified_report.renderable(request.findings, request.volumetry):\n",
                                           "    if not (any(request.findings.get(k) for k in (\"lesion_analysis\", \"dis_assessment\", \"longitudinal\", "
                                           "\"zone_stats\", \"segmentation_labels\", \"anomalies\")) or request.volumetry):\n")],
                                         "D: a request with nothing the verified report can write gives an empty report"),
    "P3_description_untruthful": ([(RT, "band, no per-lesion values; the typed text", "band are sent, no per-lesion values; the typed text"),
                                   (RT, "change candidates of a visit pair, and the total brain and intracranial volume — no sex, no age \"",
                                    "change candidates of a visit pair, the total brain and intracranial volume, sex and a 5-year age \"")],
                                  "H: the API description says sex and an age band are sent"),
    # ── RC-065: the device's own words, and the first request checked as sent (second review, G, J) ──
    "T1_retired_words_back": ([(BRS, "    texts: List[str] = []\n", "    texts: List[str] = [UNLISTED, \"Structure Label\"]\n"),
                               (BRS, "    texts.append(verified_report.REGENERATION_PREFIX + verified_report.REGENERATION_SUFFIX)\n",
                                "    texts.append(verified_report.REGENERATION_PREFIX + verified_report.REGENERATION_SUFFIX)\n"
                                "    texts.append(BrainReportService.__new__(BrainReportService)._build_findings_prompt({}, None, \"en\"))\n")],
                              "G: the retired templates' words widen the RC-065 vocabulary again"),
    "T2_first_message_built_twice": ([(BRS, "                    first_message=sent_text)", "                    first_message=None)")],
                                     "J: the first request is built a second time after the identifier check"),
    # ── RC-070: one guaranteed "not evaluated" statement (second review, F) ──
    "D1_notice_repeats_the_line": ([(RT, "    stated = content is not None and gate.NOT_EVALUATED_LINE.get(lang, gate.NOT_EVALUATED_LINE[\"en\"]) in content\n",
                                     "    stated = False\n")],
                                   "F: the route's notice repeats the \"not evaluated\" statement the draft already has"),
}


def offline_env():
    """PRB-002: backend tests never reach a real cloud service or the model provider."""
    env = dict(os.environ)
    empty = tempfile.mkdtemp(prefix="verified-report-no-gcloud-")
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(empty, "no-such-credentials.json"),
                "CLOUDSDK_CONFIG": empty, "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests"})
    for name in ("ANTHROPIC_API_KEY", "FIRESTORE_EMULATOR_HOST", "PYTHONPATH"):
        env.pop(name, None)
    return env


def run_tests():
    r = subprocess.run([PY, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "-o",
                        "log_cli=false"], cwd="backend", capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=offline_env(), timeout=1800)

    def count(word):
        m = re.search(rf"(\d+) {word}", r.stdout)
        return int(m.group(1)) if m else 0

    return {"exit": r.returncode, "failed": count("failed"), "passed": count("passed"), "errors": count("error"),
            "skipped": count("skipped"),
            "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))[:60]}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def require_committed(paths):
    dirty = _git("status", "--porcelain", "--", *paths).stdout
    if dirty.strip():
        raise SystemExit(f"uncommitted changes in {dirty.split()}: commit them first (the run uses the commit)")


def clean_stale():
    listing = _git("worktree", "list", "--porcelain").stdout
    paths = [ln.split(" ", 1)[1].strip() for ln in listing.splitlines() if ln.startswith("worktree ")]
    stale = [p for p in paths if os.path.basename(os.path.normpath(p)).startswith(PREFIX)]
    for p in stale:
        _git("worktree", "remove", "--force", p, check=False)
        shutil.rmtree(p, ignore_errors=True)
    _git("worktree", "prune", check=False)
    return stale


def main():
    files = sorted({e[0] for edits, _w in M.values() for e in edits})
    tests = [f"backend/{t}" for t in TESTS]
    require_committed(files + tests + [os.path.relpath(__file__, REPO).replace(os.sep, "/")])
    commit = _git("rev-parse", "HEAD").stdout.strip()
    if "--here" in sys.argv:
        # In a checkout that is itself disposable (an isolated agent worktree): mutate here, restore byte for byte,
        # and refuse to finish unless the mutated files are unchanged against the commit afterwards.
        res = run_in_worktree(files)
        require_committed(files)
        res["worktree"] = {"run_in": "the current checkout (--here: an isolated, disposable worktree), clean before "
                                     "and after for every mutated file", "commit": commit, "python": PY}
        return _write(res)
    stale = clean_stale()
    wt = os.path.join(tempfile.gettempdir(), f"{PREFIX}{os.getpid()}-{int(time.time())}")
    _git("worktree", "add", "--detach", wt, commit)
    try:
        os.chdir(wt)
        res = run_in_worktree(files)
    finally:
        os.chdir(REPO)
        _git("worktree", "remove", "--force", wt, check=False)
        shutil.rmtree(wt, ignore_errors=True)
        _git("worktree", "prune", check=False)
    res["worktree"] = {"run_in": "throwaway detached worktree of the commit, removed after the run", "commit": commit,
                       "stale_worktrees_removed_first": stale, "python": PY}
    return _write(res)


def _write(res):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, ensure_ascii=False)
    print("restored", res["restored"]["passed"], "passed /", res["restored"]["failed"], "failed | detected",
          res["summary"]["detected"], "of", res["summary"]["mutations"], "| undetected:", res["summary"]["undetected"])
    return 1 if res["summary"]["undetected"] or res["restored"]["failed"] or res["restored"]["errors"] else 0


def run_in_worktree(files):
    here = os.getcwd()
    raw = {p: open(p, "rb").read() for p in files}
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
    for name, (edits, _w) in M.items():
        for path, anchor, _r in edits:
            c = text[path].count(anchor)
            assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"

    def restore():
        for p, b in raw.items():
            with open(os.path.join(here, p), "wb") as fh:
                fh.write(b)

    def on_signal(signum, _frame):
        restore()
        raise SystemExit(f"interrupted by signal {signum}; sources restored")

    atexit.register(restore)
    handlers = {}
    for sig in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, sig):
            handlers[sig] = signal.signal(getattr(signal, sig), on_signal)
    try:
        res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
               "method": "in a throwaway detached worktree of the commit; one mutation at a time; each anchor asserted "
                         "to occur exactly once (LF text, written back with the file's own line endings); the bound "
                         "backend tests with no cloud credential (PRB-002); original bytes restored after each "
                         "mutation, at exit and on a signal, and checked at the end; the baseline must pass first",
               "hash_basis": "sha256 of the UTF-8 text with LF line endings",
               "source_sha256": {p: sha(text[p]) for p in files},
               "test_sha256": {t: sha(open(os.path.join("backend", t), encoding="utf-8").read().replace("\r\n", "\n"))
                               for t in TESTS},
               "tests": TESTS, "baseline": run_tests(), "mutations": {}}
        base = res["baseline"]
        if base["failed"] or base["errors"] or not base["passed"]:
            raise SystemExit(f"the baseline must pass before the mutations mean anything: {base}")
        print("baseline ok", base["passed"], "passed", flush=True)
        for name, (edits, what) in M.items():
            touched = {}
            for path, anchor, repl in edits:
                touched[path] = touched.get(path, text[path]).replace(anchor, repl, 1)
            for path, mutated in touched.items():
                assert mutated != text[path], name
                with open(path, "w", encoding="utf-8", newline=eol[path]) as fh:
                    fh.write(mutated)
            out = run_tests()
            out.update({"reintroduces": what, "files": sorted(touched),
                        "executed": datetime.datetime.now().isoformat(timespec="seconds"),
                        "detected": bool(out["failed"] or out["errors"])})
            res["mutations"][name] = out
            for path in touched:
                with open(path, "wb") as fh:
                    fh.write(raw[path])
            print(f"{name:40s} detected={out['detected']} {out['failed']} failed / {out['errors']} errors / "
                  f"{out['passed']} passed", flush=True)
    finally:
        restore()
        atexit.unregister(restore)
        for sig, h in handlers.items():
            signal.signal(getattr(signal, sig), h)
    for p in files:
        assert open(p, "rb").read() == raw[p], p
    res["restored"] = run_tests()
    undetected = sorted(n for n, v in res["mutations"].items() if not v["detected"])
    res["summary"] = {"mutations": len(res["mutations"]), "detected": len(res["mutations"]) - len(undetected),
                      "undetected": undetected}
    return res


if __name__ == "__main__":
    sys.exit(main())
