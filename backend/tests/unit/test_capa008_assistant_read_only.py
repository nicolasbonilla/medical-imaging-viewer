"""CAPA-008 — the AI assistant (MCP) layer is read-only, intended-use-bounded and never drafts a
report from nothing; CVS/PRL readings are counted faithfully and attributed to their reader.

Findings these tests bind (docs/iec62304/records/capa/CAPA-008_*.md):
- the assistant could WRITE clinical records (CVS/PRL readings feeding the McDonald summary,
  region classifications, PACS imports) through five servers with their own HTTP clients;
- its texts claimed "MS diagnosis", a "differential diagnosis" tool, HIPAA compliance, and
  "new lesions indicate disease activity";
- its MS report tool sent its data under field names the report route silently drops, so the
  language model drafted a "comprehensive clinical report" from NO measurement;
- the SSE (HTTP) mode had no authentication; three servers called unauthorized or
  non-existent routes;
- the app showed a "40% rule" as McDonald 2024 (it is not) and stored a client-chosen
  "annotated_by".

fastmcp is not needed: the MCP modules are checked by parsing their source (AST), and the
backend routes are exercised through the real app with dependency overrides.
Negative controls: scripts/safety/capa008_negative_controls.py.
"""
import ast
import asyncio
import inspect
import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from app.mcp import _backend
from app.security import get_current_active_user
from app.security.models import User, UserRole

ROOT = Path(__file__).resolve().parents[3]
MCP_DIR = ROOT / "backend" / "app" / "mcp"
FRONTEND = ROOT / "frontend" / "src"

SERVER_MODULES = {"imaging_server", "ms_clinical_server"}
EXPECTED_TOOLS = {
    "imaging_server": {"get_image_metadata", "get_slice_image", "process_image",
                       "list_segmentations", "get_matplotlib_visualization"},
    "ms_clinical_server": {"get_region_classification", "summarize_dis_items", "analyze_lesions",
                           "compare_longitudinal", "generate_ms_report"},
}
RETIRED_TOOLS = {"annotate_cvs_prl", "classify_lesions_magnims", "differential_diagnosis",
                 "detect_anomalies", "segment_brain_auto", "segment_interactive",
                 "compute_brain_volumes", "retrieve_series", "import_dicom_to_viewer",
                 "generate_brain_report", "evaluate_mcdonald_2024"}

# Phrases that contradict the intended use ("investigational, not for diagnosis") or claim
# what nothing verifies. Case-insensitive.
BANNED_PHRASES = [
    r"for ms diagnosis", r"supports ms diagnosis", r"diagnostic workflow", r"diagnostic biomarker",
    r"differential diagnosis", r"hipaa[- ]compliant", r"indicates? disease activity",
    r"treatment response", r"progression risk", r"40\s?% rule",
]


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_src(path))


def _server_files():
    return sorted(p for p in MCP_DIR.glob("*.py")
                  if p.stem not in {"__init__", "_backend", "run_all"})


def _decorated(tree, attr):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                target = d.func if isinstance(d, ast.Call) else d
                if isinstance(target, ast.Attribute) and target.attr == attr:
                    yield node


def _template(node) -> str:
    """'/segmentation/{}/lesion-analysis' from a str constant or an f-string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    raise AssertionError(f"backend path is not a literal: {ast.dump(node)[:120]}")


def _backend_calls(func_name):
    """(template, dict-literal-or-None) of every call to `func_name` in every server module."""
    out = []
    for path in _server_files():
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == func_name:
                body = node.args[1] if len(node.args) > 1 and isinstance(node.args[1], ast.Dict) else None
                out.append((path.stem, _template(node.args[0]), body))
    return out


def _mounted(method):
    routes = {}
    for r in app.routes:
        if isinstance(r, APIRoute) and method in r.methods and r.path.startswith("/api/v1"):
            routes[re.sub(r"\{[^}]+\}", "{}", r.path[len("/api/v1"):])] = r
    return routes


def _dependency_calls(dependant, acc=None):
    acc = set() if acc is None else acc
    for d in dependant.dependencies:
        acc.add(getattr(d.call, "__name__", str(d.call)))
        _dependency_calls(d, acc)
    return acc


def _authorizes_its_object(route) -> bool:
    if "require_segmentation_access" in _dependency_calls(route.dependant):
        return True
    source = inspect.getsource(route.endpoint)
    return any(f"{fn}(" in source for fn in ("require_imaging_access", "authorize_file_scope",
                                             "authorize_mask_specs"))


# ----------------------------------------------------------------------------- the MCP layer
@pytest.mark.unit
def test_rc033_only_the_two_read_only_servers_remain():
    assert {p.stem for p in _server_files()} == SERVER_MODULES
    run_all = _src(MCP_DIR / "run_all.py")
    assert 'SERVERS = ("imaging", "ms_clinical")' in run_all
    for name in ("segmentation_server", "report_server", "pacs_server"):
        assert name not in run_all


@pytest.mark.unit
def test_rc033_stdio_only_no_unauthenticated_http_transport():
    tree = _tree(MCP_DIR / "run_all.py")
    transports = [kw.value.value for n in ast.walk(tree) if isinstance(n, ast.Call)
                  for kw in n.keywords if kw.arg == "transport" and isinstance(kw.value, ast.Constant)]
    assert transports == ["stdio"], transports
    assert "--sse" not in _src(MCP_DIR / "run_all.py")


@pytest.mark.unit
def test_rc033_no_server_reaches_the_backend_except_through_the_read_only_client():
    for path in _server_files():
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                assert not any(n.split(".")[0] in {"httpx", "requests", "urllib", "aiohttp"} for n in names), \
                    f"{path.name} imports an HTTP client directly"
        assert "from app.mcp._backend import" in _src(path)


@pytest.mark.unit
def test_rc033_exact_tool_set_and_no_write_tool():
    for path in _server_files():
        tools = {f.name for f in _decorated(_tree(path), "tool")}
        assert tools == EXPECTED_TOOLS[path.stem], f"{path.stem}: {sorted(tools)}"
        assert not tools & RETIRED_TOOLS


@pytest.mark.unit
def test_rc033_every_post_is_a_compute_only_route():
    calls = _backend_calls("api_post_compute")
    assert calls, "expected the MS server to compare timepoints and draft reports"
    for module, path, _ in calls:
        assert path in _backend.COMPUTE_ONLY_POST_PATHS, f"{module}: POST {path}"


@pytest.mark.unit
def test_rc033_every_get_hits_a_mounted_route_that_authorizes_its_object():
    gets = _mounted("GET")
    for module, path, _ in _backend_calls("api_get"):
        assert path in gets, f"{module}: GET {path} is not a mounted route"
        route = gets[path]
        if "{}" in path or path == "/segmentation/list":
            assert _authorizes_its_object(route), f"{module}: GET {path} lacks object-level authorization"


@pytest.mark.unit
def test_rc033_compute_only_routes_are_mounted_authorized_and_store_nothing():
    posts = _mounted("POST")
    for path in _backend.COMPUTE_ONLY_POST_PATHS:
        assert path in posts, f"{path} is not a mounted POST route"
        source = inspect.getsource(posts[path].endpoint)
        for write in ("persist(", "upload_file(", "create_segmentation(", "save_mask("):
            assert write not in source, f"{path} stores data ({write})"
        if path.startswith("/segmentation/"):
            assert _authorizes_its_object(posts[path]), path


@pytest.mark.unit
def test_rc034_request_fields_sent_by_the_assistant_are_accepted_by_the_route():
    """Unknown field names are silently dropped by the backend: that is how the MS report
    tool drafted reports from nothing. Every literal key must be one the route reads."""
    posts = _mounted("POST")
    for module, path, body in _backend_calls("api_post_compute"):
        assert body is not None, f"{module}: POST {path} body must be a dict literal"
        keys = {k.value for k in body.keys}
        route = posts[path]
        model = next((getattr(p, "type_", None) or p.field_info.annotation
                      for p in route.dependant.body_params), None)
        if model is not None and hasattr(model, "model_fields"):
            assert keys <= set(model.model_fields), f"{module}: {path} unknown fields {keys - set(model.model_fields)}"
        else:
            source = inspect.getsource(route.endpoint)
            missing = {k for k in keys if f'"{k}"' not in source and f"'{k}'" not in source}
            assert not missing, f"{module}: {path} never reads {missing}"


@pytest.mark.unit
def test_rc034_report_findings_are_measurement_keys_the_service_consumes():
    from app.api.routes.ai_report import MEASUREMENT_FINDING_KEYS
    tree = _tree(MCP_DIR / "ms_clinical_server.py")
    keys = {n.slice.value for n in ast.walk(tree)
            if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "findings"
            and isinstance(n.slice, ast.Constant)}
    assert keys == {"lesion_analysis", "dis_assessment", "longitudinal"}
    assert keys <= MEASUREMENT_FINDING_KEYS
    service = _src(ROOT / "backend" / "app" / "services" / "brain_report_service.py")
    for k in keys:
        assert f'findings.get("{k}")' in service, f"the report service never reads {k}"


@pytest.mark.unit
@pytest.mark.parametrize("path", sorted(str(p) for p in MCP_DIR.glob("*.py"))
                         + [str(ROOT / "backend/app/api/routes/ai_report.py"),
                            str(ROOT / "backend/app/services/brain_report_service.py")],
                         ids=lambda p: Path(p).name)
def test_rc033_no_intended_use_contradiction_or_unverified_claim(path):
    text = Path(path).read_text(encoding="utf-8").lower()
    hits = [p for p in BANNED_PHRASES if re.search(p, text)]
    if Path(path).name == "brain_report_service.py":
        # The Class C report templates still carry some of these phrases: CAPA-008 CA-8.9 is
        # OPEN (template rewrite, owner review). Only the compliance claim is bound here.
        hits = [h for h in hits if h.startswith("hipaa")]
    assert not hits, f"{Path(path).name}: {hits}"


@pytest.mark.unit
def test_rc033_assistant_instructions_state_the_intended_use():
    text = _src(MCP_DIR / "ms_clinical_server.py")
    assert "NOT intended for diagnosis" in text
    assert "never infer a CVS or PRL status yourself" in text
    assert "Never call them disease activity" in text
    assert "not evaluable" in text and "never 'absent'" in text


# ----------------------------------------------------------------------------- the client
@pytest.mark.unit
@pytest.mark.parametrize("path", ["/segmentation/s1/lesion-annotations", "/segmentation/s1/classify-regions",
                                  "/segmentation/generate-zone-map", "/segmentation/create",
                                  "/dicomweb/import", "/ai/segment/auto", "/ai/volumetry/compute"])
def test_rc033_client_refuses_any_other_post_before_sending(path, monkeypatch):
    import httpx

    class _NoNetwork:
        def __init__(self, *a, **k):
            raise AssertionError("a request was about to be sent")

    monkeypatch.setattr(httpx, "AsyncClient", _NoNetwork)
    # A private loop: asyncio.run() would unset the global loop that later tests rely on.
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(_backend.AssistantWriteRefused):
            loop.run_until_complete(_backend.api_post_compute(path, {}))
    finally:
        loop.close()


@pytest.mark.unit
def test_rc033_client_removes_direct_identifiers_at_any_depth():
    raw = {"patient_name": "Doe^Jane", "PatientID": "123", "study_date": "20250101",
           "modality": "MR", "pixel_spacing": [1, 1],
           "series": [{"InstitutionName": "H", "AccessionNumber": "A1", "rows": 256,
                       "extra_fields": {"PatientBirthDate": "1980"}}]}
    clean = _backend.drop_direct_identifiers(raw)
    assert clean == {"modality": "MR", "pixel_spacing": [1, 1], "series": [{"rows": 256}]}
    assert raw["patient_name"] == "Doe^Jane"                    # input not mutated


# ----------------------------------------------------------------------------- backend routes
def _user(uid="reader-7", role=UserRole.RADIOLOGIST):
    now = datetime.utcnow()
    return User(id=uid, username="reader", email="reader@example.com", full_name="Reader",
                role=role, is_active=True, is_locked=False, email_verified=True,
                created_at=now, updated_at=now)


def _subject(monkeypatch, ai_report):
    """CAPA-014: an authorized segmentation whose patient record can be read."""
    from datetime import date

    async def _authorize(segmentation_id, user):
        return "44444444-4444-4444-4444-444444444444"

    class _Patients:
        async def get_patient(self, pid, **kw):
            return {"mrn": "MRN-T-1", "given_name": "Ana", "family_name": "Test", "birth_date": date(1980, 1, 1)}

    monkeypatch.setattr(ai_report, "authorize_segmentation_id", _authorize)
    monkeypatch.setattr(ai_report, "_patient_service", lambda: _Patients())


@pytest.fixture
def report_client(monkeypatch):
    import app.api.routes.ai_report as ai_report

    class _Svc:
        async def generate_report(self, **kw):
            return {"report_id": "r", "content": "draft", "template_type": kw["template_type"],
                    "language": kw["language"], "processing_time_ms": 1}

    monkeypatch.setattr(ai_report, "get_report_service", lambda: _Svc())
    _subject(monkeypatch, ai_report)        # CAPA-014: the route reads the patient record first
    app.dependency_overrides[get_current_active_user] = lambda: _user()
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.mark.unit
@pytest.mark.parametrize("body", [{}, {"findings": {}}, {"findings": {"clinical_indication": "headache"}},
                                  {"findings": {"additional_observations": "x", "patient_age": 40}},
                                  {"template": "general", "additional_findings": {"lesion_analysis": {"total_count": 3}}}],
                         ids=["empty", "empty-findings", "indication-only", "free-text-only", "old-assistant-payload"])
def test_rc034_report_route_refuses_a_report_without_measurements(report_client, body):
    r = report_client.post("/api/v1/ai/report/generate", json=body)
    assert r.status_code == 422, r.text
    assert "would be invented" in r.text


@pytest.mark.unit
def test_rc034_report_route_accepts_measurements(report_client):
    r = report_client.post("/api/v1/ai/report/generate",
                           json={"template_type": "general", "segmentation_id": "seg-1",
                                 "findings": {"lesion_analysis": {"total_count": 3}}})
    assert r.status_code == 200, r.text


class _Meta:
    def __init__(self):
        self.analysis_data = {}


class _Seg:
    def __init__(self):
        self.meta = _Meta()
        self.persisted = 0

    def get_loaded(self, sid):
        return {"metadata": self.meta}

    def persist(self, sid):
        self.persisted += 1


@pytest.fixture
def annotation_client():
    from app.core.container import get_segmentation_service
    from app.security.resource_access import require_segmentation_access
    seg = _Seg()
    app.dependency_overrides[get_current_active_user] = lambda: _user()
    app.dependency_overrides[require_segmentation_access] = lambda: None   # RC-029 tested elsewhere
    app.dependency_overrides[get_segmentation_service] = lambda: seg
    yield TestClient(app), seg
    for dep in (get_current_active_user, require_segmentation_access, get_segmentation_service):
        app.dependency_overrides.pop(dep, None)


URL = "/api/v1/segmentation/s1/lesion-annotations"


@pytest.mark.unit
@pytest.mark.parametrize("ann", [{"lesion_id": 1, "cvs_status": "probable"},
                                 {"lesion_id": 1, "prl_status": "yes"},
                                 {"lesion_id": "1", "cvs_status": "positive"},
                                 {"lesion_id": True, "cvs_status": "positive"},
                                 {"cvs_status": "positive"}])
def test_rc035_invalid_readings_are_refused_and_nothing_is_stored(annotation_client, ann):
    client, seg = annotation_client
    r = client.post(URL, json={"annotations": [ann]})
    assert r.status_code == 400, r.text
    assert seg.persisted == 0


@pytest.mark.unit
def test_rc035_reader_is_the_authenticated_user_and_no_40_percent_rule(annotation_client):
    client, seg = annotation_client
    anns = [{"lesion_id": i, "cvs_status": "positive", "annotated_by": "cvs_net"} for i in range(1, 6)]
    anns += [{"lesion_id": 9, "cvs_status": "negative", "prl_status": "positive"}]
    r = client.post(URL, json={"annotations": anns})
    assert r.status_code == 200, r.text
    stored = seg.meta.analysis_data["lesion_annotations"]
    assert {a["annotated_by"] for a in stored} == {"reader-7"}
    cvs = r.json()["cvs_summary"]
    assert "meets_40pct" not in cvs
    assert cvs == {"total_evaluated": 6, "cvs_positive": 5, "cvs_negative": 1,
                   "meets_select6": False, "cvs_majority": True}
    r = client.post(URL, json={"annotations": [{"lesion_id": 10, "cvs_status": "positive"}]})
    assert r.json()["cvs_summary"]["meets_select6"] is True            # 6 CVS+ lesions


# ----------------------------------------------------------------------------- user interface
@pytest.mark.unit
def test_rc035_ui_shows_counts_not_a_withdrawn_rule():
    dash = _src(FRONTEND / "components" / "LesionDashboard.tsx")
    types = _src(FRONTEND / "types" / "lesion.ts")
    assert "meets_40pct" not in dash and "40% rule" not in dash
    assert "meets_40pct:" not in types
    assert "prlSummary.meets_criteria ?" not in dash          # no green "criterion met" for >=1 PRL
    for lang in ("en", "es", "de"):
        loc = json.loads(_src(FRONTEND / "i18n" / "locales" / f"{lang}.json"))
        assert loc["lesions"]["markerReadingsNote"]


@pytest.mark.unit
def test_rc034_report_panel_states_why_a_report_was_refused():
    panel = _src(FRONTEND / "components" / "AIReportPanel.tsx")
    assert "status === 422" in panel and "report.noMeasurements" in panel
    for lang in ("en", "es", "de"):
        assert json.loads(_src(FRONTEND / "i18n" / "locales" / f"{lang}.json"))["report"]["noMeasurements"]
