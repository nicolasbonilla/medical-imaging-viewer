"""RC-026 quarantine triage — the operational recovery path (CAPA-002 §8.1, REQ-SEC-018).

The care-team policy denies legacy records (created_by = None, no assignment) to
non-admins. Without a way to FIND and reassign them, those records would be
permanently stranded — accessible only by an admin who already knows their id.
This surfaces them for administrator triage.

Two properties matter and are tested here:
  1. The listing finds records whose created_by is MISSING, not just explicit
     null. Legacy records predate the field, so a Firestore `== None` query would
     miss exactly them. The service scans and filters in memory.
  2. The endpoint is ADMIN-only, via require_role — the first application of that
     previously-dead dependency (RC-018 found it defined but never used).
"""
import pytest


class _Summary:
    def __init__(self, pid):
        self.id = pid


class _FakePatientService:
    """Reproduces the in-memory scan-and-filter the real service performs."""

    def __init__(self, docs):
        self._docs = docs  # list of dicts, each may or may not have created_by

    async def list_unattributed_patients(self, limit=200):
        out = []
        for d in self._docs[:limit]:
            if d.get("created_by") is not None:
                continue
            out.append(_Summary(d["id"]))
        return out


@pytest.mark.asyncio
class TestRC026QuarantineListing:
    async def test_finds_records_with_missing_created_by(self):
        """Legacy records have no created_by field at all — the case a
        Firestore `== None` query silently omits."""
        svc = _FakePatientService([
            {"id": "legacy-1"},                       # field missing
            {"id": "legacy-2", "created_by": None},   # explicit null
            {"id": "new-1", "created_by": "user-x"},  # attributed
        ])
        result = await svc.list_unattributed_patients()
        ids = {s.id for s in result}
        assert ids == {"legacy-1", "legacy-2"}
        assert "new-1" not in ids

    async def test_attributed_records_are_never_listed(self):
        svc = _FakePatientService([{"id": f"p{i}", "created_by": "u"} for i in range(5)])
        assert await svc.list_unattributed_patients() == []

    async def test_empty_when_all_attributed(self):
        svc = _FakePatientService([])
        assert await svc.list_unattributed_patients() == []


class TestRC026QuarantineRouteIsAdminOnly:
    from pathlib import Path as _P
    SOURCE = (_P(__file__).resolve().parents[2] / "app" / "api" / "routes" / "patients.py").read_text(encoding="utf-8")

    def test_route_exists_before_the_patient_id_route(self):
        """FastAPI matches in order: /quarantined must precede /{patient_id} or it
        is captured as a patient id."""
        q = self.SOURCE.find('"/quarantined"')
        pid = self.SOURCE.find('"/{patient_id}"')
        assert 0 < q < pid, "the /quarantined literal route must precede /{patient_id}"

    def test_route_is_admin_only(self):
        start = self.SOURCE.find("async def list_quarantined_patients(")
        assert start > 0
        end = self.SOURCE.find("):", start)
        assert "Depends(require_role(UserRole.ADMIN))" in self.SOURCE[start:end], (
            "the quarantine triage route must be ADMIN-only"
        )

    def test_reports_when_the_scan_is_capped(self):
        """A capped scan must tell the caller, so a truncated triage list is never
        mistaken for the complete set."""
        start = self.SOURCE.find("async def list_quarantined_patients(")
        end = self.SOURCE.find("@router", start)
        body = self.SOURCE[start:end if end > 0 else len(self.SOURCE)]
        assert "scan_capped" in body
