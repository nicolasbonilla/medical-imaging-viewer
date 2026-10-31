/**
 * Recording stand-in for '@niivue/niivue' (jsdom has no WebGL). Test-only.
 *
 * Every Niivue instance the component creates is kept in `fakeNiivue.instances` with the
 * options it was given, the volumes it loaded, the meshes it received and the scanner-mm
 * points it was asked to convert. `mm2frac` is the identity, so `scene.crosshairPos`
 * holds the mm point the component aimed at.
 *
 * Use:  vi.mock('@niivue/niivue', async () => (await import('@/test/fakeNiivue')).niivueModule);
 */

/** LAS-like, anisotropic, translated: a transposed voxel lands far from the right one. */
export const FAKE_AFFINE = [
  [-1, 0, 0, 90],
  [0, 1.2, 0, -126],
  [0, 0, 3, -72],
  [0, 0, 0, 1],
];

export class FakeNiivue {
  opts: Record<string, unknown>;
  scene = { crosshairPos: [0.5, 0.5, 0.5], pan2Dxyzmm: [0, 0, 0, 1] };
  volumes: Array<Record<string, unknown>> = [];
  meshes: Array<{ url: string; buffer: Float32Array }> = [];
  mm2fracCalls: number[][] = [];
  backgroundMasksOverlays = 0;

  constructor(opts: Record<string, unknown> = {}) {
    this.opts = { ...opts };
    fakeNiivue.instances.push(this);
  }
  async attachToCanvas() {}
  async loadVolumes() {
    this.volumes = [{ hdr: { affine: FAKE_AFFINE }, dims: [3, 182, 218, 60], colormap: 'gray' }];
  }
  addVolume(v: Record<string, unknown>) { this.volumes.push(v); }
  setRenderAzimuthElevation() {}
  mm2frac(mm: number[]) { this.mm2fracCalls.push([...mm]); return [...mm]; }
  drawScene() {}
  setClipPlane() {}
  broadcastTo() {}
  setOpacity() {}
  updateGLVolume() {}
  async addMeshFromUrl(m: { url: string; buffer: Float32Array }) { this.meshes.push(m); }
  removeMeshByUrl() {}
  addColormap() {}
  setScale() {}
  setPan2Dxyzmm() {}
}

export const fakeNiivue = { instances: [] as FakeNiivue[] };

export const niivueModule = {
  Niivue: FakeNiivue,
  NVImage: { loadFromUrl: async () => ({ colormap: 'red' }) },
  SLICE_TYPE: { AXIAL: 0, CORONAL: 1, SAGITTAL: 2, MULTIPLANAR: 3, RENDER: 4 },
  SHOW_RENDER: { NEVER: 0, ALWAYS: 1, AUTO: 2 },
  // The mesh "file" is its vertex array, so a test can read where a box is drawn.
  NVMeshUtilities: { createMZ3: (verts: Float32Array) => verts.slice(0) },
};
