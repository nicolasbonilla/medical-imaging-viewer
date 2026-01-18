import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { Patient, PatientSummary, ImagingStudy, StudySummary } from '@/types';

/**
 * Patient Store
 *
 * Global state management for the currently selected patient and study context.
 * Uses Zustand with persistence to maintain state across page refreshes.
 */

export interface PatientListPreferences {
  viewMode: 'grid' | 'list';
  pageSize: number;
  sortField: 'name' | 'mrn' | 'created_at' | 'birth_date';
  sortOrder: 'asc' | 'desc';
}

interface PatientState {
  // Current selected patient (full data)
  selectedPatient: Patient | null;

  // Currently selected study (for viewer context)
  selectedStudy: ImagingStudy | StudySummary | null;

  // Recently viewed patients (for quick access)
  recentPatients: PatientSummary[];

  // UI state
  isPatientFormOpen: boolean;
  patientFormMode: 'create' | 'edit';
  patientToEdit: Patient | null;

  // Search state
  searchQuery: string;
  statusFilter: string | null;

  // List preferences
  listPreferences: PatientListPreferences;

  // Actions
  setSelectedPatient: (patient: Patient | null) => void;
  setSelectedStudy: (study: ImagingStudy | StudySummary | null) => void;
  addToRecentPatients: (patient: PatientSummary) => void;
  clearRecentPatients: () => void;

  openPatientForm: (mode: 'create' | 'edit', patient?: Patient) => void;
  closePatientForm: () => void;

  setSearchQuery: (query: string) => void;
  setStatusFilter: (status: string | null) => void;
  clearFilters: () => void;

  setListPreferences: (prefs: Partial<PatientListPreferences>) => void;

  reset: () => void;
}

const MAX_RECENT_PATIENTS = 10;

const defaultListPreferences: PatientListPreferences = {
  viewMode: 'grid',
  pageSize: 12,
  sortField: 'created_at',
  sortOrder: 'desc',
};

const initialState = {
  selectedPatient: null,
  selectedStudy: null,
  recentPatients: [],
  isPatientFormOpen: false,
  patientFormMode: 'create' as const,
  patientToEdit: null,
  searchQuery: '',
  statusFilter: null,
  listPreferences: defaultListPreferences,
};

export const usePatientStore = create<PatientState>()(
  persist(
    (set, get) => ({
      ...initialState,

      setSelectedPatient: (patient) => {
        set({ selectedPatient: patient });

        // Add to recent patients if not null
        if (patient) {
          const summary: PatientSummary = {
            id: patient.id,
            mrn: patient.mrn,
            full_name: patient.full_name,
            birth_date: patient.birth_date,
            gender: patient.gender,
            status: patient.status,
          };
          get().addToRecentPatients(summary);
        }
      },

      setSelectedStudy: (study) => {
        set({ selectedStudy: study });
      },

      addToRecentPatients: (patient) => {
        set((state) => {
          // Remove if already exists
          const filtered = state.recentPatients.filter(p => p.id !== patient.id);
          // Add to beginning
          const updated = [patient, ...filtered].slice(0, MAX_RECENT_PATIENTS);
          return { recentPatients: updated };
        });
      },

      clearRecentPatients: () => {
        set({ recentPatients: [] });
      },

      openPatientForm: (mode, patient) => {
        set({
          isPatientFormOpen: true,
          patientFormMode: mode,
          patientToEdit: patient || null,
        });
      },

      closePatientForm: () => {
        set({
          isPatientFormOpen: false,
          patientToEdit: null,
        });
      },

      setSearchQuery: (query) => {
        set({ searchQuery: query });
      },

      setStatusFilter: (status) => {
        set({ statusFilter: status });
      },

      clearFilters: () => {
        set({
          searchQuery: '',
          statusFilter: null,
        });
      },

      setListPreferences: (prefs) => {
        set((state) => ({
          listPreferences: { ...state.listPreferences, ...prefs },
        }));
      },

      reset: () => {
        set(initialState);
      },
    }),
    {
      name: 'patient-storage',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        // Only persist recent patients, search state, and preferences
        recentPatients: state.recentPatients,
        searchQuery: state.searchQuery,
        statusFilter: state.statusFilter,
        listPreferences: state.listPreferences,
      }),
    }
  )
);

// Selector hooks for common patterns
export const useSelectedPatient = () => usePatientStore((state) => state.selectedPatient);
export const useSelectedStudy = () => usePatientStore((state) => state.selectedStudy);
export const useRecentPatients = () => usePatientStore((state) => state.recentPatients);
export const usePatientListPreferences = () => usePatientStore((state) => state.listPreferences);
