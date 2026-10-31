"""RC-031 step 3 fix — affine-based orientation at clinical-tool ingest.

Risk control for HAZ-006. test_rc031_ingest_order_characterization.py proved the
legacy blind np.transpose(mask,(2,1,0)) at ingest produces the in-plane TRANSPOSE
of the app's display convention (2,0,1), mirroring overlays and mis-classifying
MAGNIMS regions on square data. `ToolRunnerService._orient_mask_to_display`
replaces that blind transpose with affine-based reorientation onto the reference
MRI grid, then the (2,0,1) display transpose — correct for any source
orientation. It originally failed safe to the legacy transpose when no reference
was given; since CAPA-011 / RC-039 (2026-10-17) it FAILS CLOSED (refuses).

These tests exercise the ingest helper directly (no GCS/Firestore) on synthetic
NIfTIs with known affines.
"""
import numpy as np
import nibabel as nib
import pytest

from app.core.exceptions import SegmentationException
from app.services.tool_runner_service import ToolRunnerService
from nibabel.orientations import apply_orientation, inv_ornt_aff


# Asymmetric so the (2,1,0) vs (2,0,1) in-plane swap is observable.
A0, A1, A2 = 5, 8, 3
DISPLAY = (2, 0, 1)
LEGACY = (2, 1, 0)


@pytest.fixture
def runner():
    # storage_service=None: the orientation helper never touches storage.
    return ToolRunnerService(storage_service=None)


def _native_mask():
    m = np.zeros((A0, A1, A2), dtype=np.uint8)
    m[1, 6, 0] = 7          # asymmetric marker (distinct a0 vs a1)
    m[2, 3, 1] = 9
    return m


def _write_nifti(path, data, affine):
    nib.save(nib.Nifti1Image(data.astype(np.uint8), affine), str(path))
    return path


class TestGeometryPreservingCase:
    """The common case: the tool output shares the MRI's geometry (same affine).
    Reorientation is then a no-op and the helper must produce the DISPLAY
    convention (2,0,1) — NOT the legacy (2,1,0)."""

    def test_produces_display_convention_not_legacy(self, runner, tmp_path):
        mask = _native_mask()
        affine = np.diag([2.0, 3.0, 4.0, 1.0])
        ref = _write_nifti(tmp_path / "mri.nii.gz", np.zeros((A0, A1, A2)), affine)

        out = runner._orient_mask_to_display(mask, affine, ref)

        assert np.array_equal(out, np.transpose(mask, DISPLAY)), (
            "geometry-preserving ingest must land in the (2,0,1) display grid"
        )
        assert not np.array_equal(out, np.transpose(mask, LEGACY)), (
            "must NOT reproduce the legacy (2,1,0) in-plane-transposed result"
        )
        assert out.shape == (A2, A0, A1)


class TestOrientationCorrectingCase:
    """When the tool output is in a DIFFERENT voxel order than the MRI (e.g. it
    canonicalised), the affine reorientation must correct it before the display
    transpose, so the result still matches the MRI-aligned display grid."""

    def test_scrambled_source_is_corrected_to_display(self, runner, tmp_path):
        # Base parcellation in MRI-native order, with the MRI's affine.
        base = _native_mask()
        mri_affine = np.diag([2.0, 3.0, 4.0, 1.0])

        # The tool emits `base` in a scrambled voxel order with a matching affine
        # (same physical volume, different array order) — e.g. axes swapped+flipped.
        ornt = np.array([[2, 1], [0, -1], [1, 1]])
        src_data = apply_orientation(base, ornt)
        src_affine = mri_affine @ inv_ornt_aff(ornt, base.shape)
        ref = _write_nifti(tmp_path / "mri.nii.gz", np.zeros_like(base), mri_affine)

        out = runner._orient_mask_to_display(src_data, src_affine, ref)

        # Expected: reorient src back to MRI-native (== base), then display (2,0,1).
        assert np.array_equal(out, np.transpose(base, DISPLAY)), (
            "affine reorientation must undo the tool's scramble before the "
            "display transpose, regardless of the source orientation"
        )


class TestFailsClosed:
    """CAPA-011 / RC-039 (2026-10-17): these cases used to fall back to the legacy
    (2,1,0) transpose — a result known to be in-plane transposed. They now REFUSE
    (SegmentationException), so no mask of undetermined position is produced.
    Behavioural coverage of "nothing stored" is in test_rc039_tool_runner_mask_axes.py."""

    def test_no_reference_is_refused(self, runner):
        with pytest.raises(SegmentationException):
            runner._orient_mask_to_display(_native_mask(), np.eye(4), None)

    def test_missing_reference_path_is_refused(self, runner, tmp_path):
        with pytest.raises(SegmentationException):
            runner._orient_mask_to_display(_native_mask(), np.eye(4), tmp_path / "does_not_exist.nii.gz")

    def test_singular_source_affine_is_refused(self, runner, tmp_path):
        mask = _native_mask()
        ref = _write_nifti(tmp_path / "mri.nii.gz", np.zeros_like(mask), np.diag([2.0, 3.0, 4.0, 1.0]))
        singular = np.eye(4)
        singular[:3, :3] = 0.0  # indeterminate — primitive raises, helper refuses
        with pytest.raises(SegmentationException):
            runner._orient_mask_to_display(mask, singular, ref)
