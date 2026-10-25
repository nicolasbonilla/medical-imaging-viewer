/**
 * AiDraftBanner — persistent "AI draft, unreviewed" banner for any segmentation that carries AI
 * provenance (in-browser FLAMeS prototype; REQ-SAFE-030, RC-047).
 *
 * Shown wherever the segmentation is open, whether it is a local draft or a saved AI segmentation,
 * so an AI result can never be mistaken for manual work. A saved, unreviewed draft can be confirmed
 * only by an explicit clinician action (button + confirmation dialog), only when there are NO unsaved
 * corrections, and the confirmation is bound to the exact saved mask: the SHA-256 of the mask on screen
 * is sent and must equal the stored one; any later change of the mask resets the review (server-side).
 */
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { AIProvenance } from '@/types';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { AutomaticMarkingNotice } from './AutomaticMarkingNotice';

interface AiDraftBannerProps {
  provenance: AIProvenance;
  segmentationId: string;
  /** the open mask has unsaved corrections: the review cannot be confirmed until they are saved */
  hasUnsavedChanges?: boolean;
  /** Called with the server's updated provenance after a confirmed review. */
  onConfirmed?: (provenance: AIProvenance) => void;
}

export function aiStatusText(p: AIProvenance): string {
  return p.review_status === 'confirmed'
    ? `AI result — review confirmed by ${p.reviewed_by ?? 'unknown'}${p.reviewed_at ? ` (${p.reviewed_at.slice(0, 10)})` : ''}`
    : 'AI draft — UNREVIEWED';
}

export const AiDraftBanner: React.FC<AiDraftBannerProps> = ({ provenance, segmentationId, hasUnsavedChanges, onConfirmed }) => {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isLocal = segmentationId.startsWith('local-');
  const unreviewed = provenance.review_status !== 'confirmed';

  const confirmReview = async () => {
    if (hasUnsavedChanges) return;
    const ok = window.confirm(
      t(
        'segmentation.aiDraft.confirmQuestion',
        'Confirm that you have reviewed (and corrected where needed) this AI draft on every slice? Your name, the time and the exact saved mask will be recorded; any later change of the mask cancels this confirmation.',
      ),
    );
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      const digest = await useSegmentationStore.getState().maskDigestCallback?.();
      if (!digest) throw new Error('The open mask could not be read; reload the segmentation and try again.');
      const updated = await segmentationAPI.confirmAiReview(segmentationId, digest);
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
      {/* PRB-003 (RC-072): information for safety on automatic marking, whatever the review state. */}
      <AutomaticMarkingNotice className="text-[10px] leading-snug" />
      <p>
        {provenance.model_name} {t('segmentation.aiDraft.fold', 'fold')} {provenance.fold} · sha256 {provenance.model_sha256.slice(0, 12)} ·{' '}
        {provenance.pipeline_version}
      </p>
      {!unreviewed && provenance.reviewed_mask_sha256 && (
        <p>
          {t('segmentation.aiDraft.boundTo', 'Confirmed for the saved mask')} {provenance.reviewed_mask_sha256.slice(0, 12)}
          {hasUnsavedChanges ? ` — ${t('segmentation.aiDraft.willReset', 'saving your changes will cancel this confirmation')}` : ''}
        </p>
      )}
      {isLocal ? (
        <p>
          {t(
            'segmentation.aiDraft.notSaved',
            'Not saved. It is never saved automatically: review and correct it, then press Save; it will be stored as an unreviewed AI draft.',
          )}
        </p>
      ) : unreviewed && hasUnsavedChanges ? (
        <p data-testid="ai-draft-save-first">
          {t(
            'segmentation.aiDraft.saveFirst',
            'Unsaved corrections: save them first. The review can only be confirmed on the saved mask.',
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
