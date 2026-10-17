/**
 * Minimal, dependency-free NIfTI-1 reader for the in-browser FLAMeS prototype.
 *
 * Scope (deliberately narrow — anything else FAILS CLOSED with a readable error):
 *  - single-file NIfTI-1 ('n+1'), optionally gzip-compressed (.nii / .nii.gz)
 *  - 3D scalar volumes (dim[0] == 3, or dim[0] == 4 with dim[4] == 1)
 *  - datatypes uint8, int8, int16, uint16, int32, uint32, float32, float64
 *  - either byte order
 *
 * Voxel data is returned in the file's own storage order (i fastest, then j, then k),
 * as float32 with scl_slope / scl_inter applied (as SimpleITK, which nnU-Net uses,
 * and nibabel's get_fdata() do). No reorientation is ever performed: FLAMeS'
 * nnU-Net never reorients either (DESIGN.md §3.1).
 *
 * Spacing is taken from pixdim[1..3] (what SimpleITK and nibabel report).
 */

export interface NiftiVolume {
  /** dims of the NIfTI axes i, j, k (dim[1], dim[2], dim[3]) */
  dims: [number, number, number];
  /** pixdim[1..3] in mm */
  spacing: [number, number, number];
  /** 4x4 voxel->world (sform if sform_code>0, else qform if qform_code>0, else pixdim diagonal) */
  affine: number[][];
  /** voxels in storage order: index = i + nx * (j + ny * k) */
  data: Float32Array;
  datatype: number;
  sformCode: number;
  qformCode: number;
}

/** Hard ceiling so a malformed or huge file cannot exhaust the tab (DESIGN.md §7). */
export const MAX_NIFTI_VOXELS = 96 * 1024 * 1024;

const GZIP_MAGIC_0 = 0x1f;
const GZIP_MAGIC_1 = 0x8b;

export function isGzip(bytes: Uint8Array): boolean {
  return bytes.length > 2 && bytes[0] === GZIP_MAGIC_0 && bytes[1] === GZIP_MAGIC_1;
}

/** Gunzip with the platform DecompressionStream (browsers, Web Workers, Node >= 18). */
export async function gunzip(bytes: Uint8Array): Promise<Uint8Array> {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('This browser cannot decompress .nii.gz files (DecompressionStream missing).');
  }
  const stream = new Blob([bytes as Uint8Array<ArrayBuffer>]).stream().pipeThrough(new DecompressionStream('gzip'));
  const buffer = await new Response(stream).arrayBuffer();
  return new Uint8Array(buffer);
}

interface DatatypeInfo {
  bytes: number;
  read: (view: DataView, offset: number, little: boolean) => number;
}

const DATATYPES: Record<number, DatatypeInfo> = {
  2: { bytes: 1, read: (v, o) => v.getUint8(o) },
  256: { bytes: 1, read: (v, o) => v.getInt8(o) },
  4: { bytes: 2, read: (v, o, le) => v.getInt16(o, le) },
  512: { bytes: 2, read: (v, o, le) => v.getUint16(o, le) },
  8: { bytes: 4, read: (v, o, le) => v.getInt32(o, le) },
  768: { bytes: 4, read: (v, o, le) => v.getUint32(o, le) },
  16: { bytes: 4, read: (v, o, le) => v.getFloat32(o, le) },
  64: { bytes: 8, read: (v, o, le) => v.getFloat64(o, le) },
};

function quaternionAffine(view: DataView, le: boolean, pixdim: number[]): number[][] {
  const b = view.getFloat32(256, le);
  const c = view.getFloat32(260, le);
  const d = view.getFloat32(264, le);
  const qx = view.getFloat32(268, le);
  const qy = view.getFloat32(272, le);
  const qz = view.getFloat32(276, le);
  let a = 1 - (b * b + c * c + d * d);
  a = a < 1e-7 ? 0 : Math.sqrt(a);
  const qfac = pixdim[0] < 0 ? -1 : 1;
  const [dx, dy, dz] = [pixdim[1], pixdim[2], pixdim[3] * qfac];
  const r = [
    [a * a + b * b - c * c - d * d, 2 * (b * c - a * d), 2 * (b * d + a * c)],
    [2 * (b * c + a * d), a * a + c * c - b * b - d * d, 2 * (c * d - a * b)],
    [2 * (b * d - a * c), 2 * (c * d + a * b), a * a + d * d - c * c - b * b],
  ];
  return [
    [r[0][0] * dx, r[0][1] * dy, r[0][2] * dz, qx],
    [r[1][0] * dx, r[1][1] * dy, r[1][2] * dz, qy],
    [r[2][0] * dx, r[2][1] * dy, r[2][2] * dz, qz],
    [0, 0, 0, 1],
  ];
}

/** Parse NIfTI-1 bytes (gzip or raw). Throws a descriptive Error on anything unsupported. */
export async function readNifti(input: ArrayBuffer | Uint8Array): Promise<NiftiVolume> {
  let bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  if (isGzip(bytes)) bytes = await gunzip(bytes);
  return parseNifti(bytes);
}

/** Synchronous parse of already-decompressed NIfTI-1 bytes. */
export function parseNifti(bytes: Uint8Array): NiftiVolume {
  if (bytes.byteLength < 352) throw new Error('Not a NIfTI-1 file: shorter than its 348-byte header.');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let le = true;
  const sizeLE = view.getInt32(0, true);
  if (sizeLE !== 348) {
    if (view.getInt32(0, false) === 348) le = false;
    else if (sizeLE === 540 || view.getInt32(0, false) === 540) {
      throw new Error('NIfTI-2 files are not supported by the in-browser segmenter.');
    } else {
      throw new Error('Not a NIfTI-1 file (sizeof_hdr != 348).');
    }
  }
  const magic = String.fromCharCode(view.getUint8(344), view.getUint8(345), view.getUint8(346));
  if (magic !== 'n+1') {
    throw new Error(`Unsupported NIfTI magic "${magic}": only single-file .nii/.nii.gz is supported.`);
  }
  const dim: number[] = [];
  for (let n = 0; n < 8; n++) dim.push(view.getInt16(40 + 2 * n, le));
  const ndim = dim[0];
  if (ndim < 3 || ndim > 7) throw new Error(`Expected a 3D image, got dim[0] = ${ndim}.`);
  for (let n = 4; n <= ndim; n++) {
    if (dim[n] > 1) throw new Error(`Expected a single 3D volume, got dim[${n}] = ${dim[n]} (4D/5D not supported).`);
  }
  const dims: [number, number, number] = [dim[1], dim[2], dim[3]];
  if (dims.some((d) => !Number.isInteger(d) || d < 1)) throw new Error(`Invalid NIfTI dimensions ${dims.join('x')}.`);
  const voxels = dims[0] * dims[1] * dims[2];
  if (voxels > MAX_NIFTI_VOXELS) {
    throw new Error(`Volume too large for in-browser segmentation (${voxels} voxels > ${MAX_NIFTI_VOXELS}).`);
  }
  const datatype = view.getInt16(70, le);
  const info = DATATYPES[datatype];
  if (!info) throw new Error(`Unsupported NIfTI datatype ${datatype}.`);
  const pixdim: number[] = [];
  for (let n = 0; n < 8; n++) pixdim.push(view.getFloat32(76 + 4 * n, le));
  const spacing: [number, number, number] = [pixdim[1], pixdim[2], pixdim[3]];
  if (spacing.some((s) => !Number.isFinite(s) || s <= 0)) {
    throw new Error(`Invalid voxel spacing ${spacing.join(' x ')} mm.`);
  }
  const voxOffset = Math.round(view.getFloat32(108, le));
  const slope = view.getFloat32(112, le);
  const inter = view.getFloat32(116, le);
  const qformCode = view.getInt16(252, le);
  const sformCode = view.getInt16(254, le);

  let affine: number[][];
  if (sformCode > 0) {
    affine = [0, 1, 2].map((r) => [0, 1, 2, 3].map((c) => view.getFloat32(280 + 16 * r + 4 * c, le)));
    affine.push([0, 0, 0, 1]);
  } else if (qformCode > 0) {
    affine = quaternionAffine(view, le, pixdim);
  } else {
    affine = [
      [spacing[0], 0, 0, 0],
      [0, spacing[1], 0, 0],
      [0, 0, spacing[2], 0],
      [0, 0, 0, 1],
    ];
  }

  const needed = voxOffset + voxels * info.bytes;
  if (voxOffset < 348 || bytes.byteLength < needed) {
    throw new Error(`Truncated NIfTI: expected at least ${needed} bytes, got ${bytes.byteLength}.`);
  }
  const data = new Float32Array(voxels);
  const applyScale = Number.isFinite(slope) && slope !== 0 && !(slope === 1 && inter === 0);
  const s = applyScale ? slope : 1;
  const b = applyScale && Number.isFinite(inter) ? inter : 0;
  if (datatype === 16 && le && (bytes.byteOffset + voxOffset) % 4 === 0 && !applyScale) {
    data.set(new Float32Array(bytes.buffer, bytes.byteOffset + voxOffset, voxels));
  } else {
    for (let n = 0, o = voxOffset; n < voxels; n++, o += info.bytes) data[n] = info.read(view, o, le) * s + b;
  }
  for (let n = 0; n < voxels; n++) {
    if (!Number.isFinite(data[n])) throw new Error('The FLAIR contains non-finite voxel values (NaN/Inf).');
  }
  return { dims, spacing, affine, data, datatype, sformCode, qformCode };
}
