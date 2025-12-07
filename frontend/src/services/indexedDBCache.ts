/**
 * IndexedDB Cache Service.
 *
 * Provides persistent local storage for medical imaging slices using IndexedDB.
 * Enables offline access and reduces network requests.
 *
 * Features:
 * - Persistent slice caching with metadata
 * - LRU eviction policy for size management
 * - Quota management and monitoring
 * - Async/await API for easy usage
 * - Automatic expiration handling
 * - Storage statistics and diagnostics
 *
 * Expected Performance:
 * - Write: ~10-50ms per slice (512x512 uint16)
 * - Read: ~5-20ms per slice
 * - Storage: 50MB for ~200 slices (256KB each)
 *
 * @module services/indexedDBCache
 */

/**
 * Cached slice entry.
 */
export interface CachedSlice {
  /**
   * Unique cache key (file_id:slice_index).
   */
  key: string;

  /**
   * File identifier.
   */
  fileId: string;

  /**
   * Slice index.
   */
  sliceIndex: number;

  /**
   * Pixel data (TypedArray).
   */
  data: ArrayBuffer;

  /**
   * Image dimensions.
   */
  width: number;
  height: number;

  /**
   * Data type code.
   */
  dtype: string;

  /**
   * Window/level values.
   */
  windowCenter: number;
  windowWidth: number;

  /**
   * Min/max values.
   */
  minValue: number;
  maxValue: number;

  /**
   * Timestamp when cached (milliseconds since epoch).
   */
  timestamp: number;

  /**
   * Last access timestamp (for LRU).
   */
  lastAccess: number;

  /**
   * Size in bytes.
   */
  size: number;

  /**
   * Optional expiration time (milliseconds since epoch).
   */
  expiresAt?: number;
}

/**
 * Cache statistics.
 */
export interface CacheStats {
  /**
   * Total number of cached items.
   */
  totalItems: number;

  /**
   * Total storage used in bytes.
   */
  totalSize: number;

  /**
   * Available quota in bytes.
   */
  availableQuota: number;

  /**
   * Used quota in bytes.
   */
  usedQuota: number;

  /**
   * Cache hit count.
   */
  hits: number;

  /**
   * Cache miss count.
   */
  misses: number;

  /**
   * Hit rate (hits / (hits + misses)).
   */
  hitRate: number;
}

/**
 * IndexedDB cache configuration.
 */
export interface IndexedDBCacheConfig {
  /**
   * Database name.
   * @default 'medical-imaging-cache'
   */
  dbName?: string;

  /**
   * Database version.
   * @default 1
   */
  dbVersion?: number;

  /**
   * Object store name.
   * @default 'slices'
   */
  storeName?: string;

  /**
   * Maximum cache size in bytes.
   * @default 50MB
   */
  maxCacheSize?: number;

  /**
   * Default expiration time in milliseconds.
   * @default 24 hours
   */
  defaultExpiration?: number;

  /**
   * Enable automatic eviction when quota exceeded.
   * @default true
   */
  enableAutoEviction?: boolean;

  /**
   * Enable performance logging.
   * @default false
   */
  enableLogging?: boolean;
}

/**
 * Default configuration.
 */
const DEFAULT_CONFIG: Required<IndexedDBCacheConfig> = {
  dbName: 'medical-imaging-cache',
  dbVersion: 1,
  storeName: 'slices',
  maxCacheSize: 50 * 1024 * 1024, // 50MB
  defaultExpiration: 24 * 60 * 60 * 1000, // 24 hours
  enableAutoEviction: true,
  enableLogging: false,
};

/**
 * Log debug message.
 */
function log(enableLogging: boolean, message: string, ...args: any[]) {
  if (enableLogging) {
    console.log(`[IndexedDBCache] ${message}`, ...args);
  }
}

/**
 * IndexedDB Cache Service.
 *
 * Provides persistent caching for medical imaging slices.
 */
export class IndexedDBCache {
  private config: Required<IndexedDBCacheConfig>;
  private db: IDBDatabase | null = null;
  private initPromise: Promise<void> | null = null;

  // Statistics
  private stats = {
    hits: 0,
    misses: 0,
  };

  constructor(config: IndexedDBCacheConfig = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Initialize the IndexedDB connection.
   */
  async init(): Promise<void> {
    if (this.db) {
      return; // Already initialized
    }

    if (this.initPromise) {
      return this.initPromise; // Initialization in progress
    }

    this.initPromise = this._init();
    await this.initPromise;
  }

  private async _init(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (typeof indexedDB === 'undefined') {
        reject(new Error('IndexedDB is not supported'));
        return;
      }

      const request = indexedDB.open(this.config.dbName, this.config.dbVersion);

      request.onerror = () => {
        reject(new Error(`Failed to open IndexedDB: ${request.error}`));
      };

      request.onsuccess = () => {
        this.db = request.result;
        log(this.config.enableLogging, 'IndexedDB initialized');
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // Create object store if it doesn't exist
        if (!db.objectStoreNames.contains(this.config.storeName)) {
          const store = db.createObjectStore(this.config.storeName, {
            keyPath: 'key',
          });

          // Create indices
          store.createIndex('fileId', 'fileId', { unique: false });
          store.createIndex('timestamp', 'timestamp', { unique: false });
          store.createIndex('lastAccess', 'lastAccess', { unique: false });
          store.createIndex('expiresAt', 'expiresAt', { unique: false });

          log(this.config.enableLogging, 'Object store created');
        }
      };
    });
  }

  /**
   * Get a cached slice.
   *
   * @param fileId - File identifier
   * @param sliceIndex - Slice index
   * @returns Cached slice or null if not found
   */
  async get(fileId: string, sliceIndex: number): Promise<CachedSlice | null> {
    await this.init();

    const key = `${fileId}:${sliceIndex}`;
    const startTime = performance.now();

    try {
      const slice = await this._get(key);

      if (!slice) {
        this.stats.misses++;
        log(this.config.enableLogging, `Cache MISS: ${key}`);
        return null;
      }

      // Check expiration
      if (slice.expiresAt && slice.expiresAt < Date.now()) {
        this.stats.misses++;
        log(this.config.enableLogging, `Cache EXPIRED: ${key}`);

        // Delete expired entry
        await this.delete(fileId, sliceIndex);
        return null;
      }

      // Update last access time
      slice.lastAccess = Date.now();
      await this._put(slice);

      this.stats.hits++;

      const elapsed = performance.now() - startTime;
      log(
        this.config.enableLogging,
        `Cache HIT: ${key} (${elapsed.toFixed(2)}ms)`
      );

      return slice;
    } catch (error) {
      console.error(`[IndexedDBCache] Failed to get ${key}:`, error);
      this.stats.misses++;
      return null;
    }
  }

  /**
   * Put a slice into the cache.
   *
   * @param slice - Slice to cache
   */
  async put(slice: Omit<CachedSlice, 'key' | 'timestamp' | 'lastAccess' | 'size' | 'expiresAt'>): Promise<void> {
    await this.init();

    const key = `${slice.fileId}:${slice.sliceIndex}`;
    const startTime = performance.now();

    try {
      const now = Date.now();

      const entry: CachedSlice = {
        key,
        ...slice,
        timestamp: now,
        lastAccess: now,
        size: slice.data.byteLength,
        expiresAt: now + this.config.defaultExpiration,
      };

      // Check cache size before adding
      if (this.config.enableAutoEviction) {
        await this._ensureQuota(entry.size);
      }

      await this._put(entry);

      const elapsed = performance.now() - startTime;
      log(
        this.config.enableLogging,
        `Cached: ${key} (${(entry.size / 1024).toFixed(2)} KB, ${elapsed.toFixed(2)}ms)`
      );
    } catch (error) {
      console.error(`[IndexedDBCache] Failed to cache ${key}:`, error);
      throw error;
    }
  }

  /**
   * Delete a cached slice.
   *
   * @param fileId - File identifier
   * @param sliceIndex - Slice index
   */
  async delete(fileId: string, sliceIndex: number): Promise<void> {
    await this.init();

    const key = `${fileId}:${sliceIndex}`;

    try {
      await this._delete(key);
      log(this.config.enableLogging, `Deleted: ${key}`);
    } catch (error) {
      console.error(`[IndexedDBCache] Failed to delete ${key}:`, error);
      throw error;
    }
  }

  /**
   * Clear all cached slices for a file.
   *
   * @param fileId - File identifier
   */
  async clearFile(fileId: string): Promise<void> {
    await this.init();

    try {
      const slices = await this._getAllByIndex('fileId', fileId);

      for (const slice of slices) {
        await this._delete(slice.key);
      }

      log(this.config.enableLogging, `Cleared file: ${fileId} (${slices.length} slices)`);
    } catch (error) {
      console.error(`[IndexedDBCache] Failed to clear file ${fileId}:`, error);
      throw error;
    }
  }

  /**
   * Clear entire cache.
   */
  async clearAll(): Promise<void> {
    await this.init();

    try {
      await this._clear();
      log(this.config.enableLogging, 'Cleared all cache');
    } catch (error) {
      console.error('[IndexedDBCache] Failed to clear cache:', error);
      throw error;
    }
  }

  /**
   * Get cache statistics.
   */
  async getStats(): Promise<CacheStats> {
    await this.init();

    try {
      const slices = await this._getAll();
      const totalItems = slices.length;
      const totalSize = slices.reduce((sum, slice) => sum + slice.size, 0);

      // Get quota information
      let availableQuota = 0;
      let usedQuota = 0;

      if ('storage' in navigator && 'estimate' in navigator.storage) {
        const estimate = await navigator.storage.estimate();
        availableQuota = estimate.quota || 0;
        usedQuota = estimate.usage || 0;
      }

      const hitRate =
        this.stats.hits + this.stats.misses > 0
          ? this.stats.hits / (this.stats.hits + this.stats.misses)
          : 0;

      return {
        totalItems,
        totalSize,
        availableQuota,
        usedQuota,
        hits: this.stats.hits,
        misses: this.stats.misses,
        hitRate,
      };
    } catch (error) {
      console.error('[IndexedDBCache] Failed to get stats:', error);
      throw error;
    }
  }

  /**
   * Evict old entries to ensure quota.
   */
  private async _ensureQuota(requiredSize: number): Promise<void> {
    const stats = await this.getStats();

    if (stats.totalSize + requiredSize <= this.config.maxCacheSize) {
      return; // Quota available
    }

    log(
      this.config.enableLogging,
      `Quota exceeded, evicting LRU entries (need ${(requiredSize / 1024).toFixed(2)} KB)`
    );

    // Get all entries sorted by last access (LRU)
    const slices = await this._getAllByIndex('lastAccess');
    slices.sort((a, b) => a.lastAccess - b.lastAccess);

    let freedSize = 0;

    for (const slice of slices) {
      await this._delete(slice.key);
      freedSize += slice.size;

      log(
        this.config.enableLogging,
        `Evicted: ${slice.key} (${(slice.size / 1024).toFixed(2)} KB)`
      );

      if (stats.totalSize - freedSize + requiredSize <= this.config.maxCacheSize) {
        break;
      }
    }

    log(
      this.config.enableLogging,
      `Evicted ${(freedSize / 1024).toFixed(2)} KB`
    );
  }

  /**
   * Low-level get operation.
   */
  private async _get(key: string): Promise<CachedSlice | null> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.config.storeName], 'readonly');
      const store = transaction.objectStore(this.config.storeName);
      const request = store.get(key);

      request.onsuccess = () => {
        resolve(request.result || null);
      };

      request.onerror = () => {
        reject(request.error);
      };
    });
  }

  /**
   * Low-level put operation.
   */
  private async _put(slice: CachedSlice): Promise<void> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.config.storeName], 'readwrite');
      const store = transaction.objectStore(this.config.storeName);
      const request = store.put(slice);

      request.onsuccess = () => {
        resolve();
      };

      request.onerror = () => {
        reject(request.error);
      };
    });
  }

  /**
   * Low-level delete operation.
   */
  private async _delete(key: string): Promise<void> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.config.storeName], 'readwrite');
      const store = transaction.objectStore(this.config.storeName);
      const request = store.delete(key);

      request.onsuccess = () => {
        resolve();
      };

      request.onerror = () => {
        reject(request.error);
      };
    });
  }

  /**
   * Low-level clear operation.
   */
  private async _clear(): Promise<void> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.config.storeName], 'readwrite');
      const store = transaction.objectStore(this.config.storeName);
      const request = store.clear();

      request.onsuccess = () => {
        resolve();
      };

      request.onerror = () => {
        reject(request.error);
      };
    });
  }

  /**
   * Get all entries.
   */
  private async _getAll(): Promise<CachedSlice[]> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.config.storeName], 'readonly');
      const store = transaction.objectStore(this.config.storeName);
      const request = store.getAll();

      request.onsuccess = () => {
        resolve(request.result);
      };

      request.onerror = () => {
        reject(request.error);
      };
    });
  }

  /**
   * Get all entries by index.
   */
  private async _getAllByIndex(indexName: string, query?: string): Promise<CachedSlice[]> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.config.storeName], 'readonly');
      const store = transaction.objectStore(this.config.storeName);
      const index = store.index(indexName);
      const request = query ? index.getAll(query) : index.getAll();

      request.onsuccess = () => {
        resolve(request.result);
      };

      request.onerror = () => {
        reject(request.error);
      };
    });
  }

  /**
   * Close the database connection.
   */
  close(): void {
    if (this.db) {
      this.db.close();
      this.db = null;
      this.initPromise = null;
      log(this.config.enableLogging, 'Database closed');
    }
  }
}
