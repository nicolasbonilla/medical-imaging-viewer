import React, { useCallback, useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  Upload,
  FileText,
  FileImage,
  File,
  X,
  Check,
  AlertCircle,
  Loader2,
  Pause,
} from 'lucide-react';
import { useDocumentUpload, DocumentUploadFile } from '@/hooks/useDocuments';
import { documentAPI } from '@/services/documentApi';
import type { Document, DocumentCategory } from '@/types';

interface DocumentUploaderProps {
  patientId: string;
  studyId?: string;
  defaultCategory?: DocumentCategory;
  onComplete?: (documents: Document[]) => void;
  onCancel?: () => void;
  maxFiles?: number;
  acceptedTypes?: string[];
}

const DEFAULT_ACCEPTED_TYPES = [
  '.pdf',
  '.doc',
  '.docx',
  '.jpg',
  '.jpeg',
  '.png',
  '.gif',
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'image/jpeg',
  'image/png',
  'image/gif',
];

const DOCUMENT_CATEGORIES: DocumentCategory[] = [
  'lab-result',
  'prescription',
  'clinical-note',
  'discharge-summary',
  'radiology-report',
  'consent-form',
  'referral',
  'operative-note',
  'pathology-report',
  'other',
];

export const DocumentUploader: React.FC<DocumentUploaderProps> = ({
  patientId,
  studyId,
  defaultCategory = 'other',
  onComplete,
  onCancel,
  maxFiles = 20,
  acceptedTypes = DEFAULT_ACCEPTED_TYPES,
}) => {
  const { t } = useTranslation();
  const [isDragOver, setIsDragOver] = useState(false);
  const [category, setCategory] = useState<DocumentCategory>(defaultCategory);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [documentDate, setDocumentDate] = useState(new Date().toISOString().split('T')[0]);
  const [uploadedDocs, setUploadedDocs] = useState<Document[]>([]);

  const {
    files,
    isUploading,
    totalProgress,
    addFiles,
    removeFile,
    clearFiles,
    startUpload,
    cancelUpload,
  } = useDocumentUpload({
    patientId,
    studyId,
    category,
    onSuccess: (doc) => {
      setUploadedDocs((prev) => [...prev, doc]);
    },
  });

  // Group files by status
  const fileStats = useMemo(() => {
    return {
      pending: files.filter((f) => f.status === 'pending').length,
      uploading: files.filter((f) => f.status === 'uploading').length,
      completed: files.filter((f) => f.status === 'completed').length,
      error: files.filter((f) => f.status === 'error').length,
    };
  }, [files]);

  // Handle upload completion
  const handleUploadComplete = useCallback(() => {
    if (uploadedDocs.length > 0 && onComplete) {
      onComplete(uploadedDocs);
    }
  }, [uploadedDocs, onComplete]);

  // Effect to trigger onComplete when all files are done
  React.useEffect(() => {
    if (!isUploading && fileStats.completed > 0 && fileStats.pending === 0 && fileStats.uploading === 0) {
      handleUploadComplete();
    }
  }, [isUploading, fileStats, handleUploadComplete]);

  // Handle drag events
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      const droppedFiles = e.dataTransfer.files;
      if (droppedFiles.length > 0) {
        // Filter by accepted types
        const validFiles = Array.from(droppedFiles).filter((file) => {
          const extension = '.' + file.name.toLowerCase().split('.').pop();
          return acceptedTypes.includes(extension) || acceptedTypes.includes(file.type);
        });

        if (validFiles.length > 0) {
          addFiles(validFiles.slice(0, maxFiles - files.length));
        }
      }
    },
    [addFiles, acceptedTypes, maxFiles, files.length]
  );

  // Handle file input change
  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFiles = e.target.files;
      if (selectedFiles && selectedFiles.length > 0) {
        addFiles(Array.from(selectedFiles).slice(0, maxFiles - files.length));
      }
      // Reset input
      e.target.value = '';
    },
    [addFiles, maxFiles, files.length]
  );

  // Handle start upload
  const handleStartUpload = useCallback(() => {
    const docTitle = title.trim() || t('document.untitled');
    startUpload(docTitle, documentDate, description.trim() || undefined);
  }, [title, documentDate, description, startUpload, t]);

  // Get file icon based on content type
  const getFileIcon = (file: File) => {
    if (file.type.startsWith('image/')) {
      return <FileImage className="w-4 h-4 text-green-500" />;
    }
    if (file.type === 'application/pdf') {
      return <FileText className="w-4 h-4 text-red-500" />;
    }
    if (file.type.includes('word') || file.type.includes('document')) {
      return <FileText className="w-4 h-4 text-blue-500" />;
    }
    return <File className="w-4 h-4 text-gray-500" />;
  };

  // Get status icon
  const getStatusIcon = (status: DocumentUploadFile['status']) => {
    switch (status) {
      case 'pending':
        return <File className="w-4 h-4 text-gray-400" />;
      case 'uploading':
        return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
      case 'completed':
        return <Check className="w-4 h-4 text-green-500" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-500" />;
    }
  };

  // Get status color
  const getStatusColor = (status: DocumentUploadFile['status']) => {
    switch (status) {
      case 'pending':
        return 'bg-gray-100 dark:bg-gray-700';
      case 'uploading':
        return 'bg-blue-50 dark:bg-blue-900/20';
      case 'completed':
        return 'bg-green-50 dark:bg-green-900/20';
      case 'error':
        return 'bg-red-50 dark:bg-red-900/20';
    }
  };

  // Validation
  const canUpload = files.length > 0 && fileStats.pending > 0 && !isUploading;

  return (
    <div className="space-y-6">
      {/* Document metadata form */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Title */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('document.title')} *
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t('document.titlePlaceholder')}
            className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            disabled={isUploading}
          />
        </div>

        {/* Category */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('document.category')} *
          </label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as DocumentCategory)}
            className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
            disabled={isUploading}
          >
            {DOCUMENT_CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {t(`document.categories.${cat}`)}
              </option>
            ))}
          </select>
        </div>

        {/* Document Date */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('document.documentDate')} *
          </label>
          <input
            type="date"
            value={documentDate}
            onChange={(e) => setDocumentDate(e.target.value)}
            className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
            disabled={isUploading}
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('document.description')}
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t('document.descriptionPlaceholder')}
            className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
            disabled={isUploading}
          />
        </div>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
          isDragOver
            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
            : 'border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500'
        }`}
      >
        <input
          type="file"
          multiple
          accept={acceptedTypes.join(',')}
          onChange={handleFileChange}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          disabled={isUploading || files.length >= maxFiles}
        />

        <div className="space-y-4">
          <div
            className={`w-16 h-16 mx-auto rounded-full flex items-center justify-center ${
              isDragOver ? 'bg-blue-100 dark:bg-blue-800' : 'bg-gray-100 dark:bg-gray-700'
            }`}
          >
            <Upload
              className={`w-8 h-8 ${
                isDragOver ? 'text-blue-600' : 'text-gray-400 dark:text-gray-500'
              }`}
            />
          </div>

          <div>
            <p className="text-lg font-medium text-gray-900 dark:text-gray-100">
              {t('document.upload.dropzone')}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {t('document.upload.orBrowse')}
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">PDF</span>
            <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">Word (.doc, .docx)</span>
            <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">
              {t('document.upload.images')} (JPG, PNG)
            </span>
          </div>

          <p className="text-xs text-gray-400 dark:text-gray-500">
            {t('document.upload.maxSize', { size: '100MB' })}
          </p>
        </div>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="space-y-3">
          {/* Stats bar */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4 text-sm">
              <span className="text-gray-600 dark:text-gray-300">
                {t('document.upload.filesSelected', { count: files.length })}
              </span>
              {fileStats.completed > 0 && (
                <span className="text-green-600">
                  {t('document.upload.completed', { count: fileStats.completed })}
                </span>
              )}
              {fileStats.error > 0 && (
                <span className="text-red-600">
                  {t('document.upload.failed', { count: fileStats.error })}
                </span>
              )}
            </div>

            <button
              onClick={clearFiles}
              disabled={isUploading}
              className="text-sm text-gray-500 hover:text-red-600 disabled:opacity-50"
            >
              {t('common.clearAll')}
            </button>
          </div>

          {/* Progress bar (when uploading) */}
          {isUploading && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600 dark:text-gray-300">
                  {t('document.upload.uploading')}
                </span>
                <span className="font-medium text-blue-600">{totalProgress}%</span>
              </div>
              <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-blue-500"
                  initial={{ width: 0 }}
                  animate={{ width: `${totalProgress}%` }}
                  transition={{ duration: 0.3 }}
                />
              </div>
            </div>
          )}

          {/* File list */}
          <div className="max-h-64 overflow-y-auto space-y-2">
            <AnimatePresence mode="popLayout">
              {files.map((file) => (
                <motion.div
                  key={file.id}
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className={`flex items-center gap-3 p-3 rounded-lg ${getStatusColor(file.status)}`}
                >
                  {/* File icon */}
                  {file.status === 'pending' ? getFileIcon(file.file) : getStatusIcon(file.status)}

                  {/* File info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {file.file.name}
                    </p>
                    <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                      <span>{documentAPI.formatFileSize(file.file.size)}</span>
                      {file.status === 'uploading' && (
                        <span className="text-blue-600">{file.progress}%</span>
                      )}
                      {file.error && <span className="text-red-600">{file.error}</span>}
                    </div>
                  </div>

                  {/* Progress bar (individual) */}
                  {file.status === 'uploading' && (
                    <div className="w-20 h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 transition-all duration-300"
                        style={{ width: `${file.progress}%` }}
                      />
                    </div>
                  )}

                  {/* Remove button */}
                  {file.status === 'pending' && !isUploading && (
                    <button
                      onClick={() => removeFile(file.id)}
                      className="p-1 text-gray-400 hover:text-red-600 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        {onCancel && (
          <button
            onClick={onCancel}
            disabled={isUploading}
            className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50"
          >
            {t('common.cancel')}
          </button>
        )}

        {isUploading ? (
          <button
            onClick={cancelUpload}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
          >
            <Pause className="w-4 h-4" />
            {t('document.upload.cancel')}
          </button>
        ) : (
          <button
            onClick={handleStartUpload}
            disabled={!canUpload}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Upload className="w-4 h-4" />
            {t('document.upload.start')}
            {fileStats.pending > 0 && (
              <span className="px-2 py-0.5 bg-blue-500 rounded-full text-xs">
                {fileStats.pending}
              </span>
            )}
          </button>
        )}
      </div>
    </div>
  );
};

export default DocumentUploader;
