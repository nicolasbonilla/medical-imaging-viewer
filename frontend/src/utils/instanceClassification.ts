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
