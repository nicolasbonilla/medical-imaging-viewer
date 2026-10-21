// @vitest-environment node
/**
 * RC-048: the in-browser FLAMeS prototype is OFF unless VITE_ENABLE_BROWSER_FLAMES is 'true'/'1', and the card
 * (with ONNX Runtime) is only reachable through that flag.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('BROWSER_FLAMES feature flag', () => {
  it('rc048 is OFF when the variable is not set', async () => {
    vi.stubEnv('VITE_ENABLE_BROWSER_FLAMES', undefined as unknown as string);
    const { FEATURES } = await import('./features');
    expect(FEATURES.BROWSER_FLAMES).toBe(false);
  });

  it('rc048 is OFF for any value other than true/1', async () => {
    vi.stubEnv('VITE_ENABLE_BROWSER_FLAMES', 'yes');
    const { FEATURES } = await import('./features');
    expect(FEATURES.BROWSER_FLAMES).toBe(false);
  });

  it('turns ON only with true', async () => {
    vi.stubEnv('VITE_ENABLE_BROWSER_FLAMES', 'true');
    const { FEATURES } = await import('./features');
    expect(FEATURES.BROWSER_FLAMES).toBe(true);
  });

  it('rc048 the card is rendered only behind the flag and loaded lazily', () => {
    const src = readFileSync(join(__dirname, '..', 'components', 'ClinicalToolsPanel.tsx'), 'utf-8');
    expect(src).toMatch(/const BrowserFlamesCard = React\.lazy\(\(\) => import\('\.\/BrowserFlamesCard'\)\)/);
    expect(src).toMatch(/\{FEATURES\.BROWSER_FLAMES && \(/);
    expect(src.match(/<BrowserFlamesCard /g)?.length).toBe(1);
  });
});
