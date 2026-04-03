"""
WebAuthn / Passkeys Service.

Handles WebAuthn credential registration and authentication using py_webauthn.
Credentials are stored encrypted alongside user profiles in Firestore.

@module security.webauthn_service
"""

import json
import time
from typing import Optional
from datetime import datetime

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
    PublicKeyCredentialDescriptor,
    AttestationConveyancePreference,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

from app.core.logging import get_logger

logger = get_logger(__name__)

# Challenge TTL: 5 minutes
CHALLENGE_TTL_SECONDS = 300


class WebAuthnService:
    """Manages WebAuthn credential registration and authentication."""

    def __init__(self, rp_id: str, rp_name: str, origin: str, db=None):
        self.rp_id = rp_id
        self.rp_name = rp_name
        self.origin = origin
        self.db = db  # Firestore client
        self._challenges: dict[str, tuple[bytes, float]] = {}  # user_id -> (challenge, timestamp)

    def _store_challenge(self, user_id: str, challenge: bytes):
        self._cleanup_expired()
        self._challenges[user_id] = (challenge, time.time())

    def _get_challenge(self, user_id: str) -> Optional[bytes]:
        self._cleanup_expired()
        entry = self._challenges.pop(user_id, None)
        if entry is None:
            return None
        challenge, ts = entry
        if time.time() - ts > CHALLENGE_TTL_SECONDS:
            return None
        return challenge

    def _cleanup_expired(self):
        now = time.time()
        expired = [k for k, (_, ts) in self._challenges.items() if now - ts > CHALLENGE_TTL_SECONDS]
        for k in expired:
            del self._challenges[k]

    # ─── Firestore Credential Storage ───

    def _get_credentials_collection(self, user_id: str):
        return self.db.collection('users').document(user_id).collection('webauthn_credentials')

    def get_credentials(self, user_id: str) -> list[dict]:
        if not self.db:
            return []
        try:
            docs = self._get_credentials_collection(user_id).stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error("Failed to get WebAuthn credentials", extra={"user_id": user_id, "error": str(e)})
            return []

    def save_credential(self, user_id: str, credential: dict):
        if not self.db:
            return
        try:
            self._get_credentials_collection(user_id).document(credential['credential_id']).set(credential)
        except Exception as e:
            logger.error("Failed to save WebAuthn credential", extra={"user_id": user_id, "error": str(e)})

    def update_credential(self, user_id: str, credential_id: str, updates: dict):
        if not self.db:
            return
        try:
            self._get_credentials_collection(user_id).document(credential_id).update(updates)
        except Exception as e:
            logger.error("Failed to update WebAuthn credential", extra={"error": str(e)})

    def delete_credential(self, user_id: str, credential_id: str) -> bool:
        if not self.db:
            return False
        try:
            self._get_credentials_collection(user_id).document(credential_id).delete()
            return True
        except Exception as e:
            logger.error("Failed to delete WebAuthn credential", extra={"error": str(e)})
            return False

    # ─── Registration ───

    def generate_registration(self, user_id: str, username: str, display_name: str) -> dict:
        existing = self.get_credentials(user_id)
        exclude_credentials = [
            PublicKeyCredentialDescriptor(id=bytes.fromhex(c['credential_id_hex']))
            for c in existing if 'credential_id_hex' in c
        ]

        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=user_id.encode('utf-8'),
            user_name=username,
            user_display_name=display_name,
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            supported_pub_key_algs=[
                COSEAlgorithmIdentifier.ECDSA_SHA_256,
                COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
            ],
            exclude_credentials=exclude_credentials,
        )

        self._store_challenge(user_id, options.challenge)

        return json.loads(options_to_json(options))

    def verify_registration(self, user_id: str, credential_json: dict, device_name: str = "") -> dict:
        challenge = self._get_challenge(user_id)
        if not challenge:
            raise ValueError("Registration challenge expired or not found")

        verification = verify_registration_response(
            credential=credential_json,
            expected_challenge=challenge,
            expected_rp_id=self.rp_id,
            expected_origin=self.origin,
        )

        credential_id_hex = verification.credential_id.hex()
        public_key_hex = verification.credential_public_key.hex()

        cred_data = {
            'credential_id': credential_id_hex[:16],  # Short display ID
            'credential_id_hex': credential_id_hex,
            'public_key_hex': public_key_hex,
            'sign_count': verification.sign_count,
            'device_name': device_name or 'Unknown device',
            'created_at': datetime.utcnow().isoformat(),
            'last_used': None,
        }

        self.save_credential(user_id, cred_data)

        logger.info("WebAuthn credential registered", extra={
            "user_id": user_id,
            "credential_id": credential_id_hex[:16],
            "device_name": device_name,
        })

        return cred_data

    # ─── Authentication ───

    def generate_authentication(self, user_id: str) -> dict:
        existing = self.get_credentials(user_id)
        if not existing:
            raise ValueError("No passkeys registered for this user")

        allow_credentials = [
            PublicKeyCredentialDescriptor(id=bytes.fromhex(c['credential_id_hex']))
            for c in existing if 'credential_id_hex' in c
        ]

        options = generate_authentication_options(
            rp_id=self.rp_id,
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )

        self._store_challenge(user_id, options.challenge)

        return json.loads(options_to_json(options))

    def verify_authentication(self, user_id: str, credential_json: dict) -> bool:
        challenge = self._get_challenge(user_id)
        if not challenge:
            raise ValueError("Authentication challenge expired or not found")

        existing = self.get_credentials(user_id)
        cred_id_hex = credential_json.get('id', '') or credential_json.get('rawId', '')

        # Find matching credential
        matched = None
        for c in existing:
            if c.get('credential_id_hex', '').startswith(cred_id_hex) or cred_id_hex.startswith(c.get('credential_id_hex', 'x')):
                matched = c
                break

        if not matched:
            # Try matching by raw bytes
            from webauthn.helpers import base64url_to_bytes
            try:
                raw_id_bytes = base64url_to_bytes(cred_id_hex)
                raw_hex = raw_id_bytes.hex()
                for c in existing:
                    if c.get('credential_id_hex') == raw_hex:
                        matched = c
                        break
            except Exception:
                pass

        if not matched:
            raise ValueError("Credential not found")

        verification = verify_authentication_response(
            credential=credential_json,
            expected_challenge=challenge,
            expected_rp_id=self.rp_id,
            expected_origin=self.origin,
            credential_public_key=bytes.fromhex(matched['public_key_hex']),
            credential_current_sign_count=matched.get('sign_count', 0),
        )

        # Update sign count and last used
        self.update_credential(user_id, matched['credential_id'], {
            'sign_count': verification.new_sign_count,
            'last_used': datetime.utcnow().isoformat(),
        })

        logger.info("WebAuthn authentication successful", extra={
            "user_id": user_id,
            "credential_id": matched['credential_id'],
        })

        return True
