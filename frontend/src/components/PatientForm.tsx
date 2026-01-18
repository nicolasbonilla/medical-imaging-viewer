import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { X, Save, User, Phone, Mail, MapPin, Heart, Shield } from 'lucide-react';
import { useCreatePatient, useUpdatePatient } from '@/hooks/usePatients';
import { toast } from 'sonner';
import type { PatientCreate, PatientUpdate, Patient, Gender } from '@/types';

export interface PatientFormProps {
  patient?: Patient;
  onSubmit?: (data: PatientCreate | PatientUpdate) => Promise<void>;
  onSuccess?: () => void;
  onCancel: () => void;
  isLoading?: boolean;
}

const getInitialFormData = (patient?: Patient): PatientCreate => ({
  mrn: patient?.mrn || '',
  given_name: patient?.given_name || '',
  middle_name: patient?.middle_name || '',
  family_name: patient?.family_name || '',
  name_prefix: patient?.name_prefix || '',
  name_suffix: patient?.name_suffix || '',
  birth_date: patient?.birth_date || '',
  gender: patient?.gender || 'unknown',
  phone_home: patient?.phone_home || '',
  phone_mobile: patient?.phone_mobile || '',
  phone_work: patient?.phone_work || '',
  email: patient?.email || '',
  address_line1: patient?.address_line1 || '',
  address_line2: patient?.address_line2 || '',
  city: patient?.city || '',
  state: patient?.state || '',
  postal_code: patient?.postal_code || '',
  country: patient?.country || 'COL',
  emergency_contact_name: patient?.emergency_contact_name || '',
  emergency_contact_phone: patient?.emergency_contact_phone || '',
  emergency_contact_relationship: patient?.emergency_contact_relationship || '',
  insurance_provider: patient?.insurance_provider || '',
  insurance_policy_number: patient?.insurance_policy_number || '',
});

export default function PatientForm({
  patient,
  onSubmit,
  onSuccess,
  onCancel,
  isLoading: externalLoading = false,
}: PatientFormProps) {
  const createMutation = useCreatePatient();
  const updateMutation = useUpdatePatient();
  const isLoading = externalLoading || createMutation.isPending || updateMutation.isPending;
  const { t } = useTranslation();
  const isEdit = !!patient;

  const [formData, setFormData] = useState<PatientCreate>(getInitialFormData(patient));

  // Update form data when patient prop changes (for edit mode)
  useEffect(() => {
    if (patient) {
      setFormData(getInitialFormData(patient));
    }
  }, [patient?.id]);

  const [errors, setErrors] = useState<Record<string, string>>({});

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: '' }));
    }
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.mrn) {
      newErrors.mrn = t('patients.form.errors.mrnRequired', 'MRN es requerido');
    }
    if (!formData.given_name) {
      newErrors.given_name = t(
        'patients.form.errors.givenNameRequired',
        'Nombre es requerido'
      );
    }
    if (!formData.family_name) {
      newErrors.family_name = t(
        'patients.form.errors.familyNameRequired',
        'Apellido es requerido'
      );
    }
    if (!formData.birth_date) {
      newErrors.birth_date = t(
        'patients.form.errors.birthDateRequired',
        'Fecha de nacimiento es requerida'
      );
    }
    if (!formData.phone_mobile) {
      newErrors.phone_mobile = t(
        'patients.form.errors.phoneMobileRequired',
        'Teléfono móvil es requerido'
      );
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    try {
      if (onSubmit) {
        // Use provided onSubmit handler
        if (isEdit) {
          const { mrn: _mrn, ...updateData } = formData;
          await onSubmit(updateData);
        } else {
          await onSubmit(formData);
        }
      } else {
        // Use built-in mutations
        if (isEdit && patient) {
          const { mrn: _mrn, ...updateData } = formData;
          await updateMutation.mutateAsync({ id: patient.id, data: updateData });
          toast.success(t('patients.updateSuccess', 'Paciente actualizado'));
        } else {
          await createMutation.mutateAsync(formData);
          toast.success(t('patients.createSuccess', 'Paciente creado'));
        }
      }
      onSuccess?.();
    } catch (error) {
      toast.error(t('errors.generic', 'Error al guardar'));
      console.error('Form submission error:', error);
    }
  };

  const genderOptions: { value: Gender; label: string }[] = [
    { value: 'male', label: t('patients.gender.male', 'Masculino') },
    { value: 'female', label: t('patients.gender.female', 'Femenino') },
    { value: 'other', label: t('patients.gender.other', 'Otro') },
    { value: 'unknown', label: t('patients.gender.unknown', 'Desconocido') },
  ];

  const inputClass = (field: string) =>
    `w-full px-3 py-2 bg-white/60 dark:bg-gray-800/60 border ${
      errors[field]
        ? 'border-red-500 focus:ring-red-500'
        : 'border-gray-200/50 dark:border-gray-700/50 focus:ring-primary-500'
    } rounded-lg focus:ring-2 focus:border-transparent transition-all text-sm`;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
    >
      <motion.div
        initial={{ y: 20 }}
        animate={{ y: 0 }}
        className="w-full max-w-4xl max-h-[90vh] bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-primary-500 to-accent-500 rounded-lg">
              <User className="w-5 h-5 text-white" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              {isEdit
                ? t('patients.form.editTitle', 'Editar Paciente')
                : t('patients.form.createTitle', 'Nuevo Paciente')}
            </h2>
          </div>
          <button
            onClick={onCancel}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="p-6 overflow-y-auto max-h-[calc(90vh-180px)]"
        >
          <div className="space-y-8">
            {/* Basic Info Section */}
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold mb-4 text-gray-900 dark:text-white">
                <User className="w-5 h-5 text-primary-500" />
                {t('patients.form.sections.basicInfo', 'Información Básica')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.mrn', 'MRN')} *
                  </label>
                  <input
                    type="text"
                    name="mrn"
                    value={formData.mrn}
                    onChange={handleChange}
                    disabled={isEdit}
                    className={inputClass('mrn')}
                    placeholder="MRN-2025-001"
                  />
                  {errors.mrn && (
                    <p className="text-red-500 text-xs mt-1">{errors.mrn}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.givenName', 'Nombre')} *
                  </label>
                  <input
                    type="text"
                    name="given_name"
                    value={formData.given_name}
                    onChange={handleChange}
                    className={inputClass('given_name')}
                  />
                  {errors.given_name && (
                    <p className="text-red-500 text-xs mt-1">{errors.given_name}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.middleName', 'Segundo Nombre')}
                  </label>
                  <input
                    type="text"
                    name="middle_name"
                    value={formData.middle_name}
                    onChange={handleChange}
                    className={inputClass('middle_name')}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.familyName', 'Apellido')} *
                  </label>
                  <input
                    type="text"
                    name="family_name"
                    value={formData.family_name}
                    onChange={handleChange}
                    className={inputClass('family_name')}
                  />
                  {errors.family_name && (
                    <p className="text-red-500 text-xs mt-1">{errors.family_name}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.birthDate', 'Fecha de Nacimiento')} *
                  </label>
                  <input
                    type="date"
                    name="birth_date"
                    value={formData.birth_date}
                    onChange={handleChange}
                    className={inputClass('birth_date')}
                  />
                  {errors.birth_date && (
                    <p className="text-red-500 text-xs mt-1">{errors.birth_date}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.gender', 'Género')} *
                  </label>
                  <select
                    name="gender"
                    value={formData.gender}
                    onChange={handleChange}
                    className={inputClass('gender')}
                  >
                    {genderOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </section>

            {/* Contact Section */}
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold mb-4 text-gray-900 dark:text-white">
                <Phone className="w-5 h-5 text-primary-500" />
                {t('patients.form.sections.contact', 'Contacto')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.phoneMobile', 'Teléfono Móvil')} *
                  </label>
                  <input
                    type="tel"
                    name="phone_mobile"
                    value={formData.phone_mobile}
                    onChange={handleChange}
                    className={inputClass('phone_mobile')}
                    placeholder="+57 300 123 4567"
                  />
                  {errors.phone_mobile && (
                    <p className="text-red-500 text-xs mt-1">{errors.phone_mobile}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.phoneHome', 'Teléfono Casa')}
                  </label>
                  <input
                    type="tel"
                    name="phone_home"
                    value={formData.phone_home}
                    onChange={handleChange}
                    className={inputClass('phone_home')}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    <Mail className="w-4 h-4 inline mr-1" />
                    {t('patients.form.email', 'Email')}
                  </label>
                  <input
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    className={inputClass('email')}
                  />
                </div>
              </div>
            </section>

            {/* Address Section */}
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold mb-4 text-gray-900 dark:text-white">
                <MapPin className="w-5 h-5 text-primary-500" />
                {t('patients.form.sections.address', 'Dirección')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.addressLine1', 'Dirección')}
                  </label>
                  <input
                    type="text"
                    name="address_line1"
                    value={formData.address_line1}
                    onChange={handleChange}
                    className={inputClass('address_line1')}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.city', 'Ciudad')}
                  </label>
                  <input
                    type="text"
                    name="city"
                    value={formData.city}
                    onChange={handleChange}
                    className={inputClass('city')}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.state', 'Departamento')}
                  </label>
                  <input
                    type="text"
                    name="state"
                    value={formData.state}
                    onChange={handleChange}
                    className={inputClass('state')}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.postalCode', 'Código Postal')}
                  </label>
                  <input
                    type="text"
                    name="postal_code"
                    value={formData.postal_code}
                    onChange={handleChange}
                    className={inputClass('postal_code')}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.country', 'País')}
                  </label>
                  <input
                    type="text"
                    name="country"
                    value={formData.country}
                    onChange={handleChange}
                    className={inputClass('country')}
                    placeholder="COL"
                  />
                </div>
              </div>
            </section>

            {/* Emergency Contact Section */}
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold mb-4 text-gray-900 dark:text-white">
                <Heart className="w-5 h-5 text-red-500" />
                {t('patients.form.sections.emergency', 'Contacto de Emergencia')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.emergencyName', 'Nombre')}
                  </label>
                  <input
                    type="text"
                    name="emergency_contact_name"
                    value={formData.emergency_contact_name}
                    onChange={handleChange}
                    className={inputClass('emergency_contact_name')}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.emergencyPhone', 'Teléfono')}
                  </label>
                  <input
                    type="tel"
                    name="emergency_contact_phone"
                    value={formData.emergency_contact_phone}
                    onChange={handleChange}
                    className={inputClass('emergency_contact_phone')}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.emergencyRelationship', 'Parentesco')}
                  </label>
                  <input
                    type="text"
                    name="emergency_contact_relationship"
                    value={formData.emergency_contact_relationship}
                    onChange={handleChange}
                    className={inputClass('emergency_contact_relationship')}
                    placeholder={t('patients.form.relationshipPlaceholder', 'Ej: Esposa, Hijo')}
                  />
                </div>
              </div>
            </section>

            {/* Insurance Section */}
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold mb-4 text-gray-900 dark:text-white">
                <Shield className="w-5 h-5 text-primary-500" />
                {t('patients.form.sections.insurance', 'Seguro Médico')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.insuranceProvider', 'Aseguradora')}
                  </label>
                  <input
                    type="text"
                    name="insurance_provider"
                    value={formData.insurance_provider}
                    onChange={handleChange}
                    className={inputClass('insurance_provider')}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    {t('patients.form.insurancePolicyNumber', 'Número de Póliza')}
                  </label>
                  <input
                    type="text"
                    name="insurance_policy_number"
                    value={formData.insurance_policy_number}
                    onChange={handleChange}
                    className={inputClass('insurance_policy_number')}
                  />
                </div>
              </div>
            </section>
          </div>
        </form>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            {t('common.cancel', 'Cancelar')}
          </button>
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="flex items-center gap-2 px-6 py-2 bg-gradient-to-r from-primary-500 to-accent-500 text-white rounded-lg hover:from-primary-600 hover:to-accent-600 transition-all disabled:opacity-50"
          >
            {isLoading ? (
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full"
              />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {isEdit
              ? t('common.save', 'Guardar')
              : t('common.create', 'Crear')}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
