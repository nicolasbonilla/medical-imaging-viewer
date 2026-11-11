"""
Sixth independent review of PR #78 (W1-W7, on e88bef57) — failing-first tests (REQ-FUNC-116, REQ-SAFE-048/049/051;
RC-102 to RC-106, CAPA-013; DRAFT, PENDING owner approval).

W1 the change notice is the service's, from the validated record; a null or missing count is "not computed", never 0.
W2 the limitations mention the clinical indication only when the clinical indication itself was typed.
W3 a number word fails only when it counts a clinical noun (lesions, foci, candidates, regions…); ordinals and
   non-count uses pass.
W4 the record is projected and built once per report.
W5 one gate decides whether the AI comments can be requested — the route and the service can never disagree.
W6 the provider client is cached per running event loop.
W7 the time budget counts from the start of the request; too little left: measurements only, audited.
"""
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import brain_report_service as BRS
from app.services import verified_report as VR
from tests.unit.test_capa014_report_provider_payload import _post, route  # noqa: F401  (fixture)
from tests.unit.test_verified_report_review5 import (IDS, LESIONS, LONG, _Client, _answer, _generate, _rules,  # noqa: F401
                                                     _service, _view, sink)


# ═══════════════════════════════════════════════════════════════════════ W1 — the change notice: one source
NOT_COMPUTED = [
    {**LONG, "change_candidates": {"new": None, "enlarging": 3, "total": 3}},
    {**LONG, "change_candidates": {"enlarging": 3, "total": 3}},
    {k: v for k, v in {**LONG, "status_counts": {"enlarged": 2, "resolved": 0, "shrunk": 0, "stable": 3}}.items()
     if k != "change_candidates"},
]


@pytest.mark.parametrize("lng", NOT_COMPUTED, ids=["new-null", "new-missing", "status-new-missing"])
def test_rc102_w1_a_null_or_missing_count_is_not_computed_in_the_body_and_the_notice(route, lng):
    body = _post(route, {"longitudinal": lng}).json()
    assert body["change_notice"] == VR.CHANGE_NOTICE["en"]["not_computed"]
    content = body["content"]
    assert VR.T["en"]["lng_nc"] in content and VR.CHANGE_NOTICE["en"]["not_computed"] in content
    assert "(0 new" not in content and "unconfirmed change candidate(s)" not in content


def test_rc102_w1_the_body_and_the_notice_state_the_same_numbers(route):
    body = _post(route, {"longitudinal": LONG}).json()
    assert "2 new and 1 enlarging" in body["content"] and "(2 new, 1 enlarging)" in body["change_notice"]
    assert body["content"].count("(2 new, 1 enlarging)") == 1


def test_rc102_w1_the_route_no_longer_computes_the_notice():
    import app.api.routes.ai_report as R
    text = inspect.getsource(R)
    assert "def longitudinal_notice" not in text and 'request.findings.get("longitudinal")' not in text


# ═══════════════════════════════════════════════════════════════════════ W2 — per-field presence flags
def _limitations(findings, lang="en"):
    return VR.assemble(_view(findings, lang=lang), lang, "", "")


@pytest.mark.parametrize("field", ["technique", "additional_observations"])
def test_rc102_w2_technique_or_observations_only_keep_the_indication_not_available(field):
    report = _limitations({"lesion_analysis": LESIONS, field: "3T scanner, typed by the clinician"})
    t = VR.T["en"]
    assert t["lim_indication_entry"] not in report
    not_available = next(line for line in report.split("\n") if line.startswith(t["lim"].split("{")[0]))
    assert t["lim_items"].split("|")[0] in not_available


def test_rc102_w2_a_typed_clinical_indication_is_named_as_the_clinicians_entry():
    report = _limitations({"lesion_analysis": LESIONS, "clinical_indication": "follow-up, typed"})
    t = VR.T["en"]
    assert t["lim_indication_entry"] in report
    not_available = next(line for line in report.split("\n") if line.startswith(t["lim"].split("{")[0]))
    assert t["lim_items"].split("|")[0] not in not_available


# ═══════════════════════════════════════════════════════════════════════ W3 — counts only
COUNTS = ["Two lesions are marked.", "A single new lesion is marked.", "Lesions lie in three of the four regions.",
          "There are twenty-one small lesions.", "Both regions show lesions.", "Zero lesions are enlarging.",
          "Ambas regiones tienen lesiones.", "Se marcaron doce lesiones.", "Hay una única lesión nueva.",
          "Zwei neue Kandidaten wurden markiert.", "Es gibt einundzwanzig kleine Läsionen.", "Beide Regionen zeigen Herde.",
          # counts found slipping a noun-only rule in the offline re-scoring of the benchmark's delivered drafts
          "The lesions are categorized as one large, twenty medium, and eighteen small.",
          "The total count of lesions is twenty-five.", "A single medium-sized lesion was identified.", "The count lies in the range of twenty to fifty.",
          "There is a total volume of zero.", "Slices are at least seven point two millimeters thick.",
          "La distribución muestra una lesión grande, diez medianas y siete pequeñas.",
          "El recuento total de lesiones es de cero.",
          "Die Größenverteilung umfasst vier kleine, vierzehn mittlere und eine große Läsion."]
NOT_COUNTS = ["Lesions are seen in both hemispheres.", "This is the first automatic marking.",
              "The second visit is compared with the first.", "Once confirmed, the marking can be used.",
              "Half of the marked volume is periventricular.", "The marking was checked twice.",
              "A couple of notes: the marking is automatic.", "Las lesiones afectan a ambos hemisferios.",
              "Es la primera marcación automática.", "La mitad del volumen es periventricular.",
              "Una única secuencia FLAIR fue analizada.", "Beide Hemisphären sind betroffen.",
              "Die einzige Sequenz ist FLAIR.", "Dies ist die erste automatische Markierung.",
              "The lesions are distributed across three size categories.", "Both small and large lesions are marked.",
              "Most lesions are small, and the total volume is given above."]


@pytest.mark.parametrize("sentence", COUNTS)
def test_rc103_w3_a_count_in_words_fails(sentence):
    assert "FMT.number_words" in _rules(_view({"lesion_analysis": LESIONS}), _answer(sentence))


@pytest.mark.parametrize("sentence", NOT_COUNTS)
def test_rc103_w3_ordinals_and_non_count_uses_pass(sentence):
    assert "FMT.number_words" not in _rules(_view({"lesion_analysis": LESIONS}), _answer(sentence))


# ═══════════════════════════════════════════════════════════════════════ W4 — decide once, build once
def test_rc102_w4_the_record_is_projected_and_built_once(monkeypatch):
    counts = {"payload": 0, "view": 0}
    real_payload, real_view = BRS.provider_payload, VR.build_view

    def payload(*a, **k):
        counts["payload"] += 1
        return real_payload(*a, **k)

    def view(*a, **k):
        counts["view"] += 1
        return real_view(*a, **k)

    monkeypatch.setattr(BRS, "provider_payload", payload)
    monkeypatch.setattr(VR, "build_view", view)
    client = _Client()
    result = _generate(_service(client), {"lesion_analysis": LESIONS})
    assert len(client.calls) == 1 and result["verification"]["interpretive_text"] == "delivered"
    assert counts == {"payload": 1, "view": 1}


# ═══════════════════════════════════════════════════════════════════════ W5 — one gate
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "not-an-allowed-model"])
@pytest.mark.parametrize("key", ["test-not-a-key", ""])
def test_rc105_w5_the_route_and_the_service_use_one_gate(enabled, model, key):
    svc = _service(None, enabled=enabled, key=key)
    svc._settings.CLAUDE_MODEL = model
    view = _view({"lesion_analysis": LESIONS})
    route_side, service_side = svc.interpretive_text_gate(), svc.interpretive_text_gate(view)
    assert route_side == service_side
    assert route_side[0] is (enabled and model == "claude-sonnet-5-5" and bool(key))
    assert not hasattr(BRS.BrainReportService, "provider_call_possible")
    assert not hasattr(BRS.BrainReportService, "_interpretive_text_gate")


def test_rc105_w5_the_route_asks_the_one_gate():
    import app.api.routes.ai_report as R
    assert "interpretive_text_gate(" in inspect.getsource(R.generate_report)


# ═══════════════════════════════════════════════════════════════════════ W6 — one client per running loop
def test_rc106_w6_a_second_event_loop_gets_its_own_client(monkeypatch):
    import sys
    module = MagicMock()
    module.AsyncAnthropic.side_effect = lambda **kw: MagicMock(name="client")
    monkeypatch.setitem(sys.modules, "anthropic", module)
    svc = _service(None)

    async def two_lookups():
        return svc._get_client(), svc._get_client()

    first = asyncio.run(two_lookups())
    second = asyncio.run(two_lookups())
    assert first[0] is first[1] and second[0] is second[1]       # one client within a loop
    assert first[0] is not second[0]                             # never a client of a closed loop
    assert module.AsyncAnthropic.call_count == 2


# ═══════════════════════════════════════════════════════════════════════ W7 — the budget counts from the request start
def test_rc106_w7_a_slow_lesion_table_leaves_no_time_for_the_model(route, monkeypatch):
    import app.api.routes.ai_report as R
    clock = SimpleNamespace(t=1000.0)
    monkeypatch.setattr(VR, "now", lambda: clock.t)
    original = R.server_lesion_table

    async def slow(segmentation_id):
        clock.t += 26.0
        return await original(segmentation_id)

    monkeypatch.setattr(R, "server_lesion_table", slow)
    r = _post(route, {"lesion_analysis": LESIONS})
    assert r.status_code == 200, r.text
    assert r.json()["verification"]["reason"] == VR.REASON_TIME_BUDGET and route.provider.calls == []


def test_rc106_w7_the_model_gets_what_is_left_of_the_request_budget(route, monkeypatch):
    import app.api.routes.ai_report as R
    clock = SimpleNamespace(t=1000.0)
    monkeypatch.setattr(VR, "now", lambda: clock.t)
    original = R.server_lesion_table

    async def slow(segmentation_id):
        clock.t += 10.0
        return await original(segmentation_id)

    monkeypatch.setattr(R, "server_lesion_table", slow)
    assert _post(route, {"lesion_analysis": LESIONS}).status_code == 200
    (call,) = route.provider.calls
    assert call["timeout"] <= VR.REQUEST_BUDGET_S - VR.RESPONSE_MARGIN_S - 10.0 + 1e-6


def test_rc104_w7_too_little_time_is_measurements_only_and_audited(sink):
    client = _Client()
    result = _generate(_service(client), {"lesion_analysis": LESIONS}, request_started=VR.now() - 27.0,
                       audit_actor=SimpleNamespace(id="reader-w7", username="reader-w7", role="radiologist"))
    assert result["verification"]["reason"] == VR.REASON_TIME_BUDGET and client.calls == []
    assert "Lesions marked: 7" in result["content"]
    (outcome,) = [r for r in sink.memory_records if r["event_type"] == "clinical.ai_report.verification"]
    assert outcome["details"]["llm_reason"] == VR.REASON_TIME_BUDGET
