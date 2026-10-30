/**
 * Patient display helpers shared by every view — PRB-026 (F16; HAZ-009 patient identification).
 *
 * One record showed "DD" on the patient list and "DP" on its record page: the card took the first and LAST
 * word of the full name (the list item had no name parts), the banner the first two words (a title such as
 * "Dr." became an initial). The rule is now one function: the first LETTER of the given name and of the
 * family name, upper-cased in the user's language rules. The full name is used only when a name part is
 * missing (records from an older server), and then its first two words.
 */

interface NameParts {
  given_name?: string | null;
  family_name?: string | null;
  full_name?: string | null;
}

const LETTER = /\p{L}/u;

function firstLetter(text?: string | null): string {
  const m = (text ?? '').match(LETTER);
  return m ? m[0] : '';
}

export function patientInitials(patient: NameParts): string {
  const given = firstLetter(patient.given_name);
  const family = firstLetter(patient.family_name);
  if (given && family) return (given + family).toLocaleUpperCase();
  const words = (patient.full_name ?? '').split(/\s+/).map(firstLetter).filter(Boolean);
  if (words.length >= 2) return (words[0] + words[1]).toLocaleUpperCase();
  if (words.length === 1) {
    const letters = Array.from((patient.full_name ?? '').matchAll(/\p{L}/gu)).map((m) => m[0]);
    return letters.slice(0, 2).join('').toLocaleUpperCase() || '??';
  }
  return '??';
}
