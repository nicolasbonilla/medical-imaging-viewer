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
import re
import statistics
import threading
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

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


# Fourth review of PR #79, finding 9: a character-level diff of two whole reports is quadratic in the worst
# case (a 15k-character report took seconds). The edit size is computed in three bounded levels: sentences
# (provenance units) first; inside each changed block, words (a word with its trailing whitespace); inside a
# changed run of words, characters — only while that run is short (CHAR_DIFF_MAX characters on both sides
# together; above it, or above WORD_DIFF_MAX words in a block, the longer side counts whole: an upper bound).
_WORD = re.compile(r"\S+\s*|\s+")
CHAR_DIFF_MAX = 400
WORD_DIFF_MAX = 4000


def _diff_cost(a: Sequence[str], b: Sequence[str]) -> List[Tuple[str, str]]:
    """The changed (old, new) pieces of two token lists."""
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    return [("".join(a[i1:i2]), "".join(b[j1:j2])) for tag, i1, i2, j1, j2 in ops if tag != "equal"]


def _char_cost(old: str, new: str) -> int:
    if len(old) + len(new) > CHAR_DIFF_MAX:
        return max(len(old), len(new))
    return sum(max(len(o), len(n)) for o, n in _diff_cost(list(old), list(new)))


def edit_size(shown: str, final: str) -> Tuple[int, float]:
    """(changed characters, changed characters / characters shown)."""
    a = [u[1] + u[2] for u in split_units(shown)]
    b = [u[1] + u[2] for u in split_units(final)]
    chars = 0
    for old_block, new_block in _diff_cost(a, b):
        wa, wb = _WORD.findall(old_block), _WORD.findall(new_block)
        if len(wa) > WORD_DIFF_MAX or len(wb) > WORD_DIFF_MAX:
            chars += max(len(old_block), len(new_block))
            continue
        chars += sum(_char_cost(o, n) for o, n in _diff_cost(wa, wb))
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


PENDING_TTL = timedelta(days=7)
MAX_PENDING = 10_000


class OversightRecorder:
    """In-memory recorder (per instance). The durable store is integration step P-8.

    Fifth review of PR #79, finding 6: the drafts shown and not yet signed are BOUNDED — an entry expires
    ``pending_ttl`` after it was shown (a sign-off after that is not counted), at most ``max_pending`` entries are
    kept (the oldest is evicted), and a sign-off of a different text than the one shown evicts the entry."""

    def __init__(self, clock: Optional[Callable[[], datetime]] = None, *, pending_ttl: timedelta = PENDING_TTL,
                 max_pending: int = MAX_PENDING):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._ttl = pending_ttl
        self._max = max(1, int(max_pending))
        self._pending: "OrderedDict[Tuple[str, str], Dict[str, Any]]" = OrderedDict()
        self.evicted = 0
        self.events: List[OversightEvent] = []
        self.mismatches = 0
        self._lock = threading.Lock()

    def shown(self, draft_id: str, reader_id: str, agent_id: str, draft_text: str) -> None:
        """Review of PR #79, finding 7: the LATEST version shown is the one a sign-off must match. A new text
        under the same draft id (a regenerated draft) replaces the pending one and restarts the clock; the
        same text shown again keeps the time it was first shown."""
        key = (draft_key(draft_id), reader_key(reader_id))
        digest = sha256_text(draft_text)
        now = self._clock()
        with self._lock:
            self._expire(now)
            current = self._pending.get(key)
            if current is None or current["draft_sha256"] != digest:
                self._pending[key] = {"agent_id": agent_id, "shown_at": now, "draft_sha256": digest}
                self._pending.move_to_end(key)
            while len(self._pending) > self._max:
                self._pending.popitem(last=False)
                self.evicted += 1

    def _expire(self, now: datetime) -> None:
        """Drop the entries shown more than the TTL ago (insertion order = order shown)."""
        stale = []
        for k, v in self._pending.items():               # sixth review, E4: oldest first; stop at the first valid
            if now - v["shown_at"] <= self._ttl:
                break
            stale.append(k)
        for k in stale:
            del self._pending[k]
        self.evicted += len(stale)

    def pending_records(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [{"draft_key": d, "reader_key": r, "agent_id": v["agent_id"],
                     "day": v["shown_at"].astimezone(timezone.utc).date().isoformat()}
                    for (d, r), v in self._pending.items()]

    def signed(self, draft_id: str, reader_id: str, shown_text: str, final_text: str) -> Optional[OversightEvent]:
        key = (draft_key(draft_id), reader_key(reader_id))
        with self._lock:
            self._expire(self._clock())
            pending = self._pending.get(key)
            if pending is None or pending["draft_sha256"] != sha256_text(shown_text):
                self.mismatches += 1
                if pending is not None:                   # finding 6: a mismatch evicts the entry
                    del self._pending[key]
                    self.evicted += 1
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
