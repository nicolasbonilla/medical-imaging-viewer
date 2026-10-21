// @vitest-environment node
/**
 * PARITY HARNESS (opt-in; skipped unless FLAMES_PARITY_FLAIR is set — CI has no model or data).
 *
 * Runs the exact browser pipeline (src/services/flames/pipeline.ts) with ONNX Runtime WEB
 * (WebAssembly backend, the browser's CPU fallback) in Node, on a public FLAIR, and compares the mask
 * with reference masks produced by nnU-Net's own predictor (research/flames_in_browser/reference_nnunet.py).
 *
 *   FLAMES_PARITY_FLAIR=<flair.nii.gz> FLAMES_PARITY_MODEL=<flames-fold0.onnx> \
 *   FLAMES_PARITY_REFS="torch=<ref_torch.nii.gz>,onnx=<ref_onnx.nii.gz>" \
 *   [FLAMES_PARITY_GT=<expert mask>] [FLAMES_PARITY_OUT=<summary.json>] [FLAMES_PARITY_THREADS=8] \
 *   [FLAMES_PARITY_MIN_DICE=0.99] npx vitest run src/services/flames/__tests__/parity.flames.test.ts --pool=threads
 */
import { describe, expect, it } from 'vitest';
import { readFileSync, writeFileSync } from 'node:fs';
import { readNifti } from '../nifti';
import { segmentFlairVolume } from '../pipeline';
import { FLAMES_PLAN } from '../plan';
import { dice, summariseLesions } from '../postprocess';

const env = process.env;
const enabled = Boolean(env.FLAMES_PARITY_FLAIR);

describe.skipIf(!enabled)('FLAMeS browser path vs nnU-Net reference (public data)', () => {
  it(
    'Dice >= threshold against every reference',
    async () => {
      const ort = await import('onnxruntime-web');
      const threads = Number(env.FLAMES_PARITY_THREADS || 8);
      ort.env.wasm.numThreads = threads;
      const flair = await readNifti(readFileSync(env.FLAMES_PARITY_FLAIR!));
      const session = await ort.InferenceSession.create(readFileSync(env.FLAMES_PARITY_MODEL!), {
        executionProviders: ['wasm'],
        graphOptimizationLevel: 'all',
      });
      const patchTimes: number[] = [];
      const started = performance.now();
      const result = await segmentFlairVolume(
        { data: flair.data, dims: flair.dims, spacing: flair.spacing },
        {
          runPatch: async (tile) => {
            const t0 = performance.now();
            const input = new ort.Tensor('float32', tile, [1, 1, ...FLAMES_PLAN.patchSize]);
            const out = await session.run({ [session.inputNames[0]]: input });
            const data = (out[session.outputNames[0]].data as Float32Array).slice();
            patchTimes.push(performance.now() - t0);
            return data;
          },
        },
      );
      const seconds = (performance.now() - started) / 1000;
      await session.release();

      const refs = (env.FLAMES_PARITY_REFS || '')
        .split(',')
        .filter(Boolean)
        .map((pair) => pair.split('='));
      const comparisons: Record<string, unknown> = {};
      const minDice = Number(env.FLAMES_PARITY_MIN_DICE || 0.99);
      for (const [name, path] of refs) {
        const ref = await readNifti(readFileSync(path));
        expect(ref.dims).toEqual(flair.dims);
        const refMask = Uint8Array.from(ref.data, (v) => (v > 0.5 ? 1 : 0));
        let differing = 0;
        for (let i = 0; i < refMask.length; i++) if (refMask[i] !== result.maskNifti[i]) differing++;
        const refSummary = summariseLesions(refMask, flair.dims, flair.spacing);
        comparisons[name] = {
          dice: dice(result.maskNifti, refMask),
          differingVoxels: differing,
          refVoxels: refSummary.lesionVoxels,
          refLesions: refSummary.lesionCount,
          refVolumeMl: refSummary.lesionVolumeMl,
        };
      }
      let gt: unknown = null;
      if (env.FLAMES_PARITY_GT) {
        const g = await readNifti(readFileSync(env.FLAMES_PARITY_GT));
        const gm = Uint8Array.from(g.data, (v) => (v > 0.5 ? 1 : 0));
        const gs = summariseLesions(gm, g.dims, g.spacing);
        gt = { diceVsExpert: dice(result.maskNifti, gm), expertVoxels: gs.lesionVoxels, expertLesions: gs.lesionCount, expertVolumeMl: gs.lesionVolumeMl };
      }
      const summary = {
        flair: env.FLAMES_PARITY_FLAIR,
        dims: flair.dims,
        spacing: flair.spacing,
        runtime: `onnxruntime-web ${ort.env.versions?.web ?? ''} wasm, ${threads} threads, Node ${process.version}`,
        seconds: Math.round(seconds * 10) / 10,
        windows: result.diagnostics.windows,
        meanPatchSeconds: Math.round((patchTimes.reduce((s, v) => s + v, 0) / patchTimes.length / 1000) * 10) / 10,
        resampledShape: result.diagnostics.resampledShape,
        bbox: result.diagnostics.bbox,
        browser: {
          voxels: result.summary.lesionVoxels,
          lesions: result.summary.lesionCount,
          volumeMl: result.summary.lesionVolumeMl,
        },
        comparisons,
        expert: gt,
      };
      console.log(JSON.stringify(summary, null, 1));
      if (env.FLAMES_PARITY_OUT) {
        writeFileSync(env.FLAMES_PARITY_OUT, JSON.stringify(summary, null, 1));
        writeFileSync(env.FLAMES_PARITY_OUT.replace(/\.json$/, '') + '.mask.u8', result.maskNifti);
      }
      for (const name of Object.keys(comparisons)) {
        expect((comparisons[name] as { dice: number }).dice).toBeGreaterThanOrEqual(minDice);
      }
    },
    60 * 60 * 1000,
  );
});
