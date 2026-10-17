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
 * @module components/ConformalPanel
 */
import { useEffect, useState } from 'react';
import { useSegmentationStore } from '../store/useSegmentationStore';
import {
  runConformalSelect,
  fetchConformalStatusMask,
  type ConformalPreset,
} from '../services/conformalApi';
import { Badge, Button, Input } from '@/components/ui';
import { CONFORMAL_TIER_RGB, rgbCss } from '@/utils/clinicalPalette';

const PRESETS: { id: ConformalPreset; label: string; hint: string }[] = [
  { id: 'high_sensitivity', label: 'Alta sensibilidad', hint: 'objetivo FDR 0.30 · por defecto' },
  { id: 'balanced', label: 'Balanceado', hint: 'objetivo FDR 0.20' },
  { id: 'high_precision', label: 'Alta precisión', hint: 'objetivo FDR 0.10' },
];

// Tier colours come from the shared clinical palette (tier value 1 high, 2 medium,
// 3 low — the same encoding the backend status mask uses), so this legend always
// matches the overlay painted on the image.
const TIER = {
  high: { label: 'Alta', color: rgbCss(CONFORMAL_TIER_RGB[1]) },
  medium: { label: 'Media', color: rgbCss(CONFORMAL_TIER_RGB[2]) },
  low: { label: 'Baja', color: rgbCss(CONFORMAL_TIER_RGB[3]) },
} as const;

interface Props {
  /** GCS object key of a FLAMeS float probability NIfTI on the calibration grid. */
  probFileId?: string;
}

export function ConformalPanel({ probFileId: probFileIdProp }: Props) {
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
    if (!probFileId.trim()) { setError('Indica el file_id del mapa de probabilidad FLAMeS.'); return; }
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
        s === 404 ? 'Función no habilitada (investigacional/oscura).'
        : s === 409 ? `Rechazado por exchangeability: ${detail ?? 'grid/modelo no coincide'}.`
        : s === 422 ? `Entrada inválida: ${detail ?? 'preset o mapa'}.`
        : s === 503 ? 'Asset de calibración no disponible.'
        : `Error: ${detail ?? 'fallo de la petición'}.`,
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2 text-xs text-ink-soft">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold leading-snug text-ink-base">Segunda lectura por lesión (CALM-MS)</span>
        <Badge tone="info" className="shrink-0 text-xs uppercase tracking-wide">
          investigacional
        </Badge>
      </div>

      {/* Preset selector — validated operating points only */}
      <div className="grid grid-cols-3 gap-1 rounded-lg border border-surface-border bg-surface-base p-1">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            onClick={() => setPreset(p.id)}
            title={p.hint}
            aria-pressed={preset === p.id}
            className={`rounded-md border px-1.5 py-1 text-xs leading-tight transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 ${
              preset === p.id
                ? 'border-brand-500/30 bg-brand-950 text-brand-400'
                : 'border-transparent text-ink-muted hover:bg-surface-hover hover:text-ink-base'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Investigational probability-map input (bring-your-own FLAMeS prob) */}
      <Input
        value={probFileId}
        onChange={(e) => setProbFileId(e.target.value)}
        placeholder="file_id del mapa de probabilidad FLAMeS"
        aria-label="file_id del mapa de probabilidad FLAMeS"
        className="h-8 rounded-md text-xs"
      />

      <div className="flex gap-1">
        <Button
          variant="primary"
          size="sm"
          onClick={analyze}
          disabled={loading}
          className="flex-1"
        >
          {loading ? 'Analizando…' : 'Analizar'}
        </Button>
        {summary && (
          <>
            <Button variant="secondary" size="sm" onClick={toggleVisible}>
              {visible ? 'Ocultar' : 'Mostrar'}
            </Button>
            <Button variant="secondary" size="sm" onClick={clear}>Limpiar</Button>
          </>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-clinical-crit/30 bg-clinical-crit/10 px-2 py-1.5 text-clinical-crit">
          {error}
        </div>
      )}

      {summary && (
        <div className="space-y-2">
          {/* Tier counts */}
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {(['high', 'medium', 'low'] as const).map((t) => (
              <span key={t} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: TIER[t].color }}
                  aria-hidden
                />
                <span className="text-ink-soft">
                  {TIER[t].label}: <span className="tabular-nums text-ink-base">{summary.tier_counts[t]}</span>
                </span>
              </span>
            ))}
          </div>
          <div className="tabular-nums text-ink-muted">
            {summary.n_candidates} candidatos · objetivo FDR {summary.fdr_target} · base {summary.base_model ?? '—'}
          </div>
          {/* Guarantee scope / OOD-withheld state — prominent, always shown */}
          <div
            className={`rounded-md border px-2 py-1.5 text-xs leading-snug ${
              summary.marginal_shift_flagged
                ? 'border-clinical-crit/30 bg-clinical-crit/10 text-clinical-crit'
                : 'border-clinical-warn/30 bg-clinical-warn/10 text-clinical-warn'
            }`}
          >
            {summary.marginal_shift_flagged && (
              <div className="mb-0.5 font-semibold">⚠ Alcance retirado (desviación marginal detectada)</div>
            )}
            {summary.guarantee_scope}
          </div>
          {/* Non-dismissible investigational disclaimer — always shown when there is a review */}
          <div className="rounded-md border border-clinical-info/30 bg-clinical-info/10 px-2 py-1.5 text-xs leading-snug text-clinical-info">
            Ayuda de priorización de revisión a nivel poblacional (investigacional).
            No es un diagnóstico autónomo ni una probabilidad por lesión.
          </div>
          {/* Additive candidate list (ordinal tiers; no probabilities, no "keep").
              De-emphasised when the scope is withheld — tiers are an unguaranteed second look. */}
          <div className={`max-h-40 space-y-0.5 overflow-y-auto pr-1 ${
            summary.marginal_shift_flagged ? 'opacity-50' : ''
          }`}>
            {summary.lesions.map((l, i) => (
              <div key={i} className="flex items-center justify-between rounded-md bg-surface-base/60 px-2 py-1">
                <span className="flex items-center gap-1.5">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: TIER[l.review_priority].color }}
                    aria-hidden
                  />
                  <span className="text-ink-soft">{TIER[l.review_priority].label}</span>
                </span>
                <span className="tabular-nums text-ink-muted">{l.volume_mm3.toFixed(1)} mm³</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
