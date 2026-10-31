/**
 * Independent review of PR #74, m6 — the legend of the 2D longitudinal overlay.
 *
 * The review asked for a legend. One existed, in the comparison result (LongitudinalResultPanel), but it hard-coded
 * the former colours (blue / green / red): after PRB-031 changed the overlay to the colour-blind-safe palette, the
 * legend no longer matched the image (found while integrating the review). The legend is now one component whose
 * colours come from LONGITUDINAL_OVERLAY_COLORS, the constant the canvas draws with; its words stay CAPA-013's neutral
 * ones (a candidate, not activity). Written before the correction (the component does not exist on 290e407).
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { LongitudinalOverlayLegend } from './LongitudinalOverlayLegend';
import { LONGITUDINAL_OVERLAY_COLORS } from '@/utils/regionColors';

const rgb = (hex: string) => `rgb(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(', ')})`;
const ACTIVITY = /activ|aktiv/i;

describe('review m6: the legend of the longitudinal overlay is in the colours the overlay draws', () => {
  it('rc093 review m6 each class is named with the colour the canvas draws for it', () => {
    render(<LongitudinalOverlayLegend />);
    for (const [key, word] of [['resolved', /only at visit 1/i], ['persistent', /at both visits/i], ['new', /only at visit 2/i]] as const) {
      const item = screen.getByTestId(`longitudinal-legend-${key}`);
      expect(item).toHaveTextContent(word);
      expect((item.querySelector('[data-swatch]') as HTMLElement).style.backgroundColor).toBe(rgb(LONGITUDINAL_OVERLAY_COLORS[key]));
    }
  });

  it('rc093 review m6 the legend never claims disease activity (CAPA-013 wording)', () => {
    render(<LongitudinalOverlayLegend />);
    expect(screen.getByTestId('longitudinal-legend').textContent).not.toMatch(ACTIVITY);
  });
});
