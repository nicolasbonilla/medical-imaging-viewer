/**
 * DEV-ONLY viewer demo harness: /dev/viewer-demo
 *
 * Renders the REAL ViewerApp against an in-browser stand-in backend (demoBackend.ts)
 * holding one public MS case, so the viewer can be looked at — and screenshotted
 * headlessly — without a backend, credentials or patient data. Mounted only when
 * `import.meta.env.DEV` (see App.tsx); absent from production bundles.
 *
 * Query parameters:
 *   demo=<step,step,...>   scripted UI steps run after load, e.g.
 *                          `open-seg,plane:sagittal,slice:96` (see runStep)
 * When the steps finish, <body data-demo-ready="1"> is set for the screenshot script
 * (scripts/viewer/screenshot.mjs).
 */
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import ViewerApp from '@/ViewerApp';
import { useViewerStore } from '@/store/useViewerStore';
import { useMultiViewerStore } from '@/store/useMultiViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { installDemoBackend, DEMO_IDS } from './demoBackend';
import i18n from '@/i18n/config';

installDemoBackend();

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function waitFor<T>(probe: () => T | null | undefined | false, timeoutMs = 20000): Promise<T | null> {
  const t0 = performance.now();
  while (performance.now() - t0 < timeoutMs) {
    const v = probe();
    if (v) return v;
    await sleep(100);
  }
  return null;
}

function findByText(selector: string, text: string): HTMLElement | null {
  const nodes = Array.from(document.querySelectorAll<HTMLElement>(selector));
  return nodes.find((n) => (n.textContent ?? '').includes(text)) ?? null;
}

/** The deepest element whose own text contains `text` — clicking it bubbles to the
 *  row/button handler that owns it, whatever the surrounding markup. */
function findLeafByText(text: string): HTMLElement | null {
  const all = Array.from(document.querySelectorAll<HTMLElement>('body *'));
  const hits = all.filter((n) => (n.textContent ?? '').includes(text));
  return hits.find((n) => !Array.from(n.children).some((c) => (c.textContent ?? '').includes(text))) ?? null;
}

type Store = ReturnType<typeof useViewerStore.getState> & {
  setSlicePlane?: (plane: 'axial' | 'coronal' | 'sagittal') => void;
};

async function runStep(step: string): Promise<void> {
  const [name, arg] = step.split(':');
  const viewer = () => useViewerStore.getState() as Store;
  switch (name) {
    case 'open-seg': {
      const row = await waitFor(() => findLeafByText('Expert Rater'));
      row?.click();
      await sleep(2000);
      return;
    }
    case 'analyze': {
      // Run the lesion analysis in the dashboard and wait for its table rows.
      const btn = await waitFor(() => Array.from(document.querySelectorAll<HTMLElement>('button'))
        .find((b) => /^\s*(Analyze|Re-analyze|Analizar)\s*$/i.test(b.textContent ?? '')) ?? null);
      btn?.click();
      await waitFor(() => document.querySelector('[data-lesion-row]'), 15000);
      await sleep(800);
      return;
    }
    case 'plane':
      viewer().setSlicePlane?.(arg as 'axial' | 'coronal' | 'sagittal');
      await sleep(300);
      return;
    case 'slice':
      viewer().setCurrentSliceIndex(Number(arg));
      await sleep(300);
      return;
    case 'zoom':
      viewer().setZoomLevel(Number(arg));
      await sleep(200);
      return;
    case 'wl': {
      const [c, w] = (arg ?? '').split('/').map(Number);
      viewer().setWindowLevel(c, w);
      await sleep(200);
      return;
    }
    case '3d':
      viewer().setViewMode('3d');
      if (arg === 'mpr') viewer().setRender3DMode('multiplanar');
      await sleep(4000);
      return;
    case 'multi': {
      // Prefer the real control (it auto-assigns sequences to panels).
      const key = arg === '2x2' ? '2x2' : arg === 'single' ? 'single' : '1x2';
      document.querySelector<HTMLElement>('[aria-label="Panel layout"]')?.click();
      await sleep(300);
      const item = Array.from(document.querySelectorAll<HTMLElement>('[role="menuitemradio"]'))
        .find((el) => (el.textContent ?? '').toLowerCase().includes(key));
      if (item) item.click();
      else useMultiViewerStore.getState().setLayout((arg as '1x2' | '2x2') ?? '1x2');
      await sleep(3000);
      return;
    }
    case 'click': {
      // click:<visible text>
      const el = await waitFor(() => findLeafByText(decodeURIComponent(arg ?? '')));
      el?.click();
      await sleep(600);
      return;
    }
    case 'aria': {
      // aria:<accessible name> — click the control with that aria-label
      const name = decodeURIComponent(arg ?? '');
      const el = await waitFor(() => document.querySelector<HTMLElement>(`[aria-label="${CSS.escape(name)}"]`));
      el?.click();
      await sleep(500);
      return;
    }
    case 'select-lesion': {
      const rows = await waitFor(() => {
        const r = document.querySelectorAll<HTMLElement>('[data-lesion-row]');
        return r.length ? r : null;
      });
      rows?.[Number(arg ?? 0)]?.click();
      await sleep(600);
      return;
    }
    case 'stroke': {
      // stroke:r0,c0,r1,c1 — drag the mouse over IMAGE pixels of the current view, through
      // the real viewport handlers (same path as a clinician's brush stroke).
      const vp = document.querySelector<HTMLElement>('[data-testid="client-slice-viewport"]');
      const tr = vp?.dataset.transform ? JSON.parse(vp.dataset.transform) : null;
      if (!vp || !tr) return;
      const [r0, c0, r1, c1] = (arg ?? '').split('_').map(Number);
      const rect = vp.getBoundingClientRect();
      const at = (r: number, c: number) => ({
        clientX: rect.left + tr.originX + (c + 0.5) * tr.scaleX,
        clientY: rect.top + tr.originY + (r + 0.5) * tr.scaleY,
      });
      const fire = (type: string, p: { clientX: number; clientY: number }) =>
        vp.dispatchEvent(new MouseEvent(type, { bubbles: true, button: 0, buttons: 1, ...p }));
      fire('mousedown', at(r0, c0));
      const steps = 24;
      for (let s = 1; s <= steps; s++) {
        fire('mousemove', at(r0 + ((r1 - r0) * s) / steps, c0 + ((c1 - c0) * s) / steps));
        await sleep(15);
      }
      fire('mouseup', at(r1, c1));
      await sleep(500);
      return;
    }
    case 'brush':
      useSegmentationStore.getState().setBrushSize(Number(arg ?? 3));
      await sleep(200);
      return;
    case 'undo':
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true }));
      await sleep(500);
      return;
    case 'wait':
      await sleep(Number(arg ?? 1000));
      return;
    case 'lang':
      await i18n.changeLanguage(arg ?? 'en');
      await sleep(400);
      return;
    default:
      console.warn('[ViewerDemo] unknown step', step);
  }
}

export default function ViewerDemo() {
  const [params, setParams] = useSearchParams();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (params.get('studyId') !== DEMO_IDS.study) {
      const next = new URLSearchParams(params);
      next.set('studyId', DEMO_IDS.study);
      setParams(next, { replace: true });
      return;
    }
    setReady(true);
  }, [params, setParams]);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    const steps = (params.get('demo') ?? '').split(',').map((s) => s.trim()).filter(Boolean);
    (async () => {
      // Let the study + first image load before scripted interaction.
      await waitFor(() => useViewerStore.getState().currentSeries, 30000);
      // v3 client viewport: wait until the volume is parsed and drawn.
      await waitFor(() => document.querySelector('[data-testid="client-slice-viewport"][data-ready="1"]')
        || document.querySelector('canvas'), 30000);
      await sleep(1500);
      for (const s of steps) {
        if (cancelled) return;
        await runStep(s);
      }
      await sleep(1200);
      if (!cancelled) document.body.dataset.demoReady = '1';
    })();
    return () => { cancelled = true; };
  }, [ready]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ready) return null;
  return <ViewerApp />;
}
