import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import {
  User,
  Search,
  RefreshCw,
  Plus,
  ChevronRight,
  Calendar,
  Phone,
  Mail,
  FileText,
  Image,
} from 'lucide-react';
import { patientAPI } from '@/services/patientApi';
import type { Patient, PatientStatus } from '@/types';

interface PatientExplorerProps {
  onPatientSelect: (patient: Patient) => void;
  onCreatePatient?: () => void;
}

export default function PatientExplorer({
  onPatientSelect,
  onCreatePatient,
}: PatientExplorerProps) {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<PatientStatus | undefined>();
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const {
    data: patientsData,
    isLoading,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['patients', page, pageSize, statusFilter, searchQuery],
    queryFn: () => {
      if (searchQuery && searchQuery.length >= 2) {
        return patientAPI.search({
          query: searchQuery,
          status: statusFilter,
          page,
          page_size: pageSize,
        });
      }
      return patientAPI.list(page, pageSize, statusFilter);
    },
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    refetch();
  };

  const getGenderIcon = (gender: string) => {
    switch (gender) {
      case 'male':
        return '♂';
      case 'female':
        return '♀';
      default:
        return '○';
    }
  };

  const getStatusColor = (status: PatientStatus) => {
    switch (status) {
      case 'active':
        return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
      case 'inactive':
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400';
      case 'deceased':
        return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString();
  };

  return (
    <div className="h-full flex flex-col bg-white/50 dark:bg-gray-900/50 backdrop-blur-xl border-r border-gray-200/50 dark:border-gray-700/50">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="p-6 border-b border-gray-200/50 dark:border-gray-700/50"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-primary-500 to-accent-500 rounded-lg shadow-lg">
              <User className="w-5 h-5 text-white" />
            </div>
            <h2 className="text-lg font-bold bg-gradient-to-r from-primary-600 to-accent-600 dark:from-primary-400 dark:to-accent-400 bg-clip-text text-transparent">
              {t('patients.title', 'Pacientes')}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {onCreatePatient && (
              <motion.button
                onClick={onCreatePatient}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="p-2 bg-gradient-to-r from-primary-500 to-accent-500 text-white rounded-lg shadow-lg"
              >
                <Plus className="w-4 h-4" />
              </motion.button>
            )}
            <motion.button
              onClick={() => refetch()}
              disabled={isFetching}
              whileHover={{ scale: 1.1, rotate: 180 }}
              whileTap={{ scale: 0.9 }}
              className="p-2 bg-white/60 dark:bg-gray-800/60 hover:bg-white/80 dark:hover:bg-gray-800/80 rounded-lg border border-gray-200/50 dark:border-gray-700/50 transition-all disabled:opacity-50"
            >
              <RefreshCw
                className={`w-4 h-4 text-gray-700 dark:text-gray-300 ${
                  isFetching ? 'animate-spin' : ''
                }`}
              />
            </motion.button>
          </div>
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('patients.searchPlaceholder', 'Buscar por nombre o MRN...')}
              className="w-full pl-10 pr-4 py-2 bg-white/60 dark:bg-gray-800/60 border border-gray-200/50 dark:border-gray-700/50 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all text-sm"
            />
          </div>

          {/* Status Filter */}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setStatusFilter(undefined)}
              className={`px-3 py-1 text-xs rounded-full transition-all ${
                !statusFilter
                  ? 'bg-primary-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
              }`}
            >
              {t('patients.all', 'Todos')}
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter('active')}
              className={`px-3 py-1 text-xs rounded-full transition-all ${
                statusFilter === 'active'
                  ? 'bg-green-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
              }`}
            >
              {t('patients.active', 'Activos')}
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter('inactive')}
              className={`px-3 py-1 text-xs rounded-full transition-all ${
                statusFilter === 'inactive'
                  ? 'bg-gray-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
              }`}
            >
              {t('patients.inactive', 'Inactivos')}
            </button>
          </div>
        </form>
      </motion.div>

      {/* Patient List */}
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center h-48 gap-4">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              className="w-12 h-12 border-4 border-primary-200 dark:border-primary-800 border-t-primary-600 dark:border-t-primary-400 rounded-full"
            />
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t('patients.loading', 'Cargando pacientes...')}
            </p>
          </div>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div
              key={`${page}-${statusFilter}-${searchQuery}`}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="space-y-2"
            >
              {patientsData?.items.map((patient, index) => (
                <motion.button
                  key={patient.id}
                  onClick={() => onPatientSelect(patient)}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                  whileHover={{ scale: 1.02, x: 4 }}
                  whileTap={{ scale: 0.98 }}
                  className="w-full flex items-start gap-3 p-4 rounded-xl bg-white/60 dark:bg-gray-800/60 hover:bg-gradient-to-r hover:from-primary-50 hover:to-accent-50 dark:hover:from-primary-900/30 dark:hover:to-accent-900/30 border border-gray-200/50 dark:border-gray-700/50 hover:border-primary-200 dark:hover:border-primary-700 transition-all shadow-sm hover:shadow-lg text-left"
                >
                  {/* Avatar */}
                  <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-primary-400 to-accent-400 rounded-full flex items-center justify-center text-white font-bold text-lg">
                    {patient.given_name[0]}
                    {patient.family_name[0]}
                  </div>

                  {/* Patient Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-gray-900 dark:text-white truncate">
                        {patient.full_name}
                      </span>
                      <span className="text-lg" title={patient.gender}>
                        {getGenderIcon(patient.gender)}
                      </span>
                      <span
                        className={`px-2 py-0.5 text-xs rounded-full ${getStatusColor(
                          patient.status
                        )}`}
                      >
                        {t(`patients.status.${patient.status}`, patient.status)}
                      </span>
                    </div>

                    <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">
                          {patient.mrn}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {formatDate(patient.birth_date)} ({patient.age}{' '}
                          {t('patients.years', 'años')})
                        </span>
                      </div>

                      <div className="flex items-center gap-3">
                        {patient.phone_mobile && (
                          <span className="flex items-center gap-1">
                            <Phone className="w-3 h-3" />
                            {patient.phone_mobile}
                          </span>
                        )}
                        {patient.email && (
                          <span className="flex items-center gap-1 truncate">
                            <Mail className="w-3 h-3" />
                            {patient.email}
                          </span>
                        )}
                      </div>

                      {/* Stats */}
                      {(patient.study_count !== undefined ||
                        patient.document_count !== undefined) && (
                        <div className="flex items-center gap-3 mt-1">
                          {patient.study_count !== undefined && (
                            <span className="flex items-center gap-1 text-primary-600 dark:text-primary-400">
                              <Image className="w-3 h-3" />
                              {patient.study_count}{' '}
                              {t('patients.studies', 'estudios')}
                            </span>
                          )}
                          {patient.document_count !== undefined && (
                            <span className="flex items-center gap-1 text-accent-600 dark:text-accent-400">
                              <FileText className="w-3 h-3" />
                              {patient.document_count}{' '}
                              {t('patients.documents', 'documentos')}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <ChevronRight className="w-5 h-5 text-gray-400 flex-shrink-0" />
                </motion.button>
              ))}

              {/* Empty State */}
              {(!patientsData?.items || patientsData.items.length === 0) && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-center py-12"
                >
                  <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center">
                    <User className="w-8 h-8 text-gray-400" />
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">
                    {searchQuery
                      ? t('patients.noResults', 'No se encontraron pacientes')
                      : t('patients.noPatients', 'No hay pacientes registrados')}
                  </p>
                  {onCreatePatient && !searchQuery && (
                    <button
                      onClick={onCreatePatient}
                      className="mt-4 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors text-sm"
                    >
                      {t('patients.createFirst', 'Crear primer paciente')}
                    </button>
                  )}
                </motion.div>
              )}
            </motion.div>
          </AnimatePresence>
        )}
      </div>

      {/* Pagination */}
      {patientsData && patientsData.total_pages > 1 && (
        <div className="p-4 border-t border-gray-200/50 dark:border-gray-700/50">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">
              {t('patients.showing', 'Mostrando')} {(page - 1) * pageSize + 1}-
              {Math.min(page * pageSize, patientsData.total)}{' '}
              {t('patients.of', 'de')} {patientsData.total}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 bg-white/60 dark:bg-gray-800/60 rounded border border-gray-200/50 dark:border-gray-700/50 disabled:opacity-50"
              >
                {t('common.previous', 'Anterior')}
              </button>
              <button
                onClick={() =>
                  setPage((p) => Math.min(patientsData.total_pages, p + 1))
                }
                disabled={page === patientsData.total_pages}
                className="px-3 py-1 bg-white/60 dark:bg-gray-800/60 rounded border border-gray-200/50 dark:border-gray-700/50 disabled:opacity-50"
              >
                {t('common.next', 'Siguiente')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
