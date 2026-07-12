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
import numpy as np

import struct

from app.security import get_current_active_user
from app.security.models import User
from app.core.logging import get_logger
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
        for spec in mask_specs:
            mask_type = spec.get("type")
            mask_id = spec.get("id")
            label = spec.get("label", mask_id)

            if mask_type == "segmentation":
                # Load from segmentation cache
                mask_3d = segmentation_service.get_mask(mask_id)
                if mask_3d is None:
                    raise HTTPException(status_code=404, detail=f"Segmentation {mask_id} not found")
                loaded_masks.append({"mask": (mask_3d > 0).astype(np.uint8), "label": label})

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
                _, data = load_nifti_from_bytes(file_data, normalize=False)
                mask = (data > 0).astype(np.uint8)
                if mask.ndim == 3:
                    mask = np.transpose(mask, (2, 1, 0))  # NIfTI (W,H,D) -> (D,H,W)
                loaded_masks.append({"mask": mask, "label": label})
            else:
                raise HTTPException(status_code=400, detail=f"Unknown mask type: {mask_type}")

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
                    mask = np.transpose(mask, (2, 1, 0))
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

        # Get voxel spacing from metadata if available
        voxel_spacing = (1.0, 1.0, 1.0)
        if hasattr(metadata, 'extra_fields') and metadata.extra_fields:
            ps = metadata.extra_fields.get('pixel_spacing')
            st = metadata.extra_fields.get('slice_thickness')
            if ps and len(ps) >= 2:
                voxel_spacing = (float(st or 1.0), float(ps[0]), float(ps[1]))

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
    current_user: User = Depends(get_current_active_user),
):
    """
    Evaluate McDonald 2024 DIS (Dissemination in Space) criteria.

    McDonald 2024 (Montalban et al., 2025): DIS requires ≥2 of 5 regions
    (PV, JC, IT, spinal cord, optic nerve). Brain MRI evaluates 3 of 5.
    """
    try:
        seg_data = segmentation_service.get_loaded(segmentation_id)
        if seg_data is None:
            raise HTTPException(status_code=404, detail=f"Segmentation {segmentation_id} not found")
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]

        # Stale check — return cached result if mask hasn't changed
        cached = metadata.analysis_data or {}
        mask_mod = metadata.modified_at.isoformat()
        if cached.get("analysis_mask_modified_at") == mask_mod and "dis_assessment" in cached:
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

        # Get voxel spacing for minimum volume filter
        voxel_spacing = (1.0, 1.0, 1.0)
        if hasattr(metadata, 'extra_fields') and metadata.extra_fields:
            ps = metadata.extra_fields.get('pixel_spacing')
            st = metadata.extra_fields.get('slice_thickness')
            if ps and len(ps) >= 2:
                voxel_spacing = (float(st or 1.0), float(ps[0]), float(ps[1]))

        result = compute_dis_criteria(masks_3d, label_map, voxel_spacing)
        result["segmentation_id"] = segmentation_id

        # Persist DIS result in metadata
        metadata.analysis_data = {
            **cached,
            "dis_assessment": result,
            "analysis_mask_modified_at": mask_mod,
        }
        segmentation_service.persist(segmentation_id)

        logger.info("DIS assessment completed and cached", extra={
            "segmentation_id": segmentation_id,
            "dis_met_brain": result.get("dis_met_brain", False),
            "brain_regions_with_lesions": result.get("brain_regions_with_lesions", 0),
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
                    mask = np.transpose(mask, (2, 1, 0))
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

        # Normalize orientation: if shapes differ but sorted dims match, transpose TP2 to match TP1
        if mask_tp1.shape != mask_tp2.shape:
            sorted1 = sorted(mask_tp1.shape)
            sorted2 = sorted(mask_tp2.shape)
            if sorted1 == sorted2:
                # Find the permutation that maps TP2 shape to TP1 shape
                target = mask_tp1.shape
                source = mask_tp2.shape
                perm = []
                used = [False] * len(source)
                for t in target:
                    for i, s in enumerate(source):
                        if s == t and not used[i]:
                            perm.append(i)
                            used[i] = True
                            break
                mask_tp2 = np.transpose(mask_tp2, perm)
                logger.info("Transposed TP2 mask to match TP1", extra={
                    "original_shape": str(source),
                    "new_shape": str(mask_tp2.shape),
                    "permutation": str(perm),
                })
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Mask dimensions incompatible: TP1={mask_tp1.shape} vs TP2={mask_tp2.shape}"
                )

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
