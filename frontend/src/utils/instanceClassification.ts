/**
 * Filename-based classification of study instances.
 */

/**
 * True if an instance filename denotes a PREPROCESSED image.
 *
 * Supports both the legacy convention (`*_pp.nii` / `*_pp.nii.gz`) and BIDS
 * derivatives (`*desc-preproc*`, `*desc-segfrompreproc*`). Case-insensitive.
 *
 * Extracted from ViewerApp's inline JSX heuristic (Fase 2.2) so it is a pure,
 * unit-tested function instead of untested logic embedded in render.
 */
export function isPreprocessedInstance(filename: string): boolean {
  const lower = filename.toLowerCase();
  return (
    lower.endsWith('_pp.nii') ||
    lower.endsWith('_pp.nii.gz') ||
    lower.includes('desc-preproc') ||
    lower.includes('desc-segfrompreproc')
  );
}

export type MultiPanelImageSource = 'originals' | 'preprocessed';

/**
 * PRB-007: the images the multi-panel grid shows. The requested group when it has images,
 * otherwise the other group — a study of preprocessed images only (the demo study, any study
 * uploaded preprocessed) used to give a grid of "No image assigned" panels because the grid read
 * the empty "originals" group. `source` is the group actually shown (for the switch's label).
 */
export function multiPanelImages<T>(
  requested: MultiPanelImageSource,
  originals: T[],
  preprocessed: T[],
): { source: MultiPanelImageSource; instances: T[] } {
  if (requested === 'preprocessed' && preprocessed.length > 0) return { source: 'preprocessed', instances: preprocessed };
  if (originals.length > 0) return { source: 'originals', instances: originals };
  return { source: 'preprocessed', instances: preprocessed };
}
