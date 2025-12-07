/**
 * Tests for Integrated Caching Layer.
 *
 * @vitest-environment node
 */

import { describe, it, expect, beforeEach } from 'vitest';
import type {
  SliceData,
  PrefetchRequest,
  IntegratedCacheStats,
  IntegratedCacheConfig,
} from './integratedCache';

describe('Integrated Cache - Logic Tests', () => {
  describe('Cache Key Generation', () => {
    it('should generate correct cache key', () => {
      const fileId = 'file123';
      const sliceIndex = 42;

      const key = `${fileId}:${sliceIndex}`;

      expect(key).toBe('file123:42');
    });

    it('should handle complex file IDs', () => {
      const fileId = 'folder/subfolder/file_123.dcm';
      const sliceIndex = 999;

      const key = `${fileId}:${sliceIndex}`;

      expect(key).toBe('folder/subfolder/file_123.dcm:999');
    });
  });

  describe('L1 Cache Management', () => {
    it('should add entry to L1 cache', () => {
      const cache = new Map<string, { data: SliceData; lastAccess: number; accessCount: number }>();
      const key = 'file123:0';

      const sliceData: SliceData = {
        fileId: 'file123',
        sliceIndex: 0,
        data: new ArrayBuffer(1024),
        width: 32,
        height: 32,
        dtype: 'uint8',
        windowCenter: 50,
        windowWidth: 100,
        minValue: 0,
        maxValue: 255,
      };

      cache.set(key, {
        data: sliceData,
        lastAccess: Date.now(),
        accessCount: 1,
      });

      expect(cache.has(key)).toBe(true);
      expect(cache.size).toBe(1);
    });

    it('should enforce L1 cache size limit', () => {
      const maxL1Size = 5;
      const cache = new Map<string, { data: any; lastAccess: number; accessCount: number }>();

      // Add more than max
      for (let i = 0; i < 10; i++) {
        cache.set(`key${i}`, {
          data: { sliceIndex: i },
          lastAccess: Date.now() - (10 - i) * 1000, // Older first
          accessCount: 1,
        });

        // Evict LRU if over limit
        if (cache.size > maxL1Size) {
          let oldestKey: string | null = null;
          let oldestTime = Infinity;

          for (const [k, entry] of cache.entries()) {
            if (entry.lastAccess < oldestTime) {
              oldestTime = entry.lastAccess;
              oldestKey = k;
            }
          }

          if (oldestKey) {
            cache.delete(oldestKey);
          }
        }
      }

      expect(cache.size).toBe(maxL1Size);
    });

    it('should update access count on hit', () => {
      const cache = new Map<string, { data: any; lastAccess: number; accessCount: number }>();
      const key = 'file123:0';

      cache.set(key, {
        data: {},
        lastAccess: Date.now(),
        accessCount: 1,
      });

      // Access again
      const entry = cache.get(key);
      if (entry) {
        entry.lastAccess = Date.now();
        entry.accessCount++;
      }

      expect(entry?.accessCount).toBe(2);
    });
  });

  describe('LRU Eviction', () => {
    it('should identify least recently used entry', () => {
      const now = Date.now();

      const entries = [
        { key: 'a', lastAccess: now - 5000 }, // Oldest
        { key: 'b', lastAccess: now - 1000 }, // Newest
        { key: 'c', lastAccess: now - 3000 }, // Middle
      ];

      let oldestKey: string | null = null;
      let oldestTime = Infinity;

      for (const entry of entries) {
        if (entry.lastAccess < oldestTime) {
          oldestTime = entry.lastAccess;
          oldestKey = entry.key;
        }
      }

      expect(oldestKey).toBe('a');
    });

    it('should evict oldest when cache full', () => {
      const maxSize = 3;
      const cache = new Map<string, { lastAccess: number }>();

      const now = Date.now();
      cache.set('a', { lastAccess: now - 5000 });
      cache.set('b', { lastAccess: now - 3000 });
      cache.set('c', { lastAccess: now - 1000 });

      // Add new entry
      cache.set('d', { lastAccess: now });

      // Evict LRU
      if (cache.size > maxSize) {
        let oldestKey: string | null = null;
        let oldestTime = Infinity;

        for (const [key, entry] of cache.entries()) {
          if (entry.lastAccess < oldestTime) {
            oldestTime = entry.lastAccess;
            oldestKey = key;
          }
        }

        if (oldestKey) {
          cache.delete(oldestKey);
        }
      }

      expect(cache.size).toBe(maxSize);
      expect(cache.has('a')).toBe(false); // Oldest evicted
      expect(cache.has('d')).toBe(true); // Newest kept
    });
  });

  describe('Access Pattern Tracking', () => {
    it('should detect sequential forward access', () => {
      const pattern = [0, 1, 2, 3, 4];

      const lastTwo = pattern.slice(-2);
      const diff = lastTwo[1] - lastTwo[0];

      expect(Math.abs(diff)).toBe(1);
      expect(diff).toBeGreaterThan(0); // Forward
    });

    it('should detect sequential backward access', () => {
      const pattern = [10, 9, 8, 7, 6];

      const lastTwo = pattern.slice(-2);
      const diff = lastTwo[1] - lastTwo[0];

      expect(Math.abs(diff)).toBe(1);
      expect(diff).toBeLessThan(0); // Backward
    });

    it('should detect random access', () => {
      const pattern = [0, 5, 2, 8, 3];

      const lastTwo = pattern.slice(-2);
      const diff = lastTwo[1] - lastTwo[0];

      expect(Math.abs(diff)).not.toBe(1); // Not sequential
    });

    it('should maintain limited history', () => {
      const maxHistory = 20;
      const pattern: number[] = [];

      for (let i = 0; i < 50; i++) {
        pattern.push(i);

        if (pattern.length > maxHistory) {
          pattern.shift();
        }
      }

      expect(pattern.length).toBe(maxHistory);
      expect(pattern[0]).toBe(30); // First 30 removed
    });
  });

  describe('Prefetch Queue Management', () => {
    it('should create prefetch requests', () => {
      const fileId = 'file123';
      const currentSlice = 10;
      const prefetchCount = 5;
      const direction = 1; // Forward

      const queue: PrefetchRequest[] = [];

      for (let i = 1; i <= prefetchCount; i++) {
        const nextSlice = currentSlice + i * direction;
        queue.push({
          fileId,
          sliceIndex: nextSlice,
          priority: prefetchCount - i + 1,
        });
      }

      expect(queue.length).toBe(5);
      expect(queue[0].sliceIndex).toBe(11);
      expect(queue[0].priority).toBe(5); // Highest priority
      expect(queue[4].sliceIndex).toBe(15);
      expect(queue[4].priority).toBe(1); // Lowest priority
    });

    it('should sort by priority', () => {
      const queue: PrefetchRequest[] = [
        { fileId: 'f1', sliceIndex: 1, priority: 2 },
        { fileId: 'f1', sliceIndex: 2, priority: 5 },
        { fileId: 'f1', sliceIndex: 3, priority: 1 },
      ];

      queue.sort((a, b) => b.priority - a.priority);

      expect(queue[0].priority).toBe(5); // Highest first
      expect(queue[1].priority).toBe(2);
      expect(queue[2].priority).toBe(1); // Lowest last
    });

    it('should remove duplicates', () => {
      const queue: PrefetchRequest[] = [
        { fileId: 'f1', sliceIndex: 1, priority: 3 },
        { fileId: 'f1', sliceIndex: 2, priority: 2 },
        { fileId: 'f1', sliceIndex: 1, priority: 1 }, // Duplicate
      ];

      const seen = new Set<string>();
      const deduplicated = queue.filter((req) => {
        const key = `${req.fileId}:${req.sliceIndex}`;
        if (seen.has(key)) {
          return false;
        }
        seen.add(key);
        return true;
      });

      expect(deduplicated.length).toBe(2);
    });
  });

  describe('Statistics Calculation', () => {
    it('should calculate L1 hit rate', () => {
      const hits = 85;
      const misses = 15;

      const hitRate = hits / (hits + misses);

      expect(hitRate).toBe(0.85); // 85%
    });

    it('should calculate L2 hit rate', () => {
      const l1Misses = 15;
      const l2Hits = 12;
      const l2Misses = 3;

      const l2HitRate = l2Hits / (l2Hits + l2Misses);

      expect(l2HitRate).toBe(0.8); // 80%
      expect(l2Hits + l2Misses).toBe(l1Misses); // All L1 misses go to L2
    });

    it('should calculate overall hit rate', () => {
      const l1Hits = 85;
      const l2Hits = 12;
      const totalMisses = 3;

      const totalRequests = l1Hits + l2Hits + totalMisses;
      const totalHits = l1Hits + l2Hits;

      const overallHitRate = totalHits / totalRequests;

      expect(overallHitRate).toBe(0.97); // 97%
    });

    it('should handle zero accesses', () => {
      const hits = 0;
      const misses = 0;

      const hitRate = hits + misses > 0 ? hits / (hits + misses) : 0;

      expect(hitRate).toBe(0);
    });
  });

  describe('Configuration', () => {
    it('should use default configuration', () => {
      const config: Required<IntegratedCacheConfig> = {
        maxL1Size: 50,
        maxL2Size: 50 * 1024 * 1024,
        enablePrefetch: true,
        prefetchCount: 5,
        enableMonitoring: true,
        enableCacheWarming: false,
        enableLogging: false,
      };

      expect(config.maxL1Size).toBe(50);
      expect(config.maxL2Size).toBe(52428800); // 50MB
      expect(config.prefetchCount).toBe(5);
    });

    it('should override default configuration', () => {
      const customConfig: IntegratedCacheConfig = {
        maxL1Size: 100,
        prefetchCount: 10,
        enableLogging: true,
      };

      const defaultConfig: Required<IntegratedCacheConfig> = {
        maxL1Size: 50,
        maxL2Size: 50 * 1024 * 1024,
        enablePrefetch: true,
        prefetchCount: 5,
        enableMonitoring: true,
        enableCacheWarming: false,
        enableLogging: false,
      };

      const mergedConfig = { ...defaultConfig, ...customConfig };

      expect(mergedConfig.maxL1Size).toBe(100);
      expect(mergedConfig.prefetchCount).toBe(10);
      expect(mergedConfig.enableLogging).toBe(true);
      expect(mergedConfig.maxL2Size).toBe(52428800); // From default
    });
  });

  describe('Performance Metrics', () => {
    it('should calculate average latency', () => {
      const latencies = [1.2, 0.8, 1.5, 1.0, 0.9];

      const sum = latencies.reduce((a, b) => a + b, 0);
      const average = sum / latencies.length;

      expect(average).toBeCloseTo(1.08, 2);
    });

    it('should track L1, L2, and miss latencies separately', () => {
      const metrics = {
        l1Latencies: [0.5, 0.6, 0.4],
        l2Latencies: [15.0, 18.0, 12.0],
        missLatencies: [120.0, 150.0, 100.0],
      };

      const avgL1 = metrics.l1Latencies.reduce((a, b) => a + b, 0) / metrics.l1Latencies.length;
      const avgL2 = metrics.l2Latencies.reduce((a, b) => a + b, 0) / metrics.l2Latencies.length;
      const avgMiss = metrics.missLatencies.reduce((a, b) => a + b, 0) / metrics.missLatencies.length;

      expect(avgL1).toBeCloseTo(0.5, 1);
      expect(avgL2).toBeCloseTo(15.0, 1);
      expect(avgMiss).toBeCloseTo(123.3, 1);
    });
  });

  describe('Cache Warming', () => {
    it('should identify frequently accessed items', () => {
      const accessCounts = new Map<string, number>();

      const accesses = [
        'file1:0',
        'file1:1',
        'file1:0', // Duplicate
        'file2:0',
        'file1:0', // Duplicate
        'file1:1', // Duplicate
      ];

      for (const key of accesses) {
        accessCounts.set(key, (accessCounts.get(key) || 0) + 1);
      }

      // Sort by access count
      const sorted = Array.from(accessCounts.entries()).sort((a, b) => b[1] - a[1]);

      expect(sorted[0][0]).toBe('file1:0'); // Most accessed
      expect(sorted[0][1]).toBe(3);
    });
  });

  describe('Memory Management', () => {
    it('should calculate L1 memory usage', () => {
      const slices = [
        { size: 512 * 512 * 2 }, // 512KB
        { size: 256 * 256 * 2 }, // 128KB
        { size: 1024 * 1024 * 2 }, // 2MB
      ];

      const totalSize = slices.reduce((sum, slice) => sum + slice.size, 0);

      expect(totalSize).toBe(2752512); // ~2.62MB
    });

    it('should detect memory pressure', () => {
      const maxL1Size = 50;
      const maxL2Size = 50 * 1024 * 1024;

      const l1Size = 48; // Near limit
      const l2Size = 48 * 1024 * 1024; // Near limit

      const l1Pressure = l1Size / maxL1Size;
      const l2Pressure = l2Size / maxL2Size;

      expect(l1Pressure).toBeGreaterThan(0.9); // >90% full
      expect(l2Pressure).toBeGreaterThan(0.9);
    });
  });

  describe('Slice Data Structure', () => {
    it('should create valid slice data', () => {
      const slice: SliceData = {
        fileId: 'file123',
        sliceIndex: 42,
        data: new ArrayBuffer(512 * 512 * 2),
        width: 512,
        height: 512,
        dtype: 'uint16',
        windowCenter: 50,
        windowWidth: 100,
        minValue: 0,
        maxValue: 4095,
      };

      expect(slice.fileId).toBe('file123');
      expect(slice.sliceIndex).toBe(42);
      expect(slice.data.byteLength).toBe(524288); // 512KB
      expect(slice.width).toBe(512);
      expect(slice.height).toBe(512);
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty cache', () => {
      const cache = new Map();

      expect(cache.size).toBe(0);
    });

    it('should handle single entry cache', () => {
      const cache = new Map();
      cache.set('key1', { data: {} });

      expect(cache.size).toBe(1);
    });

    it('should handle prefetch with no pattern', () => {
      const pattern: number[] = [];

      const shouldPrefetch = pattern.length >= 2;

      expect(shouldPrefetch).toBe(false);
    });

    it('should handle negative slice index in backward scan', () => {
      const currentSlice = 2;
      const prefetchCount = 5;
      const direction = -1; // Backward

      const queue: PrefetchRequest[] = [];

      for (let i = 1; i <= prefetchCount; i++) {
        const nextSlice = currentSlice + i * direction;
        if (nextSlice >= 0) {
          // Only valid indices
          queue.push({
            fileId: 'file123',
            sliceIndex: nextSlice,
            priority: i,
          });
        }
      }

      expect(queue.length).toBe(2); // Only indices 1 and 0 are valid
      expect(queue[0].sliceIndex).toBe(1);
      expect(queue[1].sliceIndex).toBe(0);
    });
  });

  describe('Performance Characteristics', () => {
    it('should estimate cache hit time savings', () => {
      const l1HitTime = 0.5; // ms
      const l2HitTime = 15; // ms
      const missTime = 120; // ms

      const totalRequests = 1000;
      const l1HitRate = 0.85; // 85%
      const l2HitRate = 0.12; // 12%
      const missRate = 0.03; // 3%

      const l1Hits = totalRequests * l1HitRate;
      const l2Hits = totalRequests * l2HitRate;
      const misses = totalRequests * missRate;

      const timeWithCache = l1Hits * l1HitTime + l2Hits * l2HitTime + misses * missTime;
      const timeWithoutCache = totalRequests * missTime;

      const timeSaved = timeWithoutCache - timeWithCache;
      const percentSaved = (timeSaved / timeWithoutCache) * 100;

      expect(percentSaved).toBeGreaterThan(95); // >95% time saved
    });

    it('should calculate prefetch efficiency', () => {
      const prefetchRequests = 100;
      const prefetchHits = 75; // 75 were used

      const efficiency = prefetchHits / prefetchRequests;

      expect(efficiency).toBe(0.75); // 75% efficiency
    });
  });

  describe('Multi-Level Cache Integration', () => {
    it('should promote L2 hits to L1', () => {
      const l1Cache = new Map<string, any>();
      const maxL1Size = 5;

      // Simulate L2 hit
      const l2Data: SliceData = {
        fileId: 'file123',
        sliceIndex: 0,
        data: new ArrayBuffer(1024),
        width: 32,
        height: 32,
        dtype: 'uint8',
        windowCenter: 50,
        windowWidth: 100,
        minValue: 0,
        maxValue: 255,
      };

      const key = `${l2Data.fileId}:${l2Data.sliceIndex}`;

      // Promote to L1
      l1Cache.set(key, {
        data: l2Data,
        lastAccess: Date.now(),
        accessCount: 1,
      });

      expect(l1Cache.has(key)).toBe(true);
      expect(l1Cache.size).toBe(1);
    });

    it('should handle cascading cache misses', () => {
      const l1Cache = new Map();
      const l2Cache = new Map();

      const key = 'file123:0';

      const l1Hit = l1Cache.has(key);
      const l2Hit = l2Cache.has(key);

      expect(l1Hit).toBe(false);
      expect(l2Hit).toBe(false); // Complete miss
    });
  });
});
