"""Negative controls for the agent platform (RC-110 .. RC-120) — reproducible evidence.

DRAFT, PENDING owner approval. Each mutation re-introduces ONE defect a control exists to prevent, one at a time;
the script asserts the anchor occurs exactly once (the sabotage really was applied), runs the agent-platform
suites, records the failing test names and restores the file. A mutation that no test detects is listed under
"undetected" and makes the script exit non-zero.

Second review of PR #79, finding 10: the mutations are NEVER written into the real checkout. Each round copies
what the suites need (backend/app, backend/tests, pytest.ini, requirements.txt, the agent-platform documents and
this script) into a throwaway directory under the system temp folder, mutates and tests THERE, and deletes it at
the end. A hard kill (power loss, blue screen) can at worst leave a sabotaged temp copy outside the repository.
``tests/agent_platform/test_review2.py`` (CI) fails if any mutation is ever found in the tracked sources.
Loading this module has no side effect (no chdir, no write).

Light load by design: one pytest process at a time, only tests/agent_platform/, no credentials.
    backend/venv/Scripts/python scripts/safety/agent_platform_negative_controls.py             # full round
    backend/venv/Scripts/python scripts/safety/agent_platform_negative_controls.py --only A,B "reason"
Output: docs/iec62304/records/risk_verification/AGENT-PLATFORM_negative_controls_2026-11-10.json
"""
import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = str(REPO)
PY = str(REPO / "backend" / "venv" / "Scripts" / "python.exe")
if not os.path.exists(PY):
    PY = os.environ.get("AGENT_NC_PYTHON", sys.executable)
OUT = REPO / "docs" / "iec62304" / "records" / "risk_verification" / "AGENT-PLATFORM_negative_controls_2026-11-10.json"
TESTS = ["tests/agent_platform/"]
COPY = ("backend/app", "backend/tests", "backend/pytest.ini", "backend/requirements.txt",
        "docs/iec62304/agent_platform", "scripts/safety/agent_platform_negative_controls.py")

P = "backend/app/agent_platform/"
REG, UNT, TRC, RUN = P + "registry.py", P + "untrusted.py", P + "tracing.py", P + "runtime.py"
PRV, OVS, CRD, EVL = P + "provenance.py", P + "oversight.py", P + "cards.py", P + "evals.py"
GRADER = "backend/tests/agent_platform/graders/report_verifier_v3/verifier.py"
MCPB = "backend/app/mcp/_backend.py"
NCS = "scripts/safety/agent_platform_negative_controls.py"

M = {  # name: (file, anchor, replacement, control, what it re-introduces)
    # ---------------------------------------------------------------- registry
    "R1_write_tools_allowed": (REG, 'ALLOWED_TOOL_ACCESS = frozenset({"read", "compute"})',
                               'ALLOWED_TOOL_ACCESS = frozenset({"read", "compute", "write"})', "RC-110",
                               "an agent may call a write tool"),
    "R2_unapproved_agent_runs": (REG, '        if spec.approval_status != "approved":\n', "        if False:\n", "RC-110",
                                 "an agent the owner has not approved runs"),
    "R3_kill_switch_ignored": (REG, "            on = self._switches.is_on(agent_id) is True\n", "            on = True\n",
                               "RC-111", "the kill switch is not read"),
    "R4_unreadable_switch_is_on": (REG, "            return self._refuse(RefusalCode.SWITCH_UNREADABLE, agent_id=agent_id, trace_id=trace_id)\n",
                                   "            on = True\n", "RC-111", "a switch that cannot be read counts as on"),
    "R5_retirement_ignored": (REG, "            if days_left <= 0:\n", "            if days_left < -36500:\n", "RC-110",
                              "a retired model is still called"),
    "R6_model_allow_list_ignored": (REG, "        if model_id not in self._agents[agent_id].allowed_models:\n",
                                    "        if False:\n", "RC-110", "any registered model may be used by any agent"),
    "R7_candidate_model_used": (REG, '        if entry.use_status != "in_use":\n', "        if False:\n", "RC-110",
                                "a candidate (not re-validated) model is called"),
    "R8_study_cap_ignored": (REG, "            if self._study.get((agent_id, study_key), 0.0) + usd > study_cap + 1e-12:\n",
                             "            if False:\n", "RC-112", "no cost cap per study"),
    "R9_day_cap_ignored": (REG, "            if self._day.get((agent_id, day), 0.0) + usd > day_cap + 1e-12:\n",
                           "            if False:\n", "RC-112", "no cost cap per day"),
    "R10_fuzzy_model_id": (REG, "        entry = self.model(model_id) if isinstance(model_id, str) and _MODEL_ID.fullmatch(model_id) else None\n",
                           "        entry = self.model(model_id.strip().lower()) if isinstance(model_id, str) else None\n",
                           "RC-115", "a look-alike or padded model id is accepted"),
    "R11_env_switch_lenient": (REG, '        return isinstance(value, str) and value.strip().lower() == "on"\n',
                               '        return isinstance(value, str) and value.strip().lower() in ("on", "true", "1")\n',
                               "RC-111", "the environment switch accepts values other than exactly 'on'"),
    "R12_invalid_registry_used": (REG, "        self.valid = not self.errors\n", "        self.valid = True\n", "RC-110",
                                  "a registry that does not validate is used"),
    "R13_refusals_not_audited": (REG, '        self.audit("denied", code, **ctx)\n', "        pass\n", "RC-110",
                                 "refusals leave no audit record"),
    "R14_trailing_newline_id": (REG, '_AGENT_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")',
                                '_AGENT_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\\n?$")', "RC-110",
                                "an agent id with a trailing newline is accepted"),
    # ---------------------------------------------------------------- untrusted content and scope
    "U1_markup_not_escaped": (UNT, '    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")\n',
                              "    return text\n", "RC-113", "untrusted text can close its data block"),
    "U2_file_names_quoted": (UNT, '    "file_name": WITHHOLD,', '    "file_name": QUOTE,', "RC-113",
                             "file names (patient names, dates) reach the model"),
    "U3_invisible_chars_kept": (UNT, "    clean = _strip_invisible(raw)\n", "    clean = raw\n", "RC-113",
                                "direction and zero-width characters reach the model"),
    "U4_no_length_cap": (UNT, "    truncated = len(clean) > max_chars\n", "    truncated = False\n", "RC-112",
                         "untrusted text of any length reaches the model"),
    "U5_argument_scope_off": (UNT, "    bad = _scope_walk(arguments, 0, scope, invalid=RefusalCode.TOOL_ARGUMENTS_INVALID, locations=True)\n",
                              "    bad = None\n", "RC-114", "a tool call may name another patient's record"),
    "U6_undeclared_arguments_accepted": (UNT, "        if kind is None or not _kind_ok(kind, value):\n",
                                         "        if kind is not None and not _kind_ok(kind, value):\n", "RC-114",
                                         "a tool call may carry arguments its schema does not declare"),
    "U7_ids_not_compared_with_scope": (UNT, "        return None if scope.allows(value) else RefusalCode.OUT_OF_SCOPE_RESOURCE\n",
                                       "        return None\n", "RC-114",
                                       "ids in tool calls and results are not compared with the run's study"),
    "U8_identifiers_kept": (UNT, "    cleaned = assistant_view(result)       # the MCP client's own rule: no identifier, no unconfirmed activity flag\n",
                            "    cleaned = result\n", "RC-113",
                            "identifiers in tool results reach the model"),
    "U9_result_size_unbounded": (UNT, '    if len(serialized.encode("utf-8")) > max_bytes:\n', "    if False:\n", "RC-113",
                                 "a tool result of any size reaches the model"),
    "U10_dicom_identifiers_read": (UNT, 'DICOM_TEXT_TAGS = ("SeriesDescription",', 'DICOM_TEXT_TAGS = ("PatientName", "SeriesDescription",',
                                   "RC-113", "the patient's name is read from the DICOM file for the model"),
    # ---------------------------------------------------------------- tracing
    "T1_unknown_attributes_kept": (TRC, "        if check is None or not check(value):\n",
                                   "        if check is not None and not check(value):\n", "RC-116",
                                   "any attribute, including prompt content, is recorded"),
    "T2_hash_not_validated": (TRC, '    "mstool.content.input_sha256": _is_hash,', '    "mstool.content.input_sha256": lambda v: isinstance(v, str),',
                              "RC-116", "free text is recorded in a hash attribute"),
    "T3_export_on_by_default": (TRC, "    return NoopExporter()\n", "    return InMemoryExporter()\n", "RC-116",
                                "spans are exported without being configured"),
    "T4_exception_text_recorded": (TRC, "            handle.fail(type(exc).__name__)\n", "            handle.fail(str(exc))\n",
                                   "RC-116", "the exception text (may carry identifiers) is recorded"),
    "T5_request_trace_not_adopted": (TRC, "            tid, parent_id = (trace_id if valid_trace_id(trace_id) else _new_trace_id()), None\n",
                                     "            tid, parent_id = _new_trace_id(), None\n", "RC-116",
                                     "the run no longer links to the request's audit record"),
    "T6_reader_not_pseudonymised": (TRC, '"mstool.signoff.reader_key": pseudonymise(reader_id)',
                                    '"mstool.signoff.reader_key": reader_id', "RC-116",
                                    "the reader is named in the sign-off span"),
    "T7_span_name_off_convention": (TRC, '        name = f"invoke_agent {agent_id}" if _is_id(agent_id) else "invoke_agent"\n',
                                    '        name = f"agent {agent_id}"\n', "RC-116",
                                    "the agent span no longer follows the pinned conventions"),
    # ---------------------------------------------------------------- runtime
    "X1_no_switch_before_delivery": (RUN, '        d = reg.check_agent(agent_id, trace_id=tid)               # the switch, once more, before delivery\n'
                                          '        if not d.allowed:\n            return stop("refused", d.code, audit=False)\n',
                                     "", "RC-111", "text is delivered after the agent was switched off"),
    "X2_continue_after_refused_tool": (RUN, '                    if not d.allowed:\n                        ts.set("mstool.refusal.code", str(d.code))\n'
                                            '                        return stop("refused", d.code, audit=False)\n',
                                       "                    if not d.allowed:\n                        continue\n", "RC-110",
                                       "the run continues after a refused (e.g. write) tool call"),
    "X3_no_argument_scope_in_run": (RUN, "                    d = check_tool_arguments(entry, call.arguments, scope)\n",
                                    "                    d = Decision.ok()\n", "RC-114", "the run does not check tool arguments"),
    "X4_identity_not_checked": (RUN, "                if response.model_id != model_id:\n", "                if False:\n", "RC-115",
                                "an answer from another model is delivered"),
    "X5_overrides_honoured": (RUN, "        if overrides or unknown:\n", "        if False:\n", "RC-115",
                              "a caller can change registry parameters"),
    "X6_verifier_optional": (RUN, "        if spec.requires_verifier and self.verifier is None:\n", "        if False:\n", "RC-110",
                             "an agent that requires a verifier runs without one"),
    "X7_withheld_delivered": (RUN, '            if verdict.verdict != "pass" or not (verdict.delivered_text or "").strip():\n',
                              "            if False:\n", "RC-110", "a draft the verifier withheld is delivered"),
    "X8_cost_not_charged": (RUN, "                reg.settle(d.reservation, cost)                 # None: impossible usage, the worst case stays\n",
                            "                reg.settle(d.reservation, 0.0)\n", "RC-112",
                            "calls are not charged against the caps"),
    "X9_no_step_limit": (RUN, "        for step in range(1, spec.max_steps + 1):\n", "        for step in range(1, 1000):\n", "RC-112",
                         "a run is not bounded in steps"),
    "X10_no_tool_call_limit": (RUN, "                if res.tool_calls >= spec.max_tool_calls:\n", "                if False:\n", "RC-112",
                               "a run is not bounded in tool calls"),
    "X11_tool_result_not_checked": (RUN, "                    if not check.ok:\n", "                    if False:\n", "RC-113",
                                    "an invalid or foreign tool result is passed to the model"),
    "X12_untrusted_inputs_unquoted": (RUN, '            first += "\\n" + "\\n".join(q.block for q in quoted)\n',
                                      '            first += "\\n" + "\\n".join(text for _, text in untrusted)\n', "RC-113",
                                      "study-file text reaches the model as plain instructions"),
    "X13_delivered_text_unmarked": (RUN, "        res.provenance = prov.mark_model_text(delivered,",
                                    "        res.provenance = None and prov.mark_model_text(delivered,", "RC-119",
                                    "the delivered text is not marked as the model's"),
    "X14_environment_model_honoured": (RUN, "        res.model_id = model_id if isinstance(model_id, str) else None\n",
                                       '        import os; model_id = os.environ.get("CLAUDE_MODEL", model_id)\n'
                                       "        res.model_id = model_id if isinstance(model_id, str) else None\n", "RC-115",
                                       "the model id is taken from the environment"),
    # ---------------------------------------------------------------- provenance and oversight
    "P1_model_text_not_marked": (PRV, '                kind=kind, text=unit, trailing=trailing, author=author if kind != "blank" else "software",\n',
                                 '                kind=kind, text=unit, trailing=trailing, author="software",\n', "RC-119",
                                 "model text is recorded as the software's"),
    "P2_edits_keep_model_mark": (PRV, '            if tag == "equal":\n', '            if tag in ("equal", "replace"):\n', "RC-119",
                                 "a sentence the clinician changed stays marked as the model's"),
    "P3_html_not_escaped": (PRV, "{html.escape(s.text, quote=True)}</span>", "{s.text}</span>", "RC-119",
                            "model text is rendered as HTML"),
    "P4_hash_binding_ignored": (PRV, "all(s.sha256 == _sha(s.text) for s in doc.segments)", "True", "RC-119",
                                "a record whose units were altered still verifies"),
    "P5_legend_missing": (PRV, '    return body + "\\n\\n" + _legend(doc)\n', "    return body\n", "RC-119",
                          "the signed report does not name the model"),
    "O1_acceptance_always_true": (OVS, "            accepted_unedited=shown_text == final_text,", "            accepted_unedited=True,",
                                  "RC-120", "edited sign-offs are counted as unedited"),
    "O2_shown_text_not_checked": (OVS, '            if pending is None or pending["draft_sha256"] != sha256_text(shown_text):\n',
                                  "            if pending is None:\n", "RC-120",
                                  "a sign-off of a different text than shown is counted"),
    "O3_reader_not_pseudonymised": (OVS, '    return pseudonymise(f"reader:{reader_id}")\n', '    return f"reader:{reader_id}"\n',
                                    "RC-120", "the reader is stored by name"),
    # ---------------------------------------------------------------- cards
    "C1_template_hash_not_compared": (CRD, '        elif recorded[name].get("sha256") != current[name]["sha256"]:\n',
                                      "        elif False:\n", "RC-117", "a changed template goes unnoticed"),
    "C2_new_template_ignored": (CRD, "        if name not in recorded:\n", "        if False:\n", "RC-117",
                                "a new template goes unnoticed"),
    "C3_code_model_not_compared": (CRD, "            if default != mid:\n", "            if False:\n", "RC-117",
                                   "a change of the code's model goes unnoticed"),
    "C4_variants_not_hashed": (CRD, '        out[f"brain_report_service.dis_not_evaluated_template(REPORT_TEMPLATES[{name}])"] = \\\n'
                                    "            b.dis_not_evaluated_template(text)\n", "", "RC-117",
                               "the DIS-not-evaluated variants are not bound"),
    # ---------------------------------------------------------------- evals
    "E1_pass_at_1_instead_of_pass_hat_k": (EVL, "    return len(passes) > 0 and all(p is True for p in passes)\n",
                                           "    return any(p is True for p in passes)\n", "RC-118",
                                           "a case counts as passed when one trial passes"),
    "E2_replay_determinism_off": (EVL, "        same = len({(o.passed, o.detail) for o in outcomes}) == 1\n",
                                  "        same = True\n", "RC-118", "a non-deterministic outcome is accepted"),
    "E3_k_not_enforced": (EVL, '        if c["k"] != len(c["variants"]) or c["k"] < MIN_K:\n', "        if False:\n", "RC-118",
                          "a case with fewer than k recorded variants is accepted"),
    "E4_grader_weakened": (GRADER, "CONSTANTS = (0.0, 1.0,", "CONSTANTS = (0.0, 1.0, 12.4, 31.3,", "RC-118",
                           "the grader accepts invented numbers"),
    # ---------------------------------------------------------------- independent review of PR #79 (findings 1-10)
    "V1_truncated_output_delivered": (RUN, "                if response.stop_reason not in expected_end:\n",
                                      "                if False:\n", "RC-110",
                                      "an answer cut at max_tokens or stopped abnormally is delivered"),
    "V2_truncated_tool_calls_run": (RUN, "                expected_end = TOOL_END if calls else TEXT_END\n",
                                    "                expected_end = (TOOL_END | TRUNCATED) if calls else TEXT_END\n", "RC-110",
                                    "tool calls of a truncated answer run"),
    "V3_output_budget_ignored": (RUN, "        max_tokens = spec.parameter(budget_name) if isinstance(budget_name, str) and \\\n",
                                 "        max_tokens = spec.parameter(BUDGET_PREFIX) if isinstance(budget_name, str) and \\\n",
                                 "RC-115", "the per-template output budget of the registry is ignored"),
    "V4_global_switch_ignored": (REG, "        return self._on(os.environ.get(self.GLOBAL)) and self._on(os.environ.get(self.variable(agent_id)))\n",
                                 "        return self._on(os.environ.get(self.variable(agent_id)))\n", "RC-111",
                                 "the global switch does not stop the agents"),
    "V5_in_flight_calls_not_reserved": (REG, "            self._apply(agent_id, study_key, day, usd)\n            return rid, None\n",
                                        "            return rid, None\n", "RC-112",
                                        "calls in flight do not count against the caps (check-then-record race)"),
    "V6_settle_charges_nothing": (REG, "                self._apply(agent_id, study_key, day, usd - reserved)\n",
                                  "                self._apply(agent_id, study_key, day, -reserved)\n", "RC-112",
                                  "a settled call is charged nothing"),
    "V7_plural_ids_not_checked": (UNT, "        for item in value:\n            if isinstance(item, (Mapping, list)):\n",
                                  "        for item in []:\n            if isinstance(item, (Mapping, list)):\n", "RC-114",
                                  "ids in a list (*_ids, ids) are not scope-checked"),
    "V8_nested_values_not_walked": (UNT, "            bad = _scope_walk(v, depth + 1, scope, **kw)\n"
                                         "            if bad:\n                return bad\n        return None\n    if isinstance(value, list):\n",
                                    "            bad = None\n            if bad:\n                return bad\n        return None\n    if isinstance(value, list):\n",
                                    "RC-114", "ids nested in objects are not scope-checked"),
    "V9_path_uri_not_checked": (UNT, "invalid=RefusalCode.TOOL_ARGUMENTS_INVALID, locations=True)", "invalid=RefusalCode.TOOL_ARGUMENTS_INVALID, locations=False)",
                                "RC-114", "path / uri / url arguments are not scope-checked"),
    "V10_first_version_kept": (OVS, '            if current is None or current["draft_sha256"] != digest:\n', "            if current is None:\n",
                               "RC-120", "a regenerated draft keeps the old version, its sign-off is not counted"),
    "V11_failures_audited_as_denials": (RUN, '    return "failure" if status == "failed" else "denied"\n', '    return "denied"\n', "RC-110",
                                        "model, tool and verifier failures are audited as denials"),
    "V12_alarms_dropped": (RUN, "            res.alarms, res.executed_tools, res.warnings = tuple(alarms), tuple(executed), tuple(warnings)\n"
                                '            if audit and code != "ok":\n',
                           "            res.executed_tools, res.warnings = tuple(executed), tuple(warnings)\n"
                           '            if audit and code != "ok":\n', "RC-113", "early returns drop the injection alarms"),
    # ---------------------------------------------------------------- second independent review of PR #79
    "W1_activity_flags_reach_the_model": (MCPB, "    return drop_unconfirmed_activity_flags(drop_direct_identifiers(value))\n",
                                          "    return drop_direct_identifiers(value)\n", "RC-113",
                                          "activity flags computed from unconfirmed candidates reach a model (CAPA-013)"),
    "W2_list_marker_split_off": (PRV, '        head = content[:marker.end()] if marker else ""\n', '        head = ""\n', "RC-119",
                                 "a list marker is split from its item and tagged on its own"),
    "W3_abbreviations_split": (PRV, "        if _no_split_after(text[start:m.start()], text[m.end():]):\n            continue\n",
                               "        if False:\n            continue\n", "RC-119", "a sentence is split after an abbreviation"),
    "W4_foreign_id_keys_ignored": (UNT, "            if _foreign_key(k, scope, numeric_keys):\n", "            if False:\n",
                                   "RC-114", "another resource used as a dict key passes"),
    "W5_numeric_ids_ignored": (UNT, "                numbers_are_ids = numeric_keys is not None and k not in numeric_keys\n",
                               "                numbers_are_ids = False\n", "RC-114", "a numeric id of another resource passes"),
    "W6_storage_locations_ignored": (UNT, "        if STORAGE_LOCATION.search(value):\n            return RefusalCode.OUT_OF_SCOPE_RESOURCE\n",
                                     "", "RC-114", "a storage location (gs://, s3://) passes"),
    "W7_result_locations_ignored": (UNT, "    bad = _scope_walk(result, 0, scope, invalid=RefusalCode.TOOL_RESULT_INVALID, locations=True,\n",
                                    "    bad = _scope_walk(result, 0, scope, invalid=RefusalCode.TOOL_RESULT_INVALID, locations=False,\n",
                                    "RC-114", "*_path / *_uri / *_url values in a result are not checked"),
    "W8_malformed_response_used": (RUN, "                if response_is_malformed(response):\n", "                if False:\n", "RC-110",
                                   "a malformed provider response is used (and escapes the audit)"),
    "W9_cancel_leaks_reservation": (RUN, "                except asyncio.CancelledError:\n                    reg.settle(d.reservation, None)             # never leaked: the worst case stays charged\n",
                                    "                except asyncio.CancelledError:\n", "RC-112",
                                    "a cancelled call leaves its reservation open"),
    "W10_cancel_not_audited": (RUN, '            reg.audit("cancelled", RefusalCode.RUN_CANCELLED, event="agent.run", agent_id=agent_id,\n'
                                    '                      study_key=scope.study_key, trace_id=trace.get("id"))\n',
                               "", "RC-110", "a cancelled run leaves no audit record"),
    "W11_edited_marker_lost": (PRV, "        elif s.edited_from_model and unit.strip():\n            unit = _marked(unit, TEXT_MARK_EDITED)\n",
                               "", "RC-119", "a model sentence the clinician edited loses its AI marker"),
    "W12_empty_output_delivered": (RUN, '        if not (final_text or "").strip():                      # second review of PR #79, finding 8\n'
                                        '            return stop("failed", RefusalCode.MODEL_OUTPUT_EMPTY)\n',
                                   "", "RC-110", "an empty model output is delivered as a success"),
    "W13_card_hashes_docstrings_only": (CRD, '            out[f"mcp.{server}.tool[{name}].definition"] = tool_definition(name, fn)\n',
                                        '            out[f"mcp.{server}.tool[{name}].definition"] = json.dumps({"name": name, "description": (fn.__doc__ or "").strip()})\n',
                                        "RC-117", "a tool's parameters and signature are not bound by the card"),
    "W14_mutations_written_into_the_checkout": (NCS, '    (work / path).write_text(mutated, encoding="utf-8", newline=eol)\n',
                                                '    (REPO / path).write_text(mutated, encoding="utf-8", newline=eol)\n', "RC-118",
                                                "the negative-control script writes its mutations into the repository"),
}


def _text(path):
    raw = (REPO / path).read_bytes()                                   # the real checkout is only READ
    return raw, raw.decode("utf-8").replace("\r\n", "\n"), ("\r\n" if b"\r\n" in raw else "\n")


@contextlib.contextmanager
def work_copy():
    """A throwaway copy of what the suites need, outside the repository; removed afterwards."""
    work = Path(tempfile.mkdtemp(prefix="mstool-agent-nc-")).resolve()
    if work == REPO or REPO in work.parents:
        raise SystemExit("the throwaway copy must be outside the repository")
    try:
        for rel in COPY:
            src, dst = REPO / rel, work / rel
            if src.is_dir():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        yield work
    finally:
        shutil.rmtree(work, ignore_errors=True)


def apply_mutation(work, name):
    """Write the mutated file into the throwaway copy ``work`` — never into the checkout."""
    path, anchor, repl, _control, _what = M[name]
    work = Path(work).resolve()
    if work == REPO or REPO in work.parents:
        raise SystemExit("refusing to mutate inside the repository")
    _raw, text, eol = _text(path)
    count = text.count(anchor)
    assert count == 1, f"{name}: anchor occurs {count}x in {path}, expected 1"
    mutated = text.replace(anchor, repl, 1)
    assert mutated != text, name
    (work / path).write_text(mutated, encoding="utf-8", newline=eol)


def restore(work, name):
    """Put back EVERY file any mutation targets, not only this mutation's: a mutated test or script may itself
    have changed another file of the copy (found when W14's test left the copy's registry.py mutated)."""
    for path in sorted({m[0] for m in M.values()}):
        (Path(work) / path).write_bytes((REPO / path).read_bytes())


def run(work):
    env = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_MODEL"):
        env.pop(k, None)
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(tempfile.gettempdir(), "mstool-missing-credentials.json"),
                "CLOUDSDK_CONFIG": tempfile.mkdtemp(prefix="mstool-nc-gcloud-"),
                "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests"})
    r = subprocess.run([PY, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false", "-W", "ignore"],
                       cwd=str(Path(work) / "backend"), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    f = re.search(r"(\d+) failed", r.stdout)
    p = re.search(r"(\d+) passed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"failed": int(f.group(1)) if f else 0, "passed": int(p.group(1)) if p else 0,
            "errors": int(e.group(1)) if e else 0,
            "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))[:40]}


def _round(names):
    files = sorted({M[n][0] for n in names})
    out = {"executed": datetime.datetime.now().isoformat(timespec="seconds"), "mutations": {},
           "method": "one mutation at a time in a throwaway copy outside the repository; anchors asserted unique",
           "source_sha256": {p: hashlib.sha256(_text(p)[1].encode("utf-8")).hexdigest() for p in files}}
    with work_copy() as work:
        for name in names:
            apply_mutation(work, name)
            result = run(work)
            path, _a, _r, control, what = M[name]
            result.update({"control": control, "reintroduces": what, "applied": True})
            out["mutations"][name] = result
            restore(work, name)
            print(f"{name:40s} {control}  {result['failed']} failed / {result['errors']} errors / "
                  f"{result['passed']} passed", flush=True)
        out["restored"] = run(work)
    return out


def rerun(names, reason):
    """Run the named mutations and APPEND the round to the record, keeping the earlier rounds as they were."""
    res = json.load(open(OUT, encoding="utf-8"))
    entry = _round(names)
    entry["reason"] = reason
    entry["superseded"] = sorted(n for n in res["mutations"] if n not in M)
    res.setdefault("reruns", []).append(entry)
    latest = {n: v for n, v in res["mutations"].items() if n in M}
    for e in res["reruns"]:
        latest.update({n: v for n, v in e["mutations"].items() if n in M})
    never_run = sorted(set(M) - set(latest))
    if never_run:
        raise SystemExit(f"mutations never run: {never_run}")
    res["undetected"] = sorted(n for n, v in latest.items() if v["failed"] == 0 and v["errors"] == 0)
    res.setdefault("summary", {})["latest_round"] = {
        "executed": entry["executed"], "mutations": len(entry["mutations"]),
        "detected": sum(1 for v in entry["mutations"].values() if v["failed"] or v["errors"]),
        "restored_passed": entry["restored"]["passed"], "restored_failed": entry["restored"]["failed"]}
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("restored", entry["restored"]["passed"], "passed /", entry["restored"]["failed"], "failed | undetected:",
          res["undetected"])
    return 1 if res["undetected"] or entry["restored"]["failed"] else 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--only":
        return rerun(sys.argv[2].split(","), " ".join(sys.argv[3:]) or "re-run")
    res = _round(list(M))
    res.update({"status": "DRAFT, PENDING owner approval", "hash_basis": "sha256 of the UTF-8 text with LF line endings",
                "tests": TESTS})
    res["undetected"] = sorted(n for n, v in res["mutations"].items() if v["failed"] == 0 and v["errors"] == 0)
    res["summary"] = {"mutations": len(M), "detected": len(M) - len(res["undetected"]),
                      "controls": sorted({v[3] for v in M.values()})}
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("restored", res["restored"]["passed"], "passed /", res["restored"]["failed"], "failed | undetected:",
          res["undetected"])
    return 1 if res["undetected"] or res["restored"]["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
