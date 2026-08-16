"""API routes for segmentation ANALYSIS.

Comparison (Dice / agreement map), lesion analysis + McDonald DIS
assessment, longitudinal tracking, lesion annotations and DICOM-SEG
export. Split out of segmentation.py (C3 decomposition): same
/segmentation prefix, same handlers, mounted in main.py after the
CRUD router so no route is shadowed.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response
from datetime import datetime
from typing import Optional
import numpy as np

import struct

from app.security import get_current_active_user
from app.security.models import User
from app.core.logging import get_logger
from app.utils import resolve_voxel_spacing, VoxelSpacingUnavailableError
from app.core.interfaces.storage_interface import IStorageService
from app.core.container import get_segmentation_service, get_storage_service
from app.services.segmentation_service import SegmentationService
from app.services.segmentation_comparison_service import (
    compare_two_masks,
    compute_agreement_map,
)
from app.services.lesion_analysis_service import (
    analyze_lesions,
    compute_dis_criteria,
    MAGNIMS_REGIONS,
)
from app.services.longitudinal_tracking_service import compare_timepoints
from app.core.config import get_settings
from app.utils import load_nifti_from_bytes

settings = get_settings()

router = APIRouter(prefix="/segmentation", tags=["segmentation"])
logger = get_logger(__name__)


async def _voxel_spacing_from_source_image(file_id, storage_service, context: str):
    """Resolve (dz, dy, dx) in mm from a segmentation's SOURCE IMAGE.

    RC-024 required real voxel geometry, but every analysis route resolved it from
    the SEGMENTATION metadata via resolve_voxel_spacing() — and SegmentationMetadata
    never carries pixel_spacing/slice_thickness (it has no `extra_fields`). So
    resolve_voxel_spacing(seg_metadata) always raised and lesion-analysis /
    dis-assessment / compare returned 500 for every call. (The RC-024 unit test used
    a mock object WITH extra_fields, so it never exercised the real metadata.)

    The geometry lives on the source image. NIfTI zooms are native (za0, za1, zk);
    the internal mask is (D,H,W)=(k,a0,a1), so the spacing order is (zk, za0, za1).
    """
    if not file_id:
        raise VoxelSpacingUnavailableError(
            f"{context}: segmentation has no source image file_id; cannot resolve voxel spacing."
        )
    try:
        file_data = await storage_service.download_file(settings.GCS_BUCKET_NAME, file_id)
        img, _ = load_nifti_from_bytes(file_data, normalize=False)
        zooms = img.header.get_zooms()[:3]
    except Exception as e:
        raise VoxelSpacingUnavailableError(
            f"{context}: could not read voxel geometry from source image {file_id}: {e}"
        )
    if len(zooms) < 3 or not all(float(z) > 0 for z in zooms):
        raise VoxelSpacingUnavailableError(
            f"{context}: source image {file_id} has no usable voxel spacing (zooms={zooms})."
        )
    return (float(zooms[2]), float(zooms[0]), float(zooms[1]))


def _require_comparable_grid(shape_tp1, shape_tp2) -> None:
    """Reject a longitudinal comparison of two masks that don't share a voxel grid.

    Audit A-3. Both timepoints are loaded in the SAME canonical internal order
    (RC-031 for segmentations, the (2,0,1) transpose for instances / A-1), so equal
    shapes mean the same grid and a voxel-wise lesion comparison is valid. When the
    shapes DIFFER the old code transposed TP2 to whatever permutation made the sizes
    line up — but matching dimension SIZES does not imply matching anatomical AXES,
    and when two dims are equal (square in-plane) the permutation is ambiguous and
    was picked arbitrarily. That silently produced a plausible-but-wrong longitudinal
    result (new/resolved/enlarged lesion counts) — a Class C hazard.

    A real spatial mismatch between two independent acquisitions needs resampling /
    registration, not an axis permutation. We fail loud instead of guessing.
    """
    if tuple(shape_tp1) == tuple(shape_tp2):
        return
    same_dims = sorted(shape_tp1) == sorted(shape_tp2)
    if same_dims:
        detail = (
            f"Timepoint masks share the same voxel dimensions but in a different "
            f"axis order (TP1={tuple(shape_tp1)}, TP2={tuple(shape_tp2)}). Both are "
            f"loaded in the canonical orientation, so this indicates genuinely "
            f"different acquisitions; a voxel-wise longitudinal comparison requires "
            f"spatial registration/resampling, which is not applied here. Comparison "
            f"refused to avoid a silently mis-aligned result."
        )
    else:
        detail = (
            f"Timepoint masks are on different voxel grids "
            f"(TP1={tuple(shape_tp1)}, TP2={tuple(shape_tp2)}); they must be "
            f"registered/resampled to a common grid before comparison."
        )
    raise HTTPException(status_code=400, detail=detail)


@router.post("/compare")
async def compare_masks(
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Compare 2+ segmentation/expert masks.

    Request body:
    {
      "masks": [
        {"type": "segmentation", "id": "<segmentation_id>", "label": "My Seg"},
        {"type": "instance", "id": "<instance_id>", "label": "Expert 1"}
      ]
    }

    For type "segmentation": loads from segmentation cache/storage.
    For type "instance": loads NIfTI from GCS and converts to binary mask.

    Returns pairwise comparison metrics (Dice, Hausdorff, volume diff).
    """
    try:
        body = await request.json()
        mask_specs = body.get("masks", [])

        if len(mask_specs) < 2:
            raise HTTPException(status_code=400, detail="At least 2 masks required")

        # Load all masks
        loaded_masks = []
        # RC-024: compare_two_masks REQUIRES real voxel geometry (Hausdorff in mm,
        # volume). This route never resolved it -> compare_two_masks raised
        # VoxelSpacingUnavailableError -> 500 on every call (dead endpoint).
        # Resolve from the first mask that carries geometry: a segmentation's
        # SOURCE IMAGE, or an instance NIfTI's own header.
        resolved_spacing = None
        for spec in mask_specs:
            mask_type = spec.get("type")
            mask_id = spec.get("id")
            label = spec.get("label", mask_id)

            if mask_type == "segmentation":
                # Load from segmentation cache (marker-aware, correctly oriented).
                entry = segmentation_service.get_loaded(mask_id)
                if entry is None or entry.get("masks_3d") is None:
                    raise HTTPException(status_code=404, detail=f"Segmentation {mask_id} not found")
                mask_3d = entry["masks_3d"]
                loaded_masks.append({"mask": (mask_3d > 0).astype(np.uint8), "label": label})
                if resolved_spacing is None:
                    try:
                        meta = entry.get("metadata")
                        resolved_spacing = await _voxel_spacing_from_source_image(
                            getattr(meta, "file_id", None), storage_service,
                            context=f"segmentation {mask_id}",
                        )
                    except VoxelSpacingUnavailableError:
                        pass

            elif mask_type == "instance":
                # Load NIfTI from instance — prefer gcs_path (fast) over instance lookup (slow)
                gcs_path = spec.get("gcs_path")
                if not gcs_path:
                    # Lazy: only resolve the study service when an instance mask
                    # actually needs a GCS path (avoids a Firestore client init —
                    # and ADC requirement — for segmentation-only comparisons).
                    from app.core.container import get_study_service
                    instance = await get_study_service().get_instance(mask_id)
                    gcs_path = instance.gcs_object_name
                file_data = await storage_service.download_file(
                    settings.GCS_BUCKET_NAME, gcs_path
                )
                img, data = load_nifti_from_bytes(file_data, normalize=False)
                mask = (data > 0).astype(np.uint8)
                if mask.ndim == 3:
                    mask = np.transpose(mask, (2, 0, 1))  # RC-031: native (a0,a1,k) -> internal (k,a0,a1)
                loaded_masks.append({"mask": mask, "label": label})
                if resolved_spacing is None:
                    zooms = img.header.get_zooms()[:3]
                    if len(zooms) == 3 and all(float(z) > 0 for z in zooms):
                        resolved_spacing = (float(zooms[2]), float(zooms[1]), float(zooms[0]))
            else:
                raise HTTPException(status_code=400, detail=f"Unknown mask type: {mask_type}")

        if resolved_spacing is None:
            raise HTTPException(
                status_code=400,
                detail="Voxel spacing unavailable for the provided masks; cannot compute mm-based comparison metrics.",
            )

        # Compute pairwise metrics (skip pairs with shape mismatch)
        comparisons = []
        for i in range(len(loaded_masks)):
            for j in range(i + 1, len(loaded_masks)):
                if loaded_masks[i]["mask"].shape != loaded_masks[j]["mask"].shape:
                    logger.warning(
                        "Shape mismatch in comparison, skipping pair",
                        extra={
                            "label_a": loaded_masks[i]["label"],
                            "label_b": loaded_masks[j]["label"],
                            "shape_a": str(loaded_masks[i]["mask"].shape),
                            "shape_b": str(loaded_masks[j]["mask"].shape),
                        }
                    )
                    comparisons.append({
                        "label_a": loaded_masks[i]["label"],
                        "label_b": loaded_masks[j]["label"],
                        "dice": 0.0,
                        "hausdorff_mm": None,
                        "volume": {
                            "volume_a_mm3": 0,
                            "volume_b_mm3": 0,
                            "diff_percent": 0,
                        },
                        "per_slice_dice": [],
                        "error": f"Shape mismatch: {loaded_masks[i]['mask'].shape} vs {loaded_masks[j]['mask'].shape}",
                    })
                    continue
                result = compare_two_masks(
                    loaded_masks[i]["mask"],
                    loaded_masks[j]["mask"],
                    loaded_masks[i]["label"],
                    loaded_masks[j]["label"],
                    voxel_spacing=resolved_spacing,
                )
                comparisons.append(result)

        return {"comparisons": comparisons, "mask_count": len(loaded_masks)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error comparing masks", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@router.post("/agreement-map")
async def get_agreement_map(
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Compute voxel-wise agreement map across N masks.

    Returns binary data: [depth:4][height:4][width:4][mask_count:4][agreement_data:D*H*W bytes]
    Each voxel value = number of masks that agree (0 to N).
    """
    try:
        body = await request.json()
        mask_specs = body.get("masks", [])

        if len(mask_specs) < 2:
            raise HTTPException(status_code=400, detail="At least 2 masks required")

        loaded_masks = []
        for spec in mask_specs:
            mask_type = spec.get("type")
            mask_id = spec.get("id")

            if mask_type == "segmentation":
                mask_3d = segmentation_service.get_mask(mask_id)
                if mask_3d is None:
                    raise HTTPException(status_code=404, detail=f"Segmentation {mask_id} not found")
                loaded_masks.append((mask_3d > 0).astype(np.uint8))

            elif mask_type == "instance":
                # Lazy study-service resolution — see compare_masks (avoids a
                # Firestore/ADC dependency for segmentation-only requests).
                from app.core.container import get_study_service
                instance = await get_study_service().get_instance(mask_id)
                file_data = await storage_service.download_file(
                    settings.GCS_BUCKET_NAME, instance.gcs_object_name
                )
                _, data = load_nifti_from_bytes(file_data, normalize=False)
                mask = (data > 0).astype(np.uint8)
                if mask.ndim == 3:
                    mask = np.transpose(mask, (2, 0, 1))  # RC-031: native (a0,a1,k) -> internal (k,a0,a1)
                loaded_masks.append(mask)

        agreement = compute_agreement_map(loaded_masks)
        depth, height, width = agreement.shape

        header = struct.pack('<IIII', depth, height, width, len(loaded_masks))
        binary_data = header + agreement.tobytes()

        return Response(
            content=binary_data,
            media_type="application/octet-stream",
            headers={
                "Content-Length": str(len(binary_data)),
                "X-Mask-Count": str(len(loaded_masks)),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error computing agreement map", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Agreement map failed: {str(e)}")


# =============================================================================
# Lesion Analysis Endpoints
# =============================================================================

@router.get("/{segmentation_id}/lesion-analysis")
async def get_lesion_analysis(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Analyze lesions in a segmentation using connected components.

    Returns per-lesion statistics (volume, centroid, bounding box),
    region summary, total burden, and size distribution.
    """
    try:
        # Load segmentation
        seg_data = segmentation_service.get_loaded(segmentation_id)
        if seg_data is None:
            raise HTTPException(status_code=404, detail=f"Segmentation {segmentation_id} not found")
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]

        # Stale check — return cached result if mask hasn't changed
        cached = metadata.analysis_data or {}
        mask_mod = metadata.modified_at.isoformat()
        if cached.get("analysis_mask_modified_at") == mask_mod and "lesion_analysis" in cached:
            logger.info("Returning cached lesion analysis for %s", segmentation_id)
            result = dict(cached["lesion_analysis"])
            result["segmentation_id"] = segmentation_id
            return result

        # Build label map from metadata
        label_map = {}
        for lbl in metadata.labels:
            if hasattr(lbl, 'id') and hasattr(lbl, 'name'):
                label_map[lbl.id] = lbl.name
            elif isinstance(lbl, dict):
                label_map[lbl.get("id", 0)] = lbl.get("name", f"Label {lbl.get('id', 0)}")

        # Use MAGNIMS defaults if no custom labels
        if not label_map or all(lid == 0 for lid in label_map):
            label_map = MAGNIMS_REGIONS

        # RC-024 (CAPA-001 CA-5): voxel spacing is REQUIRED. This previously
        # defaulted to (1.0, 1.0, 1.0) whenever metadata was absent — and to
        # 1.0 slice thickness via `st or 1.0` even when pixel spacing WAS
        # present. Lesion volumes are voxel_count x product(spacing), so a 3 mm
        # study reported volumes understated 3x, with full apparent precision,
        # feeding the MAGNIMS lesion-size thresholds that determine DIS.
        # RC-024 fix: spacing comes from the SOURCE IMAGE, not the segmentation
        # metadata (which never carries it — see _voxel_spacing_from_source_image).
        voxel_spacing = await _voxel_spacing_from_source_image(
            metadata.file_id, storage_service, context=f"segmentation {segmentation_id}"
        )

        result = analyze_lesions(masks_3d, voxel_spacing, label_map)
        result["segmentation_id"] = segmentation_id

        # Persist analysis result in metadata
        metadata.analysis_data = {
            **cached,
            "lesion_analysis": result,
            "analysis_mask_modified_at": mask_mod,
        }
        segmentation_service.persist(segmentation_id)

        logger.info("Lesion analysis completed and cached", extra={
            "segmentation_id": segmentation_id,
            "lesion_count": result["total_count"],
            "total_burden_ml": result["total_burden_ml"],
        })

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error analyzing lesions", extra={
            "segmentation_id": segmentation_id,
            "error": str(e),
        })
        raise HTTPException(status_code=500, detail=f"Lesion analysis failed: {str(e)}")


@router.get("/{segmentation_id}/dis-assessment")
async def get_dis_assessment(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
    # 2024 McDonald external evidence the brain MRI cannot supply. None = not
    # assessed (default; identical to prior behavior and cacheable).
    spinal_cord_involved: Optional[bool] = None,
    optic_nerve_involved: Optional[bool] = None,
    cvs_positive: Optional[bool] = None,
    prl_present: Optional[bool] = None,
    csf_specific: Optional[bool] = None,
):
    """
    Evaluate McDonald 2024 DIS (Dissemination in Space) criteria.

    McDonald 2024 (Montalban et al., 2025): DIS requires ≥2 of 5 regions
    (PV, JC, IT, spinal cord, optic nerve). Brain MRI supplies 3 of 5; the spinal
    cord / optic nerve and the supportive specificity markers (central vein sign,
    paramagnetic rim lesion, CSF-specific finding) are optional external evidence.
    Decision support only — never a diagnosis (CMSC guidance).
    """
    try:
        seg_data = segmentation_service.get_loaded(segmentation_id)
        if seg_data is None:
            raise HTTPException(status_code=404, detail=f"Segmentation {segmentation_id} not found")
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]

        external_evidence = {
            "spinal_cord_involved": spinal_cord_involved,
            "optic_nerve_involved": optic_nerve_involved,
            "cvs_positive": cvs_positive,
            "prl_present": prl_present,
            "csf_specific": csf_specific,
        }
        # Only the brain-only assessment (no external evidence) is cached — a
        # parameterized result must not overwrite or be served from that cache.
        any_external = any(v is not None for v in external_evidence.values())

        # Stale check — return cached result if mask hasn't changed
        cached = metadata.analysis_data or {}
        mask_mod = metadata.modified_at.isoformat()
        if (not any_external
                and cached.get("analysis_mask_modified_at") == mask_mod
                and "dis_assessment" in cached):
            logger.info("Returning cached DIS assessment for %s", segmentation_id)
            result = dict(cached["dis_assessment"])
            result["segmentation_id"] = segmentation_id
            return result

        # Build label map
        label_map = {}
        for lbl in metadata.labels:
            if hasattr(lbl, 'id') and hasattr(lbl, 'name'):
                label_map[lbl.id] = lbl.name
            elif isinstance(lbl, dict):
                label_map[lbl.get("id", 0)] = lbl.get("name", f"Label {lbl.get('id', 0)}")

        if not label_map or all(lid == 0 for lid in label_map):
            label_map = MAGNIMS_REGIONS

        # RC-024 (CAPA-001 CA-5): voxel spacing is REQUIRED. This previously
        # defaulted to (1.0, 1.0, 1.0) whenever metadata was absent — and to
        # 1.0 slice thickness via `st or 1.0` even when pixel spacing WAS
        # present. Lesion volumes are voxel_count x product(spacing), so a 3 mm
        # study reported volumes understated 3x, with full apparent precision,
        # feeding the MAGNIMS lesion-size thresholds that determine DIS.
        # RC-024 fix: spacing from the SOURCE IMAGE, not the segmentation metadata.
        voxel_spacing = await _voxel_spacing_from_source_image(
            metadata.file_id, storage_service, context=f"segmentation {segmentation_id}"
        )

        result = compute_dis_criteria(
            masks_3d, label_map, voxel_spacing, **external_evidence
        )
        result["segmentation_id"] = segmentation_id

        # Only persist the brain-only (unparameterized) assessment to the cache;
        # a result that folds in external evidence must not become the cached one.
        if not any_external:
            metadata.analysis_data = {
                **cached,
                "dis_assessment": result,
                "analysis_mask_modified_at": mask_mod,
            }
            segmentation_service.persist(segmentation_id)

        logger.info("DIS assessment completed", extra={
            "segmentation_id": segmentation_id,
            "dis_met_brain": result.get("dis_met_brain", False),
            "brain_regions_with_lesions": result.get("brain_regions_with_lesions", 0),
            "total_topographies_involved": result.get("total_topographies_involved", 0),
            "dit_waiver_supported": result.get("dit_waiver_supported", False),
            "external_evidence": any_external,
        })

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error computing DIS assessment", extra={
            "segmentation_id": segmentation_id,
            "error": str(e),
        })
        raise HTTPException(status_code=500, detail=f"DIS assessment failed: {str(e)}")


# =============================================================================
# Longitudinal Tracking Endpoints
# =============================================================================

@router.post("/longitudinal/compare")
async def compare_longitudinal(
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Compare lesion masks from two timepoints.

    Request body:
    {
      "tp1": {"type": "segmentation"|"instance", "id": "<id>"},
      "tp2": {"type": "segmentation"|"instance", "id": "<id>"}
    }

    Returns lesion-by-lesion changes (new, resolved, enlarged, shrunk, stable),
    total burden delta, and summary counts.
    """
    try:
        body = await request.json()
        tp1_spec = body.get("tp1")
        tp2_spec = body.get("tp2")

        if not tp1_spec or not tp2_spec:
            raise HTTPException(status_code=400, detail="Both tp1 and tp2 are required")

        async def load_mask(spec):
            mask_type = spec.get("type")
            mask_id = spec.get("id")

            if mask_type == "segmentation":
                _m = segmentation_service.get_mask(mask_id)
                if _m is None:
                    raise HTTPException(status_code=404, detail=f"Segmentation {mask_id} not found")
                return _m

            elif mask_type == "instance":
                # Lazy study-service resolution — see compare_masks (avoids a
                # Firestore/ADC dependency for segmentation-only requests).
                from app.core.container import get_study_service
                instance = await get_study_service().get_instance(mask_id)
                file_data = await storage_service.download_file(
                    settings.GCS_BUCKET_NAME, instance.gcs_object_name
                )
                _, data = load_nifti_from_bytes(file_data, normalize=False)
                mask = (data > 0).astype(np.uint8)
                if mask.ndim == 3:
                    mask = np.transpose(mask, (2, 0, 1))  # RC-031: native (a0,a1,k) -> internal (k,a0,a1)
                return mask
            else:
                raise HTTPException(status_code=400, detail=f"Unknown mask type: {mask_type}")

        mask_tp1 = await load_mask(tp1_spec)
        mask_tp2 = await load_mask(tp2_spec)

        logger.info("Longitudinal masks loaded", extra={
            "tp1_shape": str(mask_tp1.shape),
            "tp2_shape": str(mask_tp2.shape),
            "tp1_nonzero": int(np.count_nonzero(mask_tp1)),
            "tp2_nonzero": int(np.count_nonzero(mask_tp2)),
        })

        # Both masks are loaded in the SAME canonical internal order, so a valid
        # voxel-wise comparison requires identical grids. A size-matching axis
        # permutation (the old behavior) silently mis-aligned square/permuted
        # volumes — audit A-3. Fail loud on any grid mismatch instead.
        _require_comparable_grid(mask_tp1.shape, mask_tp2.shape)

        # Binarize masks (labels > 0 → 1) for comparison
        mask_tp1_bin = (mask_tp1 > 0).astype(np.uint8)
        mask_tp2_bin = (mask_tp2 > 0).astype(np.uint8)

        result = compare_timepoints(mask_tp1_bin, mask_tp2_bin)

        logger.info("Longitudinal comparison completed", extra={
            "new": result["status_counts"]["new"],
            "resolved": result["status_counts"]["resolved"],
            "enlarged": result["status_counts"]["enlarged"],
        })

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Longitudinal comparison failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Longitudinal comparison failed: {str(e)}")


# =============================================================================
# CVS / PRL Lesion Annotations (McDonald 2024 Biomarkers)
# =============================================================================

@router.post("/{segmentation_id}/lesion-annotations")
async def annotate_lesions(
    segmentation_id: str,
    body: dict,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Save CVS/PRL annotations for individual lesions (McDonald 2024 biomarkers).

    McDonald 2024 (Montalban et al., Lancet Neurology 2025) incorporates
    Central Vein Sign (CVS) and Paramagnetic Rim Lesions (PRL) as diagnostic
    biomarkers. CVS Select-6: >=6 CVS+ lesions. PRL: >=1 positive.

    Body: { annotations: [{ lesion_id, cvs_status, prl_status, notes }] }
    """
    try:
        seg_data = segmentation_service.get_loaded(segmentation_id)
        if seg_data is None:
            raise HTTPException(status_code=404, detail=f"Segmentation {segmentation_id} not found")
        metadata = seg_data["metadata"]

        annotations = body.get("annotations", [])
        if not annotations:
            raise HTTPException(status_code=400, detail="No annotations provided")

        from datetime import datetime

        # Merge annotations with existing ones
        existing = (metadata.analysis_data or {}).get("lesion_annotations", [])
        existing_map = {a.get("lesion_id"): a for a in existing if isinstance(a, dict)}

        for ann in annotations:
            lesion_id = ann.get("lesion_id")
            if lesion_id is None:
                continue
            existing_map[lesion_id] = {
                "lesion_id": lesion_id,
                "cvs_status": ann.get("cvs_status"),
                "prl_status": ann.get("prl_status"),
                "annotated_by": ann.get("annotated_by", "manual"),
                "annotated_at": datetime.utcnow().isoformat(),
                "notes": ann.get("notes"),
            }

        merged_annotations = list(existing_map.values())

        # Compute CVS summary (McDonald 2024 Select-6 and 40% rule)
        cvs_evaluated = [a for a in merged_annotations if a.get("cvs_status") in ("positive", "negative")]
        cvs_positive = sum(1 for a in cvs_evaluated if a.get("cvs_status") == "positive")
        total_cvs_evaluated = len(cvs_evaluated)
        cvs_summary = {
            "total_evaluated": total_cvs_evaluated,
            "cvs_positive": cvs_positive,
            "cvs_negative": total_cvs_evaluated - cvs_positive,
            "meets_select6": cvs_positive >= 6,
            "meets_40pct": (cvs_positive / total_cvs_evaluated >= 0.4) if total_cvs_evaluated > 0 else False,
        }

        # Compute PRL summary (McDonald 2024: >=1 PRL)
        prl_evaluated = [a for a in merged_annotations if a.get("prl_status") in ("positive", "negative")]
        prl_positive = sum(1 for a in prl_evaluated if a.get("prl_status") == "positive")
        prl_summary = {
            "total_evaluated": len(prl_evaluated),
            "prl_positive": prl_positive,
            "meets_criteria": prl_positive >= 1,
        }

        # Persist in analysis_data
        metadata.analysis_data = {
            **(metadata.analysis_data or {}),
            "lesion_annotations": merged_annotations,
            "cvs_summary": cvs_summary,
            "prl_summary": prl_summary,
        }
        segmentation_service.persist(segmentation_id)

        logger.info("Lesion annotations saved", extra={
            "segmentation_id": segmentation_id,
            "annotations_count": len(merged_annotations),
            "cvs_positive": cvs_positive,
            "prl_positive": prl_positive,
        })

        return {
            "segmentation_id": segmentation_id,
            "annotations_count": len(merged_annotations),
            "cvs_summary": cvs_summary,
            "prl_summary": prl_summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Lesion annotation failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Lesion annotation failed: {str(e)}")


# =============================================================================
# DICOM-SEG Export
# =============================================================================

@router.get("/{segmentation_id}/export/dicom-seg")
async def export_dicom_seg(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Export a segmentation as a DICOM Segmentation (DICOM-SEG) object.

    Returns a binary DICOM file (.dcm) suitable for PACS archival.
    The file uses SOP Class 1.2.840.10008.5.1.4.1.1.66.4 (Segmentation Storage)
    with BINARY segmentation type and per-label segment entries.
    """
    from app.utils.dicom_utils import create_dicom_seg, save_dicom
    import tempfile

    try:
        # Load mask
        cache_entry = segmentation_service.get_loaded(segmentation_id)
        if cache_entry is None:
            raise HTTPException(status_code=404, detail=f"Segmentation {segmentation_id} not found")
        mask_3d = cache_entry["masks_3d"]
        metadata = cache_entry["metadata"]

        # Extract label info
        labels = []
        if hasattr(metadata, 'labels') and metadata.labels:
            labels = [{"id": l.id, "name": l.name, "color": l.color} for l in metadata.labels]
        else:
            # Fallback: detect unique labels
            unique_labels = np.unique(mask_3d)
            labels = [{"id": int(v), "name": f"Label {v}", "color": "#FF0000"} for v in unique_labels if v > 0]

        if not labels:
            raise HTTPException(status_code=400, detail="Segmentation has no labels")

        # Create DICOM-SEG
        description = getattr(metadata, 'description', '') or 'Segmentation'
        ds = create_dicom_seg(
            mask_3d=mask_3d,
            labels=labels,
            study_description=description,
            series_description=description,
        )

        # Serialize to bytes
        with tempfile.NamedTemporaryFile(suffix='.dcm', delete=False) as tmp:
            tmp_path = tmp.name
        save_dicom(ds, tmp_path)
        with open(tmp_path, 'rb') as f:
            dicom_bytes = f.read()
        import os
        os.unlink(tmp_path)

        logger.info("DICOM-SEG export generated", extra={
            "segmentation_id": segmentation_id,
            "labels_count": len(labels),
            "size_bytes": len(dicom_bytes),
        })

        return Response(
            content=dicom_bytes,
            media_type="application/dicom",
            headers={
                "Content-Disposition": f'attachment; filename="{segmentation_id}_seg.dcm"',
                "Content-Length": str(len(dicom_bytes)),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("DICOM-SEG export failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"DICOM-SEG export failed: {str(e)}")
