import axios from 'axios';
import type {
  DriveFileInfo,
  ImageSeriesResponse,
  ImageSlice,
  WindowLevelRequest,
  ImageOrientation,
  VolumeData,
} from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Google Drive API
export const driveAPI = {
  authenticate: async () => {
    const { data } = await api.get('/api/v1/drive/auth');
    return data;
  },

  listFolders: async (parentId?: string): Promise<DriveFileInfo[]> => {
    const { data } = await api.get('/api/v1/drive/folders', {
      params: { parent_id: parentId },
    });
    return data;
  },

  listFiles: async (folderId?: string, pageSize = 100): Promise<DriveFileInfo[]> => {
    const { data } = await api.get('/api/v1/drive/files', {
      params: { folder_id: folderId, page_size: pageSize },
    });
    return data;
  },

  getFileMetadata: async (fileId: string): Promise<DriveFileInfo> => {
    const { data } = await api.get(`/api/v1/drive/files/${fileId}/metadata`);
    return data;
  },

  downloadFile: async (fileId: string) => {
    const { data } = await api.get(`/api/v1/drive/files/${fileId}/download`);
    return data;
  },
};

// Medical Imaging API
export const imagingAPI = {
  processImage: async (
    fileId: string,
    startSlice?: number,
    endSlice?: number,
    maxSlices = 50
  ): Promise<ImageSeriesResponse> => {
    const { data } = await api.get(`/api/v1/imaging/process/${fileId}`, {
      params: {
        start_slice: startSlice,
        end_slice: endSlice,
        max_slices: maxSlices,
      },
    });
    return data;
  },

  applyWindowLevel: async (
    fileId: string,
    request: WindowLevelRequest
  ): Promise<ImageSlice> => {
    const { data } = await api.post(
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
    const { data } = await api.get(
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
    const { data } = await api.get(`/api/v1/imaging/volume/${fileId}`, {
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
    const { data } = await api.get(`/api/v1/imaging/voxel-3d/${fileId}`, {
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
    segmentationId?: string
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
    };
    console.log('📡 MAKING MATPLOTLIB REQUEST:', url, 'params:', params);
    try {
      const { data } = await api.get(url, { params });
      console.log('✅ MATPLOTLIB RESPONSE RECEIVED, data length:', data?.image?.length || 0);
      return data;
    } catch (error) {
      console.error('❌ MATPLOTLIB REQUEST FAILED:', error);
      throw error;
    }
  },

  getMetadata: async (fileId: string) => {
    const { data } = await api.get(`/api/v1/imaging/metadata/${fileId}`);
    return data;
  },
};

// Health check
export const healthCheck = async () => {
  const { data } = await api.get('/api/health');
  return data;
};

export default api;
