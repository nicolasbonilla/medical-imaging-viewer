/**
 * Hook for managing matplotlib visualization queries and rendering.
 * Handles fetching matplotlib-rendered images from the backend.
 *
 * OPTIMIZATION: Uses debouncing to prevent server overload when scrolling
 * through slices rapidly. The slice index is debounced by 300ms before
 * triggering the API request.
 */

import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { imagingAPI } from '@/services/api';
import { useViewerStore } from '@/store/useViewerStore';

interface UseMatplotlibVisualizationProps {
  colormap: string;
  appliedXMin: string;
  appliedXMax: string;
  appliedYMin: string;
  appliedYMax: string;
}

// Debounce delay in ms - prevents server overload when scrolling
const DEBOUNCE_DELAY = 300;

export function useMatplotlibVisualization({
  colormap,
  appliedXMin,
  appliedXMax,
  appliedYMin,
  appliedYMax,
}: UseMatplotlibVisualizationProps) {
  const { currentSeries, currentSliceIndex } = useViewerStore();

  // Debounced slice index - only updates after user stops scrolling
  const [debouncedSliceIndex, setDebouncedSliceIndex] = useState(currentSliceIndex);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounce the slice index changes
  useEffect(() => {
    // Clear any existing timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Set new timer
    debounceTimerRef.current = setTimeout(() => {
      setDebouncedSliceIndex(currentSliceIndex);
    }, DEBOUNCE_DELAY);

    // Cleanup on unmount
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [currentSliceIndex]);

  const { data: matplotlibData, isLoading: matplotlibLoading } = useQuery({
    queryKey: [
      'matplotlib-2d',
      currentSeries?.file_id,
      debouncedSliceIndex, // Use debounced value
      colormap,
      appliedXMin,
      appliedXMax,
      appliedYMin,
      appliedYMax,
    ],
    queryFn: async () => {
      const result = currentSeries && currentSeries.file_id
        ? await imagingAPI.getMatplotlib2D(
            currentSeries.file_id,
            debouncedSliceIndex,
            undefined,
            undefined,
            colormap,
            appliedXMin.trim() !== '' ? parseInt(appliedXMin) : undefined,
            appliedXMax.trim() !== '' ? parseInt(appliedXMax) : undefined,
            appliedYMin.trim() !== '' ? parseInt(appliedYMin) : undefined,
            appliedYMax.trim() !== '' ? parseInt(appliedYMax) : undefined,
            true  // minimal=true for exact voxel-to-voxel match with Standard mode
          )
        : null;

      return result;
    },
    enabled: !!currentSeries?.file_id,
    staleTime: 5 * 60 * 1000, // 5 minutes - cache results to avoid redundant requests
    gcTime: 10 * 60 * 1000, // 10 minutes - keep in cache longer
    retry: 2, // Retry failed requests up to 2 times
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000), // Exponential backoff
  });

  // Determine if we're still waiting for debounce to settle
  const isPendingDebounce = currentSliceIndex !== debouncedSliceIndex;

  return {
    matplotlibData,
    // Show loading state if either waiting for debounce or actually loading
    matplotlibLoading: matplotlibLoading || isPendingDebounce,
  };
}
