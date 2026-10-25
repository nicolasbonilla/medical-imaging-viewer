/**
 * AutomaticMarkingNotice — information for safety wherever an automatic LESION segmentation is shown
 * (PRB-003, RC-072, REQ-SAFE-040).
 *
 * Paper A (100 public healthy controls, one site): the raw automatic FLAMeS segmentation marked at least one
 * spot in 85 of 100 healthy brains, 63 % of them next to the ventricles. Wording A of the paper's app spec,
 * without numbers until the dataset licence is clarified for a commercial product ("most" itself rests on that
 * CC BY-NC data: owner decision). Shown for lesion-detection tools only (in-browser FLAMeS, FLAMeS worker,
 * LST-AI, mindGlide lesions) — not for structure parcellations (SynthSeg, mindGlide structures), where it would
 * be wrong (review of PR #68, finding 9). Same text as the backend (`dis_review_gate.AUTOMATIC_MARKING_NOTICE`).
 */
import React from 'react';
import { useTranslation } from 'react-i18next';

export const AUTOMATIC_MARKING_NOTICE_EN =
  'Automatic lesion marking also marks spots in most healthy brains, mostly next to the ventricles. ' +
  'A marked spot is not evidence of multiple sclerosis; every spot needs expert review.';

/** FLAMeS (worker or browser), LST-AI and the mindGlide LESION output — not structure parcellations. */
export function isLesionDetectionSource(validationSource: string | null | undefined): boolean {
  const vs = (validationSource ?? '').trim().toLowerCase();
  return vs.startsWith('flames') || vs.startsWith('lst-ai') || vs === 'mindglide-v1.0';
}

export const AutomaticMarkingNotice: React.FC<{ className?: string }> = ({ className }) => {
  const { t } = useTranslation();
  return (
    <p className={className ?? 'mt-1 text-[10px] leading-snug text-amber-200'} data-testid="automatic-marking-notice">
      {t('disReview.automaticMarkingNotice', AUTOMATIC_MARKING_NOTICE_EN)}
    </p>
  );
};

export default AutomaticMarkingNotice;
