import { useState, useCallback, useMemo } from 'react';

export function useViewerControls() {
  const [renderMode, setRenderModeInternal] = useState<'standard' | 'matplotlib'>('standard');
  const [colormap, setColormap] = useState('gray');
  const [segmentationMode, setSegmentationMode] = useState(false);

  const setRenderMode = useCallback((mode: 'standard' | 'matplotlib') => {
    console.log('⚠️ setRenderMode CALLED - changing to', mode);
    console.trace('Stack trace:');
    setRenderModeInternal(mode);
  }, []);

  // Axis limits state (temporary values from inputs)
  const [xMin, setXMin] = useState<string>('');
  const [xMax, setXMax] = useState<string>('');
  const [yMin, setYMin] = useState<string>('');
  const [yMax, setYMax] = useState<string>('');

  // Applied limits (used in query)
  const [appliedXMin, setAppliedXMin] = useState<string>('');
  const [appliedXMax, setAppliedXMax] = useState<string>('');
  const [appliedYMin, setAppliedYMin] = useState<string>('');
  const [appliedYMax, setAppliedYMax] = useState<string>('');

  return useMemo(() => ({
    renderMode,
    setRenderMode,
    colormap,
    setColormap,
    segmentationMode,
    setSegmentationMode,
    xMin,
    setXMin,
    xMax,
    setXMax,
    yMin,
    setYMin,
    yMax,
    setYMax,
    appliedXMin,
    setAppliedXMin,
    appliedXMax,
    setAppliedXMax,
    appliedYMin,
    setAppliedYMin,
    appliedYMax,
    setAppliedYMax,
  }), [renderMode, colormap, segmentationMode, xMin, xMax, yMin, yMax, appliedXMin, appliedXMax, appliedYMin, appliedYMax]);
}
