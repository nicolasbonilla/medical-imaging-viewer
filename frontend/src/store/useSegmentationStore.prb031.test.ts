/**
 * PRB-031 (L2) — the zone-map opacity is kept across sessions (localStorage). An opacity above the safe limit (30 %)
 * would come back in a new session and paint the MAGNIMS zones over lesions of the same colour without a word; it is
 * not restored — the default (30 %) is used instead. Written before the correction (fails on ca600c2; the cases at
 * or below the limit are positive controls). The cases are listed inside each test (the risk-control manifest gate
 * reads a plain `it('rc093 …')` test name).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { useSegmentationStore } from '@/store/useSegmentationStore';

function persisted(state: Record<string, unknown>) {
  localStorage.setItem('segmentation-store', JSON.stringify({ state, version: 0 }));
}

async function restoredZoneOpacity(state: Record<string, unknown>) {
  localStorage.clear();
  useSegmentationStore.setState({ zoneMapOpacity: 0.3, lesionOpacity: 0.6 });
  persisted(state);
  await useSegmentationStore.persist.rehydrate();
  return useSegmentationStore.getState().zoneMapOpacity;
}

beforeEach(() => {
  localStorage.clear();
  useSegmentationStore.setState({ zoneMapOpacity: 0.3, lesionOpacity: 0.6 });
});

describe('PRB-031: a high zone-map opacity does not survive into a new session', () => {
  it('rc093 prb031 a stored zone-map opacity above 30 % is replaced by the default', async () => {
    for (const value of [1, 0.8, 0.31]) {
      expect(await restoredZoneOpacity({ zoneMapOpacity: value }), String(value)).toBe(0.3);
    }
  });

  it('rc093 prb031 a stored zone-map opacity that is not a number is replaced by the default', async () => {
    for (const value of ['high', null, Number.NaN]) {
      expect(await restoredZoneOpacity({ zoneMapOpacity: value }), String(value)).toBe(0.3);
    }
  });

  it('rc093 prb031 a stored zone-map opacity at or below 30 % is kept (positive control)', async () => {
    for (const value of [0.3, 0.15, 0]) {
      expect(await restoredZoneOpacity({ zoneMapOpacity: value, lesionOpacity: 0.45 }), String(value)).toBe(value);
      expect(useSegmentationStore.getState().lesionOpacity).toBe(0.45);   // the lesion rule is unchanged
    }
  });
});
