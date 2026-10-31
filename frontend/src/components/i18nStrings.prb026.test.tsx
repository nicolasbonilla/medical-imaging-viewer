/**
 * PRB-026 (F03) — Spanish text in the English (and German) user interface, written into the code instead of the
 * translation files: "Cargando volumen…", "W/L GPU · solo visualización (para pintar, usa el modo estándar)",
 * "No se pudo cargar el volumen" (NiivueViewer2D.tsx), "Cargando visor GPU…" (ImageViewer2D.tsx), the tooltip
 * "Ventana/nivel instantáneo por GPU (solo visualización)" (ViewerControls.tsx), the provenance badges
 * "Experto" / "IA" / "IA · investigación" / "Sin verificar" (viewer/SegmentationRow.tsx) and the whole
 * CALM-MS second-reader panel (ConformalPanel.tsx). The provenance badge is a Class C traceability control: a
 * clinician must read it in the language of the interface. Wanted: every one of these strings in en/es/de.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Puzzle } from 'lucide-react';
import i18n from '@/i18n/config';
import { SegmentationRow } from './viewer/SegmentationRow';
import { ConformalPanel } from './ConformalPanel';
import en from '@/i18n/locales/en.json';
import es from '@/i18n/locales/es.json';
import de from '@/i18n/locales/de.json';

const row = {
  name: 'Expert Rater 1', icon: Puzzle, accent: 'purple' as const, highlighted: false, expanded: false,
  overlayOn: false, isDeleting: false, onRowClick: () => {}, onToggleOverlay: () => {}, onDelete: () => {},
};

// Words that mark Spanish text; none may appear in the English interface of these components.
const SPANISH = /Cargando|visualizaci|usa el modo|No se pudo|Ventana\/nivel|Experto|\bIA\b|investigaci|Sin verificar|Segunda lectura|Alta sensibilidad|Balanceado|Alta precisi|Analizar|Ocultar|Mostrar|Limpiar|candidatos|objetivo FDR|mapa de probabilidad/;

const FILES = ['NiivueViewer2D.tsx', 'ImageViewer2D.tsx', 'ViewerControls.tsx', 'viewer/SegmentationRow.tsx', 'ConformalPanel.tsx'];

describe('PRB-026 interface strings follow the interface language', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('rc087 prb026 provenance badges in English', () => {
    const { rerender } = render(<SegmentationRow {...row} origin="expert" />);
    expect(screen.getByText('Expert')).toBeInTheDocument();
    rerender(<SegmentationRow {...row} origin="ai" />);
    expect(screen.getByText('AI')).toBeInTheDocument();
    rerender(<SegmentationRow {...row} origin="ai-legacy" />);
    expect(screen.getByText('AI · research')).toBeInTheDocument();
    rerender(<SegmentationRow {...row} origin="unknown" />);
    expect(screen.getByText('Unverified')).toBeInTheDocument();
  });

  it('rc087 prb026 provenance badges in German and Spanish', async () => {
    await i18n.changeLanguage('de');
    const { rerender } = render(<SegmentationRow {...row} origin="expert" />);
    expect(screen.getByText('Experte')).toBeInTheDocument();
    rerender(<SegmentationRow {...row} origin="ai" />);
    expect(screen.getByText('KI')).toBeInTheDocument();
    await i18n.changeLanguage('es');
    rerender(<SegmentationRow {...row} origin="expert" />);
    expect(screen.getByText('Experto')).toBeInTheDocument();
  });

  it('rc087 prb026 the CALM-MS panel is in English in the English interface', () => {
    const { container } = render(<ConformalPanel />);
    expect(container.textContent).not.toMatch(SPANISH);
    expect(screen.getByText(/second reader/i)).toBeInTheDocument();
    const input = container.querySelector('input')!;
    expect(input.getAttribute('placeholder') || '').not.toMatch(SPANISH);
  });

  it('rc087 prb026 no Spanish text is written into these components', () => {
    const sources = import.meta.glob(['./NiivueViewer2D.tsx', './ImageViewer2D.tsx', './ViewerControls.tsx',
      './viewer/SegmentationRow.tsx', './ConformalPanel.tsx'], { eager: true, query: '?raw', import: 'default' });
    expect(Object.keys(sources)).toHaveLength(FILES.length);
    for (const [file, raw] of Object.entries(sources)) {
      // Comments may mention the old text; the code may not.
      const code = String(raw).replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
      expect(code, file).not.toMatch(SPANISH);
    }
  });

  it('rc087 prb026 every new key exists in English, Spanish and German', () => {
    const keys = ['viewer.loadingVolume', 'viewer.volumeLoadFailed', 'viewer.niivueViewOnly', 'viewer.niivueHint',
      'viewer.loadingGpuViewer', 'viewer.showOverlay', 'viewer.hideOverlay',
      'provenance.expert', 'provenance.ai', 'provenance.aiLegacy', 'provenance.unknown',
      'provenance.expertTitle', 'provenance.aiTitle', 'provenance.aiLegacyTitle', 'provenance.unknownTitle',
      'conformal.title', 'conformal.investigational', 'conformal.analyze', 'conformal.disclaimer'];
    const get = (o: unknown, k: string) => k.split('.').reduce<unknown>((a, p) => (a as Record<string, unknown>)?.[p], o);
    for (const [lang, file] of [['en', en], ['es', es], ['de', de]] as const) {
      for (const k of keys) expect(typeof get(file, k), `${lang}:${k}`).toBe('string');
    }
    for (const k of keys) expect(String(get(en, k)), `en:${k}`).not.toMatch(SPANISH);
  });
});
