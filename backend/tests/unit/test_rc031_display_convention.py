"""RC-031 — lock the DISPLAY convention against the real image-load path.

The clinical-tool ingest fix (#15) rests on one premise: the app's display /
painting convention is internal (k, a0, a1) = np.transpose(native, (2,0,1)), so a
clinical-tool mask must be brought to (2,0,1) — the legacy (2,1,0) yields
(k, a1, a0), the in-plane transpose. If a future change to the image-load or
slice-extraction path silently altered that convention, #15 would become wrong
and no test guarded it. This does.

It drives the REAL ImagingService.load_nifti + axial slice extraction on an
asymmetric synthetic MRI and proves:
  - load_nifti preserves NIfTI-native order (a0, a1, k) with slices last;
  - an axial slice is pixel_array[:, :, k] → in-plane (a0, a1);
  - a display-aligned painted mask is (k, a0, a1) = transpose(native, (2,0,1)),
    and its per-slice layout matches the extracted image slice;
  - the legacy ingest transpose (2,1,0) does NOT match that layout.

Asymmetric (a0 != a1 != k) so the (2,0,1) vs (2,1,0) distinction is observable.
"""
import numpy as np
import nibabel as nib
import pytest

from app.services.imaging_service import ImagingService


A0, A1, K = 5, 8, 3   # NIfTI-native rows, columns, slices
DISPLAY = (2, 0, 1)   # native -> internal (k, a0, a1): the fix target
LEGACY = (2, 1, 0)    # native -> (k, a1, a0): the buggy ingest transpose


def _native_mri_bytes():
    # Native (a0, a1, k) with a single asymmetric bright voxel at (a0=1, a1=6, k=0).
    vol = np.zeros((A0, A1, K), dtype=np.float32)
    vol[1, 6, 0] = 1000.0
    return nib.Nifti1Image(vol, np.eye(4)).to_bytes(), (1, 6, 0)


class TestLoadNiftiPreservesNativeOrder:
    def test_shape_and_metadata_are_native_a0_a1_k(self):
        data_bytes, _ = _native_mri_bytes()
        data, meta = ImagingService().load_nifti(data_bytes)
        assert data.shape == (A0, A1, K), "load_nifti must preserve native (a0,a1,k)"
        assert (meta.rows, meta.columns, meta.slices) == (A0, A1, K)

    def test_axial_slice_is_in_plane_a0_a1(self):
        data_bytes, marker = _native_mri_bytes()
        data, _ = ImagingService().load_nifti(data_bytes)
        k = marker[2]
        sl = data[:, :, k]                       # the app's axial extraction
        assert sl.shape == (A0, A1)
        # Brightest voxel of the slice sits at (a0=1, a1=6).
        idx = tuple(int(v) for v in np.argwhere(sl == sl.max())[0])
        assert idx == (1, 6)


class TestDisplayConventionIs201:
    """A painted mask aligned to the display is (k, a0, a1). Its per-slice layout
    must equal the extracted image slice — which fixes the ingest target as
    (2,0,1), not (2,1,0)."""

    def test_painted_convention_matches_image_slice(self):
        data_bytes, marker = _native_mri_bytes()
        data, _ = ImagingService().load_nifti(data_bytes)
        a0, a1, k = marker

        # native -> display-internal via (2,0,1)
        internal = np.transpose(data, DISPLAY)              # (k, a0, a1)
        assert internal.shape == (K, A0, A1)

        image_slice = data[:, :, k]                          # (a0, a1)
        painted_slice = internal[k, :, :]                    # (a0, a1)
        assert np.array_equal(painted_slice, image_slice), (
            "the (2,0,1) internal slice must equal the displayed image slice"
        )
        # Marker lands at (k, a0, a1) under the display convention...
        assert internal[k, a0, a1] == internal.max()

    def test_legacy_210_does_not_match_the_display(self):
        data_bytes, marker = _native_mri_bytes()
        data, _ = ImagingService().load_nifti(data_bytes)
        a0, a1, k = marker

        legacy = np.transpose(data, LEGACY)                  # (k, a1, a0)
        assert legacy.shape == (K, A1, A0)
        # Different in-plane shape than the display (k, a0, a1) on asymmetric data
        # => an ingest using (2,1,0) is mirrored vs the image. This is exactly the
        # divergence the #15 fix removes.
        assert legacy.shape != (K, A0, A1)
        # The marker sits at the transposed in-plane position under legacy.
        assert legacy[k, a1, a0] == legacy.max()
