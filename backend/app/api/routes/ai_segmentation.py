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
from typing import List, Dict, Any

from app.core.logging import get_logger
from app.core.interfaces.ai_interface import (
    InteractiveSegmentRequest,
    AutoSegmentRequest,
    AnomalyDetectionRequest,
    AITaskResult,
    AnomalyDetectionResult,
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
