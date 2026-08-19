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
  FileImage,
  X,
  Grid,
  List,
  SortAsc,
  SortDesc,
} from 'lucide-react';
import { StudyCard } from './StudyCard';
import type { StudySummary, ImagingStudy, Modality, StudyStatus } from '@/types';

interface StudyListProps {
  studies: (StudySummary | ImagingStudy)[];
  isLoading?: boolean;
  error?: Error | null;
  page?: number;
  totalPages?: number;
  total?: number;
  onPageChange?: (page: number) => void;
  onViewStudy?: (study: StudySummary | ImagingStudy) => void;
  onEditStudy?: (study: StudySummary | ImagingStudy) => void;
  onDeleteStudy?: (study: StudySummary | ImagingStudy) => void;
  onDownloadStudy?: (study: StudySummary | ImagingStudy) => void;
  onCreateStudy?: () => void;
  showFilters?: boolean;
  onFilterChange?: (filters: StudyFilters) => void;
  viewMode?: 'grid' | 'list';
  onViewModeChange?: (mode: 'grid' | 'list') => void;
  emptyMessage?: string;
}

export interface StudyFilters {
  search?: string;
  modality?: Modality | '';
  status?: StudyStatus | '';
  dateFrom?: string;
  dateTo?: string;
  sortBy?: 'date' | 'modality' | 'status';
  sortOrder?: 'asc' | 'desc';
}

const MODALITIES: Modality[] = ['CT', 'MR', 'US', 'XR', 'MG', 'NM', 'PT', 'CR', 'DX', 'OT'];
const STATUSES: StudyStatus[] = ['registered', 'available', 'cancelled', 'entered-in-error'];

export const StudyList: React.FC<StudyListProps> = ({
  studies,
  isLoading = false,
  error = null,
  page = 1,
  totalPages = 1,
  total = 0,
  onPageChange,
  onViewStudy,
  onEditStudy,
  onDeleteStudy,
  onDownloadStudy,
  onCreateStudy,
  showFilters = true,
  onFilterChange,
  viewMode = 'grid',
  onViewModeChange,
  emptyMessage,
}) => {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<StudyFilters>({
    search: '', modality: '', status: '', dateFrom: '', dateTo: '',
    sortBy: 'date', sortOrder: 'desc',
  });
  const [showFilterPanel, setShowFilterPanel] = useState(false);

  const handleFilterChange = (key: keyof StudyFilters, value: string) => {
    const newFilters = { ...filters, [key]: value };
    setFilters(newFilters);
    onFilterChange?.(newFilters);
  };

  const clearFilters = () => {
    const cleared: StudyFilters = { search: '', modality: '', status: '', dateFrom: '', dateTo: '', sortBy: 'date', sortOrder: 'desc' };
    setFilters(cleared);
    onFilterChange?.(cleared);
  };

  const hasActiveFilters = filters.search || filters.modality || filters.status || filters.dateFrom || filters.dateTo;

  // Loading
  if (isLoading && studies.length === 0) {
    return (
      <div className="flex items-center justify-center" style={{ padding: '48px 0' }}>
        <Loader2 className="animate-spin" style={{ width: 24, height: 24, color: '#60A5FA' }} />
        <span style={{ marginLeft: 8, fontSize: 13, color: '#96A0B0' }}>{t('common.loading')}</span>
      </div>
    );
  }

  // Error
  if (error) {
    return (
      <div className="text-center" style={{ padding: '48px 0' }}>
        <p style={{ fontSize: 14, color: '#F87171', marginBottom: 4 }}>{t('common.error')}</p>
        <p style={{ fontSize: 12, color: '#96A0B0' }}>{error.message}</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* ── Toolbar ── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between" style={{ gap: 8 }}>
        <div className="flex items-center flex-1 w-full sm:w-auto" style={{ gap: 8 }}>
          {/* Search — 36px height, radius 6 */}
          {showFilters && (
            <div className="relative flex-1 max-w-md">
              <Search className="absolute" style={{ left: 10, top: '50%', transform: 'translateY(-50%)', width: 16, height: 16, color: '#767E8E' }} />
              <input
                type="text"
                value={filters.search}
                onChange={(e) => handleFilterChange('search', e.target.value)}
                placeholder={t('study.searchPlaceholder')}
                className="w-full border border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                style={{ height: 36, paddingLeft: 36, paddingRight: 12, background: '#0E1014', borderRadius: 6, fontSize: 13, color: '#E7EBF2' }}
              />
            </div>
          )}

          {/* Filter toggle — 36px, radius 6 */}
          {showFilters && (
            <button
              onClick={() => setShowFilterPanel(!showFilterPanel)}
              className={`flex items-center border transition-colors ${
                showFilterPanel || hasActiveFilters
                  ? 'border-blue-500 text-blue-400 bg-blue-900/20'
                  : 'border-gray-600 text-gray-300 hover:bg-gray-700'
              }`}
              style={{ height: 36, gap: 6, padding: '0 12px', borderRadius: 6, fontSize: 13 }}
            >
              <Filter style={{ width: 16, height: 16 }} />
              <span className="hidden sm:inline">{t('common.filters')}</span>
              {hasActiveFilters && (
                <span className="flex items-center justify-center bg-blue-500 text-white rounded-full"
                  style={{ width: 18, height: 18, fontSize: 11 }}>!</span>
              )}
            </button>
          )}
        </div>

        {/* Right actions */}
        <div className="flex items-center" style={{ gap: 4 }}>
          {/* View mode — 36px buttons */}
          {onViewModeChange && (
            <div className="flex items-center border border-gray-600 overflow-hidden" style={{ borderRadius: 6 }}>
              <button
                onClick={() => onViewModeChange('grid')}
                className={`flex items-center justify-center ${
                  viewMode === 'grid' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-700'
                }`}
                style={{ width: 36, height: 36 }}
              >
                <Grid style={{ width: 16, height: 16 }} />
              </button>
              <button
                onClick={() => onViewModeChange('list')}
                className={`flex items-center justify-center ${
                  viewMode === 'list' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-700'
                }`}
                style={{ width: 36, height: 36 }}
              >
                <List style={{ width: 16, height: 16 }} />
              </button>
            </div>
          )}

          {/* Sort — 36×36 */}
          <button
            onClick={() => handleFilterChange('sortOrder', filters.sortOrder === 'asc' ? 'desc' : 'asc')}
            className="flex items-center justify-center text-gray-400 hover:bg-gray-700 border border-gray-600 transition-colors"
            style={{ width: 36, height: 36, borderRadius: 6 }}
            title={t('common.sort')}
          >
            {filters.sortOrder === 'asc'
              ? <SortAsc style={{ width: 16, height: 16 }} />
              : <SortDesc style={{ width: 16, height: 16 }} />
            }
          </button>

          {/* New Study — 36px, radius 6 */}
          {onCreateStudy && (
            <button
              onClick={onCreateStudy}
              className="flex items-center bg-brand-950 border border-brand-500/30 text-white hover:bg-brand-500/10 transition-colors"
              style={{ height: 36, gap: 6, padding: '0 14px', borderRadius: 6, fontSize: 13, fontWeight: 600 }}
            >
              <Plus style={{ width: 16, height: 16 }} />
              <span className="hidden sm:inline">{t('study.createStudy')}</span>
            </button>
          )}
        </div>
      </div>

      {/* ── Filter panel ── */}
      <AnimatePresence>
        {showFilterPanel && (
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
                  <button onClick={clearFilters}
                    className="flex items-center text-blue-400 hover:text-blue-300 transition-colors"
                    style={{ gap: 4, fontSize: 12 }}>
                    <X style={{ width: 14, height: 14 }} />
                    {t('common.clearFilters')}
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4" style={{ gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                    {t('study.modality')}
                  </label>
                  <select value={filters.modality} onChange={(e) => handleFilterChange('modality', e.target.value)}
                    className="w-full border border-gray-600 focus:ring-2 focus:ring-blue-500"
                    style={{ height: 36, padding: '0 12px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 13 }}>
                    <option value="">{t('common.all')}</option>
                    {MODALITIES.map((mod) => (
                      <option key={mod} value={mod}>{mod} - {t(`study.modalities.${mod}`)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                    {t('study.status.label')}
                  </label>
                  <select value={filters.status} onChange={(e) => handleFilterChange('status', e.target.value)}
                    className="w-full border border-gray-600 focus:ring-2 focus:ring-blue-500"
                    style={{ height: 36, padding: '0 12px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 13 }}>
                    <option value="">{t('common.all')}</option>
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>{t(`study.status.${s}`)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                    {t('study.dateFrom')}
                  </label>
                  <input type="date" value={filters.dateFrom} onChange={(e) => handleFilterChange('dateFrom', e.target.value)}
                    className="w-full border border-gray-600 focus:ring-2 focus:ring-blue-500"
                    style={{ height: 36, padding: '0 12px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 13 }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, fontWeight: 500, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                    {t('study.dateTo')}
                  </label>
                  <input type="date" value={filters.dateTo} onChange={(e) => handleFilterChange('dateTo', e.target.value)}
                    className="w-full border border-gray-600 focus:ring-2 focus:ring-blue-500"
                    style={{ height: 36, padding: '0 12px', borderRadius: 6, background: '#161922', color: '#E7EBF2', fontSize: 13 }} />
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Results count — 12px ── */}
      <div className="flex items-center justify-between" style={{ fontSize: 12, color: '#96A0B0' }}>
        <span>{t('study.showingResults', { count: studies.length, total })}</span>
        {isLoading && <Loader2 className="animate-spin" style={{ width: 16, height: 16, color: '#60A5FA' }} />}
      </div>

      {/* ── Study grid/list ── */}
      {studies.length === 0 ? (
        <div className="text-center" style={{ padding: '48px 16px' }}>
          <FileImage className="mx-auto" style={{ width: 36, height: 36, color: '#2A303C', marginBottom: 12 }} />
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#E7EBF2', margin: '0 0 4px 0' }}>
            {t('study.noStudies')}
          </h3>
          <p style={{ fontSize: 12, color: '#96A0B0', margin: '0 0 16px 0' }}>
            {emptyMessage || t('study.noStudiesDescription')}
          </p>
          {onCreateStudy && (
            <button onClick={onCreateStudy}
              className="inline-flex items-center bg-blue-600 hover:bg-blue-700 text-white transition-colors"
              style={{ height: 36, gap: 6, padding: '0 14px', borderRadius: 6, fontSize: 13, fontWeight: 500 }}>
              <Plus style={{ width: 16, height: 16 }} />
              {t('study.createStudy')}
            </button>
          )}
        </div>
      ) : (
        <div
          className={viewMode === 'grid' ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3' : ''}
          style={{ gap: viewMode === 'grid' ? 16 : 8 }}
        >
          <AnimatePresence mode="popLayout">
            {studies.map((study) => (
              <StudyCard
                key={study.id}
                study={study}
                compact={viewMode === 'list'}
                onView={onViewStudy ? () => onViewStudy(study) : undefined}
                onEdit={onEditStudy ? () => onEditStudy(study) : undefined}
                onDelete={onDeleteStudy ? () => onDeleteStudy(study) : undefined}
                onDownload={onDownloadStudy ? () => onDownloadStudy(study) : undefined}
              />
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* ── Pagination — 36px buttons, radius 6 ── */}
      {totalPages > 1 && onPageChange && (
        <div className="flex items-center justify-center" style={{ gap: 4, paddingTop: 8 }}>
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="flex items-center justify-center text-gray-400 hover:bg-gray-700 border border-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            style={{ width: 36, height: 36, borderRadius: 6 }}
          >
            <ChevronLeft style={{ width: 16, height: 16 }} />
          </button>

          <div className="flex items-center" style={{ gap: 4 }}>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              let pageNum: number;
              if (totalPages <= 5) pageNum = i + 1;
              else if (page <= 3) pageNum = i + 1;
              else if (page >= totalPages - 2) pageNum = totalPages - 4 + i;
              else pageNum = page - 2 + i;

              return (
                <button
                  key={pageNum}
                  onClick={() => onPageChange(pageNum)}
                  className={`flex items-center justify-center transition-colors ${
                    page === pageNum ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-700 border border-gray-700'
                  }`}
                  style={{ width: 36, height: 36, borderRadius: 6, fontSize: 13, fontWeight: 500 }}
                >
                  {pageNum}
                </button>
              );
            })}
          </div>

          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="flex items-center justify-center text-gray-400 hover:bg-gray-700 border border-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            style={{ width: 36, height: 36, borderRadius: 6 }}
          >
            <ChevronRight style={{ width: 16, height: 16 }} />
          </button>
        </div>
      )}
    </div>
  );
};

export default StudyList;
