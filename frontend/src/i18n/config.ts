import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import en from './locales/en.json';
import es from './locales/es.json';
import de from './locales/de.json';

/**
 * i18n Configuration
 *
 * Supports 3 languages:
 * - English (en) - Default
 * - Spanish (es)
 * - German (de)
 *
 * Features:
 * - Automatic language detection from browser
 * - localStorage persistence
 * - Fallback to English
 */

const resources = {
  en: { translation: en },
  es: { translation: es },
  de: { translation: de },
};

i18n
  // Detect user language
  .use(LanguageDetector)
  // Pass the i18n instance to react-i18next
  .use(initReactI18next)
  // Initialize i18next
  .init({
    resources,
    fallbackLng: 'es', // Changed from 'en' to 'es' for Spanish default
    lng: 'es', // Force Spanish as default language
    debug: false,

    // Language detection options
    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      caches: ['localStorage'],
      lookupLocalStorage: 'i18nextLng',
    },

    interpolation: {
      escapeValue: false, // React already escapes values
    },

    react: {
      useSuspense: false,
    },
  });

export default i18n;
