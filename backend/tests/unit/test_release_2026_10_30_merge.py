"""Release 2026-10-30 — merge of #69 (release 2026-10-25) and #71 (PRB-004 .. PRB-010), server side.

#71 (PRB-010) draws a label named after a MAGNIMS region in the shared region colour, whatever colour was stored with
it: segmentations classified before #71 carry red / green / blue / gold, the viewer draws them orange / sky blue /
bluish green / vermillion (`withRegionColors`). #69's confirmation check compares the labels drawn with the label table
of the DIS state (R2), and the server compares the digest of the table the client drew with the stored table. On the
merged tree both must describe the stored table AS THE VIEWER DRAWS IT; otherwise every segmentation classified before
#71 is refused although it is drawn exactly as the display rule says, and a client stating colours the viewer never
draws would pass.

Written BEFORE the integration decision (fails on b0aae45). Nothing reaches a store or a cloud service (PRB-002).
"""
import hashlib
import json

import pytest

from app.api.routes.segmentation_regions import MAGNIMS_REGION_LABEL_COLORS
from app.models.schemas import LabelInfo
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (  # noqa: F401  (fixture)
    _FakeDB, _dis, _mask, _seed, _service, _sha, client_for,
)

STORED_BEFORE_71 = [(1, "Periventricular", "#FF0000"), (2, "Juxtacortical", "#00CC00"),
                    (3, "Infratentorial", "#0066FF"), (4, "Deep White Matter", "#FFD700")]


def _labels(rows):
    return [LabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False)] + [
        LabelInfo(id=i, name=n, color=c, opacity=0.6, visible=True) for i, n, c in rows]


def _as_drawn(rows):
    """What the viewer draws (frontend/src/utils/regionColors.ts `withRegionColors`), computed here independently of
    the gate: a region name takes the shared region colour."""
    shared = {k.lower(): v.upper() for k, v in MAGNIMS_REGION_LABEL_COLORS.items()}
    return [(i, n, shared.get(n.lower(), c.upper())) for i, n, c in rows]


def _digest(rows):
    rows = sorted([[i, n, c.upper()] for i, n, c in rows], key=lambda r: r[0])
    return hashlib.sha256(json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _classified_before_71(svc):
    entry = _seed(svc, classified=True)
    entry["metadata"].labels = _labels(STORED_BEFORE_71)
    if isinstance(getattr(svc, "_db", None), _FakeDB):
        svc._db.docs["seg-1"] = entry["metadata"].model_dump(mode="json")
    return entry


@pytest.mark.unit
def test_rc071_release_1030_the_dis_state_serves_the_labels_as_drawn(client_for):
    svc = _service()
    _classified_before_71(svc)
    regions = _dis(client_for(svc))["regions"]
    assert regions["classified"] is True
    served = [(e["id"], e["name"], e["color"]) for e in regions["stored_labels"]]
    assert served == _as_drawn(STORED_BEFORE_71)


@pytest.mark.unit
def test_rc071_release_1030_a_segmentation_classified_before_71_drawn_in_the_region_colours_is_confirmed(client_for):
    svc = _service()
    entry = _classified_before_71(svc)
    r = client_for(svc).post("/api/v1/segmentation/seg-1/review/confirm", json={
        "mask_sha256": _sha(_mask()), "drawn_labels_sha256": _digest(_as_drawn(STORED_BEFORE_71))})
    assert r.status_code == 200, r.text[:300]
    assert entry["metadata"].clinician_review.reviewed_by == "dr_rev"


@pytest.mark.unit
def test_rc071_release_1030_a_confirmation_stating_colours_the_viewer_never_draws_is_refused(client_for):
    svc = _service()
    entry = _classified_before_71(svc)
    r = client_for(svc).post("/api/v1/segmentation/seg-1/review/confirm", json={
        "mask_sha256": _sha(_mask()), "drawn_labels_sha256": _digest(STORED_BEFORE_71)})
    assert r.status_code == 409, r.text[:300]
    assert getattr(entry["metadata"], "clinician_review", None) is None
