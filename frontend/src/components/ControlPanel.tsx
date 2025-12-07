import { useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { Box, Layers, Settings, SunMedium, Maximize2 } from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { type ImageOrientation } from '@/types';

export default function ControlPanel() {
  const { t } = useTranslation();
  const {
    viewMode,
    setViewMode,
    orientation,
    setOrientation,
    windowCenter,
    windowWidth,
    setWindowLevel,
    currentSeries,
  } = useViewerStore();

  const [localWindowCenter, setLocalWindowCenter] = useState(windowCenter);
  const [localWindowWidth, setLocalWindowWidth] = useState(windowWidth);

  const handleViewModeChange = (mode: '2d' | '3d') => {
    setViewMode(mode);
  };

  const handleOrientationChange = (orient: ImageOrientation) => {
    setOrientation(orient);
  };

  const handleWindowLevelApply = () => {
    setWindowLevel(localWindowCenter, localWindowWidth);
  };

  const presets = [
    { name: 'Brain', center: 40, width: 80, icon: '🧠' },
    { name: 'Abdomen', center: 50, width: 350, icon: '🫁' },
    { name: 'Bone', center: 400, width: 1500, icon: '🦴' },
  ];

  return (
    <div className="h-full flex flex-col bg-white/50 dark:bg-gray-900/50 backdrop-blur-xl border-l border-gray-200/50 dark:border-gray-700/50">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="p-6 border-b border-gray-200/50 dark:border-gray-700/50"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gradient-to-br from-primary-500 to-accent-500 rounded-lg shadow-lg">
            <Settings className="w-5 h-5 text-white" />
          </div>
          <h2 className="text-lg font-bold bg-gradient-to-r from-primary-600 to-accent-600 dark:from-primary-400 dark:to-accent-400 bg-clip-text text-transparent">
            {t('viewer.controls')}
          </h2>
        </div>
      </motion.div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* View Mode */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
        >
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
            <Box className="w-4 h-4 text-primary-500" />
            {t('viewer.viewMode')}
          </label>
          <div className="grid grid-cols-2 gap-3">
            {['2d', '3d'].map((mode) => (
              <motion.button
                key={mode}
                onClick={() => handleViewModeChange(mode as '2d' | '3d')}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className={`px-4 py-3 rounded-xl font-semibold transition-all duration-200 ${
                  viewMode === mode
                    ? 'bg-gradient-to-r from-primary-500 to-accent-500 text-white shadow-lg shadow-primary-500/30'
                    : 'bg-white/60 dark:bg-gray-800/60 text-gray-700 dark:text-gray-300 hover:bg-white/80 dark:hover:bg-gray-800/80 border border-gray-200/50 dark:border-gray-700/50'
                }`}
              >
                {t(`viewer.${mode}View`).toUpperCase()}
              </motion.button>
            ))}
          </div>
        </motion.div>

        {/* Orientation (for 3D) */}
        {viewMode === '3d' && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
              <Layers className="w-4 h-4 text-accent-500" />
              {t('viewer.orientation')}
            </label>
            <div className="space-y-2">
              {(['axial', 'sagittal', 'coronal'] as ImageOrientation[]).map((orient) => (
                <motion.button
                  key={orient}
                  onClick={() => handleOrientationChange(orient)}
                  whileHover={{ scale: 1.02, x: 4 }}
                  whileTap={{ scale: 0.98 }}
                  className={`w-full px-4 py-3 rounded-xl font-semibold transition-all duration-200 text-left capitalize ${
                    orientation === orient
                      ? 'bg-gradient-to-r from-accent-500 to-primary-500 text-white shadow-lg shadow-accent-500/30'
                      : 'bg-white/60 dark:bg-gray-800/60 text-gray-700 dark:text-gray-300 hover:bg-white/80 dark:hover:bg-gray-800/80 border border-gray-200/50 dark:border-gray-700/50'
                  }`}
                >
                  {t(`viewer.${orient}`)}
                </motion.button>
              ))}
            </div>
          </motion.div>
        )}

        {/* Window/Level (for 2D) */}
        {viewMode === '2d' && currentSeries && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
              <SunMedium className="w-4 h-4 text-warning-500" />
              {t('viewer.windowLevel')}
            </label>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                  {t('viewer.windowCenter')}
                </label>
                <input
                  type="number"
                  value={localWindowCenter}
                  onChange={(e) => setLocalWindowCenter(parseFloat(e.target.value))}
                  className="w-full px-4 py-2.5 bg-white/80 dark:bg-gray-800/80 text-gray-900 dark:text-white rounded-xl border border-gray-200/50 dark:border-gray-700/50 focus:border-primary-500 dark:focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 outline-none transition-all"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                  {t('viewer.windowWidth')}
                </label>
                <input
                  type="number"
                  value={localWindowWidth}
                  onChange={(e) => setLocalWindowWidth(parseFloat(e.target.value))}
                  min="1"
                  className="w-full px-4 py-2.5 bg-white/80 dark:bg-gray-800/80 text-gray-900 dark:text-white rounded-xl border border-gray-200/50 dark:border-gray-700/50 focus:border-accent-500 dark:focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 outline-none transition-all"
                />
              </div>
              <motion.button
                onClick={handleWindowLevelApply}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="w-full px-4 py-3 bg-gradient-to-r from-primary-500 to-accent-500 hover:from-primary-600 hover:to-accent-600 text-white font-semibold rounded-xl transition-all duration-200 shadow-lg shadow-primary-500/30"
              >
                {t('viewer.apply')}
              </motion.button>

              {/* Presets */}
              <div className="pt-4 border-t border-gray-200/50 dark:border-gray-700/50">
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-3 flex items-center gap-2">
                  <Maximize2 className="w-3.5 h-3.5" />
                  {t('viewer.presets')}
                </label>
                <div className="space-y-2">
                  {presets.map((preset) => (
                    <motion.button
                      key={preset.name}
                      onClick={() => {
                        setLocalWindowCenter(preset.center);
                        setLocalWindowWidth(preset.width);
                        setWindowLevel(preset.center, preset.width);
                      }}
                      whileHover={{ scale: 1.02, x: 4 }}
                      whileTap={{ scale: 0.98 }}
                      className="w-full px-4 py-2.5 bg-white/60 dark:bg-gray-800/60 hover:bg-gradient-to-r hover:from-primary-50 hover:to-accent-50 dark:hover:from-primary-900/30 dark:hover:to-accent-900/30 text-gray-700 dark:text-gray-300 rounded-lg transition-all duration-200 text-left flex items-center gap-3 border border-gray-200/50 dark:border-gray-700/50 hover:border-primary-200 dark:hover:border-primary-700"
                    >
                      <span className="text-xl">{preset.icon}</span>
                      <span className="font-medium">{t(`viewer.${preset.name.toLowerCase()}`)}</span>
                    </motion.button>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {/* Image Info */}
        {currentSeries && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="pt-6 border-t border-gray-200/50 dark:border-gray-700/50"
          >
            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              {t('viewer.imageInformation')}
            </label>
            <div className="space-y-3 text-xs">
              <InfoRow label={t('viewer.format')} value={currentSeries.format.toUpperCase()} />
              <InfoRow
                label={t('viewer.dimensions')}
                value={`${currentSeries.metadata.rows} × ${currentSeries.metadata.columns}`}
              />
              <InfoRow
                label={t('viewer.slices')}
                value={currentSeries.metadata.slices?.toString() || 'N/A'}
              />
              <InfoRow
                label={t('viewer.modality')}
                value={currentSeries.metadata.modality || 'N/A'}
              />
              {currentSeries.metadata.pixel_spacing && (
                <InfoRow
                  label={t('viewer.pixelSpacing')}
                  value={`${currentSeries.metadata.pixel_spacing[0].toFixed(2)} × ${currentSeries.metadata.pixel_spacing[1].toFixed(2)} mm`}
                />
              )}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <motion.div
      whileHover={{ x: 4 }}
      className="flex justify-between items-center p-3 bg-white/40 dark:bg-gray-800/40 rounded-lg border border-gray-200/30 dark:border-gray-700/30"
    >
      <span className="text-gray-600 dark:text-gray-400 font-medium">{label}:</span>
      <span className="text-gray-900 dark:text-white font-semibold">{value}</span>
    </motion.div>
  );
}
