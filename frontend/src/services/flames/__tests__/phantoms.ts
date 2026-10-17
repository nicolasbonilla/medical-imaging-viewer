/**
 * Synthetic head/brain phantoms for the input-gate tests (no patient data, deterministic).
 *
 * Ellipsoidal brain at 1.5 mm: a 1 mm outer CSF layer, a 3 mm cortical ribbon, white matter inside,
 * central ventricles. Tissue intensities per contrast follow the physics the FLAIR gate relies on:
 *   FLAIR: CSF dark, cortex brighter than white matter;  T1: CSF dark, white matter brighter than cortex;
 *   T2: CSF brightest, cortex brighter than white matter.
 * Optional smooth bias field and an optional skull (background zero): bright scalp fat, or a signal-free bone shell.
 */
import type { Dims3 } from '../axes';

export type PhantomContrast = 'FLAIR' | 'T1' | 'T2';

const LEVELS: Record<PhantomContrast, { csf: number; cortex: number; wm: number }> = {
  FLAIR: { csf: 15, cortex: 115, wm: 100 },
  T1: { csf: 25, cortex: 65, wm: 100 },
  T2: { csf: 260, cortex: 120, wm: 100 },
};

export interface PhantomOptions {
  contrast: PhantomContrast;
  /** multiply by (1 + bias * x / radius) along i: a smooth left-right intensity ramp */
  bias?: number;
  /** multiply by (1 + centreBias * (1 - rho^2)): centre brighter than the edge (3 T receive-field shading) */
  centreBias?: number;
  /**
   * keep a skull: 'fat' = intermediate bone + bright scalp fat (as on the public raw FLAIRs),
   * 'dark' = signal-free bone + dim scalp. Background stays zero in both.
   */
  skull?: 'fat' | 'dark';
  spacing?: number;
}

export function makePhantom(opts: PhantomOptions): { data: Float32Array; dims: Dims3; spacing: Dims3 } {
  const sp = opts.spacing ?? 1.5;
  const brainR = [62, 72, 56]; // mm
  const headPad = opts.skull ? 14 : 0; // mm of skull + scalp
  const margin = 6; // mm of zero background
  const dims = brainR.map((r) => Math.ceil((2 * (r + headPad + margin)) / sp)) as unknown as Dims3;
  const [nx, ny, nz] = dims;
  const L = LEVELS[opts.contrast];
  const data = new Float32Array(nx * ny * nz);
  let seed = 12345;
  const noise = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return (seed / 0x7fffffff - 0.5) * 4; // +-2 intensity units
  };
  for (let k = 0; k < nz; k++)
    for (let j = 0; j < ny; j++)
      for (let i = 0; i < nx; i++) {
        const x = (i + 0.5) * sp - nx * sp * 0.5;
        const y = (j + 0.5) * sp - ny * sp * 0.5;
        const z = (k + 0.5) * sp - nz * sp * 0.5;
        // normalised radius of the brain ellipsoid, and depth (mm, approximate) below its surface
        const rho = Math.sqrt((x / brainR[0]) ** 2 + (y / brainR[1]) ** 2 + (z / brainR[2]) ** 2);
        const depth = (1 - rho) * Math.min(...brainR);
        let v = 0;
        if (rho <= 1) {
          if (depth < 1) v = L.csf; // subarachnoid CSF
          else if (depth < 4) v = L.cortex; // cortical ribbon (3 mm)
          else v = L.wm;
          const vent = Math.sqrt((x / 14) ** 2 + (y / 22) ** 2 + (z / 10) ** 2);
          if (vent <= 1) v = L.csf;
          v += noise();
        } else if (opts.skull && -depth < headPad) {
          const out = -depth; // mm outside the brain surface
          if (opts.skull === 'fat') v = out < 9 ? 40 + noise() : 180 + noise(); // bone/marrow, then scalp fat
          else v = out < 9 ? 3 + Math.abs(noise()) : 130 + noise(); // signal-free bone, then dim scalp
        }
        if (v !== 0 && opts.bias) v *= 1 + (opts.bias * x) / brainR[0];
        if (v !== 0 && opts.centreBias) v *= 1 + opts.centreBias * Math.max(0, 1 - rho * rho);
        data[i + nx * (j + ny * k)] = v;
      }
  return { data, dims, spacing: [sp, sp, sp] };
}
