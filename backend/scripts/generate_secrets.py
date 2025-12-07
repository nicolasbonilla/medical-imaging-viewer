#!/usr/bin/env python3
"""
Secure Secrets Generator
ISO 27001 A.9.2.4, A.10.1.2 Compliant Secret Generation

Generates cryptographically secure secrets for production deployment.

Usage: python scripts/generate_secrets.py [--output .env.production]
"""

import secrets
import os
import base64
import argparse
from pathlib import Path

def generate_jwt_secret(length: int = 64) -> str:
    """
    Generate JWT secret key using CSPRNG.

    ISO 27001 A.9.2.4 - Management of secret authentication information

    Args:
        length: Number of bytes for secret (default 64 for 512 bits)

    Returns:
        URL-safe Base64 encoded secret
    """
    return secrets.token_urlsafe(length)

def generate_encryption_key() -> str:
    """
    Generate AES-256 encryption key (32 bytes / 256 bits).

    ISO 27001 A.10.1.2 - Key management

    Returns:
        Base64 encoded 32-byte key
    """
    key_bytes = os.urandom(32)
    return base64.b64encode(key_bytes).decode('utf-8')

def generate_redis_password(length: int = 32) -> str:
    """
    Generate Redis authentication password.

    Args:
        length: Number of bytes for password (default 32 for 256 bits)

    Returns:
        URL-safe Base64 encoded password
    """
    return secrets.token_urlsafe(length)

def generate_database_key() -> str:
    """
    Generate database encryption key (for future PHI storage).

    Returns:
        Base64 encoded 32-byte key
    """
    key_bytes = os.urandom(32)
    return base64.b64encode(key_bytes).decode('utf-8')

def create_env_file(output_path: Path, environment: str = 'production'):
    """
    Create complete .env file with generated secrets.

    Args:
        output_path: Path to output .env file
        environment: Environment name (production, staging, development)
    """

    # Generate all secrets
    jwt_secret = generate_jwt_secret(64)
    encryption_key = generate_encryption_key()
    redis_password = generate_redis_password(32)
    db_key = generate_database_key()

    # Environment-specific settings
    is_production = environment == 'production'
    is_staging = environment == 'staging'
    is_development = environment == 'development'

    debug = 'false' if (is_production or is_staging) else 'true'
    log_level = 'WARNING' if is_production else 'INFO' if is_staging else 'DEBUG'

    # CORS origins
    if is_production:
        cors_origins = 'https://your-domain.com,https://www.your-domain.com'
    elif is_staging:
        cors_origins = 'https://staging.your-domain.com'
    else:
        cors_origins = 'http://localhost:5173,http://localhost:3000'

    env_content = f"""# ============================================================================
# MEDICAL IMAGING VIEWER - {environment.upper()} ENVIRONMENT CONFIGURATION
# Generated: {__import__('datetime').datetime.utcnow().isoformat()}Z
# ISO 27001 A.9.2.4, A.10.1.2 Compliant
# ============================================================================

# WARNING: This file contains sensitive secrets. NEVER commit to version control.
# Ensure this file is listed in .gitignore

# ============================================================================
# ENVIRONMENT SETTINGS
# ============================================================================
ENVIRONMENT={environment}
DEBUG={debug}
LOG_LEVEL={log_level}

# ============================================================================
# JWT SECURITY (ISO 27001 A.9.4.2) - CRITICAL
# ============================================================================
# Auto-generated with secrets.token_urlsafe(64) - 512 bits entropy
JWT_SECRET_KEY={jwt_secret}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ============================================================================
# PASSWORD POLICY (ISO 27001 A.9.4.3)
# ============================================================================
PASSWORD_MIN_LENGTH=12
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_DIGIT=true
PASSWORD_REQUIRE_SPECIAL=true
PASSWORD_MAX_AGE_DAYS=90
PASSWORD_HISTORY_COUNT=5

# ============================================================================
# ACCOUNT LOCKOUT POLICY (ISO 27001 A.9.4.2)
# ============================================================================
ACCOUNT_LOCKOUT_THRESHOLD=5
ACCOUNT_LOCKOUT_DURATION_MINUTES=30

# ============================================================================
# ENCRYPTION CONFIGURATION (ISO 27001 A.10.1.1, A.10.1.2)
# ============================================================================
# Auto-generated with os.urandom(32) - AES-256 key (256 bits)
ENCRYPTION_MASTER_KEY={encryption_key}
KDF_ITERATIONS=100000
KDF_ALGORITHM=SHA256
KEY_ROTATION_DAYS=90

# ============================================================================
# REDIS CONFIGURATION (Secure Cache)
# ============================================================================
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
# Auto-generated with secrets.token_urlsafe(32) - 256 bits entropy
REDIS_PASSWORD={redis_password}
REDIS_MAX_CONNECTIONS=50

# Cache TTL (segundos)
CACHE_DRIVE_FILES_TTL=300
CACHE_IMAGES_TTL=1800
CACHE_METADATA_TTL=600
CACHE_DEFAULT_TTL=3600

# ============================================================================
# CORS CONFIGURATION
# ============================================================================
# IMPORTANT: Update with your actual domain(s)
CORS_ORIGINS={cors_origins}

# ============================================================================
# SERVER CONFIGURATION
# ============================================================================
HOST=0.0.0.0
PORT=8000

# ============================================================================
# GOOGLE DRIVE INTEGRATION (OAuth)
# ============================================================================
GOOGLE_DRIVE_CREDENTIALS_FILE=credentials.json
GOOGLE_DRIVE_TOKEN_FILE=token.json
GOOGLE_DRIVE_SCOPES=https://www.googleapis.com/auth/drive.readonly

# ============================================================================
# UPLOAD CONFIGURATION
# ============================================================================
MAX_UPLOAD_SIZE=524288000
ALLOWED_EXTENSIONS=.dcm,.nii,.nii.gz,.img,.hdr

# ============================================================================
# LOGGING CONFIGURATION (ISO 27001 A.12.4.1)
# ============================================================================
LOG_LEVEL={log_level}
LOG_FORMAT=json
LOG_FILE=logs/app.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=10

# ============================================================================
# PERFORMANCE OPTIMIZATION FLAGS
# ============================================================================
ENABLE_BINARY_PROTOCOL=false
ENABLE_WEBSOCKET=false
WEBSOCKET_MAX_CONNECTIONS=100
WEBSOCKET_HEARTBEAT_INTERVAL=30

ENABLE_PREFETCHING=true
PREFETCH_SLICES=3
PREFETCH_PRIORITY=normal

USE_REDIS_SCAN=true
REDIS_SCAN_COUNT=100

ENABLE_CACHE_WARMING=false
CACHE_WARMING_ON_STARTUP=false

# ============================================================================
# DATABASE ENCRYPTION (Future - PHI Storage)
# ============================================================================
# Auto-generated for future HIPAA compliance
DATABASE_ENCRYPTION_KEY={db_key}

# ============================================================================
# KEY ROTATION TRACKING
# ============================================================================
# Record when keys were generated to enforce rotation policy
SECRETS_GENERATED_DATE={__import__('datetime').datetime.utcnow().date().isoformat()}
# Next rotation due: {(__import__('datetime').datetime.utcnow() + __import__('datetime').timedelta(days=90)).date().isoformat()}

# ============================================================================
# PRODUCTION DEPLOYMENT CHECKLIST
# ============================================================================
# Before deploying to production, ensure:
# [ ] This .env file has restrictive permissions (chmod 600 on Unix)
# [ ] .env is listed in .gitignore
# [ ] CORS_ORIGINS updated with actual domain(s)
# [ ] Redis is configured with requirepass matching REDIS_PASSWORD
# [ ] TLS/SSL certificates are installed and valid
# [ ] All secrets are unique (not copied from staging/development)
# [ ] Run: python scripts/validate_security.py
"""

    # Write to file
    with open(output_path, 'w') as f:
        f.write(env_content)

    # Set restrictive permissions on Unix systems
    if os.name == 'posix':
        os.chmod(output_path, 0o600)
        print(f"✅ File permissions set to 600 (owner read/write only)")

    return {
        'jwt_secret': jwt_secret,
        'encryption_key': encryption_key,
        'redis_password': redis_password,
        'database_key': db_key
    }

def print_secrets_summary(secrets_dict: dict):
    """Print summary of generated secrets (for secure storage)."""
    print("\n" + "="*70)
    print("GENERATED SECRETS SUMMARY")
    print("="*70 + "\n")

    print(f"JWT Secret Key (length: {len(secrets_dict['jwt_secret'])} chars):")
    print(f"  {secrets_dict['jwt_secret'][:32]}...{secrets_dict['jwt_secret'][-8:]}\n")

    print(f"Encryption Master Key (Base64, 32 bytes / 256 bits):")
    print(f"  {secrets_dict['encryption_key'][:32]}...{secrets_dict['encryption_key'][-8:]}\n")

    print(f"Redis Password (length: {len(secrets_dict['redis_password'])} chars):")
    print(f"  {secrets_dict['redis_password'][:16]}...{secrets_dict['redis_password'][-4:]}\n")

    print(f"Database Encryption Key (Base64, 32 bytes / 256 bits):")
    print(f"  {secrets_dict['database_key'][:32]}...{secrets_dict['database_key'][-8:]}\n")

    print("="*70)
    print("⚠️  SECURITY REMINDERS:")
    print("="*70)
    print("1. Store these secrets securely (password manager, secrets vault)")
    print("2. NEVER commit the .env file to version control")
    print("3. Use different secrets for each environment (dev/staging/prod)")
    print("4. Rotate secrets every 90 days (see KEY_ROTATION_DAYS)")
    print("5. Backup secrets securely before rotating")
    print("="*70 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description='Generate secure secrets for Medical Imaging Viewer deployment',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate production secrets
  python scripts/generate_secrets.py --environment production --output .env

  # Generate staging secrets
  python scripts/generate_secrets.py --environment staging --output .env.staging

  # Generate development secrets
  python scripts/generate_secrets.py --environment development --output .env.development

ISO 27001 Controls:
  A.9.2.4 - Management of secret authentication information
  A.10.1.2 - Key management
        """
    )

    parser.add_argument(
        '--environment',
        choices=['production', 'staging', 'development'],
        default='production',
        help='Target environment (default: production)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default='.env',
        help='Output file path (default: .env)'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing file without confirmation'
    )

    args = parser.parse_args()

    output_path = Path(args.output)

    # Check if file exists
    if output_path.exists() and not args.force:
        print(f"⚠️  File {output_path} already exists.")
        response = input("Overwrite? This will replace all existing secrets! (yes/no): ")
        if response.lower() != 'yes':
            print("Operation cancelled.")
            return

    print("\n" + "="*70)
    print("SECURE SECRETS GENERATOR")
    print("ISO 27001 A.9.2.4, A.10.1.2 Compliant")
    print("="*70 + "\n")

    print(f"Generating secrets for: {args.environment}")
    print(f"Output file: {output_path}")
    print("\nGenerating cryptographically secure secrets using CSPRNG...")

    secrets_dict = create_env_file(output_path, args.environment)

    print(f"\n✅ Secrets generated successfully!")
    print(f"✅ Configuration file created: {output_path}")

    print_secrets_summary(secrets_dict)

    print("NEXT STEPS:")
    print("="*70)
    print("1. Review and update CORS_ORIGINS with your actual domain(s)")
    print("2. Configure Redis with the generated REDIS_PASSWORD")
    print("3. Run security validation: python scripts/validate_security.py")
    print("4. Store secrets backup in secure location (password manager)")
    print("5. Deploy application with new configuration")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
