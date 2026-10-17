/**
 * The server-equivalent 8-bit PNG of k-plane slice `k` (global min–max, truncation,
 * rows = axis 0, cols = axis 1) built in the browser. Consumers designed around the
 * server's slice PNG — the Edge-AI quick screen — keep receiving bit-identical input
 * (proven by volume/parity.test.ts) without a server round-trip.
 */
import { useMemo } from 'react';
import type { ClientVolume } from '@/volume/clientVolume';
import { buildVoxelViews } from '@/volume/sliceGeometry';
import { parityUint8Slice } from '@/volume/windowing';

export function paritySliceDataUrl(volume: ClientVolume, k: number): string | null {
  const view = buildVoxelViews(volume.nifti.dims, volume.nifti.zooms).axial;
  if (k < 0 || k >= view.depth || typeof document === 'undefined') return null;
  const grey = parityUint8Slice(volume.nifti, view, k, volume.stats);
  const canvas = document.createElement('canvas');
  canvas.width = view.cols;
  canvas.height = view.rows;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const img = ctx.createImageData(view.cols, view.rows);
  for (let p = 0; p < grey.length; p++) {
    const o = p * 4;
    img.data[o] = grey[p]; img.data[o + 1] = grey[p]; img.data[o + 2] = grey[p]; img.data[o + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL('image/png');
}

export function useParitySliceDataUrl(volume: ClientVolume | null, k: number | null): string | null {
  return useMemo(() => (volume && k != null ? paritySliceDataUrl(volume, k) : null), [volume, k]);
}
