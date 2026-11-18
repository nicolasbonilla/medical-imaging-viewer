/**
 * LesionReviewRecord — the lesion-by-lesion record of an AI review, and the reader-study reading before the draft
 * (REQ-FUNC-119, REQ-FUNC-120; RC-131, RC-132; HAZ-001 cause (h): the reader goes along with the draft).
 *
 * - `ReviewRecordLines`: after a confirmed review, what the reviewer did with the draft's lesions (kept, corrected,
 *   removed) and how many lesions the reviewer added that the model never drafted; with a reading recorded before the
 *   draft, how the result relates to it. Counts computed by the server at the confirmation.
 * - `ReaderStudyGate`: on an image of the reader-study set read without the draft first (server decision, a fixed
 *   share of images; the set is off unless the study switches it on), the in-browser AI is offered only after the
 *   reader recorded their own reading of the image.
 * - `UnaidedReadingCard`: on such an image, records the open saved segmentation the reader drew without the AI as
 *   their reading before the draft (write-once on the server, bound to the saved mask).
 */
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { ReviewRecordSummary } from '@/types';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';

export const readerStudyKey = (fileId: string) => ['readerStudy', fileId] as const;

export const ReviewRecordLines: React.FC<{ summary: ReviewRecordSummary }> = ({ summary }) => {
  const { t } = useTranslation();
  if (!summary.available) {
    return (
      <p data-testid="review-record-unavailable">
        {t('readerRecord.notAvailable', 'No lesion-by-lesion record: the original AI draft was not kept for this draft.')}
      </p>
    );
  }
  const u = summary.unaided;
  return (
    <div data-testid="review-record">
      <p>
        {t('readerRecord.summary',
          'What you did with the AI draft: of its {{draft}} lesions, {{kept}} kept, {{corrected}} corrected, {{removed}} removed; {{added}} added by you.',
          { draft: summary.draft_lesions ?? 0, kept: summary.kept ?? 0, corrected: summary.corrected ?? 0,
            removed: summary.removed ?? 0, added: summary.added ?? 0 })}
      </p>
      {u && (
        <p data-testid="review-record-unaided">
          {t('readerRecord.unaided',
            'Against your reading before the draft: {{both}} found by you and the AI, {{readerOnly}} by you only, {{adopted}} taken from the draft, {{later}} added later, {{dropped}} of yours dropped.',
            { both: u.reader_and_draft, readerOnly: u.reader_only, adopted: u.adopted_from_draft,
              later: u.added_later, dropped: u.dropped_after_draft })}
        </p>
      )}
    </div>
  );
};

function useAssignment(fileId: string | null | undefined) {
  return useQuery({
    queryKey: readerStudyKey(fileId ?? ''),
    queryFn: () => segmentationAPI.readerStudyAssignment(fileId as string),
    enabled: Boolean(fileId),
    staleTime: 30_000,
    retry: 1,
  });
}

/**
 * Renders `children` (the in-browser AI) unless the image is in the set read without the draft first and the reader
 * has not recorded their reading yet. While the server's answer is pending nothing is shown; if it cannot be read,
 * the AI is offered as before (the study's record then counts only a reading recorded before the draft was saved).
 */
export const ReaderStudyGate: React.FC<{ fileId: string; children: React.ReactNode }> = ({ fileId, children }) => {
  const { t } = useTranslation();
  const { data, isLoading } = useAssignment(fileId);
  if (isLoading) return null;
  if (data?.unaided_first && !data.reading_recorded && !data.own_draft_saved) {
    return (
      <div className="mt-2 rounded border border-violet-500/50 bg-violet-950/30 p-2 text-[10px] leading-snug text-violet-100"
           role="status" data-testid="reader-study-gate">
        <p className="font-semibold">
          {t('readerRecord.unaidedFirstTitle', 'Reader study: read this image without the AI first')}
        </p>
        <p>
          {t('readerRecord.unaidedFirstBody',
            'This image is in the set read without the AI draft first. Draw your own reading, save it, then record it in the segmentation panel. The AI draft is offered after that.')}
        </p>
      </div>
    );
  }
  return <>{children}</>;
};

interface UnaidedReadingCardProps {
  fileId: string;
  segmentationId: string;
  /** the open segmentation carries AI provenance, or is not saved, or has unsaved changes: nothing to record */
  recordable: boolean;
}

export const UnaidedReadingCard: React.FC<UnaidedReadingCardProps> = ({ fileId, segmentationId, recordable }) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data } = useAssignment(fileId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!data?.unaided_first) return null;
  if (data.reading_segmentation_ids.includes(segmentationId)) {
    return (
      <p className="mt-1 text-[10px] text-violet-200" data-testid="unaided-reading-recorded">
        {t('readerRecord.recorded', 'Recorded as your reading before the AI draft.')}
      </p>
    );
  }
  if (data.reading_recorded || data.own_draft_saved || !recordable) return null;

  const record = async () => {
    setError(null);
    const ok = window.confirm(t('readerRecord.recordQuestion',
      'Record this saved segmentation as your own reading of the image before the AI draft? It is kept as it is now and cannot be changed or replaced.'));
    if (!ok) return;
    setBusy(true);
    try {
      const digest = await useSegmentationStore.getState().maskDigestCallback?.();
      if (!digest) throw new Error('The open mask could not be read; reload the segmentation and try again.');
      await segmentationAPI.recordUnaidedReading(segmentationId, digest);
      await queryClient.invalidateQueries({ queryKey: readerStudyKey(fileId) });
    } catch (e: any) {
      const reason = e?.response?.data?.error?.message || e?.response?.data?.detail || (e instanceof Error ? e.message : String(e));
      setError(t('readerRecord.recordFailed', 'Not recorded: {{reason}}', { reason }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-1.5" data-testid="unaided-reading-card">
      <button onClick={record} disabled={busy}
              className="px-2 py-0.5 rounded bg-violet-700 hover:bg-violet-600 disabled:opacity-50 text-white text-[10px]">
        {t('readerRecord.recordButton', 'Record as my reading before the AI (cannot be changed)')}
      </button>
      {error && <p className="text-red-300 text-[10px]" role="alert">{error}</p>}
    </div>
  );
};
