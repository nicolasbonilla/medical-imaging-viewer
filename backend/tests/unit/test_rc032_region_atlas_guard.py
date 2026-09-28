"""RC-032 — risk control for HAZ-005 (wrong MAGNIMS region -> wrong DIS); REQ-SAFE-021; CAPA-006.

Each MAGNIMS classification path is valid only under a precondition. Before 2026-09-28 none was
enforced, and the region routes were dead. Pinned here:

1. OUTAGE: classify-regions and generate-zone-map resolved voxel spacing from SegmentationMetadata,
   which never carries it -> 500 on every call since 2026-07-18 (e39cdaa); generate-zone-map's
   fallback also read undefined names (NameError). Spacing now comes from the source image.
2. ATLAS OFF-MNI: the MNI152 MSMask atlas was applied to any image, with no registration. The gate
   (looks_mni) now requires an isotropic, axis-aligned, unpermuted grid with an MNI field of view
   PER AXIS and an MNI grid centre; the first version of the gate compared sorted extents and let
   native 2D FLAIR through (review 2026-09-28).
3. ORIENTATION: the fresh atlas zone map was combined with the lesion mask in a different axis
   order (silently rotated zones on cubic grids); a PERSISTED zone map came back transposed after a
   GCS reload (generate-zone-map overwrote it without the RC-031 marker). The zone map is now always
   generated fresh, transposed, shape-checked; the overwrite is gone.
4. PARCELLATION MISREAD: a MAGNIMS zone map (labels 1-4) was accepted as a FreeSurfer parcellation
   -> its DWM label 4 read as the lateral ventricle -> DWM lesions reported Periventricular.
5. GEOMETRIC FALLBACK: the image reached the heuristics in native order (brain outline silently
   dropped on every non-cubic scan -> juxtacortical almost never assigned) and the IT rule ran on
   whatever array axis 0 was. The image is now reordered, and sagittal/coronal/reversed or >30 deg
   tilted slice axes, blank or mismatched images are refused.
Review round 2 (2026-09-28): both routes lacked object-level authorization (RC-029 was wired only
in segmentation.py); a parcellation of ANOTHER image, an instance-labelled lesion mask or a
parcellation without cortex labels was accepted; faults in a path degraded silently or were
reported as refusals; generate-zone-map deleted old zone maps before the new one was persisted.

Negative controls: executed one mutation at a time; the final run against this file is recorded in
docs/iec62304/records/risk_verification/RC-032_negative_controls_2026-09-28.json (and in
rc_test_manifest.json, RC-032).
"""
from datetime import datetime

import numpy as np
import nibabel as nib
import pytest

import app.services.ms_region_classifier as rc

try:
    from app.main import app
    from app.core.container import get_segmentation_service, get_storage_service
    from app.security import get_current_active_user
    from app.security.models import User, UserRole
    from app.models.schemas import SegmentationMetadata, LabelInfo
    from app.security.resource_access import require_segmentation_access
    import app.security.resource_access as resource_access
    import app.api.routes.segmentation_regions as regions_route
    from fastapi.testclient import TestClient
    _APP_ERROR = None
except Exception as exc:  # pragma: no cover
    _APP_ERROR = exc

# FSL MNI152 1 mm and 2 mm (native (a0, a1, k), LAS), ICBM 2009c 1 mm (RAS)
MNI1_AFFINE = np.array([[-1.0, 0, 0, 90], [0, 1.0, 0, -126], [0, 0, 1.0, -72], [0, 0, 0, 1]])
MNI1_SHAPE = (182, 218, 182)
MNI_AFFINE = np.array([[-2.0, 0, 0, 90], [0, 2.0, 0, -126], [0, 0, 2.0, -72], [0, 0, 0, 1]])
MNI_SHAPE = (91, 109, 91)                        # 2 mm: used by the heavy tests (CI timeout)
ICBM_AFFINE = np.array([[1.0, 0, 0, -96], [0, 1.0, 0, -132], [0, 0, 1.0, -78], [0, 0, 0, 1]])
ICBM_SHAPE = (193, 229, 193)


@pytest.fixture(autouse=True, scope="module")
def _cache_atlas_zone_maps():
    """The atlas zone map depends only on the grid; cache the REAL function's output per grid so
    the heavy tests stay inside CI's per-test timeout. Refusals are never cached (they re-raise)."""
    real = rc.generate_zone_map_atlas
    cache = {}

    def cached(target_img, voxel_spacing, *a, **k):
        key = (tuple(target_img.shape), np.asarray(target_img.affine).tobytes(), tuple(voxel_spacing))
        if key not in cache:
            cache[key] = real(target_img, voxel_spacing, *a, **k)
        out = dict(cache[key])
        out["zone_mask"] = np.array(out["zone_mask"], copy=True)
        return out

    rc.generate_zone_map_atlas = cached
    yield
    rc.generate_zone_map_atlas = real


def _oblique(base, deg=10.0):
    t = np.deg2rad(deg)
    rot = np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])
    A = base.copy()
    A[:3, :3] = rot @ A[:3, :3]
    return A


def _centred(spacing, shape, centre=(0.0, -18.0, 18.0)):
    """An axis-aligned affine whose grid centre sits at `centre` (the MNI template centre)."""
    A = np.diag([*spacing, 1.0])
    A[:3, 3] = np.asarray(centre) - A[:3, :3] @ ((np.asarray(shape) - 1) / 2.0)
    return A


# ----------------------------------------------------------------------------- the grid gate
@pytest.mark.unit
class TestRC032Gate:
    def test_rc032_accepts_mni_grids(self):
        assert rc.looks_mni(MNI1_AFFINE, MNI1_SHAPE)
        assert rc.looks_mni(MNI_AFFINE, MNI_SHAPE)
        assert rc.looks_mni(ICBM_AFFINE, ICBM_SHAPE)
        assert rc.looks_mni(MNI1_AFFINE, MNI1_SHAPE + (3,))                    # 4-D
        hdr = nib.Nifti1Header()
        hdr["sform_code"], hdr["qform_code"] = 4, 0
        assert rc.looks_mni(MNI1_AFFINE, MNI1_SHAPE, hdr)

    def test_rc032_rejects_oblique_and_clinical_grids(self):
        assert not rc.looks_mni(_oblique(MNI1_AFFINE), MNI1_SHAPE)
        assert not rc.looks_mni(np.diag([0.9, 0.9, 5.0, 1.0]), (256, 256, 30))
        assert not rc.looks_mni(np.eye(4), (256, 256, 176))                     # native 3D
        assert not rc.looks_mni(np.eye(4), ICBM_SHAPE)                          # origin at corner

    def test_rc032_rejects_what_the_first_gate_accepted(self):
        """Review 2026-09-28: sorted extents + no isotropy/centre check let these through."""
        flair = (240, 240, 48)
        assert not rc.looks_mni(_centred((0.9375, 0.9375, 3.0), flair), flair)  # anisotropic 2D FLAIR
        permuted = np.array([[0, -1.0, 0, 90], [1.0, 0, 0, -126], [0, 0, 1.0, -72], [0, 0, 0, 1]])
        assert not rc.looks_mni(permuted, (218, 182, 182))                      # axes swapped
        far = MNI1_AFFINE.copy()
        far[:3, 3] += (0, 25.0, 0)
        assert not rc.looks_mni(far, MNI1_SHAPE)                                # 25 mm off-centre
        hdr = nib.Nifti1Header()
        hdr["sform_code"], hdr["qform_code"] = 0, 0
        assert not rc.looks_mni(MNI1_AFFINE, MNI1_SHAPE, hdr)                   # no spatial transform
        assert not rc.looks_mni(np.eye(3), MNI1_SHAPE)                          # not an affine

    def test_rc032_rejects_a_centred_isotropic_native_scan_by_field_of_view(self):
        """Isotropic, axis-aligned, centred like MNI — only the per-axis FOV tells it apart."""
        shape = (256, 256, 160)
        aff = _centred((1.0, 1.0, 1.0), shape, centre=(0.0, -14.0, 14.0))
        assert not rc.looks_mni(aff, shape)

    def test_rc032_longitudinal_route_uses_the_same_gate(self):
        """The longitudinal compare route carried its own weaker copy (sorted extents) from
        2026-08-22; it must be the classifier's gate."""
        from app.api.routes import segmentation_analysis
        assert segmentation_analysis._looks_mni is rc.looks_mni
        flair = (240, 240, 48)
        assert not segmentation_analysis._looks_mni(_centred((0.9375, 0.9375, 3.0), flair), flair)

    def test_rc032_zone_map_refuses_non_mni_image(self):
        img = nib.Nifti1Image(np.zeros((256, 256, 30), np.float32), np.diag([0.9, 0.9, 5.0, 1.0]))
        with pytest.raises(rc.NotMNISpaceError):
            rc.generate_zone_map_atlas(img, (5.0, 0.9, 0.9))


# ----------------------------------------------------------------------------- orientation
def _blob_mask_native(shape, centers, r=2):
    m = np.zeros(shape, np.uint8)
    for (a, b, c) in centers:
        m[a - r:a + r + 1, b - r:b + r + 1, c - r:c + r + 1] = 1
    return m


def _world_to_vox(affine, xyz):
    return tuple(int(round(v)) for v in np.linalg.inv(affine) @ np.r_[xyz, 1.0])[:3]


MNI_POINTS = ((-16, 0, 22), (16, -40, 20), (-40, -20, 50), (0, -30, -40), (28, 10, 28))


def _regions_by_native_centroid(result):
    """{rounded native centroid (a0, a1, k): region_id} from an orientation-consistent result."""
    return {tuple(int(round(l["centroid"][ax])) for ax in ("z", "y", "x")): l["region_id"]
            for l in result["lesions"]}


def _regions_by_internal_centroid(result):
    """Same key from an internal-order (k, a0, a1) result: map back to (a0, a1, k)."""
    out = {}
    for l in result["lesions"]:
        k, a0, a1 = (int(round(l["centroid"][ax])) for ax in ("z", "y", "x"))
        out[(a0, a1, k)] = l["region_id"]
    return out


@pytest.mark.unit
class TestRC032Orientation:
    @pytest.mark.timeout(300)
    def test_rc032_atlas_classification_matches_orientation_consistent_reference(self):
        centers = [_world_to_vox(MNI_AFFINE, xyz) for xyz in MNI_POINTS]
        native = _blob_mask_native(MNI_SHAPE, centers)
        img = nib.Nifti1Image(np.zeros(MNI_SHAPE, np.float32), MNI_AFFINE)
        zone = rc.generate_zone_map_atlas(img, (2, 2, 2))["zone_mask"]
        ref = _regions_by_native_centroid(rc.classify_from_zone_mask(native, zone, (2, 2, 2)))
        internal = np.ascontiguousarray(np.transpose(native, (2, 0, 1)))    # app (k, a0, a1)
        got = _regions_by_internal_centroid(rc.classify_lesions_with_atlas(internal, img, (2, 2, 2)))
        assert len(ref) == len(centers) and got == ref                      # per lesion

    @pytest.mark.timeout(300)
    def test_rc032_cubic_grid_is_not_silently_rotated(self):
        """On a cubic grid the pre-fix code raised nothing and applied rotated zones."""
        shape = (100, 100, 100)
        aff = _centred((-2.0, 2.0, 2.0), shape)
        assert rc.looks_mni(aff, shape)
        centers = [_world_to_vox(aff, xyz) for xyz in MNI_POINTS]
        native = _blob_mask_native(shape, centers)
        img = nib.Nifti1Image(np.zeros(shape, np.float32), aff)
        zone = rc.generate_zone_map_atlas(img, (2, 2, 2))["zone_mask"]
        ref = _regions_by_native_centroid(rc.classify_from_zone_mask(native, zone, (2, 2, 2)))
        internal = np.ascontiguousarray(np.transpose(native, (2, 0, 1)))
        got = _regions_by_internal_centroid(rc.classify_lesions_with_atlas(internal, img, (2, 2, 2)))
        assert len(ref) == len(centers) and got == ref

    def test_rc032_zone_map_of_another_grid_is_refused(self):
        lesion = np.zeros((20, 30, 40), np.uint8)
        lesion[5:8, 5:8, 5:8] = 1
        with pytest.raises(ValueError):
            rc.classify_from_zone_mask(lesion, np.zeros((40, 30, 20), np.uint8), (1, 1, 1))


# ----------------------------------------------------------------------------- the real route
def _admin():
    now = datetime.utcnow()
    return User(id="admin-1", username="admin", email="admin@example.com", full_name="Admin",
                role=UserRole.ADMIN, is_active=True, is_locked=False, email_verified=True,
                created_at=now, updated_at=now)


class _Blob:
    def __init__(self, uploads, path):
        self.uploads, self.path = uploads, path

    def upload_from_string(self, *a, **k):
        self.uploads.append(self.path)

    def upload_from_file(self, *a, **k):
        self.uploads.append(self.path)


class _Bucket:
    def __init__(self):
        self.uploads = []

    def blob(self, path):
        return _Blob(self.uploads, path)


class _Seg:
    def __init__(self, masks, analysis_data=None, descriptions=None, file_ids=None, fail_persist=()):
        self.masks, self.analysis_data = masks, analysis_data or {}
        self.descriptions = descriptions or {}
        self.file_ids, self.fail_persist = file_ids or {}, set(fail_persist)
        self.deleted, self.created = [], None
        self.gcs_bucket = _Bucket()          # records any RAW upload the route makes

    def get_loaded(self, sid):
        if sid not in self.masks:
            return None
        return {"masks_3d": self.masks[sid],
                "metadata": SegmentationMetadata(
                    file_id=self.file_ids.get(sid, f"img-{sid}"), description=self.descriptions.get(sid),
                    analysis_data=dict(self.analysis_data) if sid == "les" else {},
                    labels=[LabelInfo(id=1, name="MS Lesion", color="#ff0000", opacity=0.5, visible=True)])}

    def get_mask(self, sid):
        return self.masks.get(sid)

    def get_cached(self, sid):
        return self.get_loaded(sid)

    def list_segmentations(self, file_id=None):
        return [type("Cand", (), {"segmentation_id": sid})() for sid in self.masks]

    def persist(self, sid):
        if sid in self.fail_persist:
            raise RuntimeError("storage unavailable")
        return None

    def delete_segmentation(self, sid):
        self.deleted.append(sid)

    def create_segmentation(self, file_id, image_shape, labels, description):
        self.created = {"file_id": file_id, "image_shape": image_shape, "description": description}
        return type("Seg", (), {"segmentation_id": "zone-new"})()

    def set_mask(self, sid, mask):
        self.created["mask_shape"] = mask.shape


class _Storage:
    def __init__(self, shape, affine, zooms=None, data=None):
        self.shape, self.affine, self.zooms, self.data = shape, affine, zooms, data

    async def download_file(self, bucket, file_id):
        data = self.data if self.data is not None else np.zeros(self.shape, np.uint8)
        img = nib.Nifti1Image(data, self.affine)
        if self.zooms:
            img.header.set_zooms(self.zooms)
        return img.to_bytes()


@pytest.fixture
def route():
    if _APP_ERROR is not None:
        pytest.fail(f"FastAPI app not importable: {_APP_ERROR!r}")   # never a silent skip

    def make(seg, storage, user=None, authorize=True):
        app.dependency_overrides[get_current_active_user] = user or _admin
        app.dependency_overrides[get_segmentation_service] = lambda: seg
        app.dependency_overrides[get_storage_service] = lambda: storage
        if authorize:     # object-level authorization is exercised by its own tests below
            app.dependency_overrides[require_segmentation_access] = lambda: None
        else:
            app.dependency_overrides.pop(require_segmentation_access, None)
        return TestClient(app)
    yield make
    for dep in (get_current_active_user, get_segmentation_service, get_storage_service,
                require_segmentation_access):
        app.dependency_overrides.pop(dep, None)


CLIN_SHAPE = (120, 140, 60)                     # native (a0, a1, k): axial, 1 x 1 x 2 mm, RAS
CLIN_AFFINE = np.diag([1.0, 1.0, 2.0, 1.0])     # anisotropic, FOV ~119 x 139 x 118 mm -> NOT MNI


def _brain_native(shape=CLIN_SHAPE):
    """An ellipsoid 'brain' (radii 50 x 60 x 50 mm) centred in a clinical, non-MNI grid."""
    a0, a1, k = np.ogrid[:shape[0], :shape[1], :shape[2]]
    inside = ((a0 - 60) / 50.0) ** 2 + ((a1 - 70) / 60.0) ** 2 + ((k - 30) / 25.0) ** 2 <= 1.0
    return (inside * 100).astype(np.uint8)


def _clinical_case(affine=CLIN_AFFINE):
    """Lesion 3-5 mm under the lateral brain surface, mid-height: juxtacortical by the heuristics."""
    mask = np.zeros((CLIN_SHAPE[2], CLIN_SHAPE[0], CLIN_SHAPE[1]), np.uint8)   # internal (k, a0, a1)
    mask[29:32, 13:16, 69:72] = 1
    storage = _Storage(CLIN_SHAPE, affine, zooms=(1.0, 1.0, 2.0), data=_brain_native())
    return mask, storage


def _mni_case():
    native = _blob_mask_native(MNI_SHAPE, [_world_to_vox(MNI_AFFINE, xyz) for xyz in MNI_POINTS[:3]])
    internal = np.ascontiguousarray(np.transpose(native, (2, 0, 1)))
    return internal, _Storage(MNI_SHAPE, MNI_AFFINE, zooms=(2.0, 2.0, 2.0))


def _post(client, sid="les", **body):
    return client.post(f"/api/v1/segmentation/{sid}/classify-regions", json=body)


@pytest.mark.unit
class TestRC032Route:
    def test_rc032_classify_route_is_alive(self, route):
        """Regression for the outage: every call used to be a 500."""
        mask, storage = _clinical_case()
        r = _post(route(_Seg({"les": mask}), storage), method="geometric")
        assert r.status_code == 200, r.text[:300]
        assert r.json()["lesions"]

    def test_rc032_msmask_on_non_mni_image_is_refused(self, route):
        mask, storage = _clinical_case()
        r = _post(route(_Seg({"les": mask}), storage), method="msmask")
        assert r.status_code == 422 and "MNI" in r.text

    def test_rc032_auto_on_non_mni_falls_back_and_says_why(self, route):
        mask, storage = _clinical_case()
        r = _post(route(_Seg({"les": mask}), storage), method="auto")
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["method"] == "geometric"
        assert "MNI" in body["atlas_unavailable_reason"]

    def test_rc032_persisted_zone_map_not_reused_for_non_mni_image(self, route):
        mask, storage = _clinical_case()
        zone = np.full_like(mask, 1)                                        # a stale "all PV" zone map
        seg = _Seg({"les": mask, "zone": zone}, analysis_data={"zone_map_seg_id": "zone"})
        client = route(seg, storage)
        assert _post(client, method="msmask").status_code == 422
        r = _post(client, method="auto")
        assert r.status_code == 200 and r.json()["method"] == "geometric"

    @pytest.mark.timeout(300)
    def test_rc032_persisted_zone_map_never_reused_even_on_mni(self, route):
        """A persisted zone map came back transposed after a GCS reload (no RC-031 marker); it is
        never used for classification — the zone map is always generated fresh."""
        internal, storage = _mni_case()
        img = nib.Nifti1Image(np.zeros(MNI_SHAPE, np.float32), MNI_AFFINE)
        ref = [l["region"] for l in rc.classify_lesions_with_atlas(internal, img, (2, 2, 2))["lesions"]]
        stale = np.full_like(internal, 3)                                   # a stale "all IT" zone map
        seg = _Seg({"les": internal, "zone": stale}, analysis_data={"zone_map_seg_id": "zone"})
        r = _post(route(seg, storage), method="msmask")
        assert r.status_code == 200, r.text[:300]
        got = [l["region"] for l in r.json()["lesions"]]
        assert got == ref and "Infratentorial" not in got

    @pytest.mark.timeout(300)
    def test_rc032_msmask_on_mni_image_classifies(self, route):
        internal, storage = _mni_case()
        r = _post(route(_Seg({"les": internal}), storage), method="msmask")
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["method"] == "msmask" and not body.get("atlas_unavailable_reason")
        assert body["lesions"] and all(l["confidence"] is None for l in body["lesions"])

    def test_rc032_generate_zone_map_refuses_non_mni_and_keeps_existing_zone_maps(self, route):
        _, storage = _clinical_case()
        seg = _Seg({"old": np.zeros((2, 2, 2), np.uint8)}, descriptions={"old": rc.ZONE_MAP_DESCRIPTION})
        r = route(seg, storage).post("/api/v1/segmentation/generate-zone-map", json={"file_id": "img-x"})
        assert r.status_code == 422, r.text[:300]
        assert "MNI" in r.text and seg.created is None
        assert seg.deleted == []                                            # nothing destroyed on refusal

    @pytest.mark.timeout(300)
    def test_rc032_generate_zone_map_is_alive_on_mni_image(self, route):
        """Regression: the spacing fallback read undefined `metadata` / `segmentation_id` (500);
        the zone map is persisted only through persist() (no marker-less raw GCS overwrite)."""
        storage = _Storage(MNI_SHAPE, MNI_AFFINE, zooms=(2.0, 2.0, 2.0))
        seg = _Seg({"old": np.zeros((2, 2, 2), np.uint8)}, descriptions={"old": rc.ZONE_MAP_DESCRIPTION})
        r = route(seg, storage).post("/api/v1/segmentation/generate-zone-map", json={"file_id": "img-x"})
        assert r.status_code == 200, r.text[:300]
        a0, a1, k = MNI_SHAPE
        assert seg.created["mask_shape"] == (k, a0, a1)                    # stored in internal order
        assert seg.gcs_bucket.uploads == []                                # no raw overwrite
        assert seg.deleted == ["old"]                                       # replaced only after success

    def test_rc032_generate_zone_map_refuses_a_zone_map_as_parcellation(self, route):
        _, storage = _clinical_case()
        zone = np.full((60, 120, 140), 4, np.uint8)
        zone[0, 0, :3] = (1, 2, 3)
        r = route(_Seg({"zone": zone}), storage).post(
            "/api/v1/segmentation/generate-zone-map", json={"file_id": "img-x", "parcellation_id": "zone"})
        assert r.status_code == 422 and "parcellation" in r.text

    # ------------------------------------------------ path preconditions (parcellation / geometric)
    def test_rc032_geometric_uses_the_brain_outline(self, route):
        """The image used to reach the heuristics in native order: on every non-cubic scan the
        brain outline was dropped for the whole array, and a lesion just under the cortex came
        out Deep White Matter (juxtacortical meant 'near the array corner')."""
        mask, storage = _clinical_case()
        r = _post(route(_Seg({"les": mask}), storage), method="geometric")
        assert r.status_code == 200, r.text[:300]
        assert [l["region"] for l in r.json()["lesions"]] == ["Juxtacortical"]

    def test_rc032_zone_map_is_not_read_as_a_parcellation(self, route):
        """A MAGNIMS zone map (labels 1-4) passed the old '>= 3 FreeSurfer-range labels' test;
        its DWM label 4 was read as the lateral ventricle -> the lesion came out Periventricular."""
        mask, storage = _clinical_case()
        zone = np.full_like(mask, 4)                                        # DWM zone everywhere ...
        zone[0, 0, :3] = (1, 2, 3)                                          # ... plus PV/JC/IT voxels
        r = _post(route(_Seg({"les": mask, "zone": zone}), storage), method="auto")
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["method"] == "geometric"
        assert [l["region"] for l in body["lesions"]] == ["Juxtacortical"]

    def test_rc032_zone_map_refused_as_explicit_parcellation(self, route):
        mask, storage = _clinical_case()
        zone = np.full_like(mask, 4)
        zone[0, 0, :3] = (1, 2, 3)
        r = _post(route(_Seg({"les": mask, "zone": zone}), storage),
                  method="parcellation", parcellation_id="zone")
        assert r.status_code == 422 and "parcellation" in r.text

    def test_rc032_geometric_refused_on_sagittal_and_reversed_slices(self, route):
        sagittal = np.array([[0, 0, 2.0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 0, 1]])  # k -> R
        reversed_axial = np.diag([1.0, 1.0, -2.0, 1.0])                                       # k -> I
        for aff in (sagittal, reversed_axial):
            mask, storage = _clinical_case(affine=aff)
            client = route(_Seg({"les": mask}), storage)
            r = _post(client, method="geometric")
            assert r.status_code == 422 and "inferior to superior" in r.text, r.text[:300]
            r = _post(client, method="auto")
            assert r.status_code == 422, r.text[:300]
            assert "MNI" in r.text and "inferior to superior" in r.text     # both reasons stated


@pytest.mark.unit
class TestRC032Preconditions:
    def test_rc032_parcellation_test_rejects_zone_maps_and_lesion_masks(self):
        fs = {0, 2, 3, 4, 7, 8, 10, 16, 41, 42, 43, 46, 47}
        assert rc.looks_like_freesurfer_parcellation(fs, foreground_ml=1200.0)
        assert not rc.looks_like_freesurfer_parcellation({0, 1, 2, 3, 4})          # zone map / MAGNIMS lesions
        assert not rc.looks_like_freesurfer_parcellation(fs, rc.ZONE_MAP_DESCRIPTION)
        assert not rc.looks_like_freesurfer_parcellation(set(range(21)))            # instance-labelled lesions
        assert not rc.looks_like_freesurfer_parcellation(fs - {3, 42})              # no cortex -> JC impossible
        assert not rc.looks_like_freesurfer_parcellation(set(range(60)), foreground_ml=12.0)  # lesion-sized

    def test_rc032_geometric_image_is_reordered_and_checked(self):
        native = _brain_native()
        lesion_shape = (CLIN_SHAPE[2], CLIN_SHAPE[0], CLIN_SHAPE[1])
        got = rc.prepare_geometric_image(CLIN_AFFINE, native, lesion_shape)
        assert got.shape == lesion_shape and np.array_equal(got, np.transpose(native, (2, 0, 1)))
        bad = [
            (None, native, lesion_shape),                                     # image unreadable
            (np.diag([1.0, 1.0, -2.0, 1.0]), native, lesion_shape),          # slices superior->inferior
            (np.zeros((4, 4)), native, lesion_shape),                         # indeterminate orientation
            (CLIN_AFFINE, np.zeros_like(native), lesion_shape),               # blank image
            (CLIN_AFFINE, native, CLIN_SHAPE),                                # lesion grid mismatch
        ]
        for args in bad:
            with pytest.raises(rc.GeometricPreconditionError):
                rc.prepare_geometric_image(*args)

    def test_rc032_geometric_tilt_cap_and_singleton_4d(self):
        native = _brain_native()
        lesion_shape = (CLIN_SHAPE[2], CLIN_SHAPE[0], CLIN_SHAPE[1])

        def tilted(deg):
            t = np.deg2rad(deg)
            A = CLIN_AFFINE.copy()
            A[:3, :3] = np.array([[1, 0, 0], [0, np.cos(t), -np.sin(t)], [0, np.sin(t), np.cos(t)]]) @ A[:3, :3]
            return A
        assert rc.prepare_geometric_image(tilted(20), native, lesion_shape).shape == lesion_shape
        with pytest.raises(rc.GeometricPreconditionError):
            rc.prepare_geometric_image(tilted(40), native, lesion_shape)
        got = rc.prepare_geometric_image(CLIN_AFFINE, native[..., np.newaxis], lesion_shape)
        assert got.shape == lesion_shape

    def test_rc032_zone_volumes_use_the_voxel_volume(self):
        img = nib.Nifti1Image(np.zeros(MNI_SHAPE, np.float32), MNI_AFFINE)
        stats = rc.generate_zone_map_atlas(img, (2.0, 2.0, 2.0))["zone_stats"]
        for z in stats.values():
            assert z["volume_mm3"] == pytest.approx(z["voxel_count"] * 8.0, abs=0.1)

    def test_rc032_geometric_refuses_a_mismatched_image_instead_of_dropping_it(self):
        lesion = np.zeros((60, 120, 140), np.uint8)
        lesion[29:32, 13:16, 69:72] = 1
        with pytest.raises(ValueError):
            rc.classify_lesions_geometric(lesion, _brain_native(), (2.0, 1.0, 1.0))


def _parcellation_internal():
    """A synthetic whole-brain FreeSurfer-label parcellation on the clinical grid, internal order:
    WM 2/41 by hemisphere, cortex shell 3/42, lateral ventricles 4/43, brainstem 16 (>= 500 mL)."""
    a0, a1, k = np.ogrid[:CLIN_SHAPE[0], :CLIN_SHAPE[1], :CLIN_SHAPE[2]]
    r = ((a0 - 60) / 50.0) ** 2 + ((a1 - 70) / 60.0) ** 2 + ((k - 30) / 25.0) ** 2
    lab = np.zeros(CLIN_SHAPE, np.uint8)
    left = np.broadcast_to(a0 < 60, CLIN_SHAPE)
    lab[(r <= 1.0) & left], lab[(r <= 1.0) & ~left] = 2, 41
    shell = (r > 0.8) & (r <= 1.0)
    lab[shell & left], lab[shell & ~left] = 3, 42
    vent = ((a0 - 60) / 12.0) ** 2 + ((a1 - 70) / 20.0) ** 2 + ((k - 30) / 5.0) ** 2 <= 1.0
    lab[vent & left], lab[vent & ~left] = 4, 43
    lab[55:65, 65:75, 5:12] = 16
    return np.ascontiguousarray(np.transpose(lab, (2, 0, 1)))


@pytest.mark.unit
class TestRC032Round2:
    def test_rc032_foreign_image_parcellation_is_refused(self, route):
        mask, storage = _clinical_case()
        seg = _Seg({"les": mask, "parc": _parcellation_internal()},
                   file_ids={"les": "img-tp2", "parc": "img-tp1"})
        r = _post(route(seg, storage), method="parcellation", parcellation_id="parc")
        assert r.status_code == 422 and "not a parcellation of this image" in r.text

    def test_rc032_same_image_parcellation_is_used(self, route):
        mask = np.zeros((CLIN_SHAPE[2], CLIN_SHAPE[0], CLIN_SHAPE[1]), np.uint8)
        mask[29:32, 45:48, 69:72] = 1                  # 1 voxel (1 mm) lateral to the left ventricle
        _, storage = _clinical_case()
        seg = _Seg({"les": mask, "parc": _parcellation_internal()}, file_ids={"les": "img-1", "parc": "img-1"})
        r = _post(route(seg, storage), method="parcellation", parcellation_id="parc")
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["method"] == "parcellation"
        assert [l["region"] for l in body["lesions"]] == ["Periventricular"]

    def test_rc032_instance_labelled_mask_is_not_read_as_a_parcellation(self, route):
        mask, storage = _clinical_case()
        inst = np.zeros_like(mask)
        for i in range(1, 21):                                               # 20 lesion instances
            inst[i, 50 + i, 50:53] = i
        inst[29:32, 13:16, 69:72] = 4                                        # label 4 under the lesion
        r = _post(route(_Seg({"les": mask, "inst": inst}), storage), method="auto")
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["method"] == "geometric"
        assert [l["region"] for l in body["lesions"]] == ["Juxtacortical"]

    def test_rc032_atlas_fault_is_reported_not_silent(self, route, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("resample failed")
        monkeypatch.setattr(regions_route, "classify_lesions_with_atlas", boom)
        native = _blob_mask_native(MNI_SHAPE, [_world_to_vox(MNI_AFFINE, (-16, 0, 22))])
        internal = np.ascontiguousarray(np.transpose(native, (2, 0, 1)))
        a0, a1, k = np.ogrid[:MNI_SHAPE[0], :MNI_SHAPE[1], :MNI_SHAPE[2]]
        brain = ((((a0 - 45) / 35.0) ** 2 + ((a1 - 55) / 45.0) ** 2 + ((k - 45) / 35.0) ** 2) <= 1) * 100
        storage = _Storage(MNI_SHAPE, MNI_AFFINE, zooms=(2.0, 2.0, 2.0), data=brain.astype(np.uint8))
        r = _post(route(_Seg({"les": internal}), storage), method="auto")
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["method"] == "geometric" and body.get("atlas_error")
        assert not body.get("atlas_unavailable_reason")

    def test_rc032_geometric_fault_is_a_500_not_a_refusal(self, route, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("heuristic crashed")
        monkeypatch.setattr(regions_route, "classify_lesions_geometric", boom)
        mask, storage = _clinical_case()
        r = _post(route(_Seg({"les": mask}), storage), method="auto")
        assert r.status_code == 500 and "failed" in r.text

    def test_rc032_zone_map_replacement_is_atomic(self, route):
        storage = _Storage(MNI_SHAPE, MNI_AFFINE, zooms=(2.0, 2.0, 2.0))
        seg = _Seg({"old": np.zeros((2, 2, 2), np.uint8)}, descriptions={"old": rc.ZONE_MAP_DESCRIPTION},
                   fail_persist={"zone-new"})
        r = route(seg, storage).post("/api/v1/segmentation/generate-zone-map", json={"file_id": "img-x"})
        assert r.status_code == 500
        assert seg.deleted == []                                             # old zone map kept

    def test_rc032_classify_route_enforces_object_level_access(self, route, monkeypatch):
        """RC-029 (HAZ-010): a caller not entitled to the segmentation's patient gets a 404."""
        class _Meta:
            file_id = "patients/11111111-1111-1111-1111-111111111111/studies/s/series/x/image.nii.gz"

        class _SegSvc:
            async def get_metadata(self, sid):
                return _Meta()

        class _PatientSvc:
            async def get_patient(self, pid):
                return type("P", (), {"created_by": "someone-else"})()

        class _CareTeam:
            def list_entitlements_for_user(self, uid):
                return []
        monkeypatch.setattr(resource_access, "_segmentation_service", lambda: _SegSvc())
        monkeypatch.setattr(resource_access, "_patient_service", lambda: _PatientSvc())
        monkeypatch.setattr(resource_access, "_care_team_service", lambda: _CareTeam())
        now = datetime.utcnow()
        stranger = lambda: User(id="u-2", username="clinician", email="clinician@example.com", full_name="Clinician",
                                role=UserRole.RADIOLOGIST, is_active=True, is_locked=False,
                                email_verified=True, created_at=now, updated_at=now)
        mask, storage = _clinical_case()
        seg = _Seg({"les": mask})
        r = _post(route(seg, storage, user=stranger, authorize=False), method="geometric")
        assert r.status_code == 404

    def test_rc032_zone_map_route_enforces_image_access(self, route):
        now = datetime.utcnow()
        stranger = lambda: User(id="u-2", username="clinician", email="clinician@example.com", full_name="Clinician",
                                role=UserRole.RADIOLOGIST, is_active=True, is_locked=False,
                                email_verified=True, created_at=now, updated_at=now)
        _, storage = _clinical_case()
        seg = _Seg({"old": np.zeros((2, 2, 2), np.uint8)}, descriptions={"old": rc.ZONE_MAP_DESCRIPTION})
        r = route(seg, storage, user=stranger).post(
            "/api/v1/segmentation/generate-zone-map", json={"file_id": "img-of-someone-else"})
        assert r.status_code == 404
        assert seg.created is None and seg.deleted == []
