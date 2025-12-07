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
    return (
      <button
        onClick={toggleTheme}
        className="relative w-14 h-7 bg-gradient-to-r from-primary-500/20 to-accent-500/20 dark:from-primary-600/30 dark:to-accent-600/30 rounded-full p-1 backdrop-blur-md border border-white/10 dark:border-white/5 transition-all duration-300 hover:scale-105 group"
        aria-label="Toggle theme"
      >
        <motion.div
          className="absolute w-5 h-5 bg-gradient-to-br from-primary-400 to-accent-400 dark:from-primary-500 dark:to-accent-500 rounded-full shadow-lg flex items-center justify-center"
          animate={{
            x: isDark ? 28 : 2,
          }}
          transition={{
            type: 'spring',
            stiffness: 500,
            damping: 30,
          }}
        >
          {isDark ? (
            <Moon className="w-3 h-3 text-white" />
          ) : (
            <Sun className="w-3 h-3 text-white" />
          )}
        </motion.div>
      </button>
    );
  }

  return (
    <motion.button
      onClick={toggleTheme}
      className="relative w-16 h-8 bg-gradient-to-r from-primary-500/20 to-accent-500/20 dark:from-primary-600/30 dark:to-accent-600/30 rounded-full p-1 backdrop-blur-md border border-white/10 dark:border-white/5 transition-all duration-300 hover:shadow-xl hover:shadow-primary-500/20 dark:hover:shadow-accent-500/20"
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      aria-label="Toggle theme"
    >
      <motion.div
        className="absolute top-1 w-6 h-6 bg-gradient-to-br from-primary-400 to-accent-400 dark:from-primary-500 dark:to-accent-500 rounded-full shadow-lg flex items-center justify-center"
        animate={{
          x: isDark ? 32 : 2,
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
