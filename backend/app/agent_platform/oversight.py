"""
Oversight metrics per reader: accepted without edits, edit size, and time from shown to signed.

REQ-AGT-007; risk control RC-120 (detection of automation bias: readers who sign AI drafts unread);
hazard HAZ-024. DRAFT, PENDING owner approval. Backend only — no UI in this release.

What is recorded, per draft and reader, when the reader signs:
- ``accepted_unedited``: the signed text equals the text shown (character for character);
- ``edit_chars`` / ``edit_ratio``: characters changed (difflib opcodes: the longer side of each change)
  and that count over the length of the shown text;
- ``sentences_total`` / ``sentences_changed``: units of the shown text (provenance.split_units) changed or
  removed, plus units added;
- ``seconds_to_sign``: from the time the signed version was shown to that reader (a regenerated draft
  restarts the clock; the same version shown again does not).

No text, no patient, study or segmentation id is kept: the draft and the reader are named by the audit
log's keyed hash, and the text is held only as its SHA-256 between "shown" and "signed" (to refuse a
sign-off of a different text than the one shown, which is then not counted). ``aggregate`` gives per
reader: n, unedited rate, fast unedited sign-offs (under ``MIN_REVIEW_SECONDS``, a DRAFT threshold for
the owner to set), median edit ratio and median seconds to sign. The durable store and the alarm when a
hospital's figures drift are integration steps (Integration_Plan.md, P-8).

@module agent_platform.oversight
"""

from __future__ import annotations

import difflib
import statistics
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from app.agent_platform.hashing import sha256_text
from app.agent_platform.provenance import split_units
from app.agent_platform.registry import draft_key as _registry_draft_key
from app.agent_platform.registry import reader_key as _registry_reader_key

SCHEMA = "mstool.oversight/1"
MIN_REVIEW_SECONDS = 30
RECORD_KEYS = frozenset({"schema", "reader_key", "agent_id", "draft_key", "day", "accepted_unedited",
                         "edit_chars", "edit_ratio", "sentences_total", "sentences_changed", "seconds_to_sign"})


# The ONE pseudonym of a reader and of a draft, shared with the sign-off span (third review of PR #79, finding 6).
reader_key = _registry_reader_key
draft_key = _registry_draft_key


@dataclass(frozen=True)
class OversightEvent:
    reader_key: str
    agent_id: str
    draft_key: str
    day: str
    accepted_unedited: bool
    edit_chars: int
    edit_ratio: float
    sentences_total: int
    sentences_changed: int
    seconds_to_sign: int

    def to_record(self) -> Dict[str, Any]:
        return {"schema": SCHEMA, **asdict(self)}


def edit_size(shown: str, final: str) -> Tuple[int, float]:
    ops = difflib.SequenceMatcher(None, shown, final, autojunk=False).get_opcodes()
    chars = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in ops if tag != "equal")
    return chars, chars / max(len(shown), 1)


def sentence_changes(shown: str, final: str) -> Tuple[int, int]:
    a = [u[1].strip() for u in split_units(shown) if u[1].strip()]
    b = [u[1].strip() for u in split_units(final) if u[1].strip()]
    changed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            changed += i2 - i1
        elif tag == "insert":
            changed += j2 - j1
    return len(a), changed


class OversightRecorder:
    """In-memory recorder (per instance). The durable store is integration step P-8."""

    def __init__(self, clock: Optional[Callable[[], datetime]] = None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._pending: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.events: List[OversightEvent] = []
        self.mismatches = 0
        self._lock = threading.Lock()

    def shown(self, draft_id: str, reader_id: str, agent_id: str, draft_text: str) -> None:
        """Review of PR #79, finding 7: the LATEST version shown is the one a sign-off must match. A new text
        under the same draft id (a regenerated draft) replaces the pending one and restarts the clock; the
        same text shown again keeps the time it was first shown."""
        key = (draft_key(draft_id), reader_key(reader_id))
        digest = sha256_text(draft_text)
        with self._lock:
            current = self._pending.get(key)
            if current is None or current["draft_sha256"] != digest:
                self._pending[key] = {"agent_id": agent_id, "shown_at": self._clock(), "draft_sha256": digest}

    def pending_records(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [{"draft_key": d, "reader_key": r, "agent_id": v["agent_id"],
                     "day": v["shown_at"].astimezone(timezone.utc).date().isoformat()}
                    for (d, r), v in self._pending.items()]

    def signed(self, draft_id: str, reader_id: str, shown_text: str, final_text: str) -> Optional[OversightEvent]:
        key = (draft_key(draft_id), reader_key(reader_id))
        with self._lock:
            pending = self._pending.get(key)
            if pending is None or pending["draft_sha256"] != sha256_text(shown_text):
                self.mismatches += 1
                return None
            del self._pending[key]
        chars, ratio = edit_size(shown_text, final_text)
        total, changed = sentence_changes(shown_text, final_text)
        seconds = max(0, int((self._clock() - pending["shown_at"]).total_seconds()))
        event = OversightEvent(
            reader_key=key[1], agent_id=pending["agent_id"], draft_key=key[0],
            day=pending["shown_at"].astimezone(timezone.utc).date().isoformat(),
            accepted_unedited=shown_text == final_text, edit_chars=chars, edit_ratio=round(ratio, 6),
            sentences_total=total, sentences_changed=changed, seconds_to_sign=seconds)
        with self._lock:
            self.events.append(event)
        return event


def aggregate(events: Iterable[OversightEvent]) -> Dict[str, Dict[str, Any]]:
    by_reader: Dict[str, List[OversightEvent]] = {}
    for e in events:
        by_reader.setdefault(e.reader_key, []).append(e)
    out = {}
    for reader, evs in by_reader.items():
        n = len(evs)
        out[reader] = {
            "n": n,
            "unedited_rate": sum(e.accepted_unedited for e in evs) / n,
            "fast_unedited": sum(e.accepted_unedited and e.seconds_to_sign < MIN_REVIEW_SECONDS for e in evs),
            "median_edit_ratio": statistics.median(e.edit_ratio for e in evs),
            "median_seconds_to_sign": statistics.median(e.seconds_to_sign for e in evs),
            "agents": sorted({e.agent_id for e in evs}),
        }
    return out
