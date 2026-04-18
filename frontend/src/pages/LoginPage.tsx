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

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const API_URL = BASE_URL + '/api/v1';

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

/* ─── Social Login SVG icons (inline to avoid external deps) ─── */
const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
  </svg>
);

const AppleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>
  </svg>
);

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, loginWithPasskey, register, isAuthenticated } = useAuth();
  const { t } = useTranslation();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [requiresCaptcha, setRequiresCaptcha] = useState(false);
  const [captchaData, setCaptchaData] = useState<CaptchaData | null>(null);

  useEffect(() => {
    if (isAuthenticated) navigate('/app', { replace: true });
  }, [isAuthenticated, navigate]);

  const [loginForm, setLoginForm] = useState<LoginForm>({ username: '', password: '', captcha_response: '' });
  const [registerForm, setRegisterForm] = useState<RegisterForm>({ username: '', email: '', full_name: '', password: '', confirm_password: '' });
  const [passwordStrength, setPasswordStrength] = useState({ score: 0, feedback: [] as string[] });

  const generateCaptcha = async () => {
    try {
      const response = await axios.post(`${API_URL}/auth/captcha`, { difficulty: 'medium' });
      setCaptchaData(response.data);
      setRequiresCaptcha(true);
    } catch {
      toast.error(t('auth.captchaGenerationFailed', 'Failed to generate CAPTCHA'));
    }
  };

  useEffect(() => {
    const password = mode === 'register' ? registerForm.password : '';
    if (!password) { setPasswordStrength({ score: 0, feedback: [] }); return; }
    let score = 0;
    const feedback: string[] = [];
    if (password.length >= 12) { score += 2; feedback.push(t('auth.passwordRequirements.goodLength', 'Good length')); }
    else if (password.length >= 8) { score += 1; feedback.push(t('auth.passwordRequirements.considerLonger', 'Consider longer password')); }
    if (/[A-Z]/.test(password)) score += 1;
    if (/[a-z]/.test(password)) score += 1;
    if (/[0-9]/.test(password)) score += 1;
    if (/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password)) score += 1;
    const diversity = [/[A-Z]/, /[a-z]/, /[0-9]/, /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/].filter(r => r.test(password)).length;
    if (diversity === 4) feedback.push(t('auth.passwordRequirements.excellentDiversity', 'Excellent diversity'));
    else if (diversity >= 3) feedback.push(t('auth.passwordRequirements.goodDiversity', 'Good diversity'));
    setPasswordStrength({ score, feedback });
  }, [registerForm.password, mode, t]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(loginForm.username, loginForm.password,
        requiresCaptcha && captchaData ? captchaData.challenge_id : undefined,
        requiresCaptcha ? loginForm.captcha_response : undefined);
      localStorage.setItem('last_username', loginForm.username);
      toast.success(t('auth.welcomeBack'));
      navigate('/app', { replace: true });
    } catch (error: any) {
      const errMsg = error.response?.data?.detail || error.response?.data?.error?.message || '';
      if (error.response?.status === 400 && errMsg.toLowerCase().includes('captcha')) {
        setRequiresCaptcha(true); await generateCaptcha();
        toast.warning(t('auth.captchaRequired', 'CAPTCHA required'));
      } else if (errMsg) toast.error(errMsg);
      else toast.error(t('auth.loginFailed'));
    } finally { setLoading(false); }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (registerForm.password !== registerForm.confirm_password) { toast.error(t('auth.passwordsDoNotMatch')); return; }
    if (passwordStrength.score < 4) { toast.error(t('auth.passwordTooWeak')); return; }
    setLoading(true);
    try {
      await register({ username: registerForm.username, email: registerForm.email, password: registerForm.password, full_name: registerForm.full_name });
      toast.success(t('auth.registrationSuccess'));
      navigate('/app', { replace: true });
    } catch (error: any) {
      toast.error(error.response?.data?.detail || t('auth.registrationFailed'));
    } finally { setLoading(false); }
  };

  const handleSocialLogin = async (provider: 'google' | 'apple') => {
    toast.info(`${provider === 'google' ? 'Google' : 'Apple'} Sign-In coming soon — contact admin for early access`);
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
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden bg-gradient-to-br from-gray-900 via-slate-900 to-gray-950">
      {/* Subtle animated background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <motion.div className="absolute top-1/4 -left-20 w-96 h-96 bg-blue-500 rounded-full mix-blend-multiply filter blur-3xl opacity-10"
          animate={{ x: [0, 100, 0], y: [0, -50, 0] }} transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }} />
        <motion.div className="absolute bottom-1/4 -right-20 w-96 h-96 bg-purple-500 rounded-full mix-blend-multiply filter blur-3xl opacity-10"
          animate={{ x: [0, -100, 0], y: [0, 50, 0] }} transition={{ duration: 15, repeat: Infinity, ease: "easeInOut" }} />
      </div>

      {/* Language Selector */}
      <div className="absolute top-6 right-6 z-50">
        <LanguageSelector variant="minimal" />
      </div>

      {/* Main card */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
        className="w-full max-w-md relative z-10">
        <div className="backdrop-blur-2xl bg-white/[0.07] border border-white/[0.12] rounded-3xl shadow-2xl p-8">

          {/* Logo */}
          <div className="text-center mb-6">
            <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 200, damping: 15 }}
              className="inline-block p-3.5 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl mb-3">
              <Shield className="w-10 h-10 text-white" />
            </motion.div>
            <h1 className="text-2xl font-bold text-white mb-1">MSTool-AI</h1>
            <p className="text-gray-400 text-xs">
              AI-Powered Brain MRI Analysis · IEC 62304 Class C Medical Device
            </p>
          </div>

          {/* Mode toggle */}
          <div className="flex gap-2 mb-5 p-1 bg-white/5 rounded-xl">
            <button onClick={() => setMode('login')}
              className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-all ${mode === 'login' ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'}`}>
              {t('auth.login')}
            </button>
            <button onClick={() => setMode('register')}
              className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-all ${mode === 'register' ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'}`}>
              {t('auth.register')}
            </button>
          </div>

          <AnimatePresence mode="wait">
            {mode === 'login' ? (
              <motion.form key="login" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.3 }} onSubmit={handleLogin} className="space-y-4">

                {/* Username */}
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">{t('auth.username')}</label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input type="text" autoComplete="username" value={loginForm.username}
                      onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
                      className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all"
                      placeholder={t('auth.usernamePlaceholder')} required />
                  </div>
                </div>

                {/* Password */}
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">{t('auth.password')}</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input type={showPassword ? 'text' : 'password'} autoComplete="current-password"
                      value={loginForm.password}
                      onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                      className="w-full pl-10 pr-12 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all"
                      placeholder={t('auth.passwordPlaceholder')} required />
                    <button type="button" onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white transition-colors">
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* CAPTCHA */}
                {requiresCaptcha && captchaData && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="space-y-2">
                    <label className="flex items-center gap-2 text-xs font-medium text-gray-400"><KeyRound className="w-3 h-3" />{t('auth.captchaTitle')}</label>
                    <div className="bg-gradient-to-r from-blue-600/20 to-purple-600/20 border border-blue-500/30 rounded-xl p-3">
                      <p className="text-2xl font-mono font-bold text-white text-center tracking-widest mb-2">{captchaData.challenge_text}</p>
                      <input type="text" autoComplete="off" value={loginForm.captcha_response}
                        onChange={(e) => setLoginForm({ ...loginForm, captcha_response: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-center text-lg font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                        placeholder="• • • • • •" maxLength={10} required />
                      <button type="button" onClick={generateCaptcha}
                        className="mt-1.5 w-full flex items-center justify-center gap-1 text-xs text-gray-500 hover:text-white transition-colors">
                        <RefreshCw className="w-3 h-3" />{t('auth.captchaRefresh')}
                      </button>
                    </div>
                  </motion.div>
                )}

                {/* Login button */}
                <button type="submit" disabled={loading}
                  className="w-full py-2.5 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white text-sm font-medium rounded-xl shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2">
                  {loading ? <><RefreshCw className="w-4 h-4 animate-spin" />{t('auth.loggingIn')}</> : <><Shield className="w-4 h-4" />{t('auth.loginButton')}</>}
                </button>

                {/* Divider */}
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-px bg-white/10" />
                  <span className="text-[10px] text-gray-500 uppercase tracking-wider">or continue with</span>
                  <div className="flex-1 h-px bg-white/10" />
                </div>

                {/* Social login + Passkey */}
                <div className="space-y-2">
                  {/* Google */}
                  <button type="button" onClick={() => handleSocialLogin('google')}
                    className="w-full py-2.5 bg-white/[0.06] hover:bg-white/[0.10] border border-white/[0.12] rounded-xl text-white text-sm font-medium flex items-center justify-center gap-2.5 transition-all">
                    <GoogleIcon /> Continue with Google
                  </button>

                  {/* Apple */}
                  <button type="button" onClick={() => handleSocialLogin('apple')}
                    className="w-full py-2.5 bg-white/[0.06] hover:bg-white/[0.10] border border-white/[0.12] rounded-xl text-white text-sm font-medium flex items-center justify-center gap-2.5 transition-all">
                    <AppleIcon /> Continue with Apple
                  </button>

                  {/* Passkey */}
                  {window.PublicKeyCredential && (
                    <button type="button" disabled={loading}
                      onClick={async () => {
                        const username = loginForm.username || localStorage.getItem('last_username') || '';
                        if (!username) { toast.error('Enter your username first'); return; }
                        setLoading(true);
                        try {
                          await loginWithPasskey(username);
                          localStorage.setItem('last_username', username);
                          toast.success(t('auth.welcomeBack'));
                          navigate('/app', { replace: true });
                        } catch (err: any) {
                          toast.error(err?.response?.data?.detail || err?.message || 'Passkey authentication failed');
                        } finally { setLoading(false); }
                      }}
                      className="w-full py-2.5 bg-white/[0.06] hover:bg-white/[0.10] border border-white/[0.12] rounded-xl text-white text-sm font-medium flex items-center justify-center gap-2.5 transition-all">
                      <KeyRound className="w-4 h-4" /> Sign in with Passkey
                    </button>
                  )}
                </div>
              </motion.form>
            ) : (
              <motion.form key="register" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }} onSubmit={handleRegister} className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">{t('auth.fullName')}</label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input type="text" autoComplete="name" value={registerForm.full_name}
                      onChange={(e) => setRegisterForm({ ...registerForm, full_name: e.target.value })}
                      className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition-all"
                      placeholder={t('auth.fullNamePlaceholder')} required />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">{t('auth.username')}</label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input type="text" autoComplete="username" value={registerForm.username}
                      onChange={(e) => setRegisterForm({ ...registerForm, username: e.target.value })}
                      className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition-all"
                      placeholder={t('auth.usernameRegisterPlaceholder')} pattern="[a-zA-Z0-9_-]+" required />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">{t('auth.email')}</label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input type="email" autoComplete="email" value={registerForm.email}
                      onChange={(e) => setRegisterForm({ ...registerForm, email: e.target.value })}
                      className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition-all"
                      placeholder={t('auth.emailPlaceholder')} required />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">{t('auth.password')}</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input type={showPassword ? 'text' : 'password'} autoComplete="new-password"
                      value={registerForm.password}
                      onChange={(e) => setRegisterForm({ ...registerForm, password: e.target.value })}
                      className="w-full pl-10 pr-12 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition-all"
                      placeholder={t('auth.createPasswordPlaceholder')} minLength={12} required />
                    <button type="button" onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white transition-colors">
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  {registerForm.password && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-1.5">
                      <div className="flex items-center justify-between text-[10px] text-gray-500 mb-0.5">
                        <span>{t('auth.passwordStrength')}</span><span className="font-medium">{getPasswordStrengthLabel()}</span>
                      </div>
                      <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                        <motion.div className={`h-full bg-gradient-to-r ${getPasswordStrengthColor()}`} initial={{ width: 0 }} animate={{ width: `${(passwordStrength.score / 8) * 100}%` }} />
                      </div>
                    </motion.div>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">{t('auth.confirmPassword')}</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input type={showConfirmPassword ? 'text' : 'password'} autoComplete="new-password"
                      value={registerForm.confirm_password}
                      onChange={(e) => setRegisterForm({ ...registerForm, confirm_password: e.target.value })}
                      className="w-full pl-10 pr-12 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition-all"
                      placeholder={t('auth.confirmPasswordPlaceholder')} required />
                    <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white transition-colors">
                      {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  {registerForm.confirm_password && registerForm.password !== registerForm.confirm_password && (
                    <div className="mt-1 flex items-center gap-1 text-[10px] text-red-400"><AlertCircle className="w-3 h-3" />{t('auth.passwordsDoNotMatch')}</div>
                  )}
                  {registerForm.confirm_password && registerForm.password === registerForm.confirm_password && (
                    <div className="mt-1 flex items-center gap-1 text-[10px] text-green-400"><CheckCircle2 className="w-3 h-3" />{t('auth.passwordsMatch')}</div>
                  )}
                </div>
                <button type="submit" disabled={loading || registerForm.password !== registerForm.confirm_password}
                  className="w-full py-2.5 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white text-sm font-medium rounded-xl shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2">
                  {loading ? <><RefreshCw className="w-4 h-4 animate-spin" />{t('auth.creatingAccount')}</> : <><Sparkles className="w-4 h-4" />{t('auth.registerButton')}</>}
                </button>
              </motion.form>
            )}
          </AnimatePresence>

          {/* Security badges — research-backed per HIPAA 2026 + IEC 62304 + ISO 27001 */}
          <div className="mt-6 pt-5 border-t border-white/[0.08]">
            <div className="flex items-center justify-center gap-1.5 flex-wrap">
              {[
                { label: 'IEC 62304', sub: 'Class C' },
                { label: 'HIPAA', sub: '2026' },
                { label: 'ISO 27001', sub: '2022' },
                { label: 'AES-256', sub: 'Encrypted' },
                { label: 'TLS 1.3', sub: 'Transport' },
              ].map(b => (
                <span key={b.label} className="inline-flex flex-col items-center px-2 py-1 rounded-lg bg-white/[0.04] border border-white/[0.06]">
                  <span className="text-[9px] font-bold text-gray-300 leading-none">{b.label}</span>
                  <span className="text-[7px] text-gray-500 leading-none mt-0.5">{b.sub}</span>
                </span>
              ))}
            </div>
            <div className="flex items-center justify-center gap-3 mt-3 text-[9px] text-gray-500">
              <a href="#" className="hover:text-gray-300 transition-colors">Privacy Policy</a>
              <span>·</span>
              <a href="#" className="hover:text-gray-300 transition-colors">Terms of Service</a>
              <span>·</span>
              <a href="#" className="hover:text-gray-300 transition-colors">Cookie Policy</a>
            </div>
            <p className="text-center text-[8px] text-gray-600 mt-2">
              MFA enforced · NIST SP 800-63B AAL2 · Data never leaves your jurisdiction
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
