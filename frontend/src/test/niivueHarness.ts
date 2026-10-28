/**
 * Test harness for the niivue viewers (PRB-004, PRB-005, PRB-006). jsdom has no WebGL, so only
 * niivue's RENDERER is replaced; everything that decides what is drawn where is niivue's own code:
 *
 *   - `Niivue.loadVolumes()` does what the real one does before drawing: it runs niivue's own
 *     `getFileExt()` on each item (the call that throws "reading 'toUpperCase'" on a host name
 *     without a dot, PRB-005) and loads each item with the REAL `NVImage.loadFromUrl()`.
 *   - `NVImage` is the real class: the real NIfTI parser, the real affine → RAS math
 *     (`calculateRAS`, `convertMM2Frac`) and the real display range (`cal_min`/`cal_max`).
 *   - `URL.createObjectURL()` returns `blob:<origin>/<uuid>` as a browser does for the page's
 *     origin, and `fetch()` of such a URL returns the blob's bytes. API URLs are served from a
 *     route table.
 *
 * Use:
 *   vi.mock('@niivue/niivue', async (orig) =>
 *     (await import('@/test/niivueHarness')).harnessModule(await orig()));
 */
import { vi } from 'vitest';

type NiivueModule = typeof import('@niivue/niivue');
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyVol = any;

export interface HarnessNiivue {
  opts: Record<string, unknown>;
  scene: { crosshairPos: number[]; pan2Dxyzmm: number[] };
  volumes: AnyVol[];
  loadVolumesCalls: Array<Array<Record<string, unknown>>>;
  backgroundMasksOverlays: number;
}

export const harness = {
  instances: [] as HarnessNiivue[],
  /** Every item passed to NVImage.loadFromUrl (by the component or by loadVolumes). */
  loadFromUrlCalls: [] as Array<Record<string, unknown>>,
  /** Colormaps registered with Niivue.addColormap (name → definition), e.g. the MAGNIMS zone map's. */
  colormaps: {} as Record<string, unknown>,
  /** Keys, wheel and double-click events that reached niivue's own canvas handlers (attached as niivue attaches them). */
  keysSeenByNiivue: [] as string[],
  reset() {
    harness.instances.length = 0;
    harness.loadFromUrlCalls.length = 0;
    for (const k of Object.keys(harness.colormaps)) delete harness.colormaps[k];
    harness.keysSeenByNiivue.length = 0;
  },
};

export function harnessModule(actual: NiivueModule): NiivueModule {
  const RealNVImage = actual.NVImage;
  // niivue's own extension parser, exactly as Niivue.loadVolumes() calls it.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const realGetFileExt = (actual.Niivue.prototype as any).getFileExt as (n: string) => string;

  const NVImage = new Proxy(RealNVImage, {
    get(target, prop, receiver) {
      if (prop === 'loadFromUrl') {
        return async (opts: Record<string, unknown>) => {
          harness.loadFromUrlCalls.push({ ...opts });
          return target.loadFromUrl(opts as never);
        };
      }
      return Reflect.get(target, prop, receiver);
    },
  });

  class Niivue implements HarnessNiivue {
    opts: Record<string, unknown>;
    scene = { crosshairPos: [0.5, 0.5, 0.5], pan2Dxyzmm: [0, 0, 0, 1] };
    volumes: AnyVol[] = [];
    loadVolumesCalls: Array<Array<Record<string, unknown>>> = [];
    backgroundMasksOverlays = 0;
    meshes: unknown[] = [];

    constructor(opts: Record<string, unknown> = {}) {
      this.opts = { ...opts };
      harness.instances.push(this);
    }
    /** As niivue 0.67 attachToCanvas (registerInteractions): its keyboard, wheel and double-click handlers
     *  listen on the canvas itself, and it makes the canvas focusable. */
    async attachToCanvas(canvas?: HTMLCanvasElement) {
      canvas?.addEventListener('keydown', (e) => { harness.keysSeenByNiivue.push(`down:${e.code}`); });
      canvas?.addEventListener('keyup', (e) => { harness.keysSeenByNiivue.push(`up:${e.code}`); });
      canvas?.addEventListener('wheel', () => { harness.keysSeenByNiivue.push('wheel'); });
      canvas?.addEventListener('dblclick', () => { harness.keysSeenByNiivue.push('dblclick'); });
      canvas?.setAttribute('tabindex', '0');
      return this;
    }
    /** As niivue 0.67 Niivue.loadVolumes → addVolumesFromUrl → addVolumeFromUrl. */
    async loadVolumes(list: Array<Record<string, unknown>>) {
      this.loadVolumesCalls.push(list.map((x) => ({ ...x })));
      this.volumes = [];
      for (const item of list) {
        const ext = realGetFileExt.call(this, (item.name as string) || (item.url as string));
        if (ext === 'DCM') throw new Error('DICOM files must be loaded using useDicomLoader');
        const vol = await NVImage.loadFromUrl(item as never);
        this.addVolume(vol);
      }
      return this;
    }
    addVolume(v: AnyVol) { this.volumes.push(v); }
    setOpacity(i: number, o: number) { if (this.volumes[i]) this.volumes[i].opacity = o; }
    updateGLVolume() {}
    drawScene() {}
    cleanup() {}
    setRenderAzimuthElevation() {}
    /** niivue's own mm → texture fraction of the first volume (as Niivue.mm2frac). */
    mm2frac(mm: number[]) {
      const v = this.volumes[0];
      return v?.convertMM2Frac ? Array.from(v.convertMM2Frac(mm) as number[]) : [...mm];
    }
    setClipPlane() {}
    broadcastTo() {}
    async addMeshFromUrl(m: unknown) { this.meshes.push(m); }
    removeMeshByUrl() {}
    addColormap(name: string, cmap: unknown) { harness.colormaps[name] = cmap; }
    setScale() {}
    setPan2Dxyzmm() {}
    setColormap() {}
  }

  return { ...actual, Niivue: Niivue as never, NVImage: NVImage as never };
}

/**
 * Browser-like blob URLs for `origin` (e.g. "http://localhost:4173") and a fetch() that serves
 * them and the given API routes (path suffix → bytes, or a status code).
 */
export function installBrowserNetwork(origin: string, routes: Record<string, ArrayBuffer | number>) {
  const blobs = new Map<string, Blob>();
  let n = 0;
  URL.createObjectURL = vi.fn((b: Blob) => {
    n += 1;
    const url = `blob:${origin}/0d6c1a2b-${String(n).padStart(4, '0')}-4a5b-9c8d-${'e'.repeat(12)}`;
    blobs.set(url, b);
    return url;
  }) as never;
  URL.revokeObjectURL = vi.fn((u: string) => { blobs.delete(u); }) as never;
  const requests: string[] = [];
  // jsdom's Blob has no arrayBuffer(); FileReader reads it as a browser would.
  const bytesOf = (b: Blob) => new Promise<ArrayBuffer>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as ArrayBuffer);
    r.onerror = () => reject(r.error);
    r.readAsArrayBuffer(b);
  });
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    requests.push(url);
    if (blobs.has(url)) return new Response(await bytesOf(blobs.get(url)!));
    const path = url.split('?')[0];
    const key = Object.keys(routes).find((k) => url.endsWith(k)) ?? Object.keys(routes).find((k) => path.endsWith(k));
    if (key === undefined) return new Response('not found', { status: 404 });
    const v = routes[key];
    if (typeof v === 'number') return new Response('x', { status: v });
    return new Response(v.slice(0), { status: 200, headers: { 'content-type': 'application/octet-stream' } });
  }));
  return { requests };
}

/**
 * Where niivue's axial 2D view puts storage voxel (i, j, k) of `vol`, as fractions of the
 * slice tile: `right` 0 → 1 = left → right, `down` 0 → 1 = top → bottom, `depth` = the axial
 * crosshair fraction that selects the voxel's slice. Computed with niivue's own transforms
 * (the volume's `hdr.affine` and `convertMM2Frac`) and its axial screen convention when
 * `isRadiologicalConvention` is false: +X to the right, +Y up (the orientation text it would
 * draw is "L" left and "A" top — see the convention test).
 */
export function niivueAxialScreenOf(vol: AnyVol, i: number, j: number, k: number) {
  const a = vol.hdr.affine as number[][];
  const mm = [0, 1, 2].map((r) => a[r][0] * i + a[r][1] * j + a[r][2] * k + a[r][3]);
  const f = vol.convertMM2Frac(mm) as number[];
  return { right: f[0], down: 1 - f[1], depth: f[2] };
}
