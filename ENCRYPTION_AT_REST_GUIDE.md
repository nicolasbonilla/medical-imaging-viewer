# Data-at-Rest Encryption Guide

**ISO 27001 Controls:**
- A.10.1.1 - Policy on the use of cryptographic controls
- A.10.1.2 - Key management
- A.18.1.5 - Regulation of cryptographic controls

**HIPAA Requirements:**
- § 164.312(a)(2)(iv) - Encryption and decryption
- § 164.312(e)(2)(ii) - Encryption

**NIST Standards:**
- NIST SP 800-38D - Galois/Counter Mode (GCM)
- NIST SP 800-132 - Password-Based Key Derivation
- FIPS 140-2 - Cryptographic Module Validation

---

## Table of Contents

1. [Overview](#overview)
2. [Backend Encryption (Redis)](#backend-encryption-redis)
3. [Frontend Encryption (IndexedDB)](#frontend-encryption-indexeddb)
4. [Key Management](#key-management)
5. [Data Classification](#data-classification)
6. [Implementation Examples](#implementation-examples)
7. [Security Architecture](#security-architecture)
8. [Best Practices](#best-practices)
9. [Compliance](#compliance)

---

## Overview

The Medical Imaging Viewer implements **AES-256-GCM authenticated encryption** for all sensitive data stored at rest:

- **Backend (Redis)**: Encrypted cache storage for PHI, tokens, and sensitive metadata
- **Frontend (IndexedDB)**: Encrypted browser storage for user preferences and offline data

### Encryption Specifications

| Component | Algorithm | Key Size | Mode | Standard |
|-----------|-----------|----------|------|----------|
| **Symmetric Encryption** | AES | 256-bit | GCM | NIST SP 800-38D |
| **Key Derivation** | PBKDF2 | N/A | HMAC-SHA256 | NIST SP 800-132 |
| **Authentication** | GCM Tag | 128-bit | N/A | Built-in AEAD |

### Security Features

✅ **AEAD (Authenticated Encryption with Associated Data)**
- Provides both confidentiality AND integrity
- Detects tampering automatically
- No separate HMAC required

✅ **Random Nonces/IVs**
- Never reused (critical for GCM security)
- Generated with CSPRNG
- 96 bits (recommended for GCM)

✅ **Key Derivation (PBKDF2)**
- 100,000+ iterations (NIST recommendation)
- SHA-256 hash function
- Random salts (128 bits)

✅ **Non-Extractable Keys**
- Keys never leave secure storage
- Cannot be exported or read
- Protected by browser/OS

---

## Backend Encryption (Redis)

### Architecture

```
Master Key (env var)
       ↓
   PBKDF2-HMAC-SHA256 (100K iterations)
       ↓
  Derived Key (256-bit)
       ↓
   AES-256-GCM Cipher
       ↓
   Encrypted Data → Redis
```

### Installation

Ensure `cryptography` library is installed:

```bash
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install cryptography==42.0.0
```

### Configuration

Set master encryption key in `.env`:

```bash
# Generate strong master key (256 bits)
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"

# Add to .env
ENCRYPTION_MASTER_KEY=<generated-key-here>
KDF_ITERATIONS=100000
```

⚠️ **CRITICAL**: Never commit master key to version control!

### Basic Usage

#### 1. Encrypt/Decrypt Strings

```python
from app.core.security import EncryptionService, DataClassification

# Create encryption service
encryption = EncryptionService(
    master_key="your-master-key-from-env",
    kdf_iterations=100000
)

# Encrypt sensitive data
ciphertext_b64, metadata = encryption.encrypt_string(
    plaintext="123-45-6789",  # SSN
    classification=DataClassification.PII,
    context={'user_id': 'user_123', 'field': 'ssn'}
)

# Store ciphertext and metadata
# ...

# Decrypt later
plaintext = encryption.decrypt_string(ciphertext_b64, metadata)
```

#### 2. Encrypt/Decrypt Binary Data

```python
# Encrypt binary data (e.g., medical images)
image_data = b'\x89PNG\r\n\x1a\n...'  # PNG file

ciphertext, metadata = encryption.encrypt_data(
    data=image_data,
    classification=DataClassification.PHI,
    context={'patient_id': 'P12345', 'image_type': 'ct_scan'}
)

# Decrypt
decrypted_image = encryption.decrypt_data(ciphertext, metadata)
```

### Encrypted Redis Client

Transparent encryption/decryption wrapper for Redis:

```python
from app.core.security import create_encrypted_redis_client
import redis

# Create Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Wrap with encryption
encrypted_redis = create_encrypted_redis_client(redis_client)

# Store encrypted value (automatic encryption)
encrypted_redis.set_encrypted(
    key='user:123:ssn',
    value='123-45-6789',
    classification=DataClassification.PII,
    ttl=3600,  # 1 hour
    context={'user_id': 'user_123'}
)

# Retrieve and decrypt (automatic decryption)
ssn = encrypted_redis.get_decrypted('user:123:ssn')  # Returns '123-45-6789'

# Check existence
exists = encrypted_redis.exists('user:123:ssn')  # Returns True

# Delete
encrypted_redis.delete('user:123:ssn')
```

### Advanced: Multiple Encryption Keys

For enhanced security, use different keys for different data classifications:

```python
# PHI encryption key (highest security)
phi_encryption = EncryptionService(
    master_key=os.getenv('PHI_ENCRYPTION_KEY'),
    kdf_iterations=250000  # Higher iterations for PHI
)

# PII encryption key
pii_encryption = EncryptionService(
    master_key=os.getenv('PII_ENCRYPTION_KEY'),
    kdf_iterations=150000
)

# General confidential data key
general_encryption = EncryptionService(
    master_key=os.getenv('GENERAL_ENCRYPTION_KEY'),
    kdf_iterations=100000
)
```

---

## Frontend Encryption (IndexedDB)

### Architecture

```
Master Key (env var or derived from password)
       ↓
   PBKDF2 (Web Crypto API)
       ↓
  Derived Key (256-bit)
       ↓
   AES-GCM (Web Crypto)
       ↓
   Encrypted Data → IndexedDB
```

### Configuration

Set encryption key in `.env.local`:

```bash
# Frontend .env.local
VITE_ENCRYPTION_KEY=your-strong-master-key-here
```

⚠️ **Production Note**: In production, derive key from user password instead of env var.

### Basic Usage

#### 1. Simple Encrypted Storage

```typescript
import { createEncryptedStorage, DataClassification } from '@/utils/encryption';

// Create encrypted storage
const storage = await createEncryptedStorage(
  'medical-imaging-viewer',  // Database name
  'encrypted-data'            // Store name
);

// Store encrypted value
await storage.setEncrypted(
  'user-preferences',
  JSON.stringify({ theme: 'dark', lang: 'en' }),
  DataClassification.INTERNAL
);

// Retrieve and decrypt
const preferences = await storage.getDecrypted('user-preferences');
const parsed = JSON.parse(preferences);

// Check existence
const exists = await storage.exists('user-preferences');

// Delete
await storage.delete('user-preferences');

// Close when done
storage.close();
```

#### 2. Manual Encryption/Decryption

```typescript
import { EncryptionService, DataClassification } from '@/utils/encryption';

// Create service
const encryption = new EncryptionService('your-master-key');
await encryption.initialize();

// Encrypt
const encryptedPackage = await encryption.encrypt(
  'sensitive data',
  DataClassification.PHI,
  { patientId: 'P12345' }
);

// Encrypted package structure:
// {
//   ciphertext: 'base64-encoded-ciphertext',
//   metadata: {
//     version: '1.0',
//     algorithm: 'AES-GCM',
//     keyId: 'abc123...',
//     iv: 'base64-iv',
//     salt: 'base64-salt',
//     classification: 'phi',
//     encryptedAt: '2025-01-15T12:00:00Z',
//     context: { patientId: 'P12345' }
//   }
//}

// Decrypt
const plaintext = await encryption.decrypt(encryptedPackage);
```

#### 3. Storing Encrypted Medical Images

```typescript
import { createEncryptedStorage, DataClassification } from '@/utils/encryption';

// Store encrypted image data
const storage = await createEncryptedStorage();

// Convert image to base64 for storage
const imageBlob = await fetch('/api/image/123').then(r => r.blob());
const reader = new FileReader();
reader.readAsDataURL(imageBlob);
reader.onloadend = async () => {
  const base64Image = reader.result as string;

  // Store encrypted
  await storage.setEncrypted(
    'image:123',
    base64Image,
    DataClassification.PHI,
    { patientId: 'P12345', imageType: 'ct_scan' }
  );
};

// Retrieve encrypted image
const encryptedImage = await storage.getDecrypted('image:123');
const img = new Image();
img.src = encryptedImage;
```

### React Hook for Encrypted Storage

Create a custom hook for easy integration:

```typescript
// hooks/useEncryptedStorage.ts
import { useState, useEffect } from 'react';
import { createEncryptedStorage, DataClassification } from '@/utils/encryption';

export function useEncryptedStorage<T>(
  key: string,
  classification: DataClassification = DataClassification.CONFIDENTIAL
) {
  const [value, setValue] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadValue = async () => {
      try {
        const storage = await createEncryptedStorage();
        const encrypted = await storage.getDecrypted(key);

        if (encrypted) {
          setValue(JSON.parse(encrypted));
        }

        storage.close();
      } catch (error) {
        console.error('Failed to load encrypted value:', error);
      } finally {
        setLoading(false);
      }
    };

    loadValue();
  }, [key]);

  const updateValue = async (newValue: T) => {
    try {
      const storage = await createEncryptedStorage();
      await storage.setEncrypted(
        key,
        JSON.stringify(newValue),
        classification
      );
      setValue(newValue);
      storage.close();
    } catch (error) {
      console.error('Failed to save encrypted value:', error);
      throw error;
    }
  };

  return { value, loading, updateValue };
}

// Usage in component:
function UserPreferences() {
  const { value, loading, updateValue } = useEncryptedStorage<{theme: string}>(
    'user-preferences',
    DataClassification.INTERNAL
  );

  if (loading) return <div>Loading...</div>;

  return (
    <button onClick={() => updateValue({ theme: 'dark' })}>
      Current theme: {value?.theme}
    </button>
  );
}
```

---

## Key Management

### Key Hierarchy

```
├─ Master Key (Environment Variable)
│  ├─ ENCRYPTION_MASTER_KEY (Backend)
│  └─ VITE_ENCRYPTION_KEY (Frontend)
│
├─ Derived Keys (PBKDF2)
│  ├─ PHI Encryption Key (250K iterations)
│  ├─ PII Encryption Key (150K iterations)
│  └─ General Encryption Key (100K iterations)
│
└─ Session Keys (Optional)
   └─ User-Specific Keys (derived from password)
```

### Key Rotation Policy (ISO 27001 A.10.1.2)

| Key Type | Rotation Period | Trigger Events |
|----------|----------------|----------------|
| **Master Keys** | 90 days | Security incident, personnel change |
| **Derived Keys** | 90 days | Master key rotation |
| **Session Keys** | Per session | User logout, timeout |

### Key Rotation Procedure

Use the automated key rotation script:

```bash
cd backend/scripts

# Dry run (preview changes)
python rotate_encryption_key.py --dry-run

# Execute rotation
python rotate_encryption_key.py --execute

# Rollback if needed
python rotate_encryption_key.py --rollback
```

See [DEPLOYMENT_SECURITY_GUIDE.md](DEPLOYMENT_SECURITY_GUIDE.md) for detailed rotation procedures.

### Key Storage Best Practices

✅ **DO:**
- Store master keys in environment variables
- Use secret management systems (AWS Secrets Manager, HashiCorp Vault)
- Rotate keys every 90 days
- Audit key access
- Use different keys for different environments (dev/staging/prod)

❌ **DON'T:**
- Hardcode keys in source code
- Commit keys to version control
- Share keys via email/chat
- Use same key across environments
- Store keys in configuration files

---

## Data Classification

### Classification Levels (ISO 27001 A.8.2.1)

| Level | Description | Examples | Encryption Required | Key Strength |
|-------|-------------|----------|---------------------|--------------|
| **PUBLIC** | Publicly available | Marketing materials | ❌ No | N/A |
| **INTERNAL** | Internal use only | User preferences, UI state | ✅ Standard | 100K iterations |
| **CONFIDENTIAL** | Sensitive business data | API keys, session tokens | ✅ Enhanced | 150K iterations |
| **PII** | Personal Identifiable Info | Names, emails, addresses | ✅ Enhanced | 150K iterations |
| **PHI** | Protected Health Info (HIPAA) | Patient data, medical images | ✅ Maximum | 250K iterations |

### Classification Guidelines

```python
# Backend
from app.core.security import DataClassification

# User email (PII)
encrypted, metadata = encryption.encrypt_string(
    "user@example.com",
    classification=DataClassification.PII
)

# Medical image (PHI)
encrypted, metadata = encryption.encrypt_data(
    dicom_image_data,
    classification=DataClassification.PHI
)

# API token (Confidential)
encrypted, metadata = encryption.encrypt_string(
    "sk_live_abc123",
    classification=DataClassification.CONFIDENTIAL
)
```

```typescript
// Frontend
import { DataClassification } from '@/utils/encryption';

// User preferences (Internal)
await storage.setEncrypted(
  'preferences',
  JSON.stringify(preferences),
  DataClassification.INTERNAL
);

// Patient notes (PHI)
await storage.setEncrypted(
  'patient-notes',
  notes,
  DataClassification.PHI
);
```

---

## Implementation Examples

### Example 1: Encrypt Redis Cache

```python
# services/cache_service.py
from app.core.security import create_encrypted_redis_client, DataClassification
import redis

class EncryptedCacheService:
    def __init__(self):
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD
        )
        self.cache = create_encrypted_redis_client(redis_client)

    def cache_patient_data(self, patient_id: str, data: dict):
        """Cache patient data with PHI encryption."""
        self.cache.set_encrypted(
            key=f"patient:{patient_id}",
            value=json.dumps(data),
            classification=DataClassification.PHI,
            ttl=3600,
            context={'patient_id': patient_id}
        )

    def get_patient_data(self, patient_id: str) -> dict:
        """Retrieve and decrypt patient data."""
        encrypted = self.cache.get_decrypted(f"patient:{patient_id}")
        return json.loads(encrypted) if encrypted else None
```

### Example 2: Encrypt User Session

```python
# services/auth_service.py
from app.core.security import EncryptionService, DataClassification

class AuthService:
    def __init__(self):
        self.encryption = create_encryption_service()

    def create_encrypted_session(self, user_id: str, session_data: dict):
        """Create encrypted session token."""
        ciphertext, metadata = self.encryption.encrypt_string(
            plaintext=json.dumps(session_data),
            classification=DataClassification.CONFIDENTIAL,
            context={'user_id': user_id, 'type': 'session'}
        )

        # Store in Redis with metadata
        session_package = {
            'ciphertext': ciphertext,
            'metadata': metadata
        }

        redis.setex(
            f"session:{user_id}",
            3600,
            json.dumps(session_package)
        )

    def verify_encrypted_session(self, user_id: str) -> dict:
        """Verify and decrypt session."""
        session_json = redis.get(f"session:{user_id}")
        if not session_json:
            raise ValueError("Session not found")

        session_package = json.loads(session_json)
        plaintext = self.encryption.decrypt_string(
            session_package['ciphertext'],
            session_package['metadata']
        )

        return json.loads(plaintext)
```

### Example 3: Offline-First App with Encrypted Storage

```typescript
// services/offlineStorage.ts
import { createEncryptedStorage, DataClassification } from '@/utils/encryption';

class OfflineStorageService {
  private storage: EncryptedStorage | null = null;

  async initialize() {
    this.storage = await createEncryptedStorage(
      'medical-imaging-offline',
      'encrypted-cache'
    );
  }

  async cacheMedicalImage(
    imageId: string,
    imageData: string,
    metadata: { patientId: string; imageType: string }
  ) {
    if (!this.storage) throw new Error('Storage not initialized');

    await this.storage.setEncrypted(
      `image:${imageId}`,
      imageData,
      DataClassification.PHI,
      metadata
    );
  }

  async getCachedImage(imageId: string): Promise<string | null> {
    if (!this.storage) throw new Error('Storage not initialized');

    return await this.storage.getDecrypted(`image:${imageId}`);
  }

  async syncWithServer() {
    // Sync encrypted local data with server
    // ...
  }
}
```

---

## Security Architecture

### Threat Model

| Threat | Mitigation |
|--------|------------|
| **Data theft from disk** | AES-256-GCM encryption prevents reading |
| **Data tampering** | GCM authentication tag detects modifications |
| **Key exposure** | Keys stored in env vars, not extractable |
| **Replay attacks** | Unique nonces prevent replay |
| **Insider threats** | Key rotation + access logging |

### Defense in Depth

```
Layer 1: TLS/SSL (Data in Transit)
    ↓
Layer 2: Authentication & Authorization (Access Control)
    ↓
Layer 3: Input Validation (Injection Prevention)
    ↓
Layer 4: ENCRYPTION AT REST ← We are here
    ↓
Layer 5: Audit Logging (Detection)
```

---

## Best Practices

### 1. Always Classify Data

```python
# ❌ BAD: No classification
encrypted, meta = encryption.encrypt_string("sensitive data")

# ✅ GOOD: Explicit classification
encrypted, meta = encryption.encrypt_string(
    "sensitive data",
    classification=DataClassification.PHI
)
```

### 2. Include Context Metadata

```python
# ✅ GOOD: Rich context for audit trail
encrypted, meta = encryption.encrypt_string(
    patient_ssn,
    classification=DataClassification.PII,
    context={
        'patient_id': 'P12345',
        'field': 'ssn',
        'accessed_by': current_user.id,
        'purpose': 'billing'
    }
)
```

### 3. Handle Decryption Errors Gracefully

```python
try:
    plaintext = encryption.decrypt_string(ciphertext, metadata)
except DecryptionError as e:
    # Authentication failed - data was tampered with
    logger.critical(f"Data integrity violation: {e}")
    audit_logger.log_security_event(
        event_type=AuditEventType.SECURITY_DATA_INTEGRITY_VIOLATION,
        severity=AuditSeverity.CRITICAL,
        description="Tampered encrypted data detected"
    )
    raise HTTPException(status_code=500, detail="Data integrity check failed")
```

### 4. Rotate Keys Regularly

```bash
# Automated rotation every 90 days
0 0 1 */3 * /app/scripts/rotate_encryption_key.py --execute
```

### 5. Use Appropriate TTL

```python
# Short TTL for session data
encrypted_redis.set_encrypted(
    key='session:abc123',
    value=session_data,
    classification=DataClassification.CONFIDENTIAL,
    ttl=3600  # 1 hour
)

# Longer TTL for cached data
encrypted_redis.set_encrypted(
    key='patient:P12345',
    value=patient_data,
    classification=DataClassification.PHI,
    ttl=86400  # 24 hours
)
```

---

## Compliance

### ISO 27001 Compliance

| Control | Requirement | Implementation |
|---------|-------------|----------------|
| **A.10.1.1** | Cryptographic controls policy | AES-256-GCM for all sensitive data |
| **A.10.1.2** | Key management | PBKDF2 key derivation, 90-day rotation |
| **A.18.1.5** | Regulation of cryptographic controls | NIST-approved algorithms, FIPS 140-2 |

### HIPAA Compliance

| Requirement | Implementation |
|-------------|----------------|
| **§ 164.312(a)(2)(iv)** | Encryption mechanism | AES-256-GCM for PHI at rest |
| **§ 164.312(e)(2)(ii)** | Encryption standard | NIST SP 800-38D compliant |

### NIST Standards

- ✅ **NIST SP 800-38D** - AES-GCM mode
- ✅ **NIST SP 800-132** - PBKDF2 key derivation
- ✅ **FIPS 140-2** - Web Crypto API (browser) / cryptography library (backend)

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-01-15 | Initial implementation with AES-256-GCM |
| 1.1.0 | 2025-01-15 | Added frontend IndexedDB encryption |
| 1.2.0 | 2025-01-15 | Added data classification system |

---

**Last Updated:** 2025-01-15
**Compliance:** ISO/IEC 27001:2022, HIPAA, NIST SP 800-38D
**Encryption Standard:** AES-256-GCM (FIPS 140-2)
