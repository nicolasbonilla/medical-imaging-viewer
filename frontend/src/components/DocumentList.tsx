import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  Search,
  Filter,
  Plus,
  ChevronLeft,
  ChevronRight,
  Loader2,
  FileText,
  X,
  Grid,
  List,
  SortAsc,
  SortDesc,
  Upload,
} from 'lucide-react';
import { DocumentCard } from './DocumentCard';
import type { Document, DocumentSummary, DocumentCategory, DocumentStatus } from '@/types';

interface DocumentListProps {
  documents: (Document | DocumentSummary)[];
  isLoading?: boolean;
  error?: Error | null;
  // Pagination
  page?: number;
  totalPages?: number;
  total?: number;
  onPageChange?: (page: number) => void;
  // Actions
  onViewDocument?: (doc: Document | DocumentSummary) => void;
  onEditDocument?: (doc: Document | DocumentSummary) => void;
  onDeleteDocument?: (doc: Document | DocumentSummary) => void;
  onDownloadDocument?: (doc: Document | DocumentSummary) => void;
  onViewVersions?: (doc: Document | DocumentSummary) => void;
  onUploadDocument?: () => void;
  // Filters
  showFilters?: boolean;
  onFilterChange?: (filters: DocumentFilters) => void;
  // Display
  viewMode?: 'grid' | 'list';
  onViewModeChange?: (mode: 'grid' | 'list') => void;
  emptyMessage?: string;
}

export interface DocumentFilters {
  search?: string;
  category?: DocumentCategory | '';
  status?: DocumentStatus | '';
  dateFrom?: string;
  dateTo?: string;
  sortBy?: 'date' | 'title' | 'category';
  sortOrder?: 'asc' | 'desc';
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

export const DocumentList: React.FC<DocumentListProps> = ({
  documents,
  isLoading = false,
  error = null,
  page = 1,
  totalPages = 1,
  total = 0,
  onPageChange,
  onViewDocument,
  onEditDocument,
  onDeleteDocument,
  onDownloadDocument,
  onViewVersions,
  onUploadDocument,
  showFilters = true,
  onFilterChange,
  viewMode = 'grid',
  onViewModeChange,
  emptyMessage,
}) => {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<DocumentFilters>({
    search: '',
    category: '',
    status: '',
    dateFrom: '',
    dateTo: '',
    sortBy: 'date',
    sortOrder: 'desc',
  });
  const [showFilterPanel, setShowFilterPanel] = useState(false);

  // Handle filter changes
  const handleFilterChange = (key: keyof DocumentFilters, value: string) => {
    const newFilters = { ...filters, [key]: value };
    setFilters(newFilters);
    if (onFilterChange) {
      onFilterChange(newFilters);
    }
  };

  // Clear all filters
  const clearFilters = () => {
    const clearedFilters: DocumentFilters = {
      search: '',
      category: '',
      status: '',
      dateFrom: '',
      dateTo: '',
      sortBy: 'date',
      sortOrder: 'desc',
    };
    setFilters(clearedFilters);
    if (onFilterChange) {
      onFilterChange(clearedFilters);
    }
  };

  // Check if any filters are active
  const hasActiveFilters =
    filters.search || filters.category || filters.status || filters.dateFrom || filters.dateTo;

  // Render loading state
  if (isLoading && documents.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">{t('common.loading')}</span>
      </div>
    );
  }

  // Render error state
  if (error) {
    return (
      <div className="text-center py-12">
        <div className="text-red-500 mb-2">{t('common.error')}</div>
        <p className="text-gray-500 dark:text-gray-400">{error.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with search and actions */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4 flex-1 w-full sm:w-auto">
          {/* Search */}
          {showFilters && (
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={filters.search}
                onChange={(e) => handleFilterChange('search', e.target.value)}
                placeholder={t('document.searchPlaceholder')}
                className="w-full pl-10 pr-4 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          )}

          {/* Filter toggle */}
          {showFilters && (
            <button
              onClick={() => setShowFilterPanel(!showFilterPanel)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${
                showFilterPanel || hasActiveFilters
                  ? 'border-blue-500 text-blue-600 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              <Filter className="w-4 h-4" />
              <span className="hidden sm:inline">{t('common.filters')}</span>
              {hasActiveFilters && (
                <span className="w-5 h-5 flex items-center justify-center bg-blue-500 text-white text-xs rounded-full">
                  !
                </span>
              )}
            </button>
          )}
        </div>

        {/* Right side actions */}
        <div className="flex items-center gap-2">
          {/* View mode toggle */}
          {onViewModeChange && (
            <div className="flex items-center border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
              <button
                onClick={() => onViewModeChange('grid')}
                className={`p-2 ${
                  viewMode === 'grid'
                    ? 'bg-blue-500 text-white'
                    : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
              >
                <Grid className="w-4 h-4" />
              </button>
              <button
                onClick={() => onViewModeChange('list')}
                className={`p-2 ${
                  viewMode === 'list'
                    ? 'bg-blue-500 text-white'
                    : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
              >
                <List className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Sort toggle */}
          <button
            onClick={() =>
              handleFilterChange('sortOrder', filters.sortOrder === 'asc' ? 'desc' : 'asc')
            }
            className="p-2 text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-700"
            title={t('common.sort')}
          >
            {filters.sortOrder === 'asc' ? (
              <SortAsc className="w-4 h-4" />
            ) : (
              <SortDesc className="w-4 h-4" />
            )}
          </button>

          {/* Upload button */}
          {onUploadDocument && (
            <button
              onClick={onUploadDocument}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
            >
              <Upload className="w-4 h-4" />
              <span className="hidden sm:inline">{t('document.upload')}</span>
            </button>
          )}
        </div>
      </div>

      {/* Filter panel */}
      <AnimatePresence>
        {showFilterPanel && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium text-gray-900 dark:text-gray-100">
                  {t('common.filters')}
                </h3>
                {hasActiveFilters && (
                  <button
                    onClick={clearFilters}
                    className="text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
                  >
                    <X className="w-3.5 h-3.5" />
                    {t('common.clearFilters')}
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Category filter */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('document.category')}
                  </label>
                  <select
                    value={filters.category}
                    onChange={(e) => handleFilterChange('category', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  >
                    <option value="">{t('common.all')}</option>
                    {CATEGORIES.map((cat) => (
                      <option key={cat} value={cat}>
                        {t(`document.categories.${cat}`)}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Status filter */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('document.status.label')}
                  </label>
                  <select
                    value={filters.status}
                    onChange={(e) => handleFilterChange('status', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  >
                    <option value="">{t('common.all')}</option>
                    {STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {t(`document.status.${status}`)}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Date from */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('document.dateFrom')}
                  </label>
                  <input
                    type="date"
                    value={filters.dateFrom}
                    onChange={(e) => handleFilterChange('dateFrom', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                </div>

                {/* Date to */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('document.dateTo')}
                  </label>
                  <input
                    type="date"
                    value={filters.dateTo}
                    onChange={(e) => handleFilterChange('dateTo', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Results count */}
      <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
        <span>
          {t('document.showingResults', { count: documents.length, total })}
        </span>
        {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
      </div>

      {/* Document grid/list */}
      {documents.length === 0 ? (
        <div className="text-center py-12">
          <FileText className="w-12 h-12 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
            {t('document.noDocuments')}
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            {emptyMessage || t('document.noDocumentsDescription')}
          </p>
          {onUploadDocument && (
            <button
              onClick={onUploadDocument}
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
            >
              <Upload className="w-4 h-4" />
              {t('document.uploadFirst')}
            </button>
          )}
        </div>
      ) : (
        <div
          className={
            viewMode === 'grid'
              ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'
              : 'space-y-3'
          }
        >
          <AnimatePresence mode="popLayout">
            {documents.map((doc) => (
              <DocumentCard
                key={doc.id}
                document={doc}
                compact={viewMode === 'list'}
                onView={onViewDocument ? () => onViewDocument(doc) : undefined}
                onEdit={onEditDocument ? () => onEditDocument(doc) : undefined}
                onDelete={onDeleteDocument ? () => onDeleteDocument(doc) : undefined}
                onDownload={onDownloadDocument ? () => onDownloadDocument(doc) : undefined}
                onViewVersions={onViewVersions ? () => onViewVersions(doc) : undefined}
              />
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && onPageChange && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
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
                  onClick={() => onPageChange(pageNum)}
                  className={`w-10 h-10 rounded-lg font-medium transition-colors ${
                    page === pageNum
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
                >
                  {pageNum}
                </button>
              );
            })}
          </div>

          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>
      )}
    </div>
  );
};

export default DocumentList;
