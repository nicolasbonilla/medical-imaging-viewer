import { create } from 'zustand';
import type { ImageSeriesResponse, StorageFileInfo, ImageOrientation } from '@/types';

interface ViewerState {
  // Hierarchical context for segmentation
  currentPatientId: string | null;
  currentStudyId: string | null;
  currentSeriesId: string | null;
  setHierarchicalContext: (patientId: string | null, studyId: string | null, seriesId: string | null) => void;

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
  currentSeries: null,
  currentSliceIndex: 0,
  windowCenter: 0,
  windowWidth: 0,
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

  setCurrentSeries: (series) => set({ currentSeries: series }),

  setCurrentSliceIndex: (index) => set({ currentSliceIndex: index }),

  setWindowLevel: (center, width) =>
    set({ windowCenter: center, windowWidth: width }),

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
