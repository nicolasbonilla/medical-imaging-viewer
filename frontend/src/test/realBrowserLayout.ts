/**
 * Real-browser layout measurement for safety annotations (CAPA-010). Test-only.
 *
 * jsdom has no layout engine, so it cannot tell whether an annotation is inside the
 * visible part of the page or clipped by an `overflow: hidden` ancestor. This helper takes
 * DOM snapshots produced by rendering the REAL components in jsdom (the app's real Tailwind
 * CSS is injected by vitest `css: true` when a test imports `src/index.css`), loads each
 * snapshot into an iframe of a given size inside a headless Chromium-family browser
 * (Edge or Chrome, own temporary profile, no network), and returns for every matched
 * element the fraction of its box that lies inside the window AND inside every ancestor
 * whose overflow clips.
 *
 * Browser: env CAPA010_BROWSER or CHROME_BIN, else the usual Edge/Chrome locations.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

export interface LayoutCase {
  name: string;
  /** Full HTML document (snapshot of the rendered page, with its <style>). */
  html: string;
  width: number;
  height: number;
  /** Elements to measure: CSS selector, optionally narrowed to leaf elements whose text matches. */
  selector: string;
  text?: string;
}

export interface Measured {
  visibleFraction: number;
  hiddenBelowPx: number;
  top: number;
  bottom: number;
  left: number;
  right: number;
  /** Intersection of the window and every overflow-clipping ancestor. */
  clip: { top: number; left: number; bottom: number; right: number };
}

export interface LayoutResult {
  name: string;
  width: number;
  height: number;
  matches: Measured[];
}

export function findChromium(): string | null {
  const env = process.env.CAPA010_BROWSER || process.env.CHROME_BIN;
  if (env && existsSync(env)) return env;
  const candidates = [
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/microsoft-edge',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ];
  return candidates.find((c) => existsSync(c)) ?? null;
}

const escapeAttr = (s: string) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;');

// Runs inside the outer page after every iframe has loaded.
const MEASURE = `
window.addEventListener('load', function () {
  var cases = JSON.parse(document.getElementById('cases').textContent);
  var out = cases.map(function (c, n) {
    var win = document.getElementById('f' + n).contentWindow;
    var doc = win.document;
    var els = Array.prototype.slice.call(doc.querySelectorAll(c.selector)).filter(function (el) {
      return !c.text || (el.children.length === 0 && el.textContent.indexOf(c.text) >= 0);
    });
    var matches = els.map(function (el) {
      var r = el.getBoundingClientRect();
      var box = { top: 0, left: 0, bottom: win.innerHeight, right: win.innerWidth };
      for (var a = el.parentElement; a; a = a.parentElement) {
        var cs = win.getComputedStyle(a);
        if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
          var q = a.getBoundingClientRect();
          box = { top: Math.max(box.top, q.top), left: Math.max(box.left, q.left),
                  bottom: Math.min(box.bottom, q.bottom), right: Math.min(box.right, q.right) };
        }
      }
      var w = Math.max(0, Math.min(r.right, box.right) - Math.max(r.left, box.left));
      var h = Math.max(0, Math.min(r.bottom, box.bottom) - Math.max(r.top, box.top));
      var area = r.width * r.height;
      return { visibleFraction: area > 0 ? (w * h) / area : 0, hiddenBelowPx: Math.max(0, r.bottom - box.bottom),
               top: r.top, bottom: r.bottom, left: r.left, right: r.right, clip: box };
    });
    return { name: c.name, width: c.width, height: c.height, matches: matches };
  });
  document.getElementById('result').textContent = JSON.stringify(out);
});`;

/** Load every case in one headless browser run and measure the matched elements. */
export function measureInRealBrowser(browser: string, cases: LayoutCase[]): LayoutResult[] {
  const dir = mkdtempSync(join(tmpdir(), 'capa010-layout-'));
  const profile = join(dir, 'profile');
  const page = join(dir, 'page.html');
  const meta = cases.map(({ name, width, height, selector, text }) => ({ name, width, height, selector, text }));
  const frames = cases
    .map((c, n) => `<iframe id="f${n}" style="display:block;border:0;width:${c.width}px;height:${c.height}px" srcdoc="${escapeAttr(c.html)}"></iframe>`)
    .join('\n');
  writeFileSync(page, `<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0">
<pre id="result">pending</pre>
<script type="application/json" id="cases">${JSON.stringify(meta).replace(/</g, '\\u003c')}</script>
${frames}
<script>${MEASURE}</script>
</body></html>`, 'utf8');
  try {
    const widest = Math.max(...cases.map((c) => c.width));
    const stdout = execFileSync(browser, [
      '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run', '--no-default-browser-check',
      '--disable-extensions', '--hide-scrollbars', `--user-data-dir=${profile}`,
      `--window-size=${widest + 50},1200`, '--virtual-time-budget=10000', '--dump-dom', pathToFileURL(page).href,
    ], { encoding: 'utf8', timeout: 120000, maxBuffer: 256 * 1024 * 1024, stdio: ['ignore', 'pipe', 'ignore'] });
    const m = stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/);
    if (!m || m[1] === 'pending') throw new Error('the browser did not run the layout measurement');
    const json = m[1].replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
    return JSON.parse(json) as LayoutResult[];
  } finally {
    rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}
