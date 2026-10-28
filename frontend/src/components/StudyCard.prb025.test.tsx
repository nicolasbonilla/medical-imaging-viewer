/**
 * PRB-025 (F07) — the study card's "SEGM." was hard-coded to 0 (`StudyCard.tsx:64`, a constant `undefined`
 * rendered as `?? 0`), whatever the study held. Wanted: the count the server reports for the study
 * (`segmentation_count`, zone maps excluded); "—" when the server did not report one — never a 0 that
 * looks like a measurement.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import i18n from '@/i18n/config';
import { StudyCard } from './StudyCard';
import PatientCard from './PatientCard';
import type { StudySummary } from '@/types';

const base = {
  id: 'a1111111-1111-4111-8111-111111111111',
  patient_id: '11111111-1111-4111-8111-111111111111',
  accession_number: 'ACC-1',
  modality: 'MR',
  study_date: '2026-09-30T00:00:00',
  study_description: 'Brain MRI',
  status: 'available',
  series_count: 4,
  instance_count: 4,
  total_size_bytes: 18_000_000,
} as unknown as StudySummary;

function segmCell(): HTMLElement {
  const label = screen.getByText(/^segm/i);
  return label.parentElement!.lastElementChild as HTMLElement;
}

describe('PRB-025 study card segmentation count', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('rc085 prb025 shows the number of segmentations the server reports', () => {
    render(<StudyCard study={{ ...base, segmentation_count: 2 } as StudySummary} onView={() => {}} />);
    expect(segmCell().textContent).toBe('2');
  });

  it('rc085 prb025 shows a dash, not 0, when the count is unknown', () => {
    render(<StudyCard study={base} onView={() => {}} />);
    expect(segmCell().textContent).toBe('—');
  });

  it('rc085 prb025 shows 0 only when the server reports 0', () => {
    render(<StudyCard study={{ ...base, segmentation_count: 0 } as StudySummary} onView={() => {}} />);
    expect(segmCell().textContent).toBe('0');
  });

  it('rc085 prb025 the patient card shows a dash for a count the server could not compute', () => {
    const patient = { id: 'p', mrn: 'DEMO-0001', full_name: 'Demo Patient', given_name: 'Demo', family_name: 'Patient',
      birth_date: '2000-01-01', gender: 'male', status: 'active', study_count: 1, document_count: null } as never;
    render(<PatientCard patient={patient} onSelect={() => {}} />);
    const cell = (label: RegExp) => screen.getByText(label).parentElement!.lastElementChild!.textContent;
    expect(cell(/^studies$/i)).toBe('1');
    expect(cell(/^documents$/i)).toBe('—');
  });
});
