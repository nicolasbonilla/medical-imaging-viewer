/**
 * Longitudinal Comparison Panel
 *
 * Compares lesion masks between two timepoints. Shows:
 * - Burden delta summary (TP1 vs TP2)
 * - Status counts (new, resolved, enlarged, shrunk, stable)
 * - Per-lesion change table with click-to-navigate
 *
 * @module components/LongitudinalCompare
 */

import { useState, useCallback, useMemo, useEffect, useId } from 'react';
import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import {
  TrendingUp,
  Loader2,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  ArrowUpRight,
  ArrowDownRight,
  Plus,
  Minus,
  Equal,
} from 'lucide-react';
import { segmentationAPI } from '@/api/segmentation';
import { studyAPI } from '@/api/study';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { Badge, Button } from '@/components/ui';
import { LONGITUDINAL_RGB, MAGNIMS_ZONE_RGB, regionRgb, rgbCss } from '@/utils/clinicalPalette';
import type { RGB } from '@/utils/clinicalPalette';
import type { LongitudinalResult, LesionChange, StudySummary, SegmentationResponse, SELResult } from '@/types';

/** Names that indicate non-lesion segmentations (excluded from dropdowns) */
const EXCLUDED_DESCRIPTIONS = ['magnims zone map', 'brain extraction', 'brain mask', 'synthseg', 'parcellation'];

function isLesionSegmentation(seg: SegmentationResponse): boolean {
  const desc = (seg.metadata?.description || '').toLowerCase();
  return !EXCLUDED_DESCRIPTIONS.some((ex) => desc.includes(ex));
}

interface LongitudinalCompareProps {
  onNavigateToSlice?: (sliceIndex: number) => void;
  studies?: StudySummary[];
}

/** Shared control styles (design-system v2 tokens). */
const SELECT_CLS =
  'h-8 w-full rounded-lg border border-surface-border bg-surface-base px-2 text-xs text-ink-base ' +
  'transition-colors hover:border-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60';
const FOCUS_RING = 'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60';
const OVERLINE = 'text-xs font-medium uppercase tracking-wide text-ink-faint';
/** Compact status pill sizing for the dense change table (Badge primitive, 12px text). */
const TABLE_PILL = 'px-1.5 py-0 text-xs leading-4';

/**
 * Status colours. NEW and RESOLVED are the two classes painted on the fused overlay, so
 * they take the shared clinical palette (LONGITUDINAL_RGB: new = vermillion, resolved =
 * sky blue) — chips, table and legend must agree with the picture. Before v3 this panel
 * coloured new = blue and resolved = green while the overlay painted new = red, a
 * legend/picture disagreement. The remaining statuses use UI semantic tokens.
 */
function statusRgb(status: string): RGB | null {
  switch (status) {
    case 'new': return LONGITUDINAL_RGB.newLesion;
    case 'resolved': return LONGITUDINAL_RGB.resolved;
    default: return null;
  }
}

/** Inline text colour for the data-coloured statuses (undefined for token-coloured ones). */
function statusTextStyle(status: string): CSSProperties | undefined {
  const c = statusRgb(status);
  return c ? { color: rgbCss(c) } : undefined;
}

/** Inline dot colour for the data-coloured statuses (undefined for token-coloured ones). */
function statusDotStyle(status: string): CSSProperties | undefined {
  const c = statusRgb(status);
  return c ? { backgroundColor: rgbCss(c) } : undefined;
}

function statusIcon(status: string) {
  switch (status) {
    case 'new': return <Plus className="h-3 w-3 shrink-0" style={statusTextStyle(status)} aria-hidden />;
    case 'resolved': return <Minus className="h-3 w-3 shrink-0" style={statusTextStyle(status)} aria-hidden />;
    case 'enlarged': return <ArrowUpRight className="h-3 w-3 shrink-0 text-clinical-crit" aria-hidden />;
    case 'shrunk': return <ArrowDownRight className="h-3 w-3 shrink-0 text-ink-soft" aria-hidden />;
    case 'stable': return <Equal className="h-3 w-3 shrink-0 text-ink-muted" aria-hidden />;
    default: return null;
  }
}

function statusColor(status: string): string {
  switch (status) {
    case 'new':
    case 'resolved': return ''; // data colour applied inline (statusTextStyle)
    case 'enlarged': return 'text-clinical-crit';
    case 'shrunk': return 'text-ink-soft';
    case 'stable': return 'text-ink-muted';
    default: return 'text-ink-muted';
  }
}

function statusBg(status: string): string {
  switch (status) {
    case 'new':
    case 'resolved': return ''; // data colour applied inline (statusDotStyle)
    case 'enlarged': return 'bg-clinical-crit';
    case 'shrunk': return 'bg-ink-soft';
    case 'stable': return 'bg-ink-faint';
    default: return 'bg-ink-faint';
  }
}

/** MAGNIMS region pill colour from the shared zone palette (same as the zone-map overlay). */
function zoneBadgeStyle(regionId: number): CSSProperties | undefined {
  const c = MAGNIMS_ZONE_RGB[regionId];
  return c ? { color: rgbCss(c), backgroundColor: rgbCss(c, 0.15) } : undefined;
}

/** Region-row swatch (null for "Unassigned" / unknown names). */
function regionSwatchStyle(region: string): CSSProperties | undefined {
  const c = regionRgb(region);
  return c ? { backgroundColor: rgbCss(c) } : undefined;
}

/**
 * Legend swatch for the FLAIR subtraction heat map — the SAME endpoint colours as the
 * overlay ramp (volume/overlayPaint.subtractionRGBA and the legacy 2D canvas):
 * blue = darker / resolving, orange-red = brighter at follow-up / new signal.
 */
const SUBTRACTION_SWATCH_STYLE: CSSProperties = {
  background: 'linear-gradient(to right, rgb(60, 130, 245), transparent, rgb(245, 70, 40))',
};

function formatStudyDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return dateStr; }
}

/** Hook to fetch file_ids for a study (series → instances → gcs_object_name) */
function useStudyFileIds(studyId: string | null) {
  return useQuery({
    queryKey: ['study-file-ids', studyId],
    queryFn: async () => {
      if (!studyId) return [];
      const series = await studyAPI.listSeries(studyId);
      const allInstances = await Promise.all(series.map((s) => studyAPI.listInstances(s.id)));
      return allInstances.flat().map((inst) => inst.gcs_object_name).filter(Boolean);
    },
    enabled: !!studyId,
    staleTime: 5 * 60 * 1000,
  });
}

/** Hook to fetch lesion segmentations for a set of file_ids */
function useStudyLesionSegs(fileIds: string[], studyId: string | null) {
  return useQuery({
    queryKey: ['segmentations-lesion', studyId],
    queryFn: async () => {
      if (fileIds.length === 0) return [];
      const segs = await segmentationAPI.listSegmentationsByFileIds(fileIds);
      return segs.filter((s) => s.segmentation_id && isLesionSegmentation(s));
    },
    enabled: fileIds.length > 0,
    staleTime: 5 * 60 * 1000,
  });
}

export function LongitudinalCompare({
  onNavigateToSlice,
  studies = [],
}: LongitudinalCompareProps) {
  const { t } = useTranslation();
  const currentStudyId = useViewerStore((s) => s.currentStudyId);
  // Label ids so each timepoint's selects are announced with their TP label (a11y only).
  const tp1LabelId = useId();
  const tp2LabelId = useId();
  const tp1SelectId = useId();
  const tp2SelectId = useId();

  // Sort studies oldest first (TP1 = earlier, TP2 = later)
  const sortedStudies = useMemo(() =>
    [...studies].sort((a, b) => new Date(a.study_date).getTime() - new Date(b.study_date).getTime()),
    [studies]
  );

  // Study selection state
  const [tp1StudyId, setTp1StudyId] = useState<string>('');
  const [tp2StudyId, setTp2StudyId] = useState<string>('');

  // Segmentation selection state
  const [tp1SegId, setTp1SegId] = useState<string>('');
  const [tp2SegId, setTp2SegId] = useState<string>('');

  // Result state
  const [result, setResult] = useState<LongitudinalResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const subVisible = useSegmentationStore((s) => s.longitudinalSubtractionVisible);

  // SEL (slowly-expanding lesion) on-demand detection state
  const [selResult, setSelResult] = useState<SELResult | null>(null);
  const [selLoading, setSelLoading] = useState(false);

  const handleDetectSELs = useCallback(async () => {
    if (!tp1SegId || !tp2SegId) return;
    setSelLoading(true);
    setSelResult(null);
    try {
      const r = await segmentationAPI.detectSELs(
        { type: 'segmentation', id: tp1SegId },
        { type: 'segmentation', id: tp2SegId },
      );
      setSelResult(r);
    } catch (err: any) {
      setSelResult({ ok: false, reason: err?.response?.data?.detail || err?.message || 'SEL detection failed',
        sels: [], n_existing: 0, n_sel: 0 });
    } finally {
      setSelLoading(false);
    }
  }, [tp1SegId, tp2SegId]);

  // Invalidate a stale result: clearing the selection must also drop the on-canvas
  // overlays (fused masks + subtraction heatmap), so a heatmap can never outlive the
  // comparison it came from or persist after its toggle button disappears (Class C —
  // no stale/misleading overlay over a now-different selection).
  const invalidate = useCallback(() => {
    setResult(null);
    setSelResult(null);
    useSegmentationStore.getState().clearLongitudinalOverlay();
  }, []);
  // Also clear the overlays when this panel unmounts.
  useEffect(() => () => useSegmentationStore.getState().clearLongitudinalOverlay(), []);

  // Fetch file_ids and segmentations for each selected study
  const { data: tp1FileIds = [] } = useStudyFileIds(tp1StudyId || null);
  const { data: tp2FileIds = [] } = useStudyFileIds(tp2StudyId || null);
  const { data: tp1Segs = [] } = useStudyLesionSegs(tp1FileIds, tp1StudyId || null);
  const { data: tp2Segs = [] } = useStudyLesionSegs(tp2FileIds, tp2StudyId || null);

  // Auto-select first segmentation when list loads
  const canCompare = tp1SegId && tp2SegId;

  const handleCompare = useCallback(async () => {
    if (!canCompare) return;
    setIsLoading(true);
    setError(null);
    try {
      // Load both masks for visual overlay (parallel)
      const [tp1MaskData, tp2MaskData, data] = await Promise.all([
        segmentationAPI.loadZoneMapMask(tp1SegId),
        segmentationAPI.loadZoneMapMask(tp2SegId),
        segmentationAPI.compareLongitudinal(
          { type: 'segmentation', id: tp1SegId },
          { type: 'segmentation', id: tp2SegId },
        ),
      ]);

      // Store masks in Zustand for canvas rendering
      useSegmentationStore.getState().setLongitudinalOverlay(
        { mask: tp1MaskData.mask, dims: { depth: tp1MaskData.depth, height: tp1MaskData.height, width: tp1MaskData.width }, segId: tp1SegId },
        { mask: tp2MaskData.mask, dims: { depth: tp2MaskData.depth, height: tp2MaskData.height, width: tp2MaskData.width }, segId: tp2SegId },
      );

      // Decode the FLAIR subtraction heatmap (co-registered TP1 grid) for the overlay.
      if (data.subtraction_volume_b64 && data.subtraction_shape) {
        try {
          const bin = atob(data.subtraction_volume_b64);
          const vol = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) vol[i] = bin.charCodeAt(i);
          const [depth, height, width] = data.subtraction_shape;
          useSegmentationStore.getState().setLongitudinalSubtraction({
            volume: vol, dims: { depth, height, width }, clipSd: data.subtraction_clip_sd ?? 3,
          });
        } catch {
          useSegmentationStore.getState().setLongitudinalSubtraction(null);
        }
      } else {
        useSegmentationStore.getState().setLongitudinalSubtraction(null);
      }

      setResult(data);
      setExpanded(true);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.response?.data?.error?.message || err?.message || String(err);
      setError(detail);
    } finally {
      setIsLoading(false);
    }
  }, [tp1SegId, tp2SegId, canCompare]);

  const handleLesionClick = useCallback((change: LesionChange) => {
    onNavigateToSlice?.(Math.round(change.centroid_z));
  }, [onNavigateToSlice]);

  if (sortedStudies.length < 2) {
    return null;
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-brand-400" aria-hidden />
        <span className="text-sm font-semibold text-ink-base">
          {t('longitudinal.title', 'Longitudinal Tracking')}
        </span>
      </div>

      {/* TP1: Study + Segmentation */}
      <div className="space-y-1.5">
        <label id={tp1LabelId} htmlFor={tp1SelectId} className="block text-xs font-medium text-ink-muted">
          {t('longitudinal.tp1', 'TP1 (Earlier)')}
        </label>
        <select
          id={tp1SelectId}
          value={tp1StudyId}
          onChange={(e) => { setTp1StudyId(e.target.value); setTp1SegId(''); invalidate(); }}
          className={SELECT_CLS}
        >
          <option value="">Select study...</option>
          {sortedStudies.map((s) => (
            <option key={s.id} value={s.id}>
              {formatStudyDate(s.study_date)} — {s.study_description || s.modality}
              {s.id === currentStudyId ? ' (current)' : ''}
            </option>
          ))}
        </select>
        {tp1StudyId && tp1Segs.length > 0 && (
          <select
            aria-labelledby={tp1LabelId}
            value={tp1SegId}
            onChange={(e) => { setTp1SegId(e.target.value); invalidate(); }}
            className={SELECT_CLS}
          >
            <option value="">Select segmentation...</option>
            {tp1Segs.map((s) => (
              <option key={s.segmentation_id} value={s.segmentation_id}>
                {s.metadata?.description || s.segmentation_id.slice(0, 8)}
              </option>
            ))}
          </select>
        )}
        {tp1StudyId && tp1Segs.length === 0 && tp1FileIds.length > 0 && (
          <p className="text-xs italic text-ink-muted">No lesion segmentations found</p>
        )}
      </div>

      {/* TP2: Study + Segmentation */}
      <div className="space-y-1.5">
        <label id={tp2LabelId} htmlFor={tp2SelectId} className="block text-xs font-medium text-ink-muted">
          {t('longitudinal.tp2', 'TP2 (Later)')}
        </label>
        <select
          id={tp2SelectId}
          value={tp2StudyId}
          onChange={(e) => { setTp2StudyId(e.target.value); setTp2SegId(''); invalidate(); }}
          className={SELECT_CLS}
        >
          <option value="">Select study...</option>
          {sortedStudies.map((s) => (
            <option key={s.id} value={s.id}>
              {formatStudyDate(s.study_date)} — {s.study_description || s.modality}
              {s.id === currentStudyId ? ' (current)' : ''}
            </option>
          ))}
        </select>
        {tp2StudyId && tp2Segs.length > 0 && (
          <select
            aria-labelledby={tp2LabelId}
            value={tp2SegId}
            onChange={(e) => { setTp2SegId(e.target.value); invalidate(); }}
            className={SELECT_CLS}
          >
            <option value="">Select segmentation...</option>
            {tp2Segs.map((s) => (
              <option key={s.segmentation_id} value={s.segmentation_id}>
                {s.metadata?.description || s.segmentation_id.slice(0, 8)}
              </option>
            ))}
          </select>
        )}
        {tp2StudyId && tp2Segs.length === 0 && tp2FileIds.length > 0 && (
          <p className="text-xs italic text-ink-muted">No lesion segmentations found</p>
        )}
      </div>

      {/* Compare Button */}
      <Button
        variant="primary"
        size="sm"
        fullWidth
        onClick={handleCompare}
        disabled={!canCompare || isLoading}
        loading={isLoading}
      >
        {t('longitudinal.compare', 'Compare Timepoints')}
      </Button>

      {error && (
        <div className="flex items-start gap-1.5 text-xs text-clinical-crit">
          <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 break-words">{error}</span>
        </div>
      )}

      {result && (
        <>
          {/* Burden Summary */}
          <div className="space-y-1.5 rounded-lg border border-surface-border bg-surface-raised p-2.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-ink-muted">
                {t('longitudinal.burden', 'Lesion Burden')}
              </span>
              <div className="flex items-center gap-1.5 tabular-nums">
                <span className="text-xs text-ink-muted">{result.burden_tp1_ml.toFixed(2)} mL</span>
                <span className="text-xs text-ink-faint" aria-hidden>&rarr;</span>
                <span className="text-sm font-semibold text-ink-base">{result.burden_tp2_ml.toFixed(2)} mL</span>
              </div>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-ink-muted">{t('longitudinal.change', 'Change')}</span>
              <span className={`text-sm font-semibold tabular-nums ${
                result.burden_delta_percent > 5 ? 'text-clinical-crit' :
                result.burden_delta_percent < -5 ? 'text-clinical-good' : 'text-ink-soft'
              }`}>
                {result.burden_delta_percent > 0 ? '+' : ''}{result.burden_delta_percent.toFixed(1)}%
              </span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-ink-muted">{t('longitudinal.lesionCount', 'Lesion Count')}</span>
              <span className="text-xs tabular-nums text-ink-soft">
                {result.total_lesions_tp1} &rarr; {result.total_lesions_tp2}
              </span>
            </div>
          </div>

          {/* Safety caveat (Class C) — DRIVEN by the backend's registration flag, not
              hardcoded: until TP2 is spatially co-registered to TP1, every count is an
              UNADJUDICATED CANDIDATE (equal array dimensions are not voxel alignment), so
              counts can include misregistration artefacts. Prefer the backend's authoritative
              `caveat` string. registration_verified is currently always false. */}
          {result.registration_verified ? (
            <div className="rounded-lg border border-clinical-good/30 bg-clinical-good/10 px-2.5 py-2 text-xs leading-snug text-clinical-good">
              {t('longitudinal.registrationVerified',
                'Timepoints spatially co-registered — changes are spatially valid (still review before diagnosis).')}
            </div>
          ) : (
            <div className="rounded-lg border border-clinical-warn/30 bg-clinical-warn/10 px-2.5 py-2 text-xs leading-snug text-clinical-warn">
              {result.caveat || t('longitudinal.candidateCaveat',
                'Unadjudicated change candidates — spatial registration NOT verified. Two timepoints with equal dimensions are not necessarily aligned; a radiologist must review each candidate before it informs a diagnosis.')}
            </div>
          )}
          {result.spacing_resolved === false && (
            <div className="rounded-lg border border-clinical-warn/30 bg-clinical-warn/10 px-2.5 py-1.5 text-xs leading-snug text-clinical-warn">
              {t('longitudinal.spacingFallback',
                'Voxel spacing could not be resolved — volumes (mL) are approximate.')}
            </div>
          )}
          {/* Co-registration status (advisory). Rigid registration removes head-pose
              misregistration false positives; it is NOT lesion-scale certification
              (registration_verified stays false). Transparent method disclosure — a
              gap most commercial tools leave as a black box. */}
          <div className="flex items-start gap-1.5 text-xs leading-snug text-ink-muted">
            <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${result.registration_applied ? 'bg-clinical-info' : 'bg-ink-faint'}`} aria-hidden />
            {result.registration_applied ? (
              <span className="tabular-nums">
                {t('longitudinal.coregistered', 'Rigidly co-registered (TP2→TP1, advisory)')}
                {typeof result.registration_advisory_qc?.translation_mm === 'number' &&
                  ` · ${result.registration_advisory_qc.translation_mm.toFixed(1)} mm, ${(result.registration_advisory_qc.rotation_deg ?? 0).toFixed(1)}°`}
              </span>
            ) : (
              <span>{t('longitudinal.indexAligned', 'Index-aligned (no source image to register)')}</span>
            )}
          </div>
          {/* FLAIR subtraction confirmation summary (advisory new-lesion filter). */}
          {result.subtraction_available && result.subtraction_summary && result.subtraction_summary.new_total > 0 && (
            <div className="flex items-start gap-1.5 text-xs leading-snug text-ink-muted">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-clinical-info" aria-hidden />
              <span className="tabular-nums">
                {t('longitudinal.subSummary',
                  'FLAIR subtraction: {{c}} of {{n}} new candidates confirmed brighter at follow-up',
                  { c: result.subtraction_summary.new_subtraction_confirmed, n: result.subtraction_summary.new_total })}
              </span>
            </div>
          )}
          {/* FLAIR subtraction HEATMAP overlay toggle (red = brighter at follow-up /
              new signal; blue = resolving). Rendered on the TP1-grid viewport. */}
          {result.subtraction_volume_b64 && (
            <button
              type="button"
              aria-pressed={subVisible}
              onClick={() => useSegmentationStore.getState().toggleLongitudinalSubtraction()}
              className={`flex w-full items-center justify-between rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${FOCUS_RING} ${
                subVisible
                  ? 'border-brand-500/30 bg-brand-950 text-brand-400'
                  : 'border-surface-border text-ink-soft hover:bg-surface-hover'
              }`}
            >
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-4 rounded-sm" style={SUBTRACTION_SWATCH_STYLE} aria-hidden />
                {t('longitudinal.subOverlayToggle', 'FLAIR subtraction heatmap')}
              </span>
              <span className="font-semibold">{subVisible ? t('common.on', 'ON') : t('common.off', 'OFF')}</span>
            </button>
          )}
          {result.subtraction_volume_omitted && (
            <div className="text-xs leading-snug text-ink-muted">
              {t('longitudinal.subOmitted', 'Subtraction heatmap omitted (volume too large); confirmation flags still apply.')}
            </div>
          )}

          {/* MAGNIMS activity / DIT CANDIDATE signal (advisory — never a diagnosis).
              Gated on the same candidate framing: presented as "candidate", requires
              radiologist adjudication, never asserts active disease or DIT. */}
          {(result.activity_candidate || result.dit_candidate) && (
            <div className="rounded-lg border border-clinical-warn/30 bg-clinical-warn/10 px-2.5 py-2 text-xs leading-snug text-clinical-warn">
              <span className="font-semibold">
                {result.activity_candidate
                  ? t('longitudinal.activityCandidate', 'Active-disease CANDIDATE')
                  : t('longitudinal.ditCandidate', 'Dissemination-in-time CANDIDATE')}
              </span>{' '}
              {t('longitudinal.magnimsCandidateBody',
                '{{n}} new (≥{{d}} mm) + {{e}} enlarging. MAGNIMS 2021: any new or enlarging T2 lesion marks activity; a new lesion supports DIT. This is an UNADJUDICATED candidate — a radiologist must confirm before it informs any diagnosis or treatment change.',
                { n: result.new_clinically_significant_count ?? 0, e: result.enlarging_count ?? 0, d: result.new_lesion_min_diameter_mm ?? 3 })}
            </div>
          )}

          {/* NEDA-3 MRI (T2-arm) CANDIDATE status — composes the new/enlarging counts
              into the recognized monitoring construct, HONEST about what is not assessed
              (Gd-enhancing lesions need post-contrast T1; relapses/EDSS are clinical). */}
          {result.new_clinically_significant_count != null && (() => {
            const t2Active = (result.new_clinically_significant_count ?? 0) + (result.enlarging_count ?? 0) >= 1;
            return (
              <div className={`rounded-lg border px-2.5 py-2 text-xs leading-snug ${
                t2Active
                  ? 'border-clinical-warn/30 bg-clinical-warn/10 text-clinical-warn'
                  : 'border-clinical-good/30 bg-clinical-good/10 text-clinical-good'
              }`}>
                <span className="font-semibold">
                  {t2Active
                    ? t('longitudinal.nedaT2Active', 'NEDA-3 MRI (T2-arm): activity CANDIDATE')
                    : t('longitudinal.nedaT2Clear', 'NEDA-3 MRI (T2-arm): no new/enlarging T2 candidate')}
                </span>{' '}
                {t('longitudinal.nedaNote',
                  'T2 arm only — Gd-enhancing lesions (post-contrast T1) and clinical relapse/EDSS are NOT assessed here; full NEDA-3/NEDA-4 requires them. Candidate, not a determination.')}
              </div>
            );
          })()}

          {/* MAGNIMS region stratification (MSMask atlas) of new/enlarging candidates —
              PV/JC/IT/DWM, what commercial tools report by McDonald region. Only shown
              when a zone map was available (MNI-space data); candidate-quality.
              Region swatches use the shared MAGNIMS zone palette (same as the zone map). */}
          {result.region_stratification && (() => {
            const rows = Object.entries(result.region_stratification)
              .filter(([, v]) => v.new > 0 || v.enlarging > 0);
            if (rows.length === 0) return null;
            return (
              <div className="rounded-lg border border-surface-border px-2.5 py-2">
                <div className={`mb-1 ${OVERLINE}`}>
                  {t('longitudinal.byRegion', 'New / enlarging by MAGNIMS region (candidate)')}
                </div>
                {result.region_atlas_note && (
                  <div className="mb-1.5 text-xs leading-snug text-ink-muted">{result.region_atlas_note}</div>
                )}
                <div className="flex flex-col gap-1">
                  {rows.map(([region, v]) => (
                    <div key={region} className="flex items-center justify-between gap-2 text-xs">
                      <span className="flex min-w-0 items-center gap-1.5 text-ink-soft">
                        <span
                          className="inline-block h-2 w-2 shrink-0 rounded-sm bg-ink-faint"
                          style={regionSwatchStyle(region)}
                          aria-hidden
                        />
                        <span className="truncate">{region}</span>
                      </span>
                      <span className="shrink-0 tabular-nums text-ink-muted">
                        {v.new > 0 && <span style={statusTextStyle('new')}>{v.new} new</span>}
                        {v.new > 0 && v.enlarging > 0 && ' · '}
                        {v.enlarging > 0 && <span className="text-clinical-crit">{v.enlarging} enl</span>}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* SEL (slowly-expanding lesion) detection — vanguard smoldering-disease
              biomarker, on-demand (deformable registration). CANDIDATE, single-interval. */}
          <div className="rounded-lg border border-surface-border bg-surface-raised px-2.5 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-ink-base">
                {t('longitudinal.selTitle', 'Slowly-expanding lesions (SEL)')}
              </span>
              <Button
                variant="secondary"
                size="sm"
                className="h-7 shrink-0 px-2"
                onClick={handleDetectSELs}
                disabled={selLoading}
                leftIcon={selLoading ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : undefined}
              >
                {selLoading ? t('longitudinal.selRunning', 'Analyzing…') : t('longitudinal.selDetect', 'Detect SELs')}
              </Button>
            </div>
            {selResult && (
              <div className="mt-1.5 text-xs leading-snug">
                {!selResult.ok ? (
                  <span className="text-ink-muted">
                    {t('longitudinal.selUnavailable', 'SEL detection unavailable: {{r}}', { r: selResult.reason })}
                  </span>
                ) : (
                  <>
                    <span className="tabular-nums text-ink-soft">
                      {t('longitudinal.selSummary',
                        '{{s}} SEL candidate(s) among {{e}} pre-existing lesions (vs {{bg}}% normal-tissue noise floor)',
                        { s: selResult.n_sel, e: selResult.n_existing,
                          bg: Math.round((selResult.background_expanding_fraction ?? 0) * 100) })}
                    </span>
                    {selResult.sels.length > 0 && (
                      <div className="mt-1 flex flex-col gap-0.5">
                        {selResult.sels.map((s, i) => (
                          <button
                            key={i}
                            type="button"
                            onClick={() => onNavigateToSlice?.(Math.round(s.centroid_z))}
                            className={`flex items-center justify-between gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-surface-hover ${FOCUS_RING}`}
                          >
                            <span className="tabular-nums text-ink-soft">
                              {(s.baseline_volume_mm3 / 1000).toFixed(3)} mL {t('longitudinal.selBaseline', 'baseline')}
                            </span>
                            <span className="tabular-nums font-medium text-ink-base">
                              {Math.round(s.expanding_fraction * 100)}% {t('longitudinal.selExpanding', 'expanding')}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="mt-1 text-xs leading-snug text-ink-muted">
                      {t('longitudinal.selCaveat',
                        'CANDIDATE, single-interval (2 timepoints). The validated SEL definition needs ≥3 timepoints. The noise floor is estimated from normal tissue (approximate false-positive control, not a guaranteed rate). A radiologist must adjudicate.')}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Status Counts (candidates) */}
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(result.status_counts).map(([status, count]) => (
              count > 0 && (
                <Badge
                  key={status}
                  tone="neutral"
                  className="gap-1 px-2 py-1 text-xs tabular-nums"
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${statusBg(status)}`}
                    style={statusDotStyle(status)}
                    aria-hidden
                  />
                  <span className={statusColor(status)} style={statusTextStyle(status)}>
                    {count} {t(`longitudinal.${status}`, status)}
                    {!result.registration_verified ? ` ${t('longitudinal.candidateSuffix', 'cand.')}` : ''}
                  </span>
                </Badge>
              )
            ))}
          </div>

          {/* Legend for the fused TP1/TP2 overlay painted on the 2D viewport — colours come
              from the shared clinical palette (LONGITUDINAL_RGB), the same values the overlay
              renderer paints, so the change map is readable and colour-blind safe.
              Vermillion = TP2-only = NEW lesion candidate. */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: rgbCss(LONGITUDINAL_RGB.resolved) }} aria-hidden />
              {t('longitudinal.legendTp1', 'TP1 only (resolved cand.)')}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: rgbCss(LONGITUDINAL_RGB.persistent) }} aria-hidden />
              {t('longitudinal.legendBoth', 'Both (stable)')}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: rgbCss(LONGITUDINAL_RGB.newLesion) }} aria-hidden />
              {t('longitudinal.legendTp2', 'TP2 only (NEW cand.)')}
            </span>
          </div>

          {/* Expandable Table */}
          <button
            type="button"
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
            className={`flex items-center gap-1 rounded text-xs font-medium text-ink-muted transition-colors hover:text-ink-base ${FOCUS_RING}`}
          >
            {expanded ? <ChevronUp className="h-3.5 w-3.5" aria-hidden /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden />}
            {t('longitudinal.changeTable', 'Change Table')} <span className="tabular-nums">({result.changes.length})</span>
          </button>

          {expanded && result.changes.length > 0 && (
            <div className="max-h-48 overflow-y-auto rounded-lg border border-surface-border">
              <table className="w-full text-xs tabular-nums">
                <thead className="sticky top-0 bg-surface-base">
                  <tr className="border-b border-surface-border text-ink-faint">
                    <th className="px-1.5 py-1 text-left font-medium">{t('longitudinal.statusCol', 'Status')}</th>
                    <th className="px-1.5 py-1 text-right font-medium">TP1</th>
                    <th className="px-1.5 py-1 text-right font-medium">TP2</th>
                    <th className="px-1.5 py-1 text-right font-medium">&Delta;%</th>
                  </tr>
                </thead>
                <tbody>
                  {result.changes.map((change, i) => (
                    <tr
                      key={i}
                      tabIndex={0}
                      onClick={() => handleLesionClick(change)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleLesionClick(change);
                        }
                      }}
                      className="cursor-pointer border-b border-surface-border/60 transition-colors last:border-b-0 hover:bg-surface-hover focus:outline-none focus-visible:bg-surface-hover focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-brand-500/60"
                    >
                      <td className="px-1.5 py-1 text-left">
                        <span className="flex flex-wrap items-center gap-1">
                          {statusIcon(change.status)}
                          <span className={statusColor(change.status)} style={statusTextStyle(change.status)}>
                            {t(`longitudinal.${change.status}`, change.status)}
                          </span>
                          {change.region_id != null && (
                            <span
                              title={change.region_name ?? ''}
                              className="rounded bg-surface-hover px-1 text-xs font-medium leading-4 text-ink-soft"
                              style={zoneBadgeStyle(change.region_id)}
                            >{({ 1: 'PV', 2: 'JC', 3: 'IT', 4: 'DWM' } as Record<number, string>)[change.region_id]}</span>
                          )}
                          {/* FLAIR-subtraction confirmation badge (new candidates only) */}
                          {change.status === 'new' && change.clinically_significant === false && (
                            <Badge
                              tone="neutral"
                              title={t('longitudinal.subthresholdTip', 'Below the ~3 mm clinical size gate — not counted toward activity/DIT')}
                              className={TABLE_PILL}
                            >&lt;3mm</Badge>
                          )}
                          {change.status === 'new' && change.subtraction_confirmed === true && (
                            <Badge
                              tone="info"
                              title={t('longitudinal.subConfirmedTip', 'FLAIR brighter at follow-up (signal {{s}} SD) — supports a genuine new lesion', { s: (change.subtraction_signal ?? 0).toFixed(1) })}
                              className={TABLE_PILL}
                            >✓sub</Badge>
                          )}
                          {change.status === 'new' && change.subtraction_confirmed === false && (
                            <Badge
                              tone="neutral"
                              title={t('longitudinal.subUnconfirmedTip', 'No follow-up brightening on FLAIR subtraction — review for artifact')}
                              className={TABLE_PILL}
                            >○sub</Badge>
                          )}
                          {change.status === 'new' && change.subtraction_confirmed == null &&
                            result.subtraction_available && change.subtraction_note === 'border' && (
                            <Badge
                              tone="warn"
                              title={t('longitudinal.subWithheldTip', 'At brain/FOV edge — subtraction verdict withheld (unreliable at the boundary)')}
                              className={TABLE_PILL}
                            >◌sub</Badge>
                          )}
                        </span>
                      </td>
                      <td className="px-1.5 py-1 text-right text-ink-soft">
                        {change.volume_tp1_ml > 0 ? `${change.volume_tp1_ml.toFixed(3)}` : '\u2014'}
                      </td>
                      <td className="px-1.5 py-1 text-right text-ink-base">
                        {change.volume_tp2_ml > 0 ? `${change.volume_tp2_ml.toFixed(3)}` : '\u2014'}
                      </td>
                      <td
                        className={`px-1.5 py-1 text-right ${statusColor(change.status)}`}
                        style={statusTextStyle(change.status)}
                      >
                        {change.status === 'new' ? '+new' :
                         change.status === 'resolved' ? 'gone' :
                         `${change.change_percent > 0 ? '+' : ''}${change.change_percent.toFixed(1)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
