import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  X,
  Download,
  ZoomIn,
  ZoomOut,
  RotateCw,
  ChevronLeft,
  ChevronRight,
  Loader2,
  ExternalLink,
  FileText,
  File,
  History,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { useDocumentDownload, useDocumentVersions } from '@/hooks/useDocuments';
import { documentAPI } from '@/services/documentApi';
import type { Document, DocumentSummary, DocumentVersion } from '@/types';

interface DocumentViewerProps {
  document: Document | DocumentSummary;
  isOpen: boolean;
  onClose: () => void;
  initialVersion?: number;
}

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  document,
  isOpen,
  onClose,
  initialVersion,
}) => {
  const { t } = useTranslation();
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<number>(initialVersion || document.version);
  const [showVersions, setShowVersions] = useState(false);

  const { downloadDocument, isDownloading } = useDocumentDownload();
  const { data: versions } = useDocumentVersions(document.id);

  const isImage = documentAPI.isImage(document.content_type);
  const isPDF = documentAPI.isPDF(document.content_type);
  const isPreviewable = documentAPI.isPreviewable(document.content_type);

  // Load preview URL
  const loadPreview = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const url = await documentAPI.getDownloadUrl(
        document.id,
        selectedVersion !== document.version ? selectedVersion : undefined
      );
      setPreviewUrl(url.url);
    } catch (err) {
      setError(t('document.viewer.loadError'));
      console.error('Failed to load document preview:', err);
    } finally {
      setIsLoading(false);
    }
  }, [document.id, document.version, selectedVersion, t]);

  // Load preview when document changes or viewer opens
  useEffect(() => {
    if (isOpen && isPreviewable) {
      loadPreview();
    }
    return () => {
      setPreviewUrl(null);
      setZoom(1);
      setRotation(0);
    };
  }, [isOpen, isPreviewable, loadPreview]);

  // Handle download
  const handleDownload = useCallback(async () => {
    try {
      await downloadDocument(document.id, selectedVersion !== document.version ? selectedVersion : undefined);
    } catch (err) {
      console.error('Download failed:', err);
    }
  }, [document.id, document.version, selectedVersion, downloadDocument]);

  // Handle zoom
  const handleZoomIn = useCallback(() => {
    setZoom((prev) => Math.min(prev + 0.25, 3));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoom((prev) => Math.max(prev - 0.25, 0.25));
  }, []);

  // Handle rotation
  const handleRotate = useCallback(() => {
    setRotation((prev) => (prev + 90) % 360);
  }, []);

  // Handle fullscreen
  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((prev) => !prev);
  }, []);

  // Handle version change
  const handleVersionChange = useCallback((version: number) => {
    setSelectedVersion(version);
    setShowVersions(false);
  }, []);

  // Handle keyboard shortcuts
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'Escape':
          if (isFullscreen) {
            setIsFullscreen(false);
          } else {
            onClose();
          }
          break;
        case '+':
        case '=':
          handleZoomIn();
          break;
        case '-':
          handleZoomOut();
          break;
        case 'r':
          if (!e.ctrlKey && !e.metaKey) {
            handleRotate();
          }
          break;
        case 'f':
          if (!e.ctrlKey && !e.metaKey) {
            toggleFullscreen();
          }
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isFullscreen, onClose, handleZoomIn, handleZoomOut, handleRotate, toggleFullscreen]);

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          className={`relative flex flex-col bg-white dark:bg-gray-900 rounded-xl shadow-2xl overflow-hidden ${
            isFullscreen ? 'w-full h-full rounded-none' : 'w-[90vw] h-[90vh] max-w-6xl'
          }`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
            <div className="flex items-center gap-3">
              <FileText className="w-5 h-5 text-gray-500" />
              <div>
                <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate max-w-md">
                  {document.title}
                </h3>
                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span>{t(`document.categories.${document.category}`)}</span>
                  <span>-</span>
                  <span>{documentAPI.formatFileSize(document.file_size_bytes)}</span>
                  {selectedVersion !== document.version && (
                    <>
                      <span>-</span>
                      <span className="text-blue-600">v{selectedVersion}</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Version selector */}
              {document.version > 1 && (
                <div className="relative">
                  <button
                    onClick={() => setShowVersions(!showVersions)}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                  >
                    <History className="w-4 h-4" />
                    v{selectedVersion}
                  </button>

                  {showVersions && versions && (
                    <div className="absolute right-0 top-full mt-1 w-64 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 z-10 max-h-64 overflow-y-auto">
                      {versions.map((version) => (
                        <button
                          key={version.id}
                          onClick={() => handleVersionChange(version.version)}
                          className={`w-full flex items-center justify-between px-4 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 ${
                            selectedVersion === version.version
                              ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600'
                              : 'text-gray-700 dark:text-gray-300'
                          }`}
                        >
                          <span>v{version.version}</span>
                          <span className="text-xs text-gray-400">
                            {new Date(version.created_at).toLocaleDateString()}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Zoom controls (for images) */}
              {isImage && previewUrl && (
                <>
                  <button
                    onClick={handleZoomOut}
                    disabled={zoom <= 0.25}
                    className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50"
                    title={t('document.viewer.zoomOut')}
                  >
                    <ZoomOut className="w-4 h-4" />
                  </button>
                  <span className="text-sm text-gray-500 min-w-[3rem] text-center">
                    {Math.round(zoom * 100)}%
                  </span>
                  <button
                    onClick={handleZoomIn}
                    disabled={zoom >= 3}
                    className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50"
                    title={t('document.viewer.zoomIn')}
                  >
                    <ZoomIn className="w-4 h-4" />
                  </button>
                  <button
                    onClick={handleRotate}
                    className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                    title={t('document.viewer.rotate')}
                  >
                    <RotateCw className="w-4 h-4" />
                  </button>
                </>
              )}

              {/* Fullscreen toggle */}
              <button
                onClick={toggleFullscreen}
                className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                title={isFullscreen ? t('document.viewer.exitFullscreen') : t('document.viewer.fullscreen')}
              >
                {isFullscreen ? (
                  <Minimize2 className="w-4 h-4" />
                ) : (
                  <Maximize2 className="w-4 h-4" />
                )}
              </button>

              {/* Download */}
              <button
                onClick={handleDownload}
                disabled={isDownloading}
                className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                {isDownloading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Download className="w-4 h-4" />
                )}
                {t('common.download')}
              </button>

              {/* Open in new tab */}
              {previewUrl && (
                <a
                  href={previewUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                  title={t('document.viewer.openNewTab')}
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              )}

              {/* Close */}
              <button
                onClick={onClose}
                className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-auto bg-gray-100 dark:bg-gray-950 flex items-center justify-center">
            {isLoading && (
              <div className="flex flex-col items-center gap-4 text-gray-500">
                <Loader2 className="w-8 h-8 animate-spin" />
                <span>{t('common.loading')}</span>
              </div>
            )}

            {error && (
              <div className="flex flex-col items-center gap-4 text-red-500">
                <File className="w-12 h-12" />
                <span>{error}</span>
                <button
                  onClick={loadPreview}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  {t('common.retry')}
                </button>
              </div>
            )}

            {!isLoading && !error && previewUrl && (
              <>
                {/* PDF Preview */}
                {isPDF && (
                  <iframe
                    src={`${previewUrl}#toolbar=0`}
                    className="w-full h-full border-0"
                    title={document.title}
                  />
                )}

                {/* Image Preview */}
                {isImage && (
                  <div className="p-4 flex items-center justify-center min-h-full">
                    <img
                      src={previewUrl}
                      alt={document.title}
                      className="max-w-full max-h-full object-contain shadow-lg transition-transform duration-200"
                      style={{
                        transform: `scale(${zoom}) rotate(${rotation}deg)`,
                      }}
                      draggable={false}
                    />
                  </div>
                )}
              </>
            )}

            {/* Non-previewable files */}
            {!isPreviewable && !isLoading && (
              <div className="flex flex-col items-center gap-4 text-gray-500 p-8 text-center">
                <File className="w-16 h-16 text-gray-300" />
                <div>
                  <h4 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                    {t('document.viewer.noPreview')}
                  </h4>
                  <p className="text-sm text-gray-500 mt-1">
                    {t('document.viewer.noPreviewDescription', {
                      type: documentAPI.getExtensionFromContentType(document.content_type).toUpperCase(),
                    })}
                  </p>
                </div>
                <button
                  onClick={handleDownload}
                  disabled={isDownloading}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50"
                >
                  {isDownloading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4" />
                  )}
                  {t('document.viewer.downloadToView')}
                </button>
              </div>
            )}
          </div>

          {/* Footer with keyboard shortcuts */}
          <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-xs text-gray-500 dark:text-gray-400">
            <div className="flex items-center justify-center gap-4">
              <span>
                <kbd className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 rounded">Esc</kbd>{' '}
                {t('common.close')}
              </span>
              {isImage && (
                <>
                  <span>
                    <kbd className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 rounded">+</kbd>/
                    <kbd className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 rounded">-</kbd>{' '}
                    {t('document.viewer.zoom')}
                  </span>
                  <span>
                    <kbd className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 rounded">R</kbd>{' '}
                    {t('document.viewer.rotate')}
                  </span>
                </>
              )}
              <span>
                <kbd className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 rounded">F</kbd>{' '}
                {t('document.viewer.fullscreen')}
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default DocumentViewer;
