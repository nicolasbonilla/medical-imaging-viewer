#!/usr/bin/env node
/**
 * Headless screenshots of the DEV-only viewer demo harness (/dev/viewer-demo).
 *
 * Starts its OWN Vite dev server and its OWN headless Microsoft Edge (separate
 * temporary profile), drives them over the Chrome DevTools Protocol, writes PNGs,
 * then shuts down exactly the two processes it started (by PID, never by image
 * name). Requires the gitignored fixtures from scripts/viewer/build_demo_fixtures.py.
 *
 * Usage (from frontend/):
 *   node ../scripts/viewer/screenshot.mjs <outDir> <name>=<demo-steps> [<name>=<demo-steps> ...]
 * e.g.
 *   node ../scripts/viewer/screenshot.mjs ../docs/research/viewer-v3/screenshots \
 *        before-axial= before-overlay=open-seg
 *
 * Env: EDGE (path to msedge.exe), PORT (vite port, default 5179), SHOT_W/SHOT_H.
 */
import { spawn, execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const EDGE = process.env.EDGE ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const PORT = Number(process.env.PORT ?? 5179);
const CDP_PORT = Number(process.env.CDP_PORT ?? 9339);
const W = Number(process.env.SHOT_W ?? 1600);
const H = Number(process.env.SHOT_H ?? 1000);

const [outDirArg, ...shotArgs] = process.argv.slice(2);
if (!outDirArg || shotArgs.length === 0) {
  console.error('usage: screenshot.mjs <outDir> <name>=<steps> ...');
  process.exit(2);
}
const outDir = resolve(outDirArg);
mkdirSync(outDir, { recursive: true });
const shots = shotArgs.map((a) => {
  const i = a.indexOf('=');
  return { name: a.slice(0, i), steps: a.slice(i + 1) };
});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function killTree(pid) {
  if (!pid) return;
  try {
    execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' });
  } catch { /* already gone */ }
}

async function waitHttp(url, timeoutMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.ok) return r;
    } catch { /* not up yet */ }
    await sleep(300);
  }
  throw new Error(`timeout waiting for ${url}`);
}

class Cdp {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.events = [];
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { res, rej } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
      } else if (msg.method === 'Runtime.consoleAPICalled' || msg.method === 'Runtime.exceptionThrown') {
        this.events.push(msg);
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

async function main() {
  const frontendDir = resolve('.');
  const vite = spawn(process.execPath, [join(frontendDir, 'node_modules/vite/bin/vite.js'), '--port', String(PORT), '--strictPort', '--host', '127.0.0.1'], {
    cwd: frontendDir, stdio: ['ignore', 'pipe', 'pipe'],
  });
  vite.stdout.on('data', () => {});
  vite.stderr.on('data', (d) => process.stderr.write(`[vite] ${d}`));
  const profile = mkdtempSync(join(tmpdir(), 'mstool-edge-'));
  let edge;
  try {
    await waitHttp(`http://127.0.0.1:${PORT}/`, 60000);
    edge = spawn(EDGE, [
      '--headless=new', `--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${profile}`,
      `--window-size=${W},${H}`, '--no-first-run', '--no-default-browser-check',
      '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--hide-scrollbars',
      'about:blank',
    ], { stdio: 'ignore' });
    const ver = await (await waitHttp(`http://127.0.0.1:${CDP_PORT}/json/version`, 30000)).json();
    const ws = new WebSocket(ver.webSocketDebuggerUrl);
    await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
    const cdp = new Cdp(ws);

    // Warm-up: Vite pre-bundles dependencies on the first visit and then forces a full
    // reload; do that once off-camera so the first real shot is not mid-reload.
    shots.unshift({ name: null, steps: '' });
    for (const shot of shots) {
      const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
      const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
      await cdp.send('Page.enable', {}, sessionId);
      await cdp.send('Runtime.enable', {}, sessionId);
      await cdp.send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false }, sessionId);
      const url = `http://127.0.0.1:${PORT}/dev/viewer-demo?demo=${encodeURIComponent(shot.steps)}`;
      await cdp.send('Page.navigate', { url }, sessionId);
      const t0 = Date.now();
      let ready = false;
      while (Date.now() - t0 < 120000) {
        const r = await cdp.send('Runtime.evaluate', { expression: 'document.body && document.body.dataset.demoReady', returnByValue: true }, sessionId);
        if (r.result?.value === '1') { ready = true; break; }
        await sleep(500);
      }
      await sleep(800);
      if (shot.name === null) { await cdp.send('Target.closeTarget', { targetId }); continue; }
      const { data } = await cdp.send('Page.captureScreenshot', { format: 'png' }, sessionId);
      const file = join(outDir, `${shot.name}.png`);
      writeFileSync(file, Buffer.from(data, 'base64'));
      console.log(`${ready ? 'ok  ' : 'TIMEOUT'} ${file}`);
      await cdp.send('Target.closeTarget', { targetId });
    }
    const errs = cdp.events.filter((e) => e.method === 'Runtime.exceptionThrown' || e.params?.type === 'error');
    for (const e of errs.slice(0, 20)) {
      const p = e.params;
      console.log('[page]', p.exceptionDetails?.exception?.description?.split('\n')[0] ?? p.args?.map((a) => a.value ?? a.description).join(' '));
    }
    try { await cdp.send('Browser.close'); } catch { /* closing */ }
    ws.close();
  } finally {
    await sleep(500);
    killTree(edge?.pid);
    killTree(vite.pid);
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* profile lock */ }
  }
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
