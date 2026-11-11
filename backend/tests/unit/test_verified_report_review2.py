"""Second independent code review of PR #78 (verified AI report), items A-J — written BEFORE the corrections; the
tests of each item fail on the reviewed head (5d2cadb). DRAFT, PENDING owner approval.

  A  the frozen v2 check drops a forbidden phrase (L1 diagnosis, L4 demyelination, L5 treatment) whenever ANY negation
     or condition word stands earlier in the sentence ("This draft is not a diagnosis, but ... consistent with MS").
  B  a comment line in bold, or in capitals of up to 60 characters, is read as a heading and checked for nothing.
     Design rule for A and B: the product check is STRICTLY STRICTER than v2 (property test below).
  C  the payload check refused the whole report (503) for a bad value in a field the report does not use.
  D  the CAPA-008 filter counted measurements the verified report cannot render (an empty report).
  E  a label outside the four MAGNIMS regions made the whole per-region breakdown "not computed".
  F  the "DIS not evaluated" statement appeared three times; `except RuntimeError` in the route was dead.
  G  words of the retired templates still widened the RC-065 vocabulary.
  H  the API description said sex and a 5-year age band are sent.
  I  `PASSED[attempt]` was a fixed 3-tuple although `max_regenerations` is a parameter (IndexError).
  J  the per-lesion table reached the model (up to 3 times) and widened the E1 number pool; the first message was
     built twice.

Offline: fake provider, no credential, no network.
"""
import ast
import asyncio
import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import brain_report_service as BRS
from app.services import report_claim_verifier as V
from app.services import verified_report as VR
from app.services.report_payload_guard import (ImplausibleMeasurement, PatientIdentifiers, provider_payload,
                                               words_of)
from tests.unit.test_capa014_report_provider_payload import _post, route  # noqa: F401  (fixture)
from tests.unit import test_rc103_report_claim_verifier as PORTED

IDS = PatientIdentifiers.from_record({"mrn": "MRN-TEST-0278", "given_name": "Testgiven", "family_name": "Testfamily",
                                      "birth_date": date(1980, 1, 1)})
EVALUATED = {"evaluation_status": "evaluated", "dis_met": True, "regions_with_lesions": 2, "total_dis_regions": 5,
             "region_details": {"Periventricular": {"present": True}, "Juxtacortical": {"present": True},
                                "Infratentorial": {"present": False}}}
LESIONS = {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
           "size_distribution": {"small": 4, "medium": 2, "large": 1}}
GOOD_IMPRESSION = "To be reviewed by a radiologist."


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _view(findings, volumetry=None, lang="en"):
    p = provider_payload(findings, volumetry)
    return VR.build_view(p.findings, p.volumetry, lang)


def _answer(findings_comment, impression_comment=GOOD_IMPRESSION):
    return f"[FINDINGS_COMMENT]\n{findings_comment}\n[IMPRESSION_COMMENT]\n{impression_comment}"


def _rules(fails):
    return {f["rule"] for f in fails}


class _Client:
    def __init__(self, answer=_answer("Most lesions are small.")):
        self.answer, self.calls = answer, []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.answer)], stop_reason="end_turn",
                               model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=2, output_tokens=2))


def _service(client, enabled=True):
    svc = BRS.BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY="test-not-a-key", CLAUDE_MODEL="claude-sonnet-5-5",
                                    CLAUDE_MAX_TOKENS=4096, REPORT_LLM_ENABLED=enabled)
    svc._get_client = lambda: client
    return svc


def _generate(svc, findings, volumetry=None, language="en"):
    return _run(svc.generate_report(template_type="general", findings=findings, volumetry=volumetry,
                                    language=language, identifiers=IDS))


# ═══════════════════════════════════════════════════════════════════════ A — negation must govern the phrase
NOT_EVALUATED_VIEW = {"lesion_analysis": LESIONS}
EVALUATED_VIEW = {"lesion_analysis": LESIONS, "dis_assessment": EVALUATED}

A_CASES = [
    ("en", "This draft is not a diagnosis, but the lesion pattern is consistent with multiple sclerosis."),
    ("en", "No radiologist has reviewed the marking, but the lesions are typical of demyelination."),
    ("en", "If confirmed by a radiologist, the pattern is consistent with multiple sclerosis."),
    ("en", "The lesions are not confluent; treatment escalation should be discussed."),
    ("en", "This is not a final report and disease-modifying therapy may be considered."),
    ("es", "Este borrador no es un diagnóstico, pero el patrón es compatible con esclerosis múltiple."),
    ("es", "No hay datos clínicos; sin embargo, se debe valorar el tratamiento."),
    ("de", "Dieser Entwurf ist keine Diagnose, aber das Muster ist vereinbar mit Multipler Sklerose."),
    ("de", "Kein Radiologe hat die Läsionen geprüft, aber eine Therapie sollte erwogen werden."),
]


@pytest.mark.parametrize("lang,sentence", A_CASES)
@pytest.mark.parametrize("findings", [NOT_EVALUATED_VIEW, EVALUATED_VIEW], ids=["dis_not_evaluated", "dis_evaluated"])
def test_rc103_a_a_negation_elsewhere_in_the_sentence_no_longer_hides_a_forbidden_phrase(lang, sentence, findings):
    view = _view(findings, lang=lang)
    for answer in (_answer(sentence), _answer("Most lesions are small.", sentence)):
        _assembled, fails = VR.check(view, lang, answer)
        assert any(r.startswith("E4.") for r in _rules(fails)), (sentence, fails)


@pytest.mark.parametrize("lang,sentence", [
    ("en", "The pattern is not consistent with multiple sclerosis."),      # a diagnostic statement, negated
    ("en", "There is no evidence of disease activity."),
    ("es", "El patrón no es compatible con esclerosis múltiple."),
    ("de", "Das Muster ist nicht vereinbar mit Multipler Sklerose."),
])
def test_rc103_a_a_diagnostic_or_activity_statement_is_a_finding_in_either_polarity(lang, sentence):
    view = _view(NOT_EVALUATED_VIEW, lang=lang)
    _assembled, fails = VR.check(view, lang, _answer(sentence))
    assert any(r.startswith("E4.") for r in _rules(fails)), (sentence, fails)


@pytest.mark.parametrize("lang,sentence", [
    ("en", "This draft is not a diagnosis."), ("es", "Este borrador no es un diagnóstico."),
    ("de", "Dieser Entwurf ist keine Diagnose."), ("en", "No treatment advice is given."),
])
def test_rc103_a_the_exact_disclaimers_and_a_governed_negation_are_still_allowed(lang, sentence):
    view = _view(NOT_EVALUATED_VIEW, lang=lang)
    _assembled, fails = VR.check(view, lang, _answer(sentence))
    assert fails == [], fails


# ═══════════════════════════════════════════════════════════════════════ B — every line of the comments is checked
@pytest.mark.parametrize("line", [
    "**Consistent with multiple sclerosis**", "CONSISTENT WITH MULTIPLE SCLEROSIS", "__Treatment escalation__",
    "TYPICAL OF DEMYELINATION:", "**Lesion summary**",
])
def test_rc103_b_a_bold_or_capital_line_in_a_comment_is_a_heading_failure_and_is_checked(line):
    view = _view(NOT_EVALUATED_VIEW)
    for answer in (_answer(line + "\nMost lesions are small."), _answer("Most lesions are small.", line)):
        _assembled, fails = VR.check(view, "en", answer)
        assert "FMT.heading" in _rules(fails), (line, fails)
    if re.search(r"(?i)sclerosis|demyelination|treatment", line):
        _assembled, fails = VR.check(view, "en", _answer(line))
        assert any(r.startswith("E4.") for r in _rules(fails)), (line, fails)


# ═══════════════════════════════════════════════════════════════════════ A + B — strictly stricter than v2
def _v2_check(view, lang, text):
    """The benchmark's A3 check with the frozen v2 rules only (format rules + V.verify on the assembled report)."""
    m = VR._SLOT.search(text or "")
    if not m:
        return {"FMT.format"}
    fc, ic = m.group(1).strip(), m.group(2).strip()
    vals = VR.stated_values(view, lang)
    rules = set()
    if any(ph not in vals for ph in re.findall(r"\{([a-z_]+)\}", fc + " " + ic)):
        rules.add("FMT.placeholder")
    if re.search(r"\d", re.sub(r"\{[a-z_]+\}", "", fc + " " + ic)):
        rules.add("FMT.digits")
    for k, v in vals.items():
        fc, ic = fc.replace("{" + k + "}", v), ic.replace("{" + k + "}", v)
    if re.search(r"^\s*#", fc + "\n" + ic, re.M):
        rules.add("FMT.heading")
    for e in V.verify(VR.assemble(view, lang, fc, ic), None, view)["elements"]:
        rules.update(VR._rule_ids(e))
    return rules


def _ported_texts():
    """Every text of the ported benchmark verifier tests (string constants and f-string templates of the module)."""
    tree = ast.parse(Path(PORTED.__file__).read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) >= 12 \
                and " " in node.value and not node.value.startswith(("#", "The benchmark", "Every")):
            out.add(node.value)
        elif isinstance(node, ast.JoinedStr):
            parts = [v.value if isinstance(v, ast.Constant) else "a total volume of 3.1 mL" for v in node.values]
            out.add("".join(parts))
    return sorted(out)


ADVERSARIAL_LEADS = {"en": ["This draft is not a diagnosis", "No radiologist has reviewed these lesions",
                            "If confirmed", "Without clinical data", "It is not certain"],
                     "es": ["Este borrador no es un diagnóstico", "Ningún radiólogo revisó las lesiones", "Si se confirma"],
                     "de": ["Dieser Entwurf ist keine Diagnose", "Kein Radiologe hat die Läsionen geprüft",
                            "Ob dies zutrifft, ist offen"]}
ADVERSARIAL_JOINS = {"en": [", but", "; however,", ", although", ". Nevertheless,", " and", ", yet"],
                     "es": [", pero", "; sin embargo,", ", aunque", " y"],
                     "de": [", aber", "; jedoch", ", sondern", " und"]}
ADVERSARIAL_PHRASES = {"en": ["the lesion pattern is consistent with multiple sclerosis",
                              "the lesions are typical of demyelination", "the findings suggest active disease",
                              "treatment escalation should be considered", "the McDonald criteria are met",
                              "this confirms the diagnosis"],
                       "es": ["el patrón es compatible con esclerosis múltiple", "se cumplen los criterios",
                              "se debe valorar el tratamiento", "hay actividad de la enfermedad"],
                       "de": ["das Muster ist vereinbar mit Multipler Sklerose", "die Kriterien sind erfüllt",
                              "eine Therapie sollte erwogen werden", "es besteht Krankheitsaktivität"]}
FORMATS = ["{s}", "**{s}**", "{S}", "- {s}", "> {s}"]


def adversarial_sentences():
    for lang, leads in ADVERSARIAL_LEADS.items():
        for lead in leads:
            for join in ADVERSARIAL_JOINS[lang]:
                for phrase in ADVERSARIAL_PHRASES[lang]:
                    yield lang, f"{lead}{join} {phrase}."


def test_rc103_product_check_is_strictly_stricter_than_frozen_v2_on_the_ported_corpus():
    """Design rule (second review, A and B): every element v2 returns is also returned by the product check; the
    product check only adds. Run on every text of the ported benchmark verifier tests, against each test view."""
    from app.services import report_claim_strict as S
    views = [PORTED.BASE, PORTED.confirmed_view(), PORTED.pair_view(True), PORTED.pair_view(False)]
    texts = _ported_texts()
    assert len(texts) >= 40
    added = 0
    for text in texts:
        for view in views:
            v2 = {r for e in V.verify(text, None, view)["elements"] for r in VR._rule_ids(e)}
            product = {r for e in S.verify(text, None, view)["elements"] for r in VR._rule_ids(e)}
            assert v2 <= product, (text, v2 - product)
            added += bool(product - v2)
    assert added > 0


@pytest.mark.slow       # (seventh review of PR #78: large by design — run in CI, not on the owner's laptop)
@pytest.mark.parametrize("findings", [NOT_EVALUATED_VIEW, EVALUATED_VIEW], ids=["dis_not_evaluated", "dis_evaluated"])
def test_rc103_product_check_is_strictly_stricter_than_frozen_v2_on_adversarial_comments(findings, monkeypatch):
    """The same property on the answer check (the loop's own check), on generated adversarial comments: a negation
    or condition clause, a contrastive join, a forbidden phrase — in five layouts (plain, bold, capitals, list, quote),
    in the findings and in the impression comment. v2 flags must be kept; every adversarial answer must fail.
    (The frozen v2 result of one assembled report is computed once and shared by both checks — a pure function of
    its text and record — so the test costs half the time; every case is still checked.)"""
    frozen, cache = V.verify, {}

    def verify_once(authored, delivered, view):
        key = (authored, delivered, VR.record_json(view))
        if key not in cache:
            cache[key] = frozen(authored, delivered, view)
        return cache[key]

    monkeypatch.setattr(V, "verify", verify_once)
    n = 0
    for lang, sentence in adversarial_sentences():
        view = _view(findings, lang=lang)
        for fmt in FORMATS:
            line = fmt.format(s=sentence, S=sentence.upper())
            for answer in (_answer(line), _answer("Most lesions are small.", line)):
                v2 = _v2_check(view, lang, answer)
                _assembled, fails = VR.check(view, lang, answer)
                product = _rules(fails)
                assert v2 <= product, (answer, v2 - product)
                assert any(r.startswith("E4.") or r == "FMT.heading" for r in product), answer
                n += 1
    assert n > 1000


# ═══════════════════════════════════════════════════════════════════════ C — only what is rendered is validated
UNRENDERED_BAD = {
    "zone_stats": {"total_brain_voxels": 1000, "zones": {"Periventricular": {"voxel_count": 10, "percentage": 500.0}}},
    "anomalies": [{"type": "Lesion", "confidence": 0.5, "volume_mm3": 1e12}],
    "segmentation_labels": ["Periventricular"],
}
UNRENDERED_VOLUMETRY = {"total_brain_volume_ml": 1100.0, "intracranial_volume_ml": 1450.0,
                        "structures": [{"structure_name": "Brain Stem", "volume_ml": 99999.0}]}


@pytest.mark.parametrize("enabled", [True, False], ids=["llm_on", "llm_off"])
def test_rc064_c_a_bad_value_in_a_field_the_report_does_not_render_never_blocks_it(enabled):
    findings = {"lesion_analysis": {**LESIONS, "lesions": [{"id": 1, "volume_mm3": 1e15, "volume_ml": 1e12,
                                                            "size_category": "large", "centroid": {"z": 1e9}}]},
                "dis_assessment": {**EVALUATED, "active_voxels": -5, "black_hole_voxels": 1e40},
                **UNRENDERED_BAD}
    result = _generate(_service(_Client(), enabled), findings, UNRENDERED_VOLUMETRY)
    assert "Lesions marked: 7" in result["content"]
    assert result["verification"]["not_included"] == ["zone_statistics", "segmentation_labels", "anomalies",
                                                      "structure_volumes"]
    assert VR.T["en"]["ni_structure_volumes"] in result["content"]


def test_rc064_c_a_patient_number_in_a_field_never_sent_does_not_block_and_is_not_sent():
    client = _Client()
    # 1011980: the birth date 1 Jan 1980 as digits (a number form of the patient), in a field the report does not use
    findings = {"lesion_analysis": LESIONS, "anomalies": [{"type": "Lesion", "volume_mm3": 1011980.0}]}
    result = _generate(_service(client), findings)
    assert result["verification"]["outcome"] == "passed_0"
    assert "1011980" not in json.dumps([c["messages"] for c in client.calls])


def test_rc064_c_a_bad_value_in_a_rendered_field_still_refuses():
    with pytest.raises(ImplausibleMeasurement):
        _generate(_service(_Client()), {"lesion_analysis": {**LESIONS, "total_burden_ml": 1e9}})


# ═══════════════════════════════════════════════════════════════════════ D — 422 when nothing is renderable
@pytest.mark.parametrize("findings,volumetry", [
    ({"zone_stats": UNRENDERED_BAD["zone_stats"]}, None),
    ({"segmentation_labels": ["Periventricular"]}, None),
    ({"anomalies": [{"type": "Lesion", "confidence": 0.5}]}, None),
    ({}, {"structures": [{"structure_name": "Brain Stem", "volume_ml": 20.0}]}),
], ids=["zone_stats", "segmentation_labels", "anomalies", "structures_only"])
def test_rc102_d_a_request_with_nothing_the_verified_report_can_render_is_refused(route, findings, volumetry):
    response = _post(route, findings, volumetry)
    assert response.status_code == 422, response.text
    assert route.provider.calls == []


def test_rc102_d_brain_volumes_alone_are_renderable(route):
    response = _post(route, {}, {"total_brain_volume_ml": 1100.0, "intracranial_volume_ml": 1450.0})
    assert response.status_code == 200, response.text


# ═══════════════════════════════════════════════════════════════════════ E — other labels listed separately
def _regions(**counts):
    return {name: {"lesion_count": n, "total_volume_mm3": 1.0, "total_volume_ml": 0.001} for name, n in counts.items()}


@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc102_e_labels_outside_the_four_magnims_regions_never_hide_them(lang):
    regions = {**_regions(Periventricular=3, Juxtacortical=1), **_regions(**{"Active (Gd+)": 2, "Black Hole (T1)": 1})}
    view = _view({"lesion_analysis": {**LESIONS, "regions": regions}, "dis_assessment": EVALUATED}, lang=lang)
    assert view["regions"]["confirmed"] is True
    assert view["regions"]["lesion_counts"] == {"Periventricular": 3, "Juxtacortical": 1, "Infratentorial": 0,
                                                "Deep White Matter": 0}
    assert view["regions"]["other_labels_lesion_count"] == 3
    report = VR.assemble(view, lang, "", "")
    nc = VR.T[lang]["reg_nc"]
    assert nc not in report
    assert VR.T[lang]["reg_other"].format(n=3) in report
    assert "Gd" not in report and "Black Hole" not in report and "Gd" not in VR.first_user_message(view, lang)
    assert not V.verify(report, None, view)["primary"], V.verify(report, None, view)["elements"]


def test_rc102_e_a_region_not_computed_is_not_computed_alone():
    regions = _regions(Periventricular="x", Juxtacortical=2, Infratentorial=1, **{"Deep White Matter": 3})
    view = _view({"lesion_analysis": {**LESIONS, "regions": regions}, "dis_assessment": EVALUATED})
    report = VR.assemble(view, "en", "", "")
    assert "periventricular: not computed; juxtacortical: 2; infratentorial: 1; deep white matter: 3" in report
    assert "periventricular: 0" not in report and not V.verify(report, None, view)["primary"]


# ═══════════════════════════════════════════════════════════════════════ F — one DIS "not evaluated" statement
NOT_EVALUATED_PHRASE = {"en": "Dissemination in space: not evaluated", "es": "Diseminación en el espacio: no evaluada",
                        "de": "Räumliche Dissemination: nicht beurteilt"}


@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc070_f_the_not_evaluated_statement_is_in_the_draft_exactly_once(route, lang):
    response = _post(route, {"lesion_analysis": LESIONS}, language=lang)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"].count(NOT_EVALUATED_PHRASE[lang]) == 1, body["content"]
    from app.services.dis_review_gate import AUTOMATIC_MARKING_NOTICE
    assert AUTOMATIC_MARKING_NOTICE[lang] in body["content"]


def test_rc070_f_a_runtime_error_of_the_service_is_not_reported_as_a_missing_key(route, monkeypatch):
    import app.api.routes.ai_report as ai_report

    class _Failing:
        async def generate_report(self, **kw):
            raise RuntimeError("internal detail that must not reach the client")

    monkeypatch.setattr(ai_report, "get_report_service", lambda: _Failing())
    response = _post(route, {"lesion_analysis": LESIONS})
    assert response.status_code == 500
    assert "internal detail" not in response.text


# ═══════════════════════════════════════════════════════════════════════ G — vocabulary of the text sent now
def test_rc065_g_the_device_vocabulary_is_built_only_from_the_text_sent_now():
    texts = []
    for findings, volumetry, source in VR.synthetic_payloads():
        for lang in VR.LANGUAGES:
            view = VR.build_view(findings, volumetry, lang, review_source=source)
            texts.append(VR.first_user_message(view, lang))
    texts.append(VR.REGENERATION_PREFIX + VR.REGENERATION_SUFFIX)
    texts.extend(VR.FIXED_FEEDBACK_TEXTS)
    expected = frozenset(w for t in texts for w in words_of(t))
    BRS._fixed_prompt_word_lists.cache_clear()
    BRS.fixed_prompt_words.cache_clear()
    BRS.fixed_prompt_pairs.cache_clear()
    assert BRS.fixed_prompt_words() == expected


# ═══════════════════════════════════════════════════════════════════════ H — truthful API description
def test_rc064_h_the_api_description_says_what_is_sent():
    from app.api.routes.ai_report import router
    route_ = next(r for r in router.routes if getattr(r, "path", "").endswith("/generate"))
    assert "5-year age band" not in route_.description and "sex and a" not in route_.description
    assert "no sex, no age band" in route_.description


# ═══════════════════════════════════════════════════════════════════════ I — regenerations bounded and validated
@pytest.mark.parametrize("bad", [3, -1, True, 1.5])
def test_rc103_i_an_invalid_number_of_regenerations_is_refused_before_any_call(bad):
    view = _view(NOT_EVALUATED_VIEW)
    calls = []

    async def call(system, messages, remaining):
        calls.append(1)
        text = _answer("Most lesions are small.") if len(calls) == 4 else _answer("There are 9 lesions.")
        return VR.ModelReply(text=text)

    with pytest.raises(ValueError):
        _run(VR.run_flow(view, "en", call, request_meta={"model": "m"}, tripwire=lambda t: None,
                         on_attempt=lambda r: None, max_regenerations=bad))
    assert calls == []


def test_rc103_i_the_outcome_is_named_from_the_attempt_number():
    view = _view(NOT_EVALUATED_VIEW)
    answers = [_answer("There are 9 lesions."), _answer("Most lesions are small.")]

    async def call(system, messages, remaining):
        return VR.ModelReply(text=answers.pop(0))

    result = _run(VR.run_flow(view, "en", call, request_meta={"model": "m"}, tripwire=lambda t: None,
                              on_attempt=lambda r: None, max_regenerations=1))
    assert result.outcome == "passed_1"


# ═══════════════════════════════════════════════════════════════════════ J — no per-lesion table; message built once
PER_LESION = [{"id": 1, "volume_mm3": 1234.5, "volume_ml": 1.2345, "size_category": "large", "region": "Periventricular"},
              {"id": 2, "volume_mm3": 876.25, "volume_ml": 0.87625, "size_category": "medium",
               "region": "Juxtacortical"}]


def test_rc064_j_no_per_lesion_value_reaches_the_model_and_the_number_pool_shrinks():
    regions = _regions(Periventricular=4, Juxtacortical=3)
    regions["Periventricular"]["total_volume_ml"] = 2.4689
    view = _view({"lesion_analysis": {**LESIONS, "regions": regions, "lesions": PER_LESION},
                  "dis_assessment": EVALUATED})
    record = VR.record_json(view)
    assert "lesion_table" not in record and "volumes_ml" not in record
    for x in ("1234.5", "1.2345", "876.25", "0.87625", "2.4689"):
        assert x not in record
    pool = V.Pools(view).all
    for x in (1234.5, 1.2345, 876.25, 0.87625, 2.4689):
        assert x not in pool
    widened = json.loads(record)
    widened["lesions"]["lesion_table_columns"] = ["id", "volume_mm3", "volume_ml", "size_category"]
    widened["lesions"]["lesion_table"] = [[d["id"], d["volume_mm3"], d["volume_ml"], d["size_category"]]
                                          for d in PER_LESION]
    assert V.Pools(view).all < V.Pools(widened).all


def test_rc065_j_the_first_message_is_built_once_and_is_exactly_what_was_checked(monkeypatch):
    built, checked = [], []
    # (amended with the fifth review of PR #78: the identifier check's cached word lists are built on first use from
    # `first_user_message` of every synthetic payload — warmed here, so the count is this report's own; in a test order
    # where this test ran first, CI counted those 120 calls)
    BRS._fixed_prompt_word_lists()
    original = VR.first_user_message

    def counting(view, lang):
        built.append(1)
        return original(view, lang)

    monkeypatch.setattr(VR, "first_user_message", counting)
    real_check = BRS.assert_prompt_carries_no_identifier

    def recording(text, ids):
        checked.append(text)
        return real_check(text, ids)

    monkeypatch.setattr(BRS, "assert_prompt_carries_no_identifier", recording)
    client = _Client(_answer("There are 9 lesions."))
    _generate(_service(client), {"lesion_analysis": LESIONS})
    assert len(built) == 1
    assert len(client.calls) == 3
    assert all(c["messages"][0]["content"] == checked[0] for c in client.calls)
