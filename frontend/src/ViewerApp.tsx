import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { toast, Toaster } from 'sonner';
import { motion } from 'framer-motion';
import ImageViewer2D from './components/ImageViewer2D';
import ImageViewer3D from './components/ImageViewer3D';
import { MultiPanelViewer } from './components/MultiPanelViewer';
import ControlPanel from './components/ControlPanel';
import ViewerControls from './components/ViewerControls';
import LanguageSelector from './components/LanguageSelector';
import ThemeToggle from './components/ThemeToggle';
import { imagingAPI } from './services/api';
import { studyAPI } from './services/studyApi';
import { useViewerStore } from './store/useViewerStore';
import { useViewerControls } from './hooks/useViewerControls';
import type { ImagingStudy, ImagingSeries, ImagingInstance } from './types';
import { LogOut, Sparkles, ArrowLeft, Brain, FileImage, AlertCircle, Loader2, Puzzle, Upload, Eye, EyeOff, Plus, Trash2, ChevronDown, ChevronRight, FlaskConical, FileText, LayoutGrid, Columns2, Square, Link2, Unlink2, Map } from 'lucide-react';
import { useAuth } from './contexts/AuthContext';
import { useTheme } from './contexts/ThemeContext';
import { segmentationAPI } from './api/segmentation';
import { usePatient } from './hooks/usePatients';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ReportViewerModal } from './components/ReportViewerModal';
import { AIReportPanel } from './components/AIReportPanel';
import { LesionDashboard } from './components/LesionDashboard';
import { MAGNIMSZoneMapPanel } from './components/MAGNIMSZoneMapPanel';
import { useSegmentationStore } from './store/useSegmentationStore';
import { useMultiViewerStore, type ViewerLayout } from './store/useMultiViewerStore';
import { autoAssignPanels } from './utils/sequenceDetection';
import type { ReportResponse } from './types';

interface StudyInfo {
  study: ImagingStudy;
  series: ImagingSeries[];
  instances: ImagingInstance[];
}

/** Inline overlay toggle + opacity slider + label visibility for segmentation list items */
function OverlayControls() {
  const { t } = useTranslation();
  const isOverlayVisible = useSegmentationStore((s) => s.isOverlayVisible);
  const setIsOverlayVisible = useSegmentationStore((s) => s.setIsOverlayVisible);
  const lesionOpacity = useSegmentationStore((s) => s.lesionOpacity);
  const setLesionOpacity = useSegmentationStore((s) => s.setLesionOpacity);
  const labels = useSegmentationStore((s) => s.activeSegmentation?.labels);
  const labelVisibility = useSegmentationStore((s) => s.labelVisibility);
  const toggleLabelVisibility = useSegmentationStore((s) => s.toggleLabelVisibility);

  return (
    <div className="space-y-1.5 mb-2 p-1.5 rounded bg-gray-800/40">
      <div className="flex items-center justify-between">
        <label className="text-[10px] text-gray-300">{t('segmentation.showOverlay', 'Show Overlay')}</label>
        <button
          onClick={() => setIsOverlayVisible(!isOverlayVisible)}
          className={`relative w-8 h-4 rounded-full transition-colors ${isOverlayVisible ? 'bg-blue-600' : 'bg-gray-600'}`}
        >
          <span className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${isOverlayVisible ? 'translate-x-4' : 'translate-x-0'}`} />
        </button>
      </div>
      {isOverlayVisible && (
        <>
          <div>
            <div className="flex items-center justify-between mb-0.5">
              <label className="text-[10px] text-gray-400">{t('segmentation.lesionOpacity', 'Lesion opacity')}</label>
              <span className="text-[10px] text-gray-500">{Math.round(lesionOpacity * 100)}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={Math.round(lesionOpacity * 100)}
              onChange={(e) => setLesionOpacity(Number(e.target.value) / 100)}
              className="w-full h-1 bg-gray-700 rounded-full appearance-none cursor-pointer accent-blue-500"
            />
          </div>
          {labels && labels.filter((l) => l.id !== 0).length > 0 && (
            <div className="space-y-1">
              <select
                value={(() => {
                  const names = labels.filter(l => l.id !== 0).map(l => l.name);
                  if (names.length === 6 && names[0] === 'Periventricular') return 'magnims';
                  if (names.length === 4 && names[0] === 'MS Lesion (Active)') return 'default';
                  return 'custom';
                })()}
                onChange={(e) => {
                  const preset = e.target.value;
                  if (preset === 'default' || preset === 'magnims') {
                    useSegmentationStore.getState().setLabelPreset(preset as 'default' | 'magnims');
                  }
                }}
                className="w-full px-1.5 py-1 bg-gray-700 border border-gray-600 rounded text-[10px] text-white"
              >
                <option value="default">Default</option>
                <option value="magnims">MAGNIMS Regional</option>
                <option value="custom" disabled>Custom</option>
              </select>
            </div>
          )}
          {labels && labels.filter((l) => l.id !== 0).length > 0 && (
            <div className="space-y-0.5 max-h-28 overflow-y-auto">
              {labels.filter((l) => l.id !== 0).map((label) => {
                const visible = labelVisibility[label.id] !== false;
                return (
                  <button
                    key={label.id}
                    onClick={() => toggleLabelVisibility(label.id)}
                    className="w-full flex items-center gap-1.5 px-1 py-0.5 rounded hover:bg-gray-700/50 transition-colors"
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-sm flex-shrink-0 border border-gray-600"
                      style={{ backgroundColor: visible ? label.color : 'transparent' }}
                    />
                    <span className={`text-[10px] truncate flex-1 text-left ${visible ? 'text-gray-200' : 'text-gray-500 line-through'}`}>
                      {label.name}
                    </span>
                    <Eye className={`w-2.5 h-2.5 flex-shrink-0 ${visible ? 'text-blue-400' : 'text-gray-600'}`} />
                  </button>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ViewerApp() {
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
  const setAllFileIds = useViewerStore((state) => state.setAllFileIds);
  const setCurrentSliceIndex = useViewerStore((state) => state.setCurrentSliceIndex);

  const [selectedInstanceId, setSelectedInstanceId] = useState<string | null>(null);
  const [studyInfo, setStudyInfo] = useState<StudyInfo | null>(null);
  const [deletingSegId, setDeletingSegId] = useState<string | null>(null);
  const [expandedSegIds, setExpandedSegIds] = useState<Set<string>>(new Set());

  const queryClient = useQueryClient();
  const currentSegmentation = useSegmentationStore((s) => s.currentSegmentation);
  const activeSegmentation = useSegmentationStore((s) => s.activeSegmentation);
  const setCurrentSegmentation = useSegmentationStore((s) => s.setCurrentSegmentation);
  const setIsPaintMode = useSegmentationStore((s) => s.setIsPaintMode);
  const zoneMapVisible = useSegmentationStore((s) => s.zoneMapVisible);
  const isOverlayVisible = useSegmentationStore((s) => s.isOverlayVisible);

  const viewerControls = useViewerControls();
  const createSegmentationRef = useRef<(() => void) | null>(null);
  const segmentationUploadRef = useRef<HTMLInputElement>(null);
  const [reportToView, setReportToView] = useState<ReportResponse | null>(null);


  // Multi-panel viewer
  const multiLayout = useMultiViewerStore((s) => s.layout);
  const setMultiLayout = useMultiViewerStore((s) => s.setLayout);
  const syncSlice = useMultiViewerStore((s) => s.syncSlice);
  const setSyncSlice = useMultiViewerStore((s) => s.setSyncSlice);
  const autoAssign = useMultiViewerStore((s) => s.autoAssign);
  const isMultiPanel = multiLayout !== 'single';
  const [multiPanelSource, setMultiPanelSource] = useState<'originals' | 'preprocessed'>('originals');

  // Collapsible section states
  const [sectionsExpanded, setSectionsExpanded] = useState({
    originals: true,
    preprocessed: true,
    segmentations: true,
    experts: true,
  });
  const toggleSection = useCallback((key: 'originals' | 'preprocessed' | 'segmentations' | 'experts') => {
    setSectionsExpanded(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // MS Report panel dropdown
  const [reportPanelOpen, setReportPanelOpen] = useState(false);
  const reportPanelRef = useRef<HTMLDivElement>(null);

  // Close report panel when clicking outside
  useEffect(() => {
    if (!reportPanelOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (reportPanelRef.current && !reportPanelRef.current.contains(e.target as Node)) {
        setReportPanelOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [reportPanelOpen]);

  // Filter instances into groups: originals, preprocessed, masks (hidden)
  // Supports both legacy names (test01_01_flair_pp.nii) and BIDS names (sub-MS001_ses-01_desc-preproc_FLAIR.nii.gz)
  const isPreprocessedInstance = useCallback((filename: string) => {
    const lower = filename.toLowerCase();
    // Legacy: *_pp.nii or *_pp.nii.gz
    // BIDS: *desc-preproc* or *desc-segfrompreproc*
    return lower.endsWith('_pp.nii') || lower.endsWith('_pp.nii.gz')
      || lower.includes('desc-preproc') || lower.includes('desc-segfrompreproc');
  }, []);

  const originalInstances = useMemo(() =>
    studyInfo?.instances.filter(inst => {
      const fn = inst.original_filename || '';
      return !isPreprocessedInstance(fn);
    }) ?? [],
    [studyInfo?.instances, isPreprocessedInstance]
  );

  const preprocessedInstances = useMemo(() =>
    studyInfo?.instances.filter(inst => isPreprocessedInstance(inst.original_filename || '')) ?? [],
    [studyInfo?.instances, isPreprocessedInstance]
  );

  // Instances to use for multi-panel viewer (based on source toggle)
  const multiPanelInstances = useMemo(() =>
    multiPanelSource === 'preprocessed' && preprocessedInstances.length > 0
      ? preprocessedInstances
      : originalInstances,
    [multiPanelSource, originalInstances, preprocessedInstances]
  );

  // Auto-assign panels when switching to multi-panel layout
  const handleLayoutChange = useCallback((layout: ViewerLayout) => {
    setMultiLayout(layout);
    if (layout !== 'single' && multiPanelInstances.length > 0) {
      const assignments = autoAssignPanels(multiPanelInstances);
      autoAssign(assignments.map((a) => ({ instanceId: a.instance.id, sequence: a.sequence })));
    }
  }, [setMultiLayout, autoAssign, multiPanelInstances]);

  // Re-assign panels when source toggle changes
  const handleMultiPanelSourceChange = useCallback((source: 'originals' | 'preprocessed') => {
    setMultiPanelSource(source);
    const instances = source === 'preprocessed' && preprocessedInstances.length > 0
      ? preprocessedInstances
      : originalInstances;
    if (isMultiPanel && instances.length > 0) {
      const assignments = autoAssignPanels(instances);
      autoAssign(assignments.map((a) => ({ instanceId: a.instance.id, sequence: a.sequence })));
    }
  }, [autoAssign, isMultiPanel, originalInstances, preprocessedInstances]);

  // Collect all file_ids from all instances in the study
  const allFileIds = useMemo(() =>
    studyInfo?.instances.map(inst => inst.gcs_object_name).filter(Boolean) ?? [],
    [studyInfo?.instances]
  );

  // Fetch segmentations for ALL images in the study (not just current image)
  const { data: segmentationsData, isLoading: isLoadingSegmentations } = useQuery({
    queryKey: ['segmentations', 'study', studyId],
    queryFn: () => allFileIds.length > 0
      ? segmentationAPI.listSegmentationsByFileIds(allFileIds)
      : Promise.resolve([]),
    enabled: allFileIds.length > 0,
  });

  const segmentations = (() => {
    const all = (segmentationsData ?? []).map((seg) => ({
      id: seg.segmentation_id,
      name: seg.metadata?.description || t('segmentation.defaultName', 'Segmentation'),
      status: 'saved' as const,
      fileId: seg.file_id,
    }));
    // Deduplicate zone maps — keep only one per study (the first found)
    let zoneMapSeen = false;
    return all.filter((seg) => {
      if (seg.name === 'MAGNIMS Zone Map') {
        if (zoneMapSeen) return false;
        zoneMapSeen = true;
      }
      return true;
    });
  })();

  // Fetch patient info to display name in viewer
  const { data: patientData } = usePatient(studyInfo?.study.patient_id);

  // Load study data when studyId is present
  const { data: loadedStudyInfo, isLoading: isLoadingStudy, error: studyError } = useQuery({
    queryKey: ['study-viewer', studyId],
    queryFn: async (): Promise<StudyInfo | null> => {
      if (!studyId) return null;

      // Fetch study details and series list in parallel
      const [study, series] = await Promise.all([
        studyAPI.getById(studyId),
        studyAPI.listSeries(studyId),
      ]);

      // Fetch ALL series instances in parallel (instead of sequentially)
      const instanceArrays = await Promise.all(
        series.map(s => studyAPI.listInstances(s.id))
      );
      const instances = instanceArrays.flat();

      return { study, series, instances };
    },
    enabled: !!studyId,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });

  // Update state when study data is loaded
  useEffect(() => {
    if (loadedStudyInfo) {
      setStudyInfo(loadedStudyInfo);

      // Set hierarchical context for segmentation
      const patientId = loadedStudyInfo.study.patient_id;
      const seriesId = loadedStudyInfo.series.length > 0 ? loadedStudyInfo.series[0].id : null;
      setHierarchicalContext(patientId, studyId, seriesId);

      // Set all file_ids for study-level segmentation queries
      const fileIds = loadedStudyInfo.instances
        .map(inst => inst.gcs_object_name)
        .filter(Boolean);
      setAllFileIds(fileIds);

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
    staleTime: 10 * 60 * 1000, // Cache images for 10 minutes
  });

  // Load image when selectedInstanceId changes
  useEffect(() => {
    if (selectedInstanceId) {
      loadImage();
    }
  }, [selectedInstanceId, loadImage]);

  // Auto-load zone map when a lesion segmentation references one via analysis_data.
  // Zone map loading via sidebar click is handled by handleToggleZoneMap (independent).
  useEffect(() => {
    const segId = currentSegmentation?.segmentation_id;
    if (!segId) return;
    // Skip if current segmentation IS the zone map (handled by handleToggleZoneMap)
    if (currentSegmentation?.metadata?.description === 'MAGNIMS Zone Map') return;

    const zoneMapSegId = currentSegmentation?.metadata?.analysis_data?.zone_map_seg_id;
    if (!zoneMapSegId) return;
    if (useSegmentationStore.getState().zoneMapSegId === zoneMapSegId) return;

    segmentationAPI.loadZoneMapMask(zoneMapSegId)
      .then(({ mask, depth, height, width }) => {
        useSegmentationStore.getState().setZoneMap(zoneMapSegId, mask, { depth, height, width });
      })
      .catch(() => {
        console.warn('[ViewerApp] Referenced zone map not found');
      });
  }, [currentSegmentation?.segmentation_id, currentSegmentation?.metadata?.analysis_data?.zone_map_seg_id]);

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

  // Handle opening/loading an existing segmentation (toggle: click again to deactivate)
  const handleOpenSegmentation = useCallback((segmentation: { id: string; name: string; fileId?: string }) => {
    // Toggle off if clicking the already-active segmentation
    if (currentSegmentation?.segmentation_id === segmentation.id) {
      setCurrentSegmentation(null);
      viewerControls.setSegmentationMode(false);
      return;
    }

    // Find full segmentation data from the query results
    const fullSeg = segmentationsData?.find((s) => s.segmentation_id === segmentation.id);
    if (!fullSeg) return;

    // Segmentations are in MNI space — need a preprocessed image to overlay on.
    // If user is currently on an original image, switch to the first preprocessed image.
    const currentFilename = studyInfo?.instances.find(
      (inst) => inst.gcs_object_name === currentSeries?.file_id
    )?.original_filename || '';
    const isOnPreprocessed = isPreprocessedInstance(currentFilename);

    if (!isOnPreprocessed && preprocessedInstances.length > 0) {
      setSelectedInstanceId(preprocessedInstances[0].id);
    }

    setCurrentSegmentation(fullSeg);
    // Activate segmentation mode
    viewerControls.setSegmentationMode(true);
    toast.success(t('viewer.segmentationLoaded', `Segmentation "${segmentation.name}" loaded`));
  }, [viewerControls, t, segmentationsData, setCurrentSegmentation, currentSegmentation, currentSeries?.file_id, studyInfo, isPreprocessedInstance, preprocessedInstances]);

  // Toggle expand/collapse for a segmentation item's info panel
  const toggleSegExpanded = useCallback((segId: string) => {
    setExpandedSegIds((prev) => {
      const next = new Set(prev);
      if (next.has(segId)) next.delete(segId);
      else next.add(segId);
      return next;
    });
  }, []);

  // Handle clicking MAGNIMS Zone Map — independent from lesion segmentations.
  // Does NOT set currentSegmentation; only loads zone map into its own store fields.
  const handleToggleZoneMap = useCallback((seg: { id: string; name: string }) => {
    toggleSegExpanded(seg.id);
    // Load zone map mask into independent store fields (if not already loaded)
    const store = useSegmentationStore.getState();
    if (store.zoneMapSegId === seg.id) {
      // Already loaded — just toggle visibility
      store.toggleZoneMapVisibility();
      return;
    }
    // First time — load from server
    segmentationAPI.loadZoneMapMask(seg.id)
      .then(({ mask, depth, height, width }) => {
        useSegmentationStore.getState().setZoneMap(seg.id, mask, { depth, height, width });
        useSegmentationStore.setState({ zoneMapVisible: true });
      })
      .catch(() => {
        console.warn('[ViewerApp] Zone map mask not found');
      });
  }, [toggleSegExpanded]);

  // Handle upload segmentation file
  const handleUploadSegmentation = useCallback(() => {
    segmentationUploadRef.current?.click();
  }, []);

  const handleSegmentationFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    toast.loading(t('viewer.uploadingSegmentation', 'Uploading segmentation...'), { id: 'upload-seg' });

    // TODO: Implement actual upload logic
    // For now just show a message
    setTimeout(() => {
      toast.success(t('viewer.segmentationUploaded', 'Segmentation uploaded successfully'), { id: 'upload-seg' });
    }, 1000);

    // Reset input
    if (segmentationUploadRef.current) {
      segmentationUploadRef.current.value = '';
    }
  }, [t]);

  // Handle deleting a segmentation
  const handleDeleteSegmentation = useCallback(async (segId: string, segName: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Don't trigger the open handler
    if (!confirm(t('viewer.confirmDeleteSegmentation', `Delete segmentation "${segName}"?`))) return;

    setDeletingSegId(segId);
    try {
      await segmentationAPI.deleteSegmentation(segId);
      // If the deleted one was active, clear it
      if (currentSegmentation?.segmentation_id === segId) {
        setCurrentSegmentation(null);
        viewerControls.setSegmentationMode(false);
      }
      queryClient.invalidateQueries({ queryKey: ['segmentations', 'study', studyId] });
      toast.success(t('viewer.segmentationDeleted', 'Segmentation deleted'));
    } catch (error) {
      console.error('[ViewerApp] Failed to delete segmentation:', error);
      toast.error(t('viewer.segmentationDeleteFailed', 'Failed to delete segmentation'));
    } finally {
      setDeletingSegId(null);
    }
  }, [currentSegmentation, setCurrentSegmentation, viewerControls, queryClient, studyId, t]);

  // Handle create new segmentation (activates segmentation mode and creates segmentation)
  const handleCreateSegmentation = useCallback(() => {
    if (!currentSeries) {
      toast.error(t('viewer.noImageLoaded', 'Load an image first'));
      return;
    }
    // First enable segmentation mode
    viewerControls.setSegmentationMode(true);
    // Auto-enable paint mode for new segmentations (user wants to start drawing)
    setIsPaintMode(true);
    // Then trigger segmentation creation
    if (createSegmentationRef.current) {
      createSegmentationRef.current();
      toast.info(t('viewer.segmentationModeActivated', 'Segmentation mode activated. Use the drawing tools.'));
    } else {
      toast.error(t('viewer.segmentationCreationFailed', 'Failed to create segmentation'));
    }
  }, [viewerControls, t, currentSeries, setIsPaintMode]);

  // No study ID provided
  if (!studyId) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
        <AlertCircle className="w-16 h-16 text-amber-500 mb-4" />
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
          {t('viewer.noStudySelected', 'No study selected')}
        </h2>
        <p className="text-gray-500 dark:text-gray-400 mb-4 text-center max-w-md">
          {t('viewer.selectStudyDescription', 'Select a patient and upload an MRI study to view it.')}
        </p>
        <button
          onClick={() => navigate('/app')}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600"
        >
          <ArrowLeft className="w-4 h-4" />
          {t('viewer.goToPatients', 'Go to Patients')}
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
        <p className="text-gray-600 dark:text-gray-400">{t('viewer.loadingStudy', 'Loading study...')}</p>
      </div>
    );
  }

  // Study error or not found
  if (studyError || (!isLoadingStudy && !studyInfo)) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
        <AlertCircle className="w-16 h-16 text-red-500 mb-4" />
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
          {t('viewer.studyNotFound', 'Study not found')}
        </h2>
        <p className="text-gray-500 dark:text-gray-400 mb-4">
          {t('viewer.studyNotFoundDescription', 'The requested study does not exist or you do not have access.')}
        </p>
        <button
          onClick={() => navigate('/app')}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600"
        >
          <ArrowLeft className="w-4 h-4" />
          {t('common.goBack', 'Go Back')}
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
              {/* MS Report Button + Dropdown */}
              <div className="relative" ref={reportPanelRef}>
                <motion.button
                  onClick={() => setReportPanelOpen(!reportPanelOpen)}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className={`flex items-center gap-2 px-4 py-2 backdrop-blur-md border rounded-xl text-xs font-semibold shadow-lg transition-all ${
                    reportPanelOpen
                      ? 'bg-amber-500 border-amber-400 text-white shadow-amber-500/20'
                      : 'bg-gradient-to-r from-amber-500/20 to-amber-600/20 dark:from-amber-500/30 dark:to-amber-600/30 border-amber-500/30 dark:border-amber-500/20 text-amber-700 dark:text-amber-400 shadow-amber-500/10 hover:from-amber-500/30 hover:to-amber-600/30'
                  }`}
                >
                  <FileText className="w-4 h-4" />
                  {t('report.title', 'MS Report')}
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${reportPanelOpen ? 'rotate-180' : ''}`} />
                </motion.button>

                {/* Dropdown Panel */}
                {reportPanelOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: -8, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -8, scale: 0.95 }}
                    transition={{ duration: 0.15 }}
                    className="absolute top-full right-0 mt-2 w-80 bg-white/95 dark:bg-gray-900/95 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl shadow-2xl shadow-gray-900/20 dark:shadow-black/40 z-50 overflow-hidden"
                  >
                    <div className="p-4">
                      <AIReportPanel onReportGenerated={(report) => { setReportToView(report); setReportPanelOpen(false); }} />
                    </div>
                  </motion.div>
                )}
              </div>

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
                {t('viewer.studyInfo', 'Study')}
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
                  <span className="text-gray-500">{studyInfo.series.length} {t('study.series', 'series')}</span>
                </div>
                <div>
                  <span className="text-gray-500">{originalInstances.length + preprocessedInstances.length} {t('study.images', 'images')}</span>
                </div>
                {studyInfo.study.body_site && (
                  <div className="col-span-2">
                    <span className="text-gray-400">{studyInfo.study.body_site}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Scrollable content: 3 collapsible sections */}
          <div className="flex-1 overflow-y-auto min-h-0">

            {/* Section 1: Original Images */}
            {originalInstances.length > 0 && (
              <div className="border-b border-gray-200/50 dark:border-gray-700/50">
                <button
                  onClick={() => toggleSection('originals')}
                  className="w-full flex items-center justify-between p-3 hover:bg-gray-100/50 dark:hover:bg-gray-800/50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <FileImage className="w-4 h-4 text-primary-500" />
                    <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                      {t('viewer.originalImages', 'Originales')}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-400">
                      {originalInstances.length}
                    </span>
                  </div>
                  {sectionsExpanded.originals ? (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  )}
                </button>
                {sectionsExpanded.originals && (
                  <div className="px-3 pb-3 space-y-1">
                    {originalInstances.map((instance) => (
                      <button
                        key={instance.id}
                        onClick={() => handleSelectInstance(instance.id)}
                        className={`w-full p-1.5 rounded-lg text-left transition-all ${
                          selectedInstanceId === instance.id
                            ? 'bg-primary-500 text-white shadow-md'
                            : 'bg-white/60 dark:bg-gray-800/60 hover:bg-white dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <FileImage className={`w-3.5 h-3.5 flex-shrink-0 ${
                            selectedInstanceId === instance.id ? 'text-white' : 'text-primary-500'
                          }`} />
                          <p className="text-[11px] font-medium truncate flex-1">
                            {instance.original_filename || 'Image'}
                          </p>
                          <span className={`text-[10px] ${
                            selectedInstanceId === instance.id ? 'text-white/70' : 'text-gray-400'
                          }`}>
                            {(instance.file_size_bytes / 1024 / 1024).toFixed(1)}MB
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Section 2: Preprocessed Images */}
            {preprocessedInstances.length > 0 && (
              <div className="border-b border-gray-200/50 dark:border-gray-700/50">
                <button
                  onClick={() => toggleSection('preprocessed')}
                  className="w-full flex items-center justify-between p-3 hover:bg-gray-100/50 dark:hover:bg-gray-800/50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <FlaskConical className="w-4 h-4 text-teal-500" />
                    <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                      {t('viewer.preprocessedImages', 'Preprocesadas')}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400">
                      {preprocessedInstances.length}
                    </span>
                  </div>
                  {sectionsExpanded.preprocessed ? (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  )}
                </button>
                {sectionsExpanded.preprocessed && (
                  <div className="px-3 pb-3 space-y-1">
                    {preprocessedInstances.map((instance) => (
                      <button
                        key={instance.id}
                        onClick={() => handleSelectInstance(instance.id)}
                        className={`w-full p-1.5 rounded-lg text-left transition-all ${
                          selectedInstanceId === instance.id
                            ? 'bg-teal-500 text-white shadow-md'
                            : 'bg-white/60 dark:bg-gray-800/60 hover:bg-white dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <FlaskConical className={`w-3.5 h-3.5 flex-shrink-0 ${
                            selectedInstanceId === instance.id ? 'text-white' : 'text-teal-500'
                          }`} />
                          <p className="text-[11px] font-medium truncate flex-1">
                            {instance.original_filename || 'Preprocessed'}
                          </p>
                          <span className={`text-[10px] ${
                            selectedInstanceId === instance.id ? 'text-white/70' : 'text-gray-400'
                          }`}>
                            {(instance.file_size_bytes / 1024 / 1024).toFixed(1)}MB
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Section 3: Segmentations */}
            <div className="border-b border-gray-200/50 dark:border-gray-700/50">
              <button
                onClick={() => toggleSection('segmentations')}
                className="w-full flex items-center justify-between p-3 hover:bg-gray-100/50 dark:hover:bg-gray-800/50 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Puzzle className="w-4 h-4 text-purple-500" />
                  <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                    {t('viewer.segmentations', 'Segmentaciones')}
                  </span>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    segmentations.length > 0
                      ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
                      : 'bg-gray-100 text-gray-500 dark:bg-gray-700/50 dark:text-gray-400'
                  }`}>
                    {segmentations.length}
                  </span>
                </div>
                {sectionsExpanded.segmentations ? (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                )}
              </button>
              {sectionsExpanded.segmentations && (
                <div className="px-3 pb-3">
                  {/* Action Buttons */}
                  <div className="flex gap-1.5 mb-2">
                    <button
                      onClick={handleCreateSegmentation}
                      disabled={!currentSeries}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-purple-500 hover:bg-purple-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white text-xs font-medium rounded-md transition-colors"
                      title={t('viewer.createSegmentation', 'Create new segmentation')}
                    >
                      <Plus className="w-3 h-3" />
                      {t('viewer.create', 'Create')}
                    </button>
                    <button
                      onClick={handleUploadSegmentation}
                      disabled={!studyInfo}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white text-xs font-medium rounded-md transition-colors"
                      title={t('viewer.uploadSegmentation', 'Upload segmentation')}
                    >
                      <Upload className="w-3 h-3" />
                      {t('viewer.upload', 'Upload')}
                    </button>
                    <input
                      ref={segmentationUploadRef}
                      type="file"
                      accept=".nii,.nii.gz,.nrrd,.seg.nrrd"
                      className="hidden"
                      onChange={handleSegmentationFileChange}
                    />
                  </div>

                  {/* Segmentations List */}
                  {isLoadingSegmentations ? (
                    <div className="flex items-center justify-center py-2">
                      <Loader2 className="w-4 h-4 text-purple-500 animate-spin" />
                    </div>
                  ) : segmentations.length === 0 ? (
                    <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-1">
                      {t('viewer.noSegmentations', 'No segmentations')}
                    </p>
                  ) : (
                    <div className="space-y-1.5">
                      {segmentations.map((seg) => {
                        const isZoneMap = seg.name === 'MAGNIMS Zone Map';
                        const isActive = currentSegmentation?.segmentation_id === seg.id || activeSegmentation?.id === seg.id;
                        const isExpanded = expandedSegIds.has(seg.id);
                        const isDeleting = deletingSegId === seg.id;
                        const isSaved = !seg.id.startsWith('local-');

                        if (isZoneMap) {
                          // --- MAGNIMS Zone Map: independent layer, NOT tied to currentSegmentation ---
                          return (
                            <div key={seg.id}>
                              <div
                                onClick={() => handleToggleZoneMap(seg)}
                                className={`rounded-lg cursor-pointer transition-all ${
                                  isExpanded
                                    ? 'ring-2 ring-emerald-400 bg-emerald-100 dark:bg-emerald-900/40'
                                    : 'bg-white/60 dark:bg-gray-800/80 hover:bg-white dark:hover:bg-gray-700/80'
                                }`}
                              >
                                <div className="flex items-center gap-2 p-2">
                                  {isExpanded
                                    ? <ChevronDown className="w-3 h-3 flex-shrink-0 text-emerald-400" />
                                    : <ChevronRight className="w-3 h-3 flex-shrink-0 text-gray-400" />
                                  }
                                  <Map className="w-3.5 h-3.5 flex-shrink-0 text-emerald-500" />
                                  <span className={`text-[11px] font-medium truncate flex-1 ${isExpanded ? 'text-emerald-900 dark:text-white' : 'text-gray-700 dark:text-white'}`}>
                                    {seg.name}
                                  </span>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      useSegmentationStore.getState().toggleZoneMapVisibility();
                                    }}
                                    className={`p-1 rounded transition-colors flex-shrink-0 ${
                                      zoneMapVisible ? 'text-emerald-400 hover:text-emerald-300' : 'text-gray-500 hover:text-gray-300'
                                    }`}
                                    title={zoneMapVisible ? 'Hide overlay' : 'Show overlay'}
                                  >
                                    {zoneMapVisible ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                                  </button>
                                  <button
                                    onClick={(e) => handleDeleteSegmentation(seg.id, seg.name, e)}
                                    disabled={isDeleting}
                                    className="p-1 text-gray-400 hover:text-red-500 dark:text-gray-500 dark:hover:text-red-400 transition-colors flex-shrink-0"
                                  >
                                    {isDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                                  </button>
                                </div>
                              </div>
                              {isExpanded && isSaved && (
                                <div className="ml-2 mt-1 mb-1 border-l-2 border-emerald-600/30 pl-2">
                                  <MAGNIMSZoneMapPanel fileId={currentSeries?.file_id} />
                                </div>
                              )}
                            </div>
                          );
                        }

                        // --- Regular segmentation (Expert Rater, Brain Extraction, etc.) ---
                        return (
                          <div key={seg.id}>
                            <div
                              onClick={() => {
                                handleOpenSegmentation(seg);
                                // Auto-expand on activate, collapse on deactivate
                                if (isActive) {
                                  setExpandedSegIds((prev) => { const n = new Set(prev); n.delete(seg.id); return n; });
                                } else {
                                  setExpandedSegIds((prev) => new Set(prev).add(seg.id));
                                }
                              }}
                              className={`rounded-lg cursor-pointer transition-all ${
                                isActive
                                  ? 'ring-2 ring-purple-400 bg-purple-100 dark:bg-purple-900/50'
                                  : 'bg-white/60 dark:bg-gray-800/80 hover:bg-white dark:hover:bg-gray-700/80'
                              }`}
                            >
                              <div className="flex items-center gap-2 p-2">
                                {isExpanded
                                  ? <ChevronDown className="w-3 h-3 flex-shrink-0 text-purple-400" />
                                  : <ChevronRight className="w-3 h-3 flex-shrink-0 text-gray-400" />
                                }
                                <Puzzle className={`w-3.5 h-3.5 flex-shrink-0 ${isActive ? 'text-purple-500 dark:text-purple-400' : 'text-purple-500'}`} />
                                <span className={`text-[11px] font-medium truncate flex-1 ${isActive ? 'text-purple-900 dark:text-white' : 'text-gray-700 dark:text-white'}`}>
                                  {seg.name}
                                </span>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (isActive) {
                                      useSegmentationStore.getState().setIsOverlayVisible(!isOverlayVisible);
                                    } else {
                                      handleOpenSegmentation(seg);
                                      setExpandedSegIds((prev) => new Set(prev).add(seg.id));
                                    }
                                  }}
                                  className={`p-1 rounded transition-colors flex-shrink-0 ${
                                    isActive && isOverlayVisible ? 'text-purple-400 hover:text-purple-300' : 'text-gray-500 hover:text-gray-300'
                                  }`}
                                  title={isActive && isOverlayVisible ? 'Hide overlay' : 'Show overlay'}
                                >
                                  {isActive && isOverlayVisible ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                                </button>
                                <button
                                  onClick={(e) => handleDeleteSegmentation(seg.id, seg.name, e)}
                                  disabled={isDeleting}
                                  className="p-1 text-gray-400 hover:text-red-500 dark:text-gray-500 dark:hover:text-red-400 transition-colors flex-shrink-0"
                                >
                                  {isDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                                </button>
                              </div>
                            </div>
                            {isExpanded && isSaved && (
                              <div className="ml-2 mt-1 mb-1 border-l-2 border-cyan-600/30 pl-2">
                                {/* Overlay controls inline */}
                                <OverlayControls />
                                <LesionDashboard
                                  segmentationId={seg.id}
                                  onNavigateToSlice={(idx) => setCurrentSliceIndex(idx)}
                                />
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

          </div>

          {/* Viewer Controls */}
          {currentSeries && (
            <motion.div
              initial={{ y: 100, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.3 }}
              className="p-2 border-t border-gray-200 dark:border-gray-700 overflow-y-auto max-h-[35vh] flex-shrink-0"
            >
              <ErrorBoundary name="ViewerControls">
                <ViewerControls
                  {...viewerControls}
                  viewMode={viewMode}
                  onNavigateToSlice={(idx) => setCurrentSliceIndex(idx)}
                />
              </ErrorBoundary>
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
          {/* Layout Switcher Toolbar */}
          {viewMode === '2d' && (originalInstances.length > 1 || preprocessedInstances.length > 1) && (
            <div className="flex items-center justify-center gap-2 mb-2">
              <div className="flex items-center bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm rounded-lg border border-gray-200/50 dark:border-gray-700/50 p-1 gap-1">
                <button
                  onClick={() => handleLayoutChange('single')}
                  className={`p-1.5 rounded transition-colors ${
                    multiLayout === 'single' ? 'bg-blue-500 text-white' : 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'
                  }`}
                  title={t('layout.single', 'Single View')}
                >
                  <Square className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleLayoutChange('1x2')}
                  className={`p-1.5 rounded transition-colors ${
                    multiLayout === '1x2' ? 'bg-blue-500 text-white' : 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'
                  }`}
                  title={t('layout.sideBySide', '1x2 Side by Side')}
                >
                  <Columns2 className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleLayoutChange('2x2')}
                  className={`p-1.5 rounded transition-colors ${
                    multiLayout === '2x2' ? 'bg-blue-500 text-white' : 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'
                  }`}
                  title={t('layout.grid', '2x2 Grid')}
                >
                  <LayoutGrid className="w-4 h-4" />
                </button>
                {isMultiPanel && (
                  <>
                    <div className="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />
                    <button
                      onClick={() => setSyncSlice(!syncSlice)}
                      className={`p-1.5 rounded transition-colors ${
                        syncSlice ? 'bg-green-500 text-white' : 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'
                      }`}
                      title={syncSlice ? t('layout.syncOn', 'Slice sync: ON') : t('layout.syncOff', 'Slice sync: OFF')}
                    >
                      {syncSlice ? <Link2 className="w-4 h-4" /> : <Unlink2 className="w-4 h-4" />}
                    </button>
                    {preprocessedInstances.length > 0 && (
                      <>
                        <div className="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />
                        <button
                          onClick={() => handleMultiPanelSourceChange(
                            multiPanelSource === 'originals' ? 'preprocessed' : 'originals'
                          )}
                          className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
                            multiPanelSource === 'preprocessed'
                              ? 'bg-teal-500 text-white'
                              : 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'
                          }`}
                          title={multiPanelSource === 'preprocessed'
                            ? t('layout.showOriginals', 'Switch to original images')
                            : t('layout.showPreprocessed', 'Switch to preprocessed images')
                          }
                        >
                          {multiPanelSource === 'preprocessed'
                            ? <FlaskConical className="w-3.5 h-3.5" />
                            : <FileImage className="w-3.5 h-3.5" />
                          }
                          {multiPanelSource === 'preprocessed'
                            ? t('layout.preprocessed', 'Preproc')
                            : t('layout.originals', 'Original')
                          }
                        </button>
                      </>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          <div className="h-full bg-white/60 dark:bg-gray-900/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl shadow-2xl overflow-hidden">
            {isLoadingImage && !isMultiPanel ? (
              <div className="h-full flex flex-col items-center justify-center">
                <Loader2 className="w-12 h-12 text-primary-500 animate-spin mb-4" />
                <p className="text-gray-600 dark:text-gray-400">{t('viewer.loadingImage')}</p>
              </div>
            ) : isMultiPanel && viewMode === '2d' ? (
              <ErrorBoundary name="MultiPanelViewer">
                <MultiPanelViewer
                  instances={multiPanelInstances}
                />
              </ErrorBoundary>
            ) : viewMode === '2d' ? (
              <ErrorBoundary name="ImageViewer2D">
                <ImageViewer2D
                  viewerControls={viewerControls}
                  createSegmentationRef={createSegmentationRef}
                  patientName={patientData?.full_name}
                  studyDescription={studyInfo?.study.study_description}
                  studyModality={studyInfo?.study.modality}
                />
              </ErrorBoundary>
            ) : (
              <ErrorBoundary name="ImageViewer3D">
                <ImageViewer3D />
              </ErrorBoundary>
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

      {/* Report Viewer Modal */}
      {reportToView && (
        <ReportViewerModal
          report={reportToView}
          isOpen={!!reportToView}
          onClose={() => setReportToView(null)}
          patientName={patientData?.full_name}
          patientMRN={patientData?.mrn}
          patientAge={patientData?.age}
          patientSex={patientData?.gender === 'male' ? 'M' : patientData?.gender === 'female' ? 'F' : undefined}
          studyDate={studyInfo?.study.study_date}
          studyDescription={studyInfo?.study.study_description}
          institutionName={studyInfo?.study.institution_name}
        />
      )}
    </div>
  );
}

export default ViewerApp;
