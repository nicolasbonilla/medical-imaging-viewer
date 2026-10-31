"""RC-039 (CAPA-011, HAZ-006 / HAZ-001 / HAZ-005) — a clinical-tool mask comes back
at the voxel, and the physical position, where the tool put it.

Defect (CAPA-011). `ToolRunnerService._store_nifti_as_segmentation` brought the
tool's mask into the app's INTERNAL order (k, a0, a1) and then wrote THAT array to
`segmentations/{id}/masks.nii.gz` tagged with the RC-031 v2 marker. The marker
means "stored in the MRI's own voxel order (a0, a1, k)", so the loader
(`SegmentationService._load_masks_from_gcs` -> `_nifti_native_to_internal`)
applied the (2, 0, 1) transpose a SECOND time and the axes came back swapped:
on a cubic volume the shape still matched and a lesion at MRI voxel (5, 1, 4)
was shown at (4, 5, 1) — silently. Every mask produced through the tool runner
(FLAMeS, LST-AI, SynthSeg, mindGlide) took that path.

These tests drive the REAL tool-runner store path (and, per tool, the real
`_execute_*` method with only the sidecar HTTP call and the cloud services faked)
and the REAL segmentation load path (`SegmentationService.get_mask` ->
`_load_segmentation` -> `_load_masks_from_gcs`), on NON-cubic, asymmetric volumes
with an anisotropic, flipped, translated affine and a single marked voxel. Each
asserts that the voxel comes back at the same (a0, a1, k) of the MRI it was
computed on and at the same scanner (world) position, both in the app's internal
mask and in the stored NIfTI that is served directly to the 3D viewer.

Fail closed (CAPA-011 follow-up). When the image the tool ran on is missing or
unreadable, or the mask cannot be placed on it, the mask's position cannot be
established: nothing is stored (no mask object, no segmentation record) and the
caller gets a clear error. The former fallback stored the mask in the legacy
(2,1,0) order, known to be in-plane transposed.
"""
import gzip
import uuid
from pathlib import Path
from types import SimpleNamespace

import nibabel as nib
import numpy as np
import pytest
from nibabel.orientations import apply_orientation, inv_ornt_aff

from app.core.exceptions import SegmentationException
from app.core.interfaces.ai_interface import ToolTask, ToolTaskStatus
from app.services import tool_runner_service
from app.services.segmentation_service import SegmentationService
from app.services.tool_runner_service import ToolRunnerService

# --------------------------------------------------------------------------- #
# Geometry: non-cubic, every axis a different length, every coordinate distinct.
# --------------------------------------------------------------------------- #
MRI_SHAPE = (6, 9, 4)                      # (a0, a1, k) native MRI voxel order
MRI_AFFINE = np.array([
    [-0.9, 0.0, 0.0, 90.0],                # x flipped (radiological), 0.9 mm
    [0.0, 1.1, 0.0, -120.0],               # 1.1 mm
    [0.0, 0.0, 3.0, -40.0],                # 3 mm slices
    [0.0, 0.0, 0.0, 1.0],
])
LESION = (4, 7, 1)                         # (a0, a1, k) in the MRI grid
LABEL = 1

# The tool emits its mask in a DIFFERENT voxel order than the MRI (axes permuted
# and flipped, with the matching affine): same physical volume, other array order.
SCRAMBLE = np.array([[2, 1], [0, -1], [1, 1]])


def _world(affine, ijk):
    return (np.asarray(affine, float) @ np.r_[np.asarray(ijk, float), 1.0])[:3]


def _expected_native(shape=MRI_SHAPE, voxel=LESION, label=LABEL):
    m = np.zeros(shape, dtype=np.uint8)
    m[voxel] = label
    return m


def _tool_output(native_on_mri_grid, mri_affine, orientation):
    """The array + affine a sidecar would write for a mask that is
    `native_on_mri_grid` on the MRI grid."""
    if orientation == "mri_grid":
        return native_on_mri_grid, mri_affine
    data = apply_orientation(native_on_mri_grid, SCRAMBLE)
    affine = mri_affine @ inv_ornt_aff(SCRAMBLE, native_on_mri_grid.shape)
    return data, affine


def _nifti_bytes(data, affine, dtype=np.uint8):
    return nib.Nifti1Image(np.asarray(data).astype(dtype), affine).to_bytes()


def _write(path: Path, data, affine, dtype=np.uint8) -> Path:
    nib.save(nib.Nifti1Image(np.asarray(data).astype(dtype), affine), str(path))
    return path


# --------------------------------------------------------------------------- #
# Fakes: one object store + one Firestore shared by the tool runner (writer) and
# the segmentation service (reader), so the bytes the tool runner uploads are the
# bytes the viewer's load path reads.
# --------------------------------------------------------------------------- #
class _Store:
    def __init__(self):
        self.objects = {}   # name -> bytes
        self.docs = {}      # (collection, id) -> dict


class _ToolStorage:
    """Mirrors GCSStorageService.upload / download signatures."""

    def __init__(self, store):
        self._s = store

    async def upload(self, object_name: str, file_data: bytes, content_type: str, metadata=None):
        self._s.objects[object_name] = file_data
        return {"name": object_name}

    async def download(self, object_name: str) -> bytes:
        return self._s.objects[object_name]


class _Blob:
    def __init__(self, store, name):
        self._s, self.name, self.generation = store, name, 1

    def exists(self):
        return self.name in self._s.objects

    def download_to_file(self, buf):
        buf.write(self._s.objects[self.name])


class _Bucket:
    def __init__(self, store):
        self._s = store

    def blob(self, name):
        return _Blob(self._s, name)

    def get_blob(self, name):
        return _Blob(self._s, name) if name in self._s.objects else None


class _DocRef:
    def __init__(self, store, coll, doc_id):
        self._s, self._key = store, (coll, doc_id)

    def set(self, data):
        self._s.docs[self._key] = dict(data)

    def get(self):
        data = self._s.docs.get(self._key)
        return SimpleNamespace(exists=data is not None, to_dict=lambda: dict(data or {}))


class _Firestore:
    def __init__(self, store):
        self._s = store

    def collection(self, name):
        return SimpleNamespace(document=lambda doc_id: _DocRef(self._s, name, doc_id))


@pytest.fixture
def env(monkeypatch, tmp_path):
    store = _Store()
    import app.core.firebase as firebase_mod
    monkeypatch.setattr(firebase_mod, "get_firestore_client", lambda: _Firestore(store), raising=False)

    runner = ToolRunnerService(storage_service=_ToolStorage(store))
    runner._shared_volume = tmp_path / "shared"

    async def _no_auth(self, audience):
        return {}
    monkeypatch.setattr(ToolRunnerService, "_worker_auth_headers", _no_auth)

    seg_service = SegmentationService(storage_path=str(tmp_path / "local"), cache_service=None)
    seg_service._gcs_bucket = _Bucket(store)
    seg_service._db = _Firestore(store)
    return SimpleNamespace(store=store, runner=runner, seg=seg_service, tmp=tmp_path)


# --------------------------------------------------------------------------- #
# The behavioural check every test applies.
# --------------------------------------------------------------------------- #
def _assert_same_voxel_and_position(env, seg_id, expected_native, mri_affine, src_world):
    """`expected_native` is the mask on the MRI grid (a0, a1, k); `src_world` the
    scanner coordinates of the marked voxel as the tool emitted it."""
    a0, a1, k = (int(v) for v in np.argwhere(expected_native)[0])
    label = int(expected_native[a0, a1, k])

    # 1) The app's real load path (what the 2D viewer, MAGNIMS and lesion
    #    analysis consume): internal (k, a0, a1) of the MRI it belongs to.
    internal = env.seg.get_mask(seg_id)
    assert internal is not None, "the stored tool mask must load"
    A0, A1, K = expected_native.shape
    assert internal.shape == (K, A0, A1), (
        f"loaded mask has shape {internal.shape}; the MRI's internal grid is {(K, A0, A1)} "
        "(axes swapped on load: the stored voxel order does not match its RC-031 marker)"
    )
    hits = [tuple(int(v) for v in p) for p in np.argwhere(internal)]
    assert hits == [(k, a0, a1)], (
        f"lesion loaded at internal {hits}; it was computed at MRI voxel "
        f"(a0,a1,k)=({a0},{a1},{k}) -> internal {(k, a0, a1)}"
    )
    assert int(internal[k, a0, a1]) == label, "label value must survive verbatim"
    # Same physical position: the internal voxel, read on the MRI's own grid.
    np.testing.assert_allclose(_world(mri_affine, (a0, a1, k)), src_world, atol=1e-4)
    # Same slice layout the viewer shows: internal[k] is the MRI's axial slice k.
    assert np.array_equal(internal[k], expected_native[:, :, k])

    # 2) The stored NIfTI, served as-is to the 3D viewer (NiiVue / ITK-SNAP):
    #    the marked voxel, through the file's own affine, is at the same place.
    stored = nib.Nifti1Image.from_bytes(gzip.decompress(env.store.objects[f"segmentations/{seg_id}/masks.nii.gz"]))
    data = np.asarray(stored.dataobj)
    stored_hits = np.argwhere(data)
    assert len(stored_hits) == 1, "exactly one marked voxel must be stored"
    np.testing.assert_allclose(_world(stored.affine, stored_hits[0]), src_world, atol=1e-4)


def _src_world(src_data, src_affine):
    return _world(src_affine, np.argwhere(src_data)[0])


# --------------------------------------------------------------------------- #
# Store path (`_store_nifti_as_segmentation`) -> load path.
# --------------------------------------------------------------------------- #
class TestStorePathRoundTrip:

    @pytest.mark.asyncio
    async def test_rc039_non_cubic_mask_returns_to_same_voxel_and_position(self, env):
        expected = _expected_native()
        mri = _write(env.tmp / "mri.nii.gz", np.zeros(MRI_SHAPE), MRI_AFFINE, np.float32)
        src = _write(env.tmp / "mask.nii.gz", expected, MRI_AFFINE)

        seg_id = await env.runner._store_nifti_as_segmentation(
            mask_path=src, file_id="flair-1", description="tool mask",
            validation_source="flames-v1.0", reference_mri_path=mri,
        )

        _assert_same_voxel_and_position(env, seg_id, expected, MRI_AFFINE, _world(MRI_AFFINE, LESION))

    @pytest.mark.asyncio
    async def test_rc039_cubic_mask_is_not_silently_moved(self, env):
        """The silent case: a cubic volume keeps its shape when the axes swap, so
        only the voxel position can reveal the defect — (5,1,4) became (4,5,1)."""
        shape, voxel = (7, 7, 7), (5, 1, 4)
        affine = np.diag([1.0, 1.0, 1.0, 1.0])
        expected = _expected_native(shape, voxel)
        mri = _write(env.tmp / "mri.nii.gz", np.zeros(shape), affine, np.float32)
        src = _write(env.tmp / "mask.nii.gz", expected, affine)

        seg_id = await env.runner._store_nifti_as_segmentation(
            mask_path=src, file_id="flair-1", description="tool mask",
            validation_source="flames-v1.0", reference_mri_path=mri,
        )

        _assert_same_voxel_and_position(env, seg_id, expected, affine, _world(affine, voxel))

    @pytest.mark.asyncio
    async def test_rc039_tool_output_in_other_voxel_order_lands_at_same_physical_position(self, env):
        """A tool that writes its mask in another voxel order (e.g. canonical RAS)
        must still land on the MRI voxel at the same scanner position, and the
        stored file's affine must describe the array it holds."""
        expected = _expected_native()
        src_data, src_affine = _tool_output(expected, MRI_AFFINE, "reoriented")
        assert src_data.shape != MRI_SHAPE          # the scramble is real
        mri = _write(env.tmp / "mri.nii.gz", np.zeros(MRI_SHAPE), MRI_AFFINE, np.float32)
        src = _write(env.tmp / "mask.nii.gz", src_data, src_affine)

        seg_id = await env.runner._store_nifti_as_segmentation(
            mask_path=src, file_id="flair-1", description="tool mask",
            validation_source="synthseg-v2.0", reference_mri_path=mri,
        )

        _assert_same_voxel_and_position(env, seg_id, expected, MRI_AFFINE, _src_world(src_data, src_affine))

    @pytest.mark.asyncio
    async def test_rc039_lstai_types_mask_returns_to_same_voxel(self, env):
        """LST-AI stores its lesion-TYPES mask (zone labels) instead of the binary
        mask; the label value and its position must both survive."""
        expected = _expected_native(label=3)
        mri = _write(env.tmp / "mri.nii.gz", np.zeros(MRI_SHAPE), MRI_AFFINE, np.float32)
        binary = _write(env.tmp / "lesion_mask.nii.gz", _expected_native(), MRI_AFFINE)
        types = _write(env.tmp / "lesion_types.nii.gz", expected, MRI_AFFINE)

        seg_id = await env.runner._store_nifti_as_segmentation(
            mask_path=binary, types_path=types, file_id="flair-1", description="LST-AI",
            validation_source="lst-ai-v1.0.3", reference_mri_path=mri,
        )

        _assert_same_voxel_and_position(env, seg_id, expected, MRI_AFFINE, _world(MRI_AFFINE, LESION))

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", ["no_reference", "missing_file", "unreadable_file", "indeterminate_affine"])
    async def test_rc039_mask_without_a_usable_reference_is_not_stored(self, env, case):
        """Fail closed: without the image the tool ran on (absent, missing file,
        unreadable file) or with an affine that cannot place the mask on it, the
        mask's position cannot be established. Nothing is stored — no mask object,
        no segmentation record — and the caller gets a clear error. The former
        fallback stored it in the legacy order, known to be in-plane transposed."""
        reference = env.tmp / "mri.nii.gz"
        src = _write(env.tmp / "mask.nii.gz", _expected_native(), MRI_AFFINE)
        if case == "no_reference":
            reference = None
        elif case == "missing_file":
            reference = env.tmp / "does_not_exist.nii.gz"
        elif case == "unreadable_file":
            reference.write_bytes(b"this is not a NIfTI image")
        else:
            _write(reference, np.zeros(MRI_SHAPE), MRI_AFFINE, np.float32)
            # The tool's mask carries a singular transform: it cannot be placed.
            img = nib.Nifti1Image(_expected_native(), None)
            img.set_qform(None, code=0)
            img.set_sform(np.diag([0.0, 0.0, 0.0, 1.0]), code=2)
            nib.save(img, str(src))
            assert not np.linalg.det(nib.load(str(src)).affine[:3, :3])

        with pytest.raises(SegmentationException) as exc:
            await env.runner._store_nifti_as_segmentation(
                mask_path=src, file_id="flair-1", description="tool mask",
                validation_source="mindglide-v1.0", reference_mri_path=reference,
            )

        assert exc.value.error_code == "TOOL_MASK_REFERENCE_UNAVAILABLE"
        assert "not stored" in str(exc.value)
        assert [n for n in env.store.objects if n.startswith("segmentations/")] == [], "no mask may be uploaded"
        assert [k for k in env.store.docs if k[0] == "segmentations"] == [], "no segmentation record may be written"

    @pytest.mark.asyncio
    async def test_rc039_stored_voxel_order_matches_its_marker(self, env):
        """Contract with the loader: a file carrying the RC-031 v2 marker holds the
        MRI's own voxel order (a0, a1, k) on the MRI's grid."""
        expected = _expected_native()
        mri = _write(env.tmp / "mri.nii.gz", np.zeros(MRI_SHAPE), MRI_AFFINE, np.float32)
        src = _write(env.tmp / "mask.nii.gz", expected, MRI_AFFINE)

        seg_id = await env.runner._store_nifti_as_segmentation(
            mask_path=src, file_id="flair-1", description="tool mask",
            validation_source="flames-v1.0", reference_mri_path=mri,
        )

        stored = nib.Nifti1Image.from_bytes(gzip.decompress(env.store.objects[f"segmentations/{seg_id}/masks.nii.gz"]))
        assert SegmentationService._header_has_v2_marker(stored.header)
        assert stored.shape == MRI_SHAPE, "a v2-marked mask must be stored in the MRI's voxel order"
        assert np.array_equal(np.asarray(stored.dataobj), expected)
        np.testing.assert_allclose(stored.affine, MRI_AFFINE, atol=1e-5)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("orientation", ["mri_grid", "reoriented"])
    async def test_rc039_stored_record_dimensions_match_the_image(self, env, orientation):
        """The segmentation record carries the dimensions of the image the mask
        belongs to — image_shape = [height, width, depth] = [a0, a1, k], the
        convention of SegmentationService.create_segmentation — consistent with
        the mask the viewer loads ((depth, height, width) = (k, a0, a1)), and
        the true annotated-voxel count. Guards against computing the record from
        the mask read in another axis order."""
        expected = _expected_native()
        src_data, src_affine = _tool_output(expected, MRI_AFFINE, orientation)
        mri = _write(env.tmp / "mri.nii.gz", np.zeros(MRI_SHAPE), MRI_AFFINE, np.float32)
        src = _write(env.tmp / "mask.nii.gz", src_data, src_affine)

        seg_id = await env.runner._store_nifti_as_segmentation(
            mask_path=src, file_id="flair-1", description="tool mask",
            validation_source="flames-v1.0", reference_mri_path=mri,
        )

        doc = env.store.docs[("segmentations", seg_id)]
        A0, A1, K = MRI_SHAPE
        assert doc["image_shape"] == [A0, A1, K], (
            f"record dimensions {doc['image_shape']} do not describe the image grid {[A0, A1, K]}"
        )
        assert doc["annotated_voxels"] == 1
        assert doc["gcs_path"] == f"segmentations/{seg_id}/masks.nii.gz"
        loaded = env.seg.get_mask(seg_id)
        h, w, d = doc["image_shape"]
        assert loaded.shape == (d, h, w), "record dimensions and loaded mask must agree"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", ["shape_mismatch", "affine_mismatch", "resampled_1mm"])
    async def test_rc039_mask_not_on_the_image_grid_is_not_stored(self, env, case):
        """Fail closed when the tool's mask, after axis reorientation, is NOT on
        the grid of the image it was computed on — reordering axes cannot place
        it voxel for voxel. Cases: a different array shape on the same transform;
        the same shape shifted by half a millimetre; and a SynthSeg-like output
        resampled to 1 mm over a 0.5 x 0.5 x 3 mm study (same field of view)."""
        if case == "resampled_1mm":
            mri_shape, mri_affine = (40, 40, 10), np.diag([0.5, 0.5, 3.0, 1.0])
            mask = np.zeros((20, 20, 30), dtype=np.uint8)
            mask[10, 10, 15] = 17
            mask_affine = np.eye(4)                      # 1 mm, same origin and field of view
        else:
            mri_shape, mri_affine = MRI_SHAPE, MRI_AFFINE
            if case == "shape_mismatch":
                mask = np.zeros((6, 9, 5), dtype=np.uint8)
                mask[4, 7, 1] = 1
                mask_affine = MRI_AFFINE
            else:
                mask = _expected_native()
                mask_affine = MRI_AFFINE.copy()
                mask_affine[0, 3] += 0.5                 # half a millimetre off the image grid
        mri = _write(env.tmp / "mri.nii.gz", np.zeros(mri_shape), mri_affine, np.float32)
        src = _write(env.tmp / "mask.nii.gz", mask, mask_affine)

        with pytest.raises(SegmentationException) as exc:
            await env.runner._store_nifti_as_segmentation(
                mask_path=src, file_id="flair-1", description="tool mask",
                validation_source="synthseg-v2.0", reference_mri_path=mri,
            )

        assert exc.value.error_code == "TOOL_MASK_GRID_MISMATCH"
        assert "not stored" in str(exc.value) and "grid" in str(exc.value)
        assert [n for n in env.store.objects if n.startswith("segmentations/")] == [], "no mask may be uploaded"
        assert [k for k in env.store.docs if k[0] == "segmentations"] == [], "no segmentation record may be written"

    @pytest.mark.asyncio
    async def test_rc039_same_grid_up_to_float_rounding_is_accepted(self, env):
        """Positive control for the grid check: a transform that differs from the
        image's only by float rounding (as when a tool re-writes the header) is
        the same grid and must be stored, at the same voxel."""
        expected = _expected_native()
        mri = _write(env.tmp / "mri.nii.gz", np.zeros(MRI_SHAPE), MRI_AFFINE, np.float32)
        rounded = MRI_AFFINE + np.array([[1e-6, 0, 0, 2e-5], [0, -1e-6, 0, -2e-5], [0, 0, 1e-6, 1e-5], [0, 0, 0, 0]])
        src = _write(env.tmp / "mask.nii.gz", expected, rounded)

        seg_id = await env.runner._store_nifti_as_segmentation(
            mask_path=src, file_id="flair-1", description="tool mask",
            validation_source="flames-v1.0", reference_mri_path=mri,
        )

        _assert_same_voxel_and_position(env, seg_id, expected, MRI_AFFINE, _world(MRI_AFFINE, LESION))


# --------------------------------------------------------------------------- #
# Every tool that uses this path, end to end through its real `_execute_*`
# method; only the sidecar HTTP call and the cloud services are faked.
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


def _fake_sidecars(store, outputs, bucket):
    """`outputs[name] = (data, affine)` for each file a sidecar writes."""

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None, **_):
            if "input_gcs_uri" in json:                       # FLAMeS (GCS contract)
                name = json["output_gcs_uri"][len(f"gs://{bucket}/"):]
                store.objects[name] = gzip.compress(_nifti_bytes(*outputs["flames"]))
                return _Resp({"lesion_voxels": 1})
            out = Path(json["output_dir"])
            out.mkdir(parents=True, exist_ok=True)
            if url.endswith("/parcellate"):                   # SynthSeg
                _write(out / "synthseg.nii.gz", *outputs["synthseg"])
                return _Resp({"parcellation": "synthseg.nii.gz"})
            if "t1_path" in json:                             # LST-AI
                _write(out / "lesion_mask.nii.gz", *outputs["lstai_mask"])
                _write(out / "lesion_types.nii.gz", *outputs["lstai_types"])
                return _Resp({"lesion_mask": "lesion_mask.nii.gz", "lesion_types": "lesion_types.nii.gz"})
            _write(out / "lesion_mask.nii.gz", *outputs["mindglide_lesion"])          # mindGlide
            _write(out / "structure_mask.nii.gz", *outputs["mindglide_structure"])
            return _Resp({"lesion_mask": "lesion_mask.nii.gz", "structure_mask": "structure_mask.nii.gz"})

    return _Client


def _seed_task(runner, tool, source):
    task_id = str(uuid.uuid4())
    runner._tasks[task_id] = ToolTask(task_id=task_id, tool=tool, status=ToolTaskStatus.PENDING,
                                      validation_source=source, created_at="2026-10-17T00:00:00+00:00")
    return task_id


def _seg_ids_by_source(store):
    return {d["validation_source"]: key[1] for key, d in store.docs.items() if key[0] == "segmentations"}


@pytest.mark.parametrize("orientation", ["mri_grid", "reoriented"])
class TestEveryToolEndToEnd:

    def _setup(self, env, monkeypatch, outputs):
        bucket = tool_runner_service.settings.GCS_BUCKET_NAME
        monkeypatch.setattr(tool_runner_service.httpx, "AsyncClient", _fake_sidecars(env.store, outputs, bucket))
        mri = gzip.compress(_nifti_bytes(np.zeros(MRI_SHAPE), MRI_AFFINE, np.float32))
        env.store.objects["t1-file"] = mri          # downloaded as t1.nii.gz
        env.store.objects["flair-file"] = mri       # downloaded as flair/input.nii.gz

    def _check(self, env, task_id, expected, src):
        task = env.runner._tasks[task_id]
        assert task.status == ToolTaskStatus.COMPLETED, task.error
        _assert_same_voxel_and_position(env, task.segmentation_id, expected, MRI_AFFINE, _src_world(*src))

    @pytest.mark.asyncio
    async def test_rc039_flames(self, env, monkeypatch, orientation):
        expected = _expected_native()
        src = _tool_output(expected, MRI_AFFINE, orientation)
        self._setup(env, monkeypatch, {"flames": src})
        task_id = _seed_task(env.runner, "flames", "flames-v1.0")

        await env.runner._execute_flames(task_id, "flair-file", "patient-1", "study-1")

        self._check(env, task_id, expected, src)

    @pytest.mark.asyncio
    async def test_rc039_lstai(self, env, monkeypatch, orientation):
        expected = _expected_native(label=2)                   # the stored TYPES mask
        types = _tool_output(expected, MRI_AFFINE, orientation)
        mask = _tool_output(_expected_native(), MRI_AFFINE, orientation)
        self._setup(env, monkeypatch, {"lstai_mask": mask, "lstai_types": types})
        task_id = _seed_task(env.runner, "lst-ai", "lst-ai-v1.0.3")

        await env.runner._execute_lstai(task_id, "t1-file", "flair-file", "patient-1", "study-1")

        self._check(env, task_id, expected, types)

    @pytest.mark.asyncio
    async def test_rc039_synthseg(self, env, monkeypatch, orientation):
        expected = _expected_native(label=17)                  # a FreeSurfer label
        src = _tool_output(expected, MRI_AFFINE, orientation)
        self._setup(env, monkeypatch, {"synthseg": src})
        task_id = _seed_task(env.runner, "synthseg", "synthseg-v2.0")

        await env.runner._execute_synthseg(task_id, "flair-file", "patient-1", "study-1")

        self._check(env, task_id, expected, src)

    @pytest.mark.asyncio
    async def test_rc039_mindglide_lesion_and_structure_masks(self, env, monkeypatch, orientation):
        lesion = _expected_native()
        structure = _expected_native(voxel=(1, 2, 3), label=5)
        src_lesion = _tool_output(lesion, MRI_AFFINE, orientation)
        src_structure = _tool_output(structure, MRI_AFFINE, orientation)
        self._setup(env, monkeypatch, {"mindglide_lesion": src_lesion, "mindglide_structure": src_structure})
        task_id = _seed_task(env.runner, "mindglide", "mindglide-v1.0")

        await env.runner._execute_mindglide(task_id, "flair-file", "patient-1", "study-1")

        self._check(env, task_id, lesion, src_lesion)
        structure_id = _seg_ids_by_source(env.store)["mindglide-v1.0-structures"]
        _assert_same_voxel_and_position(env, structure_id, structure, MRI_AFFINE, _src_world(*src_structure))


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["flames", "lst-ai", "synthseg", "mindglide"])
async def test_rc039_tool_run_with_unreadable_reference_fails_and_stores_nothing(env, monkeypatch, tool):
    """Fail closed end to end: the tool returns a mask but the image it ran on
    cannot be read back to place it. The task must FAIL with a clear error and
    leave no mask object and no segmentation record behind."""
    out = (_expected_native(), MRI_AFFINE)
    outputs = {"flames": out, "lstai_mask": out, "lstai_types": out, "synthseg": out,
               "mindglide_lesion": out, "mindglide_structure": out}
    bucket = tool_runner_service.settings.GCS_BUCKET_NAME
    monkeypatch.setattr(tool_runner_service.httpx, "AsyncClient", _fake_sidecars(env.store, outputs, bucket))
    env.store.objects["t1-file"] = b"not a NIfTI image"
    env.store.objects["flair-file"] = b"not a NIfTI image"
    source = {"flames": "flames-v1.0", "lst-ai": "lst-ai-v1.0.3",
              "synthseg": "synthseg-v2.0", "mindglide": "mindglide-v1.0"}[tool]
    task_id = _seed_task(env.runner, tool, source)

    if tool == "flames":
        await env.runner._execute_flames(task_id, "flair-file", "patient-1", "study-1")
    elif tool == "lst-ai":
        await env.runner._execute_lstai(task_id, "t1-file", "flair-file", "patient-1", "study-1")
    elif tool == "synthseg":
        await env.runner._execute_synthseg(task_id, "flair-file", "patient-1", "study-1")
    else:
        await env.runner._execute_mindglide(task_id, "flair-file", "patient-1", "study-1")

    task = env.runner._tasks[task_id]
    assert task.status == ToolTaskStatus.FAILED
    assert task.segmentation_id is None
    assert "not stored" in (task.error or ""), task.error
    assert [n for n in env.store.objects if n.startswith("segmentations/")] == [], "no mask may be uploaded"
    assert [k for k in env.store.docs if k[0] == "segmentations"] == [], "no segmentation record may be written"


@pytest.mark.asyncio
async def test_rc039_synthseg_1mm_output_on_a_non_1mm_study_fails_and_stores_nothing(env, monkeypatch):
    """End to end, the case the pre-merge review reproduced: SynthSeg returns its
    parcellation resampled to 1 mm (20 x 20 x 30) for a 0.5 x 0.5 x 3 mm study
    (40 x 40 x 10, same field of view). The task must FAIL with a clear message
    and leave no mask object and no segmentation record behind."""
    mri_affine = np.diag([0.5, 0.5, 3.0, 1.0])
    parcellation = np.zeros((20, 20, 30), dtype=np.uint8)
    parcellation[10, 10, 15] = 17
    bucket = tool_runner_service.settings.GCS_BUCKET_NAME
    monkeypatch.setattr(tool_runner_service.httpx, "AsyncClient",
                        _fake_sidecars(env.store, {"synthseg": (parcellation, np.eye(4))}, bucket))
    env.store.objects["flair-file"] = gzip.compress(_nifti_bytes(np.zeros((40, 40, 10)), mri_affine, np.float32))
    task_id = _seed_task(env.runner, "synthseg", "synthseg-v2.0")

    await env.runner._execute_synthseg(task_id, "flair-file", "patient-1", "study-1")

    task = env.runner._tasks[task_id]
    assert task.status == ToolTaskStatus.FAILED
    assert task.segmentation_id is None
    assert "not stored" in (task.error or "") and "grid" in (task.error or ""), task.error
    assert [n for n in env.store.objects if n.startswith("segmentations/")] == [], "no mask may be uploaded"
    assert [k for k in env.store.docs if k[0] == "segmentations"] == [], "no segmentation record may be written"
