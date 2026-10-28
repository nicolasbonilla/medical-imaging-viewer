/**
 * Test-only NIfTI-1 writer (PRB-004). Builds a real single-file NIfTI-1 (.nii, optionally
 * gzip-compressed) that the REAL niivue/nifti-reader-js parser reads, so a test can load a
 * volume with a known affine, voxel sizes and display range through niivue's own code.
 *
 * Only the header fields niivue reads are written: dim, datatype/bitpix, pixdim,
 * vox_offset, scl_slope/inter, cal_max/cal_min, descrip, qform/sform codes, srow_x/y/z and
 * the "n+1" magic. The voxel array is in NIfTI storage order (i fastest, then j, then k).
 */
import { gzipSync } from 'fflate';

export interface SyntheticNiftiOptions {
  /** [d0, d1, d2] — storage dimensions (i, j, k). */
  dims: [number, number, number];
  /** 4x4 voxel-to-scanner transform written as the sform (rows). */
  affine: number[][];
  /** Voxel values in storage order (length d0*d1*d2). Default: all zero. */
  data?: Uint8Array;
  /** Header display range (what the MRI-copied header carried in F02). */
  calMin?: number;
  calMax?: number;
  /** Header description (the RC-031 marker lives here). */
  descrip?: string;
  gzip?: boolean;
}

export function syntheticNifti(o: SyntheticNiftiOptions): ArrayBuffer {
  const [d0, d1, d2] = o.dims;
  const nVox = d0 * d1 * d2;
  const data = o.data ?? new Uint8Array(nVox);
  if (data.length !== nVox) throw new Error(`data length ${data.length} != ${nVox}`);

  const voxOffset = 352;
  const buf = new ArrayBuffer(voxOffset + nVox);
  const v = new DataView(buf);
  const le = true;
  v.setInt32(0, 348, le); // sizeof_hdr
  // dim[0..7]
  const dim = [3, d0, d1, d2, 1, 1, 1, 1];
  dim.forEach((x, i) => v.setInt16(40 + 2 * i, x, le));
  v.setInt16(70, 2, le); // datatype DT_UINT8
  v.setInt16(72, 8, le); // bitpix
  // pixdim[0..7]: pixdim[0] = qfac (1); pixdim[1..3] = column norms of the affine
  const norm = (c: number) => Math.hypot(o.affine[0][c], o.affine[1][c], o.affine[2][c]);
  const pixdim = [1, norm(0), norm(1), norm(2), 1, 1, 1, 1];
  pixdim.forEach((x, i) => v.setFloat32(76 + 4 * i, x, le));
  v.setFloat32(108, voxOffset, le); // vox_offset
  v.setFloat32(112, 1, le); // scl_slope
  v.setFloat32(116, 0, le); // scl_inter
  v.setFloat32(124, o.calMax ?? 0, le); // cal_max
  v.setFloat32(128, o.calMin ?? 0, le); // cal_min
  const descrip = (o.descrip ?? '').slice(0, 79);
  for (let i = 0; i < descrip.length; i++) v.setUint8(148 + i, descrip.charCodeAt(i));
  v.setInt16(252, 0, le); // qform_code
  v.setInt16(254, 2, le); // sform_code (aligned)
  for (let c = 0; c < 4; c++) {
    v.setFloat32(280 + 4 * c, o.affine[0][c], le); // srow_x
    v.setFloat32(296 + 4 * c, o.affine[1][c], le); // srow_y
    v.setFloat32(312 + 4 * c, o.affine[2][c], le); // srow_z
  }
  // magic "n+1\0"
  v.setUint8(344, 0x6e); v.setUint8(345, 0x2b); v.setUint8(346, 0x31); v.setUint8(347, 0);
  new Uint8Array(buf, voxOffset).set(data);

  if (!o.gzip) return buf;
  const gz = gzipSync(new Uint8Array(buf));
  return gz.buffer.slice(gz.byteOffset, gz.byteOffset + gz.byteLength) as ArrayBuffer;
}

/** Storage-order index of voxel (i, j, k). */
export function voxelIndex(dims: [number, number, number], i: number, j: number, k: number): number {
  return i + dims[0] * (j + dims[1] * k);
}

/** LAS-like (x flipped), anisotropic, translated — the film data's orientation code. */
export const LAS_AFFINE = [
  [-1, 0, 0, 90],
  [0, 1.2, 0, -126],
  [0, 0, 3, -72],
  [0, 0, 0, 1],
];
