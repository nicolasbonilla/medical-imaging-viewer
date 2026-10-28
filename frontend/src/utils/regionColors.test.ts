// @vitest-environment node
/**
 * PRB-010 — ONE colour mapping for the MAGNIMS regions (utils/regionColors.ts), used by the lesion
 * legend, the zone-map legend, the label preset and every overlay. What reaches the screen is tested in
 * components/SegmentationCanvasLocal.prb010.test.tsx; these pin the mapping and its single source.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';
import * as regionColors from './regionColors';
import { MAGNIMS_REGION_PALETTE, MAGNIMS_REGIONS, regionHex, withRegionColors } from './regionColors';
import { MAGNIMS_LESION_LABELS, DEFAULT_LABEL_PRESETS } from '@/types';
import { maskLabelColormap } from './maskLabelColormap';

const src = (p: string) => readFileSync(join(__dirname, '..', p), 'utf-8');

describe('PRB-010 — one MAGNIMS region colour mapping', () => {
  it('rc076 the mapping is the Okabe-Ito legend mapping, by region and by label value', () => {
    expect(Object.fromEntries(MAGNIMS_REGIONS.map((r) => [r, MAGNIMS_REGION_PALETTE[r].hex]))).toEqual({
      Periventricular: '#E69F00',
      Juxtacortical: '#56B4E9',
      Infratentorial: '#009E73',
      'Deep White Matter': '#D55E00',   // vermillion (review m1: reddish purple sat 5.3 from bluish green, deutan, as drawn)
    });
    expect([1, 2, 3, 4].map((v) => regionHex(v))).toEqual(['#E69F00', '#56B4E9', '#009E73', '#D55E00']);
  });

  it('rc076 R5: ONE colour for mask values missing from the label table: cyan, used by the GPU / 3D colormap, no label preset uses it', () => {
    const fallback = (regionColors as Record<string, unknown>).UNLABELLED_FALLBACK_COLOR;
    expect(fallback).toBe('#00FFFF');
    const cm = maskLabelColormap([{ id: 1, name: 'Lesion', color: '#FF0000' }])!;
    const at = (v: number) => {
      const t = Math.max(0, Math.min(255, Math.round(((v - cm.cal_min) / (cm.cal_max - cm.cal_min)) * 255)));
      return `#${[cm.colormap.R[t], cm.colormap.G[t], cm.colormap.B[t]].map((c) => c.toString(16).padStart(2, '0')).join('').toUpperCase()}`;
    };
    expect(at(2)).toBe(fallback);   // a value the table does not list
    for (const labels of Object.values(DEFAULT_LABEL_PRESETS)) {
      for (const l of labels) expect(l.color.toUpperCase(), `${l.name}`).not.toBe(fallback);
    }
    // one definition: the colormap module holds no colour literal of its own for it
    expect(src('utils/maskLabelColormap.ts')).not.toMatch(/#00FFFF/i);
  });

  it('rc076 each legend dot class carries exactly the mapping colour', () => {
    for (const r of MAGNIMS_REGIONS) expect(MAGNIMS_REGION_PALETTE[r].dot).toBe(`bg-[${MAGNIMS_REGION_PALETTE[r].hex}]`);
  });

  it('rc076 the MAGNIMS label preset uses the mapping', () => {
    for (const r of MAGNIMS_REGIONS) {
      expect(MAGNIMS_LESION_LABELS.find((l) => l.name === r)?.color).toBe(MAGNIMS_REGION_PALETTE[r].hex);
    }
  });

  it('rc076 region labels stored with other colours are shown in the mapping; other labels untouched', () => {
    const shown = withRegionColors([
      { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
      { id: 2, name: 'juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
      { id: 5, name: 'Active (Gd+)', color: '#FF00FF', opacity: 0.6, visible: true },
    ]);
    expect(shown.map((l) => l.color)).toEqual(['#E69F00', '#56B4E9', '#FF00FF']);
  });

  it('rc076 the lesion legend and the zone-map legend take their colours from the mapping, not their own', () => {
    for (const file of ['components/LesionDashboard.tsx', 'components/MAGNIMSZoneMapPanel.tsx']) {
      const s = src(file);
      expect(s).toMatch(/from '@\/utils\/regionColors'/);
      const block = s.slice(s.indexOf('const REGION_COLORS'), s.indexOf('const REGION_COLORS') + 400);
      expect(block).not.toMatch(/#[0-9A-Fa-f]{6}|bg-(red|green|blue|yellow)-/);
    }
  });

  it('rc076 the overlays and the 3D zone colormap carry no region colour of their own', () => {
    for (const file of ['components/SegmentationCanvasLocal.tsx', 'components/ImageViewer3D.tsx']) {
      const s = src(file);
      expect(s).toMatch(/from '@\/utils\/regionColors'/);
      expect(s).not.toMatch(/r: 255, g: 0,\s+b: 0|g: 204, b: 0|R\[i\] = 255; A\[i\] = 255|G\[i\] = 204/);
    }
  });
});
