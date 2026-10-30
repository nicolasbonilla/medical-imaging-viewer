"""Release 2026-10-30 — merge of main (PR #70, owner-signed) into the #69 + #71 branch: the audit of account creation.

#70 (review of PR #70, m1) records an administrator account created by an administrator twice: as `register_user`
(actor = the administrator, target = the new account) and as `privileged_account_created`. #65 (CAPA-015, RC-067, in
this branch) sends audit events to the durable audit trail with a fixed action -> event-type mapping, and an action it
does not know is recorded as "authz.access.granted". Merged, the privileged event would read as an access grant.
It must be recorded as a role assignment ("authz.role.assigned"), by the administrator, with the new account as target.

Written BEFORE the correction (fails on the merge commit with #70's fixtures adapted). Nothing reaches a store or a
cloud service (PRB-002; in-memory audit sink).
"""
import pytest

from app.core.logging.audit_sink import get_durable_audit_sink
from app.security.models import UserRole
from tests.unit.test_prb020_review1_findings import (  # noqa: F401  (fixture)
    _act_as, _new_account, client, store,
)


def _new_records(sink, before):
    sink.flush(5.0)
    return list(sink.memory_records[before:])


@pytest.mark.unit
def test_rc067_release_1030_main_a_privileged_account_creation_is_recorded_as_a_role_assignment(store):
    sink = get_durable_audit_sink()
    assert sink.backend == "memory"
    before = len(sink.memory_records)
    admin = _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    r = client.post("/api/v1/auth/users", json=_new_account("admin", "second_admin"))
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    rows = _new_records(sink, before)
    created = [x for x in rows if x.get("event_type") == "admin.user.created"]
    assigned = [x for x in rows if x.get("event_type") == "authz.role.assigned"]
    assert len(created) == 1 and created[0].get("actor_user_id") == admin.id
    assert len(assigned) == 1 and assigned[0].get("actor_user_id") == admin.id
    assert new_id in str(assigned[0].get("resource_ids") or "") + str(assigned[0].get("details") or "")
    assert not [x for x in rows if x.get("event_type") == "authz.access.granted"]


@pytest.mark.unit
def test_rc067_release_1030_main_a_non_privileged_account_creation_is_one_record(store):
    """Positive control: a radiologist account created by an administrator is one `admin.user.created` record."""
    sink = get_durable_audit_sink()
    before = len(sink.memory_records)
    admin = _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    r = client.post("/api/v1/auth/users", json=_new_account("radiologist", "dr_two"))
    assert r.status_code == 201, r.text
    rows = _new_records(sink, before)
    assert [x.get("event_type") for x in rows if x.get("event_type", "").startswith(("admin.", "authz."))] \
        == ["admin.user.created"]
    assert rows and all(x.get("actor_user_id") == admin.id for x in rows if x.get("event_type") == "admin.user.created")
