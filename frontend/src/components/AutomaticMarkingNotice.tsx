/**
 * AutomaticMarkingNotice — information for safety wherever an automatic LESION segmentation is shown
 * (PRB-003, RC-072, REQ-SAFE-040).
 *
 * PRB-033: "most" rests on CC0 data (Dallas Lifespan Brain Study, internal and unpublished: the raw automatic FLAMeS
 * segmentation marked at least one spot in 72 of 75 adults aged 21-49 and 100 of 100 aged 50-89 without CNS disease).
 * The former "mostly next to the ventricles" held in one other cohort only and was removed. Shown for lesion-detection tools only (in-browser FLAMeS, FLAMeS worker,
 * LST-AI, mindGlide lesions) — not for structure parcellations (SynthSeg, mindGlide structures), where it would
 * be wrong (review of PR #68, finding 9). Same text as the backend (`dis_review_gate.AUTOMATIC_MARKING_NOTICE`).
 */
import React from 'react';
import { useTranslation } from 'react-i18next';

export const AUTOMATIC_MARKING_NOTICE_EN =
  'Automatic lesion marking also marks spots in most people without neurological disease, in any region of the brain. ' +
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
