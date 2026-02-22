import { create } from 'zustand';
import type { ImageSeriesResponse, StorageFileInfo, ImageOrientation } from '@/types';

export interface CursorInfo {
  x: number;
  y: number;
  z: number;
  intensity: number | null;
}

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

  // Current slice index
  currentSliceIndex: number;
  setCurrentSliceIndex: (index: number) => void;

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

  // Loading state
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;

  // Zoom level
  zoomLevel: number;
  setZoomLevel: (zoom: number) => void;

  // Pan offset
  panOffset: { x: number; y: number };
  setPanOffset: (offset: { x: number; y: number }) => void;

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
  windowCenter: 0,
  windowWidth: 0,
  brightness: 100,
  contrast: 100,
  cursorInfo: null as CursorInfo | null,
  sliceHistogram: null as number[] | null,
  selectedFiles: [],
  viewMode: '2d' as const,
  orientation: 'axial' as ImageOrientation,
  isLoading: false,
  zoomLevel: 1,
  panOffset: { x: 0, y: 0 },
};

export const useViewerStore = create<ViewerState>((set) => ({
  ...initialState,

  setHierarchicalContext: (patientId, studyId, seriesId) =>
    set({ currentPatientId: patientId, currentStudyId: studyId, currentSeriesId: seriesId }),

  setAllFileIds: (fileIds) => set({ allFileIds: fileIds }),

  setCurrentSeries: (series) => set({ currentSeries: series }),

  setCurrentSliceIndex: (index) => set({ currentSliceIndex: index }),

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

  setIsLoading: (loading) => set({ isLoading: loading }),

  setZoomLevel: (zoom) => set({ zoomLevel: zoom }),

  setPanOffset: (offset) => set({ panOffset: offset }),

  reset: () => set(initialState),
}));
