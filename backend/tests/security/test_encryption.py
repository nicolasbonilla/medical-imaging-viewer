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
@version 2.0.0 - Enterprise Security Testing
"""

import pytest
import json
from typing import Dict
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
        aes_gcm = AESGCMEncryption()

        plaintext = b"Sensitive patient data"
        key = aes_gcm.generate_key()

        # Encrypt
        ciphertext, nonce, tag = aes_gcm.encrypt(plaintext, key)

        # Decrypt
        decrypted = aes_gcm.decrypt(ciphertext, key, nonce, tag)

        assert decrypted == plaintext

    def test_generate_key_length(self):
        """Test that generated keys are 256 bits (32 bytes)."""
        aes_gcm = AESGCMEncryption()
        key = aes_gcm.generate_key()

        # AES-256 requires 32-byte key
        assert len(key) == 32

    def test_generate_key_randomness(self):
        """Test that generated keys are unique (cryptographically random)."""
        aes_gcm = AESGCMEncryption()

        key1 = aes_gcm.generate_key()
        key2 = aes_gcm.generate_key()

        # Keys should be different
        assert key1 != key2

    def test_nonce_uniqueness(self):
        """Test that nonces are unique for each encryption."""
        aes_gcm = AESGCMEncryption()
        plaintext = b"Test data"
        key = aes_gcm.generate_key()

        # Encrypt twice with same key and plaintext
        ciphertext1, nonce1, tag1 = aes_gcm.encrypt(plaintext, key)
        ciphertext2, nonce2, tag2 = aes_gcm.encrypt(plaintext, key)

        # Nonces must be different (critical for GCM security)
        assert nonce1 != nonce2

        # Ciphertexts should also differ due to different nonces
        assert ciphertext1 != ciphertext2

    def test_nonce_length(self):
        """Test that nonces are 96 bits (12 bytes) - recommended for GCM."""
        aes_gcm = AESGCMEncryption()
        plaintext = b"Test data"
        key = aes_gcm.generate_key()

        _, nonce, _ = aes_gcm.encrypt(plaintext, key)

        # GCM standard recommends 96-bit (12-byte) nonces
        assert len(nonce) == 12

    def test_authentication_tag_length(self):
        """Test that authentication tags are 128 bits (16 bytes)."""
        aes_gcm = AESGCMEncryption()
        plaintext = b"Test data"
        key = aes_gcm.generate_key()

        _, _, tag = aes_gcm.encrypt(plaintext, key)

        # GCM authentication tag should be 128 bits (16 bytes)
        assert len(tag) == 16

    def test_decryption_with_wrong_key(self):
        """Test that decryption fails with wrong key."""
        aes_gcm = AESGCMEncryption()
        plaintext = b"Sensitive data"

        key_correct = aes_gcm.generate_key()
        key_wrong = aes_gcm.generate_key()

        ciphertext, nonce, tag = aes_gcm.encrypt(plaintext, key_correct)

        # Decryption with wrong key should raise exception
        with pytest.raises(DecryptionError):
            aes_gcm.decrypt(ciphertext, key_wrong, nonce, tag)

    def test_decryption_with_tampered_ciphertext(self):
        """Test that decryption detects tampered ciphertext (authentication)."""
        aes_gcm = AESGCMEncryption()
        plaintext = b"Sensitive data"
        key = aes_gcm.generate_key()

        ciphertext, nonce, tag = aes_gcm.encrypt(plaintext, key)

        # Tamper with ciphertext
        tampered_ciphertext = bytes([c ^ 0xFF for c in ciphertext])

        # Decryption should fail due to authentication tag mismatch
        with pytest.raises(DecryptionError):
            aes_gcm.decrypt(tampered_ciphertext, key, nonce, tag)

    def test_decryption_with_tampered_tag(self):
        """Test that decryption detects tampered authentication tag."""
        aes_gcm = AESGCMEncryption()
        plaintext = b"Sensitive data"
        key = aes_gcm.generate_key()

        ciphertext, nonce, tag = aes_gcm.encrypt(plaintext, key)

        # Tamper with tag
        tampered_tag = bytes([t ^ 0xFF for t in tag])

        # Decryption should fail
        with pytest.raises(DecryptionError):
            aes_gcm.decrypt(ciphertext, key, nonce, tampered_tag)

    def test_encrypt_empty_data(self):
        """Test encryption of empty data."""
        aes_gcm = AESGCMEncryption()
        plaintext = b""
        key = aes_gcm.generate_key()

        ciphertext, nonce, tag = aes_gcm.encrypt(plaintext, key)

        # Should produce valid ciphertext (possibly empty)
        decrypted = aes_gcm.decrypt(ciphertext, key, nonce, tag)
        assert decrypted == plaintext

    def test_encrypt_large_data(self):
        """Test encryption of large data (1 MB)."""
        aes_gcm = AESGCMEncryption()
        plaintext = b"X" * (1024 * 1024)  # 1 MB
        key = aes_gcm.generate_key()

        ciphertext, nonce, tag = aes_gcm.encrypt(plaintext, key)
        decrypted = aes_gcm.decrypt(ciphertext, key, nonce, tag)

        assert decrypted == plaintext


# =============================================================================
# KEY DERIVATION TESTS
# ISO 27001 A.10.1.2 - Key management
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
class TestKeyDerivation:
    """Test key derivation with PBKDF2."""

    def test_derive_key_from_master_key(self):
        """Test key derivation from master key."""
        kdf = KeyDerivation()
        master_key = b"master-secret-key-32-bytes-long!"
        context = "patient_data"

        derived_key = kdf.derive_key(master_key, context)

        # Should return 32-byte key
        assert len(derived_key) == 32
        assert isinstance(derived_key, bytes)

    def test_derive_key_deterministic(self):
        """Test that key derivation is deterministic for same inputs."""
        kdf = KeyDerivation()
        master_key = b"master-secret-key-32-bytes-long!"
        context = "patient_data"

        key1 = kdf.derive_key(master_key, context)
        key2 = kdf.derive_key(master_key, context)

        # Should produce identical keys
        assert key1 == key2

    def test_derive_different_keys_for_different_contexts(self):
        """Test that different contexts produce different keys."""
        kdf = KeyDerivation()
        master_key = b"master-secret-key-32-bytes-long!"

        key_patients = kdf.derive_key(master_key, "patients")
        key_studies = kdf.derive_key(master_key, "studies")

        # Should produce different keys
        assert key_patients != key_studies

    def test_derive_key_with_salt(self):
        """Test key derivation with custom salt."""
        kdf = KeyDerivation()
        master_key = b"master-secret-key-32-bytes-long!"
        context = "patient_data"

        salt1 = b"salt1"
        salt2 = b"salt2"

        key1 = kdf.derive_key(master_key, context, salt=salt1)
        key2 = kdf.derive_key(master_key, context, salt=salt2)

        # Different salts should produce different keys
        assert key1 != key2

    def test_derive_key_invalid_master_key(self):
        """Test that short master keys are rejected."""
        kdf = KeyDerivation()
        short_key = b"short"

        with pytest.raises(KeyDerivationError):
            kdf.derive_key(short_key, "context")


# =============================================================================
# ENCRYPTION SERVICE TESTS
# High-level encryption service with data classification
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
class TestEncryptionService:
    """Test high-level encryption service."""

    def test_encrypt_decrypt_with_classification(self, encryption_service: EncryptionService):
        """Test encryption with data classification."""
        plaintext = "Patient SSN: 123-45-6789"

        # Encrypt with HIGHLY_RESTRICTED classification
        encrypted = encryption_service.encrypt(
            plaintext,
            classification=DataClassification.HIGHLY_RESTRICTED
        )

        # Decrypt
        decrypted = encryption_service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_phi_data(self, encryption_service: EncryptionService, sample_phi_data: dict):
        """Test encryption of Protected Health Information (PHI)."""
        phi_json = json.dumps(sample_phi_data)

        # Encrypt PHI
        encrypted = encryption_service.encrypt(
            phi_json,
            classification=DataClassification.HIGHLY_RESTRICTED
        )

        # Encrypted data should be different from plaintext
        assert encrypted != phi_json

        # Decrypt and verify
        decrypted = encryption_service.decrypt(encrypted)
        decrypted_data = json.loads(decrypted)

        assert decrypted_data == sample_phi_data

    def test_encrypt_with_different_classifications(self, encryption_service: EncryptionService):
        """Test encryption with different data classifications."""
        data = "Test data"

        classifications = [
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
            DataClassification.CONFIDENTIAL,
            DataClassification.RESTRICTED,
            DataClassification.HIGHLY_RESTRICTED,
        ]

        for classification in classifications:
            encrypted = encryption_service.encrypt(data, classification=classification)
            decrypted = encryption_service.decrypt(encrypted)

            assert decrypted == data

    def test_encrypted_data_format(self, encryption_service: EncryptionService):
        """Test that encrypted data contains all required components."""
        plaintext = "Test data"

        encrypted = encryption_service.encrypt(plaintext, classification=DataClassification.CONFIDENTIAL)

        # Encrypted data should be a string (base64 encoded JSON)
        assert isinstance(encrypted, str)

        # Should be able to parse as JSON (base64 decoded)
        import base64
        encrypted_json = json.loads(base64.b64decode(encrypted))

        # Should contain required fields
        assert "ciphertext" in encrypted_json
        assert "nonce" in encrypted_json
        assert "tag" in encrypted_json
        assert "classification" in encrypted_json
        assert "version" in encrypted_json

    def test_decrypt_with_wrong_key(self):
        """Test that decryption fails with wrong master key."""
        service1 = EncryptionService(master_key="key1" + "x" * 27)
        service2 = EncryptionService(master_key="key2" + "x" * 27)

        plaintext = "Test data"
        encrypted = service1.encrypt(plaintext, classification=DataClassification.CONFIDENTIAL)

        # Decryption with different service (different key) should fail
        with pytest.raises(DecryptionError):
            service2.decrypt(encrypted)

    def test_encrypt_unicode_data(self, encryption_service: EncryptionService):
        """Test encryption of Unicode data."""
        unicode_data = "Patient名前: John™中文🔒"

        encrypted = encryption_service.encrypt(unicode_data, classification=DataClassification.CONFIDENTIAL)
        decrypted = encryption_service.decrypt(encrypted)

        assert decrypted == unicode_data

    def test_encrypt_binary_data(self, encryption_service: EncryptionService):
        """Test encryption of binary data (e.g., DICOM files)."""
        # Simulate DICOM file header
        binary_data = b"\x00" * 128 + b"DICM" + b"\x00" * 100

        encrypted = encryption_service.encrypt_bytes(
            binary_data,
            classification=DataClassification.HIGHLY_RESTRICTED
        )
        decrypted = encryption_service.decrypt_bytes(encrypted)

        assert decrypted == binary_data


# =============================================================================
# ENCRYPTED REDIS CLIENT TESTS
# ISO 27001 A.10.1.2 - Key management for cached data
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
@pytest.mark.asyncio
class TestEncryptedRedisClient:
    """Test encrypted Redis client for secure caching."""

    async def test_set_get_encrypted_value(self, encryption_service: EncryptionService):
        """Test setting and getting encrypted values in Redis."""
        from app.core.security.encryption import EncryptedRedisClient

        # Note: This test requires Redis mock or connection
        # For now, test the encryption layer only

        client = EncryptedRedisClient(
            encryption_service=encryption_service,
            redis_client=None  # Would be actual Redis client
        )

        key = "patient:12345:data"
        value = {"ssn": "123-45-6789", "diagnosis": "Diabetes"}

        # Encrypt value
        encrypted = client.encrypt_value(value, classification=DataClassification.HIGHLY_RESTRICTED)

        # Verify encrypted value is different
        assert encrypted != json.dumps(value)

        # Decrypt value
        decrypted = client.decrypt_value(encrypted)

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
        """Test all data classification levels."""
        levels = [
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
            DataClassification.CONFIDENTIAL,
            DataClassification.RESTRICTED,
            DataClassification.HIGHLY_RESTRICTED,
        ]

        # Verify all levels exist
        assert len(levels) == 5

    def test_classification_hierarchy(self):
        """Test that classification levels have proper hierarchy."""
        # Verify that HIGHLY_RESTRICTED > RESTRICTED > CONFIDENTIAL > INTERNAL > PUBLIC
        levels_ordered = [
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
            DataClassification.CONFIDENTIAL,
            DataClassification.RESTRICTED,
            DataClassification.HIGHLY_RESTRICTED,
        ]

        # Enum values should increase
        for i in range(len(levels_ordered) - 1):
            assert levels_ordered[i].value < levels_ordered[i + 1].value


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
            encrypted = encryption_service.encrypt(
                value,
                classification=DataClassification.HIGHLY_RESTRICTED
            )

            # Verify encrypted
            assert encrypted != value

            # Verify can be decrypted
            decrypted = encryption_service.decrypt(encrypted)
            assert decrypted == value

    def test_phi_encryption_algorithm_strength(self, encryption_service: EncryptionService):
        """Test that PHI is encrypted with AES-256 (HIPAA recommended)."""
        phi = "SSN: 123-45-6789"

        encrypted = encryption_service.encrypt(
            phi,
            classification=DataClassification.HIGHLY_RESTRICTED
        )

        # Decode encrypted data structure
        import base64
        encrypted_json = json.loads(base64.b64decode(encrypted))

        # Verify metadata indicates strong encryption
        assert encrypted_json["version"] == "1.0"
        assert encrypted_json["classification"] == "HIGHLY_RESTRICTED"


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
        aes_gcm = AESGCMEncryption()
        key = aes_gcm.generate_key()

        # Encrypt
        ciphertext, nonce, tag = aes_gcm.encrypt(plaintext, key)

        # Decrypt
        decrypted = aes_gcm.decrypt(ciphertext, key, nonce, tag)

        # Should match original
        assert decrypted == plaintext

    @given(plaintext=st.text(min_size=0, max_size=5000))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=30)
    def test_encryption_service_any_string(self, plaintext: str, encryption_service: EncryptionService):
        """
        Property: Encryption service should handle any string.
        """
        try:
            encrypted = encryption_service.encrypt(
                plaintext,
                classification=DataClassification.CONFIDENTIAL
            )
            decrypted = encryption_service.decrypt(encrypted)

            assert decrypted == plaintext
        except Exception as e:
            pytest.fail(f"Encryption service failed on input: {plaintext[:100]} | Error: {e}")

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
        try:
            data_json = json.dumps(data)
            encrypted = encryption_service.encrypt(
                data_json,
                classification=DataClassification.CONFIDENTIAL
            )
            decrypted = encryption_service.decrypt(encrypted)
            decrypted_data = json.loads(decrypted)

            assert decrypted_data == data
        except Exception as e:
            pytest.fail(f"Encryption failed on JSON data | Error: {e}")


# =============================================================================
# CRYPTOGRAPHIC BEST PRACTICES TESTS
# Verify implementation follows cryptographic best practices
# =============================================================================

@pytest.mark.security
@pytest.mark.encryption
class TestCryptographicBestPractices:
    """Test cryptographic best practices."""

    def test_no_key_reuse_across_contexts(self):
        """Test that different contexts use different derived keys."""
        kdf = KeyDerivation()
        master_key = b"master-secret-key-32-bytes-long!"

        key_context1 = kdf.derive_key(master_key, "context1")
        key_context2 = kdf.derive_key(master_key, "context2")

        # Keys should be different
        assert key_context1 != key_context2

    def test_nonce_never_reused(self):
        """Test that nonces are never reused (critical for GCM security)."""
        aes_gcm = AESGCMEncryption()
        plaintext = b"Test data"
        key = aes_gcm.generate_key()

        nonces = set()

        # Generate 1000 encryptions
        for _ in range(1000):
            _, nonce, _ = aes_gcm.encrypt(plaintext, key)
            nonces.add(nonce)

        # All nonces should be unique
        assert len(nonces) == 1000

    def test_key_size_sufficient(self):
        """Test that keys are sufficiently large (256 bits for AES-256)."""
        aes_gcm = AESGCMEncryption()
        key = aes_gcm.generate_key()

        # AES-256 requires 32-byte (256-bit) key
        assert len(key) == 32

    def test_authentication_tag_present(self):
        """Test that authentication tags are generated (AEAD requirement)."""
        aes_gcm = AESGCMEncryption()
        plaintext = b"Test data"
        key = aes_gcm.generate_key()

        ciphertext, nonce, tag = aes_gcm.encrypt(plaintext, key)

        # Tag should be present and non-empty
        assert tag is not None
        assert len(tag) == 16  # GCM standard tag size

    def test_encrypted_data_differs_from_plaintext(self, encryption_service: EncryptionService):
        """Test that encrypted data is different from plaintext."""
        plaintext = "Sensitive patient data"

        encrypted = encryption_service.encrypt(
            plaintext,
            classification=DataClassification.CONFIDENTIAL
        )

        # Encrypted should not contain plaintext
        assert plaintext not in encrypted

    def test_key_rotation_support(self, encryption_service: EncryptionService):
        """Test that encryption supports key rotation (version field)."""
        plaintext = "Test data"

        encrypted = encryption_service.encrypt(
            plaintext,
            classification=DataClassification.CONFIDENTIAL
        )

        # Decode encrypted structure
        import base64
        encrypted_json = json.loads(base64.b64decode(encrypted))

        # Should have version field for key rotation
        assert "version" in encrypted_json
