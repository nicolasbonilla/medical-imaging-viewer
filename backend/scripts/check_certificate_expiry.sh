#!/bin/bash
#
# Certificate Expiry Monitoring Script
# Medical Imaging Viewer - TLS/SSL Certificate Lifecycle Management
#
# ISO 27001 A.10.1.2 - Key management
# ISO 27001 A.12.4.1 - Event logging
#
# Usage:
#   ./check_certificate_expiry.sh /path/to/cert.pem
#   ./check_certificate_expiry.sh  # Uses .env configuration
#
# Cron Schedule:
#   0 9 * * * /path/to/check_certificate_expiry.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Alert thresholds (days)
CRITICAL_THRESHOLD=7
WARNING_THRESHOLD=30

# Email configuration (optional)
ALERT_EMAIL="${ALERT_EMAIL:-security@medical-imaging-viewer.com}"
ENABLE_EMAIL_ALERTS="${ENABLE_EMAIL_ALERTS:-false}"

# Log file
LOG_FILE="${LOG_FILE:-/var/log/cert-expiry-check.log}"

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
    log "INFO: $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    log "WARN: $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    log "ERROR: $1"
}

# Function: Send email alert
send_email_alert() {
    local subject="$1"
    local message="$2"

    if [ "$ENABLE_EMAIL_ALERTS" = "true" ]; then
        if command -v mail &> /dev/null; then
            echo "$message" | mail -s "$subject" "$ALERT_EMAIL"
            log_info "Email alert sent to $ALERT_EMAIL"
        elif command -v sendmail &> /dev/null; then
            {
                echo "Subject: $subject"
                echo "To: $ALERT_EMAIL"
                echo
                echo "$message"
            } | sendmail "$ALERT_EMAIL"
            log_info "Email alert sent to $ALERT_EMAIL (sendmail)"
        else
            log_warn "Email command not found. Install 'mailutils' or 'sendmail'"
        fi
    fi
}

# Function: Check certificate expiry
check_certificate() {
    local cert_path="$1"

    if [ ! -f "$cert_path" ]; then
        log_error "Certificate file not found: $cert_path"
        return 1
    fi

    log_info "Checking certificate: $cert_path"

    # Extract certificate details
    local common_name=$(openssl x509 -in "$cert_path" -noout -subject | sed 's/.*CN = //')
    local issuer=$(openssl x509 -in "$cert_path" -noout -issuer | sed 's/.*CN = //')
    local not_after=$(openssl x509 -in "$cert_path" -noout -enddate | cut -d= -f2)

    # Convert expiry date to epoch
    local expiry_epoch
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        expiry_epoch=$(date -j -f "%b %d %T %Y %Z" "$not_after" +%s)
    else
        # Linux
        expiry_epoch=$(date -d "$not_after" +%s)
    fi

    local now_epoch=$(date +%s)
    local days_until_expiry=$(( ($expiry_epoch - $now_epoch) / 86400 ))

    # Display certificate info
    echo
    echo "Certificate Information:"
    echo "  Common Name: $common_name"
    echo "  Issuer: $issuer"
    echo "  Expires: $not_after"
    echo "  Days Until Expiry: $days_until_expiry"
    echo

    # Check expiry status
    if [ $days_until_expiry -lt 0 ]; then
        # EXPIRED
        log_error "❌ Certificate EXPIRED $((-days_until_expiry)) days ago!"
        send_email_alert \
            "CRITICAL: TLS Certificate EXPIRED - $common_name" \
            "Certificate for $common_name has EXPIRED $((-days_until_expiry)) days ago.

Certificate Details:
  Common Name: $common_name
  Issuer: $issuer
  Expired On: $not_after

IMMEDIATE ACTION REQUIRED:
  1. Renew certificate immediately
  2. Install new certificate
  3. Restart web server
  4. Verify HTTPS connectivity

Certificate Path: $cert_path
"
        return 2

    elif [ $days_until_expiry -le $CRITICAL_THRESHOLD ]; then
        # CRITICAL (expires within 7 days)
        log_error "🔴 Certificate expires in $days_until_expiry days - CRITICAL!"
        send_email_alert \
            "CRITICAL: TLS Certificate Expiring Soon - $common_name" \
            "Certificate for $common_name expires in $days_until_expiry days.

Certificate Details:
  Common Name: $common_name
  Issuer: $issuer
  Expires On: $not_after

URGENT ACTION REQUIRED:
  1. Renew certificate immediately
  2. Install new certificate before expiry
  3. Restart web server
  4. Verify HTTPS connectivity

Let's Encrypt Renewal:
  sudo certbot renew --force-renewal

Certificate Path: $cert_path
"
        return 1

    elif [ $days_until_expiry -le $WARNING_THRESHOLD ]; then
        # WARNING (expires within 30 days)
        log_warn "⚠️  Certificate expires in $days_until_expiry days - renewal recommended"
        send_email_alert \
            "WARNING: TLS Certificate Expiring Soon - $common_name" \
            "Certificate for $common_name expires in $days_until_expiry days.

Certificate Details:
  Common Name: $common_name
  Issuer: $issuer
  Expires On: $not_after

ACTION RECOMMENDED:
  1. Schedule certificate renewal
  2. Plan maintenance window for installation
  3. Test renewal process in staging

Let's Encrypt Renewal:
  sudo certbot renew

Certificate Path: $cert_path
"
        return 0

    else
        # OK
        log_info "✓ Certificate valid for $days_until_expiry days"
        return 0
    fi
}

# Function: Check all configured certificates
check_all_certificates() {
    local exit_code=0

    # Check if .env file exists
    if [ -f "$PROJECT_ROOT/.env" ]; then
        log_info "Loading configuration from .env..."

        # Source .env to get certificate paths
        # shellcheck disable=SC1090
        source <(grep -v '^#' "$PROJECT_ROOT/.env" | grep -E '^(TLS_CERT_FILE|TLS_KEY_FILE)=' | sed 's/^/export /')

        if [ -n "$TLS_CERT_FILE" ]; then
            check_certificate "$TLS_CERT_FILE" || exit_code=$?
        else
            log_warn "TLS_CERT_FILE not set in .env"
        fi
    fi

    # Check Let's Encrypt certificates if exist
    if [ -d "/etc/letsencrypt/live" ]; then
        log_info "Checking Let's Encrypt certificates..."

        for domain_dir in /etc/letsencrypt/live/*/; do
            if [ -f "$domain_dir/fullchain.pem" ]; then
                check_certificate "$domain_dir/fullchain.pem" || exit_code=$?
            fi
        done
    fi

    # Check development certificates
    if [ -f "$PROJECT_ROOT/certs/dev-cert.pem" ]; then
        log_info "Checking development certificate..."
        check_certificate "$PROJECT_ROOT/certs/dev-cert.pem" || exit_code=$?
    fi

    return $exit_code
}

# Function: Display help
show_help() {
    cat << EOF
Certificate Expiry Monitoring Script
Medical Imaging Viewer - TLS/SSL Certificate Lifecycle Management

Usage:
  $0 [certificate_file]
  $0  # Check all configured certificates

Options:
  certificate_file    Path to certificate file (.pem, .crt)
                      If not provided, checks all configured certificates

Environment Variables:
  ALERT_EMAIL              Email address for alerts (default: security@medical-imaging-viewer.com)
  ENABLE_EMAIL_ALERTS      Enable email alerts (true/false, default: false)
  LOG_FILE                 Log file path (default: /var/log/cert-expiry-check.log)

Alert Thresholds:
  CRITICAL: Certificate expires in <= 7 days (or already expired)
  WARNING:  Certificate expires in <= 30 days
  OK:       Certificate valid for > 30 days

Exit Codes:
  0  Certificate valid (> 30 days) or warning (7-30 days)
  1  Certificate expiring soon (<= 7 days)
  2  Certificate expired

Examples:
  # Check specific certificate
  $0 /etc/letsencrypt/live/example.com/fullchain.pem

  # Check all configured certificates
  $0

  # Enable email alerts
  ENABLE_EMAIL_ALERTS=true ALERT_EMAIL=admin@example.com $0

  # Cron job (daily at 9 AM)
  0 9 * * * ENABLE_EMAIL_ALERTS=true $0 >> /var/log/cert-expiry.log 2>&1

Setup Email Alerts:
  Ubuntu/Debian:
    sudo apt-get install mailutils
    echo "test" | mail -s "Test" your-email@example.com

  CentOS/RHEL:
    sudo yum install mailx
    echo "test" | mail -s "Test" your-email@example.com

EOF
}

# Main script
main() {
    log_info "===== Certificate Expiry Check Started ====="

    if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
        show_help
        exit 0
    fi

    if [ -n "$1" ]; then
        # Check specific certificate
        check_certificate "$1"
        exit_code=$?
    else
        # Check all certificates
        check_all_certificates
        exit_code=$?
    fi

    log_info "===== Certificate Expiry Check Completed ====="
    exit $exit_code
}

main "$@"
