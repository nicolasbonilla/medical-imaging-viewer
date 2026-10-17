import { create } from 'zustand';
import type { ImageSeriesResponse, StorageFileInfo, ImageOrientation } from '@/types';
import type { PlaneName } from '@/volume/sliceGeometry';

export interface CursorInfo {
  x: number;
  y: number;
  z: number;
  intensity: number | null;
  /** v3 client viewer: voxel indices (i, j, k) under the cursor. */
  voxel?: [number, number, number];
  /** v3 client viewer: scanner coordinates (mm) through the affine. */
  world?: [number, number, number];
  /** v3 client viewer: full-precision voxel value (not an 8-bit display grey). */
  value?: number | null;
  /** v3 client viewer: segmentation label under the cursor (0 = none). */
  label?: number;
}

/** 2D display path: 'client' renders in the browser from the NIfTI (v3, default);
 *  the server paths ('standard' PNG / 'matplotlib') remain as fallbacks. */
export type OrientationMode = 'anatomical' | 'voxel';
export type Voxel = [number, number, number];

interface ViewerState {
  // Hierarchical context for segmentation
  currentPatientId: string | null;
  currentStudyId: string | null;
  currentSeriesId: string | null;
  setHierarchicalContext: (patientId: string | null, studyId: string | null, seriesId: string | null) => void;

  // All file_ids from all instances in the current study (for study-level segmentation queries)
  allFileIds: string[];
  setAllFileIds: (fileIds: string[]) => void;

  // Current image series
  currentSeries: ImageSeriesResponse | null;
  setCurrentSeries: (series: ImageSeriesResponse | null) => void;

  // Current slice index. Always the index along the ACTIVE 2D view's normal axis
  // (= the k index on the legacy server path, whose only view is the k plane).
  currentSliceIndex: number;
  setCurrentSliceIndex: (index: number) => void;

  // ---- v3 client 2D viewer (multi-planar) ---------------------------------------
  /** Active plane slot of the 2D viewer. */
  slicePlane: PlaneName;
  setSlicePlane: (plane: PlaneName) => void;
  /** 3-D cursor (voxel i, j, k); each plane shows the slice through it. */
  cursorVoxel: Voxel | null;
  setCursorVoxel: (voxel: Voxel) => void;
  /** Normal axis and depth of the active view (published by the client viewport). */
  sliceNormalAxis: 0 | 1 | 2;
  sliceCount: number | null;
  setActiveSliceGeometry: (normalAxis: 0 | 1 | 2, depth: number) => void;
  /** Anatomical (affine) or voxel (array order, = legacy server layout) display. */
  orientationMode: OrientationMode;
  setOrientationMode: (mode: OrientationMode) => void;
  /** Bilinear display interpolation of the grey image (overlays stay voxel-exact). */
  smoothDisplay: boolean;
  setSmoothDisplay: (on: boolean) => void;
  /** Request to centre the 2D views on a mask voxel (backend z, y, x), consumed by the viewport. */
  focusRequest: { z: number; y?: number; x?: number; nonce: number } | null;
  requestFocus: (z: number, y?: number, x?: number) => void;

  // Window/Level settings
  windowCenter: number;
  windowWidth: number;
  setWindowLevel: (center: number, width: number) => void;

  // Brightness/Contrast (CSS filter, 0-200, default 100)
  brightness: number;
  contrast: number;
  setBrightness: (value: number) => void;
  setContrast: (value: number) => void;
  resetImageAdjustments: () => void;

  // Cursor info
  cursorInfo: CursorInfo | null;
  setCursorInfo: (info: CursorInfo | null) => void;

  // Slice histogram (256 bins of grayscale intensity counts)
  sliceHistogram: number[] | null;
  setSliceHistogram: (histogram: number[] | null) => void;

  // Selected files
  selectedFiles: StorageFileInfo[];
  setSelectedFiles: (files: StorageFileInfo[]) => void;
  addSelectedFile: (file: StorageFileInfo) => void;
  removeSelectedFile: (fileId: string) => void;

  // View mode
  viewMode: '2d' | '3d';
  setViewMode: (mode: '2d' | '3d') => void;

  // 3D orientation
  orientation: ImageOrientation;
  setOrientation: (orientation: ImageOrientation) => void;

  // 3D rendering controls
  render3DMode: 'volume' | 'multiplanar';
  colormap3D: string;
  clipPlaneEnabled: boolean;
  clipPlanePosition: number;
  clipPlaneAxis: 'axial' | 'coronal' | 'sagittal';
  setRender3DMode: (mode: 'volume' | 'multiplanar') => void;
  setColormap3D: (colormap: string) => void;
  setClipPlane: (enabled: boolean, position?: number) => void;
  setClipPlaneAxis: (axis: 'axial' | 'coronal' | 'sagittal') => void;

  // Loading state
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;

  // Zoom level
  zoomLevel: number;
  setZoomLevel: (zoom: number) => void;

  // Pan offset
  panOffset: { x: number; y: number };
  setPanOffset: (offset: { x: number; y: number }) => void;

  // Measurement tool (controlled from toolbar, read by MeasurementOverlay)
  measurementTool: 'ruler' | 'angle' | 'ellipse' | null;
  setMeasurementTool: (tool: 'ruler' | 'angle' | 'ellipse' | null) => void;
  measurementClearSignal: number;
  triggerMeasurementClear: () => void;

  // Reset all
  reset: () => void;
}

const initialState = {
  currentPatientId: null,
  currentStudyId: null,
  currentSeriesId: null,
  allFileIds: [] as string[],
  currentSeries: null,
  currentSliceIndex: 0,
  slicePlane: 'axial' as PlaneName,
  cursorVoxel: null as Voxel | null,
  sliceNormalAxis: 2 as 0 | 1 | 2,
  sliceCount: null as number | null,
  orientationMode: 'anatomical' as OrientationMode,
  smoothDisplay: true,
  focusRequest: null as { z: number; y?: number; x?: number; nonce: number } | null,
  windowCenter: 0,
  windowWidth: 0,
  brightness: 100,
  contrast: 100,
  cursorInfo: null as CursorInfo | null,
  sliceHistogram: null as number[] | null,
  selectedFiles: [],
  viewMode: '2d' as const,
  orientation: 'axial' as ImageOrientation,
  render3DMode: 'volume' as const,
  colormap3D: 'gray',
  clipPlaneEnabled: false,
  clipPlanePosition: 0.5,
  clipPlaneAxis: 'axial' as const,
  isLoading: false,
  zoomLevel: 1,
  panOffset: { x: 0, y: 0 },
  measurementTool: null as 'ruler' | 'angle' | 'ellipse' | null,
  measurementClearSignal: 0,
};

export const useViewerStore = create<ViewerState>((set) => ({
  ...initialState,

  setHierarchicalContext: (patientId, studyId, seriesId) =>
    set({ currentPatientId: patientId, currentStudyId: studyId, currentSeriesId: seriesId }),

  setAllFileIds: (fileIds) => set({ allFileIds: fileIds }),

  // A different image invalidates the 3-D cursor and the active view geometry.
  setCurrentSeries: (series) => set((s) => (
    s.currentSeries?.file_id === series?.file_id && series
      ? { currentSeries: series }
      : { currentSeries: series, cursorVoxel: null, sliceCount: null, sliceNormalAxis: 2 }
  )),

  setCurrentSliceIndex: (index) => set((s) => {
    if (!s.cursorVoxel) return { currentSliceIndex: index };
    const cursorVoxel = [...s.cursorVoxel] as Voxel;
    cursorVoxel[s.sliceNormalAxis] = index;
    return { currentSliceIndex: index, cursorVoxel };
  }),

  setSlicePlane: (plane) => set({ slicePlane: plane }),

  setCursorVoxel: (voxel) => set((s) => ({
    cursorVoxel: [...voxel] as Voxel,
    currentSliceIndex: voxel[s.sliceNormalAxis],
  })),

  setActiveSliceGeometry: (normalAxis, depth) => set((s) => {
    const fromCursor = s.cursorVoxel?.[normalAxis];
    const idx = fromCursor ?? s.currentSliceIndex;
    return {
      sliceNormalAxis: normalAxis,
      sliceCount: depth,
      currentSliceIndex: Math.max(0, Math.min(depth - 1, idx)),
    };
  }),

  setOrientationMode: (mode) => set({ orientationMode: mode }),
  setSmoothDisplay: (on) => set({ smoothDisplay: on }),
  requestFocus: (z, y, x) => set((s) => ({ focusRequest: { z, y, x, nonce: (s.focusRequest?.nonce ?? 0) + 1 } })),

  setWindowLevel: (center, width) =>
    set({ windowCenter: center, windowWidth: width }),

  setBrightness: (value) => set({ brightness: value }),
  setContrast: (value) => set({ contrast: value }),
  resetImageAdjustments: () => set({ brightness: 100, contrast: 100 }),

  setCursorInfo: (info) => set({ cursorInfo: info }),

  setSliceHistogram: (histogram) => set({ sliceHistogram: histogram }),

  setSelectedFiles: (files) => set({ selectedFiles: files }),

  addSelectedFile: (file) =>
    set((state) => ({
      selectedFiles: [...state.selectedFiles, file],
    })),

  removeSelectedFile: (fileId) =>
    set((state) => ({
      selectedFiles: state.selectedFiles.filter((f) => f.id !== fileId),
    })),

  setViewMode: (mode) => set({ viewMode: mode }),

  setOrientation: (orientation) => set({ orientation }),

  setRender3DMode: (mode) => set({ render3DMode: mode }),
  setColormap3D: (colormap) => set({ colormap3D: colormap }),
  setClipPlane: (enabled, position) => set((state) => ({
    clipPlaneEnabled: enabled,
    clipPlanePosition: position ?? state.clipPlanePosition,
  })),
  setClipPlaneAxis: (axis) => set({ clipPlaneAxis: axis }),

  setIsLoading: (loading) => set({ isLoading: loading }),

  setZoomLevel: (zoom) => set({ zoomLevel: zoom }),

  setPanOffset: (offset) => set({ panOffset: offset }),

  setMeasurementTool: (tool) => set({ measurementTool: tool }),
  triggerMeasurementClear: () => set((s) => ({ measurementClearSignal: s.measurementClearSignal + 1, measurementTool: null })),

  reset: () => set(initialState),
}));
