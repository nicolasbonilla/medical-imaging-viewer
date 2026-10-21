// @vitest-environment node
/**
 * GATE DECISION REPLAY (opt-in; skipped unless FLAMES_GATE_REPLAY_IN is set).
 *
 * Re-applies the SHIPPED decision code (GATES.maxHeadDarkFraction, decideFlairContrast / FLAIR_GATE) to the
 * features recorded by gateValidation.flames.test.ts, so a threshold change is evaluated by the code that
 * ships without recomputing the features. Border/volume refusals are carried over unchanged (they do not
 * depend on these thresholds). Writes per-case decisions and a summary per dataset / contrast / variant.
 *
 * FLAMES_GATE_REPLAY_EVIDENCE: 'clinician' (default — every case replayed as if the clinician confirmed it is a
 * FLAIR, the most permissive legal input) or 'none' (no positive evidence: flair-gate/2 must refuse every case).
 *
 *   FLAMES_GATE_REPLAY_IN="a.json,b.json" FLAMES_GATE_REPLAY_OUT=out.json \
 *     npx vitest run src/services/flames/__tests__/gateReplay.flames.test.ts --pool=threads
 */
import { describe, it } from 'vitest';
import { readFileSync, writeFileSync } from 'node:fs';
import { GATES } from '../pipeline';
import { decideFlairContrast, FLAIR_GATE, type ContrastFeatures } from '../contrastGate';
import type { HeaderEvidence } from '../headerEvidence';

const env = process.env;

interface Row {
  id: string;
  dataset: string;
  contrast: string;
  variant: string;
  accepted?: boolean;
  reason?: string;
  error?: string;
  features?: ContrastFeatures;
  header?: HeaderEvidence;
}

describe.skipIf(!env.FLAMES_GATE_REPLAY_IN)('replay gate decisions', () => {
  it('replays', () => {
    // accepts the raw harness output (an array) or a committed evidence file ({ rows: [...] })
    const rows: Row[] = env.FLAMES_GATE_REPLAY_IN!.split(',').flatMap((f) => {
      const j = JSON.parse(readFileSync(f, 'utf-8'));
      return Array.isArray(j) ? j : j.rows;
    });
    const decisions = rows.map((r) => {
      let decision: 'accepted' | 'refused-error' | 'refused-border-volume' | 'refused-skull' | 'refused-contrast';
      let reason = '';
      if (r.error || !r.features) {
        decision = 'refused-error';
        reason = r.error ?? 'no features';
      } else if (r.reason && /image border is nonzero|nonzero region measures/.test(r.reason)) {
        decision = 'refused-border-volume';
        reason = r.reason;
      } else if (
        r.features.darkFraction > GATES.maxHeadDarkFraction ||
        r.features.rimBrightFraction > GATES.maxRimBrightFraction
      ) {
        decision = 'refused-skull';
      } else {
        const c = decideFlairContrast(r.features, r.header ?? { verdict: 'none', reasons: [] }, {
          clinicianConfirmedFlair: (env.FLAMES_GATE_REPLAY_EVIDENCE ?? 'clinician') === 'clinician',
        });
        decision = c.ok ? 'accepted' : 'refused-contrast';
        reason = c.reason ?? '';
      }
      return { id: r.id, dataset: r.dataset, contrast: r.contrast, variant: r.variant, decision, reason };
    });
    const summary: Record<string, { n: number; accepted: number; byDecision: Record<string, number> }> = {};
    for (const d of decisions) {
      const k = `${d.dataset} | ${d.contrast} | ${d.variant}`;
      summary[k] ??= { n: 0, accepted: 0, byDecision: {} };
      summary[k].n++;
      if (d.decision === 'accepted') summary[k].accepted++;
      summary[k].byDecision[d.decision] = (summary[k].byDecision[d.decision] ?? 0) + 1;
    }
    const out = {
      evidence: env.FLAMES_GATE_REPLAY_EVIDENCE ?? 'clinician',
      gate: {
        ...FLAIR_GATE,
        maxHeadDarkFraction: GATES.maxHeadDarkFraction,
        maxRimBrightFraction: GATES.maxRimBrightFraction,
        maxBorderNonzeroFraction: GATES.maxBorderNonzeroFraction,
      },
      summary,
      decisions,
    };
    for (const [k, v] of Object.entries(summary).sort()) console.log(`[replay] ${k}: accepted ${v.accepted}/${v.n} ${JSON.stringify(v.byDecision)}`);
    if (env.FLAMES_GATE_REPLAY_OUT) writeFileSync(env.FLAMES_GATE_REPLAY_OUT, JSON.stringify(out, null, 1));
  });
});
