import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import AppHeader from '../components/AppHeader';
import { toast, Toaster } from 'sonner';
import {
  Users,
  Plus,
  Search,
  Filter,
  Grid,
  List,
  SortAsc,
  SortDesc,
  Download,
  Upload,
  ChevronLeft,
  ChevronRight,
  Activity,
  LogOut,
  Sparkles,
  X,
} from 'lucide-react';
import { usePatientList, useDeletePatient } from '@/hooks/usePatients';
import { PatientsOverview } from '@/components/patients/PatientsOverview';
import PatientCard from '@/components/PatientCard';
import PatientForm from '@/components/PatientForm';
import { SkeletonCard } from '@/components/ui';
import ThemeToggle from '@/components/ThemeToggle';
import LanguageSelector from '@/components/LanguageSelector';
import UserMenu from '@/components/UserMenu';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import type { Patient, PatientStatus, Gender } from '@/types';

type ViewMode = 'grid' | 'list';
type SortField = 'name' | 'mrn' | 'created_at' | 'birth_date';
type SortOrder = 'asc' | 'desc';

interface Filters {
  search: string;
  status: PatientStatus | '';
  gender: Gender | '';
}

export default function PatientsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { theme } = useTheme();

  // UI State
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [showFilters, setShowFilters] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingPatient, setEditingPatient] = useState<Patient | null>(null);
  const [deletingPatientId, setDeletingPatientId] = useState<string | null>(null);

  // Pagination & Sorting
  const [page, setPage] = useState(1);
  const [pageSize] = useState(12);
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  // Filters
  const [filters, setFilters] = useState<Filters>({
    search: '',
    status: '',
    gender: '',
  });

  // When search/gender filter is active, fetch all patients for client-side filtering
  const hasClientFilter = !!filters.search || !!filters.gender;
  const {
    data: patientsData,
    isLoading,
    isFetching,
    refetch,
  } = usePatientList(
    hasClientFilter ? 1 : page,
    hasClientFilter ? 100 : pageSize,
    filters.status || undefined
  );

  const deletePatientMutation = useDeletePatient();

  // Handlers
  const handlePatientSelect = useCallback((patient: Patient) => {
    navigate(`/app/patients/${patient.id}`);
  }, [navigate]);

  const handleCreatePatient = useCallback(() => {
    setShowCreateForm(true);
    setEditingPatient(null);
  }, []);

  const handleEditPatient = useCallback((patient: Patient) => {
    setEditingPatient(patient);
    setShowCreateForm(true);
  }, []);

  const handleDeletePatient = useCallback(async (patient: Patient) => {
    if (window.confirm(t('patients.confirmDelete', { name: patient.full_name }))) {
      setDeletingPatientId(patient.id);
      try {
        await deletePatientMutation.mutateAsync(patient.id);
        toast.success(t('patients.deleteSuccess'));
      } catch (error) {
        toast.error(t('patients.deleteFailed'));
        console.error('Delete patient error:', error);
      } finally {
        setDeletingPatientId(null);
      }
    }
  }, [deletePatientMutation, t]);

  const handleFormSuccess = useCallback(() => {
    setShowCreateForm(false);
    setEditingPatient(null);
    refetch();
    toast.success(
      editingPatient
        ? t('patients.updateSuccess')
        : t('patients.createSuccess')
    );
  }, [editingPatient, refetch, t]);

  const handleFormCancel = useCallback(() => {
    setShowCreateForm(false);
    setEditingPatient(null);
  }, []);

  const handleFilterChange = useCallback((key: keyof Filters, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setPage(1);
  }, []);

  const clearFilters = useCallback(() => {
    setFilters({ search: '', status: '', gender: '' });
    setPage(1);
  }, []);

  const toggleSortOrder = useCallback(() => {
    setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
  }, []);

  const hasActiveFilters = filters.search || filters.status || filters.gender;

  // Client-side filtering and sorting
  const allPatients = patientsData?.items || [];
  const filteredPatients = allPatients.filter((patient) => {
    // Search filter: match name or MRN
    if (filters.search) {
      const q = filters.search.toLowerCase();
      const nameMatch = patient.full_name?.toLowerCase().includes(q);
      const mrnMatch = patient.mrn?.toLowerCase().includes(q);
      if (!nameMatch && !mrnMatch) return false;
    }
    // Gender filter
    if (filters.gender && patient.gender !== filters.gender) return false;
    return true;
  }).sort((a, b) => {
    let cmp = 0;
    switch (sortField) {
      case 'name':
        cmp = (a.full_name || '').localeCompare(b.full_name || '');
        break;
      case 'mrn':
        cmp = (a.mrn || '').localeCompare(b.mrn || '');
        break;
      case 'birth_date':
        cmp = (a.birth_date || '').localeCompare(b.birth_date || '');
        break;
      default: // created_at
        cmp = (a.created_at || '').localeCompare(b.created_at || '');
    }
    return sortOrder === 'asc' ? cmp : -cmp;
  });

  const patients = filteredPatients;
  const totalPages = hasClientFilter ? 1 : (patientsData?.total_pages || 1);
  const total = hasClientFilter ? filteredPatients.length : (patientsData?.total || 0);

  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#08090C' }}>

      {/* Header */}
      <AppHeader
        title={t('patients.title')}
        subtitle={t('patients.subtitle', 'EHR Patient Management')}
        breadcrumbs={[
          { label: t('nav.home', 'Home'), path: '/app' },
          { label: t('patients.title') },
        ]}
        /* No rightControls — total count shown in "Showing X of Y" below */
      />

      {/* Main Content - WCAG 2.4.1 Skip Link Target */}
      <main id="main-content" className="relative z-0 flex-1 overflow-auto" style={{ padding: '16px 24px' }} tabIndex={-1}>
        <div className="max-w-7xl mx-auto" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Cohort overview — clinical command-center KPIs (real aggregates) */}
          <PatientsOverview patients={patients as never} total={total} />

          {/* Toolbar — inline, same pattern as StudyList/DocumentList */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col sm:flex-row items-start sm:items-center justify-between"
            style={{ gap: 8 }}
          >
            {/* Search & Filters */}
            <div className="flex items-center flex-1 w-full sm:w-auto" style={{ gap: 8 }}>
              {/* Search — 36px height (md), radius 6px */}
              <div className="relative flex-1 max-w-md">
                <Search className="absolute" style={{ left: 10, top: '50%', transform: 'translateY(-50%)', width: 16, height: 16, color: '#767E8E' }} />
                <input
                  type="text"
                  value={filters.search}
                  onChange={(e) => handleFilterChange('search', e.target.value)}
                  placeholder={t('patients.searchPlaceholder')}
                  className="w-full border border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                  style={{ height: 36, paddingLeft: 36, paddingRight: 12, background: '#0E1014', borderRadius: 6, fontSize: 13, color: '#E7EBF2' }}
                />
              </div>

              {/* Filter Toggle — 36px height, radius 6px */}
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={`flex items-center border transition-colors ${
                  showFilters || hasActiveFilters
                    ? 'border-blue-500 text-blue-400 bg-blue-900/20'
                    : 'border-gray-600 text-gray-300 hover:bg-gray-700'
                }`}
                style={{ height: 36, gap: 6, padding: '0 12px', borderRadius: 6, fontSize: 13 }}
              >
                <Filter style={{ width: 16, height: 16 }} />
                <span className="hidden sm:inline">{t('common.filters')}</span>
                {hasActiveFilters && (
                  <span className="flex items-center justify-center bg-blue-500 text-white rounded-full"
                    style={{ width: 18, height: 18, fontSize: 11 }}>
                    !
                  </span>
                )}
              </button>
            </div>

            {/* Actions */}
            <div className="flex items-center" style={{ gap: 4 }}>
              {/* View Mode — 36px buttons, radius 6px */}
              <div className="flex items-center border border-gray-600 overflow-hidden" style={{ borderRadius: 6 }}>
                <button
                  onClick={() => setViewMode('grid')}
                  className={`flex items-center justify-center ${
                    viewMode === 'grid'
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:bg-gray-700'
                  }`}
                  style={{ width: 36, height: 36 }}
                >
                  <Grid style={{ width: 16, height: 16 }} />
                </button>
                <button
                  onClick={() => setViewMode('list')}
                  className={`flex items-center justify-center ${
                    viewMode === 'list'
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:bg-gray-700'
                  }`}
                  style={{ width: 36, height: 36 }}
                >
                  <List style={{ width: 16, height: 16 }} />
                </button>
              </div>

              {/* Sort — 36×36, radius 6px */}
              <button
                onClick={toggleSortOrder}
                className="flex items-center justify-center text-gray-400 hover:bg-gray-700 border border-gray-600 transition-colors"
                style={{ width: 36, height: 36, borderRadius: 6 }}
                title={t('common.sort')}
              >
                {sortOrder === 'asc' ? (
                  <SortAsc style={{ width: 16, height: 16 }} />
                ) : (
                  <SortDesc style={{ width: 16, height: 16 }} />
                )}
              </button>

              {/* Create Patient — 36px height, radius 6px */}
              <button
                onClick={handleCreatePatient}
                className="flex items-center bg-brand-950 border border-brand-500/30 text-white hover:bg-brand-500/10 transition-colors"
                style={{ height: 36, gap: 6, padding: '0 14px', borderRadius: 6, fontSize: 13, fontWeight: 600 }}
              >
                <Plus style={{ width: 16, height: 16 }} />
                <span className="hidden sm:inline">{t('patients.createPatient')}</span>
              </button>
            </div>
          </motion.div>

          {/* Filter Panel */}
          <AnimatePresence>
            {showFilters && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="border border-gray-700" style={{ background: '#0E1014', borderRadius: 8, padding: 12 }}>
                  <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
                    <h3 style={{ fontSize: 13, fontWeight: 600, color: '#E7EBF2', margin: 0 }}>
                      {t('common.filters')}
                    </h3>
                    {hasActiveFilters && (
                      <button
                        onClick={clearFilters}
                        className="flex items-center text-blue-400 hover:text-blue-300 transition-colors"
                        style={{ gap: 4, fontSize: 12 }}
                      >
                        <X style={{ width: 14, height: 14 }} />
                        {t('common.clearFilters')}
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3" style={{ gap: 12 }}>
                    {/* Status Filter */}
                    <div>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase' as const, letterSpacing: '0.05em', marginBottom: 4 }}>
                        {t('patients.status.label', 'Status')}
                      </label>
                      <select
                        value={filters.status}
                        onChange={(e) => handleFilterChange('status', e.target.value)}
                        className="w-full border border-gray-600 focus:ring-2 focus:ring-blue-500"
                        style={{ height: 36, padding: '0 12px', borderRadius: 6, background: '#0E1014', color: '#E7EBF2', fontSize: 13 }}
                      >
                        <option value="">{t('common.all')}</option>
                        <option value="active">{t('patients.status.active')}</option>
                        <option value="inactive">{t('patients.status.inactive')}</option>
                        <option value="deceased">{t('patients.status.deceased')}</option>
                      </select>
                    </div>

                    {/* Gender Filter */}
                    <div>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase' as const, letterSpacing: '0.05em', marginBottom: 4 }}>
                        {t('patients.gender', 'Gender')}
                      </label>
                      <select
                        value={filters.gender}
                        onChange={(e) => handleFilterChange('gender', e.target.value)}
                        className="w-full border border-gray-600 focus:ring-2 focus:ring-blue-500"
                        style={{ height: 36, padding: '0 12px', borderRadius: 6, background: '#0E1014', color: '#E7EBF2', fontSize: 13 }}
                      >
                        <option value="">{t('common.all')}</option>
                        <option value="male">{t('patients.genders.male', 'Male')}</option>
                        <option value="female">{t('patients.genders.female', 'Female')}</option>
                        <option value="other">{t('patients.genders.other', 'Other')}</option>
                        <option value="unknown">{t('patients.genders.unknown', 'Unknown')}</option>
                      </select>
                    </div>

                    {/* Sort By */}
                    <div>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase' as const, letterSpacing: '0.05em', marginBottom: 4 }}>
                        {t('common.sortBy', 'Sort by')}
                      </label>
                      <select
                        value={sortField}
                        onChange={(e) => setSortField(e.target.value as SortField)}
                        className="w-full border border-gray-600 focus:ring-2 focus:ring-blue-500"
                        style={{ height: 36, padding: '0 12px', borderRadius: 6, background: '#0E1014', color: '#E7EBF2', fontSize: 13 }}
                      >
                        <option value="created_at">{t('common.createdAt', 'Created')}</option>
                        <option value="name">{t('patients.name', 'Name')}</option>
                        <option value="mrn">{t('patients.mrn', 'MRN')}</option>
                        <option value="birth_date">{t('patients.birthDate', 'Date of birth')}</option>
                      </select>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Results Count — 12px label */}
          <div className="flex items-center justify-between" style={{ fontSize: 12, color: '#96A0B0' }}>
            <span>
              {t('patients.showingResults', {
                from: patients.length > 0 ? (page - 1) * pageSize + 1 : 0,
                to: Math.min(page * pageSize, total),
                total,
              })}
            </span>
            {isFetching && (
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                className="border-2 border-blue-500 border-t-transparent rounded-full"
                style={{ width: 16, height: 16 }}
              />
            )}
          </div>

          {/* Patient Grid/List */}
          {isLoading ? (
            // Skeleton grid that matches the real card layout, so results fade in without a
            // spinner-then-pop layout jump (the audit's biggest perceived-quality gap).
            <div
              role="status"
              aria-busy="true"
              aria-label={t('patients.loading')}
              className={viewMode === 'grid'
                ? 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3'
                : 'flex flex-col'}
              style={{ gap: viewMode === 'grid' ? 16 : 8 }}
            >
              {Array.from({ length: 6 }).map((_, i) => (
                <SkeletonCard key={i} />
              ))}
            </div>
          ) : patients.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-center"
              style={{ padding: '48px 16px' }}
            >
              <Users className="mx-auto" style={{ width: 36, height: 36, color: '#2A303C', marginBottom: 12 }} />
              <h3 style={{ fontSize: 14, fontWeight: 600, color: '#E7EBF2', margin: '0 0 4px 0' }}>
                {filters.search
                  ? t('patients.noResults')
                  : t('patients.noPatients')}
              </h3>
              <p style={{ fontSize: 12, color: '#96A0B0', margin: '0 0 16px 0' }}>
                {filters.search
                  ? t('patients.tryDifferentSearch', 'Try a different search')
                  : t('patients.createFirstDescription', 'Start by registering your first patient')}
              </p>
              {!filters.search && (
                <button
                  onClick={handleCreatePatient}
                  className="inline-flex items-center bg-brand-950 border border-brand-500/30 text-white hover:bg-brand-500/10 transition-colors"
                  style={{ height: 36, gap: 6, padding: '0 14px', borderRadius: 6, fontSize: 13, fontWeight: 600 }}
                >
                  <Plus style={{ width: 16, height: 16 }} />
                  {t('patients.createFirst')}
                </button>
              )}
            </motion.div>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className={
                viewMode === 'grid'
                  ? 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3'
                  : ''
              }
              style={{ gap: viewMode === 'grid' ? 16 : 8 }}
            >
              <AnimatePresence mode="popLayout">
                {patients.map((patient, index) => (
                  <motion.div
                    key={patient.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ delay: index * 0.05 }}
                  >
                    <PatientCard
                      patient={patient}
                      compact={viewMode === 'list'}
                      onSelect={() => handlePatientSelect(patient)}
                      onEdit={() => handleEditPatient(patient)}
                      onDelete={() => handleDeletePatient(patient)}
                      isDeleting={deletingPatientId === patient.id}
                    />
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
          )}

          {/* Pagination — 36px buttons, radius 6px */}
          {totalPages > 1 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center justify-center"
              style={{ gap: 4, paddingTop: 8 }}
            >
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="flex items-center justify-center text-gray-400 hover:bg-gray-700 border border-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                style={{ width: 36, height: 36, borderRadius: 6 }}
              >
                <ChevronLeft style={{ width: 16, height: 16 }} />
              </button>

              <div className="flex items-center" style={{ gap: 4 }}>
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum: number;
                  if (totalPages <= 5) {
                    pageNum = i + 1;
                  } else if (page <= 3) {
                    pageNum = i + 1;
                  } else if (page >= totalPages - 2) {
                    pageNum = totalPages - 4 + i;
                  } else {
                    pageNum = page - 2 + i;
                  }

                  return (
                    <button
                      key={pageNum}
                      onClick={() => setPage(pageNum)}
                      className={`flex items-center justify-center transition-colors ${
                        page === pageNum
                          ? 'bg-blue-600 text-white'
                          : 'text-gray-400 hover:bg-gray-700 border border-gray-700'
                      }`}
                      style={{ width: 36, height: 36, borderRadius: 6, fontSize: 13, fontWeight: 500 }}
                    >
                      {pageNum}
                    </button>
                  );
                })}
              </div>

              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="flex items-center justify-center text-gray-400 hover:bg-gray-700 border border-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                style={{ width: 36, height: 36, borderRadius: 6 }}
              >
                <ChevronRight style={{ width: 16, height: 16 }} />
              </button>
            </motion.div>
          )}
        </div>
      </main>

      {/* Create/Edit Patient Modal */}
      <AnimatePresence>
        {showCreateForm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
            onClick={handleFormCancel}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-white dark:bg-gray-900 rounded-2xl shadow-2xl"
              onClick={e => e.stopPropagation()}
            >
              <div className="sticky top-0 z-10 flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                  {editingPatient ? t('patients.editPatient') : t('patients.createPatient')}
                </h2>
                <button
                  onClick={handleFormCancel}
                  className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6">
                <PatientForm
                  patient={editingPatient || undefined}
                  onSuccess={handleFormSuccess}
                  onCancel={handleFormCancel}
                />
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Toast Notifications */}
      <Toaster
        position="top-right"
        theme={theme === 'dark' ? 'dark' : 'light'}
        richColors
        closeButton
        expand={false}
      />
    </div>
  );
}
