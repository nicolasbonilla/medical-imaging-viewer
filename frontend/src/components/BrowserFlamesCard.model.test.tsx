/**
 * M1 (thirteenth review of PR #81; RC-122, RC-126, RC-127; DRAFT, PENDING owner approval): a MODEL-BASED test of the
 * browser card and its consultation hook. Seeded random sequences of user and environment actions — select A/B, a new
 * version of the file, tick/untick the attestation, Run / Re-run, "Check again", a 429 with its wait, a LATE response
 * of any earlier request, more than 2 h or 24 h passing, the run completing, the final consultation answering, failing
 * or rate-limited — against a FAKE SERVER with the real decision semantics: its decisions are the server's own
 * (qualityGate.card_model.v1.json, generated from quality_gate.evaluate and checked by test_rc122_review13.py); its run
 * tokens are single-use, bound to (file, version, attestation) and expire after 2 h, as spend_run_token.
 *
 * Properties, after every step (P4 at the end of each sequence):
 *  P1  a run starts only with a server decision for the CURRENT file and attestation and the newest version the card
 *      knows (a rescinded attestation invalidates an attested decision);
 *  P2  every released output is recorded by exactly one server consultation that spent an unspent, unexpired run
 *      token issued for that run; no token is presented by two runs; no run starts with a token already expired;
 *  P3  the "before" and "final" panels never show a decision for other inputs: the file shown is the selected one, an
 *      attested decision only while the attestation is ticked, the version is the newest the server named and never
 *      goes back (a late response is discarded), the final decision is the current run's;
 *  P4  liveness: settled, the card shows a decision for the current file (never stuck on "checking"), and a fresh run
 *      the server allows is possible and released (at the first attempt unless a newer version was stored after the
 *      card's last consultation);
 *  P5  the attestation is offered whenever the server says the current file is attestable, also after an attested run.
 * Not observable in the browser, hence not claimed: a new version stored after the card's last consultation — the
 * server refuses to release that run (its run token names the old version).
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, act, fireEvent, cleanup } from '@testing-library/react';
import '@/i18n/config';

/* eslint-disable @typescript-eslint/no-explicit-any */
type Json = any;
const h = vi.hoisted(() => ({
  flames: {} as Record<string, unknown>,
  request: ((..._a: unknown[]) => Promise.resolve(null)) as (...a: unknown[]) => Promise<unknown>,
  panels: {} as Record<string, Json>,
}));
vi.mock('@/hooks/useBrowserFlames', () => ({ useBrowserFlames: () => h.flames }));
vi.mock('@/services/qualityGate/api', () => ({ requestQualityGate: (...a: unknown[]) => h.request(...a) }));
vi.mock('@/config/features', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/config/features')>();
  return { ...mod, FEATURES: { ...mod.FEATURES, QUALITY_GATE: true } };
});
vi.mock('./QualityGatePanel', () => {
  const Panel = (props: { result: Json; testId?: string }) => {
    h.panels[props.testId ?? 'panel'] = props.result;
    return <div data-testid={props.testId} data-decision={props.result?.decision} />;
  };
  return { QualityGatePanel: Panel, default: Panel };
});

import { BrowserFlamesCard } from './BrowserFlamesCard';
import { useViewerStore } from '@/store/useViewerStore';

const FIXTURE = JSON.parse(readFileSync(join(__dirname, '..', 'config', 'qualityGate.card_model.v1.json'), 'utf-8'));
const A = 'patients/p/studies/s/series/a/a.nii.gz';
const B = 'patients/p/studies/s/series/b/b.nii.gz';
const SEQ: Record<string, string> = { [A]: 'missing', [B]: 'FLAIR' };          // A: attestable; B: a FLAIR
const TTL_S = 2 * 3600;
const HOUR = 3600 * 1000;
// the server of this commit withholds the output of a run it cannot confirm iff its rule says so
const WITHHOLDS = FIXTURE.decisions['FLAIR|false|stripped|false'].ai_output_allowed === false;
const PROPS = ['P1', 'P2', 'P3', 'P4', 'P5'] as const;
type Prop = typeof PROPS[number];

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Tok { file: string; version: string; attested: boolean; exp: number; spent: boolean; presentedBy: number | null }
interface Run { id: number; file: string; attested: boolean; knownVersion: number | null; checked: boolean; startedAt: number }
interface Pending { resolve: (v: unknown) => void; answer: Json }

const platformAnswer = (file: string, code: string, seconds?: number): Json => ({
  gate_version: 'quality-gate/1', policy_version: null, mode: null, decision: 'abstain', ai_may_run: false,
  ai_output_allowed: false, codes: [code], attestable_visits: [], actions: {},
  checks: [{ check: 'platform', visit: null, status: 'abstain', code, params: seconds ? { seconds } : {} }],
  subject: { file_id: file, version: null },
});
const vnum = (v: unknown) => (typeof v === 'string' && /^v\d+$/.test(v) ? Number(v.slice(1)) : null);
const attestBox = () => document.querySelector('[data-testid="quality-gate-attest"] input') as HTMLInputElement | null;

class World {
  file = A;
  versions: Record<string, number> = { [A]: 1, [B]: 1 };
  known: Record<string, number> = {};                  // the newest version DELIVERED to the card, per file
  tokens = new Map<string, Tok>();
  pending: Pending[] = [];
  answerRun = new Map<string, number | null>();        // trace id of a final answer -> its run
  released = new Set<number>();
  next429 = 0;
  nextFinal: 'ok' | 'fail' | '429' = 'ok';
  running: Run | null = null;
  doneRun: Run | null = null;
  runSeq = 0;
  n = 0;
  lastShown: number | null = null;
  lastUnseen = false;                                  // P4: the newest version was unknown to the card at the first attempt
  violations: Partial<Record<Prop, string>> = {};

  violate(p: Prop, why: string) { if (!this.violations[p]) this.violations[p] = why; }

  decide(file: string, attested: boolean, skull: string, confirmed?: boolean): Json {
    const key = `${SEQ[file]}|${attested}|${skull}` + (skull === 'pending' ? '' : `|${WITHHOLDS ? confirmed === true : true}`);
    return JSON.parse(JSON.stringify(FIXTURE.decisions[key]));
  }

  request = (file: unknown, confirmed: unknown, skull: unknown = 'pending', token?: unknown): Promise<unknown> => {
    const f = String(file);
    const attested = confirmed === true;
    const sk = String(skull ?? 'pending');
    const id = ++this.n;
    const final = sk !== 'pending';
    let answer: Json;
    if (final && this.nextFinal !== 'ok') {
      answer = this.nextFinal === '429' ? platformAnswer(f, 'gate_rate_limited', 30) : platformAnswer(f, 'gate_unavailable');
      this.nextFinal = 'ok';
    } else if (this.next429 > 0) {
      this.next429 -= 1;
      answer = platformAnswer(f, 'gate_rate_limited', 30);
    } else {
      const version = `v${this.versions[f]}`;
      if (final) {
        const run = this.doneRun;
        const tok = typeof token === 'string' ? this.tokens.get(token) : undefined;
        if (run && !run.checked) {
          run.checked = true;
          if (!tok) this.violate('P2', `run ${run.id}: its final consultation presents no run token issued by the server`);
          else if (tok.file !== run.file || tok.attested !== run.attested
            || (run.knownVersion !== null && vnum(tok.version) !== run.knownVersion)) {
            this.violate('P1', `run ${run.id} (file ${run.file === A ? 'A' : 'B'}, attested ${run.attested}, v${run.knownVersion}) `
              + `started with a decision for ${tok.file === A ? 'A' : 'B'}, attested ${tok.attested}, ${tok.version}`);
          } else if (tok.exp <= run.startedAt) {
            // a run started with a token that had already expired can never be released: a wasted AI run
            this.violate('P2', `run ${run.id} started with a run token that had already expired`);
          }
        }
        if (tok && run) {
          if (tok.presentedBy !== null && tok.presentedBy !== run.id) {
            this.violate('P2', `run ${run.id} presents the run token of run ${tok.presentedBy}`);
          }
          if (tok.presentedBy === null) tok.presentedBy = run.id;
        }
        const valid = !!tok && !tok.spent && tok.exp > Date.now() && tok.file === f && tok.version === version
          && tok.attested === attested;
        if (valid && tok) tok.spent = true;
        answer = this.decide(f, attested, sk, valid);
        if (valid && answer.ai_output_allowed === true && run) this.released.add(run.id);
        answer.trace_id = `tr-${id}`;
        this.answerRun.set(answer.trace_id, run ? run.id : null);
      } else {
        answer = this.decide(f, attested, 'pending');
        if (answer.ai_may_run === true) {
          const t = `rt-${id}`;
          this.tokens.set(t, { file: f, version, attested, exp: Date.now() + TTL_S * 1000, spent: false, presentedBy: null });
          answer.run_token = t;
          answer.run_token_ttl_s = TTL_S;
        }
        answer.trace_id = `tr-${id}`;
      }
      answer.subject = { file_id: f, version };
      answer.inputs = { mode: 'single', visits: [{ sequence: SEQ[f], physician_confirmed_flair: attested, skull: sk }] };
      answer.platform = { allowed: true, code: null };
    }
    return new Promise((resolve) => this.pending.push({ resolve, answer }));
  };

  startRun(fileId: string) {
    this.running = { id: ++this.runSeq, file: fileId, attested: attestBox()?.checked === true,
      knownVersion: this.known[fileId] ?? null, checked: false, startedAt: Date.now() };
    Object.assign(h.flames, { status: 'running', result: null });
  }

  complete() {
    if (!this.running) return;
    this.doneRun = this.running;
    this.running = null;
    Object.assign(h.flames, { status: 'done', result: resultFor(this.doneRun.file) });
  }
}

const resultFor = (fileId: string) => ({
  fileId, maskApp: new Uint8Array(24), dims: [3, 2, 4], spacing: [1, 1, 1],
  summary: { lesionCount: 2, lesionVoxels: 10, lesionVolumeMl: 0.01, componentVolumesMl: [] },
  provenance: { pipeline: 'p', model: 'm', modelSha256: 'x', sourceCheckpointSha256: 'y', backend: 'wasm', threads: 1,
    onnxRuntimeWeb: '1.24.1', mirror: false, windows: 1, networkCalls: 1, resampledShape: [1, 1, 1], seconds: 60,
    generatedAt: '2026-11-12T00:00:00.000Z', sequenceEvidence: 'clinician', inputPreparation: 'skull-removed' },
});

type Action = 'selectA' | 'selectB' | 'version' | 'attest' | 'run' | 'again' | 'r429' | 'finalOk' | 'finalFail'
  | 'final429' | 'deliverOne' | 'deliverAll' | 'tick' | 'wait' | 'h2' | 'h24' | 'complete';
const WEIGHTS: [Action, number][] = [['selectA', 2], ['selectB', 2], ['version', 1], ['attest', 3], ['run', 4], ['again', 1],
  ['r429', 1], ['finalOk', 1], ['finalFail', 1], ['final429', 1], ['deliverOne', 4], ['deliverAll', 2], ['tick', 2],
  ['wait', 1], ['h2', 1], ['h24', 0.5], ['complete', 2]];
const TOTAL = WEIGHTS.reduce((s, [, w]) => s + w, 0);
function pick(rng: () => number): Action {
  let x = rng() * TOTAL;
  for (const [a, w] of WEIGHTS) { if ((x -= w) < 0) return a; }
  return 'tick';
}

/** The reviewer's scenarios (re-run, rescind, expiry) and a late response after the attestation was rescinded. */
const CORPUS: Record<string, Action[]> = {
  rerun: ['selectB', 'tick', 'deliverAll', 'run', 'deliverAll', 'complete', 'deliverAll', 'run', 'deliverAll', 'complete', 'deliverAll'],
  rescind: ['selectA', 'tick', 'deliverAll', 'attest', 'run', 'deliverAll', 'complete', 'deliverAll', 'attest', 'run',
    'deliverAll', 'complete', 'deliverAll'],
  expiry: ['selectB', 'tick', 'deliverAll', 'h2', 'run', 'deliverAll', 'complete', 'deliverAll'],
  late: ['selectA', 'tick', 'deliverAll', 'attest', 'run', 'attest', 'deliverAll', 'complete', 'deliverAll'],
};

async function play(actions: Action[] | null, seed: number): Promise<Partial<Record<Prop, string>>> {
  const rng = mulberry32(seed);
  const world = new World();
  h.request = world.request;
  for (const k of Object.keys(h.panels)) delete h.panels[k];
  for (const k of Object.keys(h.flames)) delete h.flames[k];
  Object.assign(h.flames, { status: 'idle', fraction: 0, message: '', error: null, startedAt: null, result: null,
    run: (fileId: string) => world.startRun(fileId), cancel: () => undefined, reset: () => undefined });
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-12T08:00:00Z'));
  const view = render(<BrowserFlamesCard flairFileId={world.file} />);
  const sync = async (ms = 0) => {
    await act(async () => {
      view.rerender(<BrowserFlamesCard flairFileId={world.file} />);
      await vi.advanceTimersByTimeAsync(ms);
    });
  };
  const click = async (el: Element | null) => { if (el) await act(async () => { fireEvent.click(el); }); };
  const confirmBox = () => document.querySelector('[data-testid="browser-flames-confirm-sequence"] input') as HTMLInputElement | null;
  const runButton = () => screen.queryByRole('button', { name: /Segment in this browser/ }) as HTMLButtonElement | null;
  const deliver = async (i: number) => {
    const [p] = world.pending.splice(i, 1);
    const v = vnum(p.answer?.subject?.version);
    const file = p.answer?.subject?.file_id;
    if (v !== null && file) world.known[file] = Math.max(world.known[file] ?? 0, v);
    await act(async () => { p.resolve(p.answer); await vi.advanceTimersByTimeAsync(0); });
    await sync();
  };
  const check = () => {
    const before = screen.queryByTestId('quality-gate-before') ? h.panels['quality-gate-before'] : null;
    if (before) {
      if (before.subject?.file_id !== world.file) world.violate('P3', `the "before" panel shows a decision for another file`);
      if (before.inputs?.visits?.[0]?.physician_confirmed_flair === true && attestBox()?.checked !== true) {
        world.violate('P3', 'the "before" panel shows an attested decision while the attestation is not ticked');
      }
      const v = vnum(before.subject?.version);
      if (v !== null) {
        if (world.lastShown !== null && v < world.lastShown) world.violate('P3', `the "before" panel went back from v${world.lastShown} to v${v}`);
        const named = world.known[world.file];
        if (named !== undefined && v < named) world.violate('P3', `the "before" panel shows v${v} though the server already named v${named}`);
        world.lastShown = Math.max(world.lastShown ?? 0, v);
      }
      const decided = !(before.codes ?? []).some((c: string) => c.startsWith('gate_'));
      if (decided && world.file === A && h.flames.status !== 'running' && !attestBox()) {
        world.violate('P5', 'file A is attestable, but the attestation is not offered');
      }
    }
    const after = screen.queryByTestId('quality-gate-after') ? h.panels['quality-gate-after'] : null;
    if (after && after.subject) {                       // the browser's own 'unavailable' names no subject
      if (after.subject.file_id !== world.file) world.violate('P3', 'the "final" panel shows a decision for another file');
      const run = after.trace_id ? world.answerRun.get(after.trace_id) : undefined;
      if (run !== undefined && run !== (world.doneRun?.id ?? null)) world.violate('P3', `the "final" panel shows the decision of run ${run}`);
    }
    if (screen.queryByText(/AI draft ready/) && !(world.doneRun && world.released.has(world.doneRun.id))) {
      world.violate('P2', `run ${world.doneRun?.id} shows a released output the server did not record as a run`);
    }
  };
  const settle = async () => {
    for (let i = 0; i < 10; i += 1) {
      world.next429 = 0;
      world.nextFinal = 'ok';
      while (world.pending.length) await deliver(0);
      await sync(5 * 60 * 1000);
      await click(screen.queryByTestId('quality-gate-check-again'));
      await click(screen.queryByTestId('quality-gate-check-again-final'));
      if (world.running) { world.complete(); await sync(); }
      await sync(400);
      if (!world.pending.length && !world.running) break;
    }
  };
  try {
    await sync(400);
    await click(confirmBox());
    const steps = actions ?? Array.from({ length: 10 + Math.floor(rng() * 16) }, () => pick(rng));
    if (process.env.QG_MODEL_TRACE) console.log('steps', seed, steps.join(' '));
    for (const a of steps) {
      switch (a) {
        case 'selectA': case 'selectB': {
          const next = a === 'selectA' ? A : B;
          if (next !== world.file) { world.file = next; world.lastShown = null; }
          await sync(400);
          if (confirmBox() && !confirmBox()!.checked) await click(confirmBox());
          break;
        }
        case 'version': world.versions[world.file] += 1; break;
        case 'attest': await click(attestBox()); break;
        case 'run': {
          if (confirmBox() && !confirmBox()!.checked) await click(confirmBox());
          const b = runButton();
          if (b && !b.disabled) await click(b);
          break;
        }
        case 'again':
          await click(screen.queryByTestId('quality-gate-check-again'));
          await click(screen.queryByTestId('quality-gate-check-again-final'));
          break;
        case 'r429': world.next429 = 1 + Math.floor(rng() * 2); break;
        case 'finalOk': world.nextFinal = 'ok'; break;
        case 'finalFail': world.nextFinal = 'fail'; break;
        case 'final429': world.nextFinal = '429'; break;
        case 'deliverOne': if (world.pending.length) await deliver(Math.floor(rng() * world.pending.length)); break;
        case 'deliverAll': while (world.pending.length) await deliver(Math.floor(rng() * world.pending.length)); break;
        case 'tick': await sync(300); break;
        case 'wait': await sync(70 * 1000); break;
        case 'h2': vi.setSystemTime(Date.now() + 3 * HOUR); break;
        case 'h24': vi.setSystemTime(Date.now() + 25 * HOUR); break;
        case 'complete': world.complete(); break;
        default: break;
      }
      await sync();
      check();
    }
    // P4: settle, then the card must show a decision for the current file, and a fresh run must be possible
    await settle();
    check();
    if (!screen.queryByTestId('quality-gate-before') && !world.running && h.flames.status !== 'done') {
      world.violate('P4', 'settled, the card still shows no decision for the current file');
    }
    if (h.flames.status === 'done' && (h.flames.result as Json)?.fileId === world.file && !screen.queryByTestId('quality-gate-after')) {
      world.violate('P4', 'settled, the finished run still has no final decision');
    }
    // a fresh run the server allows must reach a released output — at the latest on the second attempt: a version
    // stored after the card's last consultation is not observable before the next answer names it (the first run's
    // final consultation does, and the server refuses to release that run)
    let released = false;
    for (let attempt = 0; attempt < 2 && !released; attempt += 1) {
      // the second attempt is allowed ONLY when the card could not know the newest version before the first
      const unseen = (world.known[world.file] ?? 0) < world.versions[world.file];
      if (attempt === 1 && !world.lastUnseen) {
        world.violate('P4', 'a fresh run the server allows was not released though the card knew the newest version');
        break;
      }
      world.lastUnseen = unseen;
      if (confirmBox() && !confirmBox()!.checked) await click(confirmBox());
      if (world.file === A && attestBox() && !attestBox()!.checked) await click(attestBox());
      const b = runButton();
      if (!b || b.disabled) {
        world.violate('P4', `settled, Run is disabled though the server allows a run of ${world.file === A ? 'A (attested)' : 'B'}`);
        break;
      }
      await click(b);
      await settle();
      check();
      released = !!(world.doneRun && world.released.has(world.doneRun.id) && screen.queryByText(/AI draft ready/));
    }
    if (!released && !world.violations.P4) world.violate('P4', 'a fresh run the server allows does not reach a released output');
  } catch (error) {
    // a crash of the card is the worst liveness failure: it never reaches a decided state again
    world.violate('P4', `the card crashed: ${String((error as Error)?.message ?? error).slice(0, 120)}`);
  } finally {
    view.unmount();
    cleanup();
    vi.useRealTimers();
  }
  return world.violations;
}

describe('M1: model-based test of the card and its consultations', () => {
  it('rc126 rc122 rc127 P1-P5 hold over the seed corpus and the generated sequences', async () => {
    useViewerStore.setState({
      currentSeries: { id: 's', name: 'flair', format: 'nifti', file_id: A, total_slices: 4, metadata: { rows: 3, columns: 2 } },
    } as never);
    const runs = Number(process.env.QG_MODEL_RUNS ?? 2000);
    const counts: Record<Prop, number> = { P1: 0, P2: 0, P3: 0, P4: 0, P5: 0 };
    const examples: Partial<Record<Prop, string>> = {};
    const record = (name: string, v: Partial<Record<Prop, string>>) => {
      for (const p of PROPS) {
        if (v[p]) { counts[p] += 1; examples[p] ??= `${name}: ${v[p]}`; }
      }
    };
    for (const [name, actions] of Object.entries(CORPUS)) record(`corpus ${name}`, await play(actions, 1));
    const only = process.env.QG_MODEL_SEED ? [Number(process.env.QG_MODEL_SEED)] : null;
    // negative controls only (QG_MODEL_STOP=1): stop at the first violated property — a mutant needs one failing sequence
    const stop = () => process.env.QG_MODEL_STOP === '1' && PROPS.some((p) => counts[p] > 0);
    for (let i = 0; i < (only ? 1 : runs) && !stop(); i += 1) {
      const seed = only ? only[0] : 20261113 + i;
      record(`seed ${seed}`, await play(null, seed));
    }
    // the counts per property, and the first example of each, are the test's report
    expect({ counts, examples, sequences: runs + Object.keys(CORPUS).length })
      .toEqual({ counts: { P1: 0, P2: 0, P3: 0, P4: 0, P5: 0 }, examples: {}, sequences: runs + Object.keys(CORPUS).length });
  }, 1_800_000);
});
