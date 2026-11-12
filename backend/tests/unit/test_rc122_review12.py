"""Twelfth review of PR #81: a SIGNED, pair-bound gate decision instead of a per-instance store (K1, K2), a refused
access always leaves an audit record (K3), the skull outcome said to be what it is — reported by the browser (K4), only a
real run recorded as a release (K5), large NIfTI extensions (O1), the base read of acquisition records with the flags
off (O2), a bounded, content-keyed word-set cache (O4), one source of truth in the card (O5). DRAFT, PENDING owner
approval."""
import asyncio
import copy
import gzip
import importlib.util
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from fastapi import HTTPException

import app.api.routes.clinical_tools as ct
import app.api.routes.segmentation_analysis as sa
from app.agent_platform import registry as R
from app.core.container import get_storage_service
from app.main import app
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg
from tests.unit.test_rc122_quality_gate_wiring import (  # noqa: F401 — fixtures
    ACQ, FILE, PAIR, REGISTRY, URL, _CountingStorage, _registry, compare, single,
)

ROOT = Path(__file__).resolve().parents[3]
REAL_AUTHORIZED = ct._authorized_inputs           # CAPA-009's own check (the fixtures replace it)
SCANNER = {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0}
WARNED = {"sequence": "FLAIR", "physician_confirmed_flair": False, "scanner": SCANNER, "skull": "stripped",
          "thickness": {"state": "not_determinable", "effective_mm": None}}
COUNTS = {"burden_tp1_ml": 1.0, "burden_tp2_ml": 1.5, "total_lesions_tp1": 3, "total_lesions_tp2": 4,
          "status_counts": {"new": 1, "enlarged": 0, "resolved": 0, "shrunk": 0, "stable": 3}}
PAIR_A = {"tp1": {"id": "seg-a1", "source": "patients/p/studies/a1/series/x/1.nii.gz", "version": "10:v1:2026-11-12"},
          "tp2": {"id": "seg-a2", "source": "patients/p/studies/a2/series/x/2.nii.gz", "version": "11:v1:2026-11-12"}}
PAIR_B = {**PAIR_A, "tp2": {**PAIR_A["tp2"], "id": "seg-b2"}}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _signed(pair, monkeypatch, visit=WARNED):
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    gate = qg.run_quality_gate({"mode": "comparison", "visits": [dict(visit), dict(visit)], "rc062_withholds": False},
                               study_key="s", releases_output=False)
    return {**gate, "token": qg.decision_token(gate, pair, "id-dr_rev")}


# ----------------------------------------------------------------------------- K1, K2
def test_rc127_k1_the_report_reads_the_signed_decision_for_its_own_pair(monkeypatch):
    gate = _signed(PAIR_A, monkeypatch)
    account = qg.report_account({**COUNTS, "pair": PAIR_A, "quality_gate": gate})
    assert account["established"] is True and account["warnings"] == qg.explain(gate)["warnings"]


def test_rc127_k2_the_decision_of_pair_a_in_a_report_for_pair_b_is_not_established(monkeypatch):
    gate = _signed(PAIR_A, monkeypatch)
    account = qg.report_account({**COUNTS, "pair": PAIR_B, "quality_gate": gate})
    assert account["established"] is False and account["causes"] == ["gate_not_established"]


def test_rc127_k1_a_second_instance_accepts_the_same_token(monkeypatch):
    gate = _signed(PAIR_A, monkeypatch)
    spec = importlib.util.spec_from_file_location("quality_gate_second_instance", qg.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)                    # a fresh module state: nothing remembered from the first one
    assert fresh.report_account({**COUNTS, "pair": PAIR_A, "quality_gate": gate})["established"] is True
    assert not hasattr(qg, "_DECISIONS"), "the per-instance decision store is retired"


def test_rc127_k1_a_tampered_or_expired_token_is_rejected(monkeypatch):
    gate = _signed(PAIR_A, monkeypatch)
    head, body, sig = gate["token"].split(".")
    flipped = body[:-2] + ("A" if body[-2] != "A" else "B") + body[-1]
    for token in (f"{head}.{flipped}.{sig}", f"{head}.{body}.{sig[:-1]}x", "", None, ["x"], "qg1.e30.e30"):
        assert qg.report_account({**COUNTS, "pair": PAIR_A, "quality_gate": {**gate, "token": token}})["established"] is False
    monkeypatch.setattr(qg, "_now", lambda: 10 ** 11)                           # far after the expiry
    assert qg.report_account({**COUNTS, "pair": PAIR_A, "quality_gate": gate})["established"] is False


def test_rc123_k2_the_comparison_answers_with_its_pair_and_a_signed_decision(compare, monkeypatch):
    client, *_ = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    res = client.post("/api/v1/segmentation/longitudinal/compare", json=PAIR).json()
    assert [res["pair"][t]["id"] for t in ("tp1", "tp2")] == ["s1", "s2"]
    assert qg.report_account(res)["established"] is True
    other = {**res, "pair": {**res["pair"], "tp2": {**res["pair"]["tp2"], "id": "s3"}}}
    assert qg.report_account(other)["established"] is False


# ----------------------------------------------------------------------------- K3
def test_rc126_k3_a_refused_access_leaves_exactly_one_audit_record(single, monkeypatch):
    from app.core.logging import audit as A
    client, _ = single
    seen = []
    monkeypatch.setattr(A.AuditLogger, "log_event", lambda self, event, durable=True: seen.append(event))
    monkeypatch.setattr(qg, "_REGISTRY", _registry())

    async def denied(file_id, user):
        raise HTTPException(status_code=404, detail="Not found")       # CAPA-009: a denial is a 404

    monkeypatch.setattr(ct, "_authorized_inputs", REAL_AUTHORIZED)
    monkeypatch.setattr(ct, "require_imaging_access", denied)
    assert client.post(URL, json={"file_id": "patients/another/studies/s/series/x/f.nii.gz"}).status_code == 404
    assert len(seen) == 1 and seen[0].outcome != A.AuditOutcome.SUCCESS, [(e.event_type, e.outcome) for e in seen]


# ----------------------------------------------------------------------------- K4
def test_rc125_k4_the_skull_outcome_is_recorded_as_reported_by_the_browser(single, monkeypatch):
    client, _ = single
    events = []
    reg = _registry()
    reg._audit = events.append
    monkeypatch.setattr(qg, "_REGISTRY", reg)
    client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True, "skull": "stripped"})
    assert events and events[-1]["details"].get("skull_report") == "client_reported:stripped", events[-1]
    doc = ct.quality_gate.__doc__ or ""
    assert "client-reported" in doc and "never from the client" not in doc
    manifest = json.loads((ROOT / "docs/iec62304/records/risk_verification/rc_test_manifest.json").read_text(encoding="utf-8"))
    assert "client-reported" in manifest["controls"]["RC-125"]["description"]


# ----------------------------------------------------------------------------- K5
def _types(monkeypatch):
    from app.core.logging import audit as A
    seen = []
    monkeypatch.setattr(A.AuditLogger, "log_event", lambda self, event, durable=True: seen.append(event.event_type))
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data["agents"]["quality-gate"]["approval"]["status"] = "approved"     # IN MEMORY, for the test only
    monkeypatch.setattr(qg, "_REGISTRY", R.AgentRegistry(data, switches=R.InMemoryKillSwitches({"quality-gate": True}),
                                                         audit=R.default_audit_sink))
    return A, seen


def test_rc126_k5_only_a_real_run_is_recorded_as_a_release(single, monkeypatch):
    client, _ = single
    A, seen = _types(monkeypatch)
    img = nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 1.0, 1.0])).to_bytes()
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_CountingStorage(img))
    final = {"file_id": FILE, "physician_confirmed_flair": True, "skull": "stripped"}
    assert client.post(URL, json=final).json()["ai_output_allowed"] is True
    assert A.AuditEventType.CLINICAL_AI_RUN not in seen, "no run, yet recorded as an AI run"
    run = client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True}).json()
    assert run["ai_may_run"] is True and isinstance(run.get("run_token"), str)
    seen.clear()
    client.post(URL, json={**final, "run_token": run["run_token"]})
    assert seen == [A.AuditEventType.CLINICAL_AI_RUN], seen
    seen.clear()
    client.post(URL, json={**final, "run_token": run["run_token"]})          # single use
    assert seen == [A.AuditEventType.QUALITY_GATE_CONSULTATION], seen


# ----------------------------------------------------------------------------- O1
class _Ranged(_CountingStorage):
    async def download_file_range(self, bucket, path, start, end):
        return self.data[start:end + 1]


def test_rc122_o1_a_header_with_extensions_beyond_1_mib_is_read():
    img = nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 3.0, 1.0]))
    img.header.extensions.append(nib.nifti1.Nifti1Extension("comment", b"x" * (1_300_000)))
    img.header.extensions.append(nib.nifti1.Nifti1Extension("comment", b'{"SeriesDescription": "AX T2 FLAIR"}'))
    data = gzip.compress(img.to_bytes())
    fields = _run(qg._read_header_fields(_Ranged(data), "b", "patients/p/studies/s/series/x/big.nii.gz"))
    assert not fields.get("unreadable") and any("FLAIR" in d for d in fields["descriptions"]), fields["descriptions"][-2:]


# ----------------------------------------------------------------------------- O2 (G26)
class _StreamOnly:
    """A store as the base read it: a collection can only be streamed (no where(filter=) / limit)."""

    def __init__(self, docs):
        self.docs = docs

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def stream(self):
        return [type("D", (), {"to_dict": lambda self, d=d: d})() for d in self.docs]


def test_rc122_g26_o2_the_base_read_of_an_acquisition_record_with_the_flags_off(monkeypatch):
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", False)
    fid = "patients/p/studies/st/series/se/f.nii.gz"
    docs = [{"gcs_object_name": "patients/p/studies/st/series/se/other.nii.gz", "acquisition": {"manufacturer": "GE"}},
            {"gcs_object_name": fid, "acquisition": dict(ACQ)}]
    service = type("S", (), {"db": _StreamOnly(docs)})()
    assert lcs.read_source_acquisition(fid, service) == ACQ


# ----------------------------------------------------------------------------- O4
def test_rc122_o4_the_word_sets_follow_the_vocabulary_and_the_cache_is_bounded():
    vocab = qg.load_policy()["sequence"]["vocabulary"]
    qg._compiled(vocab)
    vocab["other_words"].append("zzqx")                                        # changed in place
    assert "zzqx" in qg._compiled(vocab)["other"], "stale word sets reused after an in-place change"
    for i in range(qg.COMPILED_MAX + 5):
        v = copy.deepcopy(vocab)
        v["other_words"].append(f"w{i}")
        qg._compiled(v)
    assert len(qg._COMPILED) <= qg.COMPILED_MAX
    with pytest.raises(TypeError):
        qg._policy()["sequence"]["vocabulary"]["other_words"].append("x")     # the shipped vocabulary is immutable


# ----------------------------------------------------------------------------- O5
def test_rc126_o5_one_source_of_truth_in_the_card():
    card = (ROOT / "frontend/src/components/BrowserFlamesCard.tsx").read_text(encoding="utf-8")
    assert "inFlight" not in card and "gateBefore" not in card
