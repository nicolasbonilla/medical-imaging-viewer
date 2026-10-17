import { useState, useCallback, useMemo } from 'react';

/**
 * 2D display path. 'client' (v3, default) renders in the browser from the NIfTI —
 * full bit depth, instant W/L, three planes. 'standard' (server 8-bit PNG) and
 * 'matplotlib' (server render) remain as fallbacks until parity is signed off;
 * 'niivue' is the earlier view-only GPU mode.
 */
export type RenderMode = 'client' | 'standard' | 'matplotlib' | 'niivue';

/** Render modes that need the server's per-slice PNGs in currentSeries.slices. */
export function needsServerSlices(mode: RenderMode): boolean {
  return mode === 'standard' || mode === 'matplotlib';
}

export function useViewerControls() {
  const [renderMode, setRenderModeInternal] = useState<RenderMode>('client');
  const [colormap, setColormap] = useState('gray');
  const [segmentationMode, setSegmentationMode] = useState(false);

  const setRenderMode = useCallback((mode: RenderMode) => {
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
