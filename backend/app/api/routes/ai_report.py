"""
AI Report Generation API routes.

Provides endpoints for generating structured brain MRI reports
using Claude API, listing templates, and exporting reports.

@module api.routes.ai_report
"""

from fastapi import APIRouter, HTTPException, status, Depends
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.security import get_current_active_user
from app.security.models import User
from app.security.resource_access import authorize_segmentation_id
from app.services.report_deidentification import (
    DeidentificationError,
    DeidentificationUnavailable,
    PatientIdentifiers,
)

from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ai/report", tags=["AI Report"])

# CAPA-014 (RC-065, HAZ-016): the draft is written by an external model provider. The server removes
# the patient's identifiers first, using the record of the patient the analysed segmentation belongs
# to; without that record nothing is sent. Error texts name no identifier.
SUBJECT_REQUIRED_DETAIL = (
    "The analysed segmentation (segmentation_id) is required: the patient's identifiers are removed "
    "with that patient's record before anything is sent to the AI provider. Nothing was sent."
)
DEIDENTIFICATION_UNAVAILABLE_DETAIL = (
    "The patient's identifiers could not be removed ({reason}). Nothing was sent to the AI provider."
)


def _patient_service():
    from app.core.container import get_patient_service
    return get_patient_service()


async def read_patient_identifiers(patient_id: str) -> PatientIdentifiers:
    """The authorized patient's own identifiers, read from the record the server holds (RC-065).

    Raises DeidentificationUnavailable when the record cannot be read or lacks a field the removal
    needs; the caller must then send nothing.
    """
    try:
        record = await _patient_service().get_patient(patient_id)
    except Exception:          # noqa: BLE001 — any failure to read the record means: send nothing
        record = None
    return PatientIdentifiers.from_record(record)

# CAPA-008 (HAZ-003): keys of `findings` that carry a MEASUREMENT computed by the device.
# A request with none of them (and no volumetry) would make the language model write a
# report from nothing — the assistant's MS report tool did exactly that for months, because
# it sent its data under field names this route silently ignored. Such a request is refused.
MEASUREMENT_FINDING_KEYS = frozenset({
    "lesion_analysis", "dis_assessment", "longitudinal", "zone_stats",
    "segmentation_labels", "anomalies",
})


# CAPA-013 (RC-060, RC-061, RC-062; HAZ-007): a draft that received a longitudinal comparison
# ends with this notice, written by code in the report language — whatever the model wrote.
# The measured false-candidate rate comes from the server's versioned asset, never from the
# request. No wording here may present unconfirmed candidates as a statement on the disease.
LONGITUDINAL_NOTICE: Dict[str, Dict[str, str]] = {
    "en": {
        "candidates": "**Automatic change candidates (unconfirmed).** The software proposed {total} "
                      "unconfirmed change candidate(s) ({new} new, {enl} enlarging), to be reviewed one "
                      "by one by a radiologist. They are not findings. The radiologist's decisions are "
                      "recorded in the application, not in this draft.",
        "evidence": "In a public test with expert-marked change ({patients} patients) this rule proposed "
                    "on average {mean} false candidates per patient, {pct} % of all the candidates it "
                    "proposed ({source}, {date}).",
        "no_evidence": "No measured false-candidate rate is available for this rule.",
        "abstained": "**No automatic change candidates.** The acquisition of the two visits differs or "
                     "could not be established; the change between the visits must be assessed visually.",
    },
    "es": {
        "candidates": "**Candidatos automáticos de cambio (sin confirmar).** El programa propuso {total} "
                      "candidatos de cambio sin confirmar ({new} nuevos, {enl} agrandados), que un radiólogo "
                      "debe revisar uno a uno. No son hallazgos. Las decisiones del radiólogo constan en la "
                      "aplicación, no en este borrador.",
        "evidence": "En una prueba pública con cambios marcados por expertos ({patients} pacientes), esta "
                    "regla propuso de media {mean} candidatos falsos por paciente, el {pct} % de todos los "
                    "candidatos que propuso ({source}, {date}).",
        "no_evidence": "No hay una tasa medida de candidatos falsos para esta regla.",
        "abstained": "**Sin candidatos automáticos de cambio.** La adquisición de las dos visitas es "
                     "distinta o no se pudo establecer; el cambio entre las visitas debe valorarse "
                     "visualmente.",
    },
    "de": {
        "candidates": "**Automatische Veränderungskandidaten (unbestätigt).** Die Software schlug {total} "
                      "unbestätigte Veränderungskandidaten vor ({new} neu, {enl} vergrößert), die ein "
                      "Radiologe einzeln prüft. Sie sind keine Befunde. Die Entscheidungen des Radiologen "
                      "sind in der Anwendung erfasst, nicht in diesem Entwurf.",
        "evidence": "In einem öffentlichen Test mit von Experten markierten Veränderungen ({patients} "
                    "Patienten) schlug diese Regel im Mittel {mean} falsche Kandidaten pro Patient vor, "
                    "{pct} % aller vorgeschlagenen Kandidaten ({source}, {date}).",
        "no_evidence": "Für diese Regel liegt keine gemessene Rate falscher Kandidaten vor.",
        "abstained": "**Keine automatischen Veränderungskandidaten.** Die Aufnahmetechnik der beiden "
                     "Untersuchungen unterscheidet sich oder ließ sich nicht feststellen; die Veränderung "
                     "muss visuell beurteilt werden.",
    },
}


def _int(v) -> int:
    try:
        return max(0, int(v))
    except Exception:  # noqa: BLE001
        return 0


# Review of PR #63, blocker 1: a report request is client data. A reader decision in it cannot be
# verified (the route has no stored decision to check it against), so it is removed before the
# findings reach the report service; the report states that decisions are kept in the application.
UNVERIFIABLE_DECISION_FIELDS = ("reader_confirmed_activity",)
UNVERIFIABLE_CANDIDATE_COUNTS = ("confirmed", "rejected", "awaiting_review", "decisions_unavailable")


def drop_unverifiable_decisions(longitudinal: Any) -> Any:
    """A copy of a client-supplied longitudinal block without any reader decision or decision count."""
    if not isinstance(longitudinal, dict):
        return longitudinal
    out = {k: v for k, v in longitudinal.items() if k not in UNVERIFIABLE_DECISION_FIELDS}
    if isinstance(out.get("changes"), list):
        out["changes"] = [{k: v for k, v in c.items() if k != "reader_review"} if isinstance(c, dict) else c
                          for c in out["changes"]]
    if isinstance(out.get("change_candidates"), dict):
        out["change_candidates"] = {k: v for k, v in out["change_candidates"].items()
                                    if k not in UNVERIFIABLE_CANDIDATE_COUNTS}
    return out


def longitudinal_notice(longitudinal: Any, language: str) -> Optional[str]:
    """The fixed notice for a draft that received a longitudinal comparison, or None."""
    if not isinstance(longitudinal, dict) or not longitudinal:
        return None
    from app.services.longitudinal_candidate_safety import load_false_candidate_evidence

    texts = LONGITUDINAL_NOTICE.get(language, LONGITUDINAL_NOTICE["en"])
    if longitudinal.get("abstained"):
        return texts["abstained"]
    cc = longitudinal.get("change_candidates")
    if isinstance(cc, dict):
        new, enl = _int(cc.get("new")), _int(cc.get("enlarging"))
    else:  # a payload without the candidate block: count what the rule counts
        sc = longitudinal.get("status_counts") or {}
        new, enl = _int(sc.get("new")), _int(sc.get("enlarged"))
    lines = [texts["candidates"].format(total=new + enl, new=new, enl=enl)]
    from app.services.longitudinal_candidate_safety import false_share_percent
    ev = load_false_candidate_evidence()
    if ev:
        mean = f"{ev['false_candidates_per_patient']:g}"
        lines.append(texts["evidence"].format(
            patients=ev["patients"], mean=mean if language == "en" else mean.replace(".", ","),
            pct=false_share_percent(ev), source=ev["source"], date=ev["measured_on"]))
    else:
        lines.append(texts["no_evidence"])
    return " ".join(lines)


# =============================================================================
# Request/Response Models
# =============================================================================

class ReportGenerateRequest(BaseModel):
    """Request to generate a brain MRI report."""
    template_type: str = Field(
        default="general",
        pattern="^(general|ms_activity|ms_lesion_burden|ms_comprehensive|ms_longitudinal)$",
        description="Report template type",
    )
    language: str = Field(
        default="en",
        pattern="^(en|es|de)$",
        description="Report language",
    )
    findings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Clinical findings. Keys: clinical_indication, technique, patient_age, "
                    "patient_sex, segmentation_labels, anomalies, additional_observations, "
                    "lesion_analysis, dis_assessment, longitudinal, zone_stats. The server removes "
                    "identifiers before sending (CAPA-014); the age is sent as a 5-year band.",
    )
    volumetry: Optional[Dict[str, Any]] = Field(
        None,
        description="Volumetry results (from /ai/volumetry/compute)",
    )
    segmentation_id: Optional[str] = Field(
        None,
        max_length=200,
        description="The analysed segmentation the draft is for. Required (400 without it): its "
                    "patient's record lets the server remove that patient's identifiers before "
                    "anything is sent to the model provider (CAPA-014).",
    )


class ReportResponse(BaseModel):
    """Response with generated report."""
    report_id: str
    content: str
    template_type: str
    language: str
    processing_time_ms: int
    model: Optional[str] = None
    tokens_used: Optional[Dict[str, int]] = None


class ReportTemplateInfo(BaseModel):
    """Report template information."""
    id: str
    name: str
    description: str


# =============================================================================
# Lazy Service Loader
# =============================================================================

def get_report_service():
    """Lazy-load brain report service."""
    from app.services.brain_report_service import BrainReportService
    return BrainReportService()


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/generate",
    response_model=ReportResponse,
    summary="Generate brain MRI report",
    description="Generate a DRAFT structured brain MRI report from measurements computed by "
                "the device, using the Claude API, for physician review. Templates: general, "
                "ms_activity, ms_lesion_burden, ms_comprehensive, ms_longitudinal; languages "
                "en, es, de. Before anything is sent to the model provider the server removes the "
                "patient's identifiers, using the record of the patient of `segmentation_id` "
                "(CAPA-014). 422 when no measurement is supplied (CAPA-008); 400 when no segmentation is; "
                "404 when the caller may not access the segmentation; 503 when the identifiers "
                "cannot be removed (nothing is sent).",
)
async def generate_report(
    request: ReportGenerateRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Generate a draft brain MRI report from measurements computed by the device."""
    logger.info(
        f"[Report] Generate request: template={request.template_type}, "
        f"lang={request.language}"
    )

    # CAPA-008 (HAZ-003): never ask the model to write a report without a measurement.
    if not any(request.findings.get(k) for k in MEASUREMENT_FINDING_KEYS) and not request.volumetry:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No measurement was supplied (lesion analysis, DIS assessment, longitudinal "
                "comparison, zone statistics or volumetry). A report without measurements "
                "would be invented; open a segmentation and run its analysis first."
            ),
        )

    # CAPA-014 (RC-065, HAZ-016): the patient whose identifiers must be removed — authorized for
    # this caller (404 otherwise, as every object route) and read from the server's own record.
    # 400, not 422: the report panel reads every 422 as "no measurements" (CAPA-008).
    if not request.segmentation_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=SUBJECT_REQUIRED_DETAIL)
    patient_id = await authorize_segmentation_id(request.segmentation_id, current_user)
    try:
        identifiers = await read_patient_identifiers(patient_id)
    except DeidentificationUnavailable as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=DEIDENTIFICATION_UNAVAILABLE_DETAIL.format(reason=str(e)))

    findings = dict(request.findings)
    if "longitudinal" in findings:   # CAPA-013, review of PR #63 (blocker 1)
        findings["longitudinal"] = drop_unverifiable_decisions(findings["longitudinal"])

    try:
        service = get_report_service()
        result = await service.generate_report(
            template_type=request.template_type,
            findings=findings,
            volumetry=request.volumetry,
            language=request.language,
            identifiers=identifiers,
        )
        notice = longitudinal_notice(request.findings.get("longitudinal"), request.language)
        if notice:   # CAPA-013: appended in code, after the model, in the report language
            result = {**result, "content": f"{result['content']}\n\n---\n\n> {notice}"}
        return ReportResponse(**result)

    except DeidentificationError as e:
        # CAPA-014 (RC-065): the service refused to send; the message names a category, no identifier.
        logger.warning("[Report] Not sent: de-identification could not be assured",
                       extra={"deidentification": "refused"})
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=DEIDENTIFICATION_UNAVAILABLE_DETAIL.format(reason=str(e)))
    except RuntimeError as e:
        # ANTHROPIC_API_KEY not configured
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"[Report] Generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {str(e)}",
        )


@router.get(
    "/templates",
    response_model=List[ReportTemplateInfo],
    summary="List report templates",
    description="List available brain MRI report templates with descriptions.",
)
async def list_templates(current_user: User = Depends(get_current_active_user)):
    """List available report templates."""
    service = get_report_service()
    return service.list_templates()
