/**
 * NiiVue LUT (Look-Up Table) builder for multi-label segmentation overlays.
 *
 * NiiVue uses a LUT format where each integer voxel value (0-255) maps to
 * an RGBA color. This allows per-label coloring for MAGNIMS regions,
 * FreeSurfer parcellations, etc.
 *
 * @module utils/niivueLUT
 */

import type { LabelInfo } from '@/types';

/**
 * NiiVue LUT type — matches @niivue/niivue's internal LUT definition.
 * Uint8ClampedArray of length 256*4 (RGBA for each label index 0-255).
 */
export interface NiivueLUT {
  lut: Uint8ClampedArray;
  labels: string[];
}

/**
 * Build a NiiVue LUT from label definitions.
 *
 * @param labels - Array of LabelInfo with id, color, opacity, visible
 * @param labelVisibility - Optional per-label visibility overrides (from Zustand store)
 * @returns NiiVue-compatible LUT object
 */
export function buildLabelLUT(
  labels: LabelInfo[],
  labelVisibility?: Record<number, boolean>
): NiivueLUT {
  const lut = new Uint8ClampedArray(256 * 4);
  const labelNames: string[] = new Array(256).fill('');
  labelNames[0] = 'Background';

  for (const label of labels) {
    if (label.id < 0 || label.id > 255) continue;
    const offset = label.id * 4;

    const hex = label.color.replace('#', '');
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);

    const isVisible = labelVisibility != null
      ? (labelVisibility[label.id] ?? label.visible)
      : label.visible;

    const a = (label.id === 0 || !isVisible)
      ? 0
      : Math.round((label.opacity ?? 0.6) * 255);

    lut[offset] = r;
    lut[offset + 1] = g;
    lut[offset + 2] = b;
    lut[offset + 3] = a;
    labelNames[label.id] = label.name;
  }

  return { lut, labels: labelNames };
}

/**
 * Build a single-color fallback LUT (used when no label definitions are available).
 * All nonzero voxels get the same color.
 */
export function buildSingleColorLUT(
  r: number, g: number, b: number, a: number
): NiivueLUT {
  const lut = new Uint8ClampedArray(256 * 4);
  const labelNames: string[] = new Array(256).fill('');
  labelNames[0] = 'Background';

  // Label 0 = transparent background
  // Labels 1-255 = same color
  for (let i = 1; i < 256; i++) {
    const offset = i * 4;
    lut[offset] = r;
    lut[offset + 1] = g;
    lut[offset + 2] = b;
    lut[offset + 3] = a;
    labelNames[i] = `Label ${i}`;
  }

  return { lut, labels: labelNames };
}
