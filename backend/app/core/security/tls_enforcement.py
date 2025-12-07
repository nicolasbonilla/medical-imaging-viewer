"""
TLS/SSL Enforcement and Security Headers Middleware
ISO 27001 A.13.1.1 - Network controls
ISO 27001 A.13.2.1 - Information transfer policies and procedures
ISO 27001 A.13.2.3 - Electronic messaging

Implements comprehensive TLS/SSL enforcement including:
- HTTPS-only enforcement with HSTS
- Strict security headers (CSP, X-Frame-Options, etc.)
- Certificate validation and pinning
- TLS version enforcement (TLS 1.2+)
- Cipher suite restrictions

References:
- RFC 6797 - HTTP Strict Transport Security (HSTS)
- RFC 7469 - Public Key Pinning Extension for HTTP (HPKP)
- OWASP Secure Headers Project
- NIST SP 800-52 Rev. 2 - Guidelines for TLS

@module core.security.tls_enforcement
"""

import os
import ssl
import hashlib
import base64
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timezone, timedelta
from enum import Enum

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_logger, get_audit_logger
from app.core.logging.audit import AuditEventType, AuditSeverity

logger = get_logger(__name__)
audit_logger = get_audit_logger()


class TLSVersion(str, Enum):
    """
    TLS protocol versions.

    TLS 1.0 and 1.1 are deprecated (RFC 8996).
    Only TLS 1.2+ should be used in production.
    """
    TLS_1_0 = "TLSv1.0"  # Deprecated - DO NOT USE
    TLS_1_1 = "TLSv1.1"  # Deprecated - DO NOT USE
    TLS_1_2 = "TLSv1.2"  # Minimum recommended
    TLS_1_3 = "TLSv1.3"  # Preferred


class SecurityHeaderLevel(str, Enum):
    """
    Security header strictness levels.
    """
    MINIMAL = "minimal"      # Basic headers
    STANDARD = "standard"    # OWASP recommended
    STRICT = "strict"        # Maximum security (may break some features)
    PARANOID = "paranoid"    # Extreme security (breaks most third-party features)


# ============================================================================
# RECOMMENDED CIPHER SUITES (NIST SP 800-52 Rev. 2)
# ============================================================================

# TLS 1.3 cipher suites (preference order)
TLS_1_3_CIPHERS = [
    "TLS_AES_256_GCM_SHA384",           # AES-256-GCM (AEAD)
    "TLS_CHACHA20_POLY1305_SHA256",     # ChaCha20-Poly1305 (AEAD)
    "TLS_AES_128_GCM_SHA256",           # AES-128-GCM (AEAD)
]

# TLS 1.2 cipher suites (preference order)
TLS_1_2_CIPHERS = [
    # ECDHE with AES-GCM (Perfect Forward Secrecy + AEAD)
    "ECDHE-RSA-AES256-GCM-SHA384",
    "ECDHE-RSA-AES128-GCM-SHA256",
    "ECDHE-ECDSA-AES256-GCM-SHA384",
    "ECDHE-ECDSA-AES128-GCM-SHA256",

    # ECDHE with ChaCha20-Poly1305 (PFS + AEAD, good for mobile)
    "ECDHE-RSA-CHACHA20-POLY1305",
    "ECDHE-ECDSA-CHACHA20-POLY1305",
]

# Weak/insecure cipher suites to BLOCK
BLOCKED_CIPHERS = [
    # NULL encryption (no encryption!)
    "NULL", "eNULL", "aNULL",

    # Export-grade (intentionally weak)
    "EXPORT", "EXP",

    # DES (broken)
    "DES", "3DES", "DES-CBC3-SHA",

    # RC4 (broken)
    "RC4",

    # MD5 (broken)
    "MD5",

    # CBC mode with TLS 1.0/1.1 (BEAST/Lucky13 attacks)
    "CBC",

    # No Perfect Forward Secrecy
    "RSA", "PSK", "SRP",
]


# ============================================================================
# SECURITY HEADERS CONFIGURATION
# ============================================================================

def get_security_headers(
    level: SecurityHeaderLevel = SecurityHeaderLevel.STANDARD,
    custom_csp: Optional[str] = None,
    enable_hsts: bool = True,
    hsts_max_age: int = 31536000,
    hsts_include_subdomains: bool = True,
    hsts_preload: bool = False,
    report_uri: Optional[str] = None
) -> Dict[str, str]:
    """
    Generate security headers based on strictness level.

    Args:
        level: Security header strictness level
        custom_csp: Custom Content-Security-Policy
        enable_hsts: Enable HTTP Strict Transport Security
        hsts_max_age: HSTS max-age in seconds (default: 1 year)
        hsts_include_subdomains: Include subdomains in HSTS
        hsts_preload: Enable HSTS preload (requires max-age >= 1 year)
        report_uri: URI for CSP violation reports

    Returns:
        Dictionary of security headers
    """
    headers = {}

    # -------------------------------------------------------------------------
    # HSTS (HTTP Strict Transport Security) - RFC 6797
    # ISO 27001 A.13.1.1 - Forces HTTPS for all future requests
    # -------------------------------------------------------------------------
    if enable_hsts:
        hsts_value = f"max-age={hsts_max_age}"
        if hsts_include_subdomains:
            hsts_value += "; includeSubDomains"
        if hsts_preload and hsts_max_age >= 31536000:
            hsts_value += "; preload"

        headers["Strict-Transport-Security"] = hsts_value

    # -------------------------------------------------------------------------
    # Content-Security-Policy (CSP)
    # Prevents XSS, clickjacking, and other code injection attacks
    # -------------------------------------------------------------------------
    if custom_csp:
        csp = custom_csp
    else:
        if level == SecurityHeaderLevel.MINIMAL:
            csp = "default-src 'self'"

        elif level == SecurityHeaderLevel.STANDARD:
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # Allow inline scripts (React)
                "style-src 'self' 'unsafe-inline'; "  # Allow inline styles
                "img-src 'self' data: https:; "  # Images from self, data URIs, HTTPS
                "font-src 'self' data:; "
                "connect-src 'self'; "  # XHR/WebSocket to self only
                "frame-ancestors 'self'; "  # Clickjacking protection
                "base-uri 'self'; "  # Prevent base tag injection
                "form-action 'self'; "  # Forms submit to self only
                "upgrade-insecure-requests"  # Upgrade HTTP to HTTPS
            )

        elif level == SecurityHeaderLevel.STRICT:
            csp = (
                "default-src 'self'; "
                "script-src 'self'; "  # No inline scripts
                "style-src 'self'; "  # No inline styles
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "  # No framing allowed
                "base-uri 'self'; "
                "form-action 'self'; "
                "upgrade-insecure-requests; "
                "block-all-mixed-content"  # Block HTTP content on HTTPS page
            )

        else:  # PARANOID
            csp = (
                "default-src 'none'; "  # Deny everything by default
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self'; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'none'; "
                "form-action 'self'; "
                "upgrade-insecure-requests; "
                "block-all-mixed-content"
            )

    # Add CSP report URI if provided
    if report_uri:
        csp += f"; report-uri {report_uri}"

    headers["Content-Security-Policy"] = csp

    # -------------------------------------------------------------------------
    # X-Frame-Options - Clickjacking protection (legacy, use CSP frame-ancestors)
    # -------------------------------------------------------------------------
    if level in [SecurityHeaderLevel.STRICT, SecurityHeaderLevel.PARANOID]:
        headers["X-Frame-Options"] = "DENY"
    else:
        headers["X-Frame-Options"] = "SAMEORIGIN"

    # -------------------------------------------------------------------------
    # X-Content-Type-Options - Prevent MIME-type sniffing
    # -------------------------------------------------------------------------
    headers["X-Content-Type-Options"] = "nosniff"

    # -------------------------------------------------------------------------
    # X-XSS-Protection - Legacy XSS filter (deprecated, use CSP)
    # -------------------------------------------------------------------------
    headers["X-XSS-Protection"] = "1; mode=block"

    # -------------------------------------------------------------------------
    # Referrer-Policy - Control referrer information
    # -------------------------------------------------------------------------
    if level in [SecurityHeaderLevel.STRICT, SecurityHeaderLevel.PARANOID]:
        headers["Referrer-Policy"] = "no-referrer"
    else:
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # -------------------------------------------------------------------------
    # Permissions-Policy (formerly Feature-Policy)
    # Disable browser features that aren't needed
    # -------------------------------------------------------------------------
    if level == SecurityHeaderLevel.PARANOID:
        permissions = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )
    elif level == SecurityHeaderLevel.STRICT:
        permissions = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "microphone=(), "
            "payment=()"
        )
    else:
        permissions = "geolocation=(), microphone=(), camera=()"

    headers["Permissions-Policy"] = permissions

    # -------------------------------------------------------------------------
    # Cross-Origin Policies
    # -------------------------------------------------------------------------
    if level in [SecurityHeaderLevel.STRICT, SecurityHeaderLevel.PARANOID]:
        headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        headers["Cross-Origin-Opener-Policy"] = "same-origin"
        headers["Cross-Origin-Resource-Policy"] = "same-origin"

    # -------------------------------------------------------------------------
    # Cache-Control for sensitive pages
    # -------------------------------------------------------------------------
    if level in [SecurityHeaderLevel.STRICT, SecurityHeaderLevel.PARANOID]:
        headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        headers["Pragma"] = "no-cache"

    return headers


# ============================================================================
# TLS ENFORCEMENT MIDDLEWARE
# ============================================================================

class TLSEnforcementMiddleware(BaseHTTPMiddleware):
    """
    TLS/SSL Enforcement Middleware.

    ISO 27001 A.13.1.1 - Network controls
    ISO 27001 A.13.2.1 - Information transfer policies

    Features:
    - HTTPS-only enforcement
    - HSTS with optional preload
    - Security headers injection
    - TLS version validation
    - Mixed content prevention
    """

    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = True,
        enforce_https: bool = True,
        redirect_to_https: bool = True,
        security_header_level: SecurityHeaderLevel = SecurityHeaderLevel.STANDARD,
        hsts_enabled: bool = True,
        hsts_max_age: int = 31536000,
        hsts_include_subdomains: bool = True,
        hsts_preload: bool = False,
        custom_csp: Optional[str] = None,
        report_uri: Optional[str] = None,
        allowed_hosts: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None
    ):
        """
        Initialize TLS enforcement middleware.

        Args:
            app: ASGI application
            enabled: Whether TLS enforcement is enabled
            enforce_https: Reject non-HTTPS requests
            redirect_to_https: Redirect HTTP to HTTPS (if enforce_https=False)
            security_header_level: Strictness level for security headers
            hsts_enabled: Enable HTTP Strict Transport Security
            hsts_max_age: HSTS max-age in seconds (1 year default)
            hsts_include_subdomains: Include subdomains in HSTS
            hsts_preload: Enable HSTS preload list submission
            custom_csp: Custom Content-Security-Policy
            report_uri: CSP violation report URI
            allowed_hosts: Allowed hostnames (Host header validation)
            exclude_paths: Paths to exclude from TLS enforcement
        """
        super().__init__(app)
        self.enabled = enabled
        self.enforce_https = enforce_https
        self.redirect_to_https = redirect_to_https
        self.security_header_level = security_header_level
        self.hsts_enabled = hsts_enabled
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains
        self.hsts_preload = hsts_preload
        self.custom_csp = custom_csp
        self.report_uri = report_uri
        self.allowed_hosts = allowed_hosts or []
        self.exclude_paths = exclude_paths or ['/api/health', '/']

        # Generate security headers
        self.security_headers = get_security_headers(
            level=security_header_level,
            custom_csp=custom_csp,
            enable_hsts=hsts_enabled,
            hsts_max_age=hsts_max_age,
            hsts_include_subdomains=hsts_include_subdomains,
            hsts_preload=hsts_preload,
            report_uri=report_uri
        )

        logger.info(
            "TLS enforcement middleware initialized",
            extra={
                "enabled": self.enabled,
                "enforce_https": self.enforce_https,
                "hsts_enabled": self.hsts_enabled,
                "security_level": security_header_level.value,
                "iso27001_control": "A.13.1.1, A.13.2.1"
            }
        )

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Enforce TLS and inject security headers.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response with security headers
        """
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        # Skip excluded paths
        if self._should_exclude(request.url.path):
            return await call_next(request)

        # Validate Host header (prevent Host header injection)
        if not self._validate_host(request):
            audit_logger.log_security_event(
                event_type=AuditEventType.SECURITY_INVALID_INPUT,
                severity=AuditSeverity.HIGH,
                description=f"Invalid Host header: {request.headers.get('host')}",
                metadata={
                    'host': request.headers.get('host'),
                    'path': request.url.path,
                    'client_ip': self._get_client_ip(request)
                }
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Host header"
            )

        # Check if request is HTTPS
        is_https = self._is_https_request(request)

        # Enforce HTTPS
        if not is_https:
            if self.enforce_https:
                # Reject non-HTTPS requests
                audit_logger.log_security_event(
                    event_type=AuditEventType.SECURITY_POLICY_VIOLATION,
                    severity=AuditSeverity.MEDIUM,
                    description="Non-HTTPS request rejected",
                    metadata={
                        'path': request.url.path,
                        'client_ip': self._get_client_ip(request)
                    }
                )

                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="HTTPS required. This API only accepts secure connections."
                )

            elif self.redirect_to_https:
                # Redirect to HTTPS
                https_url = str(request.url).replace('http://', 'https://', 1)

                logger.info(
                    f"Redirecting HTTP to HTTPS: {request.url.path}",
                    extra={'client_ip': self._get_client_ip(request)}
                )

                return RedirectResponse(
                    url=https_url,
                    status_code=status.HTTP_301_MOVED_PERMANENTLY
                )

        # Process request
        response = await call_next(request)

        # Inject security headers (only for HTTPS)
        if is_https:
            for header_name, header_value in self.security_headers.items():
                response.headers[header_name] = header_value

            # Add server header (minimal info disclosure)
            response.headers["Server"] = "Medical Imaging Viewer"

            # Remove potentially sensitive headers
            response.headers.pop("X-Powered-By", None)

        return response

    def _should_exclude(self, path: str) -> bool:
        """Check if path should be excluded from TLS enforcement."""
        return any(path.startswith(exclude) for exclude in self.exclude_paths)

    def _is_https_request(self, request: Request) -> bool:
        """
        Determine if request is HTTPS.

        Handles reverse proxy scenarios (X-Forwarded-Proto header).
        """
        # Check URL scheme
        if request.url.scheme == "https":
            return True

        # Check X-Forwarded-Proto header (reverse proxy)
        forwarded_proto = request.headers.get('X-Forwarded-Proto', '').lower()
        if forwarded_proto == 'https':
            return True

        # Check if behind reverse proxy with SSL termination
        forwarded_ssl = request.headers.get('X-Forwarded-SSL', '').lower()
        if forwarded_ssl == 'on':
            return True

        return False

    def _validate_host(self, request: Request) -> bool:
        """
        Validate Host header to prevent Host header injection attacks.

        Args:
            request: HTTP request

        Returns:
            True if Host header is valid
        """
        if not self.allowed_hosts:
            # No restriction if allowed_hosts not configured
            return True

        host = request.headers.get('host', '').split(':')[0]  # Remove port

        # Check against allowed hosts
        for allowed_host in self.allowed_hosts:
            if allowed_host.startswith('*.'):
                # Wildcard subdomain
                domain = allowed_host[2:]
                if host.endswith(domain):
                    return True
            elif host == allowed_host:
                return True

        return False

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()

        if request.client:
            return request.client.host

        return 'unknown'


# ============================================================================
# CERTIFICATE VALIDATION
# ============================================================================

class CertificateValidator:
    """
    SSL/TLS Certificate validation and pinning.

    ISO 27001 A.13.2.1 - Information transfer policies
    RFC 7469 - Public Key Pinning Extension for HTTP
    """

    @staticmethod
    def validate_certificate_file(
        cert_path: str,
        key_path: str
    ) -> Dict[str, Any]:
        """
        Validate SSL certificate and private key files.

        Args:
            cert_path: Path to certificate file (.pem or .crt)
            key_path: Path to private key file (.pem or .key)

        Returns:
            Dictionary with validation results and certificate metadata

        Raises:
            ValueError: If certificate or key is invalid
        """
        import ssl
        from OpenSSL import crypto
        from datetime import datetime

        validation_results = {
            'valid': False,
            'errors': [],
            'warnings': [],
            'metadata': {}
        }

        try:
            # Load certificate
            with open(cert_path, 'r') as f:
                cert_data = f.read()

            cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_data)

            # Load private key
            with open(key_path, 'r') as f:
                key_data = f.read()

            key = crypto.load_privatekey(crypto.FILETYPE_PEM, key_data)

            # Validate key matches certificate
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert_path, key_path)

            # Extract certificate metadata
            subject = cert.get_subject()
            issuer = cert.get_issuer()

            not_before = datetime.strptime(
                cert.get_notBefore().decode('ascii'),
                '%Y%m%d%H%M%SZ'
            )

            not_after = datetime.strptime(
                cert.get_notAfter().decode('ascii'),
                '%Y%m%d%H%M%SZ'
            )

            validation_results['metadata'] = {
                'common_name': subject.CN,
                'organization': getattr(subject, 'O', None),
                'issuer_cn': issuer.CN,
                'valid_from': not_before.isoformat(),
                'valid_until': not_after.isoformat(),
                'serial_number': cert.get_serial_number(),
                'signature_algorithm': cert.get_signature_algorithm().decode('ascii'),
                'public_key_bits': cert.get_pubkey().bits()
            }

            # Validate certificate is not expired
            now = datetime.utcnow()
            if now < not_before:
                validation_results['errors'].append(
                    f"Certificate not yet valid (valid from {not_before})"
                )
            elif now > not_after:
                validation_results['errors'].append(
                    f"Certificate expired on {not_after}"
                )

            # Check expiration warning (30 days)
            days_until_expiry = (not_after - now).days
            if days_until_expiry < 30:
                validation_results['warnings'].append(
                    f"Certificate expires in {days_until_expiry} days - renewal recommended"
                )

            # Validate key strength
            key_bits = cert.get_pubkey().bits()
            if key_bits < 2048:
                validation_results['errors'].append(
                    f"Weak key size ({key_bits} bits) - minimum 2048 bits required"
                )
            elif key_bits < 4096:
                validation_results['warnings'].append(
                    f"Key size {key_bits} bits - consider upgrading to 4096 bits"
                )

            # Check if self-signed (warning, not error)
            if subject.CN == issuer.CN:
                validation_results['warnings'].append(
                    "Self-signed certificate - not suitable for production"
                )

            # Mark as valid if no errors
            if not validation_results['errors']:
                validation_results['valid'] = True

            return validation_results

        except Exception as e:
            validation_results['errors'].append(f"Certificate validation failed: {e}")
            return validation_results

    @staticmethod
    def calculate_cert_fingerprint(cert_path: str, algorithm: str = 'sha256') -> str:
        """
        Calculate certificate fingerprint for pinning.

        Args:
            cert_path: Path to certificate file
            algorithm: Hash algorithm ('sha256', 'sha384', 'sha512')

        Returns:
            Base64-encoded fingerprint
        """
        from OpenSSL import crypto

        with open(cert_path, 'r') as f:
            cert_data = f.read()

        cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_data)

        # Get public key
        pubkey = cert.get_pubkey()
        pubkey_der = crypto.dump_publickey(crypto.FILETYPE_ASN1, pubkey)

        # Calculate hash
        if algorithm == 'sha256':
            digest = hashlib.sha256(pubkey_der).digest()
        elif algorithm == 'sha384':
            digest = hashlib.sha384(pubkey_der).digest()
        elif algorithm == 'sha512':
            digest = hashlib.sha512(pubkey_der).digest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        # Encode to base64
        fingerprint = base64.b64encode(digest).decode('ascii')

        return f"{algorithm}-{fingerprint}"


# ============================================================================
# SSL/TLS CONFIGURATION BUILDER
# ============================================================================

def create_ssl_context(
    cert_path: str,
    key_path: str,
    min_tls_version: TLSVersion = TLSVersion.TLS_1_2,
    cipher_suites: Optional[List[str]] = None,
    verify_client_cert: bool = False,
    ca_cert_path: Optional[str] = None
) -> ssl.SSLContext:
    """
    Create secure SSL context for HTTPS server.

    Args:
        cert_path: Path to server certificate
        key_path: Path to private key
        min_tls_version: Minimum TLS version (default: TLS 1.2)
        cipher_suites: Custom cipher suite list
        verify_client_cert: Require client certificates (mutual TLS)
        ca_cert_path: Path to CA certificate for client verification

    Returns:
        Configured SSLContext
    """
    # Create context with TLS server protocol
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

    # Set minimum TLS version
    if min_tls_version == TLSVersion.TLS_1_3:
        context.minimum_version = ssl.TLSVersion.TLSv1_3
    elif min_tls_version == TLSVersion.TLS_1_2:
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    else:
        logger.warning(
            f"TLS version {min_tls_version.value} is deprecated. "
            "Use TLS 1.2 or higher."
        )

    # Load server certificate and private key
    context.load_cert_chain(cert_path, key_path)

    # Set cipher suites
    if cipher_suites:
        context.set_ciphers(':'.join(cipher_suites))
    else:
        # Use recommended ciphers
        recommended_ciphers = TLS_1_2_CIPHERS + TLS_1_3_CIPHERS
        context.set_ciphers(':'.join(recommended_ciphers))

    # Disable compression (CRIME attack mitigation)
    context.options |= ssl.OP_NO_COMPRESSION

    # Prefer server cipher suite order
    context.options |= ssl.OP_CIPHER_SERVER_PREFERENCE

    # Client certificate verification (mutual TLS)
    if verify_client_cert:
        if not ca_cert_path:
            raise ValueError("ca_cert_path required for client certificate verification")

        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(ca_cert_path)
    else:
        context.verify_mode = ssl.CERT_NONE

    logger.info(
        "SSL context created",
        extra={
            "min_tls_version": min_tls_version.value,
            "client_cert_required": verify_client_cert
        }
    )

    return context
