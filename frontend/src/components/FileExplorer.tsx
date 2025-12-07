import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { Folder, File, RefreshCw, ChevronRight, HardDrive, Cloud } from 'lucide-react';
import { driveAPI } from '@/services/api';
import type { DriveFileInfo } from '@/types';

interface FileExplorerProps {
  onFileSelect: (file: DriveFileInfo) => void;
}

export default function FileExplorer({ onFileSelect }: FileExplorerProps) {
  const { t } = useTranslation();
  const [currentFolderId, setCurrentFolderId] = useState<string | undefined>();
  const [folderPath, setFolderPath] = useState<DriveFileInfo[]>([]);

  const { refetch: authenticate, isLoading: authLoading } = useQuery({
    queryKey: ['drive-auth'],
    queryFn: async () => {
      const result = await driveAPI.authenticate();
      refetchFolders();
      refetchFiles();
      return result;
    },
    enabled: false,
  });

  const { data: folders, isLoading: foldersLoading, refetch: refetchFolders } = useQuery({
    queryKey: ['folders', currentFolderId],
    queryFn: () => driveAPI.listFolders(currentFolderId),
  });

  const { data: files, isLoading: filesLoading, refetch: refetchFiles } = useQuery({
    queryKey: ['files', currentFolderId],
    queryFn: () => driveAPI.listFiles(currentFolderId),
  });

  const handleFolderClick = (folder: DriveFileInfo) => {
    setCurrentFolderId(folder.id);
    setFolderPath([...folderPath, folder]);
  };

  const handleBreadcrumbClick = (index: number) => {
    if (index === -1) {
      setCurrentFolderId(undefined);
      setFolderPath([]);
    } else {
      const folder = folderPath[index];
      setCurrentFolderId(folder.id);
      setFolderPath(folderPath.slice(0, index + 1));
    }
  };

  const handleRefresh = () => {
    refetchFolders();
    refetchFiles();
  };

  const isLoading = foldersLoading || filesLoading || authLoading;

  return (
    <div className="h-full flex flex-col bg-white/50 dark:bg-gray-900/50 backdrop-blur-xl border-r border-gray-200/50 dark:border-gray-700/50">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="p-6 border-b border-gray-200/50 dark:border-gray-700/50"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-primary-500 to-accent-500 rounded-lg shadow-lg">
              <Cloud className="w-5 h-5 text-white" />
            </div>
            <h2 className="text-lg font-bold bg-gradient-to-r from-primary-600 to-accent-600 dark:from-primary-400 dark:to-accent-400 bg-clip-text text-transparent">
              {t('fileExplorer.googleDrive')}
            </h2>
          </div>
          <motion.button
            onClick={handleRefresh}
            disabled={isLoading}
            whileHover={{ scale: 1.1, rotate: 180 }}
            whileTap={{ scale: 0.9 }}
            className="p-2 bg-white/60 dark:bg-gray-800/60 hover:bg-white/80 dark:hover:bg-gray-800/80 rounded-lg border border-gray-200/50 dark:border-gray-700/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`w-4 h-4 text-gray-700 dark:text-gray-300 ${isLoading ? 'animate-spin' : ''}`} />
          </motion.button>
        </div>

        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 overflow-x-auto pb-1">
          <motion.button
            onClick={() => handleBreadcrumbClick(-1)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="flex items-center gap-1.5 px-2.5 py-1 hover:bg-white/60 dark:hover:bg-gray-800/60 rounded-lg transition-all whitespace-nowrap font-medium"
          >
            <HardDrive className="w-3.5 h-3.5" />
            {t('fileExplorer.root')}
          </motion.button>
          {folderPath.map((folder, index) => (
            <motion.div
              key={folder.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-center gap-1.5"
            >
              <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
              <button
                onClick={() => handleBreadcrumbClick(index)}
                className="px-2.5 py-1 hover:bg-white/60 dark:hover:bg-gray-800/60 rounded-lg transition-all whitespace-nowrap font-medium hover:text-primary-600 dark:hover:text-primary-400"
              >
                {folder.name}
              </button>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center h-48 gap-4">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              className="w-12 h-12 border-4 border-primary-200 dark:border-primary-800 border-t-primary-600 dark:border-t-primary-400 rounded-full"
            />
            <p className="text-sm text-gray-600 dark:text-gray-400">{t('fileExplorer.loading')}</p>
          </div>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div
              key={currentFolderId || 'root'}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="space-y-2"
            >
              {/* Folders */}
              {folders?.map((folder, index) => (
                <motion.button
                  key={folder.id}
                  onClick={() => handleFolderClick(folder)}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                  whileHover={{ scale: 1.02, x: 4 }}
                  whileTap={{ scale: 0.98 }}
                  className="w-full flex items-center gap-3 p-3 rounded-xl bg-white/60 dark:bg-gray-800/60 hover:bg-gradient-to-r hover:from-primary-50 hover:to-accent-50 dark:hover:from-primary-900/30 dark:hover:to-accent-900/30 border border-gray-200/50 dark:border-gray-700/50 hover:border-primary-200 dark:hover:border-primary-700 transition-all shadow-sm hover:shadow-lg"
                >
                  <Folder className="w-5 h-5 text-warning-500 flex-shrink-0" />
                  <span className="text-sm text-gray-900 dark:text-white truncate font-medium">{folder.name}</span>
                </motion.button>
              ))}

              {/* Files */}
              {files?.map((file, index) => (
                <motion.button
                  key={file.id}
                  onClick={() => onFileSelect(file)}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: (folders?.length || 0) * 0.05 + index * 0.05 }}
                  whileHover={{ scale: 1.02, x: 4 }}
                  whileTap={{ scale: 0.98 }}
                  className="w-full flex items-center gap-3 p-3 rounded-xl bg-white/60 dark:bg-gray-800/60 hover:bg-gradient-to-r hover:from-accent-50 hover:to-primary-50 dark:hover:from-accent-900/30 dark:hover:to-primary-900/30 border border-gray-200/50 dark:border-gray-700/50 hover:border-accent-200 dark:hover:border-accent-700 transition-all group shadow-sm hover:shadow-lg"
                >
                  <File className="w-5 h-5 text-primary-500 flex-shrink-0" />
                  <div className="flex-1 min-w-0 text-left">
                    <div className="text-sm text-gray-900 dark:text-white truncate font-medium group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                      {file.name}
                    </div>
                    {file.size && (
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {formatFileSize(file.size)}
                      </div>
                    )}
                  </div>
                </motion.button>
              ))}

              {!folders?.length && !files?.length && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-center py-12"
                >
                  <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center">
                    <Folder className="w-8 h-8 text-gray-400" />
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">{t('fileExplorer.noFiles')}</p>
                </motion.div>
              )}
            </motion.div>
          </AnimatePresence>
        )}
      </div>

      {/* Connect Button */}
      <div className="p-4 border-t border-gray-200/50 dark:border-gray-700/50">
        <motion.button
          onClick={() => authenticate()}
          disabled={authLoading}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="w-full px-4 py-3 bg-gradient-to-r from-primary-500 to-accent-500 hover:from-primary-600 hover:to-accent-600 text-white font-semibold rounded-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-primary-500/30"
        >
          {authLoading ? t('fileExplorer.connecting') : t('fileExplorer.connectToDrive')}
        </motion.button>
      </div>
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}
