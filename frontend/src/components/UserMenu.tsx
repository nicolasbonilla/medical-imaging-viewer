import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { LogOut, User } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

/**
 * UserMenu — icon-only in header (36×36 avatar), name in dropdown.
 *
 * Design System §2: all header controls are 36×36, radius-md (6px).
 * Name and role shown in dropdown panel, NOT in the button.
 */
export default function UserMenu() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);

  if (!user) return null;

  const initials = user.full_name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="relative">
      {/* Trigger: 36×36 avatar-only button — Design System §2 */}
      <button
        onClick={() => setOpen(!open)}
        aria-label={user.full_name}
        title={`${user.full_name} (${user.role})`}
        style={{ width: 36, height: 36, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        className="bg-brand-950 border border-brand-500/30 text-white font-bold text-xs hover:opacity-90 transition-opacity"
      >
        {initials}
      </button>

      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0" style={{ zIndex: 400 }} onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
              className="absolute right-0 top-full mt-2 border border-gray-700 overflow-hidden"
              style={{ width: 220, borderRadius: 8, background: '#1F2937', zIndex: 500 }}
            >
              {/* User info — visible here, NOT in the button */}
              <div className="px-4 py-3 border-b border-gray-700">
                <p style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB' }}>{user.full_name}</p>
                <p style={{ fontSize: 12, color: '#9CA3AF' }}>{user.email || user.username}</p>
                <p style={{ fontSize: 11, color: '#6B7280', marginTop: 2, textTransform: 'capitalize' }}>{user.role}</p>
              </div>
              <div className="py-1">
                <button
                  onClick={() => { navigate('/app/profile'); setOpen(false); }}
                  className="w-full flex items-center gap-3 px-4 text-gray-300 hover:bg-gray-700/50 transition-colors"
                  style={{ height: 40, fontSize: 13 }}
                >
                  <User style={{ width: 16, height: 16 }} />
                  {t('auth.profile', 'My Profile')}
                </button>
                <button
                  onClick={() => { setOpen(false); logout(); }}
                  className="w-full flex items-center gap-3 px-4 text-red-400 hover:bg-red-900/20 transition-colors"
                  style={{ height: 40, fontSize: 13 }}
                >
                  <LogOut style={{ width: 16, height: 16 }} />
                  {t('auth.logout')}
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
