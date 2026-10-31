"""PRB-029 and PRB-030 — the server-side part of the checks made before a radiologist confirms in the viewer.

PRB-029 — the AI-draft review (`POST /segmentation/{id}/ai-review/confirm`, RC-047; the AI report stays ON in
production by owner decision) had no drawn-lesion check: it was accepted whatever labels the mask was drawn with.
It now takes the same server-side safeguard as the DIS confirmation (release 2026-10-25, final check of PR #69, R2):
the client states the label table it drew the mask with (`drawn_labels_sha256`) and a table other than the stored
one, as the viewer draws it (`dis_review_gate.stored_labels`), is refused. (The drawn-lesion check itself runs in
the browser, shared with the DIS confirmation: frontend tests.)

PRB-030 (L1 of the last check of PR #69) — a radiologist could select another image while the segmentation stayed
open; the mask was then drawn sheared or cut off on the other grid and Confirm was accepted. Both confirmations
now state the image the standard 2D view draws under the mask (`displayed_image_file_id`); the server reads its
NIfTI header and refuses (409) unless it lies on the mask's grid: the mask's shape in the image's voxel order and
the same voxel-to-scanner transform as the segmentation's own image (the RC-039 tolerance), and in the same study
(on MNI-registered data every image of every visit shares one grid). An image that cannot be read is refused; an
image the user may not open is not read (404).

Written BEFORE the correction (the refusals fail on ca600c2; the accepted cases are positive controls). Nothing
reaches a store or a cloud service (PRB-002).
"""
import nibabel as nib
import numpy as np
import pytest
from fastapi import HTTPException

from app.core import container
from app.main import app
from app.models.schemas import LabelInfo
from app.services import dis_review_gate as gate
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (  # noqa: F401  (fixture)
    D, FILE, H, PID, STUDY, W, _classification, _drawn, _mask, _prov, _seed, _service, _sha, client_for,
)

OTHER_SERIES = "66666666-6666-6666-6666-666666666666"
OTHER_STUDY = "77777777-7777-7777-7777-777777777777"
T1_SAME_GRID = f"patients/{PID}/studies/{STUDY}/series/{OTHER_SERIES}/t1.nii.gz"
SHEARED = f"patients/{PID}/studies/{STUDY}/series/{OTHER_SERIES}/sheared.nii.gz"
SHIFTED = f"patients/{PID}/studies/{STUDY}/series/{OTHER_SERIES}/shifted.nii.gz"
RESAMPLED = f"patients/{PID}/studies/{STUDY}/series/{OTHER_SERIES}/resampled.nii.gz"
CUT = f"patients/{PID}/studies/{STUDY}/series/{OTHER_SERIES}/cut.nii.gz"
BROKEN = f"patients/{PID}/studies/{STUDY}/series/{OTHER_SERIES}/broken.nii.gz"
OTHER_VISIT_SAME_GRID = f"patients/{PID}/studies/{OTHER_STUDY}/series/{OTHER_SERIES}/flair.nii.gz"


def _nifti(shape=(H, W, D), affine=None):
    img = nib.Nifti1Image(np.zeros(shape, dtype=np.uint8), np.eye(4) if affine is None else affine)
    return img.to_bytes()


def _affine(**cells):
    a = np.eye(4)
    for key, value in cells.items():
        a[int(key[1]), int(key[2])] = value
    return a


IMAGES = {
    FILE: _nifti(),
    T1_SAME_GRID: _nifti(),
    OTHER_VISIT_SAME_GRID: _nifti(),
    SHEARED: _nifti(affine=_affine(a01=0.5)),               # sheared in-plane
    SHIFTED: _nifti(affine=_affine(a03=0.5)),               # half a millimetre to the side
    RESAMPLED: _nifti(affine=_affine(a00=1.2, a11=1.2)),    # another voxel size, same array shape
    CUT: _nifti(shape=(H, W, D - 2)),                       # fewer slices: the mask would be cut off
    BROKEN: b"not a NIfTI file",
}


class _ImageStorage:
    """The images of the study (header + zero voxels); records what was read."""

    def __init__(self):
        self.read = []

    async def download_file(self, bucket, file_id):
        self.read.append(file_id)
        if file_id not in IMAGES:
            raise FileNotFoundError(file_id)
        return IMAGES[file_id]


def _client(client_for, svc):
    client = client_for(svc)
    storage = _ImageStorage()
    app.dependency_overrides[container.get_storage_service] = lambda: storage
    return client, storage


def _atlas_classified(svc, mask=None):
    """A segmentation whose regions came from the atlas (MNI): no per-lesion review (PRB-028) is involved."""
    entry = _seed(svc, mask=mask)
    record = _classification(entry["masks_3d"])
    record["classification"]["method"] = "msmask"
    entry["metadata"].analysis_data = record
    return entry


def _confirm_dis(client, entry, displayed=FILE, drawn=None):
    body = {"mask_sha256": _sha(entry["masks_3d"]), "drawn_labels_sha256": drawn or _drawn(client)}
    if displayed is not None:
        body["displayed_image_file_id"] = displayed
    return client.post("/api/v1/segmentation/seg-1/review/confirm", json=body)


def _confirm_ai(client, entry, displayed=FILE, drawn="from-server"):
    body = {"mask_sha256": _sha(entry["masks_3d"])}
    if drawn == "from-server":
        body["drawn_labels_sha256"] = _drawn(client)
    elif drawn is not None:
        body["drawn_labels_sha256"] = drawn
    if displayed is not None:
        body["displayed_image_file_id"] = displayed
    return client.post("/api/v1/segmentation/seg-1/ai-review/confirm", json=body)


def _ai_draft(svc, mask=None):
    return _seed(svc, mask=mask, ai_provenance=_prov())


def _ai_unreviewed(entry):
    return entry["metadata"].ai_provenance.review_status == "unreviewed"


DEFAULT_PRESET = [LabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
                  LabelInfo(id=1, name="MS Lesion (Active)", color="#FF0000"),
                  LabelInfo(id=2, name="MS Lesion (Chronic)", color="#FFD700"),
                  LabelInfo(id=3, name="T2/FLAIR Hyperintensity", color="#4169E1"),
                  LabelInfo(id=4, name="Black Hole (T1)", color="#9932CC")]


# ─────────────────────────────────────────────── PRB-029: the AI-draft review states the drawn label table
@pytest.mark.unit
@pytest.mark.parametrize("drawn", [None, "", "e" * 64, "default-preset"])
def test_rc091_prb029_ai_review_refused_unless_drawn_with_the_stored_labels(client_for, drawn):
    svc = _service()
    entry = _ai_draft(svc)
    client, _storage = _client(client_for, svc)
    if drawn == "default-preset":
        drawn = gate.drawn_labels_sha256(gate.stored_labels(DEFAULT_PRESET))
    r = _confirm_ai(client, entry, drawn=drawn)
    assert r.status_code == 409, r.text[:300]
    assert "label" in r.json()["error"]["message"].lower()
    assert _ai_unreviewed(entry)


@pytest.mark.unit
def test_rc091_prb029_ai_review_drawn_with_the_stored_labels_over_its_own_image_is_confirmed(client_for):
    """Positive control: the stored table as the viewer draws it, the segmentation's own image."""
    svc = _service()
    entry = _ai_draft(svc)
    client, _storage = _client(client_for, svc)
    r = _confirm_ai(client, entry)
    assert r.status_code == 200, r.text[:300]
    assert entry["metadata"].ai_provenance.review_status == "confirmed"


# ─────────────────────────────────────────────── PRB-030: the image under the mask lies on the mask's grid
ROUTES = ["dis", "ai"]


def _setup(route, client_for, mask=None):
    svc = _service()
    entry = _atlas_classified(svc, mask) if route == "dis" else _ai_draft(svc, mask)
    client, storage = _client(client_for, svc)
    send = _confirm_dis if route == "dis" else _confirm_ai
    return entry, client, storage, (lambda displayed: send(client, entry, displayed=displayed))


def _not_confirmed(route, entry):
    return entry["metadata"].clinician_review is None if route == "dis" else _ai_unreviewed(entry)


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
def test_rc092_prb030_the_image_under_the_mask_must_be_stated(client_for, route):
    entry, _client_, _storage, send = _setup(route, client_for)
    for displayed in (None, ""):
        r = send(displayed)
        assert r.status_code == 409, (displayed, r.text[:300])
    assert _not_confirmed(route, entry)


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("displayed", [SHEARED, SHIFTED, RESAMPLED, CUT])
def test_rc092_prb030_an_image_on_another_grid_is_refused(client_for, route, displayed):
    entry, _client_, _storage, send = _setup(route, client_for)
    r = send(displayed)
    assert r.status_code == 409, r.text[:300]
    assert "grid" in r.json()["error"]["message"].lower()
    assert _not_confirmed(route, entry)


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
def test_rc092_prb030_an_image_of_another_visit_is_refused_even_on_the_same_grid(client_for, route):
    entry, _client_, _storage, send = _setup(route, client_for)
    r = send(OTHER_VISIT_SAME_GRID)
    assert r.status_code == 409, r.text[:300]
    assert _not_confirmed(route, entry)


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
def test_rc092_prb030_an_image_that_cannot_be_read_is_refused(client_for, route):
    entry, _client_, _storage, send = _setup(route, client_for)
    for displayed in (BROKEN, f"patients/{PID}/studies/{STUDY}/series/{OTHER_SERIES}/missing.nii.gz", "../etc/passwd"):
        r = send(displayed)
        assert r.status_code == 409, (displayed, r.text[:300])
    assert _not_confirmed(route, entry)


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
def test_rc092_prb030_a_mask_whose_shape_is_not_the_image_grid_is_refused(client_for, route):
    """The segmentation's own image, but the mask does not have its shape (it would be drawn sheared)."""
    small = np.zeros((D, H, W - 1), dtype=np.uint8)
    small[2:4, 2:5, 2:5] = 1
    small[6:8, 12:15, 12:15] = 2
    entry, _client_, _storage, send = _setup(route, client_for, mask=small)
    r = send(FILE)
    assert r.status_code == 409, r.text[:300]
    assert _not_confirmed(route, entry)


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
def test_rc092_prb030_an_image_the_user_may_not_open_is_not_read(client_for, route, monkeypatch):
    import app.api.routes.segmentation as seg_routes

    async def deny(*, file_ids, user, patient_service, care_team_service):
        if any(f != FILE for f in file_ids):
            raise HTTPException(status_code=404, detail="Not found")

    entry, _client_, storage, send = _setup(route, client_for)
    monkeypatch.setattr(seg_routes, "authorize_file_scope", deny)
    r = send(T1_SAME_GRID)
    assert r.status_code == 404, r.text[:300]
    assert T1_SAME_GRID not in storage.read
    assert _not_confirmed(route, entry)


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("displayed", [FILE, T1_SAME_GRID])
def test_rc092_prb030_the_own_image_or_another_series_of_the_study_on_the_same_grid_is_accepted(client_for, route, displayed):
    """Positive control: the segmentation's own image, or e.g. the T1 of the same study on the same grid."""
    entry, _client_, _storage, send = _setup(route, client_for)
    r = send(displayed)
    assert r.status_code == 200, r.text[:300]
    assert not _not_confirmed(route, entry)
