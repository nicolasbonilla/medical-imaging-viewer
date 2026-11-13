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


# Third review of PR #78 (T5, DRAFT): the two tests of the retired findings prompt's own wording ("1 lesion" /
# "N lesions") were archived with it (docs/archive/retired_report_prompt.py). The verified report writes counts in
# fixed "label: number" lines ("Lesions marked: 1", "periventricular: 1"), with no counted noun after a number.
def test_release_plural_the_verified_report_puts_no_counted_noun_after_a_number():
    from app.services import verified_report as VR
    for count in (0, 1, 2, 17):
        view = VR.build_view({"lesion_analysis": {"total_count": count}}, None, "en")
        report = VR.assemble(view, "en", "", "")
        assert not re.search(r"\b1 lesions\b", report) and f"Lesions marked: {count} " in report


@pytest.mark.parametrize("confirmed", [True, False])
@pytest.mark.parametrize("count,n_lesions", [(1, 1), (1, 3), (2, 1), (2, 3)])
def test_release_plural_both_forms_stay_in_the_devices_own_words(count, n_lesions, confirmed):
    """RC-065 tripwire: the counted noun, singular or plural, is among the device's own words and word pairs (pairs
    across two optional blocks, e.g. ("ml", "individual") without a size distribution, are not the point here).

    Amended for the second review of PR #78 (G, DRAFT): the device's own words are those of the text it sends NOW —
    the verified report's first request — so that request is the one checked here (the retired findings prompt above
    is no longer sent, and its words are no longer exempt)."""
    from app.services import verified_report as VR
    from app.services.report_payload_guard import provider_payload
    findings = _findings(dwm_count=count, pv_count=count, n_lesions=n_lesions, tp1=count, tp2=count,
                         confirmed=confirmed)
    if confirmed:
        findings["dis_assessment"] = {"evaluation_status": "evaluated", "dis_met": count > 1,
                                      "regions_with_lesions": count, "total_dis_regions": 5}
    f, v, not_included = VR.rendered_request(findings, None)
    p = provider_payload(f, v)
    view = VR.build_view(p.findings, p.volumetry, "en", not_included=not_included)
    words = words_of(VR.first_user_message(view, "en"))
    assert set(words) <= brs.fixed_prompt_words()
    counted = {p for p in zip(words, words[1:]) if {"lesion", "lesions"} & set(p)}
    assert counted and counted <= brs.fixed_prompt_pairs()
