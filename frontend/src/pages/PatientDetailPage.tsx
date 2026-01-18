import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { toast, Toaster } from 'sonner';
import {
  ArrowLeft,
  Calendar,
  Phone,
  Mail,
  MapPin,
  AlertCircle,
  Edit,
  Trash2,
  FileImage,
  FileText,
  Plus,
  Activity,
  LogOut,
  X,
  Heart,
  Clock,
  Shield,
  User,
} from 'lucide-react';
import { usePatient, useDeletePatient } from '@/hooks/usePatients';
import { usePatientStudies } from '@/hooks/useStudies';
import { usePatientDocuments, useDeleteDocument } from '@/hooks/useDocuments';
import { StudyList } from '@/components/StudyList';
import { DocumentList } from '@/components/DocumentList';
import { DocumentViewer } from '@/components/DocumentViewer';
import { DocumentUploader } from '@/components/DocumentUploader';
import { StudyCreateAndUpload } from '@/components/StudyCreateAndUpload';
import PatientForm from '@/components/PatientForm';
import { PatientBanner } from '@/components/PatientBanner';
import ThemeToggle from '@/components/ThemeToggle';
import LanguageSelector from '@/components/LanguageSelector';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { getStatusColor, getGenderColor } from '@/utils/medicalColors';
import type { ImagingStudy, StudySummary, Document as DocType, DocumentSummary } from '@/types';

type TabType = 'overview' | 'studies' | 'documents' | 'history';

export default function PatientDetailPage() {
  const { t } = useTranslation();
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { theme } = useTheme();

  // UI State
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showStudyUploader, setShowStudyUploader] = useState(false);
  const [showDocumentUploader, setShowDocumentUploader] = useState(false);
  const [viewingDocument, setViewingDocument] = useState<Document | DocumentSummary | null>(null);
  const [studiesPage, setStudiesPage] = useState(1);
  const [documentsPage, setDocumentsPage] = useState(1);
  const [studiesViewMode, setStudiesViewMode] = useState<'grid' | 'list'>('grid');
  const [documentsViewMode, setDocumentsViewMode] = useState<'grid' | 'list'>('grid');

  // Data fetching
  const {
    data: patient,
    isLoading: isLoadingPatient,
    error: patientError,
    refetch: refetchPatient,
  } = usePatient(patientId);

  const {
    data: studiesData,
    isLoading: isLoadingStudies,
    refetch: refetchStudies,
  } = usePatientStudies(patientId, studiesPage, 9);

  const {
    data: documentsData,
    isLoading: isLoadingDocuments,
    refetch: refetchDocuments,
  } = usePatientDocuments(patientId, documentsPage, 9);

  const deletePatientMutation = useDeletePatient();
  const deleteDocumentMutation = useDeleteDocument();

  // Handlers
  const handleBack = useCallback(() => {
    navigate('/app/patients');
  }, [navigate]);

  const handleEditPatient = useCallback(() => {
    setShowEditForm(true);
  }, []);

  const handleDeletePatient = useCallback(async () => {
    if (!patient) return;
    if (window.confirm(t('patients.confirmDelete', { name: patient.full_name }))) {
      try {
        await deletePatientMutation.mutateAsync(patient.id);
        toast.success(t('patients.deleteSuccess'));
        navigate('/app/patients');
      } catch (error) {
        toast.error(t('patients.deleteFailed'));
      }
    }
  }, [patient, deletePatientMutation, t, navigate]);

  const handleFormSuccess = useCallback(() => {
    setShowEditForm(false);
    refetchPatient();
    toast.success(t('patients.updateSuccess'));
  }, [refetchPatient, t]);

  const handleViewStudy = useCallback((study: StudySummary | ImagingStudy) => {
    // Navigate to viewer with study context
    navigate(`/app/viewer?studyId=${study.id}`);
  }, [navigate]);

  const handleViewDocument = useCallback((doc: Document | DocumentSummary) => {
    setViewingDocument(doc);
  }, []);

  const handleDeleteDocument = useCallback(async (doc: Document | DocumentSummary) => {
    if (window.confirm(t('document.confirmDelete', { title: doc.title }))) {
      try {
        await deleteDocumentMutation.mutateAsync(doc.id);
        toast.success(t('document.deleteSuccess'));
        refetchDocuments();
      } catch (error) {
        toast.error(t('document.deleteFailed'));
      }
    }
  }, [deleteDocumentMutation, t, refetchDocuments]);

  const handleStudyUploadComplete = useCallback((study?: any) => {
    setShowStudyUploader(false);
    refetchStudies();
    refetchPatient();
    // Don't show toast here since StudyCreateAndUpload already shows one
  }, [refetchStudies, refetchPatient]);

  const handleDocumentUploadComplete = useCallback(() => {
    setShowDocumentUploader(false);
    refetchDocuments();
    refetchPatient();
    toast.success(t('document.uploadSuccess'));
  }, [refetchDocuments, refetchPatient, t]);

  // Format helpers
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString();
  };

  // Helper to get gender symbol from centralized color utility
  const getGenderSymbol = (gender: string) => getGenderColor(gender).symbol;

  // Loading state
  if (isLoadingPatient) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          className="w-12 h-12 border-4 border-primary-200 dark:border-primary-800 border-t-primary-600 dark:border-t-primary-400 rounded-full"
        />
      </div>
    );
  }

  // Error state
  if (patientError || !patient) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
        <AlertCircle className="w-16 h-16 text-red-500 mb-4" />
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
          {t('patients.notFound')}
        </h2>
        <p className="text-gray-500 dark:text-gray-400 mb-4">
          {t('patients.notFoundDescription')}
        </p>
        <button
          onClick={handleBack}
          className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600"
        >
          {t('common.goBack')}
        </button>
      </div>
    );
  }

  const tabs: { id: TabType; label: string; icon: React.ReactNode; count?: number }[] = [
    { id: 'overview', label: t('patients.tabs.overview', 'Resumen'), icon: <User className="w-4 h-4" /> },
    { id: 'studies', label: t('patients.tabs.studies', 'Estudios'), icon: <FileImage className="w-4 h-4" />, count: patient.study_count },
    { id: 'documents', label: t('patients.tabs.documents', 'Documentos'), icon: <FileText className="w-4 h-4" />, count: patient.document_count },
    { id: 'history', label: t('patients.tabs.history', 'Historial'), icon: <Heart className="w-4 h-4" /> },
  ];

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
        className="relative z-10 backdrop-blur-xl bg-white/70 dark:bg-gray-900/70 border-b border-gray-200/50 dark:border-gray-700/50 shadow-lg"
      >
        <div className="px-6 py-3">
          <div className="flex items-center justify-between">
            {/* Left: Back + Logo */}
            <div className="flex items-center gap-4">
              <motion.button
                onClick={handleBack}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="p-2 bg-white/60 dark:bg-gray-800/60 hover:bg-white/80 dark:hover:bg-gray-800/80 rounded-xl border border-gray-200/50 dark:border-gray-700/50 transition-all"
                aria-label={t('common.back')}
              >
                <ArrowLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
              </motion.button>

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
                <h1 className="text-lg font-bold bg-gradient-to-r from-primary-600 to-accent-600 dark:from-primary-400 dark:to-accent-400 bg-clip-text text-transparent">
                  {t('viewer.title')}
                </h1>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {t('navigation.subtitle')}
                </p>
              </div>
            </div>

            {/* Right: Actions */}
            <div className="flex items-center gap-3">
              <motion.button
                onClick={handleEditPatient}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="flex items-center gap-2 px-4 py-2 bg-white/60 dark:bg-gray-800/60 hover:bg-white/80 dark:hover:bg-gray-800/80 border border-gray-200/50 dark:border-gray-700/50 rounded-xl transition-all text-sm font-medium"
                aria-label={t('common.edit')}
              >
                <Edit className="w-4 h-4" />
                {t('common.edit')}
              </motion.button>

              <motion.button
                onClick={handleDeletePatient}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="flex items-center gap-2 px-4 py-2 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 rounded-xl transition-all text-sm font-medium"
                aria-label={t('common.delete')}
              >
                <Trash2 className="w-4 h-4" />
                {t('common.delete')}
              </motion.button>

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
                aria-label={t('auth.logout')}
              >
                <LogOut className="w-5 h-5 text-gray-600 dark:text-gray-400 group-hover:text-error-600 dark:group-hover:text-error-400 transition-colors" />
              </motion.button>
            </div>
          </div>
        </div>
      </motion.header>

      {/* HIPAA-Compliant Patient Banner - Two Identifier Rule */}
      <PatientBanner patient={patient} />

      {/* Main Content - WCAG 2.4.1 Skip Link Target */}
      <main id="main-content" className="relative z-0 flex-1 overflow-auto" tabIndex={-1}>
        <div className="max-w-7xl mx-auto p-6">
          {/* Tabs */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2 mb-6 p-1 bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl shadow-lg w-fit"
          >
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-medium transition-all ${
                  activeTab === tab.id
                    ? 'bg-gradient-to-r from-primary-500 to-accent-500 text-white shadow-lg'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
              >
                {tab.icon}
                {tab.label}
                {tab.count !== undefined && (
                  <span className={`px-2 py-0.5 rounded-full text-xs ${
                    activeTab === tab.id
                      ? 'bg-white/20'
                      : 'bg-gray-200 dark:bg-gray-700'
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </motion.div>

          {/* Tab Content */}
          <AnimatePresence mode="wait">
            {activeTab === 'overview' && (
              <motion.div
                key="overview"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="grid grid-cols-1 lg:grid-cols-3 gap-6"
              >
                {/* Personal Information */}
                <div className="lg:col-span-2 space-y-6">
                  <div className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-6 shadow-lg">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                      <User className="w-5 h-5 text-primary-500" />
                      {t('patients.personalInfo', 'Información Personal')}
                    </h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                          {t('patients.fullName', 'Nombre Completo')}
                        </label>
                        <p className="text-gray-900 dark:text-white font-medium">{patient.full_name}</p>
                      </div>

                      <div>
                        <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                          {t('patients.mrn', 'MRN')}
                        </label>
                        <p className="text-gray-900 dark:text-white font-mono">{patient.mrn}</p>
                      </div>

                      <div>
                        <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {t('patients.birthDate', 'Fecha de Nacimiento')}
                        </label>
                        <p className="text-gray-900 dark:text-white">
                          {formatDate(patient.birth_date)} ({patient.age} {t('patients.years')})
                        </p>
                      </div>

                      <div>
                        <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                          {t('patients.gender', 'Género')}
                        </label>
                        <p className="text-gray-900 dark:text-white">
                          {getGenderSymbol(patient.gender)} {t(`patients.genders.${patient.gender}`)}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Contact Information */}
                  <div className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-6 shadow-lg">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                      <Phone className="w-5 h-5 text-primary-500" />
                      {t('patients.contactInfo', 'Información de Contacto')}
                    </h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {patient.phone_mobile && (
                        <div>
                          <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide flex items-center gap-1">
                            <Phone className="w-3 h-3" />
                            {t('patients.phoneMobile', 'Teléfono Móvil')}
                          </label>
                          <p className="text-gray-900 dark:text-white">{patient.phone_mobile}</p>
                        </div>
                      )}

                      {patient.phone_home && (
                        <div>
                          <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                            {t('patients.phoneHome', 'Teléfono Casa')}
                          </label>
                          <p className="text-gray-900 dark:text-white">{patient.phone_home}</p>
                        </div>
                      )}

                      {patient.email && (
                        <div className="md:col-span-2">
                          <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide flex items-center gap-1">
                            <Mail className="w-3 h-3" />
                            {t('patients.email', 'Email')}
                          </label>
                          <p className="text-gray-900 dark:text-white">{patient.email}</p>
                        </div>
                      )}

                      {(patient.address_line1 || patient.city) && (
                        <div className="md:col-span-2">
                          <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide flex items-center gap-1">
                            <MapPin className="w-3 h-3" />
                            {t('patients.address', 'Dirección')}
                          </label>
                          <p className="text-gray-900 dark:text-white">
                            {[patient.address_line1, patient.address_line2, patient.city, patient.state, patient.postal_code, patient.country]
                              .filter(Boolean)
                              .join(', ')}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Emergency Contact */}
                  {patient.emergency_contact_name && (
                    <div className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-6 shadow-lg">
                      <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                        <AlertCircle className="w-5 h-5 text-red-500" />
                        {t('patients.emergencyContact', 'Contacto de Emergencia')}
                      </h3>

                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                          <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                            {t('patients.name', 'Nombre')}
                          </label>
                          <p className="text-gray-900 dark:text-white">{patient.emergency_contact_name}</p>
                        </div>
                        {patient.emergency_contact_phone && (
                          <div>
                            <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                              {t('patients.phone', 'Teléfono')}
                            </label>
                            <p className="text-gray-900 dark:text-white">{patient.emergency_contact_phone}</p>
                          </div>
                        )}
                        {patient.emergency_contact_relationship && (
                          <div>
                            <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                              {t('patients.relationship', 'Relación')}
                            </label>
                            <p className="text-gray-900 dark:text-white">{patient.emergency_contact_relationship}</p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Sidebar */}
                <div className="space-y-6">
                  {/* Quick Stats */}
                  <div className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-6 shadow-lg">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                      <Activity className="w-5 h-5 text-primary-500" />
                      {t('patients.quickStats', 'Estadísticas')}
                    </h3>

                    <div className="space-y-4">
                      <div className="flex items-center justify-between p-3 bg-primary-50 dark:bg-primary-900/20 rounded-xl">
                        <div className="flex items-center gap-2">
                          <FileImage className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                          <span className="text-gray-700 dark:text-gray-300">{t('patients.studies')}</span>
                        </div>
                        <span className="text-2xl font-bold text-primary-600 dark:text-primary-400">
                          {patient.study_count || 0}
                        </span>
                      </div>

                      <div className="flex items-center justify-between p-3 bg-accent-50 dark:bg-accent-900/20 rounded-xl">
                        <div className="flex items-center gap-2">
                          <FileText className="w-5 h-5 text-accent-600 dark:text-accent-400" />
                          <span className="text-gray-700 dark:text-gray-300">{t('patients.documents')}</span>
                        </div>
                        <span className="text-2xl font-bold text-accent-600 dark:text-accent-400">
                          {patient.document_count || 0}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Insurance */}
                  {patient.insurance_provider && (
                    <div className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-6 shadow-lg">
                      <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                        <Shield className="w-5 h-5 text-primary-500" />
                        {t('patients.insurance', 'Seguro')}
                      </h3>

                      <div className="space-y-2">
                        <div>
                          <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                            {t('patients.insuranceProvider', 'Aseguradora')}
                          </label>
                          <p className="text-gray-900 dark:text-white">{patient.insurance_provider}</p>
                        </div>
                        {patient.insurance_policy_number && (
                          <div>
                            <label className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                              {t('patients.policyNumber', 'Número de Póliza')}
                            </label>
                            <p className="text-gray-900 dark:text-white font-mono">{patient.insurance_policy_number}</p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Timestamps */}
                  <div className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-6 shadow-lg">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                      <Clock className="w-5 h-5 text-primary-500" />
                      {t('patients.timestamps', 'Registro')}
                    </h3>

                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-500 dark:text-gray-400">{t('common.createdAt')}</span>
                        <span className="text-gray-900 dark:text-white">{formatDate(patient.created_at)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500 dark:text-gray-400">{t('common.updatedAt')}</span>
                        <span className="text-gray-900 dark:text-white">{formatDate(patient.updated_at)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Quick Actions */}
                  <div className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-6 shadow-lg">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
                      {t('patients.quickActions', 'Acciones Rápidas')}
                    </h3>

                    <div className="space-y-2">
                      <button
                        onClick={() => { setActiveTab('studies'); setShowStudyUploader(true); }}
                        className="w-full flex items-center gap-2 px-4 py-2.5 bg-primary-500 text-white rounded-xl hover:bg-primary-600 transition-colors"
                      >
                        <Plus className="w-4 h-4" />
                        {t('study.uploadStudy', 'Subir Estudio')}
                      </button>
                      <button
                        onClick={() => { setActiveTab('documents'); setShowDocumentUploader(true); }}
                        className="w-full flex items-center gap-2 px-4 py-2.5 bg-accent-500 text-white rounded-xl hover:bg-accent-600 transition-colors"
                      >
                        <Plus className="w-4 h-4" />
                        {t('document.uploadDocument', 'Subir Documento')}
                      </button>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === 'studies' && (
              <motion.div
                key="studies"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-6 shadow-lg"
              >
                <StudyList
                  studies={studiesData?.items || []}
                  isLoading={isLoadingStudies}
                  page={studiesPage}
                  totalPages={studiesData?.total_pages || 1}
                  total={studiesData?.total || 0}
                  onPageChange={setStudiesPage}
                  onViewStudy={handleViewStudy}
                  onCreateStudy={() => setShowStudyUploader(true)}
                  viewMode={studiesViewMode}
                  onViewModeChange={setStudiesViewMode}
                />
              </motion.div>
            )}

            {activeTab === 'documents' && (
              <motion.div
                key="documents"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-6 shadow-lg"
              >
                <DocumentList
                  documents={documentsData?.items || []}
                  isLoading={isLoadingDocuments}
                  page={documentsPage}
                  totalPages={documentsData?.total_pages || 1}
                  total={documentsData?.total || 0}
                  onPageChange={setDocumentsPage}
                  onViewDocument={handleViewDocument}
                  onDeleteDocument={handleDeleteDocument}
                  onUploadDocument={() => setShowDocumentUploader(true)}
                  viewMode={documentsViewMode}
                  onViewModeChange={setDocumentsViewMode}
                />
              </motion.div>
            )}

            {activeTab === 'history' && (
              <motion.div
                key="history"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl border border-gray-200/50 dark:border-gray-700/50 rounded-2xl p-6 shadow-lg"
              >
                <div className="text-center py-12">
                  <Heart className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
                    {t('patients.noMedicalHistory', 'Sin historial médico')}
                  </h3>
                  <p className="text-gray-500 dark:text-gray-400">
                    {t('patients.medicalHistoryComingSoon', 'El historial médico estará disponible próximamente')}
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* Edit Patient Modal */}
      <AnimatePresence>
        {showEditForm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
            onClick={() => setShowEditForm(false)}
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
                  {t('patients.editPatient')}
                </h2>
                <button
                  onClick={() => setShowEditForm(false)}
                  className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6">
                <PatientForm
                  patient={patient}
                  onSuccess={handleFormSuccess}
                  onCancel={() => setShowEditForm(false)}
                />
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Study Create and Upload Modal */}
      <AnimatePresence>
        {showStudyUploader && patientId && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
            onClick={() => setShowStudyUploader(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-3xl max-h-[90vh] overflow-y-auto bg-white dark:bg-gray-900 rounded-2xl shadow-2xl"
              onClick={e => e.stopPropagation()}
            >
              <div className="sticky top-0 z-10 flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                  {t('study.newBrainMRI', 'Nuevo Estudio de IRM Cerebral')}
                </h2>
                <button
                  onClick={() => setShowStudyUploader(false)}
                  className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6">
                <StudyCreateAndUpload
                  patientId={patientId}
                  patientName={patient?.full_name}
                  onComplete={handleStudyUploadComplete}
                  onCancel={() => setShowStudyUploader(false)}
                />
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Document Uploader Modal */}
      <AnimatePresence>
        {showDocumentUploader && patientId && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
            onClick={() => setShowDocumentUploader(false)}
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
                  {t('document.uploadDocument')}
                </h2>
                <button
                  onClick={() => setShowDocumentUploader(false)}
                  className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6">
                <DocumentUploader
                  patientId={patientId}
                  onSuccess={handleDocumentUploadComplete}
                  onCancel={() => setShowDocumentUploader(false)}
                />
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

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
