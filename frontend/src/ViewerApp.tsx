import { useState, useRef, useEffect, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { toast, Toaster } from 'sonner';
import { motion } from 'framer-motion';
import ImageViewer2D from './components/ImageViewer2D';
import ImageViewer3D from './components/ImageViewer3D';
import ControlPanel from './components/ControlPanel';
import ViewerControls from './components/ViewerControls';
import LanguageSelector from './components/LanguageSelector';
import ThemeToggle from './components/ThemeToggle';
import { imagingAPI } from './services/api';
import { studyAPI } from './services/studyApi';
import { useViewerStore } from './store/useViewerStore';
import { useViewerControls } from './hooks/useViewerControls';
import { useSegmentationControls } from './hooks/useSegmentationControls';
import type { ImagingStudy, ImagingSeries, ImagingInstance } from './types';
import { LogOut, Sparkles, ArrowLeft, Brain, FileImage, AlertCircle, Loader2, Puzzle, Upload, Eye, CheckCircle, Clock, Plus } from 'lucide-react';
import { useAuth } from './contexts/AuthContext';
import { useTheme } from './contexts/ThemeContext';
import { useSegmentationsByStudy } from './hooks/useSegmentations';
import { usePatient } from './hooks/usePatients';
import type { SegmentationSummary } from './types';

interface StudyInfo {
  study: ImagingStudy;
  series: ImagingSeries[];
  instances: ImagingInstance[];
}

function ViewerApp() {
  console.log('🔥 VIEWER APP v3 - FIXED PATIENT INFO - BUILD 2026-01-18-1450');
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { theme } = useTheme();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const studyId = searchParams.get('studyId');

  const viewMode = useViewerStore((state) => state.viewMode);
  const setCurrentSeries = useViewerStore((state) => state.setCurrentSeries);
  const setIsLoading = useViewerStore((state) => state.setIsLoading);
  const currentSeries = useViewerStore((state) => state.currentSeries);
  const setHierarchicalContext = useViewerStore((state) => state.setHierarchicalContext);

  const [selectedInstanceId, setSelectedInstanceId] = useState<string | null>(null);
  const [studyInfo, setStudyInfo] = useState<StudyInfo | null>(null);

  const viewerControls = useViewerControls();
  const segmentationControls = useSegmentationControls();
  const createSegmentationRef = useRef<(() => void) | null>(null);
  const segmentationUploadRef = useRef<HTMLInputElement>(null);

  // Fetch segmentations for this study
  const { data: segmentationsData, isLoading: isLoadingSegmentations } = useSegmentationsByStudy(
    studyInfo?.study.patient_id,
    studyId ?? undefined
  );

  const segmentations = segmentationsData?.items ?? [];

  // Fetch patient info to display name in viewer
  const { data: patientData, isLoading: isLoadingPatient, error: patientError } = usePatient(studyInfo?.study.patient_id);

  // Debug patient data
  console.log('👤 PATIENT DATA DEBUG:', {
    patientId: studyInfo?.study.patient_id,
    patientData: patientData,
    isLoadingPatient,
    patientError,
    fullName: patientData?.full_name,
  });

  // Load study data when studyId is present
  const { data: loadedStudyInfo, isLoading: isLoadingStudy, error: studyError } = useQuery({
    queryKey: ['study-viewer', studyId],
    queryFn: async (): Promise<StudyInfo | null> => {
      if (!studyId) return null;

      // Get study details
      const study = await studyAPI.getById(studyId);

      // Get series for this study
      const series = await studyAPI.listSeries(studyId);

      // Get instances for the first series (or all series)
      let instances: ImagingInstance[] = [];
      if (series.length > 0) {
        // Get instances from the first series
        instances = await studyAPI.listInstances(series[0].id);
      }

      return { study, series, instances };
    },
    enabled: !!studyId,
  });

  // Update state when study data is loaded
  useEffect(() => {
    if (loadedStudyInfo) {
      setStudyInfo(loadedStudyInfo);

      // Set hierarchical context for segmentation
      const patientId = loadedStudyInfo.study.patient_id;
      const seriesId = loadedStudyInfo.series.length > 0 ? loadedStudyInfo.series[0].id : null;
      setHierarchicalContext(patientId, studyId, seriesId);

      // Auto-select first instance if available
      if (loadedStudyInfo.instances.length > 0 && !selectedInstanceId) {
        const firstInstance = loadedStudyInfo.instances[0];
        setSelectedInstanceId(firstInstance.id);
      }
    }
  }, [loadedStudyInfo, selectedInstanceId, studyId, setHierarchicalContext]);

  // Load image when instance is selected
  const { refetch: loadImage, isLoading: isLoadingImage } = useQuery({
    queryKey: ['image', selectedInstanceId],
    queryFn: async () => {
      if (!selectedInstanceId || !studyInfo) return null;

      // Find the selected instance to get its gcs_object_name
      const selectedInstance = studyInfo.instances.find(
        (inst) => inst.id === selectedInstanceId
      );
      if (!selectedInstance) {
        console.error('Instance not found:', selectedInstanceId);
        return null;
      }

      setIsLoading(true);
      toast.loading(t('viewer.loadingImage'), { id: 'loading-image' });

      try {
        // Use the GCS object path to load the image
        const result = await imagingAPI.processImage(selectedInstance.gcs_object_name, 0, 500);
        // Add the file_id to the result so 3D viewer can use it
        const resultWithFileId = { ...result, file_id: selectedInstance.gcs_object_name };
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

  // Load image when selectedInstanceId changes
  useEffect(() => {
    if (selectedInstanceId) {
      loadImage();
    }
  }, [selectedInstanceId, loadImage]);

  const handleBack = useCallback(() => {
    if (studyInfo?.study.patient_id) {
      navigate(`/app/patients/${studyInfo.study.patient_id}`);
    } else {
      navigate('/app');
    }
  }, [navigate, studyInfo]);

  const handleSelectInstance = (instanceId: string) => {
    setSelectedInstanceId(instanceId);
  };

  // Handle opening/loading an existing segmentation
  const handleOpenSegmentation = useCallback((segmentation: SegmentationSummary) => {
    // Activate segmentation mode and load this segmentation
    viewerControls.setSegmentationMode(true);
    toast.success(t('viewer.segmentationLoaded', `Segmentación "${segmentation.name}" cargada`));
  }, [viewerControls, t]);

  // Handle upload segmentation file
  const handleUploadSegmentation = useCallback(() => {
    segmentationUploadRef.current?.click();
  }, []);

  const handleSegmentationFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    toast.loading(t('viewer.uploadingSegmentation', 'Subiendo segmentación...'), { id: 'upload-seg' });

    // TODO: Implement actual upload logic
    // For now just show a message
    setTimeout(() => {
      toast.success(t('viewer.segmentationUploaded', 'Segmentación subida correctamente'), { id: 'upload-seg' });
    }, 1000);

    // Reset input
    if (segmentationUploadRef.current) {
      segmentationUploadRef.current.value = '';
    }
  }, [t]);

  // Handle create new segmentation (activates segmentation mode and creates segmentation)
  const handleCreateSegmentation = useCallback(() => {
    if (!currentSeries) {
      toast.error(t('viewer.noImageLoaded', 'Carga una imagen primero'));
      return;
    }
    // First enable segmentation mode
    viewerControls.setSegmentationMode(true);
    // Then trigger segmentation creation
    if (createSegmentationRef.current) {
      createSegmentationRef.current();
      toast.info(t('viewer.segmentationModeActivated', 'Modo de segmentación activado. Usa las herramientas de dibujo.'));
    } else {
      toast.error(t('viewer.segmentationCreationFailed', 'No se pudo crear la segmentación'));
    }
  }, [viewerControls, t, currentSeries]);

  // Get status badge color
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'approved':
        return {
          icon: <CheckCircle className="w-3 h-3" />,
          bg: 'bg-green-100 dark:bg-green-900/30',
          text: 'text-green-700 dark:text-green-400',
          label: t('segmentation.status.approved', 'Aprobada')
        };
      case 'in_progress':
        return {
          icon: <Clock className="w-3 h-3" />,
          bg: 'bg-yellow-100 dark:bg-yellow-900/30',
          text: 'text-yellow-700 dark:text-yellow-400',
          label: t('segmentation.status.inProgress', 'En progreso')
        };
      default:
        return {
          icon: <Clock className="w-3 h-3" />,
          bg: 'bg-gray-100 dark:bg-gray-700/50',
          text: 'text-gray-600 dark:text-gray-400',
          label: t('segmentation.status.draft', 'Borrador')
        };
    }
  };

  // No study ID provided
  if (!studyId) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
        <AlertCircle className="w-16 h-16 text-amber-500 mb-4" />
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
          {t('viewer.noStudySelected', 'No hay estudio seleccionado')}
        </h2>
        <p className="text-gray-500 dark:text-gray-400 mb-4 text-center max-w-md">
          {t('viewer.selectStudyDescription', 'Selecciona un paciente y sube un estudio de IRM para visualizarlo.')}
        </p>
        <button
          onClick={() => navigate('/app')}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600"
        >
          <ArrowLeft className="w-4 h-4" />
          {t('viewer.goToPatients', 'Ir a Pacientes')}
        </button>
      </div>
    );
  }

  // Loading study
  if (isLoadingStudy) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          className="w-12 h-12 border-4 border-primary-200 dark:border-primary-800 border-t-primary-600 dark:border-t-primary-400 rounded-full mb-4"
        />
        <p className="text-gray-600 dark:text-gray-400">{t('viewer.loadingStudy', 'Cargando estudio...')}</p>
      </div>
    );
  }

  // Study error or not found
  if (studyError || (!isLoadingStudy && !studyInfo)) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
        <AlertCircle className="w-16 h-16 text-red-500 mb-4" />
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
          {t('viewer.studyNotFound', 'Estudio no encontrado')}
        </h2>
        <p className="text-gray-500 dark:text-gray-400 mb-4">
          {t('viewer.studyNotFoundDescription', 'El estudio solicitado no existe o no tienes acceso.')}
        </p>
        <button
          onClick={() => navigate('/app')}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600"
        >
          <ArrowLeft className="w-4 h-4" />
          {t('common.goBack', 'Volver')}
        </button>
      </div>
    );
  }

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
            {/* Left: Back + Logo & Title */}
            <div className="flex items-center gap-4">
              <motion.button
                onClick={handleBack}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="p-2 bg-white/60 dark:bg-gray-800/60 hover:bg-white/80 dark:hover:bg-gray-800/80 rounded-xl border border-gray-200/50 dark:border-gray-700/50 transition-all"
              >
                <ArrowLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
              </motion.button>

              <motion.div
                whileHover={{ scale: 1.05, rotate: 5 }}
                whileTap={{ scale: 0.95 }}
                className="relative"
              >
                <div className="absolute inset-0 bg-gradient-to-br from-primary-500 to-accent-500 rounded-2xl blur-lg opacity-60 dark:opacity-40 animate-pulse-slow" />
                <div className="relative bg-gradient-to-br from-primary-500 to-accent-500 p-3 rounded-2xl shadow-lg">
                  <Brain className="w-7 h-7 text-white" />
                </div>
              </motion.div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-primary-600 to-accent-600 dark:from-primary-400 dark:to-accent-400 bg-clip-text text-transparent flex items-center gap-2">
                  {t('viewer.title')}
                  <Sparkles className="w-5 h-5 text-accent-500 dark:text-accent-400 animate-pulse" />
                </h1>
                <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">
                  {studyInfo?.study.study_description || studyInfo?.study.modality || t('viewer.subtitle')}
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
        {/* Study Info & Controls - Left Sidebar */}
        <motion.div
          initial={{ x: -300, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="w-72 flex-shrink-0 flex flex-col bg-white/50 dark:bg-gray-900/50 backdrop-blur-xl border-r border-gray-200/50 dark:border-gray-700/50 overflow-hidden"
        >
          {/* Study Info - Compact */}
          <div className="p-3 border-b border-gray-200/50 dark:border-gray-700/50">
            <div className="flex items-center gap-2 mb-2">
              <FileImage className="w-4 h-4 text-primary-500" />
              <span className="text-sm font-semibold text-gray-900 dark:text-white">
                {t('viewer.studyInfo', 'Estudio')}
              </span>
            </div>
            {studyInfo && (
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-500">{studyInfo.study.modality}</span>
                  <span className="text-gray-400">•</span>
                </div>
                <div>
                  <span className="text-gray-900 dark:text-white">{new Date(studyInfo.study.study_date).toLocaleDateString()}</span>
                </div>
                <div>
                  <span className="text-gray-500">{studyInfo.series.length} series</span>
                </div>
                <div>
                  <span className="text-gray-500">{studyInfo.instances.length} img</span>
                </div>
                {studyInfo.study.body_site && (
                  <div className="col-span-2">
                    <span className="text-gray-400">{studyInfo.study.body_site}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Segmentations Section - Compact */}
          <div className="p-3 border-b border-gray-200/50 dark:border-gray-700/50">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Puzzle className="w-4 h-4 text-purple-500" />
                <span className="text-sm font-semibold text-gray-900 dark:text-white">
                  {t('viewer.segmentations', 'Segmentaciones')}
                </span>
              </div>
              <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                segmentations.length > 0
                  ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
                  : 'bg-gray-100 text-gray-500 dark:bg-gray-700/50 dark:text-gray-400'
              }`}>
                {segmentations.length}
              </span>
            </div>

            {/* Action Buttons - Smaller */}
            <div className="flex gap-1.5 mb-2">
              <button
                onClick={handleCreateSegmentation}
                disabled={!currentSeries}
                className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-purple-500 hover:bg-purple-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white text-xs font-medium rounded-md transition-colors"
                title={t('viewer.createSegmentation', 'Crear nueva segmentación')}
              >
                <Plus className="w-3 h-3" />
                {t('viewer.create', 'Crear')}
              </button>
              <button
                onClick={handleUploadSegmentation}
                disabled={!studyInfo}
                className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white text-xs font-medium rounded-md transition-colors"
                title={t('viewer.uploadSegmentation', 'Subir segmentación')}
              >
                <Upload className="w-3 h-3" />
                {t('viewer.upload', 'Subir')}
              </button>
              <input
                ref={segmentationUploadRef}
                type="file"
                accept=".nii,.nii.gz,.nrrd,.seg.nrrd"
                className="hidden"
                onChange={handleSegmentationFileChange}
              />
            </div>

            {/* Segmentations List - Minimal when empty */}
            {isLoadingSegmentations ? (
              <div className="flex items-center justify-center py-2">
                <Loader2 className="w-4 h-4 text-purple-500 animate-spin" />
              </div>
            ) : segmentations.length === 0 ? (
              <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-1">
                {t('viewer.noSegmentations', 'Sin segmentaciones')}
              </p>
            ) : (
              <div className="space-y-1 max-h-24 overflow-y-auto">
                {segmentations.map((seg) => {
                  const statusBadge = getStatusBadge(seg.status);
                  return (
                    <button
                      key={seg.id}
                      onClick={() => handleOpenSegmentation(seg)}
                      className="w-full p-1.5 rounded-md bg-white/60 dark:bg-gray-800/60 hover:bg-white dark:hover:bg-gray-800 border border-gray-200/50 dark:border-gray-700/50 transition-all text-left group"
                    >
                      <div className="flex items-center gap-2">
                        <Puzzle className="w-3.5 h-3.5 text-purple-500 flex-shrink-0" />
                        <span className="text-xs font-medium text-gray-900 dark:text-white truncate flex-1">
                          {seg.name}
                        </span>
                        <span className={`px-1 py-0.5 rounded text-[10px] ${statusBadge.bg} ${statusBadge.text}`}>
                          {statusBadge.label}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Instance List - Takes remaining space */}
          {studyInfo && studyInfo.instances.length > 0 && (
            <div className="flex-1 overflow-y-auto p-3 min-h-0">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                <FileImage className="w-4 h-4" />
                {t('viewer.availableImages', 'Imágenes')} ({studyInfo.instances.length})
              </h4>
              <div className="space-y-1">
                {studyInfo.instances.map((instance, index) => (
                  <button
                    key={instance.id}
                    onClick={() => handleSelectInstance(instance.id)}
                    className={`w-full p-2 rounded-lg text-left transition-all ${
                      selectedInstanceId === instance.id
                        ? 'bg-primary-500 text-white shadow-md'
                        : 'bg-white/60 dark:bg-gray-800/60 hover:bg-white dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <FileImage className={`w-4 h-4 flex-shrink-0 ${
                        selectedInstanceId === instance.id
                          ? 'text-white'
                          : 'text-primary-500'
                      }`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium truncate">
                          {instance.original_filename || `Imagen ${index + 1}`}
                        </p>
                      </div>
                      <span className={`text-[10px] ${
                        selectedInstanceId === instance.id
                          ? 'text-white/70'
                          : 'text-gray-400'
                      }`}>
                        {(instance.file_size_bytes / 1024 / 1024).toFixed(1)}MB
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Viewer Controls */}
          {currentSeries && viewMode === '2d' && (
            <motion.div
              initial={{ y: 100, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.3 }}
              className="p-2 border-t border-gray-200 dark:border-gray-700 overflow-y-auto max-h-[35vh] flex-shrink-0"
            >
              <ViewerControls
                {...viewerControls}
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
            {isLoadingImage ? (
              <div className="h-full flex flex-col items-center justify-center">
                <Loader2 className="w-12 h-12 text-primary-500 animate-spin mb-4" />
                <p className="text-gray-600 dark:text-gray-400">{t('viewer.loadingImage')}</p>
              </div>
            ) : viewMode === '2d' ? (
              <ImageViewer2D
                viewerControls={viewerControls}
                segmentationControls={segmentationControls}
                createSegmentationRef={createSegmentationRef}
                patientName={patientData?.full_name}
                studyDescription={studyInfo?.study.study_description}
                studyModality={studyInfo?.study.modality}
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
