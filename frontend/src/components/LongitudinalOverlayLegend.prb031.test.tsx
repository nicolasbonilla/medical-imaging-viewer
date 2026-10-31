/**
 * Independent review of PR #74, m6 — the 2D longitudinal overlay had no legend: nothing said which colour is a
 * persistent, a resolved or a new lesion. A small legend now sits with the comparison result while the overlay is
 * shown, in the colours the canvas draws (LONGITUDINAL_OVERLAY_COLORS), with the words (not only the colours).
 * Written before the correction (the component does not exist on 290e407).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import { LongitudinalOverlayLegend } from './LongitudinalOverlayLegend';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { LONGITUDINAL_OVERLAY_COLORS } from '@/utils/regionColors';

const rgb = (hex: string) => `rgb(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(', ')})`;

beforeEach(() => {
  useSegmentationStore.setState({ longitudinalVisible: false } as never);
});

describe('review m6: a legend for the longitudinal overlay', () => {
  it('rc093 review m6 while the overlay is shown, each class is named with the colour the overlay draws', () => {
    useSegmentationStore.setState({ longitudinalVisible: true } as never);
    render(<LongitudinalOverlayLegend />);
    for (const [key, word] of [['persistent', /persistent/i], ['resolved', /resolved/i], ['new', /new/i]] as const) {
      const item = screen.getByTestId(`longitudinal-legend-${key}`);
      expect(item).toHaveTextContent(word);
      expect((item.querySelector('[data-swatch]') as HTMLElement).style.backgroundColor).toBe(rgb(LONGITUDINAL_OVERLAY_COLORS[key]));
    }
  });

  it('rc093 review m6 no legend while the overlay is hidden', () => {
    render(<LongitudinalOverlayLegend />);
    expect(screen.queryByTestId('longitudinal-legend')).not.toBeInTheDocument();
  });
});
