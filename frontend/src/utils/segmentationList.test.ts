import { describe, it, expect } from 'vitest';
import { buildSegmentationList, classifySegOrigin } from './segmentationList';

const raw = (id: string, description?: string, file_id = 'f1') => ({
  segmentation_id: id,
  file_id,
  metadata: description !== undefined ? { description } : null,
});

describe('buildSegmentationList', () => {
  it('maps raw summaries to viewer items (with provenance origin)', () => {
    const out = buildSegmentationList([raw('a', 'Lesion A'), raw('b')], 'Default');
    expect(out).toEqual([
      { id: 'a', name: 'Lesion A', status: 'saved', fileId: 'f1', origin: 'manual' },
      { id: 'b', name: 'Default', status: 'saved', fileId: 'f1', origin: 'manual' },
    ]);
  });

  it('derives origin from validation_source when present', () => {
    const out = buildSegmentationList(
      [{ segmentation_id: 'x', file_id: 'f1', metadata: { description: 'Auto seg', validation_source: 'flames-v1.0' } }],
      'Default',
    );
    expect(out[0].origin).toBe('ai');
  });

  it('uses defaultName when description is missing or empty', () => {
    expect(buildSegmentationList([raw('a', '')], 'Fallback')[0].name).toBe('Fallback');
    expect(buildSegmentationList([raw('a')], 'Fallback')[0].name).toBe('Fallback');
  });

  it('dedupes MAGNIMS Zone Map, keeping the first', () => {
    const out = buildSegmentationList(
      [raw('z1', 'MAGNIMS Zone Map'), raw('les', 'Lesion'), raw('z2', 'MAGNIMS Zone Map')],
      'Default',
    );
    expect(out.map((s) => s.id)).toEqual(['z1', 'les']);
  });

  it('handles null / undefined / empty input', () => {
    expect(buildSegmentationList(null, 'D')).toEqual([]);
    expect(buildSegmentationList(undefined, 'D')).toEqual([]);
    expect(buildSegmentationList([], 'D')).toEqual([]);
  });
});

describe('classifySegOrigin (Class C provenance)', () => {
  it('flags the legacy over-segmenter "Output Mask" as ai-legacy', () => {
    expect(classifySegOrigin('Output Mask')).toBe('ai-legacy');
    expect(classifySegOrigin('output mask (thesis)')).toBe('ai-legacy');
  });

  it('classifies human expert ground truth', () => {
    expect(classifySegOrigin('Expert Rater')).toBe('expert');
    expect(classifySegOrigin('anything', 'expert')).toBe('expert');
  });

  it('classifies validated auto-segmenters from validation_source or name', () => {
    expect(classifySegOrigin('Auto seg', 'flames-v1.0')).toBe('ai');
    expect(classifySegOrigin('Auto seg', 'lst-ai-v1.0.3')).toBe('ai');
    expect(classifySegOrigin('Auto seg', 'synthseg-v2.0')).toBe('ai');
    expect(classifySegOrigin('FLAMeS automated MS lesion segmentation')).toBe('ai');
    expect(classifySegOrigin('LST-AI automated segmentation')).toBe('ai');
  });

  it('treats hand-drawn / manual as manual, and the zone map as zonemap', () => {
    expect(classifySegOrigin('My lesion tracing')).toBe('manual');
    expect(classifySegOrigin('Seg', 'manual')).toBe('manual');
    expect(classifySegOrigin('Seg', 'custom-edt')).toBe('manual');
    expect(classifySegOrigin('MAGNIMS Zone Map')).toBe('zonemap');
  });

  it('prioritises the legacy flag even if validation_source looks automatic', () => {
    // A legacy "Output Mask" must never be mistaken for a validated tool.
    expect(classifySegOrigin('Output Mask', 'flames-v1.0')).toBe('ai-legacy');
  });
});
