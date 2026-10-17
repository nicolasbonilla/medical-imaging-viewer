/**
 * v2 design tokens for code that cannot use Tailwind classes (canvas drawing).
 * MUST mirror `theme.extend.colors` in tailwind.config.js (surface / ink / brand).
 */
export const TOKENS = {
  surface: {
    void: '#08090C',
    base: '#0E1014',
    raised: '#161922',
    overlay: '#1C2029',
    border: '#232833',
    hover: '#2A303C',
  },
  ink: {
    faint: '#5C6472',
    muted: '#8A92A3',
    soft: '#B7BECC',
    base: '#EEF1F6',
  },
  brand: {
    400: '#57C7D4',
    500: '#35B4C4',
    600: '#2A93A1',
  },
} as const;
