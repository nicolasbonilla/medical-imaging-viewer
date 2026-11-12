"""
API Routes for Validated Clinical Tools (LST-AI, SynthSeg).

Provides endpoints to invoke, monitor, and retrieve results from
validated neuroimaging analysis tools running as Docker sidecars.

All tool outputs include validation_source metadata documenting
the tool version, academic citation, and regulatory status.

@module api.routes.clinical_tools
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, StrictBool
from typing import List, Dict, Any, Literal

from app.security import get_current_active_user
from app.security.models import User
from app.security.patient_access_dependency import require_imaging_access
from app.security.resource_access import authorize_patient_id, authorize_study_id
from app.security.ownership import initiators
from app.core.logging import get_logger
from app.core.container import get_storage_service, get_tool_runner_service
from app.core.interfaces.ai_interface import (
    LSTAISegmentRequest,
    SynthSegRequest,
    FLAMeSSegmentRequest,
    ToolTask,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/clinical", tags=["Clinical Tools"])


async def _authorized_inputs(file_ids, patient_id, study_id, user: User):
    """CAPA-009 (RC-036): every input image must belong to a patient the caller may access,
    and to ONE patient; a given patient_id / study_id must be that same patient. Returns the
    parsed, patient-authorized storage paths (RC-027) to use instead of the raw client ids."""
    from app.security.storage_access import extract_patient_id_from_path

    paths, owners = [], set()
    for fid in file_ids:
        ref = await require_imaging_access(fid, user)
        paths.append(ref.object_path)
        owners.add(extract_patient_id_from_path(ref.object_path))
    if len(owners) != 1:
        raise HTTPException(status_code=400, detail="All input images must belong to one patient")
    owner = owners.pop()
    if patient_id:
        await authorize_patient_id(patient_id, user)
        if str(patient_id) != str(owner):
            raise HTTPException(status_code=400, detail="patient_id does not match the input images")
    if study_id:
        if str(await authorize_study_id(study_id, user)) != str(owner):
            raise HTTPException(status_code=400, detail="study_id does not belong to the images' patient")
    return paths


class SkullStripRequest(BaseModel):
    file_id: str = Field(..., min_length=1, max_length=500)


@router.post("/skull-strip")
async def skull_strip(
    request: SkullStripRequest,
    tool_runner=Depends(get_tool_runner_service),
    current_user: User = Depends(get_current_active_user),
):
    """The FLAIR without its skull, for the in-browser AI (REQ-FUNC-115, RC-101). Nothing is stored; 503 when the worker is not configured,
    and the browser then reads the file as it is, where the input gates refuse an image that still has its skull."""
    paths = await _authorized_inputs([request.file_id], None, None, current_user)
    if not tool_runner.is_skull_strip_available():
        raise HTTPException(status_code=503, detail="Skull removal is not available")
    try:
        brain, model = await tool_runner.skull_strip(paths[0])
    except Exception as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning("Skull removal failed", extra={"reason": type(exc).__name__, "status_code": code})
        raise HTTPException(status_code=502, detail="The skull could not be removed")
    return Response(content=brain, media_type="application/gzip", headers={
        "Cache-Control": "no-store", "X-Strip-Model": model if re.fullmatch(r"[0-9a-f]{12}", model or "") else "",
        "Access-Control-Expose-Headers": "X-Strip-Model"})


class QualityGateRequest(BaseModel):
    file_id: str = Field(..., min_length=1, max_length=500)
    physician_confirmed_flair: StrictBool = False   # S3: a deliberate attestation, never coerced from "true"/1
    # G17: 'pending' before the run; at the final consultation the outcome the browser reports for the image the
    # AI read, so the decision that releases or withholds the output is decided and audited here.
    skull: Literal["pending", "stripped", "unknown"] = "pending"


@router.post("/quality-gate")
async def quality_gate(
    body: QualityGateRequest,
    request: Request,
    storage_service=Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
):
    """The single quality gate before the in-browser AI (REQ-FUNC-117, REQ-SAFE-052/054; RC-122, RC-126).
    Read only, nothing stored. The inputs are derived here from the stored file (never from the client, never
    from the file name); the decision comes through the agent platform (approval, kill switches: fail closed).
    The response carries the derived inputs (the browser re-checks the decision with the same rule, gate.ts) and
    its subject — the file id it was made for and the file's version (G18: a stale answer never acts).

    Second review of PR #81, finding 1: behind QUALITY_GATE_ENFORCED; the approval and both kill switches are read
    BEFORE any I/O (a refusal reads, authorizes and downloads nothing). Fifth review, F3: a per-user rate limit bounds
    the REAL evaluations (refusals included); a repeated pre-run consultation of the same file version is answered
    from the cache without counting; over the limit, 429 with the seconds to wait (code gate_rate_limited)."""
    from fastapi.responses import JSONResponse
    from app.core.config import get_settings
    from app.services import quality_gate as qg

    if not get_settings().QUALITY_GATE_ENFORCED:
        raise HTTPException(status_code=404, detail="Not Found")
    import asyncio
    actor = qg.actor_for(current_user, request)
    user_id = str(getattr(current_user, "id", ""))

    def _over_limit():
        wait = qg.rate_limit_evaluation(user_id)
        if wait is None:
            return None
        return JSONResponse(status_code=429, headers={"Retry-After": str(wait)}, content={"error": {
            "code": "HTTP_429", "message": "Too many quality-gate checks; try again shortly",
            "details": {"code": "gate_rate_limited", "retry_after_s": wait}}})

    if not qg.platform_allows():
        limited = _over_limit()                    # a refusal is a real, audited evaluation: counted too
        if limited is not None:
            return limited
        refused = await asyncio.to_thread(qg.run_quality_gate, {"mode": "single", "visits": []}, actor=actor)
        return {**refused, "subject": {"file_id": body.file_id, "version": None}}
    paths = await _authorized_inputs([body.file_id], None, None, current_user)
    bucket = get_settings().GCS_BUCKET_NAME
    version_key = await qg.file_version(storage_service, bucket, paths[0])
    # A3 (sixth review): the stored records the decision is made from are read first, and their digest is part of
    # the cache key; A2: so is the clinician when the physician attests
    records = await asyncio.to_thread(qg.stored_records, paths[0])
    key = qg.consultation_key(version_key, body.physician_confirmed_flair, body.skull, records=records, user_id=user_id)
    cached = qg.cached_consultation(key)
    if cached is not None:                         # F3: the same answer again, not counted, not re-audited
        answer, version = cached
        return {**answer, "subject": {"file_id": body.file_id, "version": version}}
    limited = _over_limit()
    if limited is not None:
        return limited
    inputs, version = await qg.single_study_inputs(paths[0], storage_service, bucket=bucket,
                                                   physician_confirmed_flair=body.physician_confirmed_flair,
                                                   skull=body.skull, version_key=version_key, records=records)
    result = await asyncio.to_thread(qg.run_quality_gate, inputs, study_key=qg.study_of(paths[0]) or paths[0], actor=actor)
    answer = {**result, "inputs": inputs}
    qg.store_consultation(key, answer, version)
    return {**answer, "subject": {"file_id": body.file_id, "version": version}}


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
    t1_path, flair_path = await _authorized_inputs(
        [request.t1_file_id, request.flair_file_id], request.patient_id, request.study_id, current_user)
    task_id = await tool_runner.run_lstai(
        t1_file_id=t1_path,
        flair_file_id=flair_path,
        patient_id=request.patient_id,
        study_id=request.study_id,
    )
    initiators.record("clinical-task", task_id, current_user)   # CAPA-009

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
        Dereskewicz E, et al. FLAMeS: a robust deep learning model for automated
        multiple sclerosis lesion segmentation. J Neuroimaging 2025;35(5)
        (doi:10.1111/jon.70085; medRxiv 2025.05.19.25327707). Weights CC-BY-4.0,
        Zenodo 17955359. (CAPA-009: first author corrected; was "Ballerini A".)
    """
    (flair_path,) = await _authorized_inputs(
        [request.flair_file_id], request.patient_id, request.study_id, current_user)
    task_id = await tool_runner.run_flames(
        flair_file_id=flair_path,
        patient_id=request.patient_id,
        study_id=request.study_id,
    )
    initiators.record("clinical-task", task_id, current_user)   # CAPA-009

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
    (image_path,) = await _authorized_inputs(
        [request.file_id], request.patient_id, request.study_id, current_user)
    task_id = await tool_runner.run_synthseg(
        file_id=image_path,
        patient_id=request.patient_id,
        study_id=request.study_id,
    )
    initiators.record("clinical-task", task_id, current_user)   # CAPA-009

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
    initiators.authorize("clinical-task", task_id, current_user, "Task")   # CAPA-009
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
    initiators.authorize("clinical-task", task_id, current_user, "Task")   # CAPA-009
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
