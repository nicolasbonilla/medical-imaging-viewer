"""Review of PR #70, finding M3 — the owner-run backfill that puts each patient's creator on its care team.

After PRB-021 a clinician sees only the patients of their care-team assignments. Records created by a clinician before
PRB-023 carry `created_by` but no assignment, so after the deployment their creators would see "no patients". The
script `scripts/owner/prb021_backfill_creator_care_team.py` (run by the owner only, before the backend deployment)
assigns each such creator. These tests run it OFFLINE against the in-memory Firestore stand-in: dry run by default,
a typed confirmation word, a backup before any write, idempotent, and it never re-grants a revoked assignment,
never assigns an administrator, an unknown or an inactive account, and refuses the Daita project.
"""
import importlib.util
import io
import json
from pathlib import Path

import pytest

from tests.unit.prb020_fakes import FakeCareTeam, FakeDb, patient_doc

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "owner" / "prb021_backfill_creator_care_team.py"
ASSIGNMENTS = "patient_assignments"
P = {n: f"{n}{n}{n}{n}{n}{n}{n}{n}-0000-4000-8000-000000000000" for n in "1234567"}


def _script():
    if not SCRIPT.exists():
        pytest.fail(f"owner backfill script missing: {SCRIPT}")
    spec = importlib.util.spec_from_file_location("prb021_backfill", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


USERS = [
    {"id": "u-admin", "username": "site_admin", "role": "admin", "is_active": True},
    {"id": "u-rad", "username": "dr_rad", "role": "radiologist", "is_active": True},
    {"id": "u-rad2", "username": "dr_two", "role": "radiologist", "is_active": True},
    {"id": "u-tech", "username": "tech_one", "role": "technician", "is_active": True},
    {"id": "u-gone", "username": "left_clinic", "role": "radiologist", "is_active": False},
]


@pytest.fixture
def world(tmp_path):
    db = FakeDb()
    pats = db.data.setdefault("patients", {})
    pats[P["1"]] = patient_doc(P["1"], "Anna", "Beispiel", "MRN-1", created_by="u-rad")     # → assign
    pats[P["2"]] = patient_doc(P["2"], "Ben", "Admin", "MRN-2", created_by="u-admin")      # admin creator → skip
    pats[P["3"]] = patient_doc(P["3"], "Cara", "Legacy", "MRN-3")                          # no provenance → skip
    pats[P["4"]] = patient_doc(P["4"], "Dora", "Assigned", "MRN-4", created_by="u-rad2")   # already assigned → skip
    pats[P["5"]] = patient_doc(P["5"], "Emil", "Revoked", "MRN-5", created_by="u-tech")    # revoked → never re-grant
    pats[P["6"]] = patient_doc(P["6"], "Fritz", "Unknown", "MRN-6", created_by="u-nobody") # unknown creator → skip
    pats[P["7"]] = patient_doc(P["7"], "Gina", "Inactive", "MRN-7", created_by="u-gone")   # inactive creator → skip
    care = FakeCareTeam()
    care.assign(patient_id=P["4"], user_id="u-rad2", role_in_care="attending", granted_by="u-rad2")
    rec = care.assign(patient_id=P["5"], user_id="u-tech", role_in_care="attending", granted_by="u-tech")
    care.revoke(assignment_id=rec.id, revoked_by="u-admin")
    db.data[ASSIGNMENTS] = {r["id"]: {k: v for k, v in r.items() if k != "id"} for r in care.rows}
    users = tmp_path / "users.json"
    users.write_text(json.dumps(USERS), encoding="utf-8")
    backups = tmp_path / "backups"
    return {"db": db, "users": str(users), "backups": backups}


def _run(world, *extra, answer=None, project="brain-mri-476110", granted_by="u-admin"):
    mod = _script()
    out = io.StringIO()
    argv = ["--project", project, "--users-json", world["users"], "--granted-by", granted_by,
            "--backup-dir", str(world["backups"]), *extra]
    asked = []

    def _input(prompt=""):
        asked.append(prompt)
        if answer is None:
            raise AssertionError("the script asked for confirmation in a dry run")
        return answer
    rc = mod.main(argv, db=world["db"], input_fn=_input, out=out)
    return rc, out.getvalue(), asked


def _rows(world):
    return dict(world["db"].data.get(ASSIGNMENTS, {}))


def test_rc083_prb023_backfill_dry_run_writes_nothing_and_lists_the_plan(world):
    before = _rows(world)
    rc, text, asked = _run(world)
    assert rc == 0 and asked == []
    assert _rows(world) == before
    assert not world["backups"].exists()
    assert "DRY RUN" in text and P["1"] in text and "dr_rad" in text
    assert "would assign: 1" in text
    for reason in ("administrator", "no provenance", "already has a care-team row", "unknown account",
                   "inactive account"):
        assert reason in text, reason
    assert "Anna" not in text and "Beispiel" not in text       # no patient names on screen


def test_rc083_prb023_backfill_needs_the_typed_confirmation_word(world):
    before = _rows(world)
    rc, _text, asked = _run(world, "--apply", answer="yes")
    assert rc != 0 and asked
    assert _rows(world) == before


def test_rc083_prb023_backfill_takes_a_backup_assigns_once_and_is_idempotent(world):
    before = _rows(world)
    rc, text, _ = _run(world, "--apply", answer="ASSIGN")
    assert rc == 0, text
    backups = sorted(world["backups"].glob("prb021_backfill_*.json"))
    assert len(backups) == 1
    saved = json.loads(backups[0].read_text(encoding="utf-8"))
    assert saved["assignments_before"] == before
    assert [a["patient_id"] for a in saved["plan"]] == [P["1"]]
    new = {k: v for k, v in _rows(world).items() if k not in before}
    assert list(new.values()) == [{
        "patient_id": P["1"], "user_id": "u-rad", "role_in_care": "attending", "granted_by": "u-admin",
        "granted_at": list(new.values())[0]["granted_at"], "revoked_at": None, "revoked_by": None,
        "basis": "prb021_backfill_created_by"}]
    # The backup ends with the ids it created, so the owner can revoke exactly those (undo).
    assert saved["created_assignment_ids"] == list(new.keys())
    # Second run: nothing left to do, nothing written, no confirmation asked.
    after_first = _rows(world)
    rc, text, asked = _run(world, "--apply", answer="ASSIGN")
    assert rc == 0 and "nothing to assign" in text.lower() and asked == []
    assert _rows(world) == after_first


def test_rc083_prb023_backfill_refuses_the_daita_project(world):
    rc, text, _ = _run(world, project="daita-9f4f6")
    assert rc != 0 and "refus" in text.lower()
    assert world["db"].reads == 0


def test_rc083_prb023_backfill_refuses_a_granter_who_is_not_an_active_administrator(world):
    for who in ("u-rad", "u-gone", "u-nobody"):
        rc, text, _ = _run(world, "--apply", answer="ASSIGN", granted_by=who)
        assert rc != 0, who
    assert len(_rows(world)) == 2


def test_rc083_prb023_backfill_stops_before_writing_when_the_backup_fails(world, tmp_path):
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    world["backups"] = blocker / "backups"      # cannot be created: a file is in the way
    before = _rows(world)
    rc, _text, _ = _run(world, "--apply", answer="ASSIGN")
    assert rc != 0
    assert _rows(world) == before
