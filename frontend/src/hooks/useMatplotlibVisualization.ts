/**
 * Hook for managing matplotlib visualization queries and rendering.
 * Handles fetching matplotlib-rendered images from the backend.
 *
 * OPTIMIZATION: Uses debouncing to prevent server overload when scrolling
 * through slices rapidly. The slice index is debounced by 300ms before
 * triggering the API request.
 */

import { useState, useEffect, useRef } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { imagingAPI } from '@/api/imaging';
import { useViewerStore } from '@/store/useViewerStore';

interface UseMatplotlibVisualizationProps {
  colormap: string;
  appliedXMin: string;
  appliedXMax: string;
  appliedYMin: string;
  appliedYMax: string;
  /** Segmentation ID to overlay on the matplotlib image (backend renders it) */
  segmentationId?: string;
  /** Opacity for the segmentation overlay (0-1) */
  overlayOpacity?: number;
}

// Debounce delay in ms - prevents server overload when scrolling
const DEBOUNCE_DELAY = 300;

export function useMatplotlibVisualization({
  colormap,
  appliedXMin,
  appliedXMax,
  appliedYMin,
  appliedYMax,
  segmentationId,
  overlayOpacity,
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

  const { data: matplotlibData, isLoading: matplotlibLoading, isError: matplotlibError } = useQuery({
    queryKey: [
      'matplotlib-2d',
      currentSeries?.file_id,
      debouncedSliceIndex, // Use debounced value
      colormap,
      appliedXMin,
      appliedXMax,
      appliedYMin,
      appliedYMax,
      segmentationId ?? null,
      overlayOpacity ?? null,
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
            true,  // minimal=true for exact voxel-to-voxel match with Standard mode
            segmentationId,
            overlayOpacity
          )
        : null;

      return result;
    },
    enabled: !!currentSeries?.file_id,
    staleTime: 5 * 60 * 1000, // 5 minutes - cache results to avoid redundant requests
    gcTime: 10 * 60 * 1000, // 10 minutes - keep in cache longer
    placeholderData: keepPreviousData, // Keep showing previous image while new query loads (prevents black screen)
    retry: 2, // Retry failed requests up to 2 times
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000), // Exponential backoff
  });

  // Determine if we're still waiting for debounce to settle
  const isPendingDebounce = currentSliceIndex !== debouncedSliceIndex;

  return {
    matplotlibData,
    // Show loading state if either waiting for debounce or actually loading
    matplotlibLoading: matplotlibLoading || isPendingDebounce,
    // Expose error state so ImageViewer2D can fall back to local canvas overlay
    matplotlibError,
  };
}
