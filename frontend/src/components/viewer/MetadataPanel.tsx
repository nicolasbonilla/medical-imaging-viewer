/**
 * Panel component displaying image metadata.
 * Shows patient information, study details, and modality.
 */

import { useTranslation } from 'react-i18next';
import type { ImageMetadata } from '@/types';

interface MetadataPanelProps {
  metadata: ImageMetadata;
  patientName?: string;
  studyDescription?: string;
  modality?: string;
}

export function MetadataPanel({ metadata, patientName, studyDescription, modality }: MetadataPanelProps) {
  const { t } = useTranslation();

  // Use explicit props if provided, fallback to metadata
  const displayPatientName = patientName || metadata.patient_name || t('viewer.unknown');
  const displayStudyDesc = studyDescription || metadata.study_description || 'N/A';
  const displayModality = modality || metadata.modality || 'N/A';

  return (
    <div className="absolute top-4 left-4 bg-gray-900 bg-opacity-90 rounded-lg px-4 py-2 text-xs text-gray-300 space-y-1">
      <div>{t('viewer.patient')}: {displayPatientName}</div>
      <div>{t('viewer.study')}: {displayStudyDesc}</div>
      <div>{t('viewer.modality')}: {displayModality}</div>
    </div>
  );
}
