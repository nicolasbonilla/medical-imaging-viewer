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
  const { currentSeries, currentSliceIndex, setCurrentSliceIndex } = useViewerStore();

  // Use refs to avoid recreating wheel listener on every render
  const currentSliceRef = useRef(currentSliceIndex);
  const totalSlicesRef = useRef(currentSeries?.total_slices || 0);
  const currentSeriesRef = useRef(currentSeries);

  // Keep refs updated without triggering listener re-creation
  currentSliceRef.current = currentSliceIndex;
  totalSlicesRef.current = currentSeries?.total_slices || 0;
  currentSeriesRef.current = currentSeries;

  // Setup wheel listener
  useEffect(() => {
    const scrollable = scrollableRef.current;
    console.log('[WHEEL SETUP] Setting up wheel listener, scrollable:', !!scrollable, 'series:', !!currentSeries);

    if (!scrollable || !currentSeries) {
      console.log('[WHEEL SETUP] Skipping - missing scrollable or series');
      return;
    }

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      console.log('[WHEEL] ImageViewer2D wheel event:', {
        deltaY: e.deltaY,
        currentSlice: currentSliceRef.current,
        totalSlices: totalSlicesRef.current
      });

      const delta = e.deltaY > 0 ? 1 : -1;
      const newIndex = Math.max(
        0,
        Math.min(totalSlicesRef.current - 1, currentSliceRef.current + delta)
      );

      console.log('[WHEEL] Changing slice from', currentSliceRef.current, 'to', newIndex);
      setCurrentSliceIndex(newIndex);
    };

    // Add event listener with passive: false to allow preventDefault
    console.log('[WHEEL SETUP] Adding wheel event listener to scrollable div');
    scrollable.addEventListener('wheel', handleWheel, { passive: false });

    return () => {
      console.log('[WHEEL SETUP] Removing wheel event listener');
      scrollable.removeEventListener('wheel', handleWheel);
    };
  }, [currentSeries, scrollableRef, setCurrentSliceIndex]);

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
