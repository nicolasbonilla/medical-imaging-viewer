"""
Rotating refresh tokens — CAPA-015, RC-068 (REQ-SEC-025; HAZ-010).

THE DEFECT (found 2026-10-24, main @ 70cc5c7)
---------------------------------------------
The frontend called `/auth/refresh`, which did not exist, and login issued a single 60-minute
access token: every user was forced to sign in again every hour, and an expired session made
unsaved segmentation work unsaveable (RC-069, frontend).

THE CONTROL
-----------
- A short-lived access token (JWT, 15 minutes by default) plus an opaque refresh token
  (384 random bits) that the browser keeps in an HttpOnly, Secure, SameSite=Strict cookie scoped
  to `/api/v1/auth` — page scripts can never read it.
- Server-side, only the SHA-256 of each refresh token is stored (Firestore `refresh_tokens`),
  grouped in a FAMILY (one per sign-in, `refresh_token_families`).
- Rotation: every refresh consumes the presented token and issues a new one, in one Firestore
  transaction. Presenting an already-used token is REUSE (a copy is in someone else's hands):
  the whole family is revoked and the event is audited (`auth.token.reuse_detected`).
- Expiry: idle (REFRESH_TOKEN_IDLE_MINUTES, default 30 — a refresh token not rotated within that
  time is dead) and absolute (REFRESH_TOKEN_ABSOLUTE_HOURS, default 12 — one clinical shift; a
  fresh sign-in at least once per shift). Why not the 12 h idle / 7 d absolute often quoted for
  consumer apps: the app already logs a user off after 15 minutes without activity (HIPAA
  §164.312(a)(2)(iii), REQ-SEC-003 context). A 12 h idle window would let anyone who opens the
  browser of a shared clinical workstation, hours after the tab was closed without logging out,
  continue the previous user's session silently — that would weaken the existing automatic
  log-off. 30 minutes is twice the client's inactivity limit, enough for the silent refresh
  (every ~13 minutes while the app is open) to survive background-tab timer throttling.
  Both values are configurable; the owner decides (CAPA-015 decision D-2).
- Revocation: on logout (the family of the presented cookie), on password change (every LIVE
  family of the user — revoked and expired families are left alone, review m8), and at refresh
  time when the user no longer exists, is inactive or is locked. The new access token carries the
  role stored NOW, not the role at sign-in. Access tokens already issued are NOT revoked across
  instances: they stay valid until they expire (at most JWT_ACCESS_TOKEN_EXPIRE_MINUTES).
- Grace window (review m5): presenting the IMMEDIATELY previous token within
  REFRESH_TOKEN_REUSE_GRACE_SECONDS (default 30) of its use, while its successor has not been used
  yet, returns that same successor (a lost response, or two tabs refreshing at once); for that
  window the successor is kept sealed (AES-GCM, key derived from the server secret) and the seal is
  cleared once the successor is used. Any other replay is reuse and revokes the family.

Backends: Firestore (production; transactions keep rotation atomic across Cloud Run instances)
and memory (tests; local runs without cloud credentials). When Firestore is unavailable in
production a refresh fails closed (401) and the frontend asks the user to sign in again,
keeping unsaved work (RC-069).

@module security.refresh_tokens
"""

import base64
import hashlib
import hmac
import os
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

TOKENS_COLLECTION = "refresh_tokens"
FAMILIES_COLLECTION = "refresh_token_families"

# Firebase Hosting forwards only a cookie named `__session` to Cloud Run (all others are stripped),
# and the auth routes are served through a Hosting rewrite on the app's own origin (firebase.json),
# which is what makes a SameSite=Strict cookie possible at all (the API's run.app host is another site).
REFRESH_COOKIE_NAME = "__session"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class RefreshError(Exception):
    """A refresh token could not be used. `reason` is a short audit code."""

    def __init__(self, reason: str, *, user_id: Optional[str] = None, family_id: Optional[str] = None,
                 reuse: bool = False):
        super().__init__(reason)
        self.reason, self.user_id, self.family_id, self.reuse = reason, user_id, family_id, reuse


@dataclass
class IssuedRefreshToken:
    token: str
    family_id: str
    user_id: str
    expires_at: datetime
    family_expires_at: datetime
    rotation_count: int = 0
    issued_at: Optional[datetime] = None
    grace_replay: bool = False

    @property
    def max_age_seconds(self) -> int:
        """Cookie lifetime: until the earlier of the idle and the absolute expiry."""
        end = min(self.expires_at, self.family_expires_at)
        start = self.issued_at or _utcnow()
        return max(0, int((end - start).total_seconds()))


# --------------------------------------------------------------------------- repositories
# A repository runs `fn(tx)` atomically; `tx` reads and writes token and family documents.

class _MemoryTx:
    def __init__(self, repo: "MemoryRefreshRepo"):
        self.repo = repo

    def get_token(self, token_hash):
        d = self.repo.tokens.get(token_hash)
        return dict(d) if d else None

    def get_family(self, family_id):
        d = self.repo.families.get(family_id)
        return dict(d) if d else None

    def create_token(self, token_hash, data):
        if token_hash in self.repo.tokens:
            raise RuntimeError("refresh token hash collision")
        self.repo.tokens[token_hash] = dict(data)

    def update_token(self, token_hash, data):
        self.repo.tokens[token_hash].update(data)

    def create_family(self, family_id, data):
        self.repo.families[family_id] = dict(data)

    def update_family(self, family_id, data):
        self.repo.families[family_id].update(data)


class MemoryRefreshRepo:
    """In-process repository (tests, local runs). Not shared between Cloud Run instances."""

    def __init__(self):
        self.tokens: Dict[str, Dict[str, Any]] = {}
        self.families: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def run(self, fn: Callable[[Any], Any]):
        with self._lock:
            return fn(_MemoryTx(self))

    def families_of(self, user_id: str, now: Optional[datetime] = None):
        """LIVE families of a user: not revoked and not past their absolute expiry."""
        with self._lock:
            return [fid for fid, f in self.families.items()
                    if f.get("user_id") == user_id and not f.get("revoked")
                    and (now is None or _aware(f.get("absolute_expires_at")) > now)]

    def dump(self) -> Dict[str, Any]:
        with self._lock:
            return {"tokens": dict(self.tokens), "families": dict(self.families)}


class _FirestoreTx:
    def __init__(self, db, txn):
        self.db, self.txn = db, txn

    def _ref(self, coll, doc_id):
        return self.db.collection(coll).document(doc_id)

    def _get(self, coll, doc_id):
        snap = self._ref(coll, doc_id).get(transaction=self.txn)
        return snap.to_dict() if snap.exists else None

    def get_token(self, token_hash):
        return self._get(TOKENS_COLLECTION, token_hash)

    def get_family(self, family_id):
        return self._get(FAMILIES_COLLECTION, family_id)

    def create_token(self, token_hash, data):
        self.txn.create(self._ref(TOKENS_COLLECTION, token_hash), data)

    def update_token(self, token_hash, data):
        self.txn.update(self._ref(TOKENS_COLLECTION, token_hash), data)

    def create_family(self, family_id, data):
        self.txn.create(self._ref(FAMILIES_COLLECTION, family_id), data)

    def update_family(self, family_id, data):
        self.txn.update(self._ref(FAMILIES_COLLECTION, family_id), data)


class FirestoreRefreshRepo:
    """Firestore repository: every rotation is one transaction (all reads before writes)."""

    def __init__(self, db, transactional: Optional[Callable] = None):
        self.db = db
        if transactional is None:
            from google.cloud import firestore
            transactional = firestore.transactional
        self._transactional = transactional

    def run(self, fn: Callable[[Any], Any]):
        @self._transactional
        def _in_txn(txn):
            return fn(_FirestoreTx(self.db, txn))
        return _in_txn(self.db.transaction())

    def families_of(self, user_id: str, now: Optional[datetime] = None):
        """LIVE families of a user (two equality filters need no composite index; the absolute
        expiry is checked here)."""
        coll = self.db.collection(FAMILIES_COLLECTION)
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
            q = coll.where(filter=FieldFilter("user_id", "==", user_id)).where(
                filter=FieldFilter("revoked", "==", False))
        except Exception:  # pragma: no cover
            q = coll.where("user_id", "==", user_id).where("revoked", "==", False)
        out = []
        for snap in q.stream():
            f = snap.to_dict() or {}
            if f.get("revoked"):
                continue
            if now is not None and _aware(f.get("absolute_expires_at")) <= now:
                continue
            out.append(snap.id)
        return out


# --------------------------------------------------------------------------- store

def _derived_key(label: bytes) -> bytes:
    """A key derived from the server secret for one purpose (never the JWT key used raw)."""
    secret = os.environ.get("JWT_SECRET_KEY", "")
    if not secret:
        try:
            from app.core.config import get_settings
            secret = get_settings().SECRET_KEY
        except Exception:  # pragma: no cover
            secret = ""
    return hmac.new(secret.encode("utf-8"), label, hashlib.sha256).digest()


class RefreshTokenStore:
    def __init__(self, repo=None, idle: Optional[timedelta] = None, absolute: Optional[timedelta] = None,
                 clock: Optional[Callable[[], datetime]] = None, grace: Optional[timedelta] = None,
                 seal_key: Optional[bytes] = None):
        self.repo = repo if repo is not None else MemoryRefreshRepo()
        self.idle = idle or timedelta(minutes=int(os.environ.get("REFRESH_TOKEN_IDLE_MINUTES", "30")))
        self.absolute = absolute or timedelta(hours=int(os.environ.get("REFRESH_TOKEN_ABSOLUTE_HOURS", "12")))
        self.clock = clock or _utcnow
        self.grace = grace if grace is not None else timedelta(
            seconds=int(os.environ.get("REFRESH_TOKEN_REUSE_GRACE_SECONDS", "30")))
        self._seal_key = seal_key or _derived_key(b"mstool-refresh-grace-seal-v1")

    def _seal(self, token: str, family_id: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = secrets.token_bytes(12)
        ct = AESGCM(self._seal_key).encrypt(nonce, token.encode("utf-8"), family_id.encode("utf-8"))
        return base64.urlsafe_b64encode(nonce + ct).decode("ascii")

    def _unseal(self, sealed: str, family_id: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = base64.urlsafe_b64decode(sealed.encode("ascii"))
        return AESGCM(self._seal_key).decrypt(raw[:12], raw[12:], family_id.encode("utf-8")).decode("utf-8")

    def _new_token_doc(self, family_id, user_id, now, rotation):
        return {"family_id": family_id, "user_id": user_id, "created_at": now,
                "expires_at": now + self.idle, "used": False, "rotation": rotation}

    def issue(self, user_id: str) -> IssuedRefreshToken:
        """Start a new family (a sign-in) and return its first token."""
        now = self.clock()
        family_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(48)
        family = {"user_id": user_id, "created_at": now, "absolute_expires_at": now + self.absolute,
                  "revoked": False, "rotation_count": 0, "last_rotated_at": now}

        def fn(tx):
            tx.create_family(family_id, family)
            tx.create_token(hash_refresh_token(token), self._new_token_doc(family_id, user_id, now, 0))

        self.repo.run(fn)
        return IssuedRefreshToken(token, family_id, user_id, now + self.idle, now + self.absolute, 0, now)

    def rotate(self, token: str) -> IssuedRefreshToken:
        """Consume `token` and return its successor. Raises RefreshError (reason code)."""
        if not token or len(token) > 512:
            raise RefreshError("missing")
        now = self.clock()
        token_hash = hash_refresh_token(token)
        new_token = secrets.token_urlsafe(48)

        def fn(tx):
            t = tx.get_token(token_hash)
            if t is None:
                return ("error", "unknown", None, None)
            fam = tx.get_family(t["family_id"])
            if fam is None:
                return ("error", "unknown", t.get("user_id"), t["family_id"])
            if fam.get("revoked"):
                return ("error", "revoked", t.get("user_id"), t["family_id"])
            if t.get("used"):
                succ_hash = t.get("replaced_by")
                succ = tx.get_token(succ_hash) if succ_hash else None
                used_at = _aware(t.get("used_at"))
                if (self.grace and used_at is not None and now - used_at <= self.grace and succ is not None
                        and not succ.get("used") and t.get("successor_sealed")
                        and now < _aware(fam["absolute_expires_at"])):
                    # the immediately previous token, within the window, its successor still unused
                    return ("grace", t["successor_sealed"], t["user_id"], t["family_id"],
                            _aware(fam["absolute_expires_at"]), _aware(succ["expires_at"]),
                            int(fam.get("rotation_count") or 0))
                tx.update_family(t["family_id"], {"revoked": True, "revoked_reason": "reuse_detected",
                                                  "revoked_at": now})
                return ("reuse", "reuse_detected", t.get("user_id"), t["family_id"])
            if now >= _aware(fam["absolute_expires_at"]):
                return ("error", "absolute_expired", t.get("user_id"), t["family_id"])
            if now >= _aware(t["expires_at"]):
                return ("error", "idle_expired", t.get("user_id"), t["family_id"])
            rotation = int(fam.get("rotation_count") or 0) + 1
            new_hash = hash_refresh_token(new_token)
            # read before any write (Firestore transactions); a predecessor already deleted (TTL) is skipped
            pred = tx.get_token(t["predecessor"]) if t.get("predecessor") else None
            tx.update_token(token_hash, {"used": True, "used_at": now, "replaced_by": new_hash,
                                         "successor_sealed": self._seal(new_token, t["family_id"])})
            new_doc = self._new_token_doc(t["family_id"], t["user_id"], now, rotation)
            new_doc["predecessor"] = token_hash
            tx.create_token(new_hash, new_doc)
            if pred is not None and pred.get("successor_sealed"):   # this token is used: drop the sealed copy
                tx.update_token(t["predecessor"], {"successor_sealed": None})
            tx.update_family(t["family_id"], {"rotation_count": rotation, "last_rotated_at": now})
            return ("ok", rotation, t["user_id"], t["family_id"], _aware(fam["absolute_expires_at"]))

        result = self.repo.run(fn)
        if result[0] == "ok":
            _, rotation, user_id, family_id, family_expires = result
            return IssuedRefreshToken(new_token, family_id, user_id, now + self.idle, family_expires, rotation, now)
        if result[0] == "grace":
            _, sealed, user_id, family_id, family_expires, succ_expires, rotation = result
            return IssuedRefreshToken(self._unseal(sealed, family_id), family_id, user_id, succ_expires,
                                      family_expires, rotation, now, grace_replay=True)
        _, reason, user_id, family_id = result[:4]
        raise RefreshError(reason, user_id=user_id, family_id=family_id, reuse=result[0] == "reuse")

    def peek_owner(self, token: str):
        """(user_id, family_id) of a token without consuming it, or (None, None)."""
        if not token or len(token) > 512:
            return None, None
        t = self.repo.run(lambda tx: tx.get_token(hash_refresh_token(token)))
        return (t.get("user_id"), t.get("family_id")) if t else (None, None)

    def revoke_family(self, family_id: str, reason: str) -> None:
        now = self.clock()

        def fn(tx):
            if tx.get_family(family_id) is not None:
                tx.update_family(family_id, {"revoked": True, "revoked_reason": reason, "revoked_at": now})

        self.repo.run(fn)

    def revoke_by_token(self, token: str, reason: str) -> Optional[str]:
        """Revoke the family of `token` (logout). Returns the family id, or None if unknown."""
        user_id, family_id = self.peek_owner(token)
        if family_id:
            self.revoke_family(family_id, reason)
        return family_id

    def revoke_all_for_user(self, user_id: str, reason: str) -> int:
        families = self.repo.families_of(user_id, self.clock())
        for family_id in families:
            self.revoke_family(family_id, reason)
        return len(families)


_store: Optional[RefreshTokenStore] = None
_store_lock = threading.Lock()


def _default_store() -> RefreshTokenStore:
    from app.core.config import SecuritySettings
    sec = SecuritySettings()
    idle = timedelta(minutes=sec.REFRESH_TOKEN_IDLE_MINUTES)
    absolute = timedelta(hours=sec.REFRESH_TOKEN_ABSOLUTE_HOURS)
    grace = timedelta(seconds=sec.REFRESH_TOKEN_REUSE_GRACE_SECONDS)
    backend = (os.environ.get("REFRESH_TOKEN_BACKEND") or "firestore").strip().lower()
    if backend == "firestore":
        try:
            from app.core.firebase import get_firestore_client
            return RefreshTokenStore(repo=FirestoreRefreshRepo(get_firestore_client()), idle=idle, absolute=absolute, grace=grace)
        except Exception as e:  # noqa: BLE001
            logger.error(
                "REFRESH_STORE_UNAVAILABLE Firestore unavailable for refresh tokens — using a "
                "per-instance memory store; sessions will not survive a restart and may need a new "
                "sign-in when another instance answers",
                extra={"error_type": type(e).__name__},
            )
    return RefreshTokenStore(repo=MemoryRefreshRepo(), idle=idle, absolute=absolute, grace=grace)


def get_refresh_token_store() -> RefreshTokenStore:
    """FastAPI dependency: the process-wide refresh-token store."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = _default_store()
    return _store


def set_refresh_cookie(response, issued: IssuedRefreshToken) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=issued.token,
        max_age=issued.max_age_seconds,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH, secure=True,
                           httponly=True, samesite="strict")


def no_store(response) -> None:
    """Responses that carry a token must never be cached (Firebase Hosting CDN, browsers)."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
