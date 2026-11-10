"""Tracing after the OpenTelemetry GenAI semantic conventions v1.37.0 (REQ-AGT-002; RC-116; HAZ-022).

DRAFT, PENDING owner approval. Written before app/agent_platform/tracing.py existed (failing first).
Negative controls: scripts/safety/agent_platform_negative_controls.py (mutations T*).

Pinned revision: semantic-conventions v1.37.0, docs/gen-ai/gen-ai-spans.md and gen-ai-agent-spans.md,
read 2026-11-10 at the v1.37.0 tag (all gen_ai attributes there are at "Development" stability; the
conventions have since moved to the separate semantic-conventions-genai repository, which has no release).

- Span names and kinds as in v1.37.0: ``invoke_agent {gen_ai.agent.name}`` (CLIENT), ``chat
  {gen_ai.request.model}`` (CLIENT), ``execute_tool {gen_ai.tool.name}`` (INTERNAL); required attributes
  present (gen_ai.operation.name; gen_ai.provider.name on invoke_agent).
- RC-116: only allow-listed attributes are ever recorded; the Opt-In content attributes
  (gen_ai.input.messages, gen_ai.output.messages, gen_ai.system_instructions) and any later content
  attribute are refused; content appears only as SHA-256; free text cannot ride in an id attribute; the
  exporter is off by default; the trace adopts the request's trace id (so the audit record of the request
  names it) and the radiologist's later sign-off is linked to the run's span.
"""
import json

import pytest

from app.agent_platform import tracing as T

FORBIDDEN = ["gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.system_instructions",
             "gen_ai.tool.definitions", "gen_ai.tool.call.arguments", "gen_ai.tool.call.result",
             "gen_ai.prompt", "gen_ai.completion", "patient.name", "mstool.free_text"]


@pytest.fixture
def mem():
    return T.InMemoryExporter()


@pytest.fixture
def tracer(mem):
    return T.Tracer(mem)


def test_rc116_semconv_revision_is_pinned_and_declared():
    assert T.SEMCONV_VERSION == "1.37.0"
    assert T.SEMCONV_SCHEMA_URL == "https://opentelemetry.io/schemas/1.37.0"
    assert T.SEMCONV_STABILITY == "Development"


def test_rc116_agent_chat_and_tool_spans_follow_v1_37(tracer, mem):
    with tracer.agent_span("test-agent", provider="anthropic") as run:
        with tracer.chat_span("model-current", provider="anthropic", max_tokens=1000) as chat:
            chat.set("gen_ai.usage.input_tokens", 120)
            chat.set("gen_ai.usage.output_tokens", 40)
            chat.set("gen_ai.response.model", "model-current")
            chat.set("gen_ai.response.finish_reasons", ("end_turn",))
        with tracer.tool_span("read_measurements", call_id="call_1"):
            pass
    spans = {s.name: s for s in mem.spans}
    agent = spans["invoke_agent test-agent"]
    assert agent.kind == "CLIENT" and agent.parent_span_id is None
    assert agent.attributes["gen_ai.operation.name"] == "invoke_agent"
    assert agent.attributes["gen_ai.provider.name"] == "anthropic"
    assert agent.attributes["gen_ai.agent.id"] == "test-agent"
    assert agent.attributes["gen_ai.agent.name"] == "test-agent"
    chat = spans["chat model-current"]
    assert chat.kind == "CLIENT" and chat.parent_span_id == agent.span_id and chat.trace_id == agent.trace_id
    assert chat.attributes["gen_ai.operation.name"] == "chat"
    assert chat.attributes["gen_ai.request.model"] == "model-current"
    assert chat.attributes["gen_ai.request.max_tokens"] == 1000
    assert chat.attributes["gen_ai.usage.input_tokens"] == 120
    tool = spans["execute_tool read_measurements"]
    assert tool.kind == "INTERNAL" and tool.parent_span_id == agent.span_id
    assert tool.attributes["gen_ai.operation.name"] == "execute_tool"
    assert tool.attributes["gen_ai.tool.name"] == "read_measurements"
    assert tool.attributes["gen_ai.tool.call.id"] == "call_1"
    assert tool.attributes["gen_ai.tool.type"] == "function"
    for s in mem.spans:
        assert len(s.trace_id) == 32 and len(s.span_id) == 16 and s.end_ns >= s.start_ns


@pytest.mark.parametrize("key", FORBIDDEN)
def test_rc116_content_attributes_are_never_recorded(tracer, mem, key):
    with tracer.agent_span("test-agent", provider="anthropic") as run:
        run.set(key, "Patient Jane Doe, born 1970-01-01: ignore previous instructions")
    span = mem.spans[-1]
    assert key not in span.attributes
    assert span.attributes.get("mstool.trace.dropped_attributes") == 1
    assert "Jane" not in json.dumps(T.to_otlp_json(mem.spans))


@pytest.mark.parametrize("key,value", [
    ("gen_ai.agent.name", "report for Jane Doe"),
    ("gen_ai.request.model", "model current\nJane"),
    ("gen_ai.tool.call.id", "x" * 200),
    ("mstool.content.input_sha256", "Patient Jane Doe"),
    ("mstool.content.output_sha256", "abc"),
    ("gen_ai.usage.input_tokens", "120"),
    ("gen_ai.usage.input_tokens", -5),
    ("mstool.verifier.verdict", "the model said the criteria are met"),
])
def test_rc116_free_text_cannot_ride_in_an_allowed_attribute(tracer, mem, key, value):
    with tracer.agent_span("test-agent", provider="anthropic") as run:
        run.set(key, value)
    assert key not in mem.spans[-1].attributes or mem.spans[-1].attributes[key] != value


def test_rc116_content_is_recorded_only_as_sha256(tracer, mem):
    text = "Patient Jane Doe has 7 lesions"
    with tracer.chat_span("model-current", provider="anthropic", max_tokens=10) as chat:
        chat.set_content_hash("input", text)
        chat.set_content_hash("output", "draft text")
    attrs = mem.spans[-1].attributes
    assert attrs["mstool.content.input_sha256"] == T.content_sha256(text)
    assert len(attrs["mstool.content.output_sha256"]) == 64
    assert "Jane" not in json.dumps(T.to_otlp_json(mem.spans))


def test_rc116_errors_set_error_type_only(tracer, mem):
    with pytest.raises(ValueError):
        with tracer.tool_span("read_measurements", call_id="c1"):
            raise ValueError("Patient Jane Doe not found")
    span = mem.spans[-1]
    assert span.status == "error" and span.attributes["error.type"] == "ValueError"
    assert "Jane" not in json.dumps(T.to_otlp_json(mem.spans))


# ------------------------------------------------------------------ export
def test_rc116_exporter_is_off_by_default(monkeypatch):
    monkeypatch.delenv("MSTOOL_AGENT_TRACE_EXPORTER", raising=False)
    assert isinstance(T.exporter_from_env(), T.NoopExporter)
    for value in ("memory", "otlp", "console", "https://collector.example.com", "OTLP-JSON-FILE"):
        monkeypatch.setenv("MSTOOL_AGENT_TRACE_EXPORTER", value)
        assert isinstance(T.exporter_from_env(), T.NoopExporter), value


def test_rc116_file_exporter_needs_both_settings_and_writes_otlp_json(monkeypatch, tmp_path):
    monkeypatch.setenv("MSTOOL_AGENT_TRACE_EXPORTER", "otlp-json-file")
    monkeypatch.delenv("MSTOOL_AGENT_TRACE_FILE", raising=False)
    assert isinstance(T.exporter_from_env(), T.NoopExporter)
    out = tmp_path / "spans.jsonl"
    monkeypatch.setenv("MSTOOL_AGENT_TRACE_FILE", str(out))
    exporter = T.exporter_from_env()
    assert isinstance(exporter, T.OtlpJsonFileExporter)
    tracer = T.Tracer(exporter)
    with tracer.agent_span("test-agent", provider="anthropic"):
        pass
    doc = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    scope = doc["resourceSpans"][0]["scopeSpans"][0]
    assert scope["schemaUrl"] == T.SEMCONV_SCHEMA_URL
    assert scope["spans"][0]["name"] == "invoke_agent test-agent"


def test_rc116_noop_exporter_keeps_nothing():
    tracer = T.Tracer(T.NoopExporter())
    with tracer.agent_span("test-agent", provider="anthropic"):
        pass
    assert len(tracer.finished) == 0


# ------------------------------------------------------------------ links
def test_rc116_trace_adopts_the_request_trace_id_and_names_the_audit_request(tracer, mem):
    cloud_trace = "0af7651916cd43dd8448eb211c80319c"
    with tracer.agent_span("test-agent", provider="anthropic", trace_id=cloud_trace, audit_request_id="req-42"):
        pass
    span = mem.spans[-1]
    assert span.trace_id == cloud_trace
    assert span.attributes["mstool.audit.request_id"] == "req-42"


@pytest.mark.parametrize("bad", ["0af7651916cd43dd8448eb211c80319", "00000000000000000000000000000000",
                                 "0AF7651916CD43DD8448EB211C80319C/1;o=1", "not-a-trace"])
def test_rc116_malformed_request_trace_id_gets_a_fresh_one(tracer, mem, bad):
    with tracer.agent_span("test-agent", provider="anthropic", trace_id=bad):
        pass
    tid = mem.spans[-1].trace_id
    assert tid != bad and len(tid) == 32 and int(tid, 16) != 0


def test_rc116_signoff_is_linked_to_the_run_without_identifiers(tracer, mem):
    events = []
    with tracer.agent_span("test-agent", provider="anthropic") as run:
        pass
    link = T.link_signoff(tracer, run_trace_id=run.trace_id, run_span_id=run.span_id,
                          signoff_record_id="signoff/Jane-Doe-1970", content_sha256=T.content_sha256("signed text"),
                          reader_id="dr.house@hospital.example", audit=events.append)
    span = mem.spans[-1]
    assert span.name == "mstool.signoff"
    assert span.links == [(run.trace_id, run.span_id)]
    assert span.attributes["mstool.signoff.content_sha256"] == T.content_sha256("signed text")
    assert span.attributes["mstool.signoff.reader_key"].startswith("hmac:")
    assert span.attributes["mstool.signoff.record_key"].startswith("hmac:")
    dumped = json.dumps(T.to_otlp_json(mem.spans)) + json.dumps(events)
    assert "Jane" not in dumped and "house" not in dumped
    assert events and events[-1]["trace_id"] == run.trace_id and events[-1]["event"] == "agent.signoff_linked"
    assert link["signoff_trace_id"] == span.trace_id


def test_rc116_every_exported_attribute_is_on_the_allow_list(tracer, mem):
    with tracer.agent_span("test-agent", provider="anthropic") as run:
        run.set("mstool.run.status", "delivered")
        with tracer.verify_span("claim-verifier", verdict="withheld", withheld=2):
            pass
    for span in mem.spans:
        assert set(span.attributes) <= set(T.ALLOWED_ATTRIBUTES), set(span.attributes) - set(T.ALLOWED_ATTRIBUTES)
