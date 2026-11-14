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
import importlib.util
import inspect
import json
import re
import sys
import types
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from app.agent_platform.hashing import sha256_text
from app.agent_platform.registry import RETIREMENT_WARNING_DAYS, retirement_state  # noqa: F401 — one rule

CARD_SCHEMA = "mstool.agent-card/1"
CARDS_DIR = Path(__file__).with_name("cards")
BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent


# ------------------------------------------------------------------ MCP modules without fastmcp
class StubFastMCP:
    """The constructor of fastmcp 3.x (the pinned version): ``name`` and ``instructions``; any other keyword is
    refused as the real one refuses it (fifth review of PR #79: 2.3.0 silently ignored ``description=``)."""

    def __init__(self, name=None, instructions=None, **kwargs):
        if kwargs:
            raise TypeError(f"FastMCP() got unexpected keyword argument(s): {', '.join(map(repr, kwargs))}")
        self.name, self.instructions = name, instructions
        self.description = None                      # never sent to the client
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


class StubContext:
    """fastmcp's request Context: injected by the server, never a model-visible parameter (eighth review, F3)."""


def load_with_stub_fastmcp(path: Path, alias: str):
    stub = types.ModuleType("fastmcp")
    stub.FastMCP = StubFastMCP
    stub.Context = StubContext
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
    if name.startswith("verified_report."):
        return "backend/app/services/verified_report.py"
    if name.startswith("mcp."):
        return f"backend/app/mcp/{name.split('.')[1]}.py"
    if name.startswith("agent_platform."):
        return f"backend/app/agent_platform/{name.split('.')[1]}.py"
    return ""


def report_drafter_templates() -> Dict[str, str]:
    """The fixed texts the verified report (PR #78) sends to the model: the one system prompt, the language line of
    each report language and every regeneration message. Reconciled 2026-11-14 when main was merged into PR #79 (the
    templates of the former report builder no longer exist)."""
    from app.services import verified_report as v
    out = {"verified_report.SYSTEM_PROMPT": v.SYSTEM_PROMPT}
    for lang in v.LANGUAGES:
        out[f"verified_report.user_lang_line({lang})"] = v.user_lang_line(lang)
    for const in sorted(n for n in dir(v) if n.endswith("_MESSAGE") and isinstance(getattr(v, n), str)):
        out[f"verified_report.{const}"] = getattr(v, const)
    out.update(_platform_templates())
    return out


def _annotation(value: Any) -> Optional[str]:
    if value is inspect.Parameter.empty:
        return None
    return value if isinstance(value, str) else getattr(value, "__name__", None) or repr(value)


def tool_definition(name: str, fn: Callable) -> str:
    """Second review of PR #79, finding 9: the FULL tool definition a client model receives — name, description,
    every parameter (name, kind, annotation, default) and the signature — as canonical JSON. The input schema
    FastMCP sends is derived from exactly these; adding, removing, retyping or re-defaulting a parameter changes
    the hash."""
    sig = inspect.signature(fn)
    # Eighth review (F3): a parameter annotated with fastmcp's Context is hidden from the client, exactly as the
    # real server advertises the tool.
    sig = sig.replace(parameters=[p for p in sig.parameters.values()
                                  if getattr(p.annotation, "__name__", "") not in ("Context", "StubContext")])
    params = [{"name": p.name, "kind": p.kind.name, "annotation": _annotation(p.annotation),
               "default": None if p.default is inspect.Parameter.empty else repr(p.default),
               "required": p.default is inspect.Parameter.empty} for p in sig.parameters.values()]
    return json.dumps({"name": name, "description": (fn.__doc__ or "").strip(), "parameters": params,
                       "returns": _annotation(sig.return_annotation), "signature": f"{name}{sig}"},
                      sort_keys=True, ensure_ascii=False)


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
            out[f"mcp.{server}.tool[{name}].definition"] = tool_definition(name, fn)
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


def _card_retirements(today, agents: Optional[Iterable[str]]):
    """(agent id, model, state, days) for every card's model, by the REGISTRY's one retirement rule (fourth
    review of PR #79, finding 10): the agents are those with templates (TEMPLATE_SOURCES), never a hard-coded
    list, and the threshold and arithmetic are registry.retirement_state's."""
    from datetime import date as _date
    for agent_id in (sorted(TEMPLATE_SOURCES) if agents is None else agents):
        model = load_card(agent_id).get("model") or {}
        retires_on = _date.fromisoformat(model["retires_on"]) if model.get("retires_on") else None
        state, days = retirement_state(retires_on, today)
        yield agent_id, model, state, days


def retirement_problems(today, agents: Optional[Iterable[str]] = None) -> List[str]:
    """Cards whose model has retired on ``today`` (an injected date: third review of PR #79, finding 5). The
    wall-clock check runs in its own scheduled job (.github/workflows/agent-model-retirement.yml), so a model
    retirement never turns unrelated pull requests red; at call time the registry refuses the retired model."""
    return [f"{agent_id}: model {model['id']} retired on {model['retires_on']}; the platform refuses it "
            "— run the re-validation protocol for a successor (RVP-AGT-001, D-AGT-1)"
            for agent_id, model, state, _ in _card_retirements(today, agents) if state == "retired"]


def retirement_warnings(today, agents: Optional[Iterable[str]] = None) -> List[str]:
    return [f"{agent_id}: model {model['id']} retires on {model['retires_on']} ({days} days)"
            for agent_id, model, state, days in _card_retirements(today, agents) if state == "warning"]


def availability_alerts(today, data: Optional[Dict[str, Any]] = None) -> List[str]:
    """Eighth review of PR #79 (F2): an agent whose every approved ('in_use') model retires within the warning window
    becomes UNAVAILABLE on that date unless the owner approves a successor through RVP-AGT-001 (D-AGT-1). Said loudly
    by the daily job (an error, not a warning)."""
    from datetime import date as _date
    data = data or json.loads((Path(__file__).with_name("agents.json")).read_text(encoding="utf-8"))
    models = data["models"]
    candidates = sorted(m for m, v in models.items() if v.get("use_status") == "candidate")
    out = []
    for aid, agent in sorted(data["agents"].items()):
        usable = [m for m in agent.get("allowed_models", []) if models.get(m, {}).get("use_status") == "in_use"]
        if not usable:
            continue
        ends = []
        for m in usable:
            retires = models[m].get("retires_on")
            state, _days = retirement_state(_date.fromisoformat(retires) if retires else None, today)
            if state == "ok":
                break
            ends.append(retires)
        else:
            out.append(f"{aid}: UNAVAILABLE from {max(ends)} — its only approved model(s) {', '.join(usable)} retire then; "
                       f"the successor {', '.join(candidates) or '(none registered)'} is 'candidate', not re-validated. "
                       f"Owner decision D-AGT-1 (RVP-AGT-001). PR #78's verified report already uses claude-sonnet-5-5: "
                       f"reconcile both when D-AGT-1 is decided.")
    return out


def main(argv: List[str], today=None) -> int:  # pragma: no cover — maintainer tool and the scheduled retirement job
    if argv == ["--retirement"]:
        from datetime import datetime, timezone
        today = today or datetime.now(timezone.utc).date()
        for w in retirement_warnings(today):
            print(f"::warning::{w}")
        problems = retirement_problems(today) + availability_alerts(today)
        for p in problems:
            print(f"::error::{p}")
        return 1 if problems else 0
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
