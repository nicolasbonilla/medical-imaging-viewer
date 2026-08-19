import { apiClient } from '../services/apiClient';
import type {
  ImageSeriesResponse,
  ImageSlice,
  WindowLevelRequest,
  ImageOrientation,
  VolumeData,
} from '@/types';

/**
 * GET with a bounded timeout + retry on TRANSIENT failures. The main service is a
 * scale-to-zero Cloud Run instance (min-instances=0 + cpu-throttling), so the first
 * request after idle pays a cold start and the default axios instance has NO timeout —
 * a cold/hung call freezes the viewer indefinitely with only a bare spinner. This bounds
 * each attempt and retries cold-start-class failures (503/502/504, network abort/timeout)
 * with backoff; the first attempt typically warms the instance so the retry succeeds.
 * Non-transient errors (4xx) throw immediately — no pointless retries.
 */
async function getWithRetry<T>(
  url: string,
  config: Record<string, unknown>,
  opts: { retries?: number; timeoutMs?: number; label?: string } = {},
): Promise<T> {
  const { retries = 2, timeoutMs = 120_000, label = url } = opts;
  let lastError: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const { data } = await apiClient.get(url, { ...config, timeout: timeoutMs });
      return data as T;
    } catch (error: unknown) {
      lastError = error;
      const status = (error as { response?: { status?: number } })?.response?.status;
      const code = (error as { code?: string })?.code;
      // Transient = server overload, gateway, or a cold-start network abort/timeout.
      // `status === undefined` (no response) covers ECONNABORTED / network errors.
      const transient =
        status === 503 || status === 502 || status === 504 ||
        code === 'ECONNABORTED' || code === 'ERR_NETWORK' || status === undefined;
      if (transient && attempt < retries) {
        const delay = Math.min(1000 * 2 ** attempt, 6000); // 1s, 2s, ... (max 6s)
        console.warn(
          `[ImagingAPI] transient failure on ${label} (status=${status} code=${code}); ` +
          `retry ${attempt + 1}/${retries} in ${delay}ms`,
        );
        await new Promise((r) => setTimeout(r, delay));
        continue;
      }
      throw error;
    }
  }
  throw lastError instanceof Error ? lastError : new Error('Request failed after retries');
}

// Medical Imaging API
export const imagingAPI = {
  processImage: async (
    fileId: string,
    startSlice?: number,
    endSlice?: number,
    maxSlices = 50
  ): Promise<ImageSeriesResponse> => {
    // Bounded timeout + cold-start retry: a scale-to-zero backend must not freeze the
    // viewer forever on the first (cold) study load. See getWithRetry.
    return getWithRetry<ImageSeriesResponse>(
      `/api/v1/imaging/process/${fileId}`,
      { params: { start_slice: startSlice, end_slice: endSlice, max_slices: maxSlices } },
      { retries: 2, timeoutMs: 120_000, label: `process/${fileId}` },
    );
  },

  applyWindowLevel: async (
    fileId: string,
    request: WindowLevelRequest
  ): Promise<ImageSlice> => {
    const { data } = await apiClient.post(
      `/api/v1/imaging/window-level/${fileId}`,
      request
    );
    return data;
  },

  getSlice: async (
    fileId: string,
    sliceIndex: number,
    windowCenter?: number,
    windowWidth?: number
  ): Promise<ImageSlice> => {
    const { data } = await apiClient.get(
      `/api/v1/imaging/slice/${fileId}/${sliceIndex}`,
      {
        params: {
          window_center: windowCenter,
          window_width: windowWidth,
        },
      }
    );
    return data;
  },

  get3DVolume: async (
    fileId: string,
    orientation: ImageOrientation = 'axial'
  ): Promise<VolumeData> => {
    const { data } = await apiClient.get(`/api/v1/imaging/volume/${fileId}`, {
      params: { orientation },
    });
    return data;
  },

  getVoxel3D: async (
    fileId: string,
    startSlice?: number,
    endSlice?: number,
    angle: number = 320
  ): Promise<{ image: string }> => {
    const { data } = await apiClient.get(`/api/v1/imaging/voxel-3d/${fileId}`, {
      params: {
        start_slice: startSlice,
        end_slice: endSlice,
        angle,
      },
    });
    return data;
  },

  getMatplotlib2D: async (
    fileId: string,
    sliceIndex: number,
    windowCenter?: number,
    windowWidth?: number,
    colormap: string = 'gray',
    xMin?: number,
    xMax?: number,
    yMin?: number,
    yMax?: number,
    minimal: boolean = false,
    segmentationId?: string,
    overlayOpacity?: number
  ): Promise<{
    image: string;
    bbox?: {
      left: number;
      top: number;
      width: number;
      height: number;
      figure_width: number;
      figure_height: number;
    }
  }> => {
    const url = `/api/v1/imaging/matplotlib-2d/${fileId}/${sliceIndex}`;
    const params = {
      window_center: windowCenter,
      window_width: windowWidth,
      colormap,
      x_min: xMin,
      x_max: xMax,
      y_min: yMin,
      y_max: yMax,
      minimal,
      segmentation_id: segmentationId,
      overlay_opacity: overlayOpacity,
    };
    // Retry logic for transient 503 errors (server overload)
    const maxRetries = 3;
    let lastError: Error | null = null;

    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const { data } = await apiClient.get(url, { params });
        return data;
      } catch (error: unknown) {
        lastError = error as Error;
        const axiosError = error as { response?: { status: number } };

        // Only retry on 503 (Service Unavailable) errors
        if (axiosError.response?.status === 503 && attempt < maxRetries - 1) {
          const delay = Math.min(1000 * Math.pow(2, attempt), 5000); // Exponential backoff: 1s, 2s, 4s (max 5s)
          console.warn(`[ImagingAPI] 503 error, retrying in ${delay}ms (attempt ${attempt + 1}/${maxRetries})`);
          await new Promise(resolve => setTimeout(resolve, delay));
          continue;
        }

        console.error('[ImagingAPI] Matplotlib request failed:', error);
        throw error;
      }
    }

    // Should not reach here, but just in case
    throw lastError || new Error('Max retries exceeded');
  },

  getMetadata: async (fileId: string) => {
    const { data } = await apiClient.get(`/api/v1/imaging/metadata/${fileId}`);
    return data;
  },
};

// Health check
export const healthCheck = async () => {
  const { data } = await apiClient.get('/api/health');
  return data;
};

export default apiClient;
