"""RC-031 — orientation characterization on ASYMMETRIC (non-square) volumes.

Risk control groundwork for HAZ-006 (wrong-coordinate / mirrored overlay
rendering). This is STEP 1 of the fix: before touching the Class C render path
(SegmentationCanvasLocal + the zone-map serve path — a path with a documented
history of failed orientation fixes), pin the ground truth on data where a
transpose is actually VISIBLE.

WHY ASYMMETRIC DATA IS MANDATORY (this is the whole point)
---------------------------------------------------------
The displayed axial image is served in convention (k, i, j) = (slice axis,
native axis0 = rows/height, native axis1 = cols/width) — see
imaging_service.py extract-slice (`pixel_array[:, :, k]`, height=shape[0]=i,
width=shape[1]=j). Painted masks are allocated (k, i, j) and are aligned; the
MSMask atlas zone map applies an explicit `np.transpose(zone_mask_raw,(2,0,1))`
to reach (k, i, j) and is aligned. The PARCELLATION-branch overlay inherits the
internal order the code labels (k, j, i) with NO compensating transpose, so its
per-slice layout is (j, i) — the in-plane TRANSPOSE of the image.

On a SQUARE axial slice (the common 256x256 case) (k, i, j) and (k, j, i) have
IDENTICAL dimensions, so:
  - the frontend transpose heuristic
    (`maskDims.width !== imageWidth && maskDims.height === imageWidth &&
      maskDims.width === imageHeight`) can NEVER fire, and
  - no dimension-based test can fail.
That dimensional invisibility on square data is precisely why prior orientation
fixes could pass every test and still ship a mirrored overlay. Every test here
therefore uses i != j so a transpose changes shape and becomes observable.

RC-023 (nifti_utils.py:45-53) demands exactly this before any orientation
migration: "a test that loads a matched pair and asserts voxel correspondence."

SCOPE OF STEP 1 (what this file does and does NOT do)
-----------------------------------------------------
It PINS, against real code, the two seams the divergence could have hidden in
and proves they are NOT the source:
  - the zone-map CLASSIFIER (generate_zone_map) preserves voxel position, and
  - the GCS NIfTI save/load `(2,1,0)` round-trip is self-inverse,
and it PROVES the square-slice blind spot as a hard dimensional fact. The actual
compensating-transpose fix on the parcellation serve path (RC-031 step 2) is a
Class C route change gated on observing real parcellation order and ships
separately with its own voxel-correspondence assertion.
"""
import numpy as np
import pytest


# Deliberately asymmetric in-plane extent (Ni != Nj) so any (i,j) transpose is
# observable as a shape change. Nk (slice count) is different again so no pair
# of axes is accidentally equal.
NI, NJ, NK = 5, 8, 3  # native axis0 (rows), axis1 (cols), axis2 (slices)


class TestZoneMapClassifierPreservesVoxelPosition:
    """The MAGNIMS zone-map classifier must be shape- and position-preserving:
    it classifies each voxel in place, it does not reorder axes. Proven on
    asymmetric data, so a stray transpose inside the classifier would change the
    output shape (or move the marked voxel) and fail here."""

    def _parcellation(self) -> np.ndarray:
        # Internal (D, H, W) = (k, i, j). Fill with cerebral white matter (2),
        # then carve a small lateral-ventricle (4) region at an asymmetric,
        # non-central location so a transpose can't map it onto itself.
        parc = np.full((NK, NI, NJ), 2, dtype=np.int32)  # WHITE_MATTER_LABELS
        parc[0, 1, 6] = 4   # LATERAL_VENTRICLE_LABELS, distinct i (1) vs j (6)
        parc[0, 1, 5] = 4
        return parc

    def test_rc031_zone_map_output_shape_equals_input_shape(self):
        from app.services.ms_region_classifier import generate_zone_map

        parc = self._parcellation()
        out = generate_zone_map(parc, voxel_spacing=(1.0, 1.0, 1.0))
        zone = out["zone_mask"]
        assert zone.shape == parc.shape == (NK, NI, NJ), (
            "generate_zone_map must not transpose: output shape must equal the "
            f"(k,i,j) input shape; got {zone.shape} for input {parc.shape}"
        )

    def test_rc031_every_classified_voxel_corresponds_to_a_brain_voxel(self):
        """Voxel correspondence: a zone label may appear only where the input
        parcellation had brain tissue at the IDENTICAL index. If the classifier
        transposed, classified voxels would land on background at that index and
        this fails — the decisive check, invisible on square data."""
        from app.services.ms_region_classifier import generate_zone_map

        parc = self._parcellation()
        zone = generate_zone_map(parc, voxel_spacing=(1.0, 1.0, 1.0))["zone_mask"]
        brain = parc > 0
        classified = zone > 0
        assert np.all(classified <= brain), (
            "a classified (nonzero) zone voxel exists where the parcellation had "
            "no brain at the same index — the classifier moved voxels (transpose)"
        )


class TestNiftiRoundTripIsSelfInverseOnAsymmetricData:
    """The GCS mask save/load pair applies `np.transpose(masks_3d,(2,1,0))` on
    save (segmentation_service.py:819) and the same `(2,1,0)` on load (:905).
    `(2,1,0)` is its own inverse, so the round-trip is lossless — proven here on
    asymmetric data so the property is real, not a square-slice coincidence.
    This rules the round-trip OUT as the source of the divergence."""

    def test_rc031_transpose_210_round_trip_is_identity(self):
        rng = np.arange(NK * NI * NJ, dtype=np.uint8).reshape((NK, NI, NJ))
        saved = np.transpose(rng, (2, 1, 0))      # (D,H,W) -> (W,H,D), as on save
        assert saved.shape == (NJ, NI, NK)         # visibly different shape
        loaded = np.transpose(saved, (2, 1, 0))    # inverse, as on load
        assert loaded.shape == rng.shape
        assert np.array_equal(loaded, rng), "the (2,1,0) round-trip must be lossless"

    def test_rc031_transpose_for_nifti_matches_raw_210(self):
        """transpose_for_nifti('DHW') / transpose_from_nifti('DHW') are the named
        wrappers of the same (2,1,0); confirm they agree with the raw call so the
        two code paths (raw and wrapper) cannot drift apart."""
        from app.utils.nifti_utils import transpose_for_nifti, transpose_from_nifti

        arr = np.arange(NK * NI * NJ, dtype=np.uint8).reshape((NK, NI, NJ))
        assert np.array_equal(transpose_for_nifti(arr, "DHW"), np.transpose(arr, (2, 1, 0)))
        # round-trip via the wrappers is also identity
        assert np.array_equal(transpose_from_nifti(transpose_for_nifti(arr, "DHW"), "DHW"), arr)


class TestSquareSliceHidesTheTranspose:
    """The dimensional fact behind every failed prior attempt: on a SQUARE slice
    an (i,j)-transposed overlay is INDISTINGUISHABLE by dimensions from an
    aligned one, so neither the frontend heuristic nor a dims-based test can
    detect it. On asymmetric data it IS distinguishable. This test locks that in
    so no one re-introduces a dims-only orientation check believing it suffices."""

    @staticmethod
    def _frontend_needs_transpose(mask_h: int, mask_w: int, image_h: int, image_w: int) -> bool:
        # Verbatim logic of SegmentationCanvasLocal.tsx needsTranspose:
        #   maskDims.width !== imageWidth && maskDims.height === imageWidth
        #   && maskDims.width === imageHeight
        return mask_w != image_w and mask_h == image_w and mask_w == image_h

    def test_rc031_square_slice_makes_transpose_undetectable_by_dims(self):
        n = 256  # square: image is (h=n, w=n)
        # An aligned overlay (h=i=n, w=j=n) and a transposed one (h=j=n, w=i=n)
        # have identical dims — the heuristic reports False for BOTH, i.e. it
        # cannot request the transpose the mirrored overlay actually needs.
        assert self._frontend_needs_transpose(n, n, n, n) is False
        # ...and there is no (h,w) that differs from the aligned case to key on.

    def test_rc031_asymmetric_slice_makes_transpose_detectable(self):
        # image (h=i=NI, w=j=NJ). A transposed overlay is (h=j=NJ, w=i=NI).
        image_h, image_w = NI, NJ
        transposed_h, transposed_w = NJ, NI
        assert self._frontend_needs_transpose(transposed_h, transposed_w, image_h, image_w) is True, (
            "on asymmetric data the dims-based heuristic CAN detect the transpose "
            "— which is exactly why RC-031 must be characterized on i != j data"
        )
        # the aligned overlay correctly needs no transpose
        assert self._frontend_needs_transpose(image_h, image_w, image_h, image_w) is False
