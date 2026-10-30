/**
 * Release 2026-10-25 — independent review of PR #69, M3: the lesion opacity is kept across sessions (localStorage);
 * an opacity below the visible minimum must not come back silently in a new session (lesions would be undrawn).
 * Written before the correction (fails on dd22708; the visible case is a positive control).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { useSegmentationStore } from '@/store/useSegmentationStore';

function persistedOpacity(value: number) {
  localStorage.setItem('segmentation-store', JSON.stringify({ state: { lesionOpacity: value }, version: 0 }));
}

beforeEach(() => {
  localStorage.clear();
  useSegmentationStore.setState({ lesionOpacity: 0.6 });
});

describe('M3: an invisible lesion opacity does not survive into a new session', () => {
  it('rc071 release m3 a stored opacity of 0 is replaced by the default when the session starts', async () => {
    persistedOpacity(0);
    await useSegmentationStore.persist.rehydrate();
    expect(useSegmentationStore.getState().lesionOpacity).toBe(0.6);
  });

  it('rc071 release m3 a stored opacity below the visible minimum is replaced too', async () => {
    persistedOpacity(0.1);
    await useSegmentationStore.persist.rehydrate();
    expect(useSegmentationStore.getState().lesionOpacity).toBe(0.6);
  });

  it('rc071 release m3 a visible stored opacity is kept (positive control)', async () => {
    persistedOpacity(0.45);
    await useSegmentationStore.persist.rehydrate();
    expect(useSegmentationStore.getState().lesionOpacity).toBe(0.45);
  });
});
