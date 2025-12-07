/**
 * Hook for managing segmentation data queries and mutations.
 * Handles fetching segmentation lists and applying paint strokes.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { segmentationAPI } from '@/api/segmentation';
import { useViewerStore } from '@/store/useViewerStore';
import type { SegmentationResponse, PaintStroke, ImageShape } from '../types/segmentation';

interface UseSegmentationDataProps {
  currentSegmentation: SegmentationResponse | null;
  setCurrentSegmentation: (seg: SegmentationResponse | null) => void;
  onPaintComplete?: () => void;
}

export function useSegmentationData({
  currentSegmentation,
  setCurrentSegmentation,
  onPaintComplete,
}: UseSegmentationDataProps) {
  const { currentSeries } = useViewerStore();
  const queryClient = useQueryClient();

  // Fetch segmentations list
  const { data: segmentations } = useQuery({
    queryKey: ['segmentations', currentSeries?.file_id],
    queryFn: () =>
      currentSeries?.file_id
        ? segmentationAPI.listSegmentations(currentSeries.file_id)
        : Promise.resolve([]),
    enabled: !!currentSeries?.file_id,
  });

  // Create segmentation mutation
  const createSegmentationMutation = useMutation({
    mutationFn: async ({
      fileId,
      imageShape,
    }: {
      fileId: string;
      imageShape: ImageShape;
    }) => {
      return segmentationAPI.createSegmentation({
        file_id: fileId,
        image_shape: imageShape,
        labels: [
          { id: 0, name: 'Background', color: '#000000', opacity: 0.0, visible: false },
          { id: 1, name: 'Lesion', color: '#FF0000', opacity: 0.5, visible: true },
        ],
      });
    },
    onSuccess: (data) => {
      setCurrentSegmentation(data);
      queryClient.invalidateQueries({ queryKey: ['segmentations'] });
    },
  });

  // Paint stroke mutation
  const paintStrokeMutation = useMutation({
    mutationFn: async (stroke: PaintStroke) => {
      if (!currentSegmentation) {
        throw new Error('No active segmentation');
      }
      return segmentationAPI.applyPaintStroke(currentSegmentation.segmentation_id, stroke);
    },
    onSuccess: () => {
      onPaintComplete?.();
    },
  });

  return {
    segmentations,
    createSegmentationMutation,
    paintStrokeMutation,
  };
}
