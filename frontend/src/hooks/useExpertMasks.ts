/**
 * Hook for loading and managing expert annotation masks as overlays.
 *
 * Downloads NIfTI expert masks via the binary mask endpoint and stores
 * them in memory for contour-based overlay rendering.
 *
 * @module hooks/useExpertMasks
 */

import { useState, useCallback, useRef } from 'react';
import { apiClient } from '@/services/apiClient';
import type { ExpertMaskData, ExpertType } from '@/types';
import { EXPERT_COLORS } from '@/types';

/**
 * Classify an expert mask filename into an ExpertType.
 *
 * Categories:
 *   - expert: Manual expert annotation (desc-expertNN)
 *   - output: Algorithm output mask (desc-outputN, desc-maskN, out_mask)
 *   - consensus: STAPLE consensus or unclassified (label-lesion_dseg without descriptor)
 */
export function classifyExpertFile(filename: string): ExpertType {
  const lower = filename.toLowerCase();
  // Expert annotation: desc-expert01, desc-expert02, Expert01, experto12, etc.
  if (/expert[eo]?\d/.test(lower)) return 'expert';
  // Algorithm output: desc-output1, desc-output2, desc-mask, desc-mask2, out_mask
  if (/desc-output|desc-mask|out_mask/.test(lower)) return 'output';
  // Default: consensus (label-lesion_dseg without expert/output descriptor)
  return 'consensus';
}

/**
 * Derive a human-readable label from a BIDS mask filename.
 * Extracts type + output number + session info.
 *
 * Examples:
 *   "sub-MS007_ses-01_label-lesion_desc-expert02_dseg.nii.gz" → "Expert Annotation (TP1)"
 *   "sub-MS007_ses-01_label-lesion_desc-output1_dseg.nii.gz"  → "Algorithm Output 1 (TP1)"
 *   "sub-MS007_ses-01_label-lesion_desc-output2_dseg.nii.gz"  → "Algorithm Output 2 (TP1)"
 *   "sub-MS007_ses-01_label-lesion_dseg.nii.gz"               → "Consensus (TP1)"
 */
export function deriveExpertLabel(filename: string): string {
  const expertType = classifyExpertFile(filename);
  let baseLabel = EXPERT_COLORS[expertType].label;

  // For output masks, append the output number if present
  if (expertType === 'output') {
    const numMatch = filename.match(/desc-(?:output|mask)(\d+)/i);
    if (numMatch) {
      baseLabel = `${baseLabel} ${numMatch[1]}`;
    }
  }

  // Extract session number from BIDS filename
  const sesMatch = filename.match(/ses-(\d+)/i);
  if (sesMatch) {
    const tp = parseInt(sesMatch[1], 10);
    return `${baseLabel} (TP${tp})`;
  }

  return baseLabel;
}

/**
 * Get display label and color for an expert type.
 */
export function getExpertDisplayInfo(type: ExpertType) {
  return EXPERT_COLORS[type];
}

interface UseExpertMasksReturn {
  /** Map of instanceId -> expert mask data */
  expertMasks: Map<string, ExpertMaskData>;
  /** Toggle visibility of an expert mask (loads on first toggle) */
  toggleExpert: (instanceId: string, filename: string) => Promise<void>;
  /** Check if any experts are currently loading */
  isLoading: boolean;
  /** Clear all loaded masks */
  clearAll: () => void;
}

/**
 * Hook for managing expert annotation mask overlays.
 */
export function useExpertMasks(): UseExpertMasksReturn {
  const [expertMasks, setExpertMasks] = useState<Map<string, ExpertMaskData>>(new Map());
  const [isLoading, setIsLoading] = useState(false);
  const loadingRef = useRef<Set<string>>(new Set());

  const toggleExpert = useCallback(async (instanceId: string, filename: string) => {
    setExpertMasks(prev => {
      const next = new Map(prev);
      const existing = next.get(instanceId);

      if (existing) {
        // Toggle visibility
        next.set(instanceId, { ...existing, visible: !existing.visible });
        return next;
      }

      // First time: create placeholder entry
      const expertType = classifyExpertFile(filename);
      const displayInfo = getExpertDisplayInfo(expertType);
      next.set(instanceId, {
        instanceId,
        label: displayInfo.label,
        color: displayInfo.color,
        mask: null,
        depth: 0,
        height: 0,
        width: 0,
        visible: true,
        loading: true,
      });
      return next;
    });

    // If already loaded or currently loading, just toggle visibility
    const existing = expertMasks.get(instanceId);
    if (existing?.mask || loadingRef.current.has(instanceId)) return;

    // Download the mask binary data
    loadingRef.current.add(instanceId);
    setIsLoading(true);

    try {
      const response = await apiClient.get(
        `/api/v1/studies/instances/${instanceId}/mask-data`,
        { responseType: 'arraybuffer' }
      );

      const buffer = response.data as ArrayBuffer;
      const view = new DataView(buffer);
      const depth = view.getUint32(0, true);
      const height = view.getUint32(4, true);
      const width = view.getUint32(8, true);
      const maskData = new Uint8Array(buffer, 12);

      const expertType = classifyExpertFile(filename);
      const displayInfo = getExpertDisplayInfo(expertType);

      setExpertMasks(prev => {
        const next = new Map(prev);
        next.set(instanceId, {
          instanceId,
          label: displayInfo.label,
          color: displayInfo.color,
          mask: maskData,
          depth,
          height,
          width,
          visible: true,
          loading: false,
        });
        return next;
      });
    } catch (error) {
      console.error('[ExpertMasks] Failed to load mask:', instanceId, error);
      setExpertMasks(prev => {
        const next = new Map(prev);
        next.delete(instanceId);
        return next;
      });
    } finally {
      loadingRef.current.delete(instanceId);
      setIsLoading(loadingRef.current.size > 0);
    }
  }, [expertMasks]);

  const clearAll = useCallback(() => {
    setExpertMasks(new Map());
  }, []);

  return { expertMasks, toggleExpert, isLoading, clearAll };
}
