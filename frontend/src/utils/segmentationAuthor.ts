/**
 * Who created a segmentation — PRB-026 (F06).
 *
 * The viewer filled every segmentation's author with the placeholder "current_user" and showed it. The server
 * now records the authenticated user at creation (`metadata.created_by`, never taken from the request). The
 * viewer shows exactly that; when nothing was recorded (older segmentations, tool or script imports) it says
 * "Author not recorded" — it never substitutes a placeholder or the name of whoever is signed in.
 */

interface WithCreator {
  created_by?: string | null;
}

/** The author recorded by the server, or '' when none was recorded. */
export function recordedAuthor(metadata?: WithCreator | null): string {
  const value = metadata?.created_by;
  return typeof value === 'string' ? value.trim() : '';
}

/** The text shown for a segmentation's author. */
export function authorLabel(
  segmentation: { created_by?: string | null; created_by_name?: string | null },
  t: (key: string, fallback: string) => string,
): string {
  return (
    (segmentation.created_by_name || '').trim() ||
    (segmentation.created_by || '').trim() ||
    t('segmentation.authorNotRecorded', 'Author not recorded')
  );
}
