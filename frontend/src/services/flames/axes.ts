/**
 * Axis-order conversions between the three layouts the in-browser FLAMeS path touches.
 * Getting these wrong is hazard HAZ-006 (mask drawn in the wrong place), so every
 * mapping is spelled out and unit-tested on asymmetric synthetic volumes.
 *
 * Let the NIfTI axes be (i, j, k) with sizes (nx, ny, nz) = (dim[1], dim[2], dim[3]).
 *
 *  1. NIfTI storage order ("nifti"):   flat = i + nx * (j + ny * k)
 *     (what readNifti returns; what nibabel calls img[i, j, k]).
 *
 *  2. nnU-Net network order ("network"): C-order array of shape (nx, nz, ny), indices (i, k, j):
 *     flat = (i * nz + k) * ny + j
 *     SimpleITK gives (k, j, i); FLAMeS plans.transpose_forward [2, 0, 1] makes it (i, k, j).
 *
 *  3. MSTool-AI segmentation order ("app", RC-031): C-order (depth, height, width) =
 *     (nz, nx, ny), indices (k, i, j): flat = (k * nx + i) * ny + j.
 *     This is the backend's  m = img.transpose(2, 0, 1)  (segmentation_service
 *     _nifti_native_to_internal, RC031-ORIENT-V2) and the frontend's
 *     useSegmentationMask index  sliceIndex * H * W + row * W + col  with
 *     sliceIndex = k, row = i, col = j  (initEmptyMask(slices=dim3, rows=dim1, columns=dim2)).
 */

export type Dims3 = readonly [number, number, number];

type AnyTyped = Float32Array | Uint8Array | Int32Array | Float64Array;

function alloc<T extends AnyTyped>(like: T, n: number): T {
  return new (like.constructor as { new (n: number): T })(n);
}

/** Network-order shape (nx, nz, ny) for NIfTI dims (nx, ny, nz). */
export function networkShape(dims: Dims3): [number, number, number] {
  return [dims[0], dims[2], dims[1]];
}

/** App-order shape (depth, height, width) = (nz, nx, ny) for NIfTI dims (nx, ny, nz). */
export function appShape(dims: Dims3): { depth: number; height: number; width: number } {
  return { depth: dims[2], height: dims[0], width: dims[1] };
}

/** NIfTI spacing (sx, sy, sz) -> network-order spacing (sx, sz, sy). */
export function networkSpacing(spacing: Dims3): [number, number, number] {
  return [spacing[0], spacing[2], spacing[1]];
}

export function niftiToNetwork<T extends AnyTyped>(data: T, dims: Dims3): T {
  const [nx, ny, nz] = dims;
  const out = alloc(data, data.length);
  for (let k = 0; k < nz; k++) {
    for (let j = 0; j < ny; j++) {
      const src = nx * (j + ny * k);
      for (let i = 0; i < nx; i++) out[(i * nz + k) * ny + j] = data[src + i];
    }
  }
  return out;
}

export function networkToNifti<T extends AnyTyped>(data: T, dims: Dims3): T {
  const [nx, ny, nz] = dims;
  const out = alloc(data, data.length);
  for (let k = 0; k < nz; k++) {
    for (let j = 0; j < ny; j++) {
      const dst = nx * (j + ny * k);
      for (let i = 0; i < nx; i++) out[dst + i] = data[(i * nz + k) * ny + j];
    }
  }
  return out;
}

export function networkToApp<T extends AnyTyped>(data: T, dims: Dims3): T {
  const [nx, ny, nz] = dims;
  const out = alloc(data, data.length);
  for (let i = 0; i < nx; i++) {
    for (let k = 0; k < nz; k++) {
      const src = (i * nz + k) * ny;
      const dst = (k * nx + i) * ny;
      for (let j = 0; j < ny; j++) out[dst + j] = data[src + j];
    }
  }
  return out;
}

export function niftiToApp<T extends AnyTyped>(data: T, dims: Dims3): T {
  const [nx, ny, nz] = dims;
  const out = alloc(data, data.length);
  for (let k = 0; k < nz; k++) {
    for (let j = 0; j < ny; j++) {
      const src = nx * (j + ny * k);
      for (let i = 0; i < nx; i++) out[(k * nx + i) * ny + j] = data[src + i];
    }
  }
  return out;
}
