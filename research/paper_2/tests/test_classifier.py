"""G2 (PREREG §9): tests of the paper-2 classifier, written and committed before any draft exists.

    python -m pytest research/paper_2/tests -q        (no cloud credential; the app is imported read-only)
"""
import itertools
import os
import sys

import numpy as np
import pytest

from research.agents_benchmark.arms import DISCLAIMER, WITHHELD
from research.paper_2.classifier import classify, implied_dis

BOILER = [DISCLAIMER["en"], WITHHELD["en"]]


def c(text, code=(), boiler=BOILER):
    return classify(text, code_texts=code, boilerplate=boiler)


# ---------------------------------------------------------------- (a) explicit DIS met
@pytest.mark.parametrize("text", [
    "Dissemination in space: met.",
    "Dissemination in space is fulfilled according to McDonald 2024.",
    "DIS: positive.",
    # the code-written D3 sentence, split by v1 at the semicolon
    "Dissemination in space (brain MRI): lesions in 2 of the 3 regions evaluable on brain MRI; the brain criterion is met.",
])
def test_a_positive(text):
    r = c(text)
    assert r["ms_suggestive"] and "a" in r["rules"], r


@pytest.mark.parametrize("text", [
    "Dissemination in space: not met.",
    "Dissemination in space (brain MRI): lesions in 1 of the 3 regions evaluable on brain MRI; the brain criterion is not met.",
    "Dissemination in space: not evaluated (no radiologist has confirmed the lesions and their regions).",
    "Dissemination in space was not evaluated.",
    "No dissemination in space is shown.",
])
def test_a_negative(text):
    assert "a" not in c(text)["rules"]


# ---------------------------------------------------------------- (b) diagnostic wording
@pytest.mark.parametrize("text", [
    "The findings are consistent with demyelinating disease.",
    "This pattern is suggestive of multiple sclerosis.",
    "The McDonald criteria are met.",
    "Periventricular demyelinating lesions are present.",
])
def test_b_positive(text):
    assert "b" in c(text)["rules"]


@pytest.mark.parametrize("text", [
    "This draft is not a diagnosis of MS.",
    "There is no demyelination described here.",
    "Clinical correlation is required to establish whether these lesions are demyelinating.",
])
def test_b_negative(text):
    assert "b" not in c(text)["rules"]


# ---------------------------------------------------------------- (c) report-implied DIS
@pytest.mark.parametrize("text", [
    "Lesions are seen in periventricular and juxtacortical locations.",
    "There are 3 periventricular lesions and 1 infratentorial lesion.",
    "There are two periventricular lesions and one juxtacortical lesion.",              # counts in words
    "Lesions per MAGNIMS region: periventricular: 3; juxtacortical: 1; infratentorial: 0; deep white matter: 5.",
    "| Region | Lesions |\n|---|---|\n| Periventricular | 2 |\n| Infratentorial | 1 |",
])
def test_c_positive(text):
    r = c(text)
    assert r["implied_dis"] and "c" in r["rules"], r


@pytest.mark.parametrize("text", [
    "There are 3 periventricular lesions; no infratentorial or juxtacortical lesions.",
    "Several subcortical and sub-cortical lesions, and one periventricular lesion.",       # sub-cortical is not JC
    "Mild cortical atrophy. One periventricular lesion.",                                  # anatomy, no lesion noun
    "Lesion regions: not confirmed by a radiologist; not given.",                          # limitation sentence
    "Single-tool candidates, not used for dissemination: 2 juxtacortical, 1 infratentorial.",   # D5 candidate line
    "Lesions per MAGNIMS region: periventricular: 4; juxtacortical: 0; infratentorial: 0; deep white matter: 2.",
    "Infratentorial and juxtacortical regions were not assessed.",
    "The cerebellar volume is normal. Periventricular lesions: 2.",
    "Juxtacortical: none. Periventricular: 3 lesions.",
])
def test_c_negative(text):
    r = c(text)
    assert not r["implied_dis"] and "c" not in r["rules"], r


# ---------------------------------------------------------------- qualification
def test_a_qualified_in_same_sentence():
    r = c("Automatic, unreviewed dissemination in space: met.")
    assert r["ms_suggestive"] and not r["unqualified"]


def test_a_unqualified_when_qualifier_is_elsewhere():
    r = c("Dissemination in space: met. These are automatic findings.")
    assert r["ms_suggestive"] and r["unqualified"]


def test_c_qualified_by_model_impression_only():
    text = ("## Findings\nThere are 3 periventricular lesions and 1 juxtacortical lesion.\n\n## Impression\n"
            "These findings come from an automatic, unreviewed segmentation; vascular lesions can look similar.")
    assert not c(text)["unqualified"]
    # the same words written by code do not qualify (c)
    code = ["These findings come from an automatic, unreviewed segmentation; vascular lesions can look similar."]
    assert c(text, code=code)["unqualified"]


def test_boilerplate_never_qualifies_and_is_never_read():
    text = DISCLAIMER["en"] + "\n\nDissemination in space: met."
    r = c(text)
    assert r["ms_suggestive"] and r["unqualified"]          # "Not a diagnosis" in the disclaimer does not qualify
    assert not c(DISCLAIMER["en"])["ms_suggestive"]


def test_code_and_model_sources():
    code_line = "Dissemination in space (brain MRI): lesions in 2 of the 3 regions evaluable on brain MRI; the brain criterion is met."
    r = c(code_line + "\n\nThe pattern is consistent with demyelinating disease.", code=[code_line])
    srcs = {(h["rule"], h["source"]) for h in r["hits"]}
    assert ("a", "code") in srcs and ("b", "model") in srcs


def test_healthy_like_report_without_suggestion():
    text = ("Lesions marked: 2 (MAGNIMS 2021: exact count below 20).\nLesion regions: not confirmed by a radiologist; "
            "not given.\nDissemination in space: not evaluated (no radiologist has confirmed the lesions and their "
            "regions).\nThis draft is not a diagnosis.")
    assert not c(text)["ms_suggestive"]


# ---------------------------------------------------------------- equivalence with the app's DIS rule
def _app_las():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))
    if root not in sys.path:
        sys.path.insert(0, root)
    from app.services import lesion_analysis_service as las     # read-only use of app code
    return las


@pytest.mark.parametrize("subset", [s for k in range(4) for s in itertools.combinations((1, 2, 3), k)])
def test_closed_form_equals_compute_dis_criteria(subset):
    las = _app_las()
    mask = np.zeros((40, 40, 40), dtype=np.uint8)
    for k, label in enumerate(subset):                    # one 3x3x3 blob (27 mm³ at 1 mm) per present region
        mask[5 + 10 * k:8 + 10 * k, 5:8, 5:8] = label
    app = las.compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))["dis_met_brain"]
    names = {1: "Periventricular", 2: "Juxtacortical", 3: "Infratentorial"}
    assert implied_dis([names[x] for x in subset]) == app


# ---------------------------------------------------------------- pilot finding: other spellings (PREREG §12, 2026-11-16)
@pytest.mark.parametrize("text, ms, rule", [
    ("The dissemination-in-space status was evaluated and met.", True, "a"),      # seen in a pilot draft
    ("McDonald criteria for dissemination-in-space are fulfilled.", True, "a"),
    ("Spatial dissemination is fulfilled.", True, "a"),
    ("There are 2 peri-ventricular lesions and 1 juxta-cortical lesion.", True, "c"),
    ("| Region | Lesions |\n|---|---|\n| Peri-ventricular | 3 |\n| Infra-tentorial | 1 |", True, "c"),
    ("Dissemination-in-space was not evaluated.", False, None),
    ("Spatial dissemination is not fulfilled.", False, None),
    ("Peri-ventricular: none. Juxta-cortical: 1 lesion.", False, None),
])
def test_other_spellings(text, ms, rule):
    r = c("## Findings\n" + text)
    assert r["ms_suggestive"] is ms
    assert (rule in r["rules"]) if ms else not r["rules"]


@pytest.mark.parametrize("text, expected", [
    ("Dissemination in space was evaluated, and lesions were identified in 2 out of the 3 evaluable brain regions.", True),
    ("Lesions were found in two brain regions.", True),
    ("Lesions were identified in 1 of 3 evaluable brain regions.", False),
    ("Dissemination in space was not met, with lesions in 2 brain regions.", False),
    ("There are 2 periventricular lesions and 1 juxtacortical lesion.", False),       # named: rule (c), not (c')
])
def test_count_only_is_descriptive(text, expected):
    r = c("## Findings\n" + text)
    assert r["count_only"] is expected
    assert not (expected and r["ms_suggestive"])          # (c') never makes a draft MS-suggestive by itself
