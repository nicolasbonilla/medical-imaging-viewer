# 🔒 SECURITY AUDIT & COMPLIANCE REPORT
## Medical Imaging Viewer Application

**Report Date:** November 22, 2025
**Auditor:** Security Analysis System
**Application Version:** 1.0.0
**Audit Type:** Comprehensive Security & Compliance Assessment
**Standards Evaluated:** ISO 27001, OWASP Top 10 2021, HIPAA Technical Safeguards

---

## EXECUTIVE SUMMARY

### Overall Security Rating: ⚠️ **MEDIUM RISK - NOT PRODUCTION READY**

The Medical Imaging Viewer demonstrates **strong architectural foundations** and modern development practices. However, **critical security vulnerabilities** prevent deployment in production healthcare environments without substantial remediation.

### Key Findings:

| Category | Status | Priority |
|----------|--------|----------|
| **Architecture** | ✅ Good | - |
| **Authentication** | ❌ Critical | P0 |
| **Authorization** | ❌ Critical | P0 |
| **Secrets Management** | ❌ Critical | P0 |
| **Input Validation** | ⚠️ Partial | P1 |
| **Encryption** | ❌ Missing | P0 |
| **Logging & Monitoring** | ⚠️ Basic | P1 |
| **Testing** | ❌ None | P1 |
| **HIPAA Compliance** | ❌ Non-Compliant | P0 |
| **ISO 27001 Compliance** | ❌ Non-Compliant | P0 |

---

## 1. ISO 27001 COMPLIANCE ANALYSIS

ISO 27001 requires organizations to establish, implement, maintain and continually improve an Information Security Management System (ISMS). Below is the compliance status for applicable controls:

### A.5 - Information Security Policies
**Status:** ❌ **NON-COMPLIANT**

**Findings:**
- No documented information security policy
- No security objectives or responsibilities defined
- No management review process

**Required Actions:**
1. Create information security policy document
2. Define security roles and responsibilities
3. Establish management review cadence

### A.8 - Asset Management
**Status:** ⚠️ **PARTIALLY COMPLIANT**

**Findings:**
- ✅ Code repository exists
- ✅ Dependencies documented (requirements.txt, package.json)
- ❌ No asset inventory or classification
- ❌ No data retention/disposal policies
- ❌ Medical imaging data classification undefined

**Required Actions:**
1. Create asset inventory including all medical data
2. Classify data according to sensitivity (e.g., PHI = Critical)
3. Define retention and disposal procedures for medical images
4. Implement automated asset discovery

### A.9 - Access Control
**Status:** ❌ **NON-COMPLIANT**

**Findings:**
- ❌ No user authentication system implemented
- ❌ No role-based access control (RBAC)
- ❌ No user registration/management
- ❌ No session management
- ❌ No password policy enforcement
- ❌ No multi-factor authentication (MFA)
- ❌ Only Google OAuth for Drive access (single purpose)

**Required Actions:**
1. Implement user authentication (OAuth 2.0 + JWT recommended)
2. Create RBAC system with roles: Admin, Radiologist, Technician, Viewer
3. Implement session management with timeouts
4. Enforce strong password policies (12+ chars, complexity)
5. Add MFA support (TOTP/SMS)
6. Implement access logging

**Code Example - Missing Authentication Middleware:**
```python
# Current: No authentication on endpoints
@router.get("/list", response_model=List[SegmentationResponse])
async def list_segmentations(file_id: Optional[str] = Query(None)):
    # Anyone can access this

# Required: Protected endpoints
from app.core.security import require_auth

@router.get("/list", response_model=List[SegmentationResponse])
async def list_segmentations(
    file_id: Optional[str] = Query(None),
    current_user: User = Depends(require_auth)  # ← Missing
):
    # Check user permissions
    if not current_user.can_view_segmentations():
        raise HTTPException(403, "Forbidden")
```

### A.10 - Cryptography
**Status:** ❌ **NON-COMPLIANT**

**Findings:**
- ❌ **CRITICAL:** No TLS/HTTPS enforcement
- ❌ **CRITICAL:** Credentials stored in plaintext files
- ❌ No encryption at rest for medical images
- ❌ No encryption in transit for internal communications
- ⚠️ JWT infrastructure present but unused
- ⚠️ Password hashing libraries installed but unused

**Vulnerabilities:**
```python
# config.py - Line 28
SECRET_KEY: str = "your-secret-key-change-this-in-production"  # ❌ Hardcoded default
```

```python
# drive_service.py - Lines 29-30, 57-58
with open(self.settings.GOOGLE_DRIVE_TOKEN_FILE, 'rb') as token:
    self.creds = pickle.load(token)  # ❌ Unencrypted token storage

with open(self.settings.GOOGLE_DRIVE_TOKEN_FILE, 'wb') as token:
    pickle.dump(self.creds, token)  # ❌ Plaintext credential persistence
```

**Required Actions:**
1. **Immediate:** Remove hardcoded SECRET_KEY, use environment variables only
2. **Immediate:** Implement HTTPS/TLS (Let's Encrypt certificates)
3. Encrypt credentials at rest using AES-256
4. Implement encrypted session storage (Redis with encryption)
5. Use secrets management service (AWS Secrets Manager, HashiCorp Vault, Azure Key Vault)
6. Encrypt medical imaging data at rest (AES-256-GCM)
7. Implement HSTS headers

### A.12 - Operations Security
**Status:** ⚠️ **PARTIALLY COMPLIANT**

**Findings:**
- ✅ Docker containerization implemented
- ✅ Dependency management in place
- ❌ No vulnerability scanning
- ❌ No malware protection
- ❌ No backup procedures defined
- ❌ No change management process
- ❌ No capacity management

**Required Actions:**
1. Implement automated vulnerability scanning (Snyk, Dependabot)
2. Regular dependency updates (monthly minimum)
3. Define backup strategy for segmentation data
4. Implement automated backups (daily)
5. Create change management workflow
6. Monitor resource usage and capacity

### A.14 - System Acquisition, Development and Maintenance
**Status:** ⚠️ **PARTIALLY COMPLIANT**

**Findings:**
- ✅ Separation of environments (dev/prod via .env)
- ✅ Code organization follows best practices
- ✅ Pydantic validation for data models
- ❌ **CRITICAL:** No automated testing
- ❌ No code review process documented
- ❌ No security testing in SDLC
- ❌ No static analysis security testing (SAST)
- ❌ No dynamic analysis security testing (DAST)

**Test Coverage:**
```bash
Backend: 0% (No tests found)
Frontend: 0% (No test framework configured)
```

**Required Actions:**
1. **Immediate:** Implement unit tests (target 80% coverage)
2. **Immediate:** Implement integration tests for API endpoints
3. Set up CI/CD pipeline with automated testing
4. Implement SAST tools (Bandit for Python, ESLint security plugins)
5. Add pre-commit hooks (black, flake8, mypy, safety)
6. Implement code review requirements (2 approvals minimum)
7. Add security-focused code review checklist

### A.16 - Information Security Incident Management
**Status:** ❌ **NON-COMPLIANT**

**Findings:**
- ❌ No incident response plan
- ❌ No security event logging
- ❌ No monitoring/alerting system
- ❌ No incident reporting procedures

**Required Actions:**
1. Create incident response plan document
2. Implement centralized logging (ELK Stack, Splunk, Datadog)
3. Set up security monitoring and alerting
4. Define incident classification levels
5. Create incident response team contacts

### A.17 - Business Continuity
**Status:** ❌ **NON-COMPLIANT**

**Findings:**
- ❌ No disaster recovery plan
- ❌ No backup procedures
- ❌ No redundancy/failover systems
- ❌ RTO/RPO undefined

**Required Actions:**
1. Define Recovery Time Objective (RTO) and Recovery Point Objective (RPO)
2. Implement automated backups
3. Create disaster recovery plan
4. Test recovery procedures quarterly

### A.18 - Compliance
**Status:** ❌ **NON-COMPLIANT**

**Findings:**
- ❌ No HIPAA compliance measures (if handling US patient data)
- ❌ No GDPR compliance measures (if handling EU patient data)
- ❌ No audit trail for medical data access
- ❌ No patient consent management
- ❌ No data breach notification procedures

---

## 2. OWASP TOP 10 (2021) VULNERABILITY ASSESSMENT

### A01:2021 – Broken Access Control
**Risk Level:** 🔴 **CRITICAL**

**Vulnerabilities Found:**

1. **No Authentication on API Endpoints**
   ```python
   # ALL endpoints are publicly accessible:

   GET /api/v1/drive/files        # ❌ Anyone can list files
   GET /api/v1/drive/files/{id}   # ❌ Anyone can download medical images
   POST /api/v1/segmentation/create  # ❌ Anyone can create segmentations
   DELETE /api/v1/segmentation/{id}  # ❌ Anyone can delete segmentations
   ```

2. **No Authorization Checks**
   - No ownership validation for segmentations
   - No role-based permissions
   - Any user can modify any segmentation

3. **CORS Misconfiguration**
   ```python
   # main.py - Lines 22-28
   app.add_middleware(
       CORSMiddleware,
       allow_origins=settings.CORS_ORIGINS,  # Multiple localhost ports
       allow_credentials=True,
       allow_methods=["*"],  # ❌ Allows ALL methods
       allow_headers=["*"],  # ❌ Allows ALL headers
   )
   ```

**Impact:** Complete unauthorized access to all medical imaging data and segmentations.

**Remediation:**

```python
# 1. Add authentication middleware
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(401, "Invalid token")
        # Fetch user from database
        user = await get_user_by_id(user_id)
        if user is None:
            raise HTTPException(401, "User not found")
        return user
    except JWTError:
        raise HTTPException(401, "Invalid token")

# 2. Protect all endpoints
@router.delete("/{segmentation_id}")
async def delete_segmentation(
    segmentation_id: str,
    current_user: User = Depends(get_current_user)  # ← Add this
):
    # 3. Check ownership
    seg = await get_segmentation(segmentation_id)
    if seg.owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(403, "Not authorized")

    # Proceed with deletion
    await segmentation_service.delete_segmentation(segmentation_id)

# 4. Restrict CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://medical-viewer.example.com"  # Production domain only
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # Specific methods
    allow_headers=["Content-Type", "Authorization"],  # Specific headers
)
```

### A02:2021 – Cryptographic Failures
**Risk Level:** 🔴 **CRITICAL**

**Vulnerabilities Found:**

1. **Plaintext Credential Storage**
   ```json
   // backend/credentials.json - 405 bytes
   {
     "installed": {
       "client_id": "209356685171-fg8ltc0308m1rmo50d20oob7j66ka274.apps.googleusercontent.com",
       "client_secret": "GOCSPX-[REDACTED]",  // ❌ Plaintext in repo
       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
       ...
     }
   }
   ```

2. **Plaintext Token Storage**
   ```python
   # token.json contains OAuth refresh tokens in plaintext
   # File size: 1,038 bytes - includes access tokens, refresh tokens
   ```

3. **Default Secret Key**
   ```python
   # config.py:28
   SECRET_KEY: str = "your-secret-key-change-this-in-production"
   ```

4. **No HTTPS Enforcement**
   - Development server runs on HTTP only
   - No redirect from HTTP to HTTPS
   - Medical images transmitted unencrypted

5. **Unencrypted Medical Data at Rest**
   - Segmentation files stored as plaintext .json
   - Mask data stored as unencrypted .npy files
   - 252MB of medical data unprotected

**Remediation:**

```python
# 1. Use environment variables for all secrets
# .env (NEVER commit this file)
SECRET_KEY=<generate-with-openssl-rand-hex-32>
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
DATABASE_URL=postgresql://user:pass@host/db
ENCRYPTION_KEY=<aes-256-key>

# 2. Encrypt credentials at rest
from cryptography.fernet import Fernet
import os

def encrypt_credentials(creds: dict) -> bytes:
    key = os.getenv("ENCRYPTION_KEY").encode()
    f = Fernet(key)
    return f.encrypt(json.dumps(creds).encode())

def decrypt_credentials(encrypted: bytes) -> dict:
    key = os.getenv("ENCRYPTION_KEY").encode()
    f = Fernet(key)
    return json.loads(f.decrypt(encrypted))

# 3. Use secrets manager
import boto3

def get_secret(secret_name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

# 4. Enforce HTTPS
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

if not settings.DEBUG:
    app.add_middleware(HTTPSRedirectMiddleware)

# 5. Add security headers
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["medical-viewer.example.com"])
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET, https_only=True)

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response
```

### A03:2021 – Injection
**Risk Level:** ⚠️ **MEDIUM**

**Vulnerabilities Found:**

1. **No SQL Injection Risk** (No database currently)
2. **Potential Path Traversal**
   ```python
   # segmentation_service.py - File path handling
   metadata_path = self.storage_path / f"{segmentation_id}.json"

   # If segmentation_id = "../../../etc/passwd"
   # Could lead to path traversal
   ```

3. **Command Injection Risk (Matplotlib)**
   ```python
   # imaging_service.py - User-controlled parameters passed to matplotlib
   # Could potentially inject malicious LaTeX code if not sanitized
   ```

**Remediation:**

```python
# 1. Validate and sanitize file paths
import re
from pathlib import Path

def validate_segmentation_id(seg_id: str) -> str:
    # Only allow alphanumeric and hyphens (UUID format)
    if not re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', seg_id):
        raise ValueError("Invalid segmentation ID format")
    return seg_id

# 2. Use safe path joining
def get_metadata_path(segmentation_id: str) -> Path:
    seg_id = validate_segmentation_id(segmentation_id)
    metadata_path = self.storage_path / f"{seg_id}.json"

    # Ensure path is within storage directory
    if not metadata_path.resolve().is_relative_to(self.storage_path.resolve()):
        raise ValueError("Path traversal attempt detected")

    return metadata_path

# 3. Sanitize matplotlib inputs
def sanitize_colormap(colormap: str) -> str:
    ALLOWED_COLORMAPS = {'gray', 'hot', 'jet', 'viridis', 'plasma', 'inferno', 'magma', 'cividis', 'bone'}
    if colormap not in ALLOWED_COLORMAPS:
        raise ValueError(f"Invalid colormap. Allowed: {ALLOWED_COLORMAPS}")
    return colormap
```

### A04:2021 – Insecure Design
**Risk Level:** ⚠️ **MEDIUM**

**Findings:**

1. **No Rate Limiting**
   - API can be overwhelmed with requests
   - No protection against DoS attacks
   - Potential for resource exhaustion

2. **File-Based Storage Design**
   - Not scalable beyond single server
   - No ACID guarantees
   - Race conditions possible in concurrent access

3. **In-Memory Segmentation Cache**
   - Not distributed
   - Lost on restart
   - Memory exhaustion risk

**Remediation:**

```python
# 1. Add rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@router.get("/list")
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def list_segmentations(request: Request, ...):
    pass

# 2. Migrate to database
# Use PostgreSQL with proper indexing
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Segmentation(Base):
    __tablename__ = "segmentations"

    id = Column(String, primary_key=True)
    file_id = Column(String, nullable=False, index=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    metadata = Column(JSON, nullable=False)

    # Add indexes
    __table_args__ = (
        Index('idx_file_owner', 'file_id', 'owner_id'),
    )

# 3. Use distributed cache
import redis.asyncio as redis

class SegmentationService:
    def __init__(self):
        self.redis = redis.from_url(settings.REDIS_URL)

    async def cache_segmentation(self, seg_id: str, data: bytes):
        await self.redis.setex(
            f"seg:{seg_id}",
            3600,  # 1 hour TTL
            data
        )
```

### A05:2021 – Security Misconfiguration
**Risk Level:** 🔴 **CRITICAL**

**Vulnerabilities Found:**

1. **Debug Mode Enabled in Production**
   ```python
   # config.py:12
   DEBUG: bool = True  # ❌ Default is True
   ```

2. **Overly Permissive CORS**
   ```python
   allow_methods=["*"]
   allow_headers=["*"]
   ```

3. **Default Error Messages**
   - Stack traces exposed to users
   - Sensitive information in error responses
   - No error sanitization

4. **Missing Security Headers**
   - No CSP (Content Security Policy)
   - No HSTS (HTTP Strict Transport Security)
   - No X-Frame-Options
   - No X-Content-Type-Options

5. **Exposed Sensitive Endpoints**
   ```python
   # /api/docs and /api/redoc are public
   # In production, should be restricted
   ```

**Remediation:**

```python
# 1. Disable debug in production
DEBUG: bool = False  # Set via environment variable

# 2. Restrict API docs in production
if settings.DEBUG:
    app = FastAPI(docs_url="/api/docs", redoc_url="/api/redoc")
else:
    app = FastAPI(docs_url=None, redoc_url=None)  # Disable in production

# 3. Custom error handling
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    # Log the actual error
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # Return sanitized response
    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "type": type(exc).__name__}
        )
    else:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

# 4. Security headers middleware (shown previously)
# 5. Environment-specific configuration
class ProductionSettings(Settings):
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = ["https://medical-viewer.example.com"]
    LOG_LEVEL: str = "WARNING"
```

### A06:2021 – Vulnerable and Outdated Components
**Risk Level:** ⚠️ **MEDIUM**

**Analysis:**
```bash
# Backend Dependencies (requirements.txt - 47 packages)
fastapi==0.115.0          # ✅ Latest stable (Nov 2024)
uvicorn==0.32.0           # ✅ Latest stable
pydantic==2.9.0           # ✅ Latest stable
pydicom==2.4.4            # ✅ Current
nibabel==5.3.0            # ✅ Latest
python-jose==3.3.0        # ⚠️ Last updated 2021 (consider PyJWT)
passlib==1.7.4            # ⚠️ Last updated 2020

# Frontend Dependencies
react==18.3.1             # ✅ Latest
axios==1.7.7              # ✅ Current
three==0.169.0            # ✅ Latest
vite==5.4.8               # ✅ Latest
```

**Recommendations:**

```bash
# 1. Set up automated dependency scanning
# Add to .github/workflows/security.yml
name: Security Scan
on: [push, pull_request]
jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Snyk
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
      - name: Safety check
        run: |
          pip install safety
          safety check --json

# 2. Add dependency update automation
# dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule:
      interval: "weekly"
  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"

# 3. Use lock files
pip freeze > requirements.lock
npm ci  # Uses package-lock.json

# 4. Consider replacing outdated packages
python-jose → PyJWT (more actively maintained)
passlib → argon2-cffi (modern password hashing)
```

### A07:2021 – Identification and Authentication Failures
**Risk Level:** 🔴 **CRITICAL**

**Vulnerabilities Found:**

1. **No User Authentication**
   - No login system
   - No user registration
   - No password authentication
   - No session management

2. **No Brute Force Protection**
   - No account lockout
   - No CAPTCHA
   - No rate limiting on auth endpoints (because they don't exist)

3. **No Multi-Factor Authentication**
4. **No Password Recovery**
5. **Insecure Credential Storage**
   - Pickle-based token storage (insecure serialization)

**Remediation:** (Comprehensive authentication system needed)

```python
# Complete authentication system implementation

# models/user.py
from sqlalchemy import Column, String, Boolean, DateTime
from passlib.context import CryptContext
import secrets

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    role = Column(String, default="viewer")  # admin, radiologist, technician, viewer
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    mfa_secret = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)

    def verify_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    def is_locked(self) -> bool:
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False

# services/auth_service.py
from datetime import datetime, timedelta
from jose import jwt
import pyotp

class AuthService:
    def __init__(self):
        self.settings = get_settings()

    async def register_user(self, email: str, password: str, full_name: str) -> User:
        # Validate password strength
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters")
        if not any(c.isupper() for c in password):
            raise ValueError("Password must contain uppercase letter")
        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain digit")
        if not any(c in "!@#$%^&*" for c in password):
            raise ValueError("Password must contain special character")

        # Check if user exists
        existing = await db.query(User).filter(User.email == email).first()
        if existing:
            raise ValueError("Email already registered")

        # Create user
        user = User(
            email=email,
            hashed_password=User.hash_password(password),
            full_name=full_name
        )

        db.add(user)
        await db.commit()

        # Send verification email
        await send_verification_email(user)

        return user

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        user = await db.query(User).filter(User.email == email).first()

        if not user:
            # Prevent timing attacks
            User.hash_password("fake_password")
            return None

        # Check if account is locked
        if user.is_locked():
            raise HTTPException(403, "Account is locked due to failed login attempts")

        # Verify password
        if not user.verify_password(password):
            # Increment failed attempts
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
            await db.commit()
            return None

        # Reset failed attempts
        user.failed_login_attempts = 0
        user.last_login = datetime.utcnow()
        await db.commit()

        return user

    def create_access_token(self, user_id: str) -> str:
        expire = datetime.utcnow() + timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode = {
            "sub": user_id,
            "exp": expire,
            "type": "access"
        }
        return jwt.encode(to_encode, self.settings.SECRET_KEY, algorithm=self.settings.ALGORITHM)

    def create_refresh_token(self, user_id: str) -> str:
        expire = datetime.utcnow() + timedelta(days=30)
        to_encode = {
            "sub": user_id,
            "exp": expire,
            "type": "refresh"
        }
        return jwt.encode(to_encode, self.settings.SECRET_KEY, algorithm=self.settings.ALGORITHM)

    async def enable_mfa(self, user: User) -> str:
        """Enable MFA and return setup QR code"""
        secret = pyotp.random_base32()
        user.mfa_secret = secret
        await db.commit()

        # Generate QR code for authenticator app
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name="Medical Imaging Viewer"
        )
        return provisioning_uri

    def verify_mfa(self, user: User, code: str) -> bool:
        if not user.mfa_enabled or not user.mfa_secret:
            return True

        totp = pyotp.TOTP(user.mfa_secret)
        return totp.verify(code, valid_window=1)

# routes/auth.py
@router.post("/register")
async def register(
    email: str = Body(...),
    password: str = Body(...),
    full_name: str = Body(...)
):
    try:
        user = await auth_service.register_user(email, password, full_name)
        return {"message": "Registration successful. Please verify your email."}
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/login")
async def login(
    email: str = Body(...),
    password: str = Body(...),
    mfa_code: Optional[str] = Body(None)
):
    user = await auth_service.authenticate(email, password)
    if not user:
        raise HTTPException(401, "Invalid credentials")

    # Check MFA if enabled
    if user.mfa_enabled:
        if not mfa_code:
            return {"mfa_required": True}
        if not auth_service.verify_mfa(user, mfa_code):
            raise HTTPException(401, "Invalid MFA code")

    access_token = auth_service.create_access_token(user.id)
    refresh_token = auth_service.create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        }
    }
```

### A08:2021 – Software and Data Integrity Failures
**Risk Level:** ⚠️ **MEDIUM**

**Vulnerabilities Found:**

1. **No Code Signing**
2. **Insecure Deserialization (Pickle)**
   ```python
   # drive_service.py:30
   self.creds = pickle.load(token)  # ❌ Dangerous deserialization
   ```

3. **No CI/CD Pipeline Integrity Checks**
4. **No Container Image Scanning**

**Remediation:**

```python
# 1. Replace pickle with secure JSON storage
import json
from google.oauth2.credentials import Credentials

# Don't use pickle
def save_credentials(creds: Credentials, path: str):
    cred_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }
    with open(path, 'w') as f:
        json.dump(cred_data, f)

def load_credentials(path: str) -> Credentials:
    with open(path, 'r') as f:
        cred_data = json.load(f)
    return Credentials(**cred_data)

# 2. Add container image scanning
# .github/workflows/security.yml
- name: Scan Docker image
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: 'medical-imaging-viewer:latest'
    format: 'sarif'
    output: 'trivy-results.sarif'

# 3. Sign commits
git config --global commit.gpgsign true

# 4. Verify dependencies integrity
pip install --require-hashes -r requirements.txt
npm ci --audit
```

### A09:2021 – Security Logging and Monitoring Failures
**Risk Level:** ⚠️ **MEDIUM**

**Vulnerabilities Found:**

1. **Insufficient Logging**
   - No user activity logging
   - No failed login attempt logging
   - No access logs for medical data
   - No security event logging

2. **No Centralized Logging**
3. **No Real-Time Monitoring**
4. **No Alerting System**
5. **No Audit Trail**

**HIPAA Requirement:** 45 CFR § 164.312(b) - Audit controls to record and examine activity in information systems containing PHI.

**Remediation:**

```python
# Complete logging implementation

# services/audit_service.py
from enum import Enum
from typing import Optional
import logging
from datetime import datetime

class AuditEventType(str, Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    IMAGE_VIEWED = "image_viewed"
    IMAGE_DOWNLOADED = "image_downloaded"
    SEGMENTATION_CREATED = "segmentation_created"
    SEGMENTATION_MODIFIED = "segmentation_modified"
    SEGMENTATION_DELETED = "segmentation_deleted"
    SEGMENTATION_VIEWED = "segmentation_viewed"
    USER_CREATED = "user_created"
    USER_MODIFIED = "user_modified"
    PERMISSION_DENIED = "permission_denied"
    DATA_EXPORTED = "data_exported"

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    event_type = Column(String, nullable=False, index=True)
    user_id = Column(String, index=True)
    user_email = Column(String)
    ip_address = Column(String)
    user_agent = Column(String)
    resource_type = Column(String)  # e.g., "segmentation", "image"
    resource_id = Column(String)
    action = Column(String)  # e.g., "create", "read", "update", "delete"
    success = Column(Boolean, default=True)
    details = Column(JSON)

    __table_args__ = (
        Index('idx_audit_user_time', 'user_id', 'timestamp'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
    )

class AuditService:
    @staticmethod
    async def log_event(
        event_type: AuditEventType,
        user: Optional[User],
        request: Request,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        success: bool = True,
        details: Optional[dict] = None
    ):
        audit_log = AuditLog(
            id=str(uuid.uuid4()),
            event_type=event_type.value,
            user_id=user.id if user else None,
            user_email=user.email if user else None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            success=success,
            details=details
        )

        db.add(audit_log)
        await db.commit()

        # Also log to structured logger for external systems
        logger = logging.getLogger("audit")
        logger.info(
            "Audit event",
            extra={
                "event_type": event_type.value,
                "user_id": user.id if user else None,
                "user_email": user.email if user else None,
                "ip_address": request.client.host,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                "success": success
            }
        )

# middleware/audit_middleware.py
from starlette.middleware.base import BaseHTTPMiddleware

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Log all API requests
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        logger.info(
            "API Request",
            extra={
                "method": request.method,
                "url": str(request.url),
                "status_code": response.status_code,
                "process_time": process_time,
                "ip_address": request.client.host
            }
        )

        return response

# Add to main.py
app.add_middleware(AuditMiddleware)

# Configure structured logging
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Use in routes
@router.get("/{segmentation_id}")
async def get_segmentation(
    segmentation_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    await audit_service.log_event(
        AuditEventType.SEGMENTATION_VIEWED,
        user=current_user,
        request=request,
        resource_type="segmentation",
        resource_id=segmentation_id,
        action="read",
        success=True
    )

    return await segmentation_service.get_segmentation(segmentation_id)

# Set up monitoring with Prometheus
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)

# Set up alerts (example with Sentry)
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    integrations=[FastApiIntegration()],
    traces_sample_rate=0.1,
    environment=settings.ENVIRONMENT
)
```

### A10:2021 – Server-Side Request Forgery (SSRF)
**Risk Level:** ⚠️ **LOW**

**Potential Vulnerabilities:**
- Google Drive API integration could be exploited if not properly validated
- Image processing could be exploited with malicious image URLs

**Remediation:**

```python
# Validate all external URLs
from urllib.parse import urlparse

ALLOWED_SCHEMES = {'https'}
ALLOWED_HOSTS = {'www.googleapis.com', 'drive.google.com'}

def validate_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError("Only HTTPS URLs allowed")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Host {parsed.hostname} not allowed")
    return True

# Use whitelist for Drive API endpoints
GOOGLE_API_ENDPOINTS = {
    'drive.files.list': 'https://www.googleapis.com/drive/v3/files',
    'drive.files.get': 'https://www.googleapis.com/drive/v3/files/{id}'
}
```

---

## 3. HIPAA COMPLIANCE ASSESSMENT

**Status:** ❌ **NON-COMPLIANT**

If this application handles Protected Health Information (PHI) for US patients, it must comply with HIPAA regulations. Current status:

### HIPAA Security Rule - Technical Safeguards

#### § 164.312(a)(1) - Access Control
**Status:** ❌ **NON-COMPLIANT**

**Requirements:**
- Unique user identification (R) ❌ Not implemented
- Emergency access procedure (R) ❌ Not documented
- Automatic logoff (A) ❌ Not implemented
- Encryption and decryption (A) ❌ Not implemented

**Required Implementation:**

```python
# 1. Session timeout
from fastapi import Request, Response
from datetime import datetime, timedelta

SESSION_TIMEOUT_MINUTES = 15

@app.middleware("http")
async def session_timeout_middleware(request: Request, call_next):
    if "session" in request.state:
        last_activity = request.state.session.get("last_activity")
        if last_activity:
            last_activity_time = datetime.fromisoformat(last_activity)
            if datetime.utcnow() - last_activity_time > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                # Session expired
                return Response(
                    content=json.dumps({"detail": "Session expired"}),
                    status_code=401
                )
        request.state.session["last_activity"] = datetime.utcnow().isoformat()

    return await call_next(request)

# 2. Emergency access
class EmergencyAccess:
    @staticmethod
    async def grant_break_glass_access(
        user: User,
        patient_id: str,
        reason: str,
        approver: User
    ):
        """
        Provide emergency access to patient data with full audit trail.
        Requires subsequent review and justification.
        """
        # Log emergency access
        await audit_service.log_event(
            AuditEventType.EMERGENCY_ACCESS,
            user=user,
            details={
                "patient_id": patient_id,
                "reason": reason,
                "approver_id": approver.id,
                "approver_email": approver.email
            }
        )

        # Send alert to security team
        await send_security_alert(
            f"Emergency access granted to user {user.email} for patient {patient_id}"
        )

        # Grant temporary access
        await grant_temporary_permission(user.id, patient_id, duration_hours=24)
```

#### § 164.312(a)(2)(i) - Unique User Identification
**Status:** ❌ **NON-COMPLIANT**

**Remediation:** Implement complete user authentication system (shown in A07 remediation)

#### § 164.312(b) - Audit Controls
**Status:** ❌ **NON-COMPLIANT**

**Requirements:**
- Record and examine activity in systems containing PHI

**Remediation:** Implement comprehensive audit logging (shown in A09 remediation)

**Required Audit Events:**
- User login/logout
- PHI access (view, download, export)
- PHI modification
- PHI deletion
- Failed access attempts
- Administrative actions
- Permission changes

#### § 164.312(c)(1) - Integrity
**Status:** ⚠️ **PARTIALLY COMPLIANT**

**Requirements:**
- Implement policies to ensure PHI is not improperly altered or destroyed

**Current Implementation:**
- ✅ File-based storage has some integrity through filesystem
- ❌ No checksums/hashes for data integrity verification
- ❌ No version control for medical data modifications

**Remediation:**

```python
import hashlib
from datetime import datetime

class DataIntegrity:
    @staticmethod
    def calculate_checksum(file_path: Path) -> str:
        """Calculate SHA-256 checksum of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @staticmethod
    async def save_segmentation_with_integrity(seg_id: str, data: bytes):
        # Save data
        file_path = storage_path / f"{seg_id}.npy"
        with open(file_path, 'wb') as f:
            f.write(data)

        # Calculate checksum
        checksum = DataIntegrity.calculate_checksum(file_path)

        # Store checksum in database
        integrity_record = DataIntegrityRecord(
            resource_id=seg_id,
            resource_type="segmentation",
            checksum=checksum,
            algorithm="SHA-256",
            created_at=datetime.utcnow()
        )
        db.add(integrity_record)
        await db.commit()

    @staticmethod
    async def verify_integrity(seg_id: str) -> bool:
        """Verify file hasn't been tampered with"""
        file_path = storage_path / f"{seg_id}.npy"
        current_checksum = DataIntegrity.calculate_checksum(file_path)

        record = await db.query(DataIntegrityRecord).filter(
            DataIntegrityRecord.resource_id == seg_id
        ).first()

        if not record:
            raise ValueError("No integrity record found")

        if current_checksum != record.checksum:
            # Data has been tampered with!
            await audit_service.log_event(
                AuditEventType.INTEGRITY_VIOLATION,
                details={"resource_id": seg_id, "expected": record.checksum, "actual": current_checksum}
            )
            return False

        return True

# Run integrity checks periodically
async def scheduled_integrity_check():
    """Run daily integrity verification on all medical data"""
    segmentations = await db.query(Segmentation).all()
    violations = []

    for seg in segmentations:
        is_valid = await DataIntegrity.verify_integrity(seg.id)
        if not is_valid:
            violations.append(seg.id)

    if violations:
        await send_security_alert(
            f"Integrity violations detected: {len(violations)} files compromised"
        )
```

#### § 164.312(d) - Person or Entity Authentication
**Status:** ❌ **NON-COMPLIANT**

**Remediation:** Implement authentication system (A07 remediation)

#### § 164.312(e)(1) - Transmission Security
**Status:** ❌ **NON-COMPLIANT**

**Requirements:**
- Integrity controls (A)
- Encryption (A)

**Current State:**
- ❌ No TLS/HTTPS
- ❌ Medical images transmitted unencrypted
- ❌ No VPN requirement for remote access

**Remediation:**

```python
# 1. Enforce HTTPS
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

if not settings.DEBUG:
    app.add_middleware(HTTPSRedirectMiddleware)

# 2. Configure TLS
# In production, use Let's Encrypt or commercial certificate
# Minimum TLS 1.2, prefer TLS 1.3

# uvicorn configuration for HTTPS
uvicorn.run(
    "app.main:app",
    host="0.0.0.0",
    port=443,
    ssl_keyfile="/etc/ssl/private/key.pem",
    ssl_certfile="/etc/ssl/certs/cert.pem",
    ssl_version=ssl.PROTOCOL_TLSv1_2,
    ssl_ciphers="ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS"
)

# 3. Implement end-to-end encryption for sensitive operations
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

class TransmissionSecurity:
    @staticmethod
    def encrypt_data(data: bytes) -> tuple[bytes, bytes]:
        """Encrypt data for transmission using AES-GCM"""
        key = os.getenv("TRANSMISSION_KEY").encode()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce, ciphertext

    @staticmethod
    def decrypt_data(nonce: bytes, ciphertext: bytes) -> bytes:
        """Decrypt received data"""
        key = os.getenv("TRANSMISSION_KEY").encode()
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
```

### HIPAA Privacy Rule

#### § 164.502(a) - Minimum Necessary
**Status:** ⚠️ **PARTIALLY COMPLIANT**

**Requirements:**
- Use minimum necessary PHI for intended purpose
- Apply to uses, disclosures, and requests

**Current Implementation:**
- ⚠️ API returns full segmentation data (could include PHI)
- ❌ No field-level access control
- ❌ No data minimization in responses

**Remediation:**

```python
# Implement field-level access control
from typing import Set
from pydantic import BaseModel

class ResponseFilter:
    @staticmethod
    def filter_fields(
        data: dict,
        allowed_fields: Set[str],
        user_role: str
    ) -> dict:
        """Return only necessary fields based on user role"""
        role_fields = {
            "viewer": {"id", "description", "created_at", "label_count"},
            "technician": {"id", "description", "created_at", "labels", "total_slices"},
            "radiologist": {"*"},  # All fields
            "admin": {"*"}
        }

        permitted = role_fields.get(user_role, set())
        if "*" in permitted:
            return data

        return {k: v for k, v in data.items() if k in permitted}

@router.get("/{segmentation_id}")
async def get_segmentation(
    segmentation_id: str,
    current_user: User = Depends(get_current_user)
):
    seg = await segmentation_service.get_segmentation(segmentation_id)

    # Filter response based on user role
    filtered_data = ResponseFilter.filter_fields(
        seg.dict(),
        allowed_fields=set(seg.dict().keys()),
        user_role=current_user.role
    )

    return filtered_data
```

#### § 164.530(i) - Sanctions
**Status:** ❌ **NON-COMPLIANT**

**Requirements:**
- Sanctions policy for workforce members who violate policies
- Apply appropriate sanctions (warnings, suspension, termination)

**Remediation:**

```python
# Implement automated policy violation detection

class PolicyViolation(Base):
    __tablename__ = "policy_violations"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    violation_type = Column(String)  # unauthorized_access, data_breach, etc.
    severity = Column(String)  # low, medium, high, critical
    detected_at = Column(DateTime, default=datetime.utcnow)
    details = Column(JSON)
    action_taken = Column(String)  # warning, suspension, termination
    reviewed_by = Column(String, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)

class ComplianceMonitor:
    @staticmethod
    async def detect_policy_violations():
        """Automatically detect potential policy violations"""

        # Example: Detect unusual access patterns
        recent_accesses = await db.query(AuditLog).filter(
            AuditLog.event_type == AuditEventType.IMAGE_VIEWED,
            AuditLog.timestamp > datetime.utcnow() - timedelta(hours=1)
        ).all()

        user_access_counts = {}
        for access in recent_accesses:
            user_access_counts[access.user_id] = user_access_counts.get(access.user_id, 0) + 1

        # Flag users accessing >100 images in 1 hour (potential data exfiltration)
        for user_id, count in user_access_counts.items():
            if count > 100:
                await create_policy_violation(
                    user_id=user_id,
                    violation_type="excessive_access",
                    severity="high",
                    details={"access_count": count, "timeframe": "1 hour"}
                )

                # Automatically suspend user pending review
                user = await db.query(User).filter(User.id == user_id).first()
                user.is_active = False
                await db.commit()

                # Alert security team
                await send_security_alert(
                    f"User {user.email} suspended due to excessive access ({count} images in 1 hour)"
                )
```

---

## 4. ADDITIONAL SECURITY RECOMMENDATIONS

### 4.1 Database Implementation
**Priority:** 🔴 **CRITICAL** (P0)

**Current:** File-based storage (252MB of segmentation data)
**Required:** PostgreSQL or MongoDB with proper schema design

**Implementation Plan:**

```sql
-- PostgreSQL Schema

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    mfa_enabled BOOLEAN DEFAULT FALSE,
    mfa_secret VARCHAR(255),
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    CONSTRAINT chk_role CHECK (role IN ('admin', 'radiologist', 'technician', 'viewer'))
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- Medical images table
CREATE TABLE medical_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drive_file_id VARCHAR(255) UNIQUE NOT NULL,
    filename VARCHAR(500) NOT NULL,
    file_format VARCHAR(50) NOT NULL, -- 'DICOM', 'NIFTI'
    patient_id VARCHAR(255),  -- De-identified patient ID
    study_date DATE,
    modality VARCHAR(50),  -- MRI, CT, etc.
    series_description TEXT,
    upload_user_id UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,
    checksum VARCHAR(64) NOT NULL  -- SHA-256
);

CREATE INDEX idx_images_drive_id ON medical_images(drive_file_id);
CREATE INDEX idx_images_patient ON medical_images(patient_id);
CREATE INDEX idx_images_modality ON medical_images(modality);

-- Segmentations table
CREATE TABLE segmentations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    image_id UUID REFERENCES medical_images(id) ON DELETE CASCADE,
    owner_id UUID REFERENCES users(id),
    description TEXT,
    status VARCHAR(50) DEFAULT 'draft',  -- draft, completed, verified
    storage_path VARCHAR(500) NOT NULL,
    file_format VARCHAR(50) NOT NULL,  -- 'npy', 'dicom_seg', 'nifti'
    total_slices INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_by UUID REFERENCES users(id),
    verified_at TIMESTAMP,
    labels JSONB NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    CONSTRAINT chk_status CHECK (status IN ('draft', 'completed', 'verified'))
);

CREATE INDEX idx_seg_image ON segmentations(image_id);
CREATE INDEX idx_seg_owner ON segmentations(owner_id);
CREATE INDEX idx_seg_status ON segmentations(status);

-- Audit logs
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(100) NOT NULL,
    user_id UUID REFERENCES users(id),
    user_email VARCHAR(255),
    ip_address VARCHAR(45),
    user_agent TEXT,
    resource_type VARCHAR(100),
    resource_id UUID,
    action VARCHAR(50),
    success BOOLEAN DEFAULT TRUE,
    details JSONB
);

-- Partition by month for performance
CREATE TABLE audit_logs_2025_11 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX idx_audit_user ON audit_logs(user_id, timestamp DESC);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_event ON audit_logs(event_type);

-- Access permissions table
CREATE TABLE resource_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    resource_type VARCHAR(100) NOT NULL,
    resource_id UUID NOT NULL,
    permission VARCHAR(50) NOT NULL,  -- read, write, delete, admin
    granted_by UUID REFERENCES users(id),
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    CONSTRAINT chk_permission CHECK (permission IN ('read', 'write', 'delete', 'admin'))
);

CREATE UNIQUE INDEX idx_perm_unique ON resource_permissions(user_id, resource_type, resource_id, permission);
CREATE INDEX idx_perm_user ON resource_permissions(user_id);
CREATE INDEX idx_perm_resource ON resource_permissions(resource_type, resource_id);

-- Session management
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_session_user ON sessions(user_id);
CREATE INDEX idx_session_token ON sessions(token_hash);
CREATE INDEX idx_session_expires ON sessions(expires_at);

-- Data retention policy enforcement
CREATE OR REPLACE FUNCTION enforce_data_retention()
RETURNS TRIGGER AS $$
BEGIN
    -- Delete audit logs older than 7 years (HIPAA requirement)
    DELETE FROM audit_logs
    WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '7 years';

    -- Delete expired sessions
    DELETE FROM sessions
    WHERE expires_at < CURRENT_TIMESTAMP;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_data_retention
    AFTER INSERT ON audit_logs
    EXECUTE FUNCTION enforce_data_retention();

-- Row-level security
ALTER TABLE segmentations ENABLE ROW LEVEL SECURITY;

CREATE POLICY segmentation_owner_policy ON segmentations
    FOR ALL
    USING (owner_id = current_setting('app.current_user_id')::UUID);

CREATE POLICY segmentation_admin_policy ON segmentations
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users
            WHERE id = current_setting('app.current_user_id')::UUID
            AND role = 'admin'
        )
    );
```

### 4.2 Infrastructure Security
**Priority:** 🔴 **CRITICAL** (P0)

```yaml
# docker-compose.production.yml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.production
    environment:
      - DEBUG=False
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - SECRET_KEY=${SECRET_KEY}  # From secrets manager
    secrets:
      - database_password
      - jwt_secret
      - encryption_key
    networks:
      - internal
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
      restart_policy:
        condition: on-failure
        max_attempts: 3
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_PASSWORD_FILE=/run/secrets/database_password
      - POSTGRES_DB=medical_imaging
    secrets:
      - database_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    networks:
      - internal
    deploy:
      placement:
        constraints:
          - node.role == manager
    # Automated backups
    command: >
      bash -c "
        postgres &
        while true; do
          sleep 86400
          pg_dump -U postgres medical_imaging > /backups/backup_$(date +%Y%m%d_%H%M%S).sql
          find /backups -name 'backup_*.sql' -mtime +30 -delete
        done
      "

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 2gb --maxmemory-policy allkeys-lru
    secrets:
      - redis_password
    networks:
      - internal
    volumes:
      - redis_data:/data

  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    networks:
      - internal
      - external
    depends_on:
      - backend

  # Security scanning
  trivy:
    image: aquasec/trivy:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: image --severity HIGH,CRITICAL medical-imaging-backend:latest

networks:
  internal:
    driver: overlay
    internal: true
  external:
    driver: overlay

volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind,encrypted  # Encrypted volume
      device: /encrypted-storage/postgres
  redis_data:

secrets:
  database_password:
    external: true
  jwt_secret:
    external: true
  encryption_key:
    external: true
  redis_password:
    external: true
```

```nginx
# nginx.conf - Production configuration
upstream backend {
    least_conn;
    server backend:8000 max_fails=3 fail_timeout=30s;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name medical-viewer.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name medical-viewer.example.com;

    # TLS Configuration
    ssl_certificate /etc/letsencrypt/live/medical-viewer.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/medical-viewer.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https://www.googleapis.com; frame-ancestors 'none';" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;
    limit_conn_zone $binary_remote_addr zone=addr:10m;
    limit_conn addr 10;

    # Request size limits
    client_max_body_size 500M;
    client_body_timeout 300s;

    # Logging
    access_log /var/log/nginx/access.log combined;
    error_log /var/log/nginx/error.log warn;

    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # Timeouts for large file uploads
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;

        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # Health check endpoint (no auth)
    location = /api/health {
        proxy_pass http://backend;
        access_log off;
    }

    # Block access to hidden files
    location ~ /\. {
        deny all;
        return 404;
    }
}
```

### 4.3 CI/CD Pipeline
**Priority:** ⚠️ **HIGH** (P1)

```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

env:
  PYTHON_VERSION: '3.11'
  NODE_VERSION: '18'

jobs:
  # Security scanning
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'

      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'

      - name: Run Bandit security linter
        run: |
          pip install bandit[toml]
          bandit -r backend/ -f json -o bandit-report.json

      - name: Run Safety check
        run: |
          pip install safety
          safety check --json --file backend/requirements.txt

      - name: Run Snyk
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        with:
          args: --severity-threshold=high

  # Backend tests
  backend-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'

      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio

      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql://postgres:test_password@localhost/test_db
          REDIS_URL: redis://localhost:6379/0
        run: |
          cd backend
          pytest tests/ --cov=app --cov-report=xml --cov-report=html

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./backend/coverage.xml
          flags: backend
          fail_ci_if_error: true

      - name: Check coverage threshold
        run: |
          cd backend
          coverage report --fail-under=80

  # Frontend tests
  frontend-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Node.js
        uses: actions/setup-node@v3
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: |
          cd frontend
          npm ci

      - name: Run linter
        run: |
          cd frontend
          npm run lint

      - name: Run TypeScript check
        run: |
          cd frontend
          npx tsc --noEmit

      - name: Run tests
        run: |
          cd frontend
          npm test -- --coverage

      - name: Build
        run: |
          cd frontend
          npm run build

  # Code quality
  code-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run Black formatter check
        run: |
          pip install black
          black --check backend/

      - name: Run isort check
        run: |
          pip install isort
          isort --check-only backend/

      - name: Run mypy type checker
        run: |
          pip install mypy
          mypy backend/app

      - name: Run flake8
        run: |
          pip install flake8
          flake8 backend/ --max-line-length=100

  # Build and push Docker images
  build-docker:
    needs: [security-scan, backend-test, frontend-test, code-quality]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Login to DockerHub
        uses: docker/login-action@v2
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and push backend
        uses: docker/build-push-action@v4
        with:
          context: ./backend
          push: true
          tags: |
            medical-imaging/backend:latest
            medical-imaging/backend:${{ github.sha }}
          cache-from: type=registry,ref=medical-imaging/backend:buildcache
          cache-to: type=registry,ref=medical-imaging/backend:buildcache,mode=max

      - name: Build and push frontend
        uses: docker/build-push-action@v4
        with:
          context: ./frontend
          push: true
          tags: |
            medical-imaging/frontend:latest
            medical-imaging/frontend:${{ github.sha }}

      - name: Scan Docker images
        run: |
          docker run --rm aquasec/trivy image medical-imaging/backend:latest
          docker run --rm aquasec/trivy image medical-imaging/frontend:latest

  # Deploy to production
  deploy-production:
    needs: [build-docker]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment:
      name: production
      url: https://medical-viewer.example.com
    steps:
      - name: Deploy to production
        run: |
          # Add deployment script here
          echo "Deploying to production..."
```

### 4.4 Testing Implementation
**Priority:** ⚠️ **HIGH** (P1)

**Target:** 80% code coverage minimum

```python
# backend/tests/conftest.py
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.models.base import Base

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost/test_medical_imaging"

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def engine():
    """Create test database engine"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session(engine):
    """Create database session for tests"""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()

@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)

@pytest.fixture
async def test_user(db_session):
    """Create test user"""
    from app.models.user import User

    user = User(
        email="test@example.com",
        hashed_password=User.hash_password("Test123!@#"),
        full_name="Test User",
        role="radiologist"
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return user

@pytest.fixture
def auth_headers(test_user):
    """Create authentication headers"""
    from app.services.auth_service import AuthService

    auth_service = AuthService()
    token = auth_service.create_access_token(test_user.id)

    return {"Authorization": f"Bearer {token}"}

# backend/tests/test_auth.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_register_user(client):
    """Test user registration"""
    response = client.post("/api/v1/auth/register", json={
        "email": "newuser@example.com",
        "password": "SecurePass123!@#",
        "full_name": "New User"
    })

    assert response.status_code == 200
    assert "message" in response.json()

@pytest.mark.asyncio
async def test_register_weak_password(client):
    """Test registration with weak password"""
    response = client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "weak",
        "full_name": "Test"
    })

    assert response.status_code == 400
    assert "Password must be at least 12 characters" in response.json()["detail"]

@pytest.mark.asyncio
async def test_login_success(client, test_user):
    """Test successful login"""
    response = client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "Test123!@#"
    })

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == test_user.email

@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    """Test login with invalid credentials"""
    response = client.post("/api/v1/auth/login", json={
        "email": "wrong@example.com",
        "password": "wrongpassword"
    })

    assert response.status_code == 401

@pytest.mark.asyncio
async def test_account_lockout(client, test_user):
    """Test account lockout after failed attempts"""
    for _ in range(5):
        client.post("/api/v1/auth/login", json={
            "email": test_user.email,
            "password": "wrongpassword"
        })

    response = client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "Test123!@#"
    })

    assert response.status_code == 403
    assert "locked" in response.json()["detail"].lower()

# backend/tests/test_segmentation.py
@pytest.mark.asyncio
async def test_create_segmentation(client, auth_headers, test_user):
    """Test creating a segmentation"""
    response = client.post(
        "/api/v1/segmentation/create",
        headers=auth_headers,
        json={
            "file_id": "test_file_id",
            "image_shape": {"rows": 256, "columns": 256, "slices": 40},
            "description": "Test segmentation"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "segmentation_id" in data
    assert data["file_id"] == "test_file_id"

@pytest.mark.asyncio
async def test_create_segmentation_unauthorized(client):
    """Test creating segmentation without authentication"""
    response = client.post("/api/v1/segmentation/create", json={
        "file_id": "test",
        "image_shape": {"rows": 256, "columns": 256, "slices": 40}
    })

    assert response.status_code == 401

@pytest.mark.asyncio
async def test_list_segmentations(client, auth_headers, test_user, db_session):
    """Test listing segmentations"""
    # Create test segmentations
    from app.models.segmentation import Segmentation

    seg1 = Segmentation(
        file_id="file1",
        owner_id=test_user.id,
        description="Seg 1"
    )
    seg2 = Segmentation(
        file_id="file1",
        owner_id=test_user.id,
        description="Seg 2"
    )

    db_session.add_all([seg1, seg2])
    await db_session.commit()

    response = client.get(
        "/api/v1/segmentation/list?file_id=file1",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

@pytest.mark.asyncio
async def test_delete_segmentation_not_owner(client, auth_headers, db_session):
    """Test deleting segmentation owned by another user"""
    from app.models.segmentation import Segmentation
    from app.models.user import User

    # Create another user
    other_user = User(
        email="other@example.com",
        hashed_password=User.hash_password("Pass123!@#")
    )
    db_session.add(other_user)
    await db_session.commit()

    # Create segmentation owned by other user
    seg = Segmentation(
        file_id="file1",
        owner_id=other_user.id,
        description="Other's seg"
    )
    db_session.add(seg)
    await db_session.commit()

    # Try to delete as current user
    response = client.delete(
        f"/api/v1/segmentation/{seg.id}",
        headers=auth_headers
    )

    assert response.status_code == 403

# backend/tests/test_security.py
def test_security_headers(client):
    """Test security headers are present"""
    response = client.get("/api/health")

    assert "Strict-Transport-Security" in response.headers
    assert "X-Content-Type-Options" in response.headers
    assert "X-Frame-Options" in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"

def test_cors_headers(client):
    """Test CORS is properly configured"""
    response = client.options(
        "/api/v1/segmentation/list",
        headers={"Origin": "https://evil.com"}
    )

    # Should not allow evil.com
    assert "Access-Control-Allow-Origin" not in response.headers

def test_rate_limiting(client):
    """Test rate limiting is enforced"""
    # Make many requests quickly
    responses = []
    for _ in range(100):
        responses.append(client.get("/api/v1/segmentation/list"))

    # Some requests should be rate limited
    assert any(r.status_code == 429 for r in responses)
```

### 4.5 Monitoring & Alerting
**Priority:** ⚠️ **HIGH** (P1)

```python
# monitoring/prometheus.py
from prometheus_client import Counter, Histogram, Gauge
import time

# Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

active_segmentations = Gauge(
    'active_segmentations_total',
    'Number of active segmentations in cache'
)

failed_logins_total = Counter(
    'failed_logins_total',
    'Total failed login attempts',
    ['user_email']
)

database_connections = Gauge(
    'database_connections_active',
    'Active database connections'
)

# Middleware
@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time

    http_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code
    ).inc()

    http_request_duration_seconds.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)

    return response

# Alert rules (Prometheus AlertManager)
# alerts.yml
groups:
  - name: medical_imaging
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status_code=~"5.."}[5m]))
          /
          sum(rate(http_requests_total[5m]))
          > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }}"

      # Multiple failed logins (potential brute force)
      - alert: BruteForceAttempt
        expr: |
          sum(increase(failed_logins_total[5m])) by (user_email) > 10
        labels:
          severity: warning
        annotations:
          summary: "Potential brute force attack"
          description: "{{ $labels.user_email }} has {{ $value }} failed logins"

      # Database connection pool exhausted
      - alert: DatabaseConnectionsHigh
        expr: database_connections_active > 90
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Database connection pool nearly exhausted"

      # Slow response times
      - alert: SlowResponses
        expr: |
          histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket[5m])
          ) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "95th percentile response time exceeds 2 seconds"
```

---

## 5. IMPLEMENTATION ROADMAP

### Phase 1: Critical Security Fixes (Week 1-2)
**Effort:** 2-3 developer-weeks

1. **Remove credentials from repository**
   - Remove credentials.json and token.json from git history
   - Add to .gitignore
   - Rotate all secrets

2. **Implement secrets management**
   - Move all secrets to environment variables
   - Set up AWS Secrets Manager / Azure Key Vault
   - Update configuration loading

3. **Implement basic authentication**
   - User registration/login endpoints
   - JWT token generation/validation
   - Password hashing with Argon2

4. **Add HTTPS/TLS**
   - Obtain SSL certificates (Let's Encrypt)
   - Configure nginx with TLS 1.3
   - Enforce HTTPS redirects

5. **Add security headers**
   - Implement HSTS, CSP, X-Frame-Options
   - Configure CORS properly

### Phase 2: Access Control & Authorization (Week 3-4)
**Effort:** 2-3 developer-weeks

1. **Implement RBAC**
   - Define roles (admin, radiologist, technician, viewer)
   - Create permission system
   - Add middleware for authorization checks

2. **Add authentication to all endpoints**
   - Protect all API routes
   - Implement ownership validation
   - Add resource-level permissions

3. **Implement session management**
   - Add session timeouts
   - Implement automatic logoff
   - Add concurrent session limits

### Phase 3: Database & Persistence (Week 5-6)
**Effort:** 3-4 developer-weeks

1. **Set up PostgreSQL**
   - Design schema (see Section 4.1)
   - Implement migrations with Alembic
   - Add database connection pooling

2. **Migrate from file-based storage**
   - Move metadata to database
   - Keep binary data in files/S3
   - Implement data migration scripts

3. **Add data integrity checks**
   - Implement checksums for all medical data
   - Add verification on read
   - Scheduled integrity checks

### Phase 4: Logging & Monitoring (Week 7-8)
**Effort:** 2 developer-weeks

1. **Implement comprehensive audit logging**
   - All user actions
   - All data access
   - Failed authentication attempts

2. **Set up centralized logging**
   - ELK Stack or similar
   - Structured logging
   - Log retention policies

3. **Implement monitoring**
   - Prometheus metrics
   - Grafana dashboards
   - Alert manager configuration

4. **Add error tracking**
   - Sentry integration
   - Performance monitoring

### Phase 5: Testing & Quality (Week 9-10)
**Effort:** 3-4 developer-weeks

1. **Write comprehensive tests**
   - Unit tests (80% coverage target)
   - Integration tests
   - Security tests

2. **Set up CI/CD pipeline**
   - Automated testing
   - Security scanning
   - Automated deployments

3. **Code quality tools**
   - Pre-commit hooks
   - SAST/DAST integration
   - Dependency scanning

### Phase 6: HIPAA Compliance (Week 11-12)
**Effort:** 2-3 developer-weeks

1. **Encryption implementation**
   - Data at rest encryption
   - End-to-end encryption for PHI
   - Key management

2. **Compliance features**
   - Emergency access procedures
   - Breach notification system
   - Data retention policies

3. **Documentation**
   - Security policies
   - Incident response plan
   - Business continuity plan

### Phase 7: Advanced Security (Week 13-14)
**Effort:** 2 developer-weeks

1. **Multi-factor authentication**
   - TOTP support
   - SMS backup codes
   - Recovery procedures

2. **Advanced threat protection**
   - Rate limiting
   - DDoS protection
   - WAF rules

3. **Penetration testing**
   - External security audit
   - Vulnerability remediation

---

## 6. COMPLIANCE CHECKLIST

### ISO 27001 Control Implementation Status

| Control | Description | Status | Priority | Effort |
|---------|-------------|--------|----------|--------|
| A.5.1 | Information security policies | ❌ | P0 | 1 week |
| A.8.1 | Asset inventory | ❌ | P1 | 1 week |
| A.8.2 | Information classification | ❌ | P0 | 1 week |
| A.9.1 | Access control policy | ❌ | P0 | 2 weeks |
| A.9.2 | User access management | ❌ | P0 | 3 weeks |
| A.9.4 | System access control | ❌ | P0 | 2 weeks |
| A.10.1 | Cryptographic controls | ❌ | P0 | 2 weeks |
| A.12.2 | Malware protection | ❌ | P1 | 1 week |
| A.12.3 | Backup | ❌ | P0 | 1 week |
| A.12.4 | Logging and monitoring | ⚠️ | P0 | 2 weeks |
| A.12.6 | Technical vulnerability mgmt | ❌ | P1 | Ongoing |
| A.14.1 | Security in development | ⚠️ | P0 | 3 weeks |
| A.14.2 | Security testing | ❌ | P0 | 3 weeks |
| A.16.1 | Incident management | ❌ | P0 | 2 weeks |
| A.17.1 | Business continuity | ❌ | P1 | 2 weeks |
| A.18.1 | Compliance assessment | ❌ | P1 | 1 week |

**Total Implementation Effort:** ~26-30 developer-weeks (~6-7 months with 1 developer)

### HIPAA Compliance Checklist

| Requirement | Status | Notes |
|-------------|--------|-------|
| Access Control (§164.312(a)(1)) | ❌ | No authentication system |
| Audit Controls (§164.312(b)) | ❌ | No audit logging |
| Integrity (§164.312(c)(1)) | ⚠️ | Partial - need checksums |
| Person/Entity Authentication (§164.312(d)) | ❌ | No user authentication |
| Transmission Security (§164.312(e)(1)) | ❌ | No TLS/encryption |
| Automatic Logoff (§164.312(a)(2)(iii)) | ❌ | No session timeouts |
| Encryption/Decryption (§164.312(a)(2)(iv)) | ❌ | No encryption at rest |
| Emergency Access (§164.312(a)(2)(ii)) | ❌ | No procedure documented |
| Unique User ID (§164.312(a)(2)(i)) | ❌ | No user system |

**HIPAA Compliance Status:** ❌ **0% Compliant** (Critical - must fix before handling PHI)

---

## 7. ESTIMATED COSTS

### Development Costs

| Phase | Duration | Effort | Cost (@ $100/hr) |
|-------|----------|--------|------------------|
| Phase 1: Critical Security | 2 weeks | 80 hours | $8,000 |
| Phase 2: Access Control | 2 weeks | 80 hours | $8,000 |
| Phase 3: Database | 2 weeks | 80 hours | $8,000 |
| Phase 4: Logging/Monitoring | 2 weeks | 80 hours | $8,000 |
| Phase 5: Testing | 2 weeks | 80 hours | $8,000 |
| Phase 6: HIPAA Compliance | 2 weeks | 80 hours | $8,000 |
| Phase 7: Advanced Security | 2 weeks | 80 hours | $8,000 |
| **TOTAL** | **14 weeks** | **560 hours** | **$56,000** |

### Infrastructure Costs (Annual)

| Service | Provider | Monthly | Annual |
|---------|----------|---------|--------|
| Cloud Hosting (2 instances) | AWS/Azure | $200 | $2,400 |
| Database (PostgreSQL) | Managed RDS | $100 | $1,200 |
| Redis Cache | Managed | $50 | $600 |
| SSL Certificates | Let's Encrypt | $0 | $0 |
| Backup Storage (500GB) | S3/Azure Blob | $25 | $300 |
| Monitoring (Datadog/New Relic) | SaaS | $100 | $1,200 |
| Security Scanning (Snyk) | SaaS | $50 | $600 |
| Error Tracking (Sentry) | SaaS | $29 | $348 |
| **TOTAL** | | **$554** | **$6,648** |

### External Services

| Service | Cost | Frequency |
|---------|------|-----------|
| Penetration Testing | $5,000-$15,000 | Annual |
| Security Audit | $10,000-$25,000 | Annual |
| HIPAA Compliance Consultant | $5,000-$10,000 | One-time |
| Legal Review | $2,000-$5,000 | One-time |

**Total First Year Cost:** $78,000 - $116,000

---

## 8. CONCLUSION

### Current State Assessment

The Medical Imaging Viewer application demonstrates **excellent technical foundations** with modern architecture and professional-grade libraries. However, **critical security deficiencies** prevent production deployment in healthcare environments.

**Strengths:**
- ✅ Modern, well-structured codebase
- ✅ Strong architectural separation (routes → services → models)
- ✅ Type safety (Pydantic, TypeScript)
- ✅ Professional medical imaging libraries
- ✅ Docker-ready deployment
- ✅ Comprehensive documentation

**Critical Gaps:**
- ❌ **No user authentication/authorization** - Anyone can access all medical data
- ❌ **Credentials in plaintext** - Severe security vulnerability
- ❌ **No encryption** - Data transmitted and stored unencrypted
- ❌ **Zero test coverage** - No quality assurance
- ❌ **HIPAA non-compliant** - Cannot handle PHI
- ❌ **ISO 27001 non-compliant** - Fails security standards

### Risk Level

**CURRENT RISK: 🔴 CRITICAL**

This application **MUST NOT** be deployed in production for:
- ❌ Real patient data (HIPAA violations)
- ❌ Multi-user environments (no access control)
- ❌ Public internet exposure (no authentication)
- ❌ Regulated industries (compliance failures)

**Acceptable for:**
- ✅ Single-user local development
- ✅ Proof-of-concept demos
- ✅ Educational purposes
- ✅ Research with de-identified data (with encryption added)

### Recommendations Priority Matrix

| Priority | Timeline | Actions |
|----------|----------|---------|
| **P0 - CRITICAL** (Do Now) | Week 1-4 | Remove credentials from repo<br>Implement authentication<br>Add HTTPS/TLS<br>Implement RBAC |
| **P1 - HIGH** (Next) | Week 5-8 | Migrate to database<br>Comprehensive audit logging<br>Test coverage 80%+ |
| **P2 - MEDIUM** (Soon) | Week 9-12 | HIPAA compliance features<br>CI/CD pipeline<br>Monitoring & alerting |
| **P3 - LOW** (Later) | Week 13+ | Advanced security features<br>Performance optimization<br>External audit |

### Path to Production Readiness

To achieve production readiness for healthcare deployment:

1. **Immediate (4 weeks):** Security fundamentals - authentication, encryption, access control
2. **Short-term (8 weeks):** Infrastructure - database, logging, testing
3. **Medium-term (12 weeks):** Compliance - HIPAA controls, audit trails, policies
4. **Long-term (16 weeks):** Advanced features - MFA, monitoring, external audit

**Estimated Timeline:** 16 weeks (4 months)
**Estimated Budget:** $78,000 - $116,000

### Next Steps

1. **Executive Decision:** Approve security remediation budget and timeline
2. **Team Formation:** Assign security engineer and backend developer
3. **Week 1 Actions:**
   - Remove credentials from repository
   - Rotate all secrets
   - Set up development/staging/production environments
   - Begin authentication system implementation
4. **Weekly Reviews:** Track progress against roadmap
5. **Milestone Gates:** Security review before each phase completion

---

## APPENDIX

### A. Glossary

**PHI:** Protected Health Information - any health information that can be linked to an individual (HIPAA definition)

**RBAC:** Role-Based Access Control - access control based on user roles

**TLS:** Transport Layer Security - cryptographic protocol for secure communications

**CSRF:** Cross-Site Request Forgery - attack forcing users to execute unwanted actions

**XSS:** Cross-Site Scripting - injection of malicious scripts into web pages

**SAST:** Static Application Security Testing - analyzing source code for vulnerabilities

**DAST:** Dynamic Application Security Testing - testing running applications

**OWASP:** Open Web Application Security Project

**HIPAA:** Health Insurance Portability and Accountability Act

**ISO 27001:** International standard for information security management

### B. References

1. **OWASP Top 10 2021:** https://owasp.org/Top10/
2. **ISO/IEC 27001:2013:** https://www.iso.org/standard/54534.html
3. **HIPAA Security Rule:** https://www.hhs.gov/hipaa/for-professionals/security/index.html
4. **NIST Cybersecurity Framework:** https://www.nist.gov/cyberframework
5. **CIS Controls:** https://www.cisecurity.org/controls
6. **GDPR (if applicable):** https://gdpr.eu/

### C. Contact Information

**For Security Issues:**
- Report vulnerabilities to: security@example.com
- PGP Key: [Add public key]

**For Compliance Questions:**
- Privacy Officer: privacy@example.com
- Security Officer: security-officer@example.com

---

**Report End**

*This security audit report is confidential and intended solely for the recipient organization. Unauthorized distribution is prohibited.*
