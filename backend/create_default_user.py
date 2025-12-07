"""
Create default user for Medical Imaging Viewer.

This script creates a default test user with known credentials.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.security.models import UserCreate, UserRole
from app.security.user_storage import get_user_storage
from app.security.password import PasswordManager

async def create_default_user():
    """Create default user with credentials: admin / Admin123!@2024"""

    # User credentials
    username = "admin"
    password = "Admin123!@2024"
    email = "admin@example.com"
    full_name = "Administrator"

    print(f"Creating default user...")
    print(f"Username: {username}")
    print(f"Password: {password}")
    print(f"Email: {email}")
    print()

    # Get storage and password manager
    storage = get_user_storage()
    pwd_manager = PasswordManager()

    # Check if user already exists
    existing_user = storage.get_user_by_username(username)
    if existing_user:
        print(f"[ERROR] User '{username}' already exists!")
        print(f"   User ID: {existing_user.id}")
        print(f"   Created: {existing_user.created_at}")
        return False

    # Create user data
    user_create = UserCreate(
        username=username,
        email=email,
        password=password,
        full_name=full_name,
        role=UserRole.ADMIN
    )

    # Hash password
    password_hash = pwd_manager.hash_password(password)

    # Create user object
    from app.security.models import User
    from datetime import datetime
    import uuid

    user = User(
        id=str(uuid.uuid4()),
        username=user_create.username,
        email=user_create.email,
        full_name=user_create.full_name,
        role=user_create.role,
        is_active=True,
        email_verified=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        last_password_change=datetime.utcnow(),
        failed_login_attempts=0
    )

    # Save user
    storage.save_user(user, password_hash)

    print(f"[SUCCESS] Default user created successfully!")
    print(f"   User ID: {user.id}")
    print(f"   Role: {user.role.value}")
    print()
    print("=" * 60)
    print("DEFAULT USER CREDENTIALS")
    print("=" * 60)
    print(f"Username: {username}")
    print(f"Password: {password}")
    print("=" * 60)

    return True

if __name__ == "__main__":
    success = asyncio.run(create_default_user())
    sys.exit(0 if success else 1)
