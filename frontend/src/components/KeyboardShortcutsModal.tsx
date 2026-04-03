/**
 * Keyboard Shortcuts Help Modal.
 *
 * Shows all available keyboard shortcuts organized by context.
 * Triggered by pressing "?" key anywhere in the app.
 *
 * @module components/KeyboardShortcutsModal
 */

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Keyboard, X } from 'lucide-react';

interface ShortcutGroup {
  title: string;
  shortcuts: { keys: string[]; description: string }[];
}

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: 'Navigation',
    shortcuts: [
      { keys: ['Scroll'], description: 'Navigate slices' },
      { keys: ['Ctrl', '+'], description: 'Zoom in' },
      { keys: ['Ctrl', '-'], description: 'Zoom out' },
      { keys: ['Ctrl', '0'], description: 'Reset view' },
      { keys: ['?'], description: 'Show this help' },
    ],
  },
  {
    title: 'Segmentation Tools',
    shortcuts: [
      { keys: ['B'], description: 'Brush tool' },
      { keys: ['E'], description: 'Eraser tool' },
      { keys: ['S'], description: 'Toggle overlay visibility' },
      { keys: ['+'], description: 'Increase brush size' },
      { keys: ['-'], description: 'Decrease brush size' },
      { keys: ['1', '-', '9'], description: 'Select label (1-9)' },
    ],
  },
  {
    title: 'Edit',
    shortcuts: [
      { keys: ['Ctrl', 'Z'], description: 'Undo' },
      { keys: ['Ctrl', 'Shift', 'Z'], description: 'Redo' },
      { keys: ['Ctrl', 'S'], description: 'Save segmentation' },
    ],
  },
  {
    title: 'Measurement Tools',
    shortcuts: [
      { keys: ['R'], description: 'Ruler (distance)' },
      { keys: ['A'], description: 'Angle measurement' },
      { keys: ['O'], description: 'Elliptical ROI (area)' },
      { keys: ['Del'], description: 'Clear measurements' },
    ],
  },
  {
    title: 'View',
    shortcuts: [
      { keys: ['F'], description: 'Toggle fullscreen' },
      { keys: ['M'], description: 'Toggle matplotlib mode' },
      { keys: ['2'], description: 'Switch to 2D view' },
      { keys: ['3'], description: 'Switch to 3D view' },
    ],
  },
];

export default function KeyboardShortcutsModal() {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger in input/textarea
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

      if (e.key === '?') {
        e.preventDefault();
        setIsOpen(prev => !prev);
      }
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100]"
            onClick={() => setIsOpen(false)}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 flex items-center justify-center z-[101] p-4"
          >
            <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden">
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
                <div className="flex items-center gap-3">
                  <Keyboard className="w-5 h-5 text-blue-400" />
                  <h2 className="text-lg font-semibold text-white">Keyboard Shortcuts</h2>
                </div>
                <button
                  onClick={() => setIsOpen(false)}
                  className="p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Content */}
              <div className="px-6 py-4 overflow-y-auto max-h-[60vh]">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {SHORTCUT_GROUPS.map((group) => (
                    <div key={group.title}>
                      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                        {group.title}
                      </h3>
                      <div className="space-y-2">
                        {group.shortcuts.map((shortcut, i) => (
                          <div key={i} className="flex items-center justify-between">
                            <span className="text-sm text-gray-300">{shortcut.description}</span>
                            <div className="flex items-center gap-1">
                              {shortcut.keys.map((key, j) => (
                                <span key={j}>
                                  {key === '-' && j > 0 && j < shortcut.keys.length - 1 ? (
                                    <span className="text-gray-500 text-xs mx-0.5">to</span>
                                  ) : (
                                    <kbd className="px-2 py-0.5 bg-gray-800 border border-gray-600 rounded text-xs text-gray-300 font-mono min-w-[24px] text-center">
                                      {key}
                                    </kbd>
                                  )}
                                  {j < shortcut.keys.length - 1 && key !== '-' && shortcut.keys[j + 1] !== '-' && (
                                    <span className="text-gray-600 text-xs mx-0.5">+</span>
                                  )}
                                </span>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-3 border-t border-gray-800 text-center">
                <p className="text-xs text-gray-500">
                  Press <kbd className="px-1.5 py-0.5 bg-gray-800 border border-gray-600 rounded text-xs font-mono">?</kbd> to toggle this panel &bull; <kbd className="px-1.5 py-0.5 bg-gray-800 border border-gray-600 rounded text-xs font-mono">Esc</kbd> to close
                </p>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
