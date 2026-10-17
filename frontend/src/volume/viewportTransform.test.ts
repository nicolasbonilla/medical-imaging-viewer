/**
 * Viewport transform (client viewer) and the measurement mapping (both viewers):
 * a click lands on the pixel drawn under it at any zoom/pan, the physical aspect is
 * kept on anisotropic reformats, and a ruler measures the same millimetres at any zoom.
 */
import { describe, it, expect } from 'vitest';
import {
  computeTransform, imageToScreen, linePixels, screenToImage, screenToPixel, zoomAroundPoint,
} from './viewportTransform';
import { legacyMeasurementMapping, measureDistanceMm } from '@/components/MeasurementOverlay';

const VIEW = { rows: 40, cols: 100, rowSpacing: 3.0, colSpacing: 0.9 }; // thick coronal reformat

describe('computeTransform', () => {
  it('keeps the PHYSICAL aspect (3 mm rows are drawn 3.33x taller than 0.9 mm columns)', () => {
    const t = computeTransform(1000, 800, VIEW, 1, { x: 0, y: 0 });
    expect(t.scaleY / t.scaleX).toBeCloseTo(3.0 / 0.9, 9);
    const w = VIEW.cols * t.scaleX, h = VIEW.rows * t.scaleY;
    expect(w <= 1000 * 0.92 + 1e-9 && h <= 800 * 0.92 + 1e-9).toBe(true);
    // centred
    expect(t.originX + w / 2).toBeCloseTo(500, 9);
    expect(t.originY + h / 2).toBeCloseTo(400, 9);
  });

  it('screen <-> image round-trips at any zoom / pan', () => {
    for (const zoom of [0.5, 1, 2.75, 12]) {
      for (const pan of [{ x: 0, y: 0 }, { x: -130, y: 77 }]) {
        const t = computeTransform(900, 700, VIEW, zoom, pan);
        for (const [x, y] of [[0, 0], [99.5, 39.5], [12.25, 7.75]]) {
          const s = imageToScreen(t, x, y);
          const back = screenToImage(t, s.x, s.y);
          expect(back.x).toBeCloseTo(x, 9);
          expect(back.y).toBeCloseTo(y, 9);
        }
      }
    }
  });

  it('screenToPixel returns the pixel whose square contains the point, null outside', () => {
    const t = computeTransform(900, 700, VIEW, 3, { x: 40, y: -20 });
    const inside = imageToScreen(t, 17.5, 9.5);
    expect(screenToPixel(t, VIEW, inside.x, inside.y)).toEqual({ r: 9, c: 17 });
    const outside = imageToScreen(t, -0.01, 5);
    expect(screenToPixel(t, VIEW, outside.x, outside.y)).toBeNull();
  });

  it('zoomAroundPoint keeps the image point under the pointer fixed', () => {
    const pan0 = { x: 25, y: -10 };
    const t0 = computeTransform(900, 700, VIEW, 1.5, pan0);
    const sx = 612, sy = 333;
    const anchor = screenToImage(t0, sx, sy);
    const pan1 = zoomAroundPoint(900, 700, VIEW, 1.5, pan0, 4, sx, sy);
    const t1 = computeTransform(900, 700, VIEW, 4, pan1);
    const s = imageToScreen(t1, anchor.x, anchor.y);
    expect(s.x).toBeCloseTo(sx, 9);
    expect(s.y).toBeCloseTo(sy, 9);
  });

  it('linePixels is gap-free between two pixels (fast brush strokes)', () => {
    const pts = linePixels({ r: 0, c: 0 }, { r: 3, c: 10 });
    expect(pts[0]).toEqual({ r: 0, c: 0 });
    expect(pts[pts.length - 1]).toEqual({ r: 3, c: 10 });
    for (let n = 1; n < pts.length; n++) {
      expect(Math.abs(pts[n].r - pts[n - 1].r)).toBeLessThanOrEqual(1);
      expect(Math.abs(pts[n].c - pts[n - 1].c)).toBeLessThanOrEqual(1);
    }
  });
});

describe('measurements use the real voxel spacing at any zoom', () => {
  it('distance uses [row, col] spacing (anisotropic)', () => {
    expect(measureDistanceMm({ x: 0, y: 0 }, { x: 10, y: 0 }, [3, 0.9])).toBeCloseTo(9, 9);
    expect(measureDistanceMm({ x: 0, y: 0 }, { x: 0, y: 10 }, [3, 0.9])).toBeCloseTo(30, 9);
  });

  it('legacy canvas mapping honours zoom and pan (a 20-pixel ruler stays 20 pixels at zoom 2)', () => {
    // Before v3 the overlay ignored zoom: at zoom 2 the same structure measured twice as long.
    const canvasW = 400, canvasH = 300, imgW = 200, imgH = 150;
    for (const zoom of [1, 2, 5]) {
      const m = legacyMeasurementMapping(canvasW, canvasH, imgW, imgH, zoom, { x: 13, y: -8 });
      // Where the legacy canvas DRAWS image point p: (p*s0 - c)*zoom + c + pan
      const drawn = (px: number, py: number) => ({
        x: ((px * canvasW) / imgW - canvasW / 2) * zoom + canvasW / 2 + 13,
        y: ((py * canvasH) / imgH - canvasH / 2) * zoom + canvasH / 2 - 8,
      });
      const a = drawn(50, 60), b = drawn(70, 60);
      const ia = { x: (a.x - m.originX) / m.scaleX, y: (a.y - m.originY) / m.scaleY };
      const ib = { x: (b.x - m.originX) / m.scaleX, y: (b.y - m.originY) / m.scaleY };
      expect(ia.x).toBeCloseTo(50, 9);
      expect(ib.x).toBeCloseTo(70, 9);
      expect(measureDistanceMm(ia, ib, [1, 1])).toBeCloseTo(20, 9);
    }
  });
});
