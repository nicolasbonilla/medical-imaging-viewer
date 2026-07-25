"""Enforcement of the risk-control → test binding manifest (CAPA-001 PA-1/PA-2).

CAPA-001 root cause:

    "The verification process accepts unexecuted, unreproducible, self-attested
     prose as objective evidence for risk-control implementation, and nothing in
     the build pipeline can contradict it."

This module is that contradiction mechanism. It reads
`docs/iec62304/records/risk_verification/rc_test_manifest.json` and fails the
build when the record and the codebase disagree — specifically when a control
claimed as implemented names a test file that no longer exists, or names no test
at all.

Without this, deleting a risk control's test produces a green build, which is
precisely how RC-006 and RC-017 came to be recorded as VERIFIED while absent.

Deliberately uses only the standard library: a compliance gate must not depend on
an undeclared transitive dependency to run.
"""
import json
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
MANIFEST_PATH = (
    REPO_ROOT
    / "docs"
    / "iec62304"
    / "records"
    / "risk_verification"
    / "rc_test_manifest.json"
)

VALID_STATUSES = {
    "implemented",
    "not_implemented",
    "deliberately_absent",
    "unverified",
}

# Statuses that permit a "VERIFIED" row in the Risk Management File.
VERIFIABLE_STATUSES = {"implemented", "deliberately_absent"}


def _resolve(rel: str):
    """Resolve a manifest test path.

    Backend paths are given relative to `backend/`; frontend paths are given
    relative to the repository root and start with `frontend/`. Risk controls
    live on both sides of the stack — RC-016 (patient identity in the viewport)
    is enforced by a React test — so the manifest must be able to name either.
    """
    if rel.startswith("frontend/"):
        return REPO_ROOT / rel
    return BACKEND_ROOT / rel


def _load_manifest():
    assert MANIFEST_PATH.exists(), (
        f"risk-control manifest is missing at {MANIFEST_PATH}. It is a controlled "
        "record required by CAPA-001 PA-1 and must not be deleted."
    )
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


MANIFEST = _load_manifest()
CONTROLS = MANIFEST["controls"]


class TestManifestIntegrity:
    """The record itself must be well formed before it can be trusted."""

    def test_manifest_is_not_empty(self):
        assert CONTROLS, "manifest lists no risk controls at all"

    @pytest.mark.parametrize("rc_id", sorted(CONTROLS))
    def test_every_control_declares_a_known_status(self, rc_id):
        status = CONTROLS[rc_id].get("status")
        assert status in VALID_STATUSES, (
            f"{rc_id} has status {status!r}; expected one of {sorted(VALID_STATUSES)}"
        )

    @pytest.mark.parametrize("rc_id", sorted(CONTROLS))
    def test_every_control_declares_its_hazard(self, rc_id):
        """A control that reduces no stated hazard cannot be risk-assessed."""
        assert CONTROLS[rc_id].get("hazard"), f"{rc_id} names no hazard"

    @pytest.mark.parametrize("rc_id", sorted(CONTROLS))
    def test_deliberately_absent_controls_state_a_rationale(self, rc_id):
        """'The code intentionally omits this' is only acceptable with a reason
        recorded — otherwise it is indistinguishable from an unnoticed defect."""
        control = CONTROLS[rc_id]
        if control["status"] == "deliberately_absent":
            assert control.get("rationale"), (
                f"{rc_id} is recorded as deliberately absent with no rationale"
            )


class TestImplementedControlsAreBoundToTests:
    """The core gate. This is what turns a deleted control red."""

    @pytest.mark.parametrize(
        "rc_id",
        sorted(k for k, v in CONTROLS.items() if v["status"] == "implemented"),
    )
    def test_implemented_control_names_at_least_one_test(self, rc_id):
        tests = CONTROLS[rc_id].get("tests") or []
        assert tests, (
            f"{rc_id} is recorded as implemented but names no test. A control "
            "without executable evidence is exactly the CAPA-001 nonconformity."
        )

    @pytest.mark.parametrize(
        "rc_id",
        sorted(k for k, v in CONTROLS.items() if v["status"] == "implemented"),
    )
    def test_named_test_files_exist(self, rc_id):
        for rel in CONTROLS[rc_id]["tests"]:
            path = _resolve(rel)
            assert path.exists(), (
                f"{rc_id} names test file '{rel}', which does not exist. Either the "
                "test was deleted (restore it) or the control is no longer verified "
                "(change its manifest status and correct the Risk Management File)."
            )

    @pytest.mark.parametrize(
        "rc_id",
        sorted(k for k, v in CONTROLS.items() if v["status"] == "implemented"),
    )
    def test_named_test_files_actually_assert_the_control(self, rc_id):
        """Guard against the file surviving as an empty shell.

        The naming convention differs by language and both are accepted, but
        neither is relaxed: a Python test must be named `test_rc016_*`, and a
        vitest case must begin its description with `rc016`. Either way the
        control ID has to appear in a test NAME, not merely in a comment — a
        file can be gutted while keeping its header docstring.
        """
        slug = rc_id.replace("-", "").lower()  # RC-006 -> rc006
        for rel in CONTROLS[rc_id]["tests"]:
            source = _resolve(rel).read_text(encoding="utf-8")

            python_named = f"def test_{slug}" in source
            js_named = f"it('{slug} " in source or f'it("{slug} ' in source

            assert python_named or js_named, (
                f"{rel} contains no test named for {rc_id} (expected a Python "
                f"`def test_{slug}_*` or a vitest `it('{slug} ...')`). It no "
                f"longer demonstrates {rc_id}."
            )

    @pytest.mark.parametrize(
        "rc_id",
        sorted(k for k, v in CONTROLS.items() if v["status"] == "implemented"),
    )
    def test_implemented_control_records_its_negative_control(self, rc_id):
        """CAPA-001 §5.3: a control is only proven by evidence that its removal
        is detected. A green suite alone proves nothing."""
        assert CONTROLS[rc_id].get("negative_control"), (
            f"{rc_id} records no negative-control result. Passing tests do not "
            "demonstrate that the control's absence would be caught."
        )


class TestUnimplementedControlsAreNotOverclaimed:
    """The other half of honesty: absent controls must stay marked absent."""

    @pytest.mark.parametrize(
        "rc_id",
        sorted(k for k, v in CONTROLS.items() if v["status"] == "not_implemented"),
    )
    def test_not_implemented_control_claims_no_implementation(self, rc_id):
        control = CONTROLS[rc_id]
        assert not control.get("implementation"), (
            f"{rc_id} is marked not_implemented but cites an implementation. "
            "If it now exists, bind it to a test and change the status."
        )
        assert not control.get("tests"), (
            f"{rc_id} is marked not_implemented but names tests."
        )

    @pytest.mark.parametrize(
        "rc_id",
        sorted(k for k, v in CONTROLS.items() if v["status"] == "not_implemented"),
    )
    def test_not_implemented_control_is_tracked_somewhere(self, rc_id):
        """An unimplemented safety control must have an owner and a CAPA action,
        not merely be noted."""
        note = CONTROLS[rc_id].get("note", "")
        assert "CA-" in note or "CAPA-" in note, (
            f"{rc_id} is not implemented and references no CAPA action. Every "
            "absent risk control needs a tracked remediation."
        )


def test_a_minimum_body_of_risk_control_tests_exists():
    """Guard against wholesale removal.

    The per-control checks above verify each named file exists. This one guards
    the aggregate: if the risk-control tests were gutted to empty shells, or the
    manifest were trimmed to a single trivial control, the individual assertions
    could still pass. Counting the actual test functions cannot be satisfied
    that way.

    Lives here rather than in CI shell because counting pytest's
    `--collect-only -q` output is fragile across versions: on pytest 9 the
    obvious `grep -c "::"` reported 0 while 28 tests were in fact collected.
    A gate that silently reports zero is worse than no gate.
    """
    total = 0
    for control in CONTROLS.values():
        for rel in control.get("tests") or []:
            path = _resolve(rel)
            if path.exists():
                # Count at any indentation: methods inside classes and
                # module-level functions both count.
                total += path.read_text(encoding="utf-8").count("def test_")

    assert total >= 20, (
        f"only {total} risk-control test functions found across the manifest "
        "(expected at least 20). Risk-control tests have been removed or "
        "emptied — see CAPA-001 PA-2."
    )


def test_capa_reference_is_recorded():
    """The manifest exists because of a specific finding; keep the link."""
    assert MANIFEST.get("capa_reference"), "manifest does not cite its originating CAPA"


def test_verifiable_statuses_are_the_only_ones_permitted_in_the_rmf():
    """Documents the rule this manifest enforces, so a reader of the test suite
    learns it without reading the QMS."""
    for rc_id, control in CONTROLS.items():
        if control["status"] in VERIFIABLE_STATUSES:
            continue
        assert control.get("note"), (
            f"{rc_id} may not be recorded VERIFIED in the Risk Management File "
            "(status is not implemented/deliberately_absent) and carries no note "
            "explaining its true state."
        )
