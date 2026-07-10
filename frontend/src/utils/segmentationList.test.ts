import { describe, it, expect } from 'vitest';
import { buildSegmentationList } from './segmentationList';

const raw = (id: string, description?: string, file_id = 'f1') => ({
  segmentation_id: id,
  file_id,
  metadata: description !== undefined ? { description } : null,
});

describe('buildSegmentationList', () => {
  it('maps raw summaries to viewer items', () => {
    const out = buildSegmentationList([raw('a', 'Lesion A'), raw('b')], 'Default');
    expect(out).toEqual([
      { id: 'a', name: 'Lesion A', status: 'saved', fileId: 'f1' },
      { id: 'b', name: 'Default', status: 'saved', fileId: 'f1' },
    ]);
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
