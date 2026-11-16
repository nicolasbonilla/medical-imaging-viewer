"""Offline tests of the OpenAI-compatible provider for open models on Vertex AI (no network, no spend)."""
import json

from research.agents_benchmark import ledger as L
from research.agents_benchmark.providers import VertexOpenAI, provider_for


def test_messages_round_trip_a_tool_call():
    req = {"system": "S", "max_tokens": 700, "tool_choice": "auto",
           "tools": [{"name": "get_second_segmentation", "description": "d", "input_schema": {"type": "object"}}],
           "messages": [{"role": "user", "content": "record"},
                        {"role": "assistant", "content": [
                            {"type": "text", "text": "Checking.", "_gemini_content": {"x": 1}},
                            {"type": "tool_use", "id": "call_1", "name": "get_second_segmentation", "input": {}}]},
                        {"role": "user", "content": [
                            {"type": "tool_result", "tool_use_id": "call_1", "content": json.dumps({"n": 2})}]}]}
    body = VertexOpenAI.body("openai/gpt-oss-120b-maas", req)
    m = body["messages"]
    assert m[0] == {"role": "system", "content": "S"} and m[1] == {"role": "user", "content": "record"}
    assert m[2]["tool_calls"][0]["function"] == {"name": "get_second_segmentation", "arguments": "{}"}
    assert m[3] == {"role": "tool", "tool_call_id": "call_1", "content": '{"n": 2}'}
    assert body["tools"][0]["function"]["name"] == "get_second_segmentation" and body["tool_choice"] == "auto"
    assert "_gemini_content" not in json.dumps(m)                       # private keys never leave the machine


def test_parse_text_tool_call_and_cut_reports():
    d = {"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
        {"id": "c9", "function": {"name": "get_regions", "arguments": '{"a": 1}'}}]}}],
         "usage": {"prompt_tokens": 100, "completion_tokens": 10}}
    r = VertexOpenAI.parse(d)
    assert r["stop_reason"] == "tool_use" and r["content"][0] == {"type": "tool_use", "id": "c9",
                                                                   "name": "get_regions", "input": {"a": 1}}
    cut = VertexOpenAI.parse({"choices": [{"finish_reason": "length", "message": {"content": "## Find"}}]})
    assert cut["stop_reason"] == "max_tokens" and cut["text"] == "## Find"


def test_pricing_and_routing(tmp_path):
    assert L.provider_of("openai/gpt-oss-120b-maas") == "maas"
    usd = L.cost("openai/gpt-oss-120b-maas", {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000})
    assert abs(usd - (0.09 + 0.36)) < 1e-9
    assert isinstance(provider_for("deepseek-ai/deepseek-v4.1-flash-maas", tmp_path), VertexOpenAI)
