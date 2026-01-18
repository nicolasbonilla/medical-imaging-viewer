import { useTranslation } from 'react-i18next';
import { useViewerStore } from '@/store/useViewerStore';
import { SegmentationPanel } from './SegmentationPanel';

interface ViewerControlsProps {
  renderMode: 'standard' | 'matplotlib';
  setRenderMode: (mode: 'standard' | 'matplotlib') => void;
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
}: ViewerControlsProps) {
  const { t } = useTranslation();
  const { currentSeries, currentPatientId, currentStudyId, currentSeriesId } = useViewerStore();

  if (!currentSeries) return null;

  return (
    <div className="bg-gray-900 rounded-lg p-3 space-y-2">
      <div>
        <label className="block text-xs text-gray-300 mb-1">{t('viewer.renderMode')}</label>
        <div className="flex gap-2">
          <button
            onClick={() => setRenderMode('standard')}
            className={`flex-1 px-2 py-1.5 rounded text-xs transition-colors ${
              renderMode === 'standard'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            {t('viewer.standard')}
          </button>
          <button
            onClick={() => {
              console.log('CLICKING MATPLOTLIB BUTTON - changing from', renderMode, 'to matplotlib');
              setRenderMode('matplotlib');
              console.log('setRenderMode called');
            }}
            className={`flex-1 px-2 py-1.5 rounded text-xs transition-colors ${
              renderMode === 'matplotlib'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            {t('viewer.matplotlib')}
          </button>
        </div>
      </div>

      {renderMode === 'matplotlib' && (
        <>
          <div>
            <label className="block text-xs text-gray-300 mb-1">{t('viewer.colormap')}</label>
            <select
              value={colormap}
              onChange={(e) => setColormap(e.target.value)}
              className="w-full px-2 py-1.5 bg-gray-700 text-white rounded text-xs"
            >
              <option value="gray">{t('viewer.gray')}</option>
              <option value="viridis">{t('viewer.viridis')}</option>
              <option value="plasma">{t('viewer.plasma')}</option>
              <option value="inferno">{t('viewer.inferno')}</option>
              <option value="magma">{t('viewer.magma')}</option>
              <option value="hot">{t('viewer.hot')}</option>
              <option value="cool">{t('viewer.cool')}</option>
              <option value="bone">{t('viewer.bone')}</option>
              <option value="jet">{t('viewer.jet')}</option>
            </select>
          </div>

          <div>
            <label className="block text-xs text-gray-300 mb-1">{t('viewer.xAxis')}</label>
            <div className="flex gap-2">
              <input
                type="number"
                placeholder={t('viewer.min')}
                value={xMin}
                onChange={(e) => setXMin(e.target.value)}
                className="w-16 px-1.5 py-1 bg-gray-700 text-white rounded text-xs"
              />
              <input
                type="number"
                placeholder={t('viewer.max')}
                value={xMax}
                onChange={(e) => setXMax(e.target.value)}
                className="w-16 px-1.5 py-1 bg-gray-700 text-white rounded text-xs"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-300 mb-1">{t('viewer.yAxis')}</label>
            <div className="flex gap-2">
              <input
                type="number"
                placeholder={t('viewer.min')}
                value={yMin}
                onChange={(e) => setYMin(e.target.value)}
                className="w-16 px-1.5 py-1 bg-gray-700 text-white rounded text-xs"
              />
              <input
                type="number"
                placeholder={t('viewer.max')}
                value={yMax}
                onChange={(e) => setYMax(e.target.value)}
                className="w-16 px-1.5 py-1 bg-gray-700 text-white rounded text-xs"
              />
            </div>
          </div>

          <div className="flex gap-1">
            <button
              onClick={() => {
                setAppliedXMin(xMin);
                setAppliedXMax(xMax);
                setAppliedYMin(yMin);
                setAppliedYMax(yMax);
              }}
              className="flex-1 px-2 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs transition-colors"
            >
              {t('viewer.apply')}
            </button>
            <button
              onClick={() => {
                setXMin('');
                setXMax('');
                setYMin('');
                setYMax('');
                setAppliedXMin('');
                setAppliedXMax('');
                setAppliedYMin('');
                setAppliedYMax('');
              }}
              className="flex-1 px-2 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs transition-colors"
            >
              {t('viewer.reset')}
            </button>
          </div>
        </>
      )}

      {/* Segmentation Toggle */}
      <div className="pt-2 border-t border-gray-700">
        <button
          onClick={() => setSegmentationMode(!segmentationMode)}
          className={`w-full px-3 py-2 rounded text-sm font-medium transition-colors ${
            segmentationMode
              ? 'bg-green-600 hover:bg-green-700 text-white'
              : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
          }`}
        >
          {segmentationMode ? `✓ ${t('viewer.segmentationMode')}` : `🎨 ${t('viewer.activateSegmentation')}`}
        </button>
      </div>

      {/* Segmentation Panel */}
      {segmentationMode && (
        <div className="pt-2 border-t border-gray-700">
          <SegmentationPanel
            patientId={currentPatientId ?? undefined}
            studyId={currentStudyId ?? undefined}
            seriesId={currentSeriesId ?? undefined}
            totalSlices={currentSeries?.total_slices ?? 1}
            dimensions={currentSeries ? [currentSeries.width, currentSeries.height] : [256, 256]}
          />
        </div>
      )}
    </div>
  );
}
