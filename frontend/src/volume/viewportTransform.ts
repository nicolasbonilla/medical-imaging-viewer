/**
 * Screen <-> image-pixel transform of the client 2D viewport. Shared by drawing,
 * painting, the cursor read-out and the measurement overlay, so a click lands on the
 * pixel that is drawn under it at any zoom / pan (tested in viewportTransform.test.ts).
 *
 * Image pixel space: column x ∈ [0, cols), row y ∈ [0, rows) — pixel (c, r) covers
 * [c, c+1) × [r, r+1). Screen = CSS pixels of the viewport element.
 *
 *   screen.x = originX + x * scaleX        scaleX = fit * zoom * colSpacing
 *   screen.y = originY + y * scaleY        scaleY = fit * zoom * rowSpacing
 *
 * `fit` (CSS px per mm) makes the PHYSICAL slice fill the viewport at zoom 1, so
 * anisotropic voxels (thick sagittal/coronal reformats) keep their true aspect.
 */
import type { SliceView } from './sliceGeometry';

export interface ViewportTransform {
  originX: number;
  originY: number;
  scaleX: number;
  scaleY: number;
}

export interface Pan { x: number; y: number }

/** Fraction of the viewport the fitted image may occupy (room for corner annotations). */
export const FIT_FRACTION = 0.92;

export function computeTransform(
  viewportW: number, viewportH: number, view: Pick<SliceView, 'rows' | 'cols' | 'rowSpacing' | 'colSpacing'>,
  zoom: number, pan: Pan, fitFraction = FIT_FRACTION,
): ViewportTransform {
  const physW = view.cols * view.colSpacing;
  const physH = view.rows * view.rowSpacing;
  const fit = Math.max(1e-6, Math.min((viewportW * fitFraction) / physW, (viewportH * fitFraction) / physH));
  const scaleX = fit * zoom * view.colSpacing;
  const scaleY = fit * zoom * view.rowSpacing;
  return {
    scaleX,
    scaleY,
    originX: viewportW / 2 + pan.x - (view.cols * scaleX) / 2,
    originY: viewportH / 2 + pan.y - (view.rows * scaleY) / 2,
  };
}

export function imageToScreen(t: ViewportTransform, x: number, y: number): { x: number; y: number } {
  return { x: t.originX + x * t.scaleX, y: t.originY + y * t.scaleY };
}

export function screenToImage(t: ViewportTransform, sx: number, sy: number): { x: number; y: number } {
  return { x: (sx - t.originX) / t.scaleX, y: (sy - t.originY) / t.scaleY };
}

/** Pixel (c, r) under a screen point, or null outside the image. */
export function screenToPixel(
  t: ViewportTransform, view: Pick<SliceView, 'rows' | 'cols'>, sx: number, sy: number,
): { r: number; c: number } | null {
  const p = screenToImage(t, sx, sy);
  const c = Math.floor(p.x), r = Math.floor(p.y);
  if (c < 0 || r < 0 || c >= view.cols || r >= view.rows) return null;
  return { r, c };
}

/** New pan that keeps the image point under (sx, sy) fixed while zooming. */
export function zoomAroundPoint(
  viewportW: number, viewportH: number, view: Pick<SliceView, 'rows' | 'cols' | 'rowSpacing' | 'colSpacing'>,
  zoom: number, pan: Pan, nextZoom: number, sx: number, sy: number,
): Pan {
  const before = computeTransform(viewportW, viewportH, view, zoom, pan);
  const anchor = screenToImage(before, sx, sy);
  const after = computeTransform(viewportW, viewportH, view, nextZoom, { x: 0, y: 0 });
  // Solve origin' + anchor*scale' = s  ->  pan' = s - anchor*scale' - (origin' without pan)
  return {
    x: sx - anchor.x * after.scaleX - after.originX,
    y: sy - anchor.y * after.scaleY - after.originY,
  };
}

/** Pixels on the segment between two pixels (inclusive), for gap-free brush strokes. */
export function linePixels(a: { r: number; c: number }, b: { r: number; c: number }): Array<{ r: number; c: number }> {
  const out: Array<{ r: number; c: number }> = [];
  let r0 = a.r, c0 = a.c;
  const dr = Math.abs(b.r - r0), dc = Math.abs(b.c - c0);
  const sr = r0 < b.r ? 1 : -1, sc = c0 < b.c ? 1 : -1;
  let err = dc - dr;
  for (;;) {
    out.push({ r: r0, c: c0 });
    if (r0 === b.r && c0 === b.c) break;
    const e2 = 2 * err;
    if (e2 > -dr) { err -= dr; c0 += sc; }
    if (e2 < dc) { err += dc; r0 += sr; }
  }
  return out;
}
