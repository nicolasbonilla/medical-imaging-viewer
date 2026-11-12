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

BACKEND_TESTS = ["tests/unit/test_quality_gate_matrix.py", "tests/unit/test_rc122_quality_gate_wiring.py",
                 "tests/unit/test_rc123_rc062_monotonicity.py", "tests/unit/test_rc122_flags_off_identity.py",
                 "tests/unit/test_rc122_one_gate.py", "tests/unit/test_rc122_review7.py",
                 "tests/unit/test_rc122_review8.py", "tests/unit/test_rc122_review9.py", "tests/unit/test_rc122_review10.py",
                 "tests/unit/test_rc122_review11.py"]
VITEST_TESTS = ["src/components/BrowserFlamesCard.qualityGate.test.tsx", "src/components/QualityGatePanel.test.tsx",
                "src/services/qualityGate/gate.test.ts", "src/services/flames/__tests__/headerEvidence.flagsOff.test.ts",
                "src/components/LongitudinalCompare.qualityGate.test.tsx", "src/components/LongitudinalResultPanel.qualityGate.test.tsx",
                "src/services/qualityGate/api.test.ts", "src/components/BrowserFlamesCard.serverDecides.test.tsx",
                "src/components/BrowserFlamesCard.boundedTraffic.test.tsx", "src/components/BrowserFlamesCard.retry.test.tsx"]
COPY_TREES = ["backend/app", "backend/data"]
COPY_FILES = ["backend/pytest.ini", "backend/tests/__init__.py", "backend/tests/conftest.py",
              "backend/tests/unit/__init__.py", *("backend/" + t for t in BACKEND_TESTS),
              "frontend/src/services/flames/headerEvidence.ts",
              # sixth review (G27): the corpus and the pre-PR snapshot are server test data
              "backend/tests/fixtures/quality_gate/sequences.v1.json", "backend/tests/fixtures/quality_gate/pre_pr_snapshot.v1.json",
              "backend/tests/fixtures/quality_gate/real_flair.v1.json",
              # eleventh review: the report route's fixture (I1, I2) and the shared UI states (I4)
              "backend/tests/unit/test_capa014_report_provider_payload.py", "frontend/src/config/qualityGate.ui_states.v1.json",
              "frontend/src/i18n/locales/en.json", "frontend/src/i18n/locales/es.json",
              "frontend/src/i18n/locales/de.json", "frontend/src/services/qualityGate/gate.ts",
              "frontend/src/components/BrowserFlamesCard.tsx", "frontend/src/components/QualityGatePanel.tsx",
              "frontend/src/hooks/useGateConsultation.ts",
              "frontend/src/services/qualityGate/api.ts", "frontend/src/services/flames/contrastGate.ts",
              "frontend/src/components/LongitudinalResultPanel.tsx", "frontend/src/components/LongitudinalCompare.tsx",
              # fifth review of PR #81 (G26): the flags-off snapshot, its generator and the route harness
              "frontend/src/config/qualityGate.flags_off_snapshot.v1.json",
              "scripts/safety/quality_gate_flags_off_snapshot.py", "backend/tests/unit/_flags_off_harness.py"]
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
LRP = "frontend/src/components/LongitudinalResultPanel.tsx"
CT = "backend/app/api/routes/clinical_tools.py"
DI = "backend/app/services/dataset_inventory.py"
HE = "frontend/src/services/flames/headerEvidence.ts"
AM = "backend/app/core/logging/audit_middleware.py"
RPG = "backend/app/services/report_payload_guard.py"
BRS = "backend/app/services/brain_report_service.py"
AIR = "backend/app/api/routes/ai_report.py"
LCS = "backend/app/services/longitudinal_candidate_safety.py"
DIC = "backend/app/services/displayed_image_check.py"
CG = "frontend/src/services/flames/contrastGate.ts"
REG = "backend/app/agent_platform/registry.py"
LC = "frontend/src/components/LongitudinalCompare.tsx"
HOOK = "frontend/src/hooks/useGateConsultation.ts"
AUD = "backend/app/core/logging/audit.py"
API = "frontend/src/services/qualityGate/api.ts"
EN = "frontend/src/i18n/locales/en.json"
CMP_ACTION = ("If you are sure this visit's image is a T2-FLAIR, tick its confirmation box below and compare again. "
              "Otherwise compare the images visually with the overlay.")

# Tenth review of PR #81 (SIMPLIFY): controls RETIRED because the part they mutated no longer exists — kept here and in the
# record with the reason, never silently dropped
RETIRED = {
    "W11_consultation_cache_off": "the consultation cache was removed (S1): there is no cache to switch off",
    "W12_cached_answers_counted": "the consultation cache was removed (S1): every consultation is evaluated and counted",
    "W13_release_decision_cached": "the consultation cache was removed (S1): no decision is ever served from a cache",
    "W14_cache_ignores_the_attestation": "the consultation cache and its key were removed (S1)",
    "Y4_cache_ignores_the_clinician": "the consultation cache and its key were removed (S1); every attestation is audited by run_quality_gate",
    "Y5_cache_ignores_the_records": "the consultation cache and its key were removed (S1)",
    "AB7_request_counter_after_the_reads": "the two limits were merged into ONE before any read (S1); S8_no_rate_limit and AC7_limit_after_the_reads cover it",
    "AB8_cached_attestation_not_audited": "the cached path was removed (S1): an attestation is always evaluated and audited",
    "S5_audit_without_the_deciding_code": "the deciding code moved from the packed audit code to structured details (S4); AA6_audit_details_dropped and AC5_durable_record_drops_the_details cover it",
}

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
    "Q9_abstention_does_not_withhold": ([(QG, '    if gate.get("ai_output_allowed") is not True:      # ONE abstention path (second review, finding 5)\n',
        '    if False:\n')],
        "a comparison the gate stops still carries lesion counts and loads", "backend", "RC-123"),
    "Q10_route_ignores_the_gate": ([(SA, '        if gate is not None and gate.get("ai_output_allowed") is not True:\n            return qg.abstained_comparison(gate)\n', '        pass\n'),
        (SA, '            visit_check=visit_check, review_read_failed=review_read_failed, gate=gate,\n', '            visit_check=visit_check, review_read_failed=review_read_failed, gate=None,\n')],
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
    "Q16_server_says_skull_stripped": ([(QG, '        "skull": skull,\n    }\n', '        "skull": "stripped",\n    }\n')],
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
    "Q21_success_not_audited": ([(QG, '            reg.audit("success", audit_code(result), event=event, agent_id=AGENT_ID,\n',
        '            (lambda *a, **k: None)("success", audit_code(result), event=event, agent_id=AGENT_ID,\n')],
        "a consultation that lets the AI run leaves no audit record", "backend", "RC-126"),
    "Q22_trace_attribute_dropped": ([(TR, '    "mstool.gate.status": lambda v: v in ("pass", "warn", "pending", "abstain"),\n', '')],
        "the trace allow-list loses the check status", "backend", "RC-126"),
    "Q23_registry_entry_approved": ([(AG, '        "status": "pending",\n        "ref": "feat/quality-gate (stacked on PR #79): entry to be approved by the owner (D-QG-1)"',
        '        "status": "approved",\n        "ref": "feat/quality-gate (stacked on PR #79): entry to be approved by the owner (D-QG-1)"')],
        "the repository records the owner's approval", "backend", "RC-126"),
    "Q24_policy_changed_silently": ([(POL, '    "thin_limit_mm": 1.5,\n', '    "thin_limit_mm": 2.0,\n')],
        "the backend policy changes without the registry, the fixture or the browser copy", "backend", "RC-126, RC-127"),
    # ── input derivation (RC-122) ──
    "Q25_file_name_as_evidence": ([(QG, '    visit = visit_inputs(fields, acq, stored, physician_confirmed_flair=physician_confirmed_flair, skull=skull)\n',
        '    visit = visit_inputs(fields, acq, f"{stored or \'\'} {file_path}", physician_confirmed_flair=physician_confirmed_flair, skull=skull)\n')],
        "the file name is read as the sequence (RC-049 forbids it)", "backend", "RC-122"),
    "Q26_t1_flair_accepted": ([(QG, '    if is_other or (flair and t1):          # a non-FLAIR name, or a T1-weighted FLAIR: ALWAYS abstains\n',
        '    if is_other:\n')],
        "a T1-weighted FLAIR is taken as a T2 FLAIR", "backend", "RC-122"),
    "Q27_short_inversion_time_ignored": ([(QG, '    elif ti is not None and ti < rules["min_flair_inversion_time_ms"]:\n', '    elif False:\n')],
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
    "R4_no_attestation_in_a_comparison": ([(POL, '    "confirmation_modes": ["single", "comparison"],\n', '    "confirmation_modes": ["single"],\n')],
        "the per-visit attestation of a comparison is never taken (two uploads never comparable, F1)", "backend", "RC-122"),
    "R5_lax_attestation_boolean": ([(CT, '    physician_confirmed_flair: StrictBool = False   # S3: a deliberate attestation, never coerced from "true"/1\n',
        '    physician_confirmed_flair: bool = False\n')],
        "'true' or 1 accepted as the physician's attestation", "backend", "RC-122, RC-126"),
    "R6_attestation_not_audited": ([(QG, '    attested = any(c.get("code") == "sequence_confirmed_by_physician" for c in result.get("checks", []))\n',
        '    attested = False\n')],
        "the physician's attestation leaves no audit trace", "backend", "RC-126"),
    "R7_comparison_action_missing": ([(EN, '        "action_comparison": "' + CMP_ACTION + '"\n      },\n      "sequence_confirmed_by_physician"',
        '        "action_comparison": ""\n      },\n      "sequence_confirmed_by_physician"')],
        "a comparison stopped on the sequence says nothing about what to do", "backend", "RC-127"),
    "R8_gate_after_loading": ([(SA, '        if gate is not None and gate.get("ai_output_allowed") is not True:\n            return qg.abstained_comparison(gate)\n', '        pass\n')],
        "the comparison loads masks, images, registration and atlas before the gate stops it", "backend", "RC-123"),
    "R10_raw_codes_in_caveat": ([(QG, '    reasons = [CAVEAT_REASONS.get(c, "a quality check did not pass") for c in explain(gate)["causes"]]\n',
        '    reasons = list(explain(gate)["causes"])\n')],
        "the caveat shows raw codes instead of plain reasons", "backend", "RC-123, RC-127"),
    "R11_pixels_decoded": ([(QG, '        ds = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True, force=True)\n',
        '        imaging_service.load_dicom(data)\n        ds = pydicom.dcmread(io.BytesIO(data), force=True)\n')],
        "the gate decodes the whole image instead of the header", "backend", "RC-122"),
    "R12_header_cache_off": ([(QG, '    if key and not fields.get("unreadable"):          # S1: a failed or unreadable read is NEVER remembered\n',
        '    if False:\n')],
        "every consultation downloads and parses the file again", "backend", "RC-122"),
    "R13_parsed_on_the_event_loop": ([(QG, '    return await asyncio.to_thread(read_header_fields, data, decoded)\n', '    return read_header_fields(data, decoded)\n')],
        "the header is parsed on the event loop", "backend", "RC-122"),
    "R14_acquisition_read_twice": ([(SA, '    if file_id not in memo:\n        memo[file_id] = _source_acquisition(file_id)\n    return memo[file_id]\n',
        '    return _source_acquisition(file_id)\n')],
        "the acquisition records are read again for RC-062", "backend", "RC-123"),
    "R15_thin_limit_not_the_evaluated_policy": ([(QG, '    limit = thin_limit_mm if thin_limit_mm is not None else _policy()["thickness"]["thin_limit_mm"]\n',
        '    limit = _policy()["thickness"]["thin_limit_mm"]\n')],
        "the thin limit of another policy than the one evaluated", "backend", "RC-124"),
    # ── second review of PR #81 ──
    "S1_inventory_routed_to_the_gate": ([(DI, '    for label, patterns in _SEQUENCE_PATTERNS:\n',
        '    from app.services.quality_gate import classify_sequence\n    found = classify_sequence(blob)\n'
        '    return SEQ_FLAIR if found["class"] == SEQ_FLAIR else (found["family"] or found["weighting"])\n'
        '    for label, patterns in _SEQUENCE_PATTERNS:\n')],
        "the research inventory answers differently with the flags off (routed to the gate's classifier; G26 b)", "backend", "RC-122"),
    "S2_tirm_not_a_flair_name": ([(POL, '      "flair_words": ["tirm"],\n', '      "flair_words": [],\n')],
        "a Siemens TIRM FLAIR is not recognised (the gate and RC-049 disagree)", "backend", "RC-122"),
    "S3_text_inversion_time_ignored": ([(QG, '        (v for v in (text_inversion_time_ms(t, policy) for t in texts) if v is not None), None)\n',
        '        (v for v in () if v is not None), None)\n')],
        "'FLAIR TI=900' in the text taken as a FLAIR", "backend", "RC-122"),
    "S4_server_ignores_the_skull_outcome": ([(CT, '                                                   skull=body.skull)\n',
        '                                                   skull="pending")\n')],
        "the server never decides the releasing decision (the browser alone does)", "backend", "RC-126"),
    "S6_endpoint_not_behind_the_flag": ([(CT, '    if not get_settings().QUALITY_GATE_ENFORCED:\n        # U1', '    if False:\n        # U1')],
        "the endpoint answers while the gate is not enforced", "backend", "RC-126"),
    "S7_platform_after_the_io": ([(CT, '    if not qg.platform_allows():\n', '    if False:\n')],
        "a refused gate still authorizes and downloads the file", "backend", "RC-126"),
    "S8_no_rate_limit": ([(CT, '    wait = qg.rate_limit(str(getattr(current_user, "id", "")))\n', '    wait = None\n')],
        "the endpoint can trigger unbounded downloads", "backend", "RC-126"),
    "S9_whole_file_downloaded": ([(DIC, '    ranged = getattr(storage_service, "download_file_range", None)\n', '    ranged = None\n')],
        "the header check downloads the whole image", "backend", "RC-122"),
    "S10_no_range_retry": ([(DIC, '        if complete or len(raw) < size or size >= largest:\n', '        if True:\n')],
        "a header longer than the first range is read truncated", "backend", "RC-122"),
    "S11_unreadable_metadata_is_a_500": ([(SA, '        except Exception as e:  # noqa: BLE001 — unknown source: the gate abstains with its reason\n',
        '        except ZeroDivisionError as e:  # noqa: BLE001\n')],
        "unreadable segmentation metadata breaks the comparison instead of abstaining", "backend", "RC-123"),
    "S12_metadata_read_twice": ([(SA, '                    meta = metas[mask_id] if mask_id in metas else await segmentation_service.get_metadata(mask_id)\n',
        '                    meta = await segmentation_service.get_metadata(mask_id)\n')],
        "each visit's metadata is read again by the loader", "backend", "RC-123"),
    "S13_policy_copied_per_consultation": ([(QG, '    policy = _policy()                 # cached, read only (finding 6)\n', '    policy = load_policy()\n')],
        "a deep copy of the policy on every consultation", "backend", "RC-126"),
    # ── third review of PR #81 ──
    "U1_sequence_name_read_as_a_description": ([(QG, '    texts = [t for t in (desc if isinstance(desc, (list, tuple)) else [desc]) if isinstance(t, str)]\n',
        '    texts = [t for t in (desc if isinstance(desc, (list, tuple)) else [desc]) if isinstance(t, str)]\n'
        '    if isinstance(fields.get("sequence_name"), str):\n        texts.append(fields["sequence_name"])\n')],
        "a Siemens '*tir...' SequenceName read as 'T2*': valid FLAIR rejected", "backend", "RC-122"),
    "U2_image_type_ignored": ([(QG, '                            _image_type_class(fields.get("image_type"), vocab)) if c]\n', '                            None) if c]\n')],
        "a reformatted or parametric image (ImageType) taken as an original FLAIR", "backend", "RC-122"),
    "U3_inventory_classifies_ids": ([(DI, '[descriptive_name(t) for t in texts[1:]]', 'list(texts[1:])')],
        "the inventory classifies file ids and paths (UUID fragments turn FLAIR into other)", "backend", "RC-122"),
    "U4_route_not_audited": ([(AM, '    "/api/v1/clinical/quality-gate",   # G22 (DRAFT)\n', '')],
        "the quality-gate route is missing from the audit middleware", "backend", "RC-126"),
    "U5_unrecorded_scanners_abstain_in_the_gate": ([(QG, '    if missing and unrecorded:\n', '    if False:\n')],
        "the gate stops two uploads itself, so the physician reads the gate's reason instead of RC-062's", "backend", "RC-123"),
    "U7_comparison_attestation_ignored": ([(QG, '        visits.append(visit_inputs(fields, acq, stored, physician_confirmed_flair=att is True, with_scanner=True))\n',
        '        visits.append(visit_inputs(fields, acq, stored, physician_confirmed_flair=False, with_scanner=True))\n')],
        "the per-visit attestation of a comparison is dropped", "backend", "RC-122"),
    "U8_lax_comparison_attestation": ([(SA, '    if not isinstance(raw, dict) or set(raw) - {"tp1", "tp2"} or not all(isinstance(v, bool) for v in raw.values()):\n',
        '    if not isinstance(raw, dict):\n')],
        "'true', 1 or unknown visits accepted as an attestation", "backend", "RC-122"),
    "U9_unreadable_header_silent": ([(QG, '    return {**_NO_HEADER, "unreadable": True}\n', '    return dict(_NO_HEADER)\n')],
        "an unreadable header passes silently as 'missing'", "backend", "RC-122"),
    "U11_completeness_on_the_loop": ([(DIC, '        return await asyncio.to_thread(inspect, raw) if in_thread else inspect(raw)\n',
        '        return inspect(raw)\n')],
        "the header completeness check runs on the event loop", "backend", "RC-122"),
    "U12_gate_on_the_loop": ([(CT, '    result = await asyncio.to_thread(qg.run_quality_gate, inputs, study_key=qg.study_of(paths[0]) or paths[0], actor=actor)\n',
        '    result = qg.run_quality_gate(inputs, study_key=qg.study_of(paths[0]) or paths[0], actor=actor)\n')],
        "the gate runs on the event loop", "backend", "RC-126"),
    "U13_default_ranges_download_repeatedly": ([(DIC, '    if ranged is None or getattr(type(storage_service), "download_file_range", None) is IStorageService.download_file_range:\n',
        '    if ranged is None:\n')],
        "a storage without real ranges downloads the whole file on every retry", "backend", "RC-122"),
    # ── fourth review of PR #81 ──
    "X1_rc062_relaxed_for_unrecorded_pairs": ([(QG, '    presented = lcs.present_comparison(result, acquisition_check=acquisition_check, evidence=evidence,\n',
        '    presented = lcs.present_comparison(result, acquisition_check=({**acquisition_check, "status": "same"} if gate is not None '
        'and "scanner_not_recorded" in (gate.get("codes") or []) else acquisition_check), evidence=evidence,\n')],
        "the D-QG-10 relaxation of RC-062 reintroduced (HAZ-007)", "backend", "RC-123"),
    "X2_a_warned_gate_lifts_rc062": ([(QG, '    out = {**result, "quality_gate": gate}\n', '    out = {**result, "quality_gate": gate, "abstained": False}\n')],
        "a gate that only warns lifts an RC-062 abstention", "backend", "RC-123"),
    "X3_sel_keeps_its_own_rule": ([(SA, '        if lcs.rc062_withholds(acquisition_check, visit_check):   # G25: RC-062\'s one predicate (the gate stopped above)\n',
        '        if acquisition_check["status"] != "same":\n')],
        "SEL decides comparability with its own rule", "backend", "RC-123"),
    "X4_sel_ignores_the_gate": ([(SA, '        if gate is not None and gate.get("ai_output_allowed") is not True:\n'
        '            return {"ok": False, "abstained": True, "reason": qg.gate_caveat(gate),',
        '        if False:\n            return {"ok": False, "abstained": True, "reason": qg.gate_caveat(gate),')],
        "the SEL search ignores the gate's abstention", "backend", "RC-123"),
    "X5_shared_predicate_ignores_visit_order": ([(LCS, '    return acquisition_check.get("status") != "same" or visit_check.get("status") != "ok"\n',
        '    return acquisition_check.get("status") != "same"\n')],
        "the one RC-062 predicate ignores an unknown visit order", "backend", "RC-123"),
    "X6_warnings_not_in_the_caveat": ([(QG, '    if reasons:                                       # R4: a warned comparison says so (the assistant reads this)\n',
        '    if False:\n')],
        "a warned comparison looks clean to the assistant", "backend", "RC-127"),
    "X7_warnings_dropped_from_the_report_payload": ([(RPG, '        if warnings:\n            o["quality_gate_warnings"] = warnings\n        return o\n',
        '        if False:\n            o["quality_gate_warnings"] = warnings\n        return o\n')],
        "the report never receives the gate's warnings", "backend", "RC-127"),
    "X8_report_prompt_silent": ([(BRS, '            if gate_warnings:\n', '            if False:\n')],
        "the report draft presents a warned comparison as clean", "backend", "RC-127"),
    "X9_report_notice_silent": ([(AIR, '    if reasons:\n        lines.append(qg.reason_lead("warned", language)',
        '    if False:\n        lines.append(qg.reason_lead("warned", language)')],
        "the code-written notice of the draft omits the gate's warnings", "backend", "RC-127"),
    # ── fifth review of PR #81: G26 flags-off identity, D-QG-12, F1-F5, cleanup ──
    "W1_rc049_gate_path_with_the_flag_off": ([(HE, "  return (options.qualityGate ?? FEATURES.QUALITY_GATE)\n", "  return (options.qualityGate ?? true)\n")],
        "the in-browser AI's header evidence changes with VITE_ENABLE_QUALITY_GATE off (G26 a)", "node", "RC-122"),
    "W2_rc049_base_rule_changed": ([(HE, "|LOCALI[SZ]ER|SCOUT)\\b/;\n", "|LOCALI[SZ]ER|SCOUT|CAL)\\b/;\n")],
        "the base RC-049 rule is edited, so production answers change with the flag off (G26 a)", "node", "RC-122"),
    "W5_attestation_parsed_with_the_gate_off": ([(SA, '    if not settings.QUALITY_GATE_ENFORCED:\n        return None, {}, {}, None\n    attestation = _attestation(body)\n',
        '    attestation = _attestation(body)\n    if not settings.QUALITY_GATE_ENFORCED:\n        return None, {}, {}, None\n')],
        "a malformed quality_gate_attestation gives 400 with the gate off (G26 c)", "backend", "RC-122"),
    "W6_sel_type_checked_early_with_the_gate_off": ([(SA, '        if settings.QUALITY_GATE_ENFORCED and any(s.get("type") != "segmentation" for s in (tp1_spec, tp2_spec)):\n',
        '        if any(s.get("type") != "segmentation" for s in (tp1_spec, tp2_spec)):\n')],
        "the SEL search checks its inputs in another order with the gate off (G26 c)", "backend", "RC-123"),
    "W7_weak_words_always_other": ([(QG, '    is_other = bool(hits - c["weak"]) or (bool(hits) and not flair)\n', '    is_other = bool(hits)\n')],
        "'AX FLAIR CAL', 'FLAIR loc', 'sag_flair_dir-AP' rejected with the gate on (D-QG-12, G19 extension)", "backend", "RC-122"),
    "W9_weak_word_alone_names_no_sequence": ([(QG, '    is_other = bool(hits - c["weak"]) or (bool(hits) and not flair)\n', '    is_other = bool(hits - c["weak"])\n')],
        "a localizer or calibration series ('AX LOC') is no longer 'other' (D-QG-12)", "backend", "RC-122"),
    "W17_retry_seconds_dropped": ([(QG, '"details": {"code": "gate_rate_limited", "retry_after_s": wait}}})',
        '"details": {"code": "gate_rate_limited"}}})')],
        "over the limit, the physician is not told how long to wait (F3)", "backend", "RC-127"),
    "W18_consultation_audited_as_an_ai_run": ([(QG, '        event = "agent.run" if releases_output and result.get("ai_output_allowed") is True else "agent.consultation"\n',
        '        event = "agent.run"\n')],
        "every consultation is recorded as an AI run (F4)", "backend", "RC-126"),
    "W19_route_audited_as_an_ai_run": ([(AM, '    ("POST", "/api/v1/clinical/quality-gate"): (E.QUALITY_GATE_CONSULTATION, "image"),',
        '    ("POST", "/api/v1/clinical/quality-gate"): (E.CLINICAL_AI_RUN, "image"),')],
        "opening an image records an AI run (F4)", "backend", "RC-126"),
    "W20_sink_maps_every_event_to_an_ai_run": ([(REG, '        etype = (AuditEventType.QUALITY_GATE_CONSULTATION if event.get("event") == "agent.consultation"\n'
        '                 else AuditEventType.CLINICAL_AI_RUN)\n', '        etype = AuditEventType.CLINICAL_AI_RUN\n')],
        "the server log records a consultation as an AI run (F4)", "backend", "RC-126"),
    "W22_present_comparison_keeps_its_own_rule": ([(LCS, '    if rc062_withholds(acquisition_check, visit_check):   # RC-062\n',
        '    if acquisition_check.get("status") != "same":   # RC-062\n')],
        "compare and SEL decide comparability with two rules (cleanup, G25)", "backend", "RC-123"),
    "V14_attestation_not_kept_for_the_pair": ([(LC, "    return attested.current?.pair === pairKey ? attested.current.value : undefined;\n",
        "    return isAttestation(given) ? given : undefined;\n")],
        "the refresh after a radiologist decision drops the physician's attestation (F1)", "vitest", "RC-122"),
    "V15_attestation_kept_across_pairs": ([(LC, "    return attested.current?.pair === pairKey ? attested.current.value : undefined;\n",
        "    return attested.current?.value;\n"), (LC, "    attested.current = null;\n", "")],
        "an attestation given for one pair is sent for another (F1)", "vitest", "RC-122"),
    "V16_sel_without_the_attestation": ([(LC, "        attestationFor(),\n", "")],
        "the SEL search never sends the pair's attestation (F2)", "vitest", "RC-122"),
    "V17_sel_shows_the_english_reason": ([(LC, "                {selResult.quality_gate && selResult.quality_gate.ai_output_allowed !== true ? (\n",
        "                {false ? (\n")],
        "a gate stop in the SEL search is shown as the backend's English reason (F2)", "vitest", "RC-127"),
    "V18_rate_limit_shown_as_unavailable": ([(API, "    if (response?.status === 429) {\n", "    if (false) {\n")],
        "'too many checks' shown as 'the check could not be completed' (F3)", "vitest", "RC-127"),
    # ── sixth review of PR #81: one server-authoritative gate (G27), A1-A4, U1-U3 ──
    "Y1_nifti_text_fields_unread": ([(QG, '    for key in ("descrip", "aux_file", "intent_name", "db_name"):\n', '    for key in ():\n')],
        "the server ignores the NIfTI descrip, so an uploaded T1 named there is 'missing' (A1)", "backend", "RC-122"),
    "Y2_nifti_extensions_unread": ([(QG, '    for ext in list(getattr(hdr, "extensions", []) or []):\n', '    for ext in []:\n')],
        "the server ignores NIfTI extensions (text and DICOM attributes) the browser used to read (A1)", "backend", "RC-122"),
    "Y3_comparison_ignores_the_headers": ([(QG, '        fields = h if isinstance(h, dict) else {**_NO_HEADER, "no_source": True} if not s else {**_NO_HEADER, "unreadable": True}\n',
        '        fields = dict(_NO_HEADER)\n')],
        "a comparison classifies from the series record only: uploaded DICOM FLAIR pairs are 'missing' (A1)", "backend", "RC-123"),
    "Y6_answer_names_no_attestable_visit": ([(QG, '        "attestable_visits": _attestable_visits(checks, policy, mode, rc062_withholds),\n',
        '        "attestable_visits": [],\n')],
        "the browser is never told which visit the physician may attest (G27)", "backend", "RC-122"),
    "Y7_action_ignores_the_mode": ([(QG, '    return key if isinstance(key, str) else "action"\n', '    return "action"\n')],
        "a comparison is told to tick a box it does not show (G14 via the answer, G27)", "backend", "RC-127"),
    "Y8_report_gives_rc062_reason_for_a_gate_stop": ([(AIR, '    if account and account["stopped"]:\n', '    if False:\n')],
        "the report says the acquisition differs when the gate stopped the pair (A4)", "backend", "RC-127"),
    "Y9_caveat_drifts_from_the_report": ([(QG, 'CAVEAT_REASONS = {code: row["en"] for code, row in _REASONS["reasons"].items()}\n',
        'CAVEAT_REASONS = {code: row["en"].replace(" (only a lower bound is known)", "") for code, row in _REASONS["reasons"].items()}\n')],
        "the assistant's caveat and the report notice give two different sentences (A4)", "backend", "RC-127"),
    "Y10_image_type_dropped": ([(QG, '            "image_type": [str(v) for v in image_type] if image_type is not None and not isinstance(image_type, str)\n',
        '            "image_type": None if True else [str(v) for v in image_type] if image_type is not None and not isinstance(image_type, str)\n')],
        "a reformatted image (ImageType MPR) read by the server as an original FLAIR (A1)", "backend", "RC-122"),
    "Y11_rc049_reads_the_header_itself": ([(HE, "  const verdict: HeaderVerdict = NOT_FLAIR.has(cls) ? 'contradicts' : cls === 'FLAIR' ? 'supports' : 'none';\n",
        "  const verdict: HeaderVerdict = 'supports';\n")],
        "with the gate on, RC-049 accepts what the server classified as another sequence (G27)", "node", "RC-122"),
    "V19_attestations_replace": ([(LC, "      attested.current = { pair: pairKey, value: { tp1: before.tp1 || given.tp1, tp2: before.tp2 || given.tp2 } };\n",
        "      attested.current = { pair: pairKey, value: given };\n")],
        "attesting visit 2 drops the attestation of visit 1 (U1)", "vitest", "RC-122"),
    "V20_no_automatic_retry": ([(HOOK, "    const id = setTimeout(() => dispatch({ type: 'retry' }), state.wait * 1000);\n",
        "    const id = setTimeout(() => undefined, state.wait * 1000);\n")],
        "a rate-limited check is never repeated: Run stays disabled (U2)", "vitest", "RC-126"),
    "V21_final_decision_keyed_to_the_file": ([(CARD, "    gateOn && doneResult && doneResult.fileId === flairFileId ? doneResult : null,\n",
        "    gateOn && doneResult && doneResult.fileId === flairFileId ? doneResult.fileId : null,\n")],
        "a re-run of the same file shows the previous run's decision (U3)", "vitest", "RC-126"),
    "V22_panel_action_not_from_the_answer": ([(PANEL, "${actionOf(result, c.code as string)}", "action")],
        "the panel ignores the action the answer names (G27)", "vitest", "RC-127"),
    "V23_attestable_visits_not_from_the_answer": ([(LRP, "  const visits = (['tp1', 'tp2'] as const).filter((v) => (gate.attestable_visits ?? []).includes(v));\n",
        "  const visits = (['tp1', 'tp2'] as const).filter(() => true);\n")],
        "the comparison offers an attestation for a visit the server did not name (G27)", "vitest", "RC-122"),
    # ── eleventh review of PR #81: I1 the server's record, I2 type-safe, I3 punctuation kept, I4, I5 one record, I6 ──
    "AD1_report_trusts_the_client_block": ([(QG, '    decision = stored_decision(longitudinal.get("quality_gate"))\n',
        '    decision = longitudinal.get("quality_gate") if isinstance(longitudinal.get("quality_gate"), dict) else None\n')],
        "the report takes the gate's decision, causes and warnings from the client's copy (I1)", "backend", "RC-127"),
    "AD2_unverified_gate_treated_as_clean": ([(QG, '    if decision is None:\n        return {"established": False, "stopped": True, "causes": ["gate_not_established"], "warnings": []}\n',
        '    if decision is None:\n        return None\n')],
        "a forged, unknown or missing trace id is reported as a clean comparison (I1)", "backend", "RC-127"),
    "AD3_decisions_not_recorded": ([(QG, '    _remember(result)                                 # I1: the report reads this record, never the client\'s copy\n', '')],
        "the server keeps no record of its decisions: every report is 'not established' (I1)", "backend", "RC-127"),
    "AD4_explain_not_type_safe": ([(QG, '                 if isinstance(c, dict) and text(c.get("code")) in statuses]\n',
        '                 if isinstance(c, dict) and c.get("code") in statuses]\n')],
        "a list in place of a code breaks the report with a 500 (I2)", "backend", "RC-127"),
    "AD5_file_name_punctuation_dropped": ([(DI, '    return "".join(kept).strip("-_. ")\n', '    return " ".join(t for t in kept if t[:1].isalnum())\n')],
        "'AX_T2*' in a file name reads as T2, not SWI: the flags-off inventory differs from the base (I3)", "backend", "RC-122"),
    "AD6_middleware_duplicates_the_record": ([(AM, '        if (method, template) in SELF_AUDITED_ROUTES and status < 500 and status not in (401, 403):\n',
        '        if False:\n')],
        "two audit records per consultation, and a consultation record for a 404 (I5)", "backend", "RC-126"),
    "V31_governed_without_the_warnings": ([(LRP, ".filter((c) => c.status === 'warn' && c.code)", ".filter(() => false)")],
        "RC-062's line hides the gate's warnings for the pair (I4)", "vitest", "RC-127"),
    "V32_run_asks_again_without_an_attestation": ([(CARD, "    if (!attestation && preflight?.ai_may_run === true && preflight.subject?.file_id === fileAtClick) {\n",
        "    if (false) {\n")],
        "three consultations per run instead of two (I6)", "vitest", "RC-126"),
    # ── tenth review of PR #81: S1 no consultation cache, S2 exam-level fields, S3 RC-062's own spacing, S4 no cut, U1 ──
    "AC1_transient_error_remembered": ([(QG, '    if key and not fields.get("unreadable"):          # S1: a failed or unreadable read is NEVER remembered\n',
        '    if key:\n')],
        "a transient storage error is remembered: the image stays 'unreadable' on every later consultation (S1)", "backend", "RC-122"),
    "AC2_exam_level_protocol_vetoes": ([(QG, '    if exam and not any(c in ("other", "T1", "T2", "FLAIR") for c in classes):   # the series is silent (S2)\n'
        '        classes.append("FLAIR" if _classify_tokens(sequence_tokens(exam[0]), vocab)[0] == "FLAIR" else "unknown")\n',
        '    classes += [_classify_tokens(sequence_tokens(t), vocab)[0] for t in exam]\n')],
        "a GE exam protocol 'BRAIN W WO CONTRAST' stops a FLAIR series with no way out (S2)", "backend", "RC-122"),
    "AC3_dicom_spacing_predicted": ([(QG, '                "voxel_spacing_mm": None}\n',
        '                "voxel_spacing_mm": [lcs._number(v) for v in list(getattr(ds, "PixelSpacing", []) or [])[:2]] + [lcs._number(getattr(ds, "SliceThickness", None))]}\n')],
        "a DICOM source RC-062 cannot load is predicted comparable: a futile attestation is offered (S3)", "backend", "RC-123"),
    "AC4_rc062_spacing_without_the_3d_check": ([(LCS, '        if len(img.shape) != 3:\n            return None\n',
        '        if False:\n            return None\n')],
        "a 4-D source RC-062 withholds at run time is predicted comparable (S3)", "backend", "RC-123"),
    "AC5_durable_record_drops_the_details": ([(AUD, '    "causes", "warnings", "attested_visits", "decision", "mode", "released", "withheld_by",\n', '')],
        "the durable audit record drops the causes and the attested visits (S4)", "backend", "RC-126"),
    "AC6_reason_cut": ([(REG, "reason=f\"{event.get('event', 'agent.decision')}:{event.get('code', 'unknown')}\",\n",
        "reason=f\"{event.get('event', 'agent.decision')}:{event.get('code', 'unknown')}\"[:24],\n")],
        "the audit reason is cut and loses the decision (S4)", "backend", "RC-126"),
    "AC7_limit_after_the_reads": ([(CT, '    wait = qg.rate_limit(str(getattr(current_user, "id", "")))\n    if wait is not None:\n        return qg.rate_limited_response(wait)\n', ''),
        (CT, '    paths = await _authorized_inputs([body.file_id], None, None, current_user)\n',
         '    paths = await _authorized_inputs([body.file_id], None, None, current_user)\n'
         '    wait = qg.rate_limit(str(getattr(current_user, "id", "")))\n    if wait is not None:\n        return qg.rate_limited_response(wait)\n')],
        "requests over the limit are still authorized and refused ones still audited (O1, S1)", "backend", "RC-126"),
    "V30_check_again_before_the_last_answer": ([(HOOK, "    settled: own && !state.inFlight && state.answer !== null && state.wait === null,\n",
        "    settled: own && state.answer !== null && state.wait === null,\n")],
        "'Check again' appears while the last retry is still in flight (U1)", "vitest", "RC-126"),
    # ── ninth review of PR #81: G33 no dead end, G34 image-level, G35 validation first, G30 extended, O1-O3 ──
    "AB1_derived_primary_blocked": ([(POL, '      "image_type_other": ["secondary", "mpr",', '      "image_type_other": ["derived", "secondary", "mpr",')],
        "a real FLAIR with on-scanner corrections (DERIVED\\PRIMARY\\NORM\\DIS2D) is stopped as 'other' with no way out (G33)", "backend", "RC-122"),
    "AB2_da_fl_not_dark_fluid": ([(POL, '[["dark", "fluid"], ["dark", "fl"], ["da", "fl"], ["fluid", "attenuated"]]', '[["dark", "fluid"], ["fluid", "attenuated"]]')],
        "a Siemens t2_spc_da-fl FLAIR is read as a T2 and stopped (G33)", "backend", "RC-122"),
    "AB3_copied_study_description_used": ([(QG, '        return None if same else value\n', '        return value\n')],
        "'MS follow-up T1 FLAIR' in the study description stops the true FLAIR (G34)", "backend", "RC-122"),
    "AB4_gate_answers_an_unknown_mask_type": ([(SA, '        if spec.get("type") not in ("segmentation", "instance"):\n            raise HTTPException(status_code=400, detail=f"Unknown mask type: {spec.get(\'type\')}")\n',
        '        if False:\n            raise HTTPException(status_code=400, detail=f"Unknown mask type: {spec.get(\'type\')}")\n')],
        "an invalid request is answered by the gate instead of its own 400 (G35)", "backend", "RC-123"),
    "AB5_visit_check_after_the_gate": ([(SA, '        _visit_check(specs[0], specs[1], sources[0], sources[1]),\n',
        '        asyncio.sleep(0, {"status": "ok"}),\n')],
        "the same mask, the same visit or a reversed order passes the gate instead of its 400 (G35)", "backend", "RC-123"),
    "AB6_instance_read_as_unreadable_header": ([(QG, '{**_NO_HEADER, "no_source": True} if not s else', '{**_NO_HEADER, "unreadable": True} if not s else')],
        "a mask without a source image is reported as an unreadable header (G35)", "backend", "RC-127"),
    "AB9_visits_read_twice": ([(SA, '        visit_check = gate_visit_check or await _visit_check(tp1_spec, tp2_spec, source_tp1, source_tp2)   # review of PR #63; O3\n',
        '        visit_check = await _visit_check(tp1_spec, tp2_spec, source_tp1, source_tp2)   # review of PR #63; O3\n')],
        "the comparison reads each visit's record twice (O3)", "backend", "RC-123"),
    "AB10_rc062_report_drops_the_warnings": ([(RPG, '            if warnings:\n                o["quality_gate_warnings"] = warnings\n',
        '            if False:\n                o["quality_gate_warnings"] = warnings\n')],
        "a warned pair withheld by RC-062 reaches the report model without its warnings (G30 extended)", "backend", "RC-127"),
    "V29_sel_failure_given_the_rc062_note": ([(LC, "                  && selResult.abstained === true && (\n", "                  && (\n")],
        "an SEL failure is presented as RC-062 withholding the pair (G30 extended)", "vitest", "RC-127"),
    # ── eighth review of PR #81: S1 fail closed, G30, G31, G32, U1, E1, E2 ──
    "AA1_rc049_none_without_server_class": ([(HE, "    return { verdict: 'no_server_decision', reasons:", "    return { verdict: 'none', reasons:")],
        "with the gate on and no server class, RC-049 stops rejecting T1/DWI from the header (S1)", "node", "RC-122"),
    "AA2_text_inversion_time_dropped": ([(HE, "  if (ti === undefined) {\n    for (const t of headerText) {", "  if (false) {\n    for (const t of headerText) {")],
        "the inversion time written in the text is lost with the gate on (S1)", "node", "RC-122"),
    "AA3_warnings_given_as_causes": ([(QG, '    causes = unique(c for c, st, _ in pairs if st == "abstain")\n',
        '    causes = unique(c for c, st, _ in pairs if st in ("abstain", "warn"))\n')],
        "a warning (thick slices, an attestation) is stated as the reason a pair was withheld (G30)", "backend", "RC-127"),
    "AA4_report_model_reads_rc062_reason": ([(RPG, '            return {"abstained": True, "abstained_by": "quality_gate", "causes": account["causes"]}\n',
        '            return {"abstained": True, "abstained_by": "rc062"}\n')],
        "the report model says 'acquisition not comparable' when the gate stopped the pair (G30)", "backend", "RC-127"),
    "AA5_comparison_released_before_rc062": ([(QG, "                            actor=actor_for(user, request) if user is not None else None, releases_output=False)\n",
        "                            actor=actor_for(user, request) if user is not None else None, releases_output=True)\n")],
        "a pair RC-062 then withholds is recorded as an AI run (G31)", "backend", "RC-126"),
    "AA6_audit_details_dropped": ([(REG, '            "details": _plain_details(details),\n', '            "details": None,\n')],
        "the audit keeps only a packed code cut at 64 characters (G31)", "backend", "RC-126"),
    "AA7_rc062_not_predicted": ([(QG, '    if mode == "comparison" and (rc062_withholds is not False\n', '    if mode == "comparison" and (False\n')],
        "an attestation is offered for a pair RC-062 will withhold anyway (G32)", "backend", "RC-122"),
    "AA8_404_without_the_gate_code": ([(CT, '                            headers={"X-Quality-Gate-Code": "gate_not_enabled",\n',
        '                            headers={"X-Unused": "gate_not_enabled",\n')],
        "the browser cannot tell 'gate not enabled' from 'not found or no access' (U1)", "backend", "RC-126, RC-127"),
    "AA9_prefix_decompressed_twice": ([(QG, '    raw = decoded if decoded is not None else _nifti_prefix(data)\n', '    raw = _nifti_prefix(data)\n')],
        "each header round is decompressed twice (E1)", "backend", "RC-122"),
    "AA10_records_read_on_the_loop": ([(SA, '        acq, desc = await asyncio.to_thread(qg.stored_records, source)\n',
        '        acq, desc = qg.stored_records(source)\n')],
        "the two visits' stored records are read one after the other, on the event loop (E2)", "backend", "RC-123"),
    "V27_contrast_gate_ignores_no_server_decision": ([(CG, "  if (header.verdict === 'no_server_decision') {\n", "  if (false) {\n")],
        "the worker runs the AI without a decision of the gate's server (S1)", "vitest", "RC-122"),
    "V28_alignment_claimed_for_a_gate_stop": ([(LRP, "      {!gateStopped && <div className=\"flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400\">\n",
        "      {true && <div className=\"flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400\">\n")],
        "the panel says 'index-aligned' for a pair the gate stopped before loading (G30)", "vitest", "RC-127"),
    # ── seventh review of PR #81: S1, G28, G29, R1, R2, E1, E2 ──
    "Z1_derived_image_type_original": ([(POL, '      "image_type_other": ["secondary", "mpr",', '      "image_type_other": ["mpr",')],
        "a secondary capture (ImageType DERIVED\\SECONDARY) passes as an original FLAIR (S1)", "backend", "RC-122"),
    "Z2_futile_attestation_offered": ([(QG, '    return [c["visit"] for c in liftable] if abstaining and len(liftable) == len(abstaining) else []\n',
        '    return [c["visit"] for c in liftable]\n')],
        "an attestation is offered (and audited) when an unreadable header or a scanner change stops the AI anyway (G28)", "backend", "RC-122, RC-126"),
    "Z3_report_reads_any_code": ([(QG, '        pairs = [(c, statuses[c], None) for c in codes if isinstance(c, str) and c in statuses]\n',
        '        pairs = [(c, statuses.get(c), None) for c in codes]\n')],
        "a malformed quality_gate in a report body breaks the draft (R1)", "backend", "RC-127"),
    "Z4_no_record_thickness_fallback": ([(QG, '    if not isinstance(thickness, dict) or thickness.get("state") == "not_determinable":\n',
        '    if not isinstance(thickness, dict):\n')],
        "an undeterminable header thickness hides the record's thickness (R2)", "backend", "RC-124"),
    "Z5_instances_streamed": ([(LCS, '        for doc in query.limit(1).stream():\n', '        for doc in instances.stream():\n')],
        "every consultation streams the whole instances collection to build the cache key (E1)", "backend", "RC-126"),
    "Z6_visits_read_one_after_the_other": ([(SA, '    sources = [getattr(m, "file_id", None) for m in await asyncio.gather(*(_meta(s) for s in specs))]\n',
        '    sources = [getattr(await _meta(s), "file_id", None) for s in specs]\n')],
        "the comparison reads the two visits one after the other (E2)", "backend", "RC-123"),
    "V24_unavailable_retried": ([(TS, "  if (!r || r.ai_may_run || r.codes.length !== 1 || r.codes[0] !== 'gate_rate_limited') return null;\n",
        "  if (!r || r.ai_may_run || r.codes.length !== 1) return null;\n")],
        "an unavailable or not-enabled answer is asked again forever (G29)", "vitest", "RC-126"),
    "V25_no_retry_cap": ([(HOOK, "        wait: a.base !== null && s.attempt < MAX_AUTOMATIC_RETRIES ? a.base * 2 ** s.attempt : null,\n",
        "        wait: a.base !== null ? a.base * 2 ** s.attempt : null,\n")],
        "a rate limit that never lifts makes the browser ask forever (G29)", "vitest", "RC-126"),
    "V26_404_shown_as_unavailable": ([(API, "    if (response?.status === 404 && code === 'gate_not_enabled') return { ...gateNotEnabled(), subject: { file_id: fileId, version: null } };\n", "")],
        "the flag mismatch (server gate off) is shown as 'not found or no access' (G29, U1)", "vitest", "RC-127"),
    # ── React components (vitest only) ──
    "V1_card_shows_output_without_the_final_check": ([(CARD, "      {flames.status === 'done' && flames.result && gateAllowsOutput && (\n",
        "      {flames.status === 'done' && flames.result && (\n")],
        "the card shows the AI result whatever the final gate says", "vitest", "RC-127"),
    "V2_card_runs_despite_an_abstention": ([(CARD, "    if (!sequenceConfirmed || !gateAllowsRun) return;\n", "    if (!sequenceConfirmed) return;\n"),
        (CARD, "            disabled={!flairFileId || !sequenceConfirmed || !gateAllowsRun || busy}\n", "            disabled={!flairFileId || !sequenceConfirmed || busy}\n")],
        "the run button ignores the gate's abstention", "vitest", "RC-122"),
    "V3_panel_hides_the_reasons": ([(PANEL, "  const notOk = (result.checks ?? []).filter((c) => c.status !== 'pass' && c.code);\n",
        "  const notOk: GateCheck[] = [];\n")],
        "the panel shows the decision but not why", "vitest", "RC-127"),
    "V7_rc062_box_for_a_gate_stop": ([(LRP, "      {abstained ? (gateStopped ? null : abstentionBox()) : (\n", "      {abstained ? abstentionBox() : (\n")],
        "the physician reads 'change of scanner or protocol' when the gate stopped the comparison", "vitest", "RC-127"),
    "V8_stale_preflight_applies": ([(HOOK, "      if (a.seq !== null && a.seq !== s.seq) return s;          // the answer to an older request never acts\n", "")],
        "the answer for file A is shown once B is selected", "vitest", "RC-122"),
    "V9_stale_run_starts": ([(CARD, "      if (currentFile.current !== fileAtClick || fresh.subject?.file_id !== fileAtClick) return;   // stale: never runs\n", "")],
        "a run of A starts while B is selected", "vitest", "RC-122"),
    "V10_final_consultation_without_the_skull": ([(CARD, "      return requestQualityGate(run.fileId, attestedAtRun.current, skullFromProvenance(run.provenance)).then((r) => {\n",
        "      return requestQualityGate(run.fileId, attestedAtRun.current).then((r) => {\n")],
        "the server never sees the skull outcome that releases the output", "vitest", "RC-126"),
    "V11_gate_panel_next_to_rc062": ([(LRP, "      {result.quality_gate && !rc062Governs && <QualityGatePanel", "      {result.quality_gate && <QualityGatePanel")],
        "'the gate allows' shown next to 'no automatic candidates'", "vitest", "RC-127"),
}

HARNESS = r"""
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { headerContrastEvidence } from './headerEvidence.ts';
// Sixth review of PR #81 (G27): the browser holds no rule; this harness checks the two things the browser still
// decides about RC-049 — with the gate OFF the base path answers as the base (G26 a), with it ON the server's class.
const failures = [];
const fail = (name, ok) => { if (!ok) failures.push(name); };
const OFF = JSON.parse(readFileSync(process.env.QG_FLAGS_OFF, 'utf-8'));
const dig = (r) => createHash('sha256').update(JSON.stringify(r), 'utf8').digest('hex').slice(0, 16);
fail('g26_rc049_flag_off_is_the_base', OFF.corpus.every((c, i) => {
  const e = headerContrastEvidence([c.text], { ...(c.inversion_time_ms ? { inversionTimeMs: c.inversion_time_ms } : {}),
    ...(c.sequence_name ? { sequenceName: c.sequence_name } : {}) }, null);
  return e.verdict === OFF.rc049[i][0] && dig(e.reasons) === OFF.rc049[i][1];
}));
const on = (text, cls) => headerContrastEvidence([text], {}, null, { qualityGate: true, serverSequenceClass: cls });
fail('g27_rc049_takes_the_server_class', on('Sag T1 MPRAGE', 'FLAIR').verdict === 'supports'
  && on('AX T2 FLAIR', 'T1').verdict === 'contradicts' && on('AX T2 FLAIR', 'other').verdict === 'contradicts'
  && on('AX T2 FLAIR', 'unknown').verdict === 'none');
// eighth review (S1): with the gate on and no server class, fail closed; the written TI stays evidence
fail('s1_no_server_class_refuses', ['Sag T1 MPRAGE', 'AX DWI', 'AX T2 FLAIR'].every((t) =>
  headerContrastEvidence([t], {}, null, { qualityGate: true }).verdict === 'no_server_decision'));
fail('s1_text_inversion_time_kept', on('TI=2500', 'unknown').inversionTimeMs === 2500
  && headerContrastEvidence(['TI=2500'], {}, null, { qualityGate: true }).inversionTimeMs === 2500);
console.log(JSON.stringify({ failures, checks: 4 }));
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
    he = open(os.path.join(copy, HE), encoding="utf-8").read()
    flag = "import { FEATURES } from '@/config/features';"
    assert he.count(flag) == 1, "the flag import of headerEvidence.ts changed"
    assert "@/services/qualityGate" not in he, "headerEvidence.ts imports the gate again (G27)"
    he = he.replace(flag, "const FEATURES = { QUALITY_GATE: false };   // the flag OFF, as in production today (G26)")
    with open(os.path.join(work, "headerEvidence.ts"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(he)
    with open(os.path.join(work, "package.json"), "w", encoding="utf-8") as fh:
        fh.write('{"type": "module"}\n')
    with open(os.path.join(work, "harness.mjs"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HARNESS)
    return work


def node_env(copy, env):
    return {**env, "NODE_NO_WARNINGS": "1",
            "QG_FLAGS_OFF": os.path.join(copy, "frontend/src/config/qualityGate.flags_off_snapshot.v1.json")}


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
        p = subprocess.run(["node", "--input-type=module", "-e", "await import('./node_harness/headerEvidence.ts')"],
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
            "bound_tests": {"backend": BACKEND_TESTS, "node": "RC-049 harness under Node: G26 a (flag off = the base) and "
                                                             "G27 (flag on = the server's class)",
                            "vitest": VITEST_TESTS},
            "source_sha256": {f: _sha(b) for f, b in raw.items()},
            "environment": "offline: GOOGLE_APPLICATION_CREDENTIALS -> missing file, CLOUDSDK_CONFIG -> empty folder, "
                           "GOOGLE_CLOUD_PROJECT=mstool-offline-tests, ANTHROPIC_API_KEY removed",
        }
        res["retired"] = RETIRED
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
