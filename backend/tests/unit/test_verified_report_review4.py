"""Fourth independent review of PR #78 (verified AI report), at 44f87cd — written BEFORE the corrections; the tests of
each item fail on the reviewed head. DRAFT, PENDING owner approval.

  Q1 an empty, whitespace-only or "." comment passed and was reported delivered / passed_0.
  Q2 only lowercase {[a-z_]+} tokens were checked: {Total_Count}, { total_count }, {{...}}, [PLACEHOLDER] reached a
     draft. Fuzz over brace and bracket variants.
  Q3 the Limitations line said "clinical indication" is not available although the clinician typed one, shown in the
     same draft.
  Q4 with no provider key the note said the AI service failed while the state said not_requested.
  Q5 the sync/async choice relied on __wrapped__: a wrapped async create went to a thread, its coroutine was never
     awaited, and the wiring fault was reported as a check failure.
  Q6 dis_notice decided by a substring search over the processed content (an explicit fact now); and the text checked
     must be the text delivered (format characters).
  Q7 MEASUREMENT_FINDING_KEYS duplicated verified_report.RENDERED_FINDINGS.
  Q8 pass-through aliases (placeholder_values, _value, _number).

Offline: fake providers, no credential, no network.
"""
import ast
import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import brain_report_service as BRS
from app.services import report_claim_verifier as V
from app.services import verified_report as VR
from app.services.report_payload_guard import PatientIdentifiers, provider_payload
from tests.unit.test_capa014_report_provider_payload import _post, route, route_text  # noqa: F401  (fixtures)

IDS = PatientIdentifiers.from_record({"mrn": "MRN-TEST-0478", "given_name": "Testgiven", "family_name": "Testfamily",
                                      "birth_date": date(1980, 1, 1)})
LESIONS = {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
           "size_distribution": {"small": 4, "medium": 2, "large": 1}}
GOOD = "[FINDINGS_COMMENT]\nMost lesions are small.\n[IMPRESSION_COMMENT]\nTo be reviewed by a radiologist."


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _view(findings, lang="en"):
    p = provider_payload(findings, None)
    return VR.build_view(p.findings, p.volumetry, lang)


def _answer(fc, ic="To be reviewed by a radiologist."):
    return f"[FINDINGS_COMMENT]\n{fc}\n[IMPRESSION_COMMENT]\n{ic}"


def _rules(view, text, lang="en"):
    return {f["rule"] for f in VR.check(view, lang, text)[1]}


def _message(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                           model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=2, output_tokens=2))


class _Client:
    def __init__(self, answers):
        self.answers = list(answers)
        self.messages = self

    def create(self, **kw):
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return _message(a) if isinstance(a, str) else a


def _service(client, key="test-not-a-key"):
    svc = BRS.BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY=key, CLAUDE_MODEL="claude-sonnet-5-5", CLAUDE_MAX_TOKENS=4096,
                                    REPORT_LLM_ENABLED=True)
    if client is not None:
        svc._get_client = lambda: client
    return svc


def _generate(svc, findings, language="en"):
    return _run(svc.generate_report(template_type="general", findings=findings, language=language, identifiers=IDS))


# ═══════════════════════════════════════════════════════════════════════ Q1 — an empty comment is nothing written
EMPTY = ["", " ", ".", "...", "-", "—", "**", "- .", "​", "  .  ", "…", "()", "*"]


@pytest.mark.parametrize("blank", EMPTY, ids=[repr(b) for b in EMPTY])
def test_rc103_q1_an_empty_comment_is_never_checked_as_written(blank):
    view = _view({"lesion_analysis": LESIONS})
    assert "FMT.empty" in _rules(view, _answer(blank))
    assert "FMT.empty" in _rules(view, _answer("Most lesions are small.", blank))
    assert "FMT.empty" not in _rules(view, GOOD)


def test_rc103_q1_three_empty_answers_are_withheld_and_never_delivered():
    result = _generate(_service(_Client([_answer(".", " ")])), {"lesion_analysis": LESIONS})
    v = result["verification"]
    assert v["outcome"] == "blocked" and v["interpretive_text"] == "withheld" and v["reason"] == VR.REASON_BLOCKED
    assert "FMT.empty" in v["rules_failed_last_attempt"]


# ═══════════════════════════════════════════════════════════════════════ Q2 — no raw template token, ever
NAMES = ["total_count", "TOTAL_COUNT", "Total_Count", "total-count", "totalcount", "PLACEHOLDER", "x", ""]
WRAPPERS = ["{%s}", "{ %s }", "{{%s}}", "[%s]", "[ %s ]", "{%s", "%s}", "｛%s｝", "［%s］", "{{ %s }}",
            "{%s}}", "{{%s}", "[[%s]]", "{%s ]", "<%s>"]


def _tokens():
    for name in NAMES:
        for w in WRAPPERS:
            tok = w % name
            if tok == "{total_count}":
                continue                     # the one valid spelling of an available placeholder
            if w == "<%s>" and not name:
                continue
            yield tok


def test_rc103_q2_fuzz_every_other_brace_or_bracket_token_fails_the_check():
    view = _view({"lesion_analysis": LESIONS})
    n = 0
    for tok in _tokens():
        for answer in (_answer(f"Most of the {tok} lesions are small."), _answer("Most lesions are small.", f"See {tok}.")):
            rules = _rules(view, answer)
            if tok.startswith("<"):
                continue                      # angle brackets are not template tokens (checked: never a placeholder)
            assert rules & {"FMT.template_token", "FMT.placeholder"}, (tok, rules)
            n += 1
    assert n > 150
    assert _rules(view, _answer("Most of the {total_count} lesions are small.")) == set()


@pytest.mark.parametrize("tok", ["{Total_Count}", "{ total_count }", "{{total_count}}", "[PLACEHOLDER]",
                                 "[FINDINGS_COMMENT]", "｛total_count｝"])
def test_rc103_q2_a_raw_token_never_reaches_a_draft(tok):
    result = _generate(_service(_Client([_answer(f"Most of the {tok} lesions are small.")])), {"lesion_analysis": LESIONS})
    assert result["verification"]["interpretive_text"] == "withheld"
    assert tok not in result["content"]


# ═══════════════════════════════════════════════════════════════════════ Q3 — the clinician's indication
@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc102_q3_a_typed_indication_is_shown_separately_never_not_available(lang):
    findings = {"lesion_analysis": LESIONS, "clinical_indication": "Follow-up of known findings."}
    result = _generate(_service(_Client([GOOD])), findings, language=lang)
    t = VR.T[lang]
    indication = t["lim_items"].split("|")[0]
    not_available = next(line for line in result["content"].split("\n") if line.startswith(t["lim"].split("{")[0]))
    assert indication not in not_available, not_available
    assert t["lim_indication_entry"] in result["content"]
    p = provider_payload(findings, None)
    view = VR.build_view(p.findings, p.volumetry, lang)
    report = VR.assemble(view, lang, "", "")
    res = V.verify(report, None, view)
    assert not res["primary"], res["elements"]


def test_rc102_q3_without_a_typed_indication_the_line_is_unchanged():
    view = _view({"lesion_analysis": LESIONS})
    report = VR.assemble(view, "en", "", "")
    assert "Not available to the automatic analysis: clinical indication" in report
    assert VR.T["en"]["lim_indication_entry"] not in report


# ═══════════════════════════════════════════════════════════════════════ Q4 — not configured: one note, one state
@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc106_q4_no_provider_key_is_not_requested_in_the_note_and_the_state(lang):
    result = _generate(_service(None, key=""), {"lesion_analysis": LESIONS}, language=lang)
    v = result["verification"]
    assert v["reason"] == VR.REASON_NOT_CONFIGURED and v["outcome"] == "not_requested"
    assert v["interpretive_text"] == "not_requested"
    assert VR.WITHHELD[lang]["not_configured"] in result["content"]
    assert VR.WITHHELD[lang]["unavailable"] not in result["content"]


# ═══════════════════════════════════════════════════════════════════════ Q5 — the client's type, any awaitable awaited
class _AsyncInner:
    async def create(self, **kw):
        return _message("[FINDINGS_COMMENT]\nMost lesions are small.\n[IMPRESSION_COMMENT]\nTo be reviewed.")


class _WrappedAsync:
    """An async create behind a plain wrapper WITHOUT functools.wraps (no __wrapped__)."""

    def __init__(self):
        self.inner = _AsyncInner()
        self.messages = self

    def create(self, **kw):
        return self.inner.create(**kw)


def test_rc106_q5_a_wrapped_async_create_is_awaited():
    result = _generate(_service(_WrappedAsync()), {"lesion_analysis": LESIONS})
    assert result["verification"]["outcome"] == "passed_0", result["verification"]


class _Broken:
    def __init__(self, value):
        self.value = value
        self.messages = self

    def create(self, **kw):
        return self.value


@pytest.mark.parametrize("value", ["not a message", None, 42, {"content": "x"}], ids=["str", "none", "int", "dict"])
def test_rc106_q5_a_wiring_fault_is_a_provider_wiring_failure_not_a_check_failure(value):
    result = _generate(_service(_Broken(value)), {"lesion_analysis": LESIONS})
    v = result["verification"]
    assert v["reason"] == VR.REASON_WIRING and v["outcome"] == "withheld" and v["attempts"] == 1
    assert v["rules_failed_last_attempt"] == []


# ═══════════════════════════════════════════════════════════════════════ Q6 — explicit facts; the text checked is delivered
def test_rc070_q6_the_notice_decides_on_an_explicit_fact_not_on_a_substring():
    from app.api.routes.ai_report import DIS_NOT_EVALUATED_NOTICE, dis_notice
    from app.services.dis_review_gate import NOT_EVALUATED_LINE
    findings = {"lesion_analysis": LESIONS}
    assert DIS_NOT_EVALUATED_NOTICE["en"] not in (dis_notice(findings, "en", 0, stated=True) or "")
    assert DIS_NOT_EVALUATED_NOTICE["en"] in dis_notice(findings, "en", 0, stated=False)
    # a quoted copy of the line inside some text is not the code-written statement
    assert DIS_NOT_EVALUATED_NOTICE["en"] in dis_notice(findings, "en", 0, stated=False)
    assert NOT_EVALUATED_LINE["en"]


def test_rc070_q6_the_route_uses_the_service_fact(route_text):
    from app.api.routes.ai_report import DIS_NOT_EVALUATED_NOTICE
    from app.services.dis_review_gate import NOT_EVALUATED_LINE
    # a text that merely CONTAINS the line (no fact from the service): the route must still state "not evaluated"
    route_text.text_state.text = "> a reader wrote: " + NOT_EVALUATED_LINE["en"]
    body = _post(route_text, {"lesion_analysis": LESIONS}).json()
    assert DIS_NOT_EVALUATED_NOTICE["en"] in body["content"]


# (a zero-width SPACE becomes a visible space under the shared rule — "demye lination" hides nothing — so the in-word
# cases use characters the rule removes: a zero-width joiner, a soft hyphen)
@pytest.mark.parametrize("hidden", ["the pattern is typical of demye‍lination",
                                    "trea­tment escalation should be considered",
                                    "consis‍tent with multi­ple sclerosis"])
def test_rc103_q6_format_characters_cannot_hide_a_phrase_from_the_check(hidden):
    view = _view({"lesion_analysis": LESIONS})
    assembled, fails = VR.check(view, "en", _answer(hidden.capitalize() + "."))
    assert any(f["rule"].startswith("E4.") for f in fails), fails
    assert "​" not in assembled and "­" not in assembled and "‍" not in assembled


# ═══════════════════════════════════════════════════════════════════════ Q7 — one source of the rendered blocks
def test_rc102_q7_the_route_takes_the_rendered_blocks_from_the_verified_report():
    import app.api.routes.ai_report as ai_report
    assert ai_report.MEASUREMENT_FINDING_KEYS == frozenset(VR.RENDERED_FINDINGS)
    tree = ast.parse(Path(ai_report.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "MEASUREMENT_FINDING_KEYS" for t in node.targets):
            assert not any(isinstance(n, ast.Set) for n in ast.walk(node.value)), "a second literal list of the blocks"


# ═══════════════════════════════════════════════════════════════════════ Q8 — no pass-through aliases
def test_rc102_q8_no_pass_through_aliases():
    from app.services import report_payload_guard as G
    assert not hasattr(VR, "placeholder_values") and not hasattr(VR, "_value")
    assert not hasattr(G, "_number")
    assert callable(VR.stated_values) and callable(G.finite_number)
