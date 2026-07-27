"""RC-030 — lesion connectivity (18-connected) and a single min-volume floor.

Risk control for HAZ-005 (incorrect lesion count / region classification).

Lesion count and DIS ("a region is present if it has a qualifying lesion") depend
on the neighbourhood connectivity used to split a mask into discrete lesions. The
code previously used scipy.ndimage.label's DEFAULT (6-connectivity, faces only),
which over-counts relative to the two canonical MS challenges:

  - ISBI-2015 (Carass et al. 2017): lesions are the 18-connected components.
  - MSSEG-2016 (Commowick et al. 2018): detection uses an 18-connectivity kernel.

These tests pin the connectivity to EXACTLY 18 (faces + edges, not corners) and
prove a single shared min-volume floor, so a regression to 6-connectivity or a
re-duplicated threshold turns CI red.

Negative control (CAPA-001 §5): revert label_lesions to scipy's default
connectivity, or drop the shared floor, and the tests below MUST fail.
"""
import numpy as np
import pytest

from app.services.lesion_metrics import (
    MIN_LESION_VOLUME_MM3,
    label_lesions,
    lesion_structuring_element,
    meets_min_volume,
)


class TestRC030ConnectivityIsExactly18:
    """18-connectivity = faces + edges. The discriminating cases:
    - an EDGE-touching voxel pair (differ in 2 axes) is ONE lesion under 18/26
      but TWO under 6  → proves we are not on scipy's 6-connected default.
    - a CORNER-touching voxel pair (differ in all 3 axes) is ONE under 26 but
      TWO under 18     → proves we are not on 26-connectivity either.
    Together they pin the connectivity to exactly 18.
    """

    def test_rc030_structuring_element_is_rank2_18_connected(self):
        se = lesion_structuring_element()
        assert se.shape == (3, 3, 3)
        # 18-connectivity: the centre plus all voxels within L1 distance 2 of the
        # centre except the 8 corners (L1 distance 3). Count of True = 19
        # (centre + 18 neighbours).
        assert int(se.sum()) == 19
        # Corners (all three offsets = ±1) must be EXCLUDED.
        assert se[0, 0, 0] == False and se[2, 2, 2] == False and se[0, 2, 0] == False

    def test_rc030_edge_touching_voxels_are_one_lesion(self):
        """Two voxels sharing a cube EDGE (differ in y and z) → ONE lesion under
        18-connectivity. Under scipy's 6-connected default they would be TWO."""
        mask = np.zeros((3, 3, 3), dtype=np.uint8)
        mask[1, 0, 0] = 1
        mask[1, 1, 1] = 1  # differs in 2 axes (edge neighbour)
        _, n = label_lesions(mask)
        assert n == 1, "edge-touching voxels must merge under 18-connectivity"

    def test_rc030_corner_touching_voxels_are_two_lesions(self):
        """Two voxels sharing only a cube CORNER (differ in all 3 axes) → TWO
        lesions under 18-connectivity (they would be ONE under 26)."""
        mask = np.zeros((3, 3, 3), dtype=np.uint8)
        mask[0, 0, 0] = 1
        mask[1, 1, 1] = 1  # differs in 3 axes (corner neighbour)
        _, n = label_lesions(mask)
        assert n == 2, "corner-only-touching voxels must stay separate under 18-connectivity"

    def test_rc030_face_touching_voxels_are_one_lesion(self):
        mask = np.zeros((3, 3, 3), dtype=np.uint8)
        mask[1, 1, 1] = 1
        mask[1, 1, 2] = 1  # face neighbour
        _, n = label_lesions(mask)
        assert n == 1

    def test_rc030_default_scipy_connectivity_would_over_count(self):
        """Documents the bug being fixed: scipy's default (6-conn) splits the
        edge-touching lesion into two — the over-count RC-030 removes."""
        from scipy.ndimage import label as scipy_default_label

        mask = np.zeros((3, 3, 3), dtype=np.uint8)
        mask[1, 0, 0] = 1
        mask[1, 1, 1] = 1
        _, n_default = scipy_default_label(mask)  # no structure → 6-connectivity
        _, n_ours = label_lesions(mask)
        assert n_default == 2 and n_ours == 1, (
            "scipy default must over-count where 18-connectivity does not"
        )


class TestRC030MinVolumeFloor:
    def test_rc030_floor_is_the_msseg_value(self):
        assert MIN_LESION_VOLUME_MM3 == 3.0

    def test_rc030_floor_is_volume_based_not_voxel_count(self):
        """Resolution-independence: 2 voxels at 2mm iso = 16 mm3 passes; 2 voxels
        at 1mm iso = 2 mm3 fails. The floor is mm3, never a raw voxel count."""
        assert meets_min_volume(voxel_count=2, voxel_volume_mm3=8.0) is True   # 16 mm3
        assert meets_min_volume(voxel_count=2, voxel_volume_mm3=1.0) is False  # 2 mm3

    def test_rc030_floor_boundary_is_inclusive(self):
        assert meets_min_volume(voxel_count=3, voxel_volume_mm3=1.0) is True   # exactly 3 mm3


class TestRC030SingleSourceOfTruth:
    """The threshold and connectivity must not be re-duplicated. The two analysis
    services must IMPORT from lesion_metrics, not redefine a literal."""

    def test_rc030_services_import_the_shared_floor(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "app" / "services"
        for name in ("lesion_analysis_service.py", "ms_region_classifier.py",
                     "longitudinal_tracking_service.py"):
            src = (root / name).read_text(encoding="utf-8")
            assert "from app.services.lesion_metrics import" in src, (
                f"{name} does not import the shared lesion metrics"
            )

    def test_rc030_no_service_redefines_the_threshold_literal(self):
        from pathlib import Path
        import re

        root = Path(__file__).resolve().parents[2] / "app" / "services"
        for name in ("lesion_analysis_service.py", "ms_region_classifier.py"):
            src = (root / name).read_text(encoding="utf-8")
            assert not re.search(r"^MIN_LESION_VOLUME_MM3\s*=", src, re.M), (
                f"{name} redefines MIN_LESION_VOLUME_MM3 instead of importing it"
            )


class TestRC030EndToEndLesionCount:
    """The wiring works: an edge-touching lesion is counted once by the real
    analysis path, not twice."""

    def test_rc030_analyze_lesions_counts_edge_touching_as_one(self):
        from app.services.lesion_analysis_service import analyze_lesions

        mask = np.zeros((5, 5, 5), dtype=np.int32)
        # A single lesion whose two halves touch only along an edge.
        mask[2, 1, 1] = 1
        mask[2, 2, 2] = 1
        result = analyze_lesions(mask, (2.0, 2.0, 2.0))  # 8 mm3/voxel → passes floor
        assert result.get("total_count") == 1, (
            f"expected 1 lesion, got {result.get('total_count')}: edge-touching "
            "voxels must not be double-counted"
        )
