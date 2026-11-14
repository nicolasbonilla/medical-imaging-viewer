"""The scenario matrix's input dimensions (eighth review of PR #78; moved out of the Class C module with the eleventh
review, C4). Test-only: the product keeps its own minimal enumeration (`verified_report._BRANCHES`) for the RC-065
device-word list, and test_verified_report_review11 checks that every value here is one of those. DRAFT, PENDING owner
approval."""
from typing import Any, Dict, List, Optional, Tuple

_SC_EVALUATED = {"evaluation_status": "evaluated", "regions_with_lesions": 2, "total_dis_regions": 5,
                 "region_details": {"Periventricular": {"present": True}, "Juxtacortical": {"present": True},
                                    "Infratentorial": {"present": False}}}
_SC_LNG = {"burden_tp1_ml": 1.0, "burden_tp2_ml": 1.4, "total_lesions_tp1": 3, "total_lesions_tp2": 9,
           "burden_delta_percent": 40.0, "abstained": False, "new_lesion_min_diameter_mm": 3}
SCENARIO: Dict[str, Dict[str, Any]] = {
    "lesion": {"absent": None,
               "not_available": {"total_count": None, "total_burden_mm3": None, "total_burden_ml": None},
               "computed": {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
                            "size_distribution": {"small": 4, "medium": 2, "large": 1}}},
    "dis": {"absent": None, "not_evaluated": {"evaluation_status": "not_evaluated"},
            "evaluated_met": {**_SC_EVALUATED, "dis_met": True}, "evaluated_not_met": {**_SC_EVALUATED, "dis_met": False}},
    "longitudinal": {
        "absent": None,
        "complete": {**_SC_LNG, "status_counts": {"new": 2, "enlarged": 1, "resolved": 0, "shrunk": 0, "stable": 3},
                     "change_candidates": {"new": 2, "enlarging": 1, "total": 3}},
        "null_counts": {**_SC_LNG, "status_counts": {"new": 2, "enlarged": 1, "resolved": 0, "shrunk": 0, "stable": 3},
                        "change_candidates": {"new": None, "enlarging": 1, "total": 1}},
        "small_new": {**_SC_LNG, "status_counts": {"new": 5, "enlarged": 1, "resolved": 0, "shrunk": 0, "stable": 3},
                      "change_candidates": {"new": 2, "enlarging": 1, "total": 3}},
    },
    "volumetry": {"absent": None, "present": {"total_brain_volume_ml": 1100.0, "intracranial_volume_ml": 1450.0}},
    "source": {"automatic": "ai_draft", "manual": "manual", "not_recorded": "origin_not_recorded"},
    "entry": {"none": {}, "indication": {"clinical_indication": "follow-up"}, "technique": {"technique": "3T"},
              "observations": {"additional_observations": "motion"}},
}
SCENARIO_BASE = {"lesion": "computed", "dis": "not_evaluated", "longitudinal": "complete", "volumetry": "present",
                 "source": "automatic", "entry": "none"}


def scenario_request(case: Dict[str, str]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """The report request (findings, volumetry) of one scenario case."""
    findings: Dict[str, Any] = dict(SCENARIO["entry"][case["entry"]])
    if SCENARIO["lesion"][case["lesion"]] is not None:
        findings["lesion_analysis"] = dict(SCENARIO["lesion"][case["lesion"]])
    if SCENARIO["dis"][case["dis"]] is not None:
        findings["dis_assessment"] = {**SCENARIO["dis"][case["dis"]],
                                      "segmentation_review": {"source": SCENARIO["source"][case["source"]]}}
    if SCENARIO["longitudinal"][case["longitudinal"]] is not None:
        findings["longitudinal"] = SCENARIO["longitudinal"][case["longitudinal"]]
    return findings, SCENARIO["volumetry"][case["volumetry"]]


def scenario_covering_cases() -> List[Dict[str, str]]:
    """Every value of every dimension, each on the base case (with the entries also on a DIS-evaluated case)."""
    out = [dict(SCENARIO_BASE)]
    for dim, values in SCENARIO.items():
        for value in values:
            if value != SCENARIO_BASE[dim]:
                out.append({**SCENARIO_BASE, dim: value})
    for value in SCENARIO["entry"]:
        out.append({**SCENARIO_BASE, "dis": "evaluated_met", "entry": value})
    return out
