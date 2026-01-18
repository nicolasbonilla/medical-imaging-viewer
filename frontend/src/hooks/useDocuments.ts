import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useCallback } from 'react';
import { documentAPI, DocumentSearchParams } from '@/services/documentApi';
import type {
  Document,
  DocumentUpdate,
  DocumentListResponse,
  DocumentVersion,
  DocumentUploadInit,
  DocumentCategory,
} from '@/types';

// Query keys
export const documentKeys = {
  all: ['documents'] as const,
  lists: () => [...documentKeys.all, 'list'] as const,
  list: (params: DocumentSearchParams) => [...documentKeys.lists(), params] as const,
  details: () => [...documentKeys.all, 'detail'] as const,
  detail: (id: string) => [...documentKeys.details(), id] as const,
  byPatient: (patientId: string, params?: { page?: number; pageSize?: number }) =>
    [...documentKeys.all, 'patient', patientId, params] as const,
  byStudy: (studyId: string, params?: { page?: number; pageSize?: number }) =>
    [...documentKeys.all, 'study', studyId, params] as const,
  versions: (documentId: string) => [...documentKeys.detail(documentId), 'versions'] as const,
  version: (versionId: string) => [...documentKeys.all, 'version', versionId] as const,
};

/**
 * Hook to fetch paginated list of documents with filters
 */
export function useDocumentList(params: DocumentSearchParams = {}) {
  return useQuery<DocumentListResponse>({
    queryKey: documentKeys.list(params),
    queryFn: () => documentAPI.list(params),
  });
}

/**
 * Hook to fetch documents for a specific patient
 */
export function usePatientDocuments(
  patientId: string | undefined,
  page: number = 1,
  pageSize: number = 20
) {
  return useQuery<DocumentListResponse>({
    queryKey: documentKeys.byPatient(patientId!, { page, pageSize }),
    queryFn: () => documentAPI.listByPatient(patientId!, page, pageSize),
    enabled: !!patientId,
  });
}

/**
 * Hook to fetch documents for a specific study
 */
export function useStudyDocuments(
  studyId: string | undefined,
  page: number = 1,
  pageSize: number = 20
) {
  return useQuery<DocumentListResponse>({
    queryKey: documentKeys.byStudy(studyId!, { page, pageSize }),
    queryFn: () => documentAPI.listByStudy(studyId!, page, pageSize),
    enabled: !!studyId,
  });
}

/**
 * Hook to fetch a single document by ID
 */
export function useDocument(documentId: string | undefined) {
  return useQuery<Document>({
    queryKey: documentKeys.detail(documentId!),
    queryFn: () => documentAPI.getById(documentId!),
    enabled: !!documentId,
  });
}

/**
 * Hook to fetch all versions of a document
 */
export function useDocumentVersions(documentId: string | undefined) {
  return useQuery<DocumentVersion[]>({
    queryKey: documentKeys.versions(documentId!),
    queryFn: () => documentAPI.listVersions(documentId!),
    enabled: !!documentId,
  });
}

/**
 * Hook to fetch a specific version
 */
export function useDocumentVersion(versionId: string | undefined) {
  return useQuery<DocumentVersion>({
    queryKey: documentKeys.version(versionId!),
    queryFn: () => documentAPI.getVersion(versionId!),
    enabled: !!versionId,
  });
}

/**
 * Hook to update a document
 */
export function useUpdateDocument() {
  const queryClient = useQueryClient();

  return useMutation<Document, Error, { id: string; data: DocumentUpdate }>({
    mutationFn: ({ id, data }) => documentAPI.update(id, data),
    onSuccess: (document) => {
      // Update the document in cache
      queryClient.setQueryData(documentKeys.detail(document.id), document);
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      // Invalidate patient documents if we have patient_id
      if (document.patient_id) {
        queryClient.invalidateQueries({
          queryKey: documentKeys.byPatient(document.patient_id),
        });
      }
    },
  });
}

/**
 * Hook to delete a document
 */
export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation<
    void,
    Error,
    { id: string; patientId: string; studyId?: string; hardDelete?: boolean }
  >({
    mutationFn: ({ id, hardDelete }) => documentAPI.delete(id, hardDelete),
    onSuccess: (_, { id, patientId, studyId }) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: documentKeys.detail(id) });
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      // Invalidate patient's document list
      queryClient.invalidateQueries({ queryKey: documentKeys.byPatient(patientId) });
      // Invalidate study's document list if applicable
      if (studyId) {
        queryClient.invalidateQueries({ queryKey: documentKeys.byStudy(studyId) });
      }
    },
  });
}

// ============================================================================
// Document Upload Hook
// ============================================================================

export interface DocumentUploadFile {
  id: string;
  file: File;
  status: 'pending' | 'uploading' | 'completed' | 'error';
  progress: number;
  error?: string;
  documentId?: string;
}

export interface UseDocumentUploadOptions {
  patientId: string;
  studyId?: string;
  category: DocumentCategory;
  onSuccess?: (document: Document) => void;
  onError?: (error: Error, file: File) => void;
}

export interface UseDocumentUploadReturn {
  files: DocumentUploadFile[];
  isUploading: boolean;
  totalProgress: number;
  addFiles: (files: FileList | File[]) => void;
  removeFile: (fileId: string) => void;
  clearFiles: () => void;
  startUpload: (title: string, documentDate: string, description?: string) => Promise<void>;
  cancelUpload: () => void;
}

export function useDocumentUpload(options: UseDocumentUploadOptions): UseDocumentUploadReturn {
  const [files, setFiles] = useState<DocumentUploadFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  const queryClient = useQueryClient();

  const addFiles = useCallback((newFiles: FileList | File[]) => {
    const fileArray = Array.from(newFiles);
    const uploadFiles: DocumentUploadFile[] = fileArray.map((file) => ({
      id: `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      status: 'pending',
      progress: 0,
    }));
    setFiles((prev) => [...prev, ...uploadFiles]);
  }, []);

  const removeFile = useCallback((fileId: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== fileId));
  }, []);

  const clearFiles = useCallback(() => {
    setFiles([]);
  }, []);

  const cancelUpload = useCallback(() => {
    if (abortController) {
      abortController.abort();
      setAbortController(null);
    }
    setIsUploading(false);
    setFiles((prev) =>
      prev.map((f) =>
        f.status === 'uploading' ? { ...f, status: 'error', error: 'Upload cancelled' } : f
      )
    );
  }, [abortController]);

  const startUpload = useCallback(
    async (title: string, documentDate: string, description?: string) => {
      const controller = new AbortController();
      setAbortController(controller);
      setIsUploading(true);

      const pendingFiles = files.filter((f) => f.status === 'pending');

      for (const uploadFile of pendingFiles) {
        if (controller.signal.aborted) break;

        try {
          // Update status to uploading
          setFiles((prev) =>
            prev.map((f) => (f.id === uploadFile.id ? { ...f, status: 'uploading' } : f))
          );

          // Calculate checksum
          const checksum = await documentAPI.calculateChecksum(uploadFile.file);

          // Initialize upload
          const initRequest: DocumentUploadInit = {
            patient_id: options.patientId,
            study_id: options.studyId,
            title: pendingFiles.length > 1 ? `${title} - ${uploadFile.file.name}` : title,
            category: options.category,
            document_date: documentDate,
            filename: uploadFile.file.name,
            content_type: uploadFile.file.type || 'application/octet-stream',
            file_size_bytes: uploadFile.file.size,
            description,
          };

          const initResponse = await documentAPI.initUpload(initRequest);

          // Upload to GCS
          await documentAPI.uploadToGCS(
            initResponse.signed_url,
            uploadFile.file,
            initResponse.headers,
            (progress) => {
              setFiles((prev) =>
                prev.map((f) => (f.id === uploadFile.id ? { ...f, progress } : f))
              );
            }
          );

          // Complete upload
          const completeResponse = await documentAPI.completeUpload({
            upload_id: initResponse.upload_id,
            checksum_sha256: checksum,
          });

          // Update status to completed
          setFiles((prev) =>
            prev.map((f) =>
              f.id === uploadFile.id
                ? { ...f, status: 'completed', progress: 100, documentId: completeResponse.document.id }
                : f
            )
          );

          // Notify success
          options.onSuccess?.(completeResponse.document);
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Upload failed';
          setFiles((prev) =>
            prev.map((f) =>
              f.id === uploadFile.id ? { ...f, status: 'error', error: errorMessage } : f
            )
          );
          options.onError?.(error instanceof Error ? error : new Error(errorMessage), uploadFile.file);
        }
      }

      // Invalidate queries
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: documentKeys.byPatient(options.patientId) });
      if (options.studyId) {
        queryClient.invalidateQueries({ queryKey: documentKeys.byStudy(options.studyId) });
      }

      setIsUploading(false);
      setAbortController(null);
    },
    [files, options, queryClient]
  );

  const totalProgress =
    files.length > 0
      ? Math.round(files.reduce((sum, f) => sum + f.progress, 0) / files.length)
      : 0;

  return {
    files,
    isUploading,
    totalProgress,
    addFiles,
    removeFile,
    clearFiles,
    startUpload,
    cancelUpload,
  };
}

// ============================================================================
// Document Version Upload Hook
// ============================================================================

export interface UseVersionUploadOptions {
  documentId: string;
  onSuccess?: (version: DocumentVersion) => void;
  onError?: (error: Error) => void;
}

export function useVersionUpload(options: UseVersionUploadOptions) {
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const uploadVersion = useCallback(
    async (file: File, changeSummary?: string) => {
      setIsUploading(true);
      setProgress(0);
      setError(null);

      try {
        // Calculate checksum
        const checksum = await documentAPI.calculateChecksum(file);

        // Initialize version upload
        const initResponse = await documentAPI.initVersionUpload({
          document_id: options.documentId,
          filename: file.name,
          content_type: file.type || 'application/octet-stream',
          file_size_bytes: file.size,
          change_summary: changeSummary,
        });

        // Upload to GCS
        await documentAPI.uploadToGCS(
          initResponse.signed_url,
          file,
          initResponse.headers,
          setProgress
        );

        // Complete upload
        const completeResponse = await documentAPI.completeVersionUpload({
          upload_id: initResponse.upload_id,
          checksum_sha256: checksum,
        });

        // Invalidate queries
        queryClient.invalidateQueries({ queryKey: documentKeys.detail(options.documentId) });
        queryClient.invalidateQueries({ queryKey: documentKeys.versions(options.documentId) });
        queryClient.invalidateQueries({ queryKey: documentKeys.lists() });

        options.onSuccess?.(completeResponse.version);
        return completeResponse.version;
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Version upload failed';
        setError(errorMessage);
        options.onError?.(err instanceof Error ? err : new Error(errorMessage));
        throw err;
      } finally {
        setIsUploading(false);
      }
    },
    [options, queryClient]
  );

  return {
    uploadVersion,
    isUploading,
    progress,
    error,
  };
}

// ============================================================================
// Document Download Hook
// ============================================================================

export function useDocumentDownload() {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const downloadDocument = useCallback(async (documentId: string, version?: number) => {
    setIsDownloading(true);
    setError(null);

    try {
      const downloadUrl = await documentAPI.getDownloadUrl(documentId, version);

      // Create a temporary link and click it
      const link = document.createElement('a');
      link.href = downloadUrl.url;
      link.download = downloadUrl.filename;
      link.target = '_blank';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      return downloadUrl;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Download failed';
      setError(errorMessage);
      throw err;
    } finally {
      setIsDownloading(false);
    }
  }, []);

  const getPreviewUrl = useCallback(async (documentId: string, version?: number) => {
    try {
      const downloadUrl = await documentAPI.getDownloadUrl(documentId, version);
      return downloadUrl.url;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to get preview URL';
      setError(errorMessage);
      throw err;
    }
  }, []);

  return {
    downloadDocument,
    getPreviewUrl,
    isDownloading,
    error,
  };
}
