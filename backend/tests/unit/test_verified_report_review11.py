"""Eleventh independent review of PR #78 — the final fix round (Class C; REQ-REG-011, REQ-SAFE-048/049/050/051; RC-064,
RC-065, RC-066, RC-102 to RC-106). DRAFT, PENDING owner approval.

Written failing first on 86aedaa (before any correction).

L1  both notices (the report panel's and the report viewer's) state exactly what the record sends — checked against the
    record's own blocks (backend/tests/fixtures/report_sent_fields.json), so the labelling cannot drift again.
L2  a comparison with a missing resolved / shrunk / stable count writes every computed count and names the missing one
    "not computed"; I4 extended: every computed count of the input appears in the draft (partial status_counts too).
C1  an identifier-pattern hit in the first message (device-written text only, e.g. 9.1175 read as a birth date) gives the
    measurements-only draft with the privacy reason, never a 503.
C2/C7 (I17) `attempts` count only requests actually sent; a retry skipped for the time budget is recorded apart
    (retry_skipped_budget); without any request sent there is no model and no token count.
C3  (I18) once an answer was received and failed the check, ANY failure of the regeneration (provider error, 5xx,
    connection error, timeout, unavailable model, refusal) is failed_check / withheld.
C4  the device-word list is built at startup (lifespan), not in the first request's budget; the test matrix's
    dimensions live in the tests, not in the Class C module.
M1  the panel names exactly the measurements that can be refused as implausible.
M2  no unused provider_payload import in the service, no unused PASSED.
"""
import inspect
import itertools
import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import brain_report_service as BRS
from app.services import report_payload_guard as G
from app.services import verified_report as VR
from app.services.report_payload_guard import PatientIdentifiers
from tests.unit.test_verified_report_scenario_matrix import GOOD, IDS, _Client, _run, _service, sink  # noqa: F401

ROOT = Path(__file__).resolve().parents[3]
SENT = json.loads((ROOT / "backend/tests/fixtures/report_sent_fields.json").read_text(encoding="utf-8"))
ERRORS = json.loads((ROOT / "backend/tests/fixtures/report_error_codes.json").read_text(encoding="utf-8"))
FAILING = GOOD.replace("The marking is automatic.", "There are seven lesions.")   # fails FMT.number_words


def _locale(lang):
    return json.loads((ROOT / f"frontend/src/i18n/locales/{lang}.json").read_text(encoding="utf-8"))


def _at(obj, key):
    for k in key.split("."):
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


# ══════════════════════════════════════════════════════════════════════════════════════════════ L1
def test_reg011_l1_the_record_sends_exactly_the_blocks_the_notices_describe():
    seen = set()
    for f, v, s in VR.synthetic_payloads():
        seen |= set(json.loads(VR.record_json(VR.build_view(f, v, "en", review_source=s))))
    assert seen == set(SENT["blocks"]), f"record blocks {sorted(seen)} vs notice categories {sorted(SENT['blocks'])}"
    # what is never sent: the typed text, sex, age or an age band, whatever the request carries
    findings = {"lesion_analysis": {"total_count": 7}, "patient_sex": "F", "patient_age": 47,
                "clinical_indication": "ZZTYPED-INDICATION", "technique": "ZZTYPED-TECHNIQUE",
                "additional_observations": "ZZTYPED-OBSERVATION"}
    f, v, ni = VR.rendered_request(findings, None)
    p = G.project_measurements(f, v)
    record = VR.record_json(VR.build_view(p.findings, p.volumetry, "en", not_included=ni))
    assert "ZZTYPED" not in record
    assert not any(k in json.loads(record) for k in SENT["never_sent_fields"])
    assert not re.search(r"age_band|patient_age|patient_sex|\"sex\"", record)


@pytest.mark.parametrize("lang", ["en", "es", "de"])
@pytest.mark.parametrize("key", SENT["notice_keys"])
def test_reg011_l1_each_notice_names_every_sent_category_and_nothing_that_is_not_sent(lang, key):
    text = _at(_locale(lang), key)
    assert isinstance(text, str) and text, key
    missing = [p for cat in set(SENT["blocks"].values()) - {"meta"} for p in SENT["phrases"][lang][cat] if p not in text]
    assert not missing, f"{lang} {key} does not name: {missing}"
    claimed = [w for w in SENT["never_sent_words"][lang] if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text, re.I)]
    assert not claimed, f"{lang} {key} names what is never sent: {claimed}"


# ══════════════════════════════════════════════════════════════════════════════════════════════ L2 / I4
OTHER = ("resolved", "shrunk", "stable")
WORDS = {"en": ("resolved", "shrunk", "stable"), "es": ("resueltos", "reducidos", "estables"),
         "de": ("zurückgebildet", "verkleinert", "stabil")}
BASE_LNG = {"burden_tp1_ml": 1.0, "burden_tp2_ml": 1.4, "total_lesions_tp1": 3, "total_lesions_tp2": 9,
            "burden_delta_percent": 40.0, "abstained": False, "new_lesion_min_diameter_mm": 3,
            "change_candidates": {"new": 2, "enlarging": 1, "total": 3}}
COUNTS = {"new": 5, "enlarged": 1, "resolved": 4, "shrunk": 6, "stable": 8}   # distinct, so each is identifiable
PARTIAL = [frozenset(c) for r in range(0, 4) for c in itertools.combinations(OTHER, r)]   # the missing ones


@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc102_l2_a_partial_comparison_writes_every_computed_count(lang):
    bad = []
    for missing in PARTIAL:
        sc = {k: v for k, v in COUNTS.items() if k not in missing}
        view = VR.build_view({"longitudinal": {**BASE_LNG, "status_counts": sc}}, None, lang)
        draft = VR.assemble(view, lang, "", "")
        for key, word in zip(OTHER, WORDS[lang]):
            if key in missing:
                if not re.search(rf"{word}\W{{1,3}}{re.escape(VR.T[lang]['nc'])}", draft):
                    bad.append((sorted(missing), f"{key} not named 'not computed'"))
            elif not re.search(rf"(?<![\d.,]){COUNTS[key]} {word}", draft):
                bad.append((sorted(missing), f"computed {key}={COUNTS[key]} dropped"))
    assert not bad, f"L2 ({lang}): {bad[:6]}"


def test_rc102_i4_every_computed_count_of_the_input_appears_in_the_draft():
    """I4 extended over the matrix's lesion, DIS and volumetry dimensions x every subset of missing resolved / shrunk /
    stable counts: the reviewable candidates, the counts below the review size and every computed status count are in
    the draft — none vanishes silently."""
    lesions = [None, {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
                      "size_distribution": {"small": 4, "medium": 2, "large": 1}}]
    dis = [None, {"evaluation_status": "not_evaluated"}]
    vols = [None, {"total_brain_volume_ml": 1100.0, "intracranial_volume_ml": 1450.0}]
    bad = []
    for la, d, vol, missing in itertools.product(lesions, dis, vols, PARTIAL):
        sc = {k: v for k, v in COUNTS.items() if k not in missing}
        findings = {"longitudinal": {**BASE_LNG, "status_counts": sc}}
        if la:
            findings["lesion_analysis"] = la
        if d:
            findings["dis_assessment"] = d
        r = _run(_service().generate_report(template_type="general", findings=findings, volumetry=vol, language="en",
                                            identifiers=IDS))
        text = r["content"]
        expected = [f"{BASE_LNG['change_candidates']['new']} new", f"{BASE_LNG['change_candidates']['enlarging']} enlarging",
                    f"{COUNTS['new'] - BASE_LNG['change_candidates']['new']} new lesion(s)"]
        expected += [f"{COUNTS[k]} {k}" for k in OTHER if k not in missing]
        if la:
            expected += ["Lesions marked: 7", "4 small", "2 medium", "1 large"]
        lost = [e for e in expected if e not in text]
        if lost:
            bad.append(((bool(la), bool(d), bool(vol), sorted(missing)), lost))
    assert not bad, f"I4: {len(bad)} cases lose a computed count; first: {bad[:3]}"


# ══════════════════════════════════════════════════════════════════════════════════════════════ C1
IDS_1975 = PatientIdentifiers.from_record({"mrn": "MRN-TEST-0578", "given_name": "Testgiven",
                                           "family_name": "Testfamily", "birth_date": date(1975, 11, 9)})


def test_rc065_c1_an_identifier_pattern_in_device_text_gives_a_measurements_only_draft():
    """The reviewer's example: a total lesion volume of 9.1175 mL is read by the tripwire as the birth date 9.11.75.
    The first message holds only device-written text, so nothing is sent and the measurements are delivered."""
    client = _Client()
    findings = {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 9117.5, "total_burden_ml": 9.1175},
                "dis_assessment": {"evaluation_status": "not_evaluated"}}
    result = _run(_service(client, enabled=True).generate_report(
        template_type="general", findings=findings, volumetry=None, language="en", identifiers=IDS_1975))
    v = result["verification"]
    assert client.calls == [] and v["reason"] == VR.REASON_PRIVACY and v["interpretive_text"] == "not_requested", v
    assert "Lesions marked: 7" in result["content"]


# ══════════════════════════════════════════════════════════════════════════════════════════════ C2 / C7 (I17)
def _timed_client(clock, seconds, replies):
    client = _Client()

    def create(**kw):
        client.calls.append(kw)
        clock.t += seconds
        r = replies[min(len(client.calls), len(replies)) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    client.create = create
    return client


def _reply(text=FAILING, stop="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                           model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=2, output_tokens=2))


LESION_CASE = {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132},
               "dis_assessment": {"evaluation_status": "not_evaluated"}}


def test_rc104_c2_a_retry_skipped_for_the_budget_is_not_an_attempt(sink, monkeypatch):
    clock = SimpleNamespace(t=1000.0)
    monkeypatch.setattr(VR, "now", lambda: clock.t)
    client = _timed_client(clock, 21.0, [_reply()])
    result = _run(_service(client, enabled=True).generate_report(
        template_type="general", findings=dict(LESION_CASE), volumetry=None, language="en", identifiers=IDS,
        request_started=clock.t, audit_actor=SimpleNamespace(id="reader-c2", username="reader-c2", role="radiologist")))
    v = result["verification"]
    attempts = [x for x in sink.memory_records if x["event_type"] == "clinical.ai_report.attempt"]
    (outcome,) = [x for x in sink.memory_records if x["event_type"] == "clinical.ai_report.verification"]
    assert len(client.calls) == 1 and v["attempts"] == 1 and v.get("retry_skipped_budget") is True, v
    assert len(attempts) == 1 and outcome["details"]["attempts"] == 1, outcome["details"]
    assert outcome["details"].get("retry_skipped_budget") is True


def test_rc104_c7_without_any_request_sent_there_is_no_model_and_no_token_count(monkeypatch):
    async def nothing_sent(view, lang, *a, **k):
        return VR.measurements_only(view, lang, VR.REASON_TIME_BUDGET,
                                    [{"attempt": 1, "verdict": "not_sent", "rule_ids": [], "error": "time_budget"}])

    monkeypatch.setattr(VR, "run_flow", nothing_sent)
    result = _run(_service(_Client(), enabled=True).generate_report(
        template_type="general", findings=dict(LESION_CASE), volumetry=None, language="en", identifiers=IDS))
    assert result["model"] is None and result["tokens_used"] is None, (result["model"], result["tokens_used"])


# ══════════════════════════════════════════════════════════════════════════════════════════════ C3 (I18)
def _exc(name, status=None):
    e = type(name, (Exception,), {})(f"{name} on the regeneration")
    if status is not None:
        e.status_code = status
    return e


RETRY_FAILURES = {
    "provider_error_5xx": _exc("InternalServerError", 500),
    "overloaded_529": _exc("OverloadedError", 529),
    "connection_error": _exc("APIConnectionError"),
    "timeout": _exc("APITimeoutError"),
    "model_unavailable_404": _exc("NotFoundError", 404),
    "refusal": _reply(text="", stop="refusal"),
}


@pytest.mark.parametrize("kind", sorted(RETRY_FAILURES))
def test_rc106_c3_any_failure_of_a_regeneration_after_a_failed_answer_is_a_failed_check(kind):
    client = _timed_client(SimpleNamespace(t=0.0), 0.0, [_reply(), RETRY_FAILURES[kind]])
    result = _run(_service(client, enabled=True).generate_report(
        template_type="general", findings=dict(LESION_CASE), volumetry=None, language="en", identifiers=IDS))
    v = result["verification"]
    assert len(client.calls) == 2 and (v["reason"], v["interpretive_text"]) == (VR.REASON_BLOCKED, "withheld"), v


@pytest.mark.parametrize("kind", ["provider_error_5xx", "connection_error", "timeout"])
def test_rc106_c3_with_no_answer_ever_received_the_reason_stays_could_not_be_obtained(kind):
    client = _timed_client(SimpleNamespace(t=0.0), 0.0, [RETRY_FAILURES[kind]])
    result = _run(_service(client, enabled=True).generate_report(
        template_type="general", findings=dict(LESION_CASE), volumetry=None, language="en", identifiers=IDS))
    assert result["verification"]["reason"] != VR.REASON_BLOCKED and len(client.calls) == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════ C4
def test_rc106_c4_the_device_word_list_is_built_at_startup():
    import app.main as main
    assert "warm_report_word_lists" in inspect.getsource(main.lifespan)
    for cached in (BRS._fixed_prompt_word_lists, BRS.fixed_prompt_words, BRS.fixed_prompt_pairs):
        cached.cache_clear()
    BRS.warm_report_word_lists()
    assert all(c.cache_info().currsize == 1
               for c in (BRS._fixed_prompt_word_lists, BRS.fixed_prompt_words, BRS.fixed_prompt_pairs))


def test_rc106_c4_the_test_matrix_lives_in_the_tests_not_in_the_class_c_module():
    for name in ("SCENARIO", "SCENARIO_BASE", "scenario_request", "scenario_covering_cases"):
        assert not hasattr(VR, name), name
    # (added with the fix) every value of the test matrix is one of the product's own branches, so the device-word
    # list (built from those branches) covers every text the matrix checks
    from tests.unit.report_scenarios import SCENARIO
    branches = getattr(VR, "_BRANCHES", {})
    for dim, values in SCENARIO.items():
        for name, value in values.items():
            if value is not None:
                assert branches.get(dim, {}).get(name) == value, (dim, name)


# ══════════════════════════════════════════════════════════════════════════════════════════════ M1
def _leaves(o, path=()):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _leaves(v, path + (i,))
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        yield path


def _set(o, path, value):
    for k in path[:-1]:
        o = o[k]
    o[path[-1]] = value


FULL_REQUEST = (
    {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
                         "size_distribution": {"small": 4, "medium": 2, "large": 1},
                         "regions": {"Periventricular": {"lesion_count": 3, "total_volume_mm3": 2000.0,
                                                         "total_volume_ml": 2.0}},
                         "lesions": [{"id": 1, "volume_mm3": 1500.0, "volume_ml": 1.5, "centroid": {"z": 1, "y": 2,
                                                                                                    "x": 3}}]},
     "dis_assessment": {"evaluation_status": "evaluated", "dis_met": True, "regions_with_lesions": 2,
                        "total_dis_regions": 5, "region_details": {"Periventricular": {"present": True}},
                        "active_voxels": 10, "black_hole_voxels": 3},
     "longitudinal": {**BASE_LNG, "status_counts": dict(COUNTS)}},
    {"total_brain_volume_ml": 1100.0, "intracranial_volume_ml": 1450.0,
     "structures": [{"structure_name": "Hippocampus", "volume_ml": 4.0, "normative_percentile": 40}]})


def _implausible_fields():
    fields = set()
    for which in (0, 1):
        for path in list(_leaves(FULL_REQUEST[which])):
            for bad in (-5.0, 1e15):
                req = json.loads(json.dumps(FULL_REQUEST))
                _set(req[which], path, bad)
                f, v, _ni = VR.rendered_request(req[0], req[1])
                try:
                    G.project_measurements(f, v)
                except G.ImplausibleMeasurement as e:
                    fields.add(e.field)
    return fields


def test_rc103_m1_the_panel_names_exactly_the_measurements_that_can_be_implausible():
    reachable = _implausible_fields()
    assert set(ERRORS["fields"]) == reachable, (sorted(set(ERRORS["fields"]) - reachable),
                                                sorted(reachable - set(ERRORS["fields"])))
    panel = (ROOT / "frontend/src/components/AIReportPanel.tsx").read_text(encoding="utf-8")
    block = re.search(r"const MEASUREMENT_NAMES[^=]*=\s*\{(.*?)\};", panel, re.S).group(1)
    assert set(re.findall(r"(\w+):\s*'", block)) == reachable
    for lang in ("en", "es", "de"):
        names = set((_at(_locale(lang), "report.measurementNames") or {})) - {"unknown"}
        assert names == reachable, (lang, sorted(names ^ reachable))


# ══════════════════════════════════════════════════════════════════════════════════════════════ M2
def test_m2_no_unused_names():
    assert not hasattr(BRS, "provider_payload")
    assert not hasattr(VR, "PASSED")
