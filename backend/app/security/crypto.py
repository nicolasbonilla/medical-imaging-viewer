"""
Cryptographic services for data protection.

Implements ISO 27001 A.10.1.1 (Cryptographic policy) and
A.10.1.2 (Key management).

Provides AES-256-GCM encryption for data at rest and secure key management.

@module security.crypto
"""

import os
import base64
from typing import Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from app.core.logging import get_logger

logger = get_logger(__name__)


class EncryptionConfig:
    """
    Encryption configuration constants (ISO 27001 A.10.1.1).

    Following OWASP and NIST recommendations for 2025.
    """
    # AES-256-GCM (Authenticated Encryption with Associated Data)
    ALGORITHM = "AES-256-GCM"
    KEY_SIZE = 32  # 256 bits
    NONCE_SIZE = 12  # 96 bits (NIST recommendation for GCM)
    TAG_SIZE = 16  # 128 bits authentication tag
    SALT_SIZE = 16  # 128 bits for key derivation

    # PBKDF2 for key derivation
    KDF_ITERATIONS = 100_000  # OWASP recommendation 2025
    KDF_ALGORITHM = hashes.SHA256()

    # Key rotation policy
    KEY_ROTATION_DAYS = 90

    @classmethod
    def get_config_summary(cls) -> dict:
        """Get encryption configuration summary for audit."""
        return {
            "algorithm": cls.ALGORITHM,
            "key_size_bits": cls.KEY_SIZE * 8,
            "nonce_size_bits": cls.NONCE_SIZE * 8,
            "tag_size_bits": cls.TAG_SIZE * 8,
            "kdf_iterations": cls.KDF_ITERATIONS,
            "kdf_algorithm": "SHA256",
            "key_rotation_days": cls.KEY_ROTATION_DAYS,
        }


class KeyManager:
    """
    Secure key management with rotation support (ISO 27001 A.10.1.2).

    Features:
    - Secure key generation using OS CSPRNG
    - Key storage with restrictive file permissions (0600)
    - Key rotation with grace period
    - Multiple key versions support
    - Key metadata tracking

    Example:
        >>> km = KeyManager(key_dir=Path("keys"))
        >>> km.generate_key("app-encryption")
        >>> key = km.get_current_key("app-encryption")
        >>> len(key)
        32
    """

    def __init__(self, key_dir: Path):
        """
        Initialize key manager.

        Args:
            key_dir: Directory for key storage
        """
        self.key_dir = Path(key_dir)
        self.key_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        logger.info(
            "KeyManager initialized",
            extra={"key_dir": str(self.key_dir)}
        )

    def generate_key(self, key_name: str) -> bytes:
        """
        Generate a new encryption key.

        Uses OS CSPRNG for cryptographically secure random generation.

        Args:
            key_name: Name/identifier for the key

        Returns:
            Generated key (32 bytes)

        Example:
            >>> km = KeyManager(Path("keys"))
            >>> key = km.generate_key("test-key")
            >>> len(key)
            32
        """
        # Generate cryptographically secure random key
        key = os.urandom(EncryptionConfig.KEY_SIZE)

        # Store key with metadata
        self._store_key(key_name, key)

        logger.info(
            "Encryption key generated",
            extra={
                "key_name": key_name,
                "key_size": len(key),
            }
        )

        return key

    def _store_key(self, key_name: str, key: bytes, version: int = 1) -> None:
        """
        Store encryption key securely.

        Args:
            key_name: Key identifier
            key: Key bytes
            version: Key version number
        """
        key_file = self.key_dir / f"{key_name}.v{version}.key"
        metadata_file = self.key_dir / f"{key_name}.v{version}.meta"

        # Create key file with restrictive permissions (owner read/write only)
        key_file.touch(mode=0o600)
        with open(key_file, 'wb') as f:
            f.write(key)

        # Store metadata
        metadata = {
            "key_name": key_name,
            "version": version,
            "created_at": datetime.utcnow().isoformat(),
            "algorithm": EncryptionConfig.ALGORITHM,
            "key_size": len(key),
        }

        metadata_file.touch(mode=0o600)
        with open(metadata_file, 'w') as f:
            import json
            json.dump(metadata, f, indent=2)

        logger.debug(
            "Key stored securely",
            extra={"key_file": str(key_file)}
        )

    def get_current_key(self, key_name: str) -> bytes:
        """
        Get the current (latest) encryption key.

        Args:
            key_name: Key identifier

        Returns:
            Current key bytes

        Raises:
            FileNotFoundError: If no key exists
        """
        # Find latest version
        key_files = list(self.key_dir.glob(f"{key_name}.v*.key"))

        if not key_files:
            raise FileNotFoundError(f"No key found for {key_name}")

        # Get latest version
        latest_key_file = sorted(key_files)[-1]

        with open(latest_key_file, 'rb') as f:
            key = f.read()

        return key

    def rotate_key(self, key_name: str) -> bytes:
        """
        Rotate encryption key (ISO 27001 A.10.1.2 - Key rotation).

        Creates a new version of the key while keeping old versions
        for decryption of existing data.

        Args:
            key_name: Key identifier

        Returns:
            New key bytes

        Example:
            >>> km = KeyManager(Path("keys"))
            >>> km.generate_key("test-key")
            >>> new_key = km.rotate_key("test-key")
        """
        # Get current version
        key_files = list(self.key_dir.glob(f"{key_name}.v*.key"))
        current_version = len(key_files)
        new_version = current_version + 1

        # Generate new key
        new_key = os.urandom(EncryptionConfig.KEY_SIZE)
        self._store_key(key_name, new_key, version=new_version)

        logger.info(
            "Key rotated",
            extra={
                "key_name": key_name,
                "old_version": current_version,
                "new_version": new_version,
            }
        )

        return new_key

    def get_key_version(self, key_name: str, version: int) -> bytes:
        """
        Get specific version of a key.

        Useful for decrypting data encrypted with older key versions.

        Args:
            key_name: Key identifier
            version: Key version number

        Returns:
            Key bytes for specified version

        Raises:
            FileNotFoundError: If key version doesn't exist
        """
        key_file = self.key_dir / f"{key_name}.v{version}.key"

        if not key_file.exists():
            raise FileNotFoundError(f"Key version {version} not found for {key_name}")

        with open(key_file, 'rb') as f:
            return f.read()


class CryptoService:
    """
    Cryptographic service for data encryption/decryption.

    Uses AES-256-GCM (Authenticated Encryption with Associated Data).

    Features:
    - Encryption with authentication (prevents tampering)
    - Random nonce per encryption (prevents pattern analysis)
    - Associated data support (additional authenticated context)
    - Key derivation from passwords (for user-specific encryption)

    ISO 27001 Controls:
    - A.10.1.1: Cryptographic controls for data protection
    - A.10.1.2: Key management

    Example:
        >>> crypto = CryptoService()
        >>> key = crypto.generate_key()
        >>> encrypted = crypto.encrypt(b"secret data", key)
        >>> decrypted = crypto.decrypt(encrypted, key)
        >>> decrypted
        b'secret data'
    """

    def __init__(self):
        """Initialize crypto service."""
        logger.info(
            "CryptoService initialized",
            extra=EncryptionConfig.get_config_summary()
        )

    @staticmethod
    def generate_key() -> bytes:
        """
        Generate a new encryption key.

        Returns:
            32-byte encryption key

        Example:
            >>> key = CryptoService.generate_key()
            >>> len(key)
            32
        """
        return os.urandom(EncryptionConfig.KEY_SIZE)

    @staticmethod
    def encrypt(
        data: bytes,
        key: bytes,
        associated_data: Optional[bytes] = None
    ) -> bytes:
        """
        Encrypt data using AES-256-GCM.

        Args:
            data: Plain data to encrypt
            key: 32-byte encryption key
            associated_data: Optional additional authenticated data

        Returns:
            Encrypted data (nonce + ciphertext + tag)

        Example:
            >>> crypto = CryptoService()
            >>> key = crypto.generate_key()
            >>> encrypted = crypto.encrypt(b"secret", key)
            >>> len(encrypted) > len(b"secret")
            True

        ISO 27001: A.10.1.1 (Data encryption)
        """
        if len(key) != EncryptionConfig.KEY_SIZE:
            raise ValueError(f"Key must be {EncryptionConfig.KEY_SIZE} bytes")

        # Generate random nonce (MUST be unique for each encryption)
        nonce = os.urandom(EncryptionConfig.NONCE_SIZE)

        # Initialize AESGCM cipher
        cipher = AESGCM(key)

        # Encrypt and authenticate
        ciphertext = cipher.encrypt(nonce, data, associated_data)

        # Return nonce + ciphertext (ciphertext includes auth tag)
        encrypted = nonce + ciphertext

        logger.debug(
            "Data encrypted",
            extra={
                "data_size": len(data),
                "encrypted_size": len(encrypted),
                "has_aad": associated_data is not None,
            }
        )

        return encrypted

    @staticmethod
    def decrypt(
        encrypted_data: bytes,
        key: bytes,
        associated_data: Optional[bytes] = None
    ) -> bytes:
        """
        Decrypt data encrypted with AES-256-GCM.

        Args:
            encrypted_data: Encrypted data (nonce + ciphertext + tag)
            key: 32-byte encryption key
            associated_data: Optional additional authenticated data (must match encryption)

        Returns:
            Decrypted plain data

        Raises:
            cryptography.exceptions.InvalidTag: If data has been tampered with

        Example:
            >>> crypto = CryptoService()
            >>> key = crypto.generate_key()
            >>> encrypted = crypto.encrypt(b"secret", key)
            >>> decrypted = crypto.decrypt(encrypted, key)
            >>> decrypted
            b'secret'

        ISO 27001: A.10.1.1 (Data decryption with authentication)
        """
        if len(key) != EncryptionConfig.KEY_SIZE:
            raise ValueError(f"Key must be {EncryptionConfig.KEY_SIZE} bytes")

        # Extract nonce and ciphertext
        nonce = encrypted_data[:EncryptionConfig.NONCE_SIZE]
        ciphertext = encrypted_data[EncryptionConfig.NONCE_SIZE:]

        # Initialize AESGCM cipher
        cipher = AESGCM(key)

        try:
            # Decrypt and verify authentication tag
            plaintext = cipher.decrypt(nonce, ciphertext, associated_data)

            logger.debug(
                "Data decrypted successfully",
                extra={"plaintext_size": len(plaintext)}
            )

            return plaintext

        except Exception as e:
            logger.error(
                "Decryption failed",
                extra={"error": str(e)},
                exc_info=True
            )
            raise

    @staticmethod
    def encrypt_text(text: str, key: bytes) -> str:
        """
        Encrypt text and return base64-encoded result.

        Convenience method for text encryption.

        Args:
            text: Plain text to encrypt
            key: 32-byte encryption key

        Returns:
            Base64-encoded encrypted data

        Example:
            >>> crypto = CryptoService()
            >>> key = crypto.generate_key()
            >>> encrypted = crypto.encrypt_text("Hello World", key)
            >>> encrypted.startswith("b'")
            False
        """
        data = text.encode('utf-8')
        encrypted = CryptoService.encrypt(data, key)
        return base64.b64encode(encrypted).decode('ascii')

    @staticmethod
    def decrypt_text(encrypted_text: str, key: bytes) -> str:
        """
        Decrypt base64-encoded text.

        Args:
            encrypted_text: Base64-encoded encrypted data
            key: 32-byte encryption key

        Returns:
            Decrypted plain text

        Example:
            >>> crypto = CryptoService()
            >>> key = crypto.generate_key()
            >>> encrypted = crypto.encrypt_text("Hello World", key)
            >>> decrypted = crypto.decrypt_text(encrypted, key)
            >>> decrypted
            'Hello World'
        """
        encrypted = base64.b64decode(encrypted_text.encode('ascii'))
        decrypted = CryptoService.decrypt(encrypted, key)
        return decrypted.decode('utf-8')

    @staticmethod
    def derive_key_from_password(
        password: str,
        salt: Optional[bytes] = None
    ) -> Tuple[bytes, bytes]:
        """
        Derive encryption key from password using PBKDF2.

        Useful for user-specific encryption where key is derived from password.

        Args:
            password: User password
            salt: Optional salt (generated if not provided)

        Returns:
            Tuple of (derived_key, salt)

        Example:
            >>> crypto = CryptoService()
            >>> key, salt = crypto.derive_key_from_password("user_password")
            >>> len(key)
            32
            >>> len(salt)
            16

        ISO 27001: A.10.1.2 (Key derivation)
        """
        if salt is None:
            salt = os.urandom(EncryptionConfig.SALT_SIZE)

        kdf = PBKDF2HMAC(
            algorithm=EncryptionConfig.KDF_ALGORITHM,
            length=EncryptionConfig.KEY_SIZE,
            salt=salt,
            iterations=EncryptionConfig.KDF_ITERATIONS,
        )

        key = kdf.derive(password.encode('utf-8'))

        logger.debug(
            "Key derived from password",
            extra={
                "iterations": EncryptionConfig.KDF_ITERATIONS,
                "key_size": len(key),
            }
        )

        return key, salt

    @staticmethod
    def encrypt_with_password(data: bytes, password: str) -> bytes:
        """
        Encrypt data using password-derived key.

        Args:
            data: Plain data to encrypt
            password: Password for key derivation

        Returns:
            Encrypted data (salt + nonce + ciphertext + tag)

        Example:
            >>> crypto = CryptoService()
            >>> encrypted = crypto.encrypt_with_password(b"secret", "password123")
            >>> decrypted = crypto.decrypt_with_password(encrypted, "password123")
            >>> decrypted
            b'secret'
        """
        # Derive key from password
        key, salt = CryptoService.derive_key_from_password(password)

        # Encrypt data
        encrypted = CryptoService.encrypt(data, key)

        # Prepend salt to encrypted data
        return salt + encrypted

    @staticmethod
    def decrypt_with_password(encrypted_data: bytes, password: str) -> bytes:
        """
        Decrypt data using password-derived key.

        Args:
            encrypted_data: Encrypted data (salt + nonce + ciphertext + tag)
            password: Password for key derivation

        Returns:
            Decrypted plain data

        Raises:
            cryptography.exceptions.InvalidTag: If password is incorrect or data tampered
        """
        # Extract salt
        salt = encrypted_data[:EncryptionConfig.SALT_SIZE]
        encrypted = encrypted_data[EncryptionConfig.SALT_SIZE:]

        # Derive key from password and salt
        key, _ = CryptoService.derive_key_from_password(password, salt)

        # Decrypt data
        return CryptoService.decrypt(encrypted, key)


# Singleton instances
_key_manager: Optional[KeyManager] = None
_crypto_service: Optional[CryptoService] = None


def get_key_manager(key_dir: Optional[Path] = None) -> KeyManager:
    """
    Get singleton KeyManager instance.

    Args:
        key_dir: Key storage directory (only used on first call)

    Returns:
        KeyManager instance
    """
    global _key_manager

    if _key_manager is None:
        if key_dir is None:
            key_dir = Path("keys")
        _key_manager = KeyManager(key_dir)

    return _key_manager


def get_crypto_service() -> CryptoService:
    """
    Get singleton CryptoService instance.

    Returns:
        CryptoService instance
    """
    global _crypto_service

    if _crypto_service is None:
        _crypto_service = CryptoService()

    return _crypto_service
