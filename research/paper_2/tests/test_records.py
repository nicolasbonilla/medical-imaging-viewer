"""Tests of the record builder (PREREG §2), on synthetic paper-1 outputs."""
import csv
import json
import re

from research.paper_2 import designs as D
from research.paper_2 import records as R
from research.paper_2.classifier import classify

SETS = {"C1_ms_iso": {"mslesseg_P1_T1": {"flames_contaminated": False}, "ljub_1": {"flames_contaminated": True}}}

UNITS = [  # id, block, T, arm, available, gr_pass, n, dis, any_dis_region, expert_dis
    ("wmh_x_1", "A", 3.0, "flames_ens", 1, 1, 3, 1, 1, 1),
    ("wmh_x_1", "A", 3.0, "lstai", 1, 1, 1, 0, 1, 1),
    ("wmh_x_1", "A", 3.0, "mindglide", 0, 1, "", "", "", 1),          # not available -> no record
    ("wmh_x_2", "A", 3.0, "flames_ens", 1, 0, 2, 0, 0, 0),            # GR failure
    ("sub-1", "B", 2.5, "flames_ens", 1, 1, 2, 0, 1, ""),
    ("sub-001", "C2", 1.0, "flames_ens", 1, 1, 4, 1, 1, ""),           # recount mismatch below
    ("sub-001_th7", "C2", 7.0, "flames_ens", 1, 1, 1, 0, 0, ""),       # simulated thickness -> excluded
    ("mslesseg_P1_T1", "C1", 1.0, "flames_ens", 1, 1, 2, 1, 1, 1),
    ("ljub_1", "C1", 1.0, "lstai", 1, 1, 1, 0, 1, 1),                  # FLAMeS-contaminated scan -> excluded
]
LESIONS = [
    ("wmh_x_1", "A", "flames_ens", 1, 120.0, "PV"), ("wmh_x_1", "A", "flames_ens", 2, 40.0, "JC"),
    ("wmh_x_1", "A", "flames_ens", 3, 2000.0, "DWM"), ("wmh_x_1", "A", "lstai", 1, 50.0, "PV"),
    ("wmh_x_2", "A", "flames_ens", 1, 10.0, "PV"), ("wmh_x_2", "A", "flames_ens", 2, 10.0, "IT"),
    ("sub-1", "B", "flames_ens", 1, 8.0, "PV"), ("sub-1", "B", "flames_ens", 2, 9.0, "DWM"),
    # sub-001: the app says DIS met, but the per-lesion recount finds only PV (+ a 2 mm³ JC speck below the rule's size)
    ("sub-001", "C2", "flames_ens", 1, 30.0, "PV"), ("sub-001", "C2", "flames_ens", 2, 2.0, "JC"),
    ("sub-001", "C2", "flames_ens", 3, 5.0, "DWM"), ("sub-001", "C2", "flames_ens", 4, 6.0, "none"),
    ("mslesseg_P1_T1", "C1", "flames_ens", 1, 300.0, "PV"), ("mslesseg_P1_T1", "C1", "flames_ens", 2, 90.0, "IT"),
]


def _write(tmp_path):
    pu, le = tmp_path / "per_unit.csv", tmp_path / "lesions.csv"
    with open(pu, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "block", "base", "T", "arm", "available", "gr_pass", "n_lesions", "dis", "dis_pv3",
                    "any_dis_region", "vol_mm3", "f1", "recall", "precision", "false_lesions", "n_ref", "expert_dis"])
        for (i, b, t, a, av, gr, n, dis, anyr, ed) in UNITS:
            w.writerow([i, b, i.split("_th")[0], t, a, av, gr, n, dis, "", anyr, "", "", "", "", "", "", ed])
    with open(le, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "block", "arm", "lesion", "vol_mm3", "region"])
        w.writerows(LESIONS)
    return str(pu), str(le)


def _build(tmp_path, geometry=None):
    units, les = R.load(*_write(tmp_path), SETS)
    return units, R.build(units, les, geometry)


def by(recs, scan, arm):
    return next(r for r in recs if r["scan"] == scan and r["arm"] == arm)


def test_selection(tmp_path):
    units, recs = _build(tmp_path)
    keys = {(r["scan"], r["arm"]) for r in recs}
    assert keys == {("wmh_x_1", "flames_ens"), ("wmh_x_1", "lstai"), ("wmh_x_2", "flames_ens"), ("sub-1", "flames_ens"),
                    ("sub-001", "flames_ens"), ("mslesseg_P1_T1", "flames_ens")}
    assert {r["set"] for r in recs} == {"wmh2017", "dlbs", "sibbms", "ms"}


def test_view_content_and_blinding(tmp_path):
    _, recs = _build(tmp_path)
    r = by(recs, "wmh_x_1", "flames_ens")
    v = r["views"]["base"]
    assert v["lesions"]["total_count"] == 3 and v["lesions"]["size_distribution"] == {"small": 1, "medium": 1, "large": 1}
    assert v["regions"]["lesion_counts"]["Periventricular"] == 1 and v["regions"]["confirmed"] is False
    assert v["dis"]["status"] == "evaluated" and v["dis"]["dis_met_brain"] is True and v["dis"]["brain_regions_with_lesions"] == 2
    for rec in recs:
        for view in rec["views"].values():
            s = json.dumps(view).lower()
            assert rec["scan"].lower() not in s
            for word in ("wmh", "dlbs", "sibbms", "healthy", "controls?", "mslesseg", "mimics?", "age", "years?"):
                assert not re.search(r"\b" + word + r"\b", s), word


def test_gr_failure_withholds_dis(tmp_path):
    _, recs = _build(tmp_path)
    v = by(recs, "wmh_x_2", "flames_ens")["views"]["base"]
    assert v["dis"]["status"] == "not evaluated" and "registered" in v["dis"]["reason"]
    assert "lesion_counts" not in v["regions"]


def test_recount_mismatch_follows_the_app(tmp_path):
    _, recs = _build(tmp_path)
    r = by(recs, "sub-001", "flames_ens")
    v = r["views"]["base"]
    assert r["meta"]["recount_mismatch"] is True
    assert v["dis"]["dis_met_brain"] is True and v["dis"]["brain_regions_with_lesions"] == 2


def test_d4_and_pairing(tmp_path):
    _, recs = _build(tmp_path)
    r = by(recs, "wmh_x_1", "flames_ens")
    assert r["views"]["d4"]["dis"]["status"] == "not evaluated" and "lesion_counts" not in r["views"]["d4"]["regions"]
    assert r["meta"]["pair_arm"] == "lstai"
    second = r["views"]["d2"]["second_segmentation"]
    assert second["tool"] == "LST-AI" and second["lesion_count"] == 1 and second["dis"]["dis_met_brain"] is False
    assert by(recs, "wmh_x_1", "lstai")["meta"]["pair_arm"] == "flames_ens"
    assert by(recs, "sub-1", "flames_ens")["views"]["d2"]["second_segmentation"]["available"] is False
    assert len({v["record_id"] for v in r["views"].values()}) == 3


def test_g1_passes(tmp_path):
    units, recs = _build(tmp_path)
    g = R.gate_g1(recs, units)
    assert g["passed"], g


def test_thick_context_from_geometry(tmp_path):
    geo = {"wmh_x_1": 3.0, "sub-1": 2.5, "sub-001": 1.0}
    _, recs = _build(tmp_path, geometry=lambda uid: {"segmented_sequence": "FLAIR", "series_description": "FLAIR",
                                                      "slice_thickness": {"state": "at_least",
                                                                          "at_least_mm": geo.get(uid)}})
    assert "thick_slice_context" in by(recs, "wmh_x_1", "flames_ens")["views"]["base"]["acquisition"]
    assert "thick_slice_context" in by(recs, "sub-1", "flames_ens")["views"]["base"]["acquisition"]
    assert "thick_slice_context" not in by(recs, "sub-001", "flames_ens")["views"]["base"]["acquisition"]


def test_built_record_runs_through_d3_and_the_classifier(tmp_path):
    _, recs = _build(tmp_path)
    v = by(recs, "wmh_x_1", "flames_ens")["views"]["base"]
    job = D.D3({"record_id": v["record_id"], "view": v, "meta": {}, "a0": None})
    job.next_request()
    job.consume({"text": "[FINDINGS_COMMENT]\nThe marking is automatic.\n[IMPRESSION_COMMENT]\nFor review.", "usage": {}})
    assert job.result["a3_outcome"] == "passed_0", job.attempts
    r = classify(job.result["delivered"], code_texts=job.code_texts(), boilerplate=D.BOILERPLATE)
    assert r["ms_suggestive"] and r["unqualified"]
