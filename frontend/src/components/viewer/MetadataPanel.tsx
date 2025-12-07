/**
 * Panel component displaying image metadata.
 * Shows patient information, study details, and modality.
 */

import { useTranslation } from 'react-i18next';
import type { ImageMetadata } from '@/types';

interface MetadataPanelProps {
  metadata: ImageMetadata;
}

export function MetadataPanel({ metadata }: MetadataPanelProps) {
  const { t } = useTranslation();

  return (
    <div className="absolute top-4 left-4 bg-gray-900 bg-opacity-90 rounded-lg px-4 py-2 text-xs text-gray-300 space-y-1">
      <div>{t('viewer.patient')}: {metadata.patient_name || t('viewer.unknown')}</div>
      <div>{t('viewer.study')}: {metadata.study_description || 'N/A'}</div>
      <div>{t('viewer.modality')}: {metadata.modality || 'N/A'}</div>
    </div>
  );
}
