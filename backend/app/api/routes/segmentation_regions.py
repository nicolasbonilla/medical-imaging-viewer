"""API routes for MAGNIMS region classification and zone-map generation.

Split out of segmentation.py (C3 decomposition): these two endpoints carried
the heaviest inline algorithms. Behaviour is unchanged — same paths, same
router prefix (/segmentation), same handlers. Mounted alongside the CRUD
router in main.py.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime
import numpy as np

from app.security import get_current_active_user
from app.security.models import User
from app.core.logging import get_logger
from app.core.interfaces.storage_interface import IStorageService
from app.core.container import get_segmentation_service, get_storage_service
from app.services.segmentation_service import SegmentationService
from app.services.lesion_analysis_service import (
    analyze_lesions,
    compute_dis_criteria,
    MAGNIMS_REGIONS,
)
from app.services.ms_region_classifier import (
    classify_lesions_with_parcellation,
    classify_lesions_with_atlas,
    classify_lesions_geometric,
    generate_zone_map,
    generate_zone_map_atlas,
)
from app.core.config import get_settings
from app.utils import load_nifti_from_bytes

settings = get_settings()

router = APIRouter(prefix="/segmentation", tags=["segmentation"])
logger = get_logger(__name__)


# =============================================================================
# Region Classification Endpoint (SynthSeg + EDT / Geometric)
# =============================================================================

@router.post("/{segmentation_id}/classify-regions")
async def classify_regions(
    segmentation_id: str,
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Auto-classify lesions into MAGNIMS regions (PV, JC, IT, DWM).

    Uses brain parcellation (SynthSeg/FreeSurfer labels) + Euclidean Distance
    Transform for high-accuracy classification (~90%+ agreement with expert
    neuroradiologists). Falls back to geometric heuristics when no parcellation
    is available.

    Request body:
    {
      "parcellation_id": "<optional segmentation_id with FreeSurfer labels>",
      "method": "auto" | "parcellation" | "msmask" | "geometric" | "lst-ai"
    }

    - method "auto" (default): tries lst-ai → parcellation → msmask → geometric
    - method "lst-ai": uses pre-computed LST-AI MAGNIMS zones (requires LST-AI segmentation)
    - method "parcellation": requires parcellation_id
    - method "msmask": uses MSMask atlas (LST-AI validated, requires nilearn)
    - method "geometric": uses spatial heuristics only

    The segmentation mask is reclassified IN-PLACE (label values changed from
    binary 1 to MAGNIMS labels 1-4) and saved. The frontend should re-download
    the binary mask after this call.
    """
    try:
        body = await request.json()
        parcellation_id = body.get("parcellation_id")
        method = body.get("method", "auto")

        # Load the lesion segmentation
        if segmentation_id not in segmentation_service.segmentations_cache:
            if not segmentation_service._load_segmentation(segmentation_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Segmentation {segmentation_id} not found",
                )

        seg_data = segmentation_service.segmentations_cache[segmentation_id]
        lesion_mask = seg_data["masks_3d"]  # (D, H, W), uint8
        metadata = seg_data["metadata"]

        # Get voxel spacing
        voxel_spacing = (1.0, 1.0, 1.0)
        if hasattr(metadata, 'extra_fields') and metadata.extra_fields:
            ps = metadata.extra_fields.get('pixel_spacing')
            st = metadata.extra_fields.get('slice_thickness')
            if ps and len(ps) >= 2:
                voxel_spacing = (float(st or 1.0), float(ps[0]), float(ps[1]))

        result = None

        # --- Try LST-AI pre-computed MAGNIMS zones ---
        if method in ("auto", "lst-ai"):
            # Look for an existing LST-AI segmentation for the same file
            file_id = metadata.file_id
            all_segs = segmentation_service.list_segmentations(file_id=file_id)
            for candidate in all_segs:
                if candidate.segmentation_id == segmentation_id:
                    continue
                try:
                    cand_id = candidate.segmentation_id
                    if cand_id not in segmentation_service.segmentations_cache:
                        segmentation_service._load_segmentation(cand_id)
                    if cand_id in segmentation_service.segmentations_cache:
                        cand_meta = segmentation_service.segmentations_cache[cand_id].get("metadata", {})
                        vs = getattr(cand_meta, "validation_source", None) or (
                            cand_meta.get("validation_source") if isinstance(cand_meta, dict) else None
                        )
                        if vs and "lst-ai" in str(vs):
                            # Found LST-AI types mask — use it directly
                            cand_mask = segmentation_service.segmentations_cache[cand_id]["masks_3d"]
                            # Apply LST-AI zones to our lesion mask locations
                            import time as _time
                            _start = _time.time()
                            classified = np.zeros_like(lesion_mask)
                            for zone_val in [1, 2, 3, 4]:
                                classified[(lesion_mask > 0) & (cand_mask == zone_val)] = zone_val
                            # Any lesion not covered by zones → DWM (4) fallback
                            classified[(lesion_mask > 0) & (classified == 0)] = 4
                            _elapsed = int((_time.time() - _start) * 1000)

                            total = int(np.sum(classified > 0))
                            result = {
                                "classified_mask": classified,
                                "method": "lst-ai",
                                "validation_source": str(vs),
                                "total_classified": total,
                                "per_region": {
                                    "periventricular": int(np.sum(classified == 1)),
                                    "juxtacortical": int(np.sum(classified == 2)),
                                    "infratentorial": int(np.sum(classified == 3)),
                                    "deep_white_matter": int(np.sum(classified == 4)),
                                },
                                "processing_time_ms": _elapsed,
                            }
                            logger.info(
                                "[ClassifyRegions] LST-AI classification applied",
                                extra={"segmentation_id": segmentation_id, "source": cand_id},
                            )
                            break
                except Exception as e:
                    logger.warning(f"[ClassifyRegions] LST-AI candidate check failed: {e}")
                    continue

            if result is None and method == "lst-ai":
                raise HTTPException(
                    status_code=400,
                    detail="LST-AI method requested but no LST-AI segmentation found. "
                           "Run LST-AI segmentation first via /clinical/lst-ai/segment.",
                )

        # --- Try parcellation-based classification ---
        if result is None and method in ("auto", "parcellation") and parcellation_id:
            try:
                # Load parcellation mask
                if parcellation_id not in segmentation_service.segmentations_cache:
                    if not segmentation_service._load_segmentation(parcellation_id):
                        if method == "parcellation":
                            raise HTTPException(
                                status_code=404,
                                detail=f"Parcellation {parcellation_id} not found",
                            )
                        logger.warning(
                            "[ClassifyRegions] Parcellation %s not found, falling back to geometric",
                            parcellation_id,
                        )

                if parcellation_id in segmentation_service.segmentations_cache:
                    parc_data = segmentation_service.segmentations_cache[parcellation_id]
                    parcellation_mask = parc_data["masks_3d"]

                    result = classify_lesions_with_parcellation(
                        lesion_mask, parcellation_mask, voxel_spacing
                    )
                    logger.info(
                        "[ClassifyRegions] Parcellation-based classification succeeded",
                        extra={"segmentation_id": segmentation_id},
                    )
            except HTTPException:
                raise
            except Exception as e:
                if method == "parcellation":
                    raise
                logger.warning(
                    "[ClassifyRegions] Parcellation classification failed: %s. Falling back.",
                    str(e),
                )

        # --- Try parcellation from instance (expert mask as NIfTI) ---
        if result is None and method in ("auto", "parcellation") and not parcellation_id:
            # Check if there is another segmentation for the same file that
            # looks like a parcellation (has FreeSurfer-range labels)
            file_id = metadata.file_id
            all_segs = segmentation_service.list_segmentations(file_id=file_id)
            for candidate in all_segs:
                if candidate.segmentation_id == segmentation_id:
                    continue
                # Load candidate and check for FreeSurfer labels
                try:
                    cand_id = candidate.segmentation_id
                    if cand_id not in segmentation_service.segmentations_cache:
                        segmentation_service._load_segmentation(cand_id)
                    if cand_id in segmentation_service.segmentations_cache:
                        cand_mask = segmentation_service.segmentations_cache[cand_id]["masks_3d"]
                        unique_vals = set(int(v) for v in np.unique(cand_mask) if v > 0)
                        # FreeSurfer labels include values like 2,3,4,7,8,10...
                        freesurfer_check = unique_vals & {2, 3, 4, 7, 8, 10, 16, 41, 42, 43}
                        if len(freesurfer_check) >= 3:
                            logger.info(
                                "[ClassifyRegions] Found parcellation candidate: %s",
                                cand_id,
                            )
                            result = classify_lesions_with_parcellation(
                                lesion_mask, cand_mask, voxel_spacing
                            )
                            break
                except Exception:
                    continue

        # --- MSMask atlas-based classification ---
        if result is None and method in ("auto", "msmask"):
            try:
                from app.services.ms_region_classifier import classify_from_zone_mask

                file_id = metadata.file_id

                # Try reusing a persisted zone map first
                zone_map_seg_id = (metadata.analysis_data or {}).get("zone_map_seg_id")
                if zone_map_seg_id:
                    if zone_map_seg_id not in segmentation_service.segmentations_cache:
                        segmentation_service._load_segmentation(zone_map_seg_id)
                    if zone_map_seg_id in segmentation_service.segmentations_cache:
                        zone_mask = segmentation_service.segmentations_cache[zone_map_seg_id]["masks_3d"]
                        result = classify_from_zone_mask(lesion_mask, zone_mask, voxel_spacing)
                        result["method"] = "msmask"
                        logger.info(
                            "[ClassifyRegions] Reused persisted zone map %s",
                            zone_map_seg_id,
                            extra={"segmentation_id": segmentation_id},
                        )

                # If no cached zone map, generate fresh via atlas
                if result is None:
                    nifti_data = await storage_service.download_file(
                        settings.GCS_BUCKET_NAME, file_id
                    )
                    nifti_img, _ = load_nifti_from_bytes(nifti_data, normalize=False)

                    result = classify_lesions_with_atlas(
                        lesion_mask, nifti_img, voxel_spacing
                    )
                    logger.info(
                        "[ClassifyRegions] MSMask atlas classification applied (fresh)",
                        extra={"segmentation_id": segmentation_id},
                    )
            except FileNotFoundError as e:
                if method == "msmask":
                    raise HTTPException(status_code=400, detail=str(e))
                logger.warning(
                    "[ClassifyRegions] MSMask atlas not available: %s. Falling back.",
                    str(e),
                )
            except ImportError as e:
                if method == "msmask":
                    raise HTTPException(
                        status_code=400,
                        detail=f"MSMask requires nilearn: {e}",
                    )
                logger.warning(
                    "[ClassifyRegions] nilearn not installed: %s. Falling back to geometric.",
                    str(e),
                )
            except Exception as e:
                if method == "msmask":
                    raise HTTPException(status_code=500, detail=str(e))
                logger.warning(
                    "[ClassifyRegions] MSMask classification failed: %s. Falling back.",
                    str(e),
                )

        # --- Geometric fallback (no parcellation or atlas available) ---
        if result is None and method in ("auto", "geometric"):
            try:
                # Load the original image data for intensity-based heuristics
                image_data = None
                file_id = metadata.file_id
                try:
                    nifti_data = await storage_service.download_file(
                        settings.GCS_BUCKET_NAME, file_id
                    )
                    _, image_data = load_nifti_from_bytes(nifti_data, normalize=False)
                except Exception as img_err:
                    logger.warning(
                        "[ClassifyRegions] Could not load image data for geometric: %s",
                        str(img_err),
                    )

                result = classify_lesions_geometric(
                    lesion_mask, image_data, voxel_spacing
                )
                logger.info(
                    "[ClassifyRegions] Geometric classification applied (fallback)",
                    extra={"segmentation_id": segmentation_id},
                )
            except Exception as e:
                logger.warning(
                    "[ClassifyRegions] Geometric classification failed: %s",
                    str(e),
                )

        # --- No method available ---
        if result is None:
            raise HTTPException(
                status_code=400,
                detail="No classification method available. "
                       "Ensure the segmentation has lesion voxels to classify.",
            )

        # --- Update the segmentation mask in place ---
        classified_mask = result.get("classified_mask")
        if classified_mask is not None:
            seg_data["masks_3d"] = classified_mask

            # Update labels to MAGNIMS
            from app.models.schemas import LabelInfo as SchemaLabelInfo
            magnims_labels = [
                SchemaLabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
                SchemaLabelInfo(id=1, name="Periventricular", color="#FF0000", opacity=0.6, visible=True),
                SchemaLabelInfo(id=2, name="Juxtacortical", color="#00CC00", opacity=0.6, visible=True),
                SchemaLabelInfo(id=3, name="Infratentorial", color="#0066FF", opacity=0.6, visible=True),
                SchemaLabelInfo(id=4, name="Deep White Matter", color="#FFD700", opacity=0.6, visible=True),
                SchemaLabelInfo(id=5, name="Active (Gd+)", color="#FF00FF", opacity=0.6, visible=True),
                SchemaLabelInfo(id=6, name="Black Hole (T1)", color="#9932CC", opacity=0.5, visible=True),
            ]
            metadata.labels = magnims_labels
            metadata.modified_at = datetime.utcnow()

            # Save classified mask to GCS
            segmentation_service._save_segmentation(segmentation_id)

        # Remove numpy array from response (not JSON serializable)
        response_data = {k: v for k, v in result.items() if k != "classified_mask"}
        response_data["segmentation_id"] = segmentation_id
        response_data["mask_updated"] = classified_mask is not None
        response_data["labels_updated"] = classified_mask is not None

        # Sanitize: replace inf/nan with finite values (EDT can produce inf)
        import math

        def _sanitize(obj):
            if isinstance(obj, float):
                if math.isinf(obj) or math.isnan(obj):
                    return 0.0
                return obj
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            # Convert numpy scalars to Python types
            if hasattr(obj, 'item'):
                return _sanitize(obj.item())
            return obj

        response_data = _sanitize(response_data)

        # --- Auto-compute and persist ALL analysis data ---
        if classified_mask is not None:
            try:
                label_map = {}
                for lbl in metadata.labels:
                    if hasattr(lbl, 'id') and hasattr(lbl, 'name'):
                        label_map[lbl.id] = lbl.name
                if not label_map or all(lid == 0 for lid in label_map):
                    label_map = MAGNIMS_REGIONS

                analysis_result = analyze_lesions(classified_mask, voxel_spacing, label_map)
                analysis_result["segmentation_id"] = segmentation_id
                dis_result = compute_dis_criteria(classified_mask, label_map, voxel_spacing)
                dis_result["segmentation_id"] = segmentation_id

                mask_mod = metadata.modified_at.isoformat()
                metadata.analysis_data = {
                    **(metadata.analysis_data or {}),
                    "classification": response_data,
                    "lesion_analysis": _sanitize(analysis_result),
                    "dis_assessment": _sanitize(dis_result),
                    "analysis_mask_modified_at": mask_mod,
                }
                segmentation_service._save_segmentation(segmentation_id)

                logger.info(
                    "[ClassifyRegions] Analysis data persisted (classification + lesion analysis + DIS)",
                    extra={"segmentation_id": segmentation_id},
                )
            except Exception as e:
                logger.warning(
                    "[ClassifyRegions] Failed to persist analysis data: %s", str(e)
                )

        logger.info(
            "[ClassifyRegions] Region classification completed",
            extra={
                "segmentation_id": segmentation_id,
                "method": result["method"],
                "total_classified": result["total_classified"],
                "processing_time_ms": result["processing_time_ms"],
            },
        )

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[ClassifyRegions] Classification failed",
            extra={"segmentation_id": segmentation_id, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Region classification failed: {str(e)}",
        )


# =============================================================================
# MAGNIMS Zone Map Generation
# =============================================================================


@router.post("/generate-zone-map")
async def generate_zone_map_endpoint(
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Generate a MAGNIMS zone map for a brain MRI.

    Creates a new segmentation where every brain voxel is classified into one of
    the four MAGNIMS regions (Periventricular, Juxtacortical, Infratentorial,
    Deep White Matter).

    Method selection:
    - If a brain parcellation (SynthSeg) exists: uses EDT from anatomical landmarks (~90% accuracy)
    - Fallback: loads MRI image, computes brain mask via Otsu thresholding, uses geometric heuristics (~70%)

    Request body:
    {
      "file_id": "<image file_id>",
      "parcellation_id": "<optional segmentation_id with FreeSurfer labels>"
    }
    """
    try:
        body = await request.json()
        file_id = body.get("file_id")
        parcellation_id = body.get("parcellation_id")

        if not file_id:
            raise HTTPException(
                status_code=400,
                detail="file_id is required",
            )

        # --- Delete existing zone maps for this file (prevent duplicates) ---
        all_existing = segmentation_service.list_segmentations(file_id=file_id)
        for existing in all_existing:
            eid = existing.segmentation_id
            try:
                if eid not in segmentation_service.segmentations_cache:
                    segmentation_service._load_segmentation(eid)
                if eid in segmentation_service.segmentations_cache:
                    emeta = segmentation_service.segmentations_cache[eid].get("metadata")
                    if emeta and getattr(emeta, 'description', '') == "MAGNIMS Zone Map":
                        logger.info("[ZoneMap] Deleting old zone map: %s", eid)
                        segmentation_service.delete_segmentation(eid)
            except Exception:
                pass

        # --- Find parcellation ---
        parcellation_mask = None
        parc_source = None

        # Explicit parcellation_id
        if parcellation_id:
            if parcellation_id not in segmentation_service.segmentations_cache:
                if not segmentation_service._load_segmentation(parcellation_id):
                    raise HTTPException(
                        status_code=404,
                        detail=f"Parcellation {parcellation_id} not found",
                    )
            parc_data = segmentation_service.segmentations_cache[parcellation_id]
            parcellation_mask = parc_data["masks_3d"]
            parc_source = parcellation_id
        else:
            # Auto-detect parcellation for this file
            all_segs = segmentation_service.list_segmentations(file_id=file_id)
            for candidate in all_segs:
                cand_id = candidate.segmentation_id
                try:
                    if cand_id not in segmentation_service.segmentations_cache:
                        segmentation_service._load_segmentation(cand_id)
                    if cand_id in segmentation_service.segmentations_cache:
                        # Skip zone map segmentations (labels 1-4 overlap with FreeSurfer)
                        cand_meta = segmentation_service.segmentations_cache[cand_id].get("metadata")
                        if cand_meta and getattr(cand_meta, 'description', '') == "MAGNIMS Zone Map":
                            continue
                        cand_mask = segmentation_service.segmentations_cache[cand_id]["masks_3d"]
                        unique_vals = set(int(v) for v in np.unique(cand_mask) if v > 0)
                        # FreeSurfer parcellations have hemispheric labels (41-43)
                        # and brainstem (16). Zone maps only have labels 1-4.
                        # Require at least one high label to distinguish.
                        freesurfer_check = unique_vals & {2, 3, 4, 7, 8, 10, 16, 41, 42, 43}
                        has_high_labels = bool(unique_vals & {16, 41, 42, 43})
                        if len(freesurfer_check) >= 3 and has_high_labels:
                            parcellation_mask = cand_mask
                            parc_source = cand_id
                            break
                except Exception:
                    continue

        # Get voxel spacing from metadata if available
        voxel_spacing = (1.0, 1.0, 1.0)
        if parc_source and parc_source in segmentation_service.segmentations_cache:
            meta = segmentation_service.segmentations_cache[parc_source].get("metadata")
            if meta and hasattr(meta, 'extra_fields') and meta.extra_fields:
                ps = meta.extra_fields.get('pixel_spacing')
                st = meta.extra_fields.get('slice_thickness')
                if ps and len(ps) >= 2:
                    voxel_spacing = (float(st or 1.0), float(ps[0]), float(ps[1]))

        # --- Generate zone map ---
        # nifti_native_* hold the zone mask in NIfTI native (i,j,k) order
        # plus the MRI affine/header, so we can save a correctly-oriented NIfTI
        # to GCS after the standard save pipeline (which has a transpose bug).
        nifti_native_data = None
        nifti_native_affine = None
        nifti_native_header = None

        if parcellation_mask is not None:
            # Preferred method: parcellation-based (high accuracy)
            logger.info("[ZoneMap] Using parcellation-based method (source=%s)", parc_source)
            result = generate_zone_map(parcellation_mask, voxel_spacing)
        else:
            # MSMask-based method: LST-AI validated atlas (Wiltgen et al. 2024)
            logger.info("[ZoneMap] No parcellation found, using MSMask method for file=%s", file_id)
            file_data = await storage_service.download_file(settings.GCS_BUCKET_NAME, file_id)
            img, data = load_nifti_from_bytes(file_data, normalize=False)
            # Create in-memory NIfTI (the temp file from load_nifti_from_bytes is
            # already deleted, so img.dataobj is a dead file proxy; we need a new
            # image backed by the in-memory data array for resample_to_img to work)
            import nibabel as nib
            target_img = nib.Nifti1Image(data, img.affine, img.header)
            result = generate_zone_map_atlas(target_img, voxel_spacing)
            # Transpose zone_mask from NIfTI native (i,j,k) to display-compatible
            # internal format (k,i,j) using transpose (2,0,1) for 2D overlay.
            zone_mask_raw = result["zone_mask"]
            if zone_mask_raw.ndim == 3:
                # Preserve the NIfTI-native data for correct GCS save
                nifti_native_data = zone_mask_raw.copy()
                nifti_native_affine = img.affine.copy()
                nifti_native_header = img.header.copy()
                result["zone_mask"] = np.transpose(zone_mask_raw, (2, 0, 1))

        zone_mask = result["zone_mask"]

        if zone_mask is None or int(zone_mask.sum()) == 0:
            raise HTTPException(
                status_code=400,
                detail="Failed to generate zone map: no brain voxels detected.",
            )

        # --- Create segmentation with zone mask ---
        from app.models.schemas import LabelInfo as SchemaLabelInfo

        depth, height, width = zone_mask.shape
        magnims_labels = [
            SchemaLabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
            SchemaLabelInfo(id=1, name="Periventricular", color="#FF0000", opacity=0.6, visible=True),
            SchemaLabelInfo(id=2, name="Juxtacortical", color="#00CC00", opacity=0.6, visible=True),
            SchemaLabelInfo(id=3, name="Infratentorial", color="#0066FF", opacity=0.6, visible=True),
            SchemaLabelInfo(id=4, name="Deep White Matter", color="#FFD700", opacity=0.6, visible=True),
        ]

        # create_segmentation expects: file_id: str, image_shape: (H, W, D) tuple
        seg_response = segmentation_service.create_segmentation(
            file_id=file_id,
            image_shape=(height, width, depth),
            labels=magnims_labels,
            description="MAGNIMS Zone Map",
        )
        new_seg_id = seg_response.segmentation_id

        # Write the zone mask into the cache
        if new_seg_id in segmentation_service.segmentations_cache:
            segmentation_service.segmentations_cache[new_seg_id]["masks_3d"] = zone_mask.astype(np.uint8)

        # Save to GCS (metadata + masks via standard pipeline)
        segmentation_service._save_segmentation(new_seg_id)

        # Overwrite GCS NIfTI with correctly-oriented zone map.
        # The standard _save_masks_to_gcs transposes (2,1,0) assuming internal
        # format (D,H,W)=(k,j,i), but the msmask path produces (k,i,j).
        # This causes X/Y axis swap in the NIfTI. We fix it by saving the
        # original NIfTI-native (i,j,k) data directly.
        if nifti_native_data is not None and nifti_native_affine is not None:
            try:
                import tempfile as _tmpmod
                import os as _os
                import nibabel as nib

                nifti_native_header.set_data_dtype(np.uint8)
                nifti_native_header.set_data_shape(nifti_native_data.shape)
                zone_nifti = nib.Nifti1Image(
                    nifti_native_data.astype(np.uint8),
                    nifti_native_affine,
                    nifti_native_header,
                )
                with _tmpmod.NamedTemporaryFile(suffix='.nii.gz', delete=False) as tmp:
                    nib.save(zone_nifti, tmp.name)
                    tmp_path = tmp.name
                with open(tmp_path, 'rb') as f:
                    nifti_bytes = f.read()
                _os.unlink(tmp_path)

                blob_path = f"segmentations/{new_seg_id}/masks.nii.gz"
                blob = segmentation_service.gcs_bucket.blob(blob_path)
                blob.upload_from_string(nifti_bytes, content_type="application/gzip")
                logger.info(
                    "[ZoneMap] Saved correctly-oriented NIfTI to GCS",
                    extra={"path": blob_path, "shape": list(nifti_native_data.shape)},
                )
            except Exception as e:
                logger.warning("[ZoneMap] Failed to save corrected NIfTI: %s", str(e))

        logger.info(
            "[ZoneMap] Zone map segmentation created",
            extra={
                "segmentation_id": new_seg_id,
                "file_id": file_id,
                "processing_time_ms": result["processing_time_ms"],
            },
        )

        # Propagate zone_map_seg_id to all lesion segmentations for this file
        try:
            all_segs = segmentation_service.list_segmentations(file_id=file_id)
            for seg in all_segs:
                if seg.segmentation_id == new_seg_id:
                    continue
                seg_meta = getattr(seg, 'metadata', None)
                if seg_meta and getattr(seg_meta, 'description', '') == "MAGNIMS Zone Map":
                    continue
                seg_cache = segmentation_service.segmentations_cache.get(seg.segmentation_id)
                if seg_cache:
                    s_meta = seg_cache["metadata"]
                    s_meta.analysis_data = {
                        **(s_meta.analysis_data or {}),
                        "zone_map_seg_id": new_seg_id,
                    }
                    segmentation_service._save_segmentation(seg.segmentation_id)
                    logger.info(
                        "[ZoneMap] Propagated zone_map_seg_id to %s",
                        seg.segmentation_id,
                    )
        except Exception as e:
            logger.warning("[ZoneMap] Failed to propagate zone_map_seg_id: %s", str(e))

        return {
            "segmentation_id": new_seg_id,
            "file_id": file_id,
            "zone_stats": result["zone_stats"],
            "total_brain_voxels": result["total_brain_voxels"],
            "processing_time_ms": result["processing_time_ms"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[ZoneMap] Zone map generation failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Zone map generation failed: {str(e)}",
        )
