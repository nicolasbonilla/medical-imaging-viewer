"""Ninth review of PR #81: no dead end for a real FLAIR (G33), image-level inputs only (G34), validation before the gate
(G35), reasons for SEL failures and for RC-062 with gate warnings (G30 extended), a request counter before any read
(O1), every attestation audited (O2), memoised visit reads (O3), dead code removed (O4). DRAFT, PENDING owner approval."""
import inspect
import json
from pathlib import Path

import numpy as np
import pytest

import app.api.routes.clinical_tools as ct
import app.api.routes.segmentation_analysis as sa
from app.agent_platform import registry as R
from app.core.container import get_storage_service
from app.main import app
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg
from tests.unit.test_quality_gate_matrix import PLATFORM_ON, build_cases
from tests.unit.test_rc122_quality_gate_wiring import (  # noqa: F401 — fixtures
    ACQ, FILE, PAIR, URL, _CountingStorage, _registry, _user, compare, single,
)
from tests.unit.test_rc122_review7 import _Coll

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "quality_gate"
SINGLE = {"physician_confirmed_flair": False, "thickness": {"state": "native", "effective_mm": 1.0}, "scanner": None,
          "skull": "stripped"}


# ----------------------------------------------------------------------------- G33
def test_rc122_g33_no_dead_end_for_a_labelled_real_flair():
    corpus = json.loads((FIXTURES / "real_flair.v1.json").read_text(encoding="utf-8"))
    assert len(corpus["cases"]) >= 500
    dead = []
    for c in corpus["cases"]:
        cls = qg.classify_fields({"description": c["text"], "sequence_name": c["sequence_name"],
                                  "image_type": c["image_type"]}, None)["class"]
        out = qg.evaluate({"mode": "single", "platform": PLATFORM_ON, "visits": [{**SINGLE, "sequence": cls}]})
        if out["decision"] == "abstain" and not out["attestable_visits"]:
            key = json.dumps([c["text"], c["sequence_name"], c["image_type"]])
            if key not in corpus["owner_decisions"]:
                dead.append((c["text"], c["image_type"], c["sequence_name"], cls))
    assert not dead, f"G33: {len(dead)} labelled real FLAIRs hit a dead end; first: {dead[:6]}"
    assert all(v.startswith("D-QG-") for v in corpus["owner_decisions"].values())


@pytest.mark.parametrize("text", ["t2_spc_da-fl_sag_p2_iso", "t2_dark-fl_tra", "T2_SPACE_DARKFLUID", "t2_space_dark_fluid",
                                  "t2_space_dark-fluid", "da-fl", "dark-fl"])
def test_rc122_g33_dark_fluid_spellings_are_flair(text):
    assert qg.classify_fields({"description": text}, None)["class"] == "FLAIR"


@pytest.mark.parametrize("image_type, expected", [
    ("DERIVED\\PRIMARY\\M\\NORM\\DIS2D", "FLAIR"), ("DERIVED\\PRIMARY\\M\\NORM\\DIS3D", "FLAIR"),
    ("DERIVED\\PRIMARY\\FILTERED", "FLAIR"), ("DERIVED\\PRIMARY\\M\\ND\\MFSPLIT", "FLAIR"), ("DERIVED\\PRIMARY", "FLAIR"),
    ("DERIVED\\SECONDARY", "other"), ("DERIVED\\SECONDARY\\MPR", "other"), ("DERIVED\\PRIMARY\\MPR\\ND\\NORM", "other"),
    ("DERIVED\\PRIMARY\\PROJECTION IMAGE", "other"), ("DERIVED\\PRIMARY\\SUBTRACTION", "other"),
    ("ORIGINAL\\PRIMARY\\LOCALIZER", "other"), ("ORIGINAL\\SECONDARY\\SCREEN SAVE", "other"),
])
def test_rc122_g33_only_non_acquisition_image_types_are_other(image_type, expected):
    assert qg.classify_fields({"description": "AX T2 FLAIR", "image_type": image_type}, None)["class"] == expected


# ----------------------------------------------------------------------------- G34
def _service(series_doc, study_doc):
    tree = {"studies": {"st": {"_doc": study_doc, "series": {"se": {"_doc": series_doc, "instances": {"_docs": []}}}}}}
    counter = {"docs": 0}
    return type("S", (), {"db": type("D", (), {"collection": lambda self, name: _Coll(tree.get(name, {}), counter)})()})()


@pytest.mark.parametrize("study", ["MS follow-up T1 FLAIR", "Brain MRI post contrast", "contrast study T1 MPRAGE"])
def test_rc122_g34_a_copied_study_description_never_classifies_a_series(study):
    fid = "patients/p/studies/st/series/se/f.nii.gz"
    assert qg.read_source_series_description(fid, _service({"series_description": study}, {"study_description": study})) is None
    assert qg.read_source_series_description(fid, _service({"series_description": study, "series_description_source": "study"},
                                                           {"study_description": "other"})) is None
    assert qg.read_source_series_description(fid, _service({"series_description": "AX T2 FLAIR"},
                                                           {"study_description": study})) == "AX T2 FLAIR"


def test_rc122_g34_the_upload_never_stores_a_copied_study_description():
    from app.models.study_schemas import UploadInitRequest
    assert "series_description" not in UploadInitRequest.model_fields, \
        "an upload may only store a series description with its provenance (series_description_source)"


# ----------------------------------------------------------------------------- G35
def _post(client, body, enforced, monkeypatch):
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", enforced)
    r = client.post("/api/v1/segmentation/longitudinal/compare", json=body)
    return r.status_code, r.json()


@pytest.mark.parametrize("body", [
    {"tp1": {"type": "segmentation", "id": "s1"}, "tp2": {"type": "segmentation", "id": "s1"}},     # the same mask
    {"tp1": {"type": "segmentation", "id": "s2"}, "tp2": {"type": "segmentation", "id": "s1"}},     # reversed order
    {"tp1": {"type": "segmentation", "id": "s1"}, "tp2": {"type": "unknown", "id": "s2"}},          # unknown mask type
])
def test_rc123_g35_validation_precedes_the_gate(compare, monkeypatch, body):
    client, *_ = compare
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    off = _post(client, body, False, monkeypatch)
    on = _post(client, body, True, monkeypatch)
    assert off[0] == 400 and on == off, (off, on)


def test_rc123_g35_an_instance_pair_abstains_for_its_true_reason(monkeypatch):
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    gate = qg.comparison_gate(None, None, headers=[None, None], records=[None, None], visit_ok=True)
    assert "source_image_missing" in gate["codes"] and "header_unreadable" not in gate["codes"]
    assert "sequence_missing" not in gate["codes"]


# ----------------------------------------------------------------------------- G30 extended
def test_rc127_g30_rc062_withholding_a_warned_pair_tells_the_model_the_same_warnings(monkeypatch):
    from tests.unit.test_rc122_review11 import paired, served   # I1 / K2: the server's signed, pair-bound decision
    from app.api.routes.ai_report import longitudinal_notice
    from app.services.brain_report_service import BrainReportService
    from app.services.report_payload_guard import _Projector
    bad, seen = [], 0
    for key, _, inp in build_cases():
        if inp["mode"] != "comparison":
            continue
        gate = qg.evaluate(inp)
        warnings = qg.explain(gate)["warnings"]
        if gate["ai_output_allowed"] is not True or not warnings:
            continue
        seen += 1
        lng = paired(qg.apply_to_comparison(lcs.present_comparison({"changes": []}, acquisition_check={
            "status": "not_established", "missing": [], "differing": []}, evidence=None, binding=None,
            stored_review=None, visit_check={"status": "ok"}), served(gate, monkeypatch)))
        prompt = BrainReportService()._build_findings_prompt({"longitudinal": _Projector().longitudinal(lng)}, language="en")
        notice = longitudinal_notice(lng, "en")
        if any(qg.reason_sentence(w) not in prompt or qg.reason_sentence(w) not in notice for w in warnings):
            bad.append(key)
        if seen > 400 and not bad:
            break
    assert seen and not bad, f"G30: {len(bad)} warned pairs withheld by RC-062 lose the warnings; first: {bad[:4]}"


# ----------------------------------------------------------------------------- O1, O2, O3, O4
def test_rc126_o1_a_request_counter_comes_before_any_read(single, monkeypatch):
    client, state = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    monkeypatch.setattr(qg, "RATE_LIMIT_PER_MINUTE", 2)                  # the ONE limit (tenth review)
    monkeypatch.setattr(qg, "_LIMITER", None)
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_CountingStorage(b"x"))
    codes = [client.post(URL, json={"file_id": FILE}).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and codes[2:] == [429, 429]
    assert len(state["paths"]) == 2, "an over-the-limit request was authorized and read"


def test_rc126_o2_every_attestation_is_audited_also_from_the_cache(single, monkeypatch):
    import nibabel as nib
    client, _ = single
    events = []
    reg = _registry()
    reg._audit = lambda e: events.append((e, R.current_actor().user_id))
    monkeypatch.setattr(qg, "_REGISTRY", reg)
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_CountingStorage(
        nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 3.0, 1.0])).to_bytes()))
    for _ in range(3):
        assert client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True}).status_code == 200
    attested = [uid for e, uid in events if (e.get("details") or {}).get("attested_visits") == ["study"]]
    assert attested == ["id-dr_rev"] * 3, events


def test_rc123_o3_the_visit_records_are_read_once_per_request(compare, monkeypatch):
    client, *_ = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    reads = []
    original = sa._source_visit
    monkeypatch.setattr(sa, "_source_visit", lambda fid: reads.append(fid) or original(fid))
    assert client.post("/api/v1/segmentation/longitudinal/compare", json=PAIR).status_code == 200
    assert len(reads) == 2, reads


def test_rc126_o4_no_dead_code_and_no_stale_browser_comments():
    for name in ("_UNREAD", "_header_complete", "classify_text"):
        assert not hasattr(qg, name), name
    assert "gate.ts" not in inspect.getsource(qg), "a comment still says the rule is also in gate.ts"
