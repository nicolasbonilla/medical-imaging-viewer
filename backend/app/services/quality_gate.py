"""Single quality gate — BASELINE SKELETON (failing-first commit; replaced by the implementation).

It models the app as it is today: there is no single gate, so every AI step proceeds.
"""
import json
from pathlib import Path

POLICY_PATH = Path(__file__).with_name("quality_gate_policy.json")


def load_policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def evaluate(inputs, policy=None):
    return {"decision": "proceed", "ai_may_run": True, "ai_output_allowed": True, "codes": [], "checks": []}


def canonical(result):
    return str(result.get("decision"))


def run_quality_gate(inputs, *, registry=None, tracer=None, study_key="", actor=None, trace_id=None):
    return evaluate(inputs)
