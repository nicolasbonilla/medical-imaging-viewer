/**
 * Sequence Detection Utility
 *
 * Detects MRI sequence type from BIDS filenames.
 * Used by the multi-panel viewer to auto-assign sequences to panels.
 *
 * @module utils/sequenceDetection
 */

import type { ImagingInstance } from '@/types';
import { isPreprocessedInstance, isSegmentationDerivative } from './instanceClassification';

export type SequenceType = 'FLAIR' | 'T1w' | 'T2w' | 'PDw' | 'unknown';

/** Display labels and colors for each sequence type */
export const SEQUENCE_INFO: Record<SequenceType, { label: string; color: string; shortLabel: string }> = {
  FLAIR: { label: 'FLAIR', color: '#F59E0B', shortLabel: 'FL' },
  T1w: { label: 'T1-weighted', color: '#3B82F6', shortLabel: 'T1' },
  T2w: { label: 'T2-weighted', color: '#10B981', shortLabel: 'T2' },
  PDw: { label: 'Proton Density', color: '#8B5CF6', shortLabel: 'PD' },
  unknown: { label: 'Unknown', color: '#767E8E', shortLabel: '?' },
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

/** The sequence a BIDS name ends with, and only that: a name that merely mentions FLAIR somewhere (space-FLAIR, T1w_to_FLAIR) is not one. */
export function sequenceFromSuffix(filename: string): string | null {
  const names: Record<string, string> = { flair: 'FLAIR', t1w: 'T1', t2w: 'T2', pdw: 'PD', t2starw: 'T2*' };
  const segments = filename.replace(/\.nii(\.gz)?$/i, '').toLowerCase().split('_');
  const suffix = segments[segments.length - 1];
  // a second sequence word anywhere else (T1w_to_FLAIR) makes the name ambiguous: no sequence is claimed
  if (!names[suffix] || segments.slice(0, -1).some((s) => names[s])) return null;
  return names[suffix];
}

const entity = (name: string, key: string) => name.match(new RegExp(`(?:^|_)${key}-([A-Za-z0-9]+)`, 'i'))?.[1];

/**
 * What a person reads in a list: the sequence and what tells two images apart (after contrast, acquisition, space, run), not the
 * research file name, which stays in the tooltip. Anything not stated in a recognisable way is shown as it is: an image is never
 * given a sequence, and a mask never an author, the file name does not state.
 */
export function friendlyImageName(filename: string): string {
  const lower = filename.toLowerCase().replace(/\.nii(\.gz)?$/, '');
  if (isSegmentationDerivative(filename) || /(?:^|_)label-|lesion/.test(lower)) {
    const rater = lower.match(/(?:^|_)(?:rater|expert)-?(\d{1,2})(?:_|$)/)?.[1];
    if (rater) return `Expert lesions ${Number(rater)}`;
    return filename;
  }
  const sequence = sequenceFromSuffix(filename);
  if (!sequence) return filename;
  const parts = [sequence];
  const base = filename.replace(/\.nii(\.gz)?$/i, '');
  const contrast = entity(base, 'ce');
  if (contrast) parts.push(`after contrast (${contrast})`);
  const acq = entity(base, 'acq');
  if (acq) parts.push(acq.toUpperCase());
  const space = entity(base, 'space');
  if (space) parts.push(`${space} space`);
  const run = entity(base, 'run');
  if (run) parts.push(`run ${run}`);
  return parts.join(' · ') + (isPreprocessedInstance(filename) ? ' (preprocessed)' : '');
}

/** Labels for a list: where two images would read the same, both show their full file name. */
export function distinctImageNames(filenames: readonly string[]): string[] {
  const friendly = filenames.map(friendlyImageName);
  return friendly.map((name, i) => (friendly.indexOf(name) !== friendly.lastIndexOf(name) ? filenames[i] : name));
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
 * Returns up to 4 instances: one per sequence in canonical order (FLAIR, T1, T2, PD), then
 * images of unknown sequence, then (PRB-007) the remaining images in study order — e.g. a T1w
 * after contrast next to the plain T1w — so no panel stays empty while the study has an image
 * for it. An image is never assigned twice.
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

  // PRB-007: then any image not yet shown, in study order (a second image of a sequence).
  const shown = new Set(assigned.map((a) => a.instance));
  for (const inst of instances) {
    if (assigned.length >= 4) break;
    if (shown.has(inst)) continue;
    assigned.push({ instance: inst, sequence: detectSequence(inst.original_filename || '') });
    shown.add(inst);
  }

  return assigned;
}
