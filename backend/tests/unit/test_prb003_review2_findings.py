"""PRB-003 — findings of the second independent review of PR #68 at 29abe29 (written BEFORE the corrections).

N1  label edits after the classification were trusted: `regions_state` checked only that the lesion voxels were
    unchanged, so one lesion half-painted juxtacortical gave a false MET, a lesion painted Active (Gd+) or a mask
    flattened back to label 1 a false NOT MET — each after a radiologist's confirmation. Now every connected
    lesion must carry exactly one region 1-4; a region that differs from the classifier's is a correction the
    radiologist sees listed and acknowledges in the confirmation (recorded, bound by its digest).
N3  the output check on the report model's text missed many wordings (en/es/de, markup, hyphens, tables,
    "not evaluated" plus a claim, wrapped sentences) and removed whole paragraph lines. It now works per sentence
    on normalised text, removes region tables and region headings — as a backstop.
N4  the not-evaluated report templates still asked for per-region sections and region columns.
N5  the confirmation history (names, ids, times) went to every role with patient access, unbounded; the AI
    assistant received the confirmer's user name.
N6  `persist_metadata` rewrote the whole metadata document from the instance's cached copy.
N7  a client lesion table without `segmentation_id` bypassed the report's binding; it is now derived on the server.

These tests drive the real routes and the real SegmentationService (datastore stubbed). They fail on 29abe29
(`records/risk_verification/PRB-003_review2_tests_on_29abe29_2026-10-24.json`).
Negative controls: scripts/safety/prb003_negative_controls.py (mutations N1-*, N3-*, ...).
"""
from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import LabelInfo, SegmentationResponse
from app.security import get_current_active_user
from app.security.models import UserRole
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (  # noqa: F401  (fixtures)
    D, H, W, FILE, MAGNIMS, _Storage, _assert_not_evaluated, _confirm, _dis, _lesion_regions, _mask, _seed,
    _service, _sha, _user, client_for, ms_server, report_env, _run,
)
from tests.unit.test_prb003_review1_findings import (  # noqa: F401  (fixtures)
    _FakeAnthropic, _classify, _review, e2e, _report,
)

ACTIVE = MAGNIMS + [LabelInfo(id=5, name="Active (Gd+)", color="#FF00FF")]


def _two_lesions(a=1, b=2):
    m = np.zeros((D, H, W), dtype=np.uint8)
    m[2:4, 2:5, 2:5] = a
    m[6:8, 12:15, 12:15] = b
    return m


def _confirm_ack(client, mask, corrections_sha256, sid="seg-1"):
    return client.post(f"/api/v1/segmentation/{sid}/review/confirm",
                       json={"mask_sha256": _sha(mask), "region_corrections_sha256": corrections_sha256})


def _classified(mask, labels=None):
    svc = _service()
    entry = _seed(svc, mask=mask)
    if labels is not None:
        entry["metadata"].labels = labels
    _classify(entry)
    return svc, entry


# ──────────────────────────────────────────── N1: one region per lesion, corrections acknowledged
@pytest.mark.unit
def test_rc070_n1_one_lesion_split_between_two_regions_is_never_evaluated(client_for):
    """Probe p2b: ONE connected lesion classified periventricular, half of it painted juxtacortical."""
    m = np.zeros((D, H, W), dtype=np.uint8)
    m[2:6, 2:8, 2:8] = 1
    svc, entry = _classified(m)
    split = m.copy()
    split[4:6, 2:8, 2:8] = 2
    entry["masks_3d"] = split
    client = client_for(svc)
    r = _confirm(client, _sha(split))
    assert r.status_code == 409, r.text[:300]
    body = _dis(client)
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "lesion_labels_invalid"
    assert body["regions"]["invalid_lesion_count"] == 1
    assert body["regions"]["invalid_lesions"][0]["labels"] == [1, 2]
    _review(entry)                                        # even a confirmation record bound to this mask
    _assert_not_evaluated(_dis(client_for(svc)))


@pytest.mark.unit
def test_rc070_n1_a_lesion_relabelled_active_is_never_evaluated(client_for):
    """Probe p2c: the periventricular lesion painted "Active (Gd+)" (label 5) has no region any more."""
    svc, entry = _classified(_two_lesions(1, 2))
    active = _two_lesions(5, 2)
    entry["masks_3d"] = active
    entry["metadata"].labels = ACTIVE
    client = client_for(svc)
    assert _confirm(client, _sha(active)).status_code == 409
    body = _dis(client)
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "lesion_labels_invalid"
    assert body["regions"]["invalid_lesions"][0]["label_names"] == ["Active (Gd+)"]
    _review(entry)
    _assert_not_evaluated(_dis(client_for(svc)))


@pytest.mark.unit
def test_rc070_n1_a_mask_flattened_to_one_label_needs_the_correction_acknowledged(client_for):
    """Probe p2d: a classified mask flattened back to label 1, same voxels (e.g. "overwrite" in the stale-save
    dialog). The juxtacortical lesion is now periventricular: listed, and evaluated only once acknowledged."""
    svc, entry = _classified(_two_lesions(1, 2))
    flat = _two_lesions(1, 1)
    entry["masks_3d"] = flat
    client = client_for(svc)
    body = _dis(client)
    _assert_not_evaluated(body)
    regions = body["regions"]
    assert regions["edited_after_classification"] is True and regions["correction_count"] == 1
    c = regions["corrections"][0]
    assert (c["lesion"], c["slice"], c["classified_region_name"], c["current_region_name"]) == (
        2, 6, "Juxtacortical", "Periventricular")
    assert _confirm(client, _sha(flat)).status_code == 409          # no acknowledgement
    _review(entry)                                                    # a record of mask + labels only
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "confirmation_outdated"
    r = _confirm_ack(client_for(svc), flat, regions["corrections_sha256"])
    assert r.status_code == 200, r.text[:300]
    review = entry["metadata"].clinician_review
    assert review.region_correction_count == 1 and review.region_corrections[0]["current_region"] == 1
    body = _dis(client_for(svc))
    assert body["evaluation_status"] == "evaluated" and body["dis_met_brain"] is False


@pytest.mark.unit
def test_rc070_n1_regions_relabelled_after_the_classification_need_an_acknowledgement(client_for):
    """Probe p2a: the classifier said deep white matter for both lesions; relabelled PV + JC by hand."""
    svc, entry = _classified(_two_lesions(4, 4))
    relabelled = _two_lesions(1, 2)
    entry["masks_3d"] = relabelled
    client = client_for(svc)
    assert _confirm(client, _sha(relabelled)).status_code == 409
    _assert_not_evaluated(_dis(client))
    digest = _dis(client)["regions"]["corrections_sha256"]
    assert _confirm_ack(client, relabelled, digest).status_code == 200
    body = _dis(client_for(svc))
    assert body["evaluation_status"] == "evaluated" and body["dis_met_brain"] is True
    assert [c["classified_region"] for c in entry["metadata"].clinician_review.region_corrections] == [4, 4]


@pytest.mark.unit
def test_rc071_n1_each_refusal_gives_its_own_reason(client_for):
    """Before the classification the radiologist is asked to classify; after it, to fix the lesions listed."""
    svc = _service()
    entry = _seed(svc)                                    # MAGNIMS labels, never classified
    r = _confirm(client_for(svc), _sha(entry["masks_3d"]))
    assert r.status_code == 409 and "region classification first" in r.json()["error"]["message"], r.text[:300]
    assert entry["metadata"].clinician_review is None
    _classify(entry)
    split = entry["masks_3d"].copy()
    split[2, 2, 2] = 2                                    # one voxel of the PV lesion painted JC
    entry["masks_3d"] = split
    r = _confirm(client_for(svc), _sha(split))
    assert r.status_code == 409, r.text[:300]
    assert "lesion 1 (slice 3): Periventricular + Juxtacortical" in r.json()["error"]["message"]


@pytest.mark.unit
def test_rc071_n1_an_acknowledgement_of_other_corrections_is_refused(client_for):
    svc, entry = _classified(_two_lesions(4, 4))
    relabelled = _two_lesions(1, 2)
    entry["masks_3d"] = relabelled
    assert _confirm_ack(client_for(svc), relabelled, "0" * 64).status_code == 409
    assert entry["metadata"].clinician_review is None


@pytest.mark.unit
def test_rc070_n1_a_classification_record_without_lesion_regions_does_not_count(client_for):
    svc = _service()
    entry = _seed(svc)
    from app.services import dis_review_gate as gate
    entry["metadata"].analysis_data = {"classification": {
        "method": "geometric", "classified_lesion_footprint_sha256": gate.footprint_sha256(entry["masks_3d"]),
        "classified_mask_sha256": _sha(entry["masks_3d"])}}
    _review(entry)
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "regions_not_classified"


@pytest.mark.unit
def test_rc070_n1_classify_regions_records_each_lesion_region(client_for, monkeypatch):
    import app.api.routes.segmentation_regions as regions_route

    svc = _service()
    entry = _seed(svc, mask=(_mask() > 0).astype(np.uint8))
    monkeypatch.setattr(svc, "list_segmentations", lambda file_id=None, file_ids=None: [], raising=False)
    monkeypatch.setattr(regions_route, "prepare_geometric_image", lambda affine, native, shape: np.ones(shape, np.uint8))
    monkeypatch.setattr(regions_route, "classify_lesions_geometric", lambda mask, image, spacing: {
        "classified_mask": _two_lesions(1, 2), "method": "geometric", "total_classified": 36, "processing_time_ms": 1,
        "lesions": [], "classification_summary": {}})
    r = client_for(svc).post("/api/v1/segmentation/seg-1/classify-regions", json={"method": "geometric"})
    assert r.status_code == 200, r.text[:300]
    rec = entry["metadata"].analysis_data["classification"]
    assert rec["classified_lesion_regions"] == _lesion_regions(_two_lesions(1, 2))


# ───────────────────────────────────────────── N3: the output check (a backstop), per sentence
from app.services import dis_review_gate as _g  # noqa: E402

CLAIMS = [
    ("en", "Lesions in periventricular, juxtacortical and infratentorial locations, fulfilling spatial dissemination."),
    ("en", "The distribution is disseminated in space (3 of 4 characteristic locations)."),
    ("en", "Findings satisfy the MRI criteria for dissemination in **space**."),
    ("en", "Dissemination-in-space criteria are fulfilled."),
    ("en", "Lesions involve ≥2 of the McDonald 2024 topographies (periventricular and juxtacortical)."),
    ("en", "Spatial distribution meets McDonald criteria."),
    ("en", "MRI shows multifocal lesions typical of MS in periventricular and juxtacortical regions."),
    ("en", "DIS: met (2/3 regions)."),
    ("en", "dis: met"),
    ("en", "D.I.S. criteria met."),
    ("es", "Las lesiones cumplen criterios de diseminación espacial (periventricular y yuxtacortical)."),
    ("es", "Cumple diseminación en espacio según McDonald."),
    ("es", "Lesiones en 2 de 4 localizaciones típicas de EM, compatible con DIS."),
    ("es", "Afectación de 3 de las 4 regiones características."),
    ("es", "Cumple criterios de diseminación espacial."),
    ("de", "Räumliche Streuung erfüllt (periventrikulär und juxtakortikal)."),
    ("de", "Die Kriterien der örtlichen Dissemination sind erfüllt."),
    ("de", "Läsionen in 2 von 4 typischen Lokalisationen, vereinbar mit räumlicher Ausbreitung."),
]


@pytest.mark.unit
@pytest.mark.parametrize("lang,claim", CLAIMS)
def test_rc070_n3_a_dis_statement_is_replaced(lang, claim):
    out, n = _g.scrub_unevaluated_dis(f"## FINDINGS\nTwo lesions.\n\n{claim}\n", lang)
    assert n >= 1 and claim not in out, out
    assert _g.NOT_EVALUATED_LINE[lang] in out
    assert out.startswith("## FINDINGS\nTwo lesions.")


@pytest.mark.unit
def test_rc070_n3_a_region_table_is_removed():
    text = ("## FINDINGS\n| Region | Present | Lesions |\n|---|---|---|\n| Periventricular | ✓ Present | 3 |\n"
            "| Juxtacortical | ✓ Present | 1 |\n\n| Metric | Value |\n|---|---|\n| Total lesion count | 4 |\n")
    out, n = _g.scrub_unevaluated_dis(text, "en")
    assert "Periventricular" not in out and "Juxtacortical" not in out and n >= 2
    assert "| Total lesion count | 4 |" in out                       # a table without regions is kept


@pytest.mark.unit
def test_rc070_n3_not_evaluated_plus_a_claim_is_caught():
    text = ("Dissemination in space: not evaluated. However, lesions involve 3 of 4 typical MS regions, "
            "consistent with DIS.")
    out, n = _g.scrub_unevaluated_dis(text, "en")
    assert n == 1 and "However" not in out and "3 of 4" not in out
    one = ("Dissemination in space was not evaluated, although lesions in 3 of 4 typical regions are consistent "
           "with DIS.")
    out, n = _g.scrub_unevaluated_dis(one, "en")
    assert n == 1 and "3 of 4" not in out


@pytest.mark.unit
def test_rc070_n3_a_region_heading_is_removed():
    text = "## FINDINGS\n### Periventricular White Matter\n- Three lesions, ovoid.\n### Deep White Matter\n- One lesion."
    out, n = _g.scrub_unevaluated_dis(text, "en")
    assert "### Periventricular" not in out and n == 1
    assert "### Deep White Matter" in out and "- Three lesions, ovoid." in out


@pytest.mark.unit
def test_rc070_n3_a_sentence_wrapped_over_two_lines_is_caught():
    text = ("## IMPRESSION\n1. Twelve T2 lesions with a typical demyelinating morphology.\n"
            "2. Dissemination in space\n   is suggested by lesions in three regions.")
    out, n = _g.scrub_unevaluated_dis(text, "en")
    assert n == 1 and "suggested by lesions in three regions" not in out
    assert "1. Twelve T2 lesions with a typical demyelinating morphology." in out


@pytest.mark.unit
def test_rc070_n3_only_the_statement_is_replaced_not_the_paragraph():
    text = ("Total lesion count 12; two ovoid lesions perpendicular to the ventricles; dissemination in space "
            "cannot be assessed here; mild atrophy for age.\n"
            "No evidence of disease activity; lesion burden stable. DIS assessment requires confirmation.")
    out, n = _g.scrub_unevaluated_dis(text, "en")
    assert n == 2
    for kept in ("Total lesion count 12", "mild atrophy for age.", "No evidence of disease activity",
                 "lesion burden stable."):
        assert kept in out, out
    assert "cannot be assessed here" not in out and "requires confirmation" not in out


@pytest.mark.unit
def test_rc070_n3_the_not_evaluated_sentence_itself_is_kept_unchanged():
    for lang, line in _g.NOT_EVALUATED_LINE.items():
        text = f"## DIS\n{line}\n\nTwo lesions, 0.07 mL."
        assert _g.scrub_unevaluated_dis(text, lang) == (text, 0)


@pytest.mark.unit
def test_rc070_n3_the_draft_states_how_many_statements_were_replaced(e2e):
    client, svc, provider, _ = e2e
    _seed(svc)
    provider.text = ("## FINDINGS\nTwo lesions; findings satisfy the criteria for dissemination in **space**.\n\n"
                     "| Region | Present |\n|---|---|\n| Periventricular | ✓ Present |\n")
    r = _report(client)
    assert r.status_code == 200, r.text[:300]
    content = r.json()["content"]
    assert "**space**" not in content and "| Periventricular |" not in content
    assert "2 statement(s)" in content


# ───────────────────────────────────── N4: no per-region template section without an evaluated DIS
REGION_REQUESTS = ("### Periventricular", "### Cortical / Juxtacortical", "### Infratentorial", "### Deep White Matter",
                   "### Regional Distribution", "MAGNIMS Region", "| Region |", "| # | Region",
                   "by anatomical region", "(region)", "Distribution pattern")


@pytest.mark.unit
@pytest.mark.parametrize("template", ["general", "ms_activity", "ms_lesion_burden", "ms_comprehensive",
                                      "ms_longitudinal"])
def test_rc070_n4_no_template_asks_for_regions_without_an_evaluated_dis(template):
    from app.services.brain_report_service import REPORT_TEMPLATES, dis_not_evaluated_template
    text = dis_not_evaluated_template(REPORT_TEMPLATES[template])
    print(f"\n===== {template} (DIS not evaluated) =====\n{text}")
    left = [p for p in REGION_REQUESTS if p in text]
    assert not left, f"{template} still asks for regions: {left}"
    for line in text.split("\n"):
        low = line.lower()
        if "not evaluated" in low or "never write" in low:
            continue                                  # the safety rule and the CMSC prohibition themselves
        assert "mcdonald" not in low and "periventricular" not in low and "juxtacortical" not in low \
            and "infratentorial" not in low, f"{template}: {line}"


# ─────────────────────────────────────── N5: who confirmed — radiologists and administrators only
def _confirmed_twice(client_for):
    svc, entry = _classified(_mask())
    assert _confirm(client_for(svc, username="dr_first"), _sha(entry["masks_3d"])).status_code == 200
    assert _confirm(client_for(svc, username="dr_second"), _sha(entry["masks_3d"])).status_code == 200
    return svc, entry


@pytest.mark.unit
@pytest.mark.parametrize("role,sees", [(UserRole.RADIOLOGIST, True), (UserRole.ADMIN, True),
                                       (UserRole.TECHNICIAN, False), (UserRole.VIEWER, False)])
def test_rc071_n5_names_and_history_only_for_radiologist_and_admin(client_for, role, sees):
    svc, entry = _confirmed_twice(client_for)
    body = client_for(svc, role=role).get("/api/v1/segmentation/seg-1").json()
    review, history = body["metadata"]["clinician_review"], body["metadata"]["clinician_review_history"]
    if sees:
        assert review["reviewed_by"] == "dr_first" and len(history) == 2
    else:
        assert review["reviewed_by"] is None and review["reviewed_by_id"] is None and history == []
        assert review["reviewed_by_role"] == "radiologist" and body["clinician_review_history_count"] == 2
        assert "dr_first" not in json.dumps(body) and "dr_second" not in json.dumps(body)
    dis = client_for(svc, role=role).get("/api/v1/segmentation/seg-1/dis-assessment").json()
    assert dis["evaluation_status"] == "evaluated"
    assert (dis["segmentation_review"]["reviewed_by"] == "dr_first") is sees
    assert dis["segmentation_review"]["reviewed_by_role"] == "radiologist"


@pytest.mark.unit
def test_rc071_n5_the_list_route_hides_names_from_other_roles(client_for, monkeypatch):
    svc, entry = _confirmed_twice(client_for)
    listed = [SegmentationResponse(segmentation_id="seg-1", file_id=FILE, metadata=entry["metadata"], total_slices=D)]
    monkeypatch.setattr(svc, "list_segmentations", lambda file_id=None, file_ids=None: listed, raising=False)
    r = client_for(svc, role=UserRole.TECHNICIAN).get("/api/v1/segmentation/list", params={"file_id": FILE})
    assert r.status_code == 200, r.text[:300]
    assert "dr_first" not in r.text and r.json()[0]["clinician_review_history_count"] == 2


@pytest.mark.unit
def test_rc071_n5_the_history_is_capped(client_for):
    svc, entry = _classified(_mask())
    client = client_for(svc)
    for _ in range(55):
        assert _confirm(client, _sha(entry["masks_3d"])).status_code == 200
    assert len(entry["metadata"].clinician_review_history) == 50
    assert len(svc._db.docs["seg-1"]["clinician_review_history"]) == 50


@pytest.mark.unit
def test_rc070_n5_the_assistant_never_receives_the_confirmer_name(ms_server, monkeypatch):
    evaluated = {"segmentation_id": "seg-1", "evaluation_status": "evaluated", "dis_met_brain": True,
                 "segmentation_review": {"status": "confirmed", "reviewed_by": "dr_rev", "reviewed_by_id": "u-1",
                                         "reviewed_by_role": "radiologist", "reviewed_at": "2026-10-24T10:00:00Z"}}
    posted = []

    async def api_get(path, params=None):
        if path.endswith("/dis-assessment"):
            return json.loads(json.dumps(evaluated))
        return {"metadata": {"analysis_data": {}}} if path == "/segmentation/seg-1" else {"total_count": 2}

    async def api_post_compute(path, body):
        posted.append(body)
        return {"content": "draft"}

    monkeypatch.setattr(ms_server, "api_get", api_get)
    monkeypatch.setattr(ms_server, "api_post_compute", api_post_compute)
    out = _run(ms_server.summarize_dis_items("seg-1"))
    review = out["dis_assessment"]["segmentation_review"]
    assert "dr_rev" not in json.dumps(out) and "u-1" not in json.dumps(out)
    assert (review["reviewed_by_role"], review["reviewed_at"]) == ("radiologist", "2026-10-24T10:00:00Z")
    _run(ms_server.generate_ms_report("seg-1"))
    assert "dr_rev" not in json.dumps(posted)


@pytest.mark.unit
def test_rc070_n5_the_report_model_never_receives_the_confirmer_name(report_env):
    client, svc, report, _ = report_env
    mask = _mask()
    entry = _seed(svc, mask=mask)
    _classify(entry)
    _review(entry, by="dr_named")
    r = client.post("/api/v1/ai/report/generate", json={"template_type": "general", "segmentation_id": "seg-1",
                                                         "findings": {"dis_assessment": {"segmentation_id": "seg-1"}}})
    assert r.status_code == 200, r.text[:300]
    sent = report.calls[0]["findings"]["dis_assessment"]
    assert sent["evaluation_status"] == "evaluated" and "dr_named" not in json.dumps(sent)


# ─────────────────────────────────────────────── N6: only the review fields are written
@pytest.mark.unit
def test_rc071_n6_the_confirmation_writes_only_the_review_fields(client_for):
    svc, entry = _classified(_mask())
    svc._db.docs["seg-1"]["description"] = "renamed by another instance"     # newer than this instance's copy
    svc._db.docs["seg-1"]["validation_source"] = "edited-elsewhere"
    assert _confirm(client_for(svc), _sha(entry["masks_3d"])).status_code == 200
    stored = svc._db.docs["seg-1"]
    assert stored["description"] == "renamed by another instance" and stored["validation_source"] == "edited-elsewhere"
    assert stored["clinician_review"]["reviewed_by"] == "dr_rev"
    assert [(kind, sorted(data)) for kind, _id, data in svc._db.writes] == [
        ("update", ["clinician_review", "clinician_review_history"])]


@pytest.mark.unit
def test_rc071_n6_a_document_changed_between_read_and_write_is_a_conflict(client_for):
    svc, entry = _classified(_mask())
    db = svc._db
    real_collection = db.collection

    def collection(name):                      # another instance writes right after this one read the document
        c = real_collection(name)

        class _C:
            def document(self, doc_id):
                d = c.document(doc_id)

                class _D:
                    def get(self):
                        snap = d.get()
                        db.times[doc_id] += 1
                        return snap

                    def update(self, data, option=None):
                        return d.update(data, option=option)

                    def set(self, data):
                        return d.set(data)
                return _D()
        return _C()

    db.collection = collection
    r = _confirm(client_for(svc), _sha(entry["masks_3d"]))
    assert r.status_code == 409, r.text[:300]
    assert "seg-1" not in svc.segmentations_cache
    assert db.docs["seg-1"].get("clinician_review") is None


@pytest.mark.unit
def test_rc071_n6_history_written_by_another_instance_is_kept(client_for):
    svc, entry = _classified(_mask())
    svc._db.docs["seg-1"]["clinician_review_history"] = [{
        "event": "voided", "by": None, "by_id": None, "at": "2000-01-01T00:00:00Z", "mask_sha256": None,
        "labels_sha256": None, "reason": "mask_changed", "previous_reviewer": "dr_other"}]
    assert _confirm(client_for(svc), _sha(entry["masks_3d"])).status_code == 200
    events = [(e["event"], e.get("previous_reviewer") or e.get("by")) for e in
              svc._db.docs["seg-1"]["clinician_review_history"]]
    assert events == [("voided", "dr_other"), ("confirmed", "dr_rev")]


# ──────────────────────────────────── N7: the report's lesion table is derived on the server
@pytest.mark.unit
def test_rc070_n7_a_client_lesion_table_never_reaches_the_report(report_env):
    client, svc, report, _ = report_env
    entry = _seed(svc)
    _classify(entry)
    _review(entry)
    forged = {"total_count": 99, "total_burden_ml": 9.9,                 # no segmentation_id: the old bypass
              "regions": {"Infratentorial": {"lesion_count": 99}},
              "lesions": [{"id": 1, "region": "Infratentorial", "volume_mm3": 9900.0}]}
    r = client.post("/api/v1/ai/report/generate", json={"template_type": "general", "segmentation_id": "seg-1",
                                                         "findings": {"lesion_analysis": forged}})
    assert r.status_code == 200, r.text[:300]
    sent = report.calls[0]["findings"]["lesion_analysis"]
    assert sent["segmentation_id"] == "seg-1" and sent["total_count"] == 2
    assert "Infratentorial" not in json.dumps(sent)


@pytest.mark.unit
def test_rc070_n7_a_lesion_table_that_cannot_be_computed_is_refused(report_env, monkeypatch):
    import app.api.routes.ai_report as ai_report
    client, svc, report, _ = report_env
    _seed(svc)

    class _NoImage:
        async def download_file(self, bucket, file_id):
            raise RuntimeError("source image unavailable")

    monkeypatch.setattr(ai_report, "_dis_services", lambda: (svc, _NoImage()), raising=False)
    r = client.post("/api/v1/ai/report/generate", json={"template_type": "general", "segmentation_id": "seg-1",
                                                         "findings": {"lesion_analysis": {"total_count": 2}}})
    assert r.status_code == 422, r.text[:300]
    assert report.calls == []
