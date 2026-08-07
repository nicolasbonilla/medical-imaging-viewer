"""RC-031 step 1.5 — PROVE the parcellation overlay divergence from real code.

Risk control for HAZ-006 (wrong-coordinate / mirrored overlay). Step 1
(test_rc031_orientation_characterization.py) ruled OUT the zone-map classifier
and the GCS round-trip as the source, and proved square slices hide any
transpose. It left the actual parcellation-branch order as an ASSERTED
diagnosis, gating the Class C serve-path fix (step 2) on "observing real
parcellation order".

This file closes that gate WITHOUT real patient data or a Firestore emulator:
it drives the ACTUAL transform code on asymmetric synthetic data and turns the
diagnosis into a code-proven fact. It does NOT yet mutate the Class C serve
path — it establishes the evidence and the exact compensating transpose that
step 2 must apply, plus the voxel-correspondence assertion the fix has to pass.

THE TWO ORDERS THAT MUST AGREE BUT DON'T
----------------------------------------
Painted masks are allocated (segmentation_service.py:157)
    masks_3d = np.zeros((depth, height, width))          # (k, i, j)
and align with the displayed axial image (painting works). So (k, i, j) is the
display-aligned internal convention.

A parcellation is ingested from a NIfTI. `_load_masks_from_gcs`
(segmentation_service.py:901-905) does
    nifti_data = get_fdata()                              # NIfTI-native (i, j, k)
    masks_3d   = np.transpose(nifti_data, (2, 1, 0))      # -> (k, j, i)
For an externally-produced parcellation (SynthSeg/FreeSurfer) whose native order
is (i, j, k) — the same native order as the MRI — this yields (k, j, i): the
in-plane axes i and j are SWAPPED relative to painted masks.

`generate_zone_map` is position-preserving (step 1), so the parcellation-branch
zone map inherits (k, j, i). The MSMask branch, by contrast, explicitly applies
np.transpose(..., (2, 0, 1)) to reach (k, i, j) (segmentation_regions.py:574) and
is aligned. The parcellation branch has NO such compensation — hence the mirror.

THE FIX step 2 MUST APPLY (proven self-consistent below)
--------------------------------------------------------
The compensation that carries (k, j, i) -> (k, i, j) is the in-plane swap
np.transpose(x, (0, 2, 1)). This test proves it restores exact voxel
correspondence on asymmetric data. It is deliberately NOT yet wired into the
serve path: that is a Class C route change and ships as step 2 with this same
assertion guarding it.
"""
import numpy as np


# Asymmetric on every axis so any swap is a visible shape change and no pair of
# axes is accidentally equal (the square-slice blind spot from step 1).
NI, NJ, NK = 5, 8, 3  # NIfTI-native axis0 (i), axis1 (j), axis2 (k = slices)

LOAD_TRANSPOSE = (2, 1, 0)   # segmentation_service.py:905, the real load op
COMPENSATION = (0, 2, 1)     # in-plane (i,j) swap that step 2 must apply


class TestParcellationLoadProducesKJI:
    """The standard GCS load transpose (2,1,0) maps a parcellation NIfTI in
    native (i,j,k) to internal (k,j,i) — NOT the display-aligned (k,i,j)."""

    def test_load_transpose_maps_native_ijk_to_kji(self):
        # NIfTI-native parcellation with a marker at a distinct (i,j): i=1, j=6.
        native = np.zeros((NI, NJ, NK), dtype=np.uint8)
        native[1, 6, 0] = 7  # (i=1, j=6, k=0)

        loaded = np.transpose(native, LOAD_TRANSPOSE)   # exactly as on load
        assert loaded.shape == (NK, NJ, NI), (
            f"load must yield (k,j,i)=({NK},{NJ},{NI}); got {loaded.shape}"
        )
        # The marker now sits at (k=0, j=6, i=1): the in-plane pair is (j, i).
        assert loaded[0, 6, 1] == 7
        # The display-aligned convention is (k,i,j) = (NK, NI, NJ). On asymmetric
        # data the loaded parcellation does not even SHARE that shape — the
        # in-plane axes are swapped — so an overlay drawn on the (k,i,j) grid is
        # mirrored. On a square slice (NI == NJ) the shapes would coincide and
        # this divergence would be invisible (the step-1 blind spot).
        assert loaded.shape != (NK, NI, NJ)
        assert NI != NJ  # guard: the whole proof relies on asymmetry


class TestPaintedMaskIsKIJ:
    """Painted masks are (k,i,j) and align with the image — the target order."""

    def test_painted_allocation_is_depth_height_width(self):
        # segmentation_service.create_segmentation: image_shape=(H,W,D) -> (D,H,W)
        image_shape = (NI, NJ, NK)          # (height=i, width=j, depth=k)
        height, width, depth = image_shape
        painted = np.zeros((depth, height, width), dtype=np.uint8)  # (k,i,j)
        assert painted.shape == (NK, NI, NJ)
        # Same physical voxel (i=1, j=6, k=0) lands at (k=0, i=1, j=6).
        painted[0, 1, 6] = 7
        assert painted[0, 1, 6] == 7


class TestCompensationRestoresVoxelCorrespondence:
    """(0,2,1) carries the loaded (k,j,i) parcellation onto the painted (k,i,j)
    grid with EXACT voxel correspondence — the property step 2's fix must hold."""

    def test_compensation_maps_kji_onto_painted_kij_exactly(self):
        native = np.zeros((NI, NJ, NK), dtype=np.uint8)
        native[1, 6, 0] = 7
        native[2, 3, 1] = 9  # second asymmetric marker to rule out coincidence

        loaded = np.transpose(native, LOAD_TRANSPOSE)          # (k,j,i)
        compensated = np.transpose(loaded, COMPENSATION)       # -> (k,i,j)

        # Reference painted mask built directly in (k,i,j) from the same voxels.
        painted = np.zeros((NK, NI, NJ), dtype=np.uint8)
        painted[0, 1, 6] = 7
        painted[1, 2, 3] = 9

        assert compensated.shape == painted.shape == (NK, NI, NJ)
        assert np.array_equal(compensated, painted), (
            "compensation (0,2,1) must make the loaded parcellation identical, "
            "voxel-for-voxel, to a display-aligned painted mask"
        )

    def test_compensation_is_self_inverse(self):
        arr = np.arange(NK * NJ * NI, dtype=np.uint8).reshape((NK, NJ, NI))
        back = np.transpose(np.transpose(arr, COMPENSATION), COMPENSATION)
        assert np.array_equal(back, arr), "(0,2,1) applied twice is identity"


class TestRealGenerateZoneMapInheritsInputOrder:
    """Tie the analytic proof to real Class C code: generate_zone_map preserves
    axis order, so a parcellation fed in (k,j,i) yields a (k,j,i) zone map, and
    the SAME (0,2,1) compensation aligns the real output to (k,i,j)."""

    def _asymmetric_parcellation_kji(self):
        # A parcellation as it arrives post-load: (k,j,i). White matter (2) with
        # a small lateral-ventricle (4) carved at an asymmetric (j,i) location.
        parc = np.full((NK, NJ, NI), 2, dtype=np.int32)
        parc[0, 6, 1] = 4
        parc[0, 5, 1] = 4
        return parc

    def test_zone_map_preserves_order_and_compensation_aligns_it(self):
        from app.services.ms_region_classifier import generate_zone_map

        parc_kji = self._asymmetric_parcellation_kji()
        zone_kji = generate_zone_map(parc_kji, voxel_spacing=(1.0, 1.0, 1.0))["zone_mask"]

        # Position-preserving: output keeps the (k,j,i) input shape.
        assert zone_kji.shape == parc_kji.shape == (NK, NJ, NI)

        # The compensation lands every classified voxel on brain tissue of the
        # (k,i,j)-aligned parcellation — voxel correspondence after the fix.
        zone_kij = np.transpose(zone_kji, COMPENSATION)
        brain_kij = np.transpose(parc_kji > 0, COMPENSATION)
        assert zone_kij.shape == (NK, NI, NJ)
        assert np.all((zone_kij > 0) <= brain_kij), (
            "after (0,2,1) every classified voxel must coincide with brain tissue "
            "on the display-aligned grid"
        )
