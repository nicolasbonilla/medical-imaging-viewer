"""
Data-at-Rest Encryption Module
ISO 27001 A.10.1.1 - Policy on the use of cryptographic controls
ISO 27001 A.10.1.2 - Key management

Provides AES-256-GCM encryption for sensitive data stored in Redis and databases.
Implements NIST SP 800-38D authenticated encryption with additional data (AEAD).

@module core.security.encryption
"""

import os
import base64
import hashlib
import secrets
from typing import Tuple, Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.exceptions import InvalidTag

from app.core.logging import get_logger, get_audit_logger
from app.core.logging.audit import AuditEventType, AuditSeverity

logger = get_logger(__name__)
audit_logger = get_audit_logger()


class EncryptionError(Exception):
    """Base exception for encryption errors."""
    pass


class DecryptionError(Exception):
    """Base exception for decryption errors."""
    pass


class KeyDerivationError(Exception):
    """Base exception for key derivation errors."""
    pass


class DataClassification(str, Enum):
    """
    Data classification levels (ISO 27001 A.8.2.1).

    Determines encryption requirements and key rotation policies.
    """
    PUBLIC = "public"              # No encryption required
    INTERNAL = "internal"          # Standard encryption
    CONFIDENTIAL = "confidential"  # Enhanced encryption + strict access
    PHI = "phi"                    # HIPAA PHI - highest security
    PII = "pii"                    # Personal Identifiable Information


# ============================================================================
# AES-256-GCM ENCRYPTION ENGINE
# ============================================================================

class AESGCMEncryption:
    """
    AES-256-GCM authenticated encryption.

    ISO 27001 A.10.1.1 - Uses NIST-approved algorithm
    NIST SP 800-38D - Galois/Counter Mode

    Features:
    - AES-256 encryption (256-bit keys)
    - GCM mode (Galois/Counter Mode)
    - AEAD (Authenticated Encryption with Associated Data)
    - Random 96-bit nonces (never reused)
    - 128-bit authentication tags
    """

    # Key size in bytes (256 bits = 32 bytes)
    KEY_SIZE = 32

    # Nonce size in bytes (96 bits = 12 bytes, recommended for GCM)
    NONCE_SIZE = 12

    # Tag size in bytes (128 bits = 16 bytes, maximum for GCM)
    TAG_SIZE = 16

    def __init__(self, key: bytes):
        """
        Initialize AES-GCM cipher.

        Args:
            key: 32-byte (256-bit) encryption key

        Raises:
            ValueError: If key size is invalid
        """
        if len(key) != self.KEY_SIZE:
            raise ValueError(f"Key must be exactly {self.KEY_SIZE} bytes (256 bits)")

        self.cipher = AESGCM(key)
        self.key_id = hashlib.sha256(key).hexdigest()[:16]  # Key fingerprint

        logger.debug(f"AES-GCM cipher initialized (key_id: {self.key_id})")

    def encrypt(
        self,
        plaintext: bytes,
        associated_data: Optional[bytes] = None
    ) -> Tuple[bytes, bytes]:
        """
        Encrypt plaintext using AES-256-GCM.

        Args:
            plaintext: Data to encrypt
            associated_data: Optional additional authenticated data (not encrypted)

        Returns:
            Tuple of (ciphertext, nonce)

        Raises:
            EncryptionError: If encryption fails
        """
        try:
            # Generate random nonce (MUST be unique for each encryption)
            nonce = os.urandom(self.NONCE_SIZE)

            # Encrypt with authentication
            ciphertext = self.cipher.encrypt(nonce, plaintext, associated_data)

            return ciphertext, nonce

        except Exception as e:
            logger.error(f"Encryption failed: {e}", exc_info=True)
            raise EncryptionError(f"Encryption failed: {e}")

    def decrypt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        associated_data: Optional[bytes] = None
    ) -> bytes:
        """
        Decrypt ciphertext using AES-256-GCM.

        Args:
            ciphertext: Encrypted data (includes authentication tag)
            nonce: Nonce used during encryption
            associated_data: Optional additional authenticated data

        Returns:
            Decrypted plaintext

        Raises:
            DecryptionError: If decryption or authentication fails
        """
        try:
            # Decrypt and verify authentication tag
            plaintext = self.cipher.decrypt(nonce, ciphertext, associated_data)

            return plaintext

        except InvalidTag:
            # Authentication tag verification failed - data was tampered with
            audit_logger.log_security_event(
                event_type=AuditEventType.SECURITY_DATA_INTEGRITY_VIOLATION,
                severity=AuditSeverity.CRITICAL,
                description="Data integrity violation: Authentication tag verification failed",
                metadata={
                    'key_id': self.key_id,
                    'error': 'Invalid authentication tag'
                }
            )
            raise DecryptionError("Data integrity violation: Authentication failed")

        except Exception as e:
            logger.error(f"Decryption failed: {e}", exc_info=True)
            raise DecryptionError(f"Decryption failed: {e}")


# ============================================================================
# KEY DERIVATION (PBKDF2)
# ============================================================================

class KeyDerivation:
    """
    PBKDF2-HMAC-SHA256 key derivation.

    ISO 27001 A.10.1.2 - Key management
    NIST SP 800-132 - Recommendation for Password-Based Key Derivation
    """

    # Default iterations (100,000+ recommended by NIST)
    DEFAULT_ITERATIONS = 100_000

    # Salt size in bytes (128 bits minimum)
    SALT_SIZE = 16

    @staticmethod
    def derive_key(
        master_key: str,
        salt: bytes,
        iterations: int = DEFAULT_ITERATIONS,
        key_length: int = AESGCMEncryption.KEY_SIZE
    ) -> bytes:
        """
        Derive encryption key from master key using PBKDF2.

        Args:
            master_key: Master key (password/secret)
            salt: Random salt (must be stored)
            iterations: KDF iterations (higher = more secure, slower)
            key_length: Derived key length in bytes

        Returns:
            Derived key

        Raises:
            KeyDerivationError: If derivation fails
        """
        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=key_length,
                salt=salt,
                iterations=iterations,
            )

            derived_key = kdf.derive(master_key.encode('utf-8'))

            return derived_key

        except Exception as e:
            logger.error(f"Key derivation failed: {e}", exc_info=True)
            raise KeyDerivationError(f"Key derivation failed: {e}")

    @staticmethod
    def generate_salt() -> bytes:
        """Generate random salt for key derivation."""
        return os.urandom(KeyDerivation.SALT_SIZE)


# ============================================================================
# ENCRYPTION SERVICE (HIGH-LEVEL API)
# ============================================================================

class EncryptionService:
    """
    High-level encryption service for data-at-rest protection.

    ISO 27001 A.10.1.1, A.10.1.2
    HIPAA § 164.312(a)(2)(iv) - Encryption and decryption

    Usage:
        >>> service = EncryptionService(master_key="your-master-key")
        >>> encrypted, metadata = service.encrypt_data(
        ...     data=b"sensitive data",
        ...     classification=DataClassification.PHI
        ... )
        >>> decrypted = service.decrypt_data(encrypted, metadata)
    """

    def __init__(
        self,
        master_key: str,
        kdf_iterations: int = KeyDerivation.DEFAULT_ITERATIONS
    ):
        """
        Initialize encryption service.

        Args:
            master_key: Master encryption key (from environment)
            kdf_iterations: PBKDF2 iterations
        """
        self.master_key = master_key
        self.kdf_iterations = kdf_iterations

        # Derive salt deterministically from master key to ensure consistency
        # This ensures the same master key always produces the same derived key
        import hashlib
        salt_source = f"encryption-salt-v1-{master_key}".encode('utf-8')
        self.salt = hashlib.sha256(salt_source).digest()[:KeyDerivation.SALT_SIZE]

        # Derive encryption key from master key
        self.encryption_key = KeyDerivation.derive_key(
            master_key=master_key,
            salt=self.salt,
            iterations=kdf_iterations
        )

        # Initialize cipher
        self.cipher = AESGCMEncryption(self.encryption_key)

        logger.info(
            "Encryption service initialized",
            extra={
                "key_id": self.cipher.key_id,
                "kdf_iterations": kdf_iterations,
                "iso27001_control": "A.10.1.1, A.10.1.2"
            }
        )

    def encrypt_data(
        self,
        data: bytes,
        classification: DataClassification = DataClassification.CONFIDENTIAL,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Encrypt data with metadata.

        Args:
            data: Plaintext data to encrypt
            classification: Data classification level
            context: Optional context metadata (user_id, resource_id, etc.)

        Returns:
            Tuple of (encrypted_data, metadata)

        Raises:
            EncryptionError: If encryption fails
        """
        try:
            # Prepare associated data (authenticated but not encrypted)
            associated_data = self._build_associated_data(classification, context)

            # Encrypt
            ciphertext, nonce = self.cipher.encrypt(
                plaintext=data,
                associated_data=associated_data
            )

            # Build metadata for storage
            metadata = {
                'version': '1.0',
                'algorithm': 'AES-256-GCM',
                'key_id': self.cipher.key_id,
                'nonce': base64.b64encode(nonce).decode('utf-8'),
                'salt': base64.b64encode(self.salt).decode('utf-8'),
                'kdf_iterations': self.kdf_iterations,
                'classification': classification.value,
                'encrypted_at': datetime.now(timezone.utc).isoformat(),
                'context': context or {}
            }

            # Log encryption event
            logger.debug(
                f"Data encrypted successfully",
                extra={
                    'key_id': self.cipher.key_id,
                    'classification': classification.value,
                    'data_size': len(data)
                }
            )

            return ciphertext, metadata

        except Exception as e:
            logger.error(f"Data encryption failed: {e}", exc_info=True)
            raise EncryptionError(f"Data encryption failed: {e}")

    def decrypt_data(
        self,
        ciphertext: bytes,
        metadata: Dict[str, Any]
    ) -> bytes:
        """
        Decrypt data using stored metadata.

        Args:
            ciphertext: Encrypted data
            metadata: Encryption metadata (from encrypt_data)

        Returns:
            Decrypted plaintext

        Raises:
            DecryptionError: If decryption fails
        """
        try:
            # Validate metadata
            self._validate_metadata(metadata)

            # Extract nonce
            nonce = base64.b64decode(metadata['nonce'])

            # Rebuild associated data
            classification = DataClassification(metadata['classification'])
            context = metadata.get('context')
            associated_data = self._build_associated_data(classification, context)

            # Decrypt
            plaintext = self.cipher.decrypt(
                ciphertext=ciphertext,
                nonce=nonce,
                associated_data=associated_data
            )

            # Log decryption event
            logger.debug(
                f"Data decrypted successfully",
                extra={
                    'key_id': metadata['key_id'],
                    'classification': classification.value
                }
            )

            return plaintext

        except Exception as e:
            logger.error(f"Data decryption failed: {e}", exc_info=True)
            raise DecryptionError(f"Data decryption failed: {e}")

    def encrypt_string(
        self,
        plaintext: str,
        classification: DataClassification = DataClassification.CONFIDENTIAL,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Encrypt string and return base64-encoded ciphertext.

        Args:
            plaintext: String to encrypt
            classification: Data classification level
            context: Optional context metadata

        Returns:
            Tuple of (base64_ciphertext, metadata)
        """
        plaintext_bytes = plaintext.encode('utf-8')
        ciphertext, metadata = self.encrypt_data(plaintext_bytes, classification, context)
        ciphertext_b64 = base64.b64encode(ciphertext).decode('utf-8')

        return ciphertext_b64, metadata

    def decrypt_string(
        self,
        ciphertext_b64: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Decrypt base64-encoded ciphertext to string.

        Args:
            ciphertext_b64: Base64-encoded ciphertext
            metadata: Encryption metadata

        Returns:
            Decrypted string
        """
        ciphertext = base64.b64decode(ciphertext_b64)
        plaintext_bytes = self.decrypt_data(ciphertext, metadata)
        plaintext = plaintext_bytes.decode('utf-8')

        return plaintext

    def _build_associated_data(
        self,
        classification: DataClassification,
        context: Optional[Dict[str, Any]]
    ) -> bytes:
        """Build associated data for AEAD."""
        aad = {
            'classification': classification.value,
            'context': context or {}
        }

        # Serialize to bytes
        import json
        aad_json = json.dumps(aad, sort_keys=True)
        return aad_json.encode('utf-8')

    def _validate_metadata(self, metadata: Dict[str, Any]) -> None:
        """
        Validate encryption metadata.

        Raises:
            DecryptionError: If metadata is invalid
        """
        required_fields = [
            'version', 'algorithm', 'key_id', 'nonce',
            'salt', 'kdf_iterations', 'classification'
        ]

        for field in required_fields:
            if field not in metadata:
                raise DecryptionError(f"Missing required metadata field: {field}")

        # Validate algorithm
        if metadata['algorithm'] != 'AES-256-GCM':
            raise DecryptionError(f"Unsupported algorithm: {metadata['algorithm']}")

        # Validate key ID
        if metadata['key_id'] != self.cipher.key_id:
            raise DecryptionError(
                f"Key mismatch: expected {self.cipher.key_id}, "
                f"got {metadata['key_id']}"
            )


# ============================================================================
# REDIS ENCRYPTION WRAPPER
# ============================================================================

class EncryptedRedisClient:
    """
    Redis client wrapper with transparent encryption.

    ISO 27001 A.10.1.1 - Automatic encryption of sensitive data
    HIPAA § 164.312(a)(2)(iv) - PHI encryption at rest

    Usage:
        >>> client = EncryptedRedisClient(redis_client, encryption_service)
        >>> client.set_encrypted("user:123:ssn", "123-45-6789", classification=DataClassification.PII)
        >>> value = client.get_decrypted("user:123:ssn")
    """

    def __init__(self, redis_client, encryption_service: EncryptionService):
        """
        Initialize encrypted Redis client.

        Args:
            redis_client: Redis client instance
            encryption_service: Encryption service
        """
        self.redis = redis_client
        self.encryption = encryption_service

        logger.info("Encrypted Redis client initialized")

    def set_encrypted(
        self,
        key: str,
        value: str,
        classification: DataClassification = DataClassification.CONFIDENTIAL,
        ttl: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Set encrypted value in Redis.

        Args:
            key: Redis key
            value: Plaintext value to encrypt
            classification: Data classification level
            ttl: Optional TTL in seconds
            context: Optional context metadata

        Returns:
            True if successful
        """
        try:
            # Encrypt value
            ciphertext_b64, metadata = self.encryption.encrypt_string(
                plaintext=value,
                classification=classification,
                context=context
            )

            # Store encrypted data and metadata
            import json
            encrypted_package = {
                'ciphertext': ciphertext_b64,
                'metadata': metadata
            }

            encrypted_json = json.dumps(encrypted_package)

            # Store in Redis
            if ttl:
                self.redis.setex(key, ttl, encrypted_json)
            else:
                self.redis.set(key, encrypted_json)

            logger.debug(
                f"Encrypted value stored in Redis",
                extra={
                    'key': key,
                    'classification': classification.value,
                    'ttl': ttl
                }
            )

            return True

        except Exception as e:
            logger.error(f"Failed to store encrypted value: {e}", exc_info=True)
            return False

    def get_decrypted(self, key: str) -> Optional[str]:
        """
        Get and decrypt value from Redis.

        Args:
            key: Redis key

        Returns:
            Decrypted value or None if key doesn't exist

        Raises:
            DecryptionError: If decryption fails
        """
        try:
            # Get encrypted package from Redis
            encrypted_json = self.redis.get(key)

            if encrypted_json is None:
                return None

            # Parse package
            import json
            encrypted_package = json.loads(encrypted_json)

            ciphertext_b64 = encrypted_package['ciphertext']
            metadata = encrypted_package['metadata']

            # Decrypt
            plaintext = self.encryption.decrypt_string(ciphertext_b64, metadata)

            logger.debug(
                f"Decrypted value retrieved from Redis",
                extra={'key': key}
            )

            return plaintext

        except Exception as e:
            logger.error(f"Failed to decrypt value: {e}", exc_info=True)
            raise DecryptionError(f"Failed to decrypt value: {e}")

    def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        result = self.redis.delete(key)
        return bool(result)

    def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        return bool(self.redis.exists(key))


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def create_encryption_service(
    master_key: Optional[str] = None,
    kdf_iterations: Optional[int] = None
) -> EncryptionService:
    """
    Create encryption service from environment configuration.

    Args:
        master_key: Optional master key (defaults to ENCRYPTION_MASTER_KEY env var)
        kdf_iterations: Optional KDF iterations (defaults to KDF_ITERATIONS env var)

    Returns:
        EncryptionService instance

    Raises:
        ValueError: If master key is not configured
    """
    from app.core.config import get_settings

    settings = get_settings()

    # Get master key
    if master_key is None:
        master_key = os.getenv('ENCRYPTION_MASTER_KEY', '')
        if not master_key:
            raise ValueError(
                "ENCRYPTION_MASTER_KEY not configured. "
                "Set in environment or pass as argument."
            )

    # Get KDF iterations
    if kdf_iterations is None:
        kdf_iterations = getattr(settings, 'KDF_ITERATIONS', KeyDerivation.DEFAULT_ITERATIONS)

    return EncryptionService(
        master_key=master_key,
        kdf_iterations=kdf_iterations
    )


def create_encrypted_redis_client(redis_client) -> EncryptedRedisClient:
    """
    Create encrypted Redis client.

    Args:
        redis_client: Redis client instance

    Returns:
        EncryptedRedisClient instance
    """
    encryption_service = create_encryption_service()

    return EncryptedRedisClient(
        redis_client=redis_client,
        encryption_service=encryption_service
    )
