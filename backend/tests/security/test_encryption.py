"""
Encryption and Cryptography Security Tests
Medical Imaging Viewer - Data-at-Rest Encryption Testing Suite

ISO 27001 A.10.1.1 - Policy on the use of cryptographic controls
ISO 27001 A.10.1.2 - Key management
ISO 27001 A.18.1.5 - Regulation of cryptographic controls

HIPAA Security Rule:
- 164.312(a)(2)(iv) - Encryption and decryption
- 164.312(e)(2)(ii) - Encryption

NIST SP 800-53:
- SC-13: Cryptographic Protection
- SC-28: Protection of Information at Rest

This module tests:
1. AES-256-GCM encryption/decryption
2. Key derivation with PBKDF2
3. Data classification enforcement
4. Encrypted Redis client
5. Cryptographic key management
6. HIPAA PHI encryption compliance
7. Property-based testing for cryptographic operations

@module tests.security.test_encryption
@version 2.1.0 - Aligned to current encryption module API
"""

import os
import json

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from app.core.security.encryption import (
    AESGCMEncryption,
    EncryptionService,
    KeyDerivation,
    DataClassification,
    EncryptionError,
    DecryptionError,
    KeyDerivationError,
)


# =============================================================================
# TEST HELPERS / LOCAL FIXTURES
#
# The current AESGCMEncryption takes a 32-byte key in its constructor (there is
# no `generate_key()` classmethod), and EncryptionService is built from a
# master-key *string*. These helpers construct objects against that current API.
# =============================================================================

# A stable, non-production master key for the high-level EncryptionService.
TEST_MASTER_KEY = "unit-test-master-key-do-not-use-in-production-1234567890"


def _make_key() -> bytes:
    """Generate a fresh, cryptographically-random 256-bit (32-byte) AES key."""
    return os.urandom(AESGCMEncryption.KEY_SIZE)


# NOTE: the four authentication-failure tests below (tamper/wrong-key/wrong-AAD =>
# DecryptionError) were previously xfail-pinned to a production defect this adversarial
# repair SURFACED: AESGCMEncryption.decrypt()'s InvalidTag handler logged a non-existent
# AuditEventType.SECURITY_DATA_INTEGRITY_VIOLATION, raising AttributeError instead of the
# intended DecryptionError. That enum member has since been added
# (app/core/logging/audit.py), restoring the correct contract, so the tests now assert it
# directly (no xfail).


@pytest.fixture
def encryption_service() -> EncryptionService:
    """
    High-level encryption service for tests.

    Shadows the conftest fixture of the same name, which accessed
    ``settings.ENCRYPTION_MASTER_KEY``. That key is defined on
    ``SecuritySettings`` (populated from the environment), NOT on the top-level
    ``Settings`` object, so the stale access raised
    ``AttributeError: 'Settings' object has no attribute 'ENCRYPTION_MASTER_KEY'``.
    We build the service directly from a fixed test master key instead.
    """
    return EncryptionService(master_key=TEST_MASTER_KEY)


# =============================================================================
# AES-256-GCM ENCRYPTION TESTS
# ISO 27001 A.10.1.1 - Cryptographic controls
# NIST SP 800-53 SC-13 - Cryptographic Protection
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
class TestAESGCMEncryption:
    """Test AES-256-GCM encryption and decryption."""

    def test_encrypt_decrypt_round_trip(self):
        """Test basic encryption/decryption round trip."""
        aes_gcm = AESGCMEncryption(_make_key())

        plaintext = b"Sensitive patient data"

        # Encrypt (current API returns ciphertext-with-tag and the nonce)
        ciphertext, nonce = aes_gcm.encrypt(plaintext)

        # Decrypt
        decrypted = aes_gcm.decrypt(ciphertext, nonce)

        assert decrypted == plaintext

    def test_key_size_enforced_256_bits(self):
        """Test that the cipher requires a 256-bit (32-byte) key for AES-256."""
        # AES-256 requires a 32-byte key.
        assert AESGCMEncryption.KEY_SIZE == 32

        # A correctly sized key is accepted.
        AESGCMEncryption(os.urandom(32))

        # Any other key size must be rejected (weak/invalid keys are refused).
        for bad_len in (0, 15, 16, 24, 31, 33, 64):
            with pytest.raises(ValueError):
                AESGCMEncryption(os.urandom(bad_len))

    def test_generate_key_randomness(self):
        """Test that generated keys are unique (cryptographically random)."""
        key1 = _make_key()
        key2 = _make_key()

        # Keys should be different and full-length.
        assert key1 != key2
        assert len(key1) == 32
        assert len(key2) == 32

    def test_nonce_uniqueness(self):
        """Test that nonces are unique for each encryption."""
        aes_gcm = AESGCMEncryption(_make_key())
        plaintext = b"Test data"

        # Encrypt twice with same key and plaintext
        ciphertext1, nonce1 = aes_gcm.encrypt(plaintext)
        ciphertext2, nonce2 = aes_gcm.encrypt(plaintext)

        # Nonces must be different (critical for GCM security)
        assert nonce1 != nonce2

        # Ciphertexts should also differ due to different nonces
        assert ciphertext1 != ciphertext2

    def test_nonce_length(self):
        """Test that nonces are 96 bits (12 bytes) - recommended for GCM."""
        aes_gcm = AESGCMEncryption(_make_key())
        plaintext = b"Test data"

        _, nonce = aes_gcm.encrypt(plaintext)

        # GCM standard recommends 96-bit (12-byte) nonces
        assert len(nonce) == 12
        assert AESGCMEncryption.NONCE_SIZE == 12

    def test_authentication_tag_length(self):
        """Test that the 128-bit (16-byte) GCM authentication tag is present."""
        aes_gcm = AESGCMEncryption(_make_key())
        plaintext = b"Test data"

        ciphertext, _ = aes_gcm.encrypt(plaintext)

        # AESGCM appends the 128-bit (16-byte) auth tag to the ciphertext.
        assert AESGCMEncryption.TAG_SIZE == 16
        assert len(ciphertext) == len(plaintext) + AESGCMEncryption.TAG_SIZE

    def test_decryption_with_wrong_key(self):
        """Test that decryption fails with wrong key."""
        plaintext = b"Sensitive data"

        aes_correct = AESGCMEncryption(_make_key())
        aes_wrong = AESGCMEncryption(_make_key())

        ciphertext, nonce = aes_correct.encrypt(plaintext)

        # Decryption with wrong key should raise exception
        with pytest.raises(DecryptionError):
            aes_wrong.decrypt(ciphertext, nonce)

    def test_decryption_with_tampered_ciphertext(self):
        """Test that decryption detects tampered ciphertext (authentication)."""
        aes_gcm = AESGCMEncryption(_make_key())
        plaintext = b"Sensitive data"

        ciphertext, nonce = aes_gcm.encrypt(plaintext)

        # Tamper with the ciphertext body (flip the first byte).
        tampered_ciphertext = bytes([ciphertext[0] ^ 0xFF]) + ciphertext[1:]

        # Decryption should fail due to authentication tag mismatch
        with pytest.raises(DecryptionError):
            aes_gcm.decrypt(tampered_ciphertext, nonce)

    def test_decryption_with_tampered_tag(self):
        """Test that decryption detects a tampered authentication tag."""
        aes_gcm = AESGCMEncryption(_make_key())
        plaintext = b"Sensitive data"

        ciphertext, nonce = aes_gcm.encrypt(plaintext)

        # The 128-bit GCM auth tag is the trailing 16 bytes of the ciphertext.
        tag_start = len(ciphertext) - AESGCMEncryption.TAG_SIZE
        tampered = ciphertext[:tag_start] + bytes(
            b ^ 0xFF for b in ciphertext[tag_start:]
        )

        # Decryption should fail
        with pytest.raises(DecryptionError):
            aes_gcm.decrypt(tampered, nonce)

    def test_decryption_with_wrong_associated_data(self):
        """Test that AEAD binds associated data (AAD tamper is detected)."""
        aes_gcm = AESGCMEncryption(_make_key())
        plaintext = b"Sensitive data"

        ciphertext, nonce = aes_gcm.encrypt(plaintext, associated_data=b"ctx:patient-1")

        # Correct AAD decrypts.
        assert aes_gcm.decrypt(ciphertext, nonce, associated_data=b"ctx:patient-1") == plaintext

        # Wrong / missing AAD must fail authentication.
        with pytest.raises(DecryptionError):
            aes_gcm.decrypt(ciphertext, nonce, associated_data=b"ctx:patient-2")
        with pytest.raises(DecryptionError):
            aes_gcm.decrypt(ciphertext, nonce)

    def test_encrypt_empty_data(self):
        """Test encryption of empty data."""
        aes_gcm = AESGCMEncryption(_make_key())
        plaintext = b""

        ciphertext, nonce = aes_gcm.encrypt(plaintext)

        # Should produce valid ciphertext (auth tag only) and round-trip.
        decrypted = aes_gcm.decrypt(ciphertext, nonce)
        assert decrypted == plaintext

    def test_encrypt_large_data(self):
        """Test encryption of large data (1 MB)."""
        aes_gcm = AESGCMEncryption(_make_key())
        plaintext = b"X" * (1024 * 1024)  # 1 MB

        ciphertext, nonce = aes_gcm.encrypt(plaintext)
        decrypted = aes_gcm.decrypt(ciphertext, nonce)

        assert decrypted == plaintext


# =============================================================================
# KEY DERIVATION TESTS
# ISO 27001 A.10.1.2 - Key management
#
# Current API: KeyDerivation.derive_key(master_key: str, salt: bytes, ...) is a
# staticmethod. The master key is a string (PBKDF2 password); the salt is bytes
# and required.
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
class TestKeyDerivation:
    """Test key derivation with PBKDF2."""

    def test_derive_key_from_master_key(self):
        """Test key derivation from master key."""
        master_key = "master-secret-key-32-bytes-long!"
        salt = b"fixed-salt-16byt"  # 16 bytes

        derived_key = KeyDerivation.derive_key(master_key, salt)

        # Should return 32-byte key
        assert len(derived_key) == 32
        assert isinstance(derived_key, bytes)

    def test_derive_key_deterministic(self):
        """Test that key derivation is deterministic for same inputs."""
        master_key = "master-secret-key-32-bytes-long!"
        salt = b"fixed-salt-16byt"

        key1 = KeyDerivation.derive_key(master_key, salt)
        key2 = KeyDerivation.derive_key(master_key, salt)

        # Should produce identical keys
        assert key1 == key2

    def test_derive_different_keys_for_different_salts(self):
        """
        Test domain separation: different salts produce different keys.

        (The legacy API separated keys by a ``context`` string; the current API
        achieves the same domain-separation security property via distinct
        per-domain salts.)
        """
        master_key = "master-secret-key-32-bytes-long!"

        key_patients = KeyDerivation.derive_key(master_key, b"salt::patients01")
        key_studies = KeyDerivation.derive_key(master_key, b"salt::studies-01")

        # Should produce different keys
        assert key_patients != key_studies

    def test_derive_key_with_salt(self):
        """Test key derivation with custom salt."""
        master_key = "master-secret-key-32-bytes-long!"

        salt1 = b"salt1-16-bytes!!"
        salt2 = b"salt2-16-bytes!!"

        key1 = KeyDerivation.derive_key(master_key, salt=salt1)
        key2 = KeyDerivation.derive_key(master_key, salt=salt2)

        # Different salts should produce different keys
        assert key1 != key2

    def test_derive_key_invalid_salt_raises(self):
        """
        Test that invalid derivation input is surfaced as KeyDerivationError.

        (Replaces the stale ``test_derive_key_invalid_master_key``: the current
        derive_key treats the master key as an arbitrary-length PBKDF2 password
        per NIST SP 800-132 and performs no length rejection. The wrapped
        KeyDerivationError path is instead exercised with an invalid salt type.
        Actual AES key-size enforcement is covered in TestAESGCMEncryption.)
        """
        with pytest.raises(KeyDerivationError):
            KeyDerivation.derive_key("master-secret-key-32-bytes-long!", salt="not-bytes")


# =============================================================================
# ENCRYPTION SERVICE TESTS
# High-level encryption service with data classification
#
# Current API: encrypt_string/decrypt_string (str) and encrypt_data/decrypt_data
# (bytes) each return / consume a (ciphertext, metadata) pair.
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
class TestEncryptionService:
    """Test high-level encryption service."""

    def test_encrypt_decrypt_with_classification(self, encryption_service: EncryptionService):
        """Test encryption with data classification."""
        plaintext = "Patient SSN: 123-45-6789"

        # Encrypt with PHI classification (highest security tier)
        ciphertext, metadata = encryption_service.encrypt_string(
            plaintext,
            classification=DataClassification.PHI
        )

        # Decrypt
        decrypted = encryption_service.decrypt_string(ciphertext, metadata)

        assert decrypted == plaintext

    def test_encrypt_phi_data(self, encryption_service: EncryptionService, sample_phi_data: dict):
        """Test encryption of Protected Health Information (PHI)."""
        phi_json = json.dumps(sample_phi_data)

        # Encrypt PHI
        ciphertext, metadata = encryption_service.encrypt_string(
            phi_json,
            classification=DataClassification.PHI
        )

        # Encrypted data should be different from plaintext
        assert ciphertext != phi_json

        # Decrypt and verify
        decrypted = encryption_service.decrypt_string(ciphertext, metadata)
        decrypted_data = json.loads(decrypted)

        assert decrypted_data == sample_phi_data

    def test_encrypt_with_different_classifications(self, encryption_service: EncryptionService):
        """Test encryption with every data classification."""
        data = "Test data"

        classifications = [
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
            DataClassification.CONFIDENTIAL,
            DataClassification.PHI,
            DataClassification.PII,
        ]

        for classification in classifications:
            ciphertext, metadata = encryption_service.encrypt_string(
                data, classification=classification
            )
            decrypted = encryption_service.decrypt_string(ciphertext, metadata)

            assert decrypted == data
            # The classification is bound into the metadata (and the AEAD AAD).
            assert metadata["classification"] == classification.value

    def test_encrypted_data_format(self, encryption_service: EncryptionService):
        """Test that encrypted output carries all required components."""
        plaintext = "Test data"

        ciphertext, metadata = encryption_service.encrypt_string(
            plaintext, classification=DataClassification.CONFIDENTIAL
        )

        # Ciphertext is a base64 string; metadata is a dict.
        assert isinstance(ciphertext, str)
        assert isinstance(metadata, dict)

        # Metadata must contain every field needed to decrypt + audit.
        for field in (
            "version", "algorithm", "key_id", "nonce",
            "salt", "kdf_iterations", "classification",
        ):
            assert field in metadata

        assert metadata["algorithm"] == "AES-256-GCM"
        assert metadata["classification"] == DataClassification.CONFIDENTIAL.value

    def test_decrypt_with_wrong_key(self):
        """Test that decryption fails with wrong master key."""
        service1 = EncryptionService(master_key="key1" + "x" * 27)
        service2 = EncryptionService(master_key="key2" + "x" * 27)

        plaintext = "Test data"
        ciphertext, metadata = service1.encrypt_string(
            plaintext, classification=DataClassification.CONFIDENTIAL
        )

        # Decryption with a different service (different derived key) must fail.
        with pytest.raises(DecryptionError):
            service2.decrypt_string(ciphertext, metadata)

    def test_encrypt_unicode_data(self, encryption_service: EncryptionService):
        """Test encryption of Unicode data."""
        unicode_data = "Patient名前: John™中文🔒"

        ciphertext, metadata = encryption_service.encrypt_string(
            unicode_data, classification=DataClassification.CONFIDENTIAL
        )
        decrypted = encryption_service.decrypt_string(ciphertext, metadata)

        assert decrypted == unicode_data

    def test_encrypt_binary_data(self, encryption_service: EncryptionService):
        """Test encryption of binary data (e.g., DICOM files)."""
        # Simulate DICOM file header
        binary_data = b"\x00" * 128 + b"DICM" + b"\x00" * 100

        ciphertext, metadata = encryption_service.encrypt_data(
            binary_data,
            classification=DataClassification.PHI
        )
        decrypted = encryption_service.decrypt_data(ciphertext, metadata)

        assert decrypted == binary_data


# =============================================================================
# ENCRYPTED REDIS CLIENT TESTS
# ISO 27001 A.10.1.2 - Key management for cached data
# =============================================================================

class _FakeRedis:
    """Minimal in-memory Redis stand-in for exercising the encryption layer."""

    def __init__(self):
        self._store = {}

    def set(self, key, value):
        self._store[key] = value
        return True

    def setex(self, key, ttl, value):
        self._store[key] = value
        return True

    def get(self, key):
        return self._store.get(key)

    def delete(self, key):
        return 1 if self._store.pop(key, None) is not None else 0

    def exists(self, key):
        return 1 if key in self._store else 0


@pytest.mark.security
@pytest.mark.encryption
@pytest.mark.asyncio
class TestEncryptedRedisClient:
    """Test encrypted Redis client for secure caching."""

    async def test_set_get_encrypted_value(self, encryption_service: EncryptionService):
        """Test setting and getting encrypted values via the encrypted client."""
        from app.core.security.encryption import EncryptedRedisClient

        fake_redis = _FakeRedis()
        client = EncryptedRedisClient(
            redis_client=fake_redis,
            encryption_service=encryption_service,
        )

        key = "patient:12345:data"
        value = json.dumps({"ssn": "123-45-6789", "diagnosis": "Diabetes"})

        # Store encrypted.
        assert client.set_encrypted(
            key, value, classification=DataClassification.PHI
        ) is True

        # What actually lands in Redis must be ciphertext, never plaintext PHI.
        stored = fake_redis.get(key)
        assert stored is not None
        assert "123-45-6789" not in stored
        assert "Diabetes" not in stored

        # Round-trip through decryption returns the original value.
        decrypted = client.get_decrypted(key)
        assert decrypted == value


# =============================================================================
# DATA CLASSIFICATION TESTS
# ISO 27001 A.8.2.1 - Classification of information
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
class TestDataClassification:
    """Test data classification enforcement."""

    def test_data_classification_levels(self):
        """Test that all expected data classification levels exist and are distinct."""
        levels = [
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
            DataClassification.CONFIDENTIAL,
            DataClassification.PHI,
            DataClassification.PII,
        ]

        # Exactly five, all distinct.
        assert len(levels) == 5
        assert len(set(levels)) == 5

        # The enum exposes precisely these members (no more, no fewer).
        assert set(DataClassification) == set(levels)

        # Values are the canonical lowercase string tags used in metadata/AAD.
        assert DataClassification.PHI.value == "phi"


# =============================================================================
# HIPAA COMPLIANCE TESTS
# HIPAA Security Rule 164.312(a)(2)(iv)
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
@pytest.mark.compliance
class TestHIPAACompliance:
    """Test HIPAA encryption compliance."""

    def test_phi_encryption_required_fields(
        self,
        encryption_service: EncryptionService,
        sample_phi_data: dict
    ):
        """Test that all PHI fields are encrypted."""
        # All PHI fields must be encrypted
        phi_fields = [
            "patient_id",
            "first_name",
            "last_name",
            "date_of_birth",
            "ssn",
            "phone",
            "email",
            "address",
        ]

        for field in phi_fields:
            value = str(sample_phi_data.get(field, ""))

            # Encrypt field
            ciphertext, metadata = encryption_service.encrypt_string(
                value,
                classification=DataClassification.PHI
            )

            # Verify encrypted (ciphertext differs from plaintext)
            assert ciphertext != value
            assert value not in ciphertext

            # Verify can be decrypted
            decrypted = encryption_service.decrypt_string(ciphertext, metadata)
            assert decrypted == value

    def test_phi_encryption_algorithm_strength(self, encryption_service: EncryptionService):
        """Test that PHI is encrypted with AES-256-GCM (HIPAA recommended)."""
        phi = "SSN: 123-45-6789"

        ciphertext, metadata = encryption_service.encrypt_string(
            phi,
            classification=DataClassification.PHI
        )

        # Verify metadata indicates strong, versioned encryption.
        assert metadata["version"] == "1.0"
        assert metadata["classification"] == DataClassification.PHI.value
        assert metadata["algorithm"] == "AES-256-GCM"

        # AES-256 => 32-byte key in the underlying cipher.
        assert encryption_service.cipher.KEY_SIZE == 32


# =============================================================================
# PROPERTY-BASED CRYPTOGRAPHY TESTS WITH HYPOTHESIS
# Advanced testing for cryptographic properties
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
@pytest.mark.property
class TestEncryptionPropertyBased:
    """Property-based tests for encryption."""

    @given(plaintext=st.binary(min_size=0, max_size=10000))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=50)
    def test_encrypt_decrypt_any_data(self, plaintext: bytes):
        """
        Property: Any data should encrypt and decrypt correctly.

        Tests that encryption/decryption works for ANY binary data.
        """
        aes_gcm = AESGCMEncryption(_make_key())

        # Encrypt
        ciphertext, nonce = aes_gcm.encrypt(plaintext)

        # Decrypt
        decrypted = aes_gcm.decrypt(ciphertext, nonce)

        # Should match original
        assert decrypted == plaintext

    @given(plaintext=st.text(alphabet=st.characters(codec="utf-8"), min_size=0, max_size=5000))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=30)
    def test_encryption_service_any_string(self, plaintext: str, encryption_service: EncryptionService):
        """
        Property: Encryption service should handle any (UTF-8-encodable) string.
        """
        ciphertext, metadata = encryption_service.encrypt_string(
            plaintext,
            classification=DataClassification.CONFIDENTIAL
        )
        decrypted = encryption_service.decrypt_string(ciphertext, metadata)

        assert decrypted == plaintext

    @given(
        data=st.dictionaries(
            keys=st.text(min_size=1, max_size=50),
            values=st.text(min_size=0, max_size=100),
            min_size=0,
            max_size=20
        )
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=30)
    def test_encrypt_any_json_serializable_data(self, data: dict, encryption_service: EncryptionService):
        """
        Property: Encryption service should handle any JSON-serializable data.
        """
        data_json = json.dumps(data)
        ciphertext, metadata = encryption_service.encrypt_string(
            data_json,
            classification=DataClassification.CONFIDENTIAL
        )
        decrypted = encryption_service.decrypt_string(ciphertext, metadata)
        decrypted_data = json.loads(decrypted)

        assert decrypted_data == data


# =============================================================================
# CRYPTOGRAPHIC BEST PRACTICES TESTS
# Verify implementation follows cryptographic best practices
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
class TestCryptographicBestPractices:
    """Test cryptographic best practices."""

    def test_no_key_reuse_across_domains(self):
        """Test that different domains (salts) use different derived keys."""
        master_key = "master-secret-key-32-bytes-long!"

        key_domain1 = KeyDerivation.derive_key(master_key, salt=b"domain-one-salt!")
        key_domain2 = KeyDerivation.derive_key(master_key, salt=b"domain-two-salt!")

        # Keys should be different
        assert key_domain1 != key_domain2

    def test_nonce_never_reused(self):
        """Test that nonces are never reused (critical for GCM security)."""
        aes_gcm = AESGCMEncryption(_make_key())
        plaintext = b"Test data"

        nonces = set()

        # Generate 1000 encryptions
        for _ in range(1000):
            _, nonce = aes_gcm.encrypt(plaintext)
            nonces.add(nonce)

        # All nonces should be unique
        assert len(nonces) == 1000

    def test_key_size_sufficient(self):
        """Test that keys are sufficiently large (256 bits for AES-256)."""
        # AES-256 requires a 32-byte (256-bit) key.
        assert AESGCMEncryption.KEY_SIZE == 32

        # A correctly sized key builds a cipher; an undersized key is rejected.
        AESGCMEncryption(os.urandom(AESGCMEncryption.KEY_SIZE))
        with pytest.raises(ValueError):
            AESGCMEncryption(os.urandom(16))

    def test_authentication_tag_present(self):
        """Test that authentication tags are generated (AEAD requirement)."""
        aes_gcm = AESGCMEncryption(_make_key())
        plaintext = b"Test data"

        ciphertext, _ = aes_gcm.encrypt(plaintext)

        # AEAD: the ciphertext must carry the 128-bit (16-byte) GCM auth tag.
        assert AESGCMEncryption.TAG_SIZE == 16
        assert len(ciphertext) == len(plaintext) + AESGCMEncryption.TAG_SIZE

    def test_encrypted_data_differs_from_plaintext(self, encryption_service: EncryptionService):
        """Test that encrypted data is different from plaintext."""
        plaintext = "Sensitive patient data"

        ciphertext, _ = encryption_service.encrypt_string(
            plaintext,
            classification=DataClassification.CONFIDENTIAL
        )

        # Encrypted output should not contain the plaintext.
        assert plaintext not in ciphertext

    def test_key_rotation_support(self, encryption_service: EncryptionService):
        """Test that encryption supports key rotation (version + key metadata)."""
        plaintext = "Test data"

        _, metadata = encryption_service.encrypt_string(
            plaintext,
            classification=DataClassification.CONFIDENTIAL
        )

        # Version + key fingerprint + KDF params enable rotation / re-keying.
        assert "version" in metadata
        assert "key_id" in metadata
        assert "kdf_iterations" in metadata
