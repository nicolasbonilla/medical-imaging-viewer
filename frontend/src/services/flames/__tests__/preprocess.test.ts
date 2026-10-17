// @vitest-environment node
/**
 * Preprocessing math of the in-browser FLAMeS port vs nnU-Net v2 itself.
 * Expected values: research/flames_in_browser/make_fixtures.py (nnunetv2 2.8.1, scipy, skimage).
 */
import { describe, expect, it } from 'vitest';
import fx from './fixtures/nnunet_reference.json';
import {
  anisotropicAxis,
  boundingBox,
  computeNewShape,
  cropTo,
  nonzeroMaskFilled,
  resampleToShape,
  roundHalfEven,
  uncrop,
  zscoreInMask,
  type Shape3,
} from '../preprocess';

const F = fx as any;

function maxAbs(a: ArrayLike<number>, b: number[]): number {
  expect(a.length).toBe(b.length);
  let worst = 0;
  for (let i = 0; i < b.length; i++) worst = Math.max(worst, Math.abs(a[i] - b[i]));
  return worst;
}

describe('rounding', () => {
  it('matches Python round() / numpy.round (half to even)', () => {
    expect([0.5, 1.5, 2.5, 3.5, -0.5, -1.5, 2.4999, 2.5001, 28.5, 29.5].map(roundHalfEven)).toEqual([
      0, 2, 2, 4, 0, -2, 2, 3, 28, 30,
    ]);
  });
});

describe('compute_new_shape', () => {
  for (const c of F.new_shape) {
    it(`${c.shape} @ ${c.spacing} -> ${c.new_spacing}`, () => {
      expect(computeNewShape(c.shape, c.spacing, c.new_spacing)).toEqual(c.expected);
    });
  }
});

describe('crop_to_nonzero (create_nonzero_mask + binary_fill_holes + bbox)', () => {
  it('fills enclosed cavities, keeps border-connected ones, same bbox', () => {
    const c = F.crop;
    const shape = c.shape as Shape3;
    const mask = nonzeroMaskFilled(Float32Array.from(c.input), shape);
    expect(Array.from(mask)).toEqual(c.nonzero_filled);
    const box = boundingBox(mask, shape);
    expect([0, 1, 2].map((a) => [box.lo[a], box.hi[a]])).toEqual(c.bbox);
    const cropped = cropTo(Float32Array.from(c.input), shape, box);
    const restored = uncrop(cropped, shape, box);
    expect(Array.from(restored)).toEqual(c.input);
  });

  it('throws on an empty image (fail closed)', () => {
    expect(() => boundingBox(new Uint8Array(8), [2, 2, 2])).toThrow(/empty/);
  });
});

describe('ZScoreNormalization(use_mask_for_norm=True)', () => {
  it('matches nnU-Net', () => {
    const c = F.zscore;
    const { image, stats } = zscoreInMask(Float32Array.from(c.input), Uint8Array.from(c.mask));
    expect(maxAbs(image, c.expected)).toBeLessThan(2e-5);
    expect(stats.count).toBe(c.mask.reduce((s: number, v: number) => s + v, 0));
  });
});

describe('anisotropy decision (get_do_separate_z / get_lowres_axis)', () => {
  it('needs max/min > 3 and a single coarsest axis', () => {
    expect(anisotropicAxis([1, 3, 1])).toBeNull();
    expect(anisotropicAxis([1, 3.01, 1])).toBe(1);
    expect(anisotropicAxis([5, 1, 1.1])).toBe(0);
    expect(anisotropicAxis([4, 4, 1])).toBeNull();
    expect(anisotropicAxis([1, 0.9, 0.9])).toBeNull();
  });
});

describe('resample_data_or_seg_to_shape (is_seg=False)', () => {
  for (const c of F.resample) {
    it(`${c.name} (order ${c.order})`, () => {
      const out = resampleToShape(Float32Array.from(c.input), c.shape, c.new_shape, c.spacing, c.new_spacing, c.order);
      // float32 storage between axes vs float64 in skimage: allow 1e-5 absolute on unit-scale data
      expect(maxAbs(out, c.expected)).toBeLessThan(1e-5);
    });
  }
});
