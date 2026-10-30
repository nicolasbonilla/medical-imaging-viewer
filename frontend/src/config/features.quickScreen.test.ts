// @vitest-environment node
/**
 * PRB-009: the in-browser "Quick Screen" (normal / abnormal screening of a slice) needs a model file
 * the app does not ship. It is OFF unless VITE_ENABLE_QUICK_SCREEN is 'true' or '1', and the viewer
 * mounts it only behind that flag (with it off nothing of it runs, so nothing is requested).
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('QUICK_SCREEN feature flag', () => {
  it('rc075 is OFF when the variable is not set', async () => {
    vi.stubEnv('VITE_ENABLE_QUICK_SCREEN', undefined as unknown as string);
    const { FEATURES } = await import('./features');
    expect(FEATURES.QUICK_SCREEN).toBe(false);
  });

  it('rc075 is OFF for any value other than true/1', async () => {
    for (const v of ['yes', 'on', 'TRUE ', '0', 'false', '']) {
      vi.resetModules();
      vi.stubEnv('VITE_ENABLE_QUICK_SCREEN', v);
      const { FEATURES } = await import('./features');
      expect(FEATURES.QUICK_SCREEN).toBe(false);
    }
  });

  it('rc075 turns ON only with true or 1', async () => {
    for (const v of ['true', '1']) {
      vi.resetModules();
      vi.stubEnv('VITE_ENABLE_QUICK_SCREEN', v);
      const { FEATURES } = await import('./features');
      expect(FEATURES.QUICK_SCREEN).toBe(true);
    }
  });

  it('rc075 the viewer mounts the badge only behind the flag, in one place', () => {
    const src = readFileSync(join(__dirname, '..', 'components', 'ImageViewer2D.tsx'), 'utf-8');
    expect(src).toMatch(/\{FEATURES\.QUICK_SCREEN && currentSeries\?\.slices\?\.\[currentSliceIndex\]\?\.image_data && \(/);
    expect(src.match(/<QuickScreenBadge\b/g)?.length).toBe(1);
  });

  it('rc075 the production environment file does not switch it on', () => {
    const env = readFileSync(join(__dirname, '..', '..', '.env.production'), 'utf-8');
    expect(env).not.toMatch(/^\s*VITE_ENABLE_QUICK_SCREEN\s*=\s*(true|1)\s*$/m);
  });
});
