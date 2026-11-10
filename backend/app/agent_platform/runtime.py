"""
Agent runtime: the ONE loop through which an agent calls a model or a tool.

Requirements REQ-AGT-001, REQ-AGT-002, REQ-AGT-006, REQ-AGT-008; it is where RC-110..RC-116 and RC-119 act
inside a run. Hazards HAZ-020, HAZ-021, HAZ-022, HAZ-024. DRAFT, PENDING owner approval.

A run is a fixed, bounded loop (no planner, no memory between runs, no agent-to-agent messages):

    check agent (approved, switch on) -> [verifier present if required] -> refuse any caller override
    repeat up to limits.max_steps:
        authorize the model call  (switch re-read; exact model; not retired; size limits; worst-case cost)
        call the model            (chat span; content only as SHA-256)
        the answer must name the model requested, or it is discarded
        charge the cost           (reported usage; impossible usage -> the worst case)
        for each tool call, up to limits.max_tool_calls in the run:
            authorize the tool    (switch re-read; known; never write; on the agent's list)
            check the arguments   (every id in the run's study)
            run it, validate the result (plain bounded JSON, same study), quote it for the model
        no tool call -> the final text
    final text -> verifier (if the agent has one; required when the registry says so) -> switch re-read
    -> delivered text marked unit by unit as the model's (provenance)

Fail closed everywhere: any refusal, any tool or model failure, an exhausted step or tool-call budget,
a verifier that withholds or raises -> NOTHING is delivered (``RunResult.text is None``), and the refusal
is audited with its code. There is deliberately no "continue after a refused tool": a request for a
write tool or another patient's record is a sign the model has been steered (OWASP ASI01/ASI02/ASI08).

The model is reached through ``ModelClient.complete`` (a provider adapter, integration step P-2); the
platform never reads a model id, a key or a parameter from the environment: ``CLAUDE_MODEL`` and the like
are ignored here — only the registry decides.

@module agent_platform.runtime
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from app.agent_platform import provenance as prov
from app.agent_platform.registry import AgentRegistry, Decision, RefusalCode, pseudonymise
from app.agent_platform.tracing import Tracer
from app.agent_platform.untrusted import (UNTRUSTED_DATA_RULE, RunScope, check_tool_arguments, quote_untrusted,
                                          validate_tool_result)


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
    stop_reason: str = "end_turn"


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


def _resolve(value: Any) -> Any:
    """Run an awaitable tool result to completion (MCP tools are async)."""
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await(value))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_await(value))).result()


async def _await(value):
    return await value


class AgentRuntime:
    def __init__(self, registry: AgentRegistry, tracer: Tracer, *, tools: Optional[Mapping[str, Callable]] = None,
                 verifier: Optional[Verifier] = None):
        self.registry = registry
        self.tracer = tracer
        self.tools = dict(tools or {})
        self.verifier = verifier

    # -------------------------------------------------------------- helpers
    def _deny(self, code: RefusalCode, *, agent_id, scope: RunScope, trace_id: str, model_id=None, tool=None):
        ctx = {"agent_id": agent_id, "study_key": scope.study_key, "trace_id": trace_id}
        if model_id is not None:
            ctx["model_id"] = model_id
        if tool is not None:
            ctx["tool"] = tool
        self.registry.audit("denied", code, **ctx)

    # -------------------------------------------------------------- the loop
    def run(self, agent_id: str, *, model_client: ModelClient, scope: RunScope, system: str, user_content: str,
            untrusted: Sequence[Tuple[str, str]] = (), model_id: Optional[str] = None,
            overrides: Optional[Mapping[str, Any]] = None, trace_id: Optional[str] = None,
            audit_request_id: Optional[str] = None) -> RunResult:
        reg = self.registry
        provider = getattr(model_client, "provider", "unknown") or "unknown"
        with self.tracer.agent_span(agent_id, provider=provider, trace_id=trace_id, audit_request_id=audit_request_id,
                                    registry_version=reg.version, study_key=pseudonymise(scope.study_key)) as span:
            result = self._run(span, agent_id, model_client, scope, system, user_content, untrusted, model_id,
                               overrides)
            result.trace_id, result.span_id = span.trace_id, span.span_id
            span.set("mstool.run.status", result.status)
            span.set("mstool.run.steps", result.steps)
            span.set("mstool.run.tool_calls", result.tool_calls)
            span.set("mstool.cost.usd", round(result.cost_usd, 6))
            span.set("mstool.untrusted.alarm_count", len(result.alarms))
            if result.code != "ok":
                span.set("mstool.refusal.code", str(result.code))
        reg.audit("success" if result.status == "delivered" else "denied", result.code, event="agent.run",
                  agent_id=agent_id, model_id=result.model_id if result.model_id else None,
                  study_key=scope.study_key, trace_id=result.trace_id)
        return result

    def _run(self, span, agent_id, model_client, scope, system, user_content, untrusted, model_id, overrides
             ) -> RunResult:
        reg = self.registry
        tid = span.trace_id
        res = RunResult(status="refused", code="ok")

        def stop(status: str, code, audit: bool = True) -> RunResult:
            res.status, res.code, res.text = status, code, None
            if audit and code != "ok":
                self._deny(code, agent_id=agent_id, scope=scope, trace_id=tid, model_id=res.model_id)
            return res

        d = reg.check_agent(agent_id, trace_id=tid)
        if not d.allowed:
            return stop("refused", d.code, audit=False)          # the registry audited it
        spec = reg.agent(agent_id)
        if overrides:
            return stop("refused", RefusalCode.PARAMETER_OVERRIDE)
        if spec.requires_verifier and self.verifier is None:
            return stop("refused", RefusalCode.VERIFIER_MISSING)
        if model_id is None:
            if not spec.allowed_models:
                return stop("refused", RefusalCode.UNKNOWN_MODEL)
            model_id = spec.allowed_models[0]
        res.model_id = model_id if isinstance(model_id, str) else None
        max_tokens = spec.parameter("max_tokens", spec.max_output_tokens)

        alarms: List[str] = []
        first = user_content or ""
        quoted = [quote_untrusted(text, source) for source, text in untrusted]
        for q in quoted:
            alarms.extend(q.flags)
        if quoted or spec.allowed_tools:
            first += "\n\n" + UNTRUSTED_DATA_RULE
        if quoted:
            first += "\n" + "\n".join(q.block for q in quoted)
        messages: List[Dict[str, Any]] = [{"role": "user", "content": first}]
        executed: List[str] = []
        warnings: List[str] = []
        final_text: Optional[str] = None

        for step in range(1, spec.max_steps + 1):
            est_in = estimate_tokens(system, messages)
            d = reg.authorize_model_call(agent_id, model_id, study_key=scope.study_key, input_tokens=est_in,
                                         max_output_tokens=max_tokens, trace_id=tid)
            if not d.allowed:
                res.alarms = tuple(alarms)
                return stop("refused", d.code, audit=False)
            warnings.extend(w for w in d.warnings if w not in warnings)
            request = ModelRequest(model_id=model_id, system=system, messages=tuple(dict(m) for m in messages),
                                   tools=tuple(sorted(spec.allowed_tools)), max_tokens=max_tokens)
            res.steps = step
            with self.tracer.chat_span(model_id, provider=getattr(model_client, "provider", "unknown"),
                                       max_tokens=max_tokens) as chat:
                chat.set_content_hash("input", {"system": system, "messages": messages})
                try:
                    response = model_client.complete(request)
                except Exception as exc:  # noqa: BLE001 — any provider failure: no draft
                    chat.fail(type(exc).__name__)
                    reg.record_cost(agent_id, scope.study_key, reg.estimate_cost_usd(model_id, est_in, max_tokens) or 0.0)
                    res.alarms = tuple(alarms)
                    return stop("failed", RefusalCode.MODEL_CALL_FAILED)
                usage_ok = _valid_count(response.input_tokens) and _valid_count(response.output_tokens)
                cost = (reg.estimate_cost_usd(model_id, response.input_tokens, response.output_tokens) if usage_ok
                        else None)
                if cost is None:                                   # impossible usage: charge the worst case
                    cost = reg.estimate_cost_usd(model_id, est_in, max_tokens) or 0.0
                reg.record_cost(agent_id, scope.study_key, cost)
                res.cost_usd += cost
                chat.set("gen_ai.response.model", response.model_id)
                if usage_ok:
                    chat.set("gen_ai.usage.input_tokens", response.input_tokens)
                    chat.set("gen_ai.usage.output_tokens", response.output_tokens)
                if isinstance(response.stop_reason, str):
                    chat.set("gen_ai.response.finish_reasons", (response.stop_reason,))
                chat.set_content_hash("output", {"text": response.text,
                                                 "tool_calls": [(c.name, dict(c.arguments)) for c in response.tool_calls]
                                                 if isinstance(response.tool_calls, (tuple, list)) else None})
                chat.set("mstool.cost.usd", round(cost, 6))
                if response.model_id != model_id:
                    chat.set("mstool.refusal.code", str(RefusalCode.MODEL_IDENTITY_MISMATCH))
                    res.alarms = tuple(alarms)
                    return stop("refused", RefusalCode.MODEL_IDENTITY_MISMATCH)

            calls = tuple(response.tool_calls or ())
            if not calls:
                final_text = response.text if isinstance(response.text, str) else ""
                break
            messages.append({"role": "assistant", "content": response.text or "",
                             "tool_calls": [{"id": c.call_id, "name": c.name, "arguments": dict(c.arguments)
                                             if isinstance(c.arguments, Mapping) else None} for c in calls]})
            for call in calls:
                if res.tool_calls >= spec.max_tool_calls:
                    res.alarms = tuple(alarms)
                    return stop("abstained", RefusalCode.TOOL_CALL_LIMIT)
                res.tool_calls += 1
                with self.tracer.tool_span(call.name, call_id=call.call_id) as ts:
                    d = reg.check_tool(agent_id, call.name, trace_id=tid)
                    if not d.allowed:
                        ts.set("mstool.refusal.code", str(d.code))
                        res.alarms = tuple(alarms)
                        return stop("refused", d.code, audit=False)
                    entry = reg.tool(call.name)
                    d = check_tool_arguments(entry, call.arguments, scope)
                    if not d.allowed:
                        ts.set("mstool.refusal.code", str(d.code))
                        res.alarms = tuple(alarms)
                        return stop("refused", d.code)
                    fn = self.tools.get(call.name)
                    if fn is None:
                        ts.set("mstool.refusal.code", str(RefusalCode.UNKNOWN_TOOL))
                        res.alarms = tuple(alarms)
                        return stop("refused", RefusalCode.UNKNOWN_TOOL)
                    try:
                        raw = _resolve(fn(**dict(call.arguments)))
                    except Exception as exc:  # noqa: BLE001 — a failing tool: no draft
                        ts.fail(type(exc).__name__)
                        res.alarms = tuple(alarms)
                        return stop("failed", RefusalCode.TOOL_FAILED)
                    check = validate_tool_result(raw, tool=entry, scope=scope, max_bytes=spec.max_tool_result_bytes)
                    if not check.ok:
                        ts.set("mstool.refusal.code", str(check.code))
                        res.alarms = tuple(alarms)
                        return stop("refused", check.code)
                    ts.set("mstool.content.tool_result_sha256", check.sha256)
                    ts.set("mstool.untrusted.alarm_count", len(check.flags))
                    alarms.extend(check.flags)
                    executed.append(call.name)
                messages.append({"role": "tool", "tool_call_id": call.call_id, "content": check.for_model})
        else:
            res.alarms = tuple(alarms)
            res.executed_tools = tuple(executed)
            return stop("abstained", RefusalCode.STEP_LIMIT)

        res.executed_tools, res.warnings, res.alarms = tuple(executed), tuple(warnings), tuple(alarms)
        delivered = final_text
        verifier_name = None
        if self.verifier is not None:
            with self.tracer.verify_span("verifier", verdict="not_run") as vs:
                try:
                    verdict = self.verifier(final_text, {"agent_id": agent_id, "model_id": model_id, "scope": scope,
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
                    vs._span.name = f"verify {verdict.verifier_name}" if isinstance(verdict.verifier_name, str) \
                        and verdict.verifier_name.replace("-", "").replace("_", "").isalnum() else "verify"
                else:
                    vs.set("mstool.verifier.verdict", "blocked")
            res.verdict = verdict if ok else None
            if not ok or verdict.verdict != "pass" or not (verdict.delivered_text or "").strip():
                return stop("withheld", RefusalCode.VERIFIER_WITHHELD)
            delivered, verifier_name = verdict.delivered_text, verdict.verifier_name

        d = reg.check_agent(agent_id, trace_id=tid)               # the switch, once more, before delivery
        if not d.allowed:
            return stop("refused", d.code, audit=False)
        res.status, res.code, res.text = "delivered", "ok", delivered
        res.provenance = prov.mark_model_text(delivered, agent_id=agent_id, model_id=model_id, trace_id=tid,
                                              verifier=verifier_name)
        return res
