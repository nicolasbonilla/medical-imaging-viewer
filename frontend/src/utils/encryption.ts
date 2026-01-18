/**
 * Data-at-Rest Encryption for IndexedDB
 * ISO 27001 A.10.1.1 - Policy on the use of cryptographic controls
 * ISO 27001 A.10.1.2 - Key management
 *
 * Provides AES-GCM encryption for sensitive data stored in browser IndexedDB.
 * Uses Web Crypto API for FIPS 140-2 compliant encryption.
 *
 * @module utils/encryption
 */

/**
 * Data classification levels (ISO 27001 A.8.2.1)
 */
export enum DataClassification {
  PUBLIC = 'public',
  INTERNAL = 'internal',
  CONFIDENTIAL = 'confidential',
  PHI = 'phi', // HIPAA Protected Health Information
  PII = 'pii', // Personal Identifiable Information
}

/**
 * Encryption metadata stored alongside ciphertext
 */
export interface EncryptionMetadata {
  version: string;
  algorithm: string;
  keyId: string;
  iv: string; // Base64-encoded initialization vector
  salt: string; // Base64-encoded salt
  classification: DataClassification;
  encryptedAt: string; // ISO 8601 timestamp
  context?: Record<string, any>;
}

/**
 * Encrypted package containing ciphertext and metadata
 */
export interface EncryptedPackage {
  ciphertext: string; // Base64-encoded
  metadata: EncryptionMetadata;
}

/**
 * Encryption configuration
 */
interface EncryptionConfig {
  algorithm: string;
  keySize: number;
  ivSize: number;
  saltSize: number;
  kdfIterations: number;
}

/**
 * Default encryption configuration
 * - AES-GCM: Authenticated encryption with associated data (AEAD)
 * - 256-bit keys: Maximum security
 * - 96-bit IV: Recommended for GCM mode
 * - 128-bit salt: NIST recommendation
 * - 100,000 iterations: NIST SP 800-132 recommendation
 */
const DEFAULT_CONFIG: EncryptionConfig = {
  algorithm: 'AES-GCM',
  keySize: 256,
  ivSize: 96,
  saltSize: 128,
  kdfIterations: 100000,
};

/**
 * AES-GCM Encryption Service
 *
 * Provides browser-based encryption using Web Crypto API.
 * All cryptographic operations use browser-native implementations.
 */
export class EncryptionService {
  private config: EncryptionConfig;
  private masterKey: string;
  private derivedKey: CryptoKey | null = null;
  private salt: Uint8Array | null = null;
  private keyId: string = '';

  constructor(masterKey: string, config: Partial<EncryptionConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.masterKey = masterKey;
  }

  /**
   * Initialize encryption service by deriving encryption key
   */
  async initialize(): Promise<void> {
    try {
      // Generate random salt
      this.salt = crypto.getRandomValues(new Uint8Array(this.config.saltSize / 8));

      // Derive key from master key using PBKDF2
      this.derivedKey = await this.deriveKey(this.masterKey, this.salt);

      // Calculate key fingerprint
      this.keyId = await this.calculateKeyId(this.derivedKey);

      console.debug('[Encryption] Service initialized', {
        keyId: this.keyId,
        algorithm: this.config.algorithm,
      });
    } catch (error) {
      console.error('[Encryption] Failed to initialize:', error);
      throw new Error(`Encryption service initialization failed: ${error}`);
    }
  }

  /**
   * Encrypt data with AES-GCM
   *
   * @param data - Plaintext data to encrypt
   * @param classification - Data classification level
   * @param context - Optional context metadata
   * @returns Encrypted package with metadata
   */
  async encrypt(
    data: string | ArrayBuffer,
    classification: DataClassification = DataClassification.CONFIDENTIAL,
    context?: Record<string, any>
  ): Promise<EncryptedPackage> {
    if (!this.derivedKey || !this.salt) {
      throw new Error('Encryption service not initialized. Call initialize() first.');
    }

    try {
      // Convert data to ArrayBuffer
      const plaintext = typeof data === 'string'
        ? new TextEncoder().encode(data)
        : new Uint8Array(data);

      // Generate random IV (MUST be unique for each encryption)
      const iv = crypto.getRandomValues(new Uint8Array(this.config.ivSize / 8));

      // Prepare additional authenticated data (AAD)
      const aad = this.buildAAD(classification, context);

      // Encrypt with AES-GCM
      const ciphertext = await crypto.subtle.encrypt(
        {
          name: this.config.algorithm,
          iv: iv as BufferSource,
          additionalData: aad as BufferSource,
        },
        this.derivedKey,
        plaintext
      );

      // Build metadata
      const metadata: EncryptionMetadata = {
        version: '1.0',
        algorithm: this.config.algorithm,
        keyId: this.keyId,
        iv: this.arrayBufferToBase64(iv),
        salt: this.arrayBufferToBase64(this.salt),
        classification,
        encryptedAt: new Date().toISOString(),
        context: context || {},
      };

      // Build encrypted package
      const package_: EncryptedPackage = {
        ciphertext: this.arrayBufferToBase64(ciphertext),
        metadata,
      };

      console.debug('[Encryption] Data encrypted', {
        keyId: this.keyId,
        classification,
        size: ciphertext.byteLength,
      });

      return package_;
    } catch (error) {
      console.error('[Encryption] Encryption failed:', error);
      throw new Error(`Encryption failed: ${error}`);
    }
  }

  /**
   * Decrypt data using stored metadata
   *
   * @param encryptedPackage - Encrypted package from encrypt()
   * @returns Decrypted plaintext
   */
  async decrypt(encryptedPackage: EncryptedPackage): Promise<string> {
    if (!this.derivedKey) {
      throw new Error('Encryption service not initialized. Call initialize() first.');
    }

    try {
      const { ciphertext, metadata } = encryptedPackage;

      // Validate metadata
      this.validateMetadata(metadata);

      // Convert ciphertext and IV from base64
      const ciphertextBuffer = this.base64ToArrayBuffer(ciphertext);
      const iv = this.base64ToArrayBuffer(metadata.iv);

      // Rebuild AAD
      const aad = this.buildAAD(
        metadata.classification as DataClassification,
        metadata.context
      );

      // Decrypt with AES-GCM (includes authentication tag verification)
      const plaintextBuffer = await crypto.subtle.decrypt(
        {
          name: this.config.algorithm,
          iv: iv as BufferSource,
          additionalData: aad as BufferSource,
        },
        this.derivedKey,
        ciphertextBuffer as BufferSource
      );

      // Convert to string
      const plaintext = new TextDecoder().decode(plaintextBuffer);

      console.debug('[Encryption] Data decrypted', {
        keyId: metadata.keyId,
        classification: metadata.classification,
      });

      return plaintext;
    } catch (error) {
      // Authentication tag verification failed - data was tampered with
      if (error instanceof DOMException && error.name === 'OperationError') {
        console.error('[Encryption] Authentication failed - data integrity violation');
        throw new Error('Data integrity violation: Authentication failed');
      }

      console.error('[Encryption] Decryption failed:', error);
      throw new Error(`Decryption failed: ${error}`);
    }
  }

  /**
   * Derive encryption key from master key using PBKDF2
   */
  private async deriveKey(
    masterKey: string,
    salt: Uint8Array
  ): Promise<CryptoKey> {
    // Import master key
    const keyMaterial = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(masterKey),
      { name: 'PBKDF2' },
      false,
      ['deriveBits', 'deriveKey']
    );

    // Derive key using PBKDF2
    const derivedKey = await crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: salt as BufferSource,
        iterations: this.config.kdfIterations,
        hash: 'SHA-256',
      },
      keyMaterial,
      {
        name: this.config.algorithm,
        length: this.config.keySize,
      },
      false, // Not extractable
      ['encrypt', 'decrypt']
    );

    return derivedKey;
  }

  /**
   * Calculate key fingerprint (SHA-256 hash)
   */
  private async calculateKeyId(key: CryptoKey): Promise<string> {
    // Export key to get raw bytes
    const exportedKey = await crypto.subtle.exportKey('raw', key);

    // Hash with SHA-256
    const hashBuffer = await crypto.subtle.digest('SHA-256', exportedKey);

    // Convert to hex string (first 16 chars)
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');

    return hashHex.substring(0, 16);
  }

  /**
   * Build Additional Authenticated Data (AAD) for AEAD
   */
  private buildAAD(
    classification: DataClassification,
    context?: Record<string, any>
  ): Uint8Array {
    const aad = {
      classification,
      context: context || {},
    };

    const aadJson = JSON.stringify(aad);
    return new TextEncoder().encode(aadJson);
  }

  /**
   * Validate encryption metadata
   */
  private validateMetadata(metadata: EncryptionMetadata): void {
    const requiredFields: (keyof EncryptionMetadata)[] = [
      'version',
      'algorithm',
      'keyId',
      'iv',
      'salt',
      'classification',
    ];

    for (const field of requiredFields) {
      if (!(field in metadata)) {
        throw new Error(`Missing required metadata field: ${field}`);
      }
    }

    // Validate algorithm
    if (metadata.algorithm !== this.config.algorithm) {
      throw new Error(`Unsupported algorithm: ${metadata.algorithm}`);
    }

    // Validate key ID
    if (metadata.keyId !== this.keyId) {
      throw new Error(
        `Key mismatch: expected ${this.keyId}, got ${metadata.keyId}`
      );
    }
  }

  /**
   * Convert ArrayBuffer to base64 string
   */
  private arrayBufferToBase64(buffer: ArrayBuffer | Uint8Array): string {
    const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  /**
   * Convert base64 string to ArrayBuffer
   */
  private base64ToArrayBuffer(base64: string): Uint8Array {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }
}

/**
 * Encrypted IndexedDB Storage
 *
 * Wrapper around IndexedDB with transparent encryption/decryption.
 * ISO 27001 A.10.1.1 - Automatic encryption of sensitive data
 */
export class EncryptedStorage {
  private dbName: string;
  private storeName: string;
  private encryption: EncryptionService;
  private db: IDBDatabase | null = null;

  constructor(
    dbName: string,
    storeName: string,
    encryptionService: EncryptionService
  ) {
    this.dbName = dbName;
    this.storeName = storeName;
    this.encryption = encryptionService;
  }

  /**
   * Open IndexedDB database
   */
  async open(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, 1);

      request.onerror = () => {
        console.error('[EncryptedStorage] Failed to open database:', request.error);
        reject(new Error(`Failed to open database: ${request.error}`));
      };

      request.onsuccess = () => {
        this.db = request.result;
        console.debug('[EncryptedStorage] Database opened', {
          dbName: this.dbName,
          storeName: this.storeName,
        });
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // Create object store if it doesn't exist
        if (!db.objectStoreNames.contains(this.storeName)) {
          db.createObjectStore(this.storeName);
          console.debug('[EncryptedStorage] Object store created', {
            storeName: this.storeName,
          });
        }
      };
    });
  }

  /**
   * Set encrypted value in IndexedDB
   *
   * @param key - Storage key
   * @param value - Plaintext value to encrypt
   * @param classification - Data classification level
   * @param context - Optional context metadata
   */
  async setEncrypted(
    key: string,
    value: string,
    classification: DataClassification = DataClassification.CONFIDENTIAL,
    context?: Record<string, any>
  ): Promise<void> {
    if (!this.db) {
      throw new Error('Database not opened. Call open() first.');
    }

    try {
      // Encrypt value
      const encryptedPackage = await this.encryption.encrypt(
        value,
        classification,
        context
      );

      // Store encrypted package
      return new Promise((resolve, reject) => {
        const transaction = this.db!.transaction([this.storeName], 'readwrite');
        const store = transaction.objectStore(this.storeName);
        const request = store.put(encryptedPackage, key);

        request.onerror = () => {
          console.error('[EncryptedStorage] Failed to store encrypted value:', request.error);
          reject(new Error(`Failed to store encrypted value: ${request.error}`));
        };

        request.onsuccess = () => {
          console.debug('[EncryptedStorage] Encrypted value stored', {
            key,
            classification,
          });
          resolve();
        };
      });
    } catch (error) {
      console.error('[EncryptedStorage] Failed to set encrypted value:', error);
      throw error;
    }
  }

  /**
   * Get and decrypt value from IndexedDB
   *
   * @param key - Storage key
   * @returns Decrypted value or null if not found
   */
  async getDecrypted(key: string): Promise<string | null> {
    if (!this.db) {
      throw new Error('Database not opened. Call open() first.');
    }

    try {
      const encryptedPackage = await new Promise<EncryptedPackage | null>(
        (resolve, reject) => {
          const transaction = this.db!.transaction([this.storeName], 'readonly');
          const store = transaction.objectStore(this.storeName);
          const request = store.get(key);

          request.onerror = () => {
            console.error('[EncryptedStorage] Failed to retrieve value:', request.error);
            reject(new Error(`Failed to retrieve value: ${request.error}`));
          };

          request.onsuccess = () => {
            resolve(request.result || null);
          };
        }
      );

      if (!encryptedPackage) {
        return null;
      }

      // Decrypt value
      const plaintext = await this.encryption.decrypt(encryptedPackage);

      console.debug('[EncryptedStorage] Decrypted value retrieved', { key });

      return plaintext;
    } catch (error) {
      console.error('[EncryptedStorage] Failed to get decrypted value:', error);
      throw error;
    }
  }

  /**
   * Delete key from IndexedDB
   */
  async delete(key: string): Promise<void> {
    if (!this.db) {
      throw new Error('Database not opened. Call open() first.');
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.storeName], 'readwrite');
      const store = transaction.objectStore(this.storeName);
      const request = store.delete(key);

      request.onerror = () => {
        console.error('[EncryptedStorage] Failed to delete key:', request.error);
        reject(new Error(`Failed to delete key: ${request.error}`));
      };

      request.onsuccess = () => {
        console.debug('[EncryptedStorage] Key deleted', { key });
        resolve();
      };
    });
  }

  /**
   * Check if key exists in IndexedDB
   */
  async exists(key: string): Promise<boolean> {
    if (!this.db) {
      throw new Error('Database not opened. Call open() first.');
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.storeName], 'readonly');
      const store = transaction.objectStore(this.storeName);
      const request = store.getKey(key);

      request.onerror = () => {
        console.error('[EncryptedStorage] Failed to check existence:', request.error);
        reject(new Error(`Failed to check existence: ${request.error}`));
      };

      request.onsuccess = () => {
        resolve(request.result !== undefined);
      };
    });
  }

  /**
   * Close database connection
   */
  close(): void {
    if (this.db) {
      this.db.close();
      this.db = null;
      console.debug('[EncryptedStorage] Database closed');
    }
  }
}

/**
 * Create encryption service with master key from environment
 */
export function createEncryptionService(): EncryptionService {
  // In production, this should come from a secure source (e.g., derived from user password)
  const masterKey = import.meta.env.VITE_ENCRYPTION_KEY || 'development-master-key-CHANGE-IN-PRODUCTION';

  if (masterKey === 'development-master-key-CHANGE-IN-PRODUCTION') {
    console.warn(
      '[Encryption] Using default development master key. ' +
      'Set VITE_ENCRYPTION_KEY in production!'
    );
  }

  return new EncryptionService(masterKey);
}

/**
 * Create encrypted IndexedDB storage
 */
export async function createEncryptedStorage(
  dbName: string = 'medical-imaging-viewer',
  storeName: string = 'encrypted-data'
): Promise<EncryptedStorage> {
  const encryption = createEncryptionService();
  await encryption.initialize();

  const storage = new EncryptedStorage(dbName, storeName, encryption);
  await storage.open();

  return storage;
}
