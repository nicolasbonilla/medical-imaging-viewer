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
        "docs/iec62304/agent_platform", "scripts/safety/agent_platform_negative_controls.py", ".github/workflows")

P = "backend/app/agent_platform/"
REG, UNT, TRC, RUN = P + "registry.py", P + "untrusted.py", P + "tracing.py", P + "runtime.py"
PRV, OVS, CRD, EVL = P + "provenance.py", P + "oversight.py", P + "cards.py", P + "evals.py"
GRADER = "backend/tests/agent_platform/graders/report_verifier_v3/verifier.py"
MCPB = "backend/app/mcp/_backend.py"
SEC = "backend/app/security/"
ASC, RAC, PAD = SEC + "agent_scope.py", SEC + "resource_access.py", SEC + "patient_access_dependency.py"
SEG, RTE = "backend/app/api/routes/segmentation.py", "backend/app/api/routes/agent_scope.py"
CAPM, PAC = "backend/app/agent_platform/capability.py", SEC + "patient_access.py"
REQ = "backend/requirements.txt"
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
    "R5_retirement_ignored": (REG, "    if days <= 0:\n", "    if days < -36500:\n", "RC-110",
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
    "U1_markup_not_escaped": (UNT, "    t = unicodedata.normalize(\"NFKC\", text).replace(\"&\", \"&amp;\").replace(\"<\", \"&lt;\").replace(\">\", \"&gt;\")\n    looks = bracket_like()\n    return \"\".join(f\"&#x{ord(c):x};\" if c in looks else c for c in t)\n",
                              "    return text\n", "RC-113", "untrusted text can close its data block"),
    "U2_file_names_quoted": (UNT, '    "file_name": WITHHOLD,', '    "file_name": QUOTE,', "RC-113",
                             "file names (patient names, dates) reach the model"),
    "U3_invisible_chars_kept": (UNT, "    clean = _strip_invisible(raw)\n", "    clean = raw\n", "RC-113",
                                "direction and zero-width characters reach the model"),
    "U4_no_length_cap": (UNT, "    truncated = len(clean) > max_chars\n", "    truncated = False\n", "RC-112",
                         "untrusted text of any length reaches the model"),
    "U5_argument_scope_off": (UNT, "    bad = _scope_walk(arguments, 0, scope, invalid=RefusalCode.TOOL_ARGUMENTS_INVALID,\n"
                                   "                      resource_keys=RESOURCE_KEYS | declared_ids)\n",
                              "    bad = None\n", "RC-114", "a tool call may name another patient's record"),
    "U6_undeclared_arguments_accepted": (UNT, "        if kind is None or not _kind_ok(kind, value):\n",
                                         "        if kind is not None and not _kind_ok(kind, value):\n", "RC-114",
                                         "a tool call may carry arguments its schema does not declare"),
    "U7_ids_not_compared_with_scope": (UNT, "        return None if scope.allows(value) else RefusalCode.OUT_OF_SCOPE_RESOURCE\n",
                                       "        return None\n", "RC-114",
                                       "ids in tool calls and results are not compared with the run's study"),
    "U8_identifiers_kept": (UNT, "            if viewed and (k.replace(\"_\", \"\").lower() in IDENTIFIER_KEYS or k in UNCONFIRMED_ACTIVITY_KEYS):\n                return invalid           # seventh review (R3, R4): the result did not pass the shared rule at the source\n",
        "", "RC-113", "a tool result still carrying direct identifiers or unconfirmed activity flags reaches the model"),
    "U9_result_size_unbounded": (UNT, '    if len(text.encode("utf-8")) > max_bytes:\n', "    if False:\n", "RC-113",
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
    "T6_reader_not_pseudonymised": (TRC, '"mstool.signoff.reader_key": reader_key(reader_id)',
                                    '"mstool.signoff.reader_key": reader_id', "RC-116",
                                    "the reader is named in the sign-off span"),
    "T7_span_name_off_convention": (TRC, '        name = f"invoke_agent {agent_id}" if _is_id(agent_id) else "invoke_agent"\n',
                                    '        name = f"agent {agent_id}"\n', "RC-116",
                                    "the agent span no longer follows the pinned conventions"),
    # ---------------------------------------------------------------- runtime
    "X1_no_switch_before_delivery": (RUN, '        d = reg.check_agent(agent_id, trace_id=tid)               # the switch, once more, before delivery\n'
                                          '        if not d.allowed:\n            return stop("refused", d.code)\n',
                                     "", "RC-111", "text is delivered after the agent was switched off"),
    "X2_continue_after_refused_tool": (RUN, '                    if not d.allowed:\n                        ts.set("mstool.refusal.code", str(d.code))\n'
                                            '                        return stop("refused", d.code)\n'
                                            '                    entry = reg.tool(call.name)\n',
                                       "                    if not d.allowed:\n                        continue\n"
                                       "                    entry = reg.tool(call.name)\n", "RC-110",
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
    "X8_cost_not_charged": (RUN, "                overrun = reg.settle(d.reservation, cost)       # None: impossible usage, the worst case stays\n",
                            "                overrun = reg.settle(d.reservation, 0.0)\n", "RC-112",
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
    "P4_hash_binding_ignored": (PRV, "isinstance(s.sha256, str) and s.sha256 == _sha(s.text)", "isinstance(s.sha256, str)", "RC-119",
                                "a record whose units were altered still verifies"),
    "P5_legend_missing": (PRV, '    return body + "\\n\\n" + _legend(doc)\n', "    return body\n", "RC-119",
                          "the signed report does not name the model"),
    "O1_acceptance_always_true": (OVS, "            accepted_unedited=shown_text == final_text,", "            accepted_unedited=True,",
                                  "RC-120", "edited sign-offs are counted as unedited"),
    "O2_shown_text_not_checked": (OVS, '            if pending is None or pending["draft_sha256"] != sha256_text(shown_text):\n',
                                  "            if pending is None:\n", "RC-120",
                                  "a sign-off of a different text than shown is counted"),
    "O3_reader_not_pseudonymised": (REG, '    return pseudonymise(f"reader:{reader_id}")\n', '    return f"reader:{reader_id}"\n',
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
    "V6_settle_charges_nothing": (REG, "            self._apply(agent_id, study_key, day, usd - reserved)\n",
                                  "            self._apply(agent_id, study_key, day, -reserved)\n", "RC-112",
                                  "a settled call is charged nothing"),
    "V7_plural_ids_not_checked": (UNT, "        for item in value:\n            if isinstance(item, (Mapping, list)):\n",
                                  "        for item in []:\n            if isinstance(item, (Mapping, list)):\n", "RC-114",
                                  "ids in a list (*_ids, ids) are not scope-checked"),
    "V8_nested_values_not_walked": (UNT, "            bad = _scope_walk(v, depth + 1, scope, invalid=invalid, resource_keys=resource_keys, exempt=exempt,\n                              actor_keys=actor_keys, flags=flags, skip_ids=skip_ids or exempt_value, viewed=viewed)\n",
        "            bad = None\n", "RC-114", "ids nested in objects are not scope-checked"),
    "V9_path_uri_not_checked": (UNT, "            if not skip_ids and not exempt_value and (k in resource_keys or _LOCATION_KEY.search(k)):\n",
                                "            if not skip_ids and not exempt_value and k in resource_keys:\n",
                                "RC-114", "path / uri / url values are not scope-checked"),
    "V10_first_version_kept": (OVS, '            if current is None or current["draft_sha256"] != digest:\n', "            if current is None:\n",
                               "RC-120", "a regenerated draft keeps the old version, its sign-off is not counted"),
    "V11_failures_audited_as_denials": (RUN, '    return "failure" if code in FAILURE_CODES else "denied"\n', '    return "denied"\n', "RC-110",
                                        "model, tool and verifier failures are audited as denials"),
    "V12_alarms_dropped": (RUN, "            res.alarms, res.executed_tools, res.warnings = tuple(alarms), tuple(executed), tuple(warnings)\n"
                                "            return res\n",
                           "            res.executed_tools, res.warnings = tuple(executed), tuple(warnings)\n"
                           "            return res\n", "RC-113", "early returns drop the injection alarms"),
    # ---------------------------------------------------------------- second independent review of PR #79
    "W1_activity_flags_reach_the_model": (MCPB, "                if str(k).replace(\"_\", \"\").lower() not in IDENTIFIER_KEYS and k not in UNCONFIRMED_ACTIVITY_KEYS}\n",
                                          "                if str(k).replace(\"_\", \"\").lower() not in IDENTIFIER_KEYS}\n", "RC-113",
                                          "activity flags computed from unconfirmed candidates reach a model (CAPA-013)"),
    "W2_list_marker_split_off": (PRV, '        head = content[:marker.end()] if marker else ""\n', '        head = ""\n', "RC-119",
                                 "a list marker is split from its item and tagged on its own"),
    "W3_abbreviations_split": (PRV, "        if _no_split_after(text[start:m.start()], text[m.end():]):\n            continue\n",
                               "        if False:\n            continue\n", "RC-119", "a sentence is split after an abbreviation"),
    "W4_foreign_id_keys_ignored": (UNT, "            if not skip_ids and not _ids_in_scope(k, scope):\n", "            if False:\n",
                                   "RC-114", "another resource used as a dict key passes"),
    "W5_numeric_ids_ignored": (UNT, "        return None if scope.allows(str(value)) else RefusalCode.OUT_OF_SCOPE_RESOURCE\n",
                               "        return None\n", "RC-114", "a numeric id of another resource passes"),
    "W6_storage_locations_ignored": (UNT, "        if STORAGE_LOCATION.search(value):\n            return RefusalCode.OUT_OF_SCOPE_RESOURCE\n",
                                     "", "RC-114", "a storage location (gs://, s3://) passes"),
    "W7_ids_found_by_value_ignored": (UNT, "        if not skip_ids and not _ids_in_scope(value, scope):\n",
                                      "        if False:\n",
                                      "RC-114", "a foreign resource id under an ordinary key (found by its value) passes"),
    "W8_malformed_response_used": (RUN, "                if response_is_malformed(response):\n", "                if False:\n", "RC-110",
                                   "a malformed provider response is used (and escapes the audit)"),
    "W9_cancel_leaks_reservation": (RUN, "                except asyncio.CancelledError:\n                    reg.settle(d.reservation, None)             # never leaked: the worst case stays charged\n",
                                    "                except asyncio.CancelledError:\n", "RC-112",
                                    "a cancelled call leaves its reservation open"),
    "W10_cancel_not_audited": (RUN, '            audit_run("cancelled", RefusalCode.RUN_CANCELLED)\n',
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
    # ---------------------------------------------------------------- third independent review of PR #79
    "Y1_resource_keys_ignored": (UNT, "            if not skip_ids and not exempt_value and (k in resource_keys or _LOCATION_KEY.search(k)):\n",
                                 "            if not skip_ids and not exempt_value and _LOCATION_KEY.search(k):\n", "RC-114",
                                 "a non-pattern id under a resource key (segmentation_id: 12345) passes"),
    "Y2_actor_keys_scope_checked": (UNT, "            exempt_value = isinstance(v, str) and (k in exempt or (k in actor_keys and bool(ACTOR_ID.fullmatch(v))))\n",
                                    "            exempt_value = isinstance(v, str) and k in exempt\n", "RC-114",
                                    "the clinician's own user id (created_by) refuses a legitimate result"),
    "Y3_model_none_audited_invalid": (REG, "    if value is _UNSET or value is None:\n", "    if value is _UNSET:\n", "RC-110",
                                      "a run that chose no model is audited with model 'invalid'"),
    # fifth review of PR #81 (F4): the sink names the event type it emits (a consultation or an AI run)
    "Y4_agent_audit_anonymous": (REG, "        write = emit_audit(etype, outcome, request=actor.request, user_id=actor.user_id,\n"
                                      "                   username=actor.username, role=actor.role,\n",
                                 "        write = emit_audit(etype, outcome,\n", "RC-110",
                                 "agent audit records are anonymous and dropped under load"),
    "Y5_retirement_check_ignores_the_date": (CRD, '            for agent_id, model, state, _ in _card_retirements(today, agents) if state == "retired"]\n',
                                             '            for agent_id, model, state, _ in _card_retirements(today, agents) if False]\n', "RC-117", "the retirement check never reports a retired model"),
    "Y6_html_author_unchecked": (PRV, '    if not verify_document(doc, doc.text()):\n        raise ValueError("refusing to render a provenance record that does not verify")\n',
                                 "", "RC-119", "an invalid provenance record (e.g. a script as author) is rendered"),
    "Y7_from_dict_unchecked": (PRV, "            if not segment_is_valid(segment):              # third review of PR #79, finding 7\n",
                               "            if False:\n", "RC-119",
                               "a provenance record with an invalid author or hash is loaded"),
    "Y8_malformed_verdict_used": (RUN, "                    ok = verdict_is_valid(verdict)              # third review of PR #79, finding 8\n",
                                  "                    ok = isinstance(verdict, Verdict)\n", "RC-110",
                                  "a Verdict with fields of the wrong type is used and the run raises unaudited"),
    # ---------------------------------------------------------------- fourth independent review of PR #79
    "Z1_uid_tokens_ignored": (UNT, "    found += [m for m in _DOTTED.findall(text) if _uid_in_text(m)]\n", "", "RC-114",
                              "a foreign DICOM UID of another root (Siemens, Philips, GE...) in text or as a key passes"),
    "Z2_actor_exemption_hides_subtree": (UNT, "            exempt_value = isinstance(v, str) and (k in exempt or (k in actor_keys and bool(ACTOR_ID.fullmatch(v))))\n",
                                         "            exempt_value = k in exempt or k in actor_keys\n", "RC-114",
                                         "a dict or list under an actor or exempt key is not walked"),
    "Z3_resource_by_keys_dropped": (UNT, '                           "superseded_by", "replaced_by", "supersedes", "replaces", "derived_from", "copied_from",\n'
                                         '                           "merged_into"})\n',
                                    "                           })\n", "RC-114",
                                    "superseded_by / replaced_by name another resource unchecked"),
    "Z4_boundary_exception_escapes": (RUN, "        except Exception:  # noqa: BLE001 — fourth review, finding 4: a platform fault is an audited failure\n"
                                           "            settle_open_reservation()\n"
                                           '            audit_run("failure", RefusalCode.RUN_INTERNAL_ERROR)\n'
                                           '            return RunResult(status="failed", code=RefusalCode.RUN_INTERNAL_ERROR, trace_id=state.get("trace_id", ""))\n',
                                      "", "RC-110", "an internal error escapes the run as an exception instead of an audited failure"),
    "Z5_run_inputs_not_validated": (RUN, '        if not scope_is_valid(scope) or not untrusted_is_valid(kwargs.get("untrusted", ())):\n',
                                    "        if False:\n", "RC-110", "a malformed scope or untrusted input reaches the run"),
    "Z6_model_part_without_model": (PRV, '        if author == "model" and not (isinstance(model_id, str) and model_id.strip()):\n'
                                         '            raise ValueError("a model part must name its model (model_id)")   # fourth review, finding 5\n',
                                    "", "RC-119", "model text is composed without naming its model"),
    "Z7_model_segment_without_model_loaded": (PRV, "        return isinstance(s.model_id, str) and bool(s.model_id.strip())\n",
                                              "        return True\n", "RC-119",
                                              "a stored model unit without a model id is loaded"),
    "Z8_in_run_decisions_audited_twice": (REG, "        if not _IN_RUN.get():                     # inside a run, the run's single record carries the code\n"
                                               '            self.audit("denied", code, **ctx)\n',
                                          '        self.audit("denied", code, **ctx)\n', "RC-110",
                                          "a run leaves more than one audit record"),
    "Z9_mcp_pin_loosened": (REQ, "mcp==1.30.0\n", "mcp>=1.24.0,<2.0\n", "RC-117",
                            "the MCP SDK (the protocol revision spoken) is whatever pip resolves"),
    "Z10_trace_lines_lost": (TRC, "            self._queue.put_nowait(json.dumps(to_otlp_json([span]), sort_keys=True))\n",
                             "            pass\n", "RC-116", "the file exporter loses the spans it is given"),
    "Z11_edit_size_on_characters": (OVS, "    a = [u[1] + u[2] for u in split_units(shown)]\n    b = [u[1] + u[2] for u in split_units(final)]\n",
                                    "    a, b = list(shown), list(final)\n", "RC-120",
                                    "the edit size is a whole-text character diff (seconds on a long report)"),
    "Z12_uuid_root_uid_ignored": (UNT, '        len(parts) == 3 and parts[:2] == ["2", "25"] and len(parts[2]) >= UID_225_MIN_DIGITS)\n',
                                  "        False)\n", "RC-114", "a foreign UUID-derived UID (2.25.<integer>) passes"),
    # ---------------------------------------------------------------- fifth independent review of PR #79
    "AA1_backend_scope_patient_unchecked": (ASC, "    return (_canon(patient_id) or str(patient_id)) == scope.patient_id and str(getattr(user, \"id\", \"\")) == scope.user_id\n",
        "    return True\n", "RC-121", "the backend serves another patient's object to an agent request"),
    "AA2_backend_scope_not_bound_to_its_user": (ASC, "    return (_canon(patient_id) or str(patient_id)) == scope.patient_id and str(getattr(user, \"id\", \"\")) == scope.user_id\n",
        "    return (_canon(patient_id) or str(patient_id)) == scope.patient_id\n", "RC-121", "a capability issued to one clinician works for another"),
    "AA3_backend_scope_study_unchecked": (ASC, "    return scope is None or _canon(study_id) in scope.study_ids\n",
        "    return True\n", "RC-121", "the backend serves another study of the same patient to an agent request"),
    "AA4_storage_path_study_unchecked": (ASC, "    return study is not None and study in scope.study_ids\n",
        "    return True\n", "RC-121", "a segmentation or file of another study passes the agent scope"),
    "AA5_scope_signature_not_checked": (ASC, "    if not hmac.compare_digest(expected, sig):\n        raise AgentScopeError(\"bad signature\")\n",
        "", "RC-121", "a forged or altered capability is accepted"),
    "AA6_scope_expiry_not_checked": (ASC, "    if not current < exp <= current + MAX_TTL_SECONDS:\n        raise AgentScopeError(\"expired\")\n",
        "", "RC-121", "an expired capability is accepted"),
    "AA7_agent_routes_unrestricted": (ASC, "            if not route_allowed(method, path):\n                raise AgentScopeError(\"not an agent route\")\n",
        "", "RC-121", "an agent request reaches routes outside the assistant's object-authorized read routes"),
    "AA8_admin_bypass_for_agent_listing": (RAC, "    if user.role == UserRole.ADMIN and not _agent_scope.scope_active():   # RC-121: no archive-wide agent listing\n",
        "    if user.role == UserRole.ADMIN:\n", "RC-121", "an administrator's agent request lists across all patients"),
    "AA9_resolver_patient_hook_removed": (RAC, "    if not _agent_scope.allows_patient(patient_id, user):\n        logger.warning(\"Resource access denied: outside the agent scope\",\n                       extra={\"user_id\": str(user.id), \"resource\": resource_label})\n        _agent_scope.audit_denial(user, patient_id)             # F1: the access-audit row, before the 404\n        raise not_found\n",
        "", "RC-121", "the CAPA-009 chokepoint ignores the agent scope"),
    "AA10_study_resolver_hook_removed": (RAC, "    if not _agent_scope.allows_study(study_id):           # RC-121: a study outside the agent scope does not resolve\n        _agent_scope.audit_denial()                          # F1: audited before it resolves to nothing\n        return None\n",
        "", "RC-121", "a study outside the agent scope resolves"),
    "AA11_storage_ref_study_hook_removed": (PAD, "    if not _agent_scope.allows_study(ref.study_id):       # RC-121: an imaging object of another study\n        _agent_scope.audit_denial(user, ref.patient_id)         # F1\n        raise not_found\n",
        "", "RC-121", "an imaging file of another study passes the agent scope"),
    "AA12_patient_dependency_hook_removed": (PAD, "    if not _agent_scope.allows_patient(patient_id, user):\n        logger.warning(\"Patient access denied: outside the agent scope\", extra={\"user_id\": str(user.id)})\n        _agent_scope.audit_denial(user, patient_id)             # F1: the access-audit row, before the 404\n        raise not_found\n",
        "", "RC-121", "the patient dependency ignores the agent scope"),
    "AA13_capability_not_sent": (MCPB, "    if capability:                                         # RC-121: the run's / the session's pass\n        headers[CAPABILITY_HEADER] = capability\n",
        "", "RC-121", "the assistant's backend client does not send the run's capability"),
    "AA14_capability_not_required": (RUN, "        if spec.requires_backend_scope and not scope.capability:\n",
        "        if False:\n", "RC-121", "a scope-bound agent runs without a capability"),
    "AA15_capability_not_current_in_tools": (RUN, "                        with capability_context(scope.capability):       # RC-121: sent with every backend request\n",
        "                        with capability_context(None):\n", "RC-121", "the run's capability is not current while its tools run"),
    "AA16_output_schema_optional": (REG, "            if out is None and t[\"access\"] == \"write\":\n",
        "            if out is None:\n", "RC-121", "a tool without a typed output schema is registered"),
    "AA17_output_type_unchecked": (UNT, "    if tool.output_type == \"array\" and not isinstance(result, list) or \\\n            tool.output_type == \"object\" and not isinstance(result, Mapping):\n        return ToolResultCheck(False, RefusalCode.TOOL_RESULT_INVALID)          # not the declared output type\n",
        "", "RC-114", "a result of another type than the declared output passes"),
    "AA18_stop_reason_defaults_to_end_turn": (RUN, "    stop_reason: Optional[str] = None\n",
        "    stop_reason: Optional[str] = \"end_turn\"\n", "RC-110", "an answer that does not say how it ended is delivered"),
    "AA19_tools_run_on_the_last_step": (RUN, "            if step == spec.max_steps:\n",
        "            if False:\n", "RC-112", "tools run on the last step, their results wasted"),
    "AA20_brackets_look_alike_pass": (UNT, "    return \"\".join(f\"&#x{ord(c):x};\" if c in looks else c for c in t)\n",
        "    return t\n", "RC-113", "a look-alike bracket forges the data block's delimiter"),
    "AA21_tool_definitions_not_reserved": (RUN, "            est_in = estimate_tokens(system, messages, tools=tool_definitions)\n",
        "            est_in = estimate_tokens(system, messages)\n", "RC-112", "the tool definitions are left out of the worst-case reservation"),
    "AA22_overrun_not_flagged": (REG, "            if usd > reserved + 1e-12:\n                self.overruns += 1\n                return True\n",
        "", "RC-112", "a call that cost more than its reservation is not flagged"),
    "AA23_exporter_per_tracer": (TRC, "        self.exporter = exporter if exporter is not None else default_exporter()\n",
        "        self.exporter = exporter if exporter is not None else exporter_from_env()\n", "RC-116", "every tracer opens its own exporter, thread and file handle"),
    "AA24_oversight_unbounded": (OVS, "            while len(self._pending) > self._max:\n",
        "            while False:\n", "RC-120", "the drafts awaiting sign-off grow without bound"),
    "AA25_oversight_never_expires": (OVS, "            if now - v[\"shown_at\"] <= self._ttl:\n                break\n",
        "            if True:\n                break\n", "RC-120", "a draft shown long ago is still counted when signed"),
    "AA26_mismatch_not_evicted": (OVS, "                if pending is not None:                   # finding 6: a mismatch evicts the entry\n",
        "                if False:\n", "RC-120", "a sign-off of another text leaves the entry pending"),
    "AA27_required_arguments_not_checked": (UNT, "        if not kind.startswith(\"optional_\") and name not in arguments:      # every required argument given\n",
        "        if kind == \"resource_id\" and name not in arguments:\n", "RC-114", "a call without a required parameter reaches the tool"),
    "AA28_malformed_call_runs": (RUN, "                    if not _binds(fn, call.arguments):\n",
        "                    if False:\n", "RC-110", "a call that does not bind to the tool is audited as the tool's failure"),
    "AA29_from_dict_fields_unchecked": (PRV, "            if missing or extra:\n",
        "            if False:\n", "RC-119", "a stored record with missing or unknown fields raises TypeError instead of ValueError"),
    "AA30_outcome_from_status": (RUN, "    return \"failure\" if code in FAILURE_CODES else \"denied\"\n",
        "    return \"failure\" if status == \"failed\" else \"denied\"\n", "RC-110", "the audit outcome follows the status, not the failure codes"),
    "AA31_mcp_stack_reverted": (REQ, "fastmcp==3.2.4\n",
        "fastmcp==2.3.0\n", "RC-117", "fastmcp goes back to 2.3.0 and its eight published advisories"),
    "AA32_stub_accepts_what_fastmcp_3_refuses": (CRD, "        if kwargs:\n            raise TypeError(f\"FastMCP() got unexpected keyword argument(s): {', '.join(map(repr, kwargs))}\")\n",
        "", "RC-117", "the card's stub accepts constructor arguments the pinned fastmcp refuses"),
    # ---------------------------------------------------------------- sixth independent review of PR #79
    "BB1_assistant_unscoped_passes_the_backend": (ASC, "        if not values and not assistant:\n",
        "        if not values:\n", "RC-121", "the backend serves an assistant request that carries no study session"),
    "BB2_assistant_marker_not_sent": (MCPB, "    headers[CLIENT_HEADER] = ASSISTANT_CLIENT              # always: the backend refuses an unscoped assistant request\n",
        "", "RC-121", "the assistant's requests are not recognisable by the backend"),
    "BB3_no_local_session_check": (MCPB, "    if capability is None:\n",
        "    if False:\n", "RC-121", "the assistant sends requests without a study session"),
    "BB4_session_never_expires": (MCPB, "    if token and time.monotonic() < _SESSION.get(\"expires_at\", 0):\n",
        "    if token:\n", "RC-121", "an expired study session is still used"),
    "BB7_refusal_audited_as_failure": (RUN, "                    except ScopeRefused as exc:\n",
        "                    except ZeroDivisionError as exc:\n", "RC-110", "a backend scope refusal is audited as the tool's failure"),
    "BB8_refusal_becomes_500": (SEG, "    except HTTPException:\n        raise          # PR #79 sixth review, C1: an authorization refusal (404/400) stays a refusal, never a 500\n",
        "", "RC-121", "the segmentation list turns an authorization refusal into a 500"),
    "BB9_issuance_reimplemented": (RTE, "    token = await issue_for_studies([str(s) for s in body.study_ids], current_user, run_id=body.run_id,\n                                    ttl_seconds=DEFAULT_TTL_SECONDS)\n",
        "    from app.security.agent_scope import sign_for_patient\n    token = sign_for_patient(current_user, {None}, [], run_id=body.run_id)\n", "RC-121", "the issuance route does not use the one tested implementation"),
    "BB10_patient_spellings_differ": (ASC, "    canonical = {_canon(p) for p in patients}\n",
        "    canonical = set(patients)\n", "RC-121", "one patient in two spellings counts as two patients"),
    "BB11_pass_returned_to_the_model": (MCPB, "    return {\"session\": \"open\", \"studies\": len(preview.get(\"studies\", [])), \"expires_in_seconds\": ttl,\n",
        "    return {\"session\": \"open\", \"token\": issued[\"token\"], \"studies\": len(preview.get(\"studies\", [])), \"expires_in_seconds\": ttl,\n", "RC-121", "the study session's pass reaches the model"),
    # ---------------------------------------------------------------- seventh independent review of PR #79
    "CC1_confirmation_not_required": (MCPB, "    if getattr(answer, \"action\", None) != \"accept\":\n",
        "    if False:\n", "RC-121", "a study session opens although the physician did not confirm it"),
    "CC2_no_elicitation_still_opens": (MCPB, "    except Exception:  # noqa: BLE001 — a client that does not implement elicitation\n        raise ScopeRequired(NO_ELICITATION)\n",
        "    except Exception:  # noqa: BLE001 — a client that does not implement elicitation\n        entry = type(\"E\", (), {\"action\": \"accept\", \"data\": \"a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d\"})()\n", "RC-121", "a client without elicitation gets a session anyway"),
    "CC3_old_session_survives_a_new_request": (MCPB, "    _SESSION.clear()\n    elicit = getattr(ctx, \"elicit\", None)\n",
        "    elicit = getattr(ctx, \"elicit\", None)\n", "RC-121", "a declined new session leaves the previous patient's pass active"),
    "CC4_patient_switch_not_audited": (ASC, "    if previous and patient_id and previous != patient_id:\n",
        "    if False:\n", "RC-121", "a switch to another patient is not audited"),
    "CC5_source_view_skipped_in_a_run": (MCPB, "    return assistant_view(data)\n",
        "    return data if current_capability() else assistant_view(data)\n", "RC-113", "inside a platform run, identifiers and activity flags are not removed at the source"),
    "CC6_path_traversal_passes": (MCPB, "            and not any(seg in (\"..\", \".\", \"\") for seg in path[1:].split(\"/\"))      # F10: \"..\" as a SEGMENT only\n",
        "", "RC-121", "a dot segment in a path parameter passes"),
    "CC7_loose_file_parameter": (MCPB, "_FILE_ID = rf\"patients/{_UUID}/studies/{_UUID}/series/{_UUID}/[A-Za-z0-9][A-Za-z0-9._-]{{0,254}}\"   # = RC-027\n",
        "_FILE_ID = r\".+\"\n", "RC-121", "a file path parameter of any shape reaches the backend"),
    "CC8_refused_write_is_a_failure": (CAPM, "    code = \"tool_not_allowed_for_agent\"\n",
        "    code = \"not_a_refusal_code\"\n", "RC-110", "a refused write or non-assistant route is audited with no denial code"),
    "CC9_scope_optional_for_the_assistant": (REG, "            if on_mcp and a.get(\"requires_backend_scope\") is not True:\n",
        "            if False:\n", "RC-121", "the registry accepts the assistant without a backend scope"),
    "CC10_issuance_continues_after_a_refusal": (ASC, "    for sid in ids:\n        patients.append(await resource_access.authorize_study_id(sid, user, services=services))\n",
        "    for sid in ids:\n        try:\n            patients.append(await resource_access.authorize_study_id(sid, user, services=services))\n        except HTTPException:\n            patients.append(None)\n    if None in patients:\n        raise HTTPException(status_code=404, detail=\"Study not found\")\n", "RC-121", "issuance keeps authorizing studies after the first refusal"),
    # ---------------------------------------------------------------- eighth (final) review of PR #79: F1
    "DD1_chokepoint_denial_not_audited": (RAC, "        _agent_scope.audit_denial(user, patient_id)             # F1: the access-audit row, before the 404\n        raise not_found\n",
        "        raise not_found\n", "RC-121", "a scope refusal at the patient chokepoint leaves no access-audit row"),
    "DD2_study_resolver_denial_not_audited": (RAC, "        _agent_scope.audit_denial()                          # F1: audited before it resolves to nothing\n",
        "", "RC-121", "a study refused by the scope leaves no access-audit row"),
    "DD3_segmentation_denial_not_audited": (RAC, "        _agent_scope.audit_denial(None, extract_patient_id_from_path(str(file_id)))      # F1\n",
        "", "RC-121", "a segmentation refused by the scope leaves no access-audit row"),
    "DD4_storage_ref_denial_not_audited": (PAD, "        _agent_scope.audit_denial(user, ref.patient_id)         # F1\n",
        "", "RC-121", "an imaging file refused by the scope leaves no access-audit row"),
    "DD5_patient_dependency_denial_not_audited": (PAD, "        logger.warning(\"Patient access denied: outside the agent scope\", extra={\"user_id\": str(user.id)})\n        _agent_scope.audit_denial(user, patient_id)             # F1: the access-audit row, before the 404\n",
        "        logger.warning(\"Patient access denied: outside the agent scope\", extra={\"user_id\": str(user.id)})\n", "RC-121", "a scope refusal at the patient dependency leaves no access-audit row"),
    "DD6_denial_audited_with_another_reason": (PAC, "    DENIED_AGENT_SCOPE = \"denied:agent_scope_denied\"\n",
        "    DENIED_AGENT_SCOPE = \"denied:no_care_team_assignment_\"\n", "RC-121", "a scope refusal is audited under another reason than agent_scope_denied"),
    # ---------------------------------------------------------------- round 9 of PR #79: T1
    "EE1_ticket_redeemed_twice": (ASC, "        fresh = ticket_store().consume(pending.jti, pending.expires_at)       # round 9 (T1): single-use, atomic\n",
        "        fresh = True\n", "RC-121", "one physician confirmation is redeemed for several passes"),
    "EE2_replay_not_audited": (ASC, "        _audit_replay(user, pending.jti)\n",
        "", "RC-121", "a replayed confirmation leaves no audit row"),
    "EE3_shared_store_not_atomic": (ASC, "            client.collection(self.COLLECTION).document(jti).create(\n",
        "            client.collection(self.COLLECTION).document(jti).set(\n", "RC-121", "the shared store overwrites instead of create-if-absent"),
    "EE4_memory_store_forgets": (ASC, "            self._used[jti] = int(expires_at)\n",
        "", "RC-121", "the in-process store does not record a consumed ticket"),
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
        # A mutation counts as detected only against a CLEAN baseline: the unmutated copy must pass first (found
        # when a test reading .github/ failed in a copy that lacked it, adding one failure to every mutation).
        out["baseline"] = run(work)
        if out["baseline"]["failed"] or out["baseline"]["errors"]:
            raise SystemExit(f"the unmutated copy is not clean: {out['baseline']['failing_tests']}")
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
