"""
Secure User Storage with Encryption.

Implements ISO 27001 A.10.1.1 (Policy on the use of cryptographic controls),
A.10.1.2 (Key management), and A.9.2.1 (User registration and de-registration).

Storage backend: Firestore (durable, multi-instance) when available, with a
local-disk fallback for environments without Firestore (local dev / tests).
User profiles and password data are AES-256-GCM encrypted at rest regardless of
backend; the backend only ever holds opaque {ciphertext, metadata} blobs.

Durability note: the previous disk-only backend lost accounts on Cloud Run
redeploy/scale (ephemeral, per-instance disk). Firestore is the same store the
rest of the app uses (patients, studies, segmentations, WebAuthn credentials).

@module security.user_storage
"""

import json
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path

from app.core.logging import get_logger
from app.core.security.encryption import EncryptionService, DataClassification
from .models import User

logger = get_logger(__name__)

# Firestore collection for encrypted auth user records.
AUTH_USERS_COLLECTION = "auth_users"

# Datetime fields on the User model that are serialized as ISO strings.
_USER_DATETIME_FIELDS = ("created_at", "updated_at", "last_login", "last_password_change", "locked_until")


class SecureUserStorage:
    """
    Secure user storage with AES-256-GCM encryption and a durable backend.

    Backends:
    - Firestore (default when a client is available): durable, survives Cloud Run
      redeploy/scale, consistent across instances.
    - Local disk (fallback): `data/users/{profiles,passwords}/*.enc` — used when
      Firestore is not configured (local dev / unit tests).

    The public interface is backend-agnostic and unchanged from the disk-only
    version, so AuthService and the auth routes are unaffected.

    ISO 27001: A.10.1.1, A.10.1.2, A.9.2.1, A.12.3.1, A.12.4.1
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        encryption_service: Optional[EncryptionService] = None,
    ):
        self.storage_dir = storage_dir or Path("data/users")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.encryption_service = encryption_service or self._create_default_encryption_service()

        # Disk paths (fallback backend + migration source).
        self.users_dir = self.storage_dir / "profiles"
        self.passwords_dir = self.storage_dir / "passwords"
        self.users_dir.mkdir(exist_ok=True)
        self.passwords_dir.mkdir(exist_ok=True)

        # Prefer Firestore; fall back to disk when unavailable.
        self._db = self._try_firestore_client()
        if self._db is not None:
            self._migrate_disk_to_firestore()

        logger.info(
            "SecureUserStorage initialized",
            extra={
                "backend": "firestore" if self._db is not None else "disk",
                "encryption": "AES-256-GCM",
                "iso27001_control": "A.10.1.1",
            },
        )

    # ------------------------------------------------------------------ setup

    @staticmethod
    def _try_firestore_client():
        """Return a Firestore client, or None if unavailable (→ disk fallback).

        When pointed at an emulator (FIRESTORE_EMULATOR_HOST), verify the host is
        actually reachable first: CI and some test envs SET that variable without
        running an emulator, and firebase_admin would happily build a client whose
        operations then hang. A fast socket probe avoids that.
        """
        import os

        emu = os.environ.get("FIRESTORE_EMULATOR_HOST")
        if emu:
            import socket
            host, _, port = emu.partition(":")
            try:
                with socket.create_connection((host, int(port or 8080)), timeout=1.0):
                    pass
            except Exception:
                logger.warning(
                    "FIRESTORE_EMULATOR_HOST is set but unreachable — using encrypted disk fallback",
                    extra={"emulator_host": emu},
                )
                return None

        try:
            from app.core.firebase import get_firestore_client
            return get_firestore_client()
        except Exception as e:  # missing ADC (tests/local), init failure, etc.
            logger.warning(
                "Firestore unavailable for user storage — using encrypted disk fallback",
                extra={"error": str(e)},
            )
            return None

    def _create_default_encryption_service(self) -> EncryptionService:
        """Create the default encryption service (env master key, dev fallback)."""
        import os
        import secrets
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parent.parent.parent / '.env'
        load_dotenv(dotenv_path=env_path)

        master_key = os.getenv('ENCRYPTION_MASTER_KEY', '')
        if not master_key:
            master_key = secrets.token_urlsafe(32)
            logger.warning(
                "Using temporary encryption key. "
                "Set ENCRYPTION_MASTER_KEY in .env for production security."
            )
        return EncryptionService(master_key=master_key)

    # ------------------------------------------------------ encryption helpers

    def _encrypt(self, data: dict) -> str:
        """Encrypt a dict → an opaque JSON blob string ({ciphertext, metadata})."""
        ciphertext, metadata = self.encryption_service.encrypt_string(
            json.dumps(data), classification=DataClassification.PHI
        )
        return json.dumps({"ciphertext": ciphertext, "metadata": metadata})

    def _decrypt(self, blob: str) -> dict:
        """Decrypt an opaque JSON blob string → the original dict."""
        obj = json.loads(blob)
        plaintext = self.encryption_service.decrypt_string(obj["ciphertext"], obj["metadata"])
        return json.loads(plaintext)

    @staticmethod
    def _revive_user(user_data: dict) -> User:
        for field in _USER_DATETIME_FIELDS:
            if user_data.get(field):
                user_data[field] = datetime.fromisoformat(user_data[field])
        return User(**user_data)

    # ------------------------------------------------------ storage primitives
    # Each returns/accepts opaque encrypted blob STRINGS; identical bytes on
    # either backend, so migration is a straight copy (no re-encryption).

    def _write_blobs(self, user_id: str, profile_blob: str, password_blob: str) -> None:
        if self._db is not None:
            self._db.collection(AUTH_USERS_COLLECTION).document(user_id).set({
                "profile": profile_blob,
                "password": password_blob,
                "updated_at": datetime.utcnow().isoformat(),
            })
        else:
            (self.users_dir / f"{user_id}.enc").write_text(profile_blob, encoding='utf-8')
            (self.passwords_dir / f"{user_id}.enc").write_text(password_blob, encoding='utf-8')

    def _read_profile_blob(self, user_id: str) -> Optional[str]:
        if self._db is not None:
            doc = self._db.collection(AUTH_USERS_COLLECTION).document(user_id).get()
            return doc.to_dict().get("profile") if doc.exists else None
        f = self.users_dir / f"{user_id}.enc"
        return f.read_text(encoding='utf-8') if f.exists() else None

    def _read_password_blob(self, user_id: str) -> Optional[str]:
        if self._db is not None:
            doc = self._db.collection(AUTH_USERS_COLLECTION).document(user_id).get()
            return doc.to_dict().get("password") if doc.exists else None
        f = self.passwords_dir / f"{user_id}.enc"
        return f.read_text(encoding='utf-8') if f.exists() else None

    def _iter_profile_blobs(self):
        """Yield every stored profile blob string (for username/email scans)."""
        if self._db is not None:
            for doc in self._db.collection(AUTH_USERS_COLLECTION).stream():
                blob = doc.to_dict().get("profile")
                if blob:
                    yield blob
        else:
            for f in self.users_dir.glob("*.enc"):
                yield f.read_text(encoding='utf-8')

    def _migrate_disk_to_firestore(self) -> None:
        """One-time, idempotent copy of any disk profiles into Firestore."""
        try:
            disk_profiles = list(self.users_dir.glob("*.enc"))
            migrated = 0
            for pf in disk_profiles:
                user_id = pf.stem
                doc_ref = self._db.collection(AUTH_USERS_COLLECTION).document(user_id)
                if doc_ref.get().exists:
                    continue  # already in Firestore
                pwd_file = self.passwords_dir / f"{user_id}.enc"
                doc_ref.set({
                    "profile": pf.read_text(encoding='utf-8'),
                    "password": pwd_file.read_text(encoding='utf-8') if pwd_file.exists() else None,
                    "updated_at": datetime.utcnow().isoformat(),
                    "migrated_from_disk": True,
                })
                migrated += 1
            if migrated:
                logger.info("Migrated users from disk to Firestore", extra={"count": migrated})
        except Exception as e:
            logger.error(
                "Disk→Firestore user migration failed (continuing on Firestore)",
                extra={"error": str(e)}, exc_info=True,
            )

    # ------------------------------------------------------------- public API

    def save_user(
        self,
        user: User,
        password_hash: str,
        password_history: Optional[List[str]] = None,
    ) -> None:
        """Save user with encrypted storage (ISO 27001 A.9.2.1)."""
        try:
            profile_blob = self._encrypt(user.model_dump(mode='json'))
            password_blob = self._encrypt({
                "user_id": user.id,
                "username": user.username,
                "password_hash": password_hash,
                "password_history": password_history or [],
                "updated_at": datetime.utcnow().isoformat(),
            })
            self._write_blobs(user.id, profile_blob, password_blob)
            logger.info(
                "User saved securely",
                extra={
                    "user_id": user.id,
                    "username": user.username,
                    "backend": "firestore" if self._db is not None else "disk",
                    "encryption": "AES-256-GCM",
                    "iso27001_control": "A.10.1.1",
                },
            )
        except Exception as e:
            logger.error(
                "Failed to save user",
                extra={"user_id": user.id if user else None, "error": str(e)},
                exc_info=True,
            )
            raise

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Retrieve and decrypt a user by ID (ISO 27001 A.10.1.1)."""
        try:
            blob = self._read_profile_blob(user_id)
            if blob is None:
                logger.debug("User not found", extra={"user_id": user_id})
                return None
            user = self._revive_user(self._decrypt(blob))
            logger.debug("User retrieved", extra={"user_id": user_id, "username": user.username})
            return user
        except Exception as e:
            logger.error(
                "Failed to retrieve user",
                extra={"user_id": user_id, "error": str(e)}, exc_info=True,
            )
            return None

    def get_user_password_data(self, user_id: str) -> Optional[Dict]:
        """Get decrypted password data (hash + history) for a user."""
        try:
            blob = self._read_password_blob(user_id)
            if blob is None:
                return None
            return self._decrypt(blob)
        except Exception as e:
            logger.error(
                "Failed to retrieve password data",
                extra={"user_id": user_id, "error": str(e)}, exc_info=True,
            )
            return None

    def _find_user_by(self, field: str, value: str) -> Optional[User]:
        for blob in self._iter_profile_blobs():
            try:
                user_data = self._decrypt(blob)
                if user_data.get(field) == value:
                    return self._revive_user(user_data)
            except Exception as e:
                logger.error("Error scanning user record", extra={"error": str(e)})
                continue
        return None

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username (scans + decrypts; user counts are small)."""
        return self._find_user_by("username", username)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email (scans + decrypts)."""
        return self._find_user_by("email", email)

    def list_all_users(self) -> List[User]:
        """List all users (decrypts every record). ISO 27001 A.9.2.5."""
        users: List[User] = []
        for blob in self._iter_profile_blobs():
            try:
                users.append(self._revive_user(self._decrypt(blob)))
            except Exception as e:
                logger.error("Error loading user", extra={"error": str(e)})
                continue
        logger.info("Listed all users", extra={"count": len(users)})
        return users

    def delete_user(self, user_id: str) -> bool:
        """Delete a user's profile + password (ISO 27001 A.11.2.7)."""
        try:
            if self._db is not None:
                doc_ref = self._db.collection(AUTH_USERS_COLLECTION).document(user_id)
                existed = doc_ref.get().exists
                if existed:
                    doc_ref.delete()
                deleted = existed
            else:
                deleted = False
                profile_file = self.users_dir / f"{user_id}.enc"
                password_file = self.passwords_dir / f"{user_id}.enc"
                if profile_file.exists():
                    profile_file.unlink()
                    deleted = True
                if password_file.exists():
                    password_file.unlink()
                    deleted = True
            if deleted:
                logger.info("User deleted", extra={"user_id": user_id, "iso27001_control": "A.11.2.7"})
            return deleted
        except Exception as e:
            logger.error(
                "Failed to delete user",
                extra={"user_id": user_id, "error": str(e)}, exc_info=True,
            )
            return False

    def user_exists(self, user_id: str) -> bool:
        """Check if a user exists."""
        if self._db is not None:
            return self._db.collection(AUTH_USERS_COLLECTION).document(user_id).get().exists
        return (self.users_dir / f"{user_id}.enc").exists()

    def username_exists(self, username: str) -> bool:
        """Check if a username exists."""
        return self.get_user_by_username(username) is not None

    def email_exists(self, email: str) -> bool:
        """Check if an email exists."""
        return self.get_user_by_email(email) is not None

    def get_user_count(self) -> int:
        """Get the total number of users."""
        if self._db is not None:
            return sum(1 for _ in self._db.collection(AUTH_USERS_COLLECTION).stream())
        return len(list(self.users_dir.glob("*.enc")))


# Singleton instance
_user_storage: Optional[SecureUserStorage] = None


def get_user_storage() -> SecureUserStorage:
    """Get the singleton SecureUserStorage instance."""
    global _user_storage
    if _user_storage is None:
        _user_storage = SecureUserStorage()
    return _user_storage
