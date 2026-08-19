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
  const windowCenter = useViewerStore((s) => s.windowCenter);
  const windowWidth = useViewerStore((s) => s.windowWidth);
  const setWindowLevel = useViewerStore((s) => s.setWindowLevel);
  const activeSegmentation = useSegmentationStore((s) => s.activeSegmentation);

  if (!currentSeries) return null;

  // Window/Level (real DICOM VOI-LUT, matplotlib mode). windowWidth>0 = a window is
  // active (server re-renders from raw intensities); 0 = full-range default (unchanged).
  // Seed reference comes from the per-series DICOM tag (MRI has no standardized units, so
  // there are NO fixed T1/T2/FLAIR presets — the correct seed is this scan's own tag).
  const dicomWC = currentSeries.metadata?.window_center;
  const dicomWW = currentSeries.metadata?.window_width;
  const wlActive = windowWidth > 0;
  const wlCenterStr = wlActive ? String(Math.round(windowCenter)) : '';
  const wlWidthStr = wlActive ? String(Math.round(windowWidth)) : '';
  const applyCenter = (raw: string) => {
    const c = parseFloat(raw);
    if (!Number.isNaN(c)) setWindowLevel(c, wlActive ? windowWidth : (dicomWW && dicomWW > 0 ? dicomWW : 1));
  };
  const applyWidth = (raw: string) => {
    const w = parseFloat(raw);
    if (!Number.isNaN(w) && w > 0) setWindowLevel(wlActive ? windowCenter : (dicomWC ?? 0), w);
  };

  return (
    <div style={{ background: '#0E1014', borderRadius: 8, padding: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {/* 2D-only: Render mode toggle and matplotlib controls */}
      {viewMode === '2d' && (
      <div>
        <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('viewer.renderMode')}</label>
        <div className="grid grid-cols-2" style={{ gap: 4 }}>
          <button
            onClick={() => setRenderMode('standard')}
            className={`flex items-center justify-center transition-colors ${
              renderMode === 'standard' ? 'bg-gray-700 text-white border border-gray-600' : 'bg-gray-800 text-gray-400 hover:bg-gray-700 border border-transparent'
            }`}
            style={{ height: 28, borderRadius: 6, fontSize: 12, fontWeight: 500 }}
          >
            {t('viewer.standard')}
          </button>
          <button
            onClick={() => setRenderMode('matplotlib')}
            className={`flex items-center justify-center transition-colors ${
              renderMode === 'matplotlib' ? 'bg-gray-700 text-white border border-gray-600' : 'bg-gray-800 text-gray-400 hover:bg-gray-700 border border-transparent'
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
          {/* Window / Level — real DICOM VOI-LUT (server re-renders from raw intensities).
              Replaces the cosmetic CSS brightness/contrast filter for lesion conspicuity. */}
          <div>
            <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
              <label style={{ fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {t('viewer.windowLevel', 'Window / Level')}
              </label>
              <span style={{ fontSize: 10, color: wlActive ? '#57C7D4' : '#5C6472', fontVariantNumeric: 'tabular-nums' }}>
                {wlActive ? `C ${Math.round(windowCenter)} · A ${Math.round(windowWidth)}` : t('viewer.wlAuto', 'Auto (full range)')}
              </span>
            </div>
            <div className="flex" style={{ gap: 4 }}>
              <input
                type="number" inputMode="numeric" value={wlCenterStr}
                onChange={(e) => applyCenter(e.target.value)}
                placeholder={dicomWC != null ? String(Math.round(dicomWC)) : t('viewer.wlCenter', 'Center')}
                aria-label={t('viewer.wlCenter', 'Window center')}
                className="w-full border border-gray-600 focus:ring-1 focus:ring-blue-500 outline-none"
                style={{ height: 28, padding: '0 8px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 12, fontVariantNumeric: 'tabular-nums' }}
              />
              <input
                type="number" inputMode="numeric" min={1} value={wlWidthStr}
                onChange={(e) => applyWidth(e.target.value)}
                placeholder={dicomWW != null ? String(Math.round(dicomWW)) : t('viewer.wlWidth', 'Width')}
                aria-label={t('viewer.wlWidth', 'Window width')}
                className="w-full border border-gray-600 focus:ring-1 focus:ring-blue-500 outline-none"
                style={{ height: 28, padding: '0 8px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 12, fontVariantNumeric: 'tabular-nums' }}
              />
            </div>
            <div className="grid grid-cols-2" style={{ gap: 4, marginTop: 4 }}>
              <button
                onClick={() => { if (dicomWC != null && dicomWW != null && dicomWW > 0) setWindowLevel(dicomWC, dicomWW); }}
                disabled={dicomWC == null || dicomWW == null || dicomWW <= 0}
                className="flex items-center justify-center bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed border border-gray-600 transition-colors"
                style={{ height: 26, borderRadius: 6, fontSize: 11, fontWeight: 500 }}
                title={t('viewer.wlDicomHint', "Apply this scan's DICOM window")}
              >
                {t('viewer.wlDicom', 'DICOM window')}
              </button>
              <button
                onClick={() => setWindowLevel(0, 0)}
                disabled={!wlActive}
                className="flex items-center justify-center bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed border border-gray-600 transition-colors"
                style={{ height: 26, borderRadius: 6, fontSize: 11, fontWeight: 500 }}
                title={t('viewer.wlResetHint', 'Reset to full-range auto')}
              >
                {t('viewer.wlReset', 'Auto')}
              </button>
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('viewer.colormap')}</label>
            <select
              value={colormap}
              onChange={(e) => setColormap(e.target.value)}
              className="w-full border border-gray-600 focus:ring-1 focus:ring-blue-500 outline-none"
              style={{ height: 28, padding: '0 8px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 12 }}
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
            <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('viewer.xAxis')}</label>
            <div className="flex" style={{ gap: 4 }}>
              <input type="number" placeholder={t('viewer.min')} value={xMin} onChange={(e) => setXMin(e.target.value)}
                className="border border-gray-600 outline-none focus:ring-1 focus:ring-blue-500"
                style={{ width: 64, height: 28, padding: '0 6px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 12 }} />
              <input type="number" placeholder={t('viewer.max')} value={xMax} onChange={(e) => setXMax(e.target.value)}
                className="border border-gray-600 outline-none focus:ring-1 focus:ring-blue-500"
                style={{ width: 64, height: 28, padding: '0 6px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 12 }} />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('viewer.yAxis')}</label>
            <div className="flex" style={{ gap: 4 }}>
              <input type="number" placeholder={t('viewer.min')} value={yMin} onChange={(e) => setYMin(e.target.value)}
                className="border border-gray-600 outline-none focus:ring-1 focus:ring-blue-500"
                style={{ width: 64, height: 28, padding: '0 6px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 12 }} />
              <input type="number" placeholder={t('viewer.max')} value={yMax} onChange={(e) => setYMax(e.target.value)}
                className="border border-gray-600 outline-none focus:ring-1 focus:ring-blue-500"
                style={{ width: 64, height: 28, padding: '0 6px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 12 }} />
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
              ? 'bg-green-900/30 border border-green-700 text-green-400'
              : 'bg-gray-800 hover:bg-gray-700 text-gray-300 border border-transparent'
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
