"""The image under the mask on screen lies on the mask's grid — checked before a radiologist confirms (PRB-030).

RC-092 (REQ-SAFE-046; HAZ-006, HAZ-008). L1 of the last check of PR #69: the standard 2D view draws the open
segmentation over whatever image is selected. A radiologist could select another image of the study (e.g. the
original instead of the MNI-preprocessed one) while the segmentation stayed open; the mask was then drawn sheared
or cut off on the other grid, and both confirmations (the AI-draft review, RC-047, and the DIS confirmation, RC-071)
were accepted.

Both confirmations now state the image the standard 2D view drew under the mask (`displayed_image_file_id`). The
image is accepted when:
- it is the segmentation's own image, or an image of the SAME study (patient and study of the storage path). On
  MNI-registered data every image of every visit shares one grid, so the grid alone cannot tell the follow-up visit
  from the baseline;
- its header (read without loading the voxels) gives the mask's shape in the internal order (k, a0, a1);
- for another image than the segmentation's own: the same shape and voxel-to-scanner transform as the own image,
  every element within the RC-039 tolerance (a sub-millimetre shift or another voxel size is another grid).
Anything that cannot be read or told is refused (fail closed). The browser makes the shape check before any request
(frontend/src/utils/confirmDrawCheck.ts); like the drawn-label digest, this server check relies on what the client
states it drew (RMF-001 residual risk of RC-071).

This module decides; it reads image headers only and computes nothing about lesions.

@module services.displayed_image_check
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from app.security.storage_access import StorageRefError, parse_patient_storage_ref
from app.services.segmentation_service import SegmentationService

# RC-039: two voxel-to-scanner transforms describe the same grid when every element agrees within this tolerance.
GRID_TOLERANCE = 1e-3

NOT_STATED = ("The confirmation does not say which image was under the segmentation on screen, so it cannot be "
              "checked that the mask was drawn on its own grid. Reload the viewer and confirm in the Standard view.")
OTHER_STUDY = ("The image under the segmentation on screen is not an image of this segmentation's study (another "
               "visit or another patient). Show an image of the same study under the segmentation, check it, then "
               "confirm.")
UNREADABLE = ("The image under the segmentation on screen could not be read, so it cannot be checked that it lies on "
              "the mask's grid. Show the segmentation's own image under it, check it, then confirm.")


def _grid_text(shape: Sequence[int]) -> str:
    """columns x rows x slices of a NIfTI shape (a0, a1, k), as the viewer names an image."""
    return f"{shape[1]} × {shape[0]} × {shape[2]}"


def _mask_text(mask_shape: Sequence[int]) -> str:
    """width x height x depth of an internal mask (k, a0, a1)."""
    return f"{mask_shape[2]} × {mask_shape[1]} × {mask_shape[0]}"


async def _header(storage_service: Any, bucket: str, file_id: str):
    shape, affine, _hdr = SegmentationService.nifti_header_grid(await storage_service.download_file(bucket, file_id))
    if len(shape) < 3 or np.shape(affine) != (4, 4):
        raise ValueError("not a 3D image")
    return tuple(int(v) for v in shape[:3]), np.asarray(affine, dtype=float)


async def displayed_image_problem(displayed_file_id: Any, own_file_id: Optional[str], mask_shape: Sequence[int],
                                  storage_service: Any, bucket: str) -> Optional[str]:
    """Why the confirmation must be refused because of the image under the mask, or None when it lies on its grid.

    The caller authorizes the user for `displayed_file_id` (when it is not the segmentation's own image) BEFORE this
    reads it."""
    displayed = str(displayed_file_id or "").strip()
    own = str(own_file_id or "").strip()
    if not displayed:
        return NOT_STATED
    same_file = displayed == own
    path = displayed
    if not same_file:
        try:
            shown, segmented = parse_patient_storage_ref(displayed), parse_patient_storage_ref(own)
        except StorageRefError:
            return OTHER_STUDY
        if (shown.patient_id, shown.study_id) != (segmented.patient_id, segmented.study_id):
            return OTHER_STUDY
        path = shown.object_path
    try:
        shape, affine = await _header(storage_service, bucket, path)
        own_grid = None if same_file else await _header(storage_service, bucket, own)
    except Exception:  # noqa: BLE001 — anything unreadable is refused (fail closed)
        return UNREADABLE
    internal = (shape[2], shape[0], shape[1])
    if tuple(int(v) for v in mask_shape) != internal:
        return (f"The image under the segmentation on screen is on another grid than the mask (image "
                f"{_grid_text(shape)}, mask {_mask_text(mask_shape)}, columns × rows × slices): the mask is drawn "
                "sheared or cut off. Show the segmentation's own image (or one on its grid) under it, check it, then "
                "confirm.")
    if own_grid is not None:
        own_shape, own_affine = own_grid
        if own_shape != shape or not np.allclose(own_affine, affine, atol=GRID_TOLERANCE, rtol=0):
            return ("The image under the segmentation on screen is on another grid than the mask (another voxel size, "
                    "position or orientation): the mask is not drawn where its lesions are. Show the segmentation's "
                    "own image (or one on its grid) under it, check it, then confirm.")
    return None
