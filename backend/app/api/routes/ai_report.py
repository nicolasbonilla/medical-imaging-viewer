"""
AI Report Generation API routes.

Provides endpoints for generating structured brain MRI reports
using Claude API, listing templates, and exporting reports.

@module api.routes.ai_report
"""

import re
import unicodedata

from fastapi import APIRouter, HTTPException, status, Depends
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field

from app.security import get_current_active_user
from app.security.models import User
from app.security.resource_access import authorize_segmentation_id
# PRB-003 (RC-070): the segmentation named in a DIS block is authorized like any other mask reference.
from app.security.resource_access import authorize_mask_specs
from app.services.report_payload_guard import (
    FREE_TEXT_FIELDS,
    PatientIdentifiers,
    PatientRecordUnavailable,
    ProviderGuardError,
)

from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ai/report", tags=["AI Report"])

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


def without_format_characters(text: str) -> str:
    """`text` without Unicode format characters (soft hyphen, zero-width joiners, BOM, bidirectional controls); a
    zero-width space becomes a space, so that the words it separated stay apart."""
    text = text.replace("\u200b", " ")
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


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
        description="Clinical findings. Keys: clinical_indication, technique, patient_age, "
                    "patient_sex, segmentation_labels, anomalies, additional_observations, "
                    "lesion_analysis, dis_assessment, longitudinal, zone_stats. Only measurements, "
                    "labels of the device's vocabulary, sex and a 5-year age band are sent to the AI "
                    "service; the typed text fields are added to the draft here, never sent (CAPA-014).",
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
                "en, es, de. Only the measurements, labels of the device's vocabulary, sex and a "
                "5-year age band are sent to the model provider; the typed text is added to the "
                "draft here. The request is checked against the record of the patient of "
                "`segmentation_id` before it is sent (CAPA-014). 422 when no measurement is supplied "
                "(CAPA-008); 400 when no segmentation is; 404 when the caller may not access the "
                "segmentation; 503 when the check cannot run or finds an identifier (nothing is sent).",
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

    # CAPA-014 (RC-065, HAZ-016): the patient the prompt is checked against — authorized for this
    # caller (404 otherwise, as every object route) and read from the server's own record.
    # 400, not 422: the report panel reads every 422 as "no measurements" (CAPA-008).
    if not request.segmentation_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=SUBJECT_REQUIRED_DETAIL)
    patient_id = await authorize_segmentation_id(request.segmentation_id, current_user)
    try:
        identifiers = await read_patient_identifiers(patient_id)
    except PatientRecordUnavailable as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=NOT_SENT_DETAIL.format(reason=str(e)))

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
            identifiers=identifiers,
        )
        replaced = 0
        # Finding 4 / N3: a DIS statement written by the model is replaced, in code — a BACKSTOP; the main controls
        # are the earlier layers (no regions sent, the system safety rule, no DIS or per-region template section).
        # Merge note (PR #67 + PR #68, release 2026-10-25): this check runs on the model's text only (with the
        # RC-006 disclaimer), BEFORE `draft_parts` / `draft_text` add the clinician's typed entry and the
        # application's notes, which it must never touch.
        if not dis_evaluated:
            content, replaced = gate.scrub_unevaluated_dis(result["content"], request.language)
            if replaced:
                logger.warning("[Report] DIS statements written by the model were replaced",
                               extra={"replaced_statements": replaced})
            result = {**result, "content": content}
        # CAPA-014 (RC-066): the typed text and the names of unlisted labels join the draft here, after the
        # model, as fields of their own; they were never sent.
        unlisted = result.pop("unlisted_labels", None)
        parts = draft_parts(result["content"], request.language, request.findings, unlisted)
        notice = longitudinal_notice(request.findings.get("longitudinal"), request.language)
        if notice:   # CAPA-013: appended in code, after the model, in the report language
            parts["ai_text"] = f"{parts['ai_text']}\n\n---\n\n> {notice}"
        dis_text = dis_notice(findings, request.language, replaced)
        if dis_text:   # PRB-003 (RC-070, RC-072): appended in code, after the model, in the report language
            parts["ai_text"] = f"{parts['ai_text']}\n\n---\n\n> {dis_text}"
        result = {**result, **parts, "content": draft_text(parts, request.language)}
        return ReportResponse(**result)

    except ProviderGuardError as e:
        # CAPA-014 (RC-065): the service refused to send; the message names categories, no identifier.
        logger.warning("[Report] Not sent: the identifier check refused the request",
                       extra={"privacy_check": "refused"})
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=NOT_SENT_DETAIL.format(reason=str(e)))
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
