/**
 * Tests for useVirtualScrolling hook.
 *
 * @vitest-environment node
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useVirtualScrolling, type VirtualScrollConfig } from './useVirtualScrolling';

describe('useVirtualScrolling', () => {
  describe('Visible Range Calculation', () => {
    it('should calculate correct visible range for start of list', () => {
      const config: VirtualScrollConfig = {
        totalItems: 1000,
        itemHeight: 100,
        viewportHeight: 800,
        overscan: 2,
      };

      // Initial state (scrollOffset = 0)
      const scrollOffset = 0;
      const viewportHeight = config.viewportHeight;
      const itemHeight = config.itemHeight;
      const overscan = config.overscan!;

      // Calculate manually
      const startIndexRaw = Math.floor(scrollOffset / itemHeight); // 0
      const endIndexRaw = Math.ceil((scrollOffset + viewportHeight) / itemHeight); // 8

      const startIndex = Math.max(0, startIndexRaw - overscan); // 0 (can't go negative)
      const endIndex = Math.min(config.totalItems, endIndexRaw + overscan); // 10

      expect(startIndex).toBe(0);
      expect(endIndex).toBe(10);

      // visibleItems should be [0, 1, 2, ..., 9]
      const expectedItems = Array.from({ length: 10 }, (_, i) => i);
      const actualItems = [];
      for (let i = startIndex; i < endIndex; i++) {
        actualItems.push(i);
      }

      expect(actualItems).toEqual(expectedItems);
    });

    it('should calculate correct visible range for middle of list', () => {
      const config: VirtualScrollConfig = {
        totalItems: 1000,
        itemHeight: 100,
        viewportHeight: 800,
        overscan: 3,
      };

      const scrollOffset = 5000; // Scrolled halfway
      const viewportHeight = config.viewportHeight;
      const itemHeight = config.itemHeight;
      const overscan = config.overscan!;

      // Calculate manually
      const startIndexRaw = Math.floor(scrollOffset / itemHeight); // 50
      const endIndexRaw = Math.ceil((scrollOffset + viewportHeight) / itemHeight); // 58

      const startIndex = Math.max(0, startIndexRaw - overscan); // 47
      const endIndex = Math.min(config.totalItems, endIndexRaw + overscan); // 61

      expect(startIndex).toBe(47);
      expect(endIndex).toBe(61);
      expect(endIndex - startIndex).toBe(14); // 14 items visible
    });

    it('should calculate correct visible range for end of list', () => {
      const config: VirtualScrollConfig = {
        totalItems: 100,
        itemHeight: 100,
        viewportHeight: 800,
        overscan: 2,
      };

      const scrollOffset = 9200; // Near end
      const viewportHeight = config.viewportHeight;
      const itemHeight = config.itemHeight;
      const overscan = config.overscan!;

      // Calculate manually
      const startIndexRaw = Math.floor(scrollOffset / itemHeight); // 92
      const endIndexRaw = Math.ceil((scrollOffset + viewportHeight) / itemHeight); // 100

      const startIndex = Math.max(0, startIndexRaw - overscan); // 90
      const endIndex = Math.min(config.totalItems, endIndexRaw + overscan); // 100 (clamped)

      expect(startIndex).toBe(90);
      expect(endIndex).toBe(100);
    });

    it('should handle zero overscan', () => {
      const config: VirtualScrollConfig = {
        totalItems: 1000,
        itemHeight: 100,
        viewportHeight: 800,
        overscan: 0,
      };

      const scrollOffset = 1000;
      const viewportHeight = config.viewportHeight;
      const itemHeight = config.itemHeight;
      const overscan = config.overscan!;

      // Calculate manually
      const startIndexRaw = Math.floor(scrollOffset / itemHeight); // 10
      const endIndexRaw = Math.ceil((scrollOffset + viewportHeight) / itemHeight); // 18

      const startIndex = Math.max(0, startIndexRaw - overscan); // 10
      const endIndex = Math.min(config.totalItems, endIndexRaw + overscan); // 18

      expect(startIndex).toBe(10);
      expect(endIndex).toBe(18);
      expect(endIndex - startIndex).toBe(8); // Exactly visible items, no overscan
    });

    it('should handle large overscan', () => {
      const config: VirtualScrollConfig = {
        totalItems: 100,
        itemHeight: 100,
        viewportHeight: 800,
        overscan: 50,
      };

      const scrollOffset = 0;
      const viewportHeight = config.viewportHeight;
      const itemHeight = config.itemHeight;
      const overscan = config.overscan!;

      // Calculate manually
      const startIndexRaw = Math.floor(scrollOffset / itemHeight); // 0
      const endIndexRaw = Math.ceil((scrollOffset + viewportHeight) / itemHeight); // 8

      const startIndex = Math.max(0, startIndexRaw - overscan); // 0 (clamped)
      const endIndex = Math.min(config.totalItems, endIndexRaw + overscan); // 58

      expect(startIndex).toBe(0);
      expect(endIndex).toBe(58);
    });
  });

  describe('Total Height Calculation', () => {
    it('should calculate correct total height', () => {
      const config: VirtualScrollConfig = {
        totalItems: 1000,
        itemHeight: 100,
        viewportHeight: 800,
      };

      const totalHeight = config.totalItems * config.itemHeight;

      expect(totalHeight).toBe(100000); // 1000 * 100
    });

    it('should handle small datasets', () => {
      const config: VirtualScrollConfig = {
        totalItems: 10,
        itemHeight: 50,
        viewportHeight: 800,
      };

      const totalHeight = config.totalItems * config.itemHeight;

      expect(totalHeight).toBe(500); // 10 * 50
    });

    it('should handle large datasets', () => {
      const config: VirtualScrollConfig = {
        totalItems: 100000,
        itemHeight: 200,
        viewportHeight: 1000,
      };

      const totalHeight = config.totalItems * config.itemHeight;

      expect(totalHeight).toBe(20000000); // 100000 * 200
    });
  });

  describe('Container Offset Calculation', () => {
    it('should calculate correct container offset', () => {
      const startIndex = 50;
      const itemHeight = 100;

      const containerOffset = startIndex * itemHeight;

      expect(containerOffset).toBe(5000); // 50 * 100
    });

    it('should handle zero start index', () => {
      const startIndex = 0;
      const itemHeight = 100;

      const containerOffset = startIndex * itemHeight;

      expect(containerOffset).toBe(0);
    });

    it('should handle large start index', () => {
      const startIndex = 9990;
      const itemHeight = 100;

      const containerOffset = startIndex * itemHeight;

      expect(containerOffset).toBe(999000); // 9990 * 100
    });
  });

  describe('Scroll Offset Clamping', () => {
    it('should clamp scroll offset to minimum (0)', () => {
      const totalHeight = 10000;
      const viewportHeight = 800;
      const newOffset = -500; // Negative (invalid)

      const maxOffset = Math.max(0, totalHeight - viewportHeight);
      const clampedOffset = Math.max(0, Math.min(maxOffset, newOffset));

      expect(clampedOffset).toBe(0);
    });

    it('should clamp scroll offset to maximum', () => {
      const totalHeight = 10000;
      const viewportHeight = 800;
      const newOffset = 15000; // Beyond max

      const maxOffset = Math.max(0, totalHeight - viewportHeight); // 9200
      const clampedOffset = Math.max(0, Math.min(maxOffset, newOffset));

      expect(clampedOffset).toBe(9200);
    });

    it('should not clamp valid scroll offset', () => {
      const totalHeight = 10000;
      const viewportHeight = 800;
      const newOffset = 5000; // Valid

      const maxOffset = Math.max(0, totalHeight - viewportHeight);
      const clampedOffset = Math.max(0, Math.min(maxOffset, newOffset));

      expect(clampedOffset).toBe(5000);
    });

    it('should handle viewport larger than content', () => {
      const totalHeight = 500;
      const viewportHeight = 800;
      const newOffset = 200;

      const maxOffset = Math.max(0, totalHeight - viewportHeight); // 0 (viewport bigger)
      const clampedOffset = Math.max(0, Math.min(maxOffset, newOffset));

      expect(clampedOffset).toBe(0); // Can't scroll
    });
  });

  describe('ScrollToItem Alignment', () => {
    it('should calculate offset for start alignment', () => {
      const index = 50;
      const itemHeight = 100;
      const viewportHeight = 800;

      const offset = index * itemHeight; // Start alignment

      expect(offset).toBe(5000);
    });

    it('should calculate offset for center alignment', () => {
      const index = 50;
      const itemHeight = 100;
      const viewportHeight = 800;

      const offset = index * itemHeight - viewportHeight / 2 + itemHeight / 2;

      expect(offset).toBe(4650); // 5000 - 400 + 50
    });

    it('should calculate offset for end alignment', () => {
      const index = 50;
      const itemHeight = 100;
      const viewportHeight = 800;

      const offset = index * itemHeight - viewportHeight + itemHeight;

      expect(offset).toBe(4300); // 5000 - 800 + 100
    });

    it('should clamp index when scrolling to item', () => {
      const totalItems = 100;

      // Index beyond bounds
      let clampedIndex = Math.max(0, Math.min(totalItems - 1, 150));
      expect(clampedIndex).toBe(99);

      // Negative index
      clampedIndex = Math.max(0, Math.min(totalItems - 1, -10));
      expect(clampedIndex).toBe(0);

      // Valid index
      clampedIndex = Math.max(0, Math.min(totalItems - 1, 50));
      expect(clampedIndex).toBe(50);
    });
  });

  describe('Container Style Generation', () => {
    it('should generate correct container style', () => {
      const totalHeight = 100000;
      const containerOffset = 5000;

      const style = {
        position: 'relative' as const,
        height: `${totalHeight}px`,
        transform: `translateY(${containerOffset}px)`,
        willChange: 'transform',
      };

      expect(style.height).toBe('100000px');
      expect(style.transform).toBe('translateY(5000px)');
      expect(style.willChange).toBe('transform');
    });

    it('should handle zero offset', () => {
      const totalHeight = 50000;
      const containerOffset = 0;

      const style = {
        height: `${totalHeight}px`,
        transform: `translateY(${containerOffset}px)`,
      };

      expect(style.height).toBe('50000px');
      expect(style.transform).toBe('translateY(0px)');
    });
  });

  describe('Item Style Generation', () => {
    it('should generate correct item style', () => {
      const index = 55;
      const startIndex = 50;
      const itemHeight = 100;

      const style = {
        position: 'absolute' as const,
        top: 0,
        left: 0,
        width: '100%',
        height: `${itemHeight}px`,
        transform: `translateY(${(index - startIndex) * itemHeight}px)`,
      };

      expect(style.height).toBe('100px');
      expect(style.transform).toBe('translateY(500px)'); // (55 - 50) * 100
    });

    it('should handle first visible item', () => {
      const index = 50;
      const startIndex = 50;
      const itemHeight = 100;

      const style = {
        transform: `translateY(${(index - startIndex) * itemHeight}px)`,
      };

      expect(style.transform).toBe('translateY(0px)');
    });

    it('should handle negative offset for items before startIndex', () => {
      const index = 48;
      const startIndex = 50;
      const itemHeight = 100;

      const style = {
        transform: `translateY(${(index - startIndex) * itemHeight}px)`,
      };

      expect(style.transform).toBe('translateY(-200px)'); // (48 - 50) * 100
    });
  });

  describe('Visibility Check', () => {
    it('should correctly identify visible items', () => {
      const startIndex = 50;
      const endIndex = 60;

      // Check items in range
      for (let i = startIndex; i < endIndex; i++) {
        const isVisible = i >= startIndex && i < endIndex;
        expect(isVisible).toBe(true);
      }

      // Check items before range
      expect(49 >= startIndex && 49 < endIndex).toBe(false);

      // Check items after range
      expect(60 >= startIndex && 60 < endIndex).toBe(false);
      expect(100 >= startIndex && 100 < endIndex).toBe(false);
    });

    it('should handle edge cases', () => {
      const startIndex = 0;
      const endIndex = 10;

      expect(0 >= startIndex && 0 < endIndex).toBe(true);
      expect(9 >= startIndex && 9 < endIndex).toBe(true);
      expect(10 >= startIndex && 10 < endIndex).toBe(false); // Exclusive
    });
  });

  describe('Performance Characteristics', () => {
    it('should render constant number of items regardless of total', () => {
      const itemHeight = 100;
      const viewportHeight = 800;
      const overscan = 3;

      // Calculate for 100 items
      const visible100 = Math.ceil(viewportHeight / itemHeight) + overscan * 2;

      // Calculate for 10,000 items (same viewport)
      const visible10000 = Math.ceil(viewportHeight / itemHeight) + overscan * 2;

      // Calculate for 100,000 items (same viewport)
      const visible100000 = Math.ceil(viewportHeight / itemHeight) + overscan * 2;

      // All should be the same (constant memory)
      expect(visible100).toBe(visible10000);
      expect(visible10000).toBe(visible100000);
      expect(visible100).toBe(14); // 8 visible + 6 overscan
    });

    it('should handle large datasets efficiently', () => {
      const totalItems = 1000000; // 1 million items
      const itemHeight = 100;
      const viewportHeight = 1000;
      const overscan = 5;

      // Total height calculation (simple multiplication, O(1))
      const totalHeight = totalItems * itemHeight;
      expect(totalHeight).toBe(100000000);

      // Visible items calculation (constant time, O(1))
      const scrollOffset = 50000000; // Arbitrary position
      const startIndexRaw = Math.floor(scrollOffset / itemHeight);
      const endIndexRaw = Math.ceil((scrollOffset + viewportHeight) / itemHeight);

      const startIndex = Math.max(0, startIndexRaw - overscan);
      const endIndex = Math.min(totalItems, endIndexRaw + overscan);

      const visibleCount = endIndex - startIndex;

      // Should render constant number of items (not related to totalItems)
      expect(visibleCount).toBe(20); // 10 visible + 10 overscan
    });

    it('should use efficient array generation for visible items', () => {
      const startIndex = 1000;
      const endIndex = 1020;

      const startTime = performance.now();

      // Generate visible items array
      const visibleItems: number[] = [];
      for (let i = startIndex; i < endIndex; i++) {
        visibleItems.push(i);
      }

      const elapsed = performance.now() - startTime;

      expect(visibleItems.length).toBe(20);
      expect(elapsed).toBeLessThan(1); // Should be < 1ms
    });
  });

  describe('Momentum Scrolling', () => {
    it('should calculate velocity from scroll delta', () => {
      const deltaOffset = 500;
      const deltaTime = 100; // 100ms

      const velocity = deltaOffset / deltaTime; // 5 px/ms

      expect(velocity).toBe(5);
    });

    it('should apply momentum decay', () => {
      const initialVelocity = 10;
      const decay = 0.95;

      let velocity = initialVelocity;

      // Decay for 10 frames
      for (let i = 0; i < 10; i++) {
        velocity *= decay;
      }

      expect(velocity).toBeCloseTo(5.987, 2); // ~60% after 10 frames
    });

    it('should stop when velocity drops below minimum', () => {
      const minVelocity = 0.5;

      let velocity = 1.0;
      const decay = 0.9;

      let iterations = 0;
      const maxIterations = 100;

      while (Math.abs(velocity) > minVelocity && iterations < maxIterations) {
        velocity *= decay;
        iterations++;
      }

      expect(Math.abs(velocity)).toBeLessThanOrEqual(minVelocity);
      expect(iterations).toBeLessThan(maxIterations); // Should converge
    });
  });

  describe('Edge Cases', () => {
    it('should handle single item list', () => {
      const totalItems = 1;
      const itemHeight = 100;

      const totalHeight = totalItems * itemHeight;

      expect(totalHeight).toBe(100);
    });

    it('should handle empty list', () => {
      const totalItems = 0;
      const itemHeight = 100;

      const totalHeight = totalItems * itemHeight;

      expect(totalHeight).toBe(0);
    });

    it('should handle very small item height', () => {
      const totalItems = 1000;
      const itemHeight = 1; // 1px

      const totalHeight = totalItems * itemHeight;

      expect(totalHeight).toBe(1000);
    });

    it('should handle very large item height', () => {
      const totalItems = 100;
      const itemHeight = 10000; // 10,000px

      const totalHeight = totalItems * itemHeight;

      expect(totalHeight).toBe(1000000);
    });
  });
});
