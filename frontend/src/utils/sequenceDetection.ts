/**
 * Sequence Detection Utility
 *
 * Detects MRI sequence type from BIDS filenames.
 * Used by the multi-panel viewer to auto-assign sequences to panels.
 *
 * @module utils/sequenceDetection
 */

import type { ImagingInstance } from '@/types';

export type SequenceType = 'FLAIR' | 'T1w' | 'T2w' | 'PDw' | 'unknown';

/** Display labels and colors for each sequence type */
export const SEQUENCE_INFO: Record<SequenceType, { label: string; color: string; shortLabel: string }> = {
  FLAIR: { label: 'FLAIR', color: '#F59E0B', shortLabel: 'FL' },
  T1w: { label: 'T1-weighted', color: '#3B82F6', shortLabel: 'T1' },
  T2w: { label: 'T2-weighted', color: '#10B981', shortLabel: 'T2' },
  PDw: { label: 'Proton Density', color: '#8B5CF6', shortLabel: 'PD' },
  unknown: { label: 'Unknown', color: '#6B7280', shortLabel: '?' },
};

/**
 * Detect MRI sequence type from a filename.
 * Supports BIDS naming (sub-MS001_ses-01_FLAIR.nii.gz) and legacy names (test01_flair.nii).
 */
export function detectSequence(filename: string): SequenceType {
  const lower = filename.toLowerCase();

  // FLAIR must be checked before T2 (some FLAIR files contain "t2" in path)
  if (lower.includes('flair')) return 'FLAIR';

  // T1-weighted variants
  if (lower.includes('t1w') || lower.includes('_t1.') || lower.includes('_t1_')
    || lower.includes('mprage') || lower.includes('t1w.')) return 'T1w';

  // T2-weighted
  if (lower.includes('t2w') || lower.includes('_t2.') || lower.includes('_t2_')
    || lower.includes('t2w.')) return 'T2w';

  // Proton Density
  if (lower.includes('pdw') || lower.includes('_pd.') || lower.includes('_pd_')
    || lower.includes('pdw.')) return 'PDw';

  return 'unknown';
}

/**
 * Group instances by detected sequence type.
 * Only includes original (non-mask, non-preprocessed) instances.
 */
export function groupInstancesBySequence(
  instances: ImagingInstance[],
): Map<SequenceType, ImagingInstance[]> {
  const groups = new Map<SequenceType, ImagingInstance[]>();

  for (const inst of instances) {
    const fn = inst.original_filename || '';
    const seq = detectSequence(fn);
    const existing = groups.get(seq) || [];
    existing.push(inst);
    groups.set(seq, existing);
  }

  return groups;
}

/** Canonical order for displaying sequences in the multi-panel viewer */
export const SEQUENCE_ORDER: SequenceType[] = ['FLAIR', 'T1w', 'T2w', 'PDw'];

/**
 * Auto-assign instances to panel slots based on sequence detection.
 * Returns up to 4 instances in canonical order (FLAIR, T1, T2, PD).
 */
export function autoAssignPanels(
  instances: ImagingInstance[],
): { instance: ImagingInstance; sequence: SequenceType }[] {
  const groups = groupInstancesBySequence(instances);
  const assigned: { instance: ImagingInstance; sequence: SequenceType }[] = [];

  for (const seq of SEQUENCE_ORDER) {
    const seqInstances = groups.get(seq);
    if (seqInstances && seqInstances.length > 0) {
      assigned.push({ instance: seqInstances[0], sequence: seq });
    }
    if (assigned.length >= 4) break;
  }

  // Fill remaining slots with unknown sequences if needed
  if (assigned.length < 4) {
    const unknowns = groups.get('unknown') || [];
    for (const inst of unknowns) {
      if (assigned.length >= 4) break;
      assigned.push({ instance: inst, sequence: 'unknown' });
    }
  }

  return assigned;
}
