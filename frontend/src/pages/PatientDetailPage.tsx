import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import AppHeader from '../components/AppHeader';
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
import UserMenu from '@/components/UserMenu';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { getStatusColor, getGenderColor } from '@/utils/medicalColors';
import type { ImagingStudy, StudySummary, Document as DocType, DocumentSummary } from '@/types';

type TabType = 'studies' | 'documents';

export default function PatientDetailPage() {
  const { t } = useTranslation();
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { theme } = useTheme();

  // UI State
  const [activeTab, setActiveTab] = useState<TabType>('studies');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showStudyUploader, setShowStudyUploader] = useState(false);
  const [showDocumentUploader, setShowDocumentUploader] = useState(false);
  const [viewingDocument, setViewingDocument] = useState<DocType | DocumentSummary | null>(null);
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

  const handleViewDocument = useCallback((doc: DocType | DocumentSummary) => {
    setViewingDocument(doc);
  }, []);

  const handleDeleteDocument = useCallback(async (doc: DocType | DocumentSummary) => {
    if (window.confirm(t('document.confirmDelete', { title: doc.title }))) {
      try {
        await deleteDocumentMutation.mutateAsync({ id: doc.id, patientId: doc.patient_id });
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

  const handleDocumentUploadComplete = useCallback((_documents?: DocType[]) => {
    setShowDocumentUploader(false);
    refetchDocuments();
    refetchPatient();
    toast.success(t('document.messages.uploadSuccess'));
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
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#030712' }}>
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          className="border-2 border-gray-700 border-t-blue-500 rounded-full"
          style={{ width: 36, height: 36 }}
        />
      </div>
    );
  }

  // Error state
  if (patientError || !patient) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center" style={{ background: '#030712' }}>
        <AlertCircle style={{ width: 36, height: 36, color: '#F87171', marginBottom: 12 }} />
        <h2 style={{ fontSize: 17, fontWeight: 700, color: '#F9FAFB', marginBottom: 4 }}>
          {t('patients.notFound')}
        </h2>
        <p style={{ fontSize: 13, color: '#9CA3AF', marginBottom: 16 }}>
          {t('patients.notFoundDescription')}
        </p>
        <button
          onClick={handleBack}
          className="bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          style={{ height: 36, padding: '0 16px', borderRadius: 6, fontSize: 13, fontWeight: 500 }}
        >
          {t('common.goBack')}
        </button>
      </div>
    );
  }

  const tabs: { id: TabType; label: string; icon: React.ReactNode; count?: number }[] = [
    { id: 'studies', label: t('patients.tabs.studies', 'Studies'), icon: <FileImage style={{ width: 16, height: 16 }} />, count: patient.study_count },
    { id: 'documents', label: t('patients.tabs.documents', 'Documents'), icon: <FileText style={{ width: 16, height: 16 }} />, count: patient.document_count },
  ];

  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#030712' }}>

      {/* Header */}
      <AppHeader
        breadcrumbs={[
          { label: t('nav.home', 'Home'), path: '/app' },
          { label: t('patients.title'), path: '/app/patients' },
          { label: patient?.full_name || '...' },
        ]}
        onBack={handleBack}
      />

      {/* Patient Banner with Edit/Delete */}
      <div className="relative">
        <PatientBanner patient={patient} />
        <div className="absolute flex items-center" style={{ top: 12, right: 24, gap: 4, zIndex: 10 }}>
          <button onClick={handleEditPatient}
            className="flex items-center justify-center border border-gray-700 hover:bg-gray-700 transition-colors"
            style={{ width: 36, height: 36, borderRadius: 6, background: '#1F2937' }}
            title={t('common.edit')}>
            <Edit style={{ width: 16, height: 16, color: '#9CA3AF' }} />
          </button>
          <button onClick={handleDeletePatient}
            className="flex items-center justify-center border border-gray-700 hover:bg-red-900/30 transition-colors"
            style={{ width: 36, height: 36, borderRadius: 6, background: '#1F2937' }}
            title={t('common.delete')}>
            <Trash2 style={{ width: 16, height: 16, color: '#9CA3AF' }} />
          </button>
        </div>
      </div>

      {/* Main Content - WCAG 2.4.1 Skip Link Target */}
      <main id="main-content" className="relative z-0 flex-1 overflow-auto" style={{ padding: '16px 24px' }} tabIndex={-1}>
        <div className="max-w-7xl mx-auto" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* ════════════════════════════════════════════════
              SECTION 1: Patient Information (always visible)
              ════════════════════════════════════════════════ */}

          {/* Patient Identification — single full-width card, 7 fields in one grid */}
          <div className="border border-gray-700" style={{ background: '#1F2937', borderRadius: 8, padding: 16 }}>
            <h3 className="flex items-center" style={{ gap: 6, fontSize: 14, fontWeight: 600, color: '#F9FAFB', margin: '0 0 12px 0' }}>
              <User style={{ width: 16, height: 16, color: '#60A5FA' }} />
              {t('patients.personalInfo', 'Patient Identification')}
            </h3>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7" style={{ gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                  {t('patients.fullName', 'Full Name')}
                </label>
                <p style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>{patient.full_name}</p>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                  {t('patients.mrn', 'MRN')}
                </label>
                <p className="font-mono" style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>{patient.mrn}</p>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                  {t('patients.birthDate', 'Date of Birth')}
                </label>
                <p style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>
                  {formatDate(patient.birth_date)} ({patient.age}{t('patients.years', 'y')})
                </p>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                  {t('patients.gender', 'Gender')}
                </label>
                <p style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>
                  {getGenderSymbol(patient.gender)} {t(`patients.genders.${patient.gender}`)}
                </p>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                  {t('patients.status.label', 'Status')}
                </label>
                <p className="flex items-center" style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0, gap: 6 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: patient.status === 'active' ? '#10B981' :
                                patient.status === 'deceased' ? '#6B7280' : '#94A3B8',
                  }} />
                  {t(`patients.status.${patient.status}`, patient.status)}
                </p>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                  {t('common.createdAt', 'Created')}
                </label>
                <p style={{ fontSize: 14, fontWeight: 500, color: '#9CA3AF', margin: 0 }}>{formatDate(patient.created_at)}</p>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                  {t('common.updatedAt', 'Updated')}
                </label>
                <p style={{ fontSize: 14, fontWeight: 500, color: '#9CA3AF', margin: 0 }}>{formatDate(patient.updated_at)}</p>
              </div>
            </div>
          </div>

          {/* Contact + Emergency + Insurance — align-start so empty cards don't stretch */}
          <div className="grid grid-cols-1 md:grid-cols-3" style={{ gap: 16, alignItems: 'start' }}>

            {/* Contact Information */}
            <div className="border border-gray-700" style={{ background: '#1F2937', borderRadius: 8, padding: 16 }}>
              <h3 className="flex items-center" style={{ gap: 6, fontSize: 14, fontWeight: 600, color: '#F9FAFB', margin: '0 0 12px 0' }}>
                <Phone style={{ width: 16, height: 16, color: '#34D399' }} />
                {t('patients.contactInfo', 'Contact Information')}
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {patient.phone_mobile && (
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                      {t('patients.phoneMobile', 'Mobile Phone')}
                    </label>
                    <p style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>{patient.phone_mobile}</p>
                  </div>
                )}
                {patient.email && (
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                      {t('patients.email', 'Email')}
                    </label>
                    <p style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>{patient.email}</p>
                  </div>
                )}
                {(patient.address_line1 || patient.city) && (
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                      {t('patients.address', 'Address')}
                    </label>
                    <p style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>
                      {[patient.address_line1, patient.address_line2, patient.city, patient.state, patient.postal_code, patient.country]
                        .filter(Boolean)
                        .join(', ')}
                    </p>
                  </div>
                )}
                {!patient.phone_mobile && !patient.email && !patient.address_line1 && !patient.city && (
                  <p style={{ fontSize: 12, color: '#6B7280', margin: 0, fontStyle: 'italic' }}>
                    {t('patients.noContactInfo', 'No contact information available')}
                  </p>
                )}
              </div>
            </div>

            {/* Emergency Contact */}
            <div className="border border-gray-700" style={{ background: '#1F2937', borderRadius: 8, padding: 16 }}>
              <h3 className="flex items-center" style={{ gap: 6, fontSize: 14, fontWeight: 600, color: '#F9FAFB', margin: '0 0 12px 0' }}>
                <AlertCircle style={{ width: 16, height: 16, color: '#F87171' }} />
                {t('patients.emergencyContact', 'Emergency Contact')}
              </h3>
              {patient.emergency_contact_name ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                      {t('patients.name', 'Name')}
                    </label>
                    <p style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>{patient.emergency_contact_name}</p>
                  </div>
                  {patient.emergency_contact_phone && (
                    <div>
                      <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                        {t('patients.phone', 'Phone')}
                      </label>
                      <p style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>{patient.emergency_contact_phone}</p>
                    </div>
                  )}
                  {patient.emergency_contact_relationship && (
                    <div>
                      <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                        {t('patients.relationship', 'Relationship')}
                      </label>
                      <p style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>{patient.emergency_contact_relationship}</p>
                    </div>
                  )}
                </div>
              ) : (
                <p style={{ fontSize: 12, color: '#6B7280', margin: 0, fontStyle: 'italic' }}>
                  {t('patients.noEmergencyContact', 'No emergency contact registered')}
                </p>
              )}
            </div>

            {/* Insurance */}
            <div className="border border-gray-700" style={{ background: '#1F2937', borderRadius: 8, padding: 16 }}>
              <h3 className="flex items-center" style={{ gap: 6, fontSize: 14, fontWeight: 600, color: '#F9FAFB', margin: '0 0 12px 0' }}>
                <Shield style={{ width: 16, height: 16, color: '#60A5FA' }} />
                {t('patients.insurance', 'Insurance')}
              </h3>
              {patient.insurance_provider ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                      {t('patients.insuranceProvider', 'Provider')}
                    </label>
                    <p style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>{patient.insurance_provider}</p>
                  </div>
                  {patient.insurance_policy_number && (
                    <div>
                      <label style={{ display: 'block', fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
                        {t('patients.policyNumber', 'Policy Number')}
                      </label>
                      <p className="font-mono" style={{ fontSize: 14, fontWeight: 500, color: '#E5E7EB', margin: 0 }}>{patient.insurance_policy_number}</p>
                    </div>
                  )}
                </div>
              ) : (
                <p style={{ fontSize: 12, color: '#6B7280', margin: 0, fontStyle: 'italic' }}>
                  {t('patients.noInsurance', 'No insurance information')}
                </p>
              )}
            </div>
          </div>

          {/* ════════════════════════════════════════════════
              SECTION 2: Collections (tabs for Studies / Documents)
              ════════════════════════════════════════════════ */}
          <div className="flex items-center border border-gray-700 w-fit"
            style={{ gap: 4, padding: 4, background: '#1F2937', borderRadius: 8 }}>
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center transition-colors ${
                  activeTab === tab.id
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:bg-gray-700'
                }`}
                style={{ height: 36, gap: 6, padding: '0 14px', borderRadius: 6, fontSize: 13, fontWeight: 500 }}
              >
                {tab.icon}
                {tab.label}
                {tab.count !== undefined && (
                  <span className={`rounded-full ${
                    activeTab === tab.id ? 'bg-white/20' : 'bg-gray-700'
                  }`} style={{ fontSize: 11, padding: '1px 6px' }}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">
            {activeTab === 'studies' && (
              <motion.div
                key="studies"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="border border-gray-700"
                style={{ background: '#1F2937', borderRadius: 8, padding: 16 }}
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
                className="border border-gray-700"
                style={{ background: '#1F2937', borderRadius: 8, padding: 16 }}
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
              className="w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-gray-700"
              style={{ background: '#111827', borderRadius: 8 }}
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
              className="w-full max-w-3xl max-h-[90vh] overflow-y-auto border border-gray-700"
              style={{ background: '#111827', borderRadius: 8 }}
              onClick={e => e.stopPropagation()}
            >
              <div className="sticky top-0 z-10 flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                  {t('study.newBrainMRI', 'New Brain MRI Study')}
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
              className="w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-gray-700"
              style={{ background: '#111827', borderRadius: 8 }}
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
                  onComplete={handleDocumentUploadComplete}
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
