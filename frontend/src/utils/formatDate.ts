import i18n from '@/i18n/config';

/**
 * Locale-aware date formatting.
 *
 * `Date.prototype.toLocaleDateString()` with no locale argument falls back to
 * the host OS locale, which leaks the wrong language into the UI (e.g. a
 * Spanish "12 de jul de 2026" in an English session). These helpers format in
 * the active i18n UI language instead, keeping dates consistent with the rest
 * of the interface across en/es/de.
 */

const DEFAULT_OPTS: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
};

/** Format a date (Date or parseable string) in the active UI language. */
export function formatDate(
  value: string | number | Date | null | undefined,
  opts: Intl.DateTimeFormatOptions = DEFAULT_OPTS,
): string {
  if (value === null || value === undefined || value === '') return '—';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString(i18n.language, opts);
}

/** Format a date with time in the active UI language. */
export function formatDateTime(
  value: string | number | Date | null | undefined,
): string {
  if (value === null || value === undefined || value === '') return '—';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(i18n.language, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
