/**
 * Review of PR #70 — M3 (PRB-021) and m5 (PRB-025), m7 (PRB-022).
 *
 * M3: after PRB-021 a clinician sees only the patients of their care team. A clinician with no assignment yet saw
 *     "No patients registered — Start by registering your first patient" and the tile "Patients 0 in registry": false,
 *     and an invitation to register a patient that already exists (a duplicate record whose earlier scans are then
 *     missing from comparisons, HAZ-009). Wanted for a non-administrator: "No patients are assigned to you yet. An
 *     administrator can add you to a patient's care team." — no "create first patient" button — and the tile labelled
 *     "assigned to you". An administrator keeps the registry wording.
 * m5: the tiles added a count the server could not compute (null) as 0; wanted "—".
 * m7: the sign-in page kept a badge "IEC 62304 · Class C" next to the removed certification badges.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import i18n from '@/i18n/config';

let role = 'radiologist';
let listItems: unknown[] = [];
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', username: 'dr_x', full_name: 'Dr X', role, email: 'x@example.org' },
    logout: vi.fn(), login: vi.fn(), loginWithPasskey: vi.fn(), register: vi.fn(), isAuthenticated: true }),
}));
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ theme: 'dark', toggleTheme: vi.fn() }) }));
vi.mock('@/hooks/usePatients', () => ({
  usePatientList: () => ({ data: { items: listItems, total: listItems.length, page: 1, page_size: 12, total_pages: 1 },
    isLoading: false, isFetching: false, refetch: vi.fn() }),
  useDeletePatient: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock('@/components/AppHeader', () => ({ default: () => null }));
vi.mock('@/components/PatientForm', () => ({ default: () => null }));

import PatientsPage from './PatientsPage';
import { PatientsOverview } from '@/components/patients/PatientsOverview';

function renderPage() {
  return render(<MemoryRouter><PatientsPage /></MemoryRouter>);
}

describe('PRB-021 patients page for a user without assignments', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
    listItems = [];
  });

  it('rc082 prb021 a clinician with no patient is told none are assigned, with no create invitation', () => {
    role = 'radiologist';
    renderPage();
    expect(screen.getByText('No patients are assigned to you yet')).toBeInTheDocument();
    expect(screen.getByText("An administrator can add you to a patient's care team.")).toBeInTheDocument();
    expect(screen.queryByText('No patients registered')).toBeNull();
    expect(screen.queryByRole('button', { name: /create first patient/i })).toBeNull();
    expect(screen.getByText('assigned to you')).toBeInTheDocument();
    expect(screen.queryByText('in registry')).toBeNull();
  });

  it('rc082 prb021 an administrator keeps the registry wording and the create invitation', () => {
    role = 'admin';
    renderPage();
    expect(screen.getByText('No patients registered')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create first patient/i })).toBeInTheDocument();
    expect(screen.getByText('in registry')).toBeInTheDocument();
  });
});

describe('PRB-025 overview tiles never turn an uncounted value into 0', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
  });

  const tileValue = (label: string) => screen.getByText(label).previousElementSibling!.textContent;

  it('rc085 prb025 a null study or document count shows a dash', () => {
    render(<PatientsOverview total={2} patients={[
      { status: 'active', study_count: 2, document_count: null },
      { status: 'active', study_count: null, document_count: 1 },
    ]} />);
    expect(tileValue('MRI Studies')).toBe('—');
    expect(tileValue('Documents')).toBe('—');
  });

  it('rc085 prb025 counted values are still summed', () => {
    render(<PatientsOverview total={2} patients={[
      { status: 'active', study_count: 2, document_count: 0 },
      { status: 'inactive', study_count: 3, document_count: 1 },
    ]} />);
    expect(tileValue('MRI Studies')).toBe('5');
    expect(tileValue('Documents')).toBe('1');
  });
});
