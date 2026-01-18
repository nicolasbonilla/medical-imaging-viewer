import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { toast, Toaster } from 'sonner';
import {
  FileText,
  Search,
  Filter,
  Grid,
  List,
  SortAsc,
  SortDesc,
  Activity,
  LogOut,
  Sparkles,
  X,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useDocumentList, useDeleteDocument } from '@/hooks/useDocuments';
import { DocumentCard } from '@/components/DocumentCard';
import { DocumentViewer } from '@/components/DocumentViewer';
import ThemeToggle from '@/components/ThemeToggle';
import LanguageSelector from '@/components/LanguageSelector';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import type { Document, DocumentSummary, DocumentCategory, DocumentStatus } from '@/types';

type ViewMode = 'grid' | 'list';
type SortField = 'date' | 'title' | 'category';
type SortOrder = 'asc' | 'desc';

interface Filters {
  search: string;
  category: DocumentCategory | '';
  status: DocumentStatus | '';
  dateFrom: string;
  dateTo: string;
}

const CATEGORIES: DocumentCategory[] = [
  'lab-result',
  'prescription',
  'clinical-note',
  'discharge-summary',
  'radiology-report',
  'consent-form',
  'referral',
  'operative-note',
  'pathology-report',
  'other',
];

const STATUSES: DocumentStatus[] = ['current', 'superseded', 'entered-in-error'];

export default function DocumentsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { theme } = useTheme();

  // UI State
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [showFilters, setShowFilters] = useState(false);
  const [viewingDocument, setViewingDocument] = useState<Document | DocumentSummary | null>(null);

  // Pagination & Sorting
  const [page, setPage] = useState(1);
  const [pageSize] = useState(12);
  const [sortField, setSortField] = useState<SortField>('date');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  // Filters
  const [filters, setFilters] = useState<Filters>({
    search: '',
    category: '',
    status: '',
    dateFrom: '',
    dateTo: '',
  });

  // Data fetching
  const {
    data: documentsData,
    isLoading,
    isFetching,
  } = useDocumentList({
    page,
    page_size: pageSize,
    category: filters.category || undefined,
    status: filters.status || undefined,
    query: filters.search || undefined,
  });

  const deleteDocumentMutation = useDeleteDocument();

  // Handlers
  const handleViewDocument = useCallback((doc: Document | DocumentSummary) => {
    setViewingDocument(doc);
  }, []);

  const handleDeleteDocument = useCallback(async (doc: Document | DocumentSummary) => {
    if (window.confirm(t('document.confirmDelete', { title: doc.title }))) {
      try {
        await deleteDocumentMutation.mutateAsync({
          id: doc.id,
          patientId: doc.patient_id,
        });
        toast.success(t('document.deleteSuccess'));
      } catch (error) {
        toast.error(t('document.deleteFailed'));
        console.error('Delete document error:', error);
      }
    }
  }, [deleteDocumentMutation, t]);

  const handleFilterChange = useCallback((key: keyof Filters, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setPage(1);
  }, []);

  const clearFilters = useCallback(() => {
    setFilters({ search: '', category: '', status: '', dateFrom: '', dateTo: '' });
    setPage(1);
  }, []);

  const toggleSortOrder = useCallback(() => {
    setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
  }, []);

  const hasActiveFilters = filters.search || filters.category || filters.status || filters.dateFrom || filters.dateTo;

  const documents = documentsData?.items || [];
  const totalPages = documentsData?.total_pages || 1;
  const total = documentsData?.total || 0;

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
      {/* Animated Background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-1/2 -right-1/2 w-full h-full bg-gradient-to-br from-primary-500/5 to-accent-500/5 dark:from-primary-500/10 dark:to-accent-500/10 rounded-full blur-3xl animate-pulse-slow" />
        <div className="absolute -bottom-1/2 -left-1/2 w-full h-full bg-gradient-to-tr from-accent-500/5 to-primary-500/5 dark:from-accent-500/10 dark:to-primary-500/10 rounded-full blur-3xl animate-pulse-slow" style={{ animationDelay: '1s' }} />
      </div>

      {/* Header */}
      <motion.header
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5, type: 'spring', stiffness: 100 }}
        className="relative z-10 backdrop-blur-xl bg-white/70 dark:bg-gray-900/70 border-b border-gray-200/50 dark:border-gray-700/50 shadow-lg shadow-gray-200/50 dark:shadow-gray-900/50"
      >
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            {/* Logo & Title */}
            <div className="flex items-center gap-4">
              <motion.div
                whileHover={{ scale: 1.05, rotate: 5 }}
                whileTap={{ scale: 0.95 }}
                className="relative cursor-pointer"
                onClick={() => navigate('/app')}
              >
                <div className="absolute inset-0 bg-gradient-to-br from-primary-500 to-accent-500 rounded-2xl blur-lg opacity-60 dark:opacity-40 animate-pulse-slow" />
                <div className="relative bg-gradient-to-br from-primary-500 to-accent-500 p-3 rounded-2xl shadow-lg">
                  <Activity className="w-7 h-7 text-white" />
                </div>
              </motion.div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-primary-600 to-accent-600 dark:from-primary-400 dark:to-accent-400 bg-clip-text text-transparent flex items-center gap-2">
                  {t('document.title', 'Documentos')}
                  <Sparkles className="w-5 h-5 text-accent-500 dark:text-accent-400 animate-pulse" />
                </h1>
                <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">
                  {t('document.subtitle', 'Gestión de documentos clínicos')}
                </p>
              </div>
            </div>

            {/* Right Side Controls */}
            <div className="flex items-center gap-3">
              {/* Stats Badge */}
              <motion.span
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                className="px-4 py-2 bg-gradient-to-r from-accent-500/20 to-primary-500/20 dark:from-accent-500/30 dark:to-primary-600/30 backdrop-blur-md border border-accent-500/30 dark:border-accent-500/20 text-accent-700 dark:text-accent-400 rounded-xl text-xs font-semibold shadow-lg shadow-accent-500/10 flex items-center gap-2"
              >
                <FileText className="w-4 h-4" />
                {total} {t('document.totalDocuments', 'documentos')}
              </motion.span>

              {/* User Info */}
              {user && (
                <motion.div
                  whileHover={{ scale: 1.05 }}
                  className="flex items-center gap-3 px-4 py-2 bg-white/60 dark:bg-gray-800/60 backdrop-blur-md border border-gray-200/50 dark:border-gray-700/50 rounded-xl shadow-lg"
                >
                  <div className="w-9 h-9 bg-gradient-to-br from-primary-500 to-accent-500 rounded-lg flex items-center justify-center text-white font-bold text-sm shadow-lg">
                    {user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-gray-900 dark:text-white font-semibold">{user.full_name}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">{user.role.toLowerCase()}</p>
                  </div>
                </motion.div>
              )}

              <ThemeToggle variant="minimal" />
              <LanguageSelector variant="minimal" />

              <motion.button
                onClick={logout}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="p-3 bg-white/60 dark:bg-gray-800/60 hover:bg-error-50 dark:hover:bg-error-900/30 backdrop-blur-md border border-gray-200/50 dark:border-gray-700/50 hover:border-error-300 dark:hover:border-error-700 rounded-xl transition-all duration-200 group shadow-lg"
                title={t('auth.logout')}
              >
                <LogOut className="w-5 h-5 text-gray-600 dark:text-gray-400 group-hover:text-error-600 dark:group-hover:text-error-400 transition-colors" />
              </motion.button>
            </div>
          </div>
        </div>
      </motion.header>

      {/* Main Content */}
      <main className="relative z-0 flex-1 p-6 overflow-auto">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Toolbar */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-4 shadow-lg"
          >
            {/* Search & Filters */}
            <div className="flex items-center gap-3 flex-1 w-full sm:w-auto">
              {/* Search */}
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={filters.search}
                  onChange={(e) => handleFilterChange('search', e.target.value)}
                  placeholder={t('document.searchPlaceholder')}
                  className="w-full pl-10 pr-4 py-2.5 bg-white/60 dark:bg-gray-900/60 border border-gray-200/50 dark:border-gray-700/50 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all text-sm"
                />
              </div>

              {/* Filter Toggle */}
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border transition-all ${
                  showFilters || hasActiveFilters
                    ? 'border-primary-500 text-primary-600 bg-primary-50 dark:bg-primary-900/20'
                    : 'border-gray-200/50 dark:border-gray-700/50 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
              >
                <Filter className="w-4 h-4" />
                <span className="hidden sm:inline">{t('common.filters')}</span>
                {hasActiveFilters && (
                  <span className="w-5 h-5 flex items-center justify-center bg-primary-500 text-white text-xs rounded-full">
                    !
                  </span>
                )}
              </button>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2">
              {/* View Mode */}
              <div className="flex items-center border border-gray-200/50 dark:border-gray-700/50 rounded-xl overflow-hidden">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`p-2.5 ${
                    viewMode === 'grid'
                      ? 'bg-primary-500 text-white'
                      : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
                >
                  <Grid className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setViewMode('list')}
                  className={`p-2.5 ${
                    viewMode === 'list'
                      ? 'bg-primary-500 text-white'
                      : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
                >
                  <List className="w-4 h-4" />
                </button>
              </div>

              {/* Sort */}
              <button
                onClick={toggleSortOrder}
                className="p-2.5 text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-xl border border-gray-200/50 dark:border-gray-700/50"
                title={t('common.sort')}
              >
                {sortOrder === 'asc' ? (
                  <SortAsc className="w-4 h-4" />
                ) : (
                  <SortDesc className="w-4 h-4" />
                )}
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
                <div className="p-4 bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl rounded-2xl border border-gray-200/50 dark:border-gray-700/50 shadow-lg">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-medium text-gray-900 dark:text-gray-100">
                      {t('common.filters')}
                    </h3>
                    {hasActiveFilters && (
                      <button
                        onClick={clearFilters}
                        className="text-sm text-primary-600 hover:text-primary-700 flex items-center gap-1"
                      >
                        <X className="w-3.5 h-3.5" />
                        {t('common.clearFilters')}
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                    {/* Category Filter */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('document.category')}
                      </label>
                      <select
                        value={filters.category}
                        onChange={(e) => handleFilterChange('category', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-200/50 dark:border-gray-700/50 rounded-xl bg-white/60 dark:bg-gray-900/60 text-gray-900 dark:text-gray-100"
                      >
                        <option value="">{t('common.all')}</option>
                        {CATEGORIES.map((cat) => (
                          <option key={cat} value={cat}>
                            {t(`document.categories.${cat}`)}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Status Filter */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('document.status.label')}
                      </label>
                      <select
                        value={filters.status}
                        onChange={(e) => handleFilterChange('status', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-200/50 dark:border-gray-700/50 rounded-xl bg-white/60 dark:bg-gray-900/60 text-gray-900 dark:text-gray-100"
                      >
                        <option value="">{t('common.all')}</option>
                        {STATUSES.map((status) => (
                          <option key={status} value={status}>
                            {t(`document.status.${status}`)}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Date From */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('document.dateFrom')}
                      </label>
                      <input
                        type="date"
                        value={filters.dateFrom}
                        onChange={(e) => handleFilterChange('dateFrom', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-200/50 dark:border-gray-700/50 rounded-xl bg-white/60 dark:bg-gray-900/60 text-gray-900 dark:text-gray-100"
                      />
                    </div>

                    {/* Date To */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('document.dateTo')}
                      </label>
                      <input
                        type="date"
                        value={filters.dateTo}
                        onChange={(e) => handleFilterChange('dateTo', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-200/50 dark:border-gray-700/50 rounded-xl bg-white/60 dark:bg-gray-900/60 text-gray-900 dark:text-gray-100"
                      />
                    </div>

                    {/* Sort By */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('common.sortBy')}
                      </label>
                      <select
                        value={sortField}
                        onChange={(e) => setSortField(e.target.value as SortField)}
                        className="w-full px-3 py-2 border border-gray-200/50 dark:border-gray-700/50 rounded-xl bg-white/60 dark:bg-gray-900/60 text-gray-900 dark:text-gray-100"
                      >
                        <option value="date">{t('document.date', 'Fecha')}</option>
                        <option value="title">{t('document.docTitle', 'Título')}</option>
                        <option value="category">{t('document.category', 'Categoría')}</option>
                      </select>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Results Count */}
          <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
            <span>
              {t('document.showingResults', { count: documents.length, total })}
            </span>
            {isFetching && (
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                className="w-4 h-4 border-2 border-primary-500 border-t-transparent rounded-full"
              />
            )}
          </div>

          {/* Document Grid/List */}
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 gap-4">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                className="w-12 h-12 border-4 border-primary-200 dark:border-primary-800 border-t-primary-600 dark:border-t-primary-400 rounded-full"
              />
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {t('common.loading')}
              </p>
            </div>
          ) : documents.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-center py-16"
            >
              <div className="w-20 h-20 mx-auto mb-6 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center">
                <FileText className="w-10 h-10 text-gray-400" />
              </div>
              <h3 className="text-xl font-medium text-gray-900 dark:text-gray-100 mb-2">
                {filters.search || hasActiveFilters
                  ? t('document.noResults', 'No se encontraron documentos')
                  : t('document.noDocuments')}
              </h3>
              <p className="text-gray-500 dark:text-gray-400">
                {filters.search || hasActiveFilters
                  ? t('document.tryDifferentSearch', 'Intenta con otros filtros')
                  : t('document.noDocumentsDescription')}
              </p>
            </motion.div>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className={
                viewMode === 'grid'
                  ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4'
                  : 'space-y-3'
              }
            >
              <AnimatePresence mode="popLayout">
                {documents.map((doc, index) => (
                  <motion.div
                    key={doc.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ delay: index * 0.05 }}
                  >
                    <DocumentCard
                      document={doc}
                      compact={viewMode === 'list'}
                      onView={() => handleViewDocument(doc)}
                      onDelete={() => handleDeleteDocument(doc)}
                    />
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center justify-center gap-2 pt-4"
            >
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-2.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed border border-gray-200/50 dark:border-gray-700/50"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>

              <div className="flex items-center gap-1">
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
                      className={`w-10 h-10 rounded-xl font-medium transition-colors ${
                        page === pageNum
                          ? 'bg-gradient-to-r from-primary-500 to-accent-500 text-white shadow-lg'
                          : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 border border-gray-200/50 dark:border-gray-700/50'
                      }`}
                    >
                      {pageNum}
                    </button>
                  );
                })}
              </div>

              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-2.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed border border-gray-200/50 dark:border-gray-700/50"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </motion.div>
          )}
        </div>
      </main>

      {/* Document Viewer Modal */}
      {viewingDocument && (
        <DocumentViewer
          document={viewingDocument}
          isOpen={!!viewingDocument}
          onClose={() => setViewingDocument(null)}
        />
      )}

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
