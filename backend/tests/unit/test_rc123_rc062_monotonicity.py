"""The single quality gate never relaxes RC-062 (fourth review of PR #81; RC-123, RC-062; HAZ-007, HAZ-025).

DRAFT, PENDING owner approval.

G24 — monotone with respect to RC-062, EXHAUSTIVE: every combination of the six acquisition facts RC-062 requires
(manufacturer, model, field strength, slice thickness, 2D/3D, voxel size), each present-equal, present-different,
missing in visit 1, missing in visit 2 or missing in both, times visit order known / unknown (5^6 x 2 = 31 250 pairs).
With the gate ON the comparison is never more permissive than RC-062 alone (gate OFF): where RC-062 abstains, no
candidate, lesion load or reader-confirmed activity is shown. The gate only ADDS abstentions and warnings.

G25 — one comparability verdict per pair: compare_longitudinal and the SEL search decide from ONE shared function and
agree on every pair of the enumeration.

R4 — a comparison the gate lets through WITH warnings says so: the caveat (read by the MCP assistant), the report
payload, the report prompt and the code-written notice of the draft carry the warnings in plain words.
"""
import inspect
import itertools

import pytest

import app.api.routes.segmentation_analysis as sa
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg
from tests.unit.test_rc122_review11 import TEST_USER  # noqa: E402 — M3: the report's clinician

pytestmark = pytest.mark.unit

ON = {"allowed": True, "code": None}
FIELDS = ("manufacturer", "manufacturer_model_name", "magnetic_field_strength_t", "slice_thickness_mm",
          "mr_acquisition_type", "voxel_spacing_mm")
VALUES = {"manufacturer": ("SIEMENS", "GE MEDICAL SYSTEMS"), "manufacturer_model_name": ("Prisma", "Skyra"),
          "magnetic_field_strength_t": (3.0, 1.5), "slice_thickness_mm": (3.0, 5.0), "mr_acquisition_type": ("2D", "3D"),
          "voxel_spacing_mm": ((1.0, 1.0, 1.0), (1.0, 1.0, 3.0))}
STATES = ("equal", "different", "missing_tp1", "missing_tp2", "missing_both")
SEQUENCE = {"repetition_time_ms": 9000.0, "echo_time_ms": 81.0, "inversion_time_ms": 2500.0}
CHANGE = {"status": "new", "clinically_significant": True, "centroid_z": 5, "centroid_y": 8, "centroid_x": 9,
          "volume_tp1_mm3": 0, "volume_tp2_mm3": 27}
BINDING = {"tp1_mask_sha256": "a" * 64, "tp2_mask_sha256": "b" * 64}
REVIEW = {**BINDING, "decisions": {lcs.candidate_key(CHANGE): {"decision": "confirmed", "reviewed_by": "dr",
                                                                 "reviewed_at": "2026-11-12T10:00:00"}}}
RESULT = {"changes": [CHANGE], "status_counts": {"new": 1, "resolved": 0, "enlarged": 0, "shrunk": 0, "stable": 0},
          "burden_tp1_mm3": 27.0, "burden_tp2_mm3": 54.0, "burden_tp1_ml": 0.027, "burden_tp2_ml": 0.054,
          "burden_delta_mm3": 27.0, "burden_delta_percent": 100.0, "total_lesions_tp1": 1, "total_lesions_tp2": 2}
SHOWN = ("change_candidates", "status_counts", "burden_tp1_mm3", "burden_tp2_mm3", "burden_delta_mm3",
         "total_lesions_tp1", "total_lesions_tp2", "reader_confirmed_activity", "review_binding")


def _pair(states):
    acq = [dict(SEQUENCE), dict(SEQUENCE)]
    spacing = [None, None]
    for field, state in zip(FIELDS, states):
        a, b = VALUES[field]
        v1, v2 = {"equal": (a, a), "different": (a, b), "missing_tp1": (None, a), "missing_tp2": (a, None),
                  "missing_both": (None, None)}[state]
        if field == "voxel_spacing_mm":
            spacing = [v1, v2]
        else:
            acq[0][field], acq[1][field] = v1, v2
    return acq, spacing


def _visit(acq):
    return {"sequence": "FLAIR", "physician_confirmed_flair": False, "skull": "unknown",
            "thickness": qg.thickness_from_acquisition_record(acq), "scanner": qg.scanner_from_acquisition_record(acq)}


def _cases():
    for states in itertools.product(STATES, repeat=len(FIELDS)):
        for order in ("ok", "unknown"):
            acq, spacing = _pair(states)
            check = lcs.compare_acquisitions(acq[0], acq[1], spacing[0], spacing[1])
            visit = {"status": order}
            gate = qg.evaluate({"mode": "comparison", "visits": [_visit(acq[0]), _visit(acq[1])], "platform": ON})
            yield states, order, check, visit, gate


def _on(check, visit, gate):
    return qg.present_gated_comparison(dict(RESULT), acquisition_check=check, evidence=None, binding=BINDING, stored_review=REVIEW,
                   visit_check=visit, gate=gate)


def test_rc123_g24_the_gate_never_relaxes_rc062_exhaustive():
    bad, n = [], 0
    for states, order, check, visit, gate in _cases():
        n += 1
        off = lcs.present_comparison(dict(RESULT), acquisition_check=check, evidence=None, binding=BINDING,
                                     stored_review=REVIEW, visit_check=visit)
        on = _on(check, visit, gate)
        if off.get("abstained") and (not on.get("abstained") or any(on.get(k) is not None for k in SHOWN)):
            bad.append((states, order))
        if on.get("abstained") is False and off.get("abstained") is not False:
            bad.append((states, order))
    assert n == 5 ** 6 * 2
    bad = sorted(set(bad))
    assert not bad, f"G24: the gate relaxed RC-062 in {len(bad)} of {n} pairs; first: {bad[:4]}"


def _sel_verdict(check, visit, gate):
    """The SEL search's two steps: the gate's early abstention, then RC-062's one predicate."""
    return gate.get("ai_output_allowed") is not True or lcs.rc062_withholds(check, visit)


def test_rc123_g25_compare_and_sel_give_one_comparability_verdict():
    bad = [(s, o) for s, o, check, visit, gate in _cases()
           if bool(_on(check, visit, gate).get("abstained")) != bool(_sel_verdict(check, visit, gate))]
    assert not bad, f"G25: compare and SEL disagree on {len(bad)} pairs; first: {bad[:4]}"
    sel = inspect.getsource(sa.detect_slowly_expanding_lesions)
    compare = inspect.getsource(sa.compare_longitudinal)
    assert "lcs.rc062_withholds(" in sel and "present_gated_comparison(" in compare, "one shared predicate"
    assert "rc062_withholds(" in inspect.getsource(lcs.present_comparison), "present_comparison uses the predicate"
    assert "lcs.present_comparison(" not in compare and 'acquisition_check["status"] != "same"' not in sel
    assert sel.index("_gate_setup(") < sel.index("lcs.rc062_withholds("), "the gate decides first"
    assert not hasattr(qg, "comparison_withheld"), "one predicate, no second copy (fifth review, cleanup)"


def test_rc123_g24_rc062_is_the_base_rule_whether_the_gate_is_on_or_off():
    """present_comparison has no gate-dependent parameter: it behaves as on the base branch."""
    params = set(inspect.signature(lcs.present_comparison).parameters)
    assert params == {"result", "acquisition_check", "evidence", "binding", "stored_review", "visit_check",
                      "review_read_failed"}
    assert not hasattr(lcs, "unrecorded_in_both")
    assert "unrecorded_in_both" not in (qg.POLICY_PATH.read_text(encoding="utf-8"))


WARNED = qg.evaluate({"mode": "comparison", "platform": ON, "visits": [
    _visit({**SEQUENCE, "manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0,
            "slice_thickness_mm": 5.0, "mr_acquisition_type": "2D"}),
    _visit({**SEQUENCE, "manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0,
            "slice_thickness_mm": 5.0, "mr_acquisition_type": "2D"})]})


def test_rc123_r4_a_warned_comparison_says_so_in_the_caveat():
    assert WARNED["decision"] == "proceed_with_warnings" and WARNED["codes"] == ["thickness_at_least"]
    out = qg.apply_to_comparison({**RESULT, "abstained": False, "caveat": "Unconfirmed candidates."}, WARNED)
    assert out["caveat"].startswith("Unconfirmed candidates.")
    assert qg.CAVEAT_REASONS["thickness_at_least"] in out["caveat"]


def test_rc123_r4_the_report_draft_states_the_gate_warnings(monkeypatch):
    from tests.unit.test_rc122_review11 import notice_for, paired, projected, served   # I1 / K2; R2: one account
    from app.services.brain_report_service import BrainReportService
    lng = paired(qg.apply_to_comparison(lcs.present_comparison(
        dict(RESULT), acquisition_check={"status": "same", "missing": [], "differing": []}, evidence=None,
        binding=None, stored_review=None, visit_check={"status": "ok"}), served(WARNED, monkeypatch)))
    guarded = projected(lng)
    assert guarded.get("quality_gate_warnings") == ["thickness_at_least"]
    prompt = BrainReportService()._build_findings_prompt({"longitudinal": guarded}, language="en")
    assert qg.CAVEAT_REASONS["thickness_at_least"] in prompt
    for lang, word in (("en", "Quality"), ("es", "calidad"), ("de", "Qualität")):
        notice = notice_for(lng, lang, TEST_USER)
        assert notice and word in notice, (lang, notice)


def test_rc123_g25_the_gate_alone_withholds_in_compare_and_sel():
    """A pair RC-062 finds comparable is still withheld, by compare AND by SEL, when the gate stops it (another sequence,
    the platform switched off) — the shared verdict carries the gate's abstention."""
    record = {**SEQUENCE, "manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0,
              "slice_thickness_mm": 3.0, "mr_acquisition_type": "2D"}
    check = lcs.compare_acquisitions(record, record, (1.0, 1.0, 3.0), (1.0, 1.0, 3.0))
    assert check["status"] == "same"
    visit = {"status": "ok"}
    stops = [qg.evaluate({"mode": "comparison", "platform": ON, "visits": [_visit(record), {**_visit(record), "sequence": "T1"}]}),
             qg.evaluate({"mode": "comparison", "platform": {"allowed": False, "code": "agent_switched_off"},
                          "visits": [_visit(record), _visit(record)]})]
    for gate in stops:
        assert gate["ai_output_allowed"] is False
        assert qg.present_gated_comparison(dict(RESULT), acquisition_check=check, evidence=None, binding=BINDING,
                                           stored_review=REVIEW, visit_check=visit, gate=gate)["abstained"] is True
        assert lcs.rc062_withholds(check, visit) is False and _sel_verdict(check, visit, gate) is True
