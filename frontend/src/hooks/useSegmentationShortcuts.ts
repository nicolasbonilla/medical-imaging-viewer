/**
 * useSegmentationShortcuts - Keyboard shortcuts for segmentation tools.
 *
 * Follows the same pattern as useSliceNavigation: window.addEventListener('keydown')
 * with proper cleanup on unmount.
 *
 * Shortcuts:
 * - Ctrl+Z: Undo last stroke
 * - Ctrl+Y / Ctrl+Shift+Z: Redo
 * - E: Toggle eraser / brush
 * - B: Activate brush
 * - S: Toggle overlay visibility
 * - + / = / ]: Increase brush size
 * - - / _ / [: Decrease brush size
 * - 1-9: Select label by number
 *
 * @module hooks/useSegmentationShortcuts
 */

import { useEffect, useRef } from 'react';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { UseSegmentationMaskReturn } from '@/hooks/useSegmentationMask';

interface UseSegmentationShortcutsProps {
  /** Whether shortcuts are active (requires segmentation mode + active segmentation) */
  enabled: boolean;
  /** Mask hook for undo/redo operations */
  segmentationMask: UseSegmentationMaskReturn;
  /** Callback to refresh canvas after undo/redo */
  onRefresh?: () => void;
}

/** Elements that should NOT trigger shortcuts when focused */
function isInputFocused(): boolean {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
  if ((el as HTMLElement).isContentEditable) return true;
  return false;
}

export function useSegmentationShortcuts({
  enabled,
  segmentationMask,
  onRefresh,
}: UseSegmentationShortcutsProps): void {
  // Use refs so the keydown handler always sees current values
  // without needing to re-attach the listener on every state change
  const enabledRef = useRef(enabled);
  const maskRef = useRef(segmentationMask);
  const refreshRef = useRef(onRefresh);

  enabledRef.current = enabled;
  maskRef.current = segmentationMask;
  refreshRef.current = onRefresh;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!enabledRef.current) return;
      if (isInputFocused()) return;

      const store = useSegmentationStore.getState();
      const mask = maskRef.current;

      // --- Undo: Ctrl+Z ---
      if (e.key === 'z' && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
        e.preventDefault();
        if (mask.undo()) {
          refreshRef.current?.();
        }
        return;
      }

      // --- Redo: Ctrl+Y or Ctrl+Shift+Z ---
      if (
        (e.key === 'y' && (e.ctrlKey || e.metaKey)) ||
        (e.key === 'z' && (e.ctrlKey || e.metaKey) && e.shiftKey)
      ) {
        e.preventDefault();
        if (mask.redo()) {
          refreshRef.current?.();
        }
        return;
      }

      // Skip remaining shortcuts if Ctrl/Meta/Alt is held (avoid clashes)
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      // --- Toggle eraser / brush: E ---
      if (e.key === 'e' || e.key === 'E') {
        e.preventDefault();
        store.setPaintTool(store.paintTool.tool === 'eraser' ? 'brush' : 'eraser');
        return;
      }

      // --- Activate brush: B ---
      if (e.key === 'b' || e.key === 'B') {
        e.preventDefault();
        store.setPaintTool('brush');
        return;
      }

      // --- Toggle overlay: S ---
      if (e.key === 's' || e.key === 'S') {
        e.preventDefault();
        store.toggleOverlayVisibility();
        return;
      }

      // --- Increase brush size: + / = / ] ---
      if (e.key === '+' || e.key === '=' || e.key === ']') {
        e.preventDefault();
        store.setBrushSize(store.paintTool.brushSize + 1);
        return;
      }

      // --- Decrease brush size: - / _ / [ ---
      if (e.key === '-' || e.key === '_' || e.key === '[') {
        e.preventDefault();
        store.setBrushSize(store.paintTool.brushSize - 1);
        return;
      }

      // --- Select label by number: 1-9 ---
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= 9) {
        e.preventDefault();
        const labels = store.activeSegmentation?.labels.filter((l) => l.id !== 0) ?? [];
        if (num <= labels.length) {
          store.setActiveLabel(labels[num - 1].id);
        }
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []); // Empty deps: handler uses refs for latest values
}

export default useSegmentationShortcuts;
