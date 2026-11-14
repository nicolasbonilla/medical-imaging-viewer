/**
 * QualityGatePanel — the single quality gate's result, shown BEFORE any AI output (REQ-FUNC-118; RC-127).
 * DRAFT, PENDING owner approval. Every word comes from the i18n files (qualityGate.*), keyed by the gate's codes:
 * the decision, then each check that is not OK with its plain reason and what to do — an action possible in the
 * gate's mode (G14: a comparison never asks for an attestation it cannot take). Rendered only when
 * FEATURES.QUALITY_GATE is on (VITE_ENABLE_QUALITY_GATE, default OFF).
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { actionOf, type GateResult } from '@/services/qualityGate/gate';
import { formatGateMessage } from '@/services/qualityGate/gateText';

const TONE: Record<GateResult['decision'], string> = {
  abstain: 'border-red-500/60 bg-red-950/30 text-red-100',
  pending: 'border-sky-500/50 bg-sky-950/30 text-sky-100',
  proceed_with_warnings: 'border-amber-500/60 bg-amber-950/30 text-amber-100',
  proceed: 'border-emerald-600/50 bg-emerald-950/20 text-emerald-100',
};

interface QualityGatePanelProps {
  result: GateResult;
  testId?: string;
}

export const QualityGatePanel: React.FC<QualityGatePanelProps> = ({ result, testId = 'quality-gate-panel' }) => {
  const { t } = useTranslation();
  const notOk = (result.checks ?? []).filter((c) => c.status !== 'pass' && c.code);
  return (
    <div
      className={`rounded border p-1.5 space-y-1 text-[9px] leading-snug ${TONE[result.decision] ?? TONE.abstain}`}
      role={result.decision === 'abstain' ? 'alert' : 'status'}
      data-testid={testId}
      data-decision={result.decision}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="font-semibold text-[10px]">{t('qualityGate.title')}</span>
        <span className="text-[8px] uppercase tracking-wide opacity-80">{t('qualityGate.draft')}</span>
      </div>
      <p className="font-medium" data-testid={`${testId}-decision`}>{t(`qualityGate.decision.${result.decision}`)}</p>
      {notOk.length > 0 && (
        <ul className="space-y-1">
          {notOk.map((c, i) => (
            <li key={`${c.check}-${c.visit ?? ''}-${i}`} data-testid={`${testId}-check`} data-code={c.code ?? ''}>
              <span className="font-semibold">
                {t(`qualityGate.check.${c.check}`)}
                {c.visit === 'tp1' || c.visit === 'tp2' ? ` (${t(`qualityGate.visit.${c.visit}`)})` : ''}
                {' · '}
                {t(`qualityGate.status.${c.status}`)}:
              </span>{' '}
              {/* K4 (fourteenth review): the ONE helper — every placeholder filled, a defined fallback otherwise */}
              {formatGateMessage(t, c.code as string, 'message', c.params)}{' '}
              <span className="italic">{formatGateMessage(t, c.code as string, actionOf(result, c.code as string), c.params)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default QualityGatePanel;
