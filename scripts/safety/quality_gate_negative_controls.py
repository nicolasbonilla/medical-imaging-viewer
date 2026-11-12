"""Negative controls for the single quality gate (RC-122..RC-127; HAZ-025) — reproducible evidence.
DRAFT, PENDING owner approval.

Each mutation re-introduces ONE defect the gate exists to prevent. It is applied to a THROWAWAY copy of the
files the tests need (made under the system temporary folder, deleted at the end), NEVER to the worktree:

- every anchor must occur EXACTLY ONCE in its file (the sabotage really was applied where intended);
- the mutant must COMPILE AND IMPORT before its kill counts (Python: the gate, both routes and the platform
  modules import; JSON: it parses; TypeScript: Node loads the module) — a mutant that does not load is
  recorded as 'invalid', never as detected (no NameError kills);
- the bound tests run in the copy (backend pytest with a JUnit report; frontend: the G4 parity harness under
  Node's type stripping — the shared fixture, the matrix digest and the browser invariants G1, G6, G11 and
  RC-125); a mutant is detected when at least one bound test fails;
- the exact original bytes are restored in the copy and hash-checked after every mutation; the unmutated copy
  must pass before (baseline) and after (restored).

Frontend mutations that only vitest can observe (React components) are listed with runner 'vitest' and run
only when frontend/node_modules exists; otherwise they are recorded as 'not run (no node_modules)', never as
detected or survived (GitHub Actions runs vitest).

First review of PR #81, S4 (lesson I15 of PR #78): EVERY test command runs with its working directory inside the
throwaway copy (pytest and Node from the copy's root, vitest from the copy's frontend with node_modules linked),
and before a kill counts the script asserts that every mutated file lies under that working directory — a mutant
can never be checked against unmutated code.

Backend tests run OFFLINE: GOOGLE_APPLICATION_CREDENTIALS points to a missing file, CLOUDSDK_CONFIG to an
empty folder, GOOGLE_CLOUD_PROJECT=mstool-offline-tests, ANTHROPIC_API_KEY removed (PRB-002).

Run from the repository root with the backend virtual environment's Python:
    <backend venv python> scripts/safety/quality_gate_negative_controls.py
Output: docs/iec62304/records/risk_verification/QUALITY-GATE_negative_controls_2026-11-12.json
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "docs/iec62304/records/risk_verification/QUALITY-GATE_negative_controls_2026-11-12.json")
PY = sys.executable

BACKEND_TESTS = ["tests/unit/test_quality_gate_matrix.py", "tests/unit/test_rc122_quality_gate_wiring.py"]
VITEST_TESTS = ["src/components/BrowserFlamesCard.qualityGate.test.tsx", "src/components/QualityGatePanel.test.tsx",
                "src/services/qualityGate/gate.test.ts"]
COPY_TREES = ["backend/app", "backend/data"]
COPY_FILES = ["backend/pytest.ini", "backend/tests/__init__.py", "backend/tests/conftest.py",
              "backend/tests/unit/__init__.py", *("backend/" + t for t in BACKEND_TESTS),
              "frontend/src/config/qualityGatePolicy.v1.json", "frontend/src/config/qualityGate.cases.v1.json",
              "frontend/src/config/qualityGate.sequences.v1.json",
              "frontend/src/i18n/locales/en.json", "frontend/src/i18n/locales/es.json",
              "frontend/src/i18n/locales/de.json", "frontend/src/services/qualityGate/gate.ts"]
IMPORT_PROBE = ("import sys; sys.path.insert(0, 'backend'); import app.services.quality_gate, app.agent_platform.registry, "
                "app.agent_platform.tracing, app.api.routes.clinical_tools, app.api.routes.segmentation_analysis")

QG = "backend/app/services/quality_gate.py"
POL = "backend/app/services/quality_gate_policy.json"
SA = "backend/app/api/routes/segmentation_analysis.py"
TR = "backend/app/agent_platform/tracing.py"
AG = "backend/app/agent_platform/agents.json"
ES = "frontend/src/i18n/locales/es.json"
TS = "frontend/src/services/qualityGate/gate.ts"
FPOL = "frontend/src/config/qualityGatePolicy.v1.json"
CARD = "frontend/src/components/BrowserFlamesCard.tsx"
PANEL = "frontend/src/components/QualityGatePanel.tsx"
CT = "backend/app/api/routes/clinical_tools.py"
EN = "frontend/src/i18n/locales/en.json"
CMP_ACTION = ("In a comparison the sequence cannot be confirmed by hand. Compare the images visually with the overlay, "
              "or compare visits whose FLAIR header names the sequence.")

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces, runner, controls)
    # ── RC-122: FLAIR only, unknown never passes ──
    "Q1_confirmation_overrides_another_sequence": ([(QG, '    return _check("sequence", label, "abstain", "sequence_not_flair", sequence=seq)\n',
        '    if visit.get("physician_confirmed_flair") is True:\n'
        '        return _check("sequence", label, "warn", "sequence_confirmed_by_physician", sequence=seq)\n'
        '    return _check("sequence", label, "abstain", "sequence_not_flair", sequence=seq)\n')],
        "a physician confirmation lets the AI run on a T1/T2 image", "backend", "RC-122"),
    "Q2_unknown_sequence_passes": ([(QG, '    if seq in rules["accepted"]:\n', '    if seq in rules["accepted"] or seq == "unknown":\n')],
        "an image whose header names no sequence is taken as a FLAIR", "backend", "RC-122"),
    "Q3_confirmation_leaves_no_warning": ([(QG, '            return _check("sequence", label, "warn", "sequence_confirmed_by_physician", sequence=seq)\n',
        '            return _check("sequence", label, "pass")\n')],
        "a physician-confirmed unknown sequence passes silently", "backend", "RC-122"),
    "Q4_unknown_thickness_passes": ([(QG, '        return _check("thickness", label, "warn", "thickness_unknown")\n',
        '        return _check("thickness", label, "pass")\n')],
        "an unreadable slice thickness passes without a word", "backend", "RC-122, RC-124"),
    "Q5_lower_bound_taken_as_thin": ([(QG, '    if state == "native" and known and mm <= rules["thin_limit_mm"]:\n',
        '    if state in ("native", "at_least") and known and mm <= rules["thin_limit_mm"]:\n')],
        "a lower bound (NIfTI grid, derived image) taken as a thin acquisition", "backend", "RC-122"),
    "Q6_gate_fault_passes": ([(QG, '    except Exception:  # noqa: BLE001 — a fault in the gate is an abstention, never a pass\n'
        '        return _result([_check("input", None, "abstain", "gate_input_invalid")], policy)\n',
        '    except Exception:  # noqa: BLE001\n        return _result([_check("input", None, "pass")], policy)\n'),
        (QG, '    if not isinstance(inputs, dict):\n        return _result([_check("input", None, "abstain", "gate_input_invalid")], policy)\n',
         '    if not isinstance(inputs, dict):\n        return _result([_check("input", None, "pass")], policy)\n')],
        "a malformed input or a fault inside the gate yields a pass", "backend", "RC-122"),
    # ── RC-123: scanner change between visits ──
    "Q7_scanner_change_ignored": ([(QG, '    if differing:\n        return _check("scanner", None, "abstain", "scanner_changed"',
        '    if False:\n        return _check("scanner", None, "abstain", "scanner_changed"')],
        "a change of manufacturer or field strength between visits is ignored", "backend", "RC-123"),
    "Q8_unknown_scanner_passes": ([(QG, '    if missing:\n        return _check("scanner", None, "abstain", "scanner_unknown", fields=[f for f in fields if f in missing])\n',
        '    if missing:\n        return _check("scanner", None, "pass")\n')],
        "an unrecorded scanner is taken as the same scanner", "backend", "RC-123"),
    "Q9_abstention_does_not_withhold": ([(QG, '        out.update({k: None for k in lcs.ABSTAINED_NULL_FIELDS})\n        out["reader_confirmed_activity"] = None\n',
        '        pass\n')],
        "a comparison the gate stops still carries lesion counts and loads", "backend", "RC-123"),
    "Q10_route_ignores_the_gate": ([(SA, '        if gate is not None and gate.get("ai_output_allowed") is not True:\n            from app.services import quality_gate as qg\n            return qg.abstained_comparison(gate)\n', '        pass\n'),
        (SA, '            result = qg.apply_to_comparison(result, gate)\n', '            pass\n')],
        "the longitudinal route consults the gate but shows the candidates anyway", "backend", "RC-123"),
    # ── RC-124: data rule ──
    "Q11_hook_ignores_the_licence": ([(QG, '    if not isinstance(asset, dict) or asset.get("licence") not in rules["commercial_licence_allowlist"]:\n',
        '    if not isinstance(asset, dict):\n')],
        "an evidence asset with a non-commercial licence makes the thickness abstain", "backend", "RC-124"),
    "Q12_thickness_abstains_on_bands": ([(QG, '    return _check("thickness", label, "warn", code, band=band, mm=mm)\n',
        '    return _check("thickness", label, "abstain" if band in ("B3", "B4") else "warn", code, band=band, mm=mm)\n')],
        "thick bands abstain on figures from non-commercial cohorts (before the v3 evidence)", "backend", "RC-124"),
    # ── RC-125: skull ──
    "Q13_unknown_skull_passes": ([(QG, '    return _check("skull", label, "abstain", "skull_unknown")\n', '    return _check("skull", label, "pass")\n')],
        "an unknown skull state lets the output through", "backend", "RC-125"),
    "Q14_pending_allows_output": ([(QG, '        "ai_output_allowed": decision in ("proceed", "proceed_with_warnings"),\n',
        '        "ai_output_allowed": decision != "abstain",\n')],
        "the AI output is shown while the skull has not been checked", "backend", "RC-125"),
    "Q15_skull_not_checked": ([(QG, '        if "skull" in spec["checks"] and mode in policy["skull"]["required_in_modes"]:\n',
        '        if False:\n')],
        "the single-study gate never checks the skull", "backend", "RC-125"),
    "Q16_server_says_skull_stripped": ([(QG, '        "skull": "pending",\n    }]}\n', '        "skull": "stripped",\n    }]}\n')],
        "the server claims a skull-free image before it was read", "backend", "RC-125"),
    # ── RC-126: platform, trace, audit ──
    "Q17_platform_off_continues": ([(QG, '    if platform["status"] != "pass":                                   # G6: nothing else runs\n',
        '    if False:\n')],
        "with the kill switch off the other checks still run and can let the AI through", "backend", "RC-126"),
    "Q18_malformed_switch_accepted": ([(QG, '    if isinstance(platform, dict) and platform.get("allowed") is True:\n',
        '    if isinstance(platform, dict) and platform.get("allowed"):\n')],
        "a malformed platform answer ('true' as text) counts as switched on", "backend", "RC-126"),
    "Q19_registry_not_consulted": ([(QG, '                decision = reg.check_agent(AGENT_ID, trace_id=span.trace_id)\n',
        '                decision = R.Decision.ok()\n')],
        "the approval and the kill switches are not read", "backend", "RC-126"),
    "Q20_trace_omits_checks": ([(QG, '                for c in result["checks"]:\n', '                for c in result["checks"][:1]:\n')],
        "the trace records only the first check", "backend", "RC-126"),
    "Q21_success_not_audited": ([(QG, '            reg.audit("success", f"quality_gate.{result[\'decision\']}"',
        '            (lambda *a, **k: None)("success", f"quality_gate.{result[\'decision\']}"')],
        "a consultation that lets the AI run leaves no audit record", "backend", "RC-126"),
    "Q22_trace_attribute_dropped": ([(TR, '    "mstool.gate.status": lambda v: v in ("pass", "warn", "pending", "abstain"),\n', '')],
        "the trace allow-list loses the check status", "backend", "RC-126"),
    "Q23_registry_entry_approved": ([(AG, '        "status": "pending",\n        "ref": "feat/quality-gate (stacked on PR #79): entry to be approved by the owner (D-QG-1)"',
        '        "status": "approved",\n        "ref": "feat/quality-gate (stacked on PR #79): entry to be approved by the owner (D-QG-1)"')],
        "the repository records the owner's approval", "backend", "RC-126"),
    "Q24_policy_changed_silently": ([(POL, '    "thin_limit_mm": 1.5,\n', '    "thin_limit_mm": 2.0,\n')],
        "the backend policy changes without the registry, the fixture or the browser copy", "backend", "RC-126, RC-127"),
    # ── input derivation (RC-122) ──
    "Q25_file_name_as_evidence": ([(QG, '    description = fields["series_description"] or stored\n',
        '    description = fields["series_description"] or stored or file_path\n')],
        "the file name is read as the sequence (RC-049 forbids it)", "backend", "RC-122"),
    "Q26_t1_flair_accepted": ([(QG, '    if is_other or (flair and t1):          # a non-FLAIR name, or a T1-weighted FLAIR: ALWAYS abstains\n',
        '    if is_other:\n')],
        "a T1-weighted FLAIR is taken as a T2 FLAIR", "backend", "RC-122"),
    "Q27_short_inversion_time_ignored": ([(QG, '    if ti is not None and ti < rules["min_flair_inversion_time_ms"]:\n', '    if False:\n')],
        "an inversion time too short for a FLAIR is ignored", "backend", "RC-122"),
    "Q28_record_called_native": ([(QG, '        return {"state": "at_least", "effective_mm": mm}\n', '        return {"state": "native", "effective_mm": mm}\n')],
        "a stored acquisition record (not provably original) reported as native thickness", "backend", "RC-122, RC-124"),
    # ── RC-127: texts ──
    "Q29_spanish_message_missing": ([(ES, '        "message": "La cabecera de la imagen indica que es una imagen {{sequence}}, no una FLAIR. La IA solo funciona con imágenes FLAIR.",\n',
        '        "message": "",\n')],
        "a reason shown to a Spanish-speaking physician is empty", "backend", "RC-127"),
    # ── first review of PR #81 ──
    "R1_underscore_kept_in_tokens": ([(QG, '_NON_ALNUM = re.compile(r"[^a-z0-9]+")\n', '_NON_ALNUM = re.compile(r"[^a-z0-9_]+")\n')],
        "'_' kept inside tokens (as a regex word boundary does): AX_DWI_B1000 names no sequence", "backend", "RC-122"),
    "R2_camel_case_not_split": ([(QG, '    s = _PLUS_C.sub(" postcontrast ", _CAMEL.sub(r"\\1 \\2", text).replace("*", " star "))\n',
        '    s = _PLUS_C.sub(" postcontrast ", text.replace("*", " star "))\n')],
        "camelCase names (TraceW) are not split", "backend", "RC-122"),
    "R3_star_not_read": ([(QG, '    s = _PLUS_C.sub(" postcontrast ", _CAMEL.sub(r"\\1 \\2", text).replace("*", " star "))\n',
        '    s = _PLUS_C.sub(" postcontrast ", _CAMEL.sub(r"\\1 \\2", text))\n')],
        "'T2*' read as a T2", "backend", "RC-122"),
    "R4_confirmation_in_a_comparison": ([(QG, '        if visit.get("physician_confirmed_flair") is True and mode in rules["confirmation_modes"]:\n',
        '        if visit.get("physician_confirmed_flair") is True:\n')],
        "a confirmation lifts an unknown sequence in a comparison, where none is offered", "backend", "RC-122"),
    "R5_lax_attestation_boolean": ([(CT, '    physician_confirmed_flair: StrictBool = False   # S3: a deliberate attestation, never coerced from "true"/1\n',
        '    physician_confirmed_flair: bool = False\n')],
        "'true' or 1 accepted as the physician's attestation", "backend", "RC-122, RC-126"),
    "R6_attestation_not_audited": ([(QG, '+ (".physician_attested" if attested else "")', '+ ""')],
        "the physician's attestation leaves no audit trace", "backend", "RC-126"),
    "R7_comparison_asks_for_a_confirmation": ([(EN, '        "action_comparison": "' + CMP_ACTION + '"\n      },\n      "sequence_confirmed_by_physician"',
        '        "action_comparison": "If you are sure it is a T2-FLAIR, tick the confirmation box."\n      },\n      "sequence_confirmed_by_physician"')],
        "a comparison asks for an attestation it cannot take", "backend", "RC-127"),
    "R8_gate_after_loading": ([(SA, '        if gate is not None and gate.get("ai_output_allowed") is not True:\n            from app.services import quality_gate as qg\n            return qg.abstained_comparison(gate)\n', '        pass\n')],
        "the comparison loads masks, images, registration and atlas before the gate stops it", "backend", "RC-123"),
    "R9_caveat_overwritten": ([(QG, '        out["caveat"] = (previous.rstrip() + " " if isinstance(previous, str) and previous.strip() else "") + gate_caveat(gate)\n',
        '        out["caveat"] = gate_caveat(gate)\n')],
        "RC-062's reasons are lost from the caveat", "backend", "RC-123"),
    "R10_raw_codes_in_caveat": ([(QG, '    reasons = [CAVEAT_REASONS.get(c, "a quality check did not pass") for c in (gate.get("codes") or ["gate_unavailable"])]\n',
        '    reasons = list(gate.get("codes") or ["gate_unavailable"])\n')],
        "the caveat shows raw codes instead of plain reasons", "backend", "RC-123, RC-127"),
    "R11_pixels_decoded": ([(QG, '        ds = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)\n',
        '        imaging_service.load_dicom(data)\n        ds = pydicom.dcmread(io.BytesIO(data))\n')],
        "the gate decodes the whole image instead of the header", "backend", "RC-122"),
    "R12_header_cache_off": ([(QG, '            if key:\n                _HEADER_CACHE[key] = fields\n',
        '            if False:\n                _HEADER_CACHE[key] = fields\n')],
        "every consultation downloads and parses the file again", "backend", "RC-122"),
    "R13_parsed_on_the_event_loop": ([(QG, '            fields = await asyncio.to_thread(read_header_fields, data, file_path.rsplit("/", 1)[-1], imaging_service)\n',
        '            fields = read_header_fields(data, file_path.rsplit("/", 1)[-1], imaging_service)\n')],
        "the header is parsed on the event loop", "backend", "RC-122"),
    "R14_acquisition_read_twice": ([(SA, '    if file_id not in memo:\n        memo[file_id] = _source_acquisition(file_id)\n    return memo[file_id]\n',
        '    return _source_acquisition(file_id)\n')],
        "the acquisition records are read again for RC-062", "backend", "RC-123"),
    "R15_thin_limit_not_the_evaluated_policy": ([(QG, '    limit = thin_limit_mm if thin_limit_mm is not None else _policy()["thickness"]["thin_limit_mm"]\n',
        '    limit = _policy()["thickness"]["thin_limit_mm"]\n')],
        "the thin limit of another policy than the one evaluated", "backend", "RC-124"),
    "F10_ts_underscore_kept_in_tokens": ([(TS, "  return s.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);\n",
        "  return s.toLowerCase().split(/[^a-z0-9_]+/).filter(Boolean);\n")],
        "the browser keeps '_' inside tokens", "node", "RC-122, RC-127"),
    "F11_ts_t1_flair_accepted": ([(TS, "  if (isOther || (flair && t1)) return 'other';", "  if (isOther) return 'other';")],
        "the browser takes a T1-weighted FLAIR as a FLAIR", "node", "RC-122, RC-127"),
    "F12_ts_confirmation_in_a_comparison": ([(TS, "    if (visit.physician_confirmed_flair === true && policy.sequence.confirmation_modes.includes(mode)) {\n",
        "    if (visit.physician_confirmed_flair === true) {\n")],
        "the browser lets a confirmation lift an unknown sequence in a comparison", "node", "RC-122"),
    # ── browser rule (G4 parity harness under Node) ──
    "F1_ts_confirmation_overrides_another_sequence": ([(TS, "  return mk('sequence', label, 'abstain', 'sequence_not_flair', { sequence: seq });\n",
        "  return visit.physician_confirmed_flair === true ? mk('sequence', label, 'warn', 'sequence_confirmed_by_physician', { sequence: seq })\n"
        "    : mk('sequence', label, 'abstain', 'sequence_not_flair', { sequence: seq });\n")],
        "the browser lets a confirmed T1/T2 run", "node", "RC-122, RC-127"),
    "F2_ts_unknown_thickness_passes": ([(TS, "  else return mk('thickness', label, 'warn', 'thickness_unknown');\n", "  else return mk('thickness', label, 'pass');\n")],
        "the browser passes an unreadable thickness", "node", "RC-122, RC-127"),
    "F3_ts_field_tolerance_ignored": ([(TS, "      ? Math.abs(a - b) > policy.scanner.field_strength_tolerance_t : a !== b) differing.push(field);\n",
        "      ? a !== b : a !== b) differing.push(field);\n")],
        "the browser compares field strength without RC-062's tolerance", "node", "RC-123, RC-127"),
    "F4_ts_scanner_text_not_normalised": ([(TS, "  return text ? text.toUpperCase() : null;\n", "  return text ? v : null;\n")],
        "the browser compares manufacturer names case- and space-sensitively", "node", "RC-123, RC-127"),
    "F5_ts_pending_allows_output": ([(TS, "    ai_output_allowed: decision === 'proceed' || decision === 'proceed_with_warnings',\n",
        "    ai_output_allowed: decision !== 'abstain',\n")],
        "the browser shows the output while a check is pending", "node", "RC-125"),
    "F6_ts_malformed_switch_accepted": ([(TS, "  if (isObj(platform) && platform.allowed === true) return mk('platform', null, 'pass');\n",
        "  if (isObj(platform) && Boolean(platform.allowed)) return mk('platform', null, 'pass');\n")],
        "the browser counts a malformed platform answer as switched on", "node", "RC-126"),
    "F7_ts_final_check_ignores_skull": ([(TS, "  const visits = (server.inputs.visits as unknown[]).map((v) => (isObj(v) ? { ...v, skull } : v));\n",
        "  const visits = (server.inputs.visits as unknown[]).map((v) => (isObj(v) ? { ...v, skull: 'stripped' } : v));\n")],
        "the final browser check ignores the worker's skull outcome", "node", "RC-125"),
    "F8_ts_unreachable_backend_allows": ([(TS, "  return evaluateGate({ platform: null });\n",
        "  return evaluateGate({ platform: { allowed: true, code: null }, mode: 'single', visits: [{ sequence: 'FLAIR', thickness: { state: 'native', effective_mm: 1 }, skull: 'stripped' }] });\n")],
        "an unreachable backend lets the browser AI through", "node", "RC-126"),
    "F9_ts_policy_copy_drifts": ([(FPOL, '    "thin_limit_mm": 1.5,\n', '    "thin_limit_mm": 2.0,\n')],
        "the browser's copy of the policy drifts from the backend's", "node", "RC-127"),
    # ── React components (vitest only) ──
    "V1_card_shows_output_without_the_final_check": ([(CARD, "      {flames.status === 'done' && flames.result && gateAllowsOutput && (\n",
        "      {flames.status === 'done' && flames.result && (\n")],
        "the card shows the AI result whatever the final gate says", "vitest", "RC-127"),
    "V2_card_runs_despite_an_abstention": ([(CARD, "    if (!sequenceConfirmed || !gateAllowsRun) return;\n", "    if (!sequenceConfirmed) return;\n"),
        (CARD, "            disabled={!flairFileId || !sequenceConfirmed || !gateAllowsRun}\n", "            disabled={!flairFileId || !sequenceConfirmed}\n")],
        "the run button ignores the gate's abstention", "vitest", "RC-122"),
    "V3_panel_hides_the_reasons": ([(PANEL, "  const notOk = (result.checks ?? []).filter((c) => c.status !== 'pass' && c.code);\n",
        "  const notOk: GateCheck[] = [];\n")],
        "the panel shows the decision but not why", "vitest", "RC-127"),
    "V4_run_checkbox_implies_the_attestation": ([(CARD, "  const gateBefore = useMemo(() => withAttestation(preflight, canAttest && attested), [preflight, canAttest, attested]);\n",
        "  const gateBefore = useMemo(() => withAttestation(preflight, sequenceConfirmed), [preflight, sequenceConfirmed]);\n")],
        "the run checkbox counts as the FLAIR attestation", "vitest", "RC-122"),
    "V5_backend_called_on_every_toggle": ([(CARD, "  }, [gateOn, flairFileId]);\n", "  }, [gateOn, flairFileId, attested]);\n")],
        "the backend is called on every toggle", "vitest", "RC-122"),
    "V6_panel_ignores_the_mode": ([(PANEL, "${actionKey(result.mode, c.code as string)}", "action")],
        "the panel asks a comparison for an attestation", "vitest", "RC-127"),
}

HARNESS = r"""
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { canonicalGate, evaluateGate, finalBrowserGate, gateUnavailable, QUALITY_GATE_POLICY, sequenceFromHeader } from './gate.ts';
const F = JSON.parse(readFileSync(process.env.QG_FIXTURE, 'utf-8'));
const BACKEND_POLICY = JSON.parse(readFileSync(process.env.QG_BACKEND_POLICY, 'utf-8'));
const failures = [];
const fail = (name, ok) => { if (!ok) failures.push(name); };
fail('policy_equals_backend', JSON.stringify(QUALITY_GATE_POLICY) === JSON.stringify(BACKEND_POLICY));
const names = F.matrix.dimensions.map((d) => d[0]);
const tables = F.matrix.dimensions.map((d) => Object.entries(d[1]));
const lines = []; let g1 = true, g11 = true;
const walk = (i, combo) => {
  if (i === tables.length) {
    const p = {}; names.forEach((n, j) => { p[n] = combo[j][1]; });
    const patch = { ...p.sequence, ...p.confirmed, ...p.thickness, ...p.skull };
    const base = JSON.parse(JSON.stringify(F.matrix.base_visit));
    const visits = p.variant.mode === 'single' ? [{ ...base, ...patch, ...p.scanner }]
      : [{ ...base, ...(p.variant.affected.includes('tp1') ? patch : {}) }, { ...base, ...(p.variant.affected.includes('tp2') ? patch : {}), ...p.scanner }];
    const out = evaluateGate({ mode: p.variant.mode, visits, platform: { allowed: true, code: null } });
    lines.push(`${combo.map((c) => c[0]).join('|')}=${canonicalGate(out)}`);
    for (const v of visits) {
      if (['T1', 'T2'].includes(v.sequence) && out.ai_may_run) g1 = false;
      if (['unknown', 'missing'].includes(v.sequence) && v.physician_confirmed_flair !== true && out.ai_may_run) g1 = false;
    }
    if (out.ai_output_allowed && out.checks.some((c) => c.status === 'pending' || c.status === 'abstain')) g11 = false;
    return;
  }
  for (const e of tables[i]) walk(i + 1, [...combo, e]);
};
walk(0, []);
fail('g4_matrix_digest', createHash('sha256').update(lines.join('\n'), 'utf8').digest('hex') === F.matrix_sha256);
fail('g4_samples', F.samples.every((s) => canonicalGate(evaluateGate(s.input)) === s.expected));
fail('g1_browser', g1);
fail('g11_browser', g11);
fail('g6_unreachable', gateUnavailable().ai_may_run === false && gateUnavailable().ai_output_allowed === false);
const visit = { ...F.matrix.base_visit, skull: 'pending' };
const server = { ...evaluateGate({ mode: 'single', visits: [visit], platform: { allowed: true, code: null } }),
  inputs: { mode: 'single', visits: [visit] }, platform: { allowed: true, code: null } };
fail('rc125_unknown_skull_hides', finalBrowserGate(server, {}).ai_output_allowed === false);
fail('rc125_removed_skull_shows', finalBrowserGate(server, { inputPreparation: 'skull-removed' }).ai_output_allowed === true);
fail('rc125_pending_hides', server.ai_output_allowed === false);
const CORPUS = JSON.parse(readFileSync(process.env.QG_CORPUS, 'utf-8'));
fail('g12_corpus', CORPUS.cases.every((c) => sequenceFromHeader(c.text, c.inversion_time_ms) === c.expected));
fail('g13_no_confirmation_in_a_comparison', evaluateGate({ mode: 'comparison', platform: { allowed: true, code: null },
  visits: [F.matrix.base_visit, { ...F.matrix.base_visit, sequence: 'unknown', physician_confirmed_flair: true }] }).ai_may_run === false);
console.log(JSON.stringify({ failures, checks: 12 }));
"""


def _sha(b: bytes) -> str:
    return hashlib.sha256(b.replace(b"\r\n", b"\n")).hexdigest()


def offline_env():
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    empty = tempfile.mkdtemp(prefix="qg_nc_gcloud_")
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(empty, "missing-credentials.json"),
                "CLOUDSDK_CONFIG": empty, "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


def make_copy(dest):
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for tree in COPY_TREES:
        shutil.copytree(os.path.join(ROOT, tree), os.path.join(dest, tree), ignore=ignore)
    if has_node_modules():       # vitest runs IN the copy (S4): the whole frontend source, node_modules linked
        shutil.copytree(os.path.join(ROOT, "frontend"), os.path.join(dest, "frontend"), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("node_modules", "dist", "coverage"))
        link, target = os.path.join(dest, "frontend", "node_modules"), os.path.join(ROOT, "frontend", "node_modules")
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", link, target], check=True, capture_output=True)
        else:
            os.symlink(target, link, target_is_directory=True)
    for f in COPY_FILES:
        os.makedirs(os.path.dirname(os.path.join(dest, f)), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, f), os.path.join(dest, f))


def has_node_modules():
    return os.path.isdir(os.path.join(ROOT, "frontend", "node_modules"))


def run_backend(copy, env):
    xml_path = os.path.join(copy, "junit.xml")
    p = subprocess.run([PY, "-m", "pytest", *("backend/" + t for t in BACKEND_TESTS), "-q", "-p", "no:cacheprovider",
                        "--timeout=120", "-o", "log_cli=false", f"--junitxml={xml_path}"], cwd=run_cwd("backend", copy),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**env, "PYTHONPATH": os.path.join(copy, "backend")}, timeout=900)
    failed, passed = [], 0
    if os.path.exists(xml_path):
        for case in ET.parse(xml_path).getroot().iter("testcase"):
            name = case.get("name")
            if case.find("failure") is not None or case.find("error") is not None:
                failed.append(name)
            elif case.find("skipped") is None:
                passed += 1
        os.remove(xml_path)
    return {"passed": passed, "failed": len(failed), "failing_tests": sorted(failed), "returncode": p.returncode}


def node_files(copy):
    work = os.path.join(copy, "node_harness")
    os.makedirs(work, exist_ok=True)
    src = open(os.path.join(copy, TS), encoding="utf-8").read()
    line = "import POLICY_JSON from '@/config/qualityGatePolicy.v1.json';"
    assert src.count(line) == 1, "the policy import of gate.ts changed; update the harness"
    src = src.replace(line, "import { readFileSync } from 'node:fs';\n"
                            "const POLICY_JSON = JSON.parse(readFileSync(process.env.QG_POLICY as string, 'utf-8'));")
    with open(os.path.join(work, "gate.ts"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(src)
    with open(os.path.join(work, "package.json"), "w", encoding="utf-8") as fh:
        fh.write('{"type": "module"}\n')
    with open(os.path.join(work, "harness.mjs"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HARNESS)
    return work


def node_env(copy, env):
    return {**env, "QG_POLICY": os.path.join(copy, FPOL), "QG_FIXTURE": os.path.join(copy, "frontend/src/config/qualityGate.cases.v1.json"),
            "QG_BACKEND_POLICY": os.path.join(copy, POL), "NODE_NO_WARNINGS": "1",
            "QG_CORPUS": os.path.join(copy, "frontend/src/config/qualityGate.sequences.v1.json")}


def probe(runner, copy, env, files):
    """The mutant must compile and import before its kill counts."""
    for f in files:
        if f.endswith(".json"):
            try:
                json.loads(open(os.path.join(copy, f), encoding="utf-8").read())
            except ValueError as exc:
                return f"{f} does not parse: {exc}"
    if runner == "backend":
        p = subprocess.run([PY, "-c", IMPORT_PROBE], cwd=run_cwd("backend", copy), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env, timeout=300)
        return None if p.returncode == 0 else (p.stderr.strip().splitlines() or ["import failed"])[-1][:300]
    if runner == "node":
        node_files(copy)
        p = subprocess.run(["node", "--input-type=module", "-e", "await import('./node_harness/gate.ts')"],
                           cwd=run_cwd("node", copy),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=node_env(copy, env),
                           timeout=120)
        return None if p.returncode == 0 else (p.stderr.strip().splitlines() or ["load failed"])[-1][:300]
    return None


def run_node(copy, env):
    node_files(copy)
    p = subprocess.run(["node", "node_harness/harness.mjs"], cwd=run_cwd("node", copy), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=node_env(copy, env), timeout=300)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"passed": 0, "failed": 1, "failing_tests": [f"harness crashed: {p.stderr.strip()[-200:]}"]}
    return {"passed": out["checks"] - len(out["failures"]), "failed": len(out["failures"]), "failing_tests": out["failures"]}


def run_vitest(copy, env):
    p = subprocess.run(["npx", "vitest", "run", *VITEST_TESTS, "--reporter=json", "--pool=threads"],
                       cwd=run_cwd("vitest", copy), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=900, shell=os.name == "nt")
    try:
        data = json.loads(p.stdout[p.stdout.index("{"):])
    except Exception:  # noqa: BLE001
        return {"passed": 0, "failed": 1, "failing_tests": ["vitest output unreadable"]}
    failed = [t["fullName"] for f in data.get("testResults", []) for t in f.get("assertionResults", []) if t["status"] == "failed"]
    return {"passed": data.get("numPassedTests", 0), "failed": len(failed), "failing_tests": failed}


RUNNERS = {"backend": run_backend, "node": run_node}


def run_cwd(runner, copy):
    """The working directory of a runner's test command: always INSIDE the throwaway copy (S4)."""
    return os.path.join(copy, "frontend") if runner == "vitest" else copy


def assert_under(paths, cwd):
    """S4: a mutant is only ever checked by a test run whose working directory contains the mutated file."""
    root = os.path.realpath(cwd)
    for path in paths:
        real = os.path.realpath(path)
        assert os.path.commonpath([real, root]) == root, f"{real} is not under the test run's directory {root}"


def main():
    env = offline_env()
    copy = tempfile.mkdtemp(prefix="qg_negative_controls_")
    try:
        make_copy(copy)
        files = sorted({f for edits, *_ in M.values() for f, _, _ in edits})
        raw = {f: open(os.path.join(copy, f), "rb").read() for f in files if os.path.exists(os.path.join(copy, f))}
        res = {
            "record": "QUALITY-GATE negative controls (RC-122..RC-127, HAZ-025) — DRAFT, PENDING owner approval",
            "date": datetime.date.today().isoformat(),
            "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
            "method": "one mutation at a time in a throwaway copy (never the worktree); every anchor exactly once; the "
                      "mutant must compile/import (or parse / load under Node) before its kill counts; bound tests: "
                      "backend pytest (JUnit) or the Node G4 parity harness; original bytes restored and hash-checked",
            "bound_tests": {"backend": BACKEND_TESTS, "node": "G4 parity harness (shared fixture, matrix digest, G1, G6, G11, RC-125)",
                            "vitest": VITEST_TESTS},
            "source_sha256": {f: _sha(b) for f, b in raw.items()},
            "environment": "offline: GOOGLE_APPLICATION_CREDENTIALS -> missing file, CLOUDSDK_CONFIG -> empty folder, "
                           "GOOGLE_CLOUD_PROJECT=mstool-offline-tests, ANTHROPIC_API_KEY removed",
        }
        res["baseline"] = {"backend": run_backend(copy, env), "node": run_node(copy, env)}
        print("baseline", json.dumps({k: (v["passed"], v["failed"]) for k, v in res["baseline"].items()}))
        assert all(v["failed"] == 0 for v in res["baseline"].values()), "the unmutated copy does not pass"
        res["mutations"] = {}
        for name, (edits, what, runner, controls) in M.items():
            entry = {"reintroduces": what, "runner": runner, "controls": controls}
            if runner == "vitest" and not has_node_modules():
                entry.update({"status": "not_run", "reason": "not run (no node_modules): vitest runs in GitHub Actions"})
                res["mutations"][name] = entry
                print(f"{name:52s} NOT RUN (vitest)")
                continue
            texts = {}
            for f, anchor, repl in edits:
                text = texts.get(f, raw[f].decode("utf-8"))
                if "\r\n" in text:            # a checkout with CRLF line endings: match the same text
                    anchor, repl = anchor.replace("\n", "\r\n"), repl.replace("\n", "\r\n")
                n = text.count(anchor)
                assert n == 1, f"{name}: anchor occurs {n} times in {f}"
                texts[f] = text.replace(anchor, repl, 1)
            for f, text in texts.items():
                with open(os.path.join(copy, f), "wb") as fh:
                    fh.write(text.encode("utf-8"))
            try:
                assert_under([os.path.join(copy, f) for f in texts], run_cwd(runner, copy))
                problem = probe(runner, copy, env, list(texts))
                if problem:
                    entry.update({"status": "invalid", "reason": problem})
                else:
                    out = run_vitest(copy, env) if runner == "vitest" else RUNNERS[runner](copy, env)
                    entry.update({"status": "detected" if out["failed"] else "SURVIVED", "result": out})
            finally:
                for f in texts:
                    with open(os.path.join(copy, f), "wb") as fh:
                        fh.write(raw[f])
                    assert open(os.path.join(copy, f), "rb").read() == raw[f], f"{name}: {f} not restored"
            res["mutations"][name] = entry
            print(f"{name:52s} {entry['status']:9s} {entry.get('result', {}).get('failed', '')}")
        res["restored"] = {"backend": run_backend(copy, env), "node": run_node(copy, env)}
        statuses = [m["status"] for m in res["mutations"].values()]
        res["summary"] = {"mutations": len(statuses), "run": sum(s != "not_run" for s in statuses),
                          "detected": statuses.count("detected"), "survived": statuses.count("SURVIVED"),
                          "invalid": statuses.count("invalid"), "not_run": statuses.count("not_run"),
                          "restored_backend": [res["restored"]["backend"]["passed"], res["restored"]["backend"]["failed"]],
                          "restored_node": [res["restored"]["node"]["passed"], res["restored"]["node"]["failed"]]}
        print("summary", json.dumps(res["summary"]))
    finally:
        shutil.rmtree(copy, ignore_errors=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return 0 if res["summary"]["survived"] == 0 and res["summary"]["invalid"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
