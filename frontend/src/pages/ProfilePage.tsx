import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { ArrowLeft, User, Mail, Shield, Clock, Calendar, KeyRound, Plus, Trash2, Loader2, Fingerprint } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import axios from 'axios';
import { useAuth } from '@/contexts/AuthContext';
import { isWebAuthnSupported, prepareRegistrationOptions, serializeRegistrationCredential } from '@/utils/webauthn';
import ThemeToggle from '@/components/ThemeToggle';
import LanguageSelector from '@/components/LanguageSelector';
import UserMenu from '@/components/UserMenu';

export default function ProfilePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();

  if (!user) return null;

  const initials = user.full_name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '\u2014';
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
      });
    } catch { return dateStr; }
  };

  const roleColors: Record<string, string> = {
    ADMIN: 'bg-red-500/20 text-red-400 border-red-500/30',
    RADIOLOGIST: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    TECHNICIAN: 'bg-green-500/20 text-green-400 border-green-500/30',
    VIEWER: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950">
      {/* Header */}
      <motion.header
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="sticky top-0 z-30 backdrop-blur-xl bg-white/5 border-b border-white/10"
      >
        <div className="max-w-5xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(-1)}
              className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="text-lg font-semibold text-white">{t('auth.profile', 'My Profile')}</h1>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle variant="minimal" />
            <LanguageSelector variant="minimal" />
            <UserMenu />
          </div>
        </div>
      </motion.header>

      {/* Content */}
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Profile Card */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="lg:col-span-1"
          >
            <div className="bg-white/5 border border-white/10 rounded-2xl p-6 text-center">
              <div className="w-24 h-24 mx-auto bg-gradient-to-br from-primary-500 to-accent-500 rounded-2xl flex items-center justify-center text-white font-bold text-3xl shadow-xl shadow-primary-500/20">
                {initials}
              </div>
              <h2 className="mt-4 text-xl font-bold text-white">{user.full_name}</h2>
              <p className="text-sm text-gray-400">@{user.username}</p>
              <div className="mt-3">
                <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${roleColors[user.role] || roleColors.VIEWER}`}>
                  <Shield className="w-3 h-3" />
                  {user.role}
                </span>
              </div>
              <div className="mt-4 flex items-center justify-center gap-2">
                <span className={`w-2 h-2 rounded-full ${user.is_active ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-xs text-gray-400">
                  {user.is_active ? t('patients.status.active', 'Active') : 'Inactive'}
                </span>
              </div>
            </div>
          </motion.div>

          {/* Details */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="lg:col-span-2 space-y-6"
          >
            {/* Account Information */}
            <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
              <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
                Account Information
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <InfoField
                  icon={<User className="w-4 h-4" />}
                  label="Full Name"
                  value={user.full_name}
                />
                <InfoField
                  icon={<User className="w-4 h-4" />}
                  label="Username"
                  value={user.username}
                />
                <InfoField
                  icon={<Mail className="w-4 h-4" />}
                  label="Email"
                  value={user.email}
                />
                <InfoField
                  icon={<Shield className="w-4 h-4" />}
                  label="Role"
                  value={user.role}
                />
              </div>
            </div>

            {/* Activity */}
            <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
              <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
                Activity
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <InfoField
                  icon={<Clock className="w-4 h-4" />}
                  label="Last Login"
                  value={formatDate(user.last_login)}
                />
                <InfoField
                  icon={<Calendar className="w-4 h-4" />}
                  label="Account Created"
                  value={formatDate(user.created_at)}
                />
                <InfoField
                  icon={<Calendar className="w-4 h-4" />}
                  label="Last Updated"
                  value={formatDate(user.updated_at)}
                />
                <InfoField
                  icon={<Shield className="w-4 h-4" />}
                  label="Failed Login Attempts"
                  value={String(user.failed_login_attempts)}
                />
              </div>
            </div>
            {/* Passkeys */}
            {isWebAuthnSupported() && (
              <PasskeySection userId={user.id} />
            )}
          </motion.div>
        </div>
      </div>
    </div>
  );
}

const API_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Separate axios instance for WebAuthn calls — avoids global 401 interceptor triggering logout
const webauthnClient = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

function PasskeySection({ userId }: { userId: string }) {
  const { t } = useTranslation();
  const [credentials, setCredentials] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [registering, setRegistering] = useState(false);

  const fetchCredentials = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      if (!token) return;
      const res = await webauthnClient.get(`/api/v1/auth/webauthn/credentials`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setCredentials(res.data);
    } catch {
      // Silently fail — don't trigger logout
    } finally {
      setLoading(false);
    }
  }, []);

  // Load credentials on mount
  useEffect(() => { fetchCredentials(); }, [fetchCredentials]);

  const handleRegister = async () => {
    setRegistering(true);
    try {
      const token = localStorage.getItem('access_token');
      if (!token) { toast.error('Not authenticated'); setRegistering(false); return; }
      const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

      // Step 1: Get registration options
      const beginRes = await webauthnClient.post(`/api/v1/auth/webauthn/register/begin`, {}, { headers });
      const options = prepareRegistrationOptions(beginRes.data.options);

      // Step 2: Browser prompt
      const credential = await navigator.credentials.create({ publicKey: options }) as PublicKeyCredential;
      if (!credential) throw new Error('Registration cancelled');

      // Step 3: Verify on server
      const deviceName = navigator.userAgent.includes('Windows') ? 'Windows Hello'
        : navigator.userAgent.includes('Mac') ? 'Touch ID'
        : navigator.userAgent.includes('iPhone') ? 'Face ID'
        : 'Passkey';

      await webauthnClient.post(`/api/v1/auth/webauthn/register/complete`, {
        credential: serializeRegistrationCredential(credential),
        device_name: deviceName,
      }, { headers });

      toast.success('Passkey registered successfully');
      fetchCredentials();
    } catch (err: any) {
      if (err.name !== 'NotAllowedError') {
        const msg = err?.response?.data?.detail || err?.response?.data?.error?.message || err?.message || String(err);
        console.error('Passkey register error:', msg, err);
        toast.error(`Passkey error: ${msg}`);
      }
    } finally {
      setRegistering(false);
    }
  };

  const handleDelete = async (credentialId: string) => {
    try {
      const token = localStorage.getItem('access_token');
      await webauthnClient.delete(`/api/v1/auth/webauthn/credentials/${credentialId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success('Passkey removed');
      fetchCredentials();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to remove');
    }
  };

  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
          <Fingerprint className="w-4 h-4" />
          Passkeys
        </h3>
        <button
          onClick={handleRegister}
          disabled={registering}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-primary-500/20 hover:bg-primary-500/30 text-primary-400 rounded-lg text-xs font-medium transition-colors"
        >
          {registering ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
          Add Passkey
        </button>
      </div>

      {credentials.length === 0 ? (
        <div className="text-center py-6">
          <KeyRound className="w-8 h-8 text-gray-600 mx-auto mb-2" />
          <p className="text-sm text-gray-500">No passkeys registered</p>
          <p className="text-xs text-gray-600 mt-1">Add a passkey for faster, passwordless login using Face ID, Windows Hello, or fingerprint.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {credentials.map((cred) => (
            <div key={cred.credential_id} className="flex items-center justify-between p-3 bg-white/5 rounded-xl">
              <div className="flex items-center gap-3">
                <KeyRound className="w-4 h-4 text-primary-400" />
                <div>
                  <p className="text-sm text-white font-medium">{cred.device_name || 'Passkey'}</p>
                  <p className="text-[10px] text-gray-500">
                    Created: {new Date(cred.created_at).toLocaleDateString()}
                    {cred.last_used && ` \u00b7 Last used: ${new Date(cred.last_used).toLocaleDateString()}`}
                  </p>
                </div>
              </div>
              <button
                onClick={() => handleDelete(cred.credential_id)}
                className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function InfoField({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 p-3 bg-white/5 rounded-xl">
      <div className="mt-0.5 text-gray-500">{icon}</div>
      <div>
        <p className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</p>
        <p className="text-sm text-white font-medium mt-0.5">{value}</p>
      </div>
    </div>
  );
}
