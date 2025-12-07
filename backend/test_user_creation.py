"""
Test script to create a user and verify persistent encryption works.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.security.user_storage import get_user_storage
from app.security.password_hasher import get_password_hasher
from app.security.models import UserCreate, UserRole
from datetime import datetime

# Create user storage and password hasher
storage = get_user_storage()
hasher = get_password_hasher()

# Create a test user
user_create = UserCreate(
    username="testuser",
    email="test@example.com",
    password="TestPassword123!",
    role=UserRole.VIEWER
)

# Hash the password
password_hash = hasher.hash_password(user_create.password)

# Create User object
from app.security.models import User
user = User(
    id="test-user-001",
    username=user_create.username,
    email=user_create.email,
    role=user_create.role,
    is_active=True,
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow()
)

# Save user
storage.save_user(user, password_hash)

print(f"✅ User '{user.username}' created successfully!")
print(f"   User ID: {user.id}")
print(f"   Email: {user.email}")
print(f"   Role: {user.role}")

# Verify we can retrieve the user
retrieved_user = storage.get_user_by_username("testuser")
if retrieved_user:
    print(f"\n✅ User retrieval successful!")
    print(f"   Retrieved username: {retrieved_user.username}")
    print(f"   Retrieved email: {retrieved_user.email}")
else:
    print("\n❌ ERROR: Could not retrieve user!")
    sys.exit(1)

# Verify password
pwd_data = storage.get_user_password_data(user.id)
if pwd_data:
    print(f"\n✅ Password data retrieved successfully!")
    
    # Verify password
    if hasher.verify_password("TestPassword123!", pwd_data['password_hash']):
        print("✅ Password verification successful!")
    else:
        print("❌ Password verification failed!")
        sys.exit(1)
else:
    print("\n❌ ERROR: Could not retrieve password data!")
    sys.exit(1)

print("\n🎉 All tests passed! User authentication is working correctly.")
