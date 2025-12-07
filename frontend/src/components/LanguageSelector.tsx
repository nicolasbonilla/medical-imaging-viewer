import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { Globe, Check } from 'lucide-react';

/**
 * LanguageSelector Component
 *
 * Modern dropdown selector for choosing between English, Spanish, and German.
 * Features:
 * - Glassmorphism design
 * - Smooth animations with Framer Motion
 * - Persistent language selection (localStorage)
 * - Flag emojis for visual identification
 */

interface Language {
  code: string;
  name: string;
  flag: string;
  nativeName: string;
}

const languages: Language[] = [
  { code: 'en', name: 'English', flag: '🇬🇧', nativeName: 'English' },
  { code: 'es', name: 'Spanish', flag: '🇪🇸', nativeName: 'Español' },
  { code: 'de', name: 'German', flag: '🇩🇪', nativeName: 'Deutsch' },
];

interface LanguageSelectorProps {
  variant?: 'default' | 'minimal';
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left';
}

const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  variant = 'default',
  position = 'top-right',
}) => {
  const { i18n, t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  const currentLanguage = languages.find((lang) => lang.code === i18n.language) || languages[0];

  const handleLanguageChange = (languageCode: string) => {
    i18n.changeLanguage(languageCode);
    setIsOpen(false);
  };

  const positionClasses = {
    'top-right': 'top-0 right-0',
    'top-left': 'top-0 left-0',
    'bottom-right': 'bottom-0 right-0',
    'bottom-left': 'bottom-0 left-0',
  };

  if (variant === 'minimal') {
    return (
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 px-3 py-2 bg-white/10 hover:bg-white/20 backdrop-blur-md border border-white/20 rounded-lg transition-all duration-200"
          aria-label="Change language"
        >
          <Globe className="w-4 h-4 text-white" />
          <span className="text-sm text-white font-medium">{currentLanguage.flag}</span>
        </button>

        <AnimatePresence>
          {isOpen && (
            <>
              {/* Backdrop */}
              <div
                className="fixed inset-0 z-40"
                onClick={() => setIsOpen(false)}
              />

              {/* Dropdown */}
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: -10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: -10 }}
                transition={{ duration: 0.15 }}
                className="absolute top-full mt-2 right-0 z-50 min-w-[200px] bg-white/10 backdrop-blur-xl border border-white/20 rounded-xl shadow-2xl overflow-hidden"
              >
                {languages.map((language) => (
                  <button
                    key={language.code}
                    onClick={() => handleLanguageChange(language.code)}
                    className={`w-full px-4 py-3 flex items-center justify-between gap-3 transition-all duration-150 ${
                      currentLanguage.code === language.code
                        ? 'bg-blue-500/30 text-white'
                        : 'hover:bg-white/10 text-gray-200'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">{language.flag}</span>
                      <div className="text-left">
                        <div className="text-sm font-medium">{language.nativeName}</div>
                        <div className="text-xs opacity-70">{language.name}</div>
                      </div>
                    </div>
                    {currentLanguage.code === language.code && (
                      <Check className="w-4 h-4 text-blue-400" />
                    )}
                  </button>
                ))}
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>
    );
  }

  // Default variant - full button with language name
  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-3 px-4 py-2.5 bg-gradient-to-r from-blue-600/20 to-purple-600/20 hover:from-blue-600/30 hover:to-purple-600/30 backdrop-blur-lg border border-white/20 rounded-xl transition-all duration-200 shadow-lg"
        aria-label="Change language"
      >
        <Globe className="w-5 h-5 text-blue-400" />
        <div className="flex items-center gap-2">
          <span className="text-2xl">{currentLanguage.flag}</span>
          <span className="text-sm text-white font-medium hidden sm:inline">
            {currentLanguage.nativeName}
          </span>
        </div>
      </button>

      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <div
              className="fixed inset-0 z-40"
              onClick={() => setIsOpen(false)}
            />

            {/* Dropdown */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -10 }}
              transition={{ duration: 0.2 }}
              className="absolute top-full mt-3 right-0 z-50 min-w-[240px] bg-gradient-to-br from-gray-900/95 to-gray-800/95 backdrop-blur-xl border border-white/20 rounded-2xl shadow-2xl overflow-hidden"
            >
              <div className="p-2">
                <div className="px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  {t('settings.language')}
                </div>
                {languages.map((language) => (
                  <motion.button
                    key={language.code}
                    onClick={() => handleLanguageChange(language.code)}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    className={`w-full px-4 py-3 flex items-center justify-between gap-3 rounded-xl transition-all duration-150 ${
                      currentLanguage.code === language.code
                        ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg'
                        : 'hover:bg-white/10 text-gray-200'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-3xl">{language.flag}</span>
                      <div className="text-left">
                        <div className="text-sm font-semibold">{language.nativeName}</div>
                        <div className="text-xs opacity-70">{language.name}</div>
                      </div>
                    </div>
                    {currentLanguage.code === language.code && (
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className="bg-white/20 rounded-full p-1"
                      >
                        <Check className="w-4 h-4 text-white" />
                      </motion.div>
                    )}
                  </motion.button>
                ))}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};

export default LanguageSelector;
