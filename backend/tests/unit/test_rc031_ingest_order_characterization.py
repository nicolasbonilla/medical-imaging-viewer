"""RC-031 step 3 — PROVE the true root cause is the SynthSeg INGEST transpose.

Risk control for HAZ-006 (mirrored overlay + mis-classified MAGNIMS regions).
Steps 1/1.5 localized the parcellation-overlay divergence to "the parcellation
arrives in (k,j,i) while the display uses (k,i,j)". This file pins WHERE that
order is set: the clinical-tool ingest, not any downstream load.

THE TWO TRANSPOSES THAT DISAGREE
--------------------------------
- INGEST (tool_runner_service.py:636), applied to every SynthSeg / LST-AI mask:
      mask_data = np.transpose(mask_data, (2, 1, 0))       # native (a0,a1,a2) -> (a2, a1, a0) = (k, a1, a0)
  The affine loaded one line above (img.affine) is DISCARDED, so this is a blind
  fixed transpose.
- DISPLAY convention, stated verbatim in the MSMask branch
  (segmentation_regions.py:566-574) and matched by painted masks
  (segmentation_service.py:157, np.zeros((depth,height,width))):
      np.transpose(zone_mask_raw, (2, 0, 1))               # native (a0,a1,a2) -> (a2, a0, a1) = (k, a0, a1)

(2,1,0) yields (k, a1, a0); (2,0,1) yields (k, a0, a1). The in-plane axes a0,a1
are SWAPPED — so an ingested parcellation is the in-plane TRANSPOSE of the
display grid. On a square slice (a0 == a1) the two shapes coincide and the
divergence is invisible (the step-1 blind spot); every case here uses a0 != a1.

WHY THIS IS WORSE THAN A COSMETIC OVERLAY BUG
---------------------------------------------
classify_lesions_with_parcellation (ms_region_classifier.py:138-142) REQUIRES
lesion_mask.shape == parcellation_mask.shape or it raises. A painted/AI lesion
mask is (k,a0,a1); an ingested parcellation is (k,a1,a0):
  - non-square data -> shapes differ -> it RAISES (fails loud, safe);
  - square data (256x256, the common MRI case) -> shapes match -> it SILENTLY
    compares each lesion voxel against the parcellation label at the TRANSPOSED
    position, mis-assigning MAGNIMS regions and therefore DIS. That silent path
    is the hazard.

SCOPE: evidence only. The fix is affine-robust reorientation at ingest
(reorient_array_to_reference to the MRI grid, then the (2,0,1) display transpose)
and is a Class-C behavior + stored-data-semantics change — it ships separately
with real-SynthSeg validation and a migration decision. This file proves the
compensation (0,2,1) reconciles the two conventions, ready for that fix.
"""
import numpy as np


# Asymmetric in-plane (a0 != a1) so the swap is a visible shape change; a2 (=k,
# slices) different again so no pair of axes is accidentally equal.
A0, A1, A2 = 5, 8, 3   # NIfTI-native axis0, axis1, axis2(=slices)

INGEST_TRANSPOSE = (2, 1, 0)    # tool_runner_service.py:636
DISPLAY_TRANSPOSE = (2, 0, 1)   # segmentation_regions.py:574 (MSMask), painted-mask convention
COMPENSATION = (0, 2, 1)        # in-plane swap reconciling ingest -> display


def _native_volume():
    # A parcellation as SynthSeg emits it: NIfTI-native (a0, a1, a2), with an
    # asymmetric marker so orientation is observable.
    v = np.zeros((A0, A1, A2), dtype=np.uint8)
    v[1, 6, 0] = 7   # distinct a0 (1) vs a1 (6)
    return v


class TestIngestAndDisplayTransposesDiverge:
    def test_ingest_yields_kji_display_yields_kij(self):
        native = _native_volume()
        ingested = np.transpose(native, INGEST_TRANSPOSE)   # (k, a1, a0)
        display = np.transpose(native, DISPLAY_TRANSPOSE)   # (k, a0, a1)

        assert ingested.shape == (A2, A1, A0)   # (3, 8, 5)
        assert display.shape == (A2, A0, A1)    # (3, 5, 8)
        assert ingested.shape != display.shape, (
            "on asymmetric data the ingest and display conventions differ in "
            "shape — the parcellation overlay is mirrored vs the image"
        )
        # The same physical voxel lands at transposed in-plane positions.
        assert ingested[0, 6, 1] == 7   # (k, a1=6, a0=1)
        assert display[0, 1, 6] == 7    # (k, a0=1, a1=6)

    def test_square_slice_would_hide_the_divergence(self):
        # If a0 == a1, both conventions produce the SAME shape and no dims-based
        # check (frontend heuristic or shape-match guard) can detect the swap.
        n = 16
        sq = np.zeros((n, n, A2), dtype=np.uint8)
        assert np.transpose(sq, INGEST_TRANSPOSE).shape == np.transpose(sq, DISPLAY_TRANSPOSE).shape


class TestCompensationReconcilesIngestToDisplay:
    def test_021_maps_ingested_onto_display_exactly(self):
        native = _native_volume()
        native[2, 3, 1] = 9   # second asymmetric marker

        ingested = np.transpose(native, INGEST_TRANSPOSE)      # (k, a1, a0)
        display = np.transpose(native, DISPLAY_TRANSPOSE)      # (k, a0, a1)

        reconciled = np.transpose(ingested, COMPENSATION)      # (k, a1, a0) -> (k, a0, a1)
        assert reconciled.shape == display.shape == (A2, A0, A1)
        assert np.array_equal(reconciled, display), (
            "(0,2,1) must carry the ingested parcellation exactly onto the "
            "display grid, voxel for voxel"
        )


class TestClassificationShapeGuardBehaviour:
    """Reproduce the ms_region_classifier shape guard to show the two regimes:
    non-square raises (safe), square silently proceeds on transposed data."""

    @staticmethod
    def _shapes_match(lesion_shape, parc_shape):
        # ms_region_classifier.py:138 — raises when these differ.
        return lesion_shape == parc_shape

    def test_nonsquare_lesion_vs_ingested_parcellation_would_raise(self):
        lesion_kij = (A2, A0, A1)          # painted/AI lesion, display convention
        parc_ingested = (A2, A1, A0)        # ingested parcellation
        assert not self._shapes_match(lesion_kij, parc_ingested), (
            "non-square: shapes differ, classifier raises — the safe regime"
        )

    def test_square_lesion_vs_ingested_parcellation_silently_matches(self):
        n = 16
        lesion_kij = (A2, n, n)
        parc_ingested = (A2, n, n)          # a0==a1 so ingest/display shapes coincide
        assert self._shapes_match(lesion_kij, parc_ingested), (
            "square: shapes coincide so the classifier proceeds — but the "
            "parcellation is in-plane transposed, silently mis-assigning regions"
        )
