/**
 * Anatomical axis codes from a NIfTI affine — a faithful port of the server's
 * `get_orientation_codes` (backend/app/utils/nifti_utils.py), i.e. nibabel
 * `aff2axcodes(io_orientation(affine))`. RC-023 / HAZ-006.
 *
 * Returns `null` — never a guess — when the affine cannot determine an orientation
 * (non-finite, wrong shape, or |det| of the 3x3 direction block < 1e-8), exactly
 * where the server returns "UNKNOWN".
 *
 * Algorithm (nibabel io_orientation):
 *   1. column-normalise the 3x3 block by the voxel sizes,
 *   2. take its closest orthogonal matrix (polar factor U·Vᵀ of the SVD) — here by
 *      Newton iteration X ← (X + X⁻ᵀ)/2, which converges to the same polar factor,
 *   3. for each voxel axis in order, pick the world axis with the largest |entry|,
 *      record its sign, and remove that world axis from further consideration.
 */
import type { Mat4 } from './nifti';

export type AxisCode = 'R' | 'L' | 'A' | 'P' | 'S' | 'I';
export type AxisCodes = [AxisCode, AxisCode, AxisCode];

const POS: AxisCode[] = ['R', 'A', 'S'];
const NEG: AxisCode[] = ['L', 'P', 'I'];

function det3(m: number[][]): number {
  return (
    m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
    m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
    m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
  );
}

function invTranspose3(m: number[][]): number[][] | null {
  const d = det3(m);
  if (!Number.isFinite(d) || Math.abs(d) < 1e-300) return null;
  // inverse = adj / det ; inverse-transpose = cofactor / det
  const c = [
    [m[1][1] * m[2][2] - m[1][2] * m[2][1], -(m[1][0] * m[2][2] - m[1][2] * m[2][0]), m[1][0] * m[2][1] - m[1][1] * m[2][0]],
    [-(m[0][1] * m[2][2] - m[0][2] * m[2][1]), m[0][0] * m[2][2] - m[0][2] * m[2][0], -(m[0][0] * m[2][1] - m[0][1] * m[2][0])],
    [m[0][1] * m[1][2] - m[0][2] * m[1][1], -(m[0][0] * m[1][2] - m[0][2] * m[1][0]), m[0][0] * m[1][1] - m[0][1] * m[1][0]],
  ];
  return c.map((row) => row.map((v) => v / d));
}

/** Orthogonal polar factor of a non-singular 3x3 matrix (Newton iteration). */
export function polarOrthogonal(m: number[][]): number[][] | null {
  let x = m.map((r) => [...r]);
  for (let it = 0; it < 100; it++) {
    const xit = invTranspose3(x);
    if (!xit) return null;
    let delta = 0;
    const next = x.map((row, r) => row.map((v, c) => {
      const n = 0.5 * (v + xit[r][c]);
      delta = Math.max(delta, Math.abs(n - v));
      return n;
    }));
    x = next;
    if (delta < 1e-15) break;
  }
  return x;
}

/** nibabel aff2axcodes(affine) for a 4x4 affine, or null when indeterminate. */
export function axisCodesFromAffine(affine: Mat4 | null | undefined): AxisCodes | null {
  if (!affine || affine.length !== 4 || affine.some((r) => !Array.isArray(r) || r.length !== 4)) return null;
  if (affine.some((r) => r.some((v) => !Number.isFinite(v)))) return null;
  const dir = [0, 1, 2].map((r) => [0, 1, 2].map((c) => affine[r][c]));
  if (Math.abs(det3(dir)) < 1e-8) return null;

  const zooms = [0, 1, 2].map((c) => Math.sqrt(dir[0][c] ** 2 + dir[1][c] ** 2 + dir[2][c] ** 2) || 1);
  const rs = dir.map((row) => row.map((v, c) => v / zooms[c]));
  const R = polarOrthogonal(rs);
  if (!R) return null;

  const codes: AxisCode[] = [];
  for (let inAx = 0; inAx < 3; inAx++) {
    const col = [R[0][inAx], R[1][inAx], R[2][inAx]];
    if (col.every((v) => Math.abs(v) < 1e-12)) return null;
    let outAx = 0;
    for (let r = 1; r < 3; r++) if (Math.abs(col[r]) > Math.abs(col[outAx])) outAx = r; // first max, like argmax
    codes.push(col[outAx] < 0 ? NEG[outAx] : POS[outAx]);
    for (let c = 0; c < 3; c++) R[outAx][c] = 0; // remove that world axis
  }
  return codes as AxisCodes;
}

/** "LAS"-style string, or "UNKNOWN" (the server's spelling) when indeterminate. */
export function describeOrientation(codes: AxisCodes | null): string {
  return codes ? codes.join('') : 'UNKNOWN';
}

/** World axis (0 = R/L, 1 = A/P, 2 = S/I) and direction (+1 towards R/A/S) of a code. */
export function codeAxis(code: AxisCode): { world: 0 | 1 | 2; sign: 1 | -1 } {
  const p = POS.indexOf(code);
  if (p >= 0) return { world: p as 0 | 1 | 2, sign: 1 };
  return { world: NEG.indexOf(code) as 0 | 1 | 2, sign: -1 };
}
