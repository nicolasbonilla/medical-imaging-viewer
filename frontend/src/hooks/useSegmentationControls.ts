import { useState, useMemo } from 'react';
import type { SegmentationResponse } from '../types/segmentation';

export function useSegmentationControls() {
  const [currentSegmentation, setCurrentSegmentation] = useState<SegmentationResponse | null>(null);
  const [selectedLabelId, setSelectedLabelId] = useState(1);
  const [brushSize, setBrushSize] = useState(3);
  const [eraseMode, setEraseMode] = useState(false);
  const [showOverlay, setShowOverlay] = useState(true);

  return useMemo(() => ({
    currentSegmentation,
    setCurrentSegmentation,
    selectedLabelId,
    setSelectedLabelId,
    brushSize,
    setBrushSize,
    eraseMode,
    setEraseMode,
    showOverlay,
    setShowOverlay,
  }), [currentSegmentation, selectedLabelId, brushSize, eraseMode, showOverlay]);
}
