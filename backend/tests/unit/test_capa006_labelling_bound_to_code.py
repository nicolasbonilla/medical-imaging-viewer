"""CAPA-006 PA-6.1 — the MAGNIMS method described in the labelling is bound to the code.

Root cause of CAPA-006 (finding 1): the IFU, AI-Act file, CER and GSPR were ISSUED on 2026-04-12
stating distance thresholds of 3 mm (PV), 4 mm (JC) and 3 mm (IT), six weeks after the code had
moved to 1.5 mm "direct contact" (67fa336, 2026-02-28) — the labelling was wrong when issued and
was never reviewed against the code or the design specification. Nothing could fail. Now:

- IFU §10.3 must state the distance each *_DISTANCE_THRESHOLD_MM constant applies;
- the withdrawn 3/4/3 mm values, a "two-tier" MAGNIMS cascade, "only published, validated" and
  unmeasured "~90 % / ~70 %" accuracy claims may appear only next to a CAPA-006 withdrawal note —
  in the labelling, the design documents AND the Class C code comments;
- the IFU must state that the atlas path is limited to MNI-space images (REQ-SAFE-021);
- a listed document that disappears FAILS the build (it used to be skipped silently).

Negative controls: executed; recorded in
docs/iec62304/records/risk_verification/RC-032_negative_controls_2026-09-28.json (section PA-6.1).
"""
import re
from pathlib import Path

import pytest

import app.services.ms_region_classifier as rc

ROOT = Path(__file__).resolve().parents[3]
LABELLING = [
    "docs/mdr/IFU-001_Instructions_For_Use.md",
    "docs/ai-act/AIA-001_AI_Act_Compliance.md",
    "docs/clinical/CER-001_Clinical_Evaluation_Report.md",
    "docs/mdr/GSPR-001_General_Safety_Performance_Requirements.md",
    "docs/iec62304/00_IEC_62304_Master_Compliance_Document.md",
    "docs/iec62304/02_Software_Requirements_Specification.md",
    "docs/iec62304/04_Software_Architecture_Design.md",
    "docs/iec62304/06_Detailed_Design_Specification.md",
    "docs/usability/UEF-001_Usability_Engineering_File.md",
    "docs/Technical_Documentation_MS_Brain_MRI_Viewer.md",
    "docs/generate_pdf.py",
    "README.md",
    # Class C code comments / docstrings (they are read by reviewers and auditors too)
    "backend/app/services/ms_region_classifier.py",
    "backend/app/api/routes/segmentation_regions.py",
    "frontend/src/api/segmentation.ts",
    "backend/app/mcp/ms_clinical_server.py",          # read by the clinical assistant
    # on-screen labelling
    "frontend/src/i18n/locales/en.json",
    "frontend/src/i18n/locales/es.json",
    "frontend/src/i18n/locales/de.json",
]
_STRUCT = r"(?:the\s+)?(?:lateral\s+)?(?:ventric|cortic|cortex|brain\s+surface|brainstem|infratentorial)"
# 3 or 4 mm, also "3.0 mm" and "3-mm", but not "1.3 mm" (review round 2)
_NUM = r"(?<![\d.])[34](?:\.0)?\s?-?mm"
WITHDRAWN = re.compile(
    _NUM + r"\s*\((?:PV|JC|IT)\)"                                    # "3 mm (PV)"
    r"|\b(?:PV|JC|IT)\)?\s*(?:\|\s*)?(?:<=|≤|<|:|=)?\s*\(?\s*(?:<=|≤|<)?\s*" + _NUM +  # "PV <= 3mm", "| PV | ≤3 mm", "PV (<3 mm)"
    r"|\b(?:PV|JC|IT)\s+within\s+" + _NUM +                          # "PV within 3.0 mm"
    r"|within\s+" + _NUM + r"\s+of\s+" + _STRUCT +                  # "within 3 mm of (the) ventricles"
    r"|" + _NUM + r"\s+(?:of|from)\s+" + _STRUCT,                     # "4 mm from cortex"
    re.IGNORECASE,
)
TWO_TIER = re.compile(r"two-tier\s+(?:MAGNIMS\s+)?(?:classification|cascade)", re.IGNORECASE)
# "Tier 1/Tier 2" is also used for caches; only a MAGNIMS-method line counts
TIER_N = re.compile(r"\bTier\s*[12]\b", re.IGNORECASE)
MAGNIMS_WORDS = re.compile(r"parcellation|MSMask|atlas|geometric|MAGNIMS|EDT|region|zone|classif", re.IGNORECASE)
OVERCLAIM = re.compile(
    r"only\s+published,?\s+(?:and\s+)?(?:clinically\s+)?validated"
    r"|exact\s+methodology"
    r"|validated\s+against\s+expert",
    re.IGNORECASE,
)
# an accuracy/agreement percentage — only on a MAGNIMS line (other features have their own figures)
PERCENT_CLAIM = re.compile(
    r"[<>≤≥~]?\s*\d{2}\+?\s*%\+?\s*(?:agreement|accuracy)"
    r"|(?:agreement|accuracy)[^.\n]{0,25}?[<>≤≥~]\s*\d{2}\s*%",
    re.IGNORECASE,
)
# an exemption needs a CAPA-006 note that actually WITHDRAWS / corrects the text (review round 2)
WITHDRAWAL_MARK = re.compile(
    r"withdrawn|superseded|~~|correction|previous text|previously|replaced|former|was wrong|were wrong|"
    r"contradicted|no evidence|struck|addendum|revision\s+\d|misdescribed|did not match",
    re.IGNORECASE,
)


def _lines(rel):
    p = ROOT / rel
    assert p.exists(), f"{rel} is listed as MAGNIMS labelling but does not exist — update the list"
    return p.read_text(encoding="utf-8").splitlines()


def _offending(rel, predicate):
    """Lines matching `predicate` that are not within one line of a CAPA-006 WITHDRAWAL note."""
    lines = _lines(rel)
    out = []
    for i, ln in enumerate(lines):
        window = " ".join(lines[max(0, i - 1): i + 2])
        if predicate(ln) and not ("CAPA-006" in window and WITHDRAWAL_MARK.search(window)):
            out.append(ln.strip()[:160])
    return out


def _ifu_section_10_3():
    ifu = "\n".join(_lines("docs/mdr/IFU-001_Instructions_For_Use.md"))
    m = re.search(r"^### 10\.3 .*?(?=^### |\Z)", ifu, re.S | re.M)
    assert m, "IFU-001 has no §10.3"
    return m.group(0)


@pytest.mark.unit
def test_capa006_ifu_states_the_distance_the_code_applies():
    section = _ifu_section_10_3()
    for name in ("PV_DISTANCE_THRESHOLD_MM", "JC_DISTANCE_THRESHOLD_MM", "IT_DISTANCE_THRESHOLD_MM"):
        value = f"{getattr(rc, name):g} mm"
        assert value in section, f"IFU §10.3 does not state {name} = {value}"


@pytest.mark.unit
@pytest.mark.parametrize("rel", LABELLING)
def test_capa006_withdrawn_thresholds_appear_only_as_withdrawn(rel):
    offending = _offending(rel, WITHDRAWN.search)
    assert not offending, f"{rel} states the withdrawn 3/4/3 mm thresholds: {offending}"


@pytest.mark.unit
@pytest.mark.parametrize("rel", LABELLING)
def test_capa006_no_two_tier_cascade_is_described(rel):
    offending = _offending(rel, lambda ln: bool(TWO_TIER.search(ln) or (TIER_N.search(ln) and MAGNIMS_WORDS.search(ln))))
    assert not offending, f"{rel} describes a two-tier MAGNIMS cascade: {offending}"


@pytest.mark.unit
@pytest.mark.parametrize("rel", LABELLING)
def test_capa006_no_unsupported_accuracy_or_validation_claim(rel):
    offending = _offending(rel, lambda ln: bool(
        OVERCLAIM.search(ln) or (PERCENT_CLAIM.search(ln) and MAGNIMS_WORDS.search(ln))))
    assert not offending, f"{rel} makes an unsupported MAGNIMS accuracy/validation claim: {offending}"


@pytest.mark.unit
def test_capa006_ifu_states_the_mni_requirement_of_the_atlas():
    section = _ifu_section_10_3()
    assert "MNI" in section and "not in MNI space" in section
    assert "does **not** register" in section or "no registration" in section.lower()


@pytest.mark.unit
def test_capa006_patterns_catch_the_phrasings_that_were_actually_issued():
    """Guards the guard: each phrasing found in the withdrawn labelling must be caught."""
    issued = ["| Periventricular | PV | <= 3 mm from ventricle |", "PV<=3mm, JC<=4mm, IT<=3mm",
              "within 3 mm of the ventricle wall", "4 mm of the cortical surface", "PV: 3 mm",
              "within 3mm of ventricles (MAGNIMS clinical threshold)",
              # phrasings the round-2 review showed the first patterns missed
              "PV within 3.0 mm", "| PV | ≤3 mm |", "| Periventricular (PV) | 3 mm |", "PV (<3 mm)",
              "within 3-mm of the ventricles"]
    for text in issued:
        assert WITHDRAWN.search(text), text
    for claim in ["The only published, validated method for MAGNIMS zone classification.",
                  "only published and clinically validated",
                  "Uses the exact methodology from LST-AI",
                  "MAGNIMS classification validated against expert annotations"]:
        assert OVERCLAIM.search(claim), claim
    for claim in ["uses EDT from anatomical landmarks (~90% accuracy)",
                  "(~70% vs ~90+% agreement with expert classification)", "(~90+% agreement)",
                  ">90% agreement", "90% accuracy", "~95% agreement"]:
        assert PERCENT_CLAIM.search(claim), claim
    assert not WITHDRAWN.search("a 3 mm study reported volumes understated 3x")
    assert not WITHDRAWN.search("lesion 1.3 mm from the cortex")
    # an unrelated CAPA-006 mention does not exempt a withdrawn value
    assert not WITHDRAWAL_MARK.search("see CAPA-006 for the MNI gate")
