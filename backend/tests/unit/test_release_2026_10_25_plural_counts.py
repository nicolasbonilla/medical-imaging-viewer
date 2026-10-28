"""Release 2026-10-25 — film capture of the release build (2026-10-28): "DWM: 1 lesions".

The region summary in the sidebar showed "DWM: 1 lesions", and the report text had the same pattern: the findings
prompt (Class C `brain_report_service.py`) gives the model "Deep White Matter: 1 lesions, …", "Individual lesion data
(1 lesions)" and "TP1 burden: … (1 lesions)", and the model copies it. A count of exactly one is singular, any other
count plural. The CAPA-014 tripwire's allow-list of the device's own words and word pairs must keep both forms.

Written BEFORE the correction (fails on 21b0df8). Nothing reaches a store, a cloud service or a model (PRB-002).
"""
import re

import pytest

from app.services import brain_report_service as brs
from app.services.report_payload_guard import words_of

_PV, _DWM = "Periventricular", "Deep White Matter"


def _lesion(i, region):
    return {"id": i, "region": region, "volume_mm3": 36.0, "volume_ml": 0.036, "size_category": "small",
            "centroid": {"z": 3, "y": 3, "x": 3}}


def _findings(dwm_count, pv_count, n_lesions, tp1, tp2, confirmed=True):
    return {
        "lesion_analysis": {
            "regions_confirmed": confirmed,
            "total_count": n_lesions, "total_burden_mm3": 36.0 * n_lesions, "total_burden_ml": 0.036 * n_lesions,
            "regions": {_PV: {"lesion_count": pv_count, "total_volume_mm3": 36.0, "total_volume_ml": 0.036},
                        _DWM: {"lesion_count": dwm_count, "total_volume_mm3": 36.0, "total_volume_ml": 0.036}},
            "lesions": [_lesion(i + 1, _PV) for i in range(n_lesions)],
        },
        "longitudinal": {"burden_tp1_ml": 0.036, "burden_tp2_ml": 0.072, "total_lesions_tp1": tp1,
                         "total_lesions_tp2": tp2},
    }


def _prompt(findings):
    builder = brs.BrainReportService.__new__(brs.BrainReportService)
    return builder._build_findings_prompt(findings, None, "en")


def test_release_plural_a_count_of_one_is_singular_in_the_findings_prompt():
    prompt = _prompt(_findings(dwm_count=1, pv_count=1, n_lesions=1, tp1=1, tp2=1))
    assert f"    - {_DWM}: 1 lesion, " in prompt
    assert f"    - {_PV}: 1 lesion, " in prompt
    assert "Individual lesion data (1 lesion):" in prompt
    assert "(1 lesion)" in prompt.split("TP1 burden:")[1].splitlines()[0]
    assert "(1 lesion)" in prompt.split("TP2 burden:")[1].splitlines()[0]
    assert not re.search(r"\b1 lesions\b", prompt)


@pytest.mark.parametrize("count", [0, 2, 17])
def test_release_plural_any_other_count_is_plural_in_the_findings_prompt(count):
    prompt = _prompt(_findings(dwm_count=count, pv_count=count, n_lesions=max(count, 2), tp1=count, tp2=count))
    assert f"    - {_DWM}: {count} lesions, " in prompt
    assert f"Individual lesion data ({max(count, 2)} lesions):" in prompt
    assert f"({count} lesions)" in prompt.split("TP1 burden:")[1].splitlines()[0]


@pytest.mark.parametrize("confirmed", [True, False])
@pytest.mark.parametrize("count,n_lesions", [(1, 1), (1, 3), (2, 1), (2, 3)])
def test_release_plural_both_forms_stay_in_the_devices_own_words(count, n_lesions, confirmed):
    """RC-065 tripwire: the counted noun, singular or plural, is among the device's own words and word pairs (pairs
    across two optional blocks, e.g. ("ml", "individual") without a size distribution, are not the point here)."""
    words = words_of(_prompt(_findings(dwm_count=count, pv_count=count, n_lesions=n_lesions, tp1=count, tp2=count,
                                       confirmed=confirmed)))
    assert set(words) <= brs.fixed_prompt_words()
    counted = {p for p in zip(words, words[1:]) if {"lesion", "lesions"} & set(p)}
    assert counted and counted <= brs.fixed_prompt_pairs()
