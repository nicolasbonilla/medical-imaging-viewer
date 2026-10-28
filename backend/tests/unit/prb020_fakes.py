"""In-memory stand-ins for the PRB-020..PRB-026 tests (not collected: no `test_` prefix).

Nothing here talks to a cloud service (PRB-002). The Firestore stand-in implements only what the
patient, study and care-team code under test calls: collection/document get, set, update, delete,
sub-collections, `where` (positional or `filter=FieldFilter`), `order_by`, `limit`, `count`, `stream`.
"""
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from app.core.config import get_settings
from app.security.models import User, UserRole
from app.security.patient_access import CareTeamAssignment


# --------------------------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------------------------
_MISSING = object()


@contextmanager
def setting(name, value):
    """Set one attribute of the cached Settings object for the duration of a block.

    object.__setattr__ is used so a field the code under test does not (yet) declare can be set
    too: on the base commit the field does not exist, and the tests must still run there."""
    s = get_settings()
    old = s.__dict__.get(name, _MISSING)
    object.__setattr__(s, name, value)
    try:
        yield
    finally:
        if old is _MISSING:
            s.__dict__.pop(name, None)
        else:
            object.__setattr__(s, name, old)


# --------------------------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------------------------
def make_user(username: str, role: UserRole = UserRole.VIEWER, uid: Optional[str] = None) -> User:
    now = datetime.utcnow()
    return User(id=uid or str(uuid.uuid4()), username=username, email=f"{username}@example.org",
                full_name=username.replace("_", " ").title(), role=role, is_active=True, is_locked=False,
                email_verified=False, created_at=now, updated_at=now, last_password_change=now,
                failed_login_attempts=0)


class FakeUserStorage:
    """The persistent user store (SecureUserStorage interface), in memory."""

    def __init__(self):
        self.users: Dict[str, User] = {}
        self.passwords: Dict[str, dict] = {}

    def save_user(self, user, password_hash, password_history=None):
        self.users[user.id] = user.model_copy(deep=True)
        self.passwords[user.id] = {"password_hash": password_hash,
                                   "password_history": list(password_history or [password_hash])}
        return True

    def get_user_by_id(self, user_id):
        u = self.users.get(user_id)
        return u.model_copy(deep=True) if u else None

    def lookup_user(self, user_id):
        return self.get_user_by_id(user_id)

    def get_user_password_data(self, user_id):
        return self.passwords.get(user_id)

    def get_user_by_username(self, username):
        for u in self.users.values():
            if u.username == username:
                return u.model_copy(deep=True)
        return None

    def get_user_by_email(self, email):
        for u in self.users.values():
            if u.email == email:
                return u.model_copy(deep=True)
        return None

    def list_all_users(self):
        return [u.model_copy(deep=True) for u in self.users.values()]

    def delete_user(self, user_id):
        existed = user_id in self.users
        self.users.pop(user_id, None)
        self.passwords.pop(user_id, None)
        return existed

    def user_exists(self, user_id):
        return user_id in self.users

    def username_exists(self, username):
        return self.get_user_by_username(username) is not None

    def email_exists(self, email):
        return self.get_user_by_email(email) is not None

    def get_user_count(self):
        return len(self.users)


# --------------------------------------------------------------------------------------------
# Care team
# --------------------------------------------------------------------------------------------
class FakeCareTeam:
    """CareTeamService interface, in memory. `fail_assign` makes assign() raise (store outage)."""

    def __init__(self):
        self.rows: List[dict] = []
        self.fail_assign = False
        self.assign_calls: List[dict] = []

    def list_entitlements_for_user(self, user_id):
        return [CareTeamAssignment(patient_id=r["patient_id"], user_id=r["user_id"],
                                   role_in_care=r["role_in_care"], revoked_at=r["revoked_at"])
                for r in self.rows if r["user_id"] == user_id]

    def list_for_patient(self, patient_id):
        from app.services.care_team_service import AssignmentRecord
        return [AssignmentRecord(id=r["id"], patient_id=r["patient_id"], user_id=r["user_id"],
                                 role_in_care=r["role_in_care"], granted_by=r["granted_by"],
                                 granted_at=r["granted_at"], revoked_at=r["revoked_at"],
                                 revoked_by=r["revoked_by"])
                for r in self.rows if r["patient_id"] == patient_id]

    def assign(self, *, patient_id, user_id, role_in_care, granted_by):
        self.assign_calls.append({"patient_id": patient_id, "user_id": user_id,
                                  "role_in_care": role_in_care, "granted_by": granted_by})
        if self.fail_assign:
            raise RuntimeError("care-team store unavailable")
        row = {"id": str(uuid.uuid4()), "patient_id": patient_id, "user_id": user_id,
               "role_in_care": role_in_care, "granted_by": granted_by,
               "granted_at": datetime.utcnow().isoformat(), "revoked_at": None, "revoked_by": None}
        self.rows.append(row)
        return self.list_for_patient(patient_id)[-1]

    def revoke(self, *, assignment_id, revoked_by):
        for r in self.rows:
            if r["id"] == assignment_id:
                r["revoked_at"] = datetime.utcnow().isoformat()
                r["revoked_by"] = revoked_by


# --------------------------------------------------------------------------------------------
# Firestore
# --------------------------------------------------------------------------------------------
class _Agg:
    def __init__(self, value):
        self.value = value


class _Count:
    def __init__(self, n):
        self._n = n

    def get(self):
        return [[_Agg(self._n)]]


class FakeSnapshot:
    def __init__(self, db, path, doc_id):
        self._db, self._path, self.id = db, path, doc_id
        self.reference = FakeDocRef(db, path, doc_id)

    @property
    def exists(self):
        return self.id in self._db.data.get(self._path, {})

    def to_dict(self):
        d = self._db.data.get(self._path, {}).get(self.id)
        return dict(d) if d is not None else None


class FakeDocRef:
    def __init__(self, db, path, doc_id):
        self._db, self._path, self.id = db, path, doc_id

    def get(self):
        return FakeSnapshot(self._db, self._path, self.id)

    def set(self, data, merge=False):
        coll = self._db.data.setdefault(self._path, {})
        coll[self.id] = {**coll.get(self.id, {}), **data} if merge else dict(data)

    def update(self, data, option=None):
        coll = self._db.data.setdefault(self._path, {})
        if self.id not in coll:
            raise KeyError(self.id)
        coll[self.id].update(data)

    def delete(self):
        self._db.data.get(self._path, {}).pop(self.id, None)

    def collection(self, name):
        return FakeQuery(self._db, f"{self._path}/{self.id}/{name}")


_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">=": lambda a, b: a is not None and a >= b,
    "<=": lambda a, b: a is not None and a <= b,
    ">": lambda a, b: a is not None and a > b,
    "<": lambda a, b: a is not None and a < b,
    "in": lambda a, b: a in b,
    "not-in": lambda a, b: a is not None and a not in b,
}


class FakeQuery:
    def __init__(self, db, path, filters=(), orders=(), lim=None):
        self._db, self._path = db, path
        self._filters, self._orders, self._limit = list(filters), list(orders), lim

    def _copy(self, **kw):
        return FakeQuery(self._db, self._path, kw.get("filters", self._filters), kw.get("orders", self._orders),
                         kw.get("lim", self._limit))

    # collection-only API
    def document(self, doc_id=None):
        return FakeDocRef(self._db, self._path, doc_id or uuid.uuid4().hex)

    def add(self, data):
        ref = self.document()
        ref.set(data)
        return None, ref

    # query API
    def where(self, field_path=None, op_string=None, value=None, *, filter=None):
        if filter is not None:
            field_path, op_string, value = filter.field_path, filter.op_string, filter.value
        return self._copy(filters=self._filters + [(field_path, op_string, value)])

    def order_by(self, field, direction="ASCENDING"):
        d = str(getattr(direction, "name", direction)).upper()
        return self._copy(orders=self._orders + [(field, d.startswith("DESC"))])

    def limit(self, n):
        return self._copy(lim=n)

    def select(self, _fields):
        return self

    def _matching(self):
        rows = []
        for doc_id, data in self._db.data.get(self._path, {}).items():
            if all(_OPS[op](data.get(f), v) for f, op, v in self._filters):
                rows.append(doc_id)
        for field, desc in reversed(self._orders):
            rows.sort(key=lambda i, f=field: (self._db.data[self._path][i].get(f) is None,
                                              self._db.data[self._path][i].get(f) or ""), reverse=desc)
        if self._limit is not None:
            rows = rows[:self._limit]
        return rows

    def stream(self):
        self._db.reads += 1
        return iter([FakeSnapshot(self._db, self._path, i) for i in self._matching()])

    def get(self):
        return list(self.stream())

    def count(self):
        return _Count(len(self._matching()))


class FakeDb:
    def __init__(self):
        self.data: Dict[str, Dict[str, dict]] = {}
        self.reads = 0

    def collection(self, name):
        return FakeQuery(self, name)


def patient_doc(pid, given, family, mrn, created_by=None, status="active", **extra):
    doc = {"id": pid, "mrn": mrn, "given_name": given, "middle_name": None, "family_name": family,
           "name_prefix": None, "name_suffix": None, "birth_date": "2000-01-01", "gender": "male",
           "phone_mobile": "+10000000000", "country": "DEU", "status": status,
           "created_at": "2026-10-28T10:00:00", "updated_at": "2026-10-28T10:00:00"}
    if created_by is not None:
        doc["created_by"] = created_by
    doc.update(extra)
    return doc


def study_doc(sid, pid, status="available", date="2026-09-30T00:00:00"):
    return {"id": sid, "patient_id": pid, "accession_number": f"ACC-{sid[:6]}",
            "study_instance_uid": f"2.25.{int(uuid.UUID(sid))}", "status": status, "modality": "MR",
            "study_date": date, "study_description": "Brain MRI", "gcs_prefix": f"patients/{pid}/studies/{sid}",
            "created_at": "2026-10-28T10:00:00", "updated_at": "2026-10-28T10:00:00"}
