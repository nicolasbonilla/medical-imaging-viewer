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
}

# Codes of a run that FAILED (the model, a tool or the verifier did not work) as opposed to one the platform
# REFUSED: failures are audited as failures, refusals as denials (review of PR #79, finding 8).
FAILURE_CODES = frozenset({RefusalCode.MODEL_CALL_FAILED, RefusalCode.TOOL_FAILED, RefusalCode.VERIFIER_FAILED,
                           RefusalCode.OUTPUT_TRUNCATED, RefusalCode.MODEL_STOP_UNEXPECTED,
                           RefusalCode.MODEL_RESPONSE_INVALID, RefusalCode.MODEL_OUTPUT_EMPTY})


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
ARGUMENT_KINDS = RESOURCE_KINDS | frozenset({"string", "integer", "number", "boolean", "object", "array"})


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
    result_exempt_keys: Tuple[str, ...] = ()             # id-like result keys that name no resource (e.g. report_id)
    result_numeric_keys: Tuple[str, ...] = ()            # id-like result keys whose NUMBERS are lesion/label numbers

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

    def settle(self, reservation_id: str, usd: Optional[float]) -> None: ...

    def add(self, agent_id: str, study_key: str, day: str, usd: float) -> None: ...


class InMemoryCostLedger:
    """The CostLedger contract in memory, for one instance (lost on restart)."""

    def __init__(self):
        self._study: Dict[Tuple[str, str], float] = {}
        self._day: Dict[Tuple[str, str], float] = {}
        self._reservations: Dict[str, Tuple[str, str, str, float]] = {}
        self._lock = threading.Lock()

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

    def settle(self, reservation_id: str, usd: Optional[float]) -> None:
        with self._lock:
            entry = self._reservations.pop(reservation_id, None)
            if entry is None:
                raise ValueError("unknown or already settled reservation")
            agent_id, study_key, day, reserved = entry
            if usd is not None:                            # None: the actual cost is unknown, the worst case stays
                self._apply(agent_id, study_key, day, usd - reserved)


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


def default_audit_sink(event: Dict[str, Any]) -> None:
    """Forward an agent-platform event to the server audit log (CAPA-015 trail). Never raises."""
    try:
        from app.core.logging.audit import AuditEventType, AuditOutcome, emit_audit
        outcome = {"denied": AuditOutcome.DENIED, "success": AuditOutcome.SUCCESS}.get(
            event.get("outcome"), AuditOutcome.FAILURE)
        ids = {k: event[k] for k in ("agent_id", "model_id", "tool", "trace_id", "study_key") if event.get(k)}
        emit_audit(AuditEventType.CLINICAL_AI_RUN, outcome, reason=f"agent.{event.get('code', 'unknown')}"[:64],
                   resource_type="agent_run", resource_ids=ids)
    except Exception:  # noqa: BLE001 — auditing never breaks the caller
        pass


_UNSET = object()


def _safe_id(value: Any, pattern: re.Pattern) -> Optional[str]:
    """The id when well formed (matched whole: a trailing newline is not accepted), else "invalid"."""
    if value is _UNSET:
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
            exempt = t.get("result_exempt_keys") or []
            numeric = t.get("result_numeric_keys") or []
            if not all(isinstance(x, list) and all(isinstance(k, str) for k in x) for x in (exempt, numeric)):
                err(f"tool {name}: result_exempt_keys and result_numeric_keys must be lists of keys")
                continue
            self._tools[name] = ToolEntry(name=name, access=t["access"], arguments=tuple(sorted(args.items())),
                                          result_exempt_keys=tuple(exempt), result_numeric_keys=tuple(numeric))
        for aid, a in data["agents"].items():
            if not isinstance(aid, str) or not _AGENT_ID.fullmatch(aid):
                err(f"agent id not well formed: {aid!r}")
                continue
            approval = a.get("approval") or {}
            if approval.get("status") not in APPROVAL_STATUSES:
                err(f"agent {aid}: approval.status must be one of {sorted(APPROVAL_STATUSES)}")
            models = a.get("allowed_models")
            tools = a.get("allowed_tools")
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
                parameters=tuple(sorted(params.items())), requires_verifier=a.get("requires_verifier") is True)

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
              study_key: Optional[str] = None, trace_id: Optional[str] = None, event: str = "agent.decision") -> None:
        record = {
            "event": event, "outcome": outcome, "code": str(code),
            "agent_id": _safe_id(agent_id, _AGENT_ID),
            "model_id": _safe_id(model_id, _MODEL_ID),
            "tool": _safe_id(tool, _TOOL_NAME),
            "study_key": pseudonymise(study_key) if study_key is not None else None,
            "trace_id": trace_id if isinstance(trace_id, str) and re.fullmatch(r"[0-9a-f]{32}", trace_id) else None,
            "registry_version": self.version[:64],
            "reason": REASONS.get(code) if isinstance(code, RefusalCode) else None,
        }
        record = {k: v for k, v in record.items() if v is not None}
        try:
            self._audit(record)
        except Exception:  # noqa: BLE001 — an audit failure never turns a refusal into a permission
            pass

    def _refuse(self, code: RefusalCode, **ctx) -> Decision:
        self.audit("denied", code, **ctx)
        return Decision.refuse(code)

    # -------------------------------------------------------------- checks
    def check_agent(self, agent_id: Any, *, trace_id: Optional[str] = None) -> Decision:
        """Known, approved and switched on — the switch is read now, at every call (RC-111)."""
        if not self.valid:
            return self._refuse(RefusalCode.REGISTRY_INVALID, agent_id=agent_id, trace_id=trace_id)
        spec = self.agent(agent_id) if isinstance(agent_id, str) and _AGENT_ID.fullmatch(agent_id) else None
        if spec is None:
            return self._refuse(RefusalCode.UNKNOWN_AGENT, agent_id=agent_id, trace_id=trace_id)
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
        if entry.retires_on is not None:
            days_left = (entry.retires_on - self.today()).days
            if days_left <= 0:
                return self._refuse(RefusalCode.MODEL_RETIRED, agent_id=agent_id, model_id=model_id,
                                    trace_id=trace_id)
            if days_left <= RETIREMENT_WARNING_DAYS:
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

    def settle(self, reservation: str, usd: Optional[float]) -> None:
        """Charge a reserved call its actual cost (``None``: unknown, the reserved worst case stays charged)."""
        if usd is not None and (not isinstance(usd, (int, float)) or isinstance(usd, bool) or not math.isfinite(usd)
                                or usd < 0):
            usd = None
        self._ledger.settle(reservation, None if usd is None else float(usd))

    def record_cost(self, agent_id: str, study_key: str, usd: float) -> None:
        if not isinstance(usd, (int, float)) or isinstance(usd, bool) or not math.isfinite(usd) or usd < 0:
            raise ValueError("a recorded cost must be a finite, non-negative number")
        self._ledger.add(agent_id, study_key, self.today().isoformat(), float(usd))
