"""RC-031 — save segmentation NIfTIs in the MRI's own voxel order (HAZ-006).

The original 131-day longitudinal bug: `_save_masks_to_gcs` stored the mask with
transpose (2,1,0) => on-disk (a1,a0,k), the in-plane TRANSPOSE of the MRI's
native (a0,a1,k), while attaching the MRI's affine. A directly-served overlay
(longitudinal NiiVue, ITK-SNAP) then rendered mirrored. It round-tripped
internally (load also used (2,1,0)), which is why the 2D editor looked fine and
the bug hid.

Fix: store MRI-native via (1,2,0) and tag the NIfTI header; read the tag back and
use (2,0,1) for tagged masks, (2,1,0) for legacy — backward compatible, no bulk
migration. These tests prove the on-disk order, the round-trip for BOTH regimes,
and the marker detection, on asymmetric data where the swap is observable.
"""
import os
import tempfile

import numpy as np
import nibabel as nib
import pytest

from app.services.segmentation_service import SegmentationService as S


A0, A1, K = 5, 8, 3          # MRI-native rows, cols, slices
INTERNAL = (K, A0, A1)       # (D,H,W) = (k,a0,a1), the app's internal convention


def _internal_mask():
    m = np.zeros(INTERNAL, dtype=np.uint8)
    m[0, 1, 6] = 7           # (k=0, a0=1, a1=6) — asymmetric
    m[2, 3, 1] = 9
    return m


class TestOnDiskOrderIsMriNative:
    def test_internal_to_native_is_1_2_0(self):
        mask = _internal_mask()
        native = S._internal_to_nifti_native(mask)
        assert native.shape == (A0, A1, K), "stored order must be MRI-native (a0,a1,k)"
        # marker at internal (0,1,6) -> native (a0=1, a1=6, k=0)
        assert native[1, 6, 0] == 7
        # legacy (2,1,0) would have placed it at (a1=6, a0=1, k=0) in shape (A1,A0,K)
        legacy = np.transpose(mask, (2, 1, 0))
        assert legacy.shape == (A1, A0, K)
        assert native.shape != legacy.shape, "v2 on-disk order differs from legacy"

    def test_v2_stored_array_aligns_with_the_mri_grid(self):
        """The actual fix: an MRI whose native array marks the SAME physical voxel
        must coincide, voxel-for-voxel, with the stored v2 mask array — i.e. a
        direct overlay aligns. Legacy (2,1,0) does not."""
        # MRI native (a0,a1,k) with the same physical voxel marked.
        mri_native = np.zeros((A0, A1, K), dtype=np.uint8)
        mri_native[1, 6, 0] = 7
        mri_native[3, 1, 2] = 9
        # The app's internal mask for that MRI is transpose(mri_native,(2,0,1)).
        internal = np.transpose(mri_native, (2, 0, 1))
        stored_v2 = S._internal_to_nifti_native(internal)
        assert np.array_equal(stored_v2, mri_native), (
            "v2-stored mask must match the MRI's native voxel array exactly"
        )
        legacy = np.transpose(internal, (2, 1, 0))
        assert not np.array_equal(legacy, mri_native), (
            "legacy on-disk order must NOT align with the MRI grid (the mirror)"
        )


class TestRoundTripBothRegimes:
    def test_v2_round_trip_is_identity(self):
        mask = _internal_mask()
        native = S._internal_to_nifti_native(mask)
        back = S._nifti_native_to_internal(native, oriented_v2=True)
        assert np.array_equal(back, mask), "v2 save/load must round-trip exactly"

    def test_legacy_round_trip_is_identity(self):
        # Backward compatibility: a legacy on-disk (a1,a0,k) read with (2,1,0)
        # still yields the correct internal convention.
        mask = _internal_mask()
        legacy_native = np.transpose(mask, (2, 1, 0))
        back = S._nifti_native_to_internal(legacy_native, oriented_v2=False)
        assert np.array_equal(back, mask), "legacy masks must still load correctly"


class TestHeaderMarker:
    def test_marker_detected_after_set(self, tmp_path):
        img = nib.Nifti1Image(np.zeros((A0, A1, K), np.uint8), np.eye(4))
        img.header["descrip"] = S._RC031_ORIENT_MARKER
        p = tmp_path / "m.nii.gz"
        nib.save(img, str(p))
        reloaded = nib.load(str(p))
        assert S._header_has_v2_marker(reloaded.header) is True

    def test_absent_marker_reads_as_legacy(self):
        img = nib.Nifti1Image(np.zeros((A0, A1, K), np.uint8), np.eye(4))
        assert S._header_has_v2_marker(img.header) is False


class TestFullNiftiRoundTripThroughDisk:
    def test_save_marked_nifti_and_reload_recovers_internal(self, tmp_path):
        """End-to-end through a real .nii.gz: internal -> native+marker -> disk ->
        reload -> marker-aware transpose -> original internal."""
        mask = _internal_mask()
        native = S._internal_to_nifti_native(mask)

        img = nib.Nifti1Image(native, np.diag([2.0, 3.0, 4.0, 1.0]))
        img.header["descrip"] = S._RC031_ORIENT_MARKER
        p = tmp_path / "seg.nii.gz"
        nib.save(img, str(p))

        reloaded = nib.load(str(p))
        data = reloaded.get_fdata().astype(np.uint8)
        v2 = S._header_has_v2_marker(reloaded.header)
        assert v2 is True
        recovered = S._nifti_native_to_internal(data, v2)
        assert np.array_equal(recovered, mask)
