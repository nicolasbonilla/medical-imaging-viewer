/**
 * Hook for managing matplotlib visualization queries and rendering.
 * Handles fetching matplotlib-rendered images from the backend.
 */

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

export function useMatplotlibVisualization({
  colormap,
  appliedXMin,
  appliedXMax,
  appliedYMin,
  appliedYMax,
}: UseMatplotlibVisualizationProps) {
  const { currentSeries, currentSliceIndex } = useViewerStore();

  const { data: matplotlibData, isLoading: matplotlibLoading, error } = useQuery({
    queryKey: [
      'matplotlib-2d',
      currentSeries?.file_id,
      currentSliceIndex,
      colormap,
      appliedXMin,
      appliedXMax,
      appliedYMin,
      appliedYMax,
    ],
    queryFn: async () => {
      // NEVER pass segmentation_id to backend - frontend always handles segmentation overlay
      console.log('🔍 [HOOK] useMatplotlibVisualization queryFn called', {
        file_id: currentSeries?.file_id,
        slice: currentSliceIndex,
        colormap,
        bounds: { appliedXMin, appliedXMax, appliedYMin, appliedYMax }
      });

      const result = currentSeries && currentSeries.file_id
        ? await imagingAPI.getMatplotlib2D(
            currentSeries.file_id,
            currentSliceIndex,
            undefined,
            undefined,
            colormap,
            appliedXMin.trim() !== '' ? parseInt(appliedXMin) : undefined,
            appliedXMax.trim() !== '' ? parseInt(appliedXMax) : undefined,
            appliedYMin.trim() !== '' ? parseInt(appliedYMin) : undefined,
            appliedYMax.trim() !== '' ? parseInt(appliedYMax) : undefined,
            false  // minimal=false to show axes, labels, grid, and colorbar
          )
        : null;

      console.log('🔍 [HOOK] Result from API:', {
        hasResult: !!result,
        resultType: typeof result,
        hasImage: result ? 'image' in result : false,
        imageLength: result?.image?.length,
        imagePrefix: result?.image?.substring(0, 50)
      });

      return result;
    },
    enabled: !!currentSeries?.file_id,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  console.log('🔍 [HOOK] Current state:', {
    hasData: !!matplotlibData,
    dataType: typeof matplotlibData,
    hasImage: matplotlibData ? 'image' in matplotlibData : false,
    imageLength: matplotlibData?.image?.length,
    isLoading: matplotlibLoading,
    hasError: !!error,
    error: error
  });

  return {
    matplotlibData,
    matplotlibLoading,
  };
}
