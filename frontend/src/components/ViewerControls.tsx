import { useTranslation } from 'react-i18next';
import { useViewerStore } from '@/store/useViewerStore';
import { SegmentationPanel } from './SegmentationPanel';
import { BrainVolumetryPanel } from './BrainVolumetryPanel';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { RenderMode } from '@/hooks/useViewerControls';

interface ViewerControlsProps {
  renderMode: RenderMode;
  setRenderMode: (mode: RenderMode) => void;
  colormap: string;
  setColormap: (colormap: string) => void;
  segmentationMode: boolean;
  setSegmentationMode: (mode: boolean) => void;
  xMin: string;
  setXMin: (val: string) => void;
  xMax: string;
  setXMax: (val: string) => void;
  yMin: string;
  setYMin: (val: string) => void;
  yMax: string;
  setYMax: (val: string) => void;
  appliedXMin: string;
  setAppliedXMin: (val: string) => void;
  appliedXMax: string;
  setAppliedXMax: (val: string) => void;
  appliedYMin: string;
  setAppliedYMin: (val: string) => void;
  appliedYMax: string;
  setAppliedYMax: (val: string) => void;
  onNavigateToSlice?: (sliceIndex: number) => void;
  /** Current view mode — controls which sections are visible */
  viewMode?: '2d' | '3d';
}

export default function ViewerControls({
  renderMode,
  setRenderMode,
  colormap,
  setColormap,
  segmentationMode,
  setSegmentationMode,
  xMin,
  setXMin,
  xMax,
  setXMax,
  yMin,
  setYMin,
  yMax,
  setYMax,
  appliedXMin,
  setAppliedXMin,
  appliedXMax,
  setAppliedXMax,
  appliedYMin,
  setAppliedYMin,
  appliedYMax,
  setAppliedYMax,
  onNavigateToSlice,
  viewMode = '2d',
}: ViewerControlsProps) {
  const { t } = useTranslation();
  const { currentSeries, currentPatientId, currentStudyId, currentSeriesId } = useViewerStore();
  const activeSegmentation = useSegmentationStore((s) => s.activeSegmentation);

  if (!currentSeries) return null;

  return (
    <div style={{ background: '#111827', borderRadius: 8, padding: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {/* 2D-only: Render mode toggle and matplotlib controls */}
      {viewMode === '2d' && (
      <div>
        <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('viewer.renderMode')}</label>
        <div className="grid grid-cols-2" style={{ gap: 4 }}>
          <button
            onClick={() => setRenderMode('standard')}
            className={`flex items-center justify-center transition-colors ${
              renderMode === 'standard' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
            style={{ height: 28, borderRadius: 6, fontSize: 12, fontWeight: 500 }}
          >
            {t('viewer.standard')}
          </button>
          <button
            onClick={() => setRenderMode('matplotlib')}
            className={`flex items-center justify-center transition-colors ${
              renderMode === 'matplotlib' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
            style={{ height: 28, borderRadius: 6, fontSize: 12, fontWeight: 500 }}
          >
            {t('viewer.matplotlib')}
          </button>
        </div>
      </div>
      )}

      {viewMode === '2d' && renderMode === 'matplotlib' && (
        <>
          <div>
            <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('viewer.colormap')}</label>
            <select
              value={colormap}
              onChange={(e) => setColormap(e.target.value)}
              className="w-full border border-gray-600 focus:ring-1 focus:ring-blue-500 outline-none"
              style={{ height: 28, padding: '0 8px', borderRadius: 6, background: '#1F2937', color: '#E5E7EB', fontSize: 12 }}
            >
              <option value="gray">{t('viewer.gray')}</option>
              <option value="viridis">{t('viewer.viridis')}</option>
              <option value="plasma">{t('viewer.plasma')}</option>
              <option value="inferno">{t('viewer.inferno')}</option>
              <option value="magma">{t('viewer.magma')}</option>
              <option value="hot">{t('viewer.hot')}</option>
              <option value="cool">{t('viewer.cool')}</option>
              <option value="jet">{t('viewer.jet')}</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('viewer.xAxis')}</label>
            <div className="flex" style={{ gap: 4 }}>
              <input type="number" placeholder={t('viewer.min')} value={xMin} onChange={(e) => setXMin(e.target.value)}
                className="border border-gray-600 outline-none focus:ring-1 focus:ring-blue-500"
                style={{ width: 64, height: 28, padding: '0 6px', borderRadius: 6, background: '#1F2937', color: '#E5E7EB', fontSize: 12 }} />
              <input type="number" placeholder={t('viewer.max')} value={xMax} onChange={(e) => setXMax(e.target.value)}
                className="border border-gray-600 outline-none focus:ring-1 focus:ring-blue-500"
                style={{ width: 64, height: 28, padding: '0 6px', borderRadius: 6, background: '#1F2937', color: '#E5E7EB', fontSize: 12 }} />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('viewer.yAxis')}</label>
            <div className="flex" style={{ gap: 4 }}>
              <input type="number" placeholder={t('viewer.min')} value={yMin} onChange={(e) => setYMin(e.target.value)}
                className="border border-gray-600 outline-none focus:ring-1 focus:ring-blue-500"
                style={{ width: 64, height: 28, padding: '0 6px', borderRadius: 6, background: '#1F2937', color: '#E5E7EB', fontSize: 12 }} />
              <input type="number" placeholder={t('viewer.max')} value={yMax} onChange={(e) => setYMax(e.target.value)}
                className="border border-gray-600 outline-none focus:ring-1 focus:ring-blue-500"
                style={{ width: 64, height: 28, padding: '0 6px', borderRadius: 6, background: '#1F2937', color: '#E5E7EB', fontSize: 12 }} />
            </div>
          </div>

          <div className="grid grid-cols-2" style={{ gap: 4 }}>
            <button
              onClick={() => { setAppliedXMin(xMin); setAppliedXMax(xMax); setAppliedYMin(yMin); setAppliedYMax(yMax); }}
              className="flex items-center justify-center bg-blue-600 hover:bg-blue-700 text-white transition-colors"
              style={{ height: 28, borderRadius: 6, fontSize: 12, fontWeight: 500 }}
            >
              {t('viewer.apply')}
            </button>
            <button
              onClick={() => { setXMin(''); setXMax(''); setYMin(''); setYMax(''); setAppliedXMin(''); setAppliedXMax(''); setAppliedYMin(''); setAppliedYMax(''); }}
              className="flex items-center justify-center bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors"
              style={{ height: 28, borderRadius: 6, fontSize: 12, fontWeight: 500 }}
            >
              {t('viewer.reset')}
            </button>
          </div>
        </>
      )}

      {/* Segmentation Toggle — 28px (sm), radius 6 */}
      <div className="border-t border-gray-700" style={{ paddingTop: 8 }}>
        <button
          onClick={() => setSegmentationMode(!segmentationMode)}
          className={`w-full flex items-center justify-center transition-colors ${
            segmentationMode
              ? 'bg-green-600 hover:bg-green-700 text-white'
              : 'bg-gray-800 hover:bg-gray-700 text-gray-300'
          }`}
          style={{ height: 28, borderRadius: 6, fontSize: 12, fontWeight: 500 }}
        >
          {segmentationMode ? `✓ ${t('viewer.segmentationMode')}` : t('viewer.activateSegmentation')}
        </button>
      </div>

      {/* Segmentation Panel */}
      {segmentationMode && (
        <div className="pt-2 border-t border-gray-700">
          <SegmentationPanel />
        </div>
      )}

      {/* Brain Volumetry Panel (visible only for parcellation segmentations, not lesion masks) */}
      {segmentationMode && activeSegmentation && (() => {
        // Only show volumetry for parcellations (FreeSurfer labels have IDs > 6)
        // Lesion/MAGNIMS masks use labels 0-6 only
        const hasFreeSurferLabels = activeSegmentation.labels?.some(
          (l) => l.id > 6
        );
        return hasFreeSurferLabels;
      })() && (
        <div className="pt-2 border-t border-gray-700">
          <BrainVolumetryPanel
            segmentationId={activeSegmentation.id}
          />
        </div>
      )}


    </div>
  );
}
