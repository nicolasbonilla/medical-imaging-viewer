import { useState, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast, Toaster } from 'sonner';
import { motion } from 'framer-motion';
import FileExplorer from './components/FileExplorer';
import ImageViewer2D from './components/ImageViewer2D';
import ImageViewer3D from './components/ImageViewer3D';
import ControlPanel from './components/ControlPanel';
import ViewerControls from './components/ViewerControls';
import LanguageSelector from './components/LanguageSelector';
import ThemeToggle from './components/ThemeToggle';
import { imagingAPI } from './services/api';
import { useViewerStore } from './store/useViewerStore';
import { useViewerControls } from './hooks/useViewerControls';
import { useSegmentationControls } from './hooks/useSegmentationControls';
import { useSegmentationManager } from './hooks/useSegmentationManager';
import type { DriveFileInfo } from './types';
import { Activity, LogOut, Sparkles } from 'lucide-react';
import { useAuth } from './contexts/AuthContext';
import { useTheme } from './contexts/ThemeContext';

function ViewerApp() {
  console.log('🔥 VIEWER APP COMPONENT RENDER');
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { theme } = useTheme();
  const viewMode = useViewerStore((state) => state.viewMode);
  const setCurrentSeries = useViewerStore((state) => state.setCurrentSeries);
  const setIsLoading = useViewerStore((state) => state.setIsLoading);
  const currentSeries = useViewerStore((state) => state.currentSeries);
  const [selectedFile, setSelectedFile] = useState<DriveFileInfo | null>(null);
  const viewerControls = useViewerControls();
  const segmentationControls = useSegmentationControls();
  const createSegmentationRef = useRef<(() => void) | null>(null);

  // Segmentation manager hook
  const segmentationManager = useSegmentationManager({
    fileId: selectedFile?.id,
    enabled: viewerControls.segmentationMode,
  });

  const handleCreateSegmentation = () => {
    if (createSegmentationRef.current) {
      createSegmentationRef.current();
    }
  };

  const handleLoadSegmentation = async (segmentationId: string) => {
    try {
      const loadedSegmentation = await segmentationManager.loadSegmentation(segmentationId);
      // Sync with segmentation controls
      if (loadedSegmentation) {
        segmentationControls.setCurrentSegmentation(loadedSegmentation);
      }
      toast.success(t('viewer.segmentationLoaded'));
    } catch (error) {
      console.error('Error loading segmentation:', error);
      toast.error(t('viewer.segmentationFailed'));
    }
  };

  const handleDeleteSegmentation = async (segmentationId: string) => {
    try {
      await segmentationManager.deleteSegmentation(segmentationId);
      toast.success(t('viewer.segmentationDeleted'));
    } catch (error) {
      console.error('Error deleting segmentation:', error);
      toast.error(t('errors.generic'));
    }
  };

  const handleCloseSegmentation = () => {
    segmentationManager.clearSegmentation();
    segmentationControls.setCurrentSegmentation(null);
  };

  // Load image when file is selected
  const { refetch: loadImage } = useQuery({
    queryKey: ['image', selectedFile?.id],
    queryFn: async () => {
      if (!selectedFile) return null;

      setIsLoading(true);
      toast.loading(t('viewer.loadingImage'), { id: 'loading-image' });

      try {
        const result = await imagingAPI.processImage(selectedFile.id, 0, 500);
        // Add the file_id to the result so 3D viewer can use it
        const resultWithFileId = { ...result, file_id: selectedFile.id };
        setCurrentSeries(resultWithFileId);
        toast.success(t('viewer.imageLoadSuccess'), { id: 'loading-image' });
        return resultWithFileId;
      } catch (error) {
        toast.error(t('viewer.imageLoadFailed'), { id: 'loading-image' });
        console.error(error);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    enabled: false,
  });

  const handleFileSelect = (file: DriveFileInfo) => {
    setSelectedFile(file);
    loadImage();
  };

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
      {/* Animated Background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-1/2 -right-1/2 w-full h-full bg-gradient-to-br from-primary-500/5 to-accent-500/5 dark:from-primary-500/10 dark:to-accent-500/10 rounded-full blur-3xl animate-pulse-slow" />
        <div className="absolute -bottom-1/2 -left-1/2 w-full h-full bg-gradient-to-tr from-accent-500/5 to-primary-500/5 dark:from-accent-500/10 dark:to-primary-500/10 rounded-full blur-3xl animate-pulse-slow" style={{ animationDelay: '1s' }} />
      </div>

      {/* Header */}
      <motion.header
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5, type: 'spring', stiffness: 100 }}
        className="relative z-10 backdrop-blur-xl bg-white/70 dark:bg-gray-900/70 border-b border-gray-200/50 dark:border-gray-700/50 shadow-lg shadow-gray-200/50 dark:shadow-gray-900/50"
      >
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            {/* Logo & Title */}
            <div className="flex items-center gap-4">
              <motion.div
                whileHover={{ scale: 1.05, rotate: 5 }}
                whileTap={{ scale: 0.95 }}
                className="relative"
              >
                <div className="absolute inset-0 bg-gradient-to-br from-primary-500 to-accent-500 rounded-2xl blur-lg opacity-60 dark:opacity-40 animate-pulse-slow" />
                <div className="relative bg-gradient-to-br from-primary-500 to-accent-500 p-3 rounded-2xl shadow-lg">
                  <Activity className="w-7 h-7 text-white" />
                </div>
              </motion.div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-primary-600 to-accent-600 dark:from-primary-400 dark:to-accent-400 bg-clip-text text-transparent flex items-center gap-2">
                  {t('viewer.title')}
                  <Sparkles className="w-5 h-5 text-accent-500 dark:text-accent-400 animate-pulse" />
                </h1>
                <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">
                  {t('viewer.subtitle')}
                </p>
              </div>
            </div>

            {/* Right Side Controls */}
            <div className="flex items-center gap-3">
              {/* Image Loaded Badge */}
              {currentSeries && (
                <motion.span
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  className="px-4 py-2 bg-gradient-to-r from-success-500/20 to-success-600/20 dark:from-success-500/30 dark:to-success-600/30 backdrop-blur-md border border-success-500/30 dark:border-success-500/20 text-success-700 dark:text-success-400 rounded-xl text-xs font-semibold shadow-lg shadow-success-500/10 flex items-center gap-2"
                >
                  <span className="w-2 h-2 bg-success-500 rounded-full animate-pulse" />
                  {t('viewer.imageLoaded')}
                </motion.span>
              )}

              {/* User Info */}
              {user && (
                <motion.div
                  whileHover={{ scale: 1.05 }}
                  className="flex items-center gap-3 px-4 py-2 bg-white/60 dark:bg-gray-800/60 backdrop-blur-md border border-gray-200/50 dark:border-gray-700/50 rounded-xl shadow-lg"
                >
                  <div className="w-9 h-9 bg-gradient-to-br from-primary-500 to-accent-500 rounded-lg flex items-center justify-center text-white font-bold text-sm shadow-lg">
                    {user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-gray-900 dark:text-white font-semibold">{user.full_name}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">{user.role.toLowerCase()}</p>
                  </div>
                </motion.div>
              )}

              {/* Theme Toggle */}
              <ThemeToggle variant="minimal" />

              {/* Language Selector */}
              <LanguageSelector variant="minimal" />

              {/* Logout Button */}
              <motion.button
                onClick={logout}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="p-3 bg-white/60 dark:bg-gray-800/60 hover:bg-error-50 dark:hover:bg-error-900/30 backdrop-blur-md border border-gray-200/50 dark:border-gray-700/50 hover:border-error-300 dark:hover:border-error-700 rounded-xl transition-all duration-200 group shadow-lg"
                title={t('auth.logout')}
              >
                <LogOut className="w-5 h-5 text-gray-600 dark:text-gray-400 group-hover:text-error-600 dark:group-hover:text-error-400 transition-colors" />
              </motion.button>
            </div>
          </div>
        </div>
      </motion.header>

      {/* Main Content */}
      <div className="relative z-0 flex-1 flex overflow-hidden">
        {/* File Explorer & Controls - Left Sidebar */}
        <motion.div
          initial={{ x: -300, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="w-80 flex-shrink-0 flex flex-col"
        >
          <div className="flex-1 overflow-hidden">
            <FileExplorer onFileSelect={handleFileSelect} />
          </div>
          {currentSeries && viewMode === '2d' && (
            <motion.div
              initial={{ y: 100, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.3 }}
              className="p-4 border-t border-gray-200 dark:border-gray-700 bg-white/50 dark:bg-gray-900/50 backdrop-blur-xl overflow-y-auto max-h-[70vh]"
            >
              <ViewerControls
                {...viewerControls}
                {...segmentationControls}
                onCreateSegmentation={handleCreateSegmentation}
                segmentations={segmentationManager.segmentations}
                isLoadingList={segmentationManager.isLoadingList}
                isLoadingSegmentation={segmentationManager.isLoading}
                isDeletingSegmentation={segmentationManager.isDeleting}
                onLoadSegmentation={handleLoadSegmentation}
                onDeleteSegmentation={handleDeleteSegmentation}
                onCloseSegmentation={handleCloseSegmentation}
              />
            </motion.div>
          )}
        </motion.div>

        {/* Viewer - Center */}
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="flex-1 p-4"
        >
          <div className="h-full bg-white/60 dark:bg-gray-900/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl shadow-2xl overflow-hidden">
            {viewMode === '2d' ? (
              <ImageViewer2D
                viewerControls={viewerControls}
                segmentationControls={segmentationControls}
                createSegmentationRef={createSegmentationRef}
              />
            ) : (
              <ImageViewer3D />
            )}
          </div>
        </motion.div>

        {/* Control Panel - Right Sidebar */}
        <motion.div
          initial={{ x: 300, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="w-80 flex-shrink-0"
        >
          <ControlPanel />
        </motion.div>
      </div>

      {/* Toast Notifications */}
      <Toaster
        position="top-right"
        theme={theme === 'dark' ? 'dark' : 'light'}
        richColors
        closeButton
        expand={false}
      />
    </div>
  );
}

export default ViewerApp;
