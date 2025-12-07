/**
 * @vitest-environment node
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  throttle,
  debounce,
  rafThrottle,
  debounceImmediate,
  memoize,
  batch,
  measurePerformance,
} from './performance';

describe('throttle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should execute immediately on first call', () => {
    const fn = vi.fn();
    const throttled = throttle(fn, 100);

    throttled();
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('should throttle subsequent calls', () => {
    const fn = vi.fn();
    const throttled = throttle(fn, 100);

    throttled(); // Call 1 - executes
    throttled(); // Call 2 - throttled
    throttled(); // Call 3 - throttled

    expect(fn).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(100);
    throttled(); // Call 4 - executes

    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('should pass arguments correctly', () => {
    const fn = vi.fn();
    const throttled = throttle(fn, 100);

    throttled('arg1', 'arg2');
    expect(fn).toHaveBeenCalledWith('arg1', 'arg2');
  });

  it('should execute pending call after wait time', () => {
    const fn = vi.fn();
    const throttled = throttle(fn, 100);

    throttled(); // Executes immediately
    throttled(); // Scheduled for later

    expect(fn).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(100);

    expect(fn).toHaveBeenCalledTimes(2);
  });
});

describe('debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should not execute immediately', () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 100);

    debounced();
    expect(fn).not.toHaveBeenCalled();
  });

  it('should execute after wait time', () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 100);

    debounced();
    vi.advanceTimersByTime(100);

    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('should reset timer on subsequent calls', () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 100);

    debounced();
    vi.advanceTimersByTime(50);

    debounced(); // Reset timer
    vi.advanceTimersByTime(50);

    expect(fn).not.toHaveBeenCalled(); // Still waiting

    vi.advanceTimersByTime(50); // Total: 150ms
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('should only execute once after multiple rapid calls', () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 100);

    debounced();
    debounced();
    debounced();
    debounced();

    vi.advanceTimersByTime(100);

    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('should pass latest arguments', () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 100);

    debounced('arg1');
    debounced('arg2');
    debounced('arg3');

    vi.advanceTimersByTime(100);

    expect(fn).toHaveBeenCalledWith('arg3');
    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe('rafThrottle', () => {
  beforeEach(() => {
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      setTimeout(cb, 16); // ~60fps
      return 1;
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('should execute on next animation frame', () => {
    const fn = vi.fn();
    const throttled = rafThrottle(fn);

    throttled();
    expect(fn).not.toHaveBeenCalled(); // Not executed yet

    vi.advanceTimersByTime(16);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('should use latest arguments when called multiple times', () => {
    const fn = vi.fn();
    const throttled = rafThrottle(fn);

    throttled('arg1');
    throttled('arg2');
    throttled('arg3');

    vi.advanceTimersByTime(16);

    expect(fn).toHaveBeenCalledWith('arg3');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('should not schedule multiple RAF calls', () => {
    const fn = vi.fn();
    const throttled = rafThrottle(fn);

    throttled();
    throttled();
    throttled();

    vi.advanceTimersByTime(16);

    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe('debounceImmediate', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should execute immediately on first call', () => {
    const fn = vi.fn();
    const debounced = debounceImmediate(fn, 100);

    debounced();
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('should not execute on subsequent calls within wait time', () => {
    const fn = vi.fn();
    const debounced = debounceImmediate(fn, 100);

    debounced(); // Executes
    debounced(); // Debounced
    debounced(); // Debounced

    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('should execute again after wait time', () => {
    const fn = vi.fn();
    const debounced = debounceImmediate(fn, 100);

    debounced(); // Executes immediately
    expect(fn).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(100);

    debounced(); // Executes again (new sequence)
    expect(fn).toHaveBeenCalledTimes(2);
  });
});

describe('memoize', () => {
  it('should cache results based on arguments', () => {
    const fn = vi.fn((a: number, b: number) => a + b);
    const memoized = memoize(fn);

    const result1 = memoized(1, 2);
    const result2 = memoized(1, 2); // Should use cache

    expect(result1).toBe(3);
    expect(result2).toBe(3);
    expect(fn).toHaveBeenCalledTimes(1); // Only called once
  });

  it('should not use cache for different arguments', () => {
    const fn = vi.fn((a: number, b: number) => a + b);
    const memoized = memoize(fn);

    const result1 = memoized(1, 2);
    const result2 = memoized(2, 3);

    expect(result1).toBe(3);
    expect(result2).toBe(5);
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('should support custom key generator', () => {
    const fn = vi.fn((obj: { id: number }) => obj.id * 2);
    const memoized = memoize(fn, (obj) => String(obj.id));

    const result1 = memoized({ id: 1 });
    const result2 = memoized({ id: 1 }); // Different object, same id

    expect(result1).toBe(2);
    expect(result2).toBe(2);
    expect(fn).toHaveBeenCalledTimes(1); // Cache hit
  });
});

describe('batch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should collect items and execute in batch', () => {
    const fn = vi.fn();
    const batched = batch(fn, 100);

    batched('item1');
    batched('item2');
    batched('item3');

    expect(fn).not.toHaveBeenCalled();

    vi.advanceTimersByTime(100);

    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith(['item1', 'item2', 'item3']);
  });

  it('should execute immediately when max batch size is reached', () => {
    const fn = vi.fn();
    const batched = batch(fn, 100, 3); // Max batch size: 3

    batched('item1');
    batched('item2');
    batched('item3'); // Reaches max size

    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith(['item1', 'item2', 'item3']);
  });

  it('should reset batch after execution', () => {
    const fn = vi.fn();
    const batched = batch(fn, 100);

    batched('item1');
    vi.advanceTimersByTime(100);

    expect(fn).toHaveBeenCalledTimes(1);

    batched('item2');
    vi.advanceTimersByTime(100);

    expect(fn).toHaveBeenCalledTimes(2);
    expect(fn).toHaveBeenNthCalledWith(2, ['item2']);
  });
});

describe('measurePerformance', () => {
  it('should execute function and log timing', () => {
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const fn = vi.fn(() => 42);
    const measured = measurePerformance(fn, 'Test Function');

    const result = measured();

    expect(result).toBe(42);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining('[Performance] Test Function:')
    );

    consoleSpy.mockRestore();
  });

  it('should preserve arguments', () => {
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const fn = vi.fn((a: number, b: number) => a + b);
    const measured = measurePerformance(fn, 'Add');

    const result = measured(1, 2);

    expect(result).toBe(3);
    expect(fn).toHaveBeenCalledWith(1, 2);

    consoleSpy.mockRestore();
  });
});

// Note: prefersReducedMotion and addPassiveEventListener tests require DOM environment
// These are tested separately in component/integration tests
