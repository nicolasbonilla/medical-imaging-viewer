# TLS/SSL Certificate Management Scripts

**Medical Imaging Viewer - Certificate Lifecycle Management**

This directory contains scripts for managing TLS/SSL certificates in the Medical Imaging Viewer application.

---

## Scripts Overview

| Script | Purpose | Usage |
|--------|---------|-------|
| `generate_certificate.sh` | Generate certificates (dev/prod) | Development, CSR generation, Let's Encrypt |
| `check_certificate_expiry.sh` | Monitor certificate expiry | Cron job for expiry alerts |
| `validate_certificate.py` | Validate certificates | Pre-deployment validation |

---

## Quick Start

### 1. Development Certificate (Self-Signed)

```bash
# Generate self-signed certificate for local development
./generate_certificate.sh development

# Certificate created at: ../certs/dev-cert.pem
# Private key created at: ../certs/dev-key.pem

# Run application with HTTPS
uvicorn app.main:app \
  --ssl-keyfile certs/dev-key.pem \
  --ssl-certfile certs/dev-cert.pem \
  --port 8443
```

**Access**: https://localhost:8443 (accept browser warning for self-signed certificate)

### 2. Production Certificate (Let's Encrypt)

```bash
# Prerequisites: Domain name, port 80/443 open, DNS configured

# Obtain Let's Encrypt certificate
DOMAIN=medical-imaging-viewer.com \
EMAIL=admin@medical-imaging-viewer.com \
./generate_certificate.sh letsencrypt

# Certificate created at: /etc/letsencrypt/live/medical-imaging-viewer.com/fullchain.pem
# Private key created at: /etc/letsencrypt/live/medical-imaging-viewer.com/privkey.pem

# Update .env
TLS_CERT_FILE=/etc/letsencrypt/live/medical-imaging-viewer.com/fullchain.pem
TLS_KEY_FILE=/etc/letsencrypt/live/medical-imaging-viewer.com/privkey.pem
```

### 3. Commercial CA Certificate (DigiCert, GlobalSign, etc.)

```bash
# Step 1: Generate CSR
COMMON_NAME=medical-imaging-viewer.com \
ORGANIZATION="Medical Imaging Viewer Inc." \
./generate_certificate.sh csr

# Step 2: Submit CSR to CA
# - Upload ../certs/production-csr.pem to CA portal
# - Complete domain validation (email, DNS, HTTP)
# - Download signed certificate

# Step 3: Save certificate
# - Save signed certificate as: ../certs/production-cert.pem
# - Save intermediate certificates (chain) as: ../certs/ca-bundle.pem

# Step 4: Validate certificate
python validate_certificate.py \
  ../certs/production-cert.pem \
  ../certs/production-key.pem

# Step 5: Verify chain
python validate_certificate.py --chain \
  ../certs/production-cert.pem \
  ../certs/ca-bundle.pem
```

---

## Script Details

### generate_certificate.sh

**Purpose**: Generate and manage TLS/SSL certificates

**Commands**:

```bash
# Development (self-signed)
./generate_certificate.sh development

# CSR for commercial CA
COMMON_NAME=example.com ./generate_certificate.sh csr

# Let's Encrypt (auto-HTTPS)
DOMAIN=example.com ./generate_certificate.sh letsencrypt

# Validate certificate
CERT_FILE=path/to/cert.pem KEY_FILE=path/to/key.pem ./generate_certificate.sh validate

# Help
./generate_certificate.sh help
```

**Environment Variables**:

| Variable | Description | Default |
|----------|-------------|---------|
| `COMMON_NAME` | Domain name | localhost |
| `COUNTRY` | Country code | US |
| `STATE` | State/Province | California |
| `LOCALITY` | City | San Francisco |
| `ORGANIZATION` | Organization name | Medical Imaging Viewer |
| `KEY_ALGORITHM` | RSA or ECDSA | RSA |
| `KEY_SIZE` | RSA key size | 4096 |
| `CURVE` | ECDSA curve | prime256v1 (P-256) |
| `DAYS` | Validity period | 365 |
| `DOMAIN` | Let's Encrypt domain | (required) |
| `EMAIL` | Let's Encrypt email | admin@$DOMAIN |

**Examples**:

```bash
# RSA 4096 development certificate
./generate_certificate.sh development

# ECDSA P-256 development certificate (faster)
KEY_ALGORITHM=ECDSA CURVE=prime256v1 ./generate_certificate.sh development

# ECDSA P-384 development certificate (more secure)
KEY_ALGORITHM=ECDSA CURVE=secp384r1 ./generate_certificate.sh development

# Multi-domain Let's Encrypt
DOMAIN=example.com \
ADDITIONAL_DOMAINS="www.example.com,api.example.com" \
./generate_certificate.sh letsencrypt
```

---

### check_certificate_expiry.sh

**Purpose**: Monitor certificate expiry and send alerts

**Usage**:

```bash
# Check specific certificate
./check_certificate_expiry.sh /etc/letsencrypt/live/example.com/fullchain.pem

# Check all configured certificates
./check_certificate_expiry.sh

# Enable email alerts
ENABLE_EMAIL_ALERTS=true \
ALERT_EMAIL=security@example.com \
./check_certificate_expiry.sh
```

**Alert Thresholds**:

- **CRITICAL** (🔴): Certificate expires in ≤ 7 days (or already expired)
- **WARNING** (⚠️): Certificate expires in ≤ 30 days
- **OK** (✓): Certificate valid for > 30 days

**Cron Setup** (Daily Monitoring):

```bash
# Edit crontab
crontab -e

# Add daily check at 9 AM with email alerts
0 9 * * * ENABLE_EMAIL_ALERTS=true ALERT_EMAIL=security@example.com /path/to/check_certificate_expiry.sh >> /var/log/cert-expiry.log 2>&1
```

**Email Configuration**:

```bash
# Ubuntu/Debian
sudo apt-get install mailutils

# CentOS/RHEL
sudo yum install mailx

# Test email
echo "Test message" | mail -s "Test Subject" your-email@example.com
```

**Environment Variables**:

| Variable | Description | Default |
|----------|-------------|---------|
| `ALERT_EMAIL` | Email for alerts | security@medical-imaging-viewer.com |
| `ENABLE_EMAIL_ALERTS` | Enable email alerts | false |
| `LOG_FILE` | Log file path | /var/log/cert-expiry-check.log |

---

### validate_certificate.py

**Purpose**: Validate certificates with detailed analysis

**Usage**:

```bash
# Validate certificate and key
python validate_certificate.py cert.pem key.pem

# Calculate fingerprint (SHA-256)
python validate_certificate.py --fingerprint cert.pem

# Calculate fingerprint (SHA-384, more secure)
python validate_certificate.py --fingerprint cert.pem --algorithm sha384

# Verify certificate chain
python validate_certificate.py --chain cert.pem ca-bundle.pem

# Help
python validate_certificate.py --help
```

**Validation Checks**:

1. ✅ **File Loading**: Certificate and key files exist and are readable
2. ✅ **Format Validation**: Valid PEM format
3. ✅ **Key Match**: Private key matches certificate public key
4. ✅ **Expiry Check**: Certificate is not expired
5. ✅ **Expiry Warning**: Alert if expiring within 30 days
6. ✅ **Key Strength**: Minimum 2048-bit RSA or 256-bit ECDSA
7. ✅ **Self-Signed Detection**: Warning if self-signed (not for production)

**Output Example**:

```
======================================================================
           TLS/SSL Certificate Validation
======================================================================

Certificate Details
-------------------
  Common Name: medical-imaging-viewer.com
  Organization: Medical Imaging Viewer Inc.
  Issuer: Let's Encrypt Authority X3

  Valid From: 2025-10-23T00:00:00
  Valid Until: 2026-01-21T23:59:59

  Serial Number: 123456789012345678901234567890
  Signature Algorithm: sha256WithRSAEncryption
  Public Key Size: 2048 bits
  Key Strength: Good (2048+ bits)

Warnings
--------
⚠ Certificate expires in 25 days - renewal recommended

Validation Result
-----------------
✓ Certificate is VALID

Recommendations:
  • Renew certificate before expiry to avoid service disruption
```

---

## Certificate Types

### 1. Self-Signed Certificate (Development)

**Pros**:
- Free
- Instant generation
- No domain required

**Cons**:
- Browser warnings
- Not trusted by clients
- Manual trust configuration

**Use Case**: Local development only

**Generation**:
```bash
./generate_certificate.sh development
```

### 2. Let's Encrypt (Production - Free)

**Pros**:
- Free
- Automated renewal
- Trusted by all browsers
- Quick issuance (minutes)

**Cons**:
- 90-day validity (requires auto-renewal)
- Requires domain ownership
- Rate limits (20/week per domain)

**Use Case**: Most production deployments

**Generation**:
```bash
DOMAIN=example.com ./generate_certificate.sh letsencrypt
```

**Auto-Renewal**:
```bash
# Cron job (daily check, renews if needed)
0 3 * * * /usr/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"
```

### 3. Commercial CA (Production - Paid)

**Pros**:
- Extended validation (EV) certificates available
- 1-year+ validity
- No rate limits
- Insurance/warranty (some CAs)

**Cons**:
- Cost ($10-$1000+/year)
- Manual renewal process
- Slower issuance (hours to days)

**Use Case**: Enterprise, high-assurance applications

**Recommended CAs**:
- DigiCert
- GlobalSign
- Sectigo (Comodo)
- GoDaddy

**Generation**:
```bash
COMMON_NAME=example.com ./generate_certificate.sh csr
# Submit CSR to CA portal
```

---

## Key Algorithms

### RSA (Widely Supported)

**Recommended Sizes**:
- **2048-bit**: Minimum for production
- **4096-bit**: Recommended for high-security applications

**Performance**: Slower than ECDSA

**Example**:
```bash
KEY_ALGORITHM=RSA KEY_SIZE=4096 ./generate_certificate.sh development
```

### ECDSA (Faster, Smaller)

**Recommended Curves**:
- **P-256 (prime256v1)**: Equivalent to RSA 2048 security
- **P-384 (secp384r1)**: Equivalent to RSA 3072 security

**Performance**: 10x faster than RSA for same security level

**Example**:
```bash
KEY_ALGORITHM=ECDSA CURVE=prime256v1 ./generate_certificate.sh development
```

**Comparison**:

| Feature | RSA 2048 | RSA 4096 | ECDSA P-256 | ECDSA P-384 |
|---------|----------|----------|-------------|-------------|
| Security | 112-bit | 128-bit | 128-bit | 192-bit |
| Key Size | 2048 bits | 4096 bits | 256 bits | 384 bits |
| Cert Size | ~1 KB | ~2 KB | ~500 bytes | ~600 bytes |
| Performance | Medium | Slow | Fast | Fast |
| Support | Excellent | Excellent | Good | Good |

**Recommendation**: ECDSA P-256 for new deployments (faster, same security as RSA 2048)

---

## Certificate Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│  1. Generation                                               │
│     - Self-signed: Instant                                   │
│     - Let's Encrypt: ~5 minutes                              │
│     - Commercial CA: Hours to days                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Validation                                               │
│     python validate_certificate.py cert.pem key.pem          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Installation                                             │
│     - Update .env: TLS_CERT_FILE, TLS_KEY_FILE               │
│     - Restart server: systemctl restart medical-imaging-viewer│
│     - Test: curl -I https://example.com                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Monitoring (Daily)                                       │
│     ./check_certificate_expiry.sh                            │
│     Alert if expiring < 30 days                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Renewal (30 days before expiry)                          │
│     - Let's Encrypt: certbot renew (automatic)               │
│     - Commercial CA: Regenerate CSR, submit to CA            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    (Back to Step 2: Validation)
```

---

## Troubleshooting

### Issue: "Permission denied" when running scripts

**Solution**:
```bash
# Make scripts executable
chmod +x generate_certificate.sh
chmod +x check_certificate_expiry.sh
chmod +x validate_certificate.py
```

### Issue: "certbot: command not found"

**Solution**:
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install certbot

# CentOS/RHEL
sudo yum install certbot

# macOS
brew install certbot
```

### Issue: Let's Encrypt validation fails

**Common Causes**:
- Port 80/443 not accessible
- DNS not configured
- Firewall blocking

**Solution**:
```bash
# Check DNS
dig example.com

# Check port 80 open
curl http://example.com/.well-known/acme-challenge/test

# Temporarily stop web server (standalone mode requires port 80)
systemctl stop nginx
certbot certonly --standalone -d example.com
systemctl start nginx
```

### Issue: "Certificate expired" but renewal failed

**Solution**:
```bash
# Force renewal
certbot renew --force-renewal

# If still failing, delete and recreate
certbot delete --cert-name example.com
DOMAIN=example.com ./generate_certificate.sh letsencrypt
```

### Issue: Browser shows "Certificate not trusted"

**Causes**:
- Self-signed certificate (expected)
- Incomplete certificate chain
- Wrong certificate file

**Solution**:
```bash
# Use fullchain.pem (includes intermediates)
TLS_CERT_FILE=/etc/letsencrypt/live/example.com/fullchain.pem  # ✓
# NOT cert.pem (only end-entity certificate)
TLS_CERT_FILE=/etc/letsencrypt/live/example.com/cert.pem  # ✗

# Verify chain
python validate_certificate.py --chain cert.pem ca-bundle.pem
```

---

## Security Best Practices

### 1. File Permissions

```bash
# Private keys: Read-only by owner
chmod 600 /path/to/private-key.pem

# Certificates: Read-only by all
chmod 644 /path/to/certificate.pem

# Scripts: Executable by owner
chmod 700 /path/to/scripts/*.sh
```

### 2. Private Key Protection

- ❌ Never commit private keys to version control
- ❌ Never share private keys via email/Slack
- ❌ Never store private keys in application code
- ✅ Store in secure location with restricted permissions
- ✅ Use environment variables for paths (.env)
- ✅ Rotate keys regularly (every 1-2 years)

### 3. Certificate Renewal

- Renew 30 days before expiry
- Set up monitoring (daily cron job)
- Test renewal process before expiry
- Have backup certificate ready

### 4. Key Size

- **Minimum**: RSA 2048-bit or ECDSA P-256
- **Recommended**: RSA 4096-bit or ECDSA P-384
- **Never**: RSA < 2048-bit (weak, deprecated)

### 5. Self-Signed Certificates

- ⚠️ Development only
- ⚠️ Never use in production
- ⚠️ Browser warnings expected
- ⚠️ Clients won't trust by default

---

## ISO 27001 Compliance

| Control | Requirement | Implementation |
|---------|-------------|----------------|
| **A.10.1.2** | Key management | Automated expiry monitoring, rotation procedures |
| **A.13.1.1** | Network controls | TLS 1.2+ enforcement, strong key sizes |
| **A.12.4.1** | Event logging | Certificate expiry logging, audit trail |
| **A.18.1.5** | Statutory requirements | Certificate validation before deployment |

---

## Support

For issues or questions:
- Documentation: `../TLS_ENFORCEMENT_GUIDE.md`
- Code: `../app/core/security/tls_enforcement.py`
- Environment Configuration: `../.env.example`

---

**Last Updated**: 2025-11-23
**Version**: 1.0.0
**Maintained By**: Security Team
