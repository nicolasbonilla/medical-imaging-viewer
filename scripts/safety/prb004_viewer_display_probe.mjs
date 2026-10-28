#!/usr/bin/env node
/**
 * PRB-004 .. PRB-009 — real-browser probe of the LIVE viewer page (display and orientation).
 *
 * jsdom has no WebGL, so the unit tests can check niivue's placement math but not its drawn pixels.
 * This probe runs the REAL application (Vite dev server, real ViewerApp, real niivue on a real GPU
 * context) in a REAL headless Microsoft Edge served from a host name WITHOUT A DOT (http://localhost),
 * answers every backend request with a fixed synthetic study (Chrome DevTools Protocol interception —
 * no backend, no network, no patient data), and measures from the rendered pixels:
 *
 *   PRB-004  where an asymmetric marker of the image appears in the Standard view and in the "W/L GPU"
 *            view, relative to the drawn head (same place = same orientation), and that the mask is
 *            drawn in the GPU view on the voxels it labels (red where the Standard view shows them);
 *   PRB-005  the GPU and 3D views load on a dot-less host (no "toUpperCase" page error, image drawn);
 *   PRB-006  the 3D volume render with the mask shown is not tinted red outside the lesion;
 *   PRB-007  the 2x2 grid of a study of preprocessed images only shows four images;
 *   PRB-008  the viewer opens on the middle slice;
 *   PRB-009  no request for /models/brain_screening.onnx and no Quick Screen button.
 *
 * It starts its OWN Vite server and its OWN Edge (temporary profile) and stops exactly those two
 * processes by PID (never by image name).
 *
 * Usage (from the repository root, frontend/node_modules installed):
 *   node scripts/safety/prb004_viewer_display_probe.mjs <out.json> [screenshotDir]
 * Env: FRONTEND (frontend dir to run, default ./frontend — e.g. a checkout of the base commit),
 *      EDGE (msedge.exe), PORT (default 5191), CDP_PORT (default 9351).
 */
import { spawn, execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { deflateSync, inflateSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FRONTEND = resolve(process.env.FRONTEND ?? join(ROOT, 'frontend'));
const EDGE = process.env.EDGE ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const PORT = Number(process.env.PORT ?? 5191);
const CDP_PORT = Number(process.env.CDP_PORT ?? 9351);
const ORIGIN = `http://localhost:${PORT}`; // PRB-005: a host name without a dot
const [W, H] = [1600, 900];

const [outArg, shotDirArg] = process.argv.slice(2);
if (!outArg) { console.error('usage: prb004_viewer_display_probe.mjs <out.json> [screenshotDir]'); process.exit(2); }
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

// ── PNG encode (grey) / decode (RGB/RGBA 8-bit) ──
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
function greyPng(w, h, px) {
  const raw = Buffer.alloc((w + 1) * h);
  for (let y = 0; y < h; y++) { raw[y * (w + 1)] = 0; for (let x = 0; x < w; x++) raw[y * (w + 1) + 1 + x] = px(y, x); }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 0;
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]).toString('base64');
}
function decodePng(buf) {
  let off = 8, w = 0, h = 0, ct = 0; const idat = [];
  while (off < buf.length) {
    const len = buf.readUInt32BE(off); const type = buf.toString('latin1', off + 4, off + 8); const data = buf.subarray(off + 8, off + 8 + len);
    if (type === 'IHDR') { w = data.readUInt32BE(0); h = data.readUInt32BE(4); ct = data[9]; if (data[8] !== 8) throw new Error('bit depth'); }
    if (type === 'IDAT') idat.push(data);
    off += 12 + len;
  }
  const bpp = ct === 6 ? 4 : ct === 2 ? 3 : (() => { throw new Error(`colour type ${ct}`); })();
  const raw = inflateSync(Buffer.concat(idat)); const stride = w * bpp; const out = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)]; const line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? out[y * stride + x - bpp] : 0; const b = y > 0 ? out[(y - 1) * stride + x] : 0;
      const c = x >= bpp && y > 0 ? out[(y - 1) * stride + x - bpp] : 0;
      const p = a + b - c; const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
      const pr = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      out[y * stride + x] = (line[x] + [0, a, b, (a + b) >> 1, pr][f]) & 0xff;
    }
  }
  return { w, h, bpp, px: (x, y) => { const i = y * stride + x * bpp; return [out[i], out[i + 1], out[i + 2]]; } };
}

// ── synthetic study (no patient data). Storage grid (i rows, j columns, k slices) = 40 x 48 x 36,
// 1 mm, LAS-like sform (x flipped), as the demo study. An ellipsoid "head" (90-129) with two markers:
// A (250) at rows 14-18, columns 36-42 — the lesion mask labels exactly these voxels — and B (180) at
// rows 27-31, columns 8-12. The standard view draws row i down, column j right: A up and to the right
// of B, twice as far across as up (so a 90-degree turn or a transpose cannot look the same).
const [NX, NY, NZ] = [40, 48, 36];
const inHead = (i, j, k) => ((i - 19.5) / 17) ** 2 + ((j - 23.5) / 21) ** 2 + ((k - 17.5) / 15) ** 2 < 1;
const isA = (i, j) => i >= 14 && i <= 18 && j >= 36 && j <= 42;
const isB = (i, j) => i >= 27 && i <= 31 && j >= 8 && j <= 12;
const value = (i, j, k) => (!inHead(i, j, k) ? 0 : isA(i, j) ? 250 : isB(i, j) ? 180 : 90 + ((i + j) % 40));
const lesion = (i, j, k) => (inHead(i, j, k) && isA(i, j) ? 1 : 0);
function nifti(voxel, { calMin = 0, calMax = 0, descrip = '' } = {}) {
  const hdr = Buffer.alloc(352);
  hdr.writeInt32LE(348, 0);
  [3, NX, NY, NZ, 1, 1, 1, 1].forEach((v, k) => hdr.writeInt16LE(v, 40 + 2 * k));
  hdr.writeInt16LE(2, 70); hdr.writeInt16LE(8, 72);
  [1, 1, 1, 1, 0, 0, 0, 0].forEach((v, k) => hdr.writeFloatLE(v, 76 + 4 * k));
  hdr.writeFloatLE(352, 108); hdr.writeFloatLE(1, 112); hdr.writeFloatLE(0, 116);
  hdr.writeFloatLE(calMax, 124); hdr.writeFloatLE(calMin, 128);
  hdr.write(descrip, 148, 'latin1');
  hdr[123] = 2; hdr.writeInt16LE(0, 252); hdr.writeInt16LE(1, 254);
  [[-1, 0, 0, 20], [0, 1, 0, -24], [0, 0, 1, -18]].forEach((row, r) => row.forEach((v, k) => hdr.writeFloatLE(v, 280 + 16 * r + 4 * k)));
  hdr.write('n+1\0', 344, 'latin1');
  const data = Buffer.alloc(NX * NY * NZ);
  for (let k = 0; k < NZ; k++) for (let j = 0; j < NY; j++) for (let i = 0; i < NX; i++) data[i + NX * (j + NY * k)] = voxel(i, j, k);
  return Buffer.concat([hdr, data]);
}
const IMAGE = nifti(value);
// As stored by the app before PRB-006: the MRI's display window copied into the mask header.
const MASK_NII = nifti(lesion, { calMin: -15.5, calMax: 189.2, descrip: 'RC031-ORIENT-V2' });
function binaryMask() { // GET /mask/binary: [D][H][W] u32 LE, then internal (k, i, j)
  const b = Buffer.alloc(12 + NX * NY * NZ);
  b.writeUInt32LE(NZ, 0); b.writeUInt32LE(NX, 4); b.writeUInt32LE(NY, 8);
  for (let k = 0; k < NZ; k++) for (let i = 0; i < NX; i++) for (let j = 0; j < NY; j++) b[12 + (k * NX + i) * NY + j] = lesion(i, j, k);
  return b;
}
const MASK_BIN = binaryMask();
const SLICES = Array.from({ length: NZ }, (_, k) => ({ slice_index: k, image_data: greyPng(NY, NX, (i, j) => value(i, j, k)), format: 'nifti', width: NY, height: NX }));

const P = '11111111-1111-4111-8111-111111111111';
const S = '22222222-2222-4222-8222-222222222222';
const SE = '33333333-3333-4333-8333-333333333333';
const SEG = '66666666-6666-4666-8666-666666666666';
const INST = [['44444444-4444-4444-8444-444444444441', 'sub-01_desc-preproc_FLAIR.nii.gz'],
              ['44444444-4444-4444-8444-444444444442', 'sub-01_desc-preproc_T1w.nii.gz'],
              ['44444444-4444-4444-8444-444444444443', 'sub-01_desc-preproc_T2w.nii.gz'],
              ['44444444-4444-4444-8444-444444444444', 'sub-01_ce-gd_desc-preproc_T1w.nii.gz']];
const fileOf = (id, name) => `patients/${P}/studies/${S}/series/${SE}/${id}/${name}`;
const FILE1 = fileOf(...INST[0]);
const USER = { id: 'u1', username: 'probe', email: 'probe@example.org', full_name: 'Display Probe', role: 'RADIOLOGIST', is_active: true };
const series = (file) => ({
  id: file, name: 'probe', format: 'nifti', total_slices: NZ,
  metadata: { rows: NX, columns: NY, slices: NZ, pixel_spacing: [1, 1], anatomical_orientation: 'LAS', modality: 'MR',
    window_center: 125, window_width: 250 },
  slices: SLICES,
});
const SEG_SUMMARY = { segmentation_id: SEG, file_id: FILE1, total_slices: NZ,
  metadata: { file_id: FILE1, created_at: '2026-01-01T00:00:00Z', modified_at: '2026-01-01T00:00:00Z', description: 'Probe lesion mask',
    labels: [{ id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false }, { id: 1, name: 'Lesion', color: '#FF0000', opacity: 0.6, visible: true }] } };

function apiResponse(url) {
  const p = new URL(url).pathname;
  if (p.startsWith('/api/v1/imaging/nifti/')) return IMAGE;
  if (p.startsWith('/api/v1/imaging/process/')) return series(decodeURIComponent(p.slice('/api/v1/imaging/process/'.length)));
  if (p === '/api/v1/auth/me') return USER;
  if (p === `/api/v1/studies/${S}`) return { id: S, patient_id: P, study_description: 'Synthetic display probe', modality: 'MR', study_date: '2026-01-01', status: 'completed' };
  if (p === `/api/v1/studies/${S}/series`) return [{ id: SE, study_id: S, series_description: 'probe', modality: 'MR' }];
  if (p === `/api/v1/studies/series/${SE}/instances`) return INST.map(([id, name]) => ({ id, series_id: SE, gcs_object_name: fileOf(id, name), original_filename: name, file_size_bytes: IMAGE.length }));
  if (p === `/api/v1/patients/${P}`) return { id: P, full_name: 'Synthetic Probe', mrn: 'MRN-PROBE-4', age: 40, gender: 'female' };
  if (p === '/api/v1/segmentation/list') return [SEG_SUMMARY];
  if (p === `/api/v1/segmentation/${SEG}`) return SEG_SUMMARY;
  if (p === `/api/v1/segmentation/${SEG}/nifti`) return MASK_NII;
  if (p === `/api/v1/segmentation/${SEG}/mask/binary`) return MASK_BIN;
  return null; // unknown → 404 (recorded)
}

class Cdp {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.listeners = []; this.exceptions = []; this.console = [];
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { res, rej } = this.pending.get(msg.id); this.pending.delete(msg.id);
        msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
      } else if (msg.method) {
        if (msg.method === 'Runtime.exceptionThrown') this.exceptions.push(msg.params?.exceptionDetails?.exception?.description?.split('\n')[0] ?? msg.params?.exceptionDetails?.text);
        if (msg.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(msg.params.type)) {
          this.console.push(`${msg.params.type}: ${(msg.params.args || []).map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 300)}`);
        }
        if (msg.method === 'Log.entryAdded' && ['error', 'warning'].includes(msg.params.entry.level)) {
          this.console.push(`log.${msg.params.entry.level}: ${msg.params.entry.text.slice(0, 300)} ${msg.params.entry.url ?? ''}`);
        }
        for (const l of this.listeners) l(msg);
      }
    };
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id; const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    this.ws.send(JSON.stringify(payload));
    return new Promise((res, rej) => this.pending.set(id, { res, rej }));
  }
}

const evaluate = async (cdp, sid, expression) => (await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, sid)).result?.value;
async function until(cdp, sid, expression, ms = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await evaluate(cdp, sid, expression)) return true; await sleep(300); }
  return false;
}
const clickButton = (cdp, sid, text) => evaluate(cdp, sid, `(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)} || (b.getAttribute('aria-label') || '').startsWith(${JSON.stringify(text)})); if (b) b.click(); return !!b; })()`);
const clickText = (cdp, sid, text) => evaluate(cdp, sid, `(() => { const el = [...document.querySelectorAll('button, [role=button], div, span, p')].reverse().find(e => e.children.length === 0 && e.textContent.trim() === ${JSON.stringify(text)}); if (el) { el.click(); return true; } return false; })()`);

/** Marker centroids in a captured region, relative to the drawn head's bounding box (0..1). */
function measure(img) {
  const acc = { head: [Infinity, Infinity, -Infinity, -Infinity], B: [0, 0, 0], A: [0, 0, 0], red: [0, 0, 0], tinted: 0 };
  // Pixels near a reddish one are the blended rim of the drawn mask, not a grey marker.
  const R = 6; const nearRed = new Uint8Array(img.w * img.h);
  for (let y = 0; y < img.h; y++) for (let x = 0; x < img.w; x++) {
    const [r, g] = img.px(x, y);
    if (r - g > 20) for (let dy = -R; dy <= R; dy++) for (let dx = -R; dx <= R; dx++) {
      const yy = y + dy, xx = x + dx;
      if (yy >= 0 && yy < img.h && xx >= 0 && xx < img.w) nearRed[yy * img.w + xx] = 1;
    }
  }
  for (let y = 0; y < img.h; y++) for (let x = 0; x < img.w; x++) {
    const [r, g, b] = img.px(x, y);
    const grey = Math.abs(r - g) < 25 && Math.abs(g - b) < 25 && !nearRed[y * img.w + x];
    if (Math.max(r, g, b) > 40) { const hb = acc.head; hb[0] = Math.min(hb[0], x); hb[1] = Math.min(hb[1], y); hb[2] = Math.max(hb[2], x); hb[3] = Math.max(hb[3], y); }
    if (grey && g >= 160 && g <= 215) { acc.B[0] += x; acc.B[1] += y; acc.B[2]++; }
    if (grey && g > 235) { acc.A[0] += x; acc.A[1] += y; acc.A[2]++; }
    if (r - g > 60 && r > 120) { acc.red[0] += x; acc.red[1] += y; acc.red[2]++; }
    if (r - g > 30 && r > 30) acc.tinted++;
  }
  const [x0, y0, x1, y1] = acc.head;
  const rel = ([sx, sy, n]) => (n > 20 ? { u: +((sx / n - x0) / (x1 - x0)).toFixed(3), v: +((sy / n - y0) / (y1 - y0)).toFixed(3), px: n } : null);
  // Red-tinted share of the whole captured viewport: the lesion and niivue's own crosshair lines are
  // red by design (a few per cent); the PRB-006 "fog" tints the whole volume extent.
  return { headBox: { x0, y0, x1, y1 }, B: rel(acc.B), A: rel(acc.A), red: rel(acc.red),
    redTintedFraction: +(acc.tinted / (img.w * img.h)).toFixed(4) };
}
const HIDE_DOM = `(() => { const s = document.createElement('style'); s.id = 'prb004-probe-hide';
  s.textContent = '#main-content * { visibility: hidden !important } #main-content canvas { visibility: visible !important }';
  document.head.appendChild(s); return true; })()`;
const SHOW_DOM = `(() => { document.getElementById('prb004-probe-hide')?.remove(); return true; })()`;

/** Screenshot of a canvas region with the page's own text and buttons hidden (pixels of the canvases only). */
async function captureCanvas(cdp, sid, selector, file) {
  await evaluate(cdp, sid, HIDE_DOM);
  await sleep(300);
  try { return await captureCanvasRaw(cdp, sid, selector, file); } finally { await evaluate(cdp, sid, SHOW_DOM); }
}
async function captureCanvasRaw(cdp, sid, selector, file) {
  const box = await evaluate(cdp, sid, `(() => { const c = [...document.querySelectorAll(${JSON.stringify(selector)})].filter(c => c.width > 0 && c.getBoundingClientRect().width > 0)[0]; if (!c) return null; const r = c.getBoundingClientRect(); return { x: r.left, y: r.top, width: r.width, height: r.height }; })()`);
  if (!box) return null;
  const { data } = await cdp.send('Page.captureScreenshot', { format: 'png', clip: { ...box, scale: 1 } }, sid);
  const buf = Buffer.from(data, 'base64');
  if (SHOTS && file) writeFileSync(join(SHOTS, file), buf);
  return decodePng(buf);
}

async function openViewer(cdp) {
  const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  const requests = []; const unknown = [];
  cdp.listeners.push(async (msg) => {
    if (msg.sessionId !== sessionId) return;
    if (msg.method === 'Network.requestWillBeSent') requests.push(msg.params.request.url);
    if (msg.method !== 'Fetch.requestPaused') return;
    const { requestId, request } = msg.params;
    const body = apiResponse(request.url);
    if (body === null) unknown.push(request.url);
    const binary = Buffer.isBuffer(body);
    const bytes = binary ? body : Buffer.from(JSON.stringify(body ?? { detail: 'not in probe fixture' }));
    await cdp.send('Fetch.fulfillRequest', {
      requestId, responseCode: body === null ? 404 : 200,
      responseHeaders: [{ name: 'Content-Type', value: binary ? 'application/octet-stream' : 'application/json' }, { name: 'Content-Length', value: String(bytes.length) }],
      body: bytes.toString('base64'),
    }, sessionId).catch(() => {});
  });
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: `${ORIGIN}/api/*`, requestStage: 'Request' }] }, sessionId);
  for (const d of ['Page', 'Runtime', 'Network', 'Log']) await cdp.send(`${d}.enable`, {}, sessionId);
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false }, sessionId);
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
    source: `try { localStorage.setItem('access_token', 'probe-token'); localStorage.setItem('user', ${JSON.stringify(JSON.stringify(USER))}); localStorage.setItem('i18nextLng', 'en'); } catch (e) {}`,
  }, sessionId);
  await cdp.send('Page.navigate', { url: `${ORIGIN}/app/viewer?studyId=${S}` }, sessionId);
  const ready = await until(cdp, sessionId, `!!document.querySelector('[data-testid="viewport-safety-overlay"]') && [...document.querySelectorAll('#main-content canvas')].some(c => c.width > 0)`, 90000);
  await sleep(1500);
  return { targetId, sessionId, ready, requests, unknown };
}

async function main() {
  const vite = spawn(process.execPath, [join(FRONTEND, 'node_modules/vite/bin/vite.js'), '--port', String(PORT), '--strictPort', '--host', 'localhost'], {
    cwd: FRONTEND, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, VITE_API_BASE_URL: ORIGIN },
  });
  vite.stderr.on('data', (d) => process.stderr.write(`[vite] ${d}`));
  const profile = mkdtempSync(join(tmpdir(), 'prb004-edge-'));
  let edge;
  const result = { executed: new Date().toISOString(), frontend: FRONTEND, origin: ORIGIN,
    method: 'real ViewerApp in headless Edge (real WebGL), served from a host name without a dot; backend answered by CDP request interception with a synthetic 40x48x36 LAS study (markers A, B; lesion mask on A whose header carries an MRI window -15.5/189.2); positions measured from rendered pixels relative to the drawn head', checks: {} };
  try {
    await waitHttp(`${ORIGIN}/`, 60000);
    edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', '--hide-scrollbars',
      '--use-angle=swiftshader', '--enable-unsafe-swiftshader', 'about:blank'], { stdio: 'ignore' });
    const ver = await (await waitHttp(`http://127.0.0.1:${CDP_PORT}/json/version`, 30000)).json();
    const ws = new WebSocket(ver.webSocketDebuggerUrl);
    await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
    const cdp = new Cdp(ws);
    const warm = await openViewer(cdp); // Vite pre-bundles on the first visit and may reload
    await cdp.send('Target.closeTarget', { targetId: warm.targetId });
    cdp.exceptions.length = 0; cdp.console.length = 0;

    const v = await openViewer(cdp);
    const sid = v.sessionId;
    result.ready = v.ready;
    // PRB-008: slice on open (toolbar counter next to the toolbar slider)
    result.checks.sliceOnOpen = await evaluate(cdp, sid, `(() => { const r = document.querySelector('#main-content input[type="range"]'); return r && r.previousElementSibling ? r.previousElementSibling.textContent.trim() : null; })()`);
    // PRB-009
    result.checks.quickScreenButton = await evaluate(cdp, sid, `[...document.querySelectorAll('button')].some(b => /Quick Screen/i.test(b.textContent))`);

    // Open the lesion mask from the sidebar (Standard view overlays it from the binary mask)
    result.checks.maskOpened = await clickText(cdp, sid, 'Probe lesion mask');
    await sleep(2500);
    const std = await captureCanvas(cdp, sid, '#main-content canvas', 'standard.png');
    result.checks.standard = std ? measure(std) : null;

    // PRB-004/005/006: the W/L GPU view (render mode button)
    result.checks.gpuButton = await clickButton(cdp, sid, 'W/L GPU');
    await until(cdp, sid, `[...document.querySelectorAll('#main-content canvas')].filter(c => c.width > 0).length > 0`, 20000);
    await sleep(4000);
    // The series' own window (125 / 250 in the fixture), so the whole head is drawn.
    result.checks.optimalWindowButton = await clickButton(cdp, sid, 'Optimal');
    await sleep(2000);
    const gpu = await captureCanvas(cdp, sid, '#main-content .z-10 canvas', 'wl_gpu.png');
    result.checks.wlGpu = gpu ? measure(gpu) : null;
    result.checks.gpuNotice = await evaluate(cdp, sid, `document.querySelector('[data-testid="niivue-mask-not-shown"]')?.textContent ?? null`);
    result.checks.gpuError = await evaluate(cdp, sid, `[...document.querySelectorAll('#main-content .bg-red-900\\\\/70')].map(e => e.textContent).join(' | ') || null`);

    // 3D volume with the mask (PRB-005 on a dot-less host; PRB-006 red fog)
    result.checks.threeDButton = await clickButton(cdp, sid, '3D');
    await sleep(9000);
    const vol = await captureCanvas(cdp, sid, '#main-content canvas', '3d_volume.png');
    result.checks.threeD = vol ? measure(vol) : null;

    // PRB-007: back to 2D, 2x2 grid of a study of preprocessed images only
    await clickButton(cdp, sid, '2D');
    await sleep(2500);
    await clickButton(cdp, sid, 'Standard');
    await sleep(1500);
    result.checks.gridButton = await clickButton(cdp, sid, '2x2');
    await sleep(5000);
    result.checks.grid = await evaluate(cdp, sid, `({ panelsDrawn: [...document.querySelectorAll('#main-content canvas')].filter(c => c.width > 0).length, emptyPanels: [...document.querySelectorAll('#main-content div')].filter(d => d.children.length === 0 && d.textContent.trim() === 'No image assigned').length })`);
    if (SHOTS) { const { data } = await cdp.send('Page.captureScreenshot', { format: 'png' }, sid); writeFileSync(join(SHOTS, 'grid_2x2.png'), Buffer.from(data, 'base64')); }

    result.checks.screeningModelRequests = v.requests.filter((u) => u.includes('brain_screening.onnx'));
    result.unknownRequests = [...new Set(v.unknown)];
    result.pageExceptions = cdp.exceptions.slice(0, 20);
    result.consoleErrorsAndWarnings = cdp.console.slice(0, 40);
    try { await cdp.send('Browser.close'); } catch { /* closing */ }
    ws.close();
  } finally {
    await sleep(500);
    killTree(edge?.pid);
    killTree(vite.pid);
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* profile lock */ }
  }

  // ── verdicts ──
  const c = result.checks;
  const close = (p, q, tol = 0.05) => !!p && !!q && Math.abs(p.u - q.u) <= tol && Math.abs(p.v - q.v) <= tol;
  result.verdict = {
    prb004_markerB_same_place_standard_vs_gpu: close(c.standard?.B, c.wlGpu?.B),
    prb004_mask_drawn_on_marker_A_in_gpu_view: close(c.standard?.red, c.wlGpu?.red),
    prb005_no_toUpperCase_error: !result.pageExceptions.some((e) => /toUpperCase/.test(e ?? '')) && !/toUpperCase/.test(c.gpuError ?? ''),
    prb005_gpu_and_3d_drawn: !!c.wlGpu?.B && !!c.threeD && Number.isFinite(c.threeD.headBox.x0),
    prb006_3d_not_tinted_red: Number.isFinite(c.threeD?.redTintedFraction) && c.threeD.redTintedFraction < 0.15,
    prb006_gpu_not_tinted_red: Number.isFinite(c.wlGpu?.redTintedFraction) && c.wlGpu.redTintedFraction < 0.15,
    prb007_grid_four_images_none_empty: c.grid?.panelsDrawn >= 4 && c.grid?.emptyPanels === 0,
    prb008_opens_on_middle_slice: c.sliceOnOpen === `${Math.floor((NZ - 1) / 2) + 1}/${NZ}`,
    prb009_no_model_request_no_button: c.screeningModelRequests.length === 0 && c.quickScreenButton === false,
  };
  writeFileSync(OUT, JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ checks: c, verdict: result.verdict, pageExceptions: result.pageExceptions }, null, 1));
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
