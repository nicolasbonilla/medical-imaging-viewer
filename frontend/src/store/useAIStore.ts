/**
 * AI Segmentation Store - Zustand state for AI-powered brain segmentation.
 *
 * Manages:
 * - AI mode (interactive click-based, auto brain structures)
 * - Click points for interactive segmentation
 * - Selected AI model
 * - Processing state and progress
 *
 * @module store/useAIStore
 */

import { create } from 'zustand';
import type { AIMode, AIModel, ClickPoint3D, AITaskResult } from '@/types';

interface AIState {
  // Mode
  aiMode: AIMode;

  // Interactive mode
  clickPoints: ClickPoint3D[];

  // Model selection
  selectedModel: AIModel;

  // Processing
  isProcessing: boolean;
  taskId: string | null;
  progress: number;
  lastResult: AITaskResult | null;
  error: string | null;

  // Actions
  setAIMode: (mode: AIMode) => void;
  addClickPoint: (point: ClickPoint3D) => void;
  removeLastClick: () => void;
  clearClicks: () => void;
  setSelectedModel: (model: AIModel) => void;
  setProcessing: (processing: boolean) => void;
  setTaskId: (taskId: string | null) => void;
  setProgress: (progress: number) => void;
  setLastResult: (result: AITaskResult | null) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  aiMode: null as AIMode,
  clickPoints: [] as ClickPoint3D[],
  selectedModel: 'sam_med3d' as AIModel,
  isProcessing: false,
  taskId: null as string | null,
  progress: 0,
  lastResult: null as AITaskResult | null,
  error: null as string | null,
};

export const useAIStore = create<AIState>()((set) => ({
  ...initialState,

  setAIMode: (mode) =>
    set({
      aiMode: mode,
      clickPoints: [],
      error: null,
      selectedModel: mode === 'auto' ? 'synthseg' : 'sam_med3d',
    }),

  addClickPoint: (point) =>
    set((state) => ({
      clickPoints: [...state.clickPoints, point],
    })),

  removeLastClick: () =>
    set((state) => ({
      clickPoints: state.clickPoints.slice(0, -1),
    })),

  clearClicks: () => set({ clickPoints: [] }),

  setSelectedModel: (model) => set({ selectedModel: model }),

  setProcessing: (processing) => set({ isProcessing: processing }),

  setTaskId: (taskId) => set({ taskId }),

  setProgress: (progress) => set({ progress }),

  setLastResult: (result) => set({ lastResult: result }),

  setError: (error) => set({ error }),

  reset: () => set(initialState),
}));
