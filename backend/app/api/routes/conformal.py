"""CALM-MS conformal second-reader endpoint (REQ-FUNC-CALM-001) — INVESTIGATIONAL.

Dark by default (`CALM_MS_RESEARCH_ENABLED`). Wraps the tested, hazard-free
`conformal_review` core with GCS I/O, authentication, object-level PHI
authorization, and off-event-loop compute. Every failure mode is FAIL-CLOSED to an
explicit HTTP status — the population-level guarantee is never served when it would
be void:

  * feature disabled            -> 404 (indistinguishable; feature is dark)
  * unknown/raw preset          -> 422 (only validated presets accepted)
  * grid/base-model mismatch    -> 409 (exchangeability refused)
  * not a valid probability map -> 422
  * null asset missing/empty    -> 503 (never a void guarantee)
  * unauthorized patient/object -> 404 (via require_imaging_access)

v1 is bring-your-own-probability: the caller supplies `prob_file_id` pointing to a
FLAMeS float NIfTI already in GCS on the calibration grid. A production FLAMeS
soft-inference producer + a validated OOD monitor + summative usability study are
prerequisites for clinical enablement (see SRS/RMF Addendum A).
"""
import struct

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.container import get_storage_service
from app.core.logging import get_logger
from app.security import get_current_active_user
from app.security.models import User
from app.security.patient_access_dependency import require_imaging_access
from app.utils.nifti_utils import load_nifti_from_bytes
from app.services.conformal_review_service import conformal_review
from app.services.conformal_null_asset import (
    PRESETS, DEFAULT_PRESET, ProvenanceMismatch, ConformalAssetError,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/conformal", tags=["conformal"])


class ConformalSelectRequest(BaseModel):
    prob_file_id: str = Field(..., description="GCS object key of a FLAMeS float probability NIfTI on the calibration grid")
    preset: str = Field(default=DEFAULT_PRESET, description="Validated preset: high_sensitivity | balanced | high_precision")


@router.post("/select")
async def conformal_select(
    request: ConformalSelectRequest,
    storage_service=Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
):
    """Second-reader review of a FLAMeS probability map at a validated preset.

    Returns an ADDITIVE, ordinal-tiered lesion review with population-level FDR
    scope. Never a per-lesion probability, never a per-scan realized FDR, never a
    mutated mask.
    """
    settings = get_settings()
    if not settings.CALM_MS_RESEARCH_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    if request.preset not in PRESETS:
        raise HTTPException(status_code=422, detail=f"unknown preset; allowed: {sorted(PRESETS)}")
    try:
        # AUTH + object-level PHI authorization (normalised, patient-authorized ref).
        await require_imaging_access(request.prob_file_id, current_user)
        file_data = await storage_service.download_file(settings.GCS_BUCKET_NAME, request.prob_file_id)
        img, arr = load_nifti_from_bytes(file_data)
        zooms = img.header.get_zooms()[:3]
        spacing = tuple(float(z) for z in zooms)
        # Heavy NumPy work off the event loop.
        review = await run_in_threadpool(conformal_review, arr.astype("float32"), spacing, request.preset)
        return review.summary()
    except ProvenanceMismatch as e:
        raise HTTPException(status_code=409, detail=f"exchangeability refused: {e}")
    except ConformalAssetError as e:
        raise HTTPException(status_code=503, detail=f"conformal null asset unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.error("[Conformal] select failed", exc_info=True)
        raise HTTPException(status_code=500, detail="conformal selection failed")


@router.post("/status-mask")
async def conformal_status_mask(
    request: ConformalSelectRequest,
    storage_service=Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
):
    """The ADDITIVE tier overlay for the viewer, in the same 12-byte-header binary
    framing the client already parses for masks: [D:4][H:4][W:4][uint8 body], where
    the body labels each candidate voxel with its review-priority tier
    (1=high, 2=medium, 3=low; 0 elsewhere). Same fail-closed contract as /select.
    """
    settings = get_settings()
    if not settings.CALM_MS_RESEARCH_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    if request.preset not in PRESETS:
        raise HTTPException(status_code=422, detail=f"unknown preset; allowed: {sorted(PRESETS)}")
    try:
        await require_imaging_access(request.prob_file_id, current_user)
        file_data = await storage_service.download_file(settings.GCS_BUCKET_NAME, request.prob_file_id)
        img, arr = load_nifti_from_bytes(file_data)
        spacing = tuple(float(z) for z in img.header.get_zooms()[:3])
        review = await run_in_threadpool(conformal_review, arr.astype("float32"), spacing, request.preset)
        mask = review.status_mask
        d, h, w = mask.shape
        body = struct.pack("<III", int(d), int(h), int(w)) + mask.astype("uint8").tobytes()
        return Response(content=body, media_type="application/octet-stream", headers={
            "X-Mask-Depth": str(d), "X-Mask-Height": str(h), "X-Mask-Width": str(w),
            "X-Conformal-Preset": request.preset, "X-Conformal-Fdr-Target": str(review.fdr_target),
            "Cache-Control": "no-cache",
            "Access-Control-Expose-Headers": "X-Mask-Depth, X-Mask-Height, X-Mask-Width, X-Conformal-Preset, X-Conformal-Fdr-Target",
        })
    except ProvenanceMismatch as e:
        raise HTTPException(status_code=409, detail=f"exchangeability refused: {e}")
    except ConformalAssetError as e:
        raise HTTPException(status_code=503, detail=f"conformal null asset unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.error("[Conformal] status-mask failed", exc_info=True)
        raise HTTPException(status_code=500, detail="conformal status-mask failed")
