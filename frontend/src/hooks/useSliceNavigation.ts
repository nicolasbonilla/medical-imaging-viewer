/**
 * Hook for managing slice navigation via keyboard and mouse wheel.
 * Handles keyboard arrow keys and mouse wheel scrolling for slice changes.
 */

import { useEffect, useRef } from 'react';
import { useViewerStore } from '@/store/useViewerStore';

interface UseSliceNavigationProps {
  scrollableRef: React.RefObject<HTMLDivElement>;
}

export function useSliceNavigation({ scrollableRef }: UseSliceNavigationProps) {
  const { currentSeries, currentSliceIndex, setCurrentSliceIndex, zoomLevel, setZoomLevel } = useViewerStore();

  // Use refs to avoid recreating wheel listener on every render
  const currentSliceRef = useRef(currentSliceIndex);
  const totalSlicesRef = useRef(currentSeries?.total_slices || 0);
  const currentSeriesRef = useRef(currentSeries);
  const zoomLevelRef = useRef(zoomLevel);

  // Keep refs updated without triggering listener re-creation
  currentSliceRef.current = currentSliceIndex;
  totalSlicesRef.current = currentSeries?.total_slices || 0;
  currentSeriesRef.current = currentSeries;
  zoomLevelRef.current = zoomLevel;

  // Setup wheel listener: plain wheel = slice nav, Ctrl+wheel = zoom
  useEffect(() => {
    const scrollable = scrollableRef.current;
    if (!scrollable || !currentSeries) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();

      if (e.ctrlKey || e.metaKey) {
        // Ctrl+wheel: zoom in/out with adaptive step
        const currentZoom = zoomLevelRef.current;
        const step = Math.max(0.25, Math.round(currentZoom * 0.15 * 4) / 4);
        const newZoom = e.deltaY < 0
          ? Math.min(20, currentZoom + step)
          : Math.max(0.25, currentZoom - step);
        setZoomLevel(newZoom);
      } else {
        // Plain wheel: slice navigation
        const delta = e.deltaY > 0 ? 1 : -1;
        const newIndex = Math.max(
          0,
          Math.min(totalSlicesRef.current - 1, currentSliceRef.current + delta)
        );
        setCurrentSliceIndex(newIndex);
      }
    };

    scrollable.addEventListener('wheel', handleWheel, { passive: false });
    return () => scrollable.removeEventListener('wheel', handleWheel);
  }, [currentSeries, scrollableRef, setCurrentSliceIndex, setZoomLevel]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (!currentSeries) return;

      if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
        setCurrentSliceIndex(Math.max(0, currentSliceIndex - 1));
      } else if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
        setCurrentSliceIndex(
          Math.min(currentSeries.total_slices - 1, currentSliceIndex + 1)
        );
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [currentSeries, currentSliceIndex, setCurrentSliceIndex]);
}
