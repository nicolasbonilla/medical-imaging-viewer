"""Pinned references and fixed definitions (PROTOCOL.md §3-§4).

Everything the analysis reads is addressed by a full commit SHA, so the numbers do not move
when branches move. GitHub also keeps ``refs/pull/<n>/head`` for each PR.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

#: Data source D1 / D2 (PROTOCOL.md §3).
REFS = {
    "main": "6209131f5b8b20f77a12bf5799f43dc73dad3ece",       # origin/main, 2026-10-17
    "capa010": "8b839fd0518bb56b69d41344fa83b508680b893c",    # PR #52 head
    "capa011": "86f19f2e1744c39774d2f7960d07c5e1dd657f3d",    # PR #51 head (contains CAPA-010)
    "flames": "7cce845960c91d7f5da8c2301081c4e87a451aaa",     # PR #53 head
    "sdp11": "4dcf1ff528373287439b17766ea2ac0f8c5484ba",      # PR #49 head (SDP-001 v1.1)
}

#: The eight Class C modules listed in CLAUDE.md.
CLASS_C_MODULES = (
    "backend/app/services/ai_segmentation_service.py",
    "backend/app/services/brain_volumetry_service.py",
    "backend/app/services/brain_report_service.py",
    "backend/app/services/lesion_analysis_service.py",
    "backend/app/services/ms_region_classifier.py",
    "backend/app/utils/nifti_utils.py",
    "backend/app/utils/dicom_utils.py",
    "frontend/src/workers/edgeAI.worker.ts",
)

#: Controlled documents (PROTOCOL.md §4).
CONTROLLED_DOC_PREFIXES = (
    "docs/iec62304/",
    "docs/mdr/",
    "docs/qms/",
    "docs/clinical/",
    "docs/ai-act/",
    "docs/usability/",
)

RV = "docs/iec62304/records/risk_verification/"

#: Negative-control (mutation) records: (label, ref key, path).
NEGATIVE_CONTROL_RECORDS = (
    ("RC-032 (CAPA-006)", "main", RV + "RC-032_negative_controls_2026-09-28.json"),
    ("RC-029 (CAPA-007)", "main", RV + "RC-029_analysis_negative_controls_2026-10-17.json"),
    ("CAPA-008", "main", RV + "CAPA-008_negative_controls_2026-10-17.json"),
    ("CAPA-009", "main", RV + "CAPA-009_negative_controls_2026-10-17.json"),
    ("CAPA-010", "capa010", RV + "CAPA-010_negative_controls_2026-10-17.json"),
    ("CAPA-011", "capa011", RV + "CAPA-011_negative_controls_2026-10-17.json"),
    ("CP-FLAMES-BROWSER-001", "flames", RV + "CP-FLAMES-BROWSER-001_negative_controls_2026-10-17.json"),
)

MANIFEST_PATH = RV + "rc_test_manifest.json"
RCV_2026_07_18 = RV + "RCV-SUMMARY_2026-07-18.md"
RCV_2026_04_12 = RV + "RCV-SUMMARY_2026-04-12.md"
CAPA010_TESTS_ON_MAIN = RV + "CAPA-010_tests_on_main_2026-10-17.json"

DATA_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR = Path(__file__).resolve().parent / "out"


def repo_root() -> Path:
    """The repository to analyse: ``$PAPER_H_REPO`` or the checkout holding this file."""
    env = os.environ.get("PAPER_H_REPO")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    out = subprocess.run(
        ["git", "-C", str(here), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return Path(out.stdout.strip())
