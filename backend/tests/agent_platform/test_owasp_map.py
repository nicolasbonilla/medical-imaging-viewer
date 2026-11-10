"""The red-team map covers OWASP Agentic 2026 and OWASP LLM 2025 item by item (REQ-AGT-004; RC-118).

DRAFT, PENDING owner approval. Every ASI01..ASI10 and LLM01..LLM10 item names at least one executable
test that exists (a function defined in the named file), and every red-team test is mapped to at least
one item, so neither side can drift: deleting a test, or adding an attack outside the map, turns CI red.
"""
import ast
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
MAP = json.loads((HERE / "owasp_map.json").read_text(encoding="utf-8"))
ITEMS = MAP["items"]
EXPECTED = [f"ASI{i:02d}" for i in range(1, 11)] + [f"LLM{i:02d}" for i in range(1, 11)]
TITLES = {"ASI01": "Agent Goal Hijack", "ASI02": "Tool Misuse and Exploitation", "ASI03": "Identity and Privilege Abuse",
          "ASI04": "Agentic Supply Chain Vulnerabilities", "ASI05": "Unexpected Code Execution",
          "ASI06": "Memory and Context Poisoning", "ASI07": "Insecure Inter-Agent Communication",
          "ASI08": "Cascading Failures", "ASI09": "Human-Agent Trust Exploitation", "ASI10": "Rogue Agents",
          "LLM01": "Prompt Injection", "LLM02": "Sensitive Information Disclosure", "LLM03": "Supply Chain",
          "LLM04": "Data and Model Poisoning", "LLM05": "Improper Output Handling", "LLM06": "Excessive Agency",
          "LLM07": "System Prompt Leakage", "LLM08": "Vector and Embedding Weaknesses", "LLM09": "Misinformation",
          "LLM10": "Unbounded Consumption"}


def _functions(file_name):
    tree = ast.parse((HERE / file_name).read_text(encoding="utf-8"))
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def test_rc118_every_owasp_item_is_mapped_with_its_title():
    assert sorted(ITEMS) == sorted(EXPECTED)
    for item_id, item in ITEMS.items():
        assert item["title"] == TITLES[item_id], item_id


@pytest.mark.parametrize("item_id", EXPECTED)
def test_rc118_every_owasp_item_names_existing_executable_tests(item_id):
    item = ITEMS[item_id]
    assert item["status"] == "tested", f"{item_id}: every item is covered by an executable test in this release"
    assert item["tests"], item_id
    for ref in item["tests"]:
        file_name, _, func = ref.partition("::")
        assert func in _functions(file_name), f"{item_id}: {ref} does not exist"
        assert func.startswith("test_rc1"), f"{item_id}: {ref} is not named for a risk control"
    assert item["controls"] and all(c.startswith("RC-1") for c in item["controls"])


def test_rc118_every_red_team_test_is_mapped():
    mapped = {ref.partition("::")[2] for item in ITEMS.values() for ref in item["tests"]
              if ref.startswith("test_redteam.py::")}
    defined = {f for f in _functions("test_redteam.py") if f.startswith("test_")}
    assert defined - mapped == set(), f"red-team tests outside the OWASP map: {sorted(defined - mapped)}"
