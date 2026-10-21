// @vitest-environment node
/**
 * RC-058 (CP-SLICE-THICKNESS-001, DRAFT, PENDING owner approval): the "reliability by slice
 * thickness" card is OFF unless VITE_ENABLE_SLICE_THICKNESS_RELIABILITY is 'true' or '1', is
 * reachable only through that flag, and is loaded lazily so that nothing of it (component,
 * logic, evidence asset) is fetched while the flag is OFF.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

const SRC = join(__dirname, '..');

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return sourceFiles(p);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name) ? [p] : [];
  });
}

describe('SLICE_THICKNESS_RELIABILITY feature flag', () => {
  it('rc058 is OFF when the variable is not set', async () => {
    vi.stubEnv('VITE_ENABLE_SLICE_THICKNESS_RELIABILITY', undefined as unknown as string);
    const { FEATURES } = await import('./features');
    expect(FEATURES.SLICE_THICKNESS_RELIABILITY).toBe(false);
  });

  it('rc058 is OFF for any value other than true/1', async () => {
    for (const v of ['yes', 'on', 'TRUE ', '0', 'false', '']) {
      vi.resetModules();
      vi.stubEnv('VITE_ENABLE_SLICE_THICKNESS_RELIABILITY', v);
      const { FEATURES } = await import('./features');
      expect(FEATURES.SLICE_THICKNESS_RELIABILITY).toBe(false);
    }
  });

  it('turns ON only with true or 1', async () => {
    for (const v of ['true', '1']) {
      vi.resetModules();
      vi.stubEnv('VITE_ENABLE_SLICE_THICKNESS_RELIABILITY', v);
      const { FEATURES } = await import('./features');
      expect(FEATURES.SLICE_THICKNESS_RELIABILITY).toBe(true);
    }
  });

  it('rc058 the card is rendered only behind the flag and loaded lazily', () => {
    const src = readFileSync(join(SRC, 'components', 'LesionDashboard.tsx'), 'utf-8');
    expect(src).toMatch(/const SliceThicknessReliabilityCard = lazy\(\(\) => import\('\.\/SliceThicknessReliabilityCard'\)\)/);
    expect(src).toMatch(/\{FEATURES\.SLICE_THICKNESS_RELIABILITY && \(\s*<Suspense fallback=\{null\}>\s*<SliceThicknessReliabilityCard /);
    expect(src.match(/<SliceThicknessReliabilityCard /g)?.length).toBe(1);
  });

  it('rc058 nothing else imports the card, its logic or its evidence asset (stays in the lazy chunk)', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(SRC)) {
      const rel = relative(SRC, file).replace(/\\/g, '/');
      if (rel === 'components/SliceThicknessReliabilityCard.tsx' || rel === 'utils/sliceThicknessReliability.ts') continue;
      const text = readFileSync(file, 'utf-8');
      const staticImport = /import\s[^;]*from\s+['"][^'"]*(SliceThicknessReliabilityCard|sliceThicknessReliability)[^'"]*['"]/;
      if (staticImport.test(text)) offenders.push(rel);
    }
    expect(offenders).toEqual([]);
  });
});
