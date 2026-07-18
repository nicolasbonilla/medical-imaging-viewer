"""RC-024 — voxel spacing is required, never assumed (CAPA-001 CA-5).

Risk control for HAZ-014 (measurement computed from assumed geometry).

Four route handlers independently defaulted to `(1.0, 1.0, 1.0)` when spacing
metadata was absent, and to a 1.0 slice thickness via `float(st or 1.0)` even
when pixel spacing WAS present. Lesion volumes are `voxel_count x product(spacing)`,
so a study acquired at 3 mm slice thickness had every reported volume in mm3
understated threefold — with no warning and full apparent precision. Those
volumes feed the MAGNIMS/McDonald lesion-size thresholds that determine
dissemination in space, so the error participates in a diagnosis.

CAPA-001 CA-5 acceptance criterion: "Raises when spacing is unavailable; test
with 3 mm slice thickness."

Negative control (CAPA-001 §5): make `resolve_voxel_spacing` return
`(1.0, 1.0, 1.0)` instead of raising, and these tests MUST fail.
"""
import pytest

from app.utils.spacing_utils import (
    VoxelSpacingUnavailableError,
    resolve_voxel_spacing,
)


class _Meta:
    """Metadata double matching the shape the routes actually pass."""

    def __init__(self, extra_fields=None):
        self.extra_fields = extra_fields


def _meta(pixel_spacing=None, slice_thickness=None):
    return _Meta({"pixel_spacing": pixel_spacing, "slice_thickness": slice_thickness})


class TestRC024ResolvesRealSpacing:
    def test_rc024_returns_spacing_in_thickness_row_column_order(self):
        spacing = resolve_voxel_spacing(_meta([0.9, 0.9], 3.0))
        assert spacing == (3.0, 0.9, 0.9)

    def test_rc024_preserves_anisotropic_3mm_geometry(self):
        """The acceptance criterion case. A 3 mm study must resolve to 3 mm —
        this is the value that was previously replaced by 1.0."""
        thickness, row, column = resolve_voxel_spacing(_meta([1.0, 1.0], 3.0))

        assert thickness == 3.0
        # The concrete harm: volume per voxel is 3x what the old code assumed.
        assert thickness * row * column == pytest.approx(3.0)

    def test_rc024_accepts_isotropic_1mm(self):
        assert resolve_voxel_spacing(_meta([1.0, 1.0], 1.0)) == (1.0, 1.0, 1.0)

    def test_rc024_accepts_string_values_from_dicom_headers(self):
        """DICOM values often arrive as strings; that is not a missing value."""
        assert resolve_voxel_spacing(_meta(["0.5", "0.5"], "2.0")) == (2.0, 0.5, 0.5)


class TestRC024RefusesToAssume:
    """The core assertion. Every one of these previously produced a confident,
    wrong measurement instead of an error."""

    def test_rc024_raises_when_metadata_is_absent(self):
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(_Meta(None))

    def test_rc024_raises_when_the_object_has_no_extra_fields(self):
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(object())

    def test_rc024_raises_when_pixel_spacing_is_missing(self):
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(_meta(None, 3.0))

    def test_rc024_raises_when_slice_thickness_is_missing(self):
        """The insidious half: pixel spacing present, so the metadata LOOKED
        adequate, and `st or 1.0` quietly substituted 1 mm."""
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(_meta([0.9, 0.9], None))

    def test_rc024_raises_when_slice_thickness_is_zero(self):
        """`0 or 1.0` evaluates to 1.0 in Python — the old code could not tell a
        zero thickness from an absent one."""
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(_meta([0.9, 0.9], 0))

    def test_rc024_raises_on_negative_spacing(self):
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(_meta([0.9, -1.0], 3.0))

    def test_rc024_raises_on_non_finite_spacing(self):
        """A NaN would propagate silently into every downstream statistic."""
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(_meta([0.9, float("nan")], 3.0))
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(_meta([0.9, 0.9], float("inf")))

    def test_rc024_raises_on_unparseable_values(self):
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(_meta(["n/a", "n/a"], "unknown"))

    def test_rc024_raises_when_pixel_spacing_has_too_few_components(self):
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(_meta([0.9], 3.0))

    def test_rc024_never_returns_a_default_on_any_failure_path(self):
        """Guard against a future 'graceful fallback' being reintroduced. The
        whole defect was that a fallback existed and looked reasonable."""
        for bad in [
            _Meta(None),
            _meta(None, None),
            _meta([0.9, 0.9], None),
            _meta([0.9, 0.9], 0),
            _meta([], 3.0),
        ]:
            with pytest.raises(VoxelSpacingUnavailableError):
                resolve_voxel_spacing(bad)


class TestRC024ErrorIsActionable:
    """A refusal the operator cannot act on becomes a bug report, then pressure
    to restore the default."""

    def test_rc024_error_names_the_required_metadata(self):
        with pytest.raises(VoxelSpacingUnavailableError) as exc:
            resolve_voxel_spacing(_meta(None, None))

        message = str(exc.value)
        assert "PixelSpacing" in message
        assert "SliceThickness" in message

    def test_rc024_error_explains_why_a_default_is_not_acceptable(self):
        with pytest.raises(VoxelSpacingUnavailableError) as exc:
            resolve_voxel_spacing(_meta(None, None))

        assert "assumed geometry" in str(exc.value)

    def test_rc024_error_identifies_the_affected_study(self):
        with pytest.raises(VoxelSpacingUnavailableError) as exc:
            resolve_voxel_spacing(_meta(None, None), context="segmentation abc-123")

        assert "segmentation abc-123" in str(exc.value)

    def test_rc024_error_type_is_distinguishable_from_a_generic_failure(self):
        """It must not surface as a 500. The API handler keys on this type."""
        assert issubclass(VoxelSpacingUnavailableError, ValueError)
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(_Meta(None))


class TestRC024RoutesNoLongerAssume:
    """Guard the call sites, not only the helper. The defect lived in the routes,
    duplicated four times; deleting the helper's use would restore it."""

    ROUTES = [
        "app/api/routes/segmentation_regions.py",
        "app/api/routes/segmentation_analysis.py",
    ]

    def test_rc024_no_route_contains_a_silent_isotropic_default(self):
        from pathlib import Path

        backend_root = Path(__file__).resolve().parents[2]
        for rel in self.ROUTES:
            source = (backend_root / rel).read_text(encoding="utf-8")
            assert "voxel_spacing = (1.0, 1.0, 1.0)" not in source, (
                f"{rel} reintroduces the silent 1 mm isotropic default (HAZ-014)"
            )
            assert "float(st or 1.0)" not in source, (
                f"{rel} reintroduces the silent 1 mm slice-thickness substitution"
            )

    def test_rc024_routes_resolve_spacing_through_the_control(self):
        from pathlib import Path

        backend_root = Path(__file__).resolve().parents[2]
        for rel in self.ROUTES:
            source = (backend_root / rel).read_text(encoding="utf-8")
            assert "resolve_voxel_spacing(" in source, (
                f"{rel} no longer resolves spacing through RC-024"
            )


class TestRC024ServicesRefuseAnOmittedSpacing:
    """The 14 Class C service signatures that carried `= (1.0, 1.0, 1.0)`.

    Eleven now have no default at all — omitting the argument is a TypeError.
    Three take voxel_spacing AFTER an optional parameter, where Python forbids a
    bare required argument; those use the SPACING_REQUIRED sentinel so the
    parameter keeps its position (reordering would silently change the meaning
    of existing positional calls) while omission still raises.
    """

    def test_rc024_sentinel_is_rejected_at_runtime(self):
        from app.utils.spacing_utils import SPACING_REQUIRED, require_spacing

        with pytest.raises(VoxelSpacingUnavailableError, match="requires voxel_spacing"):
            require_spacing(SPACING_REQUIRED, caller="analyze")

    def test_rc024_sentinel_error_explains_the_previous_behaviour(self):
        from app.utils.spacing_utils import SPACING_REQUIRED, require_spacing

        with pytest.raises(VoxelSpacingUnavailableError) as exc:
            require_spacing(SPACING_REQUIRED, caller="analyze")

        assert "previously assumed 1 mm isotropic" in str(exc.value)

    def test_rc024_require_spacing_accepts_a_real_geometry(self):
        from app.utils.spacing_utils import require_spacing

        assert require_spacing((3.0, 0.9, 0.9), caller="analyze") == (3.0, 0.9, 0.9)

    def test_rc024_require_spacing_rejects_invalid_components(self):
        from app.utils.spacing_utils import require_spacing

        for bad in [(0.0, 1.0, 1.0), (-1.0, 1.0, 1.0), (float("nan"), 1.0, 1.0),
                    (1.0, 1.0), (1.0, 1.0, 1.0, 1.0), "abc", 3.0]:
            with pytest.raises(VoxelSpacingUnavailableError):
                require_spacing(bad, caller="analyze")

    def test_rc024_compute_dis_criteria_refuses_an_omitted_spacing(self):
        """End-to-end on a real Class C entry point: this call previously
        succeeded and returned DIS criteria derived from an assumed geometry."""
        import numpy as np
        from app.services.lesion_analysis_service import compute_dis_criteria

        with pytest.raises(VoxelSpacingUnavailableError):
            compute_dis_criteria(np.zeros((10, 10, 10), dtype=np.int32))

    def test_rc024_no_class_c_service_retains_a_spacing_default(self):
        from pathlib import Path

        backend_root = Path(__file__).resolve().parents[2]
        services = [
            "app/services/lesion_analysis_service.py",
            "app/services/longitudinal_tracking_service.py",
            "app/services/ms_region_classifier.py",
            "app/services/segmentation_comparison_service.py",
        ]
        for rel in services:
            source = (backend_root / rel).read_text(encoding="utf-8")
            assert "= (1.0, 1.0, 1.0)" not in source, (
                f"{rel} reintroduces a default voxel spacing — a caller that "
                "omits the argument would silently measure against an assumed "
                "1 mm isotropic geometry (HAZ-014)."
            )
