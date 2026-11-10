"""Synthetic data shared by the agent-platform suites (no patient data)."""
from datetime import datetime, timezone

FIXED_NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def make_registry_data(**overrides):
    """A synthetic registry: two approved test agents, one pending, one model per retirement state.

    Never the production registry: the production entries are all pending the owner's approval, so
    every run with them is refused (fail closed), which is itself tested in test_registry.py.
    """
    data = {
        "registry_version": "test-1",
        "status": "TEST FIXTURE",
        "models": {
            "model-current": {"provider": "anthropic", "api_version": "2023-06-01", "retires_on": None,
                              "use_status": "in_use", "price_usd_per_mtok": {"input": 3.0, "output": 15.0}},
            "model-retiring": {"provider": "anthropic", "api_version": "2023-06-01", "retires_on": "2026-11-30",
                               "use_status": "in_use", "price_usd_per_mtok": {"input": 3.0, "output": 15.0}},
            "model-retired": {"provider": "anthropic", "api_version": "2023-06-01", "retires_on": "2026-11-01",
                              "use_status": "in_use", "price_usd_per_mtok": {"input": 3.0, "output": 15.0}},
            "model-unapproved": {"provider": "anthropic", "api_version": "2023-06-01", "retires_on": None,
                                 "use_status": "candidate", "price_usd_per_mtok": {"input": 2.0, "output": 10.0}},
            "model-unpriced": {"provider": "anthropic", "api_version": "2023-06-01", "retires_on": None,
                               "use_status": "in_use"},
        },
        "tools": {
            "read_measurements": {"access": "read", "scope_arguments": ["segmentation_id"]},
            "compare_visits": {"access": "compute", "scope_arguments": ["baseline_id", "followup_id"]},
            "write_annotation": {"access": "write", "scope_arguments": ["segmentation_id"]},
        },
        "agents": {
            "test-agent": {
                "purpose": "synthetic agent for the platform tests",
                "approval": {"status": "approved", "ref": "test fixture"},
                "allowed_models": ["model-current", "model-retiring", "model-retired", "model-unapproved",
                                   "model-unpriced"],
                "allowed_tools": ["read_measurements", "compare_visits"],
                "cost_cap_usd": {"per_study": 0.50, "per_day": 2.00},
                "limits": {"max_steps": 4, "max_tool_calls": 6, "max_tool_result_bytes": 20000,
                           "max_input_tokens": 20000, "max_output_tokens": 2000},
                "parameters": {"max_tokens": 1000},
            },
            "other-agent": {
                "purpose": "second synthetic agent (per-agent isolation of switches and costs)",
                "approval": {"status": "approved", "ref": "test fixture"},
                "allowed_models": ["model-current"],
                "allowed_tools": ["read_measurements"],
                "cost_cap_usd": {"per_study": 0.50, "per_day": 2.00},
                "limits": {"max_steps": 4, "max_tool_calls": 6, "max_tool_result_bytes": 20000,
                           "max_input_tokens": 20000, "max_output_tokens": 2000},
                "parameters": {"max_tokens": 1000},
            },
            "pending-agent": {
                "purpose": "synthetic agent awaiting approval",
                "approval": {"status": "pending", "ref": "test fixture"},
                "allowed_models": ["model-current"],
                "allowed_tools": ["read_measurements"],
                "cost_cap_usd": {"per_study": 0.50, "per_day": 2.00},
                "limits": {"max_steps": 4, "max_tool_calls": 6, "max_tool_result_bytes": 20000,
                           "max_input_tokens": 20000, "max_output_tokens": 2000},
                "parameters": {"max_tokens": 1000},
            },
        },
    }
    data.update(overrides)
    return data
