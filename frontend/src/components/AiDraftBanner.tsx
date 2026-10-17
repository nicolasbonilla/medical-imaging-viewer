/**
 * AiDraftBanner — persistent "AI draft, unreviewed" banner for any segmentation that carries AI
 * provenance (in-browser FLAMeS prototype; REQ-SAFE-030, RC-047).
 *
 * Shown wherever the segmentation is open, whether it is a local draft or a saved AI segmentation,
 * so an AI result can never be mistaken for manual work. A saved, unreviewed draft can be confirmed
 * only by an explicit clinician action (button + confirmation dialog); the server records who and when.
 */
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { AIProvenance } from '@/types';
import { segmentationAPI } from '@/api/segmentation';

interface AiDraftBannerProps {
  provenance: AIProvenance;
  segmentationId: string;
  /** Called with the server's updated provenance after a confirmed review. */
  onConfirmed?: (provenance: AIProvenance) => void;
}

export function aiStatusText(p: AIProvenance): string {
  return p.review_status === 'confirmed'
    ? `AI result — review confirmed by ${p.reviewed_by ?? 'unknown'}${p.reviewed_at ? ` (${p.reviewed_at.slice(0, 10)})` : ''}`
    : 'AI draft — UNREVIEWED';
}

export const AiDraftBanner: React.FC<AiDraftBannerProps> = ({ provenance, segmentationId, onConfirmed }) => {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isLocal = segmentationId.startsWith('local-');
  const unreviewed = provenance.review_status !== 'confirmed';

  const confirmReview = async () => {
    const ok = window.confirm(
      t(
        'segmentation.aiDraft.confirmQuestion',
        'Confirm that you have reviewed (and corrected where needed) this AI draft on every slice? Your name and the time will be recorded.',
      ),
    );
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await segmentationAPI.confirmAiReview(segmentationId);
      onConfirmed?.(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={`mt-1.5 rounded border p-1.5 text-[10px] leading-snug ${
        unreviewed ? 'border-orange-500/60 bg-orange-950/40 text-orange-200' : 'border-sky-600/50 bg-sky-950/30 text-sky-200'
      }`}
      role="status"
      data-testid="ai-draft-banner"
    >
      <p className="font-semibold">{aiStatusText(provenance)}</p>
      <p>
        {provenance.model_name} {t('segmentation.aiDraft.fold', 'fold')} {provenance.fold} · sha256 {provenance.model_sha256.slice(0, 12)} ·{' '}
        {provenance.pipeline_version}
      </p>
      {isLocal ? (
        <p>
          {t(
            'segmentation.aiDraft.notSaved',
            'Not saved. It is never saved automatically: review and correct it, then press Save; it will be stored as an unreviewed AI draft.',
          )}
        </p>
      ) : unreviewed ? (
        <button
          onClick={confirmReview}
          disabled={busy}
          className="mt-1 px-2 py-0.5 rounded bg-orange-700 hover:bg-orange-600 disabled:opacity-50 text-white"
        >
          {t('segmentation.aiDraft.confirm', 'I have reviewed this AI draft — confirm')}
        </button>
      ) : null}
      {error && <p className="text-red-300">{error}</p>}
    </div>
  );
};

export default AiDraftBanner;
