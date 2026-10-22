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

from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ai/report", tags=["AI Report"])

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
                      "by one by a radiologist; {confirmed} confirmed by a radiologist so far. They are "
                      "not findings.",
        "evidence": "In a public test with expert-marked change ({patients} patients) this rule proposed "
                    "on average {mean} false candidates per patient ({source}, {date}): most candidates "
                    "may be false.",
        "no_evidence": "No measured false-candidate rate is available for this rule.",
        "abstained": "**No automatic change candidates.** The acquisition of the two visits differs or "
                     "could not be established; the change between the visits must be assessed visually.",
    },
    "es": {
        "candidates": "**Candidatos automáticos de cambio (sin confirmar).** El programa propuso {total} "
                      "candidatos de cambio sin confirmar ({new} nuevos, {enl} agrandados), que un radiólogo "
                      "debe revisar uno a uno; {confirmed} confirmados por un radiólogo hasta ahora. No son "
                      "hallazgos.",
        "evidence": "En una prueba pública con cambios marcados por expertos ({patients} pacientes), esta "
                    "regla propuso de media {mean} candidatos falsos por paciente ({source}, {date}): la "
                    "mayoría de los candidatos pueden ser falsos.",
        "no_evidence": "No hay una tasa medida de candidatos falsos para esta regla.",
        "abstained": "**Sin candidatos automáticos de cambio.** La adquisición de las dos visitas es "
                     "distinta o no se pudo establecer; el cambio entre las visitas debe valorarse "
                     "visualmente.",
    },
    "de": {
        "candidates": "**Automatische Veränderungskandidaten (unbestätigt).** Die Software schlug {total} "
                      "unbestätigte Veränderungskandidaten vor ({new} neu, {enl} vergrößert), die ein "
                      "Radiologe einzeln prüft; bisher {confirmed} von einem Radiologen bestätigt. Sie sind "
                      "keine Befunde.",
        "evidence": "In einem öffentlichen Test mit von Experten markierten Veränderungen ({patients} "
                    "Patienten) schlug diese Regel im Mittel {mean} falsche Kandidaten pro Patient vor "
                    "({source}, {date}): die meisten Kandidaten können falsch sein.",
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
        new, enl, confirmed = _int(cc.get("new")), _int(cc.get("enlarging")), _int(cc.get("confirmed"))
    else:  # a payload without the candidate block: count what the rule counts, nothing confirmed
        sc = longitudinal.get("status_counts") or {}
        new, enl, confirmed = _int(sc.get("new")), _int(sc.get("enlarged")), 0
    lines = [texts["candidates"].format(total=new + enl, new=new, enl=enl, confirmed=confirmed)]
    ev = load_false_candidate_evidence()
    if ev:
        mean = f"{ev['false_candidates_per_patient']:g}"
        lines.append(texts["evidence"].format(
            patients=ev["patients"], mean=mean if language == "en" else mean.replace(".", ","),
            source=ev["source"], date=ev["measured_on"]))
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
        description="Clinical findings (de-identified). Keys: clinical_indication, "
                    "technique, patient_age, patient_sex, segmentation_labels, "
                    "anomalies, additional_observations",
    )
    volumetry: Optional[Dict[str, Any]] = Field(
        None,
        description="Volumetry results (from /ai/volumetry/compute)",
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
                "en, es, de. The findings are sent to the model provider: send no direct "
                "patient identifiers. 422 when no measurement is supplied (CAPA-008).",
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

    try:
        service = get_report_service()
        result = await service.generate_report(
            template_type=request.template_type,
            findings=request.findings,
            volumetry=request.volumetry,
            language=request.language,
        )
        notice = longitudinal_notice(request.findings.get("longitudinal"), request.language)
        if notice:   # CAPA-013: appended in code, after the model, in the report language
            result = {**result, "content": f"{result['content']}\n\n---\n\n> {notice}"}
        return ReportResponse(**result)

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
