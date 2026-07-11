import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Map, Puzzle } from 'lucide-react';
import { SegmentationRow } from './SegmentationRow';

const base = {
  name: 'Expert Rater 1',
  icon: Puzzle,
  accent: 'purple' as const,
  highlighted: false,
  expanded: false,
  overlayOn: false,
  isDeleting: false,
  onRowClick: () => {},
  onToggleOverlay: () => {},
  onDelete: () => {},
};

describe('SegmentationRow', () => {
  it('renders the name', () => {
    render(<SegmentationRow {...base} />);
    expect(screen.getByText('Expert Rater 1')).toBeInTheDocument();
  });

  it('fires onRowClick, and onToggleOverlay/onDelete without bubbling to the row', () => {
    const onRowClick = vi.fn();
    const onToggleOverlay = vi.fn();
    const onDelete = vi.fn();
    render(
      <SegmentationRow {...base} name="MAGNIMS Zone Map" icon={Map} accent="emerald"
        onRowClick={onRowClick} onToggleOverlay={onToggleOverlay} onDelete={onDelete} />,
    );
    const buttons = screen.getAllByRole('button'); // [overlay, delete]
    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[1]);
    expect(onToggleOverlay).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledTimes(1);
    // clicking the row container
    fireEvent.click(screen.getByText('MAGNIMS Zone Map'));
    expect(onRowClick).toHaveBeenCalled();
  });

  it('reflects overlayOn via the title (Hide vs Show overlay)', () => {
    const { rerender } = render(<SegmentationRow {...base} overlayOn={false} />);
    expect(screen.getByTitle('Show overlay')).toBeInTheDocument();
    rerender(<SegmentationRow {...base} overlayOn={true} />);
    expect(screen.getByTitle('Hide overlay')).toBeInTheDocument();
  });

  it('disables the delete button while deleting', () => {
    render(<SegmentationRow {...base} isDeleting={true} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons[1]).toBeDisabled();
  });
});
