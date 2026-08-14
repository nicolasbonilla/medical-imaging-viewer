import { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import {
  Calendar, Activity, ChevronDown, ChevronRight,
  Layers, ZoomIn, ZoomOut, RotateCcw, Box, Info, Scissors, Palette
} from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { usePatient, useMedicalHistory } from '@/hooks/usePatients';
import { studyAPI } from '@/api/study';
import { COLORMAPS_3D } from '@/components/ImageViewer3D';
import type { StudySummary, ImageOrientation } from '@/types';
import { formatDate as formatLocalizedDate } from '@/utils/formatDate';
import { LongitudinalCompare } from './LongitudinalCompare';
import { SegmentationComparison } from './SegmentationComparison';

export default function ControlPanel() {
  const { t } = useTranslation();
  const {
    viewMode,
    setViewMode,
    orientation,
    setOrientation,
    currentSeries,
    currentSliceIndex,
    setCurrentSliceIndex,
    zoomLevel,
    setZoomLevel,
    panOffset,
    setPanOffset,
    brightness,
    contrast,
    setBrightness,
    setContrast,
    resetImageAdjustments,
    cursorInfo,
    sliceHistogram,
    currentPatientId,
    currentStudyId,
    render3DMode,
    colormap3D,
    clipPlaneEnabled,
    clipPlanePosition,
    setRender3DMode,
    setColormap3D,
    setClipPlane,
    clipPlaneAxis,
    setClipPlaneAxis,
  } = useViewerStore();

  const [imageInfoOpen, setImageInfoOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [timelineOpen, setTimelineOpen] = useState(true);
  const totalSlices = currentSeries?.total_slices ?? currentSeries?.metadata?.slices ?? 1;

  // Fetch patient data
  const { data: patient } = usePatient(currentPatientId ?? undefined);

  // Fetch medical history
  const { data: medicalHistory } = useMedicalHistory(currentPatientId ?? undefined);

  // Fetch all studies for this patient (for timeline)
  const { data: patientStudies } = useQuery({
    queryKey: ['studies', 'patient', currentPatientId],
    queryFn: async () => {
      if (!currentPatientId) return [] as StudySummary[];
      const result = await studyAPI.listByPatient(currentPatientId);
      return result.items;
    },
    enabled: !!currentPatientId,
  });

  // Sort studies by date (newest first)
  const sortedStudies = (patientStudies ?? [])
    .sort((a, b) => new Date(b.study_date).getTime() - new Date(a.study_date).getTime());

  const activeConditions = (medicalHistory ?? []).filter((h) => h.is_active);

  const handleZoomIn = useCallback(() => {
    const step = Math.max(0.25, Math.round(zoomLevel * 0.25 * 4) / 4);
    setZoomLevel(Math.min(zoomLevel + step, 20));
  }, [zoomLevel, setZoomLevel]);

  const handleZoomOut = useCallback(() => {
    const step = Math.max(0.25, Math.round(zoomLevel * 0.25 * 4) / 4);
    setZoomLevel(Math.max(zoomLevel - step, 0.25));
  }, [zoomLevel, setZoomLevel]);

  const handleResetView = useCallback(() => {
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
    resetImageAdjustments();
  }, [setZoomLevel, setPanOffset, resetImageAdjustments]);

  const formatDate = (dateStr: string) => {
    try {
      return formatLocalizedDate(dateStr);
    } catch {
      return dateStr;
    }
  };

  const getSeverityColor = (severity?: string) => {
    switch (severity) {
      case 'severe': return 'text-red-400 bg-red-900/30 border-red-800/50';
      case 'moderate': return 'text-yellow-400 bg-yellow-900/30 border-yellow-800/50';
      case 'mild': return 'text-green-400 bg-green-900/30 border-green-800/50';
      default: return 'text-gray-400 bg-gray-800/30 border-gray-700/50';
    }
  };

  return (
    <div className="h-full flex flex-col overflow-hidden" style={{ background: '#111827' }}>
      {/* Content */}
      <div className="flex-1 overflow-y-auto">

        {/* Patient Info removed — already in breadcrumbs and PatientDetailPage */}

        {/* Medical History removed — belongs in PatientDetailPage, not in the viewer */}

        {/* Study Timeline removed — already in PatientDetailPage */}

        {/* Longitudinal Tracking (below timeline) */}
        {sortedStudies.length > 1 && (
          <div className="border-b border-gray-700" style={{ padding: '8px 12px' }}>
            <LongitudinalCompare studies={sortedStudies} />
          </div>
        )}

        {/* Segmentation comparison (Dice + lesion-wise detection F1) — self-hides
            unless the current study has ≥2 segmentations to compare. */}
        <div className="border-b border-gray-700" style={{ padding: '8px 12px' }}>
          <SegmentationComparison />
        </div>

        {/* View Controls (compact) */}
        <div className="border-b border-gray-700" style={{ padding: '8px 12px', display: 'flex', flexDirection: 'column' as const, gap: 12 }}>
          {/* View Mode Toggle */}
          <div>
            <label className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              <Box className="w-3.5 h-3.5" />
              {t('viewer.viewMode')}
            </label>
            <div className="grid grid-cols-2 gap-1" style={{ gap: 4 }}>
              {(['2d', '3d'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={`flex items-center justify-center h-7 text-xs font-medium transition-colors ${
                    viewMode === mode
                      ? 'bg-gray-700 text-white border border-gray-600'
                      : 'bg-gray-800 text-gray-400 hover:bg-gray-700 border border-transparent'
                  }`}
                  style={{ borderRadius: 6 }}
                >
                  {t(`viewer.${mode}View`).toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* 3D Render Mode */}
          {viewMode === '3d' && (
            <div className="space-y-3">
              {/* Render mode toggle */}
              <div>
                <label className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                  <Layers className="w-3.5 h-3.5" />
                  {t('viewer.renderMode', 'Render Mode')}
                </label>
                <div className="grid grid-cols-2 gap-1.5">
                  <button
                    onClick={() => setRender3DMode('volume')}
                    className={`flex items-center justify-center h-7 rounded-[6px] text-xs font-medium transition-all ${
                      render3DMode === 'volume'
                        ? 'bg-gray-700 text-white border border-gray-600'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    {t('viewer.volumeRender', 'Volume')}
                  </button>
                  <button
                    onClick={() => setRender3DMode('multiplanar')}
                    className={`flex items-center justify-center h-7 rounded-[6px] text-xs font-medium transition-all ${
                      render3DMode === 'multiplanar'
                        ? 'bg-gray-700 text-white border border-gray-600'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    {t('viewer.multiplanar', 'Multiplanar')}
                  </button>
                </div>
              </div>

              {/* Colormap selector */}
              <div>
                <label className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                  <Palette className="w-3.5 h-3.5" />
                  {t('viewer.colormap', 'Colormap')}
                </label>
                <select
                  value={colormap3D}
                  onChange={(e) => setColormap3D(e.target.value)}
                  className="w-full border border-gray-600 focus:ring-1 focus:ring-blue-500 outline-none"
                  style={{ height: 28, padding: '0 8px', borderRadius: 6, background: '#1F2937', color: '#E5E7EB', fontSize: 12 }}
                >
                  {COLORMAPS_3D.map((cm) => (
                    <option key={cm.id} value={cm.id}>{cm.label}</option>
                  ))}
                </select>
              </div>

              {/* Clip plane */}
              <div>
                <label className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                  <Scissors className="w-3.5 h-3.5" />
                  {t('viewer.clipPlane', 'Clip Plane')}
                </label>
                <div className="space-y-1.5">
                  <button
                    onClick={() => setClipPlane(!clipPlaneEnabled)}
                    className={`w-full flex items-center justify-center h-7 rounded-[6px] text-xs font-medium transition-colors ${
                      clipPlaneEnabled
                        ? 'bg-red-600 text-white'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    {clipPlaneEnabled ? t('viewer.clipPlaneOn', 'Clip: ON') : t('viewer.clipPlaneOff', 'Clip: OFF')}
                  </button>
                  {clipPlaneEnabled && (
                    <>
                      {/* Axis selector */}
                      <div className="grid grid-cols-3 gap-1">
                        {(['axial', 'coronal', 'sagittal'] as const).map((axis) => (
                          <button
                            key={axis}
                            onClick={() => setClipPlaneAxis(axis)}
                            className={`flex items-center justify-center h-6 rounded text-[10px] font-medium transition-colors ${
                              clipPlaneAxis === axis
                                ? 'bg-red-600 text-white'
                                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                            }`}
                          >
                            {t(`viewer.clipAxis.${axis}`, axis.charAt(0).toUpperCase() + axis.slice(1))}
                          </button>
                        ))}
                      </div>
                      {/* Depth slider */}
                      <div>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          value={Math.round(clipPlanePosition * 100)}
                          onChange={(e) => setClipPlane(true, parseInt(e.target.value) / 100)}
                          className="w-full h-1.5 bg-gray-700 rounded-full appearance-none cursor-pointer accent-red-500"
                        />
                        <div className="text-[10px] text-gray-400 text-right mt-0.5">
                          {Math.round(clipPlanePosition * 100)}%
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Slice Navigator */}
          {viewMode === '2d' && currentSeries && totalSlices > 1 && (
            <div>
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="font-semibold text-gray-400 flex items-center gap-1">
                  <Layers className="w-3 h-3" />
                  {t('viewer.slice', 'Slice')}
                </span>
                <span className="font-mono font-bold text-gray-300">
                  {currentSliceIndex + 1} / {totalSlices}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={totalSlices - 1}
                value={currentSliceIndex}
                onChange={(e) => setCurrentSliceIndex(Number(e.target.value))}
                className="w-full h-1.5 bg-gray-700 rounded-full appearance-none cursor-pointer accent-blue-500"
              />
            </div>
          )}

          {/* Zoom + Reset (compact row) */}
          {currentSeries && (
            <div className="flex items-center" style={{ gap: 4 }}>
              <button
                onClick={handleZoomOut}
                disabled={zoomLevel <= 0.25}
                className="flex items-center justify-center bg-gray-800 hover:bg-gray-700 disabled:opacity-30 transition-colors"
                style={{ width: 28, height: 28, borderRadius: 6 }}
              >
                <ZoomOut style={{ width: 14, height: 14, color: '#9CA3AF' }} />
              </button>
              <span className="font-mono" style={{ fontSize: 11, fontWeight: 600, color: '#E5E7EB', width: 48, textAlign: 'center' }}>
                {Math.round(zoomLevel * 100)}%
              </span>
              <button
                onClick={handleZoomIn}
                disabled={zoomLevel >= 20}
                className="flex items-center justify-center bg-gray-800 hover:bg-gray-700 disabled:opacity-30 transition-colors"
                style={{ width: 28, height: 28, borderRadius: 6 }}
              >
                <ZoomIn style={{ width: 14, height: 14, color: '#9CA3AF' }} />
              </button>
              <div className="flex-1" />
              <button
                onClick={handleResetView}
                className="flex items-center bg-gray-800 text-gray-400 hover:bg-gray-700 transition-colors"
                style={{ height: 28, gap: 4, padding: '0 8px', borderRadius: 6, fontSize: 10, fontWeight: 500 }}
              >
                <RotateCcw style={{ width: 12, height: 12 }} />
                {t('viewer.resetView')}
              </button>
            </div>
          )}

          {/* Brightness/Contrast (compact) */}
          {viewMode === '2d' && currentSeries && (brightness !== 100 || contrast !== 100) && (
            <div className="flex items-center gap-2 text-[10px] text-gray-500">
              <span>{t('viewer.brightness')}: {brightness}%</span>
              <span>{t('viewer.contrast')}: {contrast}%</span>
              <button
                onClick={resetImageAdjustments}
                className="ml-auto text-blue-500 hover:text-blue-400 font-medium"
              >
                {t('viewer.resetAdjustments', 'Reset')}
              </button>
            </div>
          )}
        </div>

        {/* Cursor Info + Histogram */}
        {currentSeries && cursorInfo && (
          <div className="border-b border-gray-700" style={{ padding: '8px 12px' }}>
            <div className="flex items-center gap-3 text-xs">
              <span className="text-gray-500">
                X:<span className="font-mono font-bold text-gray-300 ml-0.5">{cursorInfo.x}</span>
              </span>
              <span className="text-gray-500">
                Y:<span className="font-mono font-bold text-gray-300 ml-0.5">{cursorInfo.y}</span>
              </span>
              <span className="text-gray-500">
                Z:<span className="font-mono font-bold text-gray-300 ml-0.5">{cursorInfo.z}</span>
              </span>
              {cursorInfo.intensity !== null && (
                <span className="ml-auto text-gray-500">
                  {t('viewer.intensity', 'Val')}:<span className="font-mono font-bold text-gray-300 ml-0.5">{cursorInfo.intensity}</span>
                </span>
              )}
            </div>
            {sliceHistogram && (
              <div className="mt-2">
                <SliceHistogram histogram={sliceHistogram} cursorIntensity={cursorInfo.intensity} />
              </div>
            )}
          </div>
        )}

        {/* Histogram (visible even without cursor, if slice is loaded) */}
        {currentSeries && !cursorInfo && sliceHistogram && (
          <div className="border-b border-gray-700" style={{ padding: '8px 12px' }}>
            <label className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              {t('viewer.histogram', 'Histogram')}
            </label>
            <SliceHistogram histogram={sliceHistogram} cursorIntensity={null} />
          </div>
        )}

        {/* Image Info — Collapsible */}
        {currentSeries && (
          <div className="px-4 py-2">
            <button
              onClick={() => setImageInfoOpen(!imageInfoOpen)}
              className="w-full flex items-center gap-2 py-1 text-[11px] font-medium text-gray-500 uppercase tracking-wide hover:text-gray-300 transition-colors"
            >
              <Info className="w-3.5 h-3.5" />
              {t('viewer.imageInformation')}
              {imageInfoOpen
                ? <ChevronDown className="w-3 h-3 ml-auto" />
                : <ChevronRight className="w-3 h-3 ml-auto" />
              }
            </button>
            {imageInfoOpen && (
              <div className="mt-1 space-y-1 text-xs pb-1">
                <InfoRow label={t('viewer.format')} value={currentSeries.format.toUpperCase()} />
                <InfoRow
                  label={t('viewer.dimensions')}
                  value={`${currentSeries.metadata.rows} x ${currentSeries.metadata.columns}`}
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
                    value={`${currentSeries.metadata.pixel_spacing[0].toFixed(2)} x ${currentSeries.metadata.pixel_spacing[1].toFixed(2)} mm`}
                  />
                )}
                {currentSeries.metadata.slice_thickness != null && (
                  <InfoRow
                    label={t('viewer.sliceThickness', 'Thickness')}
                    value={`${currentSeries.metadata.slice_thickness.toFixed(2)} mm`}
                  />
                )}
              </div>
            )}
          </div>
        )}

        {/* Empty state — no image loaded */}
        {!currentSeries && !patient && (
          <div className="flex flex-col items-center justify-center py-16 text-center px-4">
            <Box className="w-10 h-10 text-gray-600 mb-3" />
            <p className="text-sm text-gray-500">
              {t('viewer.selectImageToView')}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center px-2 py-1 bg-gray-800/50 rounded">
      <span className="text-gray-400">{label}</span>
      <span className="text-white font-semibold">{value}</span>
    </div>
  );
}

function SliceHistogram({ histogram, cursorIntensity }: { histogram: number[]; cursorIntensity: number | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth;
    const cssH = canvas.clientHeight;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    ctx.scale(dpr, dpr);

    const marginLeft = 32;
    const marginBottom = 18;
    const marginTop = 4;
    const marginRight = 16;
    const plotW = cssW - marginLeft - marginRight;
    const plotH = cssH - marginTop - marginBottom;

    ctx.clearRect(0, 0, cssW, cssH);

    // Skip bin 0 (background) for better dynamic range
    const dataHist = histogram.slice(1);
    const maxCount = Math.max(...dataHist, 1);

    // Draw plot background
    ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
    ctx.fillRect(marginLeft, marginTop, plotW, plotH);

    // Draw Y-axis grid lines and labels
    ctx.font = '9px monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    const yTicks = [0, 0.25, 0.5, 0.75, 1.0];
    for (const tick of yTicks) {
      const y = marginTop + plotH - tick * plotH;
      const val = Math.round(tick * maxCount);
      // Grid line
      ctx.strokeStyle = 'rgba(107, 114, 128, 0.2)';
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(marginLeft, y);
      ctx.lineTo(marginLeft + plotW, y);
      ctx.stroke();
      // Label
      if (tick === 0 || tick === 0.5 || tick === 1.0) {
        ctx.fillStyle = 'rgba(156, 163, 175, 0.8)';
        const label = val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toString();
        ctx.fillText(label, marginLeft - 3, y);
      }
    }

    // Draw histogram bars
    const barWidth = plotW / 255;
    for (let i = 0; i < 255; i++) {
      const barHeight = (dataHist[i] / maxCount) * plotH;
      if (barHeight < 0.5) continue;
      const intensity = Math.round(((i + 1) / 255) * 255);
      ctx.fillStyle = `rgb(${intensity}, ${intensity}, ${intensity})`;
      ctx.fillRect(
        marginLeft + i * barWidth,
        marginTop + plotH - barHeight,
        Math.max(barWidth, 1),
        barHeight
      );
    }

    // Color overlay for visibility on dark bg
    ctx.save();
    ctx.globalCompositeOperation = 'source-atop';
    const gradient = ctx.createLinearGradient(marginLeft, 0, marginLeft + plotW, 0);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.6)');
    gradient.addColorStop(0.5, 'rgba(147, 51, 234, 0.6)');
    gradient.addColorStop(1, 'rgba(236, 72, 153, 0.6)');
    ctx.fillStyle = gradient;
    ctx.fillRect(marginLeft, marginTop, plotW, plotH);
    ctx.restore();

    // Draw X-axis labels
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = 'rgba(156, 163, 175, 0.8)';
    const xTicks = [0, 64, 128, 192, 255];
    for (const val of xTicks) {
      const x = marginLeft + ((val === 0 ? 0 : val - 1) / 254) * plotW;
      ctx.fillText(val.toString(), x, marginTop + plotH + 4);
      // Tick mark
      ctx.strokeStyle = 'rgba(107, 114, 128, 0.4)';
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(x, marginTop + plotH);
      ctx.lineTo(x, marginTop + plotH + 3);
      ctx.stroke();
    }

    // Plot border
    ctx.strokeStyle = 'rgba(107, 114, 128, 0.3)';
    ctx.lineWidth = 1;
    ctx.strokeRect(marginLeft, marginTop, plotW, plotH);

    // Cursor intensity marker
    if (cursorIntensity !== null && cursorIntensity > 0 && cursorIntensity <= 255) {
      const markerX = marginLeft + ((cursorIntensity - 1) / 254) * plotW;
      ctx.strokeStyle = '#22d3ee';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 2]);
      ctx.beginPath();
      ctx.moveTo(markerX, marginTop);
      ctx.lineTo(markerX, marginTop + plotH);
      ctx.stroke();
      ctx.setLineDash([]);

      // Cursor value label
      ctx.font = 'bold 9px monospace';
      ctx.fillStyle = '#22d3ee';
      ctx.textAlign = markerX > marginLeft + plotW / 2 ? 'right' : 'left';
      ctx.textBaseline = 'top';
      const labelX = markerX + (markerX > marginLeft + plotW / 2 ? -3 : 3);
      ctx.fillText(cursorIntensity.toString(), labelX, marginTop + 2);
    }
  }, [histogram, cursorIntensity]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full rounded bg-gray-950/50 border border-gray-700/30"
      style={{ height: 100 }}
    />
  );
}
