"""Tenth review of PR #81 — SIMPLIFY (fewer parts, fewer defects): no consultation cache, so a transient read error is
never remembered (S1); exam-level fields never veto a series (S2, G33 extended); RC-062 predicted from the same
spacing, axis order and loadability as at run time (S3); the real audit record keeps every attested visit, no cut at
64 characters (S4); one place for each thing. DRAFT, PENDING owner approval."""
import asyncio
import inspect
import io
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

import app.api.routes.ai_report as air
import app.api.routes.clinical_tools as ct
import app.api.routes.segmentation_analysis as sa
from app.agent_platform import registry as R
from app.core.container import get_storage_service
from app.main import app
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg
from tests.unit.test_quality_gate_matrix import PLATFORM_ON
from tests.unit.test_rc122_quality_gate_wiring import (  # noqa: F401 — fixtures
    ACQ, FILE, URL, _CountingStorage, _dicom_bytes, _registry, single,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "quality_gate"
SINGLE = {"physician_confirmed_flair": False, "thickness": {"state": "native", "effective_mm": 1.0}, "scanner": None,
          "skull": "stripped"}
F1 = "patients/p/studies/st-1/series/se-1/a"
F2 = "patients/p/studies/st-2/series/se-2/b"


def _cls(**fields):
    return qg.classify_fields(fields, None)["class"]


# ----------------------------------------------------------------------------- S1
class _FlakyRanged(_CountingStorage):
    """A storage whose FIRST ranged read fails (a transient error); every later read succeeds."""

    def __init__(self, data):
        super().__init__(data)
        self.failures = 1

    async def download_file_range(self, bucket, path, start, end):
        if self.failures:
            self.failures -= 1
            raise ConnectionError("transient storage error")
        return self.data[start:end + 1]


def test_rc126_s1_a_transient_read_error_is_never_remembered(single, monkeypatch):
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    img = nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 5.0, 1.0])).to_bytes()
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_FlakyRanged(img))
    first = client.post(URL, json={"file_id": FILE}).json()
    assert "header_unreadable" in first["codes"], first["codes"]
    second = client.post(URL, json={"file_id": FILE}).json()
    assert "header_unreadable" not in second["codes"], "S1: the transient read error was remembered"
    assert second["inputs"]["visits"][0]["thickness"] == {"state": "at_least", "effective_mm": 5.0}


def test_rc126_s1_every_consultation_is_evaluated_and_nothing_caches_an_answer(single, monkeypatch):
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    runs = []
    original = qg.run_quality_gate
    monkeypatch.setattr(qg, "run_quality_gate", lambda *a, **k: runs.append(1) or original(*a, **k))
    for _ in range(3):
        assert client.post(URL, json={"file_id": FILE}).status_code == 200
    assert len(runs) == 3, "S1: a consultation was answered from a cache"
    for name in ("consultation_key", "cached_consultation", "store_consultation", "_CONSULTATIONS",
                 "audit_cached_attestation"):
        assert not hasattr(qg, name), name


def test_rc122_s1_the_header_cache_never_keeps_a_failed_or_unreadable_read(monkeypatch):
    monkeypatch.setattr(qg, "_HEADER_CACHE", type(qg._HEADER_CACHE)())
    key = (FILE, 10, "v1", "2026-11-12")

    async def fails(*a):
        raise ConnectionError("transient")

    async def unreadable(*a):
        return {**qg._NO_HEADER, "unreadable": True}

    for reader in (fails, unreadable):
        monkeypatch.setattr(qg, "_read_header_fields", reader)
        fields = asyncio.run(qg.visit_header_fields(None, "bucket", FILE, version_key=key))
        assert fields.get("unreadable") is True and key not in qg._HEADER_CACHE, reader.__name__


# ----------------------------------------------------------------------------- S2
EXAM_PROTOCOLS = ["BRAIN W WO CONTRAST", "MS POST GD", "MS BRAIN +C", "HEAD WITH AND WITHOUT CONTRAST",
                  "BRAIN W/WO", "MS_follow_up_KM", "Brain_MS_post_Gd", "Brain MS post contrast", "MS Gd",
                  "BRAIN T1 T2 FLAIR DWI", "MS T1 MPRAGE protocol"]


@pytest.mark.parametrize("protocol", EXAM_PROTOCOLS)
def test_rc122_s2_an_exam_level_protocol_never_turns_a_flair_series_into_other(protocol):
    assert _cls(description="AX T2 FLAIR", protocol_name=protocol) == "FLAIR"
    assert _cls(description="t2_spc_da-fl_sag_p2_iso", protocol_name=protocol, image_type="ORIGINAL\\PRIMARY") == "FLAIR"
    assert _cls(description="Series 4", sequence_name="flair3d", protocol_name=protocol) == "FLAIR"


def test_rc122_s2_an_exam_level_field_supports_a_silent_series_and_never_vetoes_it():
    assert _cls(description=None, protocol_name="AX T2 FLAIR") == "FLAIR"            # supports when the series is silent
    assert _cls(description="Series 4", protocol_name="t2_tirm_tra_dark-fluid") == "FLAIR"
    for protocol in ("BRAIN W WO CONTRAST", "MS POST GD", "t1_mprage_sag"):
        assert _cls(description="Series 4", protocol_name=protocol) == "unknown", protocol   # attestable, never 'other'
    # the series' own fields still decide
    assert _cls(description="AX T2 FLAIR POST GD", protocol_name="AX FLAIR") == "other"
    assert _cls(description="t1_mprage_sag", protocol_name="AX FLAIR") == "T1"
    assert _cls(description="AX T2 FLAIR", image_type="DERIVED\\SECONDARY", protocol_name="AX FLAIR") == "other"


def test_rc122_s2_no_dead_end_for_a_flair_series_under_an_exam_level_protocol():
    corpus = json.loads((FIXTURES / "real_flair.v1.json").read_text(encoding="utf-8"))
    combos = [c for c in corpus["cases"] if c.get("protocol_name")]
    assert len(combos) >= 300 and {c["vendor"] for c in combos} == {"Siemens", "GE", "Philips", "Canon"}
    dead = []
    for c in corpus["cases"]:
        cls = _cls(description=c["text"], sequence_name=c["sequence_name"], image_type=c["image_type"],
                   protocol_name=c.get("protocol_name"))
        out = qg.evaluate({"mode": "single", "platform": PLATFORM_ON, "visits": [{**SINGLE, "sequence": cls}]})
        if out["decision"] == "abstain" and not out["attestable_visits"]:
            key = json.dumps([c["text"], c["sequence_name"], c["image_type"], c.get("protocol_name")])
            if key not in corpus["owner_decisions"]:
                dead.append((c["vendor"], c["text"], c.get("protocol_name"), c["image_type"], cls))
    assert not dead, f"S2: {len(dead)} labelled FLAIR series hit a dead end; first: {dead[:6]}"


# ----------------------------------------------------------------------------- S3
def _nifti(zooms, shape=(8, 8, 6)):
    return nib.Nifti1Image(np.zeros(shape, np.float32), np.diag([*zooms[:3], 1.0])).to_bytes()


def _dicom(pixel_spacing, thickness):
    import pydicom
    ds = pydicom.dcmread(io.BytesIO(_dicom_bytes()), force=True)
    ds.SeriesDescription = ""                 # names no sequence: the attestation is what a pair would need
    ds.PixelSpacing, ds.SliceThickness, ds.SpacingBetweenSlices = list(pixel_spacing), thickness, thickness
    buf = io.BytesIO()
    ds.save_as(buf, write_like_original=False)
    return buf.getvalue()


def _header(data):
    try:
        return qg.read_header_fields(data)
    except Exception:  # noqa: BLE001 — as visit_header_fields: an unreadable header
        return {**qg._NO_HEADER, "unreadable": True}


S3_PAIRS = {
    "two NIfTI, same anisotropic in-plane spacing": (_nifti((0.5, 0.9, 3.0)), _nifti((0.5, 0.9, 3.0))),
    "two NIfTI, in-plane spacing swapped": (_nifti((0.5, 0.9, 3.0)), _nifti((0.9, 0.5, 3.0))),
    "DICOM and NIfTI, anisotropic in-plane spacing": (_dicom((0.5, 0.9), 3.0), _nifti((0.5, 0.9, 3.0))),
    "a 4-D NIfTI (RC-062 cannot load it)": (_nifti((0.5, 0.9, 3.0), shape=(8, 8, 6, 2)), _nifti((0.5, 0.9, 3.0))),
    "not an image": (b"\0" * 400, _nifti((0.5, 0.9, 3.0))),
}


@pytest.mark.parametrize("name", list(S3_PAIRS))
def test_rc123_s3_the_rc062_prediction_is_what_rc062_does_at_run_time(name, monkeypatch):
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    d1, d2 = S3_PAIRS[name]
    runtime = [asyncio.run(sa._load_source_intensity(f, _CountingStorage(d), "s3"))[1] for f, d in ((F1, d1), (F2, d2))]
    withholds = lcs.rc062_withholds(lcs.compare_acquisitions(dict(ACQ), dict(ACQ), *runtime), {"status": "ok"})
    predicted = []
    original = qg.run_quality_gate
    monkeypatch.setattr(qg, "run_quality_gate",
                        lambda inputs, **k: predicted.append(inputs["rc062_withholds"]) or original(inputs, **k))
    gate = qg.comparison_gate(F1, F2, headers=[_header(d1), _header(d2)], records=[(dict(ACQ), None)] * 2, visit_ok=True)
    assert predicted == [withholds], f"S3 ({name}): predicted {predicted}, RC-062 at run time withholds={withholds}"
    if withholds:
        assert gate["attestable_visits"] == [], f"S3 ({name}): a futile attestation is offered"
    else:
        assert gate["attestable_visits"], f"S3 ({name}): the attestation the pair needs is not offered"


def test_rc123_s3_one_spacing_helper_for_the_prediction_and_rc062():
    assert "lcs.rc062_voxel_spacing(" in inspect.getsource(sa._load_source_intensity)
    assert "lcs.rc062_voxel_spacing(" in inspect.getsource(qg.read_header_fields)


# ----------------------------------------------------------------------------- S4
def test_rc126_s4_the_real_audit_record_keeps_every_attested_visit(monkeypatch):
    from app.core.logging import audit as A
    built, events = [], []
    monkeypatch.setattr(A.AuditLogger, "log_event",
                        lambda self, event, durable=True: built.append(A.build_audit_record(event)))
    reg = _registry()
    reg._audit = lambda e: (events.append(e), R.default_audit_sink(e))
    visit = {"sequence": "unknown", "physician_confirmed_flair": True, "skull": "stripped", "scanner": None,
             "thickness": {"state": "native", "effective_mm": 1.0}}
    qg.run_quality_gate({"mode": "comparison", "visits": [dict(visit), dict(visit)], "rc062_withholds": False},
                        registry=reg, study_key="s")
    (event,), (record,) = events, built
    assert record.get("details", {}).get("attested_visits") == ["tp1", "tp2"], record
    assert record["details"].get("causes") == ["scanner_not_recorded"], record
    assert record["reason"] == f"{event['event']}:{event['code']}", "S4: the reason was cut"


def test_rc126_s4_every_reason_the_gate_writes_fits_the_audit_code_field():
    policy = qg.load_policy()
    too_long = []
    for decision in qg.DECISIONS:
        for code in policy["codes"]:
            for visits in ([], ["study"], ["tp1"], ["tp2"], ["tp1", "tp2"]):
                checks = [{"check": "x", "visit": None, "status": "abstain" if decision == "abstain" else "pending",
                           "code": code, "params": {}}]
                checks += [{"check": "sequence", "visit": v, "status": "warn", "code": "sequence_confirmed_by_physician",
                            "params": {}} for v in visits]
                code_written = qg.audit_code({"decision": decision, "checks": checks})
                for event in R.AUDIT_EVENT_TYPES:
                    if len(f"{event}:{code_written}") > 64:
                        too_long.append(f"{event}:{code_written}")
    assert not too_long, f"S4: {len(too_long)} reasons longer than the 64-character code field; first: {too_long[:3]}"
    assert "64 characters" not in (qg.audit_code.__doc__ or "")


# ----------------------------------------------------------------------------- one place for each thing
def test_rc127_one_gate_warnings_block_in_the_report_model_text():
    from app.services import brain_report_service as brs
    assert inspect.getsource(brs).count("QUALITY-GATE WARNINGS for this pair") == 1


def test_rc127_one_warnings_story():
    assert not hasattr(qg, "warning_codes"), "warnings come from explain() only"
    assert 'reason_lead("warned"' in inspect.getsource(qg.apply_to_comparison)
    assert inspect.getsource(air.longitudinal_notice).count("explain(") == 1


def test_rc126_one_rate_limit_helper_and_one_429_builder():
    assert [n for n in dir(qg) if n.startswith("rate_limit")] == ["rate_limit"]
    assert inspect.getsource(ct.quality_gate).count("status_code=429") == 0
    assert inspect.getsource(qg).count("status_code=429") == 1


def test_rc123_one_gate_setup_for_compare_and_sel():
    for route in (sa.compare_longitudinal, sa.detect_slowly_expanding_lesions):
        src = inspect.getsource(route)
        assert "_gate_setup(" in src and "acq_memo: dict = {}" not in src and "gate_ctx" not in src, route.__name__


def test_rc123_one_source_reference_lookup():
    assert inspect.getsource(lcs).count('.collection("studies")') == 1
