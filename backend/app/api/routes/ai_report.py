"""
AI Report Generation API routes.

Provides endpoints for generating structured brain MRI reports
using Claude API, listing templates, and exporting reports.

@module api.routes.ai_report
"""

import re
import unicodedata

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.routing import APIRoute
from typing import Optional, List, Dict, Any, Literal, Tuple
from pydantic import BaseModel, Field

from app.services import verified_report
from app.security import get_current_active_user
from app.security.models import User
from app.security.resource_access import authorize_segmentation_id
# PRB-003 (RC-070): the segmentation named in a DIS block is authorized like any other mask reference.
from app.security.resource_access import authorize_mask_specs
from app.services.report_payload_guard import (
    FREE_TEXT_FIELDS,
    PatientIdentifiers,
    ImplausibleMeasurement,
    PatientRecordUnavailable,
    ProviderGuardError,
    without_format_characters,      # the one shared rule (fourth review of PR #78, Q6)
)
# fourth review of PR #78, Q7: the blocks the verified report writes — one source
from app.services.verified_report import RENDERED_FINDINGS

from app.core.exceptions import AppException
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ai/report", tags=["AI Report"])   # (route class set below, once ReportError exists)

# Tenth independent review of PR #78, I16 (DRAFT, PENDING owner approval): every error this route returns carries a
# machine-readable code (`error.code`; its parameters in `error.details`) — the report panel maps the code to its own
# message (AIReportPanel.tsx), never a message prefix. One list, checked against the shared fixture
# backend/tests/fixtures/report_error_codes.json by the backend and the frontend tests.
REPORT_ERROR_CODES = frozenset({
    "nothing_to_report",            # 422 CAPA-008: nothing the verified report can write (after the route's substitutions)
    "segmentation_required",        # 400 CAPA-014: no analysed segmentation named
    "segmentation_not_found",       # 404 RC-029: not found, or not one the caller may read
    "segmentation_conflict",        # 409 PRB-003: a block names another segmentation
    "request_invalid",              # 400 a reference the shared checks refuse
    "geometry_unreadable",          # 422 the voxel geometry of the source image could not be read
    "lesion_table_failed",          # 422 the server-side lesion table could not be computed
    "implausible_measurement",      # 422 RC-064: a measurement outside its plausible range (details.field)
    "patient_record_unavailable",   # 503 RC-065: the patient's record could not be read; nothing sent
    # (eleventh review, C1: an identifier-check hit is no error any more — a measurements-only draft, reason
    # identifier_check, as a patient-number match; "identifier_in_prompt" was removed)
    "label_in_record",              # 503 R8: a request label reached the record; nothing sent
    "not_sent",                     # 503 any other refusal of the privacy checks; nothing sent
    "report_failed",                # 500 an internal failure
})


class ReportError(AppException):
    """An error of the report route with its code (I16): {"error": {"code", "message", "details"}}."""

    def __init__(self, code: str, status_code: int, message: str, details: Optional[Dict[str, Any]] = None):
        assert code in REPORT_ERROR_CODES, code
        super().__init__(message=message, status_code=status_code, error_code=code, details=details or {})


# A shared check (authorization, the segmentation store) answers with a plain HTTP error: coded by its status.
_CODE_OF_STATUS = {400: "request_invalid", 404: "segmentation_not_found", 409: "segmentation_conflict"}


def _coded(e: HTTPException) -> ReportError:
    return ReportError(_CODE_OF_STATUS[e.status_code], e.status_code, str(e.detail))


class _CodedErrorsRoute(APIRoute):
    """The routes of this router: an HTTP error a shared check raises inside the route (authorization of the
    segmentation, the segmentation store) leaves with its code too. The sign-in's own answers (401, 403 of an inactive
    account) and the other statuses pass unchanged."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def coded(request):
            try:
                return await handler(request)
            except HTTPException as e:
                if e.status_code not in _CODE_OF_STATUS:
                    raise
                raise _coded(e) from e

        return coded


router.route_class = _CodedErrorsRoute


NOTHING_TO_REPORT_DETAIL = (
    "No measurement the verified report can write was supplied (lesion analysis, DIS assessment, longitudinal "
    "comparison, or total brain or intracranial volume). A report without measurements would be invented; open a "
    "segmentation and run its analysis first.")

# CAPA-014 (RC-065, HAZ-016): the draft is written by an external model provider from measurements only.
# Before the call the final prompt is checked against the record of the patient the analysed
# segmentation belongs to; without that record nothing is sent. Error texts name no identifier.
SUBJECT_REQUIRED_DETAIL = (
    "The analysed segmentation (segmentation_id) is required: the request to the AI service is checked "
    "against that patient's record before it is sent. Nothing was sent."
)
NOT_SENT_DETAIL = "The request was not sent to the AI service ({reason}). Nothing was sent."

# CAPA-014 (RC-066): the clinician's typed text is added to the draft here, after the model returns; it is never
# sent. The response carries it — and the application's notes — as fields of their own, which the report viewer
# renders outside the Markdown renderer, so nothing the model writes can look like them (final check of the third
# review, R1). The single text for copy and export quotes them under fixed headings, and the model's text always
# follows under its own fixed heading. Headings in the report language.
CLINICIAN_ENTRY: Dict[str, Dict[str, str]] = {
    "en": {"heading": "Clinician's entry (added in the application; not sent to the AI service)",
           "clinical_indication": "Clinical indication", "technique": "Technique",
           "additional_observations": "Additional observations"},
    "es": {"heading": "Datos del médico (añadidos en la aplicación; no enviados al servicio de IA)",
           "clinical_indication": "Indicación clínica", "technique": "Técnica",
           "additional_observations": "Observaciones adicionales"},
    "de": {"heading": "Angaben der Ärztin / des Arztes (in der Anwendung ergänzt; nicht an den KI-Dienst gesendet)",
           "clinical_indication": "Klinische Fragestellung", "technique": "Technik",
           "additional_observations": "Weitere Beobachtungen"},
}
AI_DRAFT_HEADING: Dict[str, str] = {
    "en": "AI draft (from measurements only)",
    "es": "Borrador de IA (solo a partir de las mediciones)",
    "de": "KI-Entwurf (nur aus den Messwerten)",
}
# Labels outside the device's vocabulary (e.g. a label the clinician renamed) reach the model as numbered
# placeholders; the draft names them for the clinician, here only.
UNLISTED_NOTE: Dict[str, str] = {
    "en": "Labels outside the device's vocabulary were sent to the AI service as numbered placeholders; "
          "their names were not sent:",
    "es": "Las etiquetas fuera del vocabulario del dispositivo se enviaron al servicio de IA como marcadores "
          "numerados; sus nombres no se enviaron:",
    "de": "Bezeichnungen außerhalb des Vokabulars des Geräts wurden als nummerierte Platzhalter an den "
          "KI-Dienst gesendet; ihre Namen wurden nicht gesendet:",
}
# The heading of the application's note in the single text (copy, export).
APP_NOTE_HEADING: Dict[str, str] = {
    "en": "Application note (written by the application, not by the AI service)",
    "es": "Nota de la aplicación (escrita por la aplicación, no por el servicio de IA)",
    "de": "Hinweis der Anwendung (von der Anwendung verfasst, nicht vom KI-Dienst)",
}
TRUNCATED_NOTE: Dict[str, str] = {
    "en": "[truncated: only the first {n} characters of this field are shown]",
    "es": "[truncado: solo se muestran los primeros {n} caracteres de este campo]",
    "de": "[gekürzt: nur die ersten {n} Zeichen dieses Feldes werden angezeigt]",
}
# A line of the model's text that is exactly one of the application's headings is replaced by this line.
RESERVED_HEADING_REMOVED: Dict[str, str] = {
    "en": "[a heading reserved for the application was removed from the AI text]",
    "es": "[se quitó del texto de la IA un título reservado para la aplicación]",
    "de": "[eine der Anwendung vorbehaltene Überschrift wurde aus dem KI-Text entfernt]",
}
MAX_TYPED_CHARS = 5000
MAX_LABEL_CHARS = 200
# Bidirectional control characters (LRE, RLE, PDF, LRO, RLO, LRI, RLI, FSI, PDI): removed from the typed text. The
# model's text loses every format character (Unicode category Cf), these included.
_BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")
_LINE_MARKS = re.compile(r"^(?:(?:>|[-*+]|\d{1,9}[.)]|#{1,6})\s*)*")
_QUOTE_OR_LIST = re.compile(r"^(?:(?:>|[-*+]|\d{1,9}[.)])\s+)*")
_SETEXT_LINE = re.compile(r"=+|-+")
_BOLD_LINE = re.compile(r"(\*\*|__).+\1:?")


def without_bidi(text: str) -> str:
    return _BIDI.sub("", text)


def quoted(text: str) -> str:
    """`text` exactly as written, in a fenced block longer than any run of backticks inside it: nothing in it
    is rendered as Markdown (heading, image, link, HTML) and nothing in it can close the block."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    fence = "`" * max(3, 1 + max((len(run) for run in re.findall(r"`+", text)), default=0))
    return f"{fence}text\n{text}\n{fence}"


def _typed(value: str) -> Tuple[str, bool]:
    """The typed text without bidirectional controls, leading blank lines and trailing space — the first
    line keeps its indentation — cut at MAX_TYPED_CHARS; and whether it was cut."""
    text = re.sub(r"\A(?:[ \t]*\r?\n)+", "", without_bidi(value)).rstrip()
    return text[:MAX_TYPED_CHARS], len(text) > MAX_TYPED_CHARS


def clinician_entry_of(findings: Dict[str, Any], language: str) -> Optional[Dict[str, Any]]:
    """The clinician's typed text as a response field — heading, labelled fields, whether each was cut at
    MAX_TYPED_CHARS and the note that says so — or None when nothing was typed."""
    texts = CLINICIAN_ENTRY.get(language, CLINICIAN_ENTRY["en"])
    fields = []
    for key in FREE_TEXT_FIELDS:
        if isinstance(findings.get(key), str) and without_bidi(findings[key]).strip():
            text, cut = _typed(findings[key])
            fields.append({"key": key, "label": texts[key], "text": text, "truncated": cut})
    if not fields:
        return None
    cut_note = TRUNCATED_NOTE.get(language, TRUNCATED_NOTE["en"]).format(n=MAX_TYPED_CHARS)
    return {"heading": texts["heading"], "fields": fields,
            "truncated_note": cut_note if any(f["truncated"] for f in fields) else None}


def app_notes_of(unlisted: Any, language: str) -> List[Dict[str, Any]]:
    """The application's notes as a response field: which label each numbered placeholder stands for."""
    if not isinstance(unlisted, dict) or not unlisted:
        return []
    lines = [f"{placeholder} = {' '.join(without_bidi(str(written)).split())[:MAX_LABEL_CHARS]}"
             for placeholder, written in unlisted.items()]
    return [{"kind": "unlisted_labels", "heading": APP_NOTE_HEADING.get(language, APP_NOTE_HEADING["en"]),
             "text": UNLISTED_NOTE.get(language, UNLISTED_NOTE["en"]), "lines": lines}]


def _heading_key(line: str) -> str:
    """A line reduced to its words: quote, list and heading marks, surrounding emphasis, spacing and case removed."""
    text = unicodedata.normalize("NFKC", line).replace("\u2019", "'").strip()
    return " ".join(_LINE_MARKS.sub("", text).strip("*_# \t").split()).casefold()


def _reserved_headings() -> frozenset:
    headings = [entry["heading"] for entry in CLINICIAN_ENTRY.values()] + list(AI_DRAFT_HEADING.values())
    return frozenset(_heading_key(h) for h in headings)


def neutralised_model_text(body: str, language: str) -> str:
    """The model's text without format characters, and with every line that is exactly one of the application's
    headings (any language; with heading, list, quote or emphasis marks) replaced by a fixed line. Ordinary
    sentences stay as written; the boxes of the entry and of the notes are response fields the model cannot write."""
    body = without_format_characters(body)
    reserved, removed = _reserved_headings(), RESERVED_HEADING_REMOVED.get(language, RESERVED_HEADING_REMOVED["en"])
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if _heading_key(line) in reserved:
            lines[i] = removed
    return "\n".join(lines)


def _reserved_prefixes() -> Tuple[str, ...]:
    headings = ([entry["heading"] for entry in CLINICIAN_ENTRY.values()] + list(AI_DRAFT_HEADING.values())
                + list(APP_NOTE_HEADING.values()))
    return tuple(_heading_key(h.split(" (")[0]) for h in headings)


def without_reserved_heading_imitations(text: str, language: str) -> str:
    """For the single text: a heading line of the AI text (marked with #, all bold, or underlined) whose words start
    like one of the application's headings — "Clinician's entry", "Application note", "AI draft", es/de — is
    replaced by a fixed line, so that the copied text cannot show a second entry or note. Other lines stay."""
    prefixes, removed = _reserved_prefixes(), RESERVED_HEADING_REMOVED.get(language, RESERVED_HEADING_REMOVED["en"])
    lines = text.split("\n")
    for i, line in enumerate(lines):
        bare = _QUOTE_OR_LIST.sub("", line.strip())
        following = _QUOTE_OR_LIST.sub("", lines[i + 1].strip()) if i + 1 < len(lines) else ""
        heading = bare.startswith("#") or _BOLD_LINE.fullmatch(bare) or (bare and _SETEXT_LINE.fullmatch(following))
        key = _heading_key(line)
        # starts like one: the line begins with a reserved heading's name, or is its first two words or more
        if heading and any(key.startswith(p) or (len(key.split()) >= 2 and p.startswith(key)) for p in prefixes):
            lines[i] = removed
    return "\n".join(lines)


def draft_parts(content: str, language: str, findings: Dict[str, Any], unlisted: Any) -> Dict[str, Any]:
    """The parts of the draft the response carries: the RC-006 disclaimer, the clinician's entry, the fixed heading
    of the AI text, the application's notes and the model's text (neutralised)."""
    from app.services.brain_report_service import REPORT_DISCLAIMER_EN, REPORT_DISCLAIMERS
    disclaimer = REPORT_DISCLAIMERS.get(language, REPORT_DISCLAIMER_EN)
    has_disclaimer = content.startswith(disclaimer)
    body = content[len(disclaimer):].lstrip() if has_disclaimer else content
    return {"disclaimer": disclaimer if has_disclaimer else None,
            "clinician_entry": clinician_entry_of(findings, language),
            "ai_draft_heading": AI_DRAFT_HEADING.get(language, AI_DRAFT_HEADING["en"]),
            "app_notes": app_notes_of(unlisted, language),
            "ai_text": neutralised_model_text(body, language)}


def draft_text(parts: Dict[str, Any], language: str) -> str:
    """The whole draft as one text, for copy and export, assembled from the parts: the disclaimer first; the
    clinician's entry under its fixed heading, each field quoted, closed by a rule; the AI heading; the
    application's notes under their heading, quoted; the model's text without imitations of those headings."""
    out = [parts.get("disclaimer")]
    entry = parts.get("clinician_entry")
    if entry:
        blocks = [f"**{f['label']}:**\n\n{quoted(f['text'])}" + (f"\n\n{entry['truncated_note']}" if f["truncated"] else "")
                  for f in entry["fields"]]
        out.append(f"### {entry['heading']}\n\n" + "\n\n".join(blocks) + "\n\n---")
    out.append(f"### {parts['ai_draft_heading']}")
    out += [f"#### {note['heading']}\n\n{note['text']}\n\n{quoted(chr(10).join(note['lines']))}"
            for note in parts.get("app_notes") or []]
    out.append(without_reserved_heading_imitations(parts.get("ai_text") or "", language))
    return "\n\n".join(part for part in out if part)


def _patient_service():
    from app.core.container import get_patient_service
    return get_patient_service()


async def read_patient_identifiers(patient_id: str) -> PatientIdentifiers:
    """The authorized patient's own identifiers, read from the record the server holds (RC-065).

    Raises PatientRecordUnavailable when the record cannot be read or lacks a field the check needs;
    the caller must then send nothing.
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
# Second review of PR #78 (D, DRAFT): only the blocks the verified report writes count (zone statistics, segmentation
# labels and anomalies are accepted but not included, so alone they are no measurement for this report).
MEASUREMENT_FINDING_KEYS = frozenset(RENDERED_FINDINGS)       # fourth review, Q7: the verified report's own list


# CAPA-013 (RC-060, RC-061, RC-062; HAZ-007): the change notice of a draft with a longitudinal comparison is written by
# the report service from its validated record (sixth review of PR #78, W1: `verified_report.change_notice`, returned
# as `change_notice`); the route appends it after the model's text and never recomputes it from the request.


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


# PRB-003 (RC-070, RC-072; HAZ-008, HAZ-003): a report request is client data, so a DIS conclusion in it cannot be
# trusted. The route derives the DIS state on the server for the report's own segmentation (`segmentation_id` of the
# request — never another one named inside a block), evaluated only on classified, radiologist-confirmed regions;
# without it the lesion measurements reach the model without regions. Fifth review of PR #78, V8: the report service
# owns the statement and the notice (`dis_evaluation`); the route adds no DIS text and re-checks none.


# Release 2026-10-25 (integration review of PR #69, item 6): the 422 of a lesion table that cannot be computed starts
# with this phrase (tenth review of PR #78, I16: the report panel reads its code, geometry_unreadable /
# lesion_table_failed, no longer the phrase).
GEOMETRY_UNREADABLE_PHRASE = "The image geometry could not be read; report not generated"
# Review of PR #69, n1: any other failure of the server-side lesion table says so (not "geometry").
LESION_TABLE_FAILED_PHRASE = "The lesion measurements could not be computed on the server; report not generated"


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
        from app.utils import VoxelSpacingUnavailableError
        if isinstance(e, VoxelSpacingUnavailableError):
            raise ReportError(
                "geometry_unreadable", status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{GEOMETRY_UNREADABLE_PHRASE}: the lesion measurements of segmentation {segmentation_id} could not be "
                "computed on the server (the source image or its voxel geometry could not be read). Nothing was sent.")
        raise ReportError(
            "lesion_table_failed", status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{LESION_TABLE_FAILED_PHRASE} ({type(e).__name__}) for segmentation {segmentation_id}. Nothing was sent.")


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
                    "lesion_analysis, dis_assessment, longitudinal, zone_stats. Verified report (REQ-FUNC-116, "
                    "DRAFT): the draft is built from lesion_analysis, dis_assessment, longitudinal and the total "
                    "brain and intracranial volume of `volumetry`; zone_stats, segmentation_labels, anomalies and "
                    "the structure volumes of `volumetry` are accepted but not included in the verified draft — "
                    "the draft names them as not included (and `verification.not_included` lists them). Only "
                    "measurements reach the AI service (no sex, no age band); the typed text fields are added to "
                    "the draft here, never sent (CAPA-014).",
    )
    volumetry: Optional[Dict[str, Any]] = Field(
        None,
        description="Volumetry results (from /ai/volumetry/compute)",
    )
    segmentation_id: Optional[str] = Field(
        None,
        max_length=200,
        description="The analysed segmentation the draft is for. Required (400 without it): the "
                    "request to the AI service is checked against its patient's record before it "
                    "is sent (CAPA-014). The DIS state and the lesion table are derived for it on "
                    "the server (the client's are not used); lesion measurements or a DIS block "
                    "naming another segmentation are refused (409) (PRB-003).",
    )


class ClinicianField(BaseModel):
    """One field the clinician typed (CAPA-014): shown as written, never sent to the AI service."""
    key: str
    label: str
    text: str
    truncated: bool = False


class ClinicianEntry(BaseModel):
    heading: str
    fields: List[ClinicianField]
    truncated_note: Optional[str] = None


class AppNote(BaseModel):
    """A note written by the application (not by the AI service), e.g. which label a placeholder stands for."""
    kind: str
    heading: Optional[str] = None
    text: str
    lines: List[str] = []


class ReportResponse(BaseModel):
    """Response with generated report.

    CAPA-014: `content` is the whole draft as one text (copy, export): fixed headings, typed text and notes quoted.
    The viewer renders the parts — `disclaimer`, `clinician_entry`, `ai_draft_heading`, `app_notes` in components of
    their own, and only `ai_text` (the model's text and the application's notices after it) as Markdown."""
    report_id: str
    content: str
    template_type: str
    language: str
    processing_time_ms: int
    model: Optional[str] = None
    tokens_used: Optional[Dict[str, int]] = None
    disclaimer: Optional[str] = None
    clinician_entry: Optional[ClinicianEntry] = None
    ai_draft_heading: Optional[str] = None
    app_notes: List[AppNote] = []
    ai_text: Optional[str] = None
    # REQ-FUNC-116 / RC-103 (DRAFT, PENDING owner approval): how the verified draft was obtained — flow, outcome
    # (passed_0/1/2, blocked, not_requested), whether the AI comments are in it (delivered / withheld /
    # not_requested) and why not, the number of attempts and the rule ids that failed last. Codes only.
    verification: Optional[Dict[str, Any]] = None
    # PRB-003 / RC-070 (fifth review of PR #78, V8; DRAFT): the DIS state of the draft, as the service wrote it —
    # "evaluated", "not_evaluated" (stated once in the findings, the notice follows) or "not_in_report"
    dis_evaluation: Optional[Literal["evaluated", "not_evaluated", "not_in_report"]] = None
    # CAPA-013 (sixth review of PR #78, W1; DRAFT): the change notice the service wrote from its validated record
    change_notice: Optional[str] = None


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
                "the device, for physician review. Verified report (REQ-FUNC-116, DRAFT): every number "
                "and status is written by code; the Claude API writes two short comments that pass an "
                "automatic check against the measurements or are withheld (`verification`). Written and sent to "
                "the model provider: the lesion count, the total lesion volume and the size classes, the lesions "
                "per MAGNIMS region and dissemination in space when a radiologist confirmed the segmentation, the "
                "change candidates of a visit pair, and the total brain and intracranial volume — no sex, no age "
                "band, no per-lesion values; the typed text is added to the draft here, never sent. Zone "
                "statistics, segmentation labels, anomalies and structure volumes are accepted but not included "
                "in the verified draft, which names them (`verification.not_included`); they are neither sent nor "
                "checked. Templates: general, ms_activity, ms_lesion_burden, ms_comprehensive, ms_longitudinal "
                "(recorded; one verified structure); languages en, es, de. The request is checked against the "
                "record of the patient of `segmentation_id` before it is sent (CAPA-014). 422 when nothing the "
                "verified report can write is supplied (CAPA-008); 400 when no segmentation is; 404 when the "
                "caller may not access the segmentation; 503 when the check cannot run or finds an identifier "
                "(nothing is sent). Every error carries a machine-readable `error.code` (REPORT_ERROR_CODES; "
                "parameters in `error.details`).",
)
async def generate_report(
    request: ReportGenerateRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Generate a draft brain MRI report from measurements computed by the device. Every error carries its code
    (tenth review of PR #78, I16): the route's own as ReportError; a shared check's HTTP error is coded by the
    router's route class (_CodedErrorsRoute)."""
    started = verified_report.now()   # REQ-SAFE-019 (sixth review of PR #78, W7): the 30 s count from here
    logger.info(
        f"[Report] Generate request: template={request.template_type}, "
        f"lang={request.language}"
    )

    # CAPA-008 (HAZ-003): never ask the model to write a report without a measurement. Second review of PR #78, D:
    # aligned with what the verified report can write — zone statistics, segmentation labels, anomalies or structure
    # volumes alone would give an empty report.
    if not verified_report.renderable(request.findings, request.volumetry):
        raise ReportError("nothing_to_report", status.HTTP_422_UNPROCESSABLE_ENTITY, NOTHING_TO_REPORT_DETAIL)

    # CAPA-014 (RC-065, HAZ-016): the patient the prompt is checked against — authorized for this
    # caller (404 otherwise, as every object route) and read from the server's own record.
    # (400; tenth review, I16: the panel reads the code, segmentation_required)
    if not request.segmentation_id:
        raise ReportError("segmentation_required", status.HTTP_400_BAD_REQUEST, SUBJECT_REQUIRED_DETAIL)
    patient_id = await authorize_segmentation_id(request.segmentation_id, current_user)
    service = get_report_service()

    async def identifiers():
        """The patient's own identifiers, read only if the service will send a request (seventh review of PR #78,
        finding 8; eighth review, finding 3: the service decides first — its one gate, the record, the time budget —
        and reads the patient record only when a call will happen)."""
        return await read_patient_identifiers(patient_id)

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
            raise ReportError("segmentation_conflict", status.HTTP_409_CONFLICT,
                              f"The {key.replace('_', ' ')} belongs to another segmentation than this report "
                              "(segmentation_id differs); nothing was sent.")
    if report_sid and "lesion_analysis" in findings:
        # Second review of PR #68, N7: the lesion table is derived on the server for the report's own segmentation
        # — a client table (with, without or with another `segmentation_id`) never reaches the model.
        findings["lesion_analysis"] = await server_lesion_table(report_sid)
    if "dis_assessment" in findings or (report_sid and "lesion_analysis" in findings):
        # N5: the model gets the confirmer's role and time, never the person.
        findings["dis_assessment"] = gate.without_reviewer_identity(
            await server_dis_assessment(report_sid, current_user))
        others = any(findings.get(k) for k in MEASUREMENT_FINDING_KEYS if k != "dis_assessment")
        if not (others or verified_report.renderable_volumetry(request.volumetry)
                or gate.is_evaluated(findings["dis_assessment"])):
            # A "not evaluated" DIS state is not a measurement: the model would draft from nothing (RC-034).
            raise ReportError("nothing_to_report", status.HTTP_422_UNPROCESSABLE_ENTITY,
                              "No measurement was supplied: dissemination in space was not evaluated (the segmentation "
                              "has not been confirmed by a radiologist), and nothing else was measured. A report "
                              "without measurements would be invented; run the lesion analysis first.")
    dis_evaluated = gate.is_evaluated(findings.get("dis_assessment"))
    if not dis_evaluated and isinstance(findings.get("lesion_analysis"), dict):
        # Finding 3: regions of a segmentation no radiologist confirmed are not passed to the model.
        findings["lesion_analysis"] = gate.without_region_breakdown(findings["lesion_analysis"])
    # Tenth review of PR #78, I19 (CAPA-008): "nothing to write" is decided again on what is left AFTER the route's own
    # substitutions — a block that held only an unverifiable reader decision is empty now, and a draft of the
    # limitations alone would be written from nothing
    if not verified_report.renderable(findings, request.volumetry):
        raise ReportError("nothing_to_report", status.HTTP_422_UNPROCESSABLE_ENTITY, NOTHING_TO_REPORT_DETAIL)

    try:
        result = await service.generate_report(
            template_type=request.template_type,
            findings=findings,
            volumetry=request.volumetry,
            language=request.language,
            identifiers=identifiers,
            # RC-104 (DRAFT): who asked and for which segmentation, for the audit record of every model attempt
            audit_actor=current_user,
            segmentation_id=request.segmentation_id,
            request_started=started,
        )
        # (ninth review of PR #78, finding 8: CAPA-014's format-character rule runs once, inside neutralised_model_text
        # when the draft is assembled below; the service's check applies the same rule to the comments it checks)
        # CAPA-014 (RC-066): the typed text and the names of unlisted labels join the draft here, after the
        # model, as fields of their own; they were never sent.
        unlisted = result.pop("unlisted_labels", None)
        parts = draft_parts(result["content"], request.language, request.findings, unlisted)
        notice = result.get("change_notice")
        if notice:   # CAPA-013 (sixth review, W1): the service's notice, from its validated record
            parts["ai_text"] = f"{parts['ai_text']}\n\n---\n\n> {notice}"
        result = {**result, **parts, "content": draft_text(parts, request.language)}
        return ReportResponse(**result)

    except ImplausibleMeasurement as e:
        # Ninth review of PR #78, I14: a measurement outside its plausible range is never written as a fact — the
        # request is refused (422) naming the measurement, whatever the AI comments' state. Tenth review, I16: the
        # value was computed by the server's own analysis, so the physician is asked to re-run the analysis or check
        # the segmentation (never to "correct the input"); the code and the field let the panel name the measurement.
        logger.warning("[Report] A measurement is outside its plausible range; no draft written",
                       extra={"measurement_field": e.field})
        raise ReportError("implausible_measurement", status.HTTP_422_UNPROCESSABLE_ENTITY,
                          f"A measurement computed by the segmentation analysis is outside its plausible range: "
                          f"{e.field or 'unknown'}. No draft was written; re-run the analysis or check the segmentation.",
                          {"field": e.field})
    except ProviderGuardError as e:
        # CAPA-014 (RC-065): the service refused to send; the message names categories, no identifier.
        logger.warning("[Report] Not sent: the identifier check refused the request",
                       extra={"privacy_check": "refused"})
        from app.services.brain_report_service import LabelInRecord
        code = ("patient_record_unavailable" if isinstance(e, PatientRecordUnavailable)
                else "label_in_record" if isinstance(e, LabelInRecord) else "not_sent")
        raise ReportError(code, status.HTTP_503_SERVICE_UNAVAILABLE, NOT_SENT_DETAIL.format(reason=str(e)))
    # Second review of PR #78 (F): no `except RuntimeError` any more — a missing provider key is no error of the
    # verified report (measurements-only draft, reason "not_configured"), so any RuntimeError is an internal failure
    except Exception as e:
        logger.error(f"[Report] Generation failed: {e}")
        # the class name only: an internal message never reaches the client (second review of PR #78, F)
        raise ReportError("report_failed", status.HTTP_500_INTERNAL_SERVER_ERROR,
                          f"Report generation failed ({type(e).__name__}).")


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
