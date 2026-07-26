"""Every API route module must IMPORT cleanly — a container-startup guard.

WHY THIS EXISTS
Found at deploy time. Wiring object-level authorization into segmentation.py
(CAPA-002 RC-029) lost the `from app.security.resource_access import ...` line,
leaving `require_segmentation_access` undefined — a NameError at module load.

All 584 unit tests AND the full CI passed, because NO test imported the route
modules: the RC-027/028/029 wiring tests read the route files as TEXT
(`.read_text()`) to assert a dependency is present, they never `import` them.
`app.main` imports every route at startup, so the error surfaced only when Cloud
Run started the container — the deploy failed, not the tests.

This test imports every route module (and app.main), so an import-time error
(NameError, ImportError, a lost import, a circular import) turns CI red instead
of failing a production deploy. It is the cheapest possible guard against the
most expensive class of miss: code that passes every test but cannot start.
"""
import importlib

import pytest

# The exact list app.main imports (app/main.py). Keep in sync — a route module
# that app.main loads but this list omits would not be guarded.
ROUTE_MODULES = [
    "auth",
    "imaging",
    "segmentation",
    "segmentation_regions",
    "segmentation_analysis",
    "websocket",
    "authentication",
    "patients",
    "studies",
    "documents",
    "ai_segmentation",
    "ai_report",
    "clinical_tools",
    "dicomweb",
    "fhir",
]


@pytest.mark.parametrize("name", ROUTE_MODULES)
def test_route_module_imports_cleanly(name):
    """Importing the module must not raise, and it must expose a `router`."""
    module = importlib.import_module(f"app.api.routes.{name}")
    assert hasattr(module, "router"), f"app.api.routes.{name} exposes no `router`"


def test_app_main_imports():
    """The literal container-startup path: uvicorn imports app.main:app. If this
    import raises, the container exits(1) and the deploy fails its health check —
    which is exactly what happened before this test existed."""
    main = importlib.import_module("app.main")
    assert hasattr(main, "app"), "app.main exposes no `app` (the ASGI application)"


def test_route_module_list_matches_app_main():
    """Guard against drift: if app/main.py starts importing a new route module,
    this test list must include it, or the new module goes unguarded."""
    from pathlib import Path

    main_src = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")
    # The single `from app.api.routes import a, b, c` line.
    for name in ROUTE_MODULES:
        assert name in main_src, f"{name} is in the guard list but not imported by app.main"
