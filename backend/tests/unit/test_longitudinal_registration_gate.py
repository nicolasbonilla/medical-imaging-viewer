"""Longitudinal-registration enablement gate (IEC 62304 Class C, ISO 14971).

Binds the LONG_REGISTRATION_VERIFIED_ENABLED flag to the V&V dossier: enabling the
"verified change" flip while ANY gate is not `pass` turns the build RED. Same
"a missing control must not produce a green build" pattern as the CALM-MS gate. Reads
SOURCE TEXT so no environment is needed and test env vars cannot defeat it.

The flip is PERMANENTLY blocked on in-hand data (gates 4/5 are NOT_MEETABLE — the free
data cannot measure the QC false-accept rate; see REG-VV-DOSSIER.md).
"""
import json
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
_CONFIG = _BACKEND / "app" / "core" / "config.py"
_GATE_STATUS = _REPO / "docs" / "longitudinal-registration" / "reg_vv_gate_status.json"
_FLAG = "LONG_REGISTRATION_VERIFIED_ENABLED"
_VALID_STATUS = {"pass", "amber", "fail", "blocked"}


def _load_gate_status() -> dict:
    assert _GATE_STATUS.exists(), f"registration V&V gate status missing: {_GATE_STATUS}"
    return json.loads(_GATE_STATUS.read_text(encoding="utf-8"))


def _config_flag_default() -> bool:
    src = _CONFIG.read_text(encoding="utf-8")
    m = re.search(rf"{_FLAG}\s*:\s*bool\s*=\s*Field\(\s*default\s*=\s*(True|False)", src)
    assert m, f"could not find `{_FLAG}: bool = Field(default=...)` in {_CONFIG}"
    return m.group(1) == "True"


def test_gate_status_is_structurally_valid():
    data = _load_gate_status()
    assert data.get("flag") == _FLAG
    gates = data.get("gates")
    assert isinstance(gates, dict) and gates
    for name, g in gates.items():
        assert g.get("status") in _VALID_STATUS, f"gate {name}: bad status {g.get('status')!r}"


def test_enable_permitted_matches_gate_reality():
    data = _load_gate_status()
    all_pass = all(g["status"] == "pass" for g in data["gates"].values())
    assert bool(data.get("enable_permitted")) == all_pass


def test_flag_is_not_enabled_unless_every_gate_is_green():
    data = _load_gate_status()
    all_pass = all(g["status"] == "pass" for g in data["gates"].values())
    if _config_flag_default():
        assert all_pass and data.get("enable_permitted") is True, (
            f"{_FLAG} default is True but the registration V&V dossier is not green "
            "(docs/longitudinal-registration/reg_vv_gate_status.json)."
        )


def test_not_meetable_gates_are_honestly_flagged():
    """The two data-limited gates must stay blocked AND carry the honest not-meetable flag,
    so nobody silently marks them pass without acquiring adjudicated multi-session data."""
    data = _load_gate_status()
    for gname in ("gate_4_qc_false_accept_measured", "gate_5_new_lesion_detection_validation"):
        g = data["gates"][gname]
        assert g["status"] == "blocked"
        assert g.get("not_meetable_on_in_hand_data") is True


def test_no_deploy_config_force_enables_registration():
    data = _load_gate_status()
    all_pass = all(g["status"] == "pass" for g in data["gates"].values())
    if all_pass:
        pytest.skip("dossier green")
    pat = re.compile(rf"{_FLAG}\s*[:=]\s*['\"]?(true|1|yes)['\"]?", re.IGNORECASE)
    for path in (_REPO / "cloudbuild.yaml", _REPO / "cloudbuild.yml"):
        if path.exists():
            assert not pat.search(path.read_text(encoding="utf-8")), (
                f"{path.name} enables {_FLAG} while the dossier is not green")
