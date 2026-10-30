"""PRB-010 — the region labels classify-regions and generate-zone-map store carry the app's one MAGNIMS
region colour mapping (Okabe-Ito, `frontend/src/utils/regionColors.ts`), not red / green / blue / gold.

The colours stored with the labels are what the viewer (before PRB-010), a DICOM-SEG export and any other
viewer show: they must be the legend's colours, and periventricular must not be red against a green
juxtacortical. No cloud access (PRB-002): module constants and source only.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROUTE = REPO / "backend" / "app" / "api" / "routes" / "segmentation_regions.py"
FRONTEND_PALETTE = REPO / "frontend" / "src" / "utils" / "regionColors.ts"


def _frontend_mapping():
    text = FRONTEND_PALETTE.read_text(encoding="utf-8")
    pairs = re.findall(r"'?([A-Za-z ]+?)'?\s*:\s*\{\s*id:\s*(\d)\s*,\s*hex:\s*'(#[0-9A-Fa-f]{6})'", text)
    return {name.strip(): (int(i), h.upper()) for name, i, h in pairs}


def test_rc076_backend_region_label_colours_are_the_frontend_mapping():
    from app.api.routes.segmentation_regions import MAGNIMS_REGION_LABEL_COLORS

    front = _frontend_mapping()
    assert set(front) == {"Periventricular", "Juxtacortical", "Infratentorial", "Deep White Matter"}
    assert {name: h.upper() for name, h in MAGNIMS_REGION_LABEL_COLORS.items()} == {n: h for n, (_i, h) in front.items()}


def test_rc076_routes_store_region_labels_with_the_mapping_only():
    text = ROUTE.read_text(encoding="utf-8")
    for old in ("#FF0000", "#00CC00", "#0066FF", "#FFD700"):
        assert old not in text.upper(), f"{old} still stored for a region label"
    assert text.count("MAGNIMS_REGION_LABEL_COLORS[") >= 8  # both label lists of classify-regions and generate-zone-map
