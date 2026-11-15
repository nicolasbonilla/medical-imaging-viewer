"""Tests of the paper-2 designs (PREREG §3), offline, with scripted model answers."""
import copy
import json

from research.agents_benchmark import verifier as V
from research.agents_benchmark.tests.test_verifier import BASE
from research.paper_2 import designs as D
from research.paper_2.classifier import classify

COUNTS = {"Periventricular": 3, "Juxtacortical": 2, "Infratentorial": 0, "Deep White Matter": 2}
VOLS = {"Periventricular": 2.0, "Juxtacortical": 0.6, "Infratentorial": 0.0, "Deep White Matter": 0.532}


def honest(tool="FLAMeS, mean of 5 models", dis_met=True, second=None):
    v = copy.deepcopy(BASE)
    v["segmentation"] = {"source": f"automatic AI lesion marking ({tool}), not reviewed", "tool": tool,
                         "confirmed_by_radiologist": False, "segmentation_source": "automatic, unreviewed"}
    v["regions"] = {"confirmed": False, "source": "automatic, unreviewed (computed on the AI marking)",
                    "lesion_counts": dict(COUNTS), "volumes_ml": dict(VOLS)}
    v["dis"] = {"status": "evaluated", "basis": "automatic, unreviewed AI marking", "dis_met_brain": dis_met,
                "brain_regions_with_lesions": 2 if dis_met else 1, "brain_regions_evaluable": 3,
                "total_topographies": 5, "region_presence": {"Periventricular": True, "Juxtacortical": dis_met,
                                                             "Infratentorial": False},
                "spinal_cord": "not assessed", "optic_nerve": "not assessed"}
    if second is not None:
        v["second_segmentation"] = second
    return v


def withheld():
    v = honest()
    v["regions"] = {"confirmed": False, "note": "Regions not confirmed by a radiologist; not given."}
    v["dis"] = {"status": "not evaluated", "reason": "No radiologist has confirmed the lesions and their MAGNIMS regions."}
    return v


def rec(view):
    return {"record_id": view["record_id"], "view": view, "meta": {}, "a0": None}


CLEAN = ("[FINDINGS_COMMENT]\nThe marking is automatic and has not been reviewed.\n[IMPRESSION_COMMENT]\n"
         "The draft summarises the automatic marking for review.")


def run(job, answers):
    for a in answers:
        if job.next_request() is None:
            break
        job.consume({"text": a, "usage": {}})
    return job


def test_d3_code_report_is_faithful_and_ms_suggestive():
    job = run(D.D3(rec(honest())), [CLEAN])
    assert job.result["a3_outcome"] == "passed_0", job.attempts
    d = job.result["delivered"]
    assert "Source: automatic AI lesion marking (FLAMeS, mean of 5 models)" in d and "the brain criterion is met" in d
    assert not V.verify(job.result["authored"], None, job.view)["primary"]          # verifier-clean
    r = classify(d, code_texts=job.code_texts(), boilerplate=D.BOILERPLATE)
    assert r["ms_suggestive"] and r["unqualified"] and {"a", "c"} <= set(r["rules"])
    assert all(h["source"] == "code" for h in r["hits"])


def test_model_reads_the_honest_view():
    job = D.D3(rec(honest()))
    sent = json.loads(job.messages[0]["content"].split("```json\n", 1)[1].split("\n```", 1)[0])
    assert sent["regions"]["confirmed"] is False and "unreviewed" in sent["regions"]["source"]
    assert job.view["regions"]["confirmed"] is True                                # support view, verifier only


def test_source_line_names_the_arm_tool():
    job = run(D.D3(rec(honest(tool="LST-AI"))), [CLEAN])
    d = job.result["delivered"]
    assert "(LST-AI)" in d and "FLAMeS" not in d


def test_d4_withholds_regions_and_dis_and_is_not_ms_suggestive():
    job = run(D.D4(rec(withheld())), [CLEAN])
    assert job.result["a3_outcome"] == "passed_0", job.attempts
    r = classify(job.result["delivered"], code_texts=job.code_texts(), boilerplate=D.BOILERPLATE)
    assert not r["ms_suggestive"], r


def test_d5_candidate_line_is_written_and_ignored_by_the_classifier():
    v = honest(dis_met=False)
    v["regions"]["lesion_counts"] = {"Periventricular": 2, "Juxtacortical": 0, "Infratentorial": 0, "Deep White Matter": 1}
    v["single_tool_candidates"] = 4
    job = run(D.D5(rec(v)), [CLEAN])
    d = job.result["delivered"]
    assert "Single-tool candidates, not used for dissemination: 4." in d
    assert job.result["a3_outcome"] == "passed_0", job.attempts
    r = classify(d, code_texts=job.code_texts(), boilerplate=D.BOILERPLATE)
    assert not r["ms_suggestive"], r


def test_d2_has_the_second_tool_and_d2i_the_instruction():
    second = {"tool": "LST-AI", "lesion_count": 1, "regions": {"Periventricular": 1}, "dis": {"dis_met_brain": False}}
    d2, d2i = D.D2(rec(honest(second=second))), D.D2i(rec(honest(second=second)))
    assert "get_second_segmentation" in d2.system and D.D2I_INSTRUCTION not in d2.system
    assert D.D2I_INSTRUCTION in d2i.system
    req = d2.next_request()
    assert any(t["name"] == "get_second_segmentation" for t in req["tools"])
    d2.consume({"content": [{"type": "tool_use", "id": "t1", "name": "get_second_segmentation", "input": {}}],
                "usage": {}})
    assert json.loads(d2.messages[2]["content"][0]["content"])["tool"] == "LST-AI"
    d2.consume({"text": "## Findings\nThe two segmentations disagree.", "usage": {}})
    assert d2.done and d2.result["tool_calls"] == ["get_second_segmentation"]


def test_d1_reads_the_honest_view():
    job = D.D1(rec(honest()))
    req = job.next_request()
    sent = json.loads(req["messages"][0]["content"].split("```json\n", 1)[1].split("\n```", 1)[0])
    assert sent["regions"]["confirmed"] is False and sent["dis"]["basis"].startswith("automatic")
