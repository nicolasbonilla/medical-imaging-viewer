import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InstanceButton } from './InstanceButton';

const inst = { id: 'i1', original_filename: 'sub-01_FLAIR.nii.gz', file_size_bytes: 3_670_016 };

describe('InstanceButton', () => {
  it('renders the filename and size in MB', () => {
    render(<InstanceButton instance={inst} selected={false} onSelect={() => {}} variant="original" />);
    expect(screen.getByText('sub-01_FLAIR.nii.gz')).toBeInTheDocument();
    expect(screen.getByText('3.5MB')).toBeInTheDocument();
  });

  it('falls back to a variant-specific label when no filename', () => {
    const { rerender } = render(
      <InstanceButton instance={{ id: 'x', file_size_bytes: 0 }} selected={false} onSelect={() => {}} variant="original" />,
    );
    expect(screen.getByText('Image')).toBeInTheDocument();
    rerender(
      <InstanceButton instance={{ id: 'x', file_size_bytes: 0 }} selected={false} onSelect={() => {}} variant="preprocessed" />,
    );
    expect(screen.getByText('Preprocessed')).toBeInTheDocument();
  });

  it('calls onSelect with the instance id on click', () => {
    const onSelect = vi.fn();
    render(<InstanceButton instance={inst} selected={false} onSelect={onSelect} variant="original" />);
    fireEvent.click(screen.getByRole('button'));
    expect(onSelect).toHaveBeenCalledWith('i1');
  });
});
