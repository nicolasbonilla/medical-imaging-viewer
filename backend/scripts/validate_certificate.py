#!/usr/bin/env python3
"""
Certificate Validation Script
Medical Imaging Viewer - TLS/SSL Certificate Validation and Analysis

ISO 27001 A.10.1.2 - Key management
ISO 27001 A.13.1.1 - Network controls

Usage:
    python validate_certificate.py <cert_file> <key_file>
    python validate_certificate.py --fingerprint <cert_file>
    python validate_certificate.py --chain <cert_file> <ca_bundle>

Examples:
    # Validate certificate and key
    python validate_certificate.py cert.pem key.pem

    # Calculate certificate fingerprint (for pinning)
    python validate_certificate.py --fingerprint cert.pem

    # Verify certificate chain
    python validate_certificate.py --chain cert.pem ca-bundle.pem
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.core.security import CertificateValidator
    from app.core.logging import get_logger
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}")
    print("Make sure you're running from the backend directory with virtual environment activated.")
    sys.exit(1)


# Colors for terminal output
class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    MAGENTA = '\033[0;35m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


def print_header(text: str) -> None:
    """Print formatted header."""
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 70}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text:^70}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 70}{Colors.NC}")
    print()


def print_section(text: str) -> None:
    """Print formatted section."""
    print()
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.NC}")
    print(f"{Colors.BLUE}{'-' * len(text)}{Colors.NC}")


def print_success(text: str) -> None:
    """Print success message."""
    print(f"{Colors.GREEN}✓{Colors.NC} {text}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"{Colors.RED}✗{Colors.NC} {text}")


def print_warning(text: str) -> None:
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠{Colors.NC} {text}")


def print_info(text: str) -> None:
    """Print info message."""
    print(f"{Colors.CYAN}ℹ{Colors.NC} {text}")


def validate_certificate_files(cert_path: str, key_path: str) -> int:
    """
    Validate certificate and private key files.

    Args:
        cert_path: Path to certificate file
        key_path: Path to private key file

    Returns:
        Exit code (0 = valid, 1 = invalid)
    """
    print_header("TLS/SSL Certificate Validation")

    # Check if files exist
    cert_file = Path(cert_path)
    key_file = Path(key_path)

    if not cert_file.exists():
        print_error(f"Certificate file not found: {cert_path}")
        return 1

    if not key_file.exists():
        print_error(f"Private key file not found: {key_path}")
        return 1

    print_info(f"Certificate: {cert_path}")
    print_info(f"Private Key: {key_path}")

    # Validate certificate
    print_section("Validating Certificate")

    try:
        result = CertificateValidator.validate_certificate_file(
            cert_path=cert_path,
            key_path=key_path
        )
    except Exception as e:
        print_error(f"Validation failed with exception: {e}")
        return 1

    # Print metadata
    if result['metadata']:
        print_section("Certificate Details")
        meta = result['metadata']

        print(f"  {Colors.BOLD}Common Name:{Colors.NC} {meta.get('common_name', 'N/A')}")
        print(f"  {Colors.BOLD}Organization:{Colors.NC} {meta.get('organization', 'N/A')}")
        print(f"  {Colors.BOLD}Issuer:{Colors.NC} {meta.get('issuer_cn', 'N/A')}")
        print()
        print(f"  {Colors.BOLD}Valid From:{Colors.NC} {meta.get('valid_from', 'N/A')}")
        print(f"  {Colors.BOLD}Valid Until:{Colors.NC} {meta.get('valid_until', 'N/A')}")
        print()
        print(f"  {Colors.BOLD}Serial Number:{Colors.NC} {meta.get('serial_number', 'N/A')}")
        print(f"  {Colors.BOLD}Signature Algorithm:{Colors.NC} {meta.get('signature_algorithm', 'N/A')}")
        print(f"  {Colors.BOLD}Public Key Size:{Colors.NC} {meta.get('public_key_bits', 'N/A')} bits")

        # Key strength assessment
        key_bits = meta.get('public_key_bits', 0)
        if key_bits >= 4096:
            print(f"  {Colors.BOLD}Key Strength:{Colors.NC} {Colors.GREEN}Excellent (4096+ bits){Colors.NC}")
        elif key_bits >= 2048:
            print(f"  {Colors.BOLD}Key Strength:{Colors.NC} {Colors.GREEN}Good (2048+ bits){Colors.NC}")
        elif key_bits >= 1024:
            print(f"  {Colors.BOLD}Key Strength:{Colors.NC} {Colors.YELLOW}Weak (< 2048 bits){Colors.NC}")
        else:
            print(f"  {Colors.BOLD}Key Strength:{Colors.NC} {Colors.RED}Very Weak (< 1024 bits){Colors.NC}")

    # Print errors
    if result['errors']:
        print_section("Validation Errors")
        for error in result['errors']:
            print_error(error)

    # Print warnings
    if result['warnings']:
        print_section("Warnings")
        for warning in result['warnings']:
            print_warning(warning)

    # Overall status
    print_section("Validation Result")

    if result['valid']:
        print_success("Certificate is VALID")

        # Additional recommendations
        if result['warnings']:
            print()
            print_info("Recommendations:")
            if any("expires in" in w.lower() for w in result['warnings']):
                print("  • Renew certificate before expiry to avoid service disruption")
            if any("self-signed" in w.lower() for w in result['warnings']):
                print("  • Use a certificate from a trusted CA for production")
            if any("2048 bits" in w.lower() for w in result['warnings']):
                print("  • Consider upgrading to 4096-bit RSA or ECDSA P-384 for stronger security")

        return 0
    else:
        print_error("Certificate is INVALID")
        print()
        print_info("Action Required:")
        print("  • Review errors above")
        print("  • Generate new certificate if expired or invalid")
        print("  • Verify private key matches certificate")
        return 1


def calculate_fingerprint(cert_path: str, algorithm: str = 'sha256') -> int:
    """
    Calculate certificate fingerprint for pinning.

    Args:
        cert_path: Path to certificate file
        algorithm: Hash algorithm (sha256, sha384, sha512)

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    print_header("Certificate Fingerprint Calculation")

    cert_file = Path(cert_path)
    if not cert_file.exists():
        print_error(f"Certificate file not found: {cert_path}")
        return 1

    print_info(f"Certificate: {cert_path}")
    print_info(f"Algorithm: {algorithm}")

    try:
        fingerprint = CertificateValidator.calculate_cert_fingerprint(
            cert_path=cert_path,
            algorithm=algorithm
        )

        print_section("Certificate Fingerprint")
        print(f"{Colors.BOLD}{fingerprint}{Colors.NC}")

        print_section("Usage")
        print("Add this fingerprint to your HPKP header (if using public key pinning):")
        print(f'  Public-Key-Pins: pin-{algorithm}="{fingerprint.split("-")[1]}"; max-age=5184000')

        print()
        print_warning("Note: HPKP is deprecated. Use Certificate Transparency instead.")
        print_info("Fingerprints are useful for certificate change detection and monitoring.")

        return 0

    except Exception as e:
        print_error(f"Fingerprint calculation failed: {e}")
        return 1


def verify_chain(cert_path: str, ca_bundle_path: str) -> int:
    """
    Verify certificate chain.

    Args:
        cert_path: Path to certificate file
        ca_bundle_path: Path to CA bundle file

    Returns:
        Exit code (0 = valid chain, 1 = invalid chain)
    """
    print_header("Certificate Chain Verification")

    cert_file = Path(cert_path)
    ca_bundle_file = Path(ca_bundle_path)

    if not cert_file.exists():
        print_error(f"Certificate file not found: {cert_path}")
        return 1

    if not ca_bundle_file.exists():
        print_error(f"CA bundle file not found: {ca_bundle_path}")
        return 1

    print_info(f"Certificate: {cert_path}")
    print_info(f"CA Bundle: {ca_bundle_path}")

    try:
        import subprocess

        # Use openssl verify command
        result = subprocess.run(
            ['openssl', 'verify', '-CAfile', ca_bundle_path, cert_path],
            capture_output=True,
            text=True,
            check=False
        )

        print_section("Verification Result")

        if result.returncode == 0:
            print_success("Certificate chain is VALID")
            print(f"\n{result.stdout}")
            return 0
        else:
            print_error("Certificate chain is INVALID")
            print(f"\n{result.stderr}")
            return 1

    except FileNotFoundError:
        print_error("openssl command not found. Please install OpenSSL.")
        return 1
    except Exception as e:
        print_error(f"Chain verification failed: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='TLS/SSL Certificate Validation and Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate certificate and key
  %(prog)s cert.pem key.pem

  # Calculate SHA-256 fingerprint
  %(prog)s --fingerprint cert.pem

  # Calculate SHA-384 fingerprint
  %(prog)s --fingerprint cert.pem --algorithm sha384

  # Verify certificate chain
  %(prog)s --chain cert.pem ca-bundle.pem

Security Notes:
  - Certificates should use RSA 2048+ or ECDSA P-256+ for production
  - Self-signed certificates are only suitable for development
  - Renew certificates 30 days before expiry
  - Always validate private key matches certificate

ISO 27001 Controls:
  - A.10.1.2: Key management
  - A.13.1.1: Network controls
        """
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--fingerprint',
        action='store_true',
        help='Calculate certificate fingerprint for pinning'
    )
    mode_group.add_argument(
        '--chain',
        action='store_true',
        help='Verify certificate chain'
    )

    # Arguments
    parser.add_argument(
        'cert_file',
        help='Path to certificate file (.pem, .crt)'
    )
    parser.add_argument(
        'key_or_ca_file',
        nargs='?',
        help='Path to private key file (for validation) or CA bundle (for chain verification)'
    )
    parser.add_argument(
        '--algorithm',
        choices=['sha256', 'sha384', 'sha512'],
        default='sha256',
        help='Hash algorithm for fingerprint (default: sha256)'
    )

    # Parse arguments
    args = parser.parse_args()

    # Execute based on mode
    if args.fingerprint:
        return calculate_fingerprint(args.cert_file, args.algorithm)
    elif args.chain:
        if not args.key_or_ca_file:
            parser.error("CA bundle file required for chain verification")
        return verify_chain(args.cert_file, args.key_or_ca_file)
    else:
        # Default: validate certificate
        if not args.key_or_ca_file:
            parser.error("Private key file required for certificate validation")
        return validate_certificate_files(args.cert_file, args.key_or_ca_file)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}FATAL ERROR:{Colors.NC} {e}")
        sys.exit(1)
