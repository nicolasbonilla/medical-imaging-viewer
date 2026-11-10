"""
Model and prompt card per agent: the machine-readable SOUP record of what an agent sends to which model.

REQ-AGT-005; risk control RC-117 (a model or prompt-template change that is not recorded in the card turns
CI red); hazard HAZ-023 (behaviour changes after an unrecorded model or prompt change). DRAFT, PENDING
owner approval.

A card (``cards/<agent_id>.json``) records: the exact model id, provider, platform, API version and SDK;
the parameters sent; for MCP agents the transport, the MCP SDK and the protocol revision as installed; the
SHA-256 of EVERY prompt template as it is actually rendered (each variant the code can produce is hashed
separately); the eval case file it was validated with; and a change log. ``check_card`` recomputes all of
it from the code and reports every difference; backend/tests/agent_platform/test_cards.py runs it in CI.

Templates are rendered by importing the modules that own them, never by copying their text: the card is
bound to what the code sends. The MCP server modules are imported with a stub ``FastMCP`` that records the
server's ``instructions`` and resource functions (so neither fastmcp nor a running server is needed).

Maintainers regenerate a card with ``python -m app.agent_platform.cards --write <agent_id>`` AFTER running
the re-validation protocol (docs/iec62304/agent_platform/Agent_Revalidation_Protocol.md); the card diff,
with its change-log entry, is what the reviewer and the owner see.

@module agent_platform.cards
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.util
import inspect
import json
import re
import sys
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

CARD_SCHEMA = "mstool.agent-card/1"
CARDS_DIR = Path(__file__).with_name("cards")
BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ MCP modules without fastmcp
class StubFastMCP:
    def __init__(self, name, description=None, instructions=None, **kwargs):
        self.name, self.description, self.instructions = name, description, instructions
        self.tools: Dict[str, Callable] = {}
        self.resources: Dict[str, Callable] = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco

    def resource(self, uri, *args, **kwargs):
        def deco(fn):
            self.resources[uri] = fn
            return fn
        return deco

    def run(self, *args, **kwargs):
        raise RuntimeError("an MCP server is never run while its card is computed")


def load_with_stub_fastmcp(path: Path, alias: str):
    stub = types.ModuleType("fastmcp")
    stub.FastMCP = StubFastMCP
    saved = sys.modules.get("fastmcp")
    sys.modules["fastmcp"] = stub
    try:
        spec = importlib.util.spec_from_file_location(alias, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("fastmcp", None)
        else:
            sys.modules["fastmcp"] = saved
    return module


# ------------------------------------------------------------------ rendered templates per agent
def _platform_templates() -> Dict[str, str]:
    from app.agent_platform.untrusted import UNTRUSTED_DATA_RULE
    return {"agent_platform.untrusted.UNTRUSTED_DATA_RULE": UNTRUSTED_DATA_RULE}


async def _await(value):
    return await value


def template_source(name: str) -> str:
    """The repository file that owns a template, from the template's name."""
    if name.startswith("brain_report_service."):
        return "backend/app/services/brain_report_service.py"
    if name.startswith("mcp."):
        return f"backend/app/mcp/{name.split('.')[1]}.py"
    if name.startswith("agent_platform."):
        return f"backend/app/agent_platform/{name.split('.')[1]}.py"
    return ""


def report_drafter_templates() -> Dict[str, str]:
    from app.services import brain_report_service as b
    out = {}
    for name, text in sorted(b.REPORT_TEMPLATES.items()):
        out[f"brain_report_service.REPORT_TEMPLATES[{name}]"] = text
        out[f"brain_report_service.dis_not_evaluated_template(REPORT_TEMPLATES[{name}])"] = \
            b.dis_not_evaluated_template(text)
    for const in ("DIS_NOT_EVALUATED_PROMPT", "CLINICIAN_TEXT_INSTRUCTION", "REGIONS_NOT_CONFIRMED_LINE"):
        out[f"brain_report_service.{const}"] = getattr(b, const)
    out.update(_platform_templates())
    return out


def ms_clinical_assistant_templates() -> Dict[str, str]:
    out = {}
    for server in ("ms_clinical_server", "imaging_server"):
        module = load_with_stub_fastmcp(BACKEND / "app" / "mcp" / f"{server}.py", f"mstool_card_{server}")
        mcp = module.mcp
        if mcp.instructions:
            out[f"mcp.{server}.instructions"] = mcp.instructions
        if mcp.description:
            out[f"mcp.{server}.description"] = mcp.description
        for uri, fn in sorted(mcp.resources.items()):
            value = fn()
            if inspect.isawaitable(value):
                value = asyncio.run(_await(value))
            out[f"mcp.{server}.resource[{uri}]"] = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        for name, fn in sorted(mcp.tools.items()):
            out[f"mcp.{server}.tool[{name}].description"] = (fn.__doc__ or "").strip()
    out.update(_platform_templates())
    return out


TEMPLATE_SOURCES: Dict[str, Callable[[], Dict[str, str]]] = {
    "report-drafter": report_drafter_templates,
    "ms-clinical-assistant": ms_clinical_assistant_templates,
}


# ------------------------------------------------------------------ facts read from the code
def config_default(field: str) -> Any:
    """The default of a Settings field in app/core/config.py, read from its source (no settings import)."""
    tree = ast.parse((BACKEND / "app" / "core" / "config.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == field:
            call = node.value
            if isinstance(call, ast.Call):
                for kw in call.keywords:
                    if kw.arg == "default":
                        return ast.literal_eval(kw.value)
    return None


def requirement_pin(package: str) -> Optional[str]:
    for line in (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(rf"^\s*{re.escape(package)}\s*==\s*([^\s#]+)", line, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def installed_mcp() -> Optional[Dict[str, str]]:
    """The MCP SDK as installed in this environment, or None when it is not installed."""
    try:
        import importlib.metadata as md
        import mcp.types as mt
        return {"mcp_sdk_version": md.version("mcp"), "latest_protocol_version": str(mt.LATEST_PROTOCOL_VERSION)}
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ cards
def card_path(agent_id: str) -> Path:
    return CARDS_DIR / f"{agent_id}.json"


def load_card(agent_id: str) -> Dict[str, Any]:
    return json.loads(card_path(agent_id).read_text(encoding="utf-8"))


def rendered_hashes(agent_id: str) -> Dict[str, Dict[str, Any]]:
    return {name: {"sha256": sha256_text(text), "chars": len(text)}
            for name, text in sorted(TEMPLATE_SOURCES[agent_id]().items())}


def check_card(agent_id: str, registry_data: Dict[str, Any]) -> List[str]:
    """Every difference between the card and the code / registry (empty list = the card is current)."""
    card = load_card(agent_id)
    problems: List[str] = []
    if card.get("schema") != CARD_SCHEMA or card.get("agent_id") != agent_id:
        return [f"{agent_id}: not a {CARD_SCHEMA} card for this agent"]
    current = rendered_hashes(agent_id)
    recorded = card.get("prompt_templates") or {}
    for name in sorted(set(current) | set(recorded)):
        if name not in recorded:
            problems.append(f"template {name} is sent by the code but not recorded in the card")
        elif name not in current:
            problems.append(f"template {name} is recorded in the card but no longer produced by the code")
        elif recorded[name].get("sha256") != current[name]["sha256"]:
            problems.append(f"template {name} changed (card {recorded[name].get('sha256', '')[:12]}, "
                            f"code {current[name]['sha256'][:12]}) without the card changing")
    agent = registry_data["agents"][agent_id]
    model = card.get("model") or {}
    if agent.get("model_control") == "server":
        mid = model.get("id")
        if mid not in agent["allowed_models"]:
            problems.append(f"card model {mid!r} is not on the registry allow-list {agent['allowed_models']}")
        reg_model = registry_data["models"].get(mid) or {}
        for key in ("api_version", "retires_on", "provider"):
            if model.get(key) != reg_model.get(key):
                problems.append(f"card model.{key} {model.get(key)!r} differs from the registry {reg_model.get(key)!r}")
        if agent_id == "report-drafter":
            default = config_default("CLAUDE_MODEL")
            if default != mid:
                problems.append(f"the code's default model {default!r} differs from the card model {mid!r}")
            if config_default("CLAUDE_MAX_TOKENS") != (card.get("parameters") or {}).get("max_tokens"):
                problems.append("CLAUDE_MAX_TOKENS default differs from the card's max_tokens")
    for pkg, pinned in (card.get("sdk_pins") or {}).items():
        if requirement_pin(pkg) != pinned:
            problems.append(f"requirements.txt pins {pkg}=={requirement_pin(pkg)}, the card records {pinned}")
    params = card.get("parameters") or {}
    for key, value in (agent.get("parameters") or {}).items():
        if params.get(key) != value:
            problems.append(f"registry parameter {key}={value!r} differs from the card ({params.get(key)!r})")
    log = card.get("changes") or []
    if not log or log[-1].get("card_version") != card.get("card_version"):
        problems.append("the card's change log does not end with an entry for its current card_version")
    protocol = (card.get("revalidation") or {}).get("protocol")
    if not protocol or not (REPO / protocol).exists():
        problems.append("the card names no existing re-validation protocol")
    cases = (card.get("evals") or {}).get("case_file")
    if not cases or not (REPO / cases).exists():
        problems.append("the card names no existing eval case file")
    return problems


def write_card(agent_id: str) -> None:
    """Refresh the template hashes of an existing card (after re-validation); everything else is edited by hand."""
    card = load_card(agent_id)
    card["prompt_templates"] = {name: {**v, "source": template_source(name)}
                                for name, v in rendered_hashes(agent_id).items()}
    card_path(agent_id).write_text(json.dumps(card, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                                   newline="\n")


def main(argv: List[str]) -> int:  # pragma: no cover — maintainer tool
    if len(argv) == 2 and argv[0] in ("--write", "--check"):
        if argv[0] == "--write":
            write_card(argv[1])
        data = json.loads((Path(__file__).with_name("agents.json")).read_text(encoding="utf-8"))
        problems = check_card(argv[1], data)
        print("\n".join(problems) or "card is current")
        return 1 if problems else 0
    print("usage: python -m app.agent_platform.cards --check|--write <agent_id>")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
