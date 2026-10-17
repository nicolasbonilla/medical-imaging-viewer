/**
 * Minimal, dependency-free NIfTI-1 / NIfTI-2 reader for client-side 2D rendering
 * (viewer v3). Class C context: this module decides which voxel value is shown at
 * which position, so it mirrors nibabel — the library the server uses — exactly:
 *
 *  - data layout: Fortran order, voxel (i, j, k) at  i + j*n0 + k*n0*n1
 *  - scaling: nibabel `get_fdata()` semantics — `raw * scl_slope + scl_inter` in
 *    float64, and NO scaling when scl_slope is 0 or not finite
 *  - affine precedence: nibabel `get_best_affine()` — sform if sform_code > 0, else
 *    qform if qform_code > 0, else the Analyze "base" affine (x flipped)
 *  - zooms: pixdim[1..3] as stored (what `header.get_zooms()` returns)
 *
 * Only the FIRST 3-D volume of a 4-D file is read (as the 2D viewer shows one
 * volume). Unsupported encodings (RGB, complex, 64-bit ints) throw
 * `UnsupportedNiftiError` so the caller falls back to the server-rendered path —
 * never a best-effort guess.
 *
 * Parity with the server is proven by `parity.test.ts` against fixtures produced by
 * the backend's own code (scripts/viewer/build_parity_fixture.py).
 */

export type Mat4 = number[][];

export type AffineSource = 'sform' | 'qform' | 'base';

export type VoxelArray =
  | Uint8Array | Int8Array | Int16Array | Uint16Array
  | Int32Array | Uint32Array | Float32Array | Float64Array;

export interface NiftiVolume {
  version: 1 | 2;
  /** Spatial grid [n0, n1, n2] (missing trailing dims are 1). */
  dims: [number, number, number];
  /** Number of volumes along dim 4 (only the first is loaded). */
  volumes: number;
  datatype: number;
  littleEndian: boolean;
  /** Raw stored values of the first volume, Fortran order, platform endianness. */
  raw: VoxelArray;
  /** nibabel scaling; `scaled === false` means value = raw. */
  slope: number;
  inter: number;
  scaled: boolean;
  /** pixdim[1..3] as stored (mm for spatial units). */
  zooms: [number, number, number];
  qformCode: number;
  sformCode: number;
  affine: Mat4;
  affineSource: AffineSource;
  description: string;
}

export class UnsupportedNiftiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'UnsupportedNiftiError';
  }
}

const DT: Record<number, { bytes: number; make: (b: ArrayBuffer) => VoxelArray; name: string }> = {
  2: { bytes: 1, make: (b) => new Uint8Array(b), name: 'uint8' },
  4: { bytes: 2, make: (b) => new Int16Array(b), name: 'int16' },
  8: { bytes: 4, make: (b) => new Int32Array(b), name: 'int32' },
  16: { bytes: 4, make: (b) => new Float32Array(b), name: 'float32' },
  64: { bytes: 8, make: (b) => new Float64Array(b), name: 'float64' },
  256: { bytes: 1, make: (b) => new Int8Array(b), name: 'int8' },
  512: { bytes: 2, make: (b) => new Uint16Array(b), name: 'uint16' },
  768: { bytes: 4, make: (b) => new Uint32Array(b), name: 'uint32' },
};

/** True when the buffer starts with the gzip magic bytes 1f 8b. */
export function isGzip(buf: ArrayBuffer): boolean {
  if (buf.byteLength < 2) return false;
  const b = new Uint8Array(buf, 0, 2);
  return b[0] === 0x1f && b[1] === 0x8b;
}

/** Decompress a gzip buffer with the platform DecompressionStream (no dependency). */
export async function gunzip(buf: ArrayBuffer): Promise<ArrayBuffer> {
  if (typeof DecompressionStream === 'undefined') {
    throw new UnsupportedNiftiError('gzip decompression is not available in this browser');
  }
  const source = new ReadableStream<BufferSource>({
    start(controller) {
      controller.enqueue(new Uint8Array(buf));
      controller.close();
    },
  });
  return new Response(source.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
}

function readString(view: DataView, offset: number, length: number): string {
  let s = '';
  for (let i = 0; i < length; i++) {
    const c = view.getUint8(offset + i);
    if (c === 0) break;
    s += String.fromCharCode(c);
  }
  return s;
}

/** nibabel quaternions.quat2mat. */
function quat2mat(w: number, x: number, y: number, z: number): number[][] {
  const nq = w * w + x * x + y * y + z * z;
  if (nq < Number.EPSILON) return [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  const s = 2.0 / nq;
  const X = x * s, Y = y * s, Z = z * s;
  const wX = w * X, wY = w * Y, wZ = w * Z;
  const xX = x * X, xY = x * Y, xZ = x * Z;
  const yY = y * Y, yZ = y * Z, zZ = z * Z;
  return [
    [1.0 - (yY + zZ), xY - wZ, xZ + wY],
    [xY + wZ, 1.0 - (xX + zZ), yZ - wX],
    [xZ - wY, yZ + wX, 1.0 - (xX + yY)],
  ];
}

interface RawHeader {
  version: 1 | 2;
  littleEndian: boolean;
  dim: number[];
  datatype: number;
  pixdim: number[];
  voxOffset: number;
  slope: number;
  inter: number;
  qformCode: number;
  sformCode: number;
  quatern: [number, number, number];
  qoffset: [number, number, number];
  srow: number[][];
  description: string;
  headerSize: number;
}

function readHeader(buf: ArrayBuffer): RawHeader {
  if (buf.byteLength < 348) throw new UnsupportedNiftiError('file too small to be NIfTI');
  const view = new DataView(buf);
  const le1 = view.getInt32(0, true);
  const be1 = view.getInt32(0, false);
  let version: 1 | 2;
  let littleEndian: boolean;
  if (le1 === 348) { version = 1; littleEndian = true; }
  else if (be1 === 348) { version = 1; littleEndian = false; }
  else if (le1 === 540) { version = 2; littleEndian = true; }
  else if (be1 === 540) { version = 2; littleEndian = false; }
  else throw new UnsupportedNiftiError('not a NIfTI-1/2 file (bad sizeof_hdr)');
  const le = littleEndian;

  if (version === 1) {
    const magic = readString(view, 344, 4);
    if (magic !== 'n+1') {
      throw new UnsupportedNiftiError(`unsupported NIfTI-1 magic "${magic}" (single-file n+1 required)`);
    }
    const dim = Array.from({ length: 8 }, (_, i) => view.getInt16(40 + 2 * i, le));
    const pixdim = Array.from({ length: 8 }, (_, i) => view.getFloat32(76 + 4 * i, le));
    return {
      version, littleEndian, dim, pixdim,
      datatype: view.getInt16(70, le),
      voxOffset: view.getFloat32(108, le),
      slope: view.getFloat32(112, le),
      inter: view.getFloat32(116, le),
      qformCode: view.getInt16(252, le),
      sformCode: view.getInt16(254, le),
      quatern: [view.getFloat32(256, le), view.getFloat32(260, le), view.getFloat32(264, le)],
      qoffset: [view.getFloat32(268, le), view.getFloat32(272, le), view.getFloat32(276, le)],
      srow: [0, 1, 2].map((r) => [0, 1, 2, 3].map((c) => view.getFloat32(280 + 16 * r + 4 * c, le))),
      description: readString(view, 148, 80),
      headerSize: 348,
    };
  }
  if (buf.byteLength < 540) throw new UnsupportedNiftiError('truncated NIfTI-2 header');
  const magic = readString(view, 4, 4);
  if (magic !== 'n+2') throw new UnsupportedNiftiError(`unsupported NIfTI-2 magic "${magic}"`);
  const i64 = (o: number) => Number(view.getBigInt64(o, le));
  const dim = Array.from({ length: 8 }, (_, i) => i64(16 + 8 * i));
  const pixdim = Array.from({ length: 8 }, (_, i) => view.getFloat64(104 + 8 * i, le));
  return {
    version, littleEndian, dim, pixdim,
    datatype: view.getInt16(12, le),
    voxOffset: i64(168),
    slope: view.getFloat64(176, le),
    inter: view.getFloat64(184, le),
    qformCode: view.getInt32(344, le),
    sformCode: view.getInt32(348, le),
    quatern: [view.getFloat64(352, le), view.getFloat64(360, le), view.getFloat64(368, le)],
    qoffset: [view.getFloat64(376, le), view.getFloat64(384, le), view.getFloat64(392, le)],
    srow: [0, 1, 2].map((r) => [0, 1, 2, 3].map((c) => view.getFloat64(400 + 32 * r + 8 * c, le))),
    description: readString(view, 240, 80),
    headerSize: 540,
  };
}

/** nibabel Nifti1Header.get_qform (non-strict: qfac outside ±1 is taken as 1). */
function qformAffine(h: RawHeader): Mat4 {
  const [b, c, d] = h.quatern;
  const w2 = 1 - (b * b + c * c + d * d);
  const a = w2 < 0 ? 0 : Math.sqrt(w2);
  const R = quat2mat(a, b, c, d);
  const qfac = h.pixdim[0] === -1 ? -1 : 1;
  const vox = [h.pixdim[1], h.pixdim[2], h.pixdim[3] * qfac];
  const out: Mat4 = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 1]];
  for (let r = 0; r < 3; r++) {
    for (let col = 0; col < 3; col++) out[r][col] = R[r][col] * vox[col];
    out[r][3] = h.qoffset[r];
  }
  return out;
}

/** nibabel shape_zoom_affine(shape, zooms, x_flip=True) — the Analyze fallback. */
function baseAffine(dims: [number, number, number], zooms: [number, number, number]): Mat4 {
  const z = [-zooms[0], zooms[1], zooms[2]];
  const out: Mat4 = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 1]];
  for (let r = 0; r < 3; r++) {
    out[r][r] = z[r];
    out[r][3] = -((dims[r] - 1) / 2) * z[r];
  }
  return out;
}

function swapBytes(bytes: Uint8Array, width: number): void {
  if (width === 1) return;
  for (let i = 0; i < bytes.length; i += width) {
    for (let a = i, b = i + width - 1; a < b; a++, b--) {
      const t = bytes[a]; bytes[a] = bytes[b]; bytes[b] = t;
    }
  }
}

/**
 * Parse an (already decompressed) single-file NIfTI-1/2 buffer.
 * @throws UnsupportedNiftiError for anything the client must not guess about.
 */
export function parseNifti(buf: ArrayBuffer): NiftiVolume {
  const h = readHeader(buf);
  const ndim = h.dim[0];
  if (!(ndim >= 1 && ndim <= 7)) throw new UnsupportedNiftiError(`invalid dim[0]=${ndim}`);
  const d = (i: number) => (i <= ndim && h.dim[i] > 0 ? h.dim[i] : 1);
  const dims: [number, number, number] = [d(1), d(2), d(3)];
  const volumes = d(4) * d(5) * d(6) * d(7);
  const dt = DT[h.datatype];
  if (!dt) throw new UnsupportedNiftiError(`unsupported NIfTI datatype code ${h.datatype}`);
  const nvox = dims[0] * dims[1] * dims[2];
  const nbytes = nvox * dt.bytes;
  // Single-file minimum (header + 4-byte extension flag), as nibabel's check_fix enforces.
  const offset = Math.max(Math.floor(h.voxOffset), h.headerSize + 4);
  if (offset + nbytes > buf.byteLength) {
    throw new UnsupportedNiftiError(`truncated NIfTI data (${buf.byteLength - offset} of ${nbytes} bytes)`);
  }
  // Copy into a fresh, aligned buffer (typed-array alignment + endianness swap).
  const copy = buf.slice(offset, offset + nbytes);
  if (!h.littleEndian) swapBytes(new Uint8Array(copy), dt.bytes);
  const raw = dt.make(copy);

  const scaled = h.slope !== 0 && Number.isFinite(h.slope) && !(h.slope === 1 && h.inter === 0);
  if (scaled && !Number.isFinite(h.inter)) {
    throw new UnsupportedNiftiError('valid scl_slope with an invalid scl_inter');
  }
  const zooms: [number, number, number] = [h.pixdim[1], h.pixdim[2], h.pixdim[3]];
  let affine: Mat4;
  let affineSource: AffineSource;
  if (h.sformCode > 0) {
    affine = [...h.srow.map((r) => [...r]), [0, 0, 0, 1]];
    affineSource = 'sform';
  } else if (h.qformCode > 0) {
    affine = qformAffine(h);
    affineSource = 'qform';
  } else {
    affine = baseAffine(dims, zooms);
    affineSource = 'base';
  }
  return {
    version: h.version,
    dims,
    volumes,
    datatype: h.datatype,
    littleEndian: h.littleEndian,
    raw,
    slope: scaled ? h.slope : 1,
    inter: scaled ? h.inter : 0,
    scaled,
    zooms,
    qformCode: h.qformCode,
    sformCode: h.sformCode,
    affine,
    affineSource,
    description: h.description,
  };
}

/** Decompress if needed, then parse. */
export async function readNifti(buf: ArrayBuffer): Promise<NiftiVolume> {
  return parseNifti(isGzip(buf) ? await gunzip(buf) : buf);
}

/** Fortran-order linear index of voxel (i, j, k). */
export function voxelIndex(dims: readonly [number, number, number], i: number, j: number, k: number): number {
  return i + dims[0] * (j + dims[1] * k);
}

/** Scaled (physical) value at a linear index — nibabel get_fdata semantics, float64. */
export function valueAtIndex(vol: NiftiVolume, idx: number): number {
  const v = vol.raw[idx];
  return vol.scaled ? v * vol.slope + vol.inter : v;
}

/** Scaled value at voxel (i, j, k). */
export function valueAt(vol: NiftiVolume, i: number, j: number, k: number): number {
  return valueAtIndex(vol, voxelIndex(vol.dims, i, j, k));
}

/** World (scanner mm) coordinate of a voxel centre through the affine. */
export function voxelToWorld(affine: Mat4, i: number, j: number, k: number): [number, number, number] {
  return [0, 1, 2].map((r) => affine[r][0] * i + affine[r][1] * j + affine[r][2] * k + affine[r][3]) as [number, number, number];
}

export function datatypeName(code: number): string {
  return DT[code]?.name ?? `code ${code}`;
}
