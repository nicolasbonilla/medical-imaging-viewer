/**
 * Client volume = parsed NIfTI + statistics + orientation, plus the safety checks
 * that decide whether the browser may render it (else: server PNG fallback).
 */
import { readNifti, UnsupportedNiftiError, type NiftiVolume } from './nifti';
import { axisCodesFromAffine, describeOrientation, type AxisCodes } from './orientation';
import { computeStats, type IntensityStats } from './windowing';
import {
  buildAnatomicalViews, buildVoxelViews, DISPLAY_CONVENTION,
  type PlaneName, type SliceView,
} from './sliceGeometry';

export interface ClientVolume {
  fileId: string;
  nifti: NiftiVolume;
  stats: IntensityStats;
  /** Axis codes computed in the browser from the affine (null = indeterminate). */
  codes: AxisCodes | null;
  orientation: string;
}

/** The server-side facts the client rendering must agree with. */
export interface ServerImageFacts {
  rows?: number;
  columns?: number;
  slices?: number;
  pixel_spacing?: number[];
  slice_thickness?: number;
  anatomical_orientation?: string;
}

export interface ClientVolumeCheck {
  /** False = must not render client-side (fall back to the server path). */
  renderable: boolean;
  /** True = anatomical axial/coronal/sagittal views may be shown. */
  anatomical: boolean;
  problems: string[];
  notes: string[];
}

const close = (a: number | undefined, b: number, tol = 1e-3) =>
  a == null || !Number.isFinite(a) ? true : Math.abs(a - b) <= tol * Math.max(1, Math.abs(b));

/**
 * Fail-closed agreement check between the browser's reading of the file and the
 * server's metadata for the same file.
 *  - grid or spacing disagreement  -> not renderable (server fallback)
 *  - orientation disagreement, an indeterminate affine, or an Analyze "base" affine
 *    (no sform/qform: orientation would be a convention, not a fact) -> renderable,
 *    but voxel views only: no anatomical plane names, no reorientation.
 */
export function checkClientVolume(vol: ClientVolume, server: ServerImageFacts | null | undefined): ClientVolumeCheck {
  const problems: string[] = [];
  const notes: string[] = [];
  const [n0, n1, n2] = vol.nifti.dims;
  if (server) {
    if (server.rows != null && server.rows !== n0) problems.push(`rows ${server.rows} ≠ ${n0}`);
    if (server.columns != null && server.columns !== n1) problems.push(`columns ${server.columns} ≠ ${n1}`);
    if (server.slices != null && server.slices !== n2) problems.push(`slices ${server.slices} ≠ ${n2}`);
    const ps = server.pixel_spacing;
    if (Array.isArray(ps) && ps.length >= 2) {
      if (!close(ps[0], vol.nifti.zooms[0]) || !close(ps[1], vol.nifti.zooms[1])) {
        problems.push(`pixel spacing ${ps.slice(0, 2).join('×')} ≠ ${vol.nifti.zooms.slice(0, 2).join('×')}`);
      }
    }
    if (!close(server.slice_thickness, vol.nifti.zooms[2])) {
      problems.push(`slice thickness ${server.slice_thickness} ≠ ${vol.nifti.zooms[2]}`);
    }
  }
  if (vol.nifti.volumes > 1) notes.push(`4-D file: showing volume 1 of ${vol.nifti.volumes}`);
  if (vol.stats.nonFiniteCount > 0) notes.push(`${vol.stats.nonFiniteCount} non-finite voxels shown black`);

  let anatomical = vol.codes !== null && vol.nifti.affineSource !== 'base';
  if (vol.nifti.affineSource === 'base') notes.push('no sform/qform in header: orientation not established');
  const serverOrient = server?.anatomical_orientation;
  if (anatomical && serverOrient !== vol.orientation) {
    anatomical = false;
    notes.push(`orientation disagreement (server ${serverOrient ?? 'missing'}, browser ${vol.orientation})`);
  }
  return { renderable: problems.length === 0, anatomical, problems, notes };
}

/** Views the viewer offers for this volume (anatomical only when allowed). */
export function viewsFor(vol: ClientVolume, anatomical: boolean): Record<PlaneName, SliceView> {
  const z = vol.nifti.zooms;
  return anatomical && vol.codes
    ? buildAnatomicalViews(vol.nifti.dims, z, vol.codes, DISPLAY_CONVENTION)
    : buildVoxelViews(vol.nifti.dims, z);
}

/** Parse + analyse a NIfTI buffer (exported for tests and the loader). */
export async function buildClientVolume(fileId: string, buf: ArrayBuffer): Promise<ClientVolume> {
  const nifti = await readNifti(buf);
  // Same codes the server reports (it too falls back to nibabel's base affine);
  // whether they may drive anatomical views is decided in checkClientVolume.
  const codes = axisCodesFromAffine(nifti.affine);
  return { fileId, nifti, stats: computeStats(nifti), codes, orientation: describeOrientation(codes) };
}

// ---- small LRU cache: switching plane / mode / back to an image must not re-download.
const CACHE_SIZE = 3;
const cache = new Map<string, Promise<ClientVolume>>();

export function loadClientVolume(fileId: string, fetchBuffer: (fileId: string) => Promise<ArrayBuffer>): Promise<ClientVolume> {
  const hit = cache.get(fileId);
  if (hit) {
    cache.delete(fileId);
    cache.set(fileId, hit);
    return hit;
  }
  const p = fetchBuffer(fileId).then((buf) => buildClientVolume(fileId, buf));
  p.catch(() => cache.delete(fileId));
  cache.set(fileId, p);
  while (cache.size > CACHE_SIZE) cache.delete(cache.keys().next().value as string);
  return p;
}

export function isUnsupportedNifti(e: unknown): boolean {
  return e instanceof UnsupportedNiftiError;
}
