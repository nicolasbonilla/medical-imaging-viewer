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
 * Store slice index → niivue axial depth fraction in [0, 0.999], or null when the volume
 * has no navigable depth (depth <= 1 or non-finite). The 0.999 clamp keeps the last slice
 * inside the volume (a bare 1.0 can round past the final voxel plane in niivue).
 */
export function sliceIndexToFraction(index: number, depth: number): number | null {
  if (!Number.isFinite(depth) || depth <= 1) return null;
  const frac = index / (depth - 1);
  if (!Number.isFinite(frac)) return null;
  return Math.min(0.999, Math.max(0, frac));
}
