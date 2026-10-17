/**
 * DEV-ONLY in-browser stand-in for the backend, used by the viewer demo harness
 * (/dev/viewer-demo). It is imported exclusively from `dev/ViewerDemo.tsx`, which is
 * itself only reachable behind `import.meta.env.DEV` in App.tsx — production builds
 * never contain this module (verified by grepping dist/ in the parity notes).
 *
 * It answers the REST calls the viewer makes with fixtures produced by the backend's
 * own code on ONE public case (scripts/viewer/build_demo_fixtures.py), served by the
 * Vite dev server from the gitignored `frontend/.dev-data/` folder. No network leaves
 * the machine, no login is needed, no real patient data is involved.
 */
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios';
import { apiClient } from '@/services/apiClient';

const DATA = '/__dev-data/viewer-demo';

export const DEMO_IDS = {
  patient: 'demo-patient',
  study: 'demo-study',
  series: 'demo-series',
  seg: 'demo-seg-gold',
};

const FILE_BASE = `patients/${DEMO_IDS.patient}/studies/${DEMO_IDS.study}/series/${DEMO_IDS.series}`;
export const DEMO_FILES = {
  flair: `${FILE_BASE}/FLAIR_desc-preproc.nii.gz`,
  t1: `${FILE_BASE}/T1w.nii.gz`,
};

const NOW = '2026-10-17T09:30:00Z';

const patient = {
  id: DEMO_IDS.patient,
  mrn: 'DEMO-0001',
  given_name: 'Paciente',
  family_name: 'Demo (datos públicos)',
  full_name: 'Paciente Demo (datos públicos)',
  birth_date: '1988-04-12',
  gender: 'female',
  age: 38,
  phone_mobile: '',
  country: 'ES',
  status: 'active',
  created_at: NOW,
  updated_at: NOW,
};

const study = {
  id: DEMO_IDS.study,
  patient_id: DEMO_IDS.patient,
  study_instance_uid: '1.2.826.0.1.3680043.10.999.1',
  status: 'available',
  modality: 'MR',
  study_date: '2026-09-30',
  study_description: 'RM cerebral — protocolo EM (demo pública)',
  institution_name: 'Conjunto público open_ms_data',
  series_count: 1,
  instance_count: 2,
  created_at: NOW,
};

const series = [{
  id: DEMO_IDS.series,
  study_id: DEMO_IDS.study,
  series_instance_uid: '1.2.826.0.1.3680043.10.999.1.1',
  series_number: 1,
  modality: 'MR',
  series_description: 'FLAIR + T1 (MNI)',
  instance_count: 2,
  created_at: NOW,
}];

const instances = [
  {
    id: 'demo-inst-flair', series_id: DEMO_IDS.series, sop_instance_uid: '1.2.3.1',
    gcs_object_name: DEMO_FILES.flair, original_filename: 'FLAIR_desc-preproc.nii.gz',
    content_type: 'application/gzip', file_size_bytes: 4892907, created_at: NOW,
  },
  {
    id: 'demo-inst-t1', series_id: DEMO_IDS.series, sop_instance_uid: '1.2.3.2',
    gcs_object_name: DEMO_FILES.t1, original_filename: 'T1w.nii.gz',
    content_type: 'application/gzip', file_size_bytes: 4851288, created_at: NOW,
  },
];

function keyOfFile(path: string): 'flair' | 't1' | null {
  if (path.includes('FLAIR_desc-preproc')) return 'flair';
  if (path.includes('T1w')) return 't1';
  return null;
}

const cache = new Map<string, Promise<unknown>>();
function fetchJson<T = unknown>(name: string): Promise<T> {
  if (!cache.has(name)) {
    cache.set(name, fetch(`${DATA}/${name}`).then((r) => {
      if (!r.ok) throw new Error(`demo fixture missing: ${name} (run scripts/viewer/build_demo_fixtures.py)`);
      return r.json();
    }));
  }
  return cache.get(name) as Promise<T>;
}
function fetchBytes(name: string): Promise<ArrayBuffer> {
  return fetch(`${DATA}/${name}`).then((r) => {
    if (!r.ok) throw new Error(`demo fixture missing: ${name}`);
    return r.arrayBuffer();
  });
}

async function segmentation() {
  const labels = await fetchJson('labels.json');
  return {
    segmentation_id: DEMO_IDS.seg,
    file_id: DEMO_FILES.flair,
    total_slices: 182,
    metadata: {
      file_id: DEMO_FILES.flair,
      created_at: NOW,
      modified_at: NOW,
      description: 'Expert Rater — consenso (open_ms_data)',
      validation_source: 'manual',
      labels,
    },
  };
}

type Reply = { status: number; data: unknown; headers?: Record<string, string> };

async function route(method: string, url: string): Promise<Reply> {
  const path = url.replace(/^https?:\/\/[^/]+/, '').split('?')[0];
  const ok = (data: unknown, headers?: Record<string, string>): Reply => ({ status: 200, data, headers });
  const m = method.toUpperCase();

  if (m === 'GET') {
    if (path === `/api/v1/studies/${DEMO_IDS.study}`) return ok(study);
    if (path === `/api/v1/studies/${DEMO_IDS.study}/series`) return ok(series);
    if (path === `/api/v1/studies/series/${DEMO_IDS.series}/instances`) return ok(instances);
    if (path === `/api/v1/studies/patient/${DEMO_IDS.patient}`) {
      return ok({ items: [{ ...study }], total: 1, page: 1, page_size: 20, total_pages: 1 });
    }
    if (path === `/api/v1/patients/${DEMO_IDS.patient}`) return ok(patient);
    if (path === `/api/v1/patients/${DEMO_IDS.patient}/history`) return ok([]);
    if (path === '/api/v1/segmentation/list') return ok([await segmentation()]);
    if (path === `/api/v1/segmentation/${DEMO_IDS.seg}`) return ok(await segmentation());
    if (path === `/api/v1/segmentation/${DEMO_IDS.seg}/mask/binary`) {
      return ok(await fetchBytes('mask-gold.bin'), { 'x-mask-generation': '1' });
    }
    if (path === `/api/v1/segmentation/${DEMO_IDS.seg}/lesion-analysis`) return ok(await fetchJson('lesions-gold.json'));
    if (path === `/api/v1/segmentation/${DEMO_IDS.seg}/dis-assessment`) return ok(await fetchJson('dis-gold.json'));
    if (path === `/api/v1/segmentation/${DEMO_IDS.seg}/nifti`) return ok(await fetchBytes('gold.nii.gz'));
    if (path.startsWith('/api/v1/imaging/')) {
      const key = keyOfFile(path);
      if (key && path.startsWith('/api/v1/imaging/metadata/')) return ok(await fetchJson(`metadata-${key}.json`));
      if (key && path.startsWith('/api/v1/imaging/process/')) return ok(await fetchJson(`process-${key}.json`));
      if (key && path.startsWith('/api/v1/imaging/nifti/')) return ok(await fetchBytes(`${key}.nii.gz`));
    }
    if (path === '/api/v1/ai/report/templates') return ok([]);
    if (path === '/api/v1/clinical-tools/tools') return ok([]);
  }
  return { status: 404, data: { detail: `demo backend: ${m} ${path} is not available in the offline demo` } };
}

/** axios adapter: every apiClient call is answered locally. */
const demoAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const reply = await route(config.method ?? 'get', config.url ?? '');
  const headers = new AxiosHeaders(reply.headers ?? {});
  const response = {
    data: reply.data,
    status: reply.status,
    statusText: reply.status === 200 ? 'OK' : 'Not Found',
    headers,
    config,
    request: {},
  };
  if (reply.status >= 400) {
    throw new AxiosError(`Request failed with status code ${reply.status}`, 'ERR_BAD_REQUEST', config, {}, response);
  }
  return response;
};

let installed = false;

/** Route apiClient + window.fetch (niivue/3D path) to the local fixtures. Idempotent. */
export function installDemoBackend(): void {
  if (installed) return;
  installed = true;
  apiClient.defaults.adapter = demoAdapter;
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    if (url.includes('/api/v1/')) {
      const reply = await route(init?.method ?? 'GET', url);
      const body = reply.data instanceof ArrayBuffer ? reply.data : JSON.stringify(reply.data);
      return new Response(body, { status: reply.status, headers: reply.headers });
    }
    return realFetch(input, init);
  };
}
