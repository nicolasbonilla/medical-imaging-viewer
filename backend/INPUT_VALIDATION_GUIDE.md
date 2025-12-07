# Input Validation and Sanitization Guide

**ISO 27001 Controls:**
- A.8.2.3 - Handling of assets
- A.14.1.2 - Securing application services on public networks
- A.14.2.1 - Secure development policy
- A.14.2.5 - Secure system engineering principles

**OWASP Top 10 2021:**
- A03:2021 - Injection

---

## Table of Contents

1. [Overview](#overview)
2. [Automatic Validation (Middleware)](#automatic-validation-middleware)
3. [Manual Validation](#manual-validation)
4. [File Upload Validation](#file-upload-validation)
5. [Pydantic Models with Validation](#pydantic-models-with-validation)
6. [Security Event Logging](#security-event-logging)
7. [Configuration](#configuration)
8. [Best Practices](#best-practices)

---

## Overview

The Medical Imaging Viewer implements comprehensive input validation and sanitization to prevent:

- **SQL Injection** - Prevents database manipulation attacks
- **XSS (Cross-Site Scripting)** - Prevents malicious script injection
- **Command Injection** - Prevents OS command execution
- **Path Traversal** - Prevents unauthorized file access
- **File Upload Exploits** - Validates file formats and content
- **LDAP/XML Injection** - Prevents directory and XML attacks

### Security Architecture

```
Request → IP Blacklist → Rate Limiting → INPUT VALIDATION → Audit → Logging → CORS → Routes
```

Input validation middleware is applied **automatically** to all requests (except health/docs endpoints).

---

## Automatic Validation (Middleware)

The `InputValidationMiddleware` is automatically applied to all API endpoints via FastAPI middleware stack.

### What Gets Validated Automatically

1. **Query Parameters** - All URL query string parameters
2. **Path Parameters** - All URL path parameters (e.g., `/users/{user_id}`)
3. **Request Body** - All JSON request body fields (recursively)
4. **Headers** - Selected security-sensitive headers

### Validation Rules by Path

| Path Pattern | SQL | XSS | Command | Path | Allow HTML |
|-------------|-----|-----|---------|------|-----------|
| `/api/v1/auth/*` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `/api/v1/users/*` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `/api/v1/imaging/*` | ✅ | ✅ | ❌ | ✅ | ❌ |
| `/api/v1/drive/*` | ✅ | ✅ | ❌ | ✅ | ❌ |
| `/api/v1/segmentation/*` | ✅ | ✅ | ❌ | ✅ | ❌ |
| Default | ✅ | ✅ | ❌ | ❌ | ❌ |

### Validation Responses

When validation fails, the middleware returns HTTP 400 with:

```json
{
  "error": "sql_injection|xss_attempt|command_injection|path_traversal|validation_error",
  "message": "Invalid input detected",
  "details": "Specific error description"
}
```

**Audit logging is automatic** - all validation failures are logged with severity HIGH for investigation.

### Configuration

Control middleware behavior via environment variables in `.env`:

```bash
# Enable/disable input validation middleware
INPUT_VALIDATION_ENABLED=true

# Strict mode: block requests (true) or only log warnings (false)
INPUT_VALIDATION_STRICT=true
```

**Production Recommendation:** Always use `INPUT_VALIDATION_STRICT=true` in production.

---

## Manual Validation

For cases where you need explicit validation in your code (e.g., custom business logic, non-HTTP inputs):

### 1. Comprehensive Input Validator

Use `InputValidator` for multi-layer validation:

```python
from app.core.security import InputValidator, ValidationError

validator = InputValidator()

try:
    # Validate all attack vectors
    validated_value = validator.validate_all(
        user_input,
        field_name="username",
        check_sql=True,
        check_xss=True,
        check_command=False,
        check_path=False,
        allow_html=False
    )
except ValidationError as e:
    # Handle validation error
    raise HTTPException(status_code=400, detail=str(e))
```

### 2. Specific Validators

Use individual validators for targeted protection:

#### SQL Injection Prevention

```python
from app.core.security import SQLValidator, SQLInjectionDetected

try:
    safe_input = SQLValidator.validate(user_input, field_name="search_query")
except SQLInjectionDetected as e:
    logger.error(f"SQL injection attempt: {e}")
    raise HTTPException(status_code=400, detail="Invalid input")
```

**Detects:**
- SQL keywords: `SELECT`, `UNION`, `DROP`, `EXEC`, etc.
- SQL patterns: `' OR '1'='1`, `UNION SELECT`, `; DROP TABLE`, etc.
- Comment markers: `--`, `/* */`

#### XSS Prevention

```python
from app.core.security import XSSValidator, XSSDetected

try:
    # Strict validation (blocks all HTML)
    safe_input = XSSValidator.validate(
        user_input,
        field_name="comment",
        allow_html=False
    )
except XSSDetected as e:
    logger.error(f"XSS attempt: {e}")
    raise HTTPException(status_code=400, detail="Invalid input")

# OR: Sanitize by escaping HTML
sanitized = XSSValidator.sanitize(user_input)
```

**Detects:**
- HTML tags: `<script>`, `<iframe>`, `<embed>`, etc.
- JavaScript: `javascript:`, `data:text/html`, `vbscript:`
- Event handlers: `onclick=`, `onerror=`, `onload=`, etc.

#### Command Injection Prevention

```python
from app.core.security import CommandInjectionValidator, CommandInjectionDetected

try:
    safe_input = CommandInjectionValidator.validate(
        user_input,
        field_name="filename"
    )
except CommandInjectionDetected as e:
    logger.error(f"Command injection attempt: {e}")
    raise HTTPException(status_code=400, detail="Invalid input")
```

**Detects:**
- Shell metacharacters: `;`, `|`, `&`, `$`, `` ` ``, etc.
- Command chaining: `command1 && command2`
- Subshell execution: `$(command)`, `` `command` ``

#### Path Traversal Prevention

```python
from app.core.security import PathTraversalValidator, PathTraversalDetected

try:
    safe_path = PathTraversalValidator.validate(
        user_path,
        field_name="file_path"
    )
except PathTraversalDetected as e:
    logger.error(f"Path traversal attempt: {e}")
    raise HTTPException(status_code=400, detail="Invalid path")
```

**Detects:**
- Directory traversal: `..`, `../`, `..\`
- URL encoding: `%2e%2e`, `%252e%252e`
- Absolute paths: `/etc/passwd`, `C:\Windows\`

---

## File Upload Validation

Medical imaging files require specialized validation to ensure format compliance and detect malicious content.

### Basic File Upload Validation

```python
from fastapi import UploadFile, HTTPException
from app.core.security import (
    FileUploadValidator,
    MedicalImageFormat,
    InvalidFileFormat,
    MaliciousFileDetected
)

@router.post("/upload")
async def upload_image(file: UploadFile):
    """Upload medical image with validation."""

    try:
        # Validate file
        filename, mime_type = await FileUploadValidator.validate_file(
            file=file,
            max_size=500 * 1024 * 1024,  # 500 MB
            allowed_formats=[
                MedicalImageFormat.DICOM,
                MedicalImageFormat.NIFTI,
                MedicalImageFormat.NIFTI_GZ
            ]
        )

        # File is validated - proceed with processing
        # ...

    except InvalidFileFormat as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MaliciousFileDetected as e:
        # Critical security event - already logged by validator
        raise HTTPException(status_code=400, detail="File rejected for security reasons")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
```

### File Validation Features

1. **File Size Validation** - Prevents DoS via large files (default: 500 MB)
2. **Magic Number Detection** - Verifies file format from binary signature
3. **MIME Type Validation** - Ensures file type matches allowed formats
4. **Filename Sanitization** - Removes path traversal and invalid characters
5. **Malicious Content Detection** - Scans for embedded scripts/commands
6. **SHA-256 Hashing** - Calculates integrity hash for audit trail

### Allowed Medical Image Formats

```python
from app.core.security import MedicalImageFormat

# Available formats:
MedicalImageFormat.DICOM       # .dcm, .dicom
MedicalImageFormat.NIFTI       # .nii
MedicalImageFormat.NIFTI_GZ    # .nii.gz
MedicalImageFormat.PNG         # .png
MedicalImageFormat.JPEG        # .jpg, .jpeg
MedicalImageFormat.TIFF        # .tif, .tiff
```

### Custom Upload Constraints

```python
# More restrictive validation
filename, mime_type = await FileUploadValidator.validate_file(
    file=file,
    max_size=100 * 1024 * 1024,  # 100 MB max
    allowed_formats=[MedicalImageFormat.DICOM]  # Only DICOM
)
```

---

## Pydantic Models with Validation

Use pre-built Pydantic models for automatic validation in request schemas:

### ValidatedString

```python
from pydantic import BaseModel
from app.core.security import ValidatedString

class UserSearchRequest(BaseModel):
    query: ValidatedString  # Automatically validates for SQL/XSS

# Usage in route:
@router.post("/search")
async def search_users(request: UserSearchRequest):
    query = request.query.value  # Pre-validated string
```

### ValidatedPath

```python
from pydantic import BaseModel
from app.core.security import ValidatedPath

class FileAccessRequest(BaseModel):
    path: ValidatedPath  # Automatically validates for traversal

# Usage in route:
@router.get("/file")
async def get_file(request: FileAccessRequest):
    safe_path = request.path.path  # Pre-validated path
```

### ValidatedCommand

```python
from pydantic import BaseModel
from app.core.security import ValidatedCommand

class ProcessRequest(BaseModel):
    command: ValidatedCommand  # Automatically validates for injection

# Usage in route:
@router.post("/process")
async def process(request: ProcessRequest):
    safe_command = request.command.command  # Pre-validated command
```

### Custom Pydantic Models

```python
from pydantic import BaseModel, Field, field_validator
from app.core.security import SQLValidator, XSSValidator

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., regex=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    bio: str = Field(default="", max_length=500)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username for injection attacks."""
        v = SQLValidator.validate(v, "username")
        v = XSSValidator.validate(v, "username")
        return v

    @field_validator('bio')
    @classmethod
    def validate_bio(cls, v: str) -> str:
        """Sanitize bio (allow safe HTML)."""
        v = XSSValidator.sanitize(v)
        return v
```

---

## Security Event Logging

All validation failures are **automatically logged** to the audit trail for security monitoring.

### Audit Event Types

| Validation Type | Event Type | Severity |
|----------------|------------|----------|
| SQL Injection | `SECURITY_INJECTION_ATTEMPT` | HIGH |
| XSS Attack | `SECURITY_XSS_ATTEMPT` | HIGH |
| Command Injection | `SECURITY_INJECTION_ATTEMPT` | HIGH |
| Path Traversal | `SECURITY_PATH_TRAVERSAL` | HIGH |
| Invalid Input | `SECURITY_INVALID_INPUT` | MEDIUM |
| Malware Detection | `SECURITY_MALWARE_DETECTED` | CRITICAL |

### Viewing Audit Logs

```bash
# View recent security events
tail -f logs/audit.log | grep "SECURITY_"

# Search for specific IP
grep "192.168.1.100" logs/audit.log | grep "injection"

# Count attacks by type
jq -r 'select(.event_type | contains("SECURITY")) | .event_type' logs/audit.log | sort | uniq -c
```

### Example Audit Log Entry

```json
{
  "event_id": "a3f2c1d9e8b7f6a5",
  "timestamp": "2025-01-15T14:23:45.123456Z",
  "event_type": "SECURITY_INJECTION_ATTEMPT",
  "severity": "HIGH",
  "outcome": "DENIED",
  "user_id": "user_123",
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0...",
  "description": "SQL injection attempt detected in field 'search_query'",
  "metadata": {
    "field": "search_query",
    "keyword_found": "UNION",
    "value_sample": "' UNION SELECT * FROM users--"
  },
  "iso27001_controls": ["A.14.2.1", "A.12.4.1"],
  "checksum": "sha256:abcdef1234567890..."
}
```

---

## Configuration

### Environment Variables

Add to `.env` for production:

```bash
# ============================================================================
# INPUT VALIDATION CONFIGURATION (ISO 27001 A.14.2.1)
# ============================================================================

# Enable input validation middleware
INPUT_VALIDATION_ENABLED=true

# Strict mode: true = block requests, false = log only
# CRITICAL: Always use true in production
INPUT_VALIDATION_STRICT=true

# Maximum file upload size (bytes)
MAX_UPLOAD_SIZE=524288000  # 500 MB
```

### Application Configuration

Validation settings in `app/core/config.py`:

```python
class Settings(BaseSettings):
    # Security Middleware Configuration (ISO 27001 A.14.2.1)
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    INPUT_VALIDATION_ENABLED: bool = Field(default=True)
    INPUT_VALIDATION_STRICT: bool = Field(default=True)

    # Upload Configuration
    MAX_UPLOAD_SIZE: int = Field(default=524_288_000, ge=1_000_000, le=1_073_741_824)
    ALLOWED_EXTENSIONS: List[str] = Field(default=[".dcm", ".nii", ".nii.gz"])
```

---

## Best Practices

### 1. Trust the Middleware

✅ **DO:**
- Rely on automatic middleware validation for standard endpoints
- Focus on business logic in your route handlers
- Use manual validation only when needed (e.g., complex custom logic)

❌ **DON'T:**
- Re-implement validation in every route handler
- Bypass middleware validation without security review
- Disable validation in production

### 2. Validate Early, Validate Often

```python
# ✅ GOOD: Validate at entry point
@router.post("/create-user")
async def create_user(user: CreateUserRequest):  # Pydantic validates here
    # user.username is already validated
    await user_service.create(user)

# ❌ BAD: Validate deep in business logic
@router.post("/create-user")
async def create_user(user: dict):
    # Raw dict - no validation!
    result = await user_service.create(user)  # Validation too late
```

### 3. Use Type-Safe Pydantic Models

```python
# ✅ GOOD: Type-safe with automatic validation
class ImageProcessRequest(BaseModel):
    file_id: str = Field(..., min_length=1, max_length=100)
    slice_index: int = Field(..., ge=0, le=10000)
    window_level: int = Field(..., ge=-1024, le=3071)

# ❌ BAD: Dict without validation
@router.post("/process")
async def process(request: dict):  # No validation!
    file_id = request['file_id']  # May not exist!
```

### 4. Sanitize Output to Users

```python
from app.core.security import XSSValidator

# ✅ GOOD: Sanitize user-generated content before display
@router.get("/comments/{id}")
async def get_comment(id: str):
    comment = await db.get_comment(id)
    comment.text = XSSValidator.sanitize(comment.text)  # Escape HTML
    return comment

# ❌ BAD: Return raw user input
@router.get("/comments/{id}")
async def get_comment(id: str):
    return await db.get_comment(id)  # May contain XSS!
```

### 5. Log but Don't Expose Details

```python
# ✅ GOOD: Log details, return generic error
try:
    validated = SQLValidator.validate(user_input, "query")
except SQLInjectionDetected as e:
    logger.error(f"SQL injection: {e}", extra={"input": user_input})
    raise HTTPException(status_code=400, detail="Invalid input")  # Generic

# ❌ BAD: Expose validation details to attacker
try:
    validated = SQLValidator.validate(user_input, "query")
except SQLInjectionDetected as e:
    raise HTTPException(status_code=400, detail=str(e))  # Reveals detection method!
```

### 6. File Upload Checklist

When implementing file uploads:

- [ ] Validate file size before processing
- [ ] Check magic numbers, not just extensions
- [ ] Restrict allowed MIME types
- [ ] Sanitize filename (remove path traversal)
- [ ] Scan for malicious content
- [ ] Calculate integrity hash
- [ ] Store files outside web root
- [ ] Use random filenames on disk
- [ ] Implement virus scanning if possible
- [ ] Log all uploads with user/IP/hash

### 7. Defense in Depth

```python
# ✅ GOOD: Multiple layers of defense
@router.post("/search")
async def search(query: ValidatedString):  # Layer 1: Pydantic validation
    safe_query = SQLValidator.validate(query.value, "query")  # Layer 2: Explicit validation
    results = await db.search(safe_query)  # Layer 3: Parameterized queries
    return [XSSValidator.sanitize(r.text) for r in results]  # Layer 4: Output sanitization

# ❌ BAD: Single point of failure
@router.post("/search")
async def search(query: str):
    return await db.raw_query(f"SELECT * FROM items WHERE name LIKE '%{query}%'")  # SQL injection!
```

### 8. Security Testing

Include injection attempts in your test suite:

```python
import pytest
from fastapi.testclient import TestClient

def test_sql_injection_blocked(client: TestClient):
    """Test that SQL injection attempts are blocked."""
    response = client.post("/search", json={
        "query": "'; DROP TABLE users--"
    })
    assert response.status_code == 400
    assert "injection" in response.json()['error'].lower()

def test_xss_blocked(client: TestClient):
    """Test that XSS attempts are blocked."""
    response = client.post("/comment", json={
        "text": "<script>alert('XSS')</script>"
    })
    assert response.status_code == 400
    assert "xss" in response.json()['error'].lower()
```

---

## ISO 27001 Compliance Summary

| Control | Requirement | Implementation |
|---------|-------------|----------------|
| **A.8.2.3** | Handling of assets | File upload validation, format verification |
| **A.14.1.2** | Securing application services | Automatic middleware validation |
| **A.14.2.1** | Secure development policy | Input validation framework, sanitization |
| **A.14.2.5** | Secure system engineering | Defense in depth, multiple validation layers |
| **A.12.4.1** | Event logging | Automatic audit logging of validation failures |

---

## OWASP Top 10 Coverage

| OWASP Risk | Coverage | Mitigation |
|-----------|----------|------------|
| **A03:2021 - Injection** | ✅ Complete | SQL, XSS, Command, LDAP injection prevention |
| **A01:2021 - Broken Access Control** | ✅ Partial | Path traversal prevention |
| **A04:2021 - Insecure Design** | ✅ Complete | Secure file upload validation |
| **A05:2021 - Security Misconfiguration** | ✅ Complete | Secure defaults, strict mode |
| **A09:2021 - Security Logging Failures** | ✅ Complete | Comprehensive audit trail |

---

## Support and Security Issues

**Security Vulnerabilities:** Report to security@example.com (do not create public issues)

**Questions:** Contact development team via Slack #security channel

**Documentation:** See also:
- [DEPLOYMENT_SECURITY_GUIDE.md](DEPLOYMENT_SECURITY_GUIDE.md)
- [ISO 27001 Implementation Plan](docs/iso27001_implementation_plan.md)
- [API Security Best Practices](docs/api_security.md)

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-01-15 | Initial implementation with SQL, XSS, Command, Path validation |
| 1.1.0 | 2025-01-15 | Added file upload validation for medical imaging formats |
| 1.2.0 | 2025-01-15 | Integrated automatic middleware validation |

---

**Last Updated:** 2025-01-15
**Compliance:** ISO/IEC 27001:2022
**OWASP Reference:** OWASP Top 10 2021
