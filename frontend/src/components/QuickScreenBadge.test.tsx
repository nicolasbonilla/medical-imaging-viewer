/**
 * RC-008 — the Edge AI limitation statement is shown, not offered.
 *
 * Risk control for HAZ-004 (over-reliance on an assistive screening result).
 * Repaired by CAPA-004 CA-4.4.
 *
 * CAPA-004 §4 found the disclaimer string present in the component but gated
 * behind `useState(false)`, so it rendered only after the user clicked a
 * "Disclaimer" toggle. A user could read a confidence-scored abnormal/normal
 * verdict with no limitation statement at all — while the file's own header
 * comment asserted "A clear disclaimer is always shown".
 *
 * Verification by grepping for the string could not distinguish a displayed
 * control from a hidden one. These tests assert it is RENDERED without any
 * interaction, which is the only claim that matters.
 *
 * Negative control (CAPA-001 §5): restore the toggle, or gate the disclaimer on
 * any state, and these tests MUST fail.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';

const source = readFileSync(join(__dirname, 'QuickScreenBadge.tsx'), 'utf-8');

/**
 * Comments are stripped before asserting on the defect, because the code now
 * carries a comment explaining what `showDisclaimer` used to do. Asserting over
 * raw text would flag that explanation as the defect itself — and the natural
 * response would be to delete the explanation, losing the reason the control
 * exists. Test the code; keep the history.
 */
const code = source
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/(^|[^:])\/\/.*$/gm, '$1');

describe('RC-008 — Edge AI disclaimer is unconditional', () => {
  it('rc008 the disclaimer is not gated behind a showDisclaimer state', () => {
    // The specific defect. Guard against its exact reintroduction.
    expect(code).not.toMatch(/showDisclaimer/);
    expect(source).not.toMatch(/useState\(false\)[^\n]*[Dd]isclaimer/);
  });

  it('rc008 the disclaimer renders whenever a result is present or being produced', () => {
    // It must share the result's visibility condition — never a narrower one.
    expect(code).toMatch(
      /\{\(result \|\| isProcessing\) && \(\s*\n\s*<div data-testid="edge-ai-disclaimer"/,
    );
  });

  it('rc008 no dismiss or toggle control remains for the disclaimer', () => {
    // A limitation the user can dismiss will be dismissed. There must be no
    // affordance to hide it.
    expect(code).not.toMatch(/onClick=\{\(\) => set[A-Za-z]*Disclaimer/);
  });

  it('rc008 the disclaimer states both non-diagnostic status and the need for confirmation', () => {
    expect(source).toMatch(/NOT diagnostic/);
    expect(source).toMatch(/confirmed by a qualified radiologist/);
  });

  it('rc008 the header comment no longer makes a false claim', () => {
    // The file previously asserted "A clear disclaimer is always shown" twenty
    // lines above the code that contradicted it. A false comment is worse than
    // none: it is what a reviewer reads instead of the code.
    const headerEnd = source.indexOf('*/');
    const header = source.slice(0, headerEnd);

    if (/always shown/.test(header)) {
      expect(header).toMatch(/unconditionally/);
    }
    expect(header).toMatch(/RC-008/);
  });
});
