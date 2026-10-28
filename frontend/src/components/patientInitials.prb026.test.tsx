/**
 * PRB-026 (F16) — one patient, two different initials: the patient list card showed "DD" and the record page
 * "DP" for "Demo Patient (public data)". The card built them from the first and LAST word of the full name
 * (the list item carried no given/family name), the banner from the first two words of the full name (a
 * title such as "Dr." gave "DA" for Dr. Anna Beispiel). An avatar is a patient-identification cue (HAZ-009):
 * the same record must show the same initials everywhere. Wanted: one rule — first letter of the given name
 * and of the family name — in both places, and the list item carries both names (backend part:
 * test_prb021_patient_scope_creator_counts.py::test_rc087_prb026_patient_list_item_carries_given_and_family_name).
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PatientCard from './PatientCard';
import PatientBanner from './PatientBanner';
import type { Patient } from '@/types';

// Loaded through a glob so that, on the base commit (no helper yet), each test fails on its own assertion.
const helper = import.meta.glob('../utils/patientDisplay.ts', { eager: true }) as Record<
  string, { patientInitials?: (p: Patient) => string }>;
function patientInitials(p: Patient): string {
  const fn = Object.values(helper)[0]?.patientInitials;
  if (!fn) throw new Error('no shared initials rule (utils/patientDisplay.ts::patientInitials)');
  return fn(p);
}

const detail = (over: Partial<Patient>): Patient => ({
  id: '11111111-1111-4111-8111-111111111111',
  mrn: 'DEMO-0001',
  given_name: 'Demo',
  family_name: 'Patient (public data)',
  full_name: 'Demo Patient (public data)',
  birth_date: '2000-01-01',
  gender: 'male',
  status: 'active',
  phone_mobile: '+10000000000',
  country: 'DEU',
  age: 26,
  created_at: '2026-10-28T10:00:00',
  updated_at: '2026-10-28T10:00:00',
  ...over,
} as Patient);

/** What GET /patients returned for the list on main @ 70cc5c7: no given or family name. */
const baseListItem = (p: Patient) => ({
  id: p.id, mrn: p.mrn, full_name: p.full_name, birth_date: p.birth_date, gender: p.gender, status: p.status,
  study_count: 3, document_count: 0,
}) as unknown as Patient;

/** The avatar: the only leaf element whose whole text is two capital letters (or "??"). */
function avatarText(container: HTMLElement): string {
  const leaves = Array.from(container.querySelectorAll('*')).filter(
    (el) => el.children.length === 0 && /^(\p{Lu}{2}|\?\?)$/u.test((el.textContent || '').trim()),
  );
  expect(leaves.length, 'exactly one avatar').toBe(1);
  return (leaves[0].textContent || '').trim();
}

function cardInitials(p: Patient): string {
  const { container, unmount } = render(<PatientCard patient={p} onSelect={() => {}} />);
  const text = avatarText(container);
  unmount();
  return text;
}

function bannerInitials(p: Patient): string {
  const { container, unmount } = render(<PatientBanner patient={p} />);
  expect(screen.getByRole('banner')).toBeInTheDocument();
  const text = avatarText(container);
  unmount();
  return text;
}

describe('PRB-026 patient initials are the same on the list and on the record', () => {
  it('rc087 prb026 the rule: first letter of the given name and of the family name', () => {
    expect(patientInitials(detail({}))).toBe('DP');
    expect(patientInitials(detail({ given_name: 'anna', family_name: 'de la Cruz', full_name: 'anna de la Cruz' }))).toBe('AD');
    expect(patientInitials(detail({ given_name: 'Álvaro', family_name: 'Öz', full_name: 'Álvaro Öz' }))).toBe('ÁÖ');
  });

  it('rc087 prb026 a title in the full name does not change the initials', () => {
    const p = detail({ name_prefix: 'Dr.', given_name: 'Anna', family_name: 'Beispiel', full_name: 'Dr. Anna Beispiel' });
    expect(bannerInitials(p)).toBe('AB');
    expect(cardInitials(p)).toBe('AB');
  });

  it('rc087 prb026 the list card of the capture shows the same initials as the record page', () => {
    const record = detail({});
    expect(bannerInitials(record)).toBe('DP');
    expect(cardInitials(baseListItem(record))).toBe('DP');
  });

  it('rc087 prb026 punctuation is never an initial', () => {
    expect(patientInitials(detail({ given_name: '(Demo)', family_name: '"Patient"', full_name: '(Demo) "Patient"' }))).toBe('DP');
  });
});
