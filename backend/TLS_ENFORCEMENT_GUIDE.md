# TLS/SSL Enforcement and Security Headers Guide

**Medical Imaging Viewer - Professional Security Implementation**

**Author**: Claude Code Security Implementation
**Date**: 2025-11-23
**Version**: 1.0.0
**Compliance**: ISO 27001:2022 A.13.1.1, A.13.2.1, RFC 6797, RFC 7469, NIST SP 800-52 Rev. 2

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Cryptographic Foundation](#cryptographic-foundation)
3. [Architecture and Design](#architecture-and-design)
4. [TLS/SSL Configuration](#tlsssl-configuration)
5. [Security Headers](#security-headers)
6. [Certificate Management](#certificate-management)
7. [Usage Guide](#usage-guide)
8. [Deployment Scenarios](#deployment-scenarios)
9. [Compliance Mapping](#compliance-mapping)
10. [Security Best Practices](#security-best-practices)
11. [Troubleshooting](#troubleshooting)
12. [References](#references)

---

## Executive Summary

### Purpose

This guide provides comprehensive documentation for the **TLS/SSL Enforcement System** implemented in the Medical Imaging Viewer application. The system ensures:

1. **Encryption in Transit** - All communication encrypted with TLS 1.2+ (ISO 27001 A.13.1.1)
2. **HTTPS-Only Enforcement** - Non-HTTPS requests are rejected or redirected
3. **HSTS (HTTP Strict Transport Security)** - Browser-level HTTPS enforcement (RFC 6797)
4. **Security Headers** - Defense-in-depth with multiple HTTP security headers
5. **Certificate Validation** - Automated certificate validation and expiry monitoring

### Key Features

- **TLS 1.2+ Enforcement**: Deprecated TLS 1.0/1.1 per RFC 8996
- **Recommended Cipher Suites**: ECDHE with AES-GCM and ChaCha20-Poly1305 (Perfect Forward Secrecy)
- **4 Security Levels**: MINIMAL, STANDARD, STRICT, PARANOID
- **Content-Security-Policy**: Comprehensive CSP with violation reporting
- **Host Header Validation**: Prevents Host header injection attacks
- **Certificate Pinning**: Public key pinning support (RFC 7469)
- **Mutual TLS**: Client certificate verification support

### ISO 27001 Controls

| Control | Description | Implementation |
|---------|-------------|----------------|
| **A.13.1.1** | Network controls | TLS 1.2+ enforcement, cipher restrictions |
| **A.13.2.1** | Information transfer policies | HTTPS-only, HSTS, security headers |
| **A.13.2.3** | Electronic messaging | Secure communication channels |
| **A.10.1.1** | Policy on use of cryptographic controls | TLS configuration standards |
| **A.10.1.2** | Key management | Certificate lifecycle management |

---

## Cryptographic Foundation

### TLS Protocol Overview

**TLS (Transport Layer Security)** is the cryptographic protocol that provides secure communication over networks. It consists of:

1. **Handshake Protocol**: Authenticates server/client, negotiates cipher suite
2. **Record Protocol**: Encrypts application data with negotiated cipher
3. **Alert Protocol**: Communicates errors and warnings

#### TLS Handshake Flow

```
Client                                Server
------                                ------
ClientHello          ───────>
                                      ServerHello
                                      Certificate
                                      ServerKeyExchange
                     <───────         ServerHelloDone
ClientKeyExchange
ChangeCipherSpec
Finished             ───────>
                                      ChangeCipherSpec
                     <───────         Finished

[Encrypted Application Data]
```

### TLS Version Comparison

#### TLS 1.0/1.1 (DEPRECATED - DO NOT USE)

- **RFC 8996**: TLS 1.0/1.1 officially deprecated (March 2021)
- **Vulnerabilities**: BEAST, CRIME, Lucky13 attacks
- **Cipher Suites**: Weak CBC-mode ciphers, RC4
- **Status**: ❌ **BLOCKED** - Must not be used

#### TLS 1.2 (Minimum Recommended)

- **RFC 5246**: Published August 2008
- **Features**:
  - AEAD cipher modes (GCM, CCM, ChaCha20-Poly1305)
  - SHA-256 for PRF (Pseudo-Random Function)
  - Authenticated encryption
  - Explicit IVs (prevents BEAST attack)
- **Status**: ✅ **RECOMMENDED** for compatibility
- **Cipher Suite Example**: `ECDHE-RSA-AES256-GCM-SHA384`

#### TLS 1.3 (Preferred)

- **RFC 8446**: Published August 2018
- **Improvements**:
  - **Faster Handshake**: 1-RTT (round-trip time) vs 2-RTT in TLS 1.2
  - **0-RTT Resumption**: Zero round-trip time for resumed sessions
  - **Simplified Cipher Suites**: Only AEAD ciphers allowed
  - **Perfect Forward Secrecy**: Mandatory (no RSA key exchange)
  - **Removed Legacy**: No CBC, no RC4, no MD5, no SHA-1
- **Status**: ✅ **PREFERRED** for production
- **Cipher Suite Example**: `TLS_AES_256_GCM_SHA384`

### Cipher Suite Analysis

#### Anatomy of a Cipher Suite

Example: `ECDHE-RSA-AES256-GCM-SHA384`

```
ECDHE          ─┬─ Key Exchange (Elliptic Curve Diffie-Hellman Ephemeral)
RSA            ─┴─ Authentication (RSA certificate)
AES256         ─── Encryption (Advanced Encryption Standard, 256-bit key)
GCM            ─── Mode (Galois/Counter Mode - AEAD)
SHA384         ─── MAC/PRF (Secure Hash Algorithm 384-bit)
```

#### Recommended Cipher Suites (Priority Order)

**TLS 1.3 Cipher Suites**:

1. **TLS_AES_256_GCM_SHA384**
   - Encryption: AES-256-GCM (AEAD)
   - Security: 256-bit symmetric key
   - Performance: Hardware acceleration on modern CPUs
   - Use Case: Maximum security

2. **TLS_CHACHA20_POLY1305_SHA256**
   - Encryption: ChaCha20-Poly1305 (AEAD)
   - Security: 256-bit symmetric key
   - Performance: Fast on mobile devices without AES-NI
   - Use Case: Mobile/IoT devices

3. **TLS_AES_128_GCM_SHA256**
   - Encryption: AES-128-GCM (AEAD)
   - Security: 128-bit symmetric key (still very strong)
   - Performance: Fastest on AES-NI hardware
   - Use Case: High-throughput applications

**TLS 1.2 Cipher Suites**:

1. **ECDHE-RSA-AES256-GCM-SHA384**
   - Key Exchange: ECDHE (Perfect Forward Secrecy)
   - Authentication: RSA
   - Encryption: AES-256-GCM
   - Security: Excellent

2. **ECDHE-RSA-AES128-GCM-SHA256**
   - Key Exchange: ECDHE (PFS)
   - Authentication: RSA
   - Encryption: AES-128-GCM
   - Security: Excellent, faster than AES-256

3. **ECDHE-ECDSA-AES256-GCM-SHA384**
   - Key Exchange: ECDHE (PFS)
   - Authentication: ECDSA (Elliptic Curve)
   - Encryption: AES-256-GCM
   - Security: Excellent, faster authentication

4. **ECDHE-RSA-CHACHA20-POLY1305**
   - Key Exchange: ECDHE (PFS)
   - Authentication: RSA
   - Encryption: ChaCha20-Poly1305
   - Security: Excellent, good for mobile

#### Blocked Cipher Suites (Security Risks)

| Cipher Pattern | Vulnerability | Risk Level |
|----------------|---------------|------------|
| `NULL`, `eNULL`, `aNULL` | No encryption | **CRITICAL** |
| `EXPORT`, `EXP` | Weak 40/56-bit keys | **CRITICAL** |
| `DES`, `3DES` | Broken/weak encryption | **HIGH** |
| `RC4` | Biased keystream | **HIGH** |
| `MD5` | Collision attacks | **HIGH** |
| `CBC` (with TLS 1.0/1.1) | BEAST, Lucky13 | **MEDIUM** |
| Non-ECDHE (e.g., RSA) | No Perfect Forward Secrecy | **MEDIUM** |

#### Perfect Forward Secrecy (PFS)

**Definition**: Even if the server's private key is compromised, past session keys cannot be decrypted.

**How It Works**:
- Uses ephemeral (temporary) Diffie-Hellman keys for each session
- Session key = f(server_ephemeral_key, client_ephemeral_key)
- Ephemeral keys are discarded after session
- Server's long-term private key is ONLY used for authentication

**PFS Cipher Suites**: All contain `ECDHE` or `DHE`
- ✅ `ECDHE-RSA-AES256-GCM-SHA384` → Has PFS
- ❌ `RSA-AES256-GCM-SHA384` → No PFS (session key encrypted with server's static key)

### AEAD (Authenticated Encryption with Associated Data)

**Definition**: Encryption mode that provides both **confidentiality** (encryption) and **authenticity** (MAC) in a single operation.

**Benefits**:
1. **Performance**: Single pass instead of encrypt-then-MAC
2. **Security**: Prevents padding oracle attacks (unlike CBC)
3. **Simplicity**: No separate MAC algorithm needed

**AEAD Modes**:
- **GCM (Galois/Counter Mode)**: AES-GCM
- **ChaCha20-Poly1305**: Salsa20-based stream cipher + Poly1305 MAC
- **CCM (Counter with CBC-MAC)**: Less common

**GCM Structure**:
```
Plaintext + AAD (Additional Authenticated Data)
    ↓
AES-CTR Encryption (confidentiality)
    +
GHASH (authentication tag)
    ↓
Ciphertext + Authentication Tag (128-bit)
```

**Integrity Verification**:
- Receiver computes GHASH over ciphertext + AAD
- Compares with received authentication tag
- If mismatch → decryption fails (tampered data detected)

---

## Architecture and Design

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Client (Browser)                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  HSTS Policy Stored (max-age=31536000)                │  │
│  │  - Future requests AUTOMATICALLY use HTTPS            │  │
│  │  - HTTP requests converted to HTTPS by browser        │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS (TLS 1.2+)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  TLS Termination Layer                       │
│  (Uvicorn with SSL Context OR Reverse Proxy)                │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  SSL Context Configuration                          │    │
│  │  - Minimum TLS Version: TLS 1.2 or 1.3             │    │
│  │  - Cipher Suites: ECDHE + AES-GCM / ChaCha20       │    │
│  │  - Certificate: Server cert + private key          │    │
│  │  - Client Verification: Optional (mutual TLS)      │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP (internal)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                FastAPI Application Stack                     │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  1. IPBlacklistMiddleware                           │    │
│  │     (Block malicious IPs - ISO 27001 A.13.1.3)     │    │
│  └────────────────────────────────────────────────────┘    │
│                              │                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  2. RateLimitMiddleware                             │    │
│  │     (DoS protection - ISO 27001 A.12.2.1)          │    │
│  └────────────────────────────────────────────────────┘    │
│                              │                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  3. InputValidationMiddleware                       │    │
│  │     (Injection prevention - ISO 27001 A.14.2.1)    │    │
│  └────────────────────────────────────────────────────┘    │
│                              │                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  4. AuditMiddleware                                 │    │
│  │     (Security logging - ISO 27001 A.12.4.1)        │    │
│  └────────────────────────────────────────────────────┘    │
│                              │                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  5. LoggingMiddleware                               │    │
│  │     (Operational logging)                           │    │
│  └────────────────────────────────────────────────────┘    │
│                              │                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  6. CORSMiddleware                                  │    │
│  │     (Cross-origin policy)                           │    │
│  └────────────────────────────────────────────────────┘    │
│                              │                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  7. TLSEnforcementMiddleware ⬅ NEW                 │    │
│  │     - HTTPS enforcement                             │    │
│  │     - HSTS header injection                         │    │
│  │     - Security headers (CSP, X-Frame-Options, etc) │    │
│  │     - Host header validation                        │    │
│  │     (ISO 27001 A.13.1.1, A.13.2.1)                 │    │
│  └────────────────────────────────────────────────────┘    │
│                              │                              │
│                         Route Handlers                       │
└─────────────────────────────────────────────────────────────┘
```

### Middleware Design Pattern

**TLSEnforcementMiddleware** follows the **Starlette BaseHTTPMiddleware** pattern:

```python
class TLSEnforcementMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Pre-processing (before route handler)
        - Validate request is HTTPS
        - Validate Host header
        - Enforce security policies

        # 2. Call next middleware / route handler
        response = await call_next(request)

        # 3. Post-processing (after route handler)
        - Inject security headers
        - Add HSTS header
        - Remove sensitive headers

        return response
```

**Execution Flow**:
1. Request arrives at middleware
2. Middleware validates HTTPS/Host
3. If invalid → raise HTTPException (403/400)
4. If valid → pass to next middleware
5. Response comes back from handler
6. Middleware injects security headers
7. Response returned to client

### Security Headers Injection Strategy

**4-Level Security Model**:

```
┌──────────────────────────────────────────────────────────┐
│  MINIMAL Level                                            │
│  - Basic CSP: default-src 'self'                         │
│  - X-Frame-Options: SAMEORIGIN                           │
│  - X-Content-Type-Options: nosniff                       │
│  Use Case: Development, maximum compatibility            │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  STANDARD Level (Recommended)                             │
│  - CSP with inline scripts (React compatibility)         │
│  - All OWASP recommended headers                         │
│  - Referrer-Policy: strict-origin-when-cross-origin      │
│  - Permissions-Policy: restrict camera/microphone        │
│  Use Case: Production with modern SPAs                    │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  STRICT Level                                             │
│  - CSP: No inline scripts/styles                         │
│  - X-Frame-Options: DENY                                 │
│  - Referrer-Policy: no-referrer                          │
│  - Cross-Origin-Embedder-Policy: require-corp            │
│  Use Case: High-security applications                     │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  PARANOID Level                                           │
│  - CSP: default-src 'none' (deny everything)            │
│  - All cross-origin policies enforced                    │
│  - Cache-Control: no-store                               │
│  - Disable all browser features (camera, geolocation)    │
│  Use Case: Defense contractors, government               │
└──────────────────────────────────────────────────────────┘
```

---

## TLS/SSL Configuration

### Environment Variables

**File**: `backend/.env`

```bash
# ----------------------------------------------------------------------------
# TLS/SSL Configuration (ISO 27001 A.13.1.1, A.13.2.1)
# ----------------------------------------------------------------------------

# Enable TLS/SSL enforcement middleware
TLS_ENABLED=true

# Certificate paths (use absolute paths in production)
TLS_CERT_FILE=/etc/ssl/certs/medical-imaging-viewer.crt
TLS_KEY_FILE=/etc/ssl/private/medical-imaging-viewer.key

# Minimum TLS version (1.2 or 1.3)
TLS_MIN_VERSION=1.3

# HTTPS enforcement options
TLS_ENFORCE_HTTPS=true
TLS_REDIRECT_TO_HTTPS=false

# HSTS Configuration
HSTS_ENABLED=true
HSTS_MAX_AGE=31536000  # 1 year
HSTS_INCLUDE_SUBDOMAINS=true
HSTS_PRELOAD=false

# Security Headers Level
SECURITY_HEADER_LEVEL=STANDARD

# Allowed Hosts (Host header validation)
ALLOWED_HOSTS=medical-imaging-viewer.com,*.medical-imaging-viewer.com
```

### Creating SSL Context

**File**: `app/core/security/tls_enforcement.py`

```python
from app.core.security import create_ssl_context, TLSVersion

# Create SSL context for Uvicorn
ssl_context = create_ssl_context(
    cert_path="/etc/ssl/certs/medical-imaging-viewer.crt",
    key_path="/etc/ssl/private/medical-imaging-viewer.key",
    min_tls_version=TLSVersion.TLS_1_3,
    cipher_suites=None,  # Use recommended defaults
    verify_client_cert=False,  # Set True for mutual TLS
    ca_cert_path=None
)
```

**SSL Context Configuration**:

```python
def create_ssl_context(...) -> ssl.SSLContext:
    # Create context
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

    # Set minimum TLS version
    context.minimum_version = ssl.TLSVersion.TLSv1_3

    # Load certificate and key
    context.load_cert_chain(cert_path, key_path)

    # Set cipher suites (recommended ECDHE + AEAD)
    context.set_ciphers(':'.join(TLS_1_2_CIPHERS + TLS_1_3_CIPHERS))

    # Security options
    context.options |= ssl.OP_NO_COMPRESSION  # Disable CRIME
    context.options |= ssl.OP_CIPHER_SERVER_PREFERENCE  # Server chooses cipher

    # Client certificate verification (optional)
    if verify_client_cert:
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(ca_cert_path)

    return context
```

### Running with TLS

**Development** (Self-Signed Certificate):

```bash
# Generate self-signed certificate (development only)
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365 \
  -subj "/CN=localhost"

# Run with TLS
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8443 \
  --ssl-keyfile key.pem \
  --ssl-certfile cert.pem \
  --ssl-version 3  # TLS 1.2+
```

**Production** (Let's Encrypt Certificate):

```bash
# Obtain certificate with certbot
sudo certbot certonly --standalone \
  -d medical-imaging-viewer.com \
  -d www.medical-imaging-viewer.com

# Run with TLS
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 443 \
  --ssl-keyfile /etc/letsencrypt/live/medical-imaging-viewer.com/privkey.pem \
  --ssl-certfile /etc/letsencrypt/live/medical-imaging-viewer.com/fullchain.pem \
  --ssl-version 3
```

### Reverse Proxy Configuration

**Recommended**: Use NGINX or Caddy for TLS termination in production.

**NGINX Configuration**:

```nginx
server {
    listen 443 ssl http2;
    server_name medical-imaging-viewer.com;

    # TLS Configuration
    ssl_certificate /etc/letsencrypt/live/medical-imaging-viewer.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/medical-imaging-viewer.com/privkey.pem;

    # TLS version
    ssl_protocols TLSv1.2 TLSv1.3;

    # Cipher suites (Mozilla Intermediate)
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305';
    ssl_prefer_server_ciphers on;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Security headers (handled by middleware, but can add here too)
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;

    # OCSP Stapling (performance)
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/letsencrypt/live/medical-imaging-viewer.com/chain.pem;

    # Proxy to FastAPI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# HTTP → HTTPS redirect
server {
    listen 80;
    server_name medical-imaging-viewer.com;
    return 301 https://$server_name$request_uri;
}
```

**Caddy Configuration** (Auto-HTTPS):

```caddyfile
medical-imaging-viewer.com {
    # Caddy automatically obtains and renews Let's Encrypt certificates

    # Reverse proxy to FastAPI
    reverse_proxy localhost:8000 {
        header_up X-Forwarded-Proto {scheme}
    }

    # Security headers (can let middleware handle this)
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    }
}
```

---

## Security Headers

### Overview of Security Headers

Security headers are HTTP response headers that instruct browsers to enforce security policies. They provide **defense-in-depth** by adding multiple layers of protection.

### HSTS (HTTP Strict Transport Security)

**RFC**: 6797
**Purpose**: Force browsers to use HTTPS for all future requests
**ISO 27001**: A.13.1.1 - Network controls

**Header Format**:
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

**Directives**:
- `max-age=<seconds>`: Duration to remember HTTPS-only policy (1 year = 31536000)
- `includeSubDomains`: Apply to all subdomains (e.g., api.example.com)
- `preload`: Submit to browser HSTS preload list

**How It Works**:

```
First Visit (HTTPS)
─────────────────────────────────────────────
Client ──────> GET https://example.com
Server ──────> 200 OK
               Strict-Transport-Security: max-age=31536000

Browser stores HSTS policy for 1 year

Subsequent Visits (Even if user types HTTP)
─────────────────────────────────────────────
User types: http://example.com
Browser internally converts to: https://example.com
Client ──────> GET https://example.com (no HTTP request sent!)
```

**HSTS Preload List**:
- Chrome, Firefox, Safari, Edge maintain preload lists
- Domains can submit to: https://hstspreload.org/
- **Requirement**: max-age >= 31536000, includeSubDomains, preload directive
- **Warning**: Removal takes months - only submit if committed to HTTPS forever

**Attack Prevention**:
- **SSL Stripping**: Attacker cannot downgrade HTTPS to HTTP
- **Man-in-the-Middle**: User never sends unencrypted HTTP request

**Implementation**:
```python
from app.core.security import TLSEnforcementMiddleware

app.add_middleware(
    TLSEnforcementMiddleware,
    hsts_enabled=True,
    hsts_max_age=31536000,  # 1 year
    hsts_include_subdomains=True,
    hsts_preload=False  # Set True only if submitted to preload list
)
```

### Content-Security-Policy (CSP)

**Purpose**: Prevent XSS, clickjacking, and code injection attacks
**ISO 27001**: A.14.2.5 - Secure system engineering principles

**Header Format**:
```
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; ...
```

**Common Directives**:

| Directive | Purpose | Example |
|-----------|---------|---------|
| `default-src` | Fallback for all resources | `default-src 'self'` |
| `script-src` | JavaScript sources | `script-src 'self' https://cdn.example.com` |
| `style-src` | CSS sources | `style-src 'self' 'unsafe-inline'` |
| `img-src` | Image sources | `img-src 'self' data: https:` |
| `connect-src` | XHR/WebSocket/Fetch endpoints | `connect-src 'self' wss://ws.example.com` |
| `font-src` | Font sources | `font-src 'self' data:` |
| `frame-ancestors` | Allowed parent frames | `frame-ancestors 'none'` (no framing) |
| `base-uri` | Allowed `<base>` tag URIs | `base-uri 'self'` |
| `form-action` | Allowed form submission targets | `form-action 'self'` |
| `upgrade-insecure-requests` | Upgrade HTTP to HTTPS | (no value) |
| `block-all-mixed-content` | Block HTTP content on HTTPS page | (no value) |

**Source Values**:
- `'self'`: Same origin as document
- `'none'`: No sources allowed
- `'unsafe-inline'`: Allow inline scripts/styles (not recommended)
- `'unsafe-eval'`: Allow eval() (not recommended)
- `https:`: Any HTTPS URL
- `data:`: Data URIs (e.g., base64 images)
- `https://example.com`: Specific domain

**CSP Levels by Security**:

**STANDARD (Recommended for React/Vue/Angular)**:
```
default-src 'self';
script-src 'self' 'unsafe-inline' 'unsafe-eval';  # Allow inline for React
style-src 'self' 'unsafe-inline';  # Allow inline styles
img-src 'self' data: https:;
font-src 'self' data:;
connect-src 'self';
frame-ancestors 'self';
base-uri 'self';
form-action 'self';
upgrade-insecure-requests
```

**STRICT (Maximum Security)**:
```
default-src 'self';
script-src 'self';  # No inline scripts
style-src 'self';  # No inline styles
img-src 'self' data:;
font-src 'self';
connect-src 'self';
frame-ancestors 'none';  # No framing allowed
base-uri 'self';
form-action 'self';
upgrade-insecure-requests;
block-all-mixed-content
```

**CSP Violation Reporting**:

Add `report-uri` directive to receive violation reports:

```
Content-Security-Policy: default-src 'self'; report-uri /api/v1/csp-report
```

**Violation Report Format** (JSON POST to report-uri):
```json
{
  "csp-report": {
    "document-uri": "https://example.com/page",
    "violated-directive": "script-src 'self'",
    "blocked-uri": "https://evil.com/malicious.js",
    "line-number": 42,
    "column-number": 15,
    "source-file": "https://example.com/app.js"
  }
}
```

**Implementation**:
```python
from app.core.security import TLSEnforcementMiddleware, SecurityHeaderLevel

app.add_middleware(
    TLSEnforcementMiddleware,
    security_header_level=SecurityHeaderLevel.STANDARD,
    report_uri="/api/v1/csp-report"  # Optional violation reporting
)
```

**Custom CSP**:
```python
custom_csp = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "connect-src 'self' wss://ws.example.com"
)

app.add_middleware(
    TLSEnforcementMiddleware,
    custom_csp=custom_csp
)
```

### X-Frame-Options

**Purpose**: Prevent clickjacking attacks
**Status**: Legacy (use CSP `frame-ancestors` instead)

**Values**:
- `DENY`: Never allow framing
- `SAMEORIGIN`: Allow framing from same origin
- `ALLOW-FROM https://example.com`: Allow framing from specific origin (deprecated)

**Header**:
```
X-Frame-Options: DENY
```

**Clickjacking Attack**:
```html
<!-- Attacker's page -->
<iframe src="https://victim.com/transfer-money" style="opacity: 0"></iframe>
<button style="position: absolute; top: 100px; left: 200px">
  Click here to win a prize!
</button>
```

User clicks "Win Prize" button, actually clicks invisible iframe button to transfer money.

**Prevention**:
- `X-Frame-Options: DENY` → iframe load fails
- CSP `frame-ancestors 'none'` → more modern, more flexible

### X-Content-Type-Options

**Purpose**: Prevent MIME-type sniffing
**Value**: `nosniff`

**Header**:
```
X-Content-Type-Options: nosniff
```

**MIME Sniffing Attack**:

```
Server sends: Content-Type: text/plain
File contains: <script>alert('XSS')</script>

Without nosniff:
  Browser "sniffs" content → detects HTML → executes script ❌

With nosniff:
  Browser respects Content-Type → treats as text → no execution ✅
```

**Always Include**: No downside, always good security practice.

### X-XSS-Protection

**Purpose**: Enable browser XSS filter (legacy)
**Status**: Deprecated (CSP is better)

**Header**:
```
X-XSS-Protection: 1; mode=block
```

**Values**:
- `0`: Disable XSS filter
- `1`: Enable XSS filter
- `1; mode=block`: Block page if XSS detected

**Note**: Disabled by default in modern browsers (Chrome, Edge). Use CSP instead.

### Referrer-Policy

**Purpose**: Control Referer header sent to other sites

**Values**:
- `no-referrer`: Never send Referer header
- `no-referrer-when-downgrade`: Send for HTTPS→HTTPS, not HTTPS→HTTP
- `same-origin`: Send for same-origin requests only
- `origin`: Send origin only (no path)
- `strict-origin`: Like origin, but not HTTPS→HTTP
- `strict-origin-when-cross-origin`: Full URL for same-origin, origin for cross-origin

**Header**:
```
Referrer-Policy: strict-origin-when-cross-origin
```

**Privacy Impact**:

```
User on: https://medical-imaging-viewer.com/patient/12345
Clicks link to: https://external-site.com

Referrer-Policy: no-referrer
  → External site sees: (no Referer header)

Referrer-Policy: strict-origin-when-cross-origin
  → External site sees: Referer: https://medical-imaging-viewer.com
  (Origin only, no patient ID leaked)

Referrer-Policy: unsafe-url
  → External site sees: Referer: https://medical-imaging-viewer.com/patient/12345
  ❌ Patient ID leaked!
```

**HIPAA Consideration**: Use `no-referrer` or `strict-origin` to prevent PHI leakage.

### Permissions-Policy

**Purpose**: Control browser features (camera, microphone, geolocation, etc.)
**Formerly**: Feature-Policy

**Header Format**:
```
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

**Directive Syntax**:
- `camera=()`: Disable for all origins
- `camera=(self)`: Allow for same origin
- `camera=(self "https://trusted.com")`: Allow for self and trusted.com
- `camera=*`: Allow for all origins

**Common Directives**:
- `accelerometer`, `gyroscope`, `magnetometer`: Motion sensors
- `camera`, `microphone`: Media capture
- `geolocation`: Location
- `payment`: Payment Request API
- `usb`: WebUSB
- `autoplay`: Media autoplay
- `fullscreen`: Fullscreen API

**Example** (Medical Imaging Viewer - no camera/mic needed):
```
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
```

### Cross-Origin Policies

**Cross-Origin-Embedder-Policy (COEP)**:
```
Cross-Origin-Embedder-Policy: require-corp
```
Requires cross-origin resources to opt-in via CORP header.

**Cross-Origin-Opener-Policy (COOP)**:
```
Cross-Origin-Opener-Policy: same-origin
```
Isolates browsing context (prevents window.opener access).

**Cross-Origin-Resource-Policy (CORP)**:
```
Cross-Origin-Resource-Policy: same-origin
```
Controls which origins can load this resource.

**Purpose**: Enable **cross-origin isolation** for advanced web features (SharedArrayBuffer, high-resolution timers).

**Use Case**: Not needed for most applications unless using SharedArrayBuffer or WebAssembly threads.

### Cache-Control for Sensitive Pages

**Purpose**: Prevent caching of sensitive data

**Header**:
```
Cache-Control: no-store, no-cache, must-revalidate, private
Pragma: no-cache
```

**Directives**:
- `no-store`: Don't cache at all
- `no-cache`: Cache but revalidate before using
- `must-revalidate`: Revalidate stale cache entries
- `private`: Cache in browser only, not in CDN/proxies

**Use Case**: Patient data pages, authentication pages.

**Implementation**:
- STRICT/PARANOID levels automatically add Cache-Control
- MINIMAL/STANDARD levels allow caching (for performance)

---

## Certificate Management

### Certificate Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│  1. Certificate Generation                                   │
│     - Generate private key (RSA 2048/4096 or ECDSA P-256)   │
│     - Create CSR (Certificate Signing Request)              │
│     - Submit to CA (Certificate Authority)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Certificate Issuance                                     │
│     - CA validates domain ownership (DNS/HTTP challenge)     │
│     - CA signs certificate                                   │
│     - Certificate delivered (PEM format)                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Certificate Installation                                 │
│     - Install on server (Uvicorn, NGINX, etc.)              │
│     - Validate installation (CertificateValidator)           │
│     - Test HTTPS connectivity                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Certificate Monitoring                                   │
│     - Check expiry date (daily)                              │
│     - Alert if expiring soon (30 days)                       │
│     - Monitor revocation status (OCSP)                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Certificate Renewal                                      │
│     - Renew 30 days before expiry                            │
│     - Install new certificate                                │
│     - Validate new certificate                               │
│     - Remove old certificate                                 │
└─────────────────────────────────────────────────────────────┘
```

### Generating Certificates

**Option 1: Self-Signed Certificate (Development Only)**

```bash
# Generate private key (RSA 4096-bit)
openssl genrsa -out private-key.pem 4096

# Generate self-signed certificate (valid 365 days)
openssl req -new -x509 \
  -key private-key.pem \
  -out certificate.pem \
  -days 365 \
  -subj "/C=US/ST=California/L=San Francisco/O=Medical Imaging Viewer/CN=localhost"

# Verify certificate
openssl x509 -in certificate.pem -text -noout
```

**Option 2: Let's Encrypt (Production - Free)**

```bash
# Install certbot
sudo apt-get install certbot

# Obtain certificate (standalone mode)
sudo certbot certonly --standalone \
  -d medical-imaging-viewer.com \
  -d www.medical-imaging-viewer.com \
  --email admin@medical-imaging-viewer.com \
  --agree-tos \
  --no-eff-email

# Certificate locations:
# Certificate: /etc/letsencrypt/live/medical-imaging-viewer.com/fullchain.pem
# Private Key: /etc/letsencrypt/live/medical-imaging-viewer.com/privkey.pem
# Chain: /etc/letsencrypt/live/medical-imaging-viewer.com/chain.pem

# Automatic renewal (cron job)
sudo crontab -e
0 0 * * * /usr/bin/certbot renew --quiet
```

**Option 3: Commercial CA (Production - Paid)**

```bash
# 1. Generate private key
openssl genrsa -out medical-imaging-viewer.key 4096

# 2. Create CSR (Certificate Signing Request)
openssl req -new -key medical-imaging-viewer.key -out medical-imaging-viewer.csr

# 3. Submit CSR to CA (DigiCert, GlobalSign, etc.)
# 4. Complete domain validation (email, DNS, or HTTP)
# 5. Download signed certificate from CA

# 6. Verify certificate chain
openssl verify -CAfile ca-bundle.crt medical-imaging-viewer.crt
```

**Recommended Key Sizes**:
- **RSA**: 2048-bit (minimum), 4096-bit (recommended)
- **ECDSA**: P-256 (good), P-384 (better)

**ECDSA vs RSA**:
| Feature | RSA 2048 | RSA 4096 | ECDSA P-256 | ECDSA P-384 |
|---------|----------|----------|-------------|-------------|
| Security | 112-bit | 128-bit | 128-bit | 192-bit |
| Key Size | 2048 bits | 4096 bits | 256 bits | 384 bits |
| Cert Size | ~1 KB | ~2 KB | ~500 bytes | ~600 bytes |
| Performance | Medium | Slow | Fast | Fast |
| Support | Excellent | Excellent | Good | Good |

**Recommendation**: ECDSA P-256 for new deployments (faster, smaller, same security as RSA 2048).

### Certificate Validation

**Automated Validation with CertificateValidator**:

```python
from app.core.security import CertificateValidator

# Validate certificate and private key
result = CertificateValidator.validate_certificate_file(
    cert_path="/etc/ssl/certs/medical-imaging-viewer.crt",
    key_path="/etc/ssl/private/medical-imaging-viewer.key"
)

if result['valid']:
    print(f"✓ Certificate valid")
    print(f"  Common Name: {result['metadata']['common_name']}")
    print(f"  Valid Until: {result['metadata']['valid_until']}")
    print(f"  Key Size: {result['metadata']['public_key_bits']} bits")
else:
    print(f"✗ Certificate invalid:")
    for error in result['errors']:
        print(f"  - {error}")

if result['warnings']:
    print(f"⚠ Warnings:")
    for warning in result['warnings']:
        print(f"  - {warning}")
```

**Validation Checks**:
1. **File Loading**: Certificate and key files exist and are readable
2. **Format Validation**: Valid PEM format
3. **Key Match**: Private key matches certificate public key
4. **Expiry Check**: Certificate is not expired
5. **Expiry Warning**: Alert if expiring within 30 days
6. **Key Strength**: Minimum 2048-bit RSA or 256-bit ECDSA
7. **Self-Signed Detection**: Warning if self-signed (not suitable for production)

**Output Example**:

```json
{
  "valid": true,
  "errors": [],
  "warnings": [
    "Certificate expires in 25 days - renewal recommended"
  ],
  "metadata": {
    "common_name": "medical-imaging-viewer.com",
    "organization": "Medical Imaging Viewer Inc.",
    "issuer_cn": "Let's Encrypt Authority X3",
    "valid_from": "2025-10-23T00:00:00",
    "valid_until": "2026-01-21T23:59:59",
    "serial_number": 123456789012345678901234567890,
    "signature_algorithm": "sha256WithRSAEncryption",
    "public_key_bits": 2048
  }
}
```

### Certificate Pinning (Advanced)

**Purpose**: Prevent Man-in-the-Middle attacks with rogue CA certificates.

**How It Works**:
- Client stores hash of server's public key
- On connection, client verifies server's public key matches stored hash
- If mismatch → connection rejected (even if certificate is valid)

**Calculate Certificate Fingerprint**:

```python
from app.core.security import CertificateValidator

# Calculate SHA-256 fingerprint of certificate public key
fingerprint = CertificateValidator.calculate_cert_fingerprint(
    cert_path="/etc/ssl/certs/medical-imaging-viewer.crt",
    algorithm='sha256'
)

print(f"Certificate Fingerprint: {fingerprint}")
# Output: sha256-X48E9qOokqqrvdts8nOJRJN3OWDUoyWxBf7kbu9DBPE=
```

**Public-Key-Pins Header** (DEPRECATED - DO NOT USE):

```
Public-Key-Pins: pin-sha256="X48E9qO..."; pin-sha256="backup..."; max-age=5184000
```

**Note**: HPKP (HTTP Public Key Pinning) is deprecated due to operational risks. Use Certificate Transparency instead.

### Certificate Rotation

**Rotation Schedule**:
- **Automated** (Let's Encrypt): Every 60 days (auto-renewed at 30 days)
- **Manual** (Commercial CA): Every 12 months (renew at 30 days before expiry)

**Zero-Downtime Rotation**:

```bash
#!/bin/bash
# certificate-rotation.sh

# 1. Obtain new certificate (Let's Encrypt)
certbot renew --force-renewal

# 2. Validate new certificate
python3 << EOF
from app.core.security import CertificateValidator
result = CertificateValidator.validate_certificate_file(
    '/etc/letsencrypt/live/medical-imaging-viewer.com/fullchain.pem',
    '/etc/letsencrypt/live/medical-imaging-viewer.com/privkey.pem'
)
if not result['valid']:
    print('ERROR: New certificate invalid')
    exit(1)
EOF

# 3. Reload server (graceful restart)
systemctl reload nginx  # OR
kill -HUP $(cat /var/run/uvicorn.pid)  # Graceful reload

# 4. Verify HTTPS works
curl -I https://medical-imaging-viewer.com

# 5. Log rotation event
echo "$(date): Certificate rotated successfully" >> /var/log/cert-rotation.log
```

**Automation with Cron**:

```cron
# Renew certificates daily (certbot will only renew if needed)
0 3 * * * /usr/bin/certbot renew --quiet --deploy-hook "/usr/local/bin/certificate-rotation.sh"

# Monitor certificate expiry weekly
0 9 * * 1 /usr/local/bin/check-certificate-expiry.sh
```

**Monitoring Script**:

```bash
#!/bin/bash
# check-certificate-expiry.sh

CERT="/etc/letsencrypt/live/medical-imaging-viewer.com/fullchain.pem"
EXPIRY_DATE=$(openssl x509 -in "$CERT" -noout -enddate | cut -d= -f2)
EXPIRY_EPOCH=$(date -d "$EXPIRY_DATE" +%s)
NOW_EPOCH=$(date +%s)
DAYS_UNTIL_EXPIRY=$(( ($EXPIRY_EPOCH - $NOW_EPOCH) / 86400 ))

if [ $DAYS_UNTIL_EXPIRY -lt 30 ]; then
    echo "WARNING: Certificate expires in $DAYS_UNTIL_EXPIRY days!"
    # Send alert email
    echo "Certificate expiring soon: $DAYS_UNTIL_EXPIRY days" | \
      mail -s "Certificate Expiry Alert" security@medical-imaging-viewer.com
fi
```

---

## Usage Guide

### Basic Usage

**1. Enable TLS Enforcement in .env**:

```bash
TLS_ENABLED=true
TLS_ENFORCE_HTTPS=true
HSTS_ENABLED=true
SECURITY_HEADER_LEVEL=STANDARD
```

**2. Start Application**:

```bash
# Development (HTTP - TLS enforcement logs warnings)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Production (HTTPS - TLS enforcement active)
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 443 \
  --ssl-keyfile /etc/ssl/private/key.pem \
  --ssl-certfile /etc/ssl/certs/cert.pem
```

**3. Test HTTPS Enforcement**:

```bash
# Should reject with 403 Forbidden (if TLS_ENFORCE_HTTPS=true)
curl -i http://localhost:8000/api/v1/auth/login

# Should work with security headers
curl -i https://localhost:8443/api/v1/auth/login
```

### Advanced Configuration

**Custom CSP for Specific Application Needs**:

```python
# app/main.py
from app.core.security import TLSEnforcementMiddleware, SecurityHeaderLevel

# Allow external CDN for scripts
custom_csp = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' wss://ws.medical-imaging-viewer.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

app.add_middleware(
    TLSEnforcementMiddleware,
    enabled=True,
    enforce_https=True,
    security_header_level=SecurityHeaderLevel.STANDARD,
    custom_csp=custom_csp,
    hsts_enabled=True,
    hsts_max_age=31536000,
    hsts_preload=True  # Only if submitted to HSTS preload list
)
```

**Host Header Validation (Prevent Host Header Injection)**:

```python
# .env
ALLOWED_HOSTS=medical-imaging-viewer.com,*.medical-imaging-viewer.com,api.medical-imaging-viewer.com

# app/main.py
app.add_middleware(
    TLSEnforcementMiddleware,
    allowed_hosts=['medical-imaging-viewer.com', '*.medical-imaging-viewer.com']
)
```

**HTTP → HTTPS Redirect (Instead of Reject)**:

```bash
# .env
TLS_ENFORCE_HTTPS=false
TLS_REDIRECT_TO_HTTPS=true
```

```python
# app/main.py
app.add_middleware(
    TLSEnforcementMiddleware,
    enforce_https=False,  # Don't reject HTTP
    redirect_to_https=True  # Redirect HTTP → HTTPS (301)
)
```

**Exclude Paths from TLS Enforcement**:

```python
# Useful for health checks, webhooks from HTTP-only services
app.add_middleware(
    TLSEnforcementMiddleware,
    exclude_paths=['/api/health', '/api/webhooks/stripe']
)
```

**Mutual TLS (Client Certificate Verification)**:

```python
from app.core.security import create_ssl_context, TLSVersion

ssl_context = create_ssl_context(
    cert_path="/etc/ssl/certs/server.crt",
    key_path="/etc/ssl/private/server.key",
    min_tls_version=TLSVersion.TLS_1_3,
    verify_client_cert=True,  # Require client certificates
    ca_cert_path="/etc/ssl/certs/client-ca.crt"  # CA that signed client certs
)

# Run Uvicorn with mutual TLS
uvicorn app.main:app \
  --ssl-keyfile /etc/ssl/private/server.key \
  --ssl-certfile /etc/ssl/certs/server.crt \
  --ssl-ca-certs /etc/ssl/certs/client-ca.crt \
  --ssl-cert-reqs 2  # CERT_REQUIRED
```

### Testing and Verification

**Test TLS Configuration**:

```bash
# Check TLS version and cipher suite
openssl s_client -connect medical-imaging-viewer.com:443 -tls1_2
openssl s_client -connect medical-imaging-viewer.com:443 -tls1_3

# Check certificate details
openssl s_client -connect medical-imaging-viewer.com:443 -showcerts

# Test HSTS header
curl -I https://medical-imaging-viewer.com
# Should see: Strict-Transport-Security: max-age=31536000; includeSubDomains

# Test CSP header
curl -I https://medical-imaging-viewer.com
# Should see: Content-Security-Policy: default-src 'self'; ...

# Test Host header validation
curl -H "Host: evil.com" https://medical-imaging-viewer.com
# Should return: 400 Bad Request (Invalid Host header)
```

**SSL Labs Test** (Comprehensive Analysis):

```bash
# Run SSL Labs test
https://www.ssllabs.com/ssltest/analyze.html?d=medical-imaging-viewer.com

# Should achieve A+ rating with:
# - TLS 1.2+
# - Strong cipher suites
# - HSTS enabled
# - Certificate valid
```

**Security Headers Test**:

```bash
# Check all security headers
https://securityheaders.com/?q=https://medical-imaging-viewer.com

# Should achieve A+ rating with:
# - Strict-Transport-Security
# - Content-Security-Policy
# - X-Frame-Options
# - X-Content-Type-Options
# - Referrer-Policy
# - Permissions-Policy
```

---

## Deployment Scenarios

### Scenario 1: Development (HTTP, No TLS)

```bash
# .env
TLS_ENABLED=false
DEBUG=true
```

```bash
# Run on HTTP for local development
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Notes**:
- TLS middleware inactive (allows HTTP)
- Use for local development only
- NEVER use in production

### Scenario 2: Development (HTTPS, Self-Signed)

```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout dev-key.pem -out dev-cert.pem -days 365 \
  -subj "/CN=localhost"
```

```bash
# .env
TLS_ENABLED=true
TLS_ENFORCE_HTTPS=true
HSTS_ENABLED=false  # Don't enable HSTS for dev
SECURITY_HEADER_LEVEL=MINIMAL
```

```bash
# Run with HTTPS
uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8443 \
  --ssl-keyfile dev-key.pem \
  --ssl-certfile dev-cert.pem \
  --reload
```

**Browser Warning**:
- Browser will show "Not Secure" warning (self-signed cert)
- Click "Advanced" → "Proceed to localhost" to bypass

### Scenario 3: Production (Uvicorn with TLS)

```bash
# Obtain Let's Encrypt certificate
certbot certonly --standalone -d medical-imaging-viewer.com
```

```bash
# .env
TLS_ENABLED=true
TLS_ENFORCE_HTTPS=true
HSTS_ENABLED=true
HSTS_MAX_AGE=31536000
HSTS_INCLUDE_SUBDOMAINS=true
SECURITY_HEADER_LEVEL=STANDARD
ALLOWED_HOSTS=medical-imaging-viewer.com,*.medical-imaging-viewer.com
```

```bash
# Run with production certificate
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 443 \
  --ssl-keyfile /etc/letsencrypt/live/medical-imaging-viewer.com/privkey.pem \
  --ssl-certfile /etc/letsencrypt/live/medical-imaging-viewer.com/fullchain.pem \
  --workers 4
```

**Systemd Service**:

```ini
[Unit]
Description=Medical Imaging Viewer API
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/medical-imaging-viewer/backend
Environment="PATH=/opt/medical-imaging-viewer/backend/venv/bin"
ExecStart=/opt/medical-imaging-viewer/backend/venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 443 \
  --ssl-keyfile /etc/letsencrypt/live/medical-imaging-viewer.com/privkey.pem \
  --ssl-certfile /etc/letsencrypt/live/medical-imaging-viewer.com/fullchain.pem \
  --workers 4 \
  --log-config logging.yaml

[Install]
WantedBy=multi-user.target
```

### Scenario 4: Production (NGINX Reverse Proxy)

**Recommended for Production**: NGINX handles TLS termination, FastAPI handles application logic.

**NGINX Configuration** (`/etc/nginx/sites-available/medical-imaging-viewer`):

```nginx
# HTTP → HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name medical-imaging-viewer.com www.medical-imaging-viewer.com;

    # Redirect all HTTP to HTTPS
    return 301 https://medical-imaging-viewer.com$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name medical-imaging-viewer.com www.medical-imaging-viewer.com;

    # SSL Certificate
    ssl_certificate /etc/letsencrypt/live/medical-imaging-viewer.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/medical-imaging-viewer.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/medical-imaging-viewer.com/chain.pem;

    # TLS Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305';
    ssl_prefer_server_ciphers on;

    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;

    # Security Headers (can let FastAPI middleware handle this)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Proxy to FastAPI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Client certificate max size (500 MB for DICOM files)
    client_max_body_size 500M;
}
```

**FastAPI Configuration** (TLS handled by NGINX):

```bash
# .env
TLS_ENABLED=true  # Middleware still active
TLS_ENFORCE_HTTPS=false  # NGINX handles HTTPS enforcement
HSTS_ENABLED=false  # NGINX adds HSTS header
SECURITY_HEADER_LEVEL=STANDARD  # FastAPI adds CSP, X-Frame-Options, etc.
```

```bash
# Run FastAPI on HTTP (NGINX terminates TLS)
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
```

### Scenario 5: Docker with Let's Encrypt

**docker-compose.yml**:

```yaml
version: '3.8'

services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - backend

  backend:
    build: ./backend
    environment:
      - TLS_ENABLED=true
      - TLS_ENFORCE_HTTPS=false  # NGINX handles
      - SECURITY_HEADER_LEVEL=STANDARD
    volumes:
      - ./backend:/app
    expose:
      - "8000"

  certbot:
    image: certbot/certbot
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt
      - /var/www/certbot:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
```

**Certificate Renewal**:
```bash
# Obtain initial certificate
docker-compose run --rm certbot certonly --webroot \
  -w /var/www/certbot \
  -d medical-imaging-viewer.com \
  --email admin@medical-imaging-viewer.com \
  --agree-tos

# Reload NGINX after renewal
docker-compose exec nginx nginx -s reload
```

---

## Compliance Mapping

### ISO 27001:2022 Controls

| Control | Requirement | Implementation | Evidence |
|---------|-------------|----------------|----------|
| **A.13.1.1** | Network controls | TLS 1.2+ enforcement, HTTPS-only | TLSEnforcementMiddleware, SSL context configuration |
| **A.13.2.1** | Information transfer policies | Encryption in transit, HSTS | TLS configuration, HSTS headers |
| **A.13.2.3** | Electronic messaging | Secure communication channels | WebSocket over TLS (wss://) |
| **A.10.1.1** | Cryptographic controls policy | TLS version policy, cipher suite restrictions | Config settings, blocked ciphers list |
| **A.10.1.2** | Key management | Certificate lifecycle, rotation procedures | CertificateValidator, rotation scripts |
| **A.14.1.2** | Securing application services | Security headers, CSP | SecurityHeaderLevel, get_security_headers() |
| **A.14.2.5** | Secure system engineering | Defense-in-depth, multiple security layers | Middleware stack, header injection |

### HIPAA Security Rule

| Requirement | Implementation |
|-------------|----------------|
| **§ 164.312(e)(1)** Transmission Security | TLS 1.2+ encryption for all PHI transmission |
| **§ 164.312(e)(2)(i)** Integrity Controls | AEAD cipher modes (GCM, ChaCha20-Poly1305) verify data integrity |
| **§ 164.312(e)(2)(ii)** Encryption | AES-128/256-GCM encryption for data in transit |

### NIST SP 800-52 Rev. 2

| Guideline | Implementation |
|-----------|----------------|
| **3.1** TLS Version | TLS 1.2 minimum, TLS 1.3 preferred |
| **3.2** Cipher Suites | ECDHE + AEAD (GCM/ChaCha20-Poly1305) |
| **3.3** Certificate Validation | CertificateValidator with expiry/strength checks |
| **3.4** Perfect Forward Secrecy | All cipher suites include ECDHE |
| **4.1** Server Configuration | Cipher suite preference, TLS version enforcement |

### OWASP ASVS 4.0

| Requirement | Level | Implementation |
|-------------|-------|----------------|
| **V9.1.1** | L1 | TLS in use for all client connectivity |
| **V9.1.2** | L2 | TLS 1.2+ with strong cipher suites |
| **V9.1.3** | L2 | Only strong cipher suites enabled |
| **V9.2.1** | L1 | HSTS with sufficient max-age |
| **V9.2.3** | L2 | Valid, non-expired TLS certificates |
| **V9.2.4** | L2 | Certificate chain validation |

---

## Security Best Practices

### 1. Use TLS 1.3 for New Deployments

**Rationale**:
- Faster handshake (1-RTT vs 2-RTT)
- Mandatory Perfect Forward Secrecy
- Only AEAD cipher suites (no CBC vulnerabilities)
- Removed legacy cryptography

**Configuration**:
```bash
TLS_MIN_VERSION=1.3
```

### 2. Enable HSTS with Preload

**Rationale**:
- Prevents SSL stripping attacks
- Browser enforces HTTPS before first visit (if preloaded)
- No downgrade to HTTP possible

**Configuration**:
```bash
HSTS_ENABLED=true
HSTS_MAX_AGE=31536000  # 1 year
HSTS_INCLUDE_SUBDOMAINS=true
HSTS_PRELOAD=true  # Submit to hstspreload.org
```

**Submission**:
1. Test HSTS: https://hstspreload.org/?domain=medical-imaging-viewer.com
2. Submit to preload list
3. Wait 2-3 months for browser inclusion

### 3. Use STANDARD Security Level for SPAs

**Rationale**:
- STRICT level blocks inline scripts (breaks React/Vue/Angular)
- STANDARD allows `'unsafe-inline'` for scripts/styles
- Still protects against most XSS attacks

**Configuration**:
```bash
SECURITY_HEADER_LEVEL=STANDARD
```

**Upgrade Path** (If Possible):
- Use CSP nonce/hash instead of `'unsafe-inline'`
- Extract all inline scripts to external files
- Upgrade to STRICT level for maximum protection

### 4. Validate Certificates Regularly

**Rationale**:
- Expired certificates cause service outages
- Weak keys can be compromised
- Self-signed certificates leak into production

**Automation**:
```python
# Daily certificate validation (cron job)
from app.core.security import CertificateValidator

result = CertificateValidator.validate_certificate_file(
    cert_path="/etc/ssl/certs/production.crt",
    key_path="/etc/ssl/private/production.key"
)

if not result['valid']:
    # Send alert
    send_alert(f"Certificate invalid: {result['errors']}")

if result['warnings']:
    # Send warning (e.g., expiring soon)
    send_warning(f"Certificate warnings: {result['warnings']}")
```

### 5. Rotate Certificates Before Expiry

**Rationale**:
- Avoid service outages from expired certificates
- Maintain security compliance
- Limit impact of private key compromise

**Schedule**:
- **30 days before expiry**: Renew certificate
- **7 days before expiry**: Critical alert if not renewed
- **Let's Encrypt**: Auto-renewal at 30 days (90-day validity)

### 6. Use Strong Cipher Suites Only

**Rationale**:
- Weak ciphers (DES, RC4, MD5) can be broken
- CBC mode (with TLS 1.0/1.1) vulnerable to BEAST/Lucky13
- Non-ECDHE ciphers lack Perfect Forward Secrecy

**Blocked Ciphers**:
```python
BLOCKED_CIPHERS = [
    "NULL", "eNULL", "aNULL",  # No encryption
    "EXPORT", "EXP",  # Weak 40/56-bit keys
    "DES", "3DES",  # Broken/weak
    "RC4",  # Biased keystream
    "MD5",  # Collision attacks
    "CBC",  # BEAST/Lucky13 (with TLS 1.0/1.1)
]
```

### 7. Implement Host Header Validation

**Rationale**:
- Prevents Host header injection attacks
- Prevents cache poisoning
- Ensures requests go to intended domain

**Configuration**:
```bash
ALLOWED_HOSTS=medical-imaging-viewer.com,*.medical-imaging-viewer.com
```

**Attack Scenario**:
```
Attacker sends:
GET / HTTP/1.1
Host: evil.com

If server uses Host header in password reset email:
"Click here to reset: http://evil.com/reset?token=..."

User clicks link → attacker steals reset token
```

**Prevention**: Validate Host header, reject if not in allowed list.

### 8. Monitor TLS Configuration

**Tools**:
- **SSL Labs**: https://www.ssllabs.com/ssltest/
- **Security Headers**: https://securityheaders.com/
- **Mozilla Observatory**: https://observatory.mozilla.org/

**Metrics to Monitor**:
- TLS version usage (% TLS 1.2 vs 1.3)
- Cipher suite usage (prefer ECDHE + GCM)
- Certificate expiry date
- HSTS compliance
- CSP violation reports

### 9. Test TLS Configuration

**Manual Testing**:
```bash
# Test TLS 1.2
openssl s_client -connect medical-imaging-viewer.com:443 -tls1_2

# Test TLS 1.3
openssl s_client -connect medical-imaging-viewer.com:443 -tls1_3

# Test cipher suite
openssl s_client -connect medical-imaging-viewer.com:443 -cipher ECDHE-RSA-AES256-GCM-SHA384

# Should fail (weak cipher)
openssl s_client -connect medical-imaging-viewer.com:443 -cipher DES-CBC3-SHA
```

**Automated Testing**:
```python
import subprocess

def test_tls_config(host: str, port: int = 443) -> dict:
    results = {}

    # Test TLS 1.3
    result = subprocess.run(
        ['openssl', 's_client', '-connect', f'{host}:{port}', '-tls1_3'],
        capture_output=True,
        timeout=5
    )
    results['tls_1_3'] = result.returncode == 0

    # Test TLS 1.0 (should fail)
    result = subprocess.run(
        ['openssl', 's_client', '-connect', f'{host}:{port}', '-tls1'],
        capture_output=True,
        timeout=5
    )
    results['tls_1_0_blocked'] = result.returncode != 0

    return results
```

### 10. Document TLS Configuration

**Documentation Requirements**:
1. **Certificate Information**: Issuer, expiry date, key size
2. **TLS Version**: Minimum version, preferred version
3. **Cipher Suites**: Allowed ciphers, blocked ciphers
4. **Security Headers**: CSP policy, HSTS configuration
5. **Rotation Procedures**: Certificate renewal process
6. **Incident Response**: What to do if certificate compromised

**Example**:
```markdown
## TLS Configuration

- **TLS Version**: 1.3 (preferred), 1.2 (minimum)
- **Cipher Suites**: ECDHE + AES-GCM / ChaCha20-Poly1305
- **Certificate**: Let's Encrypt, expires 2026-01-21
- **HSTS**: Enabled, max-age 1 year, includeSubDomains
- **Security Headers**: STANDARD level

## Certificate Rotation

1. Renew 30 days before expiry
2. Validate new certificate with CertificateValidator
3. Graceful reload: `systemctl reload nginx`
4. Verify HTTPS: `curl -I https://medical-imaging-viewer.com`
```

---

## Troubleshooting

### Common Issues and Solutions

#### 1. "SSL: CERTIFICATE_VERIFY_FAILED"

**Symptoms**:
```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed
```

**Causes**:
- Self-signed certificate in production
- Certificate chain incomplete
- CA certificate not trusted

**Solutions**:

**a) Self-Signed Certificate**:
```bash
# For development only - trust self-signed certificate
export REQUESTS_CA_BUNDLE=/path/to/self-signed-cert.pem

# OR use --insecure flag (curl)
curl --insecure https://localhost:8443
```

**b) Incomplete Certificate Chain**:
```bash
# Use fullchain.pem (includes intermediate certificates)
TLS_CERT_FILE=/etc/letsencrypt/live/domain.com/fullchain.pem  # ✓
# NOT cert.pem (only end-entity certificate)
TLS_CERT_FILE=/etc/letsencrypt/live/domain.com/cert.pem  # ✗
```

**c) Update CA Bundle**:
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install ca-certificates

# CentOS/RHEL
sudo yum update ca-certificates
```

#### 2. "403 Forbidden: HTTPS required"

**Symptoms**:
```json
{"detail": "HTTPS required. This API only accepts secure connections."}
```

**Causes**:
- `TLS_ENFORCE_HTTPS=true` but request is HTTP
- Reverse proxy not setting X-Forwarded-Proto header

**Solutions**:

**a) Use HTTPS**:
```bash
# Instead of:
curl http://medical-imaging-viewer.com/api/v1/auth/login

# Use:
curl https://medical-imaging-viewer.com/api/v1/auth/login
```

**b) Configure Reverse Proxy**:
```nginx
# NGINX - set X-Forwarded-Proto
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header X-Forwarded-Proto $scheme;  # ← Important
}
```

**c) Disable HTTPS Enforcement (Development Only)**:
```bash
TLS_ENFORCE_HTTPS=false
```

#### 3. "400 Bad Request: Invalid Host header"

**Symptoms**:
```json
{"detail": "Invalid Host header"}
```

**Causes**:
- Host header not in ALLOWED_HOSTS list
- Using IP address instead of domain name

**Solutions**:

**a) Add Host to ALLOWED_HOSTS**:
```bash
# .env
ALLOWED_HOSTS=medical-imaging-viewer.com,192.168.1.100,localhost
```

**b) Use Correct Domain**:
```bash
# Instead of:
curl https://192.168.1.100/api/v1/auth/login

# Use:
curl https://medical-imaging-viewer.com/api/v1/auth/login
```

**c) Disable Host Validation (Development Only)**:
```bash
# Leave ALLOWED_HOSTS empty
ALLOWED_HOSTS=
```

#### 4. "CSP Violation: Refused to load inline script"

**Symptoms**:
```
Refused to load the script 'https://example.com/app.js' because it violates
the following Content Security Policy directive: "script-src 'self'".
```

**Causes**:
- CSP policy too strict for application
- Inline scripts blocked by `script-src 'self'`

**Solutions**:

**a) Use STANDARD Level (Allows Inline)**:
```bash
SECURITY_HEADER_LEVEL=STANDARD  # Allows 'unsafe-inline'
```

**b) Custom CSP (Allow Specific Domains)**:
```bash
CUSTOM_CSP="default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; ..."
```

**c) Use CSP Nonce (Recommended)**:
```html
<!-- Backend generates random nonce -->
<script nonce="rAnd0m123">
  // Inline script
</script>
```

```
Content-Security-Policy: script-src 'self' 'nonce-rAnd0m123'
```

#### 5. Certificate Expiry Not Detected

**Symptoms**:
- Certificate expired but no alert sent
- Validation script not running

**Solutions**:

**a) Verify Cron Job**:
```bash
# Check cron jobs
crontab -l

# Should see:
0 3 * * * /usr/bin/certbot renew --quiet
0 9 * * 1 /usr/local/bin/check-certificate-expiry.sh
```

**b) Test Validation Script**:
```bash
# Run manually
/usr/local/bin/check-certificate-expiry.sh

# Check logs
tail -f /var/log/cert-rotation.log
```

**c) Enable Email Alerts**:
```bash
# In check-certificate-expiry.sh
if [ $DAYS_UNTIL_EXPIRY -lt 30 ]; then
    echo "Certificate expiring in $DAYS_UNTIL_EXPIRY days" | \
      mail -s "URGENT: Certificate Expiry" security@example.com
fi
```

#### 6. HSTS Not Working

**Symptoms**:
- Browser doesn't enforce HTTPS
- No Strict-Transport-Security header

**Solutions**:

**a) Enable HSTS**:
```bash
HSTS_ENABLED=true
HSTS_MAX_AGE=31536000
```

**b) Verify Header**:
```bash
curl -I https://medical-imaging-viewer.com
# Should see: Strict-Transport-Security: max-age=31536000; includeSubDomains
```

**c) Clear Browser HSTS Cache**:
```
Chrome: chrome://net-internals/#hsts → Delete domain
Firefox: about:permissions → Clear Site Data
```

#### 7. Performance Issues with TLS

**Symptoms**:
- Slow HTTPS handshake
- High CPU usage on SSL/TLS processing

**Solutions**:

**a) Use TLS 1.3** (Faster Handshake):
```bash
TLS_MIN_VERSION=1.3
```

**b) Enable OCSP Stapling** (NGINX):
```nginx
ssl_stapling on;
ssl_stapling_verify on;
```

**c) Use Hardware Acceleration**:
```bash
# Check for AES-NI support
grep -m1 -o aes /proc/cpuinfo

# If available, prefer AES-GCM ciphers (hardware accelerated)
ssl_ciphers 'ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384';
```

**d) Reuse SSL Sessions**:
```nginx
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
```

---

## References

### RFCs and Standards

1. **RFC 8446**: The Transport Layer Security (TLS) Protocol Version 1.3 (August 2018)
   - https://datatracker.ietf.org/doc/html/rfc8446

2. **RFC 5246**: The Transport Layer Security (TLS) Protocol Version 1.2 (August 2008)
   - https://datatracker.ietf.org/doc/html/rfc5246

3. **RFC 8996**: Deprecating TLS 1.0 and TLS 1.1 (March 2021)
   - https://datatracker.ietf.org/doc/html/rfc8996

4. **RFC 6797**: HTTP Strict Transport Security (HSTS) (November 2012)
   - https://datatracker.ietf.org/doc/html/rfc6797

5. **RFC 7469**: Public Key Pinning Extension for HTTP (April 2015)
   - https://datatracker.ietf.org/doc/html/rfc7469
   - Status: Deprecated (use Certificate Transparency instead)

6. **RFC 7540**: Hypertext Transfer Protocol Version 2 (HTTP/2) (May 2015)
   - https://datatracker.ietf.org/doc/html/rfc7540

### NIST Publications

1. **NIST SP 800-52 Rev. 2**: Guidelines for the Selection, Configuration, and Use of TLS (August 2019)
   - https://csrc.nist.gov/publications/detail/sp/800-52/rev-2/final

2. **NIST SP 800-57 Part 1 Rev. 5**: Recommendation for Key Management (May 2020)
   - https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final

3. **NIST SP 800-38D**: Recommendation for Block Cipher Modes: Galois/Counter Mode (GCM) (November 2007)
   - https://csrc.nist.gov/publications/detail/sp/800-38d/final

### ISO 27001:2022

1. **ISO/IEC 27001:2022**: Information security, cybersecurity and privacy protection (October 2022)
   - Control A.13.1.1: Network controls
   - Control A.13.2.1: Information transfer policies and procedures
   - Control A.10.1.1: Policy on the use of cryptographic controls
   - Control A.10.1.2: Key management

### OWASP Resources

1. **OWASP Transport Layer Security Cheat Sheet**
   - https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html

2. **OWASP Secure Headers Project**
   - https://owasp.org/www-project-secure-headers/

3. **OWASP Content Security Policy Cheat Sheet**
   - https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html

4. **OWASP ASVS 4.0** (Application Security Verification Standard)
   - https://owasp.org/www-project-application-security-verification-standard/

### Mozilla Resources

1. **Mozilla TLS Configuration Generator**
   - https://ssl-config.mozilla.org/

2. **Mozilla Observatory**
   - https://observatory.mozilla.org/

3. **Mozilla Security Guidelines**
   - https://infosec.mozilla.org/guidelines/web_security

### Testing Tools

1. **SSL Labs Server Test**
   - https://www.ssllabs.com/ssltest/

2. **Security Headers Scanner**
   - https://securityheaders.com/

3. **HSTS Preload List Submission**
   - https://hstspreload.org/

4. **testssl.sh** (Command-line TLS scanner)
   - https://github.com/drwetter/testssl.sh

### Let's Encrypt

1. **Let's Encrypt - Getting Started**
   - https://letsencrypt.org/getting-started/

2. **Certbot Documentation**
   - https://certbot.eff.org/docs/

### HIPAA Resources

1. **HIPAA Security Rule - Technical Safeguards (§ 164.312)**
   - https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html

---

## Appendix

### A. Cipher Suite Reference

**TLS 1.3 Cipher Suites** (All AEAD):

```
TLS_AES_256_GCM_SHA384
TLS_CHACHA20_POLY1305_SHA256
TLS_AES_128_GCM_SHA256
TLS_AES_128_CCM_SHA256 (rarely used)
TLS_AES_128_CCM_8_SHA256 (rarely used)
```

**TLS 1.2 Recommended Cipher Suites**:

```
# ECDHE-RSA (RSA certificates, most common)
ECDHE-RSA-AES256-GCM-SHA384
ECDHE-RSA-AES128-GCM-SHA256
ECDHE-RSA-CHACHA20-POLY1305

# ECDHE-ECDSA (ECDSA certificates, faster auth)
ECDHE-ECDSA-AES256-GCM-SHA384
ECDHE-ECDSA-AES128-GCM-SHA256
ECDHE-ECDSA-CHACHA20-POLY1305

# DHE-RSA (fallback if ECDHE unavailable)
DHE-RSA-AES256-GCM-SHA384
DHE-RSA-AES128-GCM-SHA256
```

### B. Security Header Examples

**MINIMAL Level**:
```
Content-Security-Policy: default-src 'self'
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

**STANDARD Level**:
```
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

**STRICT Level**:
```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests; block-all-mixed-content
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: no-referrer
Permissions-Policy: accelerometer=(), camera=(), geolocation=(), microphone=(), payment=()
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
Cache-Control: no-store, no-cache, must-revalidate, private
Pragma: no-cache
```

**PARANOID Level**:
```
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; upgrade-insecure-requests; block-all-mixed-content
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: no-referrer
Permissions-Policy: accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
Cache-Control: no-store, no-cache, must-revalidate, private
Pragma: no-cache
```

### C. Certificate Validation Script

**File**: `scripts/validate_certificate.py`

```python
#!/usr/bin/env python3
"""
Certificate Validation Script
Validates TLS certificate and private key, checks expiry.
"""

import sys
from pathlib import Path
from app.core.security import CertificateValidator

def main():
    if len(sys.argv) != 3:
        print("Usage: validate_certificate.py <cert_file> <key_file>")
        sys.exit(1)

    cert_path = sys.argv[1]
    key_path = sys.argv[2]

    # Validate files exist
    if not Path(cert_path).exists():
        print(f"ERROR: Certificate file not found: {cert_path}")
        sys.exit(1)

    if not Path(key_path).exists():
        print(f"ERROR: Key file not found: {key_path}")
        sys.exit(1)

    # Validate certificate
    print(f"Validating certificate: {cert_path}")
    print(f"Private key: {key_path}")
    print("-" * 60)

    result = CertificateValidator.validate_certificate_file(cert_path, key_path)

    # Print metadata
    if result['metadata']:
        meta = result['metadata']
        print(f"Common Name: {meta.get('common_name')}")
        print(f"Organization: {meta.get('organization')}")
        print(f"Issuer: {meta.get('issuer_cn')}")
        print(f"Valid From: {meta.get('valid_from')}")
        print(f"Valid Until: {meta.get('valid_until')}")
        print(f"Serial Number: {meta.get('serial_number')}")
        print(f"Signature Algorithm: {meta.get('signature_algorithm')}")
        print(f"Public Key Bits: {meta.get('public_key_bits')}")
        print("-" * 60)

    # Print errors
    if result['errors']:
        print("ERRORS:")
        for error in result['errors']:
            print(f"  ✗ {error}")
        print()

    # Print warnings
    if result['warnings']:
        print("WARNINGS:")
        for warning in result['warnings']:
            print(f"  ⚠ {warning}")
        print()

    # Overall status
    if result['valid']:
        print("✓ Certificate is VALID")
        sys.exit(0)
    else:
        print("✗ Certificate is INVALID")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

**Usage**:
```bash
python scripts/validate_certificate.py \
  /etc/letsencrypt/live/example.com/fullchain.pem \
  /etc/letsencrypt/live/example.com/privkey.pem
```

---

## Conclusion

This guide provides comprehensive documentation for implementing **TLS/SSL enforcement and security headers** in the Medical Imaging Viewer application. The implementation provides:

✅ **Encryption in Transit** - TLS 1.2+ with strong cipher suites
✅ **HTTPS Enforcement** - Automatic HTTPS-only mode with HSTS
✅ **Security Headers** - Defense-in-depth with CSP, X-Frame-Options, etc.
✅ **Certificate Management** - Automated validation and rotation
✅ **ISO 27001 Compliance** - Controls A.13.1.1, A.13.2.1, A.10.1.1, A.10.1.2
✅ **HIPAA Compliance** - § 164.312(e) Transmission Security
✅ **NIST SP 800-52 Compliance** - TLS configuration guidelines

For questions or support, refer to:
- Code: `backend/app/core/security/tls_enforcement.py`
- Configuration: `backend/.env.example`
- Validation: `backend/app/core/security/tls_enforcement.py` (CertificateValidator)

**Security Notice**: This is a production-ready implementation following industry best practices and compliance standards. Regular monitoring and certificate rotation are essential for maintaining security.

---

**Document Version**: 1.0.0
**Last Updated**: 2025-11-23
**Maintained By**: Security Team
**Review Cycle**: Quarterly
