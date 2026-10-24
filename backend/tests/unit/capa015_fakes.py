"""In-memory stand-ins used by the CAPA-015 tests (no network, no cloud credentials).

- FakeFirestore: the subset of google-cloud-firestore the audit sink, the audit-log reader and
  the refresh-token repository use (collection/document create/get/set/update, where, order_by,
  limit, start_after, stream, transactions). `SERVER_TIMESTAMP` is replaced on write by a
  monotonically increasing UTC time, as Firestore does on commit.
- FakeUserStorage: the SecureUserStorage interface the login / refresh routes use.
"""
import itertools
import threading
from datetime import datetime, timedelta, timezone

from google.cloud import firestore as gfs


class AlreadyExists(Exception):
    """Mirrors google.api_core.exceptions.AlreadyExists for create() on an existing id."""


try:  # the real class, so the code under test can catch it by type
    from google.api_core.exceptions import AlreadyExists as _GAE

    AlreadyExists = _GAE  # type: ignore[misc]
except Exception:  # pragma: no cover
    pass


class _Snap:
    def __init__(self, coll, doc_id, data):
        self._coll, self.id, self._data = coll, doc_id, data
        self.reference = _DocRef(coll, doc_id)

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None

    def get(self, field):
        return (self._data or {}).get(field)


class _DocRef:
    def __init__(self, coll, doc_id):
        self._coll, self.id = coll, doc_id

    @property
    def _store(self):
        return self._coll._db._data.setdefault(self._coll._name, {})

    def _resolve(self, data):
        out = {}
        for k, v in data.items():
            if v is gfs.SERVER_TIMESTAMP:
                v = self._coll._db._tick()
            out[k] = v
        return out

    def create(self, data):
        with self._coll._db._lock:
            self._coll._db._maybe_fail("create", self._coll._name)
            if self.id in self._store:
                raise AlreadyExists(f"{self._coll._name}/{self.id} already exists")
            self._store[self.id] = self._resolve(data)
            self._coll._db.calls.append(("create", self._coll._name, self.id))

    def set(self, data, merge=False):
        with self._coll._db._lock:
            self._coll._db._maybe_fail("set", self._coll._name)
            base = dict(self._store.get(self.id) or {}) if merge else {}
            base.update(self._resolve(data))
            self._store[self.id] = base
            self._coll._db.calls.append(("set", self._coll._name, self.id))

    def update(self, data):
        with self._coll._db._lock:
            self._coll._db._maybe_fail("update", self._coll._name)
            if self.id not in self._store:
                raise KeyError(f"{self._coll._name}/{self.id} not found")
            self._store[self.id].update(self._resolve(data))
            self._coll._db.calls.append(("update", self._coll._name, self.id))

    def delete(self):
        with self._coll._db._lock:
            self._store.pop(self.id, None)
            self._coll._db.calls.append(("delete", self._coll._name, self.id))

    def get(self, transaction=None):
        with self._coll._db._lock:
            self._coll._db._maybe_fail("get", self._coll._name)
            if transaction is not None:
                transaction.reads.append((self._coll._name, self.id))
                if transaction.writes:
                    raise AssertionError("read after write inside a transaction")
            data = self._store.get(self.id)
            return _Snap(self._coll, self.id, dict(data) if data is not None else None)


class _Query:
    def __init__(self, coll, filters=(), orders=(), limit=None, after=None):
        self._coll, self._filters, self._orders, self._limit, self._after = coll, filters, orders, limit, after

    def where(self, field=None, op=None, value=None, filter=None):  # noqa: A002 — mirrors the SDK
        if filter is not None:
            field, op, value = filter.field_path, filter.op_string, filter.value
        return _Query(self._coll, self._filters + ((field, op, value),), self._orders, self._limit, self._after)

    def order_by(self, field, direction="ASCENDING"):
        return _Query(self._coll, self._filters, self._orders + ((field, direction),), self._limit, self._after)

    def limit(self, n):
        return _Query(self._coll, self._filters, self._orders, n, self._after)

    def start_after(self, snap):
        return _Query(self._coll, self._filters, self._orders, self._limit, snap)

    def _match(self, d):
        for field, op, value in self._filters:
            v = d.get(field)
            ok = {"==": v == value, ">=": v is not None and v >= value, "<=": v is not None and v <= value,
                  ">": v is not None and v > value, "<": v is not None and v < value}.get(op)
            if ok is None:
                raise NotImplementedError(op)
            if not ok:
                return False
        return True

    def stream(self):
        with self._coll._db._lock:
            self._coll._db._maybe_fail("stream", self._coll._name)
            rows = [(k, dict(v)) for k, v in self._coll._db._data.get(self._coll._name, {}).items() if self._match(v)]
        if self._orders:  # first order field, ties broken on the document id (as Firestore does)
            field, direction = self._orders[0]
            desc = str(direction).upper().startswith("DESC")
            rows = [kv for kv in rows if kv[1].get(field) is not None]   # Firestore omits docs without it
            rows.sort(key=lambda kv: (kv[1].get(field), kv[0]), reverse=desc)
        if self._after is not None:
            ids = [k for k, _ in rows]
            if self._after.id in ids:
                rows = rows[ids.index(self._after.id) + 1:]
        if self._limit is not None:
            rows = rows[: self._limit]
        return [_Snap(self._coll, k, v) for k, v in rows]

    get = stream


class _Coll(_Query):
    def __init__(self, db, name):
        self._db, self._name = db, name
        super().__init__(self)

    def document(self, doc_id):
        return _DocRef(self, doc_id)


class FakeTransaction:
    def __init__(self, db):
        self._db, self.reads, self.writes = db, [], []

    def create(self, ref, data):
        self.writes.append(("create", ref._coll._name, ref.id))
        ref.create(data)

    def update(self, ref, data):
        self.writes.append(("update", ref._coll._name, ref.id))
        ref.update(data)

    def set(self, ref, data, merge=False):
        self.writes.append(("set", ref._coll._name, ref.id))
        ref.set(data, merge=merge)


class FakeFirestore:
    """Thread-safe in-memory Firestore subset. `fail_next(n, ops=...)` makes the next n matching
    operations raise, to simulate an outage."""

    def __init__(self):
        self._data, self.calls, self.transactions = {}, [], []
        self._lock = threading.RLock()
        self._clock = itertools.count()
        self._fail = {"n": 0, "ops": set(), "collections": None}

    def _tick(self):
        return datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc) + timedelta(milliseconds=next(self._clock))

    def fail_next(self, n, ops=("create",), collections=None):
        self._fail = {"n": n, "ops": set(ops), "collections": set(collections) if collections else None}

    def _maybe_fail(self, op, coll):
        f = self._fail
        if f["n"] > 0 and op in f["ops"] and (f["collections"] is None or coll in f["collections"]):
            f["n"] -= 1
            raise ConnectionError("simulated Firestore outage")

    def collection(self, name):
        return _Coll(self, name)

    def transaction(self):
        t = FakeTransaction(self)
        self.transactions.append(t)
        return t

    def docs(self, name):
        with self._lock:
            return {k: dict(v) for k, v in self._data.get(name, {}).items()}


def fake_transactional(fn):
    """Stand-in for google.cloud.firestore.transactional: runs fn(transaction) once."""
    def run(transaction, *a, **kw):
        return fn(transaction, *a, **kw)
    return run


class FakeUserStorage:
    """SecureUserStorage interface, in memory."""

    def __init__(self):
        self.users, self.passwords = {}, {}

    def add(self, user, password_hash):
        self.users[user.id] = user
        self.passwords[user.id] = {"password_hash": password_hash, "password_history": [password_hash]}
        return user

    def save_user(self, user, password_hash, password_history=None):
        self.users[user.id] = user
        self.passwords[user.id] = {"password_hash": password_hash,
                                   "password_history": list(password_history or [password_hash])}

    def get_user_by_id(self, user_id):
        return self.users.get(user_id)

    def get_user_by_username(self, username):
        return next((u for u in self.users.values() if u.username == username), None)

    def get_user_by_email(self, email):
        return next((u for u in self.users.values() if u.email == email), None)

    def get_user_password_data(self, user_id):
        d = self.passwords.get(user_id)
        return dict(d) if d else None

    def list_all_users(self):
        return list(self.users.values())

    def delete_user(self, user_id):
        self.passwords.pop(user_id, None)
        return self.users.pop(user_id, None) is not None

    def username_exists(self, username):
        return self.get_user_by_username(username) is not None

    def email_exists(self, email):
        return self.get_user_by_email(email) is not None
