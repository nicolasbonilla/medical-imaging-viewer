"""PRB-003 — findings of the independent review of PR #68 at 4c601f2 (written BEFORE the corrections).

Blocker 1  DIS was evaluated on any confirmed mask, whatever its labels meant: `compute_dis_criteria` reads
           label ids 1/2/3 as PV/JC/IT, so a confirmed binary "Lesion" mask gave a confirmed NOT MET and the
           default preset (1 = MS Lesion Active, 2 = Chronic) a false MET. DIS is now evaluated only on a
           MAGNIMS-labelled mask whose lesions went through the region classification (classified lesion
           footprint recorded), and the confirmation binds the mask AND the label scheme.
Major 2    the report's DIS block was re-derived for whatever segmentation the client named, and a merge with
           PR #67 drops `evaluation_status` — an end-to-end test through the real report service (provider
           mocked) now fails if the state is lost.
Major 3    region presence of an unconfirmed segmentation reached the reader, the report and the assistant
           without a caveat.
Major 4    the report templates still asked the model for DIS; nothing checked the model's text.
Major 5    the confirmation was not idempotent, kept no history, rewrote the mask object, ignored durability.
Minor      label renaming after a confirmation; race between the hash and the spacing download;
           information-for-safety text on non-lesion tools.

These tests drive the real routes, the real SegmentationService (datastore stubbed) and the real report
service with only the model provider replaced. They fail on 4c601f2
(`records/risk_verification/PRB-003_review1_tests_on_4c601f2_2026-10-24.json`).
Negative controls: scripts/safety/prb003_negative_controls.py (R1-R*, mutations of the review corrections).
"""
from __future__ import annotations

import logging
import sys
import types

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import LabelInfo
from app.security import get_current_active_user
from app.security.models import UserRole
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (  # noqa: F401  (fixtures)
    D, H, W, MAGNIMS, CONCLUSION_KEYS, _Storage, _assert_not_evaluated, _classification, _confirm, _dis, _mask,
    _prov, _seed, _service, _sha, _user, client_for, ms_server,
)

BINARY = [LabelInfo(id=0, name="Background", color="#000000"), LabelInfo(id=1, name="Lesion", color="#FF0000")]
DEFAULT_PRESET = [LabelInfo(id=0, name="Background", color="#000000"),
                  LabelInfo(id=1, name="MS Lesion (Active)", color="#FF0000"),
                  LabelInfo(id=2, name="MS Lesion (Chronic)", color="#FFD700"),
                  LabelInfo(id=3, name="T2/FLAIR Hyperintensity", color="#4169E1"),
                  LabelInfo(id=4, name="Black Hole (T1)", color="#9932CC")]


def _gate():
    from app.services import dis_review_gate
    return dis_review_gate


def _classify(entry, mask=None):
    """Record a region classification for the lesions of `mask` (default: the stored mask)."""
    m = entry["masks_3d"] if mask is None else mask
    meta = entry["metadata"]
    meta.analysis_data = {**(meta.analysis_data or {}), **_classification(m)}   # N1: with each lesion's region


def _review(entry, by="dr_rev"):
    """A clinician confirmation bound to the stored mask AND label scheme."""
    entry["metadata"].clinician_review = {
        "reviewed_by": by, "reviewed_by_id": "u-1", "reviewed_at": "2026-10-24T10:00:00Z",
        "reviewed_mask_sha256": _sha(entry["masks_3d"]),
        "reviewed_labels_sha256": _gate().labels_sha256(entry["metadata"].labels)}
    # re-validate through the model (a dict assigned to a pydantic field is not coerced)
    from app.models.schemas import SegmentationMetadata
    entry["metadata"] = SegmentationMetadata(**entry["metadata"].model_dump())


def _binary(mask):
    return (mask > 0).astype(np.uint8)


# ─────────────────────────────────────────────── Blocker 1: the label scheme and the classification
@pytest.mark.unit
def test_rc070_r1_a_confirmed_binary_lesion_mask_is_not_evaluated(client_for):
    """Real PV + JC lesions labelled 'Lesion' (1): the old route returned a confirmed NOT MET."""
    svc = _service()
    mask = _binary(_mask())
    entry = _seed(svc, mask=mask)
    entry["metadata"].labels = BINARY
    client = client_for(svc)
    _confirm(client, _sha(mask))
    body = _dis(client)
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "regions_not_classified"


@pytest.mark.unit
def test_rc070_r1_the_default_label_preset_confirmed_is_not_evaluated(client_for):
    """'MS Lesion (Active)' = 1 and '(Chronic)' = 2 were read as PV and JC: a false MET."""
    svc = _service()
    entry = _seed(svc)
    entry["metadata"].labels = DEFAULT_PRESET
    client = client_for(svc)
    _confirm(client, _sha(entry["masks_3d"]))
    body = _dis(client)
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "regions_not_classified"


@pytest.mark.unit
def test_rc070_r1_classified_lesions_relabelled_with_another_scheme_are_not_evaluated(client_for):
    """A classification record and a confirmation bound to the CURRENT labels do not make the default preset
    ('MS Lesion (Active)' = 1 ...) a set of regions."""
    svc = _service()
    entry = _seed(svc)
    _classify(entry)
    entry["metadata"].labels = DEFAULT_PRESET
    _review(entry)                                         # bound to the default-preset labels
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "regions_not_classified"
    assert body["regions"]["label_scheme"] == "other"


@pytest.mark.unit
def test_rc070_r1_magnims_names_without_a_recorded_classification_are_not_evaluated(client_for):
    svc = _service()
    entry = _seed(svc)            # MAGNIMS names, lesions never classified (e.g. a mask uploaded with these labels)
    _review(entry)
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "regions_not_classified"


@pytest.mark.unit
def test_rc070_r1_a_classification_of_other_lesions_does_not_count(client_for):
    svc = _service()
    entry = _seed(svc)
    other = _mask()
    other[0, 0, 0] = 4                                  # one more lesion voxel: another lesion footprint
    _classify(entry, other)
    _review(entry)
    _assert_not_evaluated(_dis(client_for(svc)))


@pytest.mark.unit
def test_rc070_r1_a_mask_value_outside_its_label_scheme_is_not_evaluated(client_for):
    svc = _service()
    mask = _mask()
    mask[5, 10, 10] = 7                                  # a value no MAGNIMS label defines
    entry = _seed(svc, mask=mask)
    _classify(entry)
    _review(entry)
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "regions_not_classified"


@pytest.mark.unit
def test_rc070_r1_classified_and_confirmed_is_evaluated(client_for):
    svc = _service()
    entry = _seed(svc)
    _classify(entry)
    _review(entry)
    body = _dis(client_for(svc))
    assert body["evaluation_status"] == "evaluated" and body["dis_met_brain"] is True
    assert body["regions"]["classified"] is True


@pytest.mark.unit
def test_rc070_r1_a_region_corrected_after_classification_keeps_the_classification(client_for):
    """The classification is bound to the classified LESIONS (footprint): a radiologist may correct a region
    label. Changed by the second review of PR #68 (N1): the correction is listed and must be acknowledged in the
    confirmation — a confirmation of mask + labels alone no longer covers it."""
    svc = _service()
    entry = _seed(svc)
    _classify(entry)
    corrected = entry["masks_3d"].copy()
    corrected[6:8, 12:15, 12:15] = 4                     # JC lesion re-labelled deep white matter
    entry["masks_3d"] = corrected
    _review(entry)
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["regions"]["classified"] is True and body["regions"]["edited_after_classification"] is True
    assert body["regions"]["correction_count"] == 1
    r = client_for(svc).post("/api/v1/segmentation/seg-1/review/confirm", json={
        "mask_sha256": _sha(corrected), "region_corrections_sha256": body["regions"]["corrections_sha256"]})
    assert r.status_code == 200, r.text[:300]
    body = _dis(client_for(svc))
    assert body["evaluation_status"] == "evaluated" and body["dis_met_brain"] is False


@pytest.mark.unit
def test_rc070_r1_a_lesion_added_after_classification_needs_a_new_classification(client_for):
    svc = _service()
    entry = _seed(svc)
    _classify(entry)
    grown = entry["masks_3d"].copy()
    grown[0, 18, 18] = 1                                  # a new lesion voxel, painted as PV by hand
    entry["masks_3d"] = grown
    _review(entry)
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "regions_not_classified"


@pytest.mark.unit
def test_rc071_r1_the_confirmation_is_refused_before_the_regions_are_classified(client_for):
    svc = _service()
    entry = _seed(svc)
    r = _confirm(client_for(svc), _sha(entry["masks_3d"]))
    assert r.status_code == 409, r.text[:300]
    assert "classif" in r.text.lower()
    assert getattr(entry["metadata"], "clinician_review", None) is None


@pytest.mark.unit
def test_rc071_r1_the_confirmation_binds_the_mask_and_the_label_scheme(client_for):
    svc = _service()
    entry = _seed(svc)
    _classify(entry)
    assert _confirm(client_for(svc), _sha(entry["masks_3d"])).status_code == 200
    review = entry["metadata"].clinician_review
    assert review.reviewed_mask_sha256 == _sha(entry["masks_3d"])
    assert review.reviewed_labels_sha256 == _gate().labels_sha256(entry["metadata"].labels)


@pytest.mark.unit
def test_rc071_r1_a_confirmation_given_for_another_label_scheme_does_not_count(client_for):
    """Even before any save voids it: labels changed by another path (still MAGNIMS) are not the confirmed scheme."""
    svc = _service()
    entry = _seed(svc)
    _classify(entry)
    _review(entry)                                         # bound to labels 0-4
    entry = svc.segmentations_cache["seg-1"]
    entry["metadata"].labels = [*MAGNIMS, LabelInfo(id=5, name="Active (Gd+)", color="#FF00FF")]
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "confirmation_outdated"


@pytest.mark.unit
def test_rc071_r1_renaming_a_label_after_the_confirmation_voids_it(client_for):
    svc = _service()
    entry = _seed(svc)
    _classify(entry)
    client = client_for(svc)
    assert _confirm(client, _sha(entry["masks_3d"])).status_code == 200
    renamed = [lbl.model_dump() for lbl in MAGNIMS]
    renamed[2]["name"] = "Deep White Matter 2"           # Juxtacortical renamed
    r = client.put("/api/v1/segmentation/seg-1/labels", json=renamed)
    assert r.status_code == 200, r.text[:300]
    assert entry["metadata"].clinician_review is None
    assert entry["metadata"].clinician_review_history[-1].event == "voided"
    assert entry["metadata"].clinician_review_history[-1].reason == "labels_changed"
    _assert_not_evaluated(_dis(client))


@pytest.mark.unit
@pytest.mark.parametrize("role,allowed", [(UserRole.VIEWER, False), (UserRole.ADMIN, False),
                                          (UserRole.TECHNICIAN, True), (UserRole.RADIOLOGIST, True)])
def test_rc071_r1_only_clinical_roles_may_rename_labels(client_for, role, allowed):
    svc = _service()
    entry = _seed(svc)
    r = client_for(svc, role=role).put("/api/v1/segmentation/seg-1/labels", json=[l.model_dump() for l in BINARY])
    assert (r.status_code == 200) is allowed, (role, r.status_code, r.text[:200])
    assert (entry["metadata"].labels == BINARY) is allowed


@pytest.mark.unit
def test_rc070_r1_classify_regions_records_the_classified_lesions(client_for, monkeypatch):
    import app.api.routes.segmentation_regions as regions

    svc = _service()
    entry = _seed(svc, mask=_binary(_mask()))
    monkeypatch.setattr(svc, "list_segmentations", lambda file_id=None, file_ids=None: [], raising=False)
    monkeypatch.setattr(regions, "prepare_geometric_image", lambda affine, native, shape: np.ones(shape, np.uint8))
    monkeypatch.setattr(regions, "classify_lesions_geometric", lambda mask, image, spacing: {
        "classified_mask": _mask(), "method": "geometric", "total_classified": 36, "processing_time_ms": 1,
        "lesions": [], "classification_summary": {}})
    r = client_for(svc).post("/api/v1/segmentation/seg-1/classify-regions", json={"method": "geometric"})
    assert r.status_code == 200, r.text[:300]
    rec = entry["metadata"].analysis_data["classification"]
    assert rec["classified_lesion_footprint_sha256"] == _gate().footprint_sha256(entry["masks_3d"])
    assert _gate().labels_are_magnims(entry["metadata"].labels)


@pytest.mark.unit
def test_rc071_r1_an_ai_draft_needs_its_own_review_and_the_dis_confirmation(client_for):
    svc = _service()
    entry = _seed(svc, segmentation_type="automatic", ai_provenance=_prov())
    _classify(entry)
    client = client_for(svc)
    r = _confirm(client, _sha(entry["masks_3d"]))         # AI review not confirmed for this mask
    assert r.status_code == 409, r.text[:300]
    body = _dis(client)
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "ai_review_missing"
    entry["metadata"].ai_provenance = _prov(review_status="confirmed", reviewed_by="dr_rev", reviewed_at="x",
                                            reviewed_mask_sha256=_sha(entry["masks_3d"]))
    body = _dis(client)                                    # AI review alone is not the DIS confirmation
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "segmentation_not_confirmed"
    assert _confirm(client, _sha(entry["masks_3d"])).status_code == 200
    assert _dis(client)["evaluation_status"] == "evaluated"


# ─────────────────────────────────────────── Major 5: idempotent, auditable, durable confirmation
def _classified_seg():
    svc = _service()
    entry = _seed(svc)
    _classify(entry)
    return svc, entry


@pytest.mark.unit
def test_rc071_r5_a_second_confirmation_keeps_the_first_reviewer_and_is_recorded(client_for):
    svc, entry = _classified_seg()
    assert _confirm(client_for(svc, username="dr_first"), _sha(entry["masks_3d"])).status_code == 200
    first = entry["metadata"].clinician_review
    r = _confirm(client_for(svc, username="dr_second"), _sha(entry["masks_3d"]))
    assert r.status_code == 200, r.text[:300]
    assert r.json()["already_confirmed"] is True
    assert entry["metadata"].clinician_review == first and first.reviewed_by == "dr_first"
    events = [(e.event, e.by) for e in entry["metadata"].clinician_review_history]
    assert events == [("confirmed", "dr_first"), ("confirmation_repeated", "dr_second")]


@pytest.mark.unit
def test_rc071_r5_a_voided_confirmation_is_kept_in_the_history(client_for):
    svc, entry = _classified_seg()
    digest = _sha(entry["masks_3d"])
    assert _confirm(client_for(svc), digest).status_code == 200
    changed = entry["masks_3d"].copy()
    changed[6:8, 12:15, 12:15] = 3
    entry["masks_3d"] = changed
    svc.persist("seg-1")
    last = entry["metadata"].clinician_review_history[-1]
    assert (last.event, last.reason, last.mask_sha256, last.previous_reviewer) == ("voided", "mask_changed", digest, "dr_rev")
    assert last.at


@pytest.mark.unit
def test_rc071_r5_the_confirmation_does_not_rewrite_the_mask_object(client_for):
    svc, entry = _classified_seg()
    writes = []
    svc._save_masks_to_gcs = lambda *a, **k: writes.append(a)
    assert _confirm(client_for(svc), _sha(entry["masks_3d"])).status_code == 200
    assert writes == []                                   # metadata only: the next save keeps its generation
    assert svc._db.docs["seg-1"]["clinician_review"]["reviewed_by"] == "dr_rev"


@pytest.mark.unit
def test_rc071_r5_a_confirmation_that_was_not_stored_durably_is_refused_and_undone(client_for):
    svc, entry = _classified_seg()

    class _Down:
        def collection(self, name):
            raise RuntimeError("datastore unavailable")

    svc._db = _Down()
    r = _confirm(client_for(svc), _sha(entry["masks_3d"]))
    assert r.status_code == 503, r.text[:300]
    assert entry["metadata"].clinician_review is None and entry["metadata"].clinician_review_history == []


@pytest.mark.unit
def test_rc071_r5_a_mask_changed_by_another_session_discards_the_cached_entry(client_for):
    svc, entry = _classified_seg()
    svc._gcs_generations["seg-1"] = 5

    class _Blob:
        generation = 6                                    # another session saved a newer mask

        def reload(self):
            return None

    class _Bucket:
        def blob(self, path):
            return _Blob()

    svc._gcs_bucket = _Bucket()
    r = _confirm(client_for(svc), _sha(entry["masks_3d"]))
    assert r.status_code == 409, r.text[:300]
    assert "seg-1" not in svc.segmentations_cache


@pytest.mark.unit
def test_rc071_r5_the_confirming_user_is_logged(client_for, caplog):
    svc, entry = _classified_seg()
    with caplog.at_level(logging.INFO):
        assert _confirm(client_for(svc), _sha(entry["masks_3d"])).status_code == 200
    assert any(getattr(rec, "reviewed_by", None) == "dr_rev" for rec in caplog.records)


# ─────────────────────────────────────────────────────────────── Minor 8: hash and spacing race
@pytest.mark.unit
def test_rc070_r8_a_mask_saved_during_the_assessment_is_never_cached_as_its_result(client_for):
    svc, entry = _classified_seg()
    _review(entry)
    entry = svc.segmentations_cache["seg-1"]
    snapshot = _sha(entry["masks_3d"])

    class _SlowStorage(_Storage):
        async def download_file(self, bucket, file_id):
            # a concurrent edit (the paint route edits the cached mask in place) removes the JC lesion
            svc.segmentations_cache["seg-1"]["masks_3d"][6:8, 12:15, 12:15] = 0
            return await super().download_file(bucket, file_id)

    from app.core import container
    client = client_for(svc)
    app.dependency_overrides[container.get_storage_service] = lambda: _SlowStorage()
    body = client.get("/api/v1/segmentation/seg-1/dis-assessment").json()
    assert body["segmentation_review"]["current_mask_sha256"] == snapshot
    # the result is that of the snapshot the gate checked (PV + JC), not of a mask changed meanwhile
    assert body["evaluation_status"] == "evaluated" and body["dis_met_brain"] is True
    assert "dis_assessment" not in (svc.segmentations_cache["seg-1"]["metadata"].analysis_data or {})


# ─────────────────────────────────────────── Minor 9: the notice only for lesion-detection tools
@pytest.mark.unit
@pytest.mark.parametrize("source,expected", [("lst-ai-v1.0.3", True), ("flames-v1.0", True),
                                             ("synthseg-v2.0", False), ("mindglide-v1.0-structures", False)])
def test_rc072_r9_the_healthy_brain_notice_only_for_lesion_detection_tools(client_for, source, expected):
    svc = _service()
    _seed(svc, segmentation_type="automatic", validation_source=source)
    body = _dis(client_for(svc))
    assert ("information_for_safety" in body) is expected
    assert "lesion marking" in _gate().AUTOMATIC_MARKING_NOTICE["en"]


# ─────────────────────────────────────── Major 3: region presence of an unconfirmed segmentation
@pytest.mark.unit
def test_rc070_r3_lesion_analysis_states_whether_its_regions_are_confirmed(client_for):
    svc = _service()
    entry = _seed(svc)
    client = client_for(svc)
    r = client.get("/api/v1/segmentation/seg-1/lesion-analysis")
    assert r.status_code == 200, r.text[:300]
    status = r.json()["region_status"]
    assert status["confirmed"] is False and "not a DIS assessment" in status["note"]
    _classify(entry)
    _review(entry)
    status = client_for(svc).get("/api/v1/segmentation/seg-1/lesion-analysis").json()["region_status"]
    assert status["confirmed"] is True


@pytest.mark.unit
def test_rc070_r3_assistant_region_tools_carry_the_caveat(ms_server, monkeypatch):
    async def api_get(path, params=None):
        if path.endswith("/dis-assessment"):
            return {"segmentation_id": "seg-1", "evaluation_status": "not_evaluated"}
        if path.endswith("/lesion-analysis"):
            return {"total_count": 2, "regions": {"Periventricular": {"lesion_count": 1}}}
        return {"metadata": {"analysis_data": {"classification": {"lesions": [{"region": "Periventricular"}]}}}}

    monkeypatch.setattr(ms_server, "api_get", api_get)
    out = _run(ms_server.get_region_classification("seg-1"))
    assert "not a DIS assessment" in out["note"]
    out = _run(ms_server.summarize_dis_items("seg-1"))
    assert "not a DIS assessment" in out["regions_note"]


@pytest.mark.unit
def test_rc070_r2_the_assistant_report_names_its_segmentation(ms_server, monkeypatch):
    posted = []

    async def api_get(path, params=None):
        return {"segmentation_id": "seg-1", "total_count": 1}

    async def api_post_compute(path, body):
        posted.append((path, body))
        return {"report_id": "r", "content": "draft"}

    monkeypatch.setattr(ms_server, "api_get", api_get)
    monkeypatch.setattr(ms_server, "api_post_compute", api_post_compute)
    _run(ms_server.generate_ms_report("seg-1"))
    assert posted and posted[-1][0] == "/ai/report/generate"
    assert posted[-1][1]["segmentation_id"] == "seg-1"


def _run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────── Major 2 and 4: the report, end to end through the real report service
class _FakeAnthropic:
    """Stands in for the model provider only; records the prompts and answers with `text`."""

    def __init__(self, text="## FINDINGS\nTwo lesions."):
        self.calls, self.text = [], text
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=self.text)],
                                     usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))


@pytest.fixture
def e2e(monkeypatch):
    import app.api.routes.ai_report as ai_report
    from app.services.brain_report_service import BrainReportService

    svc = _service()
    provider = _FakeAnthropic()
    authorized = []

    async def authorize(specs, user):
        authorized.extend(specs)

    monkeypatch.setattr(BrainReportService, "_get_client", lambda self: provider)
    monkeypatch.setattr(ai_report, "_dis_services", lambda: (svc, _Storage()), raising=False)
    monkeypatch.setattr(ai_report, "authorize_mask_specs", authorize, raising=False)
    # Second review of PR #68 (N2): the same fixture must drive PR #67's route after the merge — it checks the
    # report's segmentation and reads its patient (CAPA-014). Absent before the merge: nothing is replaced.

    async def authorize_segmentation(segmentation_id, user):
        return "11111111-1111-1111-1111-111111111111"

    monkeypatch.setattr(ai_report, "authorize_segmentation_id", authorize_segmentation, raising=False)
    try:
        from tests.unit.test_capa014_report_provider_payload import _Patients, _record
        monkeypatch.setattr(ai_report, "_patient_service", lambda: _Patients(_record()), raising=False)
    except ImportError:                                   # PR #67 not merged yet
        pass
    app.dependency_overrides[get_current_active_user] = lambda: _user()
    yield TestClient(app, raise_server_exceptions=False), svc, provider, authorized
    app.dependency_overrides.clear()


def _lesions(sid="seg-1"):
    return {"segmentation_id": sid, "total_count": 2, "total_burden_mm3": 72.0, "total_burden_ml": 0.072,
            "regions": {"Periventricular": {"lesion_count": 1, "total_volume_mm3": 36.0, "total_volume_ml": 0.036},
                        "Juxtacortical": {"lesion_count": 1, "total_volume_mm3": 36.0, "total_volume_ml": 0.036}},
            "lesions": [{"id": 1, "region": "Periventricular", "volume_mm3": 36.0, "volume_ml": 0.036,
                         "size_category": "small", "centroid": {"z": 3, "y": 3, "x": 3}},
                        {"id": 2, "region": "Juxtacortical", "volume_mm3": 36.0, "volume_ml": 0.036,
                         "size_category": "small", "centroid": {"z": 7, "y": 13, "x": 13}}]}


def _report(client, template="ms_lesion_burden", language="en", sid="seg-1", dis_sid="seg-1", lesions=True):
    findings = {"dis_assessment": {"segmentation_id": dis_sid}}
    if lesions:
        findings["lesion_analysis"] = _lesions(sid)
    body = {"template_type": template, "language": language, "findings": findings}
    if sid is not None:
        body["segmentation_id"] = sid
    return client.post("/api/v1/ai/report/generate", json=body)


@pytest.mark.unit
def test_rc070_r2_e2e_a_confirmed_dis_reaches_the_model_through_the_real_report_service(e2e):
    """Fails after a merge that drops `evaluation_status` on the way to the prompt (PR #67's payload guard)."""
    client, svc, provider, _ = e2e
    entry = _seed(svc)
    _classify(entry)
    _review(entry)
    r = _report(client, template="ms_comprehensive")
    assert r.status_code == 200, r.text[:300]
    call = provider.calls[0]
    assert "DIS Assessment: MET" in call["messages"][0]["content"]
    assert "NOT EVALUATED" not in call["messages"][0]["content"]
    assert "DIS checklist table" in call["system"]                 # the template's DIS section is kept


DIS_INSTRUCTIONS = ("DIS checklist table", "typical MS regions", "DIS regions involved", "Organize by DIS regions",
                    "Tabulate lesion presence", "consistent with dissemination in space", "MAGNIMS DIS regions",
                    "Present DIS data", "4 DIS anatomical regions")


@pytest.mark.unit
@pytest.mark.parametrize("template", ["general", "ms_activity", "ms_lesion_burden", "ms_comprehensive",
                                      "ms_longitudinal"])
def test_rc070_r4_without_an_evaluated_dis_no_template_asks_for_dis(e2e, template):
    client, svc, provider, _ = e2e
    _seed(svc)                                                       # not confirmed
    r = _report(client, template=template)
    assert r.status_code == 200, r.text[:300]
    system = provider.calls[0]["system"]
    left = [p for p in DIS_INSTRUCTIONS if p in system]
    assert not left, f"{template}: the system prompt still asks for DIS: {left}"
    assert "not evaluated (requires clinician review of the segmentation)" in system
    assert "NOT EVALUATED" in provider.calls[0]["messages"][0]["content"]


@pytest.mark.unit
@pytest.mark.parametrize("lang,stated,kept", [
    ("en", "Lesions involve 2 of 4 typical MS regions, consistent with dissemination in space.",
     "Dissemination in space: not evaluated"),
    ("es", "Las lesiones afectan 2 de 4 regiones típicas, compatible con diseminación en el espacio.",
     "Diseminación en el espacio: no evaluada"),
    ("de", "Die Läsionen betreffen 2 von 4 typischen MS-Regionen, vereinbar mit räumlicher Dissemination.",
     "Räumliche Dissemination: nicht beurteilt"),
])
def test_rc070_r4_a_dis_statement_written_by_the_model_is_replaced(e2e, lang, stated, kept):
    client, svc, provider, _ = e2e
    _seed(svc)
    provider.text = f"## FINDINGS\nTwo lesions.\n\n### DIS\n{stated}\n"
    r = _report(client, language=lang)
    assert r.status_code == 200, r.text[:300]
    content = r.json()["content"]
    assert stated not in content
    assert kept in content


@pytest.mark.unit
def test_rc072_r4_the_notice_does_not_claim_the_draft_is_not_software_text(e2e):
    client, svc, _provider, _ = e2e
    _seed(svc)
    content = _report(client).json()["content"]
    assert "comes from the software" not in content
    assert "must not be read as a statement on dissemination in space" in content


@pytest.mark.unit
def test_rc070_r2_the_dis_block_is_bound_to_the_report_segmentation(e2e):
    """Another segmentation's confirmed MET cannot be carried into this report."""
    client, svc, provider, authorized = e2e
    _seed(svc, sid="seg-1")                                          # the report's segmentation: not confirmed
    other = _seed(svc, sid="seg-2")
    _classify(other)
    _review(other)
    r = _report(client, sid="seg-1", dis_sid="seg-2")
    assert r.status_code == 409, r.text[:300]
    assert provider.calls == []


@pytest.mark.unit
def test_rc070_r2_a_dis_block_without_the_report_segmentation_is_not_evaluated(e2e):
    client, svc, provider, authorized = e2e
    other = _seed(svc, sid="seg-2")
    _classify(other)
    _review(other)
    r = _report(client, sid=None, dis_sid="seg-2", lesions=True)
    assert r.status_code == 200, r.text[:300]
    assert "NOT EVALUATED" in provider.calls[0]["messages"][0]["content"]
    assert authorized == []


@pytest.mark.unit
def test_rc070_r2_lesion_measurements_of_another_segmentation_are_refused(e2e):
    client, svc, provider, _ = e2e
    _seed(svc, sid="seg-1")
    findings = {"lesion_analysis": _lesions("seg-9")}
    r = client.post("/api/v1/ai/report/generate", json={"template_type": "general", "segmentation_id": "seg-1",
                                                         "findings": findings})
    assert r.status_code == 409, r.text[:300]
    assert provider.calls == []


@pytest.mark.unit
def test_rc070_r3_without_an_evaluated_dis_the_report_receives_no_region_breakdown(e2e):
    client, svc, provider, _ = e2e
    _seed(svc)
    assert _report(client).status_code == 200
    prompt = provider.calls[0]["messages"][0]["content"]
    for region in ("Periventricular", "Juxtacortical"):
        assert region not in prompt, f"{region} reached the model for an unconfirmed segmentation"
    assert "Total lesions: 2" in prompt                              # measurements are kept
