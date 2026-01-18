import { useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  Users,
  FileText,
  FileImage,
  Activity,
  Home,
  LogOut,
  Sparkles,
  ChevronRight,
} from 'lucide-react';
import ThemeToggle from './ThemeToggle';
import LanguageSelector from './LanguageSelector';
import { useAuth } from '@/contexts/AuthContext';
import { useRecentPatients } from '@/store/usePatientStore';

interface AppNavigationProps {
  variant?: 'header' | 'sidebar';
  showRecent?: boolean;
}

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  path: string;
  badge?: number;
}

export default function AppNavigation({ variant = 'header', showRecent = true }: AppNavigationProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const recentPatients = useRecentPatients();

  const navItems: NavItem[] = [
    {
      id: 'patients',
      label: t('navigation.patients', 'Pacientes'),
      icon: <Users className="w-5 h-5" />,
      path: '/app/patients',
    },
    {
      id: 'documents',
      label: t('navigation.documents', 'Documentos'),
      icon: <FileText className="w-5 h-5" />,
      path: '/app/documents',
    },
    {
      id: 'viewer',
      label: t('navigation.viewer', 'Visor'),
      icon: <FileImage className="w-5 h-5" />,
      path: '/app/viewer',
    },
  ];

  const isActive = useCallback(
    (path: string) => {
      if (path === '/app/patients') {
        return location.pathname === '/app' || location.pathname.startsWith('/app/patients');
      }
      return location.pathname.startsWith(path);
    },
    [location.pathname]
  );

  if (variant === 'sidebar') {
    return (
      <motion.aside
        initial={{ x: -300, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        className="w-64 h-full flex flex-col bg-white/70 dark:bg-gray-900/70 backdrop-blur-xl border-r border-gray-200/50 dark:border-gray-700/50"
      >
        {/* Logo */}
        <div className="p-4 border-b border-gray-200/50 dark:border-gray-700/50">
          <div className="flex items-center gap-3">
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-br from-primary-500 to-accent-500 rounded-xl blur-lg opacity-60 dark:opacity-40" />
              <div className="relative bg-gradient-to-br from-primary-500 to-accent-500 p-2.5 rounded-xl">
                <Activity className="w-6 h-6 text-white" />
              </div>
            </div>
            <div>
              <h1 className="text-lg font-bold bg-gradient-to-r from-primary-600 to-accent-600 dark:from-primary-400 dark:to-accent-400 bg-clip-text text-transparent">
                Medical EHR
              </h1>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {t('navigation.subtitle', 'Sistema de Imágenes')}
              </p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => navigate(item.path)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
                isActive(item.path)
                  ? 'bg-gradient-to-r from-primary-500 to-accent-500 text-white shadow-lg'
                  : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              {item.icon}
              <span className="font-medium">{item.label}</span>
              {item.badge !== undefined && (
                <span
                  className={`ml-auto px-2 py-0.5 rounded-full text-xs ${
                    isActive(item.path) ? 'bg-white/20' : 'bg-gray-200 dark:bg-gray-700'
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Recent Patients */}
        {showRecent && recentPatients.length > 0 && (
          <div className="p-4 border-t border-gray-200/50 dark:border-gray-700/50">
            <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
              {t('navigation.recentPatients', 'Pacientes Recientes')}
            </h3>
            <div className="space-y-1">
              {recentPatients.slice(0, 3).map((patient) => (
                <button
                  key={patient.id}
                  onClick={() => navigate(`/app/patients/${patient.id}`)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
                >
                  <div className="w-7 h-7 bg-gradient-to-br from-primary-400 to-accent-400 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                    {patient.full_name
                      .split(' ')
                      .map((n) => n[0])
                      .join('')
                      .slice(0, 2)}
                  </div>
                  <span className="truncate">{patient.full_name}</span>
                  <ChevronRight className="w-4 h-4 ml-auto text-gray-400 flex-shrink-0" />
                </button>
              ))}
            </div>
          </div>
        )}

        {/* User & Settings */}
        <div className="p-4 border-t border-gray-200/50 dark:border-gray-700/50 space-y-3">
          {/* User info */}
          {user && (
            <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800/50 rounded-xl">
              <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-accent-500 rounded-lg flex items-center justify-center text-white font-bold">
                {user.full_name
                  .split(' ')
                  .map((n) => n[0])
                  .join('')
                  .toUpperCase()
                  .slice(0, 2)}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                  {user.full_name}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">
                  {user.role.toLowerCase()}
                </p>
              </div>
            </div>
          )}

          {/* Controls */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ThemeToggle variant="minimal" />
              <LanguageSelector variant="minimal" />
            </div>
            <button
              onClick={logout}
              className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
              title={t('auth.logout')}
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </motion.aside>
    );
  }

  // Header variant (inline navigation)
  return (
    <nav className="flex items-center gap-1">
      {navItems.map((item) => (
        <button
          key={item.id}
          onClick={() => navigate(item.path)}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl font-medium transition-all ${
            isActive(item.path)
              ? 'bg-gradient-to-r from-primary-500/20 to-accent-500/20 text-primary-700 dark:text-primary-400'
              : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
          }`}
        >
          {item.icon}
          <span className="hidden md:inline">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
