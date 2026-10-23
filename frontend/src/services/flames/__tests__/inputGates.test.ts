// @vitest-environment node
/**
 * Input gates of the in-browser FLAMeS path (REQ-SAFE-033; RC-043 skull-stripped, RC-049 FLAIR contrast).
 *
 * Reviewer findings these tests bind:
 *  - a skull-stripped T1 passed every gate and returned "0 lesions" as a normal result;
 *  - a FLAIR WITH skull but zero background was suspected to pass the skull-strip gate — it does pass the
 *    original border/volume checks (test "control" below), and is now refused by the skull clue.
 * Negative controls: research/flames_in_browser/negative_controls_v2.py (G1-G6).
 */
import { describe, expect, it } from 'vitest';
import { checkInputGates, FlamesInputError, GATES, borderNonzeroFraction } from '../pipeline';
import { computeContrastFeatures, decideFlairContrast, FLAIR_GATE } from '../contrastGate';
import { headerContrastEvidence } from '../headerEvidence';
import { makePhantom } from './phantoms';

const NONE = { verdict: 'none' as const, reasons: [] as string[] };

function refusal(fn: () => unknown): string {
  try {
    fn();
  } catch (e) {
    expect(e).toBeInstanceOf(FlamesInputError);
    return (e as Error).message;
  }
  throw new Error('expected the gate to refuse');
}

describe('FLAIR contrast gate (RC-049)', () => {
  const flair = makePhantom({ contrast: 'FLAIR' });
  const t1 = makePhantom({ contrast: 'T1' });
  const t2 = makePhantom({ contrast: 'T2' });
  const CONFIRMED = { clinicianConfirmedFlair: true };

  it('rc049 accepts a skull-stripped FLAIR-like brain when the clinician confirmed the sequence', () => {
    const r = checkInputGates(flair, CONFIRMED);
    expect(r.contrast?.ok).toBe(true);
    expect(r.contrast?.sequenceEvidence).toBe('clinician');
    expect(r.contrast!.score).toBeLessThanOrEqual(FLAIR_GATE.maxDeepOverCortex);
  });

  it('rc049 refuses even a FLAIR-looking image without positive evidence (fail closed)', () => {
    // Re-review: content alone let 10 of 19 skull-stripped T1 of an unseen scanner (ISBI-2015) pass.
    expect(refusal(() => checkInputGates(flair, {}))).toMatch(/not confirmed as FLAIR/);
  });

  it('rc049 a header with a FLAIR inversion time is positive evidence; a "FLAIR" label alone is not', () => {
    const header = headerContrastEvidence(['AX T2 FLAIR'], { inversionTimeMs: 2500 }, null);
    expect(checkInputGates(flair, { headerEvidence: header }).contrast?.sequenceEvidence).toBe('header');
    const labelOnly = headerContrastEvidence(['2020601_flair1_clo'], {}, null); // ISBI-2015 style descrip text
    expect(labelOnly.verdict).toBe('supports');
    expect(refusal(() => checkInputGates(flair, { headerEvidence: labelOnly }))).toMatch(/not confirmed as FLAIR/);
    // when the clinician confirmed, that confirmation (which names a person) is what is recorded
    expect(checkInputGates(flair, { headerEvidence: header, clinicianConfirmedFlair: true }).contrast?.sequenceEvidence).toBe(
      'clinician',
    );
  });

  it('rc049 refuses a skull-stripped T1 (white matter brighter than cortex) even if "confirmed" — the reviewer case', () => {
    expect(refusal(() => checkInputGates(t1, CONFIRMED))).toMatch(/white matter is brighter than the cortex/);
  });

  it('rc049 refuses a T1 whose cortex forms a large darker class even when white matter is not brighter', () => {
    // ISBI-2015 T1 pattern: deepOverCortex 0.91-0.94 but a grey-matter class of 27-33 % of the brain.
    const f = computeContrastFeatures(flair.data, flair.dims, flair.spacing);
    const t1Like = { ...f, locDeepOverNearP75: 0.9, frac45to80: 0.3 };
    const d = decideFlairContrast(t1Like, NONE, CONFIRMED);
    expect(d.ok).toBe(false);
    expect(d.reason).toMatch(/darker grey-matter class/);
  });

  it('rc049 refuses a T2 (bright CSF) even if "confirmed"', () => {
    expect(refusal(() => checkInputGates(t2, CONFIRMED))).toMatch(/fluid \(CSF\) is bright/);
  });

  it('rc049 is robust to a smooth bias field (+-30 % across the head)', () => {
    expect(checkInputGates(makePhantom({ contrast: 'FLAIR', bias: 0.3 }), CONFIRMED).contrast?.ok).toBe(true);
    expect(() => checkInputGates(makePhantom({ contrast: 'T1', bias: 0.3 }), CONFIRMED)).toThrow(FlamesInputError);
  });

  it('rc049 tolerates mild centre shading; stronger shading refuses a FLAIR (safe failure)', () => {
    expect(checkInputGates(makePhantom({ contrast: 'FLAIR', centreBias: 0.1 }), CONFIRMED).contrast?.ok).toBe(true);
    expect(() => checkInputGates(makePhantom({ contrast: 'FLAIR', centreBias: 0.3 }), CONFIRMED)).toThrow(/white matter is brighter/);
  });

  it('rc049 header evidence can refuse a FLAIR-looking image but can never accept a T1-looking one', () => {
    const t1Header = headerContrastEvidence(['Sag T1 MPRAGE'], {}, null);
    expect(t1Header.verdict).toBe('contradicts');
    expect(refusal(() => checkInputGates(flair, { headerEvidence: t1Header, ...CONFIRMED }))).toMatch(/header indicates this is not a FLAIR/);
    const flairHeader = headerContrastEvidence(['AX T2 FLAIR'], { inversionTimeMs: 2500 }, null);
    expect(flairHeader.verdict).toBe('supports');
    expect(() => checkInputGates(t1, { headerEvidence: flairHeader })).toThrow(/white matter is brighter/);
  });

  it('rc049 refuses when the contrast cannot be measured (no cortex band at this resolution)', () => {
    const f = computeContrastFeatures(flair.data, flair.dims, flair.spacing);
    expect(decideFlairContrast({ ...f, nearVoxels: 10 }, NONE, CONFIRMED).ok).toBe(false);
    expect(decideFlairContrast({ ...f, locDeepOverNearP75: NaN }, NONE, CONFIRMED).ok).toBe(false);
  });
});

describe('skull-stripped gate (RC-043): FLAIR with skull and zero background', () => {
  const fat = makePhantom({ contrast: 'FLAIR', skull: 'fat' });
  const dark = makePhantom({ contrast: 'FLAIR', skull: 'dark' });

  it('rc043 control: such an image passes the ORIGINAL border and volume checks', () => {
    for (const skull of [fat, dark]) {
      expect(borderNonzeroFraction(skull.data, skull.dims)).toBeLessThanOrEqual(GATES.maxBorderNonzeroFraction);
      let n = 0;
      for (let v = 0; v < skull.data.length; v++) if (skull.data[v] !== 0) n++;
      const ml = (n * skull.spacing[0] ** 3) / 1000;
      expect(ml).toBeGreaterThan(GATES.minBrainMl);
      expect(ml).toBeLessThan(GATES.maxBrainMl);
    }
  });

  it('rc043 a head with bright scalp fat is refused by the rim clue', () => {
    expect(refusal(() => checkInputGates(fat, {}))).toMatch(/outer 6 mm is very bright \(scalp fat\)/);
    const f = computeContrastFeatures(fat.data, fat.dims, fat.spacing);
    expect(f.rimBrightFraction).toBeGreaterThan(GATES.maxRimBrightFraction);
  });

  it('rc043 a head with a signal-free bone shell is refused by the dark clue', () => {
    expect(refusal(() => checkInputGates(dark, {}))).toMatch(/head region is very dark/);
    const f = computeContrastFeatures(dark.data, dark.dims, dark.spacing);
    expect(f.darkFraction).toBeGreaterThan(GATES.maxHeadDarkFraction);
  });

  it('rc043 the stripped brain stays below both skull-clue limits', () => {
    const flair = makePhantom({ contrast: 'FLAIR' });
    const f = computeContrastFeatures(flair.data, flair.dims, flair.spacing);
    expect(checkInputGates(flair, { clinicianConfirmedFlair: true }).contrast?.ok).toBe(true);
    expect(f.darkFraction).toBeLessThan(GATES.maxHeadDarkFraction);
    expect(f.rimBrightFraction).toBeLessThan(GATES.maxRimBrightFraction);
  });
});

describe('header evidence (never the file name)', () => {
  it('rc049 reads inversion times and sequence names', () => {
    expect(headerContrastEvidence(['TE=81;Time=101112.000;phase=1'], {}, null).verdict).toBe('none');
    expect(headerContrastEvidence(['TI=2500'], {}, null).verdict).toBe('supports');
    expect(headerContrastEvidence(['TI=900'], {}, null).verdict).toBe('contradicts');
    expect(headerContrastEvidence([], { inversionTimeMs: 1000 }, null).verdict).toBe('contradicts');
    expect(headerContrastEvidence([], { seriesDescription: 'T1 FLAIR SAG' }, null).verdict).toBe('contradicts');
    expect(headerContrastEvidence([], {}, 'Axial T2 FLAIR fs').verdict).toBe('supports');
    expect(headerContrastEvidence([], {}, 'AX T2 TSE').verdict).toBe('contradicts');
    expect(headerContrastEvidence(['3D_SPACE_DARK-FLUID'], {}, null).verdict).toBe('supports');
    expect(headerContrastEvidence(['TI=2.5'], {}, null).inversionTimeMs).toBe(2500);
  });
});
