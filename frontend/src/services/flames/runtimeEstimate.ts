/**
 * Honest duration estimate for an in-browser FLAMeS run, shown BEFORE the clinician starts it.
 *
 * Basis (DESIGN.md §7): measured 230-266 s for a 1 mm brain (8 windows) with 8 WebAssembly threads on a
 * Ryzen 7 5800H (≈ 27.5-33 s per window). WebAssembly threads exist only on a cross-origin-isolated
 * page; app.mstool-ai.com is NOT isolated today (no COOP/COEP headers), so the app runs on ONE thread.
 * The single-thread figure is an extrapolation (thread speed-up assumed ~t^0.9), NOT a measurement.
 */
export interface RuntimeEnvironment {
  crossOriginIsolated: boolean;
  hardwareConcurrency: number;
}

export interface DurationEstimate {
  threads: number;
  lowMinutes: number;
  highMinutes: number;
  measured: boolean;
  text: string;
}

const SECONDS_8_THREADS = 230; // measured, headless Edge, 1 mm FLAIR, 8 windows
const SPEEDUP_EXPONENT = 0.9;

export function expectedThreads(env: RuntimeEnvironment): number {
  return env.crossOriginIsolated ? Math.max(1, Math.min(8, Math.floor(env.hardwareConcurrency || 1))) : 1;
}

export function estimateDuration(env: RuntimeEnvironment): DurationEstimate {
  const threads = expectedThreads(env);
  const seconds1 = SECONDS_8_THREADS * Math.pow(8, SPEEDUP_EXPONENT);
  const seconds = seconds1 / Math.pow(threads, SPEEDUP_EXPONENT);
  // Range for other machines and larger/thinner-slice FLAIRs (more windows): x0.8 .. x1.7.
  const lowMinutes = Math.max(1, Math.round((seconds * 0.8) / 60));
  const highMinutes = Math.max(lowMinutes + 1, Math.round((seconds * 1.7) / 60));
  const measured = threads === 8;
  const text =
    threads === 1
      ? `About ${lowMinutes}-${highMinutes} minutes: this page can use only 1 processor thread (estimate, not measured).`
      : `About ${lowMinutes}-${highMinutes} minutes with ${threads} processor threads${measured ? '' : ' (estimate)'}.`;
  return { threads, lowMinutes, highMinutes, measured, text };
}

export function currentEnvironment(): RuntimeEnvironment {
  const g = globalThis as unknown as { crossOriginIsolated?: boolean; navigator?: { hardwareConcurrency?: number } };
  return {
    crossOriginIsolated: Boolean(g.crossOriginIsolated),
    hardwareConcurrency: g.navigator?.hardwareConcurrency ?? 1,
  };
}

export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}
