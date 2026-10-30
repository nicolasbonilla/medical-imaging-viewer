"""Release 2026-10-25 — final check of PR #69 (dd22708..39d9730), the server-side part of R2.

The browser refuses the DIS confirmation unless every value of the open mask is drawn, with the region label the
server stored for it, in the standard 2D view. The server cannot see the screen. As a partial safeguard the client
now states the label table it drew (`drawn_labels_sha256`: SHA-256 of [id, name, colour] of every label but the
background, by id) and the server refuses a confirmation whose drawn table is not the stored one — e.g. after the
label preset was switched to "Default", which redraws juxtacortical lesions gold as "MS Lesion (Chronic)". The DIS
state serves the stored table (`regions.stored_labels`) so the viewer can compare value by value.

Written BEFORE the correction (fails on 39d9730). Nothing reaches a store or a cloud service (PRB-002).
"""
import hashlib
import json

import pytest

from app.models.schemas import LabelInfo
from app.services import dis_review_gate as gate
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (  # noqa: F401  (fixture)
    _dis, _mask, _seed, _service, _sha, client_for,
)

# The canonical text both sides digest (frontend/src/utils/drawnLabels.digest.test.ts uses the same vector).
MAGNIMS_PRESET = [(1, "Periventricular", "#FF0000"), (2, "Juxtacortical", "#00CC00"), (3, "Infratentorial", "#0066FF"),
                  (4, "Deep White Matter", "#FFD700"), (5, "Active (Gd+)", "#FF00FF"), (6, "Black Hole (T1)", "#9932CC")]
MAGNIMS_PRESET_TEXT = ('[[1,"Periventricular","#FF0000"],[2,"Juxtacortical","#00CC00"],[3,"Infratentorial","#0066FF"],'
                       '[4,"Deep White Matter","#FFD700"],[5,"Active (Gd+)","#FF00FF"],[6,"Black Hole (T1)","#9932CC"]]')
MAGNIMS_PRESET_SHA = "72bdfec92427dae7278166fdb50768a2bfdef44e3899db765ec5549ef906051d"
DEFAULT_PRESET = [LabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
                  LabelInfo(id=1, name="MS Lesion (Active)", color="#FF0000"),
                  LabelInfo(id=2, name="MS Lesion (Chronic)", color="#FFD700"),
                  LabelInfo(id=3, name="T2/FLAIR Hyperintensity", color="#4169E1"),
                  LabelInfo(id=4, name="Black Hole (T1)", color="#9932CC")]


def _labels(rows):
    return [LabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False)] + [
        LabelInfo(id=i, name=n, color=c) for i, n, c in rows]


def _post(client, body, sid="seg-1"):
    return client.post(f"/api/v1/segmentation/{sid}/review/confirm", json=body)


@pytest.mark.unit
def test_rc071_release_final_drawn_labels_digest_is_the_shared_canonical_text():
    assert hashlib.sha256(MAGNIMS_PRESET_TEXT.encode("utf-8")).hexdigest() == MAGNIMS_PRESET_SHA
    assert gate.drawn_labels_sha256(_labels(MAGNIMS_PRESET)) == MAGNIMS_PRESET_SHA
    # independent of the order, of the colour's letter case and of the background; not of a name or a colour
    shuffled = _labels([(i, n, c.lower()) for i, n, c in reversed(MAGNIMS_PRESET)])
    assert gate.drawn_labels_sha256(shuffled) == MAGNIMS_PRESET_SHA
    assert gate.drawn_labels_sha256([json.loads(json.dumps(r)) for r in
                                     [{"id": i, "name": n, "color": c} for i, n, c in MAGNIMS_PRESET]]) == MAGNIMS_PRESET_SHA
    assert gate.drawn_labels_sha256(_labels([(1, "Periventricular", "#FF0001")] + MAGNIMS_PRESET[1:])) != MAGNIMS_PRESET_SHA
    assert gate.drawn_labels_sha256(DEFAULT_PRESET) != MAGNIMS_PRESET_SHA


@pytest.mark.unit
def test_rc071_release_final_the_dis_state_serves_the_stored_label_table(client_for):
    svc = _service()
    _seed(svc, classified=True)
    regions = _dis(client_for(svc))["regions"]
    stored = {e["id"]: (e["name"], e["color"]) for e in regions["stored_labels"]}
    # Release 2026-10-30 (merge with #71): served as drawn — deep white matter in the shared region colour (the
    # fixture stores #CC79A7).
    assert stored == {1: ("Periventricular", "#E69F00"), 2: ("Juxtacortical", "#56B4E9"),
                      3: ("Infratentorial", "#009E73"), 4: ("Deep White Matter", "#D55E00")}


@pytest.mark.unit
def test_rc071_release_final_a_confirmation_drawn_with_other_labels_is_refused(client_for):
    svc = _service()
    mask = _mask()
    entry = _seed(svc, mask=mask, classified=True)
    client = client_for(svc)
    for drawn in (None, "", gate_digest_of(DEFAULT_PRESET), "e" * 64):
        body = {"mask_sha256": _sha(mask)}
        if drawn is not None:
            body["drawn_labels_sha256"] = drawn
        r = _post(client, body)
        assert r.status_code == 409, (drawn, r.text[:300])
        assert "label" in r.text.lower()
        assert getattr(entry["metadata"], "clinician_review", None) is None


@pytest.mark.unit
def test_rc071_release_final_a_confirmation_drawn_with_the_stored_labels_is_recorded(client_for):
    svc = _service()
    mask = _mask()
    entry = _seed(svc, mask=mask, classified=True)
    client = client_for(svc)
    stored = client.get("/api/v1/segmentation/seg-1").json()["metadata"]["labels"]
    r = _post(client, {"mask_sha256": _sha(mask), "drawn_labels_sha256": gate_digest_of(stored)})
    assert r.status_code == 200, r.text[:300]
    assert entry["metadata"].clinician_review.reviewed_by == "dr_rev"


def gate_digest_of(labels):
    """The digest computed the way the browser does (frontend/src/utils/drawnLabels.ts), independent of the gate —
    of the table AS THE VIEWER DRAWS IT (release 2026-10-30, merge with #71: region names in the shared colours)."""
    from app.api.routes.segmentation_regions import MAGNIMS_REGION_LABEL_COLORS
    shared = {k.lower(): v.upper() for k, v in MAGNIMS_REGION_LABEL_COLORS.items()}
    rows = []
    for lbl in labels:
        d = lbl if isinstance(lbl, dict) else lbl.model_dump()
        if isinstance(d.get("id"), int) and d["id"] > 0:
            rows.append([d["id"], str(d["name"]), shared.get(str(d["name"]).lower(), str(d["color"]).upper())])
    rows.sort(key=lambda r: r[0])
    return hashlib.sha256(json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
