/**
 * ConformalPanel — CALM-MS conformal second-reader (INVESTIGATIONAL).
 *
 * Surfaces the additive, population-level lesion-FDR review. Deliberately honest,
 * per the Class C adversarial review:
 *  - ordinal review-priority tiers (high/medium/low), NEVER a per-lesion % / "confidence"
 *  - the population-level scope stated prominently (NOT a per-scan guarantee)
 *  - validated PRESETS only; additive (never removes a lesion from the base mask)
 *  - "second-look candidates", never "keep"/"trusted"
 *
 * PRB-026: every text of this panel was written in Spanish into the code and shown in every interface
 * language; it is translated now (conformal.* in en/es/de; the English text here is only the fallback).
 *
 * @module components/ConformalPanel
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSegmentationStore } from '../store/useSegmentationStore';
import {
  runConformalSelect,
  fetchConformalStatusMask,
  type ConformalPreset,
} from '../services/conformalApi';

const PRESETS: { id: ConformalPreset; key: string; label: string; hint: string }[] = [
  { id: 'high_sensitivity', key: 'presetHighSensitivity', label: 'High sensitivity', hint: 'FDR target 0.30 · default' },
  { id: 'balanced', key: 'presetBalanced', label: 'Balanced', hint: 'FDR target 0.20' },
  { id: 'high_precision', key: 'presetHighPrecision', label: 'High precision', hint: 'FDR target 0.10' },
];

const TIER = {
  high: { key: 'tierHigh', label: 'High', dot: 'bg-emerald-400', text: 'text-emerald-300' },
  medium: { key: 'tierMedium', label: 'Medium', dot: 'bg-amber-400', text: 'text-amber-300' },
  low: { key: 'tierLow', label: 'Low', dot: 'bg-slate-400', text: 'text-slate-300' },
} as const;

interface Props {
  /** GCS object key of a FLAMeS float probability NIfTI on the calibration grid. */
  probFileId?: string;
}

export function ConformalPanel({ probFileId: probFileIdProp }: Props) {
  const { t } = useTranslation();
  const preset = useSegmentationStore((s) => s.conformalPreset);
  const summary = useSegmentationStore((s) => s.conformalSummary);
  const visible = useSegmentationStore((s) => s.conformalVisible);
  const setPreset = useSegmentationStore((s) => s.setConformalPreset);
  const setReview = useSegmentationStore((s) => s.setConformalReview);
  const clear = useSegmentationStore((s) => s.clearConformal);
  const toggleVisible = useSegmentationStore((s) => s.toggleConformalVisibility);

  const [probFileId, setProbFileId] = useState(probFileIdProp ?? '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Clear the additive tier overlay when the active segmentation/scan changes, so a
  // review computed for scan A can never linger over scan B (adversarial finding).
  const currentSegId = useSegmentationStore((s) => s.currentSegmentation?.segmentation_id);
  useEffect(() => { clear(); }, [currentSegId, clear]);

  const analyze = async () => {
    if (!probFileId.trim()) {
      setError(t('conformal.probRequired', 'Enter the file_id of the FLAMeS probability map.'));
      return;
    }
    setLoading(true); setError(null);
    try {
      const [sum, statusMask] = await Promise.all([
        runConformalSelect(probFileId.trim(), preset),
        fetchConformalStatusMask(probFileId.trim(), preset),
      ]);
      setReview(statusMask.mask, statusMask.dims, sum);
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      const s = err?.response?.status;
      const detail = err?.response?.data?.detail;
      setError(
        s === 404 ? t('conformal.errorDisabled', 'Feature not enabled (investigational).')
        : s === 409 ? t('conformal.errorExchangeability', 'Refused (exchangeability): {{detail}}.', {
          detail: detail ?? t('conformal.errorExchangeabilityDefault', 'grid/model mismatch') })
        : s === 422 ? t('conformal.errorInvalid', 'Invalid input: {{detail}}.', {
          detail: detail ?? t('conformal.errorInvalidDefault', 'preset or map') })
        : s === 503 ? t('conformal.errorCalibration', 'Calibration asset not available.')
        : t('conformal.errorGeneric', 'Error: {{detail}}.', {
          detail: detail ?? t('conformal.errorGenericDefault', 'request failed') }),
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2 text-xs text-gray-200">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-gray-100">{t('conformal.title', 'Per-lesion second reader (CALM-MS)')}</span>
        <span className="rounded bg-purple-900/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-purple-300">
          {t('conformal.investigational', 'investigational')}
        </span>
      </div>

      {/* Preset selector — validated operating points only */}
      <div className="grid grid-cols-3 gap-1">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            onClick={() => setPreset(p.id)}
            title={t(`conformal.${p.key}Hint`, p.hint)}
            className={`rounded px-1.5 py-1 text-[11px] leading-tight ${
              preset === p.id ? 'bg-teal-700 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            {t(`conformal.${p.key}`, p.label)}
          </button>
        ))}
      </div>

      {/* Investigational probability-map input (bring-your-own FLAMeS prob) */}
      <input
        value={probFileId}
        onChange={(e) => setProbFileId(e.target.value)}
        placeholder={t('conformal.probPlaceholder', 'file_id of the FLAMeS probability map')}
        className="w-full rounded bg-gray-800 px-2 py-1 text-[11px] text-gray-100 placeholder-gray-500"
      />

      <div className="flex gap-1">
        <button
          onClick={analyze}
          disabled={loading}
          className="flex-1 rounded bg-teal-700 px-2 py-1 text-white hover:bg-teal-600 disabled:opacity-50"
        >
          {loading ? t('conformal.analyzing', 'Analyzing…') : t('conformal.analyze', 'Analyze')}
        </button>
        {summary && (
          <>
            <button onClick={toggleVisible} className="rounded bg-gray-700 px-2 py-1 hover:bg-gray-600">
              {visible ? t('conformal.hide', 'Hide') : t('conformal.show', 'Show')}
            </button>
            <button onClick={clear} className="rounded bg-gray-700 px-2 py-1 hover:bg-gray-600">
              {t('conformal.clear', 'Clear')}
            </button>
          </>
        )}
      </div>

      {error && <div className="rounded bg-red-900/50 px-2 py-1 text-red-300">{error}</div>}

      {summary && (
        <div className="space-y-1.5">
          {/* Tier counts */}
          <div className="flex gap-3">
            {(['high', 'medium', 'low'] as const).map((tier) => (
              <span key={tier} className="flex items-center gap-1">
                <span className={`inline-block h-2 w-2 rounded-full ${TIER[tier].dot}`} />
                <span className={TIER[tier].text}>
                  {t(`conformal.${TIER[tier].key}`, TIER[tier].label)}: {summary.tier_counts[tier]}
                </span>
              </span>
            ))}
          </div>
          <div className="text-gray-400">
            {t('conformal.summaryLine', '{{n}} candidates · FDR target {{fdr}} · base {{base}}', {
              n: summary.n_candidates, fdr: summary.fdr_target, base: summary.base_model ?? '—' })}
          </div>
          {/* Guarantee scope / OOD-withheld state — prominent, always shown */}
          <div
            className={`rounded border px-2 py-1 text-[10px] leading-snug ${
              summary.marginal_shift_flagged
                ? 'border-red-600/60 bg-red-900/30 text-red-200'
                : 'border-amber-700/50 bg-amber-900/20 text-amber-200'
            }`}
          >
            {summary.marginal_shift_flagged && (
              <div className="mb-0.5 font-semibold">
                {t('conformal.scopeWithdrawn', '⚠ Scope withdrawn (marginal shift detected)')}
              </div>
            )}
            {summary.guarantee_scope}
          </div>
          {/* Non-dismissible investigational disclaimer — always shown when there is a review */}
          <div className="rounded border border-purple-800/50 bg-purple-950/30 px-2 py-1 text-[10px] leading-snug text-purple-200">
            {t('conformal.disclaimer',
              'Population-level review-prioritisation aid (investigational). Not an autonomous diagnosis and not a per-lesion probability.')}
          </div>
          {/* Additive candidate list (ordinal tiers; no probabilities, no "keep").
              De-emphasised when the scope is withheld — tiers are an unguaranteed second look. */}
          <div className={`max-h-40 space-y-0.5 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-600 ${
            summary.marginal_shift_flagged ? 'opacity-50' : ''
          }`}>
            {summary.lesions.map((l, i) => (
              <div key={i} className="flex items-center justify-between rounded bg-gray-800/60 px-2 py-0.5">
                <span className="flex items-center gap-1.5">
                  <span className={`inline-block h-2 w-2 rounded-full ${TIER[l.review_priority].dot}`} />
                  <span className={TIER[l.review_priority].text}>
                    {t(`conformal.${TIER[l.review_priority].key}`, TIER[l.review_priority].label)}
                  </span>
                </span>
                <span className="text-gray-400">{l.volume_mm3.toFixed(1)} mm³</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
