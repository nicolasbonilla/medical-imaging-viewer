/**
 * Performance Utilities
 *
 * Throttling, debouncing, and other performance optimization utilities.
 * Part of FASE 1: Quick Wins optimization.
 */

/**
 * Throttle function - Execute at most once every `wait` ms
 *
 * Best for: High-frequency events (mousemove, scroll, resize)
 * Guarantees: Function executes at regular intervals during activity
 *
 * @param func - Function to throttle
 * @param wait - Minimum time between executions (ms)
 * @returns Throttled function
 *
 * @example
 * const handleMouseMove = throttle((e: MouseEvent) => {
 *   console.log(e.clientX, e.clientY);
 * }, 16); // 60 FPS
 */
export function throttle<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;
  let lastExecuted = 0;

  return function (this: any, ...args: Parameters<T>) {
    const now = Date.now();
    const remaining = wait - (now - lastExecuted);

    if (remaining <= 0) {
      // Time has passed, execute immediately
      if (timeout) {
        clearTimeout(timeout);
        timeout = null;
      }
      lastExecuted = now;
      func.apply(this, args);
    } else if (!timeout) {
      // Schedule execution for when time is up
      timeout = setTimeout(() => {
        lastExecuted = Date.now();
        timeout = null;
        func.apply(this, args);
      }, remaining);
    }
  };
}

/**
 * Debounce function - Execute after `wait` ms of inactivity
 *
 * Best for: Search inputs, window resize, form validation
 * Guarantees: Function only executes after user stops activity
 *
 * @param func - Function to debounce
 * @param wait - Time to wait after last call (ms)
 * @returns Debounced function
 *
 * @example
 * const handleSearch = debounce((query: string) => {
 *   searchAPI(query);
 * }, 300);
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;

  return function (this: any, ...args: Parameters<T>) {
    if (timeout) {
      clearTimeout(timeout);
    }

    timeout = setTimeout(() => {
      func.apply(this, args);
    }, wait);
  };
}

/**
 * Request Animation Frame throttle - Execute once per frame
 *
 * Best for: Visual updates, animations, canvas rendering
 * Guarantees: Maximum 60 FPS, synchronized with browser repaint
 *
 * @param func - Function to throttle
 * @returns RAF-throttled function
 *
 * @example
 * const updateCanvas = rafThrottle((x: number, y: number) => {
 *   ctx.clearRect(0, 0, canvas.width, canvas.height);
 *   ctx.fillRect(x, y, 10, 10);
 * });
 */
export function rafThrottle<T extends (...args: any[]) => any>(
  func: T
): (...args: Parameters<T>) => void {
  let rafId: number | null = null;
  let latestArgs: Parameters<T> | null = null;

  return function (this: any, ...args: Parameters<T>) {
    latestArgs = args;

    if (rafId !== null) {
      // Already scheduled, just update args
      return;
    }

    rafId = requestAnimationFrame(() => {
      if (latestArgs !== null) {
        func.apply(this, latestArgs);
        latestArgs = null;
      }
      rafId = null;
    });
  };
}

/**
 * Debounce with immediate first execution
 *
 * Execute immediately on first call, then debounce subsequent calls.
 * Useful for responsive UI that needs immediate feedback.
 *
 * @param func - Function to debounce
 * @param wait - Time to wait after last call (ms)
 * @returns Debounced function with immediate first execution
 *
 * @example
 * const handleClick = debounceImmediate((e: MouseEvent) => {
 *   console.log('Click!');
 * }, 1000);
 */
export function debounceImmediate<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;
  let isFirstCall = true;

  return function (this: any, ...args: Parameters<T>) {
    if (isFirstCall) {
      // Execute immediately on first call
      func.apply(this, args);
      isFirstCall = false;
    }

    if (timeout) {
      clearTimeout(timeout);
    }

    timeout = setTimeout(() => {
      isFirstCall = true; // Reset for next sequence
    }, wait);
  };
}

/**
 * Memoize function results (simple cache)
 *
 * Cache function results based on arguments.
 * Useful for expensive calculations with same inputs.
 *
 * @param func - Function to memoize
 * @param keyGenerator - Optional custom key generator
 * @returns Memoized function
 *
 * @example
 * const expensiveCalc = memoize((a: number, b: number) => {
 *   return Math.pow(a, b); // Expensive operation
 * });
 */
export function memoize<T extends (...args: any[]) => any>(
  func: T,
  keyGenerator?: (...args: Parameters<T>) => string
): T {
  const cache = new Map<string, ReturnType<T>>();

  const defaultKeyGenerator = (...args: Parameters<T>): string => {
    return JSON.stringify(args);
  };

  const getKey = keyGenerator || defaultKeyGenerator;

  return function (this: any, ...args: Parameters<T>): ReturnType<T> {
    const key = getKey(...args);

    if (cache.has(key)) {
      return cache.get(key)!;
    }

    const result = func.apply(this, args);
    cache.set(key, result);

    return result;
  } as T;
}

/**
 * Batch function calls and execute together
 *
 * Collect multiple calls and execute them in a single batch.
 * Reduces overhead for operations that can be batched (e.g., DOM updates).
 *
 * @param func - Function to batch
 * @param wait - Time to wait before executing batch (ms)
 * @param maxBatchSize - Maximum batch size (optional)
 * @returns Batched function
 *
 * @example
 * const updateDOM = batch((elements: HTMLElement[]) => {
 *   elements.forEach(el => el.style.color = 'red');
 * }, 16);
 */
export function batch<T>(
  func: (items: T[]) => void,
  wait: number,
  maxBatchSize?: number
): (item: T) => void {
  let items: T[] = [];
  let timeout: NodeJS.Timeout | null = null;

  const executeBatch = () => {
    if (items.length > 0) {
      func(items);
      items = [];
    }
    timeout = null;
  };

  return (item: T) => {
    items.push(item);

    // Execute immediately if max batch size reached
    if (maxBatchSize && items.length >= maxBatchSize) {
      if (timeout) {
        clearTimeout(timeout);
      }
      executeBatch();
      return;
    }

    // Otherwise, schedule batch execution
    if (timeout) {
      clearTimeout(timeout);
    }

    timeout = setTimeout(executeBatch, wait);
  };
}

/**
 * Performance measurement utility
 *
 * Measure execution time of a function.
 * Useful for profiling and debugging performance issues.
 *
 * @param func - Function to measure
 * @param label - Label for console output
 * @returns Wrapped function that logs execution time
 *
 * @example
 * const slowFunction = measurePerformance(() => {
 *   // Some slow operation
 * }, 'Slow Operation');
 */
export function measurePerformance<T extends (...args: any[]) => any>(
  func: T,
  label: string
): T {
  return function (this: any, ...args: Parameters<T>): ReturnType<T> {
    const start = performance.now();
    const result = func.apply(this, args);
    const end = performance.now();

    console.log(`[Performance] ${label}: ${(end - start).toFixed(2)}ms`);

    return result;
  } as T;
}

/**
 * Async version of measurePerformance
 */
export function measurePerformanceAsync<T extends (...args: any[]) => Promise<any>>(
  func: T,
  label: string
): T {
  return async function (this: any, ...args: Parameters<T>): Promise<ReturnType<T>> {
    const start = performance.now();
    const result = await func.apply(this, args);
    const end = performance.now();

    console.log(`[Performance] ${label}: ${(end - start).toFixed(2)}ms`);

    return result;
  } as T;
}

/**
 * Check if reduced motion is preferred (accessibility)
 *
 * Returns true if user has enabled "prefers-reduced-motion".
 * Use this to disable animations for accessibility.
 *
 * @returns True if reduced motion is preferred
 */
export function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Passive event listener helper
 *
 * Add event listener with passive option for better scroll performance.
 *
 * @param element - Element to attach listener to
 * @param event - Event name
 * @param handler - Event handler
 * @param options - Additional options
 */
export function addPassiveEventListener(
  element: HTMLElement | Window | Document,
  event: string,
  handler: EventListener,
  options?: Omit<AddEventListenerOptions, 'passive'>
): () => void {
  const passiveOptions = { ...options, passive: true };
  element.addEventListener(event, handler, passiveOptions);

  // Return cleanup function
  return () => {
    element.removeEventListener(event, handler, passiveOptions);
  };
}
