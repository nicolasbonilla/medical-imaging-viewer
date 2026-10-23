// @vitest-environment node
/**
 * CP-SLICE-THICKNESS-001 (DRAFT, PENDING owner approval) — pure logic of the
 * "reliability by slice thickness" card.
 *
 *  - RC-055: the thickness comes only from a strictly parsed `acquisition_geometry`, of the
 *    segmentation's own image (or the single original FLAIR of a processed image); anything
 *    else is "not determinable"; the thicker source wins.
 *  - RC-056: no false-lesion figure, at any thickness; an asset carrying a site calibration
 *    is refused.
 *  - RC-057: detection figures only from the versioned asset, equal to Paper A v0.3 Table 4 /
 *    spec section 3; the "found 8 in 10" size is the worst case over the band's evidence.
 *    Asset v2 (2026-10-23, independent review of PR #59): only the pre-registered thickness
 *    bands of the Paper A v0.3 protocol; post-hoc rows are refused.
 *
 * Negative controls: scripts/safety/slice_thickness_negative_controls.py.
 */
import { describe, expect, it } from 'vitest';
import {
  ASSET,
  assessReliability,
  locateSource,
  parseGeometry,
  resolveThickness,
  smallestBinFrom,
  validateAsset,
  type ParsedGeometry,
  type ReliabilityAsset,
  type Resolution,
} from './sliceThicknessReliability';

const native = (mm: number): ParsedGeometry => ({ state: 'native', mm, reason: null });
const atLeast = (mm: number): ParsedGeometry => ({ state: 'at_least', mm, reason: null });
const nd = (reason: string): ParsedGeometry => ({ state: 'not_determinable', mm: null, reason });

const viewOf = (res: Resolution) => assessReliability(res);
const nativeBand = (mm: number) => viewOf({ kind: 'band', basis: 'native', mm, file: 'f', viaOriginal: false });
const lowerBand = (mm: number) => viewOf({ kind: 'band', basis: 'at_least', mm, file: 'f', viaOriginal: false });

const PROC = 'patients/p/studies/s/series/a/proc.gz';
const ORIG = 'patients/p/studies/s/series/b/orig.gz';
const instances = [
  { gcs_object_name: PROC, original_filename: 'sub-01_ses-01_desc-preproc_FLAIR.nii.gz' },
  { gcs_object_name: ORIG, original_filename: 'sub-01_ses-01_FLAIR.nii.gz' },
  { gcs_object_name: 'patients/p/studies/s/series/c/t1.gz', original_filename: 'sub-01_ses-01_T1w.nii.gz' },
];

function resolveFor(sourceFileId: string, list: typeof instances, own: ParsedGeometry, original: ParsedGeometry | null) {
  const loc = locateSource(sourceFileId, list);
  return resolveThickness({ own, ownFilename: loc.ownFilename, ownIsProcessed: loc.ownIsProcessed, original: loc.original, originalGeometry: original });
}

// ─── RC-055 ────────────────────────────────────────────────────────────────────────────

describe('RC-055 — thickness read strictly, from the right image, never guessed', () => {
  it('rc055 a native value is accepted only from a DICOM header', () => {
    expect(parseGeometry({ state: 'native', effective_mm: 5, source: 'dicom_header' })).toEqual(native(5));
    expect(parseGeometry({ state: 'native', effective_mm: 1, source: 'nifti_grid' }).state).toBe('not_determinable');
    expect(parseGeometry({ state: 'native', effective_mm: 1 }).state).toBe('not_determinable');
  });

  it('rc055 the legacy slice_thickness (1.0 mm by default) is never read', () => {
    // A metadata object of an old response: slice_thickness present, no acquisition_geometry.
    const legacyMetadata = { slice_thickness: 1.0, pixel_spacing: [1, 1] } as Record<string, unknown>;
    expect(parseGeometry(legacyMetadata.acquisition_geometry)).toEqual(nd('malformed'));
    expect(parseGeometry({ slice_thickness: 1.0 })).toEqual(nd('malformed'));
    expect(parseGeometry(null)).toEqual(nd('malformed'));
  });

  it('rc055 a lower bound at or below 1.5 mm says nothing and is rejected', () => {
    expect(parseGeometry({ state: 'at_least', effective_mm: 1.5, source: 'nifti_grid' }).state).toBe('not_determinable');
    expect(parseGeometry({ state: 'at_least', effective_mm: 1.6, source: 'nifti_grid' })).toEqual(atLeast(1.6));
  });

  it('rc055 implausible, non-numeric or non-finite values are rejected, not clipped', () => {
    for (const v of [0, -5, Number.NaN, Number.POSITIVE_INFINITY, 25, '5', undefined]) {
      expect(parseGeometry({ state: 'native', effective_mm: v, source: 'dicom_header' }).state).toBe('not_determinable');
      expect(parseGeometry({ state: 'at_least', effective_mm: v, source: 'nifti_grid' }).state).toBe('not_determinable');
    }
  });

  it('rc055 an unknown state or an unknown reason is not determinable', () => {
    expect(parseGeometry({ state: 'thin', effective_mm: 1, source: 'dicom_header' })).toEqual(nd('malformed'));
    expect(parseGeometry({ state: 'not_determinable', reason: 'whatever' })).toEqual(nd('unreadable'));
    expect(parseGeometry({ state: 'not_determinable', reason: 'template_grid' })).toEqual(nd('template_grid'));
  });

  it('rc055 an original image uses only its own geometry, never another image of the study', () => {
    const list = [
      { gcs_object_name: ORIG, original_filename: 'sub-01_FLAIR.nii.gz' },
      { gcs_object_name: 'x/other.gz', original_filename: 'sub-01_acq-3D_FLAIR.nii.gz' },
    ];
    const loc = locateSource(ORIG, list);
    expect(loc.ownIsProcessed).toBe(false);
    expect(loc.original).toEqual({ kind: 'not_needed' });
    const res = resolveThickness({ own: nd('fine_grid_no_acquisition_metadata'), ownFilename: loc.ownFilename, ownIsProcessed: false, original: loc.original, originalGeometry: native(1) });
    expect(res).toEqual({ kind: 'not_determinable', reasons: ['fine_grid_no_acquisition_metadata'] });
  });

  it('rc055 a processed image reads the single original FLAIR of the study, named', () => {
    const loc = locateSource(PROC, instances);
    expect(loc.ownIsProcessed).toBe(true);
    expect(loc.original).toEqual({ kind: 'found', fileId: ORIG, filename: 'sub-01_ses-01_FLAIR.nii.gz' });
    const res = resolveFor(PROC, instances, nd('template_grid'), native(6));
    expect(res).toEqual({ kind: 'band', basis: 'native', mm: 6, file: 'sub-01_ses-01_FLAIR.nii.gz', viaOriginal: true });
  });

  it('rc055 a processed image with no original FLAIR, or with several, is not determinable', () => {
    const none = instances.filter((i) => i.gcs_object_name !== ORIG);
    expect(resolveFor(PROC, none, nd('template_grid'), null)).toEqual({ kind: 'not_determinable', reasons: ['template_grid', 'original_missing'] });
    const two = [...instances, { gcs_object_name: 'x/flair2.gz', original_filename: 'sub-01_ses-01_run-2_FLAIR.nii.gz' }];
    expect(locateSource(PROC, two).original).toEqual({ kind: 'ambiguous', count: 2 });
    expect(resolveFor(PROC, two, nd('template_grid'), native(1))).toEqual({ kind: 'not_determinable', reasons: ['template_grid', 'original_ambiguous'] });
  });

  it('rc055 a mask whose name contains FLAIR is not taken for the original image', () => {
    const list = [
      instances[0],
      { gcs_object_name: 'x/mask.gz', original_filename: 'sub-01_FLAIR_lesion_mask.nii.gz' },
      { gcs_object_name: 'x/seg.gz', original_filename: 'sub-01_FLAIR_seg.nii.gz' },
    ];
    expect(locateSource(PROC, list).original).toEqual({ kind: 'missing' });
  });

  it('rc055 the thicker source wins; a thin value never hides a thicker one', () => {
    // processed image on a 5-mm grid, original says 1 mm native -> the analysed image is coarser
    expect(resolveFor(PROC, instances, atLeast(5), native(1))).toMatchObject({ basis: 'at_least', mm: 5, viaOriginal: false });
    // original only a lower bound
    expect(resolveFor(PROC, instances, nd('template_grid'), atLeast(6))).toMatchObject({ basis: 'at_least', mm: 6, viaOriginal: true });
    // native thicker than the processed grid's bound -> native
    expect(resolveFor(PROC, instances, atLeast(2), native(3))).toMatchObject({ basis: 'native', mm: 3, viaOriginal: true });
  });

  it('rc055 an MSLesSeg-like 1-mm image is never reported as thin', () => {
    // Acquired at 2-5 mm, delivered resampled to MNI 1 mm: the grid alone is "not determinable".
    const res = resolveFor(PROC, instances.filter((i) => i.gcs_object_name !== ORIG), nd('template_grid'), null);
    const view = viewOf(res);
    expect(view.kind).toBe('not_determinable');
    expect(view.thick).toBe(true);
    expect(view.bands).toEqual([]);
    expect(view.reliableBin).toBeNull();
  });

  it('rc055 no source image -> not determinable', () => {
    const loc = locateSource(undefined, instances);
    const res = resolveThickness({ own: nd('no_source_image'), ownFilename: loc.ownFilename, ownIsProcessed: loc.ownIsProcessed, original: loc.original, originalGeometry: null });
    expect(res).toEqual({ kind: 'not_determinable', reasons: ['no_source_image'] });
  });
});

// ─── RC-056 ────────────────────────────────────────────────────────────────────────────

describe('RC-056 — no false-lesion figure without a site calibration (none exists)', () => {
  it('rc056 no state, band or lower bound ever shows a false-lesion figure', () => {
    const views = [
      ...[0.5, 1, 1.5, 2, 3, 4, 5, 6.5, 8, 20].map(nativeBand),
      ...[1.6, 3, 5, 7, 20].map(lowerBand),
      viewOf({ kind: 'not_determinable', reasons: ['missing'] }),
    ];
    for (const v of views) expect(v.falseLesionFigure.shown).toBe(false);
  });

  it('rc056 thick or unknown thickness gives the "not reliable at this thickness" reason', () => {
    expect(nativeBand(5).falseLesionFigure.reason).toBe('thick_or_unknown');
    expect(nativeBand(1.6).falseLesionFigure.reason).toBe('thick_or_unknown');
    expect(lowerBand(1.6).falseLesionFigure.reason).toBe('thick_or_unknown');
    expect(viewOf({ kind: 'not_determinable', reasons: ['missing'] }).falseLesionFigure.reason).toBe('thick_or_unknown');
    expect(nativeBand(1.5).falseLesionFigure.reason).toBe('no_calibration_for_deployed_segmenter');
  });

  it('rc056 an asset carrying a site calibration is refused (no figures at all)', () => {
    const withCalibration = {
      ...ASSET,
      false_lesion_figure: { ...ASSET.false_lesion_figure, site_calibration: { patients: 12, segmenter: 'FLAMeS-ens5' } },
    } as ReliabilityAsset;
    expect(validateAsset(withCalibration).length).toBeGreaterThan(0);
    const v = assessReliability({ kind: 'band', basis: 'native', mm: 5, file: 'f', viaOriginal: false }, withCalibration);
    expect(v.kind).toBe('unavailable');
    expect(v.rows).toEqual([]);
    const shown = { ...ASSET, false_lesion_figure: { ...ASSET.false_lesion_figure, shown: true } } as ReliabilityAsset;
    expect(validateAsset(shown).length).toBeGreaterThan(0);
  });

  it('rc056 the shipped asset has no calibration, a >= 10-patient rule and no false-lesion numbers', () => {
    expect(ASSET.false_lesion_figure.shown).toBe(false);
    expect(ASSET.false_lesion_figure.site_calibration).toBeNull();
    expect(ASSET.false_lesion_figure.min_site_calibration_patients).toBeGreaterThanOrEqual(10);
    for (const lang of ['en', 'es', 'de'] as const) {
      const msgs = ASSET.messages[lang] as Record<string, unknown>;
      for (const key of ['false_lesion', 'false_lesion_thick', 'false_lesion_thin']) {
        expect(String(msgs[key])).not.toMatch(/\d\s*%|percent|por ciento|prozent/i);
      }
    }
  });
});

// ─── RC-057 ────────────────────────────────────────────────────────────────────────────

describe('RC-057 — detection figures from the versioned asset, worst case', () => {
  it('rc057 the shipped asset is structurally valid and every reason has a message in en/es/de', () => {
    expect(validateAsset(ASSET)).toEqual([]);
    const reasons = Object.keys(ASSET.messages.en.reasons).sort();
    for (const lang of ['es', 'de'] as const) expect(Object.keys(ASSET.messages[lang].reasons).sort()).toEqual(reasons);
    const keys = Object.keys(ASSET.messages.en).sort();
    for (const lang of ['es', 'de'] as const) expect(Object.keys(ASSET.messages[lang]).sort()).toEqual(keys);
  });

  it('rc057 the asset is bound to its source record (PR #54, commit, SHA-256 of each record)', () => {
    expect(ASSET.asset_version).toBe('2.0.0');
    expect(ASSET.source.pull_request).toBe(54);
    expect(ASSET.source.commit).toMatch(/^[0-9a-f]{40}$/);
    // Only the pre-registered record; the post-hoc MSLesSeg stratification stays in the research record.
    expect(ASSET.source.records).toHaveLength(1);
    for (const r of ASSET.source.records) {
      expect(r.sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(r.post_hoc).toBe(false);
    }
    expect(Object.keys(ASSET.evidence_rows).sort()).toEqual(['B1_grid', 'B2', 'B3', 'B4']);
    for (const row of Object.values(ASSET.evidence_rows)) expect(row.post_hoc).toBe(false);
  });

  it('rc057 only the pre-registered bands of the protocol (B1 <= 1.5, B2 (1.5, 4.5], B3 (4.5, 6.5], B4 > 6.5 mm)', () => {
    expect(ASSET.bands.map((b) => [b.id, b.min_mm, b.max_mm, b.rows])).toEqual([
      ['B1', 0, 1.5, ['B1_grid']],
      ['B2', 1.5, 4.5, ['B2']],
      ['B3', 4.5, 6.5, ['B3']],
      ['B4', 6.5, 20, ['B4']],
    ]);
  });

  it('rc057 an asset carrying a post-hoc evidence row or record is refused (no figures at all)', () => {
    const withPostHoc = {
      ...ASSET,
      evidence_rows: { ...ASSET.evidence_rows, MSL_2: { ...ASSET.evidence_rows.B2, post_hoc: true } },
      bands: ASSET.bands.map((b) => (b.id === 'B2' ? { ...b, rows: ['MSL_2'] } : b)),
    } as ReliabilityAsset;
    expect(validateAsset(withPostHoc).length).toBeGreaterThan(0);
    expect(assessReliability({ kind: 'band', basis: 'native', mm: 2, file: 'f', viaOriginal: false }, withPostHoc).kind).toBe('unavailable');
    const postHocRecord = { ...ASSET, source: { ...ASSET.source, records: [{ ...ASSET.source.records[0], post_hoc: true }] } } as ReliabilityAsset;
    expect(validateAsset(postHocRecord).length).toBeGreaterThan(0);
  });

  it('rc057 a natively 2 mm study is not told "8 in 10 from 50 mm3" (post-hoc row): no size, as pre-registered', () => {
    const v = nativeBand(2.0);
    expect(v.bands.map((b) => b.id)).toEqual(['B2']);
    expect(v.rows).toEqual(['B2']);
    expect(v.reliableBin).toBeNull();
    expect(v.halfBin).toBe(1);
  });

  it('rc057 the asset reproduces the paper (spec section 3, rounded %)', () => {
    const pct = (id: string) => ASSET.evidence_rows[id].detection.map((d) => Math.round(d * 100));
    expect(pct('B1_grid')).toEqual([36, 72, 81, 87, 90]);
    expect(pct('B2')).toEqual([37, 67, 76, 77, 80]);
    expect(pct('B3')).toEqual([13, 45, 59, 66, 76]);
    expect(pct('B4')).toEqual([21, 43, 69, 72, 70]);
    const ev = (id: string) => [ASSET.evidence_rows[id].scans, ASSET.evidence_rows[id].patients];
    expect(ev('B1_grid')).toEqual([125, 85]);
    expect(ev('B2')).toEqual([28, 9]);
    expect(ev('B3')).toEqual([76, 76]);
    expect(ev('B4')).toEqual([75, 75]);
  });

  it('rc057 "from this size" requires the bin and every larger bin', () => {
    expect(smallestBinFrom([0.36, 0.72, 0.81, 0.87, 0.9], 0.8)).toBe(2);
    expect(smallestBinFrom([0.16, 0.39, 0.73, 0.82, 0.71], 0.8)).toBeNull(); // 150-500 ok, >=500 not
    expect(smallestBinFrom([0.37, 0.67, 0.76, 0.77, 0.7957], 0.8)).toBeNull(); // PediMS misses 0.8 by 0.004
    expect(smallestBinFrom([0.9, 0.1, 0.9, 0.9, 0.9], 0.8)).toBe(2);
  });

  it('rc057 smallest sizes per band equal the paper and are the worst case over the band', () => {
    const at = (mm: number) => {
      const v = nativeBand(mm);
      return [v.bands.map((b) => b.id).join(','), v.reliableBin, v.halfBin];
    };
    expect(at(1.0)).toEqual(['B1', 2, 1]); //  >= 50 mm3 (8 in 10), >= 14 mm3 (half)
    expect(at(2.0)).toEqual(['B2', null, 1]); // PediMS: no size 8 in 10, half from 14 mm3
    expect(at(3.0)).toEqual(['B2', null, 1]);
    expect(at(3.9)).toEqual(['B2', null, 1]);
    expect(at(5.0)).toEqual(['B3', null, 2]);
    expect(at(7.2)).toEqual(['B4', null, 2]);
  });

  it('rc057 band edges: 1.5 is thin, anything above is thick', () => {
    const ids = (mm: number) => nativeBand(mm).bands.map((b) => b.id);
    expect(ids(1.5)).toEqual(['B1']);
    expect(ids(1.51)).toEqual(['B2']);
    expect(ids(4.5)).toEqual(['B2']);
    expect(ids(4.51)).toEqual(['B3']);
    expect(ids(6.5)).toEqual(['B3']);
    expect(ids(6.51)).toEqual(['B4']);
    expect(ids(20)).toEqual(['B4']);
    expect(nativeBand(1.5).thick).toBe(false);
    expect(nativeBand(1.51).thick).toBe(true);
  });

  it('rc057 a lower bound uses its band and every thicker band', () => {
    const v = lowerBand(2.0);
    expect(v.bands.map((b) => b.id)).toEqual(['B2', 'B3', 'B4']);
    expect(v.reliableBin).toBeNull();
    expect(v.halfBin).toBe(2);
    expect(v.thick).toBe(true);
    expect(lowerBand(6.0).bands.map((b) => b.id)).toEqual(['B3', 'B4']);
    expect(lowerBand(6.0).rows).toEqual(['B3', 'B4']);
  });

  it('rc057 not determinable shows no band and no figure', () => {
    const v = viewOf({ kind: 'not_determinable', reasons: ['missing'] });
    expect(v).toMatchObject({ kind: 'not_determinable', thick: true, bands: [], rows: [], reliableBin: null, halfBin: null, mm: null });
  });
});
