"""
Reset admin user password.

This script resets the admin user password to: Admin123!@2024
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.security.user_storage import get_user_storage
from app.security.password import PasswordManager

def reset_admin_password():
    """Reset admin user password."""

    username = "admin"
    new_password = "Admin123!@2024"

    print(f"Resetting password for user: {username}")
    print(f"New password: {new_password}")
    print()

    # Get storage and password manager
    storage = get_user_storage()
    pwd_manager = PasswordManager()

    # Get user
    user = storage.get_user_by_username(username)
    if not user:
        print(f"[ERROR] User '{username}' not found!")
        return False

    print(f"Found user:")
    print(f"   User ID: {user.id}")
    print(f"   Username: {user.username}")
    print(f"   Email: {user.email}")
    print(f"   Role: {user.role.value}")
    print(f"   Created: {user.created_at}")
    print()

    # Hash new password
    new_password_hash = pwd_manager.hash_password(new_password)

    # Get current password data
    password_data = storage.get_user_password_data(user.id)
    if not password_data:
        print("[ERROR] Could not retrieve password data!")
        return False

    # Update password history
    password_history = password_data.get('password_history', [])
    password_history.append(new_password_hash)

    # Reset failed login attempts
    user.failed_login_attempts = 0
    user.is_locked = False
    user.locked_until = None

    # Save user with new password
    storage.save_user(user, new_password_hash, password_history)

    print("[SUCCESS] Password reset successfully!")
    print()
    print("=" * 60)
    print("ADMIN USER CREDENTIALS")
    print("=" * 60)
    print(f"Username: {username}")
    print(f"Password: {new_password}")
    print("=" * 60)

    return True

if __name__ == "__main__":
    success = reset_admin_password()
    sys.exit(0 if success else 1)
