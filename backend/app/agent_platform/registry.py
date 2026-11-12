"""
Agent registry: identity, approval, tools, models, kill switch and cost caps of every agent.

REQ-AGT-001; risk controls RC-110 (fail-closed authorization), RC-111 (per-agent kill switch read at every
call), RC-112 (cost caps per study and per day), RC-115 (exact model identity); hazard HAZ-020.
DRAFT, PENDING owner approval.

Every decision is a ``Decision``; nothing here raises on a refusal, so a caller cannot forget an
``except``. A caller that ignores ``Decision.allowed`` is caught by the runtime (runtime.py), which is the
only component that calls a model or a tool. The rules:

- Unknown or malformed agent / model / tool id -> refused. Ids are matched EXACTLY: no alias, prefix,
  case folding, Unicode normalisation or whitespace trimming (a look-alike id is an unknown id).
- An agent whose approval status is not ``approved`` -> refused. Only the owner records ``approved``;
  the repository registry ships every agent as pending (a test enforces it).
- A tool with ``access: write`` is never allowed in this release; a registry that lists one for an agent
  does not validate, and an invalid registry refuses EVERYTHING.
- A model whose ``use_status`` is not ``in_use`` (a candidate is used only after the re-validation
  protocol), or whose ``retires_on`` date has come, -> refused; within
  ``RETIREMENT_WARNING_DAYS`` of that date the decision carries a warning.
- The kill switch is read again at every check; a switch store that raises means OFF.
- A model call is refused when its worst-case cost (input tokens + the full output allowance) would take
  the agent past its cap for the study or for the UTC day. The worst case is RESERVED atomically when the
  call is authorized and settled with the actual cost afterwards, so calls in flight count (CostLedger).
  An unpriced model cannot be bounded: refused.
- Tools declare their arguments (kind per argument); id-like arguments must be resource kinds.
- Every refusal is sent to the audit sink with a fixed code, never with free text or patient data; the
  study key is pseudonymised with the audit log's keyed hash first.

@module agent_platform.registry
"""

from __future__ import annotations

import contextlib
import contextvars
import math
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Protocol, Tuple

DEFAULT_REGISTRY_PATH = Path(__file__).with_name("agents.json")
RETIREMENT_WARNING_DAYS = 30
APPROVAL_STATUSES = frozenset({"approved", "pending", "planned", "suspended", "retired"})
MODEL_USE_STATUSES = frozenset({"in_use", "candidate", "withdrawn"})   # a fact, not an approval
TOOL_ACCESS = frozenset({"read", "compute", "write"})
ALLOWED_TOOL_ACCESS = frozenset({"read", "compute"})      # write tools: never in this release

_AGENT_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_MODEL_ID = re.compile(r"^[a-z0-9](?:[a-z0-9.\-]{0,62}[a-z0-9])?$")
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MAX_TOKENS_PER_CALL = 2_000_000          # nothing a single call can legitimately carry beyond this


class RefusalCode(str, Enum):
    """Fixed codes of every refusal the platform audits (no free text)."""

    REGISTRY_INVALID = "registry_invalid"
    UNKNOWN_AGENT = "unknown_agent"
    AGENT_NOT_APPROVED = "agent_not_approved"
    AGENT_SWITCHED_OFF = "agent_switched_off"
    SWITCH_UNREADABLE = "switch_unreadable"
    UNKNOWN_MODEL = "unknown_model"
    MODEL_NOT_ALLOWED = "model_not_allowed_for_agent"
    MODEL_NOT_IN_USE = "model_not_in_use"
    MODEL_RETIRED = "model_retired"
    MODEL_IDENTITY_MISMATCH = "model_identity_mismatch"
    PARAMETER_OVERRIDE = "parameter_override"
    UNKNOWN_TOOL = "unknown_tool"
    TOOL_NOT_ALLOWED = "tool_not_allowed_for_agent"
    WRITE_TOOL_REFUSED = "write_tool_refused"
    COST_UNKNOWN = "cost_unknown"
    STUDY_COST_CAP = "study_cost_cap"
    DAY_COST_CAP = "day_cost_cap"
    LIMIT_EXCEEDED = "limit_exceeded"
    STEP_LIMIT = "step_limit"
    TOOL_CALL_LIMIT = "tool_call_limit"
    OUT_OF_SCOPE_RESOURCE = "out_of_scope_resource"
    TOOL_RESULT_INVALID = "tool_result_invalid"
    TOOL_FAILED = "tool_failed"
    MODEL_CALL_FAILED = "model_call_failed"
    VERIFIER_WITHHELD = "verifier_withheld"
    VERIFIER_MISSING = "verifier_missing"
    VERIFIER_FAILED = "verifier_failed"
    OUTPUT_TRUNCATED = "output_truncated"
    MODEL_STOP_UNEXPECTED = "model_stop_unexpected"
    TOOL_ARGUMENTS_INVALID = "tool_arguments_invalid"
    MODEL_RESPONSE_INVALID = "model_response_invalid"
    MODEL_OUTPUT_EMPTY = "model_output_empty"
    RUN_CANCELLED = "run_cancelled"
    RUN_INPUT_INVALID = "run_input_invalid"
    RUN_INTERNAL_ERROR = "run_internal_error"
    RUN_ABORTED = "run_aborted"
    BACKEND_SCOPE_MISSING = "backend_scope_missing"

    def __str__(self) -> str:  # so f-strings and json.dumps(str(code)) give the bare code
        return self.value


REASONS: Dict[RefusalCode, str] = {
    RefusalCode.REGISTRY_INVALID: "the agent registry did not validate; every agent is refused",
    RefusalCode.UNKNOWN_AGENT: "no agent with this id is registered",
    RefusalCode.AGENT_NOT_APPROVED: "the agent is not approved by the owner",
    RefusalCode.AGENT_SWITCHED_OFF: "the agent's kill switch is off",
    RefusalCode.SWITCH_UNREADABLE: "the agent's kill switch could not be read; treated as off",
    RefusalCode.UNKNOWN_MODEL: "no model with this exact id is registered",
    RefusalCode.MODEL_NOT_ALLOWED: "the model is not on this agent's allow-list",
    RefusalCode.MODEL_NOT_IN_USE: "the model is not in use (a candidate is used only after re-validation)",
    RefusalCode.MODEL_RETIRED: "the model's retirement date has come",
    RefusalCode.MODEL_IDENTITY_MISMATCH: "the provider answered with a different model than requested",
    RefusalCode.PARAMETER_OVERRIDE: "a request tried to change a parameter fixed by the registry",
    RefusalCode.UNKNOWN_TOOL: "no tool with this name is registered",
    RefusalCode.TOOL_NOT_ALLOWED: "the tool is not on this agent's allow-list",
    RefusalCode.WRITE_TOOL_REFUSED: "write tools are never allowed",
    RefusalCode.COST_UNKNOWN: "the cost of the call cannot be bounded",
    RefusalCode.STUDY_COST_CAP: "the call would pass the agent's cost cap for this study",
    RefusalCode.DAY_COST_CAP: "the call would pass the agent's cost cap for the day",
    RefusalCode.LIMIT_EXCEEDED: "the call exceeds a size limit of the agent",
    RefusalCode.STEP_LIMIT: "the run reached its step limit; nothing is delivered",
    RefusalCode.TOOL_CALL_LIMIT: "the run reached its tool-call limit; nothing is delivered",
    RefusalCode.OUT_OF_SCOPE_RESOURCE: "the call references a resource outside the run's study",
    RefusalCode.TOOL_RESULT_INVALID: "the tool result failed validation",
    RefusalCode.TOOL_FAILED: "the tool failed",
    RefusalCode.MODEL_CALL_FAILED: "the model call failed",
    RefusalCode.VERIFIER_WITHHELD: "the verifier withheld the output",
    RefusalCode.VERIFIER_MISSING: "the agent requires a verifier and none was supplied",
    RefusalCode.VERIFIER_FAILED: "the verifier failed; nothing is delivered",
    RefusalCode.OUTPUT_TRUNCATED: "the model's output was cut at a token limit; nothing is delivered",
    RefusalCode.MODEL_STOP_UNEXPECTED: "the model stopped for a reason other than a normal end; nothing is delivered",
    RefusalCode.TOOL_ARGUMENTS_INVALID: "the tool call does not match the tool's declared arguments",
    RefusalCode.MODEL_RESPONSE_INVALID: "the provider's response does not have the expected shape; nothing is delivered",
    RefusalCode.MODEL_OUTPUT_EMPTY: "the model returned no text; nothing is delivered",
    RefusalCode.RUN_CANCELLED: "the run was cancelled; nothing is delivered",
    RefusalCode.RUN_INPUT_INVALID: "the run's scope or untrusted inputs are not well formed; nothing is run",
    RefusalCode.RUN_INTERNAL_ERROR: "the platform failed during the run; nothing is delivered",
    RefusalCode.RUN_ABORTED: "the run was aborted by the process; nothing is delivered",
    RefusalCode.BACKEND_SCOPE_MISSING: "the agent's tools need the study-scoped capability the backend issues for "
                                       "the run, and the run has none",
}

# Codes of a run that FAILED (the model, a tool or the verifier did not work) as opposed to one the platform
# REFUSED: failures are audited as failures, refusals as denials (review of PR #79, finding 8).
FAILURE_CODES = frozenset({RefusalCode.MODEL_CALL_FAILED, RefusalCode.TOOL_FAILED, RefusalCode.VERIFIER_FAILED,
                           RefusalCode.OUTPUT_TRUNCATED, RefusalCode.MODEL_STOP_UNEXPECTED,
                           RefusalCode.MODEL_RESPONSE_INVALID, RefusalCode.MODEL_OUTPUT_EMPTY,
                           RefusalCode.RUN_INTERNAL_ERROR, RefusalCode.RUN_ABORTED})

# Fourth review of PR #79, finding 7: the audit event types the platform writes, ONE record per run.
# - agent.decision        a registry decision taken OUTSIDE a run (a direct check by a caller); inside a run
#                         decisions are not recorded on their own — the run record carries the final code;
# - agent.run             exactly one per run: outcome success / denied / failure / cancelled, the final code,
#                         agent, model (when one was chosen), tool (when the run stopped at a tool call),
#                         pseudonymised study, trace id, actor; the server log reason is "agent.run:<code>";
# - agent.signoff_linked  the radiologist's sign-off linked to the run's trace.
# "agent.consultation" (fifth review of PR #81, F4): a run of a code-only agent (the single quality gate) whose
# decision releases no AI output; audited as a consultation, never as an AI run.
AUDIT_EVENT_TYPES = frozenset({"agent.decision", "agent.run", "agent.signoff_linked", "agent.consultation"})
_IN_RUN: "contextvars.ContextVar[bool]" = contextvars.ContextVar("mstool_agent_in_run", default=False)


@contextlib.contextmanager
def within_run():
    """Inside a run the registry's own decisions are not audited separately (one record per run)."""
    token = _IN_RUN.set(True)
    try:
        yield
    finally:
        _IN_RUN.reset(token)


def retirement_state(retires_on, today) -> Tuple[str, Optional[int]]:
    """The ONE retirement rule (fourth review, finding 10): ("retired" | "warning" | "ok", days left)."""
    if retires_on is None:
        return "ok", None
    days = (retires_on - today).days
    if days <= 0:
        return "retired", days
    return ("warning" if days <= RETIREMENT_WARNING_DAYS else "ok"), days


@dataclass(frozen=True)
class Decision:
    allowed: bool
    code: str
    reason: str
    warnings: Tuple[str, ...] = ()
    reservation: Optional[str] = None      # a model-call authorization reserves its worst-case cost

    @staticmethod
    def ok(warnings: Iterable[str] = (), reservation: Optional[str] = None) -> "Decision":
        return Decision(True, "ok", "allowed", tuple(warnings), reservation)

    @staticmethod
    def refuse(code: RefusalCode) -> "Decision":
        return Decision(False, code, REASONS[code])


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    provider: str
    api_version: str
    retires_on: Optional[date]
    use_status: str
    price_input_per_mtok: Optional[float]
    price_output_per_mtok: Optional[float]


# Argument kinds a tool may declare (review of PR #79, finding 5). Resource kinds are scope-checked; every
# other kind is type-checked; nested ``object`` / ``array`` values are walked and any id-like key in them is
# scope-checked too.
RESOURCE_KINDS = frozenset({"resource_id", "optional_resource_id", "resource_ids"})
VALUE_KINDS = frozenset({"string", "integer", "number", "boolean", "object", "array"})
# Fifth review of PR #79, finding 7: a declared argument is REQUIRED unless its kind starts with "optional_"
# (bound to the real functions: optional exactly when the parameter has a default).
ARGUMENT_KINDS = RESOURCE_KINDS | VALUE_KINDS | frozenset("optional_" + k for k in VALUE_KINDS)
OUTPUT_TYPES = frozenset({"object", "array"})
MCP_SERVERS = frozenset({"ms-clinical-mcp", "imaging-mcp"})


def is_id_like(name: Any, *, locations: bool = True) -> bool:
    """A key that names a resource: id, ids, *_id, *_ids and, unless ``locations`` is False, *path / *uri / *url."""
    if not isinstance(name, str):
        return False
    n = name.lower()
    if n in ("id", "ids") or n.endswith("_id") or n.endswith("_ids"):
        return True
    return locations and (n.endswith("path") or n.endswith("uri") or n.endswith("url"))


@dataclass(frozen=True)
class ToolEntry:
    name: str
    access: str
    arguments: Tuple[Tuple[str, str], ...] = ()          # (argument, kind), as declared in the registry
    # Fifth review of PR #79 (structural finding, a): the tool's TYPED OUTPUT schema (agents.json "output").
    result_exempt_keys: Tuple[str, ...] = ()             # id-like result keys that name no resource (e.g. report_id)
    result_resource_keys: Tuple[str, ...] = ()           # result keys whose values ARE resource ids (real schema)
    result_actor_keys: Tuple[str, ...] = ()              # result keys that name PEOPLE (an actor-id string only)
    output_type: str = "object"

    def definition(self) -> Dict[str, Any]:
        """What a provider adapter sends for this tool, as far as the registry knows it (finding 4)."""
        return {"name": self.name, "access": self.access, "arguments": dict(self.arguments),
                "output": {"type": self.output_type, "resource_fields": list(self.result_resource_keys),
                           "actor_fields": list(self.result_actor_keys), "exempt_fields": list(self.result_exempt_keys)}}

    @property
    def scope_arguments(self) -> Tuple[str, ...]:
        return tuple(name for name, kind in self.arguments if kind in RESOURCE_KINDS)

    def kind(self, argument: str) -> Optional[str]:
        return dict(self.arguments).get(argument)


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    purpose: str
    approval_status: str
    approval_ref: str
    allowed_models: Tuple[str, ...]
    allowed_tools: FrozenSet[str]
    cost_cap_per_study_usd: float
    cost_cap_per_day_usd: float
    max_steps: int
    max_tool_calls: int
    max_tool_result_bytes: int
    max_input_tokens: int
    max_output_tokens: int
    parameters: Tuple[Tuple[str, Any], ...] = field(default=())
    requires_verifier: bool = False
    requires_backend_scope: bool = False      # RC-121: its tools reach the backend only with the run's capability

    def parameter(self, name: str, default=None):
        return dict(self.parameters).get(name, default)


# ------------------------------------------------------------------ kill switches
class KillSwitches(Protocol):
    def is_on(self, agent_id: str) -> bool: ...


class EnvKillSwitches:
    """Kill switches read from the environment at EVERY call (Cloud Run: a new revision changes them).

    FAIL CLOSED (review of PR #79, finding 2): an agent is on only when BOTH the global switch
    ``MSTOOL_AGENTS_SWITCH`` and its own ``MSTOOL_AGENT_SWITCH__<AGENT_ID>`` (id upper-cased, ``-`` -> ``_``)
    read ``on`` once surrounding whitespace is removed and case is ignored. Absent, empty, ``off``, ``OFF``,
    ``false``, ``0``, ``yes``, ``true``, ``1`` or anything else is OFF.
    """

    GLOBAL = "MSTOOL_AGENTS_SWITCH"

    @staticmethod
    def variable(agent_id: str) -> str:
        return "MSTOOL_AGENT_SWITCH__" + agent_id.upper().replace("-", "_")

    @staticmethod
    def _on(value: Optional[str]) -> bool:
        return isinstance(value, str) and value.strip().lower() == "on"

    def is_on(self, agent_id: str) -> bool:
        return self._on(os.environ.get(self.GLOBAL)) and self._on(os.environ.get(self.variable(agent_id)))


class InMemoryKillSwitches:
    """Kill switches held in memory (tests, and a future admin store); counts its reads."""

    def __init__(self, initial: Optional[Mapping[str, bool]] = None):
        self._on = dict(initial or {})
        self._lock = threading.Lock()
        self.reads = 0

    def set(self, agent_id: str, on: bool) -> None:
        with self._lock:
            self._on[agent_id] = bool(on)

    def is_on(self, agent_id: str) -> bool:
        with self._lock:
            self.reads += 1
            return self._on.get(agent_id, False) is True


# ------------------------------------------------------------------ cost ledger
class CostLedger(Protocol):
    """Spend per (agent, study) and per (agent, UTC day), reserved and settled.

    Review of PR #79, finding 3: a model call RESERVES its worst-case cost before it is made, in one atomic
    check-and-add against both caps, and is SETTLED with its actual cost afterwards; calls in flight
    therefore count against the caps. A persistent, multi-instance ledger (Integration_Plan.md, P-5) must
    provide the same contract: (1) ``reserve`` as one transaction that reads both totals (settled plus
    reserved), compares them with the caps and writes the reservation — e.g. a Firestore transaction over
    one document per (agent, study) and one per (agent, day); (2) a reservation expiry, so the worst case
    of an instance that died mid-call stays charged until it is reconciled, never silently freed; (3) an
    idempotent ``settle`` keyed by the reservation id. Until then the in-memory ledger bounds ONE
    instance: with N Cloud Run instances the effective cap is N times the configured cap."""

    def totals(self, agent_id: str, study_key: str, day: str) -> Tuple[float, float]: ...

    def reserve(self, agent_id: str, study_key: str, day: str, usd: float, study_cap: float,
                day_cap: float) -> Tuple[Optional[str], Optional["RefusalCode"]]: ...

    def settle(self, reservation_id: str, usd: Optional[float]) -> bool: ...

    def add(self, agent_id: str, study_key: str, day: str, usd: float) -> None: ...


class InMemoryCostLedger:
    """The CostLedger contract in memory, for one instance (lost on restart)."""

    def __init__(self):
        self._study: Dict[Tuple[str, str], float] = {}
        self._day: Dict[Tuple[str, str], float] = {}
        self._reservations: Dict[str, Tuple[str, str, str, float]] = {}
        self._lock = threading.Lock()
        self.overruns = 0

    def totals(self, agent_id: str, study_key: str, day: str) -> Tuple[float, float]:
        with self._lock:
            return self._study.get((agent_id, study_key), 0.0), self._day.get((agent_id, day), 0.0)

    def _apply(self, agent_id: str, study_key: str, day: str, usd: float) -> None:
        self._study[(agent_id, study_key)] = self._study.get((agent_id, study_key), 0.0) + usd
        self._day[(agent_id, day)] = self._day.get((agent_id, day), 0.0) + usd

    def add(self, agent_id: str, study_key: str, day: str, usd: float) -> None:
        with self._lock:
            self._apply(agent_id, study_key, day, usd)

    def reserve(self, agent_id, study_key, day, usd, study_cap, day_cap):
        with self._lock:                                   # check and add in ONE critical section
            if self._study.get((agent_id, study_key), 0.0) + usd > study_cap + 1e-12:
                return None, RefusalCode.STUDY_COST_CAP
            if self._day.get((agent_id, day), 0.0) + usd > day_cap + 1e-12:
                return None, RefusalCode.DAY_COST_CAP
            rid = uuid.uuid4().hex
            self._reservations[rid] = (agent_id, study_key, day, usd)
            self._apply(agent_id, study_key, day, usd)
            return rid, None

    def open_reservations(self) -> int:
        """Reservations not yet settled (a run that ended, failed or was cancelled leaves none)."""
        with self._lock:
            return len(self._reservations)

    def settle(self, reservation_id: str, usd: Optional[float]) -> bool:
        """Charge the actual cost. Fifth review of PR #79, finding 4: returns True (and counts it) when the actual
        cost EXCEEDED the reserved worst case — it was spent, so it is charged in full; the totals may then pass a
        cap, and the next reservation is refused."""
        with self._lock:
            entry = self._reservations.pop(reservation_id, None)
            if entry is None:
                raise ValueError("unknown or already settled reservation")
            agent_id, study_key, day, reserved = entry
            if usd is None:                                # the actual cost is unknown: the worst case stays
                return False
            self._apply(agent_id, study_key, day, usd - reserved)
            if usd > reserved + 1e-12:
                self.overruns += 1
                return True
            return False


# ------------------------------------------------------------------ audit
AuditSink = Callable[[Dict[str, Any]], None]
AUDIT_EVENT_KEYS = frozenset({"event", "outcome", "agent_id", "code", "model_id", "tool", "study_key",
                              "trace_id", "registry_version", "reason"})


def pseudonymise(value: Optional[str]) -> Optional[str]:
    """The audit log's keyed hash of an identifier (same key, so traces and audit records join)."""
    if value is None:
        return None
    try:
        from app.core.logging.audit import keyed_hash
        return "hmac:" + keyed_hash(str(value))
    except Exception:  # pragma: no cover — the audit module always imports in the backend
        from app.agent_platform.hashing import sha256_text
        return "sha256:" + sha256_text(str(value))[:16]


def reader_key(reader_id: str) -> str:
    """The ONE pseudonym of a reader (third review of PR #79, finding 6): oversight records and the sign-off span
    use it, so the two join."""
    return pseudonymise(f"reader:{reader_id}")


def draft_key(draft_id: str) -> str:
    return pseudonymise(f"draft:{draft_id}")


# Third review of PR #79, finding 4: who an agent run acts for. The server audit log keeps every record of an
# authenticated actor durably and budgets only ANONYMOUS records (CAPA-015, review m9: 30 per 60 s per source);
# an agent event sent without an actor was anonymous and could be dropped under load. The runtime now sets the
# authenticated clinician (and the request) for the run; a run without a user (a job) acts as SYSTEM_ACTOR, a
# fixed service identity, so a Class C agent record is never anonymous and never budgeted away.
@dataclass(frozen=True)
class AuditActor:
    user_id: str
    username: Optional[str] = None
    role: Optional[str] = None
    request: Any = None


SYSTEM_ACTOR = AuditActor(user_id="system:agent-platform", username=None, role="system")
_ACTOR: "contextvars.ContextVar[Optional[AuditActor]]" = contextvars.ContextVar("mstool_agent_actor", default=None)


@contextlib.contextmanager
def audit_actor(actor: Optional[AuditActor]):
    """The actor every audit record of the enclosed run names (the run's context; worker threads inherit it)."""
    token = _ACTOR.set(actor if isinstance(actor, AuditActor) and actor.user_id else SYSTEM_ACTOR)
    try:
        yield
    finally:
        _ACTOR.reset(token)


def current_actor() -> AuditActor:
    return _ACTOR.get() or SYSTEM_ACTOR


def default_audit_sink(event: Dict[str, Any]) -> None:
    """Forward an agent-platform event to the server audit log (CAPA-015 trail) as the run's actor. Never raises."""
    try:
        from app.core.logging.audit import AuditEventType, AuditOutcome, emit_audit
        outcome = {"denied": AuditOutcome.DENIED, "success": AuditOutcome.SUCCESS}.get(
            event.get("outcome"), AuditOutcome.FAILURE)
        ids = {k: event[k] for k in ("agent_id", "model_id", "tool", "trace_id", "study_key") if event.get(k)}
        actor = current_actor()
        etype = (AuditEventType.QUALITY_GATE_CONSULTATION if event.get("event") == "agent.consultation"
                 else AuditEventType.CLINICAL_AI_RUN)
        emit_audit(etype, outcome, request=actor.request, user_id=actor.user_id,
                   username=actor.username, role=actor.role,
                   details=event.get("details"),   # G31 (eighth review of PR #81): structured, never cut
                   # fourth review of PR #79, finding 7: the reason is "<event type>:<code>", so the server log
                   # keeps which record of AUDIT_EVENT_TYPES this is (e.g. "agent.run:agent_not_approved")
                   reason=f"{event.get('event', 'agent.decision')}:{event.get('code', 'unknown')}"[:64],
                   resource_type="agent_run", resource_ids=ids)
    except Exception:  # noqa: BLE001 — auditing never breaks the caller
        pass


def _plain_details(details: Any) -> Optional[Dict[str, Any]]:
    """Structured audit details: short keys with strings, booleans, None or lists of short strings — nothing else
    (no free text from a request reaches the trail)."""
    if not isinstance(details, dict):
        return None
    ok = lambda v: v is None or isinstance(v, bool) or (isinstance(v, str) and len(v) <= 64)  # noqa: E731
    out = {}
    for k, v in details.items():
        if not isinstance(k, str) or len(k) > 32:
            continue
        if ok(v):
            out[k] = v
        elif isinstance(v, (list, tuple)) and all(isinstance(x, str) and len(x) <= 64 for x in v) and len(v) <= 32:
            out[k] = list(v)
    return out or None


_UNSET = object()
_MALFORMED = object()          # an id that was given but is not a string (e.g. None as an agent id)


def _safe_id(value: Any, pattern: re.Pattern) -> Optional[str]:
    """The id when well formed (matched whole: a trailing newline is not accepted); "invalid" when malformed;
    absent (None) when not applicable — a run that never chose a model has no model id, not an invalid one."""
    if value is _UNSET or value is None:
        return None
    return value if isinstance(value, str) and pattern.fullmatch(value) else "invalid"


# ------------------------------------------------------------------ registry
class AgentRegistry:
    """The validated registry plus the switches, ledger, audit sink and clock it decides with."""

    def __init__(self, data: Mapping[str, Any], *, switches: Optional[KillSwitches] = None,
                 ledger: Optional[CostLedger] = None, audit: Optional[AuditSink] = None,
                 clock: Optional[Callable[[], datetime]] = None):
        self._switches = switches if switches is not None else EnvKillSwitches()
        self._ledger = ledger if ledger is not None else InMemoryCostLedger()
        self._audit = audit if audit is not None else default_audit_sink
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.errors: List[str] = []
        self.version = str(data.get("registry_version", "unknown")) if isinstance(data, Mapping) else "unknown"
        self._models: Dict[str, ModelEntry] = {}
        self._tools: Dict[str, ToolEntry] = {}
        self._agents: Dict[str, AgentSpec] = {}
        try:
            self._load(data)
        except Exception as exc:  # noqa: BLE001 — any malformed shape fails closed
            self.errors.append(f"registry could not be read: {type(exc).__name__}")
        self.valid = not self.errors
        if not self.valid:
            self._models, self._tools, self._agents = {}, {}, {}

    @classmethod
    def load(cls, path: Path = DEFAULT_REGISTRY_PATH, **kwargs) -> "AgentRegistry":
        import json
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — unreadable registry: fail closed
            data = {}
        return cls(data, **kwargs)

    # -------------------------------------------------------------- validation
    def _load(self, data: Mapping[str, Any]) -> None:
        err = self.errors.append
        for section in ("models", "tools", "agents"):
            if not isinstance(data.get(section), Mapping) or not data.get(section):
                err(f"section '{section}' missing or empty")
        if self.errors:
            return
        for mid, m in data["models"].items():
            if not isinstance(mid, str) or not _MODEL_ID.fullmatch(mid):
                err(f"model id not well formed: {mid!r}")
                continue
            if m.get("use_status") not in MODEL_USE_STATUSES:
                err(f"model {mid}: use_status must be one of {sorted(MODEL_USE_STATUSES)}")
                continue
            retires = m.get("retires_on")
            if retires is not None and not (isinstance(retires, str) and _DATE.fullmatch(retires)):
                err(f"model {mid}: retires_on must be YYYY-MM-DD or null")
                continue
            price = m.get("price_usd_per_mtok") or {}
            pin, pout = price.get("input"), price.get("output")
            for p in (pin, pout):
                if p is not None and (not isinstance(p, (int, float)) or isinstance(p, bool) or p < 0
                                      or not math.isfinite(p)):
                    err(f"model {mid}: price must be a non-negative number")
            self._models[mid] = ModelEntry(
                model_id=mid, provider=str(m.get("provider", "")), api_version=str(m.get("api_version", "")),
                retires_on=date.fromisoformat(retires) if retires else None,
                use_status=m["use_status"],
                price_input_per_mtok=float(pin) if pin is not None else None,
                price_output_per_mtok=float(pout) if pout is not None else None)
        for name, t in data["tools"].items():
            if not isinstance(name, str) or not _TOOL_NAME.fullmatch(name):
                err(f"tool name not well formed: {name!r}")
                continue
            if t.get("access") not in TOOL_ACCESS:
                err(f"tool {name}: access must be one of {sorted(TOOL_ACCESS)}")
                continue
            args = t.get("arguments")
            if not isinstance(args, Mapping) or not all(isinstance(k, str) and v in ARGUMENT_KINDS
                                                         for k, v in args.items()):
                err(f"tool {name}: arguments must map each argument to one of {sorted(ARGUMENT_KINDS)}")
                continue
            bad_ids = [k for k, v in args.items() if is_id_like(k) and v not in RESOURCE_KINDS]
            if bad_ids:
                err(f"tool {name}: id-like arguments {bad_ids} must be declared as resource kinds")
                continue
            if "result_exempt_keys" in t or "result_resource_keys" in t:
                err(f"tool {name}: declare its result fields in its typed 'output' schema only")
                continue
            out = t.get("output")
            if out is None and t["access"] == "write":
                out = {"type": "object", "resource_fields": [], "actor_fields": [], "exempt_fields": []}
            fields = ("resource_fields", "actor_fields", "exempt_fields")
            if (not isinstance(out, Mapping) or out.get("type") not in OUTPUT_TYPES
                    or set(out) - {"type", *fields, "$comment"}
                    or not all(isinstance(out.get(f), list) and all(isinstance(k, str) and k for k in out[f])
                               for f in fields)):
                err(f"tool {name}: a typed 'output' schema is required (type object|array; resource_fields, "
                    f"actor_fields and exempt_fields as lists of keys)")
                continue
            if set(out["actor_fields"]) & set(out["resource_fields"]):
                err(f"tool {name}: a field cannot be both a resource and an actor")
                continue
            self._tools[name] = ToolEntry(name=name, access=t["access"], arguments=tuple(sorted(args.items())),
                                          result_exempt_keys=tuple(out["exempt_fields"]),
                                          result_resource_keys=tuple(out["resource_fields"]),
                                          result_actor_keys=tuple(out["actor_fields"]), output_type=out["type"])
        for aid, a in data["agents"].items():
            if not isinstance(aid, str) or not _AGENT_ID.fullmatch(aid):
                err(f"agent id not well formed: {aid!r}")
                continue
            approval = a.get("approval") or {}
            if approval.get("status") not in APPROVAL_STATUSES:
                err(f"agent {aid}: approval.status must be one of {sorted(APPROVAL_STATUSES)}")
            models = a.get("allowed_models")
            tools = a.get("allowed_tools")
            # Seventh review of PR #79 (R5): the assistant's servers never reach the backend without a scope (the
            # backend refuses it), so an agent with tools on them MUST declare requires_backend_scope: true.
            on_mcp = [n for n in (tools or []) if isinstance(data["tools"].get(n), Mapping)
                      and data["tools"][n].get("server") in MCP_SERVERS]
            if on_mcp and a.get("requires_backend_scope") is not True:
                err(f"agent {aid}: tools {on_mcp} run on the assistant's MCP servers; requires_backend_scope must be true")
            if not isinstance(models, list) or not isinstance(tools, list):
                err(f"agent {aid}: allowed_models and allowed_tools must be lists")
                continue
            for mid in models:
                if mid not in self._models:
                    err(f"agent {aid}: allowed model {mid!r} is not registered")
            for name in tools:
                if name not in self._tools:
                    err(f"agent {aid}: allowed tool {name!r} is not registered")
                elif self._tools[name].access not in ALLOWED_TOOL_ACCESS:
                    err(f"agent {aid}: tool {name!r} has {self._tools[name].access} access; write tools are "
                        f"never allowed")
            caps = a.get("cost_cap_usd")
            limits = a.get("limits")
            if not isinstance(caps, Mapping) or not isinstance(limits, Mapping):
                err(f"agent {aid}: cost_cap_usd and limits are required")
                continue
            values = {}
            for key in ("per_study", "per_day"):
                v = caps.get(key)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0:
                    err(f"agent {aid}: cost_cap_usd.{key} must be a non-negative number")
                values[key] = v
            for key in ("max_steps", "max_tool_calls", "max_tool_result_bytes", "max_input_tokens",
                        "max_output_tokens"):
                v = limits.get(key)
                if not isinstance(v, int) or isinstance(v, bool) or v < 1 or v > MAX_TOKENS_PER_CALL:
                    err(f"agent {aid}: limits.{key} must be a positive integer")
                values[key] = v
            params = a.get("parameters") or {}
            if not isinstance(params, Mapping):
                err(f"agent {aid}: parameters must be an object")
                params = {}
            if self.errors:
                continue
            self._agents[aid] = AgentSpec(
                agent_id=aid, purpose=str(a.get("purpose", "")), approval_status=approval["status"],
                approval_ref=str(approval.get("ref", "")), allowed_models=tuple(models),
                allowed_tools=frozenset(tools), cost_cap_per_study_usd=float(values["per_study"]),
                cost_cap_per_day_usd=float(values["per_day"]), max_steps=values["max_steps"],
                max_tool_calls=values["max_tool_calls"], max_tool_result_bytes=values["max_tool_result_bytes"],
                max_input_tokens=values["max_input_tokens"], max_output_tokens=values["max_output_tokens"],
                parameters=tuple(sorted(params.items())), requires_verifier=a.get("requires_verifier") is True,
                requires_backend_scope=a.get("requires_backend_scope") is True)

    # -------------------------------------------------------------- lookups
    def agent(self, agent_id: str) -> Optional[AgentSpec]:
        return self._agents.get(agent_id) if isinstance(agent_id, str) else None

    def model(self, model_id: str) -> Optional[ModelEntry]:
        return self._models.get(model_id) if isinstance(model_id, str) else None

    def tool(self, name: str) -> Optional[ToolEntry]:
        return self._tools.get(name) if isinstance(name, str) else None

    def today(self) -> date:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc).date()

    # -------------------------------------------------------------- audit
    def audit(self, outcome: str, code: str, *, agent_id: Any = _UNSET, model_id: Any = _UNSET, tool: Any = _UNSET,
              study_key: Optional[str] = None, trace_id: Optional[str] = None, event: str = "agent.decision",
              details: Optional[Dict[str, Any]] = None) -> None:
        record = {
            "event": event, "outcome": outcome, "code": str(code),
            "agent_id": _safe_id(agent_id, _AGENT_ID),
            "model_id": _safe_id(model_id, _MODEL_ID),
            "tool": _safe_id(tool, _TOOL_NAME),
            "study_key": pseudonymise(study_key) if study_key is not None else None,
            "trace_id": trace_id if isinstance(trace_id, str) and re.fullmatch(r"[0-9a-f]{32}", trace_id) else None,
            "registry_version": self.version[:64],
            "reason": REASONS.get(code) if isinstance(code, RefusalCode) else None,
            # eighth review of PR #81 (G31): structured fields (codes, visit labels, booleans), never truncated
            "details": _plain_details(details),
        }
        record = {k: v for k, v in record.items() if v is not None}
        try:
            self._audit(record)
        except Exception:  # noqa: BLE001 — an audit failure never turns a refusal into a permission
            pass

    def _refuse(self, code: RefusalCode, **ctx) -> Decision:
        if not _IN_RUN.get():                     # inside a run, the run's single record carries the code
            self.audit("denied", code, **ctx)
        return Decision.refuse(code)

    # -------------------------------------------------------------- checks
    def check_agent(self, agent_id: Any, *, trace_id: Optional[str] = None) -> Decision:
        """Known, approved and switched on — the switch is read now, at every call (RC-111)."""
        shown = _MALFORMED if agent_id is None else agent_id      # a missing agent id is audited as "invalid"
        if not self.valid:
            return self._refuse(RefusalCode.REGISTRY_INVALID, agent_id=shown, trace_id=trace_id)
        spec = self.agent(agent_id) if isinstance(agent_id, str) and _AGENT_ID.fullmatch(agent_id) else None
        if spec is None:
            return self._refuse(RefusalCode.UNKNOWN_AGENT, agent_id=shown, trace_id=trace_id)
        if spec.approval_status != "approved":
            return self._refuse(RefusalCode.AGENT_NOT_APPROVED, agent_id=agent_id, trace_id=trace_id)
        try:
            on = self._switches.is_on(agent_id) is True
        except Exception:  # noqa: BLE001 — unreadable switch = off
            return self._refuse(RefusalCode.SWITCH_UNREADABLE, agent_id=agent_id, trace_id=trace_id)
        if not on:
            return self._refuse(RefusalCode.AGENT_SWITCHED_OFF, agent_id=agent_id, trace_id=trace_id)
        return Decision.ok()

    def check_model(self, agent_id: Any, model_id: Any, *, trace_id: Optional[str] = None) -> Decision:
        d = self.check_agent(agent_id, trace_id=trace_id)
        if not d.allowed:
            return d
        entry = self.model(model_id) if isinstance(model_id, str) and _MODEL_ID.fullmatch(model_id) else None
        if entry is None:
            return self._refuse(RefusalCode.UNKNOWN_MODEL, agent_id=agent_id, model_id=model_id, trace_id=trace_id)
        if model_id not in self._agents[agent_id].allowed_models:
            return self._refuse(RefusalCode.MODEL_NOT_ALLOWED, agent_id=agent_id, model_id=model_id,
                                trace_id=trace_id)
        if entry.use_status != "in_use":
            return self._refuse(RefusalCode.MODEL_NOT_IN_USE, agent_id=agent_id, model_id=model_id,
                                trace_id=trace_id)
        warnings = []
        state, days_left = retirement_state(entry.retires_on, self.today())
        if state == "retired":
            return self._refuse(RefusalCode.MODEL_RETIRED, agent_id=agent_id, model_id=model_id, trace_id=trace_id)
        if state == "warning":
            warnings.append(f"model {model_id} retires on {entry.retires_on.isoformat()} ({days_left} days)")
        return Decision.ok(warnings)

    def check_tool(self, agent_id: Any, tool_name: Any, *, trace_id: Optional[str] = None) -> Decision:
        d = self.check_agent(agent_id, trace_id=trace_id)
        if not d.allowed:
            return d
        entry = self.tool(tool_name) if isinstance(tool_name, str) and _TOOL_NAME.fullmatch(tool_name) else None
        if entry is None:
            return self._refuse(RefusalCode.UNKNOWN_TOOL, agent_id=agent_id, tool=tool_name, trace_id=trace_id)
        if entry.access not in ALLOWED_TOOL_ACCESS:
            return self._refuse(RefusalCode.WRITE_TOOL_REFUSED, agent_id=agent_id, tool=tool_name, trace_id=trace_id)
        if tool_name not in self._agents[agent_id].allowed_tools:
            return self._refuse(RefusalCode.TOOL_NOT_ALLOWED, agent_id=agent_id, tool=tool_name, trace_id=trace_id)
        return Decision.ok()

    # -------------------------------------------------------------- cost
    def estimate_cost_usd(self, model_id: str, input_tokens: Any, max_output_tokens: Any) -> Optional[float]:
        entry = self.model(model_id)
        if entry is None or entry.price_input_per_mtok is None or entry.price_output_per_mtok is None:
            return None
        for n in (input_tokens, max_output_tokens):
            if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > MAX_TOKENS_PER_CALL:
                return None
        return (input_tokens * entry.price_input_per_mtok + max_output_tokens * entry.price_output_per_mtok) / 1e6

    def authorize_model_call(self, agent_id: Any, model_id: Any, *, study_key: str, input_tokens: Any,
                             max_output_tokens: Any, trace_id: Optional[str] = None) -> Decision:
        """Agent + model + size limits + worst-case cost against both caps (RC-110, RC-112)."""
        d = self.check_model(agent_id, model_id, trace_id=trace_id)
        if not d.allowed:
            return d
        spec = self._agents[agent_id]
        ctx = dict(agent_id=agent_id, model_id=model_id, study_key=study_key, trace_id=trace_id)
        for n, cap in ((input_tokens, spec.max_input_tokens), (max_output_tokens, spec.max_output_tokens)):
            if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                return self._refuse(RefusalCode.COST_UNKNOWN, **ctx)
            if n > cap:
                return self._refuse(RefusalCode.LIMIT_EXCEEDED, **ctx)
        estimate = self.estimate_cost_usd(model_id, input_tokens, max_output_tokens)
        if estimate is None:
            return self._refuse(RefusalCode.COST_UNKNOWN, **ctx)
        # Review of PR #79, finding 3: reserve the worst case atomically (no check-then-record race).
        reservation, code = self._ledger.reserve(agent_id, study_key, self.today().isoformat(), estimate,
                                                 spec.cost_cap_per_study_usd, spec.cost_cap_per_day_usd)
        if reservation is None:
            return self._refuse(code or RefusalCode.STUDY_COST_CAP, **ctx)
        return Decision.ok(d.warnings, reservation)

    def settle(self, reservation: str, usd: Optional[float]) -> bool:
        """Charge a reserved call its actual cost (``None``: unknown, the reserved worst case stays charged).
        True when the actual cost exceeded the reservation (fifth review, finding 4)."""
        if usd is not None and (not isinstance(usd, (int, float)) or isinstance(usd, bool) or not math.isfinite(usd)
                                or usd < 0):
            usd = None
        return self._ledger.settle(reservation, None if usd is None else float(usd)) is True

    def tool_definitions(self, names) -> Tuple[Dict[str, Any], ...]:
        """The definitions of the named, registered tools (sorted by name) — sent with a request and counted in
        its worst-case reservation (fifth review, finding 4)."""
        return tuple(self._tools[n].definition() for n in sorted(names) if n in self._tools)

    def record_cost(self, agent_id: str, study_key: str, usd: float) -> None:
        if not isinstance(usd, (int, float)) or isinstance(usd, bool) or not math.isfinite(usd) or usd < 0:
            raise ValueError("a recorded cost must be a finite, non-negative number")
        self._ledger.add(agent_id, study_key, self.today().isoformat(), float(usd))
