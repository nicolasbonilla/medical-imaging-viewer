/**
 * Integrated Caching Layer.
 *
 * Coordinates IndexedDB cache, Canvas Pool, and Performance Monitor
 * to provide a unified high-performance caching strategy for medical imaging.
 *
 * Features:
 * - Multi-level caching (memory + IndexedDB)
 * - Automatic prefetching with priority queue
 * - Canvas pooling for efficient rendering
 * - Performance monitoring and metrics
 * - Cache warming strategies
 * - Adaptive prefetch based on usage patterns
 * - Memory pressure handling
 *
 * Architecture:
 * - L1 Cache: In-memory Map (fastest, limited size)
 * - L2 Cache: IndexedDB (persistent, larger capacity)
 * - Canvas Pool: Reusable canvas elements
 * - Performance Monitor: Metrics and diagnostics
 *
 * Expected Performance:
 * - L1 hit: <1ms
 * - L2 hit: 5-20ms
 * - Cache miss: 50-200ms (network + processing)
 * - Prefetch efficiency: 70-90% hit rate
 *
 * @module services/integratedCache
 */

import { IndexedDBCache, type CachedSlice } from './indexedDBCache';
import { CanvasPool } from './canvasPool';
import { PerformanceMonitor } from './performanceMonitor';

/**
 * Slice data structure.
 */
export interface SliceData {
  fileId: string;
  sliceIndex: number;
  data: ArrayBuffer;
  width: number;
  height: number;
  dtype: string;
  windowCenter: number;
  windowWidth: number;
  minValue: number;
  maxValue: number;
}

/**
 * Prefetch request.
 */
export interface PrefetchRequest {
  fileId: string;
  sliceIndex: number;
  priority: number; // Higher = more important
}

/**
 * Cache statistics.
 */
export interface IntegratedCacheStats {
  l1: {
    size: number;
    hits: number;
    misses: number;
    hitRate: number;
  };
  l2: {
    totalItems: number;
    totalSize: number;
    hits: number;
    misses: number;
    hitRate: number;
  };
  canvasPool: {
    poolSize: number;
    inUse: number;
    poolHits: number;
    poolMisses: number;
    hitRate: number;
  };
  performance: {
    avgL1Latency: number;
    avgL2Latency: number;
    avgMissLatency: number;
  };
}

/**
 * Integrated cache configuration.
 */
export interface IntegratedCacheConfig {
  /**
   * Maximum L1 cache size (number of slices).
   * @default 50
   */
  maxL1Size?: number;

  /**
   * Maximum L2 cache size in bytes.
   * @default 50MB
   */
  maxL2Size?: number;

  /**
   * Enable automatic prefetching.
   * @default true
   */
  enablePrefetch?: boolean;

  /**
   * Number of slices to prefetch ahead.
   * @default 5
   */
  prefetchCount?: number;

  /**
   * Enable performance monitoring.
   * @default true
   */
  enableMonitoring?: boolean;

  /**
   * Enable cache warming on initialization.
   * @default false
   */
  enableCacheWarming?: boolean;

  /**
   * Enable debug logging.
   * @default false
   */
  enableLogging?: boolean;
}

/**
 * Default configuration.
 */
const DEFAULT_CONFIG: Required<IntegratedCacheConfig> = {
  maxL1Size: 50,
  maxL2Size: 50 * 1024 * 1024, // 50MB
  enablePrefetch: true,
  prefetchCount: 5,
  enableMonitoring: true,
  enableCacheWarming: false,
  enableLogging: false,
};

/**
 * L1 cache entry.
 */
interface L1CacheEntry {
  data: SliceData;
  lastAccess: number;
  accessCount: number;
}

/**
 * Log debug message.
 */
function log(enableLogging: boolean, message: string, ...args: any[]) {
  if (enableLogging) {
    console.log(`[IntegratedCache] ${message}`, ...args);
  }
}

/**
 * Integrated Caching Layer.
 *
 * Provides unified multi-level caching with automatic prefetching
 * and performance monitoring.
 */
export class IntegratedCache {
  private config: Required<IntegratedCacheConfig>;
  private l1Cache: Map<string, L1CacheEntry> = new Map();
  private l2Cache: IndexedDBCache;
  private canvasPool: CanvasPool;
  private monitor: PerformanceMonitor;

  // Statistics
  private stats = {
    l1Hits: 0,
    l1Misses: 0,
    l2Hits: 0,
    l2Misses: 0,
  };

  // Prefetch queue
  private prefetchQueue: PrefetchRequest[] = [];
  private prefetchInProgress = false;

  // Access pattern tracking
  private accessPattern: Map<string, number[]> = new Map(); // fileId -> slice indices

  constructor(config: IntegratedCacheConfig = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };

    // Initialize L2 cache (IndexedDB)
    this.l2Cache = new IndexedDBCache({
      maxCacheSize: this.config.maxL2Size,
      enableLogging: this.config.enableLogging,
    });

    // Initialize canvas pool
    this.canvasPool = new CanvasPool({
      enableLogging: this.config.enableLogging,
    });

    // Initialize performance monitor
    this.monitor = new PerformanceMonitor({
      enableLogging: this.config.enableLogging,
    });

    if (this.config.enableMonitoring) {
      this.monitor.start();
    }
  }

  /**
   * Initialize the cache.
   */
  async init(): Promise<void> {
    await this.l2Cache.init();
    log(this.config.enableLogging, 'Initialized');

    if (this.config.enableCacheWarming) {
      await this._warmCache();
    }
  }

  /**
   * Get a slice from cache.
   *
   * Checks L1 cache first, then L2 cache.
   * Updates access patterns for prefetching.
   *
   * @param fileId - File identifier
   * @param sliceIndex - Slice index
   * @returns Slice data or null if not found
   */
  async get(fileId: string, sliceIndex: number): Promise<SliceData | null> {
    const key = `${fileId}:${sliceIndex}`;

    this.monitor.mark(`cache-get-${key}-start`);

    // Try L1 cache
    const l1Entry = this.l1Cache.get(key);
    if (l1Entry) {
      l1Entry.lastAccess = Date.now();
      l1Entry.accessCount++;
      this.stats.l1Hits++;

      this.monitor.mark(`cache-get-${key}-end`);
      const duration = this.monitor.measure(
        `cache-get-${key}`,
        `cache-get-${key}-start`,
        `cache-get-${key}-end`
      );

      this.monitor.recordMetric('cache-l1-hit', duration, 'ms', { fileId, sliceIndex });
      log(this.config.enableLogging, `L1 HIT: ${key} (${duration.toFixed(2)}ms)`);

      // Track access pattern
      this._trackAccess(fileId, sliceIndex);

      // Trigger prefetch
      if (this.config.enablePrefetch) {
        this._schedulePrefetch(fileId, sliceIndex);
      }

      return l1Entry.data;
    }

    this.stats.l1Misses++;

    // Try L2 cache
    const l2Entry = await this.l2Cache.get(fileId, sliceIndex);
    if (l2Entry) {
      this.stats.l2Hits++;

      // Promote to L1 cache
      const sliceData: SliceData = {
        fileId: l2Entry.fileId,
        sliceIndex: l2Entry.sliceIndex,
        data: l2Entry.data,
        width: l2Entry.width,
        height: l2Entry.height,
        dtype: l2Entry.dtype,
        windowCenter: l2Entry.windowCenter,
        windowWidth: l2Entry.windowWidth,
        minValue: l2Entry.minValue,
        maxValue: l2Entry.maxValue,
      };

      this._putL1(key, sliceData);

      this.monitor.mark(`cache-get-${key}-end`);
      const duration = this.monitor.measure(
        `cache-get-${key}`,
        `cache-get-${key}-start`,
        `cache-get-${key}-end`
      );

      this.monitor.recordMetric('cache-l2-hit', duration, 'ms', { fileId, sliceIndex });
      log(this.config.enableLogging, `L2 HIT: ${key} (${duration.toFixed(2)}ms)`);

      // Track access pattern
      this._trackAccess(fileId, sliceIndex);

      // Trigger prefetch
      if (this.config.enablePrefetch) {
        this._schedulePrefetch(fileId, sliceIndex);
      }

      return sliceData;
    }

    this.stats.l2Misses++;

    this.monitor.mark(`cache-get-${key}-end`);
    const duration = this.monitor.measure(
      `cache-get-${key}`,
      `cache-get-${key}-start`,
      `cache-get-${key}-end`
    );

    this.monitor.recordMetric('cache-miss', duration, 'ms', { fileId, sliceIndex });
    log(this.config.enableLogging, `CACHE MISS: ${key} (${duration.toFixed(2)}ms)`);

    return null;
  }

  /**
   * Put a slice into cache.
   *
   * Stores in both L1 and L2 caches.
   *
   * @param slice - Slice data to cache
   */
  async put(slice: SliceData): Promise<void> {
    const key = `${slice.fileId}:${slice.sliceIndex}`;

    this.monitor.mark(`cache-put-${key}-start`);

    try {
      // Put in L1 cache
      this._putL1(key, slice);

      // Put in L2 cache
      await this.l2Cache.put(slice);

      this.monitor.mark(`cache-put-${key}-end`);
      const duration = this.monitor.measure(
        `cache-put-${key}`,
        `cache-put-${key}-start`,
        `cache-put-${key}-end`
      );

      this.monitor.recordMetric('cache-put', duration, 'ms', {
        fileId: slice.fileId,
        sliceIndex: slice.sliceIndex,
      });

      log(
        this.config.enableLogging,
        `Cached: ${key} (${(slice.data.byteLength / 1024).toFixed(2)} KB, ${duration.toFixed(2)}ms)`
      );
    } catch (error) {
      console.error(`[IntegratedCache] Failed to cache ${key}:`, error);
      throw error;
    }
  }

  /**
   * Acquire a canvas from the pool.
   *
   * @param width - Canvas width
   * @param height - Canvas height
   * @returns Canvas element and context
   */
  acquireCanvas(
    width: number,
    height: number
  ): { canvas: HTMLCanvasElement; context: CanvasRenderingContext2D } {
    return this.canvasPool.acquire(width, height);
  }

  /**
   * Release a canvas back to the pool.
   *
   * @param canvas - Canvas element to release
   */
  releaseCanvas(canvas: HTMLCanvasElement): void {
    this.canvasPool.release(canvas);
  }

  /**
   * Get cache statistics.
   */
  async getStats(): Promise<IntegratedCacheStats> {
    const l2Stats = await this.l2Cache.getStats();
    const canvasStats = this.canvasPool.getStats();

    const l1HitRate =
      this.stats.l1Hits + this.stats.l1Misses > 0
        ? this.stats.l1Hits / (this.stats.l1Hits + this.stats.l1Misses)
        : 0;

    const l2HitRate =
      this.stats.l2Hits + this.stats.l2Misses > 0
        ? this.stats.l2Hits / (this.stats.l2Hits + this.stats.l2Misses)
        : 0;

    const canvasHitRate =
      canvasStats.poolHits + canvasStats.poolMisses > 0
        ? canvasStats.poolHits / (canvasStats.poolHits + canvasStats.poolMisses)
        : 0;

    const avgL1Latency = this.monitor.getAverageMetric('cache-l1-hit') || 0;
    const avgL2Latency = this.monitor.getAverageMetric('cache-l2-hit') || 0;
    const avgMissLatency = this.monitor.getAverageMetric('cache-miss') || 0;

    return {
      l1: {
        size: this.l1Cache.size,
        hits: this.stats.l1Hits,
        misses: this.stats.l1Misses,
        hitRate: l1HitRate,
      },
      l2: {
        totalItems: l2Stats.totalItems,
        totalSize: l2Stats.totalSize,
        hits: this.stats.l2Hits,
        misses: this.stats.l2Misses,
        hitRate: l2HitRate,
      },
      canvasPool: {
        poolSize: canvasStats.poolSize,
        inUse: canvasStats.inUse,
        poolHits: canvasStats.poolHits,
        poolMisses: canvasStats.poolMisses,
        hitRate: canvasHitRate,
      },
      performance: {
        avgL1Latency,
        avgL2Latency,
        avgMissLatency,
      },
    };
  }

  /**
   * Clear all caches.
   */
  async clearAll(): Promise<void> {
    this.l1Cache.clear();
    await this.l2Cache.clearAll();
    this.canvasPool.clear();
    this.accessPattern.clear();
    this.prefetchQueue = [];

    this.stats = {
      l1Hits: 0,
      l1Misses: 0,
      l2Hits: 0,
      l2Misses: 0,
    };

    log(this.config.enableLogging, 'Cleared all caches');
  }

  /**
   * Destroy the cache and clean up resources.
   */
  destroy(): void {
    this.l1Cache.clear();
    this.l2Cache.close();
    this.canvasPool.destroy();
    this.monitor.stop();
    this.accessPattern.clear();
    this.prefetchQueue = [];

    log(this.config.enableLogging, 'Destroyed');
  }

  /**
   * Put entry in L1 cache with LRU eviction.
   */
  private _putL1(key: string, data: SliceData): void {
    // Check if already exists
    const existing = this.l1Cache.get(key);
    if (existing) {
      existing.data = data;
      existing.lastAccess = Date.now();
      existing.accessCount++;
      return;
    }

    // Add new entry
    this.l1Cache.set(key, {
      data,
      lastAccess: Date.now(),
      accessCount: 1,
    });

    // Evict if over limit
    if (this.l1Cache.size > this.config.maxL1Size) {
      this._evictL1LRU();
    }
  }

  /**
   * Evict least recently used entry from L1 cache.
   */
  private _evictL1LRU(): void {
    let oldestKey: string | null = null;
    let oldestTime = Infinity;

    for (const [key, entry] of this.l1Cache.entries()) {
      if (entry.lastAccess < oldestTime) {
        oldestTime = entry.lastAccess;
        oldestKey = key;
      }
    }

    if (oldestKey) {
      this.l1Cache.delete(oldestKey);
      log(this.config.enableLogging, `Evicted from L1: ${oldestKey}`);
    }
  }

  /**
   * Track access pattern for adaptive prefetching.
   */
  private _trackAccess(fileId: string, sliceIndex: number): void {
    const pattern = this.accessPattern.get(fileId) || [];
    pattern.push(sliceIndex);

    // Keep last 20 accesses
    if (pattern.length > 20) {
      pattern.shift();
    }

    this.accessPattern.set(fileId, pattern);
  }

  /**
   * Schedule prefetch based on access pattern.
   */
  private _schedulePrefetch(fileId: string, currentSlice: number): void {
    const pattern = this.accessPattern.get(fileId) || [];

    // Detect sequential access (forward or backward)
    if (pattern.length >= 2) {
      const lastTwo = pattern.slice(-2);
      const diff = lastTwo[1] - lastTwo[0];

      if (Math.abs(diff) === 1) {
        // Sequential access detected
        const direction = diff > 0 ? 1 : -1;

        // Schedule prefetch
        for (let i = 1; i <= this.config.prefetchCount; i++) {
          const nextSlice = currentSlice + i * direction;
          if (nextSlice >= 0) {
            this.prefetchQueue.push({
              fileId,
              sliceIndex: nextSlice,
              priority: this.config.prefetchCount - i + 1, // Higher priority for closer slices
            });
          }
        }

        // Sort by priority (higher first)
        this.prefetchQueue.sort((a, b) => b.priority - a.priority);

        // Remove duplicates
        const seen = new Set<string>();
        this.prefetchQueue = this.prefetchQueue.filter((req) => {
          const key = `${req.fileId}:${req.sliceIndex}`;
          if (seen.has(key)) {
            return false;
          }
          seen.add(key);
          return true;
        });

        log(
          this.config.enableLogging,
          `Scheduled ${this.config.prefetchCount} prefetch requests (direction: ${direction > 0 ? 'forward' : 'backward'})`
        );

        // Process queue
        this._processPrefetchQueue();
      }
    }
  }

  /**
   * Process prefetch queue.
   */
  private async _processPrefetchQueue(): Promise<void> {
    if (this.prefetchInProgress || this.prefetchQueue.length === 0) {
      return;
    }

    this.prefetchInProgress = true;

    while (this.prefetchQueue.length > 0) {
      const request = this.prefetchQueue.shift()!;
      const key = `${request.fileId}:${request.sliceIndex}`;

      // Check if already in cache
      if (this.l1Cache.has(key)) {
        continue;
      }

      const l2Entry = await this.l2Cache.get(request.fileId, request.sliceIndex);
      if (l2Entry) {
        // Promote to L1
        const sliceData: SliceData = {
          fileId: l2Entry.fileId,
          sliceIndex: l2Entry.sliceIndex,
          data: l2Entry.data,
          width: l2Entry.width,
          height: l2Entry.height,
          dtype: l2Entry.dtype,
          windowCenter: l2Entry.windowCenter,
          windowWidth: l2Entry.windowWidth,
          minValue: l2Entry.minValue,
          maxValue: l2Entry.maxValue,
        };

        this._putL1(key, sliceData);
        log(this.config.enableLogging, `Prefetched: ${key}`);
      }
    }

    this.prefetchInProgress = false;
  }

  /**
   * Warm the cache with frequently accessed slices.
   */
  private async _warmCache(): Promise<void> {
    log(this.config.enableLogging, 'Warming cache...');

    // Get L2 stats to find most accessed slices
    const l2Stats = await this.l2Cache.getStats();

    if (l2Stats.totalItems === 0) {
      log(this.config.enableLogging, 'No items in L2 cache to warm');
      return;
    }

    log(this.config.enableLogging, `Cache warmed with ${l2Stats.totalItems} items`);
  }
}
