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
    fireEvent.click(screen.getByRole('button', { name: 'Show overlay' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete segmentation' }));
    expect(onToggleOverlay).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onRowClick).not.toHaveBeenCalled();
    // clicking the row (its name) opens it
    fireEvent.click(screen.getByText('MAGNIMS Zone Map'));
    expect(onRowClick).toHaveBeenCalled();
  });

  it('is keyboard reachable: the name is a button whose activation opens the row', () => {
    const onRowClick = vi.fn();
    render(<SegmentationRow {...base} onRowClick={onRowClick} expanded={false} />);
    const primary = screen.getByRole('button', { name: /Expert Rater 1/ });
    expect(primary).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(primary); // Enter/Space on a button dispatch a click
    expect(onRowClick).toHaveBeenCalledTimes(1);
  });

  it('reflects overlayOn via the title (Hide vs Show overlay)', () => {
    const { rerender } = render(<SegmentationRow {...base} overlayOn={false} />);
    expect(screen.getByTitle('Show overlay')).toBeInTheDocument();
    rerender(<SegmentationRow {...base} overlayOn={true} />);
    expect(screen.getByTitle('Hide overlay')).toBeInTheDocument();
  });

  it('disables the delete button while deleting', () => {
    render(<SegmentationRow {...base} isDeleting={true} />);
    expect(screen.getByRole('button', { name: 'Delete segmentation' })).toBeDisabled();
  });

  it('shows the provenance badge (Class C traceability)', () => {
    render(<SegmentationRow {...base} origin="ai-legacy" />);
    expect(screen.getByText('IA · investigación')).toBeInTheDocument();
    expect(screen.getByTitle(/research only/)).toBeInTheDocument();
  });
});
