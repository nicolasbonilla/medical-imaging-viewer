#!/usr/bin/env node
/**
 * CAPA-010 — real-browser probe of the LIVE viewer page layout (defect 4: the standing
 * "Laterality not labelled" caveat rendered off-screen).
 *
 * jsdom has no layout engine, so a clipped annotation cannot be observed by the unit
 * suite. This probe runs the REAL application code (Vite dev server, real ViewerApp,
 * real Tailwind CSS) in a REAL headless Microsoft Edge, answers every backend request
 * with a fixed synthetic study (Chrome DevTools Protocol request interception — no
 * backend, no network, no patient data), and measures, at common window sizes, how much
 * of the safety caveat and of the image is inside the visible area of every clipping
 * ancestor.
 *
 * It starts its OWN Vite server and its OWN Edge (temporary profile) and shuts down
 * exactly those two processes by PID (never by image name).
 *
 * Usage (from the repository root, frontend/node_modules installed):
 *   node scripts/safety/capa010_viewer_layout_probe.mjs <out.json> [screenshotDir]
 * Env: EDGE (msedge.exe path), PORT (default 5181), CDP_PORT (default 9341).
 */
import { spawn, execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { deflateSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FRONTEND = join(ROOT, 'frontend');
const EDGE = process.env.EDGE ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const PORT = Number(process.env.PORT ?? 5181);
const CDP_PORT = Number(process.env.CDP_PORT ?? 9341);
const ORIGIN = `http://127.0.0.1:${PORT}`;
const SIZES = [[1366, 768], [1600, 900], [1920, 1080]];

const [outArg, shotDirArg] = process.argv.slice(2);
if (!outArg) { console.error('usage: capa010_viewer_layout_probe.mjs <out.json> [screenshotDir]'); process.exit(2); }
const OUT = resolve(outArg);
const SHOTS = shotDirArg ? resolve(shotDirArg) : null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const killTree = (pid) => { if (!pid) return; try { execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' }); } catch { /* gone */ } };

async function waitHttp(url, timeoutMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try { const r = await fetch(url); if (r.ok) return r; } catch { /* not up yet */ }
    await sleep(300);
  }
  throw new Error(`timeout waiting for ${url}`);
}

// ── synthetic 182 x 218 grey slice with a bright 4-px frame (so a clipped edge is visible)
function crc32(buf) {
  let c, crc = 0xffffffff;
  for (let n = 0; n < buf.length; n++) {
    c = (crc ^ buf[n]) & 0xff;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
function slicePng(w, h) {
  const raw = Buffer.alloc((w + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (w + 1)] = 0;
    for (let x = 0; x < w; x++) {
      const frame = x < 4 || y < 4 || x >= w - 4 || y >= h - 4;
      raw[y * (w + 1) + 1 + x] = frame ? 255 : 60 + Math.round((120 * y) / h);
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 0; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]).toString('base64');
}

// ── synthetic study (no patient data) ──
const P = '11111111-1111-4111-8111-111111111111';
const S = '22222222-2222-4222-8222-222222222222';
const SE = '33333333-3333-4333-8333-333333333333';
const I1 = '44444444-4444-4444-8444-444444444444';
const I2 = '55555555-5555-4555-8555-555555555555';
const FILE1 = `patients/${P}/studies/${S}/series/${SE}/${I1}/sub-01_FLAIR.nii.gz`;
const FILE2 = `patients/${P}/studies/${S}/series/${SE}/${I2}/sub-01_T1w.nii.gz`;
const USER = { id: 'u1', username: 'probe', email: 'probe@example.org', full_name: 'Layout Probe', role: 'RADIOLOGIST', is_active: true };
const PNG = slicePng(182, 218);
const series = (file) => ({
  id: file, name: 'probe', format: 'nifti', total_slices: 3,
  metadata: { rows: 218, columns: 182, slices: 3, pixel_spacing: [1, 1], anatomical_orientation: 'LAS', modality: 'MR' },
  slices: [0, 1, 2].map((i) => ({ slice_index: i, image_data: PNG, format: 'nifti', width: 182, height: 218 })),
});
// Synthetic NIfTI-1 (uint8, 40 x 48 x 36, 1 mm, sform LAS-like): an ellipsoid "brain" and
// a bright blob in the +i half, so a 3D render has something to draw. No patient data.
function syntheticNifti() {
  const [nx, ny, nz] = [40, 48, 36];
  const hdr = Buffer.alloc(352);
  hdr.writeInt32LE(348, 0);
  [3, nx, ny, nz, 1, 1, 1, 1].forEach((v, k) => hdr.writeInt16LE(v, 40 + 2 * k));
  hdr.writeInt16LE(2, 70); hdr.writeInt16LE(8, 72);
  [1, 1, 1, 1, 0, 0, 0, 0].forEach((v, k) => hdr.writeFloatLE(v, 76 + 4 * k));
  hdr.writeFloatLE(352, 108); hdr.writeFloatLE(1, 112); hdr.writeFloatLE(0, 116);
  hdr[123] = 2; hdr.writeInt16LE(0, 252); hdr.writeInt16LE(1, 254);
  [[-1, 0, 0, 20], [0, 1, 0, -24], [0, 0, 1, -18]].forEach((row, r) => row.forEach((v, k) => hdr.writeFloatLE(v, 280 + 16 * r + 4 * k)));
  hdr.write('n+1\0', 344, 'latin1');
  const data = Buffer.alloc(nx * ny * nz);
  for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    const e = ((i - 19.5) / 17) ** 2 + ((j - 23.5) / 21) ** 2 + ((k - 17.5) / 15) ** 2;
    const blob = ((i - 28) / 4) ** 2 + ((j - 24) / 4) ** 2 + ((k - 18) / 4) ** 2;
    data[i + nx * (j + ny * k)] = blob < 1 ? 250 : e < 1 ? 120 : 0;
  }
  return Buffer.concat([hdr, data]);
}
const NIFTI = syntheticNifti();

function apiResponse(url) {
  const u = new URL(url);
  const p = u.pathname;
  if (p.startsWith('/api/v1/imaging/nifti/')) return NIFTI;
  if (p === '/api/v1/auth/me') return USER;
  if (p === `/api/v1/studies/${S}`) return { id: S, patient_id: P, study_description: 'Synthetic layout probe', modality: 'MR', study_date: '2026-01-01', status: 'completed' };
  if (p === `/api/v1/studies/${S}/series`) return [{ id: SE, study_id: S, series_description: 'probe', modality: 'MR' }];
  if (p === `/api/v1/studies/series/${SE}/instances`) return [
    { id: I1, series_id: SE, gcs_object_name: FILE1, original_filename: 'sub-01_FLAIR.nii.gz' },
    { id: I2, series_id: SE, gcs_object_name: FILE2, original_filename: 'sub-01_T1w.nii.gz' },
  ];
  if (p === `/api/v1/patients/${P}`) return { id: P, full_name: 'Synthetic Probe', mrn: 'MRN-PROBE-1', age: 40, gender: 'female' };
  if (p.startsWith('/api/v1/imaging/process/')) return series(decodeURIComponent(p.slice('/api/v1/imaging/process/'.length)));
  if (p === '/api/v1/segmentation/list') return [];
  return null; // unknown → 404 (recorded)
}

class Cdp {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.listeners = []; this.events = [];
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { res, rej } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
      } else if (msg.method) {
        if (msg.method === 'Runtime.exceptionThrown') this.events.push(msg);
        for (const l of this.listeners) l(msg);
      }
    };
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    this.ws.send(JSON.stringify(payload));
    return new Promise((res, rej) => this.pending.set(id, { res, rej }));
  }
}

// Visible fraction of the caveat / image after intersecting with the window and every
// ancestor whose overflow clips (anything but `visible`).
const MEASURE = `(() => {
  const rect = (r) => ({ top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height, width: r.width });
  const clipChain = (el) => {
    let box = { top: 0, left: 0, bottom: innerHeight, right: innerWidth };
    for (let a = el.parentElement; a; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
        const r = a.getBoundingClientRect();
        box = { top: Math.max(box.top, r.top), left: Math.max(box.left, r.left), bottom: Math.min(box.bottom, r.bottom), right: Math.min(box.right, r.right) };
      }
    }
    return box;
  };
  const visibleFraction = (el) => {
    const r = el.getBoundingClientRect();
    const c = clipChain(el);
    const w = Math.max(0, Math.min(r.right, c.right) - Math.max(r.left, c.left));
    const h = Math.max(0, Math.min(r.bottom, c.bottom) - Math.max(r.top, c.top));
    return { rect: rect(r), clip: c, visibleFraction: r.width * r.height > 0 ? (w * h) / (r.width * r.height) : 0, hiddenBelowPx: Math.max(0, r.bottom - c.bottom) };
  };
  const overlays = [...document.querySelectorAll('[data-testid="viewport-safety-overlay"]')];
  const caveats = overlays.map((o) => [...o.querySelectorAll('div')].find((d) => d.children.length === 0 && /Laterality not labelled/.test(d.textContent)));
  const canvases = [...document.querySelectorAll('#main-content canvas')].filter((c) => c.width > 0);
  return {
    window: { innerWidth, innerHeight },
    overlays: overlays.length,
    identitiesShown: [...document.querySelectorAll('[data-testid="viewport-patient-identity"]')].filter((e) => /MRN-PROBE-1/.test(e.textContent)).length,
    caveats: caveats.map((c) => (c ? visibleFraction(c) : null)),
    images: canvases.map((c) => visibleFraction(c)),
  };
})()`;

async function openViewer(cdp, w, h, layout) {
  const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  const unknown = [];
  cdp.listeners.push(async (msg) => {
    if (msg.sessionId !== sessionId || msg.method !== 'Fetch.requestPaused') return;
    const { requestId, request } = msg.params;
    const body = apiResponse(request.url);
    if (body === null) unknown.push(request.url);
    const binary = Buffer.isBuffer(body);
    const bytes = binary ? body : Buffer.from(JSON.stringify(body ?? { detail: 'not in probe fixture' }));
    await cdp.send('Fetch.fulfillRequest', {
      requestId, responseCode: body === null ? 404 : 200,
      responseHeaders: [
        { name: 'Content-Type', value: binary ? 'application/octet-stream' : 'application/json' },
        { name: 'Content-Length', value: String(bytes.length) },
      ],
      body: bytes.toString('base64'),
    }, sessionId).catch(() => {});
  });
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: `${ORIGIN}/api/*`, requestStage: 'Request' }] }, sessionId);
  await cdp.send('Page.enable', {}, sessionId);
  await cdp.send('Runtime.enable', {}, sessionId);
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: false }, sessionId);
  // A session for the probe user, so ProtectedRoute lets the viewer render.
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
    source: `try { localStorage.setItem('access_token', 'probe-token'); localStorage.setItem('user', ${JSON.stringify(JSON.stringify(USER))}); localStorage.setItem('i18nextLng', 'en'); } catch (e) {}`,
  }, sessionId);
  await cdp.send('Page.navigate', { url: `${ORIGIN}/app/viewer?studyId=${S}` }, sessionId);
  const t0 = Date.now();
  let ready = false;
  while (Date.now() - t0 < 90000) {
    const r = await cdp.send('Runtime.evaluate', { expression: `!!document.querySelector('[data-testid="viewport-safety-overlay"]') && [...document.querySelectorAll('#main-content canvas')].some(c => c.width > 0)`, returnByValue: true }, sessionId);
    if (r.result?.value === true) { ready = true; break; }
    await sleep(400);
  }
  if (ready && layout.startsWith('3d')) {
    const clickText = (text) => cdp.send('Runtime.evaluate', {
      expression: `(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}); if (b) b.click(); return !!b; })()`,
      returnByValue: true,
    }, sessionId);
    if ((await clickText('3D')).result?.value !== true) ready = false;
    await sleep(800);
    if (layout === '3d-mpr' && (await clickText('Multiplanar')).result?.value !== true) ready = false;
    const want = layout === '3d-mpr' ? 4 : 1;
    const t1 = Date.now();
    while (Date.now() - t1 < 30000) {
      const r = await cdp.send('Runtime.evaluate', { expression: `[...document.querySelectorAll('#main-content canvas')].filter(c => c.width > 0).length`, returnByValue: true }, sessionId);
      if (r.result?.value >= want) break;
      await sleep(400);
    }
    await sleep(4000); // niivue download + first render
  } else if (ready && layout !== 'single') {
    // English labels: "1x2 Side by Side" / "2x2 Grid" (layout.sideBySide / layout.grid).
    const prefix = layout === '1x2' ? '1x2' : '2x2';
    const clicked = await cdp.send('Runtime.evaluate', {
      expression: `(() => { const b = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label').startsWith('${prefix}')); if (b) b.click(); return !!b; })()`,
      returnByValue: true,
    }, sessionId);
    if (clicked.result?.value !== true) ready = false;
    const t1 = Date.now();
    while (Date.now() - t1 < 30000) {
      const r = await cdp.send('Runtime.evaluate', { expression: `[...document.querySelectorAll('#main-content canvas')].filter(c => c.width > 0).length`, returnByValue: true }, sessionId);
      if (r.result?.value >= 2) break;
      await sleep(400);
    }
  }
  await sleep(1500);
  return { targetId, sessionId, ready, unknown };
}

async function main() {
  const vite = spawn(process.execPath, [join(FRONTEND, 'node_modules/vite/bin/vite.js'), '--port', String(PORT), '--strictPort', '--host', '127.0.0.1'], {
    cwd: FRONTEND, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, VITE_API_BASE_URL: ORIGIN },
  });
  vite.stderr.on('data', (d) => process.stderr.write(`[vite] ${d}`));
  const profile = mkdtempSync(join(tmpdir(), 'capa010-edge-'));
  let edge;
  const result = { executed: new Date().toISOString(), method: 'real ViewerApp in headless Edge; backend answered by CDP request interception with a synthetic study; visible fraction = intersection with the window and every overflow-clipping ancestor', runs: [] };
  try {
    await waitHttp(`${ORIGIN}/`, 60000);
    edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', '--hide-scrollbars',
      '--use-angle=swiftshader', '--enable-unsafe-swiftshader', 'about:blank'], { stdio: 'ignore' });
    const ver = await (await waitHttp(`http://127.0.0.1:${CDP_PORT}/json/version`, 30000)).json();
    const ws = new WebSocket(ver.webSocketDebuggerUrl);
    await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
    const cdp = new Cdp(ws);
    // Warm-up: Vite pre-bundles dependencies on the first visit and may force a reload.
    const warm = await openViewer(cdp, 1366, 768, 'single');
    await cdp.send('Target.closeTarget', { targetId: warm.targetId });
    for (const layout of ['single', '1x2', '3d-volume', '3d-mpr']) {
      for (const [w, h] of (layout.startsWith('3d') ? [SIZES[0]] : SIZES)) {
        const v = await openViewer(cdp, w, h, layout);
        const m = await cdp.send('Runtime.evaluate', { expression: MEASURE, returnByValue: true }, v.sessionId);
        const run = { layout, size: `${w}x${h}`, ready: v.ready, unknownRequests: [...new Set(v.unknown)], ...m.result.value };
        result.runs.push(run);
        const cav = run.caveats.map((c) => (c ? c.visibleFraction.toFixed(2) : 'absent')).join(',');
        const img = run.images.map((c) => c.hiddenBelowPx.toFixed(0)).join(',');
        console.log(`${layout.padEnd(9)} ${run.size.padEnd(9)} ready=${v.ready} images=${run.images.length} overlays=${run.overlays} identities=${run.identitiesShown} caveat visible fraction=[${cav}] image px hidden below=[${img}]`);
        if (SHOTS) {
          const { data } = await cdp.send('Page.captureScreenshot', { format: 'png' }, v.sessionId);
          writeFileSync(join(SHOTS, `${layout}-${w}x${h}.png`), Buffer.from(data, 'base64'));
        }
        await cdp.send('Target.closeTarget', { targetId: v.targetId });
      }
    }
    result.pageExceptions = cdp.events.slice(0, 10).map((e) => e.params?.exceptionDetails?.exception?.description?.split('\n')[0]);
    try { await cdp.send('Browser.close'); } catch { /* closing */ }
    ws.close();
  } finally {
    await sleep(500);
    killTree(edge?.pid);
    killTree(vite.pid);
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* profile lock */ }
  }
  // One annotation per image in the 2D views (multi-panel: one per panel), one for the whole
  // 3D viewport (its 4 multiplanar canvases show ONE volume); every caveat fully inside the
  // visible area; no image cut at the bottom.
  const expectedAnnotations = (r) => (r.layout === '1x2' ? 2 : 1);
  result.allCaveatsFullyVisible = result.runs.every((r) => r.ready && r.caveats.length === expectedAnnotations(r)
    && r.caveats.every((c) => c && c.visibleFraction > 0.999));
  result.noImageCutAtBottom = result.runs.every((r) => r.images.every((i) => i.hiddenBelowPx < 0.5));
  // Identity on every view: one per 2D panel in multi-panel, one for the 3D viewport.
  result.identityInEveryView = result.runs.every((r) => r.ready && r.identitiesShown >= (r.layout === '1x2' ? 2 : 1));
  writeFileSync(OUT, JSON.stringify(result, null, 2));
  console.log(`allCaveatsFullyVisible=${result.allCaveatsFullyVisible} noImageCutAtBottom=${result.noImageCutAtBottom} identityInEveryView=${result.identityInEveryView} -> ${OUT}`);
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
