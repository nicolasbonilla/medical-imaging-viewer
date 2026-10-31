/**
 * PRB-031 (L2) — the zone-map opacity is kept across sessions (localStorage). An opacity above the safe limit (30 %)
 * would come back in a new session and paint the MAGNIMS zones over lesions of the same colour without a word; it is
 * not restored — the default (30 %) is used instead. Written before the correction (fails on ca600c2; the cases at
 * or below the limit are positive controls).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { useSegmentationStore } from '@/store/useSegmentationStore';

function persisted(state: Record<string, unknown>) {
  localStorage.setItem('segmentation-store', JSON.stringify({ state, version: 0 }));
}

beforeEach(() => {
  localStorage.clear();
  useSegmentationStore.setState({ zoneMapOpacity: 0.3, lesionOpacity: 0.6 });
});

describe('PRB-031: a high zone-map opacity does not survive into a new session', () => {
  it.each([1, 0.8, 0.31])('rc093 prb031 a stored zone-map opacity of %s is replaced by the default', async (value) => {
    persisted({ zoneMapOpacity: value });
    await useSegmentationStore.persist.rehydrate();
    expect(useSegmentationStore.getState().zoneMapOpacity).toBe(0.3);
  });

  it.each(['high', null, Number.NaN])('rc093 prb031 a stored zone-map opacity that is not a number (%s) is replaced', async (value) => {
    persisted({ zoneMapOpacity: value });
    await useSegmentationStore.persist.rehydrate();
    expect(useSegmentationStore.getState().zoneMapOpacity).toBe(0.3);
  });

  it.each([0.3, 0.15, 0])('rc093 prb031 a stored zone-map opacity of %s is kept (positive control)', async (value) => {
    persisted({ zoneMapOpacity: value, lesionOpacity: 0.45 });
    await useSegmentationStore.persist.rehydrate();
    expect(useSegmentationStore.getState().zoneMapOpacity).toBe(value);
    expect(useSegmentationStore.getState().lesionOpacity).toBe(0.45);   // the lesion rule is unchanged
  });
});
