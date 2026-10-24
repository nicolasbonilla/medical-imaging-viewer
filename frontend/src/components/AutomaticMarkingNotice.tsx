/**
 * AutomaticMarkingNotice — information for safety wherever an automatic segmentation is shown
 * (PRB-003, RC-072, REQ-SAFE-040).
 *
 * Paper A (100 public healthy controls, one site): the raw automatic FLAMeS segmentation marked at least one
 * spot in 85 of 100 healthy brains, 63 % of them next to the ventricles. Wording A of the paper's app spec,
 * without numbers until the dataset licence is clarified for a commercial product. Same text as the backend
 * (`dis_review_gate.AUTOMATIC_MARKING_NOTICE`), in the reader's language.
 */
import React from 'react';
import { useTranslation } from 'react-i18next';

export const AUTOMATIC_MARKING_NOTICE_EN =
  'Automatic marking also marks spots in most healthy brains, mostly next to the ventricles. ' +
  'A marked spot is not evidence of multiple sclerosis; every spot needs expert review.';

export const AutomaticMarkingNotice: React.FC<{ className?: string }> = ({ className }) => {
  const { t } = useTranslation();
  return (
    <p className={className ?? 'mt-1 text-[10px] leading-snug text-amber-200'} data-testid="automatic-marking-notice">
      {t('disReview.automaticMarkingNotice', AUTOMATIC_MARKING_NOTICE_EN)}
    </p>
  );
};

export default AutomaticMarkingNotice;
