/**
 * v3 accessible primitives: every icon-only control has a name, segmented controls
 * are radio groups with arrow keys, menus open outside clipping containers (portal)
 * and close on Escape / outside click, switches expose their state.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IconButton, Menu, MenuItem, SegmentedControl, Switch, Tabs } from './index';

describe('IconButton', () => {
  it('uses the required label as accessible name and tooltip', () => {
    render(<IconButton label="Zoom in" icon={<svg />} />);
    const b = screen.getByRole('button', { name: 'Zoom in' });
    expect(b).toHaveAttribute('title', 'Zoom in');
  });
  it('exposes a pressed state when active', () => {
    render(<IconButton label="Ruler" icon={<svg />} active />);
    expect(screen.getByRole('button', { name: 'Ruler' })).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('SegmentedControl', () => {
  it('is a radio group; arrow keys move the selection', () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl ariaLabel="Plane" value="axial" onChange={onChange}
        options={[{ value: 'axial', label: 'Axial' }, { value: 'coronal', label: 'Coronal' }, { value: 'sagittal', label: 'Sagittal' }]} />,
    );
    const group = screen.getByRole('radiogroup', { name: 'Plane' });
    expect(screen.getByRole('radio', { name: 'Axial' })).toHaveAttribute('aria-checked', 'true');
    fireEvent.keyDown(group, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('coronal');
    fireEvent.keyDown(group, { key: 'End' });
    expect(onChange).toHaveBeenLastCalledWith('sagittal');
  });
});

describe('Menu', () => {
  function Demo({ onPick = () => {} }: { onPick?: () => void }) {
    return (
      <div style={{ overflow: 'hidden', height: 10 }}>
        <Menu trigger={(p) => <button type="button" {...p}>Open</button>}>
          {(close) => <MenuItem radio checked onSelect={() => { onPick(); close(); }}>Choice</MenuItem>}
        </Menu>
      </div>
    );
  }
  it('opens into a portal (not clipped by an overflow-hidden parent) and closes on Escape', () => {
    render(<Demo />);
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    const menu = screen.getByRole('menu');
    expect(menu.parentElement).toBe(document.body);
    expect(screen.getByRole('menuitemradio', { name: 'Choice' })).toHaveAttribute('aria-checked', 'true');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
  });
  it('selecting an item runs it and closes; outside click closes', () => {
    const onPick = vi.fn();
    render(<Demo onPick={onPick} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Choice' }));
    expect(onPick).toHaveBeenCalled();
    expect(screen.queryByRole('menu')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('menu')).toBeNull();
  });
});

describe('Switch and Tabs', () => {
  it('Switch exposes role=switch with aria-checked and a label', () => {
    const onChange = vi.fn();
    render(<Switch checked={false} onChange={onChange} label="Show overlay" />);
    const sw = screen.getByRole('switch', { name: 'Show overlay' });
    expect(sw).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(sw);
    expect(onChange).toHaveBeenCalledWith(true);
  });
  it('Tabs is a tablist with roving selection', () => {
    const onChange = vi.fn();
    render(<Tabs idPrefix="t" ariaLabel="Panels" value="a" onChange={onChange}
      items={[{ value: 'a', label: 'Image' }, { value: 'b', label: 'Report' }]} />);
    expect(screen.getByRole('tab', { name: 'Image' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('b');
  });
});
