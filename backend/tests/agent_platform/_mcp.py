"""Load the REAL MCP server modules (backend/app/mcp/) offline, for the evals, the red team and the card check.

fastmcp is not needed: a stub FastMCP records the server's instructions, tools and resources and returns
each decorated function unchanged, so the tool bodies under test are exactly the repository's. The
module is loaded under a private name (never as app.mcp.*), so nothing else in the session sees it.
``FakeBackend`` replaces the module's ``api_get`` / ``api_post_compute`` with an offline store of two
patients and records every request, to prove which ids a run asked the backend for.
"""
from pathlib import Path

from app.agent_platform.cards import StubFastMCP, load_with_stub_fastmcp  # noqa: F401 — one stub, one loader

MCP_DIR = Path(__file__).resolve().parents[2] / "app" / "mcp"


def load_mcp_module(name: str):
    """Import backend/app/mcp/<name>.py with the card's stub FastMCP (third review of PR #79, finding 10: the
    card and the evals load the SAME server surface through ONE loader)."""
    return load_with_stub_fastmcp(MCP_DIR / f"{name}.py", f"mstool_agent_tests_{name}")


STUDY = {"seg-A": {"file": "file-A", "lesions": 7, "volume_ml": 3.1},
         "seg-B": {"file": "file-B", "lesions": 6, "volume_ml": 2.9}}
OTHER_PATIENT = {"seg-OTHER": {"file": "file-OTHER", "lesions": 40, "volume_ml": 22.0}}


class FakeBackend:
    """Two patients: the run's study (seg-A, seg-B) and another patient the clinician may also read
    (seg-OTHER) — the backend's own object authorization (RC-029) would serve both to that clinician.

    Third review of PR #79, finding 1: the responses have the REAL shapes (see _contract.py: produced by the
    app's own services on synthetic masks, wrapped as the routes wrap them), so a scope rule that refuses a
    legitimate result fails the evals and the red team, not only a unit test. The lesion analysis also
    carries two direct identifiers, to prove they are removed."""

    def __init__(self, inject_note: str = "", data=None):
        self.requests = []
        self.inject_note = inject_note
        self.data = data if data is not None else {**STUDY, **OTHER_PATIENT}

    def _seg(self, path):
        parts = path.strip("/").split("/")
        return parts[1] if len(parts) > 1 and parts[0] == "segmentation" else None

    async def api_get(self, path, params=None, timeout=60.0):
        from tests.agent_platform import _contract as K
        self.requests.append(("GET", path))
        if path.startswith("/imaging/"):
            file_id = path.split("/", 3)[3].rsplit("/", 1)[0] if path.startswith(("/imaging/slice/", "/imaging/matplotlib-2d/")) \
                else path.split("/", 3)[3]
            if path.startswith("/imaging/metadata/"):
                return K.image_metadata(file_id)
            if path.startswith("/imaging/slice/"):
                return K.slice_image(file_id, int(path.rsplit("/", 1)[1]))
            if path.startswith("/imaging/process/"):
                return K.processed(file_id)
            return K.matplotlib_view(file_id, int(path.rsplit("/", 1)[1]))
        if path == "/segmentation/list":
            return K.segmentation_list((params or {}).get("file_id"))
        seg = self._seg(path)
        rec = self.data.get(seg)
        if rec is None:
            raise LookupError("404")
        if path.endswith("/lesion-analysis"):
            out = K.lesion_analysis(seg)
            out.update({"PatientName": "Doe^Jane", "patient_birth_date": "19700101"})
            if self.inject_note:
                out["note"] = self.inject_note
            return out
        if path.endswith("/dis-assessment"):
            return K.dis_assessment()
        return K.segmentation_record(seg, rec["file"])

    async def api_post_compute(self, path, json_data=None, timeout=120.0):
        from tests.agent_platform import _contract as K
        self.requests.append(("POST", path, json_data))
        if path == "/ai/report/generate":
            return K.report()
        return K.longitudinal((json_data or {}).get("tp1", {}).get("id"), (json_data or {}).get("tp2", {}).get("id"))

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
