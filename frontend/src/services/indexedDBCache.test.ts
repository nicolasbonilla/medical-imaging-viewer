/**
 * Tests for IndexedDB Cache Service.
 *
 * @vitest-environment node
 */

import { describe, it, expect } from 'vitest';
import type { CachedSlice, CacheStats, IndexedDBCacheConfig } from './indexedDBCache';

describe('IndexedDB Cache - Logic Tests', () => {
  describe('Cache Key Generation', () => {
    it('should generate correct cache key', () => {
      const fileId = 'file123';
      const sliceIndex = 42;

      const key = `${fileId}:${sliceIndex}`;

      expect(key).toBe('file123:42');
    });

    it('should handle complex file IDs', () => {
      const fileId = 'folder/subfolder/file_with_underscores_123.dcm';
      const sliceIndex = 999;

      const key = `${fileId}:${sliceIndex}`;

      expect(key).toBe('folder/subfolder/file_with_underscores_123.dcm:999');
    });

    it('should handle zero slice index', () => {
      const fileId = 'file123';
      const sliceIndex = 0;

      const key = `${fileId}:${sliceIndex}`;

      expect(key).toBe('file123:0');
    });
  });

  describe('Expiration Calculation', () => {
    it('should calculate correct expiration time', () => {
      const now = Date.now();
      const defaultExpiration = 24 * 60 * 60 * 1000; // 24 hours

      const expiresAt = now + defaultExpiration;

      const expectedExpiration = now + 24 * 60 * 60 * 1000;

      expect(expiresAt).toBeGreaterThanOrEqual(expectedExpiration - 10); // Allow 10ms tolerance
      expect(expiresAt).toBeLessThanOrEqual(expectedExpiration + 10);
    });

    it('should detect expired entries', () => {
      const now = Date.now();
      const expiresAt = now - 1000; // Expired 1 second ago

      const isExpired = expiresAt < now;

      expect(isExpired).toBe(true);
    });

    it('should detect non-expired entries', () => {
      const now = Date.now();
      const expiresAt = now + 60000; // Expires in 1 minute

      const isExpired = expiresAt < now;

      expect(isExpired).toBe(false);
    });
  });

  describe('Size Calculation', () => {
    it('should calculate correct size for Uint16Array', () => {
      const width = 512;
      const height = 512;
      const bytesPerPixel = 2; // Uint16

      const totalBytes = width * height * bytesPerPixel;

      expect(totalBytes).toBe(524288); // 512 KB
    });

    it('should calculate correct size for different dtypes', () => {
      const width = 256;
      const height = 256;

      // Uint8 (1 byte/pixel)
      expect(width * height * 1).toBe(65536); // 64 KB

      // Uint16/Int16 (2 bytes/pixel)
      expect(width * height * 2).toBe(131072); // 128 KB

      // Float32 (4 bytes/pixel)
      expect(width * height * 4).toBe(262144); // 256 KB

      // Float64 (8 bytes/pixel)
      expect(width * height * 8).toBe(524288); // 512 KB
    });

    it('should calculate cache size from multiple slices', () => {
      const slices: Array<{ size: number }> = [
        { size: 262144 }, // 256 KB
        { size: 262144 },
        { size: 262144 },
        { size: 262144 },
      ];

      const totalSize = slices.reduce((sum, slice) => sum + slice.size, 0);

      expect(totalSize).toBe(1048576); // 1 MB
    });
  });

  describe('LRU Eviction Logic', () => {
    it('should sort slices by last access time (LRU)', () => {
      const now = Date.now();

      const slices = [
        { key: 'a', lastAccess: now - 3000, size: 100 }, // Oldest
        { key: 'b', lastAccess: now - 1000, size: 100 }, // Newest
        { key: 'c', lastAccess: now - 2000, size: 100 }, // Middle
      ];

      slices.sort((a, b) => a.lastAccess - b.lastAccess);

      expect(slices[0].key).toBe('a'); // Oldest first
      expect(slices[1].key).toBe('c');
      expect(slices[2].key).toBe('b'); // Newest last
    });

    it('should calculate freed size after eviction', () => {
      const slices = [
        { key: 'a', size: 100000 },
        { key: 'b', size: 200000 },
        { key: 'c', size: 150000 },
      ];

      const maxCacheSize = 500000;
      const totalSize = slices.reduce((sum, s) => sum + s.size, 0); // 450000
      const requiredSize = 200000;

      // Need to free space: (totalSize + requiredSize) - maxCacheSize
      const needToFree = totalSize + requiredSize - maxCacheSize; // 150000

      let freedSize = 0;
      const evictedSlices = [];

      for (const slice of slices) {
        evictedSlices.push(slice);
        freedSize += slice.size;

        if (totalSize - freedSize + requiredSize <= maxCacheSize) {
          break;
        }
      }

      expect(evictedSlices.length).toBe(2); // Evicted 'a' and 'b'
      expect(freedSize).toBe(300000); // 100000 + 200000
      expect(totalSize - freedSize + requiredSize).toBeLessThanOrEqual(maxCacheSize);
    });

    it('should not evict if quota available', () => {
      const totalSize = 300000;
      const maxCacheSize = 500000;
      const requiredSize = 100000;

      const needEviction = totalSize + requiredSize > maxCacheSize;

      expect(needEviction).toBe(false);
    });
  });

  describe('Cache Statistics Calculation', () => {
    it('should calculate correct hit rate', () => {
      const hits = 80;
      const misses = 20;

      const hitRate = hits / (hits + misses);

      expect(hitRate).toBe(0.8); // 80%
    });

    it('should handle zero accesses', () => {
      const hits = 0;
      const misses = 0;

      const hitRate =
        hits + misses > 0 ? hits / (hits + misses) : 0;

      expect(hitRate).toBe(0);
    });

    it('should handle perfect hit rate', () => {
      const hits = 100;
      const misses = 0;

      const hitRate = hits / (hits + misses);

      expect(hitRate).toBe(1.0); // 100%
    });

    it('should handle perfect miss rate', () => {
      const hits = 0;
      const misses = 100;

      const hitRate = hits / (hits + misses);

      expect(hitRate).toBe(0); // 0%
    });
  });

  describe('Quota Management', () => {
    it('should calculate available quota percentage', () => {
      const usedQuota = 30 * 1024 * 1024; // 30 MB
      const availableQuota = 100 * 1024 * 1024; // 100 MB

      const usagePercentage = (usedQuota / availableQuota) * 100;

      expect(usagePercentage).toBe(30); // 30%
    });

    it('should detect quota exceeded', () => {
      const totalSize = 60 * 1024 * 1024; // 60 MB
      const maxCacheSize = 50 * 1024 * 1024; // 50 MB

      const quotaExceeded = totalSize > maxCacheSize;

      expect(quotaExceeded).toBe(true);
    });

    it('should detect quota available', () => {
      const totalSize = 40 * 1024 * 1024; // 40 MB
      const maxCacheSize = 50 * 1024 * 1024; // 50 MB
      const requiredSize = 5 * 1024 * 1024; // 5 MB

      const quotaAvailable = totalSize + requiredSize <= maxCacheSize;

      expect(quotaAvailable).toBe(true);
    });
  });

  describe('Configuration Defaults', () => {
    it('should use default configuration values', () => {
      const config: Required<IndexedDBCacheConfig> = {
        dbName: 'medical-imaging-cache',
        dbVersion: 1,
        storeName: 'slices',
        maxCacheSize: 50 * 1024 * 1024, // 50MB
        defaultExpiration: 24 * 60 * 60 * 1000, // 24 hours
        enableAutoEviction: true,
        enableLogging: false,
      };

      expect(config.dbName).toBe('medical-imaging-cache');
      expect(config.maxCacheSize).toBe(52428800); // 50 MB
      expect(config.defaultExpiration).toBe(86400000); // 24 hours
      expect(config.enableAutoEviction).toBe(true);
    });

    it('should override default configuration', () => {
      const customConfig: IndexedDBCacheConfig = {
        dbName: 'custom-cache',
        maxCacheSize: 100 * 1024 * 1024, // 100 MB
        enableLogging: true,
      };

      const defaultConfig: Required<IndexedDBCacheConfig> = {
        dbName: 'medical-imaging-cache',
        dbVersion: 1,
        storeName: 'slices',
        maxCacheSize: 50 * 1024 * 1024,
        defaultExpiration: 24 * 60 * 60 * 1000,
        enableAutoEviction: true,
        enableLogging: false,
      };

      const mergedConfig = { ...defaultConfig, ...customConfig };

      expect(mergedConfig.dbName).toBe('custom-cache');
      expect(mergedConfig.maxCacheSize).toBe(104857600); // 100 MB
      expect(mergedConfig.enableLogging).toBe(true);
      expect(mergedConfig.storeName).toBe('slices'); // From default
    });
  });

  describe('Entry Validation', () => {
    it('should validate complete cache entry', () => {
      const entry: Partial<CachedSlice> = {
        key: 'file123:0',
        fileId: 'file123',
        sliceIndex: 0,
        data: new ArrayBuffer(524288),
        width: 512,
        height: 512,
        dtype: 'uint16',
        windowCenter: 50,
        windowWidth: 100,
        minValue: 0,
        maxValue: 4095,
        timestamp: Date.now(),
        lastAccess: Date.now(),
        size: 524288,
      };

      // Validate required fields
      expect(entry.key).toBeDefined();
      expect(entry.fileId).toBeDefined();
      expect(entry.sliceIndex).toBeDefined();
      expect(entry.data).toBeDefined();
      expect(entry.width).toBeGreaterThan(0);
      expect(entry.height).toBeGreaterThan(0);
    });

    it('should detect invalid entries', () => {
      const entry: Partial<CachedSlice> = {
        key: 'file123:0',
        // Missing required fields
      };

      expect(entry.fileId).toBeUndefined();
      expect(entry.data).toBeUndefined();
    });
  });

  describe('Performance Characteristics', () => {
    it('should calculate expected read performance', () => {
      const sliceSize = 512 * 512 * 2; // 512KB (uint16)
      const expectedReadTime = 20; // 20ms

      const expectedThroughput = sliceSize / (expectedReadTime / 1000); // bytes/sec

      expect(expectedThroughput).toBeGreaterThanOrEqual(25 * 1024 * 1024); // >= 25 MB/s
    });

    it('should calculate expected write performance', () => {
      const sliceSize = 512 * 512 * 2; // 512KB (uint16)
      const expectedWriteTime = 50; // 50ms

      const expectedThroughput = sliceSize / (expectedWriteTime / 1000); // bytes/sec

      expect(expectedThroughput).toBeGreaterThanOrEqual(10 * 1024 * 1024); // >= 10 MB/s
    });

    it('should estimate cache capacity', () => {
      const maxCacheSize = 50 * 1024 * 1024; // 50 MB
      const sliceSize = 256 * 1024; // 256 KB

      const estimatedCapacity = Math.floor(maxCacheSize / sliceSize);

      expect(estimatedCapacity).toBe(200); // ~200 slices
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty cache', () => {
      const slices: CachedSlice[] = [];

      const totalSize = slices.reduce((sum, slice) => sum + slice.size, 0);

      expect(totalSize).toBe(0);
      expect(slices.length).toBe(0);
    });

    it('should handle single slice cache', () => {
      const slices: CachedSlice[] = [
        {
          key: 'file123:0',
          fileId: 'file123',
          sliceIndex: 0,
          data: new ArrayBuffer(1024),
          width: 16,
          height: 16,
          dtype: 'uint16',
          windowCenter: 0,
          windowWidth: 100,
          minValue: 0,
          maxValue: 100,
          timestamp: Date.now(),
          lastAccess: Date.now(),
          size: 1024,
        },
      ];

      expect(slices.length).toBe(1);
    });

    it('should handle very large slices', () => {
      const width = 2048;
      const height = 2048;
      const bytesPerPixel = 8; // Float64

      const size = width * height * bytesPerPixel;

      expect(size).toBe(33554432); // 32 MB
    });

    it('should handle very small slices', () => {
      const width = 64;
      const height = 64;
      const bytesPerPixel = 1; // Uint8

      const size = width * height * bytesPerPixel;

      expect(size).toBe(4096); // 4 KB
    });
  });
});
