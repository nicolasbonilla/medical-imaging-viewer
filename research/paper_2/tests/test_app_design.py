"""E5 (PREREG §12, 2026-11-21): tests on synthetic records only, written before any E5 output. They need the pinned
copy of the application (e559929) and its environment:

    backend/venv/Scripts/python.exe -m pytest research/paper_2/tests/test_app_design.py -q
"""
import asyncio
import copy
import json

import numpy as np
import pytest

from research.paper_2 import app_design as E
from research.paper_2 import app_design_vm as EV
from research.paper_2 import app_pin
from research.paper_2 import app_provider as AP


@pytest.fixture(scope="module")
def A():
    if not app_pin.check(E.APP_ROOT_DEFAULT)["passed"]:
        pytest.skip("the pinned copy of the application (e559929) is not present")
    try:
        return E.app()
    except ImportError as e:                 # another environment than the application's (e.g. agents-benchmark)
        pytest.skip(f"the application's environment is needed: {e}")


@pytest.fixture(scope="module")
def LAS(A):
    from app.services import lesion_analysis_service as las
    return las


def rec_u(scan="wmh_synthetic_1", set_="wmh2017", thickness=("at_least", 3.0), n=3):
    rows = [[j, 50.0 * j, 0.05 * j, "small", "Periventricular"] for j in range(1, n + 1)]
    return {"scan": scan, "arm": "flames_ens", "set": set_, "meta": {"expert_dis": "1", "dis_met": True},
            "views": {"base": {
                "lesions": {"total_count": n, "count_category": "exact", "total_volume_mm3": float(sum(r[1] for r in rows)),
                            "total_volume_ml": float(sum(r[2] for r in rows)),
                            "size_distribution": {"small": n, "medium": 0, "large": 0}, "lesion_table": rows},
                "regions": {"confirmed": False, "lesion_counts": {"Periventricular": n, "Juxtacortical": 0,
                                                                  "Infratentorial": 0, "Deep White Matter": 0}},
                "acquisition": {"slice_thickness": {"state": thickness[0], "at_least_mm": thickness[1]}}}}}


def mask_c():
    """A classified mask (D, H, W), 1-mm voxels: PV and JC lesions of >= 3 mm, a 4-voxel IT lesion of extent 1.4 mm."""
    m = np.zeros((20, 20, 20), np.uint8)
    m[2:5, 2:5, 2:5] = 1                      # periventricular, 27 mm³, extent >= 3 mm
    m[10:13, 10:13, 10:13] = 2                # juxtacortical
    m[16:18, 16:18, 16] = 3                   # infratentorial, 4 mm³, extent sqrt(2) mm: below RC-133's size
    m[6:9, 14:17, 2:5] = 4                    # deep white matter
    return m


def row_c(LAS, m=None):
    m = mask_c() if m is None else m
    sp = (1.0, 1.0, 1.0)
    dis = LAS.compute_dis_criteria(m, voxel_spacing=sp)
    with EV.rc133_off(LAS):
        old = LAS.compute_dis_criteria(m, voxel_spacing=sp)
    la = LAS.analyze_lesions(m, sp, LAS.MAGNIMS_REGIONS)
    return json.loads(json.dumps(EV.jsonable({
        "id": "wmh_synthetic_1", "block": "A", "cohort": "wmh2017", "n_lesions": 4, "dis_rc133": dis,
        "dis_old_met": bool(old["dis_met_brain"]), "lesion_analysis": la,
        "thickness_geometry": {"state": "at_least", "effective_mm": 3.0, "source": "nifti_grid"}})))


# ------------------------------------------------------------------------------------------------ the application
def test_pin_and_production_parameters(A):
    assert A.pin["passed"] and A.pin["app_commit"].startswith("e559929")
    assert A.claude_model == "claude-sonnet-5-5" and A.claude_max_tokens == 4096
    assert A.claude_params == {"thinking": {"type": "between_tools"}, "output_config": {"effort": "low"}}


def test_route_thickness():
    assert E.route_thickness("at_least", 2.4999, 20.0) == {"state": "at_least", "effective_mm": 2.5, "source": "header"}
    assert E.route_thickness("native", 1.0, 20.0)["state"] == "native"
    for st, mm in (("not_determinable", None), ("at_least", 0.0), ("at_least", 25.0), ("at_least", True), (None, 3)):
        assert E.route_thickness(st, mm, 20.0) == {"state": "not_determinable", "effective_mm": None}


def test_state_u_view_is_d4_with_the_production_code(A):
    f = E.findings_u(rec_u(), A)
    view = E.app_view(f, A)
    assert view["dis"]["status"] == "not evaluated"
    assert view["segmentation"]["confirmed_by_radiologist"] is False
    assert "lesion_counts" not in json.dumps(view["regions"])
    assert view["acquisition"]["slice_thickness"]["known_from"] == "grid" and "thick_slice_context" in view["acquisition"]
    first = A.VR.first_user_message(view, "en")
    assert "Periventricular" not in A.VR.record_json(view)
    assert A.G.NOT_EVALUATED_LINE["en"] in first
    res = A.VR.measurements_only(view, "en", A.VR.REASON_BLOCKED)
    d = E.delivered_text(res.text, view, f, A)
    assert d.startswith(A.BRS.REPORT_DISCLAIMERS["en"]) and A.G.AUTOMATIC_MARKING_NOTICE["en"] in d
    fl = E.flags(d, {"code_texts": E.code_texts(view, A)}, A)
    assert not fl["ms"] and not fl["unq"]


def test_state_u_unknown_thickness_says_so(A):
    view = E.app_view(E.findings_u(rec_u(set_="ms", thickness=("not_determinable", None)), A), A)
    assert view["acquisition"]["slice_thickness"]["state"] == "not determinable"
    assert A.VR.THICKNESS_UNKNOWN_CONTEXT in A.VR.assemble(view, "en", "", "")


def test_state_c_view_after_confirmation(A, LAS):
    row = row_c(LAS)
    assert row["dis_rc133"]["dis_met_brain"] is True and row["dis_rc133"]["below_size_lesion_count"] == 1
    assert row["dis_old_met"] is True
    f = E.findings_c(row, A)
    view = E.app_view(f, A)
    assert view["dis"]["status"] == "evaluated" and view["dis"]["dis_met_brain"] is True
    assert view["segmentation"]["confirmed_by_radiologist"] is True
    assert view["regions"]["lesion_counts"] == {"Periventricular": 1, "Juxtacortical": 1, "Infratentorial": 1,
                                                "Deep White Matter": 1}
    assert view["dis"]["lesions_below_size"] == 1 and view["dis"]["interpretation"] == A.VR.DIS_INTERPRETATION["en"]
    text = A.VR.assemble(view, "en", "", "")
    assert "the brain criterion is met" in text and A.VR.DIS_INTERPRETATION["en"] in text
    assert "reviewed_by" not in A.VR.first_user_message(view, "en")


def test_attribution_and_end_points_on_a_confirmed_met_record(A, LAS):
    f = E.findings_c(row_c(LAS), A)
    view = E.app_view(f, A)
    body = A.VR.assemble(view, "en", "The lesions are mostly small, on a confirmed segmentation.",
                         "Lesions in several regions on the confirmed segmentation.")
    d = E.delivered_text(body, view, f, A)
    item = {"code_texts": E.code_texts(view, A)}
    from research.paper_2 import classifier as C
    us = C._units(d, item["code_texts"], E.boilerplate(A))
    disclaimer = " ".join(A.BRS.REPORT_DISCLAIMERS["en"].split())
    for u in us:
        if u["heading"]:
            continue
        if " ".join(u["text"].split()) in disclaimer:
            assert u["source"] == "boilerplate", u["text"]
        elif "mostly small" in u["text"] or "several regions" in u["text"]:
            assert u["source"] == "model"
        else:
            assert u["source"] == "code", u["text"]
    fl = E.flags(d, item, A)
    assert fl["ms"] and fl["unq"] and fl["unq_code"] and not fl["unq_model"]
    assert fl["dis_conveyed"] and fl["clinical_any"] and not fl["ms_no_clinical"]


def test_boilerplate_of_a_not_evaluated_draft_is_never_read(A):
    f = E.findings_u(rec_u(), A)
    view = E.app_view(f, A)
    d = E.delivered_text(A.VR.measurements_only(view, "en", A.VR.REASON_BLOCKED).text, view, f, A)
    from research.paper_2 import classifier as C
    bp = E.boilerplate(A)
    srcs = {u["text"][:30]: u["source"] for u in C._units(d, E.code_texts(view, A), bp) if not u["heading"]}
    assert all(s in ("code", "boilerplate") for s in srcs.values()), srcs
    assert any(t.startswith("> Automatic lesion marking") for t, s in srcs.items() if s == "boilerplate")


# ------------------------------------------------------------------------------------------------ the flow
def items_for(A, LAS):
    u = E.make_item("U", "wmh_synthetic_1", "wmh2017", E.findings_u(rec_u(), A), {"expert_dis": "1"}, A)
    c = E.make_item("C", "wmh_synthetic_2", "wmh2017", E.findings_c(row_c(LAS), A), {"expert_dis": "1"}, A)
    return u, c


def fake(answers, log):
    """A dispatch that answers each call key with the next text of `answers[record key]` (Gemini-shaped)."""
    seen = {}

    def dispatch(alias, run_dir, items, n):
        log.append([k for k, _ in items])
        out = {}
        for k, req in items:
            rk = k.split("#")[0]
            i = seen.get(rk, 0)
            seen[rk] = i + 1
            a = answers[rk][min(i, len(answers[rk]) - 1)]
            if a == "ERROR":
                out[k] = {"error": "HTTP 503"}
            elif a == "SAFETY":
                out[k] = {"text": "", "stop_reason": "finishreason.safety", "usage": {}}
            elif alias == "sonnet":
                out[k] = {"message": {"content": [{"type": "text", "text": a}], "stop_reason": "end_turn",
                                      "model": "claude-sonnet-5-5", "usage": {"input_tokens": 1000, "output_tokens": 50}},
                          "usage": {"input_tokens": 1000, "output_tokens": 50}, "stop_reason": "end_turn", "req": req}
            else:
                out[k] = {"text": a, "stop_reason": "finishreason.stop",
                          "usage": {"prompt_token_count": 1000, "candidates_token_count": 50}}
        return out
    return dispatch


GOOD = "[FINDINGS_COMMENT]\nThe marked lesions are mostly small.\n[IMPRESSION_COMMENT]\nThe measurements above summarise the marking."
BAD = "[FINDINGS_COMMENT]\nThere are 3 lesions.\n[IMPRESSION_COMMENT]\nSummary."


def test_flow_regenerates_in_rounds_and_records_everything(A, LAS, tmp_path):
    u, c = items_for(A, LAS)
    log = []
    rows, broker = asyncio.run(E.run_items([u, c], "gemini", tmp_path, A, fake({u["key"]: [GOOD], c["key"]: [BAD, GOOD]},
                                                                                 log)))
    by = {r["key"]: r for r in rows}
    assert by[u["key"]]["result"]["outcome"] == "passed_0" and by[c["key"]]["result"]["outcome"] == "passed_1"
    assert len(log) == 2 and len(log[0]) == 2 and len(log[1]) == 1          # round 1: both; round 2: the regeneration
    assert by[c["key"]]["n_calls"] == 2 and not E.failed_delivery(by[c["key"]])
    assert "The marked lesions are mostly small." in by[c["key"]]["result"]["delivered"]


def test_claude_requests_are_the_services_call(A, LAS, tmp_path):
    u, _ = items_for(A, LAS)
    sent = []

    def dispatch(alias, run_dir, items, n):
        sent.extend(items)
        return fake({u["key"]: [GOOD]}, [])(alias, run_dir, items, n)
    rows, _ = asyncio.run(E.run_items([u], "sonnet", tmp_path, A, dispatch))
    _, req = sent[0]
    assert set(req) == {"model", "max_tokens", "system", "messages", "thinking", "output_config"}
    assert req["model"] == "claude-sonnet-5-5" and req["max_tokens"] == 4096 and req["system"] == A.VR.SYSTEM_PROMPT
    assert req["thinking"] == {"type": "between_tools"} and req["output_config"] == {"effort": "low"}
    assert req["messages"] == [{"role": "user", "content": A.VR.first_user_message(u["view"], "en")}]
    assert rows[0]["result"]["outcome"] == "passed_0" and rows[0]["usd"] > 0


def test_provider_error_is_a_failed_delivery_and_refusal_is_not(A, LAS, tmp_path):
    u, c = items_for(A, LAS)
    rows, _ = asyncio.run(E.run_items([u, c], "gemini", tmp_path, A, fake({u["key"]: ["ERROR"], c["key"]: ["SAFETY"]}, [])))
    by = {r["key"]: r for r in rows}
    assert E.failed_delivery(by[u["key"]]) and by[u["key"]]["result"]["interpretive"] == "withheld"
    assert by[c["key"]]["result"]["reason"] == A.VR.REASON_REFUSAL and not E.failed_delivery(by[c["key"]])
    p = tmp_path / "results.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert E.done_keys(p) == {c["key"]}


def test_cap_stop_sends_nothing(A, LAS, tmp_path, monkeypatch):
    u, c = items_for(A, LAS)
    monkeypatch.setitem(E.AMENDMENT_LIMIT, "gemini", 0.0)
    log = []
    rows, broker = asyncio.run(E.run_items([u, c], "gemini", tmp_path, A, fake({u["key"]: [GOOD], c["key"]: [GOOD]}, log)))
    assert rows == [] and log == [] and "amendment" in broker.stop


def test_gemini_stop_mapping():
    assert E.gemini_stop("max_tokens") == "max_tokens"
    assert E.gemini_stop("FinishReason.SAFETY") == "refusal" and E.gemini_stop("finishreason.prohibited_content") == "refusal"
    assert E.gemini_stop("finishreason.stop") == "finishreason.stop"


def test_pilot_draw_is_seeded_and_two_per_cohort():
    scans = {"wmh2017": [f"w{i:03d}" for i in range(170)], "ms": [f"m{i:03d}" for i in range(123)]}
    p1, p2 = E.pilot_scans(scans), E.pilot_scans({k: list(reversed(v)) for k, v in scans.items()})
    assert p1 == p2 and len(p1) == 4 and sum(s.startswith("w") for s in p1) == 2


def test_rc133_off_is_the_rule_before_rc133(A, LAS):
    m = np.zeros((20, 20, 20), np.uint8)
    m[2:4, 2:4, 2] = 1                       # PV: 4 mm³, extent 1.4 mm (below RC-133's 3 mm)
    m[10:13, 10:13, 10:13] = 2               # JC: 27 mm³
    assert LAS.compute_dis_criteria(m, voxel_spacing=(1.0, 1.0, 1.0))["dis_met_brain"] is False
    with EV.rc133_off(LAS):
        assert LAS.compute_dis_criteria(m, voxel_spacing=(1.0, 1.0, 1.0))["dis_met_brain"] is True
    assert LAS.compute_dis_criteria(m, voxel_spacing=(1.0, 1.0, 1.0))["dis_met_brain"] is False   # restored


def test_provider_batch_bodies_unchanged():
    items = [("k1", {"model": "claude-sonnet-5-5", "max_tokens": 4096, "system": "s", "messages": []}), ("k2", {"x": 1})]
    reqs, ids = AP.batch_requests(items)
    assert [r["params"] for r in reqs] == [b for _, b in items] and set(ids.values()) == {"k1", "k2"}


def test_cohort_summary_shapes(A):
    rows = [dict(ms=i % 2 == 0, unq=i % 2 == 0, unq_code=True, unq_model=False, ms_model=False, unq_automat=False,
                 ms_no_clinical=False, unq_dis_met=True, sens_ms=True, sens_unq=True, withheld=False, clinical_any=True,
                 clinical_model=False, provenance_any=True, outcome="passed_0", reason=None, unq_rules=["a"],
                 patient=f"mslesseg_P{i // 2}", expert_dis_met=True, app_dis_met=True, dis_conveyed=True,
                 dis_conveyed_unq=True) for i in range(6)]
    s = E.summarise_cohort(rows, True)
    assert s["ms"]["x"] == 3 and s["ms_coverage_among_app_met"]["n"] == 6 and "ci95_cluster_exact" in s["ms_cluster"]
