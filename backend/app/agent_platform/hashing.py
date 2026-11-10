"""
The one SHA-256 helper of the agent platform (review of PR #79, finding 10). DRAFT, PENDING owner approval.

Rules, the same for every module (provenance records, trace content hashes, oversight, untrusted-text
hashes, model cards, eval files):
- ``None`` hashes as the empty text (one rule; never an error, never the string "None").
- ``str`` is hashed exactly as given, UTF-8 encoded: no Unicode or newline normalisation, because the
  hash must bind the very text that was shown, sent or signed.
- ``bytes`` are hashed as they are.
- Anything else (dicts, lists, numbers) is hashed as canonical JSON: keys sorted, UTF-8 kept, compact
  separators, unknown objects as ``str``.
- Files (``file_sha256``) are hashed with CRLF turned into LF, so a Windows checkout hashes like CI.

@module agent_platform.hashing
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return sha256_bytes(bytes(value))
    return sha256_bytes(canonical_text(value).encode("utf-8"))


def file_sha256(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes().replace(b"\r\n", b"\n"))
