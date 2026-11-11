"""Fifth independent review of PR #78 (verified AI report), at 4393020 — written BEFORE the corrections; the tests of
each item fail on the reviewed head. DRAFT, PENDING owner approval.

  V1 (clinical) only digits were forbidden in the comments: "Twelve lesions are marked", "zwei neue Kandidaten",
     "doce lesiones" passed. Number, ordinal and count-quantifier words are forbidden (articles allowed).
  V2 (clinical) the draft's "new candidates" came from status_counts.new (every new component, also < 3 mm); the
     CAPA-013 notice and the review screen use change_candidates. One source, one number.
  V3 an exception after the model answered (in the check) gave HTTP 500 and an audit "not_sent, 0 attempts".
  V4 a new AsyncAnthropic (and HTTP pool) for every request, never closed.
  V5 with the kill switch off or no key the patient record and the provider-only refusals were still required.
  V6 the limitations said contrast-enhanced and T1-weighted imaging were unavailable while the confirmed segmentation
     counted labels drawn on them.
  V7 check() rebuilt the claim check instead of calling the one verify function the property tests exercise.
  V8 a hidden result key and a re-run DIS scrub in the route: the service owns the DIS notice (typed field).
  V9 the "DIS not evaluated" line was written for a volumetry-only or longitudinal-only report.
  V10 deduplication by Match identity and a redundant inner finditer.

Offline: fake providers, in-memory audit sink, no credential, no network.
"""
import ast
import asyncio
import inspect
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.logging.audit_sink import DurableAuditSink, set_durable_audit_sink
from app.services import brain_report_service as BRS
from app.services import report_claim_strict as S
from app.services import report_claim_verifier as V
from app.services import verified_report as VR
from app.services.report_payload_guard import ImplausibleMeasurement, PatientIdentifiers, provider_payload
from tests.unit.test_capa014_report_provider_payload import _post, route  # noqa: F401  (fixture)

IDS = PatientIdentifiers.from_record({"mrn": "MRN-TEST-0578", "given_name": "Testgiven", "family_name": "Testfamily",
                                      "birth_date": date(1980, 1, 1)})
LESIONS = {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
           "size_distribution": {"small": 4, "medium": 2, "large": 1}}
EVALUATED = {"evaluation_status": "evaluated", "dis_met": True, "regions_with_lesions": 2, "total_dis_regions": 5,
             "region_details": {"Periventricular": {"present": True}, "Juxtacortical": {"present": True},
                                "Infratentorial": {"present": False}}}
GOOD = "[FINDINGS_COMMENT]\nMost lesions are small.\n[IMPRESSION_COMMENT]\nTo be reviewed by a radiologist."
REPO = Path(__file__).resolve().parents[3]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _view(findings, volumetry=None, lang="en"):
    f, v, ni = VR.rendered_request(findings, volumetry)
    p = provider_payload(f, v)
    return VR.build_view(p.findings, p.volumetry, lang, not_included=ni)


def _answer(fc, ic="To be reviewed by a radiologist."):
    return f"[FINDINGS_COMMENT]\n{fc}\n[IMPRESSION_COMMENT]\n{ic}"


def _rules(view, text, lang="en"):
    return {f["rule"] for f in VR.check(view, lang, text)[1]}


def _message(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                           model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=2, output_tokens=2))


class _Client:
    def __init__(self, answer=GOOD):
        self.answer, self.calls = answer, []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return _message(self.answer)


def _service(client, enabled=True, key="test-not-a-key"):
    svc = BRS.BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY=key, CLAUDE_MODEL="claude-sonnet-5-5", CLAUDE_MAX_TOKENS=4096,
                                    REPORT_LLM_ENABLED=enabled)
    if client is not None:
        svc._get_client = lambda: client
    return svc


def _generate(svc, findings, volumetry=None, language="en", identifiers=IDS, **kw):
    return _run(svc.generate_report(template_type="general", findings=findings, volumetry=volumetry,
                                    language=language, identifiers=identifiers, **kw))


@pytest.fixture
def sink():
    from app.core.logging.audit import reset_audit_budget
    reset_audit_budget()
    memory = DurableAuditSink(None, backend="memory")
    previous = set_durable_audit_sink(memory)
    yield memory
    set_durable_audit_sink(previous)


# ═══════════════════════════════════════════════════════════════════════ V1 — no number words in the comments
NUMBER_WORDS = {
    "en": ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
           "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "twenty-one",
           "thirty", "forty-two", "hundred", "dozen", "both", "first", "second", "third", "fourth", "tenth", "twice",
           "single", "pair", "half", "zero"],
    "es": ["uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce", "trece",
           "catorce", "quince", "dieciséis", "diecinueve", "veinte", "veintiuno", "veintidós", "treinta", "cien",
           "docena", "ambos", "ambas", "primera", "segundo", "tercera", "cuarto", "única", "par", "mitad", "cero"],
    "de": ["eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf",
           "dreizehn", "neunzehn", "zwanzig", "einundzwanzig", "zweiundvierzig", "dreißig", "hundert", "Dutzend",
           "beide", "beiden", "erste", "zweite", "dritten", "vierte", "einzige", "Paar", "Hälfte", "null", "zweimal"],
}
FRAMES = {"en": "Most of the {w} lesions are small.", "es": "La mayoría de las {w} lesiones son pequeñas.",
          "de": "Die meisten der {w} Läsionen sind klein."}


def test_rc103_v1_fuzz_number_ordinal_and_count_words_fail_the_check_in_every_language():
    n = 0
    for lang, words in NUMBER_WORDS.items():
        view = _view({"lesion_analysis": LESIONS}, lang=lang)
        for w in words:
            for variant in {w, w.capitalize(), w.upper()}:
                for answer in (_answer(FRAMES[lang].format(w=variant)), _answer("Most lesions are small.",
                                                                               FRAMES[lang].format(w=variant))):
                    assert "FMT.number_words" in _rules(view, answer, lang), (lang, variant)
                    n += 1
    assert n > 500


@pytest.mark.parametrize("sentence", ["Twelve lesions are marked.", "Lesions lie in three of the four regions.",
                                      "Lesions are in all four regions.", "Zwei neue Kandidaten wurden markiert.",
                                      "Se marcaron doce lesiones.", "There are twenty-one small lesions.",
                                      "Es gibt einundzwanzig kleine Läsionen.", "Ambas regiones tienen lesiones."])
def test_rc103_v1_the_reviewers_examples_fail(sentence):
    assert "FMT.number_words" in _rules(_view({"lesion_analysis": LESIONS}), _answer(sentence))


@pytest.mark.parametrize("lang,sentence", [
    ("en", "A lesion pattern is marked; an automatic marking, to be reviewed."),
    ("es", "Una marcación automática, un borrador para revisar."),
    ("de", "Eine automatische Markierung, ein Entwurf zur Prüfung."),
    ("en", "Several small lesions; most lesions are small."),
    ("de", "Die Markierung wurde beobachtet; Hilfe beim Lesen."),       # "acht", "elf" only inside other words
])
def test_rc103_v1_articles_and_words_that_only_contain_a_number_are_allowed(lang, sentence):
    assert "FMT.number_words" not in _rules(_view({"lesion_analysis": LESIONS}, lang=lang), _answer(sentence), lang)


# ═══════════════════════════════════════════════════════════════════════ V2 — one source for the candidate figure
LONG = {"burden_tp1_ml": 1.0, "burden_tp2_ml": 1.4, "total_lesions_tp1": 3, "total_lesions_tp2": 9,
        "burden_delta_percent": 40.0, "abstained": False,
        "status_counts": {"new": 5, "enlarged": 2, "resolved": 0, "shrunk": 0, "stable": 3},
        "change_candidates": {"new": 2, "enlarging": 1, "total": 3, "confirmed": 0, "rejected": 0,
                              "awaiting_review": 3}}


@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc102_v2_the_draft_and_the_notice_state_the_reviewable_candidates(lang):
    from app.api.routes.ai_report import longitudinal_notice
    view = _view({"longitudinal": LONG}, lang=lang)
    assert view["longitudinal"]["candidates"]["new"] == 2 and view["longitudinal"]["candidates"]["enlarged"] == 1
    comp = VR.skeleton(view, lang)[1][0]
    t = VR.T[lang]
    assert comp == t["lng_ok"].format(new=2, enl=1, res=0, shr=0, sta=3)
    assert VR.stated_values(view, lang)["new_candidates"] == "2"
    notice = longitudinal_notice(LONG, lang)
    from app.api.routes.ai_report import LONGITUDINAL_NOTICE
    assert LONGITUDINAL_NOTICE[lang]["candidates"].format(total=3, new=2, enl=1) in notice
    assert VR.reviewable_candidate_counts(LONG) == (2, 1)


def test_rc102_v2_without_the_candidate_block_both_count_what_the_rule_counts():
    from app.api.routes.ai_report import longitudinal_notice
    lng = {k: v for k, v in LONG.items() if k != "change_candidates"}
    assert VR.reviewable_candidate_counts(lng) == (5, 2)
    view = _view({"longitudinal": lng})
    assert view["longitudinal"]["candidates"]["new"] == 5
    assert "(5 new, 2 enlarging)" in longitudinal_notice(lng, "en")


# ═══════════════════════════════════════════════════════════════════════ V3 — an internal check error is withheld
def test_rc104_v3_an_exception_in_the_check_after_the_model_answered_is_withheld_and_audited(sink, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("internal check fault")

    monkeypatch.setattr(VR, "check", boom)
    result = _generate(_service(_Client()), {"lesion_analysis": LESIONS},
                       audit_actor=SimpleNamespace(id="reader-v3", username="reader-v3", role="radiologist"))
    v = result["verification"]
    assert v["outcome"] == "withheld" and v["reason"] == VR.REASON_INTERNAL_CHECK and v["attempts"] == 1
    assert "Lesions marked: 7" in result["content"]
    attempts = [r for r in sink.memory_records if r["event_type"] == "clinical.ai_report.attempt"]
    (outcome,) = [r for r in sink.memory_records if r["event_type"] == "clinical.ai_report.verification"]
    assert len(attempts) == 1 and attempts[0]["details"]["verdict"] == "error"
    assert outcome["details"]["report_outcome"] == "withheld" and outcome["details"]["attempts"] == 1
    assert outcome["details"]["llm_reason"] == VR.REASON_INTERNAL_CHECK


# ═══════════════════════════════════════════════════════════════════════ V4 — one cached client, closed on shutdown
def test_rc106_v4_one_cached_client_with_the_allowed_timeout_closed_on_shutdown(monkeypatch):
    import sys
    module = MagicMock()
    module.AsyncAnthropic.return_value.close = AsyncMock()
    monkeypatch.setitem(sys.modules, "anthropic", module)
    _run(BRS.close_report_clients())
    a, b = BRS.BrainReportService(), BRS.BrainReportService()
    for svc in (a, b):
        svc._settings = SimpleNamespace(ANTHROPIC_API_KEY="test-not-a-key")
    assert a._get_client() is b._get_client()
    assert module.AsyncAnthropic.call_count == 1
    kw = module.AsyncAnthropic.call_args.kwargs
    assert kw["max_retries"] == 0 and kw["timeout"] == VR.LLM_DEADLINE_S
    _run(BRS.close_report_clients())
    module.AsyncAnthropic.return_value.close.assert_awaited_once()
    assert "close_report_clients" in (REPO / "backend" / "app" / "main.py").read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════ V5 — nothing sent: no provider-only checks
def test_rc105_v5_kill_switch_off_needs_no_patient_record(route, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "REPORT_LLM_ENABLED", False)
    route.patients.error = RuntimeError("patient store down")
    r = _post(route, {"lesion_analysis": LESIONS})
    assert r.status_code == 200, r.text
    assert r.json()["verification"]["reason"] == VR.REASON_OFF and route.provider.calls == []
    assert route.patients.asked == []


def test_rc105_v5_nothing_sent_keeps_the_measurement_checks_only():
    # no identifiers at all, kill switch off: a measurements-only draft
    result = _generate(_service(None, enabled=False), {"lesion_analysis": LESIONS}, identifiers=None)
    assert result["verification"]["reason"] == VR.REASON_OFF
    # a value in the patient's own number form is not a provider-only refusal when nothing is sent
    result = _generate(_service(None, enabled=False),
                       {"lesion_analysis": {**LESIONS, "total_burden_mm3": 1011980.0}}, identifiers=IDS)
    assert "1011980" in result["content"].replace(",", "")
    # the measurement-validity checks that protect the code-written text stay
    with pytest.raises(ImplausibleMeasurement):
        _generate(_service(None, enabled=False), {"lesion_analysis": {**LESIONS, "total_burden_ml": 1e9}},
                  identifiers=None)
    # no key: the same
    result = _generate(_service(None, key=""), {"lesion_analysis": LESIONS}, identifiers=None)
    assert result["verification"]["reason"] == VR.REASON_NOT_CONFIGURED


# ═══════════════════════════════════════════════════════════════════════ V6 — limitations consistent with the labels
def _regions(**counts):
    return {name: {"lesion_count": n} for name, n in counts.items()}


@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc102_v6_labels_drawn_on_contrast_and_t1_images_change_the_limitations(lang):
    regions = {**_regions(Periventricular=3, Juxtacortical=1), **_regions(**{"Active (Gd+)": 2, "Black Hole (T1)": 1})}
    view = _view({"lesion_analysis": {**LESIONS, "regions": regions}, "dis_assessment": EVALUATED}, lang=lang)
    report = VR.assemble(view, lang, "", "")
    t = VR.T[lang]
    items = t["lim_items"].split("|")
    not_available = next(line for line in report.split("\n") if line.startswith(t["lim"].split("{")[0]))
    assert items[1] not in not_available and items[2] not in not_available, not_available
    assert t["lim_other_images"].format(items=", ".join(items[1:3])) in report
    assert not V.verify(report, None, view)["primary"], V.verify(report, None, view)["elements"]
    only_gd = _view({"lesion_analysis": {**LESIONS, "regions": {**_regions(Periventricular=3),
                                                                   **_regions(**{"Active (Gd+)": 2})}},
                     "dis_assessment": EVALUATED}, lang=lang)
    report = VR.assemble(only_gd, lang, "", "")
    not_available = next(line for line in report.split("\n") if line.startswith(t["lim"].split("{")[0]))
    assert items[1] not in not_available and items[2] in not_available


def test_rc102_v6_without_those_labels_the_limitations_are_unchanged():
    report = VR.assemble(_view({"lesion_analysis": LESIONS}), "en", "", "")
    assert "contrast-enhanced imaging, T1-weighted imaging" in report


# ═══════════════════════════════════════════════════════════════════════ V7 — one verify function on the production path
def test_rc103_v7_check_calls_the_one_verify_function(monkeypatch):
    calls = []
    real = S.verify

    def spy(*a, **kw):
        calls.append((a, kw))
        return real(*a, **kw)

    monkeypatch.setattr(S, "verify", spy)
    view = _view({"lesion_analysis": LESIONS})
    VR.check(view, "en", _answer("Most lesions are small.", "To be reviewed."))
    assert len(calls) == 1 and list(calls[0][1]["model_text"]) == ["Most lesions are small.", "To be reviewed."]
    src = inspect.getsource(VR.check)
    assert "V.verify(" not in src and "comment_elements(" not in src and "heading_lines(" not in src


# ═══════════════════════════════════════════════════════════════════════ V8 — the service owns the DIS notice
def test_rc070_v8_the_service_owns_the_dis_notice_and_returns_a_typed_field(route):
    from app.services.dis_review_gate import AUTOMATIC_MARKING_NOTICE, NOT_EVALUATED_LINE
    body = _post(route, {"lesion_analysis": LESIONS}).json()
    assert body["dis_evaluation"] == "not_evaluated"
    assert body["content"].count(NOT_EVALUATED_LINE["en"].rstrip(".")) == 1
    assert body["content"].count(AUTOMATIC_MARKING_NOTICE["en"]) == 1
    src = (REPO / "backend" / "app" / "api" / "routes" / "ai_report.py").read_text(encoding="utf-8")
    assert "scrub_unevaluated_dis(" not in src and "def dis_notice" not in src
    assert "dis_not_evaluated_stated" not in src


def test_rc070_v8_an_evaluated_dis_has_no_not_evaluated_statement(route):
    from app.services.dis_review_gate import AUTOMATIC_MARKING_NOTICE, NOT_EVALUATED_LINE
    body = _post(route, {"lesion_analysis": {**LESIONS, "regions": _regions(Periventricular=3, Juxtacortical=4)},
                         "dis_assessment": EVALUATED}).json()
    assert body["dis_evaluation"] == "evaluated"
    assert NOT_EVALUATED_LINE["en"].rstrip(".") not in body["content"]
    assert AUTOMATIC_MARKING_NOTICE["en"] not in body["content"]


# ═══════════════════════════════════════════════════════════════════════ V9 — DIS only with lesion findings
@pytest.mark.parametrize("findings,volumetry", [({}, {"total_brain_volume_ml": 1100.0}),
                                                ({"longitudinal": LONG}, None)], ids=["volumetry", "longitudinal"])
def test_rc102_v9_no_dis_line_without_lesion_findings(findings, volumetry):
    from app.services.dis_review_gate import NOT_EVALUATED_LINE
    view = _view(findings, volumetry)
    report = VR.assemble(view, "en", "", "")
    assert NOT_EVALUATED_LINE["en"] not in report and "Dissemination in space" not in report
    result = _generate(_service(_Client()), findings, volumetry)
    assert result["dis_evaluation"] == "not_in_report"
    assert "Dissemination in space" not in result["content"]


def test_rc102_v9_with_a_lesion_analysis_the_line_is_written_once():
    from app.services.dis_review_gate import NOT_EVALUATED_LINE
    report = VR.assemble(_view({"lesion_analysis": LESIONS}), "en", "", "")
    assert report.count(NOT_EVALUATED_LINE["en"]) == 1


# ═══════════════════════════════════════════════════════════════════════ V10 — one pass, deduplicated by span
def test_rc103_v10_a_criterion_word_near_two_dis_names_is_counted_once():
    fold = "dissemination in space or dis is met"
    found = S._criteria_on_dis(fold)
    assert [m.span() for m in found] == [(fold.index("met"), fold.index("met") + 3)]
    tree = ast.parse(inspect.getsource(S._criteria_on_dis))
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.For)]
    inner = [n for loop in loops for n in ast.walk(loop) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "finditer" and n is not loop.iter]
    assert not any("DIS_CRITERION" in ast.unparse(c) for c in inner), "a finditer of the criteria inside a loop"
