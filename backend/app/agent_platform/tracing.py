"""
Agent tracing after the OpenTelemetry GenAI semantic conventions — PINNED to v1.37.0.

REQ-AGT-002; risk control RC-116 (no patient data, prompts or outputs in spans; content only as SHA-256;
export off by default); hazard HAZ-022. DRAFT, PENDING owner approval.

Pinned revision. ``SEMCONV_VERSION = "1.37.0"``: open-telemetry/semantic-conventions at tag v1.37.0,
docs/gen-ai/gen-ai-spans.md and docs/gen-ai/gen-ai-agent-spans.md, read 2026-11-10. Every gen_ai
attribute and operation name there is at "Development" stability (only error.type, server.address and
server.port are Stable). Later in 2026 the GenAI conventions moved to the separate
open-telemetry/semantic-conventions-genai repository, which had no release when this was written; the pin
is revisited at every re-validation (Agent_Revalidation_Protocol.md, step R-6), never silently.

What is emitted (names and kinds as in v1.37.0):
- agent run:     ``invoke_agent {gen_ai.agent.name}``, kind CLIENT; gen_ai.operation.name=invoke_agent,
                 gen_ai.provider.name (Required), gen_ai.agent.id / gen_ai.agent.name.
- model call:    ``chat {gen_ai.request.model}``, kind CLIENT; request/response model, max_tokens,
                 finish reasons, input/output token usage.
- tool call:     ``execute_tool {gen_ai.tool.name}``, kind INTERNAL; tool name, call id, type=function.
- verifier:      ``verify {verifier}``, kind INTERNAL; no GenAI convention exists, so only ``mstool.*``
                 attributes (the conventions reserve custom attributes to the producer's own namespace).
- sign-off:      ``mstool.signoff``, a new trace whose span LINKS to the run's span (W3C ids).

RC-116. ``ALLOWED_ATTRIBUTES`` is an allow-list with a validator per key: an unknown key, or a value that is
not an id, a fixed code, a count or a SHA-256, is dropped and counted (``mstool.trace.dropped_attributes``).
The Opt-In content attributes of the conventions (gen_ai.input.messages, gen_ai.output.messages,
gen_ai.system_instructions) and every later content attribute are therefore never recorded. Content
appears only as ``mstool.content.*_sha256``. An exception records its class name only. The study, the
reader and the sign-off record are named only by the audit log's keyed hash, so a trace joins the audit
trail (CAPA-015) without carrying an identifier. Export is OFF unless
``MSTOOL_AGENT_TRACE_EXPORTER=otlp-json-file`` AND ``MSTOOL_AGENT_TRACE_FILE`` are both set; there is no
network exporter in this release (sending traces to a collector is integration step P-6 and needs the
owner's data-processing decision first).

@module agent_platform.tracing
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import math
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

SEMCONV_VERSION = "1.37.0"
SEMCONV_SCHEMA_URL = "https://opentelemetry.io/schemas/1.37.0"
SEMCONV_STABILITY = "Development"
INSTRUMENTATION_SCOPE = "mstool.agent_platform"

OPERATIONS = frozenset({"chat", "create_agent", "embeddings", "execute_tool", "generate_content", "invoke_agent",
                        "text_completion"})                        # well-known values in v1.37.0
RUN_STATUSES = frozenset({"delivered", "withheld", "refused", "abstained", "failed"})
VERDICTS = frozenset({"pass", "withheld", "blocked", "not_run"})

_ID = re.compile(r"[A-Za-z0-9_.:/-]{1,128}")
_CODE = re.compile(r"[a-z0-9_.:-]{1,64}")
_ERROR = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,63}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_KEY = re.compile(r"(?:hmac|sha256):[0-9a-f]{16}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TRACE_ID = re.compile(r"[0-9a-f]{32}")
_SPAN_ID = re.compile(r"[0-9a-f]{16}")


def _is_id(v):
    return isinstance(v, str) and _ID.fullmatch(v) is not None


def _is_code(v):
    return isinstance(v, str) and _CODE.fullmatch(v) is not None


def _is_count(v):
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 10 ** 9


def _is_hash(v):
    return isinstance(v, str) and _HEX64.fullmatch(v) is not None


def _is_key(v):
    return isinstance(v, str) and _KEY.fullmatch(v) is not None


def _is_usd(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v <= 10 ** 6


def _is_codes(v):
    return isinstance(v, (tuple, list)) and 0 < len(v) <= 10 and all(_is_code(x) for x in v)


ALLOWED_ATTRIBUTES: Dict[str, Callable[[Any], bool]] = {
    # OpenTelemetry GenAI v1.37.0
    "gen_ai.operation.name": lambda v: v in OPERATIONS,
    "gen_ai.provider.name": _is_code,
    "gen_ai.agent.id": _is_id,
    "gen_ai.agent.name": _is_id,
    "gen_ai.request.model": _is_id,
    "gen_ai.request.max_tokens": _is_count,
    "gen_ai.response.model": _is_id,
    "gen_ai.response.id": _is_id,
    "gen_ai.response.finish_reasons": _is_codes,
    "gen_ai.usage.input_tokens": _is_count,
    "gen_ai.usage.output_tokens": _is_count,
    "gen_ai.tool.name": _is_id,
    "gen_ai.tool.call.id": _is_id,
    "gen_ai.tool.type": lambda v: v in ("function", "extension", "datastore"),
    "error.type": lambda v: isinstance(v, str) and _ERROR.fullmatch(v) is not None,
    # MSTool namespace
    "mstool.operation.name": lambda v: v in ("verify", "signoff"),
    "mstool.agent.registry_version": _is_id,
    "mstool.audit.request_id": _is_id,
    "mstool.study.key": _is_key,
    "mstool.content.input_sha256": _is_hash,
    "mstool.content.output_sha256": _is_hash,
    "mstool.content.tool_result_sha256": _is_hash,
    "mstool.prompt.template_sha256": _is_hash,
    "mstool.verifier.name": _is_id,
    "mstool.verifier.verdict": lambda v: v in VERDICTS,
    "mstool.verifier.withheld_count": _is_count,
    "mstool.refusal.code": _is_code,
    "mstool.run.status": lambda v: v in RUN_STATUSES,
    "mstool.run.steps": _is_count,
    "mstool.run.tool_calls": _is_count,
    "mstool.cost.usd": _is_usd,
    "mstool.untrusted.alarm_count": _is_count,
    "mstool.model.retires_on": lambda v: isinstance(v, str) and _DATE.fullmatch(v) is not None,
    "mstool.signoff.record_key": _is_key,
    "mstool.signoff.reader_key": _is_key,
    "mstool.signoff.content_sha256": _is_hash,
    "mstool.trace.dropped_attributes": _is_count,
}


def content_sha256(text: Any) -> str:
    """SHA-256 of the UTF-8 text (the only form in which content enters a span)."""
    raw = text if isinstance(text, str) else json.dumps(text, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_trace_id() -> str:
    while True:
        tid = secrets.token_hex(16)
        if int(tid, 16):
            return tid


def _new_span_id() -> str:
    while True:
        sid = secrets.token_hex(8)
        if int(sid, 16):
            return sid


def valid_trace_id(value: Any) -> bool:
    return isinstance(value, str) and _TRACE_ID.fullmatch(value) is not None and int(value, 16) != 0


@dataclass
class Span:
    name: str
    kind: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    start_ns: int
    end_ns: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "unset"
    links: List[Tuple[str, str]] = field(default_factory=list)


# ------------------------------------------------------------------ exporters
class NoopExporter:
    """The default: nothing leaves the process and nothing is kept."""

    retains = False

    def export(self, span: Span) -> None:
        return None


class InMemoryExporter:
    """Keeps finished spans in memory (tests; the eval report)."""

    retains = True

    def __init__(self):
        self.spans: List[Span] = []
        self._lock = threading.Lock()

    def export(self, span: Span) -> None:
        with self._lock:
            self.spans.append(span)


class OtlpJsonFileExporter:
    """Appends each span as one OTLP/JSON line to a local file (off unless both settings are given)."""

    retains = True

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def export(self, span: Span) -> None:
        line = json.dumps(to_otlp_json([span]), sort_keys=True)
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def exporter_from_env():
    """Off unless MSTOOL_AGENT_TRACE_EXPORTER is exactly 'otlp-json-file' AND MSTOOL_AGENT_TRACE_FILE is set."""
    if os.environ.get("MSTOOL_AGENT_TRACE_EXPORTER", "") == "otlp-json-file":
        path = os.environ.get("MSTOOL_AGENT_TRACE_FILE", "")
        if path:
            return OtlpJsonFileExporter(path)
    return NoopExporter()


# ------------------------------------------------------------------ OTLP/JSON shape
def _otlp_value(v: Any) -> Dict[str, Any]:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, (tuple, list)):
        return {"arrayValue": {"values": [_otlp_value(x) for x in v]}}
    return {"stringValue": str(v)}


_KIND = {"INTERNAL": "SPAN_KIND_INTERNAL", "CLIENT": "SPAN_KIND_CLIENT", "SERVER": "SPAN_KIND_SERVER"}
_STATUS = {"unset": "STATUS_CODE_UNSET", "ok": "STATUS_CODE_OK", "error": "STATUS_CODE_ERROR"}


def to_otlp_json(spans: Sequence[Span]) -> Dict[str, Any]:
    from app.agent_platform import PLATFORM_VERSION
    out = []
    for s in spans:
        item = {
            "traceId": s.trace_id, "spanId": s.span_id, "name": s.name, "kind": _KIND.get(s.kind, "SPAN_KIND_INTERNAL"),
            "startTimeUnixNano": str(s.start_ns), "endTimeUnixNano": str(s.end_ns),
            "attributes": [{"key": k, "value": _otlp_value(v)} for k, v in sorted(s.attributes.items())],
            "links": [{"traceId": t, "spanId": p} for t, p in s.links],
            "status": {"code": _STATUS.get(s.status, "STATUS_CODE_UNSET")},
        }
        if s.parent_span_id:
            item["parentSpanId"] = s.parent_span_id
        out.append(item)
    return {"resourceSpans": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "mstool-backend"}}]},
        "scopeSpans": [{"scope": {"name": INSTRUMENTATION_SCOPE, "version": PLATFORM_VERSION},
                        "schemaUrl": SEMCONV_SCHEMA_URL, "spans": out}],
    }]}


# ------------------------------------------------------------------ tracer
_CURRENT: contextvars.ContextVar[Optional["SpanHandle"]] = contextvars.ContextVar("mstool_agent_span", default=None)


class SpanHandle:
    """A span being recorded. ``set`` validates against the allow-list; nothing else can add data."""

    def __init__(self, tracer: "Tracer", span: Span):
        self._tracer = tracer
        self._span = span
        self._dropped = 0

    @property
    def trace_id(self) -> str:
        return self._span.trace_id

    @property
    def span_id(self) -> str:
        return self._span.span_id

    def set(self, key: str, value: Any) -> bool:
        check = ALLOWED_ATTRIBUTES.get(key)
        if check is None or not check(value):
            self._dropped += 1
            return False
        self._span.attributes[key] = tuple(value) if isinstance(value, list) else value
        return True

    def set_content_hash(self, which: str, content: Any) -> bool:
        key = {"input": "mstool.content.input_sha256", "output": "mstool.content.output_sha256",
               "tool_result": "mstool.content.tool_result_sha256"}.get(which)
        if key is None:
            self._dropped += 1
            return False
        return self.set(key, content_sha256(content))

    def fail(self, error_type: str) -> None:
        self._span.status = "error"
        self.set("error.type", error_type)

    def _finish(self) -> Span:
        if self._dropped:
            self._span.attributes["mstool.trace.dropped_attributes"] = self._dropped
        self._span.end_ns = max(self._tracer.clock_ns(), self._span.start_ns)
        if self._span.status == "unset":
            self._span.status = "ok"
        return self._span


class Tracer:
    def __init__(self, exporter=None, *, clock_ns: Callable[[], int] = time.time_ns):
        self.exporter = exporter if exporter is not None else exporter_from_env()
        self.clock_ns = clock_ns
        self.finished: List[Span] = []

    @contextmanager
    def span(self, name: str, kind: str, attributes: Optional[Dict[str, Any]] = None, *,
             trace_id: Optional[str] = None, links: Sequence[Tuple[str, str]] = (),
             new_trace: bool = False) -> Iterator[SpanHandle]:
        parent = None if new_trace else _CURRENT.get()
        if parent is not None:
            tid, parent_id = parent.trace_id, parent.span_id
        else:
            tid, parent_id = (trace_id if valid_trace_id(trace_id) else _new_trace_id()), None
        span = Span(name=name, kind=kind, trace_id=tid, span_id=_new_span_id(), parent_span_id=parent_id,
                    start_ns=self.clock_ns(),
                    links=[(t, s) for t, s in links if valid_trace_id(t) and isinstance(s, str) and _SPAN_ID.fullmatch(s)])
        handle = SpanHandle(self, span)
        for k, v in (attributes or {}).items():
            handle.set(k, v)
        token = _CURRENT.set(handle)
        try:
            yield handle
        except BaseException as exc:
            handle.fail(type(exc).__name__)
            raise
        finally:
            _CURRENT.reset(token)
            finished = handle._finish()
            try:
                self.exporter.export(finished)
            except Exception:  # noqa: BLE001 — tracing never breaks the agent
                pass
            if getattr(self.exporter, "retains", False):
                self.finished.append(finished)

    # -------------------------------------------------------------- the four span types
    def agent_span(self, agent_id: str, *, provider: str, trace_id: Optional[str] = None,
                   audit_request_id: Optional[str] = None, registry_version: Optional[str] = None,
                   study_key: Optional[str] = None):
        attrs = {"gen_ai.operation.name": "invoke_agent", "gen_ai.provider.name": provider,
                 "gen_ai.agent.id": agent_id, "gen_ai.agent.name": agent_id}
        if audit_request_id is not None:
            attrs["mstool.audit.request_id"] = audit_request_id
        if registry_version is not None:
            attrs["mstool.agent.registry_version"] = registry_version
        if study_key is not None:
            attrs["mstool.study.key"] = study_key
        name = f"invoke_agent {agent_id}" if _is_id(agent_id) else "invoke_agent"
        return self.span(name, "CLIENT", attrs, trace_id=trace_id)

    def chat_span(self, model_id: str, *, provider: str, max_tokens: Optional[int] = None):
        attrs = {"gen_ai.operation.name": "chat", "gen_ai.provider.name": provider, "gen_ai.request.model": model_id}
        if max_tokens is not None:
            attrs["gen_ai.request.max_tokens"] = max_tokens
        name = f"chat {model_id}" if _is_id(model_id) else "chat"
        return self.span(name, "CLIENT", attrs)

    def tool_span(self, tool_name: str, *, call_id: Optional[str] = None):
        attrs = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": tool_name, "gen_ai.tool.type": "function"}
        if call_id is not None:
            attrs["gen_ai.tool.call.id"] = call_id
        name = f"execute_tool {tool_name}" if _is_id(tool_name) else "execute_tool"
        return self.span(name, "INTERNAL", attrs)

    def verify_span(self, verifier_name: str, *, verdict: str, withheld: int = 0):
        attrs = {"mstool.operation.name": "verify", "mstool.verifier.name": verifier_name,
                 "mstool.verifier.verdict": verdict, "mstool.verifier.withheld_count": withheld}
        name = f"verify {verifier_name}" if _is_id(verifier_name) else "verify"
        return self.span(name, "INTERNAL", attrs)


def link_signoff(tracer: Tracer, *, run_trace_id: str, run_span_id: str, signoff_record_id: str,
                 content_sha256: str, reader_id: str, audit: Optional[Callable[[Dict[str, Any]], None]] = None
                 ) -> Dict[str, str]:
    """Record the radiologist's sign-off as a span LINKED to the agent run (a new trace: the sign-off happens
    later, in another request). The reader and the sign-off record appear only as keyed hashes; the signed
    text only as its SHA-256 (the same value the sign-off record binds)."""
    from app.agent_platform.registry import pseudonymise
    attrs = {"mstool.operation.name": "signoff", "mstool.signoff.record_key": pseudonymise(signoff_record_id),
             "mstool.signoff.reader_key": pseudonymise(reader_id), "mstool.signoff.content_sha256": content_sha256}
    with tracer.span("mstool.signoff", "INTERNAL", attrs, links=[(run_trace_id, run_span_id)], new_trace=True) as h:
        out = {"signoff_trace_id": h.trace_id, "signoff_span_id": h.span_id, "run_trace_id": run_trace_id}
    if audit is not None:
        try:
            audit({"event": "agent.signoff_linked", "outcome": "success", "code": "signoff_linked",
                   "trace_id": run_trace_id if valid_trace_id(run_trace_id) else None})
        except Exception:  # noqa: BLE001
            pass
    return out
