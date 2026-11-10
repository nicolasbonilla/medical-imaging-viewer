"""Second independent review of PR #78, item K (found by the agent-platform work, PR #79): the benchmark-derived
verifier does not flag "The findings fulfil dissemination in space." and similar wording — present-tense criterion
verbs (fulfil / fulfill / meet / satisfy), negated and hedged forms — neither when DIS was NOT evaluated (rule 3: say
nothing but "not evaluated") nor when the statement contradicts an evaluated result. Written BEFORE the correction;
DRAFT, PENDING owner approval. Offline.
"""
import pytest

from app.services import report_claim_verifier as V
from app.services import verified_report as VR
from app.services.report_payload_guard import provider_payload

LESIONS = {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
           "size_distribution": {"small": 4, "medium": 2, "large": 1}}


def _evaluated(met):
    return {"evaluation_status": "evaluated", "dis_met": met, "regions_with_lesions": 2 if met else 1,
            "total_dis_regions": 5, "region_details": {"Periventricular": {"present": True},
                                                       "Juxtacortical": {"present": met},
                                                       "Infratentorial": {"present": False}}}


def _view(dis, lang):
    findings = {"lesion_analysis": LESIONS}
    if dis is not None:
        findings["dis_assessment"] = dis
    p = provider_payload(findings, None)
    return VR.build_view(p.findings, p.volumetry, lang)


def _answer(sentence, where):
    other = "Most lesions are small."
    fc, ic = (sentence, other) if where == "findings" else (other, sentence)
    return f"[FINDINGS_COMMENT]\n{fc}\n[IMPRESSION_COMMENT]\n{ic}"


def _rules(view, lang, sentence, where="findings"):
    _assembled, fails = VR.check(view, lang, _answer(sentence, where))
    return {f["rule"] for f in fails}


def _dis_rule(rules):
    return any(r.startswith("E2.") and "dis" in r or r == "RC070.dis_statement" for r in rules)


AFFIRMED = [
    ("en", "The findings fulfil dissemination in space."), ("en", "The findings fulfill dissemination in space."),
    ("en", "The lesions meet dissemination in space."), ("en", "The lesion pattern satisfies dissemination in space."),
    ("en", "The findings fulfil DIS."), ("en", "DIS is met."), ("en", "The lesions satisfy the DIS criterion."),
    ("es", "Los hallazgos cumplen la diseminación en el espacio."), ("es", "La lesión cumple la diseminación en el espacio."),
    ("es", "Se satisface la diseminación en el espacio."),
    ("de", "Der Befund erfüllt die räumliche Dissemination."), ("de", "Die Läsionen erfüllen die räumliche Dissemination."),
]
NEGATED_OR_HEDGED = [
    ("en", "The findings do not fulfil dissemination in space."), ("en", "The lesions may meet dissemination in space."),
    ("en", "The pattern could possibly satisfy dissemination in space."), ("en", "DIS is probably met."),
    ("en", "The findings would not fulfill DIS."),
    ("es", "Los hallazgos no cumplen la diseminación en el espacio."),
    ("es", "Los hallazgos podrían cumplir la diseminación en el espacio."),
    ("de", "Der Befund erfüllt die räumliche Dissemination nicht."),
    ("de", "Der Befund könnte die räumliche Dissemination erfüllen."),
]


@pytest.mark.parametrize("where", ["findings", "impression"])
@pytest.mark.parametrize("lang,sentence", AFFIRMED + NEGATED_OR_HEDGED)
def test_rc103_k_any_statement_on_dis_is_refused_when_dis_was_not_evaluated(lang, sentence, where):
    view = _view(None, lang)
    assert view["dis"]["status"] != "evaluated"
    rules = _rules(view, lang, sentence, where)
    assert _dis_rule(rules), (sentence, rules)


@pytest.mark.parametrize("lang,sentence", AFFIRMED + [s for s in NEGATED_OR_HEDGED if "may" in s[1] or "could" in s[1]
                                                     or "probably" in s[1] or "podr" in s[1] or "könnte" in s[1]])
def test_rc103_k_an_affirmed_or_hedged_dis_statement_contradicting_not_met_is_refused(lang, sentence):
    view = _view(_evaluated(False), lang)
    assert view["dis"]["status"] == "evaluated" and view["dis"]["dis_met_brain"] is False
    rules = _rules(view, lang, sentence)
    assert _dis_rule(rules), (sentence, rules)


@pytest.mark.parametrize("lang,sentence", [s for s in NEGATED_OR_HEDGED if " not " in s[1] or " no " in s[1]
                                           or s[1].endswith("nicht.")])
def test_rc103_k_a_negated_dis_statement_contradicting_met_is_refused(lang, sentence):
    view = _view(_evaluated(True), lang)
    assert view["dis"]["dis_met_brain"] is True
    rules = _rules(view, lang, sentence)
    assert _dis_rule(rules), (sentence, rules)


@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc103_k_the_code_written_not_evaluated_sentence_still_passes(lang):
    from app.services.dis_review_gate import NOT_EVALUATED_LINE
    view = _view(None, lang)
    report = VR.assemble(view, lang, "", "")
    assert NOT_EVALUATED_LINE[lang] in report and not V.verify(report, None, view)["primary"]
    _assembled, fails = VR.check(view, lang, _answer(NOT_EVALUATED_LINE[lang], "findings"))
    assert fails == [], fails


@pytest.mark.parametrize("lang,sentence,met", [
    ("en", "The brain criterion for dissemination in space is met.", True),
    ("en", "Dissemination in space is not met in the brain.", False),
    ("es", "El criterio cerebral de diseminación en el espacio se cumple.", True),
    ("de", "Das Hirnkriterium der räumlichen Dissemination ist nicht erfüllt.", False),
])
def test_rc103_k_a_statement_that_agrees_with_an_evaluated_result_still_passes(lang, sentence, met):
    view = _view(_evaluated(met), lang)
    _assembled, fails = VR.check(view, lang, _answer(sentence, "findings"))
    assert not _dis_rule({f["rule"] for f in fails}), fails
