// @vitest-environment node
/**
 * INPUT-GATE VALIDATION HARNESS (opt-in; skipped unless FLAMES_GATE_MANIFEST is set — CI has no data).
 *
 * Runs the SHIPPED gate code (pipeline.checkInputGates: skull-stripped plausibility RC-043 + FLAIR
 * contrast gate RC-049, header evidence included) on public volumes and records every decision and
 * feature, so the sensitivity/specificity reported in FLAIR-GATE-VALIDATION.md come from this code.
 *
 *   FLAMES_GATE_MANIFEST=<cases.json> FLAMES_GATE_OUT=<results.json> [FLAMES_GATE_SHARD=k/n] \
 *     npx vitest run src/services/flames/__tests__/gateValidation.flames.test.ts --pool=threads
 *
 * cases.json: [{ "id", "dataset", "contrast", "variant", "file", "mask"? }]  (mask: multiply by mask > 0)
 *
 * flair-gate/2: acceptance needs positive evidence (header or clinician confirmation). The harness runs every
 * case AS IF the clinician had confirmed it is a FLAIR — the most permissive input the app accepts — so the
 * recorded decisions measure what the content check still refuses when a user confirms the wrong file.
 */
import { describe, it } from 'vitest';
import { readFileSync, writeFileSync } from 'node:fs';
import { readNifti } from '../nifti';
import { checkInputGates, FlamesInputError } from '../pipeline';
import { computeContrastFeatures, flairScore, FLAIR_GATE, type ContrastFeatures } from '../contrastGate';
import { headerContrastEvidence } from '../headerEvidence';

const env = process.env;
const enabled = Boolean(env.FLAMES_GATE_MANIFEST);

interface Case {
  id: string;
  dataset: string;
  contrast: string;
  variant: string;
  file: string;
  mask?: string;
}

describe.skipIf(!enabled)('FLAMeS input gates on public data', () => {
  it(
    'records gate decisions and features',
    async () => {
      let cases: Case[] = JSON.parse(readFileSync(env.FLAMES_GATE_MANIFEST!, 'utf-8'));
      if (env.FLAMES_GATE_SHARD) {
        const [k, n] = env.FLAMES_GATE_SHARD.split('/').map(Number);
        cases = cases.filter((_, i) => i % n === k);
      }
      const out: unknown[] = [];
      for (const c of cases) {
        const t0 = performance.now();
        const row: Record<string, unknown> = { ...c, gateVersion: FLAIR_GATE.version };
        try {
          const vol = await readNifti(readFileSync(c.file));
          let data = vol.data;
          if (c.mask) {
            const m = await readNifti(readFileSync(c.mask));
            data = Float32Array.from(data, (v, i) => (m.data[i] > 0 ? v : 0));
          }
          const header = headerContrastEvidence(vol.headerText, vol.dicom, null);
          row.header = header;
          row.dims = vol.dims;
          row.spacing = vol.spacing;
          try {
            const report = checkInputGates(
              { data, dims: vol.dims, spacing: vol.spacing },
              { headerEvidence: header, clinicianConfirmedFlair: true },
            );
            row.accepted = true;
            row.borderNonzeroFraction = report.borderNonzeroFraction;
            row.brainVolumeMl = report.brainVolumeMl;
            row.features = report.contrast?.features;
          } catch (e) {
            if (!(e instanceof FlamesInputError)) throw e;
            row.accepted = false;
            row.reason = e.message;
            row.features = e.contrast?.features;
          }
          // refused before the contrast stage (border / volume): measure anyway for the report
          if (!row.features) row.features = computeContrastFeatures(data, vol.dims, vol.spacing);
          row.score = flairScore(row.features as ContrastFeatures);
        } catch (e) {
          row.accepted = false;
          row.error = e instanceof Error ? e.message : String(e);
        }
        row.seconds = Math.round((performance.now() - t0) / 100) / 10;
        out.push(row);
        console.log(`[gate] ${c.id} ${c.contrast}/${c.variant} accepted=${row.accepted} score=${(row.score as number)?.toFixed?.(3)} ${row.seconds}s`);
        if (env.FLAMES_GATE_OUT) writeFileSync(env.FLAMES_GATE_OUT, JSON.stringify(out, null, 1));
      }
    },
    24 * 3600 * 1000,
  );
});
