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
# PRB-003 (RC-070): the segmentation named in a DIS block is authorized like any other mask reference.
from app.security.resource_access import authorize_mask_specs

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


# PRB-003 (RC-070, RC-072; HAZ-008, HAZ-003): a report request is client data, so a DIS conclusion in it
# cannot be trusted. The route derives the DIS state on the server for the report's own segmentation
# (`segmentation_id` of the request — never another one named inside a block), evaluated only on classified,
# radiologist-confirmed regions; without it the lesion measurements reach the model without regions, the
# template carries no DIS instruction, any DIS statement the model writes is replaced, and the draft ends with
# this notice, written by code in the report language (review of PR #68, findings 2-4).
DIS_NOT_EVALUATED_NOTICE: Dict[str, str] = {
    "en": "**Dissemination in space: not evaluated.** No radiologist has confirmed the lesions and their MAGNIMS "
          "regions for the current version of the segmentation, so the software did not assess dissemination "
          "in space; this draft must not be read as a statement on dissemination in space.",
    "es": "**Diseminación en el espacio: no evaluada.** Ningún radiólogo ha confirmado las lesiones y sus regiones "
          "MAGNIMS en la versión actual de la segmentación, por lo que el programa no evaluó la diseminación en "
          "el espacio; este borrador no debe leerse como una afirmación sobre la diseminación en el espacio.",
    "de": "**Räumliche Dissemination: nicht beurteilt.** Kein Radiologe hat die Läsionen und ihre MAGNIMS-Regionen "
          "in der aktuellen Fassung der Segmentierung bestätigt; die Software hat die räumliche Dissemination daher "
          "nicht beurteilt, und dieser Entwurf darf nicht als Aussage zur räumlichen Dissemination gelesen werden.",
}
# Second review of PR #68, N3: counted per statement (sentence, clause, table row or region heading).
DIS_LINES_REPLACED: Dict[str, str] = {
    "en": "{n} statement(s) of the drafting model's text on dissemination in space or on lesion regions were "
          "replaced or removed.",
    "es": "Se sustituyeron o eliminaron {n} afirmación(es) del texto del modelo de redacción sobre la diseminación "
          "en el espacio o sobre las regiones de las lesiones.",
    "de": "{n} Aussage(n) des Modelltextes zur räumlichen Dissemination oder zu den Regionen der Läsionen wurden "
          "ersetzt oder entfernt.",
}


def _dis_services():
    """The segmentation and storage services, resolved only when a DIS block must be re-derived."""
    from app.core.container import get_segmentation_service, get_storage_service
    return get_segmentation_service(), get_storage_service()


async def server_dis_assessment(segmentation_id: Optional[str], current_user: User) -> Dict[str, Any]:
    """The DIS state a report may use, derived on the server for the report's own segmentation.

    No segmentation named: not evaluated. The caller's right to read it was checked by the route (RC-029);
    the 404 of a segmentation that does not exist is raised to the caller. The state is computed by the same
    gated function as the DIS route, storing nothing (compute-only, RC-033). Any other failure of the
    assessment gives "not evaluated", never "not met"."""
    from app.services import dis_review_gate as gate

    if not isinstance(segmentation_id, str) or not segmentation_id.strip():
        return gate.not_evaluated(None, None, reason=gate.REASON_NOT_IDENTIFIED)
    from app.api.routes.segmentation_analysis import assess_dis

    segmentation_service, storage_service = _dis_services()
    try:
        return await assess_dis(segmentation_id, segmentation_service, storage_service, store=False)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — a failed assessment is "not evaluated", never "not met"
        logger.error(f"[Report] DIS assessment failed for the report: {e}")
        return gate.not_evaluated(segmentation_id, None, reason=gate.REASON_FAILED)


async def server_lesion_table(segmentation_id: str) -> Dict[str, Any]:
    """The lesion measurements a report may use, derived on the server for the report's own segmentation (N7).

    The caller's right to read it was checked by the route (RC-029). A table that cannot be computed is refused
    (422) — the client's table is never used instead."""
    from app.api.routes.segmentation_analysis import lesion_table

    segmentation_service, storage_service = _dis_services()
    try:
        return await lesion_table(segmentation_id, segmentation_service, storage_service)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error(f"[Report] Lesion measurements could not be computed for the report: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(f"The lesion measurements of segmentation {segmentation_id} could not be computed on the server "
                    "(the source image or its voxel geometry could not be read); nothing was sent."),
        )


def dis_notice(findings: Dict[str, Any], language: str, replaced: int = 0) -> Optional[str]:
    """The fixed notice for a draft with lesion measurements or a DIS block but no evaluated DIS, or None."""
    from app.services import dis_review_gate as gate

    if not (findings.get("lesion_analysis") or "dis_assessment" in findings or replaced):
        return None
    if gate.is_evaluated(findings.get("dis_assessment")):
        return None
    lang = language if language in DIS_NOT_EVALUATED_NOTICE else "en"
    parts = [DIS_NOT_EVALUATED_NOTICE[lang]]
    if replaced:
        parts.append(DIS_LINES_REPLACED[lang].format(n=replaced))
    parts.append(gate.AUTOMATIC_MARKING_NOTICE[lang])
    return " ".join(parts)


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
    segmentation_id: Optional[str] = Field(
        None,
        max_length=200,
        description=("The segmentation the findings were measured on (PRB-003): the DIS state and the lesion table "
                     "are derived for it on the server (the client's are not used); lesion measurements or a DIS "
                     "block naming another segmentation are refused (409)."),
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

    findings = dict(request.findings)
    if "longitudinal" in findings:   # CAPA-013, review of PR #63 (blocker 1)
        findings["longitudinal"] = drop_unverifiable_decisions(findings["longitudinal"])
    # PRB-003 (RC-070; review of PR #68, finding 2): every segmentation-bound block belongs to the report's own
    # segmentation; the DIS state is derived on the server for that one only.
    from app.services import dis_review_gate as gate
    report_sid = request.segmentation_id
    if report_sid:   # RC-029: the report's segmentation must be one the caller may read (404 otherwise)
        await authorize_mask_specs([{"type": "segmentation", "id": report_sid}], current_user)
    for key in ("lesion_analysis", "dis_assessment"):
        block = findings.get(key)
        named = block.get("segmentation_id") if isinstance(block, dict) else None
        if named and report_sid and named != report_sid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(f"The {key.replace('_', ' ')} belongs to another segmentation than this report "
                        "(segmentation_id differs); nothing was sent."),
            )
    if report_sid and "lesion_analysis" in findings:
        # Second review of PR #68, N7: the lesion table is derived on the server for the report's own segmentation
        # — a client table (with, without or with another `segmentation_id`) never reaches the model.
        findings["lesion_analysis"] = await server_lesion_table(report_sid)
    if "dis_assessment" in findings or (report_sid and "lesion_analysis" in findings):
        # N5: the model gets the confirmer's role and time, never the person.
        findings["dis_assessment"] = gate.without_reviewer_identity(
            await server_dis_assessment(report_sid, current_user))
        others = any(findings.get(k) for k in MEASUREMENT_FINDING_KEYS if k != "dis_assessment")
        if not (others or request.volumetry or gate.is_evaluated(findings["dis_assessment"])):
            # A "not evaluated" DIS state is not a measurement: the model would draft from nothing (RC-034).
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=("No measurement was supplied: dissemination in space was not evaluated (the segmentation "
                        "has not been confirmed by a radiologist), and nothing else was measured. A report "
                        "without measurements would be invented; run the lesion analysis first."),
            )
    dis_evaluated = gate.is_evaluated(findings.get("dis_assessment"))
    if not dis_evaluated and isinstance(findings.get("lesion_analysis"), dict):
        # Finding 3: regions of a segmentation no radiologist confirmed are not passed to the model.
        findings["lesion_analysis"] = gate.without_region_breakdown(findings["lesion_analysis"])

    try:
        service = get_report_service()
        result = await service.generate_report(
            template_type=request.template_type,
            findings=findings,
            volumetry=request.volumetry,
            language=request.language,
        )
        replaced = 0
        # Finding 4 / N3: a DIS statement written by the model is replaced, in code — a BACKSTOP; the main controls
        # are the earlier layers (no regions sent, the system safety rule, no DIS or per-region template section).
        # Merge note (PR #67): this check runs on the model's text only, BEFORE `assemble_draft` adds the
        # clinician's typed entry, which it must never touch.
        if not dis_evaluated:
            content, replaced = gate.scrub_unevaluated_dis(result["content"], request.language)
            if replaced:
                logger.warning("[Report] DIS statements written by the model were replaced",
                               extra={"replaced_statements": replaced})
            result = {**result, "content": content}
        notice = longitudinal_notice(request.findings.get("longitudinal"), request.language)
        if notice:   # CAPA-013: appended in code, after the model, in the report language
            result = {**result, "content": f"{result['content']}\n\n---\n\n> {notice}"}
        dis_text = dis_notice(findings, request.language, replaced)
        if dis_text:   # PRB-003 (RC-070, RC-072): appended in code, after the model, in the report language
            result = {**result, "content": f"{result['content']}\n\n---\n\n> {dis_text}"}
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
