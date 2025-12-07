/**
 * Tests for useBinaryWorker hook.
 *
 * @vitest-environment node
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useBinaryWorker, type WindowLevelParams, type HistogramParams } from './useBinaryWorker';
import type { DeserializedMessage } from '../services/binaryProtocol';
import { MessageType } from '../services/binaryProtocol';

describe('useBinaryWorker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Hook Initialization', () => {
    it('should initialize with correct default state', () => {
      const { result } = renderHook(() => useBinaryWorker());

      expect(result.current.isSupported).toBe(true);
      expect(typeof result.current.deserialize).toBe('function');
      expect(typeof result.current.applyWindowLevel).toBe('function');
      expect(typeof result.current.calculateHistogram).toBe('function');
      expect(typeof result.current.computeMinMax).toBe('function');
      expect(typeof result.current.terminate).toBe('function');
    });

    it('should accept custom options', () => {
      const { result } = renderHook(() =>
        useBinaryWorker({
          timeout: 10000,
          enableLogging: true,
          enableFallback: false,
        })
      );

      expect(result.current).toBeDefined();
    });
  });

  describe('Fallback Mode (Worker Not Supported)', () => {
    it('should use fallback for deserialize when worker not ready', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      // Create a valid METADATA message for testing
      const metadata = { test: 'data' };
      const payloadJson = JSON.stringify(metadata);
      const payloadBytes = new TextEncoder().encode(payloadJson);

      // Create header (24 bytes)
      const header = new ArrayBuffer(24);
      const headerView = new DataView(header);

      // Magic number (0x4D4449 = "MDI")
      headerView.setUint32(0, 0x4d4449, true);
      // Version
      headerView.setUint16(4, 1, true);
      // Message type (METADATA = 1)
      headerView.setUint8(6, MessageType.METADATA);
      // Compression (NONE = 0)
      headerView.setUint8(7, 0);
      // Payload length
      headerView.setUint32(8, payloadBytes.length, true);
      // Sequence number
      headerView.setUint32(12, 1, true);
      // CRC32 (calculate for payload)
      const crc = calculateCRC32(payloadBytes);
      headerView.setUint32(16, crc, true);
      // Reserved
      headerView.setUint32(20, 0, true);

      // Combine header + payload
      const message = new Uint8Array(header.byteLength + payloadBytes.length);
      message.set(new Uint8Array(header), 0);
      message.set(payloadBytes, header.byteLength);

      // Deserialize should use fallback
      const result_msg = await result.current.deserialize(message.buffer);

      expect(result_msg).toBeDefined();
      expect(result_msg.header.messageType).toBe(MessageType.METADATA);
    });

    it('should use fallback for applyWindowLevel', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Uint16Array([0, 50, 100, 150, 200]);
      const params: WindowLevelParams = {
        pixels,
        windowCenter: 100,
        windowWidth: 100,
      };

      const adjusted = await result.current.applyWindowLevel(params);

      expect(adjusted).toBeInstanceOf(Uint8ClampedArray);
      expect(adjusted.length).toBe(pixels.length);

      // Verify window/level logic
      // windowMin = 100 - 100/2 = 50
      // windowMax = 100 + 100/2 = 150
      expect(adjusted[0]).toBe(0); // value 0 <= windowMin
      expect(adjusted[1]).toBe(0); // value 50 = windowMin
      expect(adjusted[2]).toBe(127); // value 100 in middle
      expect(adjusted[3]).toBe(255); // value 150 = windowMax
      expect(adjusted[4]).toBe(255); // value 200 >= windowMax
    });

    it('should use fallback for calculateHistogram', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Uint16Array([0, 50, 100, 150, 200, 250]);
      const params: HistogramParams = { pixels, bins: 10 };

      const histogram = await result.current.calculateHistogram(params);

      expect(histogram).toBeDefined();
      expect(histogram.bins).toHaveLength(10);
      expect(histogram.min).toBe(0);
      expect(histogram.max).toBe(250);

      // Sum of bins should equal number of pixels
      const sum = histogram.bins.reduce((a, b) => a + b, 0);
      expect(sum).toBe(pixels.length);
    });

    it('should use fallback for computeMinMax', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Uint16Array([10, 50, 100, 5, 200, 30]);

      const minMax = await result.current.computeMinMax(pixels);

      expect(minMax).toBeDefined();
      expect(minMax.min).toBe(5);
      expect(minMax.max).toBe(200);
    });

    it('should throw error when fallback disabled and worker not ready', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: false })
      );

      const pixels = new Uint16Array([1, 2, 3]);

      await expect(result.current.computeMinMax(pixels)).rejects.toThrow(
        'Worker not available and fallback disabled'
      );
    });
  });

  describe('Window/Level Adjustment Fallback', () => {
    it('should handle custom output range', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Uint16Array([0, 50, 100, 150, 200]);
      const params: WindowLevelParams = {
        pixels,
        windowCenter: 100,
        windowWidth: 100,
        outputMin: 50,
        outputMax: 200,
      };

      const adjusted = await result.current.applyWindowLevel(params);

      expect(adjusted).toBeInstanceOf(Uint8ClampedArray);

      // Verify custom output range
      expect(adjusted[0]).toBe(50); // value <= windowMin → outputMin
      expect(adjusted[4]).toBe(200); // value >= windowMax → outputMax
    });

    it('should handle narrow window width', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Uint16Array([95, 100, 105]);
      const params: WindowLevelParams = {
        pixels,
        windowCenter: 100,
        windowWidth: 10, // Narrow window
      };

      const adjusted = await result.current.applyWindowLevel(params);

      expect(adjusted).toBeInstanceOf(Uint8ClampedArray);

      // windowMin = 95, windowMax = 105
      expect(adjusted[0]).toBe(0); // value 95 = windowMin
      expect(adjusted[1]).toBe(127); // value 100 = center
      expect(adjusted[2]).toBe(255); // value 105 = windowMax
    });

    it('should handle different typed arrays', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      // Test Int16Array
      const int16Pixels = new Int16Array([-100, 0, 100]);
      const int16Params: WindowLevelParams = {
        pixels: int16Pixels,
        windowCenter: 0,
        windowWidth: 200,
      };

      const int16Adjusted = await result.current.applyWindowLevel(int16Params);
      expect(int16Adjusted).toBeInstanceOf(Uint8ClampedArray);
      expect(int16Adjusted.length).toBe(3);

      // Test Float32Array
      const float32Pixels = new Float32Array([0.0, 0.5, 1.0]);
      const float32Params: WindowLevelParams = {
        pixels: float32Pixels,
        windowCenter: 0.5,
        windowWidth: 1.0,
      };

      const float32Adjusted = await result.current.applyWindowLevel(float32Params);
      expect(float32Adjusted).toBeInstanceOf(Uint8ClampedArray);
      expect(float32Adjusted.length).toBe(3);
    });
  });

  describe('Histogram Calculation Fallback', () => {
    it('should calculate histogram with default bins', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Uint16Array(1000).map((_, i) => i % 256);

      const histogram = await result.current.calculateHistogram({ pixels });

      expect(histogram.bins).toHaveLength(256); // Default bins
      expect(histogram.min).toBe(0);
      expect(histogram.max).toBe(255);
    });

    it('should calculate histogram with custom bins', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Uint16Array([0, 100, 200, 300, 400]);

      const histogram = await result.current.calculateHistogram({
        pixels,
        bins: 5,
      });

      expect(histogram.bins).toHaveLength(5);

      // Each value should fall into a bin
      const sum = histogram.bins.reduce((a, b) => a + b, 0);
      expect(sum).toBe(5);
    });

    it('should handle uniform pixel values', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      // All pixels have same value
      const pixels = new Uint16Array(100).fill(42);

      const histogram = await result.current.calculateHistogram({ pixels });

      expect(histogram.min).toBe(42);
      expect(histogram.max).toBe(42);

      // All values should be in one bin (last bin to handle edge case)
      const sum = histogram.bins.reduce((a, b) => a + b, 0);
      expect(sum).toBe(100);
    });
  });

  describe('Min/Max Computation Fallback', () => {
    it('should compute min/max for Uint16Array', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Uint16Array([100, 50, 200, 25, 150]);

      const minMax = await result.current.computeMinMax(pixels);

      expect(minMax.min).toBe(25);
      expect(minMax.max).toBe(200);
    });

    it('should compute min/max for Int16Array with negative values', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Int16Array([-100, -50, 0, 50, 100]);

      const minMax = await result.current.computeMinMax(pixels);

      expect(minMax.min).toBe(-100);
      expect(minMax.max).toBe(100);
    });

    it('should compute min/max for Float32Array', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Float32Array([0.5, 1.5, -0.5, 2.5, 1.0]);

      const minMax = await result.current.computeMinMax(pixels);

      expect(minMax.min).toBe(-0.5);
      expect(minMax.max).toBe(2.5);
    });

    it('should handle single value', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Uint16Array([42]);

      const minMax = await result.current.computeMinMax(pixels);

      expect(minMax.min).toBe(42);
      expect(minMax.max).toBe(42);
    });

    it('should handle large arrays efficiently', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      // Create large array (1M pixels)
      const pixels = new Uint16Array(1_000_000);
      for (let i = 0; i < pixels.length; i++) {
        pixels[i] = i % 4096;
      }

      const startTime = performance.now();
      const minMax = await result.current.computeMinMax(pixels);
      const elapsed = performance.now() - startTime;

      expect(minMax.min).toBe(0);
      expect(minMax.max).toBe(4095);

      // Should complete in reasonable time (< 100ms)
      expect(elapsed).toBeLessThan(100);
    });
  });

  describe('Error Handling', () => {
    it('should handle invalid window/level parameters gracefully', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      // Zero window width (edge case)
      const pixels = new Uint16Array([100, 200, 300]);
      const params: WindowLevelParams = {
        pixels,
        windowCenter: 200,
        windowWidth: 0, // Invalid!
      };

      // Should not throw, but result may be unexpected
      const adjusted = await result.current.applyWindowLevel(params);

      expect(adjusted).toBeInstanceOf(Uint8ClampedArray);
      expect(adjusted.length).toBe(pixels.length);
    });

    it('should handle empty pixel arrays', async () => {
      const { result } = renderHook(() =>
        useBinaryWorker({ enableFallback: true })
      );

      const pixels = new Uint16Array([]);

      const minMax = await result.current.computeMinMax(pixels);

      // min/max should be Infinity/-Infinity for empty array
      expect(minMax.min).toBe(Infinity);
      expect(minMax.max).toBe(-Infinity);
    });
  });

  describe('Cleanup', () => {
    it('should cleanup on unmount', () => {
      const { result, unmount } = renderHook(() => useBinaryWorker());

      // Ensure hook is initialized
      expect(result.current).toBeDefined();

      // Unmount should not throw
      expect(() => unmount()).not.toThrow();
    });

    it('should support manual termination', () => {
      const { result } = renderHook(() => useBinaryWorker());

      // Terminate manually
      expect(() => result.current.terminate()).not.toThrow();
    });
  });
});

/**
 * Calculate CRC32 checksum.
 * Simple implementation for testing.
 */
function calculateCRC32(data: Uint8Array): number {
  let crc = 0xffffffff;

  for (let i = 0; i < data.length; i++) {
    const byte = data[i];
    crc ^= byte;

    for (let j = 0; j < 8; j++) {
      if (crc & 1) {
        crc = (crc >>> 1) ^ 0xedb88320;
      } else {
        crc = crc >>> 1;
      }
    }
  }

  return (crc ^ 0xffffffff) >>> 0;
}
