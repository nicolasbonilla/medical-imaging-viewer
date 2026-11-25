"""PRB-033 / RC-137 (REQ-SAFE-063; HAZ-008, HAZ-003): statements about people without MS rest on checked sources.

No file that is part of the application may cite the unpublished manuscript, carry SibBMS or WMH 2017 results, or bring
back the wording that did not hold in the open data.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
APP = [REPO / "backend" / "app", REPO / "frontend" / "src", REPO / "frontend" / "public", REPO / "flames-worker"]
EXTRA = [REPO / "frontend" / "index.html"]
TEXT = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".txt", ".yaml", ".yml", ".html", ".css"}
# Names and wordings. Results are recognised by name, by the known figures and by the known wordings; a rewording that
# uses none of them is for the reviewer to see (PRB-033, prevention).
FORBIDDEN = {
    "the unpublished manuscript": re.compile(r"MEDRXIV/2026/368633|2026/368633|Automated Lesion Location and Dissemination", re.I),
    "SibBMS results": re.compile(r"sib[ _-]?bms|siberian brain|\b(19|85) of 100\b|\b97 of (the )?97\b", re.I),
    "WMH 2017 results": re.compile(r"\bwmh[ _-]*(challenge[ _-]*)?2017\b|\b(166|167) of 170\b|\b139 of 145\b", re.I),
    "paper 2 figures": re.compile(r"70 and 78 (percentage )?points|43 to 81", re.I),
    "most healthy brains": re.compile(
        r"most healthy (brains|people)|mayoría de (los|las) (cerebros|personas) (sanos|sanas)|meisten gesunden", re.I),
    "spots mostly next to the ventricles": re.compile(
        r"(mostly|mainly|predominantly) next to the ventricles|sobre todo junto a los ventrículos|vor allem neben den Ventrikeln", re.I),
    "most people with vascular disease": re.compile(
        r"most people with vascular|mayoría de[^.\"]{0,60}personas con enfermedad vascular|meisten Menschen mit vaskulärer", re.I),
}


def application_files():
    for root in APP:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in TEXT and not {"node_modules", "__pycache__"} & set(path.parts):
                yield path
    yield from (p for p in EXTRA if p.is_file())


def joined(text: str) -> str:
    """A sentence split over source lines (strings, f-strings, template literals, comments) reads as one."""
    text = re.sub(r"[\"'`]\s*\+?\s*\n\s*[rfbu]{0,2}[\"'`]", "", text)
    text = re.sub(r"\n\s*(#|//|\*)\s?", " ", text)
    return re.sub(r"\s+", " ", text)


@pytest.mark.unit
def test_the_scan_sees_the_application():
    names = {p.name for p in application_files()}
    assert {"dis_review_gate.py", "verified_report.py", "ms_clinical_server.py", "AutomaticMarkingNotice.tsx",
            "es.json"} <= names
    assert len(names) > 200


@pytest.mark.unit
@pytest.mark.parametrize("what", FORBIDDEN)
def test_no_application_file_rests_on_an_unchecked_source(what):
    bad = []
    for path in application_files():
        if path.name == "ms-clinical-assistant.json":       # its change history quotes the old wording on purpose
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("changes")
            text = json.dumps(data, ensure_ascii=False)
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
        if FORBIDDEN[what].search(joined(text)):
            bad.append(str(path.relative_to(REPO)))
    assert bad == [], f"{what}: {bad}"


@pytest.mark.unit
@pytest.mark.parametrize("what,sample", [
    ("the unpublished manuscript", "(medRxiv MEDRXIV/2026/368633)"),
    ("SibBMS results", '"sibbms": {'),
    ("SibBMS results", "Siberian Brain"),
    ("SibBMS results", "for 97 of\n97 healthy controls"),
    ("SibBMS results", 'returned "DIS met" in 19 of 100'),
    ("WMH 2017 results", "in 167 of 170 people"),
    ("WMH 2017 results", "WMH Challenge 2017"),
    ("paper 2 figures", "by 70 and 78 percentage points"),
    ("most healthy brains", "in most healthy brains."),
    ("most healthy brains", "la mayoría de los cerebros sanos"),
    ("most healthy brains", 'in den meisten "\n  f"gesunden Gehirnen'),
    ("spots mostly next to the ventricles", "healthy brains, mostly next to the ventricles; a marked"),
    ("spots mostly next to the ventricles", "mostly ' +\n  'next to the ventricles. ' +\n  'A marked spot"),
    ("spots mostly next to the ventricles", 'sanos, "\n           "sobre todo junto a los ventrículos. Una'),
    ("most people with vascular disease", 'adults and in most "\n  "people with vascular white matter'),
    ("most people with vascular disease", "in most `\n  `people with vascular white"),
    ("most people with vascular disease", "# in most\n# people with vascular white"),
    ("most people with vascular disease", "la mayoría de los adultos mayores y de las personas con enfermedad vascular"),
    ("most people with vascular disease", "la mayoría de las personas con enfermedad vascular"),
])
def test_the_scan_detects_the_former_wording(what, sample):
    assert FORBIDDEN[what].search(joined(sample))


@pytest.mark.unit
def test_the_notice_and_the_interpretation_say_the_checked_wording_in_every_language():
    from app.services.dis_review_gate import AUTOMATIC_MARKING_NOTICE as notice
    from app.services.verified_report import DIS_INTERPRETATION as meaning
    for lang, where, can in (("en", "in different regions and not only next to the ventricles", "in many older adults and can be met in people with vascular"),
                             ("es", "en distintas regiones y no solo junto a los ventrículos", "en muchos adultos mayores y pueden cumplirse en personas con enfermedad vascular"),
                             ("de", "in verschiedenen Hirnregionen und nicht nur neben den Ventrikeln", "bei vielen älteren Erwachsenen erfüllt und können bei Menschen")):
        assert where in notice[lang] and can in meaning[lang]
        locale = json.loads((REPO / "frontend" / "src" / "i18n" / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        assert locale["disReview"]["automaticMarkingNotice"] == notice[lang]
        assert meaning[lang] in json.dumps(locale, ensure_ascii=False)
