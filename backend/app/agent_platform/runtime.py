"""
Agent runtime: the ONE loop through which an agent calls a model or a tool.

Requirements REQ-AGT-001, REQ-AGT-002, REQ-AGT-006, REQ-AGT-008; it is where RC-110..RC-116 and RC-119 act
inside a run. Hazards HAZ-020, HAZ-021, HAZ-022, HAZ-024. DRAFT, PENDING owner approval.

A run is a fixed, bounded loop (no planner, no memory between runs, no agent-to-agent messages):

    check agent (approved, switch on) -> [verifier present if required] -> refuse any caller override
    -> output budget: one of the registry's max_tokens* budgets (per template), never a caller's number
    repeat up to limits.max_steps:
        authorize the model call  (switch re-read; exact model; not retired; size limits; worst-case cost
                                   RESERVED atomically against the study and day caps)
        call the model            (chat span; content only as SHA-256)
        the answer must name the model requested, or it is discarded
        settle the reservation    (reported usage; impossible usage -> the worst case stays charged)
        the answer must have ENDED normally: end_turn / stop_sequence for text, tool_use for tool calls;
        max_tokens or a context-window stop is a truncation, any other stop (refusal, pause, unknown) is
        unexpected — either way nothing is delivered and no tool call of that answer runs
        for each tool call, up to limits.max_tool_calls in the run:
            authorize the tool    (switch re-read; known; never write; on the agent's list)
            check the arguments   (declared schema; every id-like value anywhere in the run's study)
            run it, validate the result (plain bounded JSON; every id anywhere in the study), quote it
        no tool call -> the final text
    final text -> verifier (if the agent has one; required when the registry says so) -> switch re-read
    -> delivered text marked unit by unit as the model's (provenance)

Fail closed everywhere: any refusal, any tool or model failure, an exhausted step or tool-call budget,
a truncated or abnormally stopped answer, a verifier that withholds or fails -> NOTHING is delivered
(``RunResult.text is None``). Audit outcome (review of PR #79, finding 8): a refusal by the platform is
``denied``; a failure of the model, a tool or the verifier (``registry.FAILURE_CODES``) is ``failure``.
There is deliberately no "continue after a refused tool": a request for a write tool or another
patient's record is a sign the model has been steered (OWASP ASI01/ASI02/ASI08).

Two entry points (review of PR #79, finding 9): ``await arun(...)`` from async code — tool coroutines are
awaited in the caller's event loop, an async model client (``acomplete``) is awaited and a sync one runs
in a worker thread so the loop is never blocked; ``run(...)`` for sync callers only — it refuses to run
inside a running event loop instead of blocking it.

The model is reached through a provider adapter (integration step P-2); the platform never reads a model
id, a key or a parameter from the environment: ``CLAUDE_MODEL`` and the like are ignored here.

@module agent_platform.runtime
"""

from __future__ import annotations

import asyncio
import inspect
import json
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from app.agent_platform import provenance as prov
from app.agent_platform.registry import FAILURE_CODES, AgentRegistry, RefusalCode, pseudonymise
from app.agent_platform.tracing import Tracer
from app.agent_platform.untrusted import (UNTRUSTED_DATA_RULE, RunScope, check_tool_arguments, quote_untrusted,
                                          validate_tool_result)

TEXT_END = frozenset({"end_turn", "stop_sequence"})
TOOL_END = frozenset({"tool_use"})
TRUNCATED = frozenset({"max_tokens", "model_context_window_exceeded"})
BUDGET_PREFIX = "max_tokens"


# ------------------------------------------------------------------ provider-neutral messages
@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class ModelRequest:
    model_id: str
    system: str
    messages: Tuple[Dict[str, Any], ...]
    tools: Tuple[str, ...]
    max_tokens: int


@dataclass(frozen=True)
class ModelResponse:
    model_id: str                         # the model the PROVIDER says answered
    text: str
    tool_calls: Tuple[ToolCall, ...] = ()
    input_tokens: Any = None
    output_tokens: Any = None
    stop_reason: Optional[str] = "end_turn"


class ModelClient(Protocol):
    provider: str

    def complete(self, request: ModelRequest) -> ModelResponse: ...


@dataclass(frozen=True)
class Verdict:
    verdict: str                          # pass | withheld | blocked
    delivered_text: str
    withheld_count: int = 0
    verifier_name: str = "verifier"
    reasons: Tuple[str, ...] = ()


Verifier = Callable[[str, Mapping[str, Any]], Verdict]


@dataclass
class RunResult:
    status: str                           # delivered | withheld | refused | abstained | failed
    code: str
    text: Optional[str] = None
    provenance: Optional[prov.ProvenanceDocument] = None
    trace_id: str = ""
    span_id: str = ""
    model_id: Optional[str] = None
    steps: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0
    executed_tools: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    verdict: Optional[Verdict] = None
    alarms: Tuple[str, ...] = ()


def estimate_tokens(system: str, messages: Sequence[Mapping[str, Any]]) -> int:
    """A deliberately HIGH estimate: one token per 2 UTF-8 bytes (real tokenizers average about 4 characters
    per token in English), plus a per-message overhead. Used for the limits and the worst-case cost."""
    total = math.ceil(len((system or "").encode("utf-8")) / 2) + 8
    for m in messages:
        total += math.ceil(len(json.dumps(m, ensure_ascii=False, default=str).encode("utf-8")) / 2) + 8
    return total


def _valid_count(n: Any) -> bool:
    return isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 10_000_000


def audit_outcome(status: str) -> str:
    if status == "delivered":
        return "success"
    return "failure" if status == "failed" else "denied"


def response_is_malformed(response: Any) -> bool:
    """Second review of PR #79, finding 4: the provider's answer must have the expected shape before any field of
    it is used; anything else is a non-delivery (``model_response_invalid``), never an exception."""
    if not isinstance(response, ModelResponse) or not isinstance(response.model_id, str):
        return True
    if response.text is not None and not isinstance(response.text, str):
        return True
    if response.stop_reason is not None and not isinstance(response.stop_reason, str):
        return True
    if not isinstance(response.tool_calls, (tuple, list)):
        return True
    return any(not isinstance(c, ToolCall) or not isinstance(c.call_id, str) or not isinstance(c.name, str)
               or not isinstance(c.arguments, Mapping) for c in response.tool_calls)


class AgentRuntime:
    def __init__(self, registry: AgentRegistry, tracer: Tracer, *, tools: Optional[Mapping[str, Callable]] = None,
                 verifier: Optional[Verifier] = None):
        self.registry = registry
        self.tracer = tracer
        self.tools = dict(tools or {})
        self.verifier = verifier

    # -------------------------------------------------------------- entry points
    def run(self, agent_id: str, **kwargs) -> RunResult:
        """For SYNC callers. Inside a running event loop it raises instead of blocking it: use ``arun``."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._arun(agent_id, kwargs, blocking_model=True))
        raise RuntimeError("AgentRuntime.run() was called inside a running event loop; use "
                           "'await AgentRuntime.arun(...)' so tools are awaited and the loop is never blocked")

    async def arun(self, agent_id: str, **kwargs) -> RunResult:
        """For ASYNC callers (e.g. a FastAPI route): tools are awaited in this loop; a sync model client runs in
        a worker thread, an async one (``acomplete``) is awaited."""
        return await self._arun(agent_id, kwargs, blocking_model=False)

    async def _call_model(self, model_client: Any, request: ModelRequest, blocking_model: bool) -> ModelResponse:
        acomplete = getattr(model_client, "acomplete", None)
        if acomplete is not None:
            return await acomplete(request)
        if blocking_model:
            return model_client.complete(request)
        return await asyncio.to_thread(model_client.complete, request)

    @staticmethod
    async def _off_loop(fn: Callable, blocking: bool, *args, **kwargs) -> Any:
        """Second review of PR #79, finding 6: in ``arun`` a sync tool or verifier runs in a worker thread so the
        caller's loop stays responsive; a coroutine function is awaited in the loop; in ``run`` (a private loop)
        everything is called directly. A result that is awaitable is awaited in the loop."""
        if blocking or inspect.iscoroutinefunction(fn):
            out = fn(*args, **kwargs)
        else:
            out = await asyncio.to_thread(fn, *args, **kwargs)
        if inspect.isawaitable(out):
            out = await out
        return out

    # -------------------------------------------------------------- the run
    async def _arun(self, agent_id: str, kwargs: Dict[str, Any], blocking_model: bool) -> RunResult:
        model_client = kwargs.get("model_client")
        scope: RunScope = kwargs["scope"]
        reg = self.registry
        provider = getattr(model_client, "provider", "unknown") or "unknown"
        trace = {}
        try:
            with self.tracer.agent_span(agent_id, provider=provider, trace_id=kwargs.get("trace_id"),
                                        audit_request_id=kwargs.get("audit_request_id"), registry_version=reg.version,
                                        study_key=pseudonymise(scope.study_key)) as span:
                trace["id"] = span.trace_id
                result = await self._loop(span, agent_id, model_client, scope, kwargs, blocking_model)
                self._finish_span(span, result)
        except asyncio.CancelledError:
            # Second review of PR #79, finding 5: the reservation was settled where the cancellation hit (model
            # call) or was never made; the audit trail records the cancelled run; the cancellation propagates.
            reg.audit("cancelled", RefusalCode.RUN_CANCELLED, event="agent.run", agent_id=agent_id,
                      study_key=scope.study_key, trace_id=trace.get("id"))
            raise
        reg.audit(audit_outcome(result.status), result.code, event="agent.run", agent_id=agent_id,
                  model_id=result.model_id if result.model_id else None, study_key=scope.study_key,
                  trace_id=result.trace_id)
        return result

    @staticmethod
    def _finish_span(span, result: RunResult) -> None:
        result.trace_id, result.span_id = span.trace_id, span.span_id
        span.set("mstool.run.status", result.status)
        span.set("mstool.run.steps", result.steps)
        span.set("mstool.run.tool_calls", result.tool_calls)
        span.set("mstool.cost.usd", round(result.cost_usd, 6))
        span.set("mstool.untrusted.alarm_count", len(result.alarms))
        if result.code != "ok":
            span.set("mstool.refusal.code", str(result.code))

    async def _loop(self, span, agent_id, model_client, scope, kwargs, blocking_model) -> RunResult:
        reg = self.registry
        tid = span.trace_id
        system = kwargs.get("system", "")
        user_content = kwargs.get("user_content", "")
        untrusted = kwargs.get("untrusted", ())
        model_id = kwargs.get("model_id")
        overrides = kwargs.get("overrides")
        res = RunResult(status="refused", code="ok")
        alarms: List[str] = []
        executed: List[str] = []
        warnings: List[str] = []

        def stop(status: str, code, audit: bool = True) -> RunResult:
            """Every early return goes through here, so alarms, executed tools and warnings are never dropped."""
            res.status, res.code, res.text = status, code, None
            res.alarms, res.executed_tools, res.warnings = tuple(alarms), tuple(executed), tuple(warnings)
            if audit and code != "ok":
                ctx = {"agent_id": agent_id, "study_key": scope.study_key, "trace_id": tid}
                if res.model_id is not None:
                    ctx["model_id"] = res.model_id
                reg.audit(audit_outcome(status), code, **ctx)
            return res

        unknown = set(kwargs) - {"model_client", "scope", "system", "user_content", "untrusted", "model_id",
                                 "overrides", "trace_id", "audit_request_id", "output_budget"}
        d = reg.check_agent(agent_id, trace_id=tid)
        if not d.allowed:
            return stop("refused", d.code, audit=False)          # the registry audited it
        spec = reg.agent(agent_id)
        if overrides or unknown:
            return stop("refused", RefusalCode.PARAMETER_OVERRIDE)
        if spec.requires_verifier and self.verifier is None:
            return stop("refused", RefusalCode.VERIFIER_MISSING)
        if model_id is None:
            if not spec.allowed_models:
                return stop("refused", RefusalCode.UNKNOWN_MODEL)
            model_id = spec.allowed_models[0]
        res.model_id = model_id if isinstance(model_id, str) else None
        # Review of PR #79, finding 1: the output budget is one of the registry's budgets for this agent (e.g.
        # max_tokens, or max_tokens_comprehensive for the comprehensive template) — chosen by name, never a number.
        budget_name = kwargs.get("output_budget", BUDGET_PREFIX)
        max_tokens = spec.parameter(budget_name) if isinstance(budget_name, str) and \
            budget_name.startswith(BUDGET_PREFIX) else None
        if budget_name == BUDGET_PREFIX and max_tokens is None:
            max_tokens = spec.max_output_tokens
        if not _valid_count(max_tokens) or max_tokens < 1 or max_tokens > spec.max_output_tokens:
            return stop("refused", RefusalCode.PARAMETER_OVERRIDE)

        first = user_content or ""
        quoted = [quote_untrusted(text, source) for source, text in untrusted]
        for q in quoted:
            alarms.extend(q.flags)
        if quoted or spec.allowed_tools:
            first += "\n\n" + UNTRUSTED_DATA_RULE
        if quoted:
            first += "\n" + "\n".join(q.block for q in quoted)
        messages: List[Dict[str, Any]] = [{"role": "user", "content": first}]
        final_text: Optional[str] = None

        for step in range(1, spec.max_steps + 1):
            est_in = estimate_tokens(system, messages)
            d = reg.authorize_model_call(agent_id, model_id, study_key=scope.study_key, input_tokens=est_in,
                                         max_output_tokens=max_tokens, trace_id=tid)
            if not d.allowed:
                return stop("refused", d.code, audit=False)
            warnings.extend(w for w in d.warnings if w not in warnings)
            request = ModelRequest(model_id=model_id, system=system, messages=tuple(dict(m) for m in messages),
                                   tools=tuple(sorted(spec.allowed_tools)), max_tokens=max_tokens)
            res.steps = step
            worst = reg.estimate_cost_usd(model_id, est_in, max_tokens) or 0.0
            with self.tracer.chat_span(model_id, provider=getattr(model_client, "provider", "unknown"),
                                       max_tokens=max_tokens) as chat:
                chat.set_content_hash("input", {"system": system, "messages": messages})
                try:
                    response = await self._call_model(model_client, request, blocking_model)
                except asyncio.CancelledError:
                    reg.settle(d.reservation, None)             # never leaked: the worst case stays charged
                    raise
                except Exception as exc:  # noqa: BLE001 — any provider failure: no draft
                    chat.fail(type(exc).__name__)
                    reg.settle(d.reservation, None)             # the provider may have charged: worst case kept
                    res.cost_usd += worst
                    return stop("failed", RefusalCode.MODEL_CALL_FAILED)
                if response_is_malformed(response):
                    reg.settle(d.reservation, None)
                    res.cost_usd += worst
                    chat.set("mstool.refusal.code", str(RefusalCode.MODEL_RESPONSE_INVALID))
                    return stop("failed", RefusalCode.MODEL_RESPONSE_INVALID)
                usage_ok = _valid_count(response.input_tokens) and _valid_count(response.output_tokens)
                cost = (reg.estimate_cost_usd(model_id, response.input_tokens, response.output_tokens) if usage_ok
                        else None)
                reg.settle(d.reservation, cost)                 # None: impossible usage, the worst case stays
                res.cost_usd += worst if cost is None else cost
                chat.set("gen_ai.response.model", response.model_id)
                if usage_ok:
                    chat.set("gen_ai.usage.input_tokens", response.input_tokens)
                    chat.set("gen_ai.usage.output_tokens", response.output_tokens)
                if isinstance(response.stop_reason, str):
                    chat.set("gen_ai.response.finish_reasons", (response.stop_reason,))
                calls = tuple(response.tool_calls or ()) if isinstance(response.tool_calls, (tuple, list)) else ()
                chat.set_content_hash("output", {"text": response.text,
                                                 "tool_calls": [(c.name, dict(c.arguments) if isinstance(
                                                     c.arguments, Mapping) else None) for c in calls]})
                chat.set("mstool.cost.usd", round(worst if cost is None else cost, 6))
                if response.model_id != model_id:
                    chat.set("mstool.refusal.code", str(RefusalCode.MODEL_IDENTITY_MISMATCH))
                    return stop("refused", RefusalCode.MODEL_IDENTITY_MISMATCH)
                # Review of PR #79, finding 1: only a normal end is accepted.
                expected_end = TOOL_END if calls else TEXT_END
                if response.stop_reason not in expected_end:
                    code = (RefusalCode.OUTPUT_TRUNCATED if response.stop_reason in TRUNCATED
                            else RefusalCode.MODEL_STOP_UNEXPECTED)
                    chat.set("mstool.refusal.code", str(code))
                    return stop("failed", code)

            if not calls:
                final_text = response.text if isinstance(response.text, str) else ""
                break
            messages.append({"role": "assistant", "content": response.text or "",
                             "tool_calls": [{"id": c.call_id, "name": c.name, "arguments": dict(c.arguments)
                                             if isinstance(c.arguments, Mapping) else None} for c in calls]})
            for call in calls:
                if res.tool_calls >= spec.max_tool_calls:
                    return stop("abstained", RefusalCode.TOOL_CALL_LIMIT)
                res.tool_calls += 1
                with self.tracer.tool_span(call.name, call_id=call.call_id) as ts:
                    d = reg.check_tool(agent_id, call.name, trace_id=tid)
                    if not d.allowed:
                        ts.set("mstool.refusal.code", str(d.code))
                        return stop("refused", d.code, audit=False)
                    entry = reg.tool(call.name)
                    d = check_tool_arguments(entry, call.arguments, scope)
                    if not d.allowed:
                        ts.set("mstool.refusal.code", str(d.code))
                        return stop("refused", d.code)
                    fn = self.tools.get(call.name)
                    if fn is None:
                        ts.set("mstool.refusal.code", str(RefusalCode.UNKNOWN_TOOL))
                        return stop("refused", RefusalCode.UNKNOWN_TOOL)
                    try:
                        raw = await self._off_loop(fn, blocking_model, **dict(call.arguments))
                    except Exception as exc:  # noqa: BLE001 — a failing tool: no draft
                        ts.fail(type(exc).__name__)
                        return stop("failed", RefusalCode.TOOL_FAILED)
                    check = validate_tool_result(raw, tool=entry, scope=scope, max_bytes=spec.max_tool_result_bytes)
                    if not check.ok:
                        ts.set("mstool.refusal.code", str(check.code))
                        return stop("refused", check.code)
                    ts.set("mstool.content.tool_result_sha256", check.sha256)
                    ts.set("mstool.untrusted.alarm_count", len(check.flags))
                    alarms.extend(check.flags)
                    executed.append(call.name)
                messages.append({"role": "tool", "tool_call_id": call.call_id, "content": check.for_model})
        else:
            return stop("abstained", RefusalCode.STEP_LIMIT)

        if not (final_text or "").strip():                      # second review of PR #79, finding 8
            return stop("failed", RefusalCode.MODEL_OUTPUT_EMPTY)
        delivered = final_text
        verifier_name = None
        if self.verifier is not None:
            with self.tracer.verify_span("verifier", verdict="not_run") as vs:
                try:
                    verdict = await self._off_loop(self.verifier, blocking_model, final_text,
                                                   {"agent_id": agent_id, "model_id": model_id, "scope": scope,
                                                    "user_content": user_content})
                    ok = isinstance(verdict, Verdict)
                except Exception as exc:  # noqa: BLE001 — a verifier that fails withholds
                    vs.fail(type(exc).__name__)
                    verdict, ok = None, False
                if ok:
                    vs.set("mstool.verifier.name", verdict.verifier_name)
                    vs.set("mstool.verifier.verdict", verdict.verdict if verdict.verdict in ("pass", "withheld",
                                                                                              "blocked") else "blocked")
                    vs.set("mstool.verifier.withheld_count", verdict.withheld_count)
                    vs.rename(f"verify {verdict.verifier_name}")
                else:
                    vs.set("mstool.verifier.verdict", "blocked")
            res.verdict = verdict if ok else None
            if not ok:
                return stop("failed", RefusalCode.VERIFIER_FAILED)
            if verdict.verdict != "pass" or not (verdict.delivered_text or "").strip():
                return stop("withheld", RefusalCode.VERIFIER_WITHHELD)
            delivered, verifier_name = verdict.delivered_text, verdict.verifier_name

        d = reg.check_agent(agent_id, trace_id=tid)               # the switch, once more, before delivery
        if not d.allowed:
            return stop("refused", d.code, audit=False)
        res.status, res.code, res.text = "delivered", "ok", delivered
        res.alarms, res.executed_tools, res.warnings = tuple(alarms), tuple(executed), tuple(warnings)
        res.provenance = prov.mark_model_text(delivered, agent_id=agent_id, model_id=model_id, trace_id=tid,
                                              verifier=verifier_name)
        return res
