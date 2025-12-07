#!/usr/bin/env python3
"""
Encryption Key Rotation Script
ISO 27001 A.10.1.2 - Key Management

Rotates the encryption master key and re-encrypts all encrypted data.

CRITICAL: This script must be run during a maintenance window to avoid
          data corruption. Always create backups before rotating keys.

Usage:
    python scripts/rotate_encryption_key.py \\
        --old-key <BASE64_OLD_KEY> \\
        --new-key <BASE64_NEW_KEY> \\
        --backup-dir /secure/backups/20250122

Requirements:
    - Application must be stopped (no writes during rotation)
    - Redis must be accessible
    - Sufficient disk space for backups
    - Database backup completed (if applicable)
"""

import argparse
import base64
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Tuple

try:
    import redis
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError as e:
    print(f"❌ Missing required package: {e}")
    print("Install with: pip install redis cryptography")
    sys.exit(1)

class KeyRotationManager:
    """Manages encryption key rotation process."""

    def __init__(self, old_key: str, new_key: str, backup_dir: str, kdf_iterations: int = 100_000):
        """
        Initialize key rotation manager.

        Args:
            old_key: Base64-encoded current master key
            new_key: Base64-encoded new master key
            backup_dir: Directory for backups
            kdf_iterations: PBKDF2 iterations
        """
        self.old_key_b64 = old_key
        self.new_key_b64 = new_key
        self.backup_dir = Path(backup_dir)
        self.kdf_iterations = kdf_iterations

        # Decode keys
        try:
            self.old_key = base64.b64decode(old_key)
            self.new_key = base64.b64decode(new_key)
        except Exception as e:
            raise ValueError(f"Invalid Base64 key: {e}")

        # Validate key lengths
        if len(self.old_key) != 32:
            raise ValueError(f"Old key must be 32 bytes, got {len(self.old_key)}")
        if len(self.new_key) != 32:
            raise ValueError(f"New key must be 32 bytes, got {len(self.new_key)}")

        # Create backup directory
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Initialize encryption objects
        self.old_cipher = AESGCM(self.old_key)
        self.new_cipher = AESGCM(self.new_key)

    def derive_key(self, master_key: bytes, salt: bytes) -> bytes:
        """
        Derive encryption key using PBKDF2.

        Args:
            master_key: Master encryption key
            salt: Salt for key derivation

        Returns:
            Derived key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.kdf_iterations,
        )
        return kdf.derive(master_key)

    def decrypt_with_old_key(self, encrypted_data: bytes, nonce: bytes) -> bytes:
        """Decrypt data using old key."""
        try:
            return self.old_cipher.decrypt(nonce, encrypted_data, None)
        except Exception as e:
            raise ValueError(f"Decryption failed with old key: {e}")

    def encrypt_with_new_key(self, plaintext: bytes) -> Tuple[bytes, bytes]:
        """
        Encrypt data using new key.

        Returns:
            Tuple of (encrypted_data, nonce)
        """
        nonce = os.urandom(12)  # 96-bit nonce for AES-GCM
        encrypted = self.new_cipher.encrypt(nonce, plaintext, None)
        return encrypted, nonce

    def backup_redis_data(self, redis_client: redis.Redis) -> str:
        """
        Create backup of all Redis data.

        Args:
            redis_client: Connected Redis client

        Returns:
            Path to backup file
        """
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_file = self.backup_dir / f"redis_backup_{timestamp}.json"

        print(f"📦 Creating Redis backup: {backup_file}")

        all_keys = []
        cursor = 0

        # Scan all keys
        while True:
            cursor, keys = redis_client.scan(cursor, count=1000)
            all_keys.extend([k.decode('utf-8') if isinstance(k, bytes) else k for k in keys])
            if cursor == 0:
                break

        print(f"   Found {len(all_keys)} keys to backup")

        # Backup data
        backup_data = {}
        for key in all_keys:
            try:
                value_type = redis_client.type(key)

                if value_type == b'string':
                    value = redis_client.get(key)
                    backup_data[key] = {
                        'type': 'string',
                        'value': base64.b64encode(value).decode('utf-8') if value else None,
                        'ttl': redis_client.ttl(key)
                    }
                elif value_type == b'hash':
                    value = redis_client.hgetall(key)
                    backup_data[key] = {
                        'type': 'hash',
                        'value': {
                            k.decode('utf-8'): base64.b64encode(v).decode('utf-8')
                            for k, v in value.items()
                        },
                        'ttl': redis_client.ttl(key)
                    }
                else:
                    print(f"   ⚠️  Skipping unsupported type for key {key}: {value_type}")
            except Exception as e:
                print(f"   ❌ Error backing up key {key}: {e}")

        # Write backup
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)

        print(f"✅ Backup completed: {len(backup_data)} keys saved")
        return str(backup_file)

    def rotate_redis_encrypted_data(self, redis_client: redis.Redis, key_pattern: str = "*encrypted*") -> int:
        """
        Rotate encryption for all encrypted data in Redis.

        Args:
            redis_client: Connected Redis client
            key_pattern: Pattern to match encrypted keys

        Returns:
            Number of keys rotated
        """
        print(f"\n🔄 Rotating encrypted data in Redis (pattern: {key_pattern})")

        rotated_count = 0
        error_count = 0
        cursor = 0
        encrypted_keys = []

        # Find all encrypted keys
        while True:
            cursor, keys = redis_client.scan(cursor, match=key_pattern, count=100)
            encrypted_keys.extend([k.decode('utf-8') if isinstance(k, bytes) else k for k in keys])
            if cursor == 0:
                break

        print(f"   Found {len(encrypted_keys)} encrypted keys")

        for key in encrypted_keys:
            try:
                # Get encrypted data
                encrypted_value = redis_client.get(key)
                if not encrypted_value:
                    continue

                # Parse encrypted format: nonce (12 bytes) + ciphertext
                if len(encrypted_value) < 12:
                    print(f"   ⚠️  Skipping invalid encrypted data for key {key}")
                    continue

                nonce = encrypted_value[:12]
                ciphertext = encrypted_value[12:]

                # Decrypt with old key
                plaintext = self.decrypt_with_old_key(ciphertext, nonce)

                # Encrypt with new key
                new_ciphertext, new_nonce = self.encrypt_with_new_key(plaintext)

                # Store re-encrypted data
                new_encrypted_value = new_nonce + new_ciphertext

                # Get TTL to preserve it
                ttl = redis_client.ttl(key)

                # Update in Redis
                if ttl > 0:
                    redis_client.setex(key, ttl, new_encrypted_value)
                else:
                    redis_client.set(key, new_encrypted_value)

                rotated_count += 1

                if rotated_count % 100 == 0:
                    print(f"   Progress: {rotated_count}/{len(encrypted_keys)} keys rotated")

            except Exception as e:
                print(f"   ❌ Error rotating key {key}: {e}")
                error_count += 1

        print(f"\n✅ Rotation completed: {rotated_count} keys rotated, {error_count} errors")
        return rotated_count

    def update_env_file(self, env_file: str = '.env'):
        """
        Update .env file with new encryption key.

        Args:
            env_file: Path to .env file
        """
        env_path = Path(env_file)

        if not env_path.exists():
            print(f"⚠️  Warning: {env_file} not found, skipping .env update")
            return

        print(f"\n📝 Updating {env_file} with new encryption key")

        # Read current .env
        with open(env_path, 'r') as f:
            lines = f.readlines()

        # Create backup
        backup_path = self.backup_dir / f"env_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        with open(backup_path, 'w') as f:
            f.writelines(lines)
        print(f"   .env backed up to: {backup_path}")

        # Update ENCRYPTION_MASTER_KEY
        updated_lines = []
        key_updated = False

        for line in lines:
            if line.startswith('ENCRYPTION_MASTER_KEY='):
                updated_lines.append(f'ENCRYPTION_MASTER_KEY={self.new_key_b64}\n')
                key_updated = True
            elif line.startswith('SECRETS_GENERATED_DATE='):
                updated_lines.append(f'SECRETS_GENERATED_DATE={datetime.utcnow().date().isoformat()}\n')
            else:
                updated_lines.append(line)

        if not key_updated:
            print("   ⚠️  ENCRYPTION_MASTER_KEY not found in .env, adding it")
            updated_lines.append(f'\nENCRYPTION_MASTER_KEY={self.new_key_b64}\n')

        # Write updated .env
        with open(env_path, 'w') as f:
            f.writelines(updated_lines)

        print(f"✅ {env_file} updated successfully")

def main():
    parser = argparse.ArgumentParser(
        description='Rotate encryption master key and re-encrypt data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python scripts/rotate_encryption_key.py \\
        --old-key "$(grep ENCRYPTION_MASTER_KEY .env | cut -d= -f2)" \\
        --new-key "$(python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())')" \\
        --backup-dir /secure/backups/$(date +%Y%m%d) \\
        --redis-host localhost \\
        --redis-password "$(grep REDIS_PASSWORD .env | cut -d= -f2)"

IMPORTANT:
    1. Stop the application before running this script
    2. Create database backup (if applicable)
    3. Ensure sufficient disk space for Redis backup
    4. Test key rotation in staging environment first
    5. Keep old key secure for 30 days (disaster recovery)

ISO 27001 Control: A.10.1.2 - Key Management
        """
    )

    parser.add_argument('--old-key', required=True, help='Base64-encoded current master key')
    parser.add_argument('--new-key', required=True, help='Base64-encoded new master key')
    parser.add_argument('--backup-dir', required=True, help='Directory for backups')

    parser.add_argument('--redis-host', default='localhost', help='Redis host (default: localhost)')
    parser.add_argument('--redis-port', type=int, default=6379, help='Redis port (default: 6379)')
    parser.add_argument('--redis-db', type=int, default=0, help='Redis database (default: 0)')
    parser.add_argument('--redis-password', default='', help='Redis password')

    parser.add_argument('--key-pattern', default='*encrypted*', help='Pattern for encrypted keys (default: *encrypted*)')
    parser.add_argument('--env-file', default='.env', help='Path to .env file (default: .env)')

    parser.add_argument('--skip-backup', action='store_true', help='Skip Redis backup (NOT RECOMMENDED)')
    parser.add_argument('--dry-run', action='store_true', help='Simulate rotation without making changes')

    args = parser.parse_args()

    print("\n" + "="*70)
    print("ENCRYPTION KEY ROTATION - ISO 27001 A.10.1.2")
    print("="*70 + "\n")

    # Validate keys are different
    if args.old_key == args.new_key:
        print("❌ Error: Old key and new key are identical")
        sys.exit(1)

    try:
        # Initialize rotation manager
        print("🔧 Initializing key rotation manager...")
        rotation_manager = KeyRotationManager(
            old_key=args.old_key,
            new_key=args.new_key,
            backup_dir=args.backup_dir
        )
        print("✅ Rotation manager initialized\n")

        # Connect to Redis
        print(f"🔌 Connecting to Redis at {args.redis_host}:{args.redis_port}...")
        redis_client = redis.Redis(
            host=args.redis_host,
            port=args.redis_port,
            db=args.redis_db,
            password=args.redis_password if args.redis_password else None,
            decode_responses=False
        )

        # Test connection
        redis_client.ping()
        print("✅ Redis connection established\n")

        if args.dry_run:
            print("🧪 DRY RUN MODE - No changes will be made\n")

        # Backup Redis data
        if not args.skip_backup and not args.dry_run:
            backup_file = rotation_manager.backup_redis_data(redis_client)
            print(f"✅ Redis backup saved: {backup_file}\n")
        elif args.dry_run:
            print("📦 Skipping backup (dry run)\n")
        else:
            print("⚠️  WARNING: Skipping backup (--skip-backup flag set)\n")

        # Rotate encrypted data
        if not args.dry_run:
            rotated_count = rotation_manager.rotate_redis_encrypted_data(
                redis_client,
                key_pattern=args.key_pattern
            )
        else:
            print(f"🔄 Would rotate keys matching pattern: {args.key_pattern}")
            rotated_count = 0

        # Update .env file
        if not args.dry_run:
            rotation_manager.update_env_file(args.env_file)
        else:
            print(f"📝 Would update {args.env_file} with new key")

        print("\n" + "="*70)
        print("KEY ROTATION SUMMARY")
        print("="*70)
        print(f"Old key: {args.old_key[:16]}...{args.old_key[-8:]}")
        print(f"New key: {args.new_key[:16]}...{args.new_key[-8:]}")
        print(f"Backup directory: {args.backup_dir}")
        print(f"Keys rotated: {rotated_count}")
        print(f"Dry run: {args.dry_run}")
        print("="*70 + "\n")

        if not args.dry_run:
            print("✅ KEY ROTATION COMPLETED SUCCESSFULLY\n")
            print("NEXT STEPS:")
            print("1. Verify application functionality with new key")
            print("2. Run: python scripts/validate_security.py")
            print("3. Start application and monitor logs for errors")
            print("4. Keep old key secure for 30 days (disaster recovery)")
            print("5. Update key rotation tracking in documentation")
            print("6. Schedule next rotation in 90 days\n")
        else:
            print("🧪 DRY RUN COMPLETED - No changes were made\n")
            print("Run without --dry-run to perform actual rotation\n")

    except Exception as e:
        print(f"\n❌ KEY ROTATION FAILED: {e}\n")
        print("RECOVERY STEPS:")
        print("1. Check error message above")
        print("2. Restore from backup if necessary")
        print("3. Verify Redis connectivity and credentials")
        print("4. Contact security team if issue persists\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
