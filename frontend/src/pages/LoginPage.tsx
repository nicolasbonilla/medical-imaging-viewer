import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Lock, Mail, User, Eye, EyeOff, Shield, RefreshCw,
  CheckCircle2, AlertCircle, Sparkles, KeyRound
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';
import { useAuth } from '../contexts/AuthContext';
import LanguageSelector from '../components/LanguageSelector';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

interface LoginForm {
  username: string;
  password: string;
  captcha_response?: string;
}

interface RegisterForm {
  username: string;
  email: string;
  full_name: string;
  password: string;
  confirm_password: string;
}

interface CaptchaData {
  challenge_id: string;
  challenge_text: string;
  expires_in_seconds: number;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, register, isAuthenticated } = useAuth();
  const { t } = useTranslation();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [requiresCaptcha, setRequiresCaptcha] = useState(false);
  const [captchaData, setCaptchaData] = useState<CaptchaData | null>(null);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/app', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const [loginForm, setLoginForm] = useState<LoginForm>({
    username: '',
    password: '',
    captcha_response: ''
  });

  const [registerForm, setRegisterForm] = useState<RegisterForm>({
    username: '',
    email: '',
    full_name: '',
    password: '',
    confirm_password: ''
  });

  const [passwordStrength, setPasswordStrength] = useState({
    score: 0,
    feedback: [] as string[]
  });

  // Generate CAPTCHA
  const generateCaptcha = async () => {
    try {
      const response = await axios.post(`${API_URL}/auth/captcha`, {
        difficulty: 'medium'
      });
      setCaptchaData(response.data);
      setRequiresCaptcha(true);
    } catch (error) {
      toast.error('Failed to generate CAPTCHA');
      console.error(error);
    }
  };

  // Password strength calculator
  useEffect(() => {
    const password = mode === 'register' ? registerForm.password : '';
    if (!password) {
      setPasswordStrength({ score: 0, feedback: [] });
      return;
    }

    let score = 0;
    const feedback: string[] = [];

    if (password.length >= 12) {
      score += 2;
      feedback.push('Good length');
    } else if (password.length >= 8) {
      score += 1;
      feedback.push('Consider longer password');
    }

    if (/[A-Z]/.test(password)) score += 1;
    if (/[a-z]/.test(password)) score += 1;
    if (/[0-9]/.test(password)) score += 1;
    if (/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password)) score += 1;

    const diversity = [
      /[A-Z]/.test(password),
      /[a-z]/.test(password),
      /[0-9]/.test(password),
      /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password)
    ].filter(Boolean).length;

    if (diversity === 4) {
      feedback.push('Excellent diversity');
    } else if (diversity >= 3) {
      feedback.push('Good diversity');
    }

    setPasswordStrength({ score, feedback });
  }, [registerForm.password, mode]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await login(
        loginForm.username,
        loginForm.password,
        requiresCaptcha && captchaData ? captchaData.challenge_id : undefined,
        requiresCaptcha ? loginForm.captcha_response : undefined
      );

      toast.success(t('auth.welcomeBack'));
      navigate('/app', { replace: true });

    } catch (error: any) {
      console.error('Login error:', error);

      if (error.response?.status === 400 && error.response.headers['x-captcha-required']) {
        await generateCaptcha();
        toast.warning(t('auth.captchaRequired'));
      } else if (error.response?.data?.detail) {
        toast.error(error.response.data.detail);
      } else {
        toast.error(t('auth.loginFailed'));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();

    if (registerForm.password !== registerForm.confirm_password) {
      toast.error(t('auth.passwordsDoNotMatch'));
      return;
    }

    if (passwordStrength.score < 4) {
      toast.error(t('auth.passwordTooWeak'));
      return;
    }

    setLoading(true);

    try {
      await register({
        username: registerForm.username,
        email: registerForm.email,
        password: registerForm.password,
        full_name: registerForm.full_name,
      });

      toast.success(t('auth.registrationSuccess'));
      navigate('/app', { replace: true });

    } catch (error: any) {
      console.error('Registration error:', error);

      if (error.response?.data?.detail) {
        toast.error(error.response.data.detail);
      } else {
        toast.error(t('auth.registrationFailed'));
      }
    } finally {
      setLoading(false);
    }
  };

  const getPasswordStrengthColor = () => {
    if (passwordStrength.score >= 6) return 'from-green-500 to-emerald-500';
    if (passwordStrength.score >= 4) return 'from-yellow-500 to-orange-500';
    return 'from-red-500 to-pink-500';
  };

  const getPasswordStrengthLabel = () => {
    if (passwordStrength.score >= 6) return t('auth.passwordStrong');
    if (passwordStrength.score >= 4) return t('auth.passwordModerate');
    return t('auth.passwordWeak');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-blue-950 to-purple-950 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Language Selector - Top Right */}
      <div className="absolute top-6 right-6 z-50">
        <LanguageSelector variant="minimal" />
      </div>

      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <motion.div
          className="absolute top-1/4 -left-20 w-96 h-96 bg-blue-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20"
          animate={{
            x: [0, 100, 0],
            y: [0, -50, 0],
          }}
          transition={{
            duration: 20,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
        <motion.div
          className="absolute bottom-1/4 -right-20 w-96 h-96 bg-purple-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20"
          animate={{
            x: [0, -100, 0],
            y: [0, 50, 0],
          }}
          transition={{
            duration: 15,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
      </div>

      {/* Main card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md relative z-10"
      >
        {/* Glassmorphism card */}
        <div className="backdrop-blur-2xl bg-white/10 border border-white/20 rounded-3xl shadow-2xl p-8">
          {/* Logo and title */}
          <div className="text-center mb-8">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 200, damping: 15 }}
              className="inline-block p-4 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl mb-4"
            >
              <Shield className="w-12 h-12 text-white" />
            </motion.div>
            <h1 className="text-3xl font-bold text-white mb-2">
              {t('auth.welcomeTitle')}
            </h1>
            <p className="text-gray-300 text-sm">
              {mode === 'login' ? t('auth.loginTitle') : t('auth.registerTitle')}
            </p>
          </div>

          {/* Mode toggle */}
          <div className="flex gap-2 mb-6 p-1 bg-white/5 rounded-xl">
            <button
              onClick={() => setMode('login')}
              className={`flex-1 py-2 px-4 rounded-lg font-medium transition-all ${
                mode === 'login'
                  ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {t('auth.login')}
            </button>
            <button
              onClick={() => setMode('register')}
              className={`flex-1 py-2 px-4 rounded-lg font-medium transition-all ${
                mode === 'register'
                  ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {t('auth.register')}
            </button>
          </div>

          <AnimatePresence mode="wait">
            {mode === 'login' ? (
              <motion.form
                key="login"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.3 }}
                onSubmit={handleLogin}
                className="space-y-4"
              >
                {/* Username */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    {t('auth.username')}
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                    <input
                      type="text"
                      value={loginForm.username}
                      onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
                      className="w-full pl-10 pr-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all"
                      placeholder="{t('auth.username')}"
                      required
                    />
                  </div>
                </div>

                {/* Password */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={loginForm.password}
                      onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                      className="w-full pl-10 pr-12 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all"
                      placeholder="Enter your password"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                    >
                      {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>

                {/* CAPTCHA */}
                {requiresCaptcha && captchaData && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className="space-y-2"
                  >
                    <label className="block text-sm font-medium text-gray-300 mb-2">
                      <div className="flex items-center gap-2">
                        <KeyRound className="w-4 h-4" />
                        {t('auth.captchaTitle')}
                      </div>
                    </label>
                    <div className="bg-gradient-to-r from-blue-600/20 to-purple-600/20 border border-blue-500/30 rounded-xl p-4">
                      <p className="text-xs text-gray-400 mb-2">{t('auth.captchaPlaceholder')}</p>
                      <p className="text-3xl font-mono font-bold text-white text-center tracking-widest mb-3">
                        {captchaData.challenge_text}
                      </p>
                      <input
                        type="text"
                        value={loginForm.captcha_response}
                        onChange={(e) => setLoginForm({ ...loginForm, captcha_response: e.target.value })}
                        className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 text-center text-2xl font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                        placeholder="• • • • • •"
                        maxLength={10}
                        required
                      />
                      <button
                        type="button"
                        onClick={generateCaptcha}
                        className="mt-2 w-full flex items-center justify-center gap-2 text-xs text-gray-400 hover:text-white transition-colors"
                      >
                        <RefreshCw className="w-3 h-3" />
                        {t('auth.captchaRefresh')}
                      </button>
                    </div>
                  </motion.div>
                )}

                {/* Login button */}
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-3 px-4 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white font-medium rounded-xl shadow-lg hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <RefreshCw className="w-5 h-5 animate-spin" />
                      Logging in...
                    </>
                  ) : (
                    <>
                      <Shield className="w-5 h-5" />
                      Login
                    </>
                  )}
                </button>
              </motion.form>
            ) : (
              <motion.form
                key="register"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
                onSubmit={handleRegister}
                className="space-y-4"
              >
                {/* {t('auth.fullName')} */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    {t('auth.fullName')}
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                    <input
                      type="text"
                      value={registerForm.full_name}
                      onChange={(e) => setRegisterForm({ ...registerForm, full_name: e.target.value })}
                      className="w-full pl-10 pr-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all"
                      placeholder="Dr. John Doe"
                      required
                    />
                  </div>
                </div>

                {/* Username */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Username
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                    <input
                      type="text"
                      value={registerForm.username}
                      onChange={(e) => setRegisterForm({ ...registerForm, username: e.target.value })}
                      className="w-full pl-10 pr-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all"
                      placeholder="john_doe"
                      pattern="[a-zA-Z0-9_-]+"
                      title="Only letters, numbers, underscores, and hyphens allowed"
                      required
                    />
                  </div>
                </div>

                {/* Email */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Email
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                    <input
                      type="email"
                      value={registerForm.email}
                      onChange={(e) => setRegisterForm({ ...registerForm, email: e.target.value })}
                      className="w-full pl-10 pr-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all"
                      placeholder="john@hospital.com"
                      required
                    />
                  </div>
                </div>

                {/* Password */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={registerForm.password}
                      onChange={(e) => setRegisterForm({ ...registerForm, password: e.target.value })}
                      className="w-full pl-10 pr-12 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all"
                      placeholder="Create a strong password"
                      minLength={12}
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                    >
                      {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>

                  {/* Password strength indicator */}
                  {registerForm.password && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="mt-2"
                    >
                      <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                        <span>{t('auth.passwordStrength')}</span>
                        <span className="font-medium">{getPasswordStrengthLabel()}</span>
                      </div>
                      <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                        <motion.div
                          className={`h-full bg-gradient-to-r ${getPasswordStrengthColor()}`}
                          initial={{ width: 0 }}
                          animate={{ width: `${(passwordStrength.score / 8) * 100}%` }}
                          transition={{ duration: 0.3 }}
                        />
                      </div>
                      {passwordStrength.feedback.length > 0 && (
                        <div className="mt-1 flex items-center gap-1 text-xs text-gray-400">
                          <Sparkles className="w-3 h-3" />
                          {passwordStrength.feedback.join(', ')}
                        </div>
                      )}
                    </motion.div>
                  )}
                </div>

                {/* {t('auth.confirmPassword')} */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    {t('auth.confirmPassword')}
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                    <input
                      type={showConfirmPassword ? 'text' : 'password'}
                      value={registerForm.confirm_password}
                      onChange={(e) => setRegisterForm({ ...registerForm, confirm_password: e.target.value })}
                      className="w-full pl-10 pr-12 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all"
                      placeholder="Confirm your password"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                    >
                      {showConfirmPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  {registerForm.confirm_password && registerForm.password !== registerForm.confirm_password && (
                    <div className="mt-1 flex items-center gap-1 text-xs text-red-400">
                      <AlertCircle className="w-3 h-3" />
                      Passwords do not match
                    </div>
                  )}
                  {registerForm.confirm_password && registerForm.password === registerForm.confirm_password && (
                    <div className="mt-1 flex items-center gap-1 text-xs text-green-400">
                      <CheckCircle2 className="w-3 h-3" />
                      Passwords match
                    </div>
                  )}
                </div>

                {/* Register button */}
                <button
                  type="submit"
                  disabled={loading || registerForm.password !== registerForm.confirm_password}
                  className="w-full py-3 px-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-medium rounded-xl shadow-lg hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <RefreshCw className="w-5 h-5 animate-spin" />
                      Creating account...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-5 h-5" />
                      {t('auth.registerButton')}
                    </>
                  )}
                </button>
              </motion.form>
            )}
          </AnimatePresence>

          {/* Security badge */}
          <div className="mt-6 pt-6 border-t border-white/10">
            <div className="flex items-center justify-center gap-2 text-xs text-gray-400">
              <Shield className="w-4 h-4 text-green-500" />
              <span>{t('auth.securityBadges.iso27001')} • {t('auth.securityBadges.hipaa')} • {t('auth.securityBadges.encrypted')}</span>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
