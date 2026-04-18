import React from 'react';
import { motion } from 'framer-motion';
import { Sun, Moon } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

interface ThemeToggleProps {
  variant?: 'default' | 'minimal';
}

const ThemeToggle: React.FC<ThemeToggleProps> = ({ variant = 'default' }) => {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === 'dark';

  if (variant === 'minimal') {
    // Design System §2: icon-only button, 36×36, radius-md (6px)
    return (
      <button
        onClick={toggleTheme}
        aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        title={isDark ? 'Light mode' : 'Dark mode'}
        style={{ width: 36, height: 36, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        className="bg-transparent hover:bg-gray-700 text-gray-400 hover:text-gray-200 border border-gray-700 transition-colors"
      >
        {isDark ? <Sun style={{ width: 16, height: 16 }} /> : <Moon style={{ width: 16, height: 16 }} />}
      </button>
    );
  }

  return (
    <motion.button
      onClick={toggleTheme}
      className="relative w-14 h-7 bg-gradient-to-r from-primary-500/20 to-accent-500/20 dark:from-primary-600/30 dark:to-accent-600/30 rounded-full backdrop-blur-md border border-white/10 dark:border-white/5 transition-all duration-300 hover:shadow-xl hover:shadow-primary-500/20 dark:hover:shadow-accent-500/20"
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      aria-label="Toggle theme"
    >
      <motion.div
        className="absolute top-[3px] left-[3px] w-[22px] h-[22px] bg-gradient-to-br from-primary-400 to-accent-400 dark:from-primary-500 dark:to-accent-500 rounded-full shadow-lg flex items-center justify-center"
        animate={{
          x: isDark ? 28 : 0,
        }}
        transition={{
          type: 'spring',
          stiffness: 500,
          damping: 30,
        }}
      >
        <motion.div
          initial={{ rotate: 0, scale: 0.8 }}
          animate={{
            rotate: isDark ? 360 : 0,
            scale: 1
          }}
          transition={{ duration: 0.3 }}
        >
          {isDark ? (
            <Moon className="w-4 h-4 text-white" />
          ) : (
            <Sun className="w-4 h-4 text-white" />
          )}
        </motion.div>
      </motion.div>

      {/* Background icons */}
      <div className="absolute inset-0 flex items-center justify-between px-2 pointer-events-none">
        <Sun className={`w-3.5 h-3.5 transition-opacity duration-300 ${isDark ? 'opacity-30' : 'opacity-60'} text-yellow-500`} />
        <Moon className={`w-3.5 h-3.5 transition-opacity duration-300 ${isDark ? 'opacity-60' : 'opacity-30'} text-indigo-400`} />
      </div>
    </motion.button>
  );
};

export default ThemeToggle;
