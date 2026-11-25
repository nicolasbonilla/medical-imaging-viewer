"""PRB-033 / RC-137 (REQ-SAFE-063; HAZ-008, HAZ-003): statements about people without MS rest on checked sources.

No file that is part of the application may cite the unpublished manuscript, carry SibBMS or WMH 2017 results, or bring
back the wording that did not hold in the open data.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
APP = [REPO / "backend" / "app", REPO / "frontend" / "src"]
TEXT = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".txt", ".yaml", ".yml", ".html", ".css"}
FORBIDDEN = {
    "the unpublished manuscript": re.compile(r"MEDRXIV/2026/368633|2026/368633", re.I),
    "SibBMS results": re.compile(r"sibbms", re.I),
    "WMH 2017 results": re.compile(r"\bwmh[ _-]?2017\b|167 of 170|166 of 170", re.I),
    "spots mostly next to the ventricles": re.compile(
        r"mostly next to the ventricles\. A marked|sobre todo junto a los ventrículos|vor allem neben den Ventrikeln", re.I),
    "most people with vascular disease": re.compile(
        r"in most people with vascular|la mayoría[^.\"]{0,40} y de las personas con enfermedad vascular|"
        r"bei den meisten Menschen mit vaskulärer", re.I),
}


def application_files():
    for root in APP:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in TEXT and "node_modules" not in path.parts:
                yield path


def joined(text: str) -> str:
    """A sentence split over source lines reads as one ('...' '...' and JSX/py concatenations)."""
    return re.sub(r"[\"']\s*\+?\s*\n\s*[\"']", "", text)


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
    ("WMH 2017 results", "in 167 of 170 people"),
    ("spots mostly next to the ventricles", "healthy brains, mostly next to the ventricles. ' +\n  'A marked spot"),
    ("spots mostly next to the ventricles", 'sanos, "\n           "sobre todo junto a los ventrículos. Una'),
    ("most people with vascular disease", 'adults and in most "\n  "people with vascular white matter'),
    ("most people with vascular disease", "la mayoría de los adultos mayores y de las personas con enfermedad vascular"),
])
def test_the_scan_detects_the_former_wording(what, sample):
    assert FORBIDDEN[what].search(joined(sample))


@pytest.mark.unit
def test_the_notice_and_the_interpretation_say_the_checked_wording_in_every_language():
    from app.services.dis_review_gate import AUTOMATIC_MARKING_NOTICE as notice
    from app.services.verified_report import DIS_INTERPRETATION as meaning
    for lang, where, can in (("en", "in any region of the brain", "can be met in people with vascular"),
                             ("es", "en cualquier región del cerebro", "pueden cumplirse en personas con enfermedad vascular"),
                             ("de", "in jeder Hirnregion", "können bei Menschen mit vaskulärer Erkrankung")):
        assert where in notice[lang] and can in meaning[lang]
        locale = json.loads((REPO / "frontend" / "src" / "i18n" / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        assert locale["disReview"]["automaticMarkingNotice"] == notice[lang]
        assert meaning[lang] in json.dumps(locale, ensure_ascii=False)
