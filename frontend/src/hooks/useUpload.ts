import { useState, useCallback, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { studyAPI } from '@/services/studyApi';
import { studyKeys } from './useStudies';
import type {
  UploadInitRequest,
  UploadInitResponse,
  UploadCompleteResponse,
  Modality,
} from '@/types';

export interface UploadFile {
  id: string;
  file: File;
  status: 'pending' | 'uploading' | 'processing' | 'completed' | 'error';
  progress: number;
  error?: string;
  uploadId?: string;
  seriesId?: string;
  instanceId?: string;
}

export interface UseUploadOptions {
  studyId: string;
  seriesNumber?: number;
  modality?: Modality;
  seriesDescription?: string;
  onUploadComplete?: (file: UploadFile, response: UploadCompleteResponse) => void;
  onAllComplete?: (files: UploadFile[]) => void;
  onError?: (file: UploadFile, error: Error) => void;
}

export interface UseUploadReturn {
  files: UploadFile[];
  isUploading: boolean;
  totalProgress: number;
  addFiles: (files: FileList | File[]) => void;
  removeFile: (fileId: string) => void;
  clearFiles: () => void;
  startUpload: () => Promise<void>;
  cancelUpload: () => void;
}

/**
 * Hook for uploading DICOM/NIfTI files to GCS with progress tracking
 */
export function useUpload(options: UseUploadOptions): UseUploadReturn {
  const {
    studyId,
    seriesNumber = 1,
    modality,
    seriesDescription,
    onUploadComplete,
    onAllComplete,
    onError,
  } = options;

  const queryClient = useQueryClient();
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentSeriesRef = useRef<number>(seriesNumber);

  // Calculate total progress
  const totalProgress = files.length > 0
    ? Math.round(files.reduce((sum, f) => sum + f.progress, 0) / files.length)
    : 0;

  // Generate unique ID for file
  const generateFileId = useCallback((): string => {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }, []);

  // Add files to upload queue
  const addFiles = useCallback((newFiles: FileList | File[]) => {
    const fileArray = Array.from(newFiles);
    const uploadFiles: UploadFile[] = fileArray.map((file) => ({
      id: generateFileId(),
      file,
      status: 'pending',
      progress: 0,
    }));
    setFiles((prev) => [...prev, ...uploadFiles]);
  }, [generateFileId]);

  // Remove a file from queue
  const removeFile = useCallback((fileId: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== fileId));
  }, []);

  // Clear all files
  const clearFiles = useCallback(() => {
    setFiles([]);
  }, []);

  // Update a specific file's state
  const updateFile = useCallback((fileId: string, updates: Partial<UploadFile>) => {
    setFiles((prev) =>
      prev.map((f) => (f.id === fileId ? { ...f, ...updates } : f))
    );
  }, []);

  // Determine content type from file
  const getContentType = (file: File): string => {
    // Check by extension first
    const extension = file.name.toLowerCase().split('.').pop();

    switch (extension) {
      case 'dcm':
        return 'application/dicom';
      case 'nii':
        return 'application/x-nifti';
      case 'gz':
        if (file.name.toLowerCase().endsWith('.nii.gz')) {
          return 'application/x-nifti-compressed';
        }
        return 'application/gzip';
      default:
        // Check MIME type
        if (file.type) {
          return file.type;
        }
        return 'application/octet-stream';
    }
  };

  // Upload a single file
  const uploadSingleFile = async (uploadFile: UploadFile): Promise<UploadCompleteResponse> => {
    const { id, file } = uploadFile;

    // Step 1: Initialize upload (get signed URL)
    updateFile(id, { status: 'uploading', progress: 5 });

    const initRequest: UploadInitRequest = {
      study_id: studyId,
      series_number: currentSeriesRef.current,
      filename: file.name,
      content_type: getContentType(file),
      file_size_bytes: file.size,
      modality,
      series_description: seriesDescription,
    };

    const initResponse = await studyAPI.initUpload(initRequest);

    updateFile(id, {
      uploadId: initResponse.upload_id,
      seriesId: initResponse.series_id,
      progress: 10,
    });

    // Step 2: Upload to GCS with progress
    await studyAPI.uploadToGCS(
      initResponse.signed_url,
      file,
      initResponse.headers || { 'Content-Type': getContentType(file) },
      (progress) => {
        // Map progress from 10% to 85%
        const mappedProgress = 10 + Math.round(progress * 0.75);
        updateFile(id, { progress: mappedProgress });
      }
    );

    updateFile(id, { status: 'processing', progress: 90 });

    // Step 3: Calculate checksum
    const checksum = await studyAPI.calculateChecksum(file);

    updateFile(id, { progress: 95 });

    // Step 4: Complete upload
    const completeResponse = await studyAPI.completeUpload({
      upload_id: initResponse.upload_id,
      checksum_sha256: checksum,
    });

    updateFile(id, {
      status: 'completed',
      progress: 100,
      instanceId: completeResponse.instance_id,
    });

    return completeResponse;
  };

  // Start uploading all pending files
  const startUpload = useCallback(async () => {
    const pendingFiles = files.filter((f) => f.status === 'pending');
    if (pendingFiles.length === 0) return;

    setIsUploading(true);
    abortControllerRef.current = new AbortController();

    const completedFiles: UploadFile[] = [];

    for (const uploadFile of pendingFiles) {
      // Check for abort
      if (abortControllerRef.current?.signal.aborted) {
        break;
      }

      try {
        const response = await uploadSingleFile(uploadFile);

        const updatedFile = {
          ...uploadFile,
          status: 'completed' as const,
          progress: 100,
          instanceId: response.instance_id,
        };

        completedFiles.push(updatedFile);

        if (onUploadComplete) {
          onUploadComplete(updatedFile, response);
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Upload failed';

        updateFile(uploadFile.id, {
          status: 'error',
          error: errorMessage,
        });

        if (onError) {
          onError(uploadFile, error instanceof Error ? error : new Error(errorMessage));
        }
      }
    }

    setIsUploading(false);
    abortControllerRef.current = null;

    // Invalidate study queries to refresh data
    queryClient.invalidateQueries({ queryKey: studyKeys.detail(studyId) });
    queryClient.invalidateQueries({ queryKey: studyKeys.series(studyId) });

    if (onAllComplete && completedFiles.length > 0) {
      onAllComplete(completedFiles);
    }
  }, [files, studyId, onUploadComplete, onAllComplete, onError, queryClient, updateFile]);

  // Cancel ongoing upload
  const cancelUpload = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsUploading(false);
  }, []);

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

/**
 * Hook for downloading study files
 */
export function useStudyDownload(studyId: string) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(0);

  const downloadInstance = useCallback(async (instanceId: string) => {
    try {
      const { url, filename } = await studyAPI.getDownloadUrl(instanceId);

      // Create a link and trigger download
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.target = '_blank';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      console.error('Download failed:', error);
      throw error;
    }
  }, []);

  const downloadStudy = useCallback(async () => {
    setIsDownloading(true);
    setDownloadProgress(0);

    try {
      const urls = await studyAPI.getStudyDownloadUrls(studyId);

      for (let i = 0; i < urls.length; i++) {
        const { url, filename } = urls[i];

        // Create a link and trigger download
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.target = '_blank';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        setDownloadProgress(Math.round(((i + 1) / urls.length) * 100));

        // Small delay between downloads to prevent overwhelming browser
        if (i < urls.length - 1) {
          await new Promise((resolve) => setTimeout(resolve, 500));
        }
      }
    } finally {
      setIsDownloading(false);
      setDownloadProgress(0);
    }
  }, [studyId]);

  return {
    isDownloading,
    downloadProgress,
    downloadInstance,
    downloadStudy,
  };
}
