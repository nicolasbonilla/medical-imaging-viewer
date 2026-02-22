"""
AI Segmentation API routes for brain MRI.

Provides endpoints for:
- Interactive AI segmentation (click-based)
- Automatic brain structure segmentation
- Brain anomaly detection
- AI task status polling
- Available models listing

@module api.routes.ai_segmentation
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.core.interfaces.ai_interface import (
    InteractiveSegmentRequest,
    AutoSegmentRequest,
    AnomalyDetectionRequest,
    AITaskResult,
    AnomalyDetectionResult,
    VolumetryResult,
    VolumetryComparisonResult,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Segmentation"])


def get_ai_service():
    """Dependency to get AI segmentation service from DI container."""
    from app.core.container import get_container
    container = get_container()
    return container.ai_segmentation_service()


# =============================================================================
# Interactive Segmentation
# =============================================================================

@router.post(
    "/segment/interactive",
    response_model=AITaskResult,
    summary="Interactive brain segmentation",
    description="Run interactive 3D brain segmentation from user click points. "
                "The user clicks on a 2D slice and the AI generates a full 3D mask.",
)
async def segment_interactive(
    request: InteractiveSegmentRequest,
    ai_service=Depends(get_ai_service),
):
    """Interactive segmentation: click points → 3D mask."""
    logger.info(
        f"[AI] Interactive segmentation requested: "
        f"file_id={request.file_id}, model={request.model}, "
        f"clicks={len(request.click_points)}"
    )
    result = await ai_service.segment_interactive(request)
    return result


# =============================================================================
# Automatic Brain Structure Segmentation
# =============================================================================

@router.post(
    "/segment/auto",
    response_model=AITaskResult,
    summary="Automatic brain structure segmentation",
    description="Automatically segment 30+ brain structures (hippocampus, "
                "ventricles, cortex, thalamus, etc.) using SynthSeg.",
)
async def segment_auto(
    request: AutoSegmentRequest,
    ai_service=Depends(get_ai_service),
):
    """Auto segmentation: file_id → full brain labelmap."""
    logger.info(
        f"[AI] Auto segmentation requested: "
        f"file_id={request.file_id}, model={request.model}"
    )
    result = await ai_service.segment_auto(request)
    return result


# =============================================================================
# Brain Anomaly Detection
# =============================================================================

@router.post(
    "/anomaly/detect",
    response_model=AnomalyDetectionResult,
    summary="Detect brain anomalies",
    description="Detect brain anomalies including tumors, lesions, hemorrhages, "
                "infarcts, and atrophy patterns. Returns a probability heatmap "
                "and a list of detected anomalies.",
)
async def detect_anomalies(
    request: AnomalyDetectionRequest,
    ai_service=Depends(get_ai_service),
):
    """Anomaly detection: file_id → heatmap + anomaly list."""
    logger.info(
        f"[AI] Anomaly detection requested: "
        f"file_id={request.file_id}, sensitivity={request.sensitivity}"
    )
    result = await ai_service.detect_anomalies(request)
    return result


# =============================================================================
# Task Status Polling
# =============================================================================

@router.get(
    "/segment/{task_id}/status",
    response_model=AITaskResult,
    summary="Get AI task status",
    description="Poll the status of an async AI segmentation task. "
                "Use this to check progress and get the result when completed.",
)
async def get_task_status(
    task_id: str,
    ai_service=Depends(get_ai_service),
):
    """Poll async AI task: task_id → status + result."""
    result = await ai_service.get_task_status(task_id)
    return result


# =============================================================================
# Available Models
# =============================================================================

@router.get(
    "/models",
    response_model=List[Dict[str, Any]],
    summary="List available AI models",
    description="List all available AI models for brain segmentation and their "
                "configuration status. Models that are not configured will return "
                "graceful errors when invoked.",
)
async def list_models(
    ai_service=Depends(get_ai_service),
):
    """List available AI models and configuration status."""
    models = await ai_service.list_available_models()
    return models


# =============================================================================
# Brain Structure Labels Reference
# =============================================================================

@router.get(
    "/labels/synthseg",
    summary="Get SynthSeg brain structure labels",
    description="Returns the mapping of SynthSeg label IDs to brain structure "
                "names and colors (FreeSurfer convention).",
)
async def get_synthseg_labels():
    """Get brain structure label reference."""
    from app.services.ai_segmentation_service import SYNTHSEG_LABELS
    labels = [
        {
            "id": label_id,
            "name": name,
            "color": color,
        }
        for label_id, (name, color) in SYNTHSEG_LABELS.items()
    ]
    return {"labels": labels, "count": len(labels)}


# =============================================================================
# Brain Volumetry
# =============================================================================

class VolumetryRequest(BaseModel):
    """Request for brain volumetry computation."""
    segmentation_id: str = Field(..., description="ID of the segmentation to measure")
    voxel_spacing: List[float] = Field(
        default=[1.0, 1.0, 1.0],
        min_length=3,
        max_length=3,
        description="Voxel spacing in mm [z, y, x]",
    )
    patient_age: Optional[int] = Field(None, ge=0, le=150)
    patient_sex: Optional[str] = Field(None, pattern="^(M|F)$")


class VolumetryCompareRequest(BaseModel):
    """Request for longitudinal volumetry comparison."""
    patient_id: str
    timepoints: List[Dict[str, Any]] = Field(
        ...,
        min_length=2,
        description="List of timepoint dicts with study_id, date, structures",
    )


def get_volumetry_service():
    """Lazy-load brain volumetry service (CPU-only, no heavy deps)."""
    from app.services.brain_volumetry_service import BrainVolumetryService
    return BrainVolumetryService()


@router.post(
    "/volumetry/compute",
    response_model=VolumetryResult,
    summary="Compute brain volumetry",
    description="Compute per-structure volumes from a brain segmentation mask. "
                "Compares against normative data when patient age is provided. "
                "Runs on CPU — no GPU required.",
)
async def compute_volumetry(
    request: VolumetryRequest,
    volumetry_service=Depends(get_volumetry_service),
):
    """Volumetry: segmentation_id → per-structure volumes in mm3 and mL."""
    logger.info(
        f"[AI] Volumetry requested: "
        f"segmentation_id={request.segmentation_id}, "
        f"age={request.patient_age}, sex={request.patient_sex}"
    )

    # Load the segmentation mask from storage via SegmentationService
    try:
        from app.core.container import get_container
        import numpy as np

        container = get_container()
        seg_service = container.segmentation_service()
        seg_id = request.segmentation_id

        # Load segmentation into cache if not already there
        if seg_id not in seg_service.segmentations_cache:
            loaded = seg_service._load_segmentation(seg_id)
            if not loaded:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Segmentation {seg_id} not found. "
                           f"Make sure the segmentation is saved before computing volumetry.",
                )

        seg_data = seg_service.segmentations_cache[seg_id]
        mask = seg_data["masks_3d"]  # numpy array (D, H, W), dtype=uint8

        if mask is None or mask.size == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segmentation {seg_id} has no mask data",
            )

        voxel_spacing = tuple(request.voxel_spacing)

        result = volumetry_service.compute_volumes(
            mask=mask,
            voxel_spacing=voxel_spacing,
            segmentation_id=seg_id,
            patient_age=request.patient_age,
            patient_sex=request.patient_sex,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AI] Volumetry computation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Volumetry computation failed: {str(e)}",
        )


@router.post(
    "/volumetry/compare",
    response_model=VolumetryComparisonResult,
    summary="Compare brain volumes longitudinally",
    description="Compare brain structure volumes across multiple timepoints "
                "for longitudinal tracking (atrophy progression, treatment response).",
)
async def compare_volumetry(
    request: VolumetryCompareRequest,
    volumetry_service=Depends(get_volumetry_service),
):
    """Longitudinal comparison: timepoints → change percentages + trends."""
    logger.info(
        f"[AI] Volumetry comparison requested: "
        f"patient_id={request.patient_id}, timepoints={len(request.timepoints)}"
    )

    result = volumetry_service.compare_timepoints(
        patient_id=request.patient_id,
        timepoints=request.timepoints,
    )
    return result
