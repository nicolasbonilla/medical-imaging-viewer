"""Initiator registry for short-lived handles (CAPA-009, HAZ-010, RC-036).

Some routes hand out a random handle — an AI task id, a clinical-tool task id, an upload
session id, a PACS import job id — and later routes accept that handle alone. Before
CAPA-009 any authenticated caller holding (or guessing) a handle could poll, read or complete
someone else's task, upload or import.

The handle's creating route now records who started it, after authorizing the patient object
behind it; the follow-up route requires the same user (or an administrator). An unknown
handle is refused for a non-administrator: fail closed, same 404 as "not found", so handles
cannot be enumerated.

The registry is in memory, like the task and upload stores it guards (they live in the
service instances' memory too). Entries expire; the size is bounded.
"""
import threading
import time
from collections import OrderedDict
from typing import Optional

from fastapi import HTTPException, status

from app.core.logging import get_logger
from app.security.models import User, UserRole

logger = get_logger(__name__)

_TTL_SECONDS = 24 * 3600
_MAX_ENTRIES = 50_000


class InitiatorRegistry:
    def __init__(self, ttl_seconds: int = _TTL_SECONDS, max_entries: int = _MAX_ENTRIES):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._entries: "OrderedDict[tuple, tuple]" = OrderedDict()
        self._lock = threading.Lock()

    def record(self, kind: str, handle, user: User) -> None:
        if not handle:
            return
        with self._lock:
            self._entries[(kind, str(handle))] = (str(user.id), time.monotonic())
            self._entries.move_to_end((kind, str(handle)))
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)

    def initiator(self, kind: str, handle) -> Optional[str]:
        with self._lock:
            entry = self._entries.get((kind, str(handle)))
            if entry is None:
                return None
            user_id, created = entry
            if time.monotonic() - created > self._ttl:
                del self._entries[(kind, str(handle))]
                return None
            return user_id

    def authorize(self, kind: str, handle, user: User, label: str = "Resource") -> None:
        """Allow the initiator or an administrator; everyone else gets the same 404."""
        if user.role == UserRole.ADMIN:
            return
        if handle and self.initiator(kind, handle) == str(user.id):
            return
        logger.warning("Handle access denied", extra={"user_id": str(user.id), "kind": kind})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


initiators = InitiatorRegistry()
