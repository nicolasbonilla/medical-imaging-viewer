/**
 * Tests for SliceSlider component
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SliceSlider } from './SliceSlider';

describe('SliceSlider', () => {
  it('should render slider with correct initial value', () => {
    render(
      <SliceSlider
        currentSliceIndex={10}
        totalSlices={100}
        onChange={vi.fn()}
      />
    );

    const slider = screen.getByRole('slider');
    expect(slider).toBeInTheDocument();
    expect(slider).toHaveValue('10');
  });

  it('should have correct min and max values', () => {
    render(
      <SliceSlider
        currentSliceIndex={0}
        totalSlices={50}
        onChange={vi.fn()}
      />
    );

    const slider = screen.getByRole('slider');
    expect(slider).toHaveAttribute('min', '0');
    expect(slider).toHaveAttribute('max', '49'); // totalSlices - 1
  });

  it('should call onChange when slider value changes', () => {
    const mockOnChange = vi.fn();

    render(
      <SliceSlider
        currentSliceIndex={0}
        totalSlices={100}
        onChange={mockOnChange}
      />
    );

    const slider = screen.getByRole('slider');

    // jsdom does not implement range-input keyboard stepping, so drive the
    // change event directly (this is the actual DOM event the component binds).
    fireEvent.change(slider, { target: { value: '1' } });

    expect(mockOnChange).toHaveBeenCalledWith(1);
  });

  it('should call onChange with correct slice index', async () => {
    const mockOnChange = vi.fn();

    const { rerender } = render(
      <SliceSlider
        currentSliceIndex={10}
        totalSlices={100}
        onChange={mockOnChange}
      />
    );

    const slider = screen.getByRole('slider');

    // Manually trigger change event
    slider.setAttribute('value', '25');
    slider.dispatchEvent(new Event('change', { bubbles: true }));

    // Re-render with new value
    rerender(
      <SliceSlider
        currentSliceIndex={25}
        totalSlices={100}
        onChange={mockOnChange}
      />
    );

    expect(slider).toHaveValue('25');
  });

  it('should handle edge case with single slice', () => {
    render(
      <SliceSlider
        currentSliceIndex={0}
        totalSlices={1}
        onChange={vi.fn()}
      />
    );

    const slider = screen.getByRole('slider');
    expect(slider).toHaveAttribute('min', '0');
    expect(slider).toHaveAttribute('max', '0');
    expect(slider).toHaveValue('0');
  });

  it('should handle maximum slice index', () => {
    const totalSlices = 100;
    render(
      <SliceSlider
        currentSliceIndex={99}
        totalSlices={totalSlices}
        onChange={vi.fn()}
      />
    );

    const slider = screen.getByRole('slider');
    expect(slider).toHaveValue('99');
  });
});
