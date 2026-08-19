"""
API Routes for Validated Clinical Tools (LST-AI, SynthSeg).

Provides endpoints to invoke, monitor, and retrieve results from
validated neuroimaging analysis tools running as Docker sidecars.

All tool outputs include validation_source metadata documenting
the tool version, academic citation, and regulatory status.

@module api.routes.clinical_tools
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any

from app.security import get_current_active_user
from app.security.models import User
from app.core.logging import get_logger
from app.core.container import get_tool_runner_service
from app.core.interfaces.ai_interface import (
    LSTAISegmentRequest,
    SynthSegRequest,
    FLAMeSSegmentRequest,
    ToolTask,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/clinical", tags=["Clinical Tools"])


@router.get("/tools", response_model=List[Dict[str, Any]])
async def list_clinical_tools(
    tool_runner=Depends(get_tool_runner_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    List available validated clinical tools with status, version, and citation.

    Returns tool availability (depends on sidecar container configuration),
    academic citations, required inputs, and FDA regulatory status.
    """
    tools = tool_runner.list_tools()

    # Optionally check live health
    for tool in tools:
        if tool.get("available"):
            tool["healthy"] = await tool_runner.check_sidecar_health(tool["id"])

    return tools


@router.post("/lst-ai/segment", response_model=ToolTask)
async def run_lstai_segmentation(
    request: LSTAISegmentRequest,
    tool_runner=Depends(get_tool_runner_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Submit LST-AI MS lesion segmentation task.

    Requires both T1-weighted and FLAIR MRI NIfTI files.
    LST-AI uses a 3x 3D U-Net ensemble with test-time augmentation
    to produce a binary lesion mask and MAGNIMS 2021 zone classification.

    Returns a task_id for status polling via GET /clinical/task/{task_id}.

    Reference:
        Wiltgen T, et al. LST-AI: a deep learning ensemble for accurate
        MS lesion segmentation. NeuroImage: Clinical 2024;42:103611.
    """
    task_id = await tool_runner.run_lstai(
        t1_file_id=request.t1_file_id,
        flair_file_id=request.flair_file_id,
        patient_id=request.patient_id,
        study_id=request.study_id,
    )

    task = await tool_runner.get_task_status(task_id)
    return task


@router.post("/flames/segment", response_model=ToolTask)
async def run_flames_segmentation(
    request: FLAMeSSegmentRequest,
    tool_runner=Depends(get_tool_runner_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Submit a FLAMeS MS-lesion segmentation task (single FLAIR, SOTA).

    FLAMeS is the vanguard externally-validated automatic MS-lesion segmenter
    (nnU-Net v2, Dataset004_WML; Dice 0.74 / F1 0.78, outperforming SAMSEG,
    LST-LPA and LST-AI). It needs only a FLAIR volume, so it works even when a
    co-registered T1 is unavailable. Inference runs on a scale-to-zero GPU worker.

    Returns a task_id for status polling via GET /clinical/task/{task_id}. When
    complete, the segmentation is loadable via the standard segmentation endpoints.

    INVESTIGATIONAL / research-use only — the output is a review DRAFT, not an
    autonomous diagnosis.

    Reference:
        Ballerini A, et al. FLAMeS: a robust deep learning model for automated
        multiple sclerosis lesion segmentation. J Neuroimaging 2025
        (medRxiv 2025.05.19.25327707). Weights CC-BY-4.0, Zenodo 17955359.
    """
    task_id = await tool_runner.run_flames(
        flair_file_id=request.flair_file_id,
        patient_id=request.patient_id,
        study_id=request.study_id,
    )

    task = await tool_runner.get_task_status(task_id)
    return task


@router.post("/synthseg/parcellate", response_model=ToolTask)
async def run_synthseg_parcellation(
    request: SynthSegRequest,
    tool_runner=Depends(get_tool_runner_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Submit SynthSeg brain parcellation task.

    SynthSeg is contrast-agnostic — works on T1, T2, FLAIR, or any MRI contrast.
    Produces a parcellation mask with 30+ brain structures using FreeSurfer labels,
    plus per-structure volume measurements.

    Returns a task_id for status polling via GET /clinical/task/{task_id}.

    Reference:
        Billot B, et al. SynthSeg: Segmentation of brain MRI scans of any
        contrast and resolution without retraining.
        Medical Image Analysis 2023;83:102789.
    """
    task_id = await tool_runner.run_synthseg(
        file_id=request.file_id,
        patient_id=request.patient_id,
        study_id=request.study_id,
    )

    task = await tool_runner.get_task_status(task_id)
    return task


@router.get("/task/{task_id}", response_model=ToolTask)
async def get_task_status(
    task_id: str,
    tool_runner=Depends(get_tool_runner_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Poll the status of an async clinical tool task.

    Status progression:
        pending → downloading → processing → storing → completed/failed

    When status is 'completed', the segmentation_id field contains the ID
    of the resulting segmentation (loadable via standard segmentation endpoints).
    """
    task = await tool_runner.get_task_status(task_id)
    return task


@router.get("/task/{task_id}/result")
async def get_task_result(
    task_id: str,
    tool_runner=Depends(get_tool_runner_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get the full result of a completed clinical tool task.

    Includes the segmentation_id, validation metadata (tool version,
    citation, regulatory status), and processing time.

    Raises 404 if task not found, 400 if task not yet completed.
    """
    task = await tool_runner.get_task_status(task_id)

    if task.status.value == "failed" and task.error == "Task not found":
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status.value not in ("completed", "failed"):
        raise HTTPException(
            status_code=400,
            detail=f"Task is still {task.status.value}. Poll GET /clinical/task/{task_id} for updates.",
        )

    return {
        "task": task.model_dump(),
        "validation": {
            "source": task.validation_source,
            "citation": tool_runner._get_citation(task.validation_source)
            if hasattr(tool_runner, "_get_citation")
            else "",
            "fda_status": "research_only",
            "disclaimer": (
                "This analysis was performed by a research-grade tool. "
                "Results are for research and clinical decision support only. "
                "Not FDA-cleared for diagnostic use."
            ),
        },
    }
