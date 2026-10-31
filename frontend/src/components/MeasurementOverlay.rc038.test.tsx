/**
 * RC-038 (HAZ-014) — the 2D measurement tools report the real physical size at any zoom
 * and pan, and in the real (possibly anisotropic) pixel spacing.
 *
 * The standard 2D canvas draws the slice with
 *     screen = (image * s0 - centre) * zoom + centre + pan,   s0 = canvas px per image px
 * Before CAPA-010 the measurement overlay converted screen -> image with s0 only, so at
 * zoom 2 a ruler reported twice the true length (an ROI four times the area), and the
 * angle tool worked in pixel units, ignoring the row/column spacing.
 *
 * Rendered for real; the user's clicks are simulated on the overlay. In jsdom the
 * overlay's bounding box is at (0, 0), so a click's client coordinates are overlay px.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import MeasurementOverlay from './MeasurementOverlay';
import { useViewerStore } from '@/store/useViewerStore';

// 100 x 100 image drawn on a 200 x 200 canvas: s0 = 2 canvas px per image px.
const BASE = { imageWidth: 100, imageHeight: 100, canvasWidth: 200, canvasHeight: 200, sliceIndex: 0 };

function drag(svg: Element, points: Array<[number, number]>) {
  const [first, ...rest] = points;
  fireEvent.mouseDown(svg, { clientX: first[0], clientY: first[1] });
  for (const [x, y] of rest) fireEvent.mouseMove(svg, { clientX: x, clientY: y });
  const last = points[points.length - 1];
  fireEvent.mouseUp(svg, { clientX: last[0], clientY: last[1] });
}

beforeEach(() => {
  useViewerStore.setState({ measurementTool: null });
});

describe('RC-038 — measurements are zoom/pan invariant and use the real spacing', () => {
  it('rc038 a ruler at zoom 2 reports the true length, not twice it', () => {
    useViewerStore.setState({ measurementTool: 'ruler' });
    const { container } = render(
      <MeasurementOverlay {...BASE} zoomLevel={2} panOffset={{ x: 0, y: 0 }} pixelSpacing={[1, 1]} />,
    );
    // 40 screen px at zoom 2 and s0 = 2 are 10 image px = 10 mm.
    drag(container.querySelector('svg')!, [[100, 100], [140, 100]]);

    expect(container.querySelector('text')?.textContent).toBe('10.0 mm');
  });

  it('rc038 a ruler measures the same length at zoom 1, zoom 2 and zoom 4 with pan', () => {
    const results: string[] = [];
    for (const [zoom, pan] of [[1, { x: 0, y: 0 }], [2, { x: 30, y: -12 }], [4, { x: -55, y: 20 }]] as const) {
      useViewerStore.setState({ measurementTool: 'ruler' });
      const { container, unmount } = render(
        <MeasurementOverlay {...BASE} zoomLevel={zoom} panOffset={pan} pixelSpacing={[0.5, 0.5]} />,
      );
      // Two image points 6 px apart along a column and 8 px along a row: 10 px = 5 mm.
      const toScreen = (x: number, y: number): [number, number] => [
        100 * (1 - zoom) + pan.x + x * 2 * zoom,
        100 * (1 - zoom) + pan.y + y * 2 * zoom,
      ];
      drag(container.querySelector('svg')!, [toScreen(40, 40), toScreen(48, 46)]);
      results.push(container.querySelector('text')!.textContent!);
      unmount();
    }
    expect(results).toEqual(['5.0 mm', '5.0 mm', '5.0 mm']);
  });

  it('rc038 an elliptical ROI at zoom 2 reports the true area, not four times it', () => {
    useViewerStore.setState({ measurementTool: 'ellipse' });
    const { container } = render(
      <MeasurementOverlay {...BASE} zoomLevel={2} panOffset={{ x: 0, y: 0 }} pixelSpacing={[1, 1]} />,
    );
    // 40 x 20 screen px = 10 x 5 image px = 10 x 5 mm -> pi * 10 * 5 = 157.1 mm2.
    drag(container.querySelector('svg')!, [[100, 100], [140, 120]]);

    expect(container.querySelector('text')?.textContent).toBe('157.1 mm²');
  });

  it('rc038 a ruler stays on the anatomy it measured when the zoom changes', () => {
    useViewerStore.setState({ measurementTool: 'ruler' });
    const props = { ...BASE, panOffset: { x: 0, y: 0 }, pixelSpacing: [1, 1] as [number, number] };
    const { container, rerender } = render(<MeasurementOverlay {...props} zoomLevel={2} />);
    // At zoom 2 these screen points are image points (50, 50) and (60, 50).
    drag(container.querySelector('svg')!, [[100, 100], [140, 100]]);
    useViewerStore.setState({ measurementTool: null });

    // Zoom back to 1: image (60, 50) is drawn at canvas x = 120, so the line must end there.
    rerender(<MeasurementOverlay {...props} zoomLevel={1} />);
    const line = container.querySelector('line')!;
    expect(Number(line.getAttribute('x1'))).toBeCloseTo(100, 6);
    expect(Number(line.getAttribute('x2'))).toBeCloseTo(120, 6);
    expect(container.querySelector('text')?.textContent).toBe('10.0 mm');
  });

  it('rc038 a ruler stays on the anatomy it measured when the image is panned', () => {
    useViewerStore.setState({ measurementTool: 'ruler' });
    const props = { ...BASE, zoomLevel: 2, pixelSpacing: [1, 1] as [number, number] };
    const { container, rerender } = render(<MeasurementOverlay {...props} panOffset={{ x: 30, y: -12 }} />);
    // With pan (30, -12) at zoom 2 these screen points are image points (50, 50) and (60, 50).
    drag(container.querySelector('svg')!, [[130, 88], [170, 88]]);
    useViewerStore.setState({ measurementTool: null });

    // Pan back to (0, 0): the same image points are drawn 30 px left and 12 px lower.
    rerender(<MeasurementOverlay {...props} panOffset={{ x: 0, y: 0 }} />);
    const line = container.querySelector('line')!;
    expect(Number(line.getAttribute('x1'))).toBeCloseTo(100, 6);
    expect(Number(line.getAttribute('y1'))).toBeCloseTo(100, 6);
    expect(Number(line.getAttribute('x2'))).toBeCloseTo(140, 6);
    expect(container.querySelector('text')?.textContent).toBe('10.0 mm');
  });

  it('rc038 the angle is computed in millimetres on anisotropic pixels (2 mm rows, 1 mm columns)', () => {
    useViewerStore.setState({ measurementTool: 'angle' });
    // Canvas = image size (s0 = 1), zoom 1.
    const { container } = render(
      <MeasurementOverlay imageWidth={100} imageHeight={100} canvasWidth={100} canvasHeight={100} sliceIndex={0}
        zoomLevel={1} panOffset={{ x: 0, y: 0 }} pixelSpacing={[2, 1]} />,
    );
    // Arms from the vertex (50, 50): (+10, 0) px and (+10, +10) px. In pixels that is 45 deg;
    // in mm the arms are (10, 0) and (10, 20) -> atan(20 / 10) = 63.4 deg.
    drag(container.querySelector('svg')!, [[60, 50], [50, 50], [60, 60]]);

    expect(container.querySelector('text')?.textContent).toBe('63.4°');
  });
});

/**
 * Non-square image, non-square canvas, anisotropic voxels, zoom 1/2/4 with pan.
 * Square fixtures cannot tell the horizontal from the vertical axis (a centre or a scale
 * taken from the wrong dimension gives the same numbers), so every axis-specific term of
 * the transform is exercised here. s0x = 300/120 = 2.5 and s0y = 160/80 = 2 differ on
 * purpose; rows are 3 mm and columns 0.9 mm.
 */
describe('RC-038 — measurements on a non-square image and canvas with anisotropic voxels', () => {
  const NS = { imageWidth: 120, imageHeight: 80, canvasWidth: 300, canvasHeight: 160, sliceIndex: 0 };
  const SPACING: [number, number] = [3, 0.9]; // [row mm, column mm]
  const ZOOMS = [[1, { x: 0, y: 0 }], [2, { x: 25, y: -15 }], [4, { x: -40, y: 30 }]] as const;
  // Where the standard canvas draws image point (x, y) — useCanvasRendering, per axis.
  const drawnAt = (x: number, y: number, zoom: number, pan: { x: number; y: number }): [number, number] => [
    (x * 2.5 - 150) * zoom + 150 + pan.x,
    (y * 2 - 80) * zoom + 80 + pan.y,
  ];
  const A = [30, 20] as const;
  const B = [70, 50] as const;

  function measure(tool: 'ruler' | 'ellipse' | 'angle', points: Array<readonly [number, number]>, zoom: number, pan: { x: number; y: number }) {
    useViewerStore.setState({ measurementTool: tool });
    const { container, unmount } = render(
      <MeasurementOverlay {...NS} zoomLevel={zoom} panOffset={pan} pixelSpacing={SPACING} />,
    );
    drag(container.querySelector('svg')!, points.map(([x, y]) => drawnAt(x, y, zoom, pan)));
    const label = container.querySelector('text')?.textContent;
    unmount();
    return label;
  }

  it('rc038 non-square: a diagonal ruler reads the same millimetres at zoom 1, 2 and 4', () => {
    // 40 columns x 0.9 mm = 36 mm, 30 rows x 3 mm = 90 mm -> 96.9 mm.
    const labels = ZOOMS.map(([zoom, pan]) => measure('ruler', [A, B], zoom, pan));
    expect(labels).toEqual(['96.9 mm', '96.9 mm', '96.9 mm']);
  });

  it('rc038 non-square: an elliptical ROI reads the same area at zoom 1, 2 and 4', () => {
    // rx = 36 mm, ry = 90 mm -> pi * 36 * 90 = 10178.8 mm2.
    const labels = ZOOMS.map(([zoom, pan]) => measure('ellipse', [A, B], zoom, pan));
    expect(labels).toEqual(['10178.8 mm²', '10178.8 mm²', '10178.8 mm²']);
  });

  it('rc038 non-square: an angle is computed in millimetres at zoom 1, 2 and 4', () => {
    // Vertex (50, 40); arms +30 columns (27 mm) and (+30 columns, +20 rows) = (27, 60) mm
    // -> atan(60 / 27) = 65.8 deg (it would read 33.7 deg in pixel units).
    const labels = ZOOMS.map(([zoom, pan]) => measure('angle', [[80, 40], [50, 40], [80, 60]], zoom, pan));
    expect(labels).toEqual(['65.8°', '65.8°', '65.8°']);
  });

  it('rc038 non-square: a ruler drawn at zoom 2 is redrawn exactly where the canvas draws its end points at zoom 1 and 4', () => {
    useViewerStore.setState({ measurementTool: 'ruler' });
    const [, pan2] = ZOOMS[1];
    const { container, rerender } = render(
      <MeasurementOverlay {...NS} zoomLevel={2} panOffset={pan2} pixelSpacing={SPACING} />,
    );
    drag(container.querySelector('svg')!, [drawnAt(...A, 2, pan2), drawnAt(...B, 2, pan2)]);
    useViewerStore.setState({ measurementTool: null });

    for (const [zoom, pan] of [ZOOMS[0], ZOOMS[2]]) {
      rerender(<MeasurementOverlay {...NS} zoomLevel={zoom} panOffset={pan} pixelSpacing={SPACING} />);
      const line = container.querySelector('line')!;
      const [ax, ay] = drawnAt(...A, zoom, pan);
      const [bx, by] = drawnAt(...B, zoom, pan);
      expect(Number(line.getAttribute('x1'))).toBeCloseTo(ax, 6);
      expect(Number(line.getAttribute('y1'))).toBeCloseTo(ay, 6);
      expect(Number(line.getAttribute('x2'))).toBeCloseTo(bx, 6);
      expect(Number(line.getAttribute('y2'))).toBeCloseTo(by, 6);
      expect(container.querySelector('text')?.textContent).toBe('96.9 mm');
    }
  });
});
