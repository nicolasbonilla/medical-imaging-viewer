/**
 * ViewerApp — the imaging workspace (v3).
 *
 *   ┌ AppHeader ───────────────────────────────────────────────────────────┐
 *   │ Study rail        │ Toolbar (view · plane · slice · zoom · W/L · …)  │ Insights   │
 *   │  study · images   ├──────────────────────────────────────────────────┤  Image /   │
 *   │  segmentations    │ Viewport (2D in-browser / server fallback / 3D)  │  Analysis /│
 *   │  annotation dock  ├──────────────────────────────────────────────────┤  Report    │
 *   │                   │ Status bar (voxel · value · mm · W/L · zoom)     │            │
 *
 * This file keeps data loading and the cross-panel handlers; presentation lives in
 * components/workspace/*. Behaviour of every handler is unchanged from v2 except where
 * noted (metadata-only image load on the in-browser path; styled delete confirmation).
 */
import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { toast, Toaster } from 'sonner';
import { Images, Puzzle } from 'lucide-react';
import AppHeader from './components/AppHeader';
import ImageViewer2D from './components/ImageViewer2D';
import ImageViewer3D from './components/ImageViewer3D';
import { MultiPanelViewer } from './components/MultiPanelViewer';
import ViewerControls from './components/ViewerControls';
import { imagingAPI } from './api/imaging';
import { studyAPI } from './api/study';
import { useViewerStore } from './store/useViewerStore';
import { useViewerControls, needsServerSlices } from './hooks/useViewerControls';
import type { ImagingStudy, ImagingSeries, ImagingInstance, ReportResponse } from './types';
import { useTheme } from './contexts/ThemeContext';
import { segmentationAPI } from './api/segmentation';
import { usePatient } from './hooks/usePatients';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ReportViewerModal } from './components/ReportViewerModal';
import { useSegmentationStore } from './store/useSegmentationStore';
import { useMultiViewerStore, type ViewerLayout } from './store/useMultiViewerStore';
import { autoAssignPanels, detectSequence } from './utils/sequenceDetection';
import { isPreprocessedInstance } from './utils/instanceClassification';
import { buildSegmentationList, type ViewerSegmentationItem } from './utils/segmentationList';
import { formatDate } from './utils/formatDate';
import { InstanceButton } from './components/viewer/InstanceButton';
import { useActiveSliceInfo } from './hooks/useActiveSliceInfo';
import { WorkspaceToolbar } from './components/workspace/WorkspaceToolbar';
import { ViewerStatusBar } from './components/workspace/ViewerStatusBar';
import { InsightsPanel } from './components/workspace/InsightsPanel';
import { SidebarSection } from './components/workspace/SidebarSection';
import { SegmentationsSection } from './components/workspace/SegmentationsSection';
import { ViewerLoading, ViewerMessage } from './components/workspace/ViewerStates';
import { SliceScrollbar } from './components/workspace/SliceScrollbar';
import type { ClientViewportStatus } from './components/viewer2d/ClientSliceViewport';
import { Badge, Skeleton } from './components/ui';

interface StudyInfo {
  study: ImagingStudy;
  series: ImagingSeries[];
  instances: ImagingInstance[];
}

function ViewerApp() {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const studyId = searchParams.get('studyId');

  const viewMode = useViewerStore((state) => state.viewMode);
  const setViewMode = useViewerStore((state) => state.setViewMode);
  const setCurrentSeries = useViewerStore((state) => state.setCurrentSeries);
  const setIsLoading = useViewerStore((state) => state.setIsLoading);
  const currentSeries = useViewerStore((state) => state.currentSeries);
  const setHierarchicalContext = useViewerStore((state) => state.setHierarchicalContext);
  const setAllFileIds = useViewerStore((state) => state.setAllFileIds);

  // Unified slice info — reads from correct store based on single/multi panel mode
  const activeSlice = useActiveSliceInfo();

  const [selectedInstanceId, setSelectedInstanceId] = useState<string | null>(null);
  const [studyInfo, setStudyInfo] = useState<StudyInfo | null>(null);
  const [deletingSegId, setDeletingSegId] = useState<string | null>(null);
  const [expandedSegIds, setExpandedSegIds] = useState<Set<string>>(new Set());
  const [clientStatus, setClientStatus] = useState<ClientViewportStatus | null>(null);

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

  // Collapsible sections of the study rail
  const [sectionsExpanded, setSectionsExpanded] = useState({ images: true, segmentations: true });

  // Filter instances into groups: originals, preprocessed, masks (hidden).
  // Classification lives in utils/instanceClassification (pure + unit-tested).
  const originalInstances = useMemo(() =>
    studyInfo?.instances.filter((inst) => !isPreprocessedInstance(inst.original_filename || '')) ?? [],
  [studyInfo?.instances]);

  const preprocessedInstances = useMemo(() =>
    studyInfo?.instances.filter((inst) => isPreprocessedInstance(inst.original_filename || '')) ?? [],
  [studyInfo?.instances]);

  // Multi-panel shows the preprocessed set when it has ≥ 2 images (same grid as the
  // masks), otherwise every image of the study.
  const multiPanelInstances = useMemo(() =>
    (preprocessedInstances.length > 1 ? preprocessedInstances : [...originalInstances, ...preprocessedInstances]),
  [originalInstances, preprocessedInstances]);

  // Auto-assign panels when switching to multi-panel layout
  const handleLayoutChange = useCallback((layout: ViewerLayout) => {
    setMultiLayout(layout);
    if (layout !== 'single' && multiPanelInstances.length > 0) {
      const assignments = autoAssignPanels(multiPanelInstances);
      autoAssign(assignments.map((a) => ({ instanceId: a.instance.id, sequence: a.sequence })));
    }
  }, [setMultiLayout, autoAssign, multiPanelInstances]);

  // Collect all file_ids from all instances in the study
  const allFileIds = useMemo(() =>
    studyInfo?.instances.map((inst) => inst.gcs_object_name).filter(Boolean) ?? [],
  [studyInfo?.instances]);

  // Fetch segmentations for ALL images in the study (not just current image)
  const { data: segmentationsData, isLoading: isLoadingSegmentations } = useQuery({
    queryKey: ['segmentations', 'study', studyId],
    queryFn: () => allFileIds.length > 0
      ? segmentationAPI.listSegmentationsByFileIds(allFileIds)
      : Promise.resolve([]),
    enabled: allFileIds.length > 0,
  });

  const segmentations = buildSegmentationList(segmentationsData, t('segmentation.defaultName', 'Segmentation'));

  // Fetch patient info to display name in viewer
  const { data: patientData } = usePatient(studyInfo?.study.patient_id);

  // Load study data when studyId is present
  const { data: loadedStudyInfo, isLoading: isLoadingStudy, error: studyError } = useQuery({
    queryKey: ['study-viewer', studyId],
    queryFn: async (): Promise<StudyInfo | null> => {
      if (!studyId) return null;
      const [study, series] = await Promise.all([
        studyAPI.getById(studyId),
        studyAPI.listSeries(studyId),
      ]);
      const instanceArrays = await Promise.all(series.map((s) => studyAPI.listInstances(s.id)));
      return { study, series, instances: instanceArrays.flat() };
    },
    enabled: !!studyId,
    staleTime: 5 * 60 * 1000,
  });

  // Update state when study data is loaded
  useEffect(() => {
    if (loadedStudyInfo) {
      setStudyInfo(loadedStudyInfo);
      const patientId = loadedStudyInfo.study.patient_id;
      const seriesId = loadedStudyInfo.series.length > 0 ? loadedStudyInfo.series[0].id : null;
      setHierarchicalContext(patientId, studyId, seriesId);
      setAllFileIds(loadedStudyInfo.instances.map((inst) => inst.gcs_object_name).filter(Boolean));
      if (loadedStudyInfo.instances.length > 0 && !selectedInstanceId) {
        setSelectedInstanceId(loadedStudyInfo.instances[0].id);
      }
    }
  }, [loadedStudyInfo, selectedInstanceId, studyId, setHierarchicalContext, setAllFileIds]);

  // Load image when instance is selected. v3: the browser renders 2D slices from the
  // NIfTI itself, so only the server-rendered paths ('standard' / 'matplotlib') need
  // the per-slice PNG payload of /imaging/process; the default path fetches metadata only.
  const pngNeeded = needsServerSlices(viewerControls.renderMode);
  const { refetch: loadImage, isLoading: isLoadingImage } = useQuery({
    queryKey: ['image', selectedInstanceId, pngNeeded],
    queryFn: async () => {
      if (!selectedInstanceId || !studyInfo) return null;
      const selectedInstance = studyInfo.instances.find((inst) => inst.id === selectedInstanceId);
      if (!selectedInstance) {
        console.error('Instance not found:', selectedInstanceId);
        return null;
      }
      setIsLoading(true);
      try {
        const result = pngNeeded
          ? await imagingAPI.processImage(selectedInstance.gcs_object_name, 0, 500)
          : await imagingAPI.getSeriesMetadata(selectedInstance.gcs_object_name);
        // Add the file_id to the result so the 2D/3D viewers can fetch the volume
        const resultWithFileId = { ...result, file_id: selectedInstance.gcs_object_name };
        setCurrentSeries(resultWithFileId);
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
    staleTime: 10 * 60 * 1000,
  });

  useEffect(() => {
    if (selectedInstanceId) loadImage();
  }, [selectedInstanceId, loadImage, pngNeeded]);

  // Auto-load zone map when a lesion segmentation references one via analysis_data.
  useEffect(() => {
    const segId = currentSegmentation?.segmentation_id;
    if (!segId) return;
    if (currentSegmentation?.metadata?.description === 'MAGNIMS Zone Map') return;
    const zoneMapSegId = currentSegmentation?.metadata?.analysis_data?.zone_map_seg_id;
    if (!zoneMapSegId) return;
    if (useSegmentationStore.getState().zoneMapSegId === zoneMapSegId) return;
    segmentationAPI.loadZoneMapMask(zoneMapSegId)
      .then(({ mask, depth, height, width }) => {
        useSegmentationStore.getState().setZoneMap(zoneMapSegId, mask, { depth, height, width });
      })
      .catch(() => console.warn('[ViewerApp] Referenced zone map not found'));
  }, [currentSegmentation?.segmentation_id, currentSegmentation?.metadata?.analysis_data?.zone_map_seg_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSelectInstance = (instanceId: string) => {
    if (isMultiPanel) {
      // Multi-panel: assign the clicked image to the active (focused) panel
      const instance = studyInfo?.instances.find((i) => i.id === instanceId);
      const sequence = instance ? detectSequence(instance.original_filename || '') : 'unknown';
      assignInstance(activePanelId, instanceId, sequence);
    } else {
      setSelectedInstanceId(instanceId);
    }
  };

  // Open/close an existing segmentation (click again to deactivate)
  const handleOpenSegmentation = useCallback((segmentation: { id: string; name: string; fileId?: string }) => {
    if (currentSegmentation?.segmentation_id === segmentation.id) {
      setCurrentSegmentation(null);
      viewerControls.setSegmentationMode(false);
      return;
    }
    const fullSeg = segmentationsData?.find((s) => s.segmentation_id === segmentation.id);
    if (!fullSeg) return;
    // Segmentations are in the preprocessed space — switch to a preprocessed image if needed.
    const currentFilename = studyInfo?.instances.find(
      (inst) => inst.gcs_object_name === currentSeries?.file_id,
    )?.original_filename || '';
    if (!isPreprocessedInstance(currentFilename) && preprocessedInstances.length > 0) {
      setSelectedInstanceId(preprocessedInstances[0].id);
    }
    setCurrentSegmentation(fullSeg);
    viewerControls.setSegmentationMode(true);
    toast.success(t('viewer.segmentationLoaded', `Segmentation "${segmentation.name}" loaded`));
  }, [viewerControls, t, segmentationsData, setCurrentSegmentation, currentSegmentation, currentSeries?.file_id, studyInfo, preprocessedInstances]);

  const toggleSegExpanded = useCallback((segId: string) => {
    setExpandedSegIds((prev) => {
      const next = new Set(prev);
      if (next.has(segId)) next.delete(segId);
      else next.add(segId);
      return next;
    });
  }, []);

  // MAGNIMS Zone Map — independent layer; does NOT set currentSegmentation.
  const handleToggleZoneMap = useCallback((seg: { id: string; name: string }) => {
    toggleSegExpanded(seg.id);
    const store = useSegmentationStore.getState();
    if (store.zoneMapSegId === seg.id) {
      store.toggleZoneMapVisibility();
      return;
    }
    segmentationAPI.loadZoneMapMask(seg.id)
      .then(({ mask, depth, height, width }) => {
        useSegmentationStore.getState().setZoneMap(seg.id, mask, { depth, height, width });
        useSegmentationStore.setState({ zoneMapVisible: true });
      })
      .catch(() => console.warn('[ViewerApp] Zone map mask not found'));
  }, [toggleSegExpanded]);

  const handleUploadSegmentation = useCallback(() => {
    segmentationUploadRef.current?.click();
  }, []);

  const handleSegmentationFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // IMPORTANT (Class C integrity): mask import is NOT implemented — there is no
    // segmentationAPI.importSegmentation endpoint. Report the true state — never a
    // false success. The Upload button is also disabled.
    if (segmentationUploadRef.current) segmentationUploadRef.current.value = '';
    if (!file) return;
    toast.error(
      t('viewer.segmentationImportUnavailable', 'Importing a segmentation is not available yet — nothing was uploaded.'),
      { id: 'upload-seg' },
    );
  }, [t]);

  const deleteSegmentation = useCallback(async (segId: string) => {
    setDeletingSegId(segId);
    try {
      await segmentationAPI.deleteSegmentation(segId);
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

  // Delete asks for an explicit confirmation (styled toast with Delete / Cancel instead of
  // the native OS dialog; ignoring it cancels — nothing is deleted without the click).
  const handleDeleteSegmentation = useCallback((segId: string, segName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    toast(t('viewer.confirmDeleteSegmentation', `Delete segmentation "${segName}"?`), {
      id: `confirm-delete-${segId}`,
      action: { label: t('segmentation.list.delete', 'Delete'), onClick: () => { void deleteSegmentation(segId); } },
      cancel: { label: t('common.cancel', 'Cancel'), onClick: () => {} },
      duration: 8000,
    });
  }, [deleteSegmentation, t]);

  // Create a new segmentation (local-first) and enter paint mode
  const handleCreateSegmentation = useCallback(() => {
    if (!currentSeries) {
      toast.error(t('viewer.noImageLoaded', 'Load an image first'));
      return;
    }
    viewerControls.setSegmentationMode(true);
    setIsPaintMode(true);
    if (createSegmentationRef.current) {
      createSegmentationRef.current();
      toast.info(t('viewer.segmentationModeActivated', 'Segmentation mode activated. Use the drawing tools.'));
    } else {
      toast.error(t('viewer.segmentationCreationFailed', 'Failed to create segmentation'));
    }
  }, [viewerControls, t, currentSeries, setIsPaintMode]);

  // Lesion dashboard row → slice. On the in-browser path the viewport also centres all
  // three planes on the lesion centroid (selectedLesion), so any plane shows it.
  const handleNavigateToSlice = useCallback((idx: number) => {
    if (viewerControls.renderMode === 'client' && !isMultiPanel) {
      useViewerStore.getState().requestFocus(idx);
    } else {
      activeSlice.setSliceIndex(idx);
    }
  }, [viewerControls.renderMode, isMultiPanel, activeSlice]);

  // ---- route states -----------------------------------------------------------------
  if (!studyId) {
    return (
      <ViewerMessage tone="warn"
        title={t('viewer.noStudySelected', 'No study selected')}
        body={t('viewer.selectStudyDescription', 'Select a patient and upload an MRI study to view it.')}
        actionLabel={t('viewer.goToPatients', 'Go to Patients')}
        onAction={() => navigate('/app')} />
    );
  }
  if (isLoadingStudy) return <ViewerLoading />;
  if (studyError || (!isLoadingStudy && !studyInfo)) {
    return (
      <ViewerMessage tone="crit"
        title={t('viewer.studyNotFound', 'Study not found')}
        body={t('viewer.studyNotFoundDescription', 'The requested study does not exist or you do not have access.')}
        actionLabel={t('common.goBack', 'Go Back')}
        onAction={() => navigate('/app')} />
    );
  }

  const study = studyInfo!.study;
  const imageCount = originalInstances.length + preprocessedInstances.length;
  const layoutAvailable = multiPanelInstances.length > 1;

  return (
    <div className="flex h-screen flex-col bg-surface-void">
      <AppHeader
        breadcrumbs={[
          { label: t('nav.home', 'Home'), path: '/app' },
          { label: t('patients.title', 'Patients'), path: '/app/patients' },
          ...(patientData ? [{ label: patientData.full_name, path: `/app/patients/${patientData.id}` }] : []),
          { label: study.study_description || study.modality || t('viewer.title', 'Viewer') },
        ]}
      />

      <div className="relative z-0 flex min-h-0 flex-1">
        {/* ── Study rail ─────────────────────────────────────────────── */}
        <aside
          aria-label={t('viewer3.studyRail', 'Study')}
          className="flex w-[316px] shrink-0 flex-col border-r border-surface-border bg-surface-base"
        >
          <div className="border-b border-surface-border p-3">
            <div className="flex items-start gap-2.5">
              <Badge tone="brand" className="mt-0.5 shrink-0">{study.modality}</Badge>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-ink-base" title={study.study_description}>
                  {study.study_description || t('viewer.studyInfo', 'Study Info')}
                </p>
                <p className="mt-0.5 text-xs tabular-nums text-ink-muted">
                  {formatDate(study.study_date)}
                  {' · '}{t('viewer3.seriesCount', '{{count}} series', { count: studyInfo!.series.length })}
                  {' · '}{t('viewer3.imagesCount', '{{count}} images', { count: imageCount })}
                </p>
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            <SidebarSection
              title={t('viewer3.images', 'Images')}
              icon={<Images className="h-4 w-4" />}
              count={imageCount}
              open={sectionsExpanded.images}
              onToggle={() => setSectionsExpanded((s) => ({ ...s, images: !s.images }))}
            >
              <div className="space-y-3">
                {[
                  { key: 'original', label: t('viewer.originalImages', 'Originals'), list: originalInstances },
                  { key: 'preprocessed', label: t('viewer.preprocessedImages', 'Preprocessed'), list: preprocessedInstances },
                ].filter((g) => g.list.length > 0).map((g) => (
                  <div key={g.key}>
                    <p className="mb-1.5 text-xs text-ink-faint">{g.label}</p>
                    <ul className="space-y-1">
                      {g.list.map((instance) => (
                        <li key={instance.id}>
                          <InstanceButton
                            instance={instance}
                            selected={selectedInstanceId === instance.id}
                            onSelect={handleSelectInstance}
                            variant={g.key as 'original' | 'preprocessed'}
                          />
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </SidebarSection>

            <SidebarSection
              title={t('viewer.segmentations', 'Segmentations')}
              icon={<Puzzle className="h-4 w-4" />}
              count={segmentations.length}
              open={sectionsExpanded.segmentations}
              onToggle={() => setSectionsExpanded((s) => ({ ...s, segmentations: !s.segmentations }))}
            >
              <SegmentationsSection
                segmentations={segmentations as ViewerSegmentationItem[]}
                isLoading={isLoadingSegmentations}
                activeIds={{ current: currentSegmentation?.segmentation_id, active: activeSegmentation?.id }}
                expandedSegIds={expandedSegIds}
                setExpandedSegIds={setExpandedSegIds}
                deletingSegId={deletingSegId}
                isOverlayVisible={isOverlayVisible}
                zoneMapVisible={zoneMapVisible}
                canCreate={!!currentSeries}
                onCreate={handleCreateSegmentation}
                onUpload={handleUploadSegmentation}
                onOpen={handleOpenSegmentation}
                onToggleZoneMap={handleToggleZoneMap}
                onDelete={handleDeleteSegmentation}
                currentFileId={currentSeries?.file_id}
                onNavigateToSlice={handleNavigateToSlice}
              />
              <input
                ref={segmentationUploadRef}
                type="file"
                accept=".nii,.nii.gz,.nrrd,.seg.nrrd"
                className="hidden"
                onChange={handleSegmentationFileChange}
              />
            </SidebarSection>
          </div>
        </aside>

        {/* ── Viewport column (main content target of the WCAG 2.4.1 skip link) ── */}
        <main id="main-content" tabIndex={-1} className="flex min-w-0 flex-1 flex-col focus:outline-none">
          <WorkspaceToolbar
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            renderMode={viewerControls.renderMode}
            onRenderModeChange={viewerControls.setRenderMode}
            clientStatus={clientStatus}
            serverSeed={{ center: currentSeries?.metadata?.window_center, width: currentSeries?.metadata?.window_width }}
            layoutAvailable={layoutAvailable}
            layout={multiLayout}
            onLayoutChange={handleLayoutChange}
            syncSlice={syncSlice}
            onSyncChange={setSyncSlice}
          />
          <div className="relative min-h-0 flex-1 overflow-hidden bg-black">
            {isLoadingImage && !isMultiPanel ? (
              <div className="grid h-full place-items-center" role="status" aria-live="polite">
                <div className="flex flex-col items-center gap-3">
                  <Skeleton className="aspect-square w-[min(48vh,520px)] rounded-3xl" />
                  <p className="text-xs text-ink-muted">{t('viewer.loadingImage', 'Loading image…')}</p>
                </div>
              </div>
            ) : isMultiPanel && viewMode === '2d' ? (
              <ErrorBoundary name="MultiPanelViewer">
                <MultiPanelViewer
                  instances={[...originalInstances, ...preprocessedInstances]}
                  renderMode={viewerControls.renderMode}
                  patientName={patientData?.full_name}
                  patientMRN={patientData?.mrn}
                  studyDescription={study.study_description}
                />
              </ErrorBoundary>
            ) : viewMode === '2d' ? (
              <ErrorBoundary name="ImageViewer2D">
                <SliceScrollbar />
                <ImageViewer2D
                  viewerControls={viewerControls}
                  createSegmentationRef={createSegmentationRef}
                  patientName={patientData?.full_name}
                  patientMRN={patientData?.mrn}
                  studyDescription={study.study_description}
                  studyModality={study.modality}
                  onClientStatus={setClientStatus}
                />
              </ErrorBoundary>
            ) : (
              <ErrorBoundary name="ImageViewer3D">
                <ImageViewer3D
                  patientName={patientData?.full_name}
                  patientMRN={patientData?.mrn}
                  studyDescription={study.study_description}
                />
              </ErrorBoundary>
            )}
          </div>
          <ViewerStatusBar renderMode={viewerControls.renderMode} clientStatus={clientStatus} viewMode={viewMode} />
        </main>

        {/* ── Insights ───────────────────────────────────────────────── */}
        <aside
          aria-label={t('viewer3.insights', 'Image and analysis')}
          className="w-[300px] shrink-0 border-l border-surface-border bg-surface-base"
        >
          <InsightsPanel
            renderMode={viewerControls.renderMode}
            clientStatus={clientStatus}
            onReportGenerated={(report) => setReportToView(report)}
            segmentationMode={viewerControls.segmentationMode}
            annotate={currentSeries ? (
              <ErrorBoundary name="ViewerControls">
                <ViewerControls
                  {...viewerControls}
                  viewMode={viewMode}
                  onNavigateToSlice={handleNavigateToSlice}
                />
              </ErrorBoundary>
            ) : (
              <p className="text-xs text-ink-muted">{t('viewer.selectImageToView', 'Select an image to view')}</p>
            )}
          />
        </aside>
      </div>

      <Toaster position="top-right" theme={theme === 'dark' ? 'dark' : 'light'} richColors closeButton expand={false} />

      {reportToView && (
        <ReportViewerModal
          report={reportToView}
          isOpen={!!reportToView}
          onClose={() => setReportToView(null)}
          patientName={patientData?.full_name}
          patientMRN={patientData?.mrn}
          patientAge={patientData?.age}
          patientSex={patientData?.gender === 'male' ? 'M' : patientData?.gender === 'female' ? 'F' : undefined}
          studyDate={study.study_date}
          studyDescription={study.study_description}
          institutionName={study.institution_name}
        />
      )}
    </div>
  );
}

export default ViewerApp;
