"""
Brain Report Generation Service using Claude API.

VERIFIED REPORT (REQ-FUNC-116, REQ-SAFE-048..051; RC-102..RC-106; HAZ-003, HAZ-013, HAZ-016, HAZ-017 — DRAFT,
PENDING owner approval). `generate_report` no longer asks the model to write the report. It runs the fixed flow of
`verified_report` (benchmark arm A3, `research/agents-benchmark` @ f3c1976): code writes every number and status from
the device's measurements; the model writes only two short comments; every answer passes the frozen claim check
(`report_claim_verifier`) or is regenerated (at most twice) and finally withheld; every attempt goes to the audit log.
The model is one of `REPORT_MODELS` (default `claude-sonnet-5-5`; the former `claude-sonnet-4-5-20250929` retires on
2026-11-30 and is refused); `REPORT_LLM_ENABLED=false` switches the model off (measurements-only report).
The former templates (`REPORT_TEMPLATES`, `_build_findings_prompt`, `dis_not_evaluated_template`, ...) were RETIRED
from the report path and are no longer in this module (third independent review of PR #78, T5): they are archived,
unchanged and NOT shipped, in docs/archive/retired_report_prompt.py, as the reference of the design the benchmark
measured (arm A0). The template ids are still accepted (`TEMPLATE_IDS`, recorded).

Generates structured radiology reports for brain MRI studies
focused on Multiple Sclerosis evaluation following international standards:
- MAGNIMS-CMSC-NAIMS 2021 consensus guidelines
- RSNA structured reporting format
- 2017 McDonald diagnostic criteria
- ACR Practice Parameter for Communication

Template ids: general, ms_activity, ms_lesion_burden, ms_comprehensive, ms_longitudinal (recorded; one verified structure).

Data sent to the model provider (CAPA-014; RC-064, RC-065, RC-066; HAZ-016):
- Measurements only (verified report, DRAFT). The model receives the measurement record that
  `verified_report` builds from the part of the structured payload (`report_payload_guard`) the report writes —
  counts, volumes, size classes, the four MAGNIMS regions and DIS only when a radiologist confirmed them, change
  candidates, brain volumes; no sex, no age band, no per-lesion value, no label typed by a user — and the
  code-written report. No free-text or user-typed field is sent; the clinician's text is added to the draft by the
  route after the model returns. The system prompt is one fixed text, `verified_report.SYSTEM_PROMPT`.
- Before the call, a detection-only check of the final prompt (the patient's own identifiers from
  the patient record, and generic identifier patterns) refuses to send on any finding; without the
  patient's record nothing is sent (fail closed).
- An earlier header stated that patient data was de-identified and that names, IDs and dates were never sent; nothing did that then (CAPA-001 §2.3, CAPA-008 finding 4) — statement withdrawn.

@module services.brain_report_service
"""

import asyncio
import copy
import inspect
import time
import uuid
from datetime import date
from functools import lru_cache
from typing import Optional, List, Dict, Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services import verified_report
from app.services.report_payload_guard import (
    UNLISTED,
    IdentifierInPrompt,
    ImplausibleMeasurement,
    PatientIdentifiers,
    PatientRecordUnavailable,
    ProviderGuardError,
    assert_no_identifiers,
    provider_payload,
    words_of,
)
from app.services.report_payload_guard import _KNOWN_FIELDS

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# RC-106 (REQ-SAFE-051; HAZ-017, HAZ-013) — DRAFT, PENDING owner approval.
# The models this version may call for the two comments, each with the request parameters it is called with
# (the configurations pre-registered for the benchmark, PREREG.md §4: thinking off, effort low). The SDK pinned in
# requirements.txt (anthropic 0.44.0) predates `thinking` and `output_config`, so they are sent as extra body fields.
# Any other id — the retiring `claude-sonnet-4-5-20250929` (2026-11-30) included — is refused: the report is
# delivered with the measurements only and the reason. Changing the model is a change of this table (change control,
# SOUP-001), never only an environment variable.
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_REPORT_MODEL = "claude-sonnet-5-5"
REPORT_MODELS: Dict[str, Dict[str, Any]] = {
    "claude-sonnet-5-5": {"params": {"thinking": {"type": "between_tools"}, "output_config": {"effort": "low"}},
                          "retires_on": None, "soup": "SOUP-BE-029"},
    "claude-haiku-5-5": {"params": {"thinking": {"type": "disabled"}, "output_config": {"effort": "low"}},
                         "retires_on": None, "soup": "SOUP-BE-030"},
}
# Ids known to be retired or retiring (Claude API dates). FOR THE LOG MESSAGE ONLY (review of PR #78, R9): what may be
# called is decided by REPORT_MODELS and its `retires_on` alone — one mechanism.
RETIRED_OR_RETIRING_MODELS: Dict[str, str] = {
    "claude-sonnet-4-5-20250929": "2026-11-30", "claude-sonnet-4-5": "2026-11-30",
    "claude-sonnet-4-20250514": "2026-06-15", "claude-3-7-sonnet-20250219": "2026-02-19",
    "claude-3-5-sonnet-20241022": "2025-10-28", "claude-3-5-sonnet-20240620": "2025-10-28",
}


def report_model_allowed(model_id: Any, today: Optional[date] = None) -> bool:
    """RC-106: True only for an id of REPORT_MODELS whose retirement date (if any) is still ahead."""
    entry = REPORT_MODELS.get(model_id) if isinstance(model_id, str) else None
    if entry is None:
        return False
    retires = entry.get("retires_on")
    return retires is None or (today or date.today()) < date.fromisoformat(retires)


class LabelInRecord(ProviderGuardError):
    """Review of PR #78, R8: a numbered placeholder of an unlisted label reached the measurement record — the record
    carries only code-chosen strings by design, so this cannot happen; if it does, nothing is sent (fail closed)."""


def _refusal_code(exc: BaseException) -> str:
    """RC-104: the audit-safe reason of a request refused before any model call (review of PR #78, R7)."""
    for cls, code in ((PatientRecordUnavailable, "patient_record_unavailable"),
                      (IdentifierInPrompt, "identifier_in_request"),
                      (ImplausibleMeasurement, "implausible_measurement"),
                      (LabelInRecord, "label_in_request")):
        if isinstance(exc, cls):
            return code
    return "privacy_check_refused"


def _failure_reason(exc: BaseException) -> str:
    """RC-106: the audit-safe reason of a provider failure (404 = the model is no longer served)."""
    name = type(exc).__name__
    if getattr(exc, "status_code", None) == 404 or name == "NotFoundError":
        return verified_report.REASON_MODEL_UNAVAILABLE
    if "Timeout" in name:
        return verified_report.REASON_TIMEOUT
    return verified_report.REASON_PROVIDER


def _block_field(block: Any, name: str) -> Any:
    return block.get(name) if isinstance(block, dict) else getattr(block, name, None)


def reply_of(message: Any) -> "verified_report.ModelReply":
    """The model's answer, read by block TYPE: only `text` blocks count (a thinking or other block — which the pinned
    SDK returns as an unvalidated object — is never read as the answer, unlike `content[0].text`)."""
    blocks = getattr(message, "content", None) or []
    text = "".join(_block_field(b, "text") or "" for b in blocks
                   if _block_field(b, "type") == "text" and isinstance(_block_field(b, "text"), str))
    usage = getattr(message, "usage", None)

    def tokens(name):
        value = getattr(usage, name, 0) if usage is not None else 0
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    stop = getattr(message, "stop_reason", None)
    model = getattr(message, "model", None)
    return verified_report.ModelReply(text=text, stop_reason=stop if isinstance(stop, str) else None,
                                      model=model if isinstance(model, str) else None,
                                      input_tokens=tokens("input_tokens"), output_tokens=tokens("output_tokens"))


class _ReportAudit:
    """RC-104 (REQ-SAFE-050): every attempt and the outcome of each report in the server audit log (stdout + the
    durable store, CAPA-015) — codes, counts, the prompt's SHA-256; never the prompt, the record or the answer."""

    def __init__(self, report_id: str, actor: Any, segmentation_id: Optional[str], template_type: str, language: str):
        self.report_id, self.actor, self.segmentation_id = report_id, actor, segmentation_id
        self.template_type, self.language = template_type, language

    def _emit(self, event_type, outcome, details, severity):
        from app.core.logging.audit import emit_audit
        role = getattr(self.actor, "role", None)
        emit_audit(event_type, outcome, user_id=getattr(self.actor, "id", None),
                   username=getattr(self.actor, "username", None), role=role, resource_type="report",
                   resource_ids={"report_id": self.report_id,
                                 **({"segmentation_id": self.segmentation_id} if self.segmentation_id else {})},
                   details={"template_type": self.template_type, "language": self.language,
                            "flow": verified_report.FLOW_CODE, **details},
                   severity=severity)

    def attempt(self, record: Dict[str, Any]) -> None:
        from app.core.logging.audit import AuditEventType, AuditOutcome, AuditSeverity
        outcome = AuditOutcome.SUCCESS if record.get("verdict") == "pass" else AuditOutcome.FAILURE
        details = {k: record.get(k) for k in ("attempt", "model_id", "model_answered", "prompt_sha256", "verdict",
                                              "rule_ids", "latency_ms", "stop_reason", "input_tokens",
                                              "output_tokens", "error") if record.get(k) is not None}
        self._emit(AuditEventType.CLINICAL_AI_REPORT_ATTEMPT, outcome, details, AuditSeverity.LOW)

    def outcome(self, result: "verified_report.FlowResult", model_id: Optional[str]) -> None:
        from app.core.logging.audit import AuditEventType, AuditOutcome, AuditSeverity
        withheld = result.interpretive == "withheld" or (result.reason not in (None, verified_report.REASON_OFF,
                                                                                verified_report.REASON_NOTHING_TO_COMMENT))
        details = {"report_outcome": result.outcome, "interpretive_text": result.interpretive,
                   "attempts": len(result.attempts), "model_id": model_id, "model_answered": result.model_answered,
                   "llm_reason": result.reason}
        self._emit(AuditEventType.CLINICAL_AI_REPORT_VERIFICATION,
                   AuditOutcome.PARTIAL if withheld else AuditOutcome.SUCCESS,
                   {k: v for k, v in details.items() if v is not None},
                   AuditSeverity.MEDIUM if withheld else AuditSeverity.LOW)

    def not_sent(self, exc: BaseException) -> None:
        """Review of PR #78, R7: a draft that ends before any model call — a privacy check refused it (denied) or it
        failed (failure) — is audited too; the reason is a code, never the message."""
        from app.core.logging.audit import AuditEventType, AuditOutcome, AuditSeverity
        refused = isinstance(exc, ProviderGuardError)
        details = {"report_outcome": "not_sent" if refused else "error", "interpretive_text": "not_sent",
                   "attempts": 0, "llm_reason": _refusal_code(exc) if refused else None,
                   "error": None if refused else type(exc).__name__}
        self._emit(AuditEventType.CLINICAL_AI_REPORT_VERIFICATION,
                   AuditOutcome.DENIED if refused else AuditOutcome.FAILURE,
                   {k: v for k, v in details.items() if v is not None}, AuditSeverity.MEDIUM)

# ─────────────────────────────────────────────────────────────────────────────
# RC-006 — risk control for HAZ-003 (AI report hallucination, severity S5).
#
# CAPA-001: the Risk Management File recorded RC-006 as "VERIFIED — disclaimer
# present in all 5 templates". It was not present in any form. This is the
# implementation.
#
# The disclaimer is applied DETERMINISTICALLY in code (see _apply_disclaimer),
# not merely requested of the model. A risk control that depends on an LLM
# choosing to comply is not a risk control: the model can silently omit it, and
# omission would be invisible. The prompt instruction below is defence in depth,
# not the control itself.
#
# Verified by: backend/tests/unit/test_rc006_report_disclaimer.py
#              (tests named test_rc006_*). Removing this control MUST turn CI red
#              — that is the CAPA-001 §5 effectiveness criterion.
# ─────────────────────────────────────────────────────────────────────────────
REPORT_DISCLAIMER_EN = (
    "> **AI-Generated — Requires Physician Review Before Clinical Action.** "
    "This draft was produced by an automated system from computed measurements. "
    "It is not a diagnosis. A qualified physician must review, correct and sign "
    "it before it is used for any clinical decision."
)
REPORT_DISCLAIMER_ES = (
    "> **Generado por IA — Requiere revisión médica antes de cualquier acción "
    "clínica.** Este borrador fue producido por un sistema automatizado a partir "
    "de mediciones calculadas. No es un diagnóstico. Un médico cualificado debe "
    "revisarlo, corregirlo y firmarlo antes de usarlo para cualquier decisión clínica."
)
REPORT_DISCLAIMER_DE = (
    "> **KI-generiert — ärztliche Überprüfung vor klinischer Verwendung "
    "erforderlich.** Dieser Entwurf wurde von einem automatisierten System aus "
    "berechneten Messwerten erstellt. Er ist keine Diagnose. Eine qualifizierte "
    "ärztliche Fachperson muss ihn vor jeder klinischen Entscheidung prüfen, "
    "korrigieren und signieren."
)

REPORT_DISCLAIMERS: Dict[str, str] = {
    "en": REPORT_DISCLAIMER_EN,
    "es": REPORT_DISCLAIMER_ES,
    "de": REPORT_DISCLAIMER_DE,
}


def _apply_disclaimer(content: str, language: str) -> str:
    """Prepend the mandatory RC-006 disclaimer to generated report content.

    Applied unconditionally to every report, in every language, on every
    template. Falls back to English for unknown languages rather than emitting
    a report with no disclaimer at all.
    """
    disclaimer = REPORT_DISCLAIMERS.get((language or "en").lower(), REPORT_DISCLAIMER_EN)
    body = (content or "").lstrip()
    # Idempotent: never stack the banner if it is somehow already present.
    if body.startswith(disclaimer):
        return body
    return f"{disclaimer}\n\n{body}"


# The template ids the route still accepts (recorded only): every one gives the same verified structure. The
# retired templates themselves are archived in docs/archive/retired_report_prompt.py (NOT shipped; third review
# of PR #78, T5).
TEMPLATE_IDS = ("general", "ms_activity", "ms_lesion_burden", "ms_comprehensive", "ms_longitudinal")


def _review_source(findings: Any) -> Optional[str]:
    """The segmentation source code of the server's DIS state (`ai_draft`, `automatic_tool`, `origin_not_recorded`),
    set by the report route from the stored segmentation; anything else: None (fixed "not confirmed" text)."""
    block = findings.get("dis_assessment") if isinstance(findings, dict) else None
    review = block.get("segmentation_review") if isinstance(block, dict) else None
    source = review.get("source") if isinstance(review, dict) else None
    return source if source in ("ai_draft", "automatic_tool", "origin_not_recorded") else None


class BrainReportService:
    """
    Generates the verified brain MRI report draft (REQ-FUNC-116, DRAFT): code writes every number and status, the
    Claude API writes two checked comments (see the module docstring and `verified_report`).

    - One verified structure for every template id (`TEMPLATE_IDS`, recorded)
    - Total brain and intracranial volume when supplied
    - Multi-language support (en, es, de)

    CAPA-014: the request is built from the part of the structured payload the report writes (measurements, the
    device's region names; no sex, no age band, no typed text) and checked against the patient's own identifiers
    before any call; without the patient's record no request is sent.
    """

    def __init__(self):
        self._client = None
        self._settings = get_settings()

    def _get_client(self):
        """Lazy-load Anthropic client."""
        if self._client is None:
            api_key = self._settings.ANTHROPIC_API_KEY
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not configured. "
                    "Set the environment variable to enable report generation."
                )
            import anthropic
            # RC-106: no SDK retry (review of PR #78, R2: a retry got a fresh full timeout, about twice the budget);
            # the flow's own regeneration and its 25 s budget for all calls of a draft are the only repetition.
            # Third review, T3: the ASYNC client (anthropic==0.44.0 has it) — awaited on the event loop, so the end
            # of the budget cancels the HTTP request itself; no worker thread is left running.
            self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)
        return self._client

    def _interpretive_text_gate(self, model_id: Any, view: Dict[str, Any]) -> Optional[str]:
        """Why the comments are not requested (a REASON_* code), or None. RC-105: the kill switch; RC-106: the model
        allow-list and retirement; no key: not configured; nothing measured: nothing to comment on."""
        if getattr(self._settings, "REPORT_LLM_ENABLED", True) is not True:
            return verified_report.REASON_OFF
        if not report_model_allowed(model_id):
            return verified_report.REASON_MODEL_NOT_ALLOWED
        if not verified_report.has_something_to_comment(view):
            return verified_report.REASON_NOTHING_TO_COMMENT
        try:
            self._get_client()          # no ANTHROPIC_API_KEY: RuntimeError (nothing is sent)
        except RuntimeError:
            return verified_report.REASON_NOT_CONFIGURED
        return None

    def _model_call(self, model_id: str) -> "verified_report.Call":
        """One provider call of the flow (RC-106): fixed parameters of the allow-list, the remaining time budget as
        timeout; any failure becomes a ProviderFailure (audit-safe).

        Third review of PR #78, T3: the service's client is the SDK's async client; its request is awaited under the
        remaining budget, so at the deadline the request itself is cancelled (no thread, no request left running).
        A synchronous client — only the offline test doubles have one — is waited for in a worker thread under the
        same bound."""
        params = REPORT_MODELS[model_id]["params"]
        max_tokens = int(self._settings.CLAUDE_MAX_TOKENS)

        async def call(system: str, messages: List[Dict[str, str]], timeout_s: float) -> verified_report.ModelReply:
            try:
                client = self._get_client()
                create = client.messages.create
                kwargs = dict(model=model_id, max_tokens=max_tokens, system=system, messages=messages,
                              extra_body=copy.deepcopy(params), timeout=max(1.0, float(timeout_s)))
                if inspect.iscoroutinefunction(inspect.unwrap(create)):
                    # the remaining budget bounds the request itself (R2, T3): wait_for cancels it at the deadline
                    message = await asyncio.wait_for(create(**kwargs), timeout=float(timeout_s))
                else:
                    message = await asyncio.wait_for(asyncio.to_thread(create, **kwargs), timeout=float(timeout_s))
            except Exception as e:  # noqa: BLE001 — every failure: the comments are not delivered, the report is
                raise verified_report.ProviderFailure(_failure_reason(e), type(e).__name__) from e
            return reply_of(message)

        return call

    async def generate_report(
        self,
        template_type: str = "general",
        findings: Optional[Dict[str, Any]] = None,
        volumetry: Optional[Dict[str, Any]] = None,
        language: str = "en",
        identifiers: Optional[PatientIdentifiers] = None,
        audit_actor: Any = None,
        segmentation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate the verified draft of a brain MRI report (REQ-FUNC-116; DRAFT, PENDING owner approval).

        Code writes every number and status from the structured payload (RC-064, RC-102); the model writes two
        comments that pass the frozen claim check or are withheld (RC-103); every attempt is audited (RC-104).

        Args:
            template_type: kept for compatibility (recorded); every template gives the same verified structure
            findings: Clinical findings dict (only the structured payload is used, CAPA-014)
            volumetry: Volumetry results dict (optional; total brain and intracranial volume are reported)
            language: Report language (en, es, de)
            identifiers: The patient's own identifiers, from the patient record (required, for the check)
            audit_actor: the authenticated user, for the audit records (RC-104)
            segmentation_id: the report's segmentation, for the audit records

        Returns:
            Dict with report_id, content, template_type, language, processing_time_ms, model, tokens_used,
            verification (flow, outcome, interpretive_text, reason, attempts, rules_failed_last_attempt)

        Raises:
            ProviderGuardError: no identifiers, or the check found one in the first request — nothing was sent
        """
        start_time = time.time()
        report_id = str(uuid.uuid4())

        if findings is None:
            findings = {}

        # Validate template (recorded only: the verified structure is the same for every template)
        if template_type not in TEMPLATE_IDS:
            template_type = "general"

        lang = verified_report.language_of(language)
        model_id = getattr(self._settings, "CLAUDE_MODEL", None)
        # RC-104: every outcome is audited — also a request refused before any model call (review of PR #78, R7)
        audit = _ReportAudit(report_id, audit_actor, segmentation_id, template_type, lang)
        try:
            # CAPA-014 (RC-065, HAZ-016): without the patient's identifiers there is nothing to check
            # against, so no request is sent.
            if not isinstance(identifiers, PatientIdentifiers):
                raise PatientRecordUnavailable("the patient's identifiers were not supplied")

            # RC-064: structured payload only — measurements, fixed labels; no free text. Second review of PR #78, C:
            # projected (and its ranges and the patient's own numbers checked) only for what the verified report
            # renders or sends; what it does not use is named "supplied but not included" and blocks nothing.
            rendered_findings, rendered_volumetry, not_included = verified_report.rendered_request(findings, volumetry)
            payload = provider_payload(rendered_findings, rendered_volumetry, identifiers)
            # RC-102: the measurement record, built by code from the payload (the DIS state by the one gate rule)
            view = verified_report.build_view(payload.findings, payload.volumetry, lang,
                                              review_source=_review_source(findings), not_included=not_included)
            # RC-066: record that the check ran and what was withheld (counts) — never the payload.
            # (second review, C: the fields the report does not render are counted here — they are not projected)
            withheld = {**payload.withheld,
                        "unknown_fields": sum(1 for k in (findings if isinstance(findings, dict) else {})
                                              if k not in _KNOWN_FIELDS),
                        "not_included_fields": len(not_included)}
            logger.info(
                "[Report] Structured payload checked before the model provider call",
                extra={"report_id": report_id, "privacy_check": "passed", "withheld": withheld},
            )

            reason = self._interpretive_text_gate(model_id, view)
            if reason is not None:
                if reason == verified_report.REASON_MODEL_NOT_ALLOWED:
                    retired = RETIRED_OR_RETIRING_MODELS.get(model_id) if isinstance(model_id, str) else None
                    logger.error("[Report] The configured model is not allowed (" +
                                 (f"retired or retiring on {retired}" if retired else "not validated or retired") +
                                 "); measurements-only report",
                                 extra={"report_id": report_id, "model": str(model_id)[:64]})
                result = verified_report.measurements_only(view, lang, reason)
            else:
                sent_text = verified_report.first_user_message(view, lang)
                # R8: the record carries only code-chosen strings; a placeholder of a request label in it would
                # mean a label of the request reached the model — nothing is sent (fail closed)
                if UNLISTED.rstrip("]") in sent_text:
                    raise LabelInRecord("a label of the request reached the measurement record")
                # RC-065: detection-only tripwire on the first request; refuses to send on any finding (nothing sent).
                assert_prompt_carries_no_identifier(sent_text, identifiers)
                result = await verified_report.run_flow(
                    view, lang, self._model_call(model_id),
                    request_meta={"model": model_id, "max_tokens": int(self._settings.CLAUDE_MAX_TOKENS),
                                  "params": REPORT_MODELS[model_id]["params"]},
                    # RC-065 on every regeneration request too: a finding stops the flow (comments withheld)
                    tripwire=lambda text: assert_prompt_carries_no_identifier(text, identifiers),
                    on_attempt=audit.attempt,
                    deadline_s=verified_report.LLM_DEADLINE_S,   # read at call time (REQ-SAFE-019)
                    first_message=sent_text)   # second review, J: built once; what is sent is what was checked
        except Exception as e:  # noqa: BLE001 — audited, then raised as before (the route answers 503 / 500)
            audit.not_sent(e)
            raise
        audit.outcome(result, model_id if reason is None else None)

        # RC-006 (HAZ-003): the disclaimer is applied here, in code, so that no generated report can leave this
        # service without it — regardless of what the model produced. See _apply_disclaimer.
        content = _apply_disclaimer(result.text, language)
        processing_time_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"[Report] Verified draft {result.outcome} in {processing_time_ms}ms",
            extra={"report_id": report_id, "report_outcome": result.outcome, "attempts": len(result.attempts),
                   "tokens_in": result.input_tokens, "tokens_out": result.output_tokens},
        )
        asked = bool(result.attempts)
        return {
            "report_id": report_id,
            "content": content,
            "template_type": template_type,
            "language": language,
            "processing_time_ms": processing_time_ms,
            "model": (result.model_answered or model_id) if asked else None,
            "tokens_used": {"input": result.input_tokens, "output": result.output_tokens} if asked else None,
            # R3: what the verified report does not include is named, never dropped silently
            "verification": {**result.summary(), "not_included": list(view.get("not_included") or [])},
            # CAPA-014: placeholder -> label as written, for the clinician's draft only. Verified report (review of
            # PR #78, R8): the record never carries a placeholder (a request would be refused above), so there is no
            # placeholder to name and no application note "sent as numbered placeholders".
            "unlisted_labels": {},
        }

    def list_templates(self) -> List[Dict[str, str]]:
        """The report the server writes (REQ-FUNC-116, DRAFT): one verified structure. The former templates' ids are
        still accepted by the route (recorded); each gives this structure."""
        return [{
            "id": "general",
            "name": "Verified measurement report",
            "description": (
                "Every number and status is written by the software from the measurements (MAGNIMS 2021 counting; "
                "dissemination in space only when a radiologist confirmed the segmentation). The AI adds two short "
                "comments that pass an automatic check against the measurements, or are withheld. Not a diagnosis."
            ),
        }]

# ─────────────────────────────────────────────────────────────────────────────
# CAPA-014 (RC-065): the device's own words — the tripwire never reports one of them on its own, so a
# patient named White does not stop "Deep White Matter", nor two of them in the order the device's text has
# them ("Deep White"). Derived ONLY from the text the device sends now: the verified report's requests
# (`verified_report.synthetic_payloads` x `verified_report.first_user_message`, every branch and language) and
# the fixed parts of a regeneration request — never from the system prompt (second review, N5) nor from the
# retired templates (second review of PR #78, G; archived outside the shipped code, third review, T5).
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _fixed_prompt_word_lists() -> tuple:
    # Verified report (DRAFT, RC-065 extended): the device's own text of its user messages — the first message (the
    # measurement record and the code-written report, in every branch and language) and the fixed parts of a
    # regeneration request. The model's own words quoted in a regeneration request are NOT device words.
    # Second review of PR #78, G: ONLY the text sent now — the retired templates' words (and their placeholder and
    # structure labels) no longer widen the list: each word on it is a word the tripwire cannot report alone.
    texts: List[str] = []
    for findings, volumetry, source in verified_report.synthetic_payloads():
        for language in verified_report.LANGUAGES:
            view = verified_report.build_view(findings, volumetry, language, review_source=source)
            texts.append(verified_report.first_user_message(view, language))
    texts.append(verified_report.REGENERATION_PREFIX + verified_report.REGENERATION_SUFFIX)
    texts.extend(verified_report.FIXED_FEEDBACK_TEXTS)
    return tuple(tuple(words_of(text)) for text in texts)


@lru_cache(maxsize=1)
def fixed_prompt_words() -> frozenset:
    """Words the device's own text can put in the user prompt."""
    return frozenset(w for words in _fixed_prompt_word_lists() for w in words)


@lru_cache(maxsize=1)
def fixed_prompt_pairs() -> frozenset:
    """Two such words in the order the device's own text has them, e.g. ("deep", "white")."""
    return frozenset(pair for words in _fixed_prompt_word_lists() for pair in zip(words, words[1:]))


def assert_prompt_carries_no_identifier(user_prompt: str, identifiers: PatientIdentifiers) -> None:
    """RC-065: the tripwire on the final prompt (raises IdentifierInPrompt; never edits the text)."""
    assert_no_identifiers(user_prompt, identifiers, fixed_prompt_words(), fixed_prompt_pairs())
