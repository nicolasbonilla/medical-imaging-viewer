"""
Durable, append-only audit sink — CAPA-015, RC-067 (REQ-SEC-024; HAZ-010).

THE DEFECT (found 2026-10-24, main @ 70cc5c7)
---------------------------------------------
The audit logger appended to `logs/audit.log` on the container's disk and `/auth/audit-logs`
read an in-memory list. The Firestore collection `audit_logs` was declared but never written.
Cloud Run runs 0-5 instances and scales to zero: disk and memory vanish on every restart or
scale-in, so the record of who did what — needed for medical-device traceability and GDPR
accountability — was lost.

THE CONTROL
-----------
Every audit record is written:
1. at once, as one structured JSON line on stdout (Cloud Logging keeps it even if Firestore is
   unreachable) — done by AuditLogger;
2. append-only to Firestore `audit_logs` by this sink: `document(event_id).create(...)`, never
   set/update/delete, with the server's commit time (`SERVER_TIMESTAMP`). A retried write that
   finds its own record already there counts as written (idempotent by event id).

Writes never block or break the clinical request: records are queued and written by background
threads; a failed write is logged loudly (`AUDIT_SINK_WRITE_FAILED`) and retried with
exponential back-off. If the bounded queue overflows, or a record exhausts its retries, the
record is written in full to the server log at CRITICAL (`AUDIT_RECORD_DROPPED`) and counted,
and the sink reports `failing` for `drop_window_s` (15 min) after the last drop (review m9: it used
to stay red until a restart). `status()` is what the administrator indicator shows.

What "append-only" means here (review m11): this code only ever calls `create()` on
`audit_logs` and the security rules refuse every client write — a convention enforced by code
and rules, not by the database. Anyone holding the service account (Admin SDK) can still edit or
delete a record, and the `checksum` field is a plain SHA-256 that can be recomputed, not a seal.
Tamper evidence would need an external, write-once copy (e.g. a locked log bucket) — not built. The middleware waits a bounded time (AUDIT_FLUSH_WAIT_MS) for a request's
records while the sink is healthy, because Cloud Run throttles the CPU of an instance between
requests (`--cpu-throttling`); records still pending are written on the next request or by the
shutdown flush.

Backends: "firestore" (production), "memory" (tests and local runs without cloud credentials —
reported as `not_durable`), "off".

@module core.logging.audit_sink
"""

import heapq
from collections import deque
import itertools
import json
import os
import threading
import time
from concurrent.futures import Future, InvalidStateError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.logging.config import get_logger

logger = get_logger(__name__)

AUDIT_COLLECTION = "audit_logs"
_PAGE_TOKEN_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve(fut: Future, value: bool) -> None:
    try:
        if not fut.done():
            fut.set_result(value)
    except InvalidStateError:  # cancelled by a waiter — the write itself is unaffected
        pass


def _is_already_exists(exc: BaseException) -> bool:
    try:
        from google.api_core.exceptions import AlreadyExists, Conflict
        if isinstance(exc, (AlreadyExists, Conflict)):
            return True
    except Exception:  # pragma: no cover — google-api-core always present with firestore
        pass
    return type(exc).__name__ in {"AlreadyExists", "Conflict"}


def _server_timestamp():
    from google.cloud import firestore
    return firestore.SERVER_TIMESTAMP


@dataclass
class _Item:
    record: Dict[str, Any]
    future: Future
    attempt: int = 0


@dataclass
class DurableAuditSink:
    """Queue + background writers for the append-only Firestore audit trail."""

    client_factory: Optional[Callable[[], Any]]
    backend: str = "firestore"
    collection: str = AUDIT_COLLECTION
    max_queue: int = 10_000
    base_backoff_s: float = 0.5
    max_backoff_s: float = 60.0
    max_attempts: int = 50
    workers: int = 2
    failing_after: int = 3
    # Review m9: a dropped record turns the indicator red for this long, not until the next restart.
    drop_window_s: float = 900.0
    clock: Callable[[], float] = time.monotonic

    written_total: int = field(default=0, init=False)
    dropped_total: int = field(default=0, init=False)
    failed_writes_total: int = field(default=0, init=False)
    consecutive_failures: int = field(default=0, init=False)
    last_success_at: Optional[str] = field(default=None, init=False)
    last_failure_at: Optional[str] = field(default=None, init=False)
    last_error: Optional[str] = field(default=None, init=False)
    memory_records: List[Dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self):
        if self.backend not in {"firestore", "memory", "off"}:
            raise ValueError(f"unknown audit sink backend {self.backend!r}")
        self._cond = threading.Condition()
        self._ready: List[_Item] = []
        self._waiting: List[Tuple[float, int, _Item]] = []
        self._inflight = 0
        self._seq = itertools.count()
        self._threads: List[threading.Thread] = []
        self._closed = False
        self._drop_times: deque = deque()
        self._client = None

    # ------------------------------------------------------------------ public

    def submit(self, record: Dict[str, Any]) -> Optional[Future]:
        """Queue one record for durable writing. Never raises, never blocks."""
        if self.backend == "off":
            return None
        fut: Future = Future()
        if self.backend == "memory":
            with self._cond:
                if not any(r.get("event_id") == record.get("event_id") for r in self.memory_records):
                    self.memory_records.append(dict(record))
            _resolve(fut, True)
            return fut
        with self._cond:
            pending = len(self._ready) + len(self._waiting) + self._inflight
            dropped = self._closed or pending >= self.max_queue
            if dropped:
                self.dropped_total += 1
                self._drop_times.append(self.clock())
            else:
                self._ready.append(_Item(dict(record), fut))
                self._cond.notify()
        if dropped:
            self._log_dropped(record, "queue_full")
            _resolve(fut, False)
            return fut
        self._ensure_workers()
        return fut

    def client(self):
        """The Firestore client this sink writes to (used to read the trail back)."""
        if self._client is None:
            if self.client_factory is None:
                raise RuntimeError("no Firestore client factory configured")
            self._client = self.client_factory()
        return self._client

    def _recent_drops(self) -> int:
        cutoff = self.clock() - self.drop_window_s
        while self._drop_times and self._drop_times[0] < cutoff:
            self._drop_times.popleft()
        return len(self._drop_times)

    def is_healthy(self) -> bool:
        with self._cond:
            recent = self._recent_drops()
        return self.backend == "firestore" and self.consecutive_failures == 0 and recent == 0

    def flush(self, timeout: float = 5.0, retry_now: bool = False) -> bool:
        """Wait until every queued record is written (or given up). True when drained."""
        deadline = time.monotonic() + timeout
        with self._cond:
            if retry_now and self._waiting:
                self._ready.extend(item for _, _, item in self._waiting)
                self._waiting.clear()
                self._cond.notify_all()
            while self._ready or self._waiting or self._inflight:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(min(remaining, 0.05))
            return True

    def status(self) -> Dict[str, Any]:
        with self._cond:
            depth = len(self._ready) + len(self._waiting) + self._inflight
            recent = self._recent_drops()
            if self.backend == "off":
                state = "off"
            elif self.backend == "memory":
                state = "not_durable"
            elif recent > 0 or self.consecutive_failures >= self.failing_after:
                state = "failing"
            elif self.consecutive_failures > 0:
                state = "degraded"
            else:
                state = "ok"
            return {
                "state": state,
                "backend": self.backend,
                "collection": self.collection,
                "queue_depth": depth,
                "consecutive_failures": self.consecutive_failures,
                "failed_writes_total": self.failed_writes_total,
                "written_total": self.written_total if self.backend == "firestore" else len(self.memory_records),
                "dropped_total": self.dropped_total,
                "dropped_recent": recent,
                "dropped_window_s": self.drop_window_s,
                "last_success_at": self.last_success_at,
                "last_failure_at": self.last_failure_at,
                "last_error": self.last_error,
                "instance": os.environ.get("K_REVISION") or os.environ.get("HOSTNAME") or "local",
                "scope": "this server instance",
            }

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    # ---------------------------------------------------------------- workers

    def _ensure_workers(self) -> None:
        with self._cond:
            self._threads = [t for t in self._threads if t.is_alive()]
            while len(self._threads) < self.workers and not self._closed:
                t = threading.Thread(target=self._run, name=f"audit-sink-{len(self._threads)}", daemon=True)
                self._threads.append(t)
                t.start()

    def _next_item(self) -> Optional[_Item]:
        with self._cond:
            while True:
                now = time.monotonic()
                while self._waiting and self._waiting[0][0] <= now:
                    self._ready.append(heapq.heappop(self._waiting)[2])
                if self._ready:
                    self._inflight += 1
                    return self._ready.pop(0)
                if self._closed and not self._waiting:
                    return None
                timeout = (self._waiting[0][0] - now) if self._waiting else 1.0
                self._cond.wait(max(0.001, min(timeout, 1.0)))

    def _run(self) -> None:
        while True:
            item = self._next_item()
            if item is None:
                return
            error = self._write(item.record)
            give_up = False
            with self._cond:
                self._inflight -= 1
                if error is None:
                    self.written_total += 1
                    self.consecutive_failures = 0
                    self.last_success_at = _utcnow_iso()
                else:
                    self.failed_writes_total += 1
                    self.consecutive_failures += 1
                    self.last_failure_at = _utcnow_iso()
                    self.last_error = type(error).__name__
                    item.attempt += 1
                    if item.attempt >= self.max_attempts:
                        self.dropped_total += 1
                        self._drop_times.append(self.clock())
                        give_up = True
                    else:
                        delay = min(self.max_backoff_s, self.base_backoff_s * (2 ** (item.attempt - 1)))
                        heapq.heappush(self._waiting, (time.monotonic() + delay, next(self._seq), item))
                self._cond.notify_all()
            if error is None:
                _resolve(item.future, True)
                continue
            logger.error(
                f"AUDIT_SINK_WRITE_FAILED event_id={item.record.get('event_id')} attempt={item.attempt} "
                f"error={type(error).__name__}",
                extra={"audit_event_id": item.record.get("event_id"), "attempt": item.attempt,
                       "error_type": type(error).__name__, "audit_collection": self.collection},
            )
            if give_up:
                self._log_dropped(item.record, "retries_exhausted")
                _resolve(item.future, False)

    def _write(self, record: Dict[str, Any]) -> Optional[BaseException]:
        try:
            doc = dict(record)
            doc["server_timestamp"] = _server_timestamp()
            self.client().collection(self.collection).document(str(record["event_id"])).create(doc)
            return None
        except Exception as e:  # noqa: BLE001 — every failure is retried and reported
            if _is_already_exists(e):
                return None
            return e

    def _log_dropped(self, record: Dict[str, Any], why: str) -> None:
        logger.critical(
            f"AUDIT_RECORD_DROPPED reason={why} record={json.dumps(record, default=str, sort_keys=True)}",
            extra={"audit_event_id": record.get("event_id"), "drop_reason": why},
        )


# ---------------------------------------------------------------- singleton

_sink: Optional[DurableAuditSink] = None
_sink_lock = threading.Lock()


def _default_sink() -> DurableAuditSink:
    backend = (os.environ.get("AUDIT_SINK_BACKEND") or "firestore").strip().lower()

    def _client():
        from app.core.firebase import get_firestore_client
        return get_firestore_client()

    return DurableAuditSink(_client if backend == "firestore" else None, backend=backend)


def get_durable_audit_sink() -> DurableAuditSink:
    global _sink
    if _sink is None:
        with _sink_lock:
            if _sink is None:
                _sink = _default_sink()
    return _sink


def set_durable_audit_sink(sink: Optional[DurableAuditSink]) -> Optional[DurableAuditSink]:
    """Replace the process-wide sink (tests, start-up). Returns the previous one."""
    global _sink
    with _sink_lock:
        previous, _sink = _sink, sink
    return previous


# ---------------------------------------------------------------- reading

def _public(doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(data)
    out.setdefault("event_id", doc_id)
    ts = out.get("server_timestamp")
    if hasattr(ts, "isoformat"):
        out["server_timestamp"] = ts.isoformat()
    return out


def query_audit_records(
    client,
    *,
    limit: int = 50,
    page_token: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    outcome: Optional[str] = None,
    collection: str = AUDIT_COLLECTION,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Newest-first page of audit records (by server commit time) and the next page token.

    The page token is the id of the last record returned; anything else is refused."""
    from google.cloud import firestore
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
    except Exception:  # pragma: no cover
        FieldFilter = None  # type: ignore[assignment]

    limit = max(1, min(int(limit), 200))
    coll = client.collection(collection)
    query = coll
    for name, value in (("actor_user_id", actor_user_id), ("event_type", event_type), ("outcome", outcome)):
        if value:
            query = query.where(filter=FieldFilter(name, "==", value)) if FieldFilter else query.where(name, "==", value)
    query = query.order_by("server_timestamp", direction=firestore.Query.DESCENDING)
    if page_token:
        if len(page_token) > 64 or not set(page_token) <= _PAGE_TOKEN_CHARS:
            raise ValueError("invalid page token")
        snap = coll.document(page_token).get()
        if not snap.exists:
            raise ValueError("invalid page token")
        query = query.start_after(snap)
    docs = list(query.limit(limit + 1).stream())
    items = [_public(d.id, d.to_dict() or {}) for d in docs[:limit]]
    next_token = docs[limit - 1].id if len(docs) > limit else None
    return items, next_token
