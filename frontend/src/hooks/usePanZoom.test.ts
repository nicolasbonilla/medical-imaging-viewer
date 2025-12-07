/**
 * Tests for usePanZoom hook
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePanZoom } from './usePanZoom';
import { useViewerStore } from '@/store/useViewerStore';

// Mock the store
vi.mock('@/store/useViewerStore', () => ({
  useViewerStore: vi.fn(),
}));

describe('usePanZoom', () => {
  let mockSetZoomLevel: ReturnType<typeof vi.fn>;
  let mockSetPanOffset: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockSetZoomLevel = vi.fn();
    mockSetPanOffset = vi.fn();

    (useViewerStore as any).mockReturnValue({
      zoomLevel: 1,
      setZoomLevel: mockSetZoomLevel,
      panOffset: { x: 0, y: 0 },
      setPanOffset: mockSetPanOffset,
    });
  });

  it('should initialize with correct default values', () => {
    const { result } = renderHook(() => usePanZoom());

    expect(result.current.isDragging).toBe(false);
    expect(typeof result.current.handleMouseDown).toBe('function');
    expect(typeof result.current.handleMouseMove).toBe('function');
    expect(typeof result.current.handleMouseUp).toBe('function');
    expect(typeof result.current.handleZoomIn).toBe('function');
    expect(typeof result.current.handleZoomOut).toBe('function');
    expect(typeof result.current.handleResetView).toBe('function');
  });

  it('should zoom in when handleZoomIn is called', () => {
    const { result } = renderHook(() => usePanZoom());

    act(() => {
      result.current.handleZoomIn();
    });

    expect(mockSetZoomLevel).toHaveBeenCalledWith(1.25);
  });

  it('should zoom out when handleZoomOut is called', () => {
    const { result } = renderHook(() => usePanZoom());

    act(() => {
      result.current.handleZoomOut();
    });

    expect(mockSetZoomLevel).toHaveBeenCalledWith(0.75);
  });

  it('should not zoom in beyond maximum (5x)', () => {
    (useViewerStore as any).mockReturnValue({
      zoomLevel: 5,
      setZoomLevel: mockSetZoomLevel,
      panOffset: { x: 0, y: 0 },
      setPanOffset: mockSetPanOffset,
    });

    const { result } = renderHook(() => usePanZoom());

    act(() => {
      result.current.handleZoomIn();
    });

    expect(mockSetZoomLevel).toHaveBeenCalledWith(5); // Max zoom
  });

  it('should not zoom out beyond minimum (0.25x)', () => {
    (useViewerStore as any).mockReturnValue({
      zoomLevel: 0.25,
      setZoomLevel: mockSetZoomLevel,
      panOffset: { x: 0, y: 0 },
      setPanOffset: mockSetPanOffset,
    });

    const { result } = renderHook(() => usePanZoom());

    act(() => {
      result.current.handleZoomOut();
    });

    expect(mockSetZoomLevel).toHaveBeenCalledWith(0.25); // Min zoom
  });

  it('should reset view when handleResetView is called', () => {
    (useViewerStore as any).mockReturnValue({
      zoomLevel: 2,
      setZoomLevel: mockSetZoomLevel,
      panOffset: { x: 100, y: 50 },
      setPanOffset: mockSetPanOffset,
    });

    const { result } = renderHook(() => usePanZoom());

    act(() => {
      result.current.handleResetView();
    });

    expect(mockSetZoomLevel).toHaveBeenCalledWith(1);
    expect(mockSetPanOffset).toHaveBeenCalledWith({ x: 0, y: 0 });
  });

  it('should start dragging on mouse down', () => {
    const { result } = renderHook(() => usePanZoom());

    const mockEvent = {
      clientX: 100,
      clientY: 50,
    } as React.MouseEvent;

    act(() => {
      result.current.handleMouseDown(mockEvent);
    });

    expect(result.current.isDragging).toBe(true);
  });

  it('should stop dragging on mouse up', () => {
    const { result } = renderHook(() => usePanZoom());

    // Start dragging
    act(() => {
      result.current.handleMouseDown({ clientX: 100, clientY: 50 } as React.MouseEvent);
    });

    expect(result.current.isDragging).toBe(true);

    // Stop dragging
    act(() => {
      result.current.handleMouseUp();
    });

    expect(result.current.isDragging).toBe(false);
  });

  it('should update pan offset when dragging', () => {
    const { result } = renderHook(() => usePanZoom());

    // Start dragging
    act(() => {
      result.current.handleMouseDown({ clientX: 100, clientY: 50 } as React.MouseEvent);
    });

    // Move mouse
    act(() => {
      result.current.handleMouseMove({ clientX: 150, clientY: 100 } as React.MouseEvent);
    });

    expect(mockSetPanOffset).toHaveBeenCalledWith({ x: 50, y: 50 });
  });

  it('should not update pan offset when not dragging', () => {
    const { result } = renderHook(() => usePanZoom());

    // Move mouse without starting drag
    act(() => {
      result.current.handleMouseMove({ clientX: 150, clientY: 100 } as React.MouseEvent);
    });

    expect(mockSetPanOffset).not.toHaveBeenCalled();
  });
});
