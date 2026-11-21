"""RC-134 (REQ-SAFE-061, HAZ-008 / HAZ-003; SRS/RMF Addendum E, DRAFT — PENDING owner approval): an evaluated brain-DIS
result carries what it does not mean, from papers 1 and 2 — in the record the report model reads (paper 2's E4 fields
`rule` and `interpretation`) and, for a met result, in the code-written findings and impression, in the reader's
language. The dashboard shows the same text (the frontend locales are checked against it here)."""
import json
import re
from pathlib import Path

import pytest

from app.services import verified_report as VR

LANGS = ("en", "es", "de")
EVALUATED = {"evaluation_status": "evaluated", "regions_with_lesions": 2, "total_dis_regions": 5,
             "region_details": {"Periventricular": {"present": True}, "Juxtacortical": {"present": True},
                                "Infratentorial": {"present": False}}}
LESIONS = {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
           "size_distribution": {"small": 4, "medium": 2, "large": 1},
           "regions": {r: {"lesion_count": 1} for r in ("Periventricular", "Juxtacortical", "Infratentorial",
                                                         "Deep White Matter")}}


def _view(dis, lang="en"):
    return VR.build_view({"lesion_analysis": dict(LESIONS), "dis_assessment": dis}, None, lang)


def _text(blocks):
    return " ".join(x for block in blocks if block for x in block)


# ------------------------------------------------------------------ the record (paper 2, E4)
def test_record_of_an_evaluated_result_says_what_the_rule_is_and_ignores():
    for met in (True, False):
        dis = _view({**EVALUATED, "dis_met": met})["dis"]
        assert dis["rule"] == VR.DIS_RULE_LABEL
        assert dis["interpretation"] == VR.DIS_INTERPRETATION["en"]


def test_record_without_an_evaluated_result_has_no_interpretation():
    dis = _view({"evaluation_status": "not_evaluated"})["dis"]
    assert "interpretation" not in dis and "rule" not in dis


def test_the_record_sent_to_the_model_contains_the_fields():
    msg = VR.first_user_message(_view({**EVALUATED, "dis_met": True}), "en")
    assert '"interpretation"' in msg and "not evidence of multiple sclerosis" in msg


# ------------------------------------------------------------------ the code-written report
@pytest.mark.parametrize("lang", LANGS)
def test_met_result_is_followed_by_its_interpretation_in_findings_and_impression(lang):
    findings, _comp, impression, _lim = VR.skeleton(_view({**EVALUATED, "dis_met": True}, lang), lang)
    line = VR.DIS_INTERPRETATION[lang]
    assert line in findings and line in impression
    # right after the DIS line: the reader meets the result and its meaning together
    prefix = VR.T[lang]["dis_ev"].split("{")[0]
    assert impression[impression.index(line) - 1].startswith(prefix)
    assert findings[findings.index(line) - 1] == VR.T[lang]["dis_ext"]
    assert findings[findings.index(line) - 2].startswith(prefix)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("dis", [{**EVALUATED, "dis_met": False}, {"evaluation_status": "not_evaluated"}])
def test_no_interpretation_line_without_a_met_result(lang, dis):
    findings, comp, impression, lim = VR.skeleton(_view(dis, lang), lang)
    assert VR.DIS_INTERPRETATION[lang] not in _text([findings, comp, impression, lim])


# ------------------------------------------------------------------ the checks the line must pass
@pytest.mark.parametrize("lang", LANGS)
def test_a_met_report_with_plain_comments_passes_the_claim_check(lang):
    comments = {
        "en": ("The lesions are mostly small, on a segmentation confirmed by a radiologist.",
               "Lesion burden as measured on the confirmed segmentation, without any diagnosis."),
        "es": ("Las lesiones son sobre todo pequeñas, en una segmentación confirmada por un radiólogo.",
               "Carga lesional medida en la segmentación confirmada, sin ningún diagnóstico."),
        "de": ("Die Läsionen sind überwiegend klein, auf einer von einem Radiologen bestätigten Segmentierung.",
               "Läsionslast wie an der bestätigten Segmentierung gemessen, ohne Diagnose."),
    }[lang]
    answer = f"[FINDINGS_COMMENT]\n{comments[0]}\n[IMPRESSION_COMMENT]\n{comments[1]}"
    assembled, fails = VR.check(_view({**EVALUATED, "dis_met": True}, lang), lang, answer)
    assert fails == [], fails
    assert VR.DIS_INTERPRETATION[lang] in assembled


def test_no_digit_year_or_surname_joins_the_device_words():
    # every word and number of the record and the report joins the RC-065 device-word list; a number could equal one
    # of the patient's own (REASON_PRIVACY) and a surname would be exempt from the identifier tripwire
    for text in (VR.DIS_RULE_LABEL, *VR.DIS_INTERPRETATION.values()):
        assert not re.search(r"\d", text), text
        assert "McDonald" not in text and "Montalban" not in text and "MAGNIMS" not in text


# ------------------------------------------------------------------ one text for the dashboard and the report
def test_dashboard_locales_hold_the_same_text():
    root = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "locales"
    if not root.is_dir():
        pytest.skip("frontend sources not in this checkout")
    for lang in LANGS:
        data = json.loads((root / f"{lang}.json").read_text(encoding="utf-8"))
        assert data["lesions"]["disInterpretation"] == VR.DIS_INTERPRETATION[lang], lang
