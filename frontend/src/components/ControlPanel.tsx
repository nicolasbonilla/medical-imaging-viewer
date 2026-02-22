import { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import {
  Calendar, Activity, ChevronDown, ChevronRight,
  Layers, ZoomIn, ZoomOut, RotateCcw, Box, Info
} from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { usePatient, useMedicalHistory } from '@/hooks/usePatients';
import { studyAPI } from '@/services/studyApi';
import type { StudySummary, ImageOrientation } from '@/types';

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
    setZoomLevel(Math.min(zoomLevel + 0.25, 5));
  }, [zoomLevel, setZoomLevel]);

  const handleZoomOut = useCallback(() => {
    setZoomLevel(Math.max(zoomLevel - 0.25, 0.25));
  }, [zoomLevel, setZoomLevel]);

  const handleResetView = useCallback(() => {
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
    resetImageAdjustments();
  }, [setZoomLevel, setPanOffset, resetImageAdjustments]);

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString();
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
    <div className="h-full flex flex-col bg-white/50 dark:bg-gray-900/50 backdrop-blur-xl border-l border-gray-200/50 dark:border-gray-700/50">
      {/* Content */}
      <div className="flex-1 overflow-y-auto">

        {/* Patient Info */}
        {patient && (
          <div className="px-4 py-3 border-b border-gray-200/50 dark:border-gray-700/50 bg-gradient-to-r from-primary-500/5 to-accent-500/5 dark:from-primary-500/10 dark:to-accent-500/10">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-accent-500 rounded-xl flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
                {patient.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-bold text-gray-900 dark:text-white text-sm truncate">
                  {patient.full_name}
                </p>
                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  {patient.age != null && (
                    <span>{patient.age} {t('patients.years')}</span>
                  )}
                  {patient.gender && (
                    <span className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-[10px] font-medium uppercase">
                      {patient.gender === 'male' ? 'M' : patient.gender === 'female' ? 'F' : patient.gender.charAt(0).toUpperCase()}
                    </span>
                  )}
                  {patient.mrn && (
                    <span className="font-mono text-[10px]">MRN: {patient.mrn}</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Medical History */}
        {patient && (
          <div className="px-4 py-2 border-b border-gray-200/50 dark:border-gray-700/50">
            <button
              onClick={() => setHistoryOpen(!historyOpen)}
              className="w-full flex items-center gap-2 py-1 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
            >
              <Activity className="w-3.5 h-3.5" />
              {t('panel.medicalHistory', 'Medical History')}
              {activeConditions.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-full text-[10px] font-bold">
                  {activeConditions.length}
                </span>
              )}
              {historyOpen
                ? <ChevronDown className="w-3 h-3 ml-auto" />
                : <ChevronRight className="w-3 h-3 ml-auto" />
              }
            </button>
            {historyOpen && (
              <div className="mt-1 space-y-1.5 pb-1">
                {activeConditions.length === 0 ? (
                  <p className="text-xs text-gray-400 dark:text-gray-500 py-1">
                    {t('panel.noActiveConditions', 'No active conditions recorded')}
                  </p>
                ) : (
                  activeConditions.map((condition) => (
                    <div
                      key={condition.id}
                      className={`px-2.5 py-2 rounded-lg border text-xs ${getSeverityColor(condition.severity)}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold">{condition.condition_name}</span>
                        {condition.severity && (
                          <span className="text-[10px] uppercase font-medium opacity-70">
                            {t(`panel.severity.${condition.severity}`, condition.severity)}
                          </span>
                        )}
                      </div>
                      {condition.onset_date && (
                        <p className="mt-0.5 opacity-70">
                          {t('panel.since', 'Since')}: {formatDate(condition.onset_date)}
                        </p>
                      )}
                      {condition.notes && (
                        <p className="mt-0.5 opacity-60 truncate">{condition.notes}</p>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}

        {/* Study Timeline */}
        {sortedStudies.length > 0 && (
          <div className="px-4 py-2 border-b border-gray-200/50 dark:border-gray-700/50">
            <button
              onClick={() => setTimelineOpen(!timelineOpen)}
              className="w-full flex items-center gap-2 py-1 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
            >
              <Calendar className="w-3.5 h-3.5" />
              {t('panel.studyTimeline', 'Study Timeline')}
              <span className="ml-1 px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-full text-[10px] font-bold">
                {sortedStudies.length}
              </span>
              {timelineOpen
                ? <ChevronDown className="w-3 h-3 ml-auto" />
                : <ChevronRight className="w-3 h-3 ml-auto" />
              }
            </button>
            {timelineOpen && (
              <div className="mt-1 space-y-0.5 pb-1">
                {sortedStudies.map((study, idx) => {
                  const isCurrent = study.id === currentStudyId;
                  return (
                    <div
                      key={study.id}
                      className={`relative pl-5 py-1.5 text-xs rounded-md transition-colors ${
                        isCurrent
                          ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50'
                      }`}
                    >
                      {/* Timeline dot and line */}
                      <div className="absolute left-1.5 top-0 bottom-0 flex flex-col items-center">
                        <div className={`w-2 h-2 rounded-full mt-2 flex-shrink-0 ${
                          isCurrent
                            ? 'bg-primary-500 ring-2 ring-primary-300 dark:ring-primary-700'
                            : 'bg-gray-300 dark:bg-gray-600'
                        }`} />
                        {idx < sortedStudies.length - 1 && (
                          <div className="w-px flex-1 bg-gray-200 dark:bg-gray-700 mt-0.5" />
                        )}
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <span className={`font-semibold ${isCurrent ? '' : 'font-normal'}`}>
                            {formatDate(study.study_date)}
                          </span>
                          {isCurrent && (
                            <span className="ml-1.5 text-[10px] font-bold uppercase text-primary-500">
                              {t('panel.current', 'Current')}
                            </span>
                          )}
                        </div>
                        <span className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-[10px] font-medium">
                          {study.modality}
                        </span>
                      </div>
                      {study.study_description && (
                        <p className="truncate opacity-70 mt-0.5">{study.study_description}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* View Controls (compact) */}
        <div className="px-4 py-2 border-b border-gray-200/50 dark:border-gray-700/50 space-y-3">
          {/* View Mode Toggle */}
          <div>
            <label className="flex items-center gap-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5">
              <Box className="w-3.5 h-3.5" />
              {t('viewer.viewMode')}
            </label>
            <div className="grid grid-cols-2 gap-1.5">
              {(['2d', '3d'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    viewMode === mode
                      ? 'bg-primary-500 text-white shadow-md'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                  }`}
                >
                  {t(`viewer.${mode}View`).toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* 3D Orientation */}
          {viewMode === '3d' && (
            <div>
              <label className="flex items-center gap-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5">
                <Layers className="w-3.5 h-3.5" />
                {t('viewer.orientation')}
              </label>
              <div className="flex gap-1">
                {(['axial', 'sagittal', 'coronal'] as ImageOrientation[]).map((orient) => (
                  <button
                    key={orient}
                    onClick={() => setOrientation(orient)}
                    className={`flex-1 px-1.5 py-1 rounded text-[11px] font-medium transition-all capitalize ${
                      orientation === orient
                        ? 'bg-accent-500 text-white'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                    }`}
                  >
                    {t(`viewer.${orient}`)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Slice Navigator */}
          {viewMode === '2d' && currentSeries && totalSlices > 1 && (
            <div>
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="font-semibold text-gray-500 dark:text-gray-400 flex items-center gap-1">
                  <Layers className="w-3 h-3" />
                  {t('viewer.slice', 'Slice')}
                </span>
                <span className="font-mono font-bold text-gray-700 dark:text-gray-300">
                  {currentSliceIndex + 1} / {totalSlices}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={totalSlices - 1}
                value={currentSliceIndex}
                onChange={(e) => setCurrentSliceIndex(Number(e.target.value))}
                className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full appearance-none cursor-pointer accent-primary-500"
              />
            </div>
          )}

          {/* Zoom + Reset (compact row) */}
          {currentSeries && (
            <div className="flex items-center gap-1.5">
              <button
                onClick={handleZoomOut}
                disabled={zoomLevel <= 0.25}
                className="p-1.5 bg-gray-100 dark:bg-gray-800 rounded hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-30 transition-colors"
              >
                <ZoomOut className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400" />
              </button>
              <span className="text-xs font-mono font-bold text-gray-700 dark:text-gray-300 w-10 text-center">
                {Math.round(zoomLevel * 100)}%
              </span>
              <button
                onClick={handleZoomIn}
                disabled={zoomLevel >= 5}
                className="p-1.5 bg-gray-100 dark:bg-gray-800 rounded hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-30 transition-colors"
              >
                <ZoomIn className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400" />
              </button>
              <div className="flex-1" />
              <button
                onClick={handleResetView}
                className="px-2 py-1 text-[10px] font-medium bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors flex items-center gap-1"
              >
                <RotateCcw className="w-3 h-3" />
                {t('viewer.resetView')}
              </button>
            </div>
          )}

          {/* Brightness/Contrast (compact) */}
          {viewMode === '2d' && currentSeries && (brightness !== 100 || contrast !== 100) && (
            <div className="flex items-center gap-2 text-[10px] text-gray-400 dark:text-gray-500">
              <span>{t('viewer.brightness')}: {brightness}%</span>
              <span>{t('viewer.contrast')}: {contrast}%</span>
              <button
                onClick={resetImageAdjustments}
                className="ml-auto text-primary-500 hover:text-primary-400 font-medium"
              >
                {t('viewer.resetAdjustments', 'Reset')}
              </button>
            </div>
          )}
        </div>

        {/* Cursor Info + Histogram */}
        {currentSeries && cursorInfo && (
          <div className="px-4 py-2 border-b border-gray-200/50 dark:border-gray-700/50">
            <div className="flex items-center gap-3 text-xs">
              <span className="text-gray-400 dark:text-gray-500">
                X:<span className="font-mono font-bold text-gray-700 dark:text-gray-300 ml-0.5">{cursorInfo.x}</span>
              </span>
              <span className="text-gray-400 dark:text-gray-500">
                Y:<span className="font-mono font-bold text-gray-700 dark:text-gray-300 ml-0.5">{cursorInfo.y}</span>
              </span>
              <span className="text-gray-400 dark:text-gray-500">
                Z:<span className="font-mono font-bold text-gray-700 dark:text-gray-300 ml-0.5">{cursorInfo.z}</span>
              </span>
              {cursorInfo.intensity !== null && (
                <span className="ml-auto text-gray-400 dark:text-gray-500">
                  {t('viewer.intensity', 'Val')}:<span className="font-mono font-bold text-gray-700 dark:text-gray-300 ml-0.5">{cursorInfo.intensity}</span>
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
          <div className="px-4 py-2 border-b border-gray-200/50 dark:border-gray-700/50">
            <label className="flex items-center gap-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5">
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
              className="w-full flex items-center gap-2 py-1 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
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
            <Box className="w-10 h-10 text-gray-300 dark:text-gray-600 mb-3" />
            <p className="text-sm text-gray-400 dark:text-gray-500">
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
    <div className="flex justify-between items-center px-2 py-1 bg-gray-50 dark:bg-gray-800/50 rounded">
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <span className="text-gray-900 dark:text-white font-semibold">{value}</span>
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
