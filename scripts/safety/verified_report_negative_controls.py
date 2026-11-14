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
    "tests/unit/test_verified_report_review2_dis.py",   # item K (found by PR #79): DIS wording
    "tests/unit/test_verified_report_review3.py",       # third independent review of PR #78, T1-T6
    "tests/unit/test_verified_report_review4.py",       # fourth independent review of PR #78, Q1-Q8
    "tests/unit/test_verified_report_review5.py",       # fifth independent review of PR #78, V1-V10
    "tests/unit/test_verified_report_review6.py",       # sixth independent review of PR #78, W1-W7
    "tests/unit/test_verified_report_scenario_matrix.py",   # seventh review: invariants I1-I8 over 1128 cases
    "tests/unit/test_verified_report_review10.py",      # tenth independent review of PR #78, I16-I19
    "tests/unit/test_verified_report_review11.py",      # eleventh (final) review of PR #78: L1, L2, C1-C4, C7, M1, M2
]

VR = "backend/app/services/verified_report.py"
BRS = "backend/app/services/brain_report_service.py"
LEX = "backend/app/services/report_claim_lexicon.py"
CFG = "backend/app/core/config.py"
AUD = "backend/app/core/logging/audit.py"
STR = "backend/app/services/report_claim_strict.py"
GRD = "backend/app/services/report_payload_guard.py"
RT = "backend/app/api/routes/ai_report.py"
MAIN = "backend/app/main.py"
LCS = "backend/app/services/longitudinal_candidate_safety.py"

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── RC-102: the facts are written by code ──
    "F1_range_from_21": ([(VR, "            \"total_count\": n if n is not None and n < 20 else None,\n", "            \"total_count\": n if n is not None and n < 21 else None,\n"), (VR, "    if n is not None and n < 20:\n        return t[\"count_exact\"]", "    if n is not None and n < 21:\n        return t[\"count_exact\"]")],
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
    "F9_first_request_not_checked": ([(BRS, "                assert_prompt_carries_no_identifier(sent_text, ids)\n", "                pass\n")],
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
    "F15_number_reader_accepts_inf": ([(GRD, "    if isinstance(value, float) and not math.isfinite(value):\n        return None\n    return value\n",
                                        "    return value\n")],
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
    "C1_claim_check_not_run": ([(VR, "    res = S.verify(assembled, None, view, model_text=(fc, ic))\n",
                                 "    res = {\"elements\": [], \"headings\": []}\n")],
                               "the frozen claim check does not run on the answer"),
    "C2_digits_allowed": ([(VR, '    if re.search(r"\\d", re.sub(r"\\{[a-z_]+\\}|\\b[Tt][12]\\b", "", fc + " " + ic)):\n', "    if False:\n")],
                          "digits allowed in the comments"),
    "C3_headings_allowed": ([(VR, "    if res[\"headings\"]:\n", "    if False:\n")],
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
    "C15_headings_only_hash": ([(STR, "    res[\"headings\"] = [h for text in texts for h in heading_lines(text)]\n",
                                 "    res[\"headings\"] = [ln for text in texts for ln in text.split(\"\\n\") if ln.lstrip().startswith(\"#\")]\n")],
                               "B: a bold or capital comment line is read as a heading and checked for nothing"),
    "C16_strict_rules_not_run": ([(STR, "    extra = [e for text in texts for e in comment_elements(text, view)]\n",
                                   "    extra = []\n")],
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
    "C23_dis_statements_not_read": ([(STR, "    if not isinstance(view, dict):\n        return []\n    fold = L.fold(sentence)\n",
                                      "    if True:\n        return []\n    fold = L.fold(sentence)\n")],
                                    "K: a present-tense, negated or hedged statement on DIS passes (\"the findings fulfil DIS\")"),
    "C24_negation_after_the_verb_ignored": ([(STR, "    return bool(L.NEGATION.search(after[:cut.start()] if cut else after))\n",
                                              "    return False\n")],
                                            "K: a German denial after the verb (\"erfullt ... nicht\") read as an affirmation"),
    "C22_regenerations_not_validated": ([(VR,"    if isinstance(max_regenerations, bool) or not isinstance(max_regenerations, int) \\\n"
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
    "K1_kill_switch_ignored": ([(BRS, '        if getattr(self._settings, "REPORT_LLM_ENABLED", True) is not True:\n            return False, verified_report.REASON_OFF\n', "        if False:\n            return False, verified_report.REASON_OFF\n")],
                               "REPORT_LLM_ENABLED=false still calls the model"),
    "K2_kill_switch_setting_removed": ([(CFG, "    REPORT_LLM_ENABLED: bool = Field(default=True)\n", "")],
                                       "the environment cannot switch the model off"),
    # ── RC-106: the model ──
    "M1_allow_list_bypassed": ([(BRS, "        if not report_model_allowed(getattr(self._settings, \"CLAUDE_MODEL\", None)):\n", "        if getattr(self._settings, \"CLAUDE_MODEL\", None) is None:\n")],
                               "any configured model id is called"),
    "M2_retiring_default_back": ([(CFG, '    CLAUDE_MODEL: str = Field(default="claude-sonnet-5-5")\n',
                                   '    CLAUDE_MODEL: str = Field(default="claude-sonnet-4-5-20250929")\n')],
                                 "the default model is the one retiring on 2026-11-30 (the defect as found)"),
    "M3_retirement_date_ignored": ([(BRS, "    return retires is None or (today or date.today()) < date.fromisoformat(retires)\n", "    return True\n")],
                                   "an allow-listed model past its retirement date is still called"),
    "M4_sampling_parameter_sent": ([(BRS, "extra_body=copy.deepcopy(params), timeout=max(1.0, float(timeout_s)))", "extra_body=copy.deepcopy(params), timeout=max(1.0, float(timeout_s)), temperature=0.0)")],
                                   "a sampling parameter is sent (400 on the current models)"),
    "M5_answer_read_by_position": ([(BRS, '    text = "".join(_block_field(b, "text") or "" for b in blocks\n                   if _block_field(b, "type") == "text" and isinstance(_block_field(b, "text"), str))\n',
                                     '    text = (_block_field(blocks[0], "text") or "") if blocks else ""\n')],
                                   "the first block is read as the answer (a thinking block, as content[0].text did)"),
    "M6_provider_failure_propagates": ([(BRS, "            except Exception as e:  # noqa: BLE001 — every failure: the comments are not delivered, the report is\n",
                                         "            except ValueError as e:  # noqa: BLE001 — every failure: the comments are not delivered, the report is\n")],
                                       "a provider failure fails the report instead of giving the measurements only"),
    # (re-anchored with the tenth review of PR #78, I18: the minimum budget of every request)
    "M7_no_time_budget": ([(VR, "        if remaining < MIN_LLM_BUDGET_S:\n", "        if False:\n")], "the 25 s budget of a report is not enforced"),
    "M8_long_call_timeout": ([(BRS, "timeout=max(1.0, float(timeout_s)))", "timeout=600.0)")],
                             "one call may wait ten minutes (the SDK default)"),
    "M9_404_not_recognised": ([(BRS, '    if getattr(exc, "status_code", None) == 404 or name == "NotFoundError":\n', "    if False:\n")],
                              "a model the provider no longer serves is reported as a generic error"),
    "M10_sdk_retry_back": ([(BRS, "anthropic.AsyncAnthropic(api_key=api_key, max_retries=0, timeout=",
                             "anthropic.AsyncAnthropic(api_key=api_key, max_retries=1, timeout=")],
                           "R2: the SDK retries with a fresh full timeout (about twice the 25 s budget)"),
    "M11_wait_not_bounded": ([(BRS, "                    message = await asyncio.wait_for(message, timeout=float(timeout_s))\n", "                    message = await message\n")],
                             "R2: the wait for the provider is not bounded by the remaining budget"),
    "M12_retired_table_decides": ([(BRS, "    if entry is None:\n        return False\n    retires = entry.get(\"retires_on\")\n",
                                    "    if entry is None or model_id in RETIRED_OR_RETIRING_MODELS:\n        return False\n    retires = entry.get(\"retires_on\")\n")],
                                  "R9: a second allow mechanism (the retired table) next to the allow-list and its retirement date"),
    # ── third independent review of PR #78 (T1, T2, T3) ──
    "F20_volume_needs_both_units": ([(VR, "    elif ml_text is not None:\n        volume = t[\"volume_ml\"].format(ml=ml_text)\n",
                                      "    elif False:\n        volume = t[\"volume_ml\"].format(ml=ml_text)\n")],
                                    "T1: a volume in mL only is written \"not computed\" while its placeholder is filled"),
    "A7_withheld_reported_as_not_requested": ([(VR, "    return OUTCOME_WITHHELD if asked else NOT_REQUESTED\n",
                                                "    return NOT_REQUESTED\n")],
                                              "T2: a draft the AI was asked for and did not deliver is recorded as not requested"),
    "M13_sync_client_back": ([(BRS, "anthropic.AsyncAnthropic(api_key=api_key, max_retries=0, timeout=",
                               "anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=")],
                             "T3: the blocking client again (a request outlives the time budget in a worker thread)"),
    "M14_request_not_cancelled": ([(BRS, "                    message = await asyncio.wait_for(message, timeout=float(timeout_s))\n", "                    message = await asyncio.wait_for(asyncio.shield(message), timeout=float(timeout_s))\n")],
                                  "T3: the deadline ends the wait but the request keeps running (not cancelled)"),
    # ── fourth independent review of PR #78 (Q1-Q7) ──
    "C25_empty_comment_allowed": ([(VR, "    if not (_HAS_A_LETTER.search(fc) and _HAS_A_LETTER.search(ic)):\n", "    if False:\n")],
                                  "Q1: an empty or \".\" comment is checked as written and delivered"),
    "C26_template_tokens_allowed": ([(VR, "    if _TEMPLATE_TOKEN.search(fc + \"\\n\" + ic):\n", "    if False:\n")],
                                    "Q2: a raw template token ({Total_Count}, [PLACEHOLDER]) reaches a draft"),
    "C27_format_characters_kept": ([(VR, "    fc, ic = without_format_characters(m.group(1)).strip(), without_format_characters(m.group(2)).strip()\n",
                                     "    fc, ic = m.group(1).strip(), m.group(2).strip()\n")],
                                   "Q6: a zero-width joiner or a soft hyphen hides a phrase from the check"),
    "F22_indication_listed_not_available": ([(VR, "    dropped = ({0} if entry else set())",
                                              "    dropped = (set() if entry else set())")],
                                            "Q3: a typed indication is also listed as \"not available\""),
    "M15_not_configured_said_failed": ([(VR, "    REASON_NOT_CONFIGURED: \"not_configured\",\n",
                                         "    REASON_NOT_CONFIGURED: \"unavailable\",\n")],
                                       "Q4: no provider key: the note says the AI service failed"),
    "M16_wrapped_async_not_awaited": ([(BRS, "                if inspect.isawaitable(message):      # the request", "                if False:      # the request")],
                                      "Q5: an async create behind a plain wrapper is never awaited"),
    "M17_wiring_fault_read_as_answer": ([(BRS, "    if not isinstance(blocks, (list, tuple)):\n        raise ProviderWiringFault(",
                                          "    if False:\n        raise ProviderWiringFault(")],
                                        "Q5: something that is not a message is read as an empty answer (a check failure)"),
    "D2_notice_by_substring": ([(RT, "        stated_by_service = result.pop(\"dis_not_evaluated_stated\", False) is True\n",
                                 "        stated_by_service = result.pop(\"dis_not_evaluated_stated\", False) is True and False or "
                                 "gate.NOT_EVALUATED_LINE[\"en\"] in result[\"content\"]\n")],
                               "Q6: the route decides by a substring search over the processed text"),
    "P4_second_list_of_blocks": ([(RT, "MEASUREMENT_FINDING_KEYS = frozenset(RENDERED_FINDINGS)",
                                   "MEASUREMENT_FINDING_KEYS = frozenset({\"lesion_analysis\", \"dis_assessment\", \"longitudinal\"})")],
                                 "Q7: a second literal list of the blocks the report writes"),
    # ── RC-064: only what is rendered is sent and validated (second review, C, D, H) ──
    "P1_unrendered_fields_validated": ([(BRS, "            payload = project_measurements(rendered_findings, rendered_volumetry,   # (ninth review, I14)\n                                           gate_account=gate_account)            # the gate account (PR #81, R2)\n", "            payload = project_measurements(findings, volumetry, gate_account=gate_account)\n")],
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
    "T1_retired_words_back": ([(BRS, "    texts: List[str] = []\n", "    texts: List[str] = [UNLISTED, \"Structure Label\"]\n")],
                              "G: the retired templates' words widen the RC-065 vocabulary again"),
    "T2_first_message_built_twice": ([(BRS, "                    first_message=sent_text)", "                    first_message=None)")],
                                     "J: the first request is built a second time after the identifier check"),
    # ── RC-070: one guaranteed "not evaluated" statement (second review, F) ──
    "D1_notice_repeats_the_line": ([(RT, "    parts = [] if stated is True else [DIS_NOT_EVALUATED_NOTICE[lang]]\n",
                                     "    parts = [DIS_NOT_EVALUATED_NOTICE[lang]]\n")],
                                   "F: the route's notice repeats the \"not evaluated\" statement the draft already has"),
    # ── fifth independent review of PR #78 (V1-V10) ──
    "C29_number_words_allowed": ([(VR, '    if number_words(fc + "\\n" + ic, lang):\n', "    if False:\n")],
                                 "V1: a count written in words (\"Twelve lesions\") passes the check"),
    "C30_german_number_words_missed": ([(VR, '"zwei", "drei", "vier", "funf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwolf",\n', '"elf", "zwolf",\n')],
                                       "V1: German number words (\"zwei neue Kandidaten\") pass the check"),
    "L5_candidates_from_status_counts": ([(VR, '    if isinstance(cc, dict):\n        return _count(cc.get("new")), _count(cc.get("enlarging"))\n',
                                           '    if False:\n        return _count(cc.get("new")), _count(cc.get("enlarging"))\n')],
                                         "V2: the draft counts every new component, not the reviewable candidates"),
    "P5_candidates_not_projected": ([(GRD, '        if isinstance(cc, dict):\n            o["change_candidates"]',
                                      '        if False:\n            o["change_candidates"]')],
                                    "V2: the reviewable candidates never reach the record"),
    "F23_check_error_not_caught": ([(VR, "        except Exception as e:  # noqa: BLE001 — fifth review of PR #78, V3",
                                     "        except ZeroDivisionError as e:  # noqa: BLE001 — fifth review of PR #78, V3")],
                                   "V3: an error inside the check after the model answered fails the request (500)"),
    "A5_check_error_attempt_not_audited": ([(VR, "            attempts.append(record)\n            on_attempt(record)\n            return measurements_only(view, lang, REASON_INTERNAL_CHECK",
                                             "            attempts.append(record)\n            return measurements_only(view, lang, REASON_INTERNAL_CHECK")],
                                           "V3: the answered attempt of an internal check error is not audited"),
    "M18_client_per_request": ([(BRS, "    client = cache.get(api_key)\n", "    client = None\n")],
                               "V4: a new client and connection pool on every request"),
    "M19_client_not_closed": ([(BRS, "            done = close()\n", "            done = None\n")],
                              "V4: the shared client is never closed"),
    "M20_client_without_timeout": ([(BRS, "max_retries=0, timeout=verified_report.LLM_DEADLINE_S)", "max_retries=0)")],
                                   "V4: the client is built without the allowed time budget"),
    "M21_not_closed_at_shutdown": ([(MAIN, "        from app.services.brain_report_service import close_report_clients\n        await close_report_clients()\n",
                                     "        pass\n")],
                                   "V4: the application shutdown does not close the shared client"),
    "K3_record_read_when_nothing_is_sent": ([(RT, '    if not hasattr(service, "interpretive_text_gate") or service.interpretive_text_gate()[0] is not False:\n', "    if True:\n")],
                                            "V5: kill switch off, the route still needs the patient record (503)"),
    # (rewritten with the eleventh review of PR #78, M2: the service no longer imports provider_payload — the mutant
    # reaches the guard's function itself, so it imports and runs; I15)
    "P6_patient_numbers_checked_when_nothing_sent": ([(BRS, "            payload = project_measurements(rendered_findings, rendered_volumetry,   # (ninth review, I14)\n                                           gate_account=gate_account)            # the gate account (PR #81, R2)\n", "            payload = __import__(\"app.services.report_payload_guard\", fromlist=[\"provider_payload\"]).provider_payload(rendered_findings, rendered_volumetry, identifiers if isinstance(identifiers, PatientIdentifiers) else None, gate_account=gate_account)\n")],
                                                     "V5: provider-only refusals apply when nothing is sent"),
    "P7_identifiers_not_required_when_sending": ([(BRS, "                if not isinstance(ids, PatientIdentifiers):\n", "                if False:\n")],
                                                 "V5: a request is sent without the patient's identifiers"),
    "F24_limitations_ignore_drawn_labels": ([(VR, "    dropped = ({0} if entry else set()) | set(drawn) |", "    dropped = ({0} if entry else set()) |")],
                                            "V6: contrast-enhanced and T1-weighted imaging listed as not available although labels were drawn on them"),
    "C31_check_rebuilds_the_combination": ([(VR, "    res = S.verify(assembled, None, view, model_text=(fc, ic))\n",
                                             "    res = V.verify(assembled, None, view)\n    res = {**res, \"elements\": list(res[\"elements\"]) + S.comment_elements(fc, view) + S.comment_elements(ic, view), \"headings\": S.heading_lines(fc) + S.heading_lines(ic)}\n")],
                                           "V7: check() rebuilds the combination itself (another path than the property tests)"),
    "D3_service_notice_missing": ([(BRS, '            if dis_evaluation == "not_evaluated" and _review_source(findings) in AUTOMATIC_REVIEW_SOURCES:\n', "            if False:\n")],
                                  "V8: the draft without an evaluated DIS has no notice on automatic marking"),
    "D4_dis_evaluation_not_typed": ([(BRS, '            "dis_evaluation": dis_evaluation,\n', '            "dis_evaluation": None,\n')],
                                    "V8: the response does not say whether DIS was evaluated"),
    "F25_dis_line_without_lesion_findings": ([(VR, "    else:\n        # no DIS block in the request", "    elif True:\n        view[\"dis\"] = {\"status\": \"not evaluated\"}\n    else:\n        # no DIS block in the request")],
                                             "V9: a volumetry-only or longitudinal-only draft states \"DIS not evaluated\""),
    "C32_criterion_counted_twice": ([(STR, " and len(between.split()) <= DIS_WORDS_APART and m.span() not in spans:\n",
                                      " and len(between.split()) <= DIS_WORDS_APART:\n")],
                                    "V10: a criterion word near two DIS names is counted twice"),
    # ── sixth independent review of PR #78 (W1-W3) ──
    "L6_null_count_notice_as_zero": ([(VR, '        return texts["not_computed"] if lng.get("reason") == "change candidates not computed" else texts["abstained"]\n',
                                       '        return texts["candidates"].format(total=0, new=0, enl=0) if lng.get("reason") == "change candidates not computed" else texts["abstained"]\n')],
                                     "W1: a null or missing count is stated as 0 candidates in the notice"),
    "L7_notice_not_from_the_record": ([(BRS, "            change = report_change_notice(view, lang, gate_account)\n", "            change = None\n")],
                                      "W1: the draft has no change notice from its own record"),
    "F26_any_entry_names_the_indication": ([(VR, '    entry = (view.get("clinician_entry") or {}).get("clinical_indication") is True   # sixth review, W2\n',
                                             '    entry = bool(view.get("clinician_entry"))   # sixth review, W2\n')],
                                           "W2: a typed technique or observation is called the clinician's indication"),
    "P8_one_flag_for_every_field": ([(GRD, '        out["clinician_entry"] = entered\n',
                                      '        out["clinician_entry"] = {k: True for k in FREE_TEXT_FIELDS}\n')],
                                    "W2: any typed field flags every field (the indication too)"),
    "C33_size_and_unit_counts_missed": ([(VR, "        if cardinal and k <= 2 and size.fullmatch(nxt.group(0)):\n", "        if False:\n")],
                                        "W3: \"four small, ten medium\" and \"seven point two millimeters\" pass the check"),
    "C34_count_heads_missed": ([(VR, "            if prev.group(0) in _COUNT_HEADS_ANY:\n", "            if False:\n")],
                               "W3: \"the total count of lesions is twenty-five\" passes the check"),
    "C35_every_number_word_fails": ([(VR, "if tok.group(0) in words and _counts(fold, tokens, i, lang)]", "if tok.group(0) in words]")],
                                    "W3: the over-broad rule again (\"both hemispheres\", \"a single FLAIR sequence\" fail)"),
    "C36_quantifier_window_unbounded": ([(VR, "_QUANTIFIER_WINDOW = 2 ", "_QUANTIFIER_WINDOW = 4 ")],
                                        "W3: \"both small and large lesions\" read as a count"),
    "C37_hyphenated_word_counted_twice": ([(VR, '        k += 0 if gap == "-" else 1', "        k += 1")],
                                          "W3: \"a single medium-sized lesion\" passes the check"),
    # ── seventh independent review of PR #78: the clinical invariants of the scenario matrix ──
    "D5_dis_line_tied_to_lesions": ([(VR, "    elif isinstance(dis_block, dict):\n        # seventh review of PR #78, finding 1 (I2)",
                                      "    elif la is not None:\n        # seventh review of PR #78, finding 1 (I2)")],
                                    "I2: an unevaluated DIS without a lesion analysis is silently dropped"),
    "F27_lesion_block_always": ([(VR, "    lesions_in = les.get(\"computed\") is True\n", "    lesions_in = True\n")],
                                "I1: a volumetry-only draft writes \"lesion count: not computed\" and lesion impressions"),
    "A6_not_sent_after_calls": ([(BRS, "        if called:\n            # seventh review", "        if False:\n            # seventh review")],
                                "I8: an exception after model calls is audited as not sent, 0 attempts"),
    "L8_small_new_lesions_dropped": ([(VR, '            if isinstance(lng.get("change_candidates"), dict) and sc_new is not None and sc_new > cands["new"]:\n',
                                       "            if False:\n")],
                                     "I4: new lesions below the review size vanish from the draft"),
    "C39_german_compounds_missing": ([(VR, '    words += [u + "und" + t for u in units for t in tens]\n', "")],
                                     "finding 5: \"einundzwanzig Läsionen\" passes the check"),
    "K4_all_not_available_commented": ([(VR, '    lesion_value = les.get("computed") and (', '    lesion_value = les.get("computed") or (')],
                                       "I7: the model is asked to comment on a lesion analysis without any value"),
    "D6_marking_notice_for_any_source": ([(BRS, "            if dis_evaluation == \"not_evaluated\" and _review_source(findings) in AUTOMATIC_REVIEW_SOURCES:\n",
                                           "            if dis_evaluation == \"not_evaluated\":\n")],
                                         "I5: the automatic-marking notice on a manual segmentation"),
    "M22_record_read_when_nothing_is_sent": ([(BRS, "            ids = None\n            payload = project_measurements(rendered_findings, rendered_volumetry,   # (ninth review, I14)\n                                           gate_account=gate_account)            # the gate account (PR #81, R2)\n", "            ids = (await identifiers() if callable(identifiers) else identifiers) if allowed else None\n            payload = project_measurements(rendered_findings, rendered_volumetry,   # (ninth review, I14)\n                                           gate_account=gate_account)            # the gate account (PR #81, R2)\n")],
                                             "finding 8: the patient record is read (and its failure refuses) with nothing to send"),
    # ── eighth independent review of PR #78: the device never contradicts itself (I9-I11) ──
    "L9_below_size_line_split": ([(VR, '"lng_below_size": "A further {k} new lesion(s) smaller than {d} mm were marked below the minimum size for "',
                                   '"lng_below_size": "A further {k} new lesion(s) smaller than {d} mm were marked; they are below the minimum size for "')],
                                 "I9: the code-written below-size line fails the device's own check"),
    "L10_notice_cites_an_unchecked_date": ([(VR, 'of all the candidates it "\n                    "proposed ({source}).",',
                                             'of all the candidates it "\n                    "proposed ({source}, 2026-10-22).",')],
                                           "I9: the change notice states numbers the record does not hold"),
    "C40_prompt_asks_for_a_dis_statement": ([(VR, "3. Say nothing about dissemination in space: the software writes its state",
                                              "3. If dissemination in space was not evaluated, write that dissemination in space was not evaluated and say nothing else about it; the software writes its state")],
                                            "I10: the instructions ask for a DIS sentence the check refuses"),
    "C41_sequence_names_counted_as_digits": ([(VR, 're.sub(r"\\{[a-z_]+\\}|\\b[Tt][12]\\b", "", fc + " " + ic)', 're.sub(r"\\{[a-z_]+\\}", "", fc + " " + ic)')],
                                             "I10: \"T1-weighted images were not provided\" (rule 1) fails the digits rule"),
    "L11_stable_count_required": ([(VR, "        if new is None or enlarged is None:\n", "        if any(v is None for v in cands.values()):\n")],
                                  "I11: the draft says \"not computed\" where the review screen shows the candidates"),
    "M23_record_read_before_deciding": ([(BRS, "            ids = None\n            payload = project_measurements(rendered_findings, rendered_volumetry,   # (ninth review, I14)\n                                           gate_account=gate_account)            # the gate account (PR #81, R2)\n", "            ids = (await identifiers() if callable(identifiers) else identifiers) if allowed else None\n            payload = project_measurements(rendered_findings, rendered_volumetry,   # (ninth review, I14)\n                                           gate_account=gate_account)            # the gate account (PR #81, R2)\n")],
                                        "finding 3: an unreadable record refuses a draft that would send nothing"),
    "F28_empty_impression_heading": ([(VR, "    if imp or impression_comment:\n", "    if True:\n")],
                                     "finding 7: an empty Impression heading on a volumetry-only draft"),
    "C42_other_languages_cardinals_ignored": ([(VR, "_CARDINALS_OF = {lang: frozenset(_CARDINALS[lang]) | frozenset(",
                                                "_CARDINALS_OF = {lang: frozenset(_CARDINALS[lang]) | frozenset() & frozenset(")],
                                              "finding 8: \"two lesions\" in a German report passes the check"),
    # (re-anchored with the eleventh review of PR #78, C4: the module's own minimal enumeration of the branches)
    "F29_synthetic_payloads_without_the_matrix": ([(VR, "    for findings, volumetry, source in _branch_requests():\n",
                                                    "    for findings, volumetry, source in list(_branch_requests())[:0]:\n")],
                                                  "finding 6: branches of the draft missing from the RC-065 device words"),
    # ── ninth independent review of PR #78: I12-I14 and findings 1, 7, 8 ──
    "F30_exact_count_from_twenty_in_the_record": ([(VR, '            "total_count": n if n is not None and n < 20 else None,\n',
                                                    '            "total_count": n,\n')],
                                                  "I12: from 20 lesions the exact count reaches the record sent to the model"),
    "F31_exact_visit_totals_in_the_record": ([(VR, '                "visit_1": {**_magnims_count(_count(lng.get("total_lesions_tp1"))),\n',
                                               '                "visit_1": {"total_count": _count(lng.get("total_lesions_tp1")),\n')],
                                             "I12: an exact visit total from 20 lesions reaches the record"),
    "L12_status_counts_relabelled": ([(VR, "    # counts every new component, below the review size too, and is never relabelled as reviewable candidates\n    return None, None\n",
                                       "    # counts every new component, below the review size too, and is never relabelled as reviewable candidates\n    sc = lng.get(\"status_counts\") or {}\n"
                                       "    return _count(sc.get(\"new\")), _count(sc.get(\"enlarged\"))\n")],
                                     "I13: without the candidate block every new component is stated as a reviewable candidate"),
    "P9_implausible_value_as_an_ai_error": ([(RT, "    except ImplausibleMeasurement as e:\n", "    except ZeroDivisionError as e:\n")],
                                            "I14: an implausible measurement answers 'not sent to the AI service' (503)"),
    "P10_provider_payload_on_every_draft": ([(BRS, "            payload = project_measurements(rendered_findings, rendered_volumetry,   # (ninth review, I14)\n                                           gate_account=gate_account)            # the gate account (PR #81, R2)\n",
                                              "            payload = provider_payload(rendered_findings, rendered_volumetry, None, gate_account=gate_account)   # (ninth review, I14)\n")],
                                            "I14: the provider payload is built with nothing to send"),
    # (re-anchored with the tenth review of PR #78, finding 8: the time left is computed once, just before the call)
    "M24_budget_from_the_first_decision": ([(BRS, "                left = (verified_report.REQUEST_BUDGET_S - verified_report.RESPONSE_MARGIN_S\n"
                                                  "                        - (verified_report.now() - started))\n",
                                             "                left = verified_report.REQUEST_BUDGET_S - verified_report.RESPONSE_MARGIN_S\n")],
                                           "finding 1: the model gets a budget that ignores the time the record and the word list took"),
    # (C43, C44 re-anchored with the tenth review of PR #78, finding 7: a store of successful reads only)
    "C43_evidence_read_on_every_record": ([(LCS, "    _EVIDENCE_FILES[path_str] = asset\n", "")],
                                          "finding 7: the evidence JSON is read from disk for every record"),
    "C44_rule_check_served_from_the_cache": ([(LCS, "def load_false_candidate_evidence(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:\n",
                                               "@__import__(\"functools\").lru_cache(maxsize=4)\n"
                                               "def load_false_candidate_evidence(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:\n")],
                                             "finding 7 done wrongly: the rate is served from a cache after the rule in force changed"),
    "F33_frozen_check_without_the_range": ([(STR, "    res = V.verify(authored, delivered, as_the_frozen_check_reads_it(view))\n",
                                             "    res = V.verify(authored, delivered, view)\n")],
                                           "I12 done wrongly: the frozen check reads a record without a count and refuses every "
                                           "comment from 20 lesions upward"),
    "F34_range_placeholder_dropped": ([(VR, '    elif cat and cat != "exact":\n        vals["total_count"] = cat\n', "")],
                                      "I12 done wrongly: from 20 lesions the {total_count} placeholder is no longer available"),
    # ── tenth independent review of PR #78: I16-I19 and findings 5, 7, 9 (DRAFT, PENDING owner approval) ──
    "C45_implausible_without_its_code": ([(RT, '        raise ReportError("implausible_measurement", status.HTTP_422_UNPROCESSABLE_ENTITY,\n',
                                           '        raise ReportError("report_failed", status.HTTP_422_UNPROCESSABLE_ENTITY,\n')],
                                         "I16: the implausible measurement leaves without its own code (the panel cannot name it)"),
    "C46_shared_check_uncoded": ([(RT, "                raise _coded(e) from e\n", "                raise\n")],
                                 "I16: a shared check's HTTP error (authorization, the store) leaves without a code"),
    "C47_implausible_asks_to_correct_the_input": ([(RT, "{e.field or 'unknown'}. No draft was written; re-run the analysis or check the segmentation.\",\n",
                                                    "{e.field or 'unknown'}. Correct the input; no draft was written.\",\n")],
                                                  "I16: the physician is asked to correct an input the server computed itself"),
    "A8_privacy_passed_before_the_checks": ([(BRS, '            privacy = "not_run"\n', '            privacy = "passed"\n')],
                                            "I17: the record says the privacy check passed although it did not run"),
    "A9_cancelled_call_not_recorded": ([(VR, "        except asyncio.CancelledError:\n", "        except ZeroDivisionError:\n")],
                                       "I17: a model call cancelled in flight is not counted"),
    "A10_cancelled_request_not_audited": ([(BRS, "        except BaseException as e:  # noqa: BLE001 — every exit is audited",
                                            "        except Exception as e:  # noqa: BLE001 — every exit is audited")],
                                          "I17: a cancelled request writes no verification record"),
    "M25_retry_below_the_minimum_budget": ([(VR, "        if remaining < MIN_LLM_BUDGET_S:\n", "        if remaining <= 0:\n")],
                                           "I18: a retry is sent with less than the minimum budget left"),
    "M26_skipped_retry_as_timeout": ([(VR, "            if attempt:\n                return measurements_only(view, lang, REASON_BLOCKED, attempts, outcome=OUTCOME_WITHHELD,\n",
                                       "            if attempt:\n                return measurements_only(view, lang, REASON_TIMEOUT, attempts, outcome=OUTCOME_WITHHELD,\n")],
                                     "I18: a retry skipped for lack of time is reported as an AI-service timeout"),
    # (re-anchored with the eleventh review of PR #78, C3: the conversion now covers every failure of a regeneration)
    "M27_cut_retry_as_timeout": ([(VR, "            if attempt:\n                # I18 (tenth review: a retry cut",
                                   "            if False:\n                # I18 (tenth review: a retry cut")],
                                 "I18: a retry cut by the time budget is reported as an AI-service timeout"),
    "F35_nothing_to_report_before_the_substitutions": ([(RT, "    if not verified_report.renderable(findings, request.volumetry):\n"
                                                            "        raise ReportError(\"nothing_to_report\", status.HTTP_422_UNPROCESSABLE_ENTITY, NOTHING_TO_REPORT_DETAIL)\n", "")],
                                                       "I19: a block that held only a dropped reader decision gives a draft of the limitations alone"),
    # (re-anchored with the eleventh review of PR #78: the tripwire's own handler, C1, made the line occur twice)
    "P11_patient_number_as_503": ([(BRS, "                except IdentifierInPrompt:\n                    # tenth review, finding 5",
                                    "                except ZeroDivisionError:\n                    # tenth review, finding 5")],
                                  "finding 5: a measurement equal to a patient number ends in a 503 without a draft"),
    "P12_projected_payload_not_checked": ([(GRD, "        if is_patient_number(n, forms):       # (tenth review, finding 9: the projection's own rule)\n",
                                            "        if False:\n")],
                                          "finding 9: the patient's own numbers are not looked for in the projected payload"),
    "C48_failed_read_cached": ([(LCS, "    kept = _EVIDENCE_FILES.get(path_str)\n    if kept is not None:\n        return kept\n",
                                 "    if path_str in _EVIDENCE_FILES:\n        return _EVIDENCE_FILES[path_str]\n"),
                                (LCS, '        logger.warning(f"[RC-061] evidence asset unreadable: {e}")\n        return None\n',
                                 '        logger.warning(f"[RC-061] evidence asset unreadable: {e}")\n        _EVIDENCE_FILES[path_str] = None\n        return None\n')],
                               "finding 7: a transient read error withholds the rate until the server restarts"),
    # ── eleventh (final) independent review of PR #78: L1, L2, C1-C4, C7, M1 (DRAFT, PENDING owner approval) ──
    "N1_notice_claims_sex_and_age": ([("frontend/src/i18n/locales/en.json",
                                       "only the measurements \u2014 the lesion count",
                                       "only the measurements, sex and a 5-year age range \u2014 the lesion count")],
                                     "L1: the panel notice says sex and an age band are sent again"),
    "F36_partial_bracket_dropped": ([(VR, '    _t["lng_ok_partial"] = _partial\n',
                                      '    _t["lng_ok_partial"] = re.sub(r"\\s*\\([^)]*\\{res_part\\}[^)]*\\)", "", _partial)\n')],
                                    "L2: a partial comparison drops every computed resolved / shrunk / stable count"),
    "P13_identifier_hit_as_503": ([(BRS, "                except IdentifierInPrompt:\n                    # eleventh review of PR #78, C1",
                                    "                except ZeroDivisionError:\n                    # eleventh review of PR #78, C1")],
                                  "C1: an identifier-pattern hit in device-written text ends in a 503 without a draft"),
    "A11_skipped_retry_counted": ([(VR, "            if attempt:\n                return measurements_only(view, lang, REASON_BLOCKED, attempts, outcome=OUTCOME_WITHHELD,\n"
                                        "                                         tokens=tuple(tokens), model_answered=answered, retry_skipped_budget=True)\n",
                                    "            if attempt:\n                attempts.append({**record, \"verdict\": \"not_sent\", \"rule_ids\": []})\n"
                                    "                on_attempt(attempts[-1])\n"
                                    "                return measurements_only(view, lang, REASON_BLOCKED, attempts, outcome=OUTCOME_WITHHELD,\n"
                                    "                                         tokens=tuple(tokens), model_answered=answered, retry_skipped_budget=True)\n")],
                                  "C2: a retry the budget skipped is counted as an attempt (verification and audit)"),
    "A12_asked_without_a_request": ([(BRS, '        asked = any(a.get("verdict") != "not_sent" for a in result.attempts)\n',
                                      "        asked = bool(result.attempts)\n")],
                                    "C7: a draft with no request sent names a model and a token count"),
    "M28_retry_provider_error_as_unavailable": ([(VR, "            if attempt:\n                # I18 (tenth review: a retry cut",
                                                  "            if attempt and e.reason == REASON_TIMEOUT:\n                # I18 (tenth review: a retry cut")],
                                                "C3: a regeneration's provider error after a failed answer reads 'could not be obtained'"),
    "M29_word_list_built_in_the_first_request": ([("backend/app/main.py",
                                                   "        from app.services.brain_report_service import warm_report_word_lists\n"
                                                   "        await asyncio.to_thread(warm_report_word_lists)\n", "        pass\n")],
                                                 "C4: the device-word list is built inside the first request's budget"),
    "C49_label_for_a_field_never_checked": ([("frontend/src/components/AIReportPanel.tsx",
                                              "  regions_with_lesions: 'number of regions with lesions',",
                                              "  regions_with_lesions: 'number of regions with lesions', total_dis_regions: 'number of regions with lesions',")],
                                            "M1: the panel names a measurement that can never be refused as implausible"),
    "F32_format_rule_twice": ([(RT, "        # (ninth review of PR #78, finding 8: CAPA-014's format-character rule runs once, inside neutralised_model_text\n",
                                '        result = {**result, "content": without_format_characters(result["content"])}\n'
                                "        # (ninth review of PR #78, finding 8: CAPA-014's format-character rule runs once, inside neutralised_model_text\n")],
                              "finding 8: the route runs the format-character rule a second time"),
}

# Fifth review of PR #78, V8: the route's DIS notice and its `stated` fact were removed — the report service owns the
# statement and the notice (controls D3, D4, F25 and the review5 tests); these two mutations have no code left to act on.
# Replaced by: D3, D4, F25.
RETIRED_WITH_THE_ROUTE_NOTICE = {name: M.pop(name)[1] for name in ("D1_notice_repeats_the_line", "D2_notice_by_substring")}
# Seventh review of PR #78, finding 8: the route asks no gate any more (the service's one gate reads the record lazily);
# the same defect is now M22. Replaced by: M22 (and M23).
RETIRED_WITH_THE_LAZY_READER = {name: M.pop(name)[1] for name in ("K3_record_read_when_nothing_is_sent",)}
# Ninth review of PR #78, I12: from 20 lesions upward the record holds the MAGNIMS range only, so R5's defect (the
# {total_count} placeholder giving the exact count) has no exact count left to give; its line was rewritten.
# Replaced by: F1, F34 and test_rc102_i12_from_twenty_lesions_only_the_magnims_range_is_shown.
RETIRED_WITH_THE_RANGE_ONLY_RECORD = {name: M.pop(name)[1] for name in ("C14_exact_count_placeholder",)}
# Eleventh review of PR #78, M2: the service no longer imports provider_payload, so P10's defect (the provider payload
# built in the service with nothing to send) cannot be written there; its mutant would die by NameError (I15).
# Replaced by: test_m2_no_unused_names and test_rc105_i14_the_provider_payload_runs_only_when_a_call_will_happen.
RETIRED_WITH_THE_UNUSED_IMPORT = {name: M.pop(name)[1] for name in ("P10_provider_payload_on_every_draft",)}


def offline_env():
    """PRB-002: backend tests never reach a real cloud service or the model provider."""
    env = dict(os.environ)
    empty = tempfile.mkdtemp(prefix="verified-report-no-gcloud-")
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(empty, "no-such-credentials.json"),
                "CLOUDSDK_CONFIG": empty, "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests"})
    for name in ("ANTHROPIC_API_KEY", "FIRESTORE_EMULATOR_HOST", "PYTHONPATH"):
        env.pop(name, None)
    # lighter on the owner's disk: no byte-code files written for each mutated source
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _progress_path(key):
    """Results of the mutations already run on these very sources and tests (so a run cut by a crash resumes, never
    restarts); keyed by their hashes, not by the commit, so a later commit of documents does not matter."""
    return os.path.join(tempfile.gettempdir(), f"verified-report-nc-progress-{key}.json")


def _load_progress(key, source_sha, test_sha):
    try:
        with open(_progress_path(key), encoding="utf-8") as fh:
            p = json.load(fh)
    except (OSError, ValueError):
        return {}
    # only results of the very same sources and tests are kept
    if p.get("source_sha256") != source_sha or p.get("test_sha256") != test_sha:
        return {}
    return p


def _save_progress(key, res):
    tmp = _progress_path(key) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({k: res[k] for k in ("source_sha256", "test_sha256", "baseline", "mutations", "executed")}, fh)
    os.replace(tmp, _progress_path(key))


def run_tests():
    # light mode on the owner's laptop (NC_LIGHT=1): the tests marked slow run in CI only, and no test may hang
    light = ["-m", "not slow", "--timeout=120"] if os.environ.get("NC_LIGHT") == "1" else []
    r = subprocess.run([PY, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "-o",
                        "log_cli=false", *light], cwd="backend", capture_output=True, text=True, encoding="utf-8",
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


def _arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def main():
    global OUT
    only = _arg("--only")       # comma-separated mutation names: a partial round (its own record, --out)
    if only:
        wanted = [n.strip() for n in only.split(",") if n.strip()]
        unknown = [n for n in wanted if n not in M]
        if unknown:
            raise SystemExit(f"unknown mutations: {unknown}")
        for name in [n for n in M if n not in wanted]:
            del M[name]
        if not _arg("--out"):
            raise SystemExit("a partial round (--only) needs its own record: --out <path>")
    OUT = _arg("--out") or OUT
    files = sorted({e[0] for edits, _w in M.values() for e in edits})
    tests = [f"backend/{t}" for t in TESTS]
    require_committed(files + tests + [os.path.relpath(__file__, REPO).replace(os.sep, "/")])
    commit = _git("rev-parse", "HEAD").stdout.strip()
    if "--here" in sys.argv:
        # In a checkout that is itself disposable (an isolated agent worktree): mutate here, restore byte for byte,
        # and refuse to finish unless the mutated files are unchanged against the commit afterwards.
        res = run_in_worktree(files, commit)
        require_committed(files)
        res["worktree"] = {"run_in": "the current checkout (--here: an isolated, disposable worktree), clean before "
                                     "and after for every mutated file", "commit": commit, "python": PY}
        return _write(res)
    stale = clean_stale()
    wt = os.path.join(tempfile.gettempdir(), f"{PREFIX}{os.getpid()}-{int(time.time())}")
    _git("worktree", "add", "--detach", wt, commit)
    try:
        os.chdir(wt)
        res = run_in_worktree(files, commit)
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


def run_in_worktree(files, commit):
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
        source_sha = {p: sha(text[p]) for p in files}
        test_sha = {t: sha(open(os.path.join("backend", t), encoding="utf-8").read().replace("\r\n", "\n"))
                    for t in TESTS}
        key = sha(json.dumps([source_sha, test_sha], sort_keys=True))[:16]
        previous = _load_progress(key, source_sha, test_sha)
        res = {"executed": previous.get("executed") or datetime.datetime.now().isoformat(timespec="seconds"),
               "method": "one mutation at a time; each anchor asserted to occur exactly once (LF text, written back "
                         "with the file's own line endings); the bound backend tests with no cloud credential "
                         "(PRB-002), run one after the other, never in parallel; original bytes restored after each "
                         "mutation, at exit and on a signal, and checked at the end; the baseline must pass first; a "
                         "run cut by a crash resumes from the results already recorded for the same commit, sources "
                         "and tests",
               "hash_basis": "sha256 of the UTF-8 text with LF line endings",
               "source_sha256": source_sha, "test_sha256": test_sha,
               "tests": TESTS, "baseline": previous.get("baseline") or run_tests(),
               "mutations": dict(previous.get("mutations") or {})}
        if previous:
            res["resumed"] = {"from": _progress_path(key), "mutations_kept": sorted(res["mutations"]),
                              "at": datetime.datetime.now().isoformat(timespec="seconds")}
        base = res["baseline"]
        if base["failed"] or base["errors"] or not base["passed"]:
            raise SystemExit(f"the baseline must pass before the mutations mean anything: {base}")
        print("baseline ok", base["passed"], "passed", "(resumed: %d kept)" % len(res["mutations"]) if previous else "",
              flush=True)
        _save_progress(key, res)
        for name, (edits, what) in M.items():
            if name in res["mutations"]:
                continue
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
            _save_progress(key, res)
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
