"""Sixth review of PR #81: ONE implementation of the single quality gate (server-authoritative), audit attribution,
cache staleness and the report notice. DRAFT, PENDING owner approval.

G27  the gate's rule, policy and sequence classifier exist only in backend/app/services/quality_gate.py; the browser
     sends its inputs and shows the server's decision; the server alone passes the shared corpus (G12).
A1   the server reads everything the browser used to read: the NIfTI descrip / aux_file / intent_name / db_name, the
     text and DICOM attributes of NIfTI extensions, and the DICOM ImageType; a comparison reads each visit's stored
     image header exactly as a single study does.
A2   an attestation is audited under the clinician who gave it, always — also when the decision is in the cache.
A3   the cached decision depends on every input it was made from (file, series record, acquisition record,
     attestation, skull outcome, policy version, and the user when attested).
A4   when the gate stops a comparison the report notice gives the gate's reason; one table of reason sentences feeds
     the assistant's caveat and the report notice in en/es/de.
"""
import copy
import io
import json
import re
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.api.routes.clinical_tools as ct
import app.api.routes.segmentation_analysis as sa
from app.agent_platform import registry as R
from app.core.container import get_imaging_service, get_storage_service
from app.main import app
from app.security import get_current_active_user
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg
from tests.unit.test_rc122_quality_gate_wiring import (  # noqa: F401 — fixtures
    ACQ, FILE, PAIR, REGISTRY, URL, _CountingStorage, _dicom_bytes, _registry, _user, compare, single,
)

REPO = Path(__file__).resolve().parents[3]
FRONT = REPO / "frontend" / "src"
RULE_WORDS = ("evaluateGate", "classifyFields", "classifyText", "sequenceTokens", "textInversionTimeMs",
              "sequenceFromHeader", "confirmServerDecision", "finalBrowserGate", "withAttestation", "canonicalGate",
              "other_words", "flair_substring", "min_flair_inversion_time_ms", "confirmation_modes", "mode_actions",
              "sequence_name_codes", "image_type_other", "qualityGatePolicy", "QUALITY_GATE_POLICY")


def _product_sources():
    for p in FRONT.rglob("*"):
        if p.suffix in (".ts", ".tsx") and ".test." not in p.name and "__tests__" not in p.parts:
            yield p


# ----------------------------------------------------------------------------- G27
def test_rc122_g27_the_browser_holds_no_rule_no_classifier_and_no_policy():
    found = [(p.relative_to(REPO).as_posix(), w) for p in _product_sources()
             for w in RULE_WORDS if re.search(rf"\b{w}\b", p.read_text(encoding="utf-8"))]
    assert not found, f"G27: gate rule / classifier / policy in the browser: {found[:8]}"
    assert not (FRONT / "config" / "qualityGatePolicy.v1.json").exists(), "the browser keeps a policy copy"
    assert not (FRONT / "config" / "qualityGate.cases.v1.json").exists(), "the two-copy parity fixture is kept"


def test_rc122_g27_on_the_server_only_quality_gate_py_holds_the_rule():
    app_dir = REPO / "backend" / "app"
    owners = []
    for p in app_dir.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        if p.name == "quality_gate.py":
            continue
        if "quality_gate_policy.json" in text or re.search(r"def (sequence_tokens|_classify_tokens|classify_fields|_evaluate)\b", text):
            owners.append(p.relative_to(REPO).as_posix())
    assert not owners, f"G27: gate rule outside quality_gate.py: {owners}"


def test_rc122_g27_the_server_alone_passes_the_shared_corpus():
    corpus = REPO / "backend" / "tests" / "fixtures" / "quality_gate" / "sequences.v1.json"
    assert corpus.exists(), "the corpus is server test data"
    cases = json.loads(corpus.read_text(encoding="utf-8"))["cases"]
    bad = [c for c in cases if qg.classify_fields({"description": c["text"], "sequence_name": c.get("sequence_name"),
                                                   "image_type": c.get("image_type")}, c["inversion_time_ms"])["class"]
           != c["expected"]]
    assert len(cases) >= 180 and not bad, bad[:5]


def test_rc127_g27_the_answer_carries_what_the_browser_shows():
    """The browser reads the attestable visits and the action of each code from the answer, never from a policy."""
    single = qg.evaluate({"mode": "single", "platform": {"allowed": True, "code": None}, "visits": [
        {"sequence": "missing", "physician_confirmed_flair": False, "thickness": None, "scanner": None, "skull": "pending"}]})
    assert single["attestable_visits"] == ["study"] and single["actions"]["sequence_missing"] == "action"
    same = {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0}
    cmp = qg.evaluate({"mode": "comparison", "platform": {"allowed": True, "code": None}, "rc062_withholds": False, "visits": [
        {"sequence": "unknown", "physician_confirmed_flair": False, "thickness": None, "scanner": same, "skull": "unknown"},
        {"sequence": "FLAIR", "physician_confirmed_flair": False, "thickness": None, "scanner": same, "skull": "unknown"}]})
    assert cmp["attestable_visits"] == ["tp1"] and cmp["actions"]["sequence_unknown"] == "action_comparison"
    # G28 (seventh review): with visit 2 a T1 the attestation of visit 1 changes nothing, so none is offered
    futile = qg.evaluate({"mode": "comparison", "platform": {"allowed": True, "code": None}, "visits": [
        {"sequence": "unknown", "physician_confirmed_flair": False, "thickness": None, "scanner": None, "skull": "unknown"},
        {"sequence": "T1", "physician_confirmed_flair": False, "thickness": None, "scanner": None, "skull": "unknown"}]})
    assert futile["attestable_visits"] == []


# ----------------------------------------------------------------------------- A1
def _nifti(descrip=None, dicom=None, text=None):
    img = nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 3.0, 1.0]))
    if descrip:
        img.header["descrip"] = descrip.encode()
    if dicom is not None:
        img.header.extensions.append(nib.nifti1.Nifti1Extension(2, dicom))
    if text is not None:
        img.header.extensions.append(nib.nifti1.Nifti1Extension(6, text.encode()))
    return img.to_bytes()


def _dicom_payload(**attrs):
    """A bare DICOM dataset (implicit VR, little endian), as a NIfTI DICOM extension carries it."""
    import pydicom
    from pydicom.dataset import Dataset
    ds = Dataset()
    for k, v in attrs.items():
        setattr(ds, k, v)
    ds.is_little_endian, ds.is_implicit_VR = True, True
    buf = io.BytesIO()
    pydicom.dcmwrite(buf, ds, write_like_original=True)
    return buf.getvalue()


@pytest.mark.parametrize("descrip, expected", [("Sag T1 MPRAGE", "T1"), ("AX T2 FLAIR", "FLAIR"), ("TE=81;TI=900", "other")])
def test_rc122_a1_the_server_reads_the_nifti_descrip(descrip, expected):
    fields = qg.read_header_fields(_nifti(descrip=descrip))
    assert qg.classify_fields(qg.header_classifier_fields(fields), fields.get("inversion_time_ms"))["class"] == expected


def test_rc122_a1_the_server_reads_nifti_extensions_and_the_dicom_image_type():
    payload = _dicom_payload(SeriesDescription="AX T2 FLAIR", ImageType=["DERIVED", "SECONDARY", "MPR"])
    fields = qg.read_header_fields(_nifti(dicom=payload))
    assert qg.classify_fields(qg.header_classifier_fields(fields), None)["class"] == "other"
    fields = qg.read_header_fields(_nifti(text="series: Sag T1 MPRAGE"))
    assert qg.classify_fields(qg.header_classifier_fields(fields), None)["class"] == "T1"


def test_rc122_a1_the_single_route_classifies_a_nifti_by_its_descrip(single, monkeypatch):
    client, _ = single
    monkeypatch.setattr(qg, "_HEADER_CACHE", type(qg._HEADER_CACHE)())
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_CountingStorage(_nifti("Sag T1 MPRAGE")))
    body = client.post(URL, json={"file_id": FILE}).json()
    assert body["inputs"]["visits"][0]["sequence"] == "T1" and "sequence_not_flair" in body["codes"]


class _ByPath:
    def __init__(self, data):
        self.data = data

    async def download_file(self, bucket, path):
        return self.data[path]


def test_rc123_a1_a_comparison_reads_each_visit_s_image_header(compare, monkeypatch):
    """Two uploaded DICOM FLAIRs without a series record: classified FLAIR from their headers, never 'missing'."""
    client, records, (f1, f2) = compare
    records["desc"][f1] = records["desc"][f2] = None
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_ByPath({f1: _dicom_bytes(), f2: _dicom_bytes()}))
    res = client.post("/api/v1/segmentation/longitudinal/compare", json=PAIR).json()
    codes = res["quality_gate"]["codes"]
    assert "sequence_missing" not in codes and "sequence_unknown" not in codes, codes
    assert res["quality_gate"]["ai_output_allowed"] is True and res["abstained"] is False


# ----------------------------------------------------------------------------- A2, A3
def _users():
    return _user(), _user().model_copy(update={"id": "id-dr_two", "username": "dr_two", "email": "dr_two@example.com"})


def test_rc126_a2_each_clinician_s_attestation_is_audited_under_that_clinician(single, monkeypatch):
    client, _ = single
    seen = []
    reg = _registry()
    reg._audit = lambda e: seen.append((e.get("code"), R.current_actor().user_id))
    monkeypatch.setattr(qg, "_REGISTRY", reg)
    monkeypatch.setattr(qg, "_LIMITER", None)
    monkeypatch.setattr(qg, "_CONSULTATIONS", type(qg._CONSULTATIONS)())
    monkeypatch.setattr(qg, "_HEADER_CACHE", type(qg._HEADER_CACHE)())   # a fresh header cache per test
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_CountingStorage(_nifti()))
    for user in _users():
        app.dependency_overrides[get_current_active_user] = (lambda u: (lambda: u))(user)
        assert client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True}).status_code == 200
    attested = [(code, uid) for code, uid in seen if code and ".attested" in code]
    assert sorted(uid for _, uid in attested) == ["id-dr_rev", "id-dr_two"], seen


def test_rc126_a3_correcting_the_series_description_invalidates_the_cached_decision(single, monkeypatch):
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    monkeypatch.setattr(qg, "_LIMITER", None)
    monkeypatch.setattr(qg, "_CONSULTATIONS", type(qg._CONSULTATIONS)())
    monkeypatch.setattr(qg, "_HEADER_CACHE", type(qg._HEADER_CACHE)())   # a fresh header cache per test
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_CountingStorage(_nifti()))
    desc = {"value": "Sag T1 MPRAGE"}
    monkeypatch.setattr(qg, "read_source_series_description", lambda fid, svc=None: desc["value"])
    first = client.post(URL, json={"file_id": FILE}).json()
    assert first["inputs"]["visits"][0]["sequence"] == "T1"
    desc["value"] = "AX T2 FLAIR"                                  # the series record is corrected
    second = client.post(URL, json={"file_id": FILE}).json()
    assert second["inputs"]["visits"][0]["sequence"] == "FLAIR", "the cached decision of the old record was served"
    acq = {"value": None}
    monkeypatch.setattr(lcs, "read_source_acquisition", lambda fid, svc=None: copy.deepcopy(acq["value"]))
    client.post(URL, json={"file_id": FILE})
    acq["value"] = {**ACQ, "inversion_time_ms": 900.0}             # the acquisition record changes
    third = client.post(URL, json={"file_id": FILE}).json()
    assert third["inputs"]["visits"][0]["sequence"] == "other", "the cached decision of the old acquisition was served"


# ----------------------------------------------------------------------------- A4
def _stopped(code):
    gate = qg.evaluate({"mode": "comparison", "platform": {"allowed": True, "code": None}, "visits": [
        {"sequence": "FLAIR", "physician_confirmed_flair": False, "thickness": None, "scanner": None, "skull": "unknown"},
        {"sequence": "T1", "physician_confirmed_flair": False, "thickness": None, "scanner": None, "skull": "unknown"}]})
    assert code in gate["codes"]
    return qg.abstained_comparison(gate)


@pytest.mark.parametrize("lang", ["en", "es", "de"])
def test_rc127_a4_the_report_notice_gives_the_gate_s_reason_when_the_gate_stops(lang):
    from app.api.routes.ai_report import LONGITUDINAL_NOTICE, longitudinal_notice
    notice = longitudinal_notice(_stopped("sequence_not_flair"), lang)
    assert notice and LONGITUDINAL_NOTICE[lang]["abstained"] not in notice, "RC-062's reason for a gate stop"
    assert qg.reason_sentence("sequence_not_flair", lang) in notice


def test_rc127_a4_one_table_of_reasons_for_the_caveat_and_the_report():
    from app.api.routes.ai_report import longitudinal_notice
    codes = qg.load_policy()["codes"]
    for code in codes:
        assert qg.CAVEAT_REASONS[code] == qg.reason_sentence(code, "en"), code
        if qg.load_policy()["codes"][code] == "abstain":      # G30 (eighth review): a caveat gives CAUSES only
            assert qg.CAVEAT_REASONS[code] in qg.gate_caveat({"codes": [code]})
        for lang in ("es", "de"):
            assert qg.reason_sentence(code, lang) and qg.reason_sentence(code, lang) != qg.reason_sentence(code, "en"), (code, lang)
    warned = {"abstained": False, "change_candidates": {"new": 0, "enlarging": 0},
              "quality_gate": {"ai_output_allowed": True, "codes": ["thickness_at_least"]}}
    for lang in ("en", "es", "de"):
        assert qg.reason_sentence("thickness_at_least", lang) in longitudinal_notice(warned, lang)
    assert qg.CAVEAT_REASONS["thickness_at_least"] in longitudinal_notice(warned, "en"), "the drifted sentence"
