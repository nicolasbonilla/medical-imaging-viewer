"""Negative controls for the agent platform (RC-110 .. RC-120) — reproducible evidence.

DRAFT, PENDING owner approval. Each mutation re-introduces ONE defect a control exists to prevent, in the
real source, one at a time; the script asserts the anchor occurs exactly once (the sabotage really was
applied), runs the agent-platform suites, records the failing test names and restores the originals.
A mutation that no test detects is listed under "undetected" and makes the script exit non-zero.

Light load by design: one pytest process at a time, only tests/agent_platform/, no credentials.
Run from the repository root (offline environment variables are set here):
    backend/venv/Scripts/python scripts/safety/agent_platform_negative_controls.py
Output: docs/iec62304/records/risk_verification/AGENT-PLATFORM_negative_controls_2026-11-10.json
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
    PY = os.environ.get("AGENT_NC_PYTHON", sys.executable)
OUT = "docs/iec62304/records/risk_verification/AGENT-PLATFORM_negative_controls_2026-11-10.json"
TESTS = ["tests/agent_platform/"]

P = "backend/app/agent_platform/"
REG, UNT, TRC, RUN = P + "registry.py", P + "untrusted.py", P + "tracing.py", P + "runtime.py"
PRV, OVS, CRD, EVL = P + "provenance.py", P + "oversight.py", P + "cards.py", P + "evals.py"
GRADER = "backend/tests/agent_platform/graders/report_verifier_v3/verifier.py"

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
    "R8_study_cap_ignored": (REG, "        if study_spent + estimate > spec.cost_cap_per_study_usd + 1e-12:\n",
                             "        if False:\n", "RC-112", "no cost cap per study"),
    "R9_day_cap_ignored": (REG, "        if day_spent + estimate > spec.cost_cap_per_day_usd + 1e-12:\n", "        if False:\n",
                           "RC-112", "no cost cap per day"),
    "R10_fuzzy_model_id": (REG, "        entry = self.model(model_id) if isinstance(model_id, str) and _MODEL_ID.fullmatch(model_id) else None\n",
                           "        entry = self.model(model_id.strip().lower()) if isinstance(model_id, str) else None\n",
                           "RC-115", "a look-alike or padded model id is accepted"),
    "R11_env_switch_lenient": (REG, '        return os.environ.get(self.variable(agent_id), "") == "on"\n',
                               '        return os.environ.get(self.variable(agent_id), "").strip().lower() in ("on", "true", "1")\n',
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
    "U5_argument_scope_off": (UNT, "        if not scope.allows(value):\n            return Decision.refuse(RefusalCode.OUT_OF_SCOPE_RESOURCE)\n",
                              "        pass\n", "RC-114", "a tool call may name another patient's record"),
    "U6_only_declared_ids_scoped": (UNT, "        if not (name in tool.scope_arguments or _is_scoped_name(name)):\n",
                                    "        if name not in tool.scope_arguments:\n", "RC-114",
                                    "an undeclared *_id argument escapes the scope check"),
    "U7_result_scope_off": (UNT, "            if k in SCOPE_KEYS and isinstance(v, str) and v and not scope.allows(v):\n",
                            "            if False:\n", "RC-114", "a tool result carrying another study is passed on"),
    "U8_identifiers_kept": (UNT, "    cleaned = drop_direct_identifiers(result)\n", "    cleaned = result\n", "RC-113",
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
                                            '                        res.alarms = tuple(alarms)\n                        return stop("refused", d.code, audit=False)\n',
                                       "                    if not d.allowed:\n                        continue\n", "RC-110",
                                       "the run continues after a refused (e.g. write) tool call"),
    "X3_no_argument_scope_in_run": (RUN, "                    d = check_tool_arguments(entry, call.arguments, scope)\n",
                                    "                    d = Decision.ok()\n", "RC-114", "the run does not check tool arguments"),
    "X4_identity_not_checked": (RUN, "                if response.model_id != model_id:\n", "                if False:\n", "RC-115",
                                "an answer from another model is delivered"),
    "X5_overrides_honoured": (RUN, "        if overrides:\n", "        if False:\n", "RC-115",
                              "a caller can change registry parameters"),
    "X6_verifier_optional": (RUN, "        if spec.requires_verifier and self.verifier is None:\n", "        if False:\n", "RC-110",
                             "an agent that requires a verifier runs without one"),
    "X7_withheld_delivered": (RUN, '            if not ok or verdict.verdict != "pass" or not (verdict.delivered_text or "").strip():\n',
                              "            if not ok:\n", "RC-110", "a draft the verifier withheld is delivered"),
    "X8_cost_not_charged": (RUN, "                reg.record_cost(agent_id, scope.study_key, cost)\n", "                pass\n", "RC-112",
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
    "O2_shown_text_not_checked": (OVS, '            if pending is None or pending["draft_sha256"] != _sha(shown_text):\n',
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
}


def run():
    env = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_MODEL"):
        env.pop(k, None)
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(tempfile.gettempdir(), "mstool-missing-credentials.json"),
                "CLOUDSDK_CONFIG": tempfile.mkdtemp(prefix="mstool-nc-gcloud-"),
                "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests"})
    r = subprocess.run([PY, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false", "-W", "ignore"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    f = re.search(r"(\d+) failed", r.stdout)
    p = re.search(r"(\d+) passed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"failed": int(f.group(1)) if f else 0, "passed": int(p.group(1)) if p else 0,
            "errors": int(e.group(1)) if e else 0,
            "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))[:40]}


def rerun(names, reason):
    """Re-run only the named mutations (after a test was added for one the full round missed) and append the
    result to the existing record, keeping the first round as it was."""
    res = json.load(open(OUT, encoding="utf-8"))
    sub = {n: M[n] for n in names}
    files = sorted({v[0] for v in sub.values()})
    raw = {p: open(p, "rb").read() for p in files}
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
    entry = {"executed": datetime.datetime.now().isoformat(timespec="seconds"), "reason": reason, "mutations": {}}
    try:
        for name, (path, anchor, repl, control, what) in sub.items():
            assert text[path].count(anchor) == 1, name
            open(path, "w", encoding="utf-8", newline=eol[path]).write(text[path].replace(anchor, repl, 1))
            out = run()
            out.update({"control": control, "reintroduces": what, "applied": True})
            entry["mutations"][name] = out
            open(path, "wb").write(raw[path])
            print(f"{name:40s} {control}  {out['failed']} failed / {out['errors']} errors / {out['passed']} passed", flush=True)
    finally:
        for p, b in raw.items():
            open(p, "wb").write(b)
    entry["restored"] = run()
    res.setdefault("reruns", []).append(entry)
    latest = dict(res["mutations"])
    for e in res["reruns"]:
        latest.update(e["mutations"])
    res["undetected_first_round"] = res.get("undetected_first_round", res["undetected"])
    res["undetected"] = sorted(n for n, v in latest.items() if v["failed"] == 0 and v["errors"] == 0)
    res["summary"] = {"mutations": len(M), "detected": len(M) - len(res["undetected"]),
                      "detected_first_round": len(M) - len(res["undetected_first_round"]),
                      "controls": sorted({v[3] for v in M.values()})}
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("restored", entry["restored"]["passed"], "passed /", entry["restored"]["failed"], "failed | undetected:",
          res["undetected"])
    return 1 if res["undetected"] or entry["restored"]["failed"] else 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--only":
        return rerun(sys.argv[2].split(","), " ".join(sys.argv[3:]) or "re-run")
    files = sorted({v[0] for v in M.values()})
    raw = {p: open(p, "rb").read() for p in files}                       # exact bytes, restored at the end
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}   # keep each file's line endings
    for name, (path, anchor, _r, _c, _w) in M.items():
        c = text[path].count(anchor)
        assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "status": "DRAFT, PENDING owner approval",
           "method": "one mutation at a time; each anchor asserted to occur exactly once; tests/agent_platform/ only",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: hashlib.sha256(text[p].encode("utf-8")).hexdigest() for p in files},
           "tests": TESTS, "mutations": {}}
    try:
        for name, (path, anchor, repl, control, what) in M.items():
            mutated = text[path].replace(anchor, repl, 1)
            assert mutated != text[path], name
            open(path, "w", encoding="utf-8", newline=eol[path]).write(mutated)
            out = run()
            out.update({"control": control, "reintroduces": what, "applied": True})
            res["mutations"][name] = out
            open(path, "wb").write(raw[path])
            print(f"{name:40s} {control}  {out['failed']} failed / {out['errors']} errors / {out['passed']} passed", flush=True)
    finally:
        for p, b in raw.items():
            open(p, "wb").write(b)
    res["restored"] = run()
    res["undetected"] = sorted(n for n, v in res["mutations"].items() if v["failed"] == 0 and v["errors"] == 0)
    res["summary"] = {"mutations": len(M), "detected": len(M) - len(res["undetected"]),
                      "controls": sorted({v[3] for v in M.values()})}
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("restored", res["restored"]["passed"], "passed /", res["restored"]["failed"], "failed | undetected:",
          res["undetected"])
    return 1 if res["undetected"] or res["restored"]["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
