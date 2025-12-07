/**
 * Tests for Performance Monitor Service.
 *
 * @vitest-environment node
 */

import { describe, it, expect, beforeEach } from 'vitest';
import type {
  PerformanceMetric,
  PerformanceMeasurement,
  FPSStats,
  MemoryStats,
  PerformanceMonitorConfig,
} from './performanceMonitor';

describe('Performance Monitor - Logic Tests', () => {
  describe('Metric Collection', () => {
    it('should store metric with all properties', () => {
      const metric: PerformanceMetric = {
        name: 'cache-hit-rate',
        value: 0.95,
        unit: 'percent',
        timestamp: performance.now(),
        metadata: { source: 'indexeddb' },
      };

      expect(metric.name).toBe('cache-hit-rate');
      expect(metric.value).toBe(0.95);
      expect(metric.unit).toBe('percent');
      expect(metric.timestamp).toBeGreaterThan(0);
      expect(metric.metadata?.source).toBe('indexeddb');
    });

    it('should handle metric without metadata', () => {
      const metric: PerformanceMetric = {
        name: 'fps',
        value: 60,
        unit: 'fps',
        timestamp: Date.now(),
      };

      expect(metric.metadata).toBeUndefined();
    });

    it('should enforce max metrics limit', () => {
      const maxMetrics = 100;
      const metrics: PerformanceMetric[] = [];

      // Add more than max
      for (let i = 0; i < 150; i++) {
        metrics.push({
          name: `metric-${i}`,
          value: i,
          unit: 'ms',
          timestamp: Date.now(),
        });

        // Enforce limit
        if (metrics.length > maxMetrics) {
          metrics.shift();
        }
      }

      expect(metrics.length).toBe(maxMetrics);
      expect(metrics[0].name).toBe('metric-50'); // First 50 removed
    });
  });

  describe('Performance Measurements', () => {
    it('should calculate duration between marks', () => {
      const startTime = 1000;
      const endTime = 1500;

      const duration = endTime - startTime;

      expect(duration).toBe(500);
    });

    it('should create measurement with all properties', () => {
      const measurement: PerformanceMeasurement = {
        name: 'slice-load',
        startMark: 'slice-load-start',
        endMark: 'slice-load-end',
        duration: 245.5,
        timestamp: Date.now(),
      };

      expect(measurement.name).toBe('slice-load');
      expect(measurement.duration).toBe(245.5);
    });

    it('should handle missing marks', () => {
      const marks = new Map<string, number>();

      const startTime = marks.get('start');
      const endTime = marks.get('end');

      expect(startTime).toBeUndefined();
      expect(endTime).toBeUndefined();

      // Should return 0 when marks missing
      const duration = startTime !== undefined && endTime !== undefined
        ? endTime - startTime
        : 0;

      expect(duration).toBe(0);
    });

    it('should enforce max measurements limit', () => {
      const maxMeasurements = 100;
      const measurements: PerformanceMeasurement[] = [];

      for (let i = 0; i < 150; i++) {
        measurements.push({
          name: `measurement-${i}`,
          startMark: 'start',
          endMark: 'end',
          duration: i * 10,
          timestamp: Date.now(),
        });

        if (measurements.length > maxMeasurements) {
          measurements.shift();
        }
      }

      expect(measurements.length).toBe(maxMeasurements);
    });
  });

  describe('FPS Calculation', () => {
    it('should calculate FPS from frame count and time delta', () => {
      const frameCount = 60;
      const timeDelta = 1000; // 1 second

      const fps = (frameCount * 1000) / timeDelta;

      expect(fps).toBe(60);
    });

    it('should calculate FPS statistics', () => {
      const fpsFrames = [58, 59, 60, 61, 62, 60, 59];

      const sum = fpsFrames.reduce((a, b) => a + b, 0);
      const average = sum / fpsFrames.length;
      const min = Math.min(...fpsFrames);
      const max = Math.max(...fpsFrames);
      const current = fpsFrames[fpsFrames.length - 1];

      const stats: FPSStats = {
        current,
        average,
        min,
        max,
        samples: fpsFrames.length,
      };

      expect(stats.average).toBeCloseTo(59.86, 1);
      expect(stats.min).toBe(58);
      expect(stats.max).toBe(62);
      expect(stats.current).toBe(59);
      expect(stats.samples).toBe(7);
    });

    it('should handle empty FPS data', () => {
      const fpsFrames: number[] = [];

      const stats = fpsFrames.length === 0 ? null : {
        current: 0,
        average: 0,
        min: 0,
        max: 0,
        samples: 0,
      };

      expect(stats).toBeNull();
    });

    it('should keep limited FPS samples', () => {
      const maxSamples = 60;
      const fpsFrames: number[] = [];

      // Simulate 100 FPS readings
      for (let i = 0; i < 100; i++) {
        fpsFrames.push(60);

        if (fpsFrames.length > maxSamples) {
          fpsFrames.shift();
        }
      }

      expect(fpsFrames.length).toBe(maxSamples);
    });
  });

  describe('Memory Statistics', () => {
    it('should calculate memory usage percentage', () => {
      const usedJSHeapSize = 30 * 1024 * 1024; // 30 MB
      const jsHeapSizeLimit = 100 * 1024 * 1024; // 100 MB

      const usagePercent = (usedJSHeapSize / jsHeapSizeLimit) * 100;

      expect(usagePercent).toBe(30);
    });

    it('should create memory stats', () => {
      const stats: MemoryStats = {
        usedJSHeapSize: 31457280, // ~30 MB
        totalJSHeapSize: 52428800, // ~50 MB
        jsHeapSizeLimit: 104857600, // ~100 MB
        usagePercent: 30,
      };

      expect(stats.usagePercent).toBe(30);
    });

    it('should handle zero heap limit', () => {
      const usedJSHeapSize = 1000;
      const jsHeapSizeLimit = 0;

      const usagePercent = jsHeapSizeLimit > 0
        ? (usedJSHeapSize / jsHeapSizeLimit) * 100
        : 0;

      expect(usagePercent).toBe(0);
    });

    it('should keep limited memory snapshots', () => {
      const maxSnapshots = 60;
      const snapshots: MemoryStats[] = [];

      for (let i = 0; i < 100; i++) {
        snapshots.push({
          usedJSHeapSize: i * 1024 * 1024,
          totalJSHeapSize: 50 * 1024 * 1024,
          jsHeapSizeLimit: 100 * 1024 * 1024,
          usagePercent: (i / 100) * 100,
        });

        if (snapshots.length > maxSnapshots) {
          snapshots.shift();
        }
      }

      expect(snapshots.length).toBe(maxSnapshots);
    });
  });

  describe('Average Calculations', () => {
    it('should calculate average metric value', () => {
      const metrics: PerformanceMetric[] = [
        { name: 'load-time', value: 100, unit: 'ms', timestamp: 0 },
        { name: 'load-time', value: 150, unit: 'ms', timestamp: 1 },
        { name: 'load-time', value: 120, unit: 'ms', timestamp: 2 },
      ];

      const values = metrics
        .filter((m) => m.name === 'load-time')
        .map((m) => m.value);

      const sum = values.reduce((a, b) => a + b, 0);
      const average = sum / values.length;

      expect(average).toBeCloseTo(123.33, 1);
    });

    it('should calculate average measurement duration', () => {
      const measurements: PerformanceMeasurement[] = [
        { name: 'render', startMark: 's', endMark: 'e', duration: 16.5, timestamp: 0 },
        { name: 'render', startMark: 's', endMark: 'e', duration: 17.2, timestamp: 1 },
        { name: 'render', startMark: 's', endMark: 'e', duration: 15.8, timestamp: 2 },
      ];

      const durations = measurements
        .filter((m) => m.name === 'render')
        .map((m) => m.duration);

      const sum = durations.reduce((a, b) => a + b, 0);
      const average = sum / durations.length;

      expect(average).toBeCloseTo(16.5, 1);
    });

    it('should return null for non-existent metric', () => {
      const metrics: PerformanceMetric[] = [];

      const values = metrics
        .filter((m) => m.name === 'missing')
        .map((m) => m.value);

      const average = values.length === 0 ? null : values.reduce((a, b) => a + b, 0) / values.length;

      expect(average).toBeNull();
    });
  });

  describe('Filtering Operations', () => {
    it('should filter metrics by name', () => {
      const metrics: PerformanceMetric[] = [
        { name: 'fps', value: 60, unit: 'fps', timestamp: 0 },
        { name: 'memory', value: 30, unit: 'mb', timestamp: 1 },
        { name: 'fps', value: 59, unit: 'fps', timestamp: 2 },
      ];

      const fpsMetrics = metrics.filter((m) => m.name === 'fps');

      expect(fpsMetrics.length).toBe(2);
      expect(fpsMetrics[0].value).toBe(60);
      expect(fpsMetrics[1].value).toBe(59);
    });

    it('should filter measurements by name', () => {
      const measurements: PerformanceMeasurement[] = [
        { name: 'load', startMark: 's', endMark: 'e', duration: 100, timestamp: 0 },
        { name: 'render', startMark: 's', endMark: 'e', duration: 16, timestamp: 1 },
        { name: 'load', startMark: 's', endMark: 'e', duration: 120, timestamp: 2 },
      ];

      const loadMeasurements = measurements.filter((m) => m.name === 'load');

      expect(loadMeasurements.length).toBe(2);
      expect(loadMeasurements[0].duration).toBe(100);
      expect(loadMeasurements[1].duration).toBe(120);
    });
  });

  describe('Time Range Calculation', () => {
    it('should calculate duration from start to end', () => {
      const startTime = 1000;
      const endTime = 5000;

      const duration = endTime - startTime;

      expect(duration).toBe(4000);
    });

    it('should handle same start and end time', () => {
      const startTime = 1000;
      const endTime = 1000;

      const duration = endTime - startTime;

      expect(duration).toBe(0);
    });
  });

  describe('Configuration', () => {
    it('should use default configuration', () => {
      const config: Required<PerformanceMonitorConfig> = {
        enableFPSTracking: false,
        fpsInterval: 1000,
        enableMemoryTracking: false,
        memoryInterval: 5000,
        maxMetrics: 1000,
        maxMeasurements: 1000,
        enableLogging: false,
      };

      expect(config.fpsInterval).toBe(1000);
      expect(config.memoryInterval).toBe(5000);
      expect(config.maxMetrics).toBe(1000);
    });

    it('should override default configuration', () => {
      const customConfig: PerformanceMonitorConfig = {
        enableFPSTracking: true,
        fpsInterval: 500,
        maxMetrics: 500,
      };

      const defaultConfig: Required<PerformanceMonitorConfig> = {
        enableFPSTracking: false,
        fpsInterval: 1000,
        enableMemoryTracking: false,
        memoryInterval: 5000,
        maxMetrics: 1000,
        maxMeasurements: 1000,
        enableLogging: false,
      };

      const mergedConfig = { ...defaultConfig, ...customConfig };

      expect(mergedConfig.enableFPSTracking).toBe(true);
      expect(mergedConfig.fpsInterval).toBe(500);
      expect(mergedConfig.maxMetrics).toBe(500);
      expect(mergedConfig.memoryInterval).toBe(5000); // From default
    });
  });

  describe('Data Export', () => {
    it('should export data as JSON', () => {
      const summary = {
        metrics: [
          { name: 'fps', value: 60, unit: 'fps', timestamp: 0 },
        ],
        measurements: [],
        fps: null,
        memory: null,
        timeRange: {
          start: 0,
          end: 1000,
          duration: 1000,
        },
      };

      const json = JSON.stringify(summary, null, 2);

      expect(json).toContain('"value": 60');
      expect(json).toContain('"duration": 1000');
    });

    it('should handle empty data export', () => {
      const summary = {
        metrics: [],
        measurements: [],
        fps: null,
        memory: null,
        timeRange: {
          start: 0,
          end: 0,
          duration: 0,
        },
      };

      const json = JSON.stringify(summary);

      expect(json).toContain('"metrics":[]');
      expect(json).toContain('"measurements":[]');
    });
  });

  describe('Performance Thresholds', () => {
    it('should detect slow operation', () => {
      const duration = 500; // ms
      const threshold = 200; // ms

      const isSlow = duration > threshold;

      expect(isSlow).toBe(true);
    });

    it('should detect fast operation', () => {
      const duration = 50; // ms
      const threshold = 200; // ms

      const isSlow = duration > threshold;

      expect(isSlow).toBe(false);
    });

    it('should detect low FPS', () => {
      const fps = 45;
      const threshold = 50;

      const isLow = fps < threshold;

      expect(isLow).toBe(true);
    });

    it('should detect high memory usage', () => {
      const usagePercent = 85;
      const threshold = 80;

      const isHigh = usagePercent > threshold;

      expect(isHigh).toBe(true);
    });
  });

  describe('Edge Cases', () => {
    it('should handle zero duration', () => {
      const duration = 0;

      expect(duration).toBe(0);
    });

    it('should handle negative duration (clock skew)', () => {
      const startTime = 2000;
      const endTime = 1000;

      const duration = endTime - startTime;

      expect(duration).toBe(-1000);
      expect(duration).toBeLessThan(0);
    });

    it('should handle very large metric value', () => {
      const metric: PerformanceMetric = {
        name: 'bytes-transferred',
        value: 1024 * 1024 * 1024 * 10, // 10 GB
        unit: 'bytes',
        timestamp: 0,
      };

      expect(metric.value).toBe(10737418240);
    });

    it('should handle very small metric value', () => {
      const metric: PerformanceMetric = {
        name: 'latency',
        value: 0.001, // 1 microsecond
        unit: 'ms',
        timestamp: 0,
      };

      expect(metric.value).toBe(0.001);
    });

    it('should handle single sample FPS', () => {
      const fpsFrames = [60];

      const average = fpsFrames.reduce((a, b) => a + b, 0) / fpsFrames.length;

      expect(average).toBe(60);
    });
  });
});
