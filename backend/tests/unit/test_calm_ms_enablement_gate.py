"""CALM-MS enablement gate (IEC 62304 Class C, ISO 14971).

Root cause the 2026-08-21 adversarial review flagged: the conformal second reader is
dark FOR CAUSE (its FDR/precision guarantee is undeliverable under real acquisition
variation with the data on hand), yet NOTHING prevented a one-line flip of
`CALM_MS_RESEARCH_ENABLED=true` from lighting it up. Same failure mode as CAPA-001
root cause #4: "a missing control produces a green build."

This test is that control. It binds the flag to the V&V dossier
(docs/calm-ms/vv_gate_status.json): enabling the feature while ANY gate is not `pass`
turns the build RED. It reads SOURCE TEXT (not a live Settings import) so it needs no
environment and cannot be silently defeated by test env vars.

To enable CALM-MS you must, in the same change: make every gate `pass` in
vv_gate_status.json (with real evidence), set enable_permitted=true, AND flip the
flag. Any subset fails here. See docs/calm-ms/VV-DOSSIER.md.
"""
import json
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]          # backend/
_REPO = _BACKEND.parent                                  # repo root
_CONFIG = _BACKEND / "app" / "core" / "config.py"
_GATE_STATUS = _REPO / "docs" / "calm-ms" / "vv_gate_status.json"
_FLAG = "CALM_MS_RESEARCH_ENABLED"
# "amber" = a sub-claim met but the gate is not green (does not advance enablement).
# Only "pass" counts toward enabling the flag; amber/fail/blocked all keep it dark.
_VALID_STATUS = {"pass", "amber", "fail", "blocked"}


def _load_gate_status() -> dict:
    assert _GATE_STATUS.exists(), f"V&V gate status missing: {_GATE_STATUS}"
    return json.loads(_GATE_STATUS.read_text(encoding="utf-8"))


def _config_flag_default() -> bool:
    """Parse the committed default of CALM_MS_RESEARCH_ENABLED from config source."""
    src = _CONFIG.read_text(encoding="utf-8")
    m = re.search(rf"{_FLAG}\s*:\s*bool\s*=\s*Field\(\s*default\s*=\s*(True|False)", src)
    assert m, f"could not find `{_FLAG}: bool = Field(default=...)` in {_CONFIG}"
    return m.group(1) == "True"


def test_gate_status_is_structurally_valid():
    data = _load_gate_status()
    assert data.get("flag") == _FLAG
    gates = data.get("gates")
    assert isinstance(gates, dict) and gates, "no gates recorded"
    for name, g in gates.items():
        assert g.get("status") in _VALID_STATUS, f"gate {name}: bad status {g.get('status')!r}"


def test_enable_permitted_matches_gate_reality():
    """enable_permitted must be exactly 'every gate is pass' — no optimistic drift."""
    data = _load_gate_status()
    all_pass = all(g["status"] == "pass" for g in data["gates"].values())
    assert bool(data.get("enable_permitted")) == all_pass, (
        "enable_permitted contradicts the gate statuses: "
        f"enable_permitted={data.get('enable_permitted')} but all_pass={all_pass}"
    )


def test_flag_is_not_enabled_unless_every_gate_is_green():
    """THE gate: the committed flag default may be True only when the dossier is green."""
    data = _load_gate_status()
    all_pass = all(g["status"] == "pass" for g in data["gates"].values())
    if _config_flag_default():
        assert all_pass and data.get("enable_permitted") is True, (
            f"{_FLAG} default is True but the V&V dossier is not green "
            "(docs/calm-ms/vv_gate_status.json). Enabling CALM-MS requires every gate "
            "to be 'pass' with evidence. See docs/calm-ms/VV-DOSSIER.md."
        )


def test_gate2_status_is_bound_to_its_evidence_record():
    """The Gate-2 dossier status must be consistent with its coverage record — nobody can
    flip gate_2 green without the record's utility actually being cleared. Binds the gate
    to its evidence (same 'a missing control must not produce a green build' pattern)."""
    rec_path = _REPO / "docs" / "calm-ms" / "gate2_served_coverage_record.json"
    if not rec_path.exists():
        pytest.skip("gate2 coverage record not present")
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    verdict = rec.get("gate2_verdict", {})
    g2 = _load_gate_status()["gates"]["gate_2_coverage_on_heldout"]
    # utility not cleared in the record -> gate_2 may NOT be a green 'pass'
    if not verdict.get("utility_cleared", False):
        assert g2["status"] != "pass", (
            "gate_2 is 'pass' but the coverage record's utility_cleared is False — "
            "the recall cost (see gate2_served_coverage_record.json) must not be papered over"
        )
    # while amber, the gate must explicitly not advance enablement
    if g2["status"] == "amber":
        assert g2.get("counts_toward_enablement") is False, (
            "amber gate_2 must set counts_toward_enablement=false"
        )


def test_no_deploy_config_force_enables_calm_ms():
    """A cloudbuild / deploy override must not enable CALM-MS while gates are not green."""
    data = _load_gate_status()
    all_pass = all(g["status"] == "pass" for g in data["gates"].values())
    if all_pass:
        pytest.skip("dossier green — deploy override would be permitted")
    candidates = [_REPO / "cloudbuild.yaml", _REPO / "cloudbuild.yml"]
    pat = re.compile(rf"{_FLAG}\s*[:=]\s*['\"]?(true|1|yes)['\"]?", re.IGNORECASE)
    for path in candidates:
        if path.exists():
            assert not pat.search(path.read_text(encoding="utf-8")), (
                f"{path.name} enables {_FLAG} while the V&V dossier is not green"
            )
