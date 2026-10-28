/**
 * Pure, headless-testable math for the niivue GPU window/level viewer (NiivueViewer2D).
 *
 * Extracted so the DICOM VOI-LUT mapping and slice→depth math can be unit-tested WITHOUT
 * a WebGL/browser context (niivue itself cannot run in jsdom). The component wires these
 * to `vol.cal_min/cal_max` + `nv.scene.crosshairPos`.
 */

export interface CalRange {
  calMin: number;
  calMax: number;
}

/**
 * DICOM linear window/level → niivue cal_min/cal_max.
 *
 * With an active window (windowWidth > 0) the range is the standard VOI-LUT
 * center±width/2. With no active window (width <= 0) we fall back to the volume's own
 * intensity extent (global_min/global_max), and if those are not yet populated, to the
 * current cal range — so we never write `undefined` into the shader.
 *
 * Invariant: when windowWidth > 0, calMin < calMax always (min = C - W/2 < C + W/2), so
 * the mapping can never produce a degenerate cal_min >= cal_max shader state.
 */
export function windowLevelToCalRange(
  windowCenter: number,
  windowWidth: number,
  globalMin: number | undefined,
  globalMax: number | undefined,
  currentMin: number,
  currentMax: number,
): CalRange {
  if (windowWidth > 0) {
    const calMin = windowCenter - windowWidth / 2;
    let calMax = windowCenter + windowWidth / 2;
    // Guard the pathological collapse (huge center + tiny width) where float64 rounds
    // calMax === calMin → a degenerate shader normalization (blank/NaN slice).
    if (calMax <= calMin) calMax = calMin + 1e-6;
    return { calMin, calMax };
  }
  return { calMin: globalMin ?? currentMin, calMax: globalMax ?? currentMax };
}

/**
 * Store slice index → niivue axial crosshair fraction at the CENTRE of that voxel slice:
 * (index + 0.5) / depth, the index clamped to [0, depth − 1]. Null when the volume has no slices
 * (depth < 1) or the depth is not a number.
 *
 * PRB-004: this was index / (depth − 1). niivue reads a fraction f as voxel f · depth − 0.5, so
 * that put most slices between two voxel slices (slice 45 of 182 at 44.75: a blend of slices 44
 * and 45), and slice 0 on the volume's outer edge — not the slice the standard view showed.
 * The GPU view (NiivueViewer2D) lays the volume out as the standard view does (utils/niivueVoxelGrid),
 * so this fraction addresses storage slice `index` itself.
 */
export function sliceIndexToVoxelCentreFraction(index: number, depth: number): number | null {
  if (!Number.isFinite(depth) || depth < 1) return null;
  const n = Math.floor(depth);
  const i = Number.isFinite(index) ? Math.min(n - 1, Math.max(0, Math.round(index))) : 0;
  return (i + 0.5) / n;
}
