"""RC-136 (REQ-SAFE-062, HAZ-008 / HAZ-003; SRS/RMF Addendum G, DRAFT — PENDING owner approval): paper 2's experiment
E5 measured the application's verified report (commit e559929) after confirmation, with the experts' masks standing in
for a radiologist's review: the code-written sentence "the brain criterion is met" carried no qualifier in its own
sentence (164 of 168 confirmed vascular reports with each model; Gemini's 165th was the not-met edge case, counted by
the region line, rule (c)), and the one report without any clinical caveat was a NOT-met result whose region line
still listed lesions in 2 regions. So:
  1. a met result is qualified in its own sentence ("automatic", "nonspecific": words of paper 2's frozen qualifier
     list, research/paper_2/classifier.py QUALIFIER on branch research/paper-2-faithful-but-false);
  2. the interpretation (RC-134) follows EVERY evaluated result in the findings (the impression repeats it only after a
     met result)."""
import re

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
COMMENTS = {
    "en": ("The lesions are mostly small, on a segmentation confirmed by a radiologist.",
           "Lesion burden as measured on the confirmed segmentation."),
    "es": ("Las lesiones son sobre todo pequeñas, en una segmentación confirmada por un radiólogo.",
           "Carga lesional medida en la segmentación confirmada."),
    "de": ("Die Läsionen sind überwiegend klein, auf einer von einem Radiologen bestätigten Segmentierung.",
           "Läsionslast wie an der bestätigten Segmentierung gemessen."),
}
# paper 2's frozen qualifier list (research/paper_2/classifier.py, QUALIFIER) — the English one the study applied
P2_QUALIFIER = re.compile(r"\b(?:unreviewed|unconfirmed|not (?:yet )?(?:been )?confirmed|automatic\w*|not (?:a )?diagnos\w*|"
                          r"mimic\w*|vascular|small[- ]vessel|age[- ]related|non-?specific|"
                          r"alternative (?:cause|explanation|diagnos\w*)|differential)\b")
QUALIFIERS = {"en": ("automatic", "nonspecific"), "es": ("automático", "inespecífico"),
              "de": ("automatischen", "unspezifisch")}


def _view(dis, lang="en", la=True):
    findings = {"dis_assessment": dis}
    if la:
        findings["lesion_analysis"] = dict(LESIONS)
    return VR.build_view(findings, None, lang)


def _dis_line(lines, lang):
    head = VR.T[lang]["dis_ev_met"].split(":")[0]
    return next(x for x in lines if x.startswith(head))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("with_count", [True, False])
def test_a_met_result_is_qualified_in_its_own_sentence(lang, with_count):
    dis = {**EVALUATED, "dis_met": True} if with_count else {**{k: v for k, v in EVALUATED.items()
                                                                  if k != "regions_with_lesions"}, "dis_met": True}
    findings, _c, impression, _l = VR.skeleton(_view(dis, lang), lang)
    line = _dis_line(findings, lang)
    for word in QUALIFIERS[lang]:
        assert word in line, (lang, line)
    assert line in impression
    if lang == "en":
        assert P2_QUALIFIER.search(line.lower()), line          # paper 2's own sentence-level qualifier test


@pytest.mark.parametrize("lang", LANGS)
def test_a_not_met_result_keeps_its_plain_line_and_gets_the_interpretation(lang):
    findings, _c, impression, _l = VR.skeleton(_view({**EVALUATED, "dis_met": False}, lang), lang)
    plain = VR.T[lang]["dis_ev"].format(k="2", e=3, met=VR.T[lang]["notmet"])
    assert plain in findings
    notmet = VR.DIS_INTERPRETATION_NOT_MET[lang]
    assert notmet in findings and notmet not in impression and VR.DIS_INTERPRETATION[lang] not in findings


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("met", [True, False])
def test_both_results_pass_the_claim_check(lang, met):
    dis = {**EVALUATED, "dis_met": met, "below_size_lesion_count": 0 if met else 1}
    view = _view(dis, lang)
    answer = f"[FINDINGS_COMMENT]\n{COMMENTS[lang][0]}\n[IMPRESSION_COMMENT]\n{COMMENTS[lang][1]}"
    assembled, fails = VR.check(view, lang, answer)
    assert fails == [], fails
    assert (VR.DIS_INTERPRETATION if met else VR.DIS_INTERPRETATION_NOT_MET)[lang] in assembled


def test_the_new_lines_carry_no_digit_year_or_surname():
    # every word of the report joins the RC-065 device-word list, which the identifier tripwire never reports alone:
    # no digit, year or surname (review of PR #87, finding 3: "Abajo" is a surname; "véase abajo" left the met line)
    texts = [(lang, key, re.sub(r"\{[a-z]+\}", "", VR.T[lang][key])) for lang in LANGS
             for key in ("dis_ev_met", "dis_ev_nc_met", "dis_interp_notmet")]
    texts += [(lang, "NOT_MET", text) for lang, text in VR.DIS_INTERPRETATION_NOT_MET.items()]
    for lang, key, text in texts:
        assert not re.search(r"\d", text) and "McDonald" not in text, (lang, key)
        words = set(re.findall(r"\w+", text.lower()))
        assert not words & {"abajo", "debajo", "más", "mas", "véase", "siehe", "unten", "see"}, (lang, key, words)
