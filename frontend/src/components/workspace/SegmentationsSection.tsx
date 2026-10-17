/**
 * Segmentations group of the study rail (moved out of ViewerApp, v3). Rendering only:
 * every action is the ViewerApp handler it always was (open/close, zone-map layer,
 * delete with confirmation, create local-first). Loading uses skeleton rows.
 */
import { useTranslation } from 'react-i18next';
import { Map, Plus, Puzzle, Upload } from 'lucide-react';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { ViewerSegmentationItem } from '@/utils/segmentationList';
import { SegmentationRow } from '../viewer/SegmentationRow';
import { LesionDashboard } from '../LesionDashboard';
import { MAGNIMSZoneMapPanel } from '../MAGNIMSZoneMapPanel';
import { OverlayControls } from './OverlayControls';
import { Button, SkeletonRows } from '../ui';

const ZONE_MAP_NAME = 'MAGNIMS Zone Map';

export interface SegmentationsSectionProps {
  segmentations: ViewerSegmentationItem[];
  isLoading: boolean;
  activeIds: { current?: string | null; active?: string | null };
  expandedSegIds: Set<string>;
  setExpandedSegIds: (fn: (prev: Set<string>) => Set<string>) => void;
  deletingSegId: string | null;
  isOverlayVisible: boolean;
  zoneMapVisible: boolean;
  canCreate: boolean;
  onCreate: () => void;
  onUpload: () => void;
  onOpen: (seg: ViewerSegmentationItem) => void;
  onToggleZoneMap: (seg: ViewerSegmentationItem) => void;
  onDelete: (id: string, name: string, e: React.MouseEvent) => void;
  currentFileId?: string;
  onNavigateToSlice: (idx: number) => void;
}

export function SegmentationsSection({
  segmentations, isLoading, activeIds, expandedSegIds, setExpandedSegIds, deletingSegId,
  isOverlayVisible, zoneMapVisible, canCreate, onCreate, onUpload, onOpen, onToggleZoneMap, onDelete,
  currentFileId, onNavigateToSlice,
}: SegmentationsSectionProps) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2.5">
      <div className="grid grid-cols-2 gap-1.5">
        <Button size="sm" variant="secondary" onClick={onCreate} disabled={!canCreate}
          leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden />}
          aria-label={t('viewer.createSegmentation', 'Create new segmentation')}
          title={t('viewer.createSegmentation', 'Create new segmentation')}>
          {t('viewer.create', 'Create')}
        </Button>
        <Button size="sm" variant="ghost" onClick={onUpload} disabled
          leftIcon={<Upload className="h-3.5 w-3.5" aria-hidden />}
          aria-label={t('viewer.uploadSegmentationSoon', 'Import segmentation (coming soon)')}
          title={t('viewer.uploadSegmentationSoon', 'Import segmentation (coming soon)')}>
          {t('viewer.upload', 'Upload')}
        </Button>
      </div>

      {isLoading ? (
        <SkeletonRows rows={2} cols={2} />
      ) : segmentations.length === 0 ? (
        <p className="py-1 text-center text-xs text-ink-faint">{t('viewer.noSegmentations', 'No segmentations')}</p>
      ) : (
        <ul className="space-y-1.5">
          {segmentations.map((seg) => {
            const isZoneMap = seg.name === ZONE_MAP_NAME;
            const isActive = activeIds.current === seg.id || activeIds.active === seg.id;
            const isExpanded = expandedSegIds.has(seg.id);
            const isDeleting = deletingSegId === seg.id;
            const isSaved = !seg.id.startsWith('local-');

            if (isZoneMap) {
              // MAGNIMS zone map: an independent layer, NOT tied to currentSegmentation.
              return (
                <li key={seg.id}>
                  <SegmentationRow
                    name={seg.name}
                    icon={Map}
                    accent="emerald"
                    highlighted={isExpanded}
                    expanded={isExpanded}
                    overlayOn={zoneMapVisible}
                    isDeleting={isDeleting}
                    onRowClick={() => onToggleZoneMap(seg)}
                    onToggleOverlay={(e) => {
                      e.stopPropagation();
                      useSegmentationStore.getState().toggleZoneMapVisibility();
                    }}
                    onDelete={(e) => onDelete(seg.id, seg.name, e)}
                  />
                  {isExpanded && isSaved && (
                    <div className="mt-2">
                      <MAGNIMSZoneMapPanel fileId={currentFileId} />
                    </div>
                  )}
                </li>
              );
            }

            // Regular segmentation (expert rater, tool output, manual…)
            return (
              <li key={seg.id}>
                <SegmentationRow
                  name={seg.name}
                  icon={Puzzle}
                  accent="purple"
                  origin={seg.origin}
                  highlighted={isActive}
                  expanded={isExpanded}
                  overlayOn={isActive && isOverlayVisible}
                  isDeleting={isDeleting}
                  onRowClick={() => {
                    onOpen(seg);
                    // Auto-expand on activate, collapse on deactivate
                    if (isActive) {
                      setExpandedSegIds((prev) => { const n = new Set(prev); n.delete(seg.id); return n; });
                    } else {
                      setExpandedSegIds((prev) => new Set(prev).add(seg.id));
                    }
                  }}
                  onToggleOverlay={(e) => {
                    e.stopPropagation();
                    if (isActive) {
                      useSegmentationStore.getState().setIsOverlayVisible(!isOverlayVisible);
                    } else {
                      onOpen(seg);
                      setExpandedSegIds((prev) => new Set(prev).add(seg.id));
                    }
                  }}
                  onDelete={(e) => onDelete(seg.id, seg.name, e)}
                />
                {isExpanded && isSaved && (
                  <div className="mt-2 space-y-2.5">
                    <OverlayControls />
                    <LesionDashboard segmentationId={seg.id} onNavigateToSlice={onNavigateToSlice} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default SegmentationsSection;
