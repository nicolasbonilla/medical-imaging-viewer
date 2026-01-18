import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Brain,
  FileImage,
  Upload,
  Check,
  ArrowRight,
  ArrowLeft,
  AlertCircle,
  Eye,
} from 'lucide-react';
import { toast } from 'sonner';
import { studyAPI } from '@/services/studyApi';
import { StudyUploader } from './StudyUploader';
import type { StudyCreate, Modality, ImagingStudy } from '@/types';
import type { UploadFile } from '@/hooks/useUpload';

interface StudyCreateAndUploadProps {
  patientId: string;
  patientName?: string;
  onComplete?: (study: ImagingStudy) => void;
  onCancel?: () => void;
}

type Step = 'metadata' | 'upload' | 'complete';

export const StudyCreateAndUpload: React.FC<StudyCreateAndUploadProps> = ({
  patientId,
  patientName,
  onComplete,
  onCancel,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState<Step>('metadata');
  const [isCreating, setIsCreating] = useState(false);
  const [createdStudy, setCreatedStudy] = useState<ImagingStudy | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadFile[]>([]);

  // Form state for study metadata
  const [formData, setFormData] = useState<Partial<StudyCreate>>({
    patient_id: patientId,
    modality: 'MR' as Modality, // Default to MRI for brain imaging
    study_date: new Date().toISOString().split('T')[0],
    study_description: '',
    body_site: 'BRAIN',
    reason_for_study: '',
    referring_physician_name: '',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  // Modality options - focus on MR for brain imaging
  const modalityOptions: { value: Modality; label: string }[] = [
    { value: 'MR', label: t('study.modality.MR', 'MRI (Resonancia Magnética)') },
    { value: 'CT', label: t('study.modality.CT', 'CT (Tomografía)') },
    { value: 'OT', label: t('study.modality.OT', 'Otro') },
  ];

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: '' }));
    }
  };

  const validateMetadata = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.study_date) {
      newErrors.study_date = t('study.errors.dateRequired', 'La fecha del estudio es requerida');
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleCreateStudy = async () => {
    if (!validateMetadata()) return;

    setIsCreating(true);
    try {
      const studyData: StudyCreate = {
        patient_id: patientId,
        modality: formData.modality || 'MR',
        study_date: formData.study_date || new Date().toISOString().split('T')[0],
        study_description: formData.study_description || undefined,
        body_site: formData.body_site || 'BRAIN',
        reason_for_study: formData.reason_for_study || undefined,
        referring_physician_name: formData.referring_physician_name || undefined,
      };

      const study = await studyAPI.create(studyData);
      setCreatedStudy(study);
      setCurrentStep('upload');
      toast.success(t('study.createSuccess', 'Estudio creado correctamente'));
    } catch (error) {
      console.error('Error creating study:', error);
      toast.error(t('study.createError', 'Error al crear el estudio'));
    } finally {
      setIsCreating(false);
    }
  };

  const handleUploadComplete = useCallback((files: UploadFile[]) => {
    setUploadedFiles(files);
    setCurrentStep('complete');
    toast.success(t('study.uploadComplete', 'Imágenes subidas correctamente'));
  }, [t]);

  const handleViewStudy = () => {
    if (createdStudy) {
      navigate(`/app/viewer?studyId=${createdStudy.id}`);
    }
  };

  const handleFinish = () => {
    if (createdStudy && onComplete) {
      onComplete(createdStudy);
    }
  };

  const inputClass = (field: string) =>
    `w-full px-4 py-3 bg-white/60 dark:bg-gray-800/60 border ${
      errors[field]
        ? 'border-red-500 focus:ring-red-500'
        : 'border-gray-200/50 dark:border-gray-700/50 focus:ring-primary-500'
    } rounded-xl focus:ring-2 focus:border-transparent transition-all`;

  // Step indicator
  const steps = [
    { id: 'metadata', label: t('study.steps.metadata', 'Datos del Estudio'), icon: FileImage },
    { id: 'upload', label: t('study.steps.upload', 'Subir Imágenes'), icon: Upload },
    { id: 'complete', label: t('study.steps.complete', 'Completado'), icon: Check },
  ];

  const currentStepIndex = steps.findIndex((s) => s.id === currentStep);

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center justify-center gap-2">
        {steps.map((step, index) => {
          const Icon = step.icon;
          const isActive = step.id === currentStep;
          const isCompleted = index < currentStepIndex;

          return (
            <React.Fragment key={step.id}>
              <div
                className={`flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
                  isActive
                    ? 'bg-primary-500 text-white'
                    : isCompleted
                    ? 'bg-green-500 text-white'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
                }`}
              >
                <Icon className="w-5 h-5" />
                <span className="font-medium hidden sm:inline">{step.label}</span>
              </div>
              {index < steps.length - 1 && (
                <ArrowRight className="w-5 h-5 text-gray-400" />
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Patient info banner */}
      {patientName && (
        <div className="flex items-center gap-3 px-4 py-3 bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 rounded-xl">
          <Brain className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          <span className="text-primary-700 dark:text-primary-300">
            {t('study.forPatient', 'Estudio para')}: <strong>{patientName}</strong>
          </span>
        </div>
      )}

      {/* Step content */}
      <AnimatePresence mode="wait">
        {currentStep === 'metadata' && (
          <motion.div
            key="metadata"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="space-y-6"
          >
            <div className="text-center mb-6">
              <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                {t('study.createTitle', 'Crear Nuevo Estudio de IRM')}
              </h3>
              <p className="text-gray-500 dark:text-gray-400 mt-1">
                {t('study.createDescription', 'Ingresa los datos del estudio antes de subir las imágenes NIfTI')}
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Modality */}
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('study.form.modality', 'Modalidad')} *
                </label>
                <select
                  name="modality"
                  value={formData.modality}
                  onChange={handleChange}
                  className={inputClass('modality')}
                >
                  {modalityOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Study Date */}
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('study.form.studyDate', 'Fecha del Estudio')} *
                </label>
                <input
                  type="date"
                  name="study_date"
                  value={formData.study_date}
                  onChange={handleChange}
                  className={inputClass('study_date')}
                />
                {errors.study_date && (
                  <p className="text-red-500 text-xs mt-1">{errors.study_date}</p>
                )}
              </div>

              {/* Body Site */}
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('study.form.bodySite', 'Región Anatómica')}
                </label>
                <input
                  type="text"
                  name="body_site"
                  value={formData.body_site}
                  onChange={handleChange}
                  placeholder="BRAIN"
                  className={inputClass('body_site')}
                />
              </div>

              {/* Referring Physician */}
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('study.form.referringPhysician', 'Médico Referente')}
                </label>
                <input
                  type="text"
                  name="referring_physician_name"
                  value={formData.referring_physician_name}
                  onChange={handleChange}
                  className={inputClass('referring_physician_name')}
                />
              </div>

              {/* Study Description */}
              <div className="md:col-span-2">
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('study.form.description', 'Descripción del Estudio')}
                </label>
                <input
                  type="text"
                  name="study_description"
                  value={formData.study_description}
                  onChange={handleChange}
                  placeholder={t('study.form.descriptionPlaceholder', 'Ej: IRM Cerebro con contraste')}
                  className={inputClass('study_description')}
                />
              </div>

              {/* Reason for Study */}
              <div className="md:col-span-2">
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('study.form.reason', 'Motivo del Estudio')}
                </label>
                <textarea
                  name="reason_for_study"
                  value={formData.reason_for_study}
                  onChange={handleChange}
                  rows={3}
                  placeholder={t('study.form.reasonPlaceholder', 'Ej: Evaluación de lesiones cerebrales')}
                  className={inputClass('reason_for_study')}
                />
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
              {onCancel && (
                <button
                  onClick={onCancel}
                  disabled={isCreating}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                >
                  {t('common.cancel', 'Cancelar')}
                </button>
              )}
              <button
                onClick={handleCreateStudy}
                disabled={isCreating}
                className="flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-primary-500 to-accent-500 text-white rounded-xl hover:from-primary-600 hover:to-accent-600 transition-all disabled:opacity-50"
              >
                {isCreating ? (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full"
                  />
                ) : (
                  <>
                    {t('study.createAndContinue', 'Crear y Continuar')}
                    <ArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>
            </div>
          </motion.div>
        )}

        {currentStep === 'upload' && createdStudy && (
          <motion.div
            key="upload"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="space-y-6"
          >
            <div className="text-center mb-6">
              <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                {t('study.uploadTitle', 'Subir Imágenes NIfTI')}
              </h3>
              <p className="text-gray-500 dark:text-gray-400 mt-1">
                {t('study.uploadDescription', 'Arrastra o selecciona archivos .nii o .nii.gz para el estudio')}
              </p>
            </div>

            {/* Study info card */}
            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 mb-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <span className="text-gray-500 dark:text-gray-400">{t('study.accession', 'Accesión')}:</span>
                  <p className="font-mono text-gray-900 dark:text-white">{createdStudy.accession_number || 'N/A'}</p>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-gray-400">{t('study.modality', 'Modalidad')}:</span>
                  <p className="font-medium text-gray-900 dark:text-white">{createdStudy.modality}</p>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-gray-400">{t('study.date', 'Fecha')}:</span>
                  <p className="text-gray-900 dark:text-white">{new Date(createdStudy.study_date).toLocaleDateString()}</p>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-gray-400">{t('study.status.label', 'Estado')}:</span>
                  <p className="text-gray-900 dark:text-white capitalize">{t(`study.status.${createdStudy.status}`, createdStudy.status)}</p>
                </div>
              </div>
            </div>

            <StudyUploader
              studyId={createdStudy.id}
              modality={createdStudy.modality}
              seriesDescription={createdStudy.study_description || 'Brain MRI'}
              onComplete={handleUploadComplete}
              onCancel={() => setCurrentStep('metadata')}
              acceptedTypes={['.nii', '.nii.gz', 'application/x-nifti']}
            />
          </motion.div>
        )}

        {currentStep === 'complete' && createdStudy && (
          <motion.div
            key="complete"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center space-y-6"
          >
            <div className="w-20 h-20 mx-auto bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center">
              <Check className="w-10 h-10 text-green-600 dark:text-green-400" />
            </div>

            <div>
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white">
                {t('study.completeTitle', '¡Estudio Creado Exitosamente!')}
              </h3>
              <p className="text-gray-500 dark:text-gray-400 mt-2">
                {t('study.completeDescription', 'Las imágenes han sido subidas y están listas para visualizar y segmentar.')}
              </p>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 gap-4 max-w-md mx-auto">
              <div className="bg-primary-50 dark:bg-primary-900/20 rounded-xl p-4">
                <p className="text-3xl font-bold text-primary-600 dark:text-primary-400">
                  {uploadedFiles.length}
                </p>
                <p className="text-sm text-primary-600/70 dark:text-primary-400/70">
                  {t('study.filesUploaded', 'Archivos subidos')}
                </p>
              </div>
              <div className="bg-accent-50 dark:bg-accent-900/20 rounded-xl p-4">
                <p className="text-3xl font-bold text-accent-600 dark:text-accent-400">
                  {createdStudy.modality}
                </p>
                <p className="text-sm text-accent-600/70 dark:text-accent-400/70">
                  {t('study.modalityLabel', 'Modalidad')}
                </p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
              <button
                onClick={handleViewStudy}
                className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-primary-500 to-accent-500 text-white rounded-xl hover:from-primary-600 hover:to-accent-600 transition-all font-medium"
              >
                <Eye className="w-5 h-5" />
                {t('study.viewAndSegment', 'Ver y Segmentar Imágenes')}
              </button>
              <button
                onClick={handleFinish}
                className="flex items-center gap-2 px-6 py-3 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-xl transition-colors"
              >
                {t('study.backToPatient', 'Volver al Paciente')}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default StudyCreateAndUpload;
