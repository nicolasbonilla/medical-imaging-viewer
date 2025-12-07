/**
 * Performance Monitoring Service.
 *
 * Provides comprehensive performance tracking and analytics for the
 * medical imaging viewer application.
 *
 * Features:
 * - Real-time metric collection
 * - Performance marks and measures
 * - Resource timing analysis
 * - FPS tracking
 * - Memory usage monitoring
 * - Network performance tracking
 * - Custom metric registration
 * - Performance reports and insights
 *
 * Expected Usage:
 * - Track slice loading time
 * - Monitor rendering performance
 * - Analyze cache hit rates
 * - Detect performance regressions
 *
 * @module services/performanceMonitor
 */

/**
 * Performance metric entry.
 */
export interface PerformanceMetric {
  /**
   * Metric name.
   */
  name: string;

  /**
   * Metric value.
   */
  value: number;

  /**
   * Metric unit (ms, bytes, fps, etc.).
   */
  unit: string;

  /**
   * Timestamp when measured.
   */
  timestamp: number;

  /**
   * Optional metadata.
   */
  metadata?: Record<string, any>;
}

/**
 * Performance measurement.
 */
export interface PerformanceMeasurement {
  /**
   * Measurement name.
   */
  name: string;

  /**
   * Start mark name.
   */
  startMark: string;

  /**
   * End mark name.
   */
  endMark: string;

  /**
   * Duration in milliseconds.
   */
  duration: number;

  /**
   * Timestamp.
   */
  timestamp: number;
}

/**
 * FPS statistics.
 */
export interface FPSStats {
  /**
   * Current FPS.
   */
  current: number;

  /**
   * Average FPS.
   */
  average: number;

  /**
   * Minimum FPS.
   */
  min: number;

  /**
   * Maximum FPS.
   */
  max: number;

  /**
   * Number of samples.
   */
  samples: number;
}

/**
 * Memory statistics.
 */
export interface MemoryStats {
  /**
   * Used JS heap size (bytes).
   */
  usedJSHeapSize: number;

  /**
   * Total JS heap size (bytes).
   */
  totalJSHeapSize: number;

  /**
   * JS heap size limit (bytes).
   */
  jsHeapSizeLimit: number;

  /**
   * Memory usage percentage.
   */
  usagePercent: number;
}

/**
 * Performance summary.
 */
export interface PerformanceSummary {
  /**
   * All collected metrics.
   */
  metrics: PerformanceMetric[];

  /**
   * All measurements.
   */
  measurements: PerformanceMeasurement[];

  /**
   * FPS statistics.
   */
  fps: FPSStats | null;

  /**
   * Memory statistics.
   */
  memory: MemoryStats | null;

  /**
   * Time range.
   */
  timeRange: {
    start: number;
    end: number;
    duration: number;
  };
}

/**
 * Performance monitor configuration.
 */
export interface PerformanceMonitorConfig {
  /**
   * Enable automatic FPS tracking.
   * @default false
   */
  enableFPSTracking?: boolean;

  /**
   * FPS tracking interval (milliseconds).
   * @default 1000
   */
  fpsInterval?: number;

  /**
   * Enable automatic memory tracking.
   * @default false
   */
  enableMemoryTracking?: boolean;

  /**
   * Memory tracking interval (milliseconds).
   * @default 5000
   */
  memoryInterval?: number;

  /**
   * Maximum number of metrics to store.
   * @default 1000
   */
  maxMetrics?: number;

  /**
   * Maximum number of measurements to store.
   * @default 1000
   */
  maxMeasurements?: number;

  /**
   * Enable console logging.
   * @default false
   */
  enableLogging?: boolean;
}

/**
 * Default configuration.
 */
const DEFAULT_CONFIG: Required<PerformanceMonitorConfig> = {
  enableFPSTracking: false,
  fpsInterval: 1000,
  enableMemoryTracking: false,
  memoryInterval: 5000,
  maxMetrics: 1000,
  maxMeasurements: 1000,
  enableLogging: false,
};

/**
 * Log debug message.
 */
function log(enableLogging: boolean, message: string, ...args: any[]) {
  if (enableLogging) {
    console.log(`[PerformanceMonitor] ${message}`, ...args);
  }
}

/**
 * Performance Monitor Service.
 *
 * Tracks and analyzes application performance metrics.
 *
 * @example
 * ```typescript
 * const monitor = new PerformanceMonitor({
 *   enableFPSTracking: true,
 *   enableMemoryTracking: true,
 * });
 *
 * monitor.start();
 *
 * // Mark start of operation
 * monitor.mark('slice-load-start');
 *
 * // ... load slice ...
 *
 * // Mark end and measure duration
 * monitor.mark('slice-load-end');
 * monitor.measure('slice-load', 'slice-load-start', 'slice-load-end');
 *
 * // Record custom metric
 * monitor.recordMetric('cache-hit-rate', 0.95, 'percent');
 *
 * // Get summary
 * const summary = monitor.getSummary();
 * console.log('Average FPS:', summary.fps?.average);
 * ```
 */
export class PerformanceMonitor {
  private config: Required<PerformanceMonitorConfig>;
  private metrics: PerformanceMetric[] = [];
  private measurements: PerformanceMeasurement[] = [];
  private marks: Map<string, number> = new Map();

  // FPS tracking
  private fpsTimer: number | null = null;
  private fpsFrames: number[] = [];
  private fpsLastTime: number = 0;
  private fpsFrameCount: number = 0;

  // Memory tracking
  private memoryTimer: number | null = null;
  private memorySnapshots: MemoryStats[] = [];

  // Session info
  private startTime: number = 0;
  private isRunning: boolean = false;

  constructor(config: PerformanceMonitorConfig = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Start performance monitoring.
   */
  start(): void {
    if (this.isRunning) {
      log(this.config.enableLogging, 'Already running');
      return;
    }

    this.isRunning = true;
    this.startTime = performance.now();

    // Start FPS tracking
    if (this.config.enableFPSTracking) {
      this._startFPSTracking();
    }

    // Start memory tracking
    if (this.config.enableMemoryTracking) {
      this._startMemoryTracking();
    }

    log(this.config.enableLogging, 'Performance monitoring started');
  }

  /**
   * Stop performance monitoring.
   */
  stop(): void {
    if (!this.isRunning) {
      return;
    }

    this.isRunning = false;

    // Stop FPS tracking
    if (this.fpsTimer !== null) {
      cancelAnimationFrame(this.fpsTimer);
      this.fpsTimer = null;
    }

    // Stop memory tracking
    if (this.memoryTimer !== null) {
      clearInterval(this.memoryTimer);
      this.memoryTimer = null;
    }

    log(this.config.enableLogging, 'Performance monitoring stopped');
  }

  /**
   * Create a performance mark.
   *
   * @param name - Mark name
   */
  mark(name: string): void {
    const timestamp = performance.now();
    this.marks.set(name, timestamp);

    // Also use native Performance API if available
    if (typeof performance !== 'undefined' && performance.mark) {
      performance.mark(name);
    }

    log(this.config.enableLogging, `Mark: ${name} at ${timestamp.toFixed(2)}ms`);
  }

  /**
   * Create a performance measure between two marks.
   *
   * @param name - Measurement name
   * @param startMark - Start mark name
   * @param endMark - End mark name
   * @returns Duration in milliseconds
   */
  measure(name: string, startMark: string, endMark: string): number {
    const startTime = this.marks.get(startMark);
    const endTime = this.marks.get(endMark);

    if (startTime === undefined || endTime === undefined) {
      log(this.config.enableLogging, `Missing marks for measurement: ${name}`);
      return 0;
    }

    const duration = endTime - startTime;

    const measurement: PerformanceMeasurement = {
      name,
      startMark,
      endMark,
      duration,
      timestamp: performance.now(),
    };

    this.measurements.push(measurement);

    // Enforce max measurements limit
    if (this.measurements.length > this.config.maxMeasurements) {
      this.measurements.shift();
    }

    // Also use native Performance API if available
    if (typeof performance !== 'undefined' && performance.measure) {
      try {
        performance.measure(name, startMark, endMark);
      } catch (e) {
        // Marks may not exist in native API
      }
    }

    log(
      this.config.enableLogging,
      `Measure: ${name} = ${duration.toFixed(2)}ms`
    );

    return duration;
  }

  /**
   * Record a custom metric.
   *
   * @param name - Metric name
   * @param value - Metric value
   * @param unit - Metric unit
   * @param metadata - Optional metadata
   */
  recordMetric(
    name: string,
    value: number,
    unit: string,
    metadata?: Record<string, any>
  ): void {
    const metric: PerformanceMetric = {
      name,
      value,
      unit,
      timestamp: performance.now(),
      metadata,
    };

    this.metrics.push(metric);

    // Enforce max metrics limit
    if (this.metrics.length > this.config.maxMetrics) {
      this.metrics.shift();
    }

    log(
      this.config.enableLogging,
      `Metric: ${name} = ${value} ${unit}`,
      metadata
    );
  }

  /**
   * Get performance summary.
   */
  getSummary(): PerformanceSummary {
    const now = performance.now();

    return {
      metrics: [...this.metrics],
      measurements: [...this.measurements],
      fps: this._getFPSStats(),
      memory: this._getMemoryStats(),
      timeRange: {
        start: this.startTime,
        end: now,
        duration: now - this.startTime,
      },
    };
  }

  /**
   * Get metrics by name.
   *
   * @param name - Metric name
   * @returns Array of matching metrics
   */
  getMetricsByName(name: string): PerformanceMetric[] {
    return this.metrics.filter((m) => m.name === name);
  }

  /**
   * Get measurements by name.
   *
   * @param name - Measurement name
   * @returns Array of matching measurements
   */
  getMeasurementsByName(name: string): PerformanceMeasurement[] {
    return this.measurements.filter((m) => m.name === name);
  }

  /**
   * Calculate average for a metric.
   *
   * @param name - Metric name
   * @returns Average value or null
   */
  getAverageMetric(name: string): number | null {
    const values = this.metrics.filter((m) => m.name === name).map((m) => m.value);

    if (values.length === 0) {
      return null;
    }

    const sum = values.reduce((a, b) => a + b, 0);
    return sum / values.length;
  }

  /**
   * Calculate average for a measurement.
   *
   * @param name - Measurement name
   * @returns Average duration or null
   */
  getAverageMeasurement(name: string): number | null {
    const durations = this.measurements
      .filter((m) => m.name === name)
      .map((m) => m.duration);

    if (durations.length === 0) {
      return null;
    }

    const sum = durations.reduce((a, b) => a + b, 0);
    return sum / durations.length;
  }

  /**
   * Clear all collected data.
   */
  clear(): void {
    this.metrics = [];
    this.measurements = [];
    this.marks.clear();
    this.fpsFrames = [];
    this.memorySnapshots = [];

    log(this.config.enableLogging, 'Performance data cleared');
  }

  /**
   * Export performance data as JSON.
   */
  export(): string {
    const summary = this.getSummary();
    return JSON.stringify(summary, null, 2);
  }

  /**
   * Start FPS tracking.
   */
  private _startFPSTracking(): void {
    this.fpsLastTime = performance.now();
    this.fpsFrameCount = 0;

    const trackFrame = () => {
      if (!this.isRunning) {
        return;
      }

      const now = performance.now();
      const delta = now - this.fpsLastTime;

      this.fpsFrameCount++;

      if (delta >= this.config.fpsInterval) {
        const fps = (this.fpsFrameCount * 1000) / delta;
        this.fpsFrames.push(fps);

        // Keep last 60 samples
        if (this.fpsFrames.length > 60) {
          this.fpsFrames.shift();
        }

        this.recordMetric('fps', fps, 'fps');

        this.fpsFrameCount = 0;
        this.fpsLastTime = now;
      }

      this.fpsTimer = requestAnimationFrame(trackFrame);
    };

    this.fpsTimer = requestAnimationFrame(trackFrame);
  }

  /**
   * Start memory tracking.
   */
  private _startMemoryTracking(): void {
    const trackMemory = () => {
      if (!this.isRunning) {
        return;
      }

      const stats = this._captureMemorySnapshot();

      if (stats) {
        this.memorySnapshots.push(stats);

        // Keep last 60 samples
        if (this.memorySnapshots.length > 60) {
          this.memorySnapshots.shift();
        }

        this.recordMetric('memory-used', stats.usedJSHeapSize, 'bytes');
        this.recordMetric('memory-percent', stats.usagePercent, 'percent');
      }
    };

    // Initial snapshot
    trackMemory();

    // Periodic snapshots
    this.memoryTimer = window.setInterval(trackMemory, this.config.memoryInterval);
  }

  /**
   * Get FPS statistics.
   */
  private _getFPSStats(): FPSStats | null {
    if (this.fpsFrames.length === 0) {
      return null;
    }

    const sum = this.fpsFrames.reduce((a, b) => a + b, 0);
    const average = sum / this.fpsFrames.length;
    const min = Math.min(...this.fpsFrames);
    const max = Math.max(...this.fpsFrames);
    const current = this.fpsFrames[this.fpsFrames.length - 1];

    return {
      current,
      average,
      min,
      max,
      samples: this.fpsFrames.length,
    };
  }

  /**
   * Get memory statistics.
   */
  private _getMemoryStats(): MemoryStats | null {
    if (this.memorySnapshots.length === 0) {
      return this._captureMemorySnapshot();
    }

    // Return most recent snapshot
    return this.memorySnapshots[this.memorySnapshots.length - 1];
  }

  /**
   * Capture memory snapshot.
   */
  private _captureMemorySnapshot(): MemoryStats | null {
    // Check if memory API is available
    if (
      typeof performance === 'undefined' ||
      !(performance as any).memory
    ) {
      return null;
    }

    const memory = (performance as any).memory;

    const usedJSHeapSize = memory.usedJSHeapSize || 0;
    const totalJSHeapSize = memory.totalJSHeapSize || 0;
    const jsHeapSizeLimit = memory.jsHeapSizeLimit || 0;

    const usagePercent =
      jsHeapSizeLimit > 0 ? (usedJSHeapSize / jsHeapSizeLimit) * 100 : 0;

    return {
      usedJSHeapSize,
      totalJSHeapSize,
      jsHeapSizeLimit,
      usagePercent,
    };
  }
}

/**
 * Global singleton instance.
 */
let globalInstance: PerformanceMonitor | null = null;

/**
 * Get global performance monitor instance.
 *
 * @param config - Optional configuration (only used on first call)
 * @returns Global performance monitor
 */
export function getGlobalPerformanceMonitor(
  config?: PerformanceMonitorConfig
): PerformanceMonitor {
  if (!globalInstance) {
    globalInstance = new PerformanceMonitor(config);
  }

  return globalInstance;
}

/**
 * Destroy global performance monitor instance.
 */
export function destroyGlobalPerformanceMonitor(): void {
  if (globalInstance) {
    globalInstance.stop();
    globalInstance = null;
  }
}
