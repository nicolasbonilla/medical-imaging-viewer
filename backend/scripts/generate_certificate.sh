#!/bin/bash
#
# Certificate Generation Script
# Medical Imaging Viewer - TLS/SSL Certificate Management
#
# ISO 27001 A.10.1.2 - Key management
# ISO 27001 A.13.1.1 - Network controls
#
# Usage:
#   ./generate_certificate.sh development  # Self-signed for development
#   ./generate_certificate.sh production   # Let's Encrypt for production
#

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CERTS_DIR="$PROJECT_ROOT/certs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function: Generate self-signed certificate for development
generate_dev_certificate() {
    log_info "Generating self-signed certificate for development..."

    mkdir -p "$CERTS_DIR"

    # Certificate details
    COMMON_NAME="${COMMON_NAME:-localhost}"
    COUNTRY="${COUNTRY:-US}"
    STATE="${STATE:-California}"
    LOCALITY="${LOCALITY:-San Francisco}"
    ORGANIZATION="${ORGANIZATION:-Medical Imaging Viewer Dev}"
    DAYS="${DAYS:-365}"

    # Key algorithm (RSA or ECDSA)
    KEY_ALGORITHM="${KEY_ALGORITHM:-RSA}"

    if [ "$KEY_ALGORITHM" = "RSA" ]; then
        KEY_SIZE="${KEY_SIZE:-4096}"
        log_info "Generating RSA private key ($KEY_SIZE bits)..."
        openssl genrsa -out "$CERTS_DIR/dev-key.pem" "$KEY_SIZE"
    elif [ "$KEY_ALGORITHM" = "ECDSA" ]; then
        CURVE="${CURVE:-prime256v1}"  # P-256
        log_info "Generating ECDSA private key (curve: $CURVE)..."
        openssl ecparam -genkey -name "$CURVE" -out "$CERTS_DIR/dev-key.pem"
    else
        log_error "Invalid KEY_ALGORITHM: $KEY_ALGORITHM (use RSA or ECDSA)"
        exit 1
    fi

    log_info "Generating self-signed certificate (valid for $DAYS days)..."
    openssl req -new -x509 \
        -key "$CERTS_DIR/dev-key.pem" \
        -out "$CERTS_DIR/dev-cert.pem" \
        -days "$DAYS" \
        -subj "/C=$COUNTRY/ST=$STATE/L=$LOCALITY/O=$ORGANIZATION/CN=$COMMON_NAME" \
        -addext "subjectAltName=DNS:$COMMON_NAME,DNS:*.localhost,IP:127.0.0.1"

    # Set permissions (private key readable only by owner)
    chmod 600 "$CERTS_DIR/dev-key.pem"
    chmod 644 "$CERTS_DIR/dev-cert.pem"

    log_info "Certificate generated successfully!"
    echo
    log_info "Certificate: $CERTS_DIR/dev-cert.pem"
    log_info "Private Key: $CERTS_DIR/dev-key.pem"
    echo

    # Display certificate details
    log_info "Certificate Details:"
    openssl x509 -in "$CERTS_DIR/dev-cert.pem" -noout -subject -issuer -dates -ext subjectAltName

    echo
    log_warn "⚠️  WARNING: This is a self-signed certificate for DEVELOPMENT ONLY"
    log_warn "⚠️  Do NOT use in production. Obtain a certificate from a trusted CA."
    echo

    # Instructions for trusting certificate
    log_info "To trust this certificate in your browser:"
    echo "  1. Open browser settings → Security → Certificates"
    echo "  2. Import $CERTS_DIR/dev-cert.pem as a trusted authority"
    echo "  3. Restart browser"
    echo
    log_info "To use with curl (disable verification):"
    echo "  curl --insecure https://localhost:8443"
    echo
}

# Function: Generate CSR for commercial CA
generate_csr() {
    log_info "Generating Certificate Signing Request (CSR) for commercial CA..."

    mkdir -p "$CERTS_DIR"

    # Certificate details (required)
    if [ -z "$COMMON_NAME" ]; then
        log_error "COMMON_NAME is required (e.g., medical-imaging-viewer.com)"
        echo "Usage: COMMON_NAME=example.com $0 csr"
        exit 1
    fi

    COUNTRY="${COUNTRY:-US}"
    STATE="${STATE:-California}"
    LOCALITY="${LOCALITY:-San Francisco}"
    ORGANIZATION="${ORGANIZATION:-Medical Imaging Viewer Inc.}"

    # Key algorithm
    KEY_ALGORITHM="${KEY_ALGORITHM:-RSA}"

    if [ "$KEY_ALGORITHM" = "RSA" ]; then
        KEY_SIZE="${KEY_SIZE:-4096}"
        log_info "Generating RSA private key ($KEY_SIZE bits)..."
        openssl genrsa -out "$CERTS_DIR/production-key.pem" "$KEY_SIZE"
    elif [ "$KEY_ALGORITHM" = "ECDSA" ]; then
        CURVE="${CURVE:-prime256v1}"
        log_info "Generating ECDSA private key (curve: $CURVE)..."
        openssl ecparam -genkey -name "$CURVE" -out "$CERTS_DIR/production-key.pem"
    else
        log_error "Invalid KEY_ALGORITHM: $KEY_ALGORITHM"
        exit 1
    fi

    chmod 600 "$CERTS_DIR/production-key.pem"

    log_info "Generating CSR..."
    openssl req -new \
        -key "$CERTS_DIR/production-key.pem" \
        -out "$CERTS_DIR/production-csr.pem" \
        -subj "/C=$COUNTRY/ST=$STATE/L=$LOCALITY/O=$ORGANIZATION/CN=$COMMON_NAME" \
        -addext "subjectAltName=DNS:$COMMON_NAME,DNS:www.$COMMON_NAME"

    log_info "CSR generated successfully!"
    echo
    log_info "CSR File: $CERTS_DIR/production-csr.pem"
    log_info "Private Key: $CERTS_DIR/production-key.pem"
    echo

    # Display CSR details
    log_info "CSR Details:"
    openssl req -in "$CERTS_DIR/production-csr.pem" -noout -subject -text | grep -A1 "Subject:"
    echo

    log_info "Next steps:"
    echo "  1. Submit $CERTS_DIR/production-csr.pem to your CA (DigiCert, GlobalSign, etc.)"
    echo "  2. Complete domain validation (email, DNS, or HTTP challenge)"
    echo "  3. Download signed certificate from CA"
    echo "  4. Save as $CERTS_DIR/production-cert.pem"
    echo "  5. Verify: openssl verify -CAfile ca-bundle.crt production-cert.pem"
    echo
}

# Function: Setup Let's Encrypt certificate
setup_letsencrypt() {
    log_info "Setting up Let's Encrypt certificate..."

    # Check if certbot is installed
    if ! command -v certbot &> /dev/null; then
        log_error "certbot is not installed"
        echo
        echo "Install certbot:"
        echo "  Ubuntu/Debian: sudo apt-get install certbot"
        echo "  CentOS/RHEL: sudo yum install certbot"
        echo "  macOS: brew install certbot"
        exit 1
    fi

    # Domain name (required)
    if [ -z "$DOMAIN" ]; then
        log_error "DOMAIN is required (e.g., medical-imaging-viewer.com)"
        echo "Usage: DOMAIN=example.com $0 letsencrypt"
        exit 1
    fi

    # Email for renewal notifications
    EMAIL="${EMAIL:-admin@$DOMAIN}"

    # Additional domains (comma-separated)
    ADDITIONAL_DOMAINS="${ADDITIONAL_DOMAINS:-www.$DOMAIN}"

    # Build certbot command
    CERTBOT_CMD="certbot certonly --standalone"
    CERTBOT_CMD="$CERTBOT_CMD -d $DOMAIN"

    # Add additional domains
    IFS=',' read -ra DOMAINS <<< "$ADDITIONAL_DOMAINS"
    for additional_domain in "${DOMAINS[@]}"; do
        CERTBOT_CMD="$CERTBOT_CMD -d $(echo $additional_domain | xargs)"  # xargs trims whitespace
    done

    CERTBOT_CMD="$CERTBOT_CMD --email $EMAIL"
    CERTBOT_CMD="$CERTBOT_CMD --agree-tos"
    CERTBOT_CMD="$CERTBOT_CMD --non-interactive"

    log_info "Running certbot..."
    log_info "Command: $CERTBOT_CMD"
    echo

    # Run certbot (requires sudo)
    if [ "$EUID" -ne 0 ]; then
        log_warn "certbot requires root privileges. Running with sudo..."
        sudo $CERTBOT_CMD
    else
        $CERTBOT_CMD
    fi

    # Certificate location
    CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
    KEY_PATH="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

    log_info "Let's Encrypt certificate obtained successfully!"
    echo
    log_info "Certificate: $CERT_PATH"
    log_info "Private Key: $KEY_PATH"
    log_info "Chain: /etc/letsencrypt/live/$DOMAIN/chain.pem"
    echo

    # Display certificate details
    log_info "Certificate Details:"
    sudo openssl x509 -in "$CERT_PATH" -noout -subject -issuer -dates
    echo

    # Setup automatic renewal
    log_info "Setting up automatic renewal (cron job)..."

    # Check if cron job already exists
    if sudo crontab -l 2>/dev/null | grep -q "certbot renew"; then
        log_info "Cron job already exists"
    else
        # Add cron job (run daily at 3 AM)
        (sudo crontab -l 2>/dev/null; echo "0 3 * * * /usr/bin/certbot renew --quiet --deploy-hook 'systemctl reload nginx'") | sudo crontab -
        log_info "Cron job added: Daily renewal check at 3 AM"
    fi

    echo
    log_info "Next steps:"
    echo "  1. Update .env with certificate paths:"
    echo "     TLS_CERT_FILE=$CERT_PATH"
    echo "     TLS_KEY_FILE=$KEY_PATH"
    echo "  2. Restart application: systemctl restart medical-imaging-viewer"
    echo "  3. Test HTTPS: curl -I https://$DOMAIN"
    echo
}

# Function: Validate certificate
validate_certificate() {
    log_info "Validating certificate..."

    CERT_FILE="${CERT_FILE:-$CERTS_DIR/dev-cert.pem}"
    KEY_FILE="${KEY_FILE:-$CERTS_DIR/dev-key.pem}"

    if [ ! -f "$CERT_FILE" ]; then
        log_error "Certificate file not found: $CERT_FILE"
        exit 1
    fi

    if [ ! -f "$KEY_FILE" ]; then
        log_error "Private key file not found: $KEY_FILE"
        exit 1
    fi

    log_info "Validating certificate: $CERT_FILE"
    log_info "Private key: $KEY_FILE"
    echo

    # Use Python validation script if available
    if [ -f "$SCRIPT_DIR/validate_certificate.py" ]; then
        python3 "$SCRIPT_DIR/validate_certificate.py" "$CERT_FILE" "$KEY_FILE"
    else
        # Fallback to openssl validation
        log_info "Certificate Details:"
        openssl x509 -in "$CERT_FILE" -noout -subject -issuer -dates -ext subjectAltName
        echo

        log_info "Verifying private key matches certificate..."
        CERT_MODULUS=$(openssl x509 -in "$CERT_FILE" -noout -modulus | md5sum)
        KEY_MODULUS=$(openssl rsa -in "$KEY_FILE" -noout -modulus 2>/dev/null | md5sum)

        if [ "$CERT_MODULUS" = "$KEY_MODULUS" ]; then
            log_info "✓ Private key matches certificate"
        else
            log_error "✗ Private key does NOT match certificate"
            exit 1
        fi
    fi
}

# Function: Display help
show_help() {
    cat << EOF
Certificate Generation Script
Medical Imaging Viewer - TLS/SSL Certificate Management

Usage:
  $0 <command> [options]

Commands:
  development   Generate self-signed certificate for development
  csr           Generate CSR for commercial CA
  letsencrypt   Setup Let's Encrypt certificate (production)
  validate      Validate existing certificate
  help          Show this help message

Options (environment variables):
  COMMON_NAME       Domain name (e.g., medical-imaging-viewer.com)
  COUNTRY           Country code (default: US)
  STATE             State/Province (default: California)
  LOCALITY          City (default: San Francisco)
  ORGANIZATION      Organization name
  KEY_ALGORITHM     RSA or ECDSA (default: RSA)
  KEY_SIZE          RSA key size (default: 4096)
  CURVE             ECDSA curve (default: prime256v1)
  DAYS              Certificate validity in days (default: 365)
  DOMAIN            Domain for Let's Encrypt
  EMAIL             Email for Let's Encrypt notifications

Examples:
  # Development (RSA 4096)
  $0 development

  # Development (ECDSA P-256, faster)
  KEY_ALGORITHM=ECDSA CURVE=prime256v1 $0 development

  # Generate CSR for commercial CA
  COMMON_NAME=medical-imaging-viewer.com $0 csr

  # Let's Encrypt certificate
  DOMAIN=medical-imaging-viewer.com EMAIL=admin@example.com $0 letsencrypt

  # Validate certificate
  CERT_FILE=/path/to/cert.pem KEY_FILE=/path/to/key.pem $0 validate

Security Notes:
  - Development certificates are self-signed and NOT suitable for production
  - Let's Encrypt certificates are free and auto-renewable (90-day validity)
  - Commercial CA certificates typically have 1-year validity
  - Always use RSA 2048+ or ECDSA P-256+ for production
  - Store private keys securely (chmod 600)

EOF
}

# Main script
main() {
    case "${1:-help}" in
        development|dev)
            generate_dev_certificate
            ;;
        csr)
            generate_csr
            ;;
        letsencrypt|le)
            setup_letsencrypt
            ;;
        validate|check)
            validate_certificate
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown command: $1"
            echo
            show_help
            exit 1
            ;;
    esac
}

main "$@"
