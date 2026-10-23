"""Slice thickness of the ORIGINAL acquisition of a stored image — read, never guessed.

REQ-FUNC-099, REQ-SAFE-034; risk control RC-054 (HAZ-015, HAZ-001).
Change CP-SLICE-THICKNESS-001 — DRAFT, PENDING owner approval.

Why this exists
---------------
Paper A v0.3 (PR #54, ``docs/research/paper/RESULTS-v0.3.md``) found that automatic
MS-lesion detection depends on the slice thickness of the ORIGINAL acquisition, and that
a 1-mm grid is not evidence of a thin acquisition: MSLesSeg, the largest "1-mm" cohort,
was acquired with 2-5 mm FLAIR slices and resampled to MNI 1 mm, and within it detection
of 14-50 mm³ lesions fell from 74 % (2-2.3 mm) to 39 % (4-5 mm). The reliability card
(REQ-FUNC-098) therefore needs the acquisition thickness *and how it is known*.

States (``AcquisitionGeometry.state``)
--------------------------------------
``native``
    The thickness of the original acquisition, from the acquisition metadata of an
    ORIGINAL DICOM image that records a valid SliceThickness, when either the spacing
    between slices is recorded or the acquisition is 3D (so the slices are contiguous).
    ``effective_mm`` = max(SliceThickness, SpacingBetweenSlices) — a gap between slices
    counts. A spacing between slices without a SliceThickness is never used as the
    thickness (it is the distance between slice centres): such an image is
    ``not_determinable`` (reason ``missing``).
``at_least``
    Only a LOWER bound is known and it is above ``THIN_LIMIT_MM``: the stored grid of a
    NIfTI (an image cannot carry detail finer than its grid), a derived/reformatted
    DICOM, or a 2D DICOM without the spacing between slices. The acquisition may have
    been thicker still, so the client must read it as "this thick or thicker".
``not_determinable``
    Nothing reliable — with a ``reason``: missing, invalid or self-contradictory header
    values, a derived image or a fine (<= 1.5 mm) grid with no acquisition metadata
    (which may be a resampled thick acquisition), an unreadable header.

A NIfTI is never ``native``: it carries no acquisition metadata.

Never a default
---------------
Unlike ``ImageMetadata.slice_thickness`` (which is 1.0 mm for a DICOM without the tag),
no code path here returns a value that was not read from the file. Every function is
total: any unexpected input yields ``not_determinable`` with reason ``unreadable``,
never an exception, so image loading can never fail because of this module.

Class C boundary
----------------
``app.utils.nifti_utils`` and ``app.utils.dicom_utils`` are Class C and are NOT modified.
This module calls their extractors (``extract_nifti_metadata``,
``extract_dicom_metadata``) and only reads further header fields that those extractors
do not return (spacing between slices, image type, acquisition type, sform/qform codes).
"""
from __future__ import annotations

import math
from typing import Any, Iterable, List, Optional, Sequence

import numpy as np

from app.models.schemas import AcquisitionGeometry
from app.utils.dicom_utils import extract_dicom_metadata
from app.utils.nifti_utils import extract_nifti_metadata

METHOD_VERSION = "acq-geometry/1"

# A slice thickness at or below this is "thin" (Paper A v0.3 band B1, spec §2). Above it
# the study is treated as thick-slice for every purpose of the reliability card.
THIN_LIMIT_MM = 1.5

# Header values outside (0, PLAUSIBLE_MAX_MM] are treated as invalid, not clipped.
PLAUSIBLE_MAX_MM = 20.0

# Relative tolerance when comparing the NIfTI pixdim with the affine's column norms.
_PIXDIM_REL_TOL = 0.01
_PIXDIM_ABS_TOL_MM = 0.01

# Common template grids (MNI152 1 mm FSL / ICBM 2009 / SRI24-like, MNI 2 mm). Only used to
# make the "not determinable" reason more specific; never to accept a value.
_TEMPLATE_SHAPES = {
    (182, 218, 182),
    (181, 217, 181),
    (193, 229, 193),
    (197, 233, 189),
    (91, 109, 91),
    (240, 240, 155),
}
# NIfTI xform codes 3 (Talairach) and 4 (MNI 152): the image was put in template space.
_TEMPLATE_XFORM_CODES = {3, 4}

_UNIT_TO_MM = {"mm": 1.0, "meter": 1000.0, "micron": 0.001, "unknown": 1.0}

REASONS = (
    "missing",
    "invalid",
    "inconsistent_header",
    "derived_image",
    "thin_without_3d_or_spacing",
    "fine_grid_no_acquisition_metadata",
    "template_grid",
    "not_a_volume",
    "unreadable",
)


# ---------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------

def _not_determinable(reason: str, source: str = "none", **fields: Any) -> AcquisitionGeometry:
    assert reason in REASONS, reason
    return AcquisitionGeometry(
        state="not_determinable",
        effective_mm=None,
        source=source,
        reason=reason,
        method_version=METHOD_VERSION,
        **fields,
    )


def _plausible(value: Optional[float]) -> bool:
    return value is not None and math.isfinite(value) and 0.0 < value <= PLAUSIBLE_MAX_MM


def _to_float(value: Any) -> Optional[float]:
    """A DICOM DS/IS or number -> float; None when absent, empty or not numeric."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("ascii").strip()
        except Exception:  # noqa: BLE001
            return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _multi_value(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        parts = [p for p in value.split("\\")]
    elif isinstance(value, Iterable):
        parts = [str(p) for p in value]
    else:
        parts = [str(value)]
    parts = [p.strip().upper() for p in parts]
    return parts or None


def _functional_group_value(ds: Any, keyword: str) -> Any:
    """SliceThickness / SpacingBetweenSlices of an enhanced (multi-frame) image, from the
    shared functional groups only. Per-frame values are not combined (no guessing)."""
    try:
        shared = getattr(ds, "SharedFunctionalGroupsSequence", None)
        if not shared:
            return None
        measures = getattr(shared[0], "PixelMeasuresSequence", None)
        if not measures:
            return None
        return getattr(measures[0], keyword, None)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------------------
# DICOM
# ---------------------------------------------------------------------------------------

def derive_from_dicom_dataset(ds: Any) -> AcquisitionGeometry:
    """Acquisition geometry of a DICOM image. Total: never raises."""
    try:
        return _derive_from_dicom_dataset(ds)
    except Exception:  # noqa: BLE001 — fail to "not determinable", never break loading
        return _not_determinable("unreadable", source="dicom_header")


def _derive_from_dicom_dataset(ds: Any) -> AcquisitionGeometry:
    # Class C extractor (read-only use): top-level SliceThickness as it parses it.
    try:
        base = extract_dicom_metadata(ds)
    except Exception:  # noqa: BLE001 — e.g. an empty or malformed DS value
        return _not_determinable("unreadable", source="dicom_header")

    raw_thickness = base.get("slice_thickness")
    if raw_thickness is None:
        raw_thickness = _functional_group_value(ds, "SliceThickness")
    raw_spacing = getattr(ds, "SpacingBetweenSlices", None)
    if raw_spacing is None:
        raw_spacing = _functional_group_value(ds, "SpacingBetweenSlices")

    thickness = _to_float(raw_thickness)
    spacing = _to_float(raw_spacing)
    image_type = _multi_value(getattr(ds, "ImageType", None))
    acq_raw = getattr(ds, "MRAcquisitionType", None)
    acq_type = str(acq_raw).strip().upper() if acq_raw not in (None, "") else None

    fields = dict(
        slice_thickness_mm=thickness,
        spacing_between_slices_mm=spacing,
        mr_acquisition_type=acq_type,
        image_type=image_type,
    )

    thickness_ok = _plausible(thickness)
    spacing_ok = _plausible(spacing)
    if not thickness_ok and not spacing_ok:
        present = thickness is not None or spacing is not None
        return _not_determinable("invalid" if present else "missing", source="dicom_header", **fields)
    if not thickness_ok:
        # The spacing between slices is the distance between slice centres, not the thickness
        # of a slice (slices may overlap): without a valid SliceThickness the acquisition
        # thickness is missing or invalid, whatever the spacing (REQ-SAFE-034 (c)).
        return _not_determinable("invalid" if thickness is not None else "missing", source="dicom_header", **fields)

    effective = max(v for v, ok in ((thickness, thickness_ok), (spacing, spacing_ok)) if ok)
    original = bool(image_type) and image_type[0] == "ORIGINAL"

    if original and (spacing_ok or acq_type == "3D"):
        return AcquisitionGeometry(
            state="native", effective_mm=float(effective), source="dicom_header",
            reason=None, method_version=METHOD_VERSION, **fields,
        )

    # Not provably the original geometry: what is recorded is a lower bound only.
    reason = "derived_image" if not original else "thin_without_3d_or_spacing"
    if effective > THIN_LIMIT_MM:
        return AcquisitionGeometry(
            state="at_least", effective_mm=float(effective), source="dicom_header",
            reason=reason, method_version=METHOD_VERSION, **fields,
        )
    return _not_determinable(reason, source="dicom_header", **fields)


# ---------------------------------------------------------------------------------------
# NIfTI
# ---------------------------------------------------------------------------------------

def derive_from_nifti_image(img: Any) -> AcquisitionGeometry:
    """Acquisition geometry of a NIfTI image: a lower bound or nothing. Total: never raises."""
    try:
        return _derive_from_nifti_image(img)
    except Exception:  # noqa: BLE001 — fail to "not determinable", never break loading
        return _not_determinable("unreadable", source="nifti_grid")


def _xform_codes(img: Any) -> Sequence[int]:
    codes = []
    header = getattr(img, "header", None)
    for key in ("sform_code", "qform_code"):
        try:
            codes.append(int(header[key]))
        except Exception:  # noqa: BLE001
            continue
    return codes


def _derive_from_nifti_image(img: Any) -> AcquisitionGeometry:
    # Class C extractor (read-only use): shape, pixdim, affine, spatial unit.
    meta = extract_nifti_metadata(img)
    shape = tuple(int(s) for s in meta.get("shape") or ())
    if len(shape) < 3 or min(shape[:3]) < 2:
        return _not_determinable("not_a_volume", source="nifti_grid")

    unit = str(meta.get("spatial_unit") or "unknown")
    scale = _UNIT_TO_MM.get(unit)
    if scale is None:
        return _not_determinable("invalid", source="nifti_grid")

    affine = np.asarray(meta.get("affine"), dtype=float)
    pixdim = np.asarray(meta.get("voxel_sizes") or [], dtype=float)[:3]
    if affine.shape != (4, 4) or pixdim.shape != (3,) or not np.all(np.isfinite(affine)):
        return _not_determinable("invalid", source="nifti_grid")

    grid = np.linalg.norm(affine[:3, :3], axis=0) * scale  # mm between voxel centres, per axis
    grid_list = [round(float(g), 4) for g in grid]
    if not all(_plausible(float(g)) for g in grid):
        return _not_determinable("invalid", source="nifti_grid", grid_spacing_mm=grid_list)

    pix_mm = np.abs(pixdim) * scale
    if np.any(np.abs(pix_mm - grid) > _PIXDIM_ABS_TOL_MM + _PIXDIM_REL_TOL * grid):
        return _not_determinable("inconsistent_header", source="nifti_grid", grid_spacing_mm=grid_list)

    through_plane = float(np.max(grid))
    if through_plane > THIN_LIMIT_MM:
        return AcquisitionGeometry(
            state="at_least", effective_mm=round(through_plane, 4), source="nifti_grid",
            reason=None, grid_spacing_mm=grid_list, method_version=METHOD_VERSION,
        )

    templated = shape[:3] in _TEMPLATE_SHAPES or any(c in _TEMPLATE_XFORM_CODES for c in _xform_codes(img))
    return _not_determinable(
        "template_grid" if templated else "fine_grid_no_acquisition_metadata",
        source="nifti_grid", grid_spacing_mm=grid_list,
    )
