import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { toast, Toaster } from 'sonner';
import { motion } from 'framer-motion';
import AppHeader from './components/AppHeader';
import ImageViewer2D from './components/ImageViewer2D';
import ImageViewer3D from './components/ImageViewer3D';
import { MultiPanelViewer } from './components/MultiPanelViewer';
import ControlPanel from './components/ControlPanel';
import ViewerControls from './components/ViewerControls';
import LanguageSelector from './components/LanguageSelector';
import ThemeToggle from './components/ThemeToggle';
import { imagingAPI } from './api/imaging';
import { studyAPI } from './api/study';
import { useViewerStore } from './store/useViewerStore';
import { useViewerControls } from './hooks/useViewerControls';
import type { ImagingStudy, ImagingSeries, ImagingInstance } from './types';
import { ArrowLeft, Brain, FileImage, AlertCircle, Loader2, Puzzle, Upload, Eye, EyeOff, Plus, Trash2, ChevronDown, ChevronRight, FlaskConical, FileText, LayoutGrid, Columns2, Square, Link2, Unlink2, Map, ZoomIn, ZoomOut, RotateCw, Ruler, Triangle, Circle } from 'lucide-react';
import UserMenu from './components/UserMenu';
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
import { autoAssignPanels, detectSequence } from './utils/sequenceDetection';
import { isPreprocessedInstance } from './utils/instanceClassification';
import { detectLabelPreset } from './utils/labelPresets';
import { useActiveSliceInfo } from './hooks/useActiveSliceInfo';
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
                value={detectLabelPreset(labels)}
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
  const currentSliceIndex = useViewerStore((state) => state.currentSliceIndex);
  const zoomLevel = useViewerStore((state) => state.zoomLevel);
  const setZoomLevel = useViewerStore((state) => state.setZoomLevel);
  const setPanOffset = useViewerStore((state) => state.setPanOffset);
  const measurementTool = useViewerStore((state) => state.measurementTool);
  const setMeasurementTool = useViewerStore((state) => state.setMeasurementTool);
  const triggerMeasurementClear = useViewerStore((state) => state.triggerMeasurementClear);

  // Unified slice info — reads from correct store based on single/multi panel mode
  const activeSlice = useActiveSliceInfo();

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
  const activePanelId = useMultiViewerStore((s) => s.activePanelId);
  const assignInstance = useMultiViewerStore((s) => s.assignInstance);
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

  // Filter instances into groups: originals, preprocessed, masks (hidden).
  // Classification lives in utils/instanceClassification (pure + unit-tested).
  const originalInstances = useMemo(() =>
    studyInfo?.instances.filter(inst => {
      const fn = inst.original_filename || '';
      return !isPreprocessedInstance(fn);
    }) ?? [],
    [studyInfo?.instances]
  );

  const preprocessedInstances = useMemo(() =>
    studyInfo?.instances.filter(inst => isPreprocessedInstance(inst.original_filename || '')) ?? [],
    [studyInfo?.instances]
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
    if (isMultiPanel) {
      // In multi-panel mode: assign the clicked image to the active (focused) panel
      const instance = studyInfo?.instances.find(i => i.id === instanceId);
      const sequence = instance ? detectSequence(instance.original_filename || '') : 'unknown';
      assignInstance(activePanelId, instanceId, sequence);
    } else {
      // In single panel mode: load the image normally
      setSelectedInstanceId(instanceId);
    }
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
  }, [viewerControls, t, segmentationsData, setCurrentSegmentation, currentSegmentation, currentSeries?.file_id, studyInfo, preprocessedInstances]);

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
      <div className="min-h-screen flex flex-col items-center justify-center" style={{ background: '#030712' }}>
        <AlertCircle className="w-16 h-16 text-amber-500 mb-4" />
        <h2 className="text-xl font-bold text-white mb-2">
          {t('viewer.noStudySelected', 'No study selected')}
        </h2>
        <p className="text-gray-400 mb-4 text-center max-w-md">
          {t('viewer.selectStudyDescription', 'Select a patient and upload an MRI study to view it.')}
        </p>
        <button
          onClick={() => navigate('/app')}
          className="flex items-center bg-blue-600 hover:bg-blue-700 text-white transition-colors"
          style={{ height: 36, gap: 6, padding: '0 14px', borderRadius: 6, fontSize: 13, fontWeight: 500 }}
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
      <div className="min-h-screen flex flex-col items-center justify-center" style={{ background: '#030712' }}>
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          className="border-2 border-gray-700 border-t-blue-500 rounded-full mb-4"
          style={{ width: 36, height: 36 }}
        />
        <p className="text-gray-400">{t('viewer.loadingStudy', 'Loading study...')}</p>
      </div>
    );
  }

  // Study error or not found
  if (studyError || (!isLoadingStudy && !studyInfo)) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center" style={{ background: '#030712' }}>
        <AlertCircle className="w-16 h-16 text-red-500 mb-4" />
        <h2 className="text-xl font-bold text-white mb-2">
          {t('viewer.studyNotFound', 'Study not found')}
        </h2>
        <p className="text-gray-400 mb-4">
          {t('viewer.studyNotFoundDescription', 'The requested study does not exist or you do not have access.')}
        </p>
        <button
          onClick={() => navigate('/app')}
          className="flex items-center bg-blue-600 hover:bg-blue-700 text-white transition-colors"
          style={{ height: 36, gap: 6, padding: '0 14px', borderRadius: 6, fontSize: 13, fontWeight: 500 }}
        >
          <ArrowLeft className="w-4 h-4" />
          {t('common.goBack', 'Go Back')}
        </button>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col" style={{ background: '#030712' }}>

      {/* Header — AppHeader with breadcrumbs (same as all other pages) */}
      <AppHeader
        breadcrumbs={[
          { label: t('nav.home', 'Home'), path: '/app' },
          { label: t('patients.title', 'Patients'), path: '/app/patients' },
          ...(patientData ? [{ label: patientData.full_name, path: `/app/patients/${patientData.id}` }] : []),
          { label: studyInfo?.study.study_description || studyInfo?.study.modality || t('viewer.title', 'Viewer') },
        ]}
      />

      {/* Main Content */}
      <div className="relative z-0 flex-1 flex overflow-hidden">
        {/* Study Info & Controls - Left Sidebar */}
        <motion.div
          initial={{ x: -300, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="w-72 flex-shrink-0 flex flex-col border-r border-gray-700 overflow-hidden"
          style={{ background: '#111827' }}
        >
          {/* Study Info — DS: labels 11px UPPERCASE, values 12px */}
          <div className="border-b border-gray-700" style={{ padding: '8px 12px' }}>
            <div className="flex items-center" style={{ gap: 6, marginBottom: 8 }}>
              <FileImage style={{ width: 16, height: 16, color: '#60A5FA' }} />
              <span style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB' }}>
                {t('viewer.studyInfo', 'Study Info')}
              </span>
            </div>
            {studyInfo && (
              <div className="grid grid-cols-2" style={{ gap: 8 }}>
                <div>
                  <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                    {t('study.modality', 'Modality')}
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: '#E5E7EB' }}>{studyInfo.study.modality}</div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                    {t('study.studyDate', 'Date')}
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: '#E5E7EB' }}>{new Date(studyInfo.study.study_date).toLocaleDateString()}</div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                    {t('study.series', 'Series')}
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: '#E5E7EB' }}>{studyInfo.series.length}</div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                    {t('study.images', 'Images')}
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: '#E5E7EB' }}>{originalInstances.length + preprocessedInstances.length}</div>
                </div>
              </div>
            )}
          </div>

          {/* Scrollable content: 3 collapsible sections */}
          <div className="flex-1 overflow-y-auto min-h-0">

            {/* Section 1: Original Images */}
            {originalInstances.length > 0 && (
              <div className="border-b border-gray-700">
                <button
                  onClick={() => toggleSection('originals')}
                  className="w-full flex items-center justify-between hover:bg-gray-800 transition-colors"
                  style={{ padding: '8px 12px' }}
                >
                  <div className="flex items-center" style={{ gap: 6 }}>
                    <FileImage style={{ width: 16, height: 16, color: '#60A5FA' }} />
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB' }}>
                      {t('viewer.originalImages', 'Originals')}
                    </span>
                    <span style={{ fontSize: 10, fontWeight: 500, padding: '1px 6px', borderRadius: 4, background: 'rgba(30,64,175,0.2)', color: '#60A5FA' }}>
                      {originalInstances.length}
                    </span>
                  </div>
                  {sectionsExpanded.originals ? (
                    <ChevronDown style={{ width: 14, height: 14, color: '#6B7280' }} />
                  ) : (
                    <ChevronRight style={{ width: 14, height: 14, color: '#6B7280' }} />
                  )}
                </button>
                {sectionsExpanded.originals && (
                  <div className="px-3 pb-3 space-y-1">
                    {originalInstances.map((instance) => (
                      <button
                        key={instance.id}
                        onClick={() => handleSelectInstance(instance.id)}
                        className={`w-full text-left transition-colors ${
                          selectedInstanceId === instance.id
                            ? 'bg-blue-600 text-white'
                            : 'bg-gray-800/60 hover:bg-gray-800 text-gray-300'
                        }`}
                        style={{ padding: '4px 8px', borderRadius: 6 }}
                      >
                        <div className="flex items-center gap-2">
                          <FileImage className={`w-3.5 h-3.5 flex-shrink-0 ${
                            selectedInstanceId === instance.id ? 'text-white' : 'text-blue-500'
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
              <div className="border-b border-gray-700">
                <button
                  onClick={() => toggleSection('preprocessed')}
                  className="w-full flex items-center justify-between hover:bg-gray-800 transition-colors"
                  style={{ padding: '8px 12px' }}
                >
                  <div className="flex items-center" style={{ gap: 6 }}>
                    <FlaskConical style={{ width: 16, height: 16, color: '#2DD4BF' }} />
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB' }}>
                      {t('viewer.preprocessedImages', 'Preprocessed')}
                    </span>
                    <span style={{ fontSize: 10, fontWeight: 500, padding: '1px 6px', borderRadius: 4, background: 'rgba(13,148,136,0.2)', color: '#2DD4BF' }}>
                      {preprocessedInstances.length}
                    </span>
                  </div>
                  {sectionsExpanded.preprocessed ? (
                    <ChevronDown style={{ width: 14, height: 14, color: '#6B7280' }} />
                  ) : (
                    <ChevronRight style={{ width: 14, height: 14, color: '#6B7280' }} />
                  )}
                </button>
                {sectionsExpanded.preprocessed && (
                  <div className="px-3 pb-3 space-y-1">
                    {preprocessedInstances.map((instance) => (
                      <button
                        key={instance.id}
                        onClick={() => handleSelectInstance(instance.id)}
                        className={`w-full text-left transition-colors ${
                          selectedInstanceId === instance.id
                            ? 'bg-teal-600 text-white'
                            : 'bg-gray-800/60 hover:bg-gray-800 text-gray-300'
                        }`}
                        style={{ padding: '4px 8px', borderRadius: 6 }}
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
            <div className="border-b border-gray-700">
              <button
                onClick={() => toggleSection('segmentations')}
                className="w-full flex items-center justify-between hover:bg-gray-800 transition-colors"
                style={{ padding: '8px 12px' }}
              >
                <div className="flex items-center" style={{ gap: 6 }}>
                  <Puzzle style={{ width: 16, height: 16, color: '#A78BFA' }} />
                  <span style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB' }}>
                    {t('viewer.segmentations', 'Segmentations')}
                  </span>
                  <span style={{
                    fontSize: 10, fontWeight: 500, padding: '1px 6px', borderRadius: 4,
                    background: segmentations.length > 0 ? 'rgba(139,92,246,0.2)' : 'rgba(75,85,99,0.3)',
                    color: segmentations.length > 0 ? '#A78BFA' : '#9CA3AF',
                  }}>
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
                <div style={{ padding: '4px 12px 12px' }}>
                  {/* Action Buttons — L5 outline (functional controls in sidebar) */}
                  <div className="grid grid-cols-2" style={{ gap: 4, marginBottom: 8 }}>
                    <button
                      onClick={handleCreateSegmentation}
                      disabled={!currentSeries}
                      className="flex items-center justify-center border border-gray-600 text-gray-300 hover:bg-gray-700 disabled:opacity-40 transition-colors"
                      style={{ height: 28, gap: 4, borderRadius: 6, fontSize: 12, fontWeight: 500 }}
                      title={t('viewer.createSegmentation', 'Create new segmentation')}
                    >
                      <Plus style={{ width: 12, height: 12 }} />
                      {t('viewer.create', 'Create')}
                    </button>
                    <button
                      onClick={handleUploadSegmentation}
                      disabled={!studyInfo}
                      className="flex items-center justify-center border border-gray-600 text-gray-300 hover:bg-gray-700 disabled:opacity-40 transition-colors"
                      style={{ height: 28, gap: 4, borderRadius: 6, fontSize: 12, fontWeight: 500 }}
                      title={t('viewer.uploadSegmentation', 'Upload segmentation')}
                    >
                      <Upload style={{ width: 12, height: 12 }} />
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
                    <p className="text-xs text-gray-500 text-center py-1">
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
                                className={`cursor-pointer transition-colors ${
                                  isExpanded
                                    ? 'bg-emerald-900/40 border border-emerald-700'
                                    : 'bg-gray-800/60 hover:bg-gray-800 border border-transparent'
                                }`}
                                style={{ borderRadius: 6, padding: '4px 8px' }}
                              >
                                <div className="flex items-center" style={{ gap: 6 }}>
                                  {isExpanded
                                    ? <ChevronDown className="w-3 h-3 flex-shrink-0 text-emerald-400" />
                                    : <ChevronRight className="w-3 h-3 flex-shrink-0 text-gray-400" />
                                  }
                                  <Map className="w-3.5 h-3.5 flex-shrink-0 text-emerald-500" />
                                  <span className={`text-[11px] font-medium truncate flex-1 ${isExpanded ? 'text-white' : 'text-white'}`}>
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
                                    className="p-1 text-gray-500 hover:text-red-400 transition-colors flex-shrink-0"
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
                              className={`cursor-pointer transition-colors ${
                                isActive
                                  ? 'bg-purple-900/50 border border-purple-700'
                                  : 'bg-gray-800/60 hover:bg-gray-800 border border-transparent'
                              }`}
                              style={{ borderRadius: 6, padding: '4px 8px' }}
                            >
                              <div className="flex items-center" style={{ gap: 6 }}>
                                {isExpanded
                                  ? <ChevronDown className="w-3 h-3 flex-shrink-0 text-purple-400" />
                                  : <ChevronRight className="w-3 h-3 flex-shrink-0 text-gray-400" />
                                }
                                <Puzzle className={`w-3.5 h-3.5 flex-shrink-0 ${isActive ? 'text-purple-400' : 'text-purple-500'}`} />
                                <span className={`text-[11px] font-medium truncate flex-1 ${isActive ? 'text-white' : 'text-white'}`}>
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
                                  className="p-1 text-gray-500 hover:text-red-400 transition-colors flex-shrink-0"
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
                                  onNavigateToSlice={(idx) => activeSlice.setSliceIndex(idx)}
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
              className="border-t border-gray-700 overflow-y-auto max-h-[35vh] flex-shrink-0"
              style={{ padding: 8 }}
            >
              <ErrorBoundary name="ViewerControls">
                <ViewerControls
                  {...viewerControls}
                  viewMode={viewMode}
                  onNavigateToSlice={(idx) => activeSlice.setSliceIndex(idx)}
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
          className="flex-1"
        >
          {/* Viewer Toolbar — centered bar with all controls */}
          {viewMode === '2d' && currentSeries && (
            <div className="flex items-center justify-center" style={{ padding: '8px 0' }}>
              <div className="flex items-center border border-gray-700" style={{ background: '#1F2937', borderRadius: 8, padding: 4, gap: 4 }}>
                {/* Layout buttons (only when multiple images) */}
                {(originalInstances.length > 1 || preprocessedInstances.length > 1) && (
                  <>
                    <button onClick={() => handleLayoutChange('single')}
                      className={`flex items-center justify-center transition-colors ${multiLayout === 'single' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
                      style={{ width: 28, height: 28, borderRadius: 6 }} title={t('layout.single', 'Single')}>
                      <Square style={{ width: 14, height: 14 }} />
                    </button>
                    <button onClick={() => handleLayoutChange('1x2')}
                      className={`flex items-center justify-center transition-colors ${multiLayout === '1x2' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
                      style={{ width: 28, height: 28, borderRadius: 6 }} title={t('layout.sideBySide', '1x2')}>
                      <Columns2 style={{ width: 14, height: 14 }} />
                    </button>
                    <button onClick={() => handleLayoutChange('2x2')}
                      className={`flex items-center justify-center transition-colors ${multiLayout === '2x2' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
                      style={{ width: 28, height: 28, borderRadius: 6 }} title={t('layout.grid', '2x2')}>
                      <LayoutGrid style={{ width: 14, height: 14 }} />
                    </button>
                    {isMultiPanel && (
                      <>
                        <div style={{ width: 1, height: 20, background: '#374151' }} />
                        <button onClick={() => setSyncSlice(!syncSlice)}
                          className={`flex items-center justify-center transition-colors ${syncSlice ? 'bg-green-600 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
                          style={{ width: 28, height: 28, borderRadius: 6 }}
                          title={syncSlice ? 'Sync: ON' : 'Sync: OFF'}>
                          {syncSlice ? <Link2 style={{ width: 14, height: 14 }} /> : <Unlink2 style={{ width: 14, height: 14 }} />}
                        </button>
                        {preprocessedInstances.length > 0 && (
                          <button onClick={() => handleMultiPanelSourceChange(multiPanelSource === 'originals' ? 'preprocessed' : 'originals')}
                            className={`flex items-center transition-colors ${multiPanelSource === 'preprocessed' ? 'bg-teal-600 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
                            style={{ height: 28, gap: 4, padding: '0 8px', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>
                            {multiPanelSource === 'preprocessed' ? <FlaskConical style={{ width: 14, height: 14 }} /> : <FileImage style={{ width: 14, height: 14 }} />}
                            {multiPanelSource === 'preprocessed' ? 'Preproc' : 'Original'}
                          </button>
                        )}
                      </>
                    )}
                    <div style={{ width: 1, height: 20, background: '#374151' }} />
                  </>
                )}

                {/* Slice info + slider — reads from active panel in multi-panel mode */}
                <span className="font-mono" style={{ fontSize: 12, fontWeight: 500, color: '#E5E7EB', padding: '0 4px' }}>
                  {activeSlice.sliceIndex + 1}/{activeSlice.totalSlices}
                </span>
                <input
                  type="range"
                  min="0"
                  max={Math.max(0, activeSlice.totalSlices - 1)}
                  value={activeSlice.sliceIndex}
                  onChange={(e) => activeSlice.setSliceIndex(parseInt(e.target.value))}
                  className="h-1 bg-gray-700 rounded-full appearance-none cursor-pointer accent-blue-500"
                  style={{ width: 120 }}
                />

                <div style={{ width: 1, height: 20, background: '#374151' }} />

                {/* Zoom controls */}
                <button onClick={() => setZoomLevel(Math.max(0.25, zoomLevel / 1.2))}
                  className="flex items-center justify-center text-gray-400 hover:bg-gray-700 transition-colors"
                  style={{ width: 28, height: 28, borderRadius: 6 }} title={t('viewer.zoomOut', 'Zoom Out')}>
                  <ZoomOut style={{ width: 14, height: 14 }} />
                </button>
                <span className="font-mono" style={{ fontSize: 11, color: '#9CA3AF', padding: '0 2px', minWidth: 36, textAlign: 'center' }}>
                  {(zoomLevel * 100).toFixed(0)}%
                </span>
                <button onClick={() => setZoomLevel(Math.min(20, zoomLevel * 1.2))}
                  className="flex items-center justify-center text-gray-400 hover:bg-gray-700 transition-colors"
                  style={{ width: 28, height: 28, borderRadius: 6 }} title={t('viewer.zoomIn', 'Zoom In')}>
                  <ZoomIn style={{ width: 14, height: 14 }} />
                </button>
                <button onClick={() => { setZoomLevel(1); setPanOffset({ x: 0, y: 0 }); }}
                  className="flex items-center justify-center text-gray-400 hover:bg-gray-700 transition-colors"
                  style={{ width: 28, height: 28, borderRadius: 6 }} title={t('viewer.resetView', 'Reset')}>
                  <RotateCw style={{ width: 14, height: 14 }} />
                </button>

                <div style={{ width: 1, height: 20, background: '#374151' }} />

                {/* Measurement tools */}
                <button onClick={() => setMeasurementTool(measurementTool === 'ruler' ? null : 'ruler')}
                  className={`flex items-center justify-center transition-colors ${measurementTool === 'ruler' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
                  style={{ width: 28, height: 28, borderRadius: 6 }} title="Ruler">
                  <Ruler style={{ width: 14, height: 14 }} />
                </button>
                <button onClick={() => setMeasurementTool(measurementTool === 'angle' ? null : 'angle')}
                  className={`flex items-center justify-center transition-colors ${measurementTool === 'angle' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
                  style={{ width: 28, height: 28, borderRadius: 6 }} title="Angle">
                  <Triangle style={{ width: 14, height: 14 }} />
                </button>
                <button onClick={() => setMeasurementTool(measurementTool === 'ellipse' ? null : 'ellipse')}
                  className={`flex items-center justify-center transition-colors ${measurementTool === 'ellipse' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
                  style={{ width: 28, height: 28, borderRadius: 6 }} title="ROI">
                  <Circle style={{ width: 14, height: 14 }} />
                </button>
                <button onClick={triggerMeasurementClear}
                  className="flex items-center justify-center text-gray-400 hover:text-red-400 hover:bg-red-900/30 transition-colors"
                  style={{ width: 28, height: 28, borderRadius: 6 }} title={t('viewer.clearMeasurements', 'Clear measurements')}>
                  <Trash2 style={{ width: 14, height: 14 }} />
                </button>
              </div>
            </div>
          )}

          <div className="h-full overflow-hidden" style={{ background: '#000' }}>
            {isLoadingImage && !isMultiPanel ? (
              <div className="h-full flex flex-col items-center justify-center">
                <Loader2 className="animate-spin" style={{ width: 36, height: 36, color: '#60A5FA', marginBottom: 8 }} />
                <p style={{ fontSize: 13, color: '#9CA3AF' }}>{t('viewer.loadingImage')}</p>
              </div>
            ) : isMultiPanel && viewMode === '2d' ? (
              <ErrorBoundary name="MultiPanelViewer">
                <MultiPanelViewer
                  instances={[...originalInstances, ...preprocessedInstances]}
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
          className="w-80 flex-shrink-0 flex flex-col border-l border-gray-700 overflow-hidden"
          style={{ background: '#111827' }}
        >
          {/* MS Report section — collapsible, at the top of right sidebar */}
          <div className="border-b border-gray-700">
            <button
              onClick={() => setReportPanelOpen(!reportPanelOpen)}
              className="w-full flex items-center justify-between hover:bg-gray-800 transition-colors"
              style={{ padding: '8px 12px' }}
            >
              <div className="flex items-center" style={{ gap: 6 }}>
                <FileText style={{ width: 16, height: 16, color: '#FBBF24' }} />
                <span style={{ fontSize: 13, fontWeight: 600, color: '#E5E7EB' }}>{t('report.title', 'MS Report')}</span>
              </div>
              <ChevronDown style={{ width: 14, height: 14, color: '#6B7280', transition: 'transform 0.15s', transform: reportPanelOpen ? 'rotate(180deg)' : 'none' }} />
            </button>
            {reportPanelOpen && (
              <div style={{ padding: '0 12px 12px' }}>
                <AIReportPanel onReportGenerated={(report) => { setReportToView(report); setReportPanelOpen(false); }} />
              </div>
            )}
          </div>

          {/* Main control panel */}
          <div className="flex-1 overflow-hidden">
            <ControlPanel />
          </div>
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
