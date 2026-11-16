"""Tests of design D5's record views and of consensus_eval's gate and writer (offline, synthetic, no app import)."""
import csv
import json

from research.paper_2 import consensus_eval as CE
from research.paper_2 import designs as D
from research.paper_2 import records as R
from research.paper_2 import runner as RN
from research.paper_2.classifier import classify
from research.paper_2.tests.test_records import _build, by

CONS_UNITS = [  # id, block, arm, available, gr_pass, n, dis, any_dis_region, n_single
    ("wmh_x_1", "A", "d5_primary", 1, 1, 1, 0, 1, 2),        # LST-AI keeps only the PV lesion: DIS no longer met
    ("wmh_x_1", "A", "d5_k2", 1, 1, 2, 1, 1, 1),
    ("wmh_x_1", "A", "d5_k3", 0, 1, "", "", "", ""),
    ("sub-1", "B", "d5_primary", 0, 1, "", "", "", ""),        # no LST-AI on this scan: excluded and counted
    ("mslesseg_P1_T1", "C1", "d5_primary", 1, 1, 2, 1, 1, 0),
]
CONS_LESIONS = [("wmh_x_1", "A", "d5_primary", 1, 120.0, "PV"),
                ("wmh_x_1", "A", "d5_k2", 1, 120.0, "PV"), ("wmh_x_1", "A", "d5_k2", 2, 40.0, "JC"),
                ("mslesseg_P1_T1", "C1", "d5_primary", 1, 300.0, "PV"), ("mslesseg_P1_T1", "C1", "d5_primary", 2, 90.0, "IT")]


def _consensus(tmp_path):
    pu, le = tmp_path / "consensus_per_unit.csv", tmp_path / "consensus_lesions.csv"
    with open(pu, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "block", "base", "T", "arm", "available", "gr_pass", "n_lesions", "dis", "dis_pv3",
                    "any_dis_region", "vol_mm3", "n_single", "n_native_agreed", "n_native_single"])
        for (i, b, a, av, gr, n, dis, anyr, ns) in CONS_UNITS:
            w.writerow([i, b, i, 1.0, a, av, gr, n, dis, "", anyr, "", ns, "", ""])
    with open(le, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "block", "arm", "lesion", "vol_mm3", "region"])
        w.writerows(CONS_LESIONS)
    return R.load_consensus(str(pu), str(le))


def _with_d5(tmp_path):
    _, recs = _build(tmp_path)
    cu, cl = _consensus(tmp_path)
    return recs, R.attach_d5(recs, cu, cl)


def test_attach_d5_views_and_counts(tmp_path):
    recs, n = _with_d5(tmp_path)
    assert n["d5"] == 2 and n["excluded_no_lstai"] == 3 and n["d5_k2"] == 1 and n["d5_k3"] == 0   # wmh_x_2, sub-1, sub-001
    r = by(recs, "wmh_x_1", "flames_ens")
    v = r["views"]["d5"]
    assert v["lesions"]["total_count"] == 1 and v["single_tool_candidates"] == 2
    assert v["dis"]["dis_met_brain"] is False and v["regions"]["lesion_counts"]["Periventricular"] == 1
    assert "LST-AI" in v["segmentation"]["tool"] and v["record_id"] not in {x["record_id"] for k, x in r["views"].items()
                                                                            if k != "d5"}
    assert r["meta"]["d5_dis_met"] is False and r["meta"]["d5_single"] == 2
    assert r["views"]["d5_k2"]["dis"]["dis_met_brain"] is True
    assert "d5" not in by(recs, "sub-1", "flames_ens")["views"]
    assert "d5" not in by(recs, "wmh_x_1", "lstai")["views"]                  # only FLAMeS-ens records get D5


def test_d5_job_writes_the_candidate_line_and_the_classifier_ignores_it(tmp_path):
    recs, _ = _with_d5(tmp_path)
    rec = by(recs, "mslesseg_P1_T1", "flames_ens")
    job = RN.make_job(rec, "D5")
    assert job is not None
    job.next_request()
    job.consume({"text": "[FINDINGS_COMMENT]\nThe marking is automatic.\n[IMPRESSION_COMMENT]\nFor review.", "usage": {}})
    text = job.result["delivered"]
    assert D.CANDIDATE_LINE.format(n=0) in text and "LST-AI also marks them" in text
    r = classify(text, code_texts=job.code_texts(), boilerplate=D.BOILERPLATE)
    assert r["ms_suggestive"]                                                   # agreed PV + IT: DIS met, stated by code


def test_gate_identity_detects_any_difference():
    pu = {"s1": {"n_lesions": "2", "dis": "1", "dis_pv3": "0", "any_dis_region": "1"}}
    les = {"s1": [[10.0, "PV"], [5.5, "JC"]]}
    ok = {"id": "s1", "gr_pass": True, "rows": {"identity": {"n": 2, "dis": True, "dis_pv3": False, "any_dis_region": True,
                                                             "lesions": [[5.5, "JC"], [10.0, "PV"]]}}}
    assert CE.gate_identity([ok], pu, les)["passed"]
    off = json.loads(json.dumps(ok))
    off["rows"]["identity"]["lesions"][0] = [5.5, "DWM"]
    g = CE.gate_identity([off], pu, les)
    assert not g["passed"] and g["mismatches"][0]["lesions_equal"] is False
    assert not CE.gate_identity([], pu, les)["passed"]                          # nothing compared is not a pass


def test_writer_keeps_unavailable_variants(tmp_path):
    rec = {"id": "s1", "block": "B", "base": "s1", "T": 2.5, "gr_pass": True,
           "rows": {"d5_primary": {"available": True, "n": 1, "dis": False, "dis_pv3": False, "any_dis_region": True,
                                   "vol_mm3": 12.34, "n_single": 3, "n_native_agreed": 1, "n_native_single": 3,
                                   "lesions": [[12.34, "PV"]]}}}
    CE.write([rec], str(tmp_path))
    rows = list(csv.DictReader(open(tmp_path / "consensus_per_unit.csv", newline="")))
    assert [r["arm"] for r in rows] == list(CE.VARIANTS)
    assert rows[0]["available"] == "1" and rows[0]["n_single"] == "3" and rows[1]["available"] == "0"
    cu, cl = R.load_consensus(str(tmp_path / "consensus_per_unit.csv"), str(tmp_path / "consensus_lesions.csv"))
    assert cl[("s1", "d5_primary")] == [(12.34, "PV")]


def test_planned_counts_d5_only_where_its_view_exists(tmp_path):
    recs, _ = _with_d5(tmp_path)
    d5 = [(r["scan"], r["arm"]) for r, d in RN.planned(recs, "gemini") if d == "D5"]
    assert ("wmh_x_1", "flames_ens") in d5 and all(arm == "flames_ens" for _, arm in d5)
    assert ("sub-1", "flames_ens") not in d5                                    # no LST-AI: no D5 job


class _SpyPF:
    """Records the prediction it is given; the real metrics module (paper F) is used on the VM."""
    def __init__(self):
        self.pred = None

    def lesion_metrics(self, pred, ref, zooms):
        self.pred = pred.copy()
        return {"n_ref": 2, "n_pred": int(pred.sum()), "tp_ref": 1, "tp_pred": 1, "false_lesions": 0, "f1": 0.5,
                "dice": 0.1}

    def components(self, pred, zooms):
        self.pred = pred.copy()
        return None, int(pred.sum()), None


def test_accuracy_uses_paper1_threshold_and_leaves_label_2_out():
    import numpy as np
    kept = np.array([1, 1, 1, 0, 1], bool)                  # the variant's components (map >= 0.5)
    strict = np.array([1, 0, 1, 1, 1], bool)                # FLAMeS-ens map > 0.5
    ref = np.array([1, 0, 0, 0, 1], bool)
    other = np.array([0, 0, 1, 0, 0], bool)                 # WMH 2017 label 2
    pf = _SpyPF()
    out = CE.accuracy(kept, strict, ref, other, (1, 1, 1), pf)
    assert pf.pred.tolist() == [True, False, False, False, True] and set(out) == set(CE.ACC_KEYS)
    out = CE.accuracy(kept, strict, None, None, (1, 1, 1), pf)               # B and C2: the count only
    assert out == {"n_pred": 3} and pf.pred.tolist() == [True, False, True, False, True]


def test_gate_accuracy_compares_with_paper1():
    pu = {"s1": {"n_ref": "4", "false_lesions": "3", "f1": "0.6667"}, "b1": {}}
    ok = {"id": "s1", "rows": {"identity": {"acc": {"n_ref": 4, "false_lesions": 3, "f1": 2 / 3}}}}
    healthy = {"id": "b1", "rows": {"identity": {"acc": {"n_pred": 5}}}}             # no reference: not compared
    g = CE.gate_accuracy([ok, healthy], pu)
    assert g["passed"] and g["compared"] == 1
    off = json.loads(json.dumps(ok))
    off["rows"]["identity"]["acc"]["false_lesions"] = 2
    assert not CE.gate_accuracy([off], pu)["passed"]
    assert not CE.gate_accuracy([healthy], pu)["passed"]                         # nothing compared is not a pass


def test_accuracy_writer(tmp_path):
    rec = {"id": "s1", "block": "C1", "rows": {
        "identity": {"acc": {"n_ref": 4, "n_pred": 5, "tp_ref": 3, "tp_pred": 3, "false_lesions": 2, "f1": 2 / 3}},
        "d5_primary": {"acc": {"n_ref": 4, "n_pred": 3, "tp_ref": 3, "tp_pred": 3, "false_lesions": 0, "f1": 6 / 7}}}}
    healthy = {"id": "b1", "block": "B", "rows": {"identity": {"acc": {"n_pred": 5}}, "d5_primary": {"acc": {"n_pred": 2}}}}
    CE.write_accuracy([rec, healthy], str(tmp_path))                  # count-only rows (B, C2) have no F1
    rows = list(csv.DictReader(open(tmp_path / "consensus_accuracy.csv", newline="")))
    assert [r["arm"] for r in rows] == ["flames_ens", "d5_primary"] * 2
    assert rows[0]["f1"] == "0.6667" and rows[1]["false_lesions"] == "0"
    assert rows[3]["n_pred"] == "2" and rows[3]["f1"] == "" and rows[3]["n_ref"] == ""
