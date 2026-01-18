import { apiClient } from './apiClient';
import type {
  Document,
  DocumentUpdate,
  DocumentListResponse,
  DocumentVersion,
  DocumentUploadInit,
  DocumentUploadInitResponse,
  DocumentUploadComplete,
  DocumentUploadCompleteResponse,
  VersionUploadInit,
  VersionUploadInitResponse,
  DocumentDownloadUrl,
  DocumentCategory,
  DocumentStatus,
} from '@/types';

const API_PREFIX = '/api/v1/documents';

export interface DocumentSearchParams {
  patient_id?: string;
  study_id?: string;
  category?: DocumentCategory;
  status?: DocumentStatus;
  query?: string;
  page?: number;
  page_size?: number;
}

export const documentAPI = {
  // =========================================================================
  // Document CRUD Operations
  // =========================================================================

  /**
   * List documents with optional filters and pagination
   */
  async list(params: DocumentSearchParams = {}): Promise<DocumentListResponse> {
    const response = await apiClient.get<DocumentListResponse>(API_PREFIX, {
      params: {
        page: params.page ?? 1,
        page_size: params.page_size ?? 20,
        ...(params.patient_id && { patient_id: params.patient_id }),
        ...(params.study_id && { study_id: params.study_id }),
        ...(params.category && { category: params.category }),
        ...(params.status && { status: params.status }),
        ...(params.query && { query: params.query }),
      },
    });
    return response.data;
  },

  /**
   * List documents for a specific patient
   */
  async listByPatient(
    patientId: string,
    page: number = 1,
    pageSize: number = 20
  ): Promise<DocumentListResponse> {
    const response = await apiClient.get<DocumentListResponse>(
      `${API_PREFIX}/patient/${patientId}`,
      { params: { page, page_size: pageSize } }
    );
    return response.data;
  },

  /**
   * List documents linked to a specific study
   */
  async listByStudy(
    studyId: string,
    page: number = 1,
    pageSize: number = 20
  ): Promise<DocumentListResponse> {
    const response = await apiClient.get<DocumentListResponse>(
      `${API_PREFIX}/study/${studyId}`,
      { params: { page, page_size: pageSize } }
    );
    return response.data;
  },

  /**
   * Get a document by ID
   */
  async getById(documentId: string): Promise<Document> {
    const response = await apiClient.get<Document>(
      `${API_PREFIX}/${documentId}`
    );
    return response.data;
  },

  /**
   * Update document metadata
   */
  async update(documentId: string, data: DocumentUpdate): Promise<Document> {
    const response = await apiClient.patch<Document>(
      `${API_PREFIX}/${documentId}`,
      data
    );
    return response.data;
  },

  /**
   * Delete a document (soft delete by default)
   */
  async delete(documentId: string, hardDelete: boolean = false): Promise<void> {
    await apiClient.delete(`${API_PREFIX}/${documentId}`, {
      params: { hard_delete: hardDelete },
    });
  },

  // =========================================================================
  // Version Operations
  // =========================================================================

  /**
   * List all versions of a document
   */
  async listVersions(documentId: string): Promise<DocumentVersion[]> {
    const response = await apiClient.get<DocumentVersion[]>(
      `${API_PREFIX}/${documentId}/versions`
    );
    return response.data;
  },

  /**
   * Get a specific version by ID
   */
  async getVersion(versionId: string): Promise<DocumentVersion> {
    const response = await apiClient.get<DocumentVersion>(
      `${API_PREFIX}/versions/${versionId}`
    );
    return response.data;
  },

  // =========================================================================
  // Upload Operations
  // =========================================================================

  /**
   * Initialize a new document upload (get signed URL)
   */
  async initUpload(request: DocumentUploadInit): Promise<DocumentUploadInitResponse> {
    const response = await apiClient.post<DocumentUploadInitResponse>(
      `${API_PREFIX}/upload/init`,
      request
    );
    return response.data;
  },

  /**
   * Complete a document upload after uploading to GCS
   */
  async completeUpload(request: DocumentUploadComplete): Promise<DocumentUploadCompleteResponse> {
    const response = await apiClient.post<DocumentUploadCompleteResponse>(
      `${API_PREFIX}/upload/complete`,
      request
    );
    return response.data;
  },

  /**
   * Initialize upload for a new document version
   */
  async initVersionUpload(request: VersionUploadInit): Promise<VersionUploadInitResponse> {
    const response = await apiClient.post<VersionUploadInitResponse>(
      `${API_PREFIX}/versions/upload/init`,
      request
    );
    return response.data;
  },

  /**
   * Complete a version upload
   */
  async completeVersionUpload(request: {
    upload_id: string;
    checksum_sha256: string;
  }): Promise<{ version: DocumentVersion; document: Document }> {
    const response = await apiClient.post<{ version: DocumentVersion; document: Document }>(
      `${API_PREFIX}/versions/upload/complete`,
      request
    );
    return response.data;
  },

  /**
   * Upload a file to GCS using signed URL with progress tracking
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

      xhr.addEventListener('abort', () => {
        reject(new Error('Upload aborted'));
      });

      xhr.open('PUT', signedUrl);

      // Set required headers
      Object.entries(headers).forEach(([key, value]) => {
        xhr.setRequestHeader(key, value);
      });

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
   * Get a signed download URL for a document
   */
  async getDownloadUrl(
    documentId: string,
    version?: number,
    expirationMinutes: number = 60
  ): Promise<DocumentDownloadUrl> {
    const response = await apiClient.get<DocumentDownloadUrl>(
      `${API_PREFIX}/${documentId}/download-url`,
      {
        params: {
          expiration_minutes: expirationMinutes,
          ...(version !== undefined && { version }),
        },
      }
    );
    return response.data;
  },

  /**
   * Get download URLs for all documents of a patient
   */
  async getPatientDownloadUrls(
    patientId: string,
    expirationMinutes: number = 60
  ): Promise<DocumentDownloadUrl[]> {
    const response = await apiClient.get<DocumentDownloadUrl[]>(
      `${API_PREFIX}/patient/${patientId}/download-urls`,
      { params: { expiration_minutes: expirationMinutes } }
    );
    return response.data;
  },

  // =========================================================================
  // Utility Methods
  // =========================================================================

  /**
   * Get file extension from content type
   */
  getExtensionFromContentType(contentType: string): string {
    const extensionMap: Record<string, string> = {
      'application/pdf': 'pdf',
      'application/msword': 'doc',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
      'image/jpeg': 'jpg',
      'image/png': 'png',
      'image/gif': 'gif',
      'text/plain': 'txt',
      'text/html': 'html',
    };
    return extensionMap[contentType] || 'bin';
  },

  /**
   * Get content type from file extension
   */
  getContentTypeFromExtension(filename: string): string {
    const extension = filename.split('.').pop()?.toLowerCase() || '';
    const contentTypeMap: Record<string, string> = {
      pdf: 'application/pdf',
      doc: 'application/msword',
      docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      jpg: 'image/jpeg',
      jpeg: 'image/jpeg',
      png: 'image/png',
      gif: 'image/gif',
      txt: 'text/plain',
      html: 'text/html',
    };
    return contentTypeMap[extension] || 'application/octet-stream';
  },

  /**
   * Format file size for display
   */
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  },

  /**
   * Check if content type is previewable
   */
  isPreviewable(contentType: string): boolean {
    const previewableTypes = [
      'application/pdf',
      'image/jpeg',
      'image/png',
      'image/gif',
      'image/webp',
      'text/plain',
      'text/html',
    ];
    return previewableTypes.includes(contentType);
  },

  /**
   * Check if content type is an image
   */
  isImage(contentType: string): boolean {
    return contentType.startsWith('image/');
  },

  /**
   * Check if content type is PDF
   */
  isPDF(contentType: string): boolean {
    return contentType === 'application/pdf';
  },
};
