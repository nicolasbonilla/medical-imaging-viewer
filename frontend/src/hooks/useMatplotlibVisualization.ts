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
  const { currentSeries, currentSliceIndex, windowCenter, windowWidth } = useViewerStore();

  // Real DICOM window/level: the matplotlib endpoint re-renders the slice PNG from RAW
  // intensities with window_center/window_width — a true VOI-LUT on the SAME grid the
  // segmentation mask co-registers with (unlike the cosmetic CSS brightness/contrast filter
  // that operates on an already-8-bit image). The store seeds 0/0 = "unset" → send undefined
  // so the backend uses its default window; only send real values once windowWidth > 0.
  const wlActive = windowWidth > 0;
  const wc = wlActive ? windowCenter : undefined;
  const ww = wlActive ? windowWidth : undefined;

  // Debounce slice index AND window/level together — both hit the same per-slice server
  // render, so a W/L drag must not fire a request per frame (the exact overload the slice
  // debounce prevents). One combined debounced snapshot.
  const [debounced, setDebounced] = useState({ slice: currentSliceIndex, wc, ww });
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      setDebounced({ slice: currentSliceIndex, wc, ww });
    }, DEBOUNCE_DELAY);
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [currentSliceIndex, wc, ww]);

  const debouncedSliceIndex = debounced.slice;

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
      debounced.wc ?? null,
      debounced.ww ?? null,
    ],
    queryFn: async () => {
      const result = currentSeries && currentSeries.file_id
        ? await imagingAPI.getMatplotlib2D(
            currentSeries.file_id,
            debouncedSliceIndex,
            debounced.wc,   // window_center (raw-intensity VOI-LUT)
            debounced.ww,   // window_width
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
