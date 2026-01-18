import { apiClient } from './apiClient';
import type {
  ImagingStudy,
  StudyCreate,
  StudyUpdate,
  StudyListResponse,
  ImagingSeries,
  ImagingInstance,
  UploadInitRequest,
  UploadInitResponse,
  UploadCompleteRequest,
  UploadCompleteResponse,
  DownloadUrlResponse,
} from '@/types';

const API_PREFIX = '/api/v1/studies';

export const studyAPI = {
  /**
   * Create a new imaging study
   */
  async create(data: StudyCreate): Promise<ImagingStudy> {
    const response = await apiClient.post<ImagingStudy>(API_PREFIX, data);
    return response.data;
  },

  /**
   * Get a study by ID
   */
  async getById(studyId: string, includeStats: boolean = true): Promise<ImagingStudy> {
    const response = await apiClient.get<ImagingStudy>(
      `${API_PREFIX}/${studyId}`,
      { params: { include_stats: includeStats } }
    );
    return response.data;
  },

  /**
   * Get a study by accession number
   */
  async getByAccession(accessionNumber: string): Promise<ImagingStudy | null> {
    try {
      const response = await apiClient.get<ImagingStudy>(
        `${API_PREFIX}/accession/${accessionNumber}`
      );
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  },

  /**
   * List studies with pagination
   */
  async list(
    page: number = 1,
    pageSize: number = 20,
    status?: string
  ): Promise<StudyListResponse> {
    const response = await apiClient.get<StudyListResponse>(API_PREFIX, {
      params: {
        page,
        page_size: pageSize,
        ...(status && { status }),
      },
    });
    return response.data;
  },

  /**
   * Search studies with filters
   */
  async search(params: {
    patient_id?: string;
    modality?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
    page?: number;
    page_size?: number;
  }): Promise<StudyListResponse> {
    const response = await apiClient.get<StudyListResponse>(
      `${API_PREFIX}/search`,
      { params }
    );
    return response.data;
  },

  /**
   * List studies for a specific patient
   */
  async listByPatient(
    patientId: string,
    page: number = 1,
    pageSize: number = 20
  ): Promise<StudyListResponse> {
    const response = await apiClient.get<StudyListResponse>(
      `${API_PREFIX}/patient/${patientId}`,
      { params: { page, page_size: pageSize } }
    );
    return response.data;
  },

  /**
   * Update a study
   */
  async update(studyId: string, data: StudyUpdate): Promise<ImagingStudy> {
    const response = await apiClient.patch<ImagingStudy>(
      `${API_PREFIX}/${studyId}`,
      data
    );
    return response.data;
  },

  /**
   * Delete a study (soft delete by default)
   */
  async delete(studyId: string, hardDelete: boolean = false): Promise<void> {
    await apiClient.delete(`${API_PREFIX}/${studyId}`, {
      params: { hard_delete: hardDelete },
    });
  },

  // =========================================================================
  // Series Operations
  // =========================================================================

  /**
   * List series for a study
   */
  async listSeries(studyId: string): Promise<ImagingSeries[]> {
    const response = await apiClient.get<ImagingSeries[]>(
      `${API_PREFIX}/${studyId}/series`
    );
    return response.data;
  },

  /**
   * Get a specific series
   */
  async getSeries(seriesId: string): Promise<ImagingSeries> {
    const response = await apiClient.get<ImagingSeries>(
      `${API_PREFIX}/series/${seriesId}`
    );
    return response.data;
  },

  /**
   * Delete a series
   */
  async deleteSeries(seriesId: string): Promise<void> {
    await apiClient.delete(`${API_PREFIX}/series/${seriesId}`);
  },

  // =========================================================================
  // Instance Operations
  // =========================================================================

  /**
   * List instances for a series
   */
  async listInstances(seriesId: string): Promise<ImagingInstance[]> {
    const response = await apiClient.get<ImagingInstance[]>(
      `${API_PREFIX}/series/${seriesId}/instances`
    );
    return response.data;
  },

  /**
   * Get a specific instance
   */
  async getInstance(instanceId: string): Promise<ImagingInstance> {
    const response = await apiClient.get<ImagingInstance>(
      `${API_PREFIX}/instances/${instanceId}`
    );
    return response.data;
  },

  /**
   * Delete an instance
   */
  async deleteInstance(instanceId: string): Promise<void> {
    await apiClient.delete(`${API_PREFIX}/instances/${instanceId}`);
  },

  // =========================================================================
  // Upload Operations
  // =========================================================================

  /**
   * Initialize a file upload (get signed URL)
   */
  async initUpload(request: UploadInitRequest): Promise<UploadInitResponse> {
    const response = await apiClient.post<UploadInitResponse>(
      `${API_PREFIX}/upload/init`,
      request
    );
    return response.data;
  },

  /**
   * Complete a file upload after uploading to GCS
   */
  async completeUpload(request: UploadCompleteRequest): Promise<UploadCompleteResponse> {
    const response = await apiClient.post<UploadCompleteResponse>(
      `${API_PREFIX}/upload/complete`,
      request
    );
    return response.data;
  },

  /**
   * Upload a file to GCS using signed URL
   */
  async uploadToGCS(
    signedUrl: string,
    file: File,
    headers: Record<string, string>,
    onProgress?: (progress: number) => void
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable && onProgress) {
          const progress = Math.round((event.loaded / event.total) * 100);
          onProgress(progress);
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve();
        } else {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Upload failed'));
      });

      xhr.open('PUT', signedUrl);

      // Set required headers (if provided)
      if (headers && typeof headers === 'object') {
        Object.entries(headers).forEach(([key, value]) => {
          xhr.setRequestHeader(key, value);
        });
      }

      xhr.send(file);
    });
  },

  /**
   * Calculate SHA-256 checksum of a file
   */
  async calculateChecksum(file: File): Promise<string> {
    const buffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
    return hashHex;
  },

  // =========================================================================
  // Download Operations
  // =========================================================================

  /**
   * Get a signed download URL for an instance
   */
  async getDownloadUrl(
    instanceId: string,
    expirationMinutes: number = 60
  ): Promise<DownloadUrlResponse> {
    const response = await apiClient.get<DownloadUrlResponse>(
      `${API_PREFIX}/instances/${instanceId}/download-url`,
      { params: { expiration_minutes: expirationMinutes } }
    );
    return response.data;
  },

  /**
   * Get download URLs for all instances in a study
   */
  async getStudyDownloadUrls(
    studyId: string,
    expirationMinutes: number = 60
  ): Promise<DownloadUrlResponse[]> {
    const response = await apiClient.get<DownloadUrlResponse[]>(
      `${API_PREFIX}/${studyId}/download-urls`,
      { params: { expiration_minutes: expirationMinutes } }
    );
    return response.data;
  },
};
