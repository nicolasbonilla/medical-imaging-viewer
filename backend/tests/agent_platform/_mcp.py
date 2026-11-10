"""Load the REAL MCP server modules (backend/app/mcp/) offline, for the evals, the red team and the card check.

fastmcp is not needed: a stub FastMCP records the server's instructions, tools and resources and returns
each decorated function unchanged, so the tool bodies under test are exactly the repository's. The
module is loaded under a private name (never as app.mcp.*), so nothing else in the session sees it.
``FakeBackend`` replaces the module's ``api_get`` / ``api_post_compute`` with an offline store of two
patients and records every request, to prove which ids a run asked the backend for.
"""
import importlib.util
import sys
import types
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parents[2] / "app" / "mcp"


class StubFastMCP:
    def __init__(self, name, description=None, instructions=None, **kwargs):
        self.name = name
        self.description = description
        self.instructions = instructions
        self.tools = {}
        self.resources = {}

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
        raise RuntimeError("MCP servers never run inside the tests")


def load_mcp_module(name: str):
    """Import backend/app/mcp/<name>.py with the stub FastMCP; returns the module."""
    stub = types.ModuleType("fastmcp")
    stub.FastMCP = StubFastMCP
    saved = sys.modules.get("fastmcp")
    sys.modules["fastmcp"] = stub
    try:
        spec = importlib.util.spec_from_file_location(f"mstool_agent_tests_{name}", MCP_DIR / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("fastmcp", None)
        else:
            sys.modules["fastmcp"] = saved
    return module


STUDY = {"seg-A": {"file": "file-A", "lesions": 7, "volume_ml": 3.1},
         "seg-B": {"file": "file-B", "lesions": 6, "volume_ml": 2.9}}
OTHER_PATIENT = {"seg-OTHER": {"file": "file-OTHER", "lesions": 40, "volume_ml": 22.0}}


class FakeBackend:
    """Two patients: the run's study (seg-A, seg-B) and another patient the clinician may also read
    (seg-OTHER) — the backend's own object authorization (RC-029) would serve both to that clinician."""

    def __init__(self, inject_note: str = ""):
        self.requests = []
        self.inject_note = inject_note
        self.data = {**STUDY, **OTHER_PATIENT}

    def _seg(self, path):
        parts = path.strip("/").split("/")
        return parts[1] if len(parts) > 1 and parts[0] == "segmentation" else None

    async def api_get(self, path, params=None, timeout=60.0):
        self.requests.append(("GET", path))
        seg = self._seg(path)
        rec = self.data.get(seg)
        if rec is None:
            raise LookupError("404")
        if path.endswith("/lesion-analysis"):
            out = {"segmentation_id": seg, "total_lesions": rec["lesions"], "total_volume_ml": rec["volume_ml"],
                   "PatientName": "Doe^Jane", "patient_birth_date": "19700101"}
            if self.inject_note:
                out["note"] = self.inject_note
            return out
        if path.endswith("/dis-assessment"):
            return {"evaluation_status": "not_evaluated"}
        return {"segmentation_id": seg, "file_id": rec["file"], "metadata": {"analysis_data": {}}}

    async def api_post_compute(self, path, json_data=None, timeout=120.0):
        self.requests.append(("POST", path, json_data))
        return {"abstained": False, "new_candidates": 2, "enlarged_candidates": 1,
                "baseline_id": (json_data or {}).get("tp1", {}).get("id"),
                "followup_id": (json_data or {}).get("tp2", {}).get("id")}

    def asked_for(self, resource_id: str) -> bool:
        return any(resource_id in str(r) for r in self.requests)


def wire(module, backend: FakeBackend):
    module.api_get = backend.api_get
    module.api_post_compute = backend.api_post_compute
    return module


ASSISTANT_TOOLS = ("get_region_classification", "summarize_dis_items", "analyze_lesions", "compare_longitudinal",
                   "generate_ms_report")


def assistant_tools(backend: FakeBackend):
    """The real ms_clinical_server tool functions, wired to the offline backend."""
    module = wire(load_mcp_module("ms_clinical_server"), backend)
    return {name: getattr(module, name) for name in ASSISTANT_TOOLS}, module
