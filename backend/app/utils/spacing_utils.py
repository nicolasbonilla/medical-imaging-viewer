"""Voxel spacing resolution — IEC 62304 Class C.

Risk control RC-024 for HAZ-014 (measurement computed from assumed geometry).
Created by CAPA-001 action CA-5.

WHY THIS MODULE EXISTS
--------------------
Four route handlers independently contained this pattern:

    voxel_spacing = (1.0, 1.0, 1.0)
    if hasattr(metadata, 'extra_fields') and metadata.extra_fields:
        ps = metadata.extra_fields.get('pixel_spacing')
        st = metadata.extra_fields.get('slice_thickness')
        if ps and len(ps) >= 2:
            voxel_spacing = (float(st or 1.0), float(ps[0]), float(ps[1]))

When spacing metadata is absent, the code silently assumed 1 mm isotropic and
carried on. Lesion volumes are computed as `voxel_count × product(spacing)`, so
for a study acquired with 3 mm slice thickness every reported volume in mm³ is
understated by a factor of three — with no warning, no flag, and full apparent
precision. Those volumes then feed the MAGNIMS/McDonald lesion-size thresholds
that determine dissemination-in-space, i.e. they participate in a diagnosis.

The RMF recorded RC-022 as VERIFIED on the basis that "all images are
preprocessed to MNI 1 mm", verified by recollection. Even if that were true of
the development dataset, the code does not enforce it and does not check it —
it merely assumes it. HAZ-014 describes exactly this harm.

WHY IT RAISES INSTEAD OF DEFAULTING
-----------------------------------
A volume in mm³ derived from unknown geometry is not a measurement; it is a
number with a unit attached to it. Returning it is worse than returning nothing,
because a clinician cannot tell the two apart. CAPA-001 CA-5's acceptance
criterion is explicit: "Raises when spacing is unavailable."

Note that `float(st or 1.0)` above also silently substituted 1.0 whenever slice
thickness was 0, None, or absent — including on studies where pixel spacing WAS
present. That is the more insidious half: the metadata looked adequate.
"""
from typing import Any, Optional, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)

VoxelSpacing = Tuple[float, float, float]


class VoxelSpacingUnavailableError(ValueError):
    """Raised when voxel spacing cannot be established from image metadata.

    A distinct type so callers can render a specific, actionable message rather
    than a generic 500 — the user needs to know their study lacks the geometry
    metadata required for quantitative analysis, not that "something failed".
    """


class _SpacingRequired:
    """Sentinel marking `voxel_spacing` as mandatory where Python syntax forbids
    a bare required parameter.

    Three Class C functions take `voxel_spacing` AFTER an optional parameter, so
    it cannot simply lose its default — Python rejects a non-default argument
    following a defaulted one. The alternatives were both worse:

      - making it keyword-only (`*`) would break every positional caller;
      - reordering the signature would silently change the meaning of existing
        positional calls, which in a Class C module is precisely the kind of
        quiet breakage this CAPA exists to eliminate.

    So the parameter keeps its position and this sentinel takes the place of the
    old `(1.0, 1.0, 1.0)`. Omitting the argument now raises instead of quietly
    assuming a geometry.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return "<voxel_spacing: required>"


SPACING_REQUIRED = _SpacingRequired()


def require_spacing(value: Any, *, caller: str) -> VoxelSpacing:
    """Validate a caller-supplied voxel spacing, or raise.

    Used at the top of Class C analysis functions. Rejects the sentinel (the
    argument was omitted) and any physically impossible value.
    """
    if value is SPACING_REQUIRED or value is None:
        raise VoxelSpacingUnavailableError(
            f"{caller}() requires voxel_spacing. It was omitted, and this "
            "function previously assumed 1 mm isotropic — producing volumes in "
            "mm3 from an unknown geometry. Pass the study's real spacing, "
            "resolved via resolve_voxel_spacing()."
        )

    try:
        components = tuple(value)
    except TypeError:
        raise VoxelSpacingUnavailableError(
            f"{caller}() received a non-iterable voxel_spacing: {value!r}"
        )

    if len(components) != 3:
        raise VoxelSpacingUnavailableError(
            f"{caller}() requires three spacing components, received {len(components)}"
        )

    validated = tuple(_valid_dimension(component) for component in components)
    if any(component is None for component in validated):
        raise VoxelSpacingUnavailableError(
            f"{caller}() received an invalid voxel_spacing: {value!r}. "
            "Each component must be a positive, finite length in millimetres."
        )

    return validated  # type: ignore[return-value]


def _valid_dimension(value: Any) -> Optional[float]:
    """Coerce one spacing component, rejecting values that cannot be a length.

    Zero, negative and non-finite values are rejected rather than passed
    through: a 0 mm voxel yields a 0 mm³ volume, and a NaN propagates silently
    into every downstream statistic.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0.0 or number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def resolve_voxel_spacing(metadata: Any, *, context: str = "") -> VoxelSpacing:
    """Return (slice_thickness, row_spacing, column_spacing) in millimetres.

    Args:
        metadata: an object carrying `extra_fields` with `pixel_spacing` and
            `slice_thickness`, as produced by the imaging services.
        context: optional identifier (e.g. a segmentation id) included in the
            error message so the operator knows which study is affected.

    Raises:
        VoxelSpacingUnavailableError: if any component is missing or invalid.
            Never returns an assumed value.
    """
    extra = getattr(metadata, "extra_fields", None)
    if not extra:
        raise VoxelSpacingUnavailableError(_message("no image metadata", context))

    pixel_spacing = extra.get("pixel_spacing")
    slice_thickness = extra.get("slice_thickness")

    if not pixel_spacing or len(pixel_spacing) < 2:
        raise VoxelSpacingUnavailableError(_message("pixel spacing is missing", context))

    row = _valid_dimension(pixel_spacing[0])
    column = _valid_dimension(pixel_spacing[1])
    thickness = _valid_dimension(slice_thickness)

    missing = [
        name
        for name, value in (
            ("row spacing", row),
            ("column spacing", column),
            ("slice thickness", thickness),
        )
        if value is None
    ]
    if missing:
        raise VoxelSpacingUnavailableError(
            _message(f"{', '.join(missing)} missing or invalid", context)
        )

    spacing = (thickness, row, column)

    # Not an error, but worth recording: a near-1mm-isotropic assumption is what
    # the RMF believed universal (RC-022). Log when reality differs so the
    # assumption's failure is observable in production rather than inferred.
    if not all(abs(value - 1.0) < 0.01 for value in spacing):
        logger.info(
            "Non-isotropic-1mm voxel spacing in quantitative analysis",
            extra={"voxel_spacing": list(spacing), "spacing_context": context},
        )

    return spacing


def _message(reason: str, context: str) -> str:
    where = f" for {context}" if context else ""
    return (
        f"Cannot compute volumetric measurements{where}: {reason}. "
        "Voxel spacing is required — volumes in mm3 cannot be derived from an "
        "assumed geometry. Re-import the study with complete DICOM/NIfTI "
        "geometry metadata (PixelSpacing and SliceThickness)."
    )
